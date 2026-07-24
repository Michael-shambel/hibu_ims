#!/usr/bin/env python3
"""
"""
from models import supplier
from models.purchase_payment_term import PurchasePaymentTerm
from models.purchase import Purchase
from sqlalchemy import func, select
from operator import or_
from typing import Dict, List, Optional, Tuple
from models.new_product import ProfessionalProduct
from services.base_service import BaseService, get_session
from models.purchase import Purchase
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from datetime import date
from models.purchase_payment_term import PaymentStatusEnum, PurchasePaymentTerm
from models.purchase_payment_transaction import PaymentMethodEnum, PurchasePaymentTransaction
from models.bank_transactions import BankTransaction, TransactionDirectionEnum
from models.supplier_daily_notification import SupplierDailyNotification
from models.product_batch import ProductBatch
from models.supplier_credit_ledger import SupplierCreditLedger
from models.supplier import Supplier
# from collections import defaultdict
from services.bank_account_service import BankTransactionService
from services.supplier_service import SupplierService
from services.supplier_credit_ledger_service import SupplierCreditLedgerService
from ui.components.ethiopian_date import EthiopianDateConverter
import logging
from datetime import datetime, date
logger = logging.getLogger(__name__)

class PurchaseService(BaseService[Purchase]):
    def __init__(self):
        super().__init__(Purchase)
        self.bank_transaction_service = BankTransactionService()
        self.supplier_service = SupplierService()
        self.ledger_service = SupplierCreditLedgerService()
    def get_purchase_true_total(self, purchase_id: int) -> float:
        """Return the correct total for a purchase using the same logic as PurchaseItemsDialog. """
        with get_session() as session:
            purchase = session.query(Purchase).filter(
                Purchase.id == purchase_id,
                Purchase.is_deleted == False
            ).first()
            if not purchase:
                return 0.0

            total = 0.0

            # 1) Use batches (non‑deleted) if they exist
            if purchase.batches:
                for batch in purchase.batches:
                    if batch.is_deleted:
                        continue
                    product = batch.product
                    dozen = product.dozen if product and hasattr(product, 'dozen') else 1
                    total += batch.quantity * batch.cost_price * dozen

            # 2) Otherwise use the original items_data (credit purchase)
            elif purchase.items_data and isinstance(purchase.items_data, list) and purchase.items_data:
                for item in purchase.items_data:
                    qty = item.get('quantity', 0)
                    cost = item.get('cost_price', 0.0)
                    dozen = item.get('dozen', 1)
                    total += qty * cost * dozen

            return total
    
    
    def create_purchase_with_session(self, session: Session, data: dict) -> Purchase:
        purchase = Purchase(
            supplier_id=data['supplier_id'],
            total_amount=data['total_amount'],
            is_credit_sale=(data['payment_status'] == 'credit'),
            purchase_date=data.get('payment_date', date.today()),
            created_at=data.get('created_at', date.today()),
            last_modified=data.get('last_modified', date.today())
        )
        session.add(purchase)
        session.flush()

        payment_status_enum = PaymentStatusEnum.PAID if data['payment_status'] == 'paid' else PaymentStatusEnum.CREDIT
        paid_amount = data['total_amount'] if payment_status_enum == PaymentStatusEnum.PAID else 0.0

        payment_term = PurchasePaymentTerm(
            purchase_id=purchase.id,
            payment_status=payment_status_enum,
            total_amount=data['total_amount'],
            paid_amount=paid_amount,
            created_at=data.get('created_at', date.today()),
            last_modified=data.get('last_modified', date.today())
        )
        session.add(payment_term)
        session.flush()

        # ✅ Ledger: Purchase entry (always, regardless of paid/credit)
        self.ledger_service.add_entry(
            session=session,
            supplier_id=purchase.supplier_id,
            entry_date=purchase.purchase_date,
            entry_type='purchase',
            description=f"Purchase #{purchase.id}",
            debit=data['total_amount'],
            credit=0.0,
            purchase_id=purchase.id
        )

        if payment_status_enum == PaymentStatusEnum.PAID:
            method_str = data.get('payment_method', 'cash').lower()
            try:
                payment_method_enum = PaymentMethodEnum(method_str)
            except ValueError:
                payment_method_enum = PaymentMethodEnum.CASH

            payment_transaction = PurchasePaymentTransaction(
                purchase_payments_term_id=payment_term.id,
                payment_date=data.get('payment_date', date.today()),
                payment_method=payment_method_enum,
                amount=data['total_amount'],
                bank_account_id=data.get('bank_account_id'),
                user_id=data.get('user_id'),
                created_at=data.get('created_at', date.today()),
                last_modified=data.get('last_modified', date.today())
            )
            session.add(payment_transaction)
            session.flush()

            if data.get('bank_account_id'):
                current_balance = self.bank_transaction_service.get_balance(data['bank_account_id'])
                new_balance = current_balance - data['total_amount']
                if new_balance < 0:
                    raise ValueError("Insufficient funds in bank account")
                bank_transaction = BankTransaction(
                    bank_account_id=data['bank_account_id'],
                    transaction_date=data.get('payment_date', date.today()),
                    direction=TransactionDirectionEnum.DEBIT,
                    amount=data['total_amount'],
                    balance_after=current_balance - data['total_amount'],
                    payment_method=payment_method_enum,
                    description=f"Payment for purchase #{purchase.id}",
                    reference_number=data.get('invoice_number'),
                    cheque_number=None,
                    purchase_payment_term_id=payment_term.id,
                    recorded_by_user_id=data.get('user_id'),
                    created_at=data.get('created_at', date.today()),
                    last_modified=data.get('last_modified', date.today())
                )
                session.add(bank_transaction)
                session.flush()

                # ✅ Ledger: Payment entry for paid purchases
                self.ledger_service.add_entry(
                    session=session,
                    supplier_id=purchase.supplier_id,
                    entry_date=purchase.purchase_date,
                    entry_type='payment',
                    description=f"Payment for purchase #{purchase.id}",
                    debit=0.0,
                    credit=data['total_amount'],
                    purchase_id=purchase.id,
                    bank_transaction_id=bank_transaction.id
                )

                self.bank_transaction_service.recalculate_balances_for_account(session, data['bank_account_id'])

        return purchase
    
    def create_credit_purchase(self, data: dict) -> Purchase:
        with get_session() as session:
            try:
                total_amount = sum(item['quantity'] * item['cost_price'] * item['dozen'] for item in data['items'])

                purchase = Purchase(
                    supplier_id=data['supplier_id'],
                    total_amount=total_amount,
                    purchase_date=data['purchase_date'],
                    is_credit_sale=True,
                    items_data=data['items'],
                    created_at=data.get('created_at', date.today()),
                    last_modified=data.get('last_modified', date.today())
                )
                session.add(purchase)
                session.flush()

                payment_term = PurchasePaymentTerm(
                    purchase_id=purchase.id,
                    payment_status=PaymentStatusEnum.CREDIT,
                    total_amount=total_amount,
                    paid_amount=0.0,
                    created_at=data.get('created_at', date.today()),
                    last_modified=data.get('last_modified', date.today())
                )
                session.add(payment_term)
                session.flush()

                # ✅ Ledger: Purchase entry for credit purchase
                self.ledger_service.add_entry(
                    session=session,
                    supplier_id=purchase.supplier_id,
                    entry_date=purchase.purchase_date or date.today(),
                    entry_type='purchase',
                    description=f"Credit purchase #{purchase.id}",
                    debit=total_amount,
                    credit=0.0,
                    purchase_id=purchase.id
                )

                session.commit()
                return purchase
            except Exception as e:
                session.rollback()
                logger.exception("Failed to create credit purchase")
                return None # type: ignore
        
    def get_credit_purchases_list(self) -> list:
        """Return list of credit purchases with details for table, newest first."""
        with get_session() as session:
            # Use any() to avoid cartesian product
            purchases = session.query(Purchase).options(
                joinedload(Purchase.supplier),
                joinedload(Purchase.payment_terms)
            ).filter(
                Purchase.is_deleted == False,
                or_(
                    Purchase.is_credit_sale == True,
                    Purchase.payment_terms.any(
                    PurchasePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                )

                )
            ).order_by(Purchase.created_at.desc()).all()

            result = []
            for purchase in purchases:
                for term in purchase.payment_terms:
                    if term.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                        total = term.total_amount
                        paid = term.paid_amount
                        remaining = total - paid
                        status_display = term.payment_status.value.capitalize()
                        result.append({
                            'purchase_id': purchase.id,
                            'supplier_name': purchase.supplier.supplier_name if purchase.supplier else "N/A",
                            'total_amount': total,
                            'paid_amount': paid,
                            'remaining': remaining,
                            'status': status_display,
                            'payment_term_id': term.id,
                            'purchase_date': purchase.purchase_date,
                            'created_at': purchase.created_at
                        })
                    else:
                        if purchase.payment_terms:
                            term = purchase.payment_terms[0]
                            total = term.total_amount
                            paid = term.paid_amount
                            remaining = total - paid
                            status_display = term.payment_status.value.capitalize()
                            result.append({
                                'purchase_id': purchase.id,
                                'supplier_name': purchase.supplier.supplier_name if purchase.supplier else "N/A",
                                'total_amount': total,
                                'paid_amount': paid,
                                'remaining': remaining,
                                'status': status_display,
                                'payment_term_id': term.id,
                                'purchase_date': purchase.purchase_date,
                                'created_at': purchase.created_at
                            })
            return result


    def get_credit_purchases_summary(self) -> dict:
        with get_session() as session:
            rows = session.query(
                SupplierCreditLedger.entry_type,
                func.sum(SupplierCreditLedger.debit).label('total_debit'),
                func.sum(SupplierCreditLedger.credit).label('total_credit')
            ).filter(
                SupplierCreditLedger.is_deleted == False
            ).group_by(SupplierCreditLedger.entry_type).all()

            total_amount = 0.0
            total_paid = 0.0

            for row in rows:
                debit = row.total_debit or 0.0
                credit = row.total_credit or 0.0
                if row.entry_type == 'purchase':
                    total_amount += debit
                elif row.entry_type == 'payment':
                    total_paid += credit
                elif row.entry_type in ('adjustment', 'discount'):
                    # Net effect on total amount: debit increases, credit decreases
                    total_amount += debit
                    total_amount -= credit
                else:
                    # Fallback: treat as adjustment
                    total_amount += debit
                    total_amount -= credit

            return {
                'total_credit_amount': total_amount,
                'total_paid': total_paid,
                'total_unpaid': total_amount - total_paid
            }
    
    def record_payment_by_term(self, payment_term_id: int, amount: float, bank_account_id: int, user_id: int) -> Tuple[bool, str]:
        """Record a payment against a purchase payment term."""
        with get_session() as session:
            try:
                from models.purchase_payment_term import PurchasePaymentTerm
                from models.purchase_payment_transaction import PurchasePaymentTransaction, PaymentMethodEnum
                from models.bank_transactions import BankTransaction, TransactionDirectionEnum
                from services.bank_transaction_service import BankTransactionService

                term = session.query(PurchasePaymentTerm).get(payment_term_id)
                if not term:
                    return False, "Payment term not found."
                
                bank_tx_service = BankTransactionService()
                current_balance = bank_tx_service.get_balance(bank_account_id)
                if current_balance < amount:
                    return False, f"Insufficient funds. Available: ${current_balance:,.2f}, Required: ${amount:,.2f}"

                # Create payment transaction
                payment_trans = PurchasePaymentTransaction(
                    purchase_payments_term_id=term.id,
                    payment_date=date.today(),
                    payment_method=PaymentMethodEnum.TRANSFER,
                    amount=amount,
                    bank_account_id=bank_account_id,
                    user_id=user_id
                )
                session.add(payment_trans)

                # Update term
                term.paid_amount += amount
                term.update_status()

                # Bank transaction (debit)
                current_balance = bank_tx_service.get_balance(bank_account_id)
                bank_tx = BankTransaction(
                    bank_account_id=bank_account_id,
                    transaction_date=date.today(),
                    direction=TransactionDirectionEnum.DEBIT,
                    amount=amount,
                    balance_after=current_balance - amount,
                    payment_method=PaymentMethodEnum.TRANSFER,
                    description=f"Payment for purchase term #{term.id}",
                    purchase_payment_term_id=term.id,
                    recorded_by_user_id=user_id
                )
                session.add(bank_tx)
                session.flush()

                # ✅ Ledger: Payment entry
                self.ledger_service.add_entry(
                    session=session,
                    supplier_id=term.purchase.supplier_id,
                    entry_date=date.today(),
                    entry_type='payment',
                    description=f"Payment for purchase term #{term.id}",
                    debit=0.0,
                    credit=amount,
                    bank_transaction_id=bank_tx.id
                )

                # Recalculate to maintain chronological order
                bank_tx_service.recalculate_balances_for_account(session, bank_account_id)

                session.commit()
                return True, ""
            except Exception as e:
                session.rollback()
                logger.error(f"Error recording purchase payment by term: {e}")
                return False, "An error occurred while recording the payment."


    def get_purchase_with_batches(self, purchase_id: int) -> Optional[Purchase]:
        """Retrieve a purchase with its batches and products eagerly loaded."""
        with get_session() as session:

            return session.query(Purchase).options(
                joinedload(Purchase.batches).joinedload(ProductBatch.product)
            ).filter(
                Purchase.id == purchase_id,
                Purchase.is_deleted == False
            ).first()
    
    def get_credit_purchases_by_supplier(self) -> list:
        with get_session() as session:
            rows = session.query(
                SupplierCreditLedger.supplier_id,
                SupplierCreditLedger.entry_type,
                func.sum(SupplierCreditLedger.debit).label('total_debit'),
                func.sum(SupplierCreditLedger.credit).label('total_credit')
            ).filter(
                SupplierCreditLedger.is_deleted == False
            ).group_by(
                SupplierCreditLedger.supplier_id,
                SupplierCreditLedger.entry_type
            ).all()

            from collections import defaultdict
            supplier_totals = defaultdict(lambda: {'total_amount': 0.0, 'paid_amount': 0.0})

            for row in rows:
                sid = row.supplier_id
                debit = row.total_debit or 0.0
                credit = row.total_credit or 0.0
                if row.entry_type == 'purchase':
                    supplier_totals[sid]['total_amount'] += debit
                elif row.entry_type == 'payment':
                    supplier_totals[sid]['paid_amount'] += credit
                elif row.entry_type in ('adjustment', 'discount'):
                    # Net effect on total amount
                    supplier_totals[sid]['total_amount'] += debit
                    supplier_totals[sid]['total_amount'] -= credit
                else:
                    supplier_totals[sid]['total_amount'] += debit
                    supplier_totals[sid]['total_amount'] -= credit

            # Collect purchase IDs per supplier (for the "View" button)
            purchases = session.query(Purchase).filter(
                Purchase.is_deleted == False
            ).all()
            supplier_pids = defaultdict(list)
            for p in purchases:
                supplier_pids[p.supplier_id].append(p.id)

            # Get supplier names
            suppliers = session.query(Supplier).filter(
                Supplier.id.in_(list(supplier_totals.keys()))
            ).all()
            supplier_names = {s.id: s.supplier_name for s in suppliers}
            supplier_phones = {s.id: s.contact_phone for s in suppliers}

            result = []
            for sid, totals in supplier_totals.items():
                total_amount = totals['total_amount']
                paid_amount = totals['paid_amount']
                remaining = total_amount - paid_amount

                if remaining <= 0:
                    status = 'Paid'
                elif paid_amount > 0:
                    status = 'Partial'
                else:
                    status = 'Unpaid'

                result.append({
                    'supplier_id': sid,
                    'supplier_name': supplier_names.get(sid, 'Unknown'),
                    'supplier_phone': supplier_phones.get(sid, ''),
                    'total_amount': total_amount,
                    'paid_amount': paid_amount,
                    'remaining': remaining,
                    'status': status,
                    'purchase_ids': supplier_pids.get(sid, []),
                    'payment_term_ids': [],
                })

            result.sort(key=lambda x: x['remaining'], reverse=True)
            return result
    
    def record_supplier_payment(
        self,
        supplier_id: int,
        payments: List[Tuple[float, int]],
        user_id: int,
        note: str = "",
        payment_date: date = None
    ) -> Tuple[bool, str]:
        if payment_date is None:
            payment_date = date.today()
        dt = datetime.combine(payment_date, datetime.min.time())

        with get_session() as session:
            try:
                # ---- 1. Fetch all purchases for this supplier ----
                all_purchases = session.query(Purchase).options(
                    joinedload(Purchase.payment_terms)
                ).filter(
                    Purchase.supplier_id == supplier_id,
                    Purchase.is_deleted == False
                ).all()

                logger.info(f"Found {len(all_purchases)} purchases for supplier {supplier_id}")

                # ---- 2. Force recalculation of EVERY purchase's payment term ----
                for purchase in all_purchases:
                    if purchase.payment_terms:
                        logger.debug(
                            f"Recalculating purchase {purchase.id} "
                            f"(batches: {len(purchase.batches) if purchase.batches else 0}, "
                            f"items_data: {bool(purchase.items_data)})"
                        )
                        self.recalc_purchase_total(purchase.id, session, user_id)
                        session.flush()
                        session.refresh(purchase)
                        if purchase.payment_terms:
                            session.refresh(purchase.payment_terms[0])
                            logger.debug(
                                f"After recalc: purchase {purchase.id} term total={purchase.payment_terms[0].total_amount}, "
                                f"paid={purchase.payment_terms[0].paid_amount}"
                            )

                # ---- 3. Query for outstanding purchases ----
                purchases = session.query(Purchase).options(
                    joinedload(Purchase.payment_terms)
                ).filter(
                    Purchase.supplier_id == supplier_id,
                    Purchase.is_deleted == False,
                    Purchase.payment_terms.any(
                        (PurchasePaymentTerm.total_amount - PurchasePaymentTerm.paid_amount) > 0
                    )
                ).order_by(Purchase.created_at.asc()).all()

                logger.info(f"After recalculation, found {len(purchases)} outstanding purchases")

                # ---- 4. If none, repair using the ledger total ----
                if not purchases:
                    # Compute total unpaid from the ledger
                    ledger_total = session.query(
                        func.coalesce(func.sum(SupplierCreditLedger.debit), 0.0) -
                        func.coalesce(func.sum(SupplierCreditLedger.credit), 0.0)
                    ).filter(
                        SupplierCreditLedger.supplier_id == supplier_id,
                        SupplierCreditLedger.is_deleted == False
                    ).scalar() or 0.0

                    logger.warning(
                        f"No outstanding purchases found. Ledger shows unpaid: {ledger_total:.2f}"
                    )

                    if ledger_total > 0:
                        # Find the oldest purchase (or any) to repair
                        repair_purchase = session.query(Purchase).filter(
                            Purchase.supplier_id == supplier_id,
                            Purchase.is_deleted == False
                        ).order_by(Purchase.created_at.asc()).first()

                        if repair_purchase and repair_purchase.payment_terms:
                            term = repair_purchase.payment_terms[0]
                            # Set total_amount so that remaining = ledger_total
                            # term.paid_amount is assumed to be correct (or zero)
                            term.total_amount = ledger_total + term.paid_amount
                            term.update_status()
                            session.flush()
                            session.refresh(term)
                            logger.info(
                                f"Repaired purchase {repair_purchase.id}: term.total_amount set to {term.total_amount:.2f} "
                                f"(paid={term.paid_amount:.2f}, remaining={ledger_total:.2f})"
                            )

                            # Re-query outstanding purchases
                            purchases = session.query(Purchase).options(
                                joinedload(Purchase.payment_terms)
                            ).filter(
                                Purchase.supplier_id == supplier_id,
                                Purchase.is_deleted == False,
                                Purchase.payment_terms.any(
                                    (PurchasePaymentTerm.total_amount - PurchasePaymentTerm.paid_amount) > 0
                                )
                            ).order_by(Purchase.created_at.asc()).all()

                            if not purchases:
                                # Still nothing – log and return error
                                return False, (
                                    "Repair attempted but still no outstanding purchase found. "
                                    "Please contact support."
                                )
                        else:
                            return False, (
                                "Ledger shows unpaid balance but no purchase record found to repair. "
                                "Please contact support."
                            )
                    else:
                        return False, "No outstanding credit purchases for supplier."

                # ---- 5. Proceed with payment allocation (unchanged) ----
                running_balances = {}
                for amount, bank_account_id in payments:
                    if amount <= 0:
                        continue
                    if bank_account_id not in running_balances:
                        bank_tx_service = BankTransactionService()
                        current_balance = bank_tx_service.get_balance(bank_account_id)
                        running_balances[bank_account_id] = current_balance
                    if running_balances[bank_account_id] < amount:
                        return False, (
                            f"Insufficient funds. "
                            f"Available: ${running_balances[bank_account_id]:,.2f}, "
                            f"Required: ${amount:,.2f}"
                        )
                    running_balances[bank_account_id] -= amount

                affected_accounts = set()

                for amount, bank_account_id in payments:
                    if amount <= 0:
                        continue

                    supplier_obj = self.supplier_service.get_by_id(supplier_id)
                    supplier = supplier_obj.supplier_name if supplier_obj else "N/A"
                    bank_tx_service = BankTransactionService()
                    current_balance = bank_tx_service.get_balance(bank_account_id)

                    bank_transaction = BankTransaction(
                        bank_account_id=bank_account_id,
                        transaction_date=payment_date,
                        direction=TransactionDirectionEnum.DEBIT,
                        amount=amount,
                        balance_after=current_balance - amount,
                        payment_method=PaymentMethodEnum.TRANSFER,
                        description=f"Payment for supplier {supplier} - {note}" if note else f"Payment for supplier {supplier}",
                        recorded_by_user_id=user_id,
                        created_at=dt,
                        last_modified=dt
                    )
                    session.add(bank_transaction)
                    session.flush()
                    affected_accounts.add(bank_account_id)

                    # Ledger: Payment entry
                    self.ledger_service.add_entry(
                        session=session,
                        supplier_id=supplier_id,
                        entry_date=payment_date,
                        entry_type='payment',
                        description=f"Payment - {note}" if note else f"Payment for supplier {supplier}",
                        debit=0.0,
                        credit=amount,
                        bank_transaction_id=bank_transaction.id
                    )

                    remaining = amount
                    for purchase in purchases:
                        if remaining <= 0:
                            break
                        unpaid_terms = [
                            term for term in purchase.payment_terms
                            if (term.total_amount - term.paid_amount) > 0
                        ]
                        if not unpaid_terms:
                            continue
                        for term in unpaid_terms:
                            if remaining <= 0:
                                break
                            balance = term.total_amount - term.paid_amount
                            if balance <= 0:
                                continue
                            payment_for_this = min(remaining, balance)

                            payment_trans = PurchasePaymentTransaction(
                                purchase_payments_term_id=term.id,
                                payment_date=payment_date,
                                payment_method=PaymentMethodEnum.TRANSFER,
                                amount=payment_for_this,
                                bank_account_id=bank_account_id,
                                user_id=user_id,
                                notes=note,
                                bank_transaction_id=bank_transaction.id,
                                created_at=dt,
                                last_modified=dt
                            )
                            session.add(payment_trans)

                            term.paid_amount += payment_for_this
                            term.update_status()
                            term.last_modified = dt
                            remaining -= payment_for_this

                for acc_id in affected_accounts:
                    BankTransactionService().recalculate_balances_for_account(session, acc_id)

                session.commit()
                logger.info(f"Supplier payment recorded successfully for supplier {supplier_id}")
                return True, ""

            except Exception as e:
                session.rollback()
                logger.error(f"Error recording supplier payment: {e}", exc_info=True)
                return False, f"An error occurred: {str(e)}"
    
    def get_supplier_payment_history(self, supplier_id: int) -> List[Dict]:
        with get_session() as session:
            payments = session.query(PurchasePaymentTransaction).join(
                PurchasePaymentTerm, PurchasePaymentTransaction.purchase_payments_term_id == PurchasePaymentTerm.id
            ).join(
                Purchase, PurchasePaymentTerm.purchase_id == Purchase.id
            ).options(
                joinedload(PurchasePaymentTransaction.bank_account)
            ).filter(
                Purchase.supplier_id == supplier_id,
                Purchase.is_credit_sale == True,   
                Purchase.is_deleted == False,
                PurchasePaymentTransaction.is_deleted == False
            ).order_by(PurchasePaymentTransaction.payment_date.desc(), PurchasePaymentTransaction.id.desc()).all()

            result = []
            for pt in payments:
                result.append({
                    'transaction_id': pt.id,
                    'payment_term_id': pt.purchase_payments_term_id,
                    'purchase_id': pt.purchase_term.purchase_id,
                    'payment_date': pt.payment_date,
                    'amount': pt.amount,
                    'bank_account_id': pt.bank_account_id,
                    'bank_account_name': pt.bank_account.account_name if pt.bank_account else 'N/A',
                    'bank_name': pt.bank_account.bank_name if pt.bank_account else '',
                    'payment_method': pt.payment_method.value if pt.payment_method else 'transfer',
                    'notes': pt.notes
                })
            return result
    
    def delete_payment_transaction(self, transaction_id: int, user_id: int = None) -> bool:
        with get_session() as session:
            try:
                payment = session.query(PurchasePaymentTransaction).filter(
                    PurchasePaymentTransaction.id == transaction_id,
                    PurchasePaymentTransaction.is_deleted == False
                ).first()
                if not payment:
                    logger.warning(f"Purchase payment transaction {transaction_id} not found")
                    return False

                term = payment.purchase_term
                if not term:
                    logger.warning(f"Payment term for transaction {transaction_id} not found")
                    return False

                amount = payment.amount
                bank_account_id = payment.bank_account_id

                # Soft delete payment transaction
                payment.is_deleted = True
                if user_id:
                    payment.last_modified_by = user_id

                # Soft delete associated bank transaction (match by term, amount, account)
                bank_tx = session.query(BankTransaction).filter(
                    BankTransaction.purchase_payment_term_id == term.id,
                    BankTransaction.amount == amount,
                    BankTransaction.bank_account_id == bank_account_id,
                    BankTransaction.is_deleted == False
                ).first()
                if bank_tx:
                    bank_tx.is_deleted = True
                    if user_id:
                        bank_tx.last_modified_by = user_id

                # ✅ Soft-delete the associated ledger entry
                if bank_tx:
                    session.query(SupplierCreditLedger).filter(
                        SupplierCreditLedger.bank_transaction_id == bank_tx.id,
                        SupplierCreditLedger.is_deleted == False
                    ).update({"is_deleted": True}, synchronize_session=False)
                else:
                    # Fallback: try by payment_transaction_id
                    session.query(SupplierCreditLedger).filter(
                        SupplierCreditLedger.payment_transaction_id == transaction_id,
                        SupplierCreditLedger.is_deleted == False
                    ).update({"is_deleted": True}, synchronize_session=False)

                # Update payment term
                term.paid_amount -= amount
                term.update_status()

                session.flush()

                # Recalculate to maintain chronological order
                BankTransactionService().recalculate_balances_for_account(session, bank_account_id)

                session.commit()
                logger.info(f"Deleted purchase payment transaction {transaction_id}, updated term {term.id}")
                return True

            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting purchase payment transaction {transaction_id}: {e}", exc_info=True)
                return False
    
    def delete_bank_transaction_with_payments(self, bank_transaction_id: int, user_id: int = None) -> bool:
        with get_session() as session:
            try:
                bt = session.query(BankTransaction).filter(
                    BankTransaction.id == bank_transaction_id,
                    BankTransaction.is_deleted == False
                ).first()
                if not bt:
                    return False

                bank_account_id = bt.bank_account_id

                # Get all linked payment transactions
                linked_transactions = session.query(PurchasePaymentTransaction).filter(
                    PurchasePaymentTransaction.bank_transaction_id == bank_transaction_id,
                    PurchasePaymentTransaction.is_deleted == False
                ).all()

                if not linked_transactions:
                    return False

                # For each term, calculate the total amount being deleted
                term_adjustments = {}
                for tx in linked_transactions:
                    term_id = tx.purchase_payments_term_id
                    term_adjustments[term_id] = term_adjustments.get(term_id, 0.0) + tx.amount

                # Soft delete the payment transactions
                for tx in linked_transactions:
                    tx.is_deleted = True
                    if user_id:
                        tx.last_modified_by = user_id

                # Soft delete the bank transaction
                bt.is_deleted = True
                if user_id:
                    bt.last_modified_by = user_id

                # ✅ Soft-delete the associated ledger entry(s)
                session.query(SupplierCreditLedger).filter(
                    SupplierCreditLedger.bank_transaction_id == bank_transaction_id,
                    SupplierCreditLedger.is_deleted == False
                ).update({"is_deleted": True}, synchronize_session=False)

                # Adjust each term's paid_amount and update status
                for term_id, adjustment in term_adjustments.items():
                    term = session.query(PurchasePaymentTerm).get(term_id)
                    if term:
                        term.paid_amount -= adjustment
                        if term.paid_amount < 0:
                            term.paid_amount = 0.0
                        term.update_status()

                session.flush()

                # Recalculate to maintain chronological order
                BankTransactionService().recalculate_balances_for_account(session, bank_account_id)

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting bank transaction {bank_transaction_id}: {e}", exc_info=True)
                return False
    
    def delete_purchase_cascade_in_session(self, session: Session, purchase_id: int) -> bool:
        try:
            purchase = session.query(Purchase).filter(
                Purchase.id == purchase_id,
                Purchase.is_deleted == False
            ).first()
            if not purchase:
                return False

            term_ids = [term.id for term in purchase.payment_terms]

            # Collect affected bank account IDs before soft-deleting
            affected_accounts = set()
            if term_ids:
                bank_txs = session.query(BankTransaction).filter(
                    BankTransaction.purchase_payment_term_id.in_(term_ids),
                    BankTransaction.is_deleted == False
                ).all()
                for bt in bank_txs:
                    affected_accounts.add(bt.bank_account_id)

                session.query(BankTransaction).filter(
                    BankTransaction.purchase_payment_term_id.in_(term_ids),
                    BankTransaction.is_deleted == False
                ).update({"is_deleted": True}, synchronize_session=False)

                session.query(PurchasePaymentTransaction).filter(
                    PurchasePaymentTransaction.purchase_payments_term_id.in_(term_ids),
                    PurchasePaymentTransaction.is_deleted == False
                ).update({"is_deleted": True}, synchronize_session=False)

                session.query(PurchasePaymentTerm).filter(
                    PurchasePaymentTerm.id.in_(term_ids),
                    PurchasePaymentTerm.is_deleted == False
                ).update({"is_deleted": True}, synchronize_session=False)

            # Force‑delete any leftover batches (should not exist)
            session.query(ProductBatch).filter(
                ProductBatch.purchase_id == purchase_id,
                ProductBatch.is_deleted == False
            ).update({"is_deleted": True}, synchronize_session=False)

            purchase.is_deleted = True

            session.flush()

            # Recalculate balances for all affected accounts
            for acc_id in affected_accounts:
                BankTransactionService().recalculate_balances_for_account(session, acc_id)

            return True
        except Exception as e:
            logger.error(f"Error in delete_purchase_cascade_in_session: {e}")
            raise   # let the outer transaction handle rollback
    

    def get_supplier_total_credit(self, supplier_id: int) -> float:
        with get_session() as session:

            total = session.query(func.sum(PurchasePaymentTerm.total_amount)).join(
                Purchase, PurchasePaymentTerm.purchase_id == Purchase.id
            ).filter(
                Purchase.supplier_id == supplier_id,
                Purchase.is_deleted == False,
                PurchasePaymentTerm.is_deleted == False
            ).scalar() or 0.0
            return float(total)
    
    def recalc_purchase_total(self, purchase_id: int, session: Session = None, user_id: int = None) -> bool:
        def _recalc(sess):
            purchase = sess.query(Purchase).filter(
                Purchase.id == purchase_id,
                Purchase.is_deleted == False
            ).first()
            if not purchase:
                return False

            # 1. Try to calculate from batches
            new_total = (
                sess.query(func.sum(
                    ProductBatch.quantity * ProductBatch.cost_price * ProfessionalProduct.dozen
                ))
                .join(ProductBatch.product)
                .filter(
                    ProductBatch.purchase_id == purchase_id,
                    ProductBatch.is_deleted == False
                )
                .scalar() or 0.0
            )

            # 2. If no batches exist, fall back to items_data
            if new_total == 0.0 and purchase.items_data:
                new_total = sum(
                    item.get('quantity', 0) * item.get('cost_price', 0.0) * item.get('dozen', 1)
                    for item in purchase.items_data
                )

            purchase.total_amount = new_total

            term = purchase.payment_terms[0] if purchase.payment_terms else None
            if not term:
                return True

            old_paid = term.paid_amount

            if old_paid > new_total:
                surplus = old_paid - new_total
                term.paid_amount = new_total
                term.total_amount = new_total
                term.update_status()
                if surplus > 0:
                    self._allocate_surplus_to_supplier(
                        sess,
                        purchase.supplier_id,
                        surplus,
                        exclude_purchase_id=purchase_id,
                        user_id=user_id,
                        allocation_date=date.today()
                    )
            else:
                term.total_amount = new_total
                term.update_status()

            return True


    def _allocate_surplus_to_supplier(
        self,
        session: Session,
        supplier_id: int,
        surplus: float,
        exclude_purchase_id: int = None,
        user_id: int = None,
        allocation_date: date = None
    ) -> None:
        """
        Allocate a discount surplus to the supplier's oldest unpaid / partial
        purchases in FIFO order, AND create a payment transaction for each
        allocated amount so the payment history stays consistent.
        """
        if surplus <= 0:
            return

        if allocation_date is None:
            allocation_date = date.today()

        purchases = (
            session.query(Purchase)
            .join(PurchasePaymentTerm, Purchase.id == PurchasePaymentTerm.purchase_id)
            .filter(
                Purchase.supplier_id == supplier_id,
                Purchase.is_deleted == False,
                PurchasePaymentTerm.is_deleted == False,
                PurchasePaymentTerm.payment_status.in_([
                    PaymentStatusEnum.CREDIT,
                    PaymentStatusEnum.PARTIAL
                ])
            )
            .order_by(Purchase.created_at.asc())    # FIFO
            .all()
        )

        remaining = surplus

        for purchase in purchases:
            if remaining <= 0:
                break

            if exclude_purchase_id and purchase.id == exclude_purchase_id:
                continue

            term = purchase.payment_terms[0] if purchase.payment_terms else None
            if not term:
                continue

            balance_due = term.total_amount - term.paid_amount
            if balance_due <= 0:
                continue

            apply = min(remaining, balance_due)

            # Update the payment term
            term.paid_amount += apply
            term.update_status()

            # --- NEW: Create a payment transaction for the allocation ---
            payment_tx = PurchasePaymentTransaction(
                purchase_payments_term_id=term.id,
                payment_date=allocation_date,
                payment_method=PaymentMethodEnum.SURPLUS,
                amount=apply,
                bank_account_id=None,          # no bank account involved
                user_id=user_id,
                notes="Surplus allocation (discount/adjustment)",
                bank_transaction_id=None       # no bank transaction
            )
            session.add(payment_tx)

            remaining -= apply

            logger.info(
                f"Surplus allocation: applied ${apply:.2f} to purchase #{purchase.id} "
                f"(supplier {supplier_id}). Remaining surplus: ${remaining:.2f}"
            )

        if remaining > 0:
            logger.info(
                f"Supplier {supplier_id}: ${remaining:.2f} surplus exceeds all unpaid "
                f"purchases — absorbed as discount."
            )
    
    def get_supplier_combined_history(self, supplier_id: int) -> List[Dict]:
        with get_session() as session:
            entries = session.query(SupplierCreditLedger).filter(
                SupplierCreditLedger.supplier_id == supplier_id,
                SupplierCreditLedger.is_deleted == False
            ).order_by(
                SupplierCreditLedger.entry_date.asc(),
                SupplierCreditLedger.id.asc()
            ).all()

            result = []
            balance = 0.0
            for entry in entries:
                balance_before = balance

                # Determine effect on balance and map to old format
                if entry.entry_type == 'purchase':
                    # Purchase increases what you owe
                    credit_amount = entry.debit  # amount owed (credit side in supplier's view)
                    debit_amount = 0.0
                    tx_type = 'credit_purchase'
                    balance += entry.debit
                elif entry.entry_type == 'payment':
                    # Payment reduces what you owe
                    credit_amount = 0.0
                    debit_amount = entry.credit  # amount paid (debit side)
                    tx_type = 'payment'
                    balance -= entry.credit
                elif entry.entry_type in ('adjustment', 'discount'):
                    # These can be a pure debit (increase owed) or pure credit (decrease owed)
                    if entry.debit > 0:
                        credit_amount = entry.debit
                        debit_amount = 0.0
                        tx_type = 'credit_purchase'
                        balance += entry.debit
                    else:
                        credit_amount = 0.0
                        debit_amount = entry.credit
                        tx_type = 'payment'
                        balance -= entry.credit
                else:
                    # Fallback (should not happen)
                    credit_amount = entry.debit
                    debit_amount = entry.credit
                    tx_type = 'credit_purchase'
                    balance += (entry.debit - entry.credit)

                # Build bank account display for payment entries
                bank_display = "N/A"
                bank_tx_id = None
                if entry.bank_transaction_id:
                    bank_tx = session.query(BankTransaction).get(entry.bank_transaction_id)
                    if bank_tx and bank_tx.bank_account:
                        bank_display = f"{bank_tx.bank_account.bank_name} - {bank_tx.bank_account.account_name}"
                    bank_tx_id = entry.bank_transaction_id

                # Collect all transaction ids (needed for delete logic in UI)
                all_ids = [entry.payment_transaction_id] if entry.payment_transaction_id else []

                result.append({
                    'date': entry.entry_date,
                    'credit_amount': credit_amount,
                    'debit_amount': debit_amount,
                    'type': tx_type,
                    'notes': entry.description or '',
                    'bank_account_display': bank_display,
                    'bank_transaction_id': bank_tx_id,
                    'all_transaction_ids': all_ids,
                    'balance_before': balance_before,
                    'balance_after': balance,
                })

            return result
    
    def get_supplier_credit_purchases_grouped(self, supplier_id: int) -> list:
        from models.purchase_payment_term import PaymentStatusEnum
        from datetime import date

        with get_session() as session:
            purchases = session.query(Purchase).options(
                joinedload(Purchase.payment_terms),
                joinedload(Purchase.batches).joinedload(ProductBatch.product)
            ).filter(
                Purchase.supplier_id == supplier_id,
                Purchase.is_deleted == False,
                Purchase.is_credit_sale == True
            ).order_by(Purchase.purchase_date.desc()).all()

            groups = {}
            for purchase in purchases:
                # Find the relevant payment term (CREDIT or PARTIAL)
                term = None
                for pt in purchase.payment_terms:
                    if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                        term = pt
                        break
                if not term and purchase.payment_terms:
                    term = purchase.payment_terms[0]
                if not term:
                    continue

                date_key = purchase.purchase_date or purchase.created_at.date()
                if date_key not in groups:
                    groups[date_key] = {
                        'purchase_date': date_key,
                        'total_amount': 0.0,
                        'paid_amount': 0.0,
                        'remaining': 0.0,
                        'purchase_ids': [],
                        'items': [],
                    }
                groups[date_key]['total_amount'] += term.total_amount
                groups[date_key]['paid_amount'] += term.paid_amount
                groups[date_key]['remaining'] += term.total_amount - term.paid_amount
                groups[date_key]['purchase_ids'].append(purchase.id)

                # Collect items from batches
                for batch in purchase.batches:
                    if batch.is_deleted:
                        continue
                    product = batch.product
                    if not product:
                        continue

                    product_name = product.name
                    dozen = product.dozen if product.dozen else 1
                    # batch.quantity = number of dozen packs
                    quantity = batch.quantity
                    cost_price = batch.cost_price or 0.0
                    total = quantity * dozen * cost_price

                    groups[date_key]['items'].append({
                        'product_name': product_name,
                        'quantity': quantity,    # number of dozen packs
                        'dozen': dozen,          # pieces per pack
                        'unit_price': cost_price,
                        'total': total
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
                    'purchase_date': date_key,
                    'total_amount': group['total_amount'],
                    'paid_amount': group['paid_amount'],
                    'remaining': group['remaining'],
                    'status': status,
                    'purchase_ids': group['purchase_ids'],
                    'items': group['items'],
                })
            result.sort(key=lambda x: x['purchase_date'] or date.min, reverse=True)
            return result
    
    def get_daily_credit_activity(self, supplier_id: int, activity_date: date) -> dict:
        with get_session() as session:
            entries = session.query(SupplierCreditLedger).filter(
                SupplierCreditLedger.supplier_id == supplier_id,
                SupplierCreditLedger.entry_date == activity_date,
                SupplierCreditLedger.is_deleted == False
            ).all()
            
            total_purchases = 0.0
            total_payments = 0.0
            purchase_count = 0
            payment_count = 0
            net_adjustment = 0.0      # positive = increase owed, negative = decrease
            adjustment_count = 0
            
            for entry in entries:
                if entry.entry_type == 'purchase':
                    total_purchases += entry.debit
                    purchase_count += 1
                elif entry.entry_type == 'payment':
                    total_payments += entry.credit
                    payment_count += 1
                elif entry.entry_type in ('adjustment', 'discount'):
                    # net effect of this entry: debit increases, credit decreases
                    entry_net = entry.debit - entry.credit
                    net_adjustment += entry_net
                    adjustment_count += 1
            
            return {
                'total_purchases_amount': total_purchases,
                'total_payments_amount': total_payments,
                'purchase_count': purchase_count,
                'payment_count': payment_count,
                'net_adjustment': net_adjustment,
                'adjustment_count': adjustment_count,
            }

    def get_suppliers_with_daily_activity(self, activity_date: date) -> list:
        with get_session() as session:
            # Suppliers with credit purchases on that date
            purchase_suppliers = session.query(Purchase.supplier_id).filter(
                Purchase.is_credit_sale == True,
                func.date(Purchase.purchase_date) == activity_date,
                Purchase.is_deleted == False
            ).distinct().all()

            # Suppliers with payments on that date
            from models.purchase_payment_transaction import PurchasePaymentTransaction
            payment_suppliers = session.query(Purchase.supplier_id).select_from(
                PurchasePaymentTransaction
            ).join(
                PurchasePaymentTerm,
                PurchasePaymentTransaction.purchase_payments_term_id == PurchasePaymentTerm.id
            ).join(
                Purchase,
                PurchasePaymentTerm.purchase_id == Purchase.id
            ).filter(
                func.date(PurchasePaymentTransaction.payment_date) == activity_date,
                PurchasePaymentTransaction.is_deleted == False,
                Purchase.is_deleted == False
            ).distinct().all()

            # Combine unique supplier IDs
            supplier_ids = set()
            for (sid,) in purchase_suppliers + payment_suppliers:
                supplier_ids.add(sid)
            return list(supplier_ids)

    def get_opening_balance_for_date(self, supplier_id: int, target_date: date) -> float:
        """Return the balance at the END of the day before target_date."""
        with get_session() as session:
            result = session.query(
                func.coalesce(func.sum(SupplierCreditLedger.debit), 0.0) -
                func.coalesce(func.sum(SupplierCreditLedger.credit), 0.0)
            ).filter(
                SupplierCreditLedger.supplier_id == supplier_id,
                SupplierCreditLedger.entry_date < target_date,
                SupplierCreditLedger.is_deleted == False
            ).scalar()
            
            return float(result) if result else 0.0

    def was_notification_sent(self, supplier_id: int, notification_date: date) -> bool:
        with get_session() as session:
            return session.query(SupplierDailyNotification).filter(
                SupplierDailyNotification.supplier_id == supplier_id,
                SupplierDailyNotification.notification_date == notification_date,
                SupplierDailyNotification.status == 'sent'
            ).first() is not None

    def mark_notification_sent(self, supplier_id: int, notification_date: date,
                               status='sent', error: str = None):
        with get_session() as session:
            record = SupplierDailyNotification(
                supplier_id=supplier_id,
                notification_date=notification_date,
                status=status,
                error_message=error[:500] if error else None
            )
            session.add(record)
            session.commit()

    @staticmethod
    def format_daily_activity_summary(supplier_name: str, activity_date: date,
                                    opening_balance: float, closing_balance: float,
                                    activity: dict) -> str:
        eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(activity_date)
        eth_date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        lines = [
            f"📅 *Daily Credit Summary for(እለታዊ የዱቤ ማጠቃለያ ለ) {supplier_name}*",
            f"Date (ቀን): {eth_date_str}",
            "",
            f"*የቆየ ቀሪ:* ETB {opening_balance:,.2f}",
            "",
        ]
        if activity.get('purchase_count', 0) > 0:
            lines.append(f"🛒 *(አዲስ የገባ የዱቤ ግዥ):* {activity['purchase_count']} invoice(s)   →   + ETB {activity['total_purchases_amount']:,.2f}")
        if activity.get('payment_count', 0) > 0:
            lines.append(f"💰 *(የተከፈለ):* {activity['payment_count']} ክፍያዎች        →   - ETB {activity['total_payments_amount']:,.2f}")
        
        # New: adjustments (edits, discounts)
        if activity.get('adjustment_count', 0) > 0:
            net_adj = activity['net_adjustment']
            if net_adj > 0:
                lines.append(f"🔧 *(የዋጋ ማስተካከያ / Adjustments):* {activity['adjustment_count']} change(s)   →   + ETB {net_adj:,.2f}")
            elif net_adj < 0:
                lines.append(f"🔧 *(የዋጋ ማስተካከያ / Adjustments):* {activity['adjustment_count']} change(s)   →   - ETB {-net_adj:,.2f}")
            else:
                lines.append(f"🔧 *(የዋጋ ማስተካከያ / Adjustments):* {activity['adjustment_count']} change(s)   →   ETB 0.00")
        
        lines.append("")
        lines.append(f"*ጠቅላላ ቀሪ:* ETB {closing_balance:,.2f}\n\n")
        lines.append(f"*የአከፋፈል ሁኔታውን ለማየት ከታች የተላከውን pdf ይመልከቱ*\n")
        lines.append(f"*ያቀረቡትን እቃዎች ለማየት ወይም በፈልጉት ሰአት የአከፋፈል ሁኔታ ለማየት*\n")
        lines.append(f"*start menu -> supplier/አቅራቢ -> credit item history ወይም credit payment history ይንኩ፡፡*\n\n")
        lines.append(f"*==================================================*\n\n")
        lines.append(f"*developed by: Megazen Systems*\n")
        lines.append(f"contact us: @Megazenapp/ +251974250852")
        return "\n".join(lines)
    
    def get_credit_purchases_by_ids(self, purchase_ids: List[int]) -> list:
        with get_session() as session:
            purchases = session.query(Purchase).options(
                joinedload(Purchase.supplier),
                joinedload(Purchase.payment_terms),
                joinedload(Purchase.batches).joinedload(ProductBatch.product)
            ).filter(
                Purchase.id.in_(purchase_ids),
                Purchase.is_deleted == False,
                or_(
                    Purchase.is_credit_sale == True,
                    Purchase.payment_terms.any(
                        PurchasePaymentTerm.payment_status.in_([PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL])
                    )
                )
            ).order_by(Purchase.created_at.desc()).all()

            result = []
            for purchase in purchases:
                term = next(
                    (pt for pt in purchase.payment_terms if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]),
                    None
                )
                if not term and purchase.payment_terms:
                    term = purchase.payment_terms[0]
                if not term:
                    continue

                # --- FIX: direct calculation from batches ---
                true_total = 0.0
                if purchase.batches:
                    for batch in purchase.batches:
                        if batch.is_deleted:
                            continue
                        product = batch.product
                        dozen = product.dozen if product and hasattr(product, 'dozen') else 1
                        true_total += batch.quantity * batch.cost_price * dozen
                if true_total == 0.0 and purchase.items_data:
                    for item in purchase.items_data:
                        qty = item.get('quantity', 0)
                        cost = item.get('cost_price', 0.0)
                        dozen = item.get('dozen', 1)
                        true_total += qty * cost * dozen
                # --------------------------------------------

                result.append({
                    'purchase_id': purchase.id,
                    'purchase_date': purchase.purchase_date,
                    'total_amount': true_total,
                    'paid_amount': term.paid_amount,
                    'remaining': true_total - term.paid_amount,
                    'status': term.payment_status.value.capitalize(),
                    'payment_term_id': term.id,
                })
            return result