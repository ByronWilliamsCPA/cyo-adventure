"""Unit tests for run-level cost aggregation (generation.cost).

The module's one non-obvious claim is that cost must be summed per call rather
than over the run's token totals, because a single job mixes models. These
tests pin that, plus the propagation rule that makes the result trustworthy: a
single un-costable call makes the whole run's figure a lower bound.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cyo_adventure.generation.cost import estimate_run_cost
from cyo_adventure.generation.usage import TokenUsage

# Both are real entries in core/pricing.py: output-priced, input-unpriced.
_HAIKU = ("openrouter", "anthropic/claude-haiku-4.5")  # $5.00/Mtok out
_SONNET = ("openrouter", "anthropic/claude-sonnet-4.6")  # $15.00/Mtok out
_FREE = ("ollama", "qwen2.5:14b")  # fully priced at zero


def _call(
    provider_model: tuple[str, str],
    *,
    input_tokens: int | None = 1_000,
    output_tokens: int | None = 100_000,
    duration_ms: int = 500,
) -> TokenUsage:
    """Build one recorded call against a named (provider, model) pair."""
    provider, model = provider_model
    return TokenUsage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )


@pytest.mark.unit
def test_a_run_with_no_calls_costs_nothing_and_is_complete() -> None:
    """Zero calls genuinely cost zero, unlike a call whose price is unknown."""
    estimate = estimate_run_cost([])

    assert estimate.amount_usd == Decimal(0)
    assert estimate.complete is True
    assert estimate.reason == ""


@pytest.mark.unit
def test_each_call_is_costed_at_its_own_models_price() -> None:
    """A mixed-model run bills each call at its own rate, not a blended one.

    This is the property the module exists for. One job routinely runs the
    generation stages on one model and the review stages on another, so a
    figure derived from the run's summed tokens would bill some calls at a
    price they were never charged at. Here the same 100k output tokens cost
    $0.50 on Haiku and $1.50 on Sonnet; any total-based arithmetic would have
    to pick one of those rates for both.
    """
    estimate = estimate_run_cost([_call(_HAIKU), _call(_SONNET)])

    assert estimate.amount_usd == Decimal("2.0")


@pytest.mark.unit
def test_one_unpriced_call_makes_the_whole_run_incomplete() -> None:
    """An un-costable call taints the run's figure, which is one number.

    The priced call still contributes; the persisted figure is therefore a
    lower bound rather than nothing, and ``complete`` is what says so. A reader
    cannot recover per-call detail from a single stored amount, so the flag has
    to be pessimistic for the whole run.
    """
    estimate = estimate_run_cost([_call(_FREE), _call(("acme", "acme-1"))])

    assert estimate.amount_usd == Decimal(0)
    assert estimate.complete is False
    assert "acme/acme-1" in estimate.reason


@pytest.mark.unit
def test_a_fully_priced_run_reports_itself_complete() -> None:
    """A run entirely on priced, counted models carries no caveat."""
    estimate = estimate_run_cost([_call(_FREE), _call(_FREE)])

    assert estimate.amount_usd == Decimal(0)
    assert estimate.complete is True
    assert estimate.reason == ""


@pytest.mark.unit
def test_a_partly_priced_model_still_bills_the_half_it_knows() -> None:
    """The output half is billed even though the input price is missing.

    Every OpenRouter entry is in this state today, so this is the production
    path: the run reports what it can and flags the gap, rather than reporting
    nothing because it cannot report everything.
    """
    estimate = estimate_run_cost([_call(_HAIKU, output_tokens=1_000_000)])

    assert estimate.amount_usd == Decimal("5.00")
    assert estimate.complete is False
    assert "input price unknown" in estimate.reason


@pytest.mark.unit
def test_identical_shortfalls_are_reported_once() -> None:
    """Twenty calls on one unpriced model produce one reason, not twenty."""
    estimate = estimate_run_cost([_call(("acme", "acme-1")) for _ in range(20)])

    assert estimate.reason.count("acme/acme-1") == 1


@pytest.mark.unit
def test_many_distinct_shortfalls_are_summarised_rather_than_listed() -> None:
    """The reason stays readable while still saying that more exist."""
    estimate = estimate_run_cost(
        [_call(("acme", f"acme-{index}")) for index in range(9)]
    )

    assert estimate.reason.endswith("and 5 more")
    assert estimate.complete is False


@pytest.mark.unit
def test_an_unreported_token_count_does_not_silently_contribute_zero() -> None:
    """A priced model whose call reported no tokens still taints the run."""
    estimate = estimate_run_cost([_call(_FREE, output_tokens=None)])

    assert estimate.complete is False
    assert "output tokens not reported" in estimate.reason
