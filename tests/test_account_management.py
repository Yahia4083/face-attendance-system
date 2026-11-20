import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.application.dto.auth_dto import (
    ChangeOwnPasswordRequest,
    LoginRequest,
    ResetEmployeePasswordRequest,
)
from app.application.dto.employee_dto import UpdateEmployeeRequest
from app.application.use_cases.auth.login_user import LoginUser
from app.application.use_cases.auth.password_management import (
    ChangeOwnPassword,
    ResetEmployeePassword,
)
from app.application.use_cases.employees.update_employee import UpdateEmployee
from app.application.use_cases.employees.get_employee import GetEmployeeByNumber
from app.application.use_cases.exceptions import BadRequestError, ConflictError
from app.domain.enums.user_role import UserRole
from app.infrastructure.security.jwt_service import decode_access_token
from app.infrastructure.security.jwt_service import create_access_token
from app.infrastructure.security.password_hasher import hash_password, verify_password
from app.infrastructure.security.permissions import (
    get_current_user,
    require_admin,
    require_employee,
)
from app.dependencies import (
    get_audit_repository,
    get_employee_repository,
    get_user_repository,
)
from app.main import create_app


class FakeAuditRepo:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


class FakeUserRepo:
    def __init__(self, users):
        self.users = {user.id: user for user in users}

    def get_by_id(self, user_id):
        return self.users.get(user_id)

    def get_by_email(self, email):
        normalized = email.strip().lower()
        return next(
            (
                user
                for user in self.users.values()
                if user.email.strip().lower() == normalized
            ),
            None,
        )

    def replace_password(self, user_id, *, password_hash, must_change_password):
        user = self.get_by_id(user_id)
        if user is None:
            return None
        user.password_hash = password_hash
        user.must_change_password = must_change_password
        user.token_version += 1
        return user


def employee_user(
    *,
    user_id=2,
    email="employee@example.com",
    password="OldPass1!",
    must_change_password=False,
):
    return SimpleNamespace(
        id=user_id,
        email=email,
        password_hash=hash_password(password),
        role=UserRole.EMPLOYEE,
        is_active=True,
        token_version=0,
        must_change_password=must_change_password,
    )


def test_employee_changes_password_and_invalidates_existing_token():
    user = employee_user()
    users = FakeUserRepo([user])
    audit = FakeAuditRepo()
    old_hash = user.password_hash
    old_token = LoginUser(users, audit).execute(
        LoginRequest(email=user.email, password="OldPass1!")
    ).access_token

    updated = ChangeOwnPassword(users, audit).execute(
        ChangeOwnPasswordRequest(
            user_id=user.id,
            current_password="OldPass1!",
            new_password="NewPass2@",
            confirm_password="NewPass2@",
        )
    )

    assert updated.password_hash != old_hash
    assert updated.password_hash != "NewPass2@"
    assert verify_password("NewPass2@", updated.password_hash)
    assert updated.token_version == 1
    assert updated.must_change_password is False
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=old_token, user_repo=users)
    assert exc_info.value.status_code == 401

    password_audit = audit.entries[-1]
    serialized = json.dumps(password_audit)
    assert password_audit["action"] == "CHANGE_OWN_PASSWORD"
    assert "OldPass1!" not in serialized
    assert "NewPass2@" not in serialized
    assert old_hash not in serialized


def test_login_token_contains_current_version_and_forced_change_state():
    user = employee_user(must_change_password=True)
    user.token_version = 4
    result = LoginUser(FakeUserRepo([user]), FakeAuditRepo()).execute(
        LoginRequest(email=user.email, password="OldPass1!")
    )

    payload = decode_access_token(result.access_token)
    assert payload["ver"] == 4
    assert result.must_change_password is True


def test_wrong_current_password_is_rejected():
    user = employee_user()
    with pytest.raises(BadRequestError, match="Current password is incorrect"):
        ChangeOwnPassword(FakeUserRepo([user]), FakeAuditRepo()).execute(
            ChangeOwnPasswordRequest(
                user_id=user.id,
                current_password="WrongPass1!",
                new_password="NewPass2@",
                confirm_password="NewPass2@",
            )
        )


@pytest.mark.parametrize(
    ("new_password", "confirmation", "message"),
    [
        ("NewPass2@", "Different2@", "confirmation do not match"),
        ("Short1!", "Short1!", "at least 8"),
        ("alllowercase1", "alllowercase1", "uppercase letter"),
        ("OldPass1!", "OldPass1!", "different from the current"),
    ],
)
def test_invalid_new_password_is_rejected(new_password, confirmation, message):
    user = employee_user()
    with pytest.raises(BadRequestError, match=message):
        ChangeOwnPassword(FakeUserRepo([user]), FakeAuditRepo()).execute(
            ChangeOwnPasswordRequest(
                user_id=user.id,
                current_password="OldPass1!",
                new_password=new_password,
                confirm_password=confirmation,
            )
        )


def test_admin_resets_employee_password_without_logging_secrets():
    user = employee_user()
    employee = SimpleNamespace(id=9, user_id=user.id, user=user, is_active=True)
    employee_repo = SimpleNamespace(get_by_id=lambda employee_id: employee if employee_id == 9 else None)
    audit = FakeAuditRepo()

    updated = ResetEmployeePassword(
        employee_repo=employee_repo,
        user_repo=FakeUserRepo([user]),
        audit_repo=audit,
    ).execute(
        ResetEmployeePasswordRequest(
            employee_id=9,
            new_password="TempPass3#",
            confirm_password="TempPass3#",
            require_password_change=True,
            actor_user_id=1,
        )
    )

    assert verify_password("TempPass3#", updated.password_hash)
    assert updated.must_change_password is True
    assert updated.token_version == 1
    serialized = json.dumps(audit.entries[-1])
    assert audit.entries[-1]["action"] == "ADMIN_RESET_EMPLOYEE_PASSWORD"
    assert "TempPass3#" not in serialized
    assert updated.password_hash not in serialized


def test_non_admin_cannot_reset_and_forced_employee_cannot_use_normal_routes():
    employee = employee_user(must_change_password=True)
    with pytest.raises(HTTPException) as admin_error:
        require_admin(current_user=employee)
    assert admin_error.value.status_code == 403

    with pytest.raises(HTTPException) as forced_error:
        require_employee(current_user=employee)
    assert forced_error.value.status_code == 403
    assert "must change your password" in forced_error.value.detail.lower()


def test_employee_password_reset_endpoint_requires_admin_role():
    user = employee_user()
    employee = SimpleNamespace(id=9, user_id=user.id, user=user, is_active=True)
    application = create_app()
    application.dependency_overrides[get_user_repository] = lambda: FakeUserRepo([user])
    application.dependency_overrides[get_employee_repository] = lambda: SimpleNamespace(
        get_by_id=lambda employee_id: employee if employee_id == 9 else None
    )
    application.dependency_overrides[get_audit_repository] = FakeAuditRepo
    token = create_access_token({"sub": str(user.id), "ver": 0})

    with TestClient(application) as client:
        response = client.patch(
            "/employees/9/account/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "new_password": "TempPass3#",
                "confirm_password": "TempPass3#",
                "require_password_change": True,
            },
        )

    assert response.status_code == 403


def test_admin_password_reset_endpoint_returns_no_password_data():
    admin = SimpleNamespace(
        id=1,
        email="admin@example.com",
        password_hash=hash_password("AdminPass1!"),
        role=UserRole.ADMIN,
        is_active=True,
        token_version=0,
        must_change_password=False,
    )
    user = employee_user()
    employee = SimpleNamespace(id=9, user_id=user.id, user=user, is_active=True)
    users = FakeUserRepo([admin, user])
    audit = FakeAuditRepo()
    application = create_app()
    application.dependency_overrides[get_user_repository] = lambda: users
    application.dependency_overrides[get_employee_repository] = lambda: SimpleNamespace(
        get_by_id=lambda employee_id: employee if employee_id == 9 else None
    )
    application.dependency_overrides[get_audit_repository] = lambda: audit
    token = create_access_token({"sub": str(admin.id), "ver": 0})

    with TestClient(application) as client:
        response = client.patch(
            "/employees/9/account/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "new_password": "TempPass3#",
                "confirm_password": "TempPass3#",
                "require_password_change": True,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "employee_id": 9,
        "user_id": user.id,
        "require_password_change": True,
        "message": "Employee password was reset successfully.",
    }
    assert "TempPass3#" not in response.text
    assert "password_hash" not in response.text


class FakeDepartmentRepo:
    def __init__(self):
        self.departments = {
            10: SimpleNamespace(id=10, name="Engineering", is_active=True),
            20: SimpleNamespace(id=20, name="Operations", is_active=True),
        }

    def get_by_id(self, department_id):
        return self.departments.get(department_id)


class FakeEmployeeRepo:
    def __init__(self, employee):
        self.employee = employee

    def get_by_id(self, employee_id):
        return self.employee if employee_id == self.employee.id else None

    def update(self, employee_id, *, email, full_name, phone, position, department_id):
        employee = self.get_by_id(employee_id)
        employee.user.email = email
        employee.full_name = full_name
        employee.phone = phone
        employee.position = position
        employee.department_id = department_id
        employee.department = FakeDepartmentRepo().get_by_id(department_id)
        return employee


def editable_employee():
    user = employee_user(email="first@example.com")
    department = FakeDepartmentRepo().get_by_id(10)
    employee = SimpleNamespace(
        id=5,
        user_id=user.id,
        user=user,
        department_id=department.id,
        department=department,
        full_name="First Name",
        employee_number="EMP005",
        phone=None,
        position="Developer",
        is_active=True,
    )
    return user, employee


def test_admin_updates_employee_email_and_profile_without_changing_password():
    user, employee = editable_employee()
    original_hash = user.password_hash
    audit = FakeAuditRepo()
    updated = UpdateEmployee(
        employee_repo=FakeEmployeeRepo(employee),
        user_repo=FakeUserRepo([user]),
        department_repo=FakeDepartmentRepo(),
        audit_repo=audit,
    ).execute(
        UpdateEmployeeRequest(
            employee_id=employee.id,
            email="Updated@Example.com",
            full_name="Updated Name",
            phone="+218900000000",
            position="Senior Developer",
            department_id=20,
            actor_user_id=1,
        )
    )

    assert updated.user.email == "updated@example.com"
    assert updated.full_name == "Updated Name"
    assert updated.department_id == 20
    assert updated.user.password_hash == original_hash
    assert audit.entries[-1]["action"] == "UPDATE_EMPLOYEE"
    assert "password" not in str(audit.entries[-1]).lower()


def test_duplicate_employee_email_is_rejected_case_insensitively():
    user, employee = editable_employee()
    duplicate = employee_user(user_id=7, email="TAKEN@example.com")
    use_case = UpdateEmployee(
        employee_repo=FakeEmployeeRepo(employee),
        user_repo=FakeUserRepo([user, duplicate]),
        department_repo=FakeDepartmentRepo(),
        audit_repo=FakeAuditRepo(),
    )

    with pytest.raises(ConflictError, match="already used"):
        use_case.execute(
            UpdateEmployeeRequest(
                employee_id=employee.id,
                email="taken@EXAMPLE.com",
                full_name=employee.full_name,
                phone=None,
                position=employee.position,
                department_id=employee.department_id,
                actor_user_id=1,
            )
        )


def test_employee_number_lookup_returns_only_the_exact_employee():
    _, employee = editable_employee()
    repository = SimpleNamespace(
        get_by_employee_number=lambda number: employee
        if number.strip().lower() == employee.employee_number.lower()
        else None
    )

    assert GetEmployeeByNumber(repository).execute(" emp005 ") is employee
