"""Unit tests for run-level cost aggregation (generation.cost).

The module's one non-obvious claim is that cost must be summed per call rather
than over the run's token totals, because a single job mixes models. These
tests pin that, plus the propagation rule that makes the result trustworthy: a
single un-costable call makes the whole run's figure a lower bound.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cyo_adventure.generation.cost import estimate_run_cost, fit_cost_to_column
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


@pytest.mark.unit
def test_an_amount_past_the_column_maximum_is_capped_and_incomplete() -> None:
    """A cost too wide for the column is capped here, never at COMMIT.

    Postgres raises ``numeric field overflow`` on an out-of-range integer
    part, and raises it at commit rather than at assignment. Both writers of
    ``cost_usd`` commit, including the one the interrupt guard uses to record
    a failure, so an uncapped amount would displace the failure being
    recorded and strand the job in ``queued``/``running``. Capping in memory
    is what makes that sequence unreachable.

    A capped figure is a lower bound on real spend, which is exactly what
    ``cost_complete`` already means, so the flag carries it rather than a
    second signal being invented.
    """
    amount, capped = fit_cost_to_column(Decimal(1_000_000))

    assert capped is True
    assert amount == Decimal("999999.999999")


@pytest.mark.unit
def test_rounding_to_scale_is_not_capping() -> None:
    """Sub-millionth rounding moves the figure without making it a bound.

    A 3-token call at $1.25/Mtok is $0.00000375: eight fractional digits,
    stored in six. Rounding that away is immaterial and must not flip
    ``cost_complete``, or nearly every real run would report itself
    incomplete and the flag would stop meaning "the price table had a gap".
    """
    amount, capped = fit_cost_to_column(Decimal("0.00000375"))

    assert capped is False
    assert amount == Decimal("0.000004")


@pytest.mark.unit
def test_the_returned_amount_is_already_at_the_columns_scale() -> None:
    """What is held in memory is what Postgres stores, digit for digit.

    Rounding explicitly rather than letting the driver do it silently is what
    lets a caller compare a stamped value against the estimate it came from
    without an unexplained difference appearing at the sixth decimal.
    """
    amount, capped = fit_cost_to_column(Decimal("2.5"))

    assert capped is False
    assert amount == Decimal("2.5")
    assert amount.as_tuple().exponent == -6
