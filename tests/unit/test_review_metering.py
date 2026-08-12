"""The review-path providers are billed to the job that provoked them.

Two providers in a generation job are built where they are used rather than
passed in: the moderation pipeline's reviewer, and the Stage 1 fidelity gate's
semantic checker. Both would therefore spend money outside the job's ledger by
default, and the resulting undercount is the dangerous kind: the persisted
totals would still report themselves complete, and simply be too small.

These tests pin that both paths reach the caller's ledger, and that the PII
guard stays outermost so a prompt it rejects is billed to nobody.
"""

from __future__ import annotations

from typing import Protocol

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.metered import MeteredProvider, ledger_of
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.usage import Completion, TokenUsage, UsageLedger

_REAL_CHILD = "Wilhelmina Featherstone"

_REVIEW_USAGE = TokenUsage(
    provider="openrouter",
    model="anthropic/claude-sonnet-4.6",
    input_tokens=800,
    output_tokens=90,
    duration_ms=42,
)


class _Completer(Protocol):
    """The one method both provider protocols declare.

    Declared here so the fakes below can call ``complete`` on whatever the
    gate hands them without widening the parameter to ``Any``.
    """

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Return a completion for the given prompt."""
        ...


class _StubProvider:
    """A provider double that answers every call with one canned completion."""

    def __init__(self, text: str = "{}") -> None:
        self._text = text
        self.calls = 0

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        del system, prompt, max_tokens
        self.calls += 1
        return Completion(text=self._text, usage=_REVIEW_USAGE)


@pytest.mark.unit
def test_ledger_of_finds_the_ledger_through_the_wrapper() -> None:
    """The plumbing all three call sites rely on: provider carries the ledger."""
    ledger = UsageLedger()

    assert ledger_of(MeteredProvider(_StubProvider(), ledger=ledger)) is ledger


@pytest.mark.unit
def test_ledger_of_returns_none_for_an_unmetered_provider() -> None:
    """An unmetered run must be indistinguishable from the pre-metering code.

    Every review-path call site branches on this, and the ``None`` branch has
    to be the exact behaviour those sites had before, so an injected test
    double or an un-instrumented caller changes nothing.
    """
    assert ledger_of(_StubProvider()) is None
    assert ledger_of(None) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_calls_are_billed_to_the_generation_jobs_ledger() -> None:
    """A review provider metered into the job ledger contributes to its totals.

    Exercises the composition
    ``moderation/pipeline.py::_build_guarded_review`` builds: the review
    provider wrapped in the job's meter, wrapped in turn by the PII guard.
    """
    from cyo_adventure.generation.guarded import PiiGuardedProvider

    ledger = UsageLedger()
    inner = _StubProvider()
    guarded = PiiGuardedProvider(
        MeteredProvider(inner, ledger=ledger),
        forbidden=PiiContext(child_names=frozenset({_REAL_CHILD})),
    )

    await guarded.complete(system="review this", prompt="a gentle story", max_tokens=64)

    assert inner.calls == 1
    assert ledger.calls == [_REVIEW_USAGE]
    assert ledger.snapshot().output_tokens == 90


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_guard_rejected_review_prompt_is_billed_to_nobody() -> None:
    """The guard is outermost, so a blocked prompt reaches neither meter nor backend.

    This is why the guard wraps the meter rather than the reverse. A call that
    never left the process cost nothing, and recording it would inflate the
    job's call count with calls no vendor ever saw.
    """
    from cyo_adventure.generation.guarded import PiiGuardedProvider

    ledger = UsageLedger()
    inner = _StubProvider()
    guarded = PiiGuardedProvider(
        MeteredProvider(inner, ledger=ledger),
        forbidden=PiiContext(child_names=frozenset({_REAL_CHILD})),
    )

    with pytest.raises(ValidationError):
        await guarded.complete(
            system="review this",
            prompt=f"a story about {_REAL_CHILD}",
            max_tokens=64,
        )

    assert inner.calls == 0
    assert ledger.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_stage1_gates_semantic_check_is_billed_to_the_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_stage1_gate meters the review provider it builds for itself.

    The gate runs once per fill and again on every repair attempt, so an
    unmetered gate would undercount most on exactly the jobs that cost the
    most: the ones that needed repairing.
    """
    from cyo_adventure.core.config import settings as config_settings
    from cyo_adventure.generation import fidelity_gate

    inner = _StubProvider()
    monkeypatch.setattr(
        fidelity_gate,
        "build_review_provider",
        lambda *_args, **_kwargs: (inner, True),
    )
    # The pure-code checks must pass, or the gate short-circuits before ever
    # reaching the semantic call this test is about.
    monkeypatch.setattr(fidelity_gate, "run_fidelity_checks", lambda *_args: [])

    async def _fake_semantic_check(
        _original: object, _filled: object, provider: _Completer
    ) -> None:
        await provider.complete(system="s", prompt="p", max_tokens=32)
        return

    monkeypatch.setattr(
        fidelity_gate, "run_semantic_fidelity_check", _fake_semantic_check
    )

    ledger = UsageLedger()
    violations = await fidelity_gate.run_stage1_gate(
        {},
        {},
        review_stage1_model=None,
        settings=config_settings,
        pii=PiiContext(child_names=frozenset()),
        ledger=ledger,
    )

    assert violations == []
    assert inner.calls == 1
    assert ledger.calls == [_REVIEW_USAGE]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_stage1_gate_without_a_ledger_makes_the_same_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unmetered path is byte-for-byte the pre-metering behaviour."""
    from cyo_adventure.core.config import settings as config_settings
    from cyo_adventure.generation import fidelity_gate

    inner = _StubProvider()
    monkeypatch.setattr(
        fidelity_gate,
        "build_review_provider",
        lambda *_args, **_kwargs: (inner, True),
    )
    monkeypatch.setattr(fidelity_gate, "run_fidelity_checks", lambda *_args: [])

    async def _fake_semantic_check(
        _original: object, _filled: object, provider: _Completer
    ) -> None:
        await provider.complete(system="s", prompt="p", max_tokens=32)
        return

    monkeypatch.setattr(
        fidelity_gate, "run_semantic_fidelity_check", _fake_semantic_check
    )

    await fidelity_gate.run_stage1_gate(
        {},
        {},
        review_stage1_model=None,
        settings=config_settings,
        pii=PiiContext(child_names=frozenset()),
    )

    assert inner.calls == 1
