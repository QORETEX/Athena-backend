from app.skills.base import Skill, register_skill

register_skill(
    Skill(
        name="device_control",
        description="Control device settings such as volume, brightness, flashlight, do-not-disturb mode, or set alarms. Executed on the user's phone.",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "The action to perform (e.g., 'set_volume', 'toggle_flashlight', 'set_alarm', 'set_brightness', 'toggle_dnd')",
                },
                "setting": {
                    "type": "string",
                    "description": "The specific setting to modify",
                },
                "value": {
                    "type": "string",
                    "description": "The value to set (e.g., '50' for 50% volume, 'on'/'off' for toggles, '07:30' for alarm time)",
                },
            },
            "required": ["action"],
        },
        handler=None,
        client_executed=True,
    )
)
