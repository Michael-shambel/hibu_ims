#!/usr/bin/env python3
from models.engine.database import BaseModel
from sqlalchemy import Column, Integer, Float, Boolean, ForeignKey, String, JSON, Date
from sqlalchemy.orm import relationship


class ProfessionalSale(BaseModel):
    __tablename__ = "professional_sales"


    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    total_amount = Column(Float)
    labour_expense = Column(Float)
    items_data = Column(JSON, nullable=True, default=None)


    is_credit_sale = Column(Boolean, default=False)
    credit_balance = Column(Float, default=0.0) 
    delivery_name = Column(String(50), nullable=True)
    delivery_place = Column(String(50), nullable=True)
    delivery_phone = Column(String(50), nullable=True)
    delivery_Plate = Column(String(50), nullable=True)

    user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)
    despatch_date = Column(Date, nullable=True, index=True)

    customer = relationship("Customer", foreign_keys=[customer_id])

    user = relationship("AuthUser", foreign_keys=[user_id])
    items = relationship("ProfessionalSaleItem", back_populates="sale", cascade="all, delete-orphan")
    payment_terms = relationship("SalePaymentTerm", back_populates="sale", cascade="all, delete-orphan")
