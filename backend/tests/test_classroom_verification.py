import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.academic import Lecture
from app.models.user import ProfessorProfile
from app.models.verification import DetectionStatus, DiscrepancyType
from app.services import violation_service
from app.services.verification import service as verification_service
from app.services.verification.provider import StudentObservation, VisionAnalysis
from tests.conftest import auth_headers, login, make_class_setup, register_professor


@pytest.fixture(autouse=True)
def _run_background_jobs_against_the_test_database(db_session_factory, monkeypatch):
    """run_verification_job opens its own SessionLocal() (app/services/verification/service.py),
    the same pattern app/services/realtime.py's background tasks use — but that name is bound to
    the app's configured DATABASE_URL, not this test's isolated per-test SQLite file. Point it at
    the same engine as everything else in the test, or the BackgroundTask silently writes to a
    database this test can never see."""
    monkeypatch.setattr(verification_service, "SessionLocal", db_session_factory)


class FakeProvider:
    """Deterministic stand-in for AnthropicVisionProvider, keyed by roll number — mirrors the
    real provider's contract: only ever reports a student it was actually given a reference
    photo for (see analyze_classroom's `students` argument)."""

    def __init__(self, confidence_by_roll: dict | None = None, raise_error: bool = False):
        self.confidence_by_roll = confidence_by_roll or {}
        self.raise_error = raise_error
        self.calls = []

    def analyze_classroom(self, images, students):
        self.calls.append((images, students))
        if self.raise_error:
            raise RuntimeError("simulated provider failure")
        observations = [
            StudentObservation(student_id=s.student_id, confidence=self.confidence_by_roll[s.roll_number])
            for s in students
            if s.roll_number in self.confidence_by_roll
        ]
        return VisionAnalysis(observations=observations)


def _create_session_via_api(client, professor_token, lecture_id):
    resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(lecture_id)},
        headers=auth_headers(professor_token["access_token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _mark_present(client, professor_token, student_token, session_id):
    live = client.get(f"/api/attendance/sessions/{session_id}/live", headers=auth_headers(professor_token["access_token"]))
    resp = client.post(
        "/api/attendance/scan",
        json={"token": live.json()["qr_payload"]},
        headers=auth_headers(student_token["access_token"]),
    )
    assert resp.status_code == 200, resp.text


def _upload_reference_photo(client, admin_token, student_profile_id):
    resp = client.post(
        f"/api/admin/students/{student_profile_id}/reference-photo",
        files={"file": ("ref.jpg", b"fake-reference-photo-bytes", "image/jpeg")},
        headers=auth_headers(admin_token["access_token"]),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _start_verification(client, professor_token, session_id, n_images=1):
    files = [("images", (f"c{i}.jpg", b"classroom-photo-bytes", "image/jpeg")) for i in range(n_images)]
    return client.post(
        f"/api/verification/sessions/{session_id}/verify",
        files=files,
        headers=auth_headers(professor_token["access_token"]),
    )


def _add_lecture(db_session, class_division_id, start_offset_minutes=-5, duration_minutes=60):
    lecture = Lecture(
        class_division_id=class_division_id,
        topic="Second lecture",
        scheduled_start=datetime.now(timezone.utc) + timedelta(minutes=start_offset_minutes),
        scheduled_end=datetime.now(timezone.utc) + timedelta(minutes=start_offset_minutes + duration_minutes),
        room="Room 1",
    )
    db_session.add(lecture)
    db_session.commit()
    db_session.refresh(lecture)
    return lecture


# ---------------------------------------------------------------------------
# Pure unit tests: confidence bucketing + discrepancy classification
# ---------------------------------------------------------------------------


def test_confidence_bucketing_thresholds():
    assert verification_service._bucket_confidence(0.95) == DetectionStatus.CONFIRMED
    assert verification_service._bucket_confidence(0.85) == DetectionStatus.CONFIRMED
    assert verification_service._bucket_confidence(0.75) == DetectionStatus.HIGH_CONFIDENCE
    assert verification_service._bucket_confidence(0.30) == DetectionStatus.UNCERTAIN
    assert verification_service._bucket_confidence(0.0) == DetectionStatus.NOT_DETECTED


def test_discrepancy_classification_matrix():
    classify = verification_service._classify
    assert classify(True, DetectionStatus.CONFIRMED) == DiscrepancyType.ATTENDED_AND_DETECTED
    assert classify(True, DetectionStatus.HIGH_CONFIDENCE) == DiscrepancyType.ATTENDED_AND_DETECTED
    assert classify(True, DetectionStatus.UNCERTAIN) == DiscrepancyType.ATTENDED_NOT_DETECTED
    assert classify(True, DetectionStatus.NOT_DETECTED) == DiscrepancyType.ATTENDED_NOT_DETECTED
    assert classify(False, DetectionStatus.HIGH_CONFIDENCE) == DiscrepancyType.DETECTED_NOT_ATTENDED
    assert classify(False, DetectionStatus.CONFIRMED) == DiscrepancyType.DETECTED_NOT_ATTENDED
    assert classify(False, DetectionStatus.UNCERTAIN) == DiscrepancyType.NONE
    assert classify(False, DetectionStatus.NOT_DETECTED) == DiscrepancyType.NONE


def test_anthropic_provider_never_fabricates_an_unknown_student(monkeypatch):
    """Even if the model's tool call references a roll number it was never given, the provider
    must drop it rather than inventing an identity for it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-a-real-secret-0000000000")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.services.verification.anthropic_provider import AnthropicVisionProvider
        from app.services.verification.provider import StudentReference

        provider = AnthropicVisionProvider()
        block = SimpleNamespace(
            type="tool_use",
            name="report_classroom_observations",
            input={
                "observations": [
                    {"roll_number": "R001", "confidence": 0.9},
                    {"roll_number": "GHOST-NOT-A-REAL-STUDENT", "confidence": 0.99},
                ]
            },
        )
        monkeypatch.setattr(provider._client.messages, "create", lambda **kwargs: SimpleNamespace(content=[block]))

        known_id = uuid.uuid4()
        students = [
            StudentReference(student_id=known_id, full_name="A Student", roll_number="R001", image_bytes=b"x", content_type="image/jpeg")
        ]
        analysis = provider.analyze_classroom([b"classroom-photo"], students)
        assert len(analysis.observations) == 1
        assert analysis.observations[0].student_id == known_id
        assert analysis.observations[0].confidence == 0.9
    finally:
        get_settings.cache_clear()


def _provider_with_fake_response(monkeypatch, create_fn):
    """Builds a real AnthropicVisionProvider with its SDK client's .messages.create replaced by
    `create_fn`, so tests can drive the provider's response-parsing edge cases directly against
    the real request-building code without a network call."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-a-real-secret-0000000000")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.services.verification.anthropic_provider import AnthropicVisionProvider

    provider = AnthropicVisionProvider()
    monkeypatch.setattr(provider._client.messages, "create", create_fn)
    return provider


@pytest.fixture(autouse=True)
def _clear_settings_cache_after_anthropic_key_tests(monkeypatch):
    yield
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_anthropic_provider_missing_confidence_key_defaults_to_not_confident(monkeypatch):
    """A malformed observation missing `confidence` entirely must never be silently upgraded to
    a confident match — it should read as effectively zero, not crash."""
    from app.services.verification.provider import StudentReference

    block = SimpleNamespace(
        type="tool_use",
        name="report_classroom_observations",
        input={"observations": [{"roll_number": "R001"}]},  # no "confidence" key at all
    )
    provider = _provider_with_fake_response(monkeypatch, lambda **kwargs: SimpleNamespace(content=[block]))
    sid = uuid.uuid4()
    students = [StudentReference(student_id=sid, full_name="A", roll_number="R001", image_bytes=b"x", content_type="image/jpeg")]

    analysis = provider.analyze_classroom([b"photo"], students)
    assert len(analysis.observations) == 1
    assert analysis.observations[0].confidence == 0.0


def test_anthropic_provider_no_tool_use_block_yields_empty_observations(monkeypatch):
    """If the model somehow answers without calling the tool (a plain text block instead), the
    provider must not crash — it should report nobody detected, letting the comparison engine
    treat every student as NOT_DETECTED rather than guessing."""
    from app.services.verification.provider import StudentReference

    text_only = SimpleNamespace(type="text", text="I cannot help with that.")
    provider = _provider_with_fake_response(monkeypatch, lambda **kwargs: SimpleNamespace(content=[text_only]))
    students = [
        StudentReference(student_id=uuid.uuid4(), full_name="A", roll_number="R001", image_bytes=b"x", content_type="image/jpeg")
    ]

    analysis = provider.analyze_classroom([b"photo"], students)
    assert analysis.observations == []


def test_anthropic_provider_malformed_observations_shape_raises_instead_of_fabricating(monkeypatch):
    """`observations` being a string instead of a list is a genuinely malformed tool response.
    The provider must raise (letting the caller's generic failure handling take over — see
    test_invalid_ai_output_marks_verification_failed) rather than silently iterating characters
    and fabricating garbage observations."""
    from app.services.verification.provider import StudentReference

    block = SimpleNamespace(type="tool_use", name="report_classroom_observations", input={"observations": "not-a-list"})
    provider = _provider_with_fake_response(monkeypatch, lambda **kwargs: SimpleNamespace(content=[block]))
    students = [
        StudentReference(student_id=uuid.uuid4(), full_name="A", roll_number="R001", image_bytes=b"x", content_type="image/jpeg")
    ]

    try:
        provider.analyze_classroom([b"photo"], students)
        raised = False
    except AttributeError:
        raised = True
    assert raised, "a malformed 'observations' shape must raise, not silently produce garbage results"


def test_duplicate_ai_observation_for_the_same_student_does_not_duplicate_or_crash(
    client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch
):
    """The model reporting the same roll number twice (e.g. once per classroom photo) must
    collapse into exactly one result row, not violate uq_verification_student or double-count."""
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])

    class DuplicateObservationProvider:
        def analyze_classroom(self, images, students):
            sid = students[0].student_id
            return VisionAnalysis(observations=[StudentObservation(student_id=sid, confidence=0.5), StudentObservation(student_id=sid, confidence=0.95)])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: DuplicateObservationProvider())
    resp = _start_verification(client, professor_and_token, session_data["id"])
    detail = client.get(f"/api/verification/{resp.json()['id']}", headers=auth_headers(professor_and_token["access_token"])).json()
    assert detail["verification"]["status"] == "completed"
    assert len(detail["results"]) == 1


# ---------------------------------------------------------------------------
# End-to-end: create verification, image validation, RBAC
# ---------------------------------------------------------------------------


def test_start_verification_and_attended_and_detected(client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    _mark_present(client, professor_and_token, student_and_token, session_data["id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider({"R001": 0.95}))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "processing"
    verification_id = resp.json()["id"]

    # TestClient runs BackgroundTasks to completion before the POST above returns.
    detail = client.get(f"/api/verification/{verification_id}", headers=auth_headers(professor_and_token["access_token"]))
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["verification"]["status"] == "completed"
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["ai_status"] == "confirmed"
    assert result["discrepancy_type"] == "attended_and_detected"
    assert body["discrepancy_count"] == 0
    assert body["confirmed_count"] == 1


def test_unauthorized_professor_cannot_start_or_read_verification(client, db_session, professor_and_token, student_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])

    register_professor(client, email="other-prof@college.edu")
    other_token = login(client, "other-prof@college.edu").json()

    resp = _start_verification(client, other_token, session_data["id"])
    assert resp.status_code == 403

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider())
    owned = _start_verification(client, professor_and_token, session_data["id"])
    assert owned.status_code == 202
    read = client.get(f"/api/verification/{owned.json()['id']}", headers=auth_headers(other_token["access_token"]))
    assert read.status_code == 403


def test_student_cannot_access_verification_endpoints(client, db_session, professor_and_token, student_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider())
    denied_start = client.post(
        f"/api/verification/sessions/{session_data['id']}/verify",
        files=[("images", ("c.jpg", b"x", "image/jpeg"))],
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert denied_start.status_code == 403

    owned = _start_verification(client, professor_and_token, session_data["id"])
    assert owned.status_code == 202
    denied_read = client.get(
        f"/api/verification/{owned.json()['id']}", headers=auth_headers(student_and_token["access_token"])
    )
    assert denied_read.status_code == 403


def test_too_many_images_rejected(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    resp = _start_verification(client, professor_and_token, session_data["id"], n_images=4)
    assert resp.status_code == 422


def test_unsupported_image_type_rejected(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    resp = client.post(
        f"/api/verification/sessions/{session_data['id']}/verify",
        files=[("images", ("c.gif", b"x", "image/gif"))],
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 422


def test_multiple_images_accepted(client, db_session, professor_and_token, student_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider())
    resp = _start_verification(client, professor_and_token, session_data["id"], n_images=3)
    assert resp.status_code == 202
    assert resp.json()["image_count"] == 3


def test_students_without_reference_photo_are_excluded_not_guessed(client, db_session, professor_and_token, student_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    fake = FakeProvider({"R001": 0.9})
    monkeypatch.setattr(verification_service, "_get_provider", lambda: fake)
    resp = _start_verification(client, professor_and_token, session_data["id"])
    verification_id = resp.json()["id"]

    detail = client.get(f"/api/verification/{verification_id}", headers=auth_headers(professor_and_token["access_token"])).json()
    assert detail["results"] == []
    assert detail["students_excluded_no_reference_photo"] == 1
    assert fake.calls == []  # never even called the provider with zero photographed students


def test_invalid_ai_output_marks_verification_failed(client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider(raise_error=True))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    verification_id = resp.json()["id"]

    detail = client.get(f"/api/verification/{verification_id}", headers=auth_headers(professor_and_token["access_token"])).json()
    assert detail["verification"]["status"] == "failed"
    assert detail["verification"]["error_message"]
    # Regression: the student DOES have a reference photo on file — a provider failure must
    # never be misreported as "no reference photo" just because no results were produced.
    assert detail["students_excluded_no_reference_photo"] == 0


# ---------------------------------------------------------------------------
# Discrepancy review: professor decisions, violations, restrictions
# ---------------------------------------------------------------------------


def test_attended_not_detected_confirm_present_is_idempotent(client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    _mark_present(client, professor_and_token, student_and_token, session_data["id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider({"R001": 0.2}))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    verification_id = resp.json()["id"]
    detail = client.get(f"/api/verification/{verification_id}", headers=auth_headers(professor_and_token["access_token"])).json()
    result = detail["results"][0]
    assert result["discrepancy_type"] == "attended_not_detected"
    assert result["ai_status"] == "uncertain"

    decision = client.post(
        f"/api/verification/results/{result['id']}/decision",
        json={"action": "confirmed_present"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert decision.status_code == 200, decision.text

    dup = client.post(
        f"/api/verification/results/{result['id']}/decision",
        json={"action": "confirmed_present"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert dup.status_code == 409


def test_detected_not_attended_cannot_be_turned_into_a_violation(client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    # Deliberately never scan.

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider({"R001": 0.9}))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    verification_id = resp.json()["id"]
    detail = client.get(f"/api/verification/{verification_id}", headers=auth_headers(professor_and_token["access_token"])).json()
    result = detail["results"][0]
    assert result["discrepancy_type"] == "detected_not_attended"
    assert result["qr_present"] is False

    forbidden = client.post(
        f"/api/verification/results/{result['id']}/decision",
        json={"action": "violation", "reason": "proxy_attendance", "restriction_duration": "seven_days"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert forbidden.status_code == 422

    ok = client.post(
        f"/api/verification/results/{result['id']}/decision",
        json={"action": "asked_to_scan"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert ok.status_code == 200, ok.text


def test_violation_decision_creates_restriction_that_blocks_scanning(
    client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    _mark_present(client, professor_and_token, student_and_token, session_data["id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider({"R001": 0.0}))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    verification_id = resp.json()["id"]
    detail = client.get(f"/api/verification/{verification_id}", headers=auth_headers(professor_and_token["access_token"])).json()
    result = detail["results"][0]
    assert result["discrepancy_type"] == "attended_not_detected"

    decision = client.post(
        f"/api/verification/results/{result['id']}/decision",
        json={
            "action": "violation",
            "reason": "proxy_attendance",
            "restriction_duration": "seven_days",
            "notes": "Face never appeared in any classroom photo.",
        },
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert decision.status_code == 200, decision.text
    body = decision.json()
    assert body["violation_id"]
    assert body["restriction_end"]

    # Only one session may be active per class division at a time — close the first before
    # opening a second to test the restriction against.
    close_resp = client.post(
        f"/api/attendance/sessions/{session_data['id']}/close", headers=auth_headers(professor_and_token["access_token"])
    )
    assert close_resp.status_code == 200, close_resp.text

    lecture2 = _add_lecture(db_session, setup["class_division_id"])
    session2 = _create_session_via_api(client, professor_and_token, lecture2.id)
    live2 = client.get(f"/api/attendance/sessions/{session2['id']}/live", headers=auth_headers(professor_and_token["access_token"]))
    blocked = client.post(
        "/api/attendance/scan",
        json={"token": live2.json()["qr_payload"]},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert blocked.status_code == 423
    assert blocked.json()["detail"]["code"] == "attendance_restricted"

    # Student-facing restriction status endpoint also reflects the block.
    status_resp = client.get("/api/students/me/restriction", headers=auth_headers(student_and_token["access_token"]))
    assert status_resp.json()["active"] is True


def test_restriction_expires_on_its_own(db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    professor_profile = db_session.get(ProfessorProfile, setup["professor_profile_id"])
    violation = violation_service.create_violation(
        db_session,
        professor_profile=professor_profile,
        student_id=setup["student_profile_id"],
        lecture_id=setup["lecture_id"],
        session_id=None,
        verification_result_id=None,
        reason="other",
        notes=None,
        duration="one_day",
        custom_end=None,
    )
    db_session.commit()
    assert violation_service.get_active_restriction(db_session, setup["student_profile_id"]) is not None

    violation.restriction_end = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    assert violation_service.get_active_restriction(db_session, setup["student_profile_id"]) is None


def test_revoke_violation_unblocks_scanning(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    professor_profile = db_session.get(ProfessorProfile, setup["professor_profile_id"])
    violation = violation_service.create_violation(
        db_session,
        professor_profile=professor_profile,
        student_id=setup["student_profile_id"],
        lecture_id=setup["lecture_id"],
        session_id=None,
        verification_result_id=None,
        reason="other",
        notes=None,
        duration="seven_days",
        custom_end=None,
    )
    db_session.commit()

    lecture2 = _add_lecture(db_session, setup["class_division_id"])
    session2 = _create_session_via_api(client, professor_and_token, lecture2.id)
    live2 = client.get(f"/api/attendance/sessions/{session2['id']}/live", headers=auth_headers(professor_and_token["access_token"]))
    blocked = client.post(
        "/api/attendance/scan",
        json={"token": live2.json()["qr_payload"]},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert blocked.status_code == 423

    revoke = client.post(
        f"/api/verification/violations/{violation.id}/revoke",
        json={"revocation_reason": "Applied incorrectly, confirmed via CCTV."},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "revoked"

    # Revoking twice must not silently "succeed" a second time.
    again = client.post(
        f"/api/verification/violations/{violation.id}/revoke",
        json={"revocation_reason": "duplicate"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert again.status_code == 409

    live3 = client.get(f"/api/attendance/sessions/{session2['id']}/live", headers=auth_headers(professor_and_token["access_token"]))
    allowed = client.post(
        "/api/attendance/scan",
        json={"token": live3.json()["qr_payload"]},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert allowed.status_code == 200, allowed.text


def test_violation_action_without_reason_is_rejected(
    client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    _mark_present(client, professor_and_token, student_and_token, session_data["id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider({"R001": 0.0}))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    detail = client.get(
        f"/api/verification/{resp.json()['id']}", headers=auth_headers(professor_and_token["access_token"])
    ).json()
    result_id = detail["results"][0]["id"]

    # No `reason` and no `restriction_duration` at all — the request-body validator must reject
    # this before it ever reaches the discrepancy-type/action check.
    missing_reason = client.post(
        f"/api/verification/results/{result_id}/decision",
        json={"action": "violation"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert missing_reason.status_code == 422

    # restriction_duration="custom" without an end date must also be rejected.
    missing_custom_end = client.post(
        f"/api/verification/results/{result_id}/decision",
        json={"action": "violation", "reason": "proxy_attendance", "restriction_duration": "custom"},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert missing_custom_end.status_code == 422


def test_duplicate_violation_decision_is_rejected_and_creates_only_one_violation(
    client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch
):
    from app.models.verification import AttendanceViolation

    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    _upload_reference_photo(client, admin_and_token, setup["student_profile_id"])
    session_data = _create_session_via_api(client, professor_and_token, setup["lecture_id"])
    _mark_present(client, professor_and_token, student_and_token, session_data["id"])

    monkeypatch.setattr(verification_service, "_get_provider", lambda: FakeProvider({"R001": 0.0}))
    resp = _start_verification(client, professor_and_token, session_data["id"])
    detail = client.get(
        f"/api/verification/{resp.json()['id']}", headers=auth_headers(professor_and_token["access_token"])
    ).json()
    result_id = detail["results"][0]["id"]

    payload = {"action": "violation", "reason": "proxy_attendance", "restriction_duration": "seven_days"}
    first = client.post(
        f"/api/verification/results/{result_id}/decision", json=payload, headers=auth_headers(professor_and_token["access_token"])
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/verification/results/{result_id}/decision", json=payload, headers=auth_headers(professor_and_token["access_token"])
    )
    assert second.status_code == 409

    db_session.expire_all()
    assert db_session.query(AttendanceViolation).filter(AttendanceViolation.verification_result_id == result_id).count() == 1


def test_professor_cannot_revoke_another_professors_violation(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    professor_profile = db_session.get(ProfessorProfile, setup["professor_profile_id"])
    violation = violation_service.create_violation(
        db_session,
        professor_profile=professor_profile,
        student_id=setup["student_profile_id"],
        lecture_id=setup["lecture_id"],
        session_id=None,
        verification_result_id=None,
        reason="other",
        notes=None,
        duration="one_day",
        custom_end=None,
    )
    db_session.commit()

    register_professor(client, email="other-prof-2@college.edu")
    other_token = login(client, "other-prof-2@college.edu").json()
    resp = client.post(
        f"/api/verification/violations/{violation.id}/revoke",
        json={"revocation_reason": "not mine"},
        headers=auth_headers(other_token["access_token"]),
    )
    assert resp.status_code == 403
