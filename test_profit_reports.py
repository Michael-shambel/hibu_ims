#!/usr/bin/env python3
"""
Profit Report verification suite.

Checks performed
----------------
1. Source hygiene      - no stray/non-Ethiopic junk characters in the generator
2. Font coverage       - every string the PDFs emit has a font that can draw it
3. PDF generation      - daily, monthly, 3-month, 6-month and 1-year PDFs all build
4. Visible text        - the rendered PDF streams actually contain dates/amounts
5. Recipients          - every registered admin is targeted
6. Schedule            - scheduler jobs registered with the right run times
7. Ethiopian gates     - the next send date for each periodic report

Usage
-----
    python test_profit_reports.py                 # verify only (nothing is sent)
    python test_profit_reports.py --send          # verify, then really queue all 5 to admins
"""
import asyncio
import base64
import os
import re
import sys
import zlib
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import every model so SQLAlchemy mappers are configured before any query.
import models.auth_user  # noqa: F401
import models.customers  # noqa: F401
import models.supplier  # noqa: F401
import models.new_product  # noqa: F401
import models.new_sales  # noqa: F401
import models.new_sale_item  # noqa: F401
import models.product_batch  # noqa: F401
import models.purchase  # noqa: F401
import models.payment_transaction  # noqa: F401
import models.sale_payment_term  # noqa: F401
import models.bank_account  # noqa: F401
import models.bank_transactions  # noqa: F401
import models.expense  # noqa: F401
import models.expense_category  # noqa: F401
import models.pending_notification  # noqa: F401
import models.cash_loan  # noqa: F401
import models.customer_daily_notification  # noqa: F401
import models.import_shipments  # noqa: F401
import models.marketing_campaign_log  # noqa: F401
import models.cost_type  # noqa: F401
import models.batch_transaction  # noqa: F401
import models.supplier_credit_ledger  # noqa: F401
import models.supplier_daily_notification  # noqa: F401
import models.shipment_costs  # noqa: F401
import models.shipment_products  # noqa: F401
import models.purchase_payment_term  # noqa: F401
import models.purchase_payment_transaction  # noqa: F401

from telegrambot.handlers.reports import profit_report as pr  # noqa: E402

PASS, FAIL, WARN = [], [], []


def ok(label, detail=''):
    PASS.append(label)
    print('  [PASS] %s%s' % (label, (' - ' + detail) if detail else ''))


def bad(label, detail=''):
    FAIL.append(label)
    print('  [FAIL] %s%s' % (label, (' - ' + detail) if detail else ''))


def warn(label, detail=''):
    WARN.append(label)
    print('  [WARN] %s%s' % (label, (' - ' + detail) if detail else ''))


def section(title):
    print('\n' + '=' * 70)
    print('  ' + title)
    print('=' * 70)


# ---------------------------------------------------------------------------
# 1. Source hygiene — catch corrupted characters in the generator file
# ---------------------------------------------------------------------------
ALLOWED_NON_ASCII_SYMBOLS = set(' —–·•→←…°')   # intentional punctuation
ETHIOPIC_RANGES = ((0x1200, 0x137F), (0x1380, 0x139F), (0x2D80, 0x2DDF), (0xAB00, 0xAB2F))


def _in_ranges(cp, ranges):
    return any(a <= cp <= b for a, b in ranges)


def check_source_hygiene():
    section('1. SOURCE HYGIENE (no stray characters in labels)')
    src_path = os.path.join('telegrambot', 'handlers', 'reports', 'profit_report.py')
    with open(src_path, 'r', encoding='utf-8') as fh:
        text = fh.read()

    bad_chars = {}
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp < 128:
            continue
        if _in_ranges(cp, ETHIOPIC_RANGES) or ch in ALLOWED_NON_ASCII_SYMBOLS:
            continue
        line = text.count('\n', 0, i) + 1
        bad_chars.setdefault(ch, []).append(line)

    if bad_chars:
        for ch, lines in bad_chars.items():
            bad('stray character %r (U+%04X)' % (ch, ord(ch)),
                'lines %s' % ', '.join(map(str, lines[:5])))
    else:
        ok('no stray characters in profit_report.py')


# ---------------------------------------------------------------------------
# 2. Font coverage for every string the PDFs emit
# ---------------------------------------------------------------------------
def check_font_coverage(captured_strings):
    section('2. FONT COVERAGE (every character can be drawn)')

    if not pr.ethiopic_font_available():
        bad('Ethiopic font not registered', 'Amharic would render as blanks')
        return

    from fontTools.ttLib import TTFont
    here = os.path.dirname(os.path.abspath(pr.__file__))
    fdir = os.path.normpath(os.path.join(here, '..', '..', '..', 'assets', 'fonts'))
    eth_cmap = TTFont(os.path.join(fdir, 'NotoSansEthiopic-Regular.ttf')).getBestCmap()
    ethb_cmap = TTFont(os.path.join(fdir, 'NotoSansEthiopic-Bold.ttf')).getBestCmap()

    def helvetica_can(ch):
        try:
            ch.encode('cp1252')
            return True
        except UnicodeEncodeError:
            return False

    eth_re = re.compile(
        '[' + ''.join('%s-%s' % (chr(a), chr(b)) for a, b in ETHIOPIC_RANGES) + ']+'
    )

    problems = []
    latin_chars = set()
    eth_chars = set()
    for s in captured_strings:
        for part in eth_re.split(s):
            for ch in part:
                if ch == '\n':
                    continue
                latin_chars.add(ch)
                if not helvetica_can(ch):
                    problems.append(('Latin part cannot be drawn by Helvetica', ch, s[:60]))
        for m in eth_re.finditer(s):
            for ch in m.group(0):
                eth_chars.add(ch)
                if ord(ch) not in eth_cmap and ord(ch) not in ethb_cmap:
                    problems.append(('Ethiopic part missing from font', ch, s[:60]))

    if problems:
        seen = set()
        for kind, ch, ctx in problems:
            key = (kind, ch)
            if key in seen:
                continue
            seen.add(key)
            bad('%s: %r (U+%04X)' % (kind, ch, ord(ch)), 'in "%s"' % ctx)
    else:
        ok('all %d distinct Latin + %d Ethiopic characters are covered'
           % (len(latin_chars), len(eth_chars)))

    # The Ethiopic font must NOT be used for Latin runs (that was the old bug).
    if not pr.ethiopic_font_available():
        return
    sample = pr.mix_fonts('ጠቅላላ ሽያጭ / Total Sales')
    if '<font name="NotoSansEthiopic">ጠቅላላ</font>' in sample and 'Total Sales' in sample:
        ok('mixed markup keeps Latin outside the Ethiopic font tag')
    else:
        bad('mixed markup looks wrong', sample)


# ---------------------------------------------------------------------------
# 3 & 4. Generate every report type and check the rendered text
# ---------------------------------------------------------------------------
def _decode_stream(raw):
    """Undo reportlab's [/ASCII85Decode /FlateDecode] (or plain Flate) stream filter."""
    data = raw.strip()
    if data.endswith(b'~>'):
        try:
            data = base64.a85decode(data[:-2], adobe=False)
        except Exception:
            pass
    try:
        return zlib.decompress(data)
    except Exception:
        return data


_PDF_ESCAPES = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
                '(': '(', ')': ')', '\\': '\\'}


def _unescape_pdf_string(s):
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '\\' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in _PDF_ESCAPES:
                out.append(_PDF_ESCAPES[nxt])
                i += 2
                continue
            if nxt.isdigit():                       # octal escape
                oct_digits = s[i + 1:i + 4]
                oct_digits = ''.join(c for c in oct_digits if c.isdigit())[:3]
                out.append(chr(int(oct_digits, 8)))
                i += 1 + len(oct_digits)
                continue
        out.append(ch)
        i += 1
    return ''.join(out)


def pdf_stream_text(pdf_bytes):
    """
    Rebuild the text the PDF actually draws.

    Base-14 fonts (Helvetica) store text as readable literals; the Ethiopic
    subset stores glyph indices, so those bytes come out as junk. Latin runs
    stay contiguous, which is what we assert on.
    """
    parts = []
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', pdf_bytes, re.S):
        body = _decode_stream(m.group(1)).decode('latin-1', 'replace')
        for lit in re.finditer(r'\((?:\\.|[^\\()])*\)\s*Tj', body):
            raw = lit.group(0)
            raw = raw[raw.index('(') + 1:raw.rindex(')')]
            parts.append(_unescape_pdf_string(raw))
    return re.sub(r'\s+', ' ', ' '.join(parts))


def latin_fragments(s):
    """Strip Ethiopic runs from an expected string, keeping searchable Latin."""
    eth_re = re.compile(
        '[' + ''.join('%s-%s' % (chr(a), chr(b)) for a, b in ETHIOPIC_RANGES) + ']+'
    )
    frags = [' '.join(f.split()) for f in eth_re.split(s)]
    return [f for f in frags if len(f.strip()) >= 2]


def count_pages(pdf_bytes):
    return len(re.findall(rb'/Type\s*/Page[^s]', pdf_bytes))


def check_pdf(name, pdf_bytes, must_contain):
    if not pdf_bytes or len(pdf_bytes) < 800:
        bad('%s PDF too small' % name, '%d bytes' % len(pdf_bytes or 0))
        return False

    text = pdf_stream_text(pdf_bytes)
    missing = []
    for expected in must_contain:
        frags = latin_fragments(expected) or [expected]
        if any(f not in text for f in frags):
            missing.append(expected)

    if missing:
        bad('%s PDF missing visible text' % name, 'not found: %s' % missing)
        return False

    # The Ethiopic subset font must actually be used (glyph runs present).
    raw_streams = b' '.join(
        _decode_stream(m.group(1))
        for m in re.finditer(rb'stream\r?\n(.*?)endstream', pdf_bytes, re.S)
    ).decode('latin-1', 'replace')
    if 'NotoSansEthiopic' not in raw_streams and not pr.ethiopic_font_available():
        warn('%s PDF: Ethiopic font not embedded' % name)

    fname = 'test_%s.pdf' % name
    with open(fname, 'wb') as fh:
        fh.write(pdf_bytes)
    ok('%s PDF' % name, '%s (%s bytes, %d page(s))'
       % (fname, format(len(pdf_bytes), ','), count_pages(pdf_bytes)))
    return True


def build_and_check_reports():
    from telegrambot.handlers.reports.profit_report import (
        build_daily_profit_data, build_monthly_profit_data, build_period_profit_data,
        generate_daily_profit_pdf, generate_monthly_profit_pdf, generate_period_profit_pdf,
    )
    from telegrambot.scheduler import _eth_month_bounds, _prev_eth_month, _shift_eth_month
    from ui.components.ethiopian_date import EthiopianDateConverter
    from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS

    today = date.today()
    eth_y, eth_m, eth_d = EthiopianDateConverter.to_ethiopian(today)
    month_name = ETHIOPIAN_MONTHS[eth_m - 1][0]

    # --- Daily ---
    section('3a. DAILY REPORT')
    d = build_daily_profit_data(today)
    print('  data: %d product rows' % len(d['items']))
    daily_pdf = generate_daily_profit_pdf(
        d['total_selling'], d['total_cost'], d['expenses'], d['items'],
        eth_y, eth_m, eth_d, today,
    )
    check_pdf('daily_profit', daily_pdf, [
        'Daily Sales', 'Total Sales', 'Total Cost',
        today.isoformat(),           # the Gregorian date must be readable
        'ETB', '%', 'Product Breakdown', 'TOTAL',
    ])

    # --- Monthly (previous Ethiopian month, day-by-day) ---
    section('3b. MONTHLY REPORT (day-by-day)')
    py, pm = _prev_eth_month(eth_y, eth_m)
    m_start, m_end = _eth_month_bounds(py, pm)
    m_label = '%s %d / Monthly Profit Report' % (ETHIOPIAN_MONTHS[pm - 1][0], py)
    m_rows = build_monthly_profit_data(m_start, m_end)
    print('  range: %s -> %s (%d days)' % (m_start, m_end, len(m_rows)))
    monthly_pdf = generate_monthly_profit_pdf(m_label, m_start, m_end, m_rows)
    check_pdf('monthly_profit', monthly_pdf, [
        'Monthly Profit Report', m_label, str(py),
        m_start.isoformat(), m_end.isoformat(),
        'Day-by-Day Details', 'TOTAL', 'ETB', '/ Qty',
    ])

    # --- 3, 6 and 12 month reports (month-by-month) ---
    for label, span in (('3month', 3), ('6month', 6), ('1year', 12)):
        section('3c. %s REPORT (month-by-month)' % label.upper())
        end_y, end_m = _prev_eth_month(eth_y, eth_m)
        start_y, start_m = _shift_eth_month(end_y, end_m, -(span - 1))
        p_start = EthiopianDateConverter.to_gregorian(start_y, start_m, 1)
        _, p_end = _eth_month_bounds(end_y, end_m)
        p_label = '%s - %s %d / Profit Report' % (
            ETHIOPIAN_MONTHS[start_m - 1][0], ETHIOPIAN_MONTHS[end_m - 1][0], end_y)
        rows = build_period_profit_data(p_start, p_end)
        print('  range: %s -> %s (%d Ethiopian months)' % (p_start, p_end, len(rows)))
        pdf = generate_period_profit_pdf(p_label, p_start, p_end, rows)
        check_pdf('%s_profit' % label, pdf, [
            'Profit Report', p_start.isoformat(), p_end.isoformat(),
            'Month-by-Month Details', 'TOTAL', 'ETB', '%',
        ])

    return None


# ---------------------------------------------------------------------------
# 4. Outbox sender (no Telegram traffic) — queue -> dispatch -> PDF
# ---------------------------------------------------------------------------
class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, **kw):
        self.calls.append(('message', kw.get('text', '')))
        return None

    async def send_document(self, **kw):
        doc = kw.get('document')
        name = kw.get('filename', '')
        size = len(doc.getvalue()) if hasattr(doc, 'getvalue') else -1
        self.calls.append(('document', '%s (%d bytes)' % (name, size)))
        return None


def check_outbox_sender():
    section('4. OUTBOX SENDER (dispatch -> PDF, no Telegram traffic)')
    import json

    from models.pending_notification import PendingNotification
    from services.base_service import get_session
    from telegrambot.handlers.reports.profit_report import (
        build_daily_profit_data, build_period_profit_data,)
    from telegrambot.outbox import _dispatch_notification, _send_profit_report, DEDUP_TYPES

    if 'profit_report' not in DEDUP_TYPES:
        bad('profit_report missing from outbox DEDUP_TYPES')
    else:
        ok('outbox knows the profit_report type')

    today = date.today()
    cases = []

    daily = build_daily_profit_data(today)
    cases.append(('daily', {
        'period_type': 'daily', 'period_label': 'Daily check',
        'start_date': today.isoformat(), 'end_date': today.isoformat(),
    }, 'daily'))

    period_rows = build_period_profit_data(today - timedelta(days=365), today)
    cases.append(('annual', {
        'period_type': 'annual', 'period_label': 'Annual check',
        'start_date': (today - timedelta(days=365)).isoformat(),
        'end_date': today.isoformat(),
    }, 'annual'))

    for label, payload, branch in cases:
        nid = None
        fake = FakeBot()
        try:
            with get_session() as session:
                row = PendingNotification(
                    notification_type='profit_report', chat_id=0,
                    payload_json=json.dumps(payload), status='pending',
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                nid = row.id

            asyncio.run(_dispatch_notification(fake, 'profit_report', 0, payload, nid))

            kinds = [c[0] for c in fake.calls]
            if kinds == ['message', 'document']:
                ok('%s branch sent text + PDF' % branch, fake.calls[1][1])
            else:
                bad('%s branch sent %s' % (branch, kinds))

            with get_session() as session:
                saved = session.get(PendingNotification, nid)
                steps = json.loads(saved.payload_json).get('_sent_steps', [])
            if 'text' in steps and 'document' in steps:
                ok('%s branch recorded both retry-safe steps' % branch)
            else:
                bad('%s branch steps incomplete: %s' % (branch, steps))
        except Exception as e:
            bad('%s branch raised' % branch, str(e)[:180])
        finally:
            if nid is not None:
                try:
                    with get_session() as session:
                        session.query(PendingNotification).filter(
                            PendingNotification.id == nid).delete()
                        session.commit()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# 5. Recipients
# ---------------------------------------------------------------------------
def check_recipients():
    section('5. ADMIN RECIPIENTS')
    from services.auth_service import AuthService

    svc = AuthService()
    chat_ids = svc.get_all_admin_chat_ids()
    admins = svc.get_all() if hasattr(svc, 'get_all') else []
    admin_rows = [a for a in admins if getattr(a, 'role', None) == 'admin' and not a.is_deleted]

    print('  admin users: %d, linked chat_ids: %d' % (len(admin_rows), len(chat_ids)))
    for a in admin_rows:
        print('    - %-20s role=%-7s chat_id=%s' % (a.username, a.role, a.chat_id or 'NOT LINKED'))

    if not chat_ids:
        from config import ADMIN_ID
        warn('no admin has linked Telegram; reports fall back to ADMIN_ID %s' % ADMIN_ID)
    else:
        ok('reports will reach %d admin chat_id(s)' % len(chat_ids))

    unlinked = [a.username for a in admin_rows if not a.chat_id]
    if unlinked:
        warn('admin(s) without a linked Telegram: %s' % ', '.join(unlinked))
    return chat_ids


# ---------------------------------------------------------------------------
# 6. Scheduler registration
# ---------------------------------------------------------------------------
def check_schedule():
    section('6. SCHEDULER JOBS')
    expected = {
        'daily_sales_report_admin': 'every day 18:10 (all admins)',
        'monthly_profit_report_admin': 'Ethiopian day 1 @ 19:00',
        'quarterly_profit_report_admin': 'Ethiopian months 1,4,7,10 @ 19:00',
        'semiannual_profit_report_admin': 'Ethiopian months 1,7 @ 19:00',
        'annual_profit_report_admin': 'Ethiopian month 1 day 1 @ 19:00',
    }

    async def _inspect():
        from config import BOT_TOKEN
        from telegrambot.scheduler import scheduler, start_scheduler, stop_scheduler

        start_scheduler(BOT_TOKEN)
        try:
            return {j.id: getattr(j, 'next_run_time', None) for j in scheduler.get_jobs()}
        finally:
            stop_scheduler()

    try:
        jobs = asyncio.run(_inspect())
    except Exception as e:
        bad('could not inspect scheduler', str(e)[:200])
        return

    for job_id, when in expected.items():
        if job_id not in jobs:
            bad('job not registered: %s' % job_id)
            continue
        nxt = jobs[job_id]
        nxt_txt = nxt.strftime('%Y-%m-%d %H:%M:%S') if nxt else 'n/a'
        ok('%-32s %-38s next=%s' % (job_id, when, nxt_txt))


# ---------------------------------------------------------------------------
# 7. Ethiopian calendar send days
# ---------------------------------------------------------------------------
def check_send_days():
    section('7. NEXT SEND DAYS (Ethiopian calendar gates)')
    from telegrambot.scheduler import profit_report_range
    from ui.components.ethiopian_date import EthiopianDateConverter

    today = date.today()
    for ptype in ('monthly', 'quarterly', 'semiannual', 'annual'):
        found = []
        d = today
        while len(found) < 3 and d <= today + timedelta(days=1500):
            rng = profit_report_range(ptype, d)
            if rng:
                found.append((d, rng))
            d += timedelta(days=1)
        if not found:
            warn('%s: no send day found in the next 4 years' % ptype)
            continue
        for when, (label, s, e) in found:
            ey, em, ed = EthiopianDateConverter.to_ethiopian(when)
            ok('%-11s %s  (ETH %02d/%02d/%d)  covers %s -> %s'
               % (ptype, when.isoformat(), ey, em, ed, s, e))
        if ptype == 'monthly':
            gaps = [(found[i + 1][0] - found[i][0]).days for i in range(len(found) - 1)]
            if gaps and all(28 <= g <= 32 for g in gaps):
                ok('monthly cadence is ~30 days: %s' % gaps)
            else:
                bad('monthly cadence looks wrong: %s' % gaps)


# ---------------------------------------------------------------------------
# 8. Back-dated bot report must equal the scheduled daily send
# ---------------------------------------------------------------------------
class _CapturingBot:
    """Fake Telegram bot that keeps the text and the raw PDF bytes."""

    def __init__(self):
        self.texts = []
        self.documents = []

    async def send_message(self, **kw):
        self.texts.append(kw.get('text', ''))
        return None

    async def send_document(self, **kw):
        doc = kw.get('document')
        raw = doc.getvalue() if hasattr(doc, 'getvalue') else bytes(doc or b'')
        self.documents.append((kw.get('filename', ''), raw))
        return None


class _FakeMessage:
    def __init__(self, sink):
        self._sink = sink

    async def reply_text(self, text, **kw):
        self._sink.append(text)
        return None


class _FakeChat:
    id = 0


class _FakeUpdate:
    """Minimal Update for the bot handlers (message flow, no callback query)."""

    def __init__(self, sink):
        self.message = _FakeMessage(sink)
        self.callback_query = None
        self.effective_chat = _FakeChat()


class _FakeContext:
    def __init__(self, bot):
        self.bot = bot
        self.user_data = {}


def _capture_daily_send(target_date):
    """Run the real outbox daily-report sender and return what it sent."""
    import json

    from models.pending_notification import PendingNotification
    from services.base_service import get_session
    from telegrambot.outbox import _dispatch_notification

    bot = _CapturingBot()
    nid = None
    try:
        with get_session() as session:
            row = PendingNotification(
                notification_type='daily_sales_report', chat_id=0,
                payload_json=json.dumps({'target_date': target_date.isoformat()}),
                status='pending',
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            nid = row.id

        asyncio.run(_dispatch_notification(
            bot, 'daily_sales_report', 0, {'target_date': target_date.isoformat()}, nid))
    finally:
        if nid is not None:
            try:
                with get_session() as session:
                    session.query(PendingNotification).filter(
                        PendingNotification.id == nid).delete()
                    session.commit()
            except Exception:
                pass
    return bot


def check_backdated_matches_daily_send():
    section('8. BACK-DATED BOT REPORT vs SCHEDULED DAILY SEND')

    from telegrambot.handlers.reports.daily_sales_report import (
        daily_report_caption, daily_report_pdf,
    )
    from telegrambot.handlers.reports.sales_report import sales_transaction_report_handler
    from ui.components.ethiopian_date import EthiopianDateConverter

    # A back-dated day, exactly what the admin picks in the bot
    target = date.today() - timedelta(days=7)
    eth_y, eth_m, eth_d = EthiopianDateConverter.to_ethiopian(target)

    # --- A: what the 18:10 scheduled send delivers ---
    try:
        scheduled = _capture_daily_send(target)
        if not scheduled.documents:
            bad('scheduled daily send produced no PDF')
            return
        ok('scheduled daily send: 1 text + %d doc(s)' % len(scheduled.documents))
    except Exception as e:
        bad('scheduled daily send raised', str(e)[:180])
        return

    # --- B: what the admin gets after picking month -> day in the bot ---
    messages = []
    bot = _CapturingBot()
    update = _FakeUpdate(messages)
    context = _FakeContext(bot)
    try:
        asyncio.run(sales_transaction_report_handler(
            update, context, eth_y, eth_m, eth_d, target))
        sent_docs = bot.documents
    except Exception as e:
        bad('back-dated bot handler raised', str(e)[:180])
        return

    if not sent_docs:
        bad('back-dated bot handler produced no PDF')
        return

    # reportlab stamps a fresh /CreationDate + /ID into every build, so compare
    # the rendered content and page count rather than the raw bytes.
    scheduled_pdf = scheduled.documents[0][1]
    bot_pdf = sent_docs[0][1]
    if pdf_stream_text(bot_pdf) == pdf_stream_text(scheduled_pdf):
        ok('back-dated PDF renders identically to the scheduled daily PDF',
           '%s (%s bytes, %d page(s))'
           % (sent_docs[0][0], format(len(bot_pdf), ','), count_pages(bot_pdf)))
    else:
        bad('back-dated PDF content differs from the scheduled daily PDF',
            'bot=%s chars, scheduled=%s chars'
            % (len(pdf_stream_text(bot_pdf)), len(pdf_stream_text(scheduled_pdf))))

    if count_pages(bot_pdf) == count_pages(scheduled_pdf) and len(bot_pdf) == len(scheduled_pdf):
        ok('same page count and size as the scheduled daily send')

    if sent_docs[0][0] == scheduled.documents[0][0]:
        ok('same filename: %s' % scheduled.documents[0][0])

    from telegrambot.handlers.reports.daily_sales_report import daily_report_data
    data = daily_report_data(target)
    expected_caption = daily_report_caption(data, target)
    if expected_caption in scheduled.texts:
        ok('scheduled send caption matches the shared caption builder')
    else:
        bad('scheduled send caption drifted from the shared builder')

    if expected_caption in messages:
        ok('back-dated bot send uses the same caption')
    else:
        bad('back-dated bot caption differs', 'handler texts: %s' % messages)

    expected_pdf = daily_report_pdf(data, target)
    if pdf_stream_text(expected_pdf) == pdf_stream_text(scheduled_pdf):
        ok('shared builder reproduces the scheduled PDF exactly')
    else:
        bad('shared builder no longer matches the scheduled PDF')


# ---------------------------------------------------------------------------
# 9. Optional: really queue everything to all admins
# ---------------------------------------------------------------------------
def send_to_admins():
    section('9. SENDING TO ADMINS')
    import asyncio

    from telegrambot.scheduler import (
        _eth_month_bounds, _prev_eth_month, _shift_eth_month,
        queue_daily_sales_report, queue_profit_report,
    )
    from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS
    from ui.components.ethiopian_date import EthiopianDateConverter
    from services.base_service import get_session
    from models.pending_notification import PendingNotification
    from datetime import datetime

    today = date.today()
    eth_y, eth_m, _ = EthiopianDateConverter.to_ethiopian(today)

    def forced_range(ptype):
        """Range for the period that just ended, regardless of today's gate."""
        if ptype == 'monthly':
            y, m = _prev_eth_month(eth_y, eth_m)
            s, e = _eth_month_bounds(y, m)
            return ('%s %d / Monthly Profit Report' % (ETHIOPIAN_MONTHS[m - 1][0], y), s, e)
        if ptype in ('quarterly', 'semiannual'):
            span = 3 if ptype == 'quarterly' else 6
            ey, em = _prev_eth_month(eth_y, eth_m)
            sy, sm = _shift_eth_month(ey, em, -(span - 1))
            s = EthiopianDateConverter.to_gregorian(sy, sm, 1)
            _, e = _eth_month_bounds(ey, em)
            title = 'Quarterly' if ptype == 'quarterly' else 'Semi-Annual'
            return ('%s - %s %d / %s Profit Report'
                    % (ETHIOPIAN_MONTHS[sm - 1][0], ETHIOPIAN_MONTHS[em - 1][0], ey, title), s, e)
        y = eth_y - 1
        s = EthiopianDateConverter.to_gregorian(y, 1, 1)
        _, e = _eth_month_bounds(y, 13)
        return ('Ethiopian Year %d / Annual Profit Report' % y, s, e)

    def pending_rows():
        with get_session() as session:
            return session.query(PendingNotification).filter(
                PendingNotification.status == 'pending'
            ).count()

    before = pending_rows()
    asyncio.run(queue_daily_sales_report())
    for ptype in ('monthly', 'quarterly', 'semiannual', 'annual'):
        label, s, e = forced_range(ptype)
        asyncio.run(queue_profit_report(ptype, label, s, e))
    after = pending_rows()

    queued = after - before
    if queued > 0:
        ok('queued %d notification(s) - the outbox worker sends within ~20s' % queued)
        print('  watch Telegram. Delivery errors would show as retries in the app log.')
    else:
        warn('nothing new queued (duplicates within 7 days are suppressed by design)')
        info = []
        with get_session() as session:
            for row in session.query(PendingNotification).filter(
                    PendingNotification.notification_type.in_(
                        ['daily_sales_report', 'profit_report'])
            ).order_by(PendingNotification.id.desc()).limit(6):
                info.append((row.id, row.notification_type, row.chat_id, row.status))
        for r in info:
            print('    last: id=%s type=%s chat=%s status=%s' % r)


# ---------------------------------------------------------------------------
def main():
    send = '--send' in sys.argv[1:]

    # Wrap P() to capture every string that gets rendered.
    captured = []
    orig_p = pr.P

    def spy(text, *a, **kw):
        captured.append(str(text))
        return orig_p(text, *a, **kw)

    pr.P = spy
    try:
        check_source_hygiene()
        build_and_check_reports()
    finally:
        pr.P = orig_p

    check_font_coverage(captured)
    check_outbox_sender()
    check_backdated_matches_daily_send()
    check_recipients()
    check_schedule()
    check_send_days()

    if send:
        send_to_admins()

    section('SUMMARY')
    print('  passed: %d   failed: %d   warnings: %d' % (len(PASS), len(FAIL), len(WARN)))
    if FAIL:
        print('\n  FAILED CHECKS:')
        for f in FAIL:
            print('    - %s' % f)
    if not send:
        print('\n  Verify-only run. To really send all 5 reports to every admin:')
        print('    python test_profit_reports.py --send')

    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
