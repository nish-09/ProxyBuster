import asyncio
import logging
import uuid
from datetime import timedelta

from fastapi import WebSocket
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.time import ensure_utc, utcnow
from app.models.academic import Lecture
from app.models.attendance import AttendanceSession, AttendanceToken, SessionStatus

settings = get_settings()
logger = logging.getLogger("proxybusters.realtime")

MAINTENANCE_INTERVAL_SECONDS = 60


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = {}

    def connect(self, session_id: str, ws: WebSocket) -> None:
        self.rooms.setdefault(session_id, set()).add(ws)

    def disconnect(self, session_id: str, ws: WebSocket) -> None:
        room = self.rooms.get(session_id)
        if room is not None:
            room.discard(ws)
            if not room:
                self.rooms.pop(session_id, None)

    async def broadcast(self, session_id: str, message: dict) -> None:
        room = self.rooms.get(session_id)
        if not room:
            return
        message = {**message, "server_time": utcnow().isoformat()}
        dead: list[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - drop any socket that fails to receive
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)


manager = ConnectionManager()

_rotation_tasks: dict[uuid.UUID, asyncio.Task] = {}


def _closed_message(status: SessionStatus) -> dict:
    return {"type": "closed", "status": status.value}


def _rotate_once(session_id: uuid.UUID) -> tuple[bool, dict]:
    """Blocking (DB) work for one rotation tick — run via asyncio.to_thread so it never stalls
    the event loop. Returns (keep_rotating, message_to_broadcast)."""
    # Local import to avoid a circular import with attendance_service at module load time.
    from app.services.attendance_service import (
        _expire_if_overdue,
        encode_qr_payload,
        issue_token,
    )

    db = SessionLocal()
    try:
        session_obj = db.get(AttendanceSession, session_id)
        if session_obj is None:
            return False, _closed_message(SessionStatus.CLOSED)
        if session_obj.status != SessionStatus.ACTIVE:
            return False, _closed_message(session_obj.status)
        lecture = db.get(Lecture, session_obj.lecture_id)
        if _expire_if_overdue(db, session_obj, lecture):
            return False, _closed_message(session_obj.status)
        token = issue_token(db, session_obj)
        return True, {
            "type": "qr",
            "token": encode_qr_payload(token),
            "expires_at": ensure_utc(token.expires_at).isoformat(),
            "ttl_seconds": settings.qr_token_ttl_seconds,
        }
    finally:
        db.close()


MAX_CONSECUTIVE_ROTATION_FAILURES = 10


async def rotate_qr_loop(session_id: uuid.UUID) -> None:
    failures = 0
    while True:
        try:
            keep_going, message = await asyncio.to_thread(_rotate_once, session_id)
            failures = 0
        except Exception:  # noqa: BLE001 - a transient DB error must not kill rotation for good
            failures += 1
            logger.exception("QR rotation tick failed session_id=%s (%s in a row)", session_id, failures)
            if failures >= MAX_CONSECUTIVE_ROTATION_FAILURES:
                # Give up; the maintenance loop restarts rotation for any session still ACTIVE.
                break
            await asyncio.sleep(2)
            continue
        await manager.broadcast(str(session_id), message)
        if not keep_going:
            break
        await asyncio.sleep(settings.qr_token_ttl_seconds)
    _rotation_tasks.pop(session_id, None)


async def rotate_now(session_id: uuid.UUID) -> None:
    """Immediately mint + broadcast a fresh QR. Called after a successful scan: tokens are
    single-use, so the one on the professor's screen was just consumed and must be replaced at
    once instead of leaving every other student scanning a dead code until the next tick."""
    try:
        keep_going, message = await asyncio.to_thread(_rotate_once, session_id)
    except Exception:  # noqa: BLE001
        logger.exception("Immediate QR rotation failed session_id=%s", session_id)
        return
    await manager.broadcast(str(session_id), message)
    if keep_going:
        start_rotation(session_id)


def start_rotation(session_id: uuid.UUID) -> None:
    existing = _rotation_tasks.get(session_id)
    if existing is not None and not existing.done():
        return
    _rotation_tasks[session_id] = asyncio.create_task(rotate_qr_loop(session_id))


def stop_rotation(session_id: uuid.UUID) -> None:
    task = _rotation_tasks.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()


def _maintenance_once() -> list[uuid.UUID]:
    """Blocking maintenance pass. Returns ids of sessions that are still ACTIVE."""
    from app.services.attendance_service import expire_overdue_sessions

    db = SessionLocal()
    try:
        expire_overdue_sessions(db)
        cutoff = utcnow() - timedelta(hours=settings.qr_token_retention_hours)
        pruned = db.execute(delete(AttendanceToken).where(AttendanceToken.issued_at < cutoff)).rowcount
        db.commit()
        if pruned:
            logger.info("Pruned %s old QR tokens", pruned)
        return [row[0] for row in db.query(AttendanceSession.id).filter(AttendanceSession.status == SessionStatus.ACTIVE).all()]
    finally:
        db.close()


async def maintenance_loop() -> None:
    """Runs for the life of the process: expires sessions whose time is up (so nobody depends on
    a professor's browser being open for that to happen), restarts QR rotation for sessions that
    were ACTIVE when the process restarted (Render restarts/deploys otherwise strand them), and
    prunes old QR tokens so the table does not grow without bound."""
    while True:
        try:
            active_ids = await asyncio.to_thread(_maintenance_once)
            for session_id in active_ids:
                start_rotation(session_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Maintenance pass failed; will retry")
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
