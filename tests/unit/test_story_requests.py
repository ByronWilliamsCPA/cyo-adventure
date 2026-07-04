"""Unit tests for the child story-request feature (model, brief, screening)."""

from __future__ import annotations

import uuid

from cyo_adventure.db.models import ChildProfile, StoryRequest
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.story_requests.brief import brief_from_request
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
