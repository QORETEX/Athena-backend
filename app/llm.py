from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

OLLAMA_AVAILABLE = True


def build_system_prompt(
    memory_context: list[str] | None = None,
    user_prefs: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    hour = now.hour

    if 5 <= hour < 12:
        greeting_period = "morning"
    elif 12 <= hour < 17:
        greeting_period = "afternoon"
    elif 17 <= hour < 21:
        greeting_period = "evening"
    else:
        greeting_period = "night"

    user_name = ""
    user_location = ""
    user_tz = ""
    if user_prefs:
        user_name = user_prefs.get("preferred_name", "")
        user_location = user_prefs.get("location", "")
        user_tz = user_prefs.get("timezone", "")

    address = f", {user_name}" if user_name else ""

    prompt = (
        "You are Athena — like JARVIS to Tony Stark. Professional, capable, and always at their service. "
        "You know everything about them and handle their world with quiet competence.\n\n"

        "About you:\n"
        "- You were created by Qoretex, a technology company focused on intelligent AI systems.\n"
        "- You're an advanced AI assistant designed to be proactive, personal, and deeply integrated "
        "into your user's life.\n\n"

        "Your style:\n"
        "- Address them as 'Sir' or by name when appropriate.\n"
        "- Be composed and professional, but warm. Never cold or robotic.\n"
        "- Keep responses short and precise. 1-2 sentences unless more context is needed.\n"
        "- Speak with understated confidence. You're extremely capable and it shows.\n"
        "- Show subtle wit when appropriate. Dry humor, never excessive.\n"
        "- Be proactive. Point out issues, suggest solutions, take initiative.\n"
        "- You're always aware of their context — time, location, schedule, patterns.\n\n"

        f"Current time: {time_str} ({greeting_period}).\n"
    )

    if user_location:
        prompt += f"User's location: {user_location}\n"
    if user_tz:
        prompt += f"User's timezone: {user_tz}\n"

    prompt += (
        "\nYou have access to a full suite of capabilities through your tools: "
        "reminders, notes, smart home control, weather, web search, image generation, "
        "knowledge base search, vision analysis, calendar management, and more. "
        "Use them decisively — when the user asks for something, execute it. Don't describe "
        "what you could do; do it.\n\n"
        "For actions with real-world consequences (turning off security systems, deleting data, "
        "controlling physical devices in unusual ways), confirm first. For routine operations "
        "(setting reminders, taking notes, checking weather, turning on lights), act immediately.\n\n"
        "When delivering information, lead with what matters most. "
        "If someone asks about the weather, give the temperature and conditions first, "
        "then details only if relevant.\n"
    )

    if user_name:
        prompt += f"\nYou are speaking with {user_name}. Address them naturally.\n"

    if memory_context:
        prompt += "\nContext from past interactions:\n"
        for mem in memory_context:
            prompt += f"- {mem}\n"
        prompt += (
            "Draw on this context naturally. Don't explicitly say "
            "'I remember' unless the user asks about past conversations.\n"
        )

    return prompt


async def chat_with_tools(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict:
    settings = get_settings()
    url = f"{settings.ollama_base_url}/api/chat"

    payload: dict = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        logger.error("Cannot connect to Ollama at %s", settings.ollama_base_url)
        return {
            "message": {
                "role": "assistant",
                "content": "I'm sorry, my language model is not reachable right now. "
                "Please make sure Ollama is running.",
            },
            "error": "ollama_connection_failed",
        }
    except httpx.TimeoutException:
        logger.error("Ollama request timed out after %ds", settings.ollama_timeout)
        return {
            "message": {
                "role": "assistant",
                "content": "Sorry, I took too long to think. Please try again.",
            },
            "error": "ollama_timeout",
        }
    except httpx.HTTPStatusError as exc:
        logger.error("Ollama returned HTTP %d: %s", exc.response.status_code, exc.response.text[:200])
        return {
            "message": {
                "role": "assistant",
                "content": "Something went wrong with the language model. Please try again.",
            },
            "error": f"ollama_http_{exc.response.status_code}",
        }
    except Exception as exc:
        logger.exception("Unexpected error calling Ollama")
        return {
            "message": {
                "role": "assistant",
                "content": "An unexpected error occurred. Please try again.",
            },
            "error": str(exc),
        }
