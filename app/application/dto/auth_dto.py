"""Auth-related application DTOs."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LoginResult:
    """Output from a successful login use case execution."""

    access_token: str
    token_type: str
    user_id: int
    email: str
    role: str
    is_active: bool
    must_change_password: bool


@dataclass(frozen=True)
class LoginRequest:
    """Input DTO for login use case."""

    email: str
    password: str
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ChangeOwnPasswordRequest:
    """Input for an authenticated user's password change."""

    user_id: int
    current_password: str
    new_password: str
    confirm_password: str
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ResetEmployeePasswordRequest:
    """Input for an administrator resetting an employee password."""

    employee_id: int
    new_password: str
    confirm_password: str
    require_password_change: bool
    actor_user_id: int
    ip_address: Optional[str] = None
