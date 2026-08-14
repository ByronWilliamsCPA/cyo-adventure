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
from scripts.judge_books import _CRITERIA, _PANEL, Verdict, judge_book  # noqa: E402

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
    for node in nodes:
        body = str(node.get("body", ""))
        if len(body.split()) < 15:
            # Too short to harden meaningfully, and a rewrite would be a
            # replacement rather than a reworking.
            continue
        try:
            completion = await provider.complete(  # pyright: ignore[reportAttributeAccessIssue]
                system=_HARDEN_SYSTEM,
                prompt=(
                    f"Rewrite this passage about {grades:.0f} US reading grades "
                    f"harder, preserving every event exactly:\n\n{body}"
                ),
                max_tokens=1500,
            )
        except Exception as exc:  # one node failing must not void the book
            print(f"    harden failed on {node.get('id')}: {exc}", file=sys.stderr)
            continue
        text = completion.text.strip()
        if text:
            node["body"] = text
    return out


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

    if args.arms is None or args.out is None:
        print("Error: --arms and --out are required without --replay.", file=sys.stderr)
        return 2

    if args.env_file.exists():
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = (
                    line.split("=", 1)[1].strip().strip("'\"")
                )

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
