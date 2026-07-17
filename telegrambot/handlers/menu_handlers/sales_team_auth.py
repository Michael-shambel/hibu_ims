#!/usr/bin/env python3
"""
Sales Team Authentication Handlers
Handles username/password login for store team members and chat_id registration.
"""

import asyncio
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from services.auth_service import AuthService
from telegrambot.handlers.menu_handlers.states import (
    SALES_TEAM_AUTH_USERNAME,
    SALES_TEAM_AUTH_PASSWORD,
    SALES_TEAM_MENU_MAIN,
    ROLE_SALES_TEAM
)

logger = logging.getLogger(__name__)


async def check_existing_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if the current chat_id is already registered.
    Returns True if registered and sets up context, False otherwise.
    """
    chat_id = update.effective_chat.id
    auth_service = AuthService()

    # DB call off the event loop
    user = await asyncio.to_thread(auth_service.get_by_chat_id, chat_id)

    logger.info("DEBUG: chat_id=%s, user=%s, role=%s", chat_id, user, user.role if user else 'N/A')

    if user and user.role in ('sales_team', 'admin', 'sales_clerk'):
        context.user_data['authenticated_user_id'] = user.id
        context.user_data['authenticated_username'] = user.username
        context.user_data['user_role'] = ROLE_SALES_TEAM
        logger.info("Existing registration found for %s with chat_id %s", user.username, chat_id)
        return True

    logger.info("No existing registration for chat_id %s", chat_id)
    return False


async def start_sales_team_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Initiates sales team authentication flow or bypasses if already registered.
    Called when user selects 'Store Team' role from callback.
    """
    from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard
    query = update.callback_query
    await query.answer()

    if await check_existing_registration(update, context):
        username = context.user_data.get('authenticated_username', 'User')
        keyboard = get_main_keyboard(ROLE_SALES_TEAM)

        await query.edit_message_text(
            f"👔 Welcome back, {username}!\n\n"
            "You are already registered. Accessing Store Team features..."
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Use the keyboard below:",
            reply_markup=keyboard
        )
        return SALES_TEAM_MENU_MAIN

    # Not registered — start auth flow
    context.user_data['user_role'] = ROLE_SALES_TEAM
    await query.edit_message_text(
        "👔 Store Team Login\n\nPlease enter your *username*:",
        parse_mode='Markdown'
    )
    return SALES_TEAM_AUTH_USERNAME


async def ask_sales_team_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fallback entry for username input (when triggered via message instead of callback).
    """
    from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard

    if await check_existing_registration(update, context):
        username = context.user_data.get('authenticated_username', 'User')
        keyboard = get_main_keyboard(ROLE_SALES_TEAM)

        await update.message.reply_text(
            f"👔 Welcome back, {username}!\n\n"
            "You are already registered. Accessing Store Team features...",
            reply_markup=keyboard
        )
        return SALES_TEAM_MENU_MAIN

    await update.message.reply_text(
        "👔 Store Team Login\n\nPlease enter your *username*:",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return SALES_TEAM_AUTH_USERNAME


async def receive_username_ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store username and prompt for password."""
    username = update.message.text.strip()
    context.user_data['sales_team_username'] = username

    await update.message.reply_text(
        f"Username: `{username}`\n\nNow enter your *password*:",
        parse_mode='Markdown'
    )
    return SALES_TEAM_AUTH_PASSWORD


async def receive_password_authenticate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Authenticate credentials and register chat_id.
    On success: transition to sales team main menu.
    On failure: end conversation.
    """
    from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard

    password = update.message.text.strip()
    username = context.user_data.get('sales_team_username')
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

    if user:
        context.user_data['authenticated_user_id'] = user.id
        context.user_data['authenticated_username'] = user.username
        context.user_data['user_role'] = ROLE_SALES_TEAM

        keyboard = get_main_keyboard(ROLE_SALES_TEAM)
        await update.message.reply_text(
            f"✅ Login successful!\n\nWelcome, {user.username}.\n"
            "You now have access to Store Team features.\n\n"
            "Use the keyboard below:",
            reply_markup=keyboard
        )
        return SALES_TEAM_MENU_MAIN
    else:
        await update.message.reply_text(
            "❌ Authentication failed. Please check your username and password.\n\n"
            "Send /start to try again.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END


async def sales_team_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles interactions within the sales team main menu.
    """
    if update.message:
        from telegrambot.handlers.menu_handlers.main_menu import handle_persistent_buttons
        return await handle_persistent_buttons(update, context)

    return SALES_TEAM_MENU_MAIN