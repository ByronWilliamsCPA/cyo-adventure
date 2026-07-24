"""Unit and property tests for id renaming and metadata resync (WS-5 D1).

Covers ``mutation/identity.py``: the ``m<k>_`` id-rename collision-freedom and
determinism, and the metadata resync (ending_count, tier, estimated_minutes,
topology re-declaration). The safety property (design section 12, D1) is that no
D1 utility can emit a document with duplicate ids or a metadata/ending
mismatch: every resynced catalog skeleton re-validates against the schema, and
every renamed region is disjoint from its host namespace.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.identity import (
    host_id_namespace,
    recompute_ending_count,
    recompute_estimated_minutes,
    recompute_tier,
    redeclare_topology,
    rename_region,
    resync_metadata,
)
from cyo_adventure.storybook.models import Storybook, Topology

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"

# The ADR-011 section 5 reading-pace anchors, pinned independently of the
# implementation so a change to either must be a deliberate, tested edit.
_EXPECTED_PACE_WPM = {
    "3-5": 100,
    "5-8": 90,
    "8-11": 120,
    "10-13": 150,
    "13-16": 190,
    "16+": 220,
}


def _load_catalog() -> list[tuple[str, dict[str, object]]]:
    """Return ``(slug, story)`` for every production catalog skeleton.

    Mirrors ``generation.skeleton_match._production_candidates``: it skips
    ``*.contract.json`` sidecars and the three MVP/test seeds (metadata
    ``production_eligible`` False).

    Returns:
        list[tuple[str, dict[str, object]]]: The loaded skeletons.
    """
    catalog: list[tuple[str, dict[str, object]]] = []
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        meta = story.get("metadata")
        if isinstance(meta, dict):
            eligible = cast("dict[str, object]", meta).get("production_eligible")
            if eligible is False:
                continue
        catalog.append((path.stem, story))
    return catalog


_CATALOG = _load_catalog()
_CATALOG_IDS = [slug for slug, _ in _CATALOG]
_STORIES = [story for _, story in _CATALOG]


def _meta_of(story: Mapping[str, object]) -> Mapping[str, object]:
    """Return a story's metadata mapping (tests build well-formed inputs)."""
    meta = story.get("metadata")
    assert isinstance(meta, dict)
    return cast("Mapping[str, object]", meta)


# --------------------------------------------------------------------------- #
# Metadata resync over the real catalog
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("story", _STORIES, ids=_CATALOG_IDS)
def test_resync_revalidates_against_schema(story: dict[str, object]) -> None:
    """A resynced catalog skeleton is still a schema-valid Storybook."""
    resynced = resync_metadata(story)
    # Must not raise: the resync never introduces a metadata/ending mismatch or
    # any other schema violation (design CR-3 constructive direction).
    Storybook.model_validate(resynced)


@pytest.mark.unit
@pytest.mark.parametrize("story", _STORIES, ids=_CATALOG_IDS)
def test_resync_recomputes_derived_metadata_consistently(
    story: dict[str, object],
) -> None:
    """ending_count, tier, estimated_minutes, and topology are self-consistent."""
    resynced = resync_metadata(story)
    meta = _meta_of(resynced)
    nodes = cast("list[dict[str, object]]", resynced["nodes"])
    expected_endings = sum(1 for node in nodes if node.get("is_ending") is True)
    assert meta["ending_count"] == expected_endings
    variables = resynced.get("variables")
    expected_tier = 2 if isinstance(variables, list) and variables else 1
    assert meta["tier"] == expected_tier
    minutes = meta["estimated_minutes"]
    assert isinstance(minutes, int)
    assert minutes >= 1


@pytest.mark.unit
@pytest.mark.parametrize("story", _STORIES, ids=_CATALOG_IDS)
def test_resync_preserves_a_valid_trees_topology(story: dict[str, object]) -> None:
    """A gate-verified tree keeps its declared topology through re-declaration."""
    original = _meta_of(story)["topology"]
    resynced = resync_metadata(story)
    assert _meta_of(resynced)["topology"] == original


@pytest.mark.unit
@pytest.mark.parametrize("story", _STORIES, ids=_CATALOG_IDS)
def test_resync_does_not_mutate_its_input(story: dict[str, object]) -> None:
    """Resync returns a fresh document and leaves the parent untouched."""
    before = json.dumps(story, sort_keys=True)
    resync_metadata(story)
    assert json.dumps(story, sort_keys=True) == before


# --------------------------------------------------------------------------- #
# Individual resync helpers
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_recompute_ending_count_matches_ending_nodes() -> None:
    """The count equals the number of is_ending nodes."""
    story: dict[str, object] = {
        "nodes": [
            {"id": "a", "choices": [{"id": "c", "target": "b"}]},
            {"id": "b", "is_ending": True, "ending": {"id": "e1"}},
            {"id": "d", "is_ending": True, "ending": {"id": "e2"}},
        ]
    }
    assert recompute_ending_count(story) == 2


@pytest.mark.unit
def test_recompute_tier_reflects_variable_presence() -> None:
    """A story with variables is tier 2; without, tier 1."""
    assert (
        recompute_tier({"variables": [{"name": "x", "type": "int", "initial": 0}]}) == 2
    )
    assert recompute_tier({"variables": []}) == 1
    assert recompute_tier({}) == 1


@pytest.mark.unit
@pytest.mark.parametrize(("band", "pace"), sorted(_EXPECTED_PACE_WPM.items()))
def test_recompute_estimated_minutes_uses_band_pace_anchor(
    band: str, pace: int
) -> None:
    """Fastest-finish words divided by the band pace anchor gives the minutes."""
    # A two-node satisfying path carrying exactly pace*10 words must read as 10
    # minutes for the correct anchor; a wrong anchor would round differently.
    story: dict[str, object] = {
        "start_node": "s",
        "metadata": {"age_band": band, "topology": "time_cave"},
        "nodes": [
            {
                "id": "s",
                "body": f"<<FILL role=passage words={pace * 6} beats='a'>>",
                "choices": [{"id": "c", "target": "e"}],
            },
            {
                "id": "e",
                "body": f"<<FILL role=ending words={pace * 4} beats='b'>>",
                "is_ending": True,
                "ending": {
                    "id": "end1",
                    "kind": "success",
                    "valence": "positive",
                    "title": "Home",
                },
            },
        ],
    }
    assert recompute_estimated_minutes(story) == 10


@pytest.mark.unit
def test_recompute_estimated_minutes_floors_at_one() -> None:
    """A tiny story still reads as at least one minute."""
    story: dict[str, object] = {
        "start_node": "s",
        "metadata": {"age_band": "8-11", "topology": "time_cave"},
        "nodes": [
            {
                "id": "s",
                "body": "<<FILL role=passage words=3 beats='a'>>",
                "choices": [{"id": "c", "target": "e"}],
            },
            {
                "id": "e",
                "body": "<<FILL role=ending words=2 beats='b'>>",
                "is_ending": True,
                "ending": {
                    "id": "end1",
                    "kind": "success",
                    "valence": "positive",
                    "title": "Home",
                },
            },
        ],
    }
    assert recompute_estimated_minutes(story) == 1


# --------------------------------------------------------------------------- #
# Topology re-declaration
# --------------------------------------------------------------------------- #


def _cyclic_story(band: str, declared: str) -> dict[str, object]:
    """Return a small cyclic (hub/return) story declaring ``declared``."""
    return {
        "start_node": "hub",
        "metadata": {"age_band": band, "topology": declared},
        "nodes": [
            {
                "id": "hub",
                "choices": [
                    {"id": "h_x", "target": "x"},
                    {"id": "h_end", "target": "end"},
                ],
            },
            {"id": "x", "choices": [{"id": "x_hub", "target": "hub"}]},
            {"id": "end", "is_ending": True, "ending": {"id": "e"}},
        ],
    }


@pytest.mark.unit
def test_redeclare_topology_replaces_an_inadmissible_declaration() -> None:
    """A cyclic graph declared 'gauntlet' is re-declared to an admissible value.

    A cyclic graph admits only loop_and_grow/open_map; intersected with the 5-8
    band row and taken in enum-declaration order, loop_and_grow is chosen.
    """
    story = _cyclic_story("5-8", "gauntlet")
    assert redeclare_topology(story) == Topology.LOOP_AND_GROW


@pytest.mark.unit
def test_redeclare_topology_keeps_an_admissible_declaration() -> None:
    """A cyclic graph legitimately declared open_map keeps open_map."""
    story = _cyclic_story("5-8", "open_map")
    assert redeclare_topology(story) == Topology.OPEN_MAP


@pytest.mark.unit
def test_redeclare_topology_raises_when_no_band_value_is_admissible() -> None:
    """A shape whose admissible set misses the band row fails the precondition.

    A reconverging acyclic graph admits only branch_and_bottleneck/gauntlet,
    neither of which is in the 3-5 band row (loop_and_grow/time_cave), so no
    admissible topology can be declared and the mutant is discarded.
    """
    story: dict[str, object] = {
        "start_node": "start",
        "metadata": {"age_band": "3-5", "topology": "time_cave"},
        "nodes": [
            {
                "id": "start",
                "choices": [
                    {"id": "s_a", "target": "a"},
                    {"id": "s_b", "target": "b"},
                ],
            },
            {"id": "a", "choices": [{"id": "a_c", "target": "c"}]},
            {"id": "b", "choices": [{"id": "b_c", "target": "c"}]},
            {"id": "c", "choices": [{"id": "c_end", "target": "end"}]},
            {"id": "end", "is_ending": True, "ending": {"id": "e"}},
        ],
    }
    with pytest.raises(ValidationError):
        redeclare_topology(story)


# --------------------------------------------------------------------------- #
# Id renaming
# --------------------------------------------------------------------------- #


def _sample_region() -> list[dict[str, object]]:
    """Return a two-node region: an internal edge plus one external out-edge."""
    return [
        {
            "id": "r",
            "choices": [
                {"id": "r_in", "target": "leaf"},
                {"id": "r_out", "target": "host_hub"},
            ],
        },
        {"id": "leaf", "is_ending": True, "ending": {"id": "leaf_end"}},
    ]


@pytest.mark.unit
def test_rename_region_prefixes_ids_and_rewrites_internal_targets() -> None:
    """Ids gain the m<k>_ prefix; in-region targets remap, external stay put."""
    region = _sample_region()
    renamed, id_map = rename_region(region, 2, host_namespace={"host_hub"})
    assert id_map == {"r": "m2_r", "leaf": "m2_leaf"}
    root, leaf = renamed
    assert root["id"] == "m2_r"
    choices = cast("list[dict[str, object]]", root["choices"])
    assert choices[0]["id"] == "m2_r_in"
    assert choices[0]["target"] == "m2_leaf"  # internal target remapped
    assert choices[1]["target"] == "host_hub"  # external target preserved
    ending = cast("dict[str, object]", leaf["ending"])
    assert leaf["id"] == "m2_leaf"
    assert ending["id"] == "m2_leaf_end"


@pytest.mark.unit
def test_rename_region_is_deterministic() -> None:
    """The same region and index rename identically every time."""
    first, first_map = rename_region(_sample_region(), 1, host_namespace=set())
    second, second_map = rename_region(_sample_region(), 1, host_namespace=set())
    assert first == second
    assert first_map == second_map


@pytest.mark.unit
def test_rename_region_rejects_host_namespace_collision() -> None:
    """A renamed id that already exists in the host raises rather than duplicate."""
    region = _sample_region()
    with pytest.raises(ValidationError):
        rename_region(region, 1, host_namespace={"m1_r"})


@pytest.mark.unit
def test_rename_region_rejects_negative_index() -> None:
    """A negative mutation index is rejected."""
    region = _sample_region()
    with pytest.raises(ValidationError):
        rename_region(region, -1, host_namespace=set())


@pytest.mark.unit
@pytest.mark.parametrize("story", _STORIES, ids=_CATALOG_IDS)
def test_rename_region_over_catalog_is_collision_free(
    story: dict[str, object],
) -> None:
    """Renaming a real skeleton's whole node set never collides with its host ids.

    This is the design section 4.1 #VERIFY for renaming: the emitted ids are
    disjoint from the host namespace and unique, so the constructive path can
    never produce a duplicate id.
    """
    host = host_id_namespace(story)
    nodes = cast("list[Mapping[str, object]]", story["nodes"])
    renamed, id_map = rename_region(nodes, 7, host_namespace=host)
    assert len(id_map) == len(nodes)
    assert len(set(id_map.values())) == len(id_map)  # node ids stay unique

    new_ids: list[str] = []
    for node in renamed:
        node_id = node["id"]
        assert isinstance(node_id, str)
        new_ids.append(node_id)
        for choice in cast("list[dict[str, object]]", node.get("choices", [])):
            choice_id = choice["id"]
            assert isinstance(choice_id, str)
            new_ids.append(choice_id)
            # Every existing target is in-region here, so all are remapped.
            assert cast("str", choice["target"]).startswith("m7_")
        ending = node.get("ending")
        if isinstance(ending, dict):
            ending_id = cast("dict[str, object]", ending)["id"]
            assert isinstance(ending_id, str)
            new_ids.append(ending_id)

    assert all(new_id.startswith("m7_") for new_id in new_ids)
    assert host.isdisjoint(new_ids)


@pytest.mark.unit
@settings(deadline=None, max_examples=50)
@given(k=st.integers(min_value=0, max_value=999))
def test_rename_region_prefix_is_index_addressed(k: int) -> None:
    """For any non-negative index k, ids gain exactly the m<k>_ prefix."""
    renamed, id_map = rename_region(_sample_region(), k, host_namespace=set())
    assert id_map["r"] == f"m{k}_r"
    assert renamed[0]["id"] == f"m{k}_r"


@pytest.mark.unit
def test_rename_region_rejects_a_node_without_an_id() -> None:
    """A region node missing its id cannot be renamed and raises."""
    with pytest.raises(ValidationError):
        rename_region([{"choices": []}], 1, host_namespace=set())


@pytest.mark.unit
def test_host_id_namespace_unions_node_choice_and_ending_ids() -> None:
    """The namespace covers all three id kinds, so no graft can shadow any."""
    story: dict[str, object] = {
        "nodes": [
            {"id": "n1", "choices": [{"id": "c1", "target": "n2"}]},
            {"id": "n2", "is_ending": True, "ending": {"id": "en1"}},
        ]
    }
    assert host_id_namespace(story) == {"n1", "c1", "n2", "en1"}


# --------------------------------------------------------------------------- #
# Error branches (discard-on-failure paths, design section 6 stage 0)
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_resync_metadata_requires_a_metadata_object() -> None:
    """A story without metadata cannot be resynced."""
    with pytest.raises(ValidationError):
        resync_metadata({"nodes": [{"id": "a", "is_ending": True}]})


@pytest.mark.unit
@pytest.mark.parametrize(
    "metadata",
    [
        {"topology": "time_cave"},  # no age_band
        {"age_band": "8-11"},  # no topology
        {"age_band": "8-11", "topology": "not_a_topology"},  # unknown topology
    ],
    ids=["missing-band", "missing-topology", "unknown-topology"],
)
def test_redeclare_topology_rejects_malformed_metadata(
    metadata: dict[str, object],
) -> None:
    """Missing or unrecognized band/topology fields fail the precondition."""
    story: dict[str, object] = {
        "start_node": "a",
        "metadata": metadata,
        "nodes": [{"id": "a", "is_ending": True, "ending": {"id": "e"}}],
    }
    with pytest.raises(ValidationError):
        redeclare_topology(story)


@pytest.mark.unit
def test_estimated_minutes_falls_back_when_no_satisfying_ending() -> None:
    """With no success/completion ending, the nearest any-ending path is used."""
    # One setback ending reachable; pace 120 (8-11); 240 words => 2 minutes.
    story: dict[str, object] = {
        "start_node": "s",
        "metadata": {"age_band": "8-11", "topology": "time_cave"},
        "nodes": [
            {
                "id": "s",
                "body": "<<FILL role=passage words=120 beats='a'>>",
                "choices": [{"id": "c", "target": "e"}],
            },
            {
                "id": "e",
                "body": "<<FILL role=ending words=120 beats='b'>>",
                "is_ending": True,
                "ending": {
                    "id": "end1",
                    "kind": "setback",
                    "valence": "negative",
                    "title": "Lost",
                },
            },
        ],
    }
    assert recompute_estimated_minutes(story) == 2


@pytest.mark.unit
def test_estimated_minutes_falls_back_when_no_ending_is_reachable() -> None:
    """A start with no reachable ending still yields at least one minute."""
    story: dict[str, object] = {
        "start_node": "s",
        "metadata": {"age_band": "8-11", "topology": "time_cave"},
        "nodes": [
            {
                "id": "s",
                "body": "<<FILL role=passage words=60 beats='a'>>",
                "choices": [{"id": "c", "target": "s"}],
            }
        ],
    }
    assert recompute_estimated_minutes(story) == 1
