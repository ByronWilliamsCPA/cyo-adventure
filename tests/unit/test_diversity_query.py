"""Unit tests for diversity.query: pure score_history (WS-0 Phase 1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cyo_adventure.diversity.history import HistoryEntry
from cyo_adventure.diversity.query import (
    DifferentiationLevel,
    score_history,
    select_atg_comparison_partner,
)


def _entry(
    storybook_id: str,
    skeleton_slug: str | None,
    theme_sig: frozenset[str],
    *,
    day: int = 1,
) -> HistoryEntry:
    return HistoryEntry(
        storybook_id=storybook_id,
        version=1,
        skeleton_slug=skeleton_slug,
        theme_sig=theme_sig,
        created_at=datetime(2026, 7, day, tzinfo=UTC),
    )


_DRAGON = frozenset({"dragon", "fire"})
_UNRELATED = frozenset({"robot"})


@pytest.mark.unit
def test_saturation_increases_as_same_theme_stories_accumulate() -> None:
    """Saturation rises 1/3 -> 2/3 -> 1.0 as each cell slug gets a similar fill,
    then a second similar fill on any slug escalates LEAF -> CATALOG."""
    cell_slugs = ["s1", "s2", "s3"]

    ctx1 = score_history(
        request_theme_sig=_DRAGON,
        history=[_entry("b1", "s1", _DRAGON, day=1)],
        cell_slugs=cell_slugs,
    )
    assert ctx1.cell_theme_saturation == pytest.approx(1 / 3)
    assert ctx1.recommendation is DifferentiationLevel.TREE

    ctx2 = score_history(
        request_theme_sig=_DRAGON,
        history=[
            _entry("b1", "s1", _DRAGON, day=1),
            _entry("b2", "s2", _DRAGON, day=2),
        ],
        cell_slugs=cell_slugs,
    )
    assert ctx2.cell_theme_saturation == pytest.approx(2 / 3)
    assert ctx2.recommendation is DifferentiationLevel.TREE

    history_full = [
        _entry("b1", "s1", _DRAGON, day=1),
        _entry("b2", "s2", _DRAGON, day=2),
        _entry("b3", "s3", _DRAGON, day=3),
    ]
    ctx3 = score_history(
        request_theme_sig=_DRAGON, history=history_full, cell_slugs=cell_slugs
    )
    assert ctx3.cell_theme_saturation == pytest.approx(1.0)
    assert ctx3.recommendation is DifferentiationLevel.LEAF

    history_double = [*history_full, _entry("b4", "s1", _DRAGON, day=4)]
    ctx4 = score_history(
        request_theme_sig=_DRAGON, history=history_double, cell_slugs=cell_slugs
    )
    assert ctx4.cell_theme_saturation == pytest.approx(1.0)
    assert ctx4.recommendation is DifferentiationLevel.CATALOG


@pytest.mark.unit
def test_dissimilar_theme_history_does_not_saturate() -> None:
    """History entries with an unrelated theme never register as "similar"."""
    ctx = score_history(
        request_theme_sig=_DRAGON,
        history=[_entry("b1", "s1", _UNRELATED, day=1)],
        cell_slugs=["s1", "s2"],
    )
    assert ctx.cell_theme_saturation == 0.0
    assert ctx.used_slugs == frozenset()
    assert ctx.recommendation is DifferentiationLevel.TREE


@pytest.mark.unit
def test_neighbors_sorted_and_capped() -> None:
    """Neighbors are sorted by theme_similarity descending and capped at 10."""
    history = [
        _entry(
            f"b{i}", "s1", frozenset({"dragon"}) if i % 2 == 0 else _UNRELATED, day=i
        )
        for i in range(1, 15)
    ]
    ctx = score_history(
        request_theme_sig=frozenset({"dragon"}), history=history, cell_slugs=["s1"]
    )
    assert len(ctx.neighbors) == 10
    similarities = [n.theme_similarity for n in ctx.neighbors]
    assert similarities == sorted(similarities, reverse=True)
    assert similarities[0] == 1.0


@pytest.mark.unit
def test_empty_cell_slugs_reports_saturation_one() -> None:
    """An empty cell candidate list saturates trivially (nothing to pick anyway)."""
    ctx = score_history(
        request_theme_sig=_DRAGON,
        history=[_entry("b1", "s1", _DRAGON, day=1)],
        cell_slugs=[],
    )
    assert ctx.cell_theme_saturation == 1.0
    assert ctx.used_slugs == frozenset()


@pytest.mark.unit
def test_select_atg_comparison_partner_picks_nearest_same_skeleton_entry() -> None:
    """The most recent same-skeleton history entry is the comparison partner."""
    history = [
        _entry("b1", "same-slug", _DRAGON, day=1),
        _entry("b2", "same-slug", _DRAGON, day=5),
        _entry("b3", "other-slug", _DRAGON, day=10),
    ]
    partner = select_atg_comparison_partner("same-slug", history)
    assert partner is not None
    assert partner.storybook_id == "b2"


@pytest.mark.unit
def test_select_atg_comparison_partner_is_noop_on_first_use() -> None:
    """No prior fill of the same skeleton (or a None slug) yields no partner."""
    history = [_entry("b1", "other-slug", _DRAGON, day=1)]
    assert select_atg_comparison_partner("new-slug", history) is None
    assert select_atg_comparison_partner(None, history) is None
    assert select_atg_comparison_partner("new-slug", []) is None
