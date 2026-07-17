#!/usr/bin/env python3
from models.engine.database import BaseModel
from sqlalchemy.types import Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy import Column, ForeignKey, Integer, String, Text
from enum import Enum

class TransactionType(Enum):
    RECEIVED = "received"
    SALE = "sale"
    RETURN = "return"
    EXPIRED = "expired"
    DAMAGE = "damage"
    ADJUSTMENT = "adjustment"
    STOCK_IN = "stock_in"

class BatchTransaction(BaseModel):
    __tablename__ = "batch_transactions"

    batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    transaction_type = Column(SQLEnum(TransactionType, name="transaction_type", validate_strings=True), nullable=False)

    reference_number = Column(String(100), nullable=True)

    user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)
    notes = Column(Text, nullable=True)

    batch = relationship("ProductBatch", back_populates="transactions")
    user = relationship("AuthUser", foreign_keys=[user_id])

    def __repr__(self):
        return f"<BatchTransaction(batch_id={self.batch_id}, type={self.transaction_type}, qty={self.quantity})>"