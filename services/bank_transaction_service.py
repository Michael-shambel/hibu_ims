from requests import Session
from services.base_service import BaseService, get_session
import logging
from models.bank_transactions import BankTransaction, TransactionDirectionEnum
from datetime import date
from sqlalchemy import desc, func
from typing import Optional, List

# REMOVED: from services.bank_account_service import BankAccountService

logger = logging.getLogger(__name__)

class BankTransactionService(BaseService[BankTransaction]):
    def __init__(self):
        super().__init__(BankTransaction)
        # No self.bank_account_service here – will import lazily description
    
    def get_balance(self, account_id: int) -> float:
        with get_session() as session:
            try:
                # Local import to avoid circular dependency
                from services.bank_account_service import BankAccountService
                account = BankAccountService().get_by_id(account_id)
                reset_date = account.reset_date if account else None

                query = session.query(BankTransaction).filter(
                    BankTransaction.bank_account_id == account_id,
                    BankTransaction.is_deleted == False
                )
                if reset_date:
                    query = query.filter(BankTransaction.transaction_date >= reset_date)
                
                latest_tx = query.order_by(desc(BankTransaction.id)).first()
                if latest_tx:
                    return float(latest_tx.balance_after)
                return 0.0
            except Exception as e:
                logger.error(f"Error calculating balance for account {account_id}: {e}")
                return 0.0
    
    def create_transaction(self, session, data: dict) -> Optional[BankTransaction]:
        try:
            latest = session.query(BankTransaction).filter(
                BankTransaction.bank_account_id == data['bank_account_id'],
                BankTransaction.is_deleted == False
            ).order_by(desc(BankTransaction.id)).first()

            previous_balance = latest.balance_after if latest else 0.0

            if data['direction'] == TransactionDirectionEnum.DEBIT:
                data['balance_after'] = previous_balance - data['amount']
            else:
                data['balance_after'] = previous_balance + data['amount']
            
            transaction = BankTransaction(**data)
            session.add(transaction)
            session.flush()

            self.recalculate_balances_for_account(session, data['bank_account_id'])

            return transaction
        except Exception as e:
            logger.error(f"Error creating bank transaction: {e}")
            return None
    
    def get_transactions(
        self,
        account_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        direction: Optional[TransactionDirectionEnum] = None
    ) -> List[BankTransaction]:
        with get_session() as session:
            try:
                from services.bank_account_service import BankAccountService
                account = BankAccountService().get_by_id(account_id)
                reset_date = account.reset_date if account else None
                
                query = session.query(self.model).filter(
                    self.model.bank_account_id == account_id,
                    self.model.is_deleted == False
                )
                if reset_date:
                    query = query.filter(self.model.transaction_date >= reset_date)
                
                # Exclude the reset marker from display
                # query = query.filter(self.model.description != "=== RESET STARTING BALANCE ===")

                if start_date:
                    if reset_date and start_date < reset_date:
                        start_date = reset_date
                    query = query.filter(self.model.transaction_date >= start_date)
                if end_date:
                    query = query.filter(self.model.transaction_date <= end_date)
                if direction:
                    query = query.filter(self.model.direction == direction)
                
                return query.order_by(self.model.transaction_date, self.model.id).all()
            except Exception as e:
                logger.error(f"Error retrieving transactions for account {account_id}: {e}")
                return []
    
    def _create_transaction_in_session(self, session, data: dict) -> Optional[BankTransaction]:
        try:
            account_id = data['bank_account_id']
            from services.bank_account_service import BankAccountService
            account = BankAccountService().get_by_id(account_id)
            reset_date = account.reset_date if account else None
            
            query = session.query(BankTransaction).filter(
                BankTransaction.bank_account_id == account_id,
                BankTransaction.is_deleted == False
            )
            if reset_date:
                query = query.filter(BankTransaction.transaction_date >= reset_date)
            
            latest = query.order_by(desc(BankTransaction.id)).first()

            if reset_date and not latest:
                previous_balance = 0.0
            else:
                previous_balance = latest.balance_after if latest else 0.0
            
            if data['direction'] == TransactionDirectionEnum.DEBIT:
                data['balance_after'] = previous_balance - data['amount']
            else:
                data['balance_after'] = previous_balance + data['amount']
            
            transaction = BankTransaction(**data)
            session.add(transaction)
            session.flush()

            self.recalculate_balances_for_account(session, data['bank_account_id'])
            
            return transaction
        except Exception as e:
            logger.error(f"Error creating bank transaction in session: {e}")
            return None
    
    def transfer_between_accounts(
        self,
        from_account_id: int,
        to_account_id: int,
        amount: float,
        transaction_date: date,
        description: str,
        reference: str = None
    ) -> bool:
        with get_session() as session:
            try:
                debit_data = {
                    'bank_account_id': from_account_id,
                    'amount': amount,
                    'direction': TransactionDirectionEnum.DEBIT,
                    'transaction_date': transaction_date,
                    'description': f"Transfer to account {to_account_id}: {description}",
                    'reference_number': reference
                }
                debit_transaction = self._create_transaction_in_session(session, debit_data)
                if not debit_transaction:
                    raise Exception("Failed to create debit transaction")
                
                credit_data = {
                    'bank_account_id': to_account_id,
                    'amount': amount,
                    'direction': TransactionDirectionEnum.CREDIT,
                    'transaction_date': transaction_date,
                    'description': f"Transfer from account {from_account_id}: {description}",
                    'reference_number': reference
                }
                credit_transaction = self._create_transaction_in_session(session, credit_data)
                if not credit_transaction:
                    raise Exception("Failed to create credit transaction")
                
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error during transfer: {e}")
                return False
    
    def create_external_transfer(
        self,
        from_account_id: int,
        amount: float,
        transaction_date: date,
        payee: str,
        description: str,
        reference: str = None
    ) -> Optional[BankTransaction]:
        with get_session() as session:
            try:
                data = {
                    'bank_account_id': from_account_id,
                    'amount': amount,
                    'direction': TransactionDirectionEnum.DEBIT,
                    'transaction_date': transaction_date,
                    'description': f"External transfer to {payee}: {description}",
                    'reference_number': reference
                }
                transaction = self._create_transaction_in_session(session, data)
                if transaction:
                    session.commit()
                return transaction
            except Exception as e:
                session.rollback()
                logger.error(f"Error creating external transfer: {e}")
                return None
    
    def create_external_deposit(
        self,
        to_account_id: int,
        amount: float,
        transaction_date: date,
        source: str,
        description: str,
        reference: str = None
    ) -> Optional[BankTransaction]:
        with get_session() as session:
            try:
                data = {
                    'bank_account_id': to_account_id,
                    'amount': amount,
                    'direction': TransactionDirectionEnum.CREDIT,
                    'transaction_date': transaction_date,
                    'description': f"External deposit from {source}: {description}",
                    'reference_number': reference
                }
                transaction = self._create_transaction_in_session(session, data)
                if transaction:
                    session.commit()
                return transaction
            except Exception as e:
                session.rollback()
                logger.error(f"Error creating external deposit: {e}")
                return None
    
    def recalculate_balances_for_account(self, session: Session, account_id: int) -> bool:
        try:
            from services.bank_account_service import BankAccountService
            acc_svc = BankAccountService()
            account = acc_svc.get_by_id(account_id)
            reset_date = account.reset_date if account else None
            
            query = session.query(BankTransaction).filter(
                BankTransaction.bank_account_id == account_id,
                BankTransaction.is_deleted == False
            )
            if reset_date:
                query = query.filter(BankTransaction.transaction_date >= reset_date)
            transactions = query.order_by(BankTransaction.transaction_date, BankTransaction.id).all()
            
            balance = 0.0
            for tx in transactions:
                if tx.direction == TransactionDirectionEnum.DEBIT:
                    balance -= tx.amount
                else:
                    balance += tx.amount
                tx.balance_after = balance
            session.flush()
            return True
        except Exception as e:
            logger.error(f"Error recalculating balances for account {account_id}: {e}")
            return False
    
    def get_balance_before_date(self, account_id: int, before_date: date, exclude_transaction_id: int = None) -> float:
        with get_session() as session:
            try:
                from services.bank_account_service import BankAccountService
                acc_svc = BankAccountService()
                account = acc_svc.get_by_id(account_id)
                reset_date = account.reset_date if account else None
                
                query = session.query(BankTransaction).filter(
                    BankTransaction.bank_account_id == account_id,
                    BankTransaction.is_deleted == False,
                    BankTransaction.transaction_date < before_date
                )
                if reset_date:
                    query = query.filter(BankTransaction.transaction_date >= reset_date)
                if exclude_transaction_id:
                    query = query.filter(BankTransaction.id != exclude_transaction_id)
                
                latest_tx = query.order_by(desc(BankTransaction.transaction_date), desc(BankTransaction.id)).first()
                if latest_tx:
                    return float(latest_tx.balance_after)
                return 0.0
            except Exception as e:
                logger.error(f"Error getting balance before date: {e}")
                return 0.0
    
    def get_total_debit_for_account_on_date(self, account_id: int, target_date: date) -> float:
        with get_session() as session:
            try:
                from sqlalchemy import func
                total = session.query(func.sum(BankTransaction.amount)).filter(
                    BankTransaction.bank_account_id == account_id,
                    BankTransaction.direction == TransactionDirectionEnum.DEBIT,
                    BankTransaction.transaction_date == target_date,
                    BankTransaction.is_deleted == False,
                    BankTransaction.description.ilike('Transfer to account%')
                ).scalar()
                return float(total) if total else 0.0
            except Exception as e:
                logger.error(f"Error getting total debit for account {account_id} on {target_date}: {e}")
                return 0.0
    
    def delete(self, id: int) -> bool:
        """
        Soft‑delete a bank transaction and recalculate the balance chain
        for its account so that all balance_after values stay consistent.
        """
        with get_session() as session:
            try:
                tx = session.query(BankTransaction).filter(
                    BankTransaction.id == id,
                    BankTransaction.is_deleted == False
                ).first()
                if not tx:
                    logger.warning(f"BankTransaction {id} not found or already deleted")
                    return False

                account_id = tx.bank_account_id

                # Soft‑delete
                tx.is_deleted = True
                session.flush()

                # Recalculate the whole chain for this account
                if not self.recalculate_balances_for_account(session, account_id):
                    raise Exception("Balance recalculation failed")

                session.commit()
                logger.info(f"Deleted transaction {id} and recalculated balances for account {account_id}")
                return True

            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting transaction {id}: {e}")
                return False
    
    def get_total_credit_for_sales_on_date(self, account_id: int, target_date: date) -> float:
        """Sum of credit inflows from customer payments on credit sales,
        EXCLUDING payments where the sale was created on the same day (those are cash sales)."""
        from sqlalchemy import func
        from models.sale_payment_term import SalePaymentTerm
        from models.new_sales import ProfessionalSale

        with get_session() as session:
            total = session.query(func.sum(BankTransaction.amount)).join(
                SalePaymentTerm,
                BankTransaction.sale_payment_term_id == SalePaymentTerm.id
            ).join(
                ProfessionalSale,
                SalePaymentTerm.sale_id == ProfessionalSale.id
            ).filter(
                BankTransaction.bank_account_id == account_id,
                BankTransaction.direction == TransactionDirectionEnum.CREDIT,
                BankTransaction.sale_payment_term_id.isnot(None),
                func.date(BankTransaction.transaction_date) == target_date,
                BankTransaction.is_deleted == False,
                # 👇 Exclude same‑day conversions (credit sale paid immediately)
                func.date(ProfessionalSale.created_at) != target_date
            ).scalar()
            return total or 0.0

    def get_total_debit_for_purchases_on_date(self, account_id: int, target_date: date) -> float:
        """Sum of debit outflows from an account for supplier purchase payments."""
        from sqlalchemy import func
        from models.purchase_payment_transaction import PurchasePaymentTransaction

        with get_session() as session:
            total = session.query(func.sum(BankTransaction.amount)).join(
                PurchasePaymentTransaction,
                BankTransaction.id == PurchasePaymentTransaction.bank_transaction_id
            ).filter(
                BankTransaction.bank_account_id == account_id,
                BankTransaction.direction == TransactionDirectionEnum.DEBIT,
                func.date(BankTransaction.transaction_date) == target_date,
                BankTransaction.is_deleted == False,
                PurchasePaymentTransaction.is_deleted == False
            ).scalar()
            return total or 0.0