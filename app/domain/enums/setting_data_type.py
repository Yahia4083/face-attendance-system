"""System setting data types."""

import enum


class SettingDataType(str, enum.Enum):
    """Supported runtime setting value types."""

    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
