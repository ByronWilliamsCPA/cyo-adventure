"""Unit tests for the Modal adapter's finish_reason split and flat usage shape.

Mirrors ``test_openrouter_provider_pin.py``: ``ModalProvider._extract_completion``
shares the same "empty content plus finish_reason=length is a budget failure,
not a dead endpoint" split OpenRouter's adapter has (AL-329), and additionally
must read reasoning tokens from Modal's own flat ``usage.reasoning_tokens``
shape rather than OpenRouter's nested
``usage.completion_tokens_details.reasoning_tokens`` (2026-08-20 smoke test).

All HTTP is faked with ``httpx.MockTransport``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.providers import ModalProvider


def _client_returning(payload: dict[str, Any]) -> tuple[list[int], httpx.AsyncClient]:
    """Return an attempt counter and a client answering with one fixed payload.

    Args:
        payload: The JSON body every attempt receives.

    Returns:
        The list appended to once per attempt, and the client to inject.
    """
    attempts: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        """Count the attempt and answer with the fixed payload."""
        attempts.append(1)
        return httpx.Response(200, json=payload)

    return attempts, httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _leg(client: httpx.AsyncClient, *, max_retries: int = 3) -> ModalProvider:
    """Build a ModalProvider over an injected client with no backoff sleep.

    Args:
        client: The MockTransport-backed client.
        max_retries: Attempts for transient failures (default 3, matching the
            adapter's own default).

    Returns:
        The adapter.
    """
    return ModalProvider(
        base_url="https://example--cyo-standard.modal.run/v1",
        model="google/gemma-4-26b-a4b-it",
        proxy_key=None,
        proxy_secret=None,
        timeout_seconds=5,
        max_retries=max_retries,
        backoff_base_seconds=0,
        client=client,
    )


@pytest.mark.asyncio
async def test_a_completion_truncated_at_the_budget_is_not_retried() -> None:
    """A budget failure must cost one attempt, not three.

    An empty body from a truncated completion and an empty body from a dead
    endpoint are the same bytes; only ``finish_reason`` tells them apart.
    Retrying a deterministic budget exhaustion at the same cap would just
    re-buy the same wall, and as leg 3 there is no further leg to fall
    through to, so this must raise leg-fatal on the first attempt.
    """
    attempts, client = _client_returning(
        {
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"reasoning_tokens": 30872},
        }
    )

    leg = _leg(client)

    with pytest.raises(ProviderError, match="hit the token budget") as excinfo:
        _ = await leg.complete(system="s", prompt="p", max_tokens=10)

    assert len(attempts) == 1
    assert excinfo.value.leg_fatal is True
    # The reasoning spend is named in the message, because run_with_retries logs
    # the exception string and that log is where an operator sees this first.
    assert "30872" in str(excinfo.value)


@pytest.mark.asyncio
async def test_an_empty_body_without_a_length_reason_is_still_retried() -> None:
    """Not every empty body is a budget failure; a dead endpoint is transient."""
    attempts, client = _client_returning(
        {"choices": [{"message": {"content": ""}, "finish_reason": "error"}]}
    )

    leg = _leg(client)

    with pytest.raises(ProviderError, match="transient failure persisted") as excinfo:
        _ = await leg.complete(system="s", prompt="p", max_tokens=10)

    assert len(attempts) == 3
    assert excinfo.value.leg_fatal is False


@pytest.mark.asyncio
async def test_an_empty_body_with_no_finish_reason_at_all_is_still_retried() -> None:
    """An absent ``finish_reason`` is treated the same as a non-length one."""
    attempts, client = _client_returning({"choices": [{"message": {"content": ""}}]})

    leg = _leg(client)

    with pytest.raises(ProviderError, match="transient failure persisted") as excinfo:
        _ = await leg.complete(system="s", prompt="p", max_tokens=10)

    assert len(attempts) == 3
    assert excinfo.value.leg_fatal is False


@pytest.mark.asyncio
async def test_a_successful_completion_carries_finish_reason_and_reasoning() -> None:
    """A successful body's finish_reason and flat reasoning tokens both reach
    the returned Completion/TokenUsage.
    """
    _attempts, client = _client_returning(
        {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "reasoning_tokens": 42,
            },
        }
    )

    completion = await _leg(client).complete(system="s", prompt="p", max_tokens=10)

    assert completion.finish_reason == "stop"
    assert completion.usage.reasoning_tokens == 42
    assert completion.usage.output_tokens == 5


@pytest.mark.asyncio
async def test_a_nested_reasoning_tokens_shape_is_not_read() -> None:
    """A body carrying ONLY the nested (OpenRouter-shaped) reasoning field
    must not be read by the Modal adapter.

    Modal reports reasoning tokens flat on ``usage``
    (``dig_flat_reasoning_tokens``), not nested under
    ``completion_tokens_details`` (``dig_reasoning_tokens``, the OpenRouter
    shape). This is the discriminating half of the flat-vs-nested split: it
    must fail if ``_extract_completion`` is ever swapped back to reading the
    nested helper.
    """
    _attempts, client = _client_returning(
        {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "completion_tokens_details": {"reasoning_tokens": 200},
            },
        }
    )

    completion = await _leg(client).complete(system="s", prompt="p", max_tokens=10)

    assert completion.usage.reasoning_tokens is None


@pytest.mark.asyncio
async def test_a_flat_reasoning_tokens_shape_is_read() -> None:
    """A body carrying ONLY the flat (Modal-shaped) reasoning field is read.

    The other half of the discriminating pair above: with no nested block
    present at all, the flat value must still come through.
    """
    _attempts, client = _client_returning(
        {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "reasoning_tokens": 77,
            },
        }
    )

    completion = await _leg(client).complete(system="s", prompt="p", max_tokens=10)

    assert completion.usage.reasoning_tokens == 77
