"""Tests for the known-vulnerability reassessment gate.

The script this exercises is the only thing enforcing the Release Gate Policy,
so the case that matters most is the one that is hardest to notice: an entry
that quietly passes its reassessment date. These tests pin that behaviour
against fixtures rather than the live document, so they keep asserting the same
thing as real entries come and go.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Final

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_known_vulnerabilities import (
    check_document,
    check_entry,
    check_suppression_coverage,
    load_baseline,
    parse_entries,
    parse_ignore_file,
)

_TODAY: Final = date(2026, 8, 16)
"""Frozen reference date for the synthetic fixtures in this module.

Do not move it. The fixtures below encode exact offsets from this date
(`_document("2026-08-15")` asserting "1 day(s) ago", `_document("2026-08-16")`
asserting that an entry due today still passes), so bumping it silently
invalidates their arithmetic.
"""

_DOCUMENT_VERIFIED: Final = date(2026, 9, 3)
"""Date the shipped `docs/known-vulnerabilities.md` was last verified current.

Deliberately separate from `_TODAY`, which cannot move. A single shared anchor
made the two consumers incompatible: `_TODAY` has to stay frozen for the
fixtures, while the real document keeps acquiring `Discovered` and
`Last Reassessed` dates later than it, and a date later than the reference
reads as "in the future" and fails the gate. That is how reassessing an entry
came to break this suite.

Bump this to the current date whenever an entry is added or reassessed. It is
the "document verified as of" marker, not a wall-clock read: real expiry is
caught by the pre-commit hook and the weekly workflow, which both run the
checker against today.
"""


def _document(due: str, *, discovered: str = "2026-08-01", blocking: str = "No") -> str:
    """Build a minimal document with one entry.

    Args:
        due: Value for the ``Reassessment Due`` field.
        discovered: Value for the ``Discovered`` field.
        blocking: Value for the ``Blocking Release`` field.

    Returns:
        Document text parseable by the checker.
    """
    return f"""## Release Gate Policy

Prose that is not an entry.

## Active Entries

## CVE-2026-00001 | examplepkg | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-00001 |
| **Package** | examplepkg |
| **Discovered** | {discovered} |
| **Reassessment Due** | {due} |
| **Blocking Release** | {blocking} |

### Description

Text.

## Resolved Entries

| CVE | Package | Resolved Date | Resolution |
|-----|---------|---------------|------------|
"""


class TestParsing:
    """Entry extraction."""

    @pytest.mark.unit
    def test_structural_headings_are_not_entries(self) -> None:
        """Policy, Active, Resolved and History sections are skipped."""
        entries = parse_entries(_document("2026-09-01"))

        assert [entry.title for entry in entries] == [
            "CVE-2026-00001 | examplepkg | High"
        ]

    @pytest.mark.unit
    def test_fields_are_extracted(self) -> None:
        """The bolded field table becomes a dict."""
        entry = parse_entries(_document("2026-09-01"))[0]

        assert entry.fields["Package"] == "examplepkg"
        assert entry.fields["Reassessment Due"] == "2026-09-01"

    @pytest.mark.unit
    def test_date_is_read_from_a_field_carrying_prose(self) -> None:
        """Real entries annotate the date; the checker must still read it."""
        entry = parse_entries(_document("2026-09-24 (the 6 open no-fix CVEs)"))[0]

        assert check_entry(entry, date(2026, 9, 25)) != []
        assert check_entry(entry, date(2026, 9, 20)) == []


class TestReleaseGate:
    """The expiry check itself."""

    @pytest.mark.unit
    def test_current_entry_passes(self) -> None:
        """An entry inside its window raises nothing."""
        entry = parse_entries(_document("2026-09-17"))[0]

        assert check_entry(entry, _TODAY) == []

    @pytest.mark.unit
    def test_entry_due_today_still_passes(self) -> None:
        """The gate closes the day AFTER the due date, not on it."""
        entry = parse_entries(_document("2026-08-16"))[0]

        assert check_entry(entry, _TODAY) == []

    @pytest.mark.unit
    def test_expired_entry_closes_the_gate(self) -> None:
        """One day past due is a failure, with the overdue count named."""
        entry = parse_entries(_document("2026-08-15"))[0]

        problems = check_entry(entry, _TODAY)

        assert len(problems) == 1
        assert "RELEASE GATE CLOSED" in problems[0]
        assert "1 day(s) ago" in problems[0]

    @pytest.mark.unit
    def test_expiry_ignores_blocking_release_value(self) -> None:
        """`Blocking Release | No` does not exempt an entry from the deadline.

        This is the 2026-07-29 ruling: the process gate governs where the two
        gates appear to conflict.
        """
        entry = parse_entries(_document("2026-08-01", blocking="No"))[0]

        assert any(
            "RELEASE GATE CLOSED" in problem for problem in check_entry(entry, _TODAY)
        )

    @pytest.mark.unit
    def test_window_over_ninety_days_is_rejected(self) -> None:
        """A future date cannot be pushed past the 90-day maximum."""
        entry = parse_entries(_document("2026-12-01", discovered="2026-08-01"))[0]

        problems = check_entry(entry, _TODAY)

        assert len(problems) == 1
        assert "over the 90-day maximum" in problems[0]

    @pytest.mark.unit
    def test_last_reassessed_moves_the_window_anchor(self) -> None:
        """A reassessed entry measures its window from the reassessment.

        Without this, the first legitimate renewal of any entry would exceed 90
        days from discovery and fail, pushing authors toward editing
        `Discovered` and destroying the record of when the finding appeared.

        The dates are chosen so the anchor is load-bearing: 2026-11-01 is 92
        days after `Discovered` (over the maximum) but 83 days after
        `Last Reassessed` (inside it), so this passes only because the anchor
        moved. The reassessment itself is in the past, which
        `test_future_last_reassessed_is_rejected` requires.
        """
        document = _document("2026-11-01", discovered="2026-08-01").replace(
            "| **Reassessment Due** |",
            "| **Last Reassessed** | 2026-08-10 |\n| **Reassessment Due** |",
        )

        assert check_entry(parse_entries(document)[0], _TODAY) == []

    @pytest.mark.unit
    def test_last_reassessed_before_discovered_is_rejected(self) -> None:
        """An impossible ordering means the fields cannot both be trusted."""
        document = _document("2026-09-17", discovered="2026-08-01").replace(
            "| **Reassessment Due** |",
            "| **Last Reassessed** | 2026-07-01 |\n| **Reassessment Due** |",
        )

        problems = check_entry(parse_entries(document)[0], _TODAY)

        assert any("precedes 'Discovered'" in problem for problem in problems)

    @pytest.mark.unit
    def test_future_last_reassessed_is_rejected(self) -> None:
        """A future anchor would extend the window with no evidence.

        Without this, `Last Reassessed` a year out plus a due date 90 days
        after that passes the window check on a reassessment that has not
        happened. Found by CodeRabbit on PR #725.
        """
        document = _document("2027-08-01", discovered="2026-08-01").replace(
            "| **Reassessment Due** |",
            "| **Last Reassessed** | 2027-06-01 |\n| **Reassessment Due** |",
        )

        problems = check_entry(parse_entries(document)[0], _TODAY)

        assert any("is in the future" in problem for problem in problems)

    @pytest.mark.unit
    def test_future_discovered_is_rejected(self) -> None:
        """`Discovered` anchors the window when no reassessment is recorded."""
        document = _document("2030-02-01", discovered="2030-01-01")

        problems = check_entry(parse_entries(document)[0], _TODAY)

        assert any("'Discovered'" in p and "future" in p for p in problems)

    @pytest.mark.unit
    @pytest.mark.parametrize("value", ["Yes", "Undetermined"])
    def test_unresolved_blocking_values_fail(self, value: str) -> None:
        """A known blocker stops the build rather than sitting in a document."""
        entry = parse_entries(_document("2026-09-17", blocking=value))[0]

        assert any(
            "holds the release" in problem for problem in check_entry(entry, _TODAY)
        )

    @pytest.mark.unit
    def test_missing_required_field_is_reported(self) -> None:
        """An entry that cannot be parsed cannot be enforced."""
        document = _document("2026-09-17").replace("| **Package** | examplepkg |\n", "")

        problems = check_entry(parse_entries(document)[0], _TODAY)

        assert any(
            "missing required field 'Package'" in problem for problem in problems
        )


class TestSuppressionCoverage:
    """The `.trivyignore.yaml` cross-check, date agreement, and the baseline."""

    @staticmethod
    def _write(tmp_path: Path, cves: list[str], *, expires: str = "2026-09-17") -> Path:
        """Write a fixture ignore file in the real `.trivyignore.yaml` shape."""
        ignorefile = tmp_path / ".trivyignore.yaml"
        body = "# comment\nvulnerabilities:\n"
        for cve in cves:
            body += (
                f"  - id: {cve}\n    statement: fixture\n    expired_at: {expires}\n"
            )
        ignorefile.write_text(body, encoding="utf-8")
        return ignorefile

    @pytest.mark.unit
    def test_documented_suppression_passes(self, tmp_path: Path) -> None:
        """A CVE named in an entry needs no baseline row."""
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = self._write(tmp_path, ["CVE-2026-00001"])

        assert check_suppression_coverage(entries, ignorefile, set()) == ([], [])

    @pytest.mark.unit
    def test_undocumented_suppression_fails(self, tmp_path: Path) -> None:
        """A suppression with no written acceptance is an error."""
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = self._write(tmp_path, ["CVE-2026-99999"])

        problems, _ = check_suppression_coverage(entries, ignorefile, set())

        assert len(problems) == 1
        assert "CVE-2026-99999" in problems[0]

    @pytest.mark.unit
    def test_baselined_suppression_warns_but_passes(self, tmp_path: Path) -> None:
        """A grandfathered backlog does not block the build."""
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = self._write(tmp_path, ["CVE-2026-99999"])

        problems, warnings = check_suppression_coverage(
            entries, ignorefile, {"CVE-2026-99999"}
        )

        assert problems == []
        assert len(warnings) == 1
        assert "CVE-2026-99999" in warnings[0]

    @pytest.mark.unit
    def test_stale_baseline_row_fails(self, tmp_path: Path) -> None:
        """The baseline may only shrink, so debt cannot be faked."""
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = self._write(tmp_path, ["CVE-2026-00001"])

        problems, _ = check_suppression_coverage(
            entries, ignorefile, {"CVE-2026-00001"}
        )

        assert len(problems) == 1
        assert "no longer undocumented" in problems[0]

    @pytest.mark.unit
    def test_new_undocumented_fails_even_with_a_baseline(self, tmp_path: Path) -> None:
        """A baseline grandfathers its own rows only, never future ones."""
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = self._write(tmp_path, ["CVE-2026-99999", "CVE-2026-88888"])

        problems, _ = check_suppression_coverage(
            entries, ignorefile, {"CVE-2026-99999"}
        )

        assert len(problems) == 1
        assert "CVE-2026-88888" in problems[0]
        assert "CVE-2026-99999" not in problems[0]

    @pytest.mark.unit
    def test_missing_baseline_file_is_the_desired_end_state(
        self, tmp_path: Path
    ) -> None:
        """An absent baseline means no grandfathered debt, not an error."""
        assert load_baseline(tmp_path / "absent.toml") == set()

    @pytest.mark.unit
    def test_expiry_must_match_the_entry_reassessment_date(
        self, tmp_path: Path
    ) -> None:
        """The enforced date and the written assessment cannot drift apart.

        `expired_at` is what Trivy acts on; `Reassessment Due` is what a human
        reads. A mismatch means the document describes a suppression that is
        not the one in force.
        """
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = self._write(tmp_path, ["CVE-2026-00001"], expires="2026-10-01")

        problems, _ = check_suppression_coverage(entries, ignorefile, set())

        assert len(problems) == 1
        assert "expires 2026-10-01" in problems[0]
        assert "due 2026-09-17" in problems[0]

    @pytest.mark.unit
    def test_missing_expiry_is_reported(self, tmp_path: Path) -> None:
        """A dateless suppression is permanent, which the rule forbids."""
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = tmp_path / ".trivyignore.yaml"
        ignorefile.write_text(
            "vulnerabilities:\n  - id: CVE-2026-00001\n    statement: no date\n",
            encoding="utf-8",
        )

        problems, _ = check_suppression_coverage(entries, ignorefile, set())

        assert any("no parseable `expired_at`" in problem for problem in problems)

    @pytest.mark.unit
    def test_ignore_file_parses_ids_and_dates(self, tmp_path: Path) -> None:
        """The stdlib parser reads the real file shape, comments included."""
        ignorefile = self._write(tmp_path, ["CVE-2026-00001", "CVE-2026-00002"])

        parsed = parse_ignore_file(ignorefile)

        assert parsed == {
            "CVE-2026-00001": date(2026, 9, 17),
            "CVE-2026-00002": date(2026, 9, 17),
        }

    @pytest.mark.unit
    def test_prefix_collision_does_not_count_as_documented(
        self, tmp_path: Path
    ) -> None:
        """A shorter id must not ride on a longer documented one.

        `CVE-2026-0000` is a prefix of the documented `CVE-2026-00001`.
        Substring matching accepted it; exact-id matching must not.
        """
        entries = parse_entries(_document("2026-09-17"))
        ignorefile = self._write(tmp_path, ["CVE-2026-0000"])

        problems, _ = check_suppression_coverage(entries, ignorefile, set())

        assert len(problems) == 1
        assert "CVE-2026-0000" in problems[0]

    @pytest.mark.unit
    def test_prose_mention_does_not_count_as_documented(self, tmp_path: Path) -> None:
        """Only the `CVE ID` field is an acceptance, not a passing reference."""
        document = _document("2026-09-17").replace(
            "Text.", "We also considered CVE-2026-77777 while writing this."
        )
        ignorefile = self._write(tmp_path, ["CVE-2026-77777"])

        problems, _ = check_suppression_coverage(
            parse_entries(document), ignorefile, set()
        )

        assert len(problems) == 1
        assert "CVE-2026-77777" in problems[0]


class TestRepositoryState:
    """The live repository must satisfy its own gate."""

    @pytest.mark.unit
    def test_shipped_document_is_current(self) -> None:
        """Guards against committing an already-expired entry.

        Pinned to `_DOCUMENT_VERIFIED` rather than today's date so the suite
        does not start failing on a calendar boundary; the weekly scheduled
        workflow is what catches real expiry. Bump that constant when adding
        or reassessing an entry, or a newer `Discovered` or `Last Reassessed`
        date reads as being in the future and fails here.
        """
        repo_root = Path(__file__).resolve().parents[2]

        problems, _ = check_document(
            repo_root / "docs" / "known-vulnerabilities.md",
            repo_root / ".trivyignore.yaml",
            repo_root / "known-vulnerabilities-baseline.toml",
            _DOCUMENT_VERIFIED,
            warn_within=14,
        )

        assert problems == []

    @pytest.mark.unit
    def test_repository_carries_no_grandfathered_debt(self) -> None:
        """Every suppression is documented, so no baseline file should exist.

        UW-D31 cleared the eight undocumented suppressions on 2026-08-17 and the
        baseline was deleted with them. Re-introducing it is legitimate but must
        be a visible, deliberate act rather than a quiet way to park a new
        undocumented suppression, so this test fails when the file reappears.
        """
        repo_root = Path(__file__).resolve().parents[2]

        assert not (repo_root / "known-vulnerabilities-baseline.toml").exists()
