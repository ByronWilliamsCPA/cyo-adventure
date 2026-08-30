"""Generation provider protocol and deterministic mock test double.

Defines the ``GenerationProvider`` structural protocol that all LLM backend
adapters must satisfy, the ``MockProvider`` test double used in unit and
integration tests for the orchestrator, and ``build_provider`` which
constructs the appropriate backend from the application settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyo_adventure.core.config import Settings

from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError
from cyo_adventure.core.pricing import endpoint_pin_for
from cyo_adventure.generation.providers import (
    AnthropicProvider,
    FallbackProvider,
    ModalProvider,
    OpenRouterProvider,
)
from cyo_adventure.generation.usage import Completion, TokenUsage
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

# Which actor's request a generation job serves. Not a role: it is the
# constraint that role implies on which billing account the job may reach.
GenerationLane = Literal["family", "admin"]

# #CRITICAL: security: the legs a kid- or guardian-triggered generation may
# reach (D1, ruled 2026-08-23; UW-C346). The direct ``anthropic`` leg is absent
# deliberately: routing family-triggered work through the operator's own
# Anthropic account is outside that account's terms. This set is the only place
# the rule is written down, and ``build_provider`` defaults to the lane it
# constrains, so a new call site that says nothing is restricted, not exempt.
# PUBLIC (no leading underscore) because the rule now has to hold at two
# boundaries, not one: ``build_provider`` refuses a forbidden leg at job time,
# and ``api/provider_allowlist.py`` refuses to ENABLE a row naming one at
# admin-write time. Importing the one set is what keeps those two answers from
# drifting; a second copy in the API layer is how this rule would rot. The
# api -> generation import direction is the sanctioned one (``api/remoderate.py``
# already imports ``build_provider`` from here); the ban recorded in
# tests/unit/test_allowlist.py is on the reverse.
# #VERIFY: tests/unit/test_provider_lane.py::
# TestFamilyLaneRejectsTheDirectAnthropicLeg::test_the_restrictive_lane_is_the_default.
FAMILY_LANE_PROVIDERS: Final[frozenset[str]] = frozenset(
    {"mock", "openrouter", "modal"}
)

# Providers that were once selectable and are now removed. Kept as data rather
# than deleted outright so build_provider can tell "retired" apart from
# "misspelled": persisted job rows and historical GenerationJob attribution
# still carry these names long after the adapter is gone.
RETIRED_PROVIDERS: Final[frozenset[str]] = frozenset({"ollama"})

# What MockProvider reports when a test does not inject its own usage: a call
# that happened (so it is counted) but whose token cost is unknown, never zero.
# Shared as a module constant because a frozen dataclass default has to be a
# single immutable instance, not a per-instance factory.
_MOCK_USAGE: Final[TokenUsage] = TokenUsage(
    provider="mock",
    model="mock",
    input_tokens=None,
    output_tokens=None,
    duration_ms=0,
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
    "start_node": "n_open",
    "nodes": [
        # PL-25 floors the first decision at the second node for this band, so
        # the opening establishes the situation before anything is chosen. The
        # mock story is held to the same rule as a real one on purpose: it is
        # what most of the pipeline tests run through, so letting it violate a
        # gate rule would hide that rule from nearly every end-to-end test.
        {
            "id": "n_open",
            "body": (
                "You step onto the forest path. Sunlight filters through the leaves, "
                "and the air smells of pine and warm earth."
            ),
            "is_ending": False,
            "choices": [
                {
                    "id": "c_open",
                    "label": "Walk on down the path.",
                    "target": "n_start",
                },
            ],
        },
        {
            "id": "n_start",
            "body": (
                "A small rabbit hops across the trail ahead of you and stops. It "
                "turns one ear your way and waits to see what you will do."
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

# ---------------------------------------------------------------------------
# DEV/TEST-ONLY invalid fixture: a structurally broken Storybook the mock
# provider serves when Settings.mock_story_fixture == "invalid". Its single
# non-ending node has an empty ``choices`` list, which the deterministic
# validator gate (validator/) flags as an ERROR-severity topology violation on
# every attempt, so the full pipeline reaches a HARD-BLOCK / needs-review
# outcome that no repair can rescue. This lets the crown-jewel full-pipeline
# test drive the gate to BLOCK over the real HTTP path (review finding S-5).
# The mock provider is forbidden outside local by the provider allowlist, so
# this fixture never ships to a non-local environment.
# ---------------------------------------------------------------------------
_INVALID_STORY: dict[str, object] = {
    "schema_version": "2.0",
    "id": "s_bad_story",
    "version": 1,
    "title": "Bad Story",
    "metadata": {
        "age_band": "8-11",
        "reading_level": {
            "scheme": "flesch_kincaid",
            "target": 3.0,
            "tolerance": 1.0,
        },
        "tier": 1,
        "themes": [],
        "estimated_minutes": 5,
        "ending_count": 1,
        "topology": "branch_and_bottleneck",
        "content_flags": {
            "violence": "none",
            "scariness": "none",
            "peril": "none",
        },
    },
    "variables": [],
    "start_node": "n_start",
    "nodes": [
        # Non-ending node with NO choices: the gate blocks with an L1 error.
        {
            "id": "n_start",
            "body": "You are stuck.",
            "is_ending": False,
            "choices": [],
        }
    ],
}

_INVALID_STORY_JSON: str = json.dumps(_INVALID_STORY)


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
    ) -> Completion:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions for the model.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The raw text completion from the model plus what the call
            consumed. An implementation that cannot report token counts still
            returns a :class:`~cyo_adventure.generation.usage.Completion`, with
            ``None`` counts marking the usage unknown.
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
        token_usage: The usage every completion reports. The default reports
            ``None`` counts: the mock called no model, so its cost is unknown
            rather than zero, and a mock-backed run is correctly summarized as
            incomplete. A test exercising the cost aggregation injects a
            :class:`~cyo_adventure.generation.usage.TokenUsage` with real
            counts here.

    Raises:
        BusinessLogicError: When ``complete`` is called more times than there
            are queued responses. An over-call indicates a test or orchestrator
            bug, so failing loudly is the correct behaviour.

    Example:
        >>> import asyncio
        >>> provider = MockProvider(responses=["hello", "world"])
        >>> asyncio.run(provider.complete(system="s", prompt="p1", max_tokens=10)).text
        'hello'
        >>> asyncio.run(provider.complete(system="s", prompt="p2", max_tokens=10)).text
        'world'
        >>> provider.calls
        ['p1', 'p2']
    """

    responses: list[str | Callable[[str], str]]
    calls: list[str] = field(default_factory=list)
    token_usage: TokenUsage = field(default=_MOCK_USAGE)

    # Stays async to satisfy the GenerationProvider structural protocol (line 196
    # above); every real provider awaits network I/O here, and callers
    # (orchestrator.py, worker.py) uniformly `await provider.complete(...)`
    # regardless of concrete type, so a sync override on this one test double
    # would break that uniform call contract. ``system`` and ``max_tokens`` are
    # accepted-but-unused to match that fixed protocol signature.
    #
    # The suppression markers below carry a bare rule key and no trailing prose,
    # and each sits on the line its own rule is reported against. Both properties
    # are required: a language-prefixed key or a trailing `: reason` makes the
    # marker unparseable (python:S7632), and a marker only ever suppresses the
    # line it sits on, so the rationale has to live up here.
    async def complete(  # NOSONAR(S7503)
        self,
        *,
        system: str,  # noqa: ARG002  # NOSONAR(S1172)
        prompt: str,
        max_tokens: int,  # noqa: ARG002  # NOSONAR(S1172)
    ) -> Completion:
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
            The next queued response string (or callable result), wrapped with
            ``self.token_usage``.

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
        text = response(prompt) if callable(response) else response
        return Completion(text=text, usage=self.token_usage)


def build_openrouter_leg(
    settings: Settings,
    model: str,
    *,
    provider_order: tuple[str, ...] | None = None,
    temperature: float | None = None,
) -> GenerationProvider:
    """Construct a single OpenRouter leg for ``model`` from settings.

    Args:
        settings: The application settings instance.
        model: The OpenRouter model id this leg targets.
        provider_order: Optional backend pin, most preferred first. ``None``
            (the default, and what every production caller passes) means
            "unspecified", and defers to
            :func:`~cyo_adventure.core.pricing.endpoint_pin_for`, which pins
            only the slugs whose recorded price belongs to one endpoint rather
            than to the slug's default route. An explicit tuple, INCLUDING an
            empty one, is honoured verbatim: offline measurement harnesses such
            as ``scripts/compare_vendors.py`` pass each vendor fixture's own
            order, and a fixture that deliberately carries none must keep
            measuring the unpinned route.
        temperature: Optional sampling temperature, passed straight through.
            ``None`` (the default, and what every generation caller passes)
            sends no ``temperature`` field and leaves the model default intact.
            The moderation reviewer passes 0.0; see
            :data:`~cyo_adventure.moderation.review_provider.REVIEW_TEMPERATURE`.

    Returns:
        An OpenRouter ``GenerationProvider`` adapter.

    Raises:
        ConfigurationError: If ``OPENROUTER_API_KEY`` is not configured. The
            message names the key only, never its value.
    """
    api_key, resolved_order = _openrouter_prerequisites(settings, model, provider_order)
    return OpenRouterProvider(
        api_key=api_key,
        model=model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        effort=settings.llm_effort,
        provider_order=resolved_order,
        temperature=temperature,
    )


def build_openrouter_cost_reporting_leg(
    settings: Settings, model: str
) -> GenerationProvider:
    """Construct an OpenRouter leg that asks the vendor for its own charge.

    A separate builder rather than a fifth parameter on
    :func:`build_openrouter_leg`, so that function's signature and the request
    body it produces both stay exactly what they were: every production caller
    reaches this backend through it, and an always-present ``usage`` field
    would repoint requests that have nothing to do with spend measurement.

    The leg it returns populates ``Completion.vendor_cost_usd`` with what
    OpenRouter says the call cost. That is an OBSERVED number, which is a
    different kind of fact from :func:`cyo_adventure.core.pricing.estimate_cost`
    computed against a hand-transcribed, dated price table; only an offline
    spend-measurement harness needs it, and none of them pass a pin or a
    temperature, so neither is exposed here.

    Args:
        settings: The application settings instance.
        model: The OpenRouter model id this leg targets.

    Returns:
        An OpenRouter ``GenerationProvider`` adapter that reports vendor cost.

    Raises:
        ConfigurationError: If ``OPENROUTER_API_KEY`` is not configured. The
            message names the key only, never its value.
    """
    api_key, resolved_order = _openrouter_prerequisites(settings, model, None)
    return OpenRouterProvider(
        api_key=api_key,
        model=model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        effort=settings.llm_effort,
        provider_order=resolved_order,
        report_vendor_cost=True,
    )


def _openrouter_prerequisites(
    settings: Settings, model: str, provider_order: tuple[str, ...] | None
) -> tuple[str, tuple[str, ...]]:
    """Validate the OpenRouter credential and resolve this model's endpoint pin.

    Shared by both OpenRouter builders so the credential guard and the pin
    resolution below have exactly one implementation; a second copy is how
    one builder would quietly stop applying either.

    Args:
        settings: The application settings instance.
        model: The OpenRouter model id the leg targets.
        provider_order: The caller's backend pin, or ``None`` for
            "unspecified" (see :func:`build_openrouter_leg`).

    Returns:
        The API key and the resolved backend order to construct the leg with.

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

    # #CRITICAL: payment/financial: an unspecified pin resolves to the endpoint
    # the model's recorded price was read from, so a job's `cost_usd` is the
    # price of the endpoint that actually answered. Distinguishing None from ()
    # is what makes that possible without changing any measurement harness: a
    # fixture that deliberately runs unpinned passes () and keeps doing so.
    # #VERIFY: tests/unit/test_openrouter_provider_pin.py::
    # test_a_priced_pin_is_applied_when_the_caller_names_no_order and
    # ::test_an_explicit_empty_order_is_honoured_over_the_table.
    resolved_order = (
        endpoint_pin_for("openrouter", model)
        if provider_order is None
        else provider_order
    )
    return settings.openrouter_api_key, resolved_order


def build_anthropic_leg(settings: Settings, model: str) -> GenerationProvider:
    """Construct a single direct-Anthropic leg for ``model`` from settings.

    Dispatched by :func:`build_provider` when the resolved provider is
    ``anthropic`` (WS-C PR1).

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
    """Construct the Modal leg from settings (ADR-010 item 2).

    Args:
        settings: The application settings instance.

    Returns:
        A bare Modal ``GenerationProvider`` adapter. Since the Ollama
        retirement ``build_provider`` also appends this leg to the production
        :class:`~cyo_adventure.generation.providers.fallback.FallbackProvider`
        cascade as its non-OpenRouter backstop, so this is no longer an
        offline-only experiment. Callers that need to know whether the leg can
        be built at all should check ``settings.modal_leg_configured`` rather
        than catching the ``ConfigurationError`` below.

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


def build_provider(
    settings: Settings,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    lane: GenerationLane = "family",
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
    - ``"anthropic"``: the direct-Anthropic leg alone (no cascade).
      ``model_override`` replaces ``settings.anthropic_model``.
    - ``"openrouter"``: the primary OpenRouter leg, using ``model_override``
      in place of ``settings.openrouter_model`` when set. When
      ``settings.provider_fallback_enabled`` is ``True`` (default) it is
      wrapped in a
      :class:`~cyo_adventure.generation.providers.fallback.FallbackProvider`
      cascade ``[primary, openrouter:fallback_model, modal]`` (neither
      trailing leg's model is ever overridden); when ``False`` the bare
      primary leg is returned so a yield/comparison run can measure one leg
      in isolation. The Modal leg replaced the retired local Ollama leg as
      the non-OpenRouter backstop and is included only when
      ``settings.modal_leg_configured`` is true, so an environment with no
      Modal Auto Endpoint degrades to a two-leg cascade instead of failing.
    - ``"modal"``: the Modal leg alone. ``model_override`` has no effect (the
      Modal leg's model is settings-only; it is not part of the per-job
      override seam).

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

        lane: Which actor's request this generation serves. ``"family"``
            (the default, and the restrictive one) is any kid- or
            guardian-triggered job and permits only the routed legs;
            ``"admin"`` is out-of-band content generation an admin drives
            and adds no constraint. Defaulting to the restrictive value is
            deliberate: a call site that says nothing is restricted.

    Returns:
        A :class:`GenerationProvider` ready for injection into the worker.

    Raises:
        ConfigurationError: For a resolved provider outside the known set,
            when a live provider's required credential is missing, or when
            the resolved provider is not permitted on ``lane``. A provider
            named in :data:`RETIRED_PROVIDERS` gets its own message naming the
            retirement, because that case reaches here by a different route
            than a typo (see the branch below).
    """
    provider = provider_override or settings.generation_provider

    # #CRITICAL: data-integrity: a retired provider cannot reach this function
    # through settings (the Literal rejects it) or through a new request (the
    # allowlist no longer carries it), but it CAN reach it through a job row
    # written before the retirement deployed: process_generation_job reads
    # authoring_metadata["provider"] verbatim and passes it as
    # provider_override. Those rows outlive the deploy, and the reclaim sweep
    # re-enqueues stranded ones, so the window is not just "jobs in flight
    # during the restart".
    #
    # This is deliberately still a raise, not a silent fall back to
    # settings.generation_provider. Substituting a different backend would
    # bill a family's story to a provider the admin did not choose and would
    # make the job's own recorded provider attribution false, which matters
    # because reviewer independence is computed from it
    # (moderation/review_provider.py::build_review_provider). Failing the job
    # loudly is recoverable by re-requesting; a silently mis-attributed story
    # is not detectable after the fact. What this branch buys is a message an
    # operator can act on instead of a bare "unknown generation_provider".
    # #VERIFY: tests/unit/test_worker.py::
    # test_retired_provider_override_raises_a_named_error.
    if provider in RETIRED_PROVIDERS:
        msg = (
            f"generation provider '{provider}' is retired and can no longer be "
            "built. This job was almost certainly enqueued before the "
            "retirement deployed and still carries the old provider in its "
            "authoring_metadata. Fail or re-request the job; see "
            "docs/operations/runbook.md section 5.1."
        )
        raise ConfigurationError(msg)

    # #CRITICAL: security: enforced on the RESOLVED provider, so the override
    # and the global default are both covered by one check, and enforced before
    # any leg is constructed, so a rejected lane never builds a credentialled
    # client. ``lane`` defaults to "family", which is the restricted lane.
    # #VERIFY: tests/unit/test_provider_lane.py::
    # TestFamilyLaneRejectsTheDirectAnthropicLeg.
    if lane == "family" and provider not in FAMILY_LANE_PROVIDERS:
        msg = (
            f"provider '{provider}' is not permitted on the 'family' generation "
            "lane; a kid- or guardian-triggered job may use only "
            f"{sorted(FAMILY_LANE_PROVIDERS)}"
        )
        raise ConfigurationError(msg)

    if provider == "mock":
        # Queue enough copies for Stage A + Stage B + up to 3 repairs.
        # Extra copies are safe: MockProvider raises only if the queue is
        # exhausted before the pipeline finishes, not if there are leftovers.
        #
        # DEV/TEST-ONLY (review finding S-5): when mock_story_fixture is
        # "invalid", serve the structurally broken fixture instead so the
        # deterministic validator gate blocks the run to a HARD-BLOCK /
        # needs-review outcome over the real HTTP path. "safe" (default) is a
        # zero-behavior change. This branch is mock-only; no live provider is
        # affected, and the allowlist already forbids mock outside local.
        fixture = (
            _INVALID_STORY_JSON
            if settings.mock_story_fixture == "invalid"
            else _CANNED_STORY_JSON
        )
        return MockProvider(responses=[fixture] * 8)

    if provider == "anthropic":
        return build_anthropic_leg(settings, model_override or settings.anthropic_model)

    if provider == "openrouter":
        primary = build_openrouter_leg(
            settings, model_override or settings.openrouter_model
        )
        if not settings.provider_fallback_enabled:
            return primary
        legs = [
            primary,
            build_openrouter_leg(settings, settings.openrouter_fallback_model),
        ]
        # #CRITICAL: external-resources: both legs above are the same vendor on
        # the same account, so without the Modal backstop an OpenRouter outage,
        # billing lapse, or account suspension stops generation outright. The
        # retired Ollama leg used to be what kept this cascade spanning two
        # independent failure domains. Including Modal unconditionally is not an
        # option: build_modal_leg raises when the endpoint is unset, which would
        # turn every local dev run, CI run, and Modal-less deploy into a hard
        # generation failure. So degrade, but never silently.
        # #VERIFY: tests/unit/test_worker.py::TestBuildProviderLive pins all
        # four states: test_openrouter_with_modal_configured_builds_three_leg_cascade
        # and test_openrouter_without_modal_degrades_to_two_leg_cascade cover the
        # two shapes, while test_single_vendor_cascade_is_warned_about and
        # test_configured_modal_cascade_emits_no_warning cover the warning.
        if settings.modal_leg_configured:
            legs.append(build_modal_leg(settings))
        else:
            logger.warning(
                "generation.cascade_single_vendor",
                cascade_legs=len(legs),
                reason="modal_endpoint_unconfigured",
                detail=(
                    "generation cascade has no non-OpenRouter backstop; set "
                    "MODAL_BASE_URL and MODAL_MODEL to restore two-vendor failover"
                ),
            )
        return FallbackProvider(legs=legs)

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
