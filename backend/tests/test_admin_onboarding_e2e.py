"""End-to-end proof that everything an admin creates through the admin API is immediately
usable by the existing professor/student dashboards and the existing attendance/QR flow —
i.e. an admin never needs to hand-insert anything into the database for a real pilot to work."""
from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers


def _admin_headers(admin_and_token):
    return auth_headers(admin_and_token["access_token"])


def test_full_onboarding_flow_admin_to_attendance(client, admin_and_token):
    admin_h = _admin_headers(admin_and_token)

    # 1. Admin creates a professor
    prof_resp = client.post(
        "/api/admin/professors",
        json={
            "email": "e2e.professor@example.test",
            "password": "Password123!",
            "full_name": "E2E Professor",
            "department": "Computer Science",
        },
        headers=admin_h,
    )
    assert prof_resp.status_code == 201, prof_resp.text
    professor_id = prof_resp.json()["id"]

    # 2. Admin creates a student
    student_resp = client.post(
        "/api/admin/students",
        json={
            "email": "e2e.student@example.test",
            "password": "Password123!",
            "full_name": "E2E Student",
            "roll_number": "E2E001",
            "program": "B.Tech CS",
            "semester": 5,
        },
        headers=admin_h,
    )
    assert student_resp.status_code == 201, student_resp.text
    student_id = student_resp.json()["id"]

    # 3. Admin creates a subject
    subject_resp = client.post(
        "/api/admin/subjects", json={"code": "E2E-100", "name": "Onboarding Systems", "credits": 4}, headers=admin_h
    )
    assert subject_resp.status_code == 201, subject_resp.text
    subject_id = subject_resp.json()["id"]

    # 4. Admin creates a division and assigns the professor
    division_resp = client.post(
        "/api/admin/divisions",
        json={"subject_id": subject_id, "professor_id": professor_id, "name": "Div A", "semester": 5, "room": "Room 1"},
        headers=admin_h,
    )
    assert division_resp.status_code == 201, division_resp.text
    division_id = division_resp.json()["id"]
    assert division_resp.json()["professor_id"] == professor_id
    assert division_resp.json()["subject_id"] == subject_id

    # 5. Admin enrolls the student into the division
    enroll_resp = client.post(
        "/api/admin/enrollments", json={"student_id": student_id, "class_division_id": division_id}, headers=admin_h
    )
    assert enroll_resp.status_code == 201, enroll_resp.text

    # Duplicate enrollment must be rejected, not silently accepted or duplicated
    dup_resp = client.post(
        "/api/admin/enrollments", json={"student_id": student_id, "class_division_id": division_id}, headers=admin_h
    )
    assert dup_resp.status_code == 409

    # 6. Admin schedules a lecture — in the recent past so a scan right now marks PRESENT
    lecture_start = datetime.now(timezone.utc) - timedelta(minutes=2)
    lecture_resp = client.post(
        "/api/admin/lectures",
        json={
            "class_division_id": division_id,
            "topic": "Kickoff",
            "scheduled_start": lecture_start.isoformat(),
            "scheduled_end": (lecture_start + timedelta(hours=1)).isoformat(),
            "room": "Room 1",
        },
        headers=admin_h,
    )
    assert lecture_resp.status_code == 201, lecture_resp.text
    lecture_id = lecture_resp.json()["id"]

    # Now log in as the professor and student the admin just created (via the normal /auth/login,
    # not the admin API) — proving these are fully real, working accounts.
    prof_login = client.post(
        "/api/auth/login", json={"email": "e2e.professor@example.test", "password": "Password123!"}
    )
    assert prof_login.status_code == 200, prof_login.text
    prof_token = prof_login.json()["access_token"]

    student_login = client.post(
        "/api/auth/login", json={"email": "e2e.student@example.test", "password": "Password123!"}
    )
    assert student_login.status_code == 200, student_login.text
    student_token = student_login.json()["access_token"]

    # 7. Professor can see the division/subject the admin created (dashboard + student roster)
    prof_dashboard = client.get("/api/professor/dashboard", headers=auth_headers(prof_token))
    assert prof_dashboard.status_code == 200
    subject_codes = [s["subject_code"] for s in prof_dashboard.json()["active_subjects"]]
    assert "E2E-100" in subject_codes

    roster = client.get(
        "/api/professor/students", params={"class_division_id": division_id}, headers=auth_headers(prof_token)
    )
    assert roster.status_code == 200
    assert any(item["roll_number"] == "E2E001" for item in roster.json()["items"])

    # 8. Student can see the subject on their own dashboard
    student_dashboard = client.get("/api/students/me/dashboard", headers=auth_headers(student_token))
    assert student_dashboard.status_code == 200
    student_subject_codes = [s["subject_code"] for s in student_dashboard.json()["subjects"]]
    assert "E2E-100" in student_subject_codes

    # 9. Attendance starts normally: professor opens a session for the admin-created lecture
    session_resp = client.post(
        "/api/attendance/sessions", json={"lecture_id": lecture_id}, headers=auth_headers(prof_token)
    )
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["id"]

    live_resp = client.get(f"/api/attendance/sessions/{session_id}/live", headers=auth_headers(prof_token))
    assert live_resp.status_code == 200
    qr_payload = live_resp.json()["qr_payload"]
    assert qr_payload

    # Student scans it
    scan_resp = client.post("/api/attendance/scan", json={"token": qr_payload}, headers=auth_headers(student_token))
    assert scan_resp.status_code == 200, scan_resp.text
    assert scan_resp.json()["attendance_status"] == "present"

    # 10. Student's attendance percentage reflects the scan immediately
    updated_dashboard = client.get("/api/students/me/dashboard", headers=auth_headers(student_token))
    subject_entry = next(s for s in updated_dashboard.json()["subjects"] if s["subject_code"] == "E2E-100")
    assert subject_entry["present"] == 1
    assert subject_entry["percentage"] == 100.0

    close_resp = client.post(f"/api/attendance/sessions/{session_id}/close", headers=auth_headers(prof_token))
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "closed"


def test_admin_enrollment_rejects_invalid_relationships(client, admin_and_token):
    admin_h = _admin_headers(admin_and_token)

    resp = client.post(
        "/api/admin/enrollments",
        json={
            "student_id": "00000000-0000-0000-0000-000000000000",
            "class_division_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=admin_h,
    )
    assert resp.status_code == 404


def test_professor_created_by_admin_cannot_touch_other_professors_division(client, admin_and_token):
    admin_h = _admin_headers(admin_and_token)

    prof_a = client.post(
        "/api/admin/professors",
        json={"email": "prof.a@example.test", "password": "Password123!", "full_name": "Prof A", "department": "CS"},
        headers=admin_h,
    ).json()
    prof_b = client.post(
        "/api/admin/professors",
        json={"email": "prof.b@example.test", "password": "Password123!", "full_name": "Prof B", "department": "CS"},
        headers=admin_h,
    ).json()
    subject = client.post(
        "/api/admin/subjects", json={"code": "E2E-200", "name": "Isolation Test", "credits": 3}, headers=admin_h
    ).json()
    division = client.post(
        "/api/admin/divisions",
        json={"subject_id": subject["id"], "professor_id": prof_a["id"], "name": "Div A", "semester": 3},
        headers=admin_h,
    ).json()
    lecture = client.post(
        "/api/admin/lectures",
        json={
            "class_division_id": division["id"],
            "scheduled_start": "2026-09-15T10:00:00Z",
            "scheduled_end": "2026-09-15T11:00:00Z",
        },
        headers=admin_h,
    ).json()

    prof_b_login = client.post("/api/auth/login", json={"email": "prof.b@example.test", "password": "Password123!"})
    prof_b_token = prof_b_login.json()["access_token"]

    resp = client.post(
        "/api/attendance/sessions", json={"lecture_id": lecture["id"]}, headers=auth_headers(prof_b_token)
    )
    assert resp.status_code == 403
