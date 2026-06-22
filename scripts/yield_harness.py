"""Mock-driven generation yield harness for the CYO Adventure pipeline.

Demonstrates the >=60% acceptance methodology end-to-end against the
deterministic MockProvider. In Phase 2 this script runs against the mock
so the measurement path is validated without network I/O. Phase 2b swaps in
a live provider to measure the real >=60% acceptance rate over a 20-story
sample.

Usage::

    PYTHONPATH=. .venv/bin/python scripts/yield_harness.py \\
        --briefs <briefs.json> --provider mock --threshold 0.60

``briefs.json`` is a JSON array of concept-brief dicts (each matching the
:class:`~cyo_adventure.generation.concept.ConceptBrief` schema). The mock
provider returns the canned valid story for every brief, so a run against
mock deterministically reports 100% pass rate, demonstrating the measurement
path. Phase 2b swaps in a live provider (``--provider claude`` etc.) to
measure the actual acceptance rate.

Important: live providers are deferred to Phase 2b. Requesting any provider
other than ``mock`` via the CLI prints an informational message and exits
with a non-zero status code.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cyo_adventure.core.config import Settings
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.generation.orchestrator import generate_story
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyo_adventure.generation.provider import GenerationProvider

__all__ = [
    "YieldReport",
    "run_yield",
]

# #ASSUME: external-resources: run_yield is designed for deterministic mock
# runs in Phase 2; provider_factory is called once per brief so each story
# gets an isolated response queue and call log.
# #VERIFY: Phase 2b adds a real-provider factory; the function signature and
# YieldReport shape are intentionally provider-agnostic.


@dataclass(frozen=True, slots=True)
class YieldReport:
    """Summary of a yield measurement run.

    Attributes:
        total: Total number of briefs processed.
        passed: Number of briefs whose generation outcome was ``"passed"``.
        pass_rate: Fraction of briefs that passed (``passed / total``, or
            ``0.0`` when ``total == 0`` to avoid division by zero).
        per_story: One entry per brief: ``index`` (0-based), ``status``
            (``"passed"``, ``"needs_review"``, or ``"failed"``), ``attempts``
            (repair attempts), and ``failing_rule_ids`` (ERROR rule ids from
            the gate report).
        meets_threshold: ``True`` when ``pass_rate >= threshold``.
    """

    total: int
    passed: int
    pass_rate: float
    per_story: list[dict[str, object]]
    meets_threshold: bool


def _extract_failing_rule_ids(report: dict[str, object]) -> list[str]:
    """Extract ERROR-severity rule ids from a gate report dict.

    Args:
        report: The gate report dict (``to_dict()`` format from
            :class:`~cyo_adventure.validator.report.ValidationReport`).

    Returns:
        Sorted list of distinct rule ids for ERROR-severity findings only.
    """
    findings_raw: object = report.get("findings", [])
    if not isinstance(findings_raw, list):
        return []
    rule_ids: list[str] = []
    for finding_raw in findings_raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(finding_raw, dict):
            continue
        # Each finding is dict[str, str | None] per ValidationFinding.to_dict().
        finding: dict[str, str | None] = finding_raw  # pyright: ignore[reportAssignmentType,reportUnknownVariableType]
        severity: str | None = finding.get("severity")
        rule_id: str | None = finding.get("rule_id")
        if severity == "error" and isinstance(rule_id, str):
            rule_ids.append(rule_id)
    return sorted(set(rule_ids))


async def run_yield(
    briefs: list[ConceptBrief],
    provider_factory: Callable[[], GenerationProvider],
    pii: PiiContext,
    *,
    threshold: float = 0.60,
) -> YieldReport:
    """Run the generation pipeline for each brief and return a yield summary.

    For each brief a FRESH provider is constructed via ``provider_factory()``
    so every story gets its own response queue and call log. This mirrors how
    the Phase 2b live measurement will work: each generation job gets an
    independent provider instance.

    Args:
        briefs: The list of concept briefs to process. An empty list is valid
            and returns a zero-total report with ``meets_threshold=False``.
        provider_factory: A zero-argument callable that returns a
            :class:`~cyo_adventure.generation.provider.GenerationProvider`.
            Called once per brief.
        pii: The PII context forwarded to every :func:`generate_story` call.
            Use an empty :class:`~cyo_adventure.generation.pii.PiiContext`
            (empty frozensets) when no real child data exists.
        threshold: The minimum pass rate required for ``meets_threshold`` to
            be ``True``. Defaults to ``0.60`` (60%).

    Returns:
        A :class:`YieldReport` with aggregate and per-story results.
    """
    total = len(briefs)
    passed = 0
    per_story: list[dict[str, object]] = []

    for idx, brief in enumerate(briefs):
        provider = provider_factory()
        outcome = await generate_story(brief, provider, pii)

        if outcome.status == "passed":
            passed += 1

        failing_rule_ids = _extract_failing_rule_ids(outcome.report)

        per_story.append(
            {
                "index": idx,
                "status": outcome.status,
                "attempts": outcome.attempts,
                "failing_rule_ids": failing_rule_ids,
            }
        )

    pass_rate = passed / total if total > 0 else 0.0
    meets_threshold = pass_rate >= threshold

    return YieldReport(
        total=total,
        passed=passed,
        pass_rate=pass_rate,
        per_story=per_story,
        meets_threshold=meets_threshold,
    )


def _build_mock_factory() -> Callable[[], GenerationProvider]:
    """Return a factory that produces a fresh MockProvider per call.

    Each MockProvider is seeded via :func:`build_provider` with the default
    ``Settings`` (``generation_provider="mock"``), which queues enough copies
    of the canned valid story to cover Stage A + Stage B + up to three repair
    rounds. The canned story passes the gate cleanly, so a run against this
    factory deterministically reports a 100% pass rate.

    Returns:
        A zero-argument callable that returns a seeded
        :class:`~cyo_adventure.generation.provider.MockProvider`.
    """
    _settings = Settings()

    def _factory() -> GenerationProvider:
        """Build a fresh MockProvider seeded with the canned story."""
        return build_provider(_settings)

    return _factory


def _print_summary(report: YieldReport, threshold: float) -> None:
    """Print a human-readable summary of a :class:`YieldReport` to stdout.

    Args:
        report: The yield report to summarize.
        threshold: The threshold used for the run (for display purposes).
    """
    print("=" * 60)
    print("Generation Yield Harness Summary")
    print("=" * 60)
    print(f"Total briefs:    {report.total}")
    print(f"Passed:          {report.passed}")
    print(f"Pass rate:       {report.pass_rate:.1%}")
    print(f"Threshold:       {threshold:.1%}")
    meets_label = "YES" if report.meets_threshold else "NO"
    print(f"Meets threshold: {meets_label}")
    print()

    if report.per_story:
        print("Per-story breakdown:")
        for entry in report.per_story:
            idx = entry["index"]
            status = entry["status"]
            attempts = entry["attempts"]
            rule_ids = entry["failing_rule_ids"]
            rule_str = ", ".join(rule_ids) if rule_ids else "none"  # type: ignore[arg-type]
            print(
                f"  [{idx}] status={status} attempts={attempts} failing_rules={rule_str}"
            )

    print("=" * 60)


def _load_briefs(briefs_path: Path) -> list[ConceptBrief]:
    """Load and validate concept briefs from a JSON file.

    The file must contain a JSON array of concept-brief dicts. Each dict is
    validated against :class:`~cyo_adventure.generation.concept.ConceptBrief`.

    Args:
        briefs_path: Path to the JSON file containing the briefs array.

    Returns:
        A list of validated :class:`~cyo_adventure.generation.concept.ConceptBrief`
        objects.

    Raises:
        SystemExit: If the file cannot be read, is not valid JSON, or any
            brief fails Pydantic validation.
    """
    try:
        raw_text = briefs_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading briefs file: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        parsed: object = json.loads(raw_text)  # pyright: ignore[reportAny]
    except json.JSONDecodeError as exc:
        print(f"Error parsing briefs JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(parsed, list):
        print("Error: briefs file must contain a JSON array.", file=sys.stderr)
        sys.exit(1)

    briefs: list[ConceptBrief] = []
    # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType] applies
    # because parsed is list[Unknown] after isinstance narrowing of json.loads Any.
    for i, raw_item in enumerate(parsed):  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        item: object = raw_item  # pyright: ignore[reportUnknownVariableType]
        try:
            briefs.append(ConceptBrief.model_validate(item))
        except Exception as exc:
            print(f"Error validating brief #{i}: {exc}", file=sys.stderr)
            sys.exit(1)

    return briefs


def main() -> None:
    """CLI entry point for the generation yield harness.

    Parses arguments, builds the appropriate provider factory, runs the
    yield measurement, prints a summary, and exits 0 when
    ``meets_threshold`` is True or 1 when it is not.

    Non-mock providers are deferred to Phase 2b. Requesting one prints an
    informational message and exits with status 2.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Mock-driven generation yield harness. "
            "Demonstrates the >=60% acceptance methodology end-to-end. "
            "Phase 2b swaps in a live provider to measure real acceptance rate."
        )
    )
    parser.add_argument(
        "--briefs",
        required=True,
        type=Path,
        help="Path to a JSON file containing an array of concept-brief dicts.",
    )
    parser.add_argument(
        "--provider",
        default="mock",
        choices=["mock"],
        help=(
            "Provider to use. Only 'mock' is operational in Phase 2. "
            "Live providers are deferred to Phase 2b."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.60,
        help="Minimum pass rate to consider the batch acceptable (default: 0.60).",
    )

    args = parser.parse_args()

    # argparse attributes are typed Any by the stdlib stubs; suppress here.
    provider_name: str = str(args.provider)  # pyright: ignore[reportAny]
    briefs_path: Path = Path(str(args.briefs))  # pyright: ignore[reportAny]
    threshold_val: float = float(args.threshold)  # pyright: ignore[reportAny]

    if provider_name != "mock":
        # Guard: live providers are deferred to Phase 2b.
        msg = (
            f"Provider '{provider_name}' is deferred to Phase 2b; "
            "set --provider mock for the Phase 2 harness demonstration."
        )
        print(msg, file=sys.stderr)
        sys.exit(2)

    briefs = _load_briefs(briefs_path)
    pii = PiiContext(child_names=frozenset(), birthdates=frozenset())
    factory = _build_mock_factory()

    report = asyncio.run(run_yield(briefs, factory, pii, threshold=threshold_val))
    _print_summary(report, threshold_val)

    sys.exit(0 if report.meets_threshold else 1)


if __name__ == "__main__":
    main()
