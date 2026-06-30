"""Unit tests for the skeleton-diagram generator script core."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.render_skeleton_diagrams import generate_puml, slug_for, write_outputs


def _write_skeleton(root: Path) -> Path:
    # Minimal valid 3-5 skeleton satisfying all gate constraints:
    #   - 8 nodes (band min_nodes=8)
    #   - 2 endings (band min_endings=2)
    #   - 1 decision node with >=2 choices (band min_decisions=1)
    #   - pure branching tree, acyclic, no reconvergence => time_cave topology
    #   - all nodes reachable from n_start
    # Graph: n_start -[left]-> n_a -> n_a1 -> n_a2 -> n_end_a
    #        n_start -[right]-> n_b -> n_b1 -> n_b2 -> n_end_b
    # (8 nodes total; start is the single decision node)
    skel = {
        "schema_version": "2.0",
        "id": "sk_demo_diagram",
        "version": 1,
        "title": "Demo Diagram",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": [],
            "estimated_minutes": 5,
            "ending_count": 2,
            "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
            "topology": "time_cave",
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "<<FILL role=setup words=85 beats='start'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Go left.", "target": "n_a"},
                    {"id": "c_b", "label": "Go right.", "target": "n_b"},
                ],
            },
            {
                "id": "n_a",
                "body": "<<FILL role=rising words=75 beats='left'>>",
                "is_ending": False,
                "choices": [{"id": "c_a1", "label": "Continue.", "target": "n_a1"}],
            },
            {
                "id": "n_a1",
                "body": "<<FILL role=rising words=75 beats='left mid'>>",
                "is_ending": False,
                "choices": [{"id": "c_a2", "label": "Finish.", "target": "n_end_a"}],
            },
            {
                "id": "n_end_a",
                "body": "<<FILL role=completion words=75 beats='done left'>>",
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "End A",
                },
            },
            {
                "id": "n_b",
                "body": "<<FILL role=rising words=75 beats='right'>>",
                "is_ending": False,
                "choices": [{"id": "c_b1", "label": "Continue.", "target": "n_b1"}],
            },
            {
                "id": "n_b1",
                "body": "<<FILL role=rising words=75 beats='right mid'>>",
                "is_ending": False,
                "choices": [{"id": "c_b2", "label": "Continue.", "target": "n_b2"}],
            },
            {
                "id": "n_b2",
                "body": "<<FILL role=choice words=75 beats='right late'>>",
                "is_ending": False,
                "choices": [{"id": "c_bend", "label": "Finish.", "target": "n_end_b"}],
            },
            {
                "id": "n_end_b",
                "body": "<<FILL role=completion words=75 beats='done right'>>",
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End B",
                },
            },
        ],
    }
    band_dir = root / "3-5"
    band_dir.mkdir(parents=True)
    path = band_dir / "demo-diagram.json"
    path.write_text(json.dumps(skel), encoding="utf-8")
    return path


@pytest.mark.unit
def test_slug_for_uses_filename_stem() -> None:
    assert slug_for(Path("skeletons/3-5/the-lost-mitten.json")) == "the-lost-mitten"


@pytest.mark.unit
def test_generate_puml_maps_band_relative_output_paths(tmp_path: Path) -> None:
    skeletons = tmp_path / "skeletons"
    _write_skeleton(skeletons)
    out_root = tmp_path / "out"
    mapping = generate_puml(skeletons, out_root)
    expected = out_root / "3-5" / "demo-diagram.puml"
    assert expected in mapping
    assert mapping[expected].startswith("@startuml")
    assert "[*] --> n_start" in mapping[expected]


@pytest.mark.unit
def test_write_outputs_writes_files(tmp_path: Path) -> None:
    target = tmp_path / "out" / "3-5" / "demo-diagram.puml"
    write_outputs({target: "@startuml x\n@enduml\n"})
    assert target.read_text(encoding="utf-8") == "@startuml x\n@enduml\n"
