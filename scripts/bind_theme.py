"""Offline deterministic validate+render for a parameterized skeleton.

Usage::

    uv run python scripts/bind_theme.py <skeleton.json> \\
        --bindings <bindings.json> --out-bound <path> [--out-binding <path>]

Makes no LLM call: this script is the deterministic validate-and-render half
of the WS-2 bind flow (design section 5.3, 8.1 step 7). The caller (an
authoring agent, or a human curating a migration sample fill) supplies a
flat ``{slot_id: value}`` bindings map; this script loads the skeleton's
theme contract, runs the same fail-closed
``validate_slot_bindings`` -> ``render_bound_skeleton`` sequence the worker
uses at fill time, and writes the bound skeleton.

If ``--bindings`` is omitted, the contract's ``default_binding`` is used,
which renders the original theme (the reference fill).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import (
    contract_path_for,
    load_contract_for,
    render_bound_skeleton,
)
from cyo_adventure.validator.slots import validate_slot_bindings

# #ASSUME: security: bind_theme.py is invoked by the cyo-author LLM skill
# (.claude/skills/cyo-author/SKILL.md) as well as directly by a human curating
# a migration sample fill (module docstring above); a fixed containment base
# (repo root or cwd, the generation/import_cli.py::_load_blob idiom) is
# deliberately NOT applied to its path args: tests/unit/test_bind_theme.py
# exercises every one of skeleton/--bindings/--out-bound/--out-binding
# against pytest tmp_path fixtures well outside the repo tree with no chdir,
# proving arbitrary-location paths are legitimate, exercised behavior that
# containment would reject. No privilege boundary is crossed either way: the
# operator (or an LLM agent acting on the operator's own machine) already has
# full filesystem access. `.resolve()` is applied to every path arg in
# main() regardless, so symlinks and `..`/`.` segments are normalized before
# any read or write; this canonicalization removes path ambiguity but does
# not by itself constrain where a path resolves to (that is the deliberate
# no-containment tradeoff above), so it is not on its own a CWE-23 defense.
# #VERIFY: any future change reintroducing a fixed base must re-run
# test_bind_theme.py first; a rejection there means real behavior broke.


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


def _load_bindings(path: Path) -> dict[str, str]:
    """Load a flat ``{slot_id: value}`` bindings map from ``path``.

    Args:
        path: File path to read.

    Returns:
        The decoded bindings map.

    Raises:
        OSError: If the file cannot be read.
        json.JSONDecodeError: If the file is not valid JSON.
        ValueError: If the top-level JSON value is not an object of strings.
    """
    raw = _load_json_object(path)
    if not all(isinstance(value, str) for value in raw.values()):
        msg = f"bindings file {path} must be a flat object of string values"
        raise ValueError(msg)
    return cast("dict[str, str]", raw)


def main(argv: list[str] | None = None) -> int:
    """Validate and render one bindings map against a parameterized skeleton.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        Exit code: 0 when the bound skeleton is written, 1 on any load
        error, a missing contract, or a rejected (violating) binding. No
        output file is written on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", help="Path to the parameterized skeleton JSON.")
    parser.add_argument(
        "--bindings",
        help=(
            "Path to a JSON {slot_id: value} map. Defaults to the contract's "
            "default_binding when omitted."
        ),
    )
    parser.add_argument(
        "--out-bound", required=True, help="Path to write the rendered bound skeleton."
    )
    parser.add_argument(
        "--out-binding", help="Optional path to echo the binding JSON actually used."
    )
    args = parser.parse_args(argv)

    # argparse.Namespace attribute access is untyped (Any) in the stdlib
    # stubs regardless of the parser's declared arguments; this is the
    # standard, unavoidable boundary, not a loosened check on our own code.
    skeleton_arg: str = args.skeleton  # pyright: ignore[reportAny]
    bindings_arg: str | None = args.bindings  # pyright: ignore[reportAny]
    out_bound_arg: str = args.out_bound  # pyright: ignore[reportAny]
    out_binding_arg: str | None = args.out_binding  # pyright: ignore[reportAny]

    # CWE-23 hardening (Snyk python/PT): canonicalize every path arg with
    # .resolve() before it touches the filesystem. See the module-level
    # ASSUME comment above for why containment is not applied here.
    skeleton_path = Path(skeleton_arg).resolve()
    out_bound_path = Path(out_bound_arg).resolve()
    out_binding_path = (
        Path(out_binding_arg).resolve() if out_binding_arg is not None else None
    )

    try:
        skeleton = _load_json_object(skeleton_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: cannot load skeleton {skeleton_path}: {exc}\n")
        return 1

    try:
        contract = load_contract_for(skeleton_path, skeleton)
    except ValidationError as exc:
        sys.stderr.write(f"error: cannot load theme contract: {exc}\n")
        return 1
    if contract is None:
        no_contract_msg = (
            f"error: '{skeleton_path}' has no theme contract sidecar "
            f"({contract_path_for(skeleton_path)}); bind_theme.py only "
            "applies to parameterized skeletons\n"
        )
        sys.stderr.write(no_contract_msg)
        return 1

    if bindings_arg is not None:
        bindings_path = Path(bindings_arg).resolve()
        try:
            bindings = _load_bindings(bindings_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            sys.stderr.write(f"error: cannot load bindings {bindings_path}: {exc}\n")
            return 1
        source = str(bindings_path)
    else:
        bindings = dict(contract.default_binding)
        source = "contract.default_binding"

    # #CRITICAL: security: fail closed on any contract violation before ever
    # rendering. This mirrors the worker's bind -> validate -> render order
    # (design section 4): an unvalidated binding is never passed to
    # render_bound_skeleton, so a violating theme never reaches the (offline
    # equivalent of the) fill step.
    # #VERIFY: test_bind_theme.py's violating-bindings test asserts no output
    # file is written.
    violations = validate_slot_bindings(contract, bindings)
    if violations:
        for violation in violations:
            violation_msg = (
                f"FAIL slot={violation.slot_id or '-'} rule={violation.rule} "
                f"{violation.message}\n"
            )
            sys.stderr.write(violation_msg)
        sys.stderr.write(
            f"binding rejected: {len(violations)} violation(s); no output written\n"
        )
        return 1

    try:
        bound = render_bound_skeleton(skeleton, bindings)
    except ValidationError as exc:
        sys.stderr.write(f"error: render_bound_skeleton failed: {exc}\n")
        return 1

    out_bound_path.write_text(json.dumps(bound, indent=2) + "\n", encoding="utf-8")
    print(f"bound {skeleton_path} using bindings from {source}")
    print(f"wrote bound skeleton to {out_bound_path}")

    if out_binding_path is not None:
        out_binding_path.write_text(
            json.dumps(bindings, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote binding to {out_binding_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
