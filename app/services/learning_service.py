"""
Learning System Service
Teach JARVIS facts and build knowledge graph about user
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import UserKnowledge

logger = logging.getLogger(__name__)


class LearningService:
    """Service for managing user knowledge and learning"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def teach(
        self,
        category: str,
        key: str,
        value: str,
        source: str = "user",
        confidence: float = 1.0,
        context: Optional[str] = None,
        related_ids: Optional[List[int]] = None,
    ) -> UserKnowledge:
        """Teach JARVIS a new fact"""
        # Check if knowledge already exists
        existing = await self.get_knowledge(category, key)

        if existing:
            # Update existing knowledge
            existing.value = value
            existing.confidence = confidence
            if context:
                existing.context = context
            if related_ids:
                existing.related_knowledge = json.dumps(related_ids)
            existing.updated_at = datetime.now(timezone.utc)
            existing.verified = source == "user"  # User-provided is auto-verified

            await self.db.commit()
            await self.db.refresh(existing)
            logger.info(f"Updated knowledge: {category}/{key}")
            return existing
        else:
            # Create new knowledge
            knowledge = UserKnowledge(
                category=category,
                key=key,
                value=value,
                source=source,
                confidence=confidence,
                context=context,
                related_knowledge=json.dumps(related_ids or []),
                verified=source == "user",
            )
            self.db.add(knowledge)
            await self.db.commit()
            await self.db.refresh(knowledge)
            logger.info(f"Learned new knowledge: {category}/{key} = {value}")
            return knowledge

    async def get_knowledge(
        self, category: str, key: str
    ) -> Optional[UserKnowledge]:
        """Get specific knowledge by category and key"""
        result = await self.db.execute(
            select(UserKnowledge).where(
                UserKnowledge.category == category, UserKnowledge.key == key
            )
        )
        knowledge = result.scalar_one_or_none()

        if knowledge:
            # Update access stats
            knowledge.access_count += 1
            knowledge.last_accessed = datetime.now(timezone.utc)
            await self.db.commit()

        return knowledge

    async def get_by_id(self, knowledge_id: int) -> Optional[UserKnowledge]:
        """Get knowledge by ID"""
        result = await self.db.execute(
            select(UserKnowledge).where(UserKnowledge.id == knowledge_id)
        )
        return result.scalar_one_or_none()

    async def get_all_knowledge(
        self, category: Optional[str] = None
    ) -> List[UserKnowledge]:
        """Get all knowledge, optionally filtered by category"""
        query = select(UserKnowledge).order_by(UserKnowledge.category, UserKnowledge.key)

        if category:
            query = query.where(UserKnowledge.category == category)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_knowledge(self, query: str) -> List[UserKnowledge]:
        """Search knowledge by key, value, or context"""
        result = await self.db.execute(
            select(UserKnowledge).where(
                or_(
                    UserKnowledge.key.ilike(f"%{query}%"),
                    UserKnowledge.value.ilike(f"%{query}%"),
                    UserKnowledge.context.ilike(f"%{query}%"),
                )
            )
        )
        return list(result.scalars().all())

    async def delete_knowledge(self, knowledge_id: int) -> bool:
        """Delete knowledge (forget something)"""
        knowledge = await self.get_by_id(knowledge_id)
        if not knowledge:
            return False

        await self.db.delete(knowledge)
        await self.db.commit()
        logger.info(f"Forgot knowledge: {knowledge.category}/{knowledge.key}")
        return True

    async def query(self, question: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Query the knowledge base with natural language
        Uses AI to understand the question and retrieve relevant knowledge
        """
        try:
            from app.llm_claude import get_claude_llm

            # First, try to extract category/key from question
            extracted = await self._extract_knowledge_reference(question)

            relevant_knowledge = []

            if extracted:
                # Direct lookup
                knowledge = await self.get_knowledge(
                    extracted["category"], extracted["key"]
                )
                if knowledge:
                    relevant_knowledge.append(knowledge)

            # Also do text search
            search_results = await self.search_knowledge(question)
            relevant_knowledge.extend(search_results)

            # Remove duplicates
            seen_ids = set()
            unique_knowledge = []
            for k in relevant_knowledge:
                if k.id not in seen_ids:
                    seen_ids.add(k.id)
                    unique_knowledge.append(k)

            if not unique_knowledge:
                return {
                    "answer": "I don't have that information in my knowledge base yet.",
                    "confidence": 0.0,
                    "sources": [],
                }

            # Build knowledge context for AI
            knowledge_context = "\n".join(
                [
                    f"- {k.category}/{k.key}: {k.value} (confidence: {k.confidence})"
                    for k in unique_knowledge
                ]
            )

            # Use AI to answer the question
            claude = get_claude_llm()
            prompt = f"""Answer this question using only the knowledge provided below:

Question: {question}

Knowledge:
{knowledge_context}

Provide a natural, conversational answer. If the knowledge doesn't fully answer the question, say so."""

            response = await claude.chat(
                messages=[{"role": "user", "content": prompt}], max_tokens=300
            )

            return {
                "answer": response["message"]["content"],
                "confidence": max(k.confidence for k in unique_knowledge),
                "sources": [
                    {
                        "id": k.id,
                        "category": k.category,
                        "key": k.key,
                        "value": k.value,
                    }
                    for k in unique_knowledge
                ],
            }

        except Exception as e:
            logger.error(f"Failed to query knowledge: {e}")
            return {
                "answer": "Sorry, I encountered an error querying my knowledge base.",
                "error": str(e),
                "confidence": 0.0,
                "sources": [],
            }

    async def _extract_knowledge_reference(
        self, question: str
    ) -> Optional[Dict[str, str]]:
        """
        Try to extract direct knowledge reference from question
        e.g., "What is my favorite coffee?" -> {category: "preference", key: "favorite_coffee"}
        """
        # Simple pattern matching (can be enhanced with AI)
        question_lower = question.lower()

        # Preference patterns
        if "favorite" in question_lower or "prefer" in question_lower:
            category = "preference"
            # Extract what they're asking about
            for item in [
                "coffee",
                "food",
                "color",
                "music",
                "movie",
                "book",
                "restaurant",
            ]:
                if item in question_lower:
                    return {"category": category, "key": f"favorite_{item}"}

        # Fact patterns
        if any(word in question_lower for word in ["who is", "what is", "where is"]):
            category = "fact"
            # Try to extract key from question
            # This is basic - can be improved

        return None

    async def extract_knowledge_from_conversation(
        self, conversation: str
    ) -> List[Dict[str, Any]]:
        """
        Extract knowledge from natural conversation
        Used by JARVIS to learn from user interactions
        """
        try:
            from app.llm_claude import get_claude_llm

            claude = get_claude_llm()

            prompt = f"""Extract user facts and preferences from this conversation:

Conversation:
{conversation}

Extract any facts about the user, their preferences, relationships, skills, or important information.

Respond with JSON array:
[
  {{
    "category": "preference" | "fact" | "skill" | "relationship",
    "key": "descriptive_key",
    "value": "the actual information",
    "confidence": 0.0-1.0,
    "context": "additional context if needed"
  }}
]

Only extract clear, specific information. If nothing to extract, return empty array."""

            response = await claude.chat(
                messages=[{"role": "user", "content": prompt}], max_tokens=500
            )

            content = response["message"]["content"]

            # Extract JSON array
            import re

            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                extractions = json.loads(json_match.group())

                # Store extracted knowledge
                stored = []
                for item in extractions:
                    knowledge = await self.teach(
                        category=item["category"],
                        key=item["key"],
                        value=item["value"],
                        source="learned",
                        confidence=item.get("confidence", 0.7),
                        context=item.get("context"),
                    )
                    stored.append(
                        {
                            "id": knowledge.id,
                            "category": knowledge.category,
                            "key": knowledge.key,
                            "value": knowledge.value,
                        }
                    )

                return stored

            return []

        except Exception as e:
            logger.error(f"Failed to extract knowledge from conversation: {e}")
            return []

    async def get_knowledge_graph(self, knowledge_id: int) -> Dict[str, Any]:
        """Get knowledge with its related knowledge (graph view)"""
        knowledge = await self.get_by_id(knowledge_id)
        if not knowledge:
            return {"error": "Knowledge not found"}

        related_ids = json.loads(knowledge.related_knowledge)
        related = []

        for rel_id in related_ids:
            rel_knowledge = await self.get_by_id(rel_id)
            if rel_knowledge:
                related.append(
                    {
                        "id": rel_knowledge.id,
                        "category": rel_knowledge.category,
                        "key": rel_knowledge.key,
                        "value": rel_knowledge.value,
                    }
                )

        return {
            "id": knowledge.id,
            "category": knowledge.category,
            "key": knowledge.key,
            "value": knowledge.value,
            "confidence": knowledge.confidence,
            "context": knowledge.context,
            "related": related,
            "access_count": knowledge.access_count,
            "verified": knowledge.verified,
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics"""
        all_knowledge = await self.get_all_knowledge()

        stats = {
            "total_items": len(all_knowledge),
            "by_category": {},
            "by_source": {},
            "verified_count": 0,
            "average_confidence": 0.0,
            "most_accessed": [],
        }

        if not all_knowledge:
            return stats

        total_confidence = 0.0

        for k in all_knowledge:
            # Count by category
            stats["by_category"][k.category] = (
                stats["by_category"].get(k.category, 0) + 1
            )

            # Count by source
            stats["by_source"][k.source] = stats["by_source"].get(k.source, 0) + 1

            # Count verified
            if k.verified:
                stats["verified_count"] += 1

            # Sum confidence
            total_confidence += k.confidence

        stats["average_confidence"] = round(
            total_confidence / len(all_knowledge), 2
        )

        # Get most accessed
        sorted_by_access = sorted(
            all_knowledge, key=lambda k: k.access_count, reverse=True
        )
        stats["most_accessed"] = [
            {
                "id": k.id,
                "category": k.category,
                "key": k.key,
                "value": k.value,
                "access_count": k.access_count,
            }
            for k in sorted_by_access[:10]
        ]

        return stats
