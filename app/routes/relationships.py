"""
Relationship Intelligence Routes
Track contacts and maintain relationships
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.relationship_service import RelationshipService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/relationships", tags=["relationships"])


class ContactCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    relationship: Optional[str] = None  # family, friend, colleague, etc.
    notes: Optional[str] = None
    important_dates: Optional[List[Dict]] = None  # [{"type": "birthday", "date": "MM-DD"}]


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    relationship: Optional[str] = None
    notes: Optional[str] = None
    important_dates: Optional[List[Dict]] = None


class InteractionCreate(BaseModel):
    interaction_type: str  # call, email, meeting, message
    summary: Optional[str] = None
    topics: Optional[List[str]] = None
    sentiment: Optional[str] = None  # positive, neutral, negative
    interaction_date: Optional[datetime] = None


@router.post("/contacts", summary="Add contact", description="""
Add a new contact to relationship intelligence.

**Example:**
```json
{
  "name": "John Smith",
  "email": "john@example.com",
  "phone": "+1234567890",
  "relationship": "friend",
  "notes": "Met at tech conference 2023",
  "important_dates": [
    {"type": "birthday", "date": "03-15"},
    {"type": "anniversary", "date": "2020-06-20"}
  ]
}
```

**Relationship types:** family, friend, colleague, client, mentor, acquaintance

**JARVIS use:**
Tracks everyone important to you, remembers details about them, and suggests follow-ups.

"Sir, you haven't contacted John in 45 days. Last discussed: His new startup idea."
""")
async def create_contact(
    contact: ContactCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new contact"""
    service = RelationshipService(db)

    created = await service.create_contact(
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        relationship=contact.relationship,
        notes=contact.notes,
        important_dates=contact.important_dates,
    )

    return {
        "id": created.id,
        "name": created.name,
        "email": created.email,
        "relationship": created.relationship,
        "relationship_strength": created.relationship_strength,
        "created_at": created.created_at.isoformat(),
    }


@router.get("/contacts", summary="List contacts", description="""
Get all contacts, optionally filtered by relationship type.

**Query parameters:**
- `relationship` - Filter by type (family, friend, colleague, etc.)

**Returns:** All contacts with relationship strength scores

**Relationship strength (0-10):**
- 0-3: Weak relationship (needs attention)
- 4-6: Medium relationship
- 7-10: Strong relationship

**JARVIS use:** Displays relationship overview
""")
async def list_contacts(
    relationship: Optional[str] = None, db: AsyncSession = Depends(get_db)
):
    """List all contacts"""
    service = RelationshipService(db)
    contacts = await service.get_all_contacts(relationship_type=relationship)

    import json

    return [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "relationship": c.relationship,
            "relationship_strength": c.relationship_strength,
            "last_contact_date": c.last_contact_date.isoformat()
            if c.last_contact_date
            else None,
            "important_dates": json.loads(c.important_dates),
            "recent_topics": json.loads(c.conversation_topics),
        }
        for c in contacts
    ]


@router.get("/contacts/{contact_id}", summary="Get contact details", description="""
Get detailed information about a specific contact.

**Returns:**
- Full contact information
- Relationship strength
- Recent interaction history
- Conversation topics
- Important dates

**JARVIS use:** Provides context before reaching out
""")
async def get_contact(contact_id: int, db: AsyncSession = Depends(get_db)):
    """Get contact details"""
    service = RelationshipService(db)
    contact = await service.get_contact(contact_id)

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Get interaction history
    interactions = await service.get_interaction_history(contact_id, limit=10)

    import json

    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "phone": contact.phone,
        "relationship": contact.relationship,
        "relationship_strength": contact.relationship_strength,
        "last_contact_date": contact.last_contact_date.isoformat()
        if contact.last_contact_date
        else None,
        "important_dates": json.loads(contact.important_dates),
        "conversation_topics": json.loads(contact.conversation_topics),
        "notes": contact.notes,
        "recent_interactions": [
            {
                "type": i.interaction_type,
                "date": i.interaction_date.isoformat(),
                "summary": i.summary,
                "sentiment": i.sentiment,
            }
            for i in interactions
        ],
    }


@router.patch("/contacts/{contact_id}", summary="Update contact", description="""
Update contact information.

**JARVIS use:** Keep contact information current
""")
async def update_contact(
    contact_id: int, update: ContactUpdate, db: AsyncSession = Depends(get_db)
):
    """Update contact"""
    service = RelationshipService(db)

    updated = await service.update_contact(
        contact_id=contact_id,
        name=update.name,
        email=update.email,
        phone=update.phone,
        relationship=update.relationship,
        notes=update.notes,
        important_dates=update.important_dates,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Contact not found")

    return {
        "id": updated.id,
        "name": updated.name,
        "email": updated.email,
        "relationship": updated.relationship,
        "updated_at": updated.updated_at.isoformat(),
    }


@router.delete("/contacts/{contact_id}", summary="Delete contact", description="""
Delete a contact permanently.
""")
async def delete_contact(contact_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a contact"""
    service = RelationshipService(db)
    success = await service.delete_contact(contact_id)

    if not success:
        raise HTTPException(status_code=404, detail="Contact not found")

    return {"status": "deleted", "contact_id": contact_id}


@router.post("/contacts/{contact_id}/interactions", summary="Record interaction", description="""
Record an interaction with a contact.

**Example:**
```json
{
  "interaction_type": "call",
  "summary": "Discussed his new job at TechCorp",
  "topics": ["career", "tech industry", "relocating"],
  "sentiment": "positive",
  "interaction_date": "2026-09-06T15:30:00Z"
}
```

**Interaction types:** call, email, meeting, message

**Sentiment:** positive, neutral, negative

**JARVIS use:**
- Automatically tracks interactions from email, calendar, messages
- Updates relationship strength
- Learns conversation topics
- Suggests follow-ups

**Effect on relationship:**
- Positive interactions increase strength (+0.2-0.3)
- Negative interactions decrease strength (-0.3)
- Regular contact maintains relationship
""")
async def record_interaction(
    contact_id: int, interaction: InteractionCreate, db: AsyncSession = Depends(get_db)
):
    """Record an interaction with contact"""
    service = RelationshipService(db)

    recorded = await service.record_interaction(
        contact_id=contact_id,
        interaction_type=interaction.interaction_type,
        summary=interaction.summary,
        topics=interaction.topics,
        sentiment=interaction.sentiment,
        interaction_date=interaction.interaction_date,
    )

    if not recorded:
        raise HTTPException(status_code=404, detail="Contact not found")

    return {
        "id": recorded.id,
        "contact_id": recorded.contact_id,
        "type": recorded.interaction_type,
        "date": recorded.interaction_date.isoformat(),
        "sentiment": recorded.sentiment,
    }


@router.get("/followups", summary="Get followup suggestions", description="""
Get contacts that need follow-up.

**Query parameters:**
- `days` - Threshold for "needs follow-up" (default: 30)

**Returns:** List of contacts you haven't contacted recently with AI-generated suggestions

**JARVIS proactive alert:**
"Sir, you haven't contacted these 3 people in over a month:
 - Sarah: Last discussed her project launch
 - Mike: Check in about his interview results
 - Alex: Follow up on dinner plans"

**Use case:** Maintain relationships automatically
""")
async def get_followups(
    days: int = Query(30, description="Days since last contact"),
    db: AsyncSession = Depends(get_db),
):
    """Get contacts needing follow-up"""
    service = RelationshipService(db)
    suggestions = await service.get_contacts_needing_followup(days_threshold=days)

    return {
        "threshold_days": days,
        "contacts_needing_followup": len(suggestions),
        "suggestions": suggestions,
    }


@router.get("/important-dates", summary="Get upcoming important dates", description="""
Get upcoming birthdays, anniversaries, and other important dates.

**Query parameters:**
- `days_ahead` - How many days to look ahead (default: 30)

**Returns:** Upcoming important dates sorted by proximity

**JARVIS proactive alert:**
"Sir, 3 important dates coming up:
 - Sarah's birthday in 5 days (Sept 11)
 - Your anniversary in 12 days (Sept 18)
 - Mike's wedding anniversary in 20 days (Sept 26)"

**Use case:** Never forget important dates
""")
async def get_important_dates(
    days_ahead: int = Query(30, description="Days to look ahead"),
    db: AsyncSession = Depends(get_db),
):
    """Get upcoming important dates"""
    service = RelationshipService(db)
    upcoming = await service.get_upcoming_important_dates(days_ahead=days_ahead)

    return {"days_ahead": days_ahead, "upcoming_dates": upcoming}


@router.get("/search", summary="Search contacts", description="""
Search contacts by name, email, or notes.

**JARVIS use:** "Find contact named John" or "Who works at TechCorp?"
""")
async def search_contacts(
    q: str = Query(..., description="Search query"), db: AsyncSession = Depends(get_db)
):
    """Search contacts"""
    service = RelationshipService(db)
    results = await service.search_contacts(q)

    return {
        "query": q,
        "results": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "relationship": c.relationship,
                "relationship_strength": c.relationship_strength,
            }
            for c in results
        ],
    }


@router.get("/stats", summary="Get relationship statistics", description="""
Get overall relationship intelligence statistics.

**Returns:**
- Total contacts
- By relationship type
- Average relationship strength
- Strong vs weak relationships
- Top contacts by strength

**JARVIS insight:**
"Sir, your relationship overview:
 - 45 total contacts
 - 12 strong relationships
 - 8 contacts need attention (haven't contacted in 60+ days)
 - Average relationship strength: 6.5/10"
""")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get relationship statistics"""
    service = RelationshipService(db)
    stats = await service.get_relationship_stats()

    return stats
