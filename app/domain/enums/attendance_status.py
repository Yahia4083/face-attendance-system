"""
Attendance Status Enum
======================
Defines the possible statuses of an attendance record.
"""

import enum


class AttendanceStatus(str, enum.Enum):
    """Possible attendance statuses for a single day."""
    PRESENT = "PRESENT"
    LATE = "LATE"
    EARLY_DEPARTURE = "EARLY_DEPARTURE"
    MISSING_CHECKOUT = "MISSING_CHECKOUT"
    ABSENT = "ABSENT"
    UNSCHEDULED = "UNSCHEDULED"
