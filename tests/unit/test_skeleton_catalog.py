"""Unit tests for the skeleton catalog region builder."""

from __future__ import annotations

import pytest

from cyo_adventure.generation.skeleton_catalog import (
    BEGIN_MARKER,
    END_MARKER,
    build_catalog_region,
    splice_region,
)


def _row(title: str, band: str, minutes: int, endings: list[str]) -> dict[str, object]:
    nodes: list[dict[str, object]] = [
        {
            "id": "n0",
            "body": "<<FILL role=setup words=10 beats='x'>>",
            "is_ending": False,
        }
    ]
    for i, val in enumerate(endings):
        nodes.append(
            {
                "id": f"e{i}",
                "is_ending": True,
                "ending": {"valence": val, "kind": "completion", "title": "T"},
            }
        )
    return {
        "title": title,
        "metadata": {
            "age_band": band,
            "tier": 1,
            "estimated_minutes": minutes,
            "topology": "loop_and_grow",
        },
        "nodes": nodes,
    }


@pytest.mark.unit
def test_region_is_wrapped_in_markers() -> None:
    region = build_catalog_region([_row("A", "3-5", 5, ["positive"])], slugs=["a"])
    assert region.startswith(BEGIN_MARKER)
    assert region.rstrip().endswith(END_MARKER)


@pytest.mark.unit
def test_region_lists_each_skeleton_with_band_and_length() -> None:
    region = build_catalog_region(
        [_row("The Lost Mitten", "3-5", 5, ["positive", "positive"])],
        slugs=["the-lost-mitten"],
    )
    assert "The Lost Mitten" in region
    assert "| 3-5 |" in region
    assert "| 5 |" in region
    assert "the-lost-mitten.svg" in region


@pytest.mark.unit
def test_coverage_matrix_marks_populated_and_empty_bands() -> None:
    region = build_catalog_region([_row("A", "3-5", 5, ["positive"])], slugs=["a"])
    # Assert the coverage-matrix row form, not a bare substring: "3-5" also
    # appears in the documented-skeletons table above, so a substring check
    # would pass even on a malformed matrix.
    assert "| 3-5 | yes |" in region
    assert "| 5-8 | none yet |" in region


@pytest.mark.unit
def test_splice_region_replaces_between_markers() -> None:
    doc = f"intro\n{BEGIN_MARKER}\nOLD\n{END_MARKER}\noutro\n"
    new = f"{BEGIN_MARKER}\nNEW\n{END_MARKER}\n"
    out = splice_region(doc, new)
    assert "NEW" in out
    assert "OLD" not in out
    assert out.startswith("intro")
    assert out.rstrip().endswith("outro")


@pytest.mark.unit
def test_splice_region_appends_when_markers_absent() -> None:
    # Fallback path: a doc with no markers gets the region appended, not lost.
    doc = "intro\nno markers here\n"
    region = f"{BEGIN_MARKER}\nNEW\n{END_MARKER}\n"
    out = splice_region(doc, region)
    assert out.startswith("intro")
    assert "no markers here" in out
    assert BEGIN_MARKER in out
    assert "NEW" in out
    assert out.rstrip().endswith(END_MARKER)
