"""
Groq AI integration - Fast and Free LLM
"""
from __future__ import annotations

import asyncio
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
        Chat with Groq API with retry logic

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

        max_retries = 2
        retry_delay = 1.0  # seconds

        for attempt in range(max_retries + 1):
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

                    # Get content from either content or reasoning field
                    # (reasoning models put response in 'reasoning' field)
                    message = data["choices"][0]["message"]
                    content = message.get("content") or message.get("reasoning", "")

                    # If still empty, log the full response for debugging
                    if not content:
                        logger.warning(f"Groq returned empty response: {data}")
                        content = "I apologize, but I couldn't generate a response. Please try again."

                    # Convert to our standard format
                    return {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }

            except httpx.HTTPStatusError as e:
                # Retry on 400/500 errors (common on first request after startup)
                if attempt < max_retries and e.response.status_code in [400, 500, 502, 503]:
                    logger.warning(f"Groq API error {e.response.status_code}, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(f"Groq API error: {e}")
                    raise
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
