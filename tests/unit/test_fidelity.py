"""Unit tests for the pure-code Stage 1 fidelity checks."""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.generation.fidelity import (
    parse_fill_directive,
    run_fidelity_checks,
    structure_violations,
    word_count_violations,
)

_CAVE = Path("skeletons/8-11/the-cave-of-echoes.json")


def test_parse_fill_directive_handles_apostrophe_in_beats() -> None:
    """The real la_tunnel directive has an apostrophe inside beats (Biscuit's);
    a naive first-quote-closes regex would truncate it."""
    story = json.loads(_CAVE.read_text(encoding="utf-8"))
    node = next(n for n in story["nodes"] if n["id"] == "la_tunnel")
    parsed = parse_fill_directive(node["body"])
    assert parsed is not None
    assert parsed["role"] == "rising"
    assert parsed["words"] == "95"
    assert "Biscuit's ears prick" in parsed["beats"]
    assert parsed["beats"].endswith("soft rustling")


def test_parse_fill_directive_returns_none_for_non_directive() -> None:
    """A plain prose body (not a FILL directive) parses to None."""
    assert parse_fill_directive("You step into the cave.") is None


def _minimal_story(body: str) -> dict[str, object]:
    return {
        "id": "s_x",
        "start_node": "n1",
        "variables": {},
        "metadata": {"age_band": "8-11"},
        "nodes": [
            {
                "id": "n1",
                "body": body,
                "is_ending": False,
                "on_enter": [],
                "choices": [
                    {
                        "id": "c1",
                        "label": "go left",
                        "target": "n2",
                        "condition": None,
                        "effects": [],
                    }
                ],
            }
        ],
    }


def test_structure_violations_empty_when_only_prose_changes() -> None:
    """Changing only body/label text is not a structural violation."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    filled = _minimal_story("You step into the glowing cave, heart pounding.")
    filled["nodes"][0]["choices"][0]["label"] = "Step into the tunnel"
    assert structure_violations(original, filled) == []


def test_structure_violations_flags_changed_target() -> None:
    """Changing a choice's target is a structural violation."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    filled = _minimal_story("You step into the glowing cave.")
    filled["nodes"][0]["choices"][0]["target"] = "n3"
    violations = structure_violations(original, filled)
    assert any("choices changed" in v for v in violations)


def test_structure_violations_flags_changed_metadata() -> None:
    """Changing top-level metadata is a structural violation."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    filled = _minimal_story("You step into the glowing cave.")
    filled["metadata"] = {"age_band": "10-13"}
    violations = structure_violations(original, filled)
    assert any("metadata" in v for v in violations)


def test_word_count_violations_flags_too_short() -> None:
    """A body far below its directive's word target is flagged."""
    original = _minimal_story("<<FILL role=setup words=100 beats='go'>>")
    filled = _minimal_story("Too short.")
    violations = word_count_violations(original, filled)
    assert len(violations) == 1
    assert "n1" in violations[0]


def test_word_count_violations_silent_within_tolerance() -> None:
    """A body within the tolerance band produces no violation."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    filled = _minimal_story(" ".join(["word"] * 11))
    assert word_count_violations(original, filled) == []


def test_run_fidelity_checks_flags_unfilled_directive() -> None:
    """A leftover FILL directive in the filled doc is flagged."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    filled = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    violations = run_fidelity_checks(original, filled)
    assert any("unfilled" in v for v in violations)


def test_run_fidelity_checks_clean_fill_has_no_violations() -> None:
    """A clean, in-tolerance, structure-preserving fill passes with no violations."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    filled = _minimal_story(" ".join(["word"] * 10))
    assert run_fidelity_checks(original, filled) == []
