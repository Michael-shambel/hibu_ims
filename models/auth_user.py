#!/usr/bin/env python3
"""
AuthUser model: stores users with roles and secure credentials.
"""
from sqlalchemy import Column, String, BigInteger
from models.engine.database import BaseModel

class AuthUser(BaseModel):
    __tablename__ = "auth_users"

    username = Column(String(50), nullable=False, unique=True)
    password = Column(String(128), nullable=False)
    role = Column(String(20), nullable=False, default="admin")
    chat_id = Column(BigInteger, nullable=True, unique=True)

    def __repr__(self):
        return f"<AuthUser(username='{self.username}', role='{self.role}')>"
