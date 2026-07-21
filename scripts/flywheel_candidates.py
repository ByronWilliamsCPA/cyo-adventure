#!/usr/bin/env python3
"""Plan and run WS-8 flywheel candidates for one saturated cell (design 6, S2-S5).

Given a saturated ``(band, length, style)`` cell, this operator-facing CLI:

1. loads the catalog and the discard ledger;
2. plans the bounded attempt set (``strategy.plan_attempts``), skipping any
   ``attempt_sig`` the ledger already knows;
3. runs each attempt through the UNCHANGED WS-5 engine (``apply_chain`` then
   ``run_chain_acceptance``), recording every outcome to the ledger;
4. ranks the survivors by the section 6.4 precedence and writes the single best
   candidate's promotion bundle via the existing ``write_bundle``; the
   non-selected survivors are recorded as ``shelved`` (re-derivable next cycle).

    uv run python scripts/flywheel_candidates.py --band 8-11 --length short --style prose

It writes ONLY under ``out/`` (the bundle and the ledger); it never writes under
``skeletons/`` and it opens no pull request (that is D4). Re-guidance resolution
is D3, so a held candidate (one that cleared every acceptance stage but still
carries outstanding re-guidance) is a valid, bundle-able survivor here.

Exit codes:
    0 - a report was printed (whether or not a bundle was written).
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyo_adventure import __version__
from cyo_adventure.flywheel.ledger import (
    OUTCOME_DISCARDED,
    OUTCOME_HELD,
    OUTCOME_PROMOTABLE,
    OUTCOME_SHELVED,
    AttemptRecord,
    append_record,
    chain_signature,
    ledger_path,
    load_outcomes,
)
from cyo_adventure.flywheel.strategy import (
    Catalog,
    Cell,
    compute_candidate_metrics,
    load_catalog,
    plan_attempts,
    ranking_key,
)
from cyo_adventure.generation.diagram import skeleton_to_plantuml
from cyo_adventure.mutation.acceptance import acceptance_to_dict
from cyo_adventure.mutation.bundle import (
    build_lineage,
    derive_mutant_contract,
    write_bundle,
)
from cyo_adventure.mutation.compose import (
    ChainResult,
    apply_chain,
    run_chain_acceptance,
)
from cyo_adventure.mutation.floors import load_in_cell_catalog
from cyo_adventure.mutation.reguide import reconcile
from cyo_adventure.storybook.theme_contract import ThemeContract

if TYPE_CHECKING:
    from cyo_adventure.flywheel.strategy import AttemptPlan, CandidateMetrics
    from cyo_adventure.mutation.acceptance import AcceptanceResult

_DEFAULT_OUT_DIR = Path("out") / "mutations"


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser.

    Returns:
        argparse.ArgumentParser: The parser for the candidates CLI.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--band", required=True, help="Age band, e.g. 8-11.")
    _ = parser.add_argument(
        "--length", required=True, help="Length tier, e.g. short/medium/long."
    )
    _ = parser.add_argument(
        "--style", required=True, help="Narrative style, e.g. prose/gamebook."
    )
    _ = parser.add_argument(
        "--out-dir",
        default=str(_DEFAULT_OUT_DIR),
        help=f"Bundle output root under out/ (default: {_DEFAULT_OUT_DIR}).",
    )
    _ = parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PARENT_SLUG",
        help="A parent slug to exclude (an open promotion PR; repeatable).",
    )
    return parser


def _load_contract(catalog: Catalog, slug: str) -> ThemeContract | None:
    """Load a catalog skeleton's theme contract by slug, or None if contract-less.

    Args:
        catalog: The catalog scan (an entry's path locates its sidecar).
        slug: The skeleton slug.

    Returns:
        ThemeContract | None: The parsed contract, or None when absent/unreadable.
    """
    entry = catalog.by_slug(slug)
    if entry is None:
        return None
    sidecar = entry.path.with_name(f"{slug}.contract.json")
    if not sidecar.is_file():
        return None
    try:
        return ThemeContract.model_validate_json(sidecar.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _mutant_contract(
    catalog: Catalog, chain: ChainResult, parent_slug: str, mutant_slug: str
) -> ThemeContract | None:
    """Derive the mutant's theme contract, mirroring the mutate CLI (design 4.7).

    Args:
        catalog: The catalog scan (contracts are loaded from its entries).
        chain: The applied chain (its donor slugs pull donor contracts).
        parent_slug: The host (parent) slug.
        mutant_slug: The mutant slug the derived contract is keyed to.

    Returns:
        ThemeContract | None: The mutant contract, or None for a contract-less
            parent whose mutant carries no slot tokens.
    """
    host_contract = _load_contract(catalog, parent_slug)
    if host_contract is None:
        return None
    donor_contracts: dict[str, ThemeContract] = {parent_slug: host_contract}
    for donor_slug in chain.donor_slugs:
        donor_contract = _load_contract(catalog, donor_slug)
        if donor_contract is not None:
            donor_contracts[donor_slug] = donor_contract
    return derive_mutant_contract(
        chain.candidate,
        mutant_slug=mutant_slug,
        host_contract=host_contract,
        donor_contracts=donor_contracts,
    )


class _Survivor:
    """A surviving candidate awaiting ranking and bundling.

    Attributes:
        plan: The attempt plan that produced it.
        chain: The applied chain (its candidate is the mutant shell).
        result: The acceptance result (promotable or held).
        metrics: The section 6.4 ranking metrics.
        contract: The derived mutant contract, or None.
    """

    __slots__ = ("chain", "contract", "metrics", "plan", "result")

    def __init__(
        self,
        *,
        plan: AttemptPlan,
        chain: ChainResult,
        result: AcceptanceResult,
        metrics: CandidateMetrics,
        contract: ThemeContract | None,
    ) -> None:
        self.plan = plan
        self.chain = chain
        self.result = result
        self.metrics = metrics
        self.contract = contract


def _mutant_slug(plan: AttemptPlan) -> str:
    """Return a deterministic, unique bundle slug for an attempt."""
    return f"{plan.parent_slug}-fw-{plan.attempt_sig[:8]}"


def _run_one(
    catalog: Catalog, plan: AttemptPlan
) -> tuple[_Survivor | None, AttemptRecord]:
    """Run one attempt end to end and return its survivor (or None) and record.

    Applies the chain, derives the mutant contract, runs the unchanged acceptance
    harness, and builds the ledger record. A discarded attempt yields no survivor;
    a promotable or held one yields a :class:`_Survivor` carrying its 6.4 metrics.

    Args:
        catalog: The catalog scan.
        plan: The attempt plan to run.

    Returns:
        tuple: ``(survivor_or_none, attempt_record)``.
    """
    parent_entry = catalog.by_slug(plan.parent_slug)
    if parent_entry is None:  # pragma: no cover -- plan parents come from catalog
        msg = f"parent {plan.parent_slug!r} vanished from the catalog"
        raise ValueError(msg)
    parent = parent_entry.document
    chain = apply_chain(parent, plan.steps)
    slug = _mutant_slug(plan)
    contract = _mutant_contract(catalog, chain, plan.parent_slug, slug)
    result = run_chain_acceptance(
        parent, chain, parent_slug=plan.parent_slug, mutated_contract=contract
    )
    timestamp = datetime.datetime.now(datetime.UTC).isoformat()
    if result.discarded_at_stage is not None:
        record = AttemptRecord(
            attempt_sig=plan.attempt_sig,
            parent_slug=plan.parent_slug,
            parent_sha256=plan.parent_sha256,
            cell=plan.cell.as_dict(),
            chain=chain_signature(plan.steps),
            outcome=OUTCOME_DISCARDED,
            failing_stage=str(result.discarded_at_stage),
            discard_reason=result.discard_reason,
            distances={},
            timestamp=timestamp,
        )
        return None, record
    siblings = load_in_cell_catalog(chain.candidate, plan.parent_slug)
    metrics = compute_candidate_metrics(
        chain.candidate,
        parent,
        siblings,
        reguide_count=len(chain.reguide),
        seed=plan.seed,
    )
    outcome = OUTCOME_PROMOTABLE if result.promotable else OUTCOME_HELD
    record = AttemptRecord(
        attempt_sig=plan.attempt_sig,
        parent_slug=plan.parent_slug,
        parent_sha256=plan.parent_sha256,
        cell=plan.cell.as_dict(),
        chain=chain_signature(plan.steps),
        outcome=outcome,
        failing_stage=None,
        discard_reason="",
        distances={
            "parent_distance": metrics.parent_distance,
            "min_in_cell_distance": metrics.min_in_cell_distance,
        },
        timestamp=timestamp,
    )
    survivor = _Survivor(
        plan=plan, chain=chain, result=result, metrics=metrics, contract=contract
    )
    return survivor, record


def _write_best_bundle(out_root: Path, catalog: Catalog, best: _Survivor) -> Path:
    """Write the best survivor's promotion bundle and return its directory.

    Reuses the exact WS-5 bundle writer (shell, lineage, acceptance transcript,
    re-guidance, contract, diagram); no sample-fill evidence is generated here
    (that is bundle-time mock evidence, added by the mutate CLI / D4).

    Args:
        out_root: The bundle output root under ``out/``.
        catalog: The catalog scan (unused beyond the parent already on the plan).
        best: The selected survivor.

    Returns:
        Path: The written bundle directory.
    """
    plan = best.plan
    slug = _mutant_slug(plan)
    parent_entry = catalog.by_slug(plan.parent_slug)
    parent = parent_entry.document if parent_entry is not None else {}
    acceptance = acceptance_to_dict(best.result)
    lineage = build_lineage(
        mutant_slug=slug,
        parent=parent,
        parent_slug=plan.parent_slug,
        op_chain=list(best.chain.op_chain),
        donor_slugs=best.chain.donor_slugs,
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        tool_version=__version__,
        acceptance=acceptance,
    )
    return write_bundle(
        out_root,
        slug=slug,
        candidate=best.chain.candidate,
        lineage=lineage,
        acceptance=acceptance,
        reguide=reconcile(best.chain.reguide),
        contract=best.contract,
        diagram_puml=skeleton_to_plantuml(best.chain.candidate, name=slug),
    )


def _format_survivor(survivor: _Survivor, *, selected: bool) -> str:
    """Render one survivor as a report line."""
    plan = survivor.plan
    metrics = survivor.metrics
    marker = "*" if selected else " "
    status = OUTCOME_PROMOTABLE if survivor.result.promotable else OUTCOME_HELD
    return (
        f"  {marker} {plan.template_id} parent={plan.parent_slug} seed={plan.seed} "
        f"{status} min_in_cell={metrics.min_in_cell_distance:.4f} "
        f"parent_dist={metrics.parent_distance:.4f} reguide={metrics.reguide_count}"
    )


def _render_report(
    cell: Cell,
    *,
    planned: int,
    known_records: int,
    survivors: list[_Survivor],
    best: _Survivor | None,
    bundle_dir: Path | None,
) -> str:
    """Build the plain-text run report.

    Args:
        cell: The cell that was planned.
        planned: The number of fresh attempts run this cycle (already excludes any
            attempt whose signature the ledger knew: ``plan_attempts`` returns only
            unseen plans).
        known_records: The number of records already in the ledger at load time
            (the replay memory this cycle planned around).
        survivors: The surviving candidates, best-first.
        best: The selected survivor, or None when none survived.
        bundle_dir: The written bundle directory, or None.

    Returns:
        str: The report ending in a newline.
    """
    coordinate = f"band={cell.band} length={cell.length} style={cell.style}"
    header = f"CYO Adventure flywheel candidates: cell {coordinate}"
    tallies = f"ledger records loaded: {known_records} | survivors: {len(survivors)}"
    counts = f"fresh attempts run: {planned} | {tallies}"
    lines = [
        header,
        counts,
        "",
        "survivors (best-first; * = selected for bundling):",
    ]
    best_sig = best.plan.attempt_sig if best is not None else None
    lines.extend(
        _format_survivor(s, selected=s.plan.attempt_sig == best_sig) for s in survivors
    )
    if not survivors:
        lines.append("  (none)")
    lines.append("")
    if bundle_dir is not None:
        lines.append(f"wrote bundle: {bundle_dir}")
    else:
        lines.append("no bundle written (no surviving candidate)")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Plan, run, rank, and bundle flywheel candidates for one cell.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        int: ``0`` on a printed report, ``2`` on an argparse usage error.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    cell = Cell(
        band=cast("str", args.band),
        length=cast("str", args.length),
        style=cast("str", args.style),
    )
    out_root = Path(cast("str", args.out_dir)).resolve()
    excluded = frozenset(cast("list[str]", args.exclude))

    catalog = load_catalog()
    path = ledger_path(Path.cwd())
    known = load_outcomes(path)
    known_records = len(known)
    plans = plan_attempts(cell, catalog, known, excluded_parent_slugs=excluded)

    survivors: list[_Survivor] = []
    for plan in plans:
        survivor, record = _run_one(catalog, plan)
        append_record(path, record)
        if survivor is not None:
            survivors.append(survivor)

    survivors.sort(key=lambda s: ranking_key(s.metrics))
    best = survivors[0] if survivors else None

    bundle_dir: Path | None = None
    if best is not None:
        bundle_dir = _write_best_bundle(out_root, catalog, best)
        # Non-selected survivors are re-derivable next cycle: record them shelved
        # so the ledger reflects that they were considered (design 6.4).
        for survivor in survivors[1:]:
            append_record(
                path,
                AttemptRecord(
                    attempt_sig=survivor.plan.attempt_sig,
                    parent_slug=survivor.plan.parent_slug,
                    parent_sha256=survivor.plan.parent_sha256,
                    cell=survivor.plan.cell.as_dict(),
                    chain=chain_signature(survivor.plan.steps),
                    outcome=OUTCOME_SHELVED,
                    failing_stage=None,
                    discard_reason="",
                    distances={
                        "parent_distance": survivor.metrics.parent_distance,
                        "min_in_cell_distance": survivor.metrics.min_in_cell_distance,
                    },
                    timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                ),
            )

    sys.stdout.write(
        _render_report(
            cell,
            planned=len(plans),
            known_records=known_records,
            survivors=survivors,
            best=best,
            bundle_dir=bundle_dir,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
