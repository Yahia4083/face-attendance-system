"""
User Repository Interface
=========================
Abstract base class defining the contract for user data access.
Concrete implementations live in the infrastructure layer.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.domain.enums.user_role import UserRole


class UserRepositoryInterface(ABC):
    """Interface for user persistence operations."""

    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[Any]:
        """Retrieve a user by their primary key."""
        raise NotImplementedError

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[Any]:
        """Retrieve a user by their email address."""
        raise NotImplementedError

    @abstractmethod
    def create_employee_user(
        self,
        *,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.EMPLOYEE,
    ) -> Any:
        """Create an EMPLOYEE user account and return it."""
        raise NotImplementedError

    @abstractmethod
    def activate_user(self, user_id: int) -> Optional[Any]:
        """Set user account active flag to True."""
        raise NotImplementedError

    @abstractmethod
    def deactivate_user(self, user_id: int) -> Optional[Any]:
        """Set user account active flag to False."""
        raise NotImplementedError

    @abstractmethod
    def replace_password(
        self,
        user_id: int,
        *,
        password_hash: str,
        must_change_password: bool,
    ) -> Optional[Any]:
        """Replace a password hash and invalidate previously issued tokens."""
        raise NotImplementedError
