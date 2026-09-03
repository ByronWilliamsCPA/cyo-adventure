# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""`RS-CAL2`: tests for the Stage-0 advisory-floor derivation.

The point of the script under test is to give a floor decision an oracle, so
these tests are that oracle's oracle. The load-bearing one is
`test_predicate_matches_the_live_classifier_on_every_baseline_record`: the
script reimplements the production decision because it has to sweep a value
production holds in a module constant, and a reimplementation nobody checks is
worse than no measurement at all.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.moderation.classifiers import (
    _ADVISORY_SCORE_FLOOR,  # pyright: ignore[reportPrivateUsage]
    _openai_finding,  # pyright: ignore[reportPrivateUsage]
)
from scripts.derive_stage0_floor_table import (
    CLEAN_NOISE_TARGET,
    DEFAULT_BASELINE,
    FloorScenario,
    ScenarioResult,
    _was_screened,  # pyright: ignore[reportPrivateUsage]
    evaluate,
    load_records,
    main,
    ratified_scenario,
    record_verdicts,
    render_markdown,
    scalar_scenarios,
    surfaced_verdict,
)

# ``DEFAULT_BASELINE`` is relative to the repository root (the script is run
# from there), so it is anchored against ``__file__`` here rather than against
# the process working directory; otherwise every fixture-dependent test below
# fails with FileNotFoundError when pytest is invoked from anywhere else.
BASELINE = Path(__file__).resolve().parents[2] / DEFAULT_BASELINE


@pytest.fixture(scope="module")
def records() -> list[dict[str, object]]:
    """The stored 2026-08-01 baseline records."""
    return load_records(BASELINE)


def _live_verdict(category: str, flagged: bool, score: float) -> str | None:
    """Run the production decision and reduce it to this script's vocabulary."""
    finding = _openai_finding("n1", category, flagged, score)
    return None if finding is None else finding.verdict.value


def test_predicate_matches_the_live_classifier_on_every_baseline_record(
    records: list[dict[str, object]],
) -> None:
    """The script's predicate and production agree at the production floor.

    Every category of every record, not a sample: this is the only thing
    standing between the derived table and a number that describes a decision
    rule the gate does not actually use. A divergence here means either the
    script drifted or `_openai_finding` changed; both must fail the build.
    """
    compared = 0
    for record in records:
        scores = record.get("openai_scores")
        flags = record.get("openai_flags")
        if not isinstance(scores, dict) or not isinstance(flags, dict):
            continue
        for category, raw_score in scores.items():
            if not isinstance(raw_score, (int, float)):
                continue
            flagged = flags.get(category) is True
            expected = _live_verdict(category, flagged, float(raw_score))
            actual = surfaced_verdict(
                category=category,
                flagged=flagged,
                score=float(raw_score),
                floor=_ADVISORY_SCORE_FLOOR,
            )
            assert actual == expected, (
                f"{record.get('passage_id')}/{category}: script said {actual}, "
                f"classifiers.py said {expected}"
            )
            compared += 1
    # A silently empty comparison would pass the loop above, so pin that the
    # baseline actually exercised it. 134 screened records x 13 categories.
    assert compared == 1742


@pytest.mark.parametrize("score", [float("nan"), float("inf")])
def test_non_finite_scores_match_the_live_classifier(score: float) -> None:
    """A non-finite score is treated as absent by both implementations."""
    assert not math.isfinite(score)
    for flagged in (True, False):
        assert surfaced_verdict(
            category="violence", flagged=flagged, score=score, floor=0.01
        ) == _live_verdict("violence", flagged, score)


def test_a_flagged_brightline_category_blocks_at_any_floor() -> None:
    """A provider-flagged bright-line category never depends on the floor."""
    for floor in (0.0, 0.01, 0.99):
        assert (
            surfaced_verdict(
                category="sexual/minors", flagged=True, score=0.0, floor=floor
            )
            == "block"
        )


def test_a_flagged_non_brightline_category_bypasses_the_floor() -> None:
    """OpenAI's own boolean flag surfaces a category the floor would drop."""
    assert (
        surfaced_verdict(category="violence", flagged=True, score=0.0, floor=0.5)
        == "advisory"
    )


def test_a_scenario_applies_per_category_floors_over_its_default() -> None:
    """A per-category floor overrides the default for that category only."""
    scenario = FloorScenario(name="t", default=0.01, per_category={"violence": 0.10})
    assert scenario.floor_for("violence") == pytest.approx(0.10)
    assert scenario.floor_for("harassment") == pytest.approx(0.01)


def test_record_verdicts_sees_a_flag_carrying_category_with_no_score() -> None:
    """A category present only in the flag map is still judged.

    Iterating the score map alone would drop exactly the case that blocks, so
    the union of both key sets is load-bearing rather than defensive.
    """
    record: dict[str, object] = {
        "openai_scores": {},
        "openai_flags": {"sexual/minors": True},
    }
    assert record_verdicts(record, FloorScenario(name="t", default=0.01)) == {
        "sexual/minors": "block"
    }


def test_the_pii_blocked_record_counts_as_never_screened(
    records: list[dict[str, object]],
) -> None:
    """A record the egress guard stopped carries no scores to judge.

    `F1-pii-positive-control` is in the adversarial population but was never
    sent to the provider, so it cannot be detected at ANY floor. Counting it as
    a floor's recall loss measures the egress guard instead.
    """
    pii = next(r for r in records if r.get("passage_id") == "F1-pii-positive-control")
    assert pii.get("population") == "adversarial"
    assert not _was_screened(pii)
    scored = next(r for r in records if r.get("passage_id") == "A1-roof-flight-3-5")
    assert _was_screened(scored)


def test_the_recall_population_excludes_the_unscreened_and_the_unexpectant(
    records: list[dict[str, object]],
) -> None:
    """The recall denominator is 12, not the 14-record adversarial population.

    `UW-C378`'s hand-derived "loses 10 of the 14 adversarial pairs" divided a
    numerator over the screened records by a denominator over the whole
    population, which understates the loss rate. Two records are excluded here
    and named, so the correction is visible rather than implicit: one was never
    screened, one states no expected verdict.
    """
    result = evaluate(records, FloorScenario(name="t", default=_ADVISORY_SCORE_FLOOR))
    assert result.recall_records == 12
    assert result.clean_records == 120
    adversarial = [r for r in records if r.get("population") == "adversarial"]
    assert len(adversarial) == 14
    excluded = {
        r.get("passage_id")
        for r in adversarial
        if not isinstance(r.get("expected_min_verdict"), str) or not _was_screened(r)
    }
    assert excluded == {"F1-pii-positive-control", "E1-brief-injection#payload"}


def test_the_negative_control_is_in_neither_denominator(
    records: list[dict[str, object]],
) -> None:
    """The on-band control measures false positives, so it is reported alone."""
    result = evaluate(records, FloorScenario(name="t", default=_ADVISORY_SCORE_FLOOR))
    control = [r for r in records if r.get("negative_control") is True]
    assert len(control) == 1
    assert result.clean_records + result.recall_records == 132
    assert result.control_surfaced == 0


def test_reproduces_the_ratified_headline_figures(
    records: list[dict[str, object]],
) -> None:
    """The script reproduces `UW-C378`'s two published numbers.

    That report said only 0.10 clears the <= 0.2 clean-noise target, and that
    0.10 loses 10 adversarial pairs. Both come back out of this derivation, which
    is what makes the corrections in the sibling tests credible: the script is not
    computing a different thing, it is computing the same thing with the
    populations separated.
    """
    results = {
        s.name: evaluate(records, s) for s in scalar_scenarios((0.01, 0.02, 0.05, 0.10))
    }
    clears = {name: r.clears_noise_target for name, r in results.items()}
    assert clears == {
        "flat 0.01": False,
        "flat 0.02": False,
        "flat 0.05": False,
        "flat 0.1": True,
    }
    assert results["flat 0.1"].advisories_per_node <= CLEAN_NOISE_TARGET
    assert len(results["flat 0.1"].lost) == 10


def test_the_marginal_cost_of_the_ratified_split_is_zero_lost_records(
    records: list[dict[str, object]],
) -> None:
    """The ratified per-category split cuts noise without losing recall.

    This is the finding the flat sweep cannot show. Against the production floor
    as reference, the split loses no record the production floor already
    detects, while cutting clean noise by more than half. It still does not
    reach the <= 0.2 target, so it is not the end of calibration; `RS-CAL4`
    against a fresh capture is.
    """
    reference = evaluate(
        records, FloorScenario(name="ref", default=_ADVISORY_SCORE_FLOOR)
    )
    split = evaluate(records, ratified_scenario())
    assert set(split.lost_ids) - set(reference.lost_ids) == set()
    assert split.advisories_per_node < reference.advisories_per_node / 2
    assert not split.clears_noise_target


def test_raising_the_flat_floor_costs_only_known_gap_records(
    records: list[dict[str, object]],
) -> None:
    """0.01 -> 0.10 loses 2 records, both already-documented structural gaps.

    The absolute loss at 0.10 is 10 of 12, but 8 of those are already lost at
    the production floor, so they are not a cost of the raise. Both marginal
    losses carry `known_gap`: aggregate harm spread across nodes, which per-node
    classification cannot see at any floor. Attributing them to the floor
    overstates what the floor decision is trading away.
    """
    reference = evaluate(
        records, FloorScenario(name="ref", default=_ADVISORY_SCORE_FLOOR)
    )
    raised = evaluate(records, FloorScenario(name="raised", default=0.10))
    marginal = set(raised.lost_ids) - set(reference.lost_ids)
    assert marginal == {
        "C2-aggregate-stranger-10-13#n2",
        "C2-aggregate-stranger-10-13#n3",
    }
    known_gap_ids = {r.get("passage_id") for r in records if r.get("known_gap") is True}
    assert marginal <= known_gap_ids


def test_stage0_alone_never_reaches_the_expected_minimum_verdict(
    records: list[dict[str, object]],
) -> None:
    """0 of 12 is a property of the corpus, not an alarm about the floor.

    Nine of the twelve recall records expect `flag` and Stage 0 can only produce
    `advisory` or `block`; most carry `target_stage: 1`, meaning the corpus
    expects the LLM review stage to catch them. So the only recall question a
    Stage-0 floor can answer is "did anything surface at all", and a reader who
    treats the met-expected column as the floor's score will reject every
    candidate. Pinned so the column is never silently reinterpreted.
    """
    for floor in (0.0, 0.01, 0.10):
        result = evaluate(records, FloorScenario(name=f"f{floor}", default=floor))
        assert result.recall_met_expected == 0
    expectations = [
        r.get("expected_min_verdict")
        for r in records
        if r.get("population") == "adversarial"
        and isinstance(r.get("expected_min_verdict"), str)
    ]
    assert expectations.count("flag") == 9
    assert expectations.count("block") == 3


def test_the_marginal_column_is_a_set_difference_not_a_count(
    records: list[dict[str, object]],
) -> None:
    """A scenario that loses a DIFFERENT record is still a loss.

    Comparing loss COUNTS would report zero for a floor that trades one record
    for another, which is the failure mode that makes a recall metric useless.
    """
    reference = ScenarioResult(scenario=FloorScenario(name="ref", default=0.01))
    reference.lost = [("keeps", False)]
    swapped = ScenarioResult(scenario=FloorScenario(name="swapped", default=0.02))
    swapped.lost = [("loses-instead", False)]
    table = render_markdown([reference, swapped], reference=reference)
    assert "| reference |" in table
    swapped_row = next(line for line in table.splitlines() if "swapped" in line)
    assert "| 1 |" in swapped_row


def test_the_derived_table_names_every_scenario_it_measured(
    records: list[dict[str, object]],
) -> None:
    """Rendering covers the header, the separator, and one row per scenario."""
    scenarios = [*scalar_scenarios((0.01, 0.10)), ratified_scenario()]
    results = [evaluate(records, s) for s in scenarios]
    table = render_markdown(results, reference=results[0])
    lines = table.splitlines()
    assert len(lines) == 2 + len(scenarios)
    for scenario in scenarios:
        assert any(scenario.name in line for line in lines)


@pytest.mark.parametrize(
    "argv",
    [
        # ``--baseline`` is passed for the same reason ``BASELINE`` is anchored
        # against ``__file__`` above: the script's default is relative to the
        # repository root, so without it a non-root working directory would
        # raise FileNotFoundError and this test would pass for the wrong
        # reason. The guard under test runs before the baseline is read, so the
        # path only has to be correct, not reached.
        ["--baseline", str(BASELINE), "--floors", "nan"],
        ["--baseline", str(BASELINE), "--floors", "inf"],
        # "=" form: argparse reads a bare "-inf" as an option, not a value.
        [f"--baseline={BASELINE}", "--floors=-inf"],
    ],
)
def test_a_non_finite_floor_is_rejected_rather_than_derived(argv: list[str]) -> None:
    """A non-finite floor is refused, not silently derived into a table.

    argparse's ``type=float`` accepts these strings, and no downstream check
    catches them: every comparison with nan is False, so the
    production-floor equality check does not reject a nan floor. Left
    unchecked, ``surfaced_verdict``'s own ``score >= floor`` is then False for
    every scored finding, the whole baseline drops out, and the table reports a
    near-total advisory reduction that is an IEEE-754 artifact rather than a
    measurement. ``-inf`` is the same defect with the sign flipped: it surfaces
    every scored finding. Either way the output is a percentage someone
    ratifies a safety floor from.
    """
    with pytest.raises(ValidationError, match="finite"):
        main(argv)


def test_the_baseline_artifact_is_the_one_the_script_defaults_to() -> None:
    """The default path resolves and carries the schema the script expects."""
    payload: dict[str, object] = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    counts = payload["counts"]
    assert isinstance(counts, dict)
    assert counts["clean"] == 120
    assert counts["adversarial"] == 14
    assert counts["pii_blocked"] == 1
