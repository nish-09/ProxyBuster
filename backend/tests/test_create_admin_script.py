"""Tests for scripts/create_admin.py's core logic. There is no API endpoint to hit here by
design (see PROJECT decision: no public /register-admin route) — these call the same
create_admin_user() function the CLI calls, directly against the test database."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.create_admin import AdminBootstrapError, create_admin_user  # noqa: E402

from app.core.security import verify_password  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


def test_create_admin_user_creates_admin_role_user(db_session):
    user = create_admin_user(db_session, email="new.admin@example.test", password="StrongPass123!", full_name="New Admin")
    assert user.role == UserRole.ADMIN
    assert user.email == "new.admin@example.test"

    stored = db_session.query(User).filter(User.email == "new.admin@example.test").first()
    assert stored is not None
    assert stored.role == UserRole.ADMIN


def test_create_admin_user_hashes_password_with_passlib_bcrypt(db_session):
    user = create_admin_user(db_session, email="hash.check@example.test", password="StrongPass123!", full_name="Hash Check")
    assert user.password_hash != "StrongPass123!"
    assert user.password_hash.startswith("$2b$") or user.password_hash.startswith("$2a$")
    assert verify_password("StrongPass123!", user.password_hash)
    assert not verify_password("WrongPassword!", user.password_hash)


def test_create_admin_user_rejects_duplicate_email(db_session):
    create_admin_user(db_session, email="dupe.admin@example.test", password="StrongPass123!", full_name="First")
    with pytest.raises(AdminBootstrapError, match="already exists"):
        create_admin_user(db_session, email="dupe.admin@example.test", password="AnotherPass123!", full_name="Second")

    # Only one row should exist — the failed second call must not have partially written anything.
    count = db_session.query(User).filter(User.email == "dupe.admin@example.test").count()
    assert count == 1


def test_create_admin_user_rejects_email_already_used_by_other_role(db_session, student_and_token):
    with pytest.raises(AdminBootstrapError, match="already exists"):
        create_admin_user(db_session, email="student@college.edu", password="StrongPass123!", full_name="Sneaky")


def test_create_admin_user_rejects_short_password(db_session):
    with pytest.raises(AdminBootstrapError, match="at least 8 characters"):
        create_admin_user(db_session, email="shortpw@example.test", password="short", full_name="Short PW")


def test_create_admin_user_rejects_invalid_email(db_session):
    with pytest.raises(AdminBootstrapError, match="Invalid email"):
        create_admin_user(db_session, email="not-an-email", password="StrongPass123!", full_name="Bad Email")


def test_created_admin_can_log_in_and_hit_admin_endpoints(client, db_session):
    create_admin_user(db_session, email="loginflow.admin@example.test", password="StrongPass123!", full_name="Login Flow")

    login_resp = client.post(
        "/api/auth/login", json={"email": "loginflow.admin@example.test", "password": "StrongPass123!"}
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["role"] == "admin"

    token = login_resp.json()["access_token"]
    resp = client.get("/api/admin/students", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
