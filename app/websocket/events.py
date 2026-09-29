from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.schemas import MessageType

logger = logging.getLogger(__name__)

router = APIRouter()

_event_clients: set[WebSocket] = set()
_WS_MAX_TEXT_BYTES = 64 * 1024


async def _authenticate(ws: WebSocket) -> bool:
    """Expect {"type":"auth","token":"<access_token>"} within 5 s. Return True on success."""
    try:
        raw = await asyncio.wait_for(ws.receive(), timeout=5.0)
    except asyncio.TimeoutError:
        await ws.close(code=1008)
        return False

    text = raw.get("text", "")
    if not text:
        await ws.close(code=1008)
        return False

    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        await ws.close(code=1008)
        return False

    if msg.get("type") != "auth" or not msg.get("token"):
        await ws.close(code=1008)
        return False

    try:
        from app.auth.tokens import decode_access_token
        from app.db import User, async_session
        payload = decode_access_token(msg["token"])
        user_id = int(payload["sub"])
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user is None or not user.is_active:
                await ws.close(code=1008)
                return False
    except Exception:
        await ws.close(code=1008)
        return False

    ws.state.user_id = user_id
    return True


@router.websocket("/ws/events")
async def events_endpoint(ws: WebSocket):
    await ws.accept()

    if not await _authenticate(ws):
        return

    _event_clients.add(ws)
    logger.info("Events WebSocket connected (total: %d)", len(_event_clients))

    try:
        while True:
            text = await ws.receive_text()
            if len(text.encode()) > _WS_MAX_TEXT_BYTES:
                await ws.send_json({"type": "error", "payload": {"message": "Message too large"}})
                continue
            if text == "ping":
                await ws.send_json({"type": MessageType.PONG.value, "payload": {}})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Events WebSocket error")
    finally:
        _event_clients.discard(ws)
        logger.info("Events WebSocket disconnected (total: %d)", len(_event_clients))


# ── Broadcast helpers ─────────────────────────────────────


async def broadcast_event(msg_type: MessageType, payload: dict):
    if not _event_clients:
        return
    dead: set[WebSocket] = set()
    message = {"type": msg_type.value, "payload": payload}
    for ws in _event_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    _event_clients.difference_update(dead)


async def _broadcast_raw(message: dict):
    if not _event_clients:
        return
    dead: set[WebSocket] = set()
    for ws in _event_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    _event_clients.difference_update(dead)


async def push_notification(
    event_type: str,
    priority: str,
    title: str,
    body: str = "",
    data: Optional[dict] = None,
) -> int:
    """Store a notification in the database and broadcast it to connected clients."""
    from app.db import NotificationLog, async_session

    notif_id = 0

    if async_session is not None:
        async with async_session() as session:
            notif = NotificationLog(
                event_type=event_type,
                priority=priority,
                title=title,
                body=body,
                data=json.dumps(data) if data else None,
            )
            session.add(notif)
            await session.flush()
            await session.refresh(notif)
            notif_id = notif.id
            await session.commit()
    else:
        logger.warning("push_notification called before DB init — not persisted")

    payload = {
        "id": notif_id,
        "event_type": event_type,
        "priority": priority,
        "title": title,
        "body": body,
        "data": data or {},
    }

    await _broadcast_raw({"type": "notification", "payload": payload})

    logger.info(
        "Notification pushed: [%s] %s — %s (id=%d)",
        priority, event_type, title, notif_id,
    )

    return notif_id
