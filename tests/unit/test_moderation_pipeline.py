"""Unit tests for the moderation pipeline control flow and state-machine driving."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from cyo_adventure.core.config import Settings
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import _CANNED_STORY
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.moderation.review_provider import build_review_provider

pytestmark = pytest.mark.asyncio

# A valid Storybook JSON blob (uses the same canned story as the mock provider
# to guarantee it passes StoryModel.model_validate inside the pipeline).
_BLOB: dict[str, object] = dict(_CANNED_STORY)


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


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.mark.unit
async def test_pipeline_locks_storybook_row_for_update(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
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
    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
    for name in (
        "run_safety_stage",
        "run_readability_stage",
        "run_coherence_stage",
        "run_engagement_stage",
    ):
        monkeypatch.setattr(pipeline_mod, name, AsyncMock(return_value=[]))
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", AsyncMock())

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=AsyncMock(),
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
    story, version = _story(), _version()
    _load(mock_session, story, version)
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
                    message="x",
                )
            ]
        ),
    )
    auto_reject = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.auto_reject", auto_reject)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=AsyncMock(),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    assert version.moderation_report is not None
    assert version.moderation_report["summary"]["hard_block"] is True


@pytest.mark.unit
async def test_clean_story_routes_to_submit(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    story, version = _story(), _version()
    _load(mock_session, story, version)
    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
    for name in (
        "run_safety_stage",
        "run_readability_stage",
        "run_coherence_stage",
        "run_engagement_stage",
    ):
        monkeypatch.setattr(pipeline_mod, name, AsyncMock(return_value=[]))
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=AsyncMock(),
        pii=_pii(),
    )

    submit.assert_awaited_once()
    assert version.moderation_report["summary"]["hard_block"] is False


@pytest.mark.unit
async def test_soft_flag_triggers_repair_then_submits(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A soft FLAG triggers repair; if repair succeeds and re-moderation is clean,
    submit is awaited and the report carries repaired=True."""
    story, version = _story(), _version()
    _load(mock_session, story, version)

    # Stage 0 classifiers: clean
    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))

    # Safety, coherence, engagement: clean
    monkeypatch.setattr(pipeline_mod, "run_safety_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_mod, "run_coherence_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        pipeline_mod, "run_engagement_stage", AsyncMock(return_value=[])
    )

    # Readability: returns a FLAG to trigger the repair branch
    flag_finding = Finding(
        stage=2,
        source=Source.LLM_READABILITY,
        category="reading_level",
        node_id="n1",
        verdict=Verdict.FLAG,
        message="too hard",
    )
    # First call to readability returns FLAG; second call (post-repair) returns clean
    readability_mock = AsyncMock(side_effect=[[flag_finding], []])
    monkeypatch.setattr(pipeline_mod, "run_readability_stage", readability_mock)

    # Repair returns a revised blob
    revised_blob: dict[str, object] = {**_BLOB, "title": "The Forest Path (revised)"}
    monkeypatch.setattr(
        pipeline_mod,
        "attempt_repair",
        AsyncMock(return_value=revised_blob),
    )

    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=AsyncMock(),
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
        generation_provider=AsyncMock(),
        pii=_pii(),
    )

    auto_reject.assert_awaited_once()
    submit.assert_not_awaited()
    assert bad_version.moderation_report is not None
    assert bad_version.moderation_report["summary"]["hard_block"] is True


@pytest.mark.unit
async def test_invalid_repair_is_discarded_and_original_report_submits(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repair that yields a schema-invalid blob is discarded: the original
    soft-flagged report drives routing (submit), repaired stays False, and the
    invalid revision is never persisted to the version row."""
    story, version = _story(), _version()
    _load(mock_session, story, version)
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
    monkeypatch.setattr(
        pipeline_mod, "run_readability_stage", AsyncMock(return_value=[flag_finding])
    )
    # Repair yields a structurally invalid blob (not a valid Storybook).
    monkeypatch.setattr(
        pipeline_mod, "attempt_repair", AsyncMock(return_value={"garbage": True})
    )
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=_settings(),
        generation_provider=AsyncMock(),
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
    """review_model_override is threaded through to build_review_provider's settings."""
    captured: dict[str, object] = {}
    real_build = build_review_provider

    def _spy(settings, **kwargs):
        captured["review_openrouter_model"] = settings.review_openrouter_model
        return real_build(settings, **kwargs)

    monkeypatch.setattr("cyo_adventure.moderation.pipeline.build_review_provider", _spy)

    story, version = _story(), _version()
    mock_session.get = AsyncMock(side_effect=[story, version])
    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
    for name in (
        "run_safety_stage",
        "run_readability_stage",
        "run_coherence_stage",
        "run_engagement_stage",
    ):
        monkeypatch.setattr(pipeline_mod, name, AsyncMock(return_value=[]))
    submit = AsyncMock()
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit)

    settings_with_openrouter_backend = Settings(
        review_provider="openrouter",
        openai_api_key="k",
        openrouter_api_key="key",
    )
    generation_provider = AsyncMock()
    pii = _pii()

    await pipeline_mod.run_moderation_pipeline(
        session=mock_session,
        story_id="s1",
        version=1,
        settings=settings_with_openrouter_backend,
        generation_provider=generation_provider,
        pii=pii,
        review_model_override="anthropic/claude-opus-4.8",
    )

    assert captured["review_openrouter_model"] == "anthropic/claude-opus-4.8"
    submit.assert_awaited_once()
