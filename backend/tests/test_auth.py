from tests.conftest import login, register_professor, register_student


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
