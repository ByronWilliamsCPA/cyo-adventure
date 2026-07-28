"""Structural regression pin (ADR-023 R2): every title-bearing response model
in ``api/schemas.py`` must carry an explicit strip-or-raw decision.

The scan below enumerates every ``BaseModel`` subclass reachable from
``vars(cyo_adventure.api.schemas)`` (i.e. everything defined in, or imported
directly into, that module's namespace) with a field named ``title``. A new
title-bearing response model added to that surface without a matching row in
``DECIDED`` fails this test, forcing an explicit decision instead of a silent
default.

Scope note: this scans only ``api/schemas.py``'s namespace, per the Task A5
spec. A grep of the other ``api/*.py`` router modules found no additional
Pydantic response model defined *outside* ``schemas.py`` with a ``title``
field (every router that returns a title-bearing row imports its model from
``schemas.py``); if that ever changes, widen this scan or add a companion
test alongside the new module.
"""

from __future__ import annotations

from pydantic import BaseModel

import cyo_adventure.api.schemas as schemas

# Explicit strip/raw decision per title-bearing response model in
# api/schemas.py's namespace. "strip" means the title is guaranteed to have
# personalization sentinels (storybook.sentinels.strip_sentinels) removed
# before it reaches this model; "raw" means it deliberately is not (either
# because the surface is admin/review-only per ADR-023 section 10, or
# because the field is guardian-authored input rather than generated story
# content, so no sentinel could appear there in the first place).
#
# New title-bearing response model: add a strip/raw decision here and, if
# strip, a covering test (see the existing entries for the pattern: a
# dedicated `test_title_sentinels_are_stripped`-style unit test on the
# helper that builds the model).
DECIDED: dict[str, str] = {
    # --- strip: personalization sentinels are removed before serialization ---
    "LibraryItem": "strip",  # api/library.py::_library_item (title stripped at :245)
    "ReadingHistoryItem": "strip",  # api/reading_history.py::_book_title
    "RecommendationItem": "strip",  # api/recommendations.py::_book_title
    "NotificationView": "strip",  # api/notifications.py (title/body wrapped in strip_sentinels)
    # --- raw: the version-blob endpoint (the artifact the client resolves
    # personalization against) is deliberately verbatim ---
    # (get_storybook_version returns a plain dict, not a schemas.py
    # BaseModel, so it is not itself a row in this table; noted here for
    # context since it is the reference "intentionally raw" case R3 pins.)
    # --- raw: admin/review surfaces deliberately show raw markers
    # (ADR-023 section 10) ---
    "ReviewQueueItem": "raw",  # api/review_surface.py::_queue_title (admin review queue)
    "StorybookSummary": "raw",  # api/approval.py::_summary_title (admin master library)
    # --- raw: guardian-authored request input, not generated story content;
    # sentinels are embedded into published story blobs by the fill
    # pipeline, never typed by a guardian into their own request, so there
    # is nothing to strip here. This is the guardian's own title, echoed
    # back to themselves in their own "My Requests" list. ---
    "ConceptBrief": "raw",  # generation/concept.py (guardian's own request.brief.title)
    # --- raw, BUT UNFIXED LEAK: these two title-bearing consumer surfaces
    # read `blob.get("title")` directly with no strip_sentinels() call, the
    # same pattern A2-A4 fixed for LibraryItem/ReadingHistoryItem/
    # RecommendationItem/NotificationView. They are classified "raw" here
    # only because that is what the code currently does; per Task A5's
    # scope (tests only, no src/ changes), this is flagged for the
    # supervisor to schedule a follow-up fix, not silently accepted as by
    # design like the admin/review surfaces above.
    # TODO(ADR-023 leak): api/reading.py `get_series_next` builds
    # SeriesNextBook.title from `blob.get("title")` verbatim (no strip);
    # this is a kid-facing series-continuation feed, structurally identical
    # to the already-fixed LibraryItem/ReadingHistoryItem sites.
    "SeriesNextBook": "raw",  # api/reading.py::get_series_next -- UNFIXED, see TODO above
    # TODO(ADR-023 leak): api/assignments.py `_guardian_book_item` builds
    # GuardianBookItem.title from `version_row.blob.get("title")` verbatim
    # (no strip); this is the guardian browse-and-assign list, not an
    # admin/review surface, so it does not fall under the ADR-023 section 10
    # carve-out and looks like the same class of leak as SeriesNextBook.
    "GuardianBookItem": "raw",  # api/assignments.py::_guardian_book_item -- UNFIXED, see TODO above
    # --- raw: internal job-status projection, not story content. The title
    # here is read from Concept.brief (the guardian's own ConceptBrief, see
    # above), not from a published story blob, so the same "no sentinel can
    # appear here" reasoning applies. ---
    "GenerationJobListItem": "raw",  # api/generation.py::list_generation_jobs (title = brief["title"])
}


def test_every_title_field_has_a_strip_decision() -> None:
    """Every ``title``-bearing BaseModel in ``api/schemas.py`` has a decision.

    Failure message tells a future developer what to do: a title-bearing
    response model was added (or removed) without updating ``DECIDED`` in
    this file to match.
    """
    found = {
        name
        for name, obj in vars(schemas).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and "title" in getattr(obj, "model_fields", {})
    }
    assert found == set(DECIDED), (
        "New (or removed) title-bearing response model in api/schemas.py: "
        f"scan found {found!r}, DECIDED covers {set(DECIDED)!r}. Add a "
        "strip/raw decision in tests/unit/test_title_strip_registry.py's "
        "DECIDED mapping and, if strip, a covering test on the helper that "
        "builds the model."
    )


def test_every_decision_is_strip_or_raw() -> None:
    """Guard against a typo'd decision value silently passing the set check."""
    assert set(DECIDED.values()) <= {"strip", "raw"}, (
        "DECIDED values must be exactly 'strip' or 'raw'."
    )
