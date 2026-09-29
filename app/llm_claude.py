"""
Claude AI integration - Primary LLM for Athena.
Falls back through Groq -> NVIDIA -> Ollama on failure.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.llm import SECURITY_INSTRUCTION, chat_with_tools as ollama_chat_with_tools
# Top-level imports trigger module-level singleton init (startup logs fire once).
from app.llm_groq import get_groq_llm, GroqAPIError
from app.llm_nvidia import get_nvidia_llm

logger = logging.getLogger(__name__)


# ── Error helpers ─────────────────────────────────────────────────────────────


def _classify_error(exc: Exception, elapsed: float = 0.0) -> str:
    """Map an exception to a short, safe reason string — no keys or full URLs."""
    if isinstance(exc, GroqAPIError):
        if exc.error_code == "tool_use_failed":
            suffix = " (retried)" if exc.retried else ""
            return f"model produced an invalid tool call{suffix}"
        msg = (exc.error_message or "")[:200]
        base = "bad request" if exc.http_status == 400 else f"status {exc.http_status}"
        return f"{base}: {msg}" if msg else base
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
        if elapsed > 0:
            return f"timed out after {elapsed:.1f}s"
        return "timed out"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return "connection failed"
    return f"unexpected error: {type(exc).__name__}"


def _log_success(
    provider: str,
    model: str,
    elapsed: float,
    tried: list[tuple[str, str]],
    msg_count: int = 0,
    req_chars: int = 0,
) -> None:
    """Log the single per-request INFO line on success."""
    parts = [f"{n} {r}" for n, r in tried]
    after = ", ".join(parts)
    size_info = f" [{msg_count} msgs/{req_chars} chars]" if msg_count else ""
    if after:
        logger.info(
            "chat served by %s (%s) in %.1fs%s after: %s",
            provider, model, elapsed, size_info, after,
        )
    else:
        logger.info(
            "chat served by %s (%s) in %.1fs%s",
            provider, model, elapsed, size_info,
        )


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
            logger.info("No Claude API key - using fallback chain")

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
        settings = get_settings()
        chain_deadline = time.monotonic() + settings.llm_chain_deadline
        tried: list[tuple[str, str]] = []  # (provider_name, reason_or_"skipped")

        msg_count = len(messages)
        req_chars = sum(len(str(m.get("content") or "")) for m in messages)

        def _remaining() -> float:
            return chain_deadline - time.monotonic()

        def _read_to() -> float:
            rem = _remaining()
            return min(float(settings.llm_read_timeout), max(0.5, rem))

        # 1. Claude ────────────────────────────────────────────────────────────
        if not self.available or not self.client:
            tried.append(("claude", "skipped"))
        elif _remaining() <= 0:
            tried.append(("claude", "chain budget exhausted"))
        else:
            t0 = time.monotonic()
            try:
                result = await self._chat_claude(messages, tools, max_tokens)
                _log_success("claude", self.settings.claude_model, time.monotonic() - t0, tried, msg_count, req_chars)
                return result
            except Exception as e:
                tried.append(("claude", _classify_error(e, time.monotonic() - t0)))

        # 2. Groq ─────────────────────────────────────────────────────────────
        groq = get_groq_llm()
        if not groq.available:
            tried.append(("groq", "skipped"))
        elif _remaining() <= 0:
            tried.append(("groq", "chain budget exhausted"))
        else:
            t0 = time.monotonic()
            try:
                result = await groq.chat(messages, tools=tools, max_tokens=max_tokens, read_timeout=_read_to())
                _log_success("groq", groq.model, time.monotonic() - t0, tried, msg_count, req_chars)
                return result
            except Exception as e:
                tried.append(("groq", _classify_error(e, time.monotonic() - t0)))

        # 3. NVIDIA ───────────────────────────────────────────────────────────
        nvidia = get_nvidia_llm()
        if not nvidia.available:
            tried.append(("nvidia", "skipped"))
        elif _remaining() <= 0:
            tried.append(("nvidia", "chain budget exhausted"))
        else:
            t0 = time.monotonic()
            try:
                result = await nvidia.chat(messages, tools=tools, max_tokens=max_tokens, read_timeout=_read_to())
                _log_success("nvidia", nvidia.model, time.monotonic() - t0, tried, msg_count, req_chars)
                return result
            except Exception as e:
                tried.append(("nvidia", _classify_error(e, time.monotonic() - t0)))

        # 4. Ollama ───────────────────────────────────────────────────────────
        if settings.ollama_enabled:
            if _remaining() <= 0:
                tried.append(("ollama", "chain budget exhausted"))
            else:
                t0 = time.monotonic()
                result = await ollama_chat_with_tools(messages, tools)
                if not result.get("error"):
                    _log_success("ollama", settings.ollama_model, time.monotonic() - t0, tried, msg_count, req_chars)
                    return result
                tried.append(("ollama", result.get("error", "failed")))

        # All providers failed ─────────────────────────────────────────────────
        failed = [(n, r) for n, r in tried if r not in ("skipped", "chain budget exhausted")]
        exhausted = [n for n, r in tried if r == "chain budget exhausted"]

        parts = [f"{n}: {r}" for n, r in failed]
        if exhausted:
            parts.append(
                f"chain budget of {settings.llm_chain_deadline}s exhausted, skipped: {', '.join(exhausted)}"
            )
        reasons = "; ".join(parts) if parts else "all providers skipped or unconfigured"

        logger.warning("All LLM providers failed: %s", reasons)
        return {
            "message": {
                "role": "assistant",
                "content": reasons,
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

        # chat.py stores second-round tool history in OpenAI format (shared by all providers).
        # The Anthropic API needs its own format: assistant tool_use content blocks and user
        # tool_result blocks.  Convert here so chat.py stays provider-neutral.
        conversation = self._to_anthropic_messages(conversation)

        response = await self.client.messages.create(
            model=self.settings.claude_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=conversation,
            tools=claude_tools or [],
        )

        return self._convert_claude_to_ollama_format(response)

    def _to_anthropic_messages(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI-format tool history to Anthropic message format.

        Rewrites two OpenAI-specific patterns:
        - assistant message with "tool_calls" list  →  assistant content with tool_use blocks
        - role "tool" messages (one or more)         →  single user message with tool_result blocks
        Plain user/assistant messages are passed through unchanged.
        """
        result: list[dict] = []
        pending_results: list[dict] = []

        def _flush_tool_results() -> None:
            if pending_results:
                result.append({"role": "user", "content": list(pending_results)})
                pending_results.clear()

        for msg in messages:
            role = msg.get("role")

            if role == "tool":
                # Accumulate consecutive tool results; they become one user message.
                pending_results.append({
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                })
            else:
                _flush_tool_results()
                if role == "assistant" and msg.get("tool_calls"):
                    # Rebuild as Anthropic assistant content blocks.
                    content: list[dict] = []
                    if msg.get("content"):
                        content.append({"type": "text", "text": msg["content"]})
                    for tc in msg["tool_calls"]:
                        func = tc.get("function", {})
                        args = func.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, ValueError):
                                args = {}
                        content.append({
                            "type": "tool_use",
                            "id": tc.get("id") or f"toolu_{func.get('name', 'unknown')}",
                            "name": func.get("name", ""),
                            "input": args,
                        })
                    result.append({"role": "assistant", "content": content})
                else:
                    result.append(msg)

        _flush_tool_results()
        return result

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
                    "id": block.id,  # preserved so chat.py can match tool_call_id on second round
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
_claude_llm = ClaudeLLM()


def get_claude_llm() -> ClaudeLLM:
    return _claude_llm
