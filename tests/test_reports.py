from datetime import date, datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.application.dto.report_dto import (
    DailyAttendanceReportRequest,
    DepartmentAttendanceSummaryRequest,
    EmployeeAttendanceSummaryRequest,
    ExportAttendanceReportRequest,
    MonthlyAttendanceReportRequest,
)
from app.application.use_cases.exceptions import BadRequestError, NotFoundError
from app.application.use_cases.reports.report_management import (
    ExportAttendanceReport,
    GetDailyAttendanceReport,
    GetDepartmentAttendanceSummary,
    GetEmployeeAttendanceSummary,
    GetMonthlyAttendanceReport,
)
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.export_format import ExportFormat
from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.repositories.report_repository import AttendanceReportFilters
from app.infrastructure.exports.attendance_export_service import AttendanceExportService


def department(department_id=1, name="Engineering"):
    return SimpleNamespace(id=department_id, name=name)


def employee(employee_id=1, department_obj=None):
    return SimpleNamespace(
        id=employee_id,
        user_id=employee_id * 10,
        full_name=f"Employee {employee_id}",
        employee_number=f"EMP{employee_id:03d}",
        department=department_obj or department(),
    )


def justification(request_type, status, request_id=1, created_at=None):
    return SimpleNamespace(
        id=request_id,
        request_type=request_type,
        status=status,
        created_at=created_at or datetime(2026, 5, 20, 9, 0),
    )


def overtime(status, minutes=0, request_id=1, created_at=None):
    return SimpleNamespace(
        id=request_id,
        status=status,
        approved_minutes=minutes,
        created_at=created_at or datetime(2026, 5, 20, 9, 0),
    )


def record(**overrides):
    emp = overrides.pop("employee", employee())
    values = {
        "id": 1,
        "employee_id": emp.id,
        "employee": emp,
        "attendance_date": date(2026, 5, 18),
        "schedule_template": SimpleNamespace(id=1, name="Morning Shift"),
        "scheduled_start_datetime": datetime(2026, 5, 18, 8, 0),
        "scheduled_end_datetime": datetime(2026, 5, 18, 16, 0),
        "check_in_time": datetime(2026, 5, 18, 8, 0),
        "check_out_time": datetime(2026, 5, 18, 16, 0),
        "working_hours": 8.0,
        "status": AttendanceStatus.PRESENT,
        "is_late": False,
        "is_early_departure": False,
        "is_unscheduled": False,
        "is_missing_checkout": False,
        "late_minutes": 0,
        "early_departure_minutes": 0,
        "recognition_model_name": "facenet-onnx-512d-haikalmumtaz-v1",
        "justification_requests": [],
        "overtime_requests": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeReportRepo:
    def __init__(self, records):
        self.records = records

    def list_attendance_records(self, *, filters, page, page_size):
        items = self._filtered(filters)
        return items[(page - 1) * page_size : (page - 1) * page_size + page_size]

    def count_attendance_records(self, *, filters):
        return len(self._filtered(filters))

    def list_attendance_records_for_export(self, *, filters):
        return self._filtered(filters)

    def _filtered(self, filters):
        result = list(self.records)
        if filters.on_date:
            result = [item for item in result if item.attendance_date == filters.on_date]
        if filters.date_from:
            result = [item for item in result if item.attendance_date >= filters.date_from]
        if filters.date_to:
            result = [item for item in result if item.attendance_date <= filters.date_to]
        if filters.employee_id is not None:
            result = [item for item in result if item.employee_id == filters.employee_id]
        if filters.department_id is not None:
            result = [
                item
                for item in result
                if item.employee.department.id == filters.department_id
            ]
        if filters.status is not None:
            result = [
                item
                for item in result
                if (item.status.value if hasattr(item.status, "value") else item.status)
                == filters.status
            ]
        if filters.is_late is not None:
            result = [item for item in result if item.is_late == filters.is_late]
        if filters.is_early_departure is not None:
            result = [
                item for item in result if item.is_early_departure == filters.is_early_departure
            ]
        if filters.is_unscheduled is not None:
            result = [item for item in result if item.is_unscheduled == filters.is_unscheduled]
        if filters.is_missing_checkout is not None:
            result = [
                item for item in result if item.is_missing_checkout == filters.is_missing_checkout
            ]
        if filters.justification_status is not None:
            result = [
                item
                for item in result
                if any(req.status.value == filters.justification_status for req in item.justification_requests)
            ]
        if filters.overtime_status is not None:
            result = [
                item
                for item in result
                if any(req.status.value == filters.overtime_status for req in item.overtime_requests)
            ]
        return sorted(result, key=lambda item: item.id)


class FakeEmployeeRepo:
    def __init__(self, employees):
        self.employees = {item.id: item for item in employees}

    def get_by_id(self, employee_id):
        return self.employees.get(employee_id)

    def get_by_user_id(self, user_id):
        for item in self.employees.values():
            if item.user_id == user_id:
                return item
        return None


class FakeDepartmentRepo:
    def __init__(self, departments):
        self.departments = {item.id: item for item in departments}

    def get_by_id(self, department_id):
        return self.departments.get(department_id)


class FakeAuditRepo:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


def context(records):
    departments = {item.employee.department.id: item.employee.department for item in records}
    employees = {item.employee.id: item.employee for item in records}
    return {
        "report_repo": FakeReportRepo(records),
        "employee_repo": FakeEmployeeRepo(employees.values()),
        "department_repo": FakeDepartmentRepo(departments.values()),
        "audit_repo": FakeAuditRepo(),
    }


def daily_use_case(ctx):
    return GetDailyAttendanceReport(
        report_repo=ctx["report_repo"],
        employee_repo=ctx["employee_repo"],
        department_repo=ctx["department_repo"],
    )


def monthly_use_case(ctx):
    return GetMonthlyAttendanceReport(
        report_repo=ctx["report_repo"],
        employee_repo=ctx["employee_repo"],
        department_repo=ctx["department_repo"],
    )


def test_daily_report_counts_absent_and_approved_justification():
    absent = record(
        id=3,
        status=AttendanceStatus.ABSENT,
        check_in_time=None,
        check_out_time=None,
        working_hours=None,
        justification_requests=[
            justification("ABSENCE", RequestStatus.APPROVED, created_at=datetime(2026, 5, 20, 10, 0))
        ],
    )
    result = daily_use_case(context([absent])).execute(
        DailyAttendanceReportRequest(
            on_date=date(2026, 5, 18),
            filters=AttendanceReportFilters(),
            page=1,
            page_size=10,
        )
    )
    assert result.summary.absent_count == 1
    assert result.summary.justified_absent_count == 1
    assert result.summary.scheduled_attended_shift_count == 0
    assert result.summary.attendance_rate_percentage == 0.0
    assert result.items[0].status == "ABSENT"
    assert result.items[0].latest_justification_status == "APPROVED"
    assert result.items[0].check_in_at is None


def test_report_datetime_fields_include_tripoli_offset_and_dates_remain_dates():
    result = daily_use_case(context([record()])).execute(
        DailyAttendanceReportRequest(
            on_date=date(2026, 5, 18),
            filters=AttendanceReportFilters(),
            page=1,
            page_size=10,
        )
    )
    row = result.items[0]
    assert row.scheduled_start_datetime == "2026-05-18T08:00:00+02:00"
    assert row.check_in_at == "2026-05-18T08:00:00+02:00"
    assert row.schedule_date == date(2026, 5, 18)


def test_monthly_report_excludes_unscheduled_from_attendance_rate():
    scheduled_absent = record(
        id=1,
        status=AttendanceStatus.ABSENT,
        check_in_time=None,
        check_out_time=None,
        working_hours=None,
    )
    unscheduled = record(
        id=2,
        attendance_date=date(2026, 5, 19),
        status=AttendanceStatus.UNSCHEDULED,
        is_unscheduled=True,
        scheduled_start_datetime=None,
        scheduled_end_datetime=None,
        schedule_template=None,
    )
    result = monthly_use_case(context([scheduled_absent, unscheduled])).execute(
        MonthlyAttendanceReportRequest(
            year=2026,
            month=5,
            filters=AttendanceReportFilters(),
            page=1,
            page_size=10,
        )
    )
    assert result.summary.total_records == 2
    assert result.summary.scheduled_processed_shift_count == 1
    assert result.summary.unscheduled_attendance_count == 1
    assert result.summary.attendance_rate_percentage == 0.0
    assert result.items[0].unscheduled_attendance_count == 1


def test_multi_fact_late_missing_checkout_counts_both_metrics():
    item = record(
        status=AttendanceStatus.MISSING_CHECKOUT,
        is_late=True,
        is_missing_checkout=True,
        check_out_time=None,
        late_minutes=30,
        justification_requests=[
            justification("MISSING_CHECKOUT", RequestStatus.APPROVED),
            justification("LATE", RequestStatus.PENDING, request_id=2),
        ],
    )
    result = daily_use_case(context([item])).execute(
        DailyAttendanceReportRequest(
            on_date=date(2026, 5, 18),
            filters=AttendanceReportFilters(),
            page=1,
            page_size=10,
        )
    )
    assert result.summary.late_count == 1
    assert result.summary.missing_checkout_count == 1
    assert result.summary.late_and_missing_checkout_count == 1
    assert result.summary.justified_missing_checkout_count == 1
    assert result.summary.pending_justification_count == 1


def test_approved_overtime_only_contributes_to_approved_totals():
    item = record(
        overtime_requests=[
            overtime(OvertimeStatus.APPROVED, minutes=60),
            overtime(OvertimeStatus.PENDING, minutes=120, request_id=2),
            overtime(OvertimeStatus.REJECTED, minutes=90, request_id=3),
        ]
    )
    result = daily_use_case(context([item])).execute(
        DailyAttendanceReportRequest(
            on_date=date(2026, 5, 18),
            filters=AttendanceReportFilters(),
            page=1,
            page_size=10,
        )
    )
    assert result.summary.approved_overtime_request_count == 1
    assert result.summary.pending_overtime_request_count == 1
    assert result.summary.rejected_overtime_request_count == 1
    assert result.summary.approved_overtime_minutes == 60
    assert result.summary.approved_overtime_hours == 1.0


def test_filters_by_employee_department_and_request_status():
    dep1 = department(1, "Engineering")
    dep2 = department(2, "HR")
    emp1 = employee(1, dep1)
    emp2 = employee(2, dep2)
    records = [
        record(id=1, employee=emp1, justification_requests=[justification("ABSENCE", RequestStatus.APPROVED)]),
        record(id=2, employee=emp2, justification_requests=[justification("ABSENCE", RequestStatus.PENDING)]),
    ]
    result = daily_use_case(context(records)).execute(
        DailyAttendanceReportRequest(
            on_date=date(2026, 5, 18),
            filters=AttendanceReportFilters(
                employee_id=1,
                department_id=1,
                justification_status="APPROVED",
            ),
            page=1,
            page_size=10,
        )
    )
    assert result.total == 1
    assert result.items[0].employee_id == 1
    assert result.items[0].department_name == "Engineering"


def test_joined_request_collections_do_not_inflate_record_counts():
    item = record(
        justification_requests=[
            justification("LATE", RequestStatus.APPROVED, 1),
            justification("EARLY_DEPARTURE", RequestStatus.REJECTED, 2),
        ],
        overtime_requests=[
            overtime(OvertimeStatus.APPROVED, 30, 1),
            overtime(OvertimeStatus.APPROVED, 45, 2),
        ],
    )
    result = daily_use_case(context([item])).execute(
        DailyAttendanceReportRequest(
            on_date=date(2026, 5, 18),
            filters=AttendanceReportFilters(),
            page=1,
            page_size=10,
        )
    )
    assert result.summary.total_records == 1
    assert result.summary.approved_justification_count == 1
    assert result.summary.rejected_justification_count == 1
    assert result.summary.approved_overtime_minutes == 75


def test_employee_summary_rejects_missing_employee():
    ctx = context([record()])
    use_case = GetEmployeeAttendanceSummary(
        report_repo=ctx["report_repo"],
        employee_repo=ctx["employee_repo"],
        department_repo=ctx["department_repo"],
    )
    with pytest.raises(NotFoundError, match="Employee not found"):
        use_case.execute(
            EmployeeAttendanceSummaryRequest(
                employee_id=999,
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 31),
            )
        )


def test_department_summary_aggregates_employee_rows():
    dep = department(1, "Engineering")
    records = [
        record(id=1, employee=employee(1, dep), status=AttendanceStatus.ABSENT, check_in_time=None),
        record(id=2, employee=employee(2, dep), is_late=True, status=AttendanceStatus.LATE),
    ]
    ctx = context(records)
    result = GetDepartmentAttendanceSummary(
        report_repo=ctx["report_repo"],
        employee_repo=ctx["employee_repo"],
        department_repo=ctx["department_repo"],
    ).execute(
        DepartmentAttendanceSummaryRequest(
            department_id=1,
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 31),
            page=1,
            page_size=10,
        )
    )
    assert result.total == 2
    assert result.summary.absent_count == 1
    assert result.summary.late_count == 1


def test_department_summary_rejects_missing_department():
    ctx = context([record()])
    use_case = GetDepartmentAttendanceSummary(
        report_repo=ctx["report_repo"],
        employee_repo=ctx["employee_repo"],
        department_repo=ctx["department_repo"],
    )
    with pytest.raises(NotFoundError, match="Department not found"):
        use_case.execute(
            DepartmentAttendanceSummaryRequest(
                department_id=999,
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 31),
                page=1,
                page_size=10,
            )
        )


def test_date_range_validation():
    ctx = context([record()])
    use_case = GetEmployeeAttendanceSummary(
        report_repo=ctx["report_repo"],
        employee_repo=ctx["employee_repo"],
        department_repo=ctx["department_repo"],
    )
    with pytest.raises(BadRequestError, match="date_from"):
        use_case.execute(
            EmployeeAttendanceSummaryRequest(
                employee_id=1,
                date_from=date(2026, 6, 1),
                date_to=date(2026, 5, 1),
            )
        )


def export_use_case(ctx):
    return ExportAttendanceReport(
        report_repo=ctx["report_repo"],
        employee_repo=ctx["employee_repo"],
        department_repo=ctx["department_repo"],
        export_service=AttendanceExportService(),
        audit_repo=ctx["audit_repo"],
    )


def test_csv_export_uses_bom_stable_columns_and_safe_content():
    ctx = context([record()])
    result = export_use_case(ctx).execute(
        ExportAttendanceReportRequest(
            filters=AttendanceReportFilters(
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 31),
            ),
            export_format=ExportFormat.CSV,
            actor_user_id=1,
        )
    )
    assert result.content.startswith(b"\xef\xbb\xbf")
    text = result.content.decode("utf-8-sig")
    assert "Attendance ID,Employee ID,Employee Number" in text
    assert "Recognition Model Name" in text
    assert "embedding" not in text.lower()
    assert "token" not in text.lower()
    assert ctx["audit_repo"].entries[0]["action"] == "EXPORT_ATTENDANCE_REPORT"


def test_xlsx_export_contains_records_and_summary_sheets():
    ctx = context([record()])
    result = export_use_case(ctx).execute(
        ExportAttendanceReportRequest(
            filters=AttendanceReportFilters(
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 31),
            ),
            export_format=ExportFormat.XLSX,
            actor_user_id=1,
        )
    )
    workbook = load_workbook(BytesIO(result.content))
    assert "Attendance Records" in workbook.sheetnames
    assert "Summary" in workbook.sheetnames
    assert workbook["Attendance Records"]["A1"].value == "Attendance ID"


def test_zero_row_export_still_has_headers_and_summary():
    ctx = context([])
    ctx["employee_repo"] = FakeEmployeeRepo([])
    ctx["department_repo"] = FakeDepartmentRepo([])
    result = export_use_case(ctx).execute(
        ExportAttendanceReportRequest(
            filters=AttendanceReportFilters(
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 31),
            ),
            export_format=ExportFormat.CSV,
            actor_user_id=1,
        )
    )
    text = result.content.decode("utf-8-sig")
    assert "Attendance ID" in text
    assert "total_records,0" in text
    assert result.row_count == 0


def test_export_rejects_excessive_date_range():
    ctx = context([record()])
    with pytest.raises(BadRequestError, match="cannot exceed"):
        export_use_case(ctx).execute(
            ExportAttendanceReportRequest(
                filters=AttendanceReportFilters(
                    date_from=date(2025, 1, 1),
                    date_to=date(2026, 12, 31),
                ),
                export_format=ExportFormat.CSV,
                actor_user_id=1,
            )
        )


def test_report_generation_is_read_only_for_attendance_records():
    item = record()
    before = item.__dict__.copy()
    daily_use_case(context([item])).execute(
        DailyAttendanceReportRequest(
            on_date=date(2026, 5, 18),
            filters=AttendanceReportFilters(),
            page=1,
            page_size=10,
        )
    )
    assert item.__dict__ == before
