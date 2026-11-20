"""Use case for deactivating employees."""

import json

from app.application.dto.employee_dto import EmployeeStateChangeRequest
from app.application.use_cases.exceptions import NotFoundError
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface


def _serialize_employee(employee) -> dict:
    return {
        "id": employee.id,
        "user_id": employee.user_id,
        "email": employee.user.email if employee.user else None,
        "department_id": employee.department_id,
        "department_name": employee.department.name if employee.department else None,
        "full_name": employee.full_name,
        "employee_number": employee.employee_number,
        "phone": employee.phone,
        "position": employee.position,
        "is_active": employee.is_active,
        "user_is_active": employee.user.is_active if employee.user else None,
    }


class DeactivateEmployee:
    """Deactivate employee use case."""

    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._audit_repo = audit_repo

    def execute(self, request: EmployeeStateChangeRequest):
        existing = self._employee_repo.get_by_id(request.employee_id)
        if existing is None:
            raise NotFoundError("Employee not found")

        old_values = _serialize_employee(existing)

        updated = self._employee_repo.deactivate(request.employee_id)
        if updated is None:
            raise NotFoundError("Employee not found")

        new_values = _serialize_employee(updated)

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="DEACTIVATE_EMPLOYEE",
            entity_type="Employee",
            entity_id=updated.id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(new_values),
            ip_address=request.ip_address,
        )

        return updated
