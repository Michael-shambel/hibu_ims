# models/customer_daily_notification.py
from sqlalchemy import Column, Integer, Date, DateTime, String, ForeignKey, func
from sqlalchemy.orm import relationship
from models.engine.database import BaseModel

class CustomerDailyNotification(BaseModel):
    __tablename__ = 'customer_daily_notifications'

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    notification_date = Column(Date, nullable=False, index=True)
    sent_at = Column(DateTime, server_default=func.now())
    status = Column(String(20), default='sent')   # 'sent', 'failed'
    error_message = Column(String(500), nullable=True)

    customer = relationship("Customer", backref="daily_notifications")