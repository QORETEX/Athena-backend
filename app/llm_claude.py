"""
Claude AI integration - Primary LLM for Athena
Uses Claude for best intelligence, falls back to Ollama if unavailable
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.llm import chat_with_tools as ollama_chat_with_tools

logger = logging.getLogger(__name__)


class ClaudeLLM:
    """Claude AI client with Ollama fallback"""

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncAnthropic] = None
        self.available = False

        if self.settings.anthropic_api_key:
            self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
            self.available = True
            logger.info("✅ Claude AI enabled (primary LLM)")
        else:
            logger.warning("⚠️  No Claude API key - using Ollama only")

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: int = 2000,
    ) -> dict:
        """
        Chat with Claude, fallback to Groq/Ollama if unavailable

        Fallback order: Claude → Groq → Ollama

        Returns same format as ollama chat_with_tools for compatibility
        """
        if not self.available or not self.client:
            logger.debug("Claude unavailable, trying fallback")
            return await self._fallback_chat(messages, tools, max_tokens)

        try:
            # Try Claude first
            response = await self._chat_claude(messages, tools, max_tokens)
            return response

        except Exception as e:
            logger.warning(f"Claude failed ({e}), trying fallback")
            # Fallback to Groq or Ollama
            return await self._fallback_chat(messages, tools, max_tokens)

    async def _fallback_chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        max_tokens: int,
    ) -> dict:
        """
        Try fallback LLMs in order: Groq → NVIDIA → Ollama

        Priority:
        1. Groq - Fast and free (30 req/min)
        2. NVIDIA NIM - Free, good quality
        3. Ollama - Local, always available
        """

        # Try Groq first (fastest, free)
        try:
            from app.llm_groq import get_groq_llm

            groq = get_groq_llm()
            if groq.available:
                logger.info("🔄 Using Groq (Claude unavailable)")
                response = await groq.chat(messages, max_tokens=max_tokens)
                return response
        except Exception as e:
            logger.debug(f"Groq failed ({e}), trying NVIDIA")

        # Try NVIDIA NIM second (free, reliable)
        try:
            from app.llm_nvidia import get_nvidia_llm

            nvidia = get_nvidia_llm()
            if nvidia.available:
                logger.info("🔄 Using NVIDIA NIM (Claude & Groq unavailable)")
                response = await nvidia.chat(messages, max_tokens=max_tokens)
                return response
        except Exception as e:
            logger.debug(f"NVIDIA failed ({e}), trying Ollama")

        # Fall back to Ollama (local)
        logger.info("🔄 Using Ollama (all cloud LLMs unavailable)")
        return await ollama_chat_with_tools(messages, tools)

    async def _chat_claude(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        max_tokens: int
    ) -> dict:
        """Chat with Claude API"""
        # Separate system message from conversation
        system_prompt = ""
        conversation = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation.append(msg)

        # Convert tools to Claude format if provided
        claude_tools = None
        if tools:
            claude_tools = self._convert_tools_to_claude(tools)

        # Call Claude
        response = await self.client.messages.create(
            model=self.settings.claude_model,
            max_tokens=max_tokens,
            system=system_prompt or "You are Athena, a helpful AI assistant.",
            messages=conversation,
            tools=claude_tools or []
        )

        # Convert Claude response to Ollama-compatible format
        return self._convert_claude_to_ollama_format(response)

    def _convert_tools_to_claude(self, ollama_tools: list[dict]) -> list[dict]:
        """Convert Ollama tool format to Claude tool format"""
        claude_tools = []

        for tool in ollama_tools:
            # Ollama format: {type: "function", function: {name, description, parameters}}
            func = tool.get("function", {})

            claude_tool = {
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {})
            }

            claude_tools.append(claude_tool)

        return claude_tools

    def _convert_claude_to_ollama_format(self, claude_response) -> dict:
        """Convert Claude response to Ollama-compatible format"""
        # Extract content and tool calls
        content_text = ""
        tool_calls = []

        for block in claude_response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                # Convert to Ollama tool call format
                tool_calls.append({
                    "function": {
                        "name": block.name,
                        "arguments": block.input
                    }
                })

        # Build Ollama-compatible response
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
        """
        Stream Claude responses for instant feel
        Yields text chunks as they arrive
        """
        if not self.available or not self.client:
            # Ollama doesn't support streaming easily, just return full response
            response = await ollama_chat_with_tools(messages, None)
            yield response["message"]["content"]
            return

        try:
            # Separate system message
            system_prompt = ""
            conversation = []

            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                else:
                    conversation.append(msg)

            # Stream from Claude
            async with self.client.messages.stream(
                model=self.settings.claude_model,
                max_tokens=max_tokens,
                system=system_prompt or "You are Athena, a helpful AI assistant.",
                messages=conversation,
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.warning(f"Claude streaming failed: {e}")
            # Fallback: full response from Ollama
            response = await ollama_chat_with_tools(messages, None)
            yield response["message"]["content"]


# Global instance
_claude_llm: Optional[ClaudeLLM] = None


def get_claude_llm() -> ClaudeLLM:
    """Get or create Claude LLM instance"""
    global _claude_llm
    if _claude_llm is None:
        _claude_llm = ClaudeLLM()
    return _claude_llm
