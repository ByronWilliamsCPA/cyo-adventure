#!/usr/bin/env python3
"""Flag ``with pytest.raises(...)`` blocks whose body makes more than one call.

This implements SonarCloud rule ``python:S5778`` ("Only one method invocation is
expected when testing runtime exceptions"), promoted here from a gitignored prototype
(``tmp_cleanup/.tmp-check_s5778_body.py``) into a real, gated hook so its detection logic
lives in version control instead of a machine-local scratch file.

Detection semantics were derived empirically by reproducing SonarCloud's actual list of
flagged and unflagged ``pytest.raises`` sites in this repository, not by re-implementing
the published rule description. Two independent readings of that description (counting
every call anywhere inside the ``with`` statement, and counting every call in the header
plus the body) both disagreed with SonarCloud's real output. The rule that matches every
observed site is narrower than either reading:

* Only calls in the ``with`` block's BODY count. A call inside the ``with`` HEADER, for
  example the ``raises(...)`` call itself or another context manager in the same
  ``with`` statement, never counts, regardless of how many calls it contains.
* A short list of trivially-safe builtins (``str``, ``int``, ``len``, ...) is excluded
  from the body count, because a site combining one of them with the one call under test
  (for example ``str(exc_info.value)`` alongside the call that raises) was not flagged.
* A site is a violation when its body has more than one non-safe call.

Do not "fix" this logic by reading the rule text again: both plausible readings were
checked against this repository's real SonarCloud results and both were wrong. The one
implemented below is the one that matched.

Usage::

    python scripts/check_pytest_raises_scope.py tests/unit/test_example.py
    python scripts/check_pytest_raises_scope.py $(git diff --name-only --cached)

With no paths, the script exits 0: a pre-commit run with no matching staged files must
not fail the commit.

Exit codes:
    0 - no violations found (including when no paths were given).
    1 - at least one violation was found, or a file could not be read or parsed.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# Builtins SonarCloud treats as non-throwing for this rule, verified empirically against
# this repository's real SonarCloud issue list. `Path` and `frozenset` were added after
# the original prototype: including them removes exactly three false positives
# (tests/unit/test_check_work_linkage.py:3291, :3299, and
# tests/unit/test_skeleton_mutation_operators_coverage.py:948) that SonarCloud's own open
# issue list does not contain.
_SAFE_CALLS: frozenset[str] = frozenset(
    {
        "str",
        "int",
        "len",
        "list",
        "dict",
        "tuple",
        "set",
        "bool",
        "float",
        "bytes",
        "bytearray",
        "Path",
        "frozenset",
    }
)


@dataclass(frozen=True)
class Violation:
    """One ``pytest.raises`` block whose body has more than one non-safe call.

    Attributes:
        path: The file the block was found in.
        line: The 1-based line number of the ``with`` statement.
        calls: The unparsed source of each non-safe call found in the body, in the order
            ``ast.walk`` visited them.
    """

    path: Path
    line: int
    calls: tuple[str, ...]


def _is_raises_context(context_expr: ast.expr) -> bool:
    """Report whether a ``with`` item's context expression is a call to ``raises``.

    Matches both ``pytest.raises(...)`` (an attribute access) and a bare ``raises(...)``
    reached via ``from pytest import raises``.

    Args:
        context_expr: The context expression of one ``with`` item.

    Returns:
        bool: True when the expression is a call whose callee is named ``raises``.
    """
    if not isinstance(context_expr, ast.Call):
        return False
    func = context_expr.func
    if isinstance(func, ast.Attribute):
        return func.attr == "raises"
    if isinstance(func, ast.Name):
        return func.id == "raises"
    return False


def _is_safe_call(call: ast.Call) -> bool:
    """Report whether a call is to one of the SAFE builtins excluded from the count.

    Args:
        call: A call node found in a ``pytest.raises`` block's body.

    Returns:
        bool: True when the call's callee is a bare name in ``_SAFE_CALLS``.
    """
    return isinstance(call.func, ast.Name) and call.func.id in _SAFE_CALLS


def _body_calls(node: ast.With | ast.AsyncWith) -> list[ast.Call]:
    """Return every non-safe call reachable from a ``with`` block's body only.

    The block's header, meaning the ``items`` list holding the ``raises(...)`` call and
    any other context managers on the same statement, is never walked here: S5778 counts
    body invocations only, as described in the module docstring.

    Args:
        node: A ``with`` or ``async with`` statement already confirmed to guard a
            ``pytest.raises`` block.

    Returns:
        list[ast.Call]: Every non-safe call found while walking each body statement.
    """
    return [
        call
        for statement in node.body
        for call in ast.walk(statement)
        if isinstance(call, ast.Call) and not _is_safe_call(call)
    ]


def find_violations(path: Path) -> list[Violation]:
    """Find every S5778 violation in one Python file.

    Args:
        path: The Python file to check.

    Returns:
        list[Violation]: One entry per ``pytest.raises`` block whose body has more than
            one non-safe call; empty when the file has no such block.

    Raises:
        OSError: If the file cannot be read.
        UnicodeDecodeError: If the file's bytes cannot be decoded as UTF-8.
        SyntaxError: If the file cannot be parsed as Python.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        if not any(_is_raises_context(item.context_expr) for item in node.items):
            continue
        calls = _body_calls(node)
        if len(calls) > 1:
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    calls=tuple(ast.unparse(call) for call in calls),
                )
            )
    return violations


def _format_violation(violation: Violation) -> str:
    """Render one violation as a human-readable report block.

    Args:
        violation: The violation to render.

    Returns:
        str: A multi-line report: the file, line, body-invocation count, and each
            offending call expression on its own indented line.
    """
    header = (
        f"{violation.path}:{violation.line}: {len(violation.calls)} body invocation(s) "
        f"in this pytest.raises block (S5778 allows exactly one)"
    )
    detail_lines = (f"    - {call}" for call in violation.calls)
    return "\n".join((header, *detail_lines))


def _check_path(path: Path, problems: list[str]) -> list[Violation]:
    """Check one path, recording a read/parse failure as a problem instead of raising.

    Args:
        path: The Python file to check.
        problems: The running problem list; a read, decode, or parse failure is appended
            here as a message rather than propagated.

    Returns:
        list[Violation]: The violations found; empty if the file could not be checked.
    """
    try:
        return find_violations(path)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        problems.append(f"cannot check {path}: {exc}")
        return []


def main(argv: list[str] | None = None) -> int:
    """Check every named file for S5778 violations and report the results.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        int: 0 when no paths were given, or every given path is clean; 1 when at least
            one violation was found or a file could not be read or parsed.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Flag `with pytest.raises(...)` blocks whose body makes more than one "
            "non-safe call (SonarCloud python:S5778)."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Python files to check (typically the staged test files).",
    )
    args = parser.parse_args(argv)

    if not args.paths:
        return 0

    problems: list[str] = []
    violations: list[Violation] = []
    for raw_path in args.paths:
        violations.extend(_check_path(Path(raw_path), problems))

    for violation in violations:
        sys.stdout.write(f"{_format_violation(violation)}\n")
    for problem in problems:
        sys.stdout.write(f"{problem}\n")
    sys.stdout.write(
        f"\nS5778: {len(violations)} violation(s), {len(problems)} unreadable file(s)\n"
    )

    return 1 if violations or problems else 0


if __name__ == "__main__":
    sys.exit(main())
