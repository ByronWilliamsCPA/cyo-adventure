"""Unit tests for scripts/check_work_linkage.py.

scripts/ is not an importable package (no __init__.py, by design; see per-file-ignores INP for
scripts/**/*.py in pyproject.toml), so the module is loaded directly from its file path via
importlib, matching tests/unit/test_check_lessons_log.py.

Covers every failure mode the linkage contract in
docs/planning/unscheduled-work-register.md#the-linkage-contract names, against small inline
fixtures, plus a full happy-path construction and the real repository documents. The real-document
test pins the *current* state of the real documents, which as of the 2026-07-28 sweep is clean
(zero problems); CLAUDE.md forbids editing docs/ to make a check pass, so this test asserts what
the documents already are rather than papering over a gap. If the documents later drift and this
test starts failing, that is a real finding to fix in the documents (or a pin to update once fixed),
not a test bug.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    """Load a scripts/ module from its file path.

    Args:
        name: The module's file stem under scripts/.

    Returns:
        ModuleType: The imported module.
    """
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load("check_work_linkage")

# A roadmap excerpt whose headings declare exactly the hardcoded product-phase vocabulary
# (0, 1, 2, 2b, 3, 4a, 4b, 4c, 4d, 5), mirroring the real roadmap.md's heading shapes: most phases
# are "## Phase <N>" headings, 2b is a "### Phase 2b" sub-heading, and 4a/4b appear only inside
# "### Deliverables (4a, ...)" / "(4b, ...)" nested under Phase 4's own heading.
_VALID_ROADMAP = """\
## Phase 0: Implementation gate

## Phase 1: Schema, runtime, and reader MVP

## Phase 2: Validation gate and authoring pipeline

### Phase 2b (closed)

## Phase 3: Safety and review workflow

## Phase 4: Library, profiles, editor, and engagement

### Deliverables (4a, in R1)

### Deliverables (4b, after R1)

## Phase 4c: Family loops

## Phase 4d: Connections and recommendations

## Phase 5: Hardening and deploy
"""

# A roadmap that additionally carries the "Where every open register item lands" mapping
# section the capability-register check searches. `K1` sits inside the mapping table (a citation);
# `K9` sits in the prose before the heading, outside the section's start/end bounds, so a test can
# prove the search is scoped to the section and not the whole document. The `## Appendix` heading
# closes the section without introducing a new "## Phase <N>" heading, which would otherwise trip
# the roadmap vocabulary-drift check unrelated to what these tests exercise.
_ROADMAP_WITH_MAPPING = (
    _VALID_ROADMAP
    + """
K9 is mentioned here, outside the mapping section, and must not count as a citation.

### Where every open register item lands

| Register items | Phase |
|----------------|-------|
| K1 kid-facing thing | 4b |

## Appendix

Nothing relevant here.
"""
)


def _write(path: Path, content: str) -> Path:
    """Write text to a file and return its path, for compact fixture setup.

    Args:
        path: The file to write.
        content: The text to write.

    Returns:
        Path: The same path, for chaining into a function call.
    """
    path.write_text(content, encoding="utf-8")
    return path


_PLACEHOLDER_CLUSTER = "## Cluster A: ADR follow-ons\n\n| ID | Item | Phase | Status |\n| --- | --- | --- | --- |\n"


def _register(*clusters: str) -> str:
    """Join cluster fragments under the linkage-contract heading, like the real register.

    Called with no arguments, produces one header-only, data-row-free cluster (a bare
    ``## Cluster A:`` table) rather than a document with no cluster tables at all, so tests that
    only care about the roadmap/debt/lessons checks are not tripped up by the separate "no
    cluster tables found" guard; that guard has its own dedicated test.

    Args:
        clusters: Zero or more already-formatted ``## Cluster <letter>: ...`` sections.

    Returns:
        str: The assembled register text.
    """
    sections = clusters or (_PLACEHOLDER_CLUSTER,)
    return "# Unscheduled Work Register\n\n" + "\n\n".join(sections) + "\n"


_CAPABILITY_TABLE_HEADER = (
    "| ID | Capability | Docs | Notes |\n| --- | --- | --- | --- |\n"
)


def _write_no_open_capability_register(tmp_path: Path) -> Path:
    """Write a header-only capability register, so it never reports an open id.

    Most tests in this file are not about the capability-register check; they want a fifth
    ``check_linkage`` argument that stays silent so they keep testing only what they were written
    to test.

    Args:
        tmp_path: The pytest ``tmp_path`` fixture's directory.

    Returns:
        Path: The written file's path.
    """
    return _write(tmp_path / "capability.md", _CAPABILITY_TABLE_HEADER)


# ---------------------------------------------------------------------------
# A.1 id format
# ---------------------------------------------------------------------------


def test_check_row_id_accepts_well_formed_id() -> None:
    """A cluster-letter-matching, two-digit id passes."""
    assert _MODULE._check_row_id("A", 10, "UW-A01") == []


def test_check_row_id_rejects_malformed_id() -> None:
    """An id missing the zero-padded two digits fails with a message naming it."""
    problems = _MODULE._check_row_id("A", 10, "UW-A1")
    assert len(problems) == 1
    assert "UW-A1" in problems[0]
    assert "does not match UW-[A-M]NN" in problems[0]


def test_check_row_id_rejects_id_filed_under_the_wrong_cluster() -> None:
    """A well-formed id whose letter does not match the cluster table it was found in fails.

    A row copy-pasted between clusters (or a typo'd id, e.g. 'UW-A01' inside the Cluster B
    table) previously passed the id-format check silently, since it only validated the regex
    shape and never compared the id's own letter against the cluster it was found in.
    """
    problems = _MODULE._check_row_id("B", 10, "UW-A01")
    assert len(problems) == 1
    assert "UW-A01" in problems[0]
    assert "belongs to cluster 'A'" in problems[0]
    assert "cluster 'B' table" in problems[0]


def test_check_row_id_accepts_id_matching_its_cluster() -> None:
    """A well-formed id whose letter matches the cluster table it was found in still passes."""
    assert _MODULE._check_row_id("B", 10, "UW-B01") == []


def test_check_linkage_reports_malformed_id_in_a_cluster_table(tmp_path: Path) -> None:
    """A malformed id inside a real cluster table is caught end to end."""
    register = _register(
        "## Cluster A: ADR follow-ons\n\n"
        "| ID | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A1 | Bad id | 5 | unscheduled |\n"
    )
    register_path = _write(tmp_path / "register.md", register)
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert any("does not match UW-[A-M]NN" in problem for problem in problems)


# ---------------------------------------------------------------------------
# A.2 status vocabulary
# ---------------------------------------------------------------------------


def test_check_row_status_accepts_known_status() -> None:
    """Each of the five documented statuses passes."""
    for status in ("unscheduled", "blocked", "decision", "verify", "done"):
        assert _MODULE._check_row_status("A", 1, "UW-A01", status) == []


def test_check_row_status_rejects_unknown_status() -> None:
    """A status outside the closed vocabulary fails, naming the bad value."""
    problems = _MODULE._check_row_status("A", 1, "UW-A01", "done (this change)")
    assert len(problems) == 1
    assert "done (this change)" in problems[0]


# ---------------------------------------------------------------------------
# A.3 phase vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phase",
    [
        "0",
        "2b",
        "4a",
        "5",
        "6",
        "9",
        "R1",
        "R3",
        "content",
        "now",
        "CI hygiene",
        "doc",
        "recurring",
        "post-launch",
        "M0",
        "M7",
        "M4.1",
        "external:homelab-infra",
        "issue:460",
    ],
)
def test_check_row_phase_accepts_every_vocabulary_form(phase: str) -> None:
    """Every category of the closed phase vocabulary is accepted."""
    assert _MODULE._check_row_phase("A", 1, "UW-A01", phase, "unscheduled") == []


def test_check_row_phase_rejects_value_outside_vocabulary() -> None:
    """A phase spelled outside the closed vocabulary fails."""
    problems = _MODULE._check_row_phase("A", 1, "UW-A01", "42", "unscheduled")
    assert len(problems) == 1
    assert "not in the closed phase vocabulary" in problems[0]


# ---------------------------------------------------------------------------
# A.4 comma-separated phase
# ---------------------------------------------------------------------------


def test_check_row_phase_rejects_comma_separated_value() -> None:
    """A Phase column holding more than one value is rejected."""
    problems = _MODULE._check_row_phase("A", 1, "UW-A01", "4b, 5", "unscheduled")
    assert len(problems) == 1
    assert "more than one" in problems[0]


# ---------------------------------------------------------------------------
# A.5 phase repeating a status value
# ---------------------------------------------------------------------------


def test_check_row_phase_rejects_phase_equal_to_a_status() -> None:
    """A Phase column that just repeats a Status word is rejected."""
    problems = _MODULE._check_row_phase("A", 1, "UW-A01", "blocked", "decision")
    assert len(problems) == 1
    assert "repeats a Status value" in problems[0]


# ---------------------------------------------------------------------------
# A.6 empty phase
# ---------------------------------------------------------------------------


def test_check_row_phase_rejects_empty_phase_on_unscheduled_row() -> None:
    """An empty Phase on an unscheduled row is the one disallowed empty case."""
    problems = _MODULE._check_row_phase("A", 1, "UW-A01", "", "unscheduled")
    assert len(problems) == 1
    assert "Phase is empty" in problems[0]


def test_check_row_phase_allows_empty_phase_on_a_non_unscheduled_row() -> None:
    """An empty Phase is fine on blocked/decision/verify/done rows.

    Those dispositions carry their own required evidence (a named blocker, an owner, what to
    check, or a citation), not necessarily a Phase; the contract's "Not allowed" list singles out
    only the unscheduled case for an empty Phase.
    """
    assert _MODULE._check_row_phase("A", 1, "UW-A01", "", "blocked") == []


# ---------------------------------------------------------------------------
# A.7 id uniqueness across the whole register
# ---------------------------------------------------------------------------


def test_check_linkage_reports_duplicate_id_across_clusters(tmp_path: Path) -> None:
    """The same id used in two different clusters is a build failure, not a coincidence."""
    register = _register(
        "## Cluster A: ADR follow-ons\n\n"
        "| ID | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A01 | First use | 5 | unscheduled |\n",
        "## Cluster B: debt-register phase linkage\n\n"
        "| ID | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A01 | Reused id | 5 | unscheduled |\n",
    )
    register_path = _write(tmp_path / "register.md", register)
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert any("used on 2 rows" in problem for problem in problems)


# ---------------------------------------------------------------------------
# Clusters with no Phase column (L and M)
# ---------------------------------------------------------------------------


def test_check_linkage_skips_phase_checks_for_a_phase_less_cluster(
    tmp_path: Path,
) -> None:
    """Cluster L/M-shaped tables (no Phase column) still check id and Status only."""
    register = _register(
        "## Cluster L: live defects\n\n"
        "| ID | Item | Issue | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-L01 | A bug | #460 | unscheduled |\n"
    )
    register_path = _write(tmp_path / "register.md", register)
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


# ---------------------------------------------------------------------------
# B. vocabulary drift guard
# ---------------------------------------------------------------------------


def test_extract_roadmap_product_phases_matches_the_hardcoded_vocabulary_on_valid_input() -> (
    None
):
    """The roadmap parser derives exactly the hardcoded product-phase set from a valid roadmap."""
    assert (
        _MODULE._extract_roadmap_product_phases(_VALID_ROADMAP)
        == _MODULE._PRODUCT_PHASES
    )


def test_extract_roadmap_product_phases_excludes_the_bare_phase_4_container() -> None:
    """Phase 4's own heading is a container for 4a/4b, not a schedulable token on its own."""
    assert "4" not in _MODULE._extract_roadmap_product_phases(_VALID_ROADMAP)


def test_check_linkage_reports_drift_when_roadmap_drops_a_phase_heading(
    tmp_path: Path,
) -> None:
    """A roadmap missing one of its Phase headings is reported as vocabulary drift."""
    roadmap_missing_phase_5 = _VALID_ROADMAP.replace(
        "## Phase 5: Hardening and deploy\n", ""
    )
    register_path = _write(tmp_path / "register.md", _register())
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", roadmap_missing_phase_5),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    drift = [p for p in problems if "vocabulary drift" in p]
    assert len(drift) == 1
    assert "5" in drift[0]


def test_check_linkage_reports_drift_when_roadmap_adds_an_unrecognised_phase(
    tmp_path: Path,
) -> None:
    """A roadmap heading for a phase the hardcoded vocabulary does not know is also drift."""
    roadmap_with_extra_phase = _VALID_ROADMAP + "\n## Phase 10: A future phase\n"
    register_path = _write(tmp_path / "register.md", _register())
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", roadmap_with_extra_phase),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    drift = [p for p in problems if "vocabulary drift" in p]
    assert len(drift) == 1
    assert "10" in drift[0]


# ---------------------------------------------------------------------------
# C.1 debt-register linkage
# ---------------------------------------------------------------------------

_DEBT_TABLE_HEADER = "| # | Debt | Source | Severity | Suggested action |\n| --- | --- | --- | --- | --- |\n"


def test_check_linkage_reports_uncited_open_debt_id(tmp_path: Path) -> None:
    """An open (not [Closed]) debt id absent from cluster B is an orphan."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster B: debt-register phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-B01 | Nothing relevant to that debt here | 5 | unscheduled |\n"
        ),
    )
    debt_path = _write(
        tmp_path / "debt.md",
        _DEBT_TABLE_HEADER + "| C1 | Uncited debt | src | Medium | fix it |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert any(
        "debt 'C1'" in problem and "not cited" in problem for problem in problems
    )


def test_check_linkage_accepts_debt_id_cited_in_cluster_b(tmp_path: Path) -> None:
    """A debt id named in cluster B's Item text satisfies the linkage obligation."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster B: debt-register phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-B01 | Covers `C1` directly | 5 | unscheduled |\n"
        ),
    )
    debt_path = _write(
        tmp_path / "debt.md",
        _DEBT_TABLE_HEADER + "| C1 | Cited debt | src | Medium | fix it |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


def test_check_linkage_treats_closed_debt_rows_as_satisfied(tmp_path: Path) -> None:
    """A debt row marked [Closed] needs no citation at all."""
    register_path = _write(tmp_path / "register.md", _register())
    debt_path = _write(
        tmp_path / "debt.md",
        _DEBT_TABLE_HEADER + "| C1 | **[Closed]** done | src | Medium | none |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


def test_check_linkage_treats_resolved_debt_rows_as_satisfied(tmp_path: Path) -> None:
    """A debt row marked [Resolved] needs no citation, exactly like [Closed].

    The real debt register uses both markers interchangeably (per its own contract wording in
    unscheduled-work-register.md), so the check must honour both rather than only [Closed]; an
    earlier version of this check treated [Resolved] rows as still-open, producing false
    positives on every genuinely closed debt using that marker.
    """
    register_path = _write(tmp_path / "register.md", _register())
    debt_path = _write(
        tmp_path / "debt.md",
        _DEBT_TABLE_HEADER + "| C1 | **[Resolved]** by PR #1 | src | Medium | none |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


def test_check_linkage_expands_a_through_range_citation(tmp_path: Path) -> None:
    """ "`SL1` through `SL10`" style phrasing cites every id in the range, not just the ends."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster B: debt-register phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-B01 | `SL1` through `SL10`, the ten deferrals | 6 | unscheduled |\n"
        ),
    )
    rows = "".join(
        f"| SL{n} | Deferral {n} | src | Low | fix |\n" for n in range(1, 11)
    )
    debt_path = _write(tmp_path / "debt.md", _DEBT_TABLE_HEADER + rows)
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


def test_extract_citations_rejects_an_absurdly_wide_through_range() -> None:
    """A "through" range spanning far more ids than any real citation would name (a likely
    typo, e.g. a transposed digit) fails loud rather than silently manufacturing thousands of
    ids nobody actually cited."""
    with pytest.raises(ValueError, match="sanity bound"):
        _MODULE._extract_citations("`SL1` through `SL9999`", _MODULE._DEBT_ID_RE)


def test_debt_register_open_ids_excludes_lettered_sub_item_ids() -> None:
    """A decorated id like U9a is not one of the debt-id families the contract names."""
    lines = (
        _DEBT_TABLE_HEADER + "| U9a | A dark-mode polish item | src | Low | none |\n"
    ).splitlines()
    assert _MODULE._debt_register_open_ids(lines) == {}


def test_debt_register_open_ids_ignores_closed_marker_outside_the_debt_cell() -> None:
    """'[Closed]'/'[Resolved]' text in another row's Source or Suggested-action cell does not
    close this row.

    The marker match used to join every cell before searching, so a still-open row whose
    'Suggested action' cell happened to read something like 'do this once C1 is [Closed]' was
    wrongly counted as closed. The marker is only meaningful in the Debt cell (index 1).
    """
    lines = (
        _DEBT_TABLE_HEADER
        + "| C1 | Still genuinely open | see [Closed] PR discussion | Medium |"
        " do this once related work is [Resolved] |\n"
    ).splitlines()
    assert _MODULE._debt_register_open_ids(lines) == {"C1": 3}


# ---------------------------------------------------------------------------
# C.2 authoring-lessons-log linkage
# ---------------------------------------------------------------------------

_LESSONS_TABLE_HEADER = (
    "| ID | Date | Source | Category | Lesson | Proposed change | Status | Ref |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


def test_check_linkage_reports_uncited_open_lesson(tmp_path: Path) -> None:
    """An open lesson absent from cluster C is an orphan."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster C: authoring-lessons phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-C01 | Nothing relevant to that lesson here | now | unscheduled |\n"
        ),
    )
    lessons_path = _write(
        tmp_path / "lessons.md",
        _LESSONS_TABLE_HEADER
        + "| AL-001 | 2026-01-01 | run | tooling | a lesson | a change | open | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        lessons_path,
        _write_no_open_capability_register(tmp_path),
    )
    assert any(
        "lesson 'AL-001'" in problem and "not cited" in problem for problem in problems
    )


def test_check_linkage_accepts_lesson_cited_in_cluster_c(tmp_path: Path) -> None:
    """A lesson id named in cluster C's Item text satisfies the linkage obligation."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster C: authoring-lessons phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-C01 | Tracks `AL-001` | now | unscheduled |\n"
        ),
    )
    lessons_path = _write(
        tmp_path / "lessons.md",
        _LESSONS_TABLE_HEADER
        + "| AL-001 | 2026-01-01 | run | tooling | a lesson | a change | open | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        lessons_path,
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


@pytest.mark.parametrize("status", ["applied", "rejected", "superseded"])
def test_check_linkage_treats_closed_lesson_statuses_as_satisfied(
    tmp_path: Path, status: str
) -> None:
    """A lesson whose status already asserts closure needs no citation."""
    register_path = _write(tmp_path / "register.md", _register())
    lessons_path = _write(
        tmp_path / "lessons.md",
        _LESSONS_TABLE_HEADER
        + f"| AL-001 | 2026-01-01 | run | tooling | a lesson | a change | {status} | ref |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        lessons_path,
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


def test_check_linkage_reports_a_lessons_log_with_content_but_no_locatable_header(
    tmp_path: Path,
) -> None:
    """A lessons log with table-like content but a header that no longer starts with 'ID' and
    'Status' fails loud instead of silently reporting zero open lessons.

    Before this check existed, ``_lessons_needing_citation`` returned an empty dict whenever the
    header could not be located, so a renamed 'Status' column (or a header row dropped entirely)
    made every open lesson invisible to the linkage check while ``check_linkage`` still reported
    success on this document.
    """
    register_path = _write(tmp_path / "register.md", _register())
    lessons_path = _write(
        tmp_path / "lessons.md",
        "| ID | Date | Source | Category | Lesson | Proposed change | State | Ref |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| AL-001 | 2026-01-01 | run | tooling | a lesson | a change | open | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        lessons_path,
        _write_no_open_capability_register(tmp_path),
    )
    assert len(problems) == 1
    assert "lessons.md" in problems[0]
    assert "no table header with 'ID' and 'Status' columns found" in problems[0]


def test_lessons_needing_citation_returns_no_rows_for_a_genuinely_empty_document() -> (
    None
):
    """A document with no table-like content at all (not yet holding a table) is not the
    malformed-header failure mode; it has nothing to report and does not raise."""
    assert _MODULE._lessons_needing_citation([]) == {}


# ---------------------------------------------------------------------------
# C.3 capability-register linkage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("glyph", ["\U0001f7e1", "❌"])
def test_check_linkage_reports_open_capability_missing_from_mapping_section(
    tmp_path: Path, glyph: str
) -> None:
    """A capability marked open (either open glyph) and absent from the mapping is an orphan."""
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + f"| K9 | Shelf presentation | {glyph} | notes |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert any(
        "capability 'K9'" in problem
        and "Where every open register item lands" in problem
        for problem in problems
    )


def test_check_linkage_accepts_open_capability_cited_in_mapping_section(
    tmp_path: Path,
) -> None:
    """An open capability named inside the mapping section satisfies the linkage obligation."""
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K1 | Kid-facing thing | \U0001f7e1 | notes |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert problems == []


def test_check_linkage_treats_done_capability_as_satisfied(tmp_path: Path) -> None:
    """A capability already marked done (✅) needs no mapping citation, even if absent."""
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K9 | Shelf presentation | ✅ | notes |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert problems == []


def test_check_linkage_ignores_capability_citation_outside_mapping_section(
    tmp_path: Path,
) -> None:
    """A mention elsewhere in roadmap.md does not satisfy the obligation; only the section counts.

    `_ROADMAP_WITH_MAPPING` mentions `K9` in prose before the "Where every open register item
    lands" heading, outside the section's start/end bounds. If the search were not scoped to the
    section, this citation would wrongly satisfy the check.
    """
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K9 | Shelf presentation | ❌ | notes |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert any("capability 'K9'" in problem for problem in problems)


def test_check_linkage_reports_unreadable_capability_register_but_still_runs_other_checks(
    tmp_path: Path,
) -> None:
    """A missing capability register is reported without suppressing the other checks."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster B: debt-register phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-B01 | Covers `C1` | 5 | unscheduled |\n"
        ),
    )
    debt_path = _write(
        tmp_path / "debt.md",
        _DEBT_TABLE_HEADER + "| C2 | Uncited | src | Low | fix |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        tmp_path / "missing-capability.md",
    )
    assert any("cannot read" in problem for problem in problems)
    assert any("debt 'C2'" in problem for problem in problems)


def test_capability_register_open_ids_marks_open_glyph_rows_open_and_done_rows_closed() -> (
    None
):
    """Both open glyphs (\U0001f7e1, ❌) count as open; the done mark (✅) does not."""
    lines = (
        _CAPABILITY_TABLE_HEADER
        + "| K1 | Yellow | \U0001f7e1 | |\n"
        + "| K2 | Red | ❌ | |\n"
        + "| K3 | Done | ✅ | |\n"
    ).splitlines()
    open_ids = _MODULE._capability_register_open_ids(lines)
    assert set(open_ids) == {"K1", "K2"}


def test_capability_register_open_ids_tracks_each_of_the_four_tables_independently() -> (
    None
):
    """The K/G/A/S tables each re-declare their own header; a later header's index is used."""
    lines = (
        "## K: kid experience\n\n"
        + _CAPABILITY_TABLE_HEADER
        + "| K1 | Kid thing | \U0001f7e1 | |\n"
        + "\n## G: guardian experience\n\n"
        + _CAPABILITY_TABLE_HEADER
        + "| G1 | Guardian thing | ✅ | |\n"
    ).splitlines()
    open_ids = _MODULE._capability_register_open_ids(lines)
    assert set(open_ids) == {"K1"}


def test_capability_register_open_ids_rejects_content_with_no_locatable_header() -> (
    None
):
    """Table-like content with no row starting 'ID' and containing 'Docs' fails loud.

    Before this check existed, a renamed 'Docs' column (or a header row dropped entirely)
    silently returned an empty dict, so the capability-register linkage check reported every
    row as satisfied purely because it never actually found any of them.
    """
    lines = (
        "| ID | Capability | State | Notes |\n"
        "| --- | --- | --- | --- |\n"
        "| K1 | Kid thing | open | |\n"
    ).splitlines()
    with pytest.raises(
        LookupError, match="no table header with 'ID' and 'Docs' columns"
    ):
        _MODULE._capability_register_open_ids(lines)


def test_capability_register_open_ids_rejects_one_corrupted_table_among_valid_others() -> (
    None
):
    """A single table's header corrupted while the other three stay valid still fails loud.

    Caught live against a deliberately-malformed copy of the real capability-register.md: an
    earlier version of this fix only raised when zero headers were found anywhere in the
    document, so renaming just the K table's 'Docs' column (leaving G/A/S intact) still made
    'tables_found' positive and every one of K's open rows silently vanished with the check
    reporting success. A capability-shaped row (matches '[KGAS]NN') found with no header
    located for its table is now itself the failure signal, independent of how many other
    tables in the document are fine.
    """
    lines = (
        "## K: kid experience\n\n"
        "| ID | Capability | State | Notes |\n"
        "| --- | --- | --- | --- |\n"
        "| K1 | Kid thing | \U0001f7e1 | |\n"
        "\n## G: guardian experience\n\n"
        + _CAPABILITY_TABLE_HEADER
        + "| G1 | Guardian thing | \U0001f7e1 | |\n"
    ).splitlines()
    with pytest.raises(LookupError, match=r"K1 \(line 5\)"):
        _MODULE._capability_register_open_ids(lines)


def test_capability_register_open_ids_returns_no_rows_for_a_genuinely_empty_document() -> (
    None
):
    """A document with no table-like content at all is not the malformed-header failure mode;
    it has nothing to report and does not raise."""
    assert _MODULE._capability_register_open_ids([]) == {}


def test_check_linkage_reports_a_capability_register_with_no_locatable_header(
    tmp_path: Path,
) -> None:
    """The malformed-header failure surfaces end to end through check_linkage as a problem."""
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        "| ID | Capability | State | Notes |\n"
        "| --- | --- | --- | --- |\n"
        "| K1 | Kid thing | open | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert len(problems) == 1
    assert "capability.md" in problems[0]
    assert "no table header with 'ID' and 'Docs' columns found" in problems[0]


def test_check_linkage_reports_a_register_with_no_cluster_tables(
    tmp_path: Path,
) -> None:
    """A register with no '## Cluster <letter>:' table at all is its own hard failure."""
    register_path = _write(
        tmp_path / "register.md", "# Unscheduled Work Register\n\nNo clusters here.\n"
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert len(problems) == 1
    assert "no '## Cluster <letter>:' tables found" in problems[0]


def test_check_linkage_reports_a_cluster_heading_with_no_locatable_id_header(
    tmp_path: Path,
) -> None:
    """A '## Cluster' heading whose table header row is missing or malformed fails loud.

    Before this check existed, ``_find_clusters`` silently dropped a cluster it could not
    locate a header for, so the entire cluster's rows (and any real problems in them) went
    unvalidated while ``check_linkage`` still reported success. A heading with prose but no
    ``| ID | ... |`` row underneath must surface as a problem, not disappear.
    """
    register_path = _write(
        tmp_path / "register.md",
        "# Unscheduled Work Register\n\n"
        "## Cluster A: ADR follow-ons\n\n"
        "This cluster's table header got renamed and no longer starts with 'ID'.\n\n"
        "| Ident | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A01 | Something | 5 | unscheduled |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert len(problems) == 1
    assert "cluster(s) A" in problems[0]
    assert "no locatable 'ID' table header" in problems[0]


# ---------------------------------------------------------------------------
# Missing files
# ---------------------------------------------------------------------------


def test_check_linkage_reports_unreadable_register_and_stops(tmp_path: Path) -> None:
    """A missing register is a single problem; nothing downstream is attempted."""
    problems = _MODULE.check_linkage(
        tmp_path / "does-not-exist.md",
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert len(problems) == 1
    assert "cannot read" in problems[0]


def test_check_linkage_reports_a_register_with_invalid_utf8_bytes(
    tmp_path: Path,
) -> None:
    """A register file that is not valid UTF-8 is reported as unreadable, not an unhandled
    crash.

    'UnicodeDecodeError' is a 'ValueError' subclass, not an 'OSError' subclass, so
    '_read_lines' catching only 'OSError' let a bad-encoding file raise straight through
    'check_linkage' instead of being reported like any other unreadable document.
    """
    register_path = tmp_path / "register.md"
    register_path.write_bytes(
        b"# Unscheduled Work Register\n\xff\xfe not valid utf-8\n"
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert len(problems) == 1
    assert "cannot read" in problems[0]


def test_check_linkage_reports_unreadable_roadmap_but_still_runs_other_checks(
    tmp_path: Path,
) -> None:
    """A missing roadmap only skips the vocabulary-drift check, not everything else."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster B: debt-register phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-B01 | Covers `C1` | 5 | unscheduled |\n"
        ),
    )
    debt_path = _write(
        tmp_path / "debt.md",
        _DEBT_TABLE_HEADER + "| C2 | Uncited | src | Low | fix |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        tmp_path / "missing-roadmap.md",
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert any("cannot read" in problem for problem in problems)
    assert any("debt 'C2'" in problem for problem in problems)


# ---------------------------------------------------------------------------
# Full happy path
# ---------------------------------------------------------------------------


def test_check_linkage_passes_on_a_fully_linked_construction(tmp_path: Path) -> None:
    """A minimal but complete, correctly linked document set yields zero problems."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster A: ADR follow-ons\n\n"
            "| ID | Item | ADR | Phase | Status |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| UW-A01 | Do the thing | 021 | 5 | unscheduled |\n",
            "## Cluster B: debt-register phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-B01 | Covers `C1` and `T1` | 5 | unscheduled |\n",
            "## Cluster C: authoring-lessons phase linkage\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-C01 | Tracks `AL-001` | now | unscheduled |\n",
            "## Cluster L: live defects\n\n"
            "| ID | Item | Issue | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-L01 | A bug | #1 | unscheduled |\n",
        ),
    )
    debt_path = _write(
        tmp_path / "debt.md",
        _DEBT_TABLE_HEADER
        + "| C1 | Some debt | src | Low | fix |\n"
        + "| T1 | Some other debt | src | Low | fix |\n",
    )
    lessons_path = _write(
        tmp_path / "lessons.md",
        _LESSONS_TABLE_HEADER
        + "| AL-001 | 2026-01-01 | run | tooling | a lesson | a change | open | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        debt_path,
        lessons_path,
        _write_no_open_capability_register(tmp_path),
    )
    assert problems == []


# ---------------------------------------------------------------------------
# main() / CLI contract
# ---------------------------------------------------------------------------


def test_main_returns_zero_and_prints_ok_on_a_clean_construction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean document set exits 0 and prints an ok summary line."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster A: ADR follow-ons\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-A01 | Do the thing | 5 | unscheduled |\n"
        ),
    )
    roadmap_path = _write(tmp_path / "roadmap.md", _VALID_ROADMAP)
    debt_path = _write(tmp_path / "debt.md", "")
    lessons_path = _write(tmp_path / "lessons.md", "")
    capability_path = _write_no_open_capability_register(tmp_path)

    exit_code = _MODULE.main(
        [
            "--register",
            str(register_path),
            "--roadmap",
            str(roadmap_path),
            "--debt-register",
            str(debt_path),
            "--lessons-log",
            str(lessons_path),
            "--capability-register",
            str(capability_path),
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ok:" in out
    assert "A=1" in out


def test_main_returns_one_and_prints_fail_on_a_broken_construction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken document set exits 1 and lists every problem, one per line."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster A: ADR follow-ons\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-A01 | Bad status | 5 | not-a-real-status |\n"
        ),
    )
    exit_code = _MODULE.main(
        [
            "--register",
            str(register_path),
            "--roadmap",
            str(_write(tmp_path / "roadmap.md", _VALID_ROADMAP)),
            "--debt-register",
            str(_write(tmp_path / "debt.md", "")),
            "--lessons-log",
            str(_write(tmp_path / "lessons.md", "")),
            "--capability-register",
            str(_write_no_open_capability_register(tmp_path)),
        ]
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL ")
    assert "not-a-real-status" in out


def test_main_exits_two_on_argparse_usage_error() -> None:
    """An unrecognised flag is an argparse usage error, exit code 2."""
    with pytest.raises(SystemExit) as exc_info:
        _MODULE.main(["--not-a-real-flag"])
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# The real repository documents
# ---------------------------------------------------------------------------

# As of the 2026-07-28 sweep, the real planning documents satisfy the linkage contract cleanly:
# UW-A41's status was corrected, UW-B17/UW-B18/UW-C19 were added to cite debts GS2/T7 and lesson
# AL-023, and roadmap.md's "Where every open register item lands" section was extended to cover
# every open capability-register id. Per CLAUDE.md, docs/ is never edited by this test suite just
# to make a check pass; this assertion reflects work already done in the documents themselves, not
# a suppression here. If a new gap appears (a document changes, or the checker gains a new rule),
# this test is the regression signal; update it in the same change that fixes or re-pins the gap.
_KNOWN_REAL_REPO_PROBLEMS: frozenset[str] = frozenset()


def test_check_linkage_against_the_real_repository_documents() -> None:
    """The real planning documents currently satisfy the linkage contract with zero problems.

    The value of the test is catching *new* drift (an orphan appearing in the real documents
    without a corresponding test-suite update), not asserting a fixed non-empty gap set.
    """
    problems = _MODULE.check_linkage(
        _MODULE._DEFAULT_REGISTER,
        _MODULE._DEFAULT_ROADMAP,
        _MODULE._DEFAULT_DEBT_REGISTER,
        _MODULE._DEFAULT_LESSONS_LOG,
        _MODULE._DEFAULT_CAPABILITY_REGISTER,
    )
    assert set(problems) == _KNOWN_REAL_REPO_PROBLEMS


def test_main_against_the_real_repository_documents_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI over the real, default paths currently exits 0, matching check_linkage directly."""
    exit_code = _MODULE.main([])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("ok:")
