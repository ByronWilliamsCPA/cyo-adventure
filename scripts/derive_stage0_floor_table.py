# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""`RS-CAL2`: re-derive the Stage-0 advisory-floor table from the stored baseline.

`UW-C378` reported that of the candidate advisory floors {0.01, 0.02, 0.05, 0.10}
only 0.10 clears the clean-noise target of <= 0.2 advisories per node, and that
0.10 loses 10 of the 14 adversarial pairs. Those numbers were derived by hand,
which means the ratified decision that followed (per-category floors: low on
`self-harm*`/`sexual*`/`harassment/threatening`/`illicit`, higher on
`violence*`) rests on a measurement nothing can re-run. This script is the
oracle: it recomputes the whole table from
`docs/planning/safety/stage0-baseline-2026-08-01.json` so a future floor change
is measured rather than remembered.

Two properties make the output trustworthy:

1. **The decision predicate is differentially tested against production.**
   `surfaced_verdict()` below reimplements `moderation/classifiers.py`'s
   `_openai_finding` because that function reads a module-level floor constant
   and this script must sweep the floor. The reimplementation is not trusted on
   inspection: `tests/unit/test_derive_stage0_floor_table.py` asserts it agrees
   with the real `_openai_finding` on every category of every record in the
   baseline at the production floor. A drift in either implementation fails that
   test.
2. **Perspective is excluded, deliberately.** The baseline carries Perspective
   scores because it was captured to freeze them before Google's 2026-12-31
   sunset, but Perspective was retired as a Stage-0 signal source: nothing in
   `moderation/classifiers.py` produces a `Source.PERSPECTIVE` finding any more.
   Counting its contribution would overstate recall for every candidate floor,
   which is the direction that gets a book published.

Usage::

    uv run python scripts/derive_stage0_floor_table.py
    uv run python scripts/derive_stage0_floor_table.py --json out/floors.json
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.moderation.classifiers import (
    _ADVISORY_SCORE_FLOOR,  # pyright: ignore[reportPrivateUsage]
    _OPENAI_BRIGHTLINE,  # pyright: ignore[reportPrivateUsage]
)

DEFAULT_BASELINE: Final = Path("docs/planning/safety/stage0-baseline-2026-08-01.json")

# The candidates UW-C378 measured, kept verbatim so this script's table is
# comparable with the hand-derived one it replaces.
DEFAULT_FLOORS: Final[tuple[float, ...]] = (0.01, 0.02, 0.05, 0.10)

# UW-C378's clean-noise target. A floor that exceeds this buries real findings
# under classifier noise on ordinary prose.
CLEAN_NOISE_TARGET: Final = 0.2

# The ratified per-category split (UW-C378, 2026-08-25): a low floor on the
# categories where a miss is a child-safety miss, a higher one on the two
# violence categories that produce most of the clean-prose noise. 0.10 is the
# register's indicative value for the high side, not a calibrated one; RS-CAL4
# is what sets the final numbers against a fresh capture.
RATIFIED_LOW_FLOOR: Final = 0.01
RATIFIED_HIGH_FLOOR: Final = 0.10
RATIFIED_HIGH_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"violence", "violence/graphic"}
)

# Stage 0 can only ever reach these two verdicts, so the recall question is
# "did anything surface", plus "did it reach the corpus's expected minimum".
_VERDICT_RANK: Final[dict[str, int]] = {"pass": 0, "advisory": 1, "flag": 2, "block": 3}


@dataclass(frozen=True)
class FloorScenario:
    """One candidate floor configuration to evaluate.

    Attributes:
        name: Label for the output table.
        default: Floor applied to any category not named in ``per_category``.
        per_category: Category-specific overrides.
    """

    name: str
    default: float
    per_category: dict[str, float] = field(default_factory=dict[str, float])

    def floor_for(self, category: str) -> float:
        """Return the floor this scenario applies to *category*."""
        return self.per_category.get(category, self.default)


@dataclass
class ScenarioResult:
    """Measured outcome of one scenario over one baseline.

    Three populations are kept apart on purpose, because `UW-C378`'s
    hand-derived "loses 10 of the 14 adversarial pairs" merged them and
    understated the loss rate as a result: its numerator counted only records
    the classifier actually screened while its denominator counted the whole
    adversarial population, including one record (`F1-pii-positive-control`)
    that was never sent for scoring at all.

    Attributes:
        scenario: The evaluated scenario.
        clean_records: Clean-population records measured.
        clean_advisories: Total advisory findings raised on clean records.
        clean_records_hit: Clean records raising at least one finding.
        recall_records: Records in the recall population: an adversarial record
            that carries an expected minimum verdict AND was actually screened.
        recall_detected: Recall-population records raising at least one finding.
        recall_met_expected: Recall-population records reaching their expected
            minimum verdict from Stage 0 alone.
        lost: Passage ids raising nothing, paired with their ``known_gap`` flag.
        control_surfaced: Findings raised on the negative control, which is an
            on-band clean passage and should raise none.
        per_band_clean: Advisories per node keyed by age band. Clean records in
            this baseline carry no band, so this stays empty until a capture
            supplies one (plan section 5.6).
    """

    scenario: FloorScenario
    clean_records: int = 0
    clean_advisories: int = 0
    clean_records_hit: int = 0
    recall_records: int = 0
    recall_detected: int = 0
    recall_met_expected: int = 0
    lost: list[tuple[str, bool]] = field(default_factory=list[tuple[str, bool]])
    control_surfaced: int = 0
    per_band_clean: dict[str, float] = field(default_factory=dict[str, float])

    @property
    def advisories_per_node(self) -> float:
        """Clean advisories per clean node, the noise figure the target names."""
        if self.clean_records == 0:
            return 0.0
        return self.clean_advisories / self.clean_records

    @property
    def clears_noise_target(self) -> bool:
        """Whether this scenario meets `UW-C378`'s <= 0.2 advisories/node target."""
        return self.advisories_per_node <= CLEAN_NOISE_TARGET

    @property
    def lost_ids(self) -> list[str]:
        """Passage ids of every record raising nothing."""
        return [passage_id for passage_id, _ in self.lost]

    @property
    def lost_known_gap(self) -> int:
        """Losses the corpus already documents as a structural gap.

        The six aggregate-harm records (`known_gap`) describe harm that emerges
        across nodes; per-node classification cannot see it at ANY floor, so
        counting them as a floor's recall cost attributes to the floor a loss it
        did not cause.
        """
        return sum(1 for _, known in self.lost if known)


def surfaced_verdict(
    *, category: str, flagged: bool, score: float | None, floor: float
) -> str | None:
    """Return the verdict Stage 0 would record, or None for nothing recorded.

    A faithful reimplementation of ``moderation/classifiers.py::_openai_finding``
    with the floor made a parameter. Kept in step with production by the
    differential test named in this module's docstring, not by inspection.

    Args:
        category: OpenAI moderation category slug.
        flagged: OpenAI's own boolean flag for that category.
        score: The graded score, or None when the payload carried none.
        floor: The advisory floor to apply to this category.

    Returns:
        ``"block"``, ``"advisory"``, or None.
    """
    # #CRITICAL: data integrity: this predicate is a COPY of the production
    # decision in moderation/classifiers.py::_openai_finding, so a floor
    # recommendation derived here is only as trustworthy as the copy. If
    # production changes and this does not, the table describes a gate that
    # does not exist and a floor gets ratified against fiction.
    # #VERIFY: tests/unit/test_derive_stage0_floor_table.py::test_predicate_matches_the_live_classifier_on_every_baseline_record
    over_floor = score is not None and math.isfinite(score) and score >= floor
    if flagged and category in _OPENAI_BRIGHTLINE:
        return "block"
    if flagged or over_floor:
        return "advisory"
    return None


def record_verdicts(
    record: dict[str, object], scenario: FloorScenario
) -> dict[str, str]:
    """Return the surfaced verdict per category for one baseline record."""
    scores_raw = record.get("openai_scores")
    flags_raw = record.get("openai_flags")
    scores: dict[str, object] = scores_raw if isinstance(scores_raw, dict) else {}
    flags: dict[str, object] = flags_raw if isinstance(flags_raw, dict) else {}
    # Union the key sets: a category can carry a flag with no score, and the
    # brightline arm above must still see it. Iterating scores alone would drop
    # exactly the case that blocks.
    categories = set(scores) | set(flags)
    surfaced: dict[str, str] = {}
    for category in sorted(categories):
        raw_score = scores.get(category)
        score = float(raw_score) if isinstance(raw_score, (int, float)) else None
        verdict = surfaced_verdict(
            category=category,
            flagged=flags.get(category) is True,
            score=score,
            floor=scenario.floor_for(category),
        )
        if verdict is not None:
            surfaced[category] = verdict
    return surfaced


def _was_screened(record: dict[str, object]) -> bool:
    """Whether the classifier actually returned anything for this record.

    A PII-blocked record never reached the provider, so it carries no scores and
    no flags. It cannot be detected at any floor, which makes it a measurement
    of the egress guard rather than of the floor.
    """
    scores = record.get("openai_scores")
    flags = record.get("openai_flags")
    return bool(isinstance(scores, dict) and scores) or bool(
        isinstance(flags, dict) and flags
    )


def evaluate(
    records: list[dict[str, object]], scenario: FloorScenario
) -> ScenarioResult:
    """Measure *scenario* against every usable record in *records*."""
    result = ScenarioResult(scenario=scenario)
    band_totals: dict[str, list[int]] = {}
    for record in records:
        if record.get("openai_error"):
            continue
        verdicts = record_verdicts(record, scenario)
        population = record.get("population")

        if record.get("negative_control") is True:
            # An on-band clean passage carried inside the adversarial corpus:
            # it measures FALSE POSITIVES, so it belongs to neither the noise
            # denominator nor the recall denominator.
            result.control_surfaced += len(verdicts)
            continue

        if population == "clean":
            result.clean_records += 1
            result.clean_advisories += len(verdicts)
            if verdicts:
                result.clean_records_hit += 1
            band = record.get("age_band")
            if isinstance(band, str):
                band_totals.setdefault(band, []).append(len(verdicts))
            continue

        expected = record.get("expected_min_verdict")
        if not isinstance(expected, str) or not _was_screened(record):
            # No stated expectation (a brief-intake injection payload aimed at a
            # different guard), or never screened at all. Either way the record
            # cannot tell us anything about this floor.
            continue

        result.recall_records += 1
        if verdicts:
            result.recall_detected += 1
        else:
            passage_id = record.get("passage_id")
            result.lost.append(
                (
                    passage_id if isinstance(passage_id, str) else "<unnamed>",
                    record.get("known_gap") is True,
                )
            )
        reached = max((_VERDICT_RANK.get(v, 0) for v in verdicts.values()), default=0)
        if reached >= _VERDICT_RANK.get(expected, 0):
            result.recall_met_expected += 1
    result.per_band_clean = {
        band: sum(counts) / len(counts) for band, counts in sorted(band_totals.items())
    }
    return result


def scalar_scenarios(floors: tuple[float, ...]) -> list[FloorScenario]:
    """Build one flat-floor scenario per candidate value."""
    return [FloorScenario(name=f"flat {floor:g}", default=floor) for floor in floors]


def ratified_scenario() -> FloorScenario:
    """Build the per-category scenario UW-C378 ratified on 2026-08-25."""
    return FloorScenario(
        name=f"per-category ({RATIFIED_LOW_FLOOR:g} / {RATIFIED_HIGH_FLOOR:g} violence*)",
        default=RATIFIED_LOW_FLOOR,
        per_category=dict.fromkeys(RATIFIED_HIGH_CATEGORIES, RATIFIED_HIGH_FLOOR),
    )


def _markdown_row(r: ScenarioResult, *, marginal_loss: int | None) -> str:
    """Render one scenario as a table row."""
    marginal = "reference" if marginal_loss is None else str(marginal_loss)
    return (
        f"| {r.scenario.name} | {r.advisories_per_node:.3f} | "
        f"{'yes' if r.clears_noise_target else 'NO'} | "
        f"{r.clean_records_hit}/{r.clean_records} | "
        f"{r.recall_detected}/{r.recall_records} | "
        f"{r.recall_met_expected}/{r.recall_records} | "
        f"{len(r.lost)} ({r.lost_known_gap} known-gap) | {marginal} | "
        f"{r.control_surfaced} |"
    )


def render_markdown(results: list[ScenarioResult], *, reference: ScenarioResult) -> str:
    """Render the measured table, one row per scenario.

    ``reference`` is the scenario the marginal-loss column is measured against,
    normally the production floor. Absolute loss counts answer "how much does
    this classifier miss"; only the marginal column answers "what does CHANGING
    the floor cost", which is the question a floor decision actually turns on.
    """
    header = (
        "| Scenario | Advisories/node (clean) | Clears <= 0.2 | Clean nodes hit "
        "| Detected | Meets expected verdict | Lost | Lost beyond reference "
        "| Control false positives |"
    )
    reference_lost = set(reference.lost_ids)
    rows = [
        _markdown_row(
            r,
            marginal_loss=(
                None if r is reference else len(set(r.lost_ids) - reference_lost)
            ),
        )
        for r in results
    ]
    return "\n".join([header, "|" + "---|" * 9, *rows])


def as_payload(
    baseline: Path, results: list[ScenarioResult], *, reference: ScenarioResult
) -> dict[str, object]:
    """Build the machine-readable form of the table."""
    reference_lost = set(reference.lost_ids)
    return {
        "derived_from": str(baseline),
        "clean_noise_target": CLEAN_NOISE_TARGET,
        "production_floor": _ADVISORY_SCORE_FLOOR,
        "reference_scenario": reference.scenario.name,
        "excludes": [
            (
                "Perspective scores: retired as a Stage-0 signal source, so "
                "counting them would overstate recall at every candidate floor."
            ),
            (
                "Adversarial records with no expected_min_verdict, or that were "
                "never screened (PII-blocked before egress): neither can be "
                "detected at any floor, so including them in the recall "
                "denominator measures a different guard."
            ),
            (
                "The negative control: it measures false positives, not recall, "
                "and is reported in its own column."
            ),
        ],
        "scenarios": [
            {
                "name": r.scenario.name,
                "default_floor": r.scenario.default,
                "per_category_floors": r.scenario.per_category,
                "advisories_per_node": r.advisories_per_node,
                "clears_noise_target": r.clears_noise_target,
                "clean_records": r.clean_records,
                "clean_records_hit": r.clean_records_hit,
                "recall_records": r.recall_records,
                "recall_detected": r.recall_detected,
                "recall_met_expected": r.recall_met_expected,
                "lost_total": len(r.lost),
                "lost_known_gap": r.lost_known_gap,
                "lost_beyond_reference": sorted(set(r.lost_ids) - reference_lost),
                "lost_passage_ids": r.lost_ids,
                "control_false_positives": r.control_surfaced,
                "per_band_clean_advisories_per_node": r.per_band_clean,
            }
            for r in results
        ],
    }


def load_records(baseline: Path) -> list[dict[str, object]]:
    """Read the baseline artifact's record list."""
    data: object = json.loads(baseline.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{baseline}: baseline top level is not an object")
    records = data.get("records")
    if not isinstance(records, list):
        raise TypeError(f"{baseline}: baseline has no 'records' list")
    return [r for r in records if isinstance(r, dict)]


def main(argv: list[str] | None = None) -> int:
    """Derive and print the floor table.

    Raises:
        ValidationError: If any requested floor is not a finite number.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--floors",
        type=float,
        nargs="+",
        default=list(DEFAULT_FLOORS),
        help="Flat candidate floors to sweep.",
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="Also write the table as JSON here."
    )
    args = parser.parse_args(argv)

    # #CRITICAL: data integrity: reject a non-finite floor BEFORE the floors
    # are used anywhere, because nothing downstream can see one. argparse's
    # `type=float` accepts "nan", "inf" and "-inf", and every comparison with
    # nan is False, so the production-floor equality check below is False and a
    # nan floor sails through it. It then reaches `surfaced_verdict`, where
    # `score >= nan` is False for every scored finding, so the scenario
    # surfaces nothing and the table reports a ~100% advisory reduction that is
    # an artifact of IEEE-754 comparison rules, not a measurement. `inf` fails
    # the same way for the same reason (it is simply above every score); `-inf`
    # surfaces every scored finding instead, which is the same defect with the
    # sign flipped. All three are rejected here so the refusal reads on the
    # value rather than on some downstream figure.
    # #VERIFY: tests/unit/test_derive_stage0_floor_table.py::test_a_non_finite_floor_is_rejected_rather_than_derived
    non_finite = [f for f in args.floors if not math.isfinite(f)]
    if non_finite:
        joined = ", ".join(repr(f) for f in non_finite)
        msg = (
            f"floor values must be finite numbers; got {joined}. A non-finite "
            f"floor compares False against every score, so the derived table "
            f"would report an advisory reduction that is a comparison artifact "
            f"rather than a measurement."
        )
        raise ValidationError(msg, field="floors", value=non_finite)

    records = load_records(args.baseline)
    scenarios = [*scalar_scenarios(tuple(args.floors)), ratified_scenario()]
    results = [evaluate(records, scenario) for scenario in scenarios]
    # The production floor is the reference: every marginal figure answers
    # "what would CHANGING today's floor cost", not "what does the classifier
    # miss", which is a different and much larger number.
    # Fail rather than substitute. Every marginal figure below is a delta
    # against this reference, and the header prints the production floor as a
    # fact, so silently falling back to results[0] would relabel a whole table
    # of deltas against some other floor while still calling it production.
    # A --floors list that omits the production floor is a caller error, not a
    # degraded mode.
    reference = next(
        (
            r
            for r in results
            if r.scenario.default == _ADVISORY_SCORE_FLOOR
            and not r.scenario.per_category
        ),
        None,
    )
    if reference is None:
        raise SystemExit(
            f"--floors must include the production floor "
            f"{_ADVISORY_SCORE_FLOOR:g}; every marginal figure in this table is "
            f"a delta against it. Got: "
            f"{', '.join(format(f, 'g') for f in args.floors)}"
        )

    print(f"Stage-0 advisory-floor table derived from {args.baseline}")
    print(f"Records: {len(records)}; production floor {_ADVISORY_SCORE_FLOOR:g}")
    print(f"Marginal-loss reference: {reference.scenario.name}\n")
    print(render_markdown(results, reference=reference))
    print("\nLost recall-population passages per scenario (* = documented known gap):")
    for r in results:
        rendered = ", ".join(f"{pid}{'*' if known else ''}" for pid, known in r.lost)
        print(f"  {r.scenario.name}: {rendered or 'none'}")

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                as_payload(args.baseline, results, reference=reference), indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
