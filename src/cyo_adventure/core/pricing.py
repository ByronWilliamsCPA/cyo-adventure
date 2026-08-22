"""Dated per-(provider, model) token prices and the cost they imply.

A cost figure that is quietly wrong is worse than no cost figure, so this
module carries the same discipline
:mod:`cyo_adventure.generation.usage` applies to token counts, one layer up:

* A price is ``Decimal``, never ``float``. Money is never binary floating
  point, and these values are summed across thousands of calls.
* Each half of a price is ``Decimal | None`` independently. ``None`` means the
  price is not known, and is never interchangeable with ``0``: an unpriced
  model must not look free.
* Every entry is **dated** and cites its ``source``. A price is a fact about a
  vendor on a day, so a cost recomputed months later against a changed price
  list is auditable rather than mysteriously different.
* :class:`CostEstimate` reports ``complete``. When either half of the price or
  either half of the token count is missing, the amount is a **lower bound**
  and says so, rather than presenting a partial sum as a total.

**The input-price gap is closed (2026-08-14, `UW-C239`).** Every OpenRouter
entry below now carries both halves, read live from the vendor's model list by
``scripts/refresh_pricing.py`` and stamped with the date it was read. Before
that, the only recorded source (the phase-2b analysis) noted output prices and
no input prices, so every cloud entry had ``input_usd_per_mtok=None``, every
estimate reported ``complete=False``, and the per-job accounting merged with
#701 wrote ``cost_complete = false`` on every row, which made the migration's
own advice to filter on that column select nothing. Two measurement runs on
2026-08-14 printed ``$0.0000`` for work that cost $0.85 and $6.29 against the
provider's balance.

Refreshing is now a command rather than an act of archaeology::

    uv run python scripts/refresh_pricing.py

A model promoted out of a vendor comparison must be added to that script's
list at the same time it is added to the allowlist. Otherwise its calls price
as unknown and every job that touches it reports incomplete again.

#CRITICAL: payment/financial: these prices are not read from a vendor API.
They are transcribed from a dated project document, and a vendor price change
makes every later estimate silently wrong in whichever direction the change
went. Nothing here validates them against reality.
#VERIFY: before any cost figure derived from this table is used for billing,
budgeting, or a customer-visible number, re-check each entry against the
vendor's live pricing page and update ``as_of``. Treat an entry older than one
quarter as unverified. Fill the ``input_usd_per_mtok`` gaps at the same time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "PRICES",
    "CostEstimate",
    "ModelPrice",
    "estimate_cost",
    "price_for",
]

_TOKENS_PER_MTOK = Decimal(1_000_000)

# Where the seeded numbers come from. Named once so every entry cites the same
# string and a future edit cannot leave half the table pointing at a stale doc.
_PHASE_2B = "docs/planning/yield-results/phase-2b-2026-06-22-analysis.md"
_OPENROUTER_API = "https://openrouter.ai/api/v1/models (scripts/refresh_pricing.py)"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """What one vendor charged for one model, on one date.

    Attributes:
        input_usd_per_mtok: USD per million prompt tokens, or ``None`` when
            the price is not known. Not interchangeable with ``Decimal(0)``,
            which would assert the vendor charges nothing for input.
        output_usd_per_mtok: USD per million completion tokens, or ``None``
            when not known.
        as_of: The date this price was recorded. A price is a fact about a
            day, not a constant.
        source: Where the number came from, so a wrong entry can be traced to
            what it was read from rather than argued about.
        note: Anything a reader needs in order not to misread the entry.
    """

    input_usd_per_mtok: Decimal | None
    output_usd_per_mtok: Decimal | None
    as_of: date
    source: str
    note: str = ""

    @property
    def fully_priced(self) -> bool:
        """Whether both halves of this price are known.

        Returns:
            ``True`` only when neither half is ``None``. A half-known price
            can still produce a lower bound, never a total.
        """
        return (
            self.input_usd_per_mtok is not None and self.output_usd_per_mtok is not None
        )


# Keyed by (provider, model) exactly as TokenUsage reports them: the provider
# is the adapter's short name and the model is the id the call was issued
# against, so an OpenRouter-routed Anthropic model keys off "openrouter" and
# its slash-qualified id, not off "anthropic".
_PRICES: dict[tuple[str, str], ModelPrice] = {
    ("openrouter", "anthropic/claude-haiku-4.5"): ModelPrice(
        input_usd_per_mtok=Decimal(1),
        output_usd_per_mtok=Decimal(5),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "anthropic/claude-sonnet-4.6"): ModelPrice(
        input_usd_per_mtok=Decimal(3),
        output_usd_per_mtok=Decimal(15),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "anthropic/claude-sonnet-5"): ModelPrice(
        input_usd_per_mtok=Decimal(2),
        output_usd_per_mtok=Decimal(10),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "google/gemini-2.5-flash"): ModelPrice(
        input_usd_per_mtok=Decimal("0.3"),
        output_usd_per_mtok=Decimal("2.5"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "google/gemini-3-flash-preview"): ModelPrice(
        input_usd_per_mtok=Decimal("0.5"),
        output_usd_per_mtok=Decimal(3),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "google/gemini-3.1-pro-preview"): ModelPrice(
        input_usd_per_mtok=Decimal(2),
        output_usd_per_mtok=Decimal(12),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "openai/gpt-5.6-sol"): ModelPrice(
        input_usd_per_mtok=Decimal(5),
        output_usd_per_mtok=Decimal(30),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "x-ai/grok-4.6"): ModelPrice(
        input_usd_per_mtok=Decimal(2),
        output_usd_per_mtok=Decimal(6),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "deepseek/deepseek-v4-flash"): ModelPrice(
        input_usd_per_mtok=Decimal("0.14"),
        output_usd_per_mtok=Decimal("0.28"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "qwen/qwen3-32b"): ModelPrice(
        input_usd_per_mtok=Decimal("0.08"),
        output_usd_per_mtok=Decimal("0.28"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"): ModelPrice(
        input_usd_per_mtok=Decimal("0.1"),
        output_usd_per_mtok=Decimal("0.32"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "z-ai/glm-5"): ModelPrice(
        input_usd_per_mtok=Decimal("0.95"),
        output_usd_per_mtok=Decimal("2.55"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "~deepseek/deepseek-v4-flash-latest"): ModelPrice(
        input_usd_per_mtok=Decimal("0.0798"),
        output_usd_per_mtok=Decimal("0.1596"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "deepseek/deepseek-v4-flash-0731"): ModelPrice(
        input_usd_per_mtok=Decimal("0.14"),
        output_usd_per_mtok=Decimal("0.28"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    # #ASSUME: payment: this row is the price of the PINNED endpoint
    # (`azure/us`), not of the slug's default route. OpenRouter serves this one
    # slug from 18 endpoints priced from $0.66 to $1.91 input, and this table is
    # keyed on (provider, model) so it can hold exactly one of them. Recording
    # the default route ($1.44/$2.88, which is `novita/fp8`) would UNDERstate a
    # pinned run's cost by about a quarter (1.44/1.91 = 0.754, 2.88/3.83 =
    # 0.752), or equivalently the pinned endpoint costs about a third MORE than
    # the default route; a comparison that exists to price a vendor should not
    # be wrong about the endpoint it actually paid.
    #
    # Endpoint reachability was PROBED, not assumed, on 2026-08-20, because three
    # of the candidates fail in two different ways that both look like a bad slug:
    # `alibaba/fp8`, `baidu/fp8` and first-party `deepseek` return 404 "no
    # endpoints available matching your guardrail restrictions and data policy",
    # and `coreweave/fp8` and `parasail/fp8`, the only two endpoints declaring a
    # 1,048,576 output ceiling, returned a persistent 429. `azure/us` is the
    # reachable pin whose hosting matches the posture the account's own data
    # policy already expresses by blocking the three above.
    # #VERIFY: test_deepseek_v4_pro_fixture_carries_the_priced_pin asserts the
    # committed vendor fixture (this row's only caller) pins
    # `provider_order: ["azure/us"]` and that this row's note still names that
    # endpoint; an unpinned run is mispriced here AND exposed to the
    # per-endpoint output-ceiling spread recorded in
    # `docs/planning/vendor-comparison/vendors-deepseek-v4-pro.json`
    # (`_pinning_rationale`): declared ceilings run from 16,384 to 1,048,576
    # for this one slug. `MODEL_OUTPUT_CAPS` is NOT that record and must not be
    # read as it: it is keyed per slug and holds a single 393,216 for this
    # model, and its inability to express the spread is exactly why pinning is
    # a correctness requirement here rather than reproducibility hygiene.
    #
    # #ASSUME: payment: this row is deliberately ABSENT from
    # `scripts/refresh_pricing.py::_WANTED`, whose own comment otherwise
    # requires every priced OpenRouter model to be listed there. That script
    # reads `/api/v1/models`, which reports the slug's DEFAULT route, so a
    # routine price refresh would silently overwrite this pinned row with
    # $1.44/$2.88 and reintroduce the ~25 percent understatement above. Re-price
    # this row by hand from `/models/deepseek/deepseek-v4-pro/endpoints`,
    # together with the fixture's pin.
    # #VERIFY: test_deepseek_v4_pro_fixture_carries_the_priced_pin (same test:
    # it binds the fixture pin to this row, which is what a refresh would break).
    ("openrouter", "deepseek/deepseek-v4-pro"): ModelPrice(
        input_usd_per_mtok=Decimal("1.91"),
        output_usd_per_mtok=Decimal("3.83"),
        as_of=date(2026, 8, 20),
        source=_OPENROUTER_API,
        note=(
            "read live from https://openrouter.ai/api/v1/models/"
            "deepseek/deepseek-v4-pro/endpoints; price of the azure/us "
            "endpoint, which is the pin this project uses for this model"
        ),
    ),
    # Pinned-endpoint price, like the v4-pro row above: this run enablement row
    # prices the `novita/fp8` endpoint, the pin the 2026-08-21 chunked-path leg
    # uses (`docs/planning/vendor-comparison/vendors-deepseek-v32.json`, whose
    # `provider_order` is `["novita/fp8"]` and whose `_price_per_mtok` records
    # this row's exact `0.269 / 0.40`).
    #
    # This comment named `digitalocean` until 2026-08-22 while the `note=`
    # below and the fixture both said `novita/fp8`, so the row contradicted
    # itself about the endpoint it priced under a payment marker. The fixture
    # is the evidence and it settles it: digitalocean was the take-3 pin and
    # the pin MOVED. Probed 2026-08-21: digitalocean, novita/fp8 and
    # siliconflow/fp8 return 200; `atlas-cloud/fp8` returns 404 "no endpoints
    # available matching your guardrail restrictions and data policy".
    # DigitalOcean then passed a 512-token pre-flight and returned short
    # malformed output to every large chunked batch ask, so take 4 pinned
    # novita/fp8, which served the identical prompt correctly.
    #
    # Novita declares exactly 65,536 max_completion_tokens, which is the slug's
    # `MODEL_OUTPUT_CAPS` row to the token and therefore carries NO headroom
    # above the resolved cap. That is acceptable, and the reason is the
    # `_FEASIBILITY_MARGIN`, not the endpoint: chunked batch asks are held to
    # 0.8 of the cap, so the largest ask this pin can receive is 52,428 against
    # a real 65,536 ceiling. The earlier justification here, digitalocean's
    # 128,000 ceiling sitting above the cap, no longer applies to the pinned
    # endpoint and must not be reused for it.
    # #ASSUME: payment: deliberately absent from
    # `scripts/refresh_pricing.py::_WANTED` for the same reason as the v4-pro
    # row: a refresh reads the slug's default route and would overwrite this
    # pinned price. Re-price by hand from
    # /models/deepseek/deepseek-v3.2/endpoints together with the fixture's pin.
    # #VERIFY: test_deepseek_v3_2_fixture_carries_the_priced_pin asserts the
    # committed fixture still pins `novita/fp8`, that this row's note still
    # names that endpoint, and that the fixture's recorded `_price_per_mtok`
    # still matches this row's two halves. A prose "re-run the probe" marker is
    # what let the endpoint name drift here in the first place; the v4-pro row
    # above binds its pin to a test and this row now does the same.
    ("openrouter", "deepseek/deepseek-v3.2"): ModelPrice(
        input_usd_per_mtok=Decimal("0.269"),
        output_usd_per_mtok=Decimal("0.40"),
        as_of=date(2026, 8, 21),
        source=_OPENROUTER_API,
        note=(
            "read live from https://openrouter.ai/api/v1/models/"
            "deepseek/deepseek-v3.2/endpoints; price of the novita/fp8 "
            "endpoint, the pin the 2026-08-21 chunked-path leg uses after "
            "digitalocean passed its 512-token probe and then failed every "
            "large chunked batch ask with short malformed output (take 3)"
        ),
    ),
    ("openrouter", "qwen/qwen3.6-27b"): ModelPrice(
        input_usd_per_mtok=Decimal("0.6"),
        output_usd_per_mtok=Decimal("3.6"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("openrouter", "qwen/qwen3.5-27b"): ModelPrice(
        input_usd_per_mtok=Decimal("0.195"),
        output_usd_per_mtok=Decimal("1.56"),
        as_of=date(2026, 8, 14),
        source=_OPENROUTER_API,
        note="read live from https://openrouter.ai/api/v1/models",
    ),
    ("ollama", "qwen2.5:14b"): ModelPrice(
        input_usd_per_mtok=Decimal(0),
        output_usd_per_mtok=Decimal(0),
        as_of=date(2026, 8, 11),
        source="self-hosted; no vendor bills these tokens",
        note=(
            "zero VENDOR cost, not zero cost. Hardware, power and the operator's "
            "time are real and are not modelled here, so an all-Ollama run "
            "reporting $0.00 means 'nothing was billed', not 'this was free'"
        ),
    ),
}

# Exported read-only. Every entry is a dated, sourced fact that must stay
# auditable against this file, so a runtime `PRICES[key] = ...` by any importer
# would leave a live price with no trace in the source and no `as_of`/`source`
# to check it against. The proxy makes the table changeable only by editing
# the literal above.
PRICES: Mapping[tuple[str, str], ModelPrice] = MappingProxyType(_PRICES)


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """What a set of token counts cost, and how much of that is actually known.

    Attributes:
        amount_usd: The summed cost of every priced, counted half. When
            ``complete`` is ``False`` this is a **lower bound**: it omits the
            halves that had no price or no count, and omitting them can only
            reduce the figure.
        complete: ``True`` only when every half of both the price and the
            token counts was known. ``False`` means the amount understates the
            true cost by an unknown margin.
        reason: Why the estimate is incomplete, for a log line or an operator
            reading a dashboard. Empty when ``complete``.
    """

    amount_usd: Decimal
    complete: bool
    reason: str = ""


def price_for(provider: str, model: str) -> ModelPrice | None:
    """Look up the recorded price for one provider and model.

    Args:
        provider: The adapter's short name, as ``TokenUsage.provider`` reports
            it (for a fallback chain, the leg that answered).
        model: The model id the call was issued against.

    Returns:
        The recorded price, or ``None`` when this pair has no entry. ``None``
        means unknown; callers must not substitute zero.
    """
    return PRICES.get((provider, model))


def estimate_cost(
    price: ModelPrice | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> CostEstimate:
    """Cost the given token counts against the given price.

    Each half is costed independently, so a call with a known output price and
    an unknown input price still contributes what is known rather than
    contributing nothing. Every such shortfall is recorded in ``complete`` and
    ``reason``, so the result can never be mistaken for a full cost.

    Args:
        price: The recorded price, or ``None`` when the model has no entry.
        input_tokens: Prompt tokens, or ``None`` when the backend reported
            none.
        output_tokens: Completion tokens, or ``None`` when the backend
            reported none.

    Returns:
        The cost of every priced and counted half, flagged complete only when
        nothing was missing.
    """
    # #CRITICAL: payment/financial: an unknown price and an unknown token
    # count must both reduce `complete`, never silently contribute zero to a
    # sum that a reader would take as a total. The `missing` list is the
    # mechanism: every skipped half appends to it, so `complete` is derived
    # from what actually happened rather than asserted separately and left to
    # drift from the arithmetic beside it.
    # #VERIFY: test_unpriced_model_is_incomplete_and_not_free,
    # test_half_priced_entry_yields_a_lower_bound.
    if price is None:
        return CostEstimate(
            amount_usd=Decimal(0),
            complete=False,
            reason="no recorded price for this provider and model",
        )

    amount = Decimal(0)
    missing: list[str] = []

    for label, per_mtok, tokens in (
        ("input", price.input_usd_per_mtok, input_tokens),
        ("output", price.output_usd_per_mtok, output_tokens),
    ):
        if per_mtok is None:
            missing.append(f"{label} price unknown")
            continue
        if tokens is None:
            missing.append(f"{label} tokens not reported")
            continue
        amount += (Decimal(tokens) * per_mtok) / _TOKENS_PER_MTOK

    return CostEstimate(
        amount_usd=amount,
        complete=not missing,
        reason="; ".join(missing),
    )
