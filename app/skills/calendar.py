from app.skills.base import Skill, register_skill

register_skill(
    Skill(
        name="create_calendar_event",
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
                    "description": "Event start time in ISO 8601 format",
                },
                "end_time": {
                    "type": "string",
                    "description": "Event end time in ISO 8601 format",
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
    )
)

register_skill(
    Skill(
        name="list_calendar_events",
        description="List upcoming events from the user's device calendar.",
        parameters={
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start of date range (ISO 8601)",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of date range (ISO 8601)",
                },
            },
            "required": ["start_date", "end_date"],
        },
        handler=None,
        client_executed=True,
    )
)
