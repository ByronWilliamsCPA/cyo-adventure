"""Unit tests for the DEFAULT_ALLOWLIST seed constant (no DB required)."""

from __future__ import annotations

import inspect
from typing import get_args

import pytest

from cyo_adventure.api.schemas import ProviderName
from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.generation.allowlist import (
    ALLOWLIST_PROVIDERS,
    DEFAULT_ALLOWLIST,
    AllowlistSeed,
    is_enabled_allowlist_pair,
)
from cyo_adventure.generation.provider import FAMILY_LANE_PROVIDERS


def test_allowlist_providers_match_provider_name_literal() -> None:
    """ALLOWLIST_PROVIDERS mirrors the ProviderName Literal from the API layer.

    The generation layer cannot import ProviderName at runtime without inverting
    the dependency direction (generation -> api), so the two are duplicated by
    design. This drift-guard fails if either is edited without the other,
    catching silent divergence a human review would miss.
    """
    assert get_args(ProviderName) == ALLOWLIST_PROVIDERS


def test_default_allowlist_has_six_seed_rows() -> None:
    """The code constant matches the migrations' cumulative row count exactly.

    Was five until the Ollama retirement deleted the qwen2.5:14b row
    (supabase/migrations/20260818120000_retire_ollama_provider.sql), then six
    when D1 added the two DeepSeek rows
    (supabase/migrations/20260823140000_align_allowlist_with_d1_lane_ruling.sql).
    """
    assert len(DEFAULT_ALLOWLIST) == 6


def test_ollama_is_not_allowlistable() -> None:
    """The retired backend must not be selectable for a generation job.

    ALLOWLIST_PROVIDERS is the code-side mirror of the CHECK constraint, and
    is_enabled_allowlist_pair is what keeps free-string model ids out of
    billing. An 'ollama' member surviving here would let an admin pick a
    backend build_provider can no longer construct.
    """
    assert "ollama" not in ALLOWLIST_PROVIDERS
    assert all(seed.provider != "ollama" for seed in DEFAULT_ALLOWLIST)


def test_default_allowlist_providers_are_all_in_the_fixed_set() -> None:
    """Every seed row's provider is one of the three allowlistable providers."""
    for seed in DEFAULT_ALLOWLIST:
        assert seed.provider in ALLOWLIST_PROVIDERS


def test_mock_is_never_in_allowlist_providers() -> None:
    """mock is a CI-only test double, never a real allowlist entry."""
    assert "mock" not in ALLOWLIST_PROVIDERS


def test_default_allowlist_pairs_are_unique() -> None:
    """No (provider, model_id) pair repeats within the seed constant itself."""
    pairs = [(seed.provider, seed.model_id) for seed in DEFAULT_ALLOWLIST]
    assert len(pairs) == len(set(pairs))


# ---------------------------------------------------------------------------
# Agreement with the D1 lane ruling (2026-08-23, `UW-C346`)
# ---------------------------------------------------------------------------


def test_no_enabled_seed_row_names_a_provider_the_family_lane_forbids() -> None:
    """The API must not offer a pair the worker will then refuse to run.

    This is the coherence property the D1 work exists to restore. Every
    authoring plan is created against a family story request, so every job the
    worker runs states ``lane="family"`` and `build_provider` rejects any
    provider outside `FAMILY_LANE_PROVIDERS`. An ENABLED allowlist row naming
    a forbidden provider is therefore a pair the admin dialog offers, the
    authoring-plan endpoint accepts, and the worker then fails on, with the
    failure arriving at generation time and attributed to the job rather than
    to the configuration that caused it.
    """
    forbidden = [
        seed
        for seed in DEFAULT_ALLOWLIST
        if seed.enabled and seed.provider not in FAMILY_LANE_PROVIDERS
    ]

    assert not forbidden, f"enabled rows the family lane forbids: {forbidden}"


def test_an_enabled_seed_naming_a_forbidden_provider_cannot_be_constructed() -> None:
    """The invariant above is refused at construction, not merely asserted after.

    The sibling test scans `DEFAULT_ALLOWLIST` and so can only fail where the
    suite runs. `__post_init__` fails at import instead, and `DEFAULT_ALLOWLIST`
    is a module-level literal, so an offending edit cannot reach a running
    process at all. This test covers the raise the sibling cannot reach,
    because a passing `DEFAULT_ALLOWLIST` never enters that branch.
    """
    with pytest.raises(ConfigurationError, match="family generation lane forbids"):
        AllowlistSeed("anthropic", "claude-sonnet-4-6", "direct", enabled=True)


def test_a_disabled_seed_naming_a_forbidden_provider_is_allowed() -> None:
    """`enabled=False` is the sanctioned way to retire a row, so it must construct.

    Deleting the row instead is the trap: the seed migration's
    `ON CONFLICT DO NOTHING` suppresses a re-insert only while the row exists,
    so a deleted row returns ENABLED on any replay. A guard that refused the
    disabled form would push an editor toward exactly that.
    """
    seed = AllowlistSeed("anthropic", "claude-haiku-4-5", "withdrawn", enabled=False)

    assert seed.enabled is False


def test_a_seed_naming_a_provider_outside_the_allowlist_cannot_be_constructed() -> None:
    """A provider the CHECK constraint rejects is refused before it reaches the DB.

    `ALLOWLIST_PROVIDERS` mirrors `ck_provider_model_allowlist_provider`. The
    dataclass docstring already claimed this as an invariant of the `provider`
    field and nothing enforced it, so a retired provider such as `ollama` could
    be seeded and would fail at insert time instead, where the error names a
    constraint rather than the line that is wrong.
    """
    with pytest.raises(ConfigurationError, match="is not one of"):
        AllowlistSeed("ollama", "llama3", "retired", enabled=False)


def test_the_ruled_fill_and_review_models_are_enabled_seed_rows() -> None:
    """An admin can select the models D1 actually ruled on.

    Without these rows the ruling holds only as a settings default: an admin
    building an authoring plan could not choose the ruled models explicitly,
    because `is_enabled_allowlist_pair` is the single read path the
    authoring-plan endpoint trusts.
    """
    enabled = {
        (seed.provider, seed.model_id) for seed in DEFAULT_ALLOWLIST if seed.enabled
    }

    assert ("openrouter", "deepseek/deepseek-v4-pro") in enabled
    assert ("openrouter", "deepseek/deepseek-v4-flash") in enabled


def test_the_direct_anthropic_rows_are_retained_but_disabled() -> None:
    """The forbidden rows stay present and disabled rather than being deleted.

    Deleting them would be undone: `20260721230000_seed_provider_model_allowlist`
    inserts them with ``ON CONFLICT DO NOTHING``, which suppresses a re-insert
    only while the row EXISTS. A deleted row is re-inserted ENABLED by any
    replay of that seed, so disabling is the state that survives one, and it
    also leaves the admin UI able to show what was withdrawn.
    """
    anthropic = [seed for seed in DEFAULT_ALLOWLIST if seed.provider == "anthropic"]

    assert anthropic, "the direct-anthropic rows should still be described"
    assert not any(seed.enabled for seed in anthropic)


# ---------------------------------------------------------------------------
# The read path's lane parameter (`UW-C350` part (a))
# ---------------------------------------------------------------------------


def test_the_direct_anthropic_provider_is_outside_the_family_lane() -> None:
    """The read-path lane tests are built on the "anthropic" literal.

    `tests/integration/test_allowlist.py` writes "anthropic" out as a literal
    rather than deriving it from `FAMILY_LANE_PROVIDERS`, because a test whose
    expectation is computed from the constant the production code reads moves
    with that constant and can never fail (`AL-591`). The cost of the literal
    is that those tests go vacuous if the ruling ever changes; this assertion
    is what fails loudly instead of letting them pass while proving nothing.
    """
    assert "anthropic" not in FAMILY_LANE_PROVIDERS
    assert "openrouter" in FAMILY_LANE_PROVIDERS


def test_the_read_path_lane_defaults_to_the_restrictive_lane() -> None:
    """`is_enabled_allowlist_pair` restricts a caller that names no lane.

    The default is the whole point of the parameter: it mirrors
    `build_provider`, so a call site added later inherits the restriction by
    omission instead of an exemption by omission. Keyword-only so the lane
    cannot be passed positionally, and so every call site spells the lane out.
    """
    lane = inspect.signature(is_enabled_allowlist_pair).parameters["lane"]

    assert lane.default == "family"
    assert lane.kind is inspect.Parameter.KEYWORD_ONLY
