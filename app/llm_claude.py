"""
Claude AI integration - Primary LLM for Athena.
Falls back through Groq -> NVIDIA -> Ollama on failure.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.llm import SECURITY_INSTRUCTION, chat_with_tools as ollama_chat_with_tools
# Top-level imports trigger module-level singleton init (startup logs fire once).
from app.llm_groq import get_groq_llm
from app.llm_nvidia import get_nvidia_llm

logger = logging.getLogger(__name__)


# ── Error helpers ─────────────────────────────────────────────────────────────


def _classify_error(exc: Exception) -> str:
    """Map an exception to a short, safe reason string — no keys or full URLs."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return f"invalid or unauthorized key ({code})"
        if code == 404:
            return f"model not found ({code})"
        if code == 429:
            return f"rate limited ({code})"
        return f"status {code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timed out"
    return "unexpected error"


def _log_success(
    provider: str,
    model: str,
    elapsed: float,
    tried: list[tuple[str, str]],
) -> None:
    """Log the single per-request INFO line on success."""
    parts = [f"{n} {r}" for n, r in tried]
    after = ", ".join(parts)
    if after:
        logger.info("chat served by %s (%s) in %.1fs after: %s", provider, model, elapsed, after)
    else:
        logger.info("chat served by %s (%s) in %.1fs", provider, model, elapsed)


# ── LLM client ────────────────────────────────────────────────────────────────


class ClaudeLLM:
    """Claude AI client with Groq / NVIDIA / Ollama fallback chain."""

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncAnthropic] = None
        self.available = False

        if self.settings.anthropic_api_key:
            self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
            self.available = True
            logger.info("Claude AI enabled (primary LLM)")
        else:
            logger.warning("No Claude API key - using fallback chain")

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: int = 2000,
    ) -> dict:
        """Try each provider in order; return the first success.

        On total failure returns:
            {"message": {...}, "error": "llm_providers_failed"}

        Logs exactly one INFO on success and one WARNING on total failure.
        """
        tried: list[tuple[str, str]] = []  # (provider_name, reason_or_"skipped")

        # 1. Claude ────────────────────────────────────────────────────────────
        if not self.available or not self.client:
            tried.append(("claude", "skipped"))
        else:
            t0 = time.monotonic()
            try:
                result = await self._chat_claude(messages, tools, max_tokens)
                _log_success("claude", self.settings.claude_model, time.monotonic() - t0, tried)
                return result
            except Exception as e:
                tried.append(("claude", _classify_error(e)))

        # 2. Groq ─────────────────────────────────────────────────────────────
        groq = get_groq_llm()
        if not groq.available:
            tried.append(("groq", "skipped"))
        else:
            t0 = time.monotonic()
            try:
                result = await groq.chat(messages, max_tokens=max_tokens)
                _log_success("groq", groq.model, time.monotonic() - t0, tried)
                return result
            except Exception as e:
                tried.append(("groq", _classify_error(e)))

        # 3. NVIDIA ───────────────────────────────────────────────────────────
        nvidia = get_nvidia_llm()
        if not nvidia.available:
            tried.append(("nvidia", "skipped"))
        else:
            t0 = time.monotonic()
            try:
                result = await nvidia.chat(messages, max_tokens=max_tokens)
                _log_success("nvidia", nvidia.model, time.monotonic() - t0, tried)
                return result
            except Exception as e:
                tried.append(("nvidia", _classify_error(e)))

        # 4. Ollama ───────────────────────────────────────────────────────────
        settings = get_settings()
        if settings.ollama_enabled:
            t0 = time.monotonic()
            result = await ollama_chat_with_tools(messages, tools)
            if not result.get("error"):
                _log_success("ollama", settings.ollama_model, time.monotonic() - t0, tried)
                return result
            tried.append(("ollama", result.get("error", "failed")))

        # All providers failed ─────────────────────────────────────────────────
        failed = [(n, r) for n, r in tried if r != "skipped"]
        reasons = "; ".join(f"{n}: {r}" for n, r in failed)
        logger.warning("All LLM providers failed: %s", reasons)
        return {
            "message": {
                "role": "assistant",
                "content": reasons or "All configured providers failed",
            },
            "error": "llm_providers_failed",
        }

    async def _chat_claude(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        max_tokens: int,
    ) -> dict:
        system_prompt = ""
        conversation = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation.append(msg)

        claude_tools = self._convert_tools_to_claude(tools) if tools else None

        if SECURITY_INSTRUCTION not in system_prompt:
            system_prompt = system_prompt + ("\n" if system_prompt else "") + SECURITY_INSTRUCTION

        response = await self.client.messages.create(
            model=self.settings.claude_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=conversation,
            tools=claude_tools or [],
        )

        return self._convert_claude_to_ollama_format(response)

    def _convert_tools_to_claude(self, ollama_tools: list[dict]) -> list[dict]:
        claude_tools = []
        for tool in ollama_tools:
            func = tool.get("function", {})
            claude_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        return claude_tools

    def _convert_claude_to_ollama_format(self, claude_response) -> dict:
        content_text = ""
        tool_calls = []

        for block in claude_response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "function": {
                        "name": block.name,
                        "arguments": block.input,
                    }
                })

        result = {"message": {"role": "assistant", "content": content_text}}
        if tool_calls:
            result["message"]["tool_calls"] = tool_calls
        return result

    async def stream_chat(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
    ):
        """Stream Claude responses. Falls back to Ollama (non-streaming) if unavailable."""
        if not self.available or not self.client:
            response = await ollama_chat_with_tools(messages, None)
            yield response["message"]["content"]
            return

        try:
            system_prompt = ""
            conversation = []
            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                else:
                    conversation.append(msg)

            if SECURITY_INSTRUCTION not in system_prompt:
                system_prompt = system_prompt + ("\n" if system_prompt else "") + SECURITY_INSTRUCTION

            async with self.client.messages.stream(
                model=self.settings.claude_model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=conversation,
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.warning("Claude streaming failed: %s", e)
            response = await ollama_chat_with_tools(messages, None)
            yield response["message"]["content"]


# Initialized at module import so startup logs fire once during app startup.
_claude_llm: Optional[ClaudeLLM] = None


def get_claude_llm() -> ClaudeLLM:
    global _claude_llm
    if _claude_llm is None:
        _claude_llm = ClaudeLLM()
    return _claude_llm
