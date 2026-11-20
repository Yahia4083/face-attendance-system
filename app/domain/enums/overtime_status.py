"""
Overtime Status Enum
====================
Defines the lifecycle statuses of an overtime request.
"""

import enum


class OvertimeStatus(str, enum.Enum):
    """Statuses for overtime requests."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
