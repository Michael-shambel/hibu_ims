#!/usr/bin/env python3
"""
ProductGroupService – CRUD for reusable product groups and their members.

A product group is a named set of professional products ("Group A" = 20 of the
40 products). Report subscribers are assigned groups; the union of their groups'
members is the product scope of every report they receive.
"""
import logging
from typing import Dict, List, Optional, Set

from sqlalchemy import func

from models.expense import Expense
from models.new_product import ProfessionalProduct
from models.product_group import ProductGroup
from models.product_group_member import ProductGroupMember
from models.subscriber_group import SubscriberGroup
from services.base_service import BaseService, get_session

logger = logging.getLogger(__name__)


class ProductGroupService(BaseService[ProductGroup]):
    def __init__(self):
        super().__init__(ProductGroup)

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------
    def list_groups(self, active_only: bool = False) -> List[ProductGroup]:
        with get_session() as session:
            query = session.query(ProductGroup).filter(ProductGroup.is_deleted == False)  # noqa: E712
            if active_only:
                query = query.filter(ProductGroup.is_active == True)  # noqa: E712
            return query.order_by(ProductGroup.name).all()

    def list_with_counts(self) -> List[Dict]:
        """Groups with their member-product count, for pickers and tables."""
        with get_session() as session:
            rows = session.query(
                ProductGroup.id,
                ProductGroup.name,
                ProductGroup.description,
                ProductGroup.is_active,
                func.count(ProductGroupMember.id).label('product_count'),
            ).outerjoin(
                ProductGroupMember, ProductGroupMember.product_group_id == ProductGroup.id
            ).filter(
                ProductGroup.is_deleted == False  # noqa: E712
            ).group_by(
                ProductGroup.id
            ).order_by(
                ProductGroup.name
            ).all()

            return [
                {
                    'id': r.id,
                    'name': r.name,
                    'description': r.description,
                    'is_active': bool(r.is_active),
                    'product_count': int(r.product_count or 0),
                }
                for r in rows
            ]

    def create_group(self, name: str, description: str = None) -> Optional[ProductGroup]:
        name = (name or '').strip()
        if not name:
            return None
        with get_session() as session:
            try:
                existing = session.query(ProductGroup).filter(
                    ProductGroup.name == name,
                    ProductGroup.is_deleted == False,  # noqa: E712
                ).first()
                if existing:
                    logger.warning("Product group '%s' already exists", name)
                    return None

                group = ProductGroup(name=name, description=description, is_active=True)
                session.add(group)
                session.commit()
                session.refresh(group)
                return group
            except Exception as e:
                session.rollback()
                logger.error("Failed to create product group '%s': %s", name, e)
                return None

    def update_group(self, group_id: int, data: Dict) -> bool:
        with get_session() as session:
            try:
                group = session.query(ProductGroup).filter(
                    ProductGroup.id == group_id,
                    ProductGroup.is_deleted == False,  # noqa: E712
                ).first()
                if not group:
                    return False

                new_name = data.get('name')
                if new_name and new_name.strip() and new_name.strip() != group.name:
                    clash = session.query(ProductGroup).filter(
                        ProductGroup.name == new_name.strip(),
                        ProductGroup.id != group_id,
                        ProductGroup.is_deleted == False,  # noqa: E712
                    ).first()
                    if clash:
                        logger.warning("Product group name '%s' already taken", new_name)
                        return False
                    group.name = new_name.strip()

                if 'description' in data:
                    group.description = data['description']
                if 'is_active' in data:
                    group.is_active = bool(data['is_active'])

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error("Failed to update product group %s: %s", group_id, e)
                return False

    def delete_group(self, group_id: int) -> bool:
        """Remove a group and every reference to it (members, subscriber links, expense tags)."""
        with get_session() as session:
            try:
                group = session.query(ProductGroup).filter(
                    ProductGroup.id == group_id,
                    ProductGroup.is_deleted == False,  # noqa: E712
                ).first()
                if not group:
                    return False

                session.query(ProductGroupMember).filter(
                    ProductGroupMember.product_group_id == group_id
                ).delete(synchronize_session=False)

                session.query(SubscriberGroup).filter(
                    SubscriberGroup.product_group_id == group_id
                ).delete(synchronize_session=False)

                # Expenses stay, they just stop being scoped to this group.
                session.query(Expense).filter(
                    Expense.product_group_id == group_id,
                    Expense.is_deleted == False,  # noqa: E712
                ).update({'product_group_id': None}, synchronize_session=False)

                group.is_deleted = True
                session.commit()
                logger.info("Deleted product group %s", group_id)
                return True
            except Exception as e:
                session.rollback()
                logger.error("Failed to delete product group %s: %s", group_id, e)
                return False

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------
    def get_member_product_ids(self, group_ids=None) -> Set[int]:
        """Union of product ids across the given groups (all groups when None)."""
        with get_session() as session:
            query = session.query(ProductGroupMember.product_id).join(
                ProductGroup, ProductGroupMember.product_group_id == ProductGroup.id
            ).filter(
                ProductGroup.is_deleted == False,  # noqa: E712
                ProductGroup.is_active == True,  # noqa: E712
            )
            if group_ids is not None:
                group_ids = list(group_ids)
                if not group_ids:
                    return set()
                query = query.filter(ProductGroupMember.product_group_id.in_(group_ids))
            return {row[0] for row in query.all()}

    def get_members(self, group_id: int) -> List[Dict]:
        """Products inside a group (id, name, unit, selling_price)."""
        with get_session() as session:
            rows = session.query(ProfessionalProduct).join(
                ProductGroupMember, ProductGroupMember.product_id == ProfessionalProduct.id
            ).filter(
                ProductGroupMember.product_group_id == group_id,
                ProfessionalProduct.is_deleted == False,  # noqa: E712
            ).order_by(ProfessionalProduct.name).all()

            return [
                {
                    'id': p.id,
                    'name': p.name,
                    'unit': p.unit,
                    'selling_price': p.selling_price,
                    'available_quantity': p.available_quantity,
                }
                for p in rows
            ]

    def set_members(self, group_id: int, product_ids) -> bool:
        """Replace the group's members with exactly `product_ids`."""
        product_ids = {int(pid) for pid in (product_ids or [])}
        with get_session() as session:
            try:
                group = session.query(ProductGroup).filter(
                    ProductGroup.id == group_id,
                    ProductGroup.is_deleted == False,  # noqa: E712
                ).first()
                if not group:
                    return False

                current = {
                    row[0] for row in session.query(ProductGroupMember.product_id).filter(
                        ProductGroupMember.product_group_id == group_id
                    ).all()
                }

                for pid in current - product_ids:
                    session.query(ProductGroupMember).filter(
                        ProductGroupMember.product_group_id == group_id,
                        ProductGroupMember.product_id == pid,
                    ).delete(synchronize_session=False)

                for pid in product_ids - current:
                    session.add(ProductGroupMember(product_group_id=group_id, product_id=pid))

                session.commit()
                logger.info(
                    "Product group %s now has %d member(s)", group_id, len(product_ids)
                )
                return True
            except Exception as e:
                session.rollback()
                logger.error("Failed to set members for group %s: %s", group_id, e)
                return False

    def add_products(self, group_id: int, product_ids) -> bool:
        with get_session() as session:
            try:
                existing = {
                    row[0] for row in session.query(ProductGroupMember.product_id).filter(
                        ProductGroupMember.product_group_id == group_id
                    ).all()
                }
                added = 0
                for pid in {int(p) for p in (product_ids or [])} - existing:
                    session.add(ProductGroupMember(product_group_id=group_id, product_id=pid))
                    added += 1
                session.commit()
                logger.info("Added %d product(s) to group %s", added, group_id)
                return True
            except Exception as e:
                session.rollback()
                logger.error("Failed to add products to group %s: %s", group_id, e)
                return False

    def get_products_for_picker(self, search: str = '', limit: int = 500) -> List[Dict]:
        """Compact product list for the group-member checklist."""
        with get_session() as session:
            query = session.query(ProfessionalProduct).filter(
                ProfessionalProduct.is_deleted == False  # noqa: E712
            )
            if search:
                query = query.filter(ProfessionalProduct.name.ilike(f"%{search}%"))
            products = query.order_by(ProfessionalProduct.name).limit(limit).all()
            return [{'id': p.id, 'name': p.name, 'unit': p.unit} for p in products]

    def count_products(self) -> int:
        """Total active products – used for the '20 of 40 products' scope label."""
        with get_session() as session:
            return session.query(func.count(ProfessionalProduct.id)).filter(
                ProfessionalProduct.is_deleted == False  # noqa: E712
            ).scalar() or 0
