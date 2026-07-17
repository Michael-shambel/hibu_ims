#!/usr/bin/env python3

from models.engine.database import BaseModel
from sqlalchemy import Column, Integer, ForeignKey, Float, Boolean, String, Date, JSON
from sqlalchemy.orm import relationship

class Purchase(BaseModel):
    __tablename__ = 'purchases'   # lowercase for consistency

    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    total_amount = Column(Float, nullable=False, default=0.0)
    is_credit_sale = Column(Boolean, default=False)
    purchase_date = Column(Date, nullable=True)
    items_data = Column(JSON, nullable=True)

    supplier = relationship("Supplier", back_populates="purchases")
    batches = relationship("ProductBatch", back_populates="purchase", cascade="all, delete-orphan")   # one-to-many
    payment_terms = relationship("PurchasePaymentTerm", back_populates="purchase", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Purchase(id={self.id}, supplier_id={self.supplier_id}, total={self.total_amount})>"