from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.user_role import UserRole
from app.domain.repositories.attendance_record_repository import AttendanceRecordFilters
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import (
    AttendanceRecordModel,
    DepartmentModel,
    EmployeeModel,
    UserModel,
)
from app.infrastructure.database.repositories.sql_attendance_record_repository import (
    SqlAttendanceRecordRepository,
)


def filter_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_filter_records(db):
    department_a = DepartmentModel(name="Engineering", is_active=True)
    department_b = DepartmentModel(name="Operations", is_active=True)
    user_a = UserModel(
        email="a@example.com",
        password_hash="not-used",
        role=UserRole.EMPLOYEE,
        is_active=True,
    )
    user_b = UserModel(
        email="b@example.com",
        password_hash="not-used",
        role=UserRole.EMPLOYEE,
        is_active=True,
    )
    db.add_all([department_a, department_b, user_a, user_b])
    db.flush()
    employee_a = EmployeeModel(
        user_id=user_a.id,
        department_id=department_a.id,
        full_name="Employee A",
        employee_number="EMP-A",
        is_active=True,
    )
    employee_b = EmployeeModel(
        user_id=user_b.id,
        department_id=department_b.id,
        full_name="Employee B",
        employee_number="EMP-B",
        is_active=True,
    )
    db.add_all([employee_a, employee_b])
    db.flush()
    db.add_all(
        [
            AttendanceRecordModel(
                employee_id=employee_a.id,
                attendance_date=date(2026, 7, 1),
                check_in_time=datetime(2026, 7, 1, 8, 20),
                status=AttendanceStatus.LATE,
                is_late=True,
                late_minutes=20,
            ),
            AttendanceRecordModel(
                employee_id=employee_b.id,
                attendance_date=date(2026, 7, 1),
                check_in_time=datetime(2026, 7, 1, 8, 0),
                check_out_time=datetime(2026, 7, 1, 16, 0),
                status=AttendanceStatus.PRESENT,
            ),
            AttendanceRecordModel(
                employee_id=employee_a.id,
                attendance_date=date(2026, 7, 2),
                check_in_time=datetime(2026, 7, 2, 9, 0),
                status=AttendanceStatus.UNSCHEDULED,
                is_unscheduled=True,
            ),
            AttendanceRecordModel(
                employee_id=employee_b.id,
                attendance_date=date(2026, 7, 3),
                check_in_time=datetime(2026, 7, 3, 8, 0),
                status=AttendanceStatus.MISSING_CHECKOUT,
                is_missing_checkout=True,
            ),
        ]
    )
    db.commit()
    return department_a, department_b, employee_a, employee_b


def test_attendance_filters_are_applied_before_pagination_and_count():
    db = filter_session()
    try:
        department_a, _, _, _ = seed_filter_records(db)
        repository = SqlAttendanceRecordRepository(db)
        filters = AttendanceRecordFilters(department_id=department_a.id)

        first_page = repository.list_records(filters=filters, page=1, page_size=1)
        second_page = repository.list_records(filters=filters, page=2, page_size=1)

        assert repository.count_records(filters=filters) == 2
        assert len(first_page) == 1
        assert len(second_page) == 1
        assert first_page[0].employee.department_id == department_a.id
        assert second_page[0].employee.department_id == department_a.id
    finally:
        db.close()


def test_attendance_date_employee_department_status_and_fact_filters():
    db = filter_session()
    try:
        department_a, department_b, employee_a, _ = seed_filter_records(db)
        repository = SqlAttendanceRecordRepository(db)

        assert repository.count_records(
            filters=AttendanceRecordFilters(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 2),
            )
        ) == 3
        assert repository.count_records(
            filters=AttendanceRecordFilters(employee_id=employee_a.id)
        ) == 2
        assert repository.count_records(
            filters=AttendanceRecordFilters(department_id=department_b.id)
        ) == 2
        assert repository.count_records(
            filters=AttendanceRecordFilters(status="LATE")
        ) == 1
        assert repository.count_records(
            filters=AttendanceRecordFilters(is_late=True)
        ) == 1
        assert repository.count_records(
            filters=AttendanceRecordFilters(is_late=False)
        ) == 3
        assert repository.count_records(
            filters=AttendanceRecordFilters(is_missing_checkout=True)
        ) == 1
        assert repository.count_records(
            filters=AttendanceRecordFilters(is_unscheduled=True)
        ) == 1
        assert repository.count_records(
            filters=AttendanceRecordFilters(
                department_id=department_a.id,
                is_unscheduled=True,
            )
        ) == 1
    finally:
        db.close()
