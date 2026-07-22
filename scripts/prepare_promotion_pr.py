#!/usr/bin/env python3
"""Prepare a draft promotion PR from a WS-5 promotion bundle (WS-8 D4, stage S6).

This is the one WS-8 step that writes files destined for ``skeletons/``. It sits
at the automation boundary (design 4.3): automation prepares a draft PR, a human
merges it. Nothing here can merge, approve, enable auto-merge, or write under
``skeletons/`` on the default branch. The safety property is structural, not a
matter of discipline:

- it refuses to run when the current git branch is ``main`` / ``master``;
- it refuses a bundle whose ``acceptance.json`` is not ``promotable: true`` or
  whose ``reguide.json`` is not ``fully_resolved: true``;
- it re-runs ``verify_bundle`` against the live ``skeletons/`` IMMEDIATELY before
  any copy, and refuses on a parent-hash mismatch (a parent that changed since
  derivation invalidates the acceptance evidence);
- every file it writes is written ONLY inside a dedicated worktree checkout of a
  fresh ``flywheel/promote-<slug>`` branch, asserted to be contained in that
  worktree before each write;
- the only external side effect is opening a DRAFT PR labeled
  ``skeleton-promotion``, through an injected creator that (by default, without
  ``--create``) merely prints the exact ``gh pr create`` command and the composed
  PR body. There is no code path that merges, approves, or auto-merges.

Usage::

    # Default: refuse/verify, then print the gh command + PR body (no side effect).
    uv run python scripts/prepare_promotion_pr.py out/mutations/<slug>

    # In a real environment: create the worktree, stage files, open the draft PR.
    uv run python scripts/prepare_promotion_pr.py out/mutations/<slug> --create

Exit codes:
    0 - the draft-PR plan was produced (dry run) or the draft PR was opened.
    1 - a refusal (branch is main, not promotable/resolved, verify mismatch) or an
        input error.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404 -- git/gh invoked with list-form argv only; audited below
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.diagram import skeleton_to_plantuml
from cyo_adventure.mutation.bundle import LineageV2, load_lineage, verify_bundle

if TYPE_CHECKING:
    from collections.abc import Mapping

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKELETONS_ROOT = _REPO_ROOT / "skeletons"
_DEFAULT_WORKTREES = _REPO_ROOT / ".worktrees"

PROMOTION_LABEL = "skeleton-promotion"
_DEFAULT_BASE = "main"
_PROTECTED_BRANCHES = frozenset({"main", "master"})


# --------------------------------------------------------------------------- #
# Injected seams: git operations and PR creation.
# --------------------------------------------------------------------------- #


class GitRunner(Protocol):
    """The git operations this script needs, injectable for tests."""

    def current_branch(self) -> str:
        """Return the current branch name."""
        ...

    def add_worktree(self, worktree_dir: Path, branch: str) -> None:
        """Create ``worktree_dir`` as a checkout of a fresh ``branch``."""
        ...


@dataclass(frozen=True, slots=True)
class PrRequest:
    """The draft PR to open. Structurally a create-only request: no merge fields.

    Attributes:
        title: The PR title (Conventional Commits).
        body: The composed PR body (markdown).
        head: The head branch (``flywheel/promote-<slug>``).
        base: The base branch (``main``).
        draft: Always True; a promotion PR is never opened ready-for-merge.
        labels: The labels to apply (always includes ``skeleton-promotion``).
    """

    title: str
    body: str
    head: str
    base: str
    draft: bool
    labels: tuple[str, ...]


class PrCreator(Protocol):
    """The PR-creation seam, injectable for tests (never merges/approves)."""

    def __call__(self, request: PrRequest, *, worktree_dir: Path) -> None:
        """Act on a draft-PR request (open it, or print it in a dry run)."""
        ...


class _RealGitRunner:
    """A git runner backed by the ``git`` CLI, scoped to a repository root."""

    __slots__ = ("_repo_root",)

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def current_branch(self) -> str:
        """Return the current branch via ``git rev-parse --abbrev-ref HEAD``."""
        # #ASSUME: external-resources: git is on PATH and the cwd is a work tree.
        # list-form argv, no shell; output is a branch name, not user input.
        # #VERIFY: tests inject a fake runner; this path is exercised only in a
        # real environment, where a git failure surfaces as a non-zero exit.
        result = subprocess.run(  # nosec B603 B607
            ["git", "-C", str(self._repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def add_worktree(self, worktree_dir: Path, branch: str) -> None:
        """Create a worktree checkout of a fresh ``branch`` at ``worktree_dir``."""
        # #CRITICAL: security: the worktree is the write sandbox for the one step
        # that produces skeletons/ files. A fresh branch (never main) guarantees
        # the copy targets a non-default ref (design 4.3). list-form argv only.
        # #VERIFY: tests inject a fake runner; the real path only runs under
        # --create in a real environment.
        _ = subprocess.run(  # nosec B603 B607
            [
                "git",
                "-C",
                str(self._repo_root),
                "worktree",
                "add",
                str(worktree_dir),
                "-b",
                branch,
            ],
            check=True,
            capture_output=True,
            text=True,
        )


class _DryRunPrCreator:
    """The default creator: print the exact gh command and PR body; open nothing."""

    def __call__(self, request: PrRequest, *, worktree_dir: Path) -> None:
        """Print the draft ``gh pr create`` invocation and the PR body."""
        _ = worktree_dir
        label_args = " ".join(f"--label {label}" for label in request.labels)
        command = (
            f"gh pr create --draft {label_args} "
            f"--base {request.base} --head {request.head} "
            f"--title {json.dumps(request.title)} --body-file <PR_BODY_FILE>"
        )
        sys.stdout.write("DRY RUN: no PR opened. Would run:\n")
        sys.stdout.write(f"  {command}\n\n")
        sys.stdout.write("----- PR body -----\n")
        sys.stdout.write(request.body)
        if not request.body.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.write("----- end PR body -----\n")


class _GhPrCreator:
    """A creator that opens a real draft PR via ``gh`` (used only with --create)."""

    __slots__ = ()

    def __call__(self, request: PrRequest, *, worktree_dir: Path) -> None:
        """Open the draft PR with ``gh pr create --draft`` from the worktree."""
        # #CRITICAL: security: this opens a DRAFT PR only. There is deliberately no
        # branch that merges, approves, or enables auto-merge (design 4.3): the
        # human review of this PR is the promotion instrument (ADR-020 decision 4).
        # #VERIFY: tests inject a recording creator and assert draft is True and
        # the skeleton-promotion label is present; no merge/approve call exists.
        fd, tmp_name = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        body_file = Path(tmp_name)
        try:
            _ = body_file.write_text(request.body, encoding="utf-8")
            argv = [
                "gh",
                "pr",
                "create",
                "--draft",
                "--base",
                request.base,
                "--head",
                request.head,
                "--title",
                request.title,
                "--body-file",
                str(body_file),
            ]
            for label in request.labels:
                argv.extend(["--label", label])
            _ = subprocess.run(  # nosec B603 B607
                argv, check=True, cwd=str(worktree_dir), capture_output=True, text=True
            )
        finally:
            body_file.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Bundle loading and the refusal checks.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LoadedBundle:
    """A promotion bundle's parsed contents (design 7.1)."""

    bundle_dir: Path
    slug: str
    band: str
    shell_path: Path
    lineage_path: Path
    contract_path: Path | None
    shell_doc: dict[str, object]
    acceptance: dict[str, object]
    reguide: dict[str, object]
    lineage: LineageV2


def _load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON object document from disk."""
    data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(data, dict):
        msg = f"expected a JSON object in {path}"
        raise ValueError(msg)
    return cast("dict[str, object]", data)


def _band_of(shell_doc: Mapping[str, object]) -> str | None:
    """Return the shell's declared age band, or None when it is missing."""
    meta = shell_doc.get("metadata")
    if not isinstance(meta, dict):
        return None
    band = cast("dict[str, object]", meta).get("age_band")
    return band if isinstance(band, str) and band else None


def load_bundle(bundle_dir: Path) -> LoadedBundle:
    """Load and structurally validate a promotion bundle directory (design 7.1).

    Args:
        bundle_dir: The bundle directory (``<slug>.json`` plus sidecars).

    Returns:
        LoadedBundle: The parsed bundle.

    Raises:
        ValueError: If a required file is absent or malformed, or the shell
            declares no age band.
    """
    lineage_matches = sorted(bundle_dir.glob("*.lineage.json"))
    if not lineage_matches:
        msg = f"no *.lineage.json in bundle directory {bundle_dir}"
        raise ValueError(msg)
    lineage_path = lineage_matches[0]
    slug = lineage_path.name.removesuffix(".lineage.json")
    shell_path = bundle_dir / f"{slug}.json"
    if not shell_path.is_file():
        msg = f"no shell {slug}.json in bundle directory {bundle_dir}"
        raise ValueError(msg)
    acceptance_path = bundle_dir / "acceptance.json"
    reguide_path = bundle_dir / "reguide.json"
    if not acceptance_path.is_file() or not reguide_path.is_file():
        msg = f"bundle {bundle_dir} is missing acceptance.json or reguide.json"
        raise ValueError(msg)
    contract_path = bundle_dir / f"{slug}.contract.json"

    shell_doc = _load_json_object(shell_path)
    band = _band_of(shell_doc)
    if band is None:
        msg = f"shell {shell_path} declares no metadata.age_band"
        raise ValueError(msg)

    try:
        lineage = load_lineage(lineage_path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        msg = f"lineage {lineage_path} is invalid: {exc}"
        raise ValueError(msg) from exc

    return LoadedBundle(
        bundle_dir=bundle_dir,
        slug=slug,
        band=band,
        shell_path=shell_path,
        lineage_path=lineage_path,
        contract_path=contract_path if contract_path.is_file() else None,
        shell_doc=shell_doc,
        acceptance=_load_json_object(acceptance_path),
        reguide=_load_json_object(reguide_path),
        lineage=lineage,
    )


def refusal_reason(bundle: LoadedBundle, *, skeletons_root: Path) -> str | None:
    """Return why the bundle must not be promoted, or None when it may proceed.

    Applies the design-4.3 #CRITICAL refusals in order (excluding the branch check,
    which the caller performs before touching the bundle): not-promotable,
    not-fully-resolved, then a fresh ``verify_bundle`` against the live catalog.

    Args:
        bundle: The loaded bundle.
        skeletons_root: The live catalog root ``verify_bundle`` resolves against.

    Returns:
        str | None: The refusal reason, or None when the bundle may be prepared.
    """
    if bundle.acceptance.get("promotable") is not True:
        return (
            f"acceptance.json is not promotable (promotable="
            f"{bundle.acceptance.get('promotable')!r}); a held candidate must not "
            f"be promoted"
        )
    if bundle.reguide.get("fully_resolved") is not True:
        return (
            f"reguide.json is not fully_resolved (fully_resolved="
            f"{bundle.reguide.get('fully_resolved')!r}); every re-guidance item "
            f"must be resolved before promotion"
        )
    # #CRITICAL: data-integrity: re-run verify_bundle IMMEDIATELY before any copy.
    # A parent that changed between bundling and PR prep invalidates the acceptance
    # evidence and must hard-fail here (design 4.3 #CRITICAL / #VERIFY).
    verify = verify_bundle(bundle.bundle_dir, skeletons_root=skeletons_root)
    if not verify.ok:
        return f"verify_bundle failed: {verify.message}"
    return None


# --------------------------------------------------------------------------- #
# Worktree staging (the only write path; contained by construction).
# --------------------------------------------------------------------------- #


def _assert_within(worktree_dir: Path, path: Path) -> None:
    """Raise if ``path`` is not inside ``worktree_dir`` (the write-sandbox guard)."""
    root = worktree_dir.resolve()
    target = path.resolve()
    if root != target and root not in target.parents:
        # #CRITICAL: security: this is the hard stop that keeps every write inside
        # the dedicated worktree; a write escaping it could touch skeletons/ on the
        # checked-out branch's parent tree or the real repo (design 4.3 #CRITICAL).
        # #VERIFY: the filesystem sandbox test asserts nothing is written outside
        # the worktree and that the real skeletons/ is untouched.
        msg = f"refusing to write outside the worktree: {target} not under {root}"
        raise RuntimeError(msg)


def _write_contained(worktree_dir: Path, path: Path, content: str) -> None:
    """Write ``content`` to ``path`` after asserting it is inside the worktree."""
    _assert_within(worktree_dir, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _copy_contained(worktree_dir: Path, src: Path, dst: Path) -> None:
    """Copy ``src`` to ``dst`` after asserting ``dst`` is inside the worktree."""
    _assert_within(worktree_dir, dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copyfile(src, dst)


def stage_into_worktree(worktree_dir: Path, bundle: LoadedBundle) -> list[Path]:
    """Copy the shell/lineage/contract into the worktree and regenerate docs.

    Every write is asserted to land inside ``worktree_dir`` before it happens, so
    the function cannot touch the real ``skeletons/`` or anything outside the
    dedicated worktree, regardless of the bundle's contents.

    Args:
        worktree_dir: The dedicated worktree (the write sandbox).
        bundle: The loaded, refusal-cleared bundle.

    Returns:
        list[Path]: The paths written, all inside ``worktree_dir``.
    """
    _ensure_repo_on_path()
    from scripts.render_skeleton_diagrams import regenerate_catalog  # noqa: PLC0415

    band_dir = worktree_dir / "skeletons" / bundle.band
    written: list[Path] = []

    shell_dst = band_dir / f"{bundle.slug}.json"
    _copy_contained(worktree_dir, bundle.shell_path, shell_dst)
    written.append(shell_dst)

    lineage_dst = band_dir / f"{bundle.slug}.lineage.json"
    _copy_contained(worktree_dir, bundle.lineage_path, lineage_dst)
    written.append(lineage_dst)

    if bundle.contract_path is not None:
        contract_dst = band_dir / f"{bundle.slug}.contract.json"
        _copy_contained(worktree_dir, bundle.contract_path, contract_dst)
        written.append(contract_dst)

    # Regenerate the catalog doc region from the worktree's skeletons (reusing the
    # existing generator so the table can never be hand-written or drift).
    catalog_path = worktree_dir / "docs" / "architecture" / "story-skeletons.md"
    if catalog_path.is_file():
        refreshed = regenerate_catalog(worktree_dir / "skeletons", catalog_path)
        _write_contained(worktree_dir, catalog_path, refreshed)
        written.append(catalog_path)

    # Regenerate the structure diagram (PlantUML source; SVG is a separate,
    # jar-dependent step the CLI leaves to render_skeleton_diagrams.py).
    diagram_path = (
        worktree_dir
        / "docs"
        / "architecture"
        / "diagrams"
        / "skeletons"
        / bundle.band
        / f"{bundle.slug}.puml"
    )
    _write_contained(
        worktree_dir,
        diagram_path,
        skeleton_to_plantuml(bundle.shell_doc, name=bundle.slug),
    )
    written.append(diagram_path)

    return written


# --------------------------------------------------------------------------- #
# PR body composition (the S7 human-review evidence).
# --------------------------------------------------------------------------- #


def _reguide_table(reguide: Mapping[str, object]) -> list[str]:
    """Render the design-5.4 reguide table rows (target | reason | before | after | author)."""
    rows = [
        "| Target | Reason | Before | Drafted-after | Author |",
        "| --- | --- | --- | --- | --- |",
    ]
    items = reguide.get("items")
    if not isinstance(items, list):
        return rows
    for raw in cast("list[object]", items):
        if not isinstance(raw, dict):
            continue
        item = cast("dict[str, object]", raw)
        target = f"{item.get('target', '?')} {item.get('target_id', '')}".strip()
        reason = str(item.get("reason", ""))
        before = str(item.get("before", "") or "")
        after = str(item.get("after", "") or "")
        author = str(item.get("author", "") or "")
        cells = [_md_cell(c) for c in (target, reason, before, after, author)]
        rows.append("| " + " | ".join(cells) + " |")
    return rows


def _md_cell(text: str) -> str:
    """Escape a value for a Markdown table cell (pipes and newlines)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _para(*parts: str) -> str:
    """Join text fragments into one line (a wrap helper that avoids implicit concat)."""
    return "".join(parts)


def _lineage_lines(lineage: LineageV2, band: str) -> list[str]:
    """Render the origin-aware lineage bullet list (design 7.2).

    A ``mutation`` record renders its parent, op chain, and donors; a ``fresh``
    record has no parent, so it renders its generation provenance instead. This is
    what lets the promotion PR body tolerate a parentless (WS-6) bundle without
    dereferencing an absent ``parent_slug`` / ``parent_sha256``.
    """
    if lineage.origin == "mutation":
        parent_slug = lineage.parent_slug or "(unknown)"
        parent_sha = lineage.parent_sha256 or ""
        parent_ref = (
            f"`{parent_slug}` (`{parent_sha[:12]}...`)"
            if parent_sha
            else (f"`{parent_slug}`")
        )
        op_chain = " -> ".join(entry.op_id for entry in lineage.op_chain)
        return [
            "- **Origin:** mutation (WS-5)",
            f"- **Parent:** {parent_ref}",
            f"- **Op chain:** {op_chain or '(none)'}",
            f"- **Donors:** {', '.join(lineage.donor_slugs) or '(none)'}",
            f"- **Band / cell:** {band}",
            f"- **Tool version:** {lineage.tool_version}",
        ]
    if lineage.origin == "fresh":
        return [
            "- **Origin:** fresh (WS-6)",
            f"- **Generator:** `{lineage.generator or '(unknown)'}`",
            f"- **Generation params:** `{(lineage.generation_params_sha256 or '')[:12]}...`",
            f"- **Band / cell:** {band}",
            f"- **Tool version:** {lineage.tool_version}",
        ]
    return [
        "- **Origin:** composed (reserved; not yet produced)",
        f"- **Band / cell:** {band}",
        f"- **Tool version:** {lineage.tool_version}",
    ]


def compose_pr_body(bundle: LoadedBundle) -> str:
    """Compose the draft PR body: transcript, reguide table, diagram, lineage (S7)."""
    lineage = bundle.lineage
    stages = bundle.acceptance.get("stages")
    stage_count = len(cast("list[object]", stages)) if isinstance(stages, list) else 0
    agent_items = _count_agent_drafted(bundle.reguide)

    sample_note = ""
    if (bundle.bundle_dir / "sample-fill").is_dir():
        sample_note = (
            "- Sample-fill evidence is included in the bundle's `sample-fill/`.\n"
        )

    intro = _para(
        "Automated draft (WS-8 catalog flywheel, stage S6). A human performs ",
        "structure approval by reviewing and merging this PR. ",
        "**Do NOT enable auto-merge** (ADR-020 decision 4).",
    )
    transcript_line = _para(
        "- Full transcript: bundle `acceptance.json` (acceptance digest ",
        f"`{lineage.acceptance_digest[:12]}...`).",
    )
    reguide_intro = _para(
        f"Agent-drafted items requiring per-item human approval: **{agent_items}**. ",
        "Every row whose author starts with `agent:` MUST be reviewed and approved ",
        "individually; give CHOICE/ENDING rows a specific action-semantic check.",
    )
    diagram_line = _para(
        f"- `docs/architecture/diagrams/skeletons/{bundle.band}/{bundle.slug}.puml` ",
        "(regenerated on this branch).",
    )
    evidence_line = _para(
        f"{sample_note}- The `skeleton-promotion` CI job re-proves the gate, ",
        "contract, anti-clone floor, and lineage/hash from scratch on this PR.",
    )

    lines = [
        f"## Promote flywheel skeleton `{bundle.slug}`",
        "",
        intro,
        "",
        "### Lineage",
        "",
        *_lineage_lines(lineage, bundle.band),
        "",
        "### Acceptance transcript",
        "",
        f"- **promotable:** {bundle.acceptance.get('promotable')}",
        f"- **stages recorded:** {stage_count}",
        f"- **re-guidance outstanding:** {bundle.acceptance.get('reguide_outstanding')}",
        transcript_line,
        "",
        "### Re-guidance resolutions (design 5.4)",
        "",
        reguide_intro,
        "",
        *_reguide_table(bundle.reguide),
        "",
        "### Structure diagram",
        "",
        diagram_line,
        "",
        "### Evidence",
        "",
        evidence_line,
        "",
    ]
    return "\n".join(lines)


def _count_agent_drafted(reguide: Mapping[str, object]) -> int:
    """Return how many resolved reguide items were agent-drafted (author agent:*)."""
    items = reguide.get("items")
    if not isinstance(items, list):
        return 0
    count = 0
    for raw in cast("list[object]", items):
        if isinstance(raw, dict):
            author = cast("dict[str, object]", raw).get("author")
            if isinstance(author, str) and author.startswith("agent:"):
                count += 1
    return count


def _ensure_repo_on_path() -> None:
    """Make the repository root importable so sibling scripts resolve when run direct."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("bundle", help="Path to the promotion bundle directory.")
    _ = parser.add_argument(
        "--skeletons-root",
        default=str(_SKELETONS_ROOT),
        help=f"Live catalog root for verify_bundle (default {_SKELETONS_ROOT}).",
    )
    _ = parser.add_argument(
        "--worktrees-root",
        default=str(_DEFAULT_WORKTREES),
        help=f"Root the promotion worktree is created under (default {_DEFAULT_WORKTREES}).",
    )
    _ = parser.add_argument(
        "--branch",
        default=None,
        help="Override the promotion branch name (default flywheel/promote-<slug>).",
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
    """Prepare a draft promotion PR (or its dry-run plan) from a bundle.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).
        git_runner: The git seam (defaults to the real ``git`` CLI runner).
        pr_creator: The PR-creation seam (defaults to dry-run print, or ``gh`` under
            ``--create``).

    Returns:
        int: ``0`` on success (plan produced or draft PR opened), ``1`` on a
            refusal/input error, ``2`` on an argparse usage error.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    repo_root = _REPO_ROOT
    create: bool = cast("bool", args.create)
    runner = git_runner if git_runner is not None else _RealGitRunner(repo_root)
    creator = pr_creator
    if creator is None:
        creator = _GhPrCreator() if create else _DryRunPrCreator()

    # Refusal 1: never run on the default branch (design 4.3 #CRITICAL).
    branch = runner.current_branch()
    if branch in _PROTECTED_BRANCHES:
        sys.stderr.write(
            _para(
                f"refusing: current branch is '{branch}'; promotion PR preparation ",
                "must run on a dedicated feature branch, never a protected branch\n",
            )
        )
        return 1

    bundle_dir = Path(cast("str", args.bundle)).resolve()
    skeletons_root = Path(cast("str", args.skeletons_root)).resolve()
    try:
        bundle = load_bundle(bundle_dir)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: cannot load bundle {bundle_dir}: {exc}\n")
        return 1

    # Refusals 2-4: not-promotable / not-fully-resolved / stale parent.
    reason = refusal_reason(bundle, skeletons_root=skeletons_root)
    if reason is not None:
        sys.stderr.write(f"refusing: {reason}\n")
        return 1

    branch_name = cast("str | None", args.branch) or f"flywheel/promote-{bundle.slug}"
    base: str = cast("str", args.base)
    worktrees_root = Path(cast("str", args.worktrees_root)).resolve()
    worktree_dir = worktrees_root / f"promote-{bundle.slug}"

    body = compose_pr_body(bundle)
    request = PrRequest(
        title=f"feat(catalog): promote flywheel skeleton {bundle.slug}",
        body=body,
        head=branch_name,
        base=base,
        draft=True,
        labels=(PROMOTION_LABEL,),
    )

    if not create:
        contract_note = f", {bundle.slug}.contract.json" if bundle.contract_path else ""
        sys.stdout.write(
            _para(
                f"prepared promotion plan for '{bundle.slug}' (band {bundle.band}) ",
                f"from branch '{branch}':\n",
                f"  would create worktree: {worktree_dir}\n",
                f"  on new branch:         {branch_name}\n",
                f"  would copy into worktree skeletons/{bundle.band}/:\n",
                f"    {bundle.slug}.json, {bundle.slug}.lineage.json{contract_note}\n",
                "  and regenerate the catalog region + diagram.\n\n",
            )
        )
        creator(request, worktree_dir=worktree_dir)
        return 0

    runner.add_worktree(worktree_dir, branch_name)
    written = stage_into_worktree(worktree_dir, bundle)
    sys.stdout.write(f"staged {len(written)} file(s) into {worktree_dir}:\n")
    for path in written:
        sys.stdout.write(f"  {path}\n")
    creator(request, worktree_dir=worktree_dir)
    sys.stdout.write(
        _para(
            f"opened draft PR for '{bundle.slug}' (label {PROMOTION_LABEL}); a human ",
            "must review and merge it. Auto-merge is never enabled.\n",
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# Public reuse surface.
# --------------------------------------------------------------------------- #
# Sibling glue that reuses D4's draft-PR / worktree posture (WS-8 D6's
# scripts/parameterize_promotion.py) imports these instead of reaching into the
# private originals above. The underscored names remain for this module's own
# use and its existing tests; these aliases add no new behavior.

RealGitRunner = _RealGitRunner
DryRunPrCreator = _DryRunPrCreator
GhPrCreator = _GhPrCreator
write_contained = _write_contained
copy_contained = _copy_contained


if __name__ == "__main__":
    raise SystemExit(main())
