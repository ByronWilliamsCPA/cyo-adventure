"""The review-path providers are billed to the job that provoked them.

Two providers in a generation job are built where they are used rather than
passed in: the moderation pipeline's reviewer, and the Stage 1 fidelity gate's
semantic checker. Both would therefore spend money outside the job's ledger by
default, and the resulting undercount is the dangerous kind: the persisted
totals would still report themselves complete, and simply be too small.

These tests pin that both paths reach the caller's ledger, and that the PII
guard stays outermost so a prompt it rejects is billed to nobody. The
``_build_guarded_review`` tests below call that function directly (not a
hand-rebuilt copy of its composition), so a change to how it threads the
ledger through the reviewer fails here instead of leaving this file green by
construction.
"""

from __future__ import annotations

from typing import Protocol

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.metered import MeteredProvider, ledger_of
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.providers.fallback import FallbackProvider
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
async def test_review_calls_are_billed_to_the_generation_jobs_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_build_guarded_review` bills the reviewer it builds to the job's ledger.

    Stubs ``build_review_provider`` (the seam the function calls internally)
    with a provider whose usage is distinguishable from the generation side,
    then drives a call through the provider ``_build_guarded_review`` returns
    and checks the *caller's* ledger, the one attached to the
    ``generation_provider`` argument, actually grew.
    """
    from cyo_adventure.core.config import settings as config_settings
    from cyo_adventure.generation.guarded import PiiGuardedProvider
    from cyo_adventure.moderation import pipeline as pipeline_mod
    from cyo_adventure.moderation.pipeline import _build_guarded_review

    ledger = UsageLedger()
    review_stub = _StubProvider()
    monkeypatch.setattr(
        pipeline_mod, "build_review_provider", lambda *_a, **_kw: (review_stub, True)
    )

    guarded, independent = _build_guarded_review(
        config_settings,
        generator_provider="anthropic",
        generator_model="claude-opus",
        pii=PiiContext(child_names=frozenset({_REAL_CHILD})),
        generation_provider=MeteredProvider(_StubProvider(), ledger=ledger),
    )
    await guarded.complete(system="review this", prompt="a gentle story", max_tokens=64)

    assert isinstance(guarded, PiiGuardedProvider)
    assert independent is True
    assert review_stub.calls == 1
    assert ledger.calls == [_REVIEW_USAGE]
    assert ledger.snapshot().output_tokens == 90


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_guarded_review_falls_back_to_unmetered_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain (unmetered) generation provider must not stop review from working.

    ``ledger_of`` returns ``None`` for a provider that carries no ledger;
    ``_build_guarded_review`` must treat that as the documented silent
    fallback, not raise, and still return a working, PII-guarded reviewer.
    """
    from cyo_adventure.core.config import settings as config_settings
    from cyo_adventure.generation.guarded import PiiGuardedProvider
    from cyo_adventure.moderation import pipeline as pipeline_mod
    from cyo_adventure.moderation.pipeline import _build_guarded_review

    review_stub = _StubProvider()
    monkeypatch.setattr(
        pipeline_mod, "build_review_provider", lambda *_a, **_kw: (review_stub, False)
    )

    guarded, independent = _build_guarded_review(
        config_settings,
        generator_provider="anthropic",
        generator_model="claude-opus",
        pii=PiiContext(child_names=frozenset({_REAL_CHILD})),
        generation_provider=_StubProvider(),
    )
    result = await guarded.complete(
        system="review this", prompt="a gentle story", max_tokens=64
    )

    assert isinstance(guarded, PiiGuardedProvider)
    assert independent is False
    assert review_stub.calls == 1
    assert result.text == "{}"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("metered", [True, False], ids=["metered", "unmetered"])
async def test_build_guarded_review_pii_guard_rejects_before_review_or_metering(
    monkeypatch: pytest.MonkeyPatch, metered: bool
) -> None:
    """The PII guard stays outermost in both of `_build_guarded_review`'s branches.

    A rejected review prompt must reach neither the reviewer nor the meter,
    whether or not the run is metered, so a blocked call never inflates
    either the vendor's call count or the job's ledger.
    """
    from cyo_adventure.core.config import settings as config_settings
    from cyo_adventure.moderation import pipeline as pipeline_mod
    from cyo_adventure.moderation.pipeline import _build_guarded_review

    ledger = UsageLedger()
    review_stub = _StubProvider()
    monkeypatch.setattr(
        pipeline_mod, "build_review_provider", lambda *_a, **_kw: (review_stub, True)
    )
    generation_provider = (
        MeteredProvider(_StubProvider(), ledger=ledger) if metered else _StubProvider()
    )

    guarded, _independent = _build_guarded_review(
        config_settings,
        generator_provider="anthropic",
        generator_model="claude-opus",
        pii=PiiContext(child_names=frozenset({_REAL_CHILD})),
        generation_provider=generation_provider,
    )

    with pytest.raises(ValidationError):
        await guarded.complete(
            system="review this",
            prompt=f"a story about {_REAL_CHILD}",
            max_tokens=64,
        )

    assert review_stub.calls == 0
    assert ledger.calls == []


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


class _NamedProvider(_StubProvider):
    """A provider that declares a backend label, as every real adapter does."""

    name = "modal"


def _generator_seen_by_review_builder(
    monkeypatch: pytest.MonkeyPatch, generation_provider: object
) -> list[str | None]:
    """Return the ``generator_provider`` values ``build_review_provider`` saw.

    Args:
        monkeypatch: Used to intercept ``build_review_provider`` in place.
        generation_provider: The resolved provider handed to the pipeline.

    Returns:
        One entry per call, ``None`` for any non-string value.
    """
    from cyo_adventure.core.config import settings as config_settings
    from cyo_adventure.moderation import pipeline as pipeline_mod
    from cyo_adventure.moderation.pipeline import _build_guarded_review

    seen: list[str | None] = []

    def _capture(*_args: object, **kwargs: object) -> tuple[_StubProvider, bool]:
        generator = kwargs["generator_provider"]
        seen.append(generator if isinstance(generator, str) else None)
        return _StubProvider(), True

    monkeypatch.setattr(pipeline_mod, "build_review_provider", _capture)
    _build_guarded_review(
        config_settings,
        generator_provider="anthropic",
        generator_model="claude-opus",
        pii=PiiContext(child_names=frozenset({_REAL_CHILD})),
        generation_provider=generation_provider,
    )
    return seen


@pytest.mark.unit
def test_independence_is_judged_against_the_resolved_generator_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-job provider override decides independence, not the config.

    The worker can resolve a provider override before calling the pipeline, so
    the backend that actually wrote the story is the one the resolved provider
    declares, not ``settings.generation_provider``. Judging against the config
    misjudges in the dangerous direction as readily as the safe one: an
    override onto the review backend would be recorded as independent, so a
    model would review its own output while the persisted report attested that
    it had not.

    The stub declares ``modal`` while the configured argument says
    ``anthropic``, so this fails if the configured value is the one that
    reaches ``build_review_provider``.
    """
    assert _generator_seen_by_review_builder(monkeypatch, _NamedProvider()) == ["modal"]


@pytest.mark.unit
def test_the_configured_backend_is_used_when_the_provider_declares_no_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A label-less provider falls back to the configured name, not to ``None``.

    ``build_review_provider`` accepts ``None`` and reads it as "generator
    unknown", which would quietly weaken every independence verdict for a
    provider that declares no label. The configured value is the better answer
    there, because it is what the job would have run on absent an override.
    """
    seen = _generator_seen_by_review_builder(monkeypatch, _StubProvider())

    assert seen == ["anthropic"]


class _CascadeLeg:
    """A cascade leg that answers, reporting the backend it really is."""

    name = "openrouter:sonnet"

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Answer with usage attributed to the openrouter backend."""
        del system, prompt, max_tokens
        return Completion(
            text="{}",
            usage=TokenUsage(
                provider="openrouter",
                model="anthropic/claude-sonnet-4.6",
                input_tokens=1,
                output_tokens=1,
                duration_ms=1,
            ),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cascade_is_judged_on_the_leg_that_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cascade must not launder its way past the independence check.

    ``FallbackProvider.name`` is a cascade label such as
    ``"fallback[openrouter:haiku,openrouter:sonnet,modal]"``. That string
    equals no configured backend, so judging on it makes
    ``backend != generator_provider`` unconditionally true and grants tier-1
    independence to every cascade run, whatever model actually answered. The
    resolved leg is the only value that can be compared.
    """
    cascade = FallbackProvider(legs=[_CascadeLeg()])
    await cascade.complete(system="s", prompt="u", max_tokens=1)

    assert _generator_seen_by_review_builder(monkeypatch, cascade) == ["openrouter"]
