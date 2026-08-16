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
)

_TODAY: Final = date(2026, 8, 16)


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
    def test_window_over_sixty_days_is_rejected(self) -> None:
        """A future date cannot be pushed past the 60-day maximum."""
        entry = parse_entries(_document("2026-12-01", discovered="2026-08-01"))[0]

        problems = check_entry(entry, _TODAY)

        assert len(problems) == 1
        assert "over the 60-day maximum" in problems[0]

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
    """The `.trivyignore` cross-check and its shrink-only baseline."""

    @staticmethod
    def _write(tmp_path: Path, cves: list[str]) -> Path:
        ignorefile = tmp_path / ".trivyignore"
        ignorefile.write_text("# comment\n" + "\n".join(cves) + "\n", encoding="utf-8")
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


class TestRepositoryState:
    """The live repository must satisfy its own gate."""

    @pytest.mark.unit
    def test_shipped_document_is_current(self) -> None:
        """Guards against committing an already-expired entry.

        Pinned to a fixed date rather than today's so the suite does not start
        failing on a calendar boundary; the weekly scheduled workflow is what
        catches real expiry.
        """
        repo_root = Path(__file__).resolve().parents[2]

        problems, _ = check_document(
            repo_root / "docs" / "known-vulnerabilities.md",
            repo_root / ".trivyignore",
            repo_root / "known-vulnerabilities-baseline.toml",
            _TODAY,
            warn_within=14,
        )

        assert problems == []
