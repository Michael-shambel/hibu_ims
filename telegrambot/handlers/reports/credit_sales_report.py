import io
import logging
from datetime import date, datetime, time
from collections import defaultdict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS
from services.new_sale_service import NewSaleService
from models.payment_transaction import PaymentTransaction
from models.sale_payment_term import SalePaymentTerm, PaymentStatusEnum
from sqlalchemy.orm import joinedload
from services.base_service import get_session

logger = logging.getLogger(__name__)
sale_service = NewSaleService()

def generate_credit_sales_pdf(summary: dict, customers: list) -> bytes:
    """Generate PDF report for credit sales overview."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['Normal']
    
    table_style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])

    story = []

    # Title
    title_text = f"Credit Sales Report\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    # Summary section
    story.append(Paragraph("Overall Summary", heading_style))
    summary_data = [
        ["Total Credit Amount", f"ETB {summary['total_credit_amount']:,.2f}"],
        ["Total Paid", f"ETB {summary['total_paid']:,.2f}"],
        ["Total Unpaid", f"ETB {summary['total_unpaid']:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[80*mm, 80*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    # Customers table - sort by unpaid (remaining) descending
    story.append(Paragraph("Customer Credit Details (Sorted by Unpaid)", heading_style))
    if customers:
        # Sort customers by remaining amount (unpaid) in descending order
        sorted_customers = sorted(customers, key=lambda x: x['remaining'], reverse=True)
        table_data = [["Customer", "Total Credit", "Paid", "Unpaid", "Status", "Earliest Due Date"]]
        for c in sorted_customers:
            due_date_str = c['earliest_due_date'].isoformat() if c.get('earliest_due_date') else 'N/A'
            row = [
                c['customer_name'],
                f"{c['total_amount']:,.2f}",
                f"{c['paid_amount']:,.2f}",
                f"{c['remaining']:,.2f}",
                c['status'],
                due_date_str
            ]
            table_data.append(row)
        col_widths = [60*mm, 40*mm, 40*mm, 40*mm, 30*mm, 50*mm]
        details_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        details_table.setStyle(table_style)
        story.append(details_table)
    else:
        story.append(Paragraph("No credit sales found.", normal_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


async def credit_sales_report_handler(update, context):
    """Generate and send credit sales overview report."""
    from telegrambot.handlers.menu_handlers.sales_menu import sales_reports_menu

    await update.callback_query.answer()
    await update.callback_query.edit_message_text("⏳ Generating credit sales report...")

    try:
        summary = sale_service.get_credit_sales_summary()
        customers = sale_service.get_credit_sales_by_customer()

        pdf_bytes = generate_credit_sales_pdf(summary, customers)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"credit_sales_report_{date.today().isoformat()}.pdf",
            caption="📊 Credit Sales Overview"
        )

    except Exception as e:
        logger.exception("Failed to generate credit sales PDF")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Failed to generate report: {str(e)}"
        )

    return await sales_reports_menu(update, context)