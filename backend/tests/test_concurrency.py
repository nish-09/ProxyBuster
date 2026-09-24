"""Real multi-threaded race tests (not just sequential call-then-call), exercising the actual
database-level uniqueness constraints rather than only the service layer's read-then-write
fast-path checks. The per-test SQLite file is opened with check_same_thread=False (see
conftest.py) specifically so this works; the FastAPI TestClient's overridden get_db hands each
request its own Session bound to that same file, so concurrent client.post() calls from real
threads exercise a genuine race, not an artifact of call ordering.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.models.attendance import AttendanceRecord
from app.models.security import DeviceBinding, DeviceBindingStatus
from app.models.verification import VerificationDecision
from app.services.verification import service as verification_service
from tests.conftest import auth_headers, login, make_class_setup, register_student
from tests.test_classroom_verification import FakeProvider, _create_session_via_api, _mark_present, _start_verification
from tests.test_release_hardening import _live, _scan, _start


@pytest.fixture(autouse=True)
def _run_background_jobs_against_the_test_database(db_session_factory, monkeypatch):
    """See the identical fixture in test_classroom_verification.py — pytest fixtures aren't
    inherited across test modules just by importing helper functions from them."""
    monkeypatch.setattr(verification_service, "SessionLocal", db_session_factory)


def test_concurrent_decisions_on_the_same_discrepancy_only_one_wins(
    client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    client.post(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        files={"file": ("ref.jpg", b"bytes", "image/jpeg")},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    _mark_present(client, professor_and_token, student_and_token, session_data["id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider({"R001": 0.0}))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    verification_id = resp.json()["id"]
    detail = client.get(f"/api/verification/{verification_id}", headers=auth_headers(professor_and_token["access_token"])).json()
    result_id = detail["results"][0]["id"]

    def confirm():
        return client.post(
            f"/api/verification/results/{result_id}/decision",
            json={"action": "confirmed_present"},
            headers=auth_headers(professor_and_token["access_token"]),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(confirm), pool.submit(confirm)]]

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], f"expected exactly one winner, got {[r.status_code for r in results]}"
    db_session.expire_all()
    assert db_session.query(VerificationDecision).filter(VerificationDecision.result_id == result_id).count() == 1


def test_concurrent_double_submit_of_the_same_scan_only_marks_attendance_once(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_id = _start(client, professor_and_token, setup["lecture_id"])
    payload = _live(client, professor_and_token, session_id)["qr_payload"]

    def scan():
        return _scan(client, student_and_token, payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(scan), pool.submit(scan)]]

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], f"expected exactly one success, got {[r.status_code for r in results]}"
    db_session.expire_all()
    assert db_session.query(AttendanceRecord).count() == 1


def test_concurrent_registration_of_a_brand_new_device_only_binds_one_student_real_threads(client, db_session):
    register_student(client, email="ra@college.edu", roll_number="RRA001")
    register_student(client, email="rb@college.edu", roll_number="RRB001")

    def login_a():
        return login(client, "ra@college.edu", device_id="thread-race-device")

    def login_b():
        return login(client, "rb@college.edu", device_id="thread-race-device")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(login_a), pool.submit(login_b)]]

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 403], f"expected exactly one winner, got {[r.status_code for r in results]}"
    db_session.expire_all()
    active = (
        db_session.query(DeviceBinding)
        .filter(DeviceBinding.device_id == "thread-race-device", DeviceBinding.status == DeviceBindingStatus.ACTIVE)
        .all()
    )
    assert len(active) == 1
