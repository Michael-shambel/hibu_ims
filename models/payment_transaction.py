from sqlalchemy import Column, Integer, Float, Date, String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from models.engine.database import BaseModel


class PaymentMethodEnum(str, Enum):
    CASH = "cash"
    TRANSFER = "transfer"
    CHEQUE = "cheque"

class PaymentTransaction(BaseModel):
    __tablename__ = 'payment_transactions'

    sale_payment_term_id = Column(Integer, ForeignKey('sale_payments_terms.id'), nullable=False)
    payment_date = Column(Date, nullable=False)
    payment_method = Column(SQLEnum(PaymentMethodEnum, native_enum=False), nullable=False)
    amount = Column(Float, nullable=False)
    notes = Column(String(255), nullable=True)

    bank_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=True)

    user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)

    payment_term = relationship("SalePaymentTerm", back_populates="payment_transactions")
    bank_account = relationship("BankAccount")
    recorded_by = relationship("AuthUser", foreign_keys=[user_id])

    def __repr__(self):
        return f"<PaymentTransaction(id={self.id}, amount={self.amount:.2f}, date={self.payment_date}, method={self.payment_method})>"
