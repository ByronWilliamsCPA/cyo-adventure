"""Tests for L1-8, the field-minor floor (ADR-025 decision 3, UW-A45)."""

from __future__ import annotations

from typing import Any

from cyo_adventure.storybook.field_minors import BASELINE_FIELDS, FIELD_MINORS
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.layer1 import validate_layer1
from cyo_adventure.validator.report import Severity


def _story(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid story dict with overrides applied."""
    data: dict[str, Any] = {
        "schema_version": "2.1",
        "id": "test-story",
        "version": 1,
        "title": "Test Story",
        "metadata": {"age_band": "8-11", "tier": 1},
        "variables": [],
        "start_node": "n1",
        "nodes": [
            {
                "id": "n1",
                "body": "The end.",
                "ending": {"kind": "resolution", "valence": "satisfying"},
            }
        ],
    }
    data.update(overrides)
    return data


def _l1_8(data: dict[str, Any]) -> list[str]:
    report = validate_layer1(data)
    return [
        f.message
        for f in report.findings
        if f.rule_id == "L1-8" and f.severity is Severity.ERROR
    ]


def test_a_minor_one_field_at_minor_one_is_accepted() -> None:
    data = _story(schema_version="2.1", accepts_character={})
    assert _l1_8(data) == []


def test_a_minor_one_field_at_minor_zero_is_rejected() -> None:
    """The whole point of the rule: an under-declared document fails the gate.

    Before L1-8, a document could carry accepts_character while declaring
    "2.0" and be silently admitted, because extra="forbid" only rejects fields
    the *current build* does not know, and this build knows the field.
    """
    data = _story(schema_version="2.0", accepts_character={})
    messages = _l1_8(data)
    assert len(messages) == 1
    assert "accepts_character" in messages[0]
    assert "2.1" in messages[0]


def test_a_minor_one_field_declared_null_still_counts_as_used() -> None:
    """Presence of the key is the trigger, not its value.

    A parsed model cannot tell an explicit null from an absent key, which is
    exactly why this rule reads the raw dict.
    """
    data = _story(schema_version="2.0", accepts_character=None)
    assert len(_l1_8(data)) == 1


def test_a_plain_two_zero_document_is_untouched() -> None:
    """A skeleton that uses no minor-1 field stays correctly stamped 2.0.

    This is the case that makes the converse-enforcement ruling cheaper than a
    stamping sweep: 61 catalog skeletons need no edit.
    """
    assert _l1_8(_story(schema_version="2.0")) == []


def test_a_malformed_version_produces_no_l1_8_finding() -> None:
    """L1-1 owns malformed-version reporting; L1-8 must not double-report."""
    assert _l1_8(_story(schema_version="banana", accepts_character={})) == []


def test_a_missing_version_produces_no_l1_8_finding() -> None:
    data = _story(accepts_character={})
    del data["schema_version"]
    assert _l1_8(data) == []


def _gateable_story(
    schema_version: str, *, with_accepts_character: bool
) -> dict[str, Any]:
    """A story that passes every other Layer-1 rule cleanly.

    Single reachable ending node, no unmet reachability/termination/logic
    findings, and a node count below the band minimum (a WARNING, not an
    ERROR, per L1-7). This isolates L1-8 as the only possible ERROR-severity
    finding, so a blocked result can only be attributed to L1-8 through the
    gate's L1/L2/PL prefix check, not to some unrelated error riding along.
    """
    data: dict[str, Any] = {
        "schema_version": schema_version,
        "id": "gateable-story",
        "version": 1,
        "title": "Gateable Story",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 4.0,
                "tolerance": 1.0,
            },
            "tier": 2,
            "themes": [],
            "estimated_minutes": 5,
            "ending_count": 1,
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
            "topology": "branch_and_bottleneck",
        },
        "variables": [],
        "start_node": "n1",
        "nodes": [
            {
                "id": "n1",
                "body": "The end.",
                "on_enter": [],
                "choices": [],
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Done",
                },
                "tags": [],
            }
        ],
    }
    if with_accepts_character:
        data["accepts_character"] = {}
    return data


def test_l1_8_alone_sets_blocked_true_through_the_gate() -> None:
    """L1-8 must actually block, not just report.

    A finding that reports without setting ``blocked`` looks identical to a
    working rule in every assertion except this one. The companion document
    at minor 2.1 is clean (only the pre-existing L1-7 node-count WARNING),
    which is what proves the block below is attributable to L1-8 and not to
    some other error riding along.
    """
    clean = validate_layer1(_gateable_story("2.1", with_accepts_character=True))
    assert clean.ok

    result = run_gate(_gateable_story("2.0", with_accepts_character=True))
    assert result.blocked is True
    assert any(
        f.rule_id == "L1-8" and f.severity is Severity.ERROR
        for f in result.report.findings
    )


def test_every_storybook_field_is_registered_or_baselined() -> None:
    """Lockstep guard: an unregistered field gets no L1-8 floor at all.

    Mirrors tests/unit/test_validator_rules_catalog.py's shape: enumerate the
    real thing (Storybook.model_fields, never a hand-copied literal list, so
    this test cannot drift the same way the registry could), compare against
    the declared thing (FIELD_MINORS union BASELINE_FIELDS), and fail on
    either direction of mismatch.

    A field in neither set is what happens when a future minor-2 field's
    author forgets to add a FIELD_MINORS entry: L1-8 would silently apply no
    floor to it. This assertion is what would catch that.
    """
    real_fields = frozenset(Storybook.model_fields)
    declared_fields = frozenset(FIELD_MINORS) | BASELINE_FIELDS
    unregistered = sorted(real_fields - declared_fields)
    assert not unregistered, (
        "Storybook field(s) declared in neither field_minors.FIELD_MINORS nor "
        f"field_minors.BASELINE_FIELDS: {unregistered}. If the field existed "
        "at schema minor 0, add it to BASELINE_FIELDS; if it was introduced "
        "at a later minor, add it to FIELD_MINORS with that minor so L1-8 can "
        "enforce a floor on it."
    )


def test_no_field_minors_entry_names_a_field_that_does_not_exist() -> None:
    """A stale FIELD_MINORS entry must not silently enforce a floor on nothing.

    A field rename (or removal) leaves a dangling FIELD_MINORS key unless
    something checks it against the real model; this is that check.
    """
    real_fields = frozenset(Storybook.model_fields)
    stale = sorted(frozenset(FIELD_MINORS) - real_fields)
    assert not stale, (
        f"field_minors.FIELD_MINORS name(s) not present on Storybook: {stale}. "
        "This is a stale entry, likely left behind by a rename; remove it or "
        "correct it to the field's current name."
    )
