"""
Groq AI integration - Fast and Free LLM
"""
from __future__ import annotations

import logging
from typing import Optional
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class GroqLLM:
    """Groq AI client - Very fast and free"""

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.groq_api_key
        self.model = self.settings.groq_model
        self.available = bool(self.api_key)

        if self.available:
            logger.info(f"✅ Groq AI enabled (model: {self.model})")
        else:
            logger.warning("⚠️  No Groq API key")

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> dict:
        """
        Chat with Groq API

        Returns format compatible with Claude/Ollama:
        {
            "message": {
                "role": "assistant",
                "content": "response text"
            }
        }
        """
        if not self.available:
            raise Exception("Groq API key not configured")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )

                response.raise_for_status()
                data = response.json()

                # Convert to our standard format
                return {
                    "message": {
                        "role": "assistant",
                        "content": data["choices"][0]["message"]["content"],
                    }
                }

        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise


# Global instance
_groq_llm: Optional[GroqLLM] = None


def get_groq_llm() -> GroqLLM:
    """Get or create Groq LLM instance"""
    global _groq_llm
    if _groq_llm is None:
        _groq_llm = GroqLLM()
    return _groq_llm
