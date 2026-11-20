"""CSV and Excel attendance export implementation."""

from __future__ import annotations

from dataclasses import asdict
import csv
from io import BytesIO, StringIO
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from app.domain.services.attendance_export_service import AttendanceExportServiceInterface


ATTENDANCE_EXPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Attendance ID", "attendance_id"),
    ("Employee ID", "employee_id"),
    ("Employee Number", "employee_number"),
    ("Employee Name", "employee_name"),
    ("Department", "department_name"),
    ("Schedule Date", "schedule_date"),
    ("Schedule Template", "schedule_template_name"),
    ("Scheduled Start", "scheduled_start_datetime"),
    ("Scheduled End", "scheduled_end_datetime"),
    ("Check-In Time", "check_in_at"),
    ("Check-Out Time", "check_out_at"),
    ("Working Hours", "working_hours"),
    ("Status", "status"),
    ("Is Late", "is_late"),
    ("Late Minutes", "late_minutes"),
    ("Is Early Departure", "is_early_departure"),
    ("Early Departure Minutes", "early_departure_minutes"),
    ("Is Missing Checkout", "is_missing_checkout"),
    ("Is Unscheduled", "is_unscheduled"),
    ("Latest Justification Status", "latest_justification_status"),
    ("Latest Overtime Status", "latest_overtime_status"),
    ("Approved Overtime Minutes", "approved_overtime_minutes"),
    ("Recognition Model Name", "recognition_model_name"),
)


class AttendanceExportService(AttendanceExportServiceInterface):
    """Build attendance report downloads from already-safe report DTOs."""

    def build_csv(
        self,
        *,
        rows: list[Any],
        summary: Any,
        metadata: dict[str, Any],
    ) -> bytes:
        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([label for label, _field in ATTENDANCE_EXPORT_COLUMNS])
        for row in rows:
            writer.writerow([self._value(row, field) for _label, field in ATTENDANCE_EXPORT_COLUMNS])
        writer.writerow([])
        writer.writerow(["Summary"])
        for key, value in self._summary_items(summary, metadata):
            writer.writerow([key, value])
        return output.getvalue().encode("utf-8-sig")

    def build_xlsx(
        self,
        *,
        rows: list[Any],
        summary: Any,
        metadata: dict[str, Any],
    ) -> bytes:
        workbook = Workbook()
        records_sheet = workbook.active
        records_sheet.title = "Attendance Records"
        records_sheet.append([label for label, _field in ATTENDANCE_EXPORT_COLUMNS])
        for row in rows:
            records_sheet.append(
                [self._value(row, field) for _label, field in ATTENDANCE_EXPORT_COLUMNS]
            )
        records_sheet.freeze_panes = "A2"
        records_sheet.auto_filter.ref = records_sheet.dimensions
        self._apply_widths(records_sheet)

        summary_sheet = workbook.create_sheet("Summary")
        summary_sheet.append(["Metric", "Value"])
        for key, value in self._summary_items(summary, metadata):
            summary_sheet.append([key, value])
        summary_sheet.freeze_panes = "A2"
        self._apply_widths(summary_sheet)

        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    @staticmethod
    def _value(row: Any, field: str) -> Any:
        value = getattr(row, field)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if value is None:
            return ""
        return value

    @staticmethod
    def _summary_items(summary: Any, metadata: dict[str, Any]) -> list[tuple[str, Any]]:
        values = asdict(summary)
        items: list[tuple[str, Any]] = [
            ("date_from", metadata.get("date_from")),
            ("date_to", metadata.get("date_to")),
            ("timezone", metadata.get("timezone")),
            ("data_basis", metadata.get("data_basis")),
            (
                "requires_daily_processing_for_complete_absence_metrics",
                metadata.get("requires_daily_processing_for_complete_absence_metrics"),
            ),
        ]
        items.extend((key, value) for key, value in values.items())
        for key, value in (metadata.get("filters") or {}).items():
            items.append((f"filter_{key}", value if value is not None else ""))
        return items

    @staticmethod
    def _apply_widths(sheet) -> None:
        for column_cells in sheet.columns:
            max_length = 0
            column_letter = get_column_letter(column_cells[0].column)
            for cell in column_cells:
                max_length = max(max_length, len(str(cell.value or "")))
            sheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 40)
