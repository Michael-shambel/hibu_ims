# expense_menu.py

import asyncio
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from services.expense_service import ExpenseService
from services.expense_category_service import ExpenseCategoryService
from services.bank_account_service import BankAccountService
from telegrambot.handlers.menu_handlers.states import (
    EXPENSE_MENU, EXPENSE_TYPE_SELECTION, EXPENSE_BANK_ACCOUNT_SELECTION,
    EXPENSE_CATEGORY_SELECTION, EXPENSE_AMOUNT_ENTRY, EXPENSE_NOTES_ENTRY,
    CallbackData, ButtonText, ADMIN_MENU, ROLE_ADMIN
)
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard
from config import ADMIN_ID

logger = logging.getLogger(__name__)

expense_service = ExpenseService()
category_service = ExpenseCategoryService()
bank_account_service = BankAccountService()


def _expense_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Record Expense / ወጪ መዝግብ", callback_data=CallbackData.RECORD_EXPENSE)],
        [InlineKeyboardButton(ButtonText.BACK_TO_ADMIN, callback_data=CallbackData.BACK_TO_ADMIN)],
        [InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)]
    ])


def _customer_menu_inline():
    """Re-usable inline keyboard for after a report/action."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Record Another Expense / ወጪ መዝግብ", callback_data=CallbackData.RECORD_EXPENSE)],
        [InlineKeyboardButton(ButtonText.BACK_TO_ADMIN, callback_data=CallbackData.BACK_TO_ADMIN)],
        [InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)]
    ])


async def expense_menu_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point when admin selects 'Expense Report'."""
    reply_markup = _expense_menu_keyboard()

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "💸 *Expense Report*\n\nSelect an action:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="💸 *Expense Report*\n\nSelect an action:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    return EXPENSE_MENU


async def expense_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses in the expense menu."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.RECORD_EXPENSE:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏢 Business / ንግድ", callback_data=CallbackData.EXPENSE_TYPE_BUSINESS)],
            [InlineKeyboardButton("👤 Personal / ግል", callback_data=CallbackData.EXPENSE_TYPE_PERSONAL)],
            [InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)]
        ])
        await query.edit_message_text(
            "📂 *Select Expense Type*",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return EXPENSE_TYPE_SELECTION

    elif data == CallbackData.BACK_TO_ADMIN:
        admin_keyboard = get_main_keyboard(ROLE_ADMIN)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Returning to Admin Panel...",
            reply_markup=admin_keyboard
        )
        from telegrambot.handlers.menu_handlers.main_menu import admin_menu_handler
        query.data = CallbackData.SALES_REPORTS
        return await admin_menu_handler(update, context)

    elif data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled. Send /start to begin again.")
        return ConversationHandler.END

    else:
        await query.edit_message_text("❌ Unknown option.")
        return EXPENSE_MENU


async def expense_type_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store expense type and show bank accounts."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    if data in (CallbackData.EXPENSE_TYPE_BUSINESS, CallbackData.EXPENSE_TYPE_PERSONAL):
        is_personal = (data == CallbackData.EXPENSE_TYPE_PERSONAL)
        context.user_data['expense_is_personal'] = is_personal

        # DB call off the event loop
        accounts = await asyncio.to_thread(
            lambda: [a for a in bank_account_service.get_all() if a.is_active]
        )
        if not accounts:
            await query.edit_message_text("No active bank accounts found. Cancelled.")
            return await expense_menu_entry(update, context)

        keyboard = []
        for acc in accounts:
            bal = await asyncio.to_thread(
                bank_account_service.bank_transaction_service.get_balance, acc.id
            )
            btn = InlineKeyboardButton(
                f"{acc.account_name} ({acc.bank_name}) - ETB {bal:,.2f}",
                callback_data=f"expense_bank_{acc.id}"
            )
            keyboard.append([btn])
        keyboard.append([InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)])

        type_text = "Personal / ግል" if is_personal else "Business / ንግድ"
        await query.edit_message_text(
            f"🏦 *Select Bank Account*\nExpense type: {type_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EXPENSE_BANK_ACCOUNT_SELECTION

    await query.edit_message_text("❌ Unknown option.")
    return EXPENSE_TYPE_SELECTION


async def expense_bank_account_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store bank account and show expense categories."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    if data.startswith("expense_bank_"):
        bank_id = int(data.replace("expense_bank_", ""))
        context.user_data['expense_bank_id'] = bank_id

        # DB call off the event loop
        categories = await asyncio.to_thread(category_service.get_active)
        if not categories:
            await query.edit_message_text("No active expense categories. Cancelled.")
            return await expense_menu_entry(update, context)

        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(cat.name, callback_data=f"expense_cat_{cat.id}")])
        keyboard.append([InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)])

        await query.edit_message_text(
            "📂 *Select Expense Category*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EXPENSE_CATEGORY_SELECTION

    await query.edit_message_text("❌ Unknown option.")
    return EXPENSE_BANK_ACCOUNT_SELECTION


async def expense_category_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store category and ask for amount."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    if data.startswith("expense_cat_"):
        cat_id = int(data.replace("expense_cat_", ""))
        context.user_data['expense_category_id'] = cat_id

        await query.edit_message_text(
            "💵 *Enter Amount*\n\nPlease type the expense amount (numbers only):",
            parse_mode='Markdown'
        )
        return EXPENSE_AMOUNT_ENTRY

    await query.edit_message_text("❌ Unknown option.")
    return EXPENSE_CATEGORY_SELECTION


async def expense_amount_entry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    logger.info(f"EXPENSE_AMOUNT_ENTRY received: '{text}'")

    if text == ButtonText.CANCEL or text == ButtonText.START_MENU:
        if text == ButtonText.CANCEL:
            await update.message.reply_text("❌ Cancelled.", reply_markup=get_main_keyboard(ROLE_ADMIN))
            return ConversationHandler.END
        else:
            from telegrambot.handlers.menu_handlers.main_menu import start
            return await start(update, context)

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a positive number.")
        return EXPENSE_AMOUNT_ENTRY

    context.user_data['expense_amount'] = amount

    # Simple send — no retry loop, no sleep
    await update.message.reply_text(
        f"✅ Amount: *ETB {amount:,.2f}*\n\n"
        "📝 *Enter Notes* (optional):\n"
        "Type any additional notes or description.",
        parse_mode='Markdown'
    )
    return EXPENSE_NOTES_ENTRY


async def expense_notes_entry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Record the expense and confirm."""
    text = update.message.text.strip()

    if text == ButtonText.CANCEL:
        await update.message.reply_text("❌ Cancelled.", reply_markup=get_main_keyboard(ROLE_ADMIN))
        return ConversationHandler.END
    if text == ButtonText.START_MENU:
        from telegrambot.handlers.menu_handlers.main_menu import start
        return await start(update, context)

    notes = text if text else ""

    bank_id = context.user_data.get('expense_bank_id')
    category_id = context.user_data.get('expense_category_id')
    amount = context.user_data.get('expense_amount')
    is_personal = context.user_data.get('expense_is_personal', False)

    if not all([bank_id, category_id, amount is not None]):
        await update.message.reply_text("❌ Session data missing. Please start again.")
        return await expense_menu_entry(update, context)

    expense_data = {
        'bank_account_id': bank_id,
        'amount': amount,
        'category_id': category_id,
        'date': date.today(),
        'notes': notes,
        'description': "Expense recorded via bot",
        'is_personal': is_personal,
        'user_id': ADMIN_ID,
        'payment_method': 'transfer',
    }

    # DB write off the event loop — no longer blocks other users
    created = await asyncio.to_thread(expense_service.create, expense_data)

    if created:
        result_text = (
            f"✅ Expense recorded successfully!\n"
            f"Amount: ETB {amount:,.2f}\n"
            f"Type: {'Personal' if is_personal else 'Business'}\n"
            f"Notes: {notes or 'None'}"
        )
    else:
        result_text = "❌ Failed to record expense. Please check logs."

    # Clean up temp data
    for key in ['expense_bank_id', 'expense_category_id', 'expense_amount', 'expense_is_personal']:
        context.user_data.pop(key, None)

    # Send result + menu in one shot — no extra round-trip
    await update.message.reply_text(
        result_text,
        reply_markup=get_main_keyboard(ROLE_ADMIN)
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="💸 *Expense Report*\n\nSelect an action:",
        parse_mode='Markdown',
        reply_markup=_customer_menu_inline()
    )
    return EXPENSE_MENU