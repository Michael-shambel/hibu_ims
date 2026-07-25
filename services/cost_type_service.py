#!/usr/bin/env python3
from models.cost_type import CostType
from services.base_service import BaseService, get_session

class CostTypeService(BaseService):
    def __init__(self):
        super().__init__(CostType)

    def get_active(self):
        with get_session() as session:
            return session.query(self.model).filter(
                self.model.is_active==True,
                self.model.is_deleted==False
                ).all()