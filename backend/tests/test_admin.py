from tests.conftest import auth_headers


def _admin_headers(admin_and_token):
    return auth_headers(admin_and_token["access_token"])


# ---------- RBAC ----------


def test_student_cannot_access_admin_endpoints(client, student_and_token):
    resp = client.get("/api/admin/students", headers=auth_headers(student_and_token["access_token"]))
    assert resp.status_code == 403


def test_professor_cannot_access_admin_endpoints(client, professor_and_token):
    resp = client.get("/api/admin/students", headers=auth_headers(professor_and_token["access_token"]))
    assert resp.status_code == 403


def test_unauthenticated_cannot_access_admin_endpoints(client):
    resp = client.get("/api/admin/students")
    assert resp.status_code == 401


def test_professor_cannot_create_subject(client, professor_and_token):
    resp = client.post(
        "/api/admin/subjects",
        json={"code": "CS-999", "name": "Hacked In", "credits": 3},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 403


# ---------- Admin creates academic data end-to-end ----------


def test_admin_can_create_full_academic_structure(client, admin_and_token):
    headers = _admin_headers(admin_and_token)

    prof_resp = client.post(
        "/api/admin/professors",
        json={"email": "admin.created.prof@example.test", "password": "Password123!", "full_name": "Dr. Created", "department": "CS"},
        headers=headers,
    )
    assert prof_resp.status_code == 201, prof_resp.text
    professor_id = prof_resp.json()["id"]

    subj_resp = client.post(
        "/api/admin/subjects", json={"code": "CS-500", "name": "Distributed Systems", "credits": 4}, headers=headers
    )
    assert subj_resp.status_code == 201, subj_resp.text
    subject_id = subj_resp.json()["id"]

    div_resp = client.post(
        "/api/admin/divisions",
        json={"subject_id": subject_id, "professor_id": professor_id, "name": "Div A", "semester": 5, "room": "Room 101"},
        headers=headers,
    )
    assert div_resp.status_code == 201, div_resp.text
    division_id = div_resp.json()["id"]
    assert div_resp.json()["enrolled_count"] == 0

    student_resp = client.post(
        "/api/admin/students",
        json={
            "email": "admin.created.student@example.test",
            "password": "Password123!",
            "full_name": "Created Student",
            "roll_number": "ADM001",
            "program": "B.Tech CS",
            "semester": 5,
        },
        headers=headers,
    )
    assert student_resp.status_code == 201, student_resp.text
    student_id = student_resp.json()["id"]

    enroll_resp = client.post(
        "/api/admin/enrollments", json={"student_id": student_id, "class_division_id": division_id}, headers=headers
    )
    assert enroll_resp.status_code == 201, enroll_resp.text

    dup_enroll_resp = client.post(
        "/api/admin/enrollments", json={"student_id": student_id, "class_division_id": division_id}, headers=headers
    )
    assert dup_enroll_resp.status_code == 409

    lecture_resp = client.post(
        "/api/admin/lectures",
        json={
            "class_division_id": division_id,
            "topic": "Intro",
            "scheduled_start": "2026-09-15T10:00:00Z",
            "scheduled_end": "2026-09-15T11:00:00Z",
            "room": "Room 101",
        },
        headers=headers,
    )
    assert lecture_resp.status_code == 201, lecture_resp.text

    divisions_after = client.get("/api/admin/divisions", headers=headers).json()
    updated_division = next(d for d in divisions_after if d["id"] == division_id)
    assert updated_division["enrolled_count"] == 1


def test_admin_create_division_rejects_nonexistent_subject(client, admin_and_token):
    headers = _admin_headers(admin_and_token)
    prof_resp = client.post(
        "/api/admin/professors",
        json={"email": "ghost.subject.prof@example.test", "password": "Password123!", "full_name": "Dr. Ghost", "department": "CS"},
        headers=headers,
    )
    professor_id = prof_resp.json()["id"]

    resp = client.post(
        "/api/admin/divisions",
        json={
            "subject_id": "00000000-0000-0000-0000-000000000000",
            "professor_id": professor_id,
            "name": "Div A",
            "semester": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 404


def test_admin_create_enrollment_rejects_nonexistent_student(client, admin_and_token):
    headers = _admin_headers(admin_and_token)
    prof_resp = client.post(
        "/api/admin/professors",
        json={"email": "enroll.prof@example.test", "password": "Password123!", "full_name": "Dr. Enroll", "department": "CS"},
        headers=headers,
    )
    subj_resp = client.post(
        "/api/admin/subjects", json={"code": "CS-501", "name": "Networks", "credits": 3}, headers=headers
    )
    div_resp = client.post(
        "/api/admin/divisions",
        json={"subject_id": subj_resp.json()["id"], "professor_id": prof_resp.json()["id"], "name": "Div A", "semester": 3},
        headers=headers,
    )

    resp = client.post(
        "/api/admin/enrollments",
        json={"student_id": "00000000-0000-0000-0000-000000000000", "class_division_id": div_resp.json()["id"]},
        headers=headers,
    )
    assert resp.status_code == 404


def test_admin_delete_subject_blocked_when_division_exists(client, admin_and_token):
    headers = _admin_headers(admin_and_token)
    prof_resp = client.post(
        "/api/admin/professors",
        json={"email": "blocked.delete.prof@example.test", "password": "Password123!", "full_name": "Dr. Blocked", "department": "CS"},
        headers=headers,
    )
    subj_resp = client.post(
        "/api/admin/subjects", json={"code": "CS-502", "name": "Compilers", "credits": 3}, headers=headers
    )
    subject_id = subj_resp.json()["id"]
    client.post(
        "/api/admin/divisions",
        json={"subject_id": subject_id, "professor_id": prof_resp.json()["id"], "name": "Div A", "semester": 3},
        headers=headers,
    )

    resp = client.delete(f"/api/admin/subjects/{subject_id}", headers=headers)
    assert resp.status_code == 409


def test_admin_deactivate_student(client, admin_and_token):
    headers = _admin_headers(admin_and_token)
    student_resp = client.post(
        "/api/admin/students",
        json={
            "email": "deactivate.me@example.test",
            "password": "Password123!",
            "full_name": "Deactivate Me",
            "roll_number": "DEACT001",
            "program": "B.Tech CS",
            "semester": 2,
        },
        headers=headers,
    )
    student_id = student_resp.json()["id"]
    assert student_resp.json()["is_active"] is True

    patch_resp = client.patch(f"/api/admin/students/{student_id}", json={"is_active": False}, headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # A deactivated account can no longer log in / use the API (authenticate() checks is_active).
    login_resp = client.post(
        "/api/auth/login", json={"email": "deactivate.me@example.test", "password": "Password123!"}
    )
    assert login_resp.status_code == 403
