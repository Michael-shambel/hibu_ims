#!/usr/bin/env python3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import BOT_TOKEN

async def group_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporary command to get group ID"""
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title or "Private Chat"
    
    await update.message.reply_text(
        f"📋 Chat Information:\n"
        f"Title: {chat_title}\n"
        f"ID: `{chat_id}`\n"
        f"Type: {update.effective_chat.type}",
        parse_mode='Markdown'
    )

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("groupid", group_id_command))
    
    print("🤖 Bot is running... Use /groupid in your group to get the ID")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())