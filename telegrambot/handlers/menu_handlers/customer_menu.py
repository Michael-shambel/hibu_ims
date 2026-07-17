# customer_menu.py

import asyncio
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from services.customer_service import CustomerService
from telegrambot.handlers.menu_handlers.states import (
    ConversationStates, CallbackData, ButtonText, ROLE_CUSTOMER
)
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard
from telegrambot.handlers.reports.customer_credit_reports import generate_customer_credit_items_pdf, generate_customer_payment_history_pdf
from services.new_sale_service import NewSaleService
import io
from telegrambot.handlers.menu_handlers.main_menu import get_main_keyboard, start

logger = logging.getLogger(__name__)
customer_service = CustomerService()

async def start_customer_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    
    # Clear any previous data
    context.user_data.clear()
    
    # Check if this chat_id is already linked to a customer
    existing_customer = customer_service.get_by_chat_id(chat_id)
    
    if existing_customer:
        # Customer already registered - show menu directly
        context.user_data['customer_id'] = existing_customer.id
        context.user_data['customer_phone'] = existing_customer.phone
        context.user_data['customer_name'] = existing_customer.name
        context.user_data['user_role'] = ROLE_CUSTOMER
        
        # Set persistent keyboard
        await query.edit_message_text(
            f"✅ Welcome back **{existing_customer.name}\nእንኳን ደህና መጣችሁ!**!\n\n"
            "Your Telegram is already linked to your customer account.\n ቴሌግራም አካውንቶ ከስይስተማችን ጋር ተያይዟል።",
            parse_mode='Markdown'
        )
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="📋 *የደንበኛ ማውጫ\nCustomer Menu*\n\nPlease choose an option:\nእባኮ ፍላጎቶን ይምርጡ",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(ROLE_CUSTOMER)
        )
        
        # Show customer menu with two buttons
        keyboard = [
            [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.CUSTOMER_CREDIT_ITEMS)],
            [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.CUSTOMER_CREDIT_PAYMENTS)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="📋 *የደንበኛ ማውጫ\nCustomer Menu*\n\nPlease choose an option:\nእባኮ ፍላጎቶን ይምርጡ",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ConversationStates.CUSTOMER_MENU_MAIN
    
    else:
        # New customer - ask for phone number
        context.user_data['auth_role'] = 'customer'
        await query.edit_message_text(
            "📞 *አዲስ ደንበኛ ምዝግባ\nNew Customer Registration*\n\n"
            "እባኮ የደንበኝነት ስልክ ቁጥሮን ይላኩ\nPlease enter your registered phone number.\n"
            "ምሳሌ (Example): 0912345678\n\n"
            "ችግር ካጋጠሞ ደውለው ያነጋግሩን.\n"
            "ለማቋረጥ /cancel ይንኩ።\nType /cancel to abort.",
            parse_mode='Markdown'
        )
        return ConversationStates.CUSTOMER_AUTH_PHONE

async def receive_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receive phone number, validate, and attempt to register chat_id.
    """
    text = update.message.text.strip()
    if text == ButtonText.CANCEL:
        await update.message.reply_text(
            "❌ ምዝገባው ተቋርጧል። እንደገና ለመጀመር /start ይንኩ።\nRegistration cancelled. Send /start to begin again.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    elif text == ButtonText.START_MENU:
        await update.message.reply_text("Returning to main menu...\n ወደ ዋናው ማውጫ እየተመለሰ...", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)
    phone = update.message.text.strip()
    chat_id = update.effective_chat.id
    
    # Basic validation (Ethiopian phone format example)
    if not phone.isdigit() or len(phone) < 9:
        await update.message.reply_text(
            "❌ የተሳሳተ ስልክ ቁጥር። ትክክልኛ ስልክ ቁጥር ያስገቡ (ምሳሌ፡ 0911223344)\nInvalid phone number. Please enter a valid number (digits only, e.g., 0912345678).\n"
            "ለማቋረጥ /cancel ይንኩ።\nSend /cancel to stop."
        )
        return ConversationStates.CUSTOMER_AUTH_PHONE
    
    # Try to register
    customer = customer_service.register_chat_id(phone, chat_id)
    
    if customer:
        # Success – store customer info in context for later use
        context.user_data['customer_id'] = customer.id
        context.user_data['customer_phone'] = customer.phone
        context.user_data['customer_name'] = customer.name
        context.user_data['user_role'] = ROLE_CUSTOMER
        
        # Show success message with persistent keyboard
        await update.message.reply_text(
            f"✅ ተጠናቋል። ቴሌግራሞ ከኛ ሲስተም ጋር ተገናኝቷል፡፡ መረጃዎችን መግኘት ይችላሉ\nSuccess! Your Telegram is now linked to customer **{customer.name}**.\n",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(ROLE_CUSTOMER)
        )
        
        # Show customer menu with two buttons
        keyboard = [
            [InlineKeyboardButton("📦 Credit Item History/የዱቤ ", callback_data=CallbackData.CUSTOMER_CREDIT_ITEMS)],
            [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.CUSTOMER_CREDIT_PAYMENTS)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📋 *የደንበኛ ማውጫ\nCustomer Menu*\n\nPlease choose an option:\nእባኮ ፍላጎቶን ይምርጡ",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ConversationStates.CUSTOMER_MENU_MAIN
    else:
        # Registration failed
        await update.message.reply_text(
            "❌ ምዝገባው አልተከናወነም።\nRegistration failed.\n\n"
            "ተገማች ምክያቶች\nPossible reasons:\n"
            "ስልክ ቁጥሮ ሲስተም ላይ አልተመዘገበም\n- Phone number not found in our system.\n"
            # "- This phone number is already linked to another Telegram account.\n"
            "ከዚህ በፊት በሌላ ቴሌግራም ተመዝግበዋል\n- Your account already has a different chat_id (cannot change).\n\n"
            "ባለቤቱን ያናግሩ\nPlease contact support or try again with a different number.\n"
            "ከደገና ለማስጀመር /start ይንኩ።\nSend /start to restart."
        )
        return ConversationHandler.END

async def customer_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle callback queries from customer menu buttons.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Get customer info from context
    customer_name = context.user_data.get('customer_name', 'Customer')
    customer_id = context.user_data.get('customer_id')
    
    if not customer_id:
        # Try to recover by checking chat_id
        chat_id = update.effective_chat.id
        customer = customer_service.get_by_chat_id(chat_id)
        
        if customer:
            # Recovered customer data
            context.user_data['customer_id'] = customer.id
            context.user_data['customer_phone'] = customer.phone
            context.user_data['customer_name'] = customer.name
            context.user_data['user_role'] = ROLE_CUSTOMER
            customer_name = customer.name
            customer_id = customer.id
        else:
            await query.edit_message_text(
                "❌ Session expired. Please send /start to begin again."
            )
            return ConversationHandler.END
    
    if data == CallbackData.CUSTOMER_CREDIT_ITEMS:
        await query.edit_message_text("📄 በዱቤ የወሰዱትን እቃዎች በማውጣት ላይ.....እባክዎ ትንሽ ይጠብቁ። \nGenerating your credit item history report... Please wait.")
        
        try:
            sale_service = NewSaleService()
            groups = await asyncio.to_thread(sale_service.get_customer_credit_sales_grouped, customer_id)
            
            if not groups:
                await query.edit_message_text("📭 You have no credit purchases.")
                # Re-show menu
                keyboard = [
                    [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.CUSTOMER_CREDIT_ITEMS)],
                    [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.CUSTOMER_CREDIT_PAYMENTS)],
                    [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
                ]
                await query.message.reply_text(
                     "📋 *የደንበኛ ማውጫ\nCustomer Menu*\n\nPlease choose an option:\nእባኮ ፍላጎቶን ይምርጡ",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return ConversationStates.CUSTOMER_MENU_MAIN
            
            pdf_bytes = await asyncio.to_thread(
                generate_customer_credit_items_pdf, customer_name, groups
            )
            
            # Send PDF
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=io.BytesIO(pdf_bytes),
                filename=f"credit_items_{customer_name}.pdf",
                caption=f"📦 Credit Item History for {customer_name}"
            )
            
            # After sending, show menu again
            keyboard = [
                [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.CUSTOMER_CREDIT_ITEMS)],
                [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.CUSTOMER_CREDIT_PAYMENTS)],
                [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
            ]
            await query.message.reply_text(
                 "📋 *የደንበኛ ማውጫ\nCustomer Menu*\n\nPlease choose an option:\nእባኮ ፍላጎቶን ይምርጡ",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationStates.CUSTOMER_MENU_MAIN
            
        except Exception as e:
            logger.error(f"Error generating credit items PDF: {e}")
            await query.edit_message_text("❌ Failed to generate report. Please try again later.")
            # Re-show menu
            keyboard = [
                [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.CUSTOMER_CREDIT_ITEMS)],
                [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.CUSTOMER_CREDIT_PAYMENTS)],
                [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
            ]
            await query.message.reply_text(
                 "📋 *የደንበኛ ማውጫ\nCustomer Menu*\n\nPlease choose an option:\nእባኮ ፍላጎቶን ይምርጡ",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationStates.CUSTOMER_MENU_MAIN
    
    elif data == CallbackData.CUSTOMER_CREDIT_PAYMENTS:
        await query.edit_message_text("📄 በዱቤ የወሰዱትን እቃዎች ክፍያ በማውጣት ላይ.....እባክዎ ትንሽ ይጠብቁ። \nGenerating your credit item history report... Please wait.")
        
        try:
            sale_service = NewSaleService()
            payments = await asyncio.to_thread(sale_service.get_customer_combined_history, customer_id)


            if not payments:
                await query.edit_message_text("📭 You have no payment transactions.")
            else:
                total_credit = sum(tx['amount'] for tx in payments if tx['type'] == 'credit_sale')
                total_debit = sum(-tx['amount'] for tx in payments if tx['type'] == 'payment')
                closing = payments[-1]['balance_after'] if payments else 0.0
                pdf_bytes = await asyncio.to_thread(
                    generate_customer_payment_history_pdf,
                    customer_name=customer_name,
                    transactions=payments,
                    total_credit=total_credit,
                    total_debit=total_debit,
                    current_balance=closing,
                )
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=io.BytesIO(pdf_bytes),
                    filename=f"payment_history_{customer_name}.pdf",
                    caption=f"💰 Payment History for {customer_name}"
                )
        except Exception as e:
            logger.error(f"Error generating payment history PDF: {e}")
            await query.edit_message_text("❌ Failed to generate report. Please try again later.")

        # Re‑show the customer menu after PDF is sent (or on error)
        keyboard = [
            [InlineKeyboardButton("📦 Credit Item History", callback_data=CallbackData.CUSTOMER_CREDIT_ITEMS)],
            [InlineKeyboardButton("💰 Credit Payment History", callback_data=CallbackData.CUSTOMER_CREDIT_PAYMENTS)],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.CANCEL)]
        ]
        await query.message.reply_text(
            "📋 *Customer Menu*\n\nSelect another option:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationStates.CUSTOMER_MENU_MAIN

    
    elif data == CallbackData.CANCEL:
        await query.edit_message_text(
            "❌ Cancelled. Send /start to begin again.",
            reply_markup=None
        )
        return ConversationHandler.END
    
    else:
        await query.edit_message_text(
            "❌ Unknown option. Please use the buttons below."
        )
        return ConversationStates.CUSTOMER_MENU_MAIN