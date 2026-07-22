"""WS-8 D4 tests: promotion-PR preparation and the promotion-bundle prover.

Covers the design-4.3 #VERIFY set for ``scripts/prepare_promotion_pr.py`` (refuse
on branch==main, on not-promotable / not-fully-resolved, on a verify_bundle
mismatch; a filesystem sandbox that never writes outside its worktree; the
injected PR creator is called with draft+label and never merges/approves) and the
CI-job fixtures for ``scripts/check_promotion_bundle.py`` (a valid bundle passes;
a tampered shell, a stale parent, and a missing lineage each fail).

The valid-bundle fixture builds a real gate-passing mutant shell with the WS-5
engine and repoints its lineage parent at a distant in-cell catalog sibling, so
the anti-clone floor's parent-distance clause is exercised with a genuine
``>= TAU_STRUCT`` gap (no automated single mutant reaches it against its own
parent; that is by design and is why the floor is the gate).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure import __version__  # noqa: E402
from cyo_adventure.flywheel.strategy import (  # noqa: E402
    Cell,
    load_catalog,
    plan_attempts,
)
from cyo_adventure.mutation.bundle import (  # noqa: E402
    Lineage,
    OpChainEntry,
    build_lineage,
    derive_mutant_contract,
    write_bundle,
)
from cyo_adventure.mutation.compose import apply_chain  # noqa: E402
from cyo_adventure.storybook.theme_contract import ThemeContract  # noqa: E402
from scripts import check_promotion_bundle as cpb  # noqa: E402
from scripts import prepare_promotion_pr as ppr  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

_REAL_SKELETONS = _REPO_ROOT / "skeletons"
_DISTANT_PARENT = "the-locked-carousel"
_CELL = Cell(band="8-11", length="short", style="prose")


class _MutantParts:
    """The reusable pieces of one real gate-passing mutant, built once per module."""

    __slots__ = ("band", "contract", "donor_slugs", "op_chain", "shell_doc", "slug")

    def __init__(
        self,
        *,
        slug: str,
        band: str,
        shell_doc: dict[str, object],
        contract: ThemeContract | None,
        op_chain: Sequence[OpChainEntry],
        donor_slugs: Sequence[str],
    ) -> None:
        self.slug = slug
        self.band = band
        self.shell_doc = shell_doc
        self.contract = contract
        self.op_chain = tuple(op_chain)
        self.donor_slugs = tuple(donor_slugs)


def _load_contract(path: Path) -> ThemeContract | None:
    """Load a sidecar theme contract, or None when it is absent."""
    if not path.is_file():
        return None
    return ThemeContract.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mutant() -> _MutantParts:
    """Build one real gate-passing mutant shell + derived contract (WS-5 engine)."""
    catalog = load_catalog()
    plans = plan_attempts(_CELL, catalog, {})
    plan = next(p for p in plans if p.parent_slug == "the-cave-of-echoes")
    parent_entry = catalog.by_slug(plan.parent_slug)
    assert parent_entry is not None
    chain = apply_chain(parent_entry.document, plan.steps)
    slug = f"{plan.parent_slug}-fw-{plan.attempt_sig[:8]}"

    host = _load_contract(
        parent_entry.path.with_name(f"{plan.parent_slug}.contract.json")
    )
    donor_contracts: dict[str, ThemeContract] = {}
    if host is not None:
        donor_contracts[plan.parent_slug] = host
        for donor_slug in chain.donor_slugs:
            donor_entry = catalog.by_slug(donor_slug)
            if donor_entry is not None:
                donor = _load_contract(
                    donor_entry.path.with_name(f"{donor_slug}.contract.json")
                )
                if donor is not None:
                    donor_contracts[donor_slug] = donor
    contract = (
        derive_mutant_contract(
            chain.candidate,
            mutant_slug=slug,
            host_contract=host,
            donor_contracts=donor_contracts,
        )
        if host is not None
        else None
    )
    return _MutantParts(
        slug=slug,
        band="8-11",
        shell_doc=chain.candidate,
        contract=contract,
        op_chain=chain.op_chain,
        donor_slugs=chain.donor_slugs,
    )


def _write_valid_bundle(bundle_dir: Path, mutant: _MutantParts) -> None:
    """Write a promotable bundle whose lineage points at a distant in-cell parent."""
    distant_entry = load_catalog().by_slug(_DISTANT_PARENT)
    assert distant_entry is not None
    lineage = build_lineage(
        mutant_slug=mutant.slug,
        parent=distant_entry.document,
        parent_slug=_DISTANT_PARENT,
        op_chain=mutant.op_chain,
        donor_slugs=mutant.donor_slugs,
        created_at="2026-07-21T00:00:00+00:00",
        tool_version=__version__,
        acceptance={"promotable": True},
    )
    reguide = {
        "emitted_count": 1,
        "resolved_count": 1,
        "outstanding": [],
        "fully_resolved": True,
        "items": [
            {
                "target": "node",
                "target_id": "n_seam",
                "reason": "graft seam re-authored",
                "before": "old beats",
                "resolved": True,
                "after": "new beats",
                "author": "agent:test-model",
            }
        ],
    }
    _ = write_bundle(
        bundle_dir.parent,
        slug=mutant.slug,
        candidate=mutant.shell_doc,
        lineage=lineage,
        acceptance={
            "promotable": True,
            "held": False,
            "reguide_outstanding": 0,
            "stages": [{"stage": 0}, {"stage": 1}, {"stage": 2}, {"stage": 3}],
        },
        reguide=reguide,
        contract=mutant.contract,
    )


# --------------------------------------------------------------------------- #
# check_promotion_bundle: the CI-job fixtures.
# --------------------------------------------------------------------------- #


def test_prove_shell_valid_bundle_returns_no_reasons(
    mutant: _MutantParts, tmp_path: Path
) -> None:
    """A genuine gate-passing shell with a matching lineage proves clean."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)
    shell = bundle / f"{mutant.slug}.json"
    reasons = cpb.prove_shell(shell, skeletons_root=_REAL_SKELETONS)
    assert reasons == []


def test_main_bundle_dir_valid_bundle_exits_zero(
    mutant: _MutantParts, tmp_path: Path
) -> None:
    """The CLI proves a bundle directory (shell + lineage + contract) and exits 0."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)
    code = cpb.main(["--bundle", str(bundle), "--skeletons-root", str(_REAL_SKELETONS)])
    assert code == 0


def test_prove_shell_tampered_shell_fails(mutant: _MutantParts, tmp_path: Path) -> None:
    """A shell edited after bundling (gate now broken) fails the prover."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)
    shell = bundle / f"{mutant.slug}.json"
    doc = json.loads(shell.read_text(encoding="utf-8"))
    doc["start_node"] = "n_does_not_exist"  # dangling start: gate/reachability breaks
    shell.write_text(json.dumps(doc), encoding="utf-8")
    reasons = cpb.prove_shell(shell, skeletons_root=_REAL_SKELETONS)
    assert any("check_skeleton" in reason for reason in reasons)


def test_prove_shell_stale_parent_fails(mutant: _MutantParts, tmp_path: Path) -> None:
    """A parent edited after bundling (hash mismatch) fails the lineage/hash check."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)
    shell = bundle / f"{mutant.slug}.json"
    # A tmp catalog root whose parent copy has been edited since derivation.
    stale_root = tmp_path / "skeletons"
    band_dir = stale_root / mutant.band
    band_dir.mkdir(parents=True)
    distant_entry = load_catalog().by_slug(_DISTANT_PARENT)
    assert distant_entry is not None
    edited = dict(distant_entry.document)
    edited["title"] = "EDITED SINCE DERIVATION"
    (band_dir / f"{_DISTANT_PARENT}.json").write_text(
        json.dumps(edited), encoding="utf-8"
    )
    reasons = cpb.prove_shell(shell, skeletons_root=stale_root)
    assert any("mismatch" in reason or "changed since" in reason for reason in reasons)


def test_prove_shell_missing_lineage_fails(
    mutant: _MutantParts, tmp_path: Path
) -> None:
    """A shell whose lineage sidecar is absent fails the prover."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)
    (bundle / f"{mutant.slug}.lineage.json").unlink()
    shell = bundle / f"{mutant.slug}.json"
    reasons = cpb.prove_shell(shell, skeletons_root=_REAL_SKELETONS)
    assert any("missing lineage" in reason for reason in reasons)


# --------------------------------------------------------------------------- #
# prepare_promotion_pr: refusals, dry run, and the worktree sandbox.
# --------------------------------------------------------------------------- #


class _FakeGitRunner:
    """A git seam that never touches git; records calls, optionally seeds a worktree."""

    def __init__(self, branch: str, *, seed: Path | None = None) -> None:
        self.branch = branch
        self.seed = seed
        self.worktrees: list[tuple[Path, str]] = []

    def current_branch(self) -> str:
        return self.branch

    def add_worktree(self, worktree_dir: Path, branch: str) -> None:
        self.worktrees.append((worktree_dir, branch))
        if self.seed is not None:
            shutil.copytree(self.seed, worktree_dir)


class _RecordingPrCreator:
    """A PR creator that records requests and asserts by inspection (never merges)."""

    def __init__(self) -> None:
        self.calls: list[ppr.PrRequest] = []

    def __call__(self, request: ppr.PrRequest, *, worktree_dir: Path) -> None:
        _ = worktree_dir
        self.calls.append(request)


def _write_minimal_bundle(
    bundle_dir: Path,
    *,
    slug: str = "m-mutant",
    promotable: bool = True,
    fully_resolved: bool = True,
    parent_slug: str = "some-parent",
    parent_sha256: str = "deadbeef",
    band: str = "8-11",
) -> None:
    """Write a bundle sufficient for prepare's refusal checks (no gate needed)."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shell = {
        "id": slug,
        "metadata": {"age_band": band},
        "nodes": [{"id": "n_start", "is_ending": True, "body": "x"}],
        "start_node": "n_start",
    }
    (bundle_dir / f"{slug}.json").write_text(json.dumps(shell), encoding="utf-8")
    lineage = Lineage(
        lineage_version=1,
        mutant_slug=slug,
        parent_slug=parent_slug,
        parent_sha256=parent_sha256,
        donor_slugs=[],
        op_chain=[OpChainEntry(op_id="M2")],
        created_at="2026-07-21T00:00:00+00:00",
        tool_version="test",
        acceptance_digest="abc123",
    )
    (bundle_dir / f"{slug}.lineage.json").write_text(
        lineage.model_dump_json(), encoding="utf-8"
    )
    (bundle_dir / "acceptance.json").write_text(
        json.dumps({"promotable": promotable}), encoding="utf-8"
    )
    (bundle_dir / "reguide.json").write_text(
        json.dumps({"fully_resolved": fully_resolved, "items": []}), encoding="utf-8"
    )


def test_prepare_refuses_on_main_branch(tmp_path: Path) -> None:
    """The script exits non-zero and opens nothing when the branch is main."""
    bundle = tmp_path / "b"
    _write_minimal_bundle(bundle)
    creator = _RecordingPrCreator()
    code = ppr.main(
        [str(bundle)],
        git_runner=_FakeGitRunner("main"),
        pr_creator=creator,
    )
    assert code == 1
    assert creator.calls == []


def test_prepare_refuses_not_promotable(tmp_path: Path) -> None:
    """A held (not promotable) bundle is refused before any PR is prepared."""
    bundle = tmp_path / "b"
    _write_minimal_bundle(bundle, promotable=False)
    creator = _RecordingPrCreator()
    code = ppr.main(
        [str(bundle), "--skeletons-root", str(tmp_path)],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )
    assert code == 1
    assert creator.calls == []


def test_prepare_refuses_not_fully_resolved(tmp_path: Path) -> None:
    """A bundle with outstanding re-guidance is refused."""
    bundle = tmp_path / "b"
    _write_minimal_bundle(bundle, fully_resolved=False)
    creator = _RecordingPrCreator()
    code = ppr.main(
        [str(bundle), "--skeletons-root", str(tmp_path)],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )
    assert code == 1
    assert creator.calls == []


def test_prepare_refuses_verify_mismatch(tmp_path: Path) -> None:
    """A promotable, resolved bundle whose parent cannot verify is refused."""
    bundle = tmp_path / "b"
    # skeletons_root is empty: the parent is not found, so verify_bundle fails.
    empty_root = tmp_path / "skeletons"
    empty_root.mkdir()
    _write_minimal_bundle(bundle, promotable=True, fully_resolved=True)
    creator = _RecordingPrCreator()
    code = ppr.main(
        [str(bundle), "--skeletons-root", str(empty_root)],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )
    assert code == 1
    assert creator.calls == []


def test_prepare_dry_run_success_prints_draft_and_opens_no_pr(
    mutant: _MutantParts, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The dry run prints the draft gh command, creates no worktree, opens no PR."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)
    runner = _FakeGitRunner("claude/ws8")
    code = ppr.main(
        [str(bundle), "--skeletons-root", str(_REAL_SKELETONS)],
        git_runner=runner,
        # Default dry-run creator (prints); no injected creator.
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "gh pr create --draft --label skeleton-promotion" in out
    assert runner.worktrees == []  # dry run creates no worktree


def test_prepare_create_stages_into_worktree_and_calls_draft_creator(
    mutant: _MutantParts, tmp_path: Path
) -> None:
    """--create stages files into the worktree and calls the creator with draft+label."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)

    # A minimal worktree seed: one real catalog skeleton + a catalog doc with the
    # generated-region markers, so catalog regeneration runs inside the worktree.
    seed = tmp_path / "seed"
    (seed / "skeletons" / "8-11").mkdir(parents=True)
    shutil.copyfile(
        _REAL_SKELETONS / "8-11" / "the-cave-of-echoes.json",
        seed / "skeletons" / "8-11" / "the-cave-of-echoes.json",
    )
    catalog_doc = seed / "docs" / "architecture" / "story-skeletons.md"
    catalog_doc.parent.mkdir(parents=True)
    catalog_doc.write_text(
        "# Catalog\n\n"
        "<!-- BEGIN GENERATED: skeleton-catalog -->\n"
        "<!-- END GENERATED: skeleton-catalog -->\n",
        encoding="utf-8",
    )

    runner = _FakeGitRunner("feature/x", seed=seed)
    creator = _RecordingPrCreator()
    worktrees_root = tmp_path / "worktrees"
    code = ppr.main(
        [
            str(bundle),
            "--skeletons-root",
            str(_REAL_SKELETONS),
            "--worktrees-root",
            str(worktrees_root),
            "--create",
        ],
        git_runner=runner,
        pr_creator=creator,
    )
    assert code == 0
    assert len(creator.calls) == 1
    request = creator.calls[0]
    assert request.draft is True
    assert ppr.PROMOTION_LABEL in request.labels
    assert request.base == "main"
    assert request.head == f"flywheel/promote-{mutant.slug}"

    # The shell was staged inside the worktree, under skeletons/<band>/.
    worktree = worktrees_root / f"promote-{mutant.slug}"
    staged = worktree / "skeletons" / mutant.band / f"{mutant.slug}.json"
    assert staged.is_file()


def test_prepare_sandbox_never_writes_outside_worktree(
    mutant: _MutantParts, tmp_path: Path
) -> None:
    """stage_into_worktree writes only inside the worktree; the real catalog is untouched."""
    bundle = tmp_path / mutant.slug
    _write_valid_bundle(bundle, mutant)
    loaded = ppr.load_bundle(bundle)

    seed = tmp_path / "seed"
    (seed / "skeletons" / "8-11").mkdir(parents=True)
    shutil.copyfile(
        _REAL_SKELETONS / "8-11" / "the-cave-of-echoes.json",
        seed / "skeletons" / "8-11" / "the-cave-of-echoes.json",
    )
    worktree = tmp_path / "wt"
    shutil.copytree(seed, worktree)

    written = ppr.stage_into_worktree(worktree, loaded)

    assert written  # something was written
    root = worktree.resolve()
    for path in written:
        assert path.resolve().is_relative_to(root), f"{path} escaped the worktree"
    # The real catalog never gained the mutant.
    assert not (_REAL_SKELETONS / mutant.band / f"{mutant.slug}.json").exists()


def test_assert_within_rejects_paths_outside_the_worktree(tmp_path: Path) -> None:
    """The write-sandbox guard raises when a target path escapes the worktree."""
    worktree = tmp_path / "wt"
    worktree.mkdir()
    with pytest.raises(RuntimeError):
        ppr._assert_within(worktree, tmp_path / "elsewhere" / "escape.json")


def test_scripts_declare_no_merge_or_automerge_path() -> None:
    """Neither D4 script contains a merge/approve/auto-merge code path (safety property)."""
    for script in ("prepare_promotion_pr.py", "check_promotion_bundle.py"):
        source = (_REPO_ROOT / "scripts" / script).read_text(encoding="utf-8").lower()
        assert "--auto" not in source
        assert "pr merge" not in source
        assert "merge_pull_request" not in source
        assert "pr review" not in source
        assert "--approve" not in source
