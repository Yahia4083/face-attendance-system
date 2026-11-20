"""Common application-level exceptions for use cases."""

from app.domain.services.face_processing_service import FaceImageValidationIssue


class UseCaseError(Exception):
    """Base class for predictable business errors."""


class BadRequestError(UseCaseError):
    """Raised when request data violates business constraints."""


class FaceEnrollmentValidationError(BadRequestError):
    """Expose safe per-file enrollment validation failures to presentation."""

    def __init__(self, issues: tuple[FaceImageValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("Some enrollment images need attention.")


class NotFoundError(UseCaseError):
    """Raised when a requested resource does not exist."""


class ConflictError(UseCaseError):
    """Raised when request conflicts with existing data."""


class ForbiddenError(UseCaseError):
    """Raised when a business operation is not allowed for the caller."""
