"""Check a Story Plan against its filled book (ADR-033 SP-0 to SP-9, WP-1.2).

Usage:
    uv run python scripts/check_story_plan.py out/<slug>.filled.json
        [out/<slug>.plan.json] [--json] [--must-not-assert]
        [--assertions <node-assertions.json>]
    uv run python scripts/check_story_plan.py out/<slug>.filled.json --shape-hash
    uv run python scripts/check_story_plan.py --verify-witnesses

The plan path defaults to the book path with ``.filled.json`` (or ``.json``)
replaced by ``.plan.json``. Every finding names its rule, node, choice, a
witness state, the fact concerned and, for path rules, a witness route. The
checks are deterministic and read no prose and call no model.

``--shape-hash`` prints the two binding values, then exits: the graph hash for
``provenance.shape`` (``{"id": <book id>, "hash": ...}``) and the file hash for
``provenance.book_sha256``. Use it to bind a new plan.

``--must-not-assert`` adds, per reachable node, the ledger facts its prose must
not assert (ADR-033's computed ``must_not_assert``).

``--assertions`` takes a JSON object mapping node id to the fact ids that
node's prose asserts (the WP-1.4 assertion file) and adds an SP-A finding for
each asserted fact some route enters the node without.

``--verify-witnesses`` runs the built-in clean plan and at least one witness
per rule (two for SP-4 and SP-9 since the G1 revision of 2026-11-21) and fails
if any rule stopped firing or fires where it should not.

Exit codes: 0 no ERROR finding; 1 ERROR findings or a plan that fails schema
validation; 2 a file that cannot be read or parsed, or a book that fails the
Storybook schema.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan.checks import (
    check_assertions,
    check_plan,
    must_not_assert,
    verify_witnesses,
)
from cyo_adventure.storyplan.models import StoryPlan, book_sha256, shape_hash

if TYPE_CHECKING:
    from cyo_adventure.validator.report import ValidationFinding, ValidationReport

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_UNREADABLE = 2


def default_plan_path(book_path: Path) -> Path:
    """Return the conventional plan path beside a book.

    Args:
        book_path: The book file, usually ``out/<slug>.filled.json``.

    Returns:
        Path: ``out/<slug>.plan.json``.
    """
    name = book_path.name
    for suffix in (".filled.json", ".json"):
        if name.endswith(suffix):
            return book_path.with_name(name.removesuffix(suffix) + ".plan.json")
    return book_path.with_name(name + ".plan.json")


def _load_json(path: Path) -> object | None:
    """Read and decode a JSON file, reporting failure on stderr.

    Args:
        path: The file to read.

    Returns:
        object | None: The decoded value, or None when unreadable or malformed.
    """
    try:
        return cast("object", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"FAIL: cannot load {path}: {exc}\n")
        return None


def _load_book(path: Path) -> tuple[Storybook, str] | None:
    """Load and validate a Storybook, and hash the file's bytes.

    Args:
        path: The book file.

    Returns:
        tuple[Storybook, str] | None: The book and the SHA-256 hex of the file
            as stored (for ``provenance.book_sha256``), or None on any failure
            (already reported).
    """
    try:
        raw_bytes = path.read_bytes()
        raw = cast("object", json.loads(raw_bytes))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"FAIL: cannot load {path}: {exc}\n")
        return None
    try:
        return Storybook.model_validate(raw), book_sha256(raw_bytes)
    except ValidationError as exc:
        sys.stderr.write(f"FAIL: {path} is not a valid Storybook:\n{exc}\n")
        return None


def _format_finding(finding: ValidationFinding) -> str:
    """Render one finding as a text line (plus an indented route line).

    Args:
        finding: The finding.

    Returns:
        str: The rendered text, without a trailing newline.
    """
    data = finding.to_dict()
    parts = [str(data["severity"]).upper(), str(data["rule_id"])]
    parts.extend(
        f"{key}={data[key]}"
        for key in ("node_id", "choice_id", "fact_id")
        if data.get(key) is not None
    )
    if data.get("state") is not None:
        parts.append(f"state=[{data['state']}]")
    line = " ".join(parts) + f": {data['message']}"
    if data.get("route") is not None:
        line += f"\n    route: {data['route']}"
    return line


def _parse_assertions(path: Path) -> dict[str, list[str]] | None:
    """Load a node-to-asserted-facts map.

    Args:
        path: The assertion file.

    Returns:
        dict[str, list[str]] | None: The map, or None when malformed.
    """
    raw = _load_json(path)
    if not isinstance(raw, dict):
        if raw is not None:
            sys.stderr.write(f"FAIL: {path} must be a JSON object of node ids\n")
        return None
    out: dict[str, list[str]] = {}
    for node_id, facts in cast("dict[str, object]", raw).items():
        if not isinstance(facts, list) or not all(
            isinstance(f, str) for f in cast("list[object]", facts)
        ):
            sys.stderr.write(f"FAIL: {path}: {node_id!r} must map to a list of ids\n")
            return None
        out[node_id] = cast("list[str]", facts)
    return out


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser.

    Returns:
        argparse.ArgumentParser: The parser.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("book", nargs="?", help="The filled book JSON.")
    parser.add_argument("plan", nargs="?", help="The plan JSON (default: beside book).")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--shape-hash", action="store_true", help="Print the hash.")
    parser.add_argument(
        "--must-not-assert", action="store_true", help="Add per-node must_not_assert."
    )
    parser.add_argument("--assertions", default=None, help="Node assertion map JSON.")
    parser.add_argument(
        "--verify-witnesses", action="store_true", help="Self-test every rule."
    )
    return parser


def _run_witnesses() -> int:
    """Run the witness self-test.

    Returns:
        int: The exit code.
    """
    problems = verify_witnesses()
    for problem in problems:
        sys.stderr.write(f"FAIL {problem}\n")
    if not problems:
        sys.stdout.write("ok: every SP rule fires on its witness and only there\n")
    return EXIT_FINDINGS if problems else EXIT_OK


def _bound_to(plan: StoryPlan) -> str:
    """Name what a plan says it is bound to, for the report header.

    Args:
        plan: The plan.

    Returns:
        str: ``shape <id>``, ``book file <sha256 prefix>``, both, or ``nothing``.
    """
    provenance = plan.provenance
    parts: list[str] = []
    if provenance.shape is not None:
        parts.append(f"shape {provenance.shape.id}")
    if provenance.book_sha256 is not None:
        parts.append(f"book file {provenance.book_sha256[:12]}")
    return " and ".join(parts) or "nothing"


def _emit(
    args: argparse.Namespace,
    book: Storybook,
    plan: StoryPlan,
    report: ValidationReport,
    mna: dict[str, frozenset[str]] | None,
) -> None:
    """Write the report in the requested format.

    Args:
        args: The parsed arguments.
        book: The book checked.
        plan: The plan checked, whose provenance heads the output.
        report: The combined report.
        mna: The per-node must_not_assert sets, when requested.
    """
    if cast("bool", args.json):
        payload: dict[str, object] = {
            "book": book.id,
            "shape_hash": shape_hash(book),
            "plan": {
                "bound_to": _bound_to(plan),
                "producer": plan.provenance.producer,
                "approver": plan.provenance.approver,
                "book_file": plan.provenance.book_file,
                "authored": (
                    None
                    if plan.provenance.authored is None
                    else plan.provenance.authored.isoformat()
                ),
                "authoring_minutes": plan.provenance.authoring_minutes,
                "implicit_plants": {
                    fact_id: fact.implicit_plant
                    for fact_id, fact in plan.facts.items()
                    if fact.implicit_plant is not None
                },
            },
            **report.to_dict(),
        }
        if mna is not None:
            payload["must_not_assert"] = {n: sorted(f) for n, f in mna.items()}
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return
    provenance = plan.provenance
    approver = provenance.approver or "not approved"
    sys.stdout.write(
        f"plan bound to {_bound_to(plan)} by {provenance.producer} ({approver})\n"
    )
    for finding in report.findings:
        sys.stdout.write(_format_finding(finding) + "\n")
    if mna is not None:
        for node_id, facts in mna.items():
            sys.stdout.write(f"MUST_NOT_ASSERT {node_id}: {', '.join(sorted(facts))}\n")
    errors, warnings = len(report.errors), len(report.warnings)
    verdict = "ok" if report.ok else "FAIL"
    sys.stdout.write(f"{verdict}: {errors} error(s), {warnings} warning(s)\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: The exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if cast("bool", args.verify_witnesses):
        return _run_witnesses()
    if cast("str | None", args.book) is None:
        parser.error("a book path is required")
    book_path = Path(cast("str", args.book))
    loaded = _load_book(book_path)
    if loaded is None:
        return EXIT_UNREADABLE
    book, digest = loaded
    if cast("bool", args.shape_hash):
        sys.stdout.write(f"shape {book.id} {shape_hash(book)}\nbook_sha256 {digest}\n")
        return EXIT_OK
    plan_path = (
        Path(cast("str", args.plan))
        if cast("str | None", args.plan)
        else default_plan_path(book_path)
    )
    raw_plan = _load_json(plan_path)
    if raw_plan is None:
        return EXIT_UNREADABLE
    try:
        plan = StoryPlan.model_validate(raw_plan)
    except ValidationError as exc:
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "$"
            sys.stderr.write(f"SCHEMA {location}: {error['msg']}\n")
        return EXIT_FINDINGS
    report = check_plan(plan, book, book_digest=digest)
    if cast("str | None", args.assertions):
        assertions = _parse_assertions(Path(cast("str", args.assertions)))
        if assertions is None:
            return EXIT_UNREADABLE
        report.extend(check_assertions(plan, book, assertions))
    mna = must_not_assert(plan, book) if cast("bool", args.must_not_assert) else None
    _emit(args, book, plan, report, mna)
    return EXIT_OK if report.ok else EXIT_FINDINGS


if __name__ == "__main__":
    raise SystemExit(main())
