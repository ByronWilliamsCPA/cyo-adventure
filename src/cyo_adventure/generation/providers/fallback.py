"""Composite ``GenerationProvider`` that fails over across ordered legs.

This is **Layer 2** of the three-layer failure model. It holds an ordered list
of real adapter legs (each owning its own Layer-1 transient retry) and presents a
single ``GenerationProvider`` to the orchestrator, which stays unaware that any
failover happens.

Layer separation (do not collapse):

- **Layer 1** (inside each adapter): retry the *same* model on transient faults.
- **Layer 2** (this class): on a leg's :class:`ProviderError`, fail over to the
  next live leg; mark *leg-fatal* legs dead for the rest of the run.
- **Layer 3** (orchestrator repair loop): a gate-blocked-but-valid response is a
  *content* failure, not a provider failure. It is a successful ``complete``
  here and never triggers failover.

PII invariant: the orchestrator runs ``assert_prompt_pii_safe`` on both prompt
blocks immediately before calling ``complete``. This class catches **only**
:class:`ProviderError`, so a PII :class:`~cyo_adventure.core.exceptions.ValidationError`
propagates straight through, never retried and never failed over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from cyo_adventure.generation.provider import GenerationProvider

logger = get_logger(__name__)

# Hard backstop on total leg invocations across one story (all of its Stage A,
# Stage B, and repair completions). The circuit breaker normally collapses the
# blow-up well before this; the cap only fires on a pathological retry storm.
_DEFAULT_MAX_TOTAL_ATTEMPTS: Final[int] = 30


def _leg_name(leg: GenerationProvider, index: int) -> str:
    """Return a leg's ``name`` attribute if present, else a positional label."""
    return getattr(leg, "name", f"leg{index}")


@dataclass
class FallbackProvider:
    """An ordered cascade of ``GenerationProvider`` legs with failover.

    Construct one per story (per generation job): the dead-leg set and the
    attempt counter are per-run state.

    Args:
        legs: Ordered adapter legs. ``complete`` tries each live leg in turn.
        max_total_attempts: Backstop on total leg invocations across the run.
    """

    legs: list[GenerationProvider]
    max_total_attempts: int = _DEFAULT_MAX_TOTAL_ATTEMPTS
    _dead: set[int] = field(default_factory=set, init=False, repr=False)
    _total_attempts: int = field(default=0, init=False, repr=False)

    @property
    def name(self) -> str:
        """Return a cascade label naming the ordered legs (for the worker record)."""
        inner = ",".join(_leg_name(leg, i) for i, leg in enumerate(self.legs))
        return f"fallback[{inner}]"

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Try each live leg in order, failing over on ``ProviderError``.

        Args:
            system: System-role instructions (forwarded unchanged).
            prompt: User-role prompt content (forwarded unchanged).
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The completion text from the first leg that succeeds.

        Raises:
            ProviderError: When every live leg has been exhausted, or the global
                per-run attempt cap is hit. Any non-``ProviderError`` (e.g. a PII
                ``ValidationError``) propagates unchanged.
        """
        # #CRITICAL: external-resources: orchestrates network calls across legs.
        # Leg-fatal failures mark a leg dead so a vanished model is not retried on
        # every subsequent complete() call; the attempt cap bounds the worst case.
        # #VERIFY: tests assert leg order, dead-leg skip, exhaustion ProviderError,
        # and that a non-ProviderError is not caught.
        last_error: ProviderError | None = None
        for index, leg in enumerate(self.legs):
            if index in self._dead:
                continue
            if self._total_attempts >= self.max_total_attempts:
                msg = (
                    "fallback exceeded the per-run attempt cap of "
                    f"{self.max_total_attempts}"
                )
                raise ProviderError(msg, provider="fallback", leg_fatal=False)
            self._total_attempts += 1
            leg_name = _leg_name(leg, index)
            try:
                result = await leg.complete(
                    system=system, prompt=prompt, max_tokens=max_tokens
                )
            except ProviderError as exc:
                last_error = exc
                if exc.leg_fatal:
                    self._dead.add(index)
                    logger.warning("fallback.leg_dead", leg=leg_name, error=str(exc))
                else:
                    logger.warning(
                        "fallback.leg_failover", leg=leg_name, error=str(exc)
                    )
                continue
            logger.info("fallback.leg_ok", leg=leg_name)
            return result

        msg = "all fallback legs exhausted"
        raise ProviderError(msg, provider="fallback", leg_fatal=False) from last_error
