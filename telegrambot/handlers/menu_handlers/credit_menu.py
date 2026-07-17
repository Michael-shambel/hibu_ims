# telegrambot/handlers/menu_handlers/credit_menu.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegrambot.handlers.menu_handlers.states import (
    CREDIT_REPORTS_MENU, ADMIN_MENU, CallbackData, ButtonText, ROLE_ADMIN
)
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard, start

async def credit_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for credit reports submenu."""
    minimal_keyboard = ReplyKeyboardMarkup([
        [ButtonText.BACK_TO_ADMIN, ButtonText.CANCEL]
    ], resize_keyboard=True, is_persistent=True)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Purchase Item History", callback_data=CallbackData.PURCHASE_ITEM_HISTORY)],
        [InlineKeyboardButton("💰 Purchase Payment History", callback_data=CallbackData.PURCHASE_PAYMENT_HISTORY)],
        [InlineKeyboardButton(ButtonText.BACK_TO_ADMIN, callback_data=CallbackData.BACK_TO_ADMIN)],
        [InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)]
    ])

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Use the buttons below to navigate:\n መረጃዎችን ለማግኘት ከታች ይጠቀሙ፡",
            reply_markup=minimal_keyboard
        )
        await query.edit_message_text(
            text="💰 *Credit Reports Menu*\n የዱቤ መረጃ ማውጫ\nChoose a report type:\n የሪፖርት አይነት ይምረጡ",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Use the buttons below to navigate:",
            reply_markup=minimal_keyboard
        )
        await update.message.reply_text(
            "💰 *Credit Reports Menu*\n የዱቤ መረጃ ማውጫ\nChoose a report type:\n የሪፖርት አይነት ይምረጡ",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    return CREDIT_REPORTS_MENU


async def credit_submenu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses inside credit reports menu."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.PURCHASE_ITEM_HISTORY:
        context.user_data.pop('payment_history_mode', None)
        from telegrambot.handlers.reports.purchase_reports import purchase_item_history_entry
        return await purchase_item_history_entry(update, context)
    elif data == CallbackData.PURCHASE_PAYMENT_HISTORY:
        from telegrambot.handlers.reports.purchase_reports import purchase_payment_history_entry
        return await purchase_payment_history_entry(update, context)
    elif data == CallbackData.BACK_TO_ADMIN:
        admin_keyboard = get_main_keyboard(ROLE_ADMIN)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Returning to Admin Panel...\nወደ ዋናው እየተመለሰ...",
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
            "📈 Admin Panel - Select report category:\nየባለቤት ማውጫ _ የሚፈልጉትን ሪፖርት ይምረጡ",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_MENU
    elif data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled. Send /start to begin again.\n ተቋርጧል። እንደገና ለማስጀመር /start ይንኩ።")
        return ConversationHandler.END
    else:
        await query.edit_message_text("❌ Unknown option.")
        return CREDIT_REPORTS_MENU


async def credit_reports_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle persistent keyboard buttons in credit reports menu."""
    text = update.message.text

    if text == ButtonText.BACK_TO_ADMIN:
        admin_keyboard = get_main_keyboard(ROLE_ADMIN)
        await update.message.reply_text(
            "Returning to Admin Panel...\nወደ ዋናው እየተመለሰ...",
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
            "📈 Admin Panel - Select report category:\n የባለቤት ማውጫ _ የሚፈልጉትን ሪፖርት ይምረጡ",
            reply_markup=reply_markup
        )
        return ADMIN_MENU

    elif text == ButtonText.CANCEL:
        await update.message.reply_text(
            "Bye! Send /start to restart.\n ቻው! እንደገና ለማስጀመር /start ይንኩ።",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    elif text == ButtonText.START_MENU:
        await update.message.reply_text("Returning to main menu...\nወደ ዋናው እየተመለሰ...", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)

    else:
        await update.message.reply_text("Please use the buttons below to navigate.\nየታችኛውን በተን ይጠቀሙ")
        return CREDIT_REPORTS_MENU