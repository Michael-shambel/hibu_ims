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
    """
    Customer model representing a customer in the database.
    Attributes:
        id (int): Unique identifier for the customer.
        name (str): Name of the customer.
        phone (str): Phone number of the customer.
        email (str): Email address of the customer.
        state (str): State where the customer resides.
        Sub-city (str): Sub-city where the customer resides.
        wereda (str): Wereda where the customer resides.
        kebele (str): Kebele where the customer resides.
        created_at (datetime): Timestamp when the customer was created.
    """
    __tablename__ = 'customers'

    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=True, unique=False)
    tin_num = Column(String(20), nullable=True, unique=False)
    chat_id = Column(BigInteger, nullable=True, unique=False)

    sales = relationship("ProfessionalSale", back_populates="customer")

    def __repr__(self):
        return f"<Customer(id={self.id}, name={self.name})>"