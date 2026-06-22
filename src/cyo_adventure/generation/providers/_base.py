"""Shared retry/backoff driver for live ``GenerationProvider`` adapters.

Both the OpenRouter and Ollama adapters own **Layer 1** of the failure model:
retry TRANSIENT failures against the same model with exponential backoff, and
let leg-fatal failures propagate immediately so the cascade (Layer 2) can fail
over. This module factors that loop out so each adapter only supplies its own
single-attempt HTTP logic.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Final, cast

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_BACKOFF_BASE_SECONDS: Final[float] = 2.0


def as_str_map(value: object) -> dict[str, object] | None:
    """Narrow an untrusted decoded-JSON value to a string-keyed mapping.

    Mirrors the validator's defensive raw-JSON handling: returns the value typed
    as ``dict[str, object]`` when it is a dict, else ``None`` so callers can
    branch without raising on an unexpected response shape.

    Args:
        value: A value from a decoded JSON response (untrusted shape).

    Returns:
        The value as ``dict[str, object]`` when it is a dict, else ``None``.
    """
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


async def run_with_retries(
    attempt: Callable[[], Awaitable[str]],
    *,
    provider: str,
    model: str,
    max_retries: int,
    backoff_base_seconds: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> str:
    """Drive ``attempt`` with transient-only exponential-backoff retries.

    Args:
        attempt: A zero-arg coroutine performing one HTTP attempt; returns the
            completion text or raises :class:`ProviderError`.
        provider: Provider/leg name for logs and the exhaustion error.
        model: Model id for logs and the exhaustion error.
        max_retries: Number of attempts for transient failures.
        backoff_base_seconds: Base for backoff; attempt *n* (1-indexed) waits
            ``backoff_base_seconds * 2**n`` seconds before the next try. ``0``
            disables sleeping (tests).
        sleep: Injectable async sleep (defaults to :func:`asyncio.sleep`).

    Returns:
        The completion text from the first successful attempt.

    Raises:
        ProviderError: Immediately if an attempt raises a leg-fatal error; or
            with ``leg_fatal=False`` after all transient retries are exhausted.
    """
    last_exc: ProviderError | None = None
    for index in range(max_retries):
        try:
            return await attempt()
        except ProviderError as exc:
            if exc.leg_fatal:
                raise
            last_exc = exc
            logger.warning(
                "provider.transient_retry",
                provider=f"{provider}:{model}",
                attempt=index + 1,
                max_retries=max_retries,
                error=str(exc),
            )
            if index + 1 < max_retries:
                await sleep(backoff_base_seconds * 2 ** (index + 1))

    msg = f"{provider} transient failure persisted after {max_retries} attempts"
    raise ProviderError(
        msg, provider=provider, model=model, leg_fatal=False
    ) from last_exc
