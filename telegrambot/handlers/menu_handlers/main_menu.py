from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from config import ADMIN_ID
from telegrambot.handlers.menu_handlers.states import (
    ROLE_SELECTION, ADMIN_MENU, TRANSACTION_REPORTS_MENU, SALES_TEAM_AUTH_USERNAME,
    ROLE_ADMIN, ROLE_SALES_TEAM, ROLE_SUPPLIER, ROLE_CUSTOMER,
    CallbackData, ButtonText
)
from telegrambot.handlers.menu_handlers.sales_team_auth import start_sales_team_auth
import logging

logger = logging.getLogger(__name__)

def get_main_keyboard(role=ROLE_CUSTOMER):
    """Get persistent keyboard based on user role"""
    if role == ROLE_ADMIN:
        return ReplyKeyboardMarkup([
            [ButtonText.SALES_REPORTS, ButtonText.PRODUCT_REPORTS],
            [ButtonText.CREDIT_REPORT, ButtonText.BANK_TRANSFER],
            [ButtonText.START_MENU, ButtonText.CANCEL]
        ], resize_keyboard=True, is_persistent=True)
    elif role == ROLE_SALES_TEAM:
        return ReplyKeyboardMarkup([
            ["📊 Team Performance", "👥 Team Members"],
            ["📈 Sales Analytics", "🔧 Tools"],
            [ButtonText.START_MENU, ButtonText.CANCEL]
        ], resize_keyboard=True, is_persistent=True)
    else:
        return ReplyKeyboardMarkup([
            [ButtonText.START_MENU, ButtonText.CANCEL]
        ], resize_keyboard=True, is_persistent=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # context.user_data.clear()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👋 Welcome! Use the keyboard below or select your role:\n እንኳን ደህና መጣችሁ!",
        reply_markup=get_main_keyboard()
    )
    keyboard = [
        [InlineKeyboardButton("👨‍💼 Admin/ባለቤት", callback_data=CallbackData.ROLE_ADMIN)],
        [InlineKeyboardButton("👔 Store Team/መጋዘን", callback_data=CallbackData.ROLE_SALES_TEAM)],
        [InlineKeyboardButton("👤 Supplier/አቅራቢ", callback_data=CallbackData.ROLE_SUPPLIER)],
        [InlineKeyboardButton("👥 Customer/ደንበኛ", callback_data=CallbackData.ROLE_CUSTOMER)],
        [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if update.message:
            await update.message.reply_text("🔐 Select your role:\n ማንነትዎን ይምረጡ", reply_markup=reply_markup)
        else:
            await update.callback_query.edit_message_text(
                text="🔐 Select your role:\n ማንነትዎን ይምረጡ",
                reply_markup=reply_markup
            )
    except Exception:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔐 Select your role:\n ማንነትዎን ይምረጡ",
            reply_markup=reply_markup
        )

    return ROLE_SELECTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation and reset state"""
    user_role = context.user_data.get('user_role')
    context.user_data.clear()
    
    if user_role == ROLE_ADMIN:
        keyboard = get_main_keyboard(ROLE_ADMIN)
        message = "✅ Operation cancelled. Use keyboard buttons or '🔄 Start Menu'.\n ስራዎች ተቋርጠዋል። እንደገና ለማስጀመር '🔄 Start Menu' ይጠቀሙ ወይም -> /start አንድ ጊዜ ይንኩ። "
    elif user_role == ROLE_SALES_TEAM:
        keyboard = get_main_keyboard(ROLE_SALES_TEAM)
        message = "✅ Operation cancelled. Use keyboard buttons or '🔄 Start Menu'.\n ስራዎች ተቋርጠዋል። እንደገና ለማስጀመር '🔄 Start Menu' ይጠቀሙ ወይም -> /start አንድ ጊዜ ይንኩ።"
    else:
        keyboard = get_main_keyboard()
        message = "✅ Operation cancelled. Click '🔄 Start Menu' to begin again.\n ስራዎች ተቋርጠዋል። እንደገና ለማስጀመር '🔄 Start Menu' ይጠቀሙ ወይም -> /start አንድ ጊዜ ይንኩ።"
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message,
        reply_markup=keyboard
    )
    return ConversationHandler.END

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        data = query.data

        if update.effective_user.id != ADMIN_ID:
            await query.edit_message_text("❌ Unauthorized access/❌ ያልተፈቀደ ጥያቄ፡፡")
            return ConversationHandler.END
        
        if data == CallbackData.SALES_REPORTS:
            from telegrambot.handlers.menu_handlers.sales_menu import sales_reports_menu
            return await sales_reports_menu(update, context)
        elif data == CallbackData.PRODUCT_REPORTS:
            from telegrambot.handlers.menu_handlers.product_menu import product_reports_menu
            return await product_reports_menu(update, context)
        elif data == CallbackData.CREDIT_REPORTS:
            from telegrambot.handlers.menu_handlers.credit_menu import credit_reports_menu
            return await credit_reports_menu(update, context)
        elif data == CallbackData.BANK_TRANSFER:
            from telegrambot.handlers.menu_handlers.bank_menu import bank_menu_handler
            return await bank_menu_handler(update, context)
        elif data == CallbackData.EXPENSE_REPORT:
            from telegrambot.handlers.menu_handlers.expense_menu import expense_menu_entry
            return await expense_menu_entry(update, context)  # <-- was expense_menu_handler
        elif data == CallbackData.CANCEL:
            await query.edit_message_text("❌ Cancelled. Send /start to begin again.\n ተቋርጧል። እንደገና ለማስጀመር /start ይንኩ።")
            return ConversationHandler.END
        else:
            await query.edit_message_text("❌ Unknown option.\n ያልታወቀ ጥያቄ።")
        return ADMIN_MENU
    
    elif update.message:
        if update.message is None:
            return
        text = update.message.text.strip()
        user_role = context.user_data.get('user_role')
        if user_role is None:
            user_role = recover_user_role(context, update.effective_user.id)

        if text == ButtonText.START_MENU:
            await update.message.reply_text("Returning to main menu...\n ወደ ዋናው ማውጫ እየተመለሰ...", reply_markup=ReplyKeyboardRemove())
            return await start(update, context)
        elif text == ButtonText.CANCEL:
            await update.message.reply_text("Bye! Send /start to restart.\n ቻው! እንደገና ለማስጀመር /start ይንኩ።", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        elif user_role == ROLE_ADMIN:
            if text == ButtonText.SALES_REPORTS:
                from telegrambot.handlers.menu_handlers.sales_menu import sales_reports_menu
                return await sales_reports_menu(update, context)
            elif text == ButtonText.PRODUCT_REPORTS:   # Add this block
                from telegrambot.handlers.menu_handlers.product_menu import product_reports_menu
                return await product_reports_menu(update, context)
            elif text == ButtonText.CREDIT_REPORT:  # Add this block
                from telegrambot.handlers.menu_handlers.credit_menu import credit_reports_menu
                return await credit_reports_menu(update, context)
            elif text == ButtonText.BANK_TRANSFER:
                from telegrambot.handlers.menu_handlers.bank_menu import bank_menu_handler
                return await bank_menu_handler(update, context)
            elif text == ButtonText.BACK_TO_ADMIN:
                # Already in admin menu, but if user typed it manually
                await update.message.reply_text(
                    "Returning to Admin Panel...\n ወደ ዋናው ማውጫ እየተመለሰ...",
                    reply_markup=get_main_keyboard(ROLE_ADMIN)
                )
                keyboard = [
                    [InlineKeyboardButton("📊 Sales Reports", callback_data=CallbackData.SALES_REPORTS)],
                    [InlineKeyboardButton("📦 Product Reports", callback_data=CallbackData.PRODUCT_REPORTS)],
                    [InlineKeyboardButton("💰 Credit Report", callback_data=CallbackData.CREDIT_REPORTS)],
                    [InlineKeyboardButton("🏦 Bank Transfer", callback_data=CallbackData.BANK_TRANSFER)],
                    [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
                ]
                await update.message.reply_text(
                    "📈 Admin Panel - Select report category:\n የባለቤት ማቅጫ _ የሚፈልጉትን ሪፖርት አይነት ይምረጡ፤",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return ADMIN_MENU
        else:
            # Non-admin user
            await update.message.reply_text(
                f"You clicked: {text}\n\nPlease use the start menu.",
                reply_markup=get_main_keyboard()
            )
            return ADMIN_MENU
    return ADMIN_MENU

async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CallbackData.ROLE_ADMIN:
        if update.effective_user.id != ADMIN_ID:
            await query.edit_message_text(
                "❌ Unauthorized access/ያልተፈቀደ.\n\n"
                "❌መግባት ክልክል ነው፡፡\n",
                parse_mode='Markdown'
            )
            keyboard = [
                [InlineKeyboardButton("👨‍💼 Admin/ባለቤት", callback_data=CallbackData.ROLE_ADMIN)],
                [InlineKeyboardButton("👔 Store Team/መጋዘን", callback_data=CallbackData.ROLE_SALES_TEAM)],
                [InlineKeyboardButton("👤 Supplier/አቅራቢ", callback_data=CallbackData.ROLE_SUPPLIER)],
                [InlineKeyboardButton("👥 Customer/ደንበኛ", callback_data=CallbackData.ROLE_CUSTOMER)],
                [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
            ]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔐 Please select your role:\n ማንነትዎን ይምረጡ",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ROLE_SELECTION 

        context.user_data['user_role'] = ROLE_ADMIN

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🛠 Admin keyboard activated. Use the buttons below.\n የባለቤት ማቅጫ _ የሚፈልጉትን ሪፖርት አይነት ይምረጡ፤",
            reply_markup=get_main_keyboard(ROLE_ADMIN)
        )
        keyboard = [
            [InlineKeyboardButton("📊 Sales Reports / ሽያጭ መረጃ", callback_data=CallbackData.SALES_REPORTS)],
            [InlineKeyboardButton("📦 Product Reports / ንብረት መረጃ", callback_data=CallbackData.PRODUCT_REPORTS)],
            [InlineKeyboardButton("💰 Credit Report / ዱቤ መረጃ", callback_data=CallbackData.CREDIT_REPORTS)],
            [InlineKeyboardButton("🏦 Bank Transfer / ባንክ መረጃ", callback_data=CallbackData.BANK_TRANSFER)],
            [InlineKeyboardButton("💸 Expense Report / ወጪ ሪፖርት", callback_data=CallbackData.EXPENSE_REPORT)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📈 Admin Panel - Select report category:\n የባለቤት ማቅጫ _ የሚፈልጉትን ሪፖርት አይነት ይምረጡ፤",
            reply_markup=reply_markup
        )
        return ADMIN_MENU

    elif data == CallbackData.ROLE_SALES_TEAM:
        return await start_sales_team_auth(update, context)
    
    # In main_menu.py, inside handle_role_selection

    elif data == CallbackData.ROLE_CUSTOMER:
        from telegrambot.handlers.menu_handlers.customer_menu import start_customer_auth
        return await start_customer_auth(update, context)
    
    elif data == CallbackData.ROLE_SUPPLIER:
        from telegrambot.handlers.menu_handlers.supplier_menu import start_supplier_auth
        return await start_supplier_auth(update, context)

    elif data == CallbackData.CANCEL:
        await query.edit_message_text("❌ Cancelled. Send /start to begin again.\n ተቋርጧል። እንደገና ለማስጀመር /start ይንኩ።")
        return ConversationHandler.END

    else:
        await query.edit_message_text(
            f"⚠️ Role '{data}' is not implemented yet. Only Admin is available for now.\nSend /start to try again."
        )
        return ConversationHandler.END

def recover_user_role(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Recover user role from database if missing in context"""
    try:
        if user_id == ADMIN_ID:
            context.user_data['user_role'] = ROLE_ADMIN
            return ROLE_ADMIN
        return None
    except Exception as e:
        logger.error(f"❌ Failed to recover user role: {e}")
        return None

async def handle_persistent_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == ButtonText.START_MENU:
        await update.message.reply_text("Returning to main menu...\n ወደ ዋናው ማውጫ እየተመለሰ...", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return  await start(update, context)
    
    elif text == ButtonText.CANCEL:
        await update.message.reply_text("Bye! Send /start to restart.\n ቻው! እንደገና ለማስጀመር /start ይንኩ።", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    elif text == ButtonText.BACK_TO_ADMIN:
        # Check if user is admin
        user_role = context.user_data.get('user_role')
        if user_role == ROLE_ADMIN:
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
                [InlineKeyboardButton("💸 Expense Report / ወጪ ሪፖርት", callback_data=CallbackData.EXPENSE_REPORT)],
                [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "📈 Admin Panel - Select report category:\n የባለቤት ማቅጫ _ የሚፈልጉትን ሪፖርት አይነት ይምረጡ፤",
                reply_markup=reply_markup
            )
            return ADMIN_MENU
        else:
            await update.message.reply_text("You don't have admin access.")
            return None
    
    else:
        # Unknown input – politely remind user to use provided buttons
        await update.message.reply_text("Please use the inline buttons or the persistent menu below to proceed.")
        return None 

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 Your Chat ID(የእርሶ መለያ ቁጥር): `{chat_id}`\n\nወደ ሲስተሙ እንዲጨመሩ እባኮ ይሄንን ቁጥር ወደ አስተዳደር ይላኩ፡፡",
        parse_mode='Markdown'
    )