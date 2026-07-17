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
Merge duplicate suppliers:
- Lists all suppliers
- Asks for two IDs
- Moves all purchases and ledger entries to the primary
- Soft-deletes the duplicate
"""
import sys
from services.base_service import get_session
from models.supplier import Supplier
from models.purchase import Purchase
from models.supplier_credit_ledger import SupplierCreditLedger
from models.supplier_daily_notification import SupplierDailyNotification
from models.purchase_payment_term import PurchasePaymentTerm
from models.purchase_payment_transaction import PurchasePaymentTransaction

def list_suppliers(session):
    suppliers = session.query(Supplier).filter(Supplier.is_deleted == False).order_by(Supplier.supplier_name).all()
    print("\nActive Suppliers:")
    print(f"{'ID':<5} {'Name':<30} {'Phone':<20}")
    print("-" * 55)
    for s in suppliers:
        print(f"{s.id:<5} {s.supplier_name[:29]:<30} {s.contact_phone or '':<20}")
    print()

def confirm(prompt):
    while True:
        resp = input(prompt + " (y/n): ").strip().lower()
        if resp in ('y', 'yes'):
            return True
        if resp in ('n', 'no'):
            return False

def merge_suppliers(primary_id, duplicate_id):
    with get_session() as session:
        primary = session.query(Supplier).get(primary_id)
        duplicate = session.query(Supplier).get(duplicate_id)

        if not primary or primary.is_deleted:
            print(f"Primary supplier ID {primary_id} not found or is deleted.")
            return
        if not duplicate or duplicate.is_deleted:
            print(f"Duplicate supplier ID {duplicate_id} not found or is deleted.")
            return
        if primary.id == duplicate.id:
            print("Cannot merge the same supplier.")
            return

        # Count purchases and ledger entries
        purchases_count = session.query(Purchase).filter(
            Purchase.supplier_id == duplicate.id,
            Purchase.is_deleted == False
        ).count()

        ledger_count = session.query(SupplierCreditLedger).filter(
            SupplierCreditLedger.supplier_id == duplicate.id,
            SupplierCreditLedger.is_deleted == False
        ).count()

        print(f"\nSummary for duplicate supplier '{duplicate.supplier_name}' (ID {duplicate.id}):")
        print(f"  Purchases: {purchases_count}")
        print(f"  Ledger entries: {ledger_count}")
        print(f"Will be moved to primary supplier '{primary.supplier_name}' (ID {primary.id}).")

        if not confirm("\nProceed with merge?"):
            print("Merge cancelled.")
            return

        # Reassign purchases
        session.query(Purchase).filter(
            Purchase.supplier_id == duplicate.id,
            Purchase.is_deleted == False
        ).update({"supplier_id": primary.id}, synchronize_session=False)

        # Reassign ledger entries
        session.query(SupplierCreditLedger).filter(
            SupplierCreditLedger.supplier_id == duplicate.id,
            SupplierCreditLedger.is_deleted == False
        ).update({"supplier_id": primary.id}, synchronize_session=False)

        # Reassign daily notifications (if any)
        session.query(SupplierDailyNotification).filter(
            SupplierDailyNotification.supplier_id == duplicate.id
        ).update({"supplier_id": primary.id}, synchronize_session=False)

        # Soft-delete the duplicate supplier
        duplicate.is_deleted = True

        session.commit()
        print("Merge completed successfully.")
        print(f"All records from '{duplicate.supplier_name}' have been moved to '{primary.supplier_name}'.")
        print(f"Supplier '{duplicate.supplier_name}' has been marked as deleted.")

def main():
    with get_session() as session:
        list_suppliers(session)

    try:
        primary = int(input("Enter the primary supplier ID (to keep): "))
        duplicate = int(input("Enter the duplicate supplier ID (to merge): "))
    except ValueError:
        print("Invalid ID. Please enter numbers only.")
        return

    merge_suppliers(primary, duplicate)

if __name__ == "__main__":
    main()