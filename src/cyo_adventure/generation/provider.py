"""Generation provider protocol and deterministic mock test double.

Defines the ``GenerationProvider`` structural protocol that all LLM backend
adapters must satisfy, the ``MockProvider`` test double used in unit and
integration tests for the orchestrator, and ``build_provider`` which
constructs the appropriate backend from the application settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyo_adventure.core.config import Settings

from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError
from cyo_adventure.generation.providers import (
    FallbackProvider,
    OllamaProvider,
    OpenRouterProvider,
)

# #ASSUME: external-resources: concrete GenerationProvider implementations
# perform network I/O to an LLM endpoint (timeouts, retries, authentication).
# #VERIFY: Phase 2b wiring adds timeout/retry/backoff logic and credentials
# management before any real provider is injected. MockProvider is pure and
# performs no I/O; the note above applies only to future concrete adapters.

# ---------------------------------------------------------------------------
# Phase-2 canned story: the minimal valid Tier-1 Storybook used by the mock
# provider so the full pipeline runs end-to-end deterministically in-phase.
# Phase 2b swaps this for real LLM-generated content.
# ---------------------------------------------------------------------------
_CANNED_STORY: dict[str, object] = {
    "schema_version": "1.0",
    "id": "s_mock_generated",
    "version": 1,
    "title": "The Forest Path",
    "metadata": {
        "age_band": "8-11",
        "reading_level": {"scheme": "flesch_kincaid", "target": 3.0, "tolerance": 1.0},
        "tier": 1,
        "themes": ["adventure", "friendship"],
        "estimated_minutes": 5,
        "ending_count": 1,
        "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
    },
    "variables": [],
    "start_node": "n_start",
    "nodes": [
        {
            "id": "n_start",
            "body": (
                "You step onto the forest path. Sunlight filters through the leaves. "
                "A small rabbit hops across the trail ahead of you."
            ),
            "is_ending": False,
            "choices": [
                {
                    "id": "c_follow",
                    "label": "Follow the rabbit.",
                    "target": "n_happy_end",
                }
            ],
        },
        {
            "id": "n_happy_end",
            "body": (
                "The rabbit leads you to a clearing filled with wildflowers. "
                "You spend a perfect afternoon exploring together."
            ),
            "is_ending": True,
            "ending": {
                "id": "e_meadow",
                "type": "happy",
                "title": "The Flower Meadow",
            },
            "choices": [],
        },
    ],
}

_CANNED_STORY_JSON: str = json.dumps(_CANNED_STORY)


class GenerationProvider(Protocol):
    """Structural protocol for LLM completion backends.

    Any object with a matching ``complete`` coroutine satisfies this protocol;
    no explicit inheritance is required (structural subtyping).

    Concrete implementations are expected to perform network I/O to an
    external LLM endpoint; see the RAD note at the top of this module.
    """

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
    ) -> str:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions for the model.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The raw text completion from the model.
        """
        ...


@dataclass
class MockProvider:
    """Deterministic GenerationProvider test double.

    Returns queued responses in order. A response item may be a plain string
    (returned verbatim) or a callable that receives the user prompt and returns
    a string (so a test can return stage-appropriate output based on prompt
    content). Every prompt passed to complete() is recorded in ``calls`` so
    tests can assert what was sent (e.g. that no PII leaked).

    Args:
        responses: Ordered list of responses to return. Each element is either
            a ``str`` (returned verbatim) or a ``Callable[[str], str]``
            (called with the user prompt, return value used as response).
        calls: Accumulates every ``prompt`` argument received, in call order.

    Raises:
        BusinessLogicError: When ``complete`` is called more times than there
            are queued responses. An over-call indicates a test or orchestrator
            bug, so failing loudly is the correct behaviour.

    Example:
        >>> import asyncio
        >>> provider = MockProvider(responses=["hello", "world"])
        >>> asyncio.run(provider.complete(system="s", prompt="p1", max_tokens=10))
        'hello'
        >>> asyncio.run(provider.complete(system="s", prompt="p2", max_tokens=10))
        'world'
        >>> provider.calls
        ['p1', 'p2']
    """

    responses: list[str | Callable[[str], str]]
    calls: list[str] = field(default_factory=list)

    async def complete(
        self,
        *,
        system: str,  # noqa: ARG002
        prompt: str,
        max_tokens: int,  # noqa: ARG002
    ) -> str:
        """Return the next queued response, recording the prompt in ``calls``.

        ``system`` and ``max_tokens`` are accepted to satisfy the protocol but
        are not used by this mock; they exist to match the real provider
        signature so the mock can be passed wherever a ``GenerationProvider``
        is expected.

        Args:
            system: Accepted but unused by the mock; satisfies the protocol.
            prompt: User-role prompt; recorded in ``self.calls``.
            max_tokens: Accepted but unused by the mock; satisfies the protocol.

        Returns:
            The next queued response string (or callable result).

        Raises:
            BusinessLogicError: If the response queue is exhausted.
        """
        self.calls.append(prompt)
        call_number = len(self.calls)
        n_queued = len(self.responses)

        if call_number > n_queued:
            msg = (
                f"MockProvider exhausted: {n_queued} responses queued,"
                f" call {call_number} received"
            )
            raise BusinessLogicError(msg, rule="mock_provider_exhausted")

        response = self.responses[call_number - 1]
        if callable(response):
            return response(prompt)
        return response


def _build_openrouter_leg(settings: Settings, model: str) -> GenerationProvider:
    """Construct a single OpenRouter leg for ``model`` from settings.

    Args:
        settings: The application settings instance.
        model: The OpenRouter model id this leg targets.

    Returns:
        An OpenRouter ``GenerationProvider`` adapter.

    Raises:
        ConfigurationError: If ``OPENROUTER_API_KEY`` is not configured. The
            message names the key only, never its value.
    """
    # #CRITICAL: security: fail fast (and by name only) when the credential is
    # absent, rather than sending an unauthenticated request that leaks the
    # prompt to a 401 round-trip.
    # #VERIFY: test_build_provider asserts ConfigurationError when the key is None
    # and that the message does not contain a key value.
    if not settings.openrouter_api_key:
        msg = (
            "OPENROUTER_API_KEY is not set; required for generation_provider=openrouter"
        )
        raise ConfigurationError(msg)

    return OpenRouterProvider(
        api_key=settings.openrouter_api_key,
        model=model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        effort=settings.llm_effort,
    )


def _split_basic_auth(value: str | None) -> tuple[str | None, str | None]:
    """Split an ``OLLAMA_AUTH`` ``user:password`` string into its two halves.

    Splits on the FIRST colon only: per RFC 7617 a Basic-auth userid cannot
    contain a colon, but the password may, so ``partition`` preserves a password
    that itself contains colons. A ``None`` or empty/whitespace value, or one
    with no colon, yields ``(None, None)`` so the adapter sends no credential
    (and an auth-proxied host then answers the leg-fatal 302).

    Args:
        value: The raw ``ollama_auth`` setting (``user:password`` or ``None``).

    Returns:
        ``(username, password)`` when a well-formed pair is present, else
        ``(None, None)``.
    """
    if value is None or not value.strip() or ":" not in value:
        return None, None
    username, _, password = value.partition(":")
    if not username or not password:
        return None, None
    return username, password


def _build_ollama_leg(settings: Settings) -> GenerationProvider:
    """Construct the local Ollama leg from settings.

    Args:
        settings: The application settings instance.

    Returns:
        An Ollama ``GenerationProvider`` adapter.
    """
    # Basic-auth is optional: a direct local Ollama needs none, the auth-proxied
    # homelab host needs it. The adapter attaches Basic auth only when both halves
    # are present and maps the 302 auth challenge to a leg-fatal error.
    username, password = _split_basic_auth(settings.ollama_auth)
    return OllamaProvider(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        # Ollama gets its own, longer timeout: the single-parallel homelab host can
        # take minutes to first byte when a prior request holds the execution slot.
        timeout_seconds=settings.ollama_timeout_seconds,
        username=username,
        password=password,
    )


def build_provider(settings: Settings) -> GenerationProvider:
    """Construct a :class:`GenerationProvider` from application settings.

    Mapping from ``settings.generation_provider``:

    - ``"mock"`` (default): a :class:`MockProvider` seeded with the canned story.
      CI and local runs use this so they never make live calls.
    - ``"openrouter"``: the primary OpenRouter leg. When
      ``settings.provider_fallback_enabled`` is ``True`` (default) it is wrapped
      in a :class:`~cyo_adventure.generation.providers.fallback.FallbackProvider`
      cascade ``[openrouter:primary, openrouter:fallback_model, ollama]``; when
      ``False`` the bare primary leg is returned so a yield/comparison run can
      measure one leg in isolation.
    - ``"ollama"``: the local Ollama leg alone (offline path and comparison
      target).
    - ``"claude"``: a direct-Anthropic adapter is deferred; raises
      :class:`ConfigurationError`. Reach Claude via OpenRouter instead.

    Live adapters are constructed only for the provider actually selected, so the
    default mock path opens no client and validates no credential.

    Args:
        settings: The application settings instance.

    Returns:
        A :class:`GenerationProvider` ready for injection into the worker.

    Raises:
        ConfigurationError: For ``"claude"`` (deferred) or when the OpenRouter
            credential is missing.
    """
    provider = settings.generation_provider
    if provider == "mock":
        # Queue enough copies for Stage A + Stage B + up to 3 repairs.
        # Extra copies are safe: MockProvider raises only if the queue is
        # exhausted before the pipeline finishes, not if there are leftovers.
        return MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    if provider == "ollama":
        return _build_ollama_leg(settings)

    if provider == "openrouter":
        primary = _build_openrouter_leg(settings, settings.openrouter_model)
        if not settings.provider_fallback_enabled:
            return primary
        return FallbackProvider(
            legs=[
                primary,
                _build_openrouter_leg(settings, settings.openrouter_fallback_model),
                _build_ollama_leg(settings),
            ]
        )

    # "claude": a direct Anthropic SDK adapter is deferred (ADR-003); the seam
    # stays so it is a trivial future add. Reach Claude via OpenRouter.
    msg = (
        "generation_provider='claude' (direct Anthropic) is deferred; reach "
        "Claude via generation_provider=openrouter with an anthropic/* model"
    )
    raise ConfigurationError(msg)


def make_canned_story_response(story_dict: dict[str, object]) -> str:
    """Serialize a story dict to JSON for use as a queued MockProvider response.

    A convenience factory so later work-packages and tests can queue a
    valid Storybook JSON payload without repeating ``json.dumps`` calls.

    Args:
        story_dict: A dictionary representing a Storybook structure.

    Returns:
        A JSON string suitable for queuing in ``MockProvider.responses``.

    Example:
        >>> import json
        >>> payload = make_canned_story_response({"id": "s_test", "title": "T"})
        >>> json.loads(payload)["id"]
        's_test'
    """
    return json.dumps(story_dict)
