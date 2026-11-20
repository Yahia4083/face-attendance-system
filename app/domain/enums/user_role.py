"""
User Role Enum
==============
Defines the roles available within the system.
"""

import enum


class UserRole(str, enum.Enum):
    """Roles assigned to system users."""
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"
