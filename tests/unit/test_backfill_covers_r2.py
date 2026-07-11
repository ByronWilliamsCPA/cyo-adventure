"""Unit tests for scripts/backfill_covers_r2.py (no network, no DB).

scripts/ is not an importable package (no __init__.py, by design; see
per-file-ignores INP for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_seed_staging.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings
    from cyo_adventure.db.models import StorybookVersion

_SPEC = importlib.util.spec_from_file_location(
    "backfill_covers_r2",
    Path(__file__).resolve().parents[2] / "scripts" / "backfill_covers_r2.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
backfill_covers_r2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backfill_covers_r2)

pytestmark = pytest.mark.unit

_R2_BASE = "https://covers.example.com"
_SUPABASE_URL = "https://p.supabase.co/storage/v1/object/public/covers/story-1/1.webp"


def _fake_settings(r2_public_base_url: str | None = _R2_BASE) -> Settings:
    """Build a duck-typed Settings stand-in exposing only r2_public_base_url."""
    return cast("Settings", SimpleNamespace(r2_public_base_url=r2_public_base_url))


def _fake_row(
    *,
    storybook_id: str = "story-1",
    version: int = 1,
    cover_image_url: str = _SUPABASE_URL,
) -> StorybookVersion:
    """Build a duck-typed StorybookVersion row stand-in."""
    return cast(
        "StorybookVersion",
        SimpleNamespace(
            storybook_id=storybook_id,
            version=version,
            cover_image_url=cover_image_url,
        ),
    )


def _ok_response(body: bytes, url: str = "https://example.com/x") -> httpx.Response:
    """Build a real httpx.Response (200) with a request attached."""
    return httpx.Response(200, content=body, request=httpx.Request("GET", url))


def _error_response(
    status_code: int, url: str = "https://example.com/x"
) -> httpx.Response:
    """Build a real httpx.Response with an error status and a request attached."""
    return httpx.Response(status_code, request=httpx.Request("GET", url))


class _FakeAsyncClient:
    """Minimal async-context-manager stand-in for httpx.AsyncClient."""

    def __init__(self, get: AsyncMock) -> None:
        self.get = get

    async def __aenter__(self) -> _FakeAsyncClient:
        """Enter the fake async context, returning self."""
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        """Exit the fake async context without suppressing exceptions."""
        return False


def _patch_httpx_client(get: AsyncMock) -> AbstractContextManager[MagicMock]:
    """Patch backfill_covers_r2.httpx.AsyncClient to hand back a fake client."""
    return patch.object(
        backfill_covers_r2.httpx,
        "AsyncClient",
        return_value=_FakeAsyncClient(get),
    )


def _fake_session_factory(
    rows: list[StorybookVersion],
) -> tuple[Callable[[], AsyncSession], MagicMock]:
    """Build a session_factory + underlying session mock, seeded with rows."""
    session = AsyncMock()
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    factory = cast("Callable[[], AsyncSession]", MagicMock(return_value=session_ctx))
    return factory, session


# ---------------------------------------------------------------------------
# classify_cover_url
# ---------------------------------------------------------------------------


def test_classify_cover_url_supabase_shape_without_query() -> None:
    url = "https://p.supabase.co/storage/v1/object/public/covers/story-1/1.webp"
    assert backfill_covers_r2.classify_cover_url(url, _R2_BASE) == "supabase"


def test_classify_cover_url_supabase_shape_with_query() -> None:
    url = "https://p.supabase.co/storage/v1/object/public/covers/x.webp?v=1"
    assert backfill_covers_r2.classify_cover_url(url, _R2_BASE) == "supabase"


def test_classify_cover_url_r2_shape() -> None:
    url = f"{_R2_BASE}/story-1/1.webp?v=1700000000"
    assert backfill_covers_r2.classify_cover_url(url, _R2_BASE) == "r2"


def test_classify_cover_url_other() -> None:
    url = "https://example.com/some-other-image.png"
    assert backfill_covers_r2.classify_cover_url(url, _R2_BASE) == "other"


def test_classify_cover_url_supabase_shape_when_r2_unconfigured() -> None:
    # r2_public_base_url is None (R2 not configured yet): a Supabase-shaped
    # URL must still classify as "supabase", not crash on the startswith check.
    url = "https://p.supabase.co/storage/v1/object/public/covers/story-1/1.webp"
    assert backfill_covers_r2.classify_cover_url(url, None) == "supabase"


# ---------------------------------------------------------------------------
# migrate_row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_row_happy_path_migrates() -> None:
    row = _fake_row()
    _, session = _fake_session_factory([row])
    get = AsyncMock(
        side_effect=[_ok_response(b"same-bytes"), _ok_response(b"same-bytes")]
    )
    upload = AsyncMock(return_value=f"{_R2_BASE}/story-1/1.webp")

    outcome = await backfill_covers_r2.migrate_row(
        row,
        session=session,
        client=_FakeAsyncClient(get),
        settings=_fake_settings(),
        dry_run=False,
        upload=upload,
    )

    assert outcome == "migrated"
    assert row.cover_image_url is not None
    assert row.cover_image_url.startswith(f"{_R2_BASE}/story-1/1.webp?v=")
    upload.assert_awaited_once_with(b"same-bytes", "story-1/1.webp", _fake_settings())
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_migrate_row_verification_mismatch_leaves_row_untouched() -> None:
    row = _fake_row()
    original_url = row.cover_image_url
    _, session = _fake_session_factory([row])
    get = AsyncMock(
        side_effect=[_ok_response(b"original-bytes"), _ok_response(b"different-bytes")]
    )
    upload = AsyncMock(return_value=f"{_R2_BASE}/story-1/1.webp")

    outcome = await backfill_covers_r2.migrate_row(
        row,
        session=session,
        client=_FakeAsyncClient(get),
        settings=_fake_settings(),
        dry_run=False,
        upload=upload,
    )

    assert outcome == "failed"
    assert row.cover_image_url == original_url
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_row_download_failure_counts_failed() -> None:
    row = _fake_row()
    original_url = row.cover_image_url
    _, session = _fake_session_factory([row])
    get = AsyncMock(return_value=_error_response(404))
    upload = AsyncMock(return_value=f"{_R2_BASE}/story-1/1.webp")

    outcome = await backfill_covers_r2.migrate_row(
        row,
        session=session,
        client=_FakeAsyncClient(get),
        settings=_fake_settings(),
        dry_run=False,
        upload=upload,
    )

    assert outcome == "failed"
    assert row.cover_image_url == original_url
    upload.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_row_upload_failure_counts_failed() -> None:
    row = _fake_row()
    original_url = row.cover_image_url
    _, session = _fake_session_factory([row])
    get = AsyncMock(return_value=_ok_response(b"original-bytes"))
    upload = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "500", "Message": "boom"}}, "PutObject"
        )
    )

    outcome = await backfill_covers_r2.migrate_row(
        row,
        session=session,
        client=_FakeAsyncClient(get),
        settings=_fake_settings(),
        dry_run=False,
        upload=upload,
    )

    assert outcome == "failed"
    assert row.cover_image_url == original_url
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_row_dry_run_returns_skipped_without_io() -> None:
    row = _fake_row()
    original_url = row.cover_image_url
    _, session = _fake_session_factory([row])
    get = AsyncMock()
    upload = AsyncMock()

    outcome = await backfill_covers_r2.migrate_row(
        row,
        session=session,
        client=_FakeAsyncClient(get),
        settings=_fake_settings(),
        dry_run=True,
        upload=upload,
    )

    assert outcome == "skipped"
    assert row.cover_image_url == original_url
    get.assert_not_called()
    upload.assert_not_called()
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# backfill (full pass)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_dry_run_makes_no_writes() -> None:
    row = _fake_row()
    session_factory, session = _fake_session_factory([row])
    get = AsyncMock()
    upload = AsyncMock()

    with _patch_httpx_client(get):
        counts = await backfill_covers_r2.backfill(
            dry_run=True,
            settings=_fake_settings(),
            session_factory=session_factory,
            upload=upload,
        )

    assert counts == {"candidates": 1, "migrated": 0, "skipped": 1, "failed": 0}
    assert row.cover_image_url == _SUPABASE_URL
    upload.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_skips_rows_already_on_r2() -> None:
    row = _fake_row(cover_image_url=f"{_R2_BASE}/story-1/1.webp?v=1700000000")
    session_factory, session = _fake_session_factory([row])
    get = AsyncMock()
    upload = AsyncMock()

    with _patch_httpx_client(get):
        counts = await backfill_covers_r2.backfill(
            dry_run=False,
            settings=_fake_settings(),
            session_factory=session_factory,
            upload=upload,
        )

    assert counts == {"candidates": 0, "migrated": 0, "skipped": 0, "failed": 0}
    assert row.cover_image_url == f"{_R2_BASE}/story-1/1.webp?v=1700000000"
    upload.assert_not_called()
    get.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_ignores_other_shaped_urls() -> None:
    row = _fake_row(cover_image_url="https://example.com/unrelated.png")
    session_factory, session = _fake_session_factory([row])
    get = AsyncMock()
    upload = AsyncMock()

    with _patch_httpx_client(get):
        counts = await backfill_covers_r2.backfill(
            dry_run=False,
            settings=_fake_settings(),
            session_factory=session_factory,
            upload=upload,
        )

    assert counts == {"candidates": 0, "migrated": 0, "skipped": 0, "failed": 0}
    upload.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_happy_path_migrates_candidate() -> None:
    row = _fake_row()
    session_factory, session = _fake_session_factory([row])
    get = AsyncMock(
        side_effect=[_ok_response(b"cover-bytes"), _ok_response(b"cover-bytes")]
    )
    upload = AsyncMock(return_value=f"{_R2_BASE}/story-1/1.webp")

    with _patch_httpx_client(get):
        counts = await backfill_covers_r2.backfill(
            dry_run=False,
            settings=_fake_settings(),
            session_factory=session_factory,
            upload=upload,
        )

    assert counts == {"candidates": 1, "migrated": 1, "skipped": 0, "failed": 0}
    assert row.cover_image_url is not None
    assert row.cover_image_url.startswith(f"{_R2_BASE}/story-1/1.webp?v=")
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_backfill_mixed_rows_only_counts_supabase_as_candidates() -> None:
    supabase_row = _fake_row(storybook_id="s1", version=1)
    r2_row = _fake_row(
        storybook_id="s2",
        version=1,
        cover_image_url=f"{_R2_BASE}/s2/1.webp?v=1700000000",
    )
    other_row = _fake_row(
        storybook_id="s3", version=1, cover_image_url="https://example.com/x.png"
    )
    session_factory, session = _fake_session_factory([supabase_row, r2_row, other_row])
    get = AsyncMock(
        side_effect=[_ok_response(b"cover-bytes"), _ok_response(b"cover-bytes")]
    )
    upload = AsyncMock(return_value=f"{_R2_BASE}/s1/1.webp")

    with _patch_httpx_client(get):
        counts = await backfill_covers_r2.backfill(
            dry_run=False,
            settings=_fake_settings(),
            session_factory=session_factory,
            upload=upload,
        )

    assert counts == {"candidates": 1, "migrated": 1, "skipped": 0, "failed": 0}
    assert r2_row.cover_image_url == f"{_R2_BASE}/s2/1.webp?v=1700000000"
    assert other_row.cover_image_url == "https://example.com/x.png"
    upload.assert_awaited_once()
    session.commit.assert_awaited_once()
