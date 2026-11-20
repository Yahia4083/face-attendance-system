from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.dto.schedule_dto import (
    EffectiveScheduleRequest,
    EmployeeScheduleActionRequest,
    EmployeeScheduleMutationRequest,
    ScheduleTemplateActionRequest,
    ScheduleTemplateMutationRequest,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError
from app.application.use_cases.schedules.schedule_management import (
    AssignEmployeeSchedule,
    CreateScheduleTemplate,
    DeactivateScheduleTemplate,
    GetEffectiveEmployeeSchedule,
)
from app.main import create_app


class FakeAuditRepo:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


class FakeEmployeeRepo:
    def __init__(self):
        self.employees = {
            1: SimpleNamespace(id=1, full_name="Employee One", is_active=True),
            2: SimpleNamespace(id=2, full_name="Inactive Employee", is_active=False),
        }

    def get_by_id(self, employee_id):
        return self.employees.get(employee_id)

    def get_by_user_id(self, user_id):
        return None


class FakeTemplateRepo:
    def __init__(self):
        self.templates = {}
        self._next_id = 1
        self.blocked_template_ids = set()

    def create(self, commit=False, **values):
        now = datetime.now(UTC)
        template = SimpleNamespace(
            id=self._next_id,
            is_active=True,
            created_at=now,
            updated_at=now,
            **values,
        )
        self.templates[template.id] = template
        self._next_id += 1
        return template

    def get_by_id(self, template_id):
        return self.templates.get(template_id)

    def get_by_name(self, name):
        normalized = name.strip().lower()
        for template in self.templates.values():
            if template.name.lower() == normalized:
                return template
        return None

    def deactivate(self, template_id, commit=False):
        template = self.templates[template_id]
        template.is_active = False
        return template

    def has_current_or_future_active_assignments(self, template_id, reference_date):
        return template_id in self.blocked_template_ids


class FakeScheduleRepo:
    def __init__(self, template_repo):
        self.template_repo = template_repo
        self.assignments = {}
        self._next_id = 1

    def create(self, commit=False, **values):
        now = datetime.now(UTC)
        assignment = SimpleNamespace(
            id=self._next_id,
            employee_id=values["employee_id"],
            schedule_template_id=values["schedule_template_id"],
            schedule_template=self.template_repo.get_by_id(values["schedule_template_id"]),
            effective_start_date=values["effective_from"],
            effective_end_date=values["effective_to"],
            working_days=",".join(str(day) for day in values["working_days"]),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.assignments[assignment.id] = assignment
        self._next_id += 1
        return assignment

    def has_overlap(self, employee_id, effective_from, effective_to, exclude_assignment_id=None):
        requested_end = effective_to or date.max
        for assignment in self.assignments.values():
            if assignment.id == exclude_assignment_id:
                continue
            if assignment.employee_id != employee_id or not assignment.is_active:
                continue
            existing_end = assignment.effective_end_date or date.max
            if assignment.effective_start_date <= requested_end and effective_from <= existing_end:
                return True
        return False

    def get_effective_schedule(self, employee_id, on_date):
        for assignment in self.assignments.values():
            if assignment.employee_id != employee_id or not assignment.is_active:
                continue
            if assignment.effective_start_date <= on_date and (
                assignment.effective_end_date is None or assignment.effective_end_date >= on_date
            ):
                return assignment
        return None


@pytest.fixture()
def schedule_context():
    template_repo = FakeTemplateRepo()
    return {
        "employee_repo": FakeEmployeeRepo(),
        "template_repo": template_repo,
        "schedule_repo": FakeScheduleRepo(template_repo),
        "audit_repo": FakeAuditRepo(),
    }


def template_request(**overrides):
    values = {
        "name": "Morning Shift",
        "description": "Standard office schedule",
        "start_time": time(8, 0),
        "end_time": time(16, 0),
        "is_overnight": False,
        "check_in_grace_minutes": 10,
        "early_departure_tolerance_minutes": 5,
        "actor_user_id": 1,
    }
    values.update(overrides)
    return ScheduleTemplateMutationRequest(**values)


def create_template(context, **overrides):
    return CreateScheduleTemplate(
        context["template_repo"],
        context["audit_repo"],
    ).execute(template_request(**overrides))


def assign_request(template_id, **overrides):
    values = {
        "employee_id": 1,
        "schedule_template_id": template_id,
        "effective_from": date(2026, 6, 1),
        "effective_to": None,
        "working_days": [0, 1, 2, 3, 4],
        "actor_user_id": 1,
    }
    values.update(overrides)
    return EmployeeScheduleMutationRequest(**values)


def assign_schedule(context, template_id, **overrides):
    return AssignEmployeeSchedule(
        context["employee_repo"],
        context["template_repo"],
        context["schedule_repo"],
        context["audit_repo"],
    ).execute(assign_request(template_id, **overrides))


def test_create_valid_daytime_template_writes_audit(schedule_context):
    template = create_template(schedule_context)

    assert template.name == "Morning Shift"
    assert template.is_active is True
    assert schedule_context["audit_repo"].entries[0]["action"] == "CREATE_SCHEDULE_TEMPLATE"


def test_create_valid_overnight_template(schedule_context):
    template = create_template(
        schedule_context,
        name="Night Shift",
        start_time=time(20, 0),
        end_time=time(4, 0),
        is_overnight=True,
    )

    assert template.is_overnight is True


def test_reject_duplicate_template_name(schedule_context):
    create_template(schedule_context)

    with pytest.raises(ConflictError, match="Schedule template name already exists"):
        create_template(schedule_context, name=" morning shift ")


def test_reject_invalid_normal_time_range(schedule_context):
    with pytest.raises(BadRequestError, match="End time must be later"):
        create_template(
            schedule_context,
            name="Invalid Day Shift",
            start_time=time(16, 0),
            end_time=time(8, 0),
            is_overnight=False,
        )


def test_reject_inactive_template_assignment(schedule_context):
    template = create_template(schedule_context)
    template.is_active = False

    with pytest.raises(BadRequestError, match="Schedule template is inactive"):
        assign_schedule(schedule_context, template.id)


def test_reject_inactive_employee_assignment(schedule_context):
    template = create_template(schedule_context)

    with pytest.raises(BadRequestError, match="Employee is inactive"):
        assign_schedule(schedule_context, template.id, employee_id=2)


def test_assign_valid_employee_schedule_writes_audit(schedule_context):
    template = create_template(schedule_context)
    assignment = assign_schedule(schedule_context, template.id)

    assert assignment.employee_id == 1
    assert assignment.working_days == "0,1,2,3,4"
    assert schedule_context["audit_repo"].entries[-1]["action"] == "ASSIGN_EMPLOYEE_SCHEDULE"


def test_reject_overlapping_assignments(schedule_context):
    template = create_template(schedule_context)
    assign_schedule(schedule_context, template.id)

    with pytest.raises(ConflictError, match="overlapping active schedule"):
        assign_schedule(
            schedule_context,
            template.id,
            effective_from=date(2026, 7, 1),
        )


def test_resolve_effective_weekday_schedule(schedule_context):
    template = create_template(schedule_context)
    assignment = assign_schedule(schedule_context, template.id)

    result = GetEffectiveEmployeeSchedule(
        schedule_context["employee_repo"],
        schedule_context["schedule_repo"],
    ).execute(EffectiveScheduleRequest(employee_id=1, on_date=date(2026, 6, 1)))

    assert result.has_schedule is True
    assert result.assignment_id == assignment.id
    assert result.scheduled_start_datetime.isoformat() == "2026-06-01T08:00:00"
    assert result.scheduled_end_datetime.isoformat() == "2026-06-01T16:00:00"


def test_resolve_no_schedule_on_non_working_day(schedule_context):
    template = create_template(schedule_context)
    assign_schedule(schedule_context, template.id)

    result = GetEffectiveEmployeeSchedule(
        schedule_context["employee_repo"],
        schedule_context["schedule_repo"],
    ).execute(EffectiveScheduleRequest(employee_id=1, on_date=date(2026, 6, 6)))

    assert result.has_schedule is False
    assert result.working_day is False


def test_resolve_overnight_schedule_end_datetime_next_day(schedule_context):
    template = create_template(
        schedule_context,
        name="Night Shift",
        start_time=time(20, 0),
        end_time=time(4, 0),
        is_overnight=True,
    )
    assign_schedule(schedule_context, template.id, working_days=[0])

    result = GetEffectiveEmployeeSchedule(
        schedule_context["employee_repo"],
        schedule_context["schedule_repo"],
    ).execute(EffectiveScheduleRequest(employee_id=1, on_date=date(2026, 6, 1)))

    assert result.scheduled_start_datetime.isoformat() == "2026-06-01T20:00:00"
    assert result.scheduled_end_datetime.isoformat() == "2026-06-02T04:00:00"


def test_prevent_deactivating_template_used_by_active_assignment(schedule_context):
    template = create_template(schedule_context)
    schedule_context["template_repo"].blocked_template_ids.add(template.id)

    use_case = DeactivateScheduleTemplate(
        schedule_context["template_repo"],
        schedule_context["audit_repo"],
    )

    with pytest.raises(ConflictError, match="used by active current or future assignments"):
        use_case.execute(ScheduleTemplateActionRequest(template_id=template.id, actor_user_id=1))


def test_management_endpoint_requires_authentication():
    client = TestClient(create_app())

    response = client.get("/schedule-templates")

    assert response.status_code in {401, 403}
