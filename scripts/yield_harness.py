"""Generation yield harness for the CYO Adventure pipeline.

Measures the gate pass rate over a brief sample against the deterministic
MockProvider or, in Phase 2b, a live provider. ``briefs.json`` is a JSON array
of concept-brief dicts (each matching the
:class:`~cyo_adventure.generation.concept.ConceptBrief` schema).

Mock run (deterministic, 100% pass, validates the measurement path)::

    PYTHONPATH=. .venv/bin/python scripts/yield_harness.py \\
        --briefs <briefs.json> --provider mock --threshold 0.60

Live run, OpenRouter cascade (the AC-closing measurement)::

    PYTHONPATH=. .venv/bin/python scripts/yield_harness.py \\
        --briefs <briefs.json> --provider openrouter --threshold 0.60 \\
        --throttle 3 --out docs/planning/yield-results/<name>.json

Isolated leg for the comparison matrix (no failover masks one leg's yield)::

    PYTHONPATH=. .venv/bin/python scripts/yield_harness.py \\
        --briefs <briefs.json> --provider openrouter --no-fallback \\
        --model google/gemma-4-31b-it:free --out <name>.json

Live providers read ``OPENROUTER_API_KEY`` from the environment; for local runs
the harness sources it from the gitignored ``.env`` (``--env-file``). The mock
default keeps CI and casual runs free of any network I/O.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.config import Settings
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.generation.orchestrator import generate_story
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyo_adventure.generation.provider import GenerationProvider

# Provider names the CLI accepts. Live providers were deferred in Phase 2; Phase
# 2b enables them so the >=60% acceptance rate can be measured for real.
_PROVIDER_CHOICES = ("mock", "openrouter", "ollama")

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


def _error_entry(idx: int, exc: Exception, started: float) -> dict[str, object]:
    """Build a per-story entry for a brief whose generation raised.

    Args:
        idx: The 0-based brief index.
        exc: The exception raised by :func:`generate_story`.
        started: ``time.monotonic()`` captured before the attempt.

    Returns:
        A per-story entry with ``status="error"`` and the truncated message.
    """
    return {
        "index": idx,
        "status": "error",
        "attempts": 0,
        "failing_rule_ids": [],
        "latency_s": round(time.monotonic() - started, 2),
        "error": str(exc)[:512],
    }


def _print_progress(entry: dict[str, object], idx: int, total: int) -> None:
    """Print a one-line per-brief progress message to stderr.

    Args:
        entry: The per-story result entry just recorded.
        idx: The 0-based brief index.
        total: The total number of briefs in the run.
    """
    print(
        f"[{idx + 1}/{total}] status={entry['status']} "
        f"attempts={entry['attempts']} latency={entry['latency_s']}s "
        f"rules={entry['failing_rule_ids']}",
        file=sys.stderr,
        flush=True,
    )


async def run_yield(
    briefs: list[ConceptBrief],
    provider_factory: Callable[[], GenerationProvider],
    pii: PiiContext,
    *,
    threshold: float = 0.60,
    delay_between: float = 0.0,
    verbose: bool = False,
) -> YieldReport:
    """Run the generation pipeline for each brief and return a yield summary.

    For each brief a FRESH provider is constructed via ``provider_factory()``
    so every story gets its own response queue and call log. This mirrors how
    the Phase 2b live measurement works: each generation job gets an
    independent provider instance (and, for the cascade, a fresh circuit
    breaker).

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
        delay_between: Seconds to sleep after each brief. Use a small value for
            live free-tier runs to stay under per-minute request limits; the
            default ``0.0`` is correct for mock runs.
        verbose: When ``True``, print a one-line progress message per brief to
            stderr (so a long live run is monitorable from its log).

    Returns:
        A :class:`YieldReport` with aggregate and per-story results. Each
        per-story entry carries a wall-clock ``latency_s``.
    """
    total = len(briefs)
    passed = 0
    per_story: list[dict[str, object]] = []

    for idx, brief in enumerate(briefs):
        provider = provider_factory()
        started = time.monotonic()
        try:
            outcome = await generate_story(brief, provider, pii)
        except Exception as exc:  # isolate one brief's failure (best-effort harness)
            # A measurement harness must not let a single brief's exception
            # abort the batch and discard every prior result. Record this brief
            # as an error so the pass rate reflects the whole sample, not the
            # prefix before the first failure.
            entry = _error_entry(idx, exc, started)
        else:
            if outcome.status == "passed":
                passed += 1
            entry = {
                "index": idx,
                "status": outcome.status,
                "attempts": outcome.attempts,
                "failing_rule_ids": _extract_failing_rule_ids(outcome.report),
                "latency_s": round(time.monotonic() - started, 2),
            }
        per_story.append(entry)
        if verbose:
            _print_progress(entry, idx, total)
        if delay_between > 0:
            await asyncio.sleep(delay_between)

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
        except PydanticValidationError as exc:
            print(f"Error validating brief #{i}: {exc}", file=sys.stderr)
            sys.exit(1)

    return briefs


def _load_env_file(env_path: Path) -> None:
    """Load ``KEY=VALUE`` lines from ``env_path`` into ``os.environ``.

    Existing environment variables are not overwritten. Live providers read
    ``OPENROUTER_API_KEY`` from the environment; for local runs the key lives in
    the gitignored project ``.env``, which ``Settings`` does not load
    automatically, so the harness sources it here for live providers only.

    Args:
        env_path: Path to a dotenv-style file. A missing file is a no-op.
    """
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _build_live_factory(
    provider: str, *, model: str | None, fallback: bool
) -> Callable[[], GenerationProvider]:
    """Return a factory that builds a fresh live provider per brief.

    Args:
        provider: ``"openrouter"`` or ``"ollama"``.
        model: Optional model-id override for the chosen provider; ``None`` keeps
            the configured default.
        fallback: Whether the openrouter cascade may fail over. ``False`` isolates
            the primary leg (a comparison run), so no failover masks its yield.

    Returns:
        A zero-argument factory; each call builds an independent provider (and,
        for the cascade, a fresh per-story circuit breaker).
    """
    kwargs: dict[str, object] = {"generation_provider": provider}
    if provider == "openrouter":
        kwargs["provider_fallback_enabled"] = fallback
        if model is not None:
            kwargs["openrouter_model"] = model
    elif model is not None:
        kwargs["ollama_model"] = model
    settings = Settings(**kwargs)  # type: ignore[arg-type]

    def _factory() -> GenerationProvider:
        """Build a fresh live provider from the resolved settings."""
        return build_provider(settings)

    return _factory


def _tier_split(
    briefs: list[ConceptBrief], per_story: list[dict[str, object]]
) -> dict[str, dict[str, int]]:
    """Split pass/total counts by brief tier for the comparison matrix.

    Args:
        briefs: The briefs processed (indexed by each per-story ``index``).
        per_story: The per-story result entries from a :class:`YieldReport`.

    Returns:
        A mapping ``{"tier1": {"total": n, "passed": m}, "tier2": {...}}``.
    """
    buckets: dict[str, dict[str, int]] = {
        "tier1": {"total": 0, "passed": 0},
        "tier2": {"total": 0, "passed": 0},
    }
    for entry in per_story:
        index = entry["index"]
        if not isinstance(index, int) or index >= len(briefs):
            continue
        key = f"tier{briefs[index].tier}"
        bucket = buckets.setdefault(key, {"total": 0, "passed": 0})
        bucket["total"] += 1
        if entry["status"] == "passed":
            bucket["passed"] += 1
    return buckets


def _write_results(
    out_path: Path,
    report: YieldReport,
    meta: dict[str, object],
) -> None:
    """Write a results JSON capturing the run metadata and the yield report.

    Args:
        out_path: Destination path (parent directories are created).
        report: The yield report to serialize.
        meta: Run metadata (provider, model, fallback flag, threshold, tier
            split) merged into the payload.
    """
    payload: dict[str, object] = {
        **meta,
        "total": report.total,
        "passed": report.passed,
        "pass_rate": round(report.pass_rate, 4),
        "meets_threshold": report.meets_threshold,
        "per_story": report.per_story,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    """Build the argument parser and parse argv."""
    parser = argparse.ArgumentParser(
        description=(
            "Generation yield harness. Measures the gate pass rate over a brief "
            "sample against the mock or a live provider (Phase 2b)."
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
        choices=list(_PROVIDER_CHOICES),
        help="Provider to measure (default: mock).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the provider's model id (e.g. an isolated comparison leg).",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable the openrouter cascade so one leg is measured in isolation.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N briefs (cheap debug iterations).",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=0.0,
        help="Seconds to sleep between briefs (free-tier rate limits).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write the results JSON (with run metadata).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Dotenv file to source for live providers (default: .env).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.60,
        help="Minimum pass rate to consider the batch acceptable (default: 0.60).",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point for the generation yield harness.

    Parses arguments, builds the mock or a live provider factory, runs the yield
    measurement, prints a summary, optionally writes a results JSON, and exits 0
    when ``meets_threshold`` is True or 1 when it is not.
    """
    args = _parse_args()
    # argparse attributes are typed Any by the stdlib stubs; narrow them here.
    provider_name: str = str(args.provider)  # pyright: ignore[reportAny]
    briefs_path: Path = Path(str(args.briefs))  # pyright: ignore[reportAny]
    threshold_val: float = float(args.threshold)  # pyright: ignore[reportAny]
    model_override: str | None = (
        str(args.model) if args.model is not None else None  # pyright: ignore[reportAny]
    )
    fallback_enabled: bool = not bool(args.no_fallback)  # pyright: ignore[reportAny]
    limit: int | None = int(args.limit) if args.limit is not None else None  # pyright: ignore[reportAny]
    throttle: float = float(args.throttle)  # pyright: ignore[reportAny]
    out_path: Path | None = (
        Path(str(args.out)) if args.out is not None else None  # pyright: ignore[reportAny]
    )
    env_path: Path = Path(str(args.env_file))  # pyright: ignore[reportAny]

    briefs = _load_briefs(briefs_path)
    if limit is not None:
        briefs = briefs[:limit]

    if provider_name == "mock":
        factory = _build_mock_factory()
    else:
        # Live providers read OPENROUTER_API_KEY from the environment; source the
        # dotenv file so a local run picks up the gitignored key.
        _load_env_file(env_path)
        factory = _build_live_factory(
            provider_name, model=model_override, fallback=fallback_enabled
        )

    pii = PiiContext(child_names=frozenset(), birthdates=frozenset())
    report = asyncio.run(
        run_yield(
            briefs,
            factory,
            pii,
            threshold=threshold_val,
            delay_between=throttle,
            verbose=True,
        )
    )
    _print_summary(report, threshold_val)

    if out_path is not None:
        meta: dict[str, object] = {
            "provider": provider_name,
            "model": model_override,
            "fallback_enabled": fallback_enabled
            if provider_name == "openrouter"
            else False,
            "threshold": threshold_val,
            "tier_split": _tier_split(briefs, report.per_story),
        }
        _write_results(out_path, report, meta)
        print(f"Wrote results to {out_path}")

    sys.exit(0 if report.meets_threshold else 1)


if __name__ == "__main__":
    main()
