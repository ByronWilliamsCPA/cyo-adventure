# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""`RS-CAL1`: replay candidate advisory floors against stored production reports.

`RS-CAL2` swept candidate floors over the 2026-08-01 fixture corpus. That corpus
is 120 hand-written clean passages, and it answers "how noisy is this floor on
material we wrote to be clean". It does not answer "how much of a real
reviewer's load would this floor remove", because real books are not fixtures.
This script answers the second question against every stored production report.

Two properties of the stored data decide what can honestly be asked of it:

1. **The reports are truncated at the production floor.** A stored finding is
   one that already cleared 0.01, so the minimum score present is 0.0102 and
   nothing below the floor was ever persisted. Floors BELOW production are
   therefore unanswerable here, and this script refuses to report them rather
   than printing a number that looks like a measurement. That gap is exactly
   what `RS-CAL3`'s fresh capture exists to close.
2. **Reviewer load is occurrences and node hits, not findings.** A single
   merged finding spans up to 408 nodes. Counting findings understates load by
   more than an order of magnitude; counting occurrences is what the queue's
   ``flagged_count`` does. Both are reported, plus distinct node hits, which is
   what a reviewer actually walks through.

Scenarios cover the flat sweep, the ratified per-category split, higher
violence floors, and the shipped low-advisory collapse, so the floor levers and
the already-ruled UI lever are measured on one axis and can be compared.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from cyo_adventure.core.exceptions import ValidationError

DEFAULT_EXTRACT = Path(
    "docs/planning/safety/production-findings-extract-2026-08-31.json"
)
# The floor the stored reports were produced under. Scores below it were never
# persisted, so no scenario may claim to measure one.
PRODUCTION_FLOOR = 0.01
VIOLENCE_PREFIX = "violence"
BAND_ORDER = ("3-5", "5-8", "8-11", "10-13", "13-16", "16+")


@dataclass(frozen=True)
class Scenario:
    """One candidate surfacing rule.

    Attributes:
        name: Label for the report row.
        default: Floor applied to any category without an override.
        per_category: Per-category floor overrides.
        drop_low_advisory: Whether LOW-severity ADVISORY findings leave the
            default view, which is the shipped `RS-A` behaviour rather than a
            floor change.
    """

    name: str
    default: float = PRODUCTION_FLOOR
    per_category: dict[str, float] = field(default_factory=dict)
    drop_low_advisory: bool = False

    def floor_for(self, category: str) -> float:
        """Return the floor this scenario applies to one category."""
        for prefix, floor in self.per_category.items():
            if category == prefix or category.startswith(f"{prefix}/"):
                return floor
        return self.default

    def surfaces(self, finding: dict[str, object]) -> bool:
        """Whether this finding reaches the default review view."""
        if self.drop_low_advisory and _is_low_advisory(finding):
            return False
        score = finding.get("score")
        if not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            # An unscored finding is structural or verdict-only; no floor can
            # remove it, and treating a missing score as 0 would silently
            # delete safety signal the classifier could not grade.
            return True
        category = str(finding.get("category") or "")
        return float(score) >= self.floor_for(category)


def _is_low_advisory(finding: dict[str, object]) -> bool:
    """Mirror of ``api/review_surface.py::_is_low_advisory`` over raw JSON.

    Kept a mirror rather than an import because the stored reports are plain
    JSON, not ``FindingView`` instances, and hydrating them would pull the whole
    surface builder into an offline calibration script. The predicate is one
    conjunction and is pinned by
    ``tests/unit/test_replay_production_floors.py::test_low_advisory_predicate_matches_the_review_surface``.
    """
    # #CRITICAL: data integrity: this mirrors a SHIPPED production predicate,
    # and the replay's headline claim (the RS-A collapse removes ~97% of
    # reviewer load) is a claim about the shipped behaviour only while the
    # mirror agrees. If review_surface's predicate widens and this does not,
    # the report overstates what shipped and understates remaining load.
    # #VERIFY: tests/unit/test_replay_production_floors.py::test_low_advisory_predicate_matches_the_review_surface
    return finding.get("severity") == "low" and finding.get("verdict") == "advisory"


@dataclass
class BandTotals:
    """Per-band load under one scenario."""

    band: str
    books: int = 0
    nodes: int = 0
    findings: int = 0
    occurrences: int = 0
    node_hits: int = 0

    @property
    def node_hit_rate(self) -> float:
        """Share of this band's nodes carrying at least one surfaced finding."""
        return self.node_hits / self.nodes if self.nodes else 0.0

    @property
    def occurrences_per_node(self) -> float:
        """Surfaced finding-node pairs per node, the ``flagged_count`` axis."""
        return self.occurrences / self.nodes if self.nodes else 0.0


def load_extract(path: Path) -> dict[str, object]:
    """Read the anonymized production findings extract."""
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def evaluate(
    books: list[dict[str, object]], scenario: Scenario
) -> dict[str, BandTotals]:
    """Total surfaced load per age band under one scenario."""
    totals: dict[str, BandTotals] = {}
    for book in books:
        band = str(book.get("age_band") or "unknown")
        row = totals.setdefault(band, BandTotals(band=band))
        row.books += 1
        node_count = book.get("node_count")
        row.nodes += int(node_count) if isinstance(node_count, int) else 0
        hit_nodes: set[int] = set()
        findings = book.get("findings")
        for finding in findings if isinstance(findings, list) else []:
            if not isinstance(finding, dict) or not scenario.surfaces(finding):
                continue
            row.findings += 1
            node_ixs = finding.get("node_ixs")
            spans = node_ixs if isinstance(node_ixs, list) else []
            row.occurrences += len(spans)
            hit_nodes.update(int(i) for i in spans if isinstance(i, int))
        row.node_hits += len(hit_nodes)
    return totals


def scenarios(floors: tuple[float, ...]) -> list[Scenario]:
    """Build the scenario set: flat sweep, ratified split, violence, RS-A."""
    built = [Scenario(name=f"flat {floor:g}", default=floor) for floor in floors]
    built.append(
        Scenario(
            name="ratified (0.01, 0.10 violence*)",
            per_category={VIOLENCE_PREFIX: 0.10},
        )
    )
    built.append(
        Scenario(
            name="violence* 0.50",
            per_category={VIOLENCE_PREFIX: 0.50},
        )
    )
    built.append(Scenario(name="RS-A low-advisory collapse", drop_low_advisory=True))
    return built


def _row(name: str, band: str, t: BandTotals, baseline: BandTotals) -> str:
    """Render one markdown row with its change against the baseline."""
    delta = (
        "baseline"
        if baseline is t
        else f"{(t.occurrences - baseline.occurrences) / baseline.occurrences:+.1%}"
        if baseline.occurrences
        else "n/a"
    )
    return (
        f"| {name} | {band} | {t.books} | {t.nodes} | {t.findings} | "
        f"{t.occurrences} | {delta} | {t.node_hits} | {t.node_hit_rate:.3f} |"
    )


def render_markdown(
    results: list[tuple[Scenario, dict[str, BandTotals]]],
    *,
    baseline: dict[str, BandTotals],
) -> str:
    """Render the per-band, per-scenario table."""
    header = (
        "| Scenario | Band | Books | Nodes | Findings | Occurrences | "
        "vs baseline | Node hits | Node hit rate |"
    )
    rows = [
        _row(scenario.name, band, totals[band], baseline[band])
        for scenario, totals in results
        for band in BAND_ORDER
        if band in totals
    ]
    return "\n".join([header, "|" + "---|" * 9, *rows])


def main(argv: list[str] | None = None) -> int:
    """Replay candidate floors and print the per-band table.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        int: 0 on success, 1 for an unusable extract, 2 when a requested floor
            sits below the production floor.

    Raises:
        ValidationError: If any requested floor is not a finite number.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--floors", type=float, nargs="+", default=[0.02, 0.05, 0.10])
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = load_extract(args.extract)
    books = payload.get("books")
    if not isinstance(books, list):
        print(f"{args.extract}: no 'books' array")
        return 1

    # #CRITICAL: data integrity: reject a non-finite floor BEFORE the
    # below-production check, because that check cannot see one. argparse's
    # `type=float` accepts "nan", "inf" and "-inf", and every comparison with
    # nan is False, so `nan < PRODUCTION_FLOOR` is False and a nan floor sails
    # through. It then reaches `Scenario.surfaces`, where `score >= nan` is
    # False for every scored finding, so the scenario rejects the entire corpus
    # and the table reports a ~100% load reduction that is an artifact of
    # IEEE-754 comparison rules, not a measurement. `inf` fails the same way
    # for the same reason (it is simply above every score); `-inf` would be
    # caught below, but is rejected here so the refusal reads on the value
    # rather than on the floor.
    # #VERIFY: tests/unit/test_replay_production_floors.py::
    # test_a_non_finite_floor_is_rejected_rather_than_replayed.
    non_finite = [f for f in args.floors if not math.isfinite(f)]
    if non_finite:
        joined = ", ".join(repr(f) for f in non_finite)
        msg = (
            f"floor values must be finite numbers; got {joined}. A non-finite "
            f"floor compares False against every score, so the replay would "
            f"drop the whole corpus and report a load reduction that is a "
            f"comparison artifact rather than a measurement."
        )
        raise ValidationError(msg, field="floors", value=non_finite)

    below = [f for f in args.floors if f < PRODUCTION_FLOOR]
    if below:
        # Refusing is the point: the stored reports hold nothing below the
        # production floor, so a row for such a floor would be identical to the
        # baseline and would read as "lowering the floor changes nothing".
        joined = ", ".join(f"{f:g}" for f in below)
        print(
            f"Refusing to report floors below the production floor "
            f"({PRODUCTION_FLOOR:g}): {joined}. The stored reports were "
            f"truncated at that floor, so sub-floor findings were never "
            f"persisted and cannot be replayed. Use RS-CAL3's fresh capture."
        )
        return 2

    base_scenario = Scenario(name=f"production {PRODUCTION_FLOOR:g}")
    baseline = evaluate(books, base_scenario)
    results = [(base_scenario, baseline)]
    results.extend((s, evaluate(books, s)) for s in scenarios(tuple(args.floors)))

    print(f"Production floor replay from {args.extract}")
    counts = payload.get("counts")
    if isinstance(counts, dict):
        print(f"Extract: {json.dumps(counts, sort_keys=True)}")
    print()
    print(render_markdown(results, baseline=baseline))

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "extract": str(args.extract),
                    "production_floor": PRODUCTION_FLOOR,
                    "scenarios": [
                        {
                            "name": s.name,
                            "default": s.default,
                            "per_category": s.per_category,
                            "drop_low_advisory": s.drop_low_advisory,
                            "bands": {
                                b: {
                                    "books": t.books,
                                    "nodes": t.nodes,
                                    "findings": t.findings,
                                    "occurrences": t.occurrences,
                                    "node_hits": t.node_hits,
                                    "node_hit_rate": round(t.node_hit_rate, 4),
                                }
                                for b, t in sorted(totals.items())
                            },
                        }
                        for s, totals in results
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
