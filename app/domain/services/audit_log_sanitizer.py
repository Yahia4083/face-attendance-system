"""Security filtering for metadata shown in the audit-log viewer."""

from __future__ import annotations

import json
import re
from typing import Any, Optional


REDACTED_VALUE = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "embedding",
    "vector",
    "biometric",
    "image_bytes",
    "image_path",
    "captured_image",
    "raw_image",
    "face_image",
    "model_path",
)


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalized_key(key)
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def sanitize_audit_value(value: Any) -> Any:
    """Redact sensitive values recursively without changing stored history."""

    if isinstance(value, dict):
        return {
            str(key): REDACTED_VALUE if _is_sensitive_key(key) else sanitize_audit_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_audit_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_audit_value(item) for item in value]
    return value


def parse_and_sanitize_audit_json(raw_value: Optional[str]) -> Any:
    """Return sanitized JSON metadata and suppress malformed raw text."""

    if not raw_value:
        return None
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, (dict, list)):
        return None
    return sanitize_audit_value(parsed)
