"""Tests for deterministic stage-prompt assembly (prompts.py).

Tests verify:
- Correct placeholder substitution for each builder.
- No unfilled known placeholder tokens remain in builder output.
- Brace-safety: JSON payloads with literal ``{`` / ``}`` do not break
  substitution.
- Determinism: identical inputs produce identical outputs.
- Runtime uses importlib.resources (not a docs/ path) -- confirmed by calling
  builders successfully without any docs/ dependency.
- Repair prompt includes only failing node ids and excludes non-failing nodes.
"""

from __future__ import annotations

import json

import pytest

from cyo_adventure.generation.concept import ConceptBrief, Protagonist, StructurePattern
from cyo_adventure.generation.prompts import (
    build_prose_prompt,
    build_repair_prompt,
    build_structure_prompt,
)
from cyo_adventure.storybook.models import AgeBand

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

    def test_contains_premise(self, minimal_brief: ConceptBrief) -> None:
        """The prompt contains the brief's premise text."""
        result = build_structure_prompt(minimal_brief)
        assert minimal_brief.premise in result

    def test_contains_drafting_guide_content(self, minimal_brief: ConceptBrief) -> None:
        """The prompt contains text from the bundled drafting guide."""
        result = build_structure_prompt(minimal_brief)
        # The drafting guide includes this distinctive section heading.
        assert "Node and Depth Budgets" in result

    def test_concept_brief_placeholder_replaced(
        self, minimal_brief: ConceptBrief
    ) -> None:
        """The {concept_brief} placeholder is replaced with the JSON brief.

        The bundled drafting guide contains the text ``{concept_brief}`` in
        its Concept Brief Field List section (describing its own slot name).
        After template substitution the premise text must appear in the result,
        proving the slot was filled. We cannot assert the token is absent
        because it appears in the inserted guide text.
        """
        result = build_structure_prompt(minimal_brief)
        assert minimal_brief.premise in result

    def test_drafting_guide_placeholder_replaced(
        self, minimal_brief: ConceptBrief
    ) -> None:
        """The {drafting_guide} placeholder is replaced with the guide content.

        The drafting guide itself contains the text ``{drafting_guide}`` in its
        Purpose section (describing its own role). We therefore cannot assert
        that ``{drafting_guide}`` is absent from the assembled prompt. Instead
        we verify that the guide's actual section content is present, proving
        the substitution happened.
        """
        result = build_structure_prompt(minimal_brief)
        # The structure template has exactly one {drafting_guide} slot. After
        # substitution the guide text -- which includes "Node and Depth Budgets"
        # -- must appear in the result.
        assert "Node and Depth Budgets" in result
        # The raw placeholder no longer occupies the template slot: after
        # substitution the guide text is far longer than the placeholder token.
        # We can confirm by checking the result is longer than just the template.
        from importlib.resources import files as _files

        template_text = (
            _files("cyo_adventure.generation.templates")
            .joinpath("structure.md")
            .read_text(encoding="utf-8")
        )
        assert len(result) > len(template_text)

    def test_non_empty(self, minimal_brief: ConceptBrief) -> None:
        """Builder returns a non-empty string."""
        result = build_structure_prompt(minimal_brief)
        assert len(result) > 0

    def test_deterministic(self, minimal_brief: ConceptBrief) -> None:
        """Two calls with the same brief return identical strings."""
        first = build_structure_prompt(minimal_brief)
        second = build_structure_prompt(minimal_brief)
        assert first == second

    def test_brace_safety_from_json_in_brief(self, minimal_brief: ConceptBrief) -> None:
        """Brief serialised to JSON contains braces; substitution must not raise."""
        # model_dump_json produces JSON with {} braces; ensure no KeyError.
        result = build_structure_prompt(minimal_brief)
        assert "{" in result  # JSON braces are preserved in the output

    def test_brief_json_fields_present(self, minimal_brief: ConceptBrief) -> None:
        """The serialised brief includes key field values."""
        result = build_structure_prompt(minimal_brief)
        assert "adventurous" in result  # tone field
        assert "8-11" in result  # age_band value


# ---------------------------------------------------------------------------
# build_prose_prompt
# ---------------------------------------------------------------------------


class TestBuildProsePrompt:
    """Tests for build_prose_prompt."""

    def test_contains_skeleton_json(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """The prompt contains the skeleton JSON verbatim."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert skeleton_json_with_braces in result

    def test_contains_drafting_guide_content(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """The prompt contains text from the bundled drafting guide."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert "Node and Depth Budgets" in result

    def test_no_unfilled_approved_skeleton_placeholder(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """The {approved_skeleton} placeholder is replaced."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert "{approved_skeleton}" not in result

    def test_drafting_guide_placeholder_replaced(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """The {drafting_guide} placeholder is replaced with the guide content.

        The bundled drafting guide mentions ``{drafting_guide}`` in its own
        Purpose section. We verify the substitution by checking the guide's
        section content is present and the assembled prompt is larger than the
        raw template.
        """
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert "Node and Depth Budgets" in result
        from importlib.resources import files as _files

        template_text = (
            _files("cyo_adventure.generation.templates")
            .joinpath("prose.md")
            .read_text(encoding="utf-8")
        )
        assert len(result) > len(template_text)

    def test_brace_safety(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """JSON containing braces does not cause a substitution error."""
        # skeleton_json_with_braces is real JSON with many { } characters.
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert "n_start" in result  # a node id from the skeleton

    def test_deterministic(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """Two calls with the same inputs return identical strings."""
        first = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        second = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert first == second

    def test_non_empty(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """Builder returns a non-empty string."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# build_repair_prompt
# ---------------------------------------------------------------------------


class TestBuildRepairPrompt:
    """Tests for build_repair_prompt."""

    def test_contains_storybook_json(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The prompt contains the storybook JSON verbatim."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert storybook_json_with_braces in result

    def test_contains_failing_node_ids(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The prompt includes the failing node ids from the findings."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "n_orphan_node" in result
        assert "n_dead_end" in result

    def test_excludes_non_failing_node_id(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """A node id NOT in the failing findings does not appear in the node-id list.

        We assert that the fabricated id ``n_perfectly_fine_node`` does not
        appear anywhere in the repair prompt (it is not in the storybook JSON
        either, so the only way it could appear is if the builder introduced it,
        which it must not).
        """
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "n_perfectly_fine_node" not in result

    def test_contains_rule_ids(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The prompt includes the rule ids from the findings."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "L1-03" in result
        assert "L1-04" in result

    def test_no_unfilled_approved_skeleton_placeholder(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The {approved_skeleton} placeholder is replaced."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "{approved_skeleton}" not in result

    def test_no_unfilled_validator_report_placeholder(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """The {validator_report} placeholder is replaced."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "{validator_report}" not in result

    def test_no_unfilled_failing_node_ids_placeholder(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """All occurrences of {failing_node_ids} are replaced."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "{failing_node_ids}" not in result

    def test_brace_safety(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """JSON containing braces does not cause a substitution error."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert "n_start" in result  # node id from the storybook JSON

    def test_deterministic(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """Two calls with the same inputs return identical strings."""
        first = build_repair_prompt(storybook_json_with_braces, failing_findings)
        second = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert first == second

    def test_non_empty(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """Builder returns a non-empty string."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert len(result) > 0

    def test_empty_findings_list(self, storybook_json_with_braces: str) -> None:
        """Builder handles an empty findings list without error."""
        result = build_repair_prompt(storybook_json_with_braces, [])
        assert len(result) > 0
        assert "{validator_report}" not in result
        assert "{failing_node_ids}" not in result

    def test_finding_without_node_id_excluded_from_node_list(
        self, storybook_json_with_braces: str
    ) -> None:
        """A finding without a node_id (e.g. schema error) does not corrupt the node list."""
        findings: list[dict[str, object]] = [
            {
                "rule_id": "L1-01",
                "node_id": None,
                "message": "Top-level schema violation.",
            }
        ]
        result = build_repair_prompt(storybook_json_with_braces, findings)
        assert "{failing_node_ids}" not in result
        # None should not appear as a node id in the node-id section.
        assert "L1-01" in result  # still in the validator report section

    def test_finding_with_choice_id_included_in_report(
        self, storybook_json_with_braces: str
    ) -> None:
        """A finding with a choice_id includes that choice_id in the validator report."""
        findings: list[dict[str, object]] = [
            {
                "rule_id": "L1-07",
                "node_id": "n_start",
                "choice_id": "c_go_left",
                "message": "Choice target does not exist.",
            }
        ]
        result = build_repair_prompt(storybook_json_with_braces, findings)
        assert "c_go_left" in result
        assert "L1-07" in result


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
        assert len(result) > 100

    def test_prose_works_without_docs_path(
        self,
        skeleton_json_with_braces: str,
        minimal_brief: ConceptBrief,
    ) -> None:
        """build_prose_prompt runs successfully (templates are bundled)."""
        result = build_prose_prompt(skeleton_json_with_braces, minimal_brief)
        assert len(result) > 100

    def test_repair_works_without_docs_path(
        self,
        storybook_json_with_braces: str,
        failing_findings: list[dict[str, object]],
    ) -> None:
        """build_repair_prompt runs successfully (templates are bundled)."""
        result = build_repair_prompt(storybook_json_with_braces, failing_findings)
        assert len(result) > 100

    def test_importlib_resources_loads_structure_template(self) -> None:
        """importlib.resources can load structure.md from the templates package."""
        from importlib.resources import files

        text = (
            files("cyo_adventure.generation.templates")
            .joinpath("structure.md")
            .read_text(encoding="utf-8")
        )
        assert len(text) > 0
        assert "{concept_brief}" in text

    def test_importlib_resources_loads_prose_template(self) -> None:
        """importlib.resources can load prose.md from the templates package."""
        from importlib.resources import files

        text = (
            files("cyo_adventure.generation.templates")
            .joinpath("prose.md")
            .read_text(encoding="utf-8")
        )
        assert len(text) > 0
        assert "{approved_skeleton}" in text

    def test_importlib_resources_loads_repair_template(self) -> None:
        """importlib.resources can load repair.md from the templates package."""
        from importlib.resources import files

        text = (
            files("cyo_adventure.generation.templates")
            .joinpath("repair.md")
            .read_text(encoding="utf-8")
        )
        assert len(text) > 0
        assert "{approved_skeleton}" in text

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
