#!/usr/bin/env python3
"""
CostType model – stores predefined cost types for import shipments.
"""
from sqlalchemy import Column, String, Boolean
from models.engine.database import BaseModel


class CostType(BaseModel):
    __tablename__ = "cost_types"

    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<CostType(id={self.id}, name='{self.name}')>"