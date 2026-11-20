"""Use case for listing departments."""

from app.application.dto.department_dto import DepartmentListParams, DepartmentListResult
from app.domain.repositories.department_repository import DepartmentRepositoryInterface


class ListDepartments:
    """List departments with filtering and pagination."""

    def __init__(self, department_repo: DepartmentRepositoryInterface) -> None:
        self._department_repo = department_repo

    def execute(self, params: DepartmentListParams) -> DepartmentListResult:
        search = params.search.strip() if params.search else None
        if search == "":
            search = None

        items, total = self._department_repo.list(
            is_active=params.is_active,
            search=search,
            page=params.page,
            page_size=params.page_size,
        )

        return DepartmentListResult(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )
