"""Tests for the CG-1..CG-4 choice-grammar advisories (W2.1, ADR-011 section 10).

Strategy: build small synthetic Storybook fixtures (via ``Storybook.model_validate``)
with controlled graph shapes, rather than relying on the committed skeleton catalog,
so each rule's boundary can be pinned exactly.

Every CG-* finding is WARNING severity and must never set ``report.ok`` to False;
each rule is exercised both firing and non-firing, per the implementation plan.
"""

from __future__ import annotations

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.choice_grammar import (
    check_choice_grammar,
    check_choiceless_run_cap,
    check_fill_gate_acknowledgment,
    check_options_per_choice,
    check_words_per_stop,
)
from cyo_adventure.validator.report import Severity

# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

_BASE_METADATA: dict[str, object] = {
    "reading_level": {"scheme": "flesch_kincaid", "target": 4.0, "tolerance": 1.0},
    "tier": 1,
    "themes": [],
    "estimated_minutes": 5,
    "topology": "branch_and_bottleneck",
    "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
}


def _ending_node(
    node_id: str,
    ending_id: str,
    body: str = "The end of the story, quiet and warm.",
) -> dict[str, object]:
    return {
        "id": node_id,
        "body": body,
        "is_ending": True,
        "choices": [],
        "ending": {
            "id": ending_id,
            "valence": "positive",
            "kind": "success",
            "title": "Done",
        },
    }


def _story(
    band: str,
    nodes: list[dict[str, object]],
    start_node: str,
    ending_count: int = 1,
) -> Storybook:
    metadata = {**_BASE_METADATA, "age_band": band, "ending_count": ending_count}
    return Storybook.model_validate(
        {
            "schema_version": "2.0",
            "id": "test_story",
            "version": 1,
            "title": "Test Story",
            "metadata": metadata,
            "variables": [],
            "start_node": start_node,
            "nodes": nodes,
        }
    )


def _chain_story(band: str, run_length: int, extra_words: int = 0) -> Storybook:
    """Build a story whose start node begins a run of ``run_length`` single-
    choice nodes, followed by one ending. Each single-choice node body has
    ``extra_words`` filler words beyond a fixed base, to size the run's word
    total for CG-3.
    """
    filler = ("word " * extra_words).strip()
    nodes: list[dict[str, object]] = []
    for i in range(run_length):
        node_id = f"n{i}"
        target = f"n{i + 1}" if i + 1 < run_length else "n_end"
        body = f"A short beat. {filler}".strip()
        nodes.append(
            {
                "id": node_id,
                "body": body,
                "is_ending": False,
                "choices": [{"id": f"c{i}", "label": "Go on.", "target": target}],
            }
        )
    nodes.append(_ending_node("n_end", "e_done"))
    return _story(band, nodes, "n0")


# ---------------------------------------------------------------------------
# CG-1: choiceless-run cap
# ---------------------------------------------------------------------------


class TestChoicelessRunCap:
    def test_discrete_band_within_cap_is_silent(self) -> None:
        """3-5's cap is 3; a run of exactly 3 single-choice nodes is fine."""
        story = _chain_story("3-5", run_length=3)
        report = check_choiceless_run_cap(story)
        assert report.findings == []

    def test_discrete_band_over_cap_fires(self) -> None:
        """3-5's cap is 3; a run of 4 fires CG-1."""
        story = _chain_story("3-5", run_length=4)
        report = check_choiceless_run_cap(story)
        cg1 = [f for f in report.findings if f.rule_id == "CG-1"]
        assert len(cg1) == 1
        assert cg1[0].node_id == "n0"
        assert cg1[0].severity is Severity.WARNING

    def test_5_8_band_cap_is_two(self) -> None:
        assert (
            check_choiceless_run_cap(_chain_story("5-8", run_length=2)).findings == []
        )
        over = check_choiceless_run_cap(_chain_story("5-8", run_length=3))
        assert len(over.findings) == 1

    def test_flowed_band_tolerates_up_to_six(self) -> None:
        """8-11+ allows runs up to 6 (the graph may stay linear; ADR-026 flows
        it at render time)."""
        story = _chain_story("8-11", run_length=6)
        report = check_choiceless_run_cap(story)
        assert report.findings == []

    def test_flowed_band_over_six_fires_with_word_detail(self) -> None:
        story = _chain_story("8-11", run_length=7, extra_words=30)
        report = check_choiceless_run_cap(story)
        cg1 = [f for f in report.findings if f.rule_id == "CG-1"]
        assert len(cg1) == 1
        assert "words-per-stop" in cg1[0].message

    def test_report_ok_true_despite_finding(self) -> None:
        story = _chain_story("3-5", run_length=5)
        report = check_choiceless_run_cap(story)
        assert report.findings, "expected a finding to test report.ok against"
        assert report.ok is True

    def test_every_age_band_is_covered_by_a_cap_table(self) -> None:
        """Lockstep guard (mirrors test_band_profile.py): every AgeBand value
        falls into exactly one of the discrete or flowed cap tables, so the
        "unknown band" no-op branch in check_choiceless_run_cap is genuinely
        unreachable through any valid, enum-constrained age_band rather than
        silently swallowing a band this module forgot to configure."""
        from cyo_adventure.storybook.models import AgeBand
        from cyo_adventure.validator import choice_grammar as cg_module

        covered = set(cg_module._DISCRETE_RUN_CAP) | cg_module._FLOWED_BANDS
        assert covered == {band.value for band in AgeBand}


# ---------------------------------------------------------------------------
# CG-2: options-per-choice bounds
# ---------------------------------------------------------------------------


def _decision_story(band: str, option_count: int) -> Storybook:
    choices = [
        {"id": f"c{i}", "label": f"Option {i}.", "target": "n_end"}
        for i in range(option_count)
    ]
    nodes: list[dict[str, object]] = [
        {"id": "n0", "body": "Pick a path.", "is_ending": False, "choices": choices},
        _ending_node("n_end", "e_done"),
    ]
    return _story(band, nodes, "n0")


class TestOptionsPerChoice:
    def test_3_5_two_options_is_silent(self) -> None:
        report = check_options_per_choice(_decision_story("3-5", 2))
        assert report.findings == []

    def test_3_5_three_options_fires(self) -> None:
        report = check_options_per_choice(_decision_story("3-5", 3))
        cg2 = [f for f in report.findings if f.rule_id == "CG-2"]
        assert len(cg2) == 1
        assert cg2[0].node_id == "n0"
        assert cg2[0].severity is Severity.WARNING

    def test_8_11_below_bound_fires(self) -> None:
        """8-11 requires exactly 3; a 2-option decision node is flagged."""
        report = check_options_per_choice(_decision_story("8-11", 2))
        assert len(report.findings) == 1

    def test_13_16_within_range_is_silent(self) -> None:
        """13-16 allows 3-4."""
        assert check_options_per_choice(_decision_story("13-16", 3)).findings == []
        assert check_options_per_choice(_decision_story("13-16", 4)).findings == []

    def test_13_16_five_options_fires(self) -> None:
        report = check_options_per_choice(_decision_story("13-16", 5))
        assert len(report.findings) == 1

    def test_single_choice_node_is_not_a_decision_node(self) -> None:
        """A single-choice node is out of CG-2's scope (that is CG-1's rule)."""
        story = _chain_story("3-5", run_length=1)
        report = check_options_per_choice(story)
        assert report.findings == []


# ---------------------------------------------------------------------------
# CG-3: words-per-stop ceiling
# ---------------------------------------------------------------------------


class TestWordsPerStop:
    def test_under_ceiling_is_silent(self) -> None:
        """8-11's ceiling is 135; a short 3-node run stays well under it."""
        story = _chain_story("8-11", run_length=3, extra_words=5)
        report = check_words_per_stop(story)
        assert report.findings == []

    def test_over_ceiling_fires(self) -> None:
        story = _chain_story("8-11", run_length=3, extra_words=60)
        report = check_words_per_stop(story)
        cg3 = [f for f in report.findings if f.rule_id == "CG-3"]
        assert len(cg3) == 1
        assert cg3[0].severity is Severity.WARNING
        assert "words-per-stop" in cg3[0].message

    def test_discrete_band_never_fires(self) -> None:
        """3-5/5-8 have no words-per-stop ceiling (discrete pages, not flowed)."""
        story = _chain_story("3-5", run_length=2, extra_words=200)
        report = check_words_per_stop(story)
        assert report.findings == []

    def test_unfilled_skeleton_uses_declared_words(self) -> None:
        """A skeleton body (``<<FILL ... words=N ...>>``) is sized from its
        declared word target rather than skipped outright."""
        nodes: list[dict[str, object]] = [
            {
                "id": "n0",
                "body": "<<FILL role=beat words=120>>",
                "is_ending": False,
                "choices": [{"id": "c0", "label": "Go on.", "target": "n1"}],
            },
            {
                "id": "n1",
                "body": "<<FILL role=beat words=100>>",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Go on.", "target": "n_end"}],
            },
            _ending_node("n_end", "e_done"),
        ]
        story = _story("8-11", nodes, "n0")
        report = check_words_per_stop(story)
        cg3 = [f for f in report.findings if f.rule_id == "CG-3"]
        assert len(cg3) == 1


# ---------------------------------------------------------------------------
# CG-4: fill-gate acknowledgment
# ---------------------------------------------------------------------------


class TestFillGateAcknowledgment:
    def test_shared_content_word_is_silent(self) -> None:
        nodes: list[dict[str, object]] = [
            {
                "id": "n0",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {"id": "c0", "label": "Climb the tower.", "target": "n_tower"},
                    {"id": "c1", "label": "Enter the cave.", "target": "n_cave"},
                ],
            },
            {
                "id": "n_tower",
                "body": "You climb the tall tower, breathless. It creaks underfoot.",
                "is_ending": True,
                "choices": [],
                "ending": {
                    "id": "e_tower",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Tower",
                },
            },
            _ending_node("n_cave", "e_cave", body="You enter the cave, cool and dark."),
        ]
        story = _story("8-11", nodes, "n0", ending_count=2)
        report = check_fill_gate_acknowledgment(story)
        assert [f for f in report.findings if f.node_id == "n_tower"] == []

    def test_no_shared_content_word_fires(self) -> None:
        nodes: list[dict[str, object]] = [
            {
                "id": "n0",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {"id": "c0", "label": "Climb the tower.", "target": "n_tower"},
                    {"id": "c1", "label": "Enter the cave.", "target": "n_cave"},
                ],
            },
            {
                "id": "n_tower",
                "body": "Rain fell softly on the quiet meadow below.",
                "is_ending": True,
                "choices": [],
                "ending": {
                    "id": "e_tower",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Meadow",
                },
            },
            _ending_node("n_cave", "e_cave", body="You enter the cave, cool and dark."),
        ]
        story = _story("8-11", nodes, "n0", ending_count=2)
        report = check_fill_gate_acknowledgment(story)
        cg4 = [f for f in report.findings if f.rule_id == "CG-4"]
        assert len(cg4) == 1
        assert cg4[0].node_id == "n_tower"
        assert cg4[0].choice_id == "c0"
        assert cg4[0].severity is Severity.WARNING

    def test_unfilled_target_is_skipped(self) -> None:
        nodes: list[dict[str, object]] = [
            {
                "id": "n0",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {"id": "c0", "label": "Climb the tower.", "target": "n_tower"},
                    {"id": "c1", "label": "Enter the cave.", "target": "n_cave"},
                ],
            },
            {
                "id": "n_tower",
                "body": "<<FILL role=beat words=80>>",
                "is_ending": False,
                "choices": [{"id": "c2", "label": "Go on.", "target": "n_end"}],
            },
            _ending_node("n_cave", "e_cave", body="You enter the cave, cool and dark."),
            _ending_node("n_end", "e_done"),
        ]
        story = _story("8-11", nodes, "n0", ending_count=2)
        report = check_fill_gate_acknowledgment(story)
        assert report.findings == []


# ---------------------------------------------------------------------------
# Gating: enforce_grammar (D3/D11 grandfathering)
# ---------------------------------------------------------------------------


class TestEnforceGrammarGate:
    def test_default_is_silent_even_with_violations(self) -> None:
        story = _chain_story("3-5", run_length=10)
        report = check_choice_grammar(story)
        assert report.findings == []

    def test_opt_in_reports_findings(self) -> None:
        story = _chain_story("3-5", run_length=10)
        report = check_choice_grammar(story, enforce_grammar=True)
        assert any(f.rule_id == "CG-1" for f in report.findings)

    def test_all_findings_advisory_only(self) -> None:
        story = _chain_story("3-5", run_length=10)
        report = check_choice_grammar(story, enforce_grammar=True)
        assert report.findings, "expected findings to assert severity over"
        assert all(f.severity is Severity.WARNING for f in report.findings)
        assert report.ok is True
