"""Cover endpoints: admin gate, enqueue, config guard, status."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.covers.storage import cover_object_key
from cyo_adventure.db.models import StorybookVersion

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CONFIGURED = SimpleNamespace(
    gemini_api_key="g",
    r2_account_id="acct123",
    r2_access_key_id="AKIDEXAMPLE",
    r2_secret_access_key="svc",
    r2_public_base_url="https://images.example.com",
)


def _settings_missing(field: str) -> SimpleNamespace:
    """Build a `_CONFIGURED`-equivalent settings namespace with one field unset."""
    values = dict(vars(_CONFIGURED))
    values[field] = None
    return SimpleNamespace(**values)


# A recognizable stand-in for a real 32-hex-char cover_object_salt.
_SALT = "0123456789abcdef0123456789abcdef"


async def _fake_presign(
    storybook_id: str,
    version: int,
    _settings: object,
    *,
    salt: str | None = None,
    expires_in: int = 3600,
) -> str:
    """Stand in for the R2 presigner, echoing the derived object key.

    `salt` is declared explicitly rather than absorbed into `**kwargs`, and it
    reaches the returned URL via the production `cover_object_key`, so a
    caller that stopped forwarding `row.cover_object_salt` changes the URL a
    test can assert on instead of silently passing.
    """
    return f"https://signed.example.com/{cover_object_key(storybook_id, version, salt)}"


async def test_non_admin_forbidden(
    client: AsyncClient, seed: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _CONFIGURED)
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403


async def test_admin_enqueues(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _CONFIGURED)
    monkeypatch.setattr(
        "cyo_adventure.api.covers.enqueue_cover", lambda *a, **k: "job-1"
    )
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "generating"

    # The response body alone is not proof the console's poll loop will see
    # "generating" on its first read: without a persisted commit, the row
    # stays at its prior status until an RQ worker eventually dequeues the
    # job (10-30s later on a busy queue), so the 2s poll breaks the loop
    # immediately. Re-fetch through a fresh session to prove the write is
    # actually durable, not just reflected in the in-request response.
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        assert row.cover_status == "generating"


@pytest.mark.parametrize(
    "missing_field",
    [
        "gemini_api_key",
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        "r2_public_base_url",
    ],
)
async def test_missing_config_returns_400(
    client: AsyncClient,
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
    missing_field: str,
) -> None:
    monkeypatch.setattr(
        "cyo_adventure.api.covers.settings", _settings_missing(missing_field)
    )
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 400


async def test_request_cover_not_found_returns_404(
    client: AsyncClient, seed: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _CONFIGURED)
    resp = await client.post(
        "/api/v1/storybooks/does-not-exist/versions/1/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 404


async def test_request_cover_already_generating_is_noop(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _CONFIGURED)
    calls: list[object] = []

    def _fake_enqueue(*args: object, **_kwargs: object) -> str:
        calls.append(args)
        return "job"

    monkeypatch.setattr("cyo_adventure.api.covers.enqueue_cover", _fake_enqueue)
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        row.cover_status = "generating"
        await s.commit()
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "generating"
    # An in-flight cover must not enqueue a second (billable) job.
    assert calls == []


async def test_request_cover_enqueue_failure_marks_failed(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _CONFIGURED)

    def _boom(*_args: object, **_kwargs: object) -> str:
        msg = "redis down"
        raise RuntimeError(msg)

    monkeypatch.setattr("cyo_adventure.api.covers.enqueue_cover", _boom)
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    # 502 (UW-A55), not merely ">= 400": the broker being unreachable is an
    # ExternalServiceError, and asserting the exact status is what would catch
    # a regression back to the old undifferentiated 400 fallback. A ">= 400"
    # assertion would pass either way and prove nothing about which one fired.
    assert resp.status_code == 502
    # The row must not be stranded in 'generating' when the enqueue fails.
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        assert row.cover_status == "failed"


async def test_cover_status_admin_returns_status(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "none"


async def test_cover_status_non_admin_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403


async def test_cover_status_not_found_returns_404(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.get(
        "/api/v1/storybooks/does-not-exist/versions/1/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 404


async def test_cover_status_returns_presigned_url_when_pending_review(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An admin reviewer must be able to see a pending cover before deciding
    # whether to approve it; _cover_url deliberately widens the presign gate
    # to "pending_review" (not just "ready") for this admin-only endpoint.
    #
    # The stub takes `salt` explicitly (never **kwargs) and folds it into the
    # URL through the production key builder: a fake that swallowed the salt
    # would pass whether or not api/covers.py forwarded row.cover_object_salt,
    # which is the entire behavior UW-M07's defense in depth rests on.
    monkeypatch.setattr(
        "cyo_adventure.api.covers.generate_presigned_cover_url", _fake_presign
    )
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        row.cover_status = "pending_review"
        row.cover_object_salt = _SALT
        await s.commit()

    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_status"] == "pending_review"
    assert body["cover_url"] == (
        f"https://signed.example.com/{seed.storybook_id}/{seed.version}-{_SALT}.webp"
    )
    # Redundant with the equality above on purpose: this is the assertion that
    # fails loudly if the salt ever stops reaching the presign call.
    assert _SALT in body["cover_url"]


async def test_cover_status_url_uses_the_legacy_key_when_salt_is_null(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row predating cover_object_salt must keep resolving at the unsalted
    key: its object was never renamed in R2, so a salted key would 404."""
    monkeypatch.setattr(
        "cyo_adventure.api.covers.generate_presigned_cover_url", _fake_presign
    )
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        row.cover_status = "pending_review"
        row.cover_object_salt = None
        await s.commit()

    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["cover_url"] == (
        f"https://signed.example.com/{seed.storybook_id}/{seed.version}.webp"
    )


async def test_cover_status_omits_url_when_generating(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A cover mid-generation (or failed, or never requested) must not expose
    # a presigned URL: no object has necessarily been uploaded yet at that key.
    async def _fail_if_called(*_args: object, **_kwargs: object) -> str:
        msg = "must not be called for a non-viewable cover_status"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "cyo_adventure.api.covers.generate_presigned_cover_url", _fail_if_called
    )
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        row.cover_status = "generating"
        await s.commit()

    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_status"] == "generating"
    assert body["cover_url"] is None


# ---------------------------------------------------------------------------
# H2 (security-hardening-plan-2026-07.md): admin cover-approval endpoint.
# A cover cannot reach "ready" (and therefore a child library card, see
# tests/integration/test_library_cover.py) without this endpoint.
# ---------------------------------------------------------------------------


async def test_approve_cover_non_admin_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover/approve",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403


async def test_approve_cover_sets_ready_and_stamps_approver(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        row.cover_status = "pending_review"
        await s.commit()

    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover/approve",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_status"] == "ready"
    assert body["cover_approved_by"] == str(seed.admin_user_id)
    assert body["cover_approved_at"] is not None

    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        assert row.cover_status == "ready"
        assert row.cover_approved_by == seed.admin_user_id
        assert row.cover_approved_at is not None


async def test_approve_cover_not_pending_review_returns_400(
    client: AsyncClient, seed: Seed
) -> None:
    # The seeded row's cover_status defaults to "none": never generated, so
    # nothing is pending an admin's review yet.
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover/approve",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 400


async def test_approve_cover_not_found_returns_404(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.post(
        "/api/v1/storybooks/does-not-exist/versions/1/cover/approve",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 404
