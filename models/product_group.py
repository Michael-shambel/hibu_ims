#!/usr/bin/env python3
"""
ProductGroup model – a named, reusable set of products.

One group can be assigned to many report subscribers, and a product can belong
to several groups. Groups are the unit that scopes a report: a subscriber limited
to "Group A" only sees Group A's products (and the expenses tagged to Group A).
"""
from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import relationship

from models.engine.database import BaseModel


class ProductGroup(BaseModel):
    __tablename__ = 'product_groups'

    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    members = relationship(
        "ProductGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )
    subscriber_links = relationship(
        "SubscriberGroup",
        back_populates="group",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ProductGroup(id={self.id}, name='{self.name}')>"
