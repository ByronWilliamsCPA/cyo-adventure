"""Score the staging Moderation QA corpus against its labeled ground truth.

Implements moderation-review-redesign-2026-07-28.md section 5, deliverable 4:
reads the persisted ``moderation_report`` for every ``mqa_``-prefixed
storybook version (seeded and moderated by ``scripts/seed_moderation_qa.py``)
and compares it against ``docs/planning/safety/moderation-qa-corpus.json``'s
expected labels, at both the whole-story and per-node level. Prints a
pass/fail table to stdout and exits nonzero if any comparison fails, so a
regression in the classifiers/reviewer/repair pipeline is a red CI/manual
check rather than a silent drift. One caveat on repair coverage: repair
*adoption* is only reachable for the five gate-clean fixtures, not for
``mqa_borderline_storm_watch_5_8``, which is deliberately off-ceiling. See
``scripts/seed_moderation_qa.py``'s "what this corpus does and does not
exercise" note.

The comparison logic (:func:`compare_book`, :func:`story_verdict_from_report`,
:func:`node_verdict_from_report`, :func:`meets_floor`,
:func:`unknown_verdicts`) is pure and takes in-memory report dicts, so it is
unit-testable without a database; only :func:`_load_reports` and
:func:`main` touch the database.

Negative controls are scored as a CEILING ("no finding at or above flag"),
matching the manifest's own node_label_convention, not as an exactly-clean
report: ADVISORY findings never gate, and every deployed tier emits at least
one of them (the degraded-classifier advisory when a classifier key is unset,
plus subjective stage nits), so an exact-equality rule would fail every
negative control for reasons that have nothing to do with safety.

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
from cyo_adventure.core.exceptions import ConfigurationError
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

# Rank returned for a verdict string this scorecard does not recognize (a
# future Verdict member, or a hand-edited report). Deliberately below "pass"
# so every meets_floor comparison against it is False, i.e. an unrecognized
# verdict can never satisfy a floor.
_UNKNOWN_VERDICT_RANK = -1

# The gating threshold a negative control must stay BELOW. Mirrors the
# manifest's node_label_convention ("no finding at or above flag"): ADVISORY
# findings never gate (moderation/report.py::Verdict), and the deployed tiers
# emit at least one of them on every book (classifiers.py's degraded advisory
# when a classifier key is unset, stages.py's subjective nits), so requiring
# an exactly-clean report would fail every negative control for reasons that
# have nothing to do with safety.
_GATING_VERDICT = "flag"

_STATUS_MISSING = "MISSING"
_STATUS_OK = "PASS"
_STATUS_FAIL = "FAIL"


def load_manifest() -> list[dict[str, Any]]:
    """Load the moderation QA corpus manifest's book entries.

    Returns:
        The manifest's ``books`` array (id, expected labels).

    Raises:
        ConfigurationError: If the manifest is missing, is not valid JSON, or
            has no ``books`` array.
    """
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"moderation QA corpus manifest is unreadable: {_MANIFEST_PATH}"
        raise ConfigurationError(msg, details={"path": str(_MANIFEST_PATH)}) from exc
    except json.JSONDecodeError as exc:
        msg = f"moderation QA corpus manifest is not valid JSON: {_MANIFEST_PATH}"
        raise ConfigurationError(msg, details={"path": str(_MANIFEST_PATH)}) from exc
    if not isinstance(manifest, dict) or "books" not in manifest:
        msg = f"moderation QA corpus manifest has no 'books' array: {_MANIFEST_PATH}"
        raise ConfigurationError(msg, details={"path": str(_MANIFEST_PATH)})
    books: list[dict[str, Any]] = manifest["books"]
    return books


def verdict_rank(verdict: str) -> int:
    """Map a verdict string to its severity rank (pass=0 .. block=3).

    #EDGE: data-integrity: an unrecognized verdict (a future
    ``moderation/report.py::Verdict`` member, or a hand-edited report) must
    not crash the scorecard with a traceback; it degrades to
    :data:`_UNKNOWN_VERDICT_RANK`, which satisfies no floor, and
    :func:`unknown_verdicts` names it on its own FAIL row.
    #VERIFY: test_verdict_rank_degrades_on_unknown_verdict and
    test_compare_book_emits_a_fail_row_naming_an_unknown_verdict in
    tests/unit/test_moderation_qa_scorecard.py.

    Args:
        verdict: One of "pass", "advisory", "flag", "block".

    Returns:
        The verdict's severity rank, or :data:`_UNKNOWN_VERDICT_RANK` for an
        unrecognized verdict string.
    """
    return _VERDICT_RANK.get(verdict, _UNKNOWN_VERDICT_RANK)


def unknown_verdicts(report: dict[str, Any]) -> list[str]:
    """Return every unrecognized verdict string present in a report.

    Args:
        report: A persisted ``moderation_report`` dict.

    Returns:
        The sorted, de-duplicated verdict strings this scorecard cannot rank.
    """
    findings: list[dict[str, Any]] = report.get("findings", [])
    return sorted(
        {
            str(finding.get("verdict", "pass"))
            for finding in findings
            if str(finding.get("verdict", "pass")) not in _VERDICT_RANK
        }
    )


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
        whose ``node_ids`` list contains ``node_id`` (a merged finding,
        design doc 2.2: identical (category, concern) findings across
        several nodes collapse into one finding, keeping ``node_id`` as the
        first affected node and naming every affected node in
        ``node_ids``), or "pass" if no finding references this node (the
        manifest's node_label_convention: an unlisted node is expected pass,
        and an unreferenced node here has produced no finding).
    """
    findings = report.get("findings", [])
    best = "pass"
    for finding in findings:
        node_ids = finding.get("node_ids")
        matches = finding.get("node_id") == node_id or (
            isinstance(node_ids, list) and node_id in node_ids
        )
        if not matches:
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
        node label, plus one "verdict" row per unrecognized verdict string.
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

    rows: list[ScorecardRow] = [
        ScorecardRow(
            book_id=book_id,
            level="verdict",
            expected="/".join(_VERDICT_RANK),
            actual=unknown,
            negative_control=False,
            status=_STATUS_FAIL,
        )
        for unknown in unknown_verdicts(report)
    ]

    expected_story = str(entry["expected_min_verdict"])
    negative_control = bool(entry.get("negative_control", False))
    actual_story = story_verdict_from_report(report)
    # A negative control is a CEILING, not a floor: the manifest's
    # node_label_convention defines it as "no finding at or above flag", so a
    # non-gating ADVISORY (a degraded classifier, a subjective nit) is not a
    # failure. Requiring an exactly-clean report instead would fail every
    # negative control in any deployed tier for reasons unrelated to safety.
    story_ok = (
        verdict_rank(actual_story) < verdict_rank(_GATING_VERDICT)
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
    """Entry point: print the scorecard table and exit nonzero on any failure.

    A corpus that cannot be loaded at all exits with the ``ConfigurationError``
    message (which names the offending path) rather than a raw traceback.
    """
    try:
        rows = asyncio.run(score())
    except ConfigurationError as exc:
        sys.exit(f"moderation_qa_scorecard: {exc}")
    print(render_table(rows))
    if any(row.status != _STATUS_OK for row in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
