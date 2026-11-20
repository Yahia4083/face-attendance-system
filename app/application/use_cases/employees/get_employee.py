"""Use case for getting an employee by id."""

from app.application.use_cases.exceptions import NotFoundError
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface


class GetEmployee:
    """Get employee details use case."""

    def __init__(self, employee_repo: EmployeeRepositoryInterface) -> None:
        self._employee_repo = employee_repo

    def execute(self, employee_id: int):
        employee = self._employee_repo.get_by_id(employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        return employee


class GetEmployeeByNumber:
    """Resolve one employee using the official employee number."""

    def __init__(self, employee_repo: EmployeeRepositoryInterface) -> None:
        self._employee_repo = employee_repo

    def execute(self, employee_number: str):
        normalized = employee_number.strip()
        if not normalized:
            raise NotFoundError("Employee not found")
        employee = self._employee_repo.get_by_employee_number(normalized)
        if employee is None:
            raise NotFoundError("Employee not found")
        return employee
