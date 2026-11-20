"""Pydantic schemas for employee endpoints."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class EmployeeCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=2, max_length=150)
    employee_number: str = Field(min_length=2, max_length=50)
    phone: Optional[str] = None
    position: Optional[str] = None
    department_id: int = Field(gt=0)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name is required")
        if len(normalized) < 2 or len(normalized) > 150:
            raise ValueError("Full name must be between 2 and 150 characters")
        return normalized

    @field_validator("employee_number")
    @classmethod
    def validate_employee_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Employee number is required")
        if len(normalized) < 2 or len(normalized) > 50:
            raise ValueError("Employee number must be between 2 and 50 characters")
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("position")
    @classmethod
    def normalize_position(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EmployeeUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    full_name: str = Field(min_length=2, max_length=150)
    phone: Optional[str] = None
    position: Optional[str] = None
    department_id: int = Field(gt=0)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name is required")
        if len(normalized) < 2 or len(normalized) > 150:
            raise ValueError("Full name must be between 2 and 150 characters")
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("position")
    @classmethod
    def normalize_position(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EmployeeResponse(BaseModel):
    id: int
    user_id: int
    email: EmailStr
    department_id: int
    department_name: str
    full_name: str
    employee_number: str
    phone: Optional[str]
    position: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str


class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int


class EmployeePasswordResetRequest(BaseModel):
    """Admin-only temporary password reset request."""

    new_password: str
    confirm_password: str
    require_password_change: bool = True


class EmployeePasswordResetResponse(BaseModel):
    """Safe response that never returns password data."""

    employee_id: int
    user_id: int
    require_password_change: bool
    message: str
