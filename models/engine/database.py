#!/usr/bin/env python3
"""
Production-ready SQLAlchemy SQLite Engine Setup
- Error handling
- Session management
- Base and BaseModel separation
"""

import os
import logging
from typing import Generator
from sqlalchemy import create_engine, MetaData, Column, DateTime, Integer, Boolean, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func
from utils import resource_path
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Robust database setup with base model"""

    def __init__(self):
        self.engine = self._create_engine()
        self.SessionLocal = self._create_session()
        self.Base, self.BaseModel = self._create_base()

    def _create_engine(self):
        try:
            """
            for integrating diffent type of drelational database
            it will help to work with differnt environment
            """
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_dir = os.path.join(project_root, "database")
            os.makedirs(db_dir, exist_ok=True)
            # FIXED: Direct database path
            from utils import get_database_path
            db_path = get_database_path("inventory.db")
            db_url = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")
            """
            create the interfaae b/n sqlalchemy and database
                1)connection
                2)translation sqlalchemt to db specific
                3)execution
            """
            engine = create_engine(
                db_url,
                echo=False,
                connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
            )
            logger.info("Database engine initialized")
            return engine

        except SQLAlchemyError as e:
            logger.critical(f"SQLAlchemy error during engine creation: {e}")
            raise


    def _create_session(self):
        """Configure session factory"""
        return sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )

    def _create_base(self):
        """
        Define Base and BaseModel classes
        we use _prefix indicates internal implementation 
        MetaData sqlalchemy cataloge of databse which
            1)track all tables, column
        blueprint of your database structure
        declarative_base():- createbase class for ORM models
        """
        metadata = MetaData()
        Base = declarative_base(metadata=metadata)

        class BaseModel(Base):
            """
            __abstract__ makes this a template class
            sqlalchemy wontcreate table for this class srve as parent for concretemodels
            which prevent empty table creation
            also makes the table not to reapeat
            """
            __abstract__ = True
            
            id = Column(Integer, primary_key=True)
            uuid = Column(
                String(36),
                default=lambda: str(uuid.uuid4()),
                unique=True,
                nullable=True,
                index=True
            )
            created_at = Column(DateTime, server_default=func.now())
            last_modified = Column(DateTime, onupdate=func.now(), server_default=func.now(), nullable=False)
            is_deleted = Column(Boolean, default=False, server_default="0")

            def __repr__(self):
                return f"<{self.__class__.__name__}(id={getattr(self, 'id', None)})>"

        logger.info("Base and BaseModel configured")
        return Base, BaseModel

    def get_db(self) -> Generator[Session, None, None]:
        """Yield a database session"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()


db = DatabaseManager()
Base = db.Base
BaseModel = db.BaseModel
SessionLocal = db.SessionLocal
get_db = db.get_db
