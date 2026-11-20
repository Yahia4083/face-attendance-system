"""Department repository contract."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class DepartmentRepositoryInterface(ABC):
    """Abstraction for department persistence operations."""

    @abstractmethod
    def create(self, *, name: str, description: Optional[str]) -> Any:
        """Create and persist a new department."""
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, department_id: int) -> Optional[Any]:
        """Return a department by id if found."""
        raise NotImplementedError

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Any]:
        """Return a department by normalized name if found."""
        raise NotImplementedError

    @abstractmethod
    def list(
        self,
        *,
        is_active: Optional[bool],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> tuple[list[Any], int]:
        """Return paginated department results and total count."""
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        department_id: int,
        *,
        name: str,
        description: Optional[str],
    ) -> Optional[Any]:
        """Update department fields and return the updated record."""
        raise NotImplementedError

    @abstractmethod
    def set_active(self, department_id: int, *, is_active: bool) -> Optional[Any]:
        """Set department active flag and return the updated record."""
        raise NotImplementedError
