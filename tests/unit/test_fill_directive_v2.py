"""The typed v2 FILL directive (WP-2.2, ADR-033 Decision 4) and its consumers.

Covers the grammar (parse, render, the free-text rejection), the node-function
derivation, the v1-to-v2 conversion, ``scripts/check_skeleton.py``'s
enforcement, and what every FILL consumer does when handed a v2 body.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

import scripts.check_skeleton as check_skeleton
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import render_bound_skeleton
from cyo_adventure.generation.diagram import (
    _parse_fill,  # pyright: ignore[reportPrivateUsage]
)
from cyo_adventure.generation.skeleton import (
    commissioned_words_by_node,
    has_unfilled_directives,
)
from cyo_adventure.mutation.compose import ChainStep, apply_chain
from cyo_adventure.mutation.ops import OpParams
from cyo_adventure.mutation.state_promotion import promote_skeleton
from cyo_adventure.storybook.fill_directive import (
    FILL_DIRECTIVE_RE,
    NODE_FUNCTIONS,
    FillDirectiveV2,
    convert_to_v2,
    derive_node_functions,
    directive_version,
    parse_fill_v2,
    v2_directive_violations,
)
from cyo_adventure.storybook.slotted_surfaces import (
    FILL_DIRECTIVE_RE as SURFACES_FILL_RE,
)
from cyo_adventure.storybook.slotted_surfaces import iter_slotted_surfaces
from cyo_adventure.storybook.theme_contract import ThemeContract
from cyo_adventure.validator.agency import inbound_sources

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_CAVE = _REPO / "skeletons" / "8-11" / "the-cave-of-echoes.json"
_CAROUSEL = _REPO / "skeletons" / "8-11" / "the-locked-carousel.json"


def _load(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _nodes(story: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", story["nodes"])


# --------------------------------------------------------------------------
# Grammar
# --------------------------------------------------------------------------


def test_a_v2_directive_round_trips() -> None:
    directive = FillDirectiveV2(role="setup", words=70, function="opening")
    body = directive.render()
    assert body == "<<FILL v=2 role=setup words=70 function=opening>>"
    assert parse_fill_v2(body) == directive
    assert directive_version(body) == 2


@pytest.mark.parametrize(
    "body",
    [
        "<<FILL v=2 role=setup words=70 function=opening beats='a fox'>>",
        "<<FILL v=2 role=setup words=70 function=opening>> extra",
        "<<FILL v=2 role=setup words=70 function=opening>>\n",
        "<<FILL v=2 role=setup function=opening words=70>>",
        "<<FILL v=2 role=setup words=0 function=opening>>",
        "<<FILL v=2 role=Setup words=70 function=opening>>",
        "<<FILL v=2 role=setup words=70 function=payoff>>",
        "<<FILL v=2  role=setup words=70 function=opening>>",
    ],
)
def test_a_v2_directive_with_free_text_or_a_bad_field_does_not_parse(
    body: str,
) -> None:
    assert parse_fill_v2(body) is None
    assert directive_version(body) == 2


def test_version_detection_separates_v1_prose_and_unknown_versions() -> None:
    assert directive_version("<<FILL role=setup words=70 beats='x'>>") == 1
    assert directive_version("You step into the cave.") is None
    assert directive_version("<<FILL v=3 role=setup words=70 function=opening>>") == 0


def test_the_v1_parse_is_the_same_object_everywhere() -> None:
    """v1 parsing is unchanged: slotted_surfaces re-exports the one pattern."""
    assert SURFACES_FILL_RE is FILL_DIRECTIVE_RE
    assert (
        FILL_DIRECTIVE_RE.pattern == r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$"
    )
    assert (
        FILL_DIRECTIVE_RE.match("<<FILL v=2 role=a words=1 function=ending>>") is None
    )


# --------------------------------------------------------------------------
# Node functions
# --------------------------------------------------------------------------


def _toy() -> dict[str, object]:
    """A five-node graph exercising every function and the precedence."""
    return {
        "start_node": "s",
        "nodes": [
            {
                "id": "s",
                "body": "x",
                "choices": [{"id": "c1", "target": "a"}, {"id": "c2", "target": "b"}],
            },
            {"id": "a", "body": "x", "choices": [{"id": "c3", "target": "m"}]},
            {
                "id": "b",
                "body": "x",
                "choices": [{"id": "c4", "target": "m"}, {"id": "c5", "target": "b"}],
            },
            {
                "id": "m",
                "body": "x",
                "choices": [{"id": "c6", "target": "e"}, {"id": "c7", "target": "f"}],
            },
            {"id": "e", "body": "x", "is_ending": True, "choices": []},
            {"id": "f", "body": "x", "ending": {"id": "end_f"}, "choices": []},
        ],
    }


def test_node_functions_follow_the_documented_precedence() -> None:
    assert derive_node_functions(_toy()) == {
        "s": "opening",
        "a": "continue",
        # A self-loop does not make b a merge, and two choices make it a decision.
        "b": "decision",
        # m is a merge and a decision; merge wins.
        "m": "merge",
        "e": "ending",
        "f": "ending",
    }


def test_merge_matches_the_agency_definition_on_a_real_shell() -> None:
    """A derived merge is exactly an agency merge that is not start or ending."""
    story = _load(_CAROUSEL)
    functions = derive_node_functions(story)
    inbound = inbound_sources(story)
    endings = {
        str(n["id"]) for n in _nodes(story) if n.get("is_ending") or n.get("ending")
    }
    expected = {
        node_id
        for node_id, sources in inbound.items()
        if len(sources) >= 2
        and node_id not in endings
        and node_id != story["start_node"]
    }
    assert {k for k, v in functions.items() if v == "merge"} == expected
    assert set(functions.values()) <= set(NODE_FUNCTIONS)


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------


def test_conversion_keeps_everything_but_the_body_and_drops_the_beats() -> None:
    source = _load(_CAVE)
    converted = convert_to_v2(source)
    assert converted is not source
    assert _load(_CAVE) == source, "conversion must not mutate its input"
    assert {k: v for k, v in converted.items() if k != "nodes"} == {
        k: v for k, v in source.items() if k != "nodes"
    }
    for before, after in zip(_nodes(source), _nodes(converted), strict=True):
        assert {k: v for k, v in before.items() if k != "body"} == {
            k: v for k, v in after.items() if k != "body"
        }
        v1 = FILL_DIRECTIVE_RE.match(cast("str", before["body"]))
        v2 = parse_fill_v2(cast("str", after["body"]))
        assert v1 is not None
        assert v2 is not None
        assert (v2.role, v2.words) == (v1.group(1), int(v1.group(2)))
        assert "beats" not in cast("str", after["body"])
    assert v2_directive_violations(converted) == []
    assert commissioned_words_by_node(converted) == commissioned_words_by_node(source)


def test_conversion_refuses_a_prose_body() -> None:
    source = _load(_CAVE)
    _nodes(source)[3]["body"] = "Already written prose."
    with pytest.raises(ValidationError, match="no v1 FILL directive"):
        convert_to_v2(source)


def test_conversion_refuses_a_role_the_v2_grammar_cannot_hold() -> None:
    source = _load(_CAVE)
    _nodes(source)[0]["body"] = "<<FILL role=Setup words=70 beats='x'>>"
    with pytest.raises(ValidationError, match="cannot be written in the v2 grammar"):
        convert_to_v2(source)


# --------------------------------------------------------------------------
# Violations and check_skeleton.py
# --------------------------------------------------------------------------


def test_a_v1_skeleton_has_no_v2_violations() -> None:
    assert v2_directive_violations(_load(_CAVE)) == []


def test_violations_name_free_text_a_wrong_function_and_a_mixed_shell() -> None:
    shape = convert_to_v2(_load(_CAVE))
    nodes = _nodes(shape)
    nodes[0]["body"] = "<<FILL v=2 role=setup words=70 function=opening beats='x'>>"
    nodes[1]["body"] = "<<FILL v=2 role=choice words=50 function=continue>>"
    nodes[2]["body"] = "<<FILL role=rising words=95 beats='a tunnel'>>"
    nodes[3]["body"] = "<<FILL v=9 role=choice words=100 function=decision>>"
    problems = v2_directive_violations(shape)
    assert len(problems) == 4
    assert "carries free text" in problems[0]
    assert "graph makes it decision" in problems[1]
    assert "v1 directive in a v2 shape" in problems[2]
    assert "unknown directive version" in problems[3]


def test_check_skeleton_rejects_a_v2_directive_with_free_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shape = convert_to_v2(_load(_CAVE))
    _nodes(shape)[0]["body"] = (
        "<<FILL v=2 role=setup words=70 function=opening beats='Maya and Biscuit'>>"
    )
    path = tmp_path / "the-cave-of-echoes.json"
    path.write_text(json.dumps(shape), encoding="utf-8")
    assert check_skeleton.main([str(path), "--strict-agency"]) == 1
    err = capsys.readouterr().err
    assert "FAIL directive:" in err
    assert "carries free text" in err


def test_check_skeleton_passes_a_clean_v2_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "the-cave-of-echoes.json"
    path.write_text(json.dumps(convert_to_v2(_load(_CAVE))), encoding="utf-8")
    assert check_skeleton.main([str(path), "--strict-agency"]) == 0
    out = capsys.readouterr().out
    assert "directives: version 2" in out
    assert "ok: skeleton passes" in out


# --------------------------------------------------------------------------
# Consumers handed a v2 body
# --------------------------------------------------------------------------


def test_unfilled_and_word_probes_treat_v2_like_v1() -> None:
    shape = convert_to_v2(_load(_CAVE))
    assert has_unfilled_directives(shape)
    assert sum(commissioned_words_by_node(shape).values()) > 0


def test_the_diagram_parser_reads_role_and_words_from_v2() -> None:
    assert _parse_fill("<<FILL v=2 role=setup words=70 function=opening>>") == (
        "setup",
        70,
    )


def test_a_v2_body_is_not_a_slotted_surface_and_binding_leaves_it_alone() -> None:
    """Binding renders labels and titles but never touches a v2 body."""
    shape = convert_to_v2(_load(_CAVE))
    kinds = {surface.kind for surface in iter_slotted_surfaces(shape)}
    assert "beats" not in kinds
    contract = ThemeContract.model_validate_json(
        _CAVE.with_name("the-cave-of-echoes.contract.json").read_text(encoding="utf-8")
    )
    rendered = render_bound_skeleton(copy.deepcopy(shape), contract.default_binding)
    for before, after in zip(_nodes(shape), _nodes(rendered), strict=True):
        assert before["body"] == after["body"]
    labels = [
        cast("str", c["label"])
        for n in _nodes(rendered)
        for c in cast("list[dict[str, object]]", n.get("choices", []))
    ]
    assert not any("{" in label for label in labels)


@pytest.mark.asyncio
async def test_fill_skeleton_refuses_a_v2_shape() -> None:
    from cyo_adventure.generation.orchestrator import fill_skeleton
    from cyo_adventure.generation.pii import PiiContext

    class _NeverCalled:
        async def complete(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("the provider must not be called for a v2 shape")

    shape = convert_to_v2(_load(_CAVE))
    provider = _NeverCalled()
    pii = PiiContext(child_names=frozenset())
    with pytest.raises(ValidationError, match="cannot fill a v2 shape"):
        await fill_skeleton(shape, {}, provider, pii)  # pyright: ignore[reportArgumentType]


def test_mutation_refuses_a_v2_shape() -> None:
    shape = convert_to_v2(_load(_CAVE))
    steps = [ChainStep(op_id="M1", params=OpParams.of())]
    with pytest.raises(ValidationError, match="v2 shape is frozen"):
        apply_chain(shape, steps)


def test_state_promotion_refuses_a_v2_shape() -> None:
    report = promote_skeleton(convert_to_v2(_load(_CAROUSEL)))
    assert report.status == "refused"
    assert "Story Plan" in report.reason
