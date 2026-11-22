#!/usr/bin/env python3
"""Validate the plan reviewer against the labelled ground truth (WP-3.7, gate G3b).

Usage:
    uv run python scripts/validate_plan_reviewer.py --half tuning --dry-run
    uv run python scripts/validate_plan_reviewer.py --half tuning --live \
        --budget 40 --reviewer-model <model>
    uv run python scripts/validate_plan_reviewer.py --half held_out --live \
        --budget 60 --reviewer-model <model> --confirm-held-out
    uv run python scripts/validate_plan_reviewer.py --rescore <run-dir>

What it reads (committed files only; every sha256 is verified, and a mismatch
stops the run):

* the real plans of ``docs/planning/evidence/continuity-reader/validation-set.json``
  (``kind: plan``, strong labels only: ``unknown`` smoke plans and weak-labelled
  plans are skipped). ``reject`` plans are the real defective sample; ``pass``
  plans are only checked by the deterministic checker, because the clean sample
  is the baselines below;
* the synthetic plans of
  ``docs/planning/evidence/plan-reviewer/synthetic/validation-set.synthetic.json``
  (family A checker-visible, family B checker-invisible), reported apart;
* the clean sample: the checker-repaired baselines of
  ``docs/planning/evidence/plan-reviewer/clean-baselines/manifest.json`` (schema
  ``clean-baselines/v1``). The harness stops with a clear message when it is
  absent.

For each plan it runs the checker as ``scripts/check_story_plan.py`` does,
applies checker authority (an ERROR rejects the plan and no model is called),
and otherwise calls the reviewer ``--runs`` times. Figures are never merged
(``cyo_adventure.storyplan.review_figures``): real defective recall overall and
by severity and per blocker entry, split into checker-caught and
reviewer-decisive plans; synthetic recall by family and class; the clean flag
rate per book and with and without the baselines that needed repair; run
agreement; every D12 threshold; and a G3b pass or fail line.

Tuning discipline (pre-registered, D12): ``--half tuning`` is for prompt work.
``--half held_out`` needs ``--confirm-held-out`` and is refused when the same
writer, reviewer and prompt hash has already been run on the held-out half, and
after one prompt revision following a failed first run. The record is
``docs/planning/evidence/plan-reviewer/held-out-runs.json``. Dry runs touch
neither the record nor the network.

Modes: ``--dry-run`` (a stub provider answers ``pass``; no network; the figures
mean nothing) or ``--live`` (needs ``OPENROUTER_API_KEY`` and a ``--budget`` hard
cap in USD, checked before every call). Live refuses to start without a budget.

Located recall (informational, never a threshold): for each family B seed the
harness derives the entry ids the seed edited from its ``edited_paths`` and
credits the seed only when a reviewer finding names one of them. It sits beside
the "any reject" recall, and a reject-everything diagnostic warns when clean
baselines and seeds are both flagged above 90 percent. ``results.json`` records
each plan's seeded entry ids and the findings at them.

Re-scoring: ``--rescore <run-dir>`` recomputes the figures of an existing run
from its ``results.json`` with no model call and writes ``report.rescored.md``
and ``results.rescored.json`` beside it; it refuses to overwrite either, and
never touches the original files.

Output: ``<out-root>/<run-id>/results.json``, ``report.md`` and ``raw/`` (every
call's answer, with ``ensure_ascii`` so no raw em dash lands in the repo). A
live held-out run that passes G3b also writes
``<out-root>/validated-pairing.json`` and prints the setting to apply. A dry
run writes nothing unless ``--out-root`` is given.

Exit codes: 0 done (live: G3b passed; dry run: always); 1 live run finished and
G3b failed; 2 bad arguments, unreadable or mismatching inputs, or a refused
held-out run; 3 the spend cap stopped the run; 4 the reviewer is not
independent of the writer.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess  # nosec B404 - fixed argv, no shell, used only for git show
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, cast

from pydantic import ValidationError

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError
from cyo_adventure.core.pricing import ModelPrice, price_for
from cyo_adventure.generation.prompts import plan_review_prompt_hash
from cyo_adventure.moderation.plan_reviewer import (
    ASSUMED_PRICE,
    PlanReviewResult,
    ReviewSpendCap,
    StubReviewProvider,
    build_plan_reviewer_provider,
    build_review_prompt,
    reasoning_from_settings,
    review_plan,
)
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan.checks import check_plan
from cyo_adventure.storyplan.models import StoryPlan, book_sha256
from cyo_adventure.storyplan.review import (
    PlanReview,
    ReviewFinding,
    ValidatedPairing,
    assert_independent,
    format_validated_pairing,
    plan_content_hash,
)
from cyo_adventure.storyplan.review_figures import (
    AGREEMENT_MIN,
    CLEAN_FLAG_MAX,
    MIN_CLEAN_BOOKS,
    MIN_DEFECTIVE,
    RECALL_MIN,
    REJECT_EVERYTHING_MIN,
    Figures,
    G3bResult,
    ScoredPlan,
    check_held_out_allowed,
    compute_figures,
    evaluate_g3b,
    project_costs,
    seeded_entry_ids,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.moderation.review_provider import ReviewProvider
    from cyo_adventure.validator.report import ValidationReport

REPO: Final = Path(__file__).resolve().parents[1]
EVIDENCE: Final = REPO / "docs/planning/evidence"
REAL_SET: Final = EVIDENCE / "continuity-reader/validation-set.json"
SYNTHETIC_SET: Final = (
    EVIDENCE / "plan-reviewer/synthetic/validation-set.synthetic.json"
)
BASELINES: Final = EVIDENCE / "plan-reviewer/clean-baselines/manifest.json"
OUT_ROOT: Final = EVIDENCE / "plan-reviewer"
HELD_OUT_RUNS_NAME: Final = "held-out-runs.json"
RESCORED_REPORT_NAME: Final = "report.rescored.md"
RESCORED_RESULTS_NAME: Final = "results.rescored.json"
PAIRING_NAME: Final = "validated-pairing.json"

EXIT_OK: Final = 0
EXIT_G3B_FAILED: Final = 1
EXIT_BAD_INPUT: Final = 2
EXIT_SPEND_STOP: Final = 3
EXIT_NOT_INDEPENDENT: Final = 4

CHARS_PER_TOKEN: Final = 2.1
"""Measured on the 2026-11-21 pilot: 74,842 plan characters, 41,430 prompt tokens."""
ASSUMED_OUTPUT_TOKENS: Final = 14_000
"""The pilot's twelve calls averaged about 14,000 completion tokens, mostly reasoning."""

Half = Literal["tuning", "held_out"]


@dataclass(frozen=True)
class Paths:
    """Where the harness reads and writes (overridable for tests).

    Attributes:
        repo: The repository root (relative file paths in the sets resolve here).
        real_set: The real validation set.
        synthetic_set: The synthetic validation set.
        baselines: The clean-baselines manifest.
        out_root: Where run directories, the held-out record and the pairing go.
    """

    repo: Path = REPO
    real_set: Path = REAL_SET
    synthetic_set: Path = SYNTHETIC_SET
    baselines: Path = BASELINES
    out_root: Path = OUT_ROOT

    @property
    def held_out_runs(self) -> Path:
        """Return the held-out run record path.

        Returns:
            Path: ``<out_root>/held-out-runs.json``.
        """
        return self.out_root / HELD_OUT_RUNS_NAME


@dataclass(frozen=True)
class Candidate:
    """One validation item, loaded and verified.

    Attributes:
        id: The item id.
        source: ``real``, ``synthetic``, ``baseline`` or ``real_clean`` (a
            clean-labelled real plan that is only checked, never reviewed).
        half: ``tuning`` or ``held_out``.
        unit: The book.
        expected: ``reject`` or ``pass``.
        plan: The parsed plan.
        book: The parsed book.
        book_digest: SHA-256 hex of the book file's bytes.
        severity: Worst severity carried.
        blockers: Blocker-severity defect entry ids.
        family: Synthetic family.
        defect_class: Synthetic class or rule.
        needed_repair: For a baseline, whether the repair changed it.
        residual_entries: Known residuals' node and choice ids.
        seeded_entries: For a synthetic item, the entry ids its seed edited.
        files: The plan and book file paths, for the results record.
    """

    id: str
    source: str
    half: str
    unit: str
    expected: Literal["reject", "pass"]
    plan: StoryPlan
    book: Storybook
    book_digest: str
    severity: str | None = None
    blockers: tuple[str, ...] = ()
    family: str | None = None
    defect_class: str | None = None
    needed_repair: bool | None = None
    residual_entries: frozenset[str] = field(default_factory=frozenset)
    seeded_entries: frozenset[str] = field(default_factory=frozenset)
    files: dict[str, str] = field(default_factory=dict)


class InputError(BusinessLogicError):
    """A validation input is missing, unreadable or does not match its hash."""

    def __init__(self, message: str) -> None:
        """Record the problem.

        Args:
            message: What is wrong and which file.
        """
        super().__init__(message, rule="plan_reviewer_validation_input")


def _sha256(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``.

    Args:
        data: The bytes.

    Returns:
        str: The digest.
    """
    return hashlib.sha256(data).hexdigest()


def _json_object(path: Path) -> dict[str, object]:
    """Read a JSON file that must hold an object.

    Args:
        path: The file.

    Returns:
        dict[str, object]: The object.

    Raises:
        InputError: When the file is missing, unreadable or not an object.
    """
    try:
        loaded = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"cannot read {path}: {type(exc).__name__}"
        raise InputError(msg) from exc
    if not isinstance(loaded, dict):
        msg = f"{path} must hold a JSON object"
        raise InputError(msg)
    return cast("dict[str, object]", loaded)


def _mapping(value: object) -> dict[str, object]:
    """Narrow a decoded value to a dict, or an empty one.

    Args:
        value: Any decoded JSON value.

    Returns:
        dict[str, object]: The dict, or ``{}``.
    """
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _strings(value: object) -> list[str]:
    """Narrow a decoded value to its string members.

    Args:
        value: Any decoded JSON value.

    Returns:
        list[str]: The strings of a list, else ``[]``.
    """
    if not isinstance(value, list):
        return []
    return [m for m in cast("list[object]", value) if isinstance(m, str)]


def read_verified(
    paths: Paths, rel: str, *, sha256: object, revision: object = None
) -> bytes:
    """Read a repo file, at a git revision when one is named, and verify its hash.

    Args:
        paths: The harness paths.
        rel: The repo-relative file path.
        sha256: The expected SHA-256 hex, or None to skip verification.
        revision: ``git:<commit>`` to read ``git show <commit>:<rel>``; anything
            else (``working-tree``, None) reads the file.

    Returns:
        bytes: The file's bytes.

    Raises:
        InputError: When the file or revision cannot be read, or the hash does
            not match.
    """
    if isinstance(revision, str) and revision.startswith("git:"):
        commit = revision.removeprefix("git:")
        proc = subprocess.run(
            ["git", "-C", str(paths.repo), "show", f"{commit}:{rel}"],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            msg = (
                f"cannot read {rel} at revision {commit} (a shallow clone lacks "
                "pinned revisions)"
            )
            raise InputError(msg)
        data = proc.stdout
    else:
        try:
            data = (paths.repo / rel).read_bytes()
        except OSError as exc:
            msg = f"cannot read {rel}: {type(exc).__name__}"
            raise InputError(msg) from exc
    if isinstance(sha256, str) and _sha256(data) != sha256:
        msg = f"sha256 mismatch for {rel}: the file is not the one the set records"
        raise InputError(msg)
    return data


def _load_pair(
    paths: Paths, item: Mapping[str, object]
) -> tuple[StoryPlan, Storybook, str, dict[str, str]]:
    """Load and verify one item's plan and book.

    Args:
        paths: The harness paths.
        item: The validation item.

    Returns:
        tuple[StoryPlan, Storybook, str, dict[str, str]]: The plan, the book,
            the book bytes' digest and the file paths.

    Raises:
        InputError: When a file is missing, mismatching or invalid.
    """
    plan_ref = _mapping(item.get("plan"))
    book_ref = _mapping(item.get("book"))
    plan_file = str(plan_ref.get("file", ""))
    book_file = str(book_ref.get("file", ""))
    plan_bytes = read_verified(
        paths,
        plan_file,
        sha256=plan_ref.get("sha256"),
        revision=plan_ref.get("revision"),
    )
    book_bytes = read_verified(
        paths,
        book_file,
        sha256=book_ref.get("sha256"),
        revision=book_ref.get("revision"),
    )
    try:
        plan = StoryPlan.model_validate(json.loads(plan_bytes))
        book = Storybook.model_validate(json.loads(book_bytes))
    except (ValidationError, json.JSONDecodeError) as exc:
        msg = f"item {item.get('id')}: invalid plan or book ({type(exc).__name__})"
        raise InputError(msg) from exc
    return plan, book, book_sha256(book_bytes), {"plan": plan_file, "book": book_file}


def _residual_entries(item: Mapping[str, object]) -> frozenset[str]:
    """Collect the node and choice ids of an item's known residuals.

    Args:
        item: The validation item.

    Returns:
        frozenset[str]: The ids.
    """
    raw = item.get("known_residuals")
    entries: set[str] = set()
    if isinstance(raw, list):
        for residual in cast("list[object]", raw):
            data = _mapping(residual)
            entries.update(_strings(data.get("nodes")))
            choice = data.get("choice")
            if isinstance(choice, str):
                entries.add(choice)
    return frozenset(entries)


def _blockers(item: Mapping[str, object]) -> tuple[str, ...]:
    """Collect the ids of an item's blocker-severity defect entries.

    Args:
        item: The validation item.

    Returns:
        tuple[str, ...]: The ids, in item order.
    """
    out: list[str] = []
    defects = item.get("defects")
    if isinstance(defects, list):
        for defect in cast("list[object]", defects):
            data = _mapping(defect)
            if data.get("severity") == "blocker" and isinstance(data.get("id"), str):
                out.append(str(data["id"]))
    return tuple(out)


def _seeded(item: Mapping[str, object]) -> frozenset[str]:
    """Derive the entry ids a synthetic item's seed edited.

    Args:
        item: The synthetic validation item.

    Returns:
        frozenset[str]: The ids from its ``edited_paths`` pointers.
    """
    return seeded_entry_ids(_strings(item.get("edited_paths")))


def _items(document: Mapping[str, object]) -> list[dict[str, object]]:
    """Return a set's ``items`` as dicts.

    Args:
        document: The decoded set.

    Returns:
        list[dict[str, object]]: The items.
    """
    raw = document.get("items")
    if not isinstance(raw, list):
        return []
    return [_mapping(i) for i in cast("list[object]", raw)]


def load_candidates(
    paths: Paths, half: Half
) -> tuple[list[Candidate], dict[str, object]]:
    """Load every item of one half that the harness scores.

    Real plans: ``kind: plan``, strong label, ``reject`` (defective, reviewed)
    or ``pass`` (clean-labelled, checked only). Synthetic plans: every item of
    the half. Baselines: every manifest item of the half.

    Args:
        paths: The harness paths.
        half: ``tuning`` or ``held_out``.

    Returns:
        tuple[list[Candidate], dict[str, object]]: The candidates and a record
            of what was skipped and why.

    Raises:
        InputError: When a set or the baselines manifest is missing, or any
            file fails verification.
    """
    skipped: dict[str, int] = {"unknown": 0, "weak": 0}
    out: list[Candidate] = []
    real = _json_object(paths.real_set)
    for item in _items(real):
        if item.get("kind") != "plan" or item.get("half") != half:
            continue
        verdict = item.get("expected_verdict")
        if verdict == "unknown":
            skipped["unknown"] += 1
            continue
        if item.get("label_strength") != "strong":
            skipped["weak"] += 1
            continue
        plan, book, digest, files = _load_pair(paths, item)
        expected: Literal["reject", "pass"] = (
            "reject" if verdict == "reject" else "pass"
        )
        out.append(
            Candidate(
                id=str(item["id"]),
                source="real" if expected == "reject" else "real_clean",
                half=half,
                unit=str(_mapping(item.get("book")).get("unit")),
                expected=expected,
                plan=plan,
                book=book,
                book_digest=digest,
                severity=cast("str | None", item.get("severity")),
                blockers=_blockers(item),
                residual_entries=_residual_entries(item),
                files=files,
            )
        )
    synthetic = _json_object(paths.synthetic_set)
    for item in _items(synthetic):
        if item.get("kind") != "plan" or item.get("half") != half:
            continue
        plan, book, digest, files = _load_pair(paths, item)
        out.append(
            Candidate(
                id=str(item["id"]),
                source="synthetic",
                half=half,
                unit=str(_mapping(item.get("book")).get("unit")),
                expected="reject",
                plan=plan,
                book=book,
                book_digest=digest,
                severity=cast("str | None", item.get("severity")),
                family=cast("str | None", item.get("family")),
                defect_class=cast(
                    "str | None", item.get("class_code") or item.get("intended_rule")
                ),
                seeded_entries=_seeded(item),
                files=files,
            )
        )
    if not paths.baselines.is_file():
        msg = (
            f"the clean-baselines manifest {paths.baselines} does not exist; the "
            "clean sample (the checker-repaired baselines of five books) must be "
            "built before this harness can run"
        )
        raise InputError(msg)
    manifest = _json_object(paths.baselines)
    if manifest.get("schema") != "clean-baselines/v1":
        msg = f"{paths.baselines}: expected schema clean-baselines/v1"
        raise InputError(msg)
    for item in _items(manifest):
        if item.get("half") != half:
            continue
        plan, book, digest, files = _load_pair(paths, item)
        out.append(
            Candidate(
                id=str(item["id"]),
                source="baseline",
                half=half,
                unit=str(_mapping(item.get("book")).get("unit")),
                expected="pass",
                plan=plan,
                book=book,
                book_digest=digest,
                needed_repair=bool(item.get("needed_repair")),
                residual_entries=_residual_entries(item),
                files=files,
            )
        )
    return out, {"skipped_real_plans": skipped}


def _checker(candidate: Candidate) -> ValidationReport:
    """Run SP-0 to SP-9 on a candidate as ``check_story_plan.py`` does.

    Args:
        candidate: The candidate.

    Returns:
        ValidationReport: The report.
    """
    return check_plan(candidate.plan, candidate.book, book_digest=candidate.book_digest)


def _scored(candidate: Candidate, review: PlanReview) -> ScoredPlan:
    """Turn a candidate and its review into a scored plan.

    Args:
        candidate: The candidate.
        review: The final answer.

    Returns:
        ScoredPlan: The scored plan.
    """
    source = cast("Literal['real', 'synthetic', 'baseline']", candidate.source)
    return ScoredPlan(
        id=candidate.id,
        source=source,
        half=candidate.half,
        unit=candidate.unit,
        expected=candidate.expected,
        review=review,
        severity=candidate.severity,
        blockers=candidate.blockers,
        family=candidate.family,
        defect_class=candidate.defect_class,
        needed_repair=candidate.needed_repair,
        residual_entries=candidate.residual_entries,
        seeded_entries=candidate.seeded_entries,
    )


@dataclass
class RunOutcome:
    """What running the candidates produced.

    Attributes:
        scored: The scored plans (reviewed and checker-caught).
        results: Each reviewed or checker-rejected plan's result.
        checker_only: Clean-labelled real plans: id, checker error rules.
        spend_stopped: True when the cap refused a call.
        unrun: Ids not run because of a spend stop.
    """

    scored: list[ScoredPlan] = field(default_factory=list)
    results: dict[str, PlanReviewResult] = field(default_factory=dict)
    checker_only: dict[str, list[str]] = field(default_factory=dict)
    spend_stopped: bool = False
    unrun: list[str] = field(default_factory=list)


async def run_candidates(
    candidates: Sequence[Candidate],
    *,
    provider: ReviewProvider | None,
    writer_model: str,
    reviewer_model: str,
    settings: Settings,
    runs: int,
    concurrency: int,
    spend_cap: ReviewSpendCap | None,
    price: ModelPrice,
) -> RunOutcome:
    """Run the checker on every candidate and the reviewer where it is needed.

    Args:
        candidates: The loaded candidates.
        provider: The reviewer leg (None only when nothing needs a model).
        writer_model: The plan writer's model id.
        reviewer_model: The reviewer's model id.
        settings: Settings (reasoning effort, max tokens).
        runs: Calls per plan.
        concurrency: Calls in flight.
        spend_cap: The hard cap, or None.
        price: The reviewer's price.

    Returns:
        RunOutcome: Scored plans and results.
    """
    # #CRITICAL: payment/financial: every call goes through the shared cap and
    # a plan that the cap refuses is recorded as unrun, so a partial run can
    # never be mistaken for a validation (G3b requires a complete run).
    # #VERIFY: test_validate_plan_reviewer.py::test_a_spend_stop_makes_the_run_incomplete.
    outcome = RunOutcome()
    semaphore = asyncio.Semaphore(max(1, concurrency))
    reasoning = reasoning_from_settings(settings)

    async def one(candidate: Candidate) -> tuple[Candidate, PlanReviewResult | None]:
        report = _checker(candidate)
        if candidate.source == "real_clean":
            outcome.checker_only[candidate.id] = sorted(
                {f.rule_id for f in report.errors}
            )
            return candidate, None
        result = await review_plan(
            plan_id=plan_content_hash(
                cast(
                    "dict[str, object]",
                    candidate.plan.model_dump(mode="json", exclude_none=True),
                )
            ),
            plan=candidate.plan,
            book=candidate.book,
            checker=report,
            provider=provider,
            writer_model=writer_model,
            reviewer_model=reviewer_model,
            reasoning=reasoning,
            runs=runs,
            max_tokens=settings.story_plan_reviewer_max_tokens,
            spend_cap=spend_cap,
            semaphore=semaphore,
            price=price,
        )
        return candidate, result

    for candidate, result in await asyncio.gather(*(one(c) for c in candidates)):
        if result is None:
            continue
        outcome.results[candidate.id] = result
        if result.spend_stopped:
            outcome.spend_stopped = True
            outcome.unrun.append(candidate.id)
            continue
        outcome.scored.append(_scored(candidate, result.review))
    return outcome


def estimate_run(
    candidates: Sequence[Candidate],
    *,
    runs: int,
    price_in: float,
    price_out: float,
    output_tokens: int,
) -> dict[str, object]:
    """Project the tokens and cost of running the reviewer over the candidates.

    Only plans the checker passes reach the reviewer, so the prompts are built
    for exactly those; the estimate is otherwise the cost model of
    :func:`~cyo_adventure.storyplan.review_figures.project_costs`.

    Args:
        candidates: The loaded candidates.
        runs: Calls per plan.
        price_in: USD per million input tokens.
        price_out: USD per million output tokens.
        output_tokens: Assumed output tokens per call (reasoning included).

    Returns:
        dict[str, object]: The projection plus how many plans the checker
            already rejects.
    """
    chars: list[int] = []
    caught = 0
    for candidate in candidates:
        if candidate.source == "real_clean":
            continue
        report = _checker(candidate)
        if report.errors:
            caught += 1
            continue
        prompt, _ = build_review_prompt(candidate.plan, candidate.book, report)
        chars.append(len(prompt.system) + len(prompt.user))
    projection = project_costs(
        chars,
        runs=runs,
        chars_per_token=CHARS_PER_TOKEN,
        output_tokens_per_call=output_tokens,
        input_usd_per_mtok=price_in,
        output_usd_per_mtok=price_out,
    )
    projection["checker_already_rejects"] = caught
    projection["largest_prompt_chars"] = max(chars, default=0)
    return projection


def _read_runs(path: Path) -> list[dict[str, object]]:
    """Read the held-out run record, or an empty list when none exists.

    Args:
        path: ``held-out-runs.json``.

    Returns:
        list[dict[str, object]]: The run entries.

    Raises:
        InputError: When the file exists and is malformed.
    """
    if not path.is_file():
        return []
    runs = _json_object(path).get("runs")
    if not isinstance(runs, list):
        msg = f"{path}: 'runs' must be a list"
        raise InputError(msg)
    return [_mapping(r) for r in cast("list[object]", runs)]


def _write_json(path: Path, value: object) -> None:
    """Write JSON atomically with ASCII-only output.

    Args:
        path: The destination.
        value: The JSON-serializable value.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _write_runs(path: Path, runs: Sequence[Mapping[str, object]]) -> None:
    """Write the held-out run record.

    Args:
        path: ``held-out-runs.json``.
        runs: The run entries.
    """
    _write_json(
        path,
        {
            "schema": "held-out-runs/v1",
            "rule": (
                "D12: a held-out run per pairing, then one prompt revision after "
                "a failed first run, then stop; a prompt hash already run is refused"
            ),
            "runs": list(runs),
        },
    )


def _record_started(path: Path, entry: Mapping[str, object]) -> None:
    """Append a started held-out run before any call is made.

    Written first so a run that crashes after spending still counts as run.

    Args:
        path: ``held-out-runs.json``.
        entry: The run entry.
    """
    _write_runs(path, [*_read_runs(path), dict(entry)])


def _record_finished(
    path: Path, run_id: str, *, g3b_passed: bool, spend_stopped: bool
) -> None:
    """Mark a held-out run finished.

    Args:
        path: ``held-out-runs.json``.
        run_id: The run.
        g3b_passed: Whether G3b passed.
        spend_stopped: Whether the cap stopped the run.
    """
    runs = _read_runs(path)
    for run in runs:
        if run.get("run_id") == run_id:
            run["finished"] = True
            run["g3b_passed"] = g3b_passed
            run["spend_stopped"] = spend_stopped
    _write_runs(path, runs)


def _fmt_rate(value: object) -> str:
    """Render a proportion dict's count and rate.

    Args:
        value: A ``Proportion.to_dict()`` result.

    Returns:
        str: ``k/n = rate (95% low to high)``.
    """
    data = _mapping(value)
    n = cast("int", data.get("n", 0))
    if n == 0:
        return "0/0 (no plans)"
    ci = cast("list[float]", data.get("ci95", [0.0, 1.0]))
    return f"{data['k']}/{n} = {cast('float', data['rate']):.2f} (95% {ci[0]:.2f} to {ci[1]:.2f})"


_DRY_RUN_NOTE = "**Dry run: a stub provider answered every call, so no figure below measures the reviewer.**"
_TUNING_NOTE = " (the tuning half never passes G3b: it guides prompt work only)"
_DEFECTS_NOTE = "A plan's `defects` are every defect its book revision carries, an upper bound on what is visible in the plan."
_SYNTHETIC_NOTE = "Synthetic recall overstates real recall: each seed is one defect at a known place in an otherwise clean plan."
_LOCATED_NOTE = "Located recall credits a seed only when a reviewer finding (either run) names an entry the seed edited; the any-reject figure credits any reject or unsure, so a reviewer that rejects everything scores 100 percent on it. Located recall is informational: D12 sets no threshold for it, and G3b is unchanged."
_RESIDUAL_NOTE = "A reviewer finding at a recorded known residual is a true positive, not a false flag (`AL-882`); a flag elsewhere on the book is still a false flag."
_RESCORED_NOTE = "Re-scored offline from an existing run's results.json (no model call); the original report.md and results.json are unchanged. Source:"
_LIMITS = (
    "- Synthetic recall overstates real recall, and family A is checker-visible by construction.",
    "- The clean sample is five books; per-book results matter more than the pooled rate.",
    "- The plan writer is Sonnet 5.5, so the reviewer must be a different model; independence is enforced on configured ids only.",
    "- There is no measured recall on dull, generic or off-request plans: those classes stay advisory.",
    "- One reader per book labelled the real set; a clean label is the latest verified state.",
)


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    """Render a Markdown table with a header row.

    Args:
        header: The column names.
        rows: The rows.

    Returns:
        list[str]: The table lines.
    """
    out = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    out.extend("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return out


def _run_rows(run: Mapping[str, object]) -> list[Sequence[object]]:
    """Return the run-header table rows.

    Args:
        run: The ``run`` block of the results document.

    Returns:
        list[Sequence[object]]: ``(item, value)`` rows.
    """
    reported = (
        ", ".join(f"`{m}`" for m in cast("list[str]", run["reported_models"])) or "none"
    )
    lower = "" if run["cost_complete"] else " (a lower bound: some cost unknown)"
    reasoning = f"effort `{run['reasoning_effort']}`, max_tokens {run['max_tokens']}, temperature {run['temperature']}"
    plans = f"{run['plans_run']} run, {run['plans_checker_only']} clean-labelled checked only, {run['plans_unrun']} unrun"
    spend = f"{cast('float', run['cost_usd']):.2f} USD{lower}, cap {run['budget_usd'] or 'none (dry run)'}"
    return [
        ("Half", run["half"]),
        ("Reviewer model (configured)", f"`{run['reviewer_model']}`"),
        ("Reviewer model (reported by the provider)", reported),
        ("Writer model", f"`{run['writer_model']}`"),
        ("Prompt hash", f"`{run['prompt_hash']}`"),
        ("Runs per plan", run["runs"]),
        ("Reasoning", reasoning),
        ("Plans", plans),
        ("Spend", spend),
        ("Finish reasons", run["finish_reason_counts"]),
        ("Tokens in / out", f"{run['input_tokens']} / {run['output_tokens']}"),
    ]


def _cost_note(est: Mapping[str, object]) -> str:
    """Render the cost-projection paragraph.

    Args:
        est: The ``estimate`` block.

    Returns:
        str: One paragraph.
    """
    a = _mapping(est.get("assumptions"))
    tokens = f"{cast('int', est['input_tokens']):,} input and {cast('int', est['output_tokens']):,} output tokens"
    price = f"{a.get('input_usd_per_mtok')} in and {a.get('output_usd_per_mtok')} out per million tokens"
    basis = f"{a.get('chars_per_token')} characters per input token, {a.get('output_tokens_per_call')} output tokens per call"
    return f"Projected: {est['plans']} plans reach the reviewer ({est['checker_already_rejects']} the checker already rejects), {est['calls']} calls, {tokens}, about {est['usd']} USD at {price} ({basis})."


def _reject_everything_warning(diagnostic: Mapping[str, object]) -> str:
    """Render the warning that the reviewer flags nearly everything.

    Args:
        diagnostic: The ``reject_everything_diagnostic`` figures block.

    Returns:
        str: One paragraph.
    """
    return (
        f"**WARNING: the reviewer flagged more than {REJECT_EVERYTHING_MIN:.0%} of both "
        f"clean baselines ({_fmt_rate(diagnostic['clean_baselines_flagged'])}) and seeds "
        f"({_fmt_rate(diagnostic['seeds_flagged'])}): it discriminates nothing, so its "
        "any-reject recall means nothing; read located recall.**"
    )


def _located_cell(plan: Mapping[str, object]) -> str:
    """Render the "seed located" cell of the plans table.

    Args:
        plan: One plan record of the results document.

    Returns:
        str: ``yes`` or ``NO`` for a plan with seeded entries, else ``-``.
    """
    if not plan.get("seeded_entry_ids"):
        return "-"
    return "yes" if plan.get("located") else "NO"


def render_report(context: Mapping[str, object]) -> str:
    """Render ``report.md`` from a results document.

    Args:
        context: The results document (``results.json``'s content).

    Returns:
        str: The Markdown.
    """
    figures = _mapping(context["figures"])
    g3b = _mapping(context["g3b"])
    run = _mapping(context["run"])
    real = _mapping(figures["real_defective"])
    synth = _mapping(figures["synthetic"])
    clean = _mapping(figures["clean_baselines"])
    live = bool(run.get("live"))
    held_out = run["half"] == "held_out"
    verdict = f"**G3b: {'PASS' if g3b['passed'] else 'FAIL'}**" + (
        "" if held_out else _TUNING_NOTE
    )
    thresholds = f"Thresholds are the owner's D12 values, fixed before any prompt was written: recall at least {RECALL_MIN} and every blocker entry; clean flag rate at most {CLEAN_FLAG_MAX}; run agreement at least {AGREEMENT_MIN}; at least {MIN_DEFECTIVE} defective plans; the clean minimum met by baselines of {MIN_CLEAN_BOOKS} books, reported per book. Synthetic recall is reported and is not a threshold."
    checks = [
        (c["name"], "yes" if c["passed"] else "NO", c["detail"])
        for c in cast("list[dict[str, object]]", g3b["checks"])
    ]
    severity_rows = [
        (f"Recall, worst severity {k}", _fmt_rate(v))
        for k, v in _mapping(real["by_worst_severity"]).items()
    ]
    blocker_rows = [
        (
            e,
            _mapping(r)["plans"],
            _mapping(r)["flagged"],
            "yes" if _mapping(r)["plans"] == _mapping(r)["flagged"] else "NO",
        )
        for e, r in _mapping(real["blocker_entries"]).items()
    ]
    class_rows = [
        (f"Family B class {k}", _fmt_rate(v))
        for k, v in _mapping(synth["family_B_by_class"]).items()
    ]
    located_class_rows = [
        (f"Family B class {k}, located", _fmt_rate(v))
        for k, v in _mapping(synth["family_B_located_by_class"]).items()
    ]
    book_rows = [
        (b, _mapping(r)["plans"], _mapping(r)["flagged"], _mapping(r)["false_flags"])
        for b, r in _mapping(clean["by_book"]).items()
    ]
    diagnostic = _mapping(figures["reject_everything_diagnostic"])
    lines = [
        f"# Plan reviewer validation run {run['run_id']}",
        "",
        _DRY_RUN_NOTE if not live else f"Live run on the {run['half']} half.",
        "",
    ]
    rescored = _mapping(context.get("rescored"))
    if rescored:
        lines += [f"{_RESCORED_NOTE} {rescored.get('source')}.", ""]
    lines += ["## Run", ""]
    lines += _table(("Item", "Value"), _run_rows(run))
    lines += ["", "## Verdict (G3b)", "", verdict, ""]
    lines += _table(("Condition", "Met", "Detail"), checks)
    lines += [
        "",
        thresholds,
        "",
        f"Informational, not a threshold: located recall, family B: {_fmt_rate(synth['family_B_located'])} (any-reject recall {_fmt_rate(synth['family_B_checker_invisible'])}).",
        "",
    ]
    if diagnostic["warning"]:
        lines += [_reject_everything_warning(diagnostic), ""]
    lines += ["## (a) Real defective plans", ""]
    lines += _table(
        ("Figure", "Value"),
        [
            (
                "Recall overall (checker plus reviewer)",
                _fmt_rate(real["recall_overall"]),
            ),
            (
                "Of which checker-caught (no model call)",
                _fmt_rate(real["checker_caught"]),
            ),
            (
                "Reviewer-decisive recall (the reviewer's own)",
                _fmt_rate(real["reviewer_decisive_recall"]),
            ),
            *severity_rows,
        ],
    )
    lines += [
        "",
        "Every blocker entry (a plan that carries it counts once per entry):",
        "",
    ]
    lines += (
        _table(
            ("Blocker entry", "Plans carrying it", "Flagged", "All flagged"),
            blocker_rows,
        )
        if blocker_rows
        else ["No blocker entries in this half."]
    )
    lines += [
        "",
        _DEFECTS_NOTE,
        "",
        "## (b) Synthetic plans (never merged with the real set)",
        "",
    ]
    lines += _table(
        ("Figure", "Value"),
        [
            (
                "Family A, checker-visible (a floor, not reviewing skill)",
                _fmt_rate(synth["family_A_checker_visible"]),
            ),
            (
                "Family B, checker-invisible",
                _fmt_rate(synth["family_B_checker_invisible"]),
            ),
            *class_rows,
            (
                "Family B, located (a finding names a seeded entry)",
                _fmt_rate(synth["family_B_located"]),
            ),
            *located_class_rows,
        ],
    )
    unscorable = cast("int", synth["family_B_located_unscorable"])
    lines += ["", _SYNTHETIC_NOTE, "", _LOCATED_NOTE]
    if unscorable:
        lines += [
            "",
            f"{unscorable} family B plan(s) have no known seeded entry and are left out of the located figures.",
        ]
    lines += ["", "## (c) Clean baselines", ""]
    lines += _table(
        ("Figure", "Value"),
        [
            ("Flag rate, raw (reject or unsure)", _fmt_rate(clean["flag_rate_raw"])),
            (
                "False-flag rate (flags not at a known residual)",
                _fmt_rate(clean["false_flag_rate"]),
            ),
            (
                "Flags explained by a known residual (true positives)",
                clean["flags_explained_by_known_residual"],
            ),
            (
                "False flags on baselines that needed repair",
                _fmt_rate(clean["needed_repair_false_flags"]),
            ),
            (
                "False flags on baselines that needed no repair",
                _fmt_rate(clean["no_repair_false_flags"]),
            ),
        ],
    )
    lines += [
        "",
        "Per book (the effective clean sample is the books, not the plans):",
        "",
    ]
    lines += _table(("Book", "Baselines", "Flagged", "False flags"), book_rows)
    lines += ["", _RESIDUAL_NOTE, "", "## (d) Run agreement", ""]
    lines += [
        f"Identical verdicts across the runs of a plan: {_fmt_rate(figures['run_agreement'])}.",
        "",
        "## (e) Cost model",
        "",
    ]
    est = _mapping(context.get("estimate"))
    lines += [_cost_note(est) if est else "No projection recorded.", ""]
    lines += ["## (f) Reject-everything diagnostic", ""]
    lines += _table(
        ("Figure", "Value"),
        [
            (
                "Flagged, every plan the reviewer ran on (clean and defective)",
                _fmt_rate(diagnostic["reviewer_run_plans_flagged"]),
            ),
            (
                "Flagged, clean baselines",
                _fmt_rate(diagnostic["clean_baselines_flagged"]),
            ),
            (
                "Flagged, seeds the reviewer ran on",
                _fmt_rate(diagnostic["seeds_flagged"]),
            ),
        ],
    )
    lines += [
        "",
        _reject_everything_warning(diagnostic)
        if diagnostic["warning"]
        else f"No warning: the reviewer did not flag more than {REJECT_EVERYTHING_MIN:.0%} of both clean baselines and seeds.",
        "",
        "## Plans",
        "",
    ]
    plans = cast("list[dict[str, object]]", context["plans"])
    plan_rows: list[Sequence[object]] = []
    for plan in plans:
        review = _mapping(plan["review"])
        rules = cast("list[str]", plan["checker_error_rules"])
        plan_rows.append(
            (
                plan["id"],
                plan["source"],
                plan["unit"],
                plan["expected"],
                f"ERROR {','.join(rules)}" if rules else "clean",
                ", ".join(cast("list[str]", review["run_verdicts"])) or "none",
                review["verdict"],
                len(cast("list[object]", review["findings"])),
                _located_cell(plan),
            )
        )
    lines += _table(
        (
            "Plan",
            "Source",
            "Book",
            "Expected",
            "Checker",
            "Run verdicts",
            "Final",
            "Findings",
            "Seed located",
        ),
        plan_rows,
    )
    lines += [
        "",
        "## Findings by plan (flagged plans; reasons are in results.json)",
        "",
    ]
    for plan in plans:
        findings = cast("list[dict[str, object]]", _mapping(plan["review"])["findings"])
        if _mapping(plan["review"])["verdict"] != "pass" and findings:
            listed = "; ".join(
                f"{f['entry']} ({f['class']}, {f['severity']})" for f in findings[:8]
            )
            lines.append(f"- {plan['id']}: {listed}")
    lines += ["", "## Limits", "", *_LIMITS, ""]
    return "\n".join(lines)


def _located_fields(scored: ScoredPlan) -> dict[str, object]:
    """Return the per-plan record that lets located recall be recomputed offline.

    Args:
        scored: The scored plan.

    Returns:
        dict[str, object]: ``blockers``, ``residual_entries``, ``seeded_entry_ids``,
            ``reviewer_findings_at_entry`` (every seeded id with the class and
            severity of each finding naming it; an empty list means that seeded
            entry was not named) and ``located``.
    """
    return {
        "blockers": list(scored.blockers),
        "residual_entries": sorted(scored.residual_entries),
        "seeded_entry_ids": sorted(scored.seeded_entries),
        "reviewer_findings_at_entry": {
            entry: [
                {"class": f.defect_class, "severity": f.severity}
                for f in scored.review.findings
                if f.entry == entry
            ]
            for entry in sorted(scored.seeded_entries)
        },
        "located": scored.located,
    }


def build_results(
    *,
    run_id: str,
    half: str,
    live: bool,
    outcome: RunOutcome,
    candidates: Sequence[Candidate],
    figures: Figures,
    g3b: G3bResult,
    estimate: Mapping[str, object],
    settings: Settings,
    reviewer_model: str,
    writer_model: str,
    runs: int,
    budget: Decimal | None,
    partial: bool,
    skipped: Mapping[str, object],
) -> dict[str, object]:
    """Assemble the ``results.json`` document.

    Args:
        run_id: The run id.
        half: The half.
        live: Whether a real model ran.
        outcome: The run outcome.
        candidates: The loaded candidates.
        figures: The figures.
        g3b: The gate verdict.
        estimate: The cost projection.
        settings: Settings used.
        reviewer_model: The reviewer.
        writer_model: The writer.
        runs: Calls per plan.
        budget: The cap, or None.
        partial: Whether ``--only`` narrowed the run.
        skipped: What loading skipped.

    Returns:
        dict[str, object]: The document.
    """
    calls = [c for r in outcome.results.values() for c in r.runs]
    reported = sorted({c.model for c in calls if c.called})
    finish: dict[str, int] = {}
    for call in calls:
        finish[call.finish_reason] = finish.get(call.finish_reason, 0) + 1
    by_id = {c.id: c for c in candidates}
    plans: list[dict[str, object]] = []
    for scored in outcome.scored:
        result = outcome.results[scored.id]
        candidate = by_id[scored.id]
        plans.append(
            {
                "id": scored.id,
                "source": scored.source,
                "half": scored.half,
                "unit": scored.unit,
                "expected": scored.expected,
                "severity": scored.severity,
                "family": scored.family,
                "defect_class": scored.defect_class,
                "needed_repair": scored.needed_repair,
                "files": candidate.files,
                **_located_fields(scored),
                "checker_error_rules": sorted(
                    r.removeprefix("checker_error:")
                    for r in scored.review.reasons
                    if r.startswith("checker_error:")
                ),
                "review": scored.review.to_dict(),
                "cost_usd": float(result.cost_usd),
                "finish_reasons": list(result.finish_reasons),
            }
        )
    return {
        "schema": "plan-reviewer-run/v1",
        "run": {
            "run_id": run_id,
            "half": half,
            "live": live,
            "dry_run": not live,
            "partial": partial,
            "date": datetime.now(UTC).date().isoformat(),
            "reviewer_model": reviewer_model,
            "reported_models": reported,
            "writer_model": writer_model,
            "prompt_hash": plan_review_prompt_hash(),
            "runs": runs,
            "reasoning_effort": settings.story_plan_reviewer_reasoning_effort,
            "max_tokens": settings.story_plan_reviewer_max_tokens,
            "temperature": settings.story_plan_reviewer_temperature,
            "sample_rate_setting": settings.story_plan_reviewer_sample_rate,
            "plans_run": len(outcome.scored),
            "plans_checker_only": len(outcome.checker_only),
            "plans_unrun": len(outcome.unrun),
            "unrun_ids": outcome.unrun,
            "spend_stopped": outcome.spend_stopped,
            "budget_usd": None if budget is None else str(budget),
            "cost_usd": float(
                sum((r.cost_usd for r in outcome.results.values()), Decimal(0))
            ),
            "cost_complete": all(r.cost_complete for r in outcome.results.values()),
            "input_tokens": sum(r.input_tokens for r in outcome.results.values()),
            "output_tokens": sum(r.output_tokens for r in outcome.results.values()),
            "finish_reason_counts": finish,
            **dict(skipped),
        },
        "estimate": dict(estimate),
        "figures": figures.to_dict(),
        "g3b": g3b.to_dict(),
        "checker_only_clean_plans": outcome.checker_only,
        "plans": plans,
    }


def write_run(
    out_dir: Path, document: Mapping[str, object], outcome: RunOutcome
) -> None:
    """Write ``results.json``, ``report.md`` and the raw per-call outputs.

    Args:
        out_dir: ``<out-root>/<run-id>``.
        document: The results document.
        outcome: The run outcome (for raw outputs).
    """
    _write_json(out_dir / "results.json", document)
    (out_dir / "report.md").write_text(render_report(document), encoding="utf-8")
    for plan_id, result in outcome.results.items():
        for call in result.runs:
            _write_json(
                out_dir / "raw" / f"{plan_id}.run{call.run}.json",
                {"plan_id": plan_id, **call.to_dict(include_raw=True)},
            )


_VERDICTS: Final = ("pass", "reject", "unsure")
_SEVERITIES: Final = ("blocker", "should-fix", "minor")


def _review_from_record(data: Mapping[str, object]) -> PlanReview:
    """Rebuild a plan's final answer from its ``results.json`` record.

    Args:
        data: The record's ``review`` block (``PlanReview.to_dict()``).

    Returns:
        PlanReview: The review.

    Raises:
        InputError: When the verdict is not one the reviewer can give.
    """
    verdict = data.get("verdict")
    if verdict not in _VERDICTS:
        msg = f"results.json: unknown verdict {verdict!r}"
        raise InputError(msg)
    findings: list[ReviewFinding] = []
    raw_findings = data.get("findings")
    for raw in (
        cast("list[object]", raw_findings) if isinstance(raw_findings, list) else []
    ):
        entry = _mapping(raw)
        severity = entry.get("severity")
        findings.append(
            ReviewFinding(
                entry=str(entry.get("entry", "")),
                defect_class=str(entry.get("class", "other")),
                severity=severity if severity in _SEVERITIES else "should-fix",
                reason=str(entry.get("reason", "")),
                entry_known=entry.get("entry_known") is not False,
            )
        )
    confidence = data.get("confidence")
    return PlanReview(
        verdict=verdict,
        confidence=float(confidence)
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        else None,
        findings=tuple(findings),
        reasons=tuple(_strings(data.get("reasons"))),
        run_verdicts=tuple(
            v for v in _strings(data.get("run_verdicts")) if v in _VERDICTS
        ),
        checker_caught=data.get("checker_caught") is True,
        reviewer_pass_overridden=data.get("reviewer_pass_overridden") is True,
        reviewer_ran=data.get("reviewer_ran") is not False,
    )


def _set_metadata(paths: Paths, half: str) -> dict[str, dict[str, object]]:
    """Read per-item blockers, residuals and seeded entries from the committed sets.

    Used only to back-fill a ``results.json`` written before it recorded them.
    It reads the three set files and loads no plan, book or git revision.

    Args:
        paths: The harness paths.
        half: The run's half.

    Returns:
        dict[str, dict[str, object]]: Item id to ``blockers``,
            ``residual_entries`` and ``seeded_entry_ids``.

    Raises:
        InputError: When a set file cannot be read.
    """
    out: dict[str, dict[str, object]] = {}
    documents = [_json_object(paths.real_set), _json_object(paths.synthetic_set)]
    if paths.baselines.is_file():
        documents.append(_json_object(paths.baselines))
    for document in documents:
        for item in _items(document):
            if item.get("half") != half or not isinstance(item.get("id"), str):
                continue
            out[str(item["id"])] = {
                "blockers": list(_blockers(item)),
                "residual_entries": sorted(_residual_entries(item)),
                "seeded_entry_ids": sorted(_seeded(item)),
            }
    return out


def _rescored_plans(document: Mapping[str, object], paths: Paths) -> list[ScoredPlan]:
    """Rebuild every scored plan of a run from its ``results.json``.

    A record that lacks ``blockers``, ``residual_entries`` or
    ``seeded_entry_ids`` (written before they were recorded) is back-filled
    from the committed sets by item id.

    Args:
        document: The decoded ``results.json``.
        paths: The harness paths (for the back-fill).

    Returns:
        list[ScoredPlan]: One scored plan per record.

    Raises:
        InputError: When a record is malformed or the back-fill cannot be read.
    """
    records = [_mapping(p) for p in cast("list[object]", document.get("plans", []))]
    half = str(_mapping(document.get("run")).get("half"))
    keys = ("blockers", "residual_entries", "seeded_entry_ids")
    backfill: dict[str, dict[str, object]] = {}
    if any(k not in record for record in records for k in keys):
        backfill = _set_metadata(paths, half)
    scored: list[ScoredPlan] = []
    for record in records:
        extra = backfill.get(str(record.get("id")), {})
        merged = {k: record[k] if k in record else extra.get(k, []) for k in keys}
        source = record.get("source")
        expected = record.get("expected")
        if source not in ("real", "synthetic", "baseline") or expected not in (
            "reject",
            "pass",
        ):
            msg = f"results.json: plan {record.get('id')!r} has an unknown source or label"
            raise InputError(msg)
        scored.append(
            ScoredPlan(
                id=str(record["id"]),
                source=source,
                half=str(record.get("half")),
                unit=str(record.get("unit")),
                expected=expected,
                review=_review_from_record(_mapping(record.get("review"))),
                severity=cast("str | None", record.get("severity")),
                blockers=tuple(_strings(merged["blockers"])),
                family=cast("str | None", record.get("family")),
                defect_class=cast("str | None", record.get("defect_class")),
                needed_repair=cast("bool | None", record.get("needed_repair")),
                residual_entries=frozenset(_strings(merged["residual_entries"])),
                seeded_entries=frozenset(_strings(merged["seeded_entry_ids"])),
            )
        )
    return scored


def rescore_run(run_dir: Path, paths: Paths) -> int:
    """Recompute a finished run's figures from its ``results.json``; no model call.

    Writes ``report.rescored.md`` and ``results.rescored.json`` beside the
    original and refuses to overwrite either (or to run when the original is
    missing). The original ``results.json``, ``report.md`` and ``raw/`` are never
    written. G3b is re-evaluated with the same rules; its verdict is recorded
    beside the original's so a change would be visible.

    Args:
        run_dir: The run directory (holds ``results.json``).
        paths: The harness paths (for the back-fill of older results files).

    Returns:
        int: The exit code (0 done, 2 bad input or a refused overwrite).
    """
    # #ASSUME: external resources: run_dir holds a results.json this harness wrote
    # #VERIFY: a missing or malformed file stops with EXIT_BAD_INPUT, nothing written.
    report_path = run_dir / RESCORED_REPORT_NAME
    results_path = run_dir / RESCORED_RESULTS_NAME
    existing = [p.name for p in (report_path, results_path) if p.exists()]
    if existing:
        held = ", ".join(existing)
        _err(
            f"REFUSED: {run_dir} already holds {held}; a re-score never overwrites (move or delete it first)"
        )
        return EXIT_BAD_INPUT
    try:
        document = _json_object(run_dir / "results.json")
        scored = _rescored_plans(document, paths)
    except InputError as exc:
        _err(f"FAIL: {exc.message}")
        return EXIT_BAD_INPUT
    run = _mapping(document.get("run"))
    only_clean = _mapping(document.get("checker_only_clean_plans"))
    figures = compute_figures(
        scored,
        checker_only_clean=sum(1 for rules in only_clean.values() if rules),
    )
    complete = run.get("spend_stopped") is not True and run.get("partial") is not True
    g3b = evaluate_g3b(
        figures,
        half=str(run.get("half")),
        live=run.get("live") is True,
        complete=complete,
    )
    original_g3b = _mapping(document.get("g3b"))
    rescored = dict(document)
    rescored["figures"] = figures.to_dict()
    rescored["g3b"] = g3b.to_dict()
    rescored["plans"] = [
        {**_mapping(record), **_located_fields(plan)}
        for record, plan in zip(
            cast("list[object]", document.get("plans", [])), scored, strict=True
        )
    ]
    rescored["rescored"] = {
        "source": f"{run_dir.name}/results.json",
        "date": datetime.now(UTC).date().isoformat(),
        "model_calls": 0,
        "original_g3b_passed": original_g3b.get("passed"),
        "g3b_passed_now": g3b.passed,
        "note": (
            "figures recomputed from the recorded reviews; located recall and "
            "the reject-everything diagnostic are informational and change no "
            "G3b rule"
        ),
    }
    _write_json(results_path, rescored)
    report_path.write_text(render_report(rescored), encoding="utf-8")
    sys.stdout.write(f"wrote {results_path} and {report_path}\n")
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser.

    Returns:
        argparse.ArgumentParser: The parser.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--half", default=None, choices=["tuning", "held_out"])
    parser.add_argument(
        "--rescore",
        default=None,
        metavar="RUN_DIR",
        help=(
            "Recompute the figures of an existing run directory from its "
            "results.json (no model call) and write report.rescored.md and "
            "results.rescored.json beside it; never overwrites."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Stub provider; no network."
    )
    mode.add_argument("--live", action="store_true", help="Call the reviewer model.")
    parser.add_argument(
        "--budget", default=None, help="Hard spend cap, USD (required for --live)."
    )
    parser.add_argument("--confirm-held-out", action="store_true")
    parser.add_argument("--reviewer-model", default=None)
    parser.add_argument("--writer-model", default=None)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=4, help="Calls in flight.")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument(
        "--effort", default=None, choices=["none", "minimal", "low", "medium", "high"]
    )
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument(
        "--price-in", type=float, default=None, help="USD per million input tokens."
    )
    parser.add_argument(
        "--price-out", type=float, default=None, help="USD per million output tokens."
    )
    parser.add_argument(
        "--assumed-output-tokens", type=int, default=ASSUMED_OUTPUT_TOKENS
    )
    parser.add_argument(
        "--only", default=None, help="Comma-separated item ids (a partial run)."
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--out-root", default=None, help="Output root (dry runs write only if given)."
    )
    return parser


def _resolve_price(args: argparse.Namespace, model: str) -> tuple[ModelPrice, str]:
    """Pick the reviewer's price: flags, then ``core/pricing.py``, then the assumption.

    Args:
        args: The parsed arguments.
        model: The reviewer model.

    Returns:
        tuple[ModelPrice, str]: The price and where it came from.
    """
    table = price_for("openrouter", model)
    base = table or ASSUMED_PRICE
    price_in = cast("float | None", args.price_in)
    price_out = cast("float | None", args.price_out)
    if price_in is None and price_out is None:
        return base, (
            "core/pricing.py" if table else "assumed 3 in, 15 out per million tokens"
        )
    return (
        ModelPrice(
            input_usd_per_mtok=Decimal(str(price_in))
            if price_in is not None
            else base.input_usd_per_mtok,
            output_usd_per_mtok=Decimal(str(price_out))
            if price_out is not None
            else base.output_usd_per_mtok,
            as_of=base.as_of,
            source="command line",
        ),
        "command line",
    )


def _err(message: str) -> None:
    """Write a line to stderr.

    Args:
        message: The text.
    """
    sys.stderr.write(message + "\n")


async def _async_main(args: argparse.Namespace) -> int:
    """Run one validation with the default or ``--out-root`` paths.

    Args:
        args: The parsed arguments.

    Returns:
        int: The exit code.
    """
    root = cast("str | None", args.out_root)
    paths = Paths(out_root=Path(root)) if root else Paths()
    rescore = cast("str | None", args.rescore)
    if rescore is not None:
        if (
            cast("bool", args.live)
            or cast("bool", args.dry_run)
            or cast("str | None", args.half) is not None
        ):
            _err(
                "FAIL: --rescore takes only a run directory (no --half, --live or --dry-run)"
            )
            return EXIT_BAD_INPUT
        return rescore_run(Path(rescore), paths)
    if cast("str | None", args.half) is None:
        _err("FAIL: --half is required (or --rescore <run-dir>)")
        return EXIT_BAD_INPUT
    return await run_validation(args, paths)


async def run_validation(
    args: argparse.Namespace,
    paths: Paths,
    *,
    provider_override: ReviewProvider | None = None,
) -> int:
    """Run one validation end to end.

    Args:
        args: The parsed arguments.
        paths: The harness paths.
        provider_override: A provider to use instead of the stub or live leg
            (tests).

    Returns:
        int: The exit code.
    """
    half = cast("Half", args.half)
    live = cast("bool", args.live)
    if not live and not cast("bool", args.dry_run):
        _err(
            "FAIL: choose --dry-run (stub provider) or --live (calls the reviewer model)"
        )
        return EXIT_BAD_INPUT
    budget_text = cast("str | None", args.budget)
    if live and budget_text is None:
        _err(
            "FAIL: refusing to start a live run without --budget <usd> (a hard spend cap)"
        )
        return EXIT_BAD_INPUT
    budget: Decimal | None = None
    if budget_text is not None:
        try:
            budget = Decimal(budget_text)
        except InvalidOperation:
            _err("FAIL: --budget must be a number of USD")
            return EXIT_BAD_INPUT
        if budget <= 0:
            _err("FAIL: --budget must be positive")
            return EXIT_BAD_INPUT
    settings = Settings()
    overrides: dict[str, object] = {}
    if cast("float | None", args.temperature) is not None:
        overrides["story_plan_reviewer_temperature"] = cast("float", args.temperature)
    if cast("str | None", args.effort) is not None:
        overrides["story_plan_reviewer_reasoning_effort"] = cast("str", args.effort)
    if cast("int | None", args.max_tokens) is not None:
        overrides["story_plan_reviewer_max_tokens"] = cast("int", args.max_tokens)
    if overrides:
        settings = settings.model_copy(update=overrides)
    reviewer = (
        cast("str | None", args.reviewer_model) or settings.story_plan_reviewer_model
    )
    writer = cast("str | None", args.writer_model) or settings.story_plan_writer_model
    try:
        assert_independent(writer, reviewer)
    except BusinessLogicError as exc:
        _err(f"REFUSED: {exc.message}")
        return EXIT_NOT_INDEPENDENT
    try:
        candidates, skipped = load_candidates(paths, half)
    except InputError as exc:
        _err(f"FAIL: {exc.message}")
        return EXIT_BAD_INPUT
    only = cast("str | None", args.only)
    partial = only is not None
    if only is not None:
        wanted = {i.strip() for i in only.split(",") if i.strip()}
        missing = wanted - {c.id for c in candidates}
        if missing:
            _err(f"FAIL: --only names items not in the {half} half: {sorted(missing)}")
            return EXIT_BAD_INPUT
        candidates = [c for c in candidates if c.id in wanted]
    prompt_hash = plan_review_prompt_hash()
    price, price_source = _resolve_price(args, reviewer)
    estimate = estimate_run(
        candidates,
        runs=cast("int", args.runs),
        price_in=float(price.input_usd_per_mtok or 0),
        price_out=float(price.output_usd_per_mtok or 0),
        output_tokens=cast("int", args.assumed_output_tokens),
    )
    projection = f"cost projection ({price_source}): {estimate['plans']} plans reach the reviewer ({estimate['checker_already_rejects']} already rejected by the checker), {estimate['calls']} calls, about {estimate['usd']} USD"
    sys.stdout.write(projection + "\n")
    run_id = cast("str | None", args.run_id) or (
        f"{datetime.now(UTC).date().isoformat()}-{half}-{prompt_hash.removeprefix('sha256:')[:8]}"
        + ("" if live else "-dry")
    )
    out_dir = paths.out_root / run_id
    writes = live or cast("str | None", args.out_root) is not None
    if writes and out_dir.exists():
        _err(f"FAIL: {out_dir} already exists; pass a new --run-id")
        return EXIT_BAD_INPUT
    if live and half == "held_out":
        if not cast("bool", args.confirm_held_out):
            _err(
                "FAIL: --half held_out needs --confirm-held-out (D12: the held-out half is one look)"
            )
            return EXIT_BAD_INPUT
        try:
            allowed, reason = check_held_out_allowed(
                _read_runs(paths.held_out_runs),
                writer_model=writer,
                reviewer_model=reviewer,
                prompt_hash=prompt_hash,
            )
        except InputError as exc:
            _err(f"FAIL: {exc.message}")
            return EXIT_BAD_INPUT
        if not allowed:
            _err(f"REFUSED: {reason}")
            return EXIT_BAD_INPUT
        _record_started(
            paths.held_out_runs,
            {
                "run_id": run_id,
                "writer_model": writer,
                "reviewer_model": reviewer,
                "prompt_hash": prompt_hash,
                "started": datetime.now(UTC).isoformat(timespec="seconds"),
                "finished": False,
                "g3b_passed": None,
                "partial": partial,
            },
        )
    provider: ReviewProvider
    if provider_override is not None:
        provider = provider_override
    elif live:
        try:
            provider = build_plan_reviewer_provider(settings, reviewer)
        except ConfigurationError as exc:
            _err(f"FAIL: {exc.message}")
            return EXIT_BAD_INPUT
    else:
        provider = StubReviewProvider(model=f"stub:{reviewer}")
    cap = ReviewSpendCap(budget_usd=budget, price=price) if budget is not None else None
    outcome = await run_candidates(
        candidates,
        provider=provider,
        writer_model=writer,
        reviewer_model=reviewer,
        settings=settings,
        runs=cast("int", args.runs),
        concurrency=cast("int", args.concurrency),
        spend_cap=cap,
        price=price,
    )
    figures = compute_figures(
        outcome.scored,
        checker_only_clean=sum(1 for rules in outcome.checker_only.values() if rules),
    )
    complete = not outcome.spend_stopped and not partial
    g3b = evaluate_g3b(figures, half=half, live=live, complete=complete)
    document = build_results(
        run_id=run_id,
        half=half,
        live=live,
        outcome=outcome,
        candidates=candidates,
        figures=figures,
        g3b=g3b,
        estimate=estimate,
        settings=settings,
        reviewer_model=reviewer,
        writer_model=writer,
        runs=cast("int", args.runs),
        budget=budget,
        partial=partial,
        skipped=skipped,
    )
    if writes:
        write_run(out_dir, document, outcome)
        sys.stdout.write(f"wrote {out_dir}/results.json and report.md\n")
    else:
        sys.stdout.write(render_report(document))
    if live and half == "held_out":
        _record_finished(
            paths.held_out_runs,
            run_id,
            g3b_passed=g3b.passed,
            spend_stopped=outcome.spend_stopped,
        )
    sys.stdout.write(f"G3b: {'PASS' if g3b.passed else 'FAIL'}\n")
    if g3b.passed and live and half == "held_out":
        pairing = ValidatedPairing(writer, reviewer, prompt_hash)
        _write_json(
            paths.out_root / PAIRING_NAME,
            {
                "schema": "validated-pairing/v1",
                "writer_model": writer,
                "reviewer_model": reviewer,
                "prompt_hash": prompt_hash,
                "run_id": run_id,
                "validated_on": datetime.now(UTC).date().isoformat(),
                "setting": "story_plan_reviewer_validated_pairing",
                "value": format_validated_pairing(pairing),
            },
        )
        value = format_validated_pairing(pairing)
        sys.stdout.write(
            f"validated pairing recorded; set STORY_PLAN_REVIEWER_VALIDATED_PAIRING={value}\n"
        )
    if outcome.spend_stopped:
        return EXIT_SPEND_STOP
    if not live:
        return EXIT_OK
    return EXIT_OK if g3b.passed else EXIT_G3B_FAILED


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: The exit code.
    """
    args = _build_parser().parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
