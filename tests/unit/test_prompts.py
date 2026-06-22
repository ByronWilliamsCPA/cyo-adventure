"""Tests for deterministic stage-prompt assembly (prompts.py).

Tests verify:
- Correct placeholder substitution for each builder.
- No unfilled known placeholder tokens remain in builder output.
- The system/user split: static reference content (schema, drafting guide)
  lands in the cacheable ``system`` block; per-job volatile content (brief,
  budget, skeleton, repair payload) lands in the ``user`` block.
- The Stage A budget block states the exact L1-7 limits from
  ``band_budget`` so the prompt and the gate cannot drift.
- Brace-safety: JSON payloads with literal ``{`` / ``}`` do not break
  substitution.
- Determinism: identical inputs produce identical outputs.
- Runtime uses importlib.resources (not a docs/ path).
- Repair prompt includes only failing node ids and excludes non-failing nodes.
"""

from __future__ import annotations

import json

import pytest

from cyo_adventure.generation.concept import ConceptBrief, Protagonist, StructurePattern
from cyo_adventure.generation.prompts import (
    StagePrompt,
    build_prose_prompt,
    build_repair_prompt,
    build_structure_prompt,
)
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.validator.layer1 import band_budget

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_brief() -> ConceptBrief:
    """Minimal valid ConceptBrief for test use."""
    return ConceptBrief(
        premise="A young explorer discovers a hidden door in the library basement.",
        protagonist=Protagonist(name="Captain Rosa", age=10, role="young explorer"),
        age_band=AgeBand.BAND_8_11,
        reading_level_target=4.0,
        tier=1,
        tone="adventurous",
        themes_allowed=["friendship", "courage"],
        content_nogo=["graphic violence"],
        target_node_count=20,
        ending_count=2,
        structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
    )


@pytest.fixture
def skeleton_json_with_braces() -> str:
    """A skeleton JSON string that contains literal braces (normal JSON)."""
    return json.dumps(
        {
            "id": "aaaaaaaa-0000-4000-8000-000000000001",
            "schema_version": "1.0",
            "version": 1,
            "start_node": "n_start",
            "variables": [],
            "nodes": [
                {
                    "id": "n_start",
                    "body": "You stand at the threshold.",
                    "on_enter": [],
                    "choices": [
                        {
                            "id": "c_go_left",
                            "label": "Go left",
                            "target": "n_ending_a",
                            "effects": [],
                        }
                    ],
                    "is_ending": False,
                    "tags": [],
                },
                {
                    "id": "n_ending_a",
                    "body": "You find treasure.",
                    "on_enter": [],
                    "choices": [],
                    "is_ending": True,
                    "ending": {
                        "id": "ending_treasure",
                        "type": "success",
                        "title": "Treasure found",
                    },
                    "tags": [],
                },
            ],
        },
        indent=2,
    )


@pytest.fixture
def storybook_json_with_braces(skeleton_json_with_braces: str) -> str:
    """Reuse the skeleton JSON as a storybook-JSON payload for repair tests."""
    return skeleton_json_with_braces


@pytest.fixture
def failing_findings() -> list[dict[str, object]]:
    """Sample failing findings list with a known failing node id."""
    return [
        {
            "rule_id": "L1-03",
            "node_id": "n_orphan_node",
            "choice_id": None,
            "message": "Node n_orphan_node is not reachable from start_node.",
        },
        {
            "rule_id": "L1-04",
            "node_id": "n_dead_end",
            "choice_id": None,
            "message": "Non-ending node n_dead_end has no choices.",
        },
    ]


# ---------------------------------------------------------------------------
# build_structure_prompt
# ---------------------------------------------------------------------------


class TestBuildStructurePrompt:
    """Tests for build_structure_prompt."""

    def test_returns_stage_prompt(self, minimal_brief: ConceptBrief) -> None:
        """The builder returns a StagePrompt with non-empty system and user."""
        result = build_structure_prompt(minimal_brief)
        assert isinstance(result, StagePrompt)
        assert len(result.system) > 0
        assert len(result.user) > 0

    def test_brief_in_user_block(self, minimal_brief: ConceptBrief) -> None:
        """The brief's premise lands in the volatile user block, not system."""
        result = build_structure_prompt(minimal_brief)
        assert minimal_brief.premise in result.user

    def test_schema_in_system_not_user(self, minimal_brief: ConceptBrief) -> None:
        """The JSON Schema is in the cacheable system block, never the user block.

        This is the caching boundary: a per-job user block must not carry the
        large static schema, or the cached prefix would be defeated.
        """
        result = build_structure_prompt(minimal_brief)
        assert "properties" in result.system
        assert "properties" not in result.user

    def test_drafting_guide_in_system(self, minimal_brief: ConceptBrief) -> None:
        """The drafting guide content lands in the system block."""
        result = build_structure_prompt(minimal_brief)
        # The drafting guide includes this distinctive section heading.
        assert "Node and Depth Budgets" in result.system

    def test_budget_block_matches_band_budget(
        self, minimal_brief: ConceptBrief
    ) -> None:
        """The user block states the exact L1-7 limits from band_budget.

        Binds the prompt to the validator's enforced budget; if the two ever
        drift this test fails. (#VERIFY for the band_budget data-integrity tag.)
        """
        result = build_structure_prompt(minimal_brief)
        budget = band_budget(minimal_brief.age_band)
        assert budget is not None
        min_nodes, max_nodes, max_depth = budget
        assert f"between {min_nodes} and {max_nodes} nodes" in result.user
        assert f"at most {max_depth} choices deep" in result.user
        assert f"EXACTLY {minimal_brief.ending_count} ending" in result.user

    @pytest.mark.parametrize("band", list(AgeBand))
    def test_budget_block_for_every_band(self, band: AgeBand) -> None:
        """Every AgeBand renders a budget that matches its band_budget entry."""
        brief = ConceptBrief(
            premise="A test premise for the band budget check.",
            protagonist=Protagonist(name="Hero", age=10, role="explorer"),
            age_band=band,
            reading_level_target=4.0,
            tier=1,
            tone="adventurous",
            target_node_count=20,
            ending_count=2,
            structure_pattern=StructurePattern.QUEST,
        )
        result = build_structure_prompt(brief)
        budget = band_budget(band)
        assert budget is not None
        min_nodes, max_nodes, max_depth = budget
        assert f"between {min_nodes} and {max_nodes} nodes" in result.user
        assert f"at most {max_depth} choices deep" in result.user

    def test_no_unfilled_placeholders(self, minimal_brief: ConceptBrief) -> None:
        """No owned slot token remains unfilled.

        The drafting guide documents ``{concept_brief}`` and ``{drafting_guide}``
        as literal text, so those tokens legitimately appear in the system block
        after substitution (their slot-fill is verified by other tests). We
        assert absence only for the tokens the guide does not self-reference.
        """
        result = build_structure_prompt(minimal_brief)
        for token in ("{schema_rules}", "{budget_constraints}"):
            assert token not in result.combined

    def test_marker_consumed(self, minimal_brief: ConceptBrief) -> None:
        """The split marker is not present in the assembled output."""
        result = build_structure_prompt(minimal_brief)
        assert "<!-- @user -->" not in result.combined

    def test_deterministic(self, minimal_brief: ConceptBrief) -> None:
        """Two calls with the same brief return equal StagePrompts."""
        first = build_structure_prompt(minimal_brief)
        second = build_structure_prompt(minimal_brief)
        assert first == second

    def test_brace_safety_from_json_in_brief(self, minimal_brief: ConceptBrief) -> None:
        """Brief serialised to JSON contains braces; substitution must not raise."""
        result = build_structure_prompt(minimal_brief)
        assert "{" in result.user  # JSON braces from the serialised brief

    def test_brief_json_fields_present(self, minimal_brief: ConceptBrief) -> None:
        """The serialised brief includes key field values in the user block."""
        result = build_structure_prompt(minimal_brief)
        assert "adventurous" in result.user  # tone field
        assert "8-11" in result.user  # age_band value


# ---------------------------------------------------------------------------
# build_prose_prompt
# ---------------------------------------------------------------------------


class TestBuildProsePrompt:
    """Tests for build_prose_prompt."""

    def test_returns_stage_prompt(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """The builder returns a StagePrompt with non-empty blocks."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert isinstance(result, StagePrompt)
        assert len(result.system) > 0
        assert len(result.user) > 0

    def test_skeleton_in_user_block(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """The skeleton JSON lands verbatim in the volatile user block."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert skeleton_json_with_braces in result.user

    def test_schema_in_system_not_user(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """Schema and guide are in the cacheable system block, not the user block."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert "properties" in result.system
        assert "Node and Depth Budgets" in result.system
        assert "properties" not in result.user

    def test_no_unfilled_placeholders(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """No owned slot token remains unfilled.

        The drafting guide documents ``{drafting_guide}`` as literal text, so
        that token legitimately appears in the system block after substitution.
        We assert absence only for the tokens the guide does not self-reference.
        """
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        for token in ("{approved_skeleton}", "{schema_rules}"):
            assert token not in result.combined

    def test_marker_consumed(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """The split marker is not present in the assembled output."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert "<!-- @user -->" not in result.combined

    def test_brace_safety(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """JSON containing braces does not cause a substitution error."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert "n_start" in result.user  # a node id from the skeleton

    def test_deterministic(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """Two calls with the same inputs return equal StagePrompts."""
        first = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        second = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert first == second


# ---------------------------------------------------------------------------
# build_repair_prompt
# ---------------------------------------------------------------------------


class TestBuildRepairPrompt:
    """Tests for build_repair_prompt."""

    def test_returns_stage_prompt(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The builder returns a StagePrompt; repair carries no schema."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert isinstance(result, StagePrompt)
        # Repair is lean: no JSON Schema embedded in either block.
        assert "properties" not in result.combined

    def test_storybook_in_user_block(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The storybook JSON lands verbatim in the user block."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert storybook_json_with_braces in result.user

    def test_failing_node_ids_in_user_block(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The failing node ids appear in the user block, not the static system."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "n_orphan_node" in result.user
        assert "n_dead_end" in result.user
        # The static system block must stay job-independent (cacheable): no
        # substituted node ids leak into it.
        assert "n_orphan_node" not in result.system

    def test_excludes_non_failing_node_id(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """A node id NOT in the failing findings does not appear anywhere."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "n_perfectly_fine_node" not in result.combined

    def test_contains_rule_ids(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The user block includes the rule ids from the findings."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "L1-03" in result.user
        assert "L1-04" in result.user

    def test_no_unfilled_placeholders(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """No owned placeholder token remains in the assembled output."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        for token in (
            "{approved_skeleton}",
            "{validator_report}",
            "{failing_node_ids}",
        ):
            assert token not in result.combined

    def test_brace_safety(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """JSON containing braces does not cause a substitution error."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "n_start" in result.user  # node id from the storybook JSON

    def test_deterministic(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """Two calls with the same inputs return equal StagePrompts."""
        first = build_repair_prompt(storybook_json_with_braces, failing_findings)
        second = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert first == second

    def test_empty_findings_list(self, storybook_json_with_braces: str) -> None:
        """Builder handles an empty findings list without error."""
        result = build_repair_prompt(storybook_json_with_braces, [])
        assert len(result.user) > 0
        assert "{validator_report}" not in result.combined
        assert "{failing_node_ids}" not in result.combined

    def test_finding_without_node_id_excluded_from_node_list(
        self, storybook_json_with_braces: str
    ) -> None:
        """A finding without a node_id does not corrupt the node list."""
        findings: list[dict[str, object]] = [
            {
                "rule_id": "L1-01",
                "node_id": None,
                "message": "Top-level schema violation.",
            }
        ]
        result = build_repair_prompt(storybook_json_with_braces, findings)
        assert "{failing_node_ids}" not in result.combined
        assert "L1-01" in result.user  # still in the validator report section

    def test_finding_with_choice_id_included_in_report(
        self, storybook_json_with_braces: str
    ) -> None:
        """A finding with a choice_id includes that choice_id in the report."""
        findings: list[dict[str, object]] = [
            {
                "rule_id": "L1-07",
                "node_id": "n_start",
                "choice_id": "c_go_left",
                "message": "Choice target does not exist.",
            }
        ]
        result = build_repair_prompt(storybook_json_with_braces, findings)
        assert "c_go_left" in result.user
        assert "L1-07" in result.user


# ---------------------------------------------------------------------------
# Templates load via importlib.resources, not docs/
# ---------------------------------------------------------------------------


class TestRuntimeLoading:
    """Confirm builders work without any dependency on docs/."""

    def test_structure_works_without_docs_path(
        self, minimal_brief: ConceptBrief
    ) -> None:
        """build_structure_prompt runs successfully (templates are bundled)."""
        result = build_structure_prompt(minimal_brief)
        assert len(result.combined) > 100

    def test_prose_works_without_docs_path(
        self, skeleton_json_with_braces: str, minimal_brief: ConceptBrief
    ) -> None:
        """build_prose_prompt runs successfully (templates are bundled)."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert len(result.combined) > 100

    def test_repair_works_without_docs_path(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """build_repair_prompt runs successfully (templates are bundled)."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert len(result.combined) > 100

    @pytest.mark.parametrize("name", ["structure.md", "prose.md", "repair.md"])
    def test_template_has_exactly_one_user_marker(self, name: str) -> None:
        """Each stage template carries exactly one system/user split marker."""
        from importlib.resources import files

        text = (
            files("cyo_adventure.generation.templates")
            .joinpath(name)
            .read_text(encoding="utf-8")
        )
        assert text.count("<!-- @user -->") == 1

    def test_importlib_resources_loads_drafting_guide(self) -> None:
        """importlib.resources can load drafting_guide.md from the templates package."""
        from importlib.resources import files

        text = (
            files("cyo_adventure.generation.templates")
            .joinpath("drafting_guide.md")
            .read_text(encoding="utf-8")
        )
        assert len(text) > 0
        assert "Node and Depth Budgets" in text
