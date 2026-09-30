from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from io import BytesIO

from app.config import get_settings
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)

# ── Availability flags ─────────────────────────────────────

GEMINI_AVAILABLE = False
DIFFUSERS_AVAILABLE = False

try:
    from google import genai
    from google.genai import types

    GEMINI_AVAILABLE = True
except ImportError:
    logger.info("google-genai not installed — Gemini image gen disabled")

try:
    from diffusers import StableDiffusionPipeline  # noqa: F401

    DIFFUSERS_AVAILABLE = True
    logger.info("diffusers installed — Stable Diffusion fallback available")
except ImportError:
    logger.info("diffusers not installed — Stable Diffusion fallback disabled")

# Gemini startup diagnostic: library presence alone is not "enabled" —
# all three config values must also be set.
if GEMINI_AVAILABLE:
    _s = get_settings()
    if not _s.image_gen_enabled:
        logger.info("google-genai installed but IMAGE_GEN_ENABLED=false — image gen disabled")
    elif not _s.gemini_api_key:
        logger.warning("IMAGE_GEN_ENABLED=true but GEMINI_API_KEY not set — Gemini image gen disabled")
    elif not _s.gemini_image_model:
        logger.warning("IMAGE_GEN_ENABLED=true but GEMINI_IMAGE_MODEL not set — Gemini image gen disabled")
    else:
        logger.info("Gemini image gen enabled")
    del _s

_sd_pipeline = None


# ── Availability helpers ───────────────────────────────────


def _image_gen_available() -> bool:
    settings = get_settings()
    if not settings.image_gen_enabled:
        return False
    gemini_ready = (
        GEMINI_AVAILABLE
        and bool(settings.gemini_api_key)
        and bool(settings.gemini_image_model)
    )
    return gemini_ready or DIFFUSERS_AVAILABLE


def _image_gen_unavailable_reason() -> str:
    settings = get_settings()
    if not settings.image_gen_enabled:
        return "IMAGE_GEN_ENABLED=false"
    if not GEMINI_AVAILABLE and not DIFFUSERS_AVAILABLE:
        return "google-genai and diffusers not installed"
    if GEMINI_AVAILABLE and not settings.gemini_api_key:
        return "GEMINI_API_KEY not set"
    if GEMINI_AVAILABLE and not settings.gemini_image_model:
        return "GEMINI_IMAGE_MODEL not set"
    return "no image backend configured"


# ── Gemini image generation ────────────────────────────────


async def _generate_with_gemini(prompt: str) -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"error": "GEMINI_API_KEY not configured in .env"}

    def _call_gemini():
        client = genai.Client(api_key=settings.gemini_api_key)

        response = client.models.generate_content(
            model=settings.gemini_image_model,
            contents=f"Generate an image: {prompt}",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                img_bytes = part.inline_data.data
                mime = part.inline_data.mime_type or "image/png"
                return {
                    "image_base64": base64.b64encode(img_bytes).decode("ascii"),
                    "mime_type": mime,
                }

        return {"error": "Gemini did not return an image"}

    return await asyncio.to_thread(_call_gemini)


# ── Stable Diffusion fallback ──────────────────────────────


async def _generate_with_sd(prompt: str, width: int, height: int) -> dict:
    def _run_sd():
        global _sd_pipeline
        if _sd_pipeline is None:
            import torch

            settings = get_settings()
            _sd_pipeline = StableDiffusionPipeline.from_pretrained(
                settings.stable_diffusion_model,
                torch_dtype=torch.float32,
            )

        result = _sd_pipeline(prompt, width=width, height=height, num_inference_steps=30)
        image = result.images[0]

        buf = BytesIO()
        image.save(buf, format="PNG")
        return {
            "image_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "mime_type": "image/png",
        }

    return await asyncio.to_thread(_run_sd)


# ── Unified handler ────────────────────────────────────────


async def handle_image_gen(
    prompt: str, width: int = 512, height: int = 512
) -> dict:
    settings = get_settings()

    if not settings.image_gen_enabled:
        return {"error": "Image generation disabled — set IMAGE_GEN_ENABLED=true in .env"}

    job_id = str(uuid.uuid4())

    try:
        if GEMINI_AVAILABLE and settings.gemini_api_key:
            result = await _generate_with_gemini(prompt)
        elif DIFFUSERS_AVAILABLE:
            result = await _generate_with_sd(prompt, width, height)
        else:
            return {
                "job_id": job_id,
                "status": "error",
                "error": "No image generation backend available. "
                "Install google-genai (Gemini) or diffusers (Stable Diffusion).",
            }

        if "error" in result:
            return {"job_id": job_id, "status": "error", "error": result["error"]}

        return {
            "job_id": job_id,
            "status": "done",
            "image_base64": result["image_base64"],
            "mime_type": result.get("mime_type", "image/png"),
            "prompt": prompt,
            "backend": "gemini" if (GEMINI_AVAILABLE and settings.gemini_api_key) else "stable_diffusion",
        }

    except Exception as e:
        logger.exception("Image generation failed")
        return {"job_id": job_id, "status": "error", "error": str(e)}


register_skill(
    Skill(
        name="generate_image",
        summary="Generate an image",
        description="Generate an image from a text description.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate",
                },
                "width": {
                    "type": "integer",
                    "description": "Image width (default 512, only for Stable Diffusion)",
                },
                "height": {
                    "type": "integer",
                    "description": "Image height (default 512, only for Stable Diffusion)",
                },
            },
            "required": ["prompt"],
        },
        handler=handle_image_gen,
        timeout=120,
        enabled_check=_image_gen_available,
        unavailable_reason=_image_gen_unavailable_reason,
    )
)
