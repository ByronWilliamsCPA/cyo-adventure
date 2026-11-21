"""Unit tests for the pure-code Stage 1 fidelity checks."""

from __future__ import annotations

from cyo_adventure.generation.fidelity import (
    parse_fill_directive,
    run_fidelity_checks,
    structure_violations,
    word_count_violations,
)


def test_parse_fill_directive_handles_apostrophe_in_beats() -> None:
    """An apostrophe inside the beats segment must not truncate the parse.

    Beats guidance is single-quoted (``beats='...'``), so a naive
    first-quote-closes regex would stop at the apostrophe in "Biscuit's"; the
    parser must instead consume the whole segment up to the closing ``'>>``.
    Modeled on the classic cave-of-echoes ``la_tunnel`` directive but kept
    synthetic, since that skeleton's beats are now parameterized (WS-2) and its
    prose is no longer fixed.
    """
    body = (
        "<<FILL role=rising words=95 "
        "beats='Biscuit's ears prick at the soft rustling'>>"
    )
    parsed = parse_fill_directive(body)
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


def test_structure_violations_flags_net_new_node_key() -> None:
    """A structural key the filled node ADDS but the skeleton lacked is flagged.

    The union-of-keys iteration is what catches this: here the skeleton node has
    no ``is_ending`` key and the fill injects ``is_ending=True`` (flipping the
    node to an ending). Iterating only the original node's keys would miss the
    net-new key and silently weaken the "structure exactly preserved" guarantee.
    """
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    del original["nodes"][0]["is_ending"]  # skeleton lacks the key entirely
    filled = _minimal_story("You step into the glowing cave.")
    filled["nodes"][0]["is_ending"] = True  # the fill injects it
    violations = structure_violations(original, filled)
    assert any("is_ending" in v for v in violations)


def test_structure_violations_tolerates_missing_nodes_list() -> None:
    """A story with no "nodes" key at all indexes to zero nodes on both sides,
    not a crash; the only difference reported is on other top-level keys."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    del original["nodes"]
    filled = _minimal_story("You step into the glowing cave.")
    del filled["nodes"]
    assert structure_violations(original, filled) == []


def test_structure_violations_tolerates_non_list_nodes() -> None:
    """A "nodes" value that isn't a list (malformed document) indexes to zero
    nodes rather than raising."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    original["nodes"] = "not-a-list"
    filled = _minimal_story("You step into the glowing cave.")
    filled["nodes"] = "not-a-list"
    assert structure_violations(original, filled) == []


def test_structure_violations_skips_malformed_node_entries() -> None:
    """A malformed entry in the "nodes" list (not a dict, or a dict with no
    valid string id) is silently excluded from the id-indexed comparison
    rather than crashing or contributing a bogus node id."""
    original = _minimal_story("<<FILL role=setup words=10 beats='go'>>")
    original_nodes = original["nodes"]
    assert isinstance(original_nodes, list)
    original_nodes.append("garbage")
    original_nodes.append({"body": "no id here"})
    filled = _minimal_story("You step into the glowing cave.")
    filled_nodes = filled["nodes"]
    assert isinstance(filled_nodes, list)
    filled_nodes.append({"id": 123, "body": "id is not a string"})
    assert structure_violations(original, filled) == []


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


def test_parse_fill_directive_v1_keys_are_unchanged() -> None:
    """A v1 directive still parses to exactly role, words and beats (WP-2.2)."""
    parsed = parse_fill_directive("<<FILL role=setup words=70 beats='a fox'>>")
    assert parsed == {"role": "setup", "words": "70", "beats": "a fox"}


def test_parse_fill_directive_reads_a_v2_directive_without_beats() -> None:
    """A v2 directive parses with its function and deliberately no beats key."""
    parsed = parse_fill_directive("<<FILL v=2 role=choice words=50 function=decision>>")
    assert parsed == {
        "version": "2",
        "role": "choice",
        "words": "50",
        "function": "decision",
    }


def test_parse_fill_directive_rejects_a_v2_directive_with_free_text() -> None:
    """A v2 body carrying beats or trailing text is not a directive at all."""
    for body in (
        "<<FILL v=2 role=choice words=50 function=decision beats='a fox'>>",
        "<<FILL v=2 role=choice words=50 function=decision>> and then",
        "<<FILL v=2 role=choice words=50 function=surprise>>",
    ):
        assert parse_fill_directive(body) is None, body


def test_word_count_is_checked_for_a_v2_node() -> None:
    """The pure-code word-count check reads a v2 directive's budget."""
    original = {
        "nodes": [
            {"id": "n1", "body": "<<FILL v=2 role=setup words=10 function=opening>>"}
        ]
    }
    filled = {"nodes": [{"id": "n1", "body": "Too short."}]}
    violations = word_count_violations(original, filled)
    assert len(violations) == 1
    assert "target 10" in violations[0]
