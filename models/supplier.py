#!/usr/bin/env python3
"""
Supplier Model
Defines the Supplier model for the inventory management system.
"""

from sqlalchemy import Column, String, Text, BigInteger, JSON
from sqlalchemy.orm import relationship
from models.engine.database import BaseModel

class Supplier(BaseModel):
    __tablename__ = 'suppliers'

    supplier_name = Column(String(100), nullable=False, unique=False)
    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    email = Column(String(50), unique=False)
    address = Column(Text, nullable=True)
    chat_id = Column(BigInteger, nullable=True, unique=True)
    additional_chat_ids = Column(JSON, nullable=True)


    purchases = relationship("Purchase", back_populates="supplier", cascade="all, delete-orphan")

    daily_notifications = relationship("SupplierDailyNotification", back_populates="supplier")

    def __repr__(self):
        return f"<Supplier(id={self.id}, name='{self.supplier_name}')>"

    def __str__(self):
        return f"{self.supplier_name} ({self.contact_phone or 'No phone'})"
