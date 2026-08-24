"""The at-rest half of the D1 family-lane rule (`UW-C350`(b)).

``20260823160000_constrain_allowlist_enabled_to_the_family_lane.sql`` adds
``ck_provider_model_allowlist_enabled_family_lane``, which says: an allowlist
row whose provider is outside the family lane may EXIST, but may not be
ENABLED. These tests build a database from the whole
``supabase/migrations/*.sql`` chain (so the constraint is judged in the
company of the rows the seed migrations actually leave behind) and exercise
the predicate from the outside, through raw SQL rather than through the API
router or the ORM, because a non-API writer is the only thing this constraint
exists to stop.

Four claims, one test each:

1. An ENABLED row naming a forbidden provider is rejected.
2. A DISABLED row naming the same provider is accepted, which is not a
   loophole but the design ``20260823140000`` depends on (`AL-589`).
3. The rows the migration chain seeds satisfy the constraint, i.e. the ALTER
   does not fail on apply against a real database.
4. The SQL literals in the constraint still agree with the Python constants
   they were copied from.

Test 4 is the drift detector. Per `AL-591`, a test that reads its expectation
from the same source as the code under test cannot discriminate; this one
reads ``FAMILY_LANE_PROVIDERS`` and ``ALLOWLIST_PROVIDERS`` from the Python
source and compares them against text Postgres deparsed from the migration,
which are genuinely two sources. Editing either constant alone fails it, and
so does editing the migration alone.
"""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.generation.allowlist import ALLOWLIST_PROVIDERS
from cyo_adventure.generation.provider import FAMILY_LANE_PROVIDERS
from tests.integration._migration_utils import create_migrated_database

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CONSTRAINT = "ck_provider_model_allowlist_enabled_family_lane"

# The provider the whole rule turns on: allowlistable (it is in
# ALLOWLIST_PROVIDERS, so the sibling provider CHECK admits it) but not
# family-lane permitted. Asserted rather than assumed in each test that uses
# it, so a revert of the D1 ruling fails these tests at their premise instead
# of quietly turning them into tests of nothing.
_FORBIDDEN_PROVIDER = "anthropic"

# Every quoted literal inside a deparsed CHECK expression. The constraint's
# only string literals ARE its permitted provider names, so this captures the
# whole permitted set; a literal added for some other purpose would show up
# here and fail the comparison loudly rather than be skipped.
_SQL_LITERAL_RE = re.compile(r"'([^']*)'")

_INSERT = text(
    "INSERT INTO provider_model_allowlist "
    "(id, provider, model_id, enabled, display_name) "
    "VALUES (:id, :provider, :model_id, :enabled, :display_name)"
)


def _expected_permitted_providers() -> list[str]:
    """The provider set an ENABLED allowlist row may name, derived from Python.

    Not ``FAMILY_LANE_PROVIDERS`` itself: that set contains ``mock``, which
    the sibling ``ck_provider_model_allowlist_provider`` constraint keeps out
    of this table entirely (a CI-only test double is never a billing backend).
    The set the constraint may legally name is therefore the intersection of
    the two, and naming ``mock`` in it would be dead text that reads as a
    permission.

    Returns:
        The permitted provider names, sorted.
    """
    return sorted(FAMILY_LANE_PROVIDERS & set(ALLOWLIST_PROVIDERS))


def _row_params(*, provider: str, model_id: str, enabled: bool) -> dict[str, object]:
    """Build bind parameters for one allowlist row.

    Args:
        provider: The row's provider name.
        model_id: The row's provider-native model id.
        enabled: The enabled state to write.

    Returns:
        A mapping suitable for ``_INSERT``.
    """
    return {
        "id": uuid.uuid4(),
        "provider": provider,
        "model_id": model_id,
        "enabled": enabled,
        "display_name": "written by raw SQL, bypassing the admin API",
    }


async def _constraint_definition(mig_url: str) -> str:
    """Read the live deparsed definition of the family-lane CHECK.

    Args:
        mig_url: URL of a database built by ``create_migrated_database``.

    Returns:
        The ``pg_get_constraintdef`` text for the constraint.

    Raises:
        AssertionError: If the migration chain left no such constraint.
    """
    engine = create_async_engine(mig_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            found = await conn.scalar(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = 'public.provider_model_allowlist'::regclass "
                    "AND conname = :name"
                ),
                {"name": _CONSTRAINT},
            )
    finally:
        await engine.dispose()
    assert found is not None, (
        f"{_CONSTRAINT} is absent after applying the full migration chain; "
        "20260823160000_constrain_allowlist_enabled_to_the_family_lane.sql "
        "did not take effect"
    )
    return str(found)


async def test_an_enabled_forbidden_provider_row_is_rejected(pg_url: str) -> None:
    """A forbidden provider cannot be written enabled, by INSERT or by UPDATE.

    Both verbs matter and neither implies the other. A CHECK is evaluated per
    candidate row, so the INSERT covers a fresh row written by a seed script
    or a replay of the original seed migration after a DELETE (the `AL-589`
    shape), and the UPDATE covers the specific move ``20260823140000`` exists
    to prevent: re-enabling one of the two rows it withdrew.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres
            URL fixture (``tests/integration/conftest.py``).
    """
    assert _FORBIDDEN_PROVIDER not in FAMILY_LANE_PROVIDERS
    assert _FORBIDDEN_PROVIDER in ALLOWLIST_PROVIDERS

    mig_url = await create_migrated_database(pg_url, "c350_enabled_rejected")
    engine = create_async_engine(mig_url, poolclass=NullPool)
    try:
        # Params and statement built OUTSIDE the raises blocks below. S5778
        # allows exactly one invocation in the body, and the reason is the
        # point of the test: if `_row_params` or `text` raised, a block
        # containing them would pass without `conn.execute` ever running, so
        # the constraint would go unproven. Same failure family as `AL-592`,
        # one layer down: there the wrong CONSTRAINT can satisfy the
        # assertion, here the wrong CALL can.
        insert_params = _row_params(
            provider=_FORBIDDEN_PROVIDER,
            model_id="claude-opus-9",
            enabled=True,
        )
        reenable = text(
            "UPDATE provider_model_allowlist SET enabled = true "
            "WHERE provider = :provider"
        )

        async with engine.connect() as conn:
            with pytest.raises(IntegrityError) as insert_err:
                await conn.execute(_INSERT, insert_params)
            assert _CONSTRAINT in str(insert_err.value)
            await conn.rollback()

            with pytest.raises(IntegrityError) as update_err:
                await conn.execute(reenable, {"provider": _FORBIDDEN_PROVIDER})
            assert _CONSTRAINT in str(update_err.value)
            await conn.rollback()
    finally:
        await engine.dispose()


async def test_a_disabled_forbidden_provider_row_is_accepted(pg_url: str) -> None:
    """A forbidden provider's row may exist while disabled, and stay editable.

    This is the half that is easy to get wrong in the strict direction. D1
    keeps the direct Anthropic leg legitimate for out-of-band admin content
    generation, and the seed migration's ``ON CONFLICT DO NOTHING`` makes a
    DELETED row come back ENABLED on any replay (`AL-589`), so the durable
    withdrawal is a disabled row. A constraint that rejected those rows would
    make ``20260823140000`` unappliable and would break
    ``scripts/seed_dev_data.py``, which writes every ``DEFAULT_ALLOWLIST`` row
    at its declared ``enabled`` value.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres
            URL fixture.
    """
    mig_url = await create_migrated_database(pg_url, "c350_disabled_accepted")
    engine = create_async_engine(mig_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                _INSERT,
                _row_params(
                    provider=_FORBIDDEN_PROVIDER,
                    model_id="claude-opus-9",
                    enabled=False,
                ),
            )
            # An edit that leaves the row disabled must also pass: the admin
            # surface has to stay able to relabel what was withdrawn.
            await conn.execute(
                text(
                    "UPDATE provider_model_allowlist "
                    "SET display_name = :label WHERE provider = :provider"
                ),
                {
                    "label": "withdrawn, admin lane only",
                    "provider": _FORBIDDEN_PROVIDER,
                },
            )
            disabled = await conn.scalar(
                text(
                    "SELECT count(*) FROM provider_model_allowlist "
                    "WHERE provider = :provider AND enabled IS FALSE"
                ),
                {"provider": _FORBIDDEN_PROVIDER},
            )
        assert disabled is not None
        assert int(disabled) >= 3, (
            "expected the two withdrawn seed rows plus the one inserted here; "
            f"found {disabled}"
        )
    finally:
        await engine.dispose()


async def test_the_seeded_rows_satisfy_the_constraint(pg_url: str) -> None:
    """Applying the whole chain succeeds, and leaves rows on both sides of it.

    ``create_migrated_database`` running to completion IS the proof that no
    pre-existing row violates the new CHECK: the ALTER would abort the chain
    otherwise. The assertions below guard against that proof being vacuous,
    by requiring the table to hold both an enabled permitted row and a
    disabled forbidden one, so an empty or all-disabled table cannot pass.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres
            URL fixture.
    """
    mig_url = await create_migrated_database(pg_url, "c350_seeded_rows")
    engine = create_async_engine(mig_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT provider, model_id, enabled "
                        "FROM provider_model_allowlist ORDER BY provider, model_id"
                    )
                )
            ).all()
    finally:
        await engine.dispose()

    permitted = set(_expected_permitted_providers())
    offenders = [
        (provider, model_id)
        for provider, model_id, enabled in rows
        if enabled and provider not in permitted
    ]
    assert not offenders, f"seeded rows violate {_CONSTRAINT}: {offenders}"

    assert any(enabled for _, _, enabled in rows), "no enabled row was seeded at all"
    assert any(
        provider == _FORBIDDEN_PROVIDER and not enabled for provider, _, enabled in rows
    ), (
        f"no disabled {_FORBIDDEN_PROVIDER} row survives the chain, so this "
        "test would also pass against a constraint that forbade the row "
        "outright"
    )


async def test_the_constraint_literals_match_the_python_lane_constants(
    pg_url: str,
) -> None:
    """The migration's SQL literals still name the Python-derived provider set.

    The constraint has to spell its permitted providers as SQL literals, which
    is a copy of a Python constant living where nothing imports it. This is
    the mechanical tie that makes the copy's drift a failing test rather than
    a stale comment: it compares the literals Postgres deparsed out of the
    applied migration against
    ``FAMILY_LANE_PROVIDERS & set(ALLOWLIST_PROVIDERS)`` read from the source.
    Adding a provider to either constant, or editing the migration alone,
    fails here naming both sides.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres
            URL fixture.
    """
    mig_url = await create_migrated_database(pg_url, "c350_literal_drift")
    definition = await _constraint_definition(mig_url)

    in_sql = sorted(set(_SQL_LITERAL_RE.findall(definition)))
    in_python = _expected_permitted_providers()
    assert in_sql == in_python, (
        f"{_CONSTRAINT} permits {in_sql}, but FAMILY_LANE_PROVIDERS "
        f"({sorted(FAMILY_LANE_PROVIDERS)}) intersected with "
        f"ALLOWLIST_PROVIDERS ({sorted(ALLOWLIST_PROVIDERS)}) is {in_python}. "
        "Update 20260823160000_constrain_allowlist_enabled_to_the_family_lane"
        ".sql and db/models.py::_FAMILY_LANE_ENABLED_PROVIDER_VALUES together, "
        "in a NEW migration (the Supabase CLI tracks applied migrations by "
        "version, not by content, so editing that file is inert)."
    )

    # The predicate must be about the ENABLED state, not about existence. A
    # constraint spelled `provider IN (...)` alone would satisfy the literal
    # comparison above while forbidding the withdrawn rows outright.
    assert "enabled" in definition.lower(), (
        f"{_CONSTRAINT} does not mention `enabled`: {definition}"
    )
