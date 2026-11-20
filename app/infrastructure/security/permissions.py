"""Reusable authentication and authorization dependencies."""

from typing import Callable, Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.dependencies import get_user_repository
from app.domain.enums.user_role import UserRole
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.infrastructure.security.jwt_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _to_role_value(role: UserRole | str) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
):
    """Return authenticated active user from a bearer token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
        token_version = int(payload.get("ver", 0))
    except (JWTError, TypeError, ValueError):
        raise credentials_exception

    user = user_repo.get_by_id(user_id)
    if user is None:
        raise credentials_exception
    if token_version != int(getattr(user, "token_version", 0) or 0):
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return user


def require_roles(allowed_roles: Iterable[UserRole | str]) -> Callable:
    """Return dependency that allows only the provided roles."""
    allowed = {_to_role_value(role) for role in allowed_roles}

    def _role_checker(current_user=Depends(get_current_user)):
        current_role = _to_role_value(current_user.role)
        if current_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _role_checker


def require_admin(current_user=Depends(get_current_user)):
    """Allow only ADMIN users."""
    current_role = _to_role_value(current_user.role)
    if current_role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return current_user


def require_employee(current_user=Depends(get_current_user)):
    """Allow only EMPLOYEE users."""
    current_role = _to_role_value(current_user.role)
    if current_role != UserRole.EMPLOYEE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    if bool(getattr(current_user, "must_change_password", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must change your password before continuing.",
        )
    return current_user
