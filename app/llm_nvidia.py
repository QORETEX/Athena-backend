"""
NVIDIA NIM integration - Free AI models from NVIDIA
"""
from __future__ import annotations

import logging
from typing import Optional
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class NvidiaLLM:
    """NVIDIA NIM client - Free AI models"""

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.nvidia_api_key
        self.model = self.settings.nvidia_model
        self.available = bool(self.api_key)

        if self.available:
            logger.info(f"✅ NVIDIA NIM enabled (model: {self.model})")
        else:
            logger.warning("⚠️  No NVIDIA API key")

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> dict:
        """
        Chat with NVIDIA NIM API

        Returns format compatible with Claude/Ollama:
        {
            "message": {
                "role": "assistant",
                "content": "response text"
            }
        }
        """
        if not self.available:
            raise Exception("NVIDIA API key not configured")

        try:
            # NVIDIA NIM uses specific model endpoints
            # Full model list: https://build.nvidia.com/explore/discover
            base_url = "https://integrate.api.nvidia.com/v1"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
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

                # Convert to our standard format
                return {
                    "message": {
                        "role": "assistant",
                        "content": data["choices"][0]["message"]["content"],
                    }
                }

        except Exception as e:
            logger.error(f"NVIDIA API error: {e}")
            raise


# Global instance
_nvidia_llm: Optional[NvidiaLLM] = None


def get_nvidia_llm() -> NvidiaLLM:
    """Get or create NVIDIA LLM instance"""
    global _nvidia_llm
    if _nvidia_llm is None:
        _nvidia_llm = NvidiaLLM()
    return _nvidia_llm
