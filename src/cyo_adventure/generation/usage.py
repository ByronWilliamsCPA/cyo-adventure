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
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What one provider call consumed.

    Attributes:
        provider: The backend that served the call, as the adapter's own
            ``name`` reports it (e.g. ``"anthropic:claude-opus-5"``). For a
            fallback chain this is the leg that actually answered, not the
            chain, because the leg is what was billed.
        model: The model id the call was issued against.
        input_tokens: Prompt tokens the backend reported, or ``None`` when it
            reported none. Not interchangeable with ``0``.
        output_tokens: Completion tokens the backend reported, or ``None``
            when it reported none.
        duration_ms: Wall-clock milliseconds for the call, measured around the
            adapter's network work. Always known, since it is measured here
            rather than reported by the backend.
    """

    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int

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
    """

    text: str
    usage: TokenUsage


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
