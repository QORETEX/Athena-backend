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
    logger.info("google-genai available — Gemini image gen enabled")
except ImportError:
    logger.info("google-genai not installed — Gemini image gen disabled")

try:
    from diffusers import StableDiffusionPipeline  # noqa: F401

    DIFFUSERS_AVAILABLE = True
    logger.info("diffusers available — Stable Diffusion fallback enabled")
except ImportError:
    logger.info("diffusers not installed — Stable Diffusion fallback disabled")

_sd_pipeline = None


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
        description="Generate an image from a text description. Uses Gemini or Stable Diffusion.",
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
    )
)
