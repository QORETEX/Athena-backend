"""
Dummy data generators for testing Athena backend
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import random


class DummyDataGenerator:
    """Generate realistic dummy data for testing."""

    @staticmethod
    def reminders(count: int = 5) -> List[Dict[str, Any]]:
        """Generate dummy reminder data."""
        base_time = datetime.now(timezone.utc)
        reminder_texts = [
            "Call dentist to schedule appointment",
            "Submit quarterly tax returns",
            "Pick up dry cleaning",
            "Team standup meeting",
            "Review pull requests",
            "Water the plants",
            "Prepare presentation slides",
            "Buy groceries: milk, bread, eggs",
            "Schedule car maintenance",
            "Send birthday card to mom"
        ]

        reminders = []
        for i in range(min(count, len(reminder_texts))):
            reminders.append({
                "text": reminder_texts[i],
                "remind_at": (base_time + timedelta(hours=random.randint(1, 72))).isoformat()
            })

        return reminders

    @staticmethod
    def notes(count: int = 5) -> List[Dict[str, Any]]:
        """Generate dummy note data."""
        notes_data = [
            {
                "content": "Project ideas: AI-powered task manager, voice-controlled home automation, smart recipe assistant",
                "tags": ["ideas", "projects", "ai"]
            },
            {
                "content": "Book notes: The Pragmatic Programmer - emphasis on automation, code reusability, and thinking critically",
                "tags": ["books", "programming", "notes"]
            },
            {
                "content": "Meeting notes: Q4 objectives - increase user engagement by 20%, reduce latency by 30%, ship voice features",
                "tags": ["work", "meetings", "goals"]
            },
            {
                "content": "Shopping list: coffee beans, almond milk, protein powder, fresh vegetables, olive oil",
                "tags": ["personal", "shopping", "groceries"]
            },
            {
                "content": "Debug notes: Issue with WebSocket reconnection. Need to implement exponential backoff and heartbeat",
                "tags": ["work", "bugs", "websocket"]
            },
            {
                "content": "Travel plans: Tokyo trip - visit TeamLab Borderless, try authentic ramen, explore Akihabara",
                "tags": ["personal", "travel", "japan"]
            }
        ]

        return notes_data[:count]

    @staticmethod
    def conversation_history() -> List[Dict[str, str]]:
        """Generate dummy conversation history."""
        return [
            {"role": "user", "content": "Hey Athena, what's the weather like today?"},
            {"role": "assistant", "content": "Let me check the weather for you."},
            {"role": "assistant", "content": "Currently it's 72°F and sunny with clear skies. Perfect day to go outside!"},
            {"role": "user", "content": "Great! Can you remind me to water the plants at 5 PM?"},
            {"role": "assistant", "content": "I've set a reminder for 5:00 PM to water the plants."},
            {"role": "user", "content": "What do I have scheduled for tomorrow?"},
            {"role": "assistant", "content": "Tomorrow you have: 9 AM - Team standup, 2 PM - Client presentation, 4 PM - Code review session"},
            {"role": "user", "content": "Add a note about the client feedback"},
            {"role": "assistant", "content": "I've created a note. What feedback did you receive?"},
            {"role": "user", "content": "They loved the new UI but want faster load times"},
            {"role": "assistant", "content": "Note saved: Client feedback - loved new UI, want faster load times. Tagged as 'work' and 'feedback'."}
        ]

    @staticmethod
    def smart_home_devices() -> List[Dict[str, Any]]:
        """Generate dummy smart home device data."""
        return [
            {
                "entity_id": "light.living_room",
                "name": "Living Room Light",
                "device_type": "light",
                "room": "Living Room",
                "icon": "mdi:lightbulb",
                "is_favorite": True
            },
            {
                "entity_id": "light.bedroom",
                "name": "Bedroom Light",
                "device_type": "light",
                "room": "Bedroom",
                "icon": "mdi:lightbulb"
            },
            {
                "entity_id": "switch.coffee_maker",
                "name": "Coffee Maker",
                "device_type": "switch",
                "room": "Kitchen",
                "icon": "mdi:coffee-maker",
                "is_favorite": True
            },
            {
                "entity_id": "climate.thermostat",
                "name": "Thermostat",
                "device_type": "climate",
                "room": "Living Room",
                "icon": "mdi:thermostat"
            },
            {
                "entity_id": "cover.garage_door",
                "name": "Garage Door",
                "device_type": "cover",
                "room": "Garage",
                "icon": "mdi:garage"
            }
        ]

    @staticmethod
    def routines() -> List[Dict[str, Any]]:
        """Generate dummy routine data."""
        return [
            {
                "name": "Morning Routine",
                "description": "Wake up automation - lights, coffee, briefing",
                "trigger_type": "time",
                "trigger_config": {"time": "07:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
                "actions": [
                    {"action": "turn_on", "entity_id": "light.bedroom", "brightness": 30},
                    {"action": "turn_on", "entity_id": "switch.coffee_maker"},
                    {"action": "speak", "text": "Good morning! Here's your daily briefing."}
                ],
                "enabled": True
            },
            {
                "name": "Leaving Home",
                "description": "Turn off all lights and lock doors",
                "trigger_type": "manual",
                "trigger_config": {},
                "actions": [
                    {"action": "turn_off", "entity_id": "group.all_lights"},
                    {"action": "lock", "entity_id": "lock.front_door"},
                    {"action": "speak", "text": "All set! Have a great day."}
                ],
                "enabled": True
            },
            {
                "name": "Movie Night",
                "description": "Dim lights and close blinds",
                "trigger_type": "manual",
                "trigger_config": {},
                "actions": [
                    {"action": "set_brightness", "entity_id": "light.living_room", "brightness": 10},
                    {"action": "close", "entity_id": "cover.living_room_blinds"}
                ],
                "enabled": True
            }
        ]

    @staticmethod
    def user_preferences() -> Dict[str, str]:
        """Generate dummy user preferences."""
        return {
            "theme": "dark",
            "voice_speed": "1.0",
            "tts_enabled": "true",
            "wake_word": "athena",
            "language": "en-US",
            "temperature_unit": "fahrenheit",
            "time_format": "12h",
            "notifications_enabled": "true",
            "proactive_mode": "true"
        }

    @staticmethod
    def notifications() -> List[Dict[str, Any]]:
        """Generate dummy notification data."""
        return [
            {
                "event_type": "reminder_due",
                "priority": "high",
                "title": "Reminder: Team Meeting",
                "body": "Your team meeting starts in 5 minutes",
                "data": {"reminder_id": 1}
            },
            {
                "event_type": "weather_alert",
                "priority": "normal",
                "title": "Weather Update",
                "body": "Rain expected this afternoon. Don't forget your umbrella!",
                "data": {}
            },
            {
                "event_type": "smart_home",
                "priority": "high",
                "title": "Front Door Unlocked",
                "body": "Your front door was unlocked at 10:30 PM",
                "data": {"entity_id": "lock.front_door"}
            },
            {
                "event_type": "system",
                "priority": "low",
                "title": "System Update Available",
                "body": "Athena v2.1.0 is ready to install",
                "data": {"version": "2.1.0"}
            }
        ]

    @staticmethod
    def background_tasks() -> List[Dict[str, Any]]:
        """Generate dummy background task data."""
        return [
            {
                "task_type": "research",
                "prompt": "Research the latest developments in voice AI technology",
                "status": "completed",
                "result": "Voice AI has advanced significantly with models like Whisper v3 and ElevenLabs..."
            },
            {
                "task_type": "summary",
                "prompt": "Summarize today's conversations",
                "status": "pending"
            },
            {
                "task_type": "analysis",
                "prompt": "Analyze my productivity patterns from the last week",
                "status": "running"
            }
        ]

    @staticmethod
    def image_generation_requests() -> List[Dict[str, Any]]:
        """Generate dummy image generation requests."""
        return [
            {
                "prompt": "A serene mountain landscape at sunset with a lake reflection",
                "width": 512,
                "height": 512,
                "num_images": 1
            },
            {
                "prompt": "Abstract art with geometric shapes in blue and gold",
                "width": 1024,
                "height": 1024,
                "num_images": 2,
                "guidance_scale": 9.0
            },
            {
                "prompt": "A futuristic city with flying cars and neon lights",
                "width": 768,
                "height": 512,
                "num_images": 1
            }
        ]

    @staticmethod
    def web_search_queries() -> List[str]:
        """Generate dummy web search queries."""
        return [
            "FastAPI best practices 2026",
            "Python async programming patterns",
            "Home Assistant automation ideas",
            "How to optimize SQLite performance",
            "Latest developments in local LLMs"
        ]


# Convenience functions
def get_dummy_reminders(count: int = 5):
    """Get dummy reminders."""
    return DummyDataGenerator.reminders(count)


def get_dummy_notes(count: int = 5):
    """Get dummy notes."""
    return DummyDataGenerator.notes(count)


def get_dummy_conversation():
    """Get dummy conversation history."""
    return DummyDataGenerator.conversation_history()


def get_all_dummy_data():
    """Get all types of dummy data."""
    return {
        "reminders": DummyDataGenerator.reminders(),
        "notes": DummyDataGenerator.notes(),
        "conversation": DummyDataGenerator.conversation_history(),
        "devices": DummyDataGenerator.smart_home_devices(),
        "routines": DummyDataGenerator.routines(),
        "preferences": DummyDataGenerator.user_preferences(),
        "notifications": DummyDataGenerator.notifications(),
        "background_tasks": DummyDataGenerator.background_tasks(),
        "image_requests": DummyDataGenerator.image_generation_requests(),
        "search_queries": DummyDataGenerator.web_search_queries()
    }
