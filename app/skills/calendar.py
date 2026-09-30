from app.skills.base import Skill, register_skill

_ISO_OFFSET_NOTE = "ISO 8601 datetime with UTC offset, e.g. 2026-09-30T07:00:00+00:00"

register_skill(
    Skill(
        name="create_calendar_event",
        summary="Create a calendar event",
        description="Create a new event on the user's device calendar. Confirm details with the user before creating.",
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title",
                },
                "start_time": {
                    "type": "string",
                    "description": f"Event start time — {_ISO_OFFSET_NOTE}",
                },
                "end_time": {
                    "type": "string",
                    "description": f"Event end time — {_ISO_OFFSET_NOTE}",
                },
                "location": {
                    "type": "string",
                    "description": "Event location (optional)",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes for the event (optional)",
                },
            },
            "required": ["title", "start_time", "end_time"],
        },
        handler=None,
        client_executed=True,
        returns_external_content=True,
    )
)

register_skill(
    Skill(
        name="list_calendar_events",
        summary="List upcoming calendar events",
        description="List upcoming events from the user's device calendar.",
        parameters={
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": f"Start of date range — {_ISO_OFFSET_NOTE}",
                },
                "end_date": {
                    "type": "string",
                    "description": f"End of date range — {_ISO_OFFSET_NOTE}",
                },
            },
            "required": ["start_date", "end_date"],
        },
        handler=None,
        client_executed=True,
        returns_external_content=True,
    )
)
