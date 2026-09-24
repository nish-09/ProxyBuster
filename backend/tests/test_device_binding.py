"""Device binding: an anti-proxy-*sharing* layer (see app/services/device_binding_service.py).

The device_id is a client-generated, self-reported value (a random string the frontend stores
in localStorage) — it is NOT hardware attestation and is trivially reset by clearing storage or
switching browsers. What it DOES prevent is one physical/browser "device" being used to log in
as two DIFFERENT students at once, which is the concrete proxy-sharing scenario (a student hands
their unlocked phone, still logged in as them, to someone else — that's a session/device-session
issue, not this). Binding is deliberately one-way: a single student may bind multiple devices
(phone + laptop) without conflict — only device *sharing across students* is rejected.
"""
from app.models.security import DeviceBinding, DeviceBindingStatus
from tests.conftest import auth_headers, login, register_student


def test_first_login_registers_the_device(client):
    register_student(client, email="a@college.edu", roll_number="RA001")
    resp = login(client, "a@college.edu", device_id="device-1")
    assert resp.status_code == 200, resp.text


def test_same_student_same_device_always_works(client):
    register_student(client, email="a@college.edu", roll_number="RA001")
    login(client, "a@college.edu", device_id="device-1")
    second = login(client, "a@college.edu", device_id="device-1")
    assert second.status_code == 200, second.text


def test_same_student_different_device_is_allowed(client):
    """One student legitimately using a phone AND a laptop is not a proxy risk — only a device
    being shared across DIFFERENT students is."""
    register_student(client, email="a@college.edu", roll_number="RA001")
    login(client, "a@college.edu", device_id="device-1")
    second = login(client, "a@college.edu", device_id="device-2")
    assert second.status_code == 200, second.text


def test_different_student_same_device_is_rejected(client):
    register_student(client, email="a@college.edu", roll_number="RA001")
    register_student(client, email="b@college.edu", roll_number="RB001")
    login(client, "a@college.edu", device_id="shared-device")

    resp = login(client, "b@college.edu", device_id="shared-device")
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "device_registered_to_another_student"


def test_logout_does_not_free_the_device_for_another_student(client, db_session):
    register_student(client, email="a@college.edu", roll_number="RA001")
    register_student(client, email="b@college.edu", roll_number="RB001")
    first = login(client, "a@college.edu", device_id="shared-device").json()

    logout_resp = client.post("/api/auth/logout", headers=auth_headers(first["access_token"]))
    assert logout_resp.status_code == 204

    # A voluntary logout starts its own (unrelated) post-logout login cooldown — see
    # test_cooldown.py — so re-login as student A isn't exercised here. What matters for THIS
    # test is that the device_binding row itself is untouched by logout.
    db_session.expire_all()
    binding = db_session.query(DeviceBinding).filter(DeviceBinding.device_id == "shared-device").one()
    assert binding.status == DeviceBindingStatus.ACTIVE
    assert str(binding.student_id) != "" and binding.revoked_at is None

    # Student B still cannot claim it — logout does not clear the binding.
    other = login(client, "b@college.edu", device_id="shared-device")
    assert other.status_code == 403, other.text


def test_missing_device_id_is_never_blocked(client):
    """A caller that can't/won't report a device_id (e.g. a script, or a client without
    localStorage) must never be blocked over an absent value — there's nothing to check."""
    register_student(client, email="a@college.edu", roll_number="RA001")
    register_student(client, email="b@college.edu", roll_number="RB001")
    first = login(client, "a@college.edu", device_id=None)
    second = login(client, "b@college.edu", device_id=None)
    assert first.status_code == 200
    assert second.status_code == 200


def test_admin_reset_frees_the_device_for_a_new_student(client, db_session, admin_and_token):
    register_student(client, email="a@college.edu", roll_number="RA001")
    register_student(client, email="b@college.edu", roll_number="RB001")
    login(client, "a@college.edu", device_id="shared-device")

    student_a_id = str(db_session.query(DeviceBinding).filter(DeviceBinding.device_id == "shared-device").first().student_id)

    blocked = login(client, "b@college.edu", device_id="shared-device")
    assert blocked.status_code == 403

    reset = client.post(
        f"/api/admin/students/{student_a_id}/device-binding/reset",
        json={"reason": "Student reported a lost phone"},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["revoked_count"] == 1

    # Device re-registers cleanly to whoever logs in next.
    now_free = login(client, "b@college.edu", device_id="shared-device")
    assert now_free.status_code == 200, now_free.text

    db_session.expire_all()
    active_binding = (
        db_session.query(DeviceBinding)
        .filter(DeviceBinding.device_id == "shared-device", DeviceBinding.status == DeviceBindingStatus.ACTIVE)
        .one()
    )
    assert str(active_binding.student_id) != student_a_id


def test_reset_preserves_audit_history_never_deletes(client, db_session, admin_and_token):
    register_student(client, email="a@college.edu", roll_number="RA001")
    login(client, "a@college.edu", device_id="device-1")
    student_a_id = str(db_session.query(DeviceBinding).filter(DeviceBinding.device_id == "device-1").first().student_id)

    client.post(
        f"/api/admin/students/{student_a_id}/device-binding/reset",
        json={"reason": "test"},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    db_session.expire_all()
    rows = db_session.query(DeviceBinding).filter(DeviceBinding.device_id == "device-1").all()
    assert len(rows) == 1  # revoked in place, not deleted
    assert rows[0].status == DeviceBindingStatus.REVOKED
    assert rows[0].revoked_at is not None
    assert rows[0].revocation_reason == "test"


def test_reset_with_no_active_binding_is_a_harmless_noop(client, db_session, admin_and_token):
    from app.models.user import StudentProfile

    register_student(client, email="a@college.edu", roll_number="RA001")
    # Never logged in with a device_id, so nothing is bound yet.
    login(client, "a@college.edu", device_id=None)
    student_id = str(db_session.query(StudentProfile).filter(StudentProfile.roll_number == "RA001").one().id)

    reset = client.post(
        f"/api/admin/students/{student_id}/device-binding/reset",
        json={},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert reset.status_code == 200
    assert reset.json()["revoked_count"] == 0


def test_professor_cannot_reset_device_binding(client, professor_and_token, student_and_token):
    resp = client.post(
        f"/api/admin/students/{student_and_token['user_id']}/device-binding/reset",
        json={},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 403


def test_student_cannot_reset_device_binding(client, student_and_token):
    resp = client.post(
        f"/api/admin/students/{student_and_token['user_id']}/device-binding/reset",
        json={},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 403


def test_reset_for_nonexistent_student_is_404(client, admin_and_token):
    import uuid

    resp = client.post(
        f"/api/admin/students/{uuid.uuid4()}/device-binding/reset",
        json={},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert resp.status_code == 404


def test_concurrent_registration_of_the_same_new_device_only_binds_one_student(client, db_session):
    """Simulates two students racing to be the first to claim a brand-new device_id. The DB-level
    partial unique index (uq_active_device_binding) is the actual guarantee here — the service
    layer's read-then-write check is only the fast path."""
    register_student(client, email="a@college.edu", roll_number="RA001")
    register_student(client, email="b@college.edu", roll_number="RB001")

    results = [
        login(client, "a@college.edu", device_id="race-device").status_code,
        login(client, "b@college.edu", device_id="race-device").status_code,
    ]
    # The second call always loses the race deterministically here (no real concurrency in a
    # single-threaded TestClient), but it must still be cleanly rejected, not a 500.
    assert results[0] == 200
    assert results[1] == 403

    active = (
        db_session.query(DeviceBinding)
        .filter(DeviceBinding.device_id == "race-device", DeviceBinding.status == DeviceBindingStatus.ACTIVE)
        .all()
    )
    assert len(active) == 1
