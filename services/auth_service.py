#!/usr/bin/env python3
"""
AuthService: Handles admin login logic
"""

import hashlib
import hmac
import logging
from typing import Optional
from services.base_service import BaseService, get_session
from models.auth_user import AuthUser
from sqlalchemy import exc
import time

logger = logging.getLogger(__name__)

class AuthService(BaseService[AuthUser]):
    def __init__(self):
        super().__init__(AuthUser)

    def hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def check_password(self, raw: str, hashed: str) -> bool:
        return hmac.compare_digest(self.hash_password(raw), hashed)

    def authenticate_user(self, username: str, password: str) -> bool:
        with get_session() as session:
            user = session.query(AuthUser).filter_by(
                username=username,
                # role="admin",
                is_deleted=False
            ).first()

            if user and self.check_password(password, user.password):
                return True

            logger.warning("Authentication failed for username: %s", username)
            return False

    def create_admin_if_not_exists(self, username: str, password: str) -> Optional[AuthUser]:
        with get_session() as session:
            existing = session.query(AuthUser).filter_by(role="admin", is_deleted=False).first()
            if existing:
                logger.info("Admin already exists.")
                return None

            hashed_pw = self.hash_password(password)
            admin = AuthUser(username=username, password=hashed_pw, role="admin")
            session.add(admin)
            session.commit()
            session.refresh(admin)
            logger.info("Admin created with username: %s", username)
            return admin
    
    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        with get_session() as session:
            user = session.query(AuthUser).filter_by(username=username, is_deleted=False).first()

            if not user:
                return False

            if not self.check_password(old_password, user.password):
                return False

            user.password = self.hash_password(new_password)
            session.commit()
            return True
    
    def get_by_chat_id(self, chat_id: int) -> Optional[AuthUser]:
        """
        retrive user by chat id
        """
        with get_session() as session:
            try:
                return session.query(AuthUser).filter(
                    AuthUser.chat_id == chat_id,
                    AuthUser.is_deleted == False
                ).first()
            except Exception:
                logger.error(f"Failed to get user with chat id: {chat_id}")
                return None
    
    def register_chat_id(self, username: str, password: str, chat_id: int) -> Optional[AuthUser]:
        with get_session() as session:
            try:
                # Clear chat_id from any soft-deleted users that still have this chat_id
                deleted_users_with_chat = session.query(AuthUser).filter(
                    AuthUser.chat_id == chat_id,
                    AuthUser.is_deleted == True
                ).all()
                
                for deleted_user in deleted_users_with_chat:
                    deleted_user.chat_id = None
                    logger.info(f"Cleared chat_id from deleted user: {deleted_user.username}")
                
                if deleted_users_with_chat:
                    session.flush()  # Apply changes before proceeding
                
                user = session.query(AuthUser).filter(
                    AuthUser.username == username,
                    AuthUser.is_deleted == False
                ).first()

                if not user:
                    logger.error(f"Sales team user not found: {username}")
                    return None
                
                if not self.check_password(password, user.password):
                    logger.warning(f"Invalid password for user: {username}")
                    return None
                
                # Check if chat_id is already registered to THIS user
                if user.chat_id == chat_id:
                    logger.info(f"User {username} already has this chat_id registered")
                    return user
                
                # Check if chat_id is registered to ANOTHER active user
                existing_chat = session.query(AuthUser).filter(
                    AuthUser.chat_id == chat_id,
                    AuthUser.is_deleted == False
                ).first()

                if existing_chat:
                    if existing_chat.id == user.id:
                        return user
                    else:
                        # Different user has this chat_id
                        logger.warning(f"chat id {chat_id} is already registered to {existing_chat.username}")
                        return None
                
                # Safe to register
                user.chat_id = chat_id
                session.commit()
                logger.info(f"Successfully registered chat ID {chat_id} for salesperson {user.username}")
                return user

            except exc.IntegrityError as e:
                session.rollback()
                
                # Double-check: maybe it's already registered to this user due to race condition
                session.expire_all()
                user_check = session.query(AuthUser).filter(
                    AuthUser.username == username,
                    AuthUser.is_deleted == False
                ).first()
                
                if user_check and user_check.chat_id == chat_id:
                    logger.info(f"User {username} chat_id was already registered (caught in integrity error)")
                    return user_check
                
                logger.warning(f"Integrity error during registration: {e}")
                return None
            except Exception as e:
                session.rollback()
                logger.error(f"Error registering chat ID: {e}")
                return None
    
    def register_chat_id_safe(self, username: str, password: str, chat_id: int, max_retries: int = 3) -> Optional[AuthUser]:
        """
        Safe registration with retry logic
        """
        for attempt in range(max_retries):
            try:
                result = self.register_chat_id(username, password, chat_id)
                if result:
                    return result
                
                # If we got here, registration failed for business logic reasons
                # Let's check why and provide appropriate feedback
                final_username_check = self.get_by_username(username)
                final_chat_check = self.get_by_chat_id(chat_id)
                
                if final_username_check and final_username_check.chat_id:
                    logger.warning(f"Phone {username} already registered to someone else")
                    return None
                    
                if final_chat_check:
                    logger.warning(f"Chat ID {chat_id} already registered to {final_chat_check.username}")
                    return None
                
                # If it's not a clear business logic failure, retry
                if attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying registration in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.warning("Max retries exceeded for registration")
                    return None
                    
            except Exception as e:
                logger.error(f"Unexpected error during registration attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(0.1 * (2 ** attempt))
        
        return None
    
    def get_by_username(self, username: str) -> Optional[AuthUser]:
        with get_session() as session:
            return session.query(AuthUser).filter_by(username=username, is_deleted=False).first()
    
    def create(self, user: AuthUser) -> bool:
        """Create a new user"""
        try:
            with get_session() as session:
                session.add(user)
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False
    
    def delete(self, user_id: int) -> bool:
        """Soft delete user and clear chat_id"""
        try:
            with get_session() as session:
                user = session.query(AuthUser).filter_by(id=user_id).first()
                if user:
                    user.is_deleted = True
                    user.chat_id = None  # Clear chat_id so it can be reused
                    session.commit()
                    return True
            return False
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False
    
    def get_by_id(self, user_id: int) -> Optional[AuthUser]:
        """Get user by ID"""
        with get_session() as session:
            return session.query(AuthUser).filter_by(id=user_id, is_deleted=False).first()
    
    def get_admin_user(self) -> Optional[AuthUser]:
        """Get an admin user (for verification)"""
        with get_session() as session:
            return session.query(AuthUser).filter_by(role="admin", is_deleted=False).first()
    
    def update(self, user_id: int, update_data: dict) -> bool:
        """Update user data"""
        try:
            with get_session() as session:
                user = session.query(AuthUser).filter_by(id=user_id).first()
                if user:
                    for key, value in update_data.items():
                        setattr(user, key, value)
                    session.commit()
                    return True
            return False
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return False

    def update_password(self, user_id: int, new_password: str) -> bool:
        """Update user password"""
        try:
            with get_session() as session:
                user = session.query(AuthUser).filter_by(id=user_id).first()
                if user:
                    user.password = self.hash_password(new_password)
                    session.commit()
                    return True
            return False
        except Exception as e:
            logger.error(f"Error updating password: {e}")
            return False