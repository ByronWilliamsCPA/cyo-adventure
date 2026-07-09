"""Generation provider protocol and deterministic mock test double.

Defines the ``GenerationProvider`` structural protocol that all LLM backend
adapters must satisfy, the ``MockProvider`` test double used in unit and
integration tests for the orchestrator, and ``build_provider`` which
constructs the appropriate backend from the application settings.
"""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyo_adventure.core.config import Settings

from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError
from cyo_adventure.generation.providers import (
    AnthropicProvider,
    FallbackProvider,
    ModalProvider,
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
    "schema_version": "2.0",
    "id": "s_mock_generated",
    "version": 1,
    "title": "The Forest Path",
    "metadata": {
        "age_band": "8-11",
        "reading_level": {"scheme": "flesch_kincaid", "target": 3.0, "tolerance": 1.0},
        "tier": 1,
        "themes": ["adventure", "friendship"],
        "estimated_minutes": 5,
        "ending_count": 4,
        "topology": "time_cave",
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
                    "label": "Follow the rabbit into the trees.",
                    "target": "n_clearing_fork",
                },
                {
                    "id": "c_rest",
                    "label": "Sit on a mossy log to rest.",
                    "target": "n_rest_fork",
                },
            ],
        },
        {
            "id": "n_clearing_fork",
            "body": (
                "The rabbit pauses where the path splits. One way smells of flowers; "
                "the other hums with running water."
            ),
            "is_ending": False,
            "choices": [
                {
                    "id": "c_meadow",
                    "label": "Walk toward the flowers.",
                    "target": "n_happy_end",
                },
                {
                    "id": "c_stream",
                    "label": "Follow the sound of water.",
                    "target": "n_stream_end",
                },
            ],
        },
        {
            "id": "n_rest_fork",
            "body": (
                "On the log you catch your breath. A sleepy warmth tugs at you, "
                "but a hollow tree nearby looks worth a closer look."
            ),
            "is_ending": False,
            "choices": [
                {
                    "id": "c_nap",
                    "label": "Close your eyes for a moment.",
                    "target": "n_nap_end",
                },
                {
                    "id": "c_explore",
                    "label": "Peek inside the hollow tree.",
                    "target": "n_explore_end",
                },
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
                "valence": "positive",
                "kind": "success",
                "title": "The Flower Meadow",
            },
            "choices": [],
        },
        {
            "id": "n_stream_end",
            "body": (
                "The stream opens into a pool where silver fish dart. "
                "You skip stones until the sun dips low."
            ),
            "is_ending": True,
            "ending": {
                "id": "e_stream",
                "valence": "neutral",
                "kind": "discovery",
                "title": "The Hidden Pool",
            },
            "choices": [],
        },
        {
            "id": "n_nap_end",
            "body": (
                "You doze in a patch of sun. When you wake, the forest feels like "
                "an old friend, and the path home is easy to find."
            ),
            "is_ending": True,
            "ending": {
                "id": "e_nap",
                "valence": "positive",
                "kind": "completion",
                "title": "A Restful Afternoon",
            },
            "choices": [],
        },
        {
            "id": "n_explore_end",
            "body": (
                "Inside the hollow tree you find a tiny door no taller than your hand. "
                "You leave it be, but you will be back tomorrow."
            ),
            "is_ending": True,
            "ending": {
                "id": "e_explore",
                "valence": "positive",
                "kind": "success",
                "title": "The Tiny Door",
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


def build_openrouter_leg(settings: Settings, model: str) -> GenerationProvider:
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


def build_anthropic_leg(settings: Settings, model: str) -> GenerationProvider:
    """Construct a single direct-Anthropic leg for ``model`` from settings.

    This builder is a standalone unit (WS-C PR1 Task 7): it is not yet wired
    into :func:`build_provider`'s dispatch, which still raises
    ``ConfigurationError`` for ``generation_provider=anthropic`` pending the
    per-job override plumbing in a later task.

    Args:
        settings: The application settings instance.
        model: The Anthropic model id this leg targets.

    Returns:
        A direct-Anthropic ``GenerationProvider`` adapter.

    Raises:
        ConfigurationError: If ``ANTHROPIC_API_KEY`` is not configured. The
            message names the key only, never its value.
    """
    # #CRITICAL: security: fail fast (and by name only) when the credential is
    # absent, rather than sending an unauthenticated request that leaks the
    # prompt to a 401 round-trip.
    # #VERIFY: test_missing_key_raises_configuration_error_by_name and
    # test_anthropic_key_value_not_leaked_in_error assert ConfigurationError
    # when the key is None, and that no error message ever contains a key value.
    if not settings.anthropic_api_key:
        msg = "ANTHROPIC_API_KEY is not set; required for generation_provider=anthropic"
        raise ConfigurationError(msg)

    return AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=model,
        base_url=settings.anthropic_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def build_modal_leg(settings: Settings) -> GenerationProvider:
    """Construct the experimental Modal leg from settings (ADR-010 item 2).

    Args:
        settings: The application settings instance.

    Returns:
        A bare Modal ``GenerationProvider`` adapter. Never wrapped in a
        :class:`~cyo_adventure.generation.providers.fallback.FallbackProvider`
        cascade: this leg is an offline experiment, not on the production path.

    Raises:
        ConfigurationError: If ``MODAL_BASE_URL`` or ``MODAL_MODEL`` is not
            configured, or if exactly one of ``MODAL_PROXY_KEY`` and
            ``MODAL_PROXY_SECRET`` is set: a half-set credential pair is a
            misconfiguration to reject, not a valid no-auth state to guess at.
    """
    # #CRITICAL: security: fail fast (and by name only) when required config is
    # absent, rather than sending a request to an unconfigured/placeholder url.
    # #VERIFY: test_build_provider asserts ConfigurationError names the missing
    # setting and never echoes a value.
    if not settings.modal_base_url:
        msg = "MODAL_BASE_URL is not set; required for generation_provider=modal"
        raise ConfigurationError(msg)
    if not settings.modal_model:
        msg = "MODAL_MODEL is not set; required for generation_provider=modal"
        raise ConfigurationError(msg)

    has_key = bool(settings.modal_proxy_key)
    has_secret = bool(settings.modal_proxy_secret)
    if has_key != has_secret:
        msg = (
            "MODAL_PROXY_KEY and MODAL_PROXY_SECRET must be set together "
            "(or neither); found only one"
        )
        raise ConfigurationError(msg)

    return ModalProvider(
        base_url=settings.modal_base_url,
        model=settings.modal_model,
        proxy_key=settings.modal_proxy_key,
        proxy_secret=settings.modal_proxy_secret,
        timeout_seconds=settings.modal_timeout_seconds,
    )


def _split_basic_auth(value: str | None) -> tuple[str | None, str | None]:
    """Split an ``OLLAMA_AUTH`` ``user:password`` string into its two halves.

    Splits on the FIRST colon only: per RFC 7617 a Basic-auth userid cannot
    contain a colon, but the password may, so ``partition`` preserves a password
    that itself contains colons. A ``None`` or empty/whitespace value, or one
    with no colon, yields ``(None, None)`` so the adapter sends no credential
    (and an auth-proxied host then answers the leg-fatal 302). Each half is
    stripped of surrounding whitespace: a dotenv entry with stray spaces around
    the value is far more likely a typo than an intentional whitespace
    credential, and an unstripped half would silently produce an auth failure.

    Args:
        value: The raw ``ollama_auth`` setting (``user:password`` or ``None``).

    Returns:
        ``(username, password)`` when a well-formed pair is present, else
        ``(None, None)``.
    """
    if value is None or not value.strip() or ":" not in value:
        return None, None
    raw_username, _, raw_password = value.partition(":")
    username, password = raw_username.strip(), raw_password.strip()
    if not username or not password:
        return None, None
    return username, password


# Loopback hosts where HTTP Basic auth never crosses a network boundary, so
# cleartext is acceptable; any other host over plain http would put the
# credential on the wire in reversible base64.
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})


def _reject_cleartext_basic_auth(base_url: str) -> None:
    """Refuse to send HTTP Basic credentials over a cleartext, non-loopback URL.

    Basic auth base64-encodes ``user:password`` reversibly, so an ``http://``
    request to a remote host ships the credential in the clear. A misconfigured
    ``OLLAMA_BASE_URL`` (http to a remote host) paired with ``OLLAMA_AUTH`` is a
    credential-exposure bug, so fail fast rather than leak the password.

    Args:
        base_url: The configured Ollama base url.

    Raises:
        ConfigurationError: When the scheme is not https and the host is not a
            loopback address.
    """
    # #CRITICAL: security: Basic auth over plaintext http leaks the credential on
    # the wire; only loopback (never on the network) is exempt.
    # #VERIFY: build raises ConfigurationError for an http://<remote-host> + auth
    # combination (tests/unit/test_worker.py).
    parsed = urlsplit(base_url)
    if parsed.scheme == "https" or parsed.hostname in _LOOPBACK_HOSTS:
        return
    msg = (
        "OLLAMA_AUTH is set but OLLAMA_BASE_URL is not https; HTTP Basic auth "
        "would send the credential in cleartext. Use an https URL, or a local "
        "loopback host for unauthenticated dev."
    )
    raise ConfigurationError(msg)


def build_ollama_leg(
    settings: Settings, model: str | None = None
) -> GenerationProvider:
    """Construct the local Ollama leg from settings.

    Args:
        settings: The application settings instance.
        model: Override the Ollama model to use. Defaults to
            ``settings.ollama_model`` when ``None``.

    Returns:
        An Ollama ``GenerationProvider`` adapter.

    Raises:
        ConfigurationError: When auth is set over cleartext http to a non-loopback
            host, or when ``OLLAMA_CA_BUNDLE`` points at an unusable bundle.
    """
    # Basic-auth is optional: a direct local Ollama needs none, the auth-proxied
    # homelab host needs it. The adapter attaches Basic auth only when both halves
    # are present and maps the 302 auth challenge to a leg-fatal error.
    username, password = _split_basic_auth(settings.ollama_auth)
    if username is not None and password is not None:
        _reject_cleartext_basic_auth(settings.ollama_base_url)
    # TLS verification: default to the public CA store. When a CA bundle is
    # configured (the homelab host serves a Homelab-CA cert until the public
    # wildcard lands), load it ON TOP of the system CAs so verification succeeds
    # under either issuer. This is proper verification, not a bypass.
    verify: ssl.SSLContext | bool = True
    if settings.ollama_ca_bundle:
        ctx = ssl.create_default_context()
        try:
            # ssl.SSLError subclasses OSError, so OSError covers a missing path
            # and a malformed/unreadable PEM. Map both to ConfigurationError so a
            # misconfigured operator gets a named setting, not a raw traceback.
            ctx.load_verify_locations(settings.ollama_ca_bundle)
        except OSError as exc:
            msg = (
                "OLLAMA_CA_BUNDLE points at an unusable CA bundle "
                f"({settings.ollama_ca_bundle!r}): {type(exc).__name__}"
            )
            raise ConfigurationError(msg) from exc
        verify = ctx
    return OllamaProvider(
        model=model if model is not None else settings.ollama_model,
        base_url=settings.ollama_base_url,
        # Ollama gets its own, longer timeout: the single-parallel homelab host can
        # take minutes to first byte when a prior request holds the execution slot.
        timeout_seconds=settings.ollama_timeout_seconds,
        username=username,
        password=password,
        verify=verify,
    )


def build_provider(
    settings: Settings,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> GenerationProvider:
    """Construct a :class:`GenerationProvider` from application settings.

    ``provider_override``/``model_override`` are the per-job factory seam
    (WS-C PR1): the worker reads them off a job's ``authoring_metadata`` and
    passes them here. With both ``None`` this reproduces today's behavior
    exactly for every existing caller.

    Mapping from the resolved provider (``provider_override`` if set, else
    ``settings.generation_provider``):

    - ``"mock"`` (default): a :class:`MockProvider` seeded with the canned
      story. CI and local runs use this so they never make live calls.
      ``model_override`` has no effect (mock has no model concept).
    - ``"ollama"``: the local Ollama leg alone. ``model_override`` replaces
      ``settings.ollama_model`` for this leg only.
    - ``"anthropic"``: the direct-Anthropic leg alone (no cascade).
      ``model_override`` replaces ``settings.anthropic_model``.
    - ``"openrouter"``: the primary OpenRouter leg, using ``model_override``
      in place of ``settings.openrouter_model`` when set. When
      ``settings.provider_fallback_enabled`` is ``True`` (default) it is
      wrapped in a
      :class:`~cyo_adventure.generation.providers.fallback.FallbackProvider`
      cascade ``[primary, openrouter:fallback_model, ollama]`` (the fallback
      leg's model is never overridden); when ``False`` the bare primary leg
      is returned so a yield/comparison run can measure one leg in isolation.
    - ``"modal"``: the experimental Modal leg. ``model_override`` has no
      effect (the offline Modal leg's model is settings-only in PR1; it is
      not part of the per-job override seam).

    Live adapters are constructed only for the provider actually selected, so
    the default mock path opens no client and validates no credential.

    Args:
        settings: The application settings instance.
        provider_override: A per-job provider name (from a job's
            ``authoring_metadata["provider"]``), or ``None`` to use
            ``settings.generation_provider``.
        model_override: A per-job model id (from a job's
            ``authoring_metadata["model"]``), or ``None`` to use the
            resolved provider's default model from settings.

    Returns:
        A :class:`GenerationProvider` ready for injection into the worker.

    Raises:
        ConfigurationError: For a resolved provider outside the known set, or
            when a live provider's required credential is missing.
    """
    provider = provider_override or settings.generation_provider

    if provider == "mock":
        # Queue enough copies for Stage A + Stage B + up to 3 repairs.
        # Extra copies are safe: MockProvider raises only if the queue is
        # exhausted before the pipeline finishes, not if there are leftovers.
        return MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    if provider == "ollama":
        return build_ollama_leg(settings, model_override)

    if provider == "anthropic":
        return build_anthropic_leg(settings, model_override or settings.anthropic_model)

    if provider == "openrouter":
        primary = build_openrouter_leg(
            settings, model_override or settings.openrouter_model
        )
        if not settings.provider_fallback_enabled:
            return primary
        return FallbackProvider(
            legs=[
                primary,
                build_openrouter_leg(settings, settings.openrouter_fallback_model),
                build_ollama_leg(settings),
            ]
        )

    if provider == "modal":
        return build_modal_leg(settings)

    msg = f"unknown generation_provider '{provider}'"
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
