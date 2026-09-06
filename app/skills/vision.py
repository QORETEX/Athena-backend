from __future__ import annotations

import asyncio
import base64
import json
import logging
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from app.config import PROJECT_ROOT
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)

FACE_RECOGNITION_AVAILABLE = False
YOLO_AVAILABLE = False
TESSERACT_AVAILABLE = False

try:
    import face_recognition

    FACE_RECOGNITION_AVAILABLE = True
    logger.info("face_recognition available")
except ImportError:
    logger.info("face_recognition not installed — face ID disabled")

try:
    from ultralytics import YOLO

    YOLO_AVAILABLE = True
    logger.info("YOLO (ultralytics) available")
except ImportError:
    logger.info("ultralytics not installed — object detection disabled")

try:
    import pytesseract

    TESSERACT_AVAILABLE = True
    logger.info("pytesseract available")
except ImportError:
    logger.info("pytesseract not installed — OCR disabled")


KNOWN_FACES_PATH = PROJECT_ROOT / "known_faces.json"
_known_encodings: dict[str, list[float]] = {}
_yolo_model = None


def _load_known_faces():
    global _known_encodings
    if KNOWN_FACES_PATH.exists():
        try:
            data = json.loads(KNOWN_FACES_PATH.read_text())
            _known_encodings = {name: enc for name, enc in data.items()}
        except Exception as e:
            logger.warning("Failed to load known faces: %s", e)


def _save_known_faces():
    try:
        KNOWN_FACES_PATH.write_text(json.dumps(_known_encodings))
    except Exception as e:
        logger.warning("Failed to save known faces: %s", e)


_load_known_faces()


def decode_frame(base64_jpeg: str) -> np.ndarray:
    image_data = base64.b64decode(base64_jpeg)
    image = Image.open(BytesIO(image_data)).convert("RGB")
    return np.array(image)


def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO

        _yolo_model = YOLO("yolov8n.pt")
    return _yolo_model


async def handle_identify_face(image_base64: str) -> dict:
    if not FACE_RECOGNITION_AVAILABLE:
        return {"error": "face_recognition not installed"}

    def _identify():
        frame = decode_frame(image_base64)
        encodings = face_recognition.face_encodings(frame)
        if not encodings:
            return {"found": False, "message": "No face detected in image"}

        faces = []
        for enc in encodings:
            match_name = "unknown"
            for name, known_enc in _known_encodings.items():
                matches = face_recognition.compare_faces(
                    [known_enc], enc, tolerance=0.6
                )
                if matches[0]:
                    match_name = name
                    break
            faces.append({"name": match_name})

        return {"found": True, "faces": faces}

    return await asyncio.to_thread(_identify)


async def handle_detect_objects(image_base64: str) -> dict:
    if not YOLO_AVAILABLE:
        return {"error": "ultralytics (YOLO) not installed"}

    def _detect():
        frame = decode_frame(image_base64)
        model = _get_yolo()
        results = model(frame, verbose=False)
        detections = []
        for box in results[0].boxes:
            detections.append({
                "label": model.names[int(box.cls)],
                "confidence": round(float(box.conf), 3),
                "bbox": box.xyxy[0].tolist(),
            })
        return {"objects": detections}

    return await asyncio.to_thread(_detect)


async def handle_read_text(image_base64: str) -> dict:
    if not TESSERACT_AVAILABLE:
        return {"error": "pytesseract not installed (also needs tesseract binary)"}

    def _ocr():
        frame = decode_frame(image_base64)
        text = pytesseract.image_to_string(frame).strip()
        return {"text": text}

    return await asyncio.to_thread(_ocr)


async def handle_vision(
    image_base64: str, task: str, options: dict | None = None
) -> dict:
    dispatchers = {
        "identify_face": handle_identify_face,
        "detect_objects": handle_detect_objects,
        "read_text": handle_read_text,
    }

    handler = dispatchers.get(task)
    if handler is None:
        return {
            "error": f"Unknown vision task: {task}. Valid: {list(dispatchers.keys())}"
        }

    return await handler(image_base64)


async def handle_register_face(name: str, image_base64: str) -> dict:
    if not FACE_RECOGNITION_AVAILABLE:
        return {"error": "face_recognition not installed"}

    def _register():
        frame = decode_frame(image_base64)
        encodings = face_recognition.face_encodings(frame)
        if not encodings:
            return {"success": False, "error": "No face detected in image"}

        _known_encodings[name] = encodings[0].tolist()
        _save_known_faces()
        return {"success": True, "name": name}

    return await asyncio.to_thread(_register)


register_skill(
    Skill(
        name="vision",
        description="Analyze an image: identify faces, detect objects, or read text (OCR). Send a base64-encoded image and specify the task.",
        parameters={
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded JPEG/PNG image",
                },
                "task": {
                    "type": "string",
                    "enum": ["identify_face", "detect_objects", "read_text"],
                    "description": "What to do with the image",
                },
                "options": {
                    "type": "object",
                    "description": "Task-specific options (reserved for future use)",
                },
            },
            "required": ["image_base64", "task"],
        },
        handler=handle_vision,
        timeout=60,
    )
)

register_skill(
    Skill(
        name="register_face",
        description="Register a new face so it can be identified later. Provide the person's name and a clear photo of their face.",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the person",
                },
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image with the person's face clearly visible",
                },
            },
            "required": ["name", "image_base64"],
        },
        handler=handle_register_face,
        timeout=30,
    )
)
