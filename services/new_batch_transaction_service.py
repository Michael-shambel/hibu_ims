#!/usr/bin/env python3
import logging
from shlex import join
from unittest import result
from models.new_sales import ProfessionalSale
from services.base_service import BaseService, get_session
from models.batch_transaction import BatchTransaction, TransactionType
from models.new_sales import ProfessionalSale
from typing import List
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

class NewBachTransactionService(BaseService[BatchTransaction]):
    def __init__(self):
        super().__init__(BatchTransaction)

    def create_with_session(self, session, data: dict):
        obj = BatchTransaction(**data)
        session.add(obj)
        return obj
    
    def get_by_batch(self, batch_id: int) -> List[BatchTransaction]:
        """Return all transactions for a specific batch, ordered oldest first (for running balance)."""
        with get_session() as session:
            try:
                transactions = session.query(BatchTransaction).options(
                    joinedload(BatchTransaction.user)
                ).filter(
                    BatchTransaction.batch_id == batch_id,
                    BatchTransaction.is_deleted == False
                ).order_by(BatchTransaction.created_at.asc()).all()  # oldest first for correct balance

                result = []
                balance = 0

                for tx in transactions:
                    qty = tx.quantity
                    tx_type = tx.transaction_type.value if tx.transaction_type else None
                    tx_type_lower = tx_type.lower() if tx_type else ""

                    # Determine effect on running balance
                    if 'stock_in' in tx_type_lower or 'credit_stock' in tx_type_lower or 'received' in tx_type_lower:
                        balance += qty
                    elif 'sale' in tx_type_lower:
                        balance -= qty
                    elif 'adjustment' in tx_type_lower:
                        # qty is signed (positive for increase, negative for decrease)
                        balance += qty
                    else:
                        logger.warning(f"Unknown transaction type: {tx_type}")

                    # Prepare result item
                    item = {
                        'created_at': tx.created_at,
                        'type': tx_type,
                        'quantity': qty,
                        'running_balance': balance,
                        'customer_name': '',
                        'delivery_name': '',
                        'notes': tx.notes or '',
                    }

                    # Enrich with sale details if it's a sale transaction
                    if tx.transaction_type == TransactionType.SALE and tx.reference_number:
                        try:
                            sale_id = int(tx.reference_number)
                            sale = session.query(ProfessionalSale).options(
                                joinedload(ProfessionalSale.customer)
                            ).filter(
                                ProfessionalSale.id == sale_id,
                                ProfessionalSale.is_deleted == False
                            ).first()
                            if sale:
                                item['customer_name'] = sale.customer.name if sale.customer else 'N/A'
                                item['delivery_name'] = sale.delivery_name or ''
                        except (ValueError, TypeError):
                            pass

                    result.append(item)

                return result

            except Exception as e:
                logger.error(f"Error getting transactions for batch {batch_id}: {e}")
                return []