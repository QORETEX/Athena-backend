"""
Groq AI integration - Fast and free LLM fallback.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
import httpx

from app.config import get_settings
from app.llm import inject_security_instruction

logger = logging.getLogger(__name__)


class GroqLLM:
    """Groq AI client."""

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.groq_api_key
        self.model = self.settings.groq_model
        self.available = bool(self.api_key)

        if self.available:
            logger.info("Groq AI enabled (model: %s)", self.model)
        else:
            logger.warning("No Groq API key")

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> dict:
        """Chat with Groq API.

        Raises httpx.HTTPStatusError or httpx.TimeoutException on failure so the
        caller can classify the error without coupling to this module.
        """
        if not self.available:
            raise RuntimeError("Groq API key not configured")

        messages = inject_security_instruction(messages)
        max_retries = 2
        retry_delay = 1.0

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

                    message = data["choices"][0]["message"]
                    content = message.get("content") or message.get("reasoning", "")

                    if not content:
                        logger.debug("Groq returned empty response: %s", data)
                        content = "I apologize, but I couldn't generate a response. Please try again."

                    return {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }

            except httpx.HTTPStatusError as e:
                if attempt < max_retries and e.response.status_code in [400, 500, 502, 503]:
                    logger.debug(
                        "Groq HTTP %d, retrying (attempt %d/%d)",
                        e.response.status_code, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise
            except Exception:
                raise


# Initialized at module import so startup logs fire once during app startup.
_groq_llm = GroqLLM()


def get_groq_llm() -> GroqLLM:
    return _groq_llm
