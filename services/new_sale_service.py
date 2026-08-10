#!/usr/bin/env python
from ast import pattern
import logging
import difflib
from unittest import result
from sqlalchemy import func, case, or_, and_, event
from sqlalchemy.orm import joinedload
from services.base_service import BaseService, get_session
from services.new_sale_item_service import NewSaleItemService
from services.new_batch_transaction_service import NewBachTransactionService
from services.sale_payment_term_service import SalePaymentTermService
from services.payment_transaction_service import PaymentTransactionService
from services.bank_account_service import BankAccountService
from services.daily_sales_cache_service import DailySalesCacheService
from services.bank_transaction_service import BankTransactionService
from models.new_sales import ProfessionalSale
from models.batch_transaction import TransactionType, BatchTransaction
from models.payment_transaction import PaymentMethodEnum, PaymentTransaction
from models.product_batch import ProductBatch
from models.sale_payment_term import SalePaymentTerm, PaymentStatusEnum
from models.new_sale_item import ProfessionalSaleItem
from models.bank_transactions import BankTransaction
from models.new_product import ProfessionalProduct
from models.customer_daily_notification import CustomerDailyNotification
from typing import List, Dict, Optional, Tuple, Any
from datetime import date, datetime, time, timedelta
from models.customers import Customer
from sqlalchemy import or_

logger = logging.getLogger(__name__)

class NewSaleService(BaseService[ProfessionalSale]):
    def __init__(self):
        super().__init__(ProfessionalSale)
        self.sale_item_service = NewSaleItemService()
        self.new_batch_transaction_service = NewBachTransactionService()
        self.sale_payment_term_service = SalePaymentTermService()
        self.payment_transaction_service = PaymentTransactionService()
        self.account_service = BankAccountService()
        self.bank_transaction_service = BankTransactionService()
        self._cash_account_id = None

    def create_sale(
        self,
        customer_id: int,
        sale_items: List[Dict],
        user_id: int,
        labour_expense: float,
        payment_type: str,
        credit_term_days: Optional[int] = None,
        payments: List[Dict] = None,
        delivery_name: Optional[str] = None,
        delivery_place: Optional[str] = None,
        delivery_phone: Optional[str] = None,
        delivery_plate: Optional[str] = None,
        sale_date: Optional[datetime] = None
    ):
        with get_session() as session:
            try:
                requested_qty_by_batch = {}
                for item in sale_items:
                    quantity = int(item.get('quantity', 0) or 0)
                    batch_id = item.get('batch_id')

                    if quantity <= 0:
                        raise ValueError(f"Invalid sale quantity {quantity} for batch {batch_id}")

                    requested_qty_by_batch[batch_id] = requested_qty_by_batch.get(batch_id, 0) + quantity

                for batch_id, requested_qty in requested_qty_by_batch.items():
                    batch = (
                        session.query(ProductBatch)
                        .filter(
                            ProductBatch.id == batch_id,
                            ProductBatch.is_deleted == False
                        )
                        .first()
                    )

                    if not batch:
                        raise ValueError(f"Batch {batch_id} not found")

                    if requested_qty > batch.available_quantity:
                        raise ValueError(
                            f"Insufficient stock for batch {batch_id}: requested {requested_qty}, available {batch.available_quantity}"
                        )

                total_amount = sum(item['quantity'] * item['dozen'] * item['unit_price'] for item in sale_items)
                payment_term_total = total_amount + labour_expense
                is_credit = False
                if payment_type.lower() == PaymentStatusEnum.CREDIT:
                    is_credit = True

                sale = ProfessionalSale(
                    customer_id=customer_id,
                    total_amount=total_amount,
                    is_credit_sale=is_credit,
                    labour_expense=labour_expense,
                    user_id=user_id,
                    delivery_name=delivery_name,
                    delivery_place=delivery_place,
                    delivery_phone=delivery_phone,
                    delivery_Plate=delivery_plate
                )
                if sale_date:
                    if isinstance(sale_date, date) and not isinstance(sale_date, datetime):
                        now = datetime.now()
                        sale_date = datetime.combine(sale_date, now.time())
                    sale.created_at = sale_date
                    sale.last_modified = sale_date
                session.add(sale)
                session.flush()

                for item in sale_items:
                    amount = item['quantity'] * item['dozen'] * item['unit_price']
                    is_despatch = item.get('for_despatch', False)  # FIX #1: default False
                    sale_item = {
                        'sale_id': sale.id,
                        'batch_id': item['batch_id'],
                        'unit_price': item['unit_price'],
                        'quantity': item['quantity'],
                        'dozen': item['dozen'],
                        'total': amount,
                        'for_despatch': is_despatch,
                        'created_at': sale_date,
                        'last_modified': sale_date,
                        'despatched_at': sale_date if is_despatch else None,  # FIX #4: audit trail
                    }
                    self.sale_item_service.create_with_session(session, sale_item)

                    batch_transaction = {
                        'batch_id': item['batch_id'],
                        'quantity': item['quantity'],
                        'transaction_type': TransactionType.SALE,
                        'reference_number': str(sale.id),
                        'notes': f"Sale #{sale.id}",
                        'user_id': user_id,
                        'created_at': sale_date,
                        'last_modified': sale_date
                    }
                    self.new_batch_transaction_service.create_with_session(session, batch_transaction)

                    batch = session.query(ProductBatch).get(item['batch_id'])
                    if batch:
                        qty_sold = item['quantity']
                        batch.available_quantity -= qty_sold
                        if batch.available_quantity < 0:
                            raise ValueError(
                                f"Batch {batch.id} went negative while saving sale #{sale.id}; requested {qty_sold}, available before sale was {batch.available_quantity + qty_sold}"
                            )
                        if batch.product:
                            batch.product.update_totals()

                due_date = None
                if is_credit and credit_term_days is not None:
                    base_date = sale_date.date() if isinstance(sale_date, datetime) else sale_date
                    due_date = base_date + timedelta(days=credit_term_days)

                sale_payment_term_data = {
                    'sale_id': sale.id,
                    'payment_status': PaymentStatusEnum.PAID if not is_credit else PaymentStatusEnum.CREDIT,
                    'total_amount': payment_term_total,
                    'paid_amount': 0.0,
                    'due_date': due_date,
                    'created_at': sale_date,
                    'last_modified': sale_date
                }
                sale_payment_term = self.sale_payment_term_service.create_with_session(session, sale_payment_term_data)
                session.flush()

                if payment_type == "paid" and payments:
                    for payment in payments:
                        self.payment_transaction_service.record_payment(
                            session,
                            sale_payment_term.id,
                            payment['amount'],
                            payment['bank_account_id'],
                            user_id,
                            payment_date=sale_date.date() if sale_date else date.today()
                        )
                    session.refresh(sale_payment_term)

                # FIX #1: default changed to False so missing key does NOT count as despatched
                if all(item.get('for_despatch', False) for item in sale_items):
                    if sale_date:
                        if isinstance(sale_date, datetime):
                            sale.despatch_date = sale_date.date()
                        else:
                            sale.despatch_date = sale_date
                    else:
                        sale.despatch_date = date.today()

                session.commit()
                return sale, None
            except Exception as e:
                session.rollback()
                logger.error(f"Error creating sale: {e}")
                return None, str(e)

    def create_credit_sale(self, data):
        with get_session() as session:
            try:
                total_amount = sum(
                    item['quantity'] * item['dozen'] * item['unit_price']
                    for item in data['items']
                )
                labour = data.get('labour_expense', 0.0)
                payment_term_total = total_amount + labour
                
                credit_term_days = data.get('credit_term_days')
                due_date = None
                if credit_term_days is not None:
                    sale_date = data.get('sale_date', date.today())
                    due_date = sale_date + timedelta(days=credit_term_days)

                sale = ProfessionalSale(
                    customer_id=data['customer_id'],
                    total_amount=total_amount,
                    labour_expense=labour,
                    is_credit_sale=True,
                    items_data=data['items'],
                    delivery_name=data.get('delivery_name'),
                    delivery_place=data.get('delivery_place'),
                    delivery_phone=data.get('delivery_phone'),
                    delivery_Plate=data.get('delivery_plate'),
                    user_id=data.get('user_id')
                )
                session.add(sale)
                session.flush()

                sale_payment_term_data = {
                    'sale_id': sale.id,
                    'payment_status': PaymentStatusEnum.CREDIT,
                    'total_amount': payment_term_total,
                    'paid_amount': 0.0,
                    'due_date': due_date,
                }
                sale_payment_term = self.sale_payment_term_service.create_with_session(session, sale_payment_term_data)
                session.commit()
                return sale, None
            except Exception as e:
                session.rollback()
                logger.exception("Failed to create credit sale")
                return None, str(e)
    
    @property
    def cash_account_id(self) -> Optional[int]:
        if self._cash_account_id is None:
            try:
                account = self.account_service.get_by_account_number('00000')
                self._cash_account_id = account.id if account else None
                if self._cash_account_id is None:
                    logger.warning("Cash account with number '00000' not found.")
                    self._cash_account_id = -1  # Sentinel to avoid repeated attempts
            except Exception as e:
                logger.error(f"Failed to get cash account ID: {e}")
                self._cash_account_id = -1
        return self._cash_account_id if self._cash_account_id != -1 else None

    def get_daily_sales_summary(self, target_date: date) -> Dict[str, Any]:
        now_local = datetime.now()
        now_utc = datetime.utcnow()
        offset = now_local - now_utc
        start_local = datetime.combine(target_date, time.min)
        end_local = datetime.combine(target_date, time.max)
        start_utc = start_local - offset
        end_utc = end_local - offset

        with get_session() as session:
            # Sales created on this date – used for "sales made" metrics
            sales = (
                session.query(ProfessionalSale)
                .options(
                    joinedload(ProfessionalSale.customer),
                    joinedload(ProfessionalSale.payment_terms)
                    .joinedload(SalePaymentTerm.payment_transactions)
                    .joinedload(PaymentTransaction.bank_account)
                )
                .filter(
                    ProfessionalSale.created_at.between(start_utc, end_utc),
                    ProfessionalSale.is_deleted == False
                )
                .all()
            )

            total_sales_amount = 0.0
            total_invoiced_full = 0.0
            payment_totals = {}
            details = []

            for sale in sales:
                total_sales_amount += sale.total_amount

                full_total = sale.total_amount
                if sale.payment_terms:
                    full_total = sale.payment_terms[0].total_amount
                total_invoiced_full += full_total

                term_has_payment_today = False
                for payment_term in sale.payment_terms:
                    for payment in payment_term.payment_transactions:
                        if payment.payment_date != target_date:
                            continue
                        term_has_payment_today = True
                        account_id = payment.bank_account_id
                        amount = payment.amount
                        payment_totals[account_id] = payment_totals.get(account_id, 0.0) + amount

                        if payment.bank_account:
                            if account_id == self.cash_account_id:
                                payment_type_display = "Cash"
                            else:
                                payment_type_display = f"{payment.bank_account.account_name} - {payment.bank_account.bank_name}"

                        details.append({
                            'sale_id': sale.id,
                            'customer_name': sale.customer.name if sale.customer else "N/A",
                            'total_amount': sale.total_amount,
                            'labour_expense': sale.labour_expense,
                            'full_total': full_total,
                            'payment_type': payment_type_display,
                            'payment_amount': amount,
                            'delivery_name': sale.delivery_name or "",
                            'delivery_place': sale.delivery_place or "",
                            'delivery_phone': sale.delivery_phone or "",
                            'delivery_plate': sale.delivery_Plate or "",
                        })

                    if not term_has_payment_today and payment_term.payment_status in [
                        PaymentStatusEnum.CREDIT.value,
                        PaymentStatusEnum.PARTIAL.value
                    ]:
                        details.append({
                            'sale_id': sale.id,
                            'customer_name': sale.customer.name if sale.customer else "N/A",
                            'total_amount': sale.total_amount,
                            'labour_expense': sale.labour_expense,
                            'full_total': full_total,
                            'payment_type': payment_term.payment_status.capitalize(),
                            'payment_amount': sale.total_amount,
                            'delivery_name': sale.delivery_name or "",
                            'delivery_place': sale.delivery_place or "",
                            'delivery_phone': sale.delivery_phone or "",
                            'delivery_plate': sale.delivery_Plate or "",
                        })

            cash_account_id = self.cash_account_id
            cash_total = payment_totals.get(cash_account_id, 0.0) if cash_account_id else 0.0
            bank_total = sum(amt for acc, amt in payment_totals.items() if acc != cash_account_id)

            # 🔥 Labour expense keyed off despatch_date, not created_at.
            total_labour_expense = session.query(
                func.sum(ProfessionalSale.labour_expense)
            ).filter(
                ProfessionalSale.despatch_date == target_date,
                ProfessionalSale.is_deleted == False
            ).scalar() or 0.0

            return {
                'date': target_date,
                'total_sales_amount': total_sales_amount,
                'total_labour_expense': total_labour_expense,
                'total_invoiced_full': total_invoiced_full,
                'cash_total': cash_total,
                'bank_total': bank_total,
                'payment_totals_by_account': payment_totals,
                'details': details,
            }
    
    def get_sales_with_labour_expense(self, target_date: date) -> List[Dict]:
        now_local = datetime.now()
        now_utc = datetime.utcnow()
        offset = now_local - now_utc

        start_local = datetime.combine(target_date, time.min)
        end_local = datetime.combine(target_date, time.max)

        start_utc = start_local - offset
        end_utc = end_local - offset

        with get_session() as session:
            sales = (
                session.query(ProfessionalSale)
                .options(
                    joinedload(ProfessionalSale.customer),
                    joinedload(ProfessionalSale.payment_terms)
                    .joinedload(SalePaymentTerm.payment_transactions)
                    .joinedload(PaymentTransaction.bank_account)
                )
                .filter(
                    ProfessionalSale.despatch_date == target_date,
                    ProfessionalSale.labour_expense > 0,
                    ProfessionalSale.is_deleted == False
                )
                .all()
            )

            result = []
            for s in sales:
                bank_names = []
                for pt in s.payment_terms:
                    for payment in pt.payment_transactions:
                        if payment.is_deleted:
                            continue
                        if payment.bank_account:
                            name = f"{payment.bank_account.account_name} - {payment.bank_account.bank_name}" if payment.bank_account.bank_name else payment.bank_account.account_name
                            if name not in bank_names:
                                bank_names.append(name)
                paid = 0.0
                for pt in s.payment_terms:
                    for payment in pt.payment_transactions:
                        if not payment.is_deleted:
                            paid += payment.amount   # use the correct field name from PaymentTransaction

                unpaid = s.total_amount - paid
                result.append({
                    'sale_id': s.id,
                    'customer_name': s.customer.name if s.customer else "N/A",
                    'total_amount': s.total_amount,
                    'labour_expense': s.labour_expense,
                    'is_credit_sale': s.is_credit_sale,
                    'delivery_name': s.delivery_name or "",
                    'bank_accounts': bank_names,               # new field
                    'unpaid': unpaid,                          # new field
                    # keep delivery_phone/place/plate if needed elsewhere, but they are no longer in the UI
                })
            return result
    

    def get_despatch_status_sales(self, is_despatched: bool) -> List[ProfessionalSale]:
        with get_session() as session:
            subq = session.query(
                ProfessionalSaleItem.sale_id,
                func.sum(case((ProfessionalSaleItem.for_despatch == False, 1), else_=0)).label('not_despatched_count')
            ).group_by(ProfessionalSaleItem.sale_id, ProfessionalSaleItem.is_deleted == False).subquery()

            query = session.query(ProfessionalSale).outerjoin(
                subq, ProfessionalSale.id == subq.c.sale_id
            ).options(
                joinedload(ProfessionalSale.customer),
                joinedload(ProfessionalSale.items).joinedload(ProfessionalSaleItem.batch).joinedload(ProductBatch.product)
            ).filter(
                ProfessionalSale.is_deleted == False  # <-- ADD THIS FILTER
            )

            if is_despatched:
                query = query.filter(
                    (subq.c.not_despatched_count == 0) | (subq.c.not_despatched_count == None)
                )
            else:
                query = query.filter(subq.c.not_despatched_count > 0)
            
            return query.all()
    
    def count_despatch_status_sales(self, is_despatched: bool) -> int:
        """Count sales by despatch status (used for card values)."""
        from sqlalchemy import func, case

        with get_session() as session:
            subq = session.query(
                ProfessionalSaleItem.sale_id,
                func.sum(case((ProfessionalSaleItem.for_despatch == False, 1), else_=0)).label('not_despatched_count')
            ).group_by(ProfessionalSaleItem.sale_id).subquery()

            query = session.query(ProfessionalSale).outerjoin(
                subq, ProfessionalSale.id == subq.c.sale_id
            ).filter(
            ProfessionalSale.is_deleted == False  # <-- ADD THIS FILTER
        )

            if is_despatched:
                query = query.filter(
                    (subq.c.not_despatched_count == 0) | (subq.c.not_despatched_count == None)
                )
            else:
                query = query.filter(subq.c.not_despatched_count > 0)

            return query.count()
    
    def get_credit_sales_summary(self) -> dict:
        """Return total credit amount, total paid, total unpaid."""
        with get_session() as session:
            row = session.query(
                func.coalesce(func.sum(SalePaymentTerm.total_amount), 0.0).label('total_credit'),
                func.coalesce(func.sum(SalePaymentTerm.paid_amount), 0.0).label('total_paid'),
            ).join(
                ProfessionalSale, ProfessionalSale.id == SalePaymentTerm.sale_id
            ).filter(
                ProfessionalSale.is_deleted == False,
                SalePaymentTerm.is_deleted == False,
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                )
            ).one()
            total_credit = float(row.total_credit or 0.0)
            total_paid = float(row.total_paid or 0.0)
            return {
                'total_credit_amount': total_credit,
                'total_paid': total_paid,
                'total_unpaid': total_credit - total_paid
            }

    def record_credit_payment(self, sale_id: int, amount: float, bank_account_id: int, user_id: int) -> bool:
        """Record a payment against a credit sale (assumes one payment term per sale)."""
        from services.payment_transaction_service import PaymentTransactionService
        with get_session() as session:
            try:
                sale = session.query(ProfessionalSale).get(sale_id)
                if not sale:
                    return False
                # Find the first payment term (simplified – adjust if multiple terms exist)
                payment_term = sale.payment_terms[0] if sale.payment_terms else None
                if not payment_term:
                    return False
                PaymentTransactionService().record_payment(
                    session, payment_term.id, amount, bank_account_id, user_id
                )
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error recording credit payment: {e}")
                return False
    
    def get_sale_with_items(self, sale_id: int) -> Optional[ProfessionalSale]:
        """
        Retrieve a sale by ID with all its items, batches, and products eagerly loaded.
        Returns None if not found or an error occurs.
        """
        with get_session() as session:
            try:
                sale = session.query(ProfessionalSale).options(
                     joinedload(ProfessionalSale.items)
                    .joinedload(ProfessionalSaleItem.batch)
                    .joinedload(ProductBatch.product),
                    joinedload(ProfessionalSale.payment_terms)
                    .joinedload(SalePaymentTerm.payment_transactions)
                    .joinedload(PaymentTransaction.bank_account)
                ).filter(
                    ProfessionalSale.id == sale_id,
                    ProfessionalSale.is_deleted == False
                ).first()
                return sale
            except Exception as e:
                logger.error(f"Error loading sale with items {sale_id}: {e}")
                return None
    
    def delete_sale_cascade(self, sale_id: int, user_id: int = None, send_notification: bool = True) -> bool:
        with get_session() as session:
            try:
                sale = session.query(ProfessionalSale).options(
                    joinedload(ProfessionalSale.items),
                    joinedload(ProfessionalSale.payment_terms)
                    .joinedload(SalePaymentTerm.payment_transactions)
                ).filter(
                    ProfessionalSale.id == sale_id,
                    ProfessionalSale.is_deleted == False
                ).first()
                if not sale:
                    logger.warning(f"Sale {sale_id} not found or already deleted")
                    return False
                
                sale_data = self._capture_sale_data_for_notification(sale)
                
                for item in sale.items:
                    # Restore batch available quantity
                    batch = session.query(ProductBatch).get(item.batch_id)
                    if batch:
                        batch.available_quantity += item.quantity

                    # Soft delete sale item
                    item.is_deleted = True

                    batch_transactions = session.query(BatchTransaction).filter(
                        BatchTransaction.batch_id == item.batch_id,
                        BatchTransaction.transaction_type == TransactionType.SALE,
                        BatchTransaction.reference_number == str(sale_id),
                        BatchTransaction.is_deleted == False
                    ).all()
                    for bt in batch_transactions:
                        bt.is_deleted = True
                
                for term in sale.payment_terms:
                    for payment in term.payment_transactions:
                        payment.is_deleted = True

                        # Soft delete associated bank transactions
                        bank_txs = session.query(BankTransaction).filter(
                            BankTransaction.sale_payment_term_id == term.id,
                            BankTransaction.is_deleted == False
                        ).all()
                        account_ids = set()
                        for bt in bank_txs:
                            bt.is_deleted = True
                            account_ids.add(bt.bank_account_id)

                        # Recalculate balance chain for each affected account
                        for acc_id in account_ids:
                            self.bank_transaction_service.recalculate_balances_for_account(session, acc_id)
                    
                    term.is_deleted = True
                
                sale.is_deleted = True

                product_ids = set()
                for item in sale.items:
                    if item.batch and item.batch.product_id:
                        product_ids.add(item.batch.product_id)
                for pid in product_ids:
                    product = session.query(ProfessionalProduct).get(pid)
                    if product:
                        product.update_totals()
                
                session.commit()
                logger.info(f"Successfully deleted sale {sale_id} with cascade")
                
                self._refresh_json_cache_from_db()
                if send_notification:
                    self._send_cancellation_notification(sale_data)
                
                return True

            except Exception as e:
                session.rollback()
                logger.exception(f"Error deleting sale cascade {sale_id}")
                return False

    
    def _capture_sale_data_for_notification(self, sale: ProfessionalSale) -> dict:
        """Capture sale details before deletion for notification purposes."""
        from ui.components.ethiopian_date import EthiopianDateConverter
        
        items = []
        for item in sale.items:
            product_name = item.batch.product.name if item.batch and item.batch.product else "Unknown"
            items.append({
                'product_name': product_name,
                'dozen': item.dozen,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'total': item.total,
            })
        
        return {
            'sale_id': sale.id,
            'delivery_name': sale.delivery_name or "",
            'items': items,
        }

    def _send_cancellation_notification(self, sale_data: dict):
        """Send Telegram notification about a canceled/returned sale (bilingual)."""
        try:
            from telegrambot.bot import notify_store_team_sync
            
            # Build items text
            items_text_en = ""
            items_text_am = ""
            for item in sale_data['items']:
                pn = item['product_name']
                qty = item['quantity']
                items_text_en += f"  • {pn}: quantity: {qty} pcs\n"
                items_text_am += f"  • {pn}: ብዛት፡ {qty}\n"
            
            delivery_name = sale_data['delivery_name']
            
            # Build bilingual message
            # message = (
                # f"❌ <b>Sale Canceled / Returned</b> ❌\n\n"
                # f"<b>Sale ID:</b> #{sale_data['sale_id']}\n"
            # )
            # if delivery_name:
                # message += f"<b>Delivery:</b> {delivery_name}\n"
            # if items_text_en:
                # message += f"\n<b>Items:</b>\n{items_text_en}"
            
            message = (
                f"\n══════════════════════\n\n"
                f"❌ <b>ሽያጭ ተሰርዟል / ተመልሷል</b> ❌\n\n"
                f"<b>የሽያጭ ቁጥር:</b> #{sale_data['sale_id']}\n"
            )
            if delivery_name:
                message += f"<b>አድራሻ:</b> {delivery_name}\n"
            if items_text_am:
                message += f"\n<b>እቃዎች:</b>\n{items_text_am}"
            
            notify_store_team_sync(
                message,
                sale_id=sale_data['sale_id'],
                notification_type='sale_cancellation'
            )
            logger.info(f"Cancellation notification sent for sale #{sale_data['sale_id']}")
            
        except Exception as e:
            logger.error(f"Failed to send cancellation notification for sale #{sale_data.get('sale_id')}: {e}", exc_info=True)

    def get_credit_sales_list(self) -> list:
        """Return list of credit sales with details for table, newest first."""
        with get_session() as session:
            from models.sale_payment_term import SalePaymentTerm, PaymentStatusEnum
            from sqlalchemy.orm import joinedload
            from sqlalchemy import or_

            sales = session.query(ProfessionalSale).options(
                joinedload(ProfessionalSale.customer),
                joinedload(ProfessionalSale.payment_terms)
            ).filter(
                ProfessionalSale.is_deleted == False,
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    ProfessionalSale.payment_terms.any(
                        SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                    )
                )
            ).order_by(ProfessionalSale.created_at.desc()).all()

            result = []
            for sale in sales:
                # Find the first relevant payment term (CREDIT or PARTIAL)
                term = None
                for pt in sale.payment_terms:
                    if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                        term = pt
                        break
                if not term and sale.payment_terms:
                    term = sale.payment_terms[0]  # fallback (should not happen)
                if not term:
                    continue

                total = term.total_amount
                paid = term.paid_amount
                remaining = total - paid
                status_display = term.payment_status.value.capitalize()

                result.append({
                    'sale_id': sale.id,
                    'customer_name': sale.customer.name if sale.customer else "N/A",
                    'total_amount': total,
                    'paid_amount': paid,
                    'remaining': remaining,
                    'status': status_display,
                    'payment_terms': sale.payment_terms,
                    'payment_term_id': term.id,
                    'created_at': sale.created_at
                })
            return result
    
    def record_payment_by_term(self, payment_term_id: int, amount: float, bank_account_id: int, user_id: int) -> bool:
        """Record a payment against a specific payment term."""
        with get_session() as session:
            try:
                from models.sale_payment_term import SalePaymentTerm
                from services.payment_transaction_service import PaymentTransactionService

                term = session.query(SalePaymentTerm).get(payment_term_id)
                if not term:
                    return False

                PaymentTransactionService().record_payment(
                    session, term.id, amount, bank_account_id, user_id
                )
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error recording payment by term: {e}")
                return False
    
    def find_duplicate_sale(
        self,
        customer_id: int,
        items: List[Dict],
        labour_expense: float,
        delivery_name: Optional[str],
        hours: int = 24
    ):
        with get_session() as session:
            cutoff = datetime.utcnow() - timedelta(hours=hours)

            input_items = {
                (item['batch_id'], item['quantity'], item['dozen'], item['unit_price'])
                for item in items
            }

            candidate_sales = (
                session.query(ProfessionalSale)
                .filter(
                    ProfessionalSale.customer_id == customer_id,
                    ProfessionalSale.created_at >= cutoff,
                    ProfessionalSale.is_deleted == False
                )
                .options(joinedload(ProfessionalSale.items))
                .all()
            )
            
            for sale in candidate_sales:
                if sale.labour_expense != labour_expense:
                    continue
                if sale.delivery_name != delivery_name:
                    continue
                
                sale_items = set()
                for si in sale.items:
                    sale_items.add((si.batch_id, si.quantity, si.dozen, si.unit_price))
                
                if sale_items == input_items:
                    return sale
        
        return None
    
    def get_credit_sales_by_customer(self, outstanding_only: bool = False) -> list:
        """
        Return customers with aggregate credit sales data.
        When outstanding_only=True, only customers with a remaining balance are returned
        (used by combined credit overview for faster loading).
        """
        from datetime import date as date_cls

        with get_session() as session:
            query = session.query(
                ProfessionalSale.customer_id,
                Customer.name.label('customer_name'),
                Customer.phone.label('customer_phone'),
                func.sum(SalePaymentTerm.total_amount).label('total_amount'),
                func.sum(SalePaymentTerm.paid_amount).label('paid_amount'),
                func.sum(SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount).label('remaining'),
                func.min(SalePaymentTerm.due_date).label('earliest_due_date'),
                func.max(
                    case(
                        (
                            and_(
                                SalePaymentTerm.due_date == func.date(ProfessionalSale.created_at),
                                SalePaymentTerm.due_date == date_cls.today(),
                                (SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount) > 0
                            ),
                            1
                        ),
                        else_=0
                    )
                ).label('has_short_term'),
            ).join(
                SalePaymentTerm, ProfessionalSale.id == SalePaymentTerm.sale_id
            ).join(
                Customer, ProfessionalSale.customer_id == Customer.id
            ).filter(
                ProfessionalSale.is_deleted == False,
                SalePaymentTerm.is_deleted == False,
                Customer.is_deleted == False,
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                )
            ).group_by(
                ProfessionalSale.customer_id,
                Customer.name,
                Customer.phone,
            )

            if outstanding_only:
                query = query.having(
                    func.sum(SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount) > 0
                )

            rows = query.all()
            if not rows:
                return []

            customer_ids = [row.customer_id for row in rows]
            sale_id_rows = session.query(
                ProfessionalSale.customer_id,
                ProfessionalSale.id,
            ).join(
                SalePaymentTerm, ProfessionalSale.id == SalePaymentTerm.sale_id
            ).filter(
                ProfessionalSale.is_deleted == False,
                SalePaymentTerm.is_deleted == False,
                ProfessionalSale.customer_id.in_(customer_ids),
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                ),
            ).distinct().all()

            sale_ids_by_customer: Dict[int, List[int]] = {}
            for cust_id, sale_id in sale_id_rows:
                sale_ids_by_customer.setdefault(cust_id, []).append(sale_id)

            result = []
            for row in rows:
                remaining = float(row.remaining or 0.0)
                paid = float(row.paid_amount or 0.0)
                if remaining == 0:
                    status = 'Paid'
                elif paid > 0:
                    status = 'Partial'
                else:
                    status = 'Unpaid'

                result.append({
                    'customer_id': row.customer_id,
                    'customer_name': row.customer_name,
                    'customer_phone': row.customer_phone or "",
                    'total_amount': float(row.total_amount or 0.0),
                    'paid_amount': paid,
                    'remaining': remaining,
                    'status': status,
                    'sale_ids': sale_ids_by_customer.get(row.customer_id, []),
                    'payment_term_ids': [],
                    'earliest_due_date': row.earliest_due_date,
                    'has_short_term': bool(row.has_short_term),
                })

            result.sort(key=lambda x: x['customer_name'])
            return result
    
    def record_customer_payment(
        self,
        customer_id: int,
        payments: List[Tuple[float, int]],
        user_id: int,
        note: Optional[str] = None,
        payment_date: Optional[date] = None
    ) -> bool:
        if payment_date is None:
            payment_date = date.today()
        elif isinstance(payment_date, str):
            from datetime import datetime as dt
            payment_date = dt.strptime(payment_date, "%Y-%m-%d").date()

        with get_session() as session:
            try:
                sales = session.query(ProfessionalSale).options(
                    joinedload(ProfessionalSale.payment_terms)
                ).filter(
                    ProfessionalSale.customer_id == customer_id,
                    ProfessionalSale.is_deleted == False,
                    or_(
                        ProfessionalSale.is_credit_sale == True,
                        ProfessionalSale.payment_terms.any(
                            SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                        )
                    )
                ).all()

                if not sales:
                    logger.info(f"No outstanding credit sales for customer {customer_id}")
                    return False

                def sale_sort_key(sale):
                    has_short_term = False
                    for term in sale.payment_terms:
                        if term.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                            if term.due_date and term.due_date == sale.created_at.date():
                                if term.total_amount - term.paid_amount > 0:
                                    has_short_term = True
                                    break
                    return (0 if has_short_term else 1, sale.created_at)

                sales.sort(key=sale_sort_key)

                payment_made = False
                for amount, bank_account_id in payments:
                    if amount <= 0:
                        continue
                    remaining_split = amount
                    for sale in sales:
                        if remaining_split <= 0:
                            break
                        term = None
                        for pt in sale.payment_terms:
                            if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                                term = pt
                                break
                        if not term and sale.payment_terms:
                            term = sale.payment_terms[0]
                        if not term:
                            continue
                        balance = term.total_amount - term.paid_amount
                        if balance <= 0:
                            continue
                        payment_for_this = min(remaining_split, balance)
                        # Pass the payment_date to the lower layer
                        PaymentTransactionService().record_payment(
                            session,
                            term.id,
                            payment_for_this,
                            bank_account_id,
                            user_id,
                            note,
                            payment_date
                        )
                        payment_made = True
                        remaining_split -= payment_for_this
                        session.refresh(term)
                session.commit()
                return payment_made
            except Exception as e:
                session.rollback()
                logger.error(f"Error recording customer payment: {e}")
                return False
    
    def get_credit_sales_by_ids(self, sale_ids: List[int]) -> list:
        """
        Returns detailed credit sales for the given list of sale IDs.
        Used by the per‑customer list dialog.
        """
        with get_session() as session:
            sales = session.query(ProfessionalSale).options(
                joinedload(ProfessionalSale.customer),
                joinedload(ProfessionalSale.payment_terms)
            ).filter(
                ProfessionalSale.id.in_(sale_ids),
                ProfessionalSale.is_deleted == False,
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    ProfessionalSale.payment_terms.any(
                        SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                    )
                )
            ).order_by(ProfessionalSale.created_at.desc()).all()

            result = []
            for sale in sales:
                term = next(
                    (pt for pt in sale.payment_terms if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]),
                    None
                )
                if not term and sale.payment_terms:
                    term = sale.payment_terms[0]
                if not term:
                    continue

                result.append({
                    'sale_id': sale.id,
                    'labour_expense': sale.labour_expense,
                    'sale_date': sale.created_at,
                    'total_amount': term.total_amount,
                    'paid_amount': term.paid_amount,
                    'remaining': term.total_amount - term.paid_amount,
                    'status': term.payment_status.value.capitalize(),
                    'payment_term_id': term.id,
                })
            return result
    
    def get_customer_payment_history(self, customer_id: int) -> List[Dict]:
        with get_session() as session:
            from models.payment_transaction import PaymentTransaction
            from models.sale_payment_term import SalePaymentTerm, PaymentStatusEnum
            from sqlalchemy.orm import joinedload
            from sqlalchemy import or_

            payments = session.query(PaymentTransaction).join(
                SalePaymentTerm, PaymentTransaction.sale_payment_term_id == SalePaymentTerm.id
            ).join(
                ProfessionalSale, SalePaymentTerm.sale_id == ProfessionalSale.id
            ).options(
                joinedload(PaymentTransaction.bank_account)
            ).filter(
                ProfessionalSale.customer_id == customer_id,
                ProfessionalSale.is_deleted == False,
                PaymentTransaction.is_deleted == False,
                # Only payments linked to credit sales
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    SalePaymentTerm.payment_status.in_(
                        [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]
                    )
                )
            ).order_by(PaymentTransaction.payment_date.desc(), PaymentTransaction.id.desc()).all()

            result = []
            for pt in payments:
                result.append({
                    'transaction_id': pt.id,
                    'payment_term_id': pt.sale_payment_term_id,
                    'sale_id': pt.payment_term.sale_id,
                    'payment_date': pt.payment_date,
                    'amount': pt.amount,
                    'bank_account_id': pt.bank_account_id,
                    'bank_account_name': pt.bank_account.account_name if pt.bank_account else 'N/A',
                    'bank_name': pt.bank_account.bank_name if pt.bank_account else '',
                    'payment_method': pt.payment_method.value if pt.payment_method else 'transfer',
                    'notes': pt.notes or '',
                })
            return result


    def delete_payment_transaction(self, transaction_id: int, user_id: int = None) -> bool:
        """Delete a payment transaction, update the associated payment term and bank transaction."""
        with get_session() as session:
            try:
                payment = session.query(PaymentTransaction).filter(
                    PaymentTransaction.id == transaction_id,
                    PaymentTransaction.is_deleted == False
                ).first()
                if not payment:
                    logger.warning(f"Payment transaction {transaction_id} not found")
                    return False

                term = payment.payment_term
                if not term:
                    logger.warning(f"Payment term for transaction {transaction_id} not found")
                    return False

                amount = payment.amount
                bank_account_id = payment.bank_account_id

                # Soft delete payment transaction
                payment.is_deleted = True
                if user_id:
                    payment.last_modified_by = user_id

                # Soft delete associated bank transaction and recalculate
                bank_tx = session.query(BankTransaction).filter(
                    BankTransaction.sale_payment_term_id == term.id,
                    BankTransaction.amount == amount,
                    BankTransaction.bank_account_id == bank_account_id,
                    BankTransaction.is_deleted == False
                ).first()
                if bank_tx:
                    bank_tx.is_deleted = True
                    if user_id:
                        bank_tx.last_modified_by = user_id
                    # Recalculate balance for this account
                    self.bank_transaction_service.recalculate_balances_for_account(session, bank_account_id)

                # Update payment term
                term.paid_amount -= amount
                term.update_status()

                session.commit()
                logger.info(f"Deleted payment transaction {transaction_id}, updated term {term.id}")
                return True

            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting payment transaction {transaction_id}: {e}", exc_info=True)
                return False
    

    def get_all_sales_count(self) -> int:
        """Return total number of non-deleted sales (for card value)."""
        with get_session() as session:
            return session.query(ProfessionalSale) \
                .filter(ProfessionalSale.is_deleted == False) \
                .count()

    def _fuzzy_pattern(self, term: str) -> str:
        """Convert 'abc' into '%a%b%c%' for subsequence matching."""
        return '%' + '%'.join(term.strip()) + '%'

    # ---- Typo-tolerant fuzzy search ----
    # Registered as a SQLite scalar function (FUZZY_MATCH) so it can be used
    # directly inside WHERE clauses without pulling rows into Python first.
    # Only invoked as a fallback when the fast, indexed exact/substring
    # search returns zero results, so it doesn't slow down normal searches.
    _fuzzy_registered_engines = set()

    @staticmethod
    def _fuzzy_token_score(query_token: str, text_token: str, threshold: float = 0.6) -> float:
        """How well one query word matches one text word, from 0 to 1."""
        if query_token == text_token:
            return 1.0
        if query_token in text_token or text_token in query_token:
            shorter = min(len(query_token), len(text_token))
            longer = max(len(query_token), len(text_token))
            return 0.9 * (shorter / longer)
        if len(query_token) >= 3 and len(text_token) >= 3:
            ratio = difflib.SequenceMatcher(None, query_token, text_token).ratio()
            return ratio if ratio >= threshold else 0.0
        return 0.0

    @classmethod
    def _field_relevance(cls, text_val, query_val) -> Tuple[bool, float]:
        """Check one field (e.g. a product name) against the full search
        text. Returns (matched, score) where matched requires every word
        in query_val to match somewhere in text_val, and score (0-1)
        reflects how close the overall match is — used to rank results."""
        if not text_val or not query_val:
            return False, 0.0
        text_tokens = str(text_val).lower().split()
        query_tokens = str(query_val).lower().split()
        token_scores = []
        for qt in query_tokens:
            best = max(
                (cls._fuzzy_token_score(qt, tt) for tt in text_tokens),
                default=0.0,
            )
            if best <= 0.0:
                return False, 0.0
            token_scores.append(best)
        return True, sum(token_scores) / len(token_scores)

    @classmethod
    def _fuzzy_match_score(cls, text_val, query_val) -> int:
        """SQLite scalar function wrapper: 1/0 for use in WHERE clauses."""
        matched, _ = cls._field_relevance(text_val, query_val)
        return 1 if matched else 0

    def _ensure_fuzzy_function(self, session):
        """Make sure FUZZY_MATCH() is available on this session's SQLite
        connection (and any future connections from the same engine)."""
        engine = session.get_bind()
        if engine not in self._fuzzy_registered_engines:
            @event.listens_for(engine, "connect")
            def _register_fuzzy(dbapi_connection, connection_record):
                dbapi_connection.create_function(
                    "FUZZY_MATCH", 2, self._fuzzy_match_score
                )
            self._fuzzy_registered_engines.add(engine)
        # The event above only fires for *new* connections; register on the
        # current, already-open connection too so it works immediately.
        try:
            session.connection().connection.create_function(
                "FUZZY_MATCH", 2, self._fuzzy_match_score
            )
        except Exception:
            pass

    def _sale_relevance(self, sale, stmt: str) -> float:
        """Best relevance score (0-1) for a sale against the search text,
        across its customer, item product names, and delivery name. An
        exact numeric ID match always ranks highest."""
        if stmt.isdigit() and sale.id == int(stmt):
            return 1.0

        best = 0.0
        if sale.customer and sale.customer.name:
            matched, score = self._field_relevance(sale.customer.name, stmt)
            if matched:
                best = max(best, score)

        for item in sale.items:
            batch = getattr(item, "batch", None)
            product = getattr(batch, "product", None) if batch else None
            if product and product.name:
                matched, score = self._field_relevance(product.name, stmt)
                if matched:
                    best = max(best, score)

        if sale.delivery_name:
            matched, score = self._field_relevance(sale.delivery_name, stmt)
            if matched:
                best = max(best, score)

        return best

    def get_all_sales_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        filter_date: Optional[date] = None,
        fuzzy: bool = False
    ) -> Tuple[List[ProfessionalSale], int]:
        """Return a page of sales and total count. Safe against invalid filter_date."""
        try:
            with get_session() as session:
                filter_query = session.query(ProfessionalSale) \
                    .filter(ProfessionalSale.is_deleted == False)

                if filter_date and isinstance(filter_date, date):
                    start_dt = datetime.combine(filter_date, time.min)
                    end_dt = datetime.combine(filter_date, time.max)
                    filter_query = filter_query.filter(
                        ProfessionalSale.created_at.between(start_dt, end_dt)
                    )
                elif filter_date:
                    logger.warning(f"Invalid filter_date type: {type(filter_date)}")

                if search:
                    stmt = search.strip()
                    conditions = []
                    if stmt.isdigit():
                        conditions.append(ProfessionalSale.id == int(stmt))

                    if fuzzy:
                        # Typo-tolerant match (e.g. "garum" finds "gerum").
                        # Only reached as a fallback after an exact search
                        # returns nothing, so the extra cost is acceptable.
                        self._ensure_fuzzy_function(session)
                        conditions.append(
                            ProfessionalSale.customer.has(
                                func.FUZZY_MATCH(Customer.name, stmt) == 1
                            )
                        )
                        conditions.append(
                            ProfessionalSale.items.any(
                                ProfessionalSaleItem.batch.has(
                                    ProductBatch.product.has(
                                        func.FUZZY_MATCH(ProfessionalProduct.name, stmt) == 1
                                    )
                                )
                            )
                        )
                        conditions.append(
                            func.FUZZY_MATCH(ProfessionalSale.delivery_name, stmt) == 1
                        )

                        filter_query = filter_query.filter(or_(*conditions))

                        # Fuzzy matches vary in quality, so rank by
                        # relevance instead of just recency. This means
                        # pulling every match (not just one page) to score
                        # and sort in Python, then slicing the page out —
                        # acceptable since this path only runs on the rare
                        # fallback search, not on every keystroke.
                        matches = filter_query.options(
                            joinedload(ProfessionalSale.customer),
                            joinedload(ProfessionalSale.payment_terms),
                            joinedload(ProfessionalSale.items)
                                .joinedload(ProfessionalSaleItem.batch)
                                .joinedload(ProductBatch.product),
                        ).distinct().all()

                        scored = [
                            (self._sale_relevance(sale, stmt), sale.id, sale)
                            for sale in matches
                        ]
                        scored.sort(key=lambda t: (-t[0], -t[1]))

                        total = len(scored)
                        start = (page - 1) * page_size
                        page_sales = [
                            s for _, _, s in scored[start:start + page_size]
                        ]
                        return page_sales, total

                    else:
                        # Fast, indexed exact/substring search (default path).
                        pattern = f"%{stmt}%"
                        conditions.append(
                            ProfessionalSale.customer.has(Customer.name.ilike(pattern))
                        )
                        conditions.append(
                            ProfessionalSale.items.any(
                                ProfessionalSaleItem.batch.has(
                                    ProductBatch.product.has(ProfessionalProduct.name.ilike(pattern))
                                )
                            )
                        )
                        conditions.append(
                            ProfessionalSale.delivery_name.ilike(pattern)
                        )

                    filter_query = filter_query.filter(or_(*conditions))

                ordered_ids_query = filter_query.with_entities(
                    ProfessionalSale.id
                ).distinct().order_by(ProfessionalSale.id.desc())

                total = ordered_ids_query.count()

                paginated_ids = ordered_ids_query.offset((page - 1) * page_size) \
                    .limit(page_size) \
                    .all()

                sale_ids = [row[0] for row in paginated_ids]

                if not sale_ids:
                    return [], 0

                sales = session.query(ProfessionalSale) \
                    .options(
                        joinedload(ProfessionalSale.customer),
                        joinedload(ProfessionalSale.payment_terms)
                    ) \
                    .filter(ProfessionalSale.id.in_(sale_ids)) \
                    .all()

                id_to_sale = {sale.id: sale for sale in sales}
                ordered_sales = [id_to_sale[sid] for sid in sale_ids if sid in id_to_sale]

                return ordered_sales, total
        except Exception as e:
            logger.error(f"Error in get_all_sales_paginated: {e}", exc_info=True)
            return [], 0

    def get_payments_by_sale(self, sale_id: int) -> List[Dict]:
        """Return all payment transactions for a given sale."""
        with get_session() as session:
            payments = session.query(PaymentTransaction) \
                .join(SalePaymentTerm, PaymentTransaction.sale_payment_term_id == SalePaymentTerm.id) \
                .filter(SalePaymentTerm.sale_id == sale_id,
                        PaymentTransaction.is_deleted == False) \
                .options(joinedload(PaymentTransaction.bank_account)) \
                .order_by(PaymentTransaction.payment_date.desc()) \
                .all()
            result = []
            for pt in payments:
                result.append({
                    'transaction_id': pt.id,
                    'payment_term_id': pt.sale_payment_term_id,
                    'payment_date': pt.payment_date,
                    'amount': pt.amount,
                    'bank_account_id': pt.bank_account_id,
                    'bank_account_name': pt.bank_account.account_name if pt.bank_account else 'N/A',
                    'bank_name': pt.bank_account.bank_name if pt.bank_account else '',
                })
            return result
    
    def get_delivery_names_with_frequency(self, search_text: str = "", limit: int = 50) -> List[str]:
        """
        Get unique delivery names ordered by frequency of use.
        Most frequently used names appear first.
        """
        with get_session() as session:
            query = session.query(
                ProfessionalSale.delivery_name,
                func.count(ProfessionalSale.id).label('frequency')
            ).filter(
                ProfessionalSale.delivery_name.isnot(None),
                ProfessionalSale.delivery_name != '',
                ProfessionalSale.is_deleted == False
            )
            
            if search_text:
                query = query.filter(ProfessionalSale.delivery_name.ilike(f"%{search_text}%"))
            
            results = query.group_by(ProfessionalSale.delivery_name) \
                .order_by(func.count(ProfessionalSale.id).desc()) \
                .limit(limit) \
                .all()
            
            return [r[0] for r in results if r[0]]
    
    def get_total_selling_price_for_period(self, start_date: date, end_date: date) -> float:
        """Sum of (quantity * dozen * unit_price) from sale items."""
        # from models.new_sale_item import ProfessionalSaleItem
        # from models.new_sales import ProfessionalSale
        # from sqlalchemy import func
        # from datetime import datetime, time
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)
        with get_session() as session:
            total = session.query(
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProfessionalSaleItem.unit_price)
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at.between(start_dt, end_dt),
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False
            ).scalar()
            return float(total) if total else 0.0

    def get_total_cost_price_for_period(self, start_date: date, end_date: date) -> float:
        """Sum of (quantity * dozen * batch.cost_price) from sale items."""
        # from models.new_sale_item import ProfessionalSaleItem
        # from models.product_batch import ProductBatch
        # from models.new_sales import ProfessionalSale
        # from sqlalchemy import func
        # from datetime import datetime, time
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)
        with get_session() as session:
            total = session.query(
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProductBatch.cost_price)
            ).select_from(ProfessionalSaleItem).join(
                ProductBatch, ProfessionalSaleItem.batch_id == ProductBatch.id
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at.between(start_dt, end_dt),
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False,
                ProductBatch.is_deleted == False
            ).scalar()
            return float(total) if total else 0.0
    
    def get_product_profit_breakdown(self, start_date: date, end_date: date) -> List[Dict]:

        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)
        with get_session() as session:
            results = session.query(
                ProfessionalProduct.id.label('product_id'),
                ProfessionalProduct.name.label('product_name'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen).label('total_qty'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProductBatch.cost_price).label('total_cost'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProfessionalSaleItem.unit_price).label('total_selling')
            ).join(
                ProductBatch, ProfessionalSaleItem.batch_id == ProductBatch.id
            ).join(
                ProfessionalProduct, ProductBatch.product_id == ProfessionalProduct.id
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at.between(start_dt, end_dt),
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False,
                ProductBatch.is_deleted == False,
                ProfessionalProduct.is_deleted == False
            ).group_by(
                ProfessionalProduct.id, ProfessionalProduct.name
            ).all()

            data = []
            total_profit = 0.0
            for row in results:
                profit = row.total_selling - row.total_cost
                total_profit += profit
                data.append({
                    'product_name': row.product_name,
                    'quantity': int(row.total_qty),
                    'total_cost': float(row.total_cost),
                    'total_selling': float(row.total_selling),
                    'profit': profit,
                })

            # Second pass to compute ROI, margin, and contribution %
            for item in data:
                profit = item['profit']
                total_cost = item['total_cost']
                total_selling = item['total_selling']
                item['roi'] = (profit / total_cost * 100) if total_cost > 0 else 0.0
                item['margin'] = (profit / total_selling * 100) if total_selling > 0 else 0.0
                item['contribution'] = (profit / total_profit * 100) if total_profit > 0 else 0.0

            data.sort(key=lambda x: x['profit'], reverse=True)
            return data
    
    def get_total_quantity_for_period(self, start_date: date, end_date: date) -> int:
        """Return total quantity (units) sold in the date range."""
        # from models.new_sale_item import ProfessionalSaleItem
        # from models.new_sales import ProfessionalSale
        # from sqlalchemy import func
        # from datetime import datetime, time

        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        with get_session() as session:
            total = session.query(
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen)
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at.between(start_dt, end_dt),
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False
            ).scalar()
            return int(total) if total else 0
    
    def get_customer_combined_history(self, customer_id: int) -> List[Dict]:
        """
        Returns a combined list of credit sales and payments for a customer,
        sorted by date, with running balance computed.
        Each entry contains: date, amount (positive for sales, negative for payments),
        type, notes, and display info for the 'Bank Account' column.
        """
        with get_session() as session:
            # 1. Credit sales (increase balance)
            sales = session.query(ProfessionalSale).options(
                joinedload(ProfessionalSale.payment_terms)
            ).filter(
                ProfessionalSale.customer_id == customer_id,
                ProfessionalSale.is_deleted == False,
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    ProfessionalSale.payment_terms.any(
                        SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                    )
                )
            ).all()

            combined = []

            for sale in sales:
                # Find the relevant payment term (CREDIT or PARTIAL)
                term = None
                for pt in sale.payment_terms:
                    if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                        term = pt
                        break
                if not term and sale.payment_terms:
                    term = sale.payment_terms[0]  # fallback
                if not term:
                    continue

                date_obj = sale.created_at.date() if sale.created_at else date.today()
                combined.append({
                    'date': date_obj,
                    'amount': term.total_amount,          # positive = increases balance
                    'type': 'credit_sale',
                    'notes': f"Credit sale #{sale.id}",
                    'sale_id': sale.id,
                    'transaction_id': None,
                    'bank_account_display': 'New Credit',
                    'bank_account_id': None,
                })

            # 2. Payments (decrease balance) – grouped by (payment_date, bank_account_id)
            raw_payments = self.get_customer_payment_history(customer_id)
            payment_groups = {}
            for p in raw_payments:
                key = (p['payment_date'], p['bank_account_id'])
                if key not in payment_groups:
                    payment_groups[key] = {
                        'date': p['payment_date'],
                        'amount': 0.0,
                        'notes': [],
                        'transaction_ids': [],
                        'bank_account_display': f"{p['bank_name']} - {p['bank_account_name']}" if p['bank_name'] else p['bank_account_name'],
                        'bank_account_id': p['bank_account_id'],
                    }
                payment_groups[key]['amount'] += p['amount']
                if p.get('notes'):
                    payment_groups[key]['notes'].append(p['notes'])
                payment_groups[key]['transaction_ids'].append(p['transaction_id'])

            for group in payment_groups.values():
                combined.append({
                    'date': group['date'],
                    'amount': -group['amount'],            # negative = decreases balance
                    'type': 'payment',
                    'notes': '; '.join(filter(None, group['notes'])) if group['notes'] else '',
                    'sale_id': None,
                    'transaction_id': group['transaction_ids'][0],  # just for reference
                    'bank_account_display': group['bank_account_display'],
                    'bank_account_id': group['bank_account_id'],
                    'all_transaction_ids': group['transaction_ids'],  # store all for deletion
                })

            # 3. Sort by date (ascending) to compute running balance
            combined.sort(key=lambda x: x['date'])

            # 4. Compute running balance and add 'balance_before'
            balance = 0.0
            for tx in combined:
                tx['balance_before'] = balance
                balance += tx['amount']
                tx['balance_after'] = balance

            return combined
    
    def count_unpaid_same_day_credits(self) -> int:
        today = date.today()
        with get_session() as session:
            count = session.query(
                func.count(func.distinct(ProfessionalSale.customer_id))
            ).join(
                SalePaymentTerm, ProfessionalSale.id == SalePaymentTerm.sale_id
            ).filter(
                ProfessionalSale.is_deleted == False,
                SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]),
                SalePaymentTerm.due_date == func.date(ProfessionalSale.created_at),
                SalePaymentTerm.due_date == today,          # Changed from <= to ==
                SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount > 0
            ).scalar()

            return count or 0
    
    def get_customer_credit_sales_grouped(self, customer_id: int) -> List[Dict]:
        with get_session() as session:
            # Load all credit sales for this customer with items, batches, products
            sales = session.query(ProfessionalSale).options(
                joinedload(ProfessionalSale.payment_terms),
                joinedload(ProfessionalSale.items)
                .joinedload(ProfessionalSaleItem.batch)
                .joinedload(ProductBatch.product)
            ).filter(
                ProfessionalSale.customer_id == customer_id,
                ProfessionalSale.is_deleted == False,
                ProfessionalSale.is_credit_sale == True
            ).order_by(ProfessionalSale.created_at.desc()).all()

            # Group by date (YYYY-MM-DD)
            groups = {}
            for sale in sales:
                # Find relevant payment term
                term = None
                for pt in sale.payment_terms:
                    if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                        term = pt
                        break
                if not term and sale.payment_terms:
                    term = sale.payment_terms[0]
                if not term:
                    continue

                date_key = sale.created_at.date() if sale.created_at else None
                if date_key not in groups:
                    groups[date_key] = {
                        'sale_date': date_key,
                        'total_amount': 0.0,
                        'paid_amount': 0.0,
                        'remaining': 0.0,
                        'sale_ids': [],
                        'items': [],
                    }
                groups[date_key]['total_amount'] += term.total_amount
                groups[date_key]['paid_amount'] += term.paid_amount
                groups[date_key]['remaining'] += (term.total_amount - term.paid_amount)
                groups[date_key]['sale_ids'].append(sale.id)

                # Collect items from this sale
                for item in sale.items:
                    if item.is_deleted:
                        continue
                    product_name = item.batch.product.name if item.batch and item.batch.product else "Unknown"
                    groups[date_key]['items'].append({
                        'product_name': product_name,
                        'quantity': item.quantity,
                        'dozen': item.dozen,
                        'unit_price': item.unit_price,
                        'total': item.total,
                        'for_despatch': item.for_despatch,
                    })

            # Convert to list, compute status, sort newest first
            result = []
            for date_key, group in groups.items():
                if group['remaining'] <= 0:
                    status = 'Paid'
                elif group['paid_amount'] > 0:
                    status = 'Partial'
                else:
                    status = 'Unpaid'
                result.append({
                    'sale_date': date_key,
                    'total_amount': group['total_amount'],
                    'paid_amount': group['paid_amount'],
                    'remaining': group['remaining'],
                    'status': status,
                    'sale_ids': group['sale_ids'],
                    'items': group['items'],
                })
            result.sort(key=lambda x: x['sale_date'] or date.min, reverse=True)
            return result
    
    def get_daily_credit_activity(self, customer_id: int, activity_date: date) -> dict:
        """Return credit sales and payments for a customer on a given date."""
        with get_session() as session:
            # Credit sales on that date
            sales = session.query(ProfessionalSale).options(
                joinedload(ProfessionalSale.payment_terms)
            ).filter(
                ProfessionalSale.customer_id == customer_id,
                ProfessionalSale.is_credit_sale == True,
                func.date(ProfessionalSale.created_at) == activity_date,
                ProfessionalSale.is_deleted == False
            ).all()

            # Payments on that date – only from credit sales
            payments = session.query(PaymentTransaction).join(
                SalePaymentTerm,
                PaymentTransaction.sale_payment_term_id == SalePaymentTerm.id
            ).join(
                ProfessionalSale,
                SalePaymentTerm.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.customer_id == customer_id,
                func.date(PaymentTransaction.payment_date) == activity_date,
                PaymentTransaction.is_deleted == False,
                # Filter out payments from direct/cash sales
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    SalePaymentTerm.payment_status.in_(
                        [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]
                    )
                )
            ).all()

            total_sales = sum(s.total_amount for s in sales)
            total_payments = sum(p.amount for p in payments)

            return {
                'sales': sales,
                'payments': payments,
                'total_sales_amount': total_sales,
                'total_payments_amount': total_payments,
                'sale_count': len(sales),
                'payment_count': len(payments),
            }

    def get_customers_with_daily_activity(self, activity_date: date) -> list:
        """Return distinct customer IDs with credit sales or payments on the given date."""
        with get_session() as session:
            # Customers with credit sales
            sale_customers = session.query(ProfessionalSale.customer_id).filter(
                ProfessionalSale.is_credit_sale == True,
                func.date(ProfessionalSale.created_at) == activity_date,
                ProfessionalSale.is_deleted == False
            ).distinct()

            # Customers with payments
            payment_customers = session.query(ProfessionalSale.customer_id).select_from(
                PaymentTransaction
            ).join(
                SalePaymentTerm,
                PaymentTransaction.sale_payment_term_id == SalePaymentTerm.id
            ).join(
                ProfessionalSale,
                SalePaymentTerm.sale_id == ProfessionalSale.id
            ).filter(
                func.date(PaymentTransaction.payment_date) == activity_date,
                PaymentTransaction.is_deleted == False,
                ProfessionalSale.is_deleted == False
            ).distinct()

            ids = set()
            for row in sale_customers.all():
                ids.add(row[0])
            for row in payment_customers.all():
                ids.add(row[0])
            return list(ids)

    def get_opening_balance_for_date(self, customer_id: int, target_date: date) -> float:
        """Return the outstanding balance just before the first transaction on target_date."""
        history = self.get_customer_combined_history(customer_id)
        for tx in history:
            tx_date = tx.get('date')
            if tx_date and tx_date >= target_date:
                return tx['balance_before']
        return history[-1]['balance_after'] if history else 0.0

    def was_notification_sent(self, customer_id: int, notification_date: date) -> bool:
        with get_session() as session:
            return session.query(CustomerDailyNotification).filter(
                CustomerDailyNotification.customer_id == customer_id,
                CustomerDailyNotification.notification_date == notification_date,
                CustomerDailyNotification.status == 'sent'
            ).first() is not None

    def mark_notification_sent(self, customer_id: int, notification_date: date,
                            status='sent', error: str = None):
        with get_session() as session:
            record = CustomerDailyNotification(
                customer_id=customer_id,
                notification_date=notification_date,
                status=status,
                error_message=error[:500] if error else None
            )
            session.add(record)
            session.commit()

    @staticmethod
    def format_daily_activity_summary(customer_name: str, activity_date: date,
                                    opening_balance: float, closing_balance: float,
                                    activity: dict) -> str:
        lines = [
            f"📅 *(እለታዊ የዱቤ ማጠቃለያ ለ) {customer_name}*",
            f"Date (ቀን): {activity_date.strftime('%d/%m/%Y')}",
            "",
            f"*የቆየ ቀሪ:* ETB {opening_balance:,.2f}",
            "",
        ]
        if activity['sale_count'] > 0:
            lines.append(f"🛒 *(አዲስ የገባ የዱቤ ሽያጭ):* {activity['sale_count']} sale(s)   →   + ETB {activity['total_sales_amount']:,.2f}\n")
        if activity['payment_count'] > 0:
            lines.append(f"💰 *(የተከፈለ):* {activity['payment_count']} ክፍያዎች   →   - ETB {activity['total_payments_amount']:,.2f}\n")
        lines.append("")
        lines.append(f"*ጠቅላላ ቀሪ:* ETB {closing_balance:,.2f}\n\n")
        lines.append(f"*የአከፋፈል ሁኔታውን ለማየት ከታች የተላከውን pdf ይመልከቱ*\n")
        lines.append(f"*የተላከሎትን ወይም የወሰዱትን እቃዎች ለማየት ወይም በፈልጉት ሰአት የአከፋፈል ሁኔታ ለማየት*\n")
        lines.append(f"*start menu -> customer/ደንብኛ -> credit item history ወይም credit payment history ይንኩ፡፡*\n\n")
        lines.append(f"*==================================================*\n\n")
        lines.append(f"*developed by: Megazen Systems*\n")
        lines.append(f"contact us: @Megazenapp/ +251974250852")
        return "\n".join(lines)
    
    def _refresh_json_cache_from_db(self):
        """Refresh JSON daily cache from database after deletion."""
        try:
            cache = DailySalesCacheService()
            cache.refresh_from_db()
            logger.info("JSON cache refreshed after sale deletion")
        except Exception as e:
            logger.error(f"Failed to refresh JSON cache after deletion: {e}")
    
    def delete_payment_group(self, transaction_ids: List[int], user_id: int = None) -> bool:
        """Delete a group of payment transactions (e.g., same date/bank) and update terms."""
        with get_session() as session:
            try:
                affected_accounts = set()
                for tid in transaction_ids:
                    payment = session.query(PaymentTransaction).filter(
                        PaymentTransaction.id == tid,
                        PaymentTransaction.is_deleted == False
                    ).first()
                    if not payment:
                        continue

                    term = payment.payment_term
                    if not term:
                        continue

                    amount = payment.amount
                    bank_account_id = payment.bank_account_id

                    # Soft delete payment transaction
                    payment.is_deleted = True
                    if user_id:
                        payment.last_modified_by = user_id

                    # Soft delete associated bank transaction (simplified match)
                    bank_tx = session.query(BankTransaction).filter(
                        BankTransaction.sale_payment_term_id == term.id,
                        BankTransaction.amount == amount,
                        BankTransaction.bank_account_id == bank_account_id,
                        BankTransaction.is_deleted == False
                    ).first()
                    if bank_tx:
                        bank_tx.is_deleted = True
                        if user_id:
                            bank_tx.last_modified_by = user_id
                        affected_accounts.add(bank_account_id)

                    # Update payment term
                    term.paid_amount -= amount
                    term.update_status()

                # Recalculate balances for all affected accounts (once, after all deletions)
                for acc_id in affected_accounts:
                    self.bank_transaction_service.recalculate_balances_for_account(session, acc_id)

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting payment group: {e}", exc_info=True)
                return False
    
    def get_credit_customers_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        short_term_only: bool = False,
        search: str = "",
        fuzzy: bool = False
    ) -> Tuple[List[Dict], int]:
        from models.sale_payment_term import SalePaymentTerm, PaymentStatusEnum
        from models.customers import Customer
        from sqlalchemy import func, or_, and_, case, cast, String
        from datetime import date

        with get_session() as session:
            # Base query with joins – include customer name and phone
            query = session.query(
                ProfessionalSale.customer_id,
                func.sum(SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount).label('total_remaining'),
                func.sum(SalePaymentTerm.total_amount).label('total_amount'),
                func.sum(SalePaymentTerm.paid_amount).label('paid_amount'),
                func.min(SalePaymentTerm.due_date).label('earliest_due_date'),
                func.max(
                    case(
                        (
                            and_(
                                SalePaymentTerm.due_date == func.date(ProfessionalSale.created_at),
                                SalePaymentTerm.due_date == date.today(),
                                (SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount) > 0
                            ),
                            1
                        ),
                        else_=0
                    )
                ).label('has_short_term'),
                Customer.name.label('customer_name'),
                Customer.phone.label('customer_phone')   # <-- added phone
            ).join(
                SalePaymentTerm, ProfessionalSale.id == SalePaymentTerm.sale_id
            ).join(
                Customer, ProfessionalSale.customer_id == Customer.id
            ).filter(
                ProfessionalSale.is_deleted == False,
                SalePaymentTerm.is_deleted == False,
                Customer.is_deleted == False,
                or_(
                    ProfessionalSale.is_credit_sale == True,
                    SalePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                )
            ).group_by(
                ProfessionalSale.customer_id,
                Customer.name,
                Customer.phone   # <-- added phone to group_by
            )

            # Short‑term only
            if short_term_only:
                query = query.having(
                    case(
                        (
                            and_(
                                SalePaymentTerm.due_date == func.date(ProfessionalSale.created_at),
                                SalePaymentTerm.due_date == date.today(),
                                (SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount) > 0
                            ),
                            1
                        ),
                        else_=0
                    ) == 1
                )

            # Apply search if provided
            if search:
                if fuzzy:
                    pattern = self._fuzzy_pattern(search)
                else:
                    pattern = f"%{search.lower()}%"
                query = query.having(
                    or_(
                        func.lower(Customer.name).like(pattern),
                        func.lower(cast(func.sum(SalePaymentTerm.total_amount), String)).like(pattern),
                        func.lower(cast(func.sum(SalePaymentTerm.paid_amount), String)).like(pattern),
                        func.lower(cast(func.sum(SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount), String)).like(pattern)
                    )
                )

            # Total count
            total = query.count()

            # Ordering: unpaid first (total_remaining > 0), then by remaining descending
            order_priority = case(
                (func.sum(SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount) > 0, 0),
                else_=1
            )
            rows = query.order_by(
                order_priority,
                func.sum(SalePaymentTerm.total_amount - SalePaymentTerm.paid_amount).desc()
            ).offset((page - 1) * page_size).limit(page_size).all()

            if not rows:
                return [], 0

            # Build result list
            result = []
            for row in rows:
                remaining = row.total_remaining
                paid = row.paid_amount
                total_amt = row.total_amount

                if remaining == 0:
                    status = 'Paid'
                elif paid > 0:
                    status = 'Partial'
                else:
                    status = 'Unpaid'

                result.append({
                    'customer_id': row.customer_id,
                    'customer_name': row.customer_name,
                    'customer_phone': row.customer_phone or "",   # now available
                    'total_amount': float(total_amt),
                    'paid_amount': float(paid),
                    'remaining': float(remaining),
                    'status': status,
                    'earliest_due_date': row.earliest_due_date,
                    'has_short_term': bool(row.has_short_term),
                    'sale_ids': [],
                    'payment_term_ids': []
                })

            return result, total

    def get_product_performance_with_companions(
        self,
        start_date: date,
        end_date: date,
        low_margin_threshold: float = 4.0
    ) -> List[Dict]:
        """
        Returns product performance data including:
        - Companion margin (weighted)
        - Stock age (days since oldest batch was created)
        - Configurable low-margin threshold
        """
        from models.new_sale_item import ProfessionalSaleItem
        from models.product_batch import ProductBatch
        from models.new_product import ProfessionalProduct
        from models.new_sales import ProfessionalSale
        from sqlalchemy import func
        from datetime import datetime, time, date as date_cls, timedelta

        MIN_SALES_FOR_BCG = 3  # minimum distinct sales before trusting a Star/Cash Cow/Dog/Question Mark label

        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)
        today = date_cls.today()

        with get_session() as session:
            # ---- 1. Basic product profitability ----
            product_profit = session.query(
                ProfessionalProduct.id.label('product_id'),
                ProfessionalProduct.name.label('product_name'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen).label('total_qty'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProductBatch.cost_price).label('total_cost'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProfessionalSaleItem.unit_price).label('total_selling')
            ).join(
                ProductBatch, ProfessionalSaleItem.batch_id == ProductBatch.id
            ).join(
                ProfessionalProduct, ProductBatch.product_id == ProfessionalProduct.id
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at.between(start_dt, end_dt),
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False,
                ProductBatch.is_deleted == False,
                ProfessionalProduct.is_deleted == False
            ).group_by(
                ProfessionalProduct.id, ProfessionalProduct.name
            ).all()

            product_map = {}
            for row in product_profit:
                profit = float(row.total_selling) - float(row.total_cost)
                margin = (profit / float(row.total_selling) * 100) if row.total_selling else 0.0
                product_map[row.product_id] = {
                    'product_id': row.product_id,
                    'product_name': row.product_name,
                    'quantity': int(row.total_qty),
                    'total_cost': float(row.total_cost),
                    'total_selling': float(row.total_selling),
                    'profit': profit,
                    'margin': margin,
                }

            if not product_map:
                return []

            # ---- 2. Weighted companion margins ----
            sale_items = session.query(
                ProfessionalSaleItem.sale_id,
                ProductBatch.product_id,
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProfessionalSaleItem.unit_price).label('sale_selling'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProductBatch.cost_price).label('sale_cost')
            ).join(
                ProductBatch, ProfessionalSaleItem.batch_id == ProductBatch.id
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at.between(start_dt, end_dt),
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False,
                ProductBatch.is_deleted == False
            ).group_by(
                ProfessionalSaleItem.sale_id,
                ProductBatch.product_id
            ).all()

            sale_products = {}
            sales_count_map = {}  # product_id -> number of distinct sales it appeared in this period
            for row in sale_items:
                sale_id = row.sale_id
                if sale_id not in sale_products:
                    sale_products[sale_id] = []
                selling = float(row.sale_selling)
                cost = float(row.sale_cost)
                margin = (selling - cost) / selling * 100 if selling else 0.0
                sale_products[sale_id].append({
                    'product_id': row.product_id,
                    'margin': margin,
                    'selling': selling,
                    'cost': cost,
                })
                sales_count_map[row.product_id] = sales_count_map.get(row.product_id, 0) + 1

            product_companion_weighted_sum = {pid: 0.0 for pid in product_map.keys()}
            product_companion_weight_total = {pid: 0.0 for pid in product_map.keys()}

            for sale_id, items in sale_products.items():
                for i, item in enumerate(items):
                    other_margins = []
                    other_sellings = []
                    for j, other in enumerate(items):
                        if j != i:
                            other_margins.append(other['margin'])
                            other_sellings.append(other['selling'])
                    if other_margins:
                        weighted_sum = sum(m * s for m, s in zip(other_margins, other_sellings))
                        total_selling_others = sum(other_sellings)
                        if total_selling_others > 0:
                            weighted_avg = weighted_sum / total_selling_others
                        else:
                            weighted_avg = sum(other_margins) / len(other_margins)
                        product_companion_weighted_sum[item['product_id']] += weighted_avg * total_selling_others
                        product_companion_weight_total[item['product_id']] += total_selling_others

            for pid in product_map.keys():
                if product_companion_weight_total[pid] > 0:
                    product_map[pid]['companion_margin'] = product_companion_weighted_sum[pid] / product_companion_weight_total[pid]
                else:
                    product_map[pid]['companion_margin'] = None

            # ---- 3. Stock age (inventory holding) ----
            oldest_batches = session.query(
                ProductBatch.product_id,
                func.min(ProductBatch.created_at).label('first_date')
            ).filter(
                ProductBatch.is_deleted == False,
                ProductBatch.available_quantity > 0
            ).group_by(ProductBatch.product_id).all()
            oldest_map = {row.product_id: row.first_date.date() for row in oldest_batches}

            for pid in product_map.keys():
                first_date = oldest_map.get(pid)
                if first_date:
                    product_map[pid]['stock_age_days'] = (today - first_date).days
                else:
                    product_map[pid]['stock_age_days'] = None

            # ---- 3b. Trend (profit change vs. the immediately preceding period of equal length) ----
            period_length = end_date - start_date
            prev_end_date = start_date - timedelta(days=1)
            prev_start_date = prev_end_date - period_length
            prev_start_dt = datetime.combine(prev_start_date, time.min)
            prev_end_dt = datetime.combine(prev_end_date, time.max)

            prev_profit_rows = session.query(
                ProfessionalProduct.id.label('product_id'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProductBatch.cost_price).label('total_cost'),
                func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen * ProfessionalSaleItem.unit_price).label('total_selling')
            ).join(
                ProductBatch, ProfessionalSaleItem.batch_id == ProductBatch.id
            ).join(
                ProfessionalProduct, ProductBatch.product_id == ProfessionalProduct.id
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at.between(prev_start_dt, prev_end_dt),
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False,
                ProductBatch.is_deleted == False,
                ProfessionalProduct.is_deleted == False
            ).group_by(
                ProfessionalProduct.id
            ).all()

            prev_profit_map = {
                row.product_id: float(row.total_selling) - float(row.total_cost)
                for row in prev_profit_rows
            }

            for pid in product_map.keys():
                prev_profit = prev_profit_map.get(pid)
                current_profit = product_map[pid]['profit']
                if prev_profit is None:
                    # Product had no sales in the prior period - a % change would be meaningless
                    product_map[pid]['trend'] = None
                elif prev_profit == 0:
                    # Avoid divide-by-zero; only flag a trend if profit actually moved off zero
                    product_map[pid]['trend'] = None if current_profit == 0 else 100.0
                else:
                    product_map[pid]['trend'] = (current_profit - prev_profit) / abs(prev_profit) * 100

            # ---- 4. Classification (Role + Category) ----
            all_margins = [p['margin'] for p in product_map.values() if p['margin'] is not None]
            overall_avg_margin = sum(all_margins) / len(all_margins) if all_margins else 0.0

            # BCG medians
            margins_sorted = sorted([p['margin'] for p in product_map.values()])
            quantities_sorted = sorted([p['quantity'] for p in product_map.values()])
            median_margin = margins_sorted[len(margins_sorted)//2] if margins_sorted else 0.0
            median_quantity = quantities_sorted[len(quantities_sorted)//2] if quantities_sorted else 0.0

            total_profit = sum(p['profit'] for p in product_map.values())

            for pid, data in product_map.items():
                # Role (using dynamic threshold)
                comp = data.get('companion_margin')
                margin = data['margin']
                if margin <= 0:
                    if comp is not None and comp > overall_avg_margin:
                        role = 'Loss Leader'
                    else:
                        role = 'Loss'
                elif margin < low_margin_threshold:   # <--- DYNAMIC THRESHOLD
                    if comp is not None and comp > overall_avg_margin:
                        role = 'Breakeven Helper'
                    else:
                        role = 'Low Margin'
                else:
                    role = 'Profitable'
                data['role'] = role

                # BCG Category
                sales_count = sales_count_map.get(pid, 0)
                data['sales_count'] = sales_count
                if margin <= 0:
                    # A loss is a fact regardless of sample size - keep it, don't hide it
                    category = 'Loss'
                elif sales_count < MIN_SALES_FOR_BCG:
                    # Too few transactions to trust a Star/Cash Cow/Dog/Question Mark label
                    category = 'Insufficient Data'
                elif margin > median_margin and data['quantity'] > median_quantity:
                    category = 'Star'
                elif margin <= median_margin and data['quantity'] > median_quantity:
                    category = 'Cash Cow'
                elif margin > median_margin and data['quantity'] <= median_quantity:
                    category = 'Question Mark'
                else:
                    category = 'Dog'
                data['category'] = category

                # Derived metrics
                data['roi'] = (data['profit'] / data['total_cost'] * 100) if data['total_cost'] > 0 else 0.0
                data['contribution'] = (data['profit'] / total_profit * 100) if total_profit > 0 else 0.0
                data['profit_per_unit'] = (data['profit'] / data['quantity']) if data['quantity'] else 0.0

            return list(product_map.values())