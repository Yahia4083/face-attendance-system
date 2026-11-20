from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.dto.attendance_dto import CreateAttendanceCorrectionRequest
from app.application.use_cases.attendance.attendance_management import CreateAttendanceCorrection
from app.application.use_cases.exceptions import BadRequestError, NotFoundError
from app.domain.enums.attendance_status import AttendanceStatus
from app.main import create_app
from app.presentation.api.attendance import _record_response


class FakeClock:
    def __init__(self, current=None):
        self.current = current or datetime(2026, 5, 28, 20, 5)

    def now_utc(self):
        return self.current.replace(tzinfo=UTC)

    def now_in_timezone(self, timezone_name):
        return self.current


class FakeAuditRepo:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


class FakeAttendanceRepo:
    def __init__(self, record):
        self.record = record

    def get_by_id(self, attendance_id):
        return self.record if self.record and self.record.id == attendance_id else None


class FakeCorrectionRepo:
    def __init__(self):
        self.items = []
        self.next_id = 1

    def create(self, commit=False, **kwargs):
        correction = SimpleNamespace(id=self.next_id, created_at=kwargs["corrected_at"], **kwargs)
        self.next_id += 1
        self.items.append(correction)
        return correction

    def list_for_attendance(self, attendance_record_id):
        return [item for item in self.items if item.attendance_record_id == attendance_record_id]


def attendance_record():
    employee = SimpleNamespace(id=1, full_name="Employee One", employee_number="EMP001")
    return SimpleNamespace(
        id=3,
        employee_id=1,
        employee=employee,
        employee_schedule_id=1,
        schedule_template_id=1,
        schedule_template=SimpleNamespace(id=1, name="Morning Shift"),
        attendance_date=date(2026, 5, 18),
        scheduled_start_datetime=datetime(2026, 5, 18, 8, 0),
        scheduled_end_datetime=datetime(2026, 5, 18, 16, 0),
        check_in_time=None,
        check_out_time=None,
        working_hours=None,
        status=AttendanceStatus.ABSENT,
        is_late=False,
        is_early_departure=False,
        is_unscheduled=False,
        is_missing_checkout=False,
        late_minutes=0,
        early_departure_minutes=0,
        justification_requests=[],
        overtime_requests=[],
        corrections=[],
        recognition_model_name=None,
        created_at=datetime(2026, 5, 18, 16, 30),
        updated_at=datetime(2026, 5, 18, 16, 30),
    )


def correction_use_case(record, correction_repo=None, audit_repo=None):
    return CreateAttendanceCorrection(
        attendance_repo=FakeAttendanceRepo(record),
        correction_repo=correction_repo or FakeCorrectionRepo(),
        audit_repo=audit_repo or FakeAuditRepo(),
        clock=FakeClock(),
    )


def test_admin_can_create_correction_with_reason_and_preserve_factual_record():
    record = attendance_record()
    correction_repo = FakeCorrectionRepo()
    audit_repo = FakeAuditRepo()
    correction = correction_use_case(record, correction_repo, audit_repo).execute(
        CreateAttendanceCorrectionRequest(
            attendance_id=record.id,
            corrected_status="PRESENT",
            reason="Verified administrative correction after approved documentation.",
            actor_user_id=1,
            ip_address="127.0.0.1",
        )
    )

    assert correction.corrected_status == "PRESENT"
    assert record.status == AttendanceStatus.ABSENT
    assert record.check_in_time is None
    assert record.check_out_time is None
    assert audit_repo.entries[0]["action"] == "CREATE_ATTENDANCE_CORRECTION"
    assert "embedding" not in str(audit_repo.entries[0]).lower()


def test_empty_or_invalid_correction_values_are_rejected():
    use_case = correction_use_case(attendance_record())
    with pytest.raises(BadRequestError, match="Correction reason"):
        use_case.execute(
            CreateAttendanceCorrectionRequest(
                attendance_id=3,
                corrected_status="PRESENT",
                reason="too short",
                actor_user_id=1,
            )
        )
    with pytest.raises(BadRequestError, match="Invalid corrected"):
        use_case.execute(
            CreateAttendanceCorrectionRequest(
                attendance_id=3,
                corrected_status="INVALID",
                reason="This correction reason is long enough.",
                actor_user_id=1,
            )
        )


def test_correction_rejects_missing_attendance_record():
    with pytest.raises(NotFoundError, match="Attendance record not found"):
        correction_use_case(None).execute(
            CreateAttendanceCorrectionRequest(
                attendance_id=999,
                corrected_status="PRESENT",
                reason="This correction reason is long enough.",
                actor_user_id=1,
            )
        )


def test_attendance_record_response_exposes_original_and_effective_status_with_offsets():
    record = attendance_record()
    correction = SimpleNamespace(
        id=1,
        attendance_record_id=record.id,
        original_status="ABSENT",
        corrected_status="PRESENT",
        reason="Verified administrative correction after approved documentation.",
        corrected_by_user_id=1,
        corrected_at=datetime(2026, 5, 28, 20, 5),
        created_at=datetime(2026, 5, 28, 20, 5),
    )
    record.corrections = [correction]

    payload = _record_response(record).model_dump()

    assert payload["status"] == "ABSENT"
    assert payload["original_status"] == "ABSENT"
    assert payload["effective_status"] == "PRESENT"
    assert payload["has_admin_correction"] is True
    assert payload["latest_correction"]["corrected_at"] == "2026-05-28T20:05:00+02:00"
    assert payload["scheduled_start_datetime"] == "2026-05-18T08:00:00+02:00"


def test_correction_endpoint_requires_admin_authentication():
    response = TestClient(create_app()).post(
        "/attendance/records/3/corrections",
        json={
            "corrected_status": "PRESENT",
            "reason": "Verified administrative correction after approved documentation.",
        },
    )
    assert response.status_code in {401, 403}
