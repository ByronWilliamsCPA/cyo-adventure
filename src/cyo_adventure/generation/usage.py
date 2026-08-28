"""Token-usage accounting for LLM provider calls.

Every backend adapter returns a :class:`Completion` rather than a bare string,
so the usage a provider reports survives the call instead of being discarded at
the return type. :class:`UsageLedger` accumulates those records for one
pipeline run and :class:`UsageTotals` is the serializable snapshot the worker
persists.

Three properties of this module exist because a cost figure that is quietly
wrong is worse than no cost figure at all:

* ``input_tokens``/``output_tokens`` are ``int | None``. ``None`` means the
  backend did not report usage; ``0`` means it reported zero. Collapsing those
  two into ``0`` would make an un-instrumented backend look free.
* :class:`UsageLedger` counts the calls whose usage was unknown
  (``unknown_calls``), so any total derived from it can say whether it is
  complete or a lower bound.
* :attr:`UsageTotals.complete` is that answer, computed once, rather than left
  for each consumer to re-derive from the counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

__all__ = [
    "EMPTY_TOTALS",
    "Completion",
    "TokenUsage",
    "UsageLedger",
    "UsageTotals",
    "coerce_token_count",
]


def coerce_token_count(value: object) -> int | None:
    """Narrow an untrusted token count from a provider response to ``int | None``.

    Every adapter reads its counts out of a value the backend controls: decoded
    JSON for the HTTP adapters, and for the Anthropic SDK a model built by
    lenient construction rather than strict validation, so a declared ``int``
    field can still hold ``None`` or a string at runtime. Anything that is not
    a non-negative plain integer becomes ``None`` (not reported) rather than a
    number that would silently corrupt a cost total.

    ``bool`` is rejected explicitly: it is an ``int`` subclass, so ``True``
    would otherwise be accepted and counted as one token.

    Args:
        value: A candidate token count of untrusted type.

    Returns:
        The value as ``int`` when it is a non-negative, non-``bool`` integer,
        else ``None``.
    """
    # #CRITICAL: data-integrity: this is the only boundary between a
    # backend-controlled JSON value and a persisted dollar figure, and the
    # None-versus-0 choice here is what makes the difference legible
    # downstream. Coercing a malformed count to 0 would report the run as
    # fully counted at a lower total, which reads as a cheap job rather than
    # an uninstrumented one; returning None makes `cost_complete` false and
    # says so. `bool` is rejected before the `int` check because it is an
    # `int` subclass, so a `True` would otherwise be billed as one token.
    # #VERIFY: tests/unit/test_usage.py::
    # test_coerce_rejects_bool_despite_int_subclassing and
    # ::test_coerce_rejects_non_integer_and_negative_values.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What one provider call consumed.

    Attributes:
        provider: The backend that served the call, as a bare backend name
            (``"anthropic"``, ``"openrouter"``, ``"modal"``). Historical rows
            may also carry ``"ollama"``, retired as a live backend but still
            priced in ``core/pricing.py`` so past runs stay costable.
            It never embeds the model: this string is half of the
            ``(provider, model)`` key ``core.pricing.PRICES`` is looked up by,
            so a combined label would miss every price entry and silently
            make the call unpriced. For a fallback chain this is the leg that
            actually answered, not the chain, because the leg is what was
            billed.
        model: The model id the call was issued against, the other half of
            that key.
        input_tokens: Prompt tokens the backend reported, or ``None`` when it
            reported none. Not interchangeable with ``0``.
        output_tokens: Completion tokens the backend reported, or ``None``
            when it reported none.
        duration_ms: Wall-clock milliseconds for the call, measured around the
            adapter's network work. Always known, since it is measured here
            rather than reported by the backend.
        reasoning_tokens: Hidden reasoning tokens the backend reported, a
            subset of ``output_tokens`` rather than an addition to it, or
            ``None`` when the backend reported none. Billed at the output rate
            and producing no prose, which is why cost per delivered book spans
            36x across legs asked for the identical book while the prose written
            spans 1.36x (`AL-332`). Reported so reasoning share is observable in
            production rather than reconstructed from a billing probe, and so a
            leg can be selected on it. A provider that emits reasoning while
            reporting zero has been observed, so a `0` here is the backend's
            claim, not a measurement.
    """

    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    reasoning_tokens: int | None = None

    @property
    def is_known(self) -> bool:
        """Whether the backend reported both token counts.

        Returns:
            ``True`` only when neither count is ``None``. A call missing
            either half cannot contribute a defensible cost.
        """
        return self.input_tokens is not None and self.output_tokens is not None


@dataclass(frozen=True, slots=True)
class Completion:
    """A provider response plus what it cost to obtain.

    Attributes:
        text: The completion text, already stripped of code fences by the
            adapter. This is the value every pre-instrumentation caller used.
        usage: What the call consumed.
        finish_reason: Why the backend stopped, verbatim as reported
            (``"stop"``, ``"length"``, ``"error"``, ...), or ``None`` when it
            reported none. The distinction that matters is ``"length"``: a
            completion truncated at the cap and an endpoint that returned
            nothing both arrive as empty content, they want opposite responses,
            and without this field no retry policy could tell them apart. The
            comparison harness retried a budget failure three times at roughly
            eleven minutes and fifty cents an attempt (`AL-329`).
        vendor_cost_usd: What the vendor itself said this single call cost, or
            ``None`` when the backend reported no cost. This is an OBSERVED
            number, distinct in kind from the estimate
            ``core.pricing.estimate_cost`` derives from a hand-transcribed,
            dated price table whose own docstring warns that a vendor price
            change makes every later estimate silently wrong. Only backends
            that report a per-call cost and are asked to do so populate it, so
            ``None`` means "not reported", never "free"; the same discipline
            ``input_tokens`` carries. ``Decimal``, never ``float``, because it
            is money and it is summed across calls.
    """

    text: str
    usage: TokenUsage
    finish_reason: str | None = None
    vendor_cost_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class UsageTotals:
    """The serializable aggregate for one pipeline run.

    Attributes:
        call_count: Every provider call made, including ones with unknown
            usage.
        unknown_calls: How many of ``call_count`` reported no usage. Zero
            means every call is accounted for.
        input_tokens: Summed prompt tokens across the calls that reported
            them.
        output_tokens: Summed completion tokens across the calls that
            reported them.
        duration_ms: Summed wall-clock provider time. This is call time, not
            job time: it excludes gate, validator and database work, and for
            concurrent calls it over-counts against the wall clock.
    """

    call_count: int
    unknown_calls: int
    input_tokens: int
    output_tokens: int
    duration_ms: int

    @property
    def complete(self) -> bool:
        """Whether every call in this run reported its usage.

        Returns:
            ``True`` when no call was unknown. When ``False``, the token and
            cost figures derived from this snapshot are lower bounds and must
            be reported as such.
        """
        return self.unknown_calls == 0

    def to_dict(self) -> dict[str, object]:
        """Return the snapshot as a JSON-serializable mapping.

        ``complete`` is included so a stored record answers the
        lower-bound question without the reader recomputing it.

        Returns:
            A mapping of every field plus ``complete``.
        """
        return {
            "call_count": self.call_count,
            "unknown_calls": self.unknown_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_ms": self.duration_ms,
            "complete": self.complete,
        }


@dataclass
class UsageLedger:
    """Run-scoped accumulator for provider calls.

    Mutable and threaded through a pipeline run the same way
    ``orchestrator._RepairContext.stage_log`` is: created once per run by the
    entry point, appended to in place by each stage, and snapshotted at the
    end. It is deliberately not module-level state, because the worker runs
    jobs concurrently and a shared accumulator would attribute one job's cost
    to another.

    Attributes:
        calls: Every recorded call, in call order. Retained rather than folded
            immediately so a per-call event log can be written from the same
            ledger the aggregate comes from.
    """

    calls: list[TokenUsage] = field(default_factory=list)

    def record(self, usage: TokenUsage) -> None:
        """Append one call's usage.

        Args:
            usage: What the call consumed.
        """
        self.calls.append(usage)

    def snapshot(self) -> UsageTotals:
        """Fold the recorded calls into a serializable aggregate.

        Calls that reported no usage contribute to ``call_count``,
        ``unknown_calls`` and ``duration_ms`` but nothing to the token sums,
        so an un-instrumented backend depresses the totals visibly rather
        than silently.

        Returns:
            The aggregate for every call recorded so far.
        """
        # #CRITICAL: data-integrity: `or 0` here folds an unreported count to
        # zero on purpose, and is safe ONLY because `unknown_calls` is summed
        # alongside it. The token sums alone cannot distinguish a cheap run
        # from an uninstrumented one; the pair can. Dropping or miscounting
        # `unknown_calls` would leave a depressed total presenting as exact.
        # #VERIFY: tests/unit/test_usage.py::
        # test_unknown_call_depresses_totals_visibly_rather_than_silently.
        return UsageTotals(
            call_count=len(self.calls),
            unknown_calls=sum(1 for call in self.calls if not call.is_known),
            input_tokens=sum(call.input_tokens or 0 for call in self.calls),
            output_tokens=sum(call.output_tokens or 0 for call in self.calls),
            duration_ms=sum(call.duration_ms for call in self.calls),
        )


EMPTY_TOTALS: UsageTotals = UsageTotals(
    call_count=0,
    unknown_calls=0,
    input_tokens=0,
    output_tokens=0,
    duration_ms=0,
)
"""The aggregate for a run that made no provider calls.

Distinct from a run whose calls all reported nothing: that one has a non-zero
``call_count`` and ``unknown_calls``, and ``complete`` is ``False``.
"""
