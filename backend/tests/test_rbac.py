from tests.conftest import auth_headers, login, register_professor, register_student


def test_student_cannot_start_attendance_session(client, db_session, student_and_token, professor_and_token):
    from tests.conftest import make_class_setup

    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(setup["lecture_id"])},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 403


def test_professor_cannot_scan_qr(client, professor_and_token):
    resp = client.post(
        "/api/attendance/scan",
        json={"token": "irrelevant"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 403


def test_student_cannot_access_professor_dashboard(client, student_and_token):
    resp = client.get("/api/professor/dashboard", headers=auth_headers(student_and_token["access_token"]))
    assert resp.status_code == 403


def test_professor_cannot_access_student_dashboard(client, professor_and_token):
    resp = client.get("/api/students/me/dashboard", headers=auth_headers(professor_and_token["access_token"]))
    assert resp.status_code == 403
