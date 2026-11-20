"""Admin dashboard read-only use cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from app.application.dto.dashboard_dto import (
    DashboardAttendanceTableRequest,
    DashboardAttendanceTableResult,
    DashboardAttendanceTableSummary,
    DashboardAttendanceTrendRequest,
    DashboardAttendanceTrendResult,
    DashboardDepartmentSummaryItem,
    DashboardDepartmentSummaryRequest,
    DashboardDepartmentSummaryResult,
    DashboardOvertimeSummary,
    DashboardPendingRequestItem,
    DashboardPendingRequestsRequest,
    DashboardPendingRequestsResult,
    DashboardRecentActivityItem,
    DashboardRecentActivityRequest,
    DashboardRecentActivityResult,
    DashboardRequestSummary,
    DashboardSummaryRequest,
    DashboardSummaryResult,
    DashboardTrendItem,
    DashboardWorkforceSummary,
    dashboard_attendance_from_report_summary,
    dashboard_table_item_from_report_row,
)
from app.application.use_cases.exceptions import BadRequestError, NotFoundError
from app.application.use_cases.reports.report_management import (
    DATA_BASIS,
    REQUIRES_DAILY_PROCESSING,
    build_attendance_report_row,
    calculate_report_summary,
)
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.repositories.dashboard_repository import DashboardRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.report_repository import (
    AttendanceReportFilters,
    ReportRepositoryInterface,
)
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.shared.datetime_utils import local_isoformat, utc_to_local_isoformat


PENDING_REQUEST_CATEGORIES = {"JUSTIFICATION", "OVERTIME"}


def _value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise BadRequestError("Page must be greater than or equal to 1")
    if page_size < 1 or page_size > 100:
        raise BadRequestError("Page size must be between 1 and 100")


def _validate_status(status: str | None) -> None:
    if status is not None and status not in {item.value for item in AttendanceStatus}:
        raise BadRequestError("Invalid attendance status")


def _paginate(items: list, page: int, page_size: int) -> list:
    start = (page - 1) * page_size
    return items[start : start + page_size]


def _is_open_check_in(record: object) -> bool:
    # Detects attendance records that are still open for checkout.
    status = _value(getattr(record, "status"))
    return (
        getattr(record, "check_in_time", None) is not None
        and getattr(record, "check_out_time", None) is None
        and status != AttendanceStatus.ABSENT.value
        and status != AttendanceStatus.MISSING_CHECKOUT.value
        and not bool(getattr(record, "is_missing_checkout", False))
    )


class _DashboardBase:
    def __init__(
        self,
        *,
        report_repo: ReportRepositoryInterface,
        dashboard_repo: DashboardRepositoryInterface,
        employee_repo: EmployeeRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        settings_provider: SystemSettingsProviderInterface,
        clock: ClockInterface,
    ) -> None:
        self._report_repo = report_repo
        self._dashboard_repo = dashboard_repo
        self._employee_repo = employee_repo
        self._department_repo = department_repo
        self._settings_provider = settings_provider
        self._clock = clock

    def _timezone(self) -> str:
        return self._settings_provider.get_string("ORGANIZATION_TIMEZONE")

    def _organization_name(self) -> str:
        return self._settings_provider.get_string("ORGANIZATION_NAME")

    def _now_local(self):
        return self._clock.now_in_timezone(self._timezone())

    def _date_or_today(self, selected_date: date | None) -> date:
        # Resolves the selected dashboard date or the current business date.
        return selected_date or self._now_local().date()

    def _generated_at(self) -> str:
        return local_isoformat(self._now_local(), self._timezone())

    def _validate_entities(self, *, employee_id: int | None, department_id: int | None) -> None:
        if employee_id is not None and self._employee_repo.get_by_id(employee_id) is None:
            raise NotFoundError("Employee not found")
        if department_id is not None and self._department_repo.get_by_id(department_id) is None:
            raise NotFoundError("Department not found")

    def _records_for_date(self, *, on_date: date, filters: AttendanceReportFilters | None = None):
        # Loads report-compatible attendance records for the selected date.
        base_filters = AttendanceReportFilters(on_date=on_date)
        if filters is not None:
            base_filters = replace(filters, on_date=on_date, date_from=None, date_to=None)
        return self._report_repo.list_attendance_records_for_export(filters=base_filters)


class GetDashboardSummary(_DashboardBase):
    """Return compact headline dashboard metrics for a selected local date."""

    def execute(self, request: DashboardSummaryRequest) -> DashboardSummaryResult:
        on_date = self._date_or_today(request.on_date)
        timezone_name = self._timezone()
        records = self._records_for_date(on_date=on_date)
        summary = calculate_report_summary(records)
        # Loads current pending request counts for the dashboard summary.
        pending_justifications = self._dashboard_repo.count_pending_justification_requests()
        pending_overtime = self._dashboard_repo.count_pending_overtime_requests()

        return DashboardSummaryResult(
            dashboard_type="ADMIN_SUMMARY",
            organization_name=self._organization_name(),
            on_date=on_date,
            timezone=timezone_name,
            generated_at=self._generated_at(),
            attendance=dashboard_attendance_from_report_summary(
                summary,
                open_check_in_count=sum(1 for record in records if _is_open_check_in(record)),
            ),
            requests=DashboardRequestSummary(
                pending_justification_count=pending_justifications,
                pending_overtime_request_count=pending_overtime,
                total_pending_request_count=pending_justifications + pending_overtime,
            ),
            overtime=DashboardOvertimeSummary(
                approved_overtime_request_count=summary.approved_overtime_request_count,
                approved_overtime_minutes=summary.approved_overtime_minutes,
                approved_overtime_hours=summary.approved_overtime_hours,
            ),
            employees=DashboardWorkforceSummary(
                active_employee_count=self._dashboard_repo.count_active_employees(),
                active_department_count=self._dashboard_repo.count_active_departments(),
            ),
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetDashboardTodayAttendance(_DashboardBase):
    """Return selected-date attendance rows for the dashboard table."""

    def execute(self, request: DashboardAttendanceTableRequest) -> DashboardAttendanceTableResult:
        _validate_pagination(request.page, request.page_size)
        _validate_status(request.status)
        self._validate_entities(employee_id=request.employee_id, department_id=request.department_id)

        on_date = self._date_or_today(request.on_date)
        timezone_name = self._timezone()
        filters = AttendanceReportFilters(
            on_date=on_date,
            department_id=request.department_id,
            employee_id=request.employee_id,
            status=request.status,
        )
        records = self._report_repo.list_attendance_records_for_export(filters=filters)
        # Loads summary records and paginated table records separately.
        page_records = self._report_repo.list_attendance_records(
            filters=filters,
            page=request.page,
            page_size=request.page_size,
        )
        summary = calculate_report_summary(records)
        items = [
            dashboard_table_item_from_report_row(
                build_attendance_report_row(record, timezone_name)
            )
            for record in page_records
        ]

        return DashboardAttendanceTableResult(
            on_date=on_date,
            timezone=timezone_name,
            summary=DashboardAttendanceTableSummary(
                total_records=summary.total_records,
                late_count=summary.late_count,
                absent_count=summary.absent_count,
                missing_checkout_count=summary.missing_checkout_count,
                unscheduled_attendance_count=summary.unscheduled_attendance_count,
            ),
            items=items,
            page=request.page,
            page_size=request.page_size,
            total=self._report_repo.count_attendance_records(filters=filters),
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetDashboardPendingRequests(_DashboardBase):
    """Return pending justification and overtime requests requiring admin review."""

    def execute(self, request: DashboardPendingRequestsRequest) -> DashboardPendingRequestsResult:
        _validate_pagination(request.page, request.page_size)
        request_type = request.request_type.strip().upper() if request.request_type else None
        if request_type is not None and request_type not in PENDING_REQUEST_CATEGORIES:
            raise BadRequestError("request_type must be JUSTIFICATION or OVERTIME")
        self._validate_entities(employee_id=request.employee_id, department_id=None)

        pending_justifications = self._dashboard_repo.count_pending_justification_requests(
            employee_id=request.employee_id,
        )
        pending_overtime = self._dashboard_repo.count_pending_overtime_requests(
            employee_id=request.employee_id,
        )
        items = []
        if request_type in {None, "JUSTIFICATION"}:
            items.extend(
                self._dashboard_repo.list_pending_justification_requests(
                    employee_id=request.employee_id,
                )
            )
        if request_type in {None, "OVERTIME"}:
            items.extend(
                self._dashboard_repo.list_pending_overtime_requests(
                    employee_id=request.employee_id,
                )
            )

        # Combines pending justification and overtime items into one queue.
        items = sorted(
            items,
            key=lambda item: (item.created_at is not None, item.created_at, item.request_id),
            reverse=True,
        )
        paged = _paginate(items, request.page, request.page_size)
        timezone_name = self._timezone()
        return DashboardPendingRequestsResult(
            summary=DashboardRequestSummary(
                pending_justification_count=pending_justifications,
                pending_overtime_request_count=pending_overtime,
                total_pending_request_count=pending_justifications + pending_overtime,
            ),
            items=[
                DashboardPendingRequestItem(
                    request_category=item.request_category,
                    request_id=item.request_id,
                    employee_id=item.employee_id,
                    employee_name=item.employee_name,
                    employee_number=item.employee_number,
                    attendance_record_id=item.attendance_record_id,
                    attendance_status=item.attendance_status,
                    request_type=item.request_type,
                    reason=item.reason,
                    requested_minutes=item.requested_minutes,
                    eligible_minutes_at_submission=item.eligible_minutes_at_submission,
                    status=item.status,
                    created_at=utc_to_local_isoformat(item.created_at, timezone_name),
                )
                for item in paged
            ],
            page=request.page,
            page_size=request.page_size,
            total=len(items),
        )


class GetDashboardDepartmentSummary(_DashboardBase):
    """Return one dashboard metric row per active department."""

    def execute(self, request: DashboardDepartmentSummaryRequest) -> DashboardDepartmentSummaryResult:
        _validate_pagination(request.page, request.page_size)
        on_date = self._date_or_today(request.on_date)
        timezone_name = self._timezone()
        snapshots = self._dashboard_repo.list_active_department_snapshots()
        page_snapshots = _paginate(snapshots, request.page, request.page_size)
        all_records = self._report_repo.list_attendance_records_for_export(
            filters=AttendanceReportFilters(on_date=on_date)
        )
        grouped: dict[int, list[object]] = {}
        # Groups attendance records under their employee departments.
        for record in all_records:
            department = getattr(getattr(record, "employee", None), "department", None)
            department_id = getattr(department, "id", None)
            if department_id is not None:
                grouped.setdefault(department_id, []).append(record)

        items: list[DashboardDepartmentSummaryItem] = []
        for snapshot in page_snapshots:
            records = grouped.get(snapshot.department_id, [])
            summary = calculate_report_summary(records)
            items.append(
                DashboardDepartmentSummaryItem(
                    department_id=snapshot.department_id,
                    department_name=snapshot.department_name,
                    active_employee_count=snapshot.active_employee_count,
                    total_records=summary.total_records,
                    scheduled_processed_shift_count=summary.scheduled_processed_shift_count,
                    scheduled_attended_shift_count=summary.scheduled_attended_shift_count,
                    present_on_time_count=summary.present_on_time_count,
                    late_count=summary.late_count,
                    absent_count=summary.absent_count,
                    early_departure_count=summary.early_departure_count,
                    missing_checkout_count=summary.missing_checkout_count,
                    unscheduled_attendance_count=summary.unscheduled_attendance_count,
                    attendance_rate_percentage=summary.attendance_rate_percentage,
                )
            )

        return DashboardDepartmentSummaryResult(
            on_date=on_date,
            timezone=timezone_name,
            items=items,
            page=request.page,
            page_size=request.page_size,
            total=len(snapshots),
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetDashboardAttendanceTrend(_DashboardBase):
    """Return daily dashboard attendance metrics for a short date range."""

    def execute(self, request: DashboardAttendanceTrendRequest) -> DashboardAttendanceTrendResult:
        if request.days < 1 or request.days > 31:
            raise BadRequestError("days must be between 1 and 31.")

        date_to = request.end_date or self._date_or_today(None)
        date_from = date_to - timedelta(days=request.days - 1)
        timezone_name = self._timezone()
        records = self._report_repo.list_attendance_records_for_export(
            filters=AttendanceReportFilters(date_from=date_from, date_to=date_to)
        )
        grouped: dict[date, list[object]] = {}
        # Groups attendance records by date for the trend response.
        for record in records:
            grouped.setdefault(record.attendance_date, []).append(record)

        items = []
        for offset in range(request.days):
            day = date_from + timedelta(days=offset)
            summary = calculate_report_summary(grouped.get(day, []))
            items.append(
                DashboardTrendItem(
                    date=day,
                    scheduled_processed_shift_count=summary.scheduled_processed_shift_count,
                    scheduled_attended_shift_count=summary.scheduled_attended_shift_count,
                    present_on_time_count=summary.present_on_time_count,
                    late_count=summary.late_count,
                    absent_count=summary.absent_count,
                    missing_checkout_count=summary.missing_checkout_count,
                    unscheduled_attendance_count=summary.unscheduled_attendance_count,
                    attendance_rate_percentage=summary.attendance_rate_percentage,
                )
            )

        return DashboardAttendanceTrendResult(
            trend_type="ATTENDANCE_DAILY_TREND",
            date_from=date_from,
            date_to=date_to,
            days=request.days,
            timezone=timezone_name,
            items=items,
            data_basis=DATA_BASIS,
            requires_daily_processing_for_complete_absence_metrics=REQUIRES_DAILY_PROCESSING,
        )


class GetDashboardRecentActivity(_DashboardBase):
    """Return safe human-readable recent attendance/workflow activity."""

    def execute(self, request: DashboardRecentActivityRequest) -> DashboardRecentActivityResult:
        if request.limit < 1 or request.limit > 50:
            raise BadRequestError("limit must be between 1 and 50.")

        timezone_name = self._timezone()
        # Converts recent activity rows into safe dashboard activity items.
        return DashboardRecentActivityResult(
            items=[
                DashboardRecentActivityItem(
                    activity_type=item.activity_type,
                    employee_id=item.employee_id,
                    employee_name=item.employee_name,
                    description=item.description,
                    occurred_at=utc_to_local_isoformat(item.occurred_at, timezone_name),
                    related_entity_type=item.related_entity_type,
                    related_entity_id=item.related_entity_id,
                )
                for item in self._dashboard_repo.list_recent_activities(limit=request.limit)
            ]
        )
