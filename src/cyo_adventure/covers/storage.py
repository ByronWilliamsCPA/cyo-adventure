"""Upload a cover image to Cloudflare R2 via the S3-compatible API."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import boto3
from botocore.client import Config as BotoConfig

from cyo_adventure.covers.errors import CoverGenerationError

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

    from cyo_adventure.core.config import Settings

_UPLOAD_TIMEOUT_SECONDS = 30.0


def _r2_endpoint_url(account_id: str) -> str:
    """Build the R2 S3-compatible endpoint URL for an account."""
    return f"https://{account_id}.r2.cloudflarestorage.com"


async def upload_cover(image_bytes: bytes, key: str, settings: Settings) -> str:
    """Upsert ``image_bytes`` at ``key`` in the R2 covers bucket; return public URL.

    Args:
        image_bytes: The optimized WebP bytes.
        key: Object key within the bucket, e.g. ``"{storybook_id}/{version}.webp"``.
        settings: App settings (R2 account id, access key pair, bucket, and the
            public-domain base the object is served from).

    Returns:
        str: The public object URL.

    Raises:
        CoverGenerationError: If R2 is not configured.
        botocore.exceptions.ClientError: On a failed PutObject call.
    """
    if (
        not settings.r2_account_id
        or not settings.r2_access_key_id
        or not settings.r2_secret_access_key
        or not settings.r2_public_base_url
    ):
        msg = (
            "R2 cover storage is not configured (R2_ACCOUNT_ID / "
            "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_PUBLIC_BASE_URL)"
        )
        raise CoverGenerationError(msg)
    # #CRITICAL: external resources: Cloudflare R2's free tier caps storage at
    # 10GB; callers MUST pass an already-optimized small WebP. S3 PutObject is
    # inherently an upsert (no separate overwrite flag), so a re-roll replaces
    # the prior object at the same key instead of leaking orphans against that
    # budget.
    # #VERIFY: covers/service.py optimizes before calling upload_cover; a
    # PutObject at an existing key silently overwrites it.
    client: S3Client = boto3.client(
        "s3",
        endpoint_url=_r2_endpoint_url(settings.r2_account_id),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        # R2 has no region concept; "auto" is Cloudflare's documented value.
        region_name="auto",
        config=BotoConfig(
            signature_version="s3v4",
            connect_timeout=_UPLOAD_TIMEOUT_SECONDS,
            read_timeout=_UPLOAD_TIMEOUT_SECONDS,
        ),
    )
    bucket = settings.r2_bucket
    # #CRITICAL: timing dependencies: boto3's S3 client is synchronous; run the
    # blocking network call off the event loop so a slow/unavailable R2 upload
    # cannot stall other async work sharing this process.
    # #VERIFY: asyncio.to_thread offloads put_object to a worker thread.
    await asyncio.to_thread(
        client.put_object,
        Bucket=bucket,
        Key=key,
        Body=image_bytes,
        ContentType="image/webp",
    )
    # #CRITICAL: external resources: this URL is only browser-reachable if the
    # owner has connected a custom domain to this R2 bucket in the Cloudflare
    # dashboard and pointed r2_public_base_url at it; the raw R2 S3 endpoint
    # is not public.
    # #VERIFY: manual check: a fresh cover's URL loads in a browser after deploy.
    return f"{settings.r2_public_base_url.rstrip('/')}/{key}"
