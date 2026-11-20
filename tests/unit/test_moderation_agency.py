"""Unit tests for the request-path reader-agency advisory.

The detectors are tested in ``test_validator_agency.py``; these tests pin the
wiring decisions a future change can get wrong without any detector changing:
which checks are surfaced and which deliberately are not (`AL-767`), that
nothing gates, that the finding shape lands in the review surface's existing
lanes, that the shape fails open, and that messages carry identifiers rather
than story text.
"""

from __future__ import annotations

from typing import Any

import pytest

from cyo_adventure.api.review_surface import build_review_surface
from cyo_adventure.moderation.agency import (
    CATEGORY_JARGON_LABEL,
    CATEGORY_MERGE_SEAM,
    CATEGORY_META_LABEL,
    CATEGORY_SECOND_PERSON_LABEL,
    CATEGORY_STATELESS_MERGES,
    findings_from_agency,
)
from cyo_adventure.moderation.report import FindingSeverity, Source, Verdict
from cyo_adventure.moderation.synthesis import merge_findings

pytestmark = pytest.mark.unit

_SEAM = "Whichever way Mira had come, every path had led her here at last."


def _node(
    node_id: str,
    body: str,
    targets: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return a non-ending node with one choice per target."""
    return {
        "id": node_id,
        "body": body,
        "is_ending": False,
        "choices": [
            {
                "id": f"c_{node_id}_{i}",
                "label": labels[i] if i < len(labels) else f"Walk to the {target}.",
                "target": target,
            }
            for i, target in enumerate(targets)
        ],
    }


def _ending(node_id: str, body: str, valence: str) -> dict[str, Any]:
    """Return an ending node with the given valence."""
    return {
        "id": node_id,
        "body": body,
        "is_ending": True,
        "choices": [],
        "ending": {"id": f"e_{node_id}", "kind": "setback", "valence": valence},
    }


def _defective_book() -> dict[str, Any]:
    """Return a third-person book carrying every surfaced defect and three not.

    Surfaced: two merge seams (``m1``, ``m2``), a meta label, a jargon label,
    a second-person label, and merges with no variables. Not surfaced, but
    present so their absence is a real assertion: an option recap closing
    ``start``, a give-up close on ``home``, and ``home`` being a negative
    ending one decision from the start.
    """
    return {
        "id": "s1",
        "start_node": "start",
        "metadata": {},
        "variables": [],
        "nodes": [
            _node(
                "start",
                "Mira stood at the mouth of the cave with her brass lantern. "
                "She could take the left tunnel, or she could take the right.",
                ("a", "b", "home"),
            ),
            _node("a", "Mira squeezed through the narrow left tunnel.", ("m1",)),
            _node("b", "Mira waded along the cold right tunnel.", ("m1",)),
            _node(
                "m1",
                f"{_SEAM} A wide chamber glittered with crystals.",
                ("c", "d"),
                ("Ponder the strange glow.", "Use your brass lantern."),
            ),
            _node("c", "Mira climbed the crystal shelf.", ("m2",)),
            _node(
                "d",
                "Mira followed the drip of water.",
                ("m2",),
                ("Head back to the hub.",),
            ),
            _node(
                "m2",
                "Either way, the passages met at a still black pool.",
                ("win",),
            ),
            _ending("win", "Mira found the hidden spring and smiled.", "positive"),
            _ending(
                "home",
                "Mira decided the cave was too dark. She walked home.",
                "negative",
            ),
        ],
    }


def _clean_book() -> dict[str, Any]:
    """Return the same graph with honest openings, story labels, and state."""
    book = _defective_book()
    book["variables"] = [{"name": "has_crystal", "type": "bool", "initial": False}]
    for node in book["nodes"]:
        if node["id"] == "m1":
            node["body"] = "The chamber glittered with crystals."
            node["choices"][0]["label"] = "Touch the glowing crystal."
            node["choices"][1]["label"] = "Raise the brass lantern."
        if node["id"] == "m2":
            node["body"] = "A still black pool waited in the dark."
        if node["id"] == "d":
            node["choices"][0]["label"] = "Follow the drip downhill."
    return book


def _by_category(book: dict[str, Any]) -> dict[str, list[Any]]:
    """Group the advisory findings for ``book`` by category."""
    grouped: dict[str, list[Any]] = {}
    for finding in findings_from_agency(book):
        grouped.setdefault(finding.category, []).append(finding)
    return grouped


def test_a_clean_book_produces_no_findings() -> None:
    """The common case must be silent, or the advisory is noise on every book."""
    assert findings_from_agency(_clean_book()) == []


def test_a_stateless_tree_gets_no_summary() -> None:
    """No merge means no route is erased, whatever the variable count."""
    book: dict[str, Any] = {
        "id": "s1",
        "start_node": "start",
        "metadata": {},
        "variables": [],
        "nodes": [
            _node("start", "Mira looked at the two doors.", ("a", "b")),
            _ending("a", "Mira found the garden.", "positive"),
            _ending("b", "Mira found the library.", "positive"),
        ],
    }
    assert findings_from_agency(book) == []


def test_each_surfaced_defect_produces_its_finding() -> None:
    """Seams per merge node; one finding per defective label, on its node."""
    grouped = _by_category(_defective_book())

    assert [f.node_id for f in grouped[CATEGORY_MERGE_SEAM]] == ["m1", "m2"]
    assert [f.node_id for f in grouped[CATEGORY_META_LABEL]] == ["m1"]
    assert [f.node_id for f in grouped[CATEGORY_JARGON_LABEL]] == ["d"]
    assert [f.node_id for f in grouped[CATEGORY_SECOND_PERSON_LABEL]] == ["m1"]
    # The choice is named so the approver can find the exact button.
    assert "choice c_m1_0 at node m1" in grouped[CATEGORY_META_LABEL][0].message
    assert "choice c_d_0 at node d" in grouped[CATEGORY_JARGON_LABEL][0].message
    assert (
        "choice c_m1_1 at node m1" in grouped[CATEGORY_SECOND_PERSON_LABEL][0].message
    )


def test_a_book_with_merges_and_no_variables_gets_one_summary() -> None:
    """One story-level row built from the offline headline's own clauses."""
    summaries = _by_category(_defective_book())[CATEGORY_STATELESS_MERGES]

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.node_id is None
    assert summary.severity is None
    assert summary.message.startswith(
        "reader agency: 2 merge nodes, 2 of them tell the reader the route did "
        "not matter; 0 variables, so no choice comes back."
    )


def test_recaps_give_ups_and_early_setbacks_are_not_surfaced() -> None:
    """AL-767: recap style per band is unruled; endings are genre-dependent.

    The fixture carries all three, so this fails the day someone wires one
    in without the ruling that would make it a defect.
    """
    categories = {f.category for f in findings_from_agency(_defective_book())}
    assert categories == {
        CATEGORY_MERGE_SEAM,
        CATEGORY_META_LABEL,
        CATEGORY_JARGON_LABEL,
        CATEGORY_SECOND_PERSON_LABEL,
        CATEGORY_STATELESS_MERGES,
    }
    assert not any("recap" in c or "ending" in c or "setback" in c for c in categories)


def test_the_advisory_never_gates() -> None:
    """ADVISORY only: a FLAG would spend the one bounded repair; a BLOCK rejects."""
    findings = findings_from_agency(_defective_book())

    assert findings
    assert all(f.verdict is Verdict.ADVISORY for f in findings)
    assert all(f.source is Source.PIPELINE for f in findings)
    assert all(f.stage == 0 for f in findings)
    assert not any(f.structural for f in findings)
    per_node = [f for f in findings if f.category != CATEGORY_STATELESS_MERGES]
    assert all(f.severity is FindingSeverity.LOW for f in per_node)


def test_merge_stage_collapses_seams_into_one_row_and_keeps_labels_apart() -> None:
    """The persisted shape: one seam row naming every merge node, one per label."""
    merged = merge_findings(findings_from_agency(_defective_book()))
    seams = [f for f in merged if f.category == CATEGORY_MERGE_SEAM]

    assert len(seams) == 1
    assert seams[0].node_ids == ("m1", "m2")
    assert seams[0].message.endswith("(2 findings merged)")
    labels = [f for f in merged if f.category.endswith("_label")]
    assert len(labels) == 3
    assert all(f.node_ids is not None and len(f.node_ids) == 1 for f in labels)


def test_review_surface_shows_the_advisories_without_fanning_them_out() -> None:
    """The approver sees every advisory; none becomes a flagged-passage card.

    Per-node advisories land in the collapsed low-priority lane with their
    nodes for the drill-down (`RS-A1`/`RS-A2`); the summary lands in the
    primary ranked list. Nothing moves the gating summary.
    """
    book = _defective_book()
    merged = merge_findings(findings_from_agency(book))
    report: dict[str, object] = {
        "findings": [f.to_dict() for f in merged],
        "summary": {
            "count": len(merged),
            "hard_block": False,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
    }

    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=book,
        moderation_report=report,
    )

    assert view.report_unusable is False
    assert view.flagged_passages == []
    low = {f.category: f for f in view.low_advisory_findings}
    assert set(low) == {
        CATEGORY_MERGE_SEAM,
        CATEGORY_META_LABEL,
        CATEGORY_JARGON_LABEL,
        CATEGORY_SECOND_PERSON_LABEL,
    }
    assert low[CATEGORY_MERGE_SEAM].node_ids == ["m1", "m2"]
    assert low[CATEGORY_JARGON_LABEL].node_id == "d"
    assert [f.category for f in view.ranked_findings] == [CATEGORY_STATELESS_MERGES]
    assert [f.category for f in view.story_level_findings] == [
        CATEGORY_STATELESS_MERGES
    ]
    assert view.summary is not None
    assert view.summary.hard_block is False
    assert view.summary.soft_flag is False


def test_no_finding_message_carries_story_text() -> None:
    """#CRITICAL guard: messages ride a PII-guarded surface; labels are prose."""
    for finding in findings_from_agency(_defective_book()):
        for fragment in (
            "Mira",
            "Whichever",
            "crystal",
            "Ponder",
            "glow",
            "lantern",
            "the hub",
        ):
            assert fragment not in finding.message, (finding.category, fragment)


@pytest.mark.parametrize(
    "blob",
    [
        pytest.param({"id": "s1"}, id="no-nodes"),
        pytest.param({"id": "s1", "nodes": "not a list"}, id="nodes-not-list"),
        pytest.param({"id": "s1", "nodes": ["not a dict"]}, id="node-not-dict"),
        pytest.param(
            {"id": "s1", "nodes": [{"id": "n", "choices": "x"}]},
            id="choices-not-list",
        ),
        pytest.param(
            {"id": "s1", "nodes": [{"id": "n", "choices": ["x"]}]},
            id="choice-not-dict",
        ),
        pytest.param(
            {"id": "s1", "nodes": [], "variables": "x"}, id="variables-not-list"
        ),
    ],
)
def test_an_unreadable_blob_fails_open(blob: dict[str, Any]) -> None:
    """Advisory by contract: an unreadable shape must never break moderation."""
    assert findings_from_agency(blob) == []
