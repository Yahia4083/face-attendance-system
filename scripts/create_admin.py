"""Seed an initial admin user.

Usage:
    python -m scripts.create_admin

Set ADMIN_PASSWORD in .env or the process environment before running.
ADMIN_EMAIL may also be set to override the default email address.
"""

import os
import sys

# Allow `app.*` imports when running as a script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import get_settings
from app.domain.enums.user_role import UserRole
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.security.password_hasher import hash_password


def create_admin() -> None:
    settings = get_settings()
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    admin_password = settings.ADMIN_PASSWORD

    if not admin_password.strip():
        raise SystemExit(
            "Set ADMIN_PASSWORD in .env or the process environment before creating an admin."
        )

    db = SessionLocal()
    try:
        existing_user = (
            db.query(UserModel)
            .filter(UserModel.email == admin_email)
            .first()
        )

        if existing_user is not None:
            print(f"[INFO] User already exists: {admin_email} (id={existing_user.id})")
            return

        admin_user = UserModel(
            email=admin_email,
            password_hash=hash_password(admin_password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print("[SUCCESS] Admin user created")
        print(f"  Email: {admin_email}")
        print(f"  User ID: {admin_user.id}")

    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Failed to create admin user: {exc}")
        raise SystemExit(1) from exc
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
