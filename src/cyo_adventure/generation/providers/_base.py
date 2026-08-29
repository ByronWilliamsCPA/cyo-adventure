"""Shared retry/backoff driver for live ``GenerationProvider`` adapters.

Every live adapter (OpenRouter, Anthropic, Modal) owns **Layer 1** of the failure model:
retry TRANSIENT failures against the same model with exponential backoff, and
let leg-fatal failures propagate immediately so the cascade (Layer 2) can fail
over. This module factors that loop out so each adapter only supplies its own
single-attempt HTTP logic.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final, cast

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.usage import coerce_token_count
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from cyo_adventure.generation.usage import Completion

logger = get_logger(__name__)

DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_BACKOFF_BASE_SECONDS: Final[float] = 2.0


def strip_code_fences(text: str) -> str:
    """Remove a wrapping markdown code fence from a model's JSON output.

    Some models (e.g. Gemini Flash, Haiku) wrap their JSON in a ```json ... ```
    fence even when told not to; the orchestrator parses with ``json.loads`` and
    would reject the leading backticks. This strips a leading fence line
    (``` or ```json) and a matching trailing ```; non-fenced output is returned
    unchanged, so models that already emit raw JSON are unaffected.

    Args:
        text: The raw completion text from a model.

    Returns:
        The text with a wrapping code fence removed, if present.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    newline = stripped.find("\n")
    # Drop the opening fence line (everything up to and including the newline).
    stripped = stripped[newline + 1 :] if newline != -1 else stripped[3:]
    stripped = stripped.rstrip()
    if stripped.endswith("```"):
        stripped = stripped[:-3].rstrip()
    return stripped


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


def dig_content(payload: object) -> str | None:
    """Safely extract ``choices[0].message.content`` from a response payload.

    Shared by every OpenAI-chat-completions-shaped adapter (OpenRouter, Modal).
    Narrows the untrusted decoded JSON with ``isinstance`` at each level (the
    same defensive pattern the validator uses for raw JSON) so an unexpected
    shape returns ``None`` rather than raising.

    Args:
        payload: The decoded JSON response (untrusted shape).

    Returns:
        The content string, or ``None`` when any expected key is missing or has
        an unexpected type.
    """
    top = as_str_map(payload)
    if top is None:
        return None
    choices = top.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = as_str_map(choices[0])
    if first is None:
        return None
    message = as_str_map(first.get("message"))
    if message is None:
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def dig_usage(payload: object) -> tuple[int | None, int | None]:
    """Safely extract ``usage.prompt_tokens``/``usage.completion_tokens``.

    Shared by every OpenAI-chat-completions-shaped adapter (OpenRouter, Modal),
    which report usage in that block. Narrows the untrusted decoded JSON the
    same defensive way :func:`dig_content` does, so a response that omits the
    block, or carries a non-numeric count, yields ``None`` (not reported)
    rather than ``0`` (free) or an exception.

    Args:
        payload: The decoded JSON response (untrusted shape).

    Returns:
        ``(input_tokens, output_tokens)``, each ``None`` when absent or
        unusable.
    """
    # #CRITICAL: data-integrity: these counts feed a persisted spend figure,
    # and every layer below is untrusted decoded JSON: the block can be
    # absent, be a non-mapping, or carry a non-int count on an otherwise
    # valid 200. Each narrowing step below must keep reporting None
    # (unknown), never 0 (free), because a zero is indistinguishable from a
    # genuinely free call once it reaches `cost_usd`. This is the same
    # assumption `AnthropicProvider._usage_counts` carries; it lives here
    # once because OpenRouter and Modal both route through this helper.
    # #VERIFY: test_openrouter_missing_usage_block_reports_unknown,
    # test_openrouter_malformed_usage_reports_unknown.
    top = as_str_map(payload)
    if top is None:
        return (None, None)
    usage = as_str_map(top.get("usage"))
    if usage is None:
        return (None, None)
    return (
        coerce_token_count(usage.get("prompt_tokens")),
        coerce_token_count(usage.get("completion_tokens")),
    )


def dig_finish_reason(payload: object) -> str | None:
    """Safely extract ``choices[0].finish_reason`` from a response payload.

    Shared by every OpenAI-chat-completions-shaped adapter. Narrowed the same
    defensive way :func:`dig_content` is, so an unexpected shape yields ``None``
    rather than raising.

    Args:
        payload: The decoded JSON response (untrusted shape).

    Returns:
        The reason string as reported, or ``None`` when absent or non-string.
        Deliberately not normalised to an enum: the value is a vendor's word for
        what happened, and mapping an unrecognised one onto a known member would
        invent a fact about a call we did not observe.
    """
    top = as_str_map(payload)
    if top is None:
        return None
    choices = top.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = as_str_map(choices[0])
    if first is None:
        return None
    reason = first.get("finish_reason")
    return reason if isinstance(reason, str) else None


def dig_reasoning_tokens(payload: object) -> int | None:
    """Safely extract ``usage.completion_tokens_details.reasoning_tokens``.

    Args:
        payload: The decoded JSON response (untrusted shape).

    Returns:
        The reasoning-token count, or ``None`` when absent or unusable.

    Note:
        The same ``None`` versus ``0`` discipline :func:`dig_usage` documents
        applies, and here it is load-bearing in a second way: one provider has
        been observed reporting ``reasoning_tokens=0`` while emitting 5,339
        characters of reasoning, so a reported zero is a vendor's claim rather
        than a measurement, and an absent block must not be flattened into one.
    """
    top = as_str_map(payload)
    if top is None:
        return None
    usage = as_str_map(top.get("usage"))
    if usage is None:
        return None
    details = as_str_map(usage.get("completion_tokens_details"))
    if details is None:
        return None
    return coerce_token_count(details.get("reasoning_tokens"))


def dig_vendor_cost(payload: object) -> Decimal | None:
    """Safely extract the vendor's own ``usage.cost`` for one call, in USD.

    OpenRouter reports what it actually charged for a call under ``usage.cost``
    when the request opts in (``usage: {"include": true}``). That number is an
    OBSERVED cost, which is a different kind of fact from the estimate
    :func:`cyo_adventure.core.pricing.estimate_cost` computes against a
    hand-transcribed price table: the table's own module docstring warns that a
    vendor price change makes every later estimate silently wrong, and nothing
    in it validates against reality. Capturing the vendor's figure is what lets
    a spend claim be a measurement rather than an inference.

    Args:
        payload: The decoded JSON response (untrusted shape).

    Returns:
        The call's cost as ``Decimal``, or ``None`` when absent or unusable.

    Note:
        The same ``None`` versus ``0`` discipline :func:`dig_usage` documents
        applies and is if anything sharper here: a missing cost block and a
        genuinely free call are the same absence to a consumer that flattens
        them, and a consumer that treats the flattened zero as spend has a
        budget that binds on nothing. ``bool`` is rejected before ``int`` for
        the same reason :func:`coerce_token_count` rejects it, and the value is
        routed through ``str`` so a JSON float never enters a money total as
        binary floating point.
    """
    # #CRITICAL: payment/financial: this is the only path by which a vendor's
    # own charge for a call reaches a spend total, and every layer below it is
    # untrusted decoded JSON. Each narrowing step must keep reporting None
    # (not reported) rather than 0 (free), because a consumer that sums a
    # flattened zero has a spend figure that cannot rise and therefore a cap
    # that cannot bind. `float` is converted through `str` so a repeating
    # binary fraction never becomes the money value itself.
    # #VERIFY: tests/unit/test_openrouter_provider_pin.py::
    # test_vendor_cost_is_requested_and_captured_when_opted_in and
    # ::test_an_absent_or_unusable_vendor_cost_reports_none_not_zero.
    top = as_str_map(payload)
    if top is None:
        return None
    usage = as_str_map(top.get("usage"))
    if usage is None:
        return None
    cost = usage.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float, str)):
        return None
    try:
        amount = Decimal(str(cost))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def dig_flat_reasoning_tokens(payload: object) -> int | None:
    """Safely extract ``usage.reasoning_tokens`` (top level of ``usage``).

    Args:
        payload: The decoded JSON response (untrusted shape).

    Returns:
        The reasoning-token count, or ``None`` when absent or unusable.

    Note:
        This is the flat sibling of :func:`dig_reasoning_tokens`, which reads
        the OpenAI-shaped ``usage.completion_tokens_details.reasoning_tokens``.
        A Modal Auto Endpoint reports the count one level higher, directly on
        ``usage``, so the nested reader returns ``None`` against it and the
        Modal leg reported no reasoning at all. Recorded in the 2026-08-20
        smoke test (`docs/planning/handoff-modal-deepseek-v4-smoke-test-2026-08-20.md`).
        The same ``None`` versus ``0`` discipline :func:`dig_usage` documents
        applies: an absent block must not be flattened into a reported zero.
    """
    top = as_str_map(payload)
    if top is None:
        return None
    usage = as_str_map(top.get("usage"))
    if usage is None:
        return None
    return coerce_token_count(usage.get("reasoning_tokens"))


def elapsed_ms(start: float) -> int:
    """Return whole milliseconds elapsed since a :func:`time.monotonic` reading.

    Monotonic rather than wall-clock so a clock adjustment mid-call cannot
    produce a negative or absurd duration.

    Args:
        start: The :func:`time.monotonic` value captured before the work.

    Returns:
        Elapsed milliseconds, rounded to the nearest integer and floored at
        zero.
    """
    return max(0, round((time.monotonic() - start) * 1000))


async def run_with_retries(
    attempt: Callable[[], Awaitable[Completion]],
    *,
    provider: str,
    model: str,
    max_retries: int,
    backoff_base_seconds: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Completion:
    """Drive ``attempt`` with transient-only exponential-backoff retries.

    The returned :class:`~cyo_adventure.generation.usage.Completion` carries
    the duration of the **successful** attempt only. Retried attempts are
    excluded deliberately: a transient failure is typically a 429 or a
    connection error, which is not billed, so folding its duration into the
    usage record would inflate a figure meant to price the work that was
    actually done. The retry itself is already visible in the
    ``provider.transient_retry`` log line.

    Args:
        attempt: A zero-arg coroutine performing one HTTP attempt; returns the
            completion and its usage, or raises :class:`ProviderError`.
        provider: Provider/leg name for logs and the exhaustion error.
        model: Model id for logs and the exhaustion error.
        max_retries: Number of attempts for transient failures.
        backoff_base_seconds: Base for backoff; attempt *n* (1-indexed) waits
            ``backoff_base_seconds * 2**n`` seconds before the next try. ``0``
            disables sleeping (tests).
        sleep: Injectable async sleep (defaults to :func:`asyncio.sleep`).

    Returns:
        The completion from the first successful attempt.

    Raises:
        ProviderError: Immediately if an attempt raises a leg-fatal error; or
            with ``leg_fatal=False`` after all transient retries are exhausted.
        ValueError: If ``max_retries`` is less than 1; a zero/negative count
            would skip ``attempt`` entirely yet raise an exhaustion error,
            misreporting a failure that never ran.
    """
    if max_retries < 1:
        msg = f"max_retries must be >= 1, got {max_retries}"
        raise ValueError(msg)
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
                # 2 ** (index + 1) rewritten as 2 ** index * 2 (identical
                # value: 2**(n+1) == 2**n * 2): `**` binds tighter than `*`
                # here, so the parens the previous form needed to force
                # `index + 1` to evaluate before `**` are no longer needed
                # (S1110), and the exponential-backoff schedule is unchanged.
                await sleep(backoff_base_seconds * 2**index * 2)

    logger.warning(
        "provider.retries_exhausted",
        provider=f"{provider}:{model}",
        attempts=max_retries,
        error=str(last_exc),
    )
    # Carry the LAST attempt's own message into the exhaustion error. The
    # flattened form hid the cause from every recorded leg error: the
    # 2026-08-20/21 live rounds lost 4 of 15 (skeleton, brief) pairs to
    # zero-content stops whose raw `finish_reason` was `content_filter` or
    # None, and each was journalled only as "transient failure persisted"
    # (`AL-492`/`AL-517`/`UW-C309`). `raise ... from` preserves the chain for
    # logs, but harness journals record `str(exc)`, so the cause has to live
    # in the message itself.
    msg = (
        f"{provider} transient failure persisted after {max_retries} attempts "
        f"(last: {last_exc})"
    )
    raise ProviderError(
        msg, provider=provider, model=model, leg_fatal=False
    ) from last_exc
