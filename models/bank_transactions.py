from sqlalchemy import Column, Integer, Float, Date, String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from models.engine.database import BaseModel

class TransactionDirectionEnum(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"

class PaymentMethodEnum(str, Enum):
    CASH = "cash"
    TRANSFER = "transfer"
    CHEQUE = "cheque"

class BankTransaction(BaseModel):
    __tablename__ = 'bank_transactions'

    bank_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=False)
    transaction_date = Column(Date, nullable=False)
    direction = Column(SQLEnum(TransactionDirectionEnum, native_enum=False), nullable=False)
    amount = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)  # store balance after transaction
    payment_method = Column(SQLEnum(PaymentMethodEnum, native_enum=False), nullable=True)
    description = Column(String(255), nullable=True)
    reference_number = Column(String(100), nullable=True)
    cheque_number = Column(String(100), nullable=True)

    sale_payment_term_id = Column(Integer, ForeignKey('sale_payments_terms.id'), nullable=True)
    purchase_payment_term_id = Column(Integer, ForeignKey('purchase_payments_terms.id'), nullable=True)
    expense_id = Column(Integer, ForeignKey('expenses.id'), nullable=True)
    recorded_by_user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)

    bank_account = relationship("BankAccount", back_populates="transactions")
    sale_payment_term = relationship("SalePaymentTerm")
    purchase_payment_term = relationship("PurchasePaymentTerm")
    expense = relationship("Expense", foreign_keys=[expense_id])
    recorded_by = relationship("AuthUser", foreign_keys=[recorded_by_user_id])

    def __repr__(self):
        return f"<BankTransaction(id={self.id}, type={self.direction}, amount={self.amount:.2f}, balance_after={self.balance_after:.2f}, account={self.bank_account_id})>"
