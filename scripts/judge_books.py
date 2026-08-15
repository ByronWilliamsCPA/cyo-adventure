"""Score filled books on prose quality with a blind, cross-lab judge panel.

``scripts/evaluate_books.py`` measures everything deterministic code can prove:
whether a book was finished, whether it hit its reading band, whether each node
matched the word count and beats its directive asked for. None of that can say
whether a story is any good. A book can hit every target and still be lifeless,
and the compliance axis will call it perfect.

So this is the other axis, and it is a model's opinion by necessity. Three
design constraints make that opinion worth something:

**Blind.** The judge never learns which model wrote what. Books are presented as
anonymous text, so a judge cannot reward a house style it recognises.

**Cross-lab.** A model asked to rank prose reliably favours its own family's
output. One judge would bake that bias into the headline, so the panel spans
three labs and every score is reported per judge as well as pooled. When a
judge's own family is under test, that row is the one to read sceptically, and
``self_family`` marks it so nobody has to remember which lab built which model.

**Normalised.** Judges differ in how freely they spend the top of a scale; one
may never award a 5. Pooling raw means would rank the legs a lenient judge
happened to see. Scores are z-scored within each judge before pooling, so the
pooled number reflects agreement about *ordering*, which is the thing three
independent judges can actually establish.

Only books that reached full fill completeness are judged. Scoring a book that
is three-quarters unwritten produces a number that looks like a quality verdict
and is really a delivery failure; the compliance axis already reports that, and
mixing the two is exactly the conflation this split exists to prevent.

Usage::

    uv run python scripts/judge_books.py \\
        --run out/vendor-comparison/run-1 \\
        --skeletons skeletons/5-8 \\
        --out out/vendor-comparison/evaluation \\
        --env-file .env
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.core.config import Settings  # noqa: E402
from cyo_adventure.generation.provider import build_openrouter_leg  # noqa: E402
from scripts._paid_output import (  # noqa: E402
    ensure_persistable,
    persistence_notice,
)
from scripts.evaluate_books import evaluate_book  # noqa: E402
from scripts.instrument import (  # noqa: E402
    Interval,
    bootstrap_interval,
    rank_separation,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.generation.provider import GenerationProvider


@dataclass(frozen=True, slots=True)
class Judge:
    """One member of the panel.

    Attributes:
        label: Short name used in the report.
        model: OpenRouter model slug.
        provider_order: Backend pin, so a judge's scores are attributable to one
            serving stack for the same reason the generating legs are.
        family: The judge's lineage, compared against each book's family to flag
            self-scoring.
    """

    label: str
    model: str
    provider_order: tuple[str, ...]
    family: str


# Three labs, none of them Anthropic-only, so no single lineage can carry the
# pooled verdict. Kept deliberately small: a fourth judge multiplies cost across
# every book for a smaller marginal gain than a fourth generating leg would give.
_PANEL: Final[tuple[Judge, ...]] = (
    Judge("judge-gpt-5.6", "openai/gpt-5.6-sol", ("azure",), "openai"),
    Judge(
        "judge-gemini-3.1",
        "google/gemini-3.1-pro-preview",
        ("google-vertex/global",),
        "google",
    ),
    Judge("judge-grok-4.6", "x-ai/grok-4.6", ("xai/zdr",), "xai"),
)

# Each criterion names what a 1 and a 5 look like, because an unanchored 1-to-5
# scale measures a judge's mood. The anchors are written for this product: a
# story a 5-to-8-year-old reads alone, in a branching format where the choices
# are the point.
_CRITERIA: Final[dict[str, str]] = {
    "age_fit": (
        "Suitability for a 5-to-8-year-old reading alone. 1 = vocabulary or "
        "sentence structure a 7-year-old would stall on, or themes too adult. "
        "5 = consistently readable at that age with no talking down."
    ),
    "imagery": (
        "Concreteness of sensory detail. 1 = abstract or generic description "
        "that could belong to any story. 5 = specific, physical detail a child "
        "can picture."
    ),
    "voice": (
        "Distinctness and consistency of the main character. 1 = interchangeable "
        "narrator with no personality. 5 = a character who reacts in a "
        "recognisable, consistent way throughout."
    ),
    "dialogue": (
        "Naturalness of spoken lines. 1 = stilted, expository, or absent where "
        "it is clearly needed. 5 = lines that sound like people talking. Score 3 "
        "if the story is legitimately narration-led with little dialogue."
    ),
    "choice_quality": (
        "Whether the branch points feel like real decisions. 1 = options that "
        "are cosmetic restatements of each other. 5 = options that promise "
        "genuinely different experiences and deliver on that promise."
    ),
    "ending_quality": (
        "Satisfaction of the endings reached. 1 = abrupt stops or flat morals. "
        "5 = endings that resolve what the story set up and feel earned."
    ),
    "engagement": (
        "Whether a child would want to read on. 1 = a chore. 5 = genuinely compelling."
    ),
}

# The band a book declares, substituted into the system block and the age_fit
# anchor. This was hardcoded to "5 to 8" while the panel was run across books
# from 3-5 to 16+, so every existing verdict was scored off-prompt: a 13-16 book
# was graded for a seven-year-old and its age_fit score means something other
# than what the column header says. Parameterising it changes the instrument, so
# a pool scored after this point is not strictly comparable to the 84-verdict one.
_DEFAULT_BAND: Final[str] = "5 to 8"


def _band_phrase(doc: dict[str, object]) -> str:
    """Return the reader age this book should be judged for.

    Args:
        doc: The story document.

    Returns:
        A phrase like ``"8 to 11"``, falling back to :data:`_DEFAULT_BAND` when
        the book declares no band. The fallback is the historical value, so a
        book without metadata is scored exactly as it was before.
    """
    metadata = doc.get("metadata")
    band = metadata.get("age_band") if isinstance(metadata, dict) else None
    if not isinstance(band, str) or "-" not in band:
        return _DEFAULT_BAND
    low, _, high = band.partition("-")
    return f"{low.strip()} to {high.strip()}"


def _system_for(band: str) -> str:
    """Build the system block for one age band.

    Args:
        band: The reader age phrase.

    Returns:
        The system block.
    """
    return (
        "You are an experienced children's-book editor evaluating a branching "
        f"story written for children aged {band}. You are strict and calibrated: "
        "most competent-but-unremarkable writing is a 3, and a 5 is reserved for "
        "work you would publish as-is. Judge only the writing in front of you. You "
        "do not know who or what wrote it, and you must not speculate. Return only "
        "the JSON object requested, with no commentary around it."
    )


_SYSTEM: Final[str] = _system_for(_DEFAULT_BAND)

# Completion budget per scoring. Sized to clear reasoning overhead plus the
# answer, not the answer alone: a reasoning judge spends hidden tokens before it
# emits anything, and whatever is left has to carry seven criteria with their
# notes. Measured 2026-08-12 against one 3,000-word book at an 8,000-token cap,
# the three panel judges returned 1,351, 1,530 and 1,360 characters of content
# (roughly 340 to 385 tokens), so the content is small and the overhead is what
# the budget must absorb. At 2,000 this truncated every Gemini 3.1 Pro reply
# mid-note, which surfaced as a JSONDecodeError and read as a malformed answer;
# see _parse for why that misreads. This is AL-323 recurring: size a budget by
# what the model spends before it can answer, not by the answer.
_JUDGE_MAX_TOKENS: Final[int] = 8000

# W4's saturation threshold, in raw scale points on the 1-to-5 scale, applied to
# the spread of a criterion's cell means.
#
# This number is provisional and is deliberately not load-bearing. The one
# calibration point we hold is the dialogue criterion at cell means of 3.00 for
# seven of eight legs and 3.25 for the eighth (AL-330), a spread of 0.088; a
# threshold has to sit above that. The "sd 0.19 across twelve cells" phrasing
# this once carried spliced two instruments and is not reproducible here. Nothing yet establishes where a
# working criterion's spread starts, which is what replaying the real verdict
# pool is for, so the report prints every criterion sorted flattest-first and
# the flag is an annotation on a table the reader can overrule. Admission rule 3
# of the workplan is the reason it stays that way: a measure does not become a
# gate by being computable.
_SATURATION_SD: Final[float] = 0.25

__all__ = [
    "CriterionSpread",
    "Judge",
    "Verdict",
    "criterion_spread",
    "judge_book",
    "leg_intervals",
    "panel_participation",
    "pool_scores",
]


@dataclass(frozen=True, slots=True)
class Verdict:
    """One judge's scoring of one book.

    Attributes:
        book: Identifier of the book scored, ``"<leg>#<brief>"``.
        leg: The generating leg's label.
        family: The generating leg's lineage.
        judge: The scoring judge's label.
        self_family: Whether judge and book share a lineage, which is the case
            to read sceptically.
        scores: Criterion name to 1-to-5 score.
        notes: The judge's one-line justification per criterion.
        error: Why scoring failed, or ``None``.
    """

    book: str
    leg: str
    family: str
    judge: str
    self_family: bool
    scores: dict[str, float]
    notes: dict[str, str]
    error: str | None


def _story_text(doc: dict[str, object]) -> str:
    """Render a book as readable text with its branch structure intact.

    A judge cannot assess choice quality from prose alone; it needs to see which
    options each node offered and where they led. Node ids are kept so the judge
    can follow a branch rather than reading the nodes as a flat sequence.

    Args:
        doc: The filled story document.

    Returns:
        The rendered story.
    """
    lines: list[str] = [f"TITLE: {doc.get('title', 'untitled')}", ""]
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        return "\n".join(lines)
    for node in nodes:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        marker = " [ENDING]" if node.get("is_ending") else ""
        lines.append(f"--- {node.get('id')}{marker} ---")
        lines.append(str(node.get("body", "")))
        choices = node.get("choices")  # pyright: ignore[reportUnknownMemberType]
        if isinstance(choices, list):
            lines.extend(
                f'  -> "{choice.get("label")}" leads to {choice.get("target")}'
                for choice in choices  # pyright: ignore[reportUnknownVariableType]
                if isinstance(choice, dict)
            )
        lines.append("")
    return "\n".join(lines)


def _prompt(story: str) -> str:
    """Build the judging prompt for one book.

    Args:
        story: The rendered story text.

    Returns:
        The user-role prompt.
    """
    rubric = "\n".join(f"- {name}: {desc}" for name, desc in _CRITERIA.items())
    shape = ", ".join(f'"{name}": {{"score": N, "note": "..."}}' for name in _CRITERIA)
    return (
        f"Score this branching children's story on each criterion from 1 to 5.\n\n"
        f"CRITERIA\n{rubric}\n\n"
        f"Return exactly this JSON shape and nothing else:\n"
        f"{{{shape}}}\n\n"
        f"Each note must be one sentence citing something specific in the text.\n\n"
        f"STORY\n{story}"
    )


def _parse(raw: str) -> tuple[dict[str, float], dict[str, str]]:
    """Extract scores and notes from a judge's reply.

    Args:
        raw: The judge's raw completion.

    Returns:
        Scores and notes, keyed by criterion.

    Raises:
        ValueError: If the reply was truncated, carries no JSON object, or
            parsed without yielding a single criterion.
    """
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        # Cut off before even the first inner brace closed. Same cause as the
        # decode failure below, different symptom, so give the same guidance.
        if raw.lstrip().startswith("{"):
            msg = (
                f"the judge's reply was cut off at {len(raw)} chars before any "
                f"JSON object closed; raise _JUDGE_MAX_TOKENS above "
                f"{_JUDGE_MAX_TOKENS}"
            )
            raise ValueError(msg)
        msg = f"no JSON object in reply: {raw[:120]!r}"
        raise ValueError(msg)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        # A truncated reply still matches the regex above, because the greedy
        # `\{.*\}` closes on the last *inner* brace the completion managed to
        # emit. The result is an unbalanced object whose decode error points at
        # that inner brace, which reads as a malformed answer from a judge that
        # cannot follow a schema. It is not: the schema was followed and the
        # budget ran out. The two need opposite fixes, so name the difference.
        truncated = not raw.rstrip().endswith("}")
        cause = (
            f"the completion was cut off at {len(raw)} chars, so raise "
            f"_JUDGE_MAX_TOKENS above {_JUDGE_MAX_TOKENS}"
            if truncated
            else "the judge emitted a complete but invalid object"
        )
        msg = f"could not parse the judge's JSON ({cause}): {exc}"
        raise ValueError(msg) from exc
    scores: dict[str, float] = {}
    notes: dict[str, str] = {}
    for name in _CRITERIA:
        entry = payload.get(name)
        if isinstance(entry, dict) and isinstance(entry.get("score"), (int, float)):
            scores[name] = float(entry["score"])
            notes[name] = str(entry.get("note", ""))
        elif isinstance(entry, (int, float)):
            scores[name] = float(entry)
            notes[name] = ""
    if not scores:
        msg = f"reply carried no recognised criterion: {raw[:120]!r}"
        raise ValueError(msg)
    return scores, notes


async def judge_book(
    provider: GenerationProvider,
    judge: Judge,
    doc: dict[str, object],
    *,
    leg: str,
    family: str,
    brief_index: int,
) -> Verdict:
    """Have one judge score one book.

    Args:
        provider: The judge's provider leg.
        judge: The judge being asked.
        doc: The filled story document.
        leg: The generating leg's label.
        family: The generating leg's lineage.
        brief_index: Which brief the book was written from.

    Returns:
        The verdict, carrying ``error`` when scoring failed.
    """
    book = f"{leg}#{brief_index}"
    blank = Verdict(
        book=book,
        leg=leg,
        family=family,
        judge=judge.label,
        self_family=judge.family == family,
        scores={},
        notes={},
        error=None,
    )
    try:
        completion = await provider.complete(
            system=_system_for(_band_phrase(doc)),
            prompt=_prompt(_story_text(doc)),
            max_tokens=_JUDGE_MAX_TOKENS,
        )
        # #CRITICAL: data integrity: `complete` returns a Completion, not a str,
        # since #701 wrapped the provider result to capture token usage. Passing
        # the wrapper to _parse raises inside the broad handler below, which
        # records every scoring as a failed one; the panel then returns an empty
        # scorecard that looks like an unlucky run rather than a wiring bug.
        # #VERIFY: test_judge_books.py stubs the provider with a real Completion
        # rather than a str, so the unwrap cannot be removed without a failure.
        scores, notes = _parse(completion.text)
    except Exception as exc:
        # Deliberately broad: one judge failing on one book must not abandon the
        # other hundred-odd scorings. The failure is recorded per book, and
        # pool_scores drops it rather than treating a missing score as a zero.
        return dataclasses.replace(blank, error=f"{type(exc).__name__}: {exc}")
    return dataclasses.replace(blank, scores=scores, notes=notes)


def _z_scores(verdicts: Sequence[Verdict]) -> dict[tuple[str, str], float]:
    """Normalise each judge's overall scores to its own mean and spread.

    Args:
        verdicts: Every successful verdict.

    Returns:
        ``(judge, book)`` to z-scored overall rating.
    """
    by_judge: dict[str, list[tuple[str, float]]] = {}
    for v in verdicts:
        if v.scores:
            by_judge.setdefault(v.judge, []).append(
                (v.book, statistics.fmean(v.scores.values()))
            )
    out: dict[tuple[str, str], float] = {}
    for judge, rows in by_judge.items():
        values = [value for _, value in rows]
        mean = statistics.fmean(values)
        # A judge who gave every book the same score carries no ordering
        # information; spreading by zero would be a divide-by-zero, and calling
        # every book average is the honest reading.
        spread = statistics.stdev(values) if len(values) > 1 else 0.0
        for book, value in rows:
            out[judge, book] = 0.0 if spread == 0 else (value - mean) / spread
    return out


def pool_scores(
    verdicts: Sequence[Verdict], *, peers_only: bool = False
) -> dict[str, dict[str, float | int]]:
    """Aggregate verdicts per generating leg.

    Args:
        verdicts: Every verdict, successful or not.
        peers_only: Drop scorings where the judge shares the generating leg's
            lab, so a leg's figure comes only from rival labs.

    Returns:
        Per-leg pooled figures: raw mean, judge-normalised mean, per-criterion
        means, and how many scorings succeeded.
    """
    good = [v for v in verdicts if v.scores and v.error is None]
    # The z-scores stay estimated from EVERY book a judge graded even when the
    # pool below drops some of them. A judge's leniency is a property of the
    # judge, so shrinking the sample it is measured from would add noise to the
    # correction while trying to remove bias from the average. Only the set of
    # rows being averaged changes.
    z = _z_scores(good)
    if peers_only:
        good = [v for v in good if not v.self_family]
    by_leg: dict[str, list[Verdict]] = {}
    for v in good:
        by_leg.setdefault(v.leg, []).append(v)

    pooled: dict[str, dict[str, float | int]] = {}
    for leg, rows in by_leg.items():
        entry: dict[str, float | int] = {
            "scorings": len(rows),
            "raw_mean": statistics.fmean(
                [statistics.fmean(v.scores.values()) for v in rows]
            ),
            "normalised_mean": statistics.fmean(
                [z[v.judge, v.book] for v in rows if (v.judge, v.book) in z]
            ),
        }
        for name in _CRITERIA:
            values = [v.scores[name] for v in rows if name in v.scores]
            if values:
                entry[name] = statistics.fmean(values)
        pooled[leg] = entry
    return pooled


@dataclass(frozen=True, slots=True)
class CriterionSpread:
    """How much one criterion varied across the cells it was asked to separate.

    Attributes:
        criterion: The criterion's name.
        cells: How many ``(leg, judge)`` cells contributed a mean.
        mean: The mean of the cell means, on the raw 1-to-5 scale.
        sd: Standard deviation of the cell means, or ``None`` when fewer than
            two cells scored it and no spread exists to report.
        saturated: Whether the spread sits below the stated threshold, which
            makes the criterion a constant entering the composite mean and
            diluting the criteria that do discriminate.
    """

    criterion: str
    cells: int
    mean: float
    sd: float | None
    saturated: bool


def criterion_spread(
    verdicts: Sequence[Verdict], *, threshold: float = _SATURATION_SD
) -> list[CriterionSpread]:
    """Report each criterion's spread across cells, flattest first (W4).

    A criterion returning nearly the same score for every leg is measuring
    nothing, and it does harm rather than merely wasting a column: the composite
    mean averages it in, so a constant pulls every leg toward the same figure and
    shrinks the differences the discriminating criteria found. The dialogue
    criterion did exactly this, and it was caught by accident when deterministic
    parsing showed one leg contained no dialogue at all while the criterion
    scored it 3.00 like everything else.

    The cell is ``(leg, judge)`` rather than the book. A judge's scoring of one
    leg's four books is one opinion about that leg, and pooling books into the
    cell first stops a leg with more books from widening the spread on volume.

    Args:
        verdicts: Every verdict, successful or not; failures are dropped.
        threshold: Spread below which a criterion is flagged saturated.

    Returns:
        One entry per criterion that was scored at all, ascending by spread so
        the flattest criterion is first whatever the threshold is set to.
    """
    good = [v for v in verdicts if v.scores and v.error is None]
    cells: dict[str, dict[tuple[str, str], list[float]]] = {}
    for v in good:
        for name, score in v.scores.items():
            cells.setdefault(name, {}).setdefault((v.leg, v.judge), []).append(score)

    out: list[CriterionSpread] = []
    for name, by_cell in cells.items():
        values = [statistics.fmean(scores) for scores in by_cell.values()]
        sd = statistics.stdev(values) if len(values) > 1 else None
        out.append(
            CriterionSpread(
                criterion=name,
                cells=len(values),
                mean=statistics.fmean(values),
                sd=sd,
                # A criterion scored in a single cell has no spread to be below
                # a threshold. Calling that saturated would flag thin data as a
                # broken instrument, which is a different finding.
                saturated=sd is not None and sd < threshold,
            )
        )
    return sorted(out, key=lambda row: (row.sd is None, row.sd or 0.0, row.criterion))


def leg_intervals(
    verdicts: Sequence[Verdict],
    *,
    seed: int = 20260813,
    resamples: int = 2000,
) -> dict[str, Interval]:
    """Bootstrap an interval around each leg's judge-normalised score (W5).

    The unit resampled is the **book**, not the scoring. Three judges grading one
    book are three opinions about one observation, and resampling scorings would
    narrow every interval by roughly the panel size while adding no evidence.

    Args:
        verdicts: Every verdict, successful or not; failures are dropped.
        seed: Seed for the resampling generator.
        resamples: How many resamples to draw per leg.

    Returns:
        Leg label to its interval. A leg with one book yields an incomplete
        interval rather than a zero-width one.
    """
    good = [v for v in verdicts if v.scores and v.error is None]
    z = _z_scores(good)
    per_book: dict[str, dict[str, list[float]]] = {}
    for v in good:
        if (v.judge, v.book) in z:
            per_book.setdefault(v.leg, {}).setdefault(v.book, []).append(
                z[v.judge, v.book]
            )
    return {
        leg: bootstrap_interval(
            [statistics.fmean(scores) for scores in books.values()],
            seed=seed,
            resamples=resamples,
        )
        for leg, books in per_book.items()
    }


def _print_criterion_spread(rows: Sequence[CriterionSpread]) -> None:
    """Print the per-criterion spread table and name any saturated criterion.

    Args:
        rows: Output of :func:`criterion_spread`, flattest first.
    """
    if not rows:
        print("\nNo criterion was scored, so no spread can be reported.")
        return
    print("\nCRITERION SPREAD  (W4; sd of cell means, flattest first)")
    width = max(len(row.criterion) for row in rows)
    print(f"  {'criterion':<{width}}  {'cells':>5} {'mean':>5} {'sd':>6}")
    for row in rows:
        sd = f"{row.sd:>6.2f}" if row.sd is not None else f"{'-':>6}"
        flag = "  <-- SATURATED" if row.saturated else ""
        print(f"  {row.criterion:<{width}}  {row.cells:>5} {row.mean:>5.2f} {sd}{flag}")
    flagged = [row.criterion for row in rows if row.saturated]
    if flagged:
        print(
            f"\n  {len(flagged)} criterion(s) below sd {_SATURATION_SD}: "
            f"{', '.join(flagged)}. A criterion that does not vary across cells "
            "carries no ordering information and dilutes the composite mean; "
            "prefer a deterministic measure where one exists for the same "
            "property, and retire the criterion otherwise."
        )


def _print_intervals(intervals: dict[str, Interval]) -> None:
    """Print each leg's interval and say plainly whether the ranking stands.

    Args:
        intervals: Output of :func:`leg_intervals`.
    """
    if not intervals:
        print("\nNo leg was scored, so no interval can be reported.")
        return
    ranking = rank_separation(intervals)
    width = max(len(leg) for leg in intervals)
    print("\nUNCERTAINTY  (W5; 95% bootstrap over books, on the normalised score)")
    print(f"  {'leg':<{width}}  {'point':>6} {'95% interval':>18} {'books':>5}")
    for leg in ranking.ordered:
        row = intervals[leg]
        bounds = (
            f"[{row.lo:+.2f}, {row.hi:+.2f}]" if row.complete else "incomplete, n<2"
        )
        print(f"  {leg:<{width}}  {row.point:>+6.2f} {bounds:>18} {row.n:>5}")

    if ranking.excluded:
        print(
            f"\n  Excluded from pair counting for having no usable interval: "
            f"{', '.join(ranking.excluded)}."
        )
    print(
        f"\n  {ranking.separated_pairs} of {ranking.total_pairs} pairs are "
        f"separated; best and worst "
        f"{'are' if ranking.extremes_separated else 'are NOT'} disjoint."
    )
    if not ranking.supported:
        print(
            "\n  RANKING NOT SUPPORTED. Every pair of intervals overlaps, so this "
            "slate establishes no ordering. Per the workplan's pre-registered "
            "rule (W5), the ranking is retracted rather than caveated."
        )


def _verdicts_from_payload(payload: dict[str, object]) -> list[Verdict]:
    """Rebuild verdicts from a previously written ``judgements.json``.

    Replaying a finished pool is what W4's decision rule asks for and is the
    only way to run either instrument check without paying for the panel again.

    Args:
        payload: The parsed ``judgements.json``.

    Returns:
        Every verdict the file recorded.

    Raises:
        KeyError: If the file carries no ``verdicts`` array.
    """
    rows = payload["verdicts"]
    if not isinstance(rows, list):
        msg = "judgements.json 'verdicts' must be an array"
        raise TypeError(msg)
    return [Verdict(**cast("dict[str, Any]", row)) for row in rows]


def _complete_books(
    run_dirs: Sequence[Path], skeleton_dir: Path
) -> list[dict[str, object]]:
    """Collect every fully filled book across the given runs.

    Args:
        run_dirs: Directories holding ``report.json`` and ``books/``.
        skeleton_dir: Where the runs' skeletons live.

    Returns:
        One entry per complete book, carrying its document and provenance.
    """
    out: list[dict[str, object]] = []
    for run_dir in run_dirs:
        payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        names: list[str] = list(payload["skeletons"])
        skeletons = [
            json.loads((skeleton_dir / n).read_text(encoding="utf-8")) for n in names
        ]
        for row in payload["books"]:
            if row.get("file") is None:
                continue
            doc = json.loads((run_dir / row["file"]).read_text(encoding="utf-8"))
            index = int(row["brief_index"])
            score = evaluate_book(
                doc,
                skeletons[index if len(skeletons) > 1 else 0],
                leg=row["vendor"],
                family=row["family"],
                brief_index=index,
            )
            if score.fill_completeness < 1.0:
                print(
                    f"  skipping {row['vendor']}#{index}: only "
                    f"{score.fill_completeness:.0%} of nodes were filled",
                    file=sys.stderr,
                )
                continue
            out.append(
                {
                    "doc": doc,
                    "leg": row["vendor"],
                    "family": row["family"],
                    "brief_index": index,
                }
            )
    return out


async def _run_panel(
    books: Sequence[dict[str, object]], settings: Settings
) -> list[Verdict]:
    """Score every book with every judge.

    Args:
        books: Complete books with provenance.
        settings: Settings supplying the credential.

    Returns:
        Every verdict.
    """
    verdicts: list[Verdict] = []
    for judge in _PANEL:
        provider = build_openrouter_leg(
            settings, model=judge.model, provider_order=judge.provider_order
        )
        for entry in books:
            verdict = await judge_book(
                provider,
                judge,
                entry["doc"],  # pyright: ignore[reportArgumentType]
                leg=str(entry["leg"]),
                family=str(entry["family"]),
                brief_index=int(entry["brief_index"]),  # pyright: ignore[reportArgumentType]
            )
            flag = " [SELF-FAMILY]" if verdict.self_family else ""
            detail = verdict.error or (
                f"{statistics.fmean(verdict.scores.values()):.2f}"
                if verdict.scores
                else "no scores"
            )
            print(f"  {judge.label} -> {verdict.book}{flag}: {detail}", file=sys.stderr)
            verdicts.append(verdict)
    return verdicts


def panel_participation(verdicts: Sequence[Verdict]) -> dict[str, dict[str, int]]:
    """Count each judge's attempted and successful scorings.

    The panel's worth rests on being cross-lab and blind, so the failure that
    matters is not how many scorings failed but whether they failed *together*.
    Thirteen failures spread over three judges is flakiness; thirteen inside one
    judge is a dead judge, and the cross-lab guarantee is gone while the pooled
    table keeps its shape. An aggregate count cannot tell those apart, so report
    the distribution instead.

    Args:
        verdicts: Every verdict, successful or not.

    Returns:
        Per judge, its ``attempted`` and ``scored`` counts.
    """
    counts: dict[str, dict[str, int]] = {}
    for v in verdicts:
        row = counts.setdefault(v.judge, {"attempted": 0, "scored": 0})
        row["attempted"] += 1
        if v.scores and v.error is None:
            row["scored"] += 1
    return counts


def _print_participation(counts: dict[str, dict[str, int]]) -> None:
    """Print per-judge participation and shout about any judge that contributed none.

    Args:
        counts: Output of :func:`panel_participation`.
    """
    print("\nPANEL PARTICIPATION")
    for judge, row in sorted(counts.items()):
        share = f"{row['scored']}/{row['attempted']}"
        note = "  <-- CONTRIBUTED NOTHING" if row["scored"] == 0 else ""
        print(f"  {judge:<20} {share:>8}{note}")
    silent = [j for j, row in counts.items() if row["scored"] == 0]
    if silent:
        print(
            f"\nWARNING: {len(silent)} of {len(counts)} judges scored no book "
            f"({', '.join(sorted(silent))}). The pooled figures below are NOT a "
            "cross-lab verdict; fix the judge and re-run before quoting them."
        )


def _print_table(
    pooled: dict[str, dict[str, float | int]],
    peers: dict[str, dict[str, float | int]] | None = None,
) -> None:
    """Print the pooled quality scorecard.

    Args:
        pooled: Output of :func:`pool_scores`.
        peers: Output of :func:`pool_scores` with ``peers_only=True``, printed
            as a second ranking column. A leg whose lab also sits on the panel
            is partly grading itself, and two of this panel's judges are the
            very models that generated legs, so the ordering is only safe to
            quote where these two columns agree.
    """
    if not pooled:
        print("\nNo book was scored.")
        return
    rows = sorted(pooled.items(), key=lambda kv: -float(kv[1]["normalised_mean"]))
    width = max(len(leg) for leg in pooled)
    names = list(_CRITERIA)
    header = (
        f"  {'leg':<{width}}  {'norm':>6} {'peer':>6} {'raw':>5} {'n':>3}  "
        + " ".join(f"{name[:6]:>6}" for name in names)
    )
    print("\nQUALITY  (blind cross-lab panel; normalised within judge)")
    print(header)
    for leg, entry in rows:
        cells = " ".join(
            f"{float(entry[name]):>6.2f}" if name in entry else f"{'-':>6}"
            for name in names
        )
        peer_entry = (peers or {}).get(leg)
        peer_cell = (
            f"{float(peer_entry['normalised_mean']):>+6.2f}"
            if peer_entry
            else f"{'-':>6}"
        )
        print(
            f"  {leg:<{width}}  {float(entry['normalised_mean']):>+6.2f} {peer_cell} "
            f"{float(entry['raw_mean']):>5.2f} {int(entry['scorings']):>3}  {cells}"
        )
    _print_self_family_note(pooled, peers or {})


def _print_self_family_note(
    pooled: dict[str, dict[str, float | int]],
    peers: dict[str, dict[str, float | int]],
) -> None:
    """Name the legs whose own lab scored them, and by how much it helped.

    Args:
        pooled: Every scoring, including self-family ones.
        peers: Rival-lab scorings only.
    """
    affected = [
        (leg, int(entry["scorings"]) - int(peers.get(leg, {}).get("scorings", 0)))
        for leg, entry in pooled.items()
    ]
    graded_by_own_lab = [(leg, n) for leg, n in affected if n > 0]
    if not graded_by_own_lab:
        return
    print("\n  Self-family scorings (a leg's own lab grading it), dropped in 'peer':")
    for leg, dropped in sorted(graded_by_own_lab, key=lambda kv: -kv[1]):
        entry = pooled[leg]
        peer_entry = peers.get(leg)
        if peer_entry is None:
            print(f"    {leg:<24} {dropped:>2} dropped  ->  no rival-lab scoring left")
            continue
        delta = float(entry["normalised_mean"]) - float(peer_entry["normalised_mean"])
        print(
            f"    {leg:<24} {dropped:>2} dropped  ->  own lab moved it "
            f"{delta:+.2f} in 'norm'"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Judge every complete book and write the panel's verdicts.

    Args:
        argv: Command-line arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=Path, dest="runs")
    parser.add_argument("--skeletons", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--allow-untracked-out",
        action="store_true",
        help="Permit a gitignored --out. Scratch runs only; see AL-368.",
    )
    parser.add_argument(
        "--judgements",
        type=Path,
        help=(
            "Replay a previously written judgements.json instead of calling the "
            "panel. Prints participation, the scorecard and both instrument "
            "checks with no network call and no cost."
        ),
    )
    args = parser.parse_args(argv)

    if args.judgements is not None:
        payload = cast(
            "dict[str, object]",
            json.loads(args.judgements.read_text(encoding="utf-8")),
        )
        return _report(_verdicts_from_payload(payload), out=args.out)

    if args.runs is None or args.skeletons is None or args.out is None:
        print(
            "Error: --run, --skeletons and --out are all required unless "
            "--judgements is given.",
            file=sys.stderr,
        )
        return 2

    ensure_persistable(args.out, allow_untracked=args.allow_untracked_out)

    if args.env_file.exists():
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = (
                    line.split("=", 1)[1].strip().strip("'\"")
                )

    books = _complete_books(args.runs, args.skeletons)
    if not books:
        print("Error: no complete books to judge.", file=sys.stderr)
        return 1
    print(
        f"Judging {len(books)} complete books with {len(_PANEL)} judges "
        f"({len(books) * len(_PANEL)} scorings).",
        file=sys.stderr,
    )

    verdicts = asyncio.run(_run_panel(books, Settings()))
    return _report(verdicts, out=args.out)


def _report(verdicts: Sequence[Verdict], *, out: Path | None) -> int:
    """Print every panel report and write the artifact when asked to.

    Shared by the live path and the replay path so a replayed pool cannot
    silently be analysed differently from the run that produced it.

    Args:
        verdicts: Every verdict, successful or not.
        out: Directory to write ``judgements.json`` into, or ``None`` to print
            only.

    Returns:
        Process exit status.
    """
    pooled = pool_scores(verdicts)
    peers = pool_scores(verdicts, peers_only=True)
    participation = panel_participation(verdicts)
    spread = criterion_spread(verdicts)
    intervals = leg_intervals(verdicts)

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "judgements.json").write_text(
            json.dumps(
                {
                    "panel": [dataclasses.asdict(j) for j in _PANEL],
                    "participation": participation,
                    "criteria": _CRITERIA,
                    "verdicts": [dataclasses.asdict(v) for v in verdicts],
                    "pooled": pooled,
                    "pooled_peers_only": peers,
                    "criterion_spread": [dataclasses.asdict(row) for row in spread],
                    "intervals": {
                        leg: dataclasses.asdict(row) for leg, row in intervals.items()
                    },
                    "ranking": dataclasses.asdict(rank_separation(intervals))
                    if intervals
                    else None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    _print_participation(participation)
    _print_table(pooled, peers)
    _print_criterion_spread(spread)
    _print_intervals(intervals)
    failed = sum(1 for v in verdicts if v.error is not None)
    if failed:
        print(f"\n{failed} of {len(verdicts)} scorings failed; see judgements.json")
    if out is not None:
        print(f"Wrote {out / 'judgements.json'}")
        print(persistence_notice(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
