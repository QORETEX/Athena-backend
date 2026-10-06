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
        tools: Optional[list[dict]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        stream: bool = False,
    ):
        """
        Chat with Groq API with retry logic and tool support

        Returns format compatible with Claude/Ollama:
        {
            "message": {
                "role": "assistant",
                "content": "response text",
                "tool_calls": [...]  # if tools were called
            }
        }
        """
        if not self.available:
            raise Exception("Groq API key not configured")

        # Build request payload
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

        # Add reasoning_effort for reasoning models (gpt-oss-120b)
        # Only add when NOT streaming (reasoning+streaming has issues with tool calls)
        if "gpt-oss" in self.model and not stream:
            payload["reasoning_effort"] = "medium"

        # Add tools if provided (OpenAI function calling format)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Handle streaming - return generator immediately
        if stream:
            return self._stream_response(payload)

        # Non-streaming with retry logic
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
                        json=payload,
                    )

                    response.raise_for_status()
                    data = response.json()

                    # Get content from either content or reasoning field
                    # (reasoning models put response in 'reasoning' field)
                    message = data["choices"][0]["message"]
                    content = message.get("content") or message.get("reasoning", "") or ""

                    # Check for tool calls
                    tool_calls = message.get("tool_calls")

                    # Convert to our standard format
                    result = {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }

                    # Add tool calls if present
                    if tool_calls:
                        result["message"]["tool_calls"] = tool_calls

                    return result

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

    async def _stream_response(self, payload: dict):
        """Stream response from Groq API"""
        try:
            logger.info("🌊 Creating HTTP client for streaming...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info("🌊 Starting stream request to Groq...")
                async with client.stream(
                    "POST",
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    logger.info(f"🌊 Got response status: {response.status_code}")
                    response.raise_for_status()

                    # Parse SSE stream
                    logger.info("🌊 Starting to iterate lines...")
                    async for line in response.aiter_lines():
                        logger.debug(f"🌊 Got line: {line[:100]}...")
                        if not line or line.startswith(":"):
                            continue

                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix

                            if data_str == "[DONE]":
                                break

                            try:
                                import json
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})

                                # Yield content if present
                                if "content" in delta:
                                    yield {
                                        "type": "content",
                                        "content": delta["content"]
                                    }

                                # Yield reasoning if present
                                if "reasoning" in delta:
                                    yield {
                                        "type": "reasoning",
                                        "content": delta["reasoning"]
                                    }

                                # Yield tool calls if present
                                if "tool_calls" in delta:
                                    yield {
                                        "type": "tool_calls",
                                        "tool_calls": delta["tool_calls"]
                                    }

                            except json.JSONDecodeError:
                                continue

        except httpx.HTTPStatusError as e:
            logger.error(f"Groq streaming error: {e}")
            yield {
                "type": "error",
                "error": f"HTTP {e.response.status_code}"
            }
        except Exception as e:
            logger.error(f"Groq streaming error: {e}")
            yield {
                "type": "error",
                "error": str(e)
            }


# Global instance
_groq_llm: Optional[GroqLLM] = None


def get_groq_llm() -> GroqLLM:
    """Get or create Groq LLM instance"""
    global _groq_llm
    if _groq_llm is None:
        _groq_llm = GroqLLM()
    return _groq_llm
