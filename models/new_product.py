#!/usr/bin/env python3
from models.engine.database import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Float, UniqueConstraint
from sqlalchemy.orm import relationship


class ProfessionalProduct(BaseModel):
    """
    """
    __tablename__ = 'professional_products'

    name = Column(String(200), nullable=False, index=True)
    normalized_name = Column(String(200), nullable=False, index=True)
    selling_price = Column(Float, nullable=True)
    unit = Column(String(50), nullable=False)
    normalized_unit = Column(String(50), nullable=False, index=True)
    dozen = Column(Float, default=1.0, nullable=False)
    require_batch_tracking = Column(Boolean, default=True, nullable=False)
    total_quantity = Column(Integer, default=0, nullable=False)
    available_quantity = Column(Integer, default=0, nullable=False)
    user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)
    supplier_sku = Column(String(100), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint('normalized_name', 'normalized_unit', name='uq_product_normalized'),
    )



    batches = relationship("ProductBatch", back_populates="product", 
                          cascade="all, delete-orphan", lazy='dynamic')
    user = relationship("AuthUser", foreign_keys=[user_id])

    def update_totals(self):
        batches = self.batches.filter_by(is_deleted=False).all()
        self.total_quantity = sum(b.quantity for b in batches)
        self.available_quantity = sum(b.available_quantity for b in batches)

    def __repr__(self):
        return f"<ProfessionalProduct(id={self.id}, name='{self.name}', available={self.available_quantity})>"