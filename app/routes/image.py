from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas import ImageGenerateRequest, ImageGenerateResponse
from app.skills.image_gen import handle_image_gen

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/image", tags=["image"])


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(request: ImageGenerateRequest):
    """Generate an image from a text prompt using Gemini (primary) or Stable Diffusion (fallback)."""
    result = await handle_image_gen(
        prompt=request.prompt,
        width=request.width,
        height=request.height,
    )

    return ImageGenerateResponse(
        job_id=result.get("job_id", ""),
        status=result.get("status", "error"),
        result_url=result.get("image_base64"),
        error=result.get("error"),
    )
