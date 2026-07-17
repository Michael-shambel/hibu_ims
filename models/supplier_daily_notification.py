# models/supplier_daily_notification.py
from sqlalchemy import Column, Integer, BigInteger, Date, DateTime, String, ForeignKey, func
from sqlalchemy.orm import relationship
from models.engine.database import BaseModel

class SupplierDailyNotification(BaseModel):
    __tablename__ = 'supplier_daily_notifications'

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id', ondelete='CASCADE'), nullable=False, index=True)
    notification_date = Column(Date, nullable=False, index=True)
    sent_at = Column(DateTime, server_default=func.now())
    status = Column(String(20), default='sent')
    error_message = Column(String(500), nullable=True)

    # Relationship to Supplier (optional but useful)
    supplier = relationship("Supplier", back_populates="daily_notifications")