import datetime
from email.policy import default
from tokenize import String

from models.engine.database import BaseModel
from sqlalchemy import Column, String, Integer, Text, SmallInteger, DateTime
from datetime import datetime

class PendingNotification(BaseModel):
    __tablename__ = "pending_notifications"

    notification_type = Column(String(50), nullable=False)
    chat_id = Column(Integer, nullable=False)
    payload_json = Column(Text, nullable=False)
    status = Column(String(20), default="pending")

    retry_count = Column(SmallInteger, default=0)
    max_retries = Column(SmallInteger, default=10)
    next_retry_time = Column(DateTime, default=datetime.utcnow)
    last_error = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<PendingNotification(type={self.notification_type}, chat_id={self.chat_id}, status={self.status})>"