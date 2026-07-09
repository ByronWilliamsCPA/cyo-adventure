"""Admin CRUD for the provider/model allowlist: auth, add, toggle, delete, audit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_URL = "/api/v1/admin/provider-allowlist"


async def test_guardian_gets_403_on_every_verb(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """Non-admin callers are rejected before any read or write.

    Covers all four verbs. The PUT and DELETE calls target an arbitrary
    entry_id: the admin guard runs before the row is looked up, so a
    non-admin gets 403 whether or not the id exists. That ordering is
    exactly what this asserts, guarding against a regression that moved
    the guard after the DB read in the PUT/DELETE handlers.
    """
    missing_id = "00000000-0000-0000-0000-000000000000"
    get_res = await client.get(_URL, headers=auth(seed.guardian_token))
    assert get_res.status_code == 403
    post_res = await client.post(
        _URL,
        json={"provider": "anthropic", "model_id": "claude-opus-4-8"},
        headers=auth(seed.guardian_token),
    )
    assert post_res.status_code == 403
    put_res = await client.put(
        f"{_URL}/{missing_id}",
        json={"enabled": False},
        headers=auth(seed.guardian_token),
    )
    assert put_res.status_code == 403
    delete_res = await client.delete(
        f"{_URL}/{missing_id}", headers=auth(seed.guardian_token)
    )
    assert delete_res.status_code == 403
    async with AsyncSession(engine) as session:
        rows = (await session.scalars(select(ProviderModelAllowlist))).all()
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert rows == []
    assert audits == []


async def test_list_starts_empty(client: AsyncClient, seed: Seed) -> None:
    """A fresh ORM-metadata test schema carries no migration-seeded rows."""
    res = await client.get(_URL, headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert res.json()["rows"] == []


async def test_add_then_list_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """POST creates a row and an audit entry; the row shows up in GET."""
    res = await client.post(
        _URL,
        json={
            "provider": "anthropic",
            "model_id": "claude-opus-4-8",
            "display_name": "Claude Opus 4.8",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["provider"] == "anthropic"
    assert body["enabled"] is True

    listed = await client.get(_URL, headers=auth(seed.admin_token))
    assert len(listed.json()["rows"]) == 1

    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert len(audits) == 1
    assert audits[0].action == "create"
    assert audits[0].old_enabled is None
    assert audits[0].new_enabled is True
    assert audits[0].changed_by == seed.admin_user_id


async def test_add_duplicate_pair_is_409(client: AsyncClient, seed: Seed) -> None:
    """A second POST for the same (provider, model_id) is a conflict, not a second row."""
    body = {"provider": "ollama", "model_id": "qwen2.5:14b"}
    first = await client.post(_URL, json=body, headers=auth(seed.admin_token))
    assert first.status_code == 201
    second = await client.post(_URL, json=body, headers=auth(seed.admin_token))
    assert second.status_code == 409


async def test_add_unknown_provider_is_422(client: AsyncClient, seed: Seed) -> None:
    """A provider outside the fixed enum is rejected at the schema boundary."""
    res = await client.post(
        _URL,
        json={"provider": "claude", "model_id": "claude-sonnet-4-6"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422


async def test_toggle_enabled_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """PUT toggles enabled and writes an audit row with the old/new pairing."""
    created = await client.post(
        _URL,
        json={"provider": "modal", "model_id": "some-modal-model"},
        headers=auth(seed.admin_token),
    )
    entry_id = created.json()["id"]

    res = await client.put(
        f"{_URL}/{entry_id}",
        json={"enabled": False, "display_name": "disabled for maintenance"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert res.json()["display_name"] == "disabled for maintenance"

    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert [a.action for a in audits] == ["create", "update"]
    assert audits[1].old_enabled is True
    assert audits[1].new_enabled is False
    assert audits[1].changed_by == seed.admin_user_id


async def test_delete_removes_row_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """DELETE removes the row and audits it before deleting."""
    created = await client.post(
        _URL,
        json={"provider": "ollama", "model_id": "qwen3:30b"},
        headers=auth(seed.admin_token),
    )
    entry_id = created.json()["id"]

    res = await client.delete(f"{_URL}/{entry_id}", headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert res.json()["rows"] == []

    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert audits[-1].action == "delete"
    assert audits[-1].old_enabled is True
    assert audits[-1].new_enabled is None


async def test_delete_missing_row_is_404(client: AsyncClient, seed: Seed) -> None:
    """Deleting a non-existent id is a 404, not a silent no-op."""
    res = await client.delete(
        f"{_URL}/00000000-0000-0000-0000-000000000000",
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404


async def test_update_missing_row_is_404(client: AsyncClient, seed: Seed) -> None:
    """Updating a non-existent id is a 404."""
    res = await client.put(
        f"{_URL}/00000000-0000-0000-0000-000000000000",
        json={"enabled": False},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404


async def test_db_check_constraints_reject_invalid_values(
    seed: Seed, engine: AsyncEngine
) -> None:
    """The at-rest CHECK constraints reject a bad provider and a bad audit action.

    The API tests above cover the 422 boundary; this pins the DB backstop
    (``ck_provider_model_allowlist_provider`` and
    ``ck_provider_model_allowlist_audit_action``) so a direct ORM write that
    bypasses schema validation fails with IntegrityError instead of persisting a
    value the app can never have produced.
    """
    async with AsyncSession(engine) as session:
        session.add(
            ProviderModelAllowlist(
                provider="not-a-provider", model_id="x", enabled=True
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    # A valid changed_by (real user FK) isolates the action CHECK from the
    # NOT NULL FK, so the IntegrityError below is unambiguously the action guard.
    async with AsyncSession(engine) as session:
        session.add(
            ProviderModelAllowlistAudit(
                provider="anthropic",
                model_id="x",
                action="not-an-action",
                old_enabled=None,
                new_enabled=True,
                changed_by=seed.admin_user_id,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
