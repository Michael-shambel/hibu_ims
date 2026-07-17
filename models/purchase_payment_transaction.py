#!/usr/bin/env python3
from sqlalchemy import Column, Integer, Float, Date, String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from models.engine.database import BaseModel

class PaymentMethodEnum(str, Enum):
    CASH = "cash"
    TRANSFER = "transfer"
    CHEQUE = "cheque"
    SURPLUS = "surplus"

class PurchasePaymentTransaction(BaseModel):
    __tablename__ = "purchase_payment_transaction"

    purchase_payments_term_id = Column(Integer, ForeignKey('purchase_payments_terms.id'), nullable=False)
    payment_date = Column(Date, nullable=False)
    payment_method = Column(SQLEnum(PaymentMethodEnum, native_enum=False), nullable=False)
    amount = Column(Float, nullable=False)
    bank_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)
    notes = Column(String(255), nullable=True)
    bank_transaction_id = Column(Integer, ForeignKey('bank_transactions.id'), nullable=True)




    purchase_term = relationship("PurchasePaymentTerm", back_populates="purchase_payment_transaction")
    bank_account = relationship("BankAccount")
    recorded_by = relationship("AuthUser", foreign_keys=[user_id])
    bank_transaction = relationship("BankTransaction", foreign_keys=[bank_transaction_id])