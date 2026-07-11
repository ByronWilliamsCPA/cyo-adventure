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
    bucket = settings.r2_bucket
    account_id = settings.r2_account_id
    access_key_id = settings.r2_access_key_id
    secret_access_key = settings.r2_secret_access_key

    def _build_client_and_put() -> None:
        client: S3Client = boto3.client(
            "s3",
            endpoint_url=_r2_endpoint_url(account_id),
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            # Sonar python:S6262 false positive: R2 has no region concept and
            # Cloudflare's S3-compatibility docs REQUIRE the literal "auto"
            # ("the region for an R2 bucket is `auto`"); there is nothing to
            # configure per environment.
            region_name="auto",
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=_UPLOAD_TIMEOUT_SECONDS,
                read_timeout=_UPLOAD_TIMEOUT_SECONDS,
                # #EDGE: external resources: botocore >=1.36 defaults to
                # mandatory request/response checksums that R2 does not
                # support the same way AWS S3 does; Cloudflare's R2 docs
                # direct clients to opt back to "when_required".
                # #VERIFY: manual smoke-test upload against live R2 confirms
                # PutObject succeeds with these settings.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                # Path-style addressing avoids a 2-level subdomain
                # (<bucket>.<account>.r2.cloudflarestorage.com) that can fall
                # outside R2's wildcard TLS certificate scope.
                s3={"addressing_style": "path"},
            ),
        )
        # Sonar python:S7608 false positive: ExpectedBucketOwner is an AWS
        # cross-account bucket-confusion safeguard. Cloudflare R2 does not
        # implement x-amz-expected-bucket-owner (marked unsupported in the R2
        # S3-api docs), and the endpoint above is already scoped to a single
        # Cloudflare account id, so cross-account confusion cannot occur.
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=image_bytes,
            ContentType="image/webp",
        )

    # #CRITICAL: timing dependencies: boto3's S3 client is synchronous, and
    # constructing it does blocking disk I/O (service-model JSON, credential
    # file reads) in addition to the blocking put_object network call; run
    # both off the event loop so a slow/unavailable R2 upload cannot stall
    # other async work sharing this process.
    # #VERIFY: asyncio.to_thread offloads client construction and put_object
    # to a worker thread together.
    # #ASSUME: concurrency: RQ's UnixSignalDeathPenalty delivers SIGALRM to
    # the main thread only, so a job timeout cannot interrupt this worker
    # thread; a slow upload plus botocore's default retries can keep running
    # past cover_job_timeout_seconds after the job is already marked failed.
    # #VERIFY: bound worst-case thread lifetime (e.g. a stricter retry
    # policy) or move upload cancellation to a mechanism that can reach a
    # background thread; tracked as a follow-up, not fixed here.
    await asyncio.to_thread(_build_client_and_put)
    # #CRITICAL: external resources: this URL is only browser-reachable if the
    # owner has connected a custom domain to this R2 bucket in the Cloudflare
    # dashboard and pointed r2_public_base_url at it; the raw R2 S3 endpoint
    # is not public.
    # #VERIFY: manual check: a fresh cover's URL loads in a browser after deploy.
    return f"{settings.r2_public_base_url.rstrip('/')}/{key}"
