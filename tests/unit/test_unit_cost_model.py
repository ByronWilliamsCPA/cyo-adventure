"""Unit tests for the generated per-book unit-cost model.

The model exists to answer step 4 of the generation-review workstream plan
(``docs/planning/generation-review-workstream-plan-2026-08-22.md``) without
asserting anything the committed evidence does not support. D3 was ruled only
partially on 2026-08-23: the revenue anchor is a subscription at $1.99 or
$4.99 with the choice still open, so the model carries the price point as a
parameter and states headroom at both. It must never emit a single absolute
per-book cap; that is the part of D3 still owed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from cyo_adventure.core.pricing import PRICES
from cyo_adventure.validator.band_profile import offered_cells
from scripts.unit_cost_model import (
    EXCLUDED_FILL_RUNS,
    EXCLUDED_RUNS,
    GENERATED_DOC,
    LEG_MODELS,
    PRICE_POINTS_USD,
    RULED_FILL_LEG,
    RULED_REVIEW_LEG,
    _band_rank,
    _cell_sort_key,
    _render_legs,
    cell_weights,
    delivery_quality,
    fill_by_band,
    fill_costs,
    fill_provenance,
    leg_costs,
    load_fill_books,
    load_records,
    main,
    model,
    record_provenance,
    render,
)

EVIDENCE_README = Path("docs/planning/evidence/skeleton-author-vendors/README.md")


def _write_record(root: Path, run: str, name: str, **fields: Any) -> Path:
    """Write one run record into a synthetic evidence tree.

    Args:
        root: The synthetic evidence root.
        run: The run directory name, which is what the exclusion filter reads.
        name: The record's file stem.
        **fields: Overrides merged over a minimal token-bearing record.

    Returns:
        The path written.
    """
    record: dict[str, Any] = {
        "leg": RULED_FILL_LEG,
        "band": "8-11",
        "length": "short",
        "style": "prose",
        "input_tokens": 1000,
        "output_tokens": 2000,
        "reasoning_tokens": 0,
        "strict_pass": True,
        "latency_s": 1.0,
        "error": "",
    }
    record.update(fields)
    path = root / run / f"{name}.record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The leg -> price key contract
# ---------------------------------------------------------------------------


def test_every_leg_maps_to_a_real_price_entry() -> None:
    """A leg label that names no priced model would cost silently as zero.

    ``LEG_MODELS`` is hand-synced against the ``leg`` strings the committed
    run records use and the ``(provider, model)`` keys ``core.pricing.PRICES``
    is keyed by. Nothing else ties the two, so a rename on either side has to
    fail here rather than drop that leg out of the model unnoticed.
    """
    for leg, key in LEG_MODELS.items():
        assert key in PRICES, f"{leg} maps to {key}, which PRICES does not carry"


def test_every_priced_leg_is_fully_priced() -> None:
    """A half-priced entry would understate that leg rather than refuse it.

    ``estimate_cost`` costs the input and output halves independently and
    reports ``complete=False`` when either is missing, so a leg priced on one
    half only produces a real-looking number that is too small. The model
    reports incompleteness, but a leg it costs at all should be fully priced.
    """
    for leg, key in LEG_MODELS.items():
        assert PRICES[key].fully_priced, f"{leg} ({key[1]}) is only half priced"


# ---------------------------------------------------------------------------
# Measured coverage: the model must state how little is measured
# ---------------------------------------------------------------------------


def test_the_model_publishes_its_own_measured_coverage() -> None:
    """The evidence covers a fraction of the grid, and the model says which.

    This is the finding step 4 turns on. Reporting a per-book cost for all 18
    offered cells while only two carry token records would be the exact defect
    the workstream plan exists to catch.

    The assertion reads ``model()["coverage"]`` rather than recomputing the
    measured set from ``leg_costs()``. An earlier version recomputed it, so a
    ``model()`` that published the whole offered grid as measured left this
    test green: the test was checking its own re-implementation and not the
    published claim. It is also ``<=`` rather than ``<``, because full grid
    coverage is the project succeeding, not a regression to fail on.
    """
    coverage = model()["coverage"]
    measured = {tuple(c.split("/")) for c in coverage["measured"]}

    assert measured, "no committed run record carries token counts"
    assert coverage["measured_cells"] == len(measured)
    assert measured <= offered_cells(), "a measured cell is not an offered cell"
    assert coverage["off_grid"] == [], "a record names a cell the grid does not"


def test_no_leg_claims_more_delivered_books_than_it_has() -> None:
    """``strict_pass`` records, not merely error-free ones, are delivered books.

    A run that returned prose and then failed the deterministic gate cost real
    money and delivered nothing. Counting it as a delivered book is what makes
    a cost-per-delivered-book figure look better than it is, so the two counts
    are carried separately and the narrower one can never exceed the wider.
    """
    for leg, row in leg_costs().items():
        assert row["strict_pass"] <= row["without_error"] <= row["records"], leg


# ---------------------------------------------------------------------------
# Credit weights (D3: credits scale with book length and age band)
# ---------------------------------------------------------------------------


def test_credit_weights_cover_every_offered_cell() -> None:
    """A cell with no weight is a request shape the credit system cannot price."""
    assert set(cell_weights()) == offered_cells()


def test_credit_weights_discriminate_across_the_grid() -> None:
    """A weighting that barely moves would not implement D3's ruling at all.

    D3 ruled that credits scale with book length and age band. The commissioned
    word counts in the catalog span a wide range, so a correct weighting must
    too; a near-flat table would price a 16+ long gamebook like a 3-5 short and
    silently reproduce today's count-based quota under a new name.
    """
    weights = [row["weight"] for row in cell_weights().values()]

    assert min(weights) == pytest.approx(1.0), "the baseline cell is not 1.0"
    assert max(weights) > 10, f"weights span only {max(weights):.1f}x, too flat"


def test_credit_weight_rises_with_length_within_a_band() -> None:
    """Longer books cost more credits than shorter ones at the same band.

    Monotonicity in length is the one property D3's ruling states outright. It
    is asserted per band rather than globally because the bands overlap: an
    8-11 long book commissions more words than a 13-16 medium one, so a global
    sort would fail on a correct table.
    """
    order = {"short": 0, "medium": 1, "long": 2}
    by_band: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for (band, length, style), row in cell_weights().items():
        by_band.setdefault((band, style), []).append((order[length], row["weight"]))

    for key, pairs in by_band.items():
        ranked = [w for _, w in sorted(pairs)]
        assert ranked == sorted(ranked), f"{key} weights fall as length rises: {ranked}"


# ---------------------------------------------------------------------------
# What the model must NOT say (D3 is only partly ruled)
# ---------------------------------------------------------------------------


def test_both_candidate_price_points_are_carried() -> None:
    """D3 left $1.99 versus $4.99 open, so the model may not pick one."""
    assert PRICE_POINTS_USD == (1.99, 4.99)
    headroom = model()["headroom"]
    assert {row["price_usd"] for row in headroom} == set(PRICE_POINTS_USD)


def test_the_model_states_no_absolute_per_book_cap() -> None:
    """The cap is the part of D3 still owed; emitting one would pre-empt it.

    The plan blocks any absolute per-book ceiling until the price point is
    chosen and the human-minutes term is measured (S-6). The model publishes
    the cost side and the headroom at each candidate price, and stops there.
    """
    data = model()

    assert "cap_usd" not in data
    assert data["cap"] is None
    assert "S-6" in data["assumptions"]["human_minutes"]


# ---------------------------------------------------------------------------
# The generated-doc contract (mirrors scripts/catalog_census.py)
# ---------------------------------------------------------------------------


def test_generated_doc_is_current() -> None:
    """The committed page matches the evidence and prices it is derived from.

    This is the anti-decay mechanism: a price refresh or a new run record that
    is not reflected in the page fails here rather than leaving the prose
    quietly contradicting the data it cites.
    """
    assert GENERATED_DOC.read_text(encoding="utf-8") == render(model())


def test_check_mode_detects_a_stale_doc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--check`` exits non-zero when the doc does not match."""
    stale = tmp_path / "unit-cost-model.md"
    stale.write_text("# Unit cost model\n\nstale\n", encoding="utf-8")
    monkeypatch.setattr("scripts.unit_cost_model.GENERATED_DOC", stale)

    assert main(["--check"]) == 1


def test_json_mode_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    """``--json`` emits parseable JSON carrying the leg costs and weights."""
    assert main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["legs"]
    assert payload["cells"]


def test_fill_cost_uses_billed_figures_rather_than_recomputed_ones() -> None:
    """Fill cost comes from the runs' metered `cost`, not from a token estimate.

    The vendor-comparison book records carry no `input_tokens`, so a recomputed
    figure is not even derivable there. Using the metered value is therefore the
    only honest option, and it is also the better one: it is what was billed.
    """
    fills = fill_costs()
    assert fills, "no billed fill records found"
    for row in fills.values():
        assert row["source"] == "metered"
        assert row["billed_usd"] > 0


def test_fill_cost_is_measured_only_on_the_ruled_fill_leg() -> None:
    """The gap is the point: no other leg has a billed fill record committed.

    D1 ruled the fill leg to `deepseek-v4-pro`, which is the one leg this
    evidence covers, so the model can price the ruled configuration and nothing
    else. A future leg change re-opens this and the test should then fail.
    """
    assert set(fill_costs()) == {RULED_FILL_LEG}


def test_failed_fill_books_cost_money_and_deliver_nothing() -> None:
    """A book that errors is still billed, and the model must carry that.

    Charging failures to the books that landed is the difference between cost
    per call and cost per delivered book, which is the distinction the vendor
    comparison found to be worth 4x on the worst leg.
    """
    row = fill_costs()[RULED_FILL_LEG]
    assert row["books"] > row["delivered"], "no failed book in the corpus"
    assert row["failed_usd"] > 0
    assert row["usd_per_delivered_book"] > row["billed_usd"] / row["books"]


def test_headroom_scales_the_commissioned_word_rate() -> None:
    """Headroom multiplies commissioned words by a per-commissioned-word rate.

    Two category errors have to stay fixed here and they are different. The
    first is scaling the fill workload by the skeleton-authoring corpus, which
    an earlier draft did. The second is subtler and shipped: a cell's
    ``median_words`` is what the skeleton COMMISSIONS, while
    ``usd_per_1k_words`` is what a DELIVERED word cost. These books delivered
    about half their commission, so the two rates differ by roughly 2x and
    multiplying one by the other put the dearest cell at 95% of a $1.99
    subscription instead of 44%.

    Reporting the right rate is not the same as scaling by it, and only the
    second is the defect. An earlier version of this test checked the reported
    rate and the absent key; putting the delivered rate back into the
    multiplication left both of those intact and this test green, so it did not
    guard what its `#VERIFY` citation in `_headroom` claims. The scaled figures
    are therefore recomputed here from both candidate rates: they must match
    the commissioned one and must not match the delivered one.
    """
    data = model()
    fill = fill_costs()[RULED_FILL_LEG]
    delivered_rate = float(fill["usd_per_1k_words"])
    commissioned_rate = float(fill["usd_per_1k_commissioned_words"])

    assert commissioned_rate < delivered_rate, (
        "the two rates are indistinguishable, so this test cannot discriminate"
    )
    for row in data["headroom"]:
        assert row["basis"] == "billed fill, ruled leg, per commissioned word"
        assert row["usd_per_1k_commissioned_words"] == commissioned_rate
        assert "usd_per_1k_words" not in row

        words = int(data["cells"][row["dearest_cell"]]["median_words"])
        assert row["scaled_max_usd"] == pytest.approx(
            commissioned_rate * words / 1000, abs=5e-5
        )
        assert row["scaled_max_usd"] != pytest.approx(
            delivered_rate * words / 1000, abs=5e-5
        ), "the dearest cell was scaled by the delivered-word rate"


def test_the_scaled_cost_of_a_cell_is_its_commissioned_words_times_the_rate() -> None:
    """The published figure is reproducible from the two numbers beside it.

    Both the cheapest and dearest cells are recomputed from the cell table's
    own ``median_words`` and the fill table's own rate. A headroom row that
    used any other rate, or any other word count, fails here.
    """
    data = model()
    rate = fill_costs()[RULED_FILL_LEG]["usd_per_1k_commissioned_words"]
    for row in data["headroom"]:
        for cell_key, scaled_key in (
            ("cheapest_cell", "scaled_min_usd"),
            ("dearest_cell", "scaled_max_usd"),
        ):
            words = data["cells"][row[cell_key]]["median_words"]
            assert row[scaled_key] == pytest.approx(rate * words / 1000, abs=5e-5), (
                f"{row[cell_key]} does not reproduce from {words} words"
            )


def test_the_review_leg_carries_no_measured_fill_cost() -> None:
    """The ruled review leg is unmeasured, and the model must say so.

    Quoting a pair cost while only one half is measured is the failure this
    guards: the review term is named as absent rather than silently omitted.
    """
    data = model()
    assert RULED_REVIEW_LEG not in fill_costs()
    assert RULED_REVIEW_LEG in data["assumptions"]["review_leg"]


def test_billed_fill_books_are_attributed_to_a_catalog_band() -> None:
    """Each billed book is joined to the skeleton it filled, so it has a band.

    Without the join the fill corpus is a bare average and the scaling to other
    cells is unfalsifiable. With it, the rate can be read per band and the
    linearity assumption becomes checkable against real spread.
    """
    books = load_fill_books()
    assert books
    for book in books:
        assert book["skeleton"], "book not joined to a skeleton"
        # The join, not merely the slug: an unresolvable slug leaves the band
        # empty and the commissioned words at zero, which `fill_by_band` then
        # drops while `fill_costs` keeps, so the two tables disagree with
        # nothing reconciling them. Asserting only that `skeleton` is truthy
        # passes either way and is what let that fallback survive review.
        assert book["band"], f"{book['skeleton']} resolved to no catalog band"
        assert book["commissioned_words"] > 0, book["skeleton"]
    banded = {b["band"] for b in books if b["band"]}
    assert len(banded) >= 3, f"fill evidence spans too few bands: {banded}"


def test_the_fill_rate_is_reported_per_band() -> None:
    """The per-band breakdown exists and covers both newly-probed bands.

    `13-16` and `16+` are the bands with the largest books and therefore the
    ones where a wrong scaling assumption costs the most, so a model that
    scales into them without any measurement there would be guessing hardest
    exactly where it matters most.
    """
    bands = model()["fill_by_band"]
    assert {"13-16", "16+"} <= set(bands)
    for row in bands.values():
        assert row["usd_per_1k_commissioned_words"] > 0


# ---------------------------------------------------------------------------
# Run provenance: what the corpus itself disowns must not price a leg
# ---------------------------------------------------------------------------


def test_excluded_runs_match_the_evidence_readme() -> None:
    """The exclusion list is the README's, not this file's opinion.

    ``EXCLUDED_RUNS`` is hand-maintained, and nothing but this test ties it to
    the document that actually decides which runs are evidence. A third run
    excluded in the README and forgotten here would be priced as though it
    counted, and the rendered page would give no sign of it.
    """
    readme = EVIDENCE_README.read_text(encoding="utf-8")
    bullets = re.split(r"^- ", readme, flags=re.MULTILINE)[1:]
    declared: set[str] = set()
    named: set[str] = set()
    for bullet in bullets:
        match = re.match(r"`runs/([^/`]+)/`", bullet)
        if match is None:
            continue
        named.add(match.group(1))
        if "excluded from S-1 analysis" in bullet:
            declared.add(match.group(1))

    assert named, "no run bullets parsed; the README format changed"
    assert declared == set(EXCLUDED_RUNS), (
        f"README excludes {sorted(declared)}, EXCLUDED_RUNS holds "
        f"{sorted(EXCLUDED_RUNS)}"
    )
    assert set(EXCLUDED_RUNS) <= named, "EXCLUDED_RUNS names a run that is gone"


def test_records_under_an_excluded_run_are_not_read(tmp_path: Path) -> None:
    """A run the corpus disowns contributes no record at all.

    Not a cosmetic filter: two of the five priced legs have no error-free
    record anywhere outside these runs, so reading them publishes a median for
    those legs computed entirely from runs the README says are not evidence.
    """
    excluded_run = min(EXCLUDED_RUNS)
    _write_record(tmp_path, excluded_run, "smoke", input_tokens=999)
    _write_record(tmp_path, "e1-2026-08-21", "real", input_tokens=111)

    records = load_records(tmp_path)

    assert [r["input_tokens"] for r in records] == [111]
    assert record_provenance(tmp_path) == {
        "files": 2,
        "excluded_run": 1,
        "replays": 0,
        "analysed": 1,
    }


def test_a_record_replayed_into_a_second_run_is_counted_once(
    tmp_path: Path,
) -> None:
    """An identical record in two run directories is one authoring episode.

    Three such pairs exist in the corpus, identical down to ``latency_s``,
    which two independent model calls do not produce. Counting one episode
    twice pulls the median toward whatever that episode happened to cost.
    """
    _write_record(tmp_path, "e1-2026-08-21", "A__r1", input_tokens=500)
    _write_record(tmp_path, "e1r3-2026-08-21", "A__r1", input_tokens=500)

    assert len(load_records(tmp_path)) == 1
    assert record_provenance(tmp_path)["replays"] == 1


def test_a_re_run_that_differs_in_any_field_is_not_a_replay(
    tmp_path: Path,
) -> None:
    """The dedup key is content, so a genuine second attempt still counts.

    This is the discrimination half of the test above. A key of
    ``(leg, cell, replicate)`` would also make the replay test pass while
    silently discarding real re-runs, which is the opposite defect and a worse
    one: it would shrink the corpus in a direction nothing reports.
    """
    _write_record(tmp_path, "e1-2026-08-21", "A__r1", latency_s=1.0)
    _write_record(tmp_path, "e1r3-2026-08-21", "A__r1", latency_s=1.5)

    assert len(load_records(tmp_path)) == 2
    assert record_provenance(tmp_path)["replays"] == 0


def test_a_non_object_record_raises_rather_than_being_skipped(
    tmp_path: Path,
) -> None:
    """A malformed record is a fault, not a record that quietly does not exist.

    ``catalog_census.load_shells`` refuses to silently undercount its catalog
    for the same reason: a leg priced from fewer episodes than the page claims
    is indistinguishable, in the page, from a leg that ran fewer episodes.
    """
    path = tmp_path / "e1-2026-08-21" / "broken.record.json"
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="does not hold a JSON object"):
        load_records(tmp_path)


def test_the_page_states_what_it_set_aside() -> None:
    """A filter that removes part of a corpus has to say so on the page.

    A corpus silently reduced by a tenth renders exactly like a corpus that was
    always that size, so the counts are published rather than kept internal.
    """
    provenance = record_provenance()
    page = render(model())

    assert provenance["excluded_run"] > 0, "no excluded run in the corpus"
    assert provenance["replays"] > 0, "no replayed record in the corpus"
    assert provenance["analysed"] == (
        provenance["files"] - provenance["excluded_run"] - provenance["replays"]
    )
    for count in (
        provenance["files"],
        provenance["excluded_run"],
        provenance["replays"],
        provenance["analysed"],
    ):
        assert str(count) in page


def test_a_leg_reports_its_whole_corpus_not_just_its_priced_records() -> None:
    """Most records carry no tokens, so the priced count is a minority.

    Printing only the priced count reads as the leg's full history and hides
    that three quarters of its records were dropped before costing.
    """
    for leg, row in leg_costs().items():
        assert row["corpus_records"] >= row["records"], leg
    assert any(
        row["corpus_records"] > row["records"] for row in leg_costs().values()
    ), "no leg drops any record, so this test cannot discriminate"


# ---------------------------------------------------------------------------
# Rendering an empty or partial row rather than crashing on it
# ---------------------------------------------------------------------------


def test_a_leg_with_no_clean_record_renders_rather_than_crashing(
    tmp_path: Path,
) -> None:
    """A leg whose every priced record errored has a spend and no cost.

    This is reachable today, not theoretical: once the excluded runs are
    filtered out, two of the five priced legs have no error-free record left.
    Formatting ``None`` with ``:.4f`` raises, and a raise in the renderer takes
    the whole page down, including every row that was fine.
    """
    _write_record(tmp_path, "e1-2026-08-21", "boom", error="HTTP 402")
    row = leg_costs(tmp_path)[RULED_FILL_LEG]

    assert row["records"] == 1
    assert row["without_error"] == 0
    assert row["median_usd"] is None

    lines = _render_legs({"legs": leg_costs(tmp_path)})

    assert any("n/a | n/a | n/a" in line for line in lines)
    assert any("none that came back without an error" in line for line in lines)


def test_a_record_missing_output_tokens_is_reported_as_incomplete(
    tmp_path: Path,
) -> None:
    """Half a price is not a total, and the page has to say which rows are half.

    ``core/pricing.py`` carries a standing ``#CRITICAL`` requiring that a
    partial sum never silently contribute to a figure a reader takes as a
    total. On these legs the input half alone understates by several times.
    """
    _write_record(tmp_path, "e1-2026-08-21", "half", output_tokens=None)
    row = leg_costs(tmp_path)[RULED_FILL_LEG]

    assert row["complete"] is False

    lines = _render_legs({"legs": leg_costs(tmp_path)})

    assert any("cost is the input half only" in line for line in lines)


def test_the_reasoning_share_is_averaged_over_the_same_records_as_the_cost(
    tmp_path: Path,
) -> None:
    """Two numbers printed side by side must describe the same set of runs.

    A share averaged over every record while the median beside it is taken over
    the error-free ones is a mixed population inside a single table row, and
    nothing in the row shows it.
    """
    _write_record(
        tmp_path, "e1-2026-08-21", "ok", reasoning_tokens=0, output_tokens=1000
    )
    _write_record(
        tmp_path,
        "e1-2026-08-21",
        "bad",
        reasoning_tokens=1000,
        output_tokens=1000,
        error="HTTP 402",
    )
    row = leg_costs(tmp_path)[RULED_FILL_LEG]

    assert row["without_error"] == 1
    assert row["reasoning_share"] == 0.0, "the errored record leaked into the mean"


def test_an_unrecognised_band_sorts_last_instead_of_raising() -> None:
    """A stray band must not take the whole report down with it.

    ``_record_cell`` deliberately coerces a missing ``band`` to the literal
    ``"None"``, so the sort key has to accept it. The ordering itself is read
    from ``storybook.models`` rather than hand-copied, so a new age band cannot
    land in two different orders in two different files.
    """
    assert _band_rank("3-5") < _band_rank("10-13") < _band_rank("16+")
    assert _band_rank("None") > _band_rank("16+")
    assert _cell_sort_key(("None", "nonsense", "prose")) > _cell_sort_key(
        ("16+", "long", "prose")
    )


# ---------------------------------------------------------------------------
# The two billed populations, and what the corpus says about short books
# ---------------------------------------------------------------------------


def test_the_per_band_total_is_reconciled_against_the_leg_total() -> None:
    """Two tables headed with billed dollars disagree, and the page says why.

    ``fill_costs`` charges failed books to the books that landed;
    ``fill_by_band`` cannot, because a book that delivered nothing is not
    evidence about the band it was aimed at. The difference is exactly the
    failed spend, and a reader should not have to subtract two tables to find
    it.
    """
    leg = fill_costs()[RULED_FILL_LEG]
    band_total = sum(row["billed_usd"] for row in fill_by_band().values())

    assert leg["billed_usd"] > band_total, "no failed book, so nothing to reconcile"
    assert leg["billed_usd"] - band_total == pytest.approx(leg["failed_usd"], abs=1e-4)
    assert f"{leg['billed_usd']:.4f}" in render(model())
    assert f"{band_total:.4f}" in render(model())


def test_the_scorable_share_is_settled_by_the_corpus_not_hedged() -> None:
    """Delivered words near half of commission has two readings, and one is true.

    The page used to say nothing committed separates "these books are short"
    from "the measurement missed what they wrote", and that the second would
    make every dollars-per-word figure pessimistic by up to 2x. The corpus does
    separate them: the filler reports its own completeness, and repair reports
    what it dropped before measurement.
    """
    quality = delivery_quality()

    assert quality["books"] > 0
    assert quality["min_fill_completeness"] == 1.0
    assert quality["nodes_dropped_to_reading_level"] == 0
    assert quality["degraded_books"] == 0

    page = render(model())

    assert "read it as book length" in page
    assert "pessimistic by up to 2x" not in page


def test_a_mock_report_never_contributes_billed_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `--mock` run prices as zero money, and the guard has to be exercised.

    Without this the only defence against a mock run entering the cost model is
    one unexercised ``if``. A fabricated mock report carrying a large cost left
    the whole suite green before this test existed.
    """
    run = tmp_path / "mock-run"
    run.mkdir()
    (run / "report.json").write_text(
        json.dumps(
            {
                "mock": True,
                "skeletons": ["skeletons/8-11/the-tin-whistle-map.json"],
                "books": [
                    {
                        "vendor": RULED_FILL_LEG,
                        "brief_index": 0,
                        "cost": 99.0,
                        "leaf_words": 10,
                        "complete": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(Path.cwd())

    assert load_fill_books(tmp_path) == []
    assert fill_provenance(tmp_path) == {
        "books": 0,
        "unmetered": 0,
        "analysed": 0,
    }


def test_a_book_without_a_metered_cost_is_counted_out_loud(
    tmp_path: Path,
) -> None:
    """A dropped book's spend is unknown rather than zero, so it is reported.

    The corpus holds one such book. Including it as free understates the total;
    dropping it in silence understates the corpus. Counting it does neither.
    """
    run = tmp_path / "run"
    run.mkdir()
    (run / "report.json").write_text(
        json.dumps(
            {
                "skeletons": ["skeletons/8-11/the-tin-whistle-map.json"],
                "books": [
                    {"vendor": RULED_FILL_LEG, "brief_index": 0, "cost": None},
                    {
                        "vendor": RULED_FILL_LEG,
                        "brief_index": 0,
                        "cost": 1.0,
                        "leaf_words": 100,
                        "complete": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert fill_provenance(tmp_path) == {
        "books": 2,
        "unmetered": 1,
        "analysed": 1,
    }
    assert len(load_fill_books(tmp_path)) == 1


def test_the_comparator_run_never_reaches_the_fill_corpus() -> None:
    """A vendor comparator is committed evidence, but not evidence about price.

    `router-comparison-2026-08-20` is a real metered run, so `mock` is false
    and nothing else in the fill path would hold it back. It put three vendors
    on the same briefs to answer a routing question, and the only books it
    delivered are `anthropic-sonnet-5`'s at roughly 3.50 USD each against
    `deepseek-v4-pro`'s roughly 0.42. Reading it would price a DeepSeek-ruled
    product off two Sonnet books, and the page would show a plausible number
    rather than raising.

    The expectations are computed from the committed tree rather than written
    down here, so this fails when the exclusion is lifted, not when the corpus
    grows.
    """
    runs_root = Path("docs/planning/vendor-comparison/runs")
    present = {path.name for path in runs_root.iterdir() if path.is_dir()}

    assert set(EXCLUDED_FILL_RUNS) <= present, (
        f"EXCLUDED_FILL_RUNS names a run that is gone: "
        f"{sorted(set(EXCLUDED_FILL_RUNS) - present)}"
    )

    excluded_vendors: set[str] = set()
    excluded_books = 0
    for run in sorted(EXCLUDED_FILL_RUNS):
        for report in sorted((runs_root / run).glob("**/report.json")):
            data: dict[str, Any] = json.loads(report.read_text(encoding="utf-8"))
            books: list[dict[str, Any]] = list(data.get("books", []))
            excluded_books += len(books)
            excluded_vendors |= {str(b.get("vendor")) for b in books}

    assert excluded_books, "the excluded run holds no books, so this proves nothing"
    assert excluded_vendors - {RULED_FILL_LEG}, (
        "the excluded run shares every vendor label with the ruled leg, so "
        "vendor labels cannot witness its absence"
    )

    read_vendors = {str(b.get("vendor")) for b in load_fill_books()}

    assert not (excluded_vendors & read_vendors) - {RULED_FILL_LEG}, (
        f"comparator vendors reached the fill corpus: "
        f"{sorted((excluded_vendors & read_vendors) - {RULED_FILL_LEG})}"
    )

    counted = 0
    for report in sorted(runs_root.glob("**/report.json")):
        data = json.loads(report.read_text(encoding="utf-8"))
        if report.relative_to(runs_root).parts[0] in EXCLUDED_FILL_RUNS:
            continue
        if data.get("mock"):
            continue
        counted += len(list(data.get("books", [])))

    assert fill_provenance()["books"] == counted, (
        "the reported book count includes runs the model disowns"
    )
    assert delivery_quality()["books"] == sum(
        1
        for b in load_fill_books()
        if b.get("complete") and int(b.get("leaf_words") or 0) > 0
    )


def test_the_band_table_counts_only_the_ruled_fill_leg(tmp_path: Path) -> None:
    """A second leg's books must not reach a table printed as the ruled cost.

    ``fill_costs`` is keyed by leg and ``fill_by_band`` is not, so the two
    summed the same population only for as long as exactly one leg had fill
    evidence anywhere in the tree. Once a second leg lands, an unscoped band
    table stops reconciling against the leg row beside it, and the gap reads
    as failed spend rather than as another vendor's books.

    Against today's corpus the filter changes nothing, which is why it needs a
    fixture that does contain a second leg.
    """
    run = tmp_path / "two-leg-run"
    run.mkdir()
    (run / "report.json").write_text(
        json.dumps(
            {
                "skeletons": ["skeletons/8-11/the-tin-whistle-map.json"],
                "books": [
                    {
                        "vendor": RULED_FILL_LEG,
                        "brief_index": 0,
                        "cost": 0.5,
                        "leaf_words": 1000,
                        "complete": True,
                    },
                    {
                        "vendor": "anthropic-sonnet-5",
                        "brief_index": 0,
                        "cost": 7.0,
                        "leaf_words": 1000,
                        "complete": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert len(load_fill_books(tmp_path)) == 2, "the fixture lost a book"

    bands = fill_by_band(tmp_path)

    assert list(bands) == ["8-11"]
    assert bands["8-11"]["books"] == 1, "a non-ruled leg reached the band table"
    assert bands["8-11"]["billed_usd"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("other", ["--check", "--write"])
def test_json_cannot_be_combined_with_a_document_mode(other: str) -> None:
    """``--json`` used to win silently over both document modes.

    It sat outside the mutually exclusive group and returned first, so
    ``--json --check`` exited 0 with the document absent entirely and
    ``--json --write`` was a no-op that reported success. A pair of flags that
    cancel each other in silence is the defect ``catalog_census.py`` already
    shipped once.
    """
    with pytest.raises(SystemExit) as excinfo:
        main(["--json", other])

    assert excinfo.value.code == 2


def test_check_and_write_remain_mutually_exclusive() -> None:
    """``--write`` is evaluated first, so losing the group would hide ``--check``."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--check", "--write"])

    assert excinfo.value.code == 2


def test_missing_doc_is_reported_as_missing_not_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A doc that was never generated is a different fault from a stale one.

    Telling a reader "stale" when the file is absent sends them looking for a
    diff that does not exist. Mirrors the sibling census's guarantee.
    """
    monkeypatch.setattr("scripts.unit_cost_model.GENERATED_DOC", tmp_path / "absent.md")

    assert main(["--check"]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_check_names_the_command_that_fixes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failing gate that does not say how to pass costs the reader a search."""
    stale = tmp_path / "unit-cost-model.md"
    stale.write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr("scripts.unit_cost_model.GENERATED_DOC", stale)

    assert main(["--check"]) == 1
    assert "--write" in capsys.readouterr().err


def test_the_model_refuses_to_run_outside_the_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The anchoring guard is the module's own stated invariant, so it is tested.

    ``load_shells`` honours a relative root but ``iter_cells`` reaches
    ``skeleton_match``, whose root is a module-level relative constant with no
    override, so the two halves would describe different catalogs from any
    other directory.
    """
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="repository root"):
        model()
