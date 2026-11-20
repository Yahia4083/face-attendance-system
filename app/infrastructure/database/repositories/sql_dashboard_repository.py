"""SQLAlchemy dashboard repository implementation."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from app.domain.entities.dashboard import (
    DashboardActivity,
    DashboardDepartmentSnapshot,
    PendingDashboardRequest,
)
from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.repositories.dashboard_repository import DashboardRepositoryInterface
from app.infrastructure.database.models.attendance_record import AttendanceRecordModel
from app.infrastructure.database.models.audit_log import AuditLogModel
from app.infrastructure.database.models.department import DepartmentModel
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.justification_request import JustificationRequestModel
from app.infrastructure.database.models.overtime_request import OvertimeRequestModel


ALLOWED_DASHBOARD_AUDIT_ACTIONS = {
    "ATTENDANCE_CHECK_IN",
    "ATTENDANCE_CHECK_OUT",
    "CREATE_ABSENT_ATTENDANCE",
    "MARK_MISSING_CHECKOUT",
    "CREATE_JUSTIFICATION_REQUEST",
    "APPROVE_JUSTIFICATION_REQUEST",
    "REJECT_JUSTIFICATION_REQUEST",
    "CREATE_OVERTIME_REQUEST",
    "APPROVE_OVERTIME_REQUEST",
    "REJECT_OVERTIME_REQUEST",
}


def _value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _safe_json(text: Optional[str]) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_int(value: object) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _employee_name(employee: Optional[EmployeeModel]) -> Optional[str]:
    return employee.full_name if employee is not None else None


class SqlDashboardRepository(DashboardRepositoryInterface):
    """Read-only dashboard queries backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def count_active_employees(self) -> int:
        return self._db.query(EmployeeModel).filter(EmployeeModel.is_active.is_(True)).count()

    def count_active_departments(self) -> int:
        return self._db.query(DepartmentModel).filter(DepartmentModel.is_active.is_(True)).count()

    def list_active_department_snapshots(self) -> list[DashboardDepartmentSnapshot]:
        rows = (
            self._db.query(
                DepartmentModel.id,
                DepartmentModel.name,
                func.count(EmployeeModel.id).label("active_employee_count"),
            )
            .outerjoin(
                EmployeeModel,
                and_(
                    EmployeeModel.department_id == DepartmentModel.id,
                    EmployeeModel.is_active.is_(True),
                ),
            )
            .filter(DepartmentModel.is_active.is_(True))
            .group_by(DepartmentModel.id, DepartmentModel.name)
            .order_by(DepartmentModel.name.asc(), DepartmentModel.id.asc())
            .all()
        )
        return [
            DashboardDepartmentSnapshot(
                department_id=row.id,
                department_name=row.name,
                active_employee_count=int(row.active_employee_count or 0),
            )
            for row in rows
        ]

    def count_pending_justification_requests(self, *, employee_id: Optional[int] = None) -> int:
        query = self._pending_justification_query(employee_id=employee_id)
        return query.count()

    def count_pending_overtime_requests(self, *, employee_id: Optional[int] = None) -> int:
        query = self._pending_overtime_query(employee_id=employee_id)
        return query.count()

    def list_pending_justification_requests(
        self,
        *,
        employee_id: Optional[int] = None,
    ) -> list[PendingDashboardRequest]:
        items = (
            self._pending_justification_query(employee_id=employee_id)
            .options(
                joinedload(JustificationRequestModel.employee),
                joinedload(JustificationRequestModel.attendance_record),
            )
            .order_by(
                JustificationRequestModel.created_at.desc(),
                JustificationRequestModel.id.desc(),
            )
            .all()
        )
        return [self._pending_justification_to_dashboard(item) for item in items]

    def list_pending_overtime_requests(
        self,
        *,
        employee_id: Optional[int] = None,
    ) -> list[PendingDashboardRequest]:
        items = (
            self._pending_overtime_query(employee_id=employee_id)
            .options(
                joinedload(OvertimeRequestModel.employee),
                joinedload(OvertimeRequestModel.attendance_record),
            )
            .order_by(
                OvertimeRequestModel.created_at.desc(),
                OvertimeRequestModel.id.desc(),
            )
            .all()
        )
        return [self._pending_overtime_to_dashboard(item) for item in items]

    def list_recent_activities(self, *, limit: int) -> list[DashboardActivity]:
        audit_rows = (
            self._db.query(AuditLogModel)
            .filter(AuditLogModel.action.in_(ALLOWED_DASHBOARD_AUDIT_ACTIONS))
            .order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())
            .limit(limit)
            .all()
        )
        employee_ids: set[int] = set()
        attendance_ids: set[int] = set()
        payloads: dict[int, dict[str, Any]] = {}

        for row in audit_rows:
            payload = _safe_json(row.new_values) or _safe_json(row.old_values)
            payloads[row.id] = payload
            employee_id = _safe_int(payload.get("employee_id"))
            if employee_id is not None:
                employee_ids.add(employee_id)
            elif row.entity_type == "AttendanceRecord" and row.entity_id is not None:
                attendance_ids.add(row.entity_id)

        attendance_employee_map: dict[int, int] = {}
        if attendance_ids:
            attendance_rows = (
                self._db.query(AttendanceRecordModel.id, AttendanceRecordModel.employee_id)
                .filter(AttendanceRecordModel.id.in_(attendance_ids))
                .all()
            )
            for attendance_id, employee_id in attendance_rows:
                attendance_employee_map[int(attendance_id)] = int(employee_id)
                employee_ids.add(int(employee_id))

        employees = {}
        if employee_ids:
            employee_rows = self._db.query(EmployeeModel).filter(EmployeeModel.id.in_(employee_ids)).all()
            employees = {item.id: item for item in employee_rows}

        activities: list[DashboardActivity] = []
        for row in audit_rows:
            payload = payloads.get(row.id, {})
            employee_id = _safe_int(payload.get("employee_id"))
            if employee_id is None and row.entity_type == "AttendanceRecord" and row.entity_id is not None:
                employee_id = attendance_employee_map.get(row.entity_id)
            employee = employees.get(employee_id) if employee_id is not None else None
            activities.append(
                DashboardActivity(
                    activity_type=row.action,
                    employee_id=employee_id,
                    employee_name=_employee_name(employee),
                    description=self._activity_description(row.action, payload),
                    occurred_at=row.created_at,
                    related_entity_type=row.entity_type,
                    related_entity_id=row.entity_id,
                )
            )
        return activities

    def _pending_justification_query(self, *, employee_id: Optional[int]):
        query = self._db.query(JustificationRequestModel).filter(
            JustificationRequestModel.status == RequestStatus.PENDING
        )
        if employee_id is not None:
            query = query.filter(JustificationRequestModel.employee_id == employee_id)
        return query

    def _pending_overtime_query(self, *, employee_id: Optional[int]):
        query = self._db.query(OvertimeRequestModel).filter(
            OvertimeRequestModel.status == OvertimeStatus.PENDING
        )
        if employee_id is not None:
            query = query.filter(OvertimeRequestModel.employee_id == employee_id)
        return query

    @staticmethod
    def _pending_justification_to_dashboard(
        item: JustificationRequestModel,
    ) -> PendingDashboardRequest:
        employee = item.employee
        attendance = item.attendance_record
        return PendingDashboardRequest(
            request_category="JUSTIFICATION",
            request_id=item.id,
            employee_id=item.employee_id,
            employee_name=getattr(employee, "full_name", None),
            employee_number=getattr(employee, "employee_number", None),
            attendance_record_id=item.attendance_record_id,
            attendance_status=_value(attendance.status) if attendance is not None else None,
            request_type=item.request_type,
            reason=item.explanation,
            requested_minutes=None,
            eligible_minutes_at_submission=None,
            status=_value(item.status),
            created_at=item.created_at,
        )

    @staticmethod
    def _pending_overtime_to_dashboard(item: OvertimeRequestModel) -> PendingDashboardRequest:
        employee = item.employee
        attendance = item.attendance_record
        return PendingDashboardRequest(
            request_category="OVERTIME",
            request_id=item.id,
            employee_id=item.employee_id,
            employee_name=getattr(employee, "full_name", None),
            employee_number=getattr(employee, "employee_number", None),
            attendance_record_id=item.attendance_record_id,
            attendance_status=_value(attendance.status) if attendance is not None else None,
            request_type=None,
            reason=item.reason,
            requested_minutes=item.overtime_minutes,
            eligible_minutes_at_submission=item.eligible_minutes_at_submission,
            status=_value(item.status),
            created_at=item.created_at,
        )

    @staticmethod
    def _activity_description(action: str, payload: dict[str, Any]) -> str:
        if action == "ATTENDANCE_CHECK_IN":
            if payload.get("is_unscheduled") or payload.get("status") == "UNSCHEDULED":
                return "Employee recorded an unscheduled check-in."
            return "Employee checked in successfully."
        if action == "ATTENDANCE_CHECK_OUT":
            return "Employee checked out successfully."
        if action == "CREATE_ABSENT_ATTENDANCE":
            return "Absent attendance record was generated by daily processing."
        if action == "MARK_MISSING_CHECKOUT":
            return "Attendance record was marked as missing checkout."
        if action == "CREATE_JUSTIFICATION_REQUEST":
            return "Employee submitted a justification request."
        if action == "APPROVE_JUSTIFICATION_REQUEST":
            return "Justification request was approved."
        if action == "REJECT_JUSTIFICATION_REQUEST":
            return "Justification request was rejected."
        if action == "CREATE_OVERTIME_REQUEST":
            return "Employee submitted an overtime request."
        if action == "APPROVE_OVERTIME_REQUEST":
            return "Overtime request was approved."
        if action == "REJECT_OVERTIME_REQUEST":
            return "Overtime request was rejected."
        return "Attendance-related activity recorded."
