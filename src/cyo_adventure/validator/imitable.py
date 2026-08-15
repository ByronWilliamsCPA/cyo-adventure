"""Route young-band endings that reward an imitable hazard to a human.

Every safety check in the pipeline asks what happens **to** a character.
`content_flags`, the L1 safety rules and the moderation classifiers all pass a
book in which nothing bad happens, and a book that rewards an imitable hazard is
exactly a book in which nothing bad happens. Two independent readers named the
class from different book sets (`AL-386`): an enclosed snow tunnel crawled
repeatedly as the "Greatest fort ever" ending, a bravery payoff for lighting a
wick solo, a hot oven opened as a choice whose depicted cost is slumped buns.

What this is and is not
-----------------------
**A routing screen, not a rule and not a classifier.** It decides nothing and
blocks nothing. It selects the small set of endings a person should look at, on
the theory that the question "would a guardian accept a child imitating what the
protagonist is rewarded for" is one a person answers well and a keyword list
answers badly. The judged criterion that would answer it (`imitable_practice`)
is proposed but unbuilt, because this project does not let a criterion arbitrate
before W7 has shown it detects its own defect (`AL-356`).

Three design choices, each of which the measurement forced:

* **Endings only.** The concern is what the book *rewards*, not what it depicts.
  Scanning all nodes buries the signal in scene-setting.
* **Young bands only.** Gating to 3-5, 5-8 and 8-11 is what makes the screen
  usable at all. Ungated, ``open_flame`` fires on 23 endings, mostly 16+
  gamebooks where a depicted flame is not a child-imitation risk. Gated, the
  whole screen selects 13 of 167 young-band endings.
* **Co-occurrence, not single words.** A hazard cue must appear alongside an
  action cue in the same body. ``climb`` alone fired on 10.8 percent of all
  endings and was dropped for it; a screen that selects a tenth of the corpus
  has not selected anything.

Measured incidence, 2026-08-15, over the committed corpus
---------------------------------------------------------
13 of 167 young-band ending nodes (7.8 percent), across four cues. It selects
all three endings the readers named. Six of the thirteen are `the-night-market`,
a lantern festival where flame vocabulary is unavoidable, and that is the
expected and acceptable failure mode for a router: a person reads six paragraphs
and moves on. It would be an unacceptable failure mode for a gate, which is one
more reason this is not one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

    from cyo_adventure.storybook.models import Storybook

__all__ = ["HazardCue", "screen_for_review"]

# Bands where a reader is young enough that imitation is the concern. A 16+
# gamebook depicting an open flame is not the same object as a 5-8 book
# rewarding a small child for handling one.
_YOUNG_BANDS: Final[frozenset[str]] = frozenset({"3-5", "5-8", "8-11"})

# (label, hazard cue, action cue). Both must appear in the same ending body.
# The list is deliberately short and stable: every entry names a practice that
# child-safety organisations warn about specifically, rather than a general
# notion of danger, because a general notion of danger is what the existing
# `content_flags` already covers and covers better.
_CUES: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "snow_enclosure",
        r"\b(?:tunnel|cave|burrow)\b",
        r"\b(?:snow|drift|igloo|fort)\b",
    ),
    (
        "open_flame",
        r"\b(?:flame|match|candle|lantern|fire|wick)\b",
        r"\b(?:lit|light|touch|strike|struck)\w*",
    ),
    (
        "deep_water",
        r"\b(?:swam|swim|dove|dived|waded|current|pond|lake|river|tide)\b",
        r"\b(?:alone|deep|by (?:her|him|them)self|on (?:her|his|their) own)\b",
    ),
    (
        "wild_animal",
        r"\b(?:fed|feed\w*|petted|pet|held|touch\w*)\b",
        r"\b(?:wild|deer|rabbit|fox|raccoon|squirrel|snake)\b",
    ),
)

_COMPILED: Final[tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...]] = tuple(
    (label, re.compile(hazard, re.IGNORECASE), re.compile(action, re.IGNORECASE))
    for label, hazard, action in _CUES
)


@dataclass(frozen=True, slots=True)
class HazardCue:
    """One ending a person should read, and why it was selected.

    Attributes:
        node_id: The ending node.
        cue: Which cue matched, so a reviewer knows what to look for rather than
            having to rediscover it.
        band: The book's age band, always one of the young bands.
    """

    node_id: str
    cue: str
    band: str


def screen_for_review(story: Storybook) -> list[HazardCue]:
    """Return the endings of *story* worth a person's attention, if any.

    A book outside the young bands returns an empty list, and that is a scoping
    decision rather than a claim that older books carry no risk: the imitation
    concern this screen serves is specific to a reader young enough to copy what
    a protagonist is rewarded for.

    Args:
        story: The story to screen.

    Returns:
        list[HazardCue]: One entry per matching ending and cue, in node order.
        An ending matching two cues appears twice, deliberately, because the two
        are different things for a reviewer to check.
    """
    band = story.metadata.age_band.value
    if band not in _YOUNG_BANDS:
        return []
    return list(_cues_in(story, band))


def _cues_in(story: Storybook, band: str) -> Iterator[HazardCue]:
    """Yield each matching cue for each ending node.

    Args:
        story: The story being screened.
        band: The story's age band, already known to be a young one.

    Yields:
        HazardCue: One per ending-and-cue match.
    """
    for node in story.nodes:
        if not node.is_ending:
            continue
        body = node.body
        for label, hazard, action in _COMPILED:
            if hazard.search(body) and action.search(body):
                yield HazardCue(node_id=node.id, cue=label, band=band)
