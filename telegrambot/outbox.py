import logging
import json
import hashlib
import asyncio
import os
import re
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
import threading

import httpx
from telegram import Bot
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError
from sqlalchemy.orm import joinedload

from models.pending_notification import PendingNotification
from services.base_service import get_session
from config import BOT_TOKEN, ADMIN_ID

logger = logging.getLogger(__name__)

# Timeouts
_FAST_SEND_TIMEOUT = 300.0          # order_notification, admin alerts
# (was 120.0: asyncio.wait_for fired long before the 600s HTTP read timeout,
#  abandoning acks for messages Telegram HAD delivered -> retry -> duplicates)
_REPORT_SEND_TIMEOUT = 720.0       # PDF reports (was 60.0)

# Telegram's Bot API rejects document uploads over 50 MB. Keep a small margin
# so a request is never sent only to be rejected.
_MAX_TELEGRAM_DOCUMENT_MB = 49

REPORT_NOTIFICATION_TYPES = {
    'daily_sales_report',
    'supplier_summary',
    'supplier_summary_admin',
    'customer_summary',
    'customer_summary_admin',
    'shipment_approval_report',
    'profit_report',
    'database_backup',
}

# Raw .db uploads (the daily database backup) are the app's only offsite copy.
# A timeout or ambiguous network error means we cannot know whether Telegram
# accepted the file, so these notifications are RETRIED instead of being
# marked 'sent' like every other type. A duplicate snapshot is harmless; a
# silently skipped one leaves the admin with no backup at all.
_DB_FILE_EXTENSION = '.db'


def _is_db_file_notification(notification_type: str, payload: dict) -> bool:
    """True when this notification uploads a raw .db file."""
    if notification_type == 'database_backup':
        return True
    file_path = payload.get('file_path') or payload.get('file_name') or ''
    return isinstance(file_path, str) and file_path.lower().endswith(_DB_FILE_EXTENSION)


_queue_lock = threading.Lock()

# ---------------------------------------------------------------------
# Bot factory with longer HTTP timeouts
# ---------------------------------------------------------------------
def _make_bot() -> Bot:
    """Create a Bot instance with generous HTTP timeouts to avoid false timeouts."""
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=600.0,          # large PDF uploads need more time
        write_timeout=60.0,
        pool_timeout=10.0,
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
    'profit_report',
    'shipment_approval_report',
    'order_notification',
    'despatch_notification',
    'sale_cancellation',
    'purchase_notification',
    'database_backup',
}

def _scope_signature(payload: dict):
    """
    Fingerprint of a report's product scope, so two scopes of the same period
    are treated as different reports (and a scope change cannot be swallowed by
    an older dedup key).
    """
    scope = payload.get('scope') or {}
    product_ids = scope.get('product_ids')
    if product_ids is None:
        products_key = 'all'
    else:
        products_key = ','.join(str(p) for p in sorted(product_ids))
    return (products_key, tuple(int(g) for g in (scope.get('group_ids') or [])))


def _get_dedup_key(notification_type: str, payload: dict, chat_id: int):
    if notification_type not in DEDUP_TYPES:
        return None

    if notification_type == 'daily_sales_report':
        return ('daily_sales_report', payload.get('target_date'), _scope_signature(payload))

    elif notification_type == 'monthly_profit_report':
        return ('monthly_profit_report', payload.get('eth_year'), payload.get('eth_month'))

    elif notification_type == 'profit_report':
        return ('profit_report', payload.get('period_type'), payload.get('start_date'),
                payload.get('end_date'), _scope_signature(payload))

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
        return ('order_notification', _text_hash(payload.get('text', '')), chat_id)
    
    elif notification_type == 'despatch_notification':
        sale_id = payload.get('sale_id')
        if sale_id is not None:
            return ('despatch_notification', sale_id, chat_id)
        return ('despatch_notification', _text_hash(payload.get('text', '')), chat_id)
    
    elif notification_type == 'sale_cancellation':
        sale_id = payload.get('sale_id')
        if sale_id is not None:
            return (notification_type, sale_id, chat_id)
        return (notification_type, _text_hash(payload.get('text', '')), chat_id)
    
    elif notification_type == 'purchase_notification':
        purchase_id = payload.get('purchase_id')
        if purchase_id is not None:
            return (notification_type, purchase_id, chat_id)
        return (notification_type, _text_hash(payload.get('text', '')), chat_id)

    elif notification_type == 'shipment_approval_report':
        return (notification_type, payload.get('shipment_id'))

    elif notification_type == 'database_backup':
        return ('database_backup', payload.get('file_path'))

    return None

# ---------------------------------------------------------------------
# Stable text hash + catch-up-aware key matching
# ---------------------------------------------------------------------
def _text_hash(text: str) -> str:
    # Stable across restarts (hash() is randomized per process, so text-based
    # dedup keys changed on every restart and duplicates slipped through).
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

_SUMMARY_ID_FIELDS = {
    'customer_summary': 'sale_id',
    'customer_summary_admin': 'sale_id',
    'supplier_summary': 'purchase_id',
    'supplier_summary_admin': 'purchase_id',
}


def _keys_match(notification_type: str, new_payload: dict, candidate_payload: dict, chat_id: int) -> bool:
    """True when a queued notification is the same event as a stored one.

    A real-time event carries a sale_id/purchase_id, while the scheduler
    catch-up for the same day does not. Comparing both keys with the id field
    removed makes the catch-up recognise the event-based message it would
    otherwise resend.
    """
    new_key = _get_dedup_key(notification_type, new_payload, chat_id)
    cand_key = _get_dedup_key(notification_type, candidate_payload, chat_id)
    if new_key is None or cand_key is None:
        return False
    if new_key == cand_key:
        return True
    id_field = _SUMMARY_ID_FIELDS.get(notification_type)
    if id_field and new_payload.get(id_field) is None:
        strip = lambda p: {k: v for k, v in p.items() if k != id_field}
        return (
            _get_dedup_key(notification_type, strip(new_payload), chat_id)
            == _get_dedup_key(notification_type, strip(candidate_payload), chat_id)
        )
    return False

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
            if _keys_match(notification_type, payload, pl, chat_id):
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
                if _keys_match(notification_type, payload, pl, chat_id):
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
    # Serialised so two threads (UI event + scheduler) can never both pass the
    # duplicate check and insert the same row.
    with _queue_lock:
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
        max_age = datetime.utcnow() - timedelta(hours=12)
        stuck = session.query(PendingNotification).filter(
            PendingNotification.status == 'pending',
            PendingNotification.retry_count >= PendingNotification.max_retries,
            PendingNotification.next_retry_time <= cooldown,
            PendingNotification.created_at >= max_age
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
# Single-writer claim + recent-dispatch guard
# ---------------------------------------------------------------------
# These two guards close the remaining duplicate windows of an at-least-once
# outbox:
#  * _claim_for_send()  – a DB compare-and-swap so two overlapping cycles
#    (double app instance, scheduler restart race) can never both send the
#    same row. A claim left behind by a crashed worker expires after
#    _CLAIM_STALE_SECONDS so the row is eventually retried.
#  * _was_recently_dispatched() – in-process memory of messages this process
#    already delivered. If the 'sent' bookkeeping write afterwards keeps
#    failing (DB lock/IO), the old code resent the SAME message on every
#    20-second cycle -> 2-4+ identical copies per phone. The guard makes
#    those later cycles mark the row 'sent' without sending again.

_CLAIM_STALE_SECONDS = 1500      # 25 min – max plausible time for one send
_SIMPLE_SEND_TYPES = {
    'order_notification', 'despatch_confirmation', 'despatch_notification',
    'admin_copy', 'unusual_alert', 'generic_message', 'sale_cancellation',
    'purchase_notification', 'database_backup',
}
_RECENT_DISPATCH_TTL_SECONDS = 2 * 3600
_recent_dispatch_lock = threading.Lock()
_recent_dispatches = {}          # dedup key -> datetime it was last delivered


def _claim_for_send(notif_id: int) -> bool:
    """Atomically mark a pending row as being processed by this cycle.

    Returns False when the row is not pending anymore or another worker has
    claimed it recently (i.e. is actively sending it) – the caller must then
    skip the row so it is never sent twice. A claim made by THIS process is
    always refreshed (retries after a genuine failure must be allowed), while
    a fresh claim from another process blocks the row until it goes stale
    (crashed worker) or that process marks the row 'sent'.
    """
    pid = os.getpid()
    claim_ts = datetime.utcnow().isoformat()
    try:
        with get_session() as session:
            notif = session.query(PendingNotification).get(notif_id)
            if not notif or notif.status != 'pending':
                return False
            try:
                pl = json.loads(notif.payload_json)
            except Exception:
                pl = {}
            prev_pid = pl.get('_claim_pid')
            prev = pl.get('_claim_ts')
            if prev and prev_pid != pid:
                try:
                    prev_dt = datetime.fromisoformat(prev)
                    if (datetime.utcnow() - prev_dt).total_seconds() < _CLAIM_STALE_SECONDS:
                        # Fresh claim by another worker -> it is actively sending this row.
                        return False
                except Exception:
                    pass
            pl['_claim_ts'] = claim_ts
            pl['_claim_pid'] = pid
            new_payload_json = json.dumps(pl)
            updated = session.query(PendingNotification).filter(
                PendingNotification.id == notif_id,
                PendingNotification.status == 'pending',
                PendingNotification.payload_json == notif.payload_json
            ).update(
                {PendingNotification.payload_json: new_payload_json},
                synchronize_session=False
            )
            session.commit()
            return updated == 1
    except Exception as e:
        # DB contention etc. – be conservative: skip this row this cycle.
        logger.debug("Could not claim notification %d: %s", notif_id, e)
        return False


def _remember_dispatched(notification_type: str, payload: dict, chat_id: int):
    """Record that this process already delivered this notification content."""
    key = _get_dedup_key(notification_type, payload, chat_id)
    if key is None:
        return
    global _recent_dispatches
    now = datetime.utcnow()
    with _recent_dispatch_lock:
        if len(_recent_dispatches) > 10000:
            cutoff = now - timedelta(seconds=_RECENT_DISPATCH_TTL_SECONDS)
            _recent_dispatches = {k: v for k, v in _recent_dispatches.items() if v >= cutoff}
        _recent_dispatches[key] = now


def _was_recently_dispatched(notification_type: str, payload: dict, chat_id: int) -> bool:
    """True if this process already delivered the same content within the TTL.
    Multi-step report types are excluded – they keep their own per-step
    bookkeeping (_sent_steps) and must still be allowed to retry."""
    if notification_type not in _SIMPLE_SEND_TYPES:
        return False
    key = _get_dedup_key(notification_type, payload, chat_id)
    if key is None:
        return False
    now = datetime.utcnow()
    with _recent_dispatch_lock:
        last = _recent_dispatches.get(key)
        if last is None:
            return False
        if (now - last).total_seconds() < _RECENT_DISPATCH_TTL_SECONDS:
            return True
        _recent_dispatches.pop(key, None)
    return False

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

        payload = {}
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

            # Single-writer claim: if another cycle/process already grabbed this
            # row, do NOT send it again.
            if not await asyncio.to_thread(_claim_for_send, notif_id):
                logger.debug("Notification %d (type %s) claimed by another cycle; skipping", notif_id, nt)
                continue

            # If this process already delivered this exact content recently
            # (e.g. a previous cycle sent it but failed to mark it 'sent'),
            # just finish the bookkeeping – never send a second copy.
            if _was_recently_dispatched(nt, payload, chat_id):
                logger.info(
                    "Notification %d (type %s) already dispatched recently; marking sent without sending",
                    notif_id, nt
                )
                await asyncio.to_thread(_mark_sent, notif_id)
                continue

            # Dispatch with notif_id for step tracking
            await _dispatch_notification(bot, nt, chat_id, payload, notif_id)
            _remember_dispatched(nt, payload, chat_id)

        except (asyncio.TimeoutError, TimedOut) as e:
            if _is_db_file_notification(nt, payload):
                # .db upload: a timed-out snapshot upload must not be written off
                # as sent – retry it and let the admin receive it late.
                logger.warning(
                    "Notification %d (type %s) timed out uploading a .db file; will retry: %s",
                    notif_id, nt, e
                )
                await _mark_for_retry(notif_id, nt, retry_count, e)
                continue

            logger.warning(
                "Notification %d (type %s) timed out awaiting ack; assuming delivered, not retrying: %s",
                notif_id, nt, e
            )
            # Likely delivered – remember it so a retry can never resend it.
            _remember_dispatched(nt, payload, chat_id)
            await asyncio.to_thread(_mark_sent, notif_id)
            continue

        except NetworkError as e:
            cause = e.__cause__
            not_yet_sent = isinstance(cause, (httpx.ConnectError, httpx.ConnectTimeout))

            if not_yet_sent:
                logger.warning(
                    "Notification %d (type %s) failed before reaching Telegram (%s); will retry: %s",
                    notif_id, nt, type(cause).__name__, e
                )
                await _mark_for_retry(notif_id, nt, retry_count, e)
            elif _is_db_file_notification(nt, payload):
                # .db upload: never assume it landed – retry it.
                logger.warning(
                    "Notification %d (type %s) hit an ambiguous network error (%s) while "
                    "uploading a .db file; will retry: %s",
                    notif_id, nt, type(cause).__name__ if cause else "unknown", e
                )
                await _mark_for_retry(notif_id, nt, retry_count, e)
            else:
                logger.warning(
                    "Notification %d (type %s) hit an ambiguous network error (%s) after the request "
                    "may have been sent; assuming delivered, not retrying: %s",
                    notif_id, nt, type(cause).__name__ if cause else "unknown", e
                )
                # May have been delivered – remember it so a retry can never resend it.
                _remember_dispatched(nt, payload, chat_id)
                await asyncio.to_thread(_mark_sent, notif_id)
            continue

        except Exception as e:
            # Dispatch itself never completed - safe to retry, nothing was sent.
            await _mark_for_retry(notif_id, nt, retry_count, e)
            logger.warning(
                "Notification %d (type %s) failed (attempt %d): %s",
                notif_id, nt, retry_count + 1, e
            )
            continue
        try:
            await asyncio.to_thread(_mark_sent, notif_id)
            logger.debug("Sent notification %d (type %s)", notif_id, nt)
        except Exception as e:
            logger.critical(
                "Notification %d (type %s) was DELIVERED but could not be marked "
                "'sent' (DB error: %s). Retrying the bookkeeping write only - "
                "it will NOT be resent to Telegram.",
                notif_id, nt, e
            )
            for attempt in range(3):
                await asyncio.sleep(1)
                try:
                    await asyncio.to_thread(_mark_sent, notif_id)
                    logger.info("Notification %d marked sent after retry %d", notif_id, attempt + 1)
                    break
                except Exception as e2:
                    logger.critical(
                        "Retry %d/3 to mark notification %d as sent failed: %s",
                        attempt + 1, notif_id, e2
                    )
            else:
                logger.critical(
                    "Notification %d (type %s) STILL not marked sent after 3 retries. "
                    "It remains 'pending' and will be picked up again next cycle - "
                    "if the underlying send already succeeded, that next attempt "
                    "will be a genuine duplicate. Investigate the DB error above.",
                    notif_id, nt
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


async def _mark_for_retry(notif_id: int, notification_type: str, retry_count: int, error) -> None:
    """Bump the retry counter and schedule the next attempt with the standard
    exponential backoff (60s for reports, 30s otherwise, capped at 1 hour)."""
    new_retry = retry_count + 1
    if notification_type in REPORT_NOTIFICATION_TYPES:
        delay_seconds = min(3600, 60 * (2 ** (new_retry - 1)))
    else:
        delay_seconds = min(3600, 30 * (2 ** (new_retry - 1)))
    next_retry = datetime.utcnow() + timedelta(seconds=delay_seconds)
    await asyncio.to_thread(_mark_failed, notif_id, new_retry, next_retry, str(error)[:500])

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
                if _keys_match(notification_type, payload, pl, chat_id):
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
              'unusual_alert', 'generic_message', 'sale_cancellation', 'purchase_notification',
              'stock_in_notification'):
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

    elif nt == 'shipment_approval_report':
        await _send_shipment_approval_report(bot, chat_id, payload, notif_id)

    elif nt == 'profit_report':
        await _send_profit_report(bot, chat_id, payload, notif_id)

    elif nt == 'database_backup':
        await _send_database_backup(bot, chat_id, payload)

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
    """Send daily sales & profit PDF to a single chat, scoped to its products."""
    from telegrambot.handlers.reports.daily_sales_report import (
        daily_report_data, daily_report_caption, daily_report_pdf, daily_report_filename,
    )
    from services.report_subscription_service import scope_from_payload

    target_date = datetime.strptime(payload['target_date'], '%Y-%m-%d').date()
    scope = scope_from_payload(payload.get('scope'))
    product_ids = scope['product_ids']
    group_ids = scope['group_ids']
    scope_label = scope['label']
    sent_steps = set(payload.get('_sent_steps', []))

    # Step 1: Build data (all DB work off the event loop)
    data = await asyncio.to_thread(daily_report_data, target_date, product_ids, group_ids)

    # Step 2: Text message
    if 'text' not in sent_steps:
        await _safe_send_message(
            bot, chat_id,
            text=daily_report_caption(data, target_date, scope_label),
            parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 3: PDF document
    if 'document' not in sent_steps:
        pdf_bytes = await asyncio.to_thread(
            daily_report_pdf, data, target_date, scope_label)
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=daily_report_filename(target_date, scope_label),
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


# ---------------------------------------------------------------------
# Shipment Approval Report (to admin)
# ---------------------------------------------------------------------
async def _send_shipment_approval_report(bot: Bot, chat_id: int, payload: dict, notif_id: int):
    from services.import_shipment_service import ImportShipmentService
    from services.bank_account_service import BankAccountService
    from telegrambot.handlers.reports.shipment_report import generate_shipment_approval_pdf

    shipment_id = payload.get('shipment_id')
    if not shipment_id:
        raise ValueError("Missing shipment_id in shipment approval payload")

    service = ImportShipmentService()
    sent_steps = set(payload.get('_sent_steps', []))

    def _load_shipment():
        return service.get_by_id_with_relations(shipment_id)

    shipment = await asyncio.to_thread(_load_shipment)
    if not shipment:
        raise ValueError(f"Shipment #{shipment_id} not found")

    supplier_name = shipment.supplier.supplier_name if shipment.supplier else "Unknown"
    date_str = shipment.proforma_date.strftime("%d/%m/%Y") if shipment.proforma_date else ""

    # Step 1: short text notice
    if 'text' not in sent_steps:
        caption = (
            f"🚢 *Shipment #{shipment_id} Approved*\n"
            f"Supplier: {supplier_name}\n"
            f"Proforma Date: {date_str}\n"
            f"📄 Full landed-cost / tax PDF attached."
        )
        await _safe_send_message(bot, chat_id, text=caption, parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT)
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 2: PDF document
    if 'document' not in sent_steps:
        def _gen_pdf():
            tax_bank_name = ""
            if shipment.tax_bank_account_id:
                bank = BankAccountService().get_by_id(shipment.tax_bank_account_id)
                if bank:
                    tax_bank_name = f"{bank.bank_name} - {bank.account_name}"
            return generate_shipment_approval_pdf(shipment, tax_bank_name)

        pdf_bytes = await asyncio.to_thread(_gen_pdf)
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=f"shipment_{shipment_id}_approval.pdf",
            caption=f"🚢 Shipment #{shipment_id} – {supplier_name} – Landed Cost & Margin",
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'document')


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


# ---------------------------------------------------------------------
# Profit Report (periodic — daily/monthly/quarterly/semi-annual/annual)
# ---------------------------------------------------------------------
async def _send_profit_report(bot: Bot, chat_id: int, payload: dict, notif_id: int):
    """Send a periodic profit report PDF to a single chat, scoped to its products."""
    from datetime import date as date_cls
    from telegrambot.handlers.reports.profit_report import (
        generate_monthly_profit_pdf, generate_period_profit_pdf,
        build_monthly_profit_data, build_period_profit_data,
        build_period_product_breakdown,
    )
    from services.report_subscription_service import (
        scope_from_payload, scope_filename_tag,
    )

    period_type = payload['period_type']       # 'daily', 'monthly', 'quarterly', 'semiannual', 'annual'
    period_label = payload['period_label']     # e.g. 'Monthly Profit Report', '3-Month Profit Report'
    start_date = date_cls.fromisoformat(payload['start_date'])
    end_date = date_cls.fromisoformat(payload['end_date'])
    scope = scope_from_payload(payload.get('scope'))
    product_ids = scope['product_ids']
    group_ids = scope['group_ids']
    scope_label = scope['label']
    sent_steps = set(payload.get('_sent_steps', []))

    # Step 1: Text message
    if 'text' not in sent_steps:
        scope_line = f"🎯 *Scope:* {scope_label}\n" if scope_label else ""
        caption = (
            f"📊 *{period_label}*\n"
            f"📅 {start_date.strftime('%d/%m/%Y')} – {end_date.strftime('%d/%m/%Y')}\n"
            f"{scope_line}"
            f"📄 PDF report attached below."
        )
        await _safe_send_message(bot, chat_id, text=caption, parse_mode='Markdown', timeout=_REPORT_SEND_TIMEOUT)
        await asyncio.to_thread(_mark_step_done, notif_id, 'text')

    # Step 2: PDF document
    if 'document' not in sent_steps:
        def _build_pdf():
            if period_type == 'daily':
                # Same builder the scheduled daily send and the bot's back-dated
                # flow use, so all three render an identical report.
                from telegrambot.handlers.reports.daily_sales_report import (
                    daily_report_data, daily_report_pdf,
                )
                return daily_report_pdf(
                    daily_report_data(start_date, product_ids, group_ids),
                    start_date, scope_label,
                )
            elif period_type == 'monthly':
                data = build_monthly_profit_data(start_date, end_date, product_ids, group_ids)
                # Scoped periodic reports add a product table of their own.
                items = None
                if product_ids is not None:
                    items = build_period_product_breakdown(start_date, end_date, product_ids)
                return generate_monthly_profit_pdf(
                    period_label, start_date, end_date, data, items, scope_label)
            else:   # quarterly, semiannual, annual
                data = build_period_profit_data(start_date, end_date, product_ids, group_ids)
                items = None
                if product_ids is not None:
                    items = build_period_product_breakdown(start_date, end_date, product_ids)
                return generate_period_profit_pdf(
                    period_label, start_date, end_date, data, items, scope_label)

        pdf_bytes = await asyncio.to_thread(_build_pdf)
        filename_label = period_type.replace(' ', '_')
        tag = scope_filename_tag(scope_label)
        filename = (f"{filename_label}_profit_{tag}_{end_date}.pdf" if tag
                    else f"{filename_label}_profit_{end_date}.pdf")
        await _safe_send_document(
            bot, chat_id,
            document=BytesIO(pdf_bytes),
            filename=filename,
            timeout=_REPORT_SEND_TIMEOUT
        )
        await asyncio.to_thread(_mark_step_done, notif_id, 'document')


# ---------------------------------------------------------------------
# Database Backup (zipped copy of the .db, uploaded to the admin)
# ---------------------------------------------------------------------
def _zip_backup(file_path: str) -> bytes:
    """Compress a database backup into an in-memory .zip.

    SQLite files are mostly text and index pages, so deflate shrinks them
    several times over. That keeps the Telegram upload small even as the
    database grows, and leaves the raw .db untouched on disk for a direct
    local restore.
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.write(file_path, arcname=os.path.basename(file_path))
    return buffer.getvalue()


async def _send_database_backup(bot: Bot, chat_id: int, payload: dict):
    """Upload a zipped database backup to the admin.

    This is the offsite copy: if the PC is lost or its disk fails, the most
    recent snapshot is still recoverable from the Telegram chat.
    """
    file_path = payload.get('file_path')
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Backup file not found: {file_path}")

    db_name = os.path.basename(file_path)
    raw_mb = os.path.getsize(file_path) / (1024 * 1024)

    # Report when the snapshot was TAKEN, not when it was uploaded - a retry
    # can deliver it hours after the fact.
    taken_at = datetime.now()
    match = re.match(r'db_backup_(\d{8})_(\d{6})', db_name)
    if match:
        try:
            taken_at = datetime.strptime(match.group(1) + match.group(2), '%Y%m%d%H%M%S')
        except ValueError:
            pass

    # Compression is CPU-bound - keep it off the event loop.
    zipped = await asyncio.to_thread(_zip_backup, file_path)
    zip_mb = len(zipped) / (1024 * 1024)

    if zip_mb > _MAX_TELEGRAM_DOCUMENT_MB:
        # Never fail silently here - the admin must know the offsite copy stopped.
        logger.error(
            "Backup %s compresses to %.1f MB, over Telegram's %d MB limit; sending a warning instead",
            file_path, zip_mb, _MAX_TELEGRAM_DOCUMENT_MB
        )
        await _safe_send_message(
            bot, chat_id,
            text=(
                f"⚠️ *Database backup is too large for Telegram*\n"
                f"📦 {zip_mb:.1f} MB zipped from {raw_mb:.1f} MB "
                f"(limit: {_MAX_TELEGRAM_DOCUMENT_MB} MB)\n"
                f"💾 A local copy was saved on the PC as `{db_name}`.\n"
                f"Please copy it off the machine manually."
            ),
            parse_mode='Markdown',
            timeout=_FAST_SEND_TIMEOUT
        )
        return

    await _safe_send_document(
        bot, chat_id,
        document=BytesIO(zipped),
        filename=f"{db_name}.zip",
        caption=(
            f"🗄 *Database backup*\n"
            f"📅 {taken_at.strftime('%d/%m/%Y %H:%M')}\n"
            f"📦 {zip_mb:.1f} MB (from {raw_mb:.1f} MB)\n"
            f"⬇️ Unzip to get `{db_name}`, then restore it as `inventory.db`."
        ),
        parse_mode='Markdown',
        timeout=_REPORT_SEND_TIMEOUT
    )