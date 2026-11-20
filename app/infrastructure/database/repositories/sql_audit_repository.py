"""
SQL Audit Repository
====================
SQLAlchemy implementation of the AuditRepositoryInterface.
"""

from typing import Optional

from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Session, aliased

from app.domain.entities.audit_log import AuditLogRecord
from app.domain.repositories.audit_repository import AuditLogFilters, AuditRepositoryInterface
from app.infrastructure.database.models.audit_log import AuditLogModel
from app.infrastructure.database.models.attendance_record import AttendanceRecordModel
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.user import UserModel


ActorUserModel = aliased(UserModel, name="audit_actor_user")
ActorEmployeeModel = aliased(EmployeeModel, name="audit_actor_employee")
SubjectAttendanceModel = aliased(AttendanceRecordModel, name="audit_subject_attendance")
SubjectEmployeeModel = aliased(EmployeeModel, name="audit_subject_employee")
SubjectUserModel = aliased(UserModel, name="audit_subject_user")


class SqlAuditRepository(AuditRepositoryInterface):
    """Concrete audit-log repository backed by SQLAlchemy/MySQL."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        *,
        actor_user_id: Optional[int],
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        old_values: Optional[str] = None,
        new_values: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Create and persist an audit log entry."""
        entry = AuditLogModel(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
        )
        self._db.add(entry)
        self._db.commit()

    def _base_read_query(self):
        return (
            self._db.query(
                AuditLogModel,
                ActorUserModel.email.label("actor_email"),
                ActorUserModel.role.label("actor_role"),
                ActorEmployeeModel.full_name.label("actor_name"),
                SubjectUserModel.id.label("subject_user_id"),
                SubjectUserModel.email.label("subject_email"),
                SubjectEmployeeModel.full_name.label("subject_name"),
                SubjectEmployeeModel.employee_number.label("subject_employee_number"),
            )
            .outerjoin(ActorUserModel, ActorUserModel.id == AuditLogModel.actor_user_id)
            .outerjoin(ActorEmployeeModel, ActorEmployeeModel.user_id == ActorUserModel.id)
            .outerjoin(
                SubjectAttendanceModel,
                and_(
                    AuditLogModel.entity_type == "AttendanceRecord",
                    AuditLogModel.entity_id == SubjectAttendanceModel.id,
                ),
            )
            .outerjoin(
                SubjectEmployeeModel,
                SubjectEmployeeModel.id == SubjectAttendanceModel.employee_id,
            )
            .outerjoin(SubjectUserModel, SubjectUserModel.id == SubjectEmployeeModel.user_id)
        )

    @staticmethod
    def _apply_filters(query, filters: AuditLogFilters):
        if filters.created_from_utc is not None:
            query = query.filter(AuditLogModel.created_at >= filters.created_from_utc)
        if filters.created_to_utc_exclusive is not None:
            query = query.filter(AuditLogModel.created_at < filters.created_to_utc_exclusive)
        if filters.action is not None:
            query = query.filter(AuditLogModel.action == filters.action)
        if filters.entity_type is not None:
            query = query.filter(AuditLogModel.entity_type == filters.entity_type)
        if filters.actor_query is not None:
            actor_query = filters.actor_query.strip()
            lowered = actor_query.lower()
            if lowered == "system":
                query = query.filter(AuditLogModel.actor_user_id.is_(None))
            else:
                actor_filters = [
                    ActorUserModel.email.contains(actor_query, autoescape=True),
                    ActorEmployeeModel.full_name.contains(actor_query, autoescape=True),
                    SubjectUserModel.email.contains(actor_query, autoescape=True),
                    SubjectEmployeeModel.full_name.contains(actor_query, autoescape=True),
                    SubjectEmployeeModel.employee_number.contains(actor_query, autoescape=True),
                ]
                if actor_query.isdigit():
                    actor_filters.append(
                        cast(AuditLogModel.actor_user_id, String) == actor_query
                    )
                query = query.filter(or_(*actor_filters))
        return query

    def list_logs(
        self,
        *,
        filters: AuditLogFilters,
        page: int,
        page_size: int,
    ) -> list[AuditLogRecord]:
        rows = (
            self._apply_filters(self._base_read_query(), filters)
            .order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return [
            AuditLogRecord(
                id=row.AuditLogModel.id,
                actor_user_id=row.AuditLogModel.actor_user_id,
                actor_email=row.actor_email,
                actor_name=row.actor_name,
                actor_role=(
                    row.actor_role.value
                    if hasattr(row.actor_role, "value")
                    else str(row.actor_role) if row.actor_role is not None else None
                ),
                action=row.AuditLogModel.action,
                entity_type=row.AuditLogModel.entity_type,
                entity_id=row.AuditLogModel.entity_id,
                old_values=row.AuditLogModel.old_values,
                new_values=row.AuditLogModel.new_values,
                created_at=row.AuditLogModel.created_at,
                subject_user_id=row.subject_user_id,
                subject_email=row.subject_email,
                subject_name=row.subject_name,
                subject_employee_number=row.subject_employee_number,
            )
            for row in rows
        ]

    def count_logs(self, *, filters: AuditLogFilters) -> int:
        query = (
            self._db.query(func.count(AuditLogModel.id))
            .outerjoin(ActorUserModel, ActorUserModel.id == AuditLogModel.actor_user_id)
            .outerjoin(ActorEmployeeModel, ActorEmployeeModel.user_id == ActorUserModel.id)
            .outerjoin(
                SubjectAttendanceModel,
                and_(
                    AuditLogModel.entity_type == "AttendanceRecord",
                    AuditLogModel.entity_id == SubjectAttendanceModel.id,
                ),
            )
            .outerjoin(
                SubjectEmployeeModel,
                SubjectEmployeeModel.id == SubjectAttendanceModel.employee_id,
            )
            .outerjoin(SubjectUserModel, SubjectUserModel.id == SubjectEmployeeModel.user_id)
        )
        return int(self._apply_filters(query, filters).scalar() or 0)

    def list_actions(self) -> list[str]:
        rows = (
            self._db.query(AuditLogModel.action)
            .distinct()
            .order_by(AuditLogModel.action.asc())
            .all()
        )
        return [row[0] for row in rows if row[0]]

    def list_entity_types(self) -> list[str]:
        rows = (
            self._db.query(AuditLogModel.entity_type)
            .distinct()
            .order_by(AuditLogModel.entity_type.asc())
            .all()
        )
        return [row[0] for row in rows if row[0]]
