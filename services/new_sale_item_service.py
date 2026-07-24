#!/usr/bin/env python3


from services.base_service import BaseService, get_session
from models.new_sale_item import ProfessionalSaleItem
import logging
from typing import List
from datetime import datetime, date

logger = logging.getLogger(__name__)


class NewSaleItemService(BaseService[ProfessionalSaleItem]):
    def __init__(self):
        super().__init__(ProfessionalSaleItem)
    

    def create_with_session(self, session, data: dict):
        obj = ProfessionalSaleItem(**data)
        session.add(obj)
        return obj
    
    def mark_item_despatched(self, item_id: int) -> bool:
        with get_session() as session:
            try:
                item = session.query(self.model).filter(
                    self.model.id == item_id,
                    self.model.is_deleted == False
                ).first()
                if not item:
                    logger.warning(f"Item {item_id} not found")
                    return False

                item.for_despatch = True
                item.despatched_at = datetime.utcnow()

                # Make sure the update above is actually visible to the count
                # query below, regardless of the session's autoflush setting.
                session.flush()

                pending = session.query(self.model).filter(
                    self.model.sale_id == item.sale_id,
                    self.model.is_deleted == False,
                    self.model.for_despatch == False,
                    self.model.id != item.id,  # belt-and-braces: never count the item we just marked
                ).count()

                logger.debug(f"Item {item_id} marked. Sale {item.sale_id} has {pending} pending items.")

                if pending == 0:
                    from models.new_sales import ProfessionalSale
                    sale = session.query(ProfessionalSale).filter(
                        ProfessionalSale.id == item.sale_id
                    ).first()
                    if sale and not sale.despatch_date:
                        sale.despatch_date = date.today()
                        logger.debug(f"Set despatch_date = {sale.despatch_date} for sale {sale.id}")

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error marking item {item_id} despatched: {e}", exc_info=True)
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
    
    def get_pending_items_for_sale(self, sale_id: int) -> List[ProfessionalSaleItem]:
        """Return all non‑deleted items of a sale that are not yet despatched."""
        with get_session() as session:
            return session.query(self.model).filter(
                self.model.sale_id == sale_id,
                self.model.is_deleted == False,
                self.model.for_despatch == False
            ).all()