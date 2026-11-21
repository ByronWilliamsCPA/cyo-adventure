"""Explicit reasoning control for provider calls (AL-847).

The WP-2.3 paid smoke showed that leaving the ``reasoning`` field out of an
OpenRouter request (``Settings.llm_effort="off"``) does not stop a reasoning
model from reasoning: one Sonnet 5.5 plan call still spent 11,490 reasoning
tokens. A caller that cares therefore has to say what it wants. This module
gives it two ways:

- a :class:`ReasoningControl` value (disable, an effort level, or a token
  budget) passed to an adapter at construction, and
- :func:`explicit_reasoning`, a context manager that applies a control to
  every OpenRouter request made inside it, whatever wrappers (metering, PII
  guard, cascade) sit between the caller and the adapter. The Story Plan path
  uses this, so it needs no change to the ``GenerationProvider`` protocol.

OpenRouter's documented request shape (``/docs/use-cases/reasoning-tokens``,
read 2026-11-21) is ``"reasoning": {"effort": ...}`` or
``"reasoning": {"max_tokens": N}``, not both. ``effort`` accepts ``"max"``,
``"xhigh"``, ``"high"``, ``"medium"``, ``"low"``, ``"minimal"`` and
``"none"``; ``"none"`` "disables reasoning entirely", except that a model
whose reasoning is mandatory rejects it. For Anthropic models a
``max_tokens`` budget is used directly with a floor of 1,024 tokens, and the
request's own ``max_tokens`` must be strictly larger than the budget.

What is verified and what is not: the ``low`` effort form is measured (the
smoke's six runs, 0 to 3,078 reasoning tokens per plan call). The
``{"effort": "none"}`` disable and the ``{"max_tokens": N}`` budget follow the
documentation but have not been run against Sonnet 5.5 or any other model
from this codebase.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from cyo_adventure.core.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = [
    "MIN_REASONING_BUDGET",
    "ReasoningControl",
    "ReasoningEffort",
    "current_reasoning",
    "explicit_reasoning",
]

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
"""Effort levels this codebase sends. ``"none"`` disables reasoning."""

MIN_REASONING_BUDGET: Final = 1_024
"""The smallest reasoning token budget OpenRouter accepts for Anthropic models."""


@dataclass(frozen=True, slots=True)
class ReasoningControl:
    """An explicit reasoning setting: exactly one of an effort or a budget.

    Attributes:
        effort: An effort level; ``"none"`` disables reasoning.
        max_tokens: A reasoning token budget (at least
            :data:`MIN_REASONING_BUDGET`).
    """

    effort: ReasoningEffort | None = None
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        """Reject a control that sets both forms, neither, or a tiny budget.

        Raises:
            ConfigurationError: If the control is not exactly one valid form.
        """
        if (self.effort is None) == (self.max_tokens is None):
            msg = "a reasoning control sets exactly one of effort or max_tokens"
            raise ConfigurationError(msg)
        if self.max_tokens is not None and self.max_tokens < MIN_REASONING_BUDGET:
            msg = (
                f"a reasoning budget must be at least {MIN_REASONING_BUDGET} "
                f"tokens, got {self.max_tokens}"
            )
            raise ConfigurationError(msg)

    @classmethod
    def disabled(cls) -> ReasoningControl:
        """Return the explicit disable (``effort: "none"``).

        Returns:
            ReasoningControl: The control.
        """
        return cls(effort="none")

    @classmethod
    def from_settings(
        cls, effort: ReasoningEffort, max_tokens: int | None
    ) -> ReasoningControl:
        """Build a control from a pair of settings: a budget wins over an effort.

        Args:
            effort: The configured effort.
            max_tokens: The configured budget, or None to use the effort.

        Returns:
            ReasoningControl: The control.
        """
        if max_tokens is not None:
            return cls(max_tokens=max_tokens)
        return cls(effort=effort)

    def to_openrouter(self) -> dict[str, object]:
        """Return the OpenRouter ``reasoning`` request object.

        Returns:
            dict[str, object]: ``{"effort": ...}`` or ``{"max_tokens": N}``.
        """
        if self.max_tokens is not None:
            return {"max_tokens": self.max_tokens}
        return {"effort": self.effort}


# #CRITICAL: concurrency: a ContextVar, so a control set by one job's task is
# invisible to every other task (asyncio copies the context per task) and is
# reset when the ``with`` block ends, even on an exception.
# #VERIFY: test_reasoning_control.py::test_explicit_reasoning_is_scoped_and_reset
# and ::test_explicit_reasoning_does_not_leak_into_a_sibling_task.
_EXPLICIT: ContextVar[ReasoningControl | None] = ContextVar(
    "explicit_reasoning", default=None
)


@contextmanager
def explicit_reasoning(control: ReasoningControl) -> Generator[None]:
    """Apply ``control`` to every OpenRouter request made inside the block.

    Args:
        control: The reasoning setting to send.

    Yields:
        None: While the block runs.
    """
    token = _EXPLICIT.set(control)
    try:
        yield
    finally:
        _EXPLICIT.reset(token)


def current_reasoning() -> ReasoningControl | None:
    """Return the control set by an enclosing :func:`explicit_reasoning`, if any.

    Returns:
        ReasoningControl | None: The control, or None outside any block.
    """
    return _EXPLICIT.get()
