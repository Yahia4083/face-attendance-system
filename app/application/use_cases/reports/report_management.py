"""Attendance report and export use cases."""

from __future__ import annotations

import calendar
from dataclasses import asdict, replace
from datetime import date
import json
from typing import Iterable, Optional

from app.application.dto.report_dto import (
    AttendanceReportRow,
    DailyAttendanceReportRequest,
    DailyAttendanceReportResult,
    DepartmentAttendanceSummaryRequest,
    DepartmentAttendanceSummaryResult,
    EmployeeAggregateRow,
    EmployeeAttendanceSummaryRequest,
    EmployeeAttendanceSummaryResult,
    ExportAttendanceReportRequest,
    ExportAttendanceReportResult,
    MonthlyAttendanceReportRequest,
    MonthlyAttendanceReportResult,
    MyAttendanceSummaryRequest,
    ReportSummary,
)
from app.application.use_cases.exceptions import BadRequestError, NotFoundError
from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.export_format import ExportFormat
from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.report_repository import (
    AttendanceReportFilters,
    ReportRepositoryInterface,
)
from app.domain.services.attendance_export_service import AttendanceExportServiceInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.shared.datetime_utils import local_isoformat


DATA_BASIS = "existing_attendance_records"
REQUIRES_DAILY_PROCESSING = True


def _value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise BadRequestError("Page must be greater than or equal to 1")
    if page_size < 1 or page_size > 100:
        raise BadRequestError("Page size must be between 1 and 100")


def _validate_date_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise BadRequestError("date_from must be earlier than or equal to date_to.")


def _validate_filters(filters: AttendanceReportFilters) -> None:
    if filters.date_from and filters.date_to:
        _validate_date_range(filters.date_from, filters.date_to)
    if filters.status and filters.status not in {status.value for status in AttendanceStatus}:
        raise BadRequestError("Invalid attendance status")
    if filters.justification_status and filters.justification_status not in {
        status.value for status in RequestStatus
    }:
        raise BadRequestError("Invalid justification request status")
    if filters.overtime_status and filters.overtime_status not in {
        status.value for status in OvertimeStatus
    }:
        raise BadRequestError("Invalid overtime request status")


def _filters_dict(filters: AttendanceReportFilters) -> dict:
    return {
        key: (value.isoformat() if isinstance(value, date) else value)
        for key, value in asdict(filters).items()
    }


def _latest_status(items: Iterable[object]) -> Optional[str]:
    values = list(items or [])
    if not values:
        return None
    latest = max(values, key=lambda item: (getattr(item, "created_at", None), getattr(item, "id", 0)))
    return _value(latest.status)


def _request_status_items(items: Iterable[object], status: RequestStatus | OvertimeStatus) -> list[object]:
    return [item for item in items or [] if _value(item.status) == status.value]


def _has_approved_justification(record: object, request_type: str) -> bool:
    return any(
        _value(item.status) == RequestStatus.APPROVED.value
        and getattr(item, "request_type", None) == request_type
        for item in getattr(record, "justification_requests", []) or []
    )


def _approved_overtime_minutes(record: object) -> int:
    total = 0
    for item in getattr(record, "overtime_requests", []) or []:
        if _value(item.status) == OvertimeStatus.APPROVED.value:
            total += int(getattr(item, "approved_minutes", None) or 0)
    return total


def _status(record: object) -> str:
    return _value(getattr(record, "status"))


def _employee(record: object):
    return getattr(record, "employee", None)


def _department(record: object):
    employee = _employee(record)
    return getattr(employee, "department", None) if employee else None


def _template(record: object):
    return getattr(record, "schedule_template", None)


def _to_row(record: object, timezone_name: str) -> AttendanceReportRow:
    # Builds one privacy-safe attendance row for APIs and exports.
    employee = _employee(record)
    department = _department(record)
    template = _template(record)
    justifications = list(getattr(record, "justification_requests", []) or [])
    overtime_requests = list(getattr(record, "overtime_requests", []) or [])
    return AttendanceReportRow(
        attendance_id=record.id,
        employee_id=record.employee_id,
        employee_name=getattr(employee, "full_name", None),
        employee_number=getattr(employee, "employee_number", None),
        department_id=getattr(department, "id", None),
        department_name=getattr(department, "name", None),
        schedule_date=record.attendance_date,
        schedule_template_name=getattr(template, "name", None),
        scheduled_start_datetime=local_isoformat(record.scheduled_start_datetime, timezone_name),
        scheduled_end_datetime=local_isoformat(record.scheduled_end_datetime, timezone_name),
        check_in_at=local_isoformat(record.check_in_time, timezone_name),
        check_out_at=local_isoformat(record.check_out_time, timezone_name),
        working_hours=record.working_hours,
        status=_status(record),
        is_late=bool(record.is_late),
        late_minutes=int(record.late_minutes or 0),
        is_early_departure=bool(record.is_early_departure),
        early_departure_minutes=int(record.early_departure_minutes or 0),
        is_missing_checkout=bool(getattr(record, "is_missing_checkout", False)),
        is_unscheduled=bool(record.is_unscheduled),
        latest_justification_status=_latest_status(justifications),
        latest_overtime_status=_latest_status(overtime_requests),
        approved_overtime_minutes=_approved_overtime_minutes(record),
        recognition_model_name=record.recognition_model_name,
    )


def build_attendance_report_row(record: object, timezone_name: str) -> AttendanceReportRow:
    """Build the safe report row shape reused by reports and dashboard views."""
    return _to_row(record, timezone_name)


def _calculate_summary(records: Iterable[object]) -> ReportSummary:
    records = list(records)
    # Separates scheduled records from unscheduled attendance records.
    scheduled_records = [record for record in records if not bool(record.is_unscheduled)]
    attended_scheduled = [record for record in scheduled_records if record.check_in_time is not None]
    working_values = [
        float(record.working_hours)
        for record in records
        if getattr(record, "working_hours", None) is not None
    ]

    pending_justifications = 0
    approved_justifications = 0
    rejected_justifications = 0
    pending_overtime = 0
    approved_overtime = 0
    rejected_overtime = 0
    approved_overtime_minutes = 0

    for record in records:
        # Counts related justification and overtime request statuses.
        justifications = list(getattr(record, "justification_requests", []) or [])
        overtime_requests = list(getattr(record, "overtime_requests", []) or [])
        pending_justifications += len(_request_status_items(justifications, RequestStatus.PENDING))
        approved_justifications += len(_request_status_items(justifications, RequestStatus.APPROVED))
        rejected_justifications += len(_request_status_items(justifications, RequestStatus.REJECTED))
        pending_overtime += len(_request_status_items(overtime_requests, OvertimeStatus.PENDING))
        approved_items = _request_status_items(overtime_requests, OvertimeStatus.APPROVED)
        approved_overtime += len(approved_items)
        rejected_overtime += len(_request_status_items(overtime_requests, OvertimeStatus.REJECTED))
        approved_overtime_minutes += sum(int(item.approved_minutes or 0) for item in approved_items)

    denominator = len(scheduled_records)
    attendance_rate = (
        round((len(attended_scheduled) / denominator) * 100, 2)
        if denominator > 0
        else None
    )

    employee_ids = {record.employee_id for record in records}
    missing_records = [
        record
        for record in records
        if bool(getattr(record, "is_missing_checkout", False))
        or _status(record) == AttendanceStatus.MISSING_CHECKOUT.value
    ]

    return ReportSummary(
        # Builds the complete report summary metrics object.
        total_records=len(records),
        total_attendance_records=len(records),
        employee_count=len(employee_ids),
        scheduled_processed_shift_count=denominator,
        scheduled_attended_shift_count=len(attended_scheduled),
        present_on_time_count=sum(
            1
            for record in scheduled_records
            if _status(record) == AttendanceStatus.PRESENT.value and not bool(record.is_late)
        ),
        late_count=sum(1 for record in records if bool(record.is_late)),
        absent_count=sum(1 for record in records if _status(record) == AttendanceStatus.ABSENT.value),
        early_departure_count=sum(1 for record in records if bool(record.is_early_departure)),
        missing_checkout_count=len(missing_records),
        late_and_missing_checkout_count=sum(1 for record in missing_records if bool(record.is_late)),
        unscheduled_attendance_count=sum(1 for record in records if bool(record.is_unscheduled)),
        justified_absent_count=sum(
            1 for record in records if _has_approved_justification(record, "ABSENCE")
        ),
        justified_late_count=sum(
            1 for record in records if _has_approved_justification(record, "LATE")
        ),
        justified_early_departure_count=sum(
            1 for record in records if _has_approved_justification(record, "EARLY_DEPARTURE")
        ),
        justified_missing_checkout_count=sum(
            1 for record in records if _has_approved_justification(record, "MISSING_CHECKOUT")
        ),
        pending_justification_count=pending_justifications,
        approved_justification_count=approved_justifications,
        rejected_justification_count=rejected_justifications,
        pending_overtime_request_count=pending_overtime,
        approved_overtime_request_count=approved_overtime,
        rejected_overtime_request_count=rejected_overtime,
        approved_overtime_minutes=approved_overtime_minutes,
        approved_overtime_hours=round(approved_overtime_minutes / 60, 2),
        total_working_hours=round(sum(working_values), 2) if working_values else None,
        attendance_rate_percentage=attendance_rate,
    )


def calculate_report_summary(records: Iterable[object]) -> ReportSummary:
    """Calculate attendance metrics using the Phase 10 report definitions."""
    return _calculate_summary(records)


def _aggregate_by_employee(records: Iterable[object]) -> list[EmployeeAggregateRow]:
    grouped: dict[int, list[object]] = {}
    for record in records:
        grouped.setdefault(record.employee_id, []).append(record)

    rows: list[EmployeeAggregateRow] = []
    for employee_id, employee_records in grouped.items():
        first = employee_records[0]
        employee = _employee(first)
        department = _department(first)
        summary = _calculate_summary(employee_records)
        rows.append(
            EmployeeAggregateRow(
                employee_id=employee_id,
                employee_name=getattr(employee, "full_name", None),
                employee_number=getattr(employee, "employee_number", None),
                department_id=getattr(department, "id", None),
                department_name=getattr(department, "name", None),
                scheduled_processed_shift_count=summary.scheduled_processed_shift_count,
                scheduled_attended_shift_count=summary.scheduled_attended_shift_count,
                present_on_time_count=summary.present_on_time_count,
                absent_count=summary.absent_count,
                late_count=summary.late_count,
                early_departure_count=summary.early_departure_count,
                missing_checkout_count=summary.missing_checkout_count,
                unscheduled_attendance_count=summary.unscheduled_attendance_count,
                approved_justification_count=summary.approved_justification_count,
                approved_overtime_minutes=summary.approved_overtime_minutes,
                attendance_rate_percentage=summary.attendance_rate_percentage,
            )
        )
    return sorted(rows, key=lambda item: (item.employee_name or "", item.employee_id))


def _paginate(items: list, page: int, page_size: int) -> list:
    start = (page - 1) * page_size
    return items[start : start + page_size]


class _ReportBase:
    def __init__(
        self,
        *,
        report_repo: ReportRepositoryInterface,
        employee_repo: EmployeeRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
    ) -> None:
        self._report_repo = report_repo
        self._employee_repo = employee_repo
        self._department_repo = department_repo

    def _validate_entities(self, filters: AttendanceReportFilters) -> None:
        if filters.employee_id is not None and self._employee_repo.get_by_id(filters.employee_id) is None:
            raise NotFoundError("Employee not found")
        if (
            filters.department_id is not None
            and self._department_repo.get_by_id(filters.department_id) is None
        ):
            raise NotFoundError("Department not found")


class GetDailyAttendanceReport(_ReportBase):
    """Build a daily attendance report from existing records."""

    def execute(self, request: DailyAttendanceReportRequest) -> DailyAttendanceReportResult:
        _validate_pagination(request.page, request.page_size)
        filters = replace(request.filters, on_date=request.on_date, date_from=None, date_to=None)
        _validate_filters(filters)
        self._validate_entities(filters)
        settings = get_settings()

        # Loads daily report records and the paginated daily table.
        all_records = self._report_repo.list_attendance_records_for_export(filters=filters)
        page_records = self._report_repo.list_attendance_records(
            filters=filters,
            page=request.page,
            page_size=request.page_size,
        )
        return DailyAttendanceReportResult(
            report_type="DAILY_ATTENDANCE",
            on_date=request.on_date,
            timezone=settings.APP_TIMEZONE,
            filters=_filters_dict(filters),
            summary=_calculate_summary(all_records),
            items=[_to_row(record, settings.APP_TIMEZONE) for record in page_records],
            page=request.page,
            page_size=request.page_size,
            total=self._report_repo.count_attendance_records(filters=filters),
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetMonthlyAttendanceReport(_ReportBase):
    """Build a month-level report grouped by employee."""

    def execute(self, request: MonthlyAttendanceReportRequest) -> MonthlyAttendanceReportResult:
        _validate_pagination(request.page, request.page_size)
        if request.month < 1 or request.month > 12:
            raise BadRequestError("month must be between 1 and 12")
        if request.year < 1900 or request.year > 9999:
            raise BadRequestError("year must be a valid four-digit year")

        date_from = date(request.year, request.month, 1)
        date_to = date(request.year, request.month, calendar.monthrange(request.year, request.month)[1])
        filters = replace(request.filters, date_from=date_from, date_to=date_to, on_date=None)
        _validate_filters(filters)
        self._validate_entities(filters)
        settings = get_settings()

        # Loads monthly report records and groups them by employee.
        records = self._report_repo.list_attendance_records_for_export(filters=filters)
        aggregates = _aggregate_by_employee(records)
        return MonthlyAttendanceReportResult(
            report_type="MONTHLY_ATTENDANCE",
            year=request.year,
            month=request.month,
            date_from=date_from,
            date_to=date_to,
            timezone=settings.APP_TIMEZONE,
            filters=_filters_dict(filters),
            summary=_calculate_summary(records),
            items=_paginate(aggregates, request.page, request.page_size),
            page=request.page,
            page_size=request.page_size,
            total=len(aggregates),
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetEmployeeAttendanceSummary(_ReportBase):
    """Build one employee's attendance summary."""

    def execute(self, request: EmployeeAttendanceSummaryRequest) -> EmployeeAttendanceSummaryResult:
        _validate_date_range(request.date_from, request.date_to)
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        settings = get_settings()
        filters = AttendanceReportFilters(
            employee_id=request.employee_id,
            date_from=request.date_from,
            date_to=request.date_to,
        )
        records = self._report_repo.list_attendance_records_for_export(filters=filters)
        return EmployeeAttendanceSummaryResult(
            report_type="EMPLOYEE_ATTENDANCE_SUMMARY",
            employee_id=employee.id,
            employee_name=employee.full_name,
            employee_number=employee.employee_number,
            department_name=getattr(getattr(employee, "department", None), "name", None),
            date_from=request.date_from,
            date_to=request.date_to,
            timezone=settings.APP_TIMEZONE,
            summary=_calculate_summary(records),
            records=[_to_row(record, settings.APP_TIMEZONE) for record in records],
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetDepartmentAttendanceSummary(_ReportBase):
    """Build a department summary grouped by employee."""

    def execute(self, request: DepartmentAttendanceSummaryRequest) -> DepartmentAttendanceSummaryResult:
        _validate_pagination(request.page, request.page_size)
        _validate_date_range(request.date_from, request.date_to)
        department = self._department_repo.get_by_id(request.department_id)
        if department is None:
            raise NotFoundError("Department not found")
        settings = get_settings()
        filters = AttendanceReportFilters(
            department_id=request.department_id,
            date_from=request.date_from,
            date_to=request.date_to,
        )
        records = self._report_repo.list_attendance_records_for_export(filters=filters)
        aggregates = _aggregate_by_employee(records)
        return DepartmentAttendanceSummaryResult(
            report_type="DEPARTMENT_ATTENDANCE_SUMMARY",
            department_id=department.id,
            department_name=department.name,
            date_from=request.date_from,
            date_to=request.date_to,
            timezone=settings.APP_TIMEZONE,
            summary=_calculate_summary(records),
            items=_paginate(aggregates, request.page, request.page_size),
            page=request.page,
            page_size=request.page_size,
            total=len(aggregates),
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetMyAttendanceSummary(_ReportBase):
    """Build the authenticated employee's own summary."""

    def execute(self, request: MyAttendanceSummaryRequest) -> EmployeeAttendanceSummaryResult:
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")
        return GetEmployeeAttendanceSummary(
            report_repo=self._report_repo,
            employee_repo=self._employee_repo,
            department_repo=self._department_repo,
        ).execute(
            EmployeeAttendanceSummaryRequest(
                employee_id=employee.id,
                date_from=request.date_from,
                date_to=request.date_to,
            )
        )


class ExportAttendanceReport(_ReportBase):
    """Export filtered attendance records as CSV or XLSX."""

    def __init__(
        self,
        *,
        report_repo: ReportRepositoryInterface,
        employee_repo: EmployeeRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        export_service: AttendanceExportServiceInterface,
        audit_repo: AuditRepositoryInterface,
        settings_provider: Optional[SystemSettingsProviderInterface] = None,
    ) -> None:
        super().__init__(
            report_repo=report_repo,
            employee_repo=employee_repo,
            department_repo=department_repo,
        )
        self._export_service = export_service
        self._audit_repo = audit_repo
        self._settings_provider = settings_provider

    def execute(self, request: ExportAttendanceReportRequest) -> ExportAttendanceReportResult:
        settings = get_settings()
        export_format = request.export_format
        if export_format not in {ExportFormat.CSV, ExportFormat.XLSX}:
            raise BadRequestError("Unsupported export format")

        filters = request.filters
        if request.own_user_id is not None:
            # Scopes self-service exports to the authenticated employee.
            employee = self._employee_repo.get_by_user_id(request.own_user_id)
            if employee is None:
                raise NotFoundError("Employee profile not found for current user")
            filters = replace(filters, employee_id=employee.id, department_id=None)

        if filters.date_from is None or filters.date_to is None:
            raise BadRequestError("date_from and date_to are required for export")
        _validate_filters(filters)
        self._validate_entities(filters)

        max_days = (
            # Loads the effective maximum export date range.
            self._settings_provider.get_integer("REPORT_EXPORT_MAX_DATE_RANGE_DAYS")
            if self._settings_provider is not None
            else settings.REPORT_EXPORT_MAX_DATE_RANGE_DAYS
        )
        if (filters.date_to - filters.date_from).days + 1 > max_days:
            raise BadRequestError(f"Export date range cannot exceed {max_days} days")

        records = self._report_repo.list_attendance_records_for_export(filters=filters)
        rows = [_to_row(record, settings.APP_TIMEZONE) for record in records]
        summary = _calculate_summary(records)
        # Builds metadata included in exported files.
        metadata = {
            "date_from": filters.date_from.isoformat(),
            "date_to": filters.date_to.isoformat(),
            "timezone": settings.APP_TIMEZONE,
            "filters": _filters_dict(filters),
            "data_basis": DATA_BASIS,
            "requires_daily_processing_for_complete_absence_metrics": REQUIRES_DAILY_PROCESSING,
        }

        if export_format == ExportFormat.CSV:
            content = self._export_service.build_csv(rows=rows, summary=summary, metadata=metadata)
            media_type = "text/csv; charset=utf-8"
        else:
            content = self._export_service.build_xlsx(rows=rows, summary=summary, metadata=metadata)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        action = "EXPORT_OWN_ATTENDANCE_REPORT" if request.own_user_id is not None else "EXPORT_ATTENDANCE_REPORT"
        # Writes the report export event to the audit log.
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action=action,
            entity_type="AttendanceReport",
            entity_id=None,
            new_values=json.dumps(
                {
                    "requested_by_user_id": request.actor_user_id,
                    "format": export_format.value,
                    "date_from": filters.date_from.isoformat(),
                    "date_to": filters.date_to.isoformat(),
                    "employee_id": filters.employee_id,
                    "department_id": filters.department_id,
                    "status": filters.status,
                    "exported_row_count": len(rows),
                }
            ),
            ip_address=request.ip_address,
        )

        filename = (
            f"attendance_report_{filters.date_from.isoformat()}_to_"
            f"{filters.date_to.isoformat()}.{export_format.value}"
        )
        return ExportAttendanceReportResult(
            content=content,
            media_type=media_type,
            filename=filename,
            row_count=len(rows),
        )
