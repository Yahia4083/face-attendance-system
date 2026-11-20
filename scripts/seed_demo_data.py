"""Create deterministic, isolated demo data for graduation presentations.

Usage:
    python scripts/seed_demo_data.py --dry-run --reference-date 2026-06-25
    python scripts/seed_demo_data.py --reference-date 2026-06-25
    python scripts/seed_demo_data.py --cleanup-demo-data

The seeder is intentionally scoped to DEMO-prefixed rows. It never truncates
tables, never fabricates face embeddings, and never modifies non-demo records.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

# Allow `app.*` imports when running as a script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import or_
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.enums.user_role import UserRole
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.models.attendance_correction import AttendanceCorrectionModel
from app.infrastructure.database.models.attendance_record import AttendanceRecordModel
from app.infrastructure.database.models.audit_log import AuditLogModel
from app.infrastructure.database.models.department import DepartmentModel
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.employee_schedule import EmployeeScheduleModel
from app.infrastructure.database.models.face_embedding import FaceEmbeddingModel
from app.infrastructure.database.models.justification_request import JustificationRequestModel
from app.infrastructure.database.models.overtime_request import OvertimeRequestModel
from app.infrastructure.database.models.schedule_template import ScheduleTemplateModel
from app.infrastructure.database.models.system_setting import SystemSettingModel
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.security.password_hasher import hash_password


DEMO_PREFIX = "DEMO_"
DEMO_PASSWORD = "Demo123!"
DEMO_AUDIT_SOURCE = "demo_data_seeder"
DAY_WORKING_DAYS = "0,1,2,3,4,5"
ALL_WORKING_DAYS = "0,1,2,3,4,5,6"


@dataclass(frozen=True)
class DemoEmployeeSpec:
    number: str
    name: str
    email: str
    department: str
    position: str
    scenario: str
    is_active: bool = True


@dataclass(frozen=True)
class DemoTemplateSpec:
    name: str
    description: str
    start_time: time
    end_time: time
    is_overnight: bool = False
    check_in_grace_minutes: int = 10
    early_departure_tolerance_minutes: int = 5
    working_days: str = ALL_WORKING_DAYS


@dataclass
class DemoSeedSummary:
    reference_date: date
    departments: list[str]
    employees: list[DemoEmployeeSpec]
    templates: list[str]
    attendance_scenarios: dict[str, str]
    warnings: list[str]
    dry_run: bool = False
    cleanup: bool = False


DEPARTMENTS = [
    ("DEMO_Software Engineering", "Demo department for software product teams.", True),
    ("DEMO_Network Operations", "Demo department for infrastructure and operations.", True),
    ("DEMO_Human Resources", "Demo department for HR operations.", True),
    ("DEMO_Archived Department", "Inactive demo department for archive-state screens.", False),
]

EMPLOYEES = [
    DemoEmployeeSpec("DEMO001", "Amal Hassan", "demo.amal@example.com", "DEMO_Software Engineering", "Software Engineer", "Present and on time"),
    DemoEmployeeSpec("DEMO002", "Omar Saleh", "demo.omar@example.com", "DEMO_Software Engineering", "Backend Developer", "Late attendance"),
    DemoEmployeeSpec("DEMO003", "Sara Nasser", "demo.sara@example.com", "DEMO_Human Resources", "HR Officer", "Early departure"),
    DemoEmployeeSpec("DEMO004", "Youssef Ali", "demo.youssef@example.com", "DEMO_Network Operations", "Network Technician", "Missing checkout"),
    DemoEmployeeSpec("DEMO005", "Huda Mahmoud", "demo.huda@example.com", "DEMO_Human Resources", "Recruitment Specialist", "Absent"),
    DemoEmployeeSpec("DEMO006", "Karim Faraj", "demo.karim@example.com", "DEMO_Network Operations", "Field Support Engineer", "Unscheduled attendance"),
    DemoEmployeeSpec("DEMO007", "Lina Omar", "demo.lina@example.com", "DEMO_Software Engineering", "Release Engineer", "Overtime approved"),
    DemoEmployeeSpec("DEMO008", "Adam Salem", "demo.adam@example.com", "DEMO_Network Operations", "Operations Analyst", "Overtime pending"),
    DemoEmployeeSpec("DEMO009", "Noor Khaled", "demo.noor@example.com", "DEMO_Human Resources", "People Operations Analyst", "Overtime rejected"),
    DemoEmployeeSpec("DEMO010", "Inactive Demo Employee", "demo.inactive@example.com", "DEMO_Software Engineering", "Inactive Example", "Inactive account/employee example", False),
    DemoEmployeeSpec("DEMO011", "Nadia Mansour", "demo.nadia@example.com", "DEMO_Network Operations", "Night Shift Operator", "Overnight shift example"),
]

TEMPLATES = [
    DemoTemplateSpec(
        name="DEMO_Day Shift",
        description="Demo daytime schedule from 08:00 to 15:00.",
        start_time=time(8, 0),
        end_time=time(15, 0),
        is_overnight=False,
        check_in_grace_minutes=10,
        early_departure_tolerance_minutes=5,
        working_days=ALL_WORKING_DAYS,
    ),
    DemoTemplateSpec(
        name="DEMO_Evening Shift",
        description="Demo evening schedule from 15:00 to 22:00.",
        start_time=time(15, 0),
        end_time=time(22, 0),
        is_overnight=False,
        check_in_grace_minutes=10,
        early_departure_tolerance_minutes=5,
        working_days=ALL_WORKING_DAYS,
    ),
    DemoTemplateSpec(
        name="DEMO_Night Shift",
        description="Demo overnight schedule from 22:00 to 06:00.",
        start_time=time(22, 0),
        end_time=time(6, 0),
        is_overnight=True,
        check_in_grace_minutes=10,
        early_departure_tolerance_minutes=5,
        working_days=ALL_WORKING_DAYS,
    ),
]


def _business_today() -> date:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()


def _parse_reference_date(value: str | None) -> date:
    if not value:
        return _business_today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit("--reference-date must use YYYY-MM-DD format.") from exc


def _scheduled_datetimes(template: ScheduleTemplateModel, on_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(on_date, template.start_time)
    end_date = on_date + timedelta(days=1) if template.is_overnight else on_date
    return start, datetime.combine(end_date, template.end_time)


def _working_hours(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round(max(0, (end - start).total_seconds()) / 3600, 2)


def _demo_json(payload: dict) -> str:
    return json.dumps({"source": DEMO_AUDIT_SOURCE, **payload}, sort_keys=True)


class DemoDataSeeder:
    """Idempotent DEMO-prefixed data seeder."""

    def __init__(self, db: Session, *, reference_date: date, live_employee_id: int | None = None) -> None:
        self.db = db
        self.reference_date = reference_date
        self.live_employee_id = live_employee_id
        self.warnings: list[str] = []
        self._departments: dict[str, DepartmentModel] = {}
        self._employees: dict[str, EmployeeModel] = {}
        self._templates: dict[str, ScheduleTemplateModel] = {}
        self._schedules: dict[str, EmployeeScheduleModel] = {}

    def seed(self) -> DemoSeedSummary:
        self._check_justification_limit()
        self._ensure_departments()
        self._ensure_templates()
        self._ensure_employees()
        self._ensure_schedule_assignments()
        scenarios = self._ensure_attendance_dataset()
        self._ensure_justifications()
        self._ensure_overtime_requests()
        self._ensure_demo_audit("DEMO_DATA_SEEDED", None, {"reference_date": self.reference_date.isoformat()})
        self._check_live_employee()
        self.db.flush()
        return DemoSeedSummary(
            reference_date=self.reference_date,
            departments=[name for name, _, _ in DEPARTMENTS],
            employees=EMPLOYEES,
            templates=[item.name for item in TEMPLATES],
            attendance_scenarios=scenarios,
            warnings=self.warnings,
        )

    def cleanup(self) -> DemoSeedSummary:
        demo_employee_ids = [
            row[0]
            for row in self.db.query(EmployeeModel.id)
            .filter(EmployeeModel.employee_number.like("DEMO%"))
            .all()
        ]
        demo_user_ids = [
            row[0]
            for row in self.db.query(UserModel.id)
            .filter(UserModel.email.like("demo.%@example.com"))
            .all()
        ]
        demo_template_ids = [
            row[0]
            for row in self.db.query(ScheduleTemplateModel.id)
            .filter(ScheduleTemplateModel.name.like(f"{DEMO_PREFIX}%"))
            .all()
        ]
        demo_attendance_ids = []
        if demo_employee_ids:
            demo_attendance_ids = [
                row[0]
                for row in self.db.query(AttendanceRecordModel.id)
                .filter(AttendanceRecordModel.employee_id.in_(demo_employee_ids))
                .all()
            ]

        if demo_attendance_ids:
            self.db.query(AttendanceCorrectionModel).filter(
                AttendanceCorrectionModel.attendance_record_id.in_(demo_attendance_ids)
            ).delete(synchronize_session=False)
            self.db.query(OvertimeRequestModel).filter(
                OvertimeRequestModel.attendance_record_id.in_(demo_attendance_ids)
            ).delete(synchronize_session=False)
            self.db.query(JustificationRequestModel).filter(
                JustificationRequestModel.attendance_record_id.in_(demo_attendance_ids)
            ).delete(synchronize_session=False)
            self.db.query(AttendanceRecordModel).filter(
                AttendanceRecordModel.id.in_(demo_attendance_ids)
            ).delete(synchronize_session=False)

        if demo_employee_ids:
            demo_embedding_count = (
                self.db.query(FaceEmbeddingModel)
                .filter(FaceEmbeddingModel.employee_id.in_(demo_employee_ids))
                .count()
            )
            if demo_embedding_count:
                raise RuntimeError(
                    "Cleanup stopped because one or more DEMO employees have face embeddings. "
                    "The demo seeder does not delete biometric embeddings automatically."
                )
            self.db.query(EmployeeScheduleModel).filter(
                EmployeeScheduleModel.employee_id.in_(demo_employee_ids)
            ).delete(synchronize_session=False)
            self.db.query(EmployeeModel).filter(
                EmployeeModel.id.in_(demo_employee_ids)
            ).delete(synchronize_session=False)

        if demo_user_ids:
            self.db.query(UserModel).filter(UserModel.id.in_(demo_user_ids)).delete(synchronize_session=False)

        if demo_template_ids:
            self.db.query(ScheduleTemplateModel).filter(
                ScheduleTemplateModel.id.in_(demo_template_ids)
            ).delete(synchronize_session=False)

        self.db.query(DepartmentModel).filter(
            DepartmentModel.name.like(f"{DEMO_PREFIX}%")
        ).delete(synchronize_session=False)
        self.db.query(AuditLogModel).filter(
            or_(
                AuditLogModel.action.like("DEMO_%"),
                AuditLogModel.new_values.like(f"%{DEMO_AUDIT_SOURCE}%"),
                AuditLogModel.old_values.like(f"%{DEMO_AUDIT_SOURCE}%"),
            )
        ).delete(synchronize_session=False)
        self.db.flush()
        return DemoSeedSummary(
            reference_date=self.reference_date,
            departments=[name for name, _, _ in DEPARTMENTS],
            employees=EMPLOYEES,
            templates=[item.name for item in TEMPLATES],
            attendance_scenarios={},
            warnings=self.warnings,
            cleanup=True,
        )

    def _ensure_departments(self) -> None:
        for name, description, active in DEPARTMENTS:
            department = self.db.query(DepartmentModel).filter(DepartmentModel.name == name).first()
            if department is None:
                department = DepartmentModel(name=name)
                self.db.add(department)
            department.description = description
            department.is_active = active
            self._departments[name] = department
        self.db.flush()

    def _ensure_templates(self) -> None:
        for spec in TEMPLATES:
            template = self.db.query(ScheduleTemplateModel).filter(ScheduleTemplateModel.name == spec.name).first()
            if template is None:
                template = ScheduleTemplateModel(name=spec.name)
                self.db.add(template)
            template.description = spec.description
            template.start_time = spec.start_time
            template.end_time = spec.end_time
            template.is_overnight = spec.is_overnight
            template.check_in_grace_minutes = spec.check_in_grace_minutes
            template.early_departure_tolerance_minutes = spec.early_departure_tolerance_minutes
            template.grace_period_minutes = spec.check_in_grace_minutes
            template.minimum_overtime_minutes = 30
            template.working_days = spec.working_days
            template.is_active = True
            self._templates[spec.name] = template
        self.db.flush()

    def _ensure_employees(self) -> None:
        for spec in EMPLOYEES:
            user = self.db.query(UserModel).filter(UserModel.email == spec.email).first()
            if user is None:
                user = UserModel(email=spec.email, role=UserRole.EMPLOYEE)
                self.db.add(user)
            user.password_hash = hash_password(DEMO_PASSWORD)
            user.role = UserRole.EMPLOYEE
            user.is_active = spec.is_active
            self.db.flush()

            employee = (
                self.db.query(EmployeeModel)
                .filter(EmployeeModel.employee_number == spec.number)
                .first()
            )
            if employee is None:
                employee = EmployeeModel(user_id=user.id, employee_number=spec.number)
                self.db.add(employee)
            employee.user_id = user.id
            employee.full_name = spec.name
            employee.department_id = self._departments[spec.department].id
            employee.phone = None
            employee.position = spec.position
            employee.is_active = spec.is_active
            self._employees[spec.number] = employee
        self.db.flush()

    def _ensure_schedule_assignments(self) -> None:
        day_template = self._templates["DEMO_Day Shift"]
        night_template = self._templates["DEMO_Night Shift"]
        effective_start = self.reference_date - timedelta(days=30)
        for spec in EMPLOYEES:
            if spec.number in {"DEMO006", "DEMO010"}:
                continue
            template = night_template if spec.number == "DEMO011" else day_template
            assignment = (
                self.db.query(EmployeeScheduleModel)
                .filter(
                    EmployeeScheduleModel.employee_id == self._employees[spec.number].id,
                    EmployeeScheduleModel.schedule_template_id == template.id,
                )
                .first()
            )
            if assignment is None:
                assignment = EmployeeScheduleModel(
                    employee_id=self._employees[spec.number].id,
                    schedule_template_id=template.id,
                )
                self.db.add(assignment)
            assignment.effective_start_date = effective_start
            assignment.effective_end_date = None
            assignment.working_days = ALL_WORKING_DAYS
            assignment.is_active = True
            self._schedules[spec.number] = assignment
            self._ensure_demo_audit(
                "DEMO_SCHEDULE_ASSIGNED",
                None,
                {"employee_number": spec.number, "template": template.name},
            )
        self.db.flush()

    def _ensure_attendance_dataset(self) -> dict[str, str]:
        scenarios = {
            "DEMO001": "Present/on time",
            "DEMO002": "Late with approved justification",
            "DEMO003": "Early departure with pending justification",
            "DEMO004": "Missing checkout with rejected justification",
            "DEMO005": "Absent",
            "DEMO006": "Unscheduled",
            "DEMO007": "Approved overtime",
            "DEMO008": "Pending overtime",
            "DEMO009": "Rejected overtime",
            "DEMO011": "Overnight shift example",
        }

        day = self._templates["DEMO_Day Shift"]
        night = self._templates["DEMO_Night Shift"]
        self._scheduled_record("DEMO001", day, self.reference_date, check_in=time(8, 4), check_out=time(15, 8))
        self._scheduled_record("DEMO002", day, self.reference_date, check_in=time(8, 25), check_out=time(15, 10))
        self._scheduled_record("DEMO003", day, self.reference_date, check_in=time(8, 5), check_out=time(14, 25))
        self._scheduled_record("DEMO004", day, self.reference_date, check_in=time(8, 2), check_out=None, force_missing=True)
        self._absent_record("DEMO005", day, self.reference_date)
        self._unscheduled_record("DEMO006", self.reference_date, check_in=time(9, 30), check_out=time(11, 10))
        self._scheduled_record("DEMO007", day, self.reference_date, check_in=time(7, 58), check_out=time(16, 20))
        self._scheduled_record("DEMO008", day, self.reference_date, check_in=time(8, 1), check_out=time(16, 10))
        self._scheduled_record("DEMO009", day, self.reference_date, check_in=time(8, 0), check_out=time(16, 5))
        self._scheduled_record("DEMO011", night, self.reference_date - timedelta(days=1), check_in=time(21, 58), check_out=time(6, 7))

        self._ensure_trend_records(day)
        self.db.flush()
        for number, label in scenarios.items():
            self._ensure_demo_audit(
                "DEMO_ATTENDANCE_SCENARIO_CREATED",
                None,
                {"employee_number": number, "scenario": label, "reference_date": self.reference_date.isoformat()},
            )
        return scenarios

    def _ensure_trend_records(self, template: ScheduleTemplateModel) -> None:
        for offset in range(1, 15):
            on_date = self.reference_date - timedelta(days=offset)
            if on_date == self.reference_date - timedelta(days=1):
                # Leave room for the overnight example while still creating other records on that date.
                pass
            self._scheduled_record("DEMO001", template, on_date, check_in=time(8, 3), check_out=time(15, 5))
            self._scheduled_record("DEMO002", template, on_date, check_in=time(8, 8), check_out=time(15, 4))
            if offset % 3 == 0:
                self._scheduled_record("DEMO003", template, on_date, check_in=time(8, 18), check_out=time(15, 2))

    def _scheduled_record(
        self,
        employee_number: str,
        template: ScheduleTemplateModel,
        on_date: date,
        *,
        check_in: time,
        check_out: time | None,
        force_missing: bool = False,
    ) -> AttendanceRecordModel:
        assignment = self._schedules[employee_number]
        scheduled_start, scheduled_end = _scheduled_datetimes(template, on_date)
        check_in_dt = datetime.combine(on_date, check_in)
        check_out_dt = None
        if check_out is not None:
            checkout_date = on_date + timedelta(days=1) if template.is_overnight and check_out < template.start_time else on_date
            check_out_dt = datetime.combine(checkout_date, check_out)

        late_minutes = max(
            0,
            int((check_in_dt - (scheduled_start + timedelta(minutes=template.check_in_grace_minutes))).total_seconds() // 60),
        )
        early_departure_minutes = 0
        if check_out_dt is not None:
            early_departure_minutes = max(
                0,
                int(((scheduled_end - timedelta(minutes=template.early_departure_tolerance_minutes)) - check_out_dt).total_seconds() // 60),
            )

        is_missing = force_missing or (check_in_dt is not None and check_out_dt is None)
        if is_missing:
            status = AttendanceStatus.MISSING_CHECKOUT
        elif late_minutes > 0:
            status = AttendanceStatus.LATE
        elif early_departure_minutes > 0:
            status = AttendanceStatus.EARLY_DEPARTURE
        else:
            status = AttendanceStatus.PRESENT

        record = self._attendance_record(employee_number, on_date, is_unscheduled=False)
        record.employee_schedule_id = assignment.id
        record.schedule_template_id = template.id
        record.scheduled_start_datetime = scheduled_start
        record.scheduled_end_datetime = scheduled_end
        record.check_in_time = check_in_dt
        record.check_out_time = check_out_dt
        record.working_hours = _working_hours(check_in_dt, check_out_dt)
        record.status = status
        record.is_late = late_minutes > 0
        record.is_early_departure = early_departure_minutes > 0
        record.is_unscheduled = False
        record.is_missing_checkout = is_missing
        record.late_minutes = late_minutes
        record.early_departure_minutes = early_departure_minutes
        record.recognition_model_name = None
        record.detector_backend = None
        record.processed_at = scheduled_end + timedelta(minutes=30) if is_missing else None
        record.location = "DEMO generated attendance"
        return record

    def _absent_record(self, employee_number: str, template: ScheduleTemplateModel, on_date: date) -> AttendanceRecordModel:
        assignment = self._schedules[employee_number]
        scheduled_start, scheduled_end = _scheduled_datetimes(template, on_date)
        record = self._attendance_record(employee_number, on_date, is_unscheduled=False)
        record.employee_schedule_id = assignment.id
        record.schedule_template_id = template.id
        record.scheduled_start_datetime = scheduled_start
        record.scheduled_end_datetime = scheduled_end
        record.check_in_time = None
        record.check_out_time = None
        record.working_hours = None
        record.status = AttendanceStatus.ABSENT
        record.is_late = False
        record.is_early_departure = False
        record.is_unscheduled = False
        record.is_missing_checkout = False
        record.late_minutes = 0
        record.early_departure_minutes = 0
        record.recognition_model_name = None
        record.detector_backend = None
        record.processed_at = scheduled_end + timedelta(minutes=30)
        record.location = "DEMO generated absence"
        return record

    def _unscheduled_record(self, employee_number: str, on_date: date, *, check_in: time, check_out: time) -> AttendanceRecordModel:
        record = self._attendance_record(employee_number, on_date, is_unscheduled=True)
        check_in_dt = datetime.combine(on_date, check_in)
        check_out_dt = datetime.combine(on_date, check_out)
        record.employee_schedule_id = None
        record.schedule_template_id = None
        record.scheduled_start_datetime = None
        record.scheduled_end_datetime = None
        record.check_in_time = check_in_dt
        record.check_out_time = check_out_dt
        record.working_hours = _working_hours(check_in_dt, check_out_dt)
        record.status = AttendanceStatus.UNSCHEDULED
        record.is_late = False
        record.is_early_departure = False
        record.is_unscheduled = True
        record.is_missing_checkout = False
        record.late_minutes = 0
        record.early_departure_minutes = 0
        record.recognition_model_name = None
        record.detector_backend = None
        record.processed_at = None
        record.location = "DEMO generated unscheduled attendance"
        return record

    def _attendance_record(self, employee_number: str, on_date: date, *, is_unscheduled: bool) -> AttendanceRecordModel:
        employee = self._employees[employee_number]
        record = (
            self.db.query(AttendanceRecordModel)
            .filter(
                AttendanceRecordModel.employee_id == employee.id,
                AttendanceRecordModel.attendance_date == on_date,
                AttendanceRecordModel.is_unscheduled == is_unscheduled,
            )
            .first()
        )
        if record is None:
            record = AttendanceRecordModel(employee_id=employee.id, attendance_date=on_date)
            self.db.add(record)
        return record

    def _ensure_justifications(self) -> None:
        items = [
            ("DEMO002", "LATE", RequestStatus.APPROVED, "Approved demo note: traffic documentation accepted."),
            ("DEMO003", "EARLY_DEPARTURE", RequestStatus.PENDING, None),
            ("DEMO004", "MISSING_CHECKOUT", RequestStatus.REJECTED, "Rejected demo note: checkout device logs did not confirm departure."),
        ]
        reviewer_id = self._admin_user_id()
        reviewed_at = datetime.combine(self.reference_date, time(17, 30))
        for employee_number, request_type, status_value, admin_comment in items:
            employee = self._employees[employee_number]
            record = self._record_for(employee_number, self.reference_date, is_unscheduled=False)
            request = (
                self.db.query(JustificationRequestModel)
                .filter(JustificationRequestModel.attendance_record_id == record.id)
                .first()
            )
            if request is None:
                request = JustificationRequestModel(
                    employee_id=employee.id,
                    attendance_record_id=record.id,
                    request_type=request_type,
                )
                self.db.add(request)
            request.employee_id = employee.id
            request.request_type = request_type
            request.explanation = f"Demo justification for {request_type.replace('_', ' ').lower()} scenario."
            request.status = status_value
            request.admin_comment = admin_comment
            request.reviewed_by = reviewer_id if status_value != RequestStatus.PENDING else None
            request.reviewed_at = reviewed_at if status_value != RequestStatus.PENDING else None

    def _ensure_overtime_requests(self) -> None:
        items = [
            ("DEMO007", OvertimeStatus.APPROVED, 75, "Approved demo overtime for production release support."),
            ("DEMO008", OvertimeStatus.PENDING, None, "Pending demo overtime for network maintenance."),
            ("DEMO009", OvertimeStatus.REJECTED, None, "Rejected demo overtime: work was not pre-approved."),
        ]
        reviewer_id = self._admin_user_id()
        reviewed_at = datetime.combine(self.reference_date, time(18, 0))
        for employee_number, status_value, approved_minutes, reviewer_note in items:
            employee = self._employees[employee_number]
            record = self._record_for(employee_number, self.reference_date, is_unscheduled=False)
            eligible = int((record.check_out_time - record.scheduled_end_datetime).total_seconds() // 60)
            request = (
                self.db.query(OvertimeRequestModel)
                .filter(
                    OvertimeRequestModel.employee_id == employee.id,
                    OvertimeRequestModel.attendance_record_id == record.id,
                )
                .first()
            )
            if request is None:
                request = OvertimeRequestModel(employee_id=employee.id, attendance_record_id=record.id)
                self.db.add(request)
            request.overtime_minutes = min(eligible, 75)
            request.eligible_minutes_at_submission = eligible
            request.approved_minutes = approved_minutes
            request.reason = "Demo overtime request for presentation workflow."
            request.status = status_value
            request.reviewed_by = reviewer_id if status_value != OvertimeStatus.PENDING else None
            request.reviewer_note = reviewer_note if status_value != OvertimeStatus.PENDING else None
            request.reviewed_at = reviewed_at if status_value != OvertimeStatus.PENDING else None

    def _record_for(self, employee_number: str, on_date: date, *, is_unscheduled: bool) -> AttendanceRecordModel:
        employee = self._employees[employee_number]
        record = (
            self.db.query(AttendanceRecordModel)
            .filter(
                AttendanceRecordModel.employee_id == employee.id,
                AttendanceRecordModel.attendance_date == on_date,
                AttendanceRecordModel.is_unscheduled == is_unscheduled,
            )
            .first()
        )
        if record is None:
            raise RuntimeError(f"Seeded attendance record missing for {employee_number} on {on_date}")
        return record

    def _admin_user_id(self) -> int | None:
        admin = (
            self.db.query(UserModel)
            .filter(UserModel.role == UserRole.ADMIN, UserModel.is_active.is_(True))
            .order_by(UserModel.id.asc())
            .first()
        )
        return admin.id if admin is not None else None

    def _ensure_demo_audit(self, action: str, entity_id: int | None, payload: dict) -> None:
        marker = payload.copy()
        marker_json = _demo_json(marker)
        exists = (
            self.db.query(AuditLogModel)
            .filter(
                AuditLogModel.action == action,
                AuditLogModel.entity_type == "DemoData",
                AuditLogModel.new_values == marker_json,
            )
            .first()
        )
        if exists is not None:
            return
        self.db.add(
            AuditLogModel(
                actor_user_id=None,
                action=action,
                entity_type="DemoData",
                entity_id=entity_id,
                old_values=None,
                new_values=marker_json,
                ip_address=None,
            )
        )

    def _check_live_employee(self) -> None:
        if self.live_employee_id is None:
            return
        employee = self.db.get(EmployeeModel, self.live_employee_id)
        if employee is None:
            self.warnings.append(f"Live employee id {self.live_employee_id} was not found.")
            return
        active_embeddings = (
            self.db.query(FaceEmbeddingModel)
            .filter(FaceEmbeddingModel.employee_id == employee.id, FaceEmbeddingModel.is_active.is_(True))
            .count()
        )
        if not employee.is_active:
            self.warnings.append(f"Live employee {employee.employee_number} is inactive.")
        if active_embeddings == 0:
            self.warnings.append(f"Live employee {employee.employee_number} has no active FaceNet enrollment.")
        self.warnings.append(
            f"Live employee check: use {employee.full_name} ({employee.employee_number}) for real camera-based check-in/check-out. No attendance rows were changed."
        )

    def _check_justification_limit(self) -> None:
        limit = int(get_settings().JUSTIFICATION_MONTHLY_LIMIT)
        override = (
            self.db.query(SystemSettingModel)
            .filter(SystemSettingModel.key == "JUSTIFICATION_MONTHLY_LIMIT")
            .first()
        )
        if override is not None:
            try:
                limit = int(str(override.value).strip())
            except ValueError:
                self.warnings.append(
                    "JUSTIFICATION_MONTHLY_LIMIT override is not a valid integer. The seeder did not modify this setting."
                )
                return
        if limit < 1:
            self.warnings.append(
                "Current JUSTIFICATION_MONTHLY_LIMIT is 0. Demo justification rows are seeded for presentation only; the setting was not modified."
            )


def _run_in_transaction(
    session_factory: sessionmaker,
    *,
    reference_date: date,
    dry_run: bool,
    cleanup: bool,
    live_employee_id: int | None,
) -> DemoSeedSummary:
    db = session_factory()
    try:
        seeder = DemoDataSeeder(db, reference_date=reference_date, live_employee_id=live_employee_id)
        summary = seeder.cleanup() if cleanup else seeder.seed()
        if dry_run:
            db.rollback()
            summary.dry_run = True
        else:
            db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _print_summary(summary: DemoSeedSummary) -> None:
    if summary.cleanup:
        print("DEMO DATA CLEANUP COMPLETED" if not summary.dry_run else "DEMO DATA CLEANUP DRY RUN COMPLETED")
        print(f"Reference date: {summary.reference_date.isoformat()}")
        print("Cleanup scope: DEMO-prefixed employees, users, departments, schedule templates, attendance, requests, and demo audit entries.")
        return

    print("DEMO DATA SEEDED SUCCESSFULLY" if not summary.dry_run else "DEMO DATA DRY RUN COMPLETED")
    print()
    print(f"Reference date: {summary.reference_date.isoformat()}")
    print()
    print("Dashboard scenarios:")
    for number, label in summary.attendance_scenarios.items():
        print(f"* {number}: {label}")
    print()
    print("Demo login accounts:")
    for employee in summary.employees:
        print(f"* {employee.email} / {DEMO_PASSWORD} ({employee.number} - {employee.scenario})")
    print()
    print("Demo departments:")
    for department in summary.departments:
        print(f"* {department}")
    print()
    print("Demo schedule templates:")
    for template in summary.templates:
        print(f"* {template}")
    print()
    if summary.warnings:
        print("Warnings:")
        for warning in summary.warnings:
            print(f"* {warning}")
        print()
    print("Live attendance reminder:")
    print("Use an existing real employee with active FaceNet enrollment. No fake embeddings were created.")
    print()
    print("Recommended presentation flow:")
    print("1. Open Dashboard for the reference date and explain each attendance scenario.")
    print("2. Filter Attendance Management by DEMO employees, status, department, and date.")
    print("3. Open Requests to show pending, approved, and rejected justification/overtime examples.")
    print("4. Open Reports for the reference month and export CSV/XLSX.")
    print("5. Use live camera attendance only with a real enrolled employee.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed safe DEMO-prefixed presentation data.")
    parser.add_argument("--reference-date", help="Main dashboard demo date in YYYY-MM-DD format.")
    parser.add_argument("--dry-run", action="store_true", help="Run the seeder and rollback instead of committing.")
    parser.add_argument("--cleanup-demo-data", action="store_true", help="Remove only DEMO-prefixed seeded data.")
    parser.add_argument("--live-employee-id", type=int, help="Optional real enrolled employee id for live camera preparation checks.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    reference_date = _parse_reference_date(args.reference_date)
    try:
        summary = _run_in_transaction(
            SessionLocal,
            reference_date=reference_date,
            dry_run=args.dry_run,
            cleanup=args.cleanup_demo_data,
            live_employee_id=args.live_employee_id,
        )
    except Exception as exc:
        print(f"[ERROR] Demo data operation failed and was rolled back: {exc}")
        return 1
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
