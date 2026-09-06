"""
Email Integration Service - Gmail API integration
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from email.mime.text import MIMEText

from sqlalchemy import select

from app.db import async_session, Email

logger = logging.getLogger(__name__)


class EmailService:
    """
    Gmail API integration for email management

    Setup:
    1. Enable Gmail API in Google Cloud Console
    2. Download credentials.json
    3. Set GOOGLE_CREDENTIALS_PATH in .env
    """

    def __init__(self):
        self.credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        self.gmail_service = None

    async def initialize(self):
        """Initialize Gmail API connection"""
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            import pickle

            SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
                      'https://www.googleapis.com/auth/gmail.send']

            creds = None
            token_path = 'token.pickle'

            if os.path.exists(token_path):
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not self.credentials_path:
                        logger.warning("Gmail credentials not configured")
                        return False

                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)

            self.gmail_service = build('gmail', 'v1', credentials=creds)
            logger.info("✅ Gmail API initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Gmail API: {e}")
            return False

    async def fetch_recent_emails(self, max_results: int = 20) -> list[dict]:
        """Fetch recent emails from Gmail"""
        if not self.gmail_service:
            await self.initialize()

        if not self.gmail_service:
            return []

        try:
            results = self.gmail_service.users().messages().list(
                userId='me',
                maxResults=max_results,
                labelIds=['INBOX']
            ).execute()

            messages = results.get('messages', [])
            emails = []

            for msg in messages:
                email_data = await self._get_email_details(msg['id'])
                if email_data:
                    # Store in database
                    await self._store_email(email_data)
                    emails.append(email_data)

            return emails

        except Exception as e:
            logger.error(f"Failed to fetch emails: {e}")
            return []

    async def _get_email_details(self, message_id: str) -> Optional[dict]:
        """Get detailed email information"""
        try:
            message = self.gmail_service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date_str = next((h['value'] for h in headers if h['name'] == 'Date'), None)

            # Get email body
            body = self._get_email_body(message['payload'])

            return {
                'email_id': message_id,
                'sender': sender,
                'subject': subject,
                'body': body[:5000],  # Limit body size
                'is_read': 'UNREAD' not in message.get('labelIds', []),
                'received_at': self._parse_email_date(date_str)
            }

        except Exception as e:
            logger.error(f"Failed to get email details: {e}")
            return None

    def _get_email_body(self, payload: dict) -> str:
        """Extract email body from payload"""
        if 'body' in payload and 'data' in payload['body']:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')

        return ""

    def _parse_email_date(self, date_str: Optional[str]) -> datetime:
        """Parse email date"""
        if not date_str:
            return datetime.now(timezone.utc)

        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            return datetime.now(timezone.utc)

    async def _store_email(self, email_data: dict) -> int:
        """Store email in database"""
        async with async_session() as session:
            # Check if already exists
            result = await session.execute(
                select(Email).where(Email.email_id == email_data['email_id'])
            )
            existing = result.scalar_one_or_none()

            if existing:
                return existing.id

            email = Email(
                email_id=email_data['email_id'],
                sender=email_data['sender'],
                recipient='me',
                subject=email_data['subject'],
                body=email_data['body'],
                is_read=email_data['is_read'],
                is_urgent=self._is_urgent(email_data),
                category=self._categorize_email(email_data),
                received_at=email_data['received_at']
            )

            session.add(email)
            await session.commit()
            await session.refresh(email)

            return email.id

    def _is_urgent(self, email_data: dict) -> bool:
        """Detect if email is urgent"""
        urgent_keywords = ['urgent', 'asap', 'important', 'critical', 'emergency']
        subject_lower = email_data['subject'].lower()
        return any(keyword in subject_lower for keyword in urgent_keywords)

    def _categorize_email(self, email_data: dict) -> str:
        """Auto-categorize email"""
        subject = email_data['subject'].lower()
        body = email_data['body'].lower()

        if any(word in subject or word in body for word in ['meeting', 'calendar', 'invite']):
            return 'meeting'
        elif any(word in subject or word in body for word in ['invoice', 'payment', 'bill']):
            return 'financial'
        elif any(word in subject or word in body for word in ['alert', 'warning', 'error']):
            return 'alert'
        else:
            return 'general'

    async def get_urgent_emails(self) -> list[dict]:
        """Get urgent emails from database"""
        async with async_session() as session:
            result = await session.execute(
                select(Email).where(
                    Email.is_urgent == True,
                    Email.is_read == False
                ).order_by(Email.received_at.desc())
            )
            emails = result.scalars().all()

            return [
                {
                    'id': e.id,
                    'sender': e.sender,
                    'subject': e.subject,
                    'received_at': e.received_at.isoformat(),
                    'category': e.category
                }
                for e in emails
            ]

    async def summarize_email(self, email_id: int) -> str:
        """Summarize email using Claude"""
        async with async_session() as session:
            result = await session.execute(
                select(Email).where(Email.id == email_id)
            )
            email = result.scalar_one_or_none()

            if not email:
                return "Email not found"

            # Use Claude to summarize
            from app.llm_claude import get_claude_llm

            claude = get_claude_llm()

            try:
                response = await claude.chat(
                    messages=[{
                        "role": "user",
                        "content": f"""Summarize this email in 2-3 sentences:

From: {email.sender}
Subject: {email.subject}

{email.body[:1000]}

Provide a concise summary focusing on action items and key information."""
                    }],
                    max_tokens=200
                )

                return response["message"]["content"]

            except Exception as e:
                logger.error(f"Failed to summarize email: {e}")
                return f"Subject: {email.subject}\nFrom: {email.sender}"


_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get email service instance"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
