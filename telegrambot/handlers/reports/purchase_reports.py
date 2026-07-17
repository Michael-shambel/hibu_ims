# telegrambot/handlers/reports/purchase_reports.py
import io
import logging
from datetime import date
from collections import defaultdict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from services.purchase_service import PurchaseService
from services.supplier_service import SupplierService
from services.base_service import get_session
from models.purchase import Purchase
from models.product_batch import ProductBatch
from models.new_product import ProfessionalProduct
from ui.components.ethiopian_date import EthiopianDateConverter
from telegrambot.handlers.menu_handlers.states import (
    SELECT_SUPPLIER_FOR_CREDIT_PURCHASE, SELECT_DATE_GROUP_FOR_CREDIT_PURCHASE,
    CREDIT_REPORTS_MENU, CallbackData, ButtonText, ROLE_ADMIN
)
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard, start
from telegrambot.handlers.menu_handlers.credit_menu import credit_reports_menu
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)
purchase_service = PurchaseService()
supplier_service = SupplierService()


async def purchase_item_history_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of suppliers with credit purchases."""
    query = update.callback_query
    await query.answer()

    # Fetch suppliers with credit purchases
    suppliers = purchase_service.get_credit_purchases_by_supplier()
    
    if not suppliers:
        await query.edit_message_text("No credit purchases found.")
        return await credit_reports_menu(update, context)

    # Build inline keyboard of suppliers
    keyboard = []
    for supp in suppliers:
        button_text = f"{supp['supplier_name']} (Unpaid: ETB {supp['remaining']:,.2f})"
        callback_data = f"{CallbackData.SELECT_SUPPLIER_PREFIX}{supp['supplier_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Credit Menu", callback_data=CallbackData.BACK_TO_ADMIN)])
    keyboard.append([InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)])

    await query.edit_message_text(
        "📋 *Select a Supplier*\nChoose a supplier to view credit purchase history:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SUPPLIER_FOR_CREDIT_PURCHASE


async def supplier_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle supplier selection for both item history and payment history."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    elif data == CallbackData.BACK_TO_ADMIN:
        return await credit_reports_menu(update, context)
    elif data == CallbackData.BACK_TO_SUPPLIER_SELECTION:
        # Determine which entry point to return to
        if context.user_data.get('payment_history_mode'):
            return await purchase_payment_history_entry(update, context)
        else:
            return await purchase_item_history_entry(update, context)

    if data.startswith(CallbackData.SELECT_SUPPLIER_PREFIX):
        supplier_id = int(data.replace(CallbackData.SELECT_SUPPLIER_PREFIX, ""))
        context.user_data['selected_supplier_id'] = supplier_id
        
        # Get supplier name
        supplier = supplier_service.get_by_id(supplier_id)
        supplier_name = supplier.supplier_name if supplier else "Unknown"
        context.user_data['selected_supplier_name'] = supplier_name

        # Check mode
        is_payment_history_mode = context.user_data.get('payment_history_mode', False)
        
        if is_payment_history_mode:
            # ----- PAYMENT HISTORY FLOW -----
            await query.edit_message_text("⏳ Generating payment history report...")
            
            transactions = purchase_service.get_supplier_combined_history(supplier_id)
            
            if not transactions:
                await query.edit_message_text("No payment history found for this supplier.")
                context.user_data.pop('payment_history_mode', None)
                return await purchase_payment_history_entry(update, context)
            
            total_credit = sum(tx['credit_amount'] for tx in transactions)
            total_debit = sum(tx['debit_amount'] for tx in transactions)
            current_balance = transactions[-1]['balance_after'] if transactions else 0.0
            
            pdf_bytes = generate_payment_history_pdf(
                supplier_name=supplier_name,
                transactions=transactions,
                total_credit=total_credit,
                total_debit=total_debit,
                current_balance=current_balance
            )
            
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=io.BytesIO(pdf_bytes),
                filename=f"payment_history_{supplier_name}.pdf",
                caption=f"💰 Payment History - {supplier_name}"
            )
            
            # CLEAR the flag after generating payment history
            context.user_data.pop('payment_history_mode', None)
            return await purchase_payment_history_entry(update, context)
        
        else:
            # ----- ITEM HISTORY FLOW -----
            await query.edit_message_text("📄 Generating credit item history report... Please wait.")
            
            groups = purchase_service.get_supplier_credit_purchases_grouped(supplier_id)
            if not groups:
                await query.edit_message_text("📭 This supplier has no credit purchases.")
                # Return to supplier selection
                return await purchase_item_history_entry(update, context)
            
            pdf_bytes = generate_supplier_credit_items_pdf(supplier_name, groups)
            
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=io.BytesIO(pdf_bytes),
                filename=f"supplier_credit_items_{supplier_name}.pdf",
                caption=f"📦 Credit Item History - {supplier_name}"
            )
            
            # Re-show supplier list
            await query.message.reply_text(
                "📋 Select another supplier or use the buttons below:",
                reply_markup=get_main_keyboard(ROLE_ADMIN)
            )
            return await purchase_item_history_entry(update, context)

    return SELECT_SUPPLIER_FOR_CREDIT_PURCHASE


async def date_group_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date group selection and generate PDF report."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    elif data == CallbackData.BACK_TO_ADMIN:
        return await credit_reports_menu(update, context)
    elif data == CallbackData.BACK_TO_SUPPLIER_SELECTION:  # ADD THIS BLOCK
        return await purchase_item_history_entry(update, context)

    if data.startswith(CallbackData.SELECT_DATE_GROUP_PREFIX):
        date_str = data.replace(CallbackData.SELECT_DATE_GROUP_PREFIX, "")
        selected_date = date.fromisoformat(date_str) if date_str != "None" else None
        
        date_groups = context.user_data.get('date_groups', {})
        group = date_groups.get(selected_date)
        if not group:
            await query.edit_message_text("No data found for this date.")
            return await purchase_item_history_entry(update, context)

        supplier_name = context.user_data.get('selected_supplier_name', 'Unknown')

        await query.edit_message_text("⏳ Generating purchase items report...")

        # Collect items from all purchases in this date group
        items = []
        for pur in group['purchases']:
            if pur.batches:
                for batch in pur.batches:
                    if batch.is_deleted:
                        continue
                    product_name = batch.product.name if batch.product else "Unknown"
                    quantity = batch.quantity          # the base quantity from DB
                    dozen = getattr(batch, 'dozen', 1) # ensure dozen exists
                    unit_price = batch.cost_price or 0.0
                    total = quantity * dozen * unit_price
                    items.append({
                        'product_name': product_name,
                        'quantity': quantity,
                        'dozen': dozen,
                        'unit_price': unit_price,
                        'total': total
                    })
            elif pur.items_data:
                for raw in pur.items_data:
                    product_name = raw.get('name') or raw.get('product_name', '')
                    quantity = raw.get('quantity', 0)
                    dozen = raw.get('dozen', 1)
                    unit_price = raw.get('cost_price', 0.0)
                    total = raw.get('total', quantity * dozen * unit_price)
                    items.append({
                        'product_name': product_name,
                        'quantity': quantity,
                        'dozen': dozen,
                        'unit_price': unit_price,
                        'total': total
                    })

        # Generate PDF
        pdf_bytes = generate_purchase_items_pdf(
            supplier_name=supplier_name,
            purchase_date=selected_date,
            total_amount=group['total_amount'],
            paid_amount=group['paid_amount'],
            remaining=group['remaining'],
            items=items
        )

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"purchase_items_{supplier_name}_{selected_date}.pdf",
            caption=f"📦 Purchase Items - {supplier_name}"
        )

        # Return to date selection for the same supplier
        supplier_id = context.user_data.get('selected_supplier_id')
        if supplier_id:
            # Simulate clicking the same supplier again
            query.data = f"{CallbackData.SELECT_SUPPLIER_PREFIX}{supplier_id}"
            return await supplier_selection_handler(update, context)
        
        return await purchase_item_history_entry(update, context)

    return SELECT_DATE_GROUP_FOR_CREDIT_PURCHASE


def generate_purchase_items_pdf(supplier_name: str, purchase_date, total_amount: float,
                                paid_amount: float, remaining: float, items: list) -> bytes:
    """Generate PDF with summary and items table (Quantity & Dozen separated)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']

    story = []

    # Title
    if purchase_date:
        eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(purchase_date)
        date_display = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
    else:
        date_display = "Unknown Date"
    title_text = f"Purchase Items Report\n{supplier_name}\n{date_display}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    # Summary
    story.append(Paragraph("Summary", heading_style))
    summary_data = [
        ["Total Amount", f"ETB {total_amount:,.2f}"],
        ["Paid Amount", f"ETB {paid_amount:,.2f}"],
        ["Remaining", f"ETB {remaining:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[60*mm, 60*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    # Items table with separate Quantity and Dozen
    story.append(Paragraph("Items", heading_style))
    if items:
        table_data = [["Product", "Quantity", "Dozen", "Unit Price", "Total"]]
        total_quantity = 0
        total_dozen = 0
        grand_total = 0.0
        for item in items:
            qty = item.get('quantity', 0)
            doz = item.get('dozen', 1)
            uprice = item.get('unit_price', 0.0)
            total = item.get('total', qty * doz * uprice)
            table_data.append([
                item['product_name'],
                str(int(qty)) if isinstance(qty, float) and qty.is_integer() else str(qty),
                str(int(doz)) if isinstance(doz, float) and doz.is_integer() else str(doz),
                f"{uprice:,.2f}",
                f"{total:,.2f}"
            ])
            total_quantity += qty
            total_dozen += doz
            grand_total += total
        
        table_data.append(["TOTAL", str(total_quantity), str(total_dozen), "", f"{grand_total:,.2f}"])

        col_widths = [55*mm, 25*mm, 20*mm, 30*mm, 30*mm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('ALIGN', (1,1), (2,-1), 'RIGHT'),   # Quantity, Dozen
            ('ALIGN', (3,1), (4,-1), 'RIGHT'),   # Unit Price, Total
            ('BACKGROUND', (0,-1), (-1,-1), colors.beige),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No items found.", styles['Normal']))

    doc.build(story)
    return buffer.getvalue()


async def purchase_payment_history_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of suppliers with credit purchases for payment history."""
    query = update.callback_query
    await query.answer()

    # Clear any previous state data
    context.user_data.pop('selected_supplier_id', None)
    context.user_data.pop('selected_supplier_name', None)
    context.user_data.pop('payment_history_mode', None)
    context.user_data['payment_history_mode'] = True  # Flag to differentiate flow

    # Fetch suppliers with credit purchases
    suppliers = purchase_service.get_credit_purchases_by_supplier()
    
    if not suppliers:
        await query.edit_message_text("No credit purchases found.")
        return await credit_reports_menu(update, context)

    # Build inline keyboard of suppliers
    keyboard = []
    for supp in suppliers:
        button_text = f"{supp['supplier_name']} (Unpaid: ETB {supp['remaining']:,.2f})"
        callback_data = f"{CallbackData.SELECT_SUPPLIER_PREFIX}{supp['supplier_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Credit Menu", callback_data=CallbackData.BACK_TO_ADMIN)])
    keyboard.append([InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)])

    await query.edit_message_text(
        "📋 *Select a Supplier*\nChoose a supplier to view payment history:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SUPPLIER_FOR_CREDIT_PURCHASE


def generate_payment_history_pdf(supplier_name: str, transactions: list,
                                 total_credit: float, total_debit: float,
                                 current_balance: float) -> bytes:
    """Generate PDF with summary and payment history table (full note text, wrapped)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    
    # Custom style for wrapped notes
    note_style = ParagraphStyle(
        'NoteStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        wordWrap='CJK',
        alignment=TA_LEFT,
    )

    story = []

    # Title
    title_text = f"Purchase Payment History\n{supplier_name}\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    # Summary
    story.append(Paragraph("Summary", heading_style))
    summary_data = [
        ["Total Credit Purchases", f"ETB {total_credit:,.2f}"],
        ["Total Payments (Debit)", f"ETB {total_debit:,.2f}"],
        ["Current Balance Owed", f"ETB {current_balance:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[80*mm, 80*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 11),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    # Transactions table
    story.append(Paragraph("Transaction History", heading_style))
    if transactions:
        display_transactions = list(reversed(transactions))
        
        table_data = [["Date", "Balance\nBefore", "Credit", "Debit", "Bank Account", "Remaining", "Note"]]
        for tx in display_transactions:
            # Date
            if tx['date']:
                eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(tx['date'])
                date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
            else:
                date_str = ""
            
            # Format amounts
            balance_before = f"{tx['balance_before']:,.2f}"
            credit = f"{tx['credit_amount']:,.2f}" if tx['credit_amount'] > 0 else ""
            debit = f"{tx['debit_amount']:,.2f}" if tx['debit_amount'] > 0 else ""
            remaining = f"{tx['balance_after']:,.2f}"
            bank = tx['bank_account_display'] if tx['bank_account_display'] else "—"
            # Full note wrapped in a Paragraph
            note_paragraph = Paragraph(tx['notes'] if tx['notes'] else "", note_style)
            
            table_data.append([date_str, balance_before, credit, debit, bank, remaining, note_paragraph])
        
        col_widths = [25*mm, 25*mm, 25*mm, 25*mm, 50*mm, 25*mm, 75*mm]  # wider note column
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('VALIGN', (6,0), (6,-1), 'TOP'),       # note column top-aligned
            ('ALIGN', (1,1), (1,-1), 'RIGHT'),
            ('ALIGN', (2,1), (2,-1), 'RIGHT'),
            ('ALIGN', (3,1), (3,-1), 'RIGHT'),
            ('ALIGN', (5,1), (5,-1), 'RIGHT'),
            ('FONTSIZE', (0,1), (-1,-1), 8),
        ]))
        
        # Color code credits and debits
        for i, tx in enumerate(display_transactions, start=1):
            if tx['credit_amount'] > 0:
                tbl.setStyle(TableStyle([('TEXTCOLOR', (2,i), (2,i), colors.green)]))
            if tx['debit_amount'] > 0:
                tbl.setStyle(TableStyle([('TEXTCOLOR', (3,i), (3,i), colors.red)]))
        
        story.append(tbl)
    else:
        story.append(Paragraph("No transactions found.", styles['Normal']))

    doc.build(story)
    return buffer.getvalue()

def generate_supplier_credit_items_pdf(supplier_name: str, groups: list) -> bytes:
    """Generate PDF with grouped credit purchases and items for a supplier."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    story = []

    title_text = f"Credit Item History\n{supplier_name}\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    for group in groups:
        # Purchase date in Ethiopian calendar
        eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(group['purchase_date'])
        date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        story.append(Paragraph(f"<b>Purchase Date: {date_str}</b>", heading_style))
        story.append(Spacer(1, 5*mm))

        # Summary table
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

        # Items table – now with separate Quantity and Dozen columns
        if group['items']:
            story.append(Paragraph("Items:", heading_style))
            table_data = [["Product", "Quantity", "Dozen", "Unit Price", "Total"]]
            total_quantity = 0
            total_dozen = 0
            grand_total = 0.0
            for item in group['items']:
                qty = item.get('quantity', 0)
                doz = item.get('dozen', 1)
                uprice = item['unit_price']
                item_total = item['total']
                table_data.append([
                    item['product_name'],
                    str(int(qty)) if isinstance(qty, float) and qty.is_integer() else str(qty),
                    str(int(doz)) if isinstance(doz, float) and doz.is_integer() else str(doz),
                    f"{uprice:,.2f}",
                    f"{item_total:,.2f}"
                ])
                total_quantity += qty
                total_dozen += doz
                grand_total += item_total
            # Summary row
            table_data.append(["TOTAL", str(total_quantity), str(total_dozen), "", f"{grand_total:,.2f}"])

            col_widths = [55*mm, 25*mm, 20*mm, 30*mm, 30*mm]  # adjusted widths
            tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,0), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('ALIGN', (1,1), (2,-1), 'RIGHT'),   # Quantity, Dozen
                ('ALIGN', (3,1), (4,-1), 'RIGHT'),   # Unit Price, Total
                ('BACKGROUND', (0,-1), (-1,-1), colors.beige),
                ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ]))
            story.append(tbl)
        else:
            story.append(Paragraph("No items found.", styles['Normal']))
        story.append(Spacer(1, 15*mm))

    doc.build(story)
    return buffer.getvalue()

def generate_supplier_payment_history_pdf(supplier_name: str, transactions: list,
                                          total_credit: float, total_debit: float,
                                          current_balance: float) -> bytes:
    """Generate PDF with payment history for a supplier (full note text, wrapped)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    
    # Custom style for wrapped notes
    note_style = ParagraphStyle(
        'NoteStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        wordWrap='CJK',
        alignment=TA_LEFT,
    )

    story = []

    title_text = f"Payment History\n{supplier_name}\nGenerated: {date.today().isoformat()}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10*mm))

    # Summary
    summary_data = [
        ["Total Credit Purchases", f"ETB {total_credit:,.2f}"],
        ["Total Payments", f"ETB {total_debit:,.2f}"],
        ["Current Balance Owed", f"ETB {current_balance:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[80*mm, 80*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 11),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10*mm))

    # Transactions table
    story.append(Paragraph("Transaction History", heading_style))
    if transactions:
        display = list(reversed(transactions))
        table_data = [["Date", "Balance Before", "Credit", "Debit", "Bank Account", "Remaining", "Note"]]
        for tx in display:
            if tx['date']:
                eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(tx['date'])
                date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
            else:
                date_str = ""
            balance_before = f"{tx['balance_before']:,.2f}"
            credit = f"{tx['credit_amount']:,.2f}" if tx['credit_amount'] > 0 else ""
            debit = f"{tx['debit_amount']:,.2f}" if tx['debit_amount'] > 0 else ""
            remaining = f"{tx['balance_after']:,.2f}"
            bank = tx.get('bank_account_display', '—')
            note_paragraph = Paragraph(tx.get('notes', '') if tx.get('notes') else "", note_style)
            table_data.append([date_str, balance_before, credit, debit, bank, remaining, note_paragraph])

        col_widths = [25*mm, 25*mm, 25*mm, 25*mm, 50*mm, 25*mm, 75*mm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('VALIGN', (6,0), (6,-1), 'TOP'),
            ('ALIGN', (1,1), (1,-1), 'RIGHT'),
            ('ALIGN', (2,1), (2,-1), 'RIGHT'),
            ('ALIGN', (3,1), (3,-1), 'RIGHT'),
            ('ALIGN', (5,1), (5,-1), 'RIGHT'),
            ('FONTSIZE', (0,1), (-1,-1), 8),
        ]))
        # Color code credits and debits
        for i, tx in enumerate(display, start=1):
            if tx['credit_amount'] > 0:
                tbl.setStyle(TableStyle([('TEXTCOLOR', (2,i), (2,i), colors.green)]))
            if tx['debit_amount'] > 0:
                tbl.setStyle(TableStyle([('TEXTCOLOR', (3,i), (3,i), colors.red)]))
        story.append(tbl)
    else:
        story.append(Paragraph("No transactions found.", styles['Normal']))

    doc.build(story)
    return buffer.getvalue()