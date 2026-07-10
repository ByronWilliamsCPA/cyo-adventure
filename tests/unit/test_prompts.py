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

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.generation.concept import (
    AnchorContext,
    ConceptBrief,
    Protagonist,
    StructurePattern,
)
from cyo_adventure.generation.prompts import (
    _USER_MARKER,
    StagePrompt,
    _budget_block,
    _scale_cell_block,
    _split_stage_prompt,
    build_fidelity_repair_prompt,
    build_fill_prompt,
    build_prose_prompt,
    build_repair_prompt,
    build_structure_prompt,
)
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle
from cyo_adventure.validator.band_profile import (
    min_complete_floor,
    production_cell_budget,
    words_per_node_profile,
)
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
            "schema_version": "2.0",
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

    def test_budget_block_compact_scale_matches_compact_budget(
        self, minimal_brief: ConceptBrief
    ) -> None:
        """With scale='compact' the user block states the compact L1-7 limits.

        Proves the prompt side honours the scale and stays bound to band_budget,
        so the promised budget matches what the gate enforces under compact.
        """
        result = build_structure_prompt(minimal_brief, "compact")
        budget = band_budget(minimal_brief.age_band, "compact")
        assert budget is not None
        min_nodes, max_nodes, max_depth = budget
        assert f"between {min_nodes} and {max_nodes} nodes" in result.user
        assert f"at most {max_depth} choices deep" in result.user
        # The compact budget differs from the standard one (smaller).
        assert band_budget(minimal_brief.age_band, "compact") != band_budget(
            minimal_brief.age_band
        )

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

    def test_length_less_brief_omits_scale_cell_block(
        self, minimal_brief: ConceptBrief
    ) -> None:
        """A brief with no length renders no scale-cell lines (backward compatible)."""
        result = build_structure_prompt(minimal_brief)
        assert "Story scale:" not in result.user
        assert "Words per node:" not in result.user
        assert "Earned ending:" not in result.user

    def test_length_declared_brief_uses_cell_budget(self) -> None:
        """A length-declared brief promises the ADR-011 cell budget, not the band."""
        brief = ConceptBrief(
            premise="A layered mystery through a flooded city.",
            protagonist=Protagonist(name="Isla", age=12, role="diver"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=5.0,
            tier=1,
            tone="mysterious",
            target_node_count=120,
            ending_count=6,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
            length=Length.MEDIUM,
        )
        result = build_structure_prompt(brief)
        cell = production_cell_budget("8-11", "medium", "prose")
        assert cell is not None
        min_nodes, max_nodes, _max_depth = cell
        # The cell ceiling is far above the band ceiling; the prompt states it.
        assert f"between {min_nodes} and {max_nodes} nodes" in result.user
        band = band_budget("8-11")
        assert band is not None
        assert band[1] != max_nodes  # the cell genuinely lifts the band ceiling

    def test_length_declared_brief_states_words_and_arc_floor(self) -> None:
        """A scale-classified brief promises PL-19 words and the PL-20 arc floor."""
        brief = ConceptBrief(
            premise="A layered mystery through a flooded city.",
            protagonist=Protagonist(name="Isla", age=12, role="diver"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=5.0,
            tier=1,
            tone="mysterious",
            target_node_count=120,
            ending_count=6,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
            length=Length.MEDIUM,
            narrative_style=NarrativeStyle.PROSE,
        )
        result = build_structure_prompt(brief)
        words = words_per_node_profile("8-11", "prose")
        assert words is not None
        mean, _lo, _hi, per_node_max = words
        assert f"story-mean of about {mean} words" in result.user
        assert f"at or under {per_node_max} words" in result.user
        floor = min_complete_floor("8-11", "medium", "prose")
        assert floor is not None
        assert f"at least {floor} nodes long" in result.user

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


def test_structure_prompt_carries_anchor_variable_names(
    minimal_brief: ConceptBrief,
) -> None:
    """The brief's anchor variable names ride into the user block wholesale."""
    brief = minimal_brief.model_copy(
        update={
            "anchor_context": AnchorContext(
                title="Book One", variable_names=["courage"]
            )
        }
    )
    stage = build_structure_prompt(brief)
    assert '"variable_names"' in stage.user
    assert '"courage"' in stage.user


def test_structure_prompt_instructs_anchor_variable_reuse(
    minimal_brief: ConceptBrief,
) -> None:
    """The static task framing tells the model what to do with variable_names."""
    stage = build_structure_prompt(minimal_brief)
    assert "variable_names" in stage.system
    assert "same name" in stage.system


def test_structure_prompt_instructs_valid_ending_shape(
    minimal_brief: ConceptBrief,
) -> None:
    """The ending instruction matches the enforced Ending model (kind + valence).

    Regression pin for the stale `ending.type` instruction: the schema has no
    `type` field, and the old vocabulary (failure/bittersweet/open) is not in
    EndingKind. See storybook/models.py:408-416, 89-105.
    """
    stage = build_structure_prompt(minimal_brief)
    assert "`kind`" in stage.system
    assert "`valence`" in stage.system
    assert "bittersweet" not in stage.system


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
# build_fill_prompt
# ---------------------------------------------------------------------------


class TestBuildFillPrompt:
    """Tests for build_fill_prompt."""

    def test_build_fill_prompt_splits_system_and_user(self) -> None:
        """The fill prompt has a stable system block and a volatile user block."""
        prompt = build_fill_prompt('{"id": "s_x", "nodes": []}', '{"premise": "a fox"}')
        assert "<!-- @user -->" not in prompt.system
        assert "<!-- @user -->" not in prompt.user
        assert prompt.system
        assert prompt.user

    def test_build_fill_prompt_embeds_skeleton_and_theme_brief(self) -> None:
        """Both the skeleton JSON and the theme brief reach the user block."""
        prompt = build_fill_prompt(
            '{"id": "s_cave", "nodes": []}', '{"premise": "a curious otter"}'
        )
        assert '"id": "s_cave"' in prompt.user
        assert '"premise": "a curious otter"' in prompt.user

    def test_build_fill_prompt_no_unfilled_placeholders(self) -> None:
        """No owned slot token remains unfilled.

        The drafting guide documents ``{drafting_guide}`` as literal text, so
        that token legitimately appears in the system block after substitution.
        We assert absence only for the tokens the guide does not self-reference.
        """
        prompt = build_fill_prompt("{}", "{}")
        for token in ("{skeleton_with_fill_directives}", "{theme_brief}"):
            assert token not in prompt.combined


# ---------------------------------------------------------------------------
# build_fidelity_repair_prompt
# ---------------------------------------------------------------------------


class TestBuildFidelityRepairPrompt:
    """Tests for build_fidelity_repair_prompt (Stage 1 fidelity-aware repair)."""

    def test_returns_stage_prompt_split(self) -> None:
        """The builder returns a StagePrompt with distinct system/user blocks."""
        prompt = build_fidelity_repair_prompt(
            '{"id": "s_x", "nodes": []}',
            ["node 'n1' word count 3 outside [6, 14] for target 10"],
        )
        assert isinstance(prompt, StagePrompt)
        assert "<!-- @user -->" not in prompt.system
        assert "<!-- @user -->" not in prompt.user
        assert prompt.system
        assert prompt.user

    def test_carries_violation_text_verbatim(self) -> None:
        """The fidelity violation strings reach the user block, not a blind redo."""
        violations = [
            "node 'n1' word count 3 outside [6, 14] for target 10",
            "filled document still contains unfilled FILL directives",
        ]
        prompt = build_fidelity_repair_prompt('{"id": "s_x", "nodes": []}', violations)
        for violation in violations:
            assert violation in prompt.user

    def test_embeds_filled_story_json(self) -> None:
        """The story being corrected lands verbatim in the user block."""
        prompt = build_fidelity_repair_prompt(
            '{"id": "s_cave", "nodes": []}', ["some violation"]
        )
        assert '"id": "s_cave"' in prompt.user

    def test_no_unfilled_placeholders(self) -> None:
        """No owned slot token remains unfilled after substitution."""
        prompt = build_fidelity_repair_prompt("{}", ["v"])
        for token in ("{filled_story}", "{fidelity_violations}"):
            assert token not in prompt.combined


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


# ---------------------------------------------------------------------------
# _split_stage_prompt marker-count error path
# ---------------------------------------------------------------------------


class TestSplitStagePromptMarkerErrors:
    """A malformed template (zero or 2+ markers) raises BusinessLogicError.

    This is a template-authoring correctness check: real bundled templates
    always carry exactly one marker (see TestRuntimeLoading above), so this
    path is only reachable via a malformed template file. Testing the private
    ``_split_stage_prompt`` directly is the pragmatic approach: no public
    caller can pass malformed marker text since templates are fixed bundled
    resources.
    """

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("system only, no marker at all", id="zero_markers"),
            pytest.param(
                f"system{_USER_MARKER}middle{_USER_MARKER}user", id="two_markers"
            ),
        ],
    )
    def test_wrong_marker_count_raises_business_logic_error(self, text: str) -> None:
        """Zero or two-plus markers both raise BusinessLogicError."""
        with pytest.raises(BusinessLogicError, match="must contain exactly one"):
            _split_stage_prompt(text)

    def test_wrong_marker_count_sets_rule_attribute(self) -> None:
        """The raised error carries rule='stage_prompt_marker' for callers to match."""
        with pytest.raises(BusinessLogicError) as exc_info:
            _split_stage_prompt("no marker here")
        assert exc_info.value.details["rule"] == "stage_prompt_marker"


# ---------------------------------------------------------------------------
# _budget_block defensive None-budget path (unreachable via real data)
# ---------------------------------------------------------------------------


class TestBudgetBlockMissingBudget:
    """A ``None`` budget from resolve_node_budget raises BusinessLogicError.

    The source comment above ``_budget_block`` states this branch is
    defensive-only and unreachable via any valid ConceptBrief, because every
    real AgeBand has a budget at every scale. Monkeypatching
    resolve_node_budget (as imported into prompts.py) to return None is the
    only way to exercise it.
    """

    def test_none_budget_raises_business_logic_error(
        self, minimal_brief: ConceptBrief, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A None budget from resolve_node_budget raises with rule='band_budget_missing'."""
        monkeypatch.setattr(
            "cyo_adventure.generation.prompts.resolve_node_budget",
            lambda *args, **kwargs: None,
        )
        with pytest.raises(BusinessLogicError, match="no L1-7 budget"):
            _budget_block(minimal_brief)

    def test_none_budget_sets_rule_attribute(
        self, minimal_brief: ConceptBrief, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The raised error carries rule='band_budget_missing'."""
        monkeypatch.setattr(
            "cyo_adventure.generation.prompts.resolve_node_budget",
            lambda *args, **kwargs: None,
        )
        with pytest.raises(BusinessLogicError) as exc_info:
            _budget_block(minimal_brief)
        assert exc_info.value.details["rule"] == "band_budget_missing"


# ---------------------------------------------------------------------------
# _scale_cell_block branch coverage: words_per_node None (monkeypatched,
# unreachable via real data) and min_complete_floor None (real off-matrix cell)
# ---------------------------------------------------------------------------


class TestScaleCellBlockBranches:
    """Cover both independent None branches inside _scale_cell_block."""

    def test_words_per_node_none_omits_words_per_node_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A None from words_per_node_profile omits the 'Words per node' line.

        words_per_node_profile always falls back to a band's prose entry for
        any real AgeBand, so this branch is genuinely unreachable via real
        data; monkeypatching it to return None is the only way to cover it.
        """
        brief = ConceptBrief(
            premise="A layered mystery through a flooded city.",
            protagonist=Protagonist(name="Isla", age=12, role="diver"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=5.0,
            tier=1,
            tone="mysterious",
            target_node_count=120,
            ending_count=6,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
            length=Length.MEDIUM,
        )
        monkeypatch.setattr(
            "cyo_adventure.generation.prompts.words_per_node_profile",
            lambda *args, **kwargs: None,
        )
        result = _scale_cell_block(brief)
        assert "Words per node" not in result

    def test_off_matrix_cell_omits_earned_ending_but_keeps_words_per_node(
        self,
    ) -> None:
        """An off-matrix (band, length, style) combo has no arc floor, real data.

        (3-5, long, prose) is not a key in band_profile._MIN_COMPLETE (3-5
        only offers short/medium), so min_complete_floor genuinely returns
        None for a real ConceptBrief; Pydantic does not cross-validate
        band/length/style, so this combination is constructible without any
        monkeypatching. words_per_node_profile("3-5", "prose") IS defined, so
        that line is independently present.
        """
        brief = ConceptBrief(
            premise="A tiny adventure that runs long for its band.",
            protagonist=Protagonist(name="Miko", age=4, role="explorer"),
            age_band=AgeBand.BAND_3_5,
            reading_level_target=1.0,
            tier=1,
            tone="gentle",
            target_node_count=15,
            ending_count=2,
            structure_pattern=StructurePattern.GAUNTLET,
            length=Length.LONG,
            narrative_style=NarrativeStyle.PROSE,
        )
        assert min_complete_floor("3-5", "long", "prose") is None
        assert words_per_node_profile("3-5", "prose") is not None
        result = _scale_cell_block(brief)
        assert "Earned ending" not in result
        assert "Words per node" in result
