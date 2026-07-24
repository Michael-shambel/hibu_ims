#!/usr/bin/env python3
import asyncio
import datetime
import io
import logging
from models.auth_user import AuthUser
from services import auth_service
from services import supplier_service
from telegram.ext import ApplicationBuilder, PicklePersistence
from telegram.error import TimedOut, NetworkError, TelegramError
from telegram import Bot
from config import BOT_TOKEN, ADMIN_ID
from telegrambot.handlers.menu import conv_handler
from services.base_service import get_session
from telegrambot.scheduler import start_scheduler, stop_scheduler, startup_catchup, startup_backup_catchup
from telegram.ext import MessageHandler, filters
from telegrambot.handlers.menu_handlers.main_menu import handle_persistent_buttons
from telegrambot.outbox import queue_notification
from services.customer_service import CustomerService
from services.new_sale_service import NewSaleService
from telegrambot.handlers.reports.customer_credit_reports import generate_customer_credit_items_pdf, generate_customer_payment_history_pdf
from services.purchase_service import PurchaseService
from services.supplier_service import SupplierService
from telegrambot.handlers.reports.purchase_reports import generate_supplier_payment_history_pdf
from datetime import date


logger = logging.getLogger(__name__)


global_main_window_ref = None
_bot_app = None
_bot_ready = False
_bot_loop = None


def set_bot_app(app):
    global _bot_app, _bot_ready, _bot_loop
    _bot_app = app
    _bot_ready = True
    try:
        _bot_loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("No running loop found when setting bot app")


def get_bot_app():
    return _bot_app


def is_bot_ready():
    global _bot_ready, _bot_app, _bot_loop
    return _bot_ready and _bot_app is not None and _bot_loop is not None


def notify_store_team_sync(message: str, sale_id: int = None, purchase_id: int = None, skip_dedup: bool = False, notification_type: str = 'order_notification'):
    """Queue an order notification message to all sales team members."""
    with get_session() as session:
        users = session.query(AuthUser).filter(
            AuthUser.role.in_(['sales_clerk', 'sales_team']),
            AuthUser.chat_id.isnot(None),
            AuthUser.is_deleted == False
        ).all()
        for user in users:
            payload = {'text': message, 'parse_mode': 'HTML'}
            if sale_id:
                payload['sale_id'] = str(sale_id)
            if purchase_id:
                payload['purchase_id'] = str(purchase_id)   # new
            queue_notification(notification_type, user.chat_id, payload, skip_dedup)

def notify_customer_sync(customer_id: int, target_date: date = None, sale_id: int = None):
    """Queue a customer daily summary notification for the customer + admin copy.
    Uses skip_dedup=True to ensure a notification is sent for every credit sale."""
    if target_date is None:
        target_date = date.today()
    customer_svc = CustomerService()
    customer = customer_svc.get_by_id(customer_id)
    if not customer or not customer.chat_id:
        logger.info("Customer %s has no chat_id, skipping notification", customer_id)
        return
    today_iso = target_date.isoformat()
    # Customer – always queue (skip dedup)
    queue_notification('customer_summary', customer.chat_id,
                       {'customer_id': customer_id, 'target_date': today_iso, 'sale_id': sale_id},
                       skip_dedup=True)
    # Admin copy – always queue (skip dedup)
    queue_notification('customer_summary_admin', ADMIN_ID,
                       {'customer_id': customer_id, 'target_date': today_iso,
                        'customer_name': customer.name, 'sale_id': sale_id},
                       skip_dedup=True)


def notify_supplier_purchase_sync(supplier_id: int, target_date: date = None, purchase_id: int = None):
    """Queue supplier daily summary notification for all linked contacts + admin copy.
    Uses skip_dedup=True for every purchase."""
    if target_date is None:
        target_date = date.today()
    supplier_svc = SupplierService()
    chat_ids = supplier_svc.get_all_notification_chat_ids(supplier_id)
    if not chat_ids:
        logger.info("No chat IDs for supplier %s, skipping", supplier_id)
        return
    today_iso = target_date.isoformat()
    for chat_id in chat_ids:
        queue_notification('supplier_summary', chat_id,
                           {'supplier_id': supplier_id, 'target_date': today_iso, 'purchase_id': purchase_id},
                           skip_dedup=True)
    # Admin copy
    supplier = supplier_svc.get_by_id(supplier_id)
    supplier_name = supplier.supplier_name if supplier else ''
    queue_notification('supplier_summary_admin', ADMIN_ID,
                       {'supplier_id': supplier_id, 'target_date': today_iso,
                        'supplier_name': supplier_name, 'purchase_id': purchase_id},
                       skip_dedup=True)


def send_notification_to_admin_sync(message: str):
    """Queue a plain admin alert (e.g., unusual sale alert)."""
    queue_notification('generic_message', ADMIN_ID,
                       {'text': message, 'parse_mode': 'Markdown'})


async def send_notification_to_store_team(message: str):
    """Deprecated – kept only for internal reference; all external callers use queue."""
    logger.warning("Direct send_notification_to_store_team called – should use queue instead.")
    if not _bot_app or not _bot_app.bot:
        return
    notify_store_team_sync(message)


async def monitor_bot_connection(app, main_window):
    global _bot_ready
    while True:
        try:
            me = await app.bot.get_me()
            _bot_ready = True
            target_window = main_window or global_main_window_ref
            if target_window:
                try:
                    target_window.set_bot_connected()
                except Exception as e:
                    logger.debug(f"Could not update UI: {e}")
        except Exception as e:
            logger.warning(f"Bot connection lost: {e}")
            _bot_ready = False
            target_window = main_window or global_main_window_ref
            if target_window:
                try:
                    target_window.set_bot_disconnected()
                except Exception as e:
                    logger.debug(f"Could not update UI: {e}")
        await asyncio.sleep(15)


async def run_bot(main_window):
    global _bot_ready, _bot_loop
    RETRY_DELAY = 10

    while True:
        app = None
        updater_started = False
        scheduler_started = False
        try:
            persistence = PicklePersistence(filepath="bot_conversation_data")
            app = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()
            app.add_handler(conv_handler)
            set_bot_app(app)

            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            updater_started = True
            start_scheduler(BOT_TOKEN)
            scheduler_started = True

            # Catch up any missed daily reports while the app was down
            asyncio.create_task(startup_catchup())
            asyncio.create_task(startup_backup_catchup())

            try:
                me = await app.bot.get_me()
                _bot_ready = True
            except Exception as e:
                logger.error("Bot verification failed: %s", e)
                _bot_ready = False

            target_window = main_window or global_main_window_ref
            if target_window:
                try:
                    target_window.set_bot_connected()
                except Exception as e:
                    logger.debug(f"Could not update UI initially: {e}")

            asyncio.create_task(monitor_bot_connection(app, main_window))
            await asyncio.Event().wait()
        except (TimedOut, NetworkError, TelegramError) as e:
            logger.warning(f"Connection error: {e}. Retrying in {RETRY_DELAY}s...")
            _bot_ready = False
        except Exception as e:
            logger.exception(f"Critical error: {e}. Retrying in {RETRY_DELAY}s...")
            _bot_ready = False
        finally:
            if scheduler_started:
                stop_scheduler()
            target_window = main_window or global_main_window_ref
            if target_window:
                try:
                    target_window.set_bot_disconnected()
                except Exception as e:
                    logger.debug(f"Could not update UI on disconnect: {e}")

            if app:
                try:
                    if updater_started:
                        await app.updater.stop()
                    await app.stop()
                    await app.shutdown()
                except Exception as e:
                    logger.warning(f"Cleanup error: {e}")

            await asyncio.sleep(RETRY_DELAY)


def start_bot(main_window):
    import threading
    threading.Thread(target=lambda: asyncio.run(run_bot(main_window)), daemon=True, name="TelegramBotThread").start()