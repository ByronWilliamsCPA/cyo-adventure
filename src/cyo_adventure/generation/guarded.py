"""PII-enforcing provider wrapper for the generation pipeline.

Wraps any :class:`~cyo_adventure.generation.provider.GenerationProvider` and
enforces the PII egress guard on every ``complete()`` call before delegating
to the inner provider. This makes PII enforcement structural rather than
conventional: any code path that holds a :class:`PiiGuardedProvider` cannot
bypass the guard.

Usage::

    guarded = PiiGuardedProvider(real_provider, forbidden=pii_ctx)
    # All calls below are PII-checked before reaching the network.
    result = await guarded.complete(system=s, prompt=p, max_tokens=n)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.generation.pii import assert_prompt_pii_safe

if TYPE_CHECKING:
    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.provider import GenerationProvider

__all__ = ["PiiGuardedProvider"]


class PiiGuardedProvider:
    """Structural PII enforcement wrapper around a :class:`GenerationProvider`.

    Satisfies the :class:`~cyo_adventure.generation.provider.GenerationProvider`
    structural protocol: any object with a matching ``complete`` coroutine is
    accepted wherever a ``GenerationProvider`` is expected.

    Both the ``system`` and ``prompt`` blocks are screened before the inner
    provider is called. A PII match raises
    :class:`~cyo_adventure.core.exceptions.ValidationError` immediately and
    the inner provider's ``complete`` is never invoked.

    Args:
        inner: The real provider to delegate to after the PII check passes.
        forbidden: The :class:`~cyo_adventure.generation.pii.PiiContext`
            carrying real-child names for this family.
    """

    # #CRITICAL: security: sole structural enforcement point that prevents
    # real-child PII from reaching an external LLM provider via complete().
    # #VERIFY: both system and prompt are screened; a PII hit aborts before
    # the inner provider is called. Test: provider.calls is empty after a hit.

    def __init__(self, inner: GenerationProvider, *, forbidden: PiiContext) -> None:
        self._inner = inner
        self._forbidden = forbidden

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Screen both blocks for PII, then delegate to the inner provider.

        Args:
            system: System-role instructions block.
            prompt: User-role prompt block.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The raw text completion from the inner provider.

        Raises:
            ValidationError: If either block contains a real-child name from
                ``forbidden``, or PII-shaped content. The inner provider is
                not called.
        """
        assert_prompt_pii_safe(system, forbidden=self._forbidden)
        assert_prompt_pii_safe(prompt, forbidden=self._forbidden)
        return await self._inner.complete(
            system=system, prompt=prompt, max_tokens=max_tokens
        )
