#!/usr/bin/env python3
"""
Daily Sales & Profit Report — single source of truth.

Two places render this report:

1. the scheduled 18:10 send to every admin (telegrambot/scheduler.py ->
   telegrambot/outbox.py::_send_daily_sales_report), and
2. the admin's on-demand back-dated flow in the bot
   (Sales Reports -> Sales Transactions -> Ethiopian month -> day ->
   telegrambot/handlers/reports/sales_report.py).

Both go through this module, so the report an admin asks for by date is always
byte-for-byte the same report the bot sends automatically.
"""
from datetime import date

from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS
from telegrambot.handlers.reports.profit_report import (
    build_daily_profit_data,
    generate_daily_profit_pdf,
)
from ui.components.ethiopian_date import EthiopianDateConverter


def daily_report_data(target_date: date) -> dict:
    """Summary + per-product breakdown rows for one Gregorian day."""
    return build_daily_profit_data(target_date)


def daily_report_caption(data: dict, target_date: date) -> str:
    """Markdown caption the daily report is sent with."""
    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(target_date)
    net = data['total_selling'] - data['total_cost'] - data['expenses']
    margin = (net / data['total_selling'] * 100) if data['total_selling'] > 0 else 0.0
    return (
        f"📊 *Daily Sales & Profit Report*\n"
        f"📅 {ETHIOPIAN_MONTHS[eth_month - 1][0]} {eth_day}, {eth_year} "
        f"(Gregorian: {target_date})\n"
        f"💰 Total Sales: ETB {data['total_selling']:,.2f}\n"
        f"📦 Total Cost: ETB {data['total_cost']:,.2f}\n"
        f"💸 Expenses: ETB {data['expenses']:,.2f}\n"
        f"✅ Net Profit: ETB {net:,.2f} ({margin:.1f}%)"
    )


def daily_report_pdf(data: dict, target_date: date) -> bytes:
    """Landscape A4 PDF for one Gregorian day."""
    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(target_date)
    return generate_daily_profit_pdf(
        data['total_selling'], data['total_cost'], data['expenses'],
        data['items'], eth_year, eth_month, eth_day, target_date,
    )


def daily_report_filename(target_date: date) -> str:
    return f"daily_profit_{target_date}.pdf"
