"""Password policy and account password-management use cases."""

import json
import re
from typing import Callable

from app.application.dto.auth_dto import (
    ChangeOwnPasswordRequest,
    ResetEmployeePasswordRequest,
)
from app.application.use_cases.exceptions import BadRequestError, NotFoundError
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.infrastructure.security.password_hasher import hash_password, verify_password


def validate_password_policy(password: str) -> None:
    """Validate passwords used by change and reset operations."""
    if len(password) < 8:
        raise BadRequestError("Password must contain at least 8 characters.")
    if not (
        re.search(r"[A-Z]", password)
        and re.search(r"[a-z]", password)
        and re.search(r"\d", password)
        and re.search(r"[^A-Za-z0-9]", password)
    ):
        raise BadRequestError(
            "Password must include an uppercase letter, a lowercase letter, "
            "a number, and a special character."
        )


class ChangeOwnPassword:
    """Change the authenticated user's password and revoke older tokens."""

    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        password_verifier: Callable[[str, str], bool] = verify_password,
        password_hasher: Callable[[str], str] = hash_password,
    ) -> None:
        self._user_repo = user_repo
        self._audit_repo = audit_repo
        self._password_verifier = password_verifier
        self._password_hasher = password_hasher

    def execute(self, request: ChangeOwnPasswordRequest):
        user = self._user_repo.get_by_id(request.user_id)
        if user is None:
            raise NotFoundError("User account not found.")
        if not user.is_active:
            raise BadRequestError("Account is inactive.")
        if not self._password_verifier(request.current_password, user.password_hash):
            raise BadRequestError("Current password is incorrect.")
        if request.new_password != request.confirm_password:
            raise BadRequestError("New password and confirmation do not match.")
        if self._password_verifier(request.new_password, user.password_hash):
            raise BadRequestError("New password must be different from the current password.")

        validate_password_policy(request.new_password)
        updated = self._user_repo.replace_password(
            user.id,
            password_hash=self._password_hasher(request.new_password),
            must_change_password=False,
        )
        if updated is None:
            raise NotFoundError("User account not found.")

        self._audit_repo.log(
            actor_user_id=user.id,
            action="CHANGE_OWN_PASSWORD",
            entity_type="User",
            entity_id=user.id,
            new_values=json.dumps(
                {
                    "sessions_invalidated": True,
                    "must_change_password": False,
                }
            ),
            ip_address=request.ip_address,
        )
        return updated


class ResetEmployeePassword:
    """Reset a linked employee account password without exposing the old one."""

    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        user_repo: UserRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        password_hasher: Callable[[str], str] = hash_password,
    ) -> None:
        self._employee_repo = employee_repo
        self._user_repo = user_repo
        self._audit_repo = audit_repo
        self._password_hasher = password_hasher

    def execute(self, request: ResetEmployeePasswordRequest):
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found.")
        user = getattr(employee, "user", None)
        if user is None:
            raise NotFoundError("Employee user account not found.")
        if request.new_password != request.confirm_password:
            raise BadRequestError("New password and confirmation do not match.")

        validate_password_policy(request.new_password)
        updated = self._user_repo.replace_password(
            user.id,
            password_hash=self._password_hasher(request.new_password),
            must_change_password=request.require_password_change,
        )
        if updated is None:
            raise NotFoundError("Employee user account not found.")

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ADMIN_RESET_EMPLOYEE_PASSWORD",
            entity_type="Employee",
            entity_id=employee.id,
            new_values=json.dumps(
                {
                    "target_user_id": user.id,
                    "require_password_change": request.require_password_change,
                    "sessions_invalidated": True,
                }
            ),
            ip_address=request.ip_address,
        )
        return updated
