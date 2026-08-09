"""ADR-022 Tier 1 RLS enforcement, exercised as the NOBYPASSRLS ``cyo_api`` role.

These tests are the database-floor counterpart to the app-layer IDOR sweeps:
where those prove FastAPI's ``authorize_family`` refuses a cross-family read,
these prove that even if the app layer were bypassed, a Tier 1 table's RLS
policy filters rows by the caller's ``app.family_id`` context. They connect as
the least-privilege ``cyo_api`` role production uses, because the default
superuser fixtures hold BYPASSRLS and would render every policy invisible.

Real-migration schema, not ORM ``create_all``: the ADR-022 policies and the
``ENABLE ROW LEVEL SECURITY`` they depend on live in ``supabase/migrations``,
never in ``Base.metadata``. So the ``engine``/``sessions`` fixtures (tables
only) could never make these assertions bite. Each test therefore builds a
fresh migrated database via ``migrate_and_connect_as`` (the same helper
``test_rls_service_roles.py`` and the schema-parity gate use), which runs the
full migration chain and hands back both an owner DSN (RLS-bypassing, to seed
baseline rows) and a ``cyo_api`` DSN (RLS-subject, to assert enforcement).

The three enforcement assertions are the fail-closed keystone (no context =>
zero rows), the positive per-family scope (context => only own family), and
the admin escape hatch (``app.is_admin='true'`` => all families), which
together pin every branch of the ``family_scoped`` policy predicate.
``test_cyo_api_role_is_not_bypassrls`` guards the one role property the whole
suite rests on: were ``cyo_api`` ever BYPASSRLS, every assertion below would
pass-through and silently prove nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.api import deps
from cyo_adventure.api.deps import Role, _device_principal, require_principal
from cyo_adventure.core.database import apply_family_rls_context
from cyo_adventure.core.device_grant import mint_device_grant_token
from cyo_adventure.db.models import Character, DeviceGrant, Family, User
from cyo_adventure.db.models import ChildProfile as ChildProfileModel
from tests.integration._migration_utils import migrate_and_connect_as

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ADR-021 least-privilege role the FOR-cyo_api Tier 1 policy targets. The tests
# MUST connect as this exact role: a policy is role-scoped, so any other
# NOBYPASSRLS role would match no policy and see zero rows for the wrong reason.
_CYO_API_ROLE = "cyo_api"

# ADR-022 candidate Tier 1 table: children's PII, hard NOT NULL family_id,
# never crosses families. The canonical table the enforcement contract targets.
_TIER1_TABLE = "child_profile"

# ADR-028 Tier 1 table: a persistent character carries a denormalized
# family_id (see supabase/migrations/20260806120000_add_persistent_characters.sql),
# so it gets the same family_scoped policy as child_profile above.
_CHARACTER_TABLE = "character"


@dataclass(frozen=True)
class _Tier1Env:
    """A migrated database seeded with two families, reachable as ``cyo_api``."""

    sessions: async_sessionmaker[AsyncSession]
    family_a: uuid.UUID
    family_b: uuid.UUID
    # An unrevoked device grant belonging to family A, plus the guardian that
    # minted it. Seeded through the owner connection like every other baseline
    # row, so it exists regardless of policy and only RLS decides visibility.
    grant_jti: uuid.UUID
    grant_authorized_by: uuid.UUID
    # Family A's seeded child profile ids, so the guardian-branch resolution
    # test can assert on the exact set require_principal returns, not merely
    # that it is non-empty. TWO of them deliberately: with a single profile,
    # `== frozenset({profile_a})`, `len(...) == 1` and "resolved something"
    # are indistinguishable, so a partial-resolution defect would pass.
    profile_a: uuid.UUID
    profile_a2: uuid.UUID
    # Family B's profile, so the cross-family test can assert it is ABSENT
    # from a family A principal rather than only that family A's is present.
    profile_b: uuid.UUID


@pytest_asyncio.fixture
async def tier1_env(pg_url: str) -> AsyncIterator[_Tier1Env]:
    """Build a migrated DB, seed families A and B, yield a ``cyo_api`` factory.

    Baseline rows are seeded through the RLS-bypassing owner connection so that
    BOTH families' child profiles exist regardless of any policy; the tests
    then read through the NOBYPASSRLS ``cyo_api`` connection, where the Tier 1
    ``family_scoped`` policy is what decides which of those rows are visible.
    """
    admin_url, role_url = await migrate_and_connect_as(
        pg_url, "rls_tier1_enforcement", _CYO_API_ROLE
    )
    family_a = uuid.uuid4()
    family_b = uuid.uuid4()
    grant_jti = uuid.uuid4()

    admin_engine = create_async_engine(admin_url, poolclass=NullPool)
    admin_sessions = async_sessionmaker(admin_engine, expire_on_commit=False)
    try:
        async with admin_sessions() as session:
            session.add_all(
                [
                    Family(id=family_a, name="Family A"),
                    Family(id=family_b, name="Family B"),
                ]
            )
            await session.flush()
            guardian = User(
                family_id=family_a, role="guardian", authn_subject="guardian-rls-a"
            )
            # A dual-role adult in the SAME family: base role guardian plus the
            # orthogonal admin capability. Its context sets app.is_admin='true',
            # which satisfies the Tier 1 policy's second disjunct for every row
            # in child_profile, so this account is the one that proves
            # _resolve_profiles' own family_id filter still scopes the result.
            guardian_admin = User(
                family_id=family_a,
                role="guardian",
                is_admin=True,
                authn_subject="guardian-admin-rls-a",
            )
            guardian_b = User(
                family_id=family_b, role="guardian", authn_subject="guardian-rls-b"
            )
            session.add_all([guardian, guardian_admin, guardian_b])
            profile_a = ChildProfileModel(
                family_id=family_a, display_name="Reader A", age_band="8-11"
            )
            profile_a2 = ChildProfileModel(
                family_id=family_a, display_name="Reader A2", age_band="5-7"
            )
            profile_b = ChildProfileModel(
                family_id=family_b, display_name="Reader B", age_band="8-11"
            )
            session.add_all([profile_a, profile_a2, profile_b])
            await session.flush()
            session.add(
                DeviceGrant(
                    family_id=family_a,
                    authorized_by=guardian.id,
                    jti=grant_jti,
                    expires_at=datetime.now(UTC) + timedelta(days=90),
                )
            )
            # ADR-028: a character per family, so the character table's own
            # family_scoped policy (identical shape to child_profile's) has
            # rows in both families to prove it filters, not just that it
            # runs. child_profile_id is a real FK to a profile above, so its
            # family_id must (and does) match that profile's family_id; the
            # composite fk_character_profile_family constraint would reject a
            # mismatched pair even at the owner (BYPASSRLS) connection.
            # profile_a2 deliberately gets none: the character count must not
            # track the profile count, or the admin cross-family assertion
            # below would silently double as an assertion about the seeding.
            session.add_all(
                [
                    Character(
                        child_profile_id=profile_a.id,
                        family_id=family_a,
                        name="Aria",
                        archetype="scout",
                        look="avatar_01",
                    ),
                    Character(
                        child_profile_id=profile_b.id,
                        family_id=family_b,
                        name="Bram",
                        archetype="guardian",
                        look="avatar_02",
                    ),
                ]
            )
            await session.commit()
            grant_authorized_by = guardian.id
            profile_a_id = profile_a.id
            profile_a2_id = profile_a2.id
            profile_b_id = profile_b.id
    finally:
        await admin_engine.dispose()

    api_engine = create_async_engine(role_url, poolclass=NullPool)
    api_sessions = async_sessionmaker(api_engine, expire_on_commit=False)
    try:
        yield _Tier1Env(
            sessions=api_sessions,
            family_a=family_a,
            family_b=family_b,
            grant_jti=grant_jti,
            grant_authorized_by=grant_authorized_by,
            profile_a=profile_a_id,
            profile_a2=profile_a2_id,
            profile_b=profile_b_id,
        )
    finally:
        await api_engine.dispose()


async def test_cyo_api_role_is_not_bypassrls(tier1_env: _Tier1Env) -> None:
    """The role the suite connects as must not bypass RLS, or every policy is moot.

    Guards the single property the whole enforcement suite rests on: if
    ``cyo_api`` were ever provisioned (here or in production) with BYPASSRLS,
    the tests below would pass-through and silently prove nothing.
    """
    async with tier1_env.sessions() as session:
        bypass = (
            await session.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).scalar_one()
    assert bypass is False


async def test_tier1_unset_context_returns_zero_rows(tier1_env: _Tier1Env) -> None:
    """With no ``app.family_id`` set, a Tier 1 table must expose zero rows.

    The fail-closed keystone (ADR-022): the fixture commits child profiles for
    families A and B, but a ``cyo_api`` caller that never set its family context
    matches the policy's ``family_id = current_setting(...)`` predicate against
    NULL, which is never true, so it sees nothing rather than every family's
    children. This is the one assertion ``test_rls_service_roles.py`` cannot
    make, because that test always sets context before it reads.
    """
    async with tier1_env.sessions() as session:
        count = (
            await session.execute(text(f"SELECT count(*) FROM {_TIER1_TABLE}"))  # noqa: S608
        ).scalar_one()
    assert count == 0


async def test_tier1_context_scopes_reads_to_caller_family(
    tier1_env: _Tier1Env,
) -> None:
    """Setting ``app.family_id`` exposes only the caller's own family rows.

    The positive counterpart to the fail-closed test, driven through the
    production helper (``apply_family_rls_context``) rather than a raw
    ``set_config`` so the request path's exact mechanism is what is exercised:
    with the context set to family A, family A's own child profile is visible
    and family B's is not. ``set_config(..., true)`` is transaction-local and
    the session autobegins a transaction on first execute, so the setting and
    the read share one transaction.
    """
    async with tier1_env.sessions() as session:
        await apply_family_rls_context(
            session, family_id=tier1_env.family_a, is_admin=False
        )
        visible = (
            (await session.execute(text(f"SELECT family_id FROM {_TIER1_TABLE}")))  # noqa: S608
            .scalars()
            .all()
        )
    assert visible, "family A's own profile must be visible with its context set"
    assert all(str(fid) == str(tier1_env.family_a) for fid in visible), (
        "a foreign family's rows leaked past the Tier 1 policy"
    )


async def test_tier1_admin_context_reads_across_families(
    tier1_env: _Tier1Env,
) -> None:
    """The ``app.is_admin='true'`` escape hatch reads across all families.

    ADR-022's sole cross-family reach in the predicate (ADR-016 admin
    moderation): an admin principal sets ``is_admin=True`` and sees BOTH
    families' profiles, where a same-family non-admin (the test above) sees
    only its own. Pins the ``OR current_setting('app.is_admin', true) = 'true'``
    branch that a fail-closed-only suite would leave unexercised.

    Asserts on the DISTINCT families reached, not on a row count: the claim is
    "reads across families", which is independent of how many profiles the
    fixture happens to seed per family, and a bare count silently doubles as
    an assertion about the seeding.
    """
    async with tier1_env.sessions() as session:
        await apply_family_rls_context(
            session, family_id=tier1_env.family_a, is_admin=True
        )
        visible = (
            (await session.execute(text(f"SELECT family_id FROM {_TIER1_TABLE}")))  # noqa: S608
            .scalars()
            .all()
        )
    assert {str(fid) for fid in visible} >= {
        str(tier1_env.family_a),
        str(tier1_env.family_b),
    }, "the admin escape hatch must read across families"


async def test_character_unset_context_returns_zero_rows(
    tier1_env: _Tier1Env,
) -> None:
    """ADR-028: with no ``app.family_id`` set, ``character`` exposes zero rows.

    The same fail-closed keystone as ``test_tier1_unset_context_returns_zero_rows``,
    pinned separately for ``character`` because it is a distinct table with its
    own ``family_scoped`` policy (added by
    supabase/migrations/20260806120000_add_persistent_characters.sql); a policy
    typo on this table would not be caught by the child_profile assertion above.
    """
    async with tier1_env.sessions() as session:
        count = (
            await session.execute(text(f"SELECT count(*) FROM {_CHARACTER_TABLE}"))  # noqa: S608
        ).scalar_one()
    assert count == 0


async def test_character_context_scopes_reads_to_caller_family(
    tier1_env: _Tier1Env,
) -> None:
    """ADR-028: setting ``app.family_id`` exposes only the caller's own character.

    The positive counterpart to the fail-closed test above: with the context
    set to family A, family A's own character is visible and family B's is not.
    """
    async with tier1_env.sessions() as session:
        await apply_family_rls_context(
            session, family_id=tier1_env.family_a, is_admin=False
        )
        visible = (
            (
                await session.execute(
                    text(f"SELECT family_id FROM {_CHARACTER_TABLE}")  # noqa: S608
                )
            )
            .scalars()
            .all()
        )
    assert visible, "family A's own character must be visible with its context set"
    assert all(str(fid) == str(tier1_env.family_a) for fid in visible), (
        "a foreign family's character leaked past the Tier 1 policy"
    )


async def test_character_admin_context_reads_across_families(
    tier1_env: _Tier1Env,
) -> None:
    """ADR-028: the ``app.is_admin='true'`` escape hatch reads across families.

    Pins the same cross-family admin branch as
    ``test_tier1_admin_context_reads_across_families``, on ``character``'s own
    policy rather than ``child_profile``'s. Asserts on the DISTINCT families
    reached rather than a row count, for the reason that test states: a count
    silently doubles as an assertion about how many characters the fixture
    seeds per family.
    """
    async with tier1_env.sessions() as session:
        await apply_family_rls_context(
            session, family_id=tier1_env.family_a, is_admin=True
        )
        visible = (
            (
                await session.execute(
                    text(f"SELECT family_id FROM {_CHARACTER_TABLE}")  # noqa: S608
                )
            )
            .scalars()
            .all()
        )
    assert {str(fid) for fid in visible} >= {
        str(tier1_env.family_a),
        str(tier1_env.family_b),
    }, "the admin escape hatch must read across families"


async def test_device_grant_invisible_without_context(tier1_env: _Tier1Env) -> None:
    """A bare device_grant lookup with no context sees nothing (the regression).

    Pins the exact shape of the 2026-08-02 staging outage. ``device_grant`` is
    Tier 1, so a ``cyo_api`` caller that has not set ``app.family_id`` matches
    the policy predicate against NULL and gets ZERO ROWS rather than an error.
    That silence is what made the bug so expensive to find: the auth path read
    it as "this grant was never minted" and returned 401, while the row sat
    plainly visible to any ``psql`` session connected as the BYPASSRLS owner.

    Kept as its own test, separate from the passing case below, so a future
    change that quietly widens the policy fails HERE rather than leaving the
    positive test green for the wrong reason.
    """
    async with tier1_env.sessions() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM device_grant WHERE jti = :jti"),
                {"jti": str(tier1_env.grant_jti)},
            )
        ).scalar_one()
    assert count == 0, (
        "device_grant must stay fail-closed without context; if this row is "
        "visible the Tier 1 policy was weakened, not the auth path fixed"
    )


async def test_device_principal_resolves_under_tier1_rls(
    tier1_env: _Tier1Env,
) -> None:
    """``_device_principal`` must resolve a live grant as the NOBYPASSRLS role.

    The end-to-end counterpart to the test above, and the only configuration
    that ever reproduced the bug: the owner-connected fixtures elsewhere in the
    suite bypass RLS, so they authenticated a device token happily for the two
    weeks staging could not. Exercising the real function (not a hand-rolled
    query) is the point, since the defect was in WHERE the production code set
    its RLS context, not in the SQL it issued.
    """
    token, _ = mint_device_grant_token(
        family_id=tier1_env.family_a,
        authorized_by=tier1_env.grant_authorized_by,
        jti=tier1_env.grant_jti,
    )
    async with tier1_env.sessions() as session:
        principal = await _device_principal(session, token)
    assert principal.role is Role.DEVICE
    assert principal.family_id == tier1_env.family_a
    assert principal.profile_ids == frozenset()


async def test_child_profile_invisible_without_context(tier1_env: _Tier1Env) -> None:
    """A bare child_profile lookup for family A with no context sees nothing.

    Mirrors ``test_device_grant_invisible_without_context`` for the guardian
    branch's Tier 1 read: ``child_profile`` is Tier 1, so a ``cyo_api`` caller
    that never set ``app.family_id`` matches the policy predicate against NULL
    and gets ZERO ROWS, exactly as ``_resolve_profiles`` did when
    ``require_principal`` called it before applying the RLS context. Kept
    separate from the positive resolution test below so a future policy
    widening fails HERE rather than leaving that test green for the wrong
    reason.

    Deliberately narrower than ``test_tier1_unset_context_returns_zero_rows``
    above, which already asserts an unfiltered ``count(*)`` on the same table
    is zero. The added ``WHERE family_id`` is the point: it pins the exact
    shape ``_resolve_profiles`` issues, so a policy that started admitting
    rows for a NAMED family (rather than for all families) would fail here
    while the unfiltered assertion stayed green.
    """
    async with tier1_env.sessions() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM child_profile WHERE family_id = :family_id"),
                {"family_id": str(tier1_env.family_a)},
            )
        ).scalar_one()
    assert count == 0, (
        "child_profile must stay fail-closed without context; if this row is "
        "visible the Tier 1 policy was weakened, not the auth path fixed"
    )


async def test_guardian_principal_resolves_profiles_under_tier1_rls(
    tier1_env: _Tier1Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``require_principal``'s guardian branch must resolve profiles under Tier 1 RLS.

    The end-to-end counterpart to the device test above, for the OTHER
    pre-cutover-invisible defect: the guardian branch of ``require_principal``
    calls ``_resolve_profiles`` (a Tier 1 ``child_profile`` read) BEFORE it
    applied ``apply_family_rls_context``, so every guardian resolved an empty
    ``profile_ids`` once ``cyo_api`` became NOBYPASSRLS in production (the
    2026-08-04 cutover, UW-A03). Exercising the real function is the point,
    not a hand-rolled query, since the defect was in WHERE
    ``require_principal`` set its RLS context relative to its own Tier 1
    read, not in the SQL ``_resolve_profiles`` issues.

    Only the token-verification seam is neutralised (routing to the guardian
    branch and resolving the subject), never any RLS, role, or policy
    behaviour: the session still connects as the NOBYPASSRLS ``cyo_api`` role
    from ``tier1_env``, and the Tier 1 policy on ``child_profile`` is fully
    live.
    """
    monkeypatch.setattr(deps, "unverified_audience", lambda _token: None)

    async def _fake_resolve_subject(_token: str) -> str:
        return "guardian-rls-a"

    monkeypatch.setattr(deps, "_resolve_subject", _fake_resolve_subject)

    async with tier1_env.sessions() as session:
        principal = await require_principal(
            session=session, authorization="Bearer irrelevant-once-routed"
        )

    assert principal.role is Role.GUARDIAN
    assert principal.family_id == tier1_env.family_a
    assert principal.profile_ids == frozenset(
        {tier1_env.profile_a, tier1_env.profile_a2}
    ), (
        "BOTH of the guardian's own family profiles must resolve; an empty "
        "set here is the production defect (_resolve_profiles ran before the "
        "RLS context was applied) and a partial set means the context was "
        "applied but scopes more narrowly than the family"
    )


async def test_dual_role_guardian_admin_still_scoped_to_own_family(
    tier1_env: _Tier1Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An adult holding guardian + admin resolves only their OWN family.

    The dual-role account is the case where the Tier 1 policy stops scoping
    anything: ``apply_family_rls_context`` sets ``app.is_admin='true'``, which
    satisfies the policy's second disjunct
    (``current_setting('app.is_admin', true) = 'true'``) for EVERY row in
    ``child_profile``, across all families. What keeps the result correct is
    then purely application-level, the ``ChildProfile.family_id ==
    user.family_id`` filter inside ``_resolve_profiles``.

    So this test pins the layer the database is not defending. Deleting that
    WHERE clause would leave every other test in this module green and only
    fail here, which is exactly the regression worth catching: a dual-role
    adult silently resolving every family's children.
    """
    monkeypatch.setattr(deps, "unverified_audience", lambda _token: None)

    async def _fake_resolve_subject(_token: str) -> str:
        return "guardian-admin-rls-a"

    monkeypatch.setattr(deps, "_resolve_subject", _fake_resolve_subject)

    async with tier1_env.sessions() as session:
        principal = await require_principal(
            session=session, authorization="Bearer irrelevant-once-routed"
        )

    assert principal.is_admin is True, (
        "fixture drift: this test is meaningless unless the account actually "
        "carries the admin capability that opens the policy's escape hatch"
    )
    assert principal.profile_ids == frozenset(
        {tier1_env.profile_a, tier1_env.profile_a2}
    ), (
        "a dual-role adult must still resolve only their own family; the RLS "
        "policy admits every row for app.is_admin='true', so seeing family "
        "B's profile here means _resolve_profiles' family_id filter is gone"
    )
    assert tier1_env.profile_b not in principal.profile_ids


async def test_guardian_principal_does_not_resolve_another_family(
    tier1_env: _Tier1Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Family B's guardian resolves family B's profiles and none of family A's.

    The positive test above proves the context is applied; on its own it
    cannot distinguish "scoped to family A" from "scoped to nothing at all",
    because family A is the only family it ever resolves. Running the same
    real ``require_principal`` for the OTHER family is what makes the
    assertion directional: the two tests together pin that ``profile_ids``
    tracks the caller's family rather than returning a fixed set.
    """
    monkeypatch.setattr(deps, "unverified_audience", lambda _token: None)

    async def _fake_resolve_subject(_token: str) -> str:
        return "guardian-rls-b"

    monkeypatch.setattr(deps, "_resolve_subject", _fake_resolve_subject)

    async with tier1_env.sessions() as session:
        principal = await require_principal(
            session=session, authorization="Bearer irrelevant-once-routed"
        )

    assert principal.family_id == tier1_env.family_b
    assert principal.profile_ids == frozenset({tier1_env.profile_b}), (
        "family B's guardian must resolve exactly family B's profile"
    )
    assert not principal.profile_ids & {tier1_env.profile_a, tier1_env.profile_a2}, (
        "family A's profiles must never appear in family B's principal"
    )
