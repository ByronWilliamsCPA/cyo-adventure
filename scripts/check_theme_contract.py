"""Per-skeleton WS-2 migration acceptance runner.

Usage::

    uv run python scripts/check_theme_contract.py <skeleton.json> \\
        [--fingerprint-manifest <path>]

Derives the sidecar contract path via
``cyo_adventure.generation.binding.contract_path_for`` and runs every
deterministic acceptance check from
``docs/planning/ws2-parameterized-catalog-design.md`` sections 8.4 and 9.3,
printing one PASS/FAIL line per check. Exits 0 only when every check passes.

Checks:

1. ``run_gate(skeleton).blocked is False``: the parameterized skeleton itself
   gates clean.
2. The contract loads and schema-validates
   (``ThemeContract.model_validate_json``), and
   ``load_contract_for(skeleton_path, skeleton)`` succeeds -- which also
   enforces that the skeleton's ``{SLOT}`` token set exactly matches the
   contract's declared slot id set.
3. Every ``forbid`` bundle id declared on any slot is a known bundle id
   (``cyo_adventure.validator.slots.BUNDLE_IDS``), rejecting a typo that
   would otherwise silently contribute zero terms to a slot's denylist.
4. ``validate_slot_bindings(contract, contract.default_binding) == []``: the
   original theme's own values pass its own contract.
5. The contract's constraints actually bite: a slot is overwritten with a
   value a denylist bundle must reject, and that ``forbid:<bundle>`` violation
   must fire. A ``_GATE`` slot is probed with ``lethal`` (a retreat gate must
   never render lethally, at any band); otherwise the band-mandatory floor,
   else a declared bundle, is probed, so a gate-less skeleton at a weak-floor
   band (e.g. 10-13) is not spuriously failed. A contract with no
   deterministic denylist and no band floor skips this check (checks 1/2/4/6
   still hold) rather than failing it. See :func:`_pick_probe`.
6. ``render_bound_skeleton(skeleton, contract.default_binding)`` succeeds
   (all four post-conditions hold), and the result carries zero residual
   ``{SLOT}`` tokens.

``--fingerprint-manifest`` optionally compares the skeleton's current
structural fingerprint against a stored pre-migration value (design section
9.3 check 2, the *original vs. parameterized* structural-identity check).
The manifest is a flat JSON object of ``{skeleton_slug: fingerprint}``, keyed
by ``contract.skeleton_slug`` once the contract has loaded. When omitted,
that comparison is skipped with a printed note; it is not counted as a
failure, since it is a wave-level bookkeeping aid, not a property this
script can derive from the skeleton alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.generation.binding import (
    contract_path_for,
    load_contract_for,
    render_bound_skeleton,
)
from cyo_adventure.storybook.theme_contract import SLOT_TOKEN_RE, ThemeContract
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.slots import (
    BUNDLE_IDS,
    BUNDLE_PROBES,
    band_mandatory_bundles,
    validate_slot_bindings,
)

if TYPE_CHECKING:
    from cyo_adventure.storybook.theme_contract import SlotSpec


def _load_json_object(path: Path) -> dict[str, object]:
    """Load and return a JSON object from ``path``.

    Args:
        path: File path to read.

    Returns:
        The decoded top-level JSON object.

    Raises:
        OSError: If the file cannot be read.
        json.JSONDecodeError: If the file is not valid JSON.
        ValueError: If the top-level JSON value is not an object.
    """
    data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(data, dict):
        msg = f"expected a JSON object in {path}"
        raise ValueError(msg)
    return cast("dict[str, object]", data)


def _report(label: str, name: str, *, passed: bool, detail: str = "") -> None:
    """Print one PASS/FAIL line in a consistent format.

    Args:
        label: The check's ordinal ("1".."6", matching this module's
            docstring) or "opt" for the optional fingerprint-manifest
            comparison, which is not one of the six numbered checks.
        name: A short human-readable check name.
        passed: Whether the check passed.
        detail: Optional extra detail, printed only when present.
    """
    status = "PASS" if passed else "FAIL"
    line = f"{status} {label}. {name}"
    if detail:
        line += f": {detail}"
    print(line)


def _pick_probe(contract: ThemeContract) -> tuple[SlotSpec, str] | None:
    """Choose the ``(slot, bundle)`` pair check 5 uses to prove constraints bite.

    Check 5 proves a contract's deterministic denylist actually rejects a bad
    value, not merely that it parses. The probe target is chosen so the check
    exercises a genuinely enforced constraint and never false-fails a correct
    contract:

    1. A ``*_GATE`` slot exists: probe it with ``lethal``. A commit-or-turn-back
       gate is a retreatable obstacle whose own ending is a non-lethal setback,
       so it must reject a lethal binding at every band (design section 8.3);
       a ``_GATE`` that forgot ``lethal`` is the misconfiguration this check
       exists to catch.
    2. Else the band-mandatory floor is non-empty: probe the first slot with a
       floor bundle (``lethal`` when the floor includes it, else the
       lexicographically first floor bundle). The floor is applied to every
       slot unconditionally, so this always exercises a real constraint. This
       is what lets a gate-less skeleton at a weak-floor band (e.g. 10-13,
       whose floor is only ``graphic``) prove its constraints bite without a
       spurious lethal probe on a slot that legitimately does not forbid it.
    3. Else some slot declares a ``forbid`` bundle: probe that slot with one of
       its declared bundles.
    4. Else the contract declares no deterministic denylist anywhere and its
       band has no floor (a legitimately unconstrained mature-band reskin):
       return ``None`` so check 5 is skipped, not failed.

    Args:
        contract: The theme contract under test.

    Returns:
        The ``(slot, bundle_id)`` to probe, or ``None`` when no deterministic
        denylist constraint exists to exercise.
    """
    gate_slots = sorted(
        (slot for slot in contract.slots if slot.id.endswith("_GATE")),
        key=lambda slot: slot.id,
    )
    if gate_slots:
        return gate_slots[0], "lethal"

    floor = band_mandatory_bundles(contract.age_band)
    if floor:
        bundle = "lethal" if "lethal" in floor else sorted(floor)[0]
        return contract.slots[0], bundle

    for slot in contract.slots:
        declared = sorted(set(slot.constraints.forbid) & BUNDLE_IDS)
        if declared:
            return slot, declared[0]

    return None


def main(argv: list[str] | None = None) -> int:
    """Run every migration acceptance check for one skeleton/contract pair.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        Exit code: 0 when every check passes, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", help="Path to the parameterized skeleton JSON.")
    parser.add_argument(
        "--fingerprint-manifest",
        help=(
            "Optional path to a JSON {skeleton_slug: fingerprint} manifest to "
            "compare the skeleton's current structural fingerprint against."
        ),
    )
    args = parser.parse_args(argv)

    # argparse.Namespace attribute access is untyped (Any) in the stdlib
    # stubs regardless of the parser's declared arguments; this is the
    # standard, unavoidable boundary, not a loosened check on our own code.
    skeleton_path = Path(args.skeleton)  # pyright: ignore[reportAny]
    fingerprint_manifest_arg: str | None = args.fingerprint_manifest  # pyright: ignore[reportAny]
    try:
        skeleton = _load_json_object(skeleton_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: cannot load skeleton {skeleton_path}: {exc}\n")
        return 1

    all_passed = True

    # --- Check 1: the skeleton itself gates clean -------------------------
    gate_result = run_gate(skeleton)
    ok = not gate_result.blocked
    all_passed &= ok
    detail = ""
    if not ok:
        detail = "; ".join(f.message for f in gate_result.report.errors)
    _report("1", "run_gate(skeleton) not blocked", passed=ok, detail=detail)

    # --- Optional manifest fingerprint comparison (not a pass/fail check) --
    if fingerprint_manifest_arg:
        manifest_path = Path(fingerprint_manifest_arg)
        try:
            manifest = _load_json_object(manifest_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            sys.stderr.write(
                f"error: cannot load fingerprint manifest {manifest_path}: {exc}\n"
            )
            return 1
        slug = skeleton_path.stem
        stored = manifest.get(slug)
        current = structure_fingerprint(skeleton)
        matches = stored == current
        all_passed &= matches
        _report(
            "opt",
            "structure_fingerprint matches the pre-migration manifest",
            passed=matches,
            detail="" if matches else f"stored={stored!r} current={current!r}",
        )
    else:
        note = (
            "note: --fingerprint-manifest not provided; skipping the "
            "pre-migration fingerprint comparison"
        )
        print(note)

    # --- Check 2: contract loads, schema-validates, and cross-checks ------
    contract_path = contract_path_for(skeleton_path)
    contract: ThemeContract | None = None
    if not contract_path.is_file():
        all_passed = False
        _report(
            "2",
            "contract loads and schema-validates",
            passed=False,
            detail=f"no sidecar contract at {contract_path}",
        )
    else:
        try:
            raw_text = contract_path.read_text(encoding="utf-8")
            _ = ThemeContract.model_validate_json(raw_text)
            contract = load_contract_for(skeleton_path, skeleton)
        except (OSError, PydanticValidationError, ValidationError) as exc:
            all_passed = False
            _report(
                "2",
                "contract loads and schema-validates",
                passed=False,
                detail=str(exc),
            )
        else:
            _report("2", "contract loads and schema-validates", passed=True)

    if contract is None:
        _report(
            "3",
            "declared forbid bundle ids are known",
            passed=False,
            detail="skipped: no contract",
        )
        _report(
            "4",
            "default_binding passes validate_slot_bindings",
            passed=False,
            detail="skipped: no contract",
        )
        _report(
            "5",
            "a synthesized lethal binding is rejected",
            passed=False,
            detail="skipped: no contract",
        )
        _report(
            "6",
            "render_bound_skeleton(default_binding) succeeds",
            passed=False,
            detail="skipped: no contract",
        )
        return 1

    # --- Check 3: every declared forbid bundle id is known -----------------
    unknown_bundles = sorted(
        {
            bundle_id
            for slot in contract.slots
            for bundle_id in slot.constraints.forbid
            if bundle_id not in BUNDLE_IDS
        }
    )
    ok = not unknown_bundles
    all_passed &= ok
    _report(
        "3",
        "declared forbid bundle ids are known",
        passed=ok,
        detail=f"unknown bundle id(s): {unknown_bundles}" if unknown_bundles else "",
    )

    # --- Check 4: the original theme passes its own contract ---------------
    # is_default=True: the default_binding IS the original theme, so its
    # identity terms are exactly what legacy_lexicon lists to block in NEW
    # bindings; exempt only that leak check here (every other constraint,
    # including the band-mandatory denylist floor, still applies).
    default_violations = validate_slot_bindings(
        contract, contract.default_binding, is_default=True
    )
    ok = not default_violations
    all_passed &= ok
    _report(
        "4",
        "default_binding passes validate_slot_bindings",
        passed=ok,
        detail="; ".join(f"{v.slot_id}:{v.rule}" for v in default_violations),
    )

    # --- Check 5: the contract's constraints actually bite ------------------
    probe = _pick_probe(contract)
    if probe is None:
        # No _GATE, no band floor, and no declared forbid bundle anywhere: a
        # legitimately unconstrained mature-band reskin with nothing
        # deterministic to exercise. Skipped, not failed (checks 1/2/4/6 still
        # guarantee structure, schema, self-consistency, and a clean render).
        _report(
            "5",
            "constraints bite (no deterministic denylist to probe)",
            passed=True,
            detail=(
                "skipped: contract declares no forbid bundles and its band has "
                "no mandatory floor"
            ),
        )
    else:
        target_slot, probe_bundle = probe
        probe_bindings = dict(contract.default_binding)
        probe_bindings[target_slot.id] = BUNDLE_PROBES[probe_bundle]
        probe_violations = validate_slot_bindings(contract, probe_bindings)
        ok = any(
            v.rule == f"forbid:{probe_bundle}" and v.slot_id == target_slot.id
            for v in probe_violations
        )
        all_passed &= ok
        fail_detail = (
            f"validate_slot_bindings did not flag forbid:{probe_bundle} on the"
            f" target slot"
        )
        _report(
            "5",
            f"a synthesized {probe_bundle} binding on '{target_slot.id}' is rejected",
            passed=ok,
            detail="" if ok else fail_detail,
        )

    # --- Check 6: default_binding renders cleanly ---------------------------
    try:
        bound = render_bound_skeleton(skeleton, contract.default_binding)
    except ValidationError as exc:
        all_passed = False
        _report(
            "6",
            "render_bound_skeleton(default_binding) succeeds",
            passed=False,
            detail=str(exc),
        )
    else:
        found: list[str] = SLOT_TOKEN_RE.findall(json.dumps(bound))
        residual = sorted(set(found))
        ok = not residual
        all_passed &= ok
        _report(
            "6",
            "render_bound_skeleton(default_binding) succeeds, no residual tokens",
            passed=ok,
            detail=f"residual token(s): {residual}" if residual else "",
        )

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
