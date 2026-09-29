"""
NVIDIA NIM integration - Free AI models from NVIDIA.
"""
from __future__ import annotations

import json
import logging
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
        tools: list[dict] | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        read_timeout: float | None = None,
    ) -> dict:
        """Chat with NVIDIA NIM API.

        Raises httpx.HTTPStatusError or httpx.TimeoutException on failure so the
        caller can classify the error without coupling to this module.
        """
        if not self.available:
            raise RuntimeError("NVIDIA API key not configured")

        settings = get_settings()
        connect_to = float(settings.llm_connect_timeout)
        read_to = read_timeout if read_timeout is not None else float(settings.llm_read_timeout)
        timeout = httpx.Timeout(connect=connect_to, read=read_to, write=10.0, pool=5.0)

        # Cap token generation at the provider's configured ceiling.
        effective_max = min(max_tokens, settings.nvidia_max_tokens)

        messages = inject_security_instruction(messages)

        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 1,
            "max_tokens": effective_max,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        if not settings.nvidia_reasoning:
            # Disables chain-of-thought thinking on Nemotron reasoning models.
            # Verified via live API: reasoning_content becomes None, saving 5–30 s.
            body["chat_template_kwargs"] = {"thinking": False}

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=body,
            )

        response.raise_for_status()
        data = response.json()

        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        raw_tcs = message.get("tool_calls") or []

        result: dict = {"message": {"role": "assistant", "content": content}}
        if raw_tcs:
            parsed = []
            for tc in raw_tcs:
                func = tc.get("function", {})
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, ValueError):
                        args = {}
                entry: dict = {"function": {"name": func.get("name", ""), "arguments": args}}
                if tc.get("id"):
                    entry["id"] = tc["id"]
                parsed.append(entry)
            result["message"]["tool_calls"] = parsed

        return result


# Initialized at module import so startup logs fire once during app startup.
_nvidia_llm = NvidiaLLM()


def get_nvidia_llm() -> NvidiaLLM:
    return _nvidia_llm
