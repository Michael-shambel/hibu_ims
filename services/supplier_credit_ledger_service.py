import logging
from models.supplier_credit_ledger import SupplierCreditLedger
from services.base_service import BaseService, get_session
from datetime import datetime, date

logger = logging.getLogger(__name__)

class SupplierCreditLedgerService(BaseService[SupplierCreditLedger]):
    def __init__(self):
        super().__init__(SupplierCreditLedger)
    
    def add_entry(self, session, supplier_id: int, entry_date: date,
                  entry_type: str, description: str,
                  debit: float = 0.0, credit: float = 0.0,
                  purchase_id: int = None, batch_id: int = None,
                  payment_transaction_id: int = None,
                  bank_transaction_id: int = None) -> SupplierCreditLedger:
        
        entry = SupplierCreditLedger(
            supplier_id=supplier_id,
            purchase_id=purchase_id,
            batch_id=batch_id,
            payment_transaction_id=payment_transaction_id,
            bank_transaction_id=bank_transaction_id,
            entry_date=entry_date,
            entry_type=entry_type,
            description=description,
            debit=debit,
            credit=credit
        )
        session.add(entry)
        return entry