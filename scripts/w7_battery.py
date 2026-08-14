"""Score the judge panel against known-bad books, per criterion (W7).

The panel is an instrument nobody has validated. Every ranking-shaped claim in
Part IV rests on it, W11's pilot scoring needs it, and best-of-N would select on
it. This is the battery that says which of its criteria are worth trusting.

**The unit is the criterion, not the panel.** W7's rule retires a criterion that
fails to detect its own seeded defect, or that fires on the clean control. A
panel-level pass or fail would average a working criterion together with a blind
one and hide both.

**The comparison is within-book.** Each defect arm is scored against the *same
book's* control, not against the corpus mean. A judge's opinion of a book is
mostly an opinion of the book; pairing removes that and leaves the defect.
It also removes any constant offset from the panel's criteria being written for
one age band while the corpus spans three, which is the stated limit of this run
rather than a confound in it.

**Agreement is scored against our own floor.** Kappa 0.60, cited to Landis and
Koch (1977), not the 0.80 a review proposed: 0.80 sits in the "almost perfect"
band that human raters routinely miss, so adopting it would retire criteria for
being ordinarily noisy.

Usage::

    uv run python scripts/seed_defects.py <books> --out out/w7/arms
    uv run python scripts/w7_battery.py --arms out/w7/arms --prepare <books>
    uv run python scripts/w7_battery.py --arms out/w7/arms --out out/w7 --env-file .env
    uv run python scripts/w7_battery.py --replay out/w7/verdicts.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.core.config import Settings  # noqa: E402
from cyo_adventure.generation.metered import MeteredProvider  # noqa: E402
from cyo_adventure.generation.provider import build_openrouter_leg  # noqa: E402
from cyo_adventure.generation.usage import UsageLedger  # noqa: E402
from cyo_adventure.validator.reading_level import measure_book  # noqa: E402
from scripts.judge_books import _CRITERIA, _PANEL, Verdict, judge_book  # noqa: E402
from scripts.seed_defects import verify  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

# Which criterion each seeded defect is supposed to be detected by. This mapping
# IS the hypothesis under test: a criterion that does not move on its own defect
# has failed its half of the rule, whatever it does elsewhere.
DEFECT_CRITERION: Final[dict[str, str]] = {
    "dialogue_flat": "dialogue",
    "dialogue_added": "dialogue",
    "tense_break": "voice",
    "false_choice": "choice_quality",
    "reading_level_up": "age_fit",
    "premise_duplicate": "engagement",
}

# A criterion must move at least this far, on the 1-to-5 scale, against its own
# book's control before the movement counts as detection. Set below one scale
# point deliberately: a judge that reliably drops a book by half a point on a
# real defect is discriminating, and demanding a whole point would retire
# criteria for being calibrated rather than for being blind.
_DETECTION_MARGIN: Final[float] = 0.5

# The control must not move by more than this, or the criterion is firing on a
# book with nothing wrong with it.
_FALSE_POSITIVE_MARGIN: Final[float] = _DETECTION_MARGIN

_KAPPA_FLOOR: Final[float] = 0.60

# How many US reading grades the `reading_level_up` seed aims to add. Three is
# roughly a band's width in this catalogue, so the result is a book that is
# genuinely wrong for its declared band rather than one that merely reads a
# little older.
_HARDEN_GRADES: Final[float] = 3.0

# Nodes shorter than this are left alone: rewriting a ten-word body is a
# replacement, not a reworking, and the seed would then be measuring
# substitution rather than difficulty.
_MIN_HARDENABLE_WORDS: Final[int] = 15

_HARDEN_CONCURRENCY: Final[int] = 6

# The model that writes the harder prose. Sonnet 5 rather than the cheaper
# default: this seed has to produce a book that is genuinely too old for its
# band while still reading like a book, and a weak rewrite yields an arm that
# fails to land, which costs an opportunity rather than saving money. It is a
# fixture model and has nothing to do with which model the pipeline generates
# with.
_HARDEN_MODEL: Final[str] = "anthropic/claude-sonnet-5"

__all__ = ["CriterionVerdict", "score_battery"]


@dataclass(frozen=True, slots=True)
class CriterionVerdict:
    """What the battery concluded about one criterion.

    Attributes:
        criterion: The criterion's name.
        defect: The seeded defect it was supposed to detect, or empty when no
            defect targets it and it was only checked for false positives.
        detections: Books where the criterion dropped by the margin on its own
            defect arm, against that same book's control.
        opportunities: Books where it could have.
        false_positives: Control books where some OTHER book's defect moved this
            criterion, which is the "fires on the clean control" half of the rule.
        deltas: Per-book movement on the defect arm, for the record.
        verdict: RETIRE, KEEP, or UNTESTED, with the reason.
    """

    criterion: str
    defect: str
    detections: int
    opportunities: int
    false_positives: int
    deltas: list[float]
    verdict: str

    @property
    def detection_rate(self) -> float | None:
        """Share of opportunities on which the criterion noticed its defect.

        Returns:
            The rate, or ``None`` when it was never given an opportunity.
        """
        if not self.opportunities:
            return None
        return self.detections / self.opportunities


def _mean_by_criterion(verdicts: Sequence[Verdict], book: str) -> dict[str, float]:
    """Average each criterion's score across the panel for one book.

    Args:
        verdicts: Every verdict.
        book: The book identifier.

    Returns:
        Criterion name to its panel-mean score. Missing criteria are absent
        rather than zero: a judge that failed to score one is not a judge that
        scored it badly.
    """
    rows = [v for v in verdicts if v.book == book and v.scores and v.error is None]
    out: dict[str, float] = {}
    for name in _CRITERIA:
        values = [v.scores[name] for v in rows if name in v.scores]
        if values:
            out[name] = statistics.fmean(values)
    return out


def score_battery(
    verdicts: Sequence[Verdict], arms: Sequence[tuple[str, str]]
) -> list[CriterionVerdict]:
    """Apply W7's per-criterion rule to a finished set of verdicts.

    Args:
        verdicts: Every verdict from the blind panel run.
        arms: ``(book_stem, defect)`` pairs describing what each book is.

    Returns:
        One verdict per criterion, in the order the criteria are declared.
    """
    by_book = {f"{stem}__{defect}": (stem, defect) for stem, defect in arms}
    controls = {
        stem: _mean_by_criterion(verdicts, f"{stem}__control")
        for stem, defect in arms
        if defect == "control"
    }

    out: list[CriterionVerdict] = []
    for criterion in _CRITERIA:
        defect = next((d for d, c in DEFECT_CRITERION.items() if c == criterion), "")
        deltas: list[float] = []
        detections = 0
        opportunities = 0
        false_positives = 0

        for book, (stem, arm) in by_book.items():
            control = controls.get(stem)
            if control is None or criterion not in control:
                continue
            scored = _mean_by_criterion(verdicts, book)
            if criterion not in scored:
                continue
            delta = scored[criterion] - control[criterion]
            if arm == defect and defect:
                opportunities += 1
                deltas.append(delta)
                # Detection is a DROP: a seeded defect should lower the score of
                # the criterion that observes it.
                if delta <= -_DETECTION_MARGIN:
                    detections += 1
            elif arm not in {"control", defect} and abs(delta) > _FALSE_POSITIVE_MARGIN:
                # This book carries a defect some OTHER criterion owns, so this
                # criterion moving is the instrument responding to something it
                # does not claim to measure.
                false_positives += 1

        out.append(
            CriterionVerdict(
                criterion=criterion,
                defect=defect,
                detections=detections,
                opportunities=opportunities,
                false_positives=false_positives,
                deltas=deltas,
                verdict=_verdict_for(criterion, defect, detections, opportunities),
            )
        )
    return out


def _verdict_for(
    criterion: str, defect: str, detections: int, opportunities: int
) -> str:
    """State the rule's conclusion for one criterion.

    Args:
        criterion: The criterion's name.
        defect: The defect targeting it, or empty.
        detections: How many times it noticed.
        opportunities: How many times it could have.

    Returns:
        The verdict line.
    """
    if not defect or not opportunities:
        return (
            f"UNTESTED: no seeded defect exercised {criterion}, so this run says "
            "nothing about it either way"
        )
    rate = detections / opportunities
    if rate <= 0.5:
        return (
            f"RETIRE: detected its own seeded {defect} on {detections} of "
            f"{opportunities} books. A criterion that misses the defect it "
            "exists to catch cannot support a ranking"
        )
    return (
        f"KEEP: detected its own seeded {defect} on {detections} of "
        f"{opportunities} books"
    )


def cohens_kappa(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Return Cohen's kappa between two judges' scores over the same books.

    Scores are binned to the integer scale before agreement is computed, since
    kappa is a categorical statistic and treating 3.0 and 3.4 as different
    categories would report disagreement that no rubric asked for.

    Args:
        a: One judge's scores.
        b: Another judge's scores over the same books, in the same order.

    Returns:
        Kappa, or ``None`` when the pair is too small or degenerate.
    """
    if len(a) != len(b) or len(a) < 2:
        return None
    left = [round(x) for x in a]
    right = [round(x) for x in b]
    labels = sorted(set(left) | set(right))
    if len(labels) < 2:
        # Both judges used one category throughout. Kappa is undefined here and
        # reporting 0.0 would read as total disagreement when the two agreed on
        # every book.
        return None
    observed = sum(1 for x, y in zip(left, right, strict=True) if x == y) / len(left)
    expected = sum(
        (left.count(label) / len(left)) * (right.count(label) / len(right))
        for label in labels
    )
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


_HARDEN_SYSTEM: Final[str] = (
    "You rewrite children's story prose to be HARDER to read, on purpose, for a "
    "measurement fixture. Keep every event, character, name and plot beat exactly "
    "as they are. Change only the language: longer sentences, subordinate clauses, "
    "abstract and polysyllabic vocabulary in place of concrete simple words. Do "
    "not add or remove events. Do not change who does what. Return only the "
    "rewritten prose for the passage given, with no commentary."
)


async def harden_book(
    doc: dict[str, Any], provider: object, *, grades: float
) -> dict[str, Any]:
    """Rewrite a book's prose to raise its reading grade, via generation.

    The other four seeds are mechanical, and this one deliberately is not. A
    formula can raise Flesch-Kincaid by padding syllables, but the result stops
    reading like a book, and a judge scoring "would a child want to read on"
    would then be reacting to word salad rather than to a harder text. The point
    of the fixture is a book that is genuinely too old for its band while still
    being a book.

    Args:
        doc: The passing book.
        provider: A ``GenerationProvider``; each node is rewritten in one call.
        grades: How many grades harder to aim for.

    Returns:
        A copy with rewritten bodies. A node whose rewrite fails keeps its
        original prose rather than being dropped, so a partial failure lowers
        the seed's strength rather than corrupting the book; `verify` then
        reports the grade rise that actually landed.
    """
    out = copy.deepcopy(doc)
    nodes = out.get("nodes")
    if not isinstance(nodes, list):
        return out

    # Bounded concurrency rather than a sequential loop. A six-book corpus is
    # 213 hardenable nodes and one call each; serialised at a few seconds per
    # call that is most of an hour of wall clock, which is long enough that an
    # operator starts wondering whether to kill it. The bound is low because the
    # cap is the provider's rate limit, not ours.
    semaphore = asyncio.Semaphore(_HARDEN_CONCURRENCY)

    async def rewrite(node: dict[str, Any]) -> None:
        body = str(node.get("body", ""))
        if len(body.split()) < _MIN_HARDENABLE_WORDS:
            # Too short to harden meaningfully, and a rewrite would be a
            # replacement rather than a reworking.
            return
        async with semaphore:
            try:
                completion = await provider.complete(  # pyright: ignore[reportAttributeAccessIssue]
                    system=_HARDEN_SYSTEM,
                    prompt=(
                        f"Rewrite this passage about {grades:.0f} US reading "
                        f"grades harder, preserving every event exactly:"
                        f"\n\n{body}"
                    ),
                    max_tokens=1500,
                )
            except Exception as exc:  # one node failing must not void the book
                print(f"    harden failed on {node.get('id')}: {exc}", file=sys.stderr)
                return
        text = completion.text.strip()
        if text:
            node["body"] = text

    await asyncio.gather(*(rewrite(node) for node in nodes if isinstance(node, dict)))
    return out


def _book_grade(doc: dict[str, Any]) -> float | None:
    """Return the whole-book Flesch-Kincaid grade of *doc*.

    Args:
        doc: A story document.

    Returns:
        The grade, or ``None`` when the book declares no reading level or is
        too short to measure.
    """
    metadata = doc.get("metadata")
    level = metadata.get("reading_level") if isinstance(metadata, dict) else None
    if not isinstance(level, dict):
        return None
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        return None
    measured = measure_book(
        (
            str(node.get("body", ""))
            for node in nodes
            if isinstance(node, dict) and str(node.get("body", "")).strip()
        ),
        target=float(level.get("target", 3.0)),
        tolerance=float(level.get("tolerance", 1.0)),
    )
    return None if measured is None else measured.grade


def _spread_order(count: int) -> list[int]:
    """Return indices ordered to spread evenly over ``range(count)``.

    A low-discrepancy (golden-ratio) sequence rather than ``range``: swapping
    nodes in index order would put every hardened passage at the front of the
    book, which is a different defect (a book that starts hard and softens)
    from the one being seeded.

    Args:
        count: How many indices.

    Returns:
        A permutation of ``range(count)``.
    """
    return sorted(range(count), key=lambda i: (i * 0.6180339887498949) % 1.0)


def blend_to_grade(
    original: dict[str, Any], hardened: dict[str, Any], *, grades: float
) -> tuple[dict[str, Any], str]:
    """Compose an arm that is *grades* harder, from a rewrite that overshot.

    The generation seed does not take direction on magnitude. Asked for three
    US grades harder it delivered between 8.2 and 11.1 across the six-book
    corpus, moving books whose bands target grades 1.0 to 4.5 up to grades 8.1
    to 13.3. That is not a book too old for its band; it is a different genre,
    and it breaks the fixture two ways. It makes `age_fit`'s detection trivial,
    so the arm stops measuring the criterion's sensitivity to a realistic miss.
    And it moves voice, engagement and dialogue genuinely, which this battery's
    false-positive rule counts against those criteria for noticing something
    that really did change.

    Rather than re-prompting for a magnitude the model cannot hit reliably, the
    arm is composed: hardened bodies are swapped in one at a time, spread across
    the book, until the whole-book grade reaches the target. That is
    deterministic, exact, free (the generation is already paid for), and it
    seeds a more realistic defect than a uniform rewrite does, since a book
    whose passages drift too hard in places is what the pipeline actually
    produces when it fails this way.

    Args:
        original: The passing book.
        hardened: The same book with every eligible body rewritten harder.
        grades: How many US grades above the original to aim for.

    Returns:
        The blended arm, and a one-line note of what was achieved, because a
        seed whose strength is not reported cannot be read back against the
        detection rate computed over it.
    """
    base = _book_grade(original)
    if base is None:
        return copy.deepcopy(hardened), "unmeasurable grade; full rewrite used"

    out = copy.deepcopy(original)
    out_nodes = out.get("nodes")
    hard_nodes = hardened.get("nodes")
    if not isinstance(out_nodes, list) or not isinstance(hard_nodes, list):
        return out, "no nodes to blend"

    swappable = [
        i
        for i, (a, b) in enumerate(zip(out_nodes, hard_nodes, strict=False))
        if isinstance(a, dict)
        and isinstance(b, dict)
        and a.get("body") != b.get("body")
    ]
    swapped = 0
    for index in _spread_order(len(swappable)):
        node_index = swappable[index]
        out_nodes[node_index]["body"] = hard_nodes[node_index]["body"]
        swapped += 1
        current = _book_grade(out)
        if current is not None and current - base >= grades:
            break

    achieved = _book_grade(out)
    delta = "unmeasurable" if achieved is None else f"{achieved - base:+.2f}"
    return out, (
        f"{swapped} of {len(swappable)} rewritable nodes swapped, "
        f"grade {base:.2f} -> {achieved if achieved is None else round(achieved, 2)} "
        f"({delta} against a {grades:+.1f} target)"
    )


async def prepare_arms(
    corpus: Sequence[Path],
    arms_dir: Path,
    harden_dir: Path,
    settings: Settings | None,
) -> tuple[int, float | None]:
    """Write each book's control and its generation-seeded reading-level arm.

    The other arms are mechanical and `seed_defects.py` writes them, control
    included; the control is rewritten here only so this step is usable on its
    own. The reading-level arm is here because it needs a provider, and because
    it was otherwise absent: `harden_book` existed with no caller at all, so a
    run would have scored `age_fit` with no arm to score it on and reported the
    criterion untested without saying why.

    The full rewrite is kept under ``harden_dir`` and the arm is *blended* from
    it, for the reason given in `blend_to_grade`. Keeping the rewrite means a
    change of target costs nothing: the generation is the expensive half and it
    is done once.

    Args:
        corpus: The passing books to build arms from.
        arms_dir: Directory the mechanical seeds were written to.
        harden_dir: Directory holding, or to receive, the full rewrites.
        settings: Settings supplying the credential, or ``None`` to blend from
            rewrites already on disk without calling any provider.

    Returns:
        The number of arms written, and the dollars spent, which is ``None``
        when no call was made and may also be ``None`` when the models used are
        unpriced (`UW-C239`).
    """
    ledger = UsageLedger()
    provider = (
        MeteredProvider(build_openrouter_leg(settings, _HARDEN_MODEL), ledger=ledger)
        if settings is not None
        else None
    )
    written = 0
    for path in corpus:
        doc = json.loads(path.read_text(encoding="utf-8"))
        stem = path.stem.replace(".filled", "")

        (arms_dir / f"{stem}__control.json").write_text(
            json.dumps(doc, indent=2) + "\n", encoding="utf-8"
        )
        written += 1

        rewrite_path = harden_dir / f"{stem}.json"
        if provider is not None:
            hardened = await harden_book(doc, provider, grades=_HARDEN_GRADES)
            rewrite_path.write_text(
                json.dumps(hardened, indent=2) + "\n", encoding="utf-8"
            )
        elif rewrite_path.exists():
            hardened = json.loads(rewrite_path.read_text(encoding="utf-8"))
        else:
            print(f"  SKIP {stem}: no rewrite at {rewrite_path}", file=sys.stderr)
            continue

        arm, note = blend_to_grade(doc, hardened, grades=_HARDEN_GRADES)
        result = verify("reading_level_up", doc, arm)
        if not result.landed:
            print(
                f"  SKIP {stem}__reading_level_up  {result.evidence}; {note}",
                file=sys.stderr,
            )
            (arms_dir / f"{stem}__reading_level_up.json").unlink(missing_ok=True)
            continue
        print(
            f"  ok   {stem}__reading_level_up  {result.evidence}; {note}",
            file=sys.stderr,
        )
        (arms_dir / f"{stem}__reading_level_up.json").write_text(
            json.dumps(arm, indent=2) + "\n", encoding="utf-8"
        )
        written += 1

    return written, (_spend(ledger) if provider is not None else None)


async def run_panel(
    books: Sequence[tuple[str, dict[str, Any]]], settings: Settings
) -> tuple[list[Verdict], float]:
    """Score every book with every judge, blind, and meter the spend.

    Args:
        books: ``(identifier, document)`` pairs.
        settings: Settings supplying the credential.

    Returns:
        Every verdict, and the measured spend in USD.

    Note:
        The judge never learns which arm it is reading. The identifier is used
        only to join the results afterwards; the prompt carries the story text
        and nothing else, which is what makes a within-book comparison a
        comparison rather than a suggestion.
    """
    verdicts: list[Verdict] = []
    ledger = UsageLedger()
    for judge in _PANEL:
        provider = MeteredProvider(
            build_openrouter_leg(
                settings, model=judge.model, provider_order=judge.provider_order
            ),
            ledger=ledger,
        )
        for identifier, doc in books:
            verdict = await judge_book(
                provider, judge, doc, leg=identifier, family="w7", brief_index=0
            )
            detail = verdict.error or (
                f"{statistics.fmean(verdict.scores.values()):.2f}"
                if verdict.scores
                else "no scores"
            )
            print(f"  {judge.label} -> {identifier}: {detail}", file=sys.stderr)
            verdicts.append(verdict)
    return verdicts, _spend(ledger)


def _spend(ledger: UsageLedger) -> float:
    """Return measured spend for the run, priced per judge model.

    Args:
        ledger: The run's ledger.

    Returns:
        USD spent, as a lower bound when any model is unpriced.
    """
    from cyo_adventure.core.pricing import estimate_cost, price_for  # noqa: PLC0415

    total = 0.0
    for call in ledger.calls:
        estimate = estimate_cost(
            price_for(call.provider, call.model), call.input_tokens, call.output_tokens
        )
        total += float(estimate.amount_usd)
    return total


def _print_report(
    results: Sequence[CriterionVerdict], verdicts: Sequence[Verdict], spend: float
) -> None:
    """Print the per-criterion table, the agreement figures, and the spend.

    Args:
        results: Output of :func:`score_battery`.
        verdicts: Every verdict, for the agreement pass.
        spend: Measured USD.
    """
    print("\nW7 KNOWN-BAD BATTERY  (per criterion; within-book against control)")
    width = max(len(r.criterion) for r in results)
    print(
        f"  {'criterion':<{width}}  {'defect':<18} {'detect':>7} {'FP':>4} "
        f"{'median delta':>13}"
    )
    for row in results:
        rate = f"{row.detections}/{row.opportunities}" if row.opportunities else "-"
        delta = f"{statistics.median(row.deltas):+.2f}" if row.deltas else "-"
        print(
            f"  {row.criterion:<{width}}  {row.defect or '-':<18} {rate:>7} "
            f"{row.false_positives:>4} {delta:>13}"
        )
    print("\n  Verdicts:")
    for row in results:
        print(f"    {row.criterion}: {row.verdict}")

    print(f"\n  Agreement floor: kappa {_KAPPA_FLOOR} (Landis and Koch 1977).")
    books = sorted({v.book for v in verdicts})
    for i, left in enumerate(_PANEL):
        for right in _PANEL[i + 1 :]:
            pairs = [
                (
                    _one(verdicts, left.label, b),
                    _one(verdicts, right.label, b),
                )
                for b in books
            ]
            usable = [(x, y) for x, y in pairs if x is not None and y is not None]
            kappa = cohens_kappa([x for x, _ in usable], [y for _, y in usable])
            text = "undefined" if kappa is None else f"{kappa:+.2f}"
            flag = "" if kappa is None or kappa >= _KAPPA_FLOOR else "  <-- below floor"
            print(f"    {left.label} vs {right.label}: {text} (n={len(usable)}){flag}")

    print(f"\n  Measured spend: ${spend:.4f}")


def _one(verdicts: Sequence[Verdict], judge: str, book: str) -> float | None:
    """Return one judge's overall score for one book.

    Args:
        verdicts: Every verdict.
        judge: The judge label.
        book: The book identifier.

    Returns:
        The mean across criteria, or ``None`` when that scoring failed.
    """
    for v in verdicts:
        if v.judge == judge and v.book == book and v.scores and v.error is None:
            return statistics.fmean(v.scores.values())
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run or replay the battery.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--replay", type=Path)
    parser.add_argument(
        "--harden-dir",
        type=Path,
        default=Path("out/w7/harden"),
        help=(
            "Where the full generation rewrites live. The arm is blended from "
            "them to a controlled grade delta, so re-targeting costs nothing."
        ),
    )
    parser.add_argument(
        "--reblend",
        action="store_true",
        help=(
            "Rebuild the reading_level_up arms from the rewrites already in "
            "--harden-dir, calling no provider."
        ),
    )
    parser.add_argument(
        "--prepare",
        nargs="+",
        type=Path,
        metavar="BOOK",
        help=(
            "Write each book's control and its generation-seeded "
            "reading_level_up arm into --arms, then exit without judging. "
            "Separate from the run so the paid harden is not repeated when a "
            "judging pass is retried."
        ),
    )
    args = parser.parse_args(argv)

    if args.replay is not None:
        payload = json.loads(args.replay.read_text(encoding="utf-8"))
        verdicts = [Verdict(**row) for row in payload["verdicts"]]
        arms = [tuple(pair) for pair in payload["arms"]]
        _print_report(
            score_battery(verdicts, arms),  # pyright: ignore[reportArgumentType]
            verdicts,
            float(payload.get("spend_usd", 0.0)),
        )
        return 0

    if args.env_file.exists():
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = (
                    line.split("=", 1)[1].strip().strip("'\"")
                )

    if args.prepare is not None:
        if args.arms is None:
            print("Error: --prepare needs --arms.", file=sys.stderr)
            return 2
        args.arms.mkdir(parents=True, exist_ok=True)
        args.harden_dir.mkdir(parents=True, exist_ok=True)
        written, spent = asyncio.run(
            prepare_arms(
                args.prepare,
                args.arms,
                args.harden_dir,
                None if args.reblend else Settings(),
            )
        )
        # Never print "$0.0000" for an unpriced run. `core/pricing.py` leaves
        # input rates unset for every cloud model (UW-C239), so a zero here
        # means the call was not priced, not that it was free, and printing it
        # as a dollar figure would put a false number in the run's record.
        if args.reblend:
            cost = "no provider call"
        elif not spent:
            cost = f"spend unpriced ({_HARDEN_MODEL} has no rate; UW-C239)"
        else:
            cost = f"${spent:.4f} spent hardening"
        print(f"\n{written} arm(s) written; {cost}.")
        return 0

    if args.arms is None or args.out is None:
        print("Error: --arms and --out are required without --replay.", file=sys.stderr)
        return 2

    files = sorted(args.arms.glob("*.json"))
    books = [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in files]
    arms = [tuple(p.stem.rsplit("__", 1)) for p in files]
    print(
        f"Judging {len(books)} books with {len(_PANEL)} judges "
        f"({len(books) * len(_PANEL)} scorings).",
        file=sys.stderr,
    )

    verdicts, spend = asyncio.run(run_panel(books, Settings()))
    results = score_battery(verdicts, arms)  # pyright: ignore[reportArgumentType]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "verdicts.json").write_text(
        json.dumps(
            {
                "arms": [list(a) for a in arms],
                "spend_usd": spend,
                "verdicts": [
                    {
                        "book": v.book,
                        "leg": v.leg,
                        "family": v.family,
                        "judge": v.judge,
                        "self_family": v.self_family,
                        "scores": v.scores,
                        "notes": v.notes,
                        "error": v.error,
                    }
                    for v in verdicts
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _print_report(results, verdicts, spend)
    print(f"\nWrote {args.out / 'verdicts.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
