"""Integration tests for POST /story-requests/{id}/authoring-plan."""

from __future__ import annotations

import copy
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from cyo_adventure.db.models import GenerationJob, ProviderModelAllowlist
from cyo_adventure.generation import worker as worker_module
from cyo_adventure.generation.fidelity import parse_fill_directive
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.generation.skeleton_match import candidates_for_cell
from cyo_adventure.generation.worker import run_generation_job
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# A real 13-16 skeleton (a different band from the seeded request's own 10-13
# band), used by the cross-band producer->consumer test below (WS-C PR2 final
# review C1). Mirrors the constants in test_generation_worker.py.
_CROSS_BAND_SKELETON_SLUG = "the-sunspire-ascent"
_CROSS_BAND_SKELETON_BAND = "13-16"
_CROSS_BAND_SKELETON_PATH = (
    Path(__file__).resolve().parents[2]
    / "skeletons"
    / _CROSS_BAND_SKELETON_BAND
    / f"{_CROSS_BAND_SKELETON_SLUG}.json"
)


@pytest.fixture(autouse=True)
def _force_legacy_skeleton_fill(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the two worker-running tests in this module to the legacy fill path.

    Both ``run_generation_job`` tests here drive real catalog skeletons that now
    ship WS-2 theme contracts (one auto-picked by the planner, one the explicit
    ``the-sunspire-ascent`` cross-band override), which would otherwise route the
    worker through the bound (parameterized) dispatch and its extra binding
    provider call the injected ``MockProvider``s do not script; the bind step
    then fails to parse a filled-skeleton response as a slot map and the job
    never reaches the terminal status these tests assert. The bound dispatch has
    dedicated coverage in ``tests/unit/test_worker.py``; these tests cover the
    producer/consumer plan plumbing and cross-band path resolution. Forcing
    ``load_contract_for`` to ``None`` keeps them deterministic regardless of the
    on-disk contract sidecars, mirroring
    ``test_generation_worker.py::_force_legacy_skeleton_fill``. The producer-side
    tests never run the worker, so this patch is a harmless no-op for them.
    """
    monkeypatch.setattr(worker_module, "load_contract_for", lambda *_a, **_k: None)


def _filled_skeleton_json_for(skeleton_path: Path) -> str:
    """Return a JSON string: the given skeleton with every FILL body replaced.

    Mirrors test_generation_worker.py::_filled_skeleton_json_for: each node's
    FILL directive is swapped for placeholder prose sized to the directive's
    declared word target so the filled blob satisfies both the structural gate
    and the Stage 1 fidelity checks the worker runs afterward.
    """
    skeleton = load_skeleton(skeleton_path)
    filled = copy.deepcopy(skeleton)
    for node in cast("list[dict[str, object]]", filled["nodes"]):
        body = node.get("body")
        directive = parse_fill_directive(body) if isinstance(body, str) else None
        if directive is not None:
            words = max(int(directive["words"]), 1)
            node["body"] = " ".join(["word"] * words)
    return json.dumps(filled)


pytestmark = pytest.mark.asyncio

_CREATE = "/api/v1/story-requests"


# The pair every working test in this module names. openrouter, not the
# direct anthropic leg it used to be: an authoring plan is a family-lane
# question, and since D1 (`UW-C346`, `UW-C350`) the read path refuses a
# provider that lane forbids however the row is set. Written as literals, not
# derived from `FAMILY_LANE_PROVIDERS`, so the expectation cannot drift with
# the constant the production code reads (`AL-591`);
# tests/unit/test_allowlist.py::
# test_the_direct_anthropic_provider_is_outside_the_family_lane is what fails
# if the ruling ever changes.
_LANE_OK_PROVIDER = "openrouter"
_LANE_OK_MODEL = "deepseek/deepseek-v4-pro"

# The pair the family lane forbids, seeded ENABLED. No API caller can produce
# this row any more (api/provider_allowlist.py returns 422 for it), so it
# stands for the one thing that still can: a migration, seed script, or raw
# SQL. test_family_lane_forbidden_pair_is_422 is what observes it.
_LANE_FORBIDDEN_PROVIDER = "anthropic"
_LANE_FORBIDDEN_MODEL = "claude-sonnet-4-6"


# The at-rest CHECK that `UW-C350` part (b) adds, naming the same rule. An
# ENABLED row for a forbidden provider now violates it, so the veto test below
# has to remove it to reach the state the read path defends against.
_FAMILY_LANE_CHECK = "ck_provider_model_allowlist_enabled_family_lane"


@pytest_asyncio.fixture(autouse=True)
async def _seed_allowlist(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Seed one enabled allowlist row so automated_provider requests validate.

    Every test in this module either exercises mechanism='automated_provider'
    (which now requires an enabled allowlist pair) or is unaffected by the
    allowlist (mechanism='skill'); seeding one canonical row here keeps every
    test body's literal provider/model working without a per-test insert.
    """
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider=_LANE_OK_PROVIDER, model_id=_LANE_OK_MODEL, enabled=True
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def forbidden_enabled_row(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Put an ENABLED row the family lane forbids into the table, then undo it.

    Two layers have to be stepped around to reach this state, which is the
    measure of how deliberately unreachable it is: the API write path refuses
    to create it (422 since `d1fb0b7b`), and the at-rest CHECK refuses to
    store it (`UW-C350` part (b)). What remains is a database migrated before
    that CHECK existed, or one where it has been dropped, which is exactly the
    case the read-path veto is defence-in-depth for.

    The constraint's own definition is read back from ``pg_constraint`` and
    replayed verbatim on teardown rather than retyped here, so a later change
    to the migration's predicate cannot be silently replaced by a stale copy
    living in this test file. The app talks to its own connection, so unlike
    tests/integration/test_allowlist.py this cannot ride on a rolled-back
    transaction; the row and the constraint are restored explicitly instead.
    """
    async with sessions() as session:
        definition = await session.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = :name"
            ),
            {"name": _FAMILY_LANE_CHECK},
        )
        assert definition is not None, (
            f"{_FAMILY_LANE_CHECK} is absent; this test asserts the read path "
            "still refuses a row the constraint would have blocked, so it has "
            "nothing to prove if the constraint was never there"
        )
        await session.execute(
            text(
                "ALTER TABLE provider_model_allowlist "
                f"DROP CONSTRAINT {_FAMILY_LANE_CHECK}"
            )
        )
        session.add(
            ProviderModelAllowlist(
                provider=_LANE_FORBIDDEN_PROVIDER,
                model_id=_LANE_FORBIDDEN_MODEL,
                enabled=True,
            )
        )
        await session.commit()
    try:
        yield
    finally:
        async with sessions() as session:
            await session.execute(
                text(
                    "DELETE FROM provider_model_allowlist "
                    "WHERE provider = :provider AND model_id = :model_id"
                ),
                {
                    "provider": _LANE_FORBIDDEN_PROVIDER,
                    "model_id": _LANE_FORBIDDEN_MODEL,
                },
            )
            await session.execute(
                text(
                    "ALTER TABLE provider_model_allowlist "
                    f"ADD CONSTRAINT {_FAMILY_LANE_CHECK} {definition}"
                )
            )
            await session.commit()


async def _approved_request_id(client: AsyncClient, seed: Seed, text: str) -> str:
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": text},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    approved = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.admin_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert approved.status_code == 200, approved.text
    return req_id


@asynccontextmanager
async def _session_ctx(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Wrap a session from the factory in a context manager."""
    session = sessions()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _make_session_factory(
    sessions: async_sessionmaker[AsyncSession],
):  # type: ignore[return]
    """Return a callable session factory compatible with worker's session_factory."""

    def factory():  # type: ignore[return-value]
        return _session_ctx(sessions)

    return factory


async def test_fresh_generation_automated_provider_enqueues(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The unchanged path: admin picks fresh_generation, job is queued."""
    req_id = await _approved_request_id(client, seed, "a curious otter")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "queued"
    assert body["skeleton_slug"] is None
    assert body["warnings"] == []

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.status == "queued"


async def test_skeleton_fill_skill_parks_job(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """skeleton_fill + skill parks the job with skeleton + theme_brief metadata."""
    req_id = await _approved_request_id(client, seed, "a lighthouse keeper")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={"method": "skeleton_fill", "mechanism": "skill", "prep_model": "sonnet"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "awaiting_manual_fill"
    assert body["skeleton_slug"]

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.authoring_metadata is not None
        assert job.authoring_metadata["skeleton_slug"] == body["skeleton_slug"]


async def test_fresh_generation_with_skill_mechanism_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """Invalid combo: fresh_generation can never use mechanism='skill'."""
    req_id = await _approved_request_id(client, seed, "a stubborn goat")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "skill",
            "prep_model": "sonnet",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text


async def test_skeleton_fill_automated_provider_enqueues(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Plan 2: automated skeleton-fill prep is now supported and queued."""
    req_id = await _approved_request_id(client, seed, "a quiet library")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "queued"
    assert body["skeleton_slug"]

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.status == "queued"
        assert job.authoring_metadata is not None


async def test_unrecognized_skill_model_is_422(client: AsyncClient, seed: Seed) -> None:
    """A model outside SKILL_MECHANISM_MODELS is rejected for mechanism='skill'.

    Note: the task brief this test was drafted from expected 400 here. The
    service layer (story_requests/authoring_plan.py, already complete and
    fully unit-tested from Task 7) raises the same ValidationError for this
    case as it does for the two invalid method/mechanism combos above, and
    app.py's ``_status_for`` maps every ValidationError to 422 (there is no
    branch that yields 400 for this exception type). 422 is therefore the
    actual, verified behavior; see task-8-report.md for the full analysis.
    """
    req_id = await _approved_request_id(client, seed, "a shy dragon")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={"method": "skeleton_fill", "mechanism": "skill", "prep_model": "gpt-4o"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text


async def test_not_yet_approved_is_409(client: AsyncClient, seed: Seed) -> None:
    """A still-pending request cannot get an authoring plan."""
    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a pending fox",
        },
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 409, res.text


async def test_duplicate_authoring_plan_is_409(client: AsyncClient, seed: Seed) -> None:
    """A second authoring-plan call for the same request conflicts."""
    req_id = await _approved_request_id(client, seed, "a determined snail")
    body = {
        "method": "fresh_generation",
        "mechanism": "automated_provider",
        "provider": _LANE_OK_PROVIDER,
        "model": _LANE_OK_MODEL,
        "prep_model": "openrouter/some-model",
    }
    first = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan", json=body, headers=auth(seed.admin_token)
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan", json=body, headers=auth(seed.admin_token)
    )
    assert second.status_code == 409, second.text


async def test_guardian_forbidden(client: AsyncClient, seed: Seed) -> None:
    """Only an admin may create an authoring plan, per the design decision."""
    req_id = await _approved_request_id(client, seed, "a guardian-approved tale")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 403, res.text


async def test_child_forbidden(client: AsyncClient, seed: Seed) -> None:
    """A child token must never reach the authoring-plan endpoint."""
    req_id = await _approved_request_id(client, seed, "a child-visible tale")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.child_token),
    )
    assert res.status_code == 403, res.text


async def test_unknown_request_is_404(client: AsyncClient, seed: Seed) -> None:
    """A nonexistent request id is 404 even for an admin (global scope)."""
    res = await client.post(
        f"{_CREATE}/{uuid.uuid4()}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404, res.text


async def test_skeleton_fill_automated_provider_runs_end_to_end(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The full automated skeleton_fill path: authoring-plan -> worker -> storybook.

    Runs the worker function directly (as api/generation.py's own tests do
    for the fresh_generation path) rather than through RQ, since RQ/Redis are
    not part of the integration test harness.
    """
    req_id = await _approved_request_id(client, seed, "a curious fox and a lantern")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "mock",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    job_id = res.json()["job_id"]

    # #ASSUME: external-resources: this test runs the worker against an
    # explicitly-injected mock provider so it stays hermetic (no network). The
    # request body sets provider="openrouter", and the worker now honors that
    # per-job override over the settings default; passing a non-None provider
    # here intentionally bypasses that override so the test does not need a real
    # OPENROUTER_API_KEY. The override-read path itself is unit-tested in
    # test_worker.py::test_effective_provider_reads_job_authoring_override. A
    # mock provider cannot produce a schema-valid filled skeleton from a real
    # prompt, so this test only asserts the job REACHES a terminal status
    # (passed/needs_review/failed), not that it passes cleanly.
    # #VERIFY: if the injected provider is ever removed, this test starts making
    # a real network call instead of reaching a terminal status hermetically.
    from cyo_adventure.generation.provider import _CANNED_STORY_JSON, MockProvider
    from cyo_adventure.generation.worker import run_generation_job

    await run_generation_job(
        uuid.UUID(job_id),
        session_factory=_make_session_factory(sessions),
        provider=MockProvider(responses=[_CANNED_STORY_JSON] * 8),
    )

    res = await client.get(
        f"/api/v1/generation-jobs/{job_id}", headers=auth(seed.guardian_token)
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] in {"passed", "needs_review", "failed"}


async def test_automated_provider_unallowlisted_model_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """A provider/model pair with no enabled allowlist row is rejected.

    Refused for the absence of the row, not for the lane: no row matches, so
    the read path answers False before the lane rule is ever consulted. The
    lane refusal has its own test below.
    """
    req_id = await _approved_request_id(client, seed, "a stray comet")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": "anthropic",
            "model": "not-a-real-model",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text


@pytest.mark.usefixtures("forbidden_enabled_row")
async def test_family_lane_forbidden_pair_is_422(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An ENABLED row the family lane forbids is still refused by the endpoint.

    The only place the D1 read-path veto (`UW-C350` part (a)) is observable end
    to end: `is_enabled_allowlist_pair`'s own tests call the helper directly,
    and the write-path guard in api/provider_allowlist.py never sees this row
    because a migration, seed script, or raw SQL put it there. Without this
    test the swap of every other body in this module to an openrouter pair
    would have removed the last case that can watch the veto fire.

    The refusal is NOT the absence of a row: the `forbidden_enabled_row`
    fixture puts this exact pair in the table enabled, and the assertion below
    proves it is there and enabled at the moment the request is made. What
    refuses it is the lane.
    """
    async with sessions() as session:
        row = await session.scalar(
            select(ProviderModelAllowlist).where(
                ProviderModelAllowlist.provider == _LANE_FORBIDDEN_PROVIDER,
                ProviderModelAllowlist.model_id == _LANE_FORBIDDEN_MODEL,
            )
        )
        assert row is not None, (
            "the forbidden pair must exist for this test to mean anything"
        )
        assert row.enabled is True

    req_id = await _approved_request_id(client, seed, "a lantern in the deep")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": _LANE_FORBIDDEN_PROVIDER,
            "model": _LANE_FORBIDDEN_MODEL,
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )

    assert res.status_code == 422, res.text
    body = res.json()
    assert body["error"] == "ValidationError"
    assert _LANE_FORBIDDEN_PROVIDER in body["message"]
    assert body["details"]["field"] == "model"
    # The admin's submitted value is pruned from the client body (CWE-209)
    # while staying in the server log; asserted here because a frontend error
    # classifier reads this shape.
    assert "value" not in body["details"]

    # No job was created: the refusal happens before anything is persisted.
    # Filtered on the provider rather than on the request, because a
    # GenerationJob carries no story-request column and other tests in this
    # module legitimately leave openrouter jobs behind.
    async with sessions() as session:
        jobs = (
            await session.scalars(
                select(GenerationJob).where(
                    GenerationJob.provider == _LANE_FORBIDDEN_PROVIDER
                )
            )
        ).all()
        assert not jobs


async def test_skeleton_fill_response_includes_alternatives(
    client: AsyncClient, seed: Seed
) -> None:
    """The response lists the full sorted cell as alternatives and picks one.

    The cell's membership is DERIVED, not frozen. This test froze it as three
    literal slugs and broke the moment 10-13/medium/prose gained a book, which is
    exactly the tax `AL-477` records and `UW-C304` fixed across the unit suite;
    this integration copy was missed because it only runs where Docker is
    available, so every local run skipped it and CI found it instead.

    Derived from `candidates_for_cell` rather than from an independent disk scan,
    unlike the unit-layer helper. The claim under test here is that the API
    surfaces the selector's answer in the documented shape, not that the selector
    reads disk correctly, which `test_skeleton_match.py` already owns.
    """
    req_id = await _approved_request_id(client, seed, "a lighthouse keeper returns")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={"method": "skeleton_fill", "mechanism": "skill", "prep_model": "sonnet"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    cell = candidates_for_cell("10-13", "medium", "prose")
    # Guard the derivation itself: an empty cell would make both assertions below
    # vacuous, and this test would then pass while the endpoint returned nothing.
    assert cell, "10-13/medium/prose has no production skeletons"
    # The pick is a weighted-random draw over the cell (unseedable SystemRandom).
    assert body["skeleton_slug"] in cell
    assert body["skeleton_alternatives"] == [{"slug": slug} for slug in cell]


async def test_skeleton_fill_override_out_of_cell_warns(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin override outside the request's cell is accepted, with a warning."""
    req_id = await _approved_request_id(client, seed, "a lantern in the fog")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "skill",
            "prep_model": "sonnet",
            "skeleton_slug": "the-cave-of-echoes",  # a real 8-11 skeleton, not 10-13
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["skeleton_slug"] == "the-cave-of-echoes"
    assert any("outside the request's cell" in w for w in body["warnings"])


async def test_skeleton_fill_override_unknown_slug_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    req_id = await _approved_request_id(client, seed, "a raincloud named gus")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "skill",
            "prep_model": "sonnet",
            "skeleton_slug": "does-not-exist-anywhere",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text


async def test_cross_band_override_producer_binds_consumer_fill(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gap 1: one flowing producer->consumer test for the cross-band override.

    The producer (POST /authoring-plan) overrides the seeded request's own band
    (10-13) with a real 13-16 skeleton (the-sunspire-ascent) and persists the
    override's REAL band on the job. The consumer (run_generation_job ->
    _run_skeleton_fill) then reads that SAME persisted skeleton_band and must
    resolve skeletons/13-16/the-sunspire-ascent.json, reaching a terminal
    passed/needs_review status.

    This binds the producer's persisted ``skeleton_band`` to the consumer's
    read in ONE test, instead of two tests that each hardcode the "13-16"
    literal (test_authoring_plan.py's override-band unit assertion and
    test_generation_worker.py's cross-band worker fixture). If either side
    reverted to the request's own band (10-13), the worker would build a path
    to a nonexistent file and the job would end "failed".
    """
    req_id = await _approved_request_id(client, seed, "a sunspire ascent overridden")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "automated_provider",
            "provider": _LANE_OK_PROVIDER,
            "model": _LANE_OK_MODEL,
            "prep_model": "mock",
            "skeleton_slug": _CROSS_BAND_SKELETON_SLUG,
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "queued"
    assert body["skeleton_slug"] == _CROSS_BAND_SKELETON_SLUG
    job_id = body["job_id"]

    # Producer side: the persisted band is the override's REAL band (13-16),
    # NOT the seeded request's own band (10-13).
    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(job_id))
        assert job is not None
        assert job.authoring_metadata is not None
        assert job.authoring_metadata["skeleton_band"] == _CROSS_BAND_SKELETON_BAND

    # Consumer side: run the worker fill on THAT job and record the skeleton
    # path it resolves. load_skeleton is wrapped (not replaced) so the fill
    # still runs against the real 13-16 skeleton on disk.
    real_load_skeleton = worker_module.load_skeleton
    recorded_paths: list[Path] = []

    def _recording_load_skeleton(path: Path) -> dict[str, object]:
        recorded_paths.append(path)
        return real_load_skeleton(path)

    monkeypatch.setattr(worker_module, "load_skeleton", _recording_load_skeleton)
    # The bound-dispatch neutralization (load_contract_for -> None) is applied
    # module-wide by the _force_legacy_skeleton_fill autouse fixture above.

    # #ASSUME: external-resources: the injected MockProvider keeps the worker
    # hermetic (no network); the per-job provider="openrouter" override is
    # intentionally bypassed exactly as in
    # test_skeleton_fill_automated_provider_runs_end_to_end. The budget is one
    # call for the fill, 22 Stage D repair-batch calls (this 253-node
    # skeleton's placeholder bodies all score outside its declared band, for
    # the reason documented on
    # test_generation_worker.py::test_worker_cross_band_override_loads_stored_band),
    # and one more for the moderation pipeline's bounded auto-repair; queued
    # with headroom above that 24-call floor.
    # #VERIFY: recorded_paths asserts the resolved band-scoped path below.
    provider = MockProvider(
        responses=[_filled_skeleton_json_for(_CROSS_BAND_SKELETON_PATH)] * 30
    )
    await run_generation_job(
        uuid.UUID(job_id),
        session_factory=_make_session_factory(sessions),
        provider=provider,
    )

    # The consumer read the producer's persisted band: exactly the 13-16 path.
    assert len(recorded_paths) == 1
    assert recorded_paths[0].resolve() == _CROSS_BAND_SKELETON_PATH.resolve()

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(job_id))
        assert job is not None
        assert job.status in {
            "passed",
            "needs_review",
        }, f"Expected terminal status, got {job.status} ({job.error})"


async def test_traversing_or_oversized_skeleton_slug_is_422_before_job(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Security: a traversing or oversized skeleton_slug is rejected at the 422
    request-validation boundary, before any GenerationJob is created.

    AuthoringPlanRequest.skeleton_slug carries
    StringConstraints(pattern="^[a-z0-9][a-z0-9-]*$", max_length=120), so a
    path-traversal string ("../../etc/passwd") fails the charset pattern and a
    121-char slug fails max_length. Both are rejected by FastAPI request
    validation, so build_authoring_plan is never entered and no job row exists.
    """
    traversing_req = await _approved_request_id(client, seed, "a traversing slug")
    res = await client.post(
        f"{_CREATE}/{traversing_req}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "skill",
            "prep_model": "sonnet",
            "skeleton_slug": "../../etc/passwd",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text

    oversized_req = await _approved_request_id(client, seed, "an oversized slug")
    res = await client.post(
        f"{_CREATE}/{oversized_req}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "skill",
            "prep_model": "sonnet",
            "skeleton_slug": "a" * 121,  # 1 over the String(120) column cap
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text

    # Neither rejected request created a job: the 422 fires before persistence.
    async with sessions() as session:
        assert (await session.execute(select(GenerationJob))).first() is None
