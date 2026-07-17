#!/usr/bin/env python3

from models.product_batch import ProductBatch
from models.batch_transaction import BatchTransaction, TransactionType
from models.new_product import ProfessionalProduct
from models.purchase import Purchase
from models.purchase_payment_term import PurchasePaymentTerm, PaymentStatusEnum
from models.bank_transactions import BankTransaction, TransactionDirectionEnum, PaymentMethodEnum
from models.supplier_credit_ledger import SupplierCreditLedger
from services.bank_transaction_service import BankTransactionService
from services.base_service import BaseService, get_session
from services.purchase_service import PurchaseService
from services.supplier_credit_ledger_service import SupplierCreditLedgerService
from ui.components.ethiopian_date import EthiopianDateConverter
import logging
from typing import Optional
from datetime import datetime, date
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

class ProductBatchService(BaseService[ProductBatch]):

    def __init__(self):
        super().__init__(ProductBatch)
        self.purchase_service = PurchaseService()
        self.bank_transaction_service = BankTransactionService()
        self.ledger_service = SupplierCreditLedgerService()

    def delete_batch_cascade(self, batch_id: int) -> bool:
        """Soft delete a batch and its transactions, then update product totals."""
        with get_session() as session:
            try:
                batch = session.query(ProductBatch).filter(
                    ProductBatch.id == batch_id,
                    ProductBatch.is_deleted == False
                ).first()
                if not batch:
                    return False

                purchase_id = batch.purchase_id
                product = batch.product
                dozen = product.dozen if product else 1
                value = batch.quantity * batch.cost_price * dozen

                # Human-readable details
                product_name = product.name if product else "Unknown"
                purchase = session.query(Purchase).get(purchase_id) if purchase_id else None
                if purchase and purchase.purchase_date:
                    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(purchase.purchase_date)
                    purchase_date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
                else:
                    purchase_date_str = "N/A"

                # ✅ Ledger: Reverse the entire batch value if it's part of a purchase
                if purchase and purchase.supplier_id:
                    self.ledger_service.add_entry(
                        session=session,
                        supplier_id=purchase.supplier_id,
                        entry_date=date.today(),
                        entry_type='adjustment',
                        description=f"Deleted batch: Product \"{product_name}\" "
                                    f"(Purchase {purchase_date_str}) value ${value:,.2f}",
                        debit=0.0,
                        credit=value,
                        purchase_id=purchase.id,
                        batch_id=batch.id
                    )

                batch.is_deleted = True

                session.query(BatchTransaction).filter(
                    BatchTransaction.batch_id == batch_id,
                    BatchTransaction.is_deleted == False
                ).update({"is_deleted": True}, synchronize_session=False)

                session.flush()

                if product:
                    product.update_totals()

                if purchase_id:
                    self.purchase_service.recalc_purchase_total(purchase_id, session)
                    remaining = session.query(ProductBatch).filter(
                        ProductBatch.purchase_id == purchase_id,
                        ProductBatch.is_deleted == False
                    ).count()
                    if remaining == 0:
                        self.purchase_service.delete_purchase_cascade_in_session(session, purchase_id)

                session.commit()
                return True

            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting batch {batch_id}: {e}")
                return False

    def count_by_product(self, product_id: int) -> int:
        """Return the number of non-deleted batches for a given product."""
        with get_session() as session:
            return session.query(ProductBatch).filter(
                ProductBatch.product_id == product_id,
                ProductBatch.is_deleted == False
            ).count()

    def report_damage(self, batch_id: int, quantity: int, notes: str = "", user_id=None) -> bool:
        """
        Reduce batch available quantity and create a DAMAGE transaction.
        Returns True if successful, False otherwise.
        """
        with get_session() as session:
            try:
                batch = session.query(ProductBatch).filter(
                    ProductBatch.id == batch_id,
                    ProductBatch.is_deleted == False
                ).first()
                if not batch:
                    logger.warning(f"Batch {batch_id} not found")
                    return False

                if quantity <= 0 or quantity > batch.available_quantity:
                    logger.warning(f"Invalid damage quantity {quantity} for batch {batch_id}")
                    return False

                batch.available_quantity -= quantity

                transaction = BatchTransaction(
                    batch_id=batch_id,
                    quantity=quantity,
                    transaction_type=TransactionType.DAMAGE,
                    notes=notes,
                    user_id=user_id
                )
                session.add(transaction)

                product = session.query(ProfessionalProduct).get(batch.product_id)
                if product:
                    product.update_totals()

                session.commit()
                logger.info(f"Damage reported: batch {batch_id}, quantity {quantity}")
                return True

            except Exception as e:
                session.rollback()
                logger.error(f"Error reporting damage for batch {batch_id}: {e}")
                return False

    def update(self, id: int, data: dict) -> Optional[ProductBatch]:
        with get_session() as session:
            try:
                batch = session.query(ProductBatch).filter(
                    ProductBatch.id == id,
                    ProductBatch.is_deleted == False
                ).first()
                if not batch:
                    return None

                purchase_id = batch.purchase_id

                for key, value in data.items():
                    setattr(batch, key, value)

                session.flush()

                product = session.query(ProfessionalProduct).get(batch.product_id)
                if product:
                    product.update_totals()

                if purchase_id:
                    success = self.purchase_service.recalc_purchase_total(purchase_id, session)
                    if not success:
                        raise Exception("Failed to recalc purchase total")

                session.commit()
                return batch

            except Exception as e:
                session.rollback()
                logger.error(f"Error updating batch {id}: {e}")
                return None

    def update_batch_with_purchase_details(self, batch_id: int, data: dict) -> Optional[ProductBatch]:
        with get_session() as session:
            try:
                batch = session.query(ProductBatch).options(
                    joinedload(ProductBatch.product),
                    joinedload(ProductBatch.purchase).joinedload(Purchase.supplier),
                    joinedload(ProductBatch.purchase).joinedload(Purchase.payment_terms).joinedload(PurchasePaymentTerm.purchase_payment_transaction)
                ).filter(
                    ProductBatch.id == batch_id,
                    ProductBatch.is_deleted == False
                ).first()
                if not batch:
                    return None

                purchase = batch.purchase
                if not purchase:
                    raise Exception("Batch has no associated purchase")

                # Store old values
                old_quantity = batch.quantity
                old_cost_price = batch.cost_price
                product = batch.product
                dozen = product.dozen if product else 1
                old_value = old_quantity * old_cost_price * dozen

                # Ethiopian date string
                product_name = product.name if product else "Unknown"
                if purchase.purchase_date:
                    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(purchase.purchase_date)
                    purchase_date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
                else:
                    purchase_date_str = "N/A"

                # 1. Update batch fields
                if 'batch' in data:
                    for key, value in data['batch'].items():
                        setattr(batch, key, value)

                # 2. Create adjustment transaction if available quantity changed
                if 'adjustment' in data:
                    adj = data['adjustment']
                    delta = adj['delta']
                    adjustment_tx = BatchTransaction(
                        batch_id=batch.id,
                        quantity=delta,
                        transaction_type=TransactionType.ADJUSTMENT,
                        notes=adj.get('notes', f"Manual adjustment: {adj['old_quantity']} → {adj['new_quantity']}"),
                        user_id=None,
                        created_at=datetime.now(),
                        last_modified=datetime.now()
                    )
                    session.add(adjustment_tx)

                session.flush()

                new_quantity = batch.quantity
                new_cost_price = batch.cost_price
                new_value = new_quantity * new_cost_price * dozen

                # ✅ Ledger: Record adjustment if value changed
                if new_value != old_value:
                    # Reverse old
                    self.ledger_service.add_entry(
                        session=session,
                        supplier_id=purchase.supplier_id,
                        entry_date=date.today(),
                        entry_type='adjustment',
                        description=f"Edit batch: Product \"{product_name}\" "
                                    f"(Purchase {purchase_date_str}) reverse old (qty {old_quantity}, cost ${old_cost_price:.2f})",
                        debit=0.0,
                        credit=old_value,
                        purchase_id=purchase.id,
                        batch_id=batch.id
                    )
                    # Record new
                    self.ledger_service.add_entry(
                        session=session,
                        supplier_id=purchase.supplier_id,
                        entry_date=date.today(),
                        entry_type='adjustment',
                        description=f"Edit batch: Product \"{product_name}\" "
                                    f"(Purchase {purchase_date_str}) new (qty {new_quantity}, cost ${new_cost_price:.2f})",
                        debit=new_value,
                        credit=0.0,
                        purchase_id=purchase.id,
                        batch_id=batch.id
                    )

                # 3. Update purchase supplier
                if 'purchase' in data and 'supplier_id' in data['purchase']:
                    new_supplier_id = data['purchase']['supplier_id']
                    if new_supplier_id != purchase.supplier_id:
                        purchase.supplier_id = new_supplier_id
                        # ✅ Move all ledger entries for this purchase to the new supplier
                        session.query(SupplierCreditLedger).filter(
                            SupplierCreditLedger.purchase_id == purchase.id,
                            SupplierCreditLedger.is_deleted == False
                        ).update({"supplier_id": new_supplier_id}, synchronize_session=False)

                # 4. Handle payment updates if purchase is paid
                payment_term = purchase.payment_terms[0] if purchase.payment_terms else None
                payment_tx = None
                if payment_term and payment_term.payment_status == PaymentStatusEnum.PAID:
                    payment_tx = payment_term.purchase_payment_transaction[0] if payment_term.purchase_payment_transaction else None

                affected_accounts = set()
                if payment_tx and 'payment' in data:
                    old_bank_account_id = payment_tx.bank_account_id
                    new_bank_account_id = data['payment'].get('bank_account_id')
                    new_payment_date = data['payment'].get('payment_date')

                    if new_bank_account_id is not None:
                        payment_tx.bank_account_id = new_bank_account_id
                    if new_payment_date is not None:
                        payment_tx.payment_date = new_payment_date

                    bank_tx = session.query(BankTransaction).filter(
                        BankTransaction.purchase_payment_term_id == payment_term.id,
                        BankTransaction.is_deleted == False
                    ).first()

                    if bank_tx:
                        if old_bank_account_id != new_bank_account_id:
                            bank_tx.is_deleted = True
                            new_bank_tx = BankTransaction(
                                bank_account_id=new_bank_account_id,
                                transaction_date=payment_tx.payment_date,
                                direction=TransactionDirectionEnum.DEBIT,
                                amount=payment_tx.amount,
                                payment_method=PaymentMethodEnum.TRANSFER,
                                description=f"Payment for purchase #{purchase.id}",
                                reference_number=None,
                                purchase_payment_term_id=payment_term.id,
                                recorded_by_user_id=payment_tx.user_id
                            )
                            session.add(new_bank_tx)
                            session.flush()
                            affected_accounts = {old_bank_account_id, new_bank_account_id}
                        else:
                            if new_payment_date is not None and new_payment_date != bank_tx.transaction_date:
                                bank_tx.transaction_date = new_payment_date
                            affected_accounts = {bank_tx.bank_account_id}

                session.flush()

                # 5. Recalculate purchase total
                self.purchase_service.recalc_purchase_total(purchase.id, session)

                # 6. Sync payment amounts
                if payment_term:
                    session.refresh(payment_term)
                    if payment_tx and payment_tx.amount != payment_term.paid_amount:
                        old_amount = payment_tx.amount
                        payment_tx.amount = payment_term.paid_amount
                        logger.info(f"Adjusted payment_tx #{payment_tx.id} amount {old_amount} → {payment_term.paid_amount}")

                        bank_tx = session.query(BankTransaction).filter(
                            BankTransaction.purchase_payment_term_id == payment_term.id,
                            BankTransaction.is_deleted == False
                        ).first()
                        if bank_tx:
                            bank_tx.amount = payment_term.paid_amount
                            affected_accounts.add(bank_tx.bank_account_id)

                # 7. Update product totals
                if product:
                    product.update_totals()
                    session.add(product)

                # 8. Recalculate bank balances
                for acc_id in affected_accounts:
                    self.bank_transaction_service.recalculate_balances_for_account(session, acc_id)

                session.commit()
                return batch

            except Exception as e:
                session.rollback()
                logger.error(f"Error updating batch with purchase details: {e}", exc_info=True)
                return None
    
    def split_batch_for_discount(
        self,
        batch_id: int,
        new_cost_price: float,
        note: str = "",
        user_id: int = None
    ) -> Optional[ProductBatch]:
        from models.batch_transaction import BatchTransaction, TransactionType
        from models.purchase import Purchase
        from models.new_product import ProfessionalProduct
        from services.purchase_service import PurchaseService
        from datetime import datetime

        with get_session() as session:
            try:
                batch = session.query(ProductBatch).options(
                    joinedload(ProductBatch.product),
                    joinedload(ProductBatch.purchase)
                ).filter(
                    ProductBatch.id == batch_id,
                    ProductBatch.is_deleted == False
                ).first()

                if not batch:
                    logger.warning(f"Batch {batch_id} not found")
                    return None

                if batch.available_quantity <= 0:
                    raise ValueError("No remaining quantity to discount.")

                product = batch.product
                dozen = product.dozen if product else 1
                old_cost_price = batch.cost_price

                # Human-readable details
                product_name = product.name if product else "Unknown"
                purchase = batch.purchase
                if purchase and purchase.purchase_date:
                    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(purchase.purchase_date)
                    purchase_date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
                else:
                    purchase_date_str = "N/A"

                # Case 1: nothing sold – just update cost_price
                if batch.quantity == batch.available_quantity:
                    old_value = batch.quantity * old_cost_price * dozen
                    batch.cost_price = new_cost_price
                    new_value = batch.quantity * new_cost_price * dozen

                    tx = BatchTransaction(
                        batch_id=batch.id,
                        quantity=0,
                        transaction_type=TransactionType.ADJUSTMENT,
                        notes=f"Discount applied: new unit price ${new_cost_price:.2f}. {note}",
                        user_id=user_id
                    )
                    session.add(tx)

                    if batch.product:
                        batch.product.update_totals()

                    # ✅ Ledger: Discount adjustment (full batch)
                    if batch.purchase and batch.purchase.supplier_id:
                        self.ledger_service.add_entry(
                            session=session,
                            supplier_id=batch.purchase.supplier_id,
                            entry_date=date.today(),
                            entry_type='discount',
                            description=f"Discount batch: Product \"{product_name}\" "
                                        f"(Purchase {purchase_date_str}) reverse old value @ ${old_cost_price:.2f}",
                            debit=0.0,
                            credit=old_value,
                            purchase_id=batch.purchase_id,
                            batch_id=batch.id
                        )
                        self.ledger_service.add_entry(
                            session=session,
                            supplier_id=batch.purchase.supplier_id,
                            entry_date=date.today(),
                            entry_type='discount',
                            description=f"Discount batch: Product \"{product_name}\" "
                                        f"(Purchase {purchase_date_str}) new value @ ${new_cost_price:.2f}",
                            debit=new_value,
                            credit=0.0,
                            purchase_id=batch.purchase_id,
                            batch_id=batch.id
                        )

                    self.purchase_service.recalc_purchase_total(batch.purchase_id, session, user_id=user_id)

                    session.commit()
                    return batch

                # Case 2: sold portion exists – split
                sold_qty = batch.quantity - batch.available_quantity
                remaining_qty = batch.available_quantity

                # Old value of remaining portion
                old_remaining_value = remaining_qty * old_cost_price * dozen

                new_batch = ProductBatch(
                    product_id=batch.product_id,
                    purchase_id=batch.purchase_id,
                    quantity=remaining_qty,
                    available_quantity=remaining_qty,
                    cost_price=new_cost_price,
                    created_at=datetime.now(),
                    last_modified=datetime.now()
                )
                session.add(new_batch)
                session.flush()

                batch.quantity = sold_qty
                batch.available_quantity = 0

                # New value of remaining portion
                new_remaining_value = remaining_qty * new_cost_price * dozen

                tx_orig = BatchTransaction(
                    batch_id=batch.id,
                    quantity=-remaining_qty,
                    transaction_type=TransactionType.ADJUSTMENT,
                    notes=f"Batch split: remaining stock ({remaining_qty} units) moved to new batch at discounted price ${new_cost_price:.2f}. {note}",
                    user_id=user_id
                )
                session.add(tx_orig)

                tx_new = BatchTransaction(
                    batch_id=new_batch.id,
                    quantity=remaining_qty,
                    transaction_type=TransactionType.STOCK_IN,
                    notes=f"Created from batch #{batch.id} split: discounted price ${new_cost_price:.2f}. {note}",
                    user_id=user_id
                )
                session.add(tx_new)

                if batch.product:
                    batch.product.update_totals()

                # ✅ Ledger: Discount adjustment for the unsold portion
                if batch.purchase and batch.purchase.supplier_id:
                    self.ledger_service.add_entry(
                        session=session,
                        supplier_id=batch.purchase.supplier_id,
                        entry_date=date.today(),
                        entry_type='discount',
                        description=f"Discount split batch: Product \"{product_name}\" "
                                    f"(Purchase {purchase_date_str}) reverse old value of {remaining_qty} unsold units @ ${old_cost_price:.2f}",
                        debit=0.0,
                        credit=old_remaining_value,
                        purchase_id=batch.purchase_id,
                        batch_id=batch.id
                    )
                    self.ledger_service.add_entry(
                        session=session,
                        supplier_id=batch.purchase.supplier_id,
                        entry_date=date.today(),
                        entry_type='discount',
                        description=f"Discount split batch: Product \"{product_name}\" "
                                    f"(Purchase {purchase_date_str}) new value of {remaining_qty} units @ ${new_cost_price:.2f}",
                        debit=new_remaining_value,
                        credit=0.0,
                        purchase_id=batch.purchase_id,
                        batch_id=new_batch.id
                    )

                self.purchase_service.recalc_purchase_total(batch.purchase_id, session, user_id=user_id)

                session.commit()
                return new_batch

            except Exception as e:
                session.rollback()
                logger.exception(f"Error splitting batch {batch_id}: {e}")
                return None

    def get_batch_with_purchase(self, batch_id: int) -> Optional[ProductBatch]:
        with get_session() as session:
            return session.query(ProductBatch).options(
                joinedload(ProductBatch.product),
                joinedload(ProductBatch.purchase).joinedload(Purchase.supplier),
                joinedload(ProductBatch.purchase).joinedload(Purchase.payment_terms).joinedload(PurchasePaymentTerm.purchase_payment_transaction)
            ).filter(
                ProductBatch.id == batch_id,
                ProductBatch.is_deleted == False
            ).first()