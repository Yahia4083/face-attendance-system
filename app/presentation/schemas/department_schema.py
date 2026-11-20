"""Pydantic schemas for department endpoints."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Department name is required")
        if len(normalized) < 2 or len(normalized) > 100:
            raise ValueError("Department name must be between 2 and 100 characters")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DepartmentUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Department name is required")
        if len(normalized) < 2 or len(normalized) > 100:
            raise ValueError("Department name must be between 2 and 100 characters")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class DepartmentListResponse(BaseModel):
    items: list[DepartmentResponse]
    total: int
    page: int
    page_size: int
