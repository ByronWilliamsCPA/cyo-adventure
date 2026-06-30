"""Unit tests for the moderation pipeline control flow and state-machine driving."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import _CANNED_STORY
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.moderation.report import Finding, Source, Verdict

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


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.mark.unit
async def test_hard_block_routes_to_auto_reject(
    mock_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    story, version = _story(), _version()
    mock_session.get = AsyncMock(side_effect=[story, version])
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
    mock_session.get = AsyncMock(side_effect=[story, version])

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
