#!/usr/bin/env python3
from datetime import date, datetime
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import joinedload

from models.bank_transactions import BankTransaction, PaymentMethodEnum, TransactionDirectionEnum
from models.cash_loan import CashLoan, CashLoanDirectionEnum, CashLoanPayment
from services.bank_transaction_service import BankTransactionService
from services.base_service import BaseService, get_session
from sqlalchemy import func

logger = logging.getLogger(__name__)


class CashLoanService(BaseService[CashLoan]):
    def __init__(self):
        super().__init__(CashLoan)
        self.bank_transaction_service = BankTransactionService()

    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join((name or "").casefold().split())

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
        if digits.startswith("00251") and len(digits) == 14:
            return "0" + digits[5:]
        if digits.startswith("251") and len(digits) == 12:
            return "0" + digits[3:]
        return digits

    def build_match_key(self, name: str, phone: str) -> str:
        normalized_name = self.normalize_name(name)
        if not normalized_name:
            return ""
        normalized_phone = self.normalize_phone(phone)
        if normalized_phone:
            return f"name-phone:{normalized_name}:{normalized_phone}"
        return f"name-only:{normalized_name}"

    def _find_existing_open_loan(
        self,
        session,
        customer_id: Optional[int],
        supplier_id: Optional[int],
        person_name: str,
        phone: str,
        direction: CashLoanDirectionEnum,
    ) -> Optional[CashLoan]:
        """
        Find an open loan for the same person and direction.
        Priority: customer_id > supplier_id > name+phone match.
        Only returns loans that are not fully paid.
        """
        query = session.query(CashLoan).filter(
            CashLoan.is_deleted == False,
            CashLoan.status != "paid",          # only open (outstanding or partial)
            CashLoan.direction == direction,
        )

        if customer_id:
            query = query.filter(CashLoan.customer_id == customer_id)
        elif supplier_id:
            query = query.filter(CashLoan.supplier_id == supplier_id)
        else:
            # Manual person: match by normalized name and phone (if provided)
            norm_name = self.normalize_name(person_name)
            norm_phone = self.normalize_phone(phone)
            if not norm_name:
                return None
            # Use ILIKE for case-insensitive partial matching; for exact name, we could do equality
            # but ILIKE is safer for minor variations.
            query = query.filter(CashLoan.person_name.ilike(f"%{norm_name}%"))
            if norm_phone:
                query = query.filter(CashLoan.phone.ilike(f"%{norm_phone}%"))
            # else: no phone filter, rely on name only

        return query.order_by(CashLoan.id.asc()).first()  # pick the oldest open loan

    def create_cash_loan(
        self,
        person_name: str,
        phone: str,
        direction: CashLoanDirectionEnum | str,
        amount: float,
        bank_account_id: int,
        user_id: Optional[int] = None,
        loan_date: Optional[date] = None,
        due_date: Optional[date] = None,
        notes: str = "",
        customer_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Create a new cash loan or add amount to an existing open loan.
        Returns (success, message).
        """
        if loan_date is None:
            loan_date = date.today()
        direction = CashLoanDirectionEnum(direction)

        person_name = (person_name or "").strip()
        phone = (phone or "").strip()
        notes = (notes or "").strip()
        amount = float(amount or 0)

        if not person_name:
            return False, "Person name is required."
        if amount <= 0:
            return False, "Amount must be greater than zero."
        if not bank_account_id:
            return False, "Bank account is required."

        with get_session() as session:
            try:
                # ---- Check for existing open loan ----
                existing = self._find_existing_open_loan(
                    session, customer_id, supplier_id, person_name, phone, direction
                )

                dt = datetime.combine(loan_date, datetime.now().time())

                if existing:
                    # ---- Add to existing loan ----
                    # Validate direction consistency (should match)
                    if existing.direction != direction:
                        return False, "Direction mismatch with existing loan."

                    # Check sufficient balance if giving money
                    if direction == CashLoanDirectionEnum.GIVEN:
                        current_balance = self.bank_transaction_service.get_balance(bank_account_id)
                        if current_balance < amount:
                            return False, (
                                f"Insufficient funds. Available: ${current_balance:,.2f}, "
                                f"Required: ${amount:,.2f}"
                            )

                    # Create bank transaction for the additional amount
                    bank_direction = (
                        TransactionDirectionEnum.DEBIT
                        if direction == CashLoanDirectionEnum.GIVEN
                        else TransactionDirectionEnum.CREDIT
                    )
                    description = (
                        f"Additional cash loan to {person_name} (added to loan #{existing.id})"
                        if direction == CashLoanDirectionEnum.GIVEN
                        else f"Additional cash loan from {person_name} (added to loan #{existing.id})"
                    )
                    if notes:
                        description = f"{description} - {notes}"

                    bank_tx = self.bank_transaction_service.create_transaction(session, {
                        "bank_account_id": bank_account_id,
                        "transaction_date": loan_date,
                        "direction": bank_direction,
                        "amount": amount,
                        "payment_method": PaymentMethodEnum.TRANSFER,
                        "description": description,
                        "recorded_by_user_id": user_id,
                        "created_at": dt,
                        "last_modified": dt,
                    })
                    if not bank_tx:
                        raise Exception("Failed to create bank transaction for additional amount.")

                    # Update loan principal
                    existing.principal_amount += amount
                    existing.last_modified = dt
                    existing.update_status()  # may set to PAID if fully paid (won't, because we only add)
                    session.commit()

                    return True, f"Amount added to existing loan #{existing.id} for {person_name}."

                # ---- Create new loan (original logic) ----
                if direction == CashLoanDirectionEnum.GIVEN:
                    current_balance = self.bank_transaction_service.get_balance(bank_account_id)
                    if current_balance < amount:
                        return False, (
                            f"Insufficient funds. Available: ${current_balance:,.2f}, "
                            f"Required: ${amount:,.2f}"
                        )

                bank_direction = (
                    TransactionDirectionEnum.DEBIT
                    if direction == CashLoanDirectionEnum.GIVEN
                    else TransactionDirectionEnum.CREDIT
                )
                description = (
                    f"Cash loan given to {person_name}"
                    if direction == CashLoanDirectionEnum.GIVEN
                    else f"Cash loan received from {person_name}"
                )
                if notes:
                    description = f"{description} - {notes}"

                bank_tx = self.bank_transaction_service.create_transaction(session, {
                    "bank_account_id": bank_account_id,
                    "transaction_date": loan_date,
                    "direction": bank_direction,
                    "amount": amount,
                    "payment_method": PaymentMethodEnum.TRANSFER,
                    "description": description,
                    "recorded_by_user_id": user_id,
                    "created_at": dt,
                    "last_modified": dt,
                })
                if not bank_tx:
                    raise Exception("Failed to create bank transaction.")

                loan = CashLoan(
                    person_name=person_name,
                    phone=phone,
                    customer_id=customer_id,
                    supplier_id=supplier_id,
                    direction=direction,
                    principal_amount=amount,
                    paid_amount=0.0,
                    loan_date=loan_date,
                    due_date=due_date,
                    bank_account_id=bank_account_id,
                    bank_transaction_id=bank_tx.id,
                    notes=notes,
                    user_id=user_id,
                    created_at=dt,
                    last_modified=dt,
                )
                loan.update_status()
                session.add(loan)
                session.commit()
                return True, f"New loan #{loan.id} created for {person_name}."

            except Exception as exc:
                session.rollback()
                logger.error(f"Error creating cash loan: {exc}", exc_info=True)
                return False, f"An error occurred: {exc}"

    def record_repayment(
        self,
        loan_id: int,
        amount: float,
        bank_account_id: int,
        user_id: Optional[int] = None,
        payment_date: Optional[date] = None,
        notes: str = "",
    ) -> Tuple[bool, str]:
        if payment_date is None:
            payment_date = date.today()
        amount = float(amount or 0)
        notes = (notes or "").strip()

        if amount <= 0:
            return False, "Payment amount must be greater than zero."
        if not bank_account_id:
            return False, "Bank account is required."

        with get_session() as session:
            try:
                # 🔒 Lock the loan row to prevent race conditions
                loan = session.query(CashLoan).filter(
                    CashLoan.id == loan_id,
                    CashLoan.is_deleted == False,
                ).with_for_update().first()
                if not loan:
                    return False, "Loan not found."

                remaining = loan.principal_amount - loan.paid_amount
                if remaining <= 0:
                    return False, "This loan is already paid."
                if amount > remaining + 0.01:
                    return False, (
                        f"Payment amount (${amount:,.2f}) exceeds remaining balance "
                        f"(${remaining:,.2f})."
                    )

                if loan.direction == CashLoanDirectionEnum.RECEIVED:
                    current_balance = self.bank_transaction_service.get_balance(bank_account_id)
                    if current_balance < amount:
                        return False, (
                            f"Insufficient funds. Available: ${current_balance:,.2f}, "
                            f"Required: ${amount:,.2f}"
                        )

                dt = datetime.combine(payment_date, datetime.now().time())
                bank_direction = (
                    TransactionDirectionEnum.CREDIT
                    if loan.direction == CashLoanDirectionEnum.GIVEN
                    else TransactionDirectionEnum.DEBIT
                )
                description = (
                    f"Loan repayment from {loan.person_name}"
                    if loan.direction == CashLoanDirectionEnum.GIVEN
                    else f"Loan repayment to {loan.person_name}"
                )
                if notes:
                    description = f"{description} - {notes}"

                bank_tx = self.bank_transaction_service.create_transaction(session, {
                    "bank_account_id": bank_account_id,
                    "transaction_date": payment_date,
                    "direction": bank_direction,
                    "amount": amount,
                    "payment_method": PaymentMethodEnum.TRANSFER,
                    "description": description,
                    "recorded_by_user_id": user_id,
                    "created_at": dt,
                    "last_modified": dt,
                })
                if not bank_tx:
                    raise Exception("Failed to create bank transaction.")

                payment = CashLoanPayment(
                    loan_id=loan.id,
                    payment_date=payment_date,
                    amount=amount,
                    bank_account_id=bank_account_id,
                    bank_transaction_id=bank_tx.id,
                    notes=notes,
                    user_id=user_id,
                    created_at=dt,
                    last_modified=dt,
                )
                session.add(payment)

                loan.paid_amount += amount
                loan.update_status()
                loan.last_modified = dt
                session.commit()
                return True, ""
            except Exception as exc:
                session.rollback()
                logger.error(f"Error recording cash loan repayment: {exc}", exc_info=True)
                return False, f"An error occurred: {exc}"

    def get_open_loans(self) -> List[Dict]:
        with get_session() as session:
            loans = session.query(CashLoan).options(
                joinedload(CashLoan.bank_account)
            ).filter(
                CashLoan.is_deleted == False,
            ).order_by(CashLoan.loan_date.desc(), CashLoan.id.desc()).all()

            rows = []
            for loan in loans:
                remaining = loan.principal_amount - loan.paid_amount
                if remaining <= 0:
                    continue
                rows.append(self._loan_to_row(loan, remaining))
            return rows

    def get_cash_loan_summary(self) -> Dict:
        rows = self.get_open_loans()
        receivable = sum(row["remaining"] for row in rows if row["direction"] == CashLoanDirectionEnum.GIVEN.value)
        payable = sum(row["remaining"] for row in rows if row["direction"] == CashLoanDirectionEnum.RECEIVED.value)
        net = receivable - payable
        if net > 0.01:
            direction = "Net receivable"
        elif net < -0.01:
            direction = "Net payable"
        else:
            direction = "Balanced"
        return {
            "open_count": len(rows),
            "total_receivable": receivable,
            "total_payable": payable,
            "net_balance": net,
            "abs_net_balance": abs(net),
            "net_direction": direction,
        }

    def get_cash_loan_balances_by_person(self) -> List[Dict]:
        rows = self.get_open_loans()
        grouped: Dict[str, Dict] = {}
        for row in rows:
            key = self.build_match_key(row["person_name"], row.get("phone", ""))
            if not key:
                continue

            entry = grouped.setdefault(key, {
                "person_name": row["person_name"],
                "phone": row.get("phone", ""),
                "loan_ids": [],
                "loan_receivable_remaining": 0.0,
                "loan_payable_remaining": 0.0,
            })
            entry["loan_ids"].append(row["loan_id"])
            if row["direction"] == CashLoanDirectionEnum.GIVEN.value:
                entry["loan_receivable_remaining"] += row["remaining"]
            else:
                entry["loan_payable_remaining"] += row["remaining"]

        return list(grouped.values())

    def get_payment_history(self, loan_id: int) -> List[Dict]:
        with get_session() as session:
            payments = session.query(CashLoanPayment).options(
                joinedload(CashLoanPayment.bank_account)
            ).filter(
                CashLoanPayment.loan_id == loan_id,
                CashLoanPayment.is_deleted == False,
            ).order_by(CashLoanPayment.payment_date.desc(), CashLoanPayment.id.desc()).all()

            return [{
                "payment_id": payment.id,
                "payment_date": payment.payment_date,
                "amount": payment.amount,
                "bank_account": self._bank_account_name(payment.bank_account),
                "notes": payment.notes or "",
            } for payment in payments]

    def cancel_loan(self, loan_id: int, user_id: Optional[int] = None) -> Tuple[bool, str]:
        """
        Soft‑delete a loan and its original bank transaction,
        but only if no repayments have been made.
        """
        with get_session() as session:
            try:
                loan = session.query(CashLoan).filter(
                    CashLoan.id == loan_id,
                    CashLoan.is_deleted == False
                ).first()
                if not loan:
                    return False, "Loan not found."

                if loan.paid_amount > 0.01:
                    return False, "Cannot cancel a loan that already has repayments."

                # Soft delete the loan
                loan.is_deleted = True
                loan.last_modified = datetime.now()

                # Soft delete the original bank transaction
                if loan.bank_transaction_id:
                    bank_tx = session.query(BankTransaction).filter(
                        BankTransaction.id == loan.bank_transaction_id,
                        BankTransaction.is_deleted == False
                    ).first()
                    if bank_tx:
                        bank_tx.is_deleted = True
                        bank_tx.last_modified = datetime.now()
                        # Recalculate balances for that account
                        self.bank_transaction_service.recalculate_balances_for_account(
                            session, bank_tx.bank_account_id
                        )

                session.commit()
                return True, ""
            except Exception as exc:
                session.rollback()
                logger.error(f"Error cancelling loan {loan_id}: {exc}", exc_info=True)
                return False, f"An error occurred: {exc}"

    def delete_payment(self, payment_id: int, user_id: int):
        """Delete a loan payment and recalculate the loan balance."""
        try:
            with get_session() as session:
                payment = session.query(CashLoanPayment).filter_by(
                    id=payment_id, is_deleted=False
                ).first()
                if not payment:
                    return False, "Payment not found."

                loan = payment.loan
                if not loan:
                    return False, "Associated loan not found."

                # Soft delete payment
                payment.is_deleted = True

                # Soft delete bank transaction if exists
                if payment.bank_transaction_id:
                    bank_tx = session.query(BankTransaction).filter_by(
                        id=payment.bank_transaction_id
                    ).first()
                    if bank_tx:
                        bank_tx.is_deleted = True

                # FLUSH before recalculating so the sum excludes the deleted payment
                session.flush()

                # Recalculate loan paid amount and remaining
                total_paid = session.query(func.sum(CashLoanPayment.amount)).filter(
                    CashLoanPayment.loan_id == loan.id,
                    CashLoanPayment.is_deleted == False
                ).scalar() or 0.0

                loan.paid_amount = total_paid
                loan.update_status()
                session.commit()
                return True, "Payment deleted successfully."

        except Exception as e:
            logger.error(f"Error deleting payment {payment_id}: {e}")
            return False, str(e)

    def _loan_to_row(self, loan: CashLoan, remaining: float) -> Dict:
        direction_value = loan.direction.value if hasattr(loan.direction, "value") else str(loan.direction)
        status_value = loan.status.value if hasattr(loan.status, "value") else str(loan.status)
        return {
            "loan_id": loan.id,
            "person_name": loan.person_name,
            "phone": loan.phone or "",
            "customer_id": loan.customer_id,
            "supplier_id": loan.supplier_id,
            "direction": direction_value,
            "direction_label": self._direction_label(direction_value),
            "principal_amount": loan.principal_amount,
            "paid_amount": loan.paid_amount,
            "remaining": remaining,
            "status": status_value.capitalize(),
            "loan_date": loan.loan_date,
            "due_date": loan.due_date,
            "bank_account": self._bank_account_name(loan.bank_account),
            "notes": loan.notes or "",
        }

    @staticmethod
    def _direction_label(direction: str) -> str:
        if direction == CashLoanDirectionEnum.GIVEN.value:
            return "YEBEDERKUT"
        return "YETEBEDERKUT"

    @staticmethod
    def _bank_account_name(account) -> str:
        if not account:
            return ""
        if account.bank_name:
            return f"{account.bank_name} - {account.account_name}"
        return account.account_name or ""