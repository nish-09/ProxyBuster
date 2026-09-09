from datetime import timedelta

from app.models.security import Cooldown
from app.models.user import StudentProfile
from tests.conftest import auth_headers, login, make_class_setup, register_student
from app.core.time import utcnow


def test_logout_then_relogin_returns_423_with_remaining_seconds(client, student_and_token):
    logout_resp = client.post(
        "/api/auth/logout", headers=auth_headers(student_and_token["access_token"])
    )
    assert logout_resp.status_code == 204

    relogin = login(client, "student@college.edu")
    assert relogin.status_code == 423
    body = relogin.json()["detail"]
    assert body["remaining_seconds"] > 0


def test_cooldown_row_created_on_voluntary_logout(client, db_session, student_and_token):
    client.post("/api/auth/logout", headers=auth_headers(student_and_token["access_token"]))
    student_profile = db_session.query(StudentProfile).filter(
        StudentProfile.user_id == student_and_token["user_id"]
    ).first()
    cooldowns = db_session.query(Cooldown).filter(Cooldown.student_id == student_profile.id).all()
    assert len(cooldowns) == 1
    assert cooldowns[0].reason == "manual_logout"


def test_no_cooldown_created_without_voluntary_logout(client, db_session, student_and_token):
    student_profile = db_session.query(StudentProfile).filter(
        StudentProfile.user_id == student_and_token["user_id"]
    ).first()
    cooldowns = db_session.query(Cooldown).filter(Cooldown.student_id == student_profile.id).all()
    assert cooldowns == []


def test_scan_blocked_while_on_cooldown(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(setup["lecture_id"])},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    live = client.get(
        f"/api/attendance/sessions/{session_resp.json()['id']}/live",
        headers=auth_headers(professor_and_token["access_token"]),
    )

    db_session.add(
        Cooldown(
            student_id=setup["student_profile_id"],
            expires_at=utcnow() + timedelta(minutes=30),
            reason="manual_logout",
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/attendance/scan",
        json={"token": live.json()["qr_payload"]},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 423
    assert resp.json()["detail"]["remaining_seconds"] > 0


def test_cooldown_status_endpoint_reflects_active_cooldown(client, db_session):
    register_student(client, email="cooldown-check@college.edu", roll_number="R555")
    token = login(client, "cooldown-check@college.edu").json()["access_token"]

    from app.models.user import User

    user = db_session.query(User).filter(User.email == "cooldown-check@college.edu").first()
    profile = db_session.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    db_session.add(Cooldown(student_id=profile.id, expires_at=utcnow() + timedelta(minutes=10), reason="manual_logout"))
    db_session.commit()

    resp = client.get("/api/students/me/cooldown", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    assert resp.json()["remaining_seconds"] > 0
