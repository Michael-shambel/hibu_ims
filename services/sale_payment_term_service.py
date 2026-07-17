#!/usr/bin/env python3
import logging
from models.sale_payment_term import SalePaymentTerm
from services.base_service import BaseService, get_session

logger = logging.getLogger(__name__)

class SalePaymentTermService(BaseService[SalePaymentTerm]):
    def __init__(self):
        super().__init__(SalePaymentTerm)
    
    def create_with_session(self, session, data: dict):
        obj = SalePaymentTerm(**data)
        session.add(obj)
        return obj