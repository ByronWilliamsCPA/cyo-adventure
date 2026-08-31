"""Structural regression pin (ADR-023 R2): every response field that a story
blob can be projected into carries an explicit strip-or-raw decision.

**Why this file keys on (model, field) and not on ``title`` alone.** The first
version of this registry scanned for models with a field literally named
``title``. That had a blind spot large enough to miss a guard point this very
PR had to add: ``NotificationView.body`` is composed from a story title and is
stripped, but a title-only scan cannot see it. It also could not see
``GuardianBookItem.themes`` or ``FlaggedPassage.prose``.

**The scanned field-name set is the reviewable knob.** ``_BLOB_TEXT_FIELDS``
below is the set of response field names a storybook blob is projected into.
Scanning every string-bearing field instead would sweep in 224 pairs of ids,
enums, URLs and statuses, and a table that large would be classified by
guesswork; a wrong row is worse than no row, because it manufactures
confidence. So the scan stays narrow and the *set itself* is the thing to
extend: if a new blob field starts reaching a response model, add its name
here and the tests below will demand a decision for every model carrying it.

**Fail-closed in both directions.** The scan asserts set *equality* against
``DECIDED``, so adding a model with one of these fields fails, and so does
removing one without pruning the table.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from pydantic import BaseModel

import cyo_adventure.api.schemas as schemas

# Response field names a storybook blob is projected into. See the module
# docstring: this set is deliberately narrow and is the intended extension
# point.
_BLOB_TEXT_FIELDS = frozenset({"title", "body", "themes", "prose"})

# Closed decision vocabulary. ``raw`` on its own is not accepted: a bare
# "raw" lets a future developer silence a failing scan with one word and no
# reasoning, which is the failure mode this registry exists to prevent. Each
# ``raw:*`` reason states *why* no strip is required, and the reasons are
# mutually distinct claims that a reviewer can check.
_STRIP = "strip"
_RAW_REVIEW_SURFACE = "raw:review-surface"
_RAW_LEGAL_SENTINEL_SURFACE = "raw:legal-sentinel-surface"
_RAW_ADULT_AUTHORED = "raw:adult-authored"

_REASONS = frozenset(
    {
        _STRIP,
        # ADR-023 section 10: a reviewing adult sees raw markers on purpose,
        # because the marker is what they are being asked to review.
        _RAW_REVIEW_SURFACE,
        # A node body is one of the two surfaces where a sentinel is LEGAL at
        # rest (validator/sentinel_integrity.py, storybook/slotted_surfaces.py).
        # Stripping here would destroy a legitimate personalization slot rather
        # than protect anything.
        _RAW_LEGAL_SENTINEL_SURFACE,
        # The value originates from adult-typed input (a guardian's own request
        # brief, an admin's edit), never from a filled story blob, so no
        # sentinel can be present to strip.
        _RAW_ADULT_AUTHORED,
    }
)

DECIDED: dict[tuple[str, str], str] = {
    # --- strip: sentinels removed before the value reaches the client ---
    ("LibraryItem", "title"): _STRIP,
    ("ReadingHistoryItem", "title"): _STRIP,
    ("BookProgressView", "title"): _STRIP,
    ("FoundEndingView", "title"): _STRIP,
    ("RecommendationItem", "title"): _STRIP,
    ("NotificationView", "title"): _STRIP,
    ("NotificationView", "body"): _STRIP,
    ("SeriesNextBook", "title"): _STRIP,
    ("GuardianBookItem", "title"): _STRIP,
    ("GuardianBookItem", "themes"): _STRIP,
    # --- raw: admin / reviewing-adult surfaces show markers deliberately ---
    ("ReviewQueueItem", "title"): _RAW_REVIEW_SURFACE,
    ("ReviewQueueItem", "themes"): _RAW_REVIEW_SURFACE,
    ("StorybookSummary", "title"): _RAW_REVIEW_SURFACE,
    ("StorybookSummary", "themes"): _RAW_REVIEW_SURFACE,
    ("FlaggedPassage", "prose"): _RAW_REVIEW_SURFACE,
    # `RS-C2`/`RS-C3`. Same ruling as ReviewQueueItem.title, and for the same
    # reason: this row exists so an admin can decide about a book, and a
    # personalization marker in the title is part of what they are deciding
    # about. The surface is admin-gated (approval.py::get_outstanding_decisions
    # raises AuthorizationError without is_admin), so no child reads it.
    ("OutstandingDecisionItem", "title"): _RAW_REVIEW_SURFACE,
    # --- raw: stripping would destroy a legitimate slot ---
    ("NodeEditBody", "body"): _RAW_LEGAL_SENTINEL_SURFACE,
    # --- raw: adult-authored input, no sentinel can be present ---
    ("ConceptBrief", "title"): _RAW_ADULT_AUTHORED,
    ("GenerationJobListItem", "title"): _RAW_ADULT_AUTHORED,
}

# Both notification rows are covered by the one test, which asserts on the
# title and the body together.
_NOTIFICATION_TEST = (
    "tests/unit/test_notifications_api_unit.py"
    "::test_sentinels_are_stripped_from_title_and_body"
)

# Each ``strip`` row binds to the code that enforces it and the test that
# proves it. A decision with no enforcing code is a comment; a decision with
# no covering test is a hope.
ENFORCED: dict[tuple[str, str], tuple[str, str, str]] = {
    ("LibraryItem", "title"): (
        "cyo_adventure.api.library",
        "_library_item",
        "tests/unit/test_library_api_unit.py::test_title_sentinels_are_stripped",
    ),
    ("ReadingHistoryItem", "title"): (
        "cyo_adventure.api.reading_history",
        "_book_title",
        "tests/unit/test_reading_history_api_unit.py::test_book_title_strips_sentinels",
    ),
    ("BookProgressView", "title"): (
        "cyo_adventure.progress.blob",
        "book_title",
        "tests/unit/test_progress_blob.py::test_book_title_strips_sentinels",
    ),
    ("FoundEndingView", "title"): (
        "cyo_adventure.api.progress",
        "_build_found_endings",
        "tests/unit/test_progress_api_unit.py::test_found_ending_title_strips_sentinels",
    ),
    ("RecommendationItem", "title"): (
        "cyo_adventure.api.recommendations",
        "_book_title",
        "tests/unit/test_recommendations_api_unit.py::test_book_title_strips_sentinels",
    ),
    ("NotificationView", "title"): (
        "cyo_adventure.api.notifications",
        "list_notifications",
        _NOTIFICATION_TEST,
    ),
    ("NotificationView", "body"): (
        "cyo_adventure.api.notifications",
        "list_notifications",
        _NOTIFICATION_TEST,
    ),
    ("SeriesNextBook", "title"): (
        "cyo_adventure.api.reading",
        "get_series_next",
        "tests/unit/test_reading_api_unit.py::test_next_book_title_strips_sentinels",
    ),
    ("GuardianBookItem", "title"): (
        "cyo_adventure.api.assignments",
        "_guardian_book_item",
        "tests/unit/test_assignments_api_unit.py::test_title_strips_sentinels",
    ),
    ("GuardianBookItem", "themes"): (
        "cyo_adventure.api.assignments",
        "_guardian_book_item",
        "tests/unit/test_assignments_api_unit.py::test_themes_strip_sentinels",
    ),
}

_TESTS_ROOT = Path(__file__).resolve().parents[1]


def _scan() -> set[tuple[str, str]]:
    """Return every (model, field) pair a story blob can be projected into."""
    return {
        (name, field)
        for name, obj in vars(schemas).items()
        if isinstance(obj, type) and issubclass(obj, BaseModel)
        for field in getattr(obj, "model_fields", {})
        if field in _BLOB_TEXT_FIELDS
    }


def test_every_blob_text_field_has_a_recorded_decision() -> None:
    """Adding or removing such a field without updating ``DECIDED`` fails here."""
    found = _scan()

    assert found == set(DECIDED), (
        "api/schemas.py's blob-projected text fields no longer match this "
        f"registry. Scan found {sorted(found - set(DECIDED))!r} with no "
        f"decision, and {sorted(set(DECIDED) - found)!r} decided but no longer "
        "present. Add or remove a (model, field) row in "
        "tests/unit/test_title_strip_registry.py's DECIDED mapping; if the new "
        "row is 'strip', also add an ENFORCED entry naming the builder and its "
        "covering test."
    )


def test_every_decision_uses_the_closed_reason_vocabulary() -> None:
    """A bare 'raw' (or a typo) must not silence the scan above.

    The scan only checks that a key exists, so without this the cheapest way
    past a failure would be to paste a row with an unexamined value.
    """
    unknown = {
        pair: reason for pair, reason in DECIDED.items() if reason not in _REASONS
    }

    assert not unknown, (
        f"Undeclared decision value(s): {unknown!r}. Use one of "
        f"{sorted(_REASONS)!r}, or add a new reason to _REASONS with a comment "
        "explaining why that class of field needs no strip."
    )


def test_every_strip_row_names_enforcing_code_and_a_covering_test() -> None:
    """``strip`` is a claim; this pins that something actually backs it."""
    strip_rows = {pair for pair, reason in DECIDED.items() if reason == _STRIP}

    assert strip_rows == set(ENFORCED), (
        "Every 'strip' row needs an ENFORCED entry (and vice versa). "
        f"Missing: {sorted(strip_rows - set(ENFORCED))!r}; "
        f"orphaned: {sorted(set(ENFORCED) - strip_rows)!r}."
    )


def test_every_enforcing_builder_and_covering_test_exists() -> None:
    """Guard against the binding above rotting into a stale set of strings.

    A renamed helper or a deleted test would otherwise leave ENFORCED naming
    something that no longer exists, and the registry would still pass while
    documenting a guard that is gone.
    """
    for (model, field), (module_path, attr, test_ref) in ENFORCED.items():
        module = importlib.import_module(module_path)
        assert hasattr(module, attr), (
            f"{model}.{field} claims {module_path}.{attr} enforces its strip, "
            "but that attribute no longer exists."
        )

        test_file, _, test_name = test_ref.partition("::")
        path = _TESTS_ROOT.parent / test_file
        assert path.is_file(), f"{model}.{field}: missing test file {test_file}"
        assert f"def {test_name}(" in path.read_text(encoding="utf-8"), (
            f"{model}.{field} claims {test_ref} covers its strip, but no such "
            "test function is defined in that file."
        )
