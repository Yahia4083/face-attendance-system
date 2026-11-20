"""System setting categories."""

import enum


class SettingCategory(str, enum.Enum):
    """Categories for safe runtime policy settings."""

    ORGANIZATION = "ORGANIZATION"
    ATTENDANCE = "ATTENDANCE"
    JUSTIFICATION = "JUSTIFICATION"
    OVERTIME = "OVERTIME"
    REPORTING = "REPORTING"
