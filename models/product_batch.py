#!/usr/bin/env python3
from models.engine.database import  BaseModel
from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum

class ProductBatch(BaseModel):
    __tablename__ = 'product_batches'

    product_id = Column(Integer, ForeignKey('professional_products.id'), nullable=False)
    purchase_id = Column(Integer, ForeignKey('purchases.id'), nullable=True)
    quantity = Column(Integer, nullable=False)
    available_quantity = Column(Integer, nullable=False)
    cost_price = Column(Float, nullable=True)



    product = relationship("ProfessionalProduct", back_populates="batches")
    transactions = relationship("BatchTransaction", back_populates="batch", 
                               cascade="all, delete-orphan")
    purchase = relationship("Purchase", back_populates="batches")
    
    def __repr__(self):
        return f"<ProductBatch(id={self.id}, batch='{self.batch_number}', available={self.available_quantity})>"