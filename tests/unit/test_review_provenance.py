"""Unit tests for reviewer determinism and the provenance a report records.

Two defects motivate this file, both surfaced by the 2026-07-21 mock-reviewer
sweep (AL-649, UW-C397):

1. **Nothing in ``src/`` sent a ``temperature``.** The safety reviewer therefore
   sampled at the vendor default, so two reads of the same passage could return
   different verdicts. That makes every before/after comparison in the
   moderation subsystem unfalsifiable, because a changed verdict on unchanged
   prose is indistinguishable from changed prose.
2. **A persisted report did not name its own reviewer.** Working out that 31
   books had been "reviewed" by the mock backend meant re-deriving the whole
   population from a stamp that existed for an unrelated reason. A report that
   records its reviewer is auditable by construction.

The wire-level half of (1) lives in
``tests/unit/test_openrouter_provider_pin.py`` (the request body). This file
covers the moderation-side wiring: that the review leg is BUILT at zero, that
the provenance block describes the leg that was actually built, and that a
generation leg is untouched.
"""

from __future__ import annotations

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.pricing import ENDPOINT_PINS
from cyo_adventure.generation.provider import build_openrouter_leg
from cyo_adventure.generation.providers import OpenRouterProvider
from cyo_adventure.moderation.review_provider import (
    REVIEW_TEMPERATURE,
    build_review_provider,
    resolve_review_settings,
    review_provenance,
)

pytestmark = pytest.mark.unit

# The one slug `ENDPOINT_PINS` pins today. Read from the table rather than
# written literally: a pin that is retired should fail this file's setup loudly
# instead of leaving a test that silently asserts an empty endpoint everywhere
# and so can no longer tell a recorded pin from a missing one.
_PINNED_MODEL = "deepseek/deepseek-v4-pro"


def _openrouter_settings(
    *,
    review_openrouter_model: str | None = None,
    review_batch_size: int | None = None,
) -> Settings:
    """Return Settings with the live review backend selected.

    Args:
        review_openrouter_model: Review model to set, or ``None`` to keep the
            configured default (which is what most of these tests want, since
            the default slug's unpinned routing is itself under test).
        review_batch_size: Review batch size to set, or ``None`` for the
            default.

    Returns:
        Settings carrying both credentials the openrouter review backend
        validates at construction time.
    """
    base = Settings(
        review_provider="openrouter",
        openai_api_key="classifier-key",
        openrouter_api_key="leg-key",
    )
    if review_openrouter_model is not None:
        base = base.model_copy(
            update={"review_openrouter_model": review_openrouter_model}
        )
    if review_batch_size is not None:
        base = base.model_copy(update={"review_batch_size": review_batch_size})
    return base


def _built_review_leg(settings: Settings) -> OpenRouterProvider:
    """Build the review leg and narrow it to the concrete adapter.

    ``build_review_provider`` returns the ``ReviewProvider`` protocol, which
    deliberately exposes only ``complete``. The determinism assertions are
    about how the leg was CONSTRUCTED, so the narrowing is part of what is
    under test: a review backend that stopped being an OpenRouter leg would
    stop carrying a temperature at all.

    Args:
        settings: Settings selecting the openrouter review backend.

    Returns:
        The constructed adapter.
    """
    provider, _independent = build_review_provider(
        settings, generator_provider=None, generator_model=None
    )
    assert isinstance(provider, OpenRouterProvider)
    return provider


def test_the_review_leg_is_built_at_temperature_zero() -> None:
    """A safety verdict must not move between two reads of the same passage.

    Left at the vendor default (typically 1.0) a re-moderation answers
    unchanged prose differently, and sampling noise carries no stamp, so the
    only signal that a verdict changed for no reason is absent by
    construction.
    """
    leg = _built_review_leg(_openrouter_settings())

    assert leg.temperature == 0.0
    assert REVIEW_TEMPERATURE == 0.0


def test_a_generation_leg_keeps_the_model_default() -> None:
    """The pin is on the review leg only, and this is the half that says so.

    ``generation/variation.py`` buys variation with an explicit axis rather
    than with sampling noise, but the fill legs are still designed around the
    model default. A temperature that leaked onto the generation path would
    silently repoint every existing yield and diversity measurement, including
    the vendor-comparison fixtures.
    """
    leg = build_openrouter_leg(_openrouter_settings(), "anthropic/claude-sonnet-4.6")

    assert isinstance(leg, OpenRouterProvider)
    assert leg.temperature is None


def test_the_provenance_describes_the_leg_that_was_actually_built() -> None:
    """The recorded reviewer and the constructed leg cannot be allowed to drift.

    This is the reason ``_review_model_for`` exists as a single resolver both
    callers read. Two functions each reaching for
    ``settings.review_openrouter_model`` would agree today and diverge the
    moment a second live backend lands, and the divergence would surface as a
    stored report attributing a verdict to a model that never saw the prose:
    exactly the class of defect this provenance block was added to prevent.

    A pinned slug is used deliberately, so ``endpoint`` is asserted against a
    non-empty value at least once. A test that only ever saw the unpinned
    default would pass against an ``endpoint`` hard-coded to ``[]``.
    """
    settings = _openrouter_settings(review_openrouter_model=_PINNED_MODEL)
    assert ENDPOINT_PINS[("openrouter", _PINNED_MODEL)], "pin retired; test is blind"

    leg = _built_review_leg(settings)
    provenance = review_provenance(settings)

    assert provenance["model"] == leg.model
    assert provenance["model"] == _PINNED_MODEL
    assert provenance["temperature"] == leg.temperature
    assert provenance["endpoint"] == list(leg.endpoint_order)
    assert provenance["endpoint"] == ["azure/us"]


def test_the_provenance_records_an_unpinned_slug_as_unpinned() -> None:
    """An empty endpoint is a real reproducibility gap, reported as one.

    The default review slug's price row IS its default route, so it carries no
    pin and the answering backend is whichever won the routing auction. That
    is why no ``seed`` is sent either. Recording the emptiness is how the gap
    stays visible in the stored report instead of being inferred from absence.
    """
    provenance = review_provenance(_openrouter_settings())

    assert provenance["endpoint"] == []


def test_the_provenance_follows_an_admin_model_override() -> None:
    """Provenance is read from the RESOLVED settings, not the process default.

    An admin-chosen ``review_stage1_model``/``review_stage2_model`` replaces
    the model for that run. A report naming the process-wide default would
    attribute the verdict to a model that did not produce it, which is the same
    failure as naming no reviewer at all, only harder to spot.
    """
    base = _openrouter_settings()
    resolved = resolve_review_settings(base, "anthropic/claude-opus-4.8")

    assert review_provenance(resolved)["model"] == "anthropic/claude-opus-4.8"
    assert review_provenance(base)["model"] == base.review_openrouter_model


def test_the_mock_reviewer_reports_itself_as_running_no_model() -> None:
    """The mock backend must be self-evident in a stored report.

    This is the case the whole change exists for: a report written by the mock
    reviewer has to be identifiable as such from the report alone. ``model``
    and ``temperature`` are ``None`` because the mock runs neither, and
    reporting the configured slug for a backend that never called it would
    reintroduce precisely the ambiguity that cost 31 books a re-moderation.
    """
    provenance = review_provenance(Settings(review_provider="mock"))

    assert provenance["provider"] == "mock"
    assert provenance["model"] is None
    assert provenance["temperature"] is None


def test_the_provenance_records_the_batch_size_the_reviewer_used() -> None:
    """Batch size is part of what produced the verdicts, so it is recorded.

    One unparseable batch response fail-safed all eight of its nodes
    (UW-C396), so the size in force is load-bearing context for reading any
    report written before the per-node fallback landed.
    """
    provenance = review_provenance(_openrouter_settings(review_batch_size=3))

    assert provenance["batch_size"] == 3
