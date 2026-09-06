from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.skills.vision import (
    FACE_RECOGNITION_AVAILABLE,
    TESSERACT_AVAILABLE,
    YOLO_AVAILABLE,
    handle_detect_objects,
    handle_identify_face,
    handle_read_text,
    handle_register_face,
)

router = APIRouter(prefix="/api/vision", tags=["vision"])


class VisionRequest(BaseModel):
    image_base64: str


class RegisterFaceRequest(BaseModel):
    name: str
    image_base64: str


@router.get("/status")
async def vision_status():
    """Check which vision capabilities are available."""
    return {
        "face_recognition": FACE_RECOGNITION_AVAILABLE,
        "object_detection": YOLO_AVAILABLE,
        "ocr": TESSERACT_AVAILABLE,
    }


@router.post("/identify-face")
async def identify_face(body: VisionRequest):
    """Identify faces in an image against registered faces."""
    return await handle_identify_face(body.image_base64)


@router.post("/detect-objects")
async def detect_objects(body: VisionRequest):
    """Detect objects in an image using YOLO."""
    return await handle_detect_objects(body.image_base64)


@router.post("/read-text")
async def read_text(body: VisionRequest):
    """Extract text from an image using OCR (Tesseract)."""
    return await handle_read_text(body.image_base64)


@router.post("/register-face")
async def register_face(body: RegisterFaceRequest):
    """Register a new face for future identification."""
    return await handle_register_face(name=body.name, image_base64=body.image_base64)
