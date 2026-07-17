# telegrambot/handlers/reports/sales_report.py
import io
import logging
from datetime import date
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
from models.new_sale_item import ProfessionalSaleItem
from models.product_batch import ProductBatch
from models.new_product import ProfessionalProduct
from sqlalchemy.orm import joinedload
from services.base_service import get_session

logger = logging.getLogger(__name__)
sale_service = NewSaleService()


def generate_sales_pdf(summary: dict, eth_year: int, eth_month: int, eth_day: int, greg_date: date) -> bytes:
    """Generate PDF report with item-level breakdown."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=12*mm, bottomMargin=12*mm)

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontSize = 16
    heading_style = styles['Heading2']
    heading_style.fontSize = 12
    normal_style = styles['Normal']
    normal_style.fontSize = 9

    story = []

    eth_month_name = ETHIOPIAN_MONTHS[eth_month - 1][0]
    title_text = (
        f"Daily Sales Report<br/>"
        f"{eth_month_name} {eth_day}, {eth_year} "
        f"(Gregorian: {greg_date.isoformat()})"
    )
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph("Summary", heading_style))
    summary_data = [
        ["Total Sales Amount", f"ETB {summary['total_sales_amount']:,.2f}"],
        ["Total Labour Expense", f"ETB {summary['total_labour_expense']:,.2f}"],
        ["Cash Total", f"ETB {summary['cash_total']:,.2f}"],
        ["Bank Total", f"ETB {summary['bank_total']:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[80*mm, 80*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph("Item Details", heading_style))
    item_details = summary.get('item_details', [])

    if item_details:
        table_data = [["Customer", "Item Name", "Qty", "Dozen",
                       "Unit Price", "Total Price", "Payment Type", "Delivery"]]
        for item in item_details:
            table_data.append([
                item['customer_name'],
                item['item_name'],
                str(item['quantity']),
                str(item['dozen']),
                f"{item['unit_price']:,.2f}",
                f"{item['total_price']:,.2f}",
                item['payment_type'],
                item['delivery_name'],
            ])

        col_widths = [38*mm, 52*mm, 14*mm, 14*mm, 22*mm, 26*mm, 62*mm, 42*mm]
        details_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        details_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (2, 1), (3, -1), 'RIGHT'),
            ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))
        story.append(details_table)
    else:
        story.append(Paragraph("No sales recorded on this date.", normal_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def _build_sales_summary(sales, greg_date, session, sale_service) -> dict:
    """
    Pure synchronous helper — builds the summary dict from already-fetched sales.
    Called inside asyncio.to_thread so it never blocks the event loop.
    """
    from collections import defaultdict

    sale_ids = [s.id for s in sales]

    terms = session.query(SalePaymentTerm).options(
        joinedload(SalePaymentTerm.payment_transactions)
        .joinedload(PaymentTransaction.bank_account)
    ).filter(SalePaymentTerm.sale_id.in_(sale_ids)).all()
    terms_by_sale = defaultdict(list)
    for term in terms:
        terms_by_sale[term.sale_id].append(term)

    items = session.query(ProfessionalSaleItem).options(
        joinedload(ProfessionalSaleItem.batch)
        .joinedload(ProductBatch.product)
    ).filter(
        ProfessionalSaleItem.sale_id.in_(sale_ids),
        ProfessionalSaleItem.is_deleted == False
    ).all()
    items_by_sale = defaultdict(list)
    for item in items:
        items_by_sale[item.sale_id].append(item)

    cash_account_id = sale_service.cash_account_id
    total_sales_amount = 0.0
    total_labour_expense = 0.0
    payment_totals = {}
    item_details = []

    for sale in sales:
        total_sales_amount += sale.total_amount
        total_labour_expense += sale.labour_expense

        payment_type_str = ""
        sale_terms = terms_by_sale.get(sale.id, [])
        if sale_terms:
            payment_types_set = set()
            for term in sale_terms:
                for payment in term.payment_transactions:
                    if payment.payment_date != greg_date:
                        continue
                    account_id = payment.bank_account_id
                    payment_totals[account_id] = payment_totals.get(account_id, 0.0) + payment.amount
                    if payment.bank_account:
                        ptype = "Cash" if account_id == cash_account_id else (
                            f"{payment.bank_account.account_name} - {payment.bank_account.bank_name}"
                        )
                    else:
                        ptype = "Transfer"
                    payment_types_set.add(ptype)

            if payment_types_set:
                payment_type_str = ", ".join(sorted(payment_types_set))
            else:
                for term in sale_terms:
                    if term.payment_status == PaymentStatusEnum.CREDIT:
                        payment_type_str = "Credit (Unpaid)"
                        break
                    elif term.payment_status == PaymentStatusEnum.PARTIAL:
                        payment_type_str = f"Credit (Partial – Paid {term.paid_amount:,.2f})"
                        break
                if not payment_type_str:
                    payment_type_str = "Paid (off-date)"
        else:
            payment_type_str = "Unknown"

        sale_items = items_by_sale.get(sale.id, [])
        aggregated = {}
        for item in sale_items:
            name = item.batch.product.name if (item.batch and item.batch.product) else "Unknown"
            key = (name, item.unit_price, item.dozen)
            if key not in aggregated:
                aggregated[key] = {
                    'name': name,
                    'quantity': 0,
                    'dozen': item.dozen,
                    'unit_price': item.unit_price,
                    'total_price': 0.0,
                }
            aggregated[key]['quantity'] += item.quantity
            aggregated[key]['total_price'] += item.total

        for agg in aggregated.values():
            item_details.append({
                'customer_name': sale.customer.name if sale.customer else "N/A",
                'item_name': agg['name'],
                'quantity': agg['quantity'],
                'dozen': agg['dozen'],
                'unit_price': agg['unit_price'],
                'total_price': agg['total_price'],
                'payment_type': payment_type_str,
                'delivery_name': sale.delivery_name or "",
            })

    cash_total = payment_totals.get(cash_account_id, 0.0) if cash_account_id else 0.0
    bank_total = sum(amt for acc, amt in payment_totals.items() if acc != cash_account_id)

    return {
        'total_sales_amount': total_sales_amount,
        'total_labour_expense': total_labour_expense,
        'cash_total': cash_total,
        'bank_total': bank_total,
        'item_details': item_details,
    }


async def sales_transaction_report_handler(
    update, context,
    eth_year: int, eth_month: int, eth_day: int, greg_date: date
):
    """Generate item-level PDF report — all blocking work off the event loop."""
    import asyncio
    from telegrambot.handlers.menu_handlers.sales_menu import sales_reports_menu

    await update.message.reply_text(
        f"⏳ Generating report for {ETHIOPIAN_MONTHS[eth_month - 1][0]} {eth_day}, {eth_year} "
        f"(Gregorian: {greg_date.isoformat()})..."
    )

    try:
        def _fetch_and_build():
            """All DB work in one thread call — avoids multiple to_thread round-trips."""
            sales, _ = sale_service.get_all_sales_paginated(
                page=1, page_size=10000, filter_date=greg_date
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
                return _build_sales_summary(sales, greg_date, session, sale_service)

        # Single thread call covers all DB work + summary building
        summary = await asyncio.to_thread(_fetch_and_build)

        # PDF generation also off the event loop
        pdf_bytes = await asyncio.to_thread(
            generate_sales_pdf, summary, eth_year, eth_month, eth_day, greg_date
        )

        caption = f"📊 Sales Report for {ETHIOPIAN_MONTHS[eth_month - 1][0]} {eth_day}, {eth_year}"
        if summary['total_sales_amount'] == 0:
            caption += " (No sales)"

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"sales_report_{eth_year}_{eth_month:02d}_{eth_day:02d}.pdf",
            caption=caption
        )

    except Exception as e:
        logger.exception("Failed to generate sales PDF")
        await update.message.reply_text(f"❌ Failed to generate report: {str(e)}")

    return await sales_reports_menu(update, context)