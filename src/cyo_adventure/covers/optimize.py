"""Downscale a generated image to a small WebP (pure, CPU-bound)."""

import io

from PIL import Image

_QUALITY_FLOOR = 1


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
        bytes: WebP-encoded image bytes.
    """
    with Image.open(io.BytesIO(source_bytes)) as src:
        img = src.convert("RGB")
    if img.width > max_width:
        height = round(img.height * (max_width / img.width))
        img = img.resize((max_width, height))
    q = quality
    while True:
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=q)
        data = buf.getvalue()
        if len(data) <= max_bytes or q <= _QUALITY_FLOOR:
            return data
        q -= 10
