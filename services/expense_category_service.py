#!/usr/bin/env python3

from services.base_service import BaseService, get_session
import logging
from typing import Optional, List
from models.expense_category import ExpenseCategory

logger = logging.getLogger(__name__)


class ExpenseCategoryService(BaseService[ExpenseCategory]):
    def __init__(self):
        super().__init__(ExpenseCategory)
        self.expense_category_service = ExpenseCategory()
    
    def get_active(self) -> List[ExpenseCategory]:
        with get_session() as session:
            try:
                return session.query(self.model).filter(
                    self.model.is_deleted == False,
                    self.model.is_active == True
                ).all()
            except Exception as e:
                logger.error(f"Error getting active expense categories: {e}")
                return []
    
    def get_by_name(self, name: str) -> Optional[ExpenseCategory]:
        """Retrieve a category by its exact name (case-sensitive)."""
        with get_session() as session:
            try:
                return session.query(self.model).filter(
                    self.model.name == name,
                    self.model.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error getting expense category by name '{name}': {e}")
                return None