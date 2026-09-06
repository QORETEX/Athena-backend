from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    from app.audio.denoise import RNNOISE_AVAILABLE
    from app.memory.store import CHROMA_AVAILABLE
    from app.skills.vision import (
        FACE_RECOGNITION_AVAILABLE,
        TESSERACT_AVAILABLE,
        YOLO_AVAILABLE,
    )
    from app.websocket.voice import PIPER_AVAILABLE, VAD_AVAILABLE, WHISPER_AVAILABLE

    return HealthResponse(
        status="ok",
        version="2.0.0",
        models_loaded={
            "whisper": WHISPER_AVAILABLE,
            "piper_tts": PIPER_AVAILABLE,
            "vad": VAD_AVAILABLE,
            "rnnoise": RNNOISE_AVAILABLE,
            "chromadb": CHROMA_AVAILABLE,
            "face_recognition": FACE_RECOGNITION_AVAILABLE,
            "yolo": YOLO_AVAILABLE,
            "tesseract": TESSERACT_AVAILABLE,
        },
    )
