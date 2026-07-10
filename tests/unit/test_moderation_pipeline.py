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

import json
import uuid
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from cyo_adventure.core.config import Settings
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import _CANNED_STORY, MockProvider
from cyo_adventure.moderation import pipeline as pipeline_mod

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.asyncio

# A valid Storybook JSON blob (uses the same canned story as the mock provider
# to guarantee it passes StoryModel.model_validate inside the pipeline).
_BLOB: dict[str, object] = dict(_CANNED_STORY)

_NODE_COUNT = len(cast("list[object]", _CANNED_STORY["nodes"]))

# Review calls per moderation pass: safety + readability per node, coherence +
# engagement once each. A repair run makes two passes; pad the budget so an
# exhausted MockProvider (which raises loudly) signals a real pipeline bug,
# not a miscounted fixture.
_REVIEW_BUDGET = 4 * (2 * _NODE_COUNT + 2)


def _settings() -> Settings:
    """Return a minimal Settings with review_provider='mock'."""
    return Settings(review_provider="mock")


def _pii() -> PiiContext:
    """Return an empty PiiContext with no real-child identifiers."""
    return PiiContext(child_names=frozenset(), birthdates=frozenset())


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


def _load(session: AsyncMock, story: Storybook, version_row: object) -> None:
    """Wire a mock session for the pipeline's locked-load pattern.

    The storybook now loads via ``session.execute(...).scalar_one_or_none()``
    (SELECT ... FOR UPDATE); the version row still loads via ``session.get``.
    """
    session.execute = AsyncMock(return_value=_execute_result(story))
    session.get = AsyncMock(return_value=version_row)


def _verdict_review_provider(
    *, readability_flags_first_pass: bool = False
) -> MockProvider:
    """Build a review backend double that answers each stage with a real verdict.

    Unlike the settings-level mock backend (``review_provider="mock"``, whose
    fixed ``"{}"`` bodies fail-safe every safety check to FLAG), this
    responder returns schema-correct verdict JSON per stage, dispatching on
    each stage's own prompt prefix, so the REAL stage functions run and parse
    real verdicts.

    Args:
        readability_flags_first_pass: When True, every readability call in the
            FIRST moderation pass returns ``"flag"`` (the soft gate), and any
            later pass (the post-repair re-moderation) returns ``"pass"``.

    Returns:
        A :class:`MockProvider` seeded with the dispatching responder.
    """
    state = {"readability_calls": 0}

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            return '{"verdict": "safe", "reason": "ok"}'
        if prompt.startswith("Flesch-Kincaid"):
            state["readability_calls"] += 1
            first_pass = state["readability_calls"] <= _NODE_COUNT
            if readability_flags_first_pass and first_pass:
                return '{"verdict": "flag", "reason": "too hard"}'
            return '{"verdict": "pass", "reason": "ok"}'
        # Coherence and engagement (whole-story prompts) both accept "pass".
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

    mock_session.execute.assert_awaited_once()
    stmt = mock_session.execute.await_args.args[0]
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
async def test_soft_flag_triggers_repair_then_submits(
    mock_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    review_seam: Callable[[MockProvider], dict[str, object]],
) -> None:
    """A soft FLAG triggers repair; if repair succeeds and re-moderation is clean,
    submit is awaited and the report carries repaired=True.

    Runs the REAL repair path: readability FLAGs every node on the first
    pass, the real ``attempt_repair`` re-prompts the generation provider
    (a MockProvider queued with a revised, schema-valid blob), and the
    re-moderation pass comes back clean.
    """
    story, version = _story(), _version()
    _load(mock_session, story, version)
    review_seam(_verdict_review_provider(readability_flags_first_pass=True))

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
    review_seam(_verdict_review_provider(readability_flags_first_pass=True))

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
                "results": [{"flagged": False, "categories": {}, "category_scores": {}}]
            },
        )

    _install_canned_classifier_http(monkeypatch, _clean_handler)

    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    settings_with_openrouter_backend = Settings(
        review_provider="openrouter",
        openai_api_key="k",
        openrouter_api_key="key",
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
