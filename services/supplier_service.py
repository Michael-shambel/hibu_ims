#!/usr/bin/env python3
"""
SupplierService
"""
from services.base_service import BaseService, get_session
from models.supplier import Supplier
from models.customers import Customer
from typing import Optional, List
import logging
import json

logger = logging.getLogger(__name__)

class SupplierService(BaseService[Supplier]):
    """
    Service for managing Supplier records
    Provides methods to retrieve suppliers by name, contact phone, and search by query.
    Inherits from BaseService for generic CRUD operations.
    This service is specifically tailored for the Supplier model.
    """
    def __init__(self):
        """
        Initialize the SupplierService with the Supplier model
        """
        super().__init__(Supplier)

    def get_by_name(self, name: str) -> Optional[Supplier]:
        """
        Retrieve a supplier by their name
        :param name: Name of the supplier to retrieve
        :return: Supplier object if found, None otherwise
        """
        with get_session() as session:
            try:
                return session.query(Supplier).filter(
                    Supplier.supplier_name.ilike(f"%{name}%"),
                    Supplier.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting supplier by name: {e}")
                return None

    def get_by_contact_phone(self, phone: str) -> Optional[Supplier]:
        """
        Retrieve a supplier by their contact phone number
        :param phone: Contact phone number of the supplier to retrieve
        :return: Supplier object if found, None otherwise
        """
        with get_session() as session:
            try:
                return session.query(Supplier).filter(
                    Supplier.contact_phone == phone,
                    Supplier.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting supplier by phone: {e}")
                return None

    def search(self, query: str) -> List[Supplier]:
        """
        Search for suppliers by name, contact phone, or email using a query string.
        :param query: Search query string
        :return: List of suppliers matching the search criteria
        """
        with get_session() as session:
            try:
                return session.query(Supplier).filter(
                    Supplier.is_deleted == False,
                    (
                        Supplier.supplier_name.ilike(f"%{query}%") |
                        Supplier.contact_phone.ilike(f"%{query}%") |
                        Supplier.email.ilike(f"%{query}%")
                    )
                ).all()
            except Exception as e:
                logger.error(f"Error searching suppliers: {e}")
                return []

    def get_by_id(self, id: int | str) -> Optional[Supplier]:
        """
        """
        with get_session() as session:
            try:
                return session.query(Supplier).filter(
                    Supplier.id == id,
                    Supplier.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting Supplier by id: {e}")
                return None
    
    def get_by_chat_id(self, chat_id: int) -> Optional[Supplier]:
        """Retrieve a supplier by their Telegram chat_id."""
        with get_session() as session:
            try:
                return session.query(Supplier).filter(
                    Supplier.chat_id == chat_id,
                    Supplier.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting supplier by chat_id: {e}")
                return None

    def register_chat_id(self, phone: str, chat_id: int) -> Optional[Supplier]:
        """
        Link a Telegram chat_id to an existing supplier using their contact phone.
        Returns supplier if successful, None otherwise.
        """
        with get_session() as session:
            try:
                supplier = session.query(Supplier).filter(
                    Supplier.contact_phone == phone,
                    Supplier.is_deleted == False
                ).first()
                if not supplier:
                    logger.warning(f"Supplier with phone {phone} not found")
                    return None

                if supplier.chat_id == chat_id:
                    return supplier

                if supplier.chat_id is not None and supplier.chat_id != chat_id:
                    logger.warning(f"Supplier {supplier.supplier_name} already has chat_id {supplier.chat_id}")
                    return None

                existing_chat = session.query(Supplier).filter(
                    Supplier.chat_id == chat_id,
                    Supplier.is_deleted == False,
                    Supplier.id != supplier.id
                ).first()
                if existing_chat:
                    logger.warning(f"Chat_id {chat_id} already belongs to supplier {existing_chat.supplier_name}")
                    return None

                # Clear chat_id from soft‑deleted suppliers (optional)
                session.query(Supplier).filter(
                    Supplier.chat_id == chat_id,
                    Supplier.is_deleted == True
                ).update({Supplier.chat_id: None})

                supplier.chat_id = chat_id
                session.commit()
                logger.info(f"Linked chat_id {chat_id} to supplier {supplier.supplier_name}")
                return supplier

            except Exception as e:
                session.rollback()
                logger.error(f"Error registering chat_id for phone {phone}: {e}")
                return None
  
    def get_all_notification_chat_ids(self, supplier_id: int) -> list:
        """Return a list of all chat IDs that should receive notifications."""
        supplier = self.get_by_id(supplier_id)
        if not supplier:
            return []

        ids = []
        if supplier.chat_id is not None:
            ids.append(supplier.chat_id)

        if supplier.additional_chat_ids:
            # If column is JSON, it's already a list.
            # If column is Text, load it.
            data = supplier.additional_chat_ids
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except:
                    pass
            if isinstance(data, list):
                for cid in data:
                    if cid and cid not in ids:
                        ids.append(cid)

        return ids

    def get_by_any_chat_id(self, chat_id: int) -> Optional[Supplier]:
        """Find supplier by primary chat_id OR by additional_chat_ids list."""
        with get_session() as session:
            # Primary
            supplier = session.query(Supplier).filter(
                Supplier.chat_id == chat_id,
                Supplier.is_deleted == False
            ).first()
            if supplier:
                return supplier

            # Search inside additional_chat_ids
            suppliers = session.query(Supplier).filter(
                Supplier.is_deleted == False,
                Supplier.additional_chat_ids.isnot(None)
            ).all()

            for s in suppliers:
                data = s.additional_chat_ids
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except:
                        continue
                if chat_id in (data or []):
                    return s
            return None

    def create(self, data: dict) -> Optional[Supplier]:
        # Normalize additional_chat_ids (existing logic)
        self._normalize_additional_chat_ids(data)

        with get_session() as session:
            try:
                # 1. Create the supplier
                supplier = Supplier(**data)
                session.add(supplier)
                session.flush()

                # 2. Map to customer
                phone = supplier.contact_phone
                if phone:
                    # Check if a customer with this phone already exists
                    existing_customer = session.query(Customer).filter(
                        Customer.phone == phone,
                        Customer.is_deleted == False
                    ).first()

                    if existing_customer:
                        # Update customer name (in case supplier name changed)
                        existing_customer.name = supplier.supplier_name
                        logger.info(f"Updated existing customer (ID {existing_customer.id}) with supplier name")
                    else:
                        # Create a new customer
                        new_customer = Customer(
                            name=supplier.supplier_name,
                            phone=phone
                        )
                        session.add(new_customer)
                        logger.info(f"Created new customer for supplier {supplier.supplier_name}")

                # 3. Commit both in one transaction
                session.commit()
                session.refresh(supplier)
                return supplier

            except Exception as e:
                session.rollback()
                logger.error(f"Error creating supplier and customer: {e}")
                return None

    def update(self, id: int, data: dict) -> Optional[Supplier]:
        self._normalize_additional_chat_ids(data)
        return super().update(id, data)

    def _normalize_additional_chat_ids(self, data: dict):
        """Convert a comma-separated string to a list of integers.
        If the column is Text, store as JSON string instead."""
        raw = data.get('additional_chat_ids')
        if isinstance(raw, str) and raw.strip():
            ids = [int(x.strip()) for x in raw.split(',') if x.strip().isdigit()]
            # If your column is JSON, store the list directly:
            data['additional_chat_ids'] = ids if ids else None
            # Uncomment the next line and comment the above if column is Text:
            # data['additional_chat_ids'] = json.dumps(ids) if ids else None
        elif isinstance(raw, list):
            data['additional_chat_ids'] = raw
        else:
            data['additional_chat_ids'] = None