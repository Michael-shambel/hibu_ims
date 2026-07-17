#!/usr/bin/env python3
from models.engine.database import BaseModel

from sqlalchemy import Column, Integer, Float, Date, String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum


class PaymentStatusEnum(str, Enum):
    PAID = "paid"
    CREDIT = "credit"
    PARTIAL = "partial"
    PENDING = "pending"

class PurchasePaymentTerm(BaseModel):
    __tablename__ = "purchase_payments_terms"

    purchase_id = Column(Integer, ForeignKey('purchases.id'), nullable=False)
    payment_status = Column(SQLEnum(PaymentStatusEnum, native_enum=False), default=PaymentStatusEnum.PENDING)


    total_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0.0)


    purchase = relationship("Purchase", back_populates="payment_terms")
    purchase_payment_transaction = relationship("PurchasePaymentTransaction", back_populates="purchase_term", cascade="all, delete-orphan")


    @property
    def balance_amount(self):
        return self.total_amount - self.paid_amount

    def update_status(self):
        bal = self.balance_amount
        if self.paid_amount <= 0:
            self.payment_status = PaymentStatusEnum.CREDIT
        elif bal <= 0:
            self.payment_status = PaymentStatusEnum.PAID
            self.paid_amount = self.total_amount
        else:
            self.payment_status = PaymentStatusEnum.PARTIAL