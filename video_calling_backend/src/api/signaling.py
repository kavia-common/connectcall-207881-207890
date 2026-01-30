import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from src.api.models import CallSession


class SignalingManager:
    """
    In-memory connection registry for WebSocket signaling.

    Mapping:
      - user_id -> websocket

    This allows relaying SDP offers/answers and ICE candidates between authenticated users.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connections: dict[uuid.UUID, WebSocket] = {}

    async def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        """Register a user's websocket."""
        async with self._lock:
            self._connections[user_id] = websocket

    async def disconnect(self, user_id: uuid.UUID) -> None:
        """Unregister a user's websocket."""
        async with self._lock:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: uuid.UUID, message: Dict[str, Any]) -> bool:
        """Send a JSON message to a connected user, returning True if delivered."""
        async with self._lock:
            ws = self._connections.get(user_id)

        if not ws:
            return False

        await ws.send_text(json.dumps(message))
        return True


manager = SignalingManager()


def _get_uuid(value: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _touch_call_session(db: Session, *, room_id: str, caller_id: uuid.UUID, callee_id: uuid.UUID, event_type: str) -> None:
    """
    Create or update a call session record for observability.
    """
    existing = db.query(CallSession).filter(CallSession.room_id == room_id, CallSession.active.is_(True)).first()
    if not existing:
        db.add(
            CallSession(
                room_id=room_id,
                caller_user_id=caller_id,
                callee_user_id=callee_id,
                active=True,
                last_event_type=event_type,
                last_event_at=datetime.utcnow(),
            )
        )
        return

    existing.last_event_type = event_type
    existing.last_event_at = datetime.utcnow()
    if event_type == "hangup":
        existing.active = False
        existing.ended_at = datetime.utcnow()


async def signaling_loop(
    *,
    websocket: WebSocket,
    current_user_id: uuid.UUID,
    db: Session,
) -> None:
    """
    Receive signaling messages from current_user and relay them to target users.

    Expected message format from client:
      { "type": "offer" | "answer" | "candidate" | "hangup",
        "to": "<target_user_id>",
        "roomId": "<client-generated room id>",
        ... payload fields ... }

    Server forwards:
      { "type": "<same>",
        "from": "<current_user_id>",
        "roomId": "<roomId>",
        ... payload fields ... }
    """
    await manager.connect(current_user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            msg_type = str(msg.get("type") or "").strip()
            to_id = _get_uuid(msg.get("to"))
            room_id = str(msg.get("roomId") or "").strip() or "default"

            if msg_type not in {"offer", "answer", "candidate", "hangup"}:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Unknown message type."}))
                continue

            if not to_id:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Missing/invalid 'to' user id."}))
                continue

            # Update session metadata best-effort (not required for signaling to work).
            try:
                _touch_call_session(db, room_id=room_id, caller_id=current_user_id, callee_id=to_id, event_type=msg_type)
                db.commit()
            except Exception:
                db.rollback()

            forward = {k: v for k, v in msg.items() if k not in {"to"}}
            forward["from"] = str(current_user_id)
            forward["roomId"] = room_id

            delivered = await manager.send_to_user(to_id, forward)
            if not delivered:
                await websocket.send_text(json.dumps({"type": "peer_offline", "to": str(to_id), "roomId": room_id}))

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(current_user_id)
