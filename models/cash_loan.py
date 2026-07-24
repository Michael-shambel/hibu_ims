#!/usr/bin/env python3
from enum import Enum

from sqlalchemy import Column, Date, Enum as SQLEnum, Float, ForeignKey, Integer, String, Index
from sqlalchemy.orm import relationship

from models.engine.database import BaseModel


class CashLoanDirectionEnum(str, Enum):
    GIVEN = "given"
    RECEIVED = "received"


class CashLoanStatusEnum(str, Enum):
    OUTSTANDING = "outstanding"
    PARTIAL = "partial"
    PAID = "paid"


class CashLoan(BaseModel):
    __tablename__ = "cash_loans"

    person_name = Column(String(100), nullable=False, index=True)
    phone = Column(String(30), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    direction = Column(SQLEnum(CashLoanDirectionEnum, native_enum=False), nullable=False)
    status = Column(
        SQLEnum(CashLoanStatusEnum, native_enum=False),
        nullable=False,
        default=CashLoanStatusEnum.OUTSTANDING,
    )
    principal_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, nullable=False, default=0.0)
    loan_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=True)
    notes = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey("auth_users.id"), nullable=True)

    customer = relationship("Customer")
    supplier = relationship("Supplier")
    bank_account = relationship("BankAccount")
    bank_transaction = relationship("BankTransaction")
    recorded_by = relationship("AuthUser", foreign_keys=[user_id])
    payments = relationship("CashLoanPayment", back_populates="loan", cascade="all, delete-orphan")

    # 🔥 New composite index for fast name+phone lookups
    __table_args__ = (
        Index('idx_cash_loan_name_phone', 'person_name', 'phone'),
    )

    @property
    def remaining_amount(self):
        return self.principal_amount - self.paid_amount

    def update_status(self):
        remaining = self.remaining_amount
        if remaining <= 0:
            self.status = CashLoanStatusEnum.PAID
            self.paid_amount = self.principal_amount
        elif self.paid_amount > 0:
            self.status = CashLoanStatusEnum.PARTIAL
        else:
            self.status = CashLoanStatusEnum.OUTSTANDING


class CashLoanPayment(BaseModel):
    __tablename__ = "cash_loan_payments"

    loan_id = Column(Integer, ForeignKey("cash_loans.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=True)
    notes = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey("auth_users.id"), nullable=True)

    loan = relationship("CashLoan", back_populates="payments")
    bank_account = relationship("BankAccount")
    bank_transaction = relationship("BankTransaction")
    recorded_by = relationship("AuthUser", foreign_keys=[user_id])