"""System setting effective-value sources."""

import enum


class SettingSource(str, enum.Enum):
    """Where an effective setting value was resolved from."""

    DATABASE = "DATABASE"
    ENV_DEFAULT = "ENV_DEFAULT"
    APPLICATION_DEFAULT = "APPLICATION_DEFAULT"
