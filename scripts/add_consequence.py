"""Give stateless skeletons plants and payoffs (dry run by default).

Usage::

    uv run python scripts/add_consequence.py skeletons/10-13/the-blackout-week.json
    uv run python scripts/add_consequence.py skeletons/*/*.json --json out.json
    uv run python scripts/add_consequence.py <skeleton.json> --write

For each skeleton it runs
:func:`cyo_adventure.mutation.state_promotion.promote_skeleton` and prints one
block: the status (``promoted``, ``refused`` with the reason, or ``skipped``
because the skeleton already declares state), each plant and payoff it placed,
and the before/after numbers (merges, variables, conditional choices, false
forks by the consequence measure, gate result, walk size). Nothing is written
unless ``--write`` is passed, and even then only a ``promoted`` skeleton is
rewritten, in place, in the file's own JSON formatting. Sidecars are read, never
written: the edit adds no ``{SLOT}`` token (so a theme contract still matches),
and a ``.narrative.json`` sidecar is a refusal.

Promotion is a PR, never a script side effect: review the diff, run
``scripts/check_skeleton.py`` (and ``scripts/check_theme_contract.py`` for a
parameterized skeleton), and commit by hand.

Exit status: 0 when every input was promoted or skipped, 1 when any was refused
(so a dry run over the corpus doubles as a coverage report).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.core.exceptions import ProjectBaseError  # noqa: E402
from cyo_adventure.generation.binding import (  # noqa: E402
    load_contract_for,
    render_bound_skeleton,
)
from cyo_adventure.mutation.state_promotion import (  # noqa: E402
    PromotionReport,
    StateMetrics,
    measure_state,
    promote_skeleton,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_SIDECAR_SUFFIXES: Final[tuple[str, ...]] = (
    ".contract.json",
    ".narrative.json",
    ".lineage.json",
)


def _is_skeleton(path: Path) -> bool:
    return path.suffix == ".json" and not path.name.endswith(_SIDECAR_SUFFIXES)


def _dump_like(raw: str, doc: object) -> str:
    """Serialize ``doc`` in the same JSON formatting ``raw`` uses.

    The catalog mixes ``indent=1`` and ``indent=2`` files, ASCII-escaped and
    not; rewriting a file in a different style would bury the real change in a
    whitespace diff.

    Args:
        raw: The file's original text.
        doc: The document to write.

    Returns:
        The serialized text, with a trailing newline.
    """
    original = json.loads(raw)
    for indent in (2, 1, 4):
        for ensure_ascii in (True, False):
            if (
                json.dumps(original, indent=indent, ensure_ascii=ensure_ascii) + "\n"
                == raw
            ):
                return json.dumps(doc, indent=indent, ensure_ascii=ensure_ascii) + "\n"
    return json.dumps(doc, indent=2, ensure_ascii=True) + "\n"


def _check_contract(path: Path, report: PromotionReport) -> PromotionReport:
    """Refuse a promoted candidate its theme contract can no longer render.

    The promotion adds no slot token, but it does copy slotted choice labels
    into new places; ``render_bound_skeleton`` with the contract's default
    binding is the same check ``check_theme_contract.py`` (check 6) and the
    promotion prover run, so a candidate that fails it is refused here rather
    than discovered in CI.

    Args:
        path: The skeleton path (its sidecar is derived from it).
        report: The promotion report.

    Returns:
        The report unchanged, or a refusal carrying the render error.
    """
    if report.candidate is None:
        return report
    try:
        contract = load_contract_for(path, report.candidate)
        if contract is None:
            return report
        render_bound_skeleton(report.candidate, contract.default_binding)
    except ProjectBaseError as exc:
        return PromotionReport(
            report.story_id, "refused", f"theme contract no longer renders: {exc}"
        )
    return report


def _metrics_line(label: str, m: StateMetrics) -> str:
    gate = "BLOCKED" if m.gate_blocked else "pass"
    return (
        f"    {label:6} nodes={m.nodes} merges={m.merges} variables={m.variables} "
        f"conditional_choices={m.conditional_choices} false_forks={m.false_forks}/"
        f"{m.forks} gate={gate} errors={m.gate_errors} "
        f"warnings={sum(m.gate_warnings.values())} walk_configs={m.walk_configs}"
        f"{' CAPPED' if m.walk_capped else ''}"
    )


def _metrics_dict(m: StateMetrics) -> dict[str, object]:
    return {
        "nodes": m.nodes,
        "merges": m.merges,
        "variables": m.variables,
        "conditional_choices": m.conditional_choices,
        "forks": m.forks,
        "false_forks": m.false_forks,
        "walk_configs": m.walk_configs,
        "walk_capped": m.walk_capped,
        "gate_blocked": m.gate_blocked,
        "gate_errors": m.gate_errors,
        "gate_warnings": dict(sorted(m.gate_warnings.items())),
    }


def _report_dict(
    path: Path,
    report: PromotionReport,
    before: StateMetrics | None,
    after: StateMetrics | None,
) -> dict[str, object]:
    return {
        "path": str(path),
        "status": report.status,
        "reason": report.reason,
        "plants": [
            {
                "variable": p.variable,
                "fork": p.fork_id,
                "choice": p.choice_id,
                "label": p.label,
                "site": p.site_id,
                "inserted_arrival": p.inserted_arrival,
            }
            for p in report.plants
        ],
        "payoffs": [
            {
                "variable": p.variable,
                "node": p.node_id,
                "kind": p.kind,
                "choice": p.choice_id,
                "gated_choice": p.gated_choice_id,
                "label": p.label,
                "scene": p.scene_id,
                "rejoin": p.rejoin_id,
                "setback_ending": p.setback_ending,
            }
            for p in report.payoffs
        ],
        "ending_changing": list(report.ending_changing),
        "merges_annotated": report.merges_annotated,
        "notes": list(report.notes),
        "before": _metrics_dict(before) if before else None,
        "after": _metrics_dict(after) if after else None,
    }


def _print_report(
    path: Path,
    report: PromotionReport,
    before: StateMetrics | None,
    after: StateMetrics | None,
) -> None:
    print(f"\n{path}: {report.status.upper()}")
    if report.reason:
        print(f"    reason: {report.reason}")
    for plant in report.plants:
        where = "inserted arrival" if plant.inserted_arrival else "annotated target"
        print(
            f"    plant  {plant.variable}: {plant.fork_id}/{plant.choice_id} "
            f'"{plant.label}" -> {plant.site_id} ({where})'
        )
    for payoff in report.payoffs:
        extra = (
            f", ungated twin runs into {payoff.setback_ending}"
            if payoff.setback_ending
            else ""
        )
        changes = (
            " [changes reachable endings]"
            if payoff.kind == "rescue" and payoff.variable in report.ending_changing
            else ""
        )
        print(
            f"    payoff {payoff.variable}: {payoff.kind} at {payoff.node_id} "
            f'"{payoff.label}" -> {payoff.scene_id} -> {payoff.rejoin_id}{extra}{changes}'
        )
    if report.status == "promoted":
        print(f"    merge directives annotated: {report.merges_annotated}")
    for note in report.notes:
        print(f"    note: {note}")
    if before is not None:
        print(_metrics_line("before", before))
    if after is not None:
        print(_metrics_line("after", after))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the tool over the given skeletons.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status (0 when nothing was refused).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeletons", nargs="+", type=Path)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite each promoted skeleton in place (default: dry run).",
    )
    parser.add_argument(
        "--variables",
        type=int,
        default=None,
        help="Target variable count (2-4; default by length: short 2, medium 3, long 4).",
    )
    parser.add_argument("--allow-mvp", action="store_true")
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Also measure before/after numbers (runs the gate twice more).",
    )
    parser.add_argument("--json", type=Path, default=None, dest="json_out")
    args = parser.parse_args(argv)

    rows: list[dict[str, object]] = []
    counts: dict[str, int] = {"promoted": 0, "refused": 0, "skipped": 0}
    for path in [p for p in args.skeletons if _is_skeleton(p)]:
        raw = path.read_text(encoding="utf-8")
        skeleton = json.loads(raw)
        sidecar = path.with_name(path.name.removesuffix(".json") + ".narrative.json")
        report = promote_skeleton(
            skeleton,
            target_variables=args.variables,
            allow_mvp=args.allow_mvp,
            has_narrative_sidecar=sidecar.exists(),
        )
        report = _check_contract(path, report)
        counts[report.status] += 1
        before = after = None
        if args.metrics and report.candidate is not None:
            before = measure_state(skeleton)
            after = measure_state(report.candidate)
        _print_report(path, report, before, after)
        rows.append(_report_dict(path, report, before, after))
        if args.write and report.candidate is not None:
            path.write_text(_dump_like(raw, report.candidate), encoding="utf-8")
            print(f"    wrote {path}")

    print(
        f"\nSUMMARY: {counts['promoted']} promoted, {counts['refused']} refused, "
        f"{counts['skipped']} skipped (already stateful) of {sum(counts.values())}"
        + ("" if args.write else " (dry run, nothing written)")
    )
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"counts": counts, "skeletons": rows}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.json_out}")
    return 1 if counts["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
