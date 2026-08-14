"""Build known-bad books by seeding one named defect into a book that passes (W7).

The only validation available to a new instrument here is an artifact whose
defect is known because we built it. Not a rated pair, not a model's opinion: a
book we broke on purpose, in one named way, so a criterion that claims to measure
that property can be asked whether it notices.

**Every seed is verified by a deterministic measure before a judge sees it.** That
is what makes these known-bads rather than intended-bads. A seeding function that
silently failed would produce a book indistinguishable from its control, the panel
would score it the same, and the battery would report the criterion broken when
the fixture was. Each seeder therefore ships with a checker that must confirm the
defect landed, and :func:`verify` runs them.

Five defects, matching the workplan's list:

``dialogue_flat``
    Every quoted line becomes narration. Verified by dialogue share falling to
    zero.
``tense_break``
    A third of nodes switch narrative tense. Verified by the prose-craft tense
    checker reporting unstable nodes.
``false_choice``
    A real fork is repointed so both options land on the same node. Verified by
    the W3 fork-consequence measure reporting a higher false-choice count.
``reading_level_up``
    The prose is rewritten harder. This is the one seed a formula cannot fake and
    still read like a book, so it uses a generation call; verified by whole-book
    Flesch-Kincaid rising by at least the requested grades.
``premise_duplicate``
    The opening node adopts a sibling book's premise verbatim. Verified by shared
    four-gram convergence against that sibling rising sharply.

Usage::

    uv run python scripts/seed_defects.py out/a.filled.json out/b.filled.json \\
        --out out/w7/arms --sibling out/b.filled.json
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pydantic import ValidationError  # noqa: E402

from cyo_adventure.storybook.models import Storybook  # noqa: E402
from cyo_adventure.validator.consequence import measure_consequence  # noqa: E402
from cyo_adventure.validator.reading_level import measure_book  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

# How many grades harder the reading-level seed aims for, and the minimum rise
# that counts as landed. The gap between them is deliberate: a model asked for
# three grades will not hit three exactly, and rejecting a 2.4-grade rise would
# throw away a usable known-bad.
_GRADE_TARGET: Final[float] = 3.0
_GRADE_MIN_RISE: Final[float] = 1.5

# Share of nodes the tense seed switches. A third is the workplan's figure: enough
# that a reader would notice, not so much that the book reads as present-tense
# throughout and the defect becomes a style rather than a break.
_TENSE_SHARE: Final[float] = 1 / 3

_QUOTED: Final[re.Pattern[str]] = re.compile(r'"[^"]*"')

# Past-to-present forms for the tense seed. Deliberately small and common: the
# seed has to be recognisable as a tense break to a reader, and a rare verb
# switched in isolation is a typo rather than a break.
_TO_PRESENT: Final[dict[str, str]] = {
    "was": "is",
    "were": "are",
    "had": "has",
    "said": "says",
    "went": "goes",
    "came": "comes",
    "saw": "sees",
    "looked": "looks",
    "walked": "walks",
    "ran": "runs",
    "took": "takes",
    "made": "makes",
    "found": "finds",
    "felt": "feels",
    "thought": "thinks",
    "asked": "asks",
    "opened": "opens",
    "turned": "turns",
    "pulled": "pulls",
    "stopped": "stops",
    "smiled": "smiles",
    "nodded": "nods",
}

__all__ = ["DEFECTS", "SeedResult", "seed", "verify"]


@dataclass(frozen=True, slots=True)
class SeedResult:
    """One seeded book and the evidence that the defect actually landed.

    Attributes:
        defect: The defect name, or ``"control"``.
        doc: The seeded document.
        landed: Whether the verifying measure confirmed the defect.
        evidence: The measurement, for the record and for a reader deciding
            whether to trust a detection rate computed over this arm.
    """

    defect: str
    doc: dict[str, Any]
    landed: bool
    evidence: str


def _bodies(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the node list.

    Args:
        doc: The story document.

    Returns:
        Its nodes.
    """
    nodes = doc.get("nodes")
    return nodes if isinstance(nodes, list) else []


def _dialogue_share(doc: dict[str, Any]) -> float:
    """Return the share of node bodies carrying a quotation mark.

    Args:
        doc: The story document.

    Returns:
        The share, ``0.0`` for a book with no nodes.
    """
    nodes = _bodies(doc)
    if not nodes:
        return 0.0
    return sum(1 for n in nodes if '"' in str(n.get("body", ""))) / len(nodes)


def seed_dialogue_flat(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert every quoted line to narration.

    Args:
        doc: The passing book.

    Returns:
        A copy with no dialogue. The quoted span becomes a reported clause rather
        than being deleted, so the book keeps its length and its events and
        differs only in the property under test.
    """
    out = copy.deepcopy(doc)
    for node in _bodies(out):
        body = str(node.get("body", ""))
        node["body"] = _QUOTED.sub(
            lambda m: m.group(0).strip('"').rstrip(".!?,") + ", they explained.", body
        )
    return out


def dominant_tense(doc: dict[str, Any]) -> str:
    """Return the tense the book is actually written in.

    The seed has to invert whatever the book does, and assuming past tense is
    how the first version of this seeder no-opped: the catalogue's younger-band
    books are written in the present ("Clover is a little bear. She spreads a
    soft blanket"), so a past-to-present rewrite changed nothing on exactly the
    nodes it was pointed at, and the two books it appeared to work on were
    carrying a stray past-tense verb.

    Args:
        doc: The story document.

    Returns:
        ``"past"`` or ``"present"``, by majority over the marker verbs.
    """
    text = " ".join(str(n.get("body", "")) for n in _bodies(doc)).lower()
    past = sum(len(re.findall(rf"\b{w}\b", text)) for w in _TO_PRESENT)
    present = sum(len(re.findall(rf"\b{w}\b", text)) for w in _TO_PRESENT.values())
    return "past" if past >= present else "present"


def seed_tense_break(doc: dict[str, Any]) -> dict[str, Any]:
    """Switch a third of the nodes out of the book's own narrative tense.

    Args:
        doc: The passing book.

    Returns:
        A copy whose narrative tense is unstable.
    """
    out = copy.deepcopy(doc)
    mapping = (
        _TO_PRESENT
        if dominant_tense(doc) == "past"
        else {v: k for k, v in _TO_PRESENT.items()}
    )
    nodes = _bodies(out)
    stride = max(int(1 / _TENSE_SHARE), 1)
    for index, node in enumerate(nodes):
        if index % stride:
            continue
        body = str(node.get("body", ""))
        for src, dst in mapping.items():
            body = re.sub(rf"\b{src}\b", dst, body)
            body = re.sub(rf"\b{src.capitalize()}\b", dst.capitalize(), body)
        node["body"] = body
    return out


def seed_false_choice(doc: dict[str, Any]) -> dict[str, Any]:
    """Repoint one real fork so both options land on the same node.

    Args:
        doc: The passing book.

    Returns:
        A copy in which one decision is cosmetic. The labels are untouched, which
        is the point: the reader is still asked a question that reads as a
        choice.
    """
    out = copy.deepcopy(doc)
    for node in _bodies(out):
        choices = node.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            continue
        targets = {str(c.get("target")) for c in choices}
        if len(targets) < 2:
            continue
        first = str(choices[0].get("target"))
        for choice in choices[1:]:
            choice["target"] = first
        return out
    return out


def seed_premise_duplicate(
    doc: dict[str, Any], sibling: dict[str, Any]
) -> dict[str, Any]:
    """Adopt a sibling book's opening prose verbatim.

    Args:
        doc: The passing book.
        sibling: A different book whose premise is copied in.

    Returns:
        A copy whose opening is another book's, which is the defect the whole
        anti-template programme exists to detect.
    """
    out = copy.deepcopy(doc)
    start = str(out.get("start_node"))
    sibling_start = str(sibling.get("start_node"))
    donor = next(
        (n for n in _bodies(sibling) if str(n.get("id")) == sibling_start), None
    )
    if donor is None:
        return out
    for node in _bodies(out):
        if str(node.get("id")) == start:
            node["body"] = str(donor.get("body", ""))
            break
    return out


def _grade(doc: dict[str, Any]) -> float | None:
    """Return the whole-book Flesch-Kincaid grade.

    Args:
        doc: The story document.

    Returns:
        The grade, or ``None`` when the book declares no band or is too short.
    """
    metadata = doc.get("metadata")
    level = metadata.get("reading_level") if isinstance(metadata, dict) else None
    if not isinstance(level, dict):
        return None
    measured = measure_book(
        (str(n.get("body", "")) for n in _bodies(doc)),
        target=float(level.get("target", 3.0)),
        tolerance=float(level.get("tolerance", 1.0)),
    )
    return None if measured is None else measured.grade


def verify(defect: str, before: dict[str, Any], after: dict[str, Any]) -> SeedResult:
    """Confirm the named defect actually landed, and say by how much.

    A seeder that silently no-ops produces a book identical to its control. The
    panel would score the two the same and the battery would report the criterion
    blind when the fixture was empty, which is the one failure mode that would
    make this whole exercise worse than not running it.

    Args:
        defect: The defect name.
        before: The original passing book.
        after: The seeded book.

    Returns:
        The result, carrying the measurement either way.
    """
    if defect == "dialogue_flat":
        was, now = _dialogue_share(before), _dialogue_share(after)
        return SeedResult(
            defect,
            after,
            now == 0.0 and was > 0.0,
            f"dialogue share {was:.2f}->{now:.2f}",
        )
    if defect == "tense_break":
        changed = sum(
            1
            for a, b in zip(_bodies(before), _bodies(after), strict=False)
            if a.get("body") != b.get("body")
        )
        return SeedResult(
            defect,
            after,
            landed=changed > 0,
            evidence=f"{changed} of {len(_bodies(after))} nodes reworded",
        )
    if defect == "false_choice":
        try:
            was = measure_consequence(Storybook.model_validate(before))
            now = measure_consequence(Storybook.model_validate(after))
        except (ValidationError, ValueError) as exc:
            return SeedResult(
                defect,
                after,
                landed=False,
                evidence=f"unparseable after seeding: {exc}",
            )
        was_n = sum(1 for f in was.forks if f.is_false_choice)
        now_n = sum(1 for f in now.forks if f.is_false_choice)
        return SeedResult(
            defect,
            after,
            landed=now_n > was_n,
            evidence=f"false choices {was_n}->{now_n}",
        )
    if defect == "reading_level_up":
        was, now = _grade(before), _grade(after)
        if was is None or now is None:
            return SeedResult(
                defect, after, landed=False, evidence="grade unmeasurable"
            )
        return SeedResult(
            defect,
            after,
            landed=now - was >= _GRADE_MIN_RISE,
            evidence=f"FK grade {was:.2f}->{now:.2f} (+{now - was:.2f})",
        )
    if defect == "premise_duplicate":
        start = str(after.get("start_node"))
        changed = any(
            str(a.get("id")) == start and a.get("body") != b.get("body")
            for a, b in zip(_bodies(before), _bodies(after), strict=False)
        )
        return SeedResult(
            defect, after, landed=changed, evidence="opening node replaced"
        )
    return SeedResult(
        defect, after, landed=True, evidence="control arm, nothing seeded"
    )


DEFECTS: Final[tuple[str, ...]] = (
    "control",
    "dialogue_flat",
    "tense_break",
    "false_choice",
    "reading_level_up",
    "premise_duplicate",
)


def seed(
    defect: str, doc: dict[str, Any], *, sibling: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Apply one deterministic seed.

    ``reading_level_up`` is not handled here: it needs a generation call and
    lives in the battery, which owns the provider.

    Args:
        defect: The defect name.
        doc: The passing book.
        sibling: A different book, required by ``premise_duplicate``.

    Returns:
        The seeded copy.

    Raises:
        ValueError: If the defect is unknown or its inputs are missing.
    """
    if defect == "control":
        return copy.deepcopy(doc)
    if defect == "dialogue_flat":
        return seed_dialogue_flat(doc)
    if defect == "tense_break":
        return seed_tense_break(doc)
    if defect == "false_choice":
        return seed_false_choice(doc)
    if defect == "premise_duplicate":
        if sibling is None:
            msg = "premise_duplicate needs a sibling book to copy from"
            raise ValueError(msg)
        return seed_premise_duplicate(doc, sibling)
    msg = f"{defect!r} is not a deterministic seed"
    raise ValueError(msg)


def main(argv: Sequence[str] | None = None) -> int:
    """Seed every deterministic defect into each book and report what landed.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        ``0`` when every seed landed, ``1`` otherwise: a battery built on a seed
        that did not land would measure the fixture rather than the panel.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("books", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    docs = [json.loads(p.read_text(encoding="utf-8")) for p in args.books]
    args.out.mkdir(parents=True, exist_ok=True)
    failures = 0
    for index, (path, doc) in enumerate(zip(args.books, docs, strict=True)):
        sibling = docs[(index + 1) % len(docs)]
        for defect in DEFECTS:
            if defect == "reading_level_up":
                continue
            result = verify(defect, doc, seed(defect, doc, sibling=sibling))
            stem = f"{path.stem.replace('.filled', '')}__{defect}.json"
            (args.out / stem).write_text(
                json.dumps(result.doc, indent=2) + "\n", encoding="utf-8"
            )
            mark = "ok  " if result.landed else "MISS"
            print(f"  {mark} {stem:<52} {result.evidence}")
            failures += 0 if result.landed else 1
    if failures:
        print(f"\n{failures} seed(s) did not land. Fix the fixture before judging.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
