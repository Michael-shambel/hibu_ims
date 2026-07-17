import asyncio
import io
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TelegramError
from services.supplier_service import SupplierService
from services.purchase_service import PurchaseService
from telegrambot.handlers.menu_handlers.states import (
    ConversationStates, CallbackData, ButtonText, ROLE_SUPPLIER
)
from telegrambot.handlers.reports.purchase_reports import (
    generate_supplier_credit_items_pdf,
    generate_supplier_payment_history_pdf
)
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard, start

logger = logging.getLogger(__name__)
supplier_service = SupplierService()
purchase_service = PurchaseService()

async def start_supplier_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point when user selects 'Supplier' role."""
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    context.user_data.clear()

    existing = supplier_service.get_by_any_chat_id(chat_id)
    if existing:
        # Already registered
        context.user_data['supplier_id'] = existing.id
        context.user_data['supplier_name'] = existing.supplier_name
        context.user_data['user_role'] = ROLE_SUPPLIER

        await query.edit_message_text(
            f"✅ Welcome back **{existing.supplier_name}**!\n"
            "Your Telegram is already linked to your supplier account.",
            parse_mode='Markdown'
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="Use the buttons below:",
            reply_markup=get_main_keyboard(ROLE_SUPPLIER)
        )
        return await show_supplier_menu(update, context, is_new=False)
    else:
        # New supplier: ask for phone number
        context.user_data['auth_role'] = 'supplier'
        await query.edit_message_text(
            "📞 *Supplier Registration*\n\n"
            "Please enter your registered contact phone number.\n"
            "Example: 0912345678\n\n"
            "This will link your Telegram account to your supplier profile.\n"
            "Type /cancel to abort.",
            parse_mode='Markdown'
        )
        return ConversationStates.SUPPLIER_AUTH_PHONE

async def receive_supplier_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive phone number and register chat_id."""
    text = update.message.text.strip()

    # Handle persistent keyboard buttons FIRST
    if text == ButtonText.CANCEL:
        await update.message.reply_text(
            "❌ Registration cancelled. Send /start to begin again.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    elif text == ButtonText.START_MENU:
        await update.message.reply_text("Returning to main menu...", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)
    
    phone = update.message.text.strip()
    chat_id = update.effective_chat.id

    if not phone.isdigit() or len(phone) < 9:
        await update.message.reply_text(
            "❌ Invalid phone number. Please enter digits only (e.g., 0912345678).\n"
            "Send /cancel to stop."
        )
        return ConversationStates.SUPPLIER_AUTH_PHONE

    supplier = supplier_service.register_chat_id(phone, chat_id)
    if supplier:
        context.user_data['supplier_id'] = supplier.id
        context.user_data['supplier_name'] = supplier.supplier_name
        context.user_data['user_role'] = ROLE_SUPPLIER

        await update.message.reply_text(
            f"✅ Success! Your Telegram is now linked to supplier **{supplier.supplier_name}**.",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(ROLE_SUPPLIER)
        )
        return await show_supplier_menu(update, context, is_new=True)
    else:
        await update.message.reply_text(
            "❌ Registration failed.\n\n"
            "Possible reasons:\n"
            "- Phone number not found in our system.\n"
            "- This phone number is already linked to another Telegram account.\n"
            "- Your account already has a different chat_id (cannot change).\n\n"
            "Please contact support or try again.\n"
            "Send /start to restart."
        )
        return ConversationHandler.END

async def show_supplier_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_new: bool = False):
    """Display the supplier menu with two buttons."""
    supplier_name = context.user_data.get('supplier_name', 'Supplier')
    keyboard = [
        [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.SUPPLIER_CREDIT_ITEMS)],
        [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.SUPPLIER_CREDIT_PAYMENTS)],
        [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if is_new:
        await update.message.reply_text(
            f"📋 *Supplier Menu for {supplier_name}*\n\nPlease choose an option:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        # Called from callback query after welcome back
        query = update.callback_query
        await query.edit_message_text(
            f"📋 *Supplier Menu for {supplier_name}*\n\nPlease choose an option:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    return ConversationStates.SUPPLIER_MENU_MAIN

async def supplier_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses in supplier menu."""
    query = update.callback_query
    await query.answer()
    data = query.data

    supplier_id = context.user_data.get('supplier_id')
    supplier_name = context.user_data.get('supplier_name', 'Supplier')

    if not supplier_id:
        # Attempt recovery via chat_id
        chat_id = update.effective_chat.id
        supplier = supplier_service.get_by_chat_id(chat_id)
        if supplier:
            context.user_data['supplier_id'] = supplier.id
            context.user_data['supplier_name'] = supplier.supplier_name
            supplier_id = supplier.id
            supplier_name = supplier.supplier_name
        else:
            await query.edit_message_text("❌ Session expired. Send /start to begin again.")
            return ConversationHandler.END

    if data == CallbackData.SUPPLIER_CREDIT_ITEMS:
        await query.edit_message_text("📄 Generating your credit item history report... Please wait.")
        try:
            groups = await asyncio.to_thread(purchase_service.get_supplier_credit_purchases_grouped, supplier_id)
            if not groups:
                await query.edit_message_text("📭 You have no credit purchases.")
            else:
                pdf_bytes = await asyncio.to_thread(generate_supplier_credit_items_pdf, supplier_name, groups)
                all_chat_ids = supplier_service.get_all_notification_chat_ids(supplier_id)
                for cid in all_chat_ids:
                    try:
                        await context.bot.send_document(
                            chat_id=cid,
                            document=io.BytesIO(pdf_bytes),
                            filename=f"supplier_credit_items_{supplier_name}.pdf",
                            caption=f"📦 Credit Item History - {supplier_name}"
                        )
                    except TelegramError as e:
                        logger.warning("Failed to send credit items to chat %s: %s", cid, e)
        except Exception as e:
            logger.error(f"Error generating supplier credit items PDF: {e}")
            await query.edit_message_text("❌ Failed to generate report. Please try again later.")

        # Re-show menu
        keyboard = [
            [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.SUPPLIER_CREDIT_ITEMS)],
            [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.SUPPLIER_CREDIT_PAYMENTS)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        await query.message.reply_text(
            "📋 *Supplier Menu*\n\nSelect another option:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationStates.SUPPLIER_MENU_MAIN

    elif data == CallbackData.SUPPLIER_CREDIT_PAYMENTS:
        await query.edit_message_text("📄 Generating your payment history report... Please wait.")
        try:
            transactions = await asyncio.to_thread(purchase_service.get_supplier_combined_history, supplier_id)
            if not transactions:
                await query.edit_message_text("📭 No payment transactions found.")
            else:
                total_credit = sum(tx['credit_amount'] for tx in transactions)
                total_debit = sum(tx['debit_amount'] for tx in transactions)
                current_balance = transactions[-1]['balance_after'] if transactions else 0.0
                pdf_bytes = await asyncio.to_thread(
                    generate_supplier_payment_history_pdf,
                    supplier_name=supplier_name,
                    transactions=transactions,
                    total_credit=total_credit,
                    total_debit=total_debit,
                    current_balance=current_balance
                )
                all_chat_ids = supplier_service.get_all_notification_chat_ids(supplier_id)
                for cid in all_chat_ids:
                    try:
                        await context.bot.send_document(
                            chat_id=cid,
                            document=io.BytesIO(pdf_bytes),
                            filename=f"supplier_payment_history_{supplier_name}.pdf",
                            caption=f"💰 Payment History - {supplier_name}"
                        )
                    except TelegramError as e:
                        logger.warning("Failed to send payment history to chat %s: %s", cid, e)
        except Exception as e:
            logger.error(f"Error generating supplier payment history PDF: {e}")
            await query.edit_message_text("❌ Failed to generate report. Please try again later.")

        keyboard = [
            [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.SUPPLIER_CREDIT_ITEMS)],
            [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.SUPPLIER_CREDIT_PAYMENTS)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        await query.message.reply_text(
            "📋 *Supplier Menu*\n\nSelect another option:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationStates.SUPPLIER_MENU_MAIN

    elif data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled. Send /start to begin again.", reply_markup=None)
        return ConversationHandler.END
    else:
        await query.edit_message_text("❌ Unknown option.")
        return ConversationStates.SUPPLIER_MENU_MAIN