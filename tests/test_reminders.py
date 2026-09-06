"""
Tests for reminders API
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Reminder


@pytest.fixture
def sample_reminder_data():
    """Sample reminder data for testing."""
    return {
        "text": "Call mom",
        "remind_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    }


@pytest.fixture
def multiple_reminders_data():
    """Multiple reminders for testing."""
    base_time = datetime.now(timezone.utc)
    return [
        {
            "text": "Morning standup meeting",
            "remind_at": (base_time + timedelta(hours=1)).isoformat()
        },
        {
            "text": "Lunch with client",
            "remind_at": (base_time + timedelta(hours=4)).isoformat()
        },
        {
            "text": "Submit weekly report",
            "remind_at": (base_time + timedelta(days=1)).isoformat()
        },
        {
            "text": "Dentist appointment",
            "remind_at": (base_time + timedelta(days=3)).isoformat()
        }
    ]


def test_create_reminder(client: TestClient, sample_reminder_data):
    """Test creating a new reminder."""
    response = client.post("/reminders", json=sample_reminder_data)

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == sample_reminder_data["text"]
    assert "id" in data
    assert data["completed"] is False


def test_create_reminder_past_time(client: TestClient):
    """Test creating reminder with past timestamp."""
    past_reminder = {
        "text": "This is in the past",
        "remind_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    }

    response = client.post("/reminders", json=past_reminder)
    # Should still create it (may want to change this behavior)
    assert response.status_code == 200


def test_list_reminders(client: TestClient, multiple_reminders_data):
    """Test listing all reminders."""
    # Create multiple reminders
    for reminder_data in multiple_reminders_data:
        client.post("/reminders", json=reminder_data)

    response = client.get("/reminders")
    assert response.status_code == 200
    data = response.json()

    assert len(data) >= len(multiple_reminders_data)


def test_get_reminder_by_id(client: TestClient, sample_reminder_data):
    """Test getting a specific reminder by ID."""
    create_response = client.post("/reminders", json=sample_reminder_data)
    reminder_id = create_response.json()["id"]

    response = client.get(f"/reminders/{reminder_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == reminder_id
    assert data["text"] == sample_reminder_data["text"]


def test_get_nonexistent_reminder(client: TestClient):
    """Test getting a reminder that doesn't exist."""
    response = client.get("/reminders/999999")
    assert response.status_code == 404


def test_complete_reminder(client: TestClient, sample_reminder_data):
    """Test marking a reminder as completed."""
    create_response = client.post("/reminders", json=sample_reminder_data)
    reminder_id = create_response.json()["id"]

    response = client.patch(f"/reminders/{reminder_id}/complete")
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True


def test_delete_reminder(client: TestClient, sample_reminder_data):
    """Test deleting a reminder."""
    create_response = client.post("/reminders", json=sample_reminder_data)
    reminder_id = create_response.json()["id"]

    delete_response = client.delete(f"/reminders/{reminder_id}")
    assert delete_response.status_code == 200

    # Verify it's gone
    get_response = client.get(f"/reminders/{reminder_id}")
    assert get_response.status_code == 404


def test_update_reminder(client: TestClient, sample_reminder_data):
    """Test updating a reminder's text and time."""
    create_response = client.post("/reminders", json=sample_reminder_data)
    reminder_id = create_response.json()["id"]

    update_data = {
        "text": "Updated: Call mom and dad",
        "remind_at": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    }

    response = client.put(f"/reminders/{reminder_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == update_data["text"]


@pytest.mark.asyncio
async def test_reminder_database_persistence(test_db: AsyncSession, sample_reminder_data):
    """Test that reminders are properly persisted to database."""
    from sqlalchemy import select

    # Create reminder directly in DB
    reminder = Reminder(
        text=sample_reminder_data["text"],
        remind_at=datetime.fromisoformat(sample_reminder_data["remind_at"])
    )
    test_db.add(reminder)
    await test_db.commit()
    await test_db.refresh(reminder)

    # Query it back
    result = await test_db.execute(select(Reminder).where(Reminder.id == reminder.id))
    fetched_reminder = result.scalar_one()

    assert fetched_reminder.text == sample_reminder_data["text"]
    assert fetched_reminder.completed is False
