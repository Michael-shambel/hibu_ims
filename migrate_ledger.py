#!/usr/bin/env python3
"""Fix purchase #48 payment transactions - reduce by 10,800 to match batch total."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.base_service import BaseModel, get_session

import models.auth_user
import models.customers
import models.supplier
import models.supplier_daily_notification
import models.purchase
import models.purchase_payment_term
import models.purchase_payment_transaction
import models.product_batch
import models.new_product
import models.new_sales
import models.bank_transactions
import models.bank_account
import models.expense

#!/usr/bin/env python3
"""
Exact migration: use the OLD combined history logic to populate
supplier_credit_ledger with exactly the same entries as before.
"""
from datetime import datetime, date
from services.base_service import get_session
from models.purchase import Purchase
from models.purchase_payment_term import PurchasePaymentTerm, PaymentStatusEnum
from models.purchase_payment_transaction import PurchasePaymentTransaction, PaymentMethodEnum
from models.bank_transactions import BankTransaction
from models.supplier_credit_ledger import SupplierCreditLedger
from models.product_batch import ProductBatch
from models.new_product import ProfessionalProduct
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- OLD get_supplier_combined_history (copy-pasted from your original PurchaseService) ----
def old_combined_history(supplier_id):
    """Return the exact same list of dicts as the old method."""
    with get_session() as session:
        combined = []

        # Credit purchases
        purchases = session.query(Purchase).options(
            joinedload(Purchase.payment_terms),
            joinedload(Purchase.batches).joinedload(ProductBatch.product)
        ).filter(
            Purchase.supplier_id == supplier_id,
            Purchase.is_deleted == False,
            Purchase.is_credit_sale == True
        ).all()

        for purchase in purchases:
            term = purchase.payment_terms[0] if purchase.payment_terms else None
            if not term:
                continue
            # True total from batches or items_data
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

            combined.append({
                'date': purchase.purchase_date or purchase.created_at.date(),
                'credit_amount': true_total,
                'debit_amount': 0.0,
                'type': 'credit_purchase',
                'notes': f"Credit purchase #{purchase.id}",
                'bank_transaction_id': None,
                'bank_account_display': 'New Credit',
                'all_transaction_ids': [],
            })

        # Payments grouped by bank_transaction_id
        stmt = select(PurchasePaymentTransaction.bank_transaction_id).distinct().join(
            PurchasePaymentTerm,
            PurchasePaymentTransaction.purchase_payments_term_id == PurchasePaymentTerm.id
        ).join(
            Purchase,
            PurchasePaymentTerm.purchase_id == Purchase.id
        ).where(
            Purchase.supplier_id == supplier_id,
            Purchase.is_deleted == False,
            PurchasePaymentTransaction.bank_transaction_id != None,
            PurchasePaymentTransaction.is_deleted == False
        )

        bank_txs = session.query(BankTransaction).filter(
            BankTransaction.id.in_(stmt),
            BankTransaction.is_deleted == False
        ).order_by(BankTransaction.transaction_date.asc()).all()

        for bt in bank_txs:
            allocs = session.query(PurchasePaymentTransaction).join(
                PurchasePaymentTerm,
                PurchasePaymentTransaction.purchase_payments_term_id == PurchasePaymentTerm.id
            ).join(
                Purchase,
                PurchasePaymentTerm.purchase_id == Purchase.id
            ).filter(
                Purchase.supplier_id == supplier_id,
                PurchasePaymentTransaction.bank_transaction_id == bt.id,
                PurchasePaymentTransaction.is_deleted == False
            ).all()

            total_debit = sum(a.amount for a in allocs)
            notes_set = set(a.notes for a in allocs if a.notes)
            notes = '; '.join(filter(None, notes_set)) if notes_set else bt.description or 'Payment'
            transaction_ids = [a.id for a in allocs]

            bank_display = "N/A"
            if bt.bank_account:
                bank_display = f"{bt.bank_account.bank_name} - {bt.bank_account.account_name}"

            combined.append({
                'date': bt.transaction_date,
                'credit_amount': 0.0,
                'debit_amount': total_debit,
                'type': 'payment',
                'notes': notes,
                'bank_transaction_id': bt.id,
                'bank_account_display': bank_display,
                'all_transaction_ids': transaction_ids,
            })

        # Direct surplus payments (no bank transaction)
        direct_payments = session.query(PurchasePaymentTransaction).join(
            PurchasePaymentTerm,
            PurchasePaymentTransaction.purchase_payments_term_id == PurchasePaymentTerm.id
        ).join(
            Purchase,
            PurchasePaymentTerm.purchase_id == Purchase.id
        ).filter(
            Purchase.supplier_id == supplier_id,
            Purchase.is_deleted == False,
            PurchasePaymentTransaction.is_deleted == False,
            PurchasePaymentTransaction.payment_method == PaymentMethodEnum.SURPLUS
        ).order_by(PurchasePaymentTransaction.payment_date.asc()).all()

        for pt in direct_payments:
            combined.append({
                'date': pt.payment_date,
                'credit_amount': 0.0,
                'debit_amount': pt.amount,
                'type': 'payment',
                'notes': pt.notes or "Surplus allocation",
                'bank_transaction_id': None,
                'bank_account_display': 'N/A',
                'all_transaction_ids': [pt.id],
            })

        # Sort and calculate balance (though we don't need it for migration)
        combined.sort(key=lambda x: x['date'])
        balance = 0.0
        for tx in combined:
            tx['balance_before'] = balance
            if tx['type'] == 'credit_purchase':
                balance += tx['credit_amount']
            else:
                balance -= tx['debit_amount']
            tx['balance_after'] = balance

        return combined

# ---- End of old logic ----

def migrate_from_old_history():
    """Populate supplier_credit_ledger using the old history for every supplier."""
    with get_session() as session:
        # Get all distinct supplier IDs from purchases
        supplier_ids = session.query(Purchase.supplier_id).filter(
            Purchase.is_deleted == False
        ).distinct().all()
        supplier_ids = [sid for (sid,) in supplier_ids]

        total_entries = 0
        for sid in supplier_ids:
            logger.info(f"Processing supplier {sid}...")
            history = old_combined_history(sid)
            for entry in history:
                # Determine entry_type and amounts
                if entry['type'] == 'credit_purchase':
                    entry_type = 'purchase'
                    debit = entry['credit_amount']
                    credit = 0.0
                else:  # payment
                    entry_type = 'payment'
                    debit = 0.0
                    credit = entry['debit_amount']

                # Build description
                description = entry['notes']
                bank_tx_id = entry.get('bank_transaction_id')
                purchase_id = None  # We don't have a direct purchase_id for payments, but we can derive it?
                # For purchases, we can parse from notes "Credit purchase #<id>"
                if entry_type == 'purchase' and description.startswith('Credit purchase #'):
                    try:
                        purchase_id = int(description.split('#')[1].split()[0])
                    except:
                        pass
                # For payments, we could store bank_transaction_id
                payment_tx_id = None
                all_ids = entry.get('all_transaction_ids', [])
                if all_ids:
                    payment_tx_id = all_ids[0] if all_ids else None

                # Skip if duplicate (by bank_transaction_id for payments, purchase_id for purchases)
                if entry_type == 'purchase' and purchase_id:
                    exists = session.query(SupplierCreditLedger).filter(
                        SupplierCreditLedger.purchase_id == purchase_id,
                        SupplierCreditLedger.entry_type == 'purchase',
                        SupplierCreditLedger.is_deleted == False
                    ).first()
                elif bank_tx_id:
                    exists = session.query(SupplierCreditLedger).filter(
                        SupplierCreditLedger.bank_transaction_id == bank_tx_id,
                        SupplierCreditLedger.entry_type == 'payment',
                        SupplierCreditLedger.is_deleted == False
                    ).first()
                else:
                    exists = False

                if exists:
                    continue

                ledger_entry = SupplierCreditLedger(
                    supplier_id=sid,
                    purchase_id=purchase_id,
                    bank_transaction_id=bank_tx_id,
                    payment_transaction_id=payment_tx_id,
                    entry_date=entry['date'],
                    entry_type=entry_type,
                    description=description,
                    debit=debit,
                    credit=credit,
                    created_at=datetime.now(),
                    last_modified=datetime.now(),
                    is_deleted=False
                )
                session.add(ledger_entry)
                total_entries += 1

        session.commit()
        logger.info(f"✅ Migration complete. Total entries added: {total_entries}")

if __name__ == "__main__":
    print("Building exact ledger from old payment history...")
    migrate_from_old_history()
    print("Done. Ledger now matches the old history exactly.")