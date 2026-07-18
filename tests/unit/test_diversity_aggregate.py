"""Unit tests for diversity.aggregate: ECS, PS, and RAR (WS-0 Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.diversity.aggregate import (
    effective_catalog_size,
    pair_score,
    perceived_similarity,
    repeat_adventure_rate,
)
from cyo_adventure.diversity.leaf import leaf_distance_profile
from cyo_adventure.diversity.panel import make_noun_swap_variant
from cyo_adventure.storybook.models import Storybook

_CAVE_SEA = Path(
    "tests/data/diversity_panel/fills/the-cave-of-echoes.sea-caves.filled.json"
)
_CAVE_SPACE = Path(
    "tests/data/diversity_panel/fills/the-cave-of-echoes.space-station.filled.json"
)
_CAVE_DINO = Path(
    "tests/data/diversity_panel/fills/the-cave-of-echoes.dino-dig.filled.json"
)
_CLOCKWORK = Path(
    "tests/data/diversity_panel/fills/the-clockwork-menagerie.filled.json"
)

# The committed panel swap table (tests/data/diversity_panel/panel.json's
# cave-space-swap synthetic), reused here so the aggregate tests exercise
# the exact same synthetic that gates the panel.
_SWAPS: dict[str, str] = {
    "station": "burrow",
    "drone": "ferret",
    "airlock": "gate",
    "hull": "wall",
    "corridor": "tunnel",
    "console": "desk",
    "oxygen": "air",
    "solar": "lunar",
    "panel": "plank",
    "module": "room",
    "gravity": "weight",
    "orbit": "circle",
    "engine": "motor",
    "signal": "whistle",
    "metal": "wood",
    "light": "lamp",
    "door": "hatch",
    "echo": "ring",
}


def _load_story(path: Path) -> Storybook:
    return Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _identity_key(row: str) -> str:
    return row


@pytest.mark.unit
def test_ecs_uniform_four_slugs_is_four() -> None:
    """Four equally-represented keys give an ECS of exactly 4.0."""
    rows = ["a", "b", "c", "d"]
    assert effective_catalog_size(rows, _identity_key) == pytest.approx(4.0)


@pytest.mark.unit
def test_ecs_single_slug_is_one() -> None:
    """A population with a single key gives an ECS of exactly 1.0."""
    rows = ["a", "a", "a"]
    assert effective_catalog_size(rows, _identity_key) == pytest.approx(1.0)


@pytest.mark.unit
def test_ecs_empty_is_zero() -> None:
    """An empty population gives an ECS of 0.0."""
    assert effective_catalog_size([], _identity_key) == 0.0


@pytest.mark.unit
def test_ecs_pseudo_slug_keying_raises_ecs() -> None:
    """Keying NULL-slug rows per-storybook raises ECS vs collapsing them to one key."""
    rows: list[dict[str, str | None]] = [
        {"skeleton_slug": None, "storybook_id": "s1"},
        {"skeleton_slug": None, "storybook_id": "s2"},
        {"skeleton_slug": "a", "storybook_id": "s3"},
    ]

    def _collapsed_key(row: dict[str, str | None]) -> str:
        return row["skeleton_slug"] or "NULL"

    def _pseudo_key(row: dict[str, str | None]) -> str:
        return row["skeleton_slug"] or row["storybook_id"] or ""

    collapsed = effective_catalog_size(rows, _collapsed_key)
    pseudo_slugged = effective_catalog_size(rows, _pseudo_key)
    assert pseudo_slugged > collapsed


@pytest.mark.unit
def test_pair_score_same_tree_branch_uses_median_leaf_distance() -> None:
    """A same-fingerprint pair takes the leaf_distance_profile branch."""
    a = _load_story(_CAVE_SEA)
    b = _load_story(_CAVE_SPACE)
    score = pair_score(a, b)
    profile = leaf_distance_profile(a, b)
    assert score.same_tree is True
    assert score.structural_similarity == 1.0
    assert score.leaf_similarity == pytest.approx(1.0 - profile.median_d_uni)


@pytest.mark.unit
def test_pair_score_cross_tree_branch_uses_cosine_and_struct_distance() -> None:
    """A cross-fingerprint pair takes the cosine/structural-distance branch."""
    a = _load_story(_CAVE_SEA)
    b = _load_story(_CLOCKWORK)
    score = pair_score(a, b)
    assert score.same_tree is False
    assert 0.0 <= score.leaf_similarity <= 1.0
    assert 0.0 <= score.structural_similarity <= 1.0
    assert 0.0 <= score.perceived_similarity <= 1.0


@pytest.mark.unit
def test_perceived_similarity_orders_swap_above_genuine_pair() -> None:
    """The synthetic noun-swap pair scores far higher than a genuine re-authored pair."""
    a = _load_story(_CAVE_SPACE)
    b = _load_story(_CAVE_DINO)
    swap = make_noun_swap_variant(a, _SWAPS)
    ps_swap = perceived_similarity(a, swap)
    ps_genuine = perceived_similarity(a, b)
    assert ps_swap > 0.9
    assert ps_swap > ps_genuine


@pytest.mark.unit
def test_rar_zero_below_two_stories() -> None:
    """Fewer than two stories always yields RAR 0.0."""
    a = _load_story(_CAVE_SEA)
    assert repeat_adventure_rate([]) == 0.0
    assert repeat_adventure_rate([a]) == 0.0


@pytest.mark.unit
def test_rar_counts_first_repeat_only_once() -> None:
    """[A, B, A-swap, A-swap2] counts two repeats (i=2 and i=3) out of three checks."""
    a = _load_story(_CAVE_SPACE)
    b = _load_story(_CAVE_DINO)
    a_swap = make_noun_swap_variant(a, _SWAPS)
    a_swap2 = make_noun_swap_variant(a, {"station": "outpost"})
    rar = repeat_adventure_rate([a, b, a_swap, a_swap2])
    assert rar == pytest.approx(2 / 3)


@pytest.mark.unit
def test_rar_threshold_parameter_respected() -> None:
    """Lowering the threshold turns a near-but-under-0.70 pair into a counted repeat."""
    a = _load_story(_CAVE_SEA)
    b = _load_story(_CAVE_SPACE)
    assert repeat_adventure_rate([a, b]) == 0.0
    assert repeat_adventure_rate([a, b], threshold=0.5) == 1.0
