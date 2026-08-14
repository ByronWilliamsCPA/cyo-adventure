"""Score filled books on a compliance axis and a prose-character axis.

The vendor comparison answers one question: does rotating the model change the
shared idiom between books. It deliberately says nothing about whether a book is
any *good*, and the one quality signal it does carry (a Flesch-Kincaid grade) is
easy to over-read. A leg that emitted no prose at all scores ``None`` there,
which looks like a missing measurement rather than a total failure.

This script separates the two things that get conflated:

**Compliance** is what deterministic code can prove. A skeleton node does not
just ask for prose, it asks for a specific amount of prose covering specific
beats: ``<<FILL role=choice words=80 beats='...'>>``. So "did the model do what
it was told" is measurable by joining each filled node back to the directive
that requested it. Add the Layer-1 validator (topology, references, budget,
endings), the whole-book reading level, and residual placeholder leakage, and
compliance is fully determined without asking any model's opinion.

**Prose character** is measured here, not judged. Type-token ratio, sentence
length spread, and dialogue share describe *how* a leg writes; they do not say
whether it writes well. Calling them quality would be a category error, which is
why they are reported under their own heading and why the LLM judge panel in
``scripts/judge_books.py`` exists separately.

Every number here is free and reproducible: no network, no model, no cost.

Usage::

    uv run python scripts/evaluate_books.py \\
        --run out/vendor-comparison/run-1 \\
        --run out/vendor-comparison/run-2 \\
        --skeletons skeletons/5-8 \\
        --out out/vendor-comparison/evaluation
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.validator.layer1 import validate_layer1  # noqa: E402
from cyo_adventure.validator.policy import FILL_MARKER  # noqa: E402
from cyo_adventure.validator.reading_level import (  # noqa: E402
    measure_book,
    score_body,
)
from cyo_adventure.validator.report import Severity  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# A FILL directive as the skeletons write it, e.g.
# <<FILL role=choice words=80 beats='...'>>
_FILL_RE: Final[re.Pattern[str]] = re.compile(
    r"<<FILL\s+role=(?P<role>\w+)\s+words=(?P<words>\d+)\s+beats='(?P<beats>[^']*)'",
)

# Binding slots the generator is supposed to replace. Any survivor in a filled
# book is a hard compliance failure: the child would read a literal {HERO}.
_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"\{[A-Z][A-Z0-9_]*\}")

_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENTENCE_RE: Final[re.Pattern[str]] = re.compile(r"[.!?]+(?:\s|$)")

# Words carried by nearly every beat string, so their presence in a body proves
# nothing about whether the beat was covered.
_BEAT_STOPWORDS: Final[frozenset[str]] = frozenset(
    """a an and are as at be been but by can could did do does for from had has
    have he her hers him his how if in into is it its more most no not of off on
    once one or our out over own she should so some still such than that the
    their them then there these they this those to too until up very was we were
    what when where which while who whom why will with would you your""".split()
)

# How far a node may miss its declared word target and still count as on budget.
# Wide on purpose: the directive is a brief, not a contract, and a sentence over
# is not a defect. A leg that routinely lands outside this is not writing to the
# brief at all.
_WORD_BUDGET_TOLERANCE: Final[float] = 0.25

# Window for the moving-average type-token ratio. Plain TTR falls as a text
# grows, so comparing a 2,200-word book against a 4,300-word one on raw TTR
# measures length, not vocabulary. MATTR holds the window fixed instead.
_MATTR_WINDOW: Final[int] = 100

__all__ = [
    "BookScore",
    "LegSummary",
    "evaluate_book",
    "summarize_leg",
]


@dataclass(frozen=True, slots=True)
class BookScore:
    """Every deterministic measurement for one filled book.

    Attributes:
        leg: The vendor label that produced the book.
        family: The producing leg's training lineage.
        brief_index: Which brief, and therefore which skeleton, it was written
            from.
        nodes: Node count in the filled document.
        filled_nodes: Nodes whose body no longer holds a FILL directive.
        fill_completeness: ``filled_nodes / nodes``. The single most important
            number here: a book below 1.0 was not finished, and every other
            measurement on it is drawn from a partial text.
        placeholder_leaks: Count of unreplaced ``{SLOT}`` tokens.
        l1_errors: Layer-1 findings at error severity (a publication blocker).
        l1_warnings: Layer-1 findings at warning severity.
        grade: Whole-book Flesch-Kincaid grade, or ``None`` when the book holds
            too little prose to score.
        in_band: Fraction of scorable nodes inside the band.
        grade_spread: Standard deviation of per-node grade. A leg can hit the
            band on average while swinging wildly node to node, which reads as
            unevenness to a child.
        word_ratio_median: Median of ``actual / requested`` words per node.
            Above 1.0 means the leg overwrites its brief.
        word_on_budget: Fraction of nodes within ``_WORD_BUDGET_TOLERANCE``.
        beat_recall: Mean fraction of each directive's content words that
            surface in the node that answered it. A lexical proxy for beat
            coverage, not a semantic one; see the module docstring.
        mattr: Moving-average type-token ratio, vocabulary variety at fixed
            window length.
        mean_sentence_words: Mean words per sentence.
        sentence_spread: Standard deviation of sentence length. Uniform short
            sentences and varied ones can share a mean and read nothing alike.
        dialogue_share: Fraction of sentences carrying a quotation mark.
        total_words: Words across all filled bodies.
    """

    leg: str
    family: str
    brief_index: int
    nodes: int
    filled_nodes: int
    fill_completeness: float
    placeholder_leaks: int
    l1_errors: int
    l1_warnings: int
    grade: float | None
    in_band: float | None
    grade_spread: float | None
    word_ratio_median: float | None
    word_on_budget: float | None
    beat_recall: float | None
    mattr: float | None
    mean_sentence_words: float | None
    sentence_spread: float | None
    dialogue_share: float | None
    total_words: int


@dataclass(frozen=True, slots=True)
class LegSummary:
    """One leg's mean scores across its books.

    Attributes:
        leg: The vendor label.
        family: The training lineage.
        books: How many books the leg produced.
        complete_books: How many reached ``fill_completeness == 1.0``.
        means: Mean of every numeric field across books, keyed by field name.
            Books that produced no prose are excluded from prose means but
            still counted in ``books``, so a leg cannot raise its average by
            failing.
    """

    leg: str
    family: str
    books: int
    complete_books: int
    means: dict[str, float | None]


def _words(text: str) -> list[str]:
    """Return alphabetic word tokens, lowercased.

    Args:
        text: Any prose.

    Returns:
        The tokens.
    """
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def _stem(word: str) -> str:
    """Strip common inflections so 'counts' matches 'count'.

    Crude by design. A real stemmer would add a dependency to serve a proxy
    measurement that the LLM judge supersedes.

    Args:
        word: A lowercased token.

    Returns:
        The token with a trailing inflection removed.
    """
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _beat_terms(beats: str) -> set[str]:
    """Return the content words a beat string asks the node to cover.

    Placeholders are dropped: ``{HERO}`` is bound to a name chosen per brief, so
    its literal text never appears and counting it would depress every score
    equally. Stopwords are dropped for the same reason in reverse: they appear
    everywhere and would inflate every score equally.

    Args:
        beats: The raw ``beats='...'`` payload.

    Returns:
        Stemmed content terms.
    """
    without_slots = _PLACEHOLDER_RE.sub(" ", beats)
    return {
        _stem(w)
        for w in _words(without_slots)
        if len(w) > 3 and w not in _BEAT_STOPWORDS
    }


def _mattr(tokens: Sequence[str], window: int = _MATTR_WINDOW) -> float | None:
    """Return the moving-average type-token ratio.

    Args:
        tokens: Word tokens in order.
        window: Window width in tokens.

    Returns:
        Mean distinct-word fraction across every window, or plain TTR when the
        text is shorter than one window, or ``None`` when it is empty.
    """
    if not tokens:
        return None
    if len(tokens) <= window:
        return len(set(tokens)) / len(tokens)
    ratios = [
        len(set(tokens[i : i + window])) / window
        for i in range(len(tokens) - window + 1)
    ]
    return statistics.fmean(ratios)


def _sentence_lengths(text: str) -> list[int]:
    """Return the word count of each sentence.

    Args:
        text: Any prose.

    Returns:
        One length per non-empty sentence.
    """
    return [n for part in _SENTENCE_RE.split(text) if (n := len(_words(part))) > 0]


def _dialogue_share(text: str) -> float | None:
    """Return the fraction of sentences carrying a quotation mark.

    Args:
        text: Any prose.

    Returns:
        The fraction, or ``None`` when there are no sentences.
    """
    parts = [p for p in _SENTENCE_RE.split(text) if _words(p)]
    if not parts:
        return None
    quoted = sum(1 for p in parts if '"' in p or "“" in p or "”" in p)
    return quoted / len(parts)


def _directives(skeleton: dict[str, object]) -> dict[str, tuple[int, set[str]]]:
    """Map node id to its requested word count and beat terms.

    Args:
        skeleton: The unfilled skeleton document.

    Returns:
        One entry per node whose body holds a parseable FILL directive.
    """
    out: dict[str, tuple[int, set[str]]] = {}
    nodes = skeleton.get("nodes")
    if not isinstance(nodes, list):
        return out
    for node in nodes:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        body = node.get("body")
        if not isinstance(node_id, str) or not isinstance(body, str):
            continue
        match = _FILL_RE.search(body)
        if match is None:
            continue
        out[node_id] = (int(match.group("words")), _beat_terms(match.group("beats")))
    return out


def _bodies(doc: dict[str, object]) -> list[tuple[str, str]]:
    """Return ``(node_id, body)`` for every node in a document.

    Args:
        doc: A filled or unfilled story document.

    Returns:
        Node ids paired with their bodies.
    """
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        return []
    out: list[tuple[str, str]] = []
    for node in nodes:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        body = node.get("body")
        if isinstance(node_id, str) and isinstance(body, str):
            out.append((node_id, body))
    return out


def _band(doc: dict[str, object]) -> tuple[float, float] | None:
    """Return the declared reading-level target and tolerance.

    Args:
        doc: A story document.

    Returns:
        ``(target, tolerance)``, or ``None`` when the book declares no usable
        band.
    """
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        return None
    level = metadata.get("reading_level")  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(level, dict):
        return None
    target = level.get("target")  # pyright: ignore[reportUnknownMemberType]
    tolerance = level.get("tolerance")  # pyright: ignore[reportUnknownMemberType]
    # bool is an int subclass; a JSON `true`/`false` here is malformed
    # metadata, not a target/tolerance of 1.0, so it must not silently
    # become one (mirrors reading_level_loop.py's _band guard).
    if isinstance(target, bool) or isinstance(tolerance, bool):
        return None
    if not isinstance(target, (int, float)) or not isinstance(tolerance, (int, float)):
        return None
    return float(target), float(tolerance)


def _fidelity(
    bodies: Sequence[tuple[str, str]], directives: dict[str, tuple[int, set[str]]]
) -> tuple[float | None, float | None, float | None]:
    """Compare each filled body against the directive that requested it.

    Args:
        bodies: ``(node_id, body)`` pairs from the filled book.
        directives: Requested word count and beat terms, keyed by node id.

    Returns:
        ``(median word ratio, on-budget fraction, mean beat recall)``, each
        ``None`` when no node could be compared.
    """
    ratios: list[float] = []
    recalls: list[float] = []
    for node_id, body in bodies:
        request = directives.get(node_id)
        if request is None or FILL_MARKER in body:
            continue
        requested, terms = request
        tokens = _words(body)
        if requested > 0:
            ratios.append(len(tokens) / requested)
        if terms:
            present = {_stem(t) for t in tokens}
            recalls.append(len(terms & present) / len(terms))
    if not ratios:
        return None, None, (statistics.fmean(recalls) if recalls else None)
    on_budget = sum(1 for r in ratios if abs(r - 1.0) <= _WORD_BUDGET_TOLERANCE)
    return (
        statistics.median(ratios),
        on_budget / len(ratios),
        statistics.fmean(recalls) if recalls else None,
    )


def evaluate_book(
    doc: dict[str, object],
    skeleton: dict[str, object],
    *,
    leg: str,
    family: str,
    brief_index: int,
) -> BookScore:
    """Score one filled book against the skeleton it was filled from.

    Args:
        doc: The filled story document.
        skeleton: The skeleton whose FILL directives produced it.
        leg: The producing vendor label.
        family: The producing leg's lineage.
        brief_index: Which brief the book was written from.

    Returns:
        Every deterministic measurement for the book.
    """
    bodies = _bodies(doc)
    filled = [(nid, b) for nid, b in bodies if FILL_MARKER not in b]
    prose = " ".join(b for _, b in filled)
    tokens = _words(prose)

    report = validate_layer1(doc)
    errors = sum(1 for f in report.findings if f.severity is Severity.ERROR)
    warnings = sum(1 for f in report.findings if f.severity is Severity.WARNING)

    band = _band(doc)
    measured = (
        measure_book([b for _, b in bodies], target=band[0], tolerance=band[1])
        if band is not None
        else None
    )
    per_node = [g for _, b in bodies if (g := score_body(b)) is not None]
    lengths = _sentence_lengths(prose)
    ratio, on_budget, recall = _fidelity(bodies, _directives(skeleton))

    return BookScore(
        leg=leg,
        family=family,
        brief_index=brief_index,
        nodes=len(bodies),
        filled_nodes=len(filled),
        fill_completeness=len(filled) / len(bodies) if bodies else 0.0,
        placeholder_leaks=len(_PLACEHOLDER_RE.findall(prose)),
        l1_errors=errors,
        l1_warnings=warnings,
        grade=measured.grade if measured is not None else None,
        in_band=measured.in_band if measured is not None else None,
        grade_spread=statistics.stdev(per_node) if len(per_node) > 1 else None,
        word_ratio_median=ratio,
        word_on_budget=on_budget,
        beat_recall=recall,
        mattr=_mattr(tokens),
        mean_sentence_words=statistics.fmean(lengths) if lengths else None,
        sentence_spread=statistics.stdev(lengths) if len(lengths) > 1 else None,
        dialogue_share=_dialogue_share(prose),
        total_words=len(tokens),
    )


def summarize_leg(scores: Sequence[BookScore]) -> LegSummary:
    """Average one leg's book scores.

    Prose measurements are averaged over books that produced prose. A leg that
    emitted nothing for a book would otherwise either poison the mean with a
    zero or, worse, quietly raise it by dropping a bad book. ``books`` and
    ``complete_books`` keep the failure visible either way.

    Args:
        scores: Every book from one leg. Must not be empty.

    Returns:
        The leg's summary.
    """
    numeric = [
        f.name
        for f in dataclasses.fields(BookScore)
        if f.name not in {"leg", "family", "brief_index"}
    ]
    means: dict[str, float | None] = {}
    for name in numeric:
        values = [
            v
            for s in scores
            if isinstance(v := getattr(s, name), (int, float)) and v is not None
        ]
        means[name] = statistics.fmean(values) if values else None
    return LegSummary(
        leg=scores[0].leg,
        family=scores[0].family,
        books=len(scores),
        complete_books=sum(1 for s in scores if s.fill_completeness >= 1.0),
        means=means,
    )


def _skeleton_for(
    skeletons: Sequence[dict[str, object]], index: int, *, run_dir: Path
) -> dict[str, object]:
    """Select the skeleton a book's ``brief_index`` maps to.

    A run's report declares either one shared skeleton (every book in the run
    was filled from the same structure) or one skeleton per brief. Sharing
    collapses every index to the single skeleton; otherwise the index selects
    directly.

    Args:
        skeletons: The run's loaded skeleton documents, in report order.
        index: The book's ``brief_index``.
        run_dir: The run directory, folded into the error message so an
            out-of-range index names which run and row produced it.

    Returns:
        The skeleton document this book was filled from.

    Raises:
        ValueError: If ``index`` is out of range for a per-brief run (more
            than one skeleton declared) and there is no shared skeleton to
            fall back to. A bare ``IndexError`` here would name neither the
            run nor the offending index.
    """
    if len(skeletons) == 1:
        return skeletons[0]
    if not 0 <= index < len(skeletons):
        msg = (
            f"{run_dir}: brief_index {index} has no matching skeleton "
            f"({len(skeletons)} declared in report.json)"
        )
        raise ValueError(msg)
    return skeletons[index]


def _load_run(run_dir: Path, skeleton_dir: Path) -> list[BookScore]:
    """Score every book in one run directory.

    Args:
        run_dir: A directory holding ``report.json`` and ``books/``.
        skeleton_dir: Where the run's skeletons live.

    Returns:
        One score per book that has a document on disk.

    Raises:
        ValueError: If a book's ``brief_index`` does not match any skeleton
            the run declared (see :func:`_skeleton_for`); a malformed
            ``report.json`` produces this rather than a bare ``IndexError``.
    """
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    skeleton_names: list[str] = list(payload["skeletons"])
    skeletons = [
        json.loads((skeleton_dir / name).read_text(encoding="utf-8"))
        for name in skeleton_names
    ]
    scores: list[BookScore] = []
    for row in payload["books"]:
        if row.get("file") is None:
            continue
        doc = json.loads((run_dir / row["file"]).read_text(encoding="utf-8"))
        index = int(row["brief_index"])
        scores.append(
            evaluate_book(
                doc,
                _skeleton_for(skeletons, index, run_dir=run_dir),
                leg=row["vendor"],
                family=row["family"],
                brief_index=index,
            )
        )
    return scores


def _fmt(value: float | None, places: int = 2) -> str:
    """Format an optional number for the terminal table.

    Args:
        value: The number, or ``None``.
        places: Decimal places.

    Returns:
        The formatted value, or ``"-"``.
    """
    return "-" if value is None else f"{value:.{places}f}"


def _print_table(summaries: Iterable[LegSummary]) -> None:
    """Print the two-axis scorecard.

    Args:
        summaries: One summary per leg.
    """
    rows = sorted(summaries, key=lambda s: s.leg)
    width = max(len(s.leg) for s in rows)
    print("\nCOMPLIANCE  (deterministic; what the framework asked for)")
    header = (
        f"  {'leg':<{width}}  {'books':>5} {'done':>5} {'fill%':>6} {'leak':>5} "
        f"{'L1err':>6} {'FK':>5} {'inband':>7} {'FKsd':>5} {'words/req':>10} "
        f"{'onbudget':>9} {'beats':>6}"
    )
    print(header)
    for s in rows:
        m = s.means
        print(
            f"  {s.leg:<{width}}  {s.books:>5} {s.complete_books:>5} "
            f"{_fmt(m['fill_completeness']):>6} {_fmt(m['placeholder_leaks'], 1):>5} "
            f"{_fmt(m['l1_errors'], 1):>6} {_fmt(m['grade']):>5} "
            f"{_fmt(m['in_band']):>7} {_fmt(m['grade_spread']):>5} "
            f"{_fmt(m['word_ratio_median']):>10} {_fmt(m['word_on_budget']):>9} "
            f"{_fmt(m['beat_recall']):>6}"
        )
    print("\nPROSE CHARACTER  (descriptive; how the leg writes, not how well)")
    print(
        f"  {'leg':<{width}}  {'MATTR':>6} {'sent len':>9} {'sent sd':>8} "
        f"{'dialogue':>9} {'words':>7}"
    )
    for s in rows:
        m = s.means
        print(
            f"  {s.leg:<{width}}  {_fmt(m['mattr'], 3):>6} "
            f"{_fmt(m['mean_sentence_words'], 1):>9} "
            f"{_fmt(m['sentence_spread'], 1):>8} "
            f"{_fmt(m['dialogue_share'], 3):>9} {_fmt(m['total_words'], 0):>7}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Score every book in the given runs and write the scorecard.

    Args:
        argv: Command-line arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, action="append", type=Path, dest="runs")
    parser.add_argument("--skeletons", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    scores: list[BookScore] = []
    for run_dir in args.runs:
        scores.extend(_load_run(run_dir, args.skeletons))
    if not scores:
        print("Error: no books found in the given runs.", file=sys.stderr)
        return 1

    by_leg: dict[str, list[BookScore]] = {}
    for score in scores:
        by_leg.setdefault(score.leg, []).append(score)
    summaries = [summarize_leg(group) for group in by_leg.values()]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "evaluation.json").write_text(
        json.dumps(
            {
                "books": [dataclasses.asdict(s) for s in scores],
                "legs": [dataclasses.asdict(s) for s in summaries],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _print_table(summaries)
    print(f"\nWrote {args.out / 'evaluation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
