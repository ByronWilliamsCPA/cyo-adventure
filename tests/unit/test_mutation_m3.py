"""Unit and property tests for the M3 prune/graft operator (WS-5 D4).

Covers design section 4.4: prune (remove a closed, self-contained subtree and its
single choice edge) and graft (attach a renamed copy of a same-band donor subtree
under a new choice), both Tier-1 only over closed subtrees, plus the dry
contract-merge transform tested against the WS-2 models and the
``load_contract_for`` token-set equality rule (full contract acceptance is D7).

Safety properties pinned here (design section 12 D4): no cross-band content
ingress (a different-band donor is rejected at preconditions); a prune can never
remove the last success/completion ending; a graft is state-free (variable /
effect / condition regions rejected); the two-sided cell envelope is blocking
(a prune below the cell minimum and a graft above the cell maximum are discarded);
and grafted ids are renamed collision-free against the host namespace.
"""

from __future__ import annotations

import json
import random
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import load_contract_for
from cyo_adventure.mutation.acceptance import run_acceptance
from cyo_adventure.mutation.identity import host_id_namespace
from cyo_adventure.mutation.operators import (
    M3,
    M3_OP_ID,
    M3PruneGraft,
    graft_slot_id,
    merge_graft_contract,
    prune_contract,
    region_referenced_slots,
)
from cyo_adventure.mutation.ops import OpParams, ReguideTarget
from cyo_adventure.storybook.theme_contract import ThemeContract, slot_ids
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_HOST_PATH = _SKELETONS_ROOT / "8-11" / "the-cave-of-echoes.json"

# A real accepted graft, found by search over the 8-11 band: the-robot-fair-
# sabotage's ``f_herbie`` subtree (4 nodes, no satisfying ending shallow enough to
# undercut PL-20) grafted under the host's 2-choice ``la_grotto`` decision.
_DONOR_SLUG = "the-robot-fair-sabotage"
_DONOR_SUBTREE = "f_herbie"
_HOST_DECISION = "la_grotto"

# A real accepted prune on the host: cutting ``c_take`` removes the 2-node
# ``la_crystal_take`` subtree, staying above the 8-11 short envelope minimum (60).
_PRUNE_CHOICE = "c_take"


def _floor_always_passes(_parent: object, _candidate: object, _in_cell: object) -> None:
    """A typed structural-floor stub that accepts every candidate (test isolation)."""
    return


def _load(path: Path) -> dict[str, object]:
    """Return a decoded skeleton document."""
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _host() -> dict[str, object]:
    """Return a fresh copy of the host skeleton (the-cave-of-echoes)."""
    return _load(_HOST_PATH)


def _node_ids(story: Mapping[str, object]) -> set[str]:
    """Return the set of node ids in a raw story."""
    ids: set[str] = set()
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if isinstance(node, dict):
                node_id = cast("dict[str, object]", node).get("id")
                if isinstance(node_id, str):
                    ids.add(node_id)
    return ids


def _nodes_by_id(story: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Return every node dict keyed by its id."""
    result: dict[str, dict[str, object]] = {}
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if isinstance(node, dict):
                node_map = cast("dict[str, object]", node)
                node_id = node_map.get("id")
                if isinstance(node_id, str):
                    result[node_id] = node_map
    return result


def _ending_kinds(story: Mapping[str, object]) -> Counter[str]:
    """Return the ending-kind multiset of a raw story."""
    counter: Counter[str] = Counter()
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if not isinstance(node, dict):
                continue
            ending = cast("dict[str, object]", node).get("ending")
            if isinstance(ending, dict):
                kind = cast("dict[str, object]", ending).get("kind")
                if isinstance(kind, str):
                    counter[kind] += 1
    return counter


def _ending_count(story: Mapping[str, object]) -> int:
    """Return the number of ending nodes in a raw story."""
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return 0
    return sum(
        1
        for node in cast("list[object]", nodes)
        if isinstance(node, dict)
        and cast("dict[str, object]", node).get("is_ending") is True
    )


def _donor_region_nodes(
    donor: Mapping[str, object], root: str
) -> list[dict[str, object]]:
    """Return the forward-closure region node dicts of ``root`` in ``donor``."""
    by_id = _nodes_by_id(donor)
    seen: set[str] = {root}
    queue = [root]
    while queue:
        current = queue.pop()
        for choice in cast("list[object]", by_id.get(current, {}).get("choices", [])):
            if isinstance(choice, dict):
                target = cast("dict[str, object]", choice).get("target")
                if isinstance(target, str) and target in by_id and target not in seen:
                    seen.add(target)
                    queue.append(target)
    return [by_id[node_id] for node_id in seen]


# --- Crafted precondition fixtures (never gate-run; preconditions only) ---


def _prune_min_fixture() -> dict[str, object]:
    """Return a 3-5 fixture (8 nodes) where any prune drops below the envelope min.

    The 3-5 band-level budget minimum is 8 nodes; pruning any 2-node route leaves
    6, below the WS-5 two-sided envelope floor. All endings are satisfying so the
    envelope check is the first (and isolated) failure.
    """
    return {
        "start_node": "start",
        "metadata": {
            "age_band": "3-5",
            "tier": 1,
            "topology": "time_cave",
            "ending_count": 3,
        },
        "variables": [],
        "nodes": [
            {
                "id": "start",
                "body": "<<FILL role=setup words=40 beats='pick'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "A.", "target": "r_a1"},
                    {"id": "c_b", "label": "B.", "target": "r_b1"},
                    {"id": "c_c", "label": "C.", "target": "r_c1"},
                ],
            },
            {
                "id": "r_a1",
                "body": "<<FILL role=rising words=40 beats='a'>>",
                "is_ending": False,
                "choices": [{"id": "c_a_end", "label": "End.", "target": "e_a"}],
            },
            {
                "id": "e_a",
                "body": "a done",
                "is_ending": True,
                "ending": {
                    "id": "end_a",
                    "kind": "success",
                    "valence": "positive",
                    "title": "A",
                },
            },
            {
                "id": "r_b1",
                "body": "<<FILL role=rising words=40 beats='b'>>",
                "is_ending": False,
                "choices": [{"id": "c_b_end", "label": "End.", "target": "e_b"}],
            },
            {
                "id": "e_b",
                "body": "b done",
                "is_ending": True,
                "ending": {
                    "id": "end_b",
                    "kind": "success",
                    "valence": "positive",
                    "title": "B",
                },
            },
            {
                "id": "r_c1",
                "body": "<<FILL role=rising words=40 beats='c'>>",
                "is_ending": False,
                "choices": [{"id": "c_c_mid", "label": "On.", "target": "r_c2"}],
            },
            {
                "id": "r_c2",
                "body": "<<FILL role=rising words=40 beats='c2'>>",
                "is_ending": False,
                "choices": [{"id": "c_c_end", "label": "End.", "target": "e_c"}],
            },
            {
                "id": "e_c",
                "body": "c done",
                "is_ending": True,
                "ending": {
                    "id": "end_c",
                    "kind": "success",
                    "valence": "positive",
                    "title": "C",
                },
            },
        ],
    }


def _prune_last_satisfying_fixture() -> dict[str, object]:
    """Return a 3-5 fixture where pruning the only success route strips the last win.

    Post-prune node count (8) and ending count (2) both clear their floors, so the
    isolated failure is the last-success/completion guard: only ``e_s`` is a
    satisfying ending and it sits in the pruned route.
    """
    nodes: list[dict[str, object]] = [
        {
            "id": "start",
            "body": "<<FILL role=setup words=40 beats='pick'>>",
            "is_ending": False,
            "choices": [
                {"id": "c_s", "label": "S.", "target": "s1"},
                {"id": "c_d", "label": "D.", "target": "d1"},
                {"id": "c_e", "label": "E.", "target": "e1"},
            ],
        },
        {
            "id": "s1",
            "body": "<<FILL role=rising words=40 beats='s'>>",
            "is_ending": False,
            "choices": [{"id": "c_s_end", "label": "End.", "target": "e_s"}],
        },
        {
            "id": "e_s",
            "body": "won",
            "is_ending": True,
            "ending": {
                "id": "end_s",
                "kind": "success",
                "valence": "positive",
                "title": "Win",
            },
        },
        {
            "id": "d1",
            "body": "<<FILL role=rising words=40 beats='d'>>",
            "is_ending": False,
            "choices": [{"id": "c_d_end", "label": "End.", "target": "e_d"}],
        },
        {
            "id": "e_d",
            "body": "found",
            "is_ending": True,
            "ending": {
                "id": "end_d",
                "kind": "discovery",
                "valence": "positive",
                "title": "Find",
            },
        },
    ]
    # A 5-node linear setback route keeps the post-prune count at the floor.
    for index in range(1, 5):
        target = f"e{index + 1}" if index < 4 else "e_f"
        nodes.append(
            {
                "id": f"e{index}",
                "body": f"<<FILL role=rising words=40 beats='e{index}'>>",
                "is_ending": False,
                "choices": [{"id": f"c_e{index}", "label": "On.", "target": target}],
            }
        )
    nodes.append(
        {
            "id": "e_f",
            "body": "lost",
            "is_ending": True,
            "ending": {
                "id": "end_f",
                "kind": "setback",
                "valence": "negative",
                "title": "Setback",
            },
        }
    )
    return {
        "start_node": "start",
        "metadata": {
            "age_band": "3-5",
            "tier": 1,
            "topology": "time_cave",
            "ending_count": 3,
        },
        "variables": [],
        "nodes": nodes,
    }


def _fake_donor(*, effect: bool = False, size: int = 3) -> dict[str, object]:
    """Return a same-band (8-11) fake donor with a linear ``gr`` subtree.

    Args:
        effect: When True, ``gr`` carries an ``on_enter`` effect so the region is
            not state-free (exercises the graft cleanliness rejection).
        size: The number of nodes in the ``gr`` region (a linear chain plus a
            discovery ending), used to exceed the host envelope maximum.
    """
    nodes: list[dict[str, object]] = []
    root: dict[str, object] = {
        "id": "gr",
        "body": "<<FILL role=setup words=40 beats='graft root'>>",
        "is_ending": False,
        "choices": [{"id": "c_gr", "label": "On.", "target": "g1"}],
    }
    if effect:
        root["on_enter"] = [{"op": "set", "var": "flag", "value": True}]
    nodes.append(root)
    for index in range(1, size - 1):
        target = f"g{index + 1}" if index < size - 2 else "e_g"
        nodes.append(
            {
                "id": f"g{index}",
                "body": f"<<FILL role=rising words=40 beats='g{index}'>>",
                "is_ending": False,
                "choices": [{"id": f"c_g{index}", "label": "On.", "target": target}],
            }
        )
    nodes.append(
        {
            "id": "e_g",
            "body": "graft end",
            "is_ending": True,
            "ending": {
                "id": "end_g",
                "kind": "discovery",
                "valence": "positive",
                "title": "Grafted Find",
            },
        }
    )
    return {
        "start_node": "gr",
        "metadata": {
            "age_band": "8-11",
            "tier": 1,
            "topology": "time_cave",
            "ending_count": 1,
        },
        "variables": [],
        "nodes": nodes,
    }


def _resolver_for(donor: dict[str, object]) -> M3PruneGraft:
    """Return an M3 operator whose donor resolver serves ``donor`` for any slug."""
    return M3PruneGraft(donor_resolver=lambda _slug: donor)


# --- Registration and mode routing ---


@pytest.mark.unit
def test_m3_is_registered_under_its_op_id() -> None:
    """The M3 singleton is registered and exposes its stable op id."""
    assert M3.op_id == M3_OP_ID == "M3"


@pytest.mark.unit
def test_m3_requires_a_known_mode() -> None:
    """A missing or unknown mode fails preconditions and apply."""
    host = _host()
    report = M3.preconditions(host, OpParams.of())
    assert report.satisfied is False
    assert any("mode" in reason for reason in report.failures)
    with pytest.raises(ValidationError):
        M3.apply(host, OpParams.of(mode="nonsense"), random.Random(0))


# --- Prune ---


@pytest.mark.unit
def test_m3_prune_accepted_output_passes_gate_and_recounts() -> None:
    """An accepted prune clears the gate, drops the subtree, and recounts endings."""
    host = _host()
    result = M3.apply(
        host, OpParams.of(mode="prune", choice=_PRUNE_CHOICE), random.Random(0)
    )
    candidate = result.candidate
    # Prune needs no re-guidance (design 4.4).
    assert result.reguide == ()
    assert run_gate(candidate).blocked is False
    # The 2-node crystal subtree and its edge are gone.
    assert len(_node_ids(candidate)) == len(_node_ids(host)) - 2
    assert _ending_count(candidate) == _ending_count(host) - 1
    candidate_meta = cast("dict[str, object]", candidate["metadata"])
    assert candidate_meta["ending_count"] == _ending_count(candidate)


@pytest.mark.unit
def test_m3_prune_notes_are_the_prune_note_plus_the_ratio_advisory() -> None:
    """The prune note is always emitted; the ratio advisory rides along when out of band.

    ``MutationResult.notes`` is ``tuple[str, ...]``, so every entry must be a
    real note string: a padded ``None`` placeholder would corrupt the audit
    trail. This pins the caller's note composition against changes to the
    ending-ratio advisory helper's return shape.
    """
    result = M3.apply(
        _host(), OpParams.of(mode="prune", choice=_PRUNE_CHOICE), random.Random(0)
    )
    assert all(isinstance(note, str) for note in result.notes)
    assert len(result.notes) == 2
    assert result.notes[0].startswith("M3 prune: removed subtree 'la_crystal_take'")
    # The host fixture's post-prune ratio (0.24) sits above the ADR-011 band.
    assert result.notes[1].startswith("advisory: post-prune ending ratio 0.24")


@pytest.mark.unit
def test_m3_prune_leaves_the_surviving_region_byte_identical() -> None:
    """Everything outside the pruned region is byte-identical (parent loses one choice)."""
    host = _host()
    result = M3.apply(
        host, OpParams.of(mode="prune", choice=_PRUNE_CHOICE), random.Random(0)
    )
    candidate = result.candidate
    before = _nodes_by_id(host)
    after = _nodes_by_id(candidate)
    removed = set(before) - set(after)
    # Only the closed subtree was removed (its root and its single ending node).
    assert removed == {"la_crystal_take", "la_crystal_out"}
    for node_id, node in after.items():
        if node_id == "la_grotto":
            continue  # the parent legitimately lost the pruned choice
        assert json.dumps(node, sort_keys=True) == json.dumps(
            before[node_id], sort_keys=True
        )
    # The parent kept every choice except the pruned one.
    parent_choice_ids = {
        cast("dict[str, object]", c)["id"]
        for c in cast("list[object]", after["la_grotto"]["choices"])
    }
    assert _PRUNE_CHOICE not in parent_choice_ids


@pytest.mark.unit
def test_m3_prune_below_envelope_minimum_is_discarded() -> None:
    """A prune dropping the node count below the cell minimum fails preconditions.

    Design 4.4: WS-5 treats the cell envelope as two-sided and blocking, even
    though L1-7 only WARNs below-min for cell budgets.
    """
    story = _prune_min_fixture()
    report = M3.preconditions(story, OpParams.of(mode="prune", choice="c_a"))
    assert report.satisfied is False
    assert any(
        "envelope" in reason or "minimum" in reason for reason in report.failures
    )
    with pytest.raises(ValidationError):
        M3.apply(story, OpParams.of(mode="prune", choice="c_a"), random.Random(0))


@pytest.mark.unit
def test_m3_prune_removing_last_satisfying_ending_is_discarded() -> None:
    """A prune that removes the only success/completion ending is discarded (PL-17).

    Safety property (design 12 D4): pruning can never remove the last satisfying
    ending.
    """
    story = _prune_last_satisfying_fixture()
    report = M3.preconditions(story, OpParams.of(mode="prune", choice="c_s"))
    assert report.satisfied is False
    assert any(
        "success/completion" in reason or "last" in reason for reason in report.failures
    )
    with pytest.raises(ValidationError):
        M3.apply(story, OpParams.of(mode="prune", choice="c_s"), random.Random(0))


@pytest.mark.unit
def test_m3_prune_is_deterministic_per_choice_and_per_seed() -> None:
    """Explicit and rng-selected prunes are byte-reproducible."""
    host = _host()
    a = M3.apply(
        host, OpParams.of(mode="prune", choice=_PRUNE_CHOICE), random.Random(0)
    ).candidate
    b = M3.apply(
        host, OpParams.of(mode="prune", choice=_PRUNE_CHOICE), random.Random(9)
    ).candidate
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    # The rng fallback (no explicit choice) is reproducible for a fixed seed.
    c = M3.apply(host, OpParams.of(mode="prune"), random.Random(3)).candidate
    d = M3.apply(host, OpParams.of(mode="prune"), random.Random(3)).candidate
    assert json.dumps(c, sort_keys=True) == json.dumps(d, sort_keys=True)


@pytest.mark.unit
def test_m3_prune_is_promotable_through_the_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An accepted prune has no re-guidance, so the unchanged harness promotes it.

    D7 change: the prune on this small synthetic ``_host()`` fixture is near-
    isomorphic to its parent (its feature-vector distance is below the calibrated
    TAU_STRUCT), so with no re-guidance outstanding it would now be discarded by
    the stage-3 structural anti-clone floor. This test pins the ORIGINAL mechanic
    -- a prune emits no re-guidance, so the promotable path is reached without a
    hold -- so the anti-clone floor is stubbed to pass, isolating the re-guidance
    behaviour from the diversity floor (covered by test_mutation_floors.py). No
    safety assertion is weakened: the gate and cell stages run unchanged.
    """
    monkeypatch.setattr(
        "cyo_adventure.mutation.acceptance.structural_floor_reason",
        _floor_always_passes,
    )
    host = _host()
    result = run_acceptance(
        M3,
        host,
        OpParams.of(mode="prune", choice=_PRUNE_CHOICE),
        seed=0,
        parent_slug="cave",
    )
    assert result.discarded_at_stage is None
    assert result.reguide_outstanding == 0
    assert result.promotable is True


# --- Graft ---


@pytest.mark.unit
def test_m3_graft_accepted_output_passes_gate_with_renamed_ids() -> None:
    """A same-band graft clears the gate and renames every donor id collision-free.

    Exercises real donor id renaming (design 4.4): the grafted node/choice/ending
    ids are prefixed ``m<k>_`` and disjoint from the host namespace.
    """
    host = _host()
    host_namespace = host_id_namespace(host)
    result = M3.apply(
        host,
        OpParams.of(
            mode="graft",
            donor=_DONOR_SLUG,
            subtree_root=_DONOR_SUBTREE,
            host_decision=_HOST_DECISION,
        ),
        random.Random(0),
    )
    candidate = result.candidate
    assert run_gate(candidate).blocked is False
    new_ids = _node_ids(candidate) - _node_ids(host)
    assert new_ids  # the graft added nodes
    for node_id in new_ids:
        assert re.match(r"^m\d+_", node_id)
        assert node_id not in host_namespace
    # The seam re-guidance: a new choice label and the graft root's entry beats.
    targets = {item.target for item in result.reguide}
    assert targets == {ReguideTarget.CHOICE, ReguideTarget.NODE}
    assert len(result.reguide) == 2


@pytest.mark.unit
def test_m3_graft_is_held_through_the_harness() -> None:
    """An accepted graft carries unresolved re-guidance, so the harness holds it."""
    host = _host()
    result = run_acceptance(
        M3,
        host,
        OpParams.of(
            mode="graft",
            donor=_DONOR_SLUG,
            subtree_root=_DONOR_SUBTREE,
            host_decision=_HOST_DECISION,
        ),
        seed=0,
        parent_slug="cave",
    )
    assert result.discarded_at_stage is None
    assert result.held is True
    assert result.promotable is False
    assert result.reguide_outstanding == 2


@pytest.mark.unit
def test_m3_graft_from_a_different_band_donor_is_rejected() -> None:
    """A cross-band donor is rejected at preconditions (no cross-band content ingress).

    Safety property (design 12 D4): the same-band donor rule is what keeps every
    grafted ending kind band-legal and out-of-band content out of the host.
    """
    host = _host()  # 8-11
    report = M3.preconditions(
        host,
        OpParams.of(
            mode="graft",
            donor="the-night-market",  # a real 5-8 skeleton
            subtree_root="f_paper",
            host_decision=_HOST_DECISION,
        ),
    )
    assert report.satisfied is False
    assert any("band" in reason for reason in report.failures)


@pytest.mark.unit
def test_m3_graft_past_three_choices_is_discarded() -> None:
    """Grafting onto a 3-choice decision (n_start) exceeds the 2-3 window (stage 0)."""
    host = _host()
    report = M3.preconditions(
        host,
        OpParams.of(
            mode="graft",
            donor=_DONOR_SLUG,
            subtree_root=_DONOR_SUBTREE,
            host_decision="n_start",  # already 3 choices
        ),
    )
    assert report.satisfied is False
    assert any("2-3" in reason or "window" in reason for reason in report.failures)


@pytest.mark.unit
def test_m3_graft_above_envelope_maximum_is_discarded() -> None:
    """A graft that would exceed the cell node maximum is discarded (L1-7, two-sided)."""
    host = _host()  # 64 nodes, 8-11 short (max 100)
    op = _resolver_for(_fake_donor(size=41))  # 64 + 41 = 105 > 100
    report = op.preconditions(
        host,
        OpParams.of(
            mode="graft", donor="big", subtree_root="gr", host_decision=_HOST_DECISION
        ),
    )
    assert report.satisfied is False
    assert any("maximum" in reason for reason in report.failures)


@pytest.mark.unit
def test_m3_graft_of_a_stateful_region_is_rejected() -> None:
    """A donor subtree carrying an effect is rejected: v1 grafts state-free regions only.

    Safety property (design 4.4): variable/effect/condition regions are deferred
    to the composer; the operator refuses them belt-and-braces before the gate.
    """
    host = _host()
    op = _resolver_for(_fake_donor(effect=True))
    report = op.preconditions(
        host,
        OpParams.of(
            mode="graft",
            donor="stateful",
            subtree_root="gr",
            host_decision=_HOST_DECISION,
        ),
    )
    assert report.satisfied is False
    assert any(
        "state-free" in reason or "on_enter" in reason for reason in report.failures
    )


@pytest.mark.unit
def test_m3_graft_is_deterministic_for_explicit_params() -> None:
    """The same graft params reproduce a byte-identical candidate."""
    host = _host()
    params = OpParams.of(
        mode="graft",
        donor=_DONOR_SLUG,
        subtree_root=_DONOR_SUBTREE,
        host_decision=_HOST_DECISION,
    )
    a = M3.apply(host, params, random.Random(0)).candidate
    b = M3.apply(host, params, random.Random(123)).candidate  # rng unused for graft
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.unit
def test_m3_graft_preserves_the_bands_forbidden_kind_guarantee() -> None:
    """A same-band graft adds only ending kinds the host band already permits (PL-15)."""
    host = _host()
    result = M3.apply(
        host,
        OpParams.of(
            mode="graft",
            donor=_DONOR_SLUG,
            subtree_root=_DONOR_SUBTREE,
            host_decision=_HOST_DECISION,
        ),
        random.Random(0),
    )
    # 8-11 forbids `death`; a same-band donor's endings are band-legal, so none
    # can appear in the graft. The gate re-proves PL-15 (not blocked).
    assert "death" not in _ending_kinds(result.candidate)
    assert run_gate(result.candidate).blocked is False


# --- Contract merge (dry; tested against WS-2 models and load_contract_for) ---


def _load_contract(slug: str) -> ThemeContract:
    """Load a real catalog theme contract by slug from the 8-11 band."""
    path = _SKELETONS_ROOT / "8-11" / f"{slug}.contract.json"
    return ThemeContract.model_validate_json(path.read_text(encoding="utf-8"))


def _graft_index(host: Mapping[str, object], mutant: Mapping[str, object]) -> int:
    """Return the m<k>_ index the graft used, read from a grafted node id."""
    new_ids = _node_ids(mutant) - _node_ids(host)
    match = re.match(r"^m(\d+)_", sorted(new_ids)[0])
    assert match is not None
    return int(match.group(1))


@pytest.mark.unit
def test_m3_graft_contract_merge_imports_renamed_donor_slots() -> None:
    """Grafted slots are imported under M<k>_ ids with constraints and bindings kept.

    Verifies the design 4.4 contract merge against the real WS-2 models and the
    ``load_contract_for`` token-set equality rule (full acceptance is D7).
    """
    host = _host()
    host_contract = _load_contract("the-cave-of-echoes")
    donor = _load(_SKELETONS_ROOT / "8-11" / f"{_DONOR_SLUG}.json")
    donor_contract = _load_contract(_DONOR_SLUG)

    result = M3.apply(
        host,
        OpParams.of(
            mode="graft",
            donor=_DONOR_SLUG,
            subtree_root=_DONOR_SUBTREE,
            host_decision=_HOST_DECISION,
        ),
        random.Random(0),
    )
    mutant = result.candidate
    k = _graft_index(host, mutant)
    referenced = region_referenced_slots(
        cast("list[Mapping[str, object]]", _donor_region_nodes(donor, _DONOR_SUBTREE))
    )
    merged = merge_graft_contract(
        host_contract, donor_contract, referenced, k, "cave-graft-mutant"
    )

    donor_by_id = {slot.id: slot for slot in donor_contract.slots}
    for slot_id in referenced:
        imported_id = graft_slot_id(slot_id, k)
        imported = next(slot for slot in merged.slots if slot.id == imported_id)
        original = donor_by_id[slot_id]
        # SlotSpec constraints copied verbatim (max_words + forbid denylist).
        assert imported.constraints.max_words == original.constraints.max_words
        assert list(imported.constraints.forbid) == list(original.constraints.forbid)
        # default_binding entries carried over under the renamed id.
        assert (
            merged.default_binding[imported_id]
            == donor_contract.default_binding[slot_id]
        )

    # The load_contract_for token-set equality rule holds against the mutant.
    with tempfile.TemporaryDirectory() as tmp:
        skeleton_path = Path(tmp) / "cave-graft-mutant.json"
        skeleton_path.write_text(json.dumps(mutant), encoding="utf-8")
        (Path(tmp) / "cave-graft-mutant.contract.json").write_text(
            merged.model_dump_json(), encoding="utf-8"
        )
        loaded = load_contract_for(skeleton_path, mutant)
    assert loaded is not None
    assert slot_ids(loaded) == {slot.id for slot in merged.slots}


@pytest.mark.unit
def test_m3_prune_contract_drops_only_unreferenced_slots() -> None:
    """A prune drops only slots no surviving surface references (contract merge)."""
    host = _host()
    host_contract = _load_contract("the-cave-of-echoes")
    result = M3.apply(
        host, OpParams.of(mode="prune", choice=_PRUNE_CHOICE), random.Random(0)
    )
    mutant = result.candidate

    surviving = region_referenced_slots(
        cast("list[Mapping[str, object]]", list(_nodes_by_id(mutant).values()))
    )
    pruned = prune_contract(host_contract, surviving, "cave-prune-mutant")
    # Some slot(s) referenced only by the removed crystal subtree are dropped.
    assert len(pruned.slots) < len(host_contract.slots)
    assert {slot.id for slot in pruned.slots} == surviving & slot_ids(host_contract)

    with tempfile.TemporaryDirectory() as tmp:
        skeleton_path = Path(tmp) / "cave-prune-mutant.json"
        skeleton_path.write_text(json.dumps(mutant), encoding="utf-8")
        (Path(tmp) / "cave-prune-mutant.contract.json").write_text(
            pruned.model_dump_json(), encoding="utf-8"
        )
        loaded = load_contract_for(skeleton_path, mutant)
    assert loaded is not None


# --- Catalog + Tier-1 restriction ---


@pytest.mark.unit
def test_m3_rejects_a_tier2_parent() -> None:
    """M3 (D4) refuses a Tier-2 parent (variables present)."""
    host = _host()
    cast("dict[str, object]", host["metadata"])["tier"] = 2
    host["variables"] = [{"name": "x", "type": "int", "initial": 0}]
    report = M3.preconditions(host, OpParams.of(mode="prune", choice=_PRUNE_CHOICE))
    assert report.satisfied is False
    assert any("Tier-1" in reason for reason in report.failures)


@pytest.mark.unit
def test_m3_harness_never_promotes_a_blocked_candidate() -> None:
    """The unchanged harness discards a cross-band graft at preconditions (never promoted)."""
    host = _host()
    result = run_acceptance(
        M3,
        host,
        OpParams.of(
            mode="graft",
            donor="the-night-market",
            subtree_root="f_paper",
            host_decision=_HOST_DECISION,
        ),
        seed=0,
        parent_slug="cave",
    )
    assert result.promotable is False
    assert result.discarded_at_stage is not None
    assert result.candidate is None
