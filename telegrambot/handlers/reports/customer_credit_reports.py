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

def generate_customer_credit_items_pdf(customer_name: str, groups: list) -> bytes:
    """
    Generate a PDF report for customer credit items.
    groups: list of dicts as returned by NewSaleService.get_customer_credit_sales_grouped()
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['Normal']
    
    story = []

    # Title
    title_text = f"Credit Item History\n{customer_name}\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    # For each date group
    for idx, group in enumerate(groups):
        # Group header with Ethiopian date
        if group['sale_date']:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(group['sale_date'])
            date_display = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        else:
            date_display = "Unknown Date"
        
        story.append(Paragraph(f"<b>Sale Date: {date_display}</b>", heading_style))
        story.append(Spacer(1, 5*mm))
        
        # Summary table for this group
        summary_data = [
            ["Total Amount", f"ETB {group['total_amount']:,.2f}"],
            ["Paid Amount", f"ETB {group['paid_amount']:,.2f}"],
            ["Remaining", f"ETB {group['remaining']:,.2f}"],
            ["Status", group['status']],
        ]
        summary_table = Table(summary_data, colWidths=[50*mm, 60*mm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 8*mm))
        
        # Items table
        if group['items']:
            story.append(Paragraph("Items:", heading_style))
            table_data = [["Product", "Qty", "Dozen", "Unit Price", "Total", "Despatched"]]
            for item in group['items']:
                table_data.append([
                    item['product_name'],
                    str(item['quantity']),
                    str(item['dozen']),
                    f"{item['unit_price']:,.2f}",
                    f"{item['total']:,.2f}",
                    "Yes" if item['for_despatch'] else "No"
                ])
            # Add total row (sum of totals)
            total_sum = sum(i['total'] for i in group['items'])
            table_data.append(["TOTAL", "", "", "", f"{total_sum:,.2f}", ""])
            
            col_widths = [65*mm, 20*mm, 20*mm, 25*mm, 30*mm, 20*mm]
            tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,0), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 9),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (1,1), (1,-1), 'RIGHT'),
                ('ALIGN', (2,1), (2,-1), 'RIGHT'),
                ('ALIGN', (3,1), (3,-1), 'RIGHT'),
                ('ALIGN', (4,1), (4,-1), 'RIGHT'),
                ('ALIGN', (5,1), (5,-1), 'CENTER'),
                ('FONTSIZE', (0,1), (-1,-1), 8),
                ('BACKGROUND', (0,-1), (-1,-1), colors.beige),
                ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ]))
            story.append(tbl)
        else:
            story.append(Paragraph("No items found for this sale.", normal_style))
        
        story.append(Spacer(1, 15*mm))  # space between groups
    
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