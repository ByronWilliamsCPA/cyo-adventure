#!/usr/bin/env python3
"""Re-prove a promotion bundle (or touched ``skeletons/**`` files) from scratch.

WS-8 D4, the repo-enforcement half of the automation boundary (design 4.3 point
4, stage S7). This is the testable Python entry point the ``skeleton-promotion``
CI job calls on every PR that touches ``skeletons/**``. Given a promotion bundle
directory OR the set of skeleton files a PR changed, it independently re-proves,
from the files on disk and the live catalog, everything the flywheel claimed at
acceptance time, so a hand-tampered or stale bundle cannot ride an otherwise
green PR:

1. ``check_skeleton`` on the shell (the full blocking gate plus the offered-cell
   and production-envelope checks);
2. ``check_theme_contract`` on the shell when a ``<slug>.contract.json`` sidecar
   is present (the WS-2 migration acceptance checks);
3. the WS-5 anti-clone floor (``structural_floor_reason`` against the live
   in-cell catalog) for a shape-changed shell;
4. a ``verify_bundle``-equivalent lineage/hash validation: the recorded parent
   hash must equal the live parent's canonical content hash.

Every failing check contributes a reason; the process exits ``0`` only when every
shell passes every applicable check, non-zero otherwise. This never writes
anything and never merges, approves, or opens a PR: it is a read-only prover.

Usage::

    uv run python scripts/check_promotion_bundle.py --bundle out/mutations/<slug>
    uv run python scripts/check_promotion_bundle.py skeletons/8-11/<slug>.json ...

Exit codes:
    0 - every proven shell passed every applicable check.
    1 - at least one check failed (or an input could not be read).
    2 - argparse usage error.
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
from cyo_adventure.generation.skeleton import is_sidecar
from cyo_adventure.mutation.bundle import LineageV2, content_sha256, load_lineage
from cyo_adventure.mutation.floors import load_in_cell_catalog, structural_floor_reason

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKELETONS_ROOT = _REPO_ROOT / "skeletons"


def _ensure_repo_on_path() -> None:
    """Make the repository root importable so the sibling check scripts resolve."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))


def _run_check_skeleton(argv: list[str]) -> int:
    """Run ``scripts/check_skeleton.py`` in-process and return its exit code."""
    _ensure_repo_on_path()
    from scripts.check_skeleton import main as check_skeleton_main  # noqa: PLC0415

    return check_skeleton_main(argv)


def _run_check_theme_contract(argv: list[str]) -> int:
    """Run ``scripts/check_theme_contract.py`` in-process and return its exit code."""
    _ensure_repo_on_path()
    from scripts.check_theme_contract import (  # noqa: PLC0415
        main as check_theme_contract_main,
    )

    return check_theme_contract_main(argv)


def _load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON object document from disk.

    Args:
        path: The file to read.

    Returns:
        dict[str, object]: The decoded top-level object.

    Raises:
        OSError: If the file cannot be read.
        json.JSONDecodeError: If the content is not valid JSON.
        ValueError: If the top-level value is not an object.
    """
    data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(data, dict):
        msg = f"expected a JSON object in {path}"
        raise ValueError(msg)
    return cast("dict[str, object]", data)


def _find_parent_file(skeletons_root: Path, parent_slug: str) -> Path | None:
    """Return the parent skeleton file under the catalog root, or None when absent."""
    matches = sorted(skeletons_root.glob(f"*/{parent_slug}.json"))
    return matches[0] if matches else None


def _verify_parent_hash(lineage: LineageV2, skeletons_root: Path) -> str | None:
    """Return why the lineage parent hash fails to verify, or None when it matches.

    This is the ``verify_bundle`` staleness gate, restated for an explicit lineage
    record so it works both for a bundle directory and for a lineage sidecar that
    a PR placed beside its shell under ``skeletons/``. It applies to a ``mutation``
    record only: a ``fresh`` (WS-6) tree has no parent to go stale, and its
    acceptance-digest gate is ``verify_bundle``'s responsibility at the bundle
    level, so a parentless record yields no failure reason here.

    Args:
        lineage: The validated lineage record.
        skeletons_root: The catalog root the parent slug is resolved under.

    Returns:
        str | None: A failure reason, or None when the live parent's canonical
            content hash equals the recorded ``parent_sha256`` (or there is no
            parent to verify).
    """
    # #CRITICAL: data-integrity: a promotion PR could be raised from a bundle
    # whose parent skeleton changed on main after derivation; the acceptance
    # evidence would then describe a tree that no longer exists. This hash
    # comparison is the hard gate that catches it in CI (design 4.3, 9.2 #EDGE).
    # #VERIFY: the D4 CI-fixture tests assert a matching parent verifies and an
    # edited parent (and a missing parent) fail.
    parent_slug = lineage.parent_slug
    expected = lineage.parent_sha256
    if lineage.origin != "mutation" or parent_slug is None or expected is None:
        return None
    parent_path = _find_parent_file(skeletons_root, parent_slug)
    if parent_path is None:
        return (
            f"parent '{parent_slug}' not found under {skeletons_root}; "
            f"the bundle cannot be verified"
        )
    try:
        parent_document = _load_json_object(parent_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return f"parent '{parent_slug}' could not be read: {exc}"
    actual = content_sha256(parent_document)
    if actual != expected:
        return (
            f"parent hash mismatch for '{parent_slug}': the parent changed "
            f"since derivation (recorded {expected}, recomputed "
            f"{actual}); this bundle must not promote"
        )
    return None


def _floor_reason(
    shell_doc: Mapping[str, object], lineage: LineageV2, skeletons_root: Path
) -> str | None:
    """Return why the shell fails the WS-5 anti-clone floor, or None when it passes.

    The structural anti-clone floor applies to a graph-shape-changed shell: it must
    differ structurally from its parent (``>= TAU_STRUCT``) and clone no in-cell
    catalog sibling (``>= TAU_CELL``). A shape-unchanged shell (an M5 state-only
    mutant) is out of the structural floor's scope by construction, because its
    structural distance is ~0; its applicable gate is the state-signature floor,
    which ran at acceptance and is re-attested by the lineage/hash check plus the
    gate re-run rather than re-derived here. Such a shell yields no failure reason.

    Args:
        shell_doc: The shell (candidate) document.
        lineage: The validated lineage record (its parent slug is looked up live).
        skeletons_root: The catalog root the parent is resolved under.

    Returns:
        str | None: The floor's discard reason, or None when the floor passes (or
            does not apply).
    """
    parent_slug = lineage.parent_slug
    if parent_slug is None:
        # A parentless (fresh) tree has no parent-relative anti-clone floor: its
        # in-cell TAU_CELL clause runs at acceptance against the declared target
        # cell, not here. Not a failure.
        return None
    parent_path = _find_parent_file(skeletons_root, parent_slug)
    if parent_path is None:
        # The lineage/hash check already reports the missing parent; do not
        # double-count it here.
        return None
    try:
        parent_doc = _load_json_object(parent_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    # A structurally-broken shell (e.g. a tampered dangling reference) cannot be
    # fingerprinted; that is already reported by the check_skeleton failure, so the
    # floor is not evaluated on it rather than crashing the prover.
    try:
        same_shape = structure_fingerprint(shell_doc) == structure_fingerprint(
            parent_doc
        )
        if same_shape:
            # Shape unchanged: the structural anti-clone floor is inapplicable (the
            # state-signature floor governs an M5-only mutant). Not a failure.
            return None
        # In files mode the shell has already been committed under skeletons/, so
        # the live in-cell scan would include it and compare it to itself (distance
        # 0, a false clone). Exclude the shell-being-proved by content identity;
        # this is a no-op for a bundle-dir shell that is not yet in the catalog.
        shell_hash = content_sha256(shell_doc)
        in_cell = [
            sibling
            for sibling in load_in_cell_catalog(shell_doc, parent_slug)
            if content_sha256(sibling) != shell_hash
        ]
        return structural_floor_reason(parent_doc, shell_doc, in_cell)
    except (ValidationError, ValueError):
        return None


def prove_shell(shell_path: Path, *, skeletons_root: Path) -> list[str]:
    """Re-prove one shell and its sidecars from scratch (design 4.3 point 4).

    Args:
        shell_path: The gate-passing shell (``<slug>.json``).
        skeletons_root: The live catalog root the parent hash and floor resolve
            against.

    Returns:
        list[str]: One reason per failed check; empty when the shell passes every
            applicable check.
    """
    reasons: list[str] = []
    name = shell_path.name

    if _run_check_skeleton([str(shell_path)]) != 0:
        reasons.append(f"{name}: check_skeleton (gate/cell/envelope) failed")

    contract_path = shell_path.with_name(f"{shell_path.stem}.contract.json")
    if contract_path.is_file() and _run_check_theme_contract([str(shell_path)]) != 0:
        reasons.append(f"{name}: check_theme_contract failed")

    lineage_path = shell_path.with_name(f"{shell_path.stem}.lineage.json")
    if not lineage_path.is_file():
        reasons.append(f"{name}: missing lineage sidecar {lineage_path.name}")
        return reasons

    try:
        lineage = load_lineage(lineage_path.read_text(encoding="utf-8"))
    except (OSError, PydanticValidationError, ValidationError, ValueError) as exc:
        reasons.append(f"{name}: lineage sidecar is invalid: {exc}")
        return reasons

    verify_reason = _verify_parent_hash(lineage, skeletons_root)
    if verify_reason is not None:
        reasons.append(f"{name}: {verify_reason}")

    try:
        shell_doc = _load_json_object(shell_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        reasons.append(f"{name}: shell could not be read: {exc}")
        return reasons

    floor_reason = _floor_reason(shell_doc, lineage, skeletons_root)
    if floor_reason is not None:
        reasons.append(f"{name}: anti-clone floor failed: {floor_reason}")

    return reasons


def _shell_from_bundle_dir(bundle_dir: Path) -> Path | None:
    """Return the ``<slug>.json`` shell in a bundle directory (keyed off lineage).

    The bundle also holds ``acceptance.json`` / ``reguide.json`` (non-sidecar
    ``.json`` files), so the shell is identified by the lineage sidecar's slug
    rather than by "the only non-sidecar json".
    """
    lineage_matches = sorted(bundle_dir.glob("*.lineage.json"))
    if lineage_matches:
        slug = lineage_matches[0].name.removesuffix(".lineage.json")
        shell = bundle_dir / f"{slug}.json"
        return shell if shell.is_file() else None
    shells = [
        path for path in sorted(bundle_dir.glob("*.json")) if not is_sidecar(path)
    ]
    return shells[0] if len(shells) == 1 else None


def _shells_from_paths(paths: Sequence[Path]) -> tuple[list[Path], list[str]]:
    """Resolve CLI paths (bundle dirs or skeleton files) into shells to prove.

    A directory is treated as a bundle directory (its single non-sidecar
    ``<slug>.json`` shell is proven). A ``.json`` file that is not a sidecar is
    proven directly; a ``*.lineage.json`` / ``*.contract.json`` sidecar is skipped
    (it is proven via its shell), which is what lets the CI job pass the full
    changed-files list of a promotion PR unfiltered.

    Args:
        paths: The CLI paths.

    Returns:
        tuple: ``(shells, errors)`` where shells are de-duplicated, sorted shell
            paths and errors are messages for unresolvable inputs.
    """
    shells: list[Path] = []
    errors: list[str] = []
    for path in paths:
        if path.is_dir():
            shell = _shell_from_bundle_dir(path)
            if shell is None:
                errors.append(f"{path}: no single shell (<slug>.json) in bundle dir")
            else:
                shells.append(shell)
        elif path.is_file():
            if path.suffix == ".json" and not is_sidecar(path):
                shells.append(path)
            # else: a sidecar or non-skeleton file; proven via its shell / ignored.
        else:
            errors.append(f"{path}: not found")
    unique = sorted({shell.resolve(): shell for shell in shells}.values())
    return unique, errors


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="Skeleton files and/or bundle directories to prove.",
    )
    _ = parser.add_argument(
        "--bundle",
        metavar="DIR",
        action="append",
        default=[],
        help="A promotion bundle directory to prove (repeatable).",
    )
    _ = parser.add_argument(
        "--skeletons-root",
        default=str(_SKELETONS_ROOT),
        help=f"Live catalog root for parent/floor resolution (default {_SKELETONS_ROOT}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Prove every requested bundle/shell and return a process exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    raw_paths = [
        *cast("list[str]", args.paths),
        *cast("list[str]", args.bundle),
    ]
    if not raw_paths:
        sys.stderr.write("error: no paths or --bundle directories given\n")
        return 1
    skeletons_root = Path(cast("str", args.skeletons_root)).resolve()

    shells, errors = _shells_from_paths([Path(p) for p in raw_paths])
    if not shells and not errors:
        sys.stdout.write("no skeleton shells to prove (only sidecars were given)\n")
        return 0

    all_reasons: list[str] = list(errors)
    for shell in shells:
        reasons = prove_shell(shell, skeletons_root=skeletons_root)
        if reasons:
            all_reasons.extend(reasons)
        else:
            sys.stdout.write(f"PASS {shell.name}: re-proved from scratch\n")

    if all_reasons:
        sys.stderr.write("FAIL promotion-bundle proof:\n")
        for reason in all_reasons:
            sys.stderr.write(f"  - {reason}\n")
        return 1
    sys.stdout.write(f"OK: proved {len(shells)} shell(s) from scratch\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
