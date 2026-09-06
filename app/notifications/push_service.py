"""
Expo Push Notification Service for JARVIS Proactive Alerts
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests
from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import PushToken, NotificationLog, async_session

logger = logging.getLogger(__name__)


class ExpoPushService:
    """Service for sending push notifications via Expo"""

    def __init__(self):
        # Optional: Configure session with Expo access token
        self.session = requests.Session()
        expo_token = os.getenv("EXPO_ACCESS_TOKEN")
        if expo_token:
            self.session.headers.update({
                "Authorization": f"Bearer {expo_token}",
                "accept": "application/json",
                "accept-encoding": "gzip, deflate",
                "content-type": "application/json",
            })

        self.client = PushClient(session=self.session)

    async def send_push_notification(
        self,
        title: str,
        body: str,
        priority: str = "high",
        data: Optional[dict] = None,
        sound: str = "default",
        badge: Optional[int] = None
    ) -> dict:
        """
        Send push notification to all active devices

        Args:
            title: Notification title
            body: Notification body text
            priority: "default" or "high" (high wakes up device)
            data: Optional data payload
            sound: Sound to play ("default" or None for silent)
            badge: Badge number for iOS

        Returns:
            dict with status and details
        """
        async with async_session() as session:
            # Get all active push tokens
            result = await session.execute(
                select(PushToken).where(PushToken.is_active == True)
            )
            tokens = result.scalars().all()

            if not tokens:
                logger.warning("No active push tokens to send notification")
                return {"status": "error", "message": "No active devices"}

            # Log notification
            notification_log = NotificationLog(
                event_type="jarvis_proactive",
                priority=priority,
                title=title,
                body=body,
                data=str(data) if data else None
            )
            session.add(notification_log)
            await session.commit()

            # Send to all devices
            results = []
            for token in tokens:
                result = await self._send_to_token(
                    token.token,
                    title,
                    body,
                    priority,
                    data,
                    sound,
                    badge,
                    session
                )
                results.append(result)

            success_count = sum(1 for r in results if r.get("status") == "ok")
            return {
                "status": "ok",
                "sent_to": success_count,
                "total_devices": len(tokens),
                "results": results
            }

    async def _send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        priority: str,
        data: Optional[dict],
        sound: str,
        badge: Optional[int],
        session: AsyncSession
    ) -> dict:
        """Send push notification to a single token"""
        try:
            # Validate token format
            if not self._is_valid_expo_token(token):
                logger.warning(f"Invalid Expo token format: {token}")
                return {"status": "error", "message": "Invalid token format"}

            # Create push message
            message = PushMessage(
                to=token,
                title=title,
                body=body,
                data=data or {},
                sound=sound,
                badge=badge,
                priority=priority,
                channel_id="jarvis-alerts"  # Android notification channel
            )

            # Send
            response = self.client.publish(message)

            logger.info(f"Push notification sent: {title} (token: {token[:20]}...)")
            return {"status": "ok", "response": str(response)}

        except DeviceNotRegisteredError:
            # Token is no longer valid - deactivate it
            logger.warning(f"Device not registered, deactivating token: {token[:20]}...")
            await self._deactivate_token(token, session)
            return {"status": "error", "message": "Device not registered"}

        except PushTicketError as e:
            logger.error(f"Push ticket error: {e}")
            return {"status": "error", "message": str(e)}

        except PushServerError as e:
            logger.error(f"Push server error: {e}")
            return {"status": "error", "message": str(e)}

        except Exception as e:
            logger.error(f"Unexpected push notification error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _is_valid_expo_token(self, token: str) -> bool:
        """Validate Expo push token format"""
        # Expo tokens start with ExponentPushToken[...] or ExpoPushToken[...]
        return (
            token.startswith("ExponentPushToken[") or
            token.startswith("ExpoPushToken[")
        ) and token.endswith("]")

    async def _deactivate_token(self, token: str, session: AsyncSession):
        """Deactivate a push token that's no longer valid"""
        result = await session.execute(
            select(PushToken).where(PushToken.token == token)
        )
        push_token = result.scalar_one_or_none()

        if push_token:
            push_token.is_active = False
            await session.commit()
            logger.info(f"Deactivated push token: {token[:20]}...")

    async def register_token(
        self,
        token: str,
        platform: str,
        device_id: Optional[str] = None
    ) -> dict:
        """Register a new push token"""
        if not self._is_valid_expo_token(token):
            return {"status": "error", "message": "Invalid Expo token format"}

        async with async_session() as session:
            # Check if token already exists
            result = await session.execute(
                select(PushToken).where(PushToken.token == token)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing token
                existing.is_active = True
                existing.device_id = device_id
                existing.platform = platform
                logger.info(f"Updated push token: {token[:20]}...")
            else:
                # Create new token
                new_token = PushToken(
                    token=token,
                    platform=platform,
                    device_id=device_id,
                    is_active=True
                )
                session.add(new_token)
                logger.info(f"Registered new push token: {token[:20]}...")

            await session.commit()

            return {"status": "ok", "message": "Token registered"}

    async def unregister_token(self, token: str) -> dict:
        """Unregister a push token"""
        async with async_session() as session:
            result = await session.execute(
                select(PushToken).where(PushToken.token == token)
            )
            push_token = result.scalar_one_or_none()

            if push_token:
                push_token.is_active = False
                await session.commit()
                logger.info(f"Unregistered push token: {token[:20]}...")
                return {"status": "ok", "message": "Token unregistered"}
            else:
                return {"status": "error", "message": "Token not found"}


# Global instance
_push_service: Optional[ExpoPushService] = None


def get_push_service() -> ExpoPushService:
    """Get or create push service instance"""
    global _push_service
    if _push_service is None:
        _push_service = ExpoPushService()
    return _push_service
