import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.db import SessionLocal
from app.core.deps import authenticate
from app.services.attendance_service import authorize_session_access
from app.services.realtime import manager

router = APIRouter()


@router.websocket("/ws/attendance/sessions/{session_id}")
async def attendance_session_ws(websocket: WebSocket, session_id: uuid.UUID):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        current = authenticate(token, db)
        authorize_session_access(db, session_id, current.user)
    except Exception:  # noqa: BLE001 - any auth or authorization failure closes the socket
        await websocket.close(code=4403)
        return
    finally:
        db.close()

    await websocket.accept()
    room = str(session_id)
    manager.connect(room, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(room, websocket)
