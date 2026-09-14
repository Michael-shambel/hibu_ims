#!/usr/bin/env python3
"""
Profit Report PDF Generators
Generates landscape A4 PDFs for:
- Daily profit report: summary box + product-level breakdown
- Monthly profit report: day-by-day table (like MonthlyProfitSummaryDialog)
- Period profit report: month-by-month table (like MonthlySummaryDialog)

FONT NOTE
---------
Noto Sans Ethiopic contains ONLY Ethiopic glyphs (plus space/hyphen). It has no
Latin letters, no digits, no '%' and no '/'. Rendering an English word, a date or
a number with it produces invisible text. Therefore every string that mixes
Amharic/Tigrinya with Latin is emitted as reportlab markup where only the
Ethiopic runs are wrapped in <font name="NotoSansEthiopic">...</font>, so the
Latin/digits fall back to Helvetica which does cover them.
"""
import io
import logging
import os
import re
from datetime import date, datetime, time, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ui.components.ethiopian_date import EthiopianDateConverter
from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS

logger = logging.getLogger(__name__)

ETH_FONT = 'NotoSansEthiopic'
ETH_FONT_BOLD = 'NotoSansEthiopic-Bold'
BASE_FONT = 'Helvetica'
BASE_FONT_BOLD = 'Helvetica-Bold'


# ---------------------------------------------------------------------------
# Font registration
# ---------------------------------------------------------------------------
def _register_ethiopian_font():
    """Register Noto Sans Ethiopic (Amharic/Tigrinya) if the files are present."""
    here = os.path.dirname(os.path.abspath(__file__))
    font_dir = os.path.normpath(os.path.join(here, '..', '..', '..', 'assets', 'fonts'))

    for font_name, filename in ((ETH_FONT, 'NotoSansEthiopic-Regular.ttf'),
                                (ETH_FONT_BOLD, 'NotoSansEthiopic-Bold.ttf')):
        path = os.path.join(font_dir, filename)
        if font_name in pdfmetrics.getRegisteredFontNames():
            continue
        try:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(font_name, path))
                logger.info("Registered %s from %s", font_name, path)
            else:
                logger.warning("Ethiopic font not found: %s", path)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Could not register %s: %s", font_name, e)


_register_ethiopian_font()


def _has_font(name: str) -> bool:
    try:
        return name in pdfmetrics.getRegisteredFontNames()
    except Exception:
        return False


def ethiopic_font_available() -> bool:
    """True when the Ethiopic font registered successfully."""
    return _has_font(ETH_FONT)


# ---------------------------------------------------------------------------
# Mixed-script text helpers
# ---------------------------------------------------------------------------
_ETHIOPIC_RANGES = (
    (0x1200, 0x137F),   # Ethiopic
    (0x1380, 0x139F),   # Ethiopic Supplement
    (0x2D80, 0x2DDF),   # Ethiopic Extended
    (0xAB00, 0xAB2F),   # Ethiopic Extended-A
)

_ETHIOPIC_RUN = re.compile(
    '[' + ''.join('%s-%s' % (chr(a), chr(b)) for a, b in _ETHIOPIC_RANGES) + ']+'
)


def is_ethiopic_text(text: str) -> bool:
    """True if the string contains at least one Ethiopic (Amharic/Tigrinya) char."""
    return bool(_ETHIOPIC_RUN.search(text or ''))


def escape_markup(text: str) -> str:
    """Escape characters that reportlab's mini-XML parser would misinterpret."""
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def mix_fonts(text: str, bold: bool = False) -> str:
    """
    Wrap Ethiopic runs in a <font> tag so reportlab uses the Ethiopic font for
    them while Latin letters/digits keep using the base (Helvetica) font.

    Input must already be XML-escaped when it comes from user data.
    """
    eth_font = ETH_FONT_BOLD if bold else ETH_FONT
    if not _has_font(eth_font):
        return text
    return _ETHIOPIC_RUN.sub(lambda m: '<font name="%s">%s</font>' % (eth_font, m.group(0)), text)


_ALIGN = {'L': TA_LEFT, 'C': TA_CENTER, 'R': TA_RIGHT}
_STYLE_CACHE = {}


def _style(size: int, bold: bool, align: str, color):
    key = (size, bold, align, str(color))
    st = _STYLE_CACHE.get(key)
    if st is None:
        st = ParagraphStyle(
            name='cell_%s_%s_%s' % (size, bold, align),
            fontName=BASE_FONT_BOLD if bold else BASE_FONT,
            fontSize=size,
            leading=size + 2.5,
            alignment=_ALIGN.get(align, TA_LEFT),
            textColor=color,
            spaceBefore=0,
            spaceAfter=0,
        )
        _STYLE_CACHE[key] = st
    return st


def P(text, size=9, bold=False, align='L', color=None):
    """Build a Paragraph that renders mixed Amharic/Latin text correctly."""
    return Paragraph(
        mix_fonts(escape_markup(text), bold=bold),
        _style(size, bold, align, color if color is not None else colors.black),
    )


def _money(val) -> str:
    try:
        return "ETB %s" % format(float(val or 0.0), ',.2f')
    except (TypeError, ValueError):
        return "ETB 0.00"


def _pct(val) -> str:
    try:
        return "%.1f%%" % float(val)
    except (TypeError, ValueError):
        return "-"


def _num(val) -> str:
    try:
        return str(int(val))
    except (TypeError, ValueError):
        return "0"


def _eth_date_str(d: date) -> str:
    """Ethiopian calendar date, e.g. 'መስከረም 14, 2019'."""
    y, m, day = EthiopianDateConverter.to_ethiopian(d)
    month_name = ETHIOPIAN_MONTHS[m - 1][0] if 1 <= m <= len(ETHIOPIAN_MONTHS) else str(m)
    return "%s %d, %d" % (month_name, day, y)


def _range_label(start: date, end: date) -> str:
    """Human readable Ethiopian + Gregorian range for monthly/period reports."""
    eth = "%s  -  %s" % (_eth_date_str(start), _eth_date_str(end))
    greg = start.isoformat() if start == end else "%s to %s" % (start.isoformat(), end.isoformat())
    return "%s   (Gregorian: %s)" % (eth, greg)


# ---------------------------------------------------------------------------
# Shared table styling
# ---------------------------------------------------------------------------
def _summary_table(rows):
    """Left-column labels on grey, right-column values aligned right."""
    data = [[P(label, size=10), P(value, size=10, bold=True, align='R')] for label, value in rows]
    t = Table(data, colWidths=[95 * mm, 65 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8edf3')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#9aa7b5')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


def _detail_table(header_labels, rows, col_widths, total_row=None, aligns=None):
    """
    Build a striped detail table. All cells are Paragraphs so that mixed
    Ethiopic/Latin text always finds a font that covers it.
    """
    aligns = aligns or (['L'] + ['R'] * (len(header_labels) - 1))

    data = [[P(h, size=9, bold=True, align='C', color=colors.whitesmoke) for h in header_labels]]
    for row in rows:
        data.append([P(cell, size=9, align=aligns[i]) for i, cell in enumerate(row)])

    if total_row is not None:
        data.append([P(cell, size=9, bold=True, align=aligns[i]) for i, cell in enumerate(total_row)])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5b6d')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#9aa7b5')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1 if total_row is None else -2),
         [colors.white, colors.HexColor('#f4f7fa')]),
    ]
    if total_row is not None:
        style.append(('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#cfdcea')))
    t.setStyle(TableStyle(style))
    return t


def _doc(buffer):
    return SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )


# ---------------------------------------------------------------------------
# 1. Daily Profit PDF — summary box + product breakdown table
# ---------------------------------------------------------------------------
def generate_daily_profit_pdf(
    total_selling: float,
    total_cost: float,
    expenses: float,
    items: list,
    eth_year: int,
    eth_month: int,
    eth_day: int,
    greg_date: date,
) -> bytes:
    """Daily report: summary box + per-product breakdown."""
    buffer = io.BytesIO()
    doc = _doc(buffer)
    story = []

    month_name = ETHIOPIAN_MONTHS[eth_month - 1][0] if 1 <= eth_month <= len(ETHIOPIAN_MONTHS) else str(eth_month)
    story.append(P("ናይ መዓልታዊ ሽያጥን ትርፍን ጸብጻብ / Daily Sales & Profit Report", size=16, bold=True, align='C'))
    story.append(P("%s %d, %d   (Gregorian: %s)" % (month_name, eth_day, eth_year, greg_date.isoformat()),
                   size=11, align='C'))
    story.append(Spacer(1, 6 * mm))

    net_profit = float(total_selling or 0) - float(total_cost or 0) - float(expenses or 0)
    margin = (net_profit / total_selling * 100) if total_selling else 0.0

    story.append(_summary_table([
        ("ጠቅላላ ሽያጥ / Total Sales", _money(total_selling)),
        ("ጠቅላላ ዋጋ ግዛእ / Total Cost", _money(total_cost)),
        ("ወጻኢታት / Expenses", _money(expenses)),
        ("ንጹህ ትርፊ / Net Profit", _money(net_profit)),
        ("%ንጹህ ትርፊ / Net Profit %", _pct(margin)),
    ]))
    story.append(Spacer(1, 8 * mm))

    story.append(P("ዝርዝር ፍርያት / Product Breakdown", size=12, bold=True))
    story.append(Spacer(1, 2 * mm))

    if items:
        rows = []
        tot_cartons = 0
        tot_cost = tot_sell = tot_profit = 0.0
        for item in items:
            selling = float(item.get('total_selling') or 0.0)
            cost = float(item.get('total_cost') or 0.0)
            profit = float(item.get('profit') or 0.0)
            cartons = item.get('carton_qty')
            if cartons is None:
                cartons = item.get('quantity', 0)
            tot_cartons += int(cartons or 0)
            tot_cost += cost
            tot_sell += selling
            tot_profit += profit
            rows.append([
                item.get('product_name', ''),
                _num(cartons),
                _money(cost),
                _money(selling),
                _money(profit),
                _pct((profit / selling * 100) if selling else 0.0),
            ])
        total_row = [
            "ጠቅላላ / TOTAL",
            _num(tot_cartons),
            _money(tot_cost),
            _money(tot_sell),
            _money(tot_profit),
            _pct((tot_profit / tot_sell * 100) if tot_sell else 0.0),
        ]
        story.append(_detail_table(
            ["ስም / Item Name", "ብዝሒ / Qty", "ዋጋ ግዛእ / Cost", "ሽያጥ / Sales", "ትርፊ / Profit", "% ትርፊ / Profit %"],
            rows,
            [62 * mm, 22 * mm, 40 * mm, 40 * mm, 40 * mm, 34 * mm],
            total_row=total_row,
        ))
    else:
        story.append(P("ኣብዚ መዓልቲ'ዚ ሽያጥ ኣይተመዝገበን / No sales recorded on this date.", size=10))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# 2. Monthly Profit PDF — day-by-day table
# ---------------------------------------------------------------------------
def generate_monthly_profit_pdf(
    period_label: str,
    start_date: date,
    end_date: date,
    daily_data: list,
) -> bytes:
    """Monthly report: day-by-day breakdown for a single Ethiopian month."""
    buffer = io.BytesIO()
    doc = _doc(buffer)
    story = []

    story.append(P("ወርሓዊ ጸብጻብ ትርፊ / Monthly Profit Report", size=16, bold=True, align='C'))
    story.append(P(period_label, size=11, align='C'))
    story.append(P(_range_label(start_date, end_date), size=9, align='C'))
    story.append(Spacer(1, 6 * mm))

    tot_qty = 0
    tot_sell = tot_cost = tot_gross = tot_exp = tot_net = 0.0
    for d in daily_data:
        tot_qty += int(d.get('total_quantity') or 0)
        tot_sell += float(d.get('total_selling') or 0.0)
        tot_cost += float(d.get('total_cost') or 0.0)
        tot_gross += float(d.get('gross_profit') or 0.0)
        tot_exp += float(d.get('expenses') or 0.0)
        tot_net += float(d.get('net_profit') or 0.0)

    margin = (tot_net / tot_sell * 100) if tot_sell else 0.0

    story.append(_summary_table([
        ("ጠቅላላ ሽያጥ / Total Sales", _money(tot_sell)),
        ("ጠቅላላ ዋጋ ግዛእ / Total Cost", _money(tot_cost)),
        ("ወጻኢታት / Expenses", _money(tot_exp)),
        ("ንጹህ ትርፊ / Net Profit", _money(tot_net)),
        ("%ንጹህ ትርፊ / Net Profit %", _pct(margin)),
    ]))
    story.append(Spacer(1, 8 * mm))

    story.append(P("ብመዓልቲ ዝርዝር / Day-by-Day Details", size=12, bold=True))
    story.append(Spacer(1, 2 * mm))

    if daily_data:
        rows = []
        for d in daily_data:
            rows.append([
                _eth_date_str(d['date']),
                _num(d.get('total_quantity')),
                _money(d.get('total_selling')),
                _money(d.get('total_cost')),
                _money(d.get('gross_profit')),
                _money(d.get('expenses')),
                _money(d.get('net_profit')),
                _pct(d.get('margin')),
            ])
        total_row = [
            "ጠቅላላ / TOTAL",
            _num(tot_qty),
            _money(tot_sell),
            _money(tot_cost),
            _money(tot_gross),
            _money(tot_exp),
            _money(tot_net),
            _pct(margin),
        ]
        story.append(_detail_table(
            ["ዕለት / Date", "ብዝሒ / Qty", "ሽያጥ / Selling", "ዋጋ ግዛእ / Cost",
             "ሓፈሻዊ / Gross", "ወጻኢ / Expenses", "ትርፊ / Net", "% ትርፊ / Profit %"],
            rows,
            [30 * mm, 18 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm, 28 * mm],
            total_row=total_row,
        ))
    else:
        story.append(P("ኣብዚ ወርሒ'ዚ ሓበሬታ ኣይተረኽበን / No data available for this period.", size=10))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# 3. Period Profit PDF — month-by-month table (3 / 6 / 12 months)
# ---------------------------------------------------------------------------
def generate_period_profit_pdf(
    period_label: str,
    start_date: date,
    end_date: date,
    monthly_data: list,
) -> bytes:
    """Quarterly / semi-annual / annual report: month-by-month breakdown."""
    buffer = io.BytesIO()
    doc = _doc(buffer)
    story = []

    story.append(P("ጸብጻብ ትርፊ / Profit Report", size=16, bold=True, align='C'))
    story.append(P(period_label, size=11, align='C'))
    story.append(P(_range_label(start_date, end_date), size=9, align='C'))
    story.append(Spacer(1, 6 * mm))

    tot_qty = 0
    tot_sell = tot_cost = tot_gross = tot_exp = tot_net = 0.0
    for m in monthly_data:
        tot_qty += int(m.get('quantity') or 0)
        tot_sell += float(m.get('selling') or 0.0)
        tot_cost += float(m.get('cost') or 0.0)
        tot_gross += float(m.get('gross') or 0.0)
        tot_exp += float(m.get('expenses') or 0.0)
        tot_net += float(m.get('net') or 0.0)

    margin = (tot_net / tot_sell * 100) if tot_sell else 0.0

    story.append(_summary_table([
        ("ጠቅላላ ሽያጥ / Total Sales", _money(tot_sell)),
        ("ጠቅላላ ዋጋ ግዛእ / Total Cost", _money(tot_cost)),
        ("ወጻኢታት / Expenses", _money(tot_exp)),
        ("ንጹህ ትርፊ / Net Profit", _money(tot_net)),
        ("%ንጹህ ትርፊ / Net Profit %", _pct(margin)),
    ]))
    story.append(Spacer(1, 8 * mm))

    story.append(P("ብወርሒ ዝርዝር / Month-by-Month Details", size=12, bold=True))
    story.append(Spacer(1, 2 * mm))

    if monthly_data:
        rows = []
        for m in monthly_data:
            change = m.get('change')
            rows.append([
                m.get('label', ''),
                _num(m.get('quantity')),
                _money(m.get('selling')),
                _money(m.get('cost')),
                _money(m.get('gross')),
                _money(m.get('expenses')),
                _money(m.get('net')),
                _pct(change) if change is not None else "-",
                _pct(m.get('margin')),
            ])
        total_row = [
            "ጠቅላላ / TOTAL",
            _num(tot_qty),
            _money(tot_sell),
            _money(tot_cost),
            _money(tot_gross),
            _money(tot_exp),
            _money(tot_net),
            "-",
            _pct(margin),
        ]
        story.append(_detail_table(
            ["ወርሒ / Month", "ብዝሒ / Qty", "ሽያጥ / Selling", "ዋጋ ግዛእ / Cost", "ሓፈሻዊ / Gross",
             "ወጻኢ / Expenses", "ትርፊ / Net", "ለውጢ / Change %", "% ትርፊ / Profit %"],
            rows,
            [24 * mm, 17 * mm, 32 * mm, 32 * mm, 32 * mm, 32 * mm, 32 * mm, 26 * mm, 26 * mm],
            total_row=total_row,
        ))
    else:
        story.append(P("ኣብዚ እዋን'ዚ ሓበሬታ ኣይተረኽበን / No data available for this period.", size=10))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Data builders
# ---------------------------------------------------------------------------
def _get_carton_quantity_for_period(sale_svc, start_date: date, end_date: date) -> int:
    """Total cartons (sum of item.quantity only, i.e. NOT quantity * dozen)."""
    from sqlalchemy import func

    from models.new_sale_item import ProfessionalSaleItem
    from models.new_sales import ProfessionalSale
    from services.base_service import get_session

    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    with get_session() as session:
        total = session.query(
            func.sum(ProfessionalSaleItem.quantity)
        ).join(
            ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
        ).filter(
            ProfessionalSale.created_at.between(start_dt, end_dt),
            ProfessionalSale.is_deleted == False,          # noqa: E712
            ProfessionalSaleItem.is_deleted == False,      # noqa: E712
        ).scalar()
        return int(total) if total else 0


def build_daily_profit_data(target_date: date) -> dict:
    """Summary + per-product rows for one day."""
    from services.expense_service import ExpenseService
    from services.new_sale_service import NewSaleService

    sale_svc = NewSaleService()
    expense_svc = ExpenseService()

    return {
        'total_selling': sale_svc.get_total_selling_price_for_period(target_date, target_date),
        'total_cost': sale_svc.get_total_cost_price_for_period(target_date, target_date),
        'expenses': expense_svc.get_total_expenses_for_period(target_date, target_date),
        'items': sale_svc.get_product_profit_breakdown(target_date, target_date),
    }


def build_monthly_profit_data(start_date: date, end_date: date) -> list:
    """Day-by-day rows covering [start_date, end_date]."""
    from services.expense_service import ExpenseService
    from services.new_sale_service import NewSaleService

    sale_svc = NewSaleService()
    expense_svc = ExpenseService()

    data = []
    current = start_date
    while current <= end_date:
        selling = sale_svc.get_total_selling_price_for_period(current, current)
        cost = sale_svc.get_total_cost_price_for_period(current, current)
        exp = expense_svc.get_total_expenses_for_period(current, current)
        gross = selling - cost
        net = gross - exp
        data.append({
            'date': current,
            'total_quantity': _get_carton_quantity_for_period(sale_svc, current, current),
            'total_selling': selling,
            'total_cost': cost,
            'gross_profit': gross,
            'expenses': exp,
            'net_profit': net,
            'margin': (net / selling * 100) if selling else 0.0,
        })
        current += timedelta(days=1)
    return data


def _ethiopian_months_between(start_date: date, end_date: date):
    """Yield (label, month_start, month_end, year, month) for Ethiopian months in range."""
    start_eth = EthiopianDateConverter.to_ethiopian(start_date)
    end_eth = EthiopianDateConverter.to_ethiopian(end_date)

    year, month = start_eth[0], start_eth[1]
    while (year < end_eth[0]) or (year == end_eth[0] and month <= end_eth[1]):
        month_start = EthiopianDateConverter.to_gregorian(year, month, 1)
        if month == 13:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1
        month_end = EthiopianDateConverter.to_gregorian(next_year, next_month, 1) - timedelta(days=1)
        yield (f"{month:02d}/{year:04d}", max(month_start, start_date),
               min(month_end, end_date), year, month)

        if month == 13:
            year, month = year + 1, 1
        else:
            month += 1
        if year > end_eth[0] or (year == end_eth[0] and month > end_eth[1]):
            break


def build_period_profit_data(start_date: date, end_date: date) -> list:
    """Month-by-month rows for the Ethiopian months inside [start_date, end_date]."""
    from services.expense_service import ExpenseService
    from services.new_sale_service import NewSaleService

    sale_svc = NewSaleService()
    expense_svc = ExpenseService()

    month_data = []
    for label, m_start, m_end, yr, mn in _ethiopian_months_between(start_date, end_date):
        selling = sale_svc.get_total_selling_price_for_period(m_start, m_end)
        cost = sale_svc.get_total_cost_price_for_period(m_start, m_end)
        exp = expense_svc.get_total_expenses_for_period(m_start, m_end)
        gross = selling - cost
        net = gross - exp
        month_data.append({
            'label': label,
            'start': m_start,
            'end': m_end,
            'quantity': _get_carton_quantity_for_period(sale_svc, m_start, m_end),
            'selling': selling,
            'cost': cost,
            'gross': gross,
            'expenses': exp,
            'net': net,
            'margin': (net / selling * 100) if selling else 0.0,
            'year': yr,
            'month': mn,
        })

    month_data.sort(key=lambda x: (x['year'], x['month']))

    for i, m in enumerate(month_data):
        if i == 0:
            m['change'] = None
        else:
            prev_net = month_data[i - 1]['net']
            if prev_net:
                m['change'] = (m['net'] - prev_net) / abs(prev_net) * 100
            else:
                m['change'] = 100.0 if m['net'] > 0 else (-100.0 if m['net'] < 0 else 0.0)

    return month_data