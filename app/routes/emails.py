"""
Email Integration Endpoints - Gmail API integration
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Path

from app.services.email_service import get_email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/emails", tags=["emails"])


@router.post("/sync", summary="Sync emails from Gmail", description="""
Fetch recent emails from Gmail and store them in the database.

**What it does:**
- Connects to Gmail API
- Fetches latest emails (default: 20)
- Auto-categorizes emails (meeting, financial, alert, general)
- Detects urgent emails
- Stores in database for offline access

**Use case:** Call this periodically or when user asks "check my emails"
""")
async def sync_emails(max_results: int = Query(20, description="Number of emails to fetch", ge=1, le=100)):
    """Sync recent emails from Gmail"""
    email_service = get_email_service()
    emails = await email_service.fetch_recent_emails(max_results)
    return {
        "status": "ok",
        "synced": len(emails),
        "emails": emails[:5]  # Return first 5 for preview
    }


@router.get("/urgent", summary="Get urgent emails only", description="""
Retrieve unread emails marked as urgent.

**Urgent criteria:**
- Subject contains: urgent, asap, important, critical, emergency
- Unread status
- Sorted by most recent first

**JARVIS use:** "Sir, you have 3 urgent emails requiring attention"
""")
async def get_urgent_emails():
    """Get all urgent unread emails"""
    email_service = get_email_service()
    emails = await email_service.get_urgent_emails()
    return {
        "urgent_count": len(emails),
        "emails": emails
    }


@router.get("/{email_id}/summarize", summary="Summarize an email", description="""
Generate AI summary of an email using Claude.

**What it returns:**
- 2-3 sentence summary
- Key action items
- Main points

**Example output:**
"Client wants to reschedule Thursday meeting to Friday 2 PM.
They need updated proposal by Wednesday. No other changes to project scope."
""")
async def summarize_email(
    email_id: int = Path(..., description="Email ID from database")
):
    """Get AI-powered summary of email"""
    email_service = get_email_service()
    summary = await email_service.summarize_email(email_id)
    return {
        "email_id": email_id,
        "summary": summary
    }


@router.post("/initialize", summary="Initialize Gmail connection", description="""
Set up Gmail API connection (one-time setup).

**Setup steps:**
1. Enable Gmail API in Google Cloud Console
2. Download credentials.json
3. Set GOOGLE_CREDENTIALS_PATH in .env
4. Call this endpoint
5. Follow OAuth flow in browser

**Required once per deployment**
""")
async def initialize_gmail():
    """Initialize Gmail API connection"""
    email_service = get_email_service()
    success = await email_service.initialize()
    return {
        "status": "ok" if success else "error",
        "message": "Gmail API initialized" if success else "Failed to initialize. Check credentials."
    }
