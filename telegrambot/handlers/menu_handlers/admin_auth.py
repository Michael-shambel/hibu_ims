#!/usr/bin/env python3
"""
Admin Authentication Handlers
Handles username/password login for admin users and chat_id registration.
Admins register their Telegram account to receive daily sales reports
and access the admin section of the bot.
"""

import asyncio
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from services.auth_service import AuthService
from telegrambot.handlers.menu_handlers.states import (
    ADMIN_AUTH_USERNAME,
    ADMIN_AUTH_PASSWORD,
    ADMIN_MENU,
    ROLE_ADMIN,
    ROLE_SELECTION,
    CallbackData,
)

logger = logging.getLogger(__name__)


async def check_existing_admin_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if the current chat_id is already registered as an admin.
    Returns True if registered and sets up context, False otherwise.
    """
    chat_id = update.effective_chat.id
    auth_service = AuthService()

    user = await asyncio.to_thread(auth_service.get_by_chat_id, chat_id)

    if user and user.role == 'admin' and not user.is_deleted:
        context.user_data['authenticated_user_id'] = user.id
        context.user_data['authenticated_username'] = user.username
        context.user_data['user_role'] = ROLE_ADMIN
        logger.info("Existing admin registration found for %s with chat_id %s", user.username, chat_id)
        return True

    logger.info("No admin registration for chat_id %s", chat_id)
    return False


async def start_admin_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Initiates admin authentication flow or bypasses if already registered.
    Called when user selects 'Admin' role from callback.
    """
    from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard
    query = update.callback_query
    await query.answer()

    if await check_existing_admin_registration(update, context):
        username = context.user_data.get('authenticated_username', 'Admin')
        keyboard = get_main_keyboard(ROLE_ADMIN)

        await query.edit_message_text(
            f"👨‍💼 Welcome back, {username}!\n\n"
            "You are already registered. Accessing Admin features..."
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Use the keyboard below:",
            reply_markup=keyboard
        )
        return ADMIN_MENU

    # Not registered — start auth flow
    context.user_data['user_role'] = ROLE_ADMIN
    await query.edit_message_text(
        "👨‍💼 Admin Login\n\n"
        "Please enter your *admin username*:",
        parse_mode='Markdown'
    )
    return ADMIN_AUTH_USERNAME


async def ask_admin_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fallback entry for username input (when triggered via message instead of callback).
    """
    from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard

    if await check_existing_admin_registration(update, context):
        username = context.user_data.get('authenticated_username', 'Admin')
        keyboard = get_main_keyboard(ROLE_ADMIN)

        await update.message.reply_text(
            f"👨‍💼 Welcome back, {username}!\n\n"
            "You are already registered. Accessing Admin features...",
            reply_markup=keyboard
        )
        return ADMIN_MENU

    await update.message.reply_text(
        "👨‍💼 Admin Login\n\n"
        "Please enter your *admin username*:",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return ADMIN_AUTH_USERNAME


async def receive_admin_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store username and prompt for password."""
    username = update.message.text.strip()
    context.user_data['admin_username'] = username

    await update.message.reply_text(
        f"Username: `{username}`\n\nNow enter your *admin password*:",
        parse_mode='Markdown'
    )
    return ADMIN_AUTH_PASSWORD


async def receive_admin_password_authenticate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Authenticate admin credentials and register chat_id.
    On success: transition to admin menu.
    On failure: end conversation.
    """
    from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard

    password = update.message.text.strip()
    username = context.user_data.get('admin_username')
    chat_id = update.effective_chat.id

    if not username:
        await update.message.reply_text(
            "⚠️ Session expired. Please send /start to try again.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    auth_service = AuthService()

    # DB write off the event loop — authentication + chat_id registration
    user = await asyncio.to_thread(
        auth_service.register_chat_id_safe, username, password, chat_id
    )

    if user and user.role == 'admin':
        context.user_data['authenticated_user_id'] = user.id
        context.user_data['authenticated_username'] = user.username
        context.user_data['user_role'] = ROLE_ADMIN

        keyboard = get_main_keyboard(ROLE_ADMIN)
        await update.message.reply_text(
            f"✅ Admin login successful!\n\n"
            f"Welcome, {user.username}.\n"
            "You now have full admin access.\n\n"
            "Use the keyboard below:",
            reply_markup=keyboard
        )
        return ADMIN_MENU
    else:
        await update.message.reply_text(
            "❌ Authentication failed. Please check your admin credentials.\n\n"
            "Send /start to try again.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles interactions within the admin main menu.
    """
    if update.message:
        from telegrambot.handlers.menu_handlers.main_menu import handle_persistent_buttons
        return await handle_persistent_buttons(update, context)

    return ADMIN_MENU
