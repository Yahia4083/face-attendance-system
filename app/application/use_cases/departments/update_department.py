"""Use case for updating department information."""

import json

from app.application.dto.department_dto import UpdateDepartmentRequest
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface


class UpdateDepartment:
    """Update department use case."""

    def __init__(
        self,
        department_repo: DepartmentRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._department_repo = department_repo
        self._audit_repo = audit_repo

    def execute(self, request: UpdateDepartmentRequest):
        existing = self._department_repo.get_by_id(request.department_id)
        if existing is None:
            raise NotFoundError("Department not found")

        name = request.name.strip()
        if not name:
            raise BadRequestError("Department name is required")
        if len(name) < 2 or len(name) > 100:
            raise BadRequestError("Department name must be between 2 and 100 characters")

        description = request.description.strip() if request.description else None
        if description == "":
            description = None

        duplicate = self._department_repo.get_by_name(name)
        if duplicate is not None and duplicate.id != request.department_id:
            raise ConflictError("Department name already exists")

        old_values = {
            "id": existing.id,
            "name": existing.name,
            "description": existing.description,
            "is_active": existing.is_active,
        }

        updated = self._department_repo.update(
            request.department_id,
            name=name,
            description=description,
        )
        if updated is None:
            raise NotFoundError("Department not found")

        new_values = {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "is_active": updated.is_active,
        }

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="UPDATE_DEPARTMENT",
            entity_type="Department",
            entity_id=updated.id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(new_values),
            ip_address=request.ip_address,
        )

        return updated
