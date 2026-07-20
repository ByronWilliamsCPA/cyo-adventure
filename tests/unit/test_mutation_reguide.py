"""Tests for the WS-5 D8 re-guidance resolution flow (mutation/reguide.py)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.mutation.ops import ReguideItem, ReguideTarget
from cyo_adventure.mutation.reguide import (
    ReguideResolutions,
    ResolvedReguide,
    load_resolutions,
    reconcile,
    resolved_ids,
    unresolved_targets,
)

if TYPE_CHECKING:
    from pathlib import Path


def _emitted() -> tuple[ReguideItem, ...]:
    return (
        ReguideItem(
            target=ReguideTarget.CHOICE,
            target_id="c1",
            reason="new seam label",
            current_text="old label",
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id="n1",
            reason="graft root beats",
            current_text="old beats",
        ),
    )


def _resolutions(*target_ids: str) -> ReguideResolutions:
    return ReguideResolutions(
        resolutions=[
            ResolvedReguide(
                target=ReguideTarget.NODE,
                target_id=tid,
                resolved_text=f"new text for {tid}",
                author="tester",
            )
            for tid in target_ids
        ]
    )


@pytest.mark.unit
def test_resolved_ids_and_unresolved_targets() -> None:
    """resolved_ids returns covered targets; unresolved lists the rest in order."""
    resolutions = _resolutions("c1")
    assert resolved_ids(resolutions) == frozenset({"c1"})
    assert unresolved_targets(_emitted(), resolutions) == ["n1"]


@pytest.mark.unit
def test_unresolved_targets_empty_when_all_resolved() -> None:
    """A fully-resolved emitted set has no outstanding targets."""
    resolutions = _resolutions("c1", "n1")
    assert unresolved_targets(_emitted(), resolutions) == []


@pytest.mark.unit
def test_reconcile_records_before_after_and_summary() -> None:
    """reconcile pairs each emitted item with its resolution and summarizes."""
    doc = reconcile(_emitted(), _resolutions("c1", "n1"))
    assert doc["emitted_count"] == 2
    assert doc["resolved_count"] == 2
    assert doc["outstanding"] == []
    assert doc["fully_resolved"] is True
    items = doc["items"]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    assert first["before"] == "old label"
    assert first["after"] == "new text for c1"
    assert first["resolved"] is True


@pytest.mark.unit
def test_reconcile_marks_outstanding_when_partial() -> None:
    """A partially-resolved set is not fully_resolved and lists the gap."""
    doc = reconcile(_emitted(), _resolutions("c1"))
    assert doc["fully_resolved"] is False
    assert doc["outstanding"] == ["n1"]
    assert doc["resolved_count"] == 1


@pytest.mark.unit
def test_reconcile_default_no_resolutions() -> None:
    """With no resolutions, every emitted item is outstanding."""
    doc = reconcile(_emitted())
    assert doc["resolved_count"] == 0
    assert doc["outstanding"] == ["c1", "n1"]


@pytest.mark.unit
def test_load_resolutions_round_trip(tmp_path: Path) -> None:
    """A resolution file loads into a validated ReguideResolutions."""
    path = tmp_path / "resolve.json"
    path.write_text(
        json.dumps(
            {
                "mutant_slug": "m",
                "resolutions": [
                    {
                        "target": "choice",
                        "target_id": "c1",
                        "resolved_text": "a new label",
                        "author": "byron",
                        "note": "seam",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = load_resolutions(path)
    assert loaded.mutant_slug == "m"
    assert resolved_ids(loaded) == frozenset({"c1"})
