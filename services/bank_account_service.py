from multiprocessing import synchronize

from services.base_service import BaseService, get_session
import logging
from models.bank_account import BankAccount, AccountTypeEnum
from typing import Optional, List
from services.bank_transaction_service import BankTransactionService
from datetime import date
from models.bank_transactions import TransactionDirectionEnum
from models.bank_transactions import BankTransaction

logger = logging.getLogger(__name__)


class BankAccountService(BaseService[BankAccount]):
    def __init__(self):
        super().__init__(BankAccount)
        self.bank_transaction_service = BankTransactionService() 
    
    def create(self, data: dict) -> Optional[BankAccount]:
        initial_balance = data.pop("initial_balance", 0.0)

        account = super().create(data)
        if not account:
            return None
        
        if initial_balance != 0:
            try:
                tx_data = {
                    "bank_account_id": account.id,
                    "amount": abs(initial_balance),
                    "direction": TransactionDirectionEnum.CREDIT,
                    "transaction_date": date.today(),
                    "description": "Initial balance",
                    "payment_method": None,
                    "balance_after": initial_balance
                }
                
                bank_transaction = self.bank_transaction_service.create(tx_data)
                if bank_transaction:
                    logger.info(f"Created initial transaction for account {account.id}")
            except Exception as e:
                logger.error(f"Failed to create initial transaction for account {account.id}: {e}")
        
        return account
    
    def get_by_account_type(self, account_type: AccountTypeEnum, active_only: bool = True) -> List[BankAccount]:
        with get_session() as session:
            try:
                query = session.query(self.model).filter(
                    self.model.account_type == account_type,
                    self.model.is_deleted == False
                )
                if active_only:
                    query = query.filter(self.model.is_active == True)
                
                return query.all()
            except Exception as e:
                logger.error(f"Error retrieving bank transactions by type {account_type}: {e}")
                return []
    
    def soft_delete_with_transactions(self, account_id: int) -> bool:
        """Soft delete the bank account and all its bank transactions."""
        with get_session() as session:
            try:
                # Get account
                account = session.query(self.model).filter(
                    self.model.id == account_id,
                    self.model.is_deleted == False
                ).first()
                if not account:
                    return False

                # Soft delete account
                account.is_deleted = True

                session.query(BankTransaction).filter(
                    BankTransaction.bank_account_id == account_id,
                    BankTransaction.is_deleted == False
                ).update({"is_deleted": True}, synchronize_session=False)

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error soft deleting account {account_id} with transactions: {e}")
                return False

    def get_by_account_number(self, account_number: str):
        with get_session() as session:
            try:
                return session.query(BankAccount).filter(
                    BankAccount.account_number == account_number,
                    BankAccount.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"failed to get the account: {e}")
    
    def reset_transaction_history(self, account_id: int, new_starting_balance: float = 0.0) -> bool:
        with get_session() as session:
            try:
                account = session.query(self.model).filter(
                    self.model.id == account_id,
                    self.model.is_deleted == False
                ).first()
                if not account:
                    return False
                
                reset_date = date.today()
                account.reset_date = reset_date

                # Mark old reset markers as deleted (if any)
                session.query(BankTransaction).filter(
                    BankTransaction.bank_account_id == account_id,
                    BankTransaction.description == "=== RESET STARTING BALANCE ===",
                    BankTransaction.is_deleted == False
                ).update({"is_deleted": True}, synchronize_session=False)

                # Create a visible starting balance transaction as CREDIT
                direction = TransactionDirectionEnum.CREDIT  # Always credit for starting balance

                reset_tx = BankTransaction(
                    bank_account_id=account_id,
                    amount=abs(new_starting_balance),
                    direction=direction,
                    transaction_date=reset_date,
                    description=f"=== STARTING BALANCE AFTER RESET: ${new_starting_balance:,.2f} ===",
                    balance_after=new_starting_balance,
                    reference_number=None
                )
                session.add(reset_tx)

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error resetting transaction history for account {account_id}: {e}")
                return False
    
    def get_total_balance_all_accounts(self) -> float:
        """Return the sum of the latest balance_after for every active, non-deleted account."""
        total = 0.0
        accounts = self.get_all()   # already filters is_deleted=False
        for acc in accounts:
            if acc.is_active:
                try:
                    total += self.bank_transaction_service.get_balance(acc.id)
                except Exception as e:
                    logger.error(f"Could not get balance for account {acc.id}: {e}")
        return total