"""Direct endpoint-level tests for routes that were previously only exercised indirectly (their
underlying service functions have unit tests — e.g. app/services/anomaly_service.py in
test_anomaly.py — but nothing ever called the actual HTTP route). Found via a full endpoint
inventory audit (dumping app.routes and cross-checking test files) as part of hardening this
codebase for production; each of these is real, pre-existing, previously-untested surface area.
"""
from app.models.security import DeviceSession, DeviceSessionStatus
from tests.conftest import auth_headers, login, make_class_setup, register_professor


def test_force_logout_revokes_the_students_active_session(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        f"/api/professor/students/{setup['student_profile_id']}/force-logout",
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 204

    db_session.expire_all()
    session_row = (
        db_session.query(DeviceSession)
        .filter(DeviceSession.user_id == student_and_token["user_id"])
        .order_by(DeviceSession.login_at.desc())
        .first()
    )
    assert session_row.status == DeviceSessionStatus.REVOKED

    # The revoked token must actually stop working, not just look revoked in the DB.
    denied = client.get("/api/students/me", headers=auth_headers(student_and_token["access_token"]))
    assert denied.status_code == 401


def test_force_logout_by_non_owning_professor_forbidden(client, db_session, professor_and_token, student_and_token):
    """A student outside a professor's own classes reads as 404, not 403 — an IDOR-safe pattern
    already used consistently across the professor-scoped endpoints (see
    professor_service._verify_student_in_scope): confirming existence via a 403 would let one
    professor enumerate which student IDs belong to a colleague's roster."""
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    register_professor(client, email="other-force-logout@college.edu")
    other = login(client, "other-force-logout@college.edu").json()
    resp = client.post(
        f"/api/professor/students/{setup['student_profile_id']}/force-logout", headers=auth_headers(other["access_token"])
    )
    assert resp.status_code == 404


def test_bunk_calculator_returns_projection(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        "/api/students/me/bunk-calculator",
        json={"class_division_id": str(setup["class_division_id"]), "required_pct": 75.0},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "classes_can_miss" in body and "projected_after_attending_1" in body


def test_bunk_calculator_rejects_class_the_student_is_not_enrolled_in(client, db_session, professor_and_token, student_and_token):
    import uuid

    make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        "/api/students/me/bunk-calculator",
        json={"class_division_id": str(uuid.uuid4()), "required_pct": 75.0},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 404


def test_my_sessions_lists_the_students_own_device_sessions(client, student_and_token):
    resp = client.get("/api/students/me/sessions", headers=auth_headers(student_and_token["access_token"]))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1  # at least the current login


def test_professor_analytics_mirrors_dashboard(client, professor_and_token):
    resp = client.get("/api/professor/analytics", headers=auth_headers(professor_and_token["access_token"]))
    assert resp.status_code == 200
    assert "active_subjects" in resp.json()


def test_professor_cooldowns_lists_active_cooldowns_for_own_roster(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    # Voluntary logout starts a cooldown for this student.
    client.post("/api/auth/logout", headers=auth_headers(student_and_token["access_token"]))

    resp = client.get("/api/professor/cooldowns", headers=auth_headers(professor_and_token["access_token"]))
    assert resp.status_code == 200
    assert any(c["student_id"] == str(setup["student_profile_id"]) for c in resp.json())


def test_professor_anomaly_scores_endpoint(client, db_session, professor_and_token, student_and_token):
    make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.get("/api/professor/anomaly-scores", headers=auth_headers(professor_and_token["access_token"]))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_professor_security_events_list_flag_and_dismiss(client, db_session, professor_and_token, student_and_token):
    make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    # student_and_token registers with the fixture's default email (see tests/conftest.py) — a
    # second login for that same account creates a real "concurrent_login" SecurityEvent.
    login(client, "student@college.edu")

    resp = client.get("/api/professor/security", headers=auth_headers(professor_and_token["access_token"]))
    assert resp.status_code == 200
    events = resp.json()
    assert any(e["event_type"] == "concurrent_login" for e in events)
    event_id = next(e["id"] for e in events if e["event_type"] == "concurrent_login")

    flagged = client.post(f"/api/professor/security/{event_id}/flag", headers=auth_headers(professor_and_token["access_token"]))
    assert flagged.status_code == 204

    dismissed = client.post(
        f"/api/professor/security/{event_id}/dismiss", headers=auth_headers(professor_and_token["access_token"])
    )
    assert dismissed.status_code == 204


def test_student_cannot_access_professor_endpoints_covered_by_this_file(client, student_and_token):
    for method, path in [
        ("get", "/api/professor/analytics"),
        ("get", "/api/professor/security"),
        ("get", "/api/professor/cooldowns"),
        ("get", "/api/professor/anomaly-scores"),
    ]:
        resp = getattr(client, method)(path, headers=auth_headers(student_and_token["access_token"]))
        assert resp.status_code == 403, f"{method.upper()} {path} should be professor-only"
