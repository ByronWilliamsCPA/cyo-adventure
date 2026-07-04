"""Unit tests for the child story-request feature (model, brief, screening)."""

from __future__ import annotations

import uuid

from cyo_adventure.db.models import StoryRequest


def test_story_request_defaults_to_pending() -> None:
    """A newly constructed StoryRequest has status 'pending'."""
    req = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
    )
    assert req.status == "pending"
    assert req.moderation_flags is None
    assert req.reviewed_by is None
    assert req.concept_id is None
