"""Unit tests for the WP-2.3 plan branch of the generation worker (no DB, mock provider)."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation import worker as worker_module
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.storyplan.generate import ShapeView, build_shape_view
from cyo_adventure.storyplan.shapes import load_registry, load_shape, shape_entry_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.moderation.report import Finding

_SHAPE_ID = "the-cave-of-echoes"
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
_PITCH = {
    "hero": "Rosa, a young explorer",
    "want": "to map the singing cave with her friend",
    "obstacle": "the tunnels echo and the tide is coming in",
    "stake": "the town never learns where the song comes from",
    "ending_kind": "a bright discovery shared with a friend",
}


def _view() -> ShapeView:
    entry = shape_entry_for(load_registry(), _SHAPE_ID)
    assert entry is not None
    return build_shape_view(entry, load_shape(entry))


def _clean_plan(view: ShapeView) -> str:
    """An SP-clean plan for the stateless cave shape, in alias form, as JSON."""
    nodes = {
        node.id: {"event": f"Passage {i} happens.", "establishes": [f"f_{i}"]}
        for i, node in enumerate(view.book.nodes, start=1)
    }
    choices = {
        choice.id: {"intent": f"try option {i}", "cost": f"gives up option {i}"}
        for i, choice in enumerate(
            (c for n in view.book.nodes for c in n.choices), start=1
        )
    }
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
        "nodes": nodes,
        "choices": choices,
        "threads": {},
        "endings": {
            node.id: {"gift": "a reason to explore again"}
            for node in view.book.nodes
            if node.is_ending
        },
    }
    return json.dumps(view.to_alias(real))


class _Result:
    def all(self) -> list[tuple[str]]:
        return []

    def scalar_one_or_none(self) -> None:
        return None


class _Session:
    """Session double with enough surface for a job to reach a terminal status."""

    def __init__(self, job: GenerationJob, concept: Concept) -> None:
        self.job = job
        self.concept = concept
        self.added: list[object] = []
        self.commits = 0

    async def get(self, model: type, ident: object) -> object | None:
        if model is GenerationJob and self.job.id == ident:
            return self.job
        if model is Concept and self.concept.id == ident:
            return self.concept
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> _Result:
        return _Result()

    async def scalar(self, *_args: object, **_kwargs: object) -> None:
        return None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _factory(session: _Session) -> object:
    class _Ctx:
        async def __aenter__(self) -> _Session:
            return session

        async def __aexit__(self, *exc: object) -> None:
            return None

    return _Ctx


def _job(
    metadata: dict[str, object], *, premise: str | None = None
) -> tuple[GenerationJob, Concept]:
    concept_id = uuid.uuid4()
    brief = dict(_BRIEF)
    if premise is not None:
        brief["premise"] = premise
    concept = Concept(id=concept_id, family_id=uuid.uuid4(), brief=brief)
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept_id,
        status="queued",
        model="test-prep",
        authoring_metadata=metadata,
    )
    return job, concept


def _metadata(view: ShapeView) -> dict[str, object]:
    return {
        "provider": "openrouter",
        "model": "test-model",
        "plan_shape": {"id": view.shape_id, "hash": view.shape_hash},
        "plan_shape_alternatives": [view.shape_id],
        "theme_brief": dict(_BRIEF),
    }


async def _clean_screen(items: Sequence[tuple[str, str]]) -> Sequence[Finding]:
    _ = items
    return []


@pytest.fixture(autouse=True)
def _no_network_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Stage 0 screen so no classifier client is ever built."""
    monkeypatch.setattr(worker_module, "classifier_screen", lambda _key: _clean_screen)


@pytest.mark.asyncio
async def test_plan_job_routes_to_plan_generation_and_ends_needs_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plan_fill job stops at a checked plan on the report; no book is made."""
    view = _view()

    async def _must_not_fill(*_args: object, **_kwargs: object) -> object:
        pytest.fail("a plan job must not reach skeleton fill or generate_story")

    monkeypatch.setattr(worker_module, "fill_skeleton", _must_not_fill)
    monkeypatch.setattr(worker_module, "generate_story", _must_not_fill)
    job, concept = _job(_metadata(view))
    session = _Session(job, concept)
    provider = MockProvider(
        responses=[json.dumps({"pitches": [_PITCH]}), _clean_plan(view)]
    )
    await worker_module.run_generation_job(
        job.id,
        provider=provider,
        session_factory=_factory(session),  # pyright: ignore[reportArgumentType]
    )
    assert job.status == "needs_review"
    assert job.storybook_id is None
    report = cast("dict[str, object]", job.report)
    assert report["authoring_method"] == "plan_fill"
    assert report["story_plan_status"] == "checked"
    assert report["story_plan_approval"] == "pending_owner"
    plan = cast("dict[str, object]", report["story_plan"])
    provenance = cast("dict[str, object]", plan["provenance"])
    assert provenance["shape"] == {"id": view.shape_id, "hash": view.shape_hash}
    assert cast("dict[str, object]", plan["request"])["text"] == _BRIEF["premise"]
    assert session.commits >= 1
    # The request text is fenced in both prompts.
    for prompt in provider.calls:
        assert "<<<UNTRUSTED_USER_INPUT" in prompt
        assert "exploring a cave with a friend" in prompt


@pytest.mark.asyncio
async def test_plan_job_with_failing_plan_ends_needs_review_with_findings() -> None:
    """A plan still failing its checks after the budget goes to the owner."""
    view = _view()
    broken = json.loads(_clean_plan(view))
    cast("dict[str, object]", broken["nodes"]).pop("N2")
    job, concept = _job(_metadata(view))
    session = _Session(job, concept)
    provider = MockProvider(
        responses=[json.dumps({"pitches": [_PITCH]}), *[json.dumps(broken)] * 3]
    )
    await worker_module.run_generation_job(
        job.id,
        provider=provider,
        session_factory=_factory(session),  # pyright: ignore[reportArgumentType]
    )
    assert job.status == "needs_review"
    report = cast("dict[str, object]", job.report)
    assert report["story_plan_status"] == "failed_checks"
    assert report["story_plan_attempts"] == 3
    checks = cast("dict[str, object]", report["story_plan_checks"])
    findings = cast("list[dict[str, object]]", checks["findings"])
    assert any(f["rule_id"] == "SP-1" for f in findings)
    assert len(provider.calls) == 4


@pytest.mark.asyncio
async def test_pii_in_a_plan_request_hard_blocks_the_job() -> None:
    """A request naming a family child fails the job before any provider call."""
    view = _view()
    job, concept = _job(_metadata(view), premise="a story about Matilda in a cave")

    class _PiiResult(_Result):
        def all(self) -> list[tuple[str]]:
            return [("Matilda",)]

    class _PiiSession(_Session):
        async def execute(self, *_args: object, **_kwargs: object) -> _Result:
            return _PiiResult()

    session = _PiiSession(job, concept)
    provider = MockProvider(responses=[json.dumps({"pitches": [_PITCH]})])
    factory = _factory(session)
    with pytest.raises(ValidationError):
        await worker_module.run_generation_job(
            job.id,
            provider=provider,
            session_factory=factory,  # pyright: ignore[reportArgumentType]
        )
    assert provider.calls == []
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_plan_job_bound_to_a_stale_hash_fails_before_any_call() -> None:
    """A registry change since planning fails the job closed, no provider call."""
    view = _view()
    metadata = _metadata(view)
    metadata["plan_shape"] = {"id": view.shape_id, "hash": "sha256:" + "1" * 64}
    job, concept = _job(metadata)
    session = _Session(job, concept)
    provider = MockProvider(responses=[])
    factory = _factory(session)
    with pytest.raises(ValidationError, match="changed since"):
        await worker_module.run_generation_job(
            job.id,
            provider=provider,
            session_factory=factory,  # pyright: ignore[reportArgumentType]
        )
    assert provider.calls == []
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_plan_job_without_a_shape_binding_fails() -> None:
    """A malformed plan_shape binding is refused, not guessed."""
    view = _view()
    ctx = worker_module._PlanGenerationContext(
        authoring={"plan_shape": {"id": view.shape_id}},
        brief=cast("object", None),  # pyright: ignore[reportArgumentType]
        effective_provider=MockProvider(responses=[]),
        pii=cast("object", None),  # pyright: ignore[reportArgumentType]
    )
    with pytest.raises(ResourceNotFoundError):
        await worker_module._run_plan_generation(ctx)


@pytest.mark.asyncio
async def test_plan_job_passes_the_plan_settings_to_the_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker forwards the density-repair setting (AL-848)."""
    view = _view()
    seen: dict[str, object] = {}
    original = worker_module.generate_story_plan

    async def _spy(*args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return await original(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(worker_module, "generate_story_plan", _spy)
    monkeypatch.setattr(
        worker_module._default_settings,
        "story_plan_repair_density_warnings",
        False,
    )
    job, concept = _job(_metadata(view))
    session = _Session(job, concept)
    provider = MockProvider(
        responses=[json.dumps({"pitches": [_PITCH]}), _clean_plan(view)]
    )
    await worker_module.run_generation_job(
        job.id,
        provider=provider,
        session_factory=_factory(session),  # pyright: ignore[reportArgumentType]
    )
    assert seen["repair_density_warnings"] is False
    report = cast("dict[str, object]", job.report)
    summaries = cast("list[dict[str, object]]", report["story_plan_attempt_summaries"])
    assert [s["outcome"] for s in summaries] == ["checked"]
