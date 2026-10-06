"""
Gemini AI integration - Google's powerful reasoning model
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
import json

from app.config import get_settings

logger = logging.getLogger(__name__)


class GeminiLLM:
    """Gemini AI client - Powerful reasoning and multimodal"""

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.gemini_api_key
        self.model = self.settings.gemini_model
        self.available = bool(self.api_key)

        if self.available:
            logger.info(f"✅ Gemini AI enabled (model: {self.model})")
        else:
            logger.warning("⚠️  No Gemini API key")

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        stream: bool = False,
    ):
        """
        Chat with Gemini API

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
            raise Exception("Gemini API key not configured")

        # Import here to avoid loading if not needed
        from google import genai
        from google.genai import types

        def _call_gemini():
            client = genai.Client(api_key=self.api_key)

            # Convert messages to Gemini format
            gemini_messages = self._convert_messages(messages)

            # Prepare config
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            # Add tools if provided
            if tools:
                gemini_tools = self._convert_tools(tools)
                config.tools = gemini_tools

            # Make request
            response = client.models.generate_content(
                model=self.model,
                contents=gemini_messages,
                config=config,
            )

            # Extract response
            if not response.candidates:
                raise Exception("No response from Gemini")

            candidate = response.candidates[0]
            content = ""
            tool_calls = []

            # Extract text content
            for part in candidate.content.parts:
                if part.text:
                    content += part.text
                elif hasattr(part, 'function_call') and part.function_call:
                    # Extract tool call
                    tool_calls.append({
                        "id": f"call_{len(tool_calls)}",
                        "type": "function",
                        "function": {
                            "name": part.function_call.name,
                            "arguments": json.dumps(dict(part.function_call.args)),
                        }
                    })

            result = {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }

            if tool_calls:
                result["message"]["tool_calls"] = tool_calls

            return result

        # Run in thread to avoid blocking
        return await asyncio.to_thread(_call_gemini)

    def _convert_messages(self, messages: list[dict]) -> list:
        """Convert OpenAI format messages to Gemini format"""
        gemini_messages = []

        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            # Map roles
            if role == "system":
                # Gemini doesn't have system role, prepend to first user message
                continue
            elif role == "assistant":
                gemini_role = "model"
            elif role == "user":
                gemini_role = "user"
            elif role == "tool":
                # Tool results - convert to user message with prefix
                gemini_role = "user"
                content = f"Tool result: {content}"
            else:
                gemini_role = "user"

            gemini_messages.append({
                "role": gemini_role,
                "parts": [{"text": content}] if content else []
            })

        # Prepend system message to first user message if exists
        system_msg = next((m for m in messages if m["role"] == "system"), None)
        if system_msg and gemini_messages:
            first_user = next((m for m in gemini_messages if m["role"] == "user"), None)
            if first_user:
                first_user["parts"].insert(0, {"text": f"System: {system_msg['content']}\n\n"})

        return gemini_messages

    def _convert_tools(self, tools: list[dict]) -> list:
        """Convert OpenAI function format to Gemini function format"""
        from google.genai import types

        function_declarations = []

        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]

                # Convert parameters schema
                parameters = func.get("parameters", {})

                gemini_func = types.FunctionDeclaration(
                    name=func["name"],
                    description=func.get("description", ""),
                    parameters=parameters
                )

                function_declarations.append(gemini_func)

        # Wrap functions in a Tool object
        return [types.Tool(function_declarations=function_declarations)]


# Singleton instance
_gemini_llm: Optional[GeminiLLM] = None


def get_gemini_llm() -> GeminiLLM:
    """Get singleton Gemini LLM instance"""
    global _gemini_llm
    if _gemini_llm is None:
        _gemini_llm = GeminiLLM()
    return _gemini_llm
