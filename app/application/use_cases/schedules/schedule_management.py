"""Schedule template and employee assignment use cases."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Optional

from app.application.dto.schedule_dto import (
    EffectiveScheduleRequest,
    EffectiveScheduleResult,
    EmployeeScheduleActionRequest,
    EmployeeScheduleListRequest,
    EmployeeScheduleListResult,
    EmployeeScheduleMutationRequest,
    ScheduleTemplateActionRequest,
    ScheduleTemplateListRequest,
    ScheduleTemplateListResult,
    ScheduleTemplateMutationRequest,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.config import get_settings
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.repositories.schedule_template_repository import ScheduleTemplateRepositoryInterface


def _serialize_template(template) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "start_time": template.start_time.isoformat(),
        "end_time": template.end_time.isoformat(),
        "is_overnight": template.is_overnight,
        "check_in_grace_minutes": template.check_in_grace_minutes,
        "early_departure_tolerance_minutes": template.early_departure_tolerance_minutes,
        "is_active": template.is_active,
    }


def _working_days_from_assignment(assignment) -> list[int]:
    value = assignment.working_days or ""
    return [int(day) for day in value.split(",") if day != ""]


def _serialize_assignment(assignment) -> dict:
    template = assignment.schedule_template
    return {
        "id": assignment.id,
        "employee_id": assignment.employee_id,
        "schedule_template_id": assignment.schedule_template_id,
        "schedule_template_name": template.name if template else None,
        "effective_from": assignment.effective_start_date.isoformat(),
        "effective_to": assignment.effective_end_date.isoformat()
        if assignment.effective_end_date
        else None,
        "working_days": _working_days_from_assignment(assignment),
        "is_active": assignment.is_active,
    }


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise BadRequestError("Page must be greater than or equal to 1")
    if page_size < 1 or page_size > 100:
        raise BadRequestError("Page size must be between 1 and 100")


def _normalize_template_request(request: ScheduleTemplateMutationRequest) -> dict:
    name = request.name.strip()
    if len(name) < 2 or len(name) > 100:
        raise BadRequestError("Schedule template name must be between 2 and 100 characters")
    if request.start_time == request.end_time:
        raise BadRequestError("Start time and end time must not be equal")
    # Validates daytime and overnight shift time rules.
    if request.is_overnight:
        if request.end_time > request.start_time:
            raise BadRequestError("Overnight schedules must end on the next calendar date")
    elif request.end_time <= request.start_time:
        raise BadRequestError("End time must be later than start time for non-overnight schedules")
    if request.check_in_grace_minutes < 0 or request.check_in_grace_minutes > 120:
        raise BadRequestError("Check-in grace minutes must be between 0 and 120")
    if (
        request.early_departure_tolerance_minutes < 0
        or request.early_departure_tolerance_minutes > 120
    ):
        raise BadRequestError("Early departure tolerance minutes must be between 0 and 120")

    description = request.description.strip() if request.description else None
    if description == "":
        description = None
    return {
        "name": name,
        "description": description,
        "start_time": request.start_time,
        "end_time": request.end_time,
        "is_overnight": request.is_overnight,
        "check_in_grace_minutes": request.check_in_grace_minutes,
        "early_departure_tolerance_minutes": request.early_departure_tolerance_minutes,
    }


def _normalize_assignment_values(
    *,
    effective_from: date,
    effective_to: Optional[date],
    working_days: list[int],
) -> dict:
    # Validates schedule assignment dates and working days.
    if effective_to is not None and effective_to < effective_from:
        raise BadRequestError("Effective end date must be greater than or equal to effective start date")
    if not working_days:
        raise BadRequestError("At least one working day is required")
    if len(set(working_days)) != len(working_days):
        raise BadRequestError("Working days must contain unique weekday values")
    if any(day < 0 or day > 6 for day in working_days):
        raise BadRequestError("Working days must be integers from 0 to 6")
    # Stores working days as Python weekday numbers.
    return {
        "effective_from": effective_from,
        "effective_to": effective_to,
        "working_days": sorted(working_days),
    }


class CreateScheduleTemplate:
    def __init__(
        self,
        template_repo: ScheduleTemplateRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._template_repo = template_repo
        self._audit_repo = audit_repo

    def execute(self, request: ScheduleTemplateMutationRequest):
        values = _normalize_template_request(request)
        # Checks for an existing schedule template with the same name.
        if self._template_repo.get_by_name(values["name"]) is not None:
            raise ConflictError("Schedule template name already exists")
        template = self._template_repo.create(**values, commit=False)
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="CREATE_SCHEDULE_TEMPLATE",
            entity_type="ScheduleTemplate",
            entity_id=template.id,
            new_values=json.dumps(_serialize_template(template)),
            ip_address=request.ip_address,
        )
        return template


class ListScheduleTemplates:
    def __init__(self, template_repo: ScheduleTemplateRepositoryInterface) -> None:
        self._template_repo = template_repo

    def execute(self, request: ScheduleTemplateListRequest) -> ScheduleTemplateListResult:
        _validate_pagination(request.page, request.page_size)
        return ScheduleTemplateListResult(
            items=self._template_repo.list(
                search=request.search,
                is_active=request.is_active,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._template_repo.count(search=request.search, is_active=request.is_active),
        )


class GetScheduleTemplate:
    def __init__(self, template_repo: ScheduleTemplateRepositoryInterface) -> None:
        self._template_repo = template_repo

    def execute(self, template_id: int):
        template = self._template_repo.get_by_id(template_id)
        if template is None:
            raise NotFoundError("Schedule template not found")
        return template


class UpdateScheduleTemplate:
    def __init__(
        self,
        template_repo: ScheduleTemplateRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._template_repo = template_repo
        self._audit_repo = audit_repo

    def execute(self, template_id: int, request: ScheduleTemplateMutationRequest):
        template = self._template_repo.get_by_id(template_id)
        if template is None:
            raise NotFoundError("Schedule template not found")
        # Checks whether current or future assignments use this template.
        if self._template_repo.has_current_or_future_active_assignments(
            template_id,
            reference_date=date.today(),
        ):
            raise ConflictError(
                "Schedule template is used by active current or future assignments. "
                "End or reassign those assignments first."
            )
        values = _normalize_template_request(request)
        duplicate = self._template_repo.get_by_name(values["name"])
        if duplicate is not None and duplicate.id != template_id:
            raise ConflictError("Schedule template name already exists")
        old_values = _serialize_template(template)
        updated = self._template_repo.update(template_id, **values, commit=False)
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="UPDATE_SCHEDULE_TEMPLATE",
            entity_type="ScheduleTemplate",
            entity_id=template_id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_serialize_template(updated)),
            ip_address=request.ip_address,
        )
        return updated


class ActivateScheduleTemplate:
    def __init__(
        self,
        template_repo: ScheduleTemplateRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._template_repo = template_repo
        self._audit_repo = audit_repo

    def execute(self, request: ScheduleTemplateActionRequest):
        template = self._template_repo.get_by_id(request.template_id)
        if template is None:
            raise NotFoundError("Schedule template not found")
        old_values = _serialize_template(template)
        updated = self._template_repo.activate(request.template_id, commit=False)
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ACTIVATE_SCHEDULE_TEMPLATE",
            entity_type="ScheduleTemplate",
            entity_id=request.template_id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_serialize_template(updated)),
            ip_address=request.ip_address,
        )
        return updated


class DeactivateScheduleTemplate:
    def __init__(
        self,
        template_repo: ScheduleTemplateRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._template_repo = template_repo
        self._audit_repo = audit_repo

    def execute(self, request: ScheduleTemplateActionRequest):
        template = self._template_repo.get_by_id(request.template_id)
        if template is None:
            raise NotFoundError("Schedule template not found")
        # Checks whether the template is used by current or future assignments.
        if self._template_repo.has_current_or_future_active_assignments(
            request.template_id,
            reference_date=date.today(),
        ):
            raise ConflictError(
                "Schedule template is used by active current or future assignments. "
                "End or reassign those assignments first."
            )
        old_values = _serialize_template(template)
        updated = self._template_repo.deactivate(request.template_id, commit=False)
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="DEACTIVATE_SCHEDULE_TEMPLATE",
            entity_type="ScheduleTemplate",
            entity_id=request.template_id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_serialize_template(updated)),
            ip_address=request.ip_address,
        )
        return updated


class AssignEmployeeSchedule:
    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        template_repo: ScheduleTemplateRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._template_repo = template_repo
        self._schedule_repo = schedule_repo
        self._audit_repo = audit_repo

    def execute(self, request: EmployeeScheduleMutationRequest):
        employee, template = self._validate_employee_and_template(
            request.employee_id,
            request.schedule_template_id,
        )
        values = _normalize_assignment_values(
            effective_from=request.effective_from,
            effective_to=request.effective_to,
            working_days=request.working_days,
        )
        # Checks for overlapping active schedule assignments.
        if self._schedule_repo.has_overlap(
            employee_id=request.employee_id,
            effective_from=values["effective_from"],
            effective_to=values["effective_to"],
        ):
            raise ConflictError("Employee already has an overlapping active schedule assignment.")
        assignment = self._schedule_repo.create(
            employee_id=request.employee_id,
            schedule_template_id=request.schedule_template_id,
            **values,
            commit=False,
        )
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ASSIGN_EMPLOYEE_SCHEDULE",
            entity_type="EmployeeSchedule",
            entity_id=assignment.id,
            new_values=json.dumps(
                {
                    **_serialize_assignment(assignment),
                    "employee_name": employee.full_name,
                    "template_name": template.name,
                }
            ),
            ip_address=request.ip_address,
        )
        return assignment

    def _validate_employee_and_template(self, employee_id: int, template_id: int):
        # Loads and validates the employee and schedule template.
        employee = self._employee_repo.get_by_id(employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        if not employee.is_active:
            raise BadRequestError("Employee is inactive")
        template = self._template_repo.get_by_id(template_id)
        if template is None:
            raise NotFoundError("Schedule template not found")
        if not template.is_active:
            raise BadRequestError("Schedule template is inactive")
        return employee, template


class ListEmployeeSchedules:
    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._schedule_repo = schedule_repo

    def execute(self, request: EmployeeScheduleListRequest) -> EmployeeScheduleListResult:
        _validate_pagination(request.page, request.page_size)
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        return EmployeeScheduleListResult(
            employee_id=request.employee_id,
            items=self._schedule_repo.list_by_employee_id(
                request.employee_id,
                is_active=request.is_active,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._schedule_repo.count_by_employee_id(
                request.employee_id,
                is_active=request.is_active,
            ),
        )


class GetEmployeeSchedule:
    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._schedule_repo = schedule_repo

    def execute(self, request: EmployeeScheduleActionRequest):
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        assignment = self._schedule_repo.get_by_employee_and_id(
            request.employee_id,
            request.assignment_id,
        )
        if assignment is None:
            raise NotFoundError("Schedule assignment not found")
        return assignment


class UpdateEmployeeSchedule:
    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        template_repo: ScheduleTemplateRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._template_repo = template_repo
        self._schedule_repo = schedule_repo
        self._audit_repo = audit_repo

    def execute(self, assignment_id: int, request: EmployeeScheduleMutationRequest):
        assignment = self._schedule_repo.get_by_employee_and_id(request.employee_id, assignment_id)
        if assignment is None:
            raise NotFoundError("Schedule assignment not found")
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        if not employee.is_active:
            raise BadRequestError("Employee is inactive")
        template = self._template_repo.get_by_id(request.schedule_template_id)
        if template is None:
            raise NotFoundError("Schedule template not found")
        if not template.is_active:
            raise BadRequestError("Schedule template is inactive")

        values = _normalize_assignment_values(
            effective_from=request.effective_from,
            effective_to=request.effective_to,
            working_days=request.working_days,
        )
        # Checks updated assignment dates against other active assignments.
        if assignment.is_active and self._schedule_repo.has_overlap(
            employee_id=request.employee_id,
            exclude_assignment_id=assignment_id,
            effective_from=values["effective_from"],
            effective_to=values["effective_to"],
        ):
            raise ConflictError("Employee already has an overlapping active schedule assignment.")
        old_values = _serialize_assignment(assignment)
        updated = self._schedule_repo.update(
            assignment_id,
            schedule_template_id=request.schedule_template_id,
            **values,
            commit=False,
        )
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="UPDATE_EMPLOYEE_SCHEDULE",
            entity_type="EmployeeSchedule",
            entity_id=assignment_id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_serialize_assignment(updated)),
            ip_address=request.ip_address,
        )
        return updated


class ActivateEmployeeSchedule:
    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        template_repo: ScheduleTemplateRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._template_repo = template_repo
        self._schedule_repo = schedule_repo
        self._audit_repo = audit_repo

    def execute(self, request: EmployeeScheduleActionRequest):
        assignment = self._schedule_repo.get_by_employee_and_id(
            request.employee_id,
            request.assignment_id,
        )
        if assignment is None:
            raise NotFoundError("Schedule assignment not found")
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        if not employee.is_active:
            raise BadRequestError("Employee is inactive")
        template = self._template_repo.get_by_id(assignment.schedule_template_id)
        if template is None:
            raise NotFoundError("Schedule template not found")
        if not template.is_active:
            raise BadRequestError("Schedule template is inactive")
        # Checks the reactivated assignment for date overlap.
        if self._schedule_repo.has_overlap(
            employee_id=request.employee_id,
            effective_from=assignment.effective_start_date,
            effective_to=assignment.effective_end_date,
            exclude_assignment_id=request.assignment_id,
        ):
            raise ConflictError("Employee already has an overlapping active schedule assignment.")
        old_values = _serialize_assignment(assignment)
        updated = self._schedule_repo.activate(request.assignment_id, commit=False)
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ACTIVATE_EMPLOYEE_SCHEDULE",
            entity_type="EmployeeSchedule",
            entity_id=request.assignment_id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_serialize_assignment(updated)),
            ip_address=request.ip_address,
        )
        return updated


class DeactivateEmployeeSchedule:
    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._schedule_repo = schedule_repo
        self._audit_repo = audit_repo

    def execute(self, request: EmployeeScheduleActionRequest):
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        assignment = self._schedule_repo.get_by_employee_and_id(
            request.employee_id,
            request.assignment_id,
        )
        if assignment is None:
            raise NotFoundError("Schedule assignment not found")
        old_values = _serialize_assignment(assignment)
        updated = self._schedule_repo.deactivate(request.assignment_id, commit=False)
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="DEACTIVATE_EMPLOYEE_SCHEDULE",
            entity_type="EmployeeSchedule",
            entity_id=request.assignment_id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_serialize_assignment(updated)),
            ip_address=request.ip_address,
        )
        return updated


class GetEffectiveEmployeeSchedule:
    def __init__(
        self,
        employee_repo: EmployeeRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._schedule_repo = schedule_repo

    def execute(self, request: EffectiveScheduleRequest) -> EffectiveScheduleResult:
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        assignment = self._schedule_repo.get_effective_schedule(
            employee_id=request.employee_id,
            on_date=request.on_date,
        )
        settings = get_settings()
        # Resolves whether the selected date has an effective working schedule.
        if assignment is None or request.on_date.weekday() not in _working_days_from_assignment(assignment):
            return EffectiveScheduleResult(
                employee_id=request.employee_id,
                employee_name=employee.full_name,
                on_date=request.on_date,
                has_schedule=False,
                working_day=False,
                message="No effective work schedule found for the selected date",
            )

        template = assignment.schedule_template
        start_datetime = datetime.combine(request.on_date, template.start_time)
        # Builds the scheduled end date for daytime or overnight shifts.
        end_date = request.on_date + timedelta(days=1) if template.is_overnight else request.on_date
        end_datetime = datetime.combine(end_date, template.end_time)
        return EffectiveScheduleResult(
            employee_id=request.employee_id,
            employee_name=employee.full_name,
            on_date=request.on_date,
            has_schedule=True,
            working_day=True,
            assignment_id=assignment.id,
            schedule_template_id=template.id,
            schedule_template_name=template.name,
            scheduled_start_datetime=start_datetime,
            scheduled_end_datetime=end_datetime,
            is_overnight=template.is_overnight,
            check_in_grace_minutes=template.check_in_grace_minutes,
            early_departure_tolerance_minutes=template.early_departure_tolerance_minutes,
            timezone=settings.APP_TIMEZONE,
        )
