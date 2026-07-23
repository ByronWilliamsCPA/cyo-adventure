#!/usr/bin/env python3
"""Parameterize an already-promoted contract-less skeleton (WS-8 D6, design 7.3).

This is the OPTIONAL, manual-first "parameterize-at-promotion" glue. It runs the
WS-2 recipe verbatim over a tree that is already in the catalog contract-less (a
Tier-2-parity mutant today; a future WS-6 fresh tree), and prepares a SECOND
``skeleton-promotion`` PR carrying the slotted skeleton plus its authored theme
contract.

Posture (design section 7.3, OQ-6): promotion does NOT block on parameterization.
A contract-less promoted tree is exactly as safe as its contract-less parent
(same free-text fill path, same gate, ADR-020 decision 6). This glue is a
follow-up an operator may run when convenient; it never blocks, auto-runs, or
weakens any check.

The chain, in order, adding NO bypass of any check:

1. ``scripts/parameterize_skeleton.py`` applies the operator-authored slotting
   plan under its SIX fail-closed checks (coverage; dangling references;
   ``role=``/``words=`` byte-preservation; structural-fingerprint equality;
   ``run_gate`` not blocked; slot-token grammar). It writes the slotted skeleton
   ONLY when every check passes; this glue honors its exit code and writes
   nothing further on failure.
2. The operator-authored ``contract.json`` is placed as the slotted skeleton's
   sidecar (``<slug>.contract.json``).
3. ``scripts/check_theme_contract.py`` runs the WS-2 acceptance checks against
   that sidecar; the glue honors its exit code.
4. Only if both pass, a draft ``skeleton-promotion`` PR is prepared, reusing
   D4's posture exactly (dry-run by default; refuses to run on ``main``;
   worktree-only writes; draft PR; never merges, approves, or enables
   auto-merge).

Manual-first: the operator supplies BOTH the slotting ``plan.json`` and the
authored ``contract.json`` (per the WS-2 recipe). This glue does not draft
plans or contracts; there is deliberately no LLM in this path.

Usage::

    # Default: run the chain, then print the gh command + PR body (no side effect).
    uv run python scripts/parameterize_promotion.py \\
        skeletons/8-11/<slug>.json --plan plan.json --contract contract.json

    # In a real environment: also create the worktree and open the draft PR.
    uv run python scripts/parameterize_promotion.py \\
        skeletons/8-11/<slug>.json --plan plan.json --contract contract.json --create

Exit codes:
    0 - the chain passed and the draft-PR plan was produced (or opened).
    1 - a refusal (branch is main, already parameterized) or any chain-check
        failure (the transform's six checks, or contract acceptance).
    2 - an argparse usage error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import cast

from cyo_adventure.generation.binding import contract_path_for
from cyo_adventure.generation.diagram import skeleton_to_plantuml
from cyo_adventure.storybook.theme_contract import SLOT_TOKEN_RE
from scripts import check_theme_contract as ctc
from scripts import parameterize_skeleton as ps
from scripts.prepare_promotion_pr import (
    PROMOTION_LABEL,
    DryRunPrCreator,
    GhPrCreator,
    GitRunner,
    PrCreator,
    PrRequest,
    RealGitRunner,
    copy_contained,
    write_contained,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_WORKTREES = _REPO_ROOT / ".worktrees"

_DEFAULT_BASE = "main"
_PROTECTED_BRANCHES = frozenset({"main", "master"})


# --------------------------------------------------------------------------- #
# Input resolution and the contract-less guard.
# --------------------------------------------------------------------------- #


def _load_json_object(path: Path) -> dict[str, object]:
    """Load and return a JSON object document from disk.

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


def _band_of(doc: dict[str, object]) -> str | None:
    """Return the skeleton's declared age band, or None when it is missing."""
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        return None
    band = cast("dict[str, object]", meta).get("age_band")
    return band if isinstance(band, str) and band else None


def _resolve_skeleton_input(input_path: Path) -> tuple[Path, str]:
    """Resolve a skeleton file, or a bundle directory, to a (skeleton_path, slug).

    Accepts either an already-promoted skeleton ``<slug>.json`` directly, or a
    promotion bundle directory (which carries ``<slug>.lineage.json`` alongside
    the shell ``<slug>.json``), so an operator can point this glue at whatever
    artifact the first promotion produced.

    Args:
        input_path: The skeleton file or bundle directory.

    Returns:
        The resolved skeleton path and its slug.

    Raises:
        ValueError: If a bundle directory has no lineage sidecar or shell, or
            the input is neither a JSON file nor a directory.
    """
    if input_path.is_dir():
        lineage_matches = sorted(input_path.glob("*.lineage.json"))
        if not lineage_matches:
            msg = f"no *.lineage.json in bundle directory {input_path}"
            raise ValueError(msg)
        slug = lineage_matches[0].name.removesuffix(".lineage.json")
        shell_path = input_path / f"{slug}.json"
        if not shell_path.is_file():
            msg = f"no shell {slug}.json in bundle directory {input_path}"
            raise ValueError(msg)
        return shell_path, slug
    if input_path.is_file():
        return input_path, input_path.stem
    msg = f"input {input_path} is neither a JSON skeleton file nor a directory"
    raise ValueError(msg)


def contract_less_refusal(
    skeleton_path: Path, skeleton: dict[str, object]
) -> str | None:
    """Return why the input is not an eligible contract-less tree, or None.

    Parameterizing a tree that is already parameterized would be a no-op at best
    and a double-slotting corruption at worst, so this fails closed if the input
    already carries a theme contract sidecar or already exposes ``{SLOT}`` tokens.

    Args:
        skeleton_path: The input skeleton's on-disk path.
        skeleton: The decoded skeleton document.

    Returns:
        A refusal reason, or None when the tree is genuinely contract-less.
    """
    sidecar = contract_path_for(skeleton_path)
    if sidecar.is_file():
        return (
            f"{skeleton_path} already has a theme contract sidecar ({sidecar}); "
            f"it is already parameterized"
        )
    existing_tokens = sorted(set(SLOT_TOKEN_RE.findall(json.dumps(skeleton))))
    if existing_tokens:
        return (
            f"{skeleton_path} already exposes slot token(s) {existing_tokens}; "
            f"it is already parameterized"
        )
    return None


# --------------------------------------------------------------------------- #
# The chained checks (each honored by exit code; no check is re-implemented).
# --------------------------------------------------------------------------- #


def run_chain(
    *, skeleton_path: Path, plan_path: Path, contract_path: Path, out_dir: Path
) -> tuple[int, Path | None]:
    """Run transform -> contract-author -> acceptance; return (exit_code, slotted).

    The transform's six fail-closed checks and the contract-acceptance checks
    are the gatekeepers; this function only sequences them and honors their exit
    codes. It calls ``parameterize_skeleton.main`` and ``check_theme_contract.main``
    directly, so it can add no bypass: a non-zero from either aborts the chain
    and leaves no PR to prepare.

    Args:
        skeleton_path: The contract-less input skeleton.
        plan_path: The operator-authored slotting plan.
        contract_path: The operator-authored theme contract.
        out_dir: The working directory the slotted skeleton and its sidecar are
            written under (created if absent).

    Returns:
        ``(0, slotted_path)`` when both checks pass; ``(1, None)`` otherwise.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    slotted_path = out_dir / skeleton_path.name

    # Step 1: the transform runs its SIX fail-closed checks and writes the
    # slotted skeleton to --out ONLY if every one passes.
    transform_rc = ps.main(
        [str(skeleton_path), str(plan_path), "--out", str(slotted_path)]
    )
    if transform_rc != 0:
        transform_msg = (
            "chain aborted: parameterize_skeleton rejected the plan "
            "(one of its six fail-closed checks failed); nothing further written\n"
        )
        sys.stderr.write(transform_msg)
        return 1, None

    # Step 2: place the operator-authored contract as the slotted skeleton's
    # sidecar, where check_theme_contract derives it from the skeleton path.
    sidecar_path = contract_path_for(slotted_path)
    try:
        _ = shutil.copyfile(contract_path, sidecar_path)
    except OSError as exc:
        sys.stderr.write(f"chain aborted: cannot author contract sidecar: {exc}\n")
        return 1, None

    # Step 3: contract acceptance (the WS-2 six checks) against that sidecar.
    contract_rc = ctc.main([str(slotted_path)])
    if contract_rc != 0:
        sys.stderr.write(
            "chain aborted: check_theme_contract rejected the authored contract\n"
        )
        return 1, None

    return 0, slotted_path


# --------------------------------------------------------------------------- #
# Draft-PR preparation (reuses D4's posture: draft, label, worktree-only).
# --------------------------------------------------------------------------- #


def compose_pr_body(*, slug: str, band: str, slot_ids: list[str]) -> str:
    """Compose the second (parameterization) PR body for human structure review.

    Args:
        slug: The skeleton slug being parameterized.
        band: The skeleton's age band (its catalog cell directory).
        slot_ids: The slot ids the plan introduced.

    Returns:
        The Markdown PR body.
    """
    intro = (
        "Automated draft (WS-8 catalog flywheel, D6 parameterize-at-promotion). "
        "This is the OPTIONAL second PR that parameterizes an already-promoted "
        "contract-less tree; it does NOT block, and was never required for, the "
        "first promotion (design section 7.3, ADR-020 decision 6, OQ-6). "
        "A human performs review by merging. **Do NOT enable auto-merge** "
        "(ADR-020 decision 4)."
    )
    changed = (
        f"- Re-slots `skeletons/{band}/{slug}.json` in place (adds `{{SLOT}}` "
        f"tokens) and adds its `{slug}.contract.json` sidecar.\n"
        f"- Slot ids introduced: {slot_ids}."
    )
    evidence = (
        "- `parameterize_skeleton.py` passed all six fail-closed checks "
        "(coverage, dangling references, role/words byte-preservation, "
        "structural-fingerprint equality, gate-not-blocked, slot-token grammar).\n"
        "- `check_theme_contract.py` passed WS-2 acceptance against the authored "
        "contract.\n"
        "- The `skeleton-promotion` CI job re-proves the gate, contract, "
        "anti-clone floor, and lineage/hash from scratch on this PR."
    )
    lines = [
        f"## Parameterize promoted skeleton `{slug}`",
        "",
        intro,
        "",
        "### What changed",
        "",
        changed,
        "",
        "### Acceptance evidence",
        "",
        evidence,
        "",
    ]
    return "\n".join(lines)


def _stage_into_worktree(
    worktree_dir: Path,
    *,
    slug: str,
    band: str,
    slotted_path: Path,
    sidecar_path: Path,
    slotted_doc: dict[str, object],
) -> list[Path]:
    """Copy the slotted skeleton + contract into the worktree; regenerate docs.

    Every write is asserted to land inside ``worktree_dir`` (reusing D4's
    ``_write_contained`` / ``_copy_contained`` guards), so this cannot touch the
    real ``skeletons/`` or anything outside the dedicated worktree.

    Args:
        worktree_dir: The dedicated worktree (the write sandbox).
        slug: The skeleton slug.
        band: The skeleton's age band.
        slotted_path: The parameterized skeleton written by the chain.
        sidecar_path: The authored contract sidecar written by the chain.
        slotted_doc: The decoded parameterized skeleton (for the diagram).

    Returns:
        The paths written, all inside ``worktree_dir``.
    """
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts.render_skeleton_diagrams import regenerate_catalog  # noqa: PLC0415

    band_dir = worktree_dir / "skeletons" / band
    written: list[Path] = []

    shell_dst = band_dir / f"{slug}.json"
    copy_contained(worktree_dir, slotted_path, shell_dst)
    written.append(shell_dst)

    contract_dst = band_dir / f"{slug}.contract.json"
    copy_contained(worktree_dir, sidecar_path, contract_dst)
    written.append(contract_dst)

    catalog_path = worktree_dir / "docs" / "architecture" / "story-skeletons.md"
    if catalog_path.is_file():
        refreshed = regenerate_catalog(worktree_dir / "skeletons", catalog_path)
        write_contained(worktree_dir, catalog_path, refreshed)
        written.append(catalog_path)

    diagram_path = (
        worktree_dir
        / "docs"
        / "architecture"
        / "diagrams"
        / "skeletons"
        / band
        / f"{slug}.puml"
    )
    write_contained(
        worktree_dir, diagram_path, skeleton_to_plantuml(slotted_doc, name=slug)
    )
    written.append(diagram_path)

    return written


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "skeleton",
        help="Path to the contract-less promoted skeleton JSON, or its bundle dir.",
    )
    _ = parser.add_argument(
        "--plan", required=True, help="Path to the operator-authored slotting plan."
    )
    _ = parser.add_argument(
        "--contract",
        required=True,
        help="Path to the operator-authored theme contract JSON.",
    )
    _ = parser.add_argument(
        "--out-dir",
        default=None,
        help="Working dir for the slotted skeleton + sidecar (default out/parameterize/<slug>).",
    )
    _ = parser.add_argument(
        "--worktrees-root",
        default=str(_DEFAULT_WORKTREES),
        help=f"Root the promotion worktree is created under (default {_DEFAULT_WORKTREES}).",
    )
    _ = parser.add_argument(
        "--branch",
        default=None,
        help="Override the promotion branch (default flywheel/parameterize-<slug>).",
    )
    _ = parser.add_argument(
        "--base", default=_DEFAULT_BASE, help=f"Base branch (default {_DEFAULT_BASE})."
    )
    _ = parser.add_argument(
        "--create",
        action="store_true",
        help="Actually create the worktree, stage files, and open the draft PR.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    git_runner: GitRunner | None = None,
    pr_creator: PrCreator | None = None,
) -> int:
    """Run the parameterize-at-promotion chain and prepare the second draft PR.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).
        git_runner: The git seam (defaults to the real ``git`` CLI runner).
        pr_creator: The PR-creation seam (defaults to dry-run print, or ``gh``
            under ``--create``).

    Returns:
        int: ``0`` when the chain passed and the draft-PR plan was produced (or
            the PR was opened), ``1`` on a refusal or any chain-check failure,
            ``2`` on an argparse usage error.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    create: bool = cast("bool", args.create)
    runner = git_runner if git_runner is not None else RealGitRunner(_REPO_ROOT)
    creator = pr_creator
    if creator is None:
        creator = GhPrCreator() if create else DryRunPrCreator()

    # Refusal 1: never run on the default branch (design 4.3 #CRITICAL, D4 posture).
    branch = runner.current_branch()
    if branch in _PROTECTED_BRANCHES:
        branch_msg = (
            f"refusing: current branch is '{branch}'; parameterization PR "
            "preparation must run on a dedicated feature branch, never a "
            "protected branch\n"
        )
        sys.stderr.write(branch_msg)
        return 1

    # ASSUME: security: skeleton/plan/contract/out_dir are already
    # canonicalized with .resolve() below (CWE-23 hardening, Snyk python/PT),
    # but deliberately NOT contained to a fixed base (the
    # generation/import_cli.py::_load_blob idiom): tests/unit/
    # test_parameterize_promotion.py exercises every one of them against
    # pytest tmp_path fixtures well outside the repo tree with no chdir,
    # proving arbitrary-location paths are legitimate, exercised behavior
    # that containment would reject. No privilege boundary is crossed either
    # way: the operator invoking this dev-only glue already has full
    # filesystem access, per the path-traversal verification report
    # (scratchpad/pt-verification-report.md).
    # VERIFY: any future change adding a fixed base must re-run
    # test_parameterize_promotion.py first; a rejection there means real
    # behavior broke.
    input_path = Path(cast("str", args.skeleton)).resolve()
    plan_path = Path(cast("str", args.plan)).resolve()
    contract_path = Path(cast("str", args.contract)).resolve()
    try:
        skeleton_path, slug = _resolve_skeleton_input(input_path)
        skeleton = _load_json_object(skeleton_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: cannot load input {input_path}: {exc}\n")
        return 1

    # Refusal 2: only a genuinely contract-less tree is eligible (design 7.3).
    reason = contract_less_refusal(skeleton_path, skeleton)
    if reason is not None:
        sys.stderr.write(f"refusing: {reason}\n")
        return 1

    out_dir_arg: str | None = cast("str | None", args.out_dir)
    out_dir = (
        Path(out_dir_arg).resolve()
        if out_dir_arg is not None
        else _REPO_ROOT / "out" / "parameterize" / slug
    )

    chain_rc, slotted_path = run_chain(
        skeleton_path=skeleton_path,
        plan_path=plan_path,
        contract_path=contract_path,
        out_dir=out_dir,
    )
    if chain_rc != 0 or slotted_path is None:
        return 1

    slotted_doc = _load_json_object(slotted_path)
    band = _band_of(slotted_doc)
    if band is None:
        sys.stderr.write(
            f"error: slotted skeleton {slotted_path} declares no metadata.age_band\n"
        )
        return 1
    sidecar_path = contract_path_for(slotted_path)
    slot_ids = sorted(set(SLOT_TOKEN_RE.findall(json.dumps(slotted_doc))))

    branch_name = cast("str | None", args.branch) or f"flywheel/parameterize-{slug}"
    base: str = cast("str", args.base)
    worktrees_root = Path(cast("str", args.worktrees_root)).resolve()
    worktree_dir = worktrees_root / f"parameterize-{slug}"

    request = PrRequest(
        title=f"feat(catalog): parameterize promoted skeleton {slug}",
        body=compose_pr_body(slug=slug, band=band, slot_ids=slot_ids),
        head=branch_name,
        base=base,
        draft=True,
        labels=(PROMOTION_LABEL,),
    )

    if not create:
        summary = (
            f"chain passed for '{slug}' (band {band}); "
            f"{len(slot_ids)} slot id(s) introduced: {slot_ids}\n"
            f"  slotted skeleton: {slotted_path}\n"
            f"  contract sidecar: {sidecar_path}\n"
            f"  would create worktree: {worktree_dir}\n"
            f"  on new branch:         {branch_name}\n\n"
        )
        sys.stdout.write(summary)
        creator(request, worktree_dir=worktree_dir)
        return 0

    runner.add_worktree(worktree_dir, branch_name)
    written = _stage_into_worktree(
        worktree_dir,
        slug=slug,
        band=band,
        slotted_path=slotted_path,
        sidecar_path=sidecar_path,
        slotted_doc=slotted_doc,
    )
    sys.stdout.write(f"staged {len(written)} file(s) into {worktree_dir}:\n")
    for path in written:
        sys.stdout.write(f"  {path}\n")
    creator(request, worktree_dir=worktree_dir)
    opened_msg = (
        f"opened draft PR for '{slug}' (label {PROMOTION_LABEL}); a human must "
        "review and merge it. Auto-merge is never enabled.\n"
    )
    sys.stdout.write(opened_msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
