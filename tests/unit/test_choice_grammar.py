"""Tests for the CG-1..CG-4 choice-grammar advisories (W2.1, ADR-011 section 10).

Strategy: build small synthetic Storybook fixtures (via ``Storybook.model_validate``)
with controlled graph shapes, rather than relying on the committed skeleton catalog,
so each rule's boundary can be pinned exactly.

Every CG-* finding is WARNING severity and must never set ``report.ok`` to False;
each rule is exercised both firing and non-firing, per the implementation plan.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator import choice_grammar
from cyo_adventure.validator.choice_grammar import (
    check_choice_grammar,
    check_choiceless_run_cap,
    check_fill_gate_acknowledgment,
    check_options_per_choice,
    check_visible_run_cap,
    check_words_per_stop,
)
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.report import Severity
from cyo_adventure.validator.walk import ConfigDag

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


def _stateful_story(
    band: str, nodes: list[dict[str, object]], start_node: str
) -> Storybook:
    """Build a Tier-2 story declaring one `has_key` bool, validated in one pass.

    The variable has to be present when the document is validated: a condition
    naming an undeclared variable is a schema error, so it cannot be patched on
    afterwards with ``model_copy``.
    """
    metadata = {
        **_BASE_METADATA,
        "age_band": band,
        "ending_count": 1,
        "tier": 2,
    }
    return Storybook.model_validate(
        {
            "schema_version": "2.0",
            "id": "test_story",
            "version": 1,
            "title": "Test Story",
            "metadata": metadata,
            "variables": [
                {"name": "has_key", "type": "bool", "initial": False},
            ],
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

    def test_5_8_band_cap_is_three(self) -> None:
        """Raised from 2 on 2026-08-17 with the CG-1 share allowance: a cap that
        binds before the share would make the share a dead letter, and section
        10's 5-8 cadence is an average ("choice every 1st-2nd page") that the
        share now carries. The local cap stays as a backstop only."""
        assert (
            check_choiceless_run_cap(_chain_story("5-8", run_length=3)).findings == []
        )
        over = check_choiceless_run_cap(_chain_story("5-8", run_length=4))
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


def _mixed_fan_story(band: str, fans: list[int], corridors: int = 0) -> Storybook:
    """Build a story whose decision nodes offer the given per-node fan counts.

    Args:
        band: The age band to declare.
        fans: One entry per decision node, giving how many choices it offers.
        corridors: How many single-choice nodes to prepend, which are NOT
            decision nodes and so must not dilute the CG-2 variance share.

    Returns:
        Storybook: A story with ``len(fans)`` decision nodes and ``corridors``
            single-choice nodes, every choice landing on one shared ending.
    """
    nodes: list[dict[str, object]] = []
    first_decision = f"d{0}"
    for index in range(corridors):
        nxt = f"k{index + 1}" if index + 1 < corridors else first_decision
        nodes.append(
            {
                "id": f"k{index}",
                "body": "Walk on.",
                "is_ending": False,
                "choices": [{"id": f"ck{index}", "label": "Go on.", "target": nxt}],
            }
        )
    for index, fan in enumerate(fans):
        nodes.append(
            {
                "id": f"d{index}",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {"id": f"c{index}_{j}", "label": f"Option {j}.", "target": "n_end"}
                    for j in range(fan)
                ],
            }
        )
    nodes.append(_ending_node("n_end", "e_done"))
    return _story(band, nodes, "k0" if corridors else first_decision)


class TestChoicelessShareAllowance:
    """CG-1's 2026-08-17 second axis: a per-band share of no-decision nodes,
    carrying section 10's AVERAGE cadence, with the run cap left as a local
    backstop."""

    def test_a_long_scene_is_allowed_when_the_story_spends_decisions_elsewhere(
        self,
    ) -> None:
        """The point of the change: a 3-corridor scene at 5-8 no longer blocks
        on its own, provided the story's overall cadence stays inside 50%."""
        nodes: list[dict[str, object]] = [
            {
                "id": "k0",
                "body": "A long scene begins.",
                "is_ending": False,
                "choices": [{"id": "a", "label": "Read on.", "target": "k1"}],
            },
            {
                "id": "k1",
                "body": "It continues.",
                "is_ending": False,
                "choices": [{"id": "b", "label": "Read on.", "target": "k2"}],
            },
            {
                "id": "k2",
                "body": "And again.",
                "is_ending": False,
                "choices": [{"id": "c", "label": "Read on.", "target": "d0"}],
            },
        ]
        # five decision nodes, so 3 of 8 non-ending nodes are choiceless (37%)
        nodes.extend(
            {
                "id": f"d{index}",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {
                        "id": f"e{index}_{j}",
                        "label": f"Option {j}.",
                        "target": f"d{index + 1}" if index < 4 else "n_end",
                    }
                    for j in range(2)
                ],
            }
            for index in range(5)
        )
        nodes.append(_ending_node("n_end", "e_done"))
        report = check_choiceless_run_cap(_story("5-8", nodes, "k0"))
        assert [f for f in report.findings if f.rule_id == "CG-1"] == []

    def test_share_above_the_band_allowance_fires(self) -> None:
        """Three choiceless nodes against one decision is 75% at 5-8, over 50%."""
        nodes: list[dict[str, object]] = [
            {
                "id": f"k{i}",
                "body": "Run up.",
                "is_ending": False,
                "choices": [
                    {"id": f"a{i}", "label": "Read on.", "target": f"k{i + 1}"}
                ],
            }
            for i in range(2)
        ]
        nodes.append(
            {
                "id": "k2",
                "body": "Still going.",
                "is_ending": False,
                "choices": [{"id": "a2", "label": "Read on.", "target": "d0"}],
            }
        )
        nodes.append(
            {
                "id": "d0",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {"id": "c0", "label": "One.", "target": "n_end"},
                    {"id": "c1", "label": "Two.", "target": "n_end"},
                ],
            }
        )
        nodes.append(_ending_node("n_end", "e_done"))
        report = check_choiceless_run_cap(_story("5-8", nodes, "k0"))
        share = [f for f in report.findings if "allowance" in f.message]
        assert len(share) == 1
        assert "3 of 4 non-ending nodes are single-choice" in share[0].message

    def test_a_story_with_no_decision_at_all_is_left_to_pl_17(self) -> None:
        """Cadence is undefined with nothing to pace against, so an
        all-corridor graph draws no share finding from this rule."""
        report = check_choiceless_run_cap(_chain_story("5-8", run_length=2))
        assert [f for f in report.findings if "allowance" in f.message] == []

    def test_choiceless_share_ignores_endings_in_the_denominator(self) -> None:
        """An ending can never be single-choice, so counting endings in the
        denominator would hand a story a larger allowance purely for having
        more endings, which is unrelated to its cadence."""
        base: list[dict[str, object]] = [
            {
                "id": "k0",
                "body": "Run up.",
                "is_ending": False,
                "choices": [{"id": "a", "label": "Read on.", "target": "d0"}],
            },
            {
                "id": "d0",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {"id": "c0", "label": "One.", "target": "n_end"},
                    {"id": "c1", "label": "Two.", "target": "n_end2"},
                ],
            },
            _ending_node("n_end", "e_done"),
        ]
        two_endings = [*base, _ending_node("n_end2", "e_done2")]
        many_endings = [
            *base,
            _ending_node("n_end2", "e_done2"),
            _ending_node("n_end3", "e_done3"),
            _ending_node("n_end4", "e_done4"),
            _ending_node("n_end5", "e_done5"),
        ]
        few = check_choiceless_run_cap(_story("5-8", two_endings, "k0", ending_count=2))
        lots = check_choiceless_run_cap(
            _story("5-8", many_endings, "k0", ending_count=5)
        )
        assert [f.message for f in few.findings] == [f.message for f in lots.findings]


class TestOptionsVarianceAllowance:
    """CG-2's 2026-08-17 tiers: a band target, a one-step allowance capped at
    20 percent of decision nodes, and a hard [2, 4] envelope."""

    def test_one_step_variance_inside_the_allowance_is_silent(self) -> None:
        # 10 decision nodes at 8-11 (target exactly 3); two may vary by one.
        report = check_options_per_choice(_mixed_fan_story("8-11", [3] * 8 + [2, 4]))
        assert [f for f in report.findings if f.rule_id == "CG-2"] == []

    def test_variance_above_the_allowance_fires_once(self) -> None:
        # 3 of 10 vary, against an allowance of 2.
        report = check_options_per_choice(_mixed_fan_story("8-11", [3] * 7 + [2, 2, 4]))
        cg2 = [f for f in report.findings if f.rule_id == "CG-2"]
        assert len(cg2) == 1
        assert "above the 20% allowance of 2" in cg2[0].message

    @pytest.mark.parametrize("fan", [5, 7])
    def test_over_the_global_ceiling_fires_at_any_share(self, fan: int) -> None:
        """A fan over 4 is never a permitted variant, even as a lone node.

        Only the ceiling is testable here. The envelope's floor of 2 is already
        structural rather than enforced: :func:`_is_decision` requires two or
        more choices, so a one-choice node is CG-1's subject (a choiceless
        corridor) and never reaches CG-2 at all.
        """
        report = check_options_per_choice(_mixed_fan_story("13-16", [3] * 19 + [fan]))
        cg2 = [f for f in report.findings if f.rule_id == "CG-2"]
        assert len(cg2) == 1
        assert "outside the global envelope" in cg2[0].message

    def test_two_steps_from_the_target_is_not_a_permitted_variant(self) -> None:
        """3-5 targets exactly 2, so a 4-way fan is two steps out and blocks
        even though 4 is inside the global envelope."""
        report = check_options_per_choice(_mixed_fan_story("3-5", [2] * 19 + [4]))
        cg2 = [f for f in report.findings if f.rule_id == "CG-2"]
        assert len(cg2) == 1
        assert "by more than one step" in cg2[0].message

    def test_variance_share_is_measured_against_decision_nodes_not_all_nodes(
        self,
    ) -> None:
        """The allowance counts decision nodes only.

        A story padded with single-choice corridors has the same number of
        decisions, so it must get the same allowance; counting all nodes would
        let a corridor-heavy story carry more odd fans than a branchy one for
        no reason a reader would recognise.
        """
        fans = [3] * 7 + [2, 2, 4]  # 3 of 10 vary, one over the allowance of 2
        bare = check_options_per_choice(_mixed_fan_story("8-11", fans))
        padded = check_options_per_choice(_mixed_fan_story("8-11", fans, corridors=40))
        bare_cg2 = [f for f in bare.findings if f.rule_id == "CG-2"]
        padded_cg2 = [f for f in padded.findings if f.rule_id == "CG-2"]
        assert len(bare_cg2) == 1
        assert [f.message for f in padded_cg2] == [f.message for f in bare_cg2]


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

    def test_discrete_band_is_measured_per_node(self) -> None:
        """3-5 and 5-8 ARE covered now, and a node there is a stop by itself.

        These bands render one node per page (ADR-026 decision 4), so a node is
        a rendered stop and ADR-011 section 10 rules a range for them like every
        other band: 40 words at 3-5, 70 at 5-8. The table carried four bands and
        this test pinned the two-band gap as intentional (`AL-454`, `UW-C276`).

        The substitute at those bands was `words_per_node_profile`, roughly 2.2x
        more permissive at the top (90 and 155 hard against 40 and 70), so a
        200-word 3-5 node drew nothing at all.
        """
        story = _chain_story("3-5", run_length=2, extra_words=200)
        report = check_words_per_stop(story)
        assert report.findings, "a 200-word 3-5 stop must be reported"
        assert all(f.rule_id == "CG-3" for f in report.findings)

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

    def test_opening_sentence_starting_with_an_abbreviation_is_not_misread(
        self,
    ) -> None:
        """UW-C260/AL-390: a node opening "Mr. Fez's..." must not have its
        opening sentence read as the bare string "Mr.". The old code
        borrowed `diversity.normalize.split_sentences` (documented there as
        "crude, not linguistic sentences") for this extraction; that split
        on any "." followed by whitespace, so the real opening sentence
        never reached the content-word comparison and CG-4 fired
        unfixably. `utils.sentences.split_sentences` reads the whole first
        sentence instead, so the shared word "toys" is found and CG-4 stays
        silent.
        """
        nodes: list[dict[str, object]] = [
            {
                "id": "n0",
                "body": "Pick a path.",
                "is_ending": False,
                "choices": [
                    {
                        "id": "c0",
                        "label": "Look at the broken toys.",
                        "target": "n_toys",
                    },
                    {"id": "c1", "label": "Enter the cave.", "target": "n_cave"},
                ],
            },
            {
                "id": "n_toys",
                "body": (
                    "Mr. Fez's table was a tiny hospital for toys. "
                    "Wind-up beetles lay on their backs."
                ),
                "is_ending": True,
                "choices": [],
                "ending": {
                    "id": "e_toys",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Toy Mender",
                },
            },
            _ending_node("n_cave", "e_cave", body="You enter the cave, cool and dark."),
        ]
        story = _story("8-11", nodes, "n0", ending_count=2)
        report = check_fill_gate_acknowledgment(story)
        assert [f for f in report.findings if f.node_id == "n_toys"] == []

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


class TestRunGateForwardsTheFlag:
    """The gate wiring itself, which no test previously exercised.

    Every assertion above calls ``check_choice_grammar`` directly, so the
    forwarding through ``run_gate`` (the only path any production caller
    takes) was unproven in both directions. Since ``run_gate`` defaults the
    flag ``False`` and nothing in ``src/`` or ``scripts/`` passes ``True``,
    these rules emit no finding on any real story today; see the module
    docstring's flip condition and ``UW-C24``. That is a deliberate
    grandfathering state, not a reason to leave the wiring untested.
    """

    def _raw(self) -> dict[str, object]:
        """A committed fixture that CLEARS Layer 1, not a synthetic chain.

        ``run_gate`` returns early when Layer 1 fails, before the grammar
        checks run at all. The synthetic ``_chain_story`` fixtures used above
        trip L1-7's branch-depth budget, so a gate-level test built on one
        would assert "no CG findings" against a code path that never reached
        the grammar stage: green for the wrong reason, in both directions.
        This fixture passes the gate cleanly and trips CG-2 and CG-4.
        """
        path = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "storybook"
            / "valid"
            / "03_tier2_lantern.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def test_fixture_reaches_the_grammar_stage(self) -> None:
        """Guards the guard: the two tests below are only meaningful while
        this fixture clears Layer 1 and the policy layer."""
        assert run_gate(self._raw()).blocked is False

    def test_default_emits_no_cg_finding_through_the_gate(self) -> None:
        result = run_gate(self._raw())
        assert [f for f in result.report.findings if f.rule_id.startswith("CG-")] == []

    def test_opt_in_emits_cg_findings_through_the_gate(self) -> None:
        result = run_gate(self._raw(), enforce_grammar=True)
        assert {
            f.rule_id for f in result.report.findings if f.rule_id.startswith("CG-")
        }
        assert all(
            f.severity is Severity.WARNING
            for f in result.report.findings
            if f.rule_id.startswith("CG-")
        )

    def test_cg_findings_never_block_the_gate(self) -> None:
        """Advisory means advisory: opting in must not change blocked-ness."""
        raw = self._raw()
        assert run_gate(raw, enforce_grammar=True).blocked is False
        assert run_gate(raw, enforce_grammar=True).report.ok is True


# ---------------------------------------------------------------------------
# Exact cap and ceiling boundaries for CG-1 and CG-3.
#
# Added against the 2026-08-15 mutation run, which left 16 surviving mutants in
# `check_choiceless_run_cap` and 13 in `check_words_per_stop` even though both
# rules already had firing and non-firing tests. That is the signature of a
# boundary asserted loosely: a run of 10 against a cap of 6 fires for the same
# reason a run of 7 does, and neither distinguishes `<=` from `<`. Every case
# below pins the last quiet value against the first noisy one, per band, so the
# comparison operator and the table entry are both load-bearing.
# ---------------------------------------------------------------------------

# (band, cap) straight from ADR-011 section 10, restated here on purpose: a
# test that imports the module's own table cannot detect that table changing.
_RUN_CAP_BY_BAND: tuple[tuple[str, int], ...] = (
    ("3-5", 3),
    ("5-8", 3),  # raised from 2 on 2026-08-17 alongside the CG-1 share allowance
    ("8-11", 6),
    ("10-13", 6),
    ("13-16", 6),
    ("16+", 6),
)

# (band, ceiling) for the flowed bands only; the discrete bands have no
# composed stop and so no entry.
_WORDS_CEILING_BY_BAND: tuple[tuple[str, int], ...] = (
    ("8-11", 135),
    ("10-13", 150),
    ("13-16", 200),
    ("16+", 230),
)


class TestChoicelessRunCapBoundary:
    """CG-1 fires on the first run longer than the band's cap, never at it."""

    @pytest.mark.parametrize(("band", "cap"), _RUN_CAP_BY_BAND)
    def test_a_run_exactly_at_the_cap_is_quiet(self, band: str, cap: int) -> None:
        report = check_choiceless_run_cap(_chain_story(band, cap))
        assert [f.rule_id for f in report.findings] == []

    @pytest.mark.parametrize(("band", "cap"), _RUN_CAP_BY_BAND)
    def test_a_run_one_past_the_cap_fires_once(self, band: str, cap: int) -> None:
        report = check_choiceless_run_cap(_chain_story(band, cap + 1))
        findings = [f for f in report.findings if f.rule_id == "CG-1"]
        assert len(findings) == 1
        # The reported length is the run's own, not the cap: a message that
        # echoed the cap back would read plausibly and say nothing.
        assert f"run of {cap + 1} " in findings[0].message
        assert f"(cap {cap})" in findings[0].message

    @pytest.mark.parametrize(("band", "cap"), _RUN_CAP_BY_BAND)
    def test_the_finding_is_advisory_only(self, band: str, cap: int) -> None:
        # Severity is the whole contract of these rules: a CG-* finding must
        # never fail the gate, whatever its band.
        report = check_choiceless_run_cap(_chain_story(band, cap + 1))
        assert all(f.severity is Severity.WARNING for f in report.findings)
        assert report.ok


class TestWordsPerStopBoundary:
    """CG-3 fires on the first composed stop above the band's ceiling."""

    @staticmethod
    def _stop_words(story: Storybook) -> int:
        # The composed stop is every run node PLUS its terminal, which is the
        # part a per-node word check would miss.
        return sum(len(node.body.split()) for node in story.nodes)

    @pytest.mark.parametrize(("band", "ceiling"), _WORDS_CEILING_BY_BAND)
    def test_a_stop_exactly_at_the_ceiling_is_quiet(
        self, band: str, ceiling: int
    ) -> None:
        # A ONE-node run plus its ending terminal, so each filler word moves
        # the composed total by exactly one. A two-node run steps by two and
        # can stride straight over an odd ceiling without ever landing on it.
        for extra in range(ceiling + 40):
            story = _chain_story(band, 1, extra_words=extra)
            if self._stop_words(story) == ceiling:
                break
        else:  # pragma: no cover - the loop always finds an exact hit
            pytest.fail(f"could not size a stop to exactly {ceiling} words")
        assert self._stop_words(story) == ceiling
        assert list(check_words_per_stop(story).findings) == []

    @pytest.mark.parametrize(("band", "ceiling"), _WORDS_CEILING_BY_BAND)
    def test_a_stop_above_the_ceiling_fires(self, band: str, ceiling: int) -> None:
        for extra in range(ceiling + 40):
            story = _chain_story(band, 1, extra_words=extra)
            if self._stop_words(story) > ceiling:
                break
        else:  # pragma: no cover - the loop always exceeds the ceiling
            pytest.fail(f"could not size a stop above {ceiling} words")
        findings = [
            f for f in check_words_per_stop(story).findings if f.rule_id == "CG-3"
        ]
        assert len(findings) == 1
        assert f"ceiling {ceiling}" in findings[0].message
        assert findings[0].severity is Severity.WARNING

    @pytest.mark.parametrize("band", ["3-5", "5-8"])
    def test_a_discrete_band_is_capped_per_node(self, band: str) -> None:
        # These bands now carry ADR-011 section 10's own ceilings (40 at 3-5, 70
        # at 5-8). A node is a rendered stop there, so a wordy chain is reported
        # per node rather than ignored for having no composed stop (`UW-C276`).
        story = _chain_story(band, 4, extra_words=300)
        assert check_words_per_stop(story).findings


# ---------------------------------------------------------------------------
# CG-3: what counts as one stop depends on whether the band flows
# ---------------------------------------------------------------------------


class TestWordsPerStopRespectsTheRenderedPage:
    """CG-3 must measure the page the reader actually meets.

    ADR-026 decision 4 renders one node per page at 3-5 and 5-8, and composes a
    single-choice run into one scrolling stop only at the flowed bands. Adding
    the two young bands to the ceiling table on 2026-08-18 gave them the flowed
    composition by accident, which summed pages a child never sees together and
    knocked seven strict-clean skeletons out of the catalog, two of them authored
    to the strict bar. These tests pin the distinction rather than the symptom.
    """

    def test_a_young_band_measures_each_node_on_its_own(self) -> None:
        """Two 30-word pages at 3-5 are two stops, not one 60-word stop.

        The 3-5 ceiling is 40. Composed the pair reads 60 and fires; rendered as
        the child meets them, each is comfortably inside.
        """
        story = _chain_story("3-5", run_length=2, extra_words=27)
        report = check_words_per_stop(story)
        assert [f.message for f in report.findings if f.rule_id == "CG-3"] == []

    def test_a_young_band_still_catches_a_single_over_long_page(self) -> None:
        """Per-node measurement is not a licence to write a 100-word page at 3-5."""
        story = _chain_story("3-5", run_length=2, extra_words=100)
        cg3 = [f for f in check_words_per_stop(story).findings if f.rule_id == "CG-3"]
        assert cg3
        assert all("on its own" in f.message for f in cg3)

    def test_a_flowed_band_still_composes_the_run(self) -> None:
        """8-11 flows, so the same shape is one stop and the sum is the quantity.

        The 8-11 ceiling is 135. Three 60-word nodes are each fine alone and
        must still fire once composed, which is the behaviour the young-band fix
        must not disturb.
        """
        story = _chain_story("8-11", run_length=3, extra_words=57)
        cg3 = [f for f in check_words_per_stop(story).findings if f.rule_id == "CG-3"]
        assert cg3
        assert any("composed stop" in f.message for f in cg3)


# ---------------------------------------------------------------------------
# CG-5: the corridor the reader walks, not the one the graph declares
# ---------------------------------------------------------------------------


class TestVisibleRunCap:
    """CG-5 measures the run a reader meets, which CG-1 structurally cannot.

    CG-1 counts `len(node.choices)`, so a node declaring four options is a
    decision to it even when every reader standing there sees one. Two committed
    books walk a reader past CG-1's own cap while CG-1 reports them compliant;
    the worst is a ten-stop corridor CG-1 scores as three (`UW-C297`).
    """

    @staticmethod
    def _gated_corridor(band: str, length: int) -> Storybook:
        """A chain of `length` nodes, each declaring two choices, one gated off.

        Every node offers "press on" plus a second option conditioned on a flag
        the story never sets, so a reader sees exactly one option at each. CG-1
        sees a graph of two-choice decisions and no run at all.
        """
        nodes: list[dict[str, object]] = []
        for i in range(length):
            target = f"n{i + 1}" if i + 1 < length else "n_end"
            nodes.append(
                {
                    "id": f"n{i}",
                    "body": "A beat.",
                    "is_ending": False,
                    "choices": [
                        {"id": f"c{i}a", "label": "Press on.", "target": target},
                        {
                            "id": f"c{i}b",
                            "label": "Use the key.",
                            "target": "n_end",
                            "condition": {"var": "has_key"},
                        },
                    ],
                }
            )
        nodes.append(
            {
                "id": "n_end",
                "body": "Done.",
                "is_ending": True,
                "choices": [],
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Done",
                },
            }
        )
        return _stateful_story(band, nodes, "n0")

    def _cg5(self, story: Storybook) -> list[str]:
        return [
            f.message
            for f in check_visible_run_cap(story).findings
            if f.rule_id == "CG-5"
        ]

    def test_a_conditioned_corridor_past_the_cap_fires(self) -> None:
        """Ten two-choice nodes, one option each: CG-1 sees no run, CG-5 sees ten."""
        story = self._gated_corridor("16+", 10)
        assert check_choiceless_run_cap(story).findings == [], (
            "CG-1 must see nothing here; if it does, this test no longer covers "
            "the gap CG-5 exists for"
        )
        findings = self._cg5(story)
        assert len(findings) == 1
        assert "10 consecutive stops" in findings[0]
        assert "run cap 6" in findings[0]

    def test_a_conditioned_corridor_inside_the_cap_is_silent(self) -> None:
        """The rule is a cap, not a report of every conditioned corridor."""
        assert self._cg5(self._gated_corridor("16+", 4)) == []

    def test_a_story_with_no_conditions_is_never_walked(self) -> None:
        """An unconditioned story's visible graph IS its declared graph.

        Paying for a configuration walk to learn that is waste, and CG-1 already
        covers the declared reading.
        """
        story = _chain_story("16+", run_length=10)
        assert self._cg5(story) == []

    def test_a_cycle_reports_only_that_cycle_not_every_one_option_stop(self) -> None:
        """A loop anywhere must not inflate the corridor with unrelated stops.

        `_topological_order` returns None for a cycle ANYWHERE in the induced
        one-option subgraph, and the cycle branch used to answer with the whole
        vertex set. So a 2-vertex loop made CG-5 report a corridor as long as
        every one-option configuration in the story, listing stops no reader
        walks consecutively. The rule over-reported rather than missing a
        defect, but an inflated finding naming unrelated stops is close to
        unactionable (`UW-C307`, found in review of the CG-5 PR).

        Asserted through `_longest_visible_run`, the function that had the
        defect, on a hand-built `ConfigDag`. Calling `_largest_cycle` directly
        would pass against the pre-fix code too, since the bug was which helper
        the caller reached for: the first version of this test did exactly that
        and proved nothing.

        The graph: a 2-cycle `c0 <-> c1`, three unrelated one-option
        configurations `c2 -> c3`, `c4`, and a two-option `c5` that must be
        excluded from the induced subgraph entirely.
        """
        dag = ConfigDag(
            adjacency={
                "c0": ["c1"],
                "c1": ["c0"],
                "c2": ["c3"],
                "c3": [],
                "c4": [],
                "c5": ["c0", "c2"],
            },
            start="c5",
            node_of={f"c{i}": f"n{i}" for i in range(6)},
            choice_count={"c0": 1, "c1": 1, "c2": 1, "c3": 1, "c4": 1, "c5": 2},
        )

        assert choice_grammar._longest_visible_run(dag) == ["c0", "c1"]  # pyright: ignore[reportPrivateUsage]

    def test_a_self_looping_configuration_counts_as_a_cycle(self) -> None:
        """A single vertex is a cycle only when it carries a self-edge.

        `loop_and_grow` can route a choice back to its own node in the same
        variable state, which is a one-vertex strongly connected component that
        IS an unbounded corridor. Sizing components alone would discard it and
        fall through to the whole-vertex-set fallback, restoring the very
        over-report this fix removes.
        """
        dag = ConfigDag(
            adjacency={"c0": ["c0"], "c1": [], "c2": []},
            start="c0",
            node_of={f"c{i}": f"n{i}" for i in range(3)},
            choice_count={"c0": 1, "c1": 1, "c2": 1},
        )

        assert choice_grammar._longest_visible_run(dag) == ["c0"]  # pyright: ignore[reportPrivateUsage]

    def test_a_declared_run_already_over_the_cap_is_left_to_cg1(self) -> None:
        """No duplicate finding: what CG-5 adds is the excess CG-1 cannot see.

        Here the corridor is declared as single-choice nodes, so CG-1 reports it.
        CG-5 defers whenever CG-1 already fires, because the author already has
        the signal and a second finding under a second rule id is noise.
        """
        nodes: list[dict[str, object]] = [
            {
                "id": f"n{i}",
                "body": "A beat.",
                "is_ending": False,
                "choices": [
                    {
                        "id": f"c{i}",
                        "label": "On.",
                        "target": f"n{i + 1}" if i < 9 else "n_end",
                    }
                ],
            }
            for i in range(10)
        ]
        nodes.append(
            {
                "id": "n_end",
                "body": "Done.",
                "is_ending": True,
                "choices": [],
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Done",
                },
            }
        )
        # One conditioned choice elsewhere, so the walk is entered at all.
        nodes[0]["choices"] = [
            *nodes[0]["choices"],  # type: ignore[misc]
            {
                "id": "c_alt",
                "label": "Shortcut.",
                "target": "n_end",
                "condition": {"var": "has_key"},
            },
        ]
        story = _stateful_story("16+", nodes, "n0")
        assert check_choiceless_run_cap(story).findings, "CG-1 must own this one"
        assert self._cg5(story) == []


class TestVisibleRunCycleMeasurement:
    """`_longest_visible_run` must not lose a corridor to an unrelated loop."""

    def test_a_loop_does_not_hide_a_longer_corridor_elsewhere(self) -> None:
        """A cycle anywhere must not suppress the acyclic run measurement.

        `_topological_order` returns None for a cycle ANYWHERE in the induced
        one-option subgraph, and the first fix for `UW-C307` answered that branch
        with the largest cycle alone. That corrected the original over-report but
        introduced an under-report: a 2-vertex loop beside a ten-stop corridor
        answered 2, which is under every band cap, so CG-5 emitted nothing at all
        for the corridor the rule exists to catch.

        Measured over the SCC condensation, the cycle contributes its own size
        and the longer chain wins on its length.
        """
        adjacency: dict[str, list[str]] = {"c0": ["c1"], "c1": ["c0"]}
        for index in range(2, 12):
            adjacency[f"c{index:02d}"] = [f"c{index + 1:02d}"] if index < 11 else []
        adjacency["c99"] = ["c0", "c02"]
        choice_count = dict.fromkeys(adjacency, 1)
        choice_count["c99"] = 2

        dag = ConfigDag(
            adjacency=adjacency,
            start="c99",
            node_of={vertex: f"n{vertex}" for vertex in adjacency},
            choice_count=choice_count,
        )

        run = choice_grammar._longest_visible_run(dag)  # pyright: ignore[reportPrivateUsage]

        assert run is not None
        assert len(run) == 10, f"the ten-stop corridor must win, got {run}"
        assert "c0" not in run
        assert "c1" not in run

    def test_the_reported_run_is_stable_across_hash_seeds(self) -> None:
        """Two equal-size cycles must not swap places run to run.

        `strongly_connected_components` yields `set` objects in hash order, so
        breaking an equal-size tie with a bare `max` made CG-5's `node_id` and
        message vary with `PYTHONHASHSEED`. The head tie-break is lexical on the
        component's smallest member, which is derived from the story's own
        discovery order rather than from a node id.
        """
        dag = ConfigDag(
            adjacency={
                "c0": ["c1"],
                "c1": ["c0"],
                "c2": ["c3"],
                "c3": ["c2"],
                "c9": ["c0", "c2"],
            },
            start="c9",
            node_of={f"c{i}": f"n{i}" for i in (0, 1, 2, 3, 9)},
            choice_count={"c0": 1, "c1": 1, "c2": 1, "c3": 1, "c9": 2},
        )

        runs = {
            tuple(choice_grammar._longest_visible_run(dag) or ())  # pyright: ignore[reportPrivateUsage]
            for _ in range(8)
        }

        assert runs == {("c0", "c1")}, f"unstable across repeats: {runs}"
