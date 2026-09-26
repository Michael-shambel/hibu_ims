#!/usr/bin/env python3
"""
ReportSubscriptionService – who receives which report, scoped to which products.

Resolution rules
----------------
* Every admin chat (`auth_users.role == 'admin'` with a chat_id) receives EVERY
  report type, always as the FULL company report. Registering the user as an
  admin is the opt-in: a subscriber row they own (product scope, per-type
  flags, even inactive) never limits or mutes an admin.
* Every active `ReportSubscriber` that is not an admin's chat and whose flag
  for the report type is on is a recipient, scoped to its product groups.
  Subscriber rows owned by an admin chat are skipped here - the admin entry
  already covers them with the full report.
* `full_report=True` (or a subscriber with an empty product scope resolution)
  means no product filter: `product_ids is None`.
* A subscriber in several groups gets one MERGED report: the union of the groups'
  products and the union of the groups' expense tags.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import joinedload

from models.auth_user import AuthUser
from models.product_group import ProductGroup
from models.report_subscriber import ReportSubscriber
from models.subscriber_group import SubscriberGroup
from services.base_service import get_session
from services.product_group_service import ProductGroupService

logger = logging.getLogger(__name__)

# report_type -> ReportSubscriber flag column
REPORT_TYPE_FLAGS = {
    'daily': 'receive_daily',
    'monthly': 'receive_monthly',
    'quarterly': 'receive_quarterly',
    'semiannual': 'receive_semiannual',
    'annual': 'receive_annual',
}

REPORT_TYPE_LABELS = {
    'daily': 'Daily',
    'monthly': '1-Month',
    'quarterly': '3-Month',
    'semiannual': '6-Month',
    'annual': '1-Year',
}


@dataclass
class Recipient:
    """A resolved delivery target plus the product scope it should be sent with."""
    chat_id: int
    label: str
    product_ids: Optional[Set[int]] = None      # None => full report
    group_ids: List[int] = field(default_factory=list)
    group_names: List[str] = field(default_factory=list)
    subscriber_id: Optional[int] = None
    total_products: int = 0
    source: str = 'subscriber'                  # 'subscriber' | 'admin'

    @property
    def is_full(self) -> bool:
        return self.product_ids is None

    @property
    def scope_label(self) -> str:
        """Human readable scope banner, e.g. 'Group A, Group B (20 of 40 products)'."""
        if self.is_full:
            return ''
        names = ', '.join(self.group_names) if self.group_names else 'No group'
        if self.total_products:
            return f"{names} ({len(self.product_ids or [])} of {self.total_products} products)"
        return names

    def to_payload(self) -> Dict:
        """The `scope` block that travels inside a pending_notification payload."""
        if self.is_full:
            # A full report is not limited by product groups at all, so the
            # group scope must travel as None. An empty list would be read on
            # the way back out as "no product group", which zeroes the expense
            # side of a company-wide report instead of leaving it untouched.
            return {'product_ids': None, 'group_ids': None, 'label': ''}
        return {
            'product_ids': sorted(self.product_ids),
            'group_ids': list(self.group_ids),
            'label': self.scope_label,
        }


def full_recipient(chat_id: int, label: str = 'Admin (fallback)') -> Recipient:
    """A recipient that receives the unmodified company-wide report."""
    return Recipient(chat_id=chat_id, label=label, product_ids=None, source='admin')


def scope_filename_tag(scope_label: str) -> str:
    """Filesystem-safe short tag for a scope label, e.g. 'group_a_group_b'."""
    if not scope_label:
        return ''
    base = scope_label.split('(')[0]
    slug = re.sub(r'[^0-9A-Za-z]+', '_', base).strip('_').lower()
    return slug[:40]


def scope_from_payload(scope: Optional[Dict]) -> Dict:
    """
    Normalise the scope block read back out of a pending_notification payload.

    Returns {'product_ids': set|None, 'group_ids': list|None, 'label': str}, where
    `None` means "not scoped": every product and every expense.
    """
    if not scope:
        return {'product_ids': None, 'group_ids': None, 'label': ''}

    raw_products = scope.get('product_ids')
    product_ids = None if raw_products is None else {int(p) for p in raw_products}
    if product_ids is None:
        # Full report: the expense side has to stay company-wide too. Reading an
        # empty group list here would mean "no group's expenses", which would
        # silently drop every expense from an unscoped report.
        group_ids = None
    else:
        group_ids = [int(g) for g in (scope.get('group_ids') or [])]
    return {
        'product_ids': product_ids,
        'group_ids': group_ids,
        'label': scope.get('label') or '',
    }


class ReportSubscriptionService:
    def __init__(self):
        self.group_service = ProductGroupService()

    # ------------------------------------------------------------------
    # Recipient resolution (used by the scheduler)
    # ------------------------------------------------------------------
    def get_recipients(self, report_type: str) -> List[Recipient]:
        """
        Every recipient of `report_type`, each with its own product scope.

        Admins are ALWAYS recipients of every report type with the FULL company
        report - the admin role is the opt-in, so a subscriber row they own
        (scope, per-type flags, inactive) is skipped rather than applied.

        `report_type` is one of REPORT_TYPE_FLAGS. An unknown type behaves like
        'daily' for the admin fallback but matches no subscriber flag, so pass a
        valid one.
        """
        flag = REPORT_TYPE_FLAGS.get(report_type)
        total_products = self.group_service.count_products()

        with get_session() as session:
            rows = session.query(ReportSubscriber).options(
                joinedload(ReportSubscriber.group_links).joinedload(SubscriberGroup.group)
            ).filter(
                ReportSubscriber.is_deleted == False  # noqa: E712
            ).all()

            admin_chat_ids = {
                chat_id for (chat_id,) in session.query(AuthUser.chat_id).filter(
                    AuthUser.role == 'admin',
                    AuthUser.chat_id.isnot(None),
                    AuthUser.is_deleted == False,  # noqa: E712
                ).all()
            }

        # An admin's own subscriber row never scopes or mutes them: the admin
        # entries appended below are always the full company report.
        subscribers = [
            s for s in rows
            if s.chat_id not in admin_chat_ids
            and s.is_active and (flag is None or bool(getattr(s, flag, True)))
        ]
        recipients = [
            self._resolve(s, total_products) for s in subscribers
        ]
        recipients.extend(
            full_recipient(chat_id, label='Admin (full report)')
            for chat_id in sorted(admin_chat_ids)
        )

        recipients.sort(key=lambda r: (not r.is_full, r.label))
        logger.info(
            "Report '%s' has %d recipient(s) (%d scoped)",
            report_type, len(recipients), sum(1 for r in recipients if not r.is_full),
        )
        return recipients

    def _resolve(self, subscriber: ReportSubscriber, total_products: int = 0) -> Recipient:
        """Turn a subscriber row into a Recipient, resolving its product scope."""
        groups = [link.group for link in subscriber.group_links
                  if link.group and not link.group.is_deleted and link.group.is_active]

        if subscriber.full_report or not groups:
            # A partial subscriber with no group assigned has no scope to apply,
            # so it falls back to the full report. (A group that exists but has
            # no members is NOT this case: it stays an intentionally empty scope
            # and the report says so, rather than leaking company-wide figures.)
            return Recipient(
                chat_id=subscriber.chat_id,
                label=subscriber.display_name,
                product_ids=None,
                subscriber_id=subscriber.id,
            )

        group_ids = [g.id for g in groups]
        product_ids = self.group_service.get_member_product_ids(group_ids)
        return Recipient(
            chat_id=subscriber.chat_id,
            label=subscriber.display_name,
            product_ids=product_ids,
            group_ids=group_ids,
            group_names=[g.name for g in groups],
            subscriber_id=subscriber.id,
            total_products=total_products,
        )

    # ------------------------------------------------------------------
    # Subscriber CRUD (desktop UI)
    # ------------------------------------------------------------------
    def list_subscribers(self) -> List[Dict]:
        with get_session() as session:
            rows = session.query(ReportSubscriber).options(
                joinedload(ReportSubscriber.group_links).joinedload(SubscriberGroup.group),
                joinedload(ReportSubscriber.auth_user),
            ).filter(
                ReportSubscriber.is_deleted == False  # noqa: E712
            ).order_by(ReportSubscriber.display_name).all()

            return [
                {
                    'id': s.id,
                    'display_name': s.display_name,
                    'chat_id': s.chat_id,
                    'auth_user_id': s.auth_user_id,
                    'auth_username': s.auth_user.username if s.auth_user else None,
                    'is_active': bool(s.is_active),
                    'full_report': bool(s.full_report),
                    'group_ids': [link.product_group_id for link in s.group_links],
                    'group_names': [
                        link.group.name for link in s.group_links if link.group
                    ],
                    'receive_daily': bool(s.receive_daily),
                    'receive_monthly': bool(s.receive_monthly),
                    'receive_quarterly': bool(s.receive_quarterly),
                    'receive_semiannual': bool(s.receive_semiannual),
                    'receive_annual': bool(s.receive_annual),
                    'notes': s.notes,
                }
                for s in rows
            ]

    def get_subscriber(self, subscriber_id: int) -> Optional[Dict]:
        for row in self.list_subscribers():
            if row['id'] == subscriber_id:
                return row
        return None

    def create_subscriber(
        self,
        display_name: str,
        chat_id: int,
        auth_user_id: Optional[int] = None,
        full_report: bool = True,
        report_types: Optional[List[str]] = None,
        group_ids: Optional[List[int]] = None,
        notes: str = None,
    ) -> Optional[ReportSubscriber]:
        display_name = (display_name or '').strip()
        if not display_name or chat_id is None:
            logger.warning("Subscriber needs a display name and a chat_id")
            return None

        with get_session() as session:
            try:
                clash = session.query(ReportSubscriber).filter(
                    ReportSubscriber.chat_id == chat_id,
                    ReportSubscriber.is_deleted == False,  # noqa: E712
                ).first()
                if clash:
                    logger.warning("chat_id %s is already subscribed", chat_id)
                    return None

                types = self._normalise_report_types(report_types)
                subscriber = ReportSubscriber(
                    display_name=display_name,
                    chat_id=int(chat_id),
                    auth_user_id=auth_user_id,
                    full_report=bool(full_report),
                    notes=notes,
                    is_active=True,
                    **types,
                )
                session.add(subscriber)
                session.flush()

                for gid in {int(g) for g in (group_ids or [])}:
                    session.add(SubscriberGroup(subscriber_id=subscriber.id, product_group_id=gid))

                session.commit()
                session.refresh(subscriber)
                logger.info("Created report subscriber %s (%s)", subscriber.id, display_name)
                return subscriber
            except Exception as e:
                session.rollback()
                logger.error("Failed to create subscriber '%s': %s", display_name, e)
                return None

    def update_subscriber(self, subscriber_id: int, data: Dict) -> bool:
        with get_session() as session:
            try:
                subscriber = session.query(ReportSubscriber).filter(
                    ReportSubscriber.id == subscriber_id,
                    ReportSubscriber.is_deleted == False,  # noqa: E712
                ).first()
                if not subscriber:
                    return False

                if 'chat_id' in data and data['chat_id'] is not None:
                    new_chat = int(data['chat_id'])
                    if new_chat != subscriber.chat_id:
                        clash = session.query(ReportSubscriber).filter(
                            ReportSubscriber.chat_id == new_chat,
                            ReportSubscriber.id != subscriber_id,
                            ReportSubscriber.is_deleted == False,  # noqa: E712
                        ).first()
                        if clash:
                            logger.warning("chat_id %s is already subscribed", new_chat)
                            return False
                        subscriber.chat_id = new_chat

                for field_name in ('display_name', 'notes', 'auth_user_id'):
                    if field_name in data:
                        setattr(subscriber, field_name, data[field_name])

                for field_name in ('is_active', 'full_report'):
                    if field_name in data:
                        setattr(subscriber, field_name, bool(data[field_name]))

                if 'report_types' in data:
                    for key, value in self._normalise_report_types(data['report_types']).items():
                        setattr(subscriber, key, value)

                if 'group_ids' in data:
                    session.query(SubscriberGroup).filter(
                        SubscriberGroup.subscriber_id == subscriber_id
                    ).delete(synchronize_session=False)
                    for gid in {int(g) for g in (data['group_ids'] or [])}:
                        session.add(SubscriberGroup(subscriber_id=subscriber_id, product_group_id=gid))

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error("Failed to update subscriber %s: %s", subscriber_id, e)
                return False

    def delete_subscriber(self, subscriber_id: int) -> bool:
        with get_session() as session:
            try:
                subscriber = session.query(ReportSubscriber).filter(
                    ReportSubscriber.id == subscriber_id,
                    ReportSubscriber.is_deleted == False,  # noqa: E712
                ).first()
                if not subscriber:
                    return False
                session.query(SubscriberGroup).filter(
                    SubscriberGroup.subscriber_id == subscriber_id
                ).delete(synchronize_session=False)
                subscriber.is_deleted = True
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error("Failed to delete subscriber %s: %s", subscriber_id, e)
                return False

    @staticmethod
    def _normalise_report_types(report_types: Optional[List[str]]) -> Dict[str, bool]:
        """Missing types default to on so a new subscriber receives every report."""
        types = set(report_types) if report_types is not None else set(REPORT_TYPE_FLAGS)
        return {flag: (key in types) for key, flag in REPORT_TYPE_FLAGS.items()}

    # ------------------------------------------------------------------
    # Admin self-service (Telegram bot)
    # ------------------------------------------------------------------
    def get_by_chat_id(self, chat_id: int) -> Optional[Dict]:
        with get_session() as session:
            subscriber = session.query(ReportSubscriber).options(
                joinedload(ReportSubscriber.group_links).joinedload(SubscriberGroup.group)
            ).filter(
                ReportSubscriber.chat_id == chat_id,
                ReportSubscriber.is_deleted == False,  # noqa: E712
            ).first()
            if not subscriber:
                return None
            groups = [link.group for link in subscriber.group_links if link.group and not link.group.is_deleted]
            return {
                'id': subscriber.id,
                'display_name': subscriber.display_name,
                'chat_id': subscriber.chat_id,
                'full_report': bool(subscriber.full_report),
                'is_active': bool(subscriber.is_active),
                'group_ids': [g.id for g in groups],
                'group_names': [g.name for g in groups],
                'receive_daily': bool(subscriber.receive_daily),
                'receive_monthly': bool(subscriber.receive_monthly),
                'receive_quarterly': bool(subscriber.receive_quarterly),
                'receive_semiannual': bool(subscriber.receive_semiannual),
                'receive_annual': bool(subscriber.receive_annual),
            }

    def ensure_for_chat_id(self, chat_id: int, display_name: str = 'Admin') -> Optional[int]:
        """Create a default (full-report) subscriber row for an admin on first use."""
        existing = self.get_by_chat_id(chat_id)
        if existing:
            return existing['id']
        created = self.create_subscriber(display_name=display_name, chat_id=chat_id, full_report=True)
        return created.id if created else None

    def set_full_report_for_chat_id(self, chat_id: int, full_report: bool) -> bool:
        subscriber_id = self.ensure_for_chat_id(chat_id)
        if not subscriber_id:
            return False
        return self.update_subscriber(subscriber_id, {'full_report': bool(full_report)})

    def set_groups_for_chat_id(self, chat_id: int, group_ids: List[int]) -> bool:
        subscriber_id = self.ensure_for_chat_id(chat_id)
        if not subscriber_id:
            return False
        return self.update_subscriber(
            subscriber_id,
            {'group_ids': list(group_ids or []), 'full_report': False},
        )

    def set_report_type_for_chat_id(self, chat_id: int, report_type: str, enabled: bool) -> bool:
        if report_type not in REPORT_TYPE_FLAGS:
            return False
        subscriber_id = self.ensure_for_chat_id(chat_id)
        if not subscriber_id:
            return False

        current = self.get_by_chat_id(chat_id) or {}
        enabled_types = [
            key for key in REPORT_TYPE_FLAGS
            if bool(current.get(REPORT_TYPE_FLAGS[key], True))
        ]
        if enabled:
            if report_type not in enabled_types:
                enabled_types.append(report_type)
        else:
            enabled_types = [t for t in enabled_types if t != report_type]
        return self.update_subscriber(subscriber_id, {'report_types': enabled_types})
