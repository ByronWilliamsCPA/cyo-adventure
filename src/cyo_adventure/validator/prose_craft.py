"""Self-repetition and narrative-person detectors: the shared definition.

Two places need to answer "does this book repeat itself" and "is the narrator
in the person the book declares": the request-path advisory in
``moderation/prose_craft.py`` and the offline ``scripts/check_prose_craft.py``.
Two copies of a detector drift silently, and the calibration figures below stop
describing the code that runs the moment they do, so both route through here.

**What these catch that beat-overlap cannot.** Beat-restatement overlap does
not order books by quality: the better-judged of two live books scored HIGHER
(mean 0.668 against 0.51). What actually separated them was self-repetition,
23 redundant nodes across 11 repeated texts and three strings covering 89.8
percent of 674 choice labels, against zero duplicate bodies and 191 distinct
labels across 466. And the better book's own worst defect appears in neither
number: "you" occurs in 12 of its 193 nodes on beats that specify second
person, so the protagonist is absent from their own story (`AL-496`,
`UW-C313`).

Calibration, all measured on the committed corpora:

* duplicate bodies: known-good books have zero, the worst live book 23.
* top-3 label share: known-good 0.02 to 0.27, the worst live book 0.898.
* second-person node rate: committed gamebooks 0.715 to 1.0, committed
  third-person prose 0.0 to 0.27, and three fills of one prose skeleton
  scattered to 0.07, 0.13 and 0.72 because nothing pinned narrative person
  (`AL-523`, `UW-C328`).

Pure module: stdlib plus ``validator.dialogue`` only, in keeping with the rest
of the deterministic validator. Never imports ``db``, ``generation``, or
``sqlalchemy``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from cyo_adventure.validator.dialogue import strip_tagged

if TYPE_CHECKING:
    from collections.abc import Mapping

# Curly quotes are written as escapes so the pattern source stays ASCII
# (ruff RUF001 flags ambiguous unicode literals).
_LEFT_DOUBLE = "\u201c"
_RIGHT_DOUBLE = "\u201d"
_LEFT_SINGLE = "\u2018"
_RIGHT_SINGLE = "\u2019"

_DOUBLE_QUOTED = re.compile(
    f'["{_LEFT_DOUBLE}][^"{_LEFT_DOUBLE}{_RIGHT_DOUBLE}]{{0,400}}["{_RIGHT_DOUBLE}]'
)
_SINGLE_QUOTED = re.compile(
    f"(?<![A-Za-z])['{_LEFT_SINGLE}]"
    f"[^'{_LEFT_SINGLE}{_RIGHT_SINGLE}]{{0,400}}"
    f"['{_RIGHT_SINGLE}](?![A-Za-z])"
)

_SECOND_PERSON_RE = re.compile(r"\b(you|your|yours|yourself)\b", re.IGNORECASE)

MAX_REDUNDANT_NODES: Final[int] = 0
"""Nodes allowed to repeat another node's exact body. Zero: the known-good
corpus has none at all, so any duplicate is evidence rather than noise."""

MAX_TOP3_LABEL_SHARE: Final[float] = 0.5
"""Share of all choice labels the three most common strings may cover, on
books large enough for the share to mean anything. Known-good books run 0.02
to 0.27; the worst live book 0.898."""

TOP3_MIN_LABELS: Final[int] = 40
"""Labels a book needs before its top-3 share is judged at all.

Below this the share is arithmetic rather than evidence: a book with three
distinct labels scores 1.0 by construction and has done nothing wrong.
"""

MAX_THIRD_SECOND_PERSON: Final[float] = 0.35
"""Second-person node rate a book declaring third person may not exceed.
Committed third-person prose runs 0.0 to 0.27; the drift case shipped a 3-5
book fully second-person against third-person beats."""

MIN_GAMEBOOK_SECOND_PERSON: Final[float] = 0.5
"""Second-person node rate a gamebook, or a book declaring second person, must
reach. Committed gamebooks run 0.715 to 1.0."""


def strip_quoted(text: str) -> str:
    """Return text with quoted dialogue replaced by whitespace.

    Handles quotation marks only. Callers wanting the exemption the detectors
    actually intend want :func:`narration_of`; this stays separate because the
    single-quote handling below is more careful than a general detector should
    be, and is worth keeping distinct rather than folding away.

    Double quotes are removed first; single-quoted spans are then removed only
    where the opening quote is not preceded by a letter, so possessives and
    contractions ("Elara's", "isn't") survive.

    Args:
        text: Raw node body.

    Returns:
        The body with quoted spans blanked out.
    """
    return _SINGLE_QUOTED.sub(" ", _DOUBLE_QUOTED.sub(" ", text))


def narration_of(text: str) -> str:
    """Return the body with all recognised dialogue removed, quoted or tagged.

    Dialogue is exempt from every detector here: a child speaking in the
    present tense inside a past-tense book is correct English, and a character
    may say "my heart sank" without the narrator telling emotion. That
    rationale never depended on quotation marks, but an earlier implementation
    did, so the catalogue's own unquoted house style ("Almost there, Nina
    whispered.") was being scanned as though the narrator had said it.

    Deliberately NOT named ``strip_dialogue``: ``validator/dialogue.py``
    already exports a function by that name whose quote handling differs (it
    covers curly doubles but not careful singles), and two same-named
    functions returning different narration is the exact confusion this module
    exists to end. The name here says what the caller wants back.

    Args:
        text: Raw node body.

    Returns:
        The body with quoted spans blanked and tagged sentences dropped.
    """
    return strip_tagged(strip_quoted(text))


@dataclass(frozen=True)
class SamenessReport:
    """Duplicate-body and label-diversity counts for one book (`UW-C313`).

    Attributes:
        repeated_texts: Distinct body strings appearing on 2+ nodes.
        redundant_nodes: Nodes beyond the first carrying a repeated body.
        labels: Total choice labels.
        distinct_labels: Distinct label strings.
        top3_share: Share of all labels covered by the three most common
            strings; 0.0 when the book has no labels.
    """

    repeated_texts: int
    redundant_nodes: int
    labels: int
    distinct_labels: int
    top3_share: float


@dataclass(frozen=True)
class Judgment:
    """A detector's verdict plus the framing that explains it.

    Attributes:
        breached: Whether the book is outside the calibrated bound.
        framing: Which bound was applied and why, for a reviewer reading the
            finding. Populated whether or not the bound was breached, because
            "which rule did you apply to my book" is the first question a
            surprising verdict raises.
    """

    breached: bool
    framing: str


def sameness_report(story: Mapping[str, Any]) -> SamenessReport:
    """Count duplicate bodies and label collapse (`AL-496`/`UW-C313`).

    Deliberate exception to the module's dialogue exemption: bodies are
    compared RAW, because a byte-duplicated passage is a sameness defect
    whether or not it contains quoted speech, and stripping dialogue would
    merge distinct bodies that differ only in their quotes.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        SamenessReport: The counts.
    """
    nodes = cast("list[dict[str, Any]]", story.get("nodes") or [])
    bodies = [
        cast("str", node.get("body") or "").strip()
        for node in nodes
        if cast("str", node.get("body") or "").strip()
    ]
    body_counts = Counter(bodies)
    dup = {text: count for text, count in body_counts.items() if count > 1}
    labels = [
        cast("str", choice.get("label") or "")
        for node in nodes
        for choice in cast("list[dict[str, Any]]", node.get("choices") or [])
        if choice.get("label")
    ]
    label_counts = Counter(labels)
    top3 = sum(count for _, count in label_counts.most_common(3))
    return SamenessReport(
        repeated_texts=len(dup),
        redundant_nodes=sum(count - 1 for count in dup.values()),
        labels=len(labels),
        distinct_labels=len(label_counts),
        top3_share=(top3 / len(labels)) if labels else 0.0,
    )


def judge_sameness(
    report: SamenessReport,
    *,
    max_redundant_nodes: int = MAX_REDUNDANT_NODES,
    max_top3_label_share: float = MAX_TOP3_LABEL_SHARE,
) -> Judgment:
    """Apply the calibrated self-repetition bounds to a sameness report.

    Args:
        report: The counts from :func:`sameness_report`.
        max_redundant_nodes: Duplicate-body allowance.
        max_top3_label_share: Label-collapse allowance, applied only to books
            of at least :data:`TOP3_MIN_LABELS` labels.

    Returns:
        Judgment: Whether either bound was exceeded, and which.
    """
    over_bodies = report.redundant_nodes > max_redundant_nodes
    judged_labels = report.labels >= TOP3_MIN_LABELS
    over_labels = judged_labels and report.top3_share > max_top3_label_share
    if over_bodies and over_labels:
        framing = "duplicate bodies and collapsed choice labels"
    elif over_bodies:
        framing = f"{report.redundant_nodes} nodes repeat another node's body"
    elif over_labels:
        framing = (
            f"the 3 most common labels cover {report.top3_share:.1%} of "
            f"{report.labels} choices"
        )
    elif not judged_labels:
        framing = f"only {report.labels} labels; label collapse not judged"
    else:
        framing = "no self-repetition beyond the calibrated bounds"
    return Judgment(breached=over_bodies or over_labels, framing=framing)


@dataclass(frozen=True)
class PersonReport:
    """Second-person presence for one book (`AL-523`/`UW-C313`, `UW-C328`).

    Attributes:
        nodes: Nodes with non-empty narration once dialogue is stripped. A
            node whose body is nothing but speech carries no evidence about
            the narrator's person and is counted in neither term.
        second_person_nodes: Nodes whose narration contains a second-person
            token.
        rate: ``second_person_nodes / nodes``; 0.0 for an empty book.
    """

    nodes: int
    second_person_nodes: int
    rate: float


def person_report(story: Mapping[str, Any]) -> PersonReport:
    """Measure second-person presence in narration (`AL-523`, `UW-C328`).

    Dialogue is stripped first, as it is for every narrator-attribution
    detector here. "You go first," she said is one character addressing
    another; counting it would push a third-person book with ordinary quoted
    speech through the ceiling on dialogue it is entitled to have.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        PersonReport: The per-node second-person rate over narration.
    """
    nodes = 0
    hits = 0
    for node in cast("list[dict[str, Any]]", story.get("nodes") or []):
        narration = narration_of(cast("str", node.get("body") or ""))
        if not narration.strip():
            continue
        nodes += 1
        if _SECOND_PERSON_RE.search(narration):
            hits += 1
    return PersonReport(
        nodes=nodes,
        second_person_nodes=hits,
        rate=(hits / nodes) if nodes else 0.0,
    )


def judge_person(
    story: Mapping[str, Any],
    report: PersonReport,
    *,
    floor: float = MIN_GAMEBOOK_SECOND_PERSON,
    ceiling: float = MAX_THIRD_SECOND_PERSON,
) -> Judgment:
    """Apply the bound the book's own declaration implies (`UW-C328`).

    Keyed to the declared person rather than to a universal rate: a declared
    second-person book must clear the floor, a declared third-person book must
    stay under the ceiling, and an undeclared prose book is reported but never
    failed, because nothing pins its person and three correct fills of one
    skeleton spanned 0.07 to 0.72.

    Genre is tested before the declaration on purpose. ``StoryMetadata``
    rejects gamebook + third, so a conforming document arrives here declaring
    second or nothing; testing style first means a stale on-disk book carrying
    the old contradiction is measured against the second-person floor its
    prose actually targets, instead of being failed by a third-person ceiling
    for the second person its genre requires. The two orders agree on every
    document the model accepts.

    Args:
        story: Decoded filled-story JSON, read for its metadata declarations.
        report: The rate from :func:`person_report`.
        floor: Rate a gamebook, or a declared second-person book, must reach.
        ceiling: Rate a declared third-person book may not exceed.

    Returns:
        Judgment: Whether the book missed the bound its declaration implies,
        and which bound that was.
    """
    metadata = cast("dict[str, Any]", story.get("metadata") or {})
    declared = cast("str", metadata.get("narrative_person") or "")
    style = cast("str", metadata.get("narrative_style") or "")
    if declared == "third" and style == "gamebook":
        # Contradictory declaration: the gamebook genre addresses the reader,
        # so holding a correct second-person gamebook to the third-person
        # ceiling would invert the check. The model now rejects this pairing
        # at validation; a raw document carrying it is a contract error rather
        # than a measurement.
        return Judgment(
            breached=True,
            framing="contradictory declaration: a gamebook cannot be third person",
        )
    if style == "gamebook":
        # Style is tested BEFORE the remaining declaration branches: a gamebook
        # is second-person by genre whatever its metadata says, and testing the
        # declaration first sent it down a prose path.
        return Judgment(
            breached=report.rate < floor,
            framing=f"{declared or 'undeclared'} gamebook, floor {floor:.0%}",
        )
    if declared == "second":
        return Judgment(
            breached=report.rate < floor,
            framing=f"declared second, floor {floor:.0%}",
        )
    if declared == "third":
        return Judgment(
            breached=report.rate > ceiling,
            framing=f"declared third, ceiling {ceiling:.0%}",
        )
    return Judgment(breached=False, framing="undeclared prose, reported only")
