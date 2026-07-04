"""Unit tests for the child story-request feature (model, brief, screening)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from cyo_adventure.db.models import ChildProfile, StoryRequest
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.story_requests.screening import screen_request_text
from cyo_adventure.storybook.models import AgeBand


def test_story_request_defaults_to_pending() -> None:
    """A newly constructed StoryRequest has status 'pending'."""
    req = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
    )
    assert req.status == "pending"
    assert req.moderation_flags is None
    assert req.reviewed_by is None
    assert req.concept_id is None


def _profile(age_band: str = "8-11", cap: float = 99.0) -> ChildProfile:
    return ChildProfile(
        family_id=uuid.uuid4(),
        display_name="Emma",
        age_band=age_band,
        reading_level_cap=cap,
    )


def test_brief_from_request_uses_band_budget_and_generic_protagonist() -> None:
    """The brief inherits band node/ending budgets and a generic protagonist."""
    brief = brief_from_request("a story about a brave fox", _profile("8-11"))
    assert isinstance(brief, ConceptBrief)
    assert brief.premise == "a story about a brave fox"
    assert brief.age_band == AgeBand.BAND_8_11
    assert brief.target_node_count == 15  # band_profile 8-11 min_nodes
    assert brief.ending_count == 3  # band_profile 8-11 min_endings
    assert brief.protagonist.name == "Explorer"  # never a real child name
    assert brief.tier == 1


def test_brief_from_request_uses_reading_cap_when_below_sentinel() -> None:
    """A concrete reading_level_cap (below 99) becomes the FK target."""
    brief = brief_from_request("a gentle tale", _profile("5-8", cap=2.5))
    assert brief.reading_level_target == 2.5


@pytest.mark.asyncio
async def test_screen_blocks_on_pii_match() -> None:
    """A request naming a real child is blocked before any classifier call."""
    result = await screen_request_text(
        "a story about Emma and a dragon",
        child_names=frozenset({"Emma"}),
        openai_key=None,
        perspective_key=None,
    )
    assert result.blocked is True
    assert any(f.category == "personal_information" for f in result.flags)


@pytest.mark.asyncio
async def test_screen_clean_when_no_keys_and_no_pii() -> None:
    """With no PII and no classifier keys, the request is not blocked."""
    result = await screen_request_text(
        "a story about a brave fox",
        child_names=frozenset({"Emma"}),
        openai_key=None,
        perspective_key=None,
    )
    assert result.blocked is False
    assert result.flags == []


@pytest.mark.asyncio
async def test_screen_blocks_on_bright_line_classifier(monkeypatch) -> None:
    """A bright-line BLOCK finding from the classifier blocks the request."""

    async def _fake_run_classifiers(**_kwargs: object) -> list[Finding]:
        return [
            Finding(
                stage=0,
                source=Source.OPENAI,
                category="sexual/minors",
                node_id="request",
                verdict=Verdict.BLOCK,
                score=0.99,
                message="OpenAI bright-line category 'sexual/minors' flagged",
            )
        ]

    monkeypatch.setattr(
        "cyo_adventure.story_requests.screening.run_classifiers",
        _fake_run_classifiers,
    )
    result = await screen_request_text(
        "some idea",
        child_names=frozenset(),
        openai_key="k",
        perspective_key=None,
    )
    assert result.blocked is True
    # Redacted: no score/source leak into the flag payload.
    flag = next(f for f in result.flags if f.verdict is Verdict.BLOCK)
    assert flag.category == "sexual/minors"
    assert "flagged" in flag.message


@pytest.mark.asyncio
async def test_screen_fails_open_on_classifier_network_error(
    monkeypatch,
) -> None:
    """When a classifier network call fails, the request proceeds (fail-open).

    The guardian remains the human gate; this test proves that network failures
    in classifier APIs do not hard-block story requests. The fail-open behavior
    is a property of run_classifiers' internal per-call except (httpx.HTTPError,
    ValueError) contract.
    """

    class _FakeRequest:
        """Minimal request object for ConnectError."""

    async def _fake_post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError(
            "Network unreachable",
            request=_FakeRequest(),  # type: ignore[arg-type]
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    result = await screen_request_text(
        "some idea",
        child_names=frozenset(),
        openai_key="k",
        perspective_key=None,
    )
    assert result.blocked is False
    assert result.flags == []
