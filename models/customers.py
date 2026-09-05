#!/usr/bin/env python3
"""
models/customers.py
This module defines the Customer model for the database.
It includes fields for customer details such as name, phone, email, and address.
"""
from sqlalchemy import Column, String, BigInteger
from models.engine.database import BaseModel
from sqlalchemy.orm import relationship

class Customer(BaseModel):
    __tablename__ = 'customers'

    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=True, unique=False)
    tin_num = Column(String(20), nullable=True, unique=False)
    chat_id = Column(BigInteger, nullable=True, unique=False)

    sales = relationship("ProfessionalSale", back_populates="customer")

    def __repr__(self):
        return f"<Customer(id={self.id}, name={self.name})>"