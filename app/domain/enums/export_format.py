"""Supported report export formats."""

import enum


class ExportFormat(str, enum.Enum):
    """Download formats supported by attendance reports."""

    CSV = "csv"
    XLSX = "xlsx"
