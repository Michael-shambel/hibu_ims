#!/usr/bin/env python3

import logging
from models.expense import Expense, ExpensePaymentMethod
from services.base_service import BaseService, get_session
from typing import Optional, List, Tuple
from models.bank_transactions import TransactionDirectionEnum, PaymentMethodEnum
from models.bank_transactions import BankTransaction
from services.bank_transaction_service import BankTransactionService
from sqlalchemy import or_, func
from datetime import date
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

class ExpenseService(BaseService[Expense]):
    def __init__(self):
        super().__init__(Expense)
        self.expense_service = Expense()
        self.bank_transaction_service = BankTransactionService()
    
    def get_filtered(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        is_personal: Optional[bool] = None, 
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Expense], int]:
        with get_session() as session:
            query = session.query(self.model).options(
                joinedload(self.model.category),
                joinedload(self.model.bank_account)
            ).filter(
                self.model.is_deleted == False
            )
            if start_date:
                query = query.filter(self.model.date >= start_date)
            if end_date:
                query = query.filter(self.model.date <= end_date)
            if category_id:
                query = query.filter(self.model.category_id == category_id)
            if is_personal is not None:
                query = query.filter(self.model.is_personal == is_personal)
            if search:
                search_filter = (
                    self.model.description.ilike(f"%{search}%") |
                    self.model.notes.ilike(f"%{search}%") |
                    self.model.reference.ilike(f"%{search}%")
                )
                query = query.filter(search_filter)

            total = query.count()
            results = query.order_by(self.model.date.desc()).offset(offset).limit(limit).all()
            return results, total
    
    def create(self, data: dict) -> Optional[Expense]:
        with get_session() as session:
            try:
                self._validate_create(data)
                expense = Expense(**data)
                session.add(expense)
                session.flush()

                transaction_data = {
                    'bank_account_id': data['bank_account_id'],
                    'transaction_date': expense.date,
                    'direction': TransactionDirectionEnum.DEBIT,
                    'amount': expense.amount,
                    'payment_method': PaymentMethodEnum.TRANSFER,
                    'description': f"Expense: {expense.notes}",
                    'expense_id': expense.id,
                    'recorded_by_user_id': data.get('user_id')
                }
                bank_transaction = self.bank_transaction_service.create_transaction(session, transaction_data)
                if not bank_transaction:
                    raise Exception("Failed to record bank transactions")
                
                session.commit()
                session.refresh(expense)
                logger.info(f"Expense {expense.id} created with bank transaction {bank_transaction.id}")
                return expense
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to create expense: {e}")
                return None

    
    def _validate_create(self, data: dict) -> None:
        bank_account_id = data.get('bank_account_id')
        amount = data.get('amount', 0.0)

        if not bank_account_id:
            raise ValueError("Bank account is required")

        current_balance = self.bank_transaction_service.get_balance(bank_account_id)
        if amount > current_balance:
            raise ValueError(
                f"Insufficient balance. Available: {current_balance:.2f}, Required: {amount:.2f}"
            )
    
    def delete_with_transaction(self, expense_id: int) -> bool:
        with get_session() as session:
            try:
                expense = session.query(Expense).filter(
                    Expense.id == expense_id,
                    Expense.is_deleted == False
                ).first()
                if not expense:
                    logger.warning(f"Expense {expense_id} not found or already deleted")
                    return False

                bank_tx = session.query(BankTransaction).filter(
                    BankTransaction.expense_id == expense_id,
                    BankTransaction.is_deleted == False
                ).first()

                account_id = None
                if bank_tx:
                    account_id = bank_tx.bank_account_id
                    bank_tx.is_deleted = True  # Soft-delete

                expense.is_deleted = True
                session.flush()

                if account_id:
                    # Use the service method – it respects reset_date
                    self.bank_transaction_service.recalculate_balances_for_account(session, account_id)

                session.commit()
                logger.info(f"Expense {expense_id} and its bank transaction deleted, balances updated.")
                return True

            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting expense {expense_id} with transaction: {e}")
                return False
    
    def create_multiple(self, data):
        common = data['common']
        lines = data['lines']
        with get_session() as session:
            try:
                lines_by_account = {}
                for line in lines:
                    acc_id = line['bank_account_id']
                    lines_by_account.setdefault(acc_id, []).append(line)

                for acc_id, acc_lines in lines_by_account.items():
                    total_for_acc = sum(line['amount'] for line in acc_lines)
                    current_balance = self.bank_transaction_service.get_balance(acc_id)
                    if total_for_acc > current_balance:
                        raise ValueError(
                            f"Insufficient balance in account {acc_id}. "
                            f"Available: {current_balance:.2f}, Required: {total_for_acc:.2f}"
                        )

                affected_accounts = set()

                for line in lines:
                    expense_data = {
                        'date': common['date'],
                        'description': line.get('description', 'Expense'),
                        'amount': line['amount'],
                        'category_id': line['category_id'],
                        'payment_method': common['payment_method'],
                        'bank_account_id': line['bank_account_id'],
                        'notes': line.get('notes'),
                        'user_id': common.get('user_id'),
                        'is_personal': line.get('is_personal', False)
                    }
                    expense = Expense(**expense_data)
                    session.add(expense)
                    session.flush()

                    from models.bank_transactions import BankTransaction, TransactionDirectionEnum, PaymentMethodEnum
                    last_tx = session.query(BankTransaction).filter(
                        BankTransaction.bank_account_id == line['bank_account_id'],
                        BankTransaction.is_deleted == False
                    ).order_by(BankTransaction.id.desc()).first()
                    prev_balance = last_tx.balance_after if last_tx else 0.0
                    bank_tx = BankTransaction(
                        bank_account_id=line['bank_account_id'],
                        transaction_date=expense.date,
                        direction=TransactionDirectionEnum.DEBIT,
                        amount=expense.amount,
                        payment_method=PaymentMethodEnum.TRANSFER,
                        description=f"Expense: {expense.notes}",
                        expense_id=expense.id,
                        recorded_by_user_id=common.get('user_id'),
                        balance_after=prev_balance - expense.amount
                    )
                    session.add(bank_tx)
                    session.flush()
                    affected_accounts.add(line['bank_account_id'])

                # Recalculate balances for all affected accounts – use service method
                for acc_id in affected_accounts:
                    self.bank_transaction_service.recalculate_balances_for_account(session, acc_id)

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to create multiple expenses: {e}")
                return False
    
    def get_total_expenses_for_period(self, start_date: date, end_date: date, business_only: bool = True) -> float:
        with get_session() as session:
            query = session.query(func.sum(Expense.amount)).filter(
                Expense.date >= start_date,
                Expense.date <= end_date,
                Expense.is_deleted == False
            )
            if business_only:
                query = query.filter(Expense.is_personal == False)
            total = query.scalar()
            return float(total) if total else 0.0
        
    
    def get_expenses_by_date_range(self, start_date: date, end_date: date, business_only: bool = False) -> List[Expense]:
        with get_session() as session:
            query = session.query(Expense).options(
                joinedload(Expense.category),
                joinedload(Expense.bank_account)
            ).filter(
                Expense.created_at.between(start_date, end_date),
                Expense.is_deleted == False
            )
            if business_only:
                query = query.filter(Expense.is_personal == False)
            return query.order_by(Expense.created_at.asc()).all()
    
    # ---------- UPDATED UPDATE METHOD ----------
    def update(self, expense_id: int, data: dict) -> Optional[Expense]:
        with get_session() as session:
            try:
                expense = session.query(Expense).filter(
                    Expense.id == expense_id,
                    Expense.is_deleted == False
                ).first()
                if not expense:
                    logger.warning(f"Expense {expense_id} not found")
                    return None

                old_amount = expense.amount
                old_bank_id = expense.bank_account_id
                old_date = expense.date

                # Apply updates
                for key, value in data.items():
                    setattr(expense, key, value)

                amount_changed = old_amount != data.get('amount', old_amount)
                bank_changed = old_bank_id != data.get('bank_account_id', old_bank_id)
                date_changed = old_date != data.get('date', old_date)

                if amount_changed or bank_changed or date_changed:
                    bank_tx = session.query(BankTransaction).filter(
                        BankTransaction.expense_id == expense_id,
                        BankTransaction.is_deleted == False
                    ).first()

                    if bank_tx:
                        if bank_changed:
                            # ---- Move to new bank account ----
                            # 1. Check if destination account has enough balance
                            new_balance_before = self.bank_transaction_service.get_balance(expense.bank_account_id)
                            if expense.amount > new_balance_before:
                                # Not enough funds – raise an error that the UI can catch
                                raise ValueError(
                                    f"Insufficient balance in new account. "
                                    f"Available: {new_balance_before:.2f}, Required: {expense.amount:.2f}"
                                )

                            # 2. Soft-delete old transaction and recalc old account
                            old_tx_id = bank_tx.id
                            bank_tx.is_deleted = True
                            session.flush()
                            self.bank_transaction_service.recalculate_balances_for_account(session, old_bank_id)

                            # 3. Create new transaction for the new account
                            tx_data = {
                                'bank_account_id': expense.bank_account_id,
                                'amount': expense.amount,
                                'direction': TransactionDirectionEnum.DEBIT,
                                'transaction_date': expense.date,
                                'description': f"Expense: {expense.notes}",
                                'expense_id': expense.id,
                                'recorded_by_user_id': expense.user_id,
                                'payment_method': PaymentMethodEnum.TRANSFER,
                            }
                            new_tx = self.bank_transaction_service.create_transaction(session, tx_data)
                            if not new_tx:
                                raise Exception("Failed to create bank transaction for updated expense")
                        else:
                            # Update existing transaction (amount/date changed)
                            bank_tx.amount = expense.amount
                            bank_tx.transaction_date = expense.date
                            bank_tx.description = f"Expense: {expense.notes}"
                            session.flush()
                            self.bank_transaction_service.recalculate_balances_for_account(session, expense.bank_account_id)
                    else:
                        # No transaction – create one (shouldn't happen)
                        tx_data = {
                            'bank_account_id': expense.bank_account_id,
                            'amount': expense.amount,
                            'direction': TransactionDirectionEnum.DEBIT,
                            'transaction_date': expense.date,
                            'description': f"Expense: {expense.notes}",
                            'expense_id': expense.id,
                            'recorded_by_user_id': expense.user_id,
                            'payment_method': PaymentMethodEnum.TRANSFER,
                        }
                        new_tx = self.bank_transaction_service.create_transaction(session, tx_data)
                        if not new_tx:
                            raise Exception("Failed to create bank transaction for expense")

                session.commit()
                session.refresh(expense)
                return expense
            except ValueError as ve:
                # Re-raise so the UI can show a user-friendly message
                session.rollback()
                raise ve
            except Exception as e:
                session.rollback()
                logger.error(f"Error updating expense {expense_id}: {e}")
                return None

    # ---------- ORIGINAL HELPERS (KEPT FOR BACKWARDS COMPATIBILITY BUT NOW USE SERVICE METHODS) ----------
    def _delete_transaction_and_recalc(self, session, transaction_id: int):
        tx = session.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
        if not tx:
            return
        account_id = tx.bank_account_id
        tx.is_deleted = True
        session.flush()
        self.bank_transaction_service.recalculate_balances_for_account(session, account_id)

    def _recalculate_balances_for_account(self, session, account_id: int, after_tx_id: int = None):
        # Delegate to the service method – it handles reset_date properly
        # Note: the service method recalculates all transactions from the beginning,
        # not from after_tx_id. So we ignore after_tx_id here.
        self.bank_transaction_service.recalculate_balances_for_account(session, account_id)

    def _create_transaction_for_expense(self, session, expense: Expense):
        # Use the service method to create the transaction correctly
        tx_data = {
            'bank_account_id': expense.bank_account_id,
            'amount': expense.amount,
            'direction': TransactionDirectionEnum.DEBIT,
            'transaction_date': expense.date,
            'description': f"Expense: {expense.notes}",
            'expense_id': expense.id,
            'recorded_by_user_id': expense.user_id,
            'payment_method': PaymentMethodEnum.TRANSFER,
        }
        return self.bank_transaction_service.create_transaction(session, tx_data)

    # ---------- CASH EXPENSES (unchanged) ----------
    def get_cash_expenses_for_date(self, target_date: date) -> float:
        from models.bank_account import BankAccount

        with get_session() as session:
            cash_account = session.query(BankAccount).filter(
                BankAccount.account_number == '00000',
                BankAccount.is_active == True,
                BankAccount.is_deleted == False
            ).first()
            if not cash_account:
                cash_account = session.query(BankAccount).filter(
                    BankAccount.account_name.ilike('%cash%'),
                    BankAccount.is_active == True
                ).first()

            if not cash_account:
                logger.warning("Cash account not found – cannot compute cash expenses")
                return 0.0

            total = session.query(func.sum(Expense.amount)).filter(
                Expense.bank_account_id == cash_account.id,
                Expense.date == target_date,
                Expense.is_deleted == False,
                Expense.is_personal == False
            ).scalar()

            result = float(total) if total else 0.0
            logger.info(f"Business cash expenses for {target_date}: {result} (account id={cash_account.id})")
            return result
    
    def get_personal_expenses_for_period(self, start_date, end_date) -> float:
        from sqlalchemy import func
        with get_session() as session:
            total = session.query(func.sum(Expense.amount)).filter(
                Expense.date >= start_date,
                Expense.date <= end_date,
                Expense.is_deleted == False,
                Expense.is_personal == True
            ).scalar()
            return float(total) if total else 0.0