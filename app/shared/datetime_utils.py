"""Datetime formatting helpers shared by presentation/export layers."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Africa/Tripoli"


def _resolve_timezone_name(timezone_name: str | None) -> str:
    if timezone_name:
        return timezone_name
    try:
        from app.config import get_settings

        return get_settings().APP_TIMEZONE
    except Exception:
        return DEFAULT_TIMEZONE


def local_isoformat(value: datetime | None, timezone_name: str | None = None) -> str | None:
    """Format a stored business datetime with an explicit local timezone offset.

    Existing attendance datetimes are stored as naive business-local values. When
    a timezone-aware value is provided, it is converted into the requested zone.
    """

    if value is None:
        return None

    zone = ZoneInfo(_resolve_timezone_name(timezone_name))
    if value.tzinfo is None:
        localized = value.replace(tzinfo=zone)
    else:
        localized = value.astimezone(zone)
    return localized.isoformat(timespec="seconds")


def utc_to_local_isoformat(value: datetime | None, timezone_name: str | None = None) -> str | None:
    """Format a UTC-stored datetime in the requested local timezone.

    Audit timestamps are stored as naive UTC values by the existing audit model,
    while attendance business timestamps are stored as naive Africa/Tripoli
    values. Keeping this helper separate prevents accidental double conversion.
    """

    if value is None:
        return None

    zone = ZoneInfo(_resolve_timezone_name(timezone_name))
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.astimezone(zone).isoformat(timespec="seconds")
