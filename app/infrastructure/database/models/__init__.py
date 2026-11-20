"""
Database Models Package
=======================
Imports all SQLAlchemy models so that Alembic and the
application can discover them via a single import.
"""

from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.models.department import DepartmentModel
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.schedule_template import ScheduleTemplateModel
from app.infrastructure.database.models.employee_schedule import EmployeeScheduleModel
from app.infrastructure.database.models.face_embedding import FaceEmbeddingModel
from app.infrastructure.database.models.attendance_record import AttendanceRecordModel
from app.infrastructure.database.models.attendance_correction import AttendanceCorrectionModel
from app.infrastructure.database.models.justification_request import JustificationRequestModel
from app.infrastructure.database.models.overtime_request import OvertimeRequestModel
from app.infrastructure.database.models.audit_log import AuditLogModel
from app.infrastructure.database.models.system_setting import SystemSettingModel

__all__ = [
    "UserModel",
    "DepartmentModel",
    "EmployeeModel",
    "ScheduleTemplateModel",
    "EmployeeScheduleModel",
    "FaceEmbeddingModel",
    "AttendanceRecordModel",
    "AttendanceCorrectionModel",
    "JustificationRequestModel",
    "OvertimeRequestModel",
    "AuditLogModel",
    "SystemSettingModel",
]
