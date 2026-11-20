"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.dto.auth_dto import (
    ChangeOwnPasswordRequest,
    LoginRequest as LoginRequestDTO,
)
from app.application.use_cases.auth.login_user import (
    AuthenticationError,
    InactiveAccountError,
    LoginUser,
)
from app.application.use_cases.auth.password_management import ChangeOwnPassword
from app.application.use_cases.exceptions import BadRequestError, NotFoundError
from app.dependencies import (
    get_audit_repository,
    get_login_use_case,
    get_user_repository,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.infrastructure.security.permissions import (
    get_current_user,
    require_admin,
    require_employee,
)
from app.presentation.schemas.auth_schema import (
    CurrentUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    PasswordChangeResponse,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _role_to_str(role: object) -> str:
    return role.value if hasattr(role, "value") else str(role)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    use_case: LoginUser = Depends(get_login_use_case),
):
    """Authenticate user and return JWT access token."""
    ip_address = request.client.host if request.client else None

    try:
        result = use_case.execute(
            request=LoginRequestDTO(
                email=body.email,
                password=body.password,
                ip_address=ip_address,
            )
        )
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InactiveAccountError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return TokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        user=UserResponse(
            id=result.user_id,
            email=result.email,
            role=result.role,
            is_active=result.is_active,
            must_change_password=result.must_change_password,
        ),
    )


@router.get("/me", response_model=CurrentUserResponse)
def get_me(current_user=Depends(get_current_user)):
    """Return currently authenticated user."""
    return CurrentUserResponse(
        id=current_user.id,
        email=current_user.email,
        role=_role_to_str(current_user.role),
        is_active=current_user.is_active,
        must_change_password=bool(
            getattr(current_user, "must_change_password", False)
        ),
    )


@router.patch("/me/password", response_model=PasswordChangeResponse)
def change_own_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user=Depends(get_current_user),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    """Change the authenticated user's password and revoke older tokens."""
    use_case = ChangeOwnPassword(user_repo=user_repo, audit_repo=audit_repo)
    try:
        updated = use_case.execute(
            ChangeOwnPasswordRequest(
                user_id=current_user.id,
                current_password=body.current_password,
                new_password=body.new_password,
                confirm_password=body.confirm_password,
                ip_address=request.client.host if request.client else None,
            )
        )
    except BadRequestError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )

    return PasswordChangeResponse(
        message="Password changed successfully. Please sign in again using your new password.",
        must_change_password=bool(updated.must_change_password),
    )


@router.get("/admin-test")
def admin_test(current_user=Depends(require_admin)):
    """Test endpoint for ADMIN role."""
    return {
        "message": "Welcome, Admin!",
        "user_id": current_user.id,
        "email": current_user.email,
    }


@router.get("/employee-test")
def employee_test(current_user=Depends(require_employee)):
    """Test endpoint for EMPLOYEE role."""
    return {
        "message": "Welcome, Employee!",
        "user_id": current_user.id,
        "email": current_user.email,
    }
