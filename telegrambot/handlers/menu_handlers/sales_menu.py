from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from datetime import date
from telegrambot.handlers.menu_handlers.states import (
    TRANSACTION_REPORTS_MENU, ADMIN_MENU, CallbackData, ButtonText, ROLE_ADMIN,
    ETHIOPIAN_MONTHS, ETHIOPIAN_MONTH_SELECTION, ETHIOPIAN_DATE_SELECTION
)
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard, start
from ui.components.ethiopian_date import EthiopianDateConverter
from telegrambot.handlers.reports.sales_report import sales_transaction_report_handler


# -------------------------------------------------------------------------
# Shared helpers
# -------------------------------------------------------------------------
def _admin_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Sales Reports / ሽያጭ መረጃ", callback_data=CallbackData.SALES_REPORTS)],
        [InlineKeyboardButton("📦 Product Reports / ንብረት መረጃ", callback_data=CallbackData.PRODUCT_REPORTS)],
        [InlineKeyboardButton("💰 Credit Report / ዱቤ መረጃ", callback_data=CallbackData.CREDIT_REPORTS)],
        [InlineKeyboardButton("🏦 Bank Transfer / ባንክ መረጃ", callback_data=CallbackData.BANK_TRANSFER)],
        [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)],
    ])


# =========================================================================
#  SALES REPORTS MENU
# =========================================================================
async def sales_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for sales reports submenu."""
    minimal_keyboard = ReplyKeyboardMarkup(
        [[ButtonText.BACK_TO_ADMIN, ButtonText.CANCEL]],
        resize_keyboard=True, is_persistent=True
    )
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Sales Transactions", callback_data=CallbackData.SALES_TRANSACTIONS)],
        [InlineKeyboardButton("💰 Credit Sales Tracking", callback_data=CallbackData.CREDIT_STATUS)],
        [InlineKeyboardButton(ButtonText.BACK_TO_ADMIN, callback_data=CallbackData.BACK_TO_ADMIN)],
        [InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)],
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
            "📊 *Sales Reports Menu*\nChoose a report type:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Use the buttons below to navigate:",
            reply_markup=minimal_keyboard
        )
        await update.message.reply_text(
            "📊 *Sales Reports Menu*\nChoose a report type:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    return TRANSACTION_REPORTS_MENU


# =========================================================================
#  SALES SUBMENU CALLBACK HANDLER
# =========================================================================
async def sales_submenu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses inside sales reports menu."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.SALES_TRANSACTIONS:
        return await ask_ethiopian_month(update, context)

    elif data == CallbackData.CREDIT_STATUS:
        from telegrambot.handlers.reports.credit_sales_report import credit_sales_report_handler
        return await credit_sales_report_handler(update, context)

    elif data == CallbackData.BACK_TO_ADMIN:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Returning to Admin Panel...",
            reply_markup=get_main_keyboard(ROLE_ADMIN)
        )
        await query.edit_message_text(
            "📈 Admin Panel - Select report category:",
            reply_markup=_admin_inline_keyboard()
        )
        return ADMIN_MENU

    elif data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled. Send /start to begin again.")
        return ConversationHandler.END

    else:
        await query.edit_message_text("❌ Unknown option.")
        return TRANSACTION_REPORTS_MENU


# =========================================================================
#  ETHIOPIAN MONTH SELECTION
# =========================================================================
async def ask_ethiopian_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show inline keyboard with Ethiopian months."""
    query = update.callback_query
    await query.answer()

    month_buttons = [
        InlineKeyboardButton(
            f"{amharic} ({english})",
            callback_data=f"{CallbackData.SELECT_MONTH}{i + 1}"
        )
        for i, (amharic, english) in enumerate(ETHIOPIAN_MONTHS)
    ]

    keyboard = [month_buttons[i:i + 2] for i in range(0, len(month_buttons), 2)]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL_DATE)])

    await query.edit_message_text(
        "📅 *Select Ethiopian Month*\nChoose the month for the sales report:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ETHIOPIAN_MONTH_SELECTION


async def handle_month_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.CANCEL_DATE:
        await query.edit_message_text("Date selection cancelled.")
        return await sales_reports_menu(update, context)

    if data.startswith(CallbackData.SELECT_MONTH):
        month_num = int(data.split('_')[-1])
        context.user_data['temp_month'] = month_num
        return await ask_ethiopian_date(update, context, month_num)


async def ask_ethiopian_date(update: Update, context: ContextTypes.DEFAULT_TYPE, month_num: int):
    query = update.callback_query
    max_day = 6 if month_num == 13 else 30
    context.user_data['temp_max_day'] = max_day

    await query.edit_message_text(
        f"📅 *Selected Month:* {ETHIOPIAN_MONTHS[month_num - 1][0]} ({ETHIOPIAN_MONTHS[month_num - 1][1]})\n\n"
        f"Now enter the *day number* (1-{max_day}):\n"
        f"Example: `15`\n\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    return ETHIOPIAN_DATE_SELECTION


# =========================================================================
#  DATE INPUT HANDLER
# =========================================================================
async def handle_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process day number typed by user."""
    user_input = update.message.text.strip()

    # Persistent keyboard buttons
    if user_input == ButtonText.START_MENU:
        await update.message.reply_text("Returning to main menu...", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)

    if user_input == ButtonText.CANCEL:
        await update.message.reply_text("Bye! Send /start to restart.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if user_input == ButtonText.BACK_TO_ADMIN:
        await update.message.reply_text(
            "Returning to Admin Panel...",
            reply_markup=get_main_keyboard(ROLE_ADMIN)
        )
        await update.message.reply_text(
            "📈 Admin Panel - Select report category:",
            reply_markup=_admin_inline_keyboard()
        )
        return ADMIN_MENU

    if not user_input.isdigit():
        await update.message.reply_text(
            "❌ Please enter a valid number (e.g., 15) or use the menu buttons."
        )
        return ETHIOPIAN_DATE_SELECTION

    day = int(user_input)
    month = context.user_data.get('temp_month')
    max_day = context.user_data.get('temp_max_day')

    if not month or not max_day:
        await update.message.reply_text("Session expired. Please start again from Sales Reports.")
        return await sales_reports_menu(update, context)

    if day < 1 or day > max_day:
        await update.message.reply_text(f"❌ Day must be between 1 and {max_day}. Try again.")
        return ETHIOPIAN_DATE_SELECTION

    today_greg = date.today()
    eth_year, _, _ = EthiopianDateConverter.to_ethiopian(today_greg)
    eth_year = context.user_data.get('temp_year', eth_year)

    greg_date = EthiopianDateConverter.to_gregorian(eth_year, month, day)

    context.user_data.pop('temp_month', None)
    context.user_data.pop('temp_max_day', None)
    context.user_data.pop('temp_year', None)

    return await sales_transaction_report_handler(update, context, eth_year, month, day, greg_date)


# =========================================================================
#  PERSISTENT KEYBOARD TEXT HANDLER
# =========================================================================
async def sales_reports_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle persistent keyboard buttons while in sales reports menu."""
    text = update.message.text

    if text == ButtonText.BACK_TO_ADMIN:
        await update.message.reply_text(
            "Returning to Admin Panel...",
            reply_markup=get_main_keyboard(ROLE_ADMIN)
        )
        await update.message.reply_text(
            "📈 Admin Panel - Select report category:",
            reply_markup=_admin_inline_keyboard()
        )
        return ADMIN_MENU

    elif text == ButtonText.CANCEL:
        await update.message.reply_text("Bye! Send /start to restart.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    elif text == ButtonText.START_MENU:
        await update.message.reply_text("Returning to main menu...", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)

    else:
        await update.message.reply_text("Please use the buttons below to navigate.")
        return TRANSACTION_REPORTS_MENU