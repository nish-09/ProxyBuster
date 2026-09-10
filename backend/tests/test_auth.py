from tests.conftest import TEST_INVITE_CODE, login, register_professor, register_student


def test_register_and_login_student(client):
    register_student(client)
    resp = login(client, "student@college.edu")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "student"
    assert "access_token" in body


def test_register_and_login_professor(client):
    register_professor(client)
    resp = login(client, "prof@college.edu")
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "professor"


def test_login_wrong_password_401(client):
    register_student(client)
    resp = login(client, "student@college.edu", password="WrongPassword!")
    assert resp.status_code == 401


def test_login_nonexistent_user_401(client):
    resp = login(client, "nobody@college.edu", password="whatever")
    assert resp.status_code == 401


def test_unauthenticated_request_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_endpoint_returns_current_user(client):
    register_student(client)
    token = login(client, "student@college.edu").json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "student@college.edu"


def test_professor_registration_rejects_missing_invite_code(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "noinvite@college.edu",
            "password": "Password123!",
            "full_name": "No Invite",
            "role": "professor",
            "department": "Computer Science",
        },
    )
    assert resp.status_code == 403, resp.text


def test_professor_registration_rejects_wrong_invite_code(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "wronginvite@college.edu",
            "password": "Password123!",
            "full_name": "Wrong Invite",
            "role": "professor",
            "department": "Computer Science",
            "invite_code": "not-the-real-code",
        },
    )
    assert resp.status_code == 403, resp.text


def test_professor_registration_accepts_correct_invite_code(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "rightinvite@college.edu",
            "password": "Password123!",
            "full_name": "Right Invite",
            "role": "professor",
            "department": "Computer Science",
            "invite_code": TEST_INVITE_CODE,
        },
    )
    assert resp.status_code == 201, resp.text


def test_professor_invite_code_never_returned_in_response(client):
    resp = register_professor(client, email="checkleak@college.edu")
    assert "invite_code" not in resp
    assert TEST_INVITE_CODE not in str(resp)


def test_duplicate_email_registration_conflict(client):
    register_student(client)
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "student@college.edu",
            "password": "Password123!",
            "full_name": "Someone Else",
            "role": "student",
            "roll_number": "R999",
            "program": "B.Tech CS",
            "semester": 6,
        },
    )
    assert resp.status_code == 409
