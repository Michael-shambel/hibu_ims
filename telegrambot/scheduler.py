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
# Database backups run twice a day. Any slot missed because the app/PC was off
# is replayed by startup_backup_catchup() on the next launch.
DATABASE_BACKUP_SLOTS = ((13, 0), (18, 0))
DATABASE_BACKUP_HOURS = ','.join(str(hour) for hour, _ in DATABASE_BACKUP_SLOTS)
DATABASE_BACKUP_MINUTES = ','.join(sorted({str(minute) for _, minute in DATABASE_BACKUP_SLOTS}))


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
# Helper: get all admin chat_ids (with ADMIN_ID fallback)
# ---------------------------------------------------------------------
def _get_all_admin_chat_ids() -> list:
    """Return chat_ids of all registered admins. Falls back to [ADMIN_ID] if none."""
    from services.auth_service import AuthService
    try:
        auth_svc = AuthService()
        chat_ids = auth_svc.get_all_admin_chat_ids()
        if chat_ids:
            return chat_ids
    except Exception as e:
        logger.warning("Could not fetch admin chat_ids: %s", e)
    return [ADMIN_ID]


# ---------------------------------------------------------------------
# Helper: resolve report recipients (product-scoped subscribers + admins)
# ---------------------------------------------------------------------
def _get_report_recipients(report_type: str) -> list:
    """
    Recipients of `report_type`, each carrying its own product scope.

    A subscriber limited to product groups gets `product_ids`/`group_ids`;
    everyone else (including admins with no subscription row) gets the full
    company report. Falls back to ADMIN_ID when nothing can be resolved, which
    keeps the pre-feature behaviour on an empty database.
    """
    from services.report_subscription_service import (
        ReportSubscriptionService, full_recipient,
    )
    try:
        recipients = ReportSubscriptionService().get_recipients(report_type)
        if recipients:
            return recipients
        logger.warning("No recipients found for '%s', falling back to ADMIN_ID", report_type)
    except Exception as e:
        logger.warning("Could not resolve recipients for '%s': %s", report_type, e)
    return [full_recipient(ADMIN_ID)]


# ---------------------------------------------------------------------
# Profit Report (periodic — daily / monthly / quarterly / semiannual / annual)
# ---------------------------------------------------------------------
async def queue_profit_report(
    period_type: str,
    period_label: str,
    start_date: date,
    end_date: date,
):
    """Queue a profit report PDF to every subscriber, scoped to their products."""
    recipients = _get_report_recipients(period_type)
    for recipient in recipients:
        payload = {
            'period_type': period_type,
            'period_label': period_label,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'scope': recipient.to_payload(),
        }
        queue_notification('profit_report', recipient.chat_id, payload)
    logger.info(
        "Queued %s profit report to %d recipient(s) (%d scoped)",
        period_type, len(recipients), sum(1 for r in recipients if not r.is_full),
    )


# --- Pure Ethiopian-calendar helpers (unit-testable, no side effects) ---
PROFIT_PERIOD_TYPES = ('monthly', 'quarterly', 'semiannual', 'annual')


def _prev_eth_month(year: int, month: int):
    return (year - 1, 13) if month == 1 else (year, month - 1)


def _shift_eth_month(year: int, month: int, delta: int):
    """Shift an Ethiopian (year, month) by delta months (every year has 13)."""
    total = year * 13 + (month - 1) + delta
    return total // 13, (total % 13) + 1


def _eth_month_bounds(year: int, month: int):
    """Gregorian (first_day, last_day) of an Ethiopian month."""
    start = EthiopianDateConverter.to_gregorian(year, month, 1)
    if month == 13:
        nxt = EthiopianDateConverter.to_gregorian(year + 1, 1, 1)
    else:
        nxt = EthiopianDateConverter.to_gregorian(year, month + 1, 1)
    return start, nxt - timedelta(days=1)


def profit_report_day_matches(period_type: str, eth_year: int, eth_month: int, eth_day: int) -> bool:
    """True when this Ethiopian calendar day is the send day for the period type."""
    if period_type == 'monthly':
        return eth_day == 1
    if period_type == 'quarterly':
        return eth_day == 1 and eth_month in (1, 4, 7, 10)
    if period_type == 'semiannual':
        return eth_day == 1 and eth_month in (1, 7)
    if period_type == 'annual':
        return eth_day == 1 and eth_month == 1
    return False


def profit_report_range(period_type: str, today_greg: date = None):
    """
    Return (period_label, start_date, end_date) for the period that just ended,
    or None when today is not the send day for this period type.
    """
    if today_greg is None:
        today_greg = date.today()

    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(today_greg)
    if not profit_report_day_matches(period_type, eth_year, eth_month, eth_day):
        return None

    if period_type == 'monthly':
        y, m = _prev_eth_month(eth_year, eth_month)
        start, end = _eth_month_bounds(y, m)
        name = ETHIOPIAN_MONTHS[m - 1][0]
        return (f"{name} {y} / Monthly Profit Report", start, end)

    if period_type in ('quarterly', 'semiannual'):
        span = 3 if period_type == 'quarterly' else 6
        end_y, end_m = _prev_eth_month(eth_year, eth_month)
        start_y, start_m = _shift_eth_month(end_y, end_m, -(span - 1))
        start = EthiopianDateConverter.to_gregorian(start_y, start_m, 1)
        _, end = _eth_month_bounds(end_y, end_m)
        title = "Quarterly" if period_type == 'quarterly' else "Semi-Annual"
        label = (f"{ETHIOPIAN_MONTHS[start_m - 1][0]} - {ETHIOPIAN_MONTHS[end_m - 1][0]} {end_y} "
                 f"/ {title} Profit Report")
        return (label, start, end)

    if period_type == 'annual':
        y = eth_year - 1
        start = EthiopianDateConverter.to_gregorian(y, 1, 1)
        _, end = _eth_month_bounds(y, 13)
        return (f"Ethiopian Year {y} / Annual Profit Report", start, end)

    return None


async def queue_periodic_profit_report(period_type: str) -> bool:
    """Queue one periodic profit report if today is its Ethiopian send day."""
    rng = profit_report_range(period_type, date.today())
    if rng is None:
        return False
    label, start, end = rng
    await queue_profit_report(period_type, label, start, end)
    return True


async def queue_monthly_profit_report():
    """Queue monthly profit report on the first day of an Ethiopian month."""
    return await queue_periodic_profit_report('monthly')


async def queue_quarterly_profit_report():
    """Queue quarterly profit report every 3 Ethiopian months (months 1,4,7,10)."""
    return await queue_periodic_profit_report('quarterly')


async def queue_semiannual_profit_report():
    """Queue semi-annual profit report every 6 Ethiopian months (months 1, 7)."""
    return await queue_periodic_profit_report('semiannual')


async def queue_annual_profit_report():
    """Queue annual profit report on Meskerem 1 (Ethiopian New Year)."""
    return await queue_periodic_profit_report('annual')


# ---------------------------------------------------------------------
# Daily Sales Report (sent to all admins)
# ---------------------------------------------------------------------
async def queue_daily_sales_report(target_date: date = None):
    """Queue a daily sales report for the given date (default today), scoped per recipient."""
    if target_date is None:
        target_date = date.today()
    recipients = _get_report_recipients('daily')
    for recipient in recipients:
        payload = {
            'target_date': target_date.isoformat(),
            'scope': recipient.to_payload(),
        }
        queue_notification('daily_sales_report', recipient.chat_id, payload)
    logger.info(
        "Queued daily sales report for %s to %d recipient(s) (%d scoped)",
        target_date, len(recipients), sum(1 for r in recipients if not r.is_full),
    )


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
    # Offsite copy: the outbox uploads the file to the admin on Telegram.
    queue_notification('database_backup', ADMIN_ID, {'file_path': str(backup_file)})


async def startup_backup_catchup():
    """Create any backups missed while the app was closed.

    Count-based rather than "is today's backup present": a PC that was off
    across both slots must produce both backups on the next launch, not just
    recover the latest one.
    """
    now = datetime.now()
    slots_due = sum(
        1 for hour, minute in DATABASE_BACKUP_SLOTS
        if now >= now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    )
    if slots_due == 0:
        return

    backup_dir = Path(get_backup_dir())
    today_prefix = now.strftime('%Y%m%d')
    existing_backups = list(backup_dir.glob(f'db_backup_{today_prefix}_*.db'))

    for _ in range(max(0, slots_due - len(existing_backups))):
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

    # Daily sales report to all admins
    scheduler.add_job(
        _safe_job(queue_daily_sales_report),
        trigger=CronTrigger(hour=18, minute=10),
        id='daily_sales_report_admin',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Monthly profit report (Ethiopian month day 1)
    scheduler.add_job(
        _safe_job(queue_monthly_profit_report),
        trigger=CronTrigger(hour=19, minute=0),
        id='monthly_profit_report_admin',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Quarterly profit report (Ethiopian months 1, 4, 7, 10)
    scheduler.add_job(
        _safe_job(queue_quarterly_profit_report),
        trigger=CronTrigger(hour=19, minute=0),
        id='quarterly_profit_report_admin',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Semi-annual profit report (Ethiopian months 1, 7)
    scheduler.add_job(
        _safe_job(queue_semiannual_profit_report),
        trigger=CronTrigger(hour=19, minute=0),
        id='semiannual_profit_report_admin',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Annual profit report (Ethiopian Meskerem 1)
    scheduler.add_job(
        _safe_job(queue_annual_profit_report),
        trigger=CronTrigger(hour=19, minute=0),
        id='annual_profit_report_admin',
        replace_existing=True,
        misfire_grace_time=86400
    )

    # Database backups (13:00 and 18:00) - each one is also sent to the admin
    scheduler.add_job(
        _safe_job(queue_daily_database_backup),
        trigger=CronTrigger(hour=DATABASE_BACKUP_HOURS, minute=DATABASE_BACKUP_MINUTES),
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
        trigger=IntervalTrigger(seconds=20),
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