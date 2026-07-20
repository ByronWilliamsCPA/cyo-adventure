"""Branch-coverage tests for defensive paths in ``mutation/identity.py`` (WS-5 D1).

These target the malformed-document skips, the collision raises, and the
fastest-finish fallbacks that the primary catalog-driven suite in
``test_mutation_identity.py`` does not reach. Every test drives a real code path
with a crafted minimal raw document and asserts the observable behavior.
"""

from __future__ import annotations

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.identity import (
    host_id_namespace,
    recompute_estimated_minutes,
    rename_region,
)


@pytest.mark.unit
def test_recompute_estimated_minutes_raises_without_metadata() -> None:
    """A story with no metadata object raises through ``_metadata_of``."""
    with pytest.raises(ValidationError, match="no metadata object"):
        recompute_estimated_minutes({"nodes": []})


@pytest.mark.unit
def test_host_id_namespace_skips_idless_surfaces() -> None:
    """A node, choice, and ending that carry no id contribute nothing to the set."""
    story = {
        "nodes": [
            {
                # node with no id, a choice with no id, an ending block with no id
                "choices": [{"target": "x"}],
                "ending": {"kind": "success"},
            },
            {"id": "kept", "choices": [{"id": "c_kept", "target": "kept"}]},
        ]
    }
    namespace = host_id_namespace(story)
    assert namespace == {"kept", "c_kept"}


@pytest.mark.unit
def test_rename_region_raises_on_a_duplicate_region_node_id() -> None:
    """Two region nodes sharing an id collide on the second reserve (intra-region)."""
    region = [{"id": "a"}, {"id": "a"}]
    with pytest.raises(ValidationError, match="not unique within the region"):
        rename_region(region, 0, set())


@pytest.mark.unit
def test_rename_region_skips_malformed_choices_and_idless_surfaces() -> None:
    """A non-dict choice, an id-less choice, and an id-less ending are all tolerated.

    The id-less choice's in-region target is still rewired, and the id-less
    ending block is carried over untouched.
    """
    region = [
        {
            "id": "a",
            "choices": [{"target": "a"}, 99],
            "ending": {"kind": "discovery"},
        }
    ]
    renamed, node_id_map = rename_region(region, 0, set())
    assert node_id_map == {"a": "m0_a"}
    (node,) = renamed
    choices = node["choices"]
    assert isinstance(choices, list)
    # The id-less choice's in-region target was rewired to the renamed node id.
    assert choices[0] == {"target": "m0_a"}
    assert choices[1] == 99
    # The id-less ending block is preserved verbatim.
    assert node["ending"] == {"kind": "discovery"}


@pytest.mark.unit
def test_recompute_estimated_minutes_handles_non_string_body() -> None:
    """A node whose body is not a string contributes zero words, never raising."""
    story = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "body": 123, "choices": [{"id": "c", "target": "e"}]},
            {
                "id": "e",
                "is_ending": True,
                "body": "the end here",
                "ending": {"id": "e_end", "kind": "success"},
            },
            # an ending node with no id is skipped by the fastest-finish target scan
            {"is_ending": True, "body": "stray"},
        ],
    }
    assert recompute_estimated_minutes(story) == 1


@pytest.mark.unit
def test_recompute_estimated_minutes_returns_one_without_a_start_node() -> None:
    """No ``start_node`` yields zero words and the floored one-minute estimate."""
    story = {
        "metadata": {"age_band": "8-11"},
        "nodes": [{"id": "s", "body": "hello world"}],
    }
    assert recompute_estimated_minutes(story) == 1


@pytest.mark.unit
def test_recompute_estimated_minutes_falls_back_when_ending_unreachable() -> None:
    """When no ending is reachable, the estimate falls back to the start's words."""
    story = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            # start has no choices, so the ending is unreachable from it
            {"id": "s", "body": "<<FILL role=passage words=240 beats='x'>>"},
            {
                "id": "e",
                "is_ending": True,
                "body": "done",
                "ending": {"id": "e_end", "kind": "success"},
            },
        ],
    }
    # 240 start words / 120 wpm (8-11) = 2 minutes; the unreachable-ending path
    # returns the start node's own word budget.
    assert recompute_estimated_minutes(story) == 2
