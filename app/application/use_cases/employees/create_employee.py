"""Use case for creating an employee and linked user account."""

import json

from app.application.dto.employee_dto import CreateEmployeeRequest
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.domain.enums.user_role import UserRole
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.infrastructure.security.password_hasher import hash_password


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


class CreateEmployee:
    """Create employee use case."""

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

    def execute(self, request: CreateEmployeeRequest):
        email = request.email.strip().lower()
        if not email:
            raise BadRequestError("Employee email is required")

        if len(request.password) < 6:
            raise BadRequestError("Password must be at least 6 characters")

        full_name = request.full_name.strip()
        if not full_name:
            raise BadRequestError("Full name is required")
        if len(full_name) < 2 or len(full_name) > 150:
            raise BadRequestError("Full name must be between 2 and 150 characters")

        employee_number = request.employee_number.strip()
        if not employee_number:
            raise BadRequestError("Employee number is required")
        if len(employee_number) < 2 or len(employee_number) > 50:
            raise BadRequestError("Employee number must be between 2 and 50 characters")

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

        if self._user_repo.get_by_email(email) is not None:
            raise ConflictError("Employee email already exists")

        if self._employee_repo.get_by_employee_number(employee_number) is not None:
            raise ConflictError("Employee number already exists")

        password_hash = hash_password(request.password)

        employee = self._employee_repo.create_employee_with_user(
            email=email,
            password_hash=password_hash,
            role=UserRole.EMPLOYEE,
            full_name=full_name,
            employee_number=employee_number,
            phone=phone,
            position=position,
            department_id=request.department_id,
        )

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="CREATE_EMPLOYEE",
            entity_type="Employee",
            entity_id=employee.id,
            new_values=json.dumps(_serialize_employee(employee)),
            ip_address=request.ip_address,
        )

        return employee
