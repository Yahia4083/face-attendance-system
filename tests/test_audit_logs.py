import json
from datetime import date, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.dto.audit_log_dto import ListAuditLogsRequest
from app.application.use_cases.audit_logs.list_audit_logs import ListAuditLogs
from app.domain.entities.audit_log import AuditLogRecord
from app.domain.enums.user_role import UserRole
from app.domain.repositories.audit_repository import AuditLogFilters
from app.domain.services.audit_log_sanitizer import REDACTED_VALUE, parse_and_sanitize_audit_json
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import AuditLogModel, UserModel
from app.infrastructure.database.repositories.sql_audit_repository import SqlAuditRepository
from app.infrastructure.security.jwt_service import create_access_token
from app.dependencies import get_audit_repository, get_user_repository
from app.main import create_app


def audit_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_audit_logs(db):
    actor = UserModel(
        email="admin@example.com",
        password_hash="not-used",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(actor)
    db.flush()
    db.add_all(
        [
            AuditLogModel(
                actor_user_id=actor.id,
                action="CREATE_EMPLOYEE",
                entity_type="Employee",
                entity_id=7,
                new_values=json.dumps(
                    {
                        "employee_number": "EMP007",
                        "email": "employee@example.com",
                        "password": "plain-secret",
                        "nested": {
                            "access_token": "jwt-secret",
                            "face_embedding": [0.1, 0.2],
                        },
                    }
                ),
                created_at=datetime(2026, 8, 24, 18, 30),
            ),
            AuditLogModel(
                actor_user_id=None,
                action="PROCESS_DAILY_ATTENDANCE",
                entity_type="AttendanceRecord",
                entity_id=None,
                new_values=json.dumps({"on_date": "2026-08-24"}),
                created_at=datetime(2026, 8, 24, 19, 30),
            ),
            AuditLogModel(
                actor_user_id=999,
                action="UPDATE_SYSTEM_SETTING",
                entity_type="SystemSetting",
                entity_id=2,
                new_values=json.dumps({"key": "ORGANIZATION_NAME", "value": "University"}),
                created_at=datetime(2026, 8, 23, 22, 30),
            ),
        ]
    )
    db.commit()
    return actor


def test_recursive_audit_metadata_sanitization_redacts_security_and_biometric_values():
    result = parse_and_sanitize_audit_json(
        json.dumps(
            {
                "email": "safe@example.com",
                "password_hash": "hash",
                "children": [
                    {"refresh-token": "token"},
                    {"image_bytes": "bytes", "embedding_vector": [1, 2]},
                ],
            }
        )
    )

    assert result["email"] == "safe@example.com"
    assert result["password_hash"] == REDACTED_VALUE
    assert result["children"][0]["refresh-token"] == REDACTED_VALUE
    assert result["children"][1]["image_bytes"] == REDACTED_VALUE
    assert result["children"][1]["embedding_vector"] == REDACTED_VALUE
    assert parse_and_sanitize_audit_json("not-json") is None
    assert parse_and_sanitize_audit_json('"unstructured secret"') is None


def test_sql_audit_repository_orders_and_filters_before_pagination():
    db = audit_session()
    try:
        seed_audit_logs(db)
        repository = SqlAuditRepository(db)

        first_page = repository.list_logs(
            filters=AuditLogFilters(),
            page=1,
            page_size=2,
        )
        assert [item.action for item in first_page] == [
            "PROCESS_DAILY_ATTENDANCE",
            "CREATE_EMPLOYEE",
        ]
        assert repository.count_logs(filters=AuditLogFilters()) == 3

        action_filter = AuditLogFilters(action="CREATE_EMPLOYEE")
        assert repository.count_logs(filters=action_filter) == 1
        assert repository.list_logs(
            filters=action_filter,
            page=1,
            page_size=1,
        )[0].entity_id == 7

        actor_filter = AuditLogFilters(actor_query="admin@example.com")
        assert repository.count_logs(filters=actor_filter) == 1
        system_filter = AuditLogFilters(actor_query="System")
        assert repository.count_logs(filters=system_filter) == 1
        entity_filter = AuditLogFilters(entity_type="SystemSetting")
        assert repository.count_logs(filters=entity_filter) == 1
    finally:
        db.close()


def test_audit_use_case_uses_business_date_and_handles_system_or_missing_actors():
    db = audit_session()
    try:
        seed_audit_logs(db)
        result = ListAuditLogs(
            SqlAuditRepository(db),
            timezone_name="Africa/Tripoli",
        ).execute(
            ListAuditLogsRequest(
                date_from=date(2026, 8, 24),
                date_to=date(2026, 8, 24),
                page=1,
                page_size=25,
            )
        )

        assert result.total == 3
        by_action = {item.action: item for item in result.items}
        assert by_action["PROCESS_DAILY_ATTENDANCE"].actor.kind == "SYSTEM"
        assert by_action["PROCESS_DAILY_ATTENDANCE"].actor.name == "System"
        assert by_action["UPDATE_SYSTEM_SETTING"].actor.kind == "UNKNOWN"
        assert by_action["UPDATE_SYSTEM_SETTING"].actor.name == "Unknown user"
        assert by_action["CREATE_EMPLOYEE"].target.label == "Employee - EMP007"
        assert by_action["CREATE_EMPLOYEE"].current_values["password"] == REDACTED_VALUE
        serialized = json.dumps(by_action["CREATE_EMPLOYEE"].current_values)
        assert "plain-secret" not in serialized
        assert "jwt-secret" not in serialized
        assert "0.1" not in serialized
    finally:
        db.close()


def test_live_kiosk_attendance_exposes_employee_as_performer_and_admin_as_authorizer():
    class KioskAuditRepository:
        def list_logs(self, *, filters, page, page_size):
            return [
                AuditLogRecord(
                    id=405,
                    actor_user_id=1,
                    actor_email="admin@example.com",
                    actor_name=None,
                    actor_role="ADMIN",
                    action="ATTENDANCE_CHECK_IN",
                    entity_type="AttendanceRecord",
                    entity_id=155,
                    old_values=None,
                    new_values=json.dumps(
                        {"employee_id": 4, "source": "LIVE_KIOSK", "status": "LATE"}
                    ),
                    created_at=datetime(2026, 8, 24, 21, 27, 15),
                    subject_user_id=5,
                    subject_email="demo.employee@example.com",
                    subject_name="Demo Employee",
                    subject_employee_number="DEMO004",
                )
            ]

        def count_logs(self, *, filters):
            return 1

        def list_actions(self):
            return ["ATTENDANCE_CHECK_IN"]

        def list_entity_types(self):
            return ["AttendanceRecord"]

    result = ListAuditLogs(
        KioskAuditRepository(),
        timezone_name="Africa/Tripoli",
    ).execute(ListAuditLogsRequest())
    item = result.items[0]

    assert item.performed_by is not None
    assert item.performed_by.name == "Demo Employee"
    assert item.performed_by.employee_number == "DEMO004"
    assert item.actor.name == "Administrator"
    assert item.actor.email == "admin@example.com"


def test_failed_live_verification_exposes_kiosk_as_performer_not_admin():
    class FailedVerificationRepository:
        def list_logs(self, *, filters, page, page_size):
            return [
                AuditLogRecord(
                    id=504,
                    actor_user_id=1,
                    actor_email="admin@example.com",
                    actor_name=None,
                    actor_role="ADMIN",
                    action="LIVENESS_VERIFICATION_FAILED",
                    entity_type="LiveAttendance",
                    entity_id=None,
                    old_values=None,
                    new_values=json.dumps({"failure_reason": "No face detected."}),
                    created_at=datetime(2026, 8, 25, 20, 23),
                )
            ]

        def count_logs(self, *, filters):
            return 1

        def list_actions(self):
            return ["LIVENESS_VERIFICATION_FAILED"]

        def list_entity_types(self):
            return ["LiveAttendance"]

    result = ListAuditLogs(
        FailedVerificationRepository(),
        timezone_name="Africa/Tripoli",
    ).execute(ListAuditLogsRequest())
    item = result.items[0]

    assert item.performed_by is not None
    assert item.performed_by.name == "Live kiosk terminal"
    assert item.performed_by.kind == "SYSTEM"
    assert item.actor.name == "Administrator"


class FakeAuditReadRepository:
    def log(self, **kwargs):
        raise AssertionError("Audit-log reads must not create audit entries.")

    def list_logs(self, *, filters, page, page_size):
        return [
            AuditLogRecord(
                id=10,
                actor_user_id=None,
                actor_email=None,
                actor_name=None,
                actor_role=None,
                action="LOGIN_FAILED",
                entity_type="User",
                entity_id=None,
                old_values=None,
                new_values=json.dumps(
                    {
                        "email": "person@example.com",
                        "password_hash": "must-not-leak",
                        "token": "must-not-leak",
                        "embedding": [0.1],
                    }
                ),
                created_at=datetime(2026, 8, 24, 18, 32, 14),
            )
        ]

    def count_logs(self, *, filters):
        return 1

    def list_actions(self):
        return ["LOGIN_FAILED"]

    def list_entity_types(self):
        return ["User"]


class FakeUserRepository:
    def __init__(self, user):
        self.user = user

    def get_by_id(self, user_id):
        return self.user if self.user.id == user_id else None


def _auth_user(role):
    return SimpleNamespace(
        id=1,
        email="user@example.com",
        role=role,
        is_active=True,
        token_version=0,
        must_change_password=False,
    )


def test_audit_log_endpoint_is_admin_only_timezone_aware_and_safe():
    admin = _auth_user(UserRole.ADMIN)
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: FakeUserRepository(admin)
    app.dependency_overrides[get_audit_repository] = FakeAuditReadRepository
    token = create_access_token({"sub": str(admin.id), "ver": 0})

    with TestClient(app) as client:
        response = client.get(
            "/audit-logs?page=1&page_size=25",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["created_at"] == "2026-08-24T20:32:14+02:00"
    assert payload["items"][0]["actor"]["name"] == "System"
    assert payload["items"][0]["current_values"]["password_hash"] == REDACTED_VALUE
    assert "must-not-leak" not in response.text
    assert "ip_address" not in response.text


def test_employee_cannot_list_audit_logs():
    employee = _auth_user(UserRole.EMPLOYEE)
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: FakeUserRepository(employee)
    app.dependency_overrides[get_audit_repository] = FakeAuditReadRepository
    token = create_access_token({"sub": str(employee.id), "ver": 0})

    with TestClient(app) as client:
        response = client.get(
            "/audit-logs",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
