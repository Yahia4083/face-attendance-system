"""Use case for activating a department."""

import json

from app.application.dto.department_dto import DepartmentStateChangeRequest
from app.application.use_cases.exceptions import NotFoundError
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface


class ActivateDepartment:
    """Activate department use case."""

    def __init__(
        self,
        department_repo: DepartmentRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._department_repo = department_repo
        self._audit_repo = audit_repo

    def execute(self, request: DepartmentStateChangeRequest):
        existing = self._department_repo.get_by_id(request.department_id)
        if existing is None:
            raise NotFoundError("Department not found")
        previous_is_active = existing.is_active

        updated = self._department_repo.set_active(request.department_id, is_active=True)
        if updated is None:
            raise NotFoundError("Department not found")

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ACTIVATE_DEPARTMENT",
            entity_type="Department",
            entity_id=updated.id,
            old_values=json.dumps({"is_active": previous_is_active}),
            new_values=json.dumps({"is_active": updated.is_active}),
            ip_address=request.ip_address,
        )

        return updated
