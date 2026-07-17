from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey
from models.engine.database import BaseModel

class MarketingCampaignLog(BaseModel):
    __tablename__ = 'marketing_campaign_logs'

    id = Column(Integer, primary_key=True)
    campaign_name = Column(String(100), nullable=False)  # e.g., "Megazen_Monthly_2026_04"
    recipient_type = Column(String(20), nullable=False)   # 'customer' or 'supplier'
    recipient_id = Column(Integer, nullable=False)
    recipient_chat_id = Column(String(50), nullable=False)
    sent_at = Column(DateTime, nullable=False)
    status = Column(String(20), default='sent')  # 'sent', 'failed'
    error_message = Column(String(500))