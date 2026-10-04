"""
Tests for database models and operations
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import (
    Reminder,
    Note,
    ConversationLog,
    User,
    UserPreference,
    SmartHomeDevice,
    Routine,
    BackgroundTask,
    NotificationLog
)


@pytest.mark.asyncio
async def test_create_reminder(test_db: AsyncSession):
    """Test creating a reminder in database."""
    user = User(email="db_reminder@test.com", name="DB User")
    test_db.add(user)
    await test_db.flush()

    reminder = Reminder(
        user_id=user.id,
        text="Test reminder",
        remind_at=datetime.now(timezone.utc),
    )

    test_db.add(reminder)
    await test_db.commit()
    await test_db.refresh(reminder)

    assert reminder.id is not None
    assert reminder.completed is False


@pytest.mark.asyncio
async def test_create_note(test_db: AsyncSession):
    """Test creating a note in database."""
    user = User(email="db_note@test.com", name="Note User")
    test_db.add(user)
    await test_db.flush()

    note = Note(
        user_id=user.id,
        content="Test note content",
        tags='["test", "database"]',
    )

    test_db.add(note)
    await test_db.commit()
    await test_db.refresh(note)

    assert note.id is not None
    assert note.created_at is not None


@pytest.mark.asyncio
async def test_conversation_log(test_db: AsyncSession):
    """Test logging conversation messages."""
    user = User(email="db_conv@test.com", name="Conv User")
    test_db.add(user)
    await test_db.flush()

    messages = [
        ConversationLog(user_id=user.id, role="user", content="Hello Athena"),
        ConversationLog(user_id=user.id, role="assistant", content="Hello! How can I help you?"),
        ConversationLog(user_id=user.id, role="user", content="What's the weather?"),
        ConversationLog(
            user_id=user.id,
            role="assistant",
            content="Let me check the weather for you.",
            tool_calls='[{"tool": "get_weather", "args": {}}]',
        ),
    ]

    for msg in messages:
        test_db.add(msg)

    await test_db.commit()

    # Query conversation history
    result = await test_db.execute(select(ConversationLog).order_by(ConversationLog.id))
    logs = result.scalars().all()

    assert len(logs) == 4
    assert logs[0].role == "user"
    assert logs[3].tool_calls is not None


@pytest.mark.asyncio
async def test_user_creation(test_db: AsyncSession):
    """Test creating a user."""
    user = User(
        email="test@example.com",
        name="Test User",
        avatar_url="https://example.com/avatar.jpg",
        is_active=True,
    )

    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_user_preferences(test_db: AsyncSession):
    """Test storing user preferences."""
    user = User(email="db_prefs@test.com", name="Prefs User")
    test_db.add(user)
    await test_db.flush()

    prefs = [
        UserPreference(user_id=user.id, key="theme", value="dark"),
        UserPreference(user_id=user.id, key="voice_speed", value="1.0"),
        UserPreference(user_id=user.id, key="tts_enabled", value="true"),
    ]

    for pref in prefs:
        test_db.add(pref)

    await test_db.commit()

    result = await test_db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    stored_prefs = result.scalars().all()

    assert len(stored_prefs) == 3


@pytest.mark.asyncio
async def test_smart_home_device(test_db: AsyncSession):
    """Test storing smart home device info."""
    user = User(email="db_smarthome@test.com", name="SmartHome User")
    test_db.add(user)
    await test_db.flush()

    device = SmartHomeDevice(
        user_id=user.id,
        entity_id="light.living_room",
        name="Living Room Light",
        device_type="light",
        room="Living Room",
        icon="mdi:lightbulb",
        is_favorite=True,
    )

    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    assert device.id is not None
    assert device.is_favorite is True


@pytest.mark.asyncio
async def test_routine_creation(test_db: AsyncSession):
    """Test creating a routine."""
    import json

    user = User(email="db_routine@test.com", name="Routine User")
    test_db.add(user)
    await test_db.flush()

    routine = Routine(
        user_id=user.id,
        name="Morning Routine",
        description="Turn on lights and play news",
        trigger_type="time",
        trigger_config=json.dumps({"time": "07:00", "days": ["mon", "tue", "wed", "thu", "fri"]}),
        actions=json.dumps([
            {"action": "turn_on", "entity_id": "light.bedroom"},
            {"action": "speak", "text": "Good morning! Here's your briefing."},
        ]),
        enabled=True,
    )

    test_db.add(routine)
    await test_db.commit()
    await test_db.refresh(routine)

    assert routine.id is not None
    assert routine.enabled is True


@pytest.mark.asyncio
async def test_background_task(test_db: AsyncSession):
    """Test background task tracking."""
    user = User(email="db_task@test.com", name="Task User")
    test_db.add(user)
    await test_db.flush()

    task = BackgroundTask(
        user_id=user.id,
        task_type="research",
        prompt="Research the latest trends in AI",
        status="pending",
    )

    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    # Update task status
    task.status = "completed"
    task.result = "Here are the latest AI trends..."
    task.completed_at = datetime.now(timezone.utc)

    await test_db.commit()

    # Verify update
    result = await test_db.execute(select(BackgroundTask).where(BackgroundTask.id == task.id))
    updated_task = result.scalar_one()

    assert updated_task.status == "completed"
    assert updated_task.result is not None


@pytest.mark.asyncio
async def test_notification_log(test_db: AsyncSession):
    """Test notification logging."""
    user = User(email="db_notif@test.com", name="Notif User")
    test_db.add(user)
    await test_db.flush()

    notification = NotificationLog(
        user_id=user.id,
        event_type="reminder_due",
        priority="high",
        title="Reminder: Team Meeting",
        body="Your team meeting starts in 5 minutes",
        data='{"reminder_id": 123}',
        read=False,
    )

    test_db.add(notification)
    await test_db.commit()
    await test_db.refresh(notification)

    assert notification.id is not None
    assert notification.read is False

    notification.read = True
    await test_db.commit()


@pytest.mark.asyncio
async def test_query_unread_notifications(test_db: AsyncSession):
    """Test querying unread notifications."""
    user = User(email="db_unread@test.com", name="Unread User")
    test_db.add(user)
    await test_db.flush()

    notifications = [
        NotificationLog(user_id=user.id, event_type="info", priority="normal", title="System Update", read=True),
        NotificationLog(user_id=user.id, event_type="reminder_due", priority="high", title="Important Reminder", read=False),
        NotificationLog(user_id=user.id, event_type="alert", priority="high", title="Security Alert", read=False),
    ]

    for notif in notifications:
        test_db.add(notif)

    await test_db.commit()

    result = await test_db.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == user.id,
            NotificationLog.read == False,
        )
    )
    unread = result.scalars().all()

    assert len(unread) == 2
