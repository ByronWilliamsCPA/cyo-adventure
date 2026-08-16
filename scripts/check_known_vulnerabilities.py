#!/usr/bin/env python3
"""Enforce the Release Gate Policy in ``docs/known-vulnerabilities.md``.

That document has said since 2026-07-29 that an entry past its
``Reassessment Due`` date closes the release gate regardless of its
``Blocking Release`` value, on the reasoning that a dated verdict which has
expired no longer rests on verified evidence. Until now nothing checked it. The
policy was prose, the dates were a Markdown table, and the only thing standing
between an expired acceptance and a shipped release was somebody remembering.
That is precisely the failure the 2026-07-20 to 2026-07-29 incident recorded in
the document's own preamble, where two entries sat overdue and non-blocking for
nine days.

This script makes the process gate real. It reads the entries, and fails when
one has passed its reassessment date. Consistency checks come with it, because
an entry that cannot be parsed is an entry that cannot be enforced.

Checks:

1. Every ``## Active Entries`` section has a field table carrying ``Package``,
   ``Discovered``, ``Reassessment Due`` and ``Blocking Release``.
2. Every ``Discovered`` and ``Reassessment Due`` value contains an ISO date.
3. No entry's reassessment date has passed (the release gate).
4. No entry's reassessment window exceeds the documented 60 days from its
   discovery or last reassessment, so the deadline cannot be reopened by
   editing the date alone.
5. ``Blocking Release`` reads ``Yes``, ``No``, or ``Undetermined``. An entry
   marked ``Yes`` or ``Undetermined`` fails: a known release blocker should
   stop the build rather than sit in a document.
6. Every CVE suppressed in ``.trivyignore`` is covered by an active entry, so a
   suppression cannot outlive its justification.

Check 6 deliberately does NOT require the reverse. Findings suppressed by
``.trivy/ignore-policy.rego`` are accepted at package scope and by design carry
no CVE list; see that file and the "package-scoped acceptance" entry.

Usage::

    uv run python scripts/check_known_vulnerabilities.py
    uv run python scripts/check_known_vulnerabilities.py --today 2026-09-18
    uv run python scripts/check_known_vulnerabilities.py --warn-within 14

Exit codes:
    0 - every entry is current.
    1 - at least one check failed, or a file could not be read.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

_REPO_ROOT: Final = Path(__file__).resolve().parent.parent
_DEFAULT_DOC: Final = _REPO_ROOT / "docs" / "known-vulnerabilities.md"
_DEFAULT_IGNOREFILE: Final = _REPO_ROOT / ".trivyignore"
_DEFAULT_BASELINE: Final = _REPO_ROOT / "known-vulnerabilities-baseline.toml"

# The reassessment window the Release Gate Policy fixes at 60 days.
_MAX_WINDOW_DAYS: Final = 60

# Sections that are not vulnerability entries and carry no field table.
_NON_ENTRY_HEADINGS: Final = frozenset(
    {"Release Gate Policy", "Active Entries", "Resolved Entries", "Review History"}
)

_ACCEPTED_BLOCKING: Final = frozenset({"No"})
_KNOWN_BLOCKING: Final = frozenset({"Yes", "No", "Undetermined"})

_HEADING_RE: Final = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_FIELD_RE: Final = re.compile(
    r"^\|\s*\*\*(?P<name>[^*]+)\*\*\s*\|\s*(?P<value>.*?)\s*\|\s*$"
)
_ISO_DATE_RE: Final = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_CVE_RE: Final = re.compile(r"^(CVE-\d{4}-\d+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Entry:
    """One vulnerability entry parsed from the document.

    Attributes:
        title: The entry's ``##`` heading text.
        line: 1-based line number of that heading.
        fields: The entry's field table, keyed by bolded field name.
        body: The entry's full text, used for CVE coverage matching.
    """

    title: str
    line: int
    fields: dict[str, str]
    body: str


def _parse_iso_date(value: str) -> date | None:
    """Pull the first ISO date out of a field value.

    Field values carry prose alongside the date (an entry may read
    ``2026-09-24 (the 6 open no-fix CVEs)``), so this matches rather than
    parses the whole string.

    Args:
        value: The raw field value.

    Returns:
        The parsed date, or ``None`` when the value carries no ISO date.
    """
    match = _ISO_DATE_RE.search(value)
    if match is None:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def parse_entries(text: str) -> list[Entry]:
    """Split the document into vulnerability entries.

    Args:
        text: Full document text.

    Returns:
        One :class:`Entry` per ``##`` section that is not structural.
    """
    headings = list(_HEADING_RE.finditer(text))
    entries: list[Entry] = []

    for index, heading in enumerate(headings):
        title = heading.group(1).strip()
        if title in _NON_ENTRY_HEADINGS:
            continue

        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end() : end]

        fields: dict[str, str] = {}
        for line in body.splitlines():
            field = _FIELD_RE.match(line)
            if field is not None:
                fields[field.group("name").strip()] = field.group("value").strip()

        entries.append(
            Entry(
                title=title,
                line=text[: heading.start()].count("\n") + 1,
                fields=fields,
                body=body,
            )
        )

    return entries


def check_entry(entry: Entry, today: date) -> list[str]:
    """Validate a single entry against the Release Gate Policy.

    Args:
        entry: The entry to check.
        today: The date to evaluate expiry against.

    Returns:
        Human-readable problems; empty when the entry is current.
    """
    problems: list[str] = [
        f"missing required field '{required}'"
        for required in (
            "Package",
            "Discovered",
            "Reassessment Due",
            "Blocking Release",
        )
        if required not in entry.fields
    ]

    due_raw = entry.fields.get("Reassessment Due", "")
    due = _parse_iso_date(due_raw)
    if "Reassessment Due" in entry.fields and due is None:
        problems.append(f"'Reassessment Due' carries no ISO date: {due_raw!r}")

    discovered_raw = entry.fields.get("Discovered", "")
    discovered = _parse_iso_date(discovered_raw)
    if "Discovered" in entry.fields and discovered is None:
        problems.append(f"'Discovered' carries no ISO date: {discovered_raw!r}")

    if due is not None:
        overdue = (today - due).days
        if overdue > 0:
            problems.append(
                f"RELEASE GATE CLOSED: reassessment was due {due.isoformat()}, "
                f"{overdue} day(s) ago. Per the Release Gate Policy this blocks releases "
                f"whatever 'Blocking Release' says. Re-verify fix status, reachability and "
                f"severity against current sources, record what was checked and on what "
                f"date, then set a new date within {_MAX_WINDOW_DAYS} days. Bumping the date "
                f"without new evidence is not a reassessment."
            )
        elif discovered is not None and (due - discovered).days > _MAX_WINDOW_DAYS:
            problems.append(
                f"reassessment window is {(due - discovered).days} days from the "
                f"'Discovered' date ({discovered.isoformat()}), over the "
                f"{_MAX_WINDOW_DAYS}-day maximum. If this entry has been reassessed, "
                f"update 'Discovered' or record the reassessment date in the entry."
            )

    blocking = entry.fields.get("Blocking Release", "")
    if blocking and blocking not in _KNOWN_BLOCKING:
        problems.append(
            f"'Blocking Release' is {blocking!r}; expected one of {sorted(_KNOWN_BLOCKING)}"
        )
    elif blocking in _KNOWN_BLOCKING and blocking not in _ACCEPTED_BLOCKING:
        problems.append(
            f"'Blocking Release' is {blocking!r}, so this entry holds the release. "
            f"Resolve it or reassess it to 'No' with evidence."
        )

    return problems


def load_baseline(path: Path) -> set[str]:
    """Read the grandfathered undocumented-suppression CVEs.

    Args:
        path: Path to the baseline TOML file.

    Returns:
        The set of CVE IDs exempt from the coverage check. Empty when the file
        is absent, which is the desired end state.
    """
    if not path.is_file():
        return set()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {
        cve for group in data.get("undocumented", []) for cve in group.get("cves", [])
    }


def check_suppression_coverage(
    entries: list[Entry], ignorefile: Path, baseline: set[str]
) -> tuple[list[str], list[str]]:
    """Check every ``.trivyignore`` CVE is justified by an active entry.

    Baselined CVEs are reported as warnings rather than failures, so a bounded
    pre-existing backlog does not block the build while any NEW undocumented
    suppression does. A baselined CVE that has since been documented is an
    error: the backlog may only shrink, and a stale row would let debt be
    faked.

    Args:
        entries: Parsed active entries.
        ignorefile: Path to ``.trivyignore``.
        baseline: Grandfathered CVE IDs from the baseline file.

    Returns:
        A ``(problems, warnings)`` pair.
    """
    if not ignorefile.is_file():
        return ([f"{ignorefile} not found"], [])

    documented = "\n".join(entry.body for entry in entries)
    suppressed = set(_CVE_RE.findall(ignorefile.read_text(encoding="utf-8")))

    uncovered = {cve for cve in suppressed if cve not in documented}
    problems: list[str] = []
    warnings: list[str] = []

    new_uncovered = sorted(uncovered - baseline)
    if new_uncovered:
        problems.append(
            f"{ignorefile.name} suppresses {len(new_uncovered)} CVE(s) with no active "
            f"entry in the document: {', '.join(new_uncovered)}. Every suppression needs "
            f"a written acceptance carrying a reassessment date."
        )

    stale = sorted(baseline - uncovered)
    if stale:
        problems.append(
            f"{_DEFAULT_BASELINE.name} grandfathers {len(stale)} CVE(s) that are no longer "
            f"undocumented: {', '.join(stale)}. Delete their rows; the baseline may only "
            f"shrink."
        )

    still_baselined = sorted(uncovered & baseline)
    if still_baselined:
        warnings.append(
            f"{len(still_baselined)} suppression(s) remain undocumented and grandfathered "
            f"in {_DEFAULT_BASELINE.name}: {', '.join(still_baselined)}"
        )

    return (problems, warnings)


def check_document(
    path: Path, ignorefile: Path, baseline_path: Path, today: date, warn_within: int
) -> tuple[list[str], list[str]]:
    """Validate the whole document.

    Args:
        path: Path to ``known-vulnerabilities.md``.
        ignorefile: Path to ``.trivyignore``.
        baseline_path: Path to the undocumented-suppression baseline.
        today: The date to evaluate expiry against.
        warn_within: Emit a warning for entries due within this many days.

    Returns:
        A ``(problems, warnings)`` pair.
    """
    if not path.is_file():
        return ([f"{path} not found"], [])

    text = path.read_text(encoding="utf-8")
    entries = parse_entries(text)
    if not entries:
        return (
            [f"{path} contains no vulnerability entries; expected at least one"],
            [],
        )

    problems: list[str] = []
    warnings: list[str] = []

    for entry in entries:
        problems.extend(
            f"{path.name}:{entry.line}: {entry.title}: {problem}"
            for problem in check_entry(entry, today)
        )

        due = _parse_iso_date(entry.fields.get("Reassessment Due", ""))
        if due is not None and 0 <= (due - today).days <= warn_within:
            warnings.append(
                f"{path.name}:{entry.line}: {entry.title}: reassessment due "
                f"{due.isoformat()}, in {(due - today).days} day(s)"
            )

    coverage_problems, coverage_warnings = check_suppression_coverage(
        entries, ignorefile, load_baseline(baseline_path)
    )
    problems.extend(coverage_problems)
    warnings.extend(coverage_warnings)
    return (problems, warnings)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        int: 0 when every entry is current, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Enforce reassessment dates in docs/known-vulnerabilities.md."
    )
    parser.add_argument(
        "--doc",
        default=str(_DEFAULT_DOC),
        help="Path to the known-vulnerabilities document.",
    )
    parser.add_argument(
        "--ignorefile",
        default=str(_DEFAULT_IGNOREFILE),
        help="Path to the Trivy ignore file.",
    )
    parser.add_argument(
        "--baseline",
        default=str(_DEFAULT_BASELINE),
        help="Path to the undocumented-suppression baseline.",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="ISO date to evaluate expiry against (defaults to the system date).",
    )
    parser.add_argument(
        "--warn-within",
        type=int,
        default=14,
        help="Warn about entries due within this many days (default: 14).",
    )
    args = parser.parse_args(argv)

    if args.today is None:
        # UTC, not local time: the reassessment dates are policy deadlines, and
        # a gate that closes an hour earlier west of Greenwich than east of it
        # would be a lottery rather than a rule.
        today = datetime.now(tz=UTC).date()
    else:
        parsed = _parse_iso_date(args.today)
        if parsed is None:
            parser.error(f"--today is not an ISO date: {args.today!r}")
        today = parsed

    path = Path(args.doc)
    problems, warnings = check_document(
        path, Path(args.ignorefile), Path(args.baseline), today, args.warn_within
    )

    for warning in warnings:
        sys.stdout.write(f"warning: {warning}\n")

    if problems:
        sys.stdout.write(f"FAIL {path}:\n")
        for problem in problems:
            sys.stdout.write(f"  - {problem}\n")
        return 1

    entry_count = len(parse_entries(path.read_text(encoding="utf-8")))
    sys.stdout.write(
        f"ok: {entry_count} active entr{'y' if entry_count == 1 else 'ies'}, "
        f"none past reassessment as of {today.isoformat()}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
