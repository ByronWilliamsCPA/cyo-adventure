"""Adversarial safety harness for the CYO Adventure moderation pipeline.

Reads the passage-oriented adversarial corpus
(``docs/planning/safety/adversarial-corpus.json``), feeds each executable item to
the real moderation stages using the configured ``review_provider`` (and, for the
PII positive control, the ``PiiGuardedProvider``), compares the observed verdict to
the item's expected minimum, and reports a per-taxonomy-class catch-rate against the
thresholds in ``docs/planning/safety/adversarial-safety-evaluation.md``.

Honesty guardrail: the mock review provider returns ``"{}"`` for every call, which
the stage parser maps to the fail-safe verdict (Stage 1 -> FLAG, soft stages ->
PASS). A mock run therefore flags every Stage-1-routed item by fail-safe, but a
Stage-2 (readability) item still resolves to PASS and can show as a spurious miss;
either way, a mock run measures nothing about real classifier discrimination. The
harness detects ``review_provider == "mock"`` and refuses to report the run as
evidence: it prints a prominent notice and exits non-zero regardless of the apparent
catch-rate. A real evaluation needs a live review model::

    PYTHONPATH=. .venv/bin/python scripts/adversarial_harness.py \\
        --corpus docs/planning/safety/adversarial-corpus.json \\
        --review-provider openrouter \\
        --out docs/planning/safety/adversarial-results-<date>.json

Live providers read their credential from the environment; for local runs the
harness sources the gitignored ``.env`` (``--env-file``), exactly like the yield
harness. The mock default keeps CI and casual runs free of network I/O. A live
``--review-provider`` also needs a Stage-0 classifier credential (either
``OPENAI_API_KEY`` or ``PERSPECTIVE_API_KEY``); see ``main()`` for how a missing
one is surfaced.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ProjectBaseError, ValidationError
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.moderation.review_provider import (
    ReviewProvider,
    build_review_provider,
)
from cyo_adventure.moderation.stages import run_readability_stage, run_safety_stage

_REPO_ROOT = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "CorpusReport",
    "ItemOutcome",
    "classify_item",
    "is_caught",
    "run_corpus",
    "verdict_rank",
]

# Verdict severity, low to high. "routed to a human" is FLAG or stronger.
_VERDICT_RANK: dict[str, int] = {"pass": 0, "advisory": 1, "flag": 2, "block": 3}

# The fixed set of statuses classify_item ever constructs, and the review-provider
# names this harness accepts. Both are internally controlled (never round-tripped
# from untrusted corpus JSON), so a Literal catches a typo at the call site instead
# of only at runtime.
ItemStatus = Literal[
    "caught", "missed", "gap", "skipped", "control_ok", "control_over_block"
]
ReviewProviderName = Literal["mock", "openrouter", "ollama"]

# Stage-2 (readability) needs a Flesch-Kincaid grade target; the corpus items are
# banded, not grade-tagged, so map each band to a representative grade for the probe.
# #ASSUME: data integrity: the mapped grade is approximate by design. The current
# Stage-2 corpus item is far outside any reasonable band, so the exact target does
# not change its flag outcome.
# #VERIFY: if a future Stage-2 item sits close to a band boundary, confirm the
# approximation still doesn't flip caught/missed before trusting its result.
_BAND_GRADE: dict[str, float] = {
    "3-5": 0.5,
    "5-8": 2.0,
    "8-11": 4.0,
    "10-13": 6.0,
    "13-16": 9.0,
    "16+": 11.0,
}

_READABILITY_TOLERANCE = 1.5
_PROBE_MAX_TOKENS = 1024


def verdict_rank(verdict: str) -> int:
    """Return the severity rank of a verdict string.

    Args:
        verdict: One of ``pass``, ``advisory``, ``flag``, ``block``.

    Returns:
        The severity rank (``pass`` = 0 through ``block`` = 3).

    Raises:
        ValueError: If ``verdict`` is not a recognized verdict.
    """
    rank = _VERDICT_RANK.get(verdict)
    if rank is None:
        msg = f"unknown verdict: {verdict!r}"
        raise ValueError(msg)
    return rank


def is_caught(expected_min_verdict: str, observed_verdicts: Sequence[str]) -> bool:
    """Return whether the observed verdicts reach the expected minimum severity.

    Args:
        expected_min_verdict: The minimum verdict that counts as caught (usually
            ``flag`` for route-to-human, or ``block`` for a bright-line item).
        observed_verdicts: The verdicts the pipeline produced for the item.

    Returns:
        ``True`` when the strongest observed verdict is at least the expected
        minimum. No observations counts as ``pass`` (not caught).
    """
    expected_rank = verdict_rank(expected_min_verdict)
    observed_max = max((verdict_rank(v) for v in observed_verdicts), default=0)
    return observed_max >= expected_rank


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    """The classified result for one corpus item.

    Attributes:
        item_id: The corpus item id.
        taxonomy_class: The attack class (``A``-``F``).
        status: One of ``caught``, ``missed``, ``gap``, ``skipped``,
            ``control_ok``, ``control_over_block``.
        expected: The expected outcome string (min verdict, or ``raise_before_egress``).
        observed: The observed verdicts (empty for guard/skip items).
        note: A short human-readable explanation of the status.
    """

    item_id: str
    taxonomy_class: str
    status: ItemStatus
    expected: str
    observed: tuple[str, ...]
    note: str


def _as_str(value: object) -> str:
    """Coerce a JSON value to str, defaulting to empty."""
    return value if isinstance(value, str) else ""


def _as_bool(value: object) -> bool:
    """Coerce a JSON value to bool, defaulting to False (non-bool is False)."""
    return value if isinstance(value, bool) else False


def classify_item(
    item: Mapping[str, object],
    observed_verdicts: Sequence[str],
    *,
    guard_raised: bool | None = None,
) -> ItemOutcome:
    """Classify one corpus item against its observed pipeline result.

    Dispatch order: non-executable items are skipped; PII-guard items are decided
    by whether the guard raised; known-gap (aggregate) items are recorded as gaps
    rather than scored; negative controls invert the sense (clean is good); all
    other items are caught iff the observed severity reaches the expected minimum.

    Args:
        item: One corpus item (the JSON object).
        observed_verdicts: Verdicts the pipeline produced (empty for guard/skip).
        guard_raised: For PII-guard items, whether the guard raised before egress;
            ``None`` for non-PII items.

    Returns:
        The classified :class:`ItemOutcome`.
    """
    item_id = _as_str(item.get("id"))
    tax = _as_str(item.get("taxonomy_class"))
    observed = tuple(observed_verdicts)
    expected = _as_str(item.get("expected_min_verdict")) or _as_str(
        item.get("expected")
    )

    if not _as_bool(item.get("executable")):
        target = _as_str(item.get("target")) or "call graph"
        note = f"not executable by the passage harness (target: {target})"
        return ItemOutcome(item_id, tax, "skipped", expected, observed, note)

    if _as_str(item.get("target")) == "pii_guard":
        caught = bool(guard_raised)
        note = (
            "PII guard raised before egress"
            if caught
            else "PII guard did NOT raise: real-child data would egress"
        )
        status = "caught" if caught else "missed"
        return ItemOutcome(item_id, tax, status, "raise_before_egress", observed, note)

    if _as_bool(item.get("known_gap")):
        gated = is_caught("flag", observed)
        note = (
            "per-node gate DID gate this path (better than the documented gap)"
            if gated
            else "per-node gate did not gate the assembled path (expected per Finding 4)"
        )
        return ItemOutcome(item_id, tax, "gap", expected, observed, note)

    if _as_bool(item.get("negative_control")):
        over_blocked = is_caught("flag", observed)
        status = "control_over_block" if over_blocked else "control_ok"
        note = (
            "clean passage was flagged: the gate over-blocks"
            if over_blocked
            else "clean passage passed as expected"
        )
        return ItemOutcome(item_id, tax, status, expected, observed, note)

    caught = is_caught(expected, observed)
    note = (
        f"observed {list(observed)} reached expected minimum {expected!r}"
        if caught
        else f"observed {list(observed)} below expected minimum {expected!r}"
    )
    return ItemOutcome(
        item_id, tax, "caught" if caught else "missed", expected, observed, note
    )


def _nodes_of(item: Mapping[str, object]) -> list[tuple[str, str]]:
    """Extract ``(node_id, prose)`` pairs from an item's passage or nodes list."""
    passage = item.get("passage")
    if isinstance(passage, str):
        return [(_as_str(item.get("id")) or "n0", passage)]
    raw_nodes = item.get("nodes")
    if not isinstance(raw_nodes, list):
        return []
    pairs: list[tuple[str, str]] = []
    for node in raw_nodes:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        node_map: dict[str, object] = node  # pyright: ignore[reportUnknownVariableType,reportAssignmentType]
        nid = _as_str(node_map.get("id"))
        body = _as_str(node_map.get("body"))
        if nid:
            pairs.append((nid, body))
    return pairs


def _pii_context_of(item: Mapping[str, object]) -> PiiContext:
    """Build a PiiContext from an item's ``pii_context`` block."""
    raw = item.get("pii_context")
    names: list[str] = []
    if isinstance(raw, dict):
        ctx: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType,reportAssignmentType]
        raw_names = ctx.get("child_names")
        if isinstance(raw_names, list):
            names = [n for n in raw_names if isinstance(n, str)]  # pyright: ignore[reportUnknownVariableType]
    return PiiContext(child_names=frozenset(names))


async def _observe_item(
    item: Mapping[str, object], review_provider: ReviewProvider
) -> tuple[list[str], bool | None]:
    """Run the appropriate moderation probe for one item.

    Args:
        item: The corpus item.
        review_provider: The configured review provider (LLM stages).

    Returns:
        ``(observed_verdicts, guard_raised)``. ``guard_raised`` is ``None`` for
        non-PII items, and a bool for PII-guard items.
    """
    target = _as_str(item.get("target"))
    guarded = PiiGuardedProvider(review_provider, forbidden=_pii_context_of(item))
    if target == "pii_guard":
        passage = _as_str(item.get("passage"))
        try:
            _ = await guarded.complete(system="", prompt=passage, max_tokens=16)
        except ValidationError:
            return [], True
        return [], False

    # #ASSUME: security: production (moderation/pipeline.py) always routes Stage
    # 1/2 calls through a PiiGuardedProvider, never the bare review provider. This
    # probe must match that topology so a guard regression would show up here too,
    # not just in production.
    # #VERIFY: guarded, not review_provider, is passed to both stage calls below.
    nodes = _nodes_of(item)
    stage = item.get("target_stage")
    band = _as_str(item.get("age_band"))
    if stage == 2:
        target_grade = _BAND_GRADE.get(band, 4.0)
        findings = await run_readability_stage(
            provider=guarded,
            nodes=nodes,
            reading_target=target_grade,
            tolerance=_READABILITY_TOLERANCE,
            max_tokens=_PROBE_MAX_TOKENS,
        )
    elif stage in (1, "aggregate"):
        # Stage 1 (per-node safety) covers both target_stage == 1 and the
        # aggregate (known-gap) items, which are run per node to demonstrate the gap.
        findings = await run_safety_stage(
            provider=guarded,
            nodes=nodes,
            age_band=band,
            max_tokens=_PROBE_MAX_TOKENS,
        )
    else:
        # #ASSUME: data integrity: target_stage is hand-authored corpus JSON with no
        # schema validation on load. A typo (e.g. "2" instead of 2) must not silently
        # misroute an item into the wrong probe and corrupt its scored outcome.
        # #VERIFY: test_target_stage_type_mismatch_raises exercises this branch.
        item_id = _as_str(item.get("id")) or "<unknown>"
        msg = f"item {item_id!r} has an unrecognized target_stage: {stage!r}"
        raise ValidationError(msg)
    return [f.verdict.value for f in findings], None


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """Aggregate result of an adversarial corpus run.

    Attributes:
        review_provider: The provider name the run used.
        outcomes: One :class:`ItemOutcome` per corpus item.
        per_class: ``{class: {status: count}}`` rollup.

    ``is_evidence`` is deliberately not a stored field: this harness's entire
    purpose is to never let a mock run masquerade as evidence, so that fact is
    derived from ``review_provider`` rather than an independently-settable value
    that could drift out of sync with it.
    """

    review_provider: ReviewProviderName
    outcomes: list[ItemOutcome]
    per_class: dict[str, dict[str, int]]

    @property
    def is_evidence(self) -> bool:
        """``False`` for a mock run (fail-safe artifacts, not a measure)."""
        return self.review_provider != "mock"


def _rollup(outcomes: Sequence[ItemOutcome]) -> dict[str, dict[str, int]]:
    """Roll outcomes up into ``{taxonomy_class: {status: count}}``."""
    rollup: dict[str, dict[str, int]] = {}
    for out in outcomes:
        by_status = rollup.setdefault(out.taxonomy_class, {})
        by_status[out.status] = by_status.get(out.status, 0) + 1
    return rollup


def _catch_rate(status_counts: Mapping[str, int]) -> float | None:
    """Return the caught/(caught+missed) rate for one class's status counts.

    Returns ``None`` when the class has no caught-or-missed item to score (for
    example a class made up only of ``gap``/``skipped``/control items), since a
    rate would be undefined rather than zero.
    """
    caught = status_counts.get("caught", 0)
    missed = status_counts.get("missed", 0)
    total = caught + missed
    if total == 0:
        return None
    return caught / total


async def run_corpus(
    items: Sequence[Mapping[str, object]],
    review_provider: ReviewProvider,
    *,
    review_provider_name: ReviewProviderName,
) -> CorpusReport:
    """Run every corpus item through its probe and classify the outcome.

    Args:
        items: The corpus items.
        review_provider: The configured review provider.
        review_provider_name: The provider name (``mock`` marks a non-evidence run).

    Returns:
        A :class:`CorpusReport`. ``is_evidence`` is ``False`` for a mock run.
    """
    outcomes: list[ItemOutcome] = []
    for item in items:
        if not _as_bool(item.get("executable")):
            outcomes.append(classify_item(item, []))
            continue
        observed, guard_raised = await _observe_item(item, review_provider)
        outcomes.append(classify_item(item, observed, guard_raised=guard_raised))
    return CorpusReport(
        review_provider=review_provider_name,
        outcomes=outcomes,
        per_class=_rollup(outcomes),
    )


def _load_items(corpus_path: Path) -> list[dict[str, object]]:
    """Load the corpus items array from the corpus JSON file.

    Args:
        corpus_path: Path to the corpus JSON.

    Returns:
        The list of item dicts.

    Raises:
        SystemExit: If the file cannot be read or parsed, or has no items array.
    """
    try:
        raw_text = corpus_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading corpus file: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        parsed: object = json.loads(raw_text)  # pyright: ignore[reportAny]
    except json.JSONDecodeError as exc:
        print(f"Error parsing corpus JSON: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(parsed, dict):
        print(
            "Error: corpus must be a JSON object with an 'items' array.",
            file=sys.stderr,
        )
        sys.exit(2)
    corpus: dict[str, object] = parsed  # pyright: ignore[reportUnknownVariableType,reportAssignmentType]
    raw_items = corpus.get("items")
    if not isinstance(raw_items, list):
        print("Error: corpus 'items' must be an array.", file=sys.stderr)
        sys.exit(2)
    return [
        cast("dict[str, object]", entry)
        for entry in raw_items  # pyright: ignore[reportUnknownVariableType]
        if isinstance(entry, dict)
    ]


def _load_env_file(env_path: Path) -> None:
    """Load ``KEY=VALUE`` lines from ``env_path`` into ``os.environ`` (no overwrite)."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _print_report(report: CorpusReport) -> None:
    """Print a human-readable summary of a corpus run to stdout."""
    print("=" * 64)
    print("Adversarial Safety Harness Summary")
    print("=" * 64)
    print(f"Review provider: {report.review_provider}")
    if not report.is_evidence:
        print()
        print("!!! MOCK RUN: NOT EVIDENCE !!!")
        print("The mock review provider returns fail-safe verdicts (Stage 1 -> FLAG,")
        print("soft stages -> PASS), so results are deterministic artifacts of that")
        print("fail-safe mapping, not real classifier discrimination.")
        print("Re-run with --review-provider openrouter (or ollama) for a real result.")
        print()
    print(f"Items: {len(report.outcomes)}")
    print()
    print("Per-class rollup (status counts and catch-rate):")
    for tax in sorted(report.per_class):
        counts = report.per_class[tax]
        rate = _catch_rate(counts)
        rate_str = f"{rate:.0%}" if rate is not None else "N/A"
        print(f"  {tax}: {counts} catch-rate={rate_str}")
    print()
    print("Per-item:")
    for out in report.outcomes:
        print(f"  [{out.item_id}] class={out.taxonomy_class} status={out.status}")
        print(f"      {out.note}")
    print("=" * 64)


def _write_results(out_path: Path, report: CorpusReport) -> None:
    """Write the run results as JSON (metadata plus per-item outcomes)."""
    payload: dict[str, object] = {
        "review_provider": report.review_provider,
        "is_evidence": report.is_evidence,
        "per_class": report.per_class,
        "catch_rate": {
            tax: _catch_rate(counts) for tax, counts in report.per_class.items()
        },
        "items": [
            {
                "id": out.item_id,
                "taxonomy_class": out.taxonomy_class,
                "status": out.status,
                "expected": out.expected,
                "observed": list(out.observed),
                "note": out.note,
            }
            for out in report.outcomes
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _has_misses(report: CorpusReport) -> bool:
    """Return whether any executable item missed or a control over-blocked."""
    return any(
        out.status in {"missed", "control_over_block"} for out in report.outcomes
    )


# #ASSUME: security: --corpus/--out/--env-file are documented (module
# docstring above, docs/planning/safety/adversarial-safety-evaluation.md) as
# always repo-relative (docs/planning/safety/*.json, .env), and this script
# has no test that exercises them against an out-of-repo tmp_path fixture
# (test_adversarial_harness.py only covers the pure scoring core); containing
# them to the repo root closes the CWE-23 gap (Snyk python/PT) without
# rejecting any documented or tested invocation.
# #VERIFY: if a future evaluation needs a corpus or output location outside
# the repo tree, this containment must be relaxed deliberately (and the
# rationale above updated), not silently bypassed.
def _resolve_within(path_arg: Path, *, label: str) -> Path:
    """Resolve a CLI-supplied path and require it stay within the repo root.

    Matches the containment idiom in ``generation/import_cli.py::_load_blob``:
    canonicalize with ``.resolve()``, then reject anything that escapes
    ``_REPO_ROOT`` via ``.relative_to()``.

    Args:
        path_arg: The raw ``Path`` from an argparse argument (``type=Path``).
        label: Human-readable argument name for the error message.

    Returns:
        The resolved, canonicalized Path, guaranteed to be under
        ``_REPO_ROOT``.

    Raises:
        SystemExit: If the resolved path escapes ``_REPO_ROOT``, exit code 2
            (matching this script's own load-error convention).
    """
    resolved = path_arg.resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        msg = (
            f"Error: {label} path {str(path_arg)!r} resolves to {resolved}, "
            f"which is outside the repo root {_REPO_ROOT}"
        )
        print(msg, file=sys.stderr)
        sys.exit(2)
    return resolved


def _parse_args() -> argparse.Namespace:
    """Build the argument parser and parse argv."""
    parser = argparse.ArgumentParser(
        description=(
            "Adversarial safety harness. Feeds the adversarial corpus to the "
            "moderation stages and reports a per-class catch-rate. Mock runs are "
            "wiring checks only, never evidence."
        )
    )
    parser.add_argument(
        "--corpus",
        required=True,
        type=Path,
        help="Path to the adversarial corpus JSON.",
    )
    parser.add_argument(
        "--review-provider",
        default="mock",
        choices=("mock", "openrouter", "ollama"),
        help=(
            "Review provider for the LLM stages (default: mock, not evidence). "
            "A live provider also needs a Stage-0 classifier credential "
            "(OPENAI_API_KEY or PERSPECTIVE_API_KEY) in the environment or "
            "--env-file."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write the results JSON.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Dotenv file to source for live providers (default: .env).",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point.

    Loads the corpus, builds the review provider, runs the corpus, prints and
    optionally writes results. Exits 0 only for an evidence run with no misses and
    no control over-blocks; exits 1 on a miss; exits 2 if the settings or review
    provider could not be built (for example a missing live-provider credential);
    exits 3 for a non-evidence mock run.
    """
    args = _parse_args()
    corpus_path = _resolve_within(cast("Path", args.corpus), label="--corpus")
    provider_name: str = str(args.review_provider)  # pyright: ignore[reportAny]
    out_arg = cast("Path | None", args.out)
    out_path: Path | None = (
        _resolve_within(out_arg, label="--out") if out_arg is not None else None
    )
    env_path = _resolve_within(cast("Path", args.env_file), label="--env-file")

    items = _load_items(corpus_path)

    if provider_name != "mock":
        _load_env_file(env_path)
    try:
        settings = Settings.model_validate({"review_provider": provider_name})
        review_provider, _independent = build_review_provider(
            settings, generator_provider=None, generator_model=None
        )
        report = asyncio.run(
            run_corpus(
                items,
                review_provider,
                review_provider_name=cast("ReviewProviderName", provider_name),
            )
        )
    except ProjectBaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    _print_report(report)
    if out_path is not None:
        _write_results(out_path, report)
        print(f"Wrote results to {out_path}")

    if not report.is_evidence:
        sys.exit(3)
    sys.exit(1 if _has_misses(report) else 0)


if __name__ == "__main__":
    main()
