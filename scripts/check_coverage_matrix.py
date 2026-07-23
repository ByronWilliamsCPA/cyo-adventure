"""Fail if a frontend test file is not referenced in the coverage matrix.

The frontend test coverage matrix (``docs/testing/coverage-matrix.md``) is
hand-maintained and maps every user journey to the tests that cover it. It
drifts silently as new spec files land without a matching matrix entry: a
2026-07-22 audit found eight E2E specs on disk that no section referenced.

This guard is the structural fix that audit requested. It enumerates every
Playwright E2E spec and every Vitest component/unit test, then fails if any of
their repo-relative paths does not appear verbatim in the matrix. Adding a new
spec without a matrix entry now breaks CI at PR time instead of surfacing in a
later audit.

Run from the repository root::

    python scripts/check_coverage_matrix.py

Exit codes: 0 = every test file is referenced; 1 = one or more orphans.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Repo-root-relative locations. This script lives in ``scripts/``.
REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = REPO_ROOT / "docs" / "testing" / "coverage-matrix.md"

# E2E tiers: every ``*.spec.ts`` under these dirs must be referenced. Support
# and helper modules (``support/*.ts``, ``real-stack.ts``) are not specs and
# are excluded by the ``*.spec.ts`` glob itself.
E2E_DIRS = (
    "frontend/e2e",
    "frontend/e2e-real",
    "frontend/e2e-staging",
    "frontend/e2e-prod",
)

# Component/unit tier: every Vitest test colocated under ``frontend/src``.
# Vitest's ``include`` is ``src/**/*.{test,spec}.{ts,tsx}``
# (frontend/vite.config.ts), so ``.spec`` files under ``src`` are real tests the
# matrix must list too; omitting the ``.spec`` globs left an invisible hole.
COMPONENT_ROOT = "frontend/src"
COMPONENT_GLOBS = ("*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx")

# A documented test-path token: a run of path characters ending in a
# Vitest/Playwright test suffix. Used to pull the exact set of paths the matrix
# references so the drift check matches whole tokens, not loose substrings.
_TEST_PATH_TOKEN = re.compile(r"[\w./-]+\.(?:test|spec)\.tsx?")


def _discover_test_files() -> list[Path]:
    """Discover every frontend test file the matrix is expected to reference.

    Returns:
        Sorted repo-relative paths of every Playwright E2E spec (under
        ``E2E_DIRS``) and every Vitest component/unit test (under
        ``COMPONENT_ROOT``).
    """
    found: set[Path] = set()
    for rel_dir in E2E_DIRS:
        base = REPO_ROOT / rel_dir
        if base.is_dir():
            found.update(p.relative_to(REPO_ROOT) for p in base.rglob("*.spec.ts"))
    component_base = REPO_ROOT / COMPONENT_ROOT
    if component_base.is_dir():
        for pattern in COMPONENT_GLOBS:
            found.update(
                p.relative_to(REPO_ROOT) for p in component_base.rglob(pattern)
            )
    return sorted(found)


def main() -> int:
    if not MATRIX_PATH.is_file():
        print(f"ERROR: coverage matrix not found at {MATRIX_PATH}", file=sys.stderr)
        return 1

    matrix_text = MATRIX_PATH.read_text(encoding="utf-8")
    test_files = _discover_test_files()
    if not test_files:
        print(
            "ERROR: no frontend test files discovered; check the globs.",
            file=sys.stderr,
        )
        return 1

    # Pull the exact path tokens the matrix documents, then require each
    # discovered test to appear as a whole token. A plain ``path in matrix_text``
    # substring scan let a spec named only in a "removed"/"gap" prose note pass,
    # and let a short path satisfy the guard by being a substring of a longer
    # documented one. Paths use forward slashes in the Markdown regardless of
    # host OS, so ``as_posix()`` compares directly.
    referenced = set(_TEST_PATH_TOKEN.findall(matrix_text))
    orphans = [p for p in test_files if p.as_posix() not in referenced]

    if orphans:
        print(
            f"Coverage matrix drift: {len(orphans)} test file(s) are not "
            f"referenced in {MATRIX_PATH.relative_to(REPO_ROOT).as_posix()}:",
            file=sys.stderr,
        )
        for path in orphans:
            print(f"  - {path.as_posix()}", file=sys.stderr)
        print(
            "\nAdd each file to the matrix under the journey it covers (or the "
            "component/utility test index) in this same PR, then re-run.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Coverage matrix OK: all {len(test_files)} frontend test files are referenced."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
