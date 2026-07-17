#!/usr/bin/env python3
from models.engine.database import BaseModel
from sqlalchemy import Column, String, Boolean


class ExpenseCategory(BaseModel):
    __tablename__ = 'expense_categories'

    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<ExpenseCategory(id={self.id}, name='{self.name}')>"