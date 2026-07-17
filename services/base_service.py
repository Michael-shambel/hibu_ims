#!/usr/bin/env python3
"""
BaseService: Generic CRUD service for SQLAlchemy models
"""
from typing import Type, TypeVar, Generic, Optional, List
from sqlalchemy.orm import Session
from models.engine.database import db, BaseModel 
from contextlib import contextmanager
import logging

T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)

@contextmanager
def get_session() -> Session:
    """Context-managed session from db.get_db() generator"""
    session_gen = db.get_db()
    session = next(session_gen)
    try:
        yield session
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass

class BaseService(Generic[T]):
    def __init__(self, model: Type[T]):
        self.model = model

    def get_by_id(self, id: int) -> Optional[T]:
        with get_session() as session:
            try:
                return session.query(self.model).filter(
                    self.model.id == id,
                    self.model.is_deleted == False
                ).first()
            except Exception as e:
                logger.error(f"Error retrieving {self.model.__name__} by ID {id}: {e}")
                return None

    def get_all(self) -> List[T]:
        with get_session() as session:
            try:
                return session.query(self.model).filter(
                    self.model.is_deleted == False
                ).all()
            except Exception as e:
                logger.error(f"Error retrieving all {self.model.__name__} records: {e}")
                return []

    def create(self, data: dict) -> Optional[T]:
        with get_session() as session:
            try:
                obj = self.model(**data)
                session.add(obj)
                session.commit()
                session.refresh(obj)
                return obj
            except Exception as e:
                session.rollback()
                logger.error(f"Error creating {self.model.__name__}: {e}")
                return None

    def update(self, id: int, data: dict) -> Optional[T]:
        with get_session() as session:
            try:
                obj = session.query(self.model).filter(
                    self.model.id == id,
                    self.model.is_deleted == False
                ).first()
                if not obj:
                    logger.warning(f"{self.model.__name__} with ID {id} not found")
                    return None
                for key, value in data.items():
                    setattr(obj, key, value)
                session.commit()
                return obj
            except Exception as e:
                session.rollback()
                logger.error(f"Error updating {self.model.__name__} {id}: {e}")
                return None

    def delete(self, id: int) -> bool:
        with get_session() as session:
            try:
                obj = session.query(self.model).filter(
                    self.model.id == id,
                    self.model.is_deleted == False
                ).first()
                if not obj:
                    return False
                obj.is_deleted = True
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
                return False