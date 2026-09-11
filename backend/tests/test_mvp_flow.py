from datetime import datetime, timedelta, timezone

from app.models.academic import Lecture
from app.models.attendance import AttendanceSession
from app.models.security import Cooldown
from app.services import attendance_service
from tests.conftest import auth_headers, make_class_setup


def _scan(client, professor_token, student_token, lecture_id):
    session_resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(lecture_id)},
        headers=auth_headers(professor_token["access_token"]),
    )
    assert session_resp.status_code == 201, session_resp.text
    live = client.get(
        f"/api/attendance/sessions/{session_resp.json()['id']}/live",
        headers=auth_headers(professor_token["access_token"]),
    )
    return client.post(
        "/api/attendance/scan",
        json={"token": live.json()["qr_payload"]},
        headers=auth_headers(student_token["access_token"]),
    ), session_resp.json()["id"]


# --- Ad-hoc session creation (spec #2) ----------------------------------------------------


def test_adhoc_session_creates_lecture_and_starts_attendance(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        "/api/attendance/sessions/adhoc",
        json={"class_division_id": str(setup["class_division_id"]), "duration_minutes": 30},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 201, resp.text
    session_id = resp.json()["id"]

    lecture = db_session.get(Lecture, resp.json()["lecture_id"])
    assert lecture.class_division_id == setup["class_division_id"]
    assert (lecture.scheduled_end - lecture.scheduled_start) == timedelta(minutes=30)

    live = client.get(
        f"/api/attendance/sessions/{session_id}/live", headers=auth_headers(professor_and_token["access_token"])
    )
    assert live.status_code == 200
    assert live.json()["qr_payload"] is not None


def test_adhoc_session_rejected_for_class_not_owned(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    from tests.conftest import login, register_professor

    register_professor(client, email="other-adhoc@college.edu")
    other_token = login(client, "other-adhoc@college.edu").json()

    resp = client.post(
        "/api/attendance/sessions/adhoc",
        json={"class_division_id": str(setup["class_division_id"]), "duration_minutes": 30},
        headers=auth_headers(other_token["access_token"]),
    )
    assert resp.status_code == 403


# --- Attendance sheet: same-day lectures must not collide (root cause of "scan disappears") -----


def test_attendance_sheet_keeps_separate_columns_for_same_day_lectures(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])

    # First lecture: scan recorded as present.
    resp1, _ = _scan(client, professor_and_token, student_and_token, setup["lecture_id"])
    assert resp1.status_code == 200, resp1.text

    # Second lecture, same class_division, same calendar day, no attendance recorded against it.
    now = datetime.now(timezone.utc)
    lecture2 = Lecture(
        class_division_id=setup["class_division_id"],
        topic="Second session",
        scheduled_start=now + timedelta(minutes=1),
        scheduled_end=now + timedelta(hours=1),
        room="Room 1",
    )
    db_session.add(lecture2)
    db_session.commit()

    today = now.date().isoformat()
    sheet = client.get(
        "/api/professor/attendance-sheet",
        params={"class_division_id": str(setup["class_division_id"]), "date_from": today, "date_to": today},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert sheet.status_code == 200, sheet.text
    body = sheet.json()

    assert len(body["columns"]) == 2
    col_ids = {c["lecture_id"] for c in body["columns"]}
    assert str(setup["lecture_id"]) in col_ids
    assert str(lecture2.id) in col_ids

    row = body["rows"][0]
    # The recorded lecture must show "present" and the other lecture must show no record —
    # NOT be silently overwritten by each other, which was the bug (cells keyed by date).
    assert row["cells"][str(setup["lecture_id"])]["status"] == "present"
    assert row["cells"][str(lecture2.id)]["status"] is None


# --- Server-side post-scan cooldown (spec #6/#7) ------------------------------------------


def test_successful_scan_creates_cooldown_row(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp, _ = _scan(client, professor_and_token, student_and_token, setup["lecture_id"])
    assert resp.status_code == 200, resp.text

    from app.core.time import ensure_utc

    cooldowns = (
        db_session.query(Cooldown).filter(Cooldown.student_id == setup["student_profile_id"]).all()
    )
    assert len(cooldowns) == 1
    assert cooldowns[0].reason == "attendance_marked"
    assert ensure_utc(cooldowns[0].expires_at) > datetime.now(timezone.utc)


def test_scan_against_different_lecture_blocked_by_post_scan_cooldown(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp1, _ = _scan(client, professor_and_token, student_and_token, setup["lecture_id"])
    assert resp1.status_code == 200

    # A second, different lecture in the same class — the per-lecture unique constraint
    # wouldn't block this on its own; the post-scan cooldown must.
    now = datetime.now(timezone.utc)
    lecture2 = Lecture(
        class_division_id=setup["class_division_id"],
        topic="Second session",
        scheduled_start=now,
        scheduled_end=now + timedelta(hours=1),
        room="Room 1",
    )
    db_session.add(lecture2)
    db_session.commit()

    resp2, _ = _scan(client, professor_and_token, student_and_token, lecture2.id)
    assert resp2.status_code == 423
    assert resp2.json()["detail"]["remaining_seconds"] > 0


def test_cooldown_status_reflects_post_scan_cooldown_after_refresh(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp, _ = _scan(client, professor_and_token, student_and_token, setup["lecture_id"])
    assert resp.status_code == 200

    status_resp = client.get("/api/students/me/cooldown", headers=auth_headers(student_and_token["access_token"]))
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["active"] is True
    assert body["reason"] == "attendance_marked"
    assert body["remaining_seconds"] > 0


def test_login_not_blocked_by_post_scan_cooldown(client, db_session, professor_and_token, student_and_token):
    """A short post-scan cooldown must not lock a student out of logging back in — only the
    voluntary-logout penalty should (see auth_service.login_user)."""
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp, _ = _scan(client, professor_and_token, student_and_token, setup["lecture_id"])
    assert resp.status_code == 200

    from tests.conftest import login

    relogin = login(client, "student@college.edu")
    assert relogin.status_code == 200


# --- Session expiry (spec #3) --------------------------------------------------------------


def test_scan_rejected_after_lecture_scheduled_end(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(
        db_session,
        professor_and_token["user_id"],
        student_and_token["user_id"],
        lecture_start=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    # make_class_setup sets scheduled_end = lecture_start + 1 hour, i.e. already in the past.
    session_resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(setup["lecture_id"])},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    from app.core.time import ensure_utc

    session_obj = db_session.get(AttendanceSession, session_id)
    lecture = db_session.get(Lecture, setup["lecture_id"])
    fresh_token = attendance_service.issue_token(db_session, session_obj)
    fresh_payload = attendance_service.encode_qr_payload(fresh_token)
    assert ensure_utc(lecture.scheduled_end) < datetime.now(timezone.utc)

    resp = client.post(
        "/api/attendance/scan",
        json={"token": fresh_payload},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 410
    assert "expired" in resp.json()["detail"].lower()

    db_session.refresh(session_obj)
    assert session_obj.status.value == "closed"
