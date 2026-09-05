"""The mutmut `also_copy` list must cover every repo-root path the unit suite reads.

mutmut re-runs `tests/unit` from inside the generated `mutants/` tree, under
`-x`. A test that opens a repo-root path which `[tool.mutmut].also_copy` does
not name finds nothing there, raises `FileNotFoundError`, and `-x` aborts the
whole run before a single mutant is scored. That has killed every scheduled
mutation run in this repository's history, each time on a different path:
`fuzz/` (2026-06-28), `tools/`, `.github/` (issue #302, 2026-07-19), and
`.claude/skills/naive-ux-check/` (every run through 2026-08-30). Each fix
added the one missing entry and left the derivation as two grep one-liners in
a `pyproject.toml` comment that nothing runs.

This module runs the derivation. It walks every unit-test module's AST,
resolves module-level constants rooted in `Path(__file__)...parents[N]` (and
aliases of them, e.g. `FRONTEND_DIR = REPO_ROOT / "frontend"`), collects every
maximal `ROOT / "literal" / "literal"` chain the module builds, plus every
repo-root package the module imports (`fuzz`, `tools`, `scripts`), and asserts
that each such path which exists in the real tree is covered by an
`also_copy` entry. The failure message names the test module, the path, and
the entry to add, so the next new root-path dependency is a red test on the
PR that introduces it rather than a red Sunday cron nobody reads.

It also pins the one ordering rule `also_copy` has: mutmut copies a FILE entry
with `shutil.copy2`, which does not create parent directories, so a nested
file entry (`frontend/package.json`) must come after a directory entry that
creates its parent (`frontend/src/`).

Tests deselected under mutmut are exempt: a module-level `pytestmark`, or a
class or function decorated with `pytest.mark.mutation_deselect`, never runs
inside `mutants/`, so what it reads there cannot fail. The derivation is
static and sees only literal segments joined with `/` onto a root-derived
name. A path built with `os.path.join`, an f-string, or a variable segment is
invisible to it; the anti-vacuity assertion below at least proves the walker
is finding the known cases.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path
from typing import Final

import pytest

# mutation_deselect: this contract reads pyproject.toml and the test tree at
# `parents[2]`, which under mutmut is the generated `mutants/` copy. It asserts
# a property of the real repository's configuration and mutates no source
# under `only_mutate`, so the copy is the wrong place to run it (the same
# reasoning as test_check_no_em_dash.py's tree guard). Module-level so the
# walker below, which honours this marker, does not demand `pyproject.toml`
# be copied for its own sake.
pytestmark = pytest.mark.mutation_deselect

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PYPROJECT: Final = REPO_ROOT / "pyproject.toml"
UNIT_TESTS_DIR: Final = REPO_ROOT / "tests" / "unit"
DESELECT_MARK: Final = "mutation_deselect"

# Paths mutmut supplies itself, or that are not repo-root reads at all.
#   src/   -> the mutated source tree mutmut writes.
#   tests/ -> copied by mutmut without an also_copy entry.
#   ..     -> path-traversal probes; a test asserting a guard rejects
#             `ROOT / ".." / "escape.json"` reads nothing there.
_SUPPLIED_BY_MUTMUT: Final = frozenset({"src", "tests", ".."})


def _also_copy() -> list[str]:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["tool"]["mutmut"]["also_copy"]


def _is_root_anchor(node: ast.expr) -> bool:
    """True for `Path(__file__).resolve().parents[N]` and `Path(__file__).parents[N]`."""
    if not isinstance(node, ast.Subscript):
        return False
    value = node.value
    if not (isinstance(value, ast.Attribute) and value.attr == "parents"):
        return False
    inner = value.value
    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
        if inner.func.attr != "resolve":
            return False
        inner = inner.func.value
    return (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "Path"
        and len(inner.args) == 1
        and isinstance(inner.args[0], ast.Name)
        and inner.args[0].id == "__file__"
    )


def _flatten(
    node: ast.expr, aliases: dict[str, tuple[str, ...]]
) -> tuple[str, ...] | None:
    """Flatten a `/`-chain into root-relative segments, or None if not root-rooted.

    Returns:
        The literal segments joined onto a root anchor or a known alias, or
        None when the chain's leftmost operand is neither. A chain containing
        a non-literal segment resolves to its literal prefix only, which is
        the coarsest path that still has to exist under `mutants/`.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _flatten(node.left, aliases)
        if left is None:
            return None
        right = node.right
        if isinstance(right, ast.Constant) and isinstance(right.value, str):
            return (*left, right.value)
        return left
    if _is_root_anchor(node):
        return ()
    if isinstance(node, ast.Name) and node.id in aliases:
        return aliases[node.id]
    return None


def _has_deselect_mark(decorators: list[ast.expr]) -> bool:
    for deco in decorators:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(target, ast.Attribute) and target.attr == DESELECT_MARK:
            return True
    return False


def _module_is_deselected(tree: ast.Module) -> bool:
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets
        ):
            continue
        for node in ast.walk(stmt.value):
            if isinstance(node, ast.Attribute) and node.attr == DESELECT_MARK:
                return True
    return False


def _deselected_node_ids(tree: ast.Module) -> set[int]:
    """Ids of every AST node inside a class or function deselected under mutmut."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ) and _has_deselect_mark(node.decorator_list):
            skipped.update(id(child) for child in ast.walk(node))
    return skipped


def _module_aliases(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    """Module-level names bound to root-anchored `/`-chains, resolved transitively."""
    aliases: dict[str, tuple[str, ...]] = {}
    # Two passes so `B = A / "x"` resolves whichever order A and B appear in.
    for _ in range(2):
        for stmt in tree.body:
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(stmt, ast.Assign):
                targets, value = stmt.targets, stmt.value
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                targets, value = [stmt.target], stmt.value
            if value is None:
                continue
            flat = _flatten(value, aliases)
            if flat is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    aliases[target.id] = flat
    return aliases


def _import_roots(node: ast.AST) -> set[str]:
    """Top-level package names an import statement reaches for."""
    if isinstance(node, ast.Import):
        return {alias.name.split(".", 1)[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return {node.module.split(".", 1)[0]}
    return set()


def _excluded_node_ids(tree: ast.Module) -> set[int]:
    """Nodes the walker must not count as reads.

    Three kinds: anything inside a deselected class or function; the value of
    a module-level assignment (an alias DEFINITION is not a read); and the
    left operand of any `/`, so only the maximal chain is counted rather than
    every prefix of it.
    """
    excluded = _deselected_node_ids(tree)
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) or (
            isinstance(stmt, ast.AnnAssign) and stmt.value is not None
        ):
            excluded.add(id(stmt.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            excluded.add(id(node.left))
    return excluded


def _root_paths_in(module_path: Path) -> set[str]:
    """Every root-relative path a test module builds or imports, maximal chains only.

    An alias definition (`SKILL_DIR = ROOT / ".claude" / ...`) is not itself a
    read; it counts only where the alias is used, either bare or as the root
    of a longer chain, so `FRONTEND_DIR = ROOT / "frontend"` does not demand
    that all of `frontend/` (node_modules included) be copied.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    if _module_is_deselected(tree):
        return set()
    aliases = _module_aliases(tree)
    excluded = _excluded_node_ids(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in excluded:
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            flat = _flatten(node, aliases)
            if flat:
                found.add("/".join(flat))
        elif isinstance(node, ast.Name) and aliases.get(node.id):
            found.add("/".join(aliases[node.id]))
        else:
            found |= _import_roots(node)
    return found


def _first_segment(path: str) -> str:
    return path.split("/", 1)[0]


def _covered(path: str, entries: list[str]) -> bool:
    """True when an also_copy entry guarantees `mutants/<path>` exists.

    Either an entry is this path or a directory containing it (the contents
    are copied), or this path is a DIRECTORY that some entry sits inside (its
    existence is guaranteed because copytree creates every ancestor, even
    though its other contents are not copied). The second case is what lets
    `FRONTEND_DIR = ROOT / "frontend"` be used bare (as a `cwd`, say) without
    demanding all of `frontend/`, node_modules included, be copied; a test
    that needs a specific file under it must build that file's chain, which
    the walker then sees as its own requirement.
    """
    for entry in entries:
        clean = entry.rstrip("/")
        if path == clean or path.startswith(clean + "/"):
            return True
        if (REPO_ROOT / path).is_dir() and clean.startswith(path + "/"):
            return True
    return False


def _required_root_paths() -> dict[str, set[str]]:
    """Map of root-relative path -> the unit-test modules that read it.

    Only paths that exist in the real tree count: a literal that names
    nothing (a fixture name, a probe like `escape.json`, a stdlib import) is
    not a dependency mutmut can break. `..`, `src` and `tests` are excluded
    per `_SUPPLIED_BY_MUTMUT`.
    """
    required: dict[str, set[str]] = {}
    for module_path in sorted(UNIT_TESTS_DIR.glob("test_*.py")):
        for rel in _root_paths_in(module_path):
            if _first_segment(rel) in _SUPPLIED_BY_MUTMUT:
                continue
            if not (REPO_ROOT / rel).exists():
                continue
            required.setdefault(rel, set()).add(module_path.name)
    return required


class TestAlsoCopyCoversEveryRootRead:
    """`also_copy` must name every existing repo-root path the unit suite builds."""

    def test_the_walker_finds_the_known_dependencies(self) -> None:
        """Anti-vacuity: every historical killer is visible to the walker.

        `fuzz` and `tools` arrive via imports, `.github` and the skill
        directory via path chains, `frontend/package.json` via an alias.
        """
        required = _required_root_paths()
        for known in (
            "fuzz",
            "tools",
            ".github",
            ".claude/skills/naive-ux-check",
            "frontend/package.json",
        ):
            assert any(
                path == known or path.startswith(known + "/") for path in required
            ), f"walker no longer sees {known!r}; it found {sorted(required)}"

    def test_every_root_read_is_covered(self) -> None:
        """Each root path a unit test reads is copied into `mutants/`."""
        entries = _also_copy()
        required = _required_root_paths()
        uncovered = {
            path: sorted(readers)
            for path, readers in required.items()
            if not _covered(path, entries)
        }
        listing = "\n".join(
            f"  {path}  <- {', '.join(readers)}"
            for path, readers in sorted(uncovered.items())
        )
        assert not uncovered, (
            "these repo-root paths are read by tests/unit but absent from "
            "[tool.mutmut].also_copy in pyproject.toml, so mutmut's `-x` run "
            "dies on FileNotFoundError before scoring a mutant. Add an entry "
            "for each (a directory entry `dir/` or an exact file), and put a "
            "nested FILE after the directory entry that creates its parent:\n" + listing
        )

    def test_every_entry_exists(self) -> None:
        """A stale entry is skipped silently by mutmut; keep the list honest."""
        missing = [entry for entry in _also_copy() if not (REPO_ROOT / entry).exists()]
        assert not missing, f"also_copy names paths that no longer exist: {missing}"

    def test_nested_file_entries_follow_a_parent_creating_directory_entry(
        self,
    ) -> None:
        """`shutil.copy2` makes no parent dirs, so order matters for nested files."""
        created: set[str] = {""}
        problems: list[str] = []
        for entry in _also_copy():
            clean = entry.rstrip("/")
            parent = str(Path(clean).parent)
            parent = "" if parent == "." else parent
            if (REPO_ROOT / clean).is_dir():
                # copytree creates every ancestor of its destination.
                parts = Path(clean).parts
                created.update("/".join(parts[: i + 1]) for i in range(len(parts)))
            elif parent not in created:
                problems.append(
                    f"{entry!r} needs a preceding directory entry that creates "
                    f"{parent!r}/"
                )
        assert not problems, "\n".join(problems)

    def test_pyproject_comment_points_at_this_test(self) -> None:
        """The comment that once held the derivation now has to name the check."""
        text = PYPROJECT.read_text(encoding="utf-8")
        # Anchored to the line start: a comment elsewhere in the file also
        # mentions `[tool.mutmut]`, and `str.index` would find that first.
        header = re.search(r"^\[tool\.mutmut\]$", text, re.MULTILINE)
        assert header is not None, "pyproject.toml has no [tool.mutmut] table"
        section = text[header.start() :]
        next_table = re.search(r"^\[tool\.", section[1:], re.MULTILINE)
        if next_table is not None:
            section = section[: next_table.start() + 1]
        assert Path(__file__).name in section, (
            "the [tool.mutmut] also_copy comment should name this test as the "
            "enforced derivation, so a reader does not re-run the grep one-liners "
            "by hand"
        )
