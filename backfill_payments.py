#!/usr/bin/env python3
"""
Simplified backfill script for purchase payment transactions.
This script works without loading complex relationships.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.base_service import get_session
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill_payment_transactions():
    """Create BankTransaction records for old PurchasePaymentTransaction rows."""
    
    with get_session() as session:
        # Raw SQL approach to avoid ORM relationship issues
        # First, get all orphan transactions directly from the table
        result = session.execute(
            text("""
                SELECT 
                    ppt.id,
                    ppt.payment_date,
                    ppt.amount,
                    ppt.bank_account_id,
                    ppt.user_id,
                    ppt.notes,
                    ppt.purchase_payments_term_id
                FROM purchase_payment_transaction ppt
                WHERE ppt.bank_transaction_id IS NULL 
                    AND ppt.is_deleted = 0
            """)
        )
        
        orphan_transactions = list(result)
        
        if not orphan_transactions:
            logger.info("No orphan transactions found. Backfill not needed.")
            return
        
        # Group them by (payment_date, bank_account_id, user_id, notes)
        groups = {}
        for tx in orphan_transactions:
            key = (tx.payment_date, tx.bank_account_id, tx.user_id, tx.notes or '')
            if key not in groups:
                groups[key] = []
            groups[key].append(tx)
        
        logger.info(f"Found {len(orphan_transactions)} transactions, grouped into {len(groups)} potential payment groups.")
        
        created_count = 0
        linked_count = 0
        
        for (pay_date, bank_acc_id, user_id, notes), tx_list in groups.items():
            total_amount = sum(tx.amount for tx in tx_list)
            
            # Insert one BankTransaction for this group
            # Use 'DEBIT' (uppercase) for the enum name, not 'debit'
            session.execute(
                text("""
                    INSERT INTO bank_transactions (
                        bank_account_id,
                        transaction_date,
                        direction,
                        amount,
                        balance_after,
                        payment_method,
                        description,
                        recorded_by_user_id,
                        is_deleted,
                        created_at,
                        last_modified
                    ) VALUES (
                        :bank_account_id,
                        :transaction_date,
                        'DEBIT',
                        :amount,
                        0.0,
                        'transfer',
                        :description,
                        :user_id,
                        0,
                        :created_at,
                        :last_modified
                    )
                """),
                {
                    'bank_account_id': bank_acc_id,
                    'transaction_date': pay_date,
                    'amount': total_amount,
                    'description': f'Backfilled payment (grouped) - {notes}' if notes else 'Backfilled payment (grouped)',
                    'user_id': user_id,
                    'created_at': date.today(),
                    'last_modified': date.today()
                }
            )
            
            # Get the last inserted bank_transaction_id
            bt_result = session.execute(text("SELECT last_insert_rowid()"))
            bank_tx_id = bt_result.scalar()
            
            # Update all related payment transactions with this bank_transaction_id
            for tx in tx_list:
                session.execute(
                    text("""
                        UPDATE purchase_payment_transaction
                        SET bank_transaction_id = :bank_tx_id
                        WHERE id = :tx_id
                    """),
                    {'bank_tx_id': bank_tx_id, 'tx_id': tx.id}
                )
            
            created_count += 1
            linked_count += len(tx_list)
            logger.info(f"Created bank transaction {bank_tx_id} for {len(tx_list)} payments totaling ${total_amount:,.2f}")
        
        session.commit()
        logger.info(f"Backfill complete: Created {created_count} BankTransaction records, linked {linked_count} PurchasePaymentTransaction records.")

if __name__ == "__main__":
    backfill_payment_transactions()