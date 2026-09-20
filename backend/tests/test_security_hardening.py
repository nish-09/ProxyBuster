"""Regression tests for the production-readiness security audit."""
import pytest

from tests.conftest import auth_headers, login, register_professor, register_student


# --- Privilege escalation via public registration --------------------------------------


@pytest.mark.parametrize("extra", [{}, {"department": "x"}, {"department": "x", "invite_code": "test-professor-invite-code"}])
def test_public_registration_can_never_create_an_admin(client, extra):
    resp = client.post(
        "/api/auth/register",
        json={"email": "evil@college.edu", "password": "Password123!", "full_name": "Evil", "role": "admin", **extra},
    )
    assert resp.status_code == 403
    assert login(client, "evil@college.edu").status_code == 401


def test_professor_registration_requires_invite_code(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "p@college.edu",
            "password": "Password123!",
            "full_name": "P",
            "role": "professor",
            "department": "CS",
            "invite_code": "wrong",
        },
    )
    assert resp.status_code == 403


def test_student_self_registration_can_be_disabled(client, monkeypatch):
    from app.services import auth_service

    monkeypatch.setattr(auth_service.settings, "allow_public_student_registration", False)
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "s@college.edu",
            "password": "Password123!",
            "full_name": "S",
            "role": "student",
            "roll_number": "R1",
            "program": "CS",
            "semester": 1,
        },
    )
    assert resp.status_code == 403


def test_duplicate_roll_number_is_a_409_not_a_500(client):
    register_student(client, email="a@college.edu", roll_number="SAME")
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "b@college.edu",
            "password": "Password123!",
            "full_name": "B",
            "role": "student",
            "roll_number": "SAME",
            "program": "CS",
            "semester": 1,
        },
    )
    assert resp.status_code == 409


# --- Email handling ---------------------------------------------------------------------


def test_email_is_case_insensitive(client):
    register_student(client, email="Mixed.Case@College.edu")
    assert login(client, "mixed.case@college.edu").status_code == 200
    assert login(client, "MIXED.CASE@COLLEGE.EDU").status_code == 200
    dup = client.post(
        "/api/auth/register",
        json={
            "email": "mixed.case@college.edu",
            "password": "Password123!",
            "full_name": "Dup",
            "role": "student",
            "roll_number": "R2",
            "program": "CS",
            "semester": 1,
        },
    )
    assert dup.status_code == 409


# --- Error responses never leak secrets ---------------------------------------------------


def test_validation_error_does_not_echo_the_submitted_password(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "SuperSecretPw1!", "full_name": "X", "role": "student"},
    )
    assert resp.status_code == 422
    assert "SuperSecretPw1!" not in resp.text
    assert isinstance(resp.json()["detail"], list)


def test_unauthenticated_and_garbage_tokens_get_401_not_500(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers("garbage")).status_code == 401
    assert client.get("/api/students/me/dashboard").status_code == 401


def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"


# --- Role separation ----------------------------------------------------------------------


def test_student_and_professor_cannot_reach_admin_endpoints(client, professor_and_token, student_and_token):
    for token in (professor_and_token, student_and_token):
        headers = auth_headers(token["access_token"])
        assert client.get("/api/admin/students", headers=headers).status_code == 403
        assert client.post("/api/admin/subjects", json={"code": "X", "name": "X"}, headers=headers).status_code == 403
    assert client.get("/api/admin/students").status_code == 401


def test_student_cannot_call_professor_or_session_control_endpoints(client, student_and_token, professor_and_token):
    headers = auth_headers(student_and_token["access_token"])
    assert client.get("/api/professor/dashboard", headers=headers).status_code == 403
    assert client.get("/api/professor/attendance-sheet", params={"class_division_id": "x"}, headers=headers).status_code in (403, 422)
    assert client.post("/api/attendance/sessions", json={"lecture_id": "00000000-0000-0000-0000-000000000000"}, headers=headers).status_code == 403
    assert client.post("/api/attendance/manual", json={}, headers=headers).status_code in (403, 422)


def test_professor_cannot_scan(client, professor_and_token):
    headers = auth_headers(professor_and_token["access_token"])
    assert client.post("/api/attendance/scan", json={"token": "abc"}, headers=headers).status_code == 403


def test_deactivated_user_token_stops_working(client, admin_and_token):
    register_professor(client, email="temp@college.edu")
    prof_token = login(client, "temp@college.edu").json()
    profs = client.get("/api/admin/professors", headers=auth_headers(admin_and_token["access_token"])).json()
    prof_id = next(p["id"] for p in profs if p["email"] == "temp@college.edu")
    resp = client.patch(
        f"/api/admin/professors/{prof_id}",
        json={"is_active": False},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert resp.status_code == 200
    assert client.get("/api/professor/dashboard", headers=auth_headers(prof_token["access_token"])).status_code == 401
    assert login(client, "temp@college.edu").status_code == 403


# --- Production config guard --------------------------------------------------------------


def test_production_refuses_weak_or_shared_secrets():
    from pydantic import ValidationError

    from app.core.config import Settings

    good = "x" * 40
    base = dict(database_url="postgresql://u:p@h/db", jwt_secret=good, qr_signing_secret="y" * 40, cors_origins="https://a.example")
    Settings(environment="production", **base)  # a sound config is accepted

    for bad in (
        {"jwt_secret": "short"},
        {"jwt_secret": "change-me-to-a-long-random-string-xxxxxxxxxx"},
        {"qr_signing_secret": good},  # same as JWT secret
        {"cors_origins": "*"},
        {"database_url": "sqlite:///x.db"},
    ):
        with pytest.raises(ValidationError):
            Settings(environment="production", **{**base, **bad})
