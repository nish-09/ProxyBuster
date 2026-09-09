"""Confirms rate limiting is actually enforced (not just wired but never applied)."""


def test_login_is_rate_limited(client):
    payload = {"email": "nobody@college.edu", "password": "wrong-password"}

    responses = [client.post("/api/auth/login", json=payload) for _ in range(11)]

    assert all(r.status_code == 401 for r in responses[:10])
    assert responses[10].status_code == 429


def test_register_is_rate_limited(client):
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

    responses = [attempt(i) for i in range(6)]

    assert all(r.status_code == 201 for r in responses[:5])
    assert responses[5].status_code == 429
