"""Unit tests for the OpenRouter backend pin used by the vendor comparison.

One OpenRouter slug is routed across several backends. ``anthropic/claude-
sonnet-4.6`` alone is served by Anthropic, Google, Amazon Bedrock and Azure, so
an unpinned request attributed to "Anthropic" can be answered by Bedrock. The
pin exists so a comparison run measures one backend; these tests assert both
that it is emitted when asked for and that the default path still sends nothing,
since every production caller relies on OpenRouter's own routing.

All HTTP is faked with ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import httpx
import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.generation.provider import build_openrouter_leg
from cyo_adventure.generation.providers import OpenRouterProvider


def _capture() -> tuple[list[dict[str, Any]], httpx.AsyncClient]:
    """Return a body sink and a client whose transport records each request.

    Returns:
        The list that receives each decoded request body, and the client to
        inject into the adapter.
    """
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record the request body and return a minimal success payload."""
        bodies.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok": true}'}}]}
        )

    return bodies, httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _provider(client: httpx.AsyncClient, order: tuple[str, ...]) -> OpenRouterProvider:
    """Build an adapter over the capturing client with the given pin.

    Args:
        client: The MockTransport-backed client.
        order: The backend pin to apply (empty for the default path).

    Returns:
        A configured adapter.
    """
    return OpenRouterProvider(
        api_key="test-key",
        model="anthropic/claude-sonnet-4.6",
        base_url="https://openrouter.test/api/v1",
        timeout_seconds=5,
        effort="off",
        backoff_base_seconds=0.0,
        client=client,
        provider_order=order,
    )


@pytest.mark.asyncio
async def test_openrouter_provider_pin_forbids_fallbacks() -> None:
    """A non-empty pin sends the order verbatim and disallows substitution."""
    bodies, client = _capture()
    await _provider(client, ("Anthropic",)).complete(
        system="s", prompt="p", max_tokens=16
    )

    assert bodies[0]["provider"] == {
        "order": ["Anthropic"],
        "allow_fallbacks": False,
    }


@pytest.mark.asyncio
async def test_openrouter_provider_pin_preserves_preference_order() -> None:
    """A multi-entry pin keeps the caller's ordering, most preferred first."""
    bodies, client = _capture()
    await _provider(client, ("Anthropic", "Amazon Bedrock")).complete(
        system="s", prompt="p", max_tokens=16
    )

    assert bodies[0]["provider"]["order"] == ["Anthropic", "Amazon Bedrock"]


@pytest.mark.asyncio
async def test_openrouter_unpinned_body_has_no_provider_field() -> None:
    """The default path is byte-identical to the pre-pin request.

    Every production caller leaves the pin empty. Emitting an empty ``order``
    with ``allow_fallbacks: false`` would forbid every backend and turn each
    live call into an error, so absence has to mean absence.
    """
    bodies, client = _capture()
    await _provider(client, ()).complete(system="s", prompt="p", max_tokens=16)

    assert "provider" not in bodies[0]
    assert set(bodies[0]) == {"model", "messages", "max_tokens"}


def _leg_kwargs(model: str, **extra: object) -> dict[str, Any]:
    """Capture the kwargs ``build_openrouter_leg`` hands the adapter.

    The factory constructs its own ``httpx`` client, so observing the wire body
    would mean reaching into a private attribute. Recording the constructor call
    instead tests exactly what the factory is responsible for: threading the pin
    through unchanged.

    Args:
        model: The model slug to build a leg for.
        **extra: Extra keyword arguments forwarded to the factory.

    Returns:
        The keyword arguments the factory passed to ``OpenRouterProvider``.
    """
    recorded: dict[str, Any] = {}

    def _record(**kwargs: object) -> object:
        """Stand in for the adapter constructor and record its kwargs."""
        recorded.update(kwargs)
        return object()

    settings = Settings(openrouter_api_key="test-key")
    with mock.patch(
        "cyo_adventure.generation.provider.OpenRouterProvider", side_effect=_record
    ):
        build_openrouter_leg(settings, model, **extra)  # pyright: ignore[reportArgumentType]
    return recorded


def test_build_openrouter_leg_defaults_to_no_pin() -> None:
    """``build_openrouter_leg`` without the keyword leaves routing untouched."""
    assert _leg_kwargs("anthropic/claude-sonnet-4.6")["provider_order"] == ()


def test_build_openrouter_leg_forwards_the_pin() -> None:
    """``build_openrouter_leg`` threads ``provider_order`` to the adapter."""
    recorded = _leg_kwargs("openai/gpt-5.4", provider_order=("OpenAI",))

    assert recorded["provider_order"] == ("OpenAI",)
    assert recorded["model"] == "openai/gpt-5.4"
