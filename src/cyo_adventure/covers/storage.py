"""Upload a cover image to Cloudflare R2 via the S3-compatible API."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.utils.redaction import digest_identifier

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


# A Cloudflare account id becomes the leftmost label of the R2 endpoint hostname
# below, so it must be a legal DNS label. Duplicated from
# ``scripts/backup_database.py::_ACCOUNT_ID_RE`` rather than shared: that script must
# run standalone in CI with only the ``api`` extra installed and cannot import from
# this package (see the note on ``_r2_endpoint_url`` there). Keep the two in step.
# ``fullmatch`` rather than ``match``: ``$`` also matches before a trailing newline.
_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _r2_endpoint_url(account_id: str) -> str:
    """Build the R2 S3-compatible endpoint URL for an account."""
    return f"https://{account_id}.r2.cloudflarestorage.com"


def _key_log_fields(key: str) -> dict[str, object]:
    """Project an object key into log fields that disclose no salt.

    # #CRITICAL: security: the object key embeds ``cover_object_salt``, whose
    # whole job (see ``cover_object_key``'s note, UW-M07) is to be unguessable
    # so the bucket's private binding is not the only thing between a guessed
    # storybook id and the image bytes. Writing the key to a log publishes
    # that control to every sink the logs reach, in every environment. Only
    # the already-public storybook id and a non-reversible digest of the key
    # leave this function.
    # #VERIFY: tests/unit/test_cover_storage.py::
    # TestDeleteCoverNeverLogsTheSaltedKey asserts neither the salt nor the
    # key appears in either warning path's emitted event.

    Args:
        key: The object key, as produced by :func:`cover_object_key`.

    Returns:
        dict[str, object]: ``storybook_id`` (the key's already-public prefix,
        empty when the key has no ``/``), ``version`` (the salt-free numeric
        segment, matching what the sibling ``cover_presign_*`` log sites emit,
        and omitted when the key does not parse), and ``key_digest``, a stable
        digest that correlates repeated failures on one object without
        revealing it.
    """
    storybook_id, _, remainder = key.partition("/")
    fields: dict[str, object] = {
        "storybook_id": storybook_id,
        "key_digest": digest_identifier(key),
    }
    # `<version>-<salt>.webp` when salted, `<version>.webp` when legacy. The
    # version is not secret and is what tells an operator WHICH cover failed;
    # it is omitted rather than emitted as a string for an unparseable key, so
    # this field never varies in type between log lines.
    version_text = remainder.partition("-")[0].removesuffix(".webp")
    if version_text.isdigit():
        fields["version"] = int(version_text)
    return fields


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
        CoverGenerationError: If R2 is not fully configured, or if
            ``r2_account_id`` cannot be a hostname label.
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

    # #CRITICAL: external resources: without this, a malformed account id is
    # interpolated into the endpoint hostname and boto3 reports only
    # `Invalid endpoint: https://***.r2.cloudflarestorage.com`, where `***` is the
    # deployment's secret mask. That message cannot tell an operator whether the
    # value carries a stray space or is a whole URL pasted into the id field, which
    # is the exact failure that cost `scripts/backup_database.py` two dispatches to
    # diagnose on 2026-08-27. Raising here rather than in a Settings validator keeps
    # the blast radius on cover art: `settings = Settings()` runs at import.
    # #VERIFY: tests/unit/test_cover_storage.py::test_upload_cover_rejects_a_malformed_account_id
    if not _ACCOUNT_ID_RE.fullmatch(settings.r2_account_id):
        msg = (
            "R2_ACCOUNT_ID is not a valid hostname label, so no R2 endpoint can be "
            f"built from it (it holds {len(settings.r2_account_id)} characters). A "
            "Cloudflare account id is 32 lowercase hex characters: copy it from the "
            "R2 dashboard sidebar, not the S3 API endpoint URL."
        )
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
    ``generate_presigned_cover_url``) generated from the same ``key``,
    independent of this stored value.

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
    # an upsert (no separate overwrite flag), but since cover_object_key folds
    # in a per-cover random salt a re-roll lands on a DIFFERENT key, so it no
    # longer reclaims the prior object implicitly: the caller must delete the
    # previous key itself (covers/service.py::generate_cover, via
    # delete_cover) or every regeneration orphans an object against that
    # budget and leaves it reachable by an outstanding presigned URL.
    # #VERIFY: covers/service.py optimizes before calling upload_cover, and
    # tests/integration/test_cover_service.py::
    # test_regeneration_deletes_the_previous_object pins the delete.
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


async def delete_cover(key: str, settings: Settings) -> bool:
    """Best-effort delete of one cover object from the R2 covers bucket.

    Used when a cover is regenerated: because the object key now folds in a
    per-cover random salt (see ``cover_object_key``), a re-roll writes to a
    NEW key instead of overwriting the previous object in place, so the prior
    object has to be removed explicitly or it is orphaned in the bucket.

    # #CRITICAL: security: an orphaned object stays fetchable by anyone
    # holding a previously-issued presigned URL for it (up to that URL's
    # 1-hour TTL) and, if the bucket's public binding is ever mistakenly
    # restored, indefinitely at a key that is no longer referenced by any
    # row. A failed delete is therefore a real (if bounded) exposure, not
    # just wasted storage against R2's 10GB free-tier cap, so it is logged
    # loudly rather than silently swallowed. It is still non-fatal: the
    # replacement cover is already uploaded and committed by the time this
    # runs, and failing the whole regeneration would leave the caller worse
    # off (a "failed" status over a cover that actually exists).
    # #VERIFY: tests/unit/test_cover_storage.py::
    # test_delete_cover_returns_false_on_client_error,
    # ::test_delete_cover_returns_false_when_unconfigured; the caller's
    # non-fatal contract is pinned by tests/integration/test_cover_service.py
    # ::test_regeneration_survives_a_failed_delete_of_the_previous_object.

    Args:
        key: The object key to remove, as produced by ``cover_object_key``.
        settings: App settings (R2 account id, access key pair, and bucket).
            The public base URL is not required: nothing here builds a URL.

    Returns:
        bool: True when the DeleteObject call completed, False when R2 is
        unconfigured or the call failed (both logged, never raised). S3
        DeleteObject is idempotent, so True does not imply the object
        existed beforehand.
    """
    try:
        _require_r2_configured(settings, require_public_base_url=False)
    except CoverGenerationError:
        _logger.warning("cover_delete_unconfigured", **_key_log_fields(key))
        return False
    bucket = settings.r2_bucket

    def _build_client_and_delete() -> None:
        client = _build_client(settings)
        # Sonar python:S7608 false positive: see the identical note in
        # upload_cover; R2 does not implement x-amz-expected-bucket-owner and
        # the endpoint is already scoped to one Cloudflare account id.
        client.delete_object(Bucket=bucket, Key=key)

    # #CRITICAL: timing dependencies: same rationale as upload_cover -- boto3
    # client construction does blocking disk I/O and delete_object is a
    # blocking network call, so both run off the event loop.
    # #VERIFY: asyncio.to_thread wraps client construction and delete_object
    # together.
    try:
        await asyncio.to_thread(_build_client_and_delete)
    except (BotoCoreError, ClientError):
        _logger.warning("cover_delete_failed", **_key_log_fields(key), exc_info=True)
        return False
    return True


def cover_object_key(storybook_id: str, version: int, salt: str | None = None) -> str:
    """Return the canonical R2 object key for a story version's cover.

    The single source of truth for this format; ``covers/service.py`` (on
    upload) and every read path (via ``generate_presigned_cover_url``) must
    derive the same key from the same identifiers.

    # #CRITICAL: security: UW-M07 defense-in-depth (StorybookVersion.
    # cover_object_salt). With no salt the key is fully determined by
    # storybook_id and version, both of which a client can already see or
    # guess, so the object is only as private as the bucket's own access
    # control. Folding in a per-cover random salt means the bucket binding
    # (kept private per the module docstring above) is no longer the only
    # thing standing between a guessed storybook id and the image bytes.
    # #VERIFY: test_cover_object_key_includes_salt_when_present,
    # test_cover_object_key_falls_back_without_salt.

    Args:
        storybook_id: The storybook id.
        version: The version number.
        salt: The per-cover token from ``cover_object_salt``, or None for a
            row created before that column existed, which keeps resolving at
            the legacy unsalted key rather than a key nothing was ever
            uploaded to.

    Returns:
        str: The object key, e.g. ``"s1/2-<salt>.webp"``, or the legacy
        ``"s1/2.webp"`` when ``salt`` is None.
    """
    if salt:
        return f"{storybook_id}/{version}-{salt}.webp"
    return f"{storybook_id}/{version}.webp"


async def generate_presigned_cover_url(
    storybook_id: str,
    version: int,
    settings: Settings,
    *,
    salt: str | None = None,
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
        salt: The row's ``cover_object_salt`` (None for a pre-migration row);
            forwarded to ``cover_object_key`` unchanged.
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
    key = cover_object_key(storybook_id, version, salt)

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
    triples: list[tuple[str, int, str | None]],
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
        triples: The ``(storybook_id, version, salt)`` rows to sign; ``salt``
            is each row's ``cover_object_salt`` (None for a pre-migration
            row), forwarded to ``cover_object_key`` unchanged.
        settings: App settings (R2 account id, access key pair, and bucket).
        expires_in: URL validity window in seconds.

    Returns:
        dict[tuple[str, int], str]: Every requested ``(storybook_id,
        version)`` mapped to its signed URL (the salt is not part of the
        returned key, since callers look results up by book identity, not by
        the internal object key). Empty input, an unconfigured R2, or a
        failed sign call all return an empty dict (logged, not raised)
        rather than a partial or raised result.
    """
    if not triples:
        return {}
    try:
        _require_r2_configured(settings, require_public_base_url=False)
    except CoverGenerationError:
        _logger.warning("cover_presign_batch_unconfigured", count=len(triples))
        return {}
    bucket = settings.r2_bucket

    def _presign_all() -> dict[tuple[str, int], str]:
        client = _build_client(settings)
        return {
            (storybook_id, version): client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": cover_object_key(storybook_id, version, salt),
                },
                ExpiresIn=expires_in,
            )
            for storybook_id, version, salt in triples
        }

    try:
        return await asyncio.to_thread(_presign_all)
    except (BotoCoreError, ClientError):
        _logger.warning("cover_presign_batch_failed", count=len(triples), exc_info=True)
        return {}
