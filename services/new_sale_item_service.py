#!/usr/bin/env python3


from services.base_service import BaseService, get_session
from models.new_sale_item import ProfessionalSaleItem
import logging
from typing import List

logger = logging.getLogger(__name__)


class NewSaleItemService(BaseService[ProfessionalSaleItem]):
    def __init__(self):
        super().__init__(ProfessionalSaleItem)
    

    def create_with_session(self, session, data: dict):
        obj = ProfessionalSaleItem(**data)
        session.add(obj)
        return obj
    
    def mark_item_despatched(self, item_id: int) -> bool:
        """Mark a single sale item as despatched."""
        with get_session() as session:
            try:
                item = session.query(self.model).get(item_id)
                if not item or item.is_deleted:
                    return False
                item.for_despatch = True
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error marking item {item_id} despatched: {e}")
                return False
    
    def get_items_by_sales_and_product(self, sale_ids: List[int], product_id: int):
        """
        Retrieve sale items for a list of sale IDs and a specific product ID.
        Returns a list of ProfessionalSaleItem objects.
        """
        from services.base_service import get_session
        from models.new_sale_item import ProfessionalSaleItem
        from models.product_batch import ProductBatch

        with get_session() as session:
            return session.query(ProfessionalSaleItem).join(
                ProductBatch, ProfessionalSaleItem.batch_id == ProductBatch.id
            ).filter(
                ProfessionalSaleItem.sale_id.in_(sale_ids),
                ProductBatch.product_id == product_id,
                ProfessionalSaleItem.is_deleted == False
            ).all()