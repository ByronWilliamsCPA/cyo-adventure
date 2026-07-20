"""Branch-coverage tests for defensive paths in ``mutation/compose.py`` (WS-5 D8).

Targets the malformed-candidate skips in the surviving-re-guidance scan and the
``walk_cap`` delegation branch of ``run_chain_acceptance`` that the primary
suite in ``test_mutation_compose.py`` does not reach.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.mutation.compose import (
    ChainStep,
    _present_target_ids,  # pyright: ignore[reportPrivateUsage]
    _surviving_reguide,  # pyright: ignore[reportPrivateUsage]
    apply_chain,
    run_chain_acceptance,
)
from cyo_adventure.mutation.ops import OpParams, ReguideItem, ReguideTarget

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CAVE = "8-11/the-cave-of-echoes.json"


def _load(slug_path: str) -> dict[str, object]:
    """Load one catalog skeleton by its ``band/slug.json`` path."""
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


@pytest.mark.unit
def test_present_target_ids_returns_early_when_nodes_is_not_a_list() -> None:
    """A candidate whose ``nodes`` is not a list yields the empty present set."""
    assert _present_target_ids({"nodes": "not-a-list"}) == set()


@pytest.mark.unit
def test_present_target_ids_skips_malformed_surfaces() -> None:
    """Non-dict nodes/choices and non-string ending/choice ids are all skipped."""
    candidate = {
        "nodes": [
            "not-a-node",
            {
                "id": "n1",
                "ending": {"id": 5},  # non-string ending id: skipped
                "choices": ["not-a-choice", {"id": 7}],  # non-dict, non-str id
            },
        ]
    }
    assert _present_target_ids(candidate) == {"n1"}


@pytest.mark.unit
def test_surviving_reguide_drops_items_whose_target_vanished() -> None:
    """A re-guidance item pointing at an absent surface is filtered out."""
    candidate = {"nodes": [{"id": "n1"}]}
    item = ReguideItem(
        target=ReguideTarget.NODE, target_id="gone", reason="stale", current_text=""
    )
    assert _surviving_reguide([item], candidate) == ()


@pytest.mark.unit
def test_run_chain_acceptance_honors_an_explicit_walk_cap() -> None:
    """Passing ``walk_cap`` routes through the cap-forwarding delegation branch."""
    parent = _load(_CAVE)
    chain = apply_chain(parent, [ChainStep("M1", OpParams.of(), 0)])
    result = run_chain_acceptance(
        parent,
        chain,
        parent_slug="the-cave-of-echoes",
        walk_cap=100_000,
    )
    # A Tier-1 M1 chain clears every stage but is held on outstanding re-guidance.
    assert result.discarded_at_stage is None
    assert result.held is True
