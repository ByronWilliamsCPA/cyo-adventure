#!/usr/bin/env python3
"""Validate the authoring lessons log's structure so the log cannot rot silently.

The log (``docs/planning/authoring-lessons-log.md``) is the durable record of what
each story development run taught us, and its value depends entirely on being
appended to consistently. A malformed row, a reused id, or an ``applied`` claim
with nothing to prove it degrades the log into prose nobody trusts, so those
conditions are errors here rather than review comments.

Checks:

1. The log table is present and its header matches the documented column set.
2. Every id matches ``AL-NNN``, ids are unique, and they run consecutively from
   ``AL-001`` (a gap means a row was deleted; ids are never reused or renumbered).
3. Every ``Date`` is an ISO date.
4. Every ``Category`` and ``Status`` is in the documented vocabulary.
5. ``Lesson`` and ``Proposed change`` are non-empty.
6. A row whose status is ``applied``, ``rejected``, or ``superseded`` carries a
   non-empty ``Ref``, because those three statuses are claims about something
   having happened.

Usage::

    uv run python scripts/check_lessons_log.py
    uv run python scripts/check_lessons_log.py --log path/to/log.md

Exit codes:
    0 - the log is well formed.
    1 - at least one check failed, or the log could not be read.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG = _REPO_ROOT / "docs" / "planning" / "authoring-lessons-log.md"

_COLUMNS: tuple[str, ...] = (
    "ID",
    "Date",
    "Source",
    "Category",
    "Lesson",
    "Proposed change",
    "Status",
    "Ref",
)

_CATEGORIES = frozenset(
    {
        "validator",
        "tooling",
        "authoring-craft",
        "scale",
        "metadata",
        "process",
        "docs",
        "product",
    }
)

_STATUSES = frozenset({"open", "accepted", "applied", "rejected", "superseded"})

# The three statuses that assert something already happened, so a reference is
# mandatory: a bare "applied" is exactly the unverifiable claim this log exists
# to prevent.
_STATUSES_NEEDING_REF = frozenset({"applied", "rejected", "superseded"})

_ID_RE = re.compile(r"^AL-(\d{3})$")

# Split on a pipe that is not backslash-escaped, so a cell may carry a literal
# '|' as '\|' exactly as the column-count error message promises authors it can.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def _split_row(line: str) -> list[str]:
    """Split one markdown table row into its trimmed cell values.

    A literal pipe inside a cell is written escaped (``\\|``); the split honours
    that escape and then unescapes it, so such a cell counts as one column
    rather than being torn in two.

    Args:
        line: A single table line, with or without surrounding pipes.

    Returns:
        list[str]: The cell values, outer empty strings from the leading and
            trailing pipes removed.
    """
    cells = [
        cell.strip().replace("\\|", "|")
        for cell in _UNESCAPED_PIPE_RE.split(line.strip())
    ]
    if cells and not cells[0]:
        cells = cells[1:]
    if cells and not cells[-1]:
        cells = cells[:-1]
    return cells


def _is_separator(cells: list[str]) -> bool:
    """Report whether a split row is a markdown header separator (``---``)."""
    return bool(cells) and all(set(cell) <= {"-", ":"} and cell for cell in cells)


def _find_log_table(lines: list[str]) -> tuple[int, list[str]]:
    """Return the 1-based line number and cells of the log table's header row.

    The log table is identified by its header rather than by position, so
    surrounding prose (including the field-documentation table, which has a
    different header) can be edited freely.

    Args:
        lines: The log file's lines.

    Returns:
        tuple[int, list[str]]: The header's 1-based line number and its cells.

    Raises:
        LookupError: If no row matching the documented column set is found.
    """
    for number, line in enumerate(lines, start=1):
        if "|" not in line:
            continue
        cells = _split_row(line)
        if tuple(cells) == _COLUMNS:
            return number, cells
    msg = f"no log table found with header {' | '.join(_COLUMNS)}"
    raise LookupError(msg)


def _collect_rows(lines: list[str], header_line: int) -> list[tuple[int, list[str]]]:
    """Return the data rows following the log table header.

    Args:
        lines: The log file's lines.
        header_line: 1-based line number of the header row.

    Returns:
        list[tuple[int, list[str]]]: One (line number, cells) pair per data row,
            stopping at the first line that is not part of the table.
    """
    rows: list[tuple[int, list[str]]] = []
    for offset, line in enumerate(lines[header_line:], start=header_line + 1):
        if "|" not in line:
            break
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        rows.append((offset, cells))
    return rows


def _check_row(number: int, cells: list[str]) -> list[str]:
    """Return one problem string per failed check for a single data row.

    Args:
        number: The row's 1-based line number, for the message.
        cells: The row's cell values.

    Returns:
        list[str]: Problems found; empty when the row is well formed.
    """
    if len(cells) != len(_COLUMNS):
        return [
            (
                f"line {number}: expected {len(_COLUMNS)} columns, "
                f"found {len(cells)} "
                f"(a literal '|' inside a cell must be escaped as '\\|')"
            )
        ]

    row = dict(zip(_COLUMNS, cells, strict=True))
    problems: list[str] = []
    entry_id = row["ID"]

    if not _ID_RE.match(entry_id):
        problems.append(f"line {number}: id '{entry_id}' is not of the form AL-NNN")

    try:
        date.fromisoformat(row["Date"])
    except ValueError:
        problems.append(f"{entry_id}: date '{row['Date']}' is not an ISO date")

    if row["Category"] not in _CATEGORIES:
        allowed = ", ".join(sorted(_CATEGORIES))
        problems.append(
            f"{entry_id}: category '{row['Category']}' is not one of: {allowed}"
        )

    status = row["Status"]
    if status not in _STATUSES:
        allowed = ", ".join(sorted(_STATUSES))
        problems.append(f"{entry_id}: status '{status}' is not one of: {allowed}")

    problems.extend(
        f"{entry_id}: {field} is empty"
        for field in ("Source", "Lesson", "Proposed change")
        if not row[field]
    )

    if status in _STATUSES_NEEDING_REF and not row["Ref"]:
        problems.append(
            f"{entry_id}: status '{status}' asserts something happened, so Ref "
            f"must cite the commit, PR, file, or decision that proves it"
        )

    return problems


def _check_id_sequence(rows: list[tuple[int, list[str]]]) -> list[str]:
    """Return problems with the id sequence across all rows.

    Ids must be unique and consecutive from 001: a gap means a row was deleted,
    and the log is append-only precisely so a lesson cannot quietly disappear.

    Args:
        rows: The (line number, cells) pairs from the log table.

    Returns:
        list[str]: Problems found; empty when the sequence is sound.
    """
    numbers: list[int] = []
    seen: set[str] = set()
    problems: list[str] = []
    for _, cells in rows:
        if not cells:
            continue
        entry_id = cells[0]
        if entry_id in seen:
            problems.append(f"{entry_id}: duplicate id")
            continue
        seen.add(entry_id)
        match = _ID_RE.match(entry_id)
        if match:
            numbers.append(int(match.group(1)))

    expected = list(range(1, len(numbers) + 1))
    if sorted(numbers) != expected:
        missing = sorted(set(expected) - set(numbers))
        if missing:
            gaps = ", ".join(f"AL-{n:03d}" for n in missing)
            problems.append(
                f"id sequence has gaps ({gaps}); ids are append-only and are "
                f"never reused or renumbered, so mark a withdrawn lesson "
                f"'rejected' instead of deleting its row"
            )
    return problems


def check_log(path: Path) -> list[str]:
    """Validate a lessons log and return every problem found.

    Args:
        path: The log markdown file.

    Returns:
        list[str]: One problem per failed check; empty when the log is valid.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]

    try:
        header_line, _ = _find_log_table(lines)
    except LookupError as exc:
        return [str(exc)]

    rows = _collect_rows(lines, header_line)
    if not rows:
        return [f"{path.name}: log table has a header but no rows"]

    problems: list[str] = []

    # A blank line silently ends a markdown table, so an appended block separated
    # from the table by one splits the log in two and every row after the gap
    # stops being checked at all. The count still looks plausible, which is the
    # dangerous part: this check exists because that failure passed once.
    collected = {number for number, _ in rows}
    orphans = [
        number
        for number, line in enumerate(lines, start=1)
        if _ID_RE.match(_split_row(line)[0] if _split_row(line) else "")
        and number not in collected
    ]
    if orphans:
        listed = ", ".join(str(number) for number in orphans)
        problems.append(
            f"line(s) {listed}: lesson row(s) outside the checked table, usually a "
            f"blank line splitting the table; every AL-NNN row must be contiguous "
            f"with the header or it is silently unvalidated"
        )
    for number, cells in rows:
        problems.extend(_check_row(number, cells))
    problems.extend(_check_id_sequence(rows))
    return problems


def _summary(path: Path) -> str:
    """Return a one-line status tally for a log already known to be well formed.

    The tally is the reason to run this script on a green log: the count of
    ``open`` rows is the review backlog, and it is easy to lose track of.

    Args:
        path: The validated log markdown file.

    Returns:
        str: A newline-terminated summary line.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    header_line, _ = _find_log_table(lines)
    rows = _collect_rows(lines, header_line)
    counts: dict[str, int] = {}
    for _, cells in rows:
        status = cells[_COLUMNS.index("Status")]
        counts[status] = counts.get(status, 0) + 1
    tally = ", ".join(f"{status}={counts[status]}" for status in sorted(counts))
    return f"     {len(rows)} lesson(s): {tally}\n"


def main(argv: list[str] | None = None) -> int:
    """Validate the lessons log named on the command line.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        int: 0 when the log is well formed, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Validate the authoring lessons log's structure."
    )
    parser.add_argument(
        "--log",
        default=str(_DEFAULT_LOG),
        help="Path to the lessons log markdown file.",
    )
    args = parser.parse_args(argv)

    path = Path(args.log)
    problems = check_log(path)
    if problems:
        sys.stdout.write(f"FAIL {path}:\n")
        for problem in problems:
            sys.stdout.write(f"  - {problem}\n")
        return 1

    sys.stdout.write(f"ok: {path.name} is well formed\n")
    sys.stdout.write(_summary(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
