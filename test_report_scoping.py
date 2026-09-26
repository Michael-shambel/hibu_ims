#!/usr/bin/env python3
"""
Product specific report scoping — self-contained checks.

Runs against a throwaway database file (DATABASE_URL is forced before anything
imports the engine), so it never touches the real inventory.db. Run it from the
project root:

    build_env/Scripts/python.exe test_report_scoping.py

Covers:
  * product group CRUD and member resolution
  * recipient merge (scoped subscribers + admins with no subscription row)
  * product-filtered sales/cost/profit/quantity queries
  * expense filtering by product-group tag + bulk tagging
  * multi-group union (a product in two groups counted once)
  * empty-scope safety (never silently falls back to the full report)
  * dedup key + payload round-trip
  * PDF + caption rendering for scoped and unscoped reports
  * the expenses.product_group_id migration helper
"""
import os
import sys
from datetime import date, datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# A file DB (not :memory:) because the outbox senders run their queries on a
# worker thread and an in-memory SQLite connection is per-thread.
TEST_DB_PATH = os.path.join('database', '_scoping_test.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + TEST_DB_PATH.replace('\\', '/')
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

import models  # noqa: F401  (registers the package's models before create_all)
# models/__init__.py does not import every module (the app pulls the rest in via
# its service layer), so register the stragglers explicitly before create_all.
import models.supplier  # noqa: F401

from models.engine.database import db, Base

Base.metadata.create_all(bind=db.engine)

from models.auth_user import AuthUser
from models.customers import Customer
from models.expense import Expense, ExpensePaymentMethod
from models.expense_category import ExpenseCategory
from models.new_product import ProfessionalProduct
from models.new_sale_item import ProfessionalSaleItem
from models.new_sales import ProfessionalSale
from models.product_batch import ProductBatch
from services.base_service import get_session
from services.expense_service import ExpenseService
from services.new_sale_service import NewSaleService
from services.product_group_service import ProductGroupService
from services.report_subscription_service import (
    ReportSubscriptionService, scope_filename_tag, scope_from_payload,
)
from telegrambot.handlers.reports.daily_sales_report import (
    daily_report_caption, daily_report_filename, daily_report_pdf, daily_report_data,
)
from telegrambot.handlers.reports.profit_report import (
    build_daily_profit_data, build_monthly_profit_data, build_period_product_breakdown,
    build_period_profit_data, generate_monthly_profit_pdf, generate_period_profit_pdf,
)

TODAY = date(2026, 9, 18)

FAILURES = []


def check(label, condition, detail=''):
    if condition:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} {detail}")
        FAILURES.append(label)


def approx(a, b, tol=0.01):
    return abs(float(a) - float(b)) <= tol


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
def seed():
    with get_session() as session:
        admin = AuthUser(username='ADMIN', password='x', role='admin', chat_id=1000)
        admin_no_subs = AuthUser(username='ADMIN2', password='x', role='admin', chat_id=1001)
        customer = Customer(name='Test Customer')
        cat_a = ExpenseCategory(name='Transport')
        cat_b = ExpenseCategory(name='Rent')
        session.add_all([admin, admin_no_subs, customer, cat_a, cat_b])
        session.flush()

        products = {}
        for name, price in (('P1', 10.0), ('P2', 20.0), ('P3', 30.0), ('P4', 40.0)):
            product = ProfessionalProduct(
                name=name, normalized_name=name.lower(), unit='carton',
                normalized_unit='carton', dozen=1, selling_price=price,
            )
            session.add(product)
            session.flush()
            batch = ProductBatch(
                product_id=product.id, quantity=100, available_quantity=90, cost_price=price / 2.0,
            )
            session.add(batch)
            session.flush()
            products[name] = {'product': product, 'batch': batch}

        # One sale on TODAY holding all four products.
        sale = ProfessionalSale(
            customer_id=customer.id, total_amount=1000.0,
            created_at=datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=10),
        )
        session.add(sale)
        session.flush()

        # qty 1 each: selling = price, cost = price/2
        for entry in products.values():
            session.add(ProfessionalSaleItem(
                sale_id=sale.id, batch_id=entry['batch'].id,
                unit_price=entry['product'].selling_price, quantity=1, dozen=1,
                total=entry['product'].selling_price,
            ))

        # Expenses: two tagged to the first group (created later), one untagged.
        session.add_all([
            Expense(category_id=cat_a.id, amount=50.0, payment_method=ExpensePaymentMethod.CASH,
                    date=TODAY, description='Expense', notes='group expense', is_personal=False),
            Expense(category_id=cat_b.id, amount=30.0, payment_method=ExpensePaymentMethod.CASH,
                    date=TODAY, description='Expense', notes='group expense 2', is_personal=False),
            Expense(category_id=cat_b.id, amount=999.0, payment_method=ExpensePaymentMethod.CASH,
                    date=TODAY, description='Expense', notes='company wide', is_personal=False),
            Expense(category_id=cat_b.id, amount=111.0, payment_method=ExpensePaymentMethod.CASH,
                    date=TODAY, description='Expense', notes='personal', is_personal=True),
        ])
        session.commit()

        return {
            'admin_chat': admin.chat_id,
            'admin_no_subs_chat': admin_no_subs.chat_id,
            'cat_a': cat_a.id, 'cat_b': cat_b.id,
            'products': {k: {'id': v['product'].id} for k, v in products.items()},
            'today': TODAY,
        }


# ---------------------------------------------------------------------------
# 1. Product groups
# ---------------------------------------------------------------------------
def test_product_groups(seed_data):
    print("\n1. Product groups")
    groups = ProductGroupService()
    p = seed_data['products']

    group_a = groups.create_group('Group A', 'first half')
    group_b = groups.create_group('Group B', 'second half')
    check('create groups', group_a is not None and group_b is not None)
    check('duplicate name rejected', groups.create_group('Group A') is None)

    check('set members A', groups.set_members(group_a.id, [p['P1']['id'], p['P2']['id']]))
    check('set members B', groups.set_members(group_b.id, [p['P3']['id']]))
    check('member ids', groups.get_member_product_ids([group_a.id]) == {p['P1']['id'], p['P2']['id']})
    check('union of groups de-duplicates',
          groups.get_member_product_ids([group_a.id, group_b.id]) ==
          {p['P1']['id'], p['P2']['id'], p['P3']['id']})

    counts = {g['name']: g['product_count'] for g in groups.list_with_counts()}
    check('counts', counts.get('Group A') == 2 and counts.get('Group B') == 1, str(counts))
    check('total product count', groups.count_products() == 4)

    # replace members
    groups.set_members(group_b.id, [p['P3']['id'], p['P2']['id']])
    check('replace members', groups.get_member_product_ids([group_b.id]) ==
          {p['P2']['id'], p['P3']['id']})
    groups.set_members(group_b.id, [p['P3']['id']])

    return group_a.id, group_b.id


# ---------------------------------------------------------------------------
# 2. Subscribers + recipient merge
# ---------------------------------------------------------------------------
def test_recipients(seed_data, group_a_id, group_b_id):
    print("\n2. Recipient resolution")
    subs = ReportSubscriptionService()
    p = seed_data['products']

    scoped_a = subs.create_subscriber('Group A partner', 5555, group_ids=[group_a_id],
                                      full_report=False)
    scoped_ab = subs.create_subscriber('A+B partner', 6666, group_ids=[group_a_id, group_b_id],
                                       full_report=False)
    full_sub = subs.create_subscriber('Full partner', 7777)
    no_daily = subs.create_subscriber('No daily', 8888)
    subs.update_subscriber(no_daily.id, {'report_types': ['monthly']})

    check('created subscribers', None not in (scoped_a, scoped_ab, full_sub, no_daily))
    check('duplicate chat_id rejected', subs.create_subscriber('dup', 5555) is None)

    recipients = subs.get_recipients('daily')
    by_chat = {r.chat_id: r for r in recipients}

    check('admin without a row still receives', seed_data['admin_chat'] in by_chat)
    check('that admin is unscoped', by_chat[seed_data['admin_chat']].is_full)
    check('second admin also receives', seed_data['admin_no_subs_chat'] in by_chat)
    check('daily opt-out respected', 8888 not in by_chat)
    check('monthly opt-in respected',
          8888 in {r.chat_id for r in subs.get_recipients('monthly')})

    check('scoped A product set', by_chat[5555].product_ids == {p['P1']['id'], p['P2']['id']})
    check('scoped A+B union', by_chat[6666].product_ids ==
          {p['P1']['id'], p['P2']['id'], p['P3']['id']})
    check('full subscriber unscoped', by_chat[7777].is_full)
    check('scope label mentions totals',
          'of 4 products' in by_chat[5555].scope_label, by_chat[5555].scope_label)

    # The admin role is the opt-in: an admin stays FULL for every report type
    # even when a subscriber row of their own is scoped and has types muted.
    admin_row = subs.create_subscriber('Admin scoped row', seed_data['admin_chat'],
                                       group_ids=[group_a_id], full_report=False)
    subs.update_subscriber(admin_row.id, {'report_types': ['monthly']})
    by_chat = {r.chat_id: r for r in subs.get_recipients('daily')}
    check('admin with a scoped row still gets the full daily report',
          by_chat[seed_data['admin_chat']].is_full)
    check('admin is queued exactly once per report',
          len([r for r in subs.get_recipients('daily')
               if r.chat_id == seed_data['admin_chat']]) == 1)
    check('an admin row cannot mute a report type',
          seed_data['admin_chat'] in {r.chat_id for r in subs.get_recipients('monthly')})

    # partial with no group links must fall back to full (misconfiguration),
    # while a group that exists but is empty stays an intentionally empty scope.
    orphan = subs.create_subscriber('Orphan scoped', 9999, full_report=False)
    by_chat = {r.chat_id: r for r in subs.get_recipients('daily')}
    check('scoped with no groups falls back to full', by_chat[9999].is_full)

    empty_group = ProductGroupService().create_group('Empty Group')
    by_chat[9999]  # keep reference clean
    subs.update_subscriber(orphan.id, {'group_ids': [empty_group.id]})
    by_chat = {r.chat_id: r for r in subs.get_recipients('daily')}
    check('empty group is a real (empty) scope, not full',
          by_chat[9999].product_ids == set() and not by_chat[9999].is_full,
          f"product_ids={by_chat[9999].product_ids}")

    # payload round-trip
    payload = by_chat[6666].to_payload()
    restored = scope_from_payload(payload)
    check('payload round-trip products', restored['product_ids'] == by_chat[6666].product_ids)
    check('payload round-trip groups', restored['group_ids'] == [group_a_id, group_b_id])
    check('unscoped payload round-trips as None',
          scope_from_payload(by_chat[7777].to_payload())['product_ids'] is None)
    check('missing scope payload means full', scope_from_payload(None)['product_ids'] is None)
    check('filename tag', scope_filename_tag('Group A, Group B (3 of 4 products)') == 'group_a_group_b',
          scope_filename_tag('Group A, Group B (3 of 4 products)'))
    check('empty filename tag', scope_filename_tag('') == '')

    return {'scoped_a': scoped_a.id, 'scoped_ab': scoped_ab.id, 'full': full_sub.id,
            'orphan': orphan.id}


# ---------------------------------------------------------------------------
# 3. Product-filtered money queries
# ---------------------------------------------------------------------------
def test_sale_scoping(seed_data):
    print("\n3. Scoped sales queries")
    sale_svc = NewSaleService()
    p = seed_data['products']
    today = seed_data['today']
    subset = {p['P1']['id'], p['P2']['id']}

    check('unscoped selling = all products',
          approx(sale_svc.get_total_selling_price_for_period(today, today), 100.0))
    check('scoped selling = subset',
          approx(sale_svc.get_total_selling_price_for_period(today, today, subset), 30.0))
    check('scoped cost = subset half',
          approx(sale_svc.get_total_cost_price_for_period(today, today, subset), 15.0))
    check('scoped quantity', sale_svc.get_total_quantity_for_period(today, today, subset) == 2)
    check('empty scope yields nothing',
          sale_svc.get_total_selling_price_for_period(today, today, set()) == 0.0 and
          sale_svc.get_total_quantity_for_period(today, today, set()) == 0)

    breakdown = sale_svc.get_product_profit_breakdown(today, today, subset)
    check('scoped breakdown rows', {r['product_name'] for r in breakdown} == {'P1', 'P2'},
          str([r['product_name'] for r in breakdown]))
    check('breakdown carries product_id', all('product_id' in r for r in breakdown))
    # profit per product = price - price/2, so 5+10+15+20 = 50
    check('total profit unscoped',
          approx(sum(r['profit'] for r in sale_svc.get_product_profit_breakdown(today, today)), 50.0))


# ---------------------------------------------------------------------------
# 4. Expense scoping + tagging
# ---------------------------------------------------------------------------
def test_expense_scoping(seed_data, group_a_id):
    print("\n4. Scoped expenses")
    expenses = ExpenseService()
    today = seed_data['today']

    # Tag the two non-personal "group expense" rows to Group A via bulk tagging.
    changed = expenses.assign_group_to_expenses(
        group_id=group_a_id, category_id=None, date_from=today, date_to=today,
        only_untagged=True, is_personal=False,
    )
    check('bulk tagging changed 3 business rows', changed == 3, f"changed={changed}")

    check('scoped total = tagged rows only',
          approx(expenses.get_total_expenses_for_period(today, today, product_group_ids=[group_a_id]),
                 1079.0))
    check('unscoped total unaffected (business only)',
          approx(expenses.get_total_expenses_for_period(today, today), 1079.0))
    check('personal expense excluded',
          approx(expenses.get_total_expenses_for_period(today, today, business_only=False), 1190.0))
    check('unknown group has nothing',
          expenses.get_total_expenses_for_period(today, today, product_group_ids=[99999]) == 0.0)
    check('empty group scope is zero (not everything)',
          expenses.get_total_expenses_for_period(today, today, product_group_ids=[]) == 0.0)

    # Move just the "company wide" row (999) into its own group and re-check.
    group_c = ProductGroupService().create_group('Group C')
    with get_session() as session:
        row = session.query(Expense).filter(Expense.amount == 999.0).first()
        row.product_group_id = group_c.id
        session.commit()

    check('group A no longer includes the 999 row',
          approx(expenses.get_total_expenses_for_period(today, today, product_group_ids=[group_a_id]),
                 80.0))
    check('group C holds it', approx(
        expenses.get_total_expenses_for_period(today, today, product_group_ids=[group_c.id]), 999.0))

    details = expenses.get_expense_details_by_category(
        today, today, product_group_ids=[group_a_id])
    check('scoped breakdown only has group A rows',
          approx(sum(c['total_amount'] for c in details), 80.0))
    check('scoped breakdown items carry group ids',
          all('product_group_id' in item for c in details for item in c['items']))

    # clearing the tag puts rows back into the "untagged" bucket
    cleared = expenses.assign_group_to_expenses(
        group_id=None, date_from=today, date_to=today, only_untagged=False, is_personal=False)
    check('bulk clear untagged everything', cleared == 3, f"cleared={cleared}")
    check('after clearing, scoped totals are zero',
          expenses.get_total_expenses_for_period(
              today, today, product_group_ids=[group_a_id]) == 0.0)
    check('after clearing, unscoped total unchanged',
          approx(expenses.get_total_expenses_for_period(today, today), 1079.0))
    # get_expenses_by_group has no personal filter, so all 4 untagged rows show
    check('untagged listing shows every untagged row',
          len(expenses.get_expenses_by_group(None, today, today)) == 4, str(
              len(expenses.get_expenses_by_group(None, today, today))))

    # re-tag for the report-building tests
    expenses.assign_group_to_expenses(
        group_id=group_a_id, date_from=today, date_to=today, only_untagged=True, is_personal=False)
    with get_session() as session:
        row = session.query(Expense).filter(Expense.amount == 999.0).first()
        row.product_group_id = group_c.id
        session.commit()
    return group_c.id


# ---------------------------------------------------------------------------
# 5. Report data + PDF for scoped and unscoped
# ---------------------------------------------------------------------------
def test_reports(seed_data, group_a_id):
    print("\n5. Report build + render")
    p = seed_data['products']
    today = seed_data['today']
    subset = {p['P1']['id'], p['P2']['id']}

    baseline = build_daily_profit_data(today)
    check('baseline matches company totals',
          approx(baseline['total_selling'], 100.0) and approx(baseline['total_cost'], 50.0) and
          len(baseline['items']) == 4)

    scoped = build_daily_profit_data(today, subset, [group_a_id])
    check('scoped totals', approx(scoped['total_selling'], 30.0) and approx(scoped['total_cost'], 15.0))
    check('scoped items', {i['product_name'] for i in scoped['items']} == {'P1', 'P2'})
    check('scoped expenses', approx(scoped['expenses'], 80.0), str(scoped['expenses']))
    check('scoped net profit', approx(scoped['total_selling'] - scoped['total_cost'] - scoped['expenses'], -65.0))

    empty = build_daily_profit_data(today, set(), [group_a_id])
    check('empty scope renders zero sales', empty['total_selling'] == 0.0 and empty['items'] == [])

    data = daily_report_data(today, subset, [group_a_id])
    caption = daily_report_caption(data, today, 'Group A (2 of 4 products)')
    check('caption names the scope', 'Scope:' in caption and 'Group A' in caption)
    check('unscoped caption has no scope line', 'Scope:' not in daily_report_caption(data, today))
    check('scoped filename tagged',
          daily_report_filename(today, 'Group A (2 of 4 products)') ==
          f"daily_profit_group_a_{today}.pdf")
    check('unscoped filename plain',
          daily_report_filename(today) == f"daily_profit_{today}.pdf")

    for label, blob in (
        ('scoped daily PDF', daily_report_pdf(data, today, 'Group A (2 of 4 products)')),
        ('unscoped daily PDF', daily_report_pdf(baseline, today)),
    ):
        check(f'{label} renders', isinstance(blob, bytes) and blob[:4] == b'%PDF' and len(blob) > 1000,
              f"{len(blob) if blob else 0} bytes")

    month_start = today - timedelta(days=5)
    monthly = build_monthly_profit_data(month_start, today, subset, [group_a_id])
    check('monthly rows cover the range', len(monthly) == 6)
    check('monthly last day scoped', approx(monthly[-1]['total_selling'], 30.0))
    items = build_period_product_breakdown(month_start, today, subset)
    check('period product breakdown scoped', {i['product_name'] for i in items} == {'P1', 'P2'})
    check('scoped monthly PDF renders',
          generate_monthly_profit_pdf('Test Month', month_start, today, monthly, items,
                                      'Group A (2 of 4 products)')[:4] == b'%PDF')
    check('unscoped monthly PDF renders',
          generate_monthly_profit_pdf('Test Month', month_start, today, monthly)[:4] == b'%PDF')

    period = build_period_profit_data(month_start, today, subset, [group_a_id])
    check('period rows', len(period) >= 1)
    check('scoped period PDF renders',
          generate_period_profit_pdf('Test Period', month_start, today, period, items,
                                     'Group A (2 of 4 products)')[:4] == b'%PDF')
    check('unscoped period PDF renders',
          generate_period_profit_pdf('Test Period', month_start, today, period)[:4] == b'%PDF')


# ---------------------------------------------------------------------------
# 6. Dedup keys
# ---------------------------------------------------------------------------
def test_dedup(seed_data):
    print("\n6. Dedup keys carry the scope")
    from telegrambot.outbox import _get_dedup_key

    today = seed_data['today'].isoformat()
    full_payload = {'target_date': today, 'scope': {'product_ids': None, 'group_ids': [], 'label': ''}}
    scoped_payload = {'target_date': today,
                      'scope': {'product_ids': [1, 2], 'group_ids': [7], 'label': 'Group A'}}

    full_key = _get_dedup_key('daily_sales_report', full_payload, 100)
    scoped_key = _get_dedup_key('daily_sales_report', scoped_payload, 100)
    check('same day, different scope → different keys', full_key != scoped_key)
    check('same payload is stable',
          _get_dedup_key('daily_sales_report', scoped_payload, 100) == scoped_key)
    check('legacy payload (no scope) is full',
          _get_dedup_key('daily_sales_report', {'target_date': today}, 100) == full_key)

    profit_key = _get_dedup_key('profit_report', {
        'period_type': 'annual', 'start_date': '2025-01-01', 'end_date': '2025-12-31',
        'scope': scoped_payload['scope']}, 100)
    check('profit key includes the scope signature', profit_key[-1] == ('1,2', (7,)), str(profit_key))
    check('profit key differs by scope', profit_key != _get_dedup_key('profit_report', {
        'period_type': 'annual', 'start_date': '2025-01-01', 'end_date': '2025-12-31',
        'scope': {'product_ids': None, 'group_ids': [], 'label': ''}}, 100))


# ---------------------------------------------------------------------------
# 7. Migration helper
# ---------------------------------------------------------------------------
def test_migration():
    print("\n7. Column migration helper")
    from sqlalchemy import text
    from migrations import ensure_column

    with db.engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS legacy_probe"))
        conn.execute(text("CREATE TABLE legacy_probe (id INTEGER PRIMARY KEY, name TEXT)"))

    check('adds a missing column', ensure_column('legacy_probe', 'group_id', 'INTEGER') is True)
    check('idempotent on the second run', ensure_column('legacy_probe', 'group_id', 'INTEGER') is False)
    check('missing table is a no-op', ensure_column('nope_table', 'x', 'INTEGER') is False)

    # expenses already has the column from create_all, so this must be a no-op.
    check('expenses.product_group_id already present',
          ensure_column('expenses', 'product_group_id', 'INTEGER REFERENCES product_groups(id)') is False)


# ---------------------------------------------------------------------------
# 8. Outbox senders, end to end with a stub bot
# ---------------------------------------------------------------------------
class StubBot:
    """Minimal async Bot stand-in that records what would be sent."""

    def __init__(self):
        self.messages = []
        self.documents = []

    async def send_message(self, chat_id, text=None, parse_mode=None, **kwargs):
        self.messages.append({'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode})

    async def send_document(self, chat_id, document=None, filename=None, caption=None, **kwargs):
        blob = document.read() if hasattr(document, 'read') else b''
        self.documents.append({'chat_id': chat_id, 'filename': filename,
                               'caption': caption, 'bytes': blob})


def test_senders(seed_data, group_a_id):
    print("\n8. Outbox senders")
    import asyncio
    from telegrambot.outbox import _send_daily_sales_report, _send_profit_report

    today = seed_data['today']
    p = seed_data['products']
    scoped_scope = {'product_ids': [p['P1']['id'], p['P2']['id']],
                    'group_ids': [group_a_id], 'label': 'Group A (2 of 4 products)'}

    async def run_scoped_daily():
        bot = StubBot()
        await _send_daily_sales_report(bot, 5555, {
            'target_date': today.isoformat(), 'scope': scoped_scope}, notif_id=-1)
        return bot

    bot = asyncio.run(run_scoped_daily())
    check('scoped daily sends one text', len(bot.messages) == 1 and len(bot.documents) == 1)
    check('scoped daily caption names the scope', 'Scope:' in bot.messages[0]['text'])
    check('scoped daily caption uses subset sales', '30.00' in bot.messages[0]['text'],
          bot.messages[0]['text'])
    check('scoped daily filename tagged',
          bot.documents[0]['filename'] == f"daily_profit_group_a_{today}.pdf",
          bot.documents[0]['filename'])
    check('scoped daily PDF body', bot.documents[0]['bytes'][:4] == b'%PDF')

    async def run_full_daily():
        bot = StubBot()
        # Legacy payload without a scope block must behave exactly as before.
        await _send_daily_sales_report(bot, 1000, {'target_date': today.isoformat()}, notif_id=-1)
        return bot

    bot = asyncio.run(run_full_daily())
    check('legacy daily caption has no scope', 'Scope:' not in bot.messages[0]['text'])
    check('legacy daily caption uses company sales', '100.00' in bot.messages[0]['text'])
    check('legacy daily filename plain',
          bot.documents[0]['filename'] == f"daily_profit_{today}.pdf")

    async def run_scoped_annual():
        bot = StubBot()
        await _send_profit_report(bot, 5555, {
            'period_type': 'annual', 'period_label': 'Ethiopian Year 2018 / Annual Profit Report',
            'start_date': (today - timedelta(days=400)).isoformat(),
            'end_date': today.isoformat(), 'scope': scoped_scope}, notif_id=-1)
        return bot

    bot = asyncio.run(run_scoped_annual())
    check('scoped profit sends text + pdf', len(bot.messages) == 1 and len(bot.documents) == 1)
    check('scoped profit caption names the scope', 'Scope:' in bot.messages[0]['text'])
    check('scoped profit filename tagged',
          bot.documents[0]['filename'].endswith(f"_group_a_{today}.pdf"),
          bot.documents[0]['filename'])
    check('scoped profit PDF body', bot.documents[0]['bytes'][:4] == b'%PDF')

    async def run_full_annual():
        bot = StubBot()
        await _send_profit_report(bot, 1000, {
            'period_type': 'annual', 'period_label': 'Annual Profit Report',
            'start_date': (today - timedelta(days=400)).isoformat(),
            'end_date': today.isoformat()}, notif_id=-1)
        return bot

    bot = asyncio.run(run_full_annual())
    check('unscoped profit filename plain',
          bot.documents[0]['filename'] == f"annual_profit_{today}.pdf",
          bot.documents[0]['filename'])
    check('unscoped profit caption has no scope', 'Scope:' not in bot.messages[0]['text'])


# ---------------------------------------------------------------------------
# 9. Scheduler queueing shape
# ---------------------------------------------------------------------------
def test_scheduler_queue(seed_data, group_a_id):
    print("\n9. Scheduler queueing")
    import asyncio
    import json
    from models.pending_notification import PendingNotification
    from telegrambot.scheduler import queue_daily_sales_report, queue_profit_report

    with get_session() as session:
        session.query(PendingNotification).delete()
        session.commit()

    asyncio.run(queue_daily_sales_report(target_date=seed_data['today']))

    with get_session() as session:
        rows = session.query(PendingNotification).filter(
            PendingNotification.notification_type == 'daily_sales_report').all()
        payloads = {r.chat_id: json.loads(r.payload_json) for r in rows}

    check('daily queued for the scoped partner', 5555 in payloads, str(sorted(payloads)))
    check('daily queued for the second admin', seed_data['admin_no_subs_chat'] in payloads)
    group_a_scope = payloads[5555]['scope']
    check('group A payload carries its product ids',
          set(group_a_scope['product_ids']) ==
          {seed_data['products']['P1']['id'], seed_data['products']['P2']['id']},
          str(group_a_scope))
    check('group A payload carries group ids and label',
          group_a_scope['group_ids'] == [group_a_id]
          and 'of 4 products' in group_a_scope['label'], str(group_a_scope))
    check('two-group payload carries both groups', len(payloads[6666]['scope']['group_ids']) == 2,
          str(payloads[6666]['scope']))
    check('unscoped recipients get a null scope',
          payloads[seed_data['admin_no_subs_chat']]['scope']['product_ids'] is None
          and payloads[7777]['scope']['product_ids'] is None)

    asyncio.run(queue_profit_report('annual', 'Annual Profit Report',
                                    seed_data['today'] - timedelta(days=365),
                                    seed_data['today']))
    with get_session() as session:
        rows = session.query(PendingNotification).filter(
            PendingNotification.notification_type == 'profit_report').all()
        profit_chat_ids = {r.chat_id for r in rows}
    check('profit report queued scoped', 5555 in profit_chat_ids and 6666 in profit_chat_ids)


# ---------------------------------------------------------------------------
# 10. A full report must keep its company-wide expenses
# ---------------------------------------------------------------------------
def test_full_report_expenses(seed_data, group_a_id):
    """Regression: a full recipient is scoped to NO group, which must mean "every
    expense" and not "no group's expenses".

    The first version of Recipient.to_payload() sent group_ids=[] for a full
    report; read back, that filtered expenses by an empty group list, so every
    company-wide report shipped with ETB 0.00 expenses and an overstated profit.
    """
    print("\n10. Full report keeps company-wide expenses")
    import asyncio
    import json
    from models.pending_notification import PendingNotification
    from telegrambot.outbox import _send_daily_sales_report
    from telegrambot.scheduler import queue_daily_sales_report
    from services.report_subscription_service import full_recipient

    today = seed_data['today']

    check('full recipient payload carries a null group scope',
          full_recipient(1000).to_payload()['group_ids'] is None,
          str(full_recipient(1000).to_payload()))
    check('round-tripped full scope is unscoped',
          scope_from_payload(full_recipient(1000).to_payload())['group_ids'] is None)
    check('empty group list + no products is read as unscoped',
          scope_from_payload({'product_ids': None, 'group_ids': [], 'label': ''})['group_ids']
          is None)
    check('explicit empty product scope keeps an empty group scope',
          scope_from_payload({'product_ids': [], 'group_ids': [], 'label': 'x'})['group_ids']
          == [])

    with get_session() as session:
        session.query(PendingNotification).delete()
        session.commit()
    asyncio.run(queue_daily_sales_report(target_date=today))
    with get_session() as session:
        payloads = {
            r.chat_id: json.loads(r.payload_json) for r in session.query(PendingNotification).filter(
                PendingNotification.notification_type == 'daily_sales_report').all()
        }

    full_chat = seed_data['admin_no_subs_chat']
    check('queued full payload has a null group scope',
          payloads[full_chat]['scope']['group_ids'] is None, str(payloads[full_chat]['scope']))

    async def send(payload, chat_id):
        bot = StubBot()
        await _send_daily_sales_report(bot, chat_id, payload, notif_id=-1)
        return bot.messages[0]['text']

    text = asyncio.run(send(payloads[full_chat], full_chat))
    check('full report shows the company-wide expense total', '1,079.00' in text, text)
    check('full report has no scope banner', 'Scope:' not in text)

    # The exact payload shape the bug produced must still be sent as a full report.
    legacy_shape = {'target_date': today.isoformat(),
                    'scope': {'product_ids': None, 'group_ids': [], 'label': ''}}
    text = asyncio.run(send(legacy_shape, full_chat))
    check('empty-group full payload still shows all expenses', '1,079.00' in text, text)

    scoped_text = asyncio.run(send(payloads[5555], 5555))
    check('scoped report still shows only its own expenses', '80.00' in scoped_text, scoped_text)

    # Annual/monthly builders are driven by the same scope, so guard them too.
    from telegrambot.outbox import _send_profit_report

    async def send_profit(payload, chat_id):
        bot = StubBot()
        await _send_profit_report(bot, chat_id, payload, notif_id=-1)
        return bot.messages[0]['text']

    annual = {'period_type': 'annual', 'period_label': 'Annual Profit Report',
              'start_date': today.isoformat(), 'end_date': today.isoformat(),
              'scope': {'product_ids': None, 'group_ids': [], 'label': ''}}
    profit_text = asyncio.run(send_profit(annual, full_chat))
    check('full annual report still renders a PDF', 'PDF' in profit_text, profit_text)
    check('scoped annual report still renders a PDF',
          'PDF' in asyncio.run(send_profit(dict(annual, scope=payloads[5555]['scope']), 5555)))

    # The caption of a periodic report carries no money figures, so check the
    # numbers the PDF is built from, resolved from the very same payload scope.
    full_scope = scope_from_payload(annual['scope'])
    data = build_period_profit_data(today, today, full_scope['product_ids'],
                                    full_scope['group_ids'])
    check('full annual keeps every expense',
          approx(sum(row['expenses'] for row in data), 1079.0),
          str([row['expenses'] for row in data]))

    scoped_scope = scope_from_payload(payloads[5555]['scope'])
    data = build_period_profit_data(today, today, scoped_scope['product_ids'],
                                    scoped_scope['group_ids'])
    check('scoped annual keeps only its own expenses',
          approx(sum(row['expenses'] for row in data), 80.0),
          str([row['expenses'] for row in data]))


# ---------------------------------------------------------------------------
# 11. Per-product breakdown respects its period (regression)
# ---------------------------------------------------------------------------
def test_breakdown_period(seed_data):
    """Regression: the per-product breakdown must not report all-time figures.

    Its date/deleted filters were lost while the product scope was added, so the
    product table in every daily/monthly/period report silently summed every sale
    ever recorded. Runs last, because it adds a sale on the previous day.
    """
    print("\n11. Per-product breakdown respects the period")
    today = seed_data['today']
    yesterday = today - timedelta(days=1)
    sales = NewSaleService()

    with get_session() as session:
        product = ProfessionalProduct(
            name='OLD', normalized_name='old', unit='carton', normalized_unit='carton',
            dozen=1, selling_price=7.0,
        )
        session.add(product)
        session.flush()
        batch = ProductBatch(product_id=product.id, quantity=10, available_quantity=9,
                             cost_price=3.0)
        session.add(batch)
        session.flush()
        customer_id = session.query(Customer.id).scalar()
        sale = ProfessionalSale(
            customer_id=customer_id, total_amount=7.0,
            created_at=datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=10),
        )
        session.add(sale)
        session.flush()
        session.add(ProfessionalSaleItem(sale_id=sale.id, batch_id=batch.id, unit_price=7.0,
                                         quantity=1, dozen=1, total=7.0))
        session.commit()
        old_product_id = product.id

    today_rows = sales.get_product_profit_breakdown(today, today)
    check('today\'s breakdown excludes yesterday\'s product',
          all(r['product_id'] != old_product_id for r in today_rows),
          str([r['product_name'] for r in today_rows]))
    check('today\'s breakdown has only products sold today', len(today_rows) == 4,
          str([r['product_name'] for r in today_rows]))
    check('today\'s breakdown totals match the day',
          approx(sum(r['total_selling'] for r in today_rows), 100.0),
          str(sum(r['total_selling'] for r in today_rows)))

    yesterday_rows = sales.get_product_profit_breakdown(yesterday, yesterday)
    check('yesterday\'s breakdown has only the previous-day sale',
          [r['product_id'] for r in yesterday_rows] == [old_product_id],
          str([r['product_name'] for r in yesterday_rows]))
    check('scoped breakdown for yesterday',
          [r['product_id'] for r in
           sales.get_product_profit_breakdown(yesterday, yesterday, {old_product_id})]
          == [old_product_id])
    check('scoped breakdown for yesterday is empty for other products',
          sales.get_product_profit_breakdown(yesterday, yesterday, {seed_data['products']['P4']['id']})
          == [])
    check('breakdown for a sale-free window is empty',
          sales.get_product_profit_breakdown(today - timedelta(days=9),
                                             today - timedelta(days=8)) == [])

    data = daily_report_data(today)
    check('the daily report product table is period-limited',
          all(item.get('product_id') != old_product_id for item in data['items']),
          str(data['items']))


def main():
    print("Product specific report scoping — throwaway database")
    print(f"  db: {TEST_DB_PATH}")
    seed_data = seed()
    group_a_id, group_b_id = test_product_groups(seed_data)
    test_recipients(seed_data, group_a_id, group_b_id)
    test_sale_scoping(seed_data)
    test_expense_scoping(seed_data, group_a_id)
    test_reports(seed_data, group_a_id)
    test_dedup(seed_data)
    test_migration()
    test_senders(seed_data, group_a_id)
    test_scheduler_queue(seed_data, group_a_id)
    test_full_report_expenses(seed_data, group_a_id)
    test_breakdown_period(seed_data)

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s)")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == '__main__':
    try:
        exit_code = main()
    finally:
        # Never leave the throwaway database behind.
        import gc
        gc.collect()
        try:
            db.engine.dispose()
        except Exception:
            pass
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                print(f"(could not remove {TEST_DB_PATH})")
    sys.exit(exit_code)
