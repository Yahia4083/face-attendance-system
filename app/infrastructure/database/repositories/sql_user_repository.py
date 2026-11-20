"""
SQL User Repository
===================
SQLAlchemy implementation of the UserRepositoryInterface.
"""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.enums.user_role import UserRole
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.infrastructure.database.models.user import UserModel


class SqlUserRepository(UserRepositoryInterface):
    """Concrete user repository backed by SQLAlchemy/MySQL."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, user_id: int) -> Optional[UserModel]:
        """Retrieve a user by primary key."""
        return self._db.query(UserModel).filter(UserModel.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[UserModel]:
        """Retrieve a user by email (case-insensitive)."""
        normalized_email = email.strip().lower()
        return (
            self._db.query(UserModel)
            .filter(func.lower(UserModel.email) == normalized_email)
            .first()
        )

    def create_employee_user(
        self,
        *,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.EMPLOYEE,
    ) -> UserModel:
        """Create an employee user account."""
        user = UserModel(
            email=email.strip().lower(),
            password_hash=password_hash,
            role=role,
            is_active=True,
        )
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user

    def activate_user(self, user_id: int) -> Optional[UserModel]:
        """Activate a user account."""
        user = self.get_by_id(user_id)
        if user is None:
            return None
        user.is_active = True
        self._db.commit()
        self._db.refresh(user)
        return user

    def deactivate_user(self, user_id: int) -> Optional[UserModel]:
        """Deactivate a user account."""
        user = self.get_by_id(user_id)
        if user is None:
            return None
        user.is_active = False
        self._db.commit()
        self._db.refresh(user)
        return user

    def replace_password(
        self,
        user_id: int,
        *,
        password_hash: str,
        must_change_password: bool,
    ) -> Optional[UserModel]:
        """Store a new hash and increment the token version."""
        user = self.get_by_id(user_id)
        if user is None:
            return None
        user.password_hash = password_hash
        user.must_change_password = must_change_password
        user.token_version = int(user.token_version or 0) + 1
        self._db.commit()
        self._db.refresh(user)
        return user
