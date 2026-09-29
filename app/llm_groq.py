"""Groq AI integration - Fast and free LLM fallback."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import httpx

from app.config import get_settings
from app.llm import inject_security_instruction

logger = logging.getLogger(__name__)


class GroqAPIError(Exception):
    """Parsed Groq 4xx error — carries error.type/code/message, never keys or request body."""

    def __init__(
        self,
        http_status: int,
        error_type: str,
        error_code: str,
        error_message: str,
        retried: bool = False,
    ):
        self.http_status = http_status
        self.error_type = error_type
        self.error_code = error_code
        self.error_message = error_message
        self.retried = retried
        super().__init__(f"Groq {http_status}: {error_code or error_type or 'unknown'}")


def _parse_groq_error(response: httpx.Response) -> tuple[str, str, str]:
    """Extract (error_type, error_code, error_message) from a Groq error response."""
    try:
        body = response.json()
        err = body.get("error", {})
        return (err.get("type", ""), err.get("code", ""), err.get("message", ""))
    except Exception:
        return ("", "", "")


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
        tools: list[dict] | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        read_timeout: float | None = None,
    ) -> dict:
        """Chat with Groq API.

        Raises GroqAPIError for 4xx responses, httpx.TimeoutException / httpx.ConnectError
        on network failures, so the caller can classify the error without coupling here.
        """
        if not self.available:
            raise RuntimeError("Groq API key not configured")

        settings = get_settings()
        connect_to = float(settings.llm_connect_timeout)
        read_to = read_timeout if read_timeout is not None else float(settings.llm_read_timeout)
        timeout = httpx.Timeout(connect=connect_to, read=read_to, write=10.0, pool=5.0)

        # Cap token generation at the provider's configured ceiling.
        effective_max = min(max_tokens, settings.groq_max_tokens)

        messages = inject_security_instruction(messages)

        _tool_use_retried = False

        # At most one retry: connection errors or 429/5xx or tool_use_failed.
        # Read timeouts are never retried — the server is busy, a second request makes it worse.
        for attempt in range(2):
            try:
                json_body: dict = {
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": effective_max,
                    "temperature": temperature,
                }
                if tools:
                    json_body["tools"] = tools

                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=json_body,
                    )

                response.raise_for_status()
                data = response.json()

                message = data["choices"][0]["message"]
                content = message.get("content") or message.get("reasoning", "")
                raw_tcs = message.get("tool_calls") or []

                if not content and not raw_tcs:
                    logger.debug("Groq returned empty response: %s", data)
                    content = "I apologize, but I couldn't generate a response. Please try again."

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

            except httpx.ReadTimeout:
                raise

            except httpx.HTTPStatusError as e:
                status = e.response.status_code

                if 400 <= status < 500:
                    err_type, err_code, err_msg = _parse_groq_error(e.response)
                    logger.warning(
                        "Groq %d: type=%s code=%s message=%.200s",
                        status,
                        err_type or "-",
                        err_code or "-",
                        err_msg or "-",
                    )
                    # tool_use_failed: model produced a malformed tool call; retry once immediately.
                    if status == 400 and err_code == "tool_use_failed" and attempt == 0:
                        logger.info("Groq: model produced invalid tool call — retrying once")
                        _tool_use_retried = True
                        continue
                    retried = _tool_use_retried and err_code == "tool_use_failed"
                    raise GroqAPIError(status, err_type, err_code, err_msg, retried=retried) from e

                if attempt == 0 and status in (429, 500, 502, 503):
                    logger.debug("Groq HTTP %d, retrying (attempt 1/1)", status)
                    await asyncio.sleep(1.0)
                    continue
                raise

            except (httpx.ConnectTimeout, httpx.ConnectError):
                if attempt == 0:
                    logger.debug("Groq connection error, retrying (attempt 1/1)")
                    await asyncio.sleep(1.0)
                    continue
                raise


# Initialized at module import so startup logs fire once during app startup.
_groq_llm = GroqLLM()


def get_groq_llm() -> GroqLLM:
    return _groq_llm
