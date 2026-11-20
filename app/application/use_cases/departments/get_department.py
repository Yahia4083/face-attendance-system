"""Use case for getting a department by id."""

from app.application.use_cases.exceptions import NotFoundError
from app.domain.repositories.department_repository import DepartmentRepositoryInterface


class GetDepartment:
    """Get department details use case."""

    def __init__(self, department_repo: DepartmentRepositoryInterface) -> None:
        self._department_repo = department_repo

    def execute(self, department_id: int):
        department = self._department_repo.get_by_id(department_id)
        if department is None:
            raise NotFoundError("Department not found")
        return department
