"""The review-provider abstraction for the LLM moderation stages.

``ReviewProvider`` mirrors ``GenerationProvider`` exactly so the same backend
adapters and the same ``PiiGuardedProvider`` wrapper apply. OpenRouter is the
only live review backend: the Ollama leg was retired, and Modal review is still
deferred to slice 2b.
``build_review_provider`` enforces reviewer independence: a model must not review
its own output without that being recorded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol, cast

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.core.pricing import endpoint_pin_for
from cyo_adventure.generation.provider import (
    MockProvider,
    build_openrouter_leg,
)
from cyo_adventure.generation.usage import Completion

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

# The mock review backend (the dev/test default) must outlast a full pipeline run.
# A clean run issues ceil(N / review_batch_size) + 2 review calls: safety,
# chunked per review_batch_size (default 8), plus coherence and engagement once
# each. The ceiling matters because a trailing partial chunk still costs a full
# call, so plain division under-counts by one whenever N is not a multiple of
# the batch size; the two coincide only at review_batch_size=1.
#
# The worst case is higher than that, and deliberately so: an unusable batch
# response is retried one node at a time, which adds up to len(batch) calls for
# that batch. A story whose every batch response is unusable therefore costs at
# most ceil(N / review_batch_size) + N + 2, and the retries stop entirely once
# one batch recovers nothing (the reviewer, not the format, is then the problem).
#
# MockProvider raises BusinessLogicError on over-call, so a fixed budget that is
# too small turns a large clean story into a spurious job failure. This bound
# covers that worst case well beyond any realistic node count; mock is never a
# live backend.
_MOCK_RESPONSE_BUDGET = 4096


class ReviewProvider(Protocol):
    """Structural protocol identical to ``GenerationProvider``."""

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Return the model's completion and usage for a system+user prompt."""
        ...


def completion_text(returned: object) -> str | None:
    """Read the text off a review-provider return, or ``None`` if it is unusable.

    Every moderation stage fails safe on an unparseable reviewer response rather
    than aborting the run, so the reviewer's return value must be treated as
    untrusted at two levels, not one: that it is a ``Completion`` at all, and
    that its ``text`` is a ``str``.

    Args:
        returned: Whatever the provider's ``complete`` actually returned.

    Returns:
        The completion text, or ``None`` when the value cannot supply one.
    """
    # #CRITICAL: data-integrity: ReviewProvider is a structural protocol, so a
    # non-conforming implementation can return anything, and a real backend can
    # hand back None on a truncated or errored completion despite its declared
    # type. The parameter is typed `object` deliberately: annotating it
    # `Completion` would let the type checker prove both guards dead and a
    # future edit would then "simplify" them away, turning a degraded reviewer
    # into a pipeline outage (AttributeError on .text, or TypeError inside
    # json.loads). Callers must pass the raw return, not a narrowed binding.
    # #VERIFY: test_batch_non_string_response_falls_back_rather_than_raising,
    # test_semantic_check_provider_contract_violation_fails_open.
    if not isinstance(returned, Completion):
        return None
    # The cast is load-bearing for the same reason: `Completion.text` is
    # declared `str`, and Completion is a plain dataclass with no runtime
    # validation, so the declared type is a claim about the constructor's
    # caller rather than about this value.
    text = cast("object", returned.text)
    return text if isinstance(text, str) else None


def completion_truncated(returned: object) -> bool:
    """Return ``True`` when the provider reported a budget truncation.

    Args:
        returned: Whatever the provider's ``complete`` actually returned.

    Returns:
        ``True`` only when the backend reported ``finish_reason="length"``.

    # #CRITICAL: external-resources: the OpenRouter adapter raises only when a
    # truncated completion comes back EMPTY. A truncation that produced some
    # bytes first returns normally, so a starved review call reaches the stage
    # parsers as a JSON prefix and fails safe as "unparseable". That reads like
    # a model formatting quirk and hides the real cause, which is that we did
    # not buy enough output budget. ``finish_reason`` is the only thing that
    # separates the two, and nothing in moderation read it before this.
    # #VERIFY: test_truncated_batch_is_reported_as_truncation_not_bad_json.
    """
    return completion_finish_reason(returned) == "length"


def completion_finish_reason(returned: object) -> str:
    """Return the provider's reported finish reason, always as a string.

    The observable half of :func:`completion_truncated`. That predicate can
    only answer yes or no, so a provider that omits ``finish_reason``, or
    spells truncation some other way, makes a genuinely starved call
    indistinguishable from a model that merely emitted bad JSON, and the log
    cannot show which one happened because the predicate discarded the value.
    This returns the value itself so a parse failure records what the backend
    actually said. Both observed OpenRouter runs (2026-08-26, at ceilings of
    400 and 16000) populated the field, so this closes a confidence gap rather
    than a known failure.

    Args:
        returned: Whatever the provider's ``complete`` actually returned.

    Returns:
        str: The reported reason. ``"<absent>"`` when the field is missing or
            ``None``, and ``"<not-a-completion>"`` when the provider returned
            a bare string, so an empty log field can never be mistaken for a
            backend that reported nothing.

    # #ASSUME: external-resources: a non-string finish_reason is coerced with
    # repr rather than dropped. The field is free-form across backends and
    # this value is diagnostic only, never a control-flow input beyond the
    # equality test in completion_truncated.
    # #VERIFY: test_finish_reason_is_logged_even_when_it_is_not_a_truncation.
    """
    if not isinstance(returned, Completion):
        return "<not-a-completion>"
    reason = cast("object", getattr(returned, "finish_reason", None))
    if reason is None:
        return "<absent>"
    return reason if isinstance(reason, str) else repr(reason)


# #CRITICAL: data-integrity: a safety verdict is a judgment, and a judgment that
# moves between two reads of the same passage is not one. Left at the vendor
# default (typically 1.0) a re-moderation returns a different answer to
# unchanged prose, which is indistinguishable from the prose having changed and
# makes every before/after comparison in this subsystem unfalsifiable: the
# 2026-07-21 mock-reviewer sweep was only detectable because its reports carried
# a stamp, and sampling noise carries none. Generation deliberately keeps the
# default (see generation/variation.py: variation is bought with an explicit
# axis, not with noise), so this is set on the review leg only.
#
# No `seed` is sent alongside it. OpenRouter forwards `seed` only to backends
# that implement it and this reviewer slug runs UNPINNED (its PRICES row is the
# slug's default route, so `ENDPOINT_PINS` carries no entry, see
# core/config.py::review_openrouter_model), which means the answering backend
# is not known in advance and neither is whether it honours the field. Sending
# one would buy an appearance of reproducibility without the property. Pinning
# the endpoint first is the prerequisite, and it needs a reachability probe this
# account has not run for this slug.
# #VERIFY: tests/unit/test_review_provenance.py::
# test_the_review_leg_is_built_at_temperature_zero.
REVIEW_TEMPERATURE: Final = 0.0


def _review_model_for(settings: Settings) -> str | None:
    """Return the model the configured review backend will actually run.

    The ONE resolver both :func:`build_review_provider` and
    :func:`review_provenance` read, so a persisted report can never name a
    model other than the one that was built. Two functions each reaching for
    ``settings.review_openrouter_model`` would agree today and drift the moment
    a second live backend lands, and the drift would surface as a report
    attributing a verdict to a model that never saw the prose.

    Args:
        settings: Application settings.

    Returns:
        str | None: The model id, or ``None`` for a backend that runs no model
        (the mock reviewer).
    """
    if settings.review_provider == "mock":
        return None
    return settings.review_openrouter_model


def review_provenance(settings: Settings) -> dict[str, object]:
    """Describe the reviewer a run used, for persistence on the report.

    The 2026-07-21 mock-reviewer run persisted no reviewer provenance at all,
    which is why 31 books' reports could not be told apart from genuinely
    reviewed ones without re-deriving the whole population from a stamp that
    happened to exist. A report that records its own reviewer is auditable
    after the fact by construction.

    Args:
        settings: The settings the review provider was (or will be) built from,
            AFTER any :func:`resolve_review_settings` override, so an
            admin-chosen stage model is what gets recorded.

    Returns:
        dict[str, object]: A JSON-serializable provenance block. ``endpoint`` is
        the OpenRouter backend pin, an empty list meaning the slug ran on
        whichever backend won the routing auction; that is a real gap in
        reproducibility and recording it as empty is how it stays visible.
    """
    model = _review_model_for(settings)
    return {
        "provider": settings.review_provider,
        "model": model,
        "endpoint": (
            list(endpoint_pin_for("openrouter", model))
            if settings.review_provider == "openrouter" and model is not None
            else []
        ),
        "temperature": (
            REVIEW_TEMPERATURE if settings.review_provider != "mock" else None
        ),
        "batch_size": settings.review_batch_size,
    }


def build_review_provider(
    settings: Settings,
    *,
    generator_provider: str | None,
    generator_model: str | None,
) -> tuple[ReviewProvider, bool]:
    """Build the review provider and report whether it is independent.

    Independence tiers (prefer-different, degrade-with-warning):

      1. Different backend from the generator -> independent.
      2. Same backend, different model -> independent.
      3. Same backend and same model -> NOT independent (caller records a
         ``reviewer_not_independent`` finding).

    Args:
        settings: Application settings (``review_provider`` and model fields).
        generator_provider: The provider that generated the story; ``None``
            when unknown.
        generator_model: The model that generated the story; ``None`` when
            unknown.

    Returns:
        ``(provider, independent)``.

    Raises:
        ConfigurationError: when ``review_provider`` is the deferred ``"modal"``,
            or when the required API credential is missing.
    """
    # #CRITICAL: security: a model reviewing its own output is not an independent
    # check; tier 3 must surface as not-independent, never silently pass.
    # #VERIFY: test_same_backend_same_model_is_not_independent.
    # #CRITICAL: external-resource: the openrouter leg is a network-backed HTTP
    # client; a missing credential raises ConfigurationError at build time rather
    # than failing mid-pipeline.
    # #VERIFY: build_openrouter_leg raises on absent credentials.
    backend = settings.review_provider

    if backend == "mock":
        return MockProvider(responses=["{}"] * _MOCK_RESPONSE_BUDGET), True

    if backend == "modal":
        msg = "review_provider 'modal' is deferred to slice 2b; use openrouter"
        raise ConfigurationError(msg)

    review_model = _review_model_for(settings)
    # A non-mock, non-modal backend always resolves a model, so this narrowing
    # cannot be reached; asserting it beats an ignore comment on the call below.
    if review_model is None:  # pragma: no cover - unreachable for openrouter
        msg = f"review_provider '{backend}' resolved no model"
        raise ConfigurationError(msg)
    provider = build_openrouter_leg(
        settings, review_model, temperature=REVIEW_TEMPERATURE
    )

    independent = backend != generator_provider or review_model != generator_model
    return provider, independent


def resolve_review_settings(settings: Settings, model_override: str | None) -> Settings:
    """Return settings with the active backend's review model overridden.

    Used by the admin-chosen review_stage1_model / review_stage2_model
    fields on an authoring plan: the override replaces whichever field
    ``build_review_provider`` will actually read for the configured backend,
    without needing a new parameter on that function.

    Args:
        settings: The base application settings.
        model_override: An admin-chosen model id, or None to leave settings
            unchanged.

    Returns:
        The original ``settings`` object unchanged when ``model_override`` is
        None; otherwise a copy with ``review_openrouter_model`` overridden.
        The mock backend has no configurable model and the modal backend is
        still deferred, so the override is a no-op for both.
    """
    if model_override is None:
        return settings
    if settings.review_provider == "openrouter":
        return settings.model_copy(update={"review_openrouter_model": model_override})
    return settings
