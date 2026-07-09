"""Integration tests: every lifecycle transition writes exactly one pipeline_event."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.core.config import Settings
from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    GenerationJob,
    Storybook,
    StorybookVersion,
    User,
)
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import (
    _CANNED_STORY,
    _CANNED_STORY_JSON,
    MockProvider,
)
from cyo_adventure.generation.worker import run_generation_job
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.moderation.report import Finding, Source, Verdict
from tests.conftest import make_clean_moderation_report
from tests.integration._event_assertions import assert_single_event, fetch_events
from tests.integration.conftest import Seed, auth
from tests.integration.test_generation_worker import (
    _make_session_factory,
    gen_seed,  # noqa: F401 -- imported for pytest fixture discovery
)

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_CREATE = "/api/v1/story-requests"


def _moderation_settings() -> Settings:
    """Return minimal Settings driving the moderation pipeline's mock backend."""
    return Settings(review_provider="mock")


def _pii() -> PiiContext:
    """Return an empty PiiContext with no real-child identifiers to guard against."""
    return PiiContext(child_names=frozenset(), birthdates=frozenset())


async def _seed_draft_storybook(
    sessions: async_sessionmaker[AsyncSession], story_id: str
) -> None:
    """Persist a minimal Family + draft Storybook + StorybookVersion row.

    Reuses the canned, schema-valid story blob (``_CANNED_STORY``) that the
    unit-level moderation-pipeline tests
    (tests/unit/test_moderation_pipeline.py) also validate against, so the
    same story passes ``StoryModel.model_validate`` inside the pipeline.
    """
    async with sessions() as session:
        fam = Family(name="Moderation Event Test Family")
        session.add(fam)
        await session.flush()
        session.add(Storybook(id=story_id, family_id=fam.id, status="draft"))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob=dict(_CANNED_STORY),
                model="gen-model",
            )
        )
        await session.commit()


async def _seed_in_review_storybook(
    sessions: async_sessionmaker[AsyncSession], story_id: str
) -> None:
    """Seed Family + admin user + an in-review, moderation-screened single-version story.

    Mirrors tests/integration/test_approval_api.py::_seed_in_review (a clean
    moderation_report is required: approve() and send_back() both operate on
    an already-screened in_review version).
    """
    async with sessions() as session:
        fam = Family(name="Publishing Event Test Family")
        session.add(fam)
        await session.flush()
        session.add(User(family_id=fam.id, role="admin", authn_subject="admin-a"))
        session.add(Storybook(id=story_id, family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.commit()


async def test_approve_writes_released_event(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Admin approve on an in-review story writes exactly one released event."""
    story_id = "s_release_event"
    await _seed_in_review_storybook(sessions, story_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="released",
        entity_type="storybook",
        to_state="published",
        actor_role="admin",
    )


async def test_send_back_writes_sent_back_event(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Admin send-back on an in-review story writes exactly one sent_back event."""
    story_id = "s_send_back_event"
    await _seed_in_review_storybook(sessions, story_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth("admin-a"),
        json={"reason": "too scary for 6yo"},
    )
    assert resp.status_code == 200, resp.text

    event = await assert_single_event(
        sessions,
        event_type="sent_back",
        entity_type="storybook",
        to_state="needs_revision",
        actor_role="admin",
    )
    assert event.payload == {}


async def test_kid_create_writes_request_created(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    resp = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    await assert_single_event(
        sessions,
        event_type="request_created",
        entity_type="story_request",
        actor_role="child",
    )


async def test_decline_writes_request_declined(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/decline",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_declined",
        entity_type="story_request",
        to_state="declined",
        actor_role="guardian",
    )


async def test_approve_writes_request_approved(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_approved",
        entity_type="story_request",
        to_state="approved",
        actor_role="guardian",
    )


async def test_authoring_plan_writes_plan_assigned(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    approved = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert approved.status_code == 200, approved.text
    resp = await client.post(
        f"{_CREATE}/{request_id}/authoring-plan",
        headers=auth(seed.admin_token),
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
    )
    assert resp.status_code == 201, resp.text
    await assert_single_event(
        sessions,
        event_type="plan_assigned",
        entity_type="generation_job",
        actor_role="admin",
    )


async def test_generation_run_writes_started_and_finished_system_events(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],  # noqa: F811 -- pytest fixture, not the import
) -> None:
    """A full worker run writes exactly one generation_started and one
    generation_finished event, both attributed to the system actor.

    Reuses the ``gen_seed`` fixture and session-factory helper from
    test_generation_worker.py (seeded queued job + injected MockProvider)
    rather than building a new worker-test arrangement.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    provider = MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed", f"Expected passed, got {job.status}"

    await assert_single_event(
        sessions,
        event_type="generation_started",
        entity_type="generation_job",
        to_state="running",
        actor_is_system=True,
    )
    await assert_single_event(
        sessions,
        event_type="generation_finished",
        entity_type="generation_job",
        to_state="passed",
        actor_is_system=True,
    )


async def test_generation_finished_event_precedes_failure_commit(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],  # noqa: F811 -- pytest fixture, not the import
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pipeline failure's generation_finished event is committed atomically
    with the job's "failed" status write, never separately (worker.py
    ``_record_failure``'s #CRITICAL marker).

    ``record_event`` (events/writer.py) only flushes; the durable write comes
    from the SAME ``session.commit()`` that ``_record_failure`` calls right
    after it. Asserting "the event lands before the commit" cannot be done by
    polling from a second session/connection: Postgres's transaction
    isolation means a separate session can never observe an intermediate
    state inside another session's still-open transaction, so there is
    nothing to poll for. Two observations together establish the atomicity
    claim instead of one impossible one:

    1. Here: once the worker's failure path has fully run, the failed job row
       and its generation_finished/failed event are BOTH visible from a fresh
       session. If the event write happened in a transaction separate from
       the status write, a crash between the two could leave one committed
       without the other; this pins that they always arrive together.
    2. In the companion test
       (test_generation_finished_event_and_failed_status_share_one_commit):
       forcing the shared commit itself to fail leaves NEITHER row durable,
       proving the converse: nothing here becomes visible without that one
       commit succeeding. 1 and 2 together pin the "same transaction" claim.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    async def _boom_generate(*_args: object, **_kwargs: object) -> None:
        msg = "pipeline exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "cyo_adventure.generation.worker.generate_story", _boom_generate
    )

    with pytest.raises(RuntimeError, match="pipeline exploded"):
        await run_generation_job(
            job_id,
            provider=MockProvider(responses=[]),
            session_factory=_make_session_factory(sessions),
        )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error == "pipeline exploded"

    event = await assert_single_event(
        sessions,
        event_type="generation_finished",
        entity_type="generation_job",
        to_state="failed",
        actor_is_system=True,
    )
    assert event.entity_id == str(job_id)
    assert event.actor_id is None
    assert event.actor_role == "system"
    assert event.payload == {"outcome": "failed"}


async def test_generation_finished_event_and_failed_status_share_one_commit(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],  # noqa: F811 -- pytest fixture, not the import
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the worker's terminal commit fails, neither the failed status nor
    its generation_finished event becomes durable.

    Companion to test_generation_finished_event_precedes_failure_commit:
    forces ``AsyncSession.commit`` to raise, simulating a crash landing right
    at the commit boundary ``_record_failure`` relies on. ``record_event``'s
    INSERT was already flushed (sent to Postgres over the same still-open
    transaction) before this failing commit call; since that row still does
    not survive, the event write was never durable on its own, only the
    shared commit makes it (and the status write) durable together.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    async def _boom_generate(*_args: object, **_kwargs: object) -> None:
        msg = "pipeline exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "cyo_adventure.generation.worker.generate_story", _boom_generate
    )

    async def _boom_commit(_self: AsyncSession) -> None:
        msg = "commit interrupted"
        raise RuntimeError(msg)

    monkeypatch.setattr(AsyncSession, "commit", _boom_commit)

    with pytest.raises(RuntimeError, match="commit interrupted"):
        await run_generation_job(
            job_id,
            provider=MockProvider(responses=[]),
            session_factory=_make_session_factory(sessions),
        )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        # Neither the "running" nor the "failed" transition was ever
        # committed: the job row is still at its original queued state.
        assert job.status == "queued"

    assert await fetch_events(sessions, "generation_finished") == []


async def test_clean_moderation_writes_moderation_completed(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean moderation run (no soft flags, no hard block) writes exactly one
    moderation_completed event, attributed to the system actor, with
    to_state="in_review" and a PII-free payload showing repaired=False.

    Drives ``run_moderation_pipeline`` directly against a real session, reusing
    the stage-stubbing arrangement from
    tests/unit/test_moderation_pipeline.py::test_clean_story_routes_to_submit
    (classifiers and all four LLM stages stubbed clean) rather than the mock
    review backend, whose fixed ``"{}"`` responses fail-safe every safety
    finding to FLAG and would spuriously trigger repair on every run.
    """
    story_id = "s_mod_clean"
    await _seed_draft_storybook(sessions, story_id)

    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
    for name in (
        "run_safety_stage",
        "run_readability_stage",
        "run_coherence_stage",
        "run_engagement_stage",
    ):
        monkeypatch.setattr(pipeline_mod, name, AsyncMock(return_value=[]))

    async with sessions() as session:
        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=_moderation_settings(),
            generation_provider=AsyncMock(),
            pii=_pii(),
        )
        await session.commit()

    event = await assert_single_event(
        sessions,
        event_type="moderation_completed",
        entity_type="storybook_version",
        to_state="in_review",
        actor_is_system=True,
    )
    assert event.payload["overall_verdict"] == "pass"
    assert event.payload["repaired"] is False
    assert event.payload["counts"] == {}

    assert await fetch_events(sessions, "repair_applied") == []


async def test_repaired_moderation_writes_repair_applied_then_completed(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A soft-flagged run that triggers repair writes exactly one repair_applied
    event followed by exactly one moderation_completed event with
    payload["repaired"] is True.

    Reuses the repair-triggering arrangement from
    tests/unit/test_moderation_pipeline.py::test_soft_flag_triggers_repair_then_submits
    (readability FLAGs once, then clean after the stubbed repair) against a
    real session so both events land in the durable pipeline_event table.
    """
    story_id = "s_mod_repair"
    await _seed_draft_storybook(sessions, story_id)

    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_mod, "run_safety_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_mod, "run_coherence_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        pipeline_mod, "run_engagement_stage", AsyncMock(return_value=[])
    )

    flag_finding = Finding(
        stage=2,
        source=Source.LLM_READABILITY,
        category="reading_level",
        node_id="n1",
        verdict=Verdict.FLAG,
        message="too hard",
    )
    # First call (initial moderation) returns the FLAG; second call (post-repair
    # re-moderation) returns clean, mirroring the unit test's arrangement.
    monkeypatch.setattr(
        pipeline_mod,
        "run_readability_stage",
        AsyncMock(side_effect=[[flag_finding], []]),
    )
    revised_blob: dict[str, object] = {
        **dict(_CANNED_STORY),
        "title": "The Forest Path (revised)",
    }
    monkeypatch.setattr(
        pipeline_mod, "attempt_repair", AsyncMock(return_value=revised_blob)
    )

    async with sessions() as session:
        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=_moderation_settings(),
            generation_provider=AsyncMock(),
            pii=_pii(),
        )
        await session.commit()

    repair_event = await assert_single_event(
        sessions,
        event_type="repair_applied",
        entity_type="storybook_version",
        actor_is_system=True,
    )
    assert repair_event.payload == {"stage": "moderation"}

    completed_event = await assert_single_event(
        sessions,
        event_type="moderation_completed",
        entity_type="storybook_version",
        to_state="in_review",
        actor_is_system=True,
    )
    assert completed_event.payload["repaired"] is True

    # repair_applied precedes moderation_completed for this version (WS-D task
    # brief order requirement): the adoption point fires before the report's
    # outcome is persisted and the completion event is recorded.
    assert repair_event.occurred_at <= completed_event.occurred_at


async def test_hard_block_moderation_writes_moderation_completed_needs_revision(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hard-blocked run (auto_reject, not submit) writes exactly one
    moderation_completed event with to_state="needs_revision" and a payload
    holding only enum verdicts, a bool, and int counts, never the blocking
    finding's message text or category (spec D3 PII-free contract).

    Mirrors the hard-block arrangement from
    tests/unit/test_moderation_pipeline.py::test_hard_block_routes_to_auto_reject
    (a classifier BLOCK finding, all four LLM stages stubbed clean) against a
    real session, and additionally asserts the storybook's real routed state
    (the unit test only checks that ``publishing.service.auto_reject`` was
    called; here it actually runs).
    """
    story_id = "s_mod_block"
    await _seed_draft_storybook(sessions, story_id)

    monkeypatch.setattr(
        pipeline_mod,
        "run_classifiers",
        AsyncMock(
            return_value=[
                Finding(
                    stage=0,
                    source=Source.OPENAI,
                    category="sexual/minors",
                    node_id="n1",
                    verdict=Verdict.BLOCK,
                    message="this finding's prose must never reach the event log",
                )
            ]
        ),
    )
    for name in (
        "run_safety_stage",
        "run_readability_stage",
        "run_coherence_stage",
        "run_engagement_stage",
    ):
        monkeypatch.setattr(pipeline_mod, name, AsyncMock(return_value=[]))

    async with sessions() as session:
        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=_moderation_settings(),
            generation_provider=AsyncMock(),
            pii=_pii(),
        )
        await session.commit()

    async with sessions() as session:
        story = await session.get(Storybook, story_id)
        assert story is not None
        assert story.status == "needs_revision"

    event = await assert_single_event(
        sessions,
        event_type="moderation_completed",
        entity_type="storybook_version",
        to_state="needs_revision",
        actor_is_system=True,
    )
    # Exact equality (not just key presence) pins that "counts" holds a plain
    # verdict-name -> int mapping: any stray string/float value, or an extra
    # key such as "message"/"category" carrying the finding's own prose,
    # would break this comparison.
    assert event.payload == {
        "overall_verdict": "block",
        "repaired": False,
        "counts": {"block": 1},
    }


_THRESHOLD_URL = "/api/v1/admin/moderation-thresholds"
_NOISE_FLOOR_URL = "/api/v1/admin/moderation/noise-floor"


async def test_threshold_upsert_emits_threshold_changed_event(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """PUT on a threshold override writes exactly one threshold_changed event,
    attributed to the admin, with a payload carrying action="upsert" plus
    the age_band/category/min_verdict/min_score that were written.
    """
    res = await client.put(
        f"{_THRESHOLD_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": 0.3},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200

    event = await assert_single_event(
        sessions,
        event_type="threshold_changed",
        entity_type="moderation_threshold",
        actor_role="admin",
    )
    assert event.entity_id == "3-5"
    assert event.payload == {
        "age_band": "3-5",
        "category": "violence",
        "action": "upsert",
        "min_verdict": "advisory",
        "min_score": 0.3,
    }


async def test_threshold_delete_emits_threshold_changed_event(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """DELETE on a threshold override writes exactly one threshold_changed
    event with action="delete" and only the keys known at delete time (no
    min_verdict/min_score, since the value no longer exists).
    """
    put_res = await client.put(
        f"{_THRESHOLD_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert put_res.status_code == 200

    res = await client.delete(
        f"{_THRESHOLD_URL}/3-5",
        params={"category": "violence"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200

    events = await fetch_events(sessions, "threshold_changed")
    assert [e.payload["action"] for e in events] == ["upsert", "delete"]
    delete_event = events[-1]
    assert delete_event.entity_type == "moderation_threshold"
    assert delete_event.actor_role == "admin"
    assert delete_event.payload == {
        "age_band": "3-5",
        "category": "violence",
        "action": "delete",
    }


async def test_noise_floor_update_emits_noise_floor_changed_event(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """PUT on the global noise floor writes exactly one noise_floor_changed
    event, attributed to the admin, with a payload carrying only the new
    value.
    """
    res = await client.put(
        _NOISE_FLOOR_URL, json={"value": 0.2}, headers=auth(seed.admin_token)
    )
    assert res.status_code == 200

    event = await assert_single_event(
        sessions,
        event_type="noise_floor_changed",
        entity_type="moderation_setting",
        actor_role="admin",
    )
    assert event.entity_id == "admin_noise_floor"
    assert event.payload == {"value": 0.2}


async def test_assign_writes_book_assigned_event_per_new_assignment(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Assigning a published book to a NEW profile writes exactly one
    book_assigned event, attributed to the guardian.

    The ``seed`` fixture already assigns ``seed.storybook_id`` to
    ``seed.child_profile_id`` (profile_a), so this test adds a second Family A
    child profile and assigns the same book to that new profile instead. This
    keeps the new-event count at exactly one and, together with the assertion
    below, pins that the idempotent skip branch (an already-assigned profile)
    does not also emit an event.
    """
    async with sessions() as session:
        sibling = ChildProfile(
            family_id=seed.family_id, display_name="Reader A2", age_band="8-11"
        )
        session.add(sibling)
        await session.commit()
        sibling_id = sibling.id

    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id), str(sibling_id)]},
    )
    assert resp.status_code == 200, resp.text

    event = await assert_single_event(
        sessions,
        event_type="book_assigned",
        entity_type="storybook_assignment",
        actor_role="guardian",
    )
    assert event.entity_id == f"{sibling_id}:{seed.storybook_id}"
    assert event.payload == {"child_profile_id": str(sibling_id)}


async def test_rating_writes_rated_event_with_is_update_transition(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Rating the same book twice writes two rated events: the first with
    is_update False (new row), the second with is_update True (overwrite).
    """
    first = await client.post(
        "/api/v1/ratings",
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 3,
        },
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/api/v1/ratings",
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 5,
        },
    )
    assert second.status_code == 200, second.text

    events = await fetch_events(sessions, "rated")
    assert len(events) == 2
    assert [e.payload["is_update"] for e in events] == [False, True]
    assert [e.payload["value"] for e in events] == [3, 5]
    for event in events:
        assert event.entity_type == "rating"
        assert event.entity_id == f"{seed.child_profile_id}:{seed.storybook_id}"
        assert event.actor_role == "child"
