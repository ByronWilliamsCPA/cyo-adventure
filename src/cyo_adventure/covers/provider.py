"""Nano banana (Gemini image generation) call. Returns raw image bytes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from google import genai
from google.genai import types

from cyo_adventure.covers.errors import CoverGenerationError

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings


def generate_cover_image(prompt: str, settings: Settings) -> bytes:
    """Generate a portrait cover image via nano banana Pro.

    Args:
        prompt: The descriptive, textless-art prompt.
        settings: App settings (reads ``gemini_api_key`` and ``cover_model``).

    Returns:
        bytes: Raw image bytes (PNG) from the first inline image part.

    Raises:
        CoverGenerationError: If unconfigured, refused, or no image is returned.
    """
    # #CRITICAL: external resources: the Gemini SDK call has no retry/backoff and
    # a safety refusal returns empty candidates; surface it as a typed error so
    # the worker can mark the job failed rather than crash.
    # #VERIFY: empty candidates / content is None raise CoverGenerationError below.
    if not settings.gemini_api_key:
        msg = "GEMINI_API_KEY is not configured"
        raise CoverGenerationError(msg)
    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.cover_model,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(aspect_ratio="2:3", image_size="1K"),
        ),
    )
    for candidate in response.candidates or []:
        content = candidate.content
        if content is None:
            continue
        for part in content.parts or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and inline.data:
                return inline.data
    feedback = getattr(response, "prompt_feedback", None)
    msg = f"nano banana returned no image (prompt_feedback={feedback})"
    raise CoverGenerationError(msg)
