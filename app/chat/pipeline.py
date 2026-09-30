"""Shared chat pipeline: prompt → tool loop → reply.

All three entry points (POST /api/chat/text, POST /api/chat/audio, WS /ws/voice)
call run_chat_turn() once they have the user's message as text.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Optional

from app.config import get_settings
from app.llm import build_system_prompt
from app.llm_claude import get_claude_llm
from app.memory.store import get_memory_store
from app.skills.base import (
    SkillInfo,
    call_skill_handler,
    get_skill,
    serialize_tool_result,
    skills_for,
)

logger = logging.getLogger(__name__)

# Current authenticated user for this chat turn — used by skills that need per-user data.
_current_user_id: ContextVar[int | None] = ContextVar("_current_user_id", default=None)


def _skills_to_tool_list(skill_infos: list[SkillInfo]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            },
        }
        for s in skill_infos
    ]


@dataclass
class ChatTurnResult:
    reply: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    error: Optional[str] = None


def _summarize_tool_results(tool_results: list[dict]) -> str:
    """Build a minimal user-facing confirmation from raw tool results.

    Last-resort fallback when the LLM returns empty content after the tool loop.
    """
    parts: list[str] = []
    for tr in tool_results:
        tool_name = tr.get("tool", "")
        result = tr.get("result", {})
        if not isinstance(result, dict):
            continue
        if result.get("success"):
            if tool_name == "set_reminder":
                remind_at = result.get("remind_at", "")
                if remind_at:
                    try:
                        dt = datetime.fromisoformat(remind_at)
                        parts.append(
                            f"Reminder set for {dt.strftime('%a')} {dt.day} {dt.strftime('%b, %H:%M')}."
                        )
                    except ValueError:
                        parts.append("Reminder set.")
                else:
                    parts.append("Reminder set.")
            elif tool_name == "save_note":
                parts.append("Note saved.")
            elif tool_name == "create_calendar_event":
                parts.append("Calendar event created.")
            else:
                parts.append("Done.")
        elif tool_name == "list_reminders" and "reminders" in result:
            reminders = result["reminders"]
            if not reminders:
                parts.append("You have no upcoming reminders.")
            else:
                items = "; ".join(
                    f"'{r['text']}' at {r.get('remind_at', '?')}"
                    for r in reminders[:5]
                )
                parts.append(f"Upcoming reminders: {items}.")
        elif "error" in result:
            parts.append(f"Error: {result['error']}")
    return " ".join(parts) if parts else "Done."


async def run_chat_turn(
    user_text: str,
    history: list[dict],
    client_capabilities: bool = False,
    user_id: int | None = None,
    on_tool_call: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    on_tool_result: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    client_tool_futures: Optional[dict[str, asyncio.Future]] = None,
) -> ChatTurnResult:
    """Run the full prompt → tool loop → reply pipeline.

    Parameters
    ----------
    user_text:
        Transcribed or typed user message.
    history:
        Conversation history (read-only; the caller is responsible for trimming
        and updating after this call returns).
    client_capabilities:
        True  → include client_executed skills in the tool list (WS voice path).
        False → server-side tools only (HTTP paths).
    user_id:
        Authenticated user's DB id.  Set as a ContextVar so skills that need
        per-user data (e.g. get_device_context) can read it without being
        threaded through every skill call.
    on_tool_call:
        Optional async callback invoked just before each tool executes.
        Signature: (tool_name: str, args: dict) -> None.
    on_tool_result:
        Optional async callback invoked after each tool result is available.
        Signature: (tool_name: str, result: dict) -> None.
    client_tool_futures:
        Dict shared with the WS message loop.  When provided and a skill has
        client_executed=True, a Future is inserted here and awaited until the
        client sends a TOOL_RESULT_CLIENT frame.  When None, client_executed
        skills return a structured error instead.
    """
    _uid_token = _current_user_id.set(user_id)
    try:
        return await _run_chat_turn_inner(
            user_text, history, client_capabilities,
            on_tool_call, on_tool_result, client_tool_futures,
        )
    finally:
        _current_user_id.reset(_uid_token)


async def _run_chat_turn_inner(
    user_text: str,
    history: list[dict],
    client_capabilities: bool = False,
    on_tool_call: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    on_tool_result: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    client_tool_futures: Optional[dict[str, asyncio.Future]] = None,
) -> ChatTurnResult:
    memory_store = get_memory_store()
    memory_context = None
    if memory_store:
        results = await memory_store.search(user_text, top_k=5)
        if results:
            memory_context = results

    # Single source of truth: skills_for() drives both the tool list and the
    # capabilities section of the system prompt.
    all_skill_infos = skills_for(client_capabilities=client_capabilities)
    available_skill_infos = [s for s in all_skill_infos if s.available]
    tools = _skills_to_tool_list(available_skill_infos)

    system_prompt = build_system_prompt(
        memory_context,
        available_skills=available_skill_infos,
        memory_available=memory_store is not None and memory_store.available,
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-20:])
    messages.append({"role": "user", "content": user_text})

    claude = get_claude_llm()
    max_rounds = get_settings().max_tool_rounds

    all_tool_calls: list[dict] = []
    all_tool_results: list[dict] = []
    reply = ""
    tool_round = 0

    while True:
        is_final = tool_round >= max_rounds
        # Withhold tools on the final forced-text round so the model must reply with text.
        request_tools = None if is_final else (tools or None)

        response = await claude.chat(messages, request_tools)

        if response.get("error") == "llm_providers_failed":
            # Providers failed mid-loop.  If tools already ran, surface a summary
            # rather than an opaque error string.
            if all_tool_results:
                reply = _summarize_tool_results(all_tool_results)
                break
            return ChatTurnResult(
                reply=response["message"]["content"],
                error="llm_providers_failed",
            )

        assistant_message = response.get("message", {})
        tool_calls = assistant_message.get("tool_calls")

        if is_final or not tool_calls:
            # No tools were called, or we hit the round cap.  If the model STILL
            # returned tool calls on the final round, ignore them and use the summary.
            reply = assistant_message.get("content", "")
            if not reply and all_tool_results:
                reply = _summarize_tool_results(all_tool_results)
            break

        # ── Execute tool calls for this round ──────────────────────────────────

        # Append the assistant message (with tool_calls) to history so the next
        # round receives a well-formed OpenAI-format conversation.
        openai_tcs = []
        for tc in tool_calls:
            func = tc.get("function", {})
            args = func.get("arguments", {})
            entry: dict = {
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "arguments": json.dumps(args) if isinstance(args, dict) else (args or "{}"),
                },
            }
            if tc.get("id"):
                entry["id"] = tc["id"]
            openai_tcs.append(entry)
        messages.append({
            "role": "assistant",
            "content": assistant_message.get("content") or "",
            "tool_calls": openai_tcs,
        })

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            tool_args = func.get("arguments", {})
            tc_id = tc.get("id")
            all_tool_calls.append({"tool": tool_name, "args": tool_args})

            if on_tool_call is not None:
                await on_tool_call(tool_name, tool_args)

            skill = get_skill(tool_name)
            if skill is None:
                result: dict = {"error": f"Unknown skill: {tool_name}"}
            elif skill.client_executed:
                if client_tool_futures is not None:
                    future: asyncio.Future = asyncio.get_running_loop().create_future()
                    client_tool_futures[tool_name] = future
                    try:
                        result = await asyncio.wait_for(future, timeout=skill.timeout)
                    except asyncio.TimeoutError:
                        result = {"error": "Client did not respond in time"}
                    finally:
                        client_tool_futures.pop(tool_name, None)
                else:
                    result = {"error": f"Skill '{tool_name}' must be executed on the client device"}
            else:
                result = await call_skill_handler(skill, tool_name, tool_args)

            all_tool_results.append({"tool": tool_name, "result": result})

            if on_tool_result is not None:
                await on_tool_result(tool_name, result)

            tool_result_msg: dict = {
                "role": "tool",
                "content": serialize_tool_result(skill, tool_name, result),
            }
            if tc_id:
                tool_result_msg["tool_call_id"] = tc_id
            messages.append(tool_result_msg)

        tool_round += 1

    if memory_store:
        await memory_store.add_memory(user_text, {"role": "user", "type": "chat"})
        await memory_store.add_memory(reply, {"role": "assistant", "type": "chat"})

    return ChatTurnResult(
        reply=reply,
        tool_calls=all_tool_calls,
        tool_results=all_tool_results,
        error=None,
    )
