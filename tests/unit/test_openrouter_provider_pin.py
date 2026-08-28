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
from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.core.pricing import ENDPOINT_PINS, PRICES
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


def _provider(
    client: httpx.AsyncClient,
    order: tuple[str, ...],
    *,
    temperature: float | None = None,
) -> OpenRouterProvider:
    """Build an adapter over the capturing client with the given pin.

    Args:
        client: The MockTransport-backed client.
        order: The backend pin to apply (empty for the default path).
        temperature: The sampling temperature to apply, ``None`` (the default,
            and what every generation caller passes) for the model default.

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
        temperature=temperature,
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


# ---------------------------------------------------------------------------
# Telemetry the retry policy needs (AL-329 / UW-C235)
# ---------------------------------------------------------------------------


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


def _leg(client: httpx.AsyncClient) -> OpenRouterProvider:
    """Build an adapter over an injected client with no real sleeping.

    Args:
        client: The MockTransport-backed client.

    Returns:
        The adapter.
    """
    return OpenRouterProvider(
        api_key="k",
        model="vendor/model",
        base_url="https://example.invalid",
        timeout_seconds=5,
        effort="off",
        backoff_base_seconds=0,
        client=client,
    )


@pytest.mark.asyncio
async def test_a_completion_truncated_at_the_budget_is_not_retried() -> None:
    """A budget failure must cost one attempt, not three.

    An empty body from a truncated completion and an empty body from a dead
    endpoint are the same bytes. Retrying the first re-buys the identical wall
    at the identical cap: the comparison harness spent three attempts at roughly
    eleven minutes and fifty cents each doing exactly that, because no retry
    policy could see ``finish_reason`` (AL-329).
    """
    attempts, client = _client_returning(
        {
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"completion_tokens_details": {"reasoning_tokens": 30872}},
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
    # The exhaustion error is raised `from` the last attempt's, so the reason the
    # body was empty survives into the traceback rather than being replaced by a
    # generic retry message.
    assert "no message content" in str(excinfo.value.__cause__)


@pytest.mark.asyncio
async def test_a_successful_completion_carries_finish_reason_and_reasoning() -> None:
    """Reasoning share must be observable in production, not bought afterwards.

    Cost per delivered book spans 36x across legs asked for the identical book
    while the prose written spans 1.36x, and reasoning share is the discriminator
    (AL-332). It was measured by reissuing calls against the billing API because
    the pipeline recorded nothing.
    """
    _attempts, client = _client_returning(
        {
            "choices": [
                {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 250,
                "completion_tokens_details": {"reasoning_tokens": 200},
            },
        }
    )

    completion = await _leg(client).complete(system="s", prompt="p", max_tokens=10)

    assert completion.finish_reason == "stop"
    assert completion.usage.reasoning_tokens == 200
    assert completion.usage.output_tokens == 250


@pytest.mark.asyncio
async def test_a_backend_reporting_no_reasoning_block_reports_unknown() -> None:
    """Absent must stay None, never 0.

    A provider has been observed reporting ``reasoning_tokens=0`` while emitting
    5,339 characters of reasoning, so a reported zero is already only a claim.
    Flattening an absent block into the same zero would make the two
    indistinguishable and quietly credit a reasoning leg with none.
    """
    _attempts, client = _client_returning(
        {
            "choices": [
                {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 250},
        }
    )

    completion = await _leg(client).complete(system="s", prompt="p", max_tokens=10)

    assert completion.usage.reasoning_tokens is None


# ---------------------------------------------------------------------------
# The priced-endpoint pin on the REQUEST path (D1, ruled 2026-08-23; UW-C346)
# ---------------------------------------------------------------------------
# Until D1, the pin was a measurement-harness affordance and every production
# caller left it empty, which `build_openrouter_leg`'s own docstring recorded as
# a deliberate choice. D1 puts `deepseek/deepseek-v4-pro` on the production fill
# leg, and that slug's PRICES row is the price of ONE of its 18 endpoints
# (`azure/us`). An unpinned production run would therefore be served by the
# slug's default route and costed against a different endpoint's price, and
# would sit anywhere in that slug's 16,384-to-1,048,576 declared output-ceiling
# spread. The pin is what makes the recorded cost the cost that was paid.


def test_a_priced_pin_is_applied_when_the_caller_names_no_order() -> None:
    """A model with a pinned price row is pinned to that endpoint by default."""
    assert _leg_kwargs("deepseek/deepseek-v4-pro")["provider_order"] == ("azure/us",)


def test_a_model_without_a_pin_entry_stays_unpinned() -> None:
    """Absence in the pin table means OpenRouter's own routing, as before."""
    assert _leg_kwargs("deepseek/deepseek-v4-flash")["provider_order"] == ()


def test_an_explicit_empty_order_is_honoured_over_the_table() -> None:
    """An explicit ``()`` means "deliberately unpinned", not "unspecified".

    ``scripts/compare_vendors.py`` passes each vendor fixture's own
    ``provider_order`` verbatim, and some fixtures carry none on purpose (the
    script warns about them rather than inventing a pin). If the table
    overrode an explicit empty tuple, those runs would silently acquire a pin
    the fixture never asked for and stop measuring what they claim to.
    """
    recorded = _leg_kwargs("deepseek/deepseek-v4-pro", provider_order=())

    assert recorded["provider_order"] == ()


def test_an_explicit_order_overrides_the_table() -> None:
    """A caller naming an endpoint outranks the default pin for that slug."""
    recorded = _leg_kwargs("deepseek/deepseek-v4-pro", provider_order=("novita/fp8",))

    assert recorded["provider_order"] == ("novita/fp8",)


def test_every_pinned_model_has_a_price_row() -> None:
    """A pin without a price row would pin an endpoint nothing prices.

    The pin exists to make the recorded price attributable, so a pin whose
    pair carries no price is not a safer default, it is a pin with no purpose.
    """
    assert set(ENDPOINT_PINS) <= set(PRICES)


def test_every_pinned_price_row_names_its_endpoint_in_the_note() -> None:
    """The price row must say which endpoint it priced.

    This is the invariant the whole mechanism rests on: ``PRICES`` holds one
    price per (provider, model) while the slug is served by many endpoints at
    different prices, so the row is only correct with respect to a named
    endpoint. Binding the two here means a future price refresh that silently
    replaces a pinned row with the slug's default-route price fails a test
    instead of quietly overstating or understating every job's cost.
    """
    for key, order in ENDPOINT_PINS.items():
        note = PRICES[key].note
        assert order, f"{key} has an empty pin"
        assert order[0] in note, f"{key} price note does not name {order[0]}"


# ---------------------------------------------------------------------------
# The sampling temperature on the REQUEST path (UW-C408)
# ---------------------------------------------------------------------------
# The moderation reviewer sampled at the vendor default because nothing in
# `src/` sent a `temperature` at all, so two reads of the same passage could
# return different safety verdicts and no before/after comparison in that
# subsystem was falsifiable. The field is therefore per-leg and opt-in:
# generation keeps the default deliberately (`generation/variation.py` buys
# variation with an explicit axis, not with noise), and only the review leg
# pins it. That split is what these two tests hold in place.


@pytest.mark.asyncio
async def test_no_temperature_field_is_sent_by_default() -> None:
    """Absence has to stay absence on the generation path.

    A `temperature` present but defaulted would repoint every existing
    generation measurement, including the vendor-comparison fixtures, the same
    way an always-emitted `provider` field would. The whole point of the
    parameter is that adding it changed no request that existed before it.
    """
    bodies, client = _capture()
    await _provider(client, ()).complete(system="s", prompt="p", max_tokens=16)

    assert "temperature" not in bodies[0]


@pytest.mark.asyncio
async def test_a_review_temperature_is_sent_when_set() -> None:
    """Zero must reach the wire as zero, not be dropped as falsy.

    This is the failure mode worth a test of its own: the one value the
    reviewer actually needs is the one an ``if self._temperature:`` guard would
    silently discard, and a dropped field is indistinguishable on the wire from
    the pre-fix behaviour it exists to correct.
    """
    bodies, client = _capture()
    await _provider(client, (), temperature=0.0).complete(
        system="s", prompt="p", max_tokens=16
    )

    assert bodies[0]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_the_temperature_property_reports_what_the_leg_sends() -> None:
    """The property and the wire body must not be able to disagree.

    ``review_provenance`` persists a temperature into the durable moderation
    report, and a report is only worth keeping if it records what ran. Reading
    the property here against the recorded body is what stops the two becoming
    independent claims about the same request.
    """
    bodies, client = _capture()
    leg = _provider(client, ("Anthropic",), temperature=0.0)
    await leg.complete(system="s", prompt="p", max_tokens=16)

    assert leg.temperature == bodies[0]["temperature"]
    assert list(leg.endpoint_order) == bodies[0]["provider"]["order"]
