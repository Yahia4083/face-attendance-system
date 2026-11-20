"""
Login User Use Case
===================
Authentication flow:
1. Find user by email.
2. Verify password.
3. Reject inactive accounts.
4. Issue access token.
5. Write audit logs for every attempt.
"""

import json
from typing import Callable

from app.application.dto.auth_dto import LoginRequest, LoginResult
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.infrastructure.security.jwt_service import create_access_token
from app.infrastructure.security.password_hasher import verify_password


class AuthenticationError(Exception):
    """Raised when credentials are invalid."""


class InactiveAccountError(Exception):
    """Raised when the user account is disabled."""


class LoginUser:
    """Use case for authenticating users with email and password."""

    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        password_verifier: Callable[[str, str], bool] = verify_password,
        token_creator: Callable[[dict], str] = create_access_token,
    ) -> None:
        self._user_repo = user_repo
        self._audit_repo = audit_repo
        self._password_verifier = password_verifier
        self._token_creator = token_creator

    def execute(
        self,
        request: LoginRequest,
    ) -> LoginResult:
        normalized_email = request.email.strip().lower()
        user = self._user_repo.get_by_email(normalized_email)

        if user is None:
            self._audit_repo.log(
                actor_user_id=None,
                action="LOGIN_FAILED",
                entity_type="User",
                entity_id=None,
                new_values=json.dumps(
                    {"email": normalized_email, "reason": "user_not_found"}
                ),
                ip_address=request.ip_address,
            )
            raise AuthenticationError("Invalid email or password")

        if not self._password_verifier(request.password, user.password_hash):
            self._audit_repo.log(
                actor_user_id=user.id,
                action="LOGIN_FAILED",
                entity_type="User",
                entity_id=user.id,
                new_values=json.dumps(
                    {"email": normalized_email, "reason": "invalid_password"}
                ),
                ip_address=request.ip_address,
            )
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            self._audit_repo.log(
                actor_user_id=user.id,
                action="LOGIN_FAILED",
                entity_type="User",
                entity_id=user.id,
                new_values=json.dumps(
                    {"email": normalized_email, "reason": "inactive_account"}
                ),
                ip_address=request.ip_address,
            )
            raise InactiveAccountError("Account is inactive")

        access_token = self._token_creator(
            data={
                "sub": str(user.id),
                "ver": int(getattr(user, "token_version", 0) or 0),
            }
        )

        self._audit_repo.log(
            actor_user_id=user.id,
            action="LOGIN_SUCCESS",
            entity_type="User",
            entity_id=user.id,
            new_values=json.dumps({"email": normalized_email}),
            ip_address=request.ip_address,
        )

        return LoginResult(
            access_token=access_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
            is_active=user.is_active,
            must_change_password=bool(
                getattr(user, "must_change_password", False)
            ),
        )
