from app.skills.base import Skill, register_skill


async def handle_daily_briefing() -> dict:
    from app.chat.pipeline import current_user_id
    from app.routes.briefing import generate_briefing

    return await generate_briefing(user_id=current_user_id())


register_skill(
    Skill(
        name="daily_briefing",
        summary="Today's briefing: weather and reminders",
        description=(
            "Generate a daily briefing with today's weather, upcoming reminders, "
            "and pending background tasks. Use when the user asks for a briefing, "
            "status update, or 'what's going on today'."
        ),
        parameters={"type": "object", "properties": {}},
        handler=handle_daily_briefing,
        timeout=30,
    )
)
