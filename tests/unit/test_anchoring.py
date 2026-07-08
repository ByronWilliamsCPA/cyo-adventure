"""Unit tests for anchor-context extraction (WS-B PR 3)."""

from __future__ import annotations

from cyo_adventure.story_requests.anchoring import anchor_context_from_blob


def _blob() -> dict[str, object]:
    return {
        "title": "The Fox and the Map",
        "nodes": [
            {"id": "n1", "body": "You set off.", "is_ending": False},
            {
                "id": "n2",
                "body": "You find the treasure and share it with the village.",
                "is_ending": True,
                "ending": {"id": "e1", "title": "Treasure shared"},
            },
            {
                "id": "n3",
                "body": "You head home for supper.",
                "is_ending": True,
                "ending": {"id": "e2", "title": "Home again"},
            },
        ],
    }


def test_extracts_title_names_and_ending_excerpts() -> None:
    ctx = anchor_context_from_blob(_blob(), character_names=["Robin"])
    assert ctx.title == "The Fox and the Map"
    assert ctx.character_names == ["Robin"]
    assert "Treasure shared: You find the treasure" in ctx.ending_summary
    assert "Home again" in ctx.ending_summary


def test_caps_excerpt_count_and_length() -> None:
    blob = _blob()
    nodes = blob["nodes"]
    assert isinstance(nodes, list)
    for i in range(5):
        nodes.append(
            {
                "id": f"x{i}",
                "body": "y" * 500,
                "is_ending": True,
                "ending": {"id": f"ex{i}", "title": "Long"},
            }
        )
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert len(ctx.ending_summary) <= 600
    assert ctx.ending_summary.count("|") <= 2


def test_malformed_blob_degrades_to_defaults() -> None:
    ctx = anchor_context_from_blob(
        {"title": 7, "nodes": "not-a-list"}, character_names=[]
    )
    assert ctx.title == "Untitled story"
    assert ctx.ending_summary == ""
