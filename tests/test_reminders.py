"""
Tests for reminders API
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Reminder

BASE = "/api/reminders"


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


def test_create_reminder(authenticated_client: TestClient, sample_reminder_data):
    """Test creating a new reminder."""
    response = authenticated_client.post(f"{BASE}", json=sample_reminder_data)

    assert response.status_code == 201
    data = response.json()
    assert data["text"] == sample_reminder_data["text"]
    assert "id" in data
    assert data["completed"] is False


def test_create_reminder_past_time(authenticated_client: TestClient):
    """Test creating reminder with past timestamp."""
    past_reminder = {
        "text": "This is in the past",
        "remind_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    }

    response = authenticated_client.post(f"{BASE}", json=past_reminder)
    assert response.status_code == 201


def test_list_reminders(authenticated_client: TestClient, multiple_reminders_data):
    """Test listing all reminders."""
    for reminder_data in multiple_reminders_data:
        authenticated_client.post(f"{BASE}", json=reminder_data)

    response = authenticated_client.get(f"{BASE}")
    assert response.status_code == 200
    data = response.json()

    assert len(data) >= len(multiple_reminders_data)


def test_create_and_find_reminder(authenticated_client: TestClient, sample_reminder_data):
    """Test that a created reminder appears in the list."""
    authenticated_client.post(f"{BASE}", json=sample_reminder_data)

    response = authenticated_client.get(f"{BASE}")
    assert response.status_code == 200
    data = response.json()
    texts = [r["text"] for r in data]
    assert sample_reminder_data["text"] in texts


def test_patch_nonexistent_reminder(authenticated_client: TestClient):
    """Test patching a reminder that doesn't exist returns 404."""
    response = authenticated_client.patch(f"{BASE}/999999", json={"completed": True})
    assert response.status_code == 404


def test_complete_reminder(authenticated_client: TestClient, sample_reminder_data):
    """Test marking a reminder as completed via PATCH."""
    create_response = authenticated_client.post(f"{BASE}", json=sample_reminder_data)
    reminder_id = create_response.json()["id"]

    response = authenticated_client.patch(f"{BASE}/{reminder_id}", json={"completed": True})
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True


def test_delete_reminder(authenticated_client: TestClient, sample_reminder_data):
    """Test deleting a reminder."""
    create_response = authenticated_client.post(f"{BASE}", json=sample_reminder_data)
    reminder_id = create_response.json()["id"]

    delete_response = authenticated_client.delete(f"{BASE}/{reminder_id}")
    assert delete_response.status_code == 204


def test_update_reminder(authenticated_client: TestClient, sample_reminder_data):
    """Test updating a reminder's text and time via PATCH."""
    create_response = authenticated_client.post(f"{BASE}", json=sample_reminder_data)
    reminder_id = create_response.json()["id"]

    update_data = {
        "text": "Updated: Call mom and dad",
        "remind_at": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    }

    response = authenticated_client.patch(f"{BASE}/{reminder_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == update_data["text"]


@pytest.mark.asyncio
async def test_reminder_database_persistence(test_db: AsyncSession, sample_reminder_data):
    """Test that reminders are properly persisted to database."""
    from sqlalchemy import select

    reminder = Reminder(
        text=sample_reminder_data["text"],
        remind_at=datetime.fromisoformat(sample_reminder_data["remind_at"])
    )
    test_db.add(reminder)
    await test_db.commit()
    await test_db.refresh(reminder)

    result = await test_db.execute(select(Reminder).where(Reminder.id == reminder.id))
    fetched_reminder = result.scalar_one()

    assert fetched_reminder.text == sample_reminder_data["text"]
    assert fetched_reminder.completed is False
