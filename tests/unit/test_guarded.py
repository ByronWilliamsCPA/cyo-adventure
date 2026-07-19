"""Unit tests for the PiiGuardedProvider structural PII enforcement wrapper.

These exercise the wrapper in isolation (the orchestrator tests cover it only
transitively, and only via a prompt-block hit). The wrapper is the sole
structural point that prevents real-child PII from reaching an external LLM, so
both the system-block and prompt-block screening paths, and the
inner-provider-never-called invariant, are asserted directly here.
"""

from __future__ import annotations

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.pii import PiiContext

_REAL_CHILD = "Wilhelmina Featherstone"


class _RecordingProvider:
    """Inner provider double that records every complete() call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        self.calls.append(
            {"system": system, "prompt": prompt, "max_tokens": max_tokens}
        )
        return "inner-response"


def _guard() -> tuple[_RecordingProvider, PiiGuardedProvider]:
    inner = _RecordingProvider()
    forbidden = PiiContext(child_names=frozenset({_REAL_CHILD}))
    return inner, PiiGuardedProvider(inner, forbidden=forbidden)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_call_delegates_to_inner() -> None:
    """A PII-free call reaches the inner provider and returns its response."""
    inner, guarded = _guard()

    result = await guarded.complete(
        system="You write gentle stories.",
        prompt="A story about a brave fox.",
        max_tokens=128,
    )

    assert result == "inner-response"
    assert len(inner.calls) == 1
    assert inner.calls[0]["max_tokens"] == 128


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pii_in_prompt_aborts_before_inner() -> None:
    """A real-child name in the prompt block raises and never calls inner."""
    inner, guarded = _guard()

    with pytest.raises(ValidationError):
        await guarded.complete(
            system="You write gentle stories.",
            prompt=f"A story for {_REAL_CHILD}.",
            max_tokens=128,
        )

    assert inner.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pii_in_system_aborts_before_inner() -> None:
    """A real-child name in the system block raises and never calls inner.

    The system block is screened too, so a future template change cannot smuggle
    PII past the guard via the system role.
    """
    inner, guarded = _guard()

    with pytest.raises(ValidationError):
        await guarded.complete(
            system=f"The reader is {_REAL_CHILD}.",
            prompt="A story about a brave fox.",
            max_tokens=128,
        )

    assert inner.calls == []
