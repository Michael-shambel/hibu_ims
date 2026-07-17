import io
import logging
from datetime import date
from collections import defaultdict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER

from services.new_product_service import NewProductService
from models.product_batch import ProductBatch
from services.base_service import get_session
from models.batch_transaction import BatchTransaction, TransactionType
from models.product_batch import ProductBatch
from models.new_product import ProfessionalProduct
from models.purchase import Purchase
from models.supplier import Supplier
from ui.components.ethiopian_date import EthiopianDateConverter
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)
product_service = NewProductService()

def generate_stock_valuation_pdf(products: list, total_valuation: float, total_capital: float) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['Normal']

    story = []

    title_text = f"Stock Valuation Report\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    story.append(Paragraph("Summary", heading_style))
    summary_data = [
        ["Total Stock Valuation (Selling Price)", f"ETB {total_valuation:,.2f}"],
        ["Total Capital (Cost Price)", f"ETB {total_capital:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[80*mm, 80*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTSIZE', (0,0), (-1,-1), 12),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    story.append(Paragraph("Product Stock Details", heading_style))
    if products:
        table_data = [["No.", "Product Name", "Available", "Selling Price", "Unit", "Dozen", "Total Stock"]]

        base_table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ])

        for i, p in enumerate(products, 1):
            available = p['available_stock']
            row_data = [
                str(i),
                p['name'],
                str(available),
                f"{p['price']:,.2f}",
                p['unit'],
                str(p['dozen']),
                str(p['total_quantity'])
            ]
            table_data.append(row_data)
            
            # Highlight low stock rows
            if available <= 2:
                # Row index in table (header is row 0)
                row_idx = i
                base_table_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#fadbd8'))
                base_table_style.add('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.red)
        
        col_widths = [15*mm, 60*mm, 25*mm, 30*mm, 25*mm, 20*mm, 25*mm]
        details_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        details_table.setStyle(base_table_style)
        story.append(details_table)
    else:
        story.append(Paragraph("No products found.", normal_style))
    
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


async def stock_valuation_report_handler(update, context):
    from telegrambot.handlers.menu_handlers.product_menu import product_reports_menu

    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Generating stock valuation report...")

    try:
        products_data = product_service.get_paginated(offset=0, limit=10000)
        total_valuation = 0.0
        total_capital = 0.0

        with get_session() as session:
            product_ids = [p['id'] for p in products_data]
            batches = session.query(ProductBatch).filter(
                ProductBatch.product_id.in_(product_ids),
                ProductBatch.is_deleted == False
            ).all()
            
            batches_by_product = defaultdict(list)
            for b in batches:
                batches_by_product[b.product_id].append(b)
            
            for p in products_data:
                product_batches = batches_by_product.get(p['id'], [])
                available = sum(b.available_quantity for b in product_batches)
                total_qty = sum(b.quantity for b in product_batches)
                # Update the product data with accurate stock counts from batches
                p['available_stock'] = available
                p['total_quantity'] = total_qty
                
                # Calculate valuations
                total_valuation += available * p['price'] * p['dozen']
                for b in product_batches:
                    total_capital += b.available_quantity * (b.cost_price or 0) * p['dozen']
        
        products_data.sort(key=lambda x: x['available_stock'], reverse=True)

        pdf_bytes = generate_stock_valuation_pdf(products_data, total_valuation, total_capital)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"stock_valuation_{date.today().isoformat()}.pdf",
            caption="📦 Stock Valuation Report"
        )
    
    except Exception as e:
        logger.exception("Failed to generate stock valuation PDF")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Failed to generate report: {str(e)}"
        )

    return await product_reports_menu(update, context)


async def low_stock_report_handler(update, context):
    """Generate and send low stock alert report."""
    from telegrambot.handlers.menu_handlers.product_menu import product_reports_menu

    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Generating low stock report...")

    try:
        # Fetch all products
        products_data = product_service.get_paginated(offset=0, limit=10000)
        
        low_stock_threshold = 10
        low_stock_products = []
        total_valuation_low = 0.0
        total_capital_low = 0.0
        
        with get_session() as session:
            product_ids = [p['id'] for p in products_data]
            batches = session.query(ProductBatch).filter(
                ProductBatch.product_id.in_(product_ids),
                ProductBatch.is_deleted == False
            ).all()
            
            batches_by_product = defaultdict(list)
            for b in batches:
                batches_by_product[b.product_id].append(b)
            
            for p in products_data:
                product_batches = batches_by_product.get(p['id'], [])
                available = sum(b.available_quantity for b in product_batches)
                total_qty = sum(b.quantity for b in product_batches)
                
                if available <= low_stock_threshold:
                    p['available_stock'] = available
                    p['total_quantity'] = total_qty
                    low_stock_products.append(p)
                    
                    # Calculate valuations for low stock items
                    total_valuation_low += available * p['price'] * p['dozen']
                    for b in product_batches:
                        total_capital_low += b.available_quantity * (b.cost_price or 0) * p['dozen']
        
        # Sort by available stock ascending (most critical first)
        low_stock_products.sort(key=lambda x: x['available_stock'])
        
        # Generate PDF
        pdf_bytes = generate_low_stock_pdf(low_stock_products, total_valuation_low, total_capital_low, low_stock_threshold)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"low_stock_alert_{date.today().isoformat()}.pdf",
            caption=f"⚠️ Low Stock Alert (≤{low_stock_threshold} units)"
        )

    except Exception as e:
        logger.exception("Failed to generate low stock PDF")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Failed to generate report: {str(e)}"
        )

    return await product_reports_menu(update, context)


def generate_low_stock_pdf(products: list, total_valuation: float, total_capital: float, threshold: int) -> bytes:
    """Generate PDF report for low stock items."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['Normal']
    
    story = []

    # Title
    title_text = f"Low Stock Alert Report (≤{threshold} units)\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    # Summary section
    story.append(Paragraph("Summary", heading_style))
    summary_data = [
        ["Total Low Stock Items", str(len(products))],
        ["Low Stock Valuation (Selling Price)", f"ETB {total_valuation:,.2f}"],
        ["Low Stock Capital (Cost Price)", f"ETB {total_capital:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[80*mm, 80*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTSIZE', (0,0), (-1,-1), 12),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    # Products table
    story.append(Paragraph("Low Stock Products", heading_style))
    if products:
        table_data = [["No.", "Product Name", "Available", "Selling Price", "Unit", "Dozen", "Total Stock"]]
        
        base_table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ])
        
        for i, p in enumerate(products, 1):
            available = p['available_stock']
            row_data = [
                str(i),
                p['name'],
                str(available),
                f"{p['price']:,.2f}",
                p['unit'],
                str(p['dozen']),
                str(p['total_quantity'])
            ]
            table_data.append(row_data)
            
            # Highlight all low stock rows (they all are)
            row_idx = i
            base_table_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#fadbd8'))
            base_table_style.add('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.red)
        
        col_widths = [15*mm, 60*mm, 25*mm, 30*mm, 25*mm, 20*mm, 25*mm]
        details_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        details_table.setStyle(base_table_style)
        story.append(details_table)
    else:
        story.append(Paragraph("No low stock items found.", normal_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


async def stock_in_history_report_handler(update, context):
    """Generate and send stock in history report grouped by Ethiopian date."""
    from telegrambot.handlers.menu_handlers.product_menu import product_reports_menu

    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Generating stock in history report...")

    try:
        with get_session() as session:
            # Fetch RECEIVED transactions linked to purchases
            transactions = session.query(BatchTransaction).options(
                joinedload(BatchTransaction.batch)
                .joinedload(ProductBatch.product),
                joinedload(BatchTransaction.batch)
                .joinedload(ProductBatch.purchase)
                .joinedload(Purchase.supplier)
            ).filter(
                BatchTransaction.transaction_type == TransactionType.RECEIVED,
                BatchTransaction.is_deleted == False,
                BatchTransaction.batch.has(ProductBatch.purchase_id.isnot(None))
            ).order_by(BatchTransaction.created_at.desc()).all()

            # Group by Ethiopian date
            date_groups = {}
            for tx in transactions:
                batch = tx.batch
                if not batch or not batch.purchase:
                    continue
                greg_date = tx.created_at.date() if tx.created_at else date.today()
                eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(greg_date)
                key = (eth_year, eth_month, eth_day)

                if key not in date_groups:
                    date_groups[key] = []
                date_groups[key].append(tx)

            # Sort dates descending
            sorted_dates = sorted(date_groups.keys(), key=lambda x: (x[0], x[1], x[2]), reverse=True)

            # Prepare data for PDF
            sections = []
            for eth_date in sorted_dates:
                txs = date_groups[eth_date]
                total_qty = sum(tx.quantity for tx in txs)
                distinct_products = set()
                rows = []
                for tx in txs:
                    batch = tx.batch
                    product = batch.product
                    purchase = batch.purchase
                    supplier = purchase.supplier if purchase else None
                    if product:
                        distinct_products.add(product.id)
                    rows.append({
                        'product_name': product.name if product else "N/A",
                        'quantity': tx.quantity,
                        'cost_price': batch.cost_price if batch else 0.0,
                        'supplier_name': supplier.supplier_name if supplier else "N/A",
                    })
                # Sort rows by product name
                rows.sort(key=lambda x: x['product_name'])
                sections.append({
                    'eth_date': eth_date,
                    'total_qty': total_qty,
                    'item_count': len(distinct_products),
                    'rows': rows
                })

        pdf_bytes = generate_stock_in_history_pdf(sections)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"stock_in_history_{date.today().isoformat()}.pdf",
            caption="📜 Stock In History Report"
        )

    except Exception as e:
        logger.exception("Failed to generate stock in history PDF")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Failed to generate report: {str(e)}"
        )

    return await product_reports_menu(update, context)


def generate_stock_in_history_pdf(sections: list) -> bytes:
    """Generate PDF with sections per Ethiopian date."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['Normal']

    # Custom style for centered date header
    date_header_style = ParagraphStyle(
        'DateHeader',
        parent=styles['Heading3'],
        alignment=TA_CENTER,
        spaceAfter=6,
        textColor=colors.HexColor('#2c3e50')
    )

    story = []

    # Main title
    title_text = f"Stock In History Report (Purchases Only)\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    if not sections:
        story.append(Paragraph("No stock in records found.", normal_style))
    else:
        for idx, section in enumerate(sections):
            year, month, day = section['eth_date']
            eth_date_str = f"{day:02d}/{month:02d}/{year:04d}"

            # Date header with summary
            header_text = f"<b>{eth_date_str}</b>  —  Total Qty: {section['total_qty']}  |  Items: {section['item_count']}"
            story.append(Paragraph(header_text, date_header_style))
            story.append(Spacer(1, 4*mm))

            # Table for this date
            table_data = [["Product Name", "Quantity", "Cost Price", "Supplier"]]
            for row in section['rows']:
                table_data.append([
                    row['product_name'],
                    str(row['quantity']),
                    f"{row['cost_price']:,.2f}",
                    row['supplier_name']
                ])

            # Set column widths
            col_widths = [80*mm, 25*mm, 30*mm, 60*mm]
            tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 9),
                ('BOTTOMPADDING', (0,0), (-1,0), 6),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (1,1), (1,-1), 'RIGHT'),  # quantity right-aligned
                ('ALIGN', (2,1), (2,-1), 'RIGHT'),  # cost price right-aligned
            ]))
            story.append(tbl)
            story.append(Spacer(1, 8*mm))

            # Add page break if not last section and table is long
            if idx < len(sections) - 1:
                story.append(PageBreak())

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes