from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.dto.attendance_dto import AttendanceFaceRequest
from app.application.use_cases.attendance.attendance_management import (
    CheckInByFace,
    CheckOutByFace,
)
from app.application.use_cases.exceptions import ConflictError, NotFoundError
from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.repositories.face_embedding_repository import ActiveFaceEmbeddingForRecognition
from app.domain.services.face_processing_service import FaceDetectionResult
from app.domain.services.face_recognition_service import FaceRecognitionResult
from app.infrastructure.face_ai.facenet_recognition_service import FaceNetRecognitionService
from app.infrastructure.face_ai.image_validator import ImageValidator
from app.main import create_app
from app.presentation.api.attendance import _event_response


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


class FakeAuditRepo:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


class FakeClock:
    def __init__(self, current):
        self.current = current

    def now_utc(self):
        return self.current.replace(tzinfo=UTC)

    def now_in_timezone(self, timezone_name):
        return self.current.replace(tzinfo=UTC)


class FakeRecognitionService:
    def __init__(self, result=None, error=None):
        self.result = result or FaceRecognitionResult(
            matched=True,
            employee_id=1,
            matched_model_name="facenet-onnx-512d-haikalmumtaz-v1",
        )
        self.error = error

    def recognize(self, *, image_bytes, original_filename):
        if self.error is not None:
            raise self.error
        return self.result


class FakeEmployeeRepo:
    def __init__(self):
        self.employees = {
            1: SimpleNamespace(
                id=1,
                full_name="Employee One",
                employee_number="EMP001",
                is_active=True,
            ),
            2: SimpleNamespace(
                id=2,
                full_name="Employee Two",
                employee_number="EMP002",
                is_active=True,
            ),
            3: SimpleNamespace(
                id=3,
                full_name="Inactive Employee",
                employee_number="EMP003",
                is_active=False,
            ),
        }

    def get_by_id(self, employee_id):
        return self.employees.get(employee_id)

    def get_by_user_id(self, user_id):
        return self.employees.get(1) if user_id == 10 else None


class FakeScheduleRepo:
    def __init__(self):
        self.assignments = {}

    def add_assignment(
        self,
        *,
        employee_id=1,
        assignment_id=1,
        start=time(8, 0),
        end=time(16, 0),
        is_overnight=False,
        grace=10,
        tolerance=5,
        working_days=None,
        effective_start=date(2026, 6, 1),
        effective_end=None,
    ):
        template = SimpleNamespace(
            id=assignment_id,
            name="Night Shift Test" if is_overnight else "Morning Shift",
            start_time=start,
            end_time=end,
            is_overnight=is_overnight,
            check_in_grace_minutes=grace,
            early_departure_tolerance_minutes=tolerance,
        )
        assignment = SimpleNamespace(
            id=assignment_id,
            employee_id=employee_id,
            schedule_template_id=template.id,
            schedule_template=template,
            effective_start_date=effective_start,
            effective_end_date=effective_end,
            working_days=",".join(str(day) for day in (working_days or [0, 1, 2, 3, 4])),
            is_active=True,
        )
        self.assignments.setdefault(employee_id, []).append(assignment)
        return assignment

    def get_effective_schedule(self, *, employee_id, on_date):
        for assignment in self.assignments.get(employee_id, []):
            if not assignment.is_active:
                continue
            if assignment.effective_start_date <= on_date and (
                assignment.effective_end_date is None or assignment.effective_end_date >= on_date
            ):
                return assignment
        return None


class FakeAttendanceRepo:
    def __init__(self, employee_repo):
        self.employee_repo = employee_repo
        self.records = []
        self.next_id = 1

    def create_check_in(self, commit=False, **kwargs):
        employee = self.employee_repo.get_by_id(kwargs["employee_id"])
        template = None
        if kwargs["schedule_template_id"] is not None:
            template = SimpleNamespace(
                id=kwargs["schedule_template_id"],
                name="Night Shift Test" if kwargs["scheduled_end_datetime"] and kwargs[
                    "scheduled_end_datetime"
                ].date() > kwargs["schedule_date"] else "Morning Shift",
                early_departure_tolerance_minutes=5,
            )
        record = SimpleNamespace(
            id=self.next_id,
            employee=employee,
            schedule_template=template,
            employee_schedule=None,
            check_out_time=None,
            working_hours=None,
            is_early_departure=False,
            early_departure_minutes=0,
            created_at=_now(),
            updated_at=_now(),
            **kwargs,
        )
        record.attendance_date = kwargs["schedule_date"]
        record.check_in_time = kwargs["check_in_at"]
        self.next_id += 1
        self.records.append(record)
        return record

    def get_by_id(self, attendance_id):
        return next((record for record in self.records if record.id == attendance_id), None)

    def find_existing_for_shift(
        self,
        *,
        employee_id,
        schedule_date,
        employee_schedule_id,
        is_unscheduled,
    ):
        for record in self.records:
            if record.employee_id != employee_id or record.attendance_date != schedule_date:
                continue
            if is_unscheduled and record.is_unscheduled and record.check_out_time is None:
                return record
            if (
                not is_unscheduled
                and not record.is_unscheduled
                and record.employee_schedule_id == employee_schedule_id
            ):
                return record
        return None

    def find_open_for_employee(self, *, employee_id):
        open_records = [
            record
            for record in self.records
            if (
                record.employee_id == employee_id
                and record.check_out_time is None
                and not getattr(record, "is_missing_checkout", False)
            )
        ]
        return open_records[-1] if open_records else None

    def find_latest_for_employee_on_date(self, *, employee_id, on_date):
        records = [
            record
            for record in self.records
            if record.employee_id == employee_id and record.attendance_date == on_date
        ]
        return records[-1] if records else None

    def close_with_check_out(
        self,
        *,
        attendance_id,
        check_out_at,
        is_early_departure,
        early_departure_minutes,
        working_hours,
        commit=False,
    ):
        record = self.get_by_id(attendance_id)
        record.check_out_time = check_out_at
        record.is_early_departure = is_early_departure
        record.early_departure_minutes = early_departure_minutes
        record.working_hours = working_hours
        return record

    def list_records(self, *, filters, page, page_size):
        return self.records

    def count_records(self, *, filters):
        return len(self.records)


@pytest.fixture()
def attendance_context(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ALLOW_UNSCHEDULED_ATTENDANCE", True)
    employee_repo = FakeEmployeeRepo()
    schedule_repo = FakeScheduleRepo()
    attendance_repo = FakeAttendanceRepo(employee_repo)
    return {
        "employee_repo": employee_repo,
        "schedule_repo": schedule_repo,
        "attendance_repo": attendance_repo,
        "audit_repo": FakeAuditRepo(),
    }


def face_request():
    return AttendanceFaceRequest(
        filename="face.jpeg",
        content=b"fake-image",
        actor_user_id=1,
        ip_address="127.0.0.1",
    )


def check_in_use_case(context, clock, recognition=None, settings_provider=None):
    return CheckInByFace(
        attendance_repo=context["attendance_repo"],
        employee_repo=context["employee_repo"],
        schedule_repo=context["schedule_repo"],
        recognition_service=recognition or FakeRecognitionService(),
        audit_repo=context["audit_repo"],
        clock=clock,
        settings_provider=settings_provider,
    )


def check_out_use_case(context, clock, recognition=None):
    return CheckOutByFace(
        attendance_repo=context["attendance_repo"],
        employee_repo=context["employee_repo"],
        schedule_repo=context["schedule_repo"],
        recognition_service=recognition or FakeRecognitionService(),
        audit_repo=context["audit_repo"],
        clock=clock,
    )


def test_scheduled_check_in_on_time_is_present(attendance_context):
    attendance_context["schedule_repo"].add_assignment()
    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 0)),
    ).execute(face_request())

    assert result.record.status == AttendanceStatus.PRESENT
    assert result.record.is_late is False
    assert attendance_context["audit_repo"].entries[-1]["action"] == "ATTENDANCE_CHECK_IN"


def test_scheduled_check_in_within_grace_is_present(attendance_context):
    attendance_context["schedule_repo"].add_assignment(grace=10)
    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 10)),
    ).execute(face_request())

    assert result.record.status == AttendanceStatus.PRESENT
    assert result.record.is_late is False


def test_scheduled_check_in_after_grace_is_late(attendance_context):
    attendance_context["schedule_repo"].add_assignment(grace=10)
    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 11)),
    ).execute(face_request())

    assert result.record.status == AttendanceStatus.LATE
    assert result.record.is_late is True


def test_check_in_many_hours_before_shift_is_unscheduled(attendance_context):
    attendance_context["schedule_repo"].add_assignment(
        start=time(23, 26),
        end=time(23, 28),
    )

    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 0, 18)),
    ).execute(face_request())

    assert result.record.status == AttendanceStatus.UNSCHEDULED
    assert result.record.is_unscheduled is True
    assert result.record.employee_schedule_id is None
    assert result.record.schedule_template_id is None
    assert result.record.scheduled_start_datetime is None
    assert result.record.scheduled_end_datetime is None
    assert result.record.is_late is False
    assert result.record.late_minutes == 0

    checked_out = check_out_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 0, 19)),
    ).execute(face_request())
    assert checked_out.record.is_early_departure is False
    assert checked_out.record.early_departure_minutes == 0


def test_check_in_after_scheduled_end_is_unscheduled(attendance_context):
    attendance_context["schedule_repo"].add_assignment()

    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 16, 1)),
    ).execute(face_request())

    assert result.record.status == AttendanceStatus.UNSCHEDULED
    assert result.record.is_unscheduled is True
    assert result.record.scheduled_start_datetime is None
    assert result.record.scheduled_end_datetime is None


class FakeAttendancePolicyProvider:
    def __init__(self, early_window_minutes):
        self.early_window_minutes = early_window_minutes

    def get_boolean(self, key):
        assert key == "ALLOW_UNSCHEDULED_ATTENDANCE"
        return True

    def get_integer(self, key):
        assert key == "ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES"
        return self.early_window_minutes


@pytest.mark.parametrize(
    ("early_window_minutes", "expected_status"),
    [(60, AttendanceStatus.UNSCHEDULED), (120, AttendanceStatus.PRESENT)],
)
def test_runtime_early_check_in_window_controls_schedule_matching(
    attendance_context,
    early_window_minutes,
    expected_status,
):
    attendance_context["schedule_repo"].add_assignment()

    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 6, 30)),
        settings_provider=FakeAttendancePolicyProvider(early_window_minutes),
    ).execute(face_request())

    assert result.record.status == expected_status
    assert result.record.is_unscheduled is (expected_status == AttendanceStatus.UNSCHEDULED)


def test_duplicate_check_in_for_same_shift_is_rejected(attendance_context):
    attendance_context["schedule_repo"].add_assignment()
    use_case = check_in_use_case(attendance_context, FakeClock(datetime(2026, 6, 1, 8, 0)))
    use_case.execute(face_request())

    with pytest.raises(ConflictError, match="already checked in"):
        use_case.execute(face_request())


def test_unscheduled_attendance_created_when_enabled(attendance_context):
    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 7, 8, 0)),
    ).execute(face_request())

    assert result.record.status == AttendanceStatus.UNSCHEDULED
    assert result.record.is_unscheduled is True


def test_unscheduled_attendance_rejected_when_disabled(attendance_context, monkeypatch):
    monkeypatch.setattr(get_settings(), "ALLOW_UNSCHEDULED_ATTENDANCE", False)

    with pytest.raises(ConflictError, match="No effective schedule"):
        check_in_use_case(
            attendance_context,
            FakeClock(datetime(2026, 6, 7, 8, 0)),
        ).execute(face_request())
    assert attendance_context["attendance_repo"].records == []


def test_face_with_no_match_creates_no_attendance_record(attendance_context):
    recognition = FakeRecognitionService(
        FaceRecognitionResult(matched=False, failure_reason="no_match")
    )

    with pytest.raises(NotFoundError, match="No enrolled employee matched"):
        check_in_use_case(
            attendance_context,
            FakeClock(datetime(2026, 6, 1, 8, 0)),
            recognition=recognition,
        ).execute(face_request())
    assert attendance_context["attendance_repo"].records == []


def test_valid_check_out_closes_open_record(attendance_context):
    attendance_context["schedule_repo"].add_assignment()
    check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 0)),
    ).execute(face_request())

    result = check_out_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 16, 0)),
    ).execute(face_request())

    assert result.record.check_out_time == datetime(2026, 6, 1, 16, 0)
    assert result.record.is_early_departure is False
    assert attendance_context["audit_repo"].entries[-1]["action"] == "ATTENDANCE_CHECK_OUT"


def test_check_out_before_allowed_end_sets_early_departure(attendance_context):
    attendance_context["schedule_repo"].add_assignment(tolerance=5)
    check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 0)),
    ).execute(face_request())

    result = check_out_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 15, 30)),
    ).execute(face_request())

    assert result.record.is_early_departure is True


def test_late_and_early_departure_are_both_preserved(attendance_context):
    attendance_context["schedule_repo"].add_assignment(grace=10, tolerance=5)
    check_in = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 30)),
    ).execute(face_request())

    check_out = check_out_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 15, 30)),
    ).execute(face_request())

    assert check_in.record.is_late is True
    assert check_out.record.is_late is True
    assert check_out.record.is_early_departure is True


def test_check_out_without_open_check_in_is_rejected(attendance_context):
    with pytest.raises(ConflictError, match="No open attendance record"):
        check_out_use_case(
            attendance_context,
            FakeClock(datetime(2026, 6, 1, 16, 0)),
        ).execute(face_request())


def test_duplicate_check_out_is_rejected(attendance_context):
    attendance_context["schedule_repo"].add_assignment()
    check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 0)),
    ).execute(face_request())
    check_out_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 16, 0)),
    ).execute(face_request())

    with pytest.raises(ConflictError, match="No open attendance record"):
        check_out_use_case(
            attendance_context,
            FakeClock(datetime(2026, 6, 1, 16, 1)),
        ).execute(face_request())


def test_overnight_check_in_before_midnight_uses_shift_start_date(attendance_context):
    attendance_context["schedule_repo"].add_assignment(
        start=time(20, 0),
        end=time(4, 0),
        is_overnight=True,
    )

    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 20, 3)),
    ).execute(face_request())

    assert result.record.attendance_date == date(2026, 6, 1)
    assert result.record.scheduled_end_datetime == datetime(2026, 6, 2, 4, 0)


def test_overnight_check_out_after_midnight_closes_previous_shift(attendance_context):
    attendance_context["schedule_repo"].add_assignment(
        start=time(20, 0),
        end=time(4, 0),
        is_overnight=True,
    )
    check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 20, 3)),
    ).execute(face_request())

    result = check_out_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 2, 3, 30)),
    ).execute(face_request())

    assert result.record.attendance_date == date(2026, 6, 1)
    assert result.record.check_out_time == datetime(2026, 6, 2, 3, 30)
    assert result.record.is_early_departure is True


def test_post_midnight_check_in_resolves_previous_overnight_shift(attendance_context):
    attendance_context["schedule_repo"].add_assignment(
        start=time(20, 0),
        end=time(4, 0),
        is_overnight=True,
    )

    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 2, 0, 30)),
    ).execute(face_request())

    assert result.record.attendance_date == date(2026, 6, 1)
    assert result.record.status == AttendanceStatus.LATE


class FakeDetector:
    def __init__(self, face_count=1):
        self.face_count = face_count

    def detect_face(self, image_bytes, *, employee_id=None, filename=None):
        return FaceDetectionResult(face_count=self.face_count, face_crop="face")


class FakeEmbedder:
    model_name = "facenet-onnx-512d-haikalmumtaz-v1"

    def __init__(self, embedding):
        self.embedding = embedding

    def generate_embedding(self, face_image):
        return self.embedding


class FakeFaceEmbeddingRepo:
    def __init__(self, rows):
        self.rows = rows

    def get_active_compatible_embeddings_for_recognition(self, *, model_name):
        return [
            ActiveFaceEmbeddingForRecognition(
                employee_id=row["employee_id"],
                embedding_vector=row["embedding"],
                model_name=row["model_name"],
            )
            for row in self.rows
            if row["active"] and row["employee_active"] and row["model_name"] == model_name
        ]


def recognition_service(query_embedding, rows):
    return FaceNetRecognitionService(
        image_validator=ImageValidator(),
        detector=FakeDetector(),
        embedder=FakeEmbedder(query_embedding),
        face_embedding_repo=FakeFaceEmbeddingRepo(rows),
    )


def test_recognizes_active_employee_with_compatible_facenet_embedding():
    service = recognition_service(
        [1.0, 0.0],
        [
            {
                "employee_id": 1,
                "embedding": [1.0, 0.0],
                "model_name": "facenet-onnx-512d-haikalmumtaz-v1",
                "active": True,
                "employee_active": True,
            }
        ],
    )

    result = service.recognize(image_bytes=b"image", original_filename="face.jpg")

    assert result.matched is True
    assert result.employee_id == 1


def test_recognition_ignores_inactive_legacy_and_inactive_employee_embeddings():
    service = recognition_service(
        [1.0, 0.0],
        [
            {
                "employee_id": 1,
                "embedding": [1.0, 0.0],
                "model_name": "facenet-onnx-512d-haikalmumtaz-v1",
                "active": False,
                "employee_active": True,
            },
            {
                "employee_id": 2,
                "embedding": [1.0, 0.0],
                "model_name": "development-face-embedder-v1",
                "active": True,
                "employee_active": True,
            },
            {
                "employee_id": 3,
                "embedding": [1.0, 0.0],
                "model_name": "facenet-onnx-512d-haikalmumtaz-v1",
                "active": True,
                "employee_active": False,
            },
        ],
    )

    result = service.recognize(image_bytes=b"image", original_filename="face.jpg")

    assert result.matched is False
    assert result.failure_reason == "no_match"


def test_recognition_rejects_unknown_face_below_threshold():
    service = recognition_service(
        [1.0, 0.0],
        [
            {
                "employee_id": 1,
                "embedding": [0.0, 1.0],
                "model_name": "facenet-onnx-512d-haikalmumtaz-v1",
                "active": True,
                "employee_active": True,
            }
        ],
    )

    result = service.recognize(image_bytes=b"image", original_filename="face.jpg")

    assert result.matched is False
    assert result.failure_reason == "no_match"


def test_recognition_rejects_ambiguous_match_between_two_employees():
    service = recognition_service(
        [1.0, 0.0],
        [
            {
                "employee_id": 1,
                "embedding": [1.0, 0.0],
                "model_name": "facenet-onnx-512d-haikalmumtaz-v1",
                "active": True,
                "employee_active": True,
            },
            {
                "employee_id": 2,
                "embedding": [0.999, 0.045],
                "model_name": "facenet-onnx-512d-haikalmumtaz-v1",
                "active": True,
                "employee_active": True,
            },
        ],
    )

    result = service.recognize(image_bytes=b"image", original_filename="face.jpg")

    assert result.matched is False
    assert result.failure_reason == "ambiguous"


def test_public_event_response_does_not_expose_similarity_scores(attendance_context):
    attendance_context["schedule_repo"].add_assignment()
    result = check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 0)),
    ).execute(face_request())

    payload = _event_response(result).model_dump()

    assert "similarity_score" not in payload
    assert "second_best_score" not in payload


def test_non_admin_cannot_call_check_in_endpoint_without_token():
    response = TestClient(create_app()).post(
        "/attendance/check-in",
        files={"file": ("face.jpg", b"fake", "image/jpeg")},
    )

    assert response.status_code in {401, 403}


def test_audit_logs_do_not_contain_embeddings_or_image_bytes(attendance_context):
    attendance_context["schedule_repo"].add_assignment()
    check_in_use_case(
        attendance_context,
        FakeClock(datetime(2026, 6, 1, 8, 0)),
    ).execute(face_request())

    serialized = str(attendance_context["audit_repo"].entries[-1])

    assert "embedding" not in serialized.lower()
    assert "fake-image" not in serialized
