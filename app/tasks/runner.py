from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

logger = logging.getLogger(__name__)

_task_queue: asyncio.Queue = asyncio.Queue()
_worker_task: Optional[asyncio.Task] = None


async def start_task_worker():
    global _worker_task
    _worker_task = asyncio.create_task(_worker_loop())
    await _reload_pending_tasks()
    logger.info("Background task worker started")


async def stop_task_worker():
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
    logger.info("Background task worker stopped")


async def submit_task(task_type: str, prompt: str) -> int:
    from app.db import BackgroundTask, async_session

    async with async_session() as session:
        task = BackgroundTask(
            task_type=task_type,
            prompt=prompt,
            status="pending",
        )
        session.add(task)
        await session.flush()
        await session.refresh(task)
        task_id = task.id
        await session.commit()

    await _task_queue.put(task_id)
    logger.info("Submitted background task %d (type=%s)", task_id, task_type)
    return task_id


async def _reload_pending_tasks():
    from app.db import BackgroundTask, async_session

    async with async_session() as session:
        stmt = select(BackgroundTask.id).where(
            BackgroundTask.status.in_(["pending", "running"])
        )
        result = await session.execute(stmt)
        task_ids = [row[0] for row in result.all()]

    for tid in task_ids:
        await _task_queue.put(tid)

    if task_ids:
        logger.info("Reloaded %d pending/running tasks from DB", len(task_ids))


async def _worker_loop():
    while True:
        task_id = await _task_queue.get()
        try:
            await _process_task(task_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background task %d failed unexpectedly", task_id)
            await _mark_failed(task_id, "Internal worker error")
        finally:
            _task_queue.task_done()


async def _process_task(task_id: int):
    from app.db import BackgroundTask, async_session

    async with async_session() as session:
        task = await session.get(BackgroundTask, task_id)
        if not task:
            logger.warning("Task %d not found in DB, skipping", task_id)
            return
        if task.status not in ("pending", "running"):
            logger.info("Task %d already %s, skipping", task_id, task.status)
            return

        task.status = "running"
        task_type = task.task_type
        prompt = task.prompt
        await session.commit()

    logger.info("Processing task %d (type=%s)", task_id, task_type)

    try:
        if task_type == "research":
            result = await _do_research(prompt)
        elif task_type == "analysis":
            result = await _do_analysis(prompt)
        elif task_type == "summary":
            result = await _do_summary(prompt)
        else:
            result = await _do_research(prompt)

        async with async_session() as session:
            task = await session.get(BackgroundTask, task_id)
            task.status = "completed"
            task.result = json.dumps(result) if isinstance(result, dict) else str(result)
            task.completed_at = datetime.now(timezone.utc)
            await session.commit()

        logger.info("Task %d completed", task_id)
        await _broadcast_completion(task_id, task_type, prompt)

    except Exception as e:
        logger.exception("Task %d processing error", task_id)
        await _mark_failed(task_id, str(e))


async def _do_research(prompt: str) -> dict:
    from app.llm import chat_with_tools, build_system_prompt

    query_messages = [
        {"role": "system", "content": (
            "You are a research assistant. Given a research topic, generate 2-3 focused "
            "web search queries that would help gather comprehensive information. "
            "Return ONLY a JSON array of query strings, nothing else."
        )},
        {"role": "user", "content": f"Research topic: {prompt}"},
    ]

    query_resp = await chat_with_tools(query_messages)
    query_text = query_resp.get("message", {}).get("content", "")

    queries = [prompt]
    try:
        parsed = json.loads(query_text)
        if isinstance(parsed, list):
            queries = [str(q) for q in parsed[:3]]
    except (json.JSONDecodeError, TypeError):
        queries = [prompt]

    all_results = []
    for query in queries:
        try:
            from app.skills.web_search import handle_web_search
            search_result = await handle_web_search(query=query)
            results = search_result.get("results", [])
            all_results.extend(results)
        except Exception as e:
            logger.warning("Search query '%s' failed: %s", query, e)

    search_context = ""
    for i, r in enumerate(all_results[:10], 1):
        search_context += f"{i}. {r.get('title', 'No title')}\n"
        search_context += f"   {r.get('snippet', '')}\n\n"

    if not search_context:
        search_context = "(No search results available — SearXNG may not be running)"

    synthesis_messages = [
        {"role": "system", "content": (
            "You are a research analyst. Synthesize the following search results into a "
            "comprehensive, well-organized report. Include key findings, relevant details, "
            "and note any gaps in the information. Be thorough but concise."
        )},
        {"role": "user", "content": (
            f"Research topic: {prompt}\n\n"
            f"Search results:\n{search_context}\n\n"
            "Please synthesize these into a comprehensive report."
        )},
    ]

    synthesis_resp = await chat_with_tools(synthesis_messages)
    report = synthesis_resp.get("message", {}).get("content", "Research completed but no synthesis available.")

    return {
        "report": report,
        "queries_used": queries,
        "sources_found": len(all_results),
    }


async def _do_analysis(prompt: str) -> dict:
    from app.llm import chat_with_tools

    messages = [
        {"role": "system", "content": (
            "You are an expert analyst. Analyze the following thoroughly. "
            "Provide structured insights, identify patterns, and offer actionable conclusions."
        )},
        {"role": "user", "content": prompt},
    ]

    resp = await chat_with_tools(messages)
    analysis = resp.get("message", {}).get("content", "Analysis completed but no output available.")

    return {"analysis": analysis}


async def _do_summary(prompt: str) -> dict:
    from app.llm import chat_with_tools

    messages = [
        {"role": "system", "content": (
            "You are a summarization expert. Provide a clear, concise summary of the following. "
            "Capture the key points and main ideas without losing important details."
        )},
        {"role": "user", "content": prompt},
    ]

    resp = await chat_with_tools(messages)
    summary = resp.get("message", {}).get("content", "Summary completed but no output available.")

    return {"summary": summary}


async def _mark_failed(task_id: int, error_msg: str):
    from app.db import BackgroundTask, async_session

    try:
        async with async_session() as session:
            task = await session.get(BackgroundTask, task_id)
            if task:
                task.status = "failed"
                task.error = error_msg
                task.completed_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception:
        logger.exception("Failed to mark task %d as failed", task_id)

    await _broadcast_completion(task_id, "unknown", "", failed=True)


async def _broadcast_completion(
    task_id: int, task_type: str, prompt: str, failed: bool = False
):
    try:
        from app.websocket.events import broadcast_event
        from app.schemas import MessageType

        await broadcast_event(
            MessageType.REMINDER_DUE,
            {
                "event_type": "task_completed" if not failed else "task_failed",
                "task_id": task_id,
                "task_type": task_type,
                "prompt": prompt[:100],
                "status": "failed" if failed else "completed",
            },
        )
    except Exception:
        logger.exception("Failed to broadcast task %d completion", task_id)
