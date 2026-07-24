import logging
import json
import asyncio
from datetime import datetime, timedelta
from io import BytesIO

from telegram import Bot
from telegram.request import HTTPXRequest
from sqlalchemy.orm import joinedload

from models.pending_notification import PendingNotification
from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS
from services.base_service import get_session
from config import BOT_TOKEN, ADMIN_ID

logger = logging.getLogger(__name__)

# Timeouts
_FAST_SEND_TIMEOUT = 60.0          # order_notification, admin alerts
_REPORT_SEND_TIMEOUT = 240.0       # PDF reports (was 60.0)

REPORT_NOTIFICATION_TYPES = {
    'daily_sales_report',
    'supplier_summary',
    'supplier_summary_admin',
    'customer_summary',
    'customer_summary_admin',
}

# ---------------------------------------------------------------------
# Bot factory with longer HTTP timeouts
# ---------------------------------------------------------------------
def _make_bot() -> Bot:
    """Create a Bot instance with generous HTTP timeouts to avoid false timeouts."""
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=300.0,          # large PDF uploads need more time
        write_timeout=30.0,
        pool_timeout=5.0,
    )
    return Bot(token=BOT_TOKEN, request=request)

# ---------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------
DEDUP_TYPES = {
    'daily_sales_report',
    'customer_summary',
    'customer_summary_admin',
    'supplier_summary',
    'supplier_summary_admin',
    'monthly_profit_report',
    'order_notification',
    'despatch_notification',
    'sale_cancellation',
    'purchase_notification',
}

def _get_dedup_key(notification_type: str, payload: dict, chat_id: int):
    if notification_type not in DEDUP_TYPES:
        return None

    if notification_type == 'daily_sales_report':
        return ('daily_sales_report', payload.get('target_date'))

    elif notification_type == 'monthly_profit_report':
        return ('monthly_profit_report', payload.get('eth_year'), payload.get('eth_month'))

    elif notification_type in ('customer_summary', 'customer_summary_admin'):
        sale_id = payload.get('sale_id')
        if sale_id is not None:
            return (notification_type, payload.get('customer_id'), payload.get('target_date'), sale_id)
        return (notification_type, payload.get('customer_id'), payload.get('target_date'))

    elif notification_type in ('supplier_summary', 'supplier_summary_admin'):
        purchase_id = payload.get('purchase_id')
        if purchase_id is not None:
            return (notification_type, chat_id, payload.get('supplier_id'), payload.get('target_date'), purchase_id)
        return (notification_type, chat_id, payload.get('supplier_id'), payload.get('target_date'))

    elif notification_type == 'order_notification':
        sale_id = payload.get('sale_id')
        if sale_id is not None:
            return ('order_notification', sale_id, chat_id)
        return ('order_notification', hash(payload.get('text', '')), chat_id)
    
    elif notification_type == 'despatch_notification':
        sale_id = payload.get('sale_id')
        if sale_id is not None:
            return ('despatch_notification', sale_id, chat_id)
        return ('despatch_notification', hash(payload.get('text', '')), chat_id)
    
    elif notification_type == 'sale_cancellation':
        sale_id = payload.get('sale_id')
        if sale_id is not None:
            return (notification_type, sale_id, chat_id)
        return (notification_type, hash(payload.get('text', '')), chat_id)
    
    elif notification_type == 'purchase_notification':
        purchase_id = payload.get('purchase_id')
        if purchase_id is not None:
            return (notification_type, purchase_id, chat_id)
        return (notification_type, hash(payload.get('text', '')), chat_id)

    return None

# ---------------------------------------------------------------------
# Duplicate check for pending notifications
# ---------------------------------------------------------------------
def _is_duplicate(session, notification_type: str, payload: dict, chat_id: int) -> bool:
    key = _get_dedup_key(notification_type, payload, chat_id)
    if key is None:
        return False

    since = datetime.utcnow() - timedelta(days=7)
    candidates = session.query(PendingNotification).filter(
        PendingNotification.notification_type == notification_type,
        PendingNotification.chat_id == chat_id,
        PendingNotification.status.in_(['pending', 'sent']),
        PendingNotification.created_at >= since
    ).all()

    for notif in candidates:
        try:
            pl = json.loads(notif.payload_json)
            if _get_dedup_key(notification_type, pl, chat_id) == key:
                return True
        except Exception:
            continue
    return False

# ---------------------------------------------------------------------
# Check for sent duplicate (idempotency)
# ---------------------------------------------------------------------
def _has_sent_duplicate(notification_type: str, payload: dict, chat_id: int) -> bool:
    key = _get_dedup_key(notification_type, payload, chat_id)
    if key is None:
        return False

    since = datetime.utcnow() - timedelta(days=7)
    with get_session() as session:
        candidates = session.query(PendingNotification).filter(
            PendingNotification.notification_type == notification_type,
            PendingNotification.chat_id == chat_id,
            PendingNotification.status == 'sent',
            PendingNotification.created_at >= since
        ).all()

        for notif in candidates:
            try:
                pl = json.loads(notif.payload_json)
                if _get_dedup_key(notification_type, pl, chat_id) == key:
                    return True
            except Exception:
                continue
    return False

# ---------------------------------------------------------------------
# Step tracking for multi-part reports
# ---------------------------------------------------------------------
def _mark_step_done(notif_id: int, step: str):
    """Record that one piece of a multi-part report was delivered successfully.
    This prevents resending on retry."""
    with get_session() as session:
        notif = session.query(PendingNotification).get(notif_id)
        if not notif:
            return
        try:
            payload = json.loads(notif.payload_json)
        except Exception:
            return
        done = set(payload.get('_sent_steps', []))
        done.add(step)
        payload['_sent_steps'] = sorted(done)
        notif.payload_json = json.dumps(payload)
        session.commit()

# ---------------------------------------------------------------------
# Queue notification
# ---------------------------------------------------------------------
def queue_notification(notification_type: str, chat_id: int, payload: dict, skip_dedup: bool = False):
    with get_session() as session:
        if not skip_dedup and _is_duplicate(session, notification_type, payload, chat_id):
            logger.debug("Skipping duplicate %s for chat_id %s", notification_type, chat_id)
            return

        notif = PendingNotification(
            notification_type=notification_type,
            chat_id=chat_id,
            payload_json=json.dumps(payload),
        )
        session.add(notif)
        session.commit()
    logger.debug("Queued %s for chat_id %s", notification_type, chat_id)

# ---------------------------------------------------------------------
# Reset stuck notifications
# ---------------------------------------------------------------------
def reset_failed_pending_notifications():
    with get_session() as session:
        cooldown = datetime.utcnow() - timedelta(hours=1)
        stuck = session.query(PendingNotification).filter(
            PendingNotification.status == 'pending',
            PendingNotification.retry_count >= PendingNotification.max_retries,
            PendingNotification.next_retry_time <= cooldown
        ).all()

        for notif in stuck:
            notif.retry_count = 0
            notif.next_retry_time = datetime.utcnow()
            logger.info(
                "Reset retry_count for notification %d (type %s, chat_id %s)",
                notif.id, notif.notification_type, notif.chat_id
            )

        if stuck:
            session.commit()
            logger.info("Reset %d stuck notifications", len(stuck))

# ---------------------------------------------------------------------
# Outbox processor
# ---------------------------------------------------------------------
async def process_pending_notifications():
    bot = _make_bot()

    def _fetch_pending():
        with get_session() as session:
            now = datetime.utcnow()
            rows = session.query(PendingNotification).filter(
                PendingNotification.status == 'pending',
                PendingNotification.next_retry_time <= now,
                PendingNotification.retry_count < PendingNotification.max_retries
            ).order_by(PendingNotification.created_at).limit(100).all()

            result = []
            for r in rows:
                result.append({
                    'id': r.id,
                    'notification_type': r.notification_type,
                    'chat_id': r.chat_id,
                    'payload_json': r.payload_json,
                    'retry_count': r.retry_count,
                })
            return result

    pending = await asyncio.to_thread(_fetch_pending)

    if not pending:
        return

    logger.info("Processing %d pending notifications", len(pending))

    for row in pending:
        notif_id = row['id']
        nt = row['notification_type']
        chat_id = row['chat_id']
        retry_count = row['retry_count']

        try:
            payload = json.loads(row['payload_json'])

            # Idempotency: if already fully sent, just mark as sent
            if _has_sent_duplicate(nt, payload, chat_id):
                logger.info("Duplicate sent notification found for %d, marking as sent without sending", notif_id)
                await asyncio.to_thread(_mark_sent, notif_id)
                continue

            if _has_pending_duplicate(nt, payload, chat_id, notif_id):
                logger.info("Skipping duplicate pending notification %d", notif_id)
                await asyncio.to_thread(_mark_sent, notif_id)
                continue

            # Dispatch with notif_id for step tracking
            await _dispatch_notification(bot, nt, chat_id, payload, notif_id)
            await asyncio.to_thread(_mark_sent, notif_id)
            logger.debug("Sent notification %d (type %s)", notif_id, nt)

        except Exception as e:
            new_retry = retry_count + 1
            if nt in REPORT_NOTIFICATION_TYPES:
                delay_seconds = min(3600, 30 * (2 ** (new_retry - 1)))
            else:
                delay_seconds = min(3600, 15 * (2 ** (new_retry - 1)))
            next_retry = datetime.utcnow() + timedelta(seconds=delay_seconds)
            await asyncio.to_thread(_mark_failed, notif_id, new_retry, next_retry, str(e)[:500])
            logger.warning(
                "Notification %d (type %s) failed (attempt %d): %s",
                notif_id, nt, new_retry, e
            )

# ---------------------------------------------------------------------
# Mark status helpers
# ---------------------------------------------------------------------
def _mark_sent(notif_id: int):
    with get_session() as session:
        notif = session.query(PendingNotification).get(notif_id)
        if notif:
            notif.status = 'sent'
            session.commit()

def _mark_failed(notif_id: int, retry_count: int, next_retry: datetime, error: str):
    with get_session() as session:
        notif = session.query(PendingNotification).get(notif_id)
        if notif:
            notif.retry_count = retry_count
            notif.next_retry_time = next_retry
            notif.last_error = error
            session.commit()

def _has_pending_duplicate(notification_type: str, payload: dict, chat_id: int, exclude_id: int) -> bool:
    key = _get_dedup_key(notification_type, payload, chat_id)
    if key is None:
        return False
    with get_session() as session:
        candidates = session.query(PendingNotification).filter(
            PendingNotification.notification_type == notification_type,
            PendingNotification.chat_id == chat_id,
            PendingNotification.status == 'pending',
            PendingNotification.id != exclude_id,
            PendingNotification.retry_count < PendingNotification.max_retries
        ).all()
        for notif in candidates:
            try:
                pl = json.loads(notif.payload_json)
                if _get_dedup_key(notification_type, pl, chat_id) == key:
                    return True
            except Exception:
                continue
    return False


# ---------------------------------------------------------------------
# Safe send helpers
# ---------------------------------------------------------------------
async def _safe_send_message(bot: Bot, chat_id: int, timeout: float = _FAST_SEND_TIMEOUT, **kwargs):
    return await asyncio.wait_for(
        bot.send_message(chat_id=chat_id, **kwargs),
        timeout=timeout
    )

async def _safe_send_document(bot: Bot, chat_id: int, timeout: float = _REPORT_SEND_TIMEOUT, **kwargs):
    return await asyncio.wait_for(
        bot.send_document(chat_id=chat_id, **kwargs),
        timeout=timeout
    )

# ---------------------------------------------------------------------
# Dispatcher (now passes notif_id)
# ---------------------------------------------------------------------
async def _dispatch_notification(bot: Bot, nt: str, chat_id: int, payload: dict, notif_id: int):
    if nt in ('order_notification', 'despatch_confirmation', 'despatch_notification', 'admin_copy',
              'unusual_alert', 'generic_message', 'sale_cancellation', 'purchase_notification'):
        await _send_generic_message(bot, chat_id, payload)

    elif nt == 'daily_sales_report':
        await _send_daily_sales_report(bot, chat_id, payload, notif_id)

    elif nt == 'customer_summary':
        await _send_customer_summary(bot, chat_id, payload, notif_id)

    elif nt == 'customer_summary_admin':
        await _send_customer_summary_admin(bot, chat_id, payload, notif_id)

    elif nt == 'supplier_summary':
        await _send_supplier_summary(bot, chat_id, payload, notif_id)

    elif nt == 'supplier_summary_admin':
        await _send_supplier_summary_admin(bot, chat_id, payload, notif_id)

    else:
        raise ValueError(f"Unknown notification type: {nt}")

# =============================================================================
# Senders with step-tracking
# =============================================================================

async def _send_generic_message(bot: Bot, chat_id: int, payload: dict):
    parse_mode = payload.get('parse_mode', 'HTML')
    await _safe_send_message(bot, chat_id, text=payload['text'], parse_mode=parse_mode)

# ---------------------------------------------------------------------
# Daily Sales Report
# ---------------------------------------------------------------------
async def _send_daily_sales_report(bot: Bot, chat_id: int, payload: dict, notif_id: int):
    from services.new_sale_service import NewSaleService
    from telegrambot.handlers.reports.sales_report import generate_sales_pdf, _build_sales_summary
    from ui.components.ethiopian_date import EthiopianDateConverter
    from services.base_service import get_session

    target_date = datetime.strptime(payload['target_date'], '%Y-%m-%d').date()
    sale_service = NewSaleService()
    sent_steps = set(payload.get('_sent_steps', []))

    def _fetch_and_build():
        sales, _ = sale_service.get_all_sales_paginated(
            page=1, page_size=10000, filter_date=target_date
        )
        if not sales:
            return {
                'total_sales_amount': 0.0,
                'total_labour_expense': 0.0,
                'cash_total': 0.0,
                'bank_total': 0.0,
                'item_details': [],
            }
        with get_session() as session:
            return _build_sales_summary(sales, target_date, session, sale_service)

    summary = await asyncio.to_thread(_fetch_and_build)
    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(target_date)

    # Step 1: Text message
    if 'text' not in sent_steps:
        caption = (
            f"📊 *Daily Sales Report*\n"
            f"📅 {ETHIOPIAN_MONTHS[eth_month - 1][0]} {eth_day}, {eth_year} "
            f"(Gregorian: {target_date})\n"
            f"💰 Total Sales: ETB {summary['total_sales_amount']:,.2f}"
        )
        await _safe_send_message(bot, chat_id, text=caption, parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT)
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 2: PDF document
    if 'document' not in sent_steps:
        pdf_bytes = await asyncio.to_thread(
            generate_sales_pdf, summary, eth_year, eth_month, eth_day, target_date
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=f"daily_sales_{target_date}.pdf",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'document')

# ---------------------------------------------------------------------
# Supplier Summary (to supplier)
# ---------------------------------------------------------------------
async def _send_supplier_summary(bot: Bot, chat_id: int, payload: dict, notif_id: int):
    from services.purchase_service import PurchaseService
    from services.supplier_service import SupplierService
    from telegrambot.handlers.reports.purchase_reports import (
        generate_supplier_payment_history_pdf,
    )

    supplier_id = payload['supplier_id']
    target_date = datetime.strptime(payload['target_date'], '%Y-%m-%d').date()
    purchase_svc = PurchaseService()
    supplier_svc = SupplierService()
    sent_steps = set(payload.get('_sent_steps', []))

    supplier = await asyncio.to_thread(supplier_svc.get_by_id, supplier_id)
    if not supplier:
        return

    activity = await asyncio.to_thread(purchase_svc.get_daily_credit_activity, supplier_id, target_date)
    opening = await asyncio.to_thread(purchase_svc.get_opening_balance_for_date, supplier_id, target_date)
    closing = (
        opening
        + activity['total_purchases_amount']
        - activity['total_payments_amount']
        + activity.get('net_adjustment', 0.0)
    )
    text = PurchaseService.format_daily_activity_summary(
        supplier.supplier_name, target_date, opening, closing, activity
    )

    transactions = await asyncio.to_thread(purchase_svc.get_supplier_combined_history, supplier_id)
    total_credit = sum(tx['credit_amount'] for tx in transactions)
    total_debit = sum(tx['debit_amount'] for tx in transactions)

    # Step 1: Text
    if 'text' not in sent_steps:
        await _safe_send_message(bot, chat_id, text=text, parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT)
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 2: Payment PDF
    if 'payment_pdf' not in sent_steps:
        pdf_bytes = await asyncio.to_thread(
            generate_supplier_payment_history_pdf,
            supplier_name=supplier.supplier_name,
            transactions=transactions,
            total_credit=total_credit,
            total_debit=total_debit,
            current_balance=closing,
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=f"statement_{target_date}.pdf",
            caption=f"📄 Payment History Statement – {target_date.strftime('%d/%m/%Y')}",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'payment_pdf')

# ---------------------------------------------------------------------
# Supplier Summary Admin (copy to admin + credit items)
# ---------------------------------------------------------------------
async def _send_supplier_summary_admin(bot: Bot, chat_id: int, payload: dict, notif_id: int):
    from services.purchase_service import PurchaseService
    from services.supplier_service import SupplierService
    from telegrambot.handlers.reports.purchase_reports import (
        generate_supplier_payment_history_pdf,
        generate_supplier_credit_items_pdf,
    )

    supplier_id = payload['supplier_id']
    target_date = datetime.strptime(payload['target_date'], '%Y-%m-%d').date()
    purchase_svc = PurchaseService()
    supplier_svc = SupplierService()
    sent_steps = set(payload.get('_sent_steps', []))

    supplier = await asyncio.to_thread(supplier_svc.get_by_id, supplier_id)
    supplier_name = supplier.supplier_name if supplier else payload.get('supplier_name', 'N/A')

    activity = await asyncio.to_thread(purchase_svc.get_daily_credit_activity, supplier_id, target_date)
    opening = await asyncio.to_thread(purchase_svc.get_opening_balance_for_date, supplier_id, target_date)
    closing = (
        opening
        + activity['total_purchases_amount']
        - activity['total_payments_amount']
        + activity.get('net_adjustment', 0.0)
    )
    text = PurchaseService.format_daily_activity_summary(
        supplier_name, target_date, opening, closing, activity
    )
    admin_text = (
        f"📋 *Copy of supplier notification*\n"
        f"Supplier: {supplier_name} (ID: {supplier_id})\n\n{text}"
    )

    transactions = await asyncio.to_thread(purchase_svc.get_supplier_combined_history, supplier_id)
    total_credit = sum(tx['credit_amount'] for tx in transactions)
    total_debit = sum(tx['debit_amount'] for tx in transactions)

    # Step 1: Text
    if 'text' not in sent_steps:
        await _safe_send_message(bot, chat_id, text=admin_text, parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT)
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 2: Payment PDF
    if 'payment_pdf' not in sent_steps:
        pdf_bytes = await asyncio.to_thread(
            generate_supplier_payment_history_pdf,
            supplier_name=supplier_name,
            transactions=transactions,
            total_credit=total_credit,
            total_debit=total_debit,
            current_balance=closing,
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=f"copy_statement_{supplier_name}_{target_date}.pdf",
            caption=f"📄 Copy – Payment History for {supplier_name} – {target_date.strftime('%d/%m/%Y')}",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'payment_pdf')

    # Step 3: Credit Items PDF (only if groups exist and not done)
    groups = await asyncio.to_thread(purchase_svc.get_supplier_credit_purchases_grouped, supplier_id)
    if groups and 'credit_items_pdf' not in sent_steps:
        pdf_bytes_items = await asyncio.to_thread(
            generate_supplier_credit_items_pdf, supplier_name, groups
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes_items),
            filename=f"copy_credit_items_{supplier_name}_{target_date}.pdf",
            caption=f"📦 Copy – Credit Items History for {supplier_name} – {target_date.strftime('%d/%m/%Y')}",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'credit_items_pdf')

# ---------------------------------------------------------------------
# Customer Summary (to customer)
# ---------------------------------------------------------------------
async def _send_customer_summary(bot: Bot, chat_id: int, payload: dict, notif_id: int):
    from services.customer_service import CustomerService
    from services.new_sale_service import NewSaleService
    from telegrambot.handlers.reports.customer_credit_reports import (
        generate_customer_payment_history_pdf,
        generate_customer_credit_items_pdf,
    )

    customer_id = payload['customer_id']
    target_date = datetime.strptime(payload['target_date'], '%Y-%m-%d').date()
    customer_svc = CustomerService()
    sale_svc = NewSaleService()
    sent_steps = set(payload.get('_sent_steps', []))

    customer = await asyncio.to_thread(customer_svc.get_by_id, customer_id)
    if not customer:
        return

    activity = await asyncio.to_thread(sale_svc.get_daily_credit_activity, customer_id, target_date)
    opening = await asyncio.to_thread(sale_svc.get_opening_balance_for_date, customer_id, target_date)
    history = await asyncio.to_thread(sale_svc.get_customer_combined_history, customer_id)

    total_credit = sum(tx['amount'] for tx in history if tx['type'] == 'credit_sale')
    total_debit = sum(-tx['amount'] for tx in history if tx['type'] == 'payment')
    closing = history[-1]['balance_after'] if history else 0.0
    text = NewSaleService.format_daily_activity_summary(
        customer.name, target_date, opening, closing, activity
    )

    # Step 1: Text
    if 'text' not in sent_steps:
        await _safe_send_message(bot, chat_id, text=text, parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT)
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 2: Payment PDF
    if 'payment_pdf' not in sent_steps:
        pdf_bytes = await asyncio.to_thread(
            generate_customer_payment_history_pdf,
            customer_name=customer.name,
            transactions=history,
            total_credit=total_credit,
            total_debit=total_debit,
            current_balance=closing,
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=f"statement_{target_date}.pdf",
            caption=f"📄 Credit Statement – {target_date.strftime('%d/%m/%Y')}",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'payment_pdf')

    # Step 3: Credit Items PDF
    groups = await asyncio.to_thread(sale_svc.get_customer_credit_sales_grouped, customer_id)
    if groups and 'credit_items_pdf' not in sent_steps:
        pdf_bytes_items = await asyncio.to_thread(
            generate_customer_credit_items_pdf, customer.name, groups
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes_items),
            filename=f"credit_items_{customer.name}_{target_date}.pdf",
            caption=f"📦 Credit Items History – {target_date.strftime('%d/%m/%Y')}",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'credit_items_pdf')


async def _send_customer_summary_admin(bot: Bot, chat_id: int, payload: dict, notif_id: int):
    from services.customer_service import CustomerService
    from services.new_sale_service import NewSaleService
    from telegrambot.handlers.reports.customer_credit_reports import (
        generate_customer_payment_history_pdf,
        generate_customer_credit_items_pdf,
    )

    customer_id = payload['customer_id']
    target_date = datetime.strptime(payload['target_date'], '%Y-%m-%d').date()
    customer_svc = CustomerService()
    sale_svc = NewSaleService()
    sent_steps = set(payload.get('_sent_steps', []))

    customer = await asyncio.to_thread(customer_svc.get_by_id, customer_id)
    name = customer.name if customer else payload.get('customer_name', 'N/A')

    activity = await asyncio.to_thread(sale_svc.get_daily_credit_activity, customer_id, target_date)
    opening = await asyncio.to_thread(sale_svc.get_opening_balance_for_date, customer_id, target_date)
    history = await asyncio.to_thread(sale_svc.get_customer_combined_history, customer_id)

    total_credit = sum(tx['amount'] for tx in history if tx['type'] == 'credit_sale')
    total_debit = sum(-tx['amount'] for tx in history if tx['type'] == 'payment')
    closing = history[-1]['balance_after'] if history else 0.0

    text = NewSaleService.format_daily_activity_summary(
        name, target_date, opening, closing, activity
    )
    admin_text = (
        f"📋 *Copy of customer notification*\n"
        f"Customer: {name} (ID: {customer_id})\n\n{text}"
    )

    # Step 1: Text
    if 'text' not in sent_steps:
        await _safe_send_message(bot, chat_id, text=admin_text, parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT)
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 2: Payment PDF
    if 'payment_pdf' not in sent_steps:
        pdf_bytes = await asyncio.to_thread(
            generate_customer_payment_history_pdf,
            customer_name=name,
            transactions=history,
            total_credit=total_credit,
            total_debit=total_debit,
            current_balance=closing,
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=f"copy_statement_{name}_{target_date}.pdf",
            caption=f"📄 Copy – Credit Statement for {name} – {target_date.strftime('%d/%m/%Y')}",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'payment_pdf')

    # Step 3: Credit Items PDF
    groups = await asyncio.to_thread(sale_svc.get_customer_credit_sales_grouped, customer_id)
    if groups and 'credit_items_pdf' not in sent_steps:
        pdf_bytes_items = await asyncio.to_thread(
            generate_customer_credit_items_pdf, name, groups
        )
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes_items),
            filename=f"copy_credit_items_{name}_{target_date}.pdf",
            caption=f"📦 Copy – Credit Items History for {name} – {target_date.strftime('%d/%m/%Y')}",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'credit_items_pdf')