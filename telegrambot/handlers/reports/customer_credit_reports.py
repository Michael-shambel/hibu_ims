# telegrambot/handlers/reports/customer_credit_reports.py

import io
import logging
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from ui.components.ethiopian_date import EthiopianDateConverter

logger = logging.getLogger(__name__)

# Amharic labels for the credit-items PDF
STATUS_AMHARIC = {
    'Paid': 'ተከፍሏል',
    'Partial': 'በከፊል ተከፍሏል',
    'Unpaid': 'ያልተከፈለ',
}


def _amharic_name(name: str) -> str:
    """Product name in Amharic, keeping the original in brackets.

    Uses the same transliteration service as the store-team Telegram text
    (user corrections -> seed dictionary -> rules), so names corrected in
    Reports -> Amharic Names appear here too.
    """
    raw = (name or '').strip()
    if not raw:
        return ''
    try:
        from services.amharic_service import to_amharic
        converted = to_amharic(raw)
    except Exception:
        logger.warning("Amharic conversion failed for %r", raw, exc_info=True)
        return raw
    if not converted or converted == raw:
        return raw
    return f"{converted} ({raw})"


def _fmt_qty(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:,.2f}"


def generate_customer_credit_items_pdf(customer_name: str, groups: list) -> bytes:
    """
    Generate the customer credit-items PDF, in Amharic.

    groups: list of dicts as returned by NewSaleService.get_customer_credit_sales_grouped()

    All titles, headings and table headers are Amharic (with the English term
    beside them) and product names go through the same Amharic transliteration
    used by the store-team notification text.
    """
    # P() renders mixed Amharic/Latin text with the Noto Sans Ethiopic font
    from telegrambot.handlers.reports.profit_report import P

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    story = []

    # Title
    story.append(P("የዱቤ እቃዎች ታሪክ (Credit Item History)", size=15, bold=True, align='C'))
    story.append(Spacer(1, 2*mm))
    story.append(P(customer_name, size=12, bold=True, align='C'))
    story.append(P(f"የተዘጋጀበት ቀን / Generated: {date.today().isoformat()}", size=8, align='C'))
    story.append(Spacer(1, 8*mm))

    # For each date group
    for idx, group in enumerate(groups):
        # Group header with Ethiopian date
        if group['sale_date']:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(group['sale_date'])
            date_display = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        else:
            date_display = "ቀን አልተገኘም / Unknown Date"

        story.append(P(f"የሽያጭ ቀን / Sale Date: {date_display}", size=11, bold=True))
        story.append(Spacer(1, 4*mm))

        # Summary table for this group
        status_am = STATUS_AMHARIC.get(group['status'], group['status'])
        summary_data = [
            [P("ጠቅላላ ዋጋ / Total Amount", size=9),
             P(f"ETB {group['total_amount']:,.2f}", size=9, align='R')],
            [P("የተከፈለ / Paid Amount", size=9),
             P(f"ETB {group['paid_amount']:,.2f}", size=9, align='R')],
            [P("ቀሪ / Remaining", size=9),
             P(f"ETB {group['remaining']:,.2f}", size=9, align='R')],
            [P("ሁኔታ / Status", size=9),
             P(status_am, size=9, align='R')],
        ]
        summary_table = Table(summary_data, colWidths=[95*mm, 55*mm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 7*mm))

        # Items table
        if group['items']:
            story.append(P("እቃዎች / Items", size=11, bold=True))
            story.append(Spacer(1, 2*mm))

            table_data = [[
                P("ምርት / Product", size=8, bold=True, align='C', color=colors.whitesmoke),
                P("ብዛት / Qty", size=8, bold=True, align='C', color=colors.whitesmoke),
                P("ደርዘን / Dozen", size=8, bold=True, align='C', color=colors.whitesmoke),
                P("የአንድ ዋጋ / Unit Price", size=8, bold=True, align='C', color=colors.whitesmoke),
                P("ጠቅላላ / Total", size=8, bold=True, align='C', color=colors.whitesmoke),
                P("የተላከ / Despatched", size=8, bold=True, align='C', color=colors.whitesmoke),
            ]]
            for item in group['items']:
                table_data.append([
                    P(_amharic_name(item['product_name']), size=8),
                    P(_fmt_qty(item['quantity']), size=8, align='R'),
                    P(_fmt_qty(item['dozen']), size=8, align='R'),
                    P(f"{item['unit_price']:,.2f}", size=8, align='R'),
                    P(f"{item['total']:,.2f}", size=8, align='R'),
                    P("አዎ" if item['for_despatch'] else "አይ", size=8, align='C'),
                ])
            # Add total row (sum of totals)
            total_sum = sum(i['total'] for i in group['items'])
            table_data.append([
                P("ጠቅላላ / TOTAL", size=8, bold=True),
                P("", size=8), P("", size=8), P("", size=8),
                P(f"{total_sum:,.2f}", size=8, bold=True, align='R'),
                P("", size=8),
            ])

            col_widths = [62*mm, 17*mm, 17*mm, 30*mm, 30*mm, 24*mm]
            tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BACKGROUND', (0,-1), (-1,-1), colors.beige),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ]))
            story.append(tbl)
        else:
            story.append(P("በዚህ ሽያጭ ላይ እቃ አልተገኘም። / No items found for this sale.", size=9))

        story.append(Spacer(1, 12*mm))  # space between groups

    doc.build(story)
    return buffer.getvalue()

def generate_customer_payment_history_pdf(customer_name: str, transactions: list,
                                           total_credit: float = 0.0, total_debit: float = 0.0,
                                           current_balance: float = 0.0) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']

    story = []

    # Title
    title_text = f"Credit Payment History<br/>{customer_name}<br/>Generated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    if not transactions:
        story.append(Paragraph("No transaction history found.", styles['Normal']))
        doc.build(story)
        return buffer.getvalue()

    # Reversal: show newest first
    display_transactions = list(reversed(transactions))

    # Summary section
    summary_data = [
        ["Total Credit (Sales)", f"ETB {total_credit:,.2f}"],
        ["Total Debit (Payments)", f"ETB {total_debit:,.2f}"],
        ["Current Balance", f"ETB {current_balance:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[80*mm, 60*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    # Main transaction table
    story.append(Paragraph("<b>Transaction History</b>", heading_style))
    story.append(Spacer(1, 5*mm))

    table_data = [["Date", "Balance (Before)", "Credit", "Debit", "Bank Account", "Remaining", "Note"]]

    for tx in display_transactions:
        # Date in Ethiopian
        if tx['date']:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(tx['date'])
            date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        else:
            date_str = "Unknown Date"

        balance_before = f"{tx['balance_before']:,.2f}"

        if tx['type'] == 'credit_sale':
            credit = f"{tx['amount']:,.2f}"
            debit = ""
            bank_display = "New Credit"
        else:
            credit = ""
            debit = f"{-tx['amount']:,.2f}"  # amount is negative for payments
            bank_display = tx.get('bank_account_display', 'N/A')

        remaining = f"{tx['balance_after']:,.2f}"
        note = tx.get('notes', '')[:60]  # truncate for PDF

        table_data.append([date_str, balance_before, credit, debit, bank_display, remaining, note])

    # Create table
    col_widths = [30*mm, 30*mm, 25*mm, 25*mm, 45*mm, 30*mm, 55*mm]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,1), (1,-1), 'RIGHT'),   # Balance
        ('ALIGN', (2,1), (2,-1), 'RIGHT'),   # Credit
        ('ALIGN', (3,1), (3,-1), 'RIGHT'),   # Debit
        ('ALIGN', (4,1), (4,-1), 'LEFT'),    # Bank Account
        ('ALIGN', (5,1), (5,-1), 'RIGHT'),   # Remaining
        ('FONTSIZE', (0,1), (-1,-1), 7),
    ]))

    # Apply row colors for credit vs payment (using reversed list indexes)
    for i, tx in enumerate(display_transactions, start=1):
        if tx['type'] == 'credit_sale':
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (2, i), (2, i), colors.HexColor('#e8f5e9')),
            ]))
        else:
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (3, i), (3, i), colors.HexColor('#ffebee')),
            ]))

    story.append(tbl)

    doc.build(story)
    return buffer.getvalue()