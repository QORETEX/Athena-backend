from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.config import get_settings
from app.rate_limit import limiter
from app.schemas import ImageGenerateRequest, ImageGenerateResponse
from app.skills.image_gen import handle_image_gen

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/image", tags=["image"])


@router.post("/generate", response_model=ImageGenerateResponse)
@limiter.limit(get_settings().rate_limit_image)
async def generate_image(request: Request, body: ImageGenerateRequest):
    """Generate an image from a text prompt using Gemini (primary) or Stable Diffusion (fallback)."""
    result = await handle_image_gen(
        prompt=body.prompt,
        width=body.width,
        height=body.height,
    )

    return ImageGenerateResponse(
        job_id=result.get("job_id", ""),
        status=result.get("status", "error"),
        result_url=result.get("image_base64"),
        error=result.get("error"),
    )
