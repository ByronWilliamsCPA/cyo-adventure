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
    """Pins the 3-excerpt count cap via the " | " separator count.

    The per-excerpt 150-char cap is pinned independently by
    test_single_ending_excerpt_is_capped_at_150_chars; this test only needs to
    prove the _MAX_ENDING_EXCERPTS=3 cap holds when more than 3 ending nodes
    are present.
    """
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
    # 3 excerpts joined by " | " means exactly 2 separators; pins the count
    # cap independent of the per-excerpt cap (pinned separately above).
    assert ctx.ending_summary.count(" | ") == 2
    # With per-excerpt caps of 150 chars and at most 3 excerpts, the maximum
    # possible summary length is 3 * 150 + 2 * len(" | ") = 456, well under
    # the outer 600-char slice. The outer 600 cap is a defensive backstop
    # that cannot fire under the current constants, so this pins the real,
    # reachable bound instead of fabricating a scenario for the unreachable
    # outer cap.
    assert len(ctx.ending_summary) <= 456


def test_single_ending_excerpt_is_capped_at_150_chars() -> None:
    """A single long ending pins the 150-char per-excerpt cap on its own.

    With only one excerpt the " | " join contributes nothing and the outer
    600-char slice never engages (150 < 600), so a summary length of exactly
    150 can only be explained by the per-excerpt cap firing.
    """
    blob = {
        "title": "T",
        "nodes": [
            {
                "id": "n1",
                "body": "m" * 144 + "OVERFLOW",
                "is_ending": True,
                "ending": {"id": "e1", "title": "Long"},
            }
        ],
    }
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.ending_summary == "Long: " + "m" * 144
    assert len(ctx.ending_summary) == 150
    assert "OVERFLOW" not in ctx.ending_summary


def test_malformed_blob_degrades_to_defaults() -> None:
    ctx = anchor_context_from_blob(
        {"title": 7, "nodes": "not-a-list"}, character_names=[]
    )
    assert ctx.title == "Untitled story"
    assert ctx.ending_summary == ""
