# telegrambot/handlers/reports/sales_report.py
"""
Back-dated daily sales & profit report, requested from the bot by an admin:

    Admin -> Sales Reports -> Sales Transactions -> Ethiopian month -> day

It renders exactly the report the bot sends automatically at 18:10 (same data,
same summary, same product breakdown, same caption/filename) by going through
telegrambot/handlers/reports/daily_sales_report.py.
"""
import asyncio
import io
import logging
from datetime import date

from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS
from telegrambot.handlers.reports.daily_sales_report import (
    daily_report_data,
    daily_report_caption,
    daily_report_pdf,
    daily_report_filename,
)

logger = logging.getLogger(__name__)


async def sales_transaction_report_handler(
    update, context,
    eth_year: int, eth_month: int, eth_day: int, greg_date: date
):
    """Send the daily sales & profit report for a back-dated day."""
    from telegrambot.handlers.menu_handlers.sales_menu import sales_reports_menu

    await update.message.reply_text(
        f"⏳ Generating report for {ETHIOPIAN_MONTHS[eth_month - 1][0]} {eth_day}, {eth_year} "
        f"(Gregorian: {greg_date.isoformat()})..."
    )

    try:
        # DB work and PDF rendering both off the event loop
        data = await asyncio.to_thread(daily_report_data, greg_date)
        pdf_bytes = await asyncio.to_thread(daily_report_pdf, data, greg_date)

        await update.message.reply_text(
            daily_report_caption(data, greg_date),
            parse_mode='Markdown'
        )
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=daily_report_filename(greg_date),
            caption=f"📄 {daily_report_filename(greg_date)}",
        )

    except Exception as e:
        logger.exception("Failed to generate sales PDF")
        await update.message.reply_text(f"❌ Failed to generate report: {str(e)}")

    return await sales_reports_menu(update, context)
