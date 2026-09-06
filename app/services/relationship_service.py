"""
Relationship Intelligence Service
Track contacts and interactions to maintain relationships
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Contact, ContactInteraction

logger = logging.getLogger(__name__)


class RelationshipService:
    """Service for managing contacts and relationship intelligence"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_contact(
        self,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        relationship: Optional[str] = None,
        notes: Optional[str] = None,
        important_dates: Optional[List[Dict]] = None,
    ) -> Contact:
        """Create a new contact"""
        contact = Contact(
            name=name,
            email=email,
            phone=phone,
            relationship=relationship,
            notes=notes,
            important_dates=json.dumps(important_dates or []),
            relationship_strength=5.0,  # Start at neutral
        )
        self.db.add(contact)
        await self.db.commit()
        await self.db.refresh(contact)
        logger.info(f"Created contact: {name}")
        return contact

    async def get_all_contacts(
        self, relationship_type: Optional[str] = None
    ) -> List[Contact]:
        """Get all contacts, optionally filtered by relationship type"""
        query = select(Contact).order_by(Contact.relationship_strength.desc())

        if relationship_type:
            query = query.where(Contact.relationship == relationship_type)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_contact(self, contact_id: int) -> Optional[Contact]:
        """Get a specific contact"""
        result = await self.db.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        return result.scalar_one_or_none()

    async def update_contact(
        self,
        contact_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        relationship: Optional[str] = None,
        notes: Optional[str] = None,
        important_dates: Optional[List[Dict]] = None,
    ) -> Optional[Contact]:
        """Update contact information"""
        contact = await self.get_contact(contact_id)
        if not contact:
            return None

        if name is not None:
            contact.name = name
        if email is not None:
            contact.email = email
        if phone is not None:
            contact.phone = phone
        if relationship is not None:
            contact.relationship = relationship
        if notes is not None:
            contact.notes = notes
        if important_dates is not None:
            contact.important_dates = json.dumps(important_dates)

        contact.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact

    async def delete_contact(self, contact_id: int) -> bool:
        """Delete a contact"""
        contact = await self.get_contact(contact_id)
        if not contact:
            return False

        await self.db.delete(contact)
        await self.db.commit()
        logger.info(f"Deleted contact: {contact.name}")
        return True

    async def record_interaction(
        self,
        contact_id: int,
        interaction_type: str,
        summary: Optional[str] = None,
        topics: Optional[List[str]] = None,
        sentiment: Optional[str] = None,
        interaction_date: Optional[datetime] = None,
    ) -> Optional[ContactInteraction]:
        """Record an interaction with a contact"""
        contact = await self.get_contact(contact_id)
        if not contact:
            logger.warning(f"Contact {contact_id} not found")
            return None

        if interaction_date is None:
            interaction_date = datetime.now(timezone.utc)

        interaction = ContactInteraction(
            contact_id=contact_id,
            interaction_type=interaction_type,
            summary=summary,
            topics=json.dumps(topics or []),
            sentiment=sentiment,
            interaction_date=interaction_date,
        )
        self.db.add(interaction)

        # Update contact's last contact date
        contact.last_contact_date = interaction_date
        contact.updated_at = datetime.now(timezone.utc)

        # Update conversation topics
        existing_topics = json.loads(contact.conversation_topics)
        if topics:
            # Add new topics, keep last 10
            existing_topics.extend(topics)
            contact.conversation_topics = json.dumps(existing_topics[-10:])

        # Adjust relationship strength based on interaction
        await self._adjust_relationship_strength(contact, interaction_type, sentiment)

        await self.db.commit()
        await self.db.refresh(interaction)
        logger.info(f"Recorded {interaction_type} with {contact.name}")
        return interaction

    async def _adjust_relationship_strength(
        self, contact: Contact, interaction_type: str, sentiment: Optional[str]
    ):
        """Adjust relationship strength based on interaction"""
        # Positive interactions increase strength
        strength_change = 0.0

        if sentiment == "positive":
            strength_change = 0.2
        elif sentiment == "negative":
            strength_change = -0.3
        else:
            strength_change = 0.1  # Neutral interactions still maintain relationship

        # Different interaction types have different impacts
        type_multipliers = {
            "call": 1.5,
            "meeting": 1.5,
            "message": 1.0,
            "email": 0.8,
        }
        multiplier = type_multipliers.get(interaction_type, 1.0)

        contact.relationship_strength = max(
            0.0,
            min(10.0, contact.relationship_strength + (strength_change * multiplier)),
        )

    async def get_interaction_history(
        self, contact_id: int, limit: int = 20
    ) -> List[ContactInteraction]:
        """Get recent interactions with a contact"""
        result = await self.db.execute(
            select(ContactInteraction)
            .where(ContactInteraction.contact_id == contact_id)
            .order_by(desc(ContactInteraction.interaction_date))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_contacts_needing_followup(
        self, days_threshold: int = 30
    ) -> List[Dict]:
        """Get contacts that haven't been contacted recently"""
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        result = await self.db.execute(
            select(Contact)
            .where(Contact.last_contact_date < threshold_date)
            .order_by(Contact.relationship_strength.desc())
        )
        contacts = list(result.scalars().all())

        # Generate suggestions for each
        suggestions = []
        for contact in contacts:
            days_since = (
                datetime.now(timezone.utc) - contact.last_contact_date
            ).days if contact.last_contact_date else 999

            # Get recent topics for context
            topics = json.loads(contact.conversation_topics)
            recent_topics = topics[-3:] if topics else []

            suggestion = await self._generate_followup_suggestion(
                contact, days_since, recent_topics
            )

            suggestions.append(
                {
                    "contact_id": contact.id,
                    "name": contact.name,
                    "days_since_contact": days_since,
                    "relationship": contact.relationship,
                    "relationship_strength": contact.relationship_strength,
                    "suggestion": suggestion,
                    "recent_topics": recent_topics,
                }
            )

        return suggestions

    async def _generate_followup_suggestion(
        self, contact: Contact, days_since: int, recent_topics: List[str]
    ) -> str:
        """Generate AI-powered followup suggestion"""
        try:
            from app.llm_claude import get_claude_llm

            claude = get_claude_llm()

            topics_str = ", ".join(recent_topics) if recent_topics else "no recent topics"

            prompt = f"""Generate a brief, natural followup suggestion for reconnecting with this person:

Name: {contact.name}
Relationship: {contact.relationship or 'contact'}
Days since last contact: {days_since}
Recent topics discussed: {topics_str}
Notes: {contact.notes or 'none'}

Provide a 1-2 sentence suggestion for what to say or ask about. Be warm and natural."""

            response = await claude.chat(
                messages=[{"role": "user", "content": prompt}], max_tokens=100
            )

            return response["message"]["content"].strip()

        except Exception as e:
            logger.error(f"Failed to generate followup suggestion: {e}")
            default_msg = "how they're doing"
            topic = recent_topics[0] if recent_topics else default_msg
            return f"Check in about {topic}"

    async def get_upcoming_important_dates(
        self, days_ahead: int = 30
    ) -> List[Dict]:
        """Get upcoming birthdays, anniversaries, etc."""
        contacts = await self.get_all_contacts()
        upcoming = []

        now = datetime.now(timezone.utc)
        future_date = now + timedelta(days=days_ahead)

        for contact in contacts:
            important_dates = json.loads(contact.important_dates)

            for date_info in important_dates:
                date_str = date_info.get("date")
                date_type = date_info.get("type", "important date")

                if date_str:
                    # Parse date (assuming format: MM-DD or YYYY-MM-DD)
                    try:
                        if len(date_str) == 5:  # MM-DD
                            # Add current year
                            date_obj = datetime.strptime(
                                f"{now.year}-{date_str}", "%Y-%m-%d"
                            ).replace(tzinfo=timezone.utc)
                        else:
                            date_obj = datetime.fromisoformat(date_str).replace(
                                tzinfo=timezone.utc
                            )

                        # Check if it's coming up
                        if now <= date_obj <= future_date:
                            days_until = (date_obj - now).days
                            upcoming.append(
                                {
                                    "contact_id": contact.id,
                                    "contact_name": contact.name,
                                    "date": date_str,
                                    "date_type": date_type,
                                    "days_until": days_until,
                                    "relationship": contact.relationship,
                                }
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to parse date {date_str} for {contact.name}: {e}"
                        )

        # Sort by days_until
        upcoming.sort(key=lambda x: x["days_until"])
        return upcoming

    async def search_contacts(self, query: str) -> List[Contact]:
        """Search contacts by name, email, or notes"""
        # Simple case-insensitive search
        result = await self.db.execute(
            select(Contact).where(
                (Contact.name.ilike(f"%{query}%"))
                | (Contact.email.ilike(f"%{query}%"))
                | (Contact.notes.ilike(f"%{query}%"))
            )
        )
        return list(result.scalars().all())

    async def get_relationship_stats(self) -> Dict:
        """Get overall relationship statistics"""
        contacts = await self.get_all_contacts()

        stats = {
            "total_contacts": len(contacts),
            "by_relationship": {},
            "average_strength": 0.0,
            "strong_relationships": 0,
            "weak_relationships": 0,
            "contacts_by_strength": {
                "strong": [],
                "medium": [],
                "weak": [],
            },
        }

        if not contacts:
            return stats

        # Calculate stats
        total_strength = 0.0
        for contact in contacts:
            # Count by relationship type
            rel_type = contact.relationship or "unknown"
            stats["by_relationship"][rel_type] = (
                stats["by_relationship"].get(rel_type, 0) + 1
            )

            # Strength stats
            strength = contact.relationship_strength
            total_strength += strength

            if strength >= 7.0:
                stats["strong_relationships"] += 1
                stats["contacts_by_strength"]["strong"].append(
                    {"id": contact.id, "name": contact.name, "strength": strength}
                )
            elif strength <= 3.0:
                stats["weak_relationships"] += 1
                stats["contacts_by_strength"]["weak"].append(
                    {"id": contact.id, "name": contact.name, "strength": strength}
                )
            else:
                stats["contacts_by_strength"]["medium"].append(
                    {"id": contact.id, "name": contact.name, "strength": strength}
                )

        stats["average_strength"] = round(total_strength / len(contacts), 2)

        return stats
