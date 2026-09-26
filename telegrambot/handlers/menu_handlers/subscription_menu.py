#!/usr/bin/env python3
"""
Admin self-service for report subscriptions.

An admin can switch between the full company report and a product-scoped report
built from named product groups, and choose which report types they receive.
Groups themselves, external subscribers and expense tagging are maintained from
the desktop app (Reports -> Admin Actions -> Report Subscriptions).
"""
import asyncio
import logging

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    ReplyKeyboardRemove, Update,
)
from telegram.ext import ContextTypes, ConversationHandler

from services.auth_service import AuthService
from services.product_group_service import ProductGroupService
from services.report_subscription_service import (
    REPORT_TYPE_LABELS, ReportSubscriptionService,
)
from telegrambot.handlers.menu_handlers.states import (
    ADMIN_MENU, REPORT_SUBSCRIPTION_MENU, ROLE_ADMIN, CallbackData, ButtonText,
)

logger = logging.getLogger(__name__)


def _subscription_keyboard(subscription: dict, groups: list) -> InlineKeyboardMarkup:
    """Build the toggle keyboard for one admin's subscription."""
    scoped = not subscription['full_report']
    selected_groups = set(subscription['group_ids'])

    rows = []
    if scoped:
        rows.append([InlineKeyboardButton(
            "✅ Full report (all products)", callback_data=CallbackData.SUB_FULL_REPORT)])
    else:
        rows.append([InlineKeyboardButton(
            "🎯 Limit to product groups", callback_data=CallbackData.SUB_PARTIAL_REPORT)])

    for group in groups:
        mark = "✅" if group['id'] in selected_groups else "⬜"
        rows.append([InlineKeyboardButton(
            f"{mark} {group['name']} ({group['product_count']} products)",
            callback_data=f"{CallbackData.SUB_TOGGLE_GROUP}{group['id']}",
        )])

    type_row = []
    for key, label in REPORT_TYPE_LABELS.items():
        flag = 'receive_' + key
        mark = "✅" if subscription.get(flag, True) else "⬜"
        type_row.append(InlineKeyboardButton(
            f"{mark} {label}", callback_data=f"{CallbackData.SUB_TOGGLE_TYPE}{key}"))
        if len(type_row) == 2:
            rows.append(type_row)
            type_row = []
    if type_row:
        rows.append(type_row)

    rows.append([InlineKeyboardButton("🔙 Back to Admin", callback_data=CallbackData.BACK_TO_ADMIN)])
    return InlineKeyboardMarkup(rows)


def _subscription_text(subscription: dict, groups: list, admin_name: str) -> str:
    scoped = not subscription['full_report']
    selected = [g['name'] for g in groups if g['id'] in set(subscription['group_ids'])]

    if not scoped:
        scope_line = "📦 *Scope:* Full report (all products)"
    elif not selected:
        scope_line = ("⚠️ *Scope:* Product scoped, but no group is selected yet — "
                      "you will still receive the full report until you pick one.")
    else:
        scope_line = f"📦 *Scope:* {', '.join(selected)}"

    types = [label for key, label in REPORT_TYPE_LABELS.items()
             if subscription.get('receive_' + key, True)]

    return (
        f"🔔 *Report Subscription*\n"
        f"👤 {admin_name}\n\n"
        f"ℹ️ *Admin accounts always receive all five reports* — Daily, 1-Month, "
        f"3-Month, 6-Month and 1-Year — as the *full company report*, so the "
        f"choices below no longer change what you receive.\n\n"
        f"{scope_line}\n"
        f"🗓 *Reports:* {', '.join(types) if types else 'none'}"
    )


async def _render(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    service = ReportSubscriptionService()
    group_service = ProductGroupService()

    admin_name = context.user_data.get('authenticated_username', 'Admin')

    def _load_subscription():
        # First use creates a default (full report) row for this admin.
        service.ensure_for_chat_id(chat_id, admin_name)
        return service.get_by_chat_id(chat_id)

    subscription = await asyncio.to_thread(_load_subscription)
    if not subscription:
        subscription = {
            'full_report': True, 'group_ids': [],
            'receive_daily': True, 'receive_monthly': True, 'receive_quarterly': True,
            'receive_semiannual': True, 'receive_annual': True,
        }

    groups = await asyncio.to_thread(group_service.list_with_counts)
    text = _subscription_text(subscription, groups, admin_name)
    keyboard = _subscription_keyboard(subscription, groups)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode='Markdown', reply_markup=keyboard)
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode='Markdown', reply_markup=keyboard)
    return REPORT_SUBSCRIPTION_MENU


async def subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/subscription` — works from any menu state."""
    chat_id = update.effective_chat.id
    auth_service = AuthService()
    is_admin = await asyncio.to_thread(auth_service.is_admin_chat_id, chat_id)
    if not is_admin:
        await context.bot.send_message(
            chat_id=chat_id,
            text="🔒 Report subscriptions are available to admins only.\n"
                 "Send /getid and share the number with the administrator to be added.",
        )
        return ConversationHandler.END

    context.user_data['user_role'] = ROLE_ADMIN
    return await _render(update, context)


async def report_subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point from the admin panel button."""
    if update.callback_query:
        await update.callback_query.answer()
    return await _render(update, context)


async def subscription_submenu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the toggle buttons."""
    query = update.callback_query
    await query.answer()
    data = query.data or ''
    chat_id = update.effective_chat.id
    service = ReportSubscriptionService()

    if data == CallbackData.SUB_FULL_REPORT:
        await asyncio.to_thread(service.set_full_report_for_chat_id, chat_id, True)
    elif data == CallbackData.SUB_PARTIAL_REPORT:
        await asyncio.to_thread(service.set_full_report_for_chat_id, chat_id, False)
    elif data.startswith(CallbackData.SUB_TOGGLE_GROUP):
        try:
            group_id = int(data.replace(CallbackData.SUB_TOGGLE_GROUP, ''))
        except ValueError:
            return REPORT_SUBSCRIPTION_MENU

        current = await asyncio.to_thread(service.get_by_chat_id, chat_id) or {}
        selected = set(current.get('group_ids') or [])
        if group_id in selected:
            selected.discard(group_id)
        else:
            selected.add(group_id)
        await asyncio.to_thread(service.set_groups_for_chat_id, chat_id, sorted(selected))
    elif data.startswith(CallbackData.SUB_TOGGLE_TYPE):
        report_type = data.replace(CallbackData.SUB_TOGGLE_TYPE, '')
        if report_type in REPORT_TYPE_LABELS:
            current = await asyncio.to_thread(service.get_by_chat_id, chat_id) or {}
            currently_on = bool(current.get('receive_' + report_type, True))
            await asyncio.to_thread(
                service.set_report_type_for_chat_id, chat_id, report_type, not currently_on)
    elif data == CallbackData.BACK_TO_ADMIN:
        from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard
        await context.bot.send_message(
            chat_id=chat_id,
            text="Returning to Admin Panel...",
            reply_markup=get_main_keyboard(ROLE_ADMIN),
        )
        await query.edit_message_text(
            "📈 Admin Panel - Select report category:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Sales Reports / ሽያጭ መረጃ", callback_data=CallbackData.SALES_REPORTS)],
                [InlineKeyboardButton("📦 Product Reports / ንብረት መረጃ", callback_data=CallbackData.PRODUCT_REPORTS)],
                [InlineKeyboardButton("💰 Credit Report / ዱቤ መረጃ", callback_data=CallbackData.CREDIT_REPORTS)],
                [InlineKeyboardButton("🏦 Bank Transfer / ባንክ መረጃ", callback_data=CallbackData.BANK_TRANSFER)],
                [InlineKeyboardButton("🔔 Report Subscription / ሪፖርት ደንበኝነት", callback_data=CallbackData.REPORT_SUBSCRIPTION)],
                [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)],
            ]),
        )
        return ADMIN_MENU
    else:
        await query.edit_message_text("❌ Unknown option.")
        return REPORT_SUBSCRIPTION_MENU

    return await _render(update, context)


async def subscription_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Persistent-keyboard handling inside the subscription menu."""
    text = (update.message.text or '').strip()

    if text == ButtonText.BACK_TO_ADMIN:
        await update.message.reply_text(
            "Returning to Admin Panel...",
            reply_markup=ReplyKeyboardMarkup(
                [[ButtonText.SALES_REPORTS, ButtonText.PRODUCT_REPORTS],
                 [ButtonText.CREDIT_REPORT, ButtonText.BANK_TRANSFER],
                 [ButtonText.REPORT_SUBSCRIPTION, ButtonText.START_MENU, ButtonText.CANCEL]],
                resize_keyboard=True, is_persistent=True,
            ),
        )
        await update.message.reply_text(
            "📈 Admin Panel - Select report category:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Sales Reports / ሽያጭ መረጃ", callback_data=CallbackData.SALES_REPORTS)],
                [InlineKeyboardButton("📦 Product Reports / ንብረት መረጃ", callback_data=CallbackData.PRODUCT_REPORTS)],
                [InlineKeyboardButton("💰 Credit Report / ዱቤ መረጃ", callback_data=CallbackData.CREDIT_REPORTS)],
                [InlineKeyboardButton("🏦 Bank Transfer / ባንክ መረጃ", callback_data=CallbackData.BANK_TRANSFER)],
                [InlineKeyboardButton("🔔 Report Subscription / ሪፖርት ደንበኝነት", callback_data=CallbackData.REPORT_SUBSCRIPTION)],
                [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)],
            ]),
        )
        return ADMIN_MENU

    if text == ButtonText.START_MENU:
        from telegrambot.handlers.menu_handlers.main_menu import start
        await update.message.reply_text("Returning to main menu...", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)

    if text == ButtonText.CANCEL:
        await update.message.reply_text("Bye! Send /start to restart.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    return await _render(update, context)
