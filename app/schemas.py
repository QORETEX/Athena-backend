"""
THE CONTRACT - All message shapes between backend and frontend
This file must be kept in sync between backend and mobile app
"""

from enum import Enum
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field
from datetime import datetime


class AssistantState(str, Enum):
    """Valid states for the assistant state machine"""
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"


class MessageType(str, Enum):
    """WebSocket message types"""
    # Client → Server
    WAKE_DETECTED = "wake_detected"
    AUDIO_START = "audio_start"
    AUDIO_END = "audio_end"
    INTERRUPT = "interrupt"
    GESTURE_DETECTED = "gesture_detected"
    TOOL_RESULT_CLIENT = "tool_result_client"
    PING = "ping"

    # Server → Client
    STATUS = "status"
    PARTIAL_TRANSCRIPT = "partial_transcript"
    FINAL_TRANSCRIPT = "final_transcript"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ASSISTANT_TEXT = "assistant_text"
    TTS_CHUNK = "tts_chunk"
    TTS_END = "tts_end"
    REMINDER_DUE = "reminder_due"
    ERROR = "error"
    PONG = "pong"


# Base message models
class WebSocketMessage(BaseModel):
    """Base model for all WebSocket messages"""
    type: MessageType
    payload: Optional[Dict[str, Any]] = {}


# Client → Server message payloads
class GesturePayload(BaseModel):
    gesture: str


class ToolResultClientPayload(BaseModel):
    tool: str
    result: Dict[str, Any]


# Server → Client message payloads
class StatusPayload(BaseModel):
    state: AssistantState


class TranscriptPayload(BaseModel):
    text: str


class ToolCallPayload(BaseModel):
    tool: str
    args: Dict[str, Any]


class ToolResultPayload(BaseModel):
    tool: str
    result: Dict[str, Any]


class AssistantTextPayload(BaseModel):
    text: str


class TTSChunkPayload(BaseModel):
    audio_base64: str
    seq: int


class ReminderDuePayload(BaseModel):
    text: str
    id: Optional[int] = None


class ErrorPayload(BaseModel):
    message: str
    code: Optional[str] = None


# REST API models
class ImageGenerateRequest(BaseModel):
    prompt: str
    width: int = 512
    height: int = 512
    num_images: int = 1
    guidance_scale: float = 7.5
    num_inference_steps: int = 50


class ImageGenerateResponse(BaseModel):
    job_id: str
    status: str  # "running", "done", "error"
    result_url: Optional[str] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    models_loaded: Dict[str, bool] = {}


# Database models (for API responses)
class ReminderResponse(BaseModel):
    id: int
    text: str
    remind_at: datetime
    completed: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class NoteResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    tags: List[str] = []

    class Config:
        from_attributes = True


class ConversationLogResponse(BaseModel):
    id: int
    timestamp: datetime
    role: str
    content: str
    tool_calls: Optional[str] = None

    class Config:
        from_attributes = True


# Skill-related models
class SkillParameter(BaseModel):
    type: str
    description: Optional[str] = None
    enum: Optional[List[str]] = None
    required: bool = False


class SkillDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    client_executed: bool = False


# Memory models
class MemoryEntry(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any]
    timestamp: datetime
    embedding: Optional[List[float]] = None


class MemorySearchResult(BaseModel):
    entries: List[MemoryEntry]
    query: str
    top_k: int


# Vision models
class VisionRequest(BaseModel):
    image_base64: str
    task: str  # "identify_face", "detect_objects", "read_text"
    options: Dict[str, Any] = {}


class VisionResponse(BaseModel):
    success: bool
    result: Dict[str, Any]
    error: Optional[str] = None


# Knowledge models
class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    collection: str = "athena_knowledge"


class KnowledgeSearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    query: str
    collection: str


# Smart Home models
class SmartHomeDeviceAction(BaseModel):
    entity_id: str
    action: str  # "turn_on", "turn_off", "toggle", "set_brightness", etc.
    attributes: Dict[str, Any] = {}


class SmartHomeResponse(BaseModel):
    success: bool
    entity_id: str
    new_state: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# Weather models
class WeatherRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None


class WeatherResponse(BaseModel):
    location: str
    current: Dict[str, Any]
    forecast: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


# Web Search models
class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: Optional[float] = None


class WebSearchResponse(BaseModel):
    results: List[WebSearchResult]
    query: str
    total_results: Optional[int] = None