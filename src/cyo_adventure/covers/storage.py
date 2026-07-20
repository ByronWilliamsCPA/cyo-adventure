"""Upload a cover image to Cloudflare R2 via the S3-compatible API."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from cyo_adventure.covers.errors import CoverGenerationError

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

    from cyo_adventure.core.config import Settings

_logger = structlog.get_logger(__name__)

_UPLOAD_TIMEOUT_SECONDS = 30.0

# #CRITICAL: security: covers are served exclusively via short-lived presigned
# GET URLs (see generate_presigned_cover_url), not a permanent public URL, so
# the R2 bucket must NOT have a public custom domain or r2.dev access bound to
# it in the Cloudflare dashboard -- that is an infrastructure step outside
# this codebase (docs/compliance/coppa-gdpr-remediation-plan.md Phase 1d).
# 3600s balances exposure window (a leaked URL via referrer/history/screenshot
# is only usable for an hour) against not forcing a page refresh mid-browse
# for a family paging through a library of covers.
# #VERIFY: test_cover_storage.py::test_presigned_url_expires_in_one_hour.
_PRESIGNED_URL_TTL_SECONDS = 3600


def _r2_endpoint_url(account_id: str) -> str:
    """Build the R2 S3-compatible endpoint URL for an account."""
    return f"https://{account_id}.r2.cloudflarestorage.com"


def _require_r2_configured(
    settings: Settings, *, require_public_base_url: bool
) -> None:
    """Raise if any required R2 credential/setting is missing or blank.

    Args:
        settings: App settings to check.
        require_public_base_url: Whether ``r2_public_base_url`` is required.
            ``upload_cover`` still needs it (it returns a public URL for
            ``scripts/backfill_covers_r2.py``'s URL-classification logic and
            the ``cover_image_url`` audit column); the presigned-read path
            does not, since it never constructs a public URL.

    Raises:
        CoverGenerationError: If R2 is not fully configured.
    """
    if (
        not settings.r2_account_id
        or not settings.r2_access_key_id
        or not settings.r2_secret_access_key
        or not settings.r2_bucket
        or (require_public_base_url and not settings.r2_public_base_url)
    ):
        fields = "R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET"
        if require_public_base_url:
            fields += " / R2_PUBLIC_BASE_URL"
        msg = f"R2 cover storage is not configured ({fields})"
        raise CoverGenerationError(msg)


def _build_client(settings: Settings) -> S3Client:
    """Construct the shared R2 S3-compatible client from app settings.

    Callers MUST run this off the event loop (blocking disk I/O per the
    #CRITICAL note on ``upload_cover``); it is not itself async.

    Args:
        settings: App settings (already validated via
            :func:`_require_r2_configured`).

    Returns:
        S3Client: A boto3 client scoped to this R2 account.
    """
    return boto3.client(
        "s3",
        endpoint_url=_r2_endpoint_url(settings.r2_account_id or ""),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
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


async def upload_cover(image_bytes: bytes, key: str, settings: Settings) -> str:
    """Upsert ``image_bytes`` at ``key`` in the R2 covers bucket; return public URL.

    The returned URL is stored on ``cover_image_url`` for audit/history and for
    ``scripts/backfill_covers_r2.py``'s URL-classification logic; it is NOT the
    URL served to readers, which is always a fresh presigned URL (see
    ``generate_presigned_cover_url``) generated from the same deterministic
    key, independent of this stored value.

    Args:
        image_bytes: The optimized WebP bytes.
        key: Object key within the bucket, e.g. ``"{storybook_id}/{version}.webp"``.
        settings: App settings (R2 account id, access key pair, bucket, and the
            public-domain base recorded alongside the upload).

    Returns:
        str: The public object URL.

    Raises:
        CoverGenerationError: If R2 is not configured.
        botocore.exceptions.ClientError: On a failed PutObject call.
    """
    _require_r2_configured(settings, require_public_base_url=True)
    # #CRITICAL: external resources: Cloudflare R2's free tier caps storage at
    # 10GB; callers MUST pass an already-optimized small WebP. S3 PutObject is
    # inherently an upsert (no separate overwrite flag), so a re-roll replaces
    # the prior object at the same key instead of leaking orphans against that
    # budget.
    # #VERIFY: covers/service.py optimizes before calling upload_cover; a
    # PutObject at an existing key silently overwrites it.
    bucket = settings.r2_bucket

    def _build_client_and_put() -> None:
        client = _build_client(settings)
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
    # #CRITICAL: external resources: this URL is recorded for audit/backfill
    # classification only; it is only browser-reachable if the owner has
    # connected a public custom domain to this R2 bucket. Readers are never
    # sent this value directly (see the module-level presigned-URL note).
    # _require_r2_configured(require_public_base_url=True) above guarantees
    # this is non-empty.
    public_base_url = settings.r2_public_base_url or ""
    return f"{public_base_url.rstrip('/')}/{key}"


def cover_object_key(storybook_id: str, version: int) -> str:
    """Return the canonical R2 object key for a story version's cover.

    The single source of truth for this format; ``covers/service.py`` (on
    upload) and every read path (via ``generate_presigned_cover_url``) must
    derive the same key from the same two identifiers.

    Args:
        storybook_id: The storybook id.
        version: The version number.

    Returns:
        str: The canonical object key, e.g. ``"s1/2.webp"``.
    """
    return f"{storybook_id}/{version}.webp"


async def generate_presigned_cover_url(
    storybook_id: str,
    version: int,
    settings: Settings,
    *,
    expires_in: int = _PRESIGNED_URL_TTL_SECONDS,
) -> str | None:
    """Return a short-lived signed GET URL for a story version's cover.

    Generating a presigned URL is a local HMAC computation (no network call),
    but client construction does blocking disk I/O (see ``upload_cover``), so
    this still offloads to a worker thread.

    # #CRITICAL: external resources: this is a READ/display path, not a
    # write; R2 being unconfigured or a presign call failing must degrade to
    # "no cover shown" rather than 500 the whole page a cover is embedded in
    # (library listing, recommendations feed, admin status poll). Unlike
    # ``upload_cover`` (a write whose caller needs the failure to mark the
    # job "failed"), every caller here can tolerate a missing image.
    # #VERIFY: test_cover_storage.py::
    # test_generate_presigned_cover_url_returns_none_when_unconfigured,
    # ::test_generate_presigned_cover_url_returns_none_on_client_error.

    Args:
        storybook_id: The storybook id.
        version: The version number.
        settings: App settings (R2 account id, access key pair, and bucket).
        expires_in: URL validity window in seconds.

    Returns:
        str | None: A signed URL valid for ``expires_in`` seconds, or None if
        R2 is not configured or URL generation otherwise fails (logged, not
        raised).
    """
    try:
        _require_r2_configured(settings, require_public_base_url=False)
    except CoverGenerationError:
        _logger.warning(
            "cover_presign_unconfigured", storybook_id=storybook_id, version=version
        )
        return None
    bucket = settings.r2_bucket
    key = cover_object_key(storybook_id, version)

    def _presign() -> str:
        client = _build_client(settings)
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    try:
        return await asyncio.to_thread(_presign)
    except (BotoCoreError, ClientError):
        _logger.warning(
            "cover_presign_failed",
            storybook_id=storybook_id,
            version=version,
            exc_info=True,
        )
        return None


async def generate_presigned_cover_urls(
    pairs: list[tuple[str, int]],
    settings: Settings,
    *,
    expires_in: int = _PRESIGNED_URL_TTL_SECONDS,
) -> dict[tuple[str, int], str]:
    """Return presigned GET URLs for many story versions' covers at once.

    A listing view (library, recommendations) needs a URL per book; signing
    is a local HMAC computation, so this builds one client and signs every
    key in a single worker-thread call instead of N separate
    ``asyncio.to_thread`` round-trips (each of which pays boto3's client
    construction cost, per ``_build_client``'s blocking-disk-I/O note).

    # #CRITICAL: external resources: same degrade-not-crash contract as
    # ``generate_presigned_cover_url``: an unconfigured R2 or a failed batch
    # sign yields an empty dict (every book in the listing shows no cover)
    # rather than a 500 on the whole listing.
    # #VERIFY: test_cover_storage.py::
    # test_generate_presigned_cover_urls_returns_empty_dict_when_unconfigured,
    # ::test_generate_presigned_cover_urls_returns_empty_dict_on_client_error.

    Args:
        pairs: The ``(storybook_id, version)`` pairs to sign.
        settings: App settings (R2 account id, access key pair, and bucket).
        expires_in: URL validity window in seconds.

    Returns:
        dict[tuple[str, int], str]: Every requested pair mapped to its signed
        URL. Empty input, an unconfigured R2, or a failed sign call all
        return an empty dict (logged, not raised) rather than a partial or
        raised result.
    """
    if not pairs:
        return {}
    try:
        _require_r2_configured(settings, require_public_base_url=False)
    except CoverGenerationError:
        _logger.warning("cover_presign_batch_unconfigured", count=len(pairs))
        return {}
    bucket = settings.r2_bucket

    def _presign_all() -> dict[tuple[str, int], str]:
        client = _build_client(settings)
        return {
            pair: client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": cover_object_key(*pair)},
                ExpiresIn=expires_in,
            )
            for pair in pairs
        }

    try:
        return await asyncio.to_thread(_presign_all)
    except (BotoCoreError, ClientError):
        _logger.warning("cover_presign_batch_failed", count=len(pairs), exc_info=True)
        return {}
