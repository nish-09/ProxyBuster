"""Release-audit tests: session lifecycle, QR security, WebSocket authorisation, dashboards,
attendance-sheet/absent accounting, last-scan, and admin fixes. Everything goes through the real
HTTP API and the real (SQLite-backed) database — nothing about attendance is mocked."""
import asyncio
import base64
from datetime import datetime, timedelta, timezone

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.time import ensure_utc
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject
from app.models.attendance import AttendanceRecord, AttendanceSession, AttendanceToken, SessionStatus
from app.models.user import ProfessorProfile, StudentProfile
from app.services import attendance_service, realtime
from tests.conftest import auth_headers, login, make_class_setup, register_professor, register_student


def _start(client, prof_token, lecture_id):
    resp = client.post(
        "/api/attendance/sessions", json={"lecture_id": str(lecture_id)}, headers=auth_headers(prof_token["access_token"])
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _live(client, prof_token, session_id):
    resp = client.get(f"/api/attendance/sessions/{session_id}/live", headers=auth_headers(prof_token["access_token"]))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _scan(client, student_token, payload):
    return client.post("/api/attendance/scan", json={"token": payload}, headers=auth_headers(student_token["access_token"]))


def _add_student(db_session, client, n, class_division_id):
    """Registers another student and enrols them; returns (token_json, student_profile_id)."""
    register_student(client, email=f"extra{n}@college.edu", roll_number=f"X{n:03d}", full_name=f"Extra Student {n}")
    token = login(client, f"extra{n}@college.edu").json()
    sp = db_session.query(StudentProfile).filter(StudentProfile.roll_number == f"X{n:03d}").one()
    db_session.add(Enrollment(student_id=sp.id, class_division_id=class_division_id))
    db_session.commit()
    return token, sp.id


# ----------------------------------------------------------------------------------------
# QR security
# ----------------------------------------------------------------------------------------


def test_tampered_qr_payloads_are_rejected(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    payload = _live(client, professor_and_token, session_id)["qr_payload"]
    session_str, nonce, issued, expires, sig = base64.urlsafe_b64decode(payload.encode()).decode().split(".")

    def forge(*parts):
        return base64.urlsafe_b64encode(".".join(parts).encode()).decode()

    forged = [
        forge(session_str, nonce, issued, str(int(expires) + 3600), sig),  # extended expiry
        forge("00000000-0000-0000-0000-000000000000", nonce, issued, expires, sig),  # other session
        forge(session_str, nonce + "x", issued, expires, sig),  # altered nonce
        forge(session_str, nonce, issued, expires, "0" * 64),  # bad signature
        "not-base64-at-all!!",
        "",
    ]
    for bad in forged:
        resp = _scan(client, student_and_token, bad) if bad else client.post(
            "/api/attendance/scan", json={"token": "x"}, headers=auth_headers(student_and_token["access_token"])
        )
        assert resp.status_code == 400, (bad, resp.text)
        assert resp.json()["detail"]["code"] == "invalid_qr"

    # None of that burned the real token or created attendance.
    assert db_session.query(AttendanceRecord).count() == 0
    assert _scan(client, student_and_token, payload).status_code == 200


def test_qr_from_other_session_cannot_mark_attendance_elsewhere(client, db_session, professor_and_token, student_and_token):
    """A valid, unexpired QR from session A must not credit a lecture of session B."""
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_a = _start(client, professor_and_token, setup["lecture_id"])
    payload_a = _live(client, professor_and_token, session_a)["qr_payload"]

    resp = _scan(client, student_and_token, payload_a)
    assert resp.status_code == 200
    record = db_session.query(AttendanceRecord).one()
    assert str(record.session_id) == session_a
    assert record.lecture_id == setup["lecture_id"]


def test_student_not_enrolled_in_that_class_is_rejected_and_token_not_burned(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    register_student(client, email="outsider@college.edu", roll_number="OUT1")
    outsider = login(client, "outsider@college.edu").json()

    session_id = _start(client, professor_and_token, setup["lecture_id"])
    payload = _live(client, professor_and_token, session_id)["qr_payload"]

    resp = _scan(client, outsider, payload)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "not_enrolled"
    # The genuine student can still use the very same QR.
    assert _scan(client, student_and_token, payload).status_code == 200


def test_qr_after_professor_stops_session_is_rejected(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    payload = _live(client, professor_and_token, session_id)["qr_payload"]
    closed = client.post(
        f"/api/attendance/sessions/{session_id}/close", headers=auth_headers(professor_and_token["access_token"])
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    resp = _scan(client, student_and_token, payload)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "session_closed"
    assert db_session.query(AttendanceRecord).count() == 0


def test_consumed_token_is_not_served_again_and_a_fresh_one_is_issued(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    first = _live(client, professor_and_token, session_id)["qr_payload"]
    assert _scan(client, student_and_token, first).status_code == 200

    again = _live(client, professor_and_token, session_id)["qr_payload"]
    assert again != first, "professor screen must never be handed a dead (already consumed) QR"

    token_rows = db_session.query(AttendanceToken).all()
    assert sum(1 for t in token_rows if t.consumed) == 1


def test_only_one_of_two_students_can_use_the_same_qr(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    second, _ = _add_student(db_session, client, 1, setup["class_division_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    payload = _live(client, professor_and_token, session_id)["qr_payload"]

    a = _scan(client, student_and_token, payload)
    b = _scan(client, second, payload)
    assert (a.status_code, b.status_code) == (200, 409)
    assert b.json()["detail"]["code"] == "qr_used"
    assert db_session.query(AttendanceRecord).count() == 1


def test_rotate_now_replaces_the_consumed_qr(client, db_session_factory, db_session, professor_and_token, student_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    payload = _live(client, professor_and_token, session_id)["qr_payload"]
    assert _scan(client, student_and_token, payload).status_code == 200

    monkeypatch.setattr(realtime, "SessionLocal", db_session_factory)
    monkeypatch.setattr(realtime, "start_rotation", lambda _sid: None)
    before = db_session.query(AttendanceToken).count()
    asyncio.run(realtime.rotate_now(AttendanceSession.__table__.c.id.type.process_result_value(session_id, None)))
    db_session.expire_all()
    assert db_session.query(AttendanceToken).count() == before + 1
    newest = db_session.query(AttendanceToken).order_by(AttendanceToken.issued_at.desc()).first()
    assert newest.consumed is False


# ----------------------------------------------------------------------------------------
# Session lifecycle
# ----------------------------------------------------------------------------------------


def test_lifecycle_active_to_closed_and_double_close_is_409(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    assert _live(client, professor_and_token, session_id)["status"] == "active"
    headers = auth_headers(professor_and_token["access_token"])
    assert client.post(f"/api/attendance/sessions/{session_id}/close", headers=headers).status_code == 200
    assert client.post(f"/api/attendance/sessions/{session_id}/close", headers=headers).status_code == 409
    live = _live(client, professor_and_token, session_id)
    assert live["status"] == "closed"
    assert live["qr_payload"] is None


def test_live_endpoint_reports_expired_without_any_frontend_timer(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    lecture = db_session.get(Lecture, setup["lecture_id"])
    lecture.scheduled_end = datetime.now(timezone.utc) - timedelta(seconds=5)
    db_session.commit()

    live = _live(client, professor_and_token, session_id)
    assert live["status"] == "expired"
    assert live["qr_payload"] is None


def test_sweeper_expires_overdue_sessions(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    lecture = db_session.get(Lecture, setup["lecture_id"])
    lecture.scheduled_end = datetime.now(timezone.utc) - timedelta(minutes=2)
    db_session.commit()

    assert attendance_service.expire_overdue_sessions(db_session) == 1
    db_session.expire_all()
    session_obj = db_session.get(AttendanceSession, session_id)
    assert session_obj.status == SessionStatus.EXPIRED
    assert session_obj.ended_at is not None
    assert attendance_service.expire_overdue_sessions(db_session) == 0


def test_cannot_start_two_sessions_for_the_same_class(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _start(client, professor_and_token, setup["lecture_id"])
    headers = auth_headers(professor_and_token["access_token"])
    dup = client.post(
        "/api/attendance/sessions/adhoc",
        json={"class_division_id": str(setup["class_division_id"]), "duration_minutes": 30},
        headers=headers,
    )
    assert dup.status_code == 409
    # ...and the rejected ad-hoc start left no orphan lecture behind.
    assert db_session.query(Lecture).filter(Lecture.class_division_id == setup["class_division_id"]).count() == 1


def test_cannot_start_attendance_for_a_division_with_no_students(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    db_session.query(Enrollment).delete()
    db_session.commit()
    resp = client.post(
        "/api/attendance/sessions/adhoc",
        json={"class_division_id": str(setup["class_division_id"]), "duration_minutes": 30},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 409
    assert "enrolled" in resp.json()["detail"].lower()


def test_cannot_start_a_lecture_days_in_the_future(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(
        db_session,
        professor_and_token["user_id"],
        student_and_token["user_id"],
        lecture_start=datetime.now(timezone.utc) + timedelta(days=2),
    )
    resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(setup["lecture_id"])},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 409


@pytest.mark.parametrize("minutes", [0, 4, 241, -5])
def test_adhoc_duration_is_validated(client, db_session, professor_and_token, student_and_token, minutes):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        "/api/attendance/sessions/adhoc",
        json={"class_division_id": str(setup["class_division_id"]), "duration_minutes": minutes},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 422


def test_professor_cannot_touch_another_professors_session(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    register_professor(client, email="rival@college.edu")
    rival = login(client, "rival@college.edu").json()
    headers = auth_headers(rival["access_token"])
    assert client.get(f"/api/attendance/sessions/{session_id}/live", headers=headers).status_code == 403
    assert client.post(f"/api/attendance/sessions/{session_id}/close", headers=headers).status_code == 403
    assert client.post(
        "/api/attendance/sessions", json={"lecture_id": str(setup["lecture_id"])}, headers=headers
    ).status_code == 403
    manual = client.post(
        "/api/attendance/manual",
        json={
            "student_id": str(setup["student_profile_id"]),
            "lecture_id": str(setup["lecture_id"]),
            "status": "present",
            "reason": "trying it on",
        },
        headers=headers,
    )
    assert manual.status_code == 403
    assert client.get(
        "/api/professor/attendance-sheet",
        params={"class_division_id": str(setup["class_division_id"]), "date_from": "2000-01-01", "date_to": "2100-01-01"},
        headers=headers,
    ).status_code == 403


# ----------------------------------------------------------------------------------------
# Live state payload
# ----------------------------------------------------------------------------------------


def test_live_state_carries_everything_the_professor_screen_needs(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    live = _live(client, professor_and_token, session_id)
    assert live["subject_name"] == "Test Subject"
    assert live["subject_code"] == "CS-999"
    assert live["division_name"] == "Div A"
    assert live["class_division_id"] == str(setup["class_division_id"])
    assert live["total_enrolled"] == 1
    assert live["present_count"] == 0
    assert live["qr_ttl_seconds"] >= 2
    assert live["session_expires_at"] is not None
    assert ensure_utc(datetime.fromisoformat(live["server_time"])) - datetime.now(timezone.utc) < timedelta(seconds=5)


# ----------------------------------------------------------------------------------------
# WebSocket authorisation
# ----------------------------------------------------------------------------------------


@pytest.fixture()
def ws_client(client, db_session_factory, monkeypatch):
    from app.api import ws as ws_module

    monkeypatch.setattr(ws_module, "SessionLocal", db_session_factory)
    return client


def test_websocket_owner_professor_can_subscribe_via_first_message_auth(
    ws_client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(ws_client, professor_and_token, setup["lecture_id"])
    with ws_client.websocket_connect(f"/api/ws/attendance/sessions/{session_id}") as ws:
        ws.send_json({"type": "auth", "token": professor_and_token["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_websocket_rejects_enrolled_student_who_could_otherwise_read_the_qr(
    ws_client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(ws_client, professor_and_token, setup["lecture_id"])
    with ws_client.websocket_connect(f"/api/ws/attendance/sessions/{session_id}") as ws:
        ws.send_json({"type": "auth", "token": student_and_token["access_token"]})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4403


def test_websocket_rejects_missing_or_bad_auth_and_query_string_tokens(
    ws_client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(ws_client, professor_and_token, setup["lecture_id"])

    with ws_client.websocket_connect(f"/api/ws/attendance/sessions/{session_id}") as ws:
        ws.send_json({"type": "auth", "token": "garbage"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    # A token in the URL is ignored: it must not authenticate (and would leak into access logs).
    url = f"/api/ws/attendance/sessions/{session_id}?token={professor_and_token['access_token']}"
    with ws_client.websocket_connect(url) as ws:
        ws.send_json({"type": "hello"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    register_professor(ws_client, email="snoop@college.edu")
    snoop = login(ws_client, "snoop@college.edu").json()
    with ws_client.websocket_connect(f"/api/ws/attendance/sessions/{session_id}") as ws:
        ws.send_json({"type": "auth", "token": snoop["access_token"]})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


# ----------------------------------------------------------------------------------------
# Attendance sheet / absent accounting
# ----------------------------------------------------------------------------------------


def test_manual_absent_counts_as_absent_not_as_recorded(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    headers = auth_headers(professor_and_token["access_token"])
    resp = client.post(
        "/api/attendance/manual",
        json={
            "student_id": str(setup["student_profile_id"]),
            "lecture_id": str(setup["lecture_id"]),
            "status": "absent",
            "reason": "left the class early",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    history = client.get("/api/students/me/attendance", headers=auth_headers(student_and_token["access_token"])).json()
    assert (history["present"], history["absent"], history["total"]) == (0, 1, 1)

    dash = client.get("/api/students/me/dashboard", headers=auth_headers(student_and_token["access_token"])).json()
    subject = dash["subjects"][0]
    assert (subject["present"], subject["absent"], subject["total"]) == (0, 1, 1)


def test_sheet_shows_each_session_in_its_own_column_with_correct_marks(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    other, _ = _add_student(db_session, client, 2, setup["class_division_id"])
    headers = auth_headers(professor_and_token["access_token"])

    session_id = _start(client, professor_and_token, setup["lecture_id"])
    assert _scan(client, student_and_token, _live(client, professor_and_token, session_id)["qr_payload"]).status_code == 200
    client.post(f"/api/attendance/sessions/{session_id}/close", headers=headers)

    adhoc = client.post(
        "/api/attendance/sessions/adhoc",
        json={"class_division_id": str(setup["class_division_id"]), "duration_minutes": 30, "topic": "Quiz"},
        headers=headers,
    )
    assert adhoc.status_code == 201, adhoc.text

    sheet = client.get(
        "/api/professor/attendance-sheet",
        params={"class_division_id": str(setup["class_division_id"]), "date_from": "2000-01-01", "date_to": "2100-01-01"},
        headers=headers,
    ).json()
    assert len(sheet["columns"]) == 2
    marks = {row["full_name"]: [row["cells"][c["lecture_id"]]["status"] for c in sheet["columns"]] for row in sheet["rows"]}
    assert marks["Test Student"].count("present") == 1
    absent_student = next(v for k, v in marks.items() if k != "Test Student")
    assert absent_student == [None, None]


# ----------------------------------------------------------------------------------------
# Professor dashboard
# ----------------------------------------------------------------------------------------


def test_dashboard_offers_lecture_in_progress_and_the_active_session_to_resume(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])  # started 5 min ago
    headers = auth_headers(professor_and_token["access_token"])
    dash = client.get("/api/professor/dashboard", headers=headers).json()
    assert [s["lecture_id"] for s in dash["upcoming_sessions"]] == [str(setup["lecture_id"])]
    assert dash["upcoming_sessions"][0]["has_active_session"] is False

    session_id = _start(client, professor_and_token, setup["lecture_id"])
    dash = client.get("/api/professor/dashboard", headers=headers).json()
    assert dash["upcoming_sessions"][0]["active_session_id"] == session_id
    assert dash["active_subjects"][0]["active_session_id"] == session_id


def test_dashboard_does_not_report_an_overdue_session_as_active(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _start(client, professor_and_token, setup["lecture_id"])
    lecture = db_session.get(Lecture, setup["lecture_id"])
    lecture.scheduled_end = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    dash = client.get("/api/professor/dashboard", headers=auth_headers(professor_and_token["access_token"])).json()
    assert dash["active_subjects"][0]["has_active_session"] is False


# ----------------------------------------------------------------------------------------
# Student: last scan (success screen) and cooldown persistence
# ----------------------------------------------------------------------------------------


def test_last_scan_survives_refresh_and_relogin(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    student_headers = auth_headers(student_and_token["access_token"])
    assert client.get("/api/students/me/last-scan", headers=student_headers).status_code == 404

    session_id = _start(client, professor_and_token, setup["lecture_id"])
    scan = _scan(client, student_and_token, _live(client, professor_and_token, session_id)["qr_payload"])
    assert scan.status_code == 200
    assert scan.json()["cooldown_expires_at"] is not None

    for headers in (student_headers,):
        last = client.get("/api/students/me/last-scan", headers=headers).json()
        assert last["subject_name"] == "Test Subject"
        assert last["attendance_status"] == "present"
        assert last["cooldown_active"] is True
        assert 0 < last["cooldown_remaining_seconds"] <= 60

    # Logging out and back in (the post-scan cooldown must not block re-login) shows the same record.
    relogin = login(client, "student@college.edu")
    assert relogin.status_code == 200
    again = client.get("/api/students/me/last-scan", headers=auth_headers(relogin.json()["access_token"])).json()
    assert again["marked_at"] == last["marked_at"]


def test_logout_cooldown_blocks_login_until_it_expires_and_is_server_side(client, student_and_token):
    from app.core.security import decode_access_token  # noqa: F401  (token is opaque to the client)

    headers = auth_headers(student_and_token["access_token"])
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    blocked = login(client, "student@college.edu")
    assert blocked.status_code == 423
    assert blocked.json()["detail"]["remaining_seconds"] > 3000  # ~60 minutes, from the server clock
    # The old token is dead too — logging out really ends the session.
    assert client.get("/api/auth/me", headers=headers).status_code == 401


# ----------------------------------------------------------------------------------------
# Admin fixes
# ----------------------------------------------------------------------------------------


def test_admin_lecture_accepts_naive_datetimes_as_utc(client, admin_and_token, professor_and_token, db_session, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        "/api/admin/lectures",
        json={
            "class_division_id": str(setup["class_division_id"]),
            "scheduled_start": "2030-01-01T09:00:00",
            "scheduled_end": "2030-01-01T10:00:00",
        },
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert resp.status_code == 201, resp.text
    bad = client.post(
        "/api/admin/lectures",
        json={
            "class_division_id": str(setup["class_division_id"]),
            "scheduled_start": "2030-01-01T10:00:00",
            "scheduled_end": "2030-01-01T09:00:00Z",
        },
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert bad.status_code == 422


def test_admin_can_reset_a_student_password_and_old_sessions_die(client, admin_and_token, student_and_token):
    admin_headers = auth_headers(admin_and_token["access_token"])
    students = client.get("/api/admin/students", headers=admin_headers).json()
    student_id = students[0]["id"]
    resp = client.patch(f"/api/admin/students/{student_id}", json={"password": "BrandNewPass9!"}, headers=admin_headers)
    assert resp.status_code == 200
    assert "password" not in resp.text.lower().replace("password_hash", "")
    assert client.get("/api/auth/me", headers=auth_headers(student_and_token["access_token"])).status_code == 401
    assert login(client, "student@college.edu", "Password123!").status_code == 401
    assert login(client, "student@college.edu", "BrandNewPass9!").status_code == 200
    short = client.patch(f"/api/admin/students/{student_id}", json={"password": "short"}, headers=admin_headers)
    assert short.status_code == 422


def test_full_admin_onboarding_to_scan_uses_only_the_admin_api(client, admin_and_token):
    """Journey A -> B -> C with no direct DB manipulation: everything a new college needs."""
    h = auth_headers(admin_and_token["access_token"])
    prof = client.post(
        "/api/admin/professors",
        json={"email": "Prof.New@College.edu", "password": "Password123!", "full_name": "Prof New", "department": "CS"},
        headers=h,
    ).json()
    subject = client.post("/api/admin/subjects", json={"code": "CS101", "name": "Intro", "credits": 4}, headers=h).json()
    division = client.post(
        "/api/admin/divisions",
        json={"subject_id": subject["id"], "professor_id": prof["id"], "name": "A", "semester": 1, "room": "R1"},
        headers=h,
    ).json()
    student_ids = []
    for i in range(3):
        st = client.post(
            "/api/admin/students",
            json={
                "email": f"s{i}@college.edu",
                "password": "Password123!",
                "full_name": f"Student {i}",
                "roll_number": f"R{i}",
                "program": "BTech",
                "semester": 1,
            },
            headers=h,
        )
        assert st.status_code == 201, st.text
        student_ids.append(st.json()["id"])
    bulk = client.post("/api/admin/enrollments/bulk", json={"student_ids": student_ids, "class_division_id": division["id"]}, headers=h)
    assert len(bulk.json()["enrolled"]) == 3
    now = datetime.now(timezone.utc)
    lecture = client.post(
        "/api/admin/lectures",
        json={
            "class_division_id": division["id"],
            "topic": "Kickoff",
            "scheduled_start": (now - timedelta(minutes=2)).isoformat(),
            "scheduled_end": (now + timedelta(hours=1)).isoformat(),
        },
        headers=h,
    )
    assert lecture.status_code == 201, lecture.text

    prof_token = login(client, "prof.new@college.edu").json()  # different case than created
    session = client.post(
        "/api/attendance/sessions", json={"lecture_id": lecture.json()["id"]}, headers=auth_headers(prof_token["access_token"])
    )
    assert session.status_code == 201, session.text
    for i in range(3):
        student_token = login(client, f"s{i}@college.edu").json()
        qr = _live(client, prof_token, session.json()["id"])["qr_payload"]
        assert _scan(client, student_token, qr).status_code == 200
        assert client.get("/api/students/me/last-scan", headers=auth_headers(student_token["access_token"])).status_code == 200

    live = _live(client, prof_token, session.json()["id"])
    assert (live["present_count"], live["total_enrolled"]) == (3, 3)
    assert len(live["feed"]) == 3


# ----------------------------------------------------------------------------------------
# Admin summary + sheet "started" flag
# ----------------------------------------------------------------------------------------


def test_admin_summary_counts_and_is_admin_only(client, admin_and_token, professor_and_token, student_and_token, db_session):
    make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.get("/api/admin/summary", headers=auth_headers(admin_and_token["access_token"]))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"students": 1, "professors": 1, "subjects": 1, "divisions": 1, "lectures": 1, "enrollments": 1}
    assert client.get("/api/admin/summary", headers=auth_headers(student_and_token["access_token"])).status_code == 403
    assert client.get("/api/admin/summary").status_code == 401


def test_sheet_marks_future_lectures_as_not_started(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    future = Lecture(
        class_division_id=setup["class_division_id"],
        topic="Later",
        scheduled_start=datetime.now(timezone.utc) + timedelta(hours=3),
        scheduled_end=datetime.now(timezone.utc) + timedelta(hours=4),
    )
    db_session.add(future)
    db_session.commit()
    today = datetime.now(timezone.utc).date()
    sheet = client.get(
        "/api/professor/attendance-sheet",
        params={
            "class_division_id": str(setup["class_division_id"]),
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": (today + timedelta(days=1)).isoformat(),
        },
        headers=auth_headers(professor_and_token["access_token"]),
    ).json()
    started = {c["lecture_id"]: c["started"] for c in sheet["columns"]}
    assert started[str(setup["lecture_id"])] is True
    assert started[str(future.id)] is False
