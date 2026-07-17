import logging
import io
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from services.bank_account_service import BankAccountService
from services.bank_transaction_service import BankTransactionService
from telegrambot.handlers.reports.bank_reports import (
    generate_total_balance_pdf,
    generate_bank_account_pdf
)
from telegrambot.handlers.menu_handlers.states import (
    BANK_TRANSFER_EXTERNAL_PAYEE, CallbackData, ButtonText, BANK_MENU,
    BANK_TRANSFER_FROM_ACCOUNT, BANK_TRANSFER_TO_ACCOUNT, BANK_TRANSFER_AMOUNT,
    BANK_TRANSFER_REASON, ADMIN_MENU, ROLE_ADMIN
)
import asyncio

logger = logging.getLogger(__name__)

bank_account_service = BankAccountService()
bank_transaction_service = BankTransactionService()


# -------------------------------------------------------------------------
# Helper to get a nice display name for a bank account
# -------------------------------------------------------------------------
def bank_display_name(account) -> str:
    return f"{account.account_name} ({account.bank_name})"


def _admin_inline_keyboard():
    """Shared admin panel inline keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Sales Reports", callback_data=CallbackData.SALES_REPORTS)],
        [InlineKeyboardButton("📦 Product Reports", callback_data=CallbackData.PRODUCT_REPORTS)],
        [InlineKeyboardButton("💰 Credit Report", callback_data=CallbackData.CREDIT_REPORTS)],
        [InlineKeyboardButton("🏦 Bank Transfer", callback_data=CallbackData.BANK_TRANSFER)],
        [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
    ])


# =========================================================================
#  BANK MENU (entry point)
# =========================================================================
async def bank_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display bank operations menu. Works with both inline buttons and text messages."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Get Total Balance/ጠቅላላ ባንክ መረጃ", callback_data=CallbackData.BANK_GET_TOTAL_BALANCE)],
        [InlineKeyboardButton("ℹ️ Bank Information/የተናጥል ባንክ መረጃ", callback_data=CallbackData.BANK_GET_INFO)],
        [InlineKeyboardButton("💸 Transfer Funds/ገንዘብ ማስተላለፍ", callback_data=CallbackData.BANK_TRANSFER_FUNDS)],
        [InlineKeyboardButton(ButtonText.BACK_TO_ADMIN, callback_data=CallbackData.BACK_TO_ADMIN)],
        [InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)]
    ])

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "🏦 *Bank Operations*\nChoose an action:",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            "🏦 *Bank Operations*\nChoose an action:",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    return BANK_MENU


# =========================================================================
#  1) GET TOTAL BALANCE
# =========================================================================
async def get_total_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Generating total balance report.../ጠቅላላ ባንክ መረጃ በማፍራት ላይ...")

    # PDF generation is CPU-bound — run off the event loop
    pdf_bytes = await asyncio.to_thread(generate_total_balance_pdf)

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=io.BytesIO(pdf_bytes),
        filename=f"total_balance_{date.today().isoformat()}.pdf",
        caption="💰 Total Balance Report/ጠቅላላ ባንክ መረጃ"
    )
    return await bank_menu_handler(update, context)


# =========================================================================
#  2) BANK INFORMATION (list of accounts)
# =========================================================================
async def bank_info_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # DB call off the event loop
    accounts = await asyncio.to_thread(bank_account_service.get_all)
    active_accounts = [a for a in accounts if a.is_active]

    if not active_accounts:
        await query.edit_message_text("No active bank accounts found.")
        return await bank_menu_handler(update, context)

    keyboard = []
    for acc in active_accounts:
        balance = await asyncio.to_thread(bank_transaction_service.get_balance, acc.id)
        btn_text = f"{acc.account_name} ({acc.bank_name}) - ETB {balance:,.2f}"
        cb_data = f"{CallbackData.BANK_ACCOUNT_PREFIX}{acc.id}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

    keyboard.append([InlineKeyboardButton(ButtonText.BACK_TO_ADMIN, callback_data=CallbackData.BACK_TO_ADMIN)])
    keyboard.append([InlineKeyboardButton(ButtonText.CANCEL, callback_data=CallbackData.CANCEL)])

    await query.edit_message_text(
        "🏛 *Select a bank account* to get its report:/ የተናጥል ባንክ መረጃ ለማግኘት ባንክ አካውንት ይምረጡ:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BANK_MENU


async def handle_bank_account_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith(CallbackData.BANK_ACCOUNT_PREFIX):
        account_id = int(data.replace(CallbackData.BANK_ACCOUNT_PREFIX, ""))
        await query.edit_message_text(f"⏳ Generating report for account ID {account_id}.../ ባንክ መረጃ በማፍራት ላይ...")

        # DB + PDF off the event loop
        account = await asyncio.to_thread(bank_account_service.get_by_id, account_id)
        if not account:
            await query.edit_message_text("Account not found.")
            return await bank_menu_handler(update, context)

        pdf_bytes = await asyncio.to_thread(generate_bank_account_pdf, account)
        safe_name = account.account_name.replace(' ', '_')
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"bank_{safe_name}_{date.today().isoformat()}.pdf",
            caption=f"🏦 {account.account_name} ({account.bank_name}) Report"
        )
        return await bank_info_list_handler(update, context)

    elif data == CallbackData.BACK_TO_ADMIN:
        return await bank_menu_handler(update, context)
    elif data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    return BANK_MENU


# =========================================================================
#  3) TRANSFER FUNDS – with step‑by‑step confirmations
# =========================================================================

# --------------------------------------------------------------------
# Show source accounts
# --------------------------------------------------------------------
async def show_from_accounts(update, context, message_text):
    """Display source accounts as buttons."""
    accounts = await asyncio.to_thread(bank_account_service.get_all)
    active = [a for a in accounts if a.is_active]

    if not active:
        if update.callback_query:
            await update.callback_query.edit_message_text("No active accounts.")
        return await bank_menu_handler(update, context)

    keyboard = []
    for acc in active:
        balance = await asyncio.to_thread(bank_transaction_service.get_balance, acc.id)
        btn = InlineKeyboardButton(
            f"{acc.account_name} ({acc.bank_name}) - ETB {balance:,.2f}",
            callback_data=f"transfer_from_{acc.id}"
        )
        keyboard.append([btn])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)])

    await update.callback_query.edit_message_text(
        message_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BANK_TRANSFER_FROM_ACCOUNT


# --------------------------------------------------------------------
# After source is selected
# --------------------------------------------------------------------
async def transfer_from_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("transfer_from_"):
        from_id = int(data.replace("transfer_from_", ""))

        # DB call off the event loop
        source_acc = await asyncio.to_thread(bank_account_service.get_by_id, from_id)
        src_name = bank_display_name(source_acc) if source_acc else "Unknown"

        context.user_data['bank_transfer'] = {
            'from_id': from_id,
            'from_name': src_name
        }

        if context.user_data.get('transfer_type') == 'external':
            await query.edit_message_text(
                f"✅ Source: **{src_name}**\n\n💵 Please enter the **amount** to transfer:",
                parse_mode='Markdown'
            )
            return BANK_TRANSFER_AMOUNT
        else:
            return await show_to_accounts(update, context, from_id)

    elif data == CallbackData.CANCEL:
        await query.edit_message_text("Transfer cancelled.")
        return await bank_menu_handler(update, context)

    return BANK_TRANSFER_FROM_ACCOUNT


# --------------------------------------------------------------------
# Show destination accounts (internal)
# --------------------------------------------------------------------
async def show_to_accounts(update, context, from_id):
    accounts = await asyncio.to_thread(bank_account_service.get_all)
    active = [a for a in accounts if a.is_active and a.id != from_id]

    if not active:
        await update.callback_query.edit_message_text("No other active accounts to transfer to.")
        return await bank_menu_handler(update, context)

    transfer = context.user_data.get('bank_transfer', {})
    src_name = transfer.get('from_name', 'Unknown')

    keyboard = []
    for acc in active:
        balance = await asyncio.to_thread(bank_transaction_service.get_balance, acc.id)
        btn = InlineKeyboardButton(
            f"{acc.account_name} ({acc.bank_name}) - ETB {balance:,.2f}",
            callback_data=f"transfer_to_{acc.id}"
        )
        keyboard.append([btn])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)])

    await update.callback_query.edit_message_text(
        f"✅ Source: **{src_name}**\n\nSelect the **destination** bank account:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BANK_TRANSFER_TO_ACCOUNT


# --------------------------------------------------------------------
# After destination is selected
# --------------------------------------------------------------------
async def transfer_to_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("transfer_to_"):
        to_id = int(data.replace("transfer_to_", ""))

        # DB call off the event loop
        dest_acc = await asyncio.to_thread(bank_account_service.get_by_id, to_id)
        dest_name = bank_display_name(dest_acc) if dest_acc else "Unknown"

        transfer_data = context.user_data.get('bank_transfer', {})
        transfer_data['to_id'] = to_id
        transfer_data['to_name'] = dest_name
        context.user_data['bank_transfer'] = transfer_data

        src_name = transfer_data.get('from_name', 'Unknown')
        await query.edit_message_text(
            f"✅ Source: **{src_name}**\n"
            f"✅ Destination: **{dest_name}**\n\n"
            f"💵 Please enter the **amount** to transfer:",
            parse_mode='Markdown'
        )
        return BANK_TRANSFER_AMOUNT

    elif data == CallbackData.CANCEL:
        await query.edit_message_text("Transfer cancelled.")
        return await bank_menu_handler(update, context)

    return BANK_TRANSFER_TO_ACCOUNT


# --------------------------------------------------------------------
# Handle amount entry
# --------------------------------------------------------------------
async def transfer_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in (ButtonText.START_MENU, ButtonText.CANCEL, ButtonText.BACK_TO_ADMIN):
        from telegrambot.handlers.menu_handlers.main_menu import handle_persistent_buttons
        return await handle_persistent_buttons(update, context)

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid positive number.")
        return BANK_TRANSFER_AMOUNT

    transfer = context.user_data.get('bank_transfer', {})
    transfer['amount'] = amount
    context.user_data['bank_transfer'] = transfer

    if context.user_data.get('transfer_type') == 'external':
        await update.message.reply_text(
            f"💵 Amount entered: **ETB {amount:,.2f}**\n\n👤 Enter the **payee / recipient name**:",
            parse_mode='Markdown'
        )
        return BANK_TRANSFER_EXTERNAL_PAYEE
    else:
        await update.message.reply_text(
            f"💵 Amount entered: **ETB {amount:,.2f}**\n\n📝 Provide a short **reason/description**:",
            parse_mode='Markdown'
        )
        return BANK_TRANSFER_REASON


# --------------------------------------------------------------------
# After reason is entered (internal transfer)
# --------------------------------------------------------------------
async def transfer_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in (ButtonText.START_MENU, ButtonText.CANCEL, ButtonText.BACK_TO_ADMIN):
        from telegrambot.handlers.menu_handlers.main_menu import handle_persistent_buttons
        return await handle_persistent_buttons(update, context)

    transfer = context.user_data.pop('bank_transfer', None)
    if not transfer:
        await update.message.reply_text("Transfer session expired. Please start again.")
        return await bank_menu_handler(update, context)

    from_id = transfer['from_id']
    to_id = transfer['to_id']
    amount = transfer['amount']
    description = text
    src_name = transfer.get('from_name', 'Unknown')
    to_name = transfer.get('to_name', 'Unknown')

    await update.message.reply_text(
        f"🔄 Transferring **ETB {amount:,.2f}**\n"
        f"From: **{src_name}**\n"
        f"To: **{to_name}**\n"
        f"Reason: *{description}*\n\n⏳ Processing...",
        parse_mode='Markdown'
    )

    # DB write off the event loop
    success = await asyncio.to_thread(
        bank_transaction_service.transfer_between_accounts,
        from_account_id=from_id,
        to_account_id=to_id,
        amount=amount,
        transaction_date=date.today(),
        description=description
    )

    if success:
        await update.message.reply_text("✅ Transfer completed successfully.")
    else:
        await update.message.reply_text("❌ Transfer failed. Please check the logs.")

    return await bank_menu_handler(update, context)


# --------------------------------------------------------------------
# After payee name is entered (external transfer)
# --------------------------------------------------------------------
async def transfer_external_payee_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in (ButtonText.START_MENU, ButtonText.CANCEL, ButtonText.BACK_TO_ADMIN):
        from telegrambot.handlers.menu_handlers.main_menu import handle_persistent_buttons
        return await handle_persistent_buttons(update, context)

    transfer = context.user_data.get('bank_transfer', {})
    if not transfer:
        await update.message.reply_text("Session expired. Please start again.")
        return await bank_menu_handler(update, context)

    from_id = transfer['from_id']
    amount = transfer['amount']
    payee = text
    src_name = transfer.get('from_name', 'Unknown')

    await update.message.reply_text(
        f"🔄 Transferring **ETB {amount:,.2f}**\n"
        f"From: **{src_name}**\n"
        f"To: external payee **{payee}**\n\n⏳ Processing...",
        parse_mode='Markdown'
    )

    # DB write off the event loop
    success = await asyncio.to_thread(
        bank_transaction_service.create_external_transfer,
        from_account_id=from_id,
        amount=amount,
        transaction_date=date.today(),
        payee=payee,
        description=f"External transfer to {payee}"
    )

    if success:
        await update.message.reply_text("✅ External transfer recorded successfully.")
    else:
        await update.message.reply_text("❌ Transfer failed. Check logs.")

    # Clean up transfer data
    context.user_data.pop('bank_transfer', None)
    context.user_data.pop('transfer_type', None)

    return await bank_menu_handler(update, context)


# =========================================================================
#  BANK_MENU callback dispatcher
# =========================================================================
async def bank_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.BANK_GET_TOTAL_BALANCE:
        return await get_total_balance_handler(update, context)

    elif data == CallbackData.BANK_GET_INFO:
        return await bank_info_list_handler(update, context)

    elif data == CallbackData.BANK_TRANSFER_FUNDS:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Between My Accounts", callback_data="transfer_type_internal")],
            [InlineKeyboardButton("🏦 To External Account", callback_data="transfer_type_external")],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ])
        await query.edit_message_text(
            "💸 **Select Transfer Type:**",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return BANK_MENU

    elif data in ("transfer_type_internal", "transfer_type_external"):
        context.user_data['transfer_type'] = "external" if data == "transfer_type_external" else "internal"
        return await show_from_accounts(update, context, "Select the **source** bank account:")

    elif data == CallbackData.BACK_TO_ADMIN:
        from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard
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
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    elif data.startswith(CallbackData.BANK_ACCOUNT_PREFIX):
        return await handle_bank_account_selection(update, context)

    else:
        await query.edit_message_text("Unknown action.")
        return BANK_MENU