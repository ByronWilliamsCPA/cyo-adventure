"""Unit tests for the moderation pipeline control flow and state-machine driving.

Mocking policy (org testing standard §4.2/§4.3): these tests run the REAL
stage functions (``run_classifiers`` and the four LLM stages), the real
report accumulation, and the real repair logic. Only true system boundaries
are doubled:

- the review LLM backend, via the ``build_review_provider`` seam (replaced
  with a deterministic :class:`MockProvider` that answers each stage with
  schema-correct verdict JSON);
- the generation LLM backend, via a :class:`MockProvider` passed as
  ``generation_provider`` (the repair re-prompt seam);
- classifier HTTP, via ``httpx.MockTransport`` (the same pattern as
  tests/unit/test_moderation_classifiers.py) when a classifier response is
  needed;
- the publishing service's ``submit``/``auto_reject`` (the state-machine
  outbound edge, asserted as the pipeline's routing outcome; its own behavior
  is covered by tests/unit/test_publishing_service_unit.py);
- the DB session (spec'd ``AsyncMock``; no live database in unit tests).
"""

from __future__ import annotations

import copy
import json
import math
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ValidationError as CoreValidationError
from cyo_adventure.db.models import GenerationJob, Storybook, StorybookVersion
from cyo_adventure.diversity.history import HistoryEntry
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import _CANNED_STORY, MockProvider
from cyo_adventure.moderation import leaf_diversity as leaf_diversity_mod
from cyo_adventure.moderation import personalizable_slots as pslots_mod
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.moderation.leaf_diversity import (
    run_leaf_diversity_check as _real_run_leaf_diversity_check,
)
from cyo_adventure.moderation.personalizable_slots import (
    PERSONALIZABLE_SLOTS_UNRECOVERABLE,
    PersonalizableSlots,
)
from cyo_adventure.moderation.prose_craft import findings_from_prose_craft
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.sentinels import wrap
from cyo_adventure.storybook.theme_contract import SlotScope, SlotSpec, ThemeContract

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

# A valid Storybook JSON blob (uses the same canned story as the mock provider
# to guarantee it passes StoryModel.model_validate inside the pipeline).
_BLOB: dict[str, object] = dict(_CANNED_STORY)

_NODE_COUNT = len(cast("list[object]", _CANNED_STORY["nodes"]))

# Batch size for the partial-final-chunk test: derived so the last chunk always
# holds exactly one node, whatever the mock story's node count happens to be.
# That remainder of one is what drives ``run_safety_stage``'s single-node path
# (stages.py, ``len(batch) == 1``), so the test covers both prompt shapes.
#
# It was a literal 3 against a 7-node story, which is a relationship that holds
# by coincidence rather than by construction: the story grew to 8 nodes when
# PL-25's floor forced an establishing opening, the remainder became 2, and the
# single-node path silently stopped being exercised at all.
#
# At the current _NODE_COUNT (8), this evaluates to 7 and produces ONE full
# batch of 7 nodes plus a remainder of exactly 1: a single full batch, not two,
# so it cannot exercise the loop iterating between full batches before it hits
# the remainder. See ``_TWO_FULL_BATCHES_BATCH_SIZE`` below for that seam. If
# the story's node count moves again, recheck what split this derivation
# yields; it is coupled to ``_NODE_COUNT`` by construction, not by coincidence,
# but the split it produces can still change shape.
_PARTIAL_CHUNK_BATCH_SIZE = _NODE_COUNT - 1

# Batch size for the two-full-batches test: a literal, NOT derived from
# _NODE_COUNT, so growing the story cannot silently collapse it back to a
# single-batch split the way ``_PARTIAL_CHUNK_BATCH_SIZE`` did when the story
# grew from 7 to 8 nodes (see above). At the current _NODE_COUNT (8), a batch
# size of 3 chunks as 3+3+2: two full batches of 3 followed by a remainder of
# 2, which exercises the loop actually iterating between two full batches
# (rather than entering the loop body once, as the partial-chunk test above
# does). The test asserts this split explicitly rather than assuming it.
_TWO_FULL_BATCHES_BATCH_SIZE = 3

# Review calls per moderation pass: safety per node (review_batch_size=1,
# pinned by _settings() below, so every chunk is one node), coherence +
# engagement once each. A repair run makes two passes; pad the budget so an
# exhausted MockProvider (which raises loudly) signals a real pipeline bug,
# not a miscounted fixture.
_REVIEW_BUDGET = 4 * (_NODE_COUNT + 2)


def _settings() -> Settings:
    """Return a minimal Settings with review_provider='mock'.

    Pins ``review_batch_size=1``: the fixtures built by ``_review_provider``
    answer Stage-1 prompts with a single verdict OBJECT, which only the
    single-node parser accepts (see the coupling notes on
    ``_review_provider``). The Settings default rose to 8 after the Gate 3
    recall comparison (2026-08-01); the size-1 path stays a supported
    configuration and these legacy tests keep exercising it, while
    default-batching coverage lives in the ``review_batch_size wiring``
    tests at the bottom of this file.
    """
    return Settings(review_provider="mock", review_batch_size=1)


def _pii() -> PiiContext:
    """Return an empty PiiContext with no real-child identifiers."""
    return PiiContext(child_names=frozenset())


def _story(status: str = "draft") -> Storybook:
    return Storybook(id="s1", family_id=uuid.uuid4(), status=status)


def _version() -> StorybookVersion:
    return StorybookVersion(storybook_id="s1", version=1, blob=_BLOB, model="gen-model")


def _execute_result(value: object) -> MagicMock:
    """Build a fake `Result` whose `scalar_one_or_none()` returns ``value``.

    Mirrors tests/unit/test_approval_unit.py::_execute_result: `execute()` is
    awaited, but the `Result` it returns exposes a plain (synchronous)
    `scalar_one_or_none` method.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _load(
    session: AsyncMock,
    story: Storybook,
    version_row: object,
    job: GenerationJob | None = None,
) -> None:
    """Wire a mock session for the pipeline's locked-load pattern.

    The storybook now loads via ``session.execute(...).scalar_one_or_none()``
    (SELECT ... FOR UPDATE); the version row still loads via ``session.get``.
    ``session.execute`` now also serves the repair path's ``GenerationJob``
    lookup (``personalizable_slot_ids_for_story``): the two ``select(...)``
    statements are distinguished by which ORM entity they target, so a test
    that never triggers repair is unaffected, and one that does gets ``job``
    (default ``None``: no job on record, today's dormant default).
    """

    def _execute_side_effect(stmt: Select[tuple[object]]) -> MagicMock:
        if stmt.column_descriptions[0]["type"] is GenerationJob:
            return _execute_result(job)
        return _execute_result(story)

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.get = AsyncMock(return_value=version_row)


def _verdict_review_provider(*, safety_flags_first_pass: bool = False) -> MockProvider:
    """Build a review backend double that answers each stage with a real verdict.

    Unlike the settings-level mock backend (``review_provider="mock"``, whose
    fixed ``"{}"`` bodies fail-safe every safety check to FLAG), this
    responder returns schema-correct verdict JSON per stage, dispatching on
    each stage's own prompt prefix, so the REAL stage functions run and parse
    real verdicts.

    Args:
        safety_flags_first_pass: When True, every safety call in the FIRST
            moderation pass returns ``"flag"`` (the soft gate), and any later
            pass (the post-repair re-moderation) returns ``"safe"``. Stage 2
            (readability) was retired (design doc 2.7 option (a)); the soft
            FLAG that used to drive the repair-trigger tests now comes from
            Stage 1 safety instead, since it is the only stage left capable
            of a per-node FLAG.

    Coupled to ``review_batch_size == 1`` (pinned by ``_settings()``; the
    Settings default is 8 since Gate 3) in two ways, neither of which
    announces itself if the pin is removed:

    1. It answers with a single verdict OBJECT. The batched Stage-1 prompt
       starts with the same ``"Age band:"`` prefix this dispatches on, but
       ``_parse_batch_verdicts`` expects a JSON ARRAY, so at a batch size
       above 1 every batch would be rejected as malformed and every node
       would fail safe to FLAG.
    2. ``safety_calls <= _NODE_COUNT`` assumes one call per node, which is
       how it tells the first moderation pass from the post-repair one. At a
       batch size of B that boundary is ``ceil(_NODE_COUNT / B)``.

    Symptom if the ``_settings()`` pin is ever dropped: these tests fail
    with unexplained fail-safe FLAGs rather than with anything naming the
    batch size. The fix is to return an array keyed by the node ids in the
    prompt and to derive the pass boundary from the batch size (see
    ``_batched_verdict_review_provider``), not to relax the assertions.

    Returns:
        A :class:`MockProvider` seeded with the dispatching responder.
    """
    state = {"safety_calls": 0}

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            state["safety_calls"] += 1
            first_pass = state["safety_calls"] <= _NODE_COUNT
            if safety_flags_first_pass and first_pass:
                return '{"verdict": "flag", "reason": "too hard"}'
            return '{"verdict": "safe", "reason": "ok"}'
        # Coherence and engagement (whole-story prompts) both accept "pass".
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * _REVIEW_BUDGET)


def _safety_block_review_provider() -> MockProvider:
    """Build a review backend double whose Stage 1 safety call BLOCKs once.

    Unlike ``_verdict_review_provider`` (always "safe"), this answers the
    FIRST safety-stage prompt with a genuine ``"block"`` verdict and every
    other stage with a passing verdict, so ``run_safety_stage`` (the real
    stage function, not the Stage-0 classifier bright-line path) is what
    produces the hard-block finding.

    Returns:
        A :class:`MockProvider` seeded with the dispatching responder.
    """
    state = {"safety_calls": 0}

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            state["safety_calls"] += 1
            if state["safety_calls"] == 1:
                return '{"verdict": "block", "reason": "unsafe content"}'
            return '{"verdict": "safe", "reason": "ok"}'
        # Never reached: a hard block short-circuits before coherence/
        # engagement run, but answer "pass" defensively so a future
        # short-circuit regression fails on an assertion, not a starved
        # MockProvider raising BusinessLogicError.
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * _REVIEW_BUDGET)


def _install_canned_classifier_http(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Route the pipeline's internally-built classifier client to a canned handler.

    The pipeline constructs its own ``httpx.AsyncClient`` inside
    ``_run_all_stages`` (not injectable), so the ``httpx.MockTransport``
    pattern from tests/unit/test_moderation_classifiers.py is applied one
    level up: the client constructor is replaced with one that wires the
    canned transport in.
    """
    real_async_client = httpx.AsyncClient

    def _canned_client(**_kwargs: object) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(pipeline_mod.httpx, "AsyncClient", _canned_client)


@pytest.fixture
def review_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[MockProvider], dict[str, object]]:
    """Factory patching the pipeline's one external review boundary.

    Replaces ``pipeline_mod.build_review_provider`` (the seam where a real
    LLM backend would be constructed) so the real stage functions and the
    real report/routing logic all execute against a deterministic in-process
    provider; only the backend itself is doubled, per the
    mock-at-the-boundary rule (testing standard §4.3).

    Returns:
        An installer taking the provider to serve; calling it patches the
        seam and returns a capture dict recording the resolved ``Settings``
        and kwargs the pipeline passed to the builder.
    """

    def _install(provider: MockProvider) -> dict[str, object]:
        captured: dict[str, object] = {}

        def _build(settings: Settings, **kwargs: object) -> tuple[MockProvider, bool]:
            captured["settings"] = settings
            captured["kwargs"] = kwargs
            return provider, True

        monkeypatch.setattr(pipeline_mod, "build_review_provider", _build)
        return captured

    return _install


@pytest.fixture
def mock_session(mock_async_session: AsyncMock) -> AsyncMock:
    """Alias the shared spec'd session double (tests/unit/conftest.py)."""
    return mock_async_session


@pytest.mark.unit
async def test_pipeline_locks_storybook_row_for_update(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The pipeline's storybook load must carry SELECT ... FOR UPDATE.

    Mirrors tests/unit/test_approval_unit.py::
    test_load_admin_story_locks_row_for_update. This worker path drives the
    same submit/auto_reject transitions api/approval.py's admin path drives,
    so losing the lock here reopens the #129-style race for the worker path:
    a concurrent transition on the same story could read a stale in-memory
    status and clobber the other's write.

    Since Task 6a, ``session.execute`` is awaited a SECOND time on every
    pass (the entry-level sentinel-integrity backstop's ``GenerationJob``
    lookup, ``personalizable_slot_ids_for_story``, now runs unconditionally
    rather than only inside the repair path), so this locates the STORYBOOK
    select specifically by its target entity rather than assuming a single
    ``execute`` call.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    assert mock_session.execute.await_count == 2
    stmt = next(
        call.args[0]
        for call in mock_session.execute.await_args_list
        if call.args[0].column_descriptions[0]["type"] is Storybook
    )
    where = str(stmt.whereclause)
    assert "storybook" in where.lower()

    # Render with the Postgres dialect (the deployment target): the generic
    # compiler omits skip_locked/nowait clauses, so a weakening would be
    # invisible under str(stmt). skip_locked would let a concurrent caller
    # slip past the lock instead of serializing behind it.
    rendered = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in rendered
    assert "SKIP LOCKED" not in rendered
    assert "NOWAIT" not in rendered


@pytest.mark.unit
async def test_hard_block_routes_to_auto_reject(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Stage-0 bright-line classifier hit hard-blocks straight to auto_reject.

    Runs the REAL ``run_classifiers`` against a canned OpenAI Moderation
    response (bright-line ``sexual/minors`` flagged) served over
    ``MockTransport``; the Stage-0 short-circuit then skips every LLM stage,
    so no review verdicts are needed.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)

    def _brightline_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "categories": {"sexual/minors": True},
                        "category_scores": {"sexual/minors": 0.99},
                    }
                ]
            },
        )

    _install_canned_classifier_http(monkeypatch, _brightline_handler)
    auto_reject = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=Settings(review_provider="mock", openai_api_key="k"),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["hard_block"] is True


@pytest.mark.unit
async def test_classifier_call_blocked_on_pii_in_node_body(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registered real-child name in generated node prose blocks the
    Stage-0 classifier calls before they reach the network, propagating
    uncaught out of ``run_moderation_pipeline`` -- the same behavior a PII
    trip in the guarded LLM review stages already has.

    Regression test: OpenAI Moderation/Google Perspective previously received
    raw node prose with no PII screening at all, unlike the sibling LLM
    review stage (``guarded_review``) three lines away in the same function.
    """
    tainted_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", tainted_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = "This story was written just for RealChildName today."

    story = _story()
    version = StorybookVersion(
        storybook_id="s1", version=1, blob=tainted_blob, model="gen-model"
    )
    _load(mock_session, story, version)

    classifier_called = {"count": 0}

    def _handler(_request: httpx.Request) -> httpx.Response:
        classifier_called["count"] += 1
        return httpx.Response(
            200,
            json={
                "results": [{"flagged": False, "categories": {}, "category_scores": {}}]
            },
        )

    _install_canned_classifier_http(monkeypatch, _handler)

    settings = Settings(review_provider="mock", openai_api_key="k")
    generation_provider = MockProvider(responses=[])
    pii = PiiContext(child_names=frozenset({"RealChildName"}))
    with pytest.raises(CoreValidationError):
        await pipeline_mod.run_moderation_pipeline(
            session=mock_session,
            story_id="s1",
            version=1,
            settings=settings,
            generation_provider=generation_provider,
            pii=pii,
        )

    assert classifier_called["count"] == 0


@pytest.mark.unit
async def test_safety_stage_block_routes_to_auto_reject(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A Stage-1 LLM safety BLOCK verdict (not a Stage-0 classifier hit) also
    routes to auto_reject.

    ``test_hard_block_routes_to_auto_reject`` exercises the Stage-0
    bright-line classifier short-circuit only; nothing in this module drove
    the real ``run_safety_stage`` to a genuine ``Verdict.BLOCK``. Here Stage 0
    passes (no classifier keys configured, so ``run_classifiers`` is a no-op),
    and the real safety stage parses a "block" verdict on its first node,
    which must: (1) short-circuit the remaining LLM stages (coherence/
    engagement never asked for a verdict beyond the padded budget),
    (2) mark the persisted report hard_block=True with an ``llm_safety``
    sourced block finding, and (3) drive ``auto_reject``, never ``submit``.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_safety_block_review_provider())
    auto_reject = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["hard_block"] is True
    findings = cast("list[dict[str, object]]", version.moderation_report["findings"])
    block_findings = [f for f in findings if f["verdict"] == "block"]
    assert block_findings, "expected at least one block finding"
    assert any(f["source"] == "llm_safety" for f in block_findings)


@pytest.mark.unit
async def test_clean_story_routes_to_submit(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    assert version.moderation_report["summary"]["hard_block"] is False


@pytest.mark.unit
async def test_mock_review_escape_hatch_stamps_report_as_not_independent(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The CYO_ADVENTURE_ALLOW_MOCK_REVIEW escape hatch self-identifies forever.

    Design doc section 2.4 / gap G1: a report moderated with the mock
    reviewer outside environment="local" (only reachable via the explicit
    escape hatch, since ``_require_real_reviewer_outside_local`` otherwise
    raises ConfigurationError at Settings construction) must be stamped
    ``reviewer_independent=False`` plus a structural advisory finding, so the
    report is self-identifying even after the escape hatch is later unset.

    ``review_seam`` replaces ``build_review_provider`` with a real-verdict
    responder (rather than exercising the actual mock backend's fixed "{}"
    body) so this test isolates the pipeline-level stamp from the Stage-1
    collapse behavior covered separately in test_moderation_stages.py.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    escape_hatch_settings = Settings(
        review_provider="mock",
        environment="staging",
        allow_mock_review=True,
        # Same coupling as _settings(): the single-object verdict responders
        # in this file only speak the size-1 parser's format.
        review_batch_size=1,
        database_url="postgresql+asyncpg://user:pw@staging-db:5432/cyo_adventure",
        oidc_issuer="https://issuer.example.com",
        oidc_jwks_url="https://issuer.example.com/jwks.json",
        child_session_secret="a" * 32,
        device_grant_secret="b" * 32,
    )

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=escape_hatch_settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["reviewer_independent"] is False
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    mock_reviewer_findings = [
        f for f in findings if f.get("concern") == "mock_reviewer_active"
    ]
    assert len(mock_reviewer_findings) == 1
    finding = mock_reviewer_findings[0]
    assert finding["structural"] is True
    assert finding["verdict"] == "advisory"
    assert finding["source"] == "pipeline"


@pytest.mark.unit
async def test_mock_review_stamps_report_as_not_independent_in_local(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The mock stamp must NOT depend on ``environment``.

    Regression for the twelve books stuck at the review gate since
    2026-07-21 with 2,916 fail-safe nodes and
    ``summary.reviewer_independent: true``
    (docs/planning/safety/moderation-review-current-state-2026-08-25.md
    section 6).

    The stamp and ``config._require_real_reviewer_outside_local`` were BOTH
    gated on ``environment != "local"``, and both read ``environment`` and
    ``review_provider`` off the same ``Settings`` object. That object declares
    no ``env_file`` at all, so it sees exported process environment variables
    and nothing else: a process started without them exported gets
    ``review_provider="mock"`` (config.py's default) AND
    ``environment="local"`` in the same instant, from one absence, and both
    defenses go quiet together. The guard does not raise, the stamp does not
    apply, and the persisted report claims an independent reviewer while
    every node carries "unknown verdict; defaulted to fail-safe" from the
    mock's fixed "{}" body.

    A mock review is not an independent review in local either, so the stamp
    applies unconditionally. Its ADVISORY finding never gates, but its other
    half, ``reviewer_independent = False``, does: a story moderated with the
    mock is unapprovable afterwards, deliberately.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    local_mock_settings = Settings(
        review_provider="mock",
        environment="local",
        review_batch_size=1,
        database_url="postgresql+asyncpg://user:pw@localhost:5432/cyo_adventure",
        oidc_issuer="https://issuer.example.com",
        oidc_jwks_url="https://issuer.example.com/jwks.json",
        child_session_secret="a" * 32,
        device_grant_secret="b" * 32,
    )

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=local_mock_settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["reviewer_independent"] is False
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    mock_reviewer_findings = [
        f for f in findings if f.get("concern") == "mock_reviewer_active"
    ]
    assert len(mock_reviewer_findings) == 1


@pytest.mark.unit
async def test_a_real_reviewer_in_local_is_not_stamped(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The negative control for the two stamp tests above.

    Those two prove the stamp fires in staging and in local. Neither can tell
    a correctly targeted stamp from one that fires on every run: a
    ``_stamp_mock_reviewer`` call with its ``review_provider == "mock"``
    condition deleted would pass both. This runs the identical pipeline with
    the ONLY difference being a real provider, and requires the stamp's two
    halves to be absent.

    ``environment`` is held at ``"local"`` deliberately, so this differs from
    ``test_mock_review_stamps_report_as_not_independent_in_local`` in exactly
    one field. The seam still injects the same real-verdict responder, so the
    verdicts are identical too and only the declared provider moves.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    def _clean_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [{"flagged": False, "categories": {}, "category_scores": {}}]
            },
        )

    # Configuring `openai_api_key` below is what makes Stage 0 actually call
    # out, unlike the mock-provider tests above which configure no classifier
    # key at all. Without this canned transport the run reaches
    # api.openai.com, which unit tests must never do.
    _install_canned_classifier_http(monkeypatch, _clean_handler)

    local_real_settings = Settings(
        review_provider="openrouter",
        environment="local",
        # Required by `_require_classifier_when_reviewing`: any non-mock
        # reviewer must have a Stage-0 classifier configured in front of it,
        # so Settings refuses to construct without this.
        openai_api_key="sk-test-classifier",
        openrouter_api_key="sk-or-test",
        review_batch_size=1,
        database_url="postgresql+asyncpg://user:pw@localhost:5432/cyo_adventure",
        oidc_issuer="https://issuer.example.com",
        oidc_jwks_url="https://issuer.example.com/jwks.json",
        child_session_secret="a" * 32,
        device_grant_secret="b" * 32,
    )

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=local_real_settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["reviewer_independent"] is True
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    assert not [f for f in findings if f.get("concern") == "mock_reviewer_active"]


@pytest.mark.unit
async def test_soft_flag_triggers_repair_then_submits(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A soft FLAG triggers repair; if repair succeeds and re-moderation is clean,
    submit is awaited and the report carries repaired=True.

    Runs the REAL repair path: safety FLAGs every node on the first pass,
    the real ``attempt_repair`` re-prompts the generation provider (a
    MockProvider queued with a revised, schema-valid blob), and the
    re-moderation pass comes back clean.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["repaired"] is True


@pytest.mark.unit
async def test_mock_review_stamp_survives_adopted_repair(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The gap-G1 mock-reviewer stamp must survive an ADOPTED repair.

    An adopted repair replaces the pipeline's ``report`` wholesale with the
    fresh report built inside ``_attempt_and_adopt_repair``, and it is that
    report which gets persisted. Stamping only the pre-repair report therefore
    lost the stamp on exactly the stories most likely to have it: under the
    mock reviewer every Stage-1 node fail-safes, so a soft flag (and hence the
    repair branch) is the normal case, not the exception.

    Unlike ``test_mock_review_escape_hatch_stamps_report_as_not_independent``
    (which deliberately avoids the repair branch), this drives the REAL repair
    path: safety FLAGs every node on the first pass, ``attempt_repair``
    re-prompts the generation provider with a schema-valid revision, and the
    revision is adopted. The assertions are on the PERSISTED report.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    escape_hatch_settings = Settings(
        review_provider="mock",
        environment="staging",
        allow_mock_review=True,
        # Same coupling as _settings(): the single-object verdict responders
        # in this file only speak the size-1 parser's format.
        review_batch_size=1,
        database_url="postgresql+asyncpg://user:pw@staging-db:5432/cyo_adventure",
        oidc_issuer="https://issuer.example.com",
        oidc_jwks_url="https://issuer.example.com/jwks.json",
        child_session_secret="a" * 32,
        device_grant_secret="b" * 32,
    )

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=escape_hatch_settings,
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    # The repair really was adopted: without this the test would pass
    # vacuously on the pre-repair report.
    assert summary["repaired"] is True
    assert version.blob["title"] == "The Forest Path (revised)"
    # Both halves of the stamp survive onto the persisted report.
    assert summary["reviewer_independent"] is False
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    mock_reviewer_findings = [
        f for f in findings if f.get("concern") == "mock_reviewer_active"
    ]
    assert len(mock_reviewer_findings) == 1
    finding = mock_reviewer_findings[0]
    assert finding["structural"] is True
    assert finding["verdict"] == "advisory"
    assert finding["source"] == "pipeline"


@pytest.mark.unit
async def test_structural_only_soft_flag_skips_repair_and_submits(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A structural-only soft flag makes no repair call and auto-rejects.

    The degraded-reviewer case: every Stage-1 safety call fails to parse, the
    stage collapses them into one structural FLAG, and nothing in the prose was
    actually judged.

    Two separate things must hold, and until 2026-08-27 only the first did.

    No repair: re-prompting the generator with "- node None (pipeline):
    reviewer unavailable ..." spends a full generation budget on a meaningless
    instruction and risks replacing the persisted blob with its output. The
    generation provider here has no queued responses, so ``MockProvider``
    raises loudly if the repair path is ever entered.

    No submit: this test previously asserted ``submit``, on the reasoning that
    "routing is unchanged, the story still soft-flags to a human". That is the
    fail-open. A story nobody judged is not a soft flag; it arrives in the
    review queue looking like an ordinary "review when convenient" item, and
    the re-moderation sweep exits 0 on it. Four books in the live catalog sat
    in exactly that state with eight unscreened nodes each. It must
    auto-reject, which is the outcome that names the run as needing to be
    redone rather than reviewed.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)

    def _respond(prompt: str) -> str:
        # Stage 1 (safety) bodies are unparseable -> per-node fail-safe, which
        # the stage collapses into a single structural FLAG. Every other stage
        # returns a genuine passing verdict, so the structural finding is the
        # report's ONLY soft flag.
        if prompt.startswith("Age band:"):
            return "{}"
        return '{"verdict": "pass", "reason": "ok"}'

    review_seam(MockProvider(responses=[_respond] * _REVIEW_BUDGET))
    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    original_blob = copy.deepcopy(version.blob)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    # The persisted flags still describe the findings truthfully: the only
    # gating finding IS a soft flag, and no BLOCK was invented. What changed is
    # that coverage now routes, so the truthful summary and the auto-reject can
    # coexist. coverage_complete is the field that distinguishes them.
    assert summary["soft_flag"] is True
    assert summary["hard_block"] is False
    assert summary["coverage_complete"] is False
    assert summary["repaired"] is False
    assert version.blob == original_blob, (
        "the repair path must not have rewritten prose no reviewer read"
    )
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    soft = [f for f in findings if f["verdict"] == "flag"]
    assert soft
    assert all(f["structural"] is True for f in soft)


@pytest.mark.unit
async def test_invalid_blob_routes_to_auto_reject(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stored blob that fails schema validation is force-blocked to auto_reject,
    not allowed to raise out of the pipeline and strand the story in draft."""
    story = _story()
    bad_version = StorybookVersion(
        storybook_id="s1", version=1, blob={"garbage": True}, model="gen-model"
    )
    _load(mock_session, story, bad_version)
    auto_reject = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    assert bad_version.moderation_report is not None
    assert bad_version.moderation_report["summary"]["hard_block"] is True


@pytest.mark.unit
async def test_entry_forged_sentinel_in_clean_blob_routes_to_human_review(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """(Task 6a) The universal at-rest sentinel-integrity backstop at
    moderation entry catches a well-formed-but-undeclared sentinel in a
    CLEANLY-MODERATING blob (no soft flag at all, e.g. a cyo-author import):
    before this change, Variant B ran only inside the repair path, so a blob
    that never soft-flags got ZERO automated sentinel checks. No
    ``GenerationJob`` is wired (``_load``'s dormant default), so the declared
    personalizable-slot set resolves to the empty set, matching every real
    skeleton today: the sentinel below is necessarily forged against it.
    """
    story, version = _story(), _version()
    tainted_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", tainted_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = f"{start_node['body']} {wrap('HERO', 'Ada')}"
    version.blob = tainted_blob
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())  # no soft flag: an otherwise-clean pass

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    assert moderation_report["summary"]["hard_block"] is True
    categories = {
        f["category"]
        for f in cast("list[dict[str, object]]", moderation_report["findings"])
    }
    assert "sentinel_integrity_violation" in categories
    # Never auto-adopted/auto-published: the stored blob is untouched.
    assert version.blob == tainted_blob


@pytest.mark.unit
async def test_stage0_classifiers_skipped_when_already_hard_blocked_at_entry(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """(Task 6b, Minor efficiency carried from the 6a review) A report that is
    ALREADY hard-blocked before ``_run_all_stages`` runs (here, the Task 6a
    moderation-entry sentinel-integrity backstop firing on a forged sentinel
    in an otherwise-clean blob) must skip the Stage-0 external classifier
    calls entirely: the verdict is already fixed at auto_reject, so an
    OpenAI Moderation / Google Perspective call here would be a wasted paid
    request. ``openai_api_key`` is configured (unlike the sibling entry-
    backstop tests) precisely so the classifier WOULD be invoked here if the
    short-circuit were missing or broken.
    """
    story, version = _story(), _version()
    tainted_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", tainted_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = f"{start_node['body']} {wrap('HERO', 'Ada')}"
    version.blob = tainted_blob
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())

    classifier_called = {"count": 0}

    def _handler(_request: httpx.Request) -> httpx.Response:
        classifier_called["count"] += 1
        return httpx.Response(
            200,
            json={
                "results": [{"flagged": False, "categories": {}, "category_scores": {}}]
            },
        )

    _install_canned_classifier_http(monkeypatch, _handler)

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=Settings(review_provider="mock", openai_api_key="k"),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    assert classifier_called["count"] == 0, (
        "Stage 0 classifiers must not run once a hard block already exists"
    )
    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    assert moderation_report["summary"]["hard_block"] is True


@pytest.mark.unit
async def test_entry_contract_unrecoverable_routes_to_human_review(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """(Task 6a) An unrecoverable personalizable-slot contract (a
    ``GenerationJob`` naming a ``skeleton_slug`` but missing its
    ``skeleton_band``) fails the moderation entry closed even for an
    otherwise completely clean, sentinel-free blob: ``None`` means the entry
    check cannot prove the blob's sentinel content is safe, so it must never
    auto-adopt/auto-publish, exactly mirroring the repair gate's own
    fail-closed posture on the same resolver result.
    """
    story, version = _story(), _version()
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band
    )
    _load(mock_session, story, version, job=job)
    review_seam(_verdict_review_provider())  # no soft flag: an otherwise-clean pass

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    categories = {
        f["category"]
        for f in cast("list[dict[str, object]]", moderation_report["findings"])
    }
    assert "sentinel_integrity_violation" in categories
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_run_moderation_pipeline_honors_explicit_personalizable_slots(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """(Task 6c, I1) An explicitly-threaded, non-default ``personalizable_slots``
    is honored VERBATIM and skips the database resolver entirely.

    No ``GenerationJob`` is wired (``_load``'s dormant default), so if this
    call fell back to ``personalizable_slot_ids_for_story`` the resolver
    would answer the empty set and the ``HERO`` sentinel below would be
    wrongly flagged ``unknown_slot`` -- exactly the resume-path timing bug
    (I1) the whole-branch review found: on that path, the GenerationJob is
    not yet linked to the story id at the moment moderation runs, so the
    resolver sees "no job" even though the fill legitimately declares a
    personalizable slot. Passing the caller's own resolution (as
    ``resume_manual_fill`` now does) bypasses that timing gap by construction.
    """
    story, version = _story(), _version()
    tainted_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", tainted_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = f"{start_node['body']} {wrap('HERO', 'Ada')}"
    version.blob = tainted_blob
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())

    resolver_called = False
    real_resolver = pipeline_mod.personalizable_slot_ids_for_story

    async def _spy_resolver(
        session: AsyncSession, story_id: str
    ) -> PersonalizableSlots:
        nonlocal resolver_called
        resolver_called = True
        return await real_resolver(session, story_id)

    monkeypatch.setattr(
        pipeline_mod, "personalizable_slot_ids_for_story", _spy_resolver
    )

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
        personalizable_slots=frozenset({"HERO"}),
    )

    assert not resolver_called, (
        "an explicit personalizable_slots must skip personalizable_slot_ids_for_story"
    )
    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    categories = {
        f["category"]
        for f in cast("list[dict[str, object]]", moderation_report["findings"])
    }
    assert "sentinel_integrity_violation" not in categories
    assert version.blob == tainted_blob


@pytest.mark.unit
async def test_run_moderation_pipeline_explicit_unrecoverable_fails_closed(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """(Task 6c, M1) An explicit ``PERSONALIZABLE_SLOTS_UNRECOVERABLE`` fails
    closed at the entry backstop, even for an otherwise completely clean,
    sentinel-free blob, and without ever consulting
    ``personalizable_slot_ids_for_story``.

    Mirrors ``test_entry_contract_unrecoverable_routes_to_human_review``'s
    routing assertion, but for a CALLER-supplied marker (the shape
    ``resume_manual_fill`` now threads when its own contract resolution is
    genuinely uncomputable) rather than one this function resolves itself.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())

    resolver_called = False
    real_resolver = pipeline_mod.personalizable_slot_ids_for_story

    async def _spy_resolver(
        session: AsyncSession, story_id: str
    ) -> PersonalizableSlots:
        nonlocal resolver_called
        resolver_called = True
        return await real_resolver(session, story_id)

    monkeypatch.setattr(
        pipeline_mod, "personalizable_slot_ids_for_story", _spy_resolver
    )

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
        personalizable_slots=PERSONALIZABLE_SLOTS_UNRECOVERABLE,
    )

    assert not resolver_called, (
        "an explicit personalizable_slots (even the fail-closed marker) must "
        "skip the resolver"
    )
    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    categories = {
        f["category"]
        for f in cast("list[dict[str, object]]", moderation_report["findings"])
    }
    assert "sentinel_integrity_violation" in categories
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_run_moderation_pipeline_none_slots_fails_closed(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A literal ``None`` fails closed exactly as the marker does.

    ``None`` is the RETIRED spelling of the fail-closed arm and is no longer a
    member of ``PersonalizableSlotsArg``, but ``tests/`` is type-checked by no
    gate here (basedpyright's ``include = ["src"]``), so an untyped or stale
    caller can still supply it. Between the two ``isinstance`` narrowings it
    matched neither, fell through to ``check_sentinel_integrity_at_rest``,
    and on this sentinel-free blob returned ok=True: the story submitted
    clean with no entry-level check at all. Mirrors
    ``test_run_moderation_pipeline_explicit_unrecoverable_fails_closed``,
    which is the arm ``None`` must now share.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
        # Deliberately off-contract: the retired spelling an untyped caller
        # can still reach this security control with.
        personalizable_slots=None,
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    categories = {
        f["category"]
        for f in cast("list[dict[str, object]]", moderation_report["findings"])
    }
    assert "sentinel_integrity_violation" in categories
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_run_moderation_pipeline_default_resolves_from_story(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """(Task 6c dormancy) Omitting ``personalizable_slots`` entirely -- every
    caller except ``resume_manual_fill`` -- still resolves via
    ``personalizable_slot_ids_for_story``, exactly as before Task 6c.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())

    resolver_called = False
    real_resolver = pipeline_mod.personalizable_slot_ids_for_story

    async def _spy_resolver(
        session: AsyncSession, story_id: str
    ) -> PersonalizableSlots:
        nonlocal resolver_called
        resolver_called = True
        return await real_resolver(session, story_id)

    monkeypatch.setattr(
        pipeline_mod, "personalizable_slot_ids_for_story", _spy_resolver
    )

    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    assert resolver_called, (
        "omitting personalizable_slots must still resolve via "
        "personalizable_slot_ids_for_story (dormancy)"
    )
    submit.assert_awaited_once()


@pytest.mark.unit
async def test_classifier_and_review_stage_receive_stripped_sentinel_text(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """(Task 6a) A node body carrying a sentinel is stripped before it
    reaches the Stage-0 classifiers AND the LLM review stages, mirroring
    ``moderation/rescreen.py``'s existing strip. Before this change, initial
    classifier/review scores were computed on sentinel-noisy text while a
    later rescreen scored the same content stripped, the exact comparability
    break rescreen's own strip exists to prevent. The STORED blob is left
    with the sentinel intact: only the classifier/review INPUT copy is
    stripped.

    ``personalizable_slot_ids_for_story`` is patched to declare ``HERO``
    personalizable (Task 6b): without a declared slot, this fixture's
    sentinel trips the moderation-entry Variant B backstop (Task 6a) as an
    ``unknown_slot`` hard block, and Task 6b's Stage-0 short-circuit would
    then legitimately skip the classifier call this test wants to inspect,
    which is exactly the case the dedicated
    ``test_stage0_classifiers_skipped_when_already_hard_blocked_at_entry``
    test covers instead.
    """
    story, version = _story(), _version()
    tainted_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", tainted_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = f"{start_node['body']} {wrap('HERO', 'Ada')}"
    version.blob = tainted_blob
    _load(mock_session, story, version)
    monkeypatch.setattr(
        pipeline_mod,
        "personalizable_slot_ids_for_story",
        AsyncMock(return_value=frozenset({"HERO"})),
    )

    captured_classifier_bodies: list[bytes] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_classifier_bodies.append(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        # A non-empty categories dict: the real OpenAI
                        # Moderation API always returns every category with a
                        # boolean value, so an empty dict is a malformed
                        # response shape (gap G11), not a clean-scan
                        # shorthand; classifiers.py now raises
                        # ClassifierUnavailable on it.
                        "flagged": False,
                        "categories": {"violence": False},
                        "category_scores": {"violence": 0.01},
                    }
                ]
            },
        )

    _install_canned_classifier_http(monkeypatch, _handler)
    provider = _verdict_review_provider()
    review_seam(provider)

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=Settings(review_provider="mock", openai_api_key="k"),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    assert captured_classifier_bodies, "the classifier HTTP call was never made"
    for body in captured_classifier_bodies:
        assert b"{~" not in body
    for prompt in provider.calls:
        assert "{~" not in prompt
    # The stored blob is untouched: only the classifier/review input copy
    # was stripped, never the persisted blob.
    assert version.blob == tainted_blob


@pytest.mark.unit
async def test_invalid_repair_is_discarded_and_original_report_submits(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A repair that yields a schema-invalid blob is discarded: the original
    soft-flagged report drives routing (submit), repaired stays False, and the
    invalid revision is never persisted to the version row.

    Runs the REAL ``attempt_repair``: the generation provider returns a JSON
    object that is not a valid Storybook, so re-moderation raises
    ValidationError and the revision is dropped by the pipeline.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    # Repair yields a structurally invalid blob (parses as JSON, fails schema).
    generation_provider = MockProvider(responses=[json.dumps({"garbage": True})])

    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["repaired"] is False
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_persisted_report_merges_identical_findings_across_nodes(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """Task B1.4: the persist site runs merge_findings before persistence.

    Reuses the same "safety flags every node, repair discarded" scenario as
    test_invalid_repair_is_discarded_and_original_report_submits so the
    original (unrepaired) report -- one identical safety FLAG per node -- is
    what reaches the persist site. Before the merge stage this would persist
    one finding per node; after it, the identical (category, concern)
    findings collapse into a single finding whose node_ids names every
    affected node.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    generation_provider = MockProvider(responses=[json.dumps({"garbage": True})])
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    assert version.moderation_report is not None
    findings = cast("list[dict[str, object]]", version.moderation_report["findings"])
    safety_findings = [f for f in findings if f.get("category") == "safety"]
    assert len(safety_findings) == 1
    merged = safety_findings[0]
    assert merged["node_ids"] is not None
    assert len(cast("list[str]", merged["node_ids"])) == _NODE_COUNT
    assert "findings merged" in cast("str", merged["message"])


@pytest.mark.unit
async def test_repair_failing_gate_is_discarded_and_routes_to_human_review(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A repair that is schema-valid and re-moderates clean but breaks graph
    topology is still rejected: the deterministic gate re-runs on the
    repaired blob before it can replace the pre-repair one (owner ruling
    2026-07-16), a blocked gate is treated exactly like a schema-invalid
    revision, and the job routes to human review (submit), never silent
    acceptance and never auto-publish.

    The revised blob points ``c_follow``'s target at a node id that does not
    exist in the story; ``StoryModel.model_validate`` and the mocked review
    stages do not check reference integrity (only ``validator.gate.run_gate``
    -- specifically L1 -- does), so this blob would have been silently
    adopted before the fix and is rejected after it.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    broken_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", broken_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    choices = cast("list[dict[str, object]]", start_node["choices"])
    choices[0]["target"] = "n_does_not_exist"
    generation_provider = MockProvider(responses=[json.dumps(broken_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    # Rejected repair routes exactly like the pre-repair soft-flagged report:
    # human review via submit, never auto_reject and never silent acceptance.
    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["repaired"] is False
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_repair_identity_mismatch_is_discarded(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A repair that is schema-valid, re-moderates clean, and passes the gate but
    is a DIFFERENT story (identity swapped) is rejected, not adopted.

    Models the all-mock-provider hazard: the imported content is one story, and
    the mock generation provider returns its canned stub story (``_CANNED_STORY``,
    a different id), which is schema-valid and gate-clean and would otherwise
    wholesale-replace the imported blob (storybook.id no longer matching
    version.blob.id). The identity guard must discard the stub so the pre-repair
    soft-flagged report routes to human review (submit) with the original blob
    intact.
    """
    story = _story()
    # The imported content is a distinct story, not the mock stub.
    imported_blob = copy.deepcopy(_BLOB)
    imported_blob["id"] = "sk_imported_original"
    version = StorybookVersion(
        storybook_id="s1", version=1, blob=imported_blob, model="gen-model"
    )
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    # The mock generation provider returns its canned stub (id "s_mock_generated"):
    # schema-valid and gate-clean, but a different story than the import.
    stub = copy.deepcopy(_BLOB)
    generation_provider = MockProvider(responses=[json.dumps(stub)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["repaired"] is False
    # The imported content is preserved, not silently swapped for the stub.
    assert version.blob == imported_blob


@pytest.mark.unit
async def test_repair_passing_gate_is_adopted(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A repair that is schema-valid, re-moderates clean, AND passes the
    deterministic gate is adopted: existing accept-a-good-repair behavior is
    preserved after wiring the gate re-run into the adoption seam.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["repaired"] is True
    assert version.blob == revised_blob


# ---------------------------------------------------------------------------
# ADR-023 plan 3.3 (Task 4b sub-task 2): the repair re-check must not adopt a
# repair that forges an undeclared sentinel, must fail closed when the
# story's contract genuinely cannot be recovered, and must still adopt a
# repair that preserves a genuinely declared sentinel verbatim, using the
# story's REAL personalizable-slot-id set (never an empty placeholder).
# ---------------------------------------------------------------------------


def _personalizable_contract() -> ThemeContract:
    """A minimal contract declaring one ``kind="personalizable"`` HERO slot."""
    return ThemeContract(
        contract_version=1,
        skeleton_slug="themed-slug",
        age_band=AgeBand.BAND_8_11,
        legacy_lexicon=[],
        default_binding={"HERO": "Ada"},
        slots=[
            SlotSpec(
                id="HERO",
                scope=SlotScope.GLOBAL,
                meaning="the reader's own child, personalized",
                kind="personalizable",
                personalization_field="protagonist_first_name",
                role_safety="protagonist",
            ),
        ],
    )


def _personalizable_skeleton() -> dict[str, object]:
    """A skeleton whose ``{HERO}`` beats token matches `_personalizable_contract`."""
    return {
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    "<<FILL role=setup words=40 beats='The hero, {HERO}, "
                    "arrives and must choose a path.'>>"
                ),
                "choices": [],
            },
        ],
    }


def _wire_personalizable_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> GenerationJob:
    """Write a real contract sidecar to ``tmp_path`` and wire the loader seam.

    Mirrors tests/unit/test_worker.py's
    ``_personalizable_dispatch_contract``/``_personalizable_dispatch_skeleton``
    pattern: ``resolve_skeleton_path``/``load_skeleton`` are monkeypatched (so
    no real skeleton file is needed), but ``load_contract_for``'s own sidecar
    read is the REAL function reading a REAL file, so the contract-loading
    chain ``personalizable_slot_ids_for_story`` drives is genuinely exercised
    end to end, not stubbed out.

    Returns:
        A ``GenerationJob`` row whose ``authoring_metadata`` names the wired
        skeleton, ready to pass to ``_load(..., job=...)``.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(
        _personalizable_contract().model_dump_json().encode("utf-8")
    )

    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(
        pslots_mod, "load_skeleton", lambda _path: _personalizable_skeleton()
    )
    return GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={
            "skeleton_slug": "themed-slug",
            "skeleton_band": "8-11",
        },
    )


@pytest.mark.unit
async def testpersonalizable_slot_ids_for_job_band_override_recovers_missing_metadata_band(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(Task 6c, I2) A ``band`` override recovers the contract even when the
    job's own ``authoring_metadata`` has no ``skeleton_band`` key at all.

    Mirrors ``resume_manual_fill``'s own situation: a job that predates the
    ``skeleton_band`` authoring_metadata key falls back to the request's
    brief band via ``_resolve_resume_band``, and that resolution -- not the
    (absent) raw metadata key -- must be what determines the contract. Before
    Task 6c, only ``personalizable_slot_ids_for_story`` existed, which reads
    ONLY the raw metadata key and would resolve the fail-closed marker for
    this exact job, even though the contract is perfectly recoverable via the
    caller's own better-informed band.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(
        _personalizable_contract().model_dump_json().encode("utf-8")
    )
    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(
        pslots_mod, "load_skeleton", lambda _path: _personalizable_skeleton()
    )
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band key
    )

    # Without the override, this is the pre-Task-6c fail-closed answer.
    assert (
        pslots_mod.personalizable_slot_ids_for_job(job)
        is PERSONALIZABLE_SLOTS_UNRECOVERABLE
    )

    # With the caller's own resolved band, the SAME contract recovers cleanly.
    result = pslots_mod.personalizable_slot_ids_for_job(job, band="8-11")
    assert result == frozenset({"HERO"})


@pytest.mark.unit
async def testpersonalizable_slot_ids_for_job_no_override_reads_metadata_band(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(Task 6c dormancy) With no ``band`` override, behavior is unchanged:
    the raw ``authoring_metadata`` key is read, matching every non-resume
    caller (which has no better band to offer).
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(
        _personalizable_contract().model_dump_json().encode("utf-8")
    )
    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(
        pslots_mod, "load_skeleton", lambda _path: _personalizable_skeleton()
    )
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug", "skeleton_band": "8-11"},
    )

    assert pslots_mod.personalizable_slot_ids_for_job(job) == frozenset({"HERO"})


@pytest.mark.unit
async def testpersonalizable_slot_ids_for_job_returns_none_when_contract_uncomputable(
    tmp_path: Path,
) -> None:
    """(Task 6c, M1) A ``skeleton_slug`` present but the skeleton file genuinely
    missing (even with a band override supplied) resolves ``None``, never a
    guessed empty set: this is the exact resolution ``resume_manual_fill``
    threads through to make the moderation entry fail closed on M1.
    """
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "does-not-exist"},
    )

    result = pslots_mod.personalizable_slot_ids_for_job(
        job, band=str(tmp_path / "nonexistent-band")
    )

    assert result is None


@pytest.mark.unit
async def test_repair_preserving_declared_sentinel_is_adopted(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
    tmp_path: Path,
) -> None:
    """A repair that copies a declared personalizable sentinel verbatim is
    still adopted: the new sentinel-integrity re-check (gate 3 of
    ``_repair_is_adoptable``) must not reject a genuine, unmutated sentinel
    resolved from the story's REAL contract.
    """
    job = _wire_personalizable_job(monkeypatch, tmp_path)
    sentinel = wrap("HERO", "Ada")
    original_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", original_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = f"{start_node['body']} {sentinel}"

    story = _story()
    version = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob=original_blob,
        model="gen-model",
        personalization_eligible=True,
    )
    _load(mock_session, story, version, job=job)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    revised_blob = copy.deepcopy(original_blob)
    revised_nodes = cast("list[dict[str, object]]", revised_blob["nodes"])
    revised_start = next(n for n in revised_nodes if n["id"] == "n_start")
    revised_start["body"] = f"{revised_start['body']} (revised)"
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["repaired"] is True
    assert version.blob == revised_blob
    assert sentinel in revised_start["body"]
    # Positive control for the recompute added alongside the adoption write:
    # the sentinel survived, so the flag must survive with it. Paired with
    # ::test_adopted_repair_clears_personalization_eligible_when_sentinels_lost,
    # which drives the same recompute the other way.
    assert version.personalization_eligible is True


@pytest.mark.unit
async def test_adopted_repair_clears_personalization_eligible_when_sentinels_lost(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
    tmp_path: Path,
) -> None:
    """An adopted repair that DROPS the story's last sentinel must clear
    ``personalization_eligible`` on the row it just rewrote.

    ``_repair_is_adoptable``'s sentinel check is a forged/unknown/malformed
    backstop and explicitly "cannot catch a DROPPED sentinel", so this repair
    is adopted, correctly. But the flag was derived at persist time from the
    PREVIOUS blob, and ``api/library.py`` reads it verbatim to advertise a
    personalization affordance. Without the recompute at the adoption write,
    the column would keep promising a slot the stored blob can no longer fill.
    """
    job = _wire_personalizable_job(monkeypatch, tmp_path)
    sentinel = wrap("HERO", "Ada")
    original_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", original_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    plain_body = cast("str", start_node["body"])
    start_node["body"] = f"{plain_body} {sentinel}"

    story = _story()
    version = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob=original_blob,
        model="gen-model",
        personalization_eligible=True,
    )
    _load(mock_session, story, version, job=job)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    # The repair rewrites the sentinel-bearing node back to plain prose: a
    # well-formed, gate-passing blob that simply no longer carries a sentinel.
    revised_blob = copy.deepcopy(original_blob)
    revised_nodes = cast("list[dict[str, object]]", revised_blob["nodes"])
    revised_start = next(n for n in revised_nodes if n["id"] == "n_start")
    revised_start["body"] = f"{plain_body} (revised)"
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["repaired"] is True
    assert version.blob == revised_blob
    assert sentinel not in revised_start["body"]
    assert version.personalization_eligible is False


@pytest.mark.unit
async def test_repair_forged_sentinel_is_discarded_and_routes_to_human_review(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A repair that introduces a well-formed sentinel with NO declared
    personalizable slot for this story is rejected as ``unknown_slot``,
    exactly like a gate failure: the pre-repair report and blob are preserved
    and the job routes to human review, never silent acceptance.

    No ``GenerationJob`` is wired (``_load``'s dormant default), so
    ``personalizable_slot_ids`` resolves to the empty set, matching every real
    skeleton today (dormancy fact): any well-formed sentinel a repair
    introduces is necessarily forged against that empty set.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    revised_blob = copy.deepcopy(_BLOB)
    nodes = cast("list[dict[str, object]]", revised_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = f"{start_node['body']} {wrap('HERO', 'Ada')}"
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["repaired"] is False
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_repair_contract_unrecoverable_is_discarded(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A ``GenerationJob`` that names a ``skeleton_slug`` but is missing its
    ``skeleton_band`` cannot be traced to a contract; the repair is
    fail-closed discarded rather than guessing an empty personalizable-slot
    set, per the brief's NEEDS_CONTEXT posture: an empty guess would falsely
    treat a genuine sentinel as forged.

    Since Task 6a, ``personalizable_slot_ids_for_story`` is resolved ONCE at
    moderation entry and reused for the repair gate; the SAME ``None``
    result that discards the repair now also fails the entry-level backstop
    closed, so this story routes to ``auto_reject``, not ``submit`` (the
    pre-Task-6a routing, when only the repair path ever saw this resolver's
    result).
    """
    story, version = _story(), _version()
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band
    )
    _load(mock_session, story, version, job=job)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["repaired"] is False
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_repair_contract_file_missing_is_discarded_and_routes_to_human_review(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
    tmp_path: Path,
) -> None:
    """A ``GenerationJob`` naming a ``skeleton_slug``/``skeleton_band`` whose
    skeleton file has since moved or been deleted must fail closed like
    every other unrecoverable-contract case, not crash the moderation pass.

    ``load_skeleton`` (generation/skeleton.py) does
    ``json.loads(path.read_text(...))``, which raises a raw
    ``FileNotFoundError`` (NOT ``CoreValidationError``) when the file the
    stale ``authoring_metadata`` points at no longer exists. Before the fix,
    ``personalizable_slot_ids_for_story`` only caught ``CoreValidationError``
    and this exception propagated uncaught through
    ``_attempt_and_adopt_repair``/``run_moderation_pipeline``, crashing the
    whole moderation pass. Mirrors
    ``generation/import_story.py::_load_resume_skeleton``'s handling of the
    same resolve-then-load chain.

    Since Task 6a, this same ``None`` resolution also fails the entry-level
    backstop closed (it is resolved once and reused), so this story routes
    to ``auto_reject``, not ``submit``.
    """
    story, version = _story(), _version()
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={
            "skeleton_slug": "themed-slug",
            "skeleton_band": "8-11",
        },
    )
    _load(mock_session, story, version, job=job)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))

    missing_path = tmp_path / "themed-slug.json"
    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: missing_path
    )

    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["repaired"] is False
    assert version.blob == _BLOB


@pytest.mark.unit
async def test_review_model_override_reaches_build_review_provider(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """review_model_override is threaded through to build_review_provider's settings.

    The spy returns a deterministic verdict provider instead of delegating to
    the real builder: with ``review_provider="openrouter"`` the real builder
    would construct a live network-backed leg, which a unit test must never
    call once the real stages run against it.
    """
    captured: dict[str, object] = {}
    provider = _verdict_review_provider()

    def _spy(settings: Settings, **_kwargs: object) -> tuple[MockProvider, bool]:
        captured["review_openrouter_model"] = settings.review_openrouter_model
        return provider, True

    monkeypatch.setattr("cyo_adventure.moderation.pipeline.build_review_provider", _spy)

    story, version = _story(), _version()
    _load(mock_session, story, version)

    # The openrouter review backend requires a classifier key at Settings
    # validation time, so Stage 0 runs for real; serve it a canned clean
    # OpenAI Moderation response.
    def _clean_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        # Non-empty categories: see the identical comment in
                        # test_classifier_and_review_stage_receive_stripped_sentinel_text
                        # (gap G11, empty dict now raises ClassifierUnavailable).
                        "flagged": False,
                        "categories": {"violence": False},
                        "category_scores": {"violence": 0.01},
                    }
                ]
            },
        )

    _install_canned_classifier_http(monkeypatch, _clean_handler)

    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    settings_with_openrouter_backend = Settings(
        review_provider="openrouter",
        openai_api_key="k",
        openrouter_api_key="key",
        # Same pin _settings() carries, and for the reason
        # _verdict_review_provider's docstring spells out: that responder
        # answers with a single verdict OBJECT, which the batched parser
        # rejects, so at the Settings default of 8 every node fail-safes. This
        # test builds its own Settings and so missed the pin, which went
        # unnoticed while a fail-safe FLAG and a genuine one were
        # indistinguishable to routing. They no longer are: a fail-safe now
        # auto-rejects, so the missing pin surfaces as this test failing.
        review_batch_size=1,
    )

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings_with_openrouter_backend,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
        review_model_override="anthropic/claude-opus-4.8",
    )

    assert captured["review_openrouter_model"] == "anthropic/claude-opus-4.8"
    submit.assert_awaited_once()


@pytest.mark.unit
async def test_the_pipeline_persists_the_reviewer_that_ran(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stored report must name its own reviewer, resolved override included.

    The 2026-07-21 sweep persisted no reviewer provenance, so 31 books' reports
    were indistinguishable from genuinely reviewed ones and the population had
    to be re-derived from a stamp that existed for an unrelated reason
    (UW-C408). Provenance is read from the RESOLVED settings, which is why this
    test drives the same admin override as the test above it: recording the
    process-wide default would attribute the verdict to a model that never saw
    the prose, a quieter version of the same defect.

    The seam is the same spy: with ``review_provider="openrouter"`` the real
    builder would construct a live network-backed leg, which a unit test must
    never call.
    """
    provider = _verdict_review_provider()

    def _spy(_settings: Settings, **_kwargs: object) -> tuple[MockProvider, bool]:
        return provider, True

    monkeypatch.setattr("cyo_adventure.moderation.pipeline.build_review_provider", _spy)

    story, version = _story(), _version()
    _load(mock_session, story, version)

    def _clean_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "categories": {"violence": False},
                        "category_scores": {"violence": 0.01},
                    }
                ]
            },
        )

    _install_canned_classifier_http(monkeypatch, _clean_handler)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=Settings(
            review_provider="openrouter",
            openai_api_key="k",
            openrouter_api_key="key",
            # Same size-1 pin, same reason as the test above: the fixture
            # answers with a single verdict OBJECT, which the batched parser
            # rejects.
            review_batch_size=1,
        ),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
        review_model_override="anthropic/claude-opus-4.8",
    )

    assert version.moderation_report is not None
    assert version.moderation_report["reviewer"] == {
        "provider": "openrouter",
        "model": "anthropic/claude-opus-4.8",
        # Empty because that slug carries no `ENDPOINT_PINS` entry. Asserted
        # rather than skipped: an unpinned reviewer is a real reproducibility
        # gap, and the stored report is where it stays visible.
        "endpoint": [],
        "temperature": 0.0,
        "batch_size": 1,
    }


# ---------------------------------------------------------------------------
# WS-1 D1: the advisory leaf-diversity (anti-template) guard wiring.
#
# load_family_history/load_version_blob are monkeypatched at the
# moderation.leaf_diversity import site (design doc section 6): the real
# run_leaf_diversity_check and findings_from_anti_template execute, only the
# two DB reads are doubled, keeping this file's AsyncMock session simple.
# ---------------------------------------------------------------------------


def _version_with_slug(
    skeleton_slug: str | None = "the-cave-of-echoes",
) -> StorybookVersion:
    return StorybookVersion(
        storybook_id="s1",
        version=1,
        blob=_BLOB,
        model="gen-model",
        skeleton_slug=skeleton_slug,
    )


def _history_entry(
    *, storybook_id: str = "other-book", skeleton_slug: str = "the-cave-of-echoes"
) -> HistoryEntry:
    return HistoryEntry(
        storybook_id=storybook_id,
        version=5,
        skeleton_slug=skeleton_slug,
        theme_sig=frozenset(),
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


@pytest.mark.unit
async def test_atg_fail_triggers_single_repair_then_submit(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A same-tree ATG FAIL (partner blob identical to the current draft, so
    every node's masked distance is 0.0) drives exactly one bounded repair
    through the real per-node FLAG findings, then submit.

    The ATG seam (``run_leaf_diversity_check``) is spied rather than stubbed
    (``AsyncMock(side_effect=...)`` wrapping the real function), so this also
    proves the "run once, never re-run on the repaired blob" contract
    (design doc section 3.6): the seam must be invoked exactly once even
    though ``_run_all_stages`` runs twice (initial pass plus post-repair
    re-moderation).
    """
    story, version = _story(), _version_with_slug()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())

    partner_blob = copy.deepcopy(_BLOB)
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_family_history",
        AsyncMock(return_value=[_history_entry()]),
    )
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_version_blob",
        AsyncMock(return_value=partner_blob),
    )
    atg_spy = AsyncMock(side_effect=_real_run_leaf_diversity_check)
    monkeypatch.setattr(pipeline_mod, "run_leaf_diversity_check", atg_spy)

    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    assert atg_spy.await_count == 1
    assert len(generation_provider.calls) == 1
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["repaired"] is True
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    leaf_flags = [f for f in findings if f.get("category") == "leaf_diversity"]
    leaf_summaries = [
        f for f in findings if f.get("category") == "leaf_diversity_summary"
    ]
    # The adopted repaired_report replaces `report` wholesale (pipeline.py:196)
    # and the ATG is not re-run on it (design doc section 3.6), so the
    # pre-repair ATG findings do not survive adoption (supervisor ruling,
    # section 10, OQ4 declined for v1): neither the per-node FLAGs nor the
    # summary ADVISORY appear in the persisted report.
    assert leaf_flags == []
    assert leaf_summaries == []


@pytest.mark.unit
async def test_atg_warn_is_advisory_no_repair(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """An ATG WARN (stubbed at the run_leaf_diversity_check seam) contributes
    only an ADVISORY finding: no repair is triggered, and the story still
    routes to submit exactly like any other clean-except-advisory pass."""
    story, version = _story(), _version_with_slug()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())

    warn_finding = pipeline_mod.Finding(
        stage=0,
        source=pipeline_mod.Source.PIPELINE,
        category="leaf_diversity_summary",
        verdict=pipeline_mod.Verdict.ADVISORY,
        message="anti-template guard warn vs storybook other-book v5",
    )
    monkeypatch.setattr(
        pipeline_mod,
        "run_leaf_diversity_check",
        AsyncMock(return_value=[warn_finding]),
    )

    generation_provider = MockProvider(responses=[])
    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    assert len(generation_provider.calls) == 0
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    assert summary["repaired"] is False
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    assert any(f.get("category") == "leaf_diversity_summary" for f in findings)


@pytest.mark.unit
async def test_atg_skipped_on_hard_block(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A hard block from Stage 1 safety skips the ATG guard entirely: the
    ``if not report.has_hard_block:`` gate at the call site must never invoke
    ``run_leaf_diversity_check`` once routing is already decided."""
    story, version = _story(), _version_with_slug()
    _load(mock_session, story, version)
    review_seam(_safety_block_review_provider())

    atg_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(pipeline_mod, "run_leaf_diversity_check", atg_mock)
    auto_reject = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    atg_mock.assert_not_awaited()


@pytest.mark.unit
async def test_atg_no_partner_path_matches_atg_fully_stubbed_noop(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The real ATG code's no-partner fail-open branch (empty family history)
    must leave the pipeline outcome byte-identical to a run where the ATG
    seam is stubbed out to return ``[]`` directly, proving the guard's
    error/no-op paths add nothing observable (design doc section 6)."""
    # Run A: the REAL run_leaf_diversity_check executes; the family has no
    # history at all, so it exits at the "no partner" fail-open branch.
    story_a, version_a = _story(), _version_with_slug()
    _load(mock_session, story_a, version_a)
    review_seam(_verdict_review_provider())
    monkeypatch.setattr(
        leaf_diversity_mod, "load_family_history", AsyncMock(return_value=[])
    )
    submit_a = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit_a)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    # Run B: the ATG seam is stubbed to return [] directly, bypassing every
    # internal branch (no history load, no partner selection, nothing).
    story_b, version_b = _story(), _version_with_slug()
    _load(mock_session, story_b, version_b)
    review_seam(_verdict_review_provider())
    monkeypatch.setattr(
        pipeline_mod, "run_leaf_diversity_check", AsyncMock(return_value=[])
    )
    submit_b = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit_b)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    submit_a.assert_awaited_once()
    submit_b.assert_awaited_once()
    assert version_a.moderation_report == version_b.moderation_report


# aggregate.nodes_reviewed: the coverage denominator (design doc 2.1).
# Once PASS findings stop being persisted as rows, this counter is the only
# signal distinguishing "reviewed everything and found nothing" from "never
# got there", so it must track actual coverage rather than intent.


def _aggregate(version: StorybookVersion) -> dict[str, object]:
    assert version.moderation_report is not None
    return cast("dict[str, object]", version.moderation_report["aggregate"])


@pytest.mark.unit
async def test_nodes_reviewed_counts_every_node_on_a_complete_pass(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A run that reaches the end reports coverage of the whole node list."""
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    aggregate = _aggregate(version)
    assert aggregate["nodes_reviewed"] == _NODE_COUNT
    # A complete clean pass also records the PASS rollup the counter denominates.
    assert aggregate["pass_counts"]


@pytest.mark.unit
async def test_nodes_reviewed_zero_when_stage0_block_short_circuits(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Stage-0 bright-line block never reviews a node, so coverage stays 0.

    Setting the counter beside the node list would have persisted full
    coverage here, claiming every node was reviewed by a safety stage that
    never ran.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)

    def _brightline_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "categories": {"sexual/minors": True},
                        "category_scores": {"sexual/minors": 0.99},
                    }
                ]
            },
        )

    _install_canned_classifier_http(monkeypatch, _brightline_handler)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", AsyncMock())
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=Settings(review_provider="mock", openai_api_key="k"),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    aggregate = _aggregate(version)
    assert aggregate["nodes_reviewed"] == 0
    # The empty PASS rollup beside it tells the same story, consistently.
    assert aggregate["pass_counts"] == {}


@pytest.mark.unit
async def test_nodes_reviewed_zero_when_stage1_block_short_circuits(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A Stage-1 safety block also leaves the review incomplete.

    Stage 1 blocks on its first node, so the later stages never run and the
    story has not been reviewed end to end even though Stage 0 passed.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_safety_block_review_provider())
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", AsyncMock())
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    assert version.moderation_report is not None
    summary = cast("dict[str, object]", version.moderation_report["summary"])
    assert summary["hard_block"] is True
    assert _aggregate(version)["nodes_reviewed"] == 0


# ---------------------------------------------------------------------------
# review_batch_size wiring (design doc 2.2 item 2): settings.review_batch_size
# reaches run_safety_stage through the pipeline call site.
# ---------------------------------------------------------------------------


def _extract_batch_node_ids(prompt: str) -> list[str]:
    """Pull node ids from a Stage-1 batch prompt's "[node_id] <untrusted_passage>" lines."""
    return [
        line[1 : line.index("]")]
        for line in prompt.splitlines()
        if line.startswith("[") and "]" in line
    ]


def _capture_events(monkeypatch: pytest.MonkeyPatch) -> list[MagicMock]:
    """Record every ``record_event`` call the pipeline makes, in order.

    Patched at the pipeline's own import site, not in ``events``, so the real
    writer stays intact for anything else and the mock_session (which has no
    working insert) is never asked to persist a row.
    """
    calls: list[MagicMock] = []

    async def _record(*args: object, **kwargs: object) -> None:
        call = MagicMock()
        call.args = args
        call.kwargs = kwargs
        calls.append(call)

    monkeypatch.setattr(pipeline_mod, "record_event", _record)
    return calls


def _one_bad_batch_review_provider(*, bad_batch_index: int = 0) -> MockProvider:
    """Answer every Stage-1 batch genuinely except ONE, which is unparseable.

    This is the production failure shape behind UW-C407. ``review_batch_size``
    defaults to 8, so a single unusable batch response costs all eight of its
    nodes their coverage while the rest of the story reviews normally. Five
    reports in the live catalog admitted exactly 8 or 16 unreviewed nodes, and
    that exact multiple is what identified the cause as batch-granular rather
    than node-granular flakiness.

    Since the per-node fallback landed, an unusable batch response alone no
    longer costs anybody their coverage: the stage retries each of that batch's
    nodes one at a time. So this double also refuses the retries for the bad
    batch's nodes specifically, which is the only shape that still reaches the
    pipeline as a real gap. Other batches' nodes keep answering normally, so a
    fallback that mistakenly widened its refusal to the whole story would show
    up as a different report rather than the same one.

    Args:
        bad_batch_index: Which Stage-1 batch call returns garbage, 0-based.
    """
    state = {"batches": 0}
    refused_prose: set[str] = set()

    def _passages(prompt: str) -> list[str]:
        return re.findall(
            r"<untrusted_passage>\n(.*?)\n</untrusted_passage>", prompt, re.DOTALL
        )

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:") and "Nodes:" in prompt:
            index = state["batches"]
            state["batches"] += 1
            if index == bad_batch_index:
                # Not a 5xx and not empty: a syntactically fine response the
                # batch parser cannot attribute. The provider raises on an
                # EMPTY truncation only, so a partial one arrives here as bad
                # JSON rather than as an error.
                refused_prose.update(_passages(prompt))
                return "sorry, I cannot review these passages"
            return json.dumps(
                [
                    {"verdict": "safe", "reason": "ok", "node_id": nid}
                    for nid in _extract_batch_node_ids(prompt)
                ]
            )
        if prompt.startswith("Age band:"):
            if any(text in refused_prose for text in _passages(prompt)):
                # The per-node retry for a node in the bad batch. Parses, and
                # carries no verdict, so the node stays unjudged.
                return "{}"
            return '{"verdict": "safe", "reason": "ok"}'
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * _REVIEW_BUDGET)


@pytest.mark.unit
async def test_a_coverage_gap_auto_rejects_instead_of_submitting(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """One unusable batch response must not submit the story for approval.

    Every other batch reviews clean, so the report carries genuine judgments
    beside the gap. That combination is what made the bug survive: the
    fail-safe records FLAG (never BLOCK, since ``has_hard_block`` is
    ``any(verdict is BLOCK)``), so the run looked like an ordinary soft flag
    and went to the review queue as "review when convenient".
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    # Batches of two, so one bad batch leaves most of the story genuinely
    # reviewed and the gap cannot be mistaken for a total reviewer outage.
    review_seam(_one_bad_batch_review_provider())
    settings = Settings(review_provider="mock", review_batch_size=2)
    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    events = _capture_events(monkeypatch)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    report = version.moderation_report
    assert report is not None
    summary = cast("dict[str, object]", report["summary"])
    assert summary["coverage_complete"] is False
    assert summary["hard_block"] is False, (
        "the gap must gate WITHOUT inventing a content block that no reviewer "
        "actually returned; that distinction is why coverage is its own field"
    )
    findings = cast("list[dict[str, object]]", report["findings"])
    gaps = [f for f in findings if f.get("concern") == "reviewer_unavailable"]
    assert len(gaps) == 1
    node_ids = cast("list[str]", gaps[0]["node_ids"])
    assert len(node_ids) == 2, (
        "the whole batch loses coverage, not one node: the batch size is the "
        f"blast radius, but {node_ids} were named"
    )
    # The durable audit record must agree with the status transition. Without
    # this, _overall_verdict could keep reporting "flag" (the fail-safe finding
    # IS a flag) while the story auto-rejected, leaving the append-only log
    # describing an outcome that did not happen.
    payload = cast("dict[str, object]", events[-1].kwargs["payload"])
    assert payload["overall_verdict"] == "block"


@pytest.mark.unit
async def test_a_coverage_gap_does_not_route_into_the_auto_repair(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A gap must not be handed to the repairer, which would erase the evidence.

    The fail-safe FLAG satisfies ``has_soft_flag``, so under the old predicate
    a coverage gap ROUTED INTO the bounded auto-repair. Two things go wrong
    there: the repairer rewrites prose no reviewer has read, and an adopted
    revision replaces the report wholesale, so the record that anything went
    unreviewed disappears along with the text it described.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_one_bad_batch_review_provider())
    settings = Settings(review_provider="mock", review_batch_size=2)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", AsyncMock())
    repair = AsyncMock(side_effect=lambda **kw: kw["report"])
    monkeypatch.setattr(pipeline_mod, "_attempt_and_adopt_repair", repair)

    original_blob = copy.deepcopy(version.blob)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    repair.assert_not_awaited()
    assert version.blob == original_blob


def _batched_verdict_review_provider() -> MockProvider:
    """Build a review backend double that answers Stage-1 batch prompts.

    Unlike ``_verdict_review_provider`` (one node per call), this recognizes
    the batch prompt shape (``"Age band:"`` followed by a ``"Nodes:"``
    section) and returns one schema-correct array entry per node id found in
    the prompt, so a chunked ``run_safety_stage`` call gets a genuine
    per-node verdict for every node in its batch.
    """

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:") and "Nodes:" in prompt:
            node_ids = _extract_batch_node_ids(prompt)
            return json.dumps(
                [
                    {"verdict": "safe", "reason": "ok", "node_id": nid}
                    for nid in node_ids
                ]
            )
        if prompt.startswith("Age band:"):
            return '{"verdict": "safe", "reason": "ok"}'
        # Coherence and engagement (whole-story prompts) both accept "pass".
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * _REVIEW_BUDGET)


@pytest.mark.unit
async def test_review_batch_size_from_settings_drives_chunked_safety_calls(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """settings.review_batch_size reaches run_safety_stage through the
    pipeline's call site. With every node fitting in a single batch, Stage 1
    issues one call instead of one per node, and the story still reviews
    clean end to end.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    provider = _batched_verdict_review_provider()
    review_seam(provider)
    settings = Settings(review_provider="mock", review_batch_size=_NODE_COUNT)
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    safety_calls = [c for c in provider.calls if c.startswith("Age band:")]
    assert len(safety_calls) == 1
    assert version.moderation_report is not None
    findings = cast("list[dict[str, object]]", version.moderation_report["findings"])
    # The assertion is that the BATCHED safety path emitted no fail-safe
    # pipeline finding. The gap-G1 mock stamp is a separate, expected advisory:
    # these settings declare review_provider="mock" (to satisfy config) while
    # `review_seam` injects a real-verdict responder, so the stamp fires on the
    # declared provider.
    #
    # Assert the WHOLE set rather than filtering the stamp out by concern. A
    # negative filter passes for two different reasons, "the batch path was
    # clean" and "a new fail-safe arrived wearing the stamp's concern", and it
    # also passes if the stamp stops firing entirely. Equality against an
    # explicit expected set fails on all three.
    pipeline_concerns = {
        f.get("concern") for f in findings if f.get("category") == "pipeline"
    }
    assert pipeline_concerns == {"mock_reviewer_active"}, (
        f"unexpected pipeline findings: {pipeline_concerns}"
    )
    assert _aggregate(version)["nodes_reviewed"] == _NODE_COUNT


@pytest.mark.unit
async def test_review_batch_size_default_batches_stage1_calls(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The Settings DEFAULT (review_batch_size=8, ratified by the Gate 3
    recall comparison on 2026-08-01) chunks Stage-1 into ceil(N/8) calls
    through the pipeline's call site, and the story still reviews clean.

    Unlike the other pipeline tests, this deliberately builds ``Settings``
    without the ``_settings()`` batch-size pin so it exercises whatever the
    shipped default is; if the default changes, the expected call count
    below moves with it."""
    story, version = _story(), _version()
    _load(mock_session, story, version)
    provider = _batched_verdict_review_provider()
    review_seam(provider)
    settings = Settings(review_provider="mock")
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    safety_calls = [c for c in provider.calls if c.startswith("Age band:")]
    assert settings.review_batch_size == 8
    assert len(safety_calls) == math.ceil(_NODE_COUNT / settings.review_batch_size)


@pytest.mark.unit
async def test_review_batch_size_covers_partial_final_chunk(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A node count that is NOT a multiple of the batch size still reviews
    every node exactly once.

    The two tests above both put every node in one full chunk, so neither can
    tell a correct chunker from one that drops or duplicates the remainder.
    ``_PARTIAL_CHUNK_BATCH_SIZE`` splits the story into one full batch plus a
    remainder of exactly one node, and that remainder takes
    ``run_safety_stage``'s single-node path (stages.py, ``len(batch) == 1``)
    rather than the batch path, so this covers both prompt shapes in a single
    pipeline run.
    """
    assert _NODE_COUNT % _PARTIAL_CHUNK_BATCH_SIZE != 0, (
        "fixture must not divide evenly by the batch size"
    )
    story, version = _story(), _version()
    _load(mock_session, story, version)
    provider = _batched_verdict_review_provider()
    review_seam(provider)
    settings = Settings(
        review_provider="mock", review_batch_size=_PARTIAL_CHUNK_BATCH_SIZE
    )
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    safety_calls = [c for c in provider.calls if c.startswith("Age band:")]
    assert len(safety_calls) == math.ceil(_NODE_COUNT / _PARTIAL_CHUNK_BATCH_SIZE)
    # Exactly one call is the single-node shape (the remainder), the rest are
    # batch shape. Node coverage is the real assertion: every node once.
    batch_calls = [c for c in safety_calls if "Nodes:" in c]
    assert len(batch_calls) == _NODE_COUNT // _PARTIAL_CHUNK_BATCH_SIZE
    reviewed: list[str] = []
    for call in batch_calls:
        reviewed.extend(_extract_batch_node_ids(call))
    assert len(reviewed) == len(batch_calls) * _PARTIAL_CHUNK_BATCH_SIZE
    assert len(set(reviewed)) == len(reviewed)  # no node reviewed twice
    assert _aggregate(version)["nodes_reviewed"] == _NODE_COUNT


@pytest.mark.unit
async def test_review_batch_size_covers_two_full_batches_plus_remainder(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A split with TWO full batches before the remainder still reviews every
    node exactly once.

    ``test_review_batch_size_covers_partial_final_chunk`` above enters
    ``run_safety_stage``'s chunking loop once and then hits the remainder; it
    cannot tell a chunker that only handles "one batch, then stop" from one
    that correctly keeps iterating across several full batches, because at
    the current node count its own batch size produces exactly one full
    batch. ``_TWO_FULL_BATCHES_BATCH_SIZE`` is a literal chosen so the split
    holds at least two full batches ahead of the remainder, which is the seam
    that exercises the loop actually advancing from one full batch to the
    next rather than just entering the loop body once.
    """
    full_batches, remainder = divmod(_NODE_COUNT, _TWO_FULL_BATCHES_BATCH_SIZE)
    assert full_batches >= 2, "fixture must produce at least two full batches"
    assert remainder != 0, "fixture must produce a non-empty remainder"
    story, version = _story(), _version()
    _load(mock_session, story, version)
    provider = _batched_verdict_review_provider()
    review_seam(provider)
    settings = Settings(
        review_provider="mock", review_batch_size=_TWO_FULL_BATCHES_BATCH_SIZE
    )
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings,
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    safety_calls = [c for c in provider.calls if c.startswith("Age band:")]
    assert len(safety_calls) == full_batches + 1
    # Every chunk of more than one node takes the batch shape ("Nodes:"); a
    # remainder of exactly one node would take the single-node shape instead
    # (covered separately above), so count batch-shaped calls accordingly.
    expected_batch_shaped = full_batches + (1 if remainder > 1 else 0)
    batch_calls = [c for c in safety_calls if "Nodes:" in c]
    assert len(batch_calls) == expected_batch_shaped
    reviewed: list[str] = []
    for call in batch_calls:
        reviewed.extend(_extract_batch_node_ids(call))
    assert len(reviewed) == full_batches * _TWO_FULL_BATCHES_BATCH_SIZE + (
        remainder if remainder > 1 else 0
    )
    assert len(set(reviewed)) == len(reviewed)  # no node reviewed twice
    assert _aggregate(version)["nodes_reviewed"] == _NODE_COUNT


# ---------------------------------------------------------------------------
# Prose-craft advisory (UW-C313 / UW-C328): wiring, not detection
# ---------------------------------------------------------------------------
#
# The detectors are covered in test_validator_prose_craft.py and the finding
# shapes in test_moderation_prose_craft.py. What these two pin is the pair of
# decisions the pipeline itself owns: that an advisory reaches the persisted
# report WITHOUT changing routing, and that the guard does not run once a hard
# block has already decided routing.


def _prose_craft_advisory() -> Finding:
    """Build one prose-craft ADVISORY, as the real guard would emit it."""
    return Finding(
        stage=0,
        source=Source.PIPELINE,
        category="prose_craft_sameness",
        verdict=Verdict.ADVISORY,
        node_id=None,
        score=None,
        message="self-repetition: 3 nodes repeat another node's exact body",
    )


@pytest.mark.unit
async def test_prose_craft_advisory_reaches_the_report_without_gating(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """An ADVISORY must be persisted and must not change where the book goes.

    This is the whole point of the guard: the evidence lands in front of the
    human approver, and nothing about the automated routing moves. A future
    change promoting these to FLAG would silently start spending the pipeline's
    one bounded repair on a defect a repair prompt cannot fix.
    """
    story, version = _story(), _version_with_slug()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    monkeypatch.setattr(
        pipeline_mod,
        "findings_from_prose_craft",
        create_autospec(
            findings_from_prose_craft, return_value=[_prose_craft_advisory()]
        ),
    )
    submit = AsyncMock()
    auto_reject = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    generation_provider = MockProvider(responses=[])

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=generation_provider,
        pii=_pii(),
    )

    submit.assert_awaited_once()
    auto_reject.assert_not_awaited()
    # No repair was attempted: an ADVISORY does not set has_soft_flag.
    assert generation_provider.calls == []
    moderation_report = version.moderation_report
    assert moderation_report is not None
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    advisories = [f for f in findings if f.get("category") == "prose_craft_sameness"]
    assert len(advisories) == 1
    assert advisories[0]["verdict"] == Verdict.ADVISORY


@pytest.mark.unit
async def test_prose_craft_skipped_on_hard_block(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """Routing is already decided, so the measurement would change nothing.

    Same gate as the ATG guard: an auto-rejected book is not going to a human
    approver, so the advisory has no reader.
    """
    story, version = _story(), _version_with_slug()
    _load(mock_session, story, version)
    review_seam(_safety_block_review_provider())

    prose_craft = create_autospec(findings_from_prose_craft, return_value=[])
    monkeypatch.setattr(pipeline_mod, "findings_from_prose_craft", prose_craft)
    auto_reject = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    prose_craft.assert_not_called()


@pytest.mark.unit
async def test_prose_craft_advisory_survives_an_adopted_repair(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """An ADVISORY must survive an adopted repair onto the persisted report.

    Same failure shape as ``test_mock_review_stamp_survives_adopted_repair``:
    ``_attempt_and_adopt_repair`` replaces the pipeline's ``report`` wholesale
    with the one built inside it, and that replacement is what gets persisted.
    Appending the advisory before the repair therefore dropped it on exactly
    the books most likely to have earned one, since a book whose prose is
    repetitive enough to trip the detector is also a book likely to be
    soft-flagged and repaired.

    This drives the REAL repair path: safety FLAGs every node on the first
    pass, the generation provider answers with a schema-valid revision, and
    the revision is adopted.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))
    monkeypatch.setattr(
        pipeline_mod,
        "findings_from_prose_craft",
        create_autospec(
            findings_from_prose_craft, return_value=[_prose_craft_advisory()]
        ),
    )
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)
    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[json.dumps(revised_blob)]),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    moderation_report = version.moderation_report
    assert moderation_report is not None
    summary = cast("dict[str, object]", moderation_report["summary"])
    # The repair really was adopted: without this the test passes vacuously on
    # the pre-repair report, which is the report that already carried it.
    assert summary["repaired"] is True
    findings = cast("list[dict[str, object]]", moderation_report["findings"])
    advisories = [f for f in findings if f.get("category") == "prose_craft_sameness"]
    assert len(advisories) == 1


@pytest.mark.unit
async def test_prose_craft_measures_the_repaired_blob(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """The measurement must describe the prose a human will actually read.

    The other half of running the guard after the repair rather than before
    it. Measured pre-repair, the advisory reports the sameness of prose that
    no longer exists: a repair that fixed the repetition would still be
    reported as repetitive, and one that introduced it would be reported as
    clean. Either way the number in front of the approver describes a
    different book than the one on the version row.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(safety_flags_first_pass=True))
    titles_measured: list[object] = []

    def _capture(blob: dict[str, object]) -> list[Finding]:
        titles_measured.append(blob.get("title"))
        return []

    monkeypatch.setattr(
        pipeline_mod,
        "findings_from_prose_craft",
        create_autospec(findings_from_prose_craft, side_effect=_capture),
    )
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())
    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[json.dumps(revised_blob)]),
        pii=_pii(),
    )

    assert version.blob["title"] == "The Forest Path (revised)"
    assert titles_measured == ["The Forest Path (revised)"]


# Whole-story review budget (_MAX_WHOLE_STORY_REVIEW_TOKENS). The coherence and
# engagement stages send EVERY node in one call, so sizing them with the
# per-node _MAX_REVIEW_TOKENS starved a reasoning-native review model: the
# model spent the whole 1024-token allowance on reasoning and the call returned
# finish_reason=length with empty content, raising ProviderError and aborting
# the book. The safety stage never showed the bug because it multiplies its
# per-node budget by batch size and clamps at _MAX_BATCH_REVIEW_TOKENS.


@pytest.mark.unit
async def test_whole_story_stages_get_the_whole_story_token_budget(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """Coherence and engagement must not be sized with the PER-NODE budget.

    Asserts the wiring rather than provider behaviour on purpose: the defect
    was which constant the pipeline handed these two stages, so recording the
    argument at the call site is what discriminates fixed from regressed. A
    provider-level assertion would also pass if someone reverted the constant
    but happened to test a book whose reasoning fit in 1024 tokens.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider())
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())

    budgets: dict[str, int] = {}

    def _recording_stage(name: str) -> Callable[..., object]:
        async def _stage(
            *, provider: object, nodes: object, max_tokens: int
        ) -> list[object]:
            _ = provider, nodes
            budgets[name] = max_tokens
            return []

        return _stage

    monkeypatch.setattr(
        pipeline_mod, "run_coherence_stage", _recording_stage("coherence")
    )
    monkeypatch.setattr(
        pipeline_mod, "run_engagement_stage", _recording_stage("engagement")
    )

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=MockProvider(responses=[]),
        pii=_pii(),
    )

    assert budgets == {"coherence": 16000, "engagement": 16000}
    # The regression this pins: both were previously handed the per-node budget.
    assert all(b > pipeline_mod._MAX_REVIEW_TOKENS for b in budgets.values())
