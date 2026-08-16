"""Unit tests for the dated price table and cost arithmetic (core.pricing).

The module exists so a cost figure can never be quietly wrong, and every
distinction it draws is only real if something asserts it. These tests pin the
three that matter: an unpriced model is not a free model, a half-known price
yields a labelled lower bound rather than a total, and the seeded entries are
dated and sourced rather than folklore.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from cyo_adventure.core.pricing import (
    PRICES,
    CostEstimate,
    ModelPrice,
    estimate_cost,
    price_for,
)


def _price(
    *,
    input_usd_per_mtok: Decimal | None = Decimal("3.00"),
    output_usd_per_mtok: Decimal | None = Decimal("15.00"),
) -> ModelPrice:
    """Build a ModelPrice with defaults for whichever half is under test."""
    return ModelPrice(
        input_usd_per_mtok=input_usd_per_mtok,
        output_usd_per_mtok=output_usd_per_mtok,
        as_of=date(2026, 8, 11),
        source="test fixture",
    )


@pytest.mark.unit
def test_a_fully_priced_call_costs_both_halves() -> None:
    """Both halves contribute, and the result reports itself complete."""
    estimate = estimate_cost(_price(), input_tokens=1_000_000, output_tokens=100_000)

    # 1 Mtok in at $3 plus 0.1 Mtok out at $15.
    assert estimate.amount_usd == Decimal("4.50")
    assert estimate.complete is True
    assert estimate.reason == ""


@pytest.mark.unit
def test_unpriced_model_is_incomplete_and_not_free() -> None:
    """A model with no table entry yields zero flagged as unknown, not as free.

    This is the distinction the whole module is built around. Zero is the only
    honest amount when nothing is known, so the amount alone cannot carry the
    difference; ``complete`` is what separates "we know it cost nothing" from
    "we do not know what it cost".
    """
    estimate = estimate_cost(None, input_tokens=5_000, output_tokens=5_000)

    assert estimate.amount_usd == Decimal(0)
    assert estimate.complete is False
    assert "no recorded price" in estimate.reason


@pytest.mark.unit
def test_half_priced_entry_yields_a_lower_bound() -> None:
    """A known output price still bills output while flagging the input gap.

    Every seeded entry is in exactly this state today, so the behaviour under
    test is the behaviour production gets, not a hypothetical branch.
    """
    estimate = estimate_cost(
        _price(input_usd_per_mtok=None),
        input_tokens=1_000_000,
        output_tokens=200_000,
    )

    # The output half is billed in full; the input half contributes nothing.
    assert estimate.amount_usd == Decimal("3.0")
    assert estimate.complete is False
    assert estimate.reason == "input price unknown"


@pytest.mark.unit
def test_an_unreported_token_count_is_incomplete_rather_than_zero() -> None:
    """A missing count is a gap in the measurement, not a zero-token call."""
    estimate = estimate_cost(_price(), input_tokens=None, output_tokens=100_000)

    assert estimate.amount_usd == Decimal("1.5")
    assert estimate.complete is False
    assert estimate.reason == "input tokens not reported"


@pytest.mark.unit
def test_both_halves_missing_are_both_reported() -> None:
    """Two gaps produce two reasons, so the log names each one."""
    estimate = estimate_cost(
        _price(input_usd_per_mtok=None),
        input_tokens=1_000,
        output_tokens=None,
    )

    assert estimate.amount_usd == Decimal(0)
    assert estimate.complete is False
    assert estimate.reason == "input price unknown; output tokens not reported"


@pytest.mark.unit
def test_a_genuinely_free_model_is_complete_at_zero() -> None:
    """A self-hosted zero price is a known cost, unlike an absent entry.

    Contrast with ``test_unpriced_model_is_incomplete_and_not_free``: the same
    amount, the opposite epistemic status.
    """
    free = _price(input_usd_per_mtok=Decimal(0), output_usd_per_mtok=Decimal(0))

    estimate = estimate_cost(free, input_tokens=10_000, output_tokens=10_000)

    assert estimate.amount_usd == Decimal(0)
    assert estimate.complete is True


@pytest.mark.unit
def test_cost_arithmetic_stays_exact_at_small_token_counts() -> None:
    """Per-call amounts are tiny, so binary floating point would round them away.

    A single call costed in float can lose the sub-cent precision that only
    matters once thousands of calls are summed, which is exactly when the error
    is hardest to attribute. Decimal keeps the fraction exact.
    """
    estimate = estimate_cost(
        _price(input_usd_per_mtok=Decimal("3.00")),
        input_tokens=1,
        output_tokens=None,
    )

    assert estimate.amount_usd == Decimal("0.000003")
    assert isinstance(estimate.amount_usd, Decimal)


@pytest.mark.unit
def test_price_for_returns_none_for_an_unknown_pair() -> None:
    """An unrecorded pair returns None so the caller must handle the gap."""
    assert price_for("openrouter", "no/such-model") is None


@pytest.mark.unit
def test_price_for_keys_on_the_routing_provider_not_the_vendor() -> None:
    """An OpenRouter-routed Anthropic model keys off openrouter, as billed."""
    assert price_for("openrouter", "anthropic/claude-haiku-4.5") is not None
    assert price_for("anthropic", "anthropic/claude-haiku-4.5") is None


@pytest.mark.unit
def test_every_seeded_entry_is_dated_and_sourced() -> None:
    """A price with no date or provenance cannot be audited or re-checked."""
    assert PRICES, "the table must not be empty; an empty table prices nothing"
    for key, entry in PRICES.items():
        assert isinstance(entry.as_of, date), f"{key} has no usable as_of date"
        assert entry.source.strip(), f"{key} cites no source"


@pytest.mark.unit
def test_no_seeded_price_is_negative() -> None:
    """A negative price would credit the account for spending money."""
    for key, entry in PRICES.items():
        for half in (entry.input_usd_per_mtok, entry.output_usd_per_mtok):
            if half is not None:
                assert half >= 0, f"{key} carries a negative price"


@pytest.mark.unit
def test_every_entry_is_fully_priced() -> None:
    """Was the inverse assertion until 2026-08-14, and it did its job.

    This test used to pin the *gap*: it named the three phase-2b entries with
    no input price and said that filling them in would fail this test and point
    at what changed. That is what happened (`UW-C239`), so the assertion is now
    the one the module always wanted. Every entry carries both halves, read live
    from the vendor by `scripts/refresh_pricing.py`.

    It stays an exhaustive check rather than a spot check, because the way this
    gap reopens is a model added to the allowlist and not to the price table:
    its calls then price as unknown and every job touching it reports
    incomplete, exactly as before.
    """
    unpriced = {
        key
        for key, entry in PRICES.items()
        if entry.input_usd_per_mtok is None or entry.output_usd_per_mtok is None
    }

    assert unpriced == set()
    assert PRICES[("openrouter", "anthropic/claude-haiku-4.5")].fully_priced
    assert PRICES[("ollama", "qwen2.5:14b")].fully_priced


@pytest.mark.unit
def test_price_and_estimate_are_immutable() -> None:
    """Neither a recorded price nor a computed estimate may be edited in place."""
    price = _price()
    # Built outside the block so the raises assertion has exactly one
    # invocation to attribute the failure to (S5778).
    replacement = Decimal("1.00")
    with pytest.raises(FrozenInstanceError):
        setattr(price, "input_usd_per_mtok", replacement)  # noqa: B010  # frozen: must go via setattr

    estimate = CostEstimate(amount_usd=Decimal(0), complete=True)
    with pytest.raises(FrozenInstanceError):
        setattr(estimate, "complete", False)  # noqa: B010  # frozen: must go via setattr
