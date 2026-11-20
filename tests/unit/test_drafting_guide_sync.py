"""The two drafting-guide copies agree on the sections that steer agency and person.

``src/cyo_adventure/generation/templates/drafting_guide.md`` is the copy every
structure, prose and fill prompt renders as ``{drafting_guide}``;
``docs/planning/drafting-guide.md`` is the human-maintained planning copy. The
two have diverged elsewhere on purpose, but the point-of-view section once
told the model "There is no band where third person is correct" while 59 of 84
skeletons declared third person and ``fill.md`` told it to obey the
declaration. These tests hold the sections that resolved that contradiction,
and the reader-agency rules added beside them, identical in both copies, and
pin the resolution itself so it cannot quietly regress.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PROMPT_GUIDE = Path("src/cyo_adventure/generation/templates/drafting_guide.md")
_PLANNING_GUIDE = Path("docs/planning/drafting-guide.md")

SYNCED_SECTIONS = ("Reader Agency", "Voice, Tense, and Perspective")


def _section(text: str, heading: str) -> str | None:
    """Return the body of a level-2 section, up to the next level-2 heading.

    Args:
        text: Full guide text.
        heading: The section heading, without the leading ``## ``.

    Returns:
        The section body, stripped, or None when the section is absent.
    """
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else None


@pytest.mark.parametrize("heading", SYNCED_SECTIONS)
def test_synced_section_is_identical_in_both_guides(heading: str) -> None:
    """A synced section reads the same in the prompt copy and the planning copy."""
    prompt = _section(_PROMPT_GUIDE.read_text(encoding="utf-8"), heading)
    planning = _section(_PLANNING_GUIDE.read_text(encoding="utf-8"), heading)
    assert prompt is not None, f"the prompt guide lost its {heading!r} section"
    assert prompt == planning, (
        f"the {heading!r} section has drifted between {_PROMPT_GUIDE} and "
        f"{_PLANNING_GUIDE}; change both together"
    )


def test_the_prompt_guide_defers_to_the_declared_person() -> None:
    """The rendered guide says the skeleton's declared person governs.

    Pins the 2026-11-20 resolution: no wording that forbids third person may
    return, because a third-person skeleton is filled in third person
    (``UW-C328``) and the fill prompt says so.
    """
    text = _PROMPT_GUIDE.read_text(encoding="utf-8")
    flattened = re.sub(r"\s+", " ", text)
    assert "no band where third person is correct" not in flattened
    assert "The skeleton's declared person governs." in flattened
    assert "`metadata.narrative_person`" in flattened


def test_reader_agency_precedes_the_budgets_in_the_prompt_guide() -> None:
    """The agency rules sit near the top, before the schema-heavy sections.

    A review found the craft section ~2,300 words into a ~6,000-word prompt;
    rules placed that deep are the ones a model weights least.
    """
    text = _PROMPT_GUIDE.read_text(encoding="utf-8")
    assert text.index("## Reader Agency") < text.index("## Node and Depth Budgets")
