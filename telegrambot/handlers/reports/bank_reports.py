# telegrambot/handlers/reports/bank_reports.py
import io
import logging
from datetime import date, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from services.bank_account_service import BankAccountService
from services.bank_transaction_service import BankTransactionService
from models.bank_transactions import TransactionDirectionEnum
from ui.components.ethiopian_date import EthiopianDateConverter

logger = logging.getLogger(__name__)

bank_account_service = BankAccountService()
bank_transaction_service = BankTransactionService()

def generate_total_balance_pdf() -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']

    story = []
    story.append(Paragraph("Total Bank Balance Report", title_style))
    story.append(Spacer(1, 10*mm))

    accounts = [a for a in bank_account_service.get_all() if a.is_active]
    total_balance = 0.0

    account_data = [["Account Name", "Bank", "Balance"]]
    for acc in accounts:
        bal = bank_transaction_service.get_balance(acc.id)
        total_balance += bal
        account_data.append([acc.account_name, acc.bank_name, f"ETB {bal:,.2f}"])
    account_data.append(["TOTAL", "", f"ETB {total_balance:,.2f}"])

    acct_table = Table(account_data, colWidths=[60*mm, 60*mm, 40*mm])
    acct_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (2,1), (2,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
    ]))
    story.append(acct_table)
    story.append(Spacer(1, 10*mm))

    start_date = date.today() - timedelta(days=30)
    all_tx = []
    for acc in accounts:
        txs = bank_transaction_service.get_transactions(
            account_id=acc.id,
            start_date=start_date
        )
        for tx in txs:
            all_tx.append({
                'account_name': f"{acc.account_name} ({acc.bank_name})",
                'date': tx.transaction_date,
                'description': tx.description or '',
                'credit': tx.amount if tx.direction == TransactionDirectionEnum.CREDIT else 0.0,
                'debit': tx.amount if tx.direction == TransactionDirectionEnum.DEBIT else 0.0,
                'balance_after': tx.balance_after
            })

    all_tx.sort(key=lambda x: x['date'], reverse=True)

    story.append(Paragraph("Recent Transactions (last 30 days)", heading_style))
    if all_tx:
        table_data = [["Date", "Account", "Description", "Credit", "Debit", "Balance After"]]
        for tx in all_tx:
            eth_date = EthiopianDateConverter.to_ethiopian(tx['date'])
            date_str = f"{eth_date[2]:02d}/{eth_date[1]:02d}/{eth_date[0]}"
            table_data.append([
                date_str,
                tx['account_name'],
                tx['description'][:40],
                f"{tx['credit']:,.2f}" if tx['credit'] > 0 else "",
                f"{tx['debit']:,.2f}" if tx['debit'] > 0 else "",
                f"{tx['balance_after']:,.2f}"
            ])

        col_widths = [25*mm, 50*mm, 65*mm, 25*mm, 25*mm, 30*mm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (3,1), (5,-1), 'RIGHT'),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No recent transactions.", styles['Normal']))

    doc.build(story)
    return buffer.getvalue()


def generate_bank_account_pdf(account) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']

    story = []
    story.append(Paragraph(f"Bank Account Report", title_style))
    story.append(Paragraph(f"{account.account_name} ({account.bank_name})", styles['Heading3']))
    story.append(Spacer(1, 5*mm))

    transactions = bank_transaction_service.get_transactions(account_id=account.id)
    total_credit = sum(tx.amount for tx in transactions if tx.direction == TransactionDirectionEnum.CREDIT)
    total_debit  = sum(tx.amount for tx in transactions if tx.direction == TransactionDirectionEnum.DEBIT)
    current_balance = bank_transaction_service.get_balance(account.id)

    summary_data = [
        ["Total Credit", f"ETB {total_credit:,.2f}"],
        ["Total Debit", f"ETB {total_debit:,.2f}"],
        ["Current Balance", f"ETB {current_balance:,.2f}"]
    ]
    summary_table = Table(summary_data, colWidths=[50*mm, 50*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 12),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    story.append(Paragraph("Transaction History", heading_style))
    if transactions:
        display_txs = list(reversed(transactions))
        table_data = [["Date", "Description", "Credit", "Debit", "Balance After"]]
        for tx in display_txs:
            eth_date = EthiopianDateConverter.to_ethiopian(tx.transaction_date)
            date_str = f"{eth_date[2]:02d}/{eth_date[1]:02d}/{eth_date[0]}"
            credit = f"{tx.amount:,.2f}" if tx.direction == TransactionDirectionEnum.CREDIT else ""
            debit  = f"{tx.amount:,.2f}" if tx.direction == TransactionDirectionEnum.DEBIT else ""
            table_data.append([
                date_str,
                tx.description or "",
                credit,
                debit,
                f"{tx.balance_after:,.2f}"
            ])

        col_widths = [25*mm, 80*mm, 30*mm, 30*mm, 30*mm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (2,1), (4,-1), 'RIGHT'),
        ]))
        for i, tx in enumerate(display_txs, start=1):
            if tx.direction == TransactionDirectionEnum.CREDIT:
                tbl.setStyle(TableStyle([('TEXTCOLOR', (2,i), (2,i), colors.green)]))
            else:
                tbl.setStyle(TableStyle([('TEXTCOLOR', (3,i), (3,i), colors.red)]))
        story.append(tbl)
    else:
        story.append(Paragraph("No transactions.", styles['Normal']))

    doc.build(story)
    return buffer.getvalue()