#!/usr/bin/env python3
from models.engine.database import BaseModel
from enum import Enum
from sqlalchemy import Boolean, String, Column, Integer, ForeignKey, Enum as SQLEnum, Float, Date
from sqlalchemy.orm import relationship

class ExpensePaymentMethod(str, Enum):
    CASH = "cash"
    TRANSFER = "transfer"
    CHEQUE = "cheque"

class Expense(BaseModel):
    __tablename__ = 'expenses'

    category_id = Column(Integer, ForeignKey('expense_categories.id'), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(SQLEnum(ExpensePaymentMethod), nullable=False)
    bank_account_id = Column(Integer, ForeignKey('bank_accounts.id'), nullable=True)
    date = Column(Date, nullable=False)
    description = Column(String(255), nullable=False)
    notes = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)
    is_personal = Column(Boolean, default=False, nullable=False)


    category = relationship("ExpenseCategory")
    bank_account = relationship("BankAccount")
    created_by = relationship("AuthUser", foreign_keys=[user_id])


    def __repr__(self):
        return f"<Exepse(id={self.id}, date={self.date}, amount={self.amount}, category='{self.category.name if self.category else ''}')>"
