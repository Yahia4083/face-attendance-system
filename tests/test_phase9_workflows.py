from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.dto.attendance_processing_dto import ProcessDailyAttendanceRequest
from app.application.dto.justification_request_dto import (
    CreateJustificationRequestDTO,
    ListJustificationRequestsDTO,
    ListMyJustificationRequestsDTO,
    ReviewJustificationRequestDTO,
)
from app.application.dto.overtime_request_dto import (
    ApproveOvertimeRequestDTO,
    CreateOvertimeRequestDTO,
    ListMyOvertimeRequestsDTO,
    ListOvertimeRequestsDTO,
    RejectOvertimeRequestDTO,
)
from app.application.use_cases.attendance.process_daily_attendance import ProcessDailyAttendance
from app.application.use_cases.exceptions import BadRequestError, ConflictError
from app.application.use_cases.justifications.justification_management import (
    ApproveJustificationRequest,
    CreateJustificationRequest,
    ListJustificationRequests,
    ListMyJustificationRequests,
    RejectJustificationRequest,
)
from app.application.use_cases.overtime.overtime_management import (
    ApproveOvertimeRequest,
    CreateOvertimeRequest,
    ListMyOvertimeRequests,
    ListOvertimeRequests,
    RejectOvertimeRequest,
)
from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.repositories.justification_request_repository import JustificationRequestFilters
from app.domain.repositories.overtime_request_repository import OvertimeRequestFilters
from app.main import create_app


def now():
    return datetime.now(UTC).replace(tzinfo=None)


class FakeClock:
    def __init__(self, current):
        self.current = current

    def now_utc(self):
        return self.current.replace(tzinfo=UTC)

    def now_in_timezone(self, timezone_name):
        return self.current.replace(tzinfo=UTC)


class FakeAuditRepo:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


class FakeEmployeeRepo:
    def __init__(self):
        self.employees = {
            1: SimpleNamespace(id=1, user_id=10, full_name="Employee One", employee_number="EMP001", is_active=True),
            2: SimpleNamespace(id=2, user_id=20, full_name="Employee Two", employee_number="EMP002", is_active=True),
        }

    def get_by_id(self, employee_id):
        return self.employees.get(employee_id)

    def get_by_user_id(self, user_id):
        for employee in self.employees.values():
            if employee.user_id == user_id:
                return employee
        return None


class FakeScheduleRepo:
    def __init__(self):
        self.assignments = []

    def add_assignment(
        self,
        *,
        employee_id=1,
        assignment_id=1,
        start=time(8, 0),
        end=time(16, 0),
        is_overnight=False,
        working_days=None,
        active=True,
    ):
        template = SimpleNamespace(
            id=assignment_id,
            name="Night Shift" if is_overnight else "Morning Shift",
            start_time=start,
            end_time=end,
            is_overnight=is_overnight,
            check_in_grace_minutes=10,
            early_departure_tolerance_minutes=5,
        )
        assignment = SimpleNamespace(
            id=assignment_id,
            employee_id=employee_id,
            schedule_template_id=template.id,
            schedule_template=template,
            effective_start_date=date(2026, 6, 1),
            effective_end_date=None,
            working_days=",".join(str(day) for day in (working_days or [0, 1, 2, 3, 4])),
            is_active=active,
        )
        self.assignments.append(assignment)
        return assignment

    def list_active_assignments_for_date(self, *, on_date):
        return [
            item
            for item in self.assignments
            if item.is_active
            and item.effective_start_date <= on_date
            and (item.effective_end_date is None or item.effective_end_date >= on_date)
        ]


class FakeAttendanceRepo:
    def __init__(self, employee_repo):
        self.employee_repo = employee_repo
        self.records = []
        self.next_id = 1

    def add_record(self, **overrides):
        values = {
            "id": self.next_id,
            "employee_id": 1,
            "employee_schedule_id": 1,
            "schedule_template_id": 1,
            "attendance_date": date(2026, 6, 1),
            "scheduled_start_datetime": datetime(2026, 6, 1, 8, 0),
            "scheduled_end_datetime": datetime(2026, 6, 1, 16, 0),
            "check_in_time": None,
            "check_out_time": None,
            "working_hours": None,
            "status": AttendanceStatus.ABSENT,
            "is_late": False,
            "is_early_departure": False,
            "is_unscheduled": False,
            "is_missing_checkout": False,
            "late_minutes": 0,
            "early_departure_minutes": 0,
            "recognition_model_name": None,
            "detector_backend": None,
            "processed_at": None,
            "created_at": now(),
            "updated_at": now(),
        }
        values.update(overrides)
        record = SimpleNamespace(**values)
        record.employee = self.employee_repo.get_by_id(record.employee_id)
        record.justification_requests = []
        record.overtime_requests = []
        self.next_id += 1
        self.records.append(record)
        return record

    def get_by_id(self, attendance_id):
        return next((record for record in self.records if record.id == attendance_id), None)

    def find_existing_for_shift(self, *, employee_id, schedule_date, employee_schedule_id, is_unscheduled):
        for record in self.records:
            if record.employee_id != employee_id or record.attendance_date != schedule_date:
                continue
            if is_unscheduled and record.is_unscheduled:
                return record
            if not is_unscheduled and record.employee_schedule_id == employee_schedule_id:
                return record
        return None

    def create_absent_record(self, commit=False, **kwargs):
        return self.add_record(
            employee_id=kwargs["employee_id"],
            employee_schedule_id=kwargs["employee_schedule_id"],
            schedule_template_id=kwargs["schedule_template_id"],
            attendance_date=kwargs["schedule_date"],
            scheduled_start_datetime=kwargs["scheduled_start_datetime"],
            scheduled_end_datetime=kwargs["scheduled_end_datetime"],
            status=AttendanceStatus.ABSENT,
            processed_at=kwargs["processed_at"],
        )

    def mark_missing_checkout(self, *, attendance_id, processed_at, commit=False):
        record = self.get_by_id(attendance_id)
        record.status = AttendanceStatus.MISSING_CHECKOUT
        record.is_missing_checkout = True
        record.processed_at = processed_at
        return record

    def list_records(self, *, filters, page, page_size):
        rows = self.records
        if filters.employee_id is not None:
            rows = [row for row in rows if row.employee_id == filters.employee_id]
        return rows[(page - 1) * page_size : page * page_size]

    def count_records(self, *, filters):
        return len(self.list_records(filters=filters, page=1, page_size=1000))


class FakeJustificationRepo:
    def __init__(self, attendance_repo=None):
        self.items = []
        self.next_id = 1
        self.attendance_repo = attendance_repo

    def create(self, commit=False, **kwargs):
        attendance_record = (
            self.attendance_repo.get_by_id(kwargs["attendance_record_id"])
            if self.attendance_repo is not None
            else None
        )
        item = SimpleNamespace(
            id=self.next_id,
            employee_id=kwargs["employee_id"],
            attendance_record_id=kwargs["attendance_record_id"],
            request_type=kwargs["request_type"],
            explanation=kwargs["reason"],
            status=RequestStatus.PENDING,
            reviewed_by=None,
            admin_comment=None,
            reviewed_at=None,
            created_at=now(),
            updated_at=now(),
            employee=None,
            attendance_date=getattr(attendance_record, "attendance_date", None),
        )
        self.next_id += 1
        self.items.append(item)
        return item

    def get_by_id(self, request_id):
        return next((item for item in self.items if item.id == request_id), None)

    def list_for_employee(self, employee_id, *, filters, page, page_size):
        return [item for item in self.items if item.employee_id == employee_id]

    def count_for_employee(self, employee_id, *, filters):
        return len(self.list_for_employee(employee_id, filters=filters, page=1, page_size=1000))

    def list_all(self, *, filters, page, page_size):
        items = self.items
        if filters.status:
            items = [item for item in items if item.status.value == filters.status]
        return items

    def count_all(self, *, filters):
        return len(self.list_all(filters=filters, page=1, page_size=1000))

    def has_pending_for_attendance_and_type(self, *, attendance_record_id, request_type):
        return any(
            item.attendance_record_id == attendance_record_id
            and item.request_type == request_type
            and item.status == RequestStatus.PENDING
            for item in self.items
        )

    def has_approved_for_attendance_and_type(self, *, attendance_record_id, request_type):
        return any(
            item.attendance_record_id == attendance_record_id
            and item.request_type == request_type
            and item.status == RequestStatus.APPROVED
            for item in self.items
        )

    def exists_for_attendance(self, *, attendance_record_id):
        return any(item.attendance_record_id == attendance_record_id for item in self.items)

    def count_for_employee_attendance_month(self, *, employee_id, month_start, month_end):
        return sum(
            1
            for item in self.items
            if item.employee_id == employee_id
            and item.attendance_date is not None
            and month_start <= item.attendance_date <= month_end
        )

    def approve(self, *, request_id, reviewer_user_id, reviewer_note, reviewed_at, commit=False):
        item = self.get_by_id(request_id)
        item.status = RequestStatus.APPROVED
        item.reviewed_by = reviewer_user_id
        item.admin_comment = reviewer_note
        item.reviewed_at = reviewed_at
        return item

    def reject(self, *, request_id, reviewer_user_id, reviewer_note, reviewed_at, commit=False):
        item = self.get_by_id(request_id)
        item.status = RequestStatus.REJECTED
        item.reviewed_by = reviewer_user_id
        item.admin_comment = reviewer_note
        item.reviewed_at = reviewed_at
        return item


class FakeOvertimeRepo:
    def __init__(self):
        self.items = []
        self.next_id = 1

    def create(self, commit=False, **kwargs):
        item = SimpleNamespace(
            id=self.next_id,
            employee_id=kwargs["employee_id"],
            attendance_record_id=kwargs["attendance_record_id"],
            overtime_minutes=kwargs["requested_minutes"],
            eligible_minutes_at_submission=kwargs["eligible_minutes_at_submission"],
            approved_minutes=None,
            reason=kwargs["reason"],
            status=OvertimeStatus.PENDING,
            reviewed_by=None,
            reviewer_note=None,
            reviewed_at=None,
            created_at=now(),
            updated_at=now(),
            employee=None,
        )
        self.next_id += 1
        self.items.append(item)
        return item

    def get_by_id(self, request_id):
        return next((item for item in self.items if item.id == request_id), None)

    def list_for_employee(self, employee_id, *, filters, page, page_size):
        return [item for item in self.items if item.employee_id == employee_id]

    def count_for_employee(self, employee_id, *, filters):
        return len(self.list_for_employee(employee_id, filters=filters, page=1, page_size=1000))

    def list_all(self, *, filters, page, page_size):
        items = self.items
        if filters.status:
            items = [item for item in items if item.status.value == filters.status]
        return items

    def count_all(self, *, filters):
        return len(self.list_all(filters=filters, page=1, page_size=1000))

    def has_pending_for_attendance(self, *, attendance_record_id):
        return any(
            item.attendance_record_id == attendance_record_id
            and item.status == OvertimeStatus.PENDING
            for item in self.items
        )

    def has_approved_for_attendance(self, *, attendance_record_id):
        return any(
            item.attendance_record_id == attendance_record_id
            and item.status == OvertimeStatus.APPROVED
            for item in self.items
        )

    def approve(self, *, request_id, approved_minutes, reviewer_user_id, reviewer_note, reviewed_at, commit=False):
        item = self.get_by_id(request_id)
        item.status = OvertimeStatus.APPROVED
        item.approved_minutes = approved_minutes
        item.reviewed_by = reviewer_user_id
        item.reviewer_note = reviewer_note
        item.reviewed_at = reviewed_at
        return item

    def reject(self, *, request_id, reviewer_user_id, reviewer_note, reviewed_at, commit=False):
        item = self.get_by_id(request_id)
        item.status = OvertimeStatus.REJECTED
        item.reviewed_by = reviewer_user_id
        item.reviewer_note = reviewer_note
        item.reviewed_at = reviewed_at
        return item


@pytest.fixture()
def context(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ATTENDANCE_PROCESSING_DELAY_MINUTES", 30)
    monkeypatch.setattr(settings, "MISSING_CHECKOUT_DELAY_MINUTES", 240)
    monkeypatch.setattr(settings, "OVERTIME_MINIMUM_MINUTES", 30)
    monkeypatch.setattr(settings, "JUSTIFICATION_MONTHLY_LIMIT", 3)
    employee_repo = FakeEmployeeRepo()
    attendance_repo = FakeAttendanceRepo(employee_repo)
    return {
        "employee_repo": employee_repo,
        "schedule_repo": FakeScheduleRepo(),
        "attendance_repo": attendance_repo,
        "justification_repo": FakeJustificationRepo(attendance_repo),
        "overtime_repo": FakeOvertimeRepo(),
        "audit_repo": FakeAuditRepo(),
    }


def process_use_case(context, clock):
    return ProcessDailyAttendance(
        attendance_repo=context["attendance_repo"],
        schedule_repo=context["schedule_repo"],
        audit_repo=context["audit_repo"],
        clock=clock,
    )


def process_request():
    return ProcessDailyAttendanceRequest(on_date=date(2026, 6, 1), actor_user_id=1)


def test_process_daily_creates_absent_after_shift_end(context):
    context["schedule_repo"].add_assignment()
    result = process_use_case(context, FakeClock(datetime(2026, 6, 1, 16, 31))).execute(process_request())

    assert result.absent_records_created == 1
    assert context["attendance_repo"].records[0].status == AttendanceStatus.ABSENT
    assert "CREATE_ABSENT_ATTENDANCE" in [entry["action"] for entry in context["audit_repo"].entries]


def test_process_daily_does_not_create_absent_before_delay(context):
    context["schedule_repo"].add_assignment()

    with pytest.raises(BadRequestError, match="eligible"):
        process_use_case(context, FakeClock(datetime(2026, 6, 1, 16, 29))).execute(process_request())
    assert context["attendance_repo"].records == []


def test_process_daily_skips_non_working_day_and_inactive_assignment(context):
    context["schedule_repo"].add_assignment(working_days=[1])
    context["schedule_repo"].add_assignment(assignment_id=2, active=False)
    result = process_use_case(context, FakeClock(datetime(2026, 6, 1, 16, 31))).execute(process_request())

    assert result.processed_assignments == 0
    assert result.absent_records_created == 0


def test_process_daily_is_idempotent(context):
    context["schedule_repo"].add_assignment()
    use_case = process_use_case(context, FakeClock(datetime(2026, 6, 1, 16, 31)))
    use_case.execute(process_request())
    result = use_case.execute(process_request())

    assert result.absent_records_created == 0
    assert result.already_processed_or_unchanged == 1
    assert len(context["attendance_repo"].records) == 1


def test_automatic_process_uses_system_actor_and_avoids_no_change_audit_noise(context):
    context["schedule_repo"].add_assignment()
    use_case = process_use_case(context, FakeClock(datetime(2026, 6, 1, 16, 31)))
    request = ProcessDailyAttendanceRequest(
        on_date=date(2026, 6, 1),
        actor_user_id=None,
        is_automatic=True,
    )

    first_result = use_case.execute(request)
    first_entries = list(context["audit_repo"].entries)
    second_result = use_case.execute(request)

    assert first_result.absent_records_created == 1
    assert second_result.absent_records_created == 0
    assert all(entry["actor_user_id"] is None for entry in first_entries)
    assert '"trigger": "AUTOMATIC"' in first_entries[-1]["new_values"]
    assert context["audit_repo"].entries == first_entries


def test_process_daily_marks_missing_checkout_and_preserves_late(context):
    context["schedule_repo"].add_assignment()
    record = context["attendance_repo"].add_record(
        check_in_time=datetime(2026, 6, 1, 8, 30),
        status=AttendanceStatus.LATE,
        is_late=True,
    )
    result = process_use_case(context, FakeClock(datetime(2026, 6, 1, 20, 0))).execute(process_request())

    assert result.missing_checkout_records_updated == 1
    assert record.status == AttendanceStatus.MISSING_CHECKOUT
    assert record.is_missing_checkout is True
    assert record.is_late is True


def test_process_daily_keeps_open_check_in_during_four_hour_overtime_window(context):
    context["schedule_repo"].add_assignment()
    record = context["attendance_repo"].add_record(
        check_in_time=datetime(2026, 6, 1, 8, 0),
        status=AttendanceStatus.PRESENT,
    )

    result = process_use_case(context, FakeClock(datetime(2026, 6, 1, 19, 59))).execute(
        process_request()
    )

    assert result.missing_checkout_records_updated == 0
    assert record.status == AttendanceStatus.PRESENT
    assert record.is_missing_checkout is False


def test_process_daily_handles_overnight_after_next_day_end(context):
    context["schedule_repo"].add_assignment(start=time(20, 0), end=time(4, 0), is_overnight=True)

    with pytest.raises(BadRequestError):
        process_use_case(context, FakeClock(datetime(2026, 6, 2, 4, 29))).execute(process_request())

    result = process_use_case(context, FakeClock(datetime(2026, 6, 2, 4, 31))).execute(process_request())
    assert result.absent_records_created == 1
    assert context["attendance_repo"].records[0].scheduled_end_datetime == datetime(2026, 6, 2, 4, 0)


def test_process_daily_endpoint_requires_admin():
    response = TestClient(create_app()).post("/attendance/process-daily", json={"on_date": "2026-06-01"})

    assert response.status_code in {401, 403}


class FakeSettingsProvider:
    def __init__(self, values):
        self.values = values

    def get_integer(self, key):
        return self.values[key]


def create_justification(context, attendance_record, request_type="LATE", user_id=10, settings_provider=None):
    return CreateJustificationRequest(
        employee_repo=context["employee_repo"],
        attendance_repo=context["attendance_repo"],
        justification_repo=context["justification_repo"],
        audit_repo=context["audit_repo"],
        settings_provider=settings_provider,
    ).execute(
        CreateJustificationRequestDTO(
            user_id=user_id,
            attendance_record_id=attendance_record.id,
            request_type=request_type,
            reason="Medical emergency prevented attendance.",
        )
    )


def test_absence_justification_is_rejected_and_late_early_missing_are_allowed(context):
    absent = context["attendance_repo"].add_record(status=AttendanceStatus.ABSENT)
    late = context["attendance_repo"].add_record(id=99, status=AttendanceStatus.LATE, is_late=True)
    early = context["attendance_repo"].add_record(id=100, status=AttendanceStatus.PRESENT, is_early_departure=True)
    missing = context["attendance_repo"].add_record(id=101, status=AttendanceStatus.MISSING_CHECKOUT, is_missing_checkout=True)

    with pytest.raises(BadRequestError, match="Invalid justification"):
        create_justification(context, absent, "ABSENCE")
    assert create_justification(context, late, "LATE").status == RequestStatus.PENDING
    assert create_justification(context, early, "EARLY_DEPARTURE").status == RequestStatus.PENDING
    assert create_justification(context, missing, "MISSING_CHECKOUT").status == RequestStatus.PENDING


def test_employee_cannot_submit_justification_for_other_employee_or_present(context):
    other = context["attendance_repo"].add_record(employee_id=2, status=AttendanceStatus.LATE, is_late=True)
    present = context["attendance_repo"].add_record(status=AttendanceStatus.PRESENT)

    with pytest.raises(BadRequestError, match="another employee"):
        create_justification(context, other, "LATE")
    with pytest.raises(BadRequestError, match="not eligible"):
        create_justification(context, present, "LATE")


def test_any_existing_justification_blocks_another_request_for_record(context):
    late = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)
    create_justification(context, late, "LATE")

    with pytest.raises(ConflictError, match="already been submitted"):
        create_justification(context, late, "LATE")


def test_rejected_and_approved_justifications_still_block_new_request(context):
    late = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)
    rejected = create_justification(context, late, "LATE")
    RejectJustificationRequest(
        justification_repo=context["justification_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    ).execute(ReviewJustificationRequestDTO(request_id=rejected.id, reviewer_user_id=1, reviewer_note="Rejected"))
    with pytest.raises(ConflictError, match="already been submitted"):
        create_justification(context, late, "LATE")

    early = context["attendance_repo"].add_record(status=AttendanceStatus.PRESENT, is_early_departure=True)
    approved = create_justification(context, early, "EARLY_DEPARTURE")
    ApproveJustificationRequest(
        justification_repo=context["justification_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    ).execute(ReviewJustificationRequestDTO(request_id=approved.id, reviewer_user_id=1, reviewer_note="Ok"))
    with pytest.raises(ConflictError, match="already been submitted"):
        create_justification(context, early, "EARLY_DEPARTURE")


def test_admin_can_approve_and_reject_justifications_and_cannot_review_twice(context):
    late = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)
    first = create_justification(context, late, "LATE")
    approve = ApproveJustificationRequest(
        justification_repo=context["justification_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    )
    approved = approve.execute(
        ReviewJustificationRequestDTO(request_id=first.id, reviewer_user_id=1, reviewer_note="Accepted")
    )

    assert approved.status == RequestStatus.APPROVED
    with pytest.raises(BadRequestError, match="pending"):
        approve.execute(
            ReviewJustificationRequestDTO(request_id=first.id, reviewer_user_id=1, reviewer_note="Again")
        )

    early = context["attendance_repo"].add_record(status=AttendanceStatus.PRESENT, is_early_departure=True)
    second = create_justification(context, early, "EARLY_DEPARTURE")
    rejected = RejectJustificationRequest(
        justification_repo=context["justification_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    ).execute(
        ReviewJustificationRequestDTO(request_id=second.id, reviewer_user_id=1, reviewer_note="Rejected")
    )
    assert rejected.status == RequestStatus.REJECTED


def test_justification_approval_does_not_modify_attendance_timestamps_and_lists_are_scoped(context):
    late = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)
    original_check_in = late.check_in_time
    item = create_justification(context, late, "LATE")
    ApproveJustificationRequest(
        justification_repo=context["justification_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    ).execute(ReviewJustificationRequestDTO(request_id=item.id, reviewer_user_id=1, reviewer_note="Ok"))

    mine = ListMyJustificationRequests(
        employee_repo=context["employee_repo"],
        justification_repo=context["justification_repo"],
    ).execute(ListMyJustificationRequestsDTO(user_id=10, filters=JustificationRequestFilters(), page=1, page_size=10))
    all_items = ListJustificationRequests(context["justification_repo"]).execute(
        ListJustificationRequestsDTO(filters=JustificationRequestFilters(status="APPROVED"), page=1, page_size=10)
    )
    assert late.check_in_time == original_check_in
    assert len(mine.items) == 1
    assert len(all_items.items) == 1
    assert "embedding" not in str(context["audit_repo"].entries).lower()


def test_unscheduled_record_cannot_be_treated_as_late(context):
    unscheduled = context["attendance_repo"].add_record(
        status=AttendanceStatus.UNSCHEDULED,
        is_unscheduled=True,
        is_late=True,
        scheduled_start_datetime=None,
        scheduled_end_datetime=None,
        late_minutes=15,
        employee_schedule_id=None,
        schedule_template_id=None,
    )

    with pytest.raises(BadRequestError, match="not eligible"):
        create_justification(context, unscheduled, "LATE")


def test_monthly_justification_limit_zero_rejects_all_new_requests(context):
    late = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)

    with pytest.raises(ConflictError, match="monthly justification limit"):
        create_justification(
            context,
            late,
            "LATE",
            settings_provider=FakeSettingsProvider({"JUSTIFICATION_MONTHLY_LIMIT": 0}),
        )


def test_monthly_limit_allows_first_and_rejects_second_same_month(context):
    first = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)
    second = context["attendance_repo"].add_record(id=200, status=AttendanceStatus.PRESENT, is_early_departure=True)
    provider = FakeSettingsProvider({"JUSTIFICATION_MONTHLY_LIMIT": 1})

    assert create_justification(context, first, "LATE", settings_provider=provider).status == RequestStatus.PENDING
    with pytest.raises(ConflictError, match="monthly justification limit"):
        create_justification(context, second, "EARLY_DEPARTURE", settings_provider=provider)


def test_rejected_requests_count_toward_monthly_limit(context):
    first = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)
    second = context["attendance_repo"].add_record(id=201, status=AttendanceStatus.PRESENT, is_early_departure=True)
    provider = FakeSettingsProvider({"JUSTIFICATION_MONTHLY_LIMIT": 1})
    item = create_justification(context, first, "LATE", settings_provider=provider)
    RejectJustificationRequest(
        justification_repo=context["justification_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    ).execute(ReviewJustificationRequestDTO(request_id=item.id, reviewer_user_id=1, reviewer_note="Rejected"))

    with pytest.raises(ConflictError, match="monthly justification limit"):
        create_justification(context, second, "EARLY_DEPARTURE", settings_provider=provider)


def test_monthly_limit_is_scoped_by_employee_and_month(context):
    first = context["attendance_repo"].add_record(status=AttendanceStatus.LATE, is_late=True)
    next_month = context["attendance_repo"].add_record(
        id=202,
        status=AttendanceStatus.PRESENT,
        is_early_departure=True,
        attendance_date=date(2026, 7, 1),
        scheduled_start_datetime=datetime(2026, 7, 1, 8, 0),
        scheduled_end_datetime=datetime(2026, 7, 1, 16, 0),
    )
    other_employee = context["attendance_repo"].add_record(
        id=203,
        employee_id=2,
        status=AttendanceStatus.LATE,
        is_late=True,
    )
    provider = FakeSettingsProvider({"JUSTIFICATION_MONTHLY_LIMIT": 1})

    create_justification(context, first, "LATE", settings_provider=provider)
    assert create_justification(context, next_month, "EARLY_DEPARTURE", settings_provider=provider).status == RequestStatus.PENDING
    assert create_justification(context, other_employee, "LATE", user_id=20, settings_provider=provider).status == RequestStatus.PENDING


def create_overtime(context, attendance_record, requested=60, user_id=10):
    return CreateOvertimeRequest(
        employee_repo=context["employee_repo"],
        attendance_repo=context["attendance_repo"],
        overtime_repo=context["overtime_repo"],
        audit_repo=context["audit_repo"],
    ).execute(
        CreateOvertimeRequestDTO(
            user_id=user_id,
            attendance_record_id=attendance_record.id,
            requested_minutes=requested,
            reason="Completed required work after the scheduled shift ended.",
        )
    )


def eligible_overtime_record(context, **overrides):
    values = {
        "status": AttendanceStatus.PRESENT,
        "check_in_time": datetime(2026, 6, 1, 8, 0),
        "check_out_time": datetime(2026, 6, 1, 17, 15),
        "scheduled_end_datetime": datetime(2026, 6, 1, 16, 0),
    }
    values.update(overrides)
    return context["attendance_repo"].add_record(**values)


def test_employee_can_submit_overtime_for_eligible_record(context):
    record = eligible_overtime_record(context)
    item = create_overtime(context, record, requested=60)

    assert item.overtime_minutes == 60
    assert item.eligible_minutes_at_submission == 75
    assert context["audit_repo"].entries[-1]["action"] == "CREATE_OVERTIME_REQUEST"


def test_overtime_rejects_unscheduled_absent_no_checkout_below_min_and_excess(context):
    with pytest.raises(BadRequestError, match="Unscheduled"):
        create_overtime(context, eligible_overtime_record(context, is_unscheduled=True))
    with pytest.raises(BadRequestError, match="Absent"):
        create_overtime(context, eligible_overtime_record(context, status=AttendanceStatus.ABSENT))
    with pytest.raises(BadRequestError, match="no check-out"):
        create_overtime(context, eligible_overtime_record(context, check_out_time=None))
    with pytest.raises(BadRequestError, match="below"):
        create_overtime(context, eligible_overtime_record(context, check_out_time=datetime(2026, 6, 1, 16, 10)), requested=5)
    with pytest.raises(BadRequestError, match="exceed"):
        create_overtime(context, eligible_overtime_record(context), requested=90)


def test_overtime_rejects_other_employee_and_duplicate_pending(context):
    other = eligible_overtime_record(context, employee_id=2)
    with pytest.raises(BadRequestError, match="another employee"):
        create_overtime(context, other)

    record = eligible_overtime_record(context)
    create_overtime(context, record)
    with pytest.raises(ConflictError, match="pending overtime"):
        create_overtime(context, record)


def test_admin_can_approve_reject_overtime_and_cannot_review_twice(context):
    record = eligible_overtime_record(context)
    item = create_overtime(context, record)
    approve = ApproveOvertimeRequest(
        overtime_repo=context["overtime_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    )
    approved = approve.execute(
        ApproveOvertimeRequestDTO(
            request_id=item.id,
            reviewer_user_id=1,
            approved_minutes=60,
            reviewer_note="Approved",
        )
    )
    assert approved.status == OvertimeStatus.APPROVED
    with pytest.raises(BadRequestError, match="pending"):
        approve.execute(
            ApproveOvertimeRequestDTO(
                request_id=item.id,
                reviewer_user_id=1,
                approved_minutes=60,
                reviewer_note="Again",
            )
        )

    second = create_overtime(context, eligible_overtime_record(context, id=999), requested=30)
    rejected = RejectOvertimeRequest(
        overtime_repo=context["overtime_repo"],
        audit_repo=context["audit_repo"],
        clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
    ).execute(
        RejectOvertimeRequestDTO(request_id=second.id, reviewer_user_id=1, reviewer_note="Rejected")
    )
    assert rejected.status == OvertimeStatus.REJECTED


def test_admin_cannot_approve_more_overtime_than_requested(context):
    item = create_overtime(context, eligible_overtime_record(context), requested=30)

    with pytest.raises(BadRequestError, match="must not exceed requested"):
        ApproveOvertimeRequest(
            overtime_repo=context["overtime_repo"],
            audit_repo=context["audit_repo"],
            clock=FakeClock(datetime(2026, 6, 2, 9, 0)),
        ).execute(
            ApproveOvertimeRequestDTO(
                request_id=item.id,
                reviewer_user_id=1,
                approved_minutes=60,
                reviewer_note="Too much",
            )
        )


def test_overtime_lists_are_scoped_and_audit_safe(context):
    create_overtime(context, eligible_overtime_record(context))
    mine = ListMyOvertimeRequests(
        employee_repo=context["employee_repo"],
        overtime_repo=context["overtime_repo"],
    ).execute(ListMyOvertimeRequestsDTO(user_id=10, filters=OvertimeRequestFilters(), page=1, page_size=10))
    all_items = ListOvertimeRequests(context["overtime_repo"]).execute(
        ListOvertimeRequestsDTO(filters=OvertimeRequestFilters(status="PENDING"), page=1, page_size=10)
    )

    assert len(mine.items) == 1
    assert len(all_items.items) == 1
    assert "embedding" not in str(context["audit_repo"].entries).lower()
