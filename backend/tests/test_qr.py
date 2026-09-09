import base64
import hashlib
import hmac
from datetime import timedelta

from app.core.config import get_settings
from app.core.time import ensure_utc, utcnow
from app.models.attendance import AttendanceSession, AttendanceToken, SessionStatus
from tests.conftest import auth_headers, make_class_setup

settings = get_settings()


def _start_session_and_get_payload(client, db_session, professor_token, student_token):
    setup = make_class_setup(db_session, professor_token["user_id"], student_token["user_id"])
    resp = client.post(
        "/api/attendance/sessions",
        json={"lecture_id": str(setup["lecture_id"])},
        headers=auth_headers(professor_token["access_token"]),
    )
    assert resp.status_code == 201, resp.text
    session_id = resp.json()["id"]

    live = client.get(
        f"/api/attendance/sessions/{session_id}/live", headers=auth_headers(professor_token["access_token"])
    )
    assert live.status_code == 200, live.text
    return session_id, live.json()["qr_payload"], setup


def test_valid_scan_marks_attendance(client, db_session, professor_and_token, student_and_token):
    session_id, payload, _setup = _start_session_and_get_payload(
        client, db_session, professor_and_token, student_and_token
    )
    resp = client.post(
        "/api/attendance/scan", json={"token": payload}, headers=auth_headers(student_and_token["access_token"])
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "marked"


def test_replayed_token_rejected(client, db_session, professor_and_token, student_and_token):
    session_id, payload, _setup = _start_session_and_get_payload(
        client, db_session, professor_and_token, student_and_token
    )
    first = client.post(
        "/api/attendance/scan", json={"token": payload}, headers=auth_headers(student_and_token["access_token"])
    )
    assert first.status_code == 200

    second = client.post(
        "/api/attendance/scan", json={"token": payload}, headers=auth_headers(student_and_token["access_token"])
    )
    assert second.status_code == 409


def test_expired_token_rejected(client, db_session, professor_and_token, student_and_token):
    session_id, payload, _setup = _start_session_and_get_payload(
        client, db_session, professor_and_token, student_and_token
    )
    # Manually expire the freshly-issued token.
    token = db_session.query(AttendanceToken).filter(AttendanceToken.session_id == session_id).first()
    token.expires_at = utcnow() - timedelta(seconds=5)
    db_session.commit()

    resp = client.post(
        "/api/attendance/scan", json={"token": payload}, headers=auth_headers(student_and_token["access_token"])
    )
    assert resp.status_code == 410


def test_tampered_signature_rejected(client, db_session, professor_and_token, student_and_token):
    session_id, payload, _setup = _start_session_and_get_payload(
        client, db_session, professor_and_token, student_and_token
    )
    decoded = base64.urlsafe_b64decode(payload.encode()).decode()
    session_id_str, nonce, issued_at_ts, expires_at_ts, signature = decoded.split(".", 4)
    tampered_signature = "0" * len(signature)
    tampered = f"{session_id_str}.{nonce}.{issued_at_ts}.{expires_at_ts}.{tampered_signature}"
    tampered_payload = base64.urlsafe_b64encode(tampered.encode()).decode()

    resp = client.post(
        "/api/attendance/scan",
        json={"token": tampered_payload},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 400


def test_spliced_session_id_rejected(client, db_session, professor_and_token, student_and_token):
    """Swapping in a different session_id changes the signed payload, so the signature
    (computed with a secret the client never has) no longer matches -> rejected."""
    session_id, payload, _setup = _start_session_and_get_payload(
        client, db_session, professor_and_token, student_and_token
    )
    decoded = base64.urlsafe_b64decode(payload.encode()).decode()
    _session_id_str, nonce, issued_at_ts, expires_at_ts, signature = decoded.split(".", 4)
    fake_session_id = "00000000-0000-0000-0000-000000000000"
    forged = f"{fake_session_id}.{nonce}.{issued_at_ts}.{expires_at_ts}.{signature}"
    forged_payload = base64.urlsafe_b64encode(forged.encode()).decode()

    resp = client.post(
        "/api/attendance/scan",
        json={"token": forged_payload},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 400


def test_scan_after_session_closed_rejected(client, db_session, professor_and_token, student_and_token):
    session_id, payload, _setup = _start_session_and_get_payload(
        client, db_session, professor_and_token, student_and_token
    )
    close_resp = client.post(
        f"/api/attendance/sessions/{session_id}/close", headers=auth_headers(professor_and_token["access_token"])
    )
    assert close_resp.status_code == 200

    resp = client.post(
        "/api/attendance/scan", json={"token": payload}, headers=auth_headers(student_and_token["access_token"])
    )
    assert resp.status_code == 409


def test_garbage_payload_rejected(client, student_and_token):
    resp = client.post(
        "/api/attendance/scan",
        json={"token": "not-a-valid-base64-payload"},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 400
