"""Use case for creating a department."""

import json

from app.application.dto.department_dto import CreateDepartmentRequest
from app.application.use_cases.exceptions import BadRequestError, ConflictError
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface


class CreateDepartment:
    """Create department use case."""

    def __init__(
        self,
        department_repo: DepartmentRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._department_repo = department_repo
        self._audit_repo = audit_repo

    def execute(self, request: CreateDepartmentRequest):
        name = request.name.strip()
        if not name:
            raise BadRequestError("Department name is required")
        if len(name) < 2 or len(name) > 100:
            raise BadRequestError("Department name must be between 2 and 100 characters")

        description = request.description.strip() if request.description else None
        if description == "":
            description = None

        existing = self._department_repo.get_by_name(name)
        if existing is not None:
            raise ConflictError("Department name already exists")

        department = self._department_repo.create(name=name, description=description)

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="CREATE_DEPARTMENT",
            entity_type="Department",
            entity_id=department.id,
            new_values=json.dumps(
                {
                    "id": department.id,
                    "name": department.name,
                    "description": department.description,
                    "is_active": department.is_active,
                }
            ),
            ip_address=request.ip_address,
        )

        return department
