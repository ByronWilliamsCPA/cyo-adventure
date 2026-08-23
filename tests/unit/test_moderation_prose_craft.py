"""Unit tests for the request-path prose-craft advisory.

The detectors themselves are tested in ``test_validator_prose_craft.py``;
these tests pin the wiring decisions, which are the part a future change can
get wrong without any detector changing: that the guard never gates, that it
fails open on a shape it cannot read, and that its messages carry numbers
rather than story prose.
"""

from __future__ import annotations

from typing import Any

import pytest

from cyo_adventure.moderation.prose_craft import findings_from_prose_craft
from cyo_adventure.moderation.report import Source, Verdict

pytestmark = pytest.mark.unit


def _node(node_id: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
    """Build one node with the given body and choice labels."""
    return {
        "id": node_id,
        "body": body,
        "choices": [
            {"id": f"{node_id}c{i}", "label": label, "target": "n0"}
            for i, label in enumerate(labels or [])
        ],
    }


def _book(nodes: list[dict[str, Any]], **metadata: str) -> dict[str, Any]:
    """Build a story blob around the given nodes and metadata declarations."""
    return {"id": "s1", "nodes": nodes, "metadata": dict(metadata)}


def _clean_prose(count: int) -> list[dict[str, Any]]:
    """Build ``count`` third-person nodes with distinct bodies and labels."""
    return [
        _node(
            f"n{i}",
            f"Priya counted seedling number {i} and marked the tray with chalk.",
            [f"Check tray {i}", f"Water tray {i}"],
        )
        for i in range(count)
    ]


def test_a_clean_book_produces_no_findings() -> None:
    """The common case must be silent, or the advisory is noise on every book."""
    assert findings_from_prose_craft(_book(_clean_prose(30))) == []


def test_duplicate_bodies_produce_an_advisory() -> None:
    """Zero duplicate bodies in the known-good corpus; 23 in the worst live book."""
    nodes = _clean_prose(10)
    nodes[3]["body"] = nodes[0]["body"]
    nodes[7]["body"] = nodes[0]["body"]

    findings = findings_from_prose_craft(_book(nodes))

    assert len(findings) == 1
    assert findings[0].category == "prose_craft_sameness"
    # Not `"2" in message`: the fixed calibration text ("0.02 to 0.27") and
    # the label count both contain a 2, so that passes at any count.
    assert findings[0].message.startswith(
        "self-repetition: 2 nodes repeat another node's exact body"
    )


def test_the_advisory_never_gates() -> None:
    """The whole guard is advisory: a FLAG would route the book into repair.

    A bounded repair asks the model to rewrite the document, which is neither
    what a collapsed label set needs nor something the repair budget can
    afford; the human approval gate is where this evidence is meant to land.
    """
    nodes = _clean_prose(10)
    nodes[3]["body"] = nodes[0]["body"]

    findings = findings_from_prose_craft(
        _book(nodes, narrative_person="third", narrative_style="gamebook")
    )

    assert findings
    assert all(f.verdict is Verdict.ADVISORY for f in findings)
    assert all(f.source is Source.PIPELINE for f in findings)
    assert all(f.stage == 0 for f in findings)


def test_a_small_book_is_not_judged_for_label_collapse() -> None:
    """A six-label picture book scores a top-3 share of 1.0 and has done nothing."""
    nodes = [_node(f"n{i}", f"Body {i} differs.", ["Go", "Stay"]) for i in range(3)]
    assert findings_from_prose_craft(_book(nodes)) == []


def test_label_collapse_on_a_large_book_produces_an_advisory() -> None:
    """Three strings covering most of 674 choices is the live defect this catches."""
    nodes = [
        _node(f"n{i}", f"Body {i} differs entirely from the others.", ["Go", "Stay"])
        for i in range(40)
    ]
    findings = findings_from_prose_craft(_book(nodes))
    assert [f.category for f in findings] == ["prose_craft_sameness"]


def test_a_third_person_declaration_contradicted_by_the_prose_is_reported() -> None:
    """The 3-5 book that shipped fully second-person against third-person beats."""
    nodes = [
        _node(f"n{i}", f"You reach for lantern {i} and you feel the heat.")
        for i in range(10)
    ]
    findings = findings_from_prose_craft(_book(nodes, narrative_person="third"))
    assert [f.category for f in findings] == ["prose_craft_person"]
    assert "third" in findings[0].message


def test_an_undeclared_prose_book_gets_no_person_advisory() -> None:
    """Nothing pins an undeclared book's person, so nothing may be claimed."""
    nodes = [
        _node(f"n{i}", f"You reach for lantern {i} and you feel the heat.")
        for i in range(10)
    ]
    assert findings_from_prose_craft(_book(nodes)) == []


def test_a_gamebook_written_in_third_person_is_reported() -> None:
    """Committed gamebooks run 0.715 to 1.0; the genre is second-person address."""
    nodes = [
        _node(f"n{i}", f"Priya lifted lantern {i} and the shadows shifted.")
        for i in range(10)
    ]
    findings = findings_from_prose_craft(
        _book(nodes, narrative_style="gamebook", narrative_person="second")
    )
    assert [f.category for f in findings] == ["prose_craft_person"]


def test_both_defects_at_once_produce_both_advisories() -> None:
    """The two detectors are independent; neither may mask the other."""
    nodes = [
        _node(f"n{i}", f"You reach for lantern {i} and you feel the heat.")
        for i in range(10)
    ]
    nodes[4]["body"] = nodes[0]["body"]

    categories = [
        f.category
        for f in findings_from_prose_craft(_book(nodes, narrative_person="third"))
    ]

    assert sorted(categories) == ["prose_craft_person", "prose_craft_sameness"]


def test_a_blob_with_no_readable_nodes_fails_open() -> None:
    """Advisory by contract: an unreadable shape must never break moderation."""
    assert findings_from_prose_craft({"id": "s1", "nodes": "not a list"}) == []
    assert findings_from_prose_craft({"id": "s1"}) == []
    assert findings_from_prose_craft({"id": "s1", "nodes": ["not a dict"]}) == []


def test_no_finding_message_carries_story_prose() -> None:
    """#CRITICAL guard: these messages ride a PII-guarded surface.

    The leaf-diversity precedent keeps its messages prose-free (instructions
    and numbers only) for exactly this reason. A body that leaked into a
    message would carry a child's personalized story text with it.
    """
    body = "Priya unlocked the hydroponics bay with her grandmother's brass key."
    nodes = [_node(f"n{i}", body) for i in range(10)]

    findings = findings_from_prose_craft(_book(nodes, narrative_person="third"))

    assert findings
    for finding in findings:
        assert "Priya" not in finding.message
        assert "hydroponics" not in finding.message
