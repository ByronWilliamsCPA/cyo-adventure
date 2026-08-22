"""Structural contract: every provider adapter exposes its model id.

``fill_skeleton`` and ``generate_story`` resolve the output cap (and with it
the chunking decision) from ``getattr(provider, "model", None)``, and the
wrappers (``MeteredProvider``, ``PiiGuardedProvider``) forward the attribute
by getattr. An adapter that does not expose ``model`` therefore forwards
``None`` all the way up, ``MODEL_OUTPUT_CAPS`` is never consulted for it, and
the chunked path can never engage on that backend. That is not hypothetical:
the OpenRouter adapter shipped without the property, a low-cap model was asked
for 131,072 tokens one-shot, and the endpoint rejected the request outright
(HTTP 400 in 0.6s, measured 2026-08-21; `AL-518`/`UW-C323`).

This module pins the contract so the next adapter cannot reintroduce the
blind spot.
"""

from __future__ import annotations

import pytest

from cyo_adventure.generation.metered import MeteredProvider
from cyo_adventure.generation.providers.anthropic import AnthropicProvider
from cyo_adventure.generation.providers.modal import ModalProvider
from cyo_adventure.generation.providers.openrouter import OpenRouterProvider
from cyo_adventure.generation.skeleton import MODEL_OUTPUT_CAPS, resolve_output_cap
from cyo_adventure.generation.usage import UsageLedger

pytestmark = pytest.mark.unit

_MODEL = "deepseek/deepseek-v3.2"


def _adapters() -> list[object]:
    """Construct one instance of every leg adapter with inert credentials."""
    return [
        OpenRouterProvider(
            api_key="test-key",
            model=_MODEL,
            base_url="https://openrouter.invalid/api/v1",
            timeout_seconds=1,
            effort=None,
        ),
        AnthropicProvider(
            api_key="test-key",
            model=_MODEL,
            base_url="https://anthropic.invalid",
            timeout_seconds=1,
        ),
        ModalProvider(
            base_url="https://modal.invalid",
            model=_MODEL,
            proxy_key=None,
            proxy_secret=None,
            timeout_seconds=1,
        ),
    ]


def test_every_provider_adapter_exposes_its_model() -> None:
    """Each leg adapter declares the model id cap resolution reads."""
    for adapter in _adapters():
        assert getattr(adapter, "model", None) == _MODEL, (
            f"{type(adapter).__name__} does not expose .model; cap resolution "
            "falls back to the permissive default and the chunked path can "
            "never engage on this backend (AL-518/UW-C323)"
        )


def test_the_model_survives_the_metered_wrapper_into_cap_resolution() -> None:
    """The end-to-end path that was blind: adapter -> wrapper -> cap.

    A wrapped OpenRouter leg for a low-cap model must resolve that model's
    own cap, not the 131,072 default, because the ask goes into the request
    payload unclamped and an over-ask is rejected by the API rather than
    quietly lowered.
    """
    for adapter in _adapters():
        wrapped = MeteredProvider(adapter, ledger=UsageLedger())  # pyright: ignore[reportArgumentType]
        assert wrapped.model == _MODEL
        assert resolve_output_cap(wrapped.model) == MODEL_OUTPUT_CAPS[_MODEL]
