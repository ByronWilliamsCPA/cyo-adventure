"""SAFE-14 safety stub validator (Phase-2 placeholder).

This module establishes the call seam that the Phase-3 content-moderation
pipeline will share. In Phase 2 the function body is intentionally empty: it
returns a ``ValidationReport`` with no findings.

Phase-3 replacement contract
-----------------------------
Phase 3 will replace the body of ``check_safety`` with:

1. A provider moderation call (e.g. OpenAI Moderation API or equivalent).
2. An independent LLM-reviewer pass that scores the story text against a
   per-age-band safety policy defined in ``docs/planning/validator-rules.md``
   section SAFE-14.
3. Findings of severity ``ERROR`` for policy violations that must block the
   story, and ``WARNING`` for advisory notes.

The seam exists so the combined gate (WP4) and the Phase-3 moderation share
one call site and the WP4 gate does not need to change when Phase 3 lands.

Usage::

    from cyo_adventure.validator.safety import check_safety

    report = check_safety(story)  # always empty in Phase 2

Rule source: ``docs/planning/validator-rules.md`` section SAFE-14,
and ``docs/planning/roadmap.md`` Phase 3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.validator.report import ValidationReport

if TYPE_CHECKING:
    from cyo_adventure.storybook.models import Storybook


def check_safety(story: Storybook) -> ValidationReport:
    """Run the SAFE-14 safety check over a story.

    Phase-2 stub: returns an empty ``ValidationReport`` with no findings.

    Phase 3 will replace this body with provider moderation and an independent
    LLM-reviewer pass scored against per-age-band policy (see module docstring
    and ``docs/planning/validator-rules.md`` SAFE-14).

    Args:
        story: The validated Storybook to check.

    Returns:
        ValidationReport: An empty report with no findings and ``ok=True``.
    """
    _ = story  # Phase-3 will use the story argument; retained for call-site stability.
    return ValidationReport()
