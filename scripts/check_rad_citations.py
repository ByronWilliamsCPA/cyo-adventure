#!/usr/bin/env python3
"""Check that RAD ``#VERIFY`` citations name tests that actually exist.

This repository mandates RAD assumption markers: a ``#CRITICAL`` /
``#ASSUME`` / ``#EDGE`` comment paired with a ``#VERIFY`` line naming the
test that proves the assumption. A citation that names a test file or test
function which does not exist is worse than no citation at all: the marker
reads as if the assumption is proven, and the named test, not existing,
proves nothing at all.

Closing that gap is *all* this checker does. Resolving is a floor, not a
ceiling: see "Deliberate non-goals" below, in particular the first entry,
before treating a clean run as anything more than "these names refer to
real tests."

What this checker does
----------------------

For Python sources it resolves every citation it can parse:

* ``tests/unit/test_x.py`` or ``tests/unit/x_test.py`` -- the file must
  exist somewhere in the repo. Both are recognised because
  ``pyproject.toml``'s ``python_files`` permits either naming.
* ``tests/unit/test_x.py::test_y`` -- ``test_y`` must be defined in it.
* ``tests/unit/test_x.py::TestC::test_y`` -- both must be defined in it.
* ``test_x.py`` (bare basename) -- resolved by basename.
* ``test_y`` (bare name, no ``.py``) -- must be either a test function
  defined in a test module or ``conftest.py``, or the basename of such a
  module itself. The informal "name the module without the extension"
  style is common here and is deliberately accepted. A bare name is
  resolved repo-wide, so it can match a same-named function in an unrelated
  file; see "Deliberate non-goals" for what that costs.
* ``test_family_{a,b}_suffix_*`` -- brace/glob shorthand for a test family.
  Braces are expanded and every expansion must match at least one real test.

For TypeScript sources it checks **file existence only**. TS citations in
this repo name a colocated ``*.test.tsx`` file plus a *paraphrase* of an
``it()`` title; no TS citation embeds a literal test title verbatim.
Paraphrases are not mechanically checkable, so this checker does not
pretend to check them. Pinning a paraphrase would generate noise and train
people to ignore the hook.

Deliberate non-goals
--------------------

* **This checker proves existence, not discrimination, and that ceiling is
  load-bearing, not a footnote.** A citation that resolves has proven only
  that a test by that name exists in the file it names. It has proven
  nothing about whether that test would fail if the tagged assumption were
  violated or the property it cites were removed. A test that happens to
  pass for an unrelated reason, or that exercises a helper without
  exercising the caller's use of it, resolves here exactly like a test that
  really does discriminate the claim, and this checker cannot and does not
  tell the two apart. A non-discriminating citation passes this gate
  silently, every time. Reaching zero findings means every citation names a
  real test; it does not mean the citations are sound, and reading a clean
  run as "our RAD claims are verified" is a false assurance this checker
  cannot prevent. Whether a cited test actually discriminates the claimed
  property remains a human review judgement, made once at the time the
  citation is written and not re-checked by any automation here.
* A ``#VERIFY`` line that names no test at all (pure prose, a source module,
  a runbook section) yields no citation and is skipped. This checker proves
  citations resolve; it does not police citation style.
* Bare names are resolved repo-wide rather than against the nearest cited
  file, which is the lenient reading and keeps the false-positive rate at
  zero. This is a second, narrower instance of the existence-vs-discrimination
  gap above: a bare name that matches more than one same-named test function
  resolves against all of them without saying so, so a citation can point at
  the wrong one of several look-alikes and still pass. The checker prints a
  non-failing note when this happens (see ``_report``), but the note is
  informational; it does not fail the run.
* ``tests/``, ``supabase/``, and ``frontend/e2e/`` carry ``#VERIFY`` markers
  but are outside this hook's ``files:`` scope in
  ``.pre-commit-config.yaml``, so citations in those trees are never
  checked by this gate at all, clean run or not.

Baseline
--------

An existing backlog of stale citations lives in ``rad-citation-baseline.toml``
at the repo root. Baselined citations are grandfathered: they do not fail the
run. Everything else does, so new and newly-broken citations are blocked from
day one.

The baseline is keyed on ``(citing file, citation text)`` and never on line
numbers, so it does not churn when unrelated lines move.

The baseline can only shrink. A baselined citation that has since been fixed
is reported as an error telling you to delete the row, so a fixed citation
cannot sit in the debt list pretending to be debt. To make that check
complete regardless of how few files a hook run was handed, every file named
in the baseline is scanned on every run, in addition to the files given.

Usage
-----

::

    scripts/check_rad_citations.py path/to/file.py ...   # what pre-commit does
    scripts/check_rad_citations.py --all                 # whole repo
    scripts/check_rad_citations.py --all --write-baseline

Exit codes: ``0`` clean, ``1`` findings, ``2`` usage error. Being handed no
files and no ``--all`` is a usage error, not a pass: a gate that succeeds
vacuously is not a gate. A run that prints only ambiguous-bare-name notes
(see "Deliberate non-goals") and no stale or baseline-drift findings still
exits ``0``: notes are informational and never fail the run.
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import re
import sys
import tokenize
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
BASELINE_PATH: Final = REPO_ROOT / "rad-citation-baseline.toml"

_SKIP_DIRS: Final = frozenset(
    {
        ".git",
        ".hypothesis",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".worktrees",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "out",
        "site",
        "venv",
    }
)

_PY_SUFFIX: Final = ".py"
_TS_SUFFIXES: Final = (".ts", ".tsx")

# This checker's own test fixtures deliberately cite tests that do not exist,
# because that is the condition under test. Scanning them would report the
# fixtures as debt forever, exactly like a secret scanner flagging its own
# sample keys. The exclusion is a fixed list of one rather than a general
# opt-out directive, so no other file can quietly join it.
_FIXTURE_FILES: Final = frozenset({"tests/unit/test_check_rad_citations.py"})

# A marker line opens a new RAD block; a VERIFY line opens a citation block.
# The leading "#" is optional because docstring-embedded markers carry no
# comment character at all (see core/observability.py).
_MARKER_RE: Final = re.compile(r"#?\b(?:VERIFY|CRITICAL|ASSUME|EDGE)\b\s*[:(]")
_VERIFY_RE: Final = re.compile(r"#?\bVERIFY\b\s*[:(]")

# Docstring prose resumes at a Google-style section heading; stop there so a
# VERIFY block never swallows an Args: list.
_SECTION_RE: Final = re.compile(
    r"^(?:Args|Arguments|Attributes|Example|Examples|Note|Notes|Raises|Returns"
    r"|Todo|Yields)\s*:\s*$"
)

_STR_OPEN_RE: Final = re.compile(r"^[rRbBuUfF]*(\"\"\"|'''|\"|')")
_COMMENT_PREFIX_RE: Final = re.compile(r"^#+\s?")
_TS_COMMENT_PREFIX_RE: Final = re.compile(r"^(?:/\*\*|/\*|\*/|\*|//)\s?")

# A cited name is identifier characters plus glob "*", with "{a,b}" brace
# groups as an inseparable unit. The comma lives only inside a brace group,
# so a comma-separated citation list does not glue the separator onto a name.
_NAME_BODY: Final = r"(?:[A-Za-z0-9_*]|\{[^{}]*\})"

_PY_CITATION_RE: Final = re.compile(
    # A path ending in a test module, with or without leading directories.
    # pyproject.toml's python_files permits "test_*.py" and "*_test.py"
    # both, so both module-naming conventions are recognised as a path.
    r"(?P<path>(?:[A-Za-z0-9_.\-]+/)*"
    r"(?:test_[A-Za-z0-9_]+|[A-Za-z0-9_]+_test)\.py)"
    # "::name", optionally with a pytest parametrisation suffix.
    rf"|::(?P<chain>{_NAME_BODY}+)(?:\[[^\]]*\])?"
    # A bare test name not preceded by a path separator or another name char.
    rf"|(?<![A-Za-z0-9_./:])(?P<bare>test_{_NAME_BODY}*[A-Za-z0-9_}}*])"
)

# The basename may itself carry dots (ReaderPage.badgeToast.test.tsx), so the
# leading run must admit them and let the anchored ".test.tsx" suffix decide
# where the name starts.
_TS_CITATION_RE: Final = re.compile(
    r"(?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_.\-]+\.(?:test|spec)\.tsx?"
)

_DEF_RE: Final = re.compile(
    r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)", re.MULTILINE
)
_CLASS_RE: Final = re.compile(r"^[ \t]*class[ \t]+([A-Za-z_]\w*)", re.MULTILINE)

# Joining a wrapped citation. A long test name or path can wrap with the
# break on either side of the underscore, so both halves of the rule matter:
# a line that ENDS on one of these, or a next line that STARTS with "_",
# continues the same token rather than starting a new word. Prose
# effectively never ends a line on "_", "/" or "::", nor starts one with "_".
_TIGHT_JOIN_SUFFIXES: Final = ("_", "/", "::")

_FIXED_ROW_REASON: Final = (
    "baselined citation is no longer stale; delete this row from "
    "rad-citation-baseline.toml"
)
_GONE_FILE_REASON: Final = (
    "baselined file no longer exists; delete its rows from rad-citation-baseline.toml"
)


@dataclass(frozen=True)
class Finding:
    """One thing worth reporting about a citation.

    Attributes:
        path: Repo-relative posix path of the file that carries the citation,
            or of the baselined file for baseline-drift findings.
        line: 1-based line of the ``#VERIFY`` marker, or 0 when the finding is
            about the baseline rather than a specific line.
        citation: The stable baseline key for this citation.
        reason: Human-readable explanation.
        kind: ``"stale"`` for an unresolvable citation and ``"baseline"`` for
            a baseline row that is no longer justified; both fail the run.
            ``"note"`` is informational only and never fails the run: it
            flags a bare name that resolved but matched more than one
            same-named test function, which the "Deliberate non-goals"
            section in this module's docstring documents as a real gap this
            checker cannot close by failing the build, only by saying so.
    """

    path: str
    line: int
    citation: str
    reason: str
    kind: str = "stale"


@dataclass(frozen=True)
class Block:
    """A joined ``#VERIFY`` comment or docstring block.

    Attributes:
        line: 1-based line of the ``#VERIFY`` marker that opened the block.
        text: The block's lines joined into one string.
    """

    line: int
    text: str


@dataclass
class RepoIndex:
    """Everything the checker knows about the repo's real tests.

    Attributes:
        py_test_paths: Repo-relative posix paths of every ``test_*.py``.
        py_defs_by_path: Function and class names defined in each test module
            (and in each ``conftest.py``).
        py_test_names: Every ``test_``-prefixed function and ``Test``-prefixed
            class name defined anywhere in the repo.
        py_test_modules: Every ``test_*.py`` basename with the suffix removed.
        ts_test_paths: Repo-relative posix paths of every TS/TSX test file.
    """

    py_test_paths: set[str] = field(default_factory=set)
    py_defs_by_path: dict[str, set[str]] = field(default_factory=dict)
    py_test_names: set[str] = field(default_factory=set)
    py_test_modules: set[str] = field(default_factory=set)
    ts_test_paths: set[str] = field(default_factory=set)


def _iter_repo_files(root: Path) -> list[Path]:
    """List every source file in the repo, skipping build and cache trees.

    Args:
        root: Repository root.

    Returns:
        Paths to every ``.py``, ``.ts`` and ``.tsx`` file worth reading.
    """
    found: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS:
                    stack.append(entry)
            elif entry.suffix == _PY_SUFFIX or entry.suffix in _TS_SUFFIXES:
                found.append(entry)
    return found


def _read(path: Path) -> str:
    """Read a source file, tolerating undecodable bytes.

    Args:
        path: File to read.

    Returns:
        The file's text.
    """
    return path.read_text(encoding="utf-8", errors="replace")


def build_index(root: Path, files: list[Path] | None = None) -> RepoIndex:
    """Index the repo's real test files, test functions and test classes.

    Args:
        root: Repository root, used to make paths relative.
        files: Pre-collected file list, or ``None`` to walk the tree.

    Returns:
        A populated :class:`RepoIndex`.
    """
    index = RepoIndex()
    for path in files if files is not None else _iter_repo_files(root):
        rel = path.relative_to(root).as_posix()
        name = path.name
        if path.suffix in _TS_SUFFIXES:
            if re.search(r"\.(?:test|spec)\.tsx?$", name):
                index.ts_test_paths.add(rel)
            continue
        if path.suffix != _PY_SUFFIX:
            continue
        # pyproject.toml's python_files permits both "test_*.py" and
        # "*_test.py"; a file named the second way is a real test module too.
        is_test_module = name.startswith("test_") or name.endswith("_test.py")
        source = _read(path)
        defs = set(_DEF_RE.findall(source)) | set(_CLASS_RE.findall(source))
        if is_test_module or name == "conftest.py":
            index.py_defs_by_path[rel] = defs
            # Restricted to test modules and conftest.py on purpose: a
            # test_-prefixed function defined in src/ must not satisfy a bare
            # citation, or a rename in src/ could silently mask drift in the
            # actual test suite. See "Deliberate non-goals" in the module
            # docstring.
            index.py_test_names.update(
                d for d in defs if d.startswith(("test_", "Test"))
            )
        if is_test_module:
            index.py_test_paths.add(rel)
            index.py_test_modules.add(name[: -len(_PY_SUFFIX)])
    return index


def _strip_string_quotes(token: str) -> str:
    """Remove the surrounding quotes from a Python string token.

    Args:
        token: The raw token text, prefixes and quotes included.

    Returns:
        The string's body, with line structure preserved.
    """
    match = _STR_OPEN_RE.match(token)
    if match is None:
        return token
    quote = match.group(1)
    return token[match.end() :].removesuffix(quote)


def _join_block(payloads: list[str]) -> str:
    """Join a block's lines, reattaching tokens that were wrapped mid-name.

    A comment line that ends in ``_``, ``/`` or ``::`` is continued by the
    next line rather than followed by it: the repo wraps long test names and
    long paths that way. Everything else joins with a space.

    Args:
        payloads: The block's lines, comment prefixes already removed.

    Returns:
        One joined string.
    """
    joined = ""
    for position, payload in enumerate(payloads):
        if position == 0:
            joined = payload
            continue
        head = payload[:1]
        opens_token = bool(head) and (head.isalnum() or head == "_")
        tight = (joined.endswith(_TIGHT_JOIN_SUFFIXES) and opens_token) or (
            head == "_" and joined[-1:].isalnum()
        )
        joined = joined + payload if tight else f"{joined} {payload}"
    # "path.py::" followed by a wrapped name still needs the space closed up
    # when the wrap fell after a comma rather than after the "::".
    return re.sub(r"::\s+", "::", joined)


def _blocks_from_groups(groups: list[list[tuple[int, str]]]) -> list[Block]:
    """Carve ``#VERIFY`` blocks out of contiguous comment/docstring runs.

    Args:
        groups: Runs of ``(line number, payload)`` pairs.

    Returns:
        One :class:`Block` per ``#VERIFY`` marker found.
    """
    blocks: list[Block] = []
    for group in groups:
        for position, (line, payload) in enumerate(group):
            if _VERIFY_RE.search(payload) is None:
                continue
            collected = [payload]
            for _, following in group[position + 1 :]:
                if not following:
                    break
                if _MARKER_RE.search(following) is not None:
                    break
                if _SECTION_RE.match(following) is not None:
                    break
                collected.append(following)
            blocks.append(Block(line=line, text=_join_block(collected)))
    return blocks


def extract_py_blocks(source: str) -> list[Block]:
    """Extract ``#VERIFY`` blocks from Python comments and docstrings.

    Args:
        source: Python source text.

    Returns:
        Every ``#VERIFY`` block in the file.
    """
    groups: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    previous_line = -10
    previous_column = -1
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return _fallback_blocks(source, _COMMENT_PREFIX_RE)
    for token in tokens:
        if token.type == tokenize.COMMENT:
            row, column = token.start
            payload = _COMMENT_PREFIX_RE.sub("", token.string).strip()
            if row == previous_line + 1 and column == previous_column:
                current.append((row, payload))
            else:
                if current:
                    groups.append(current)
                current = [(row, payload)]
            previous_line, previous_column = row, column
        elif token.type == tokenize.STRING and "#VERIFY" in token.string:
            if current:
                groups.append(current)
                current = []
            previous_line, previous_column = -10, -1
            start = token.start[0]
            body = _strip_string_quotes(token.string)
            # Docstring RAD blocks in this repo are written as comment-styled
            # prose inside the string ("#  #EDGE: ..."), so the same prefix
            # stripping a real comment gets has to apply here too. Without it
            # a wrapped name keeps a "#" between its halves and never rejoins.
            groups.append(
                [
                    (start + offset, _COMMENT_PREFIX_RE.sub("", text.strip()).strip())
                    for offset, text in enumerate(body.splitlines())
                ]
            )
    if current:
        groups.append(current)
    return _blocks_from_groups(groups)


def _fallback_blocks(source: str, prefix_re: re.Pattern[str]) -> list[Block]:
    """Extract blocks line by line when a real tokenizer is unavailable.

    Args:
        source: Source text.
        prefix_re: Pattern matching this language's comment prefix.

    Returns:
        Every ``#VERIFY`` block found in contiguous comment runs.
    """
    groups: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if prefix_re.match(stripped) is not None:
            current.append((number, prefix_re.sub("", stripped).strip()))
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return _blocks_from_groups(groups)


def extract_ts_blocks(source: str) -> list[Block]:
    """Extract ``#VERIFY`` blocks from TypeScript ``//`` and JSDoc comments.

    Args:
        source: TypeScript source text.

    Returns:
        Every ``#VERIFY`` block in the file.
    """
    return _fallback_blocks(source, _TS_COMMENT_PREFIX_RE)


def expand_braces(pattern: str) -> list[str]:
    """Expand ``{a,b}`` shorthand into one string per alternative.

    Args:
        pattern: A citation possibly containing brace groups.

    Returns:
        Every expansion, or the input unchanged when there are no braces.
    """
    match = re.search(r"\{([^{}]*)\}", pattern)
    if match is None:
        return [pattern]
    expanded: list[str] = []
    for option in match.group(1).split(","):
        rest = pattern[: match.start()] + option.strip() + pattern[match.end() :]
        expanded.extend(expand_braces(rest))
    return expanded


def _is_pattern(name: str) -> bool:
    """Report whether a citation uses glob or brace shorthand.

    Args:
        name: A cited test name.

    Returns:
        ``True`` when the name must be matched rather than compared.
    """
    return any(character in name for character in "*{}")


def _matches(name: str, universe: set[str]) -> bool:
    """Resolve a cited name, literally or as a glob, against real names.

    Args:
        name: A cited test name, possibly with braces or ``*``.
        universe: Every real name the citation is allowed to resolve to.

    Returns:
        ``True`` when the citation resolves.
    """
    if not _is_pattern(name):
        return name in universe
    return all(
        any(fnmatch.fnmatchcase(real, expansion) for real in universe)
        for expansion in expand_braces(name)
    )


def _normalise_path(path: str) -> str:
    """Strip a leading ``./`` or ``/`` from a cited path.

    Args:
        path: A cited path.

    Returns:
        The path without a leading current-directory or root marker.
    """
    return re.sub(r"^\.?/+", "", path)


def _resolve_py_path(index: RepoIndex, path: str) -> list[str]:
    """Find the real test modules a cited Python path could mean.

    Args:
        index: The repo index.
        path: A normalised cited path, full or bare basename.

    Returns:
        Matching repo-relative paths, empty when the citation is stale.
    """
    if path in index.py_test_paths:
        return [path]
    suffix = "/" + path
    return sorted(p for p in index.py_test_paths if p.endswith(suffix))


def _resolve_ts_path(index: RepoIndex, path: str) -> list[str]:
    """Find the real TS test files a cited path could mean.

    Args:
        index: The repo index.
        path: A normalised cited path, full or bare basename.

    Returns:
        Matching repo-relative paths, empty when the citation is stale.
    """
    if path in index.ts_test_paths:
        return [path]
    suffix = "/" + path
    return sorted(p for p in index.ts_test_paths if p.endswith(suffix))


def _check_bare_name(index: RepoIndex, name: str) -> bool:
    """Resolve a bare cited name as either a test function or a test module.

    Args:
        index: The repo index.
        name: A cited name with no path and no ``.py`` suffix.

    Returns:
        ``True`` when the citation resolves.
    """
    return _matches(name, index.py_test_names | index.py_test_modules)


def _bare_ambiguity_note(
    rel: str, line: int, index: RepoIndex, name: str
) -> Finding | None:
    """Flag a resolved bare name that matches more than one test function.

    A bare citation is resolved repo-wide (see "Deliberate non-goals" in the
    module docstring), so a same-named test function in an unrelated file
    resolves it exactly as well as the one the author meant. This cannot be
    turned into a failure without breaking every legitimately shared helper
    name, so it is reported as a non-failing note instead: visible, but not
    blocking.

    Args:
        rel: Repo-relative path of the citing file.
        line: 1-based line of the ``#VERIFY`` marker.
        index: The repo index.
        name: A cited bare name that has already resolved via
            :func:`_check_bare_name`.

    Returns:
        A ``"note"``-kind :class:`Finding`, or ``None`` when ``name`` is a
        glob/brace pattern (matching several tests is the point there) or
        matched at most one function definition.
    """
    if _is_pattern(name):
        return None
    definers = sorted(p for p, defs in index.py_defs_by_path.items() if name in defs)
    if len(definers) <= 1:
        return None
    return Finding(
        path=rel,
        line=line,
        citation=name,
        reason=(
            f"resolves against {len(definers)} same-named test functions"
            f" ({', '.join(definers)}); a bare citation cannot say which one"
            " actually covers this assumption"
        ),
        kind="note",
    )


def _scan_py_block(index: RepoIndex, rel: str, block: Block) -> list[Finding]:
    """Resolve every citation in one Python ``#VERIFY`` block.

    Args:
        index: The repo index.
        rel: Repo-relative path of the citing file.
        block: The joined block.

    Returns:
        A finding for each citation that does not resolve.
    """
    findings: list[Finding] = []
    current_path: str | None = None
    current_files: list[str] = []
    for match in _PY_CITATION_RE.finditer(block.text):
        raw_path = match.group("path")
        chain = match.group("chain")
        bare = match.group("bare")
        if raw_path is not None:
            current_path = _normalise_path(raw_path)
            current_files = _resolve_py_path(index, current_path)
            if not current_files:
                findings.append(
                    Finding(
                        path=rel,
                        line=block.line,
                        citation=current_path,
                        reason="no test file by that path exists in the repo",
                    )
                )
        elif chain is not None:
            if not chain.startswith(("test_", "Test")):
                continue
            if current_path is None:
                if not _check_bare_name(index, chain):
                    findings.append(
                        Finding(
                            path=rel,
                            line=block.line,
                            citation=chain,
                            reason="no test function or test module by that name",
                        )
                    )
                else:
                    note = _bare_ambiguity_note(rel, block.line, index, chain)
                    if note is not None:
                        findings.append(note)
                continue
            if not current_files:
                continue  # already reported the missing file; do not double-count
            universe: set[str] = set()
            for candidate in current_files:
                universe |= index.py_defs_by_path.get(candidate, set())
            if not _matches(chain, universe):
                findings.append(
                    Finding(
                        path=rel,
                        line=block.line,
                        citation=f"{current_path}::{chain}",
                        reason=f"{current_path} defines no such test",
                    )
                )
        elif bare is not None:
            if not _check_bare_name(index, bare):
                findings.append(
                    Finding(
                        path=rel,
                        line=block.line,
                        citation=bare,
                        reason="no test function or test module by that name",
                    )
                )
            else:
                note = _bare_ambiguity_note(rel, block.line, index, bare)
                if note is not None:
                    findings.append(note)
    return findings


def _scan_ts_block(index: RepoIndex, rel: str, block: Block) -> list[Finding]:
    """Resolve every cited TypeScript test file in one block.

    File existence only: TS citations paraphrase ``it()`` titles rather than
    quoting them, and a paraphrase cannot be checked mechanically.

    Args:
        index: The repo index.
        rel: Repo-relative path of the citing file.
        block: The joined block.

    Returns:
        A finding for each cited file that does not exist.
    """
    findings: list[Finding] = []
    for match in _TS_CITATION_RE.finditer(block.text):
        cited = _normalise_path(match.group(0))
        if not _resolve_ts_path(index, cited):
            findings.append(
                Finding(
                    path=rel,
                    line=block.line,
                    citation=cited,
                    reason="no test file by that name exists under frontend/",
                )
            )
    return findings


def scan_file(index: RepoIndex, root: Path, path: Path) -> list[Finding]:
    """Find every stale citation in one file.

    Args:
        index: The repo index.
        root: Repository root.
        path: File to scan.

    Returns:
        Findings, in source order.
    """
    rel = path.relative_to(root).as_posix()
    if rel in _FIXTURE_FILES:
        return []
    source = _read(path)
    if "#VERIFY" not in source:
        return []
    if path.suffix == _PY_SUFFIX:
        blocks = extract_py_blocks(source)
        scan = _scan_py_block
    elif path.suffix in _TS_SUFFIXES:
        blocks = extract_ts_blocks(source)
        scan = _scan_ts_block
    else:
        return []
    findings: list[Finding] = []
    for block in blocks:
        findings.extend(scan(index, rel, block))
    return findings


def load_baseline(path: Path) -> dict[str, dict[str, list[str]]]:
    """Read the grandfathered-citation baseline.

    Args:
        path: Baseline file path.

    Returns:
        ``{"python": {file: [citation, ...]}, "typescript": {...}}``. Missing
        sections come back empty, and a missing file yields empty sections.

    Raises:
        ValueError: If the file exists but is not shaped as expected.
    """
    sections: dict[str, dict[str, list[str]]] = {"python": {}, "typescript": {}}
    if not path.exists():
        return sections
    with path.open("rb") as handle:
        # tomllib always yields a table at the top level, so the only shapes
        # worth validating are the ones below it.
        document = cast("dict[str, object]", tomllib.load(handle))
    for section, collected in sections.items():
        block = document.get(section)
        if block is None:
            continue
        if not isinstance(block, dict):
            msg = f"baseline section [{section}] must be a table"
            raise ValueError(msg)
        for key, value in cast("dict[object, object]", block).items():
            if not isinstance(key, str) or not isinstance(value, list):
                msg = f"baseline entry [{section}].{key!r} must map to a list"
                raise ValueError(msg)
            citations: list[str] = []
            for item in cast("list[object]", value):
                if not isinstance(item, str):
                    msg = f"baseline entry [{section}].{key!r} must hold strings"
                    raise ValueError(msg)
                citations.append(item)
            collected[key] = citations
    return sections


def render_baseline(findings: list[Finding]) -> str:
    """Serialise findings as a baseline file.

    Args:
        findings: Every stale citation to grandfather.

    Returns:
        The complete TOML document.
    """
    grouped: dict[str, dict[str, set[str]]] = {"python": {}, "typescript": {}}
    for finding in findings:
        section = "python" if finding.path.endswith(_PY_SUFFIX) else "typescript"
        grouped[section].setdefault(finding.path, set()).add(finding.citation)
    total = sum(len(c) for s in grouped.values() for c in s.values())
    lines = [
        "# RAD #VERIFY citation baseline (debt item D-2).",
        "#",
        "# Every row is a citation that names a test which does not exist.",
        "# scripts/check_rad_citations.py grandfathers these and fails on any",
        "# stale citation not listed here, so the backlog is bounded and new",
        "# breakage is blocked from day one.",
        "#",
        "# This list may only shrink. Fixing a citation and leaving its row",
        "# here is itself an error: the checker reports rows that are no",
        "# longer stale so debt cannot be faked. Delete the row with the fix.",
        "#",
        "# Rows are keyed on (file, citation text), never on line numbers, so",
        "# unrelated edits above a citation do not churn this file.",
        "#",
        "# WHAT REACHING ZERO ROWS DOES NOT MEAN, for the team fixing this list:",
        "# the checker proves a citation names a test that EXISTS. It does not and",
        "# cannot prove that test would FAIL if the property it is cited for were",
        '# removed. Fixing every row here gets you to "every #VERIFY name refers to',
        '# a real test," not to "every RAD claim is actually proven." Nine',
        "# citations shipped during this same workstream name a real, passing test",
        "# that proves nothing about the claim above it; the checker passed all",
        "# nine, and it will pass the next one too, silently, because that is a",
        "# human review judgement this file's automation cannot make. See",
        '# "Deliberate non-goals" in scripts/check_rad_citations.py\'s module',
        "# docstring before treating an empty version of this file as done.",
        "#",
        "# This baseline also only covers what the check-rad-citations pre-commit",
        "# hook scans: src/, scripts/, frontend/src/, and this file. tests/,",
        "# supabase/, and frontend/e2e/ carry #VERIFY markers of their own and are",
        "# not scanned by this hook at all, so a citation going stale in any of",
        "# those trees produces no row here and no failure anywhere.",
        "#",
        (
            f"# Entries: {total}"
            f" ({sum(len(c) for c in grouped['python'].values())} python,"
            f" {sum(len(c) for c in grouped['typescript'].values())} typescript)"
        ),
        "",
    ]
    for section in ("python", "typescript"):
        lines.append(f"[{section}]")
        for file_path in sorted(grouped[section]):
            citations = sorted(grouped[section][file_path])
            lines.append(f"{json.dumps(file_path)} = [")
            lines.extend(f"    {json.dumps(citation)}," for citation in citations)
            lines.append("]")
        lines.append("")
    return "\n".join(lines)


def _baseline_files(baseline: dict[str, dict[str, list[str]]]) -> set[str]:
    """List every file the baseline mentions.

    Args:
        baseline: A loaded baseline.

    Returns:
        Repo-relative paths.
    """
    return {path for section in baseline.values() for path in section}


def _baseline_for(baseline: dict[str, dict[str, list[str]]], rel: str) -> set[str]:
    """Look up the grandfathered citations for one file.

    Args:
        baseline: A loaded baseline.
        rel: Repo-relative path of the citing file.

    Returns:
        The citations baselined for that file.
    """
    section = "python" if rel.endswith(_PY_SUFFIX) else "typescript"
    return set(baseline[section].get(rel, []))


def run(
    root: Path,
    targets: list[Path],
    baseline: dict[str, dict[str, list[str]]],
    index: RepoIndex,
) -> list[Finding]:
    """Scan the given files and reconcile the results with the baseline.

    Every file named in the baseline is scanned as well as the files given,
    so the "no longer stale" check is complete even on a two-file hook run.

    Args:
        root: Repository root.
        targets: Files the caller asked about.
        baseline: The loaded baseline.
        index: The repo index.

    Returns:
        Everything worth reporting: ``"stale"`` and ``"baseline"`` findings
        the caller should fail on, plus informational ``"note"`` findings
        that should be printed but never fail the run.
    """
    scanned: dict[str, list[Finding]] = {}
    ordered: list[Path] = list(targets)
    seen = {p.resolve() for p in targets}
    stale_baseline_files: list[str] = []
    for rel in sorted(_baseline_files(baseline)):
        candidate = root / rel
        if not candidate.exists():
            stale_baseline_files.append(rel)
            continue
        if candidate.resolve() not in seen:
            ordered.append(candidate)
            seen.add(candidate.resolve())

    for path in ordered:
        rel = path.relative_to(root).as_posix()
        scanned[rel] = scan_file(index, root, path)

    findings: list[Finding] = []
    for rel in sorted(scanned):
        grandfathered = _baseline_for(baseline, rel)
        actual = {f.citation for f in scanned[rel]}
        findings.extend(f for f in scanned[rel] if f.citation not in grandfathered)
        findings.extend(
            Finding(
                path=rel,
                line=0,
                citation=gone,
                reason=_FIXED_ROW_REASON,
                kind="baseline",
            )
            for gone in sorted(grandfathered - actual)
        )
    findings.extend(
        Finding(
            path=rel, line=0, citation="*", reason=_GONE_FILE_REASON, kind="baseline"
        )
        for rel in stale_baseline_files
    )
    return findings


def _collect_targets(root: Path, paths: list[str], scan_all: bool) -> list[Path]:
    """Resolve CLI arguments into the set of files to scan.

    Args:
        root: Repository root.
        paths: Paths given on the command line.
        scan_all: Whether ``--all`` was passed.

    Returns:
        Existing Python and TypeScript files inside the repo.
    """
    if scan_all:
        return _iter_repo_files(root)
    targets: list[Path] = []
    for raw in paths:
        candidate = Path(raw)
        resolved = candidate if candidate.is_absolute() else root / candidate
        if not resolved.is_file():
            continue
        if resolved.suffix != _PY_SUFFIX and resolved.suffix not in _TS_SUFFIXES:
            continue
        targets.append(resolved)
    return targets


def _report(findings: list[Finding]) -> None:
    """Print findings and the remediation hint.

    Args:
        findings: What to print. ``"note"``-kind findings are informational:
            they are printed but never fail the run (see :func:`main`).
    """
    stale = [f for f in findings if f.kind == "stale"]
    drift = [f for f in findings if f.kind == "baseline"]
    notes = [f for f in findings if f.kind == "note"]
    for finding in stale:
        print(f"{finding.path}:{finding.line}: {finding.citation}: {finding.reason}")
    for finding in drift:
        print(f"{finding.path}: {finding.citation}: {finding.reason}")
    for finding in notes:
        print(
            f"{finding.path}:{finding.line}: note: {finding.citation}: {finding.reason}"
        )
    print()
    if stale:
        print(
            f"{len(stale)} stale RAD #VERIFY citation(s). A stale citation"
            " reads as proof of the assumption above it while the named test,"
            " not existing, proves nothing at all: fix the citation to name"
            " the real test, or delete it. Note that a citation which"
            " resolves is not thereby proven either; see 'Deliberate"
            " non-goals' in this script's module docstring for the ceiling"
            " this check does not raise."
        )
    if drift:
        print(
            f"{len(drift)} baseline row(s) no longer describe real debt."
            " Delete them from rad-citation-baseline.toml."
        )
    if notes:
        print(
            f"{len(notes)} bare citation(s) resolve against more than one"
            " same-named test function. This is not a failure: the citation"
            " is not stale. It is a note that a bare name cannot say which"
            " of several look-alikes it means; consider citing the file to"
            " disambiguate."
        )


class _Args(argparse.Namespace):
    """Typed view of this checker's command line.

    Attributes:
        paths: Files to check, as pre-commit passes them.
        scan_all: Whether to scan the whole repo instead.
        write_baseline: Whether to rewrite the baseline.
        baseline: Path to the baseline file.
        root: Repository root.
    """

    paths: list[str]
    scan_all: bool
    write_baseline: bool
    baseline: str
    root: str


def _build_parser() -> argparse.ArgumentParser:
    """Construct the command-line parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(description="Check RAD #VERIFY citations.")
    parser.add_argument("paths", nargs="*", help="files to check")
    parser.add_argument(
        "--all",
        dest="scan_all",
        action="store_true",
        help="scan the whole repo",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="rewrite the baseline from a whole-repo scan (requires --all)",
    )
    parser.add_argument("--baseline", default=str(BASELINE_PATH))
    parser.add_argument("--root", default=str(REPO_ROOT))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments, or ``None`` to read ``sys.argv``.

    Returns:
        ``0`` clean, ``1`` findings, ``2`` usage error.
    """
    args = _build_parser().parse_args(argv, namespace=_Args())

    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path

    if not args.paths and not args.scan_all:
        print(
            "check_rad_citations: no files to check. Pass file paths, or --all"
            " to scan the repo. Passing nothing is a usage error rather than"
            " a pass, so this gate can never succeed vacuously.",
            file=sys.stderr,
        )
        return 2
    if args.write_baseline and not args.scan_all:
        print(
            "check_rad_citations: --write-baseline requires --all, otherwise"
            " the baseline would be rewritten from a partial scan and would"
            " silently drop rows.",
            file=sys.stderr,
        )
        return 2

    all_files = _iter_repo_files(root)
    index = build_index(root, all_files)

    if args.write_baseline:
        findings: list[Finding] = []
        for path in all_files:
            findings.extend(scan_file(index, root, path))
        # Only "stale" findings are debt the baseline grandfathers. A "note"
        # is a citation that resolves; baselining it would both misrepresent
        # it as unresolved debt and, worse, cause run() to filter it out of
        # every future report as "already known", silencing the one thing a
        # note exists to keep visible.
        stale = [f for f in findings if f.kind == "stale"]
        notes = [f for f in findings if f.kind == "note"]
        baseline_path.write_text(render_baseline(stale), encoding="utf-8")
        rows = len({(f.path, f.citation) for f in stale})
        print(
            f"wrote {baseline_path}: {rows} row(s) covering"
            f" {len(stale)} stale citation site(s)"
        )
        if notes:
            print(
                f"{len(notes)} bare-name ambiguity note(s) found during this"
                " scan. They are not stale and are not written to the"
                " baseline; re-run without --write-baseline to see them."
            )
        return 0

    try:
        baseline = load_baseline(baseline_path)
    except (ValueError, tomllib.TOMLDecodeError) as error:
        print(f"check_rad_citations: bad baseline: {error}", file=sys.stderr)
        return 2

    targets = _collect_targets(root, args.paths, args.scan_all)
    results = run(root, targets, baseline, index)
    if not results:
        return 0
    _report(results)
    # "note" findings are informational (see Finding.kind): a run with only
    # notes and no stale or baseline-drift findings still passes.
    return 1 if any(f.kind != "note" for f in results) else 0


if __name__ == "__main__":
    sys.exit(main())
