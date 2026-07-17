#!/usr/bin/env python3

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Enum as SQLEnum, Date
from models.engine.database import BaseModel
from sqlalchemy.orm import relationship
from enum import Enum

class AccountTypeEnum(str, Enum):
    INVOICE = "invoice"
    NON_INVOICE = "non_invoice"
class BankAccount(BaseModel):
    __tablename__ = 'bank_accounts'

    account_name = Column(String(100))
    bank_name = Column(String(100))
    account_number = Column(String(50))
    account_type = Column(SQLEnum(AccountTypeEnum), nullable=False, default=AccountTypeEnum.INVOICE)
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)
    reset_date = Column(Date, nullable=True)

    user = relationship("AuthUser", foreign_keys=[user_id])

    payment_transactions = relationship("PaymentTransaction", back_populates="bank_account")
    transactions = relationship("BankTransaction", back_populates="bank_account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BankAccount(id={self.id}, name='{self.account_name}', type='{self.account_type}')>"