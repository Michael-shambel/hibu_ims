from sqlalchemy import Column, Integer, Float, String, Date, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import date
from enum import Enum
from models.engine.database import BaseModel


class PaymentStatusEnum(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    CREDIT = "credit"

class SalePaymentTerm(BaseModel):
    __tablename__ = "sale_payments_terms"

    sale_id = Column(Integer, ForeignKey('professional_sales.id'), nullable=False)
    payment_status = Column(SQLEnum(PaymentStatusEnum, native_enum=False), default=PaymentStatusEnum.PENDING)


    total_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0.0)
    due_date = Column(Date, nullable=True)

    sale = relationship("ProfessionalSale", back_populates="payment_terms")
    payment_transactions = relationship("PaymentTransaction", back_populates="payment_term", cascade="all, delete-orphan")

    @property
    def balance_amount(self):
        return self.total_amount - self.paid_amount

    def update_status(self):
        bal = self.balance_amount
        if self.paid_amount <= 0:
            self.payment_status = PaymentStatusEnum.PENDING
        elif bal <= 0:
            self.payment_status = PaymentStatusEnum.PAID
            self.paid_amount = self.total_amount
        else:
            self.payment_status = PaymentStatusEnum.PARTIAL


    def __repr__(self):
        return f"<SalePaymentTerm(id={self.id}, sale={self.sale_id}, total={self.total_amount:.2f}, paid={self.paid_amount:.2f}, status={self.payment_status})>"
