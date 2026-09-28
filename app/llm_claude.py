"""
Claude AI integration - Primary LLM for Athena
Uses Claude for best intelligence, falls back to Groq → NVIDIA → Ollama.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.llm import SECURITY_INSTRUCTION, chat_with_tools as ollama_chat_with_tools

logger = logging.getLogger(__name__)


class ClaudeLLM:
    """Claude AI client with Groq / NVIDIA / Ollama fallback chain."""

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncAnthropic] = None
        self.available = False

        if self.settings.anthropic_api_key:
            self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
            self.available = True
            logger.info("✅ Claude AI enabled (primary LLM)")
        else:
            logger.warning("⚠️  No Claude API key - using fallback chain")

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: int = 2000,
    ) -> dict:
        """
        Chat with Claude; fall back to Groq → NVIDIA → Ollama on failure.
        Returns same format as ollama chat_with_tools for compatibility.
        """
        if not self.available or not self.client:
            logger.debug("Claude unavailable, trying fallback")
            return await self._fallback_chat(messages, tools, max_tokens)

        try:
            return await self._chat_claude(messages, tools, max_tokens)
        except Exception as e:
            logger.warning(f"Claude failed ({e}), trying fallback")
            return await self._fallback_chat(messages, tools, max_tokens)

    async def _fallback_chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        max_tokens: int,
    ) -> dict:
        """Try fallback LLMs in order: Groq → NVIDIA → Ollama (if enabled)."""

        try:
            from app.llm_groq import get_groq_llm

            groq = get_groq_llm()
            if groq.available:
                logger.info("🔄 Using Groq (Claude unavailable)")
                return await groq.chat(messages, max_tokens=max_tokens)
        except Exception as e:
            logger.debug(f"Groq failed ({e}), trying NVIDIA")

        try:
            from app.llm_nvidia import get_nvidia_llm

            nvidia = get_nvidia_llm()
            if nvidia.available:
                logger.info("🔄 Using NVIDIA NIM (Claude & Groq unavailable)")
                return await nvidia.chat(messages, max_tokens=max_tokens)
        except Exception as e:
            logger.debug(f"NVIDIA failed ({e}), trying Ollama")

        # Ollama: only attempt when configured — avoids a 120 s connection timeout.
        settings = get_settings()
        if settings.ollama_enabled:
            logger.info("🔄 Using Ollama (all cloud LLMs unavailable)")
            return await ollama_chat_with_tools(messages, tools)

        logger.error("No LLM provider is available")
        return {
            "message": {
                "role": "assistant",
                "content": (
                    "No language model is available. "
                    "Please configure at least one of: ANTHROPIC_API_KEY, GROQ_API_KEY, "
                    "NVIDIA_API_KEY, or OLLAMA_BASE_URL."
                ),
            },
            "error": "no_llm_available",
        }

    async def _chat_claude(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        max_tokens: int
    ) -> dict:
        """Chat with the Claude API."""
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
            tools=claude_tools or []
        )

        return self._convert_claude_to_ollama_format(response)

    def _convert_tools_to_claude(self, ollama_tools: list[dict]) -> list[dict]:
        """Convert Ollama tool format to Claude tool format."""
        claude_tools = []
        for tool in ollama_tools:
            func = tool.get("function", {})
            claude_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {})
            })
        return claude_tools

    def _convert_claude_to_ollama_format(self, claude_response) -> dict:
        """Convert Claude response to Ollama-compatible format."""
        content_text = ""
        tool_calls = []

        for block in claude_response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "function": {
                        "name": block.name,
                        "arguments": block.input
                    }
                })

        result = {
            "message": {
                "role": "assistant",
                "content": content_text,
            }
        }
        if tool_calls:
            result["message"]["tool_calls"] = tool_calls
        return result

    async def stream_chat(
        self,
        messages: list[dict],
        max_tokens: int = 2000
    ):
        """Stream Claude responses. Falls back to Ollama (no streaming) if unavailable."""
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
            logger.warning(f"Claude streaming failed: {e}")
            response = await ollama_chat_with_tools(messages, None)
            yield response["message"]["content"]


# Global instance
_claude_llm: Optional[ClaudeLLM] = None


def get_claude_llm() -> ClaudeLLM:
    """Get or create the Claude LLM instance."""
    global _claude_llm
    if _claude_llm is None:
        _claude_llm = ClaudeLLM()
    return _claude_llm
