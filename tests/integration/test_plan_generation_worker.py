"""Integration tests for the WP-2.3 plan path against real Postgres.

Mock provider only (no model call). Covers what the unit doubles cannot: the
plan written to ``generation_job.report`` survives a JSONB round trip and
reloads as a Story Plan that still passes SP-0 to SP-9, and the new
``storybook_version.story_plan`` column stores and returns a plan.
"""

from __future__ import annotations

import json
import uuid  # noqa: TC003 -- uuid.UUID used at runtime in test bodies
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import pytest
import pytest_asyncio

from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    Family,
    GenerationJob,
    StorybookVersion,
    User,
)
from cyo_adventure.generation import worker as worker_module
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.storyplan.checks import check_plan
from cyo_adventure.storyplan.generate import ShapeView, build_shape_view
from cyo_adventure.storyplan.models import StoryPlan
from cyo_adventure.storyplan.shapes import load_registry, load_shape, shape_entry_for

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from cyo_adventure.moderation.report import Finding

_PITCH = {
    "hero": "Rosa, a young explorer",
    "want": "to map the singing cave with her friend",
    "obstacle": "the tunnels echo and the tide is coming in",
    "stake": "the town never learns where the song comes from",
    "ending_kind": "a bright discovery shared with a friend",
}
_BRIEF: dict[str, object] = {
    "premise": "exploring a cave with a friend",
    "protagonist": {"name": "Captain Rosa", "age": 9, "role": "young explorer"},
    "point_of_view": "second",
    "age_band": "8-11",
    "reading_level_target": 3.0,
    "tone": "adventurous",
    "themes_allowed": ["exploration"],
    "content_nogo": [],
    "target_node_count": 20,
    "ending_count": 4,
    "desired_variables": [],
    "special_constraints": [],
}


def _view() -> ShapeView:
    entry = shape_entry_for(load_registry(), "the-cave-of-echoes")
    assert entry is not None
    return build_shape_view(entry, load_shape(entry))


def _clean_plan(view: ShapeView) -> str:
    real = {
        "cast": {
            "rosa": {
                "name": "Rosa",
                "role": "hero",
                "want": "to map the cave",
                "voice": "bright and curious",
                "knows": [],
            }
        },
        "truth": {
            "statement": "The song is the tide in the rocks.",
            "question": "What sings in the cave?",
            "facts": ["f_1"],
        },
        "facts": {
            f"f_{i}": {"text": f"Passage {i} happens."}
            for i in range(1, len(view.book.nodes) + 1)
        },
        "nodes": {
            node.id: {"event": f"Passage {i} happens.", "establishes": [f"f_{i}"]}
            for i, node in enumerate(view.book.nodes, start=1)
        },
        "choices": {
            choice.id: {"intent": f"try option {i}", "cost": f"gives up option {i}"}
            for i, choice in enumerate(
                (c for n in view.book.nodes for c in n.choices), start=1
            )
        },
        "threads": {},
        "endings": {
            node.id: {"gift": "a reason to explore again"}
            for node in view.book.nodes
            if node.is_ending
        },
    }
    return json.dumps(view.to_alias(real))


@asynccontextmanager
async def _session_ctx(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = sessions()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _factory(
    sessions: async_sessionmaker[AsyncSession],
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    return lambda: _session_ctx(sessions)


async def _clean_screen(items: Sequence[tuple[str, str]]) -> Sequence[Finding]:
    _ = items
    return []


@pytest_asyncio.fixture
async def plan_job(sessions: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    """Seed a family, guardian, child, concept and a plan_fill job."""
    view = _view()
    async with sessions() as session:
        fam = Family(name="Plan Family")
        session.add(fam)
        await session.flush()
        guardian = User(family_id=fam.id, role="guardian", authn_subject="plan-g")
        child = ChildProfile(family_id=fam.id, display_name="TestKid", age_band="8-11")
        session.add_all([guardian, child])
        await session.flush()
        concept = Concept(family_id=fam.id, created_by=guardian.id, brief=_BRIEF)
        session.add(concept)
        await session.flush()
        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            authoring_metadata={
                "plan_shape": {"id": view.shape_id, "hash": view.shape_hash},
                "plan_shape_alternatives": [view.shape_id],
                "theme_brief": _BRIEF,
            },
        )
        session.add(job)
        await session.commit()
        return {"job_id": job.id, "family_id": fam.id}


@pytest.mark.asyncio
async def test_plan_job_persists_a_checked_plan_on_the_report(
    sessions: async_sessionmaker[AsyncSession],
    plan_job: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The committed report holds a plan that reloads and still passes SP-0..9."""
    monkeypatch.setattr(worker_module, "classifier_screen", lambda _k: _clean_screen)
    view = _view()
    job_id = cast("uuid.UUID", plan_job["job_id"])
    provider = MockProvider(
        responses=[json.dumps({"pitches": [_PITCH]}), _clean_plan(view)]
    )
    await worker_module.run_generation_job(
        job_id, provider=provider, session_factory=_factory(sessions)
    )
    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "needs_review"
        assert job.storybook_id is None
        report = cast("dict[str, object]", job.report)
        assert report["story_plan_status"] == "checked"
        plan = StoryPlan.model_validate(report["story_plan"])
        assert check_plan(plan, view.book).ok
        assert plan.request.text == _BRIEF["premise"]
        assert job.provider_call_count == 2


@pytest.mark.asyncio
async def test_story_plan_column_round_trips(
    sessions: async_sessionmaker[AsyncSession],
    plan_job: dict[str, object],
) -> None:
    """storybook_version.story_plan stores and returns the plan JSON."""
    plan: dict[str, object] = {"plan_version": "0.1", "facts": {"a": {"text": "x"}}}
    family_id = cast("uuid.UUID", plan_job["family_id"])
    async with sessions() as session:
        await persist_storybook(
            session,
            StorybookParams(
                story_id="s_plan_column",
                blob={"id": "s_plan_column", "title": "T", "nodes": []},
                family_id=family_id,
                provider="mock",
                story_plan=plan,
            ),
        )
        await session.commit()
    async with sessions() as session:
        row = await session.get(StorybookVersion, ("s_plan_column", 1))
        assert row is not None
        assert row.story_plan == plan
