"""Backfill pre-R2 cover art from Supabase Storage to Cloudflare R2.

PR #209 (commit 6a2036b) moved cover-art storage from Supabase Storage to
Cloudflare R2 but explicitly did not migrate covers generated before that
cutover: those rows still carry a Supabase Storage public URL in
``storybook_version.cover_image_url`` (see the CHANGELOG.md "No migration"
note under that PR's entry). This script performs that migration as a
one-shot operator task:

1. Selects every ``StorybookVersion`` row with a non-null ``cover_image_url``.
2. Classifies each URL as ``"supabase"`` (candidate), ``"r2"`` (already
   migrated; skipped, not counted as a candidate), or ``"other"`` (skipped).
3. For each ``"supabase"`` candidate: downloads the original bytes, uploads
   them to R2 via the real ``upload_cover()`` (the same function
   ``covers/service.py`` uses for freshly generated covers) under the
   canonical ``{storybook_id}/{version}.webp`` key, downloads the bytes back
   from the new R2 URL, and only writes the new URL to the database if the
   re-downloaded bytes are byte-for-byte identical to the original. Any
   download/upload failure or a verification mismatch leaves the row
   untouched and counts it as failed; nothing is ever half-migrated.

Run recipe (idempotent: re-running skips rows already migrated to R2)::

    uv run --env-file .env python scripts/backfill_covers_r2.py --dry-run
    uv run --env-file .env python scripts/backfill_covers_r2.py

This is a real one-shot admin script that writes to the configured database
and uploads to the configured R2 bucket. It is NOT covered by integration
tests against live infrastructure; always run ``--dry-run`` first against a
non-production database/bucket and read its summary before running live.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import time
from typing import TYPE_CHECKING

import httpx
from botocore.exceptions import ClientError
from sqlalchemy import select

from cyo_adventure.core.config import settings as _settings
from cyo_adventure.core.database import get_session
from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.storage import upload_cover
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.utils.logging import get_logger, setup_logging

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings

_logger = get_logger(__name__)

# #ASSUME: external resources: the williamshome.family Cloudflare zone's bot
# protection returns a 403 for the default python-httpx/requests User-Agent
# (observed in practice during the PR #209/#210 R2 rollout smoke tests); a
# browser-like User-Agent avoids tripping that same bot challenge when
# downloading cover bytes from either the old Supabase public URL or the new
# R2 public URL.
# #VERIFY: run a manual smoke test (download one known cover URL with this
# User-Agent) before running this script against a live database/bucket.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_DOWNLOAD_TIMEOUT_SECONDS = 30.0

# Matches the pre-R2 Supabase Storage public URL shape:
# https://<project-ref>.supabase.co/storage/v1/object/public/<bucket>/<key>
# An optional "?..." cache-busting query suffix (e.g. "?v=1") is tolerated
# since it is folded into the trailing ".+" group.
_SUPABASE_STORAGE_URL_RE = re.compile(
    r"^https://[^/]+\.supabase\.co/storage/v1/object/public/[^/]+/.+$"
)


def classify_cover_url(url: str, r2_public_base_url: str | None) -> str:
    """Classify a ``cover_image_url`` value as ``"r2"``, ``"supabase"``, or ``"other"``.

    Args:
        url: The row's current ``cover_image_url`` value (never None; callers
            only classify non-null URLs).
        r2_public_base_url: The configured R2 public base URL
            (``settings.r2_public_base_url``), or None if R2 is unconfigured.

    Returns:
        ``"r2"`` if the URL already starts with the configured R2 public
        base (already migrated; not a candidate), ``"supabase"`` if it
        matches the pre-R2 Supabase Storage public URL shape (a migration
        candidate), or ``"other"`` for anything else (not a candidate).
    """
    if r2_public_base_url and url.startswith(r2_public_base_url):
        return "r2"
    if _SUPABASE_STORAGE_URL_RE.match(url):
        return "supabase"
    return "other"


async def _download(client: httpx.AsyncClient, url: str) -> bytes:
    """Download bytes from ``url`` using the shared client.

    Args:
        client: The shared httpx.AsyncClient (browser User-Agent already set).
        url: The absolute URL to download.

    Returns:
        The response body bytes.

    Raises:
        httpx.HTTPError: On any request failure or non-2xx response.
    """
    response = await client.get(url)
    response.raise_for_status()
    return response.content


async def migrate_row(
    row: StorybookVersion,
    *,
    session: AsyncSession,
    client: httpx.AsyncClient,
    settings: Settings,
    dry_run: bool,
    upload: Callable[[bytes, str, Settings], Awaitable[str]] = upload_cover,
) -> str:
    """Migrate one Supabase-classified candidate row to R2.

    Downloads the original bytes from the row's current (Supabase) URL,
    uploads them to R2 under the canonical ``{storybook_id}/{version}.webp``
    key via ``upload``, then re-downloads from the returned R2 public URL and
    compares byte-for-byte against the original before writing anything to
    the database. Never raises: any download/upload failure, or a
    verification mismatch, is logged as a warning and reported as a failed
    outcome so the caller can continue to the next row without writing to
    this one.

    Args:
        row: The candidate StorybookVersion row (non-null cover_image_url
            already classified "supabase" by the caller).
        session: The active DB session; used to commit the URL update on
            success. Never committed to on failure.
        client: Shared httpx.AsyncClient with a browser-like User-Agent.
        settings: App settings, passed through to ``upload``.
        dry_run: When True, only logs the would-be migration and returns
            "skipped" without any network call or database write.
        upload: The R2 upload callable. Defaults to the real
            ``covers.storage.upload_cover``; tests substitute a fake so no
            real boto3/network call is made.

    Returns:
        ``"migrated"``, ``"skipped"`` (dry-run only), or ``"failed"``.
    """
    key = f"{row.storybook_id}/{row.version}.webp"
    original_url = row.cover_image_url
    # #ASSUME: data integrity: the caller only invokes this for rows already
    # classified "supabase" by classify_cover_url(), which only classifies
    # non-null URLs; this assert documents that invariant rather than
    # silently treating a None URL as an empty-string download target.
    # #VERIFY: backfill()'s WHERE clause and classification gate both run
    # before migrate_row() is ever called.
    assert original_url is not None

    if dry_run:
        _logger.info(
            "backfill_dry_run_candidate",
            storybook_id=row.storybook_id,
            version=row.version,
            key=key,
            source_url=original_url,
        )
        return "skipped"

    try:
        original_bytes = await _download(client, original_url)
        public_url = await upload(original_bytes, key, settings)
        verify_bytes = await _download(client, public_url)
    except (httpx.HTTPError, CoverGenerationError, ClientError) as exc:
        _logger.warning(
            "backfill_row_failed",
            storybook_id=row.storybook_id,
            version=row.version,
            error=str(exc),
        )
        return "failed"

    # #CRITICAL: data integrity: never write a new cover_image_url unless the
    # bytes served back from R2 are byte-for-byte identical to what was
    # downloaded from Supabase; a silently-truncated or corrupted upload must
    # never replace a working (if soon-to-be-deprecated) Supabase URL.
    # #VERIFY: test_migrate_row_verification_mismatch_leaves_row_untouched.
    if verify_bytes != original_bytes:
        _logger.warning(
            "backfill_verification_mismatch",
            storybook_id=row.storybook_id,
            version=row.version,
        )
        return "failed"

    row.cover_image_url = f"{public_url}?v={int(time.time())}"
    await session.commit()
    _logger.info(
        "backfill_row_migrated",
        storybook_id=row.storybook_id,
        version=row.version,
        new_url=row.cover_image_url,
    )
    return "migrated"


async def backfill(
    *,
    dry_run: bool = False,
    settings: Settings = _settings,
    session_factory: Callable[[], AsyncSession] = get_session,
    upload: Callable[[bytes, str, Settings], Awaitable[str]] = upload_cover,
) -> dict[str, int]:
    """Run one backfill pass over every StorybookVersion row with a cover URL.

    Selects all ``StorybookVersion`` rows with a non-null ``cover_image_url``,
    classifies each, and migrates every ``"supabase"``-classified candidate
    to R2 (or, in dry-run mode, logs what would be migrated without any
    network call or database write). Rows already on R2 (``"r2"``) or with an
    unrecognized URL shape (``"other"``) are skipped and not counted as
    candidates.

    Args:
        dry_run: When True, do not download/upload/write anything; only log
            each candidate and count it as skipped.
        settings: App settings (R2 public base URL for classification, and
            the settings ``upload`` needs for a real R2 upload). Defaults to
            the process-wide settings singleton.
        session_factory: Callable returning a fresh AsyncSession usable as an
            async context manager. Defaults to ``get_session``; tests inject
            a fake so no real database connection is required.
        upload: The R2 upload callable. Defaults to the real
            ``covers.storage.upload_cover``; tests substitute a fake.

    Returns:
        A dict with integer counts under the keys "candidates", "migrated",
        "skipped", and "failed".
    """
    counts = {"candidates": 0, "migrated": 0, "skipped": 0, "failed": 0}

    async with (
        httpx.AsyncClient(
            headers={"User-Agent": _BROWSER_USER_AGENT},
            timeout=_DOWNLOAD_TIMEOUT_SECONDS,
        ) as client,
        session_factory() as session,
    ):
        result = await session.scalars(
            select(StorybookVersion).where(
                StorybookVersion.cover_image_url.is_not(None)
            )
        )
        rows = result.all()
        for row in rows:
            url = row.cover_image_url
            if url is None:
                continue
            classification = classify_cover_url(url, settings.r2_public_base_url)
            if classification != "supabase":
                continue
            counts["candidates"] += 1
            outcome = await migrate_row(
                row,
                session=session,
                client=client,
                settings=settings,
                dry_run=dry_run,
                upload=upload,
            )
            counts[outcome] += 1

    return counts


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the backfill script.

    Args:
        argv: Argument list to parse, or None to use ``sys.argv[1:]``.

    Returns:
        The parsed ``argparse.Namespace`` (has a ``dry_run: bool`` attribute).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "List candidates and log what would be migrated, without "
            "downloading, uploading, or writing to the database."
        ),
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for the cover backfill script."""
    setup_logging(level="INFO", json_logs=False, include_correlation=False)
    args = _parse_args()
    counts = asyncio.run(backfill(dry_run=args.dry_run, settings=_settings))
    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(
        f"[{mode}] cover backfill summary: "
        f"candidates={counts['candidates']} migrated={counts['migrated']} "
        f"skipped={counts['skipped']} failed={counts['failed']}"
    )


if __name__ == "__main__":
    main()
