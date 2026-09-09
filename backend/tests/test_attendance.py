from datetime import datetime, timedelta, timezone

from app.models.attendance import AttendanceSession
from app.services import attendance_service
from tests.conftest import auth_headers, login, make_class_setup, register_professor, register_student


def _create_session_via_api(client, professor_token, lecture_id):
    resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(lecture_id)},
        headers=auth_headers(professor_token["access_token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_present_status_when_scanned_promptly(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(
        db_session,
        professor_and_token["user_id"],
        student_and_token["user_id"],
        lecture_start=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    live = client.get(
        f"/api/attendance/sessions/{session_data['id']}/live",
        headers=auth_headers(professor_and_token["access_token"]),
    )
    resp = client.post(
        "/api/attendance/scan",
        json={"token": live.json()["qr_payload"]},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["attendance_status"] == "present"


def test_late_status_when_scanned_after_15_minutes(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(
        db_session,
        professor_and_token["user_id"],
        student_and_token["user_id"],
        lecture_start=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    live = client.get(
        f"/api/attendance/sessions/{session_data['id']}/live",
        headers=auth_headers(professor_and_token["access_token"]),
    )
    resp = client.post(
        "/api/attendance/scan",
        json={"token": live.json()["qr_payload"]},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["attendance_status"] == "late"


def test_unenrolled_student_scan_rejected(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    live = client.get(
        f"/api/attendance/sessions/{session_data['id']}/live",
        headers=auth_headers(professor_and_token["access_token"]),
    )

    register_student(client, email="outsider@college.edu", roll_number="R777")
    outsider_token = login(client, "outsider@college.edu").json()

    resp = client.post(
        "/api/attendance/scan",
        json={"token": live.json()["qr_payload"]},
        headers=auth_headers(outsider_token["access_token"]),
    )
    assert resp.status_code == 403


def test_duplicate_attendance_for_same_lecture_rejected(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    live = client.get(
        f"/api/attendance/sessions/{session_data['id']}/live",
        headers=auth_headers(professor_and_token["access_token"]),
    )
    first = client.post(
        "/api/attendance/scan",
        json={"token": live.json()["qr_payload"]},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert first.status_code == 200

    # Issue a brand-new (unconsumed) token directly, bypassing the "reuse current if
    # unexpired" cache in get_or_issue_current_token, so this exercises the
    # duplicate-attendance-record check rather than the token-replay check.
    session_obj = db_session.get(AttendanceSession, session_data["id"])
    fresh_token = attendance_service.issue_token(db_session, session_obj)
    fresh_payload = attendance_service.encode_qr_payload(fresh_token)

    second = client.post(
        "/api/attendance/scan",
        json={"token": fresh_payload},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert second.status_code == 409


def test_create_session_conflict_when_already_active(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    first = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(setup["lecture_id"])},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 409


def test_close_session_by_non_owning_professor_forbidden(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])

    register_professor(client, email="other.prof@college.edu")
    other_prof_token = login(client, "other.prof@college.edu").json()

    resp = client.post(
        f"/api/attendance/sessions/{session_data['id']}/close",
        headers=auth_headers(other_prof_token["access_token"]),
    )
    assert resp.status_code == 403


def test_close_session_success(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    resp = client.post(
        f"/api/attendance/sessions/{session_data['id']}/close",
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
