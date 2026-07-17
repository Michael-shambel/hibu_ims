#!/usr/bin/env python3
"""
CustomerService
"""
from sqlalchemy import func
from services.base_service import BaseService, get_session
from models.customers import Customer
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

class CustomerService(BaseService[Customer]):
    def __init__(self):
        super().__init__(Customer)
    def get_by_id(self, id: str) -> Optional[Customer]: # type: ignore
        with get_session() as session:
            try:
                return session.query(Customer).filter(
                    Customer.id == id,
                    Customer.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting customer by id: {e}")
                return None

    def get_by_phone(self, phone: str) -> Optional[Customer]:
        with get_session() as session:
            try:
                return session.query(Customer).filter(
                    Customer.phone == phone,
                    Customer.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting customer by phone: {e}")
                return None
    
    
    def search(self, query: str) -> List[Customer]:
        with get_session() as session:
            try:
                search_term = f"%{query}%"
                return session.query(Customer).filter(
                    Customer.is_deleted == False,
                    (
                        Customer.name.ilike(search_term) |
                        Customer.phone.ilike(search_term) |
                        Customer.email.ilike(search_term) |
                        Customer.tin_num.ilike(search_term)
                    )
                ).order_by(Customer.name).all()
            except Exception as e:
                logger.error(f"Error searching customers: {e}")
                return []
    
    def create(self, data: dict) -> Optional[Customer]:
        tin_num = data.get('tin_num')
        if tin_num and self.get_by_tin(tin_num):
            logger.warning(f"Customer creation failed: Tin Number {tin_num} already exists")
            return None
            
        return super().create(data)
    
    def update(self, id: int, data: dict) -> Optional[Customer]:
                
        return super().update(id, data)
    
    def get_by_name(self, name: str) -> Optional[Customer]:
        with get_session() as session:
            try:
                return session.query(Customer).filter(
                    func.lower(Customer.name) == func.lower(name),
                    Customer.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting customers by name: {e}")
                return [] # type: ignore
    
    def get_by_chat_id(self, chat_id: int):
        with get_session() as session:
            try:
                return session.query(Customer).filter(
                    Customer.chat_id == chat_id,
                    Customer.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting customer by chat_id: {e}")
                return None
    
    def register_chat_id(self, phone: str, chat_id: int) -> Optional[Customer]:
        with get_session() as session:
            try:
                # 1. Find customer by phone (active, not deleted)
                customer = session.query(Customer).filter(
                    Customer.phone == phone,
                    Customer.is_deleted == False
                ).first()
                if not customer:
                    logger.warning(f"Customer with phone {phone} not found")
                    return None

                # 2. If already linked to this chat_id → success
                if customer.chat_id == chat_id:
                    logger.info(f"Customer {customer.name} already linked to chat_id {chat_id}")
                    return customer

                # 3. If customer already has a different chat_id → reject (non-updateable)
                if customer.chat_id is not None and customer.chat_id != chat_id:
                    logger.warning(f"Customer {customer.name} already linked to another chat_id {customer.chat_id}. Cannot change.")
                    return None

                # 4. Check if this chat_id is already used by another active customer
                existing_chat = session.query(Customer).filter(
                    Customer.chat_id == chat_id,
                    Customer.is_deleted == False,
                    Customer.id != customer.id
                ).first()
                if existing_chat:
                    logger.warning(f"Chat_id {chat_id} already belongs to customer {existing_chat.name}")
                    return None

                # 5. Also clear chat_id from any soft-deleted customers (optional cleanup)
                deleted_with_chat = session.query(Customer).filter(
                    Customer.chat_id == chat_id,
                    Customer.is_deleted == True
                ).all()
                for del_cust in deleted_with_chat:
                    del_cust.chat_id = None
                    logger.info(f"Cleared chat_id from deleted customer {del_cust.name}")

                # 6. All good – assign chat_id
                customer.chat_id = chat_id
                session.commit()
                logger.info(f"Linked chat_id {chat_id} to customer {customer.name} (phone {phone})")
                return customer

            except Exception as e:
                session.rollback()
                logger.error(f"Error registering chat_id for phone {phone}: {e}")
                return None