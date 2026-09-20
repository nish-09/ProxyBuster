"""Confirms throttling is actually enforced (not just wired but never applied)."""
from tests.conftest import register_student


def test_failed_logins_lock_the_account_regardless_of_ip(client):
    register_student(client, email="victim@college.edu")
    payload = {"email": "victim@college.edu", "password": "wrong-password"}

    responses = [client.post("/api/auth/login", json=payload) for _ in range(9)]

    assert all(r.status_code == 401 for r in responses[:8])
    assert responses[8].status_code == 429
    assert responses[8].json()["detail"]["remaining_seconds"] > 0

    # Even the CORRECT password is refused while the account is locked...
    locked = client.post("/api/auth/login", json={"email": "victim@college.edu", "password": "Password123!"})
    assert locked.status_code == 429
    # ...but other accounts sharing the same IP (a whole campus NAT) are unaffected.
    register_student(client, email="bystander@college.edu", roll_number="R777")
    ok = client.post("/api/auth/login", json={"email": "bystander@college.edu", "password": "Password123!"})
    assert ok.status_code == 200


def test_successful_login_resets_failure_counter(client):
    register_student(client, email="forgetful@college.edu")
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "forgetful@college.edu", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "forgetful@college.edu", "password": "Password123!"}).status_code == 200
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "forgetful@college.edu", "password": "nope"}).status_code == 401


def test_register_is_rate_limited_per_ip(client):
    def attempt(i):
        return client.post(
            "/api/auth/register",
            json={
                "email": f"ratelimit{i}@college.edu",
                "password": "Password123!",
                "full_name": "Rate Limit Test",
                "role": "student",
                "roll_number": f"RL{i}",
                "program": "B.Tech CS",
                "semester": 1,
            },
        )

    responses = [attempt(i) for i in range(21)]

    assert all(r.status_code == 201 for r in responses[:20])
    assert responses[20].status_code == 429
