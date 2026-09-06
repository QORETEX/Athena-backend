"""
Learning System Routes
Teach JARVIS facts and build knowledge graph
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.learning_service import LearningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["learning"])


class KnowledgeCreate(BaseModel):
    category: str  # preference, fact, skill, relationship
    key: str
    value: str
    source: str = "user"
    confidence: float = 1.0
    context: Optional[str] = None


class KnowledgeQuery(BaseModel):
    question: str
    context: Optional[Dict[str, Any]] = None


@router.post("/teach", summary="Teach JARVIS something", description="""
Teach JARVIS a new fact about you.

**Categories:**
- `preference` - Your likes, dislikes, favorites
- `fact` - Personal facts, biographical info
- `skill` - Your abilities, expertise
- `relationship` - Information about people you know

**Example:**
```json
{
  "category": "preference",
  "key": "favorite_coffee",
  "value": "double espresso with oat milk",
  "source": "user",
  "confidence": 1.0,
  "context": "Always orders this at cafes"
}
```

**JARVIS learns:**
User: "Athena, remember: My favorite coffee is double espresso"
JARVIS: "Understood. I'll remember you prefer double espresso."

Later:
User: "Athena, I need coffee"
JARVIS: "Your usual: double espresso with oat milk? The nearest cafe is Starbucks, 5 minutes away."

**Use case:**
- Personal preferences
- Important facts
- Relationships
- Skills and expertise
- Habits and routines

**Effect:** JARVIS becomes more personalized over time
""")
async def teach_knowledge(
    knowledge: KnowledgeCreate, db: AsyncSession = Depends(get_db)
):
    """Teach JARVIS new knowledge"""
    service = LearningService(db)

    learned = await service.teach(
        category=knowledge.category,
        key=knowledge.key,
        value=knowledge.value,
        source=knowledge.source,
        confidence=knowledge.confidence,
        context=knowledge.context,
    )

    return {
        "id": learned.id,
        "category": learned.category,
        "key": learned.key,
        "value": learned.value,
        "confidence": learned.confidence,
        "verified": learned.verified,
        "message": f"Learned: {knowledge.key} = {knowledge.value}",
    }


@router.get("/knowledge", summary="Get all knowledge", description="""
Get all knowledge JARVIS has learned about you.

**Query parameters:**
- `category` - Filter by category (preference, fact, skill, relationship)

**Returns:** All stored knowledge

**JARVIS use:** Build comprehensive user profile
""")
async def get_all_knowledge(
    category: Optional[str] = None, db: AsyncSession = Depends(get_db)
):
    """Get all knowledge"""
    service = LearningService(db)
    knowledge = await service.get_all_knowledge(category=category)

    return [
        {
            "id": k.id,
            "category": k.category,
            "key": k.key,
            "value": k.value,
            "source": k.source,
            "confidence": k.confidence,
            "context": k.context,
            "access_count": k.access_count,
            "verified": k.verified,
            "created_at": k.created_at.isoformat(),
        }
        for k in knowledge
    ]


@router.get("/knowledge/{category}/{key}", summary="Get specific knowledge", description="""
Get specific knowledge by category and key.

**Example:** GET /api/learning/knowledge/preference/favorite_coffee

**Returns:** The stored value and metadata

**JARVIS use:** Quick lookup of user preferences
""")
async def get_knowledge(
    category: str, key: str, db: AsyncSession = Depends(get_db)
):
    """Get specific knowledge"""
    service = LearningService(db)
    knowledge = await service.get_knowledge(category, key)

    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    return {
        "id": knowledge.id,
        "category": knowledge.category,
        "key": knowledge.key,
        "value": knowledge.value,
        "source": knowledge.source,
        "confidence": knowledge.confidence,
        "context": knowledge.context,
        "access_count": knowledge.access_count,
        "verified": knowledge.verified,
        "last_accessed": knowledge.last_accessed.isoformat()
        if knowledge.last_accessed
        else None,
    }


@router.get("/search", summary="Search knowledge", description="""
Search knowledge base by keyword.

**Example:** GET /api/learning/search?q=coffee

**Returns:** All knowledge matching the query

**JARVIS use:**
User: "What do you know about my coffee preferences?"
→ Search for "coffee"
→ Return all coffee-related knowledge
""")
async def search_knowledge(
    q: str = Query(..., description="Search query"), db: AsyncSession = Depends(get_db)
):
    """Search knowledge"""
    service = LearningService(db)
    results = await service.search_knowledge(q)

    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "id": k.id,
                "category": k.category,
                "key": k.key,
                "value": k.value,
                "confidence": k.confidence,
            }
            for k in results
        ],
    }


@router.delete("/knowledge/{knowledge_id}", summary="Forget knowledge", description="""
Delete knowledge from JARVIS's memory.

**JARVIS use:**
User: "Athena, forget my favorite coffee"
JARVIS: "Understood, I've forgotten that information."

**Use case:** Correct mistakes or remove outdated information
""")
async def forget_knowledge(knowledge_id: int, db: AsyncSession = Depends(get_db)):
    """Delete knowledge"""
    service = LearningService(db)
    success = await service.delete_knowledge(knowledge_id)

    if not success:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    return {"status": "forgotten", "knowledge_id": knowledge_id}


@router.post("/query", summary="Ask JARVIS a question", description="""
Query knowledge base with natural language.

**Example:**
```json
{
  "question": "What is my favorite coffee?",
  "context": {}
}
```

**JARVIS response:**
"Your favorite coffee is double espresso with oat milk."

**More examples:**
- "What's my brother's name?"
- "What do I prefer for breakfast?"
- "What are my skills in programming?"
- "When is my anniversary?"

**AI-powered:**
- Understands natural language
- Searches relevant knowledge
- Provides conversational answers
- Cites sources

**Use case:** Natural conversation about yourself
""")
async def query_knowledge(
    query: KnowledgeQuery, db: AsyncSession = Depends(get_db)
):
    """Query knowledge with natural language"""
    service = LearningService(db)
    result = await service.query(query.question, query.context)

    return result


@router.post("/extract", summary="Extract knowledge from conversation", description="""
Automatically extract knowledge from conversation text.

**Example:**
```json
{
  "conversation": "User: My favorite coffee is double espresso. I usually have it around 10 AM. My brother John introduced me to it."
}
```

**JARVIS extracts:**
- preference/favorite_coffee: "double espresso"
- fact/coffee_time: "10 AM"
- relationship/brother_name: "John"

**Returns:** List of extracted and stored knowledge

**JARVIS use:**
Learn from every conversation automatically without explicit "remember" commands.

**Use case:**
After chat, JARVIS: "I learned 3 new things about you:
 - Your favorite coffee
 - Your morning routine time
 - Your brother's name
Should I remember these?"

**Effect:** Passive learning from natural conversation
""")
async def extract_from_conversation(
    conversation: str = Body(..., embed=True), db: AsyncSession = Depends(get_db)
):
    """Extract knowledge from conversation"""
    service = LearningService(db)
    extracted = await service.extract_knowledge_from_conversation(conversation)

    return {
        "extracted_count": len(extracted),
        "knowledge": extracted,
        "message": f"Learned {len(extracted)} new things from conversation",
    }


@router.get("/graph/{knowledge_id}", summary="Get knowledge graph", description="""
Get knowledge with its related knowledge (graph view).

**Returns:** Knowledge item with all related items

**Use case:**
Show how different pieces of knowledge connect:
- "favorite_coffee" relates to "morning_routine"
- "brother_name" relates to "family_members"
- "programming_skills" relates to "work_projects"

**JARVIS use:** Build semantic understanding of user's life
""")
async def get_knowledge_graph(knowledge_id: int, db: AsyncSession = Depends(get_db)):
    """Get knowledge graph"""
    service = LearningService(db)
    graph = await service.get_knowledge_graph(knowledge_id)

    return graph


@router.get("/stats", summary="Get knowledge statistics", description="""
Get statistics about JARVIS's knowledge.

**Returns:**
- Total knowledge items
- By category breakdown
- By source (user-provided vs learned)
- Verified vs unverified
- Average confidence
- Most accessed knowledge

**JARVIS insight:**
"Sir, my knowledge about you:
 - 127 total items learned
 - 45 preferences
 - 32 facts
 - 18 skills
 - 32 relationship details
 - Average confidence: 0.92
 - Most accessed: Your favorite coffee (accessed 47 times)"

**Use case:** Show how much JARVIS knows about you
""")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get knowledge statistics"""
    service = LearningService(db)
    stats = await service.get_stats()

    return stats


@router.post("/teach-from-voice", summary="Teach from voice command", description="""
Parse natural language teaching command.

**Examples:**
- "Remember my favorite color is blue"
- "My brother's name is Michael"
- "I prefer tea over coffee in the afternoon"
- "I'm skilled at Python programming"

**Returns:** Parsed and stored knowledge

**JARVIS voice use:**
User: "Athena, remember: I'm allergic to peanuts"
JARVIS: "Understood. I'll remember you're allergic to peanuts and won't suggest foods containing them."

**Use case:** Natural voice teaching without structured JSON
""")
async def teach_from_voice(
    command: str = Body(..., embed=True), db: AsyncSession = Depends(get_db)
):
    """Parse and teach from natural voice command"""
    service = LearningService(db)

    # Use AI to parse the command
    try:
        from app.llm_claude import get_claude_llm

        claude = get_claude_llm()

        prompt = f"""Parse this teaching command and extract:
- category (preference, fact, skill, relationship)
- key (descriptive identifier)
- value (the actual information)
- context (any additional context)

Command: "{command}"

Respond in JSON:
{{"category": "...", "key": "...", "value": "...", "context": "..."}}"""

        response = await claude.chat(
            messages=[{"role": "user", "content": prompt}], max_tokens=200
        )

        # Extract JSON from response
        import re
        import json

        json_match = re.search(r"\{.*\}", response["message"]["content"], re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())

            # Store the knowledge
            learned = await service.teach(
                category=parsed["category"],
                key=parsed["key"],
                value=parsed["value"],
                source="user",
                confidence=1.0,
                context=parsed.get("context"),
            )

            return {
                "parsed": parsed,
                "knowledge_id": learned.id,
                "message": f"Understood. I'll remember: {parsed['value']}",
            }

        return {"error": "Failed to parse command"}

    except Exception as e:
        logger.error(f"Failed to parse teaching command: {e}")
        raise HTTPException(
            status_code=400, detail=f"Failed to parse command: {str(e)}"
        )
