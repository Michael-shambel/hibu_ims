#!/usr/bin/env python3
"""
ReportSubscriber model – one report recipient.

A subscriber is identified by a Telegram chat_id. It may be linked to an admin
account (`auth_user_id`) or be external (a partner/agent who never logs into the
app). `full_report=True` means "ignore product groups, send everything"; when it
is False the subscriber's `group_links` decide which products and which expenses
appear in their reports.

A subscriber in several groups receives ONE merged report (union of products,
union of expense tags).
"""
from sqlalchemy import Column, String, BigInteger, Boolean, Integer, ForeignKey
from sqlalchemy.orm import relationship

from models.engine.database import BaseModel


class ReportSubscriber(BaseModel):
    __tablename__ = 'report_subscribers'

    display_name = Column(String(150), nullable=False)
    chat_id = Column(BigInteger, nullable=False, unique=True)
    auth_user_id = Column(Integer, ForeignKey('auth_users.id'), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    full_report = Column(Boolean, default=True, nullable=False)

    receive_daily = Column(Boolean, default=True, nullable=False)
    receive_monthly = Column(Boolean, default=True, nullable=False)
    receive_quarterly = Column(Boolean, default=True, nullable=False)
    receive_semiannual = Column(Boolean, default=True, nullable=False)
    receive_annual = Column(Boolean, default=True, nullable=False)

    notes = Column(String(255), nullable=True)

    auth_user = relationship("AuthUser")
    group_links = relationship(
        "SubscriberGroup",
        back_populates="subscriber",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        scope = "full" if self.full_report else "partial"
        return f"<ReportSubscriber(id={self.id}, name='{self.display_name}', scope={scope})>"
