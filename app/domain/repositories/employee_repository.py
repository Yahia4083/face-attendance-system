"""Employee repository contract."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.domain.enums.user_role import UserRole


class EmployeeRepositoryInterface(ABC):
    """Abstraction for employee and linked user persistence operations."""

    @abstractmethod
    def create_employee_with_user(
        self,
        *,
        email: str,
        password_hash: str,
        role: UserRole,
        full_name: str,
        employee_number: str,
        phone: Optional[str],
        position: Optional[str],
        department_id: int,
    ) -> Any:
        """Create a linked user + employee record transactionally."""
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, employee_id: int) -> Optional[Any]:
        """Return employee by id with linked user and department."""
        raise NotImplementedError

    @abstractmethod
    def get_by_user_id(self, user_id: int) -> Optional[Any]:
        """Return employee linked to a user id if found."""
        raise NotImplementedError

    @abstractmethod
    def get_by_employee_number(self, employee_number: str) -> Optional[Any]:
        """Return employee by employee number if found."""
        raise NotImplementedError

    @abstractmethod
    def list(
        self,
        *,
        is_active: Optional[bool],
        department_id: Optional[int],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> list[Any]:
        """Return paginated employee results."""
        raise NotImplementedError

    @abstractmethod
    def count(
        self,
        *,
        is_active: Optional[bool],
        department_id: Optional[int],
        search: Optional[str],
    ) -> int:
        """Return filtered employee count."""
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        employee_id: int,
        *,
        email: str,
        full_name: str,
        phone: Optional[str],
        position: Optional[str],
        department_id: int,
    ) -> Optional[Any]:
        """Update employee and linked account fields transactionally."""
        raise NotImplementedError

    @abstractmethod
    def activate(self, employee_id: int) -> Optional[Any]:
        """Activate employee and linked user."""
        raise NotImplementedError

    @abstractmethod
    def deactivate(self, employee_id: int) -> Optional[Any]:
        """Deactivate employee and linked user."""
        raise NotImplementedError
