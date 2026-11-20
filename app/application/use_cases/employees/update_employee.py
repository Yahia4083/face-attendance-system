"""Use case for updating employee basic information."""

import json

from app.application.dto.employee_dto import UpdateEmployeeRequest
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.user_repository import UserRepositoryInterface


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


class UpdateEmployee:
    """Update employee use case."""

    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        user_repo: UserRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._user_repo = user_repo
        self._department_repo = department_repo
        self._audit_repo = audit_repo

    def execute(self, request: UpdateEmployeeRequest):
        existing = self._employee_repo.get_by_id(request.employee_id)
        if existing is None:
            raise NotFoundError("Employee not found")

        email = (
            request.email.strip().lower()
            if request.email is not None
            else existing.user.email.strip().lower()
        )
        duplicate_user = self._user_repo.get_by_email(email)
        if duplicate_user is not None and duplicate_user.id != existing.user_id:
            raise ConflictError("This email address is already used by another account.")

        full_name = request.full_name.strip()
        if not full_name:
            raise BadRequestError("Full name is required")
        if len(full_name) < 2 or len(full_name) > 150:
            raise BadRequestError("Full name must be between 2 and 150 characters")

        phone = request.phone.strip() if request.phone else None
        if phone == "":
            phone = None

        position = request.position.strip() if request.position else None
        if position == "":
            position = None

        department = self._department_repo.get_by_id(request.department_id)
        if department is None:
            raise NotFoundError("Department not found")
        if not department.is_active:
            raise BadRequestError("Department must be active")

        old_values = _serialize_employee(existing)

        updated = self._employee_repo.update(
            request.employee_id,
            email=email,
            full_name=full_name,
            phone=phone,
            position=position,
            department_id=request.department_id,
        )
        if updated is None:
            raise NotFoundError("Employee not found")

        new_values = _serialize_employee(updated)

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="UPDATE_EMPLOYEE",
            entity_type="Employee",
            entity_id=updated.id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(new_values),
            ip_address=request.ip_address,
        )

        return updated
