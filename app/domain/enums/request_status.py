"""
Request Status Enum
===================
Defines the lifecycle statuses of a justification request.
"""

import enum


class RequestStatus(str, enum.Enum):
    """Statuses for justification requests."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
