from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegrambot.handlers.menu_handlers.states import (
    ButtonText, CallbackData,  PRODUCT_REPORTS_MENU, ROLE_ADMIN, ADMIN_MENU
)
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard, start

async def product_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    minimal_keyboard = ReplyKeyboardMarkup([
        [ButtonText.BACK_TO_ADMIN, ButtonText.CANCEL]
    ], resize_keyboard=True, is_persistent=True)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Stock Valuation", callback_data=CallbackData.STOCK_VALUATION)],
        [InlineKeyboardButton("⚠️ Low Stock Alert", callback_data=CallbackData.LOW_STOCK)],
        [InlineKeyboardButton("📜 Stock In History", callback_data=CallbackData.STOCK_IN_HISTORY)],
        [InlineKeyboardButton(ButtonText.BACK_TO_ADMIN, callback_data=CallbackData.BACK_TO_ADMIN)],
        [InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)]
    ])

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Use the buttons below to navigate:",
            reply_markup=minimal_keyboard
        )
        await query.edit_message_text(
            text="📊 *Product Reports Menu*\nChoose a report type:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Use the buttons below to navigate:",
            reply_markup=minimal_keyboard
        )
        await update.message.reply_text(
            "📊 *Product Reports Menu*\nChoose a report type:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    return PRODUCT_REPORTS_MENU

async def product_submenu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.STOCK_VALUATION:
        from telegrambot.handlers.reports.product_report import stock_valuation_report_handler
        return await stock_valuation_report_handler(update, context)
    elif data == CallbackData.LOW_STOCK:
        from telegrambot.handlers.reports.product_report import low_stock_report_handler
        return await low_stock_report_handler(update, context)
    elif data == CallbackData.STOCK_IN_HISTORY:
        from telegrambot.handlers.reports.product_report import stock_in_history_report_handler
        return await stock_in_history_report_handler(update, context)
    elif data == CallbackData.BACK_TO_ADMIN:
        admin_keyboard = get_main_keyboard(ROLE_ADMIN)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Returning to Admin Panel...",
            reply_markup=admin_keyboard
        )
        keyboard = [
            [InlineKeyboardButton("📊 Sales Reports / ሽያጭ መረጃ", callback_data=CallbackData.SALES_REPORTS)],
            [InlineKeyboardButton("📦 Product Reports / ንብረት መረጃ", callback_data=CallbackData.PRODUCT_REPORTS)],
            [InlineKeyboardButton("💰 Credit Report / ዱቤ መረጃ", callback_data=CallbackData.CREDIT_REPORTS)],
            [InlineKeyboardButton("🏦 Bank Transfer / ባንክ መረጃ", callback_data=CallbackData.BANK_TRANSFER)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        await query.edit_message_text(
            "📈 Admin Panel - Select report category:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_MENU
    elif data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled. Send /start to begin again.")
        return ConversationHandler.END
    else:
        await query.edit_message_text("❌ Unknown option.")
        return PRODUCT_REPORTS_MENU
    
async def product_reports_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == ButtonText.BACK_TO_ADMIN:
        admin_keyboard = get_main_keyboard(ROLE_ADMIN)
        await update.message.reply_text(
            "Returning to Admin Panel...",
            reply_markup=admin_keyboard
        )
        keyboard = [
            [InlineKeyboardButton("📊 Sales Reports / ሽያጭ መረጃ", callback_data=CallbackData.SALES_REPORTS)],
            [InlineKeyboardButton("📦 Product Reports / ንብረት መረጃ", callback_data=CallbackData.PRODUCT_REPORTS)],
            [InlineKeyboardButton("💰 Credit Report / ዱቤ መረጃ", callback_data=CallbackData.CREDIT_REPORTS)],
            [InlineKeyboardButton("🏦 Bank Transfer / ባንክ መረጃ", callback_data=CallbackData.BANK_TRANSFER)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📈 Admin Panel - Select report category:",
            reply_markup=reply_markup
        )
        return ADMIN_MENU
    
    elif text == ButtonText.CANCEL:
        await update.message.reply_text(
            "Bye! Send /start to restart.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    elif text == ButtonText.START_MENU:
        await update.message.reply_text("Returning to main menu...", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)
    
    else:
        await update.message.reply_text("Please use the buttons below to navigate.")
        return PRODUCT_REPORTS_MENU