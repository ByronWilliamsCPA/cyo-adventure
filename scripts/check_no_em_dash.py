#!/usr/bin/env python3
"""Flag em-dash characters (U+2014) in authored files.

Enforces the ``CLAUDE.md`` core directive "Never use em-dash characters (U+2014) in any
output, including docs, comments, commit messages, and ADRs".

This replaces an inline ``bash -c 'git grep --cached -nP "\\xe2\\x80\\x94" -- .'`` hook
that could not fire in the environment it shipped to. Two independent defects, both
measured rather than reasoned about:

* ``git grep -P`` interprets ``\\xNN`` against the **locale**, not as raw bytes. Under
  ``LC_ALL=C`` the pattern matches the three UTF-8 bytes of an em-dash and found 62
  occurrences in this repository. Under ``LC_ALL=C.UTF-8`` PCRE runs in UTF mode, where
  ``\\xe2`` means codepoint U+00E2 (``a`` with circumflex), so the pattern searches for
  that character followed by two C1 control codes and matched **zero**. ``C.utf8`` is the
  only UTF-8 locale installed in this project's containers, so the hook was inert exactly
  where CI runs it. Matching the literal character, as this script does, is
  locale-independent.
* ``git grep --cached -- .`` scans the whole index rather than the staged change, so a
  single pre-existing violation anywhere in the tree would have failed every subsequent
  commit. Taking paths from pre-commit scopes the check to what is actually being added.

#CRITICAL: data-integrity: this script is the ONLY enforcement of the no-em-dash
directive. A silent pass is indistinguishable from a clean tree, which is how 62
occurrences accumulated across 18 files while the hook reported success on every commit.
#VERIFY: ``tests/unit/test_check_no_em_dash.py::TestMain::test_violation_exits_non_zero``
asserts a file containing the character exits 1, and
``TestScanText::test_em_dash_is_reported_with_position`` asserts the match itself, so a
regression that stops matching fails the suite rather than passing quietly.
``TestRepositoryIsClean::test_tracked_authored_files_have_no_em_dashes`` is the standing
tree-wide guard, and it matters more than it looks: this hook runs at ``stages:
[pre-commit]`` only and no CI job invokes pre-commit for it, so that test is the only
enforcement CI has.

Legitimate uses exist: code that counts or asserts the absence of the character needs the
character itself. Mark those lines with ``em-dash-ok`` plus a reason, mirroring this
project's convention of documenting a false positive inline rather than suppressing a
whole file.

Usage::

    python scripts/check_no_em_dash.py docs/some-doc.md
    python scripts/check_no_em_dash.py $(git diff --name-only --cached)

With no paths, the script exits 0: a pre-commit run with no matching staged files must
not fail the commit.

Exit codes:
    0 - no violations found (including when no paths were given).
    1 - at least one violation was found.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

EM_DASH = "—"  # em-dash-ok: this is the character the script exists to detect

# A line carrying this marker is exempt. The marker must be accompanied by a reason in
# the same comment; that is a review expectation, not something this script can check.
#
# #EDGE: data-integrity: the marker is matched per LINE, so `ruff format` can silently
# disable one by splitting a long statement and carrying the trailing comment to a
# different line than the em-dash. Observed on
# `assert "..." not in path.read_text(encoding="utf-8")  # em-dash-ok: ...`.
# #VERIFY: bind the character to a short module-level constant carrying the marker and
# reference the constant, as tests/unit/test_report_retention.py does; a short line has
# nothing to split. The hook catches the mistake either way, so this costs a failed run
# rather than a missed violation.
ALLOW_MARKER = "em-dash-ok"

_REPLACEMENT_HINT = "replace with a comma, semicolon, colon, or a restructured sentence"


@dataclass(frozen=True)
class Violation:
    """One em-dash occurrence.

    Attributes:
        path: File the occurrence was found in.
        line_number: 1-indexed line number.
        column: 1-indexed character column of the em-dash.
        line: Full text of the offending line, stripped of trailing newline.
    """

    path: Path
    line_number: int
    column: int
    line: str

    def render(self) -> str:
        """Render the violation as a single ``file:line:col`` diagnostic.

        Returns:
            str: A one-line diagnostic including the offending line's text.
        """
        return f"{self.path}:{self.line_number}:{self.column}: em-dash (U+2014): {self.line.strip()}"


def scan_text(path: Path, text: str) -> list[Violation]:
    """Collect every non-exempt em-dash occurrence in ``text``.

    Args:
        path: Path reported in the resulting violations.
        text: Full file contents.

    Returns:
        list[Violation]: One entry per em-dash on a line without the allow marker. A line
        containing the marker is skipped in full, however many em-dashes it holds.
    """
    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        start = 0
        while (index := line.find(EM_DASH, start)) != -1:
            violations.append(
                Violation(
                    path=path, line_number=line_number, column=index + 1, line=line
                )
            )
            start = index + 1
    return violations


def scan_path(path: Path) -> list[Violation]:
    """Scan one file, skipping only what genuinely cannot hold a UTF-8 em-dash.

    Two skips are deliberate. A file pre-commit classifies as text can still fail to
    decode (a stray latin-1 byte, a UTF-16 export), and such a file cannot carry a UTF-8
    em-dash; and a path can vanish between staging and this run.

    Every other read failure propagates. Catching bare ``OSError`` here also swallowed
    ``PermissionError`` and ``IsADirectoryError``, which made the hook report success on
    a staged file it never actually inspected. For a check whose whole failure mode is
    "a silent pass is indistinguishable from a clean tree" (see the module docstring),
    an uninspected file must be an error, not a pass.

    Args:
        path: File to read.

    Returns:
        list[Violation]: Violations found, or an empty list when the file is missing or
        not UTF-8 decodable.

    Raises:
        OSError: If the file exists but cannot be read (permissions, a directory, an
            I/O error), since a file this script could not inspect must not be reported
            as clean.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return []
    return scan_text(path, text)


def main(argv: list[str] | None = None) -> int:
    """Scan the given paths and report every em-dash found.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        int: 0 when no violations were found, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="Files to scan.")
    args = parser.parse_args(argv)

    violations: list[Violation] = []
    for path in args.paths:
        violations.extend(scan_path(path))

    if not violations:
        return 0

    for violation in violations:
        print(violation.render())
    count = len(violations)
    noun = "occurrence" if count == 1 else "occurrences"
    print(f"\n{count} em-dash {noun} found; {_REPLACEMENT_HINT}.")
    print(
        f"If the character is load-bearing (counting or asserting it), add "
        f"'{ALLOW_MARKER}' plus a reason to that line."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
