import asyncio
import uuid

from fastapi import WebSocket

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.attendance import AttendanceSession, SessionStatus

settings = get_settings()


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


async def rotate_qr_loop(session_id: uuid.UUID) -> None:
    # Local imports to avoid a circular import with attendance_service at module load time.
    from app.services.attendance_service import encode_qr_payload, issue_token

    while True:
        db = SessionLocal()
        try:
            session_obj = db.get(AttendanceSession, session_id)
            if session_obj is None or session_obj.status != SessionStatus.ACTIVE:
                break
            token = issue_token(db, session_obj)
            payload = {
                "type": "qr",
                "token": encode_qr_payload(token),
                "expires_at": token.expires_at.isoformat(),
            }
        finally:
            db.close()
        await manager.broadcast(str(session_id), payload)
        await asyncio.sleep(settings.qr_token_ttl_seconds)


def start_rotation(session_id: uuid.UUID) -> None:
    if session_id in _rotation_tasks and not _rotation_tasks[session_id].done():
        return
    task = asyncio.create_task(rotate_qr_loop(session_id))
    _rotation_tasks[session_id] = task


def stop_rotation(session_id: uuid.UUID) -> None:
    task = _rotation_tasks.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()
