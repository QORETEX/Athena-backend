from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.schemas import MessageType

logger = logging.getLogger(__name__)

router = APIRouter()

_event_clients: set[WebSocket] = set()


# ── WebSocket endpoint ────────────────────────────────────


@router.websocket("/ws/events")
async def events_endpoint(ws: WebSocket):
    await ws.accept()
    _event_clients.add(ws)
    logger.info("Events WebSocket connected (total: %d)", len(_event_clients))

    try:
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_json(
                    {"type": MessageType.PONG.value, "payload": {}}
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Events WebSocket error")
    finally:
        _event_clients.discard(ws)
        logger.info("Events WebSocket disconnected (total: %d)", len(_event_clients))


# ── Broadcast helpers ─────────────────────────────────────


async def broadcast_event(msg_type: MessageType, payload: dict):
    """Broadcast a typed event to all connected WebSocket clients."""
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
    """Broadcast a raw dict message to all connected clients."""
    if not _event_clients:
        return

    dead: set[WebSocket] = set()
    for ws in _event_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)

    _event_clients.difference_update(dead)


# ── Push notification (persisted + broadcast) ─────────────


async def push_notification(
    event_type: str,
    priority: str,
    title: str,
    body: str = "",
    data: Optional[dict] = None,
) -> int:
    """
    Store a notification in the database and broadcast it to all connected
    WebSocket clients. Returns the notification ID.

    Can be called from anywhere (non-route code, background tasks, etc.)
    """
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
        priority,
        event_type,
        title,
        notif_id,
    )

    return notif_id
