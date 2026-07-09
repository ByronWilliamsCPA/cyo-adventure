"""Upload a cover image to Supabase Storage via the REST API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from cyo_adventure.covers.errors import CoverGenerationError

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

_UPLOAD_TIMEOUT = 30.0


async def upload_cover(image_bytes: bytes, key: str, settings: Settings) -> str:
    """Upsert ``image_bytes`` at ``key`` in the covers bucket; return public URL.

    Args:
        image_bytes: The optimized WebP bytes.
        key: Object key within the bucket, e.g. ``"{storybook_id}/{version}.webp"``.
        settings: App settings (Supabase URL, service key, bucket name).

    Returns:
        str: The public object URL.

    Raises:
        CoverGenerationError: If Supabase is not configured.
        httpx.HTTPStatusError: On a non-2xx upload response.
    """
    if not settings.supabase_url or not settings.supabase_service_key:
        msg = "Supabase storage is not configured (SUPABASE_URL / SUPABASE_SERVICE_KEY)"
        raise CoverGenerationError(msg)
    # #CRITICAL: external resources: Supabase Storage is capped at 500MB total;
    # callers MUST pass an already-optimized small WebP. Upsert keeps re-rolls
    # from leaking orphaned objects against that budget.
    # #VERIFY: covers/service.py optimizes before calling; x-upsert overwrites.
    base = settings.supabase_url.rstrip("/")
    bucket = settings.covers_bucket
    upload_url = f"{base}/storage/v1/object/{bucket}/{key}"
    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        resp = await client.post(
            upload_url,
            content=image_bytes,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "image/webp",
                "x-upsert": "true",
            },
        )
    resp.raise_for_status()
    return f"{base}/storage/v1/object/public/{bucket}/{key}"
