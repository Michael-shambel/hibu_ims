#!/usr/bin/env python3
"""SubscriberGroup – assigns a product group to a report subscriber."""
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from models.engine.database import BaseModel


class SubscriberGroup(BaseModel):
    __tablename__ = 'subscriber_product_groups'

    subscriber_id = Column(Integer, ForeignKey('report_subscribers.id'), nullable=False)
    product_group_id = Column(Integer, ForeignKey('product_groups.id'), nullable=False)

    __table_args__ = (
        UniqueConstraint('subscriber_id', 'product_group_id', name='uq_subscriber_product_group'),
    )

    subscriber = relationship("ReportSubscriber", back_populates="group_links")
    group = relationship("ProductGroup", back_populates="subscriber_links")

    def __repr__(self):
        return f"<SubscriberGroup(subscriber={self.subscriber_id}, group={self.product_group_id})>"
