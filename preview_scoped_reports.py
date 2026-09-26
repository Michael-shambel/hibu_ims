#!/usr/bin/env python3
"""
Preview what each report recipient will actually receive — without sending anything.

This is the "pretend it is 18:10" button. It:

  1. copies database/inventory.db to database/_preview_copy.db and points the app at
     the COPY (DATABASE_URL is set before the engine loads), so your real database is
     never touched and nothing is ever queued or sent to Telegram;
  2. prints your Product Groups, Subscribers and Expense tags;
  3. resolves the real recipient list from ReportSubscriptionService;
  4. calls the REAL outbox senders (telegrambot.outbox._send_daily_sales_report /
     _send_profit_report) with a stub bot, and saves every PDF to report_previews/.

Usage (from the project root):

    build_env/Scripts/python.exe preview_scoped_reports.py                 # latest day with sales
    build_env/Scripts/python.exe preview_scoped_reports.py 2026-09-05      # a specific day
    build_env/Scripts/python.exe preview_scoped_reports.py --demo          # copy-only: make the
                                                                           # group/subs demo-ready
    build_env/Scripts/python.exe preview_scoped_reports.py --periods       # + 1/3/6/12-month reports

The 1/3/6/12-month reports walk day by day, so --periods takes a while (the annual one
queries a full Ethiopian year, which is 13 months of daily queries).
"""
import os
import shutil
import sys
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DB = ROOT / 'database' / 'inventory.db'
COPY_DB = ROOT / 'database' / '_preview_copy.db'
OUT_DIR = ROOT / 'report_previews'

if not SRC_DB.exists():
    sys.exit(f"Could not find {SRC_DB}")

# Redirect the whole app at a throwaway copy before anything imports the engine.
shutil.copy2(SRC_DB, COPY_DB)
os.environ['DATABASE_URL'] = 'sqlite:///' + COPY_DB.as_posix()

import asyncio  # noqa: E402

import models  # noqa: F401,E402  (registers models before any query)

from models.new_sales import ProfessionalSale  # noqa: E402
from services.base_service import get_session  # noqa: E402
from services.product_group_service import ProductGroupService  # noqa: E402
from services.report_subscription_service import ReportSubscriptionService  # noqa: E402
from telegrambot.handlers.reports.daily_sales_report import (  # noqa: E402
    daily_report_data,
)
from telegrambot.handlers.menu_handlers.states import ETHIOPIAN_MONTHS  # noqa: E402
from telegrambot.outbox import (  # noqa: E402
    _send_daily_sales_report,
    _send_profit_report,
)
from telegrambot.scheduler import (  # noqa: E402
    _eth_month_bounds,
    _prev_eth_month,
    _shift_eth_month,
)
from ui.components.ethiopian_date import EthiopianDateConverter  # noqa: E402


class StubBot:
    """Bot stand-in that captures what would have been sent."""

    def __init__(self):
        self.messages = []
        self.documents = []

    async def send_message(self, chat_id, text=None, parse_mode=None, **kwargs):
        self.messages.append({'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode})

    async def send_document(self, chat_id, document=None, filename=None, caption=None, **kwargs):
        blob = document.read() if hasattr(document, 'read') else b''
        self.documents.append({'chat_id': chat_id, 'filename': filename,
                               'caption': caption, 'bytes': blob})


def rule(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def latest_sale_date():
    with get_session() as session:
        newest = session.query(ProfessionalSale.created_at).filter(
            ProfessionalSale.is_deleted == False  # noqa: E712
        ).order_by(ProfessionalSale.created_at.desc()).first()
    return newest[0].date() if newest and newest[0] else date.today()


def apply_demo(group_svc, sub_svc, target_date):
    """Copy-only demo setup, so a scoped report has something to show.

    Gives the first product group products that actually sold, tags an expense to
    that group, and makes sure a scoped subscriber exists — all inside the DB copy,
    so your real configuration is untouched. Without it a group of never-sold
    products legitimately renders zeros, which looks like a bug and is not one.
    """
    from models.expense import Expense
    from models.new_sale_item import ProfessionalSaleItem
    from models.new_sales import ProfessionalSale
    from models.product_batch import ProductBatch
    from models.new_product import ProfessionalProduct
    from sqlalchemy import func

    window_start = target_date - timedelta(days=60)
    with get_session() as session:
        top = session.query(
            ProfessionalProduct.id, ProfessionalProduct.name,
            func.count(ProfessionalSaleItem.id).label('units'),
        ).select_from(ProfessionalSaleItem).join(
            ProductBatch, ProfessionalSaleItem.batch_id == ProductBatch.id
        ).join(
            ProfessionalProduct, ProductBatch.product_id == ProfessionalProduct.id
        ).join(
            ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
        ).filter(
            ProfessionalSale.created_at >= window_start,
            ProfessionalSaleItem.is_deleted == False,  # noqa: E712
            ProfessionalSale.is_deleted == False,  # noqa: E712
            ProductBatch.is_deleted == False,  # noqa: E712
            ProfessionalProduct.is_deleted == False,  # noqa: E712
        ).group_by(ProfessionalProduct.id).order_by(func.count(ProfessionalSaleItem.id).desc()).limit(3).all()

    groups = group_svc.list_with_counts()
    if groups:
        group_id = groups[0]['id']
        group_name = groups[0]['name']
    else:
        created = group_svc.create_group('DEMO GROUP', 'created by preview_scoped_reports.py --demo')
        group_id, group_name = created.id, created.name

    if top:
        group_svc.set_members(group_id, [pid for pid, _, _ in top])
        print(f"\n[demo] '{group_name}' now holds the 3 best sellers in 60 days: "
              + ', '.join(f"{name} ({units} units)" for _, name, units in top))
    else:
        print(f"\n[demo] no sales in the last 60 days, leaving '{group_name}' as it is")

    subs = sub_svc.list_subscribers()
    if not any(not s['full_report'] and s['group_ids'] for s in subs):
        created = sub_svc.create_subscriber(
            'DEMO scoped subscriber', 999000111, full_report=False,
            group_ids=[group_id],
            report_types=['daily', 'monthly', 'quarterly', 'semiannual', 'annual'],
            notes='created by preview_scoped_reports.py --demo',
        )
        print(f"[demo] added a scoped subscriber for '{group_name}' "
              f"(chat 999000111, id {created.id if created else 'FAILED'})")

    # Make sure the demo date has at least one expense tagged to the group, so the
    # expense side of the scoped report is exercised too (not just the sales side).
    with get_session() as session:
        on_date = session.query(Expense).filter(
            Expense.product_group_id == group_id,
            Expense.date == target_date,
            Expense.is_deleted == False,  # noqa: E712
        ).first()
        if on_date is not None:
            print(f"[demo] '{group_name}' already has an expense tagged on {target_date}")
        else:
            candidate = session.query(Expense).filter(
                Expense.product_group_id.is_(None),
                Expense.is_deleted == False,  # noqa: E712
                Expense.is_personal == False,  # noqa: E712
            ).order_by(func.abs(func.julianday(Expense.date) - func.julianday(target_date))).first()
            if candidate is None:
                print(f"[demo] no untagged expense to tag for {target_date}")
            else:
                candidate.product_group_id = group_id
                session.commit()
                print(f"[demo] tagged the {candidate.amount:,.2f} expense of "
                      f"{candidate.date} to '{group_name}' (nearest to {target_date})")


def show_config(group_svc, sub_svc):
    rule('1. What is configured')
    groups = group_svc.list_with_counts()
    if not groups:
        print("Product Groups: (none)")
    else:
        print(f"Product Groups ({len(groups)}):")
        for g in groups:
            state = 'active' if g['is_active'] else 'INACTIVE'
            print(f"  #{g['id']:<4} {g['name']:<28} {g['product_count']:>4} products   {state}")

    subs = sub_svc.list_subscribers()
    if not subs:
        print("\nSubscribers: (none — every admin gets the full report)")
    else:
        print(f"\nSubscribers ({len(subs)}):")
        for s in subs:
            scope = 'Full report' if s['full_report'] else (
                ', '.join(s['group_names']) or 'no group -> falls back to FULL report')
            types = ','.join(t for t, key in (
                ('daily', 'receive_daily'), ('1m', 'receive_monthly'),
                ('3m', 'receive_quarterly'), ('6m', 'receive_semiannual'),
                ('1y', 'receive_annual')) if s[key])
            print(f"  #{s['id']:<4} {s['display_name']:<24} chat={s['chat_id']:<14} "
                  f"[{'active' if s['is_active'] else 'INACTIVE'}]")
            print(f"       scope: {scope}")
            print(f"       gets : {types or '(nothing ticked)'}")

    from models.expense import Expense
    from models.product_group import ProductGroup
    with get_session() as session:
        rows = session.query(
            Expense.date, Expense.amount, Expense.description, ProductGroup.name,
        ).outerjoin(
            ProductGroup, Expense.product_group_id == ProductGroup.id
        ).filter(
            Expense.is_deleted == False,  # noqa: E712
            Expense.is_personal == False,  # noqa: E712
        ).order_by(Expense.date.desc()).all()

    tagged = [r for r in rows if r[3]]
    print(f"\nExpenses: {len(rows)} non-personal, {len(tagged)} tagged to a group:")
    for d, amount, desc, gname in rows:
        mark = f"[{gname}]" if gname else '[untagged]'
        print(f"  {d}  {float(amount or 0):>12,.2f}  {mark:<12} {(desc or '')[:40]}")
    if not tagged:
        print("  !! Nothing is tagged yet, so every scoped report will show ZERO expenses.")


def show_recipients(sub_svc, report_type='daily'):
    rule(f"2. Resolved recipients for the '{report_type}' report")
    recipients = sub_svc.get_recipients(report_type)
    if not recipients:
        print("Nobody would receive this report!")
    for r in recipients:
        kind = 'FULL' if r.is_full else f"SCOPED to {r.scope_label}"
        print(f"  chat={r.chat_id:<14} {r.label:<26} [{r.source:<10}] {kind}")
    print(f"\n  total: {len(recipients)} recipient(s), "
          f"{sum(1 for r in recipients if not r.is_full)} scoped")
    return recipients


def show_scope_math(recipients, target_date, days_to_scan=45):
    rule(f"3. What each recipient's numbers would be for {target_date}")
    header = (f"  {'recipient':<26} {'prods':>6} {'sales':>12} {'cost':>12} "
              f"{'expenses':>12} {'net':>12}")
    print(header)
    print('  ' + '-' * (len(header) - 2))
    for r in recipients:
        payload = r.to_payload()
        data = daily_report_data(target_date, payload['product_ids'], payload['group_ids'])
        net = data['total_selling'] - data['total_cost'] - data['expenses']
        print(f"  {r.label[:25]:<26} {len(data['items']):>6} "
              f"{data['total_selling']:>12,.2f} {data['total_cost']:>12,.2f} "
              f"{data['expenses']:>12,.2f} {net:>12,.2f}")

    # A scoped subset is often tiny on a given day; point at other days that are not.
    for r in recipients:
        if r.is_full:
            continue
        payload = r.to_payload()
        recent = []
        for back in range(days_to_scan):
            day = target_date - timedelta(days=back)
            data = daily_report_data(day, payload['product_ids'], payload['group_ids'])
            if data['total_selling'] or data['expenses']:
                recent.append((day, data['total_selling'], data['expenses']))
            if len(recent) == 3:
                break
        if recent and recent[0][0] == target_date:
            others = [row for row in recent if row[0] != target_date]
            if others:
                print(f"\n  {r.label}: other recent days, if you want a different "
                      f"side-by-side:")
                for day, selling, exp in others:
                    print(f"    {day}   sales {selling:>12,.2f}   expenses {exp:>12,.2f}")
        elif recent:
            print(f"\n  {r.label} has NOTHING on {target_date}, but does on these days "
                  f"(re-run with one of them):")
            for day, selling, exp in recent:
                print(f"    {day}   sales {selling:>12,.2f}   expenses {exp:>12,.2f}")
        else:
            print(f"\n  {r.label} has no scoped sales or expenses in the last "
                  f"{days_to_scan} days, including {target_date}.")


async def render_daily(recipients, target_date):
    rule(f"4. Rendered PDFs for {target_date} (real outbox senders, stub bot)")
    for r in recipients:
        bot = StubBot()
        await _send_daily_sales_report(bot, r.chat_id, {
            'target_date': target_date.isoformat(),
            'scope': r.to_payload(),
        }, notif_id=-1)
        for doc in bot.documents:
            path = OUT_DIR / f"{r.source}_{r.chat_id}_{doc['filename']}"
            path.write_bytes(doc['bytes'])
            print(f"\n  -> {path.name}  ({len(doc['bytes']) / 1024:.0f} KB)")
        for msg in bot.messages:
            print('  ' + msg['text'].replace('\n', '\n  '))
        if not bot.documents:
            print(f"\n  !! {r.label}: NO document produced")


def period_ranges():
    """(period_type, label, start, end) for the periods that most recently ended."""
    eth_year, eth_month, _ = EthiopianDateConverter.to_ethiopian(date.today())
    end_y, end_m = _prev_eth_month(eth_year, eth_month)
    _, end = _eth_month_bounds(end_y, end_m)
    out = []
    for period_type, span in (('monthly', 1), ('quarterly', 3),
                              ('semiannual', 6), ('annual', 13)):
        start_y, start_m = _shift_eth_month(end_y, end_m, -(span - 1))
        start = EthiopianDateConverter.to_gregorian(start_y, start_m, 1)
        title = {'monthly': 'Monthly', 'quarterly': 'Quarterly',
                 'semiannual': 'Semi-Annual', 'annual': 'Annual'}[period_type]
        if span == 1:
            label = f"{ETHIOPIAN_MONTHS[end_m - 1][0]} {end_y} / {title} Profit Report"
        else:
            label = (f"{ETHIOPIAN_MONTHS[start_m - 1][0]} - "
                     f"{ETHIOPIAN_MONTHS[end_m - 1][0]} {end_y} / {title} Profit Report")
        out.append((period_type, label, start, end))
    return out


async def render_periods(recipients, period_type, label, start, end, step=5):
    rule(f"{step}. {label}\n   {start} .. {end}  (period_type='{period_type}')")
    for r in recipients:
        bot = StubBot()
        await _send_profit_report(bot, r.chat_id, {
            'period_type': period_type, 'period_label': label,
            'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'scope': r.to_payload(),
        }, notif_id=-1)
        for doc in bot.documents:
            path = OUT_DIR / f"{r.source}_{r.chat_id}_{doc['filename']}"
            path.write_bytes(doc['bytes'])
            print(f"\n  -> {path.name}  ({len(doc['bytes']) / 1024:.0f} KB)")
        for msg in bot.messages:
            print('  ' + msg['text'].replace('\n', '\n  '))


def main():
    args = sys.argv[1:]
    want_periods = '--periods' in args
    date_args = [a for a in args if not a.startswith('-')]
    target_date = date.fromisoformat(date_args[0]) if date_args else latest_sale_date()

    OUT_DIR.mkdir(exist_ok=True)
    group_svc = ProductGroupService()
    sub_svc = ReportSubscriptionService()

    if '--demo' in args:
        apply_demo(group_svc, sub_svc, target_date)

    show_config(group_svc, sub_svc)
    recipients = show_recipients(sub_svc, 'daily')
    if recipients:
        show_scope_math(recipients, target_date)
        asyncio.run(render_daily(recipients, target_date))

    if want_periods:
        for step, (period_type, label, start, end) in enumerate(period_ranges(), start=5):
            rts = sub_svc.get_recipients(period_type)
            if not rts:
                continue
            asyncio.run(render_periods(rts, period_type, label, start, end, step))

    rule('Done')
    print(f"PDFs written to {OUT_DIR}")
    print("Nothing was sent to Telegram and your real database was not modified.")


if __name__ == '__main__':
    main()
