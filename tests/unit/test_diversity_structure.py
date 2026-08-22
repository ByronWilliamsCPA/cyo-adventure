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
from cyo_adventure.generation.skeleton import is_sidecar
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
    paths = sorted(p for p in _SKELETON_DIR.glob("*.json") if not is_sidecar(p))
    assert len(paths) >= 2
    first = _load(paths[0])
    second = _load(paths[1])
    assert structure_fingerprint(first) != structure_fingerprint(second)
    assert structural_distance(first, second) > 0.0


@pytest.mark.unit
def test_fingerprint_ignores_titles_bodies_and_labels() -> None:
    """Retitling an ending, a node body, or every choice label does not move it."""
    story = _load(_SPACE_STATION_FILL)
    before = structure_fingerprint(story)

    retitled = json.loads(json.dumps(story))
    retitled["title"] = "A Completely Different Title"
    for node in retitled["nodes"]:
        node["body"] = "Different prose entirely."
        if node.get("ending") is not None:
            node["ending"]["title"] = "A New Ending Title"
        for choice in node.get("choices", []):
            choice["label"] = "A completely different choice label."

    after = structure_fingerprint(retitled)
    assert before == after


@pytest.mark.unit
def test_fingerprint_equal_for_label_rewritten_fill_of_same_skeleton() -> None:
    """A fill whose choice labels alone were rewritten still shares a fingerprint.

    Labels are leaf content the automated fill rewrites per theme (the
    WS-0 labels-are-leaves decision); a rewritten choice ``target``, by
    contrast, is a genuine structural change and must still move the hash.
    """
    story = _load(_SPACE_STATION_FILL)
    before = structure_fingerprint(story)

    label_rewritten = json.loads(json.dumps(story))
    for node in label_rewritten["nodes"]:
        for choice in node.get("choices", []):
            choice["label"] = f"Reskinned: {choice['label']}"
    assert structure_fingerprint(label_rewritten) == before

    target_rewritten = json.loads(json.dumps(story))
    first_node_with_choices = next(
        node for node in target_rewritten["nodes"] if node.get("choices")
    )
    original_target = first_node_with_choices["choices"][0]["target"]
    other_node_id = next(
        node["id"]
        for node in target_rewritten["nodes"]
        if node["id"] not in (first_node_with_choices["id"], original_target)
    )
    first_node_with_choices["choices"][0]["target"] = other_node_id
    assert structure_fingerprint(target_rewritten) != before


@pytest.mark.unit
def test_features_handle_cyclic_topologies() -> None:
    """An open_map (cyclic) skeleton computes features without hanging or crashing."""
    cyclic_paths = [
        path
        for path in _SKELETON_DIR.glob("*.json")
        if not is_sidecar(path) and _load(path)["metadata"]["topology"] == "open_map"
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


# The digest of ``_PINNED_STORY`` below, recorded 2026-08-06. Any change to
# this literal is a change to every fingerprint ever stored in this repo.
_PINNED_DIGEST = "a93def8cc7cc0f661d97ea271f40743c0062edb3d14e59b1a0142c55b245a375"

# A fixed story, written inline rather than loaded from a file so that no
# fixture edit can move the digest silently. Deliberately minimal: two nodes,
# one ending, no variables, so the only thing that can rotate its digest is a
# change to the hashing itself or to the Storybook model's field set.
_PINNED_METADATA: dict[str, object] = {
    "age_band": "8-11",
    "reading_level": {
        "scheme": "flesch_kincaid",
        "target": 4.0,
        "tolerance": 1.0,
    },
    "tier": 1,
    "estimated_minutes": 5,
    "ending_count": 1,
    "topology": "branch_and_bottleneck",
}

_PINNED_STORY: dict[str, object] = {
    "schema_version": "2.1",
    "id": "fingerprint-pin",
    "version": 1,
    "title": "Fingerprint Pin",
    "metadata": _PINNED_METADATA,
    "start_node": "start",
    "nodes": [
        {
            "id": "start",
            "body": "You stand at the gate.",
            "choices": [{"id": "go", "label": "Go in.", "target": "end"}],
        },
        {
            "id": "end",
            "body": "You are inside.",
            "is_ending": True,
            "ending": {
                "id": "e_end",
                "kind": "success",
                "valence": "positive",
                "title": "Inside",
            },
        },
    ],
}


@pytest.mark.unit
def test_structure_fingerprint_is_pinned_to_a_literal_digest() -> None:
    """A digest rotation must fail here first, with an obvious cause.

    ``_strip_leaf_content`` is a blacklist: it pops the four known prose keys
    and hashes everything else the dump contains, so **every** additive
    ``Storybook`` field enters the digest automatically, whether or not it
    says anything about graph shape. That rotates every fingerprint stored
    anywhere in the repo, and those stores are not all under ``tests/``:
    ``out/ws2/*/fingerprint-manifest.json`` holds 45 committed acceptance
    manifests that no test loads. The ADR-025 schema minor that added
    ``accepts_character`` rotated 19 of them, and the only signal at the time
    was one unrelated panel-baseline test going red.

    If this assertion fails, that is the signal, not a bug in this test. The
    fix is: regenerate ``tests/data/diversity_panel/baseline.json`` and the
    ``out/ws2`` manifests, then update ``_PINNED_DIGEST`` in the same change.
    """
    assert structure_fingerprint(_PINNED_STORY) == _PINNED_DIGEST


@pytest.mark.unit
def test_structure_fingerprint_pin_moves_when_a_field_is_added() -> None:
    """The pin above is load-bearing: an extra top-level key must change it.

    Without this, ``_PINNED_DIGEST`` could be pinned against a hash that
    ignored the field set entirely and the test above would still pass.
    ``accepts_character`` is the real field that caused the incident, so
    supplying a non-default value for it is the exact mutation being guarded.
    """
    tier2_metadata = {**_PINNED_METADATA, "tier": 2}
    opted_in: dict[str, object] = {
        **_PINNED_STORY,
        "metadata": tier2_metadata,
        "variables": [
            {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 2}
        ],
        "accepts_character": {"might": {"min": 0, "max": 2}},
    }
    assert structure_fingerprint(opted_in) != _PINNED_DIGEST
