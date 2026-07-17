#!/usr/bin/env python3
import asyncio
import logging
import json
from pathlib import Path
from datetime import date, timedelta, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from telegrambot.outbox import queue_notification, process_pending_notifications, reset_failed_pending_notifications
from services.marketing_campaign_service import MarketingCampaignService
from services.unusual_sales_alert_service import UnusualSalesAlertService
from ui.components.ethiopian_date import EthiopianDateConverter
from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS
from config import ADMIN_ID
from utils import backup_database, get_backup_dir

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
DATABASE_BACKUP_HOUR = 18
DATABASE_BACKUP_MINUTE = 10


# -------------------------------------------------------------------------
# Safe job wrapper — prevents one crash from silently killing a scheduler job
# -------------------------------------------------------------------------
def _safe_job(coro_func):
    """Wrap an async job so exceptions are logged but never propagate."""
    async def wrapper(*args, **kwargs):
        try:
            await coro_func(*args, **kwargs)
        except Exception as e:
            logger.exception("Scheduler job '%s' failed: %s", coro_func.__name__, e)
    wrapper.__name__ = coro_func.__name__
    return wrapper


# ---------------------------------------------------------------------
# Monthly Profit Report
# ---------------------------------------------------------------------
async def queue_monthly_profit_report():
    """Queue monthly profit report on the first day of an Ethiopian month."""
    today_greg = date.today()
    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(today_greg)
    if eth_day != 1:
        return

    if eth_month == 1:
        prev_year, prev_month = eth_year - 1, 13
    else:
        prev_year, prev_month = eth_year, eth_month - 1

    queue_notification(
        'monthly_profit_report',
        ADMIN_ID,
        {'eth_year': prev_year, 'eth_month': prev_month}
    )
    logger.info("Queued monthly profit report for Ethiopian %d-%02d", prev_year, prev_month)


# ---------------------------------------------------------------------
# Daily Sales Report
# ---------------------------------------------------------------------
async def queue_daily_sales_report(target_date: date = None):
    """Queue a daily sales report for the given date (default today)."""
    if target_date is None:
        target_date = date.today()
    queue_notification(
        'daily_sales_report',
        ADMIN_ID,
        {'target_date': target_date.isoformat()}
    )
    logger.info("Queued daily sales report for %s", target_date)


# ---------------------------------------------------------------------
# Daily Customer Notifications
# ---------------------------------------------------------------------
async def queue_daily_customer_notifications(target_date: date = None):
    """Queue daily credit summaries for all customers with activity on target_date."""
    from services.new_sale_service import NewSaleService
    from telegrambot.bot import notify_customer_sync

    if target_date is None:
        target_date = date.today()

    sale_service = NewSaleService()

    # DB call off the event loop
    customer_ids = await asyncio.to_thread(
        sale_service.get_customers_with_daily_activity, target_date
    )
    logger.info("Found %d customers with daily activity on %s", len(customer_ids), target_date)

    for cid in customer_ids:
        try:
            notify_customer_sync(cid, target_date=target_date)
        except Exception as e:
            logger.error("Failed to queue customer notification for %d: %s", cid, e)
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------
# Daily Supplier Notifications
# ---------------------------------------------------------------------
async def queue_daily_supplier_notifications(target_date: date = None):
    """Queue daily credit summaries for all suppliers with activity on target_date."""
    from services.purchase_service import PurchaseService
    from telegrambot.bot import notify_supplier_purchase_sync

    if target_date is None:
        target_date = date.today()

    purchase_service = PurchaseService()

    # DB call off the event loop
    supplier_ids = await asyncio.to_thread(
        purchase_service.get_suppliers_with_daily_activity, target_date
    )
    logger.info("Found %d suppliers with daily activity on %s", len(supplier_ids), target_date)

    for sid in supplier_ids:
        try:
            notify_supplier_purchase_sync(sid, target_date=target_date)
        except Exception as e:
            logger.error("Failed to queue supplier notification for %d: %s", sid, e)
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------
# Startup catch-up: replay missed days while the app was down
# ---------------------------------------------------------------------
async def startup_catchup():
    """Queue any daily reports missed while the bot was offline."""
    logger.info("Running startup catch-up for missed notifications...")
    from services.base_service import get_session
    from models.pending_notification import PendingNotification

    try:
        with get_session() as session:
            last_sent = session.query(PendingNotification.payload_json).filter(
                PendingNotification.notification_type == 'daily_sales_report',
                PendingNotification.status == 'sent'
            ).order_by(PendingNotification.created_at.desc()).first()

            if last_sent:
                try:
                    payload = json.loads(last_sent[0])
                    last_date_str = payload.get('target_date')
                    last_date = (
                        datetime.strptime(last_date_str, '%Y-%m-%d').date()
                        if last_date_str else None
                    )
                except Exception:
                    last_date = None
            else:
                last_date = None

        if last_date is None:
            logger.info("No previous sent sales report found, skipping catch-up.")
            return

        today = date.today()
        yesterday = today - timedelta(days=1)
        now = datetime.now()

        missing_dates = []
        d = last_date + timedelta(days=1)

        while d <= yesterday:
            missing_dates.append(d)
            d += timedelta(days=1)

        # Include today only if past the 18:30 scheduled time
        if d == today and (now.hour > 18 or (now.hour == 18 and now.minute >= 30)):
            missing_dates.append(today)

        if not missing_dates:
            logger.info("No missing days to catch up.")
            return

        logger.info(
            "Catching up %d missed days: %s ... %s",
            len(missing_dates), missing_dates[0], missing_dates[-1]
        )

        for day in missing_dates:
            try:
                await queue_daily_sales_report(target_date=day)
                await queue_daily_customer_notifications(target_date=day)
                await queue_daily_supplier_notifications(target_date=day)
            except Exception as e:
                logger.error("Catch-up failed for %s: %s", day, e)
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.exception("startup_catchup failed entirely: %s", e)


# ---------------------------------------------------------------------
# Marketing campaign
# ---------------------------------------------------------------------
async def run_monthly_marketing_campaign(bot_token: str):
    """Run the pre-configured Megazen marketing campaign."""
    campaign_service = MarketingCampaignService(bot_token)
    await campaign_service.run_campaign()


# ---------------------------------------------------------------------
# Daily Database Backup
# ---------------------------------------------------------------------
async def queue_daily_database_backup():
    """Create a daily backup of the active SQLite database."""
    backup_file = await asyncio.to_thread(backup_database)
    logger.info("Created database backup at %s", backup_file)


async def startup_backup_catchup():
    """Create today's backup on startup if the scheduled run was missed."""
    now = datetime.now()
    scheduled_time = now.replace(hour=DATABASE_BACKUP_HOUR, minute=DATABASE_BACKUP_MINUTE, second=0, microsecond=0)

    if now < scheduled_time:
        return

    backup_dir = Path(get_backup_dir())
    today_prefix = now.strftime('%Y%m%d')
    existing_backups = list(backup_dir.glob(f'db_backup_{today_prefix}_*.db'))
    if existing_backups:
        return

    await queue_daily_database_backup()


# ---------------------------------------------------------------------
# Scheduler Setup
# ---------------------------------------------------------------------
def start_scheduler(bot_token: str):
    """Configure and start all APScheduler jobs."""
    config_path = Path(__file__).parent.parent / "assets" / "marketing" / "monthly_campaign.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    schedule = config['schedule']

    # Monthly marketing campaign
    scheduler.add_job(
        _safe_job(run_monthly_marketing_campaign),
        trigger=CronTrigger(
            day=schedule['day_of_month'],
            hour=schedule['hour'],
            minute=schedule['minute']
        ),
        args=[bot_token],
        id='monthly_marketing_campaign',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Daily sales report to admin
    scheduler.add_job(
        _safe_job(queue_daily_sales_report),
        trigger=CronTrigger(hour=18, minute=10),
        id='daily_sales_report_admin',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Daily database backup
    scheduler.add_job(
        _safe_job(queue_daily_database_backup),
        trigger=CronTrigger(hour=DATABASE_BACKUP_HOUR, minute=DATABASE_BACKUP_MINUTE),
        id='daily_database_backup',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Unusual sales cache refresh
    scheduler.add_job(
        _safe_job(UnusualSalesAlertService.refresh_cache),
        trigger=CronTrigger(hour=2, minute=0),
        id='refresh_unusual_sales_cache',
        replace_existing=True,
        misfire_grace_time=3600
    )

    # Outbox retry worker — every 10 seconds
    scheduler.add_job(
        _safe_job(process_pending_notifications),
        trigger=IntervalTrigger(seconds=10),
        id='process_pending_notifications',
        replace_existing=True,
        misfire_grace_time=20,
        max_instances=1
    )

    # Reset stuck notifications every 30 minutes
    scheduler.add_job(
        _safe_job(reset_failed_pending_notifications),
        trigger=IntervalTrigger(minutes=30),
        id='reset_stuck_notifications',
        replace_existing=True,
        misfire_grace_time=300
    )

    scheduler.start()
    logger.info("Scheduler started with outbox retry, reset, and backup jobs.")


def stop_scheduler():
    """Shutdown the scheduler gracefully."""
    scheduler.shutdown()
    logger.info("Scheduler stopped.")