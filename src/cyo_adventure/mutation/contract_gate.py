"""In-memory contract acceptance for a mutated parameterized skeleton (design 4.7).

Stage 4 of the section-6 acceptance table. For a mutant of a parameterized parent
the mutated ``.contract.json`` must pass the same deterministic checks
``scripts/check_theme_contract.py`` runs, end to end: the skeleton gates clean,
the contract's slot id set matches the skeleton's ``{SLOT}`` tokens, every
declared ``forbid`` bundle id is known, the ``default_binding`` passes
``validate_slot_bindings`` (INCLUDING the band-mandatory denylist floor), a
synthesized floor-violating binding is rejected, and ``render_bound_skeleton``
succeeds with no residual tokens.

This module calls the underlying library functions directly
(``validate_slot_bindings``, ``render_bound_skeleton``, ``run_gate``,
``band_mandatory_bundles``) against the in-memory ``(candidate, contract)`` pair
rather than shelling out to the script or touching disk, so it stays inside the
``mutation`` layer and never inverts into ``scripts/``. The check ladder mirrors
``check_theme_contract.py`` checks 1-6, including the ``_pick_probe`` selection.

Reject-only (design CR-2): :func:`contract_acceptance_reason` returns a discard
reason or ``None``; it never admits a candidate or weakens a floor. The
band-mandatory floor is unioned inside ``validate_slot_bindings`` regardless of
contract content, so a mutated contract can never weaken it (CR-4).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import render_bound_skeleton
from cyo_adventure.storybook.theme_contract import (
    SLOT_TOKEN_RE,
    ThemeContract,
    slot_ids,
)
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.slots import (
    BUNDLE_IDS,
    BUNDLE_PROBES,
    band_mandatory_bundles,
    validate_slot_bindings,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.storybook.theme_contract import SlotSpec

# The FILL directive parse, matching ``generation/binding._FILL_RE`` verbatim so
# the beats surface is scanned identically to the render path.
_FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)


# dict[str, object] / list[str] have no forward reference to defer, so there is
# no runtime cost to not quoting them in these cast() calls (see
# review_surface.py for the same pattern); left unquoted here so the type
# expression is not a duplicated string literal (S1192) across the module.
def _body_beats_tokens(node: Mapping[str, object]) -> frozenset[str]:
    """Return the slot tokens in a node's ``<<FILL ...>>`` beats segment.

    Args:
        node: One skeleton node to scan.

    Returns:
        frozenset[str]: The slot ids referenced in the beats segment, or an
            empty set when the node has no matching body.
    """
    body = node.get("body")
    if not isinstance(body, str):
        return frozenset()
    match = _FILL_RE.match(body)
    if match is None:
        return frozenset()
    return frozenset(cast(list[str], SLOT_TOKEN_RE.findall(match.group(3))))  # noqa: TC006


def _ending_title_tokens(node: Mapping[str, object]) -> frozenset[str]:
    """Return the slot tokens in a node's ending title, when present.

    Args:
        node: One skeleton node to scan.

    Returns:
        frozenset[str]: The slot ids referenced in the ending title, or an
            empty set when the node has no ending title.
    """
    ending = node.get("ending")
    if not isinstance(ending, dict):
        return frozenset()
    title = cast(dict[str, object], ending).get("title")  # noqa: TC006
    if not isinstance(title, str):
        return frozenset()
    return frozenset(cast(list[str], SLOT_TOKEN_RE.findall(title)))  # noqa: TC006


def _choice_label_tokens(node: Mapping[str, object]) -> frozenset[str]:
    """Return the slot tokens in a node's choice labels.

    Args:
        node: One skeleton node to scan.

    Returns:
        frozenset[str]: The slot ids referenced across the node's choices.
    """
    choices = node.get("choices")
    if not isinstance(choices, list):
        return frozenset()
    tokens: set[str] = set()
    for raw_choice in cast("list[object]", choices):
        if not isinstance(raw_choice, dict):
            continue
        label = cast(dict[str, object], raw_choice).get("label")  # noqa: TC006
        if isinstance(label, str):
            tokens.update(cast(list[str], SLOT_TOKEN_RE.findall(label)))  # noqa: TC006
    return frozenset(tokens)


def _slotted_surface_tokens(skeleton: Mapping[str, object]) -> frozenset[str]:
    """Return every ``{SLOT}`` token in a skeleton's three slotted surfaces.

    The three surfaces are exactly the ADR-019 legal homes for a slot token: the
    ``beats='...'`` segment of a ``<<FILL ...>>`` node body, an ending title, and
    a choice label. Reimplements ``generation.binding._slotted_surface_tokens``
    (a private helper) here so the mutation layer holds no cross-module private
    import.

    Args:
        skeleton: The raw skeleton dict to scan.

    Returns:
        frozenset[str]: The slot ids referenced in those three surfaces.
    """
    nodes = skeleton.get("nodes")
    if not isinstance(nodes, list):
        return frozenset()
    tokens: set[str] = set()
    for raw_node in cast("list[object]", nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast(dict[str, object], raw_node)  # noqa: TC006
        tokens |= _body_beats_tokens(node)
        tokens |= _ending_title_tokens(node)
        tokens |= _choice_label_tokens(node)
    return frozenset(tokens)


def _pick_probe(contract: ThemeContract) -> tuple[SlotSpec, str] | None:
    """Choose the ``(slot, bundle)`` pair that proves the contract's floor bites.

    Mirrors ``scripts.check_theme_contract._pick_probe`` (design section 8.3):
    prefer a ``*_GATE`` slot probed with ``lethal``; else the band-mandatory floor
    probed on the first slot; else a slot's own declared ``forbid`` bundle; else
    None (a legitimately unconstrained mature-band reskin, check skipped).

    Args:
        contract: The mutated theme contract under test.

    Returns:
        tuple[SlotSpec, str] | None: The ``(slot, bundle_id)`` to probe, or None.
    """
    gate_slots = sorted(
        (slot for slot in contract.slots if slot.id.endswith("_GATE")),
        key=lambda slot: slot.id,
    )
    if gate_slots:
        return gate_slots[0], "lethal"
    floor = band_mandatory_bundles(contract.age_band)
    if floor:
        bundle = "lethal" if "lethal" in floor else min(floor)
        return contract.slots[0], bundle
    for slot in contract.slots:
        declared = sorted(set(slot.constraints.forbid) & BUNDLE_IDS)
        if declared:
            return slot, declared[0]
    return None


# One cohesive reject-only check ladder, one reason each (PLR0911).
def contract_acceptance_reason(  # noqa: PLR0911
    candidate: Mapping[str, object], contract: ThemeContract
) -> str | None:
    """Return why the mutated ``(candidate, contract)`` pair fails stage 4, or None.

    Runs ``check_theme_contract``'s six deterministic checks in memory against the
    mutated contract. Reject-only: the first failing check's reason is returned;
    a fully-passing pair returns None.

    Args:
        candidate: The mutated, gate-passing skeleton shell (FILL intact).
        contract: The mutated theme contract for the candidate.

    Returns:
        str | None: A discard reason on the first failing check, else None.
    """
    # #CRITICAL: security: a mutated contract can never weaken the band-mandatory
    # denylist floor. ``validate_slot_bindings`` unions ``band_mandatory_bundles``
    # regardless of contract content, so an emptied/weakened ``forbid`` list still
    # fails a floor-violating binding (design CR-4). This is the load-bearing
    # children's-safety check for parameterized mutants.
    # #VERIFY: tests/unit/test_mutation_floors.py pins that a mutated contract with
    # a stripped ``forbid`` list still fails a floor-violating binding.
    if run_gate(candidate).blocked:
        return "stage 4: the mutated skeleton itself is gate-blocked"

    declared = slot_ids(contract)
    actual = _slotted_surface_tokens(candidate)
    if declared != actual:
        return (
            f"stage 4: contract slot id set does not match the skeleton's tokens: "
            f"declared_but_absent={sorted(declared - actual)} "
            f"present_but_undeclared={sorted(actual - declared)}"
        )

    unknown = sorted(
        {
            bundle_id
            for slot in contract.slots
            for bundle_id in slot.constraints.forbid
            if bundle_id not in BUNDLE_IDS
        }
    )
    if unknown:
        return f"stage 4: contract declares unknown forbid bundle id(s) {unknown}"

    default_violations = validate_slot_bindings(
        contract, contract.default_binding, is_default=True
    )
    if default_violations:
        joined = "; ".join(f"{v.slot_id}:{v.rule}" for v in default_violations)
        return f"stage 4: default_binding fails its own contract: {joined}"

    probe = _pick_probe(contract)
    if probe is not None:
        target_slot, probe_bundle = probe
        probe_bindings = dict(contract.default_binding)
        probe_bindings[target_slot.id] = BUNDLE_PROBES[probe_bundle]
        probe_violations = validate_slot_bindings(contract, probe_bindings)
        bit = any(
            v.rule == f"forbid:{probe_bundle}" and v.slot_id == target_slot.id
            for v in probe_violations
        )
        if not bit:
            return (
                f"stage 4: contract constraints do not bite: a synthesized "
                f"{probe_bundle} binding on '{target_slot.id}' was not rejected "
                f"(design CR-4 band floor / denylist weakened)"
            )

    try:
        bound = render_bound_skeleton(dict(candidate), contract.default_binding)
    except ValidationError as exc:
        return f"stage 4: render_bound_skeleton(default_binding) failed: {exc}"
    residual = sorted(set(cast("list[str]", SLOT_TOKEN_RE.findall(json.dumps(bound)))))
    if residual:
        return f"stage 4: render left residual slot token(s) {residual}"
    return None
