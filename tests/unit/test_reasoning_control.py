"""Unit tests for explicit reasoning control on OpenRouter (AL-847).

Omitting ``reasoning`` did not stop a reasoning model from reasoning in the
WP-2.3 paid smoke, so a model configured as reasoning-capable must never be
sent a request without an explicit setting. All HTTP is faked with
``httpx.MockTransport``; no test calls a model.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal
from unittest import mock

import httpx
import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.generation.provider import (
    build_openrouter_cost_reporting_leg,
    build_openrouter_leg,
)
from cyo_adventure.generation.providers import OpenRouterProvider
from cyo_adventure.generation.reasoning import (
    ReasoningControl,
    current_reasoning,
    explicit_reasoning,
)

_LISTED = ("anthropic/claude-sonnet-5.5", "deepseek/deepseek-v4-flash")
_EFFORTS: tuple[Literal["off", "low", "medium", "high"], ...] = (
    "off",
    "low",
    "medium",
    "high",
)
_CONTROLS = (
    None,
    ReasoningControl.disabled(),
    ReasoningControl(effort="low"),
    ReasoningControl(max_tokens=2_048),
)


def _capture() -> tuple[list[dict[str, Any]], httpx.AsyncClient]:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok": true}'}}]}
        )

    return bodies, httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _leg_kwargs(settings: Settings, model: str, *, cost: bool) -> dict[str, Any]:
    recorded: dict[str, Any] = {}

    def _record(**kwargs: Any) -> object:
        recorded.update(kwargs)
        return object()

    with mock.patch(
        "cyo_adventure.generation.provider.OpenRouterProvider", side_effect=_record
    ):
        if cost:
            build_openrouter_cost_reporting_leg(settings, model)
        else:
            build_openrouter_leg(settings, model)
    return recorded


async def _body(
    provider: OpenRouterProvider, bodies: list[dict[str, Any]]
) -> dict[str, Any]:
    await provider.complete(system="s", prompt="p", max_tokens=8_000)
    return bodies[-1]


# ---------------------------------------------------------------------------
# The control value and its scope
# ---------------------------------------------------------------------------


def test_a_control_is_exactly_one_form() -> None:
    with pytest.raises(ConfigurationError, match="exactly one"):
        ReasoningControl()
    with pytest.raises(ConfigurationError, match="exactly one"):
        ReasoningControl(effort="low", max_tokens=2_048)
    with pytest.raises(ConfigurationError, match="at least 1024"):
        ReasoningControl(max_tokens=512)


def test_controls_render_openrouters_documented_shapes() -> None:
    assert ReasoningControl.disabled().to_openrouter() == {"effort": "none"}
    assert ReasoningControl(effort="low").to_openrouter() == {"effort": "low"}
    assert ReasoningControl(max_tokens=4_096).to_openrouter() == {"max_tokens": 4_096}
    assert ReasoningControl.from_settings("low", None) == ReasoningControl(effort="low")
    assert ReasoningControl.from_settings("low", 3_000) == ReasoningControl(
        max_tokens=3_000
    )


def test_explicit_reasoning_is_scoped_and_reset() -> None:
    assert current_reasoning() is None
    control = ReasoningControl.disabled()
    with explicit_reasoning(control):
        assert current_reasoning() == control
    assert current_reasoning() is None
    with pytest.raises(RuntimeError), explicit_reasoning(control):
        raise RuntimeError
    assert current_reasoning() is None


@pytest.mark.asyncio
async def test_explicit_reasoning_does_not_leak_into_a_sibling_task() -> None:
    seen: list[ReasoningControl | None] = []
    started = asyncio.Event()

    async def inside() -> None:
        with explicit_reasoning(ReasoningControl(effort="low")):
            started.set()
            await asyncio.sleep(0)
            seen.append(current_reasoning())

    async def outside() -> None:
        await started.wait()
        seen.append(current_reasoning())

    await asyncio.gather(inside(), outside())
    assert ReasoningControl(effort="low") in seen
    assert None in seen


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("model", _LISTED)
@pytest.mark.parametrize("effort", _EFFORTS)
@pytest.mark.parametrize("control", _CONTROLS)
@pytest.mark.parametrize("cost", [False, True])
@pytest.mark.parametrize("scoped", [False, True])
async def test_every_body_for_a_listed_model_carries_explicit_reasoning(
    model: str,
    effort: Literal["off", "low", "medium", "high"],
    control: ReasoningControl | None,
    cost: bool,
    scoped: bool,
) -> None:
    """AL-847: a configured reasoning-capable model is never sent nothing."""
    settings = Settings(
        openrouter_api_key="test-key",
        llm_effort=effort,
        llm_reasoning_capable_models=list(_LISTED),
    )
    kwargs = _leg_kwargs(settings, model, cost=cost)
    assert kwargs["reasoning_capable_models"] == frozenset(_LISTED)
    bodies, client = _capture()
    provider = OpenRouterProvider(
        **kwargs,
        client=client,
        backoff_base_seconds=0.0,
        reasoning=None if scoped else control,
    )
    if scoped and control is not None:
        with explicit_reasoning(control):
            body = await _body(provider, bodies)
    else:
        body = await _body(provider, bodies)
    assert "reasoning" in body
    if control is not None:
        assert body["reasoning"] == control.to_openrouter()
    elif effort == "off":
        assert body["reasoning"] == {"effort": "none"}
    else:
        assert body["reasoning"] == {"effort": effort}


@pytest.mark.asyncio
async def test_an_unlisted_model_with_effort_off_still_omits_reasoning() -> None:
    """Production default: no model is listed, so no request body changes."""
    assert Settings().llm_reasoning_capable_models == []
    kwargs = _leg_kwargs(
        Settings(openrouter_api_key="test-key"),
        "anthropic/claude-sonnet-4.6",
        cost=False,
    )
    bodies, client = _capture()
    provider = OpenRouterProvider(**kwargs, client=client, backoff_base_seconds=0.0)
    assert "reasoning" not in await _body(provider, bodies)


@pytest.mark.asyncio
async def test_a_scoped_control_wins_over_the_leg_and_its_effort() -> None:
    bodies, client = _capture()
    provider = OpenRouterProvider(
        api_key="k",
        model="vendor/model",
        base_url="https://example.invalid",
        timeout_seconds=5,
        effort="high",
        backoff_base_seconds=0.0,
        client=client,
        reasoning=ReasoningControl(effort="low"),
    )
    assert (await _body(provider, bodies))["reasoning"] == {"effort": "low"}
    with explicit_reasoning(ReasoningControl.disabled()):
        assert (await _body(provider, bodies))["reasoning"] == {"effort": "none"}


@pytest.mark.asyncio
async def test_a_budget_at_or_above_max_tokens_is_refused_before_any_call() -> None:
    bodies, client = _capture()
    provider = OpenRouterProvider(
        api_key="k",
        model="vendor/model",
        base_url="https://example.invalid",
        timeout_seconds=5,
        effort="off",
        backoff_base_seconds=0.0,
        client=client,
        reasoning=ReasoningControl(max_tokens=8_000),
    )
    with pytest.raises(ConfigurationError, match="below the request max_tokens"):
        await provider.complete(system="s", prompt="p", max_tokens=8_000)
    assert bodies == []


def test_plan_reasoning_settings_default_to_the_measured_effort() -> None:
    settings = Settings()
    assert settings.story_plan_reasoning_effort == "low"
    assert settings.story_plan_reasoning_max_tokens is None
