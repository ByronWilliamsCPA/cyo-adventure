"""Unit tests for scripts/check_rad_citations.py.

scripts/ is not an importable package (no ``__init__.py``, by design; see
per-file-ignores ``INP`` for ``scripts/**/*.py`` in pyproject.toml), so the
module is loaded directly from its file path via importlib.

The tests build a miniature repo in ``tmp_path`` for each case rather than
asserting against the real tree, so they pin the parser's behaviour per
citation shape instead of pinning today's backlog.

Covered:

* the seven Python citation shapes the repo actually uses;
* the TypeScript file-existence-only contract, including the deliberate
  refusal to check a paraphrased ``it()`` title;
* the baseline mechanism in both directions: it grandfathers known debt, and
  it reports a baseline row that is no longer stale so the list can only
  shrink;
* the three defects this repo has hit when promoting a scratch script to a
  gate: never exiting non-zero, passing on empty input, and firing outside
  the directory it was calibrated on;
* the ``*_test.py`` module-naming convention, alongside ``test_*.py``;
* that a bare name resolves only against test modules and ``conftest.py``,
  never a same-named function living in ``src/``;
* that an ambiguous bare-name match is a non-failing ``"note"`` finding
  rather than silence or a false pass/fail;
* two defects a D-2 review found in this file's own tests: a guard test that
  held for the wrong reason, and a smoke test that never exercised its own
  stated scenario.

This checker proves a cited test exists; it does not and cannot prove that
test would fail if the property it is cited for were removed. See
"Deliberate non-goals" in ``scripts/check_rad_citations.py``'s module
docstring for that ceiling. Nothing in this file tests for discrimination,
because nothing in the checker attempts it.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    """Load a scripts/ module from its file path.

    Args:
        name: Module basename inside scripts/.

    Returns:
        The executed module.
    """
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves field types through sys.modules, so the module has
    # to be registered before it executes its own @dataclass decorators.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load("check_rad_citations")


def _make_repo(root: Path) -> None:
    """Lay down a miniature repo with a handful of real tests.

    Args:
        root: Directory to populate.
    """
    tests = root / "tests" / "unit"
    tests.mkdir(parents=True)
    (tests / "test_widget.py").write_text(
        "def test_widget_rejects_a_blank_name() -> None:\n"
        "    pass\n"
        "\n"
        "\n"
        "class TestWidgetInvariants:\n"
        "    def test_tally_is_coherent(self) -> None:\n"
        "        pass\n"
        "\n"
        "\n"
        "def test_dual_role_same_family_publish_stamps_actor() -> None:\n"
        "    pass\n"
        "\n"
        "\n"
        "def test_dual_role_foreign_family_publish_stamps_actor() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tests / "test_config.py").write_text("def test_loads() -> None:\n    pass\n")
    web = root / "frontend" / "src" / "kid"
    web.mkdir(parents=True)
    (web / "Reader.badgeToast.test.tsx").write_text("it('x', () => {})\n")


def _write_source(root: Path, body: str, name: str = "src/thing.py") -> Path:
    """Write a source file carrying a RAD block.

    Args:
        root: Repo root.
        body: File contents.
        name: Repo-relative path to write.

    Returns:
        The written path.
    """
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _findings(root: Path, path: Path) -> list[str]:
    """Scan one file and return its findings as ``citation`` strings.

    Args:
        root: Repo root.
        path: File to scan.

    Returns:
        The citation key of each finding, in order.
    """
    index = _MODULE.build_index(root)
    return [f.citation for f in _MODULE.scan_file(index, root, path)]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Provide a miniature repo with known tests.

    Args:
        tmp_path: pytest temporary directory.

    Returns:
        The repo root.
    """
    _make_repo(tmp_path)
    return tmp_path


# --------------------------------------------------------------------------
# Shape 1: single-line "path::test_name"
# --------------------------------------------------------------------------


def test_single_line_path_and_name_resolves(repo: Path) -> None:
    """A correct ``path::name`` citation produces no finding."""
    source = _write_source(
        repo,
        "# #CRITICAL: data integrity: the name is validated here.\n"
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n"
        "VALUE = 1\n",
    )
    assert _findings(repo, source) == []


def test_single_line_name_missing_from_the_cited_file_is_stale(repo: Path) -> None:
    """A real file cited with a name it does not define is reported."""
    source = _write_source(
        repo,
        "# #CRITICAL: data integrity: the name is validated here.\n"
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_long_name.\n"
        "VALUE = 1\n",
    )
    assert _findings(repo, source) == [
        "tests/unit/test_widget.py::test_widget_rejects_a_long_name"
    ]


def test_class_qualified_chain_checks_every_component(repo: Path) -> None:
    """``file::Class::method`` resolves only when both names are defined."""
    good = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::TestWidgetInvariants"
        "::test_tally_is_coherent.\n",
        name="src/good.py",
    )
    bad = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::TestGhost::test_tally_is_coherent.\n",
        name="src/bad.py",
    )
    assert _findings(repo, good) == []
    assert _findings(repo, bad) == ["tests/unit/test_widget.py::TestGhost"]


# --------------------------------------------------------------------------
# Shape 2: multi-line comma list whose continuation lines re-open with "::"
# --------------------------------------------------------------------------


def test_comma_list_continuation_carries_the_cited_file(repo: Path) -> None:
    """Continuation lines that re-open with ``::`` attach to the last path.

    The comma separator must not be glued onto the preceding name, and each
    listed name is resolved against the carried file rather than skipped.
    """
    source = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name,\n"
        "# ::test_tally_is_coherent, ::test_absent_one.\n",
    )
    assert _findings(repo, source) == ["tests/unit/test_widget.py::test_absent_one"]


def test_path_wrapped_before_its_name_rejoins(repo: Path) -> None:
    """A line ending in ``::`` continues into the name on the next line."""
    source = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::\n# test_widget_rejects_a_blank_name.\n",
    )
    assert _findings(repo, source) == []


# --------------------------------------------------------------------------
# Shape 3: prose naming only a file
# --------------------------------------------------------------------------


def test_prose_naming_only_a_file_is_checked_for_existence(repo: Path) -> None:
    """Prose coverage still has its file citation resolved."""
    good = _write_source(
        repo,
        "# #VERIFY: test_widget.py covers the blank and the overlong name.\n",
        name="src/good.py",
    )
    bad = _write_source(
        repo,
        "# #VERIFY: test_widgets.py covers the blank and the overlong name.\n",
        name="src/bad.py",
    )
    assert _findings(repo, good) == []
    assert _findings(repo, bad) == ["test_widgets.py"]


def test_verify_line_naming_no_test_at_all_is_skipped(repo: Path) -> None:
    """A prose-only ``#VERIFY`` yields no citation and no finding.

    The checker proves citations resolve; it does not police citation style,
    so a line pointing at a source module or a runbook is left alone.
    """
    source = _write_source(
        repo,
        "# #VERIFY: moderation/thresholds.py validates at the application\n"
        "# boundary; docs/operations/runbook.md section 11 is the procedure.\n",
    )
    assert _findings(repo, source) == []


# --------------------------------------------------------------------------
# Shape 4: docstring-embedded citation with no "#" comment marker
# --------------------------------------------------------------------------


def test_docstring_citation_with_a_hash_marker_is_checked(repo: Path) -> None:
    """A citation inside a module docstring, hash-prefixed, is checked.

    This fixture keeps the ``#`` on ``#CRITICAL``/``#VERIFY`` even though it
    sits inside a triple-quoted string (so it is not a real Python comment
    token); it proves docstring-embedded markers are parsed at all. It does
    not exercise the hash-less spelling the module docstring says is also
    supported; see ``test_docstring_citation_without_a_hash_marker_is_checked``
    for that case (Minor 15).
    """
    source = _write_source(
        repo,
        '"""Module summary.\n'
        "\n"
        "#CRITICAL: security: PII must never be sent.\n"
        "#VERIFY: tests/unit/test_widget.py::test_pii_is_never_sent\n"
        "asserts every call passes send_default_pii=False.\n"
        '"""\n',
    )
    assert _findings(repo, source) == [
        "tests/unit/test_widget.py::test_pii_is_never_sent"
    ]


def test_docstring_citation_without_a_hash_marker_is_checked(repo: Path) -> None:
    """A hash-less docstring block (``VERIFY:``, no ``#``) is still checked.

    Minor 15: the module docstring says the leading ``#`` is optional inside
    docstrings, "because docstring-embedded markers carry no comment
    character at all", but the extraction gate used to test the literal
    substring ``"#VERIFY"``, which a hash-less block never contains. Before
    the fix this citation was skipped entirely: zero findings, exit 0,
    despite naming a test that does not exist.
    """
    source = _write_source(
        repo,
        '"""Module summary.\n'
        "\n"
        "CRITICAL: security: PII must never be sent.\n"
        "VERIFY: tests/unit/test_widget.py::test_pii_is_never_sent\n"
        "asserts every call passes send_default_pii=False.\n"
        '"""\n',
    )
    assert _findings(repo, source) == [
        "tests/unit/test_widget.py::test_pii_is_never_sent"
    ]


def test_docstring_block_stops_at_a_google_section_heading(repo: Path) -> None:
    """A VERIFY block must not swallow the docstring's ``Args:`` list."""
    source = _write_source(
        repo,
        "def f(test_widget_thing: int) -> int:\n"
        '    """Do a thing.\n'
        "\n"
        "    #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n"
        "\n"
        "    Args:\n"
        "        test_widget_thing: not a citation.\n"
        "\n"
        "    Returns:\n"
        "        The thing.\n"
        '    """\n'
        "    return test_widget_thing\n",
    )
    assert _findings(repo, source) == []


# --------------------------------------------------------------------------
# Shape 5: informal bare module name with no ".py"
# --------------------------------------------------------------------------


def test_bare_module_name_without_a_suffix_resolves(repo: Path) -> None:
    """``test_config`` resolves against ``tests/unit/test_config.py``."""
    source = _write_source(
        repo,
        "# #VERIFY: no branch echoes the secret value; test_config covers it.\n",
    )
    assert _findings(repo, source) == []


def test_bare_name_resolves_as_a_function_too(repo: Path) -> None:
    """A bare name may name a test function rather than a module."""
    source = _write_source(
        repo,
        "# #VERIFY: same module, test_widget_rejects_a_blank_name.\n",
    )
    assert _findings(repo, source) == []


def test_bare_name_matching_neither_is_stale(repo: Path) -> None:
    """A bare name that is neither a module nor a function is reported."""
    source = _write_source(repo, "# #VERIFY: test_nothing_at_all covers it.\n")
    assert _findings(repo, source) == ["test_nothing_at_all"]


# --------------------------------------------------------------------------
# Shape 6: brace-glob shorthand for a test family
# --------------------------------------------------------------------------


def test_brace_glob_family_resolves_when_every_expansion_matches(repo: Path) -> None:
    """Each brace alternative must match at least one real test."""
    source = _write_source(
        repo,
        "# #VERIFY: test_dual_role_{same,foreign}_family_publish_stamps_* in\n"
        "# tests/unit/test_widget.py.\n",
    )
    assert _findings(repo, source) == []


def test_brace_glob_is_stale_when_one_expansion_matches_nothing(repo: Path) -> None:
    """A family citation is only as true as its least-supported member."""
    source = _write_source(
        repo,
        "# #VERIFY: test_dual_role_{same,foreign,orphan}_family_publish_stamps_*.\n",
    )
    assert _findings(repo, source) == [
        "test_dual_role_{same,foreign,orphan}_family_publish_stamps_*"
    ]


def test_expand_braces_produces_every_combination() -> None:
    """Brace expansion is combinatorial across multiple groups."""
    assert _MODULE.expand_braces("a{1,2}b{x,y}") == ["a1bx", "a1by", "a2bx", "a2by"]


# --------------------------------------------------------------------------
# Shape 7: long identifier word-wrapped mid-token
# --------------------------------------------------------------------------


def test_name_wrapped_mid_token_after_an_underscore_rejoins(repo: Path) -> None:
    """A line ending in ``_`` continues the same identifier."""
    source = _write_source(
        repo,
        "# #VERIFY: test_dual_role_same_family_publish_stamps_\n"
        "# actor pins the stamp.\n",
    )
    assert _findings(repo, source) == []


def test_name_wrapped_mid_token_before_an_underscore_rejoins(repo: Path) -> None:
    """A continuation line starting with ``_`` continues the same identifier.

    Prose never opens a line with an underscore, so this is unambiguous. The
    naive rule that only looks at the end of the previous line misses it and
    reports a truncated name that nobody wrote.
    """
    source = _write_source(
        repo,
        "# #VERIFY: test_dual_role_same_family_publish_stamps\n"
        "# _actor pins the stamp.\n",
    )
    assert _findings(repo, source) == []


def test_mid_token_wrap_inside_a_docstring_rejoins(repo: Path) -> None:
    """The comment-styled prefix inside a docstring is stripped before joining.

    Leaving the ``#`` in place would wedge it between the two halves of a
    wrapped identifier and invent a stale citation.
    """
    source = _write_source(
        repo,
        '"""Summary.\n'
        "\n"
        "#        multilingual names. #VERIFY: test_dual_role_same_family_publish_\n"
        "#        stamps_actor pins this residual.\n"
        '"""\n',
    )
    assert _findings(repo, source) == []


# --------------------------------------------------------------------------
# The other pytest ``python_files`` convention: "*_test.py"
# --------------------------------------------------------------------------


def test_suffix_style_test_module_path_resolves(repo: Path) -> None:
    """``x_test.py`` is recognised as a test module path, not just ``test_x.py``.

    ``pyproject.toml``'s ``python_files`` permits both ``test_*.py`` and
    ``*_test.py``; a citation naming the second style must resolve exactly
    like the first.
    """
    _write_source(
        repo,
        "def test_suffix_style() -> None:\n    pass\n",
        name="tests/unit/widget_test.py",
    )
    source = _write_source(
        repo, "# #VERIFY: tests/unit/widget_test.py::test_suffix_style.\n"
    )
    assert _findings(repo, source) == []


def test_suffix_style_test_module_stale_name_is_reported(repo: Path) -> None:
    """A real ``*_test.py`` file cited with the wrong function name is stale.

    Before this path shape was recognised, the ``path`` group never matched
    it, so the citation fell through to a repo-wide bare-name check on just
    the trailing ``test_...`` chain, silently dropping the file part of the
    citation instead of validating it. This pins that the file is now
    actually resolved: the reported citation carries the file prefix.
    """
    _write_source(
        repo,
        "def test_suffix_style() -> None:\n    pass\n",
        name="tests/unit/widget_test.py",
    )
    source = _write_source(
        repo, "# #VERIFY: tests/unit/widget_test.py::test_ghost_case.\n"
    )
    assert _findings(repo, source) == ["tests/unit/widget_test.py::test_ghost_case"]


# --------------------------------------------------------------------------
# Bare names resolve only against test modules and conftest.py
# --------------------------------------------------------------------------


def test_bare_name_does_not_resolve_against_a_src_defined_function(repo: Path) -> None:
    """A ``test_``-prefixed function defined outside a test module must not
    satisfy a bare citation.

    Before this was restricted to test modules and ``conftest.py``, every
    ``test_``-prefixed function anywhere in the repo counted, so a helper
    that happens to start with ``test_`` in ``src/`` could silently satisfy
    an unrelated bare citation. That is the false-negative direction a
    citation gate cannot afford.
    """
    _write_source(
        repo,
        "def test_helper_defined_in_src() -> None:\n    pass\n",
        name="src/helper.py",
    )
    source = _write_source(
        repo, "# #VERIFY: test_helper_defined_in_src proves it.\n", name="src/thing.py"
    )
    assert _findings(repo, source) == ["test_helper_defined_in_src"]


# --------------------------------------------------------------------------
# An ambiguous bare name is a non-failing note, not silence
# --------------------------------------------------------------------------


def test_ambiguous_bare_name_resolution_emits_a_non_failing_note(repo: Path) -> None:
    """A bare name matching two same-named test functions is flagged, not silent.

    The citation still resolves (repo-wide bare matching is deliberately
    lenient; see "Deliberate non-goals"), so this must not be a ``"stale"``
    finding. It is reported as a ``"note"`` finding so the ambiguity is
    visible instead of invisible, per the reviewer's ``test_guardian_gets_403``
    case: three same-named functions across three files, where a bare
    citation cannot say which one covers the claim.
    """
    _write_source(
        repo,
        "def test_shared_case() -> None:\n    pass\n",
        name="tests/unit/test_c.py",
    )
    _write_source(
        repo,
        "def test_shared_case() -> None:\n    pass\n",
        name="tests/unit/test_d.py",
    )
    source = _write_source(
        repo, "# #VERIFY: test_shared_case proves it.\n", name="src/thing.py"
    )
    index = _MODULE.build_index(repo)
    findings = _MODULE.scan_file(index, repo, source)
    assert [(f.kind, f.citation) for f in findings] == [("note", "test_shared_case")]


def test_ambiguous_bare_name_note_does_not_fail_the_run(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run whose only finding is an ambiguity note still exits 0.

    A note is informational, never blocking; this is the exit-code half of
    the previous test. The note text is asserted on stdout too, so the test
    fails (rather than passing vacuously) if note generation were deleted
    outright instead of merely kept non-blocking.
    """
    _write_source(
        repo,
        "def test_shared_case() -> None:\n    pass\n",
        name="tests/unit/test_c.py",
    )
    _write_source(
        repo,
        "def test_shared_case() -> None:\n    pass\n",
        name="tests/unit/test_d.py",
    )
    _write_source(repo, "# #VERIFY: test_shared_case proves it.\n", name="src/thing.py")
    path = _baseline(repo, "[python]\n[typescript]\n")
    assert _MODULE.main(["--all", "--root", str(repo), "--baseline", str(path)]) == 0
    assert "note: test_shared_case" in capsys.readouterr().out


# --------------------------------------------------------------------------
# _join_block: the trailing "::<space>" cleanup is not dead code
# --------------------------------------------------------------------------


def test_join_block_closes_the_gap_before_a_wrapped_glob_or_brace_continuation() -> (
    None
):
    """The tight-join rule alone cannot close every wrap-induced gap.

    The tight-join rule treats a continuation as attached only when it opens
    with an identifier character (alnum or ``_``). A continuation that opens
    with ``*`` or ``{`` (a glob or brace citation, both valid ``_NAME_BODY``
    starts) is not caught by that rule and would otherwise leave a stray
    space right after ``::``, which ``_PY_CITATION_RE`` would then fail to
    recognise as a chain at all. This is the one class of continuation the
    tight-join rule cannot see, not a redundant repeat of it.
    """
    assert (
        _MODULE._join_block(["tests/unit/test_widget.py::", "*_publish_stamps_actor"])
        == "tests/unit/test_widget.py::*_publish_stamps_actor"
    )
    assert (
        _MODULE._join_block(
            ["tests/unit/test_widget.py::", "{a,b}_publish_stamps_actor"]
        )
        == "tests/unit/test_widget.py::{a,b}_publish_stamps_actor"
    )


# --------------------------------------------------------------------------
# TypeScript: file existence only
# --------------------------------------------------------------------------


def test_ts_dotted_basename_resolves(repo: Path) -> None:
    """A colocated ``Component.suffix.test.tsx`` citation resolves whole.

    Truncating at the first dot would report the real file as missing.
    """
    source = _write_source(
        repo,
        "// #VERIFY: Reader.badgeToast.test.tsx 'suppresses the toast when\n"
        "// badges_enabled is off'.\n",
        name="frontend/src/kid/progressApi.ts",
    )
    assert _findings(repo, source) == []


def test_ts_missing_file_is_stale(repo: Path) -> None:
    """A TS citation naming a file that does not exist is reported."""
    source = _write_source(
        repo,
        "// #VERIFY: Reader.ghostToast.test.tsx 'does something'.\n",
        name="frontend/src/kid/other.ts",
    )
    assert _findings(repo, source) == ["Reader.ghostToast.test.tsx"]


def test_ts_paraphrased_test_title_is_not_checked(repo: Path) -> None:
    """A quoted paraphrase of an ``it()`` title is deliberately not checked.

    No TS citation in this repo embeds a literal test title, so checking the
    quoted text would be checking a paraphrase. That would generate noise and
    train people to ignore the hook.
    """
    source = _write_source(
        repo,
        "/**\n"
        " * #VERIFY: Reader.badgeToast.test.tsx 'a title that matches no it()\n"
        " * block anywhere in the repository whatsoever'.\n"
        " */\n",
        name="frontend/src/kid/jsdoc.tsx",
    )
    assert _findings(repo, source) == []


# --------------------------------------------------------------------------
# The baseline mechanism, in both directions
# --------------------------------------------------------------------------


def _baseline(root: Path, body: str) -> Path:
    """Write a baseline file.

    Args:
        root: Repo root.
        body: TOML contents.

    Returns:
        The baseline path.
    """
    path = root / "rad-citation-baseline.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_baseline_grandfathers_a_known_stale_citation(repo: Path) -> None:
    """A baselined citation does not fail the run."""
    _write_source(repo, "# #VERIFY: test_nothing_at_all covers it.\n")
    path = _baseline(
        repo,
        '[python]\n"src/thing.py" = ["test_nothing_at_all"]\n[typescript]\n',
    )
    exit_code = _MODULE.main(
        ["--all", "--root", str(repo), "--baseline", str(path)],
    )
    assert exit_code == 0


def test_baseline_does_not_grandfather_a_different_citation(repo: Path) -> None:
    """Grandfathering is per citation, not per file."""
    _write_source(
        repo,
        "# #VERIFY: test_nothing_at_all covers it.\n"
        "# #ASSUME: ui state: the other one.\n"
        "# #VERIFY: test_also_absent covers it.\n",
    )
    path = _baseline(
        repo,
        '[python]\n"src/thing.py" = ["test_nothing_at_all"]\n[typescript]\n',
    )
    assert _MODULE.main(["--all", "--root", str(repo), "--baseline", str(path)]) == 1


def test_baseline_reports_an_entry_that_is_no_longer_stale(repo: Path) -> None:
    """A fixed citation cannot sit in the debt list pretending to be debt.

    This is the guard against the failure mode where a baseline silently
    absorbs true positives forever: the list may only shrink.
    """
    _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n",
    )
    path = _baseline(
        repo,
        "[python]\n"
        '"src/thing.py" = ['
        '"tests/unit/test_widget.py::test_widget_rejects_a_blank_name"]\n'
        "[typescript]\n",
    )
    index = _MODULE.build_index(repo)
    baseline = _MODULE.load_baseline(path)
    findings = _MODULE.run(repo, [repo / "src" / "thing.py"], baseline, index)
    assert [(f.kind, f.citation) for f in findings] == [
        ("baseline", "tests/unit/test_widget.py::test_widget_rejects_a_blank_name")
    ]
    assert _MODULE.main(["--all", "--root", str(repo), "--baseline", str(path)]) == 1


def test_baseline_reports_a_row_whose_file_is_gone(repo: Path) -> None:
    """A baselined file that no longer exists must not linger in the list."""
    path = _baseline(
        repo,
        '[python]\n"src/deleted.py" = ["test_nothing_at_all"]\n[typescript]\n',
    )
    index = _MODULE.build_index(repo)
    findings = _MODULE.run(repo, [], _MODULE.load_baseline(path), index)
    assert [f.path for f in findings] == ["src/deleted.py"]


def test_baseline_drift_is_found_even_when_the_file_was_not_passed(
    repo: Path,
) -> None:
    """Every baselined file is scanned, however few files the hook was handed.

    Otherwise a two-file pre-commit run could never notice that a row
    elsewhere had become obsolete, and the list would stop shrinking.
    """
    _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n",
        name="src/elsewhere.py",
    )
    other = _write_source(repo, "VALUE = 1\n", name="src/passed.py")
    path = _baseline(
        repo,
        "[python]\n"
        '"src/elsewhere.py" = ['
        '"tests/unit/test_widget.py::test_widget_rejects_a_blank_name"]\n'
        "[typescript]\n",
    )
    index = _MODULE.build_index(repo)
    findings = _MODULE.run(repo, [other], _MODULE.load_baseline(path), index)
    assert [f.kind for f in findings] == ["baseline"]


def test_baseline_key_is_stable_when_lines_move(repo: Path) -> None:
    """The baseline keys on citation text, never on line numbers.

    Inserting unrelated lines above a citation must not churn the file.
    """
    body = "# #VERIFY: test_nothing_at_all covers it.\n"
    source = _write_source(repo, body)
    index = _MODULE.build_index(repo)
    before = _MODULE.render_baseline(_MODULE.scan_file(index, repo, source))
    source.write_text("VALUE = 1\n" * 40 + body, encoding="utf-8")
    after = _MODULE.render_baseline(_MODULE.scan_file(index, repo, source))
    assert before == after


def test_render_and_load_baseline_round_trip(repo: Path) -> None:
    """A rendered baseline parses back into the same rows."""
    _write_source(repo, "# #VERIFY: test_nothing_at_all covers it.\n")
    _write_source(
        repo,
        "// #VERIFY: Ghost.test.tsx 'x'.\n",
        name="frontend/src/kid/g.ts",
    )
    index = _MODULE.build_index(repo)
    findings: list[object] = []
    for path in _MODULE._iter_repo_files(repo):
        findings.extend(_MODULE.scan_file(index, repo, path))
    path = _baseline(repo, _MODULE.render_baseline(findings))
    loaded = _MODULE.load_baseline(path)
    assert loaded["python"]["src/thing.py"] == ["test_nothing_at_all"]
    assert loaded["typescript"]["frontend/src/kid/g.ts"] == ["Ghost.test.tsx"]


def test_malformed_baseline_is_a_usage_error(repo: Path) -> None:
    """A baseline the checker cannot trust stops the run rather than passing."""
    path = _baseline(repo, '[python]\n"src/thing.py" = "not-a-list"\n')
    assert _MODULE.main(["--all", "--root", str(repo), "--baseline", str(path)]) == 2


# --------------------------------------------------------------------------
# The three gate-promotion defects this repo has hit before
# --------------------------------------------------------------------------


def test_exits_non_zero_on_a_stale_citation(repo: Path) -> None:
    """Defect 1: a checker that never exits non-zero is not a gate."""
    source = _write_source(repo, "# #VERIFY: test_nothing_at_all covers it.\n")
    path = _baseline(repo, "[python]\n[typescript]\n")
    assert (
        _MODULE.main([str(source), "--root", str(repo), "--baseline", str(path)]) == 1
    )


def test_no_files_and_no_all_is_a_usage_error(repo: Path) -> None:
    """Defect 2: being handed nothing is an error, never a vacuous pass."""
    path = _baseline(repo, "[python]\n[typescript]\n")
    assert _MODULE.main(["--root", str(repo), "--baseline", str(path)]) == 2


def test_write_baseline_refuses_a_partial_scan(repo: Path) -> None:
    """``--write-baseline`` without ``--all`` would silently drop rows."""
    source = _write_source(repo, "# #VERIFY: test_nothing_at_all covers it.\n")
    path = _baseline(repo, "[python]\n[typescript]\n")
    exit_code = _MODULE.main(
        ["--write-baseline", str(source), "--root", str(repo), "--baseline", str(path)]
    )
    assert exit_code == 2


def test_write_baseline_never_writes_a_note_as_debt(repo: Path) -> None:
    """An ambiguous-but-resolving bare name must never land in the baseline.

    ``render_baseline``'s own header promises every row names a test that
    does not exist. A ``"note"`` finding names a test that does exist (just
    ambiguously), so writing it in would misrepresent it as debt, and worse,
    would cause ``run()`` to treat it as already known and stop reporting it
    on every future scan: the one behaviour a note exists to prevent.
    """
    _write_source(
        repo,
        "def test_shared_case() -> None:\n    pass\n",
        name="tests/unit/test_c.py",
    )
    _write_source(
        repo,
        "def test_shared_case() -> None:\n    pass\n",
        name="tests/unit/test_d.py",
    )
    _write_source(repo, "# #VERIFY: test_shared_case proves it.\n", name="src/thing.py")
    path = _baseline(repo, "[python]\n[typescript]\n")
    exit_code = _MODULE.main(
        ["--all", "--write-baseline", "--root", str(repo), "--baseline", str(path)]
    )
    assert exit_code == 0
    loaded = _MODULE.load_baseline(path)
    assert loaded["python"] == {}


def test_clean_tree_exits_zero(repo: Path) -> None:
    """Defect 3: no finding is reported where every citation resolves."""
    source = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n",
    )
    path = _baseline(repo, "[python]\n[typescript]\n")
    assert (
        _MODULE.main([str(source), "--root", str(repo), "--baseline", str(path)]) == 0
    )


def test_non_source_arguments_are_ignored(repo: Path) -> None:
    """A hook run handed a README must not crash, and must not be scanned.

    ``_collect_targets`` is asserted directly so the test fails if the
    suffix filter is ever removed, not just if the run happens to crash;
    a real source file is passed alongside the README so the run itself
    has something to scan.
    """
    readme = repo / "README.md"
    readme.write_text("# hi\n", encoding="utf-8")
    assert _MODULE._collect_targets(repo, [str(readme)], scan_all=False) == []
    clean = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n",
    )
    path = _baseline(repo, "[python]\n[typescript]\n")
    exit_code = _MODULE.main(
        [str(readme), str(clean), "--root", str(repo), "--baseline", str(path)]
    )
    assert exit_code == 0


def test_missing_file_argument_is_skipped_without_crashing(repo: Path) -> None:
    """A path that no longer exists must be filtered before it is read.

    This is the case pre-commit can actually hand the hook: a file deleted
    in the same commit still appears in the diff's path list. Without the
    ``is_file()`` guard in ``_collect_targets``, ``scan_file`` would try to
    read a path that is not there and raise ``FileNotFoundError`` instead of
    the run completing cleanly; asserting the exit code catches that
    regardless of which layer would have crashed. A real, resolving source
    file is passed alongside the ghost path so the run has something to
    scan and the vacuous-target guard (Important 7) does not itself account
    for the exit code.
    """
    ghost = repo / "src" / "ghost.py"
    clean = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n",
    )
    assert _MODULE._collect_targets(repo, [str(ghost)], scan_all=False) == []
    path = _baseline(repo, "[python]\n[typescript]\n")
    exit_code = _MODULE.main(
        [str(ghost), str(clean), "--root", str(repo), "--baseline", str(path)]
    )
    assert exit_code == 0


def test_baseline_toml_argument_is_accepted_without_being_scanned(repo: Path) -> None:
    """The hook also runs when ``rad-citation-baseline.toml`` itself changes.

    pre-commit's ``files:`` regex for this hook matches the baseline file
    too, so an edit to it re-triggers the hook with the baseline's own path
    as an argument. ``_collect_targets`` is asserted directly to prove the
    ``.toml`` path is dropped rather than treated as a source file to scan
    for citations; a real source file is passed alongside it so the run
    itself has something to scan (with an empty baseline, the vacuous-target
    guard from Important 7 would otherwise reject the run outright, which
    would prove nothing about the suffix filter this test targets).
    """
    baseline_path = _baseline(repo, "[python]\n[typescript]\n")
    assert _MODULE._collect_targets(repo, [str(baseline_path)], scan_all=False) == []
    clean = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::test_widget_rejects_a_blank_name.\n",
    )
    exit_code = _MODULE.main(
        [
            str(baseline_path),
            str(clean),
            "--root",
            str(repo),
            "--baseline",
            str(baseline_path),
        ]
    )
    assert exit_code == 0


def test_a_file_with_no_verify_marker_short_circuits_before_parsing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-marker fast path must skip parsing entirely, not just filter results.

    ``_blocks_from_groups`` already requires a ``#VERIFY`` hit, so asserting
    only that the finding list comes back empty would still pass with the
    fast path deleted, for an unrelated reason. This pins the fast path
    itself by proving ``extract_py_blocks`` is never invoked when it fires.
    """
    source = _write_source(repo, "VALUE = 1  # test_nothing_at_all\n")

    def _must_not_run(_source: str) -> list[_MODULE.Block]:
        msg = "extract_py_blocks must not run when '#VERIFY' is absent"
        raise AssertionError(msg)

    monkeypatch.setattr(_MODULE, "extract_py_blocks", _must_not_run)
    index = _MODULE.build_index(repo)
    assert _MODULE.scan_file(index, repo, source) == []


def test_unparseable_python_still_gets_a_line_based_pass(repo: Path) -> None:
    """A file the tokenizer rejects falls back rather than silently passing."""
    source = _write_source(
        repo,
        "def broken(:\n# #VERIFY: test_nothing_at_all covers it.\n",
    )
    assert _findings(repo, source) == ["test_nothing_at_all"]


def test_this_test_file_is_excluded_from_scanning(repo: Path) -> None:
    """This module's fixtures cite tests that must not exist, by design.

    Scanning it would report the fixtures as permanent debt, the way a secret
    scanner flags its own sample keys. The exclusion is a fixed list of one, so
    this pins both that the list holds and that it is not a general opt-out.
    """
    excluded = _write_source(
        repo,
        "# #VERIFY: test_nothing_at_all covers it.\n",
        name="tests/unit/test_check_rad_citations.py",
    )
    assert _findings(repo, excluded) == []
    # A neighbour with the same content is still scanned, so the exclusion is
    # scoped to the one path rather than to the tests/unit directory.
    neighbour = _write_source(
        repo,
        "# #VERIFY: test_nothing_at_all covers it.\n",
        name="tests/unit/test_check_rad_citations_extra.py",
    )
    assert _findings(repo, neighbour) == ["test_nothing_at_all"]


# --------------------------------------------------------------------------
# Important 5: a glob citation matching too many real tests proves nothing
# --------------------------------------------------------------------------


def test_glob_citation_matching_too_many_tests_is_stale(repo: Path) -> None:
    """``test_*`` fnmatches nearly the whole repo and must not resolve for free.

    Before the fix, ``_is_pattern`` treated any ``*``/``{}`` citation as
    resolved the moment one real name matched, so ``test_*`` matched every
    test in the repo and passed silently with no note either (Important 5
    in the D-2 final review). The fixture repo needs enough matching tests
    to exceed ``_MAX_GLOB_MATCHES`` (20); the shared ``repo`` fixture's small
    handful of tests is not enough to exercise the bound.
    """
    tests_dir = repo / "tests" / "unit"
    lines = [f"def test_extra_case_{i}() -> None:\n    pass\n\n" for i in range(25)]
    (tests_dir / "test_bulk.py").write_text("".join(lines), encoding="utf-8")
    source = _write_source(
        repo,
        "# #CRITICAL: security: totally unproven claim.\n# #VERIFY: test_*\n",
    )
    findings = _findings(repo, source)
    assert len(findings) == 1
    assert findings[0] == "test_*"


def test_bounded_brace_glob_still_resolves_from_nothing(repo: Path) -> None:
    """A small, deliberate glob family is not caught by the overreach bound.

    ``test_dual_role_{same,foreign}_*`` matches exactly the two fixture
    tests named for it, well under ``_MAX_GLOB_MATCHES``; the Important 5
    fix must not turn every glob into a failure, only unbounded ones.
    """
    source = _write_source(
        repo,
        "# #VERIFY: test_dual_role_{same,foreign}_family_publish_stamps_actor\n",
    )
    assert _findings(repo, source) == []


# --------------------------------------------------------------------------
# Important 6: the baseline grandfathers a citation SITE, not a citation STRING
# --------------------------------------------------------------------------


def test_baseline_covers_only_as_many_sites_as_it_lists(repo: Path) -> None:
    """A citation repeated twice in one file is grandfathered only once.

    Before the fix, the baseline was keyed on ``(file, citation)``, a set:
    one row for ``test_ghost_case`` in ``src/thing.py`` silently absorbed
    every site sharing that string, however many there were. A brand-new
    second site reusing an already-baselined name must still be reported
    (Important 6 in the D-2 final review).
    """
    source = _write_source(
        repo,
        "# #VERIFY: test_ghost_case one\nX = 1\n# #VERIFY: test_ghost_case two\nY = 2\n",
    )
    baseline = _MODULE.load_baseline(
        _baseline(
            repo, '[python]\n"src/thing.py" = ["test_ghost_case"]\n[typescript]\n'
        )
    )
    index = _MODULE.build_index(repo)
    findings = _MODULE.run(repo, [source], baseline, index)
    stale = [f for f in findings if f.kind == "stale"]
    assert [f.citation for f in stale] == ["test_ghost_case"]
    assert stale[0].line == 3


def test_baseline_covering_every_real_site_stays_silent(repo: Path) -> None:
    """A single citation with a single matching baseline row is unaffected.

    Regression guard for the per-site rewrite: the common one-site case
    must not start failing just because the reconciliation is now counted.
    """
    source = _write_source(repo, "# #VERIFY: test_brand_new_ghost_case\nX = 1\n")
    baseline = _MODULE.load_baseline(
        _baseline(
            repo,
            '[python]\n"src/thing.py" = ["test_brand_new_ghost_case"]\n[typescript]\n',
        )
    )
    index = _MODULE.build_index(repo)
    findings = _MODULE.run(repo, [source], baseline, index)
    assert [f for f in findings if f.kind == "stale"] == []


# --------------------------------------------------------------------------
# Important 6 (CI half): --assert-no-growth compares against a prior ref
# --------------------------------------------------------------------------


def _init_git_repo(root: Path) -> None:
    """Initialise a throwaway git repository for ``--assert-no-growth`` tests.

    Args:
        root: Directory to turn into a git repository.
    """
    git = shutil.which("git")
    assert git is not None, "git must be on PATH to exercise --assert-no-growth"
    env_args = ["-c", "user.email=test@example.com", "-c", "user.name=test"]
    subprocess.run([git, *env_args, "init", "-q", str(root)], check=True)
    subprocess.run([git, *env_args, "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [git, *env_args, "-C", str(root), "commit", "-q", "-m", "snapshot"],
        check=True,
    )


def test_assert_no_growth_passes_when_the_baseline_did_not_grow(
    tmp_path: Path,
) -> None:
    """No growth against BASE_REF exits 0."""
    baseline = _baseline(
        tmp_path, '[python]\n"src/thing.py" = ["test_ghost_case"]\n[typescript]\n'
    )
    _init_git_repo(tmp_path)
    assert _MODULE._assert_no_growth(tmp_path, baseline, "HEAD") == 0


def test_assert_no_growth_fails_when_a_new_site_is_grandfathered(
    tmp_path: Path,
) -> None:
    """A baseline that grew past BASE_REF's site count fails.

    This is the CI-side half of Important 6: it catches a pull request that
    adds a brand-new stale citation alongside a brand-new (or widened)
    baseline row that grandfathers it, which no single-commit run of this
    script, working-tree-only, can ever see.
    """
    baseline = _baseline(
        tmp_path, '[python]\n"src/thing.py" = ["test_ghost_case"]\n[typescript]\n'
    )
    _init_git_repo(tmp_path)
    baseline.write_text(
        '[python]\n"src/thing.py" = ["test_ghost_case", "test_ghost_case",'
        ' "test_other_ghost"]\n[typescript]\n',
        encoding="utf-8",
    )
    assert _MODULE._assert_no_growth(tmp_path, baseline, "HEAD") == 1


def test_assert_no_growth_reports_a_missing_ref_as_a_usage_error(
    tmp_path: Path,
) -> None:
    """A ref that does not exist in history is a usage error, not a crash."""
    baseline = _baseline(tmp_path, "[python]\n[typescript]\n")
    _init_git_repo(tmp_path)
    assert _MODULE._assert_no_growth(tmp_path, baseline, "not-a-real-ref") == 2


def test_assert_no_growth_reports_a_malformed_prior_baseline_as_a_usage_error(
    tmp_path: Path,
) -> None:
    """A prior commit whose baseline is not valid TOML is a usage error."""
    baseline = _baseline(tmp_path, "not valid toml [[[\n")
    _init_git_repo(tmp_path)
    assert _MODULE._assert_no_growth(tmp_path, baseline, "HEAD") == 2


# --------------------------------------------------------------------------
# Important 7: the run must never scan zero files and still exit 0
# --------------------------------------------------------------------------


def test_run_scanning_nothing_at_all_is_a_usage_error(repo: Path) -> None:
    """An empty baseline plus no scannable targets can never pass silently.

    ``.pre-commit-config.yaml``'s ``files:`` regex matches
    ``rad-citation-baseline.toml`` itself, so a commit that stages only the
    baseline invokes this script with only the baseline's own path as an
    argument. ``_collect_targets`` drops the ``.toml`` suffix, and once the
    baseline reaches zero rows there is nothing left to rescan either: the
    run would silently scan nothing and exit 0 (Important 7 in the D-2 final
    review), which contradicts the script's own claim that it can never
    succeed vacuously.
    """
    path = _baseline(repo, "[python]\n[typescript]\n")
    exit_code = _MODULE.main([str(path), "--root", str(repo), "--baseline", str(path)])
    assert exit_code == 2


def test_run_with_all_flag_is_never_vacuous(repo: Path) -> None:
    """``--all`` always finds the fixture repo's own tests, so it never trips."""
    path = _baseline(repo, "[python]\n[typescript]\n")
    exit_code = _MODULE.main(["--all", "--root", str(repo), "--baseline", str(path)])
    assert exit_code == 0


# --------------------------------------------------------------------------
# Important 8: a citation continuation re-indented on the next line
# --------------------------------------------------------------------------


def test_reindented_continuation_still_carries_the_name(repo: Path) -> None:
    """A ``path::`` continuation at a different column must not drop ``::name``.

    Before the fix, comment grouping required the continuation line's
    column to match the opening line's exactly; a continuation indented
    differently (as an autoformatter or a copy-paste can produce) fell
    outside the group, leaving a bare ``path::`` that resolves on the file
    half alone while silently discarding the name (Important 8 in the D-2
    final review).
    """
    source = _write_source(
        repo,
        "# #VERIFY: tests/unit/test_widget.py::\n"
        "    # test_name_that_does_not_exist_at_all\n",
    )
    assert _findings(repo, source) == [
        "tests/unit/test_widget.py::test_name_that_does_not_exist_at_all"
    ]


# --------------------------------------------------------------------------
# Minor 14: a baselined row's ambiguity note must not re-grandfather itself
# --------------------------------------------------------------------------


def test_baseline_drift_survives_a_third_same_named_definition(repo: Path) -> None:
    """A fixed-then-ambiguous citation stays reported, not silently absorbed.

    Reproduced in three steps in the D-2 final review: (1) a row baselined
    while no such test exists is clean; (2) one real ``test_ghost_case`` is
    written, and the row correctly flags as no-longer-stale; (3) a *second*
    ``test_ghost_case`` appears in another module, and the ambiguity note
    this produces was, before the fix, folding back into ``actual`` and
    silencing the baseline-drift report. This test starts from step 3
    directly: the row must still be reported as no-longer-stale, and the
    ambiguity note must still be visible alongside it.
    """
    _write_source(
        repo, "def test_ghost_case() -> None:\n    pass\n", name="tests/unit/test_a.py"
    )
    _write_source(
        repo, "def test_ghost_case() -> None:\n    pass\n", name="tests/unit/test_b.py"
    )
    source = _write_source(repo, "# #VERIFY: test_ghost_case proves it.\nX = 1\n")
    baseline = _MODULE.load_baseline(
        _baseline(
            repo, '[python]\n"src/thing.py" = ["test_ghost_case"]\n[typescript]\n'
        )
    )
    index = _MODULE.build_index(repo)
    findings = _MODULE.run(repo, [source], baseline, index)
    kinds = sorted((f.kind, f.citation) for f in findings)
    assert kinds == [("baseline", "test_ghost_case"), ("note", "test_ghost_case")]


# --------------------------------------------------------------------------
# Minor 19: a citation naming a non-test-shaped file is checked, not dropped
# --------------------------------------------------------------------------


def test_citation_naming_a_nonexistent_non_test_shaped_file_is_stale(
    repo: Path,
) -> None:
    """A path whose basename is not ``test_*``/``*_test`` is still validated.

    Before the fix, ``foo.py::test_bar_ghost`` failed the citation regex's
    path group outright (the basename does not look like a test module),
    so the match fell through to a bare-name check on ``test_bar_ghost``
    alone, discarding the file half with no note (Minor 19 in the D-2 final
    review). ``tests/unit/foo.py`` does not exist at all here, and neither
    does a bare ``test_bar_ghost`` anywhere, so this also fails before the
    fix in a different way (as a bare-name miss) than after it (as a
    missing-file citation): the assertion pins the post-fix citation text.
    """
    source = _write_source(repo, "# #VERIFY: tests/unit/foo.py::test_bar_ghost\n")
    assert _findings(repo, source) == ["tests/unit/foo.py"]


def test_citation_naming_a_real_non_test_shaped_file_does_not_leak_to_a_lookalike(
    repo: Path,
) -> None:
    """A non-test-shaped file citation must not resolve via an unrelated module.

    ``tests/unit/foo.py`` exists and really does define ``test_bar``, but
    ``foo.py`` is not a name pytest would ever collect (it matches neither
    ``test_*.py`` nor ``*_test.py``), so it is not in the repo index's test
    paths. A second, unrelated module also defines ``test_bar``. Before the
    fix, the path half of ``foo.py::test_bar`` was invisible to the citation
    regex, so the citation matched as a bare ``test_bar`` and silently
    resolved against the unrelated module instead of the file the author
    actually named. After the fix, the path is recognised, found not to be
    a real test file, and reported: it must not fall back to the lookalike.
    """
    _write_source(repo, "def test_bar() -> None:\n    pass\n", name="tests/unit/foo.py")
    _write_source(
        repo,
        "def test_bar() -> None:\n    pass\n",
        name="tests/unit/test_unrelated.py",
    )
    source = _write_source(repo, "# #VERIFY: tests/unit/foo.py::test_bar\n")
    assert _findings(repo, source) == ["tests/unit/foo.py"]
