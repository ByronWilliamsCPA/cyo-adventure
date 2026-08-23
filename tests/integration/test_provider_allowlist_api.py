"""Admin CRUD for the provider/model allowlist: auth, add, toggle, delete, audit."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit
from cyo_adventure.generation.provider import FAMILY_LANE_PROVIDERS
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
    """POST creates a row and an audit entry; the row shows up in GET.

    The happy path names ``openrouter`` rather than the direct ``anthropic``
    leg it used to: this endpoint only ever creates ENABLED rows, and D1 forbids
    an enabled row for a provider the family generation lane cannot use, so a
    direct-anthropic POST is now a 422 (see
    ``test_add_a_provider_the_family_lane_forbids_is_422``). The provider is
    incidental to what this test pins; the rejection is not.
    """
    res = await client.post(
        _URL,
        json={
            "provider": "openrouter",
            "model_id": "anthropic/claude-opus-4.8",
            "display_name": "Claude Opus 4.8",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["provider"] == "openrouter"
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
    body = {"provider": "modal", "model_id": "google/gemma-4-26b-a4b-it"}
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
        json={"provider": "modal", "model_id": "google/gemma-4-26b-a4b-it"},
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


async def test_list_tolerates_a_retired_provider_row(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """A row naming a retired provider must not 500 the whole list endpoint.

    ``AllowlistView.provider`` used to be narrowed to ``ProviderName`` (the
    fixed 3-member ``Literal``). ``_view()`` builds that model per row, so a
    single surviving row naming a retired backend (``ollama``, dropped by
    ``ALLOWLIST_PROVIDERS``/``20260818120000_retire_ollama_provider.sql``)
    raised an unhandled ``pydantic.ValidationError`` and turned
    ``GET /api/v1/admin/provider-allowlist`` into a 500, including the read an
    admin would use to find and delete the offending row. This pins the fix:
    ``AllowlistView.provider`` is now a plain ``str``, so the row round-trips.

    The same migration that retired ``ollama`` also narrowed
    ``ck_provider_model_allowlist_provider`` (the ORM CHECK constraint mirrors
    it via ``_ALLOWLIST_PROVIDER_VALUES``) to exactly the three live
    providers, so there is no longer any string that names a retired provider
    yet still satisfies the CHECK: a plain ``session.add(...)`` +
    ``commit()`` with ``provider="ollama"`` raises ``IntegrityError`` before
    the row ever reaches ``_view``. To genuinely exercise ``_view()`` against
    an out-of-``Literal`` value (rather than testing the CHECK, which
    ``test_db_check_constraints_reject_invalid_values`` already covers), the
    constraint is dropped for the duration of this test only, mirroring
    ``test_malformed_min_verdict_row_is_skipped_with_warning`` in
    ``test_threshold_policy_loader.py``: the ``engine`` fixture truncates
    data but not DDL between tests in this worker, so both the row and the
    constraint are restored in ``finally`` to avoid leaking the drop into
    ``test_db_check_constraints_reject_invalid_values`` or any other test
    that runs later in this worker.

    This must fail if ``AllowlistView.provider`` is narrowed back to
    ``ProviderName``: the GET below would then raise ``pydantic.ValidationError``
    instead of returning 200 (the test client's ``ASGITransport`` defaults to
    ``raise_app_exceptions=True``, so the old behavior surfaces as an error
    here rather than a 500 response).
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE provider_model_allowlist "
                "DROP CONSTRAINT ck_provider_model_allowlist_provider"
            )
        )
    try:
        async with AsyncSession(engine) as session:
            session.add(
                ProviderModelAllowlist(
                    provider="ollama",
                    model_id="retired-model",
                    enabled=True,
                )
            )
            await session.commit()

        res = await client.get(_URL, headers=auth(seed.admin_token))
        assert res.status_code == 200
        rows = res.json()["rows"]
        assert any(
            row["provider"] == "ollama" and row["model_id"] == "retired-model"
            for row in rows
        )
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM provider_model_allowlist WHERE provider = 'ollama'")
            )
            await conn.execute(
                text(
                    "ALTER TABLE provider_model_allowlist "
                    "ADD CONSTRAINT ck_provider_model_allowlist_provider "
                    "CHECK (provider IN ('anthropic', 'openrouter', 'modal'))"
                )
            )


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


# ---------------------------------------------------------------------------
# Agreement with the D1 lane ruling at the write boundary (2026-08-23, UW-C346)
# ---------------------------------------------------------------------------
# `tests/unit/test_allowlist.py::
# test_no_enabled_seed_row_names_a_provider_the_family_lane_forbids` pins the
# same property for the code-side seed constant. That guard covers a static
# Python literal only; the rows these endpoints write are what
# `is_enabled_allowlist_pair` actually reads, so the runtime table needs its
# own guard at the point untrusted admin input enters.


async def _withdrawn_anthropic_row(engine: AsyncEngine) -> str:
    """Insert the disabled direct-anthropic row D1's migration leaves behind.

    Written straight through the ORM rather than through ``POST``: after the
    fix the API refuses to create an enabled row for this provider, and this
    is the state the migration actually produces (present, unselectable).

    Args:
        engine: The test container engine.

    Returns:
        str: The new row's id, as it appears in a URL path.
    """
    async with AsyncSession(engine) as session:
        row = ProviderModelAllowlist(
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            enabled=False,
            display_name="Claude Sonnet 4.6 (direct, withdrawn)",
        )
        session.add(row)
        # The id is read BEFORE the commit: ``expire_on_commit`` would expire
        # the instance and re-reading it would attempt IO outside the greenlet
        # context (``MissingGreenlet``). The client-side ``uuid.uuid4`` default
        # is applied at flush, so the value is already there.
        await session.flush()
        entry_id = str(row.id)
        await session.commit()
    return entry_id


async def test_add_a_provider_the_family_lane_forbids_is_422(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """POST cannot create a row for a provider the family lane forbids.

    ``add_allowlist_entry`` hardcodes ``enabled=True``, so a POST naming a
    provider outside ``FAMILY_LANE_PROVIDERS`` can only produce the exact
    incoherence D1 exists to remove: a pair the admin dialog offers, the
    authoring-plan endpoint accepts via ``is_enabled_allowlist_pair``, and
    ``build_provider(lane="family")`` then refuses at job time, so the
    configuration error arrives as a generation failure attributed to the job.

    The precondition assertion is deliberate: if D1 is ever reversed and the
    direct leg is readmitted to the family lane, this test should fail there
    and say why, not silently keep asserting a rule that no longer holds.
    """
    assert "anthropic" not in FAMILY_LANE_PROVIDERS

    res = await client.post(
        _URL,
        json={"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
        headers=auth(seed.admin_token),
    )

    assert res.status_code == 422, res.text
    async with AsyncSession(engine) as session:
        rows = (await session.scalars(select(ProviderModelAllowlist))).all()
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert rows == []
    assert audits == []


async def test_reenabling_a_provider_the_family_lane_forbids_is_422(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """PUT cannot flip a withdrawn row back on.

    The D1 migration disables the two direct-anthropic rows rather than
    deleting them. Without a guard here, one PUT undoes that migration and
    puts the pair back in front of ``is_enabled_allowlist_pair``, which is the
    single read path the authoring-plan endpoint trusts.
    """
    entry_id = await _withdrawn_anthropic_row(engine)

    res = await client.put(
        f"{_URL}/{entry_id}",
        json={"enabled": True},
        headers=auth(seed.admin_token),
    )

    assert res.status_code == 422, res.text
    async with AsyncSession(engine) as session:
        row = await session.get(ProviderModelAllowlist, uuid.UUID(entry_id))
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert row is not None
    assert row.enabled is False
    assert audits == []


async def test_a_withdrawn_row_stays_editable_while_it_stays_disabled(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """The rule is "may exist but may not be enabled", not "may not exist".

    D1 still permits the direct leg for out-of-band admin content generation,
    and the row has to remain expressible so the admin surface can show what
    was withdrawn. So a PUT that leaves the row disabled is a normal update:
    it succeeds, relabels the row, and audits itself like any other.
    """
    entry_id = await _withdrawn_anthropic_row(engine)

    res = await client.put(
        f"{_URL}/{entry_id}",
        json={"enabled": False, "display_name": "withdrawn by D1"},
        headers=auth(seed.admin_token),
    )

    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is False
    assert res.json()["display_name"] == "withdrawn by D1"
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert [a.action for a in audits] == ["update"]
    assert audits[0].old_enabled is False
    assert audits[0].new_enabled is False
