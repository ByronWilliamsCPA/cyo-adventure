"""Unit tests for token-usage accounting (generation.usage).

The whole point of this module is that a wrong cost figure is worse than no
cost figure, so these tests pin the distinctions that make that true: unknown
is not zero, a partially-instrumented run reports itself incomplete, and a
count the backend controls cannot smuggle a non-integer into a total.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cyo_adventure.generation.usage import (
    EMPTY_TOTALS,
    Completion,
    TokenUsage,
    UsageLedger,
    UsageTotals,
    coerce_token_count,
)


def _usage(
    *,
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
    duration_ms: int = 100,
) -> TokenUsage:
    """Build a TokenUsage with sensible defaults for the field under test."""
    return TokenUsage(
        provider="openrouter",
        model="anthropic/claude-sonnet-4.6",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# 1. coerce_token_count
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, 1, 4096])
def test_coerce_accepts_non_negative_integers(value: int) -> None:
    """A plain non-negative int passes through unchanged, including zero.

    Zero is a real report ("this call consumed no prompt tokens"), so it must
    survive as ``0`` rather than being folded into the unknown case.
    """
    assert coerce_token_count(value) == value


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [None, "512", 12.0, -1, [12], {"prompt_tokens": 12}],
)
def test_coerce_rejects_non_integer_and_negative_values(value: object) -> None:
    """Anything not a non-negative plain int reports unknown, never a number.

    These are the shapes a backend can actually put on the wire: a null usage
    field, a stringified count from a proxy, a float from a JSON encoder that
    round-trips through a double, and a negative from a broken accumulator.
    """
    assert coerce_token_count(value) is None


@pytest.mark.unit
@pytest.mark.parametrize("value", [True, False])
def test_coerce_rejects_bool_despite_int_subclassing(value: object) -> None:
    """``bool`` is an ``int`` subclass, so it must be rejected explicitly.

    Without the explicit check, a backend returning ``"prompt_tokens": true``
    would bill one token and read as a known, complete call.
    """
    assert coerce_token_count(value) is None


# ---------------------------------------------------------------------------
# 2. TokenUsage.is_known
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_usage_with_both_counts_is_known() -> None:
    """Both counts present means the call can contribute a defensible cost."""
    assert _usage().is_known is True


@pytest.mark.unit
def test_usage_with_zero_counts_is_still_known() -> None:
    """Zero is a report, not an absence: a zero-token call is fully accounted."""
    assert _usage(input_tokens=0, output_tokens=0).is_known is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("input_tokens", "output_tokens"),
    [(None, 5), (10, None), (None, None)],
)
def test_usage_missing_either_half_is_unknown(
    input_tokens: int | None, output_tokens: int | None
) -> None:
    """Half a report is not a cost: either count missing marks the call unknown.

    Priced separately at different rates, an input-only or output-only record
    cannot produce a total, so it must not be treated as complete.
    """
    usage = _usage(input_tokens=input_tokens, output_tokens=output_tokens)

    assert usage.is_known is False


# ---------------------------------------------------------------------------
# 3. UsageLedger accumulation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_ledger_snapshots_to_empty_totals() -> None:
    """A run that made no provider calls folds to the zero aggregate, complete.

    Nothing was spent and nothing is unaccounted for, so ``complete`` is True:
    this is genuinely different from a run whose calls all reported nothing.
    """
    assert UsageLedger().snapshot() == EMPTY_TOTALS
    assert EMPTY_TOTALS.complete is True


@pytest.mark.unit
def test_ledger_sums_known_calls_and_reports_complete() -> None:
    """Fully instrumented calls sum straight through with nothing unknown."""
    ledger = UsageLedger()
    ledger.record(_usage(input_tokens=100, output_tokens=20, duration_ms=900))
    ledger.record(_usage(input_tokens=250, output_tokens=60, duration_ms=1_100))

    totals = ledger.snapshot()

    assert totals == UsageTotals(
        call_count=2,
        unknown_calls=0,
        input_tokens=350,
        output_tokens=80,
        duration_ms=2_000,
    )
    assert totals.complete is True


@pytest.mark.unit
def test_unknown_call_depresses_totals_visibly_rather_than_silently() -> None:
    """An un-instrumented call is counted and flagged, contributing no tokens.

    This is the case the whole ``int | None`` design exists for: the token sums
    become a lower bound, and ``complete`` is what says so. A ledger that
    coerced the missing counts to zero would produce the same sums with
    ``complete`` still True, which is the silent-undercount failure.
    """
    ledger = UsageLedger()
    ledger.record(_usage(input_tokens=100, output_tokens=20, duration_ms=900))
    ledger.record(_usage(input_tokens=None, output_tokens=None, duration_ms=700))

    totals = ledger.snapshot()

    assert totals.call_count == 2
    assert totals.unknown_calls == 1
    assert totals.input_tokens == 100
    assert totals.output_tokens == 20
    # Duration is measured locally, so it is known even when the tokens are not.
    assert totals.duration_ms == 1_600
    assert totals.complete is False


@pytest.mark.unit
def test_ledger_retains_calls_in_order_for_per_call_reporting() -> None:
    """Calls are kept, not folded on arrival, so per-call events share a source.

    The per-call event log and the aggregate must agree; they do so by being
    derived from the same list rather than accumulated twice.
    """
    ledger = UsageLedger()
    first = _usage(input_tokens=1, output_tokens=1)
    second = _usage(input_tokens=2, output_tokens=2)

    ledger.record(first)
    ledger.record(second)

    assert ledger.calls == [first, second]


@pytest.mark.unit
def test_snapshot_does_not_consume_the_ledger() -> None:
    """Snapshotting mid-run is non-destructive; a later call still accumulates."""
    ledger = UsageLedger()
    ledger.record(_usage(input_tokens=10, output_tokens=1))

    mid = ledger.snapshot()
    ledger.record(_usage(input_tokens=90, output_tokens=9))
    final = ledger.snapshot()

    assert mid.input_tokens == 10
    assert final.input_tokens == 100
    assert final.call_count == 2


@pytest.mark.unit
def test_separate_ledgers_do_not_share_state() -> None:
    """Each run gets its own accumulator, so one job's cost cannot land on another.

    ``calls`` uses ``default_factory``; a bare mutable default would make every
    ledger share one list, and the concurrent RQ worker would cross-bill jobs.
    """
    first = UsageLedger()
    second = UsageLedger()

    first.record(_usage())

    assert second.calls == []
    assert second.snapshot().call_count == 0


# ---------------------------------------------------------------------------
# 4. UsageTotals serialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_to_dict_carries_the_completeness_verdict() -> None:
    """The stored record answers "is this a lower bound?" without recomputation."""
    ledger = UsageLedger()
    ledger.record(_usage(input_tokens=100, output_tokens=20, duration_ms=900))
    ledger.record(_usage(input_tokens=None, output_tokens=None, duration_ms=700))

    assert ledger.snapshot().to_dict() == {
        "call_count": 2,
        "unknown_calls": 1,
        "input_tokens": 100,
        "output_tokens": 20,
        "duration_ms": 1_600,
        "complete": False,
    }


# ---------------------------------------------------------------------------
# 5. Completion pairing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_completion_is_not_a_string_subclass() -> None:
    """Completion must not be usable as a str, or usage dies at the first slice.

    A ``str`` subclass would have let every existing call site keep working
    untouched, which is exactly the trap: any string operation returns a plain
    ``str`` and drops ``.usage`` with no error, reproducing the
    value-dies-at-a-type-boundary bug this type exists to fix.
    """
    completion = Completion(text="hello", usage=_usage())

    assert not isinstance(completion, str)
    assert completion.text == "hello"


@pytest.mark.unit
def test_usage_records_are_immutable() -> None:
    """Frozen records: a downstream stage cannot rewrite what a call was billed."""
    usage = _usage()

    with pytest.raises(FrozenInstanceError):
        setattr(usage, "input_tokens", 999)  # noqa: B010  # frozen: must go via setattr
