from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.dto.attendance_dto import AttendanceFaceRequest
from app.application.dto.attendance_processing_dto import ProcessDailyAttendanceRequest
from app.application.dto.overtime_request_dto import CreateOvertimeRequestDTO
from app.application.dto.report_dto import ExportAttendanceReportRequest
from app.application.dto.system_setting_dto import UpdateSystemSettingDTO
from app.application.use_cases.attendance.attendance_management import CheckInByFace
from app.application.use_cases.attendance.process_daily_attendance import ProcessDailyAttendance
from app.application.use_cases.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.application.use_cases.overtime.overtime_management import CreateOvertimeRequest
from app.application.use_cases.reports.report_management import ExportAttendanceReport
from app.application.use_cases.settings.system_setting_management import UpdateSystemSetting
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.export_format import ExportFormat
from app.domain.repositories.report_repository import AttendanceReportFilters
from app.domain.services.face_recognition_service import FaceRecognitionResult
from app.infrastructure.exports.attendance_export_service import AttendanceExportService
from app.infrastructure.settings.runtime_system_settings_provider import RuntimeSystemSettingsProvider
from app.main import create_app
from app.presentation.api.system_settings import _setting_response


class FakeClock:
    def __init__(self, current=None):
        self.current = current or datetime(2026, 5, 28, 0, 10)

    def now_utc(self):
        return self.current.replace(tzinfo=UTC)

    def now_in_timezone(self, timezone_name):
        return self.current.replace(tzinfo=UTC)


class FakeSettingRepo:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def get_override_by_key(self, key):
        return self.rows.get(key.strip().upper())

    def list_overrides(self):
        return list(self.rows.values())

    def upsert_override(self, *, key, value, description, actor_user_id, updated_at, commit=True):
        key = key.strip().upper()
        row = self.rows.get(key)
        if row is None:
            row = SimpleNamespace(id=self.next_id, key=key)
            self.next_id += 1
            self.rows[key] = row
        row.value = value
        row.description = description
        row.updated_by = actor_user_id
        row.updated_at = updated_at
        return row


class FakeAuditRepo:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


def provider(repo=None, clock=None):
    return RuntimeSystemSettingsProvider(
        settings_repo=repo or FakeSettingRepo(),
        clock=clock or FakeClock(),
    )


def test_admin_can_list_safe_effective_settings():
    items = provider().list_effective_settings()
    keys = {item.key for item in items}
    assert "ORGANIZATION_NAME" in keys
    assert "ALLOW_UNSCHEDULED_ATTENDANCE" in keys
    assert "DATABASE_URL" not in keys
    assert "SECRET_KEY" not in keys
    assert "FACE_EMBEDDER_BACKEND" not in keys


def test_admin_can_get_supported_setting_by_key():
    setting = provider().get_effective_setting("allow_unscheduled_attendance")
    assert setting.key == "ALLOW_UNSCHEDULED_ATTENDANCE"
    assert setting.value is True
    assert setting.source.value in {"ENV_DEFAULT", "APPLICATION_DEFAULT"}


def test_unknown_setting_returns_not_found():
    with pytest.raises(NotFoundError, match="System setting not found"):
        provider().get_effective_setting("DATABASE_URL")


def test_employee_cannot_list_admin_settings_without_admin_token():
    response = TestClient(create_app()).get("/system-settings")
    assert response.status_code in {401, 403}


def test_read_only_setting_cannot_be_updated():
    with pytest.raises(ForbiddenError, match="read-only"):
        provider().update_setting(
            key="ORGANIZATION_TIMEZONE",
            raw_value="UTC",
            reason="Attempt protected update",
            actor_user_id=1,
        )


def test_update_organization_name_trims_and_uses_database_source():
    repo = FakeSettingRepo()
    updated = provider(repo).update_setting(
        key="ORGANIZATION_NAME",
        raw_value="  University Face Attendance System  ",
        reason="Set display name",
        actor_user_id=1,
    )
    assert updated.setting.value == "University Face Attendance System"
    assert updated.setting.source.value == "DATABASE"
    assert provider(repo).get_string("ORGANIZATION_NAME") == "University Face Attendance System"


def test_too_short_organization_name_is_rejected():
    with pytest.raises(BadRequestError, match="ORGANIZATION_NAME"):
        provider().update_setting(
            key="ORGANIZATION_NAME",
            raw_value="A",
            reason="Bad name",
            actor_user_id=1,
        )


def test_boolean_setting_accepts_boolean_and_rejects_string():
    repo = FakeSettingRepo()
    updated = provider(repo).update_setting(
        key="ALLOW_UNSCHEDULED_ATTENDANCE",
        raw_value=False,
        reason="Disable unscheduled check-ins",
        actor_user_id=1,
    )
    assert updated.setting.value is False
    with pytest.raises(BadRequestError, match="boolean"):
        provider(repo).update_setting(
            key="ALLOW_UNSCHEDULED_ATTENDANCE",
            raw_value="false",
            reason="Invalid boolean",
            actor_user_id=1,
        )


@pytest.mark.parametrize("value", [-1, 1441])
def test_processing_delay_range_validation(value):
    with pytest.raises(BadRequestError, match="ATTENDANCE_PROCESSING_DELAY_MINUTES"):
        provider().update_setting(
            key="ATTENDANCE_PROCESSING_DELAY_MINUTES",
            raw_value=value,
            reason="Invalid processing delay",
            actor_user_id=1,
        )


def test_missing_checkout_delay_defaults_to_four_hours_and_updates_future_reads():
    repo = FakeSettingRepo()
    settings_provider = provider(repo)

    setting = settings_provider.get_effective_setting("MISSING_CHECKOUT_DELAY_MINUTES")
    assert setting.value == 240
    assert setting.category == "ATTENDANCE"
    assert setting.editable_by_admin is True

    settings_provider.update_setting(
        key="MISSING_CHECKOUT_DELAY_MINUTES",
        raw_value=300,
        reason=None,
        actor_user_id=1,
    )
    assert settings_provider.get_integer("MISSING_CHECKOUT_DELAY_MINUTES") == 300


@pytest.mark.parametrize("value", [-1, 1441])
def test_missing_checkout_delay_range_validation(value):
    with pytest.raises(BadRequestError, match="MISSING_CHECKOUT_DELAY_MINUTES"):
        provider().update_setting(
            key="MISSING_CHECKOUT_DELAY_MINUTES",
            raw_value=value,
            reason=None,
            actor_user_id=1,
        )


def test_early_check_in_window_is_safe_and_updates_future_reads():
    repo = FakeSettingRepo()
    settings_provider = provider(repo)

    setting = settings_provider.get_effective_setting(
        "ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES"
    )
    assert setting.value == 60
    assert setting.category == "ATTENDANCE"
    assert setting.editable_by_admin is True

    settings_provider.update_setting(
        key="ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES",
        raw_value=90,
        reason=None,
        actor_user_id=1,
    )
    assert settings_provider.get_integer("ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES") == 90


@pytest.mark.parametrize("value", [-1, 721])
def test_early_check_in_window_range_validation(value):
    with pytest.raises(BadRequestError, match="ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES"):
        provider().update_setting(
            key="ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES",
            raw_value=value,
            reason=None,
            actor_user_id=1,
        )


@pytest.mark.parametrize("value", [0, 721])
def test_overtime_minimum_range_validation(value):
    with pytest.raises(BadRequestError, match="OVERTIME_MINIMUM_MINUTES"):
        provider().update_setting(
            key="OVERTIME_MINIMUM_MINUTES",
            raw_value=value,
            reason="Invalid overtime minimum",
            actor_user_id=1,
        )


def test_blank_update_reason_uses_automatic_reason_and_short_manual_reason_is_rejected():
    updated = provider().update_setting(
        key="OVERTIME_MINIMUM_MINUTES",
        raw_value=15,
        reason="",
        actor_user_id=1,
    )
    assert updated.reason == "Updated from System Settings page."

    with pytest.raises(BadRequestError, match="reason"):
        provider().update_setting(
            key="OVERTIME_MINIMUM_MINUTES",
            raw_value=15,
            reason="bad",
            actor_user_id=1,
        )


def test_justification_monthly_limit_is_safe_editable_setting():
    repo = FakeSettingRepo()
    settings_provider = provider(repo)
    setting = settings_provider.get_effective_setting("JUSTIFICATION_MONTHLY_LIMIT")
    assert setting.value == 3
    assert setting.category == "JUSTIFICATION"
    assert setting.editable_by_admin is True

    updated = settings_provider.update_setting(
        key="JUSTIFICATION_MONTHLY_LIMIT",
        raw_value=5,
        reason=None,
        actor_user_id=1,
    )
    assert updated.setting.value == 5
    assert updated.reason == "Updated from System Settings page."
    assert settings_provider.get_integer("JUSTIFICATION_MONTHLY_LIMIT") == 5


@pytest.mark.parametrize("value", [-1, 32])
def test_justification_monthly_limit_range_validation(value):
    with pytest.raises(BadRequestError, match="JUSTIFICATION_MONTHLY_LIMIT"):
        provider().update_setting(
            key="JUSTIFICATION_MONTHLY_LIMIT",
            raw_value=value,
            reason=None,
            actor_user_id=1,
        )


def test_database_override_precedence_and_immediate_future_reads():
    repo = FakeSettingRepo()
    settings_provider = provider(repo)
    assert settings_provider.get_integer("OVERTIME_MINIMUM_MINUTES") == 30
    settings_provider.update_setting(
        key="OVERTIME_MINIMUM_MINUTES",
        raw_value=15,
        reason="Lower future overtime minimum",
        actor_user_id=1,
    )
    assert settings_provider.get_integer("OVERTIME_MINIMUM_MINUTES") == 15
    assert settings_provider.get_effective_setting("OVERTIME_MINIMUM_MINUTES").source.value == "DATABASE"


def test_update_setting_writes_safe_audit_log():
    repo = FakeSettingRepo()
    audit = FakeAuditRepo()
    use_case = UpdateSystemSetting(settings_provider=provider(repo), audit_repo=audit)
    use_case.execute(
        UpdateSystemSettingDTO(
            key="ATTENDANCE_PROCESSING_DELAY_MINUTES",
            value=45,
            reason="Increase processing buffer",
            actor_user_id=1,
        )
    )
    serialized = str(audit.entries)
    assert "UPDATE_SYSTEM_SETTING" in serialized
    assert "ATTENDANCE_PROCESSING_DELAY_MINUTES" in serialized
    assert "Increase processing buffer" in serialized
    assert "SECRET_KEY" not in serialized
    assert "embedding" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_settings_api_response_updated_at_has_explicit_offset():
    repo = FakeSettingRepo()
    setting = provider(repo).update_setting(
        key="ORGANIZATION_NAME",
        raw_value="University Face Attendance System",
        reason="Set display name",
        actor_user_id=1,
    ).setting
    payload = _setting_response(setting).model_dump()
    assert payload["updated_at"] == "2026-05-28T00:10:00+02:00"


class FakeRecognitionService:
    def recognize(self, *, image_bytes, original_filename):
        return FaceRecognitionResult(
            matched=True,
            employee_id=1,
            matched_model_name="facenet-onnx-512d-haikalmumtaz-v1",
        )


class FakeEmployeeRepo:
    def __init__(self):
        self.employee = SimpleNamespace(
            id=1,
            user_id=10,
            full_name="Employee One",
            employee_number="EMP001",
            is_active=True,
        )

    def get_by_id(self, employee_id):
        return self.employee if employee_id == 1 else None

    def get_by_user_id(self, user_id):
        return self.employee if user_id == 10 else None


class FakeScheduleRepo:
    def __init__(self, assignment=None):
        self.assignment = assignment

    def get_effective_schedule(self, *, employee_id, on_date):
        return self.assignment

    def list_active_assignments_for_date(self, *, on_date):
        return [self.assignment] if self.assignment else []


class FakeAttendanceRepo:
    def __init__(self):
        self.records = []
        self.next_id = 1

    def find_existing_for_shift(self, **kwargs):
        return None

    def create_check_in(self, **kwargs):
        record = SimpleNamespace(
            id=self.next_id,
            employee=FakeEmployeeRepo().employee,
            attendance_date=kwargs["schedule_date"],
            check_in_time=kwargs["check_in_at"],
            check_out_time=None,
            scheduled_start_datetime=kwargs["scheduled_start_datetime"],
            scheduled_end_datetime=kwargs["scheduled_end_datetime"],
            status=kwargs["status"],
            is_late=kwargs["is_late"],
            is_early_departure=False,
            is_unscheduled=kwargs["is_unscheduled"],
            is_missing_checkout=False,
            late_minutes=kwargs["late_minutes"],
            early_departure_minutes=0,
            recognition_model_name=kwargs["recognition_model_name"],
            detector_backend=kwargs["detector_backend"],
            employee_id=kwargs["employee_id"],
        )
        self.next_id += 1
        self.records.append(record)
        return record

    def create_absent_record(self, **kwargs):
        record = SimpleNamespace(
            id=self.next_id,
            employee_id=kwargs["employee_id"],
            attendance_date=kwargs["schedule_date"],
            status=AttendanceStatus.ABSENT,
            scheduled_end_datetime=kwargs["scheduled_end_datetime"],
        )
        self.next_id += 1
        self.records.append(record)
        return record


class SimplePolicyProvider:
    def __init__(self, values):
        self.values = values

    def get_boolean(self, key):
        return bool(self.values[key])

    def get_integer(self, key):
        return int(self.values[key])

    def get_string(self, key):
        return str(self.values[key])


def check_in_use_case(attendance_repo, settings_provider):
    return CheckInByFace(
        attendance_repo=attendance_repo,
        employee_repo=FakeEmployeeRepo(),
        schedule_repo=FakeScheduleRepo(),
        recognition_service=FakeRecognitionService(),
        audit_repo=FakeAuditRepo(),
        clock=FakeClock(datetime(2026, 6, 7, 8, 0)),
        settings_provider=settings_provider,
    )


def test_runtime_allow_unscheduled_false_rejects_future_unscheduled_check_in():
    attendance_repo = FakeAttendanceRepo()
    with pytest.raises(ConflictError, match="No effective schedule"):
        check_in_use_case(
            attendance_repo,
            SimplePolicyProvider({"ALLOW_UNSCHEDULED_ATTENDANCE": False}),
        ).execute(
            AttendanceFaceRequest(
                filename="face.jpg",
                content=b"fake-image",
                actor_user_id=1,
            )
        )
    assert attendance_repo.records == []


def test_runtime_allow_unscheduled_true_allows_future_unscheduled_check_in():
    attendance_repo = FakeAttendanceRepo()
    result = check_in_use_case(
        attendance_repo,
        SimplePolicyProvider({"ALLOW_UNSCHEDULED_ATTENDANCE": True}),
    ).execute(
        AttendanceFaceRequest(
            filename="face.jpg",
            content=b"fake-image",
            actor_user_id=1,
        )
    )
    assert result.record.status == AttendanceStatus.UNSCHEDULED
    assert result.record.is_unscheduled is True
    assert result.record.is_late is False
    assert result.record.scheduled_start_datetime is None
    assert result.record.scheduled_end_datetime is None
    assert result.record.late_minutes == 0
    assert len(attendance_repo.records) == 1


def processing_assignment():
    template = SimpleNamespace(
        id=1,
        name="Morning Shift",
        start_time=time(8, 0),
        end_time=time(16, 0),
        is_overnight=False,
    )
    return SimpleNamespace(
        id=1,
        employee_id=1,
        schedule_template_id=1,
        schedule_template=template,
        working_days="0",
    )


def process_daily_use_case(attendance_repo, delay):
    return ProcessDailyAttendance(
        attendance_repo=attendance_repo,
        schedule_repo=FakeScheduleRepo(processing_assignment()),
        audit_repo=FakeAuditRepo(),
        clock=FakeClock(datetime(2026, 6, 1, 16, 0)),
        settings_provider=SimplePolicyProvider(
            {
                "ATTENDANCE_PROCESSING_DELAY_MINUTES": delay,
                "MISSING_CHECKOUT_DELAY_MINUTES": 240,
            }
        ),
    )


def test_runtime_processing_delay_controls_future_daily_processing():
    attendance_repo = FakeAttendanceRepo()
    request = ProcessDailyAttendanceRequest(on_date=date(2026, 6, 1), actor_user_id=1)
    with pytest.raises(BadRequestError, match="eligible"):
        process_daily_use_case(attendance_repo, 30).execute(request)
    assert attendance_repo.records == []

    result = process_daily_use_case(attendance_repo, 0).execute(request)
    assert result.absent_records_created == 1
    assert attendance_repo.records[0].status == AttendanceStatus.ABSENT


class FakeOvertimeRepo:
    def __init__(self):
        self.items = []
        self.next_id = 1

    def has_pending_for_attendance(self, *, attendance_record_id):
        return False

    def has_approved_for_attendance(self, *, attendance_record_id):
        return False

    def create(self, **kwargs):
        item = SimpleNamespace(
            id=self.next_id,
            employee_id=kwargs["employee_id"],
            attendance_record_id=kwargs["attendance_record_id"],
            overtime_minutes=kwargs["requested_minutes"],
            eligible_minutes_at_submission=kwargs["eligible_minutes_at_submission"],
            approved_minutes=None,
            status="PENDING",
        )
        self.next_id += 1
        self.items.append(item)
        return item


class FakeAttendanceRepoForOvertime:
    def __init__(self, attendance_record):
        self.attendance_record = attendance_record

    def get_by_id(self, attendance_id):
        return self.attendance_record


def overtime_record():
    return SimpleNamespace(
        id=1,
        employee_id=1,
        scheduled_end_datetime=datetime(2026, 6, 1, 16, 0),
        check_out_time=datetime(2026, 6, 1, 16, 20),
        status=AttendanceStatus.PRESENT,
        is_unscheduled=False,
    )


def create_overtime_with_minimum(minimum):
    overtime_repo = FakeOvertimeRepo()
    use_case = CreateOvertimeRequest(
        employee_repo=FakeEmployeeRepo(),
        attendance_repo=FakeAttendanceRepoForOvertime(overtime_record()),
        overtime_repo=overtime_repo,
        audit_repo=FakeAuditRepo(),
        settings_provider=SimplePolicyProvider({"OVERTIME_MINIMUM_MINUTES": minimum}),
    )
    return use_case, overtime_repo


def test_runtime_overtime_minimum_controls_future_overtime_requests():
    with pytest.raises(BadRequestError, match="below"):
        create_overtime_with_minimum(30)[0].execute(
            CreateOvertimeRequestDTO(
                user_id=10,
                attendance_record_id=1,
                requested_minutes=20,
                reason="Worked beyond the scheduled end time.",
            )
        )

    use_case, overtime_repo = create_overtime_with_minimum(15)
    item = use_case.execute(
        CreateOvertimeRequestDTO(
            user_id=10,
            attendance_record_id=1,
            requested_minutes=20,
            reason="Worked beyond the scheduled end time.",
        )
    )
    assert item.eligible_minutes_at_submission == 20
    assert len(overtime_repo.items) == 1


class FakeReportRepo:
    def list_attendance_records_for_export(self, *, filters):
        return []


def export_use_case(max_days):
    return ExportAttendanceReport(
        report_repo=FakeReportRepo(),
        employee_repo=FakeEmployeeRepo(),
        department_repo=SimpleNamespace(get_by_id=lambda department_id: None),
        export_service=AttendanceExportService(),
        audit_repo=FakeAuditRepo(),
        settings_provider=SimplePolicyProvider({"REPORT_EXPORT_MAX_DATE_RANGE_DAYS": max_days}),
    )


def test_runtime_report_export_max_range_controls_future_exports():
    request = ExportAttendanceReportRequest(
        filters=AttendanceReportFilters(
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 2),
        ),
        export_format=ExportFormat.CSV,
        actor_user_id=1,
    )
    with pytest.raises(BadRequestError, match="cannot exceed"):
        export_use_case(1).execute(request)
    result = export_use_case(2).execute(request)
    assert result.row_count == 0
