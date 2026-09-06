import logging

from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_knowledge_search(query: str, top_k: int = 5) -> dict:
    try:
        from app.knowledge.ingest import search_knowledge

        results = await search_knowledge(query, top_k=top_k)
        return {"results": results, "query": query}
    except Exception as e:
        logger.warning("Knowledge search failed: %s", e)
        return {"error": str(e), "query": query}


register_skill(
    Skill(
        name="search_knowledge",
        description="Search the user's offline knowledge base (ingested documents like PDFs, text files). Use this when the user asks about their own documents or stored information.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in the knowledge base",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)",
                },
            },
            "required": ["query"],
        },
        handler=handle_knowledge_search,
    )
)
