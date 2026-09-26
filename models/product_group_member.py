#!/usr/bin/env python3
"""ProductGroupMember – joins a professional product to a product group."""
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from models.engine.database import BaseModel


class ProductGroupMember(BaseModel):
    __tablename__ = 'product_group_members'

    product_group_id = Column(Integer, ForeignKey('product_groups.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('professional_products.id'), nullable=False)

    __table_args__ = (
        UniqueConstraint('product_group_id', 'product_id', name='uq_product_group_member'),
    )

    group = relationship("ProductGroup", back_populates="members")
    product = relationship("ProfessionalProduct")

    def __repr__(self):
        return f"<ProductGroupMember(group={self.product_group_id}, product={self.product_id})>"
