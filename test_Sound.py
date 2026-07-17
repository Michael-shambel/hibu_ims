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
Inspect purchase #121, show its supplier, and list all suppliers
to reveal the hard-coded index bug.
"""

from services.purchase_service import PurchaseService
from services.supplier_service import SupplierService
from services.base_service import get_session
from models.purchase import Purchase
from models.purchase_payment_term import PurchasePaymentTerm
from models.supplier_credit_ledger import SupplierCreditLedger
from models.supplier import Supplier
from sqlalchemy.orm import joinedload

PURCHASE_ID = 121

def main():
    print(f"\n🔍 Inspecting Purchase #{PURCHASE_ID}\n")

    purchase_service = PurchaseService()
    supplier_service = SupplierService()

    # --- FIX: Fetch purchase with supplier eagerly loaded ---
    with get_session() as session:
        purchase = session.query(Purchase).options(
            joinedload(Purchase.supplier),
            joinedload(Purchase.payment_terms),
            joinedload(Purchase.batches).joinedload(ProductBatch.product)
        ).filter(
            Purchase.id == PURCHASE_ID,
            Purchase.is_deleted == False
        ).first()

    if not purchase:
        print(f"❌ Purchase #{PURCHASE_ID} not found or deleted.")
        return

    # 2. Show supplier info (now safely accessible)
    supplier = purchase.supplier
    supplier_name = supplier.supplier_name if supplier else "N/A"
    supplier_id = supplier.id if supplier else None
    print(f"📌 Purchase #{PURCHASE_ID} is linked to supplier:")
    print(f"   ID: {supplier_id} | Name: {supplier_name}\n")

    # 3. Show all suppliers in order (as they appear in the combo box)
    print("📋 All suppliers (ordered by ID, which is the order in the combo):")
    all_suppliers = supplier_service.get_all()
    for idx, s in enumerate(all_suppliers):
        print(f"   Index {idx}: ID={s.id}, Name={s.supplier_name}")

    # Show which supplier is at index 9 (if any)
    if len(all_suppliers) > 9:
        s9 = all_suppliers[9]
        print(f"\n⚠️ Index 9 is: ID={s9.id}, Name={s9.supplier_name}")
        if s9.id == supplier_id:
            print("   → This matches the purchase's supplier! (The hard‑coded index 9 is the cause.)")
        else:
            print("   → The purchase supplier does NOT match index 9 – something else is wrong.")
    else:
        print("\n⚠️ Fewer than 10 suppliers, so index 9 doesn't exist – but the bug code would skip forcing.")

    # 4. Show true total (from batches/items)
    true_total = purchase_service.get_purchase_true_total(PURCHASE_ID)
    print(f"\n💰 True total (from batches/items): ${true_total:,.2f}")

    # 5. Payment term details
    term = purchase.payment_terms[0] if purchase.payment_terms else None
    if term:
        print(f"💳 Payment status: {term.payment_status.value if term.payment_status else 'Unknown'}")
        print(f"   Paid amount: ${term.paid_amount:,.2f}")
        print(f"   Remaining: ${term.total_amount - term.paid_amount:,.2f}")

    # 6. Items (batches or items_data)
    if purchase.batches:
        print("\n📦 Batches:")
        for batch in purchase.batches:
            if batch.is_deleted:
                continue
            product = batch.product
            product_name = product.name if product else "Unknown"
            dozen = product.dozen if product and hasattr(product, 'dozen') else 1
            print(f"  - {product_name}: qty={batch.quantity}, cost={batch.cost_price}, dozen={dozen}, total={batch.quantity * batch.cost_price * dozen:.2f}")
    elif purchase.items_data:
        print("\n📋 Items from credit purchase (items_data):")
        for item in purchase.items_data:
            print(f"  - {item.get('name')}: qty={item.get('quantity')}, cost={item.get('cost_price')}, dozen={item.get('dozen', 1)}")

    # 7. Ledger entries (separate session – fine because we only read)
    with get_session() as session:
        ledger = session.query(SupplierCreditLedger).filter(
            SupplierCreditLedger.purchase_id == PURCHASE_ID,
            SupplierCreditLedger.is_deleted == False
        ).order_by(SupplierCreditLedger.entry_date).all()

    if ledger:
        print("\n📘 Supplier Credit Ledger entries:")
        for entry in ledger:
            print(f"  - {entry.entry_date}: {entry.entry_type} | debit={entry.debit}, credit={entry.credit} | {entry.description}")
    else:
        print("\n⚠️ No ledger entries found for this purchase.")

if __name__ == "__main__":
    main()