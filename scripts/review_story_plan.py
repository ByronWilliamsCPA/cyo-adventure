#!/usr/bin/env python3
"""Review one Story Plan against its book with the plan reviewer (WP-3.7).

Usage:
    uv run python scripts/review_story_plan.py --plan out/<slug>.plan.json \
        --book out/<slug>.filled.json --dry-run
    uv run python scripts/review_story_plan.py --plan out/<slug>.plan.json \
        --book out/<slug>.filled.json --reviewer-model <model> \
        --writer-model <model> --budget 2.00

The deterministic checks (SP-0 to SP-9) run first, as ``check_story_plan.py``
does. If they report an ERROR the plan is rejected as ``checker_caught`` and no
model is called. Otherwise the reviewer is asked twice, the verdicts are
combined (a disagreement is ``unsure``) and the combined verdict is printed
with its findings grouped by plan entry.

``--dry-run`` uses a stub provider that answers ``pass`` for every call: no
network, no key, and the verdict means nothing; it shows the harness, the
prompt size and the cost arithmetic. A live run needs ``--budget`` (a hard cap
in USD, checked before every call) and ``OPENROUTER_API_KEY``. The reviewer
must be a different model from the writer (``--writer-model`` defaults to
``story_plan_writer_model``); the same model or family is refused.

Messages and the printed findings name plan entries and never quote story text.

Exit codes: 0 pass; 1 reject; 2 a file could not be read, a plan or book is
invalid, or the arguments are wrong; 3 unsure; 4 the reviewer is not
independent of the writer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError
from cyo_adventure.core.pricing import price_for
from cyo_adventure.moderation.plan_reviewer import (
    ASSUMED_PRICE,
    PlanReviewResult,
    ReviewSpendCap,
    StubReviewProvider,
    build_plan_reviewer_provider,
    reasoning_from_settings,
    review_plan,
)
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan.checks import check_plan
from cyo_adventure.storyplan.models import StoryPlan, book_sha256
from cyo_adventure.storyplan.review import PlanReview, plan_content_hash

if TYPE_CHECKING:
    from cyo_adventure.moderation.review_provider import ReviewProvider

EXIT_PASS = 0
EXIT_REJECT = 1
EXIT_UNREADABLE = 2
EXIT_UNSURE = 3
EXIT_NOT_INDEPENDENT = 4

_SEVERITY_ORDER = {"blocker": 0, "should-fix": 1, "minor": 2}


def _load(path: Path) -> tuple[object, bytes] | None:
    """Read and decode a JSON file, reporting failure on stderr.

    Args:
        path: The file.

    Returns:
        tuple[object, bytes] | None: The decoded value and the raw bytes, or
            None when unreadable or malformed.
    """
    try:
        raw = path.read_bytes()
        return cast("object", json.loads(raw)), raw
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"FAIL: cannot load {path}: {exc}\n")
        return None


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser.

    Returns:
        argparse.ArgumentParser: The parser.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--plan", required=True, help="The plan JSON.")
    parser.add_argument("--book", required=True, help="The filled book JSON.")
    parser.add_argument("--reviewer-model", default=None, help="Default: settings.")
    parser.add_argument("--writer-model", default=None, help="Default: settings.")
    parser.add_argument("--dry-run", action="store_true", help="Stub provider.")
    parser.add_argument("--budget", default=None, help="Hard spend cap in USD (live).")
    parser.add_argument("--runs", type=int, default=2, help="Calls per plan.")
    parser.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    return parser


def _format_review(review: PlanReview) -> list[str]:
    """Render a review's verdict and findings grouped by entry.

    Args:
        review: The final answer.

    Returns:
        list[str]: The lines.
    """
    lines = [
        f"verdict: {review.verdict}"
        + (
            f" (confidence {review.confidence:.2f})"
            if review.confidence is not None
            else ""
        )
    ]
    if review.checker_caught:
        lines.append("checker_caught: the deterministic checks reported an ERROR")
    if review.reviewer_pass_overridden:
        lines.append("the reviewer's pass was overridden by the checker")
    if review.run_verdicts:
        lines.append("runs: " + ", ".join(review.run_verdicts))
    if review.reasons:
        lines.append("reason codes: " + ", ".join(review.reasons))
    by_entry: dict[str, list[str]] = {}
    for finding in sorted(
        review.findings, key=lambda f: (_SEVERITY_ORDER[f.severity], f.entry)
    ):
        unknown = "" if finding.entry_known else " (entry not in plan)"
        by_entry.setdefault(finding.entry, []).append(
            f"  {finding.severity} {finding.defect_class}{unknown}: {finding.reason}"
        )
    for entry, rows in by_entry.items():
        lines.append(f"{entry}:")
        lines.extend(rows)
    return lines


def _format_cost(result: PlanReviewResult) -> str:
    """Render the call, token and cost line.

    Args:
        result: The review result.

    Returns:
        str: One line.
    """
    lower_bound = "" if result.cost_complete else " (lower bound: a cost is unknown)"
    return (
        f"calls: {len(result.runs)}, finish reasons: {', '.join(result.finish_reasons) or 'none'}, "
        f"tokens in/out: {result.input_tokens}/{result.output_tokens}, "
        f"cost: {result.cost_usd:.4f} USD{lower_bound}, prompt: {result.prompt_hash[:19]}"
    )


async def _run(args: argparse.Namespace) -> int:
    """Load, check and review one plan.

    Args:
        args: The parsed arguments.

    Returns:
        int: The exit code.
    """
    plan_loaded = _load(Path(cast("str", args.plan)))
    book_loaded = _load(Path(cast("str", args.book)))
    if plan_loaded is None or book_loaded is None:
        return EXIT_UNREADABLE
    try:
        plan = StoryPlan.model_validate(plan_loaded[0])
        book = Storybook.model_validate(book_loaded[0])
    except ValidationError as exc:
        sys.stderr.write(f"FAIL: invalid plan or book: {len(exc.errors())} error(s)\n")
        return EXIT_UNREADABLE
    report = check_plan(plan, book, book_digest=book_sha256(book_loaded[1]))
    settings = Settings()
    reviewer = (
        cast("str | None", args.reviewer_model) or settings.story_plan_reviewer_model
    )
    writer = cast("str | None", args.writer_model) or settings.story_plan_writer_model
    dry = cast("bool", args.dry_run)
    budget_text = cast("str | None", args.budget)
    if not dry and budget_text is None:
        sys.stderr.write(
            "FAIL: a live review needs --budget <usd> (or use --dry-run)\n"
        )
        return EXIT_UNREADABLE
    provider: ReviewProvider | None = None
    spend_cap: ReviewSpendCap | None = None
    if report.ok:
        if dry:
            provider = StubReviewProvider(model=f"stub:{reviewer}")
        else:
            try:
                budget = Decimal(cast("str", budget_text))
                provider = build_plan_reviewer_provider(settings, reviewer)
            except (InvalidOperation, ConfigurationError) as exc:
                sys.stderr.write(f"FAIL: {type(exc).__name__}\n")
                return EXIT_UNREADABLE
            spend_cap = ReviewSpendCap(
                budget_usd=budget,
                price=price_for("openrouter", reviewer) or ASSUMED_PRICE,
            )
    plan_id = plan_content_hash(
        cast("dict[str, object]", plan.model_dump(mode="json", exclude_none=True))
    )
    try:
        result = await review_plan(
            plan_id=plan_id,
            plan=plan,
            book=book,
            checker=report,
            provider=provider,
            writer_model=writer,
            reviewer_model=reviewer,
            reasoning=reasoning_from_settings(settings),
            runs=cast("int", args.runs),
            max_tokens=settings.story_plan_reviewer_max_tokens,
            spend_cap=spend_cap,
        )
    except BusinessLogicError as exc:
        sys.stderr.write(f"REFUSED: {exc.message}\n")
        return EXIT_NOT_INDEPENDENT
    if cast("bool", args.json):
        sys.stdout.write(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=True) + "\n"
        )
    else:
        mode = "dry run (stub provider; the verdict means nothing)" if dry else "live"
        sys.stdout.write(
            f"plan reviewer, {mode}; reviewer {reviewer}, writer {writer}\n"
        )
        sys.stdout.write(
            f"checker: {len(report.errors)} error(s), {len(report.warnings)} warning(s)\n"
        )
        sys.stdout.write("\n".join(_format_review(result.review)) + "\n")
        sys.stdout.write(_format_cost(result) + "\n")
    return {"pass": EXIT_PASS, "reject": EXIT_REJECT}.get(
        result.review.verdict, EXIT_UNSURE
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: The exit code.
    """
    args = _build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
