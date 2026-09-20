import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.db import SessionLocal
from app.core.deps import authenticate
from app.services.attendance_service import authorize_session_owner
from app.services.realtime import manager

router = APIRouter()
logger = logging.getLogger("proxybusters.ws")

AUTH_TIMEOUT_SECONDS = 10


def _authorize(token: str, session_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        current = authenticate(token, db)
        authorize_session_owner(db, session_id, current.user)
    finally:
        db.close()


@router.websocket("/ws/attendance/sessions/{session_id}")
async def attendance_session_ws(websocket: WebSocket, session_id: uuid.UUID):
    """Live feed for the owning professor only.

    Authentication is the FIRST message ({"type": "auth", "token": "<jwt>"}), not a query-string
    parameter: URLs are written to proxy/server access logs, so a JWT in the URL would leak a
    live credential into logs. The socket is accepted, but joins the room (and receives the QR
    stream) only after the token authenticates AND the user owns the session.
    """
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        message = json.loads(raw)
        token = message.get("token") if isinstance(message, dict) and message.get("type") == "auth" else None
        if not isinstance(token, str) or not token:
            raise ValueError("missing auth message")
        await asyncio.to_thread(_authorize, token, session_id)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 - any auth or authorization failure closes the socket
        logger.info("WebSocket rejected for session_id=%s", session_id)
        await websocket.close(code=4403)
        return

    room = str(session_id)
    manager.connect(room, websocket)
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            text = await websocket.receive_text()
            if text == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("WebSocket error session_id=%s", session_id, exc_info=True)
    finally:
        manager.disconnect(room, websocket)
