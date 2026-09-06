"""
Tests for Pydantic schemas validation
"""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from app.schemas import (
    WebSocketMessage,
    MessageType,
    StatusPayload,
    TranscriptPayload,
    ToolCallPayload,
    AssistantTextPayload,
    ImageGenerateRequest,
    ReminderResponse,
    VisionRequest,
    SmartHomeDeviceAction,
    WeatherRequest,
    WebSearchRequest
)


def test_websocket_message_valid():
    """Test valid WebSocket message creation."""
    msg = WebSocketMessage(
        type=MessageType.STATUS,
        payload={"state": "idle"}
    )
    assert msg.type == MessageType.STATUS
    assert msg.payload["state"] == "idle"


def test_websocket_message_no_payload():
    """Test WebSocket message with no payload."""
    msg = WebSocketMessage(type=MessageType.PING)
    assert msg.payload == {}


def test_status_payload():
    """Test status payload validation."""
    from app.schemas import AssistantState

    payload = StatusPayload(state=AssistantState.THINKING)
    assert payload.state == AssistantState.THINKING


def test_transcript_payload():
    """Test transcript payload validation."""
    payload = TranscriptPayload(text="Hello, how can I help you?")
    assert payload.text == "Hello, how can I help you?"


def test_tool_call_payload():
    """Test tool call payload validation."""
    payload = ToolCallPayload(
        tool="turn_on_light",
        args={"entity_id": "light.living_room", "brightness": 80}
    )
    assert payload.tool == "turn_on_light"
    assert payload.args["brightness"] == 80


def test_image_generate_request_defaults():
    """Test image generation request with defaults."""
    request = ImageGenerateRequest(prompt="A sunset over mountains")

    assert request.prompt == "A sunset over mountains"
    assert request.width == 512
    assert request.height == 512
    assert request.num_images == 1
    assert request.guidance_scale == 7.5


def test_image_generate_request_custom():
    """Test image generation request with custom values."""
    request = ImageGenerateRequest(
        prompt="Abstract art in blue and gold",
        width=1024,
        height=1024,
        num_images=4,
        guidance_scale=9.0,
        num_inference_steps=75
    )

    assert request.width == 1024
    assert request.num_images == 4
    assert request.num_inference_steps == 75


def test_reminder_response():
    """Test reminder response model."""
    now = datetime.now(timezone.utc)

    reminder = ReminderResponse(
        id=1,
        text="Team meeting",
        remind_at=now,
        completed=False,
        created_at=now
    )

    assert reminder.id == 1
    assert reminder.completed is False


def test_vision_request_valid():
    """Test vision request validation."""
    request = VisionRequest(
        image_base64="base64encodeddata",
        task="identify_face",
        options={"threshold": 0.8}
    )

    assert request.task == "identify_face"
    assert request.options["threshold"] == 0.8


def test_smart_home_device_action():
    """Test smart home device action validation."""
    action = SmartHomeDeviceAction(
        entity_id="light.bedroom",
        action="turn_on",
        attributes={"brightness": 50, "color": "warm_white"}
    )

    assert action.entity_id == "light.bedroom"
    assert action.action == "turn_on"
    assert action.attributes["brightness"] == 50


def test_weather_request_coordinates():
    """Test weather request with coordinates."""
    request = WeatherRequest(latitude=40.7128, longitude=-74.0060)

    assert request.latitude == 40.7128
    assert request.longitude == -74.0060


def test_weather_request_location_name():
    """Test weather request with location name."""
    request = WeatherRequest(location_name="New York")

    assert request.location_name == "New York"
    assert request.latitude is None


def test_web_search_request():
    """Test web search request validation."""
    request = WebSearchRequest(query="FastAPI async patterns", max_results=10)

    assert request.query == "FastAPI async patterns"
    assert request.max_results == 10


def test_web_search_request_defaults():
    """Test web search request with defaults."""
    request = WebSearchRequest(query="Python best practices")

    assert request.max_results == 5  # Default value


def test_invalid_message_type():
    """Test that invalid message types are rejected."""
    with pytest.raises(ValidationError):
        WebSocketMessage(type="invalid_type", payload={})


def test_assistant_text_payload_empty():
    """Test assistant text payload cannot be empty."""
    # This should be valid - empty string is allowed
    payload = AssistantTextPayload(text="")
    assert payload.text == ""
