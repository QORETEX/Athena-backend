"""
NVIDIA NIM integration - Free AI models from NVIDIA.
"""
from __future__ import annotations

import logging
from typing import Optional
import httpx

from app.config import get_settings
from app.llm import inject_security_instruction

logger = logging.getLogger(__name__)


class NvidiaLLM:
    """NVIDIA NIM client."""

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.nvidia_api_key
        self.model = self.settings.nvidia_model
        self.available = bool(self.api_key)

        if self.available:
            logger.info("NVIDIA NIM enabled (model: %s)", self.model)
        else:
            logger.warning("No NVIDIA API key")

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> dict:
        """Chat with NVIDIA NIM API.

        Raises httpx.HTTPStatusError or httpx.TimeoutException on failure so the
        caller can classify the error without coupling to this module.
        """
        if not self.available:
            raise RuntimeError("NVIDIA API key not configured")

        messages = inject_security_instruction(messages)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "top_p": 1,
                    "max_tokens": max_tokens,
                    "stream": False,
                },
            )

            response.raise_for_status()
            data = response.json()

            return {
                "message": {
                    "role": "assistant",
                    "content": data["choices"][0]["message"]["content"],
                }
            }


# Initialized at module import so startup logs fire once during app startup.
_nvidia_llm = NvidiaLLM()


def get_nvidia_llm() -> NvidiaLLM:
    return _nvidia_llm
