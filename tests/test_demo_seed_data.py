from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.user_role import UserRole
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import (  # noqa: F401 - ensure model metadata is registered
    AttendanceRecordModel,
    DepartmentModel,
    EmployeeModel,
    FaceEmbeddingModel,
    JustificationRequestModel,
    UserModel,
)
from app.infrastructure.security.password_hasher import hash_password
from scripts.seed_demo_data import DemoDataSeeder


def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def seed_admin_and_real_employee(db):
    department = DepartmentModel(
        name="Real Department",
        description="Non-demo department",
        is_active=True,
    )
    admin = UserModel(
        email="real.admin@example.com",
        password_hash=hash_password("admin123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    user = UserModel(
        email="real.employee@example.com",
        password_hash=hash_password("employee123"),
        role=UserRole.EMPLOYEE,
        is_active=True,
    )
    db.add_all([department, admin, user])
    db.flush()
    employee = EmployeeModel(
        user_id=user.id,
        department_id=department.id,
        full_name="Real Employee",
        employee_number="REAL001",
        is_active=True,
    )
    db.add(employee)
    db.flush()
    attendance = AttendanceRecordModel(
        employee_id=employee.id,
        attendance_date=date(2026, 6, 25),
        status=AttendanceStatus.PRESENT,
        is_late=False,
        is_early_departure=False,
        is_unscheduled=False,
        is_missing_checkout=False,
        late_minutes=0,
        early_departure_minutes=0,
    )
    embedding = FaceEmbeddingModel(
        employee_id=employee.id,
        embedding_vector=b"real-embedding",
        image_path="real/path.jpg",
        model_name="facenet-onnx-512d-haikalmumtaz-v1",
        is_active=True,
    )
    db.add_all([attendance, embedding])
    db.commit()
    return employee, attendance, embedding


def test_demo_seed_is_idempotent_and_does_not_duplicate_employees():
    Session = session_factory()
    db = Session()
    try:
        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).seed()
        db.commit()
        first_count = db.query(EmployeeModel).filter(EmployeeModel.employee_number.like("DEMO%")).count()

        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).seed()
        db.commit()
        second_count = db.query(EmployeeModel).filter(EmployeeModel.employee_number.like("DEMO%")).count()

        assert first_count == 11
        assert second_count == first_count
    finally:
        db.close()


def test_demo_seed_does_not_modify_non_demo_data_or_real_embeddings():
    Session = session_factory()
    db = Session()
    try:
        employee, attendance, embedding = seed_admin_and_real_employee(db)
        original_name = employee.full_name
        original_status = attendance.status
        original_embedding = embedding.embedding_vector

        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).seed()
        db.commit()

        db.refresh(employee)
        db.refresh(attendance)
        db.refresh(embedding)
        assert employee.full_name == original_name
        assert attendance.status == original_status
        assert embedding.embedding_vector == original_embedding
        assert embedding.is_active is True
    finally:
        db.close()


def test_demo006_unscheduled_attendance_is_not_late_and_has_no_schedule_values():
    Session = session_factory()
    db = Session()
    try:
        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).seed()
        db.commit()

        employee = db.query(EmployeeModel).filter(EmployeeModel.employee_number == "DEMO006").one()
        record = (
            db.query(AttendanceRecordModel)
            .filter(
                AttendanceRecordModel.employee_id == employee.id,
                AttendanceRecordModel.attendance_date == date(2026, 6, 25),
            )
            .one()
        )

        assert record.status == AttendanceStatus.UNSCHEDULED
        assert record.is_unscheduled is True
        assert record.is_late is False
        assert record.is_early_departure is False
        assert record.late_minutes == 0
        assert record.early_departure_minutes == 0
        assert record.scheduled_start_datetime is None
        assert record.scheduled_end_datetime is None
    finally:
        db.close()


def test_seeded_justifications_are_one_per_attendance_record():
    Session = session_factory()
    db = Session()
    try:
        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).seed()
        db.commit()

        rows = (
            db.query(JustificationRequestModel.attendance_record_id)
            .join(EmployeeModel, EmployeeModel.id == JustificationRequestModel.employee_id)
            .filter(EmployeeModel.employee_number.in_(["DEMO002", "DEMO003", "DEMO004"]))
            .all()
        )
        attendance_ids = [row[0] for row in rows]
        assert len(attendance_ids) == 3
        assert len(set(attendance_ids)) == 3
    finally:
        db.close()


def test_cleanup_removes_only_demo_prefixed_records():
    Session = session_factory()
    db = Session()
    try:
        real_employee, real_attendance, real_embedding = seed_admin_and_real_employee(db)
        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).seed()
        db.commit()

        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).cleanup()
        db.commit()

        assert db.query(EmployeeModel).filter(EmployeeModel.employee_number.like("DEMO%")).count() == 0
        assert db.query(DepartmentModel).filter(DepartmentModel.name.like("DEMO_%")).count() == 0
        assert db.get(EmployeeModel, real_employee.id) is not None
        assert db.get(AttendanceRecordModel, real_attendance.id) is not None
        assert db.get(FaceEmbeddingModel, real_embedding.id) is not None
    finally:
        db.close()


def test_dry_run_can_be_rolled_back_without_persisting_demo_rows():
    Session = session_factory()
    db = Session()
    try:
        DemoDataSeeder(db, reference_date=date(2026, 6, 25)).seed()
        db.rollback()

        assert db.query(EmployeeModel).filter(EmployeeModel.employee_number.like("DEMO%")).count() == 0
    finally:
        db.close()
