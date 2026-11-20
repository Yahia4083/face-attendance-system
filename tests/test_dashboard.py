from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.dto.dashboard_dto import (
    DashboardAttendanceTableRequest,
    DashboardAttendanceTrendRequest,
    DashboardDepartmentSummaryRequest,
    DashboardPendingRequestsRequest,
    DashboardRecentActivityRequest,
    DashboardSummaryRequest,
)
from app.application.use_cases.dashboard.dashboard_management import (
    GetDashboardAttendanceTrend,
    GetDashboardDepartmentSummary,
    GetDashboardPendingRequests,
    GetDashboardRecentActivity,
    GetDashboardSummary,
    GetDashboardTodayAttendance,
)
from app.application.use_cases.exceptions import BadRequestError, NotFoundError
from app.domain.entities.dashboard import (
    DashboardActivity,
    DashboardDepartmentSnapshot,
    PendingDashboardRequest,
)
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.enums.request_status import RequestStatus
from app.main import create_app


def department(department_id=1, name="Computer Science", is_active=True):
    return SimpleNamespace(id=department_id, name=name, is_active=is_active)


def employee(employee_id=1, department_obj=None, active=True):
    return SimpleNamespace(
        id=employee_id,
        user_id=employee_id * 10,
        full_name=f"Employee {employee_id}",
        employee_number=f"EMP{employee_id:03d}",
        department=department_obj or department(),
        is_active=active,
    )


def justification(request_type, status, request_id=1, created_at=None):
    return SimpleNamespace(
        id=request_id,
        request_type=request_type,
        status=status,
        created_at=created_at or datetime(2026, 5, 20, 9, 0),
    )


def overtime(status, approved_minutes=0, request_id=1, created_at=None):
    return SimpleNamespace(
        id=request_id,
        status=status,
        approved_minutes=approved_minutes,
        created_at=created_at or datetime(2026, 5, 20, 9, 0),
    )


def record(**overrides):
    emp = overrides.pop("employee", employee())
    values = {
        "id": 1,
        "employee_id": emp.id,
        "employee": emp,
        "attendance_date": date(2026, 5, 28),
        "schedule_template": SimpleNamespace(id=1, name="Morning Shift"),
        "scheduled_start_datetime": datetime(2026, 5, 28, 8, 0),
        "scheduled_end_datetime": datetime(2026, 5, 28, 16, 0),
        "check_in_time": datetime(2026, 5, 28, 8, 0),
        "check_out_time": datetime(2026, 5, 28, 16, 0),
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


class FakeClock:
    def __init__(self, current=None):
        self.current = current or datetime(2026, 5, 28, 20, 0)

    def now_utc(self):
        return self.current.replace(tzinfo=UTC)

    def now_in_timezone(self, timezone_name):
        return self.current


class FakeSettingsProvider:
    def __init__(self, organization_name="University Face Attendance System"):
        self.organization_name = organization_name

    def get_string(self, key):
        if key == "ORGANIZATION_NAME":
            return self.organization_name
        if key == "ORGANIZATION_TIMEZONE":
            return "Africa/Tripoli"
        raise KeyError(key)


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
        if filters.on_date is not None:
            result = [item for item in result if item.attendance_date == filters.on_date]
        if filters.date_from is not None:
            result = [item for item in result if item.attendance_date >= filters.date_from]
        if filters.date_to is not None:
            result = [item for item in result if item.attendance_date <= filters.date_to]
        if filters.employee_id is not None:
            result = [item for item in result if item.employee_id == filters.employee_id]
        if filters.department_id is not None:
            result = [
                item
                for item in result
                if getattr(item.employee.department, "id", None) == filters.department_id
            ]
        if filters.status is not None:
            result = [
                item
                for item in result
                if (item.status.value if hasattr(item.status, "value") else item.status)
                == filters.status
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


class FakeDashboardRepo:
    def __init__(self, *, departments, employees, pending=None, activities=None):
        self.departments = list(departments)
        self.employees = list(employees)
        self.pending = list(pending or [])
        self.activities = list(activities or [])

    def count_active_employees(self):
        return sum(1 for item in self.employees if item.is_active)

    def count_active_departments(self):
        return sum(1 for item in self.departments if item.is_active)

    def list_active_department_snapshots(self):
        rows = []
        for dep in sorted([item for item in self.departments if item.is_active], key=lambda item: item.id):
            rows.append(
                DashboardDepartmentSnapshot(
                    department_id=dep.id,
                    department_name=dep.name,
                    active_employee_count=sum(
                        1
                        for emp in self.employees
                        if emp.is_active and emp.department.id == dep.id
                    ),
                )
            )
        return rows

    def count_pending_justification_requests(self, *, employee_id=None):
        return len(self._pending("JUSTIFICATION", employee_id))

    def count_pending_overtime_requests(self, *, employee_id=None):
        return len(self._pending("OVERTIME", employee_id))

    def list_pending_justification_requests(self, *, employee_id=None):
        return self._pending("JUSTIFICATION", employee_id)

    def list_pending_overtime_requests(self, *, employee_id=None):
        return self._pending("OVERTIME", employee_id)

    def list_recent_activities(self, *, limit):
        return self.activities[:limit]

    def _pending(self, category, employee_id):
        result = [
            item
            for item in self.pending
            if item.request_category == category and item.status == "PENDING"
        ]
        if employee_id is not None:
            result = [item for item in result if item.employee_id == employee_id]
        return result


def pending_request(category="JUSTIFICATION", request_id=1, created_at=None):
    return PendingDashboardRequest(
        request_category=category,
        request_id=request_id,
        employee_id=1,
        employee_name="Employee 1",
        employee_number="EMP001",
        attendance_record_id=10 + request_id,
        attendance_status="LATE",
        request_type="LATE" if category == "JUSTIFICATION" else None,
        reason="Traffic delay due to blocked road.",
        requested_minutes=60 if category == "OVERTIME" else None,
        eligible_minutes_at_submission=75 if category == "OVERTIME" else None,
        status="PENDING",
        created_at=created_at or datetime(2026, 5, 28, 18, request_id),
    )


def dashboard_context(records=None, departments=None, employees=None, pending=None, activities=None):
    records = records or []
    departments = departments or list({item.employee.department.id: item.employee.department for item in records}.values())
    employees = employees or list({item.employee.id: item.employee for item in records}.values())
    return {
        "report_repo": FakeReportRepo(records),
        "dashboard_repo": FakeDashboardRepo(
            departments=departments,
            employees=employees,
            pending=pending,
            activities=activities,
        ),
        "employee_repo": FakeEmployeeRepo(employees),
        "department_repo": FakeDepartmentRepo(departments),
        "settings_provider": FakeSettingsProvider(),
        "clock": FakeClock(),
    }


def test_dashboard_summary_counts_absent_and_uses_settings_metadata():
    dep = department()
    emp = employee(1, dep)
    absent = record(
        id=3,
        employee=emp,
        attendance_date=date(2026, 5, 18),
        status=AttendanceStatus.ABSENT,
        check_in_time=None,
        check_out_time=None,
        working_hours=None,
        justification_requests=[justification("ABSENCE", RequestStatus.APPROVED)],
    )
    result = GetDashboardSummary(**dashboard_context([absent])).execute(
        DashboardSummaryRequest(on_date=date(2026, 5, 18))
    )
    assert result.organization_name == "University Face Attendance System"
    assert result.timezone == "Africa/Tripoli"
    assert result.generated_at.endswith("+02:00")
    assert result.attendance.absent_count == 1
    assert result.attendance.scheduled_processed_shift_count == 1
    assert result.attendance.scheduled_attended_shift_count == 0
    assert result.attendance.attendance_rate_percentage == 0.0


def test_dashboard_summary_defaults_to_current_local_date_and_zero_cards():
    ctx = dashboard_context(records=[], departments=[department()], employees=[])
    result = GetDashboardSummary(**ctx).execute(DashboardSummaryRequest())
    assert result.on_date == date(2026, 5, 28)
    assert result.attendance.total_records == 0
    assert result.attendance.attendance_rate_percentage is None
    assert result.requires_daily_processing_for_complete_absence_metrics is True


def test_dashboard_summary_counts_unscheduled_separately_and_pending_requests_globally():
    dep = department()
    emp = employee(1, dep)
    unscheduled = record(
        id=4,
        employee=emp,
        status=AttendanceStatus.UNSCHEDULED,
        is_unscheduled=True,
        schedule_template=None,
        scheduled_start_datetime=None,
        scheduled_end_datetime=None,
    )
    pending = [pending_request("JUSTIFICATION"), pending_request("OVERTIME", request_id=2)]
    result = GetDashboardSummary(**dashboard_context([unscheduled], pending=pending)).execute(
        DashboardSummaryRequest(on_date=date(2026, 5, 28))
    )
    assert result.attendance.unscheduled_attendance_count == 1
    assert result.attendance.scheduled_processed_shift_count == 0
    assert result.attendance.attendance_rate_percentage is None
    assert result.requests.total_pending_request_count == 2


def test_dashboard_attendance_table_filters_paginates_and_uses_safe_row_shape():
    dep1 = department(1, "Computer Science")
    dep2 = department(2, "Math")
    emp1 = employee(1, dep1)
    emp2 = employee(2, dep2)
    records = [
        record(id=1, employee=emp1, is_late=True, status=AttendanceStatus.LATE),
        record(id=2, employee=emp2, status=AttendanceStatus.PRESENT),
    ]
    result = GetDashboardTodayAttendance(**dashboard_context(records)).execute(
        DashboardAttendanceTableRequest(
            on_date=date(2026, 5, 28),
            department_id=1,
            employee_id=1,
            status="LATE",
            page=1,
            page_size=10,
        )
    )
    assert result.total == 1
    assert result.items[0].attendance_id == 1
    assert result.items[0].check_in_at.endswith("+02:00")
    assert not hasattr(result.items[0], "recognition_model_name")


def test_dashboard_attendance_table_rejects_invalid_filters():
    ctx = dashboard_context(records=[record()])
    with pytest.raises(BadRequestError, match="Invalid attendance status"):
        GetDashboardTodayAttendance(**ctx).execute(
            DashboardAttendanceTableRequest(
                on_date=date(2026, 5, 28),
                department_id=None,
                employee_id=None,
                status="NOT_A_STATUS",
                page=1,
                page_size=10,
            )
        )
    with pytest.raises(NotFoundError, match="Employee not found"):
        GetDashboardTodayAttendance(**ctx).execute(
            DashboardAttendanceTableRequest(
                on_date=date(2026, 5, 28),
                department_id=None,
                employee_id=999,
                status=None,
                page=1,
                page_size=10,
            )
        )


def test_pending_requests_queue_filters_and_excludes_reviewed_items():
    pending = [
        pending_request("JUSTIFICATION", 1),
        pending_request("OVERTIME", 2),
        PendingDashboardRequest(
            request_category="JUSTIFICATION",
            request_id=3,
            employee_id=1,
            employee_name="Employee 1",
            employee_number="EMP001",
            attendance_record_id=13,
            attendance_status="ABSENT",
            request_type="ABSENCE",
            reason="Already reviewed.",
            requested_minutes=None,
            eligible_minutes_at_submission=None,
            status="APPROVED",
            created_at=datetime(2026, 5, 28, 19, 0),
        ),
    ]
    ctx = dashboard_context(records=[record()], pending=pending)
    result = GetDashboardPendingRequests(**ctx).execute(
        DashboardPendingRequestsRequest(
            request_type=None,
            employee_id=None,
            page=1,
            page_size=10,
        )
    )
    assert result.summary.pending_justification_count == 1
    assert result.summary.pending_overtime_request_count == 1
    assert result.total == 2
    assert all(item.status == "PENDING" for item in result.items)

    overtime_only = GetDashboardPendingRequests(**ctx).execute(
        DashboardPendingRequestsRequest(
            request_type="OVERTIME",
            employee_id=None,
            page=1,
            page_size=10,
        )
    )
    assert overtime_only.total == 1
    assert overtime_only.items[0].request_category == "OVERTIME"


def test_department_summary_includes_active_departments_with_zero_values():
    dep1 = department(1, "Computer Science")
    dep2 = department(2, "Math")
    emp1 = employee(1, dep1)
    emp2 = employee(2, dep2)
    absent = record(
        id=3,
        employee=emp1,
        attendance_date=date(2026, 5, 18),
        status=AttendanceStatus.ABSENT,
        check_in_time=None,
        check_out_time=None,
        working_hours=None,
    )
    result = GetDashboardDepartmentSummary(
        **dashboard_context([absent], departments=[dep1, dep2], employees=[emp1, emp2])
    ).execute(
        DashboardDepartmentSummaryRequest(
            on_date=date(2026, 5, 18),
            page=1,
            page_size=10,
        )
    )
    assert result.total == 2
    by_department = {item.department_id: item for item in result.items}
    assert by_department[1].absent_count == 1
    assert by_department[2].total_records == 0


def test_attendance_trend_returns_chronological_zero_value_days():
    unscheduled = record(
        id=4,
        attendance_date=date(2026, 5, 28),
        status=AttendanceStatus.UNSCHEDULED,
        is_unscheduled=True,
    )
    absent = record(
        id=3,
        attendance_date=date(2026, 5, 27),
        status=AttendanceStatus.ABSENT,
        check_in_time=None,
        check_out_time=None,
    )
    result = GetDashboardAttendanceTrend(**dashboard_context([unscheduled, absent])).execute(
        DashboardAttendanceTrendRequest(days=3, end_date=date(2026, 5, 28))
    )
    assert [item.date for item in result.items] == [
        date(2026, 5, 26),
        date(2026, 5, 27),
        date(2026, 5, 28),
    ]
    assert result.items[0].scheduled_processed_shift_count == 0
    assert result.items[1].absent_count == 1
    assert result.items[2].unscheduled_attendance_count == 1
    assert result.items[2].attendance_rate_percentage is None


def test_attendance_trend_rejects_too_many_days():
    with pytest.raises(BadRequestError, match="days"):
        GetDashboardAttendanceTrend(**dashboard_context()).execute(
            DashboardAttendanceTrendRequest(days=32, end_date=date(2026, 5, 28))
        )


def test_recent_activity_returns_safe_mapped_items_and_validates_limit():
    activities = [
        DashboardActivity(
            activity_type="ATTENDANCE_CHECK_OUT",
            employee_id=1,
            employee_name="Employee 1",
            description="Employee checked out successfully.",
            occurred_at=datetime(2026, 5, 28, 17, 52),
            related_entity_type="AttendanceRecord",
            related_entity_id=4,
        )
    ]
    use_case = GetDashboardRecentActivity(**dashboard_context(activities=activities))
    result = use_case.execute(DashboardRecentActivityRequest(limit=10))
    assert result.items[0].description == "Employee checked out successfully."
    assert result.items[0].occurred_at == "2026-05-28T19:52:00+02:00"
    assert not hasattr(result.items[0], "old_values")
    assert not hasattr(result.items[0], "new_values")

    with pytest.raises(BadRequestError, match="limit"):
        use_case.execute(DashboardRecentActivityRequest(limit=51))


def test_multifact_records_are_counted_once_but_in_all_relevant_metrics():
    item = record(
        id=9,
        is_late=True,
        status=AttendanceStatus.MISSING_CHECKOUT,
        is_missing_checkout=True,
        check_out_time=None,
        justification_requests=[
            justification("MISSING_CHECKOUT", RequestStatus.APPROVED, 1),
            justification("LATE", RequestStatus.PENDING, 2),
        ],
        overtime_requests=[
            overtime(OvertimeStatus.APPROVED, approved_minutes=30, request_id=1),
            overtime(OvertimeStatus.APPROVED, approved_minutes=15, request_id=2),
        ],
    )
    result = GetDashboardSummary(**dashboard_context([item])).execute(
        DashboardSummaryRequest(on_date=date(2026, 5, 28))
    )
    assert result.attendance.total_records == 1
    assert result.attendance.late_count == 1
    assert result.attendance.missing_checkout_count == 1
    assert result.attendance.open_check_in_count == 0
    assert result.overtime.approved_overtime_minutes == 45


def test_dashboard_use_cases_are_read_only_for_records_settings_and_face_data():
    item = record()
    before = item.__dict__.copy()
    ctx = dashboard_context([item])
    GetDashboardSummary(**ctx).execute(DashboardSummaryRequest(on_date=date(2026, 5, 28)))
    GetDashboardTodayAttendance(**ctx).execute(
        DashboardAttendanceTableRequest(
            on_date=date(2026, 5, 28),
            department_id=None,
            employee_id=None,
            status=None,
            page=1,
            page_size=10,
        )
    )
    assert item.__dict__ == before


def test_dashboard_routes_require_authentication():
    client = TestClient(create_app())
    assert client.get("/dashboard/summary").status_code in {401, 403}
    assert client.get("/dashboard/today-attendance").status_code in {401, 403}
    assert client.get("/dashboard/pending-requests").status_code in {401, 403}
    assert client.get("/dashboard/recent-activity").status_code in {401, 403}
