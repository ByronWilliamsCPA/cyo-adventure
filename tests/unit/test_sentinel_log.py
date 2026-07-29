"""Unit tests for the shared API-egress sentinel strip-and-report helper.

The security property under test is negative: a personalization value may be a
child's first name, so it must never reach a log sink. Asserting only that the
warning *fires* would miss a regression that fires it with the value attached,
so every test here also asserts what the rendered line does NOT contain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.storybook.sentinels import wrap

if TYPE_CHECKING:
    import pytest

_CHILD_NAME = "Briella"


def test_strip_and_log_without_a_sentinel_returns_text_unchanged() -> None:
    """The common case is a no-op: clean text through, nothing logged."""
    assert strip_and_log("A Perfectly Ordinary Title", at="library_item.title") == (
        "A Perfectly Ordinary Title"
    )


def test_strip_and_log_without_a_sentinel_emits_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No sentinel means no signal.

    A warning on every served field would drown the one case that matters,
    since a sentinel reaching this helper always means an upstream invariant
    already broke.
    """
    with caplog.at_level("WARNING"):
        strip_and_log("A Perfectly Ordinary Title", at="library_item.title")

    assert "api.served_field_sentinel_stripped" not in caplog.text


def test_strip_and_log_substitutes_the_generic_value_rather_than_deleting() -> None:
    """The generic word survives; only the token markup is removed.

    Deleting instead of substituting would leave a grammatically broken title
    ("The  and the Map"), which is a worse reader-facing outcome than the
    generic word the sentinel already carries as its fallback.
    """
    text = f"{wrap('HERO', 'Explorer')} and the Map"

    assert strip_and_log(text, at="library_item.title") == "Explorer and the Map"


def test_strip_and_log_warning_omits_the_sentinel_value_and_the_raw_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The redaction invariant: no personalization value reaches the log.

    ``_CHILD_NAME`` stands in for a resolved personalization value. Neither it
    nor the raw text carrying it may appear in the rendered line, mirroring the
    redaction in ``moderation/pipeline.py``'s
    ``moderation.entry_sentinel_integrity_violation``.
    """
    text = f"{wrap('HERO', _CHILD_NAME)} and the Map"

    with caplog.at_level("WARNING"):
        stripped = strip_and_log(
            text, at="library_item.title", storybook_id="sb-1", version=3
        )

    assert stripped == f"{_CHILD_NAME} and the Map"
    assert "api.served_field_sentinel_stripped" in caplog.text
    assert _CHILD_NAME not in caplog.text
    assert "{~" not in caplog.text
    assert "~}" not in caplog.text


def test_strip_and_log_warning_records_the_call_site_and_story_coordinates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """What the log DOES carry: enough to locate the broken blob, and no more.

    The slot id is safe to log (it is an authored identifier like ``HERO``,
    never resolved child data) and is what tells an operator which slot leaked.
    """
    text = f"{wrap('HERO', _CHILD_NAME)} and the Map"

    with caplog.at_level("WARNING"):
        strip_and_log(text, at="library_item.title", storybook_id="sb-1", version=3)

    assert "library_item.title" in caplog.text
    assert "sb-1" in caplog.text
    assert "HERO" in caplog.text


def test_strip_and_log_tolerates_a_surface_with_no_story_coordinates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Notifications are not always story-linked, so both coordinates default.

    This pins that the helper still warns (rather than raising) when the
    calling surface cannot supply a storybook id or version.
    """
    text = wrap("PET", _CHILD_NAME)

    with caplog.at_level("WARNING"):
        stripped = strip_and_log(text, at="notification.body")

    assert stripped == _CHILD_NAME
    assert "api.served_field_sentinel_stripped" in caplog.text
    assert _CHILD_NAME not in caplog.text
