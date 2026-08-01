"""Unit tests for the pure Storybook-blob helpers (W3.1, badge 7)."""

from __future__ import annotations

import pytest

from cyo_adventure.progress.blob import book_title, ending_count, ending_valence_map
from cyo_adventure.storybook.sentinels import wrap


@pytest.mark.unit
class TestEndingValenceMap:
    def test_maps_ending_ids_to_valence(self) -> None:
        blob = {
            "nodes": [
                {"id": "n1", "is_ending": False},
                {
                    "id": "n2",
                    "is_ending": True,
                    "ending": {
                        "id": "e-sad",
                        "valence": "negative",
                        "kind": "setback",
                        "title": "Oh no",
                    },
                },
                {
                    "id": "n3",
                    "is_ending": True,
                    "ending": {
                        "id": "e-happy",
                        "valence": "positive",
                        "kind": "success",
                        "title": "Yay",
                    },
                },
            ]
        }
        assert ending_valence_map(blob) == {"e-sad": "negative", "e-happy": "positive"}

    def test_non_list_nodes_returns_empty(self) -> None:
        assert ending_valence_map({"nodes": "not-a-list"}) == {}

    def test_missing_nodes_returns_empty(self) -> None:
        assert ending_valence_map({}) == {}

    def test_skips_malformed_ending_node(self) -> None:
        blob = {
            "nodes": [
                {"id": "n1", "is_ending": True, "ending": "not-a-dict"},
                {"id": "n2", "is_ending": True, "ending": {"id": "e1"}},
            ]
        }
        assert ending_valence_map(blob) == {}

    def test_ignores_non_ending_nodes(self) -> None:
        blob = {
            "nodes": [
                {
                    "id": "n1",
                    "is_ending": False,
                    "ending": {"id": "e1", "valence": "positive"},
                }
            ]
        }
        assert ending_valence_map(blob) == {}


@pytest.mark.unit
class TestEndingCount:
    def test_reads_metadata(self) -> None:
        assert ending_count({"metadata": {"ending_count": 5}}, "s1", 1) == 5

    def test_missing_metadata_defaults_zero(self) -> None:
        assert ending_count({}, "s1", 1) == 0

    def test_non_int_logs_and_defaults_zero(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING"):
            result = ending_count({"metadata": {"ending_count": "seven"}}, "s1", 1)
        assert result == 0
        assert "progress_malformed_ending_count" in caplog.text

    def test_bool_rejected_as_non_int(self) -> None:
        assert ending_count({"metadata": {"ending_count": True}}, "s1", 1) == 0


@pytest.mark.unit
class TestBookTitle:
    def test_uses_blob_title(self) -> None:
        assert book_title({"title": "Space Race"}, "fallback", 1) == "Space Race"

    def test_falls_back_on_missing_title(self) -> None:
        assert book_title({}, "fallback-id", 1) == "fallback-id"


@pytest.mark.unit
def test_book_title_strips_sentinels() -> None:
    """Referenced by name from tests/unit/test_title_strip_registry.py's
    ENFORCED mapping (``BookProgressView.title``); kept as a bare top-level
    function so that registry's plain-text ``def <name>(`` scan finds it.
    """
    token = wrap("HERO", "Explorer")
    title = book_title({"title": f"{token} and the Map"}, "fallback-id", 1)
    assert "{~" not in title
    assert "Explorer" in title
