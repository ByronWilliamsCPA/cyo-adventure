"""Unit tests for diversity.structure (WS-0 Phase 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.diversity.structure import (
    structural_distance,
    structure_features,
    structure_fingerprint,
)
from cyo_adventure.storybook.models import Storybook

_SPACE_STATION_FILL = Path(
    "out/pilot/fills/the-cave-of-echoes.space-station.filled.json"
)
_DINO_DIG_FILL = Path("out/pilot/fills/the-cave-of-echoes.dino-dig.filled.json")
_SKELETON_DIR = Path("skeletons/8-11")


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_structure_fingerprint_equal_for_two_fills_of_one_skeleton() -> None:
    """The two pilot fills of one skeleton fingerprint identically."""
    a = _load(_SPACE_STATION_FILL)
    b = _load(_DINO_DIG_FILL)
    assert structure_fingerprint(a) == structure_fingerprint(b)


@pytest.mark.unit
def test_structural_distance_zero_for_same_skeleton_fills() -> None:
    """Two fills of one skeleton are exactly 0.0 apart structurally."""
    a = _load(_SPACE_STATION_FILL)
    b = _load(_DINO_DIG_FILL)
    assert structural_distance(a, b) == 0.0


@pytest.mark.unit
def test_structural_distance_positive_across_skeletons() -> None:
    """Any two distinct skeleton files in skeletons/8-11/ are structurally apart."""
    paths = sorted(_SKELETON_DIR.glob("*.json"))
    assert len(paths) >= 2
    first = _load(paths[0])
    second = _load(paths[1])
    assert structure_fingerprint(first) != structure_fingerprint(second)
    assert structural_distance(first, second) > 0.0


@pytest.mark.unit
def test_fingerprint_ignores_titles_and_bodies() -> None:
    """Retitling an ending (or a node body) does not change the fingerprint."""
    story = _load(_SPACE_STATION_FILL)
    before = structure_fingerprint(story)

    retitled = json.loads(json.dumps(story))
    retitled["title"] = "A Completely Different Title"
    for node in retitled["nodes"]:
        node["body"] = "Different prose entirely."
        if node.get("ending") is not None:
            node["ending"]["title"] = "A New Ending Title"

    after = structure_fingerprint(retitled)
    assert before == after


@pytest.mark.unit
def test_features_handle_cyclic_topologies() -> None:
    """An open_map (cyclic) skeleton computes features without hanging or crashing."""
    cyclic_paths = [
        path
        for path in _SKELETON_DIR.glob("*.json")
        if _load(path)["metadata"]["topology"] == "open_map"
    ]
    assert cyclic_paths, "expected at least one open_map skeleton fixture"
    for path in cyclic_paths:
        features = structure_features(_load(path))
        assert features.n_nodes > 0
        assert features.max_depth >= 0
        assert features.min_ending_depth >= 0


@pytest.mark.unit
def test_structure_features_reports_topology_and_ending_histograms() -> None:
    """Feature extraction reports the declared topology and normalized histograms."""
    story = Storybook.model_validate(_load(_SPACE_STATION_FILL))
    features = structure_features(story)
    assert features.topology == "time_cave"
    assert features.n_endings > 0
    assert pytest.approx(sum(features.ending_kind_hist), abs=1e-9) == 1.0
    assert pytest.approx(sum(features.valence_hist), abs=1e-9) == 1.0
