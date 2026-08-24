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
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.pricing import PRICES
from cyo_adventure.validator.band_profile import offered_cells
from scripts.unit_cost_model import (
    GENERATED_DOC,
    LEG_MODELS,
    PRICE_POINTS_USD,
    cell_weights,
    leg_costs,
    main,
    model,
    render,
)

if TYPE_CHECKING:
    from pathlib import Path

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


def test_measured_cells_are_a_strict_subset_of_the_offered_grid() -> None:
    """The evidence covers a fraction of the grid, and the model says which.

    This is the finding step 4 turns on. Reporting a per-book cost for all 18
    offered cells while only two carry token records would be the exact defect
    the workstream plan exists to catch, so the measured set is computed and
    published rather than assumed to be the whole grid.
    """
    costs = leg_costs()
    measured = {c for leg in costs.values() for c in leg["cells"]}

    assert measured, "no committed run record carries token counts"
    assert measured < offered_cells(), "measured coverage is not a strict subset"


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
