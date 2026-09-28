"""
Tests for notes API
"""
import pytest
from fastapi.testclient import TestClient

BASE = "/api/notes"


@pytest.fixture
def sample_note_data():
    """Sample note data for testing."""
    return {
        "content": "Remember to review the PR for the new authentication feature",
        "tags": ["work", "code-review", "urgent"]
    }


@pytest.fixture
def multiple_notes_data():
    """Multiple notes for testing."""
    return [
        {
            "content": "Grocery list: milk, eggs, bread, coffee",
            "tags": ["personal", "shopping"]
        },
        {
            "content": "Meeting notes: Q4 planning session. Focus on user growth and retention.",
            "tags": ["work", "meetings", "planning"]
        },
        {
            "content": "Book recommendations: Atomic Habits, Deep Work, The Phoenix Project",
            "tags": ["personal", "books", "reading"]
        },
        {
            "content": "Bug report: Login page not responsive on mobile Safari",
            "tags": ["work", "bugs", "mobile"]
        }
    ]


def test_create_note(client: TestClient, sample_note_data):
    """Test creating a new note."""
    response = client.post(f"{BASE}/", json=sample_note_data)

    assert response.status_code == 201
    data = response.json()
    assert data["content"] == sample_note_data["content"]
    assert data["tags"] == sample_note_data["tags"]
    assert "id" in data
    assert "created_at" in data


def test_create_note_without_tags(client: TestClient):
    """Test creating a note without tags."""
    note_data = {"content": "Simple note without tags"}

    response = client.post(f"{BASE}/", json=note_data)
    assert response.status_code == 201
    data = response.json()
    assert data["tags"] == []


def test_list_notes(client: TestClient, multiple_notes_data):
    """Test listing all notes."""
    for note_data in multiple_notes_data:
        client.post(f"{BASE}/", json=note_data)

    response = client.get(f"{BASE}/")
    assert response.status_code == 200
    data = response.json()

    assert len(data) >= len(multiple_notes_data)


def test_create_and_find_note_by_content(client: TestClient, sample_note_data):
    """Test that a created note appears in the list."""
    client.post(f"{BASE}/", json=sample_note_data)

    response = client.get(f"{BASE}/")
    assert response.status_code == 200
    data = response.json()
    contents = [n["content"] for n in data]
    assert sample_note_data["content"] in contents


def test_update_note(client: TestClient, sample_note_data):
    """Test updating a note's content and tags."""
    create_response = client.post(f"{BASE}/", json=sample_note_data)
    note_id = create_response.json()["id"]

    update_data = {
        "content": "Updated: PR review completed successfully",
        "tags": ["work", "done"]
    }

    response = client.patch(f"{BASE}/{note_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == update_data["content"]
    assert data["tags"] == update_data["tags"]
    assert "updated_at" in data


def test_delete_note(client: TestClient, sample_note_data):
    """Test deleting a note."""
    create_response = client.post(f"{BASE}/", json=sample_note_data)
    note_id = create_response.json()["id"]

    delete_response = client.delete(f"{BASE}/{note_id}")
    assert delete_response.status_code == 204


def test_search_notes(client: TestClient, multiple_notes_data):
    """Test searching notes by content."""
    for note_data in multiple_notes_data:
        client.post(f"{BASE}/", json=note_data)

    response = client.get(f"{BASE}/?search=meeting")
    assert response.status_code == 200
    data = response.json()

    for note in data:
        assert "meeting" in note["content"].lower()
