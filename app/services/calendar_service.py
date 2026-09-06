"""
Calendar Integration Service - Google Calendar API
"""
from __future__ import annotations

import logging
import os
import pickle
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from app.db import async_session, Meeting

logger = logging.getLogger(__name__)


class CalendarService:
    """
    Google Calendar integration for meeting intelligence

    Setup:
    1. Enable Google Calendar API
    2. Use same credentials as Gmail
    3. Sync meetings to database
    """

    def __init__(self):
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        self.calendar_service = None

    async def initialize(self):
        """Initialize Google Calendar API"""
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

            creds = None
            token_path = 'token_calendar.pickle'

            if os.path.exists(token_path):
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not self.credentials_path:
                        logger.warning("Calendar credentials not configured")
                        return False

                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)

            self.calendar_service = build('calendar', 'v3', credentials=creds)
            logger.info("✅ Google Calendar API initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Calendar API: {e}")
            return False

    async def sync_upcoming_meetings(self, days_ahead: int = 7) -> list[dict]:
        """Sync upcoming meetings from Google Calendar"""
        if not self.calendar_service:
            await self.initialize()

        if not self.calendar_service:
            return []

        try:
            now = datetime.utcnow().isoformat() + 'Z'
            end_date = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'

            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=end_date,
                maxResults=50,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            meetings = []

            for event in events:
                meeting_data = await self._parse_event(event)
                if meeting_data:
                    await self._store_meeting(meeting_data)
                    meetings.append(meeting_data)

            logger.info(f"Synced {len(meetings)} meetings")
            return meetings

        except Exception as e:
            logger.error(f"Failed to sync meetings: {e}")
            return []

    async def _parse_event(self, event: dict) -> Optional[dict]:
        """Parse calendar event"""
        try:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))

            # Parse datetime
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

            # Get attendees
            attendees = []
            if 'attendees' in event:
                attendees = [a.get('email', '') for a in event['attendees']]

            return {
                'calendar_event_id': event['id'],
                'title': event.get('summary', 'No Title'),
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'attendees': attendees,
                'start_time': start_dt,
                'end_time': end_dt
            }

        except Exception as e:
            logger.error(f"Failed to parse event: {e}")
            return None

    async def _store_meeting(self, meeting_data: dict):
        """Store meeting in database"""
        async with async_session() as session:
            # Check if exists
            result = await session.execute(
                select(Meeting).where(
                    Meeting.calendar_event_id == meeting_data['calendar_event_id']
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing
                existing.title = meeting_data['title']
                existing.description = meeting_data['description']
                existing.location = meeting_data['location']
                existing.start_time = meeting_data['start_time']
                existing.end_time = meeting_data['end_time']
            else:
                # Create new
                import json
                meeting = Meeting(
                    calendar_event_id=meeting_data['calendar_event_id'],
                    title=meeting_data['title'],
                    description=meeting_data['description'],
                    location=meeting_data['location'],
                    attendees=json.dumps(meeting_data['attendees']),
                    start_time=meeting_data['start_time'],
                    end_time=meeting_data['end_time']
                )
                session.add(meeting)

            await session.commit()

    async def get_next_meeting(self) -> Optional[dict]:
        """Get next upcoming meeting"""
        async with async_session() as session:
            now = datetime.now(timezone.utc)

            result = await session.execute(
                select(Meeting).where(
                    Meeting.start_time >= now
                ).order_by(Meeting.start_time.asc()).limit(1)
            )
            meeting = result.scalar_one_or_none()

            if meeting:
                import json
                return {
                    'id': meeting.id,
                    'title': meeting.title,
                    'start_time': meeting.start_time.isoformat(),
                    'location': meeting.location,
                    'attendees': json.loads(meeting.attendees),
                    'minutes_until': int((meeting.start_time - now).total_seconds() / 60)
                }

            return None

    async def prepare_meeting_brief(self, meeting_id: int) -> str:
        """Generate meeting preparation brief"""
        async with async_session() as session:
            result = await session.execute(
                select(Meeting).where(Meeting.id == meeting_id)
            )
            meeting = result.scalar_one_or_none()

            if not meeting:
                return "Meeting not found"

            # Use Claude to generate brief
            from app.llm_claude import get_claude_llm
            import json

            claude = get_claude_llm()

            try:
                attendees = json.loads(meeting.attendees)

                response = await claude.chat(
                    messages=[{
                        "role": "user",
                        "content": f"""Generate a concise meeting preparation brief:

Meeting: {meeting.title}
Time: {meeting.start_time}
Location: {meeting.location}
Attendees: {', '.join(attendees)}
Description: {meeting.description}

Provide:
1. Key objectives
2. Important context
3. Action items to prepare

Keep it brief (3-4 sentences)."""
                    }],
                    max_tokens=300
                )

                return response["message"]["content"]

            except Exception as e:
                logger.error(f"Failed to generate meeting brief: {e}")
                return f"Meeting: {meeting.title} at {meeting.start_time}"


_calendar_service: Optional[CalendarService] = None


def get_calendar_service() -> CalendarService:
    """Get calendar service instance"""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = CalendarService()
    return _calendar_service
