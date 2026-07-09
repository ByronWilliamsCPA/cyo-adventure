"""Downscale a generated image to a small WebP (pure, CPU-bound)."""

import io

import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

# #ASSUME: production-risk: 40 keeps the step-down loop's landing quality in
# [31, 40] for any starting quality above the floor, since a single step is
# 10 points; a lower floor (e.g. 1) combined with a non-multiple-of-10
# starting quality can walk past 0 into a negative Pillow quality value.
# #VERIFY: the loop also clamps the saved quality to >= 0 independently, so a
# future change to this constant cannot reintroduce the crash on its own.
_QUALITY_FLOOR = 40


def optimize_cover(
    source_bytes: bytes,
    *,
    max_width: int = 800,
    quality: int = 80,
    max_bytes: int = 256_000,
) -> bytes:
    """Resize to ``max_width`` (preserving ratio) and encode WebP under a ceiling.

    Args:
        source_bytes: The raw source image (PNG/JPEG) from the provider.
        max_width: Target width in px; taller/wider sources are downscaled.
        quality: Initial WebP quality; stepped down toward the floor if needed.
        max_bytes: Soft ceiling; quality is reduced until met or the floor hits.

    Returns:
        bytes: WebP-encoded image bytes. May exceed ``max_bytes`` if the floor
        is reached first; the ceiling is a target, not a hard requirement.
    """
    # #EDGE: data integrity: source_bytes is untrusted external input from the
    # image generation provider; a malformed or undecodable payload raises
    # PIL.UnidentifiedImageError here.
    # #VERIFY: intentionally not caught: covers/service.py treats any
    # exception from this function as a failed cover (cover_status="failed"),
    # so letting it propagate is the correct behavior, not an oversight.
    with Image.open(io.BytesIO(source_bytes)) as src:
        img = src.convert("RGB")
    if img.width > max_width:
        height = max(1, round(img.height * (max_width / img.width)))
        img = img.resize((max_width, height))
    q = quality
    while True:
        save_quality = max(q, 0)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=save_quality)
        data = buf.getvalue()
        under_ceiling = len(data) <= max_bytes
        at_floor = q <= _QUALITY_FLOOR
        if under_ceiling or at_floor:
            if not under_ceiling:
                logger.warning(
                    "cover_over_size_ceiling",
                    final_bytes=len(data),
                    quality=save_quality,
                    max_bytes=max_bytes,
                )
            return data
        q -= 10
