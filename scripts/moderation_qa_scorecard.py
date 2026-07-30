"""Score the staging Moderation QA corpus against its labeled ground truth.

Implements moderation-review-redesign-2026-07-28.md section 5, deliverable 4:
reads the persisted ``moderation_report`` for every ``mqa_``-prefixed
storybook version (seeded and moderated by ``scripts/seed_moderation_qa.py``)
and compares it against ``docs/planning/safety/moderation-qa-corpus.json``'s
expected labels, at both the whole-story and per-node level. Prints a
pass/fail table to stdout and exits nonzero if any comparison fails, so a
regression in the classifiers/reviewer/repair pipeline is a red CI/manual
check rather than a silent drift.

The comparison logic (:func:`compare_book`, :func:`story_verdict_from_report`,
:func:`node_verdict_from_report`, :func:`meets_floor`) is pure and takes
in-memory report dicts, so it is unit-testable without a database; only
:func:`_load_reports` and :func:`main` touch the database.

Run against staging (read-only; requires the corpus to have already been
seeded and moderated)::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/moderation_qa_scorecard.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import get_engine
from cyo_adventure.db.models import StorybookVersion

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_PATH = (
    _REPO_ROOT / "docs" / "planning" / "safety" / "moderation-qa-corpus.json"
)
_MODERATED_VERSION = 1

# Mirrors moderation/report.py::Verdict; the manifest's own
# verdict_severity list is asserted to match this ordering by
# tests/unit/test_moderation_qa_corpus.py, so drift between the two is
# caught at fixture-integrity time, not silently here.
_VERDICT_RANK: dict[str, int] = {"pass": 0, "advisory": 1, "flag": 2, "block": 3}

# S105 (hardcoded-password heuristic) is a false positive here: these are
# scorecard row labels, not credentials.
_STATUS_MISSING = "MISSING"
_STATUS_OK = "PASS"
_STATUS_FAIL = "FAIL"


def load_manifest() -> list[dict[str, Any]]:
    """Load the moderation QA corpus manifest's book entries.

    Returns:
        The manifest's ``books`` array (id, expected labels).
    """
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    books: list[dict[str, Any]] = manifest["books"]
    return books


def verdict_rank(verdict: str) -> int:
    """Map a verdict string to its severity rank (pass=0 .. block=3).

    Args:
        verdict: One of "pass", "advisory", "flag", "block".

    Returns:
        The verdict's severity rank.

    Raises:
        KeyError: If ``verdict`` is not a recognized verdict string.
    """
    return _VERDICT_RANK[verdict]


def meets_floor(actual: str, floor: str) -> bool:
    """Return True when ``actual`` is at least as severe as ``floor``.

    Args:
        actual: The verdict the moderation pipeline actually produced.
        floor: The manifest's ``expected_min_verdict`` floor.

    Returns:
        True if ``actual``'s severity rank is >= ``floor``'s.
    """
    return verdict_rank(actual) >= verdict_rank(floor)


def story_verdict_from_report(report: dict[str, Any]) -> str:
    """Derive a whole-story verdict as the most severe finding in the report.

    Args:
        report: A persisted ``StorybookVersion.moderation_report`` dict
            (``ModerationReport.to_dict()`` shape: ``{"findings": [...],
            "summary": {...}}``).

    Returns:
        The most severe verdict across every finding, or "pass" if the
        report has no findings (a clean report).
    """
    findings = report.get("findings", [])
    best = "pass"
    for finding in findings:
        verdict = finding.get("verdict", "pass")
        if verdict_rank(verdict) > verdict_rank(best):
            best = verdict
    return best


def node_verdict_from_report(report: dict[str, Any], node_id: str) -> str:
    """Derive a single node's verdict from the findings that reference it.

    Args:
        report: A persisted ``moderation_report`` dict.
        node_id: The node id to look up.

    Returns:
        The most severe verdict among findings whose ``node_id`` matches, or
        "pass" if no finding references this node (the manifest's
        node_label_convention: an unlisted node is expected pass, and an
        unreferenced node here has produced no finding).
    """
    findings = report.get("findings", [])
    best = "pass"
    for finding in findings:
        if finding.get("node_id") != node_id:
            continue
        verdict = finding.get("verdict", "pass")
        if verdict_rank(verdict) > verdict_rank(best):
            best = verdict
    return best


@dataclass(frozen=True)
class ScorecardRow:
    """One comparison row: a book's story-level or single node-level label."""

    book_id: str
    level: str
    expected: str
    actual: str
    negative_control: bool
    status: str


def compare_book(
    entry: dict[str, Any], report: dict[str, Any] | None
) -> list[ScorecardRow]:
    """Compare one manifest book entry against its persisted moderation report.

    Args:
        entry: A manifest book entry (id, expected_min_verdict,
            negative_control, node_labels).
        report: The book's persisted ``moderation_report`` dict, or None if
            the book has not been moderated yet (has never been seeded, or
            was seeded with ``--skip-moderation``).

    Returns:
        One :class:`ScorecardRow` for the story level, plus one per manifest
        node label.
    """
    book_id = str(entry["id"])
    if report is None:
        return [
            ScorecardRow(
                book_id=book_id,
                level="story",
                expected=entry["expected_min_verdict"],
                actual="",
                negative_control=False,
                status=_STATUS_MISSING,
            )
        ]

    rows: list[ScorecardRow] = []
    expected_story = str(entry["expected_min_verdict"])
    negative_control = bool(entry.get("negative_control", False))
    actual_story = story_verdict_from_report(report)
    story_ok = (
        actual_story == "pass"
        if negative_control
        else meets_floor(actual_story, expected_story)
    )
    rows.append(
        ScorecardRow(
            book_id=book_id,
            level="story",
            expected=expected_story,
            actual=actual_story,
            negative_control=negative_control,
            status=_STATUS_OK if story_ok else _STATUS_FAIL,
        )
    )

    for label in entry.get("node_labels", []):
        node_id = str(label["node_id"])
        expected_node = str(label["expected_min_verdict"])
        actual_node = node_verdict_from_report(report, node_id)
        node_ok = meets_floor(actual_node, expected_node)
        rows.append(
            ScorecardRow(
                book_id=book_id,
                level=node_id,
                expected=expected_node,
                actual=actual_node,
                negative_control=False,
                status=_STATUS_OK if node_ok else _STATUS_FAIL,
            )
        )
    return rows


def render_table(rows: list[ScorecardRow]) -> str:
    """Render scorecard rows as a fixed-width stdout table.

    Args:
        rows: The comparison rows to render, in the order they should print.

    Returns:
        The rendered table, including a trailing summary line.
    """
    header = f"{'BOOK':<38} {'LEVEL':<14} {'EXPECTED':<10} {'ACTUAL':<10} {'STATUS':<8}"
    lines = [header, "-" * len(header)]
    for row in rows:
        expected = row.expected + (" (neg)" if row.negative_control else "")
        lines.append(
            f"{row.book_id:<38} {row.level:<14} {expected:<10} {row.actual:<10} {row.status:<8}"
        )
    failed = sum(1 for row in rows if row.status != _STATUS_OK)
    lines.append("-" * len(header))
    lines.append(f"{len(rows)} row(s), {failed} failed/missing")
    return "\n".join(lines)


async def _load_reports(
    session: AsyncSession, book_ids: list[str]
) -> dict[str, dict[str, Any] | None]:
    """Load each book's persisted moderation report by id.

    Args:
        session: An open async session.
        book_ids: The manifest's book ids to look up.

    Returns:
        A mapping of book id to its ``moderation_report`` dict, or None if
        the book has no version row, or its report is still null.
    """
    result: dict[str, dict[str, Any] | None] = dict.fromkeys(book_ids)
    if not book_ids:
        return result
    rows = (
        (
            await session.execute(
                select(StorybookVersion).where(
                    StorybookVersion.storybook_id.in_(book_ids),
                    StorybookVersion.version == _MODERATED_VERSION,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        result[row.storybook_id] = row.moderation_report
    return result


async def score(*, engine: AsyncEngine | None = None) -> list[ScorecardRow]:
    """Score every manifest book against its persisted moderation report.

    Args:
        engine: Async engine to query. Defaults to the app's shared engine
            (``get_engine()``); tests inject a mock engine here.

    Returns:
        The full list of comparison rows across every book.
    """
    active_engine = engine if engine is not None else get_engine()
    session_factory = async_sessionmaker(active_engine, expire_on_commit=False)
    books = load_manifest()
    book_ids = [str(book["id"]) for book in books]
    async with session_factory() as session:
        reports = await _load_reports(session, book_ids)

    rows: list[ScorecardRow] = []
    for entry in books:
        rows.extend(compare_book(entry, reports.get(str(entry["id"]))))
    return rows


def main() -> None:
    """Entry point: print the scorecard table and exit nonzero on any failure."""
    rows = asyncio.run(score())
    print(render_table(rows))
    if any(row.status != _STATUS_OK for row in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
