"""
Push notification endpoints for mobile app registration
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.notifications.push_service import get_push_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push", tags=["push"])


class RegisterTokenRequest(BaseModel):
    token: str
    platform: str  # "ios" or "android"
    device_id: str | None = None


class UnregisterTokenRequest(BaseModel):
    token: str


class TestNotificationRequest(BaseModel):
    title: str = "Test from Athena"
    body: str = "This is a test notification"


@router.post("/register")
async def register_push_token(request: RegisterTokenRequest):
    """
    Register a push notification token from mobile app
    Called when user opens the app
    """
    push_service = get_push_service()
    result = await push_service.register_token(
        token=request.token,
        platform=request.platform,
        device_id=request.device_id
    )
    return result


@router.post("/unregister")
async def unregister_push_token(request: UnregisterTokenRequest):
    """
    Unregister a push token
    Called when user logs out or disables notifications
    """
    push_service = get_push_service()
    result = await push_service.unregister_token(request.token)
    return result


@router.post("/test")
async def send_test_notification(request: TestNotificationRequest):
    """
    Send a test notification to all registered devices
    Useful for debugging
    """
    push_service = get_push_service()
    result = await push_service.send_push_notification(
        title=request.title,
        body=request.body,
        priority="high",
        data={"type": "test"}
    )
    return result
