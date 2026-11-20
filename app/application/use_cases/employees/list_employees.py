"""Use case for listing employees."""

from app.application.dto.employee_dto import EmployeeListParams, EmployeeListResult
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface


class ListEmployees:
    """List employees with filtering and pagination."""

    def __init__(self, employee_repo: EmployeeRepositoryInterface) -> None:
        self._employee_repo = employee_repo

    def execute(self, params: EmployeeListParams) -> EmployeeListResult:
        search = params.search.strip() if params.search else None
        if search == "":
            search = None

        items = self._employee_repo.list(
            is_active=params.is_active,
            department_id=params.department_id,
            search=search,
            page=params.page,
            page_size=params.page_size,
        )
        total = self._employee_repo.count(
            is_active=params.is_active,
            department_id=params.department_id,
            search=search,
        )

        return EmployeeListResult(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )
