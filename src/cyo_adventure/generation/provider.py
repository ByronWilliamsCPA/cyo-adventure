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


def build_provider(settings: Settings) -> GenerationProvider:
    """Construct a :class:`GenerationProvider` from application settings.

    In Phase 2 only ``"mock"`` is operational; real providers are deferred to
    Phase 2b when network I/O, retries, authentication, and timeouts will be
    added. Requesting any other provider raises :class:`ConfigurationError`
    immediately so the misconfiguration surfaces at job dispatch time.

    The mock provider is seeded with enough copies of the canned story JSON to
    cover Stage A + Stage B + several repair rounds without exhausting the
    response queue, making a single ``mock`` worker run produce a deterministic
    ``"passed"`` outcome.

    Args:
        settings: The application settings instance.

    Returns:
        A :class:`GenerationProvider` ready for injection into the worker.

    Raises:
        ConfigurationError: If ``settings.generation_provider`` is not
            ``"mock"`` (deferred providers raise immediately).
    """
    if settings.generation_provider == "mock":
        # Queue enough copies for Stage A + Stage B + up to 3 repairs.
        # Extra copies are safe: MockProvider raises only if the queue is
        # exhausted before the pipeline finishes, not if there are leftovers.
        return MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    # #ASSUME: external-resources: "claude", "ollama", and "openrouter" require
    # network I/O, credentials, retries, and timeout handling that are deferred
    # to Phase 2b. Raising here prevents silent mis-configuration in-phase.
    # #VERIFY: Phase 2b adds real adapters for each provider and removes this
    # guard, replacing it with per-provider credential validation at startup.
    msg = (
        f"provider '{settings.generation_provider}' is deferred to Phase 2b; "
        "set generation_provider=mock"
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
