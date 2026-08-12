"""Unit tests for the usage-recording provider wrapper (generation.metered).

The wrapper's whole claim is structural: a code path holding a
``MeteredProvider`` cannot make an unmetered call. These tests pin both halves
of that claim, the recording and the forwarding, plus the two degraded-response
paths that must stay live under a strict type checker: accounting may never
turn a malformed provider response into an outage.
"""

from __future__ import annotations

from typing import cast

import pytest

from cyo_adventure.core.exceptions import ExternalServiceError
from cyo_adventure.generation.metered import MeteredProvider
from cyo_adventure.generation.usage import Completion, TokenUsage, UsageLedger


def _usage(
    *,
    provider: str = "openrouter",
    model: str = "anthropic/claude-haiku-4.5",
    input_tokens: int | None = 120,
    output_tokens: int | None = 340,
    duration_ms: int = 900,
) -> TokenUsage:
    """Build a TokenUsage with defaults for whichever field is under test."""
    return TokenUsage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )


class _RecordingProvider:
    """Inner provider double returning a scripted sequence of responses."""

    def __init__(self, *responses: object) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        self.calls.append(
            {"system": system, "prompt": prompt, "max_tokens": max_tokens}
        )
        returned = self._responses.pop(0) if self._responses else None
        return cast("Completion", returned)


class _FailingProvider:
    """Inner provider double that raises rather than returning."""

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        del system, prompt, max_tokens
        msg = "backend unreachable"
        raise ExternalServiceError(msg)


def _metered(
    *responses: object,
) -> tuple[_RecordingProvider, MeteredProvider, UsageLedger]:
    """Wire a recording inner provider, a fresh ledger, and the wrapper."""
    inner = _RecordingProvider(*responses)
    ledger = UsageLedger()
    return inner, MeteredProvider(inner, ledger=ledger), ledger


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_call_is_recorded_and_the_response_forwarded_unchanged() -> None:
    """The ledger gains the call's usage and the caller gets the same object."""
    usage = _usage()
    completion = Completion(text="once upon a time", usage=usage)
    inner, metered, ledger = _metered(completion)

    result = await metered.complete(
        system="You write gentle stories.",
        prompt="A story about a brave fox.",
        max_tokens=256,
    )

    assert result is completion
    assert ledger.calls == [usage]
    assert inner.calls == [
        {
            "system": "You write gentle stories.",
            "prompt": "A story about a brave fox.",
            "max_tokens": 256,
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_every_call_lands_in_the_ledger_in_call_order() -> None:
    """Order is retained, so a per-call event log can be written from it."""
    first = _usage(model="first", duration_ms=100)
    second = _usage(model="second", duration_ms=200)
    _, metered, ledger = _metered(
        Completion(text="a", usage=first),
        Completion(text="b", usage=second),
    )

    await metered.complete(system="s", prompt="p", max_tokens=8)
    await metered.complete(system="s", prompt="p", max_tokens=8)

    assert ledger.calls == [first, second]
    snapshot = ledger.snapshot()
    assert snapshot.call_count == 2
    assert snapshot.duration_ms == 300
    assert snapshot.complete is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_unreported_usage_makes_the_snapshot_incomplete() -> None:
    """A call the backend did not instrument is counted, not silently dropped.

    The call still reaches the ledger, so ``unknown_calls`` rises and the
    snapshot reports itself a lower bound. Dropping the record instead would
    make an un-instrumented backend look free.
    """
    _, metered, ledger = _metered(
        Completion(text="a", usage=_usage(input_tokens=None, output_tokens=None))
    )

    await metered.complete(system="s", prompt="p", max_tokens=8)

    snapshot = ledger.snapshot()
    assert snapshot.call_count == 1
    assert snapshot.unknown_calls == 1
    assert snapshot.complete is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_non_completion_response_is_forwarded_unmetered() -> None:
    """A provider returning a bare string is passed through, not crashed on.

    Both provider protocols are structural, so a non-conforming implementation
    can return anything. The wrapper's job is accounting; a response it cannot
    account for must still reach the caller, whose own fail-safe path is what
    decides the outcome.
    """
    _, metered, ledger = _metered("a bare string, not a Completion")

    result = await metered.complete(system="s", prompt="p", max_tokens=8)

    assert cast("object", result) == "a bare string, not a Completion"
    assert ledger.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_completion_with_a_non_usage_payload_is_forwarded_unmetered() -> None:
    """A Completion carrying a malformed usage field records nothing and returns.

    Recording it would put an object of unknown shape into a ledger that later
    feeds cost arithmetic, which converts a provider defect into a wrong money
    figure. Skipping it costs one unaccounted call instead.
    """
    malformed = Completion(text="body", usage=cast("TokenUsage", {"input": 5}))
    _, metered, ledger = _metered(malformed)

    result = await metered.complete(system="s", prompt="p", max_tokens=8)

    assert result is malformed
    assert ledger.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_none_response_is_forwarded_unmetered() -> None:
    """The degenerate response is handled by the same guard, not a special case."""
    _, metered, ledger = _metered(None)

    result = await metered.complete(system="s", prompt="p", max_tokens=8)

    assert cast("object", result) is None
    assert ledger.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_failed_call_records_nothing_and_propagates() -> None:
    """A raised provider error reaches the caller and bills no tokens.

    A call that never returned has no usage to attribute, and swallowing the
    error here would hide a backend outage behind a zero-cost job.
    """
    ledger = UsageLedger()
    metered = MeteredProvider(_FailingProvider(), ledger=ledger)

    with pytest.raises(ExternalServiceError):
        await metered.complete(system="s", prompt="p", max_tokens=8)

    assert ledger.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_two_wrappers_do_not_share_a_ledger() -> None:
    """Per-job ledgers are what stop concurrent jobs cross-billing each other."""
    first_usage = _usage(model="job-one")
    second_usage = _usage(model="job-two")
    _, first, first_ledger = _metered(Completion(text="a", usage=first_usage))
    _, second, second_ledger = _metered(Completion(text="b", usage=second_usage))

    await first.complete(system="s", prompt="p", max_tokens=8)
    await second.complete(system="s", prompt="p", max_tokens=8)

    assert first_ledger.calls == [first_usage]
    assert second_ledger.calls == [second_usage]


class _LabelledProvider(_RecordingProvider):
    """An inner provider that declares its name and model, as adapters do."""

    name = "openrouter"
    model = "anthropic/claude-haiku-4.5"


@pytest.mark.unit
def test_the_wrapper_forwards_the_provider_and_model_labels() -> None:
    """The wrapper is invisible to whatever reads a provider's labels.

    The worker stamps job.provider/job.model with
    ``getattr(provider, "name", None) or <configured default>``. A wrapper
    that dropped the attribute would not raise; it would relabel every job
    with the configured default, so an audit of which provider ran a job
    would report the config rather than the run.
    """
    metered = MeteredProvider(_LabelledProvider(), ledger=UsageLedger())

    assert metered.name == "openrouter"
    assert metered.model == "anthropic/claude-haiku-4.5"


@pytest.mark.unit
def test_absent_labels_are_forwarded_as_none() -> None:
    """A provider declaring no labels still reaches the caller's own fallback.

    Forwarding a placeholder string here would be worse than forwarding
    nothing: the caller's ``or <default>`` fallback would stop firing and
    every such job would be labelled with this module's invention instead.
    """
    metered = MeteredProvider(_RecordingProvider(), ledger=UsageLedger())

    assert metered.name is None
    assert metered.model is None


@pytest.mark.unit
def test_the_ledger_is_readable_through_the_wrapper() -> None:
    """The ledger is reachable from the provider, which is how the worker stamps."""
    ledger = UsageLedger()
    metered = MeteredProvider(_RecordingProvider(), ledger=ledger)

    assert metered.ledger is ledger
