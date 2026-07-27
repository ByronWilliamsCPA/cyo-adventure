"""Unit tests for the WS-2 bound-skeleton render (generation/binding.py).

Covers ``render_bound_skeleton``'s substitution scope (beats/titles/labels
only), its four post-conditions (residual tokens, structure fingerprint, the
validation gate, and CR-1's role/words invariant), and ``load_contract_for``'s
sidecar-absent / half-migrated / drift / present branches.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.generation import binding
from cyo_adventure.generation.binding import (
    contract_path_for,
    load_contract_for,
    render_bound_skeleton,
)
from cyo_adventure.storybook.sentinels import SENTINEL_RE, wrap
from cyo_adventure.storybook.theme_contract import (
    SLOT_TOKEN_RE,
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from cyo_adventure.validator.gate import run_gate

_PILOT_SKELETON_PATH = (
    Path(__file__).resolve().parents[2]
    / "out"
    / "pilot"
    / "the-cave-of-echoes.parameterized.json"
)


def _nodes(doc: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", doc["nodes"])


def _node_by_id(doc: dict[str, object], node_id: str) -> dict[str, object]:
    for node in _nodes(doc):
        if node["id"] == node_id:
            return node
    msg = f"no node with id {node_id!r}"
    raise AssertionError(msg)


def _choices(node: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", node["choices"])


def _ending(node: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", node["ending"])


def _tiny_skeleton() -> dict[str, object]:
    """Return a fresh, gate-passing, schema-valid fixture skeleton.

    One decision node with a FILL body carrying two slots in its beats
    (``{HERO}``, ``{A1_GATE}``) and one slotted choice label
    (``{A1_OFFER}``); two ending nodes, one with a slotted title
    (``{PRIZE}``) and one with a fixed title. Verified (by construction and
    by this module's own tests) to pass ``run_gate`` with ``blocked=False``.
    """
    return {
        "schema_version": "2.0",
        "id": "s_test_bind",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    "<<FILL role=setup words=40 beats='The hero, {HERO}, "
                    "arrives at {A1_GATE} and must choose a path.'>>"
                ),
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Approach {A1_OFFER}.",
                        "target": "n_end_a",
                    },
                    {
                        "id": "c_b",
                        "label": "Turn back toward home.",
                        "target": "n_end_b",
                    },
                ],
            },
            {
                "id": "n_end_a",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero claims the "
                    "prize and celebrates.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The {PRIZE}",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero returns "
                    "home safely.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "completion",
                    "title": "Home Again",
                },
                "choices": [],
            },
        ],
    }


_FULL_BINDINGS = {
    "HERO": "Priya",
    "A1_GATE": "the jammed hatch",
    "A1_OFFER": "a glinting tide pool",
    "PRIZE": "Glass Starfish",
}


def _slot(slot_id: str, *, scope: SlotScope = SlotScope.GLOBAL) -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=scope,
        meaning=f"placeholder meaning for {slot_id}",
        constraints=SlotConstraints(),
    )


def _tiny_contract() -> ThemeContract:
    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_test_bind",
        age_band="3-5",
        legacy_lexicon=[],
        default_binding=dict(_FULL_BINDINGS),
        slots=[
            _slot("HERO"),
            _slot("A1_GATE", scope=SlotScope.TRACK),
            _slot("A1_OFFER", scope=SlotScope.TRACK),
            _slot("PRIZE", scope=SlotScope.ENDING),
        ],
    )


# ---------------------------------------------------------------------------
# render_bound_skeleton: substitution scope
# ---------------------------------------------------------------------------


def test_render_substitutes_only_beats_titles_labels() -> None:
    """Substitution touches beats text, ending titles, and choice labels only."""
    skeleton = _tiny_skeleton()
    bound = render_bound_skeleton(skeleton, _FULL_BINDINGS)

    start = _node_by_id(bound, "n_start")
    assert start["body"] == (
        "<<FILL role=setup words=40 beats='The hero, Priya, arrives at the "
        "jammed hatch and must choose a path.'>>"
    )
    choices = _choices(start)
    assert choices[0]["label"] == "Approach a glinting tide pool."
    assert choices[1]["label"] == "Turn back toward home."

    end_a = _node_by_id(bound, "n_end_a")
    assert _ending(end_a)["title"] == "The Glass Starfish"

    end_b = _node_by_id(bound, "n_end_b")
    assert _ending(end_b)["title"] == "Home Again"

    # Structural fields are untouched.
    assert bound["start_node"] == skeleton["start_node"]
    assert bound["metadata"] == skeleton["metadata"]
    for original_node, bound_node in zip(_nodes(skeleton), _nodes(bound), strict=True):
        assert original_node["id"] == bound_node["id"]
        assert original_node["is_ending"] == bound_node["is_ending"]


def test_render_does_not_mutate_the_input_skeleton() -> None:
    """The original skeleton dict is untouched (render works on a deep copy)."""
    skeleton = _tiny_skeleton()
    before = copy.deepcopy(skeleton)
    render_bound_skeleton(skeleton, _FULL_BINDINGS)
    assert skeleton == before


def test_render_substitutes_regex_metacharacters_literally() -> None:
    """A value containing regex metacharacters is inserted verbatim."""
    skeleton = _tiny_skeleton()
    tricky_bindings = dict(_FULL_BINDINGS)
    tricky_bindings["A1_OFFER"] = r"a$1 \1 (x)"
    bound = render_bound_skeleton(skeleton, tricky_bindings)
    start = _node_by_id(bound, "n_start")
    choices = _choices(start)
    assert choices[0]["label"] == r"Approach a$1 \1 (x)."


# ---------------------------------------------------------------------------
# render_bound_skeleton: personalizable slots (P1b, ADR-023)
# ---------------------------------------------------------------------------


def test_render_wraps_personalizable_slot_in_beats_and_ending_title() -> None:
    """A personalizable slot's value is sentinel-wrapped in beats and ending title."""
    skeleton = _tiny_skeleton()
    bound = render_bound_skeleton(
        skeleton, _FULL_BINDINGS, personalizable_slots=frozenset({"HERO", "PRIZE"})
    )

    start = _node_by_id(bound, "n_start")
    assert wrap("HERO", "Priya") in cast("str", start["body"])
    # A non-personalizable slot in the same beats string stays bare.
    assert "the jammed hatch" in cast("str", start["body"])

    end_a = _node_by_id(bound, "n_end_a")
    assert _ending(end_a)["title"] == "The " + wrap("PRIZE", "Glass Starfish")


def test_render_never_wraps_a_personalizable_slot_in_a_choice_label() -> None:
    """Choice labels always carry the BARE value, even for a personalizable slot."""
    skeleton = _tiny_skeleton()
    bound = render_bound_skeleton(
        skeleton, _FULL_BINDINGS, personalizable_slots=frozenset({"A1_OFFER"})
    )
    start = _node_by_id(bound, "n_start")
    choices = _choices(start)
    assert choices[0]["label"] == "Approach a glinting tide pool."
    assert "{~" not in cast("str", choices[0]["label"])


def test_render_with_no_personalizable_slots_is_byte_identical_to_before() -> None:
    """Passing an empty (or omitted) ``personalizable_slots`` changes nothing."""
    skeleton = _tiny_skeleton()
    explicit_empty = render_bound_skeleton(
        skeleton, _FULL_BINDINGS, personalizable_slots=frozenset()
    )
    omitted = render_bound_skeleton(skeleton, _FULL_BINDINGS)
    assert explicit_empty == omitted


def test_render_sentinel_leaves_no_residual_slot_token() -> None:
    """A sentinel-wrapped personalizable value never trips the residual-token check."""
    skeleton = _tiny_skeleton()
    bound = render_bound_skeleton(
        skeleton, _FULL_BINDINGS, personalizable_slots=frozenset({"HERO"})
    )
    serialized = json.dumps(bound)
    assert not SLOT_TOKEN_RE.findall(serialized)
    assert SENTINEL_RE.search(serialized) is not None


def test_render_personalizable_slot_with_non_empty_default_succeeds() -> None:
    """A personalizable slot with a non-empty default_binding value renders cleanly."""
    skeleton = _tiny_skeleton()
    bound = render_bound_skeleton(
        skeleton, _FULL_BINDINGS, personalizable_slots=frozenset({"HERO"})
    )
    start = _node_by_id(bound, "n_start")
    assert wrap("HERO", "Priya") in cast("str", start["body"])


def test_render_personalizable_slot_with_empty_default_raises() -> None:
    """`wrap` rejects an empty value; an empty personalizable default must raise.

    Edge case flagged by the P1b brief: a personalizable slot requires a
    non-empty `default_binding` value, or render fails (via `wrap`'s own
    empty-value guard) rather than silently emitting a malformed sentinel.
    """
    skeleton = _tiny_skeleton()
    empty_bindings = dict(_FULL_BINDINGS)
    empty_bindings["HERO"] = ""
    personalizable_slots = frozenset({"HERO"})
    with pytest.raises(ValidationError, match="must not be empty"):
        render_bound_skeleton(skeleton, empty_bindings, personalizable_slots)


def test_validator_gate_accepts_sentinel_bearing_final_prose() -> None:
    """CRITICAL verification (P1b brief): the gate accepts a sentinel in final prose.

    After ``render_bound_skeleton`` wraps a personalizable slot, the sentinel
    ``{~SLOTID:Value~}`` is copied verbatim into a node's FINAL prose by the
    fill LLM, per ``generation/templates/fill_bound.md``'s "Verbatim tokens"
    instruction. This is a small hand-built ALREADY-FILLED (no ``<<FILL...>>``
    directive) storybook -- the artifact that actually reaches storage after
    Stage B' -- with a sentinel embedded in a node body and an ending title
    (never a choice label, per design). Proves no existing charset, topology,
    or schema rule anywhere in the combined gate (layer1 schema/logic, policy,
    layer2 walk, reading-level, safety) rejects ``{``, ``}``, or ``~`` in
    stored node prose. If this ever fails, the correct response is to STOP
    and report BLOCKED with the exact rule, never to weaken the rule.
    """
    sentinel = wrap("HERO", "Explorer")
    filled: dict[str, object] = {
        "schema_version": "2.0",
        "id": "s_test_sentinel_gate",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    f"{sentinel} stood at the gate, wondering which path to take next."
                ),
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Go toward the light.",
                        "target": "n_end_a",
                    },
                    {
                        "id": "c_b",
                        "label": "Turn back toward home.",
                        "target": "n_end_b",
                    },
                ],
            },
            {
                "id": "n_end_a",
                "body": f"{sentinel} celebrated finding the prize at last.",
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": f"The Triumph of {sentinel}",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": f"{sentinel} returned home safely for supper.",
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "completion",
                    "title": "Home Again",
                },
                "choices": [],
            },
        ],
    }

    result = run_gate(filled)

    assert result.blocked is False, "; ".join(
        f"{finding.rule_id}: {finding.message}" for finding in result.report.errors
    )


# ---------------------------------------------------------------------------
# render_bound_skeleton: post-conditions
# ---------------------------------------------------------------------------


def test_render_fingerprint_post_condition_holds() -> None:
    """A valid render shares its structural fingerprint with the original."""
    skeleton = _tiny_skeleton()
    bound = render_bound_skeleton(skeleton, _FULL_BINDINGS)
    assert structure_fingerprint(bound) == structure_fingerprint(skeleton)


def test_render_gate_post_condition_holds() -> None:
    """A valid render passes the blocking validation gate."""
    skeleton = _tiny_skeleton()
    bound = render_bound_skeleton(skeleton, _FULL_BINDINGS)
    assert run_gate(bound).blocked is False


def test_render_residual_token_raises() -> None:
    """A binding missing a declared slot leaves a residual token and fails."""
    skeleton = _tiny_skeleton()
    incomplete = dict(_FULL_BINDINGS)
    del incomplete["PRIZE"]
    with pytest.raises(ValidationError, match="unresolved"):
        render_bound_skeleton(skeleton, incomplete)


def test_render_residual_token_anywhere_raises() -> None:
    """An empty bindings map leaves every token unresolved and fails."""
    skeleton = _tiny_skeleton()
    with pytest.raises(ValidationError, match="unresolved"):
        render_bound_skeleton(skeleton, {})


def test_render_fingerprint_mismatch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A substitution that also rewires structure fails the fingerprint check.

    Simulates a substitution bug that (incorrectly) swaps two choices'
    targets after otherwise substituting normally: no residual token remains
    and every FILL directive's role/words is untouched, but the structural
    fingerprint no longer matches, so the fingerprint post-condition (which
    runs before the gate and CR-1 checks) is what catches it.
    """
    real_substitute = binding._substitute_slotted_surfaces

    def _target_swapping_substitute(
        bound: dict[str, object],
        bindings: Mapping[str, str],
        personalizable_slots: frozenset[str] = frozenset(),
    ) -> None:
        real_substitute(bound, bindings, personalizable_slots)
        start = _node_by_id(bound, "n_start")
        choices = _choices(start)
        choices[0]["target"], choices[1]["target"] = (
            choices[1]["target"],
            choices[0]["target"],
        )

    monkeypatch.setattr(
        binding, "_substitute_slotted_surfaces", _target_swapping_substitute
    )
    skeleton = _tiny_skeleton()
    with pytest.raises(ValidationError, match="structural fingerprint"):
        render_bound_skeleton(skeleton, _FULL_BINDINGS)


def test_assert_gate_not_blocked_raises_on_a_gate_blocking_document() -> None:
    """The gate post-condition helper raises when run_gate reports blocked."""
    blocked_doc: dict[str, object] = {
        "schema_version": "2.0",
        "id": "s_bad",
        "nodes": [],
    }
    assert run_gate(blocked_doc).blocked is True
    with pytest.raises(ValidationError, match="validation gate"):
        binding._assert_gate_not_blocked(blocked_doc)


def test_fill_role_words_map_skips_non_string_node_ids() -> None:
    """A node whose ``id`` is not a string is skipped, not raised on."""
    skeleton: dict[str, object] = {"nodes": [{"id": 123, "body": "prose"}]}
    assert binding._fill_role_words_map(skeleton) == {}


# ---------------------------------------------------------------------------
# CR-1: role/words invariant
# ---------------------------------------------------------------------------


def test_render_preserves_role_words_map() -> None:
    """The parsed {node_id: (role, words)} map is identical before and after."""
    skeleton = _tiny_skeleton()
    before = binding._fill_role_words_map(skeleton)
    bound = render_bound_skeleton(skeleton, _FULL_BINDINGS)
    after = binding._fill_role_words_map(bound)
    assert before == after
    assert before == {
        "n_start": ("setup", "40"),
        "n_end_a": ("ending", "30"),
        "n_end_b": ("ending", "30"),
    }


def test_render_rejects_mangled_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-1: a corrupted substitution that changes ``words=`` is rejected.

    Fingerprint equality alone cannot catch this (the whole body is stripped
    from the fingerprint), so the render must verify its own role/words
    invariant directly. Simulate a substitution bug by monkeypatching the
    internal substitution helper to run the real substitution (so every
    other post-condition still holds) and then mangle one node's word
    target, proving CR-1 is what catches it.
    """
    real_substitute = binding._substitute_slotted_surfaces

    def _corrupting_substitute(
        bound: dict[str, object],
        bindings: Mapping[str, str],
        personalizable_slots: frozenset[str] = frozenset(),
    ) -> None:
        real_substitute(bound, bindings, personalizable_slots)
        nodes = _nodes(bound)
        nodes[0]["body"] = (
            "<<FILL role=setup words=4 beats='The hero, Priya, arrives at "
            "the jammed hatch and must choose a path.'>>"
        )

    monkeypatch.setattr(binding, "_substitute_slotted_surfaces", _corrupting_substitute)
    skeleton = _tiny_skeleton()
    with pytest.raises(ValidationError, match=r"CR-1|role/words"):
        render_bound_skeleton(skeleton, _FULL_BINDINGS)


def test_render_rejects_fill_directive_degraded_to_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-1: a FILL directive silently replaced by raw prose is rejected."""
    real_substitute = binding._substitute_slotted_surfaces

    def _degrading_substitute(
        bound: dict[str, object],
        bindings: Mapping[str, str],
        personalizable_slots: frozenset[str] = frozenset(),
    ) -> None:
        real_substitute(bound, bindings, personalizable_slots)
        nodes = _nodes(bound)
        nodes[0]["body"] = "Priya arrives at the jammed hatch."

    monkeypatch.setattr(binding, "_substitute_slotted_surfaces", _degrading_substitute)
    skeleton = _tiny_skeleton()
    with pytest.raises(ValidationError, match=r"CR-1|role/words"):
        render_bound_skeleton(skeleton, _FULL_BINDINGS)


# ---------------------------------------------------------------------------
# contract_path_for / load_contract_for
# ---------------------------------------------------------------------------


def test_contract_path_for_derives_sidecar_name(tmp_path: Path) -> None:
    skeleton_path = tmp_path / "8-11" / "the-cave-of-echoes.json"
    assert contract_path_for(skeleton_path) == (
        tmp_path / "8-11" / "the-cave-of-echoes.contract.json"
    )


def test_load_contract_for_no_sidecar_no_tokens_returns_none(tmp_path: Path) -> None:
    """A legacy (non-parameterized) skeleton with no sidecar loads as None."""
    skeleton_path = tmp_path / "the-forest-path.json"
    plain_skeleton: dict[str, object] = {
        "nodes": [{"id": "n1", "body": "Already-filled prose.", "choices": []}]
    }
    skeleton_path.write_text(json.dumps(plain_skeleton), encoding="utf-8")
    assert load_contract_for(skeleton_path, plain_skeleton) is None


def test_load_contract_for_half_migrated_raises(tmp_path: Path) -> None:
    """A skeleton with {SLOT} tokens but no sidecar fails closed."""
    skeleton = _tiny_skeleton()
    skeleton_path = tmp_path / "s_test_bind.json"
    skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
    with pytest.raises(ValidationError, match="half-migrated"):
        load_contract_for(skeleton_path, skeleton)


def test_load_contract_for_present_and_matching_returns_contract(
    tmp_path: Path,
) -> None:
    skeleton = _tiny_skeleton()
    skeleton_path = tmp_path / "s_test_bind.json"
    skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
    contract = _tiny_contract()
    contract_path_for(skeleton_path).write_text(
        contract.model_dump_json(), encoding="utf-8"
    )
    loaded = load_contract_for(skeleton_path, skeleton)
    assert loaded is not None
    assert loaded.skeleton_slug == "s_test_bind"


def test_load_contract_for_drift_raises(tmp_path: Path) -> None:
    """A contract whose declared slots do not match the skeleton's tokens fails."""
    skeleton = _tiny_skeleton()
    skeleton_path = tmp_path / "s_test_bind.json"
    skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")

    contract = _tiny_contract()
    remaining_slots = [s for s in contract.slots if s.id != "PRIZE"]
    drifted = ThemeContract(
        contract_version=contract.contract_version,
        skeleton_slug=contract.skeleton_slug,
        age_band=contract.age_band,
        legacy_lexicon=contract.legacy_lexicon,
        default_binding={
            k: v for k, v in contract.default_binding.items() if k != "PRIZE"
        },
        slots=remaining_slots,
    )
    contract_path_for(skeleton_path).write_text(
        drifted.model_dump_json(), encoding="utf-8"
    )

    with pytest.raises(ValidationError, match="does not match"):
        load_contract_for(skeleton_path, skeleton)


def test_load_contract_for_invalid_sidecar_json_raises(tmp_path: Path) -> None:
    skeleton = _tiny_skeleton()
    skeleton_path = tmp_path / "s_test_bind.json"
    skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
    contract_path_for(skeleton_path).write_text("not json", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_contract_for(skeleton_path, skeleton)


# ---------------------------------------------------------------------------
# End-to-end: the real pilot parameterized skeleton
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _PILOT_SKELETON_PATH.is_file(), reason="pilot artifact not present"
)
def test_render_end_to_end_on_pilot_parameterized_skeleton() -> None:
    """The real 64-node/73-slot pilot skeleton renders cleanly end to end."""
    skeleton = cast(
        "dict[str, object]",
        json.loads(_PILOT_SKELETON_PATH.read_text(encoding="utf-8")),
    )
    tokens = binding._slotted_surface_tokens(skeleton)
    assert tokens, "expected the pilot skeleton to declare slot tokens"

    bindings = {token: f"the {token.lower().replace('_', ' ')}" for token in tokens}
    before = binding._fill_role_words_map(skeleton)

    bound = render_bound_skeleton(skeleton, bindings)

    assert not SLOT_TOKEN_RE.findall(json.dumps(bound))
    assert structure_fingerprint(bound) == structure_fingerprint(skeleton)
    assert run_gate(bound).blocked is False
    assert binding._fill_role_words_map(bound) == before


# ---------------------------------------------------------------------------
# Node-level slot-scanning helper (_iter_nodes)
# ---------------------------------------------------------------------------


def test_iter_nodes_returns_nothing_when_nodes_key_is_absent() -> None:
    """A mapping with no ``nodes`` key yields no nodes (not a crash)."""
    assert list(binding._iter_nodes({})) == []


def test_iter_nodes_skips_non_dict_entries_in_the_nodes_list() -> None:
    """A malformed ``nodes`` list with a non-dict entry skips it, not raises."""
    skeleton: Mapping[str, object] = {
        "nodes": ["not a node", {"id": "n1", "body": "prose"}]
    }
    nodes = list(binding._iter_nodes(skeleton))
    assert nodes == [{"id": "n1", "body": "prose"}]


# ---------------------------------------------------------------------------
# Node-level substitution helpers (_substitute_body, _substitute_ending_title,
# _substitute_choice_labels)
# ---------------------------------------------------------------------------


def test_substitute_body_no_op_when_body_is_not_a_string() -> None:
    """A node whose ``body`` is not a string is left untouched."""
    node: dict[str, object] = {"body": 123}
    binding._substitute_body(node, {"HERO": "Priya"})
    assert node["body"] == 123


def test_substitute_body_no_op_when_body_is_not_a_fill_directive() -> None:
    """A node whose ``body`` does not match the FILL pattern is left untouched."""
    node: dict[str, object] = {"body": "Already-filled prose with {HERO}."}
    binding._substitute_body(node, {"HERO": "Priya"})
    assert node["body"] == "Already-filled prose with {HERO}."


def test_substitute_ending_title_no_op_when_title_is_not_a_string() -> None:
    """A node whose ending ``title`` is not a string is left untouched."""
    node: dict[str, object] = {"ending": {"id": "e_a", "title": 123}}
    binding._substitute_ending_title(node, {"PRIZE": "Glass Starfish"})
    assert cast("dict[str, object]", node["ending"])["title"] == 123


def test_substitute_choice_labels_skips_non_dict_and_non_string_labels() -> None:
    """Non-dict choices and non-string labels are left untouched in place."""
    choices: list[object] = [
        "not a choice",
        {"label": 123},
        {"label": "Approach {A1_OFFER}."},
    ]
    node: dict[str, object] = {"choices": choices}
    binding._substitute_choice_labels(node, {"A1_OFFER": "a glinting tide pool"})
    assert choices[0] == "not a choice"
    assert cast("dict[str, object]", choices[1])["label"] == 123
    assert cast("dict[str, object]", choices[2])["label"] == (
        "Approach a glinting tide pool."
    )
