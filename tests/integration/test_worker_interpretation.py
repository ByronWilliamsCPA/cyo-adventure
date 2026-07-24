"""Integration test for the WS-7 refined interpretation end-to-end (D6).

Skips cleanly when Docker is unavailable (via the testcontainers Postgres
harness in ``tests/integration/conftest.py``). Unlike
``test_generation_worker.py`` this module does NOT neutralize
``load_contract_for`` to ``None``: it drives the worker's PARAMETERIZED
(bound) dispatch against a tiny on-disk contract fixture under ``tmp_path`` so
the real ``interpret_and_bind`` -> ``derive_dispositions`` ->
``render_interpretation`` chain runs, and asserts that the resulting refined
interpretation is (a) attached to the job/version report block and (b)
projected onto the originating ``story_request`` row (design section 5.5).

Only the LLM fill step is stubbed (``fill_skeleton`` returns the canned,
schema-valid story blob) so persistence + moderation + the D6 request-row
update all execute against the real database.
"""

from __future__ import annotations

import copy
import json
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import pytest
import pytest_asyncio
from sqlalchemy import select

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    Family,
    GenerationJob,
    StoryRequest,
    User,
)
from cyo_adventure.generation import worker as worker_module
from cyo_adventure.generation.orchestrator import GenerationOutcome
from cyo_adventure.generation.provider import (
    _CANNED_STORY,
    _CANNED_STORY_JSON,
    MockProvider,
)
from cyo_adventure.generation.worker import run_generation_job
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# The same tiny parameterized fixture the unit tests use (mirrors
# tests/unit/test_worker.py::_bound_dispatch_skeleton), inlined here so the
# integration module stays self-contained.
_BINDINGS = {
    "HERO": "Priya",
    "A1_GATE": "the jammed hatch",
    "A1_OFFER": "a glinting tide pool",
    "PRIZE": "Glass Starfish",
}


def _bound_skeleton() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "id": "s_worker_interp_fixture",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
            "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    "<<FILL role=setup words=40 beats='The hero, {HERO}, "
                    "arrives at {A1_GATE} and must choose a path.'>>"
                ),
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Approach {A1_OFFER}.", "target": "n_end_a"},
                    {
                        "id": "c_b",
                        "label": "Turn back toward home.",
                        "target": "n_end_b",
                    },
                ],
            },
            {
                "id": "n_end_a",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero claims the "
                    "prize and celebrates.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The {PRIZE}",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero returns home safely.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "completion",
                    "title": "Home Again",
                },
                "choices": [],
            },
        ],
    }


def _bound_contract() -> ThemeContract:
    def _slot(slot_id: str, *, scope: SlotScope = SlotScope.GLOBAL) -> SlotSpec:
        return SlotSpec(
            id=slot_id,
            scope=scope,
            meaning=f"placeholder meaning for {slot_id}",
            constraints=SlotConstraints(),
        )

    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_worker_interp_fixture",
        age_band=AgeBand.BAND_3_5,
        legacy_lexicon=[],
        default_binding=dict(_BINDINGS),
        slots=[
            _slot("HERO"),
            _slot("A1_GATE", scope=SlotScope.TRACK),
            _slot("A1_OFFER", scope=SlotScope.TRACK),
            _slot("PRIZE", scope=SlotScope.ENDING),
        ],
    )


def _named_contract(skeleton_slug: str) -> ThemeContract:
    """A ``_bound_contract`` variant with a distinct ``skeleton_slug`` label."""
    return _bound_contract().model_copy(update={"skeleton_slug": skeleton_slug})


def _interpret_bind_response() -> str:
    payload: dict[str, object] = {
        "bindings": dict(_BINDINGS),
        "elements": [
            {"phrase": "a brave hero", "slot_id": "HERO"},
            {"phrase": "a sword fight", "slot_id": None},
        ],
    }
    return json.dumps(payload)


def _violating_bind_response() -> str:
    # "a sword-wielder" trips the 3-5 band weapon floor on every bind attempt.
    payload: dict[str, object] = {
        "bindings": {**_BINDINGS, "HERO": "a sword-wielder"},
        "elements": [],
    }
    return json.dumps(payload)


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


def _make_session_factory(sessions: async_sessionmaker[AsyncSession]):  # type: ignore[no-untyped-def]
    def factory():  # type: ignore[no-untyped-def]
        return _session_ctx(sessions)

    return factory


@pytest_asyncio.fixture
async def interp_seed(
    sessions: async_sessionmaker[AsyncSession],
) -> dict[str, object]:
    """Seed Family/User/Concept, a queued skeleton_fill Job, and a StoryRequest
    linked to the concept so the D6 projection has a row to write onto."""
    async with sessions() as session:
        fam = Family(name="Interp Family")
        session.add(fam)
        await session.flush()

        guardian = User(
            family_id=fam.id, role="guardian", authn_subject="guardian-interp-test"
        )
        child_profile = ChildProfile(
            family_id=fam.id, display_name="TestKid", age_band="3-5"
        )
        session.add_all([guardian, child_profile])
        await session.flush()

        concept = Concept(
            family_id=fam.id,
            created_by=guardian.id,
            brief={
                "premise": "A brave explorer discovers a hidden garden.",
                "protagonist": {"name": "Captain Rosa", "age": 5, "role": "explorer"},
                "point_of_view": "second",
                "age_band": "3-5",
                "reading_level_target": 1.0,
                "tier": 1,
                "tone": "adventurous",
                "themes_allowed": ["exploration"],
                "content_nogo": [],
                "target_node_count": 3,
                "ending_count": 2,
                "structure_pattern": "time_cave",
                "desired_variables": [],
                "special_constraints": [],
            },
        )
        session.add(concept)
        await session.flush()

        request = StoryRequest(
            family_id=fam.id,
            profile_id=child_profile.id,
            request_text="A brave explorer discovers a hidden garden.",
            status="approved",
            age_band="3-5",
            concept_id=concept.id,
        )
        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            authoring_metadata={
                "skeleton_slug": "themed-slug",
                "theme_brief": {
                    "premise": "A brave explorer discovers a hidden garden."
                },
            },
        )
        session.add_all([request, job])
        await session.commit()

        return {
            "job_id": job.id,
            "concept_id": concept.id,
            "request_id": request.id,
        }


@pytest.mark.asyncio
async def test_bound_fill_projects_refined_interpretation_onto_request_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions: async_sessionmaker[AsyncSession],
    interp_seed: dict[str, object],
) -> None:
    """End-to-end bound fill: the refined interpretation lands on both the job
    report block and the originating story_request row (WS-7 D5/D6)."""
    job_id = cast("uuid.UUID", interp_seed["job_id"])
    request_id = cast("uuid.UUID", interp_seed["request_id"])

    band_dir = tmp_path / "3-5"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(_bound_contract().model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: _bound_skeleton())

    async def _fake_fill(
        skeleton: dict[str, object],
        theme_brief: dict[str, object],
        provider_arg: object,
        pii: object,
        **_kwargs: object,
    ) -> GenerationOutcome:
        return GenerationOutcome(
            status="passed",
            storybook=copy.deepcopy(_CANNED_STORY),
            report={},
            attempts=0,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill)

    # First response: the interpret-and-bind call. The rest: canned story JSON
    # consumed by the moderation pipeline (fill_skeleton is stubbed, so it makes
    # no provider call).
    responses: list[str | Callable[[str], str]] = [_interpret_bind_response()]
    responses.extend([_CANNED_STORY_JSON] * 8)
    provider = MockProvider(responses=responses)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed", f"expected passed, got {job.status}"
        assert job.report is not None
        block = cast("dict[str, object]", job.report["request_interpretation"])
        assert block["layer"] == "refined"
        assert block["contract_version"] == 1
        assert "theme_contract" in job.report

        result = await session.execute(
            select(StoryRequest).where(StoryRequest.id == request_id)
        )
        request_row = result.scalar_one()
        assert request_row.interpretation is not None
        assert request_row.interpretation["layer"] == "refined"
        assert request_row.interpretation["contract_version"] == 1


# ---------------------------------------------------------------------------
# WS-7 D7: the bounded re-route and the CANNOT_CARRY failure surface end-to-end.
# ---------------------------------------------------------------------------


async def _seed_job(
    sessions: async_sessionmaker[AsyncSession],
    authoring_metadata: dict[str, object],
) -> dict[str, object]:
    """Seed a Family/User/Concept, a queued skeleton_fill Job carrying the given
    authoring_metadata, and a StoryRequest linked to the concept."""
    async with sessions() as session:
        fam = Family(name="D7 Family")
        session.add(fam)
        await session.flush()
        guardian = User(
            family_id=fam.id, role="guardian", authn_subject=f"g-{uuid.uuid4()}"
        )
        child = ChildProfile(family_id=fam.id, display_name="D7Kid", age_band="3-5")
        session.add_all([guardian, child])
        await session.flush()
        concept = Concept(
            family_id=fam.id,
            created_by=guardian.id,
            brief={
                "premise": "A brave explorer discovers a hidden garden.",
                "protagonist": {"name": "Captain Rosa", "age": 5, "role": "explorer"},
                "point_of_view": "second",
                "age_band": "3-5",
                "reading_level_target": 1.0,
                "tier": 1,
                "tone": "adventurous",
                "themes_allowed": ["exploration"],
                "content_nogo": [],
                "target_node_count": 3,
                "ending_count": 2,
                "structure_pattern": "time_cave",
                "desired_variables": [],
                "special_constraints": [],
            },
        )
        session.add(concept)
        await session.flush()
        request = StoryRequest(
            family_id=fam.id,
            profile_id=child.id,
            request_text="A brave explorer discovers a hidden garden.",
            status="approved",
            age_band="3-5",
            concept_id=concept.id,
        )
        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            authoring_metadata=authoring_metadata,
        )
        session.add_all([request, job])
        await session.commit()
        return {"job_id": job.id, "request_id": request.id}


def _multi_skeleton_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: dict[str, str],
) -> None:
    """Write per-slug contract sidecars (all sharing _bound_skeleton) and patch
    resolve_skeleton_path/load_skeleton to dispatch on the 3-5 band directory."""
    band_dir = tmp_path / "3-5"
    band_dir.mkdir()
    for slug, contract_slug in contracts.items():
        (band_dir / f"{slug}.contract.json").write_bytes(
            _named_contract(contract_slug).model_dump_json().encode("utf-8")
        )
    monkeypatch.setattr(
        worker_module,
        "resolve_skeleton_path",
        lambda _band, slug: band_dir / f"{slug}.json",
    )
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: _bound_skeleton())


@pytest.mark.asyncio
async def test_reroute_success_persists_alternate_interpretation_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """bind-fail -> re-route -> success: the alternate's interpretation lands on
    the request row and the report records rerouted_from (WS-7 D7, 6.2)."""
    _multi_skeleton_dispatch(
        tmp_path, monkeypatch, {"themed-slug": "s_planned", "alt-slug": "s_alt"}
    )

    async def _fake_fill(
        skeleton: dict[str, object],
        theme_brief: dict[str, object],
        provider_arg: object,
        pii: object,
        **_kwargs: object,
    ) -> GenerationOutcome:
        return GenerationOutcome(
            status="passed",
            storybook=copy.deepcopy(_CANNED_STORY),
            report={},
            attempts=0,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill)

    seed = await _seed_job(
        sessions,
        {
            "skeleton_slug": "themed-slug",
            "skeleton_alternatives": ["alt-slug"],
            "theme_brief": {"premise": "A brave explorer discovers a hidden garden."},
        },
    )
    job_id = cast("uuid.UUID", seed["job_id"])
    request_id = cast("uuid.UUID", seed["request_id"])

    # planned: 2 violating attempts; alt-slug: 1 valid; then canned for moderation.
    responses: list[str | Callable[[str], str]] = [
        _violating_bind_response(),
        _violating_bind_response(),
        _interpret_bind_response(),
    ]
    responses.extend([_CANNED_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=MockProvider(responses=responses),
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed", f"expected passed, got {job.status}"
        assert job.report is not None
        audit = cast("dict[str, object]", job.report["theme_contract"])
        assert audit["skeleton_slug"] == "s_alt"
        assert audit["rerouted_from"] == "themed-slug"

        result = await session.execute(
            select(StoryRequest).where(StoryRequest.id == request_id)
        )
        row = result.scalar_one()
        assert row.interpretation is not None
        assert row.interpretation["skeleton_slug"] == "s_alt"


@pytest.mark.asyncio
async def test_reroute_exhausted_persists_cannot_carry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """bind-fail -> exhausted -> CANNOT_CARRY: the job fails and the request row
    plus report carry NO_CONFORMING_BINDING (WS-7 D7, 6.1)."""
    _multi_skeleton_dispatch(tmp_path, monkeypatch, {"themed-slug": "s_planned"})

    async def _no_fill(*_a: object, **_k: object) -> GenerationOutcome:
        pytest.fail("fill_skeleton must not run on an exhausted bind path")

    monkeypatch.setattr(worker_module, "fill_skeleton", _no_fill)

    seed = await _seed_job(
        sessions,
        {
            "skeleton_slug": "themed-slug",
            "skeleton_alternatives": [],  # no alternates: exhausts immediately
            "theme_brief": {"premise": "A brave explorer discovers a hidden garden."},
        },
    )
    job_id = cast("uuid.UUID", seed["job_id"])
    request_id = cast("uuid.UUID", seed["request_id"])

    provider = MockProvider(
        responses=[_violating_bind_response(), _violating_bind_response()]
    )

    session_factory = _make_session_factory(sessions)
    with pytest.raises(ValidationError):  # fail-closed re-raise
        await run_generation_job(
            job_id,
            provider=provider,
            session_factory=session_factory,
        )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.report is not None
        violations = cast(
            "list[dict[str, object]]", job.report["slot_binding_violations"]
        )
        assert any(v["rule"] == "forbid:weapon" for v in violations)
        block = cast("dict[str, object]", job.report["request_interpretation"])
        elements = cast("list[dict[str, object]]", block["elements"])
        assert any(
            e["disposition"] == "cannot_carry"
            and e["reason"] == "no_conforming_binding"
            for e in elements
        )

        result = await session.execute(
            select(StoryRequest).where(StoryRequest.id == request_id)
        )
        row = result.scalar_one()
        assert row.interpretation is not None
        row_elements = cast("list[dict[str, object]]", row.interpretation["elements"])
        assert any(e["disposition"] == "cannot_carry" for e in row_elements)
