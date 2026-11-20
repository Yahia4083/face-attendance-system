"""Pydantic schemas for authentication endpoints."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """POST /auth/login request body."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public user representation."""

    id: int
    email: str
    role: str
    is_active: bool
    must_change_password: bool = False

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Response returned after successful login."""

    access_token: str
    token_type: str
    user: UserResponse


class CurrentUserResponse(BaseModel):
    """Response for GET /auth/me."""

    id: int
    email: str
    role: str
    is_active: bool
    must_change_password: bool = False

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    """Request body for changing the current account password."""

    current_password: str
    new_password: str
    confirm_password: str


class PasswordChangeResponse(BaseModel):
    """Safe password-operation response."""

    message: str
    must_change_password: bool
