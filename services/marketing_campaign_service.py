# services/marketing_campaign_service.py
import json
import os
import logging
import asyncio
from datetime import date, datetime
from pathlib import Path

from services.customer_service import CustomerService
from services.supplier_service import SupplierService
from models.marketing_campaign_log import MarketingCampaignLog
from services.base_service import get_session

logger = logging.getLogger(__name__)

class MarketingCampaignService:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.customer_service = CustomerService()
        self.supplier_service = SupplierService()
        self.config = self._load_config()
    
    def _load_config(self):
        config_path = Path(__file__).parent.parent / "assets" / "marketing" / "monthly_campaign.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_assets_path(self):
        return Path(__file__).parent.parent / "assets" / "marketing"
    
    def get_all_recipients(self):
        """Return all customers and suppliers with chat_id, including additional controllers."""
        recipients = []
        
        # Customers (unchanged)
        customers = self.customer_service.get_all()
        for c in customers:
            if c.chat_id:
                recipients.append({
                    'id': c.id,
                    'chat_id': c.chat_id,
                    'name': c.name,
                    'type': 'customer'
                })
        
        # Suppliers – include primary + additional chat IDs
        suppliers = self.supplier_service.get_all()
        for s in suppliers:
            # Get all notification chat IDs for this supplier
            chat_ids = self.supplier_service.get_all_notification_chat_ids(s.id)
            for chat_id in chat_ids:
                recipients.append({
                    'id': s.id,
                    'chat_id': chat_id,
                    'name': s.supplier_name,
                    'type': 'supplier'
                })
        
        return recipients
    
    def already_received_campaign(self, recipient_type: str, recipient_id: int, campaign_name: str) -> bool:
        """Check if this recipient already got this campaign."""
        with get_session() as session:
            exists = session.query(MarketingCampaignLog).filter(
                MarketingCampaignLog.campaign_name == campaign_name,
                MarketingCampaignLog.recipient_type == recipient_type,
                MarketingCampaignLog.recipient_id == recipient_id,
                MarketingCampaignLog.status == 'sent'
            ).first()
            return exists is not None
    
    def log_campaign_sent(self, recipient_type: str, recipient_id: int, chat_id: str,
                      campaign_name: str, status: str, error: str = None):
        with get_session() as session:
            log = MarketingCampaignLog(
                campaign_name=campaign_name,
                recipient_type=recipient_type,
                recipient_id=recipient_id,
                recipient_chat_id=str(chat_id),
                sent_at=datetime.now(),
                status=status,
                error_message=error[:500] if error else None
            )
            session.add(log)
            session.commit()
    
    async def run_campaign(self):
        """Main campaign execution."""
        from telegram import Bot
        from telegram.error import TelegramError
        
        bot = Bot(token=self.bot_token)
        campaign_name = f"{self.config['campaign_name']}_{date.today().strftime('%Y_%m')}"
        
        recipients = self.get_all_recipients()
        logger.info(f"Starting marketing campaign '{campaign_name}' for {len(recipients)} recipients")
        
        assets_path = self._get_assets_path()
        success_count = 0
        
        # Group recipients by (type, id) to avoid duplicate campaign checks per chat_id
        grouped = {}
        for r in recipients:
            key = (r['type'], r['id'])
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(r)
        
        for (recipient_type, recipient_id), entries in grouped.items():
            # Check campaign already sent for this recipient (any chat_id)
            if self.already_received_campaign(recipient_type, recipient_id, campaign_name):
                name = entries[0]['name']
                logger.debug(f"Skipping {recipient_type} {recipient_id} ({name}) – already received {campaign_name}")
                continue
            
            # Send to all chat IDs for this recipient
            sent_any = False
            last_error = None
            for r in entries:
                try:
                    for msg in self.config['messages']:
                        if msg['type'] == 'text':
                            await bot.send_message(
                                chat_id=r['chat_id'],
                                text=msg['content'],
                                parse_mode='Markdown'
                            )
                        elif msg['type'] == 'voice':
                            voice_path = assets_path / msg['file']
                            with open(voice_path, 'rb') as voice_file:
                                await bot.send_voice(
                                    chat_id=r['chat_id'],
                                    voice=voice_file.read(),
                                    caption=msg.get('caption', '')
                                )
                        elif msg['type'] == 'photo':
                            photo_path = assets_path / msg['file']
                            with open(photo_path, 'rb') as photo_file:
                                await bot.send_photo(
                                    chat_id=r['chat_id'],
                                    photo=photo_file.read(),
                                    caption=msg.get('caption', '')
                                )
                        
                        await asyncio.sleep(0.5)  # Small delay between messages to same recipient
                    
                    sent_any = True
                    logger.info(f"Campaign message sent to {r['type']} {r['name']} ({r['chat_id']})")
                    
                except TelegramError as e:
                    logger.error(f"Telegram error for {r['chat_id']}: {e}")
                    last_error = str(e)
                except Exception as e:
                    logger.exception(f"Unexpected error for {r['chat_id']}: {e}")
                    last_error = str(e)
            
            # Log once per recipient (not per chat_id)
            if sent_any:
                self.log_campaign_sent(recipient_type, recipient_id, entries[0]['chat_id'], campaign_name, 'sent')
                success_count += 1
            else:
                self.log_campaign_sent(recipient_type, recipient_id, entries[0]['chat_id'], campaign_name, 'failed', last_error)
            
            await asyncio.sleep(0.1)  # Rate limit between recipients
        
        logger.info(f"Campaign '{campaign_name}' complete: {success_count}/{len(grouped)} successful")