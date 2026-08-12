"""Run-level cost aggregation over a usage ledger.

Sits between :mod:`cyo_adventure.generation.usage` (what the calls consumed)
and :mod:`cyo_adventure.core.pricing` (what a token costs), and belongs to
neither: ``usage`` stays free of money and ``core.pricing`` stays free of any
import from ``generation``.

Cost is summed **per call**, never over the run's token totals. One job routinely
mixes models: the generation stages run on the configured generation model while
the review stages run on the review model, and a fallback chain can move a
single call to a different leg mid-run. Multiplying a run's summed tokens by any
one price would therefore bill some calls at another model's rate, and the error
grows with exactly the mixed-model runs the pipeline is built around.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from cyo_adventure.core.pricing import CostEstimate, estimate_cost, price_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyo_adventure.generation.usage import TokenUsage

__all__ = ["estimate_run_cost"]

# How many distinct shortfalls a run's `reason` names before it summarises. A
# run makes tens of calls, and an unpriced model produces one identical reason
# per call; the cap keeps the string readable without hiding that more exist.
_MAX_REASONS = 4


def estimate_run_cost(calls: Iterable[TokenUsage]) -> CostEstimate:
    """Cost every recorded call at its own model's price and sum the results.

    Args:
        calls: The run's recorded calls, typically
            :attr:`~cyo_adventure.generation.usage.UsageLedger.calls`.

    Returns:
        The summed cost, marked ``complete`` only when every call was fully
        priced and fully counted. An incomplete result is a lower bound: the
        halves it could not cost contribute nothing, and omitting a cost can
        only push the total down.
    """
    # #CRITICAL: payment/financial: a single unpriced or uncounted call must
    # make the WHOLE run incomplete. `complete` is ANDed across calls rather
    # than reported per call and lost in the sum, because the persisted figure
    # is one number and a reader cannot recover which calls it under-counted.
    # #VERIFY: test_one_unpriced_call_makes_the_whole_run_incomplete.
    total = Decimal(0)
    complete = True
    reasons: list[str] = []

    for call in calls:
        estimate = estimate_cost(
            price_for(call.provider, call.model),
            call.input_tokens,
            call.output_tokens,
        )
        total += estimate.amount_usd
        if not estimate.complete:
            complete = False
            detail = f"{call.provider}/{call.model}: {estimate.reason}"
            if detail not in reasons:
                reasons.append(detail)

    if len(reasons) > _MAX_REASONS:
        dropped = len(reasons) - _MAX_REASONS
        reasons = [*reasons[:_MAX_REASONS], f"and {dropped} more"]

    return CostEstimate(
        amount_usd=total,
        complete=complete,
        reason="; ".join(reasons),
    )
