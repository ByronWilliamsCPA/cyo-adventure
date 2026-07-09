"""Unit tests for the DEFAULT_ALLOWLIST seed constant (no DB required)."""

from __future__ import annotations

from typing import get_args

from cyo_adventure.api.schemas import ProviderName
from cyo_adventure.generation.allowlist import ALLOWLIST_PROVIDERS, DEFAULT_ALLOWLIST


def test_allowlist_providers_match_provider_name_literal() -> None:
    """ALLOWLIST_PROVIDERS mirrors the ProviderName Literal from the API layer.

    The generation layer cannot import ProviderName at runtime without inverting
    the dependency direction (generation -> api), so the two are duplicated by
    design. This drift-guard fails if either is edited without the other,
    catching silent divergence a human review would miss.
    """
    assert get_args(ProviderName) == ALLOWLIST_PROVIDERS


def test_default_allowlist_has_five_seed_rows() -> None:
    """The code constant matches the migration's seed row count exactly."""
    assert len(DEFAULT_ALLOWLIST) == 5


def test_default_allowlist_providers_are_all_in_the_fixed_set() -> None:
    """Every seed row's provider is one of the four allowlistable providers."""
    for seed in DEFAULT_ALLOWLIST:
        assert seed.provider in ALLOWLIST_PROVIDERS


def test_mock_is_never_in_allowlist_providers() -> None:
    """mock is a CI-only test double, never a real allowlist entry."""
    assert "mock" not in ALLOWLIST_PROVIDERS


def test_default_allowlist_pairs_are_unique() -> None:
    """No (provider, model_id) pair repeats within the seed constant itself."""
    pairs = [(seed.provider, seed.model_id) for seed in DEFAULT_ALLOWLIST]
    assert len(pairs) == len(set(pairs))
