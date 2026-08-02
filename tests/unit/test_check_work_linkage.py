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
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

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


# A minimal but complete plan-manifest.toml fixture whose track-1 phase set matches
# _VALID_ROADMAP's declared headings exactly, so manifest-focused tests can construct their own
# isolated manifest without depending on (or drifting from) the real plan-manifest.toml.
_VALID_MANIFEST = """\
schema_version = 1

[status_vocabulary]
"yes/yes" = "delivered"
"yes/partial" = "substantially delivered"
"partial/partial" = "partially delivered"
"no/no" = "not started"

[rungs.R1]
requires_phases = ["0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5"]

[rungs.R2]
requires_phases = ["0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5", "6"]
excludes_phases = ["7"]

[rungs.R3]
requires_phases = ["0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5", "6", "7"]

[phases."0"]
track = 1
shipped = "yes"
usable = "yes"

[phases."1"]
track = 1
shipped = "yes"
usable = "yes"

[phases."2"]
track = 1
shipped = "yes"
usable = "yes"

[phases."2b"]
track = 1
shipped = "yes"
usable = "yes"

[phases."3"]
track = 1
shipped = "yes"
usable = "yes"

[phases."4a"]
track = 1
shipped = "yes"
usable = "yes"

[phases."4b"]
track = 1
shipped = "yes"
usable = "partial"

[phases."4c"]
track = 1
shipped = "yes"
usable = "partial"

[phases."4d"]
track = 1
shipped = "yes"
usable = "partial"

[phases."5"]
track = 1
shipped = "partial"
usable = "partial"

[phases."6"]
track = 2
shipped = "no"
usable = "no"

[phases."7"]
track = 2
shipped = "no"
usable = "no"
"""


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


def test_check_roadmap_vocabulary_accepts_matching_manifest_phases() -> None:
    """A roadmap whose headings exactly match the given manifest phase set is clean."""
    assert (
        _MODULE._check_roadmap_vocabulary(
            _VALID_ROADMAP.splitlines(),
            Path("roadmap.md"),
            frozenset({"0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5"}),
        )
        == []
    )


def test_check_roadmap_vocabulary_reports_drift_against_a_smaller_manifest_set() -> (
    None
):
    """A roadmap heading the given manifest phase set does not know about is drift."""
    problems = _MODULE._check_roadmap_vocabulary(
        _VALID_ROADMAP.splitlines(),
        Path("roadmap.md"),
        frozenset({"0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d"}),
    )
    assert len(problems) == 1
    assert "vocabulary drift" in problems[0]
    assert "5" in problems[0]


# ---------------------------------------------------------------------------
# D. plan-manifest.toml loading and phase-vocabulary derivation
# ---------------------------------------------------------------------------


def test_load_manifest_returns_parsed_toml_on_success(tmp_path: Path) -> None:
    """A well-formed manifest parses into a dict with the expected top-level tables."""
    manifest_path = _write(tmp_path / "manifest.toml", _VALID_MANIFEST)
    problems: list[str] = []
    manifest = _MODULE._load_manifest(manifest_path, problems)
    assert problems == []
    assert manifest is not None
    assert manifest["phases"]["0"]["shipped"] == "yes"


def test_load_manifest_reports_missing_file_instead_of_raising(tmp_path: Path) -> None:
    """A missing manifest is a reported problem, not a traceback."""
    problems: list[str] = []
    manifest = _MODULE._load_manifest(tmp_path / "does-not-exist.toml", problems)
    assert manifest is None
    assert len(problems) == 1
    assert "cannot read" in problems[0]


def test_load_manifest_reports_unparseable_toml_instead_of_raising(
    tmp_path: Path,
) -> None:
    """Malformed TOML is a reported problem, not a traceback."""
    manifest_path = _write(tmp_path / "manifest.toml", "not = valid = toml = [[[")
    problems: list[str] = []
    manifest = _MODULE._load_manifest(manifest_path, problems)
    assert manifest is None
    assert len(problems) == 1
    assert "cannot parse" in problems[0]


def test_manifest_phases_for_track_splits_phases_by_their_track_field(
    tmp_path: Path,
) -> None:
    """Track-1 and track-2 phase tokens are derived from each phase's own ``track`` field."""
    manifest_path = _write(tmp_path / "manifest.toml", _VALID_MANIFEST)
    manifest = _MODULE._load_manifest(manifest_path, [])
    assert manifest is not None
    assert _MODULE._manifest_phases_for_track(manifest, 1) == {
        "0",
        "1",
        "2",
        "2b",
        "3",
        "4a",
        "4b",
        "4c",
        "4d",
        "5",
    }
    assert _MODULE._manifest_phases_for_track(manifest, 2) == {"6", "7"}


def test_check_linkage_reports_unreadable_manifest_but_still_runs_other_checks(
    tmp_path: Path,
) -> None:
    """A missing manifest only skips the manifest-dependent checks, not everything else."""
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
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        debt_path,
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=tmp_path / "missing-manifest.toml",
    )
    assert any("cannot read" in problem for problem in problems)
    assert any("debt 'C2'" in problem for problem in problems)


def test_check_linkage_reports_unparseable_manifest_end_to_end(tmp_path: Path) -> None:
    """A malformed manifest surfaces through check_linkage as a reported problem."""
    register_path = _write(tmp_path / "register.md", _register())
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", "not [ valid toml"),
    )
    assert any("cannot parse" in problem for problem in problems)


# ---------------------------------------------------------------------------
# E. manifest integrity
# ---------------------------------------------------------------------------


def test_check_manifest_rung_phase_references_flags_an_unknown_phase() -> None:
    """A rung requiring a phase absent from [phases] is reported."""
    manifest = {
        "phases": {"0": {}},
        "rungs": {"R1": {"requires_phases": ["0", "9"]}},
    }
    problems = _MODULE._check_manifest_rung_phase_references(
        manifest, Path("plan-manifest.toml")
    )
    assert len(problems) == 1
    assert "R1" in problems[0]
    assert "'9'" in problems[0]


def test_check_manifest_rung_phase_references_accepts_all_declared_phases() -> None:
    """A rung whose phase lists reference only declared phases passes."""
    manifest = {
        "phases": {"0": {}, "7": {}},
        "rungs": {"R2": {"requires_phases": ["0"], "excludes_phases": ["7"]}},
    }
    assert (
        _MODULE._check_manifest_rung_phase_references(
            manifest, Path("plan-manifest.toml")
        )
        == []
    )


def test_check_manifest_rung_requires_excludes_disjoint_flags_overlap() -> None:
    """A rung listing the same phase in both requires_phases and excludes_phases is reported."""
    manifest = {
        "rungs": {"R2": {"requires_phases": ["6", "7"], "excludes_phases": ["7"]}},
    }
    problems = _MODULE._check_manifest_rung_requires_excludes_disjoint(
        manifest, Path("plan-manifest.toml")
    )
    assert len(problems) == 1
    assert "R2" in problems[0]
    assert "7" in problems[0]


def test_check_manifest_rung_requires_excludes_disjoint_accepts_disjoint_lists() -> (
    None
):
    """A rung whose requires and excludes lists share nothing passes."""
    manifest = {
        "rungs": {"R2": {"requires_phases": ["6"], "excludes_phases": ["7"]}},
    }
    assert (
        _MODULE._check_manifest_rung_requires_excludes_disjoint(
            manifest, Path("plan-manifest.toml")
        )
        == []
    )


def test_check_manifest_rung_monotonicity_flags_a_dropped_phase() -> None:
    """A higher rung that drops a phase the lower rung required is reported."""
    manifest = {
        "rungs": {
            "R1": {"requires_phases": ["0", "1"]},
            "R2": {"requires_phases": ["0"]},
            "R3": {"requires_phases": ["0", "1"]},
        }
    }
    problems = _MODULE._check_manifest_rung_monotonicity(
        manifest, Path("plan-manifest.toml")
    )
    assert len(problems) == 1
    assert "R2" in problems[0]
    assert "1" in problems[0]


def test_check_manifest_rung_monotonicity_accepts_a_monotonic_ladder() -> None:
    """R1 requires subset of R2 requires subset of R3 requires passes."""
    manifest = {
        "rungs": {
            "R1": {"requires_phases": ["0"]},
            "R2": {"requires_phases": ["0", "6"]},
            "R3": {"requires_phases": ["0", "6", "7"]},
        }
    }
    assert (
        _MODULE._check_manifest_rung_monotonicity(manifest, Path("plan-manifest.toml"))
        == []
    )


def test_check_manifest_status_vocabulary_coverage_flags_a_missing_entry() -> None:
    """A phase's (shipped, usable) pair with no matching status_vocabulary key is reported."""
    manifest = {
        "phases": {"5": {"shipped": "partial", "usable": "no"}},
        "status_vocabulary": {"partial/partial": "partially delivered"},
    }
    problems = _MODULE._check_manifest_status_vocabulary_coverage(
        manifest, Path("plan-manifest.toml")
    )
    assert len(problems) == 1
    assert "partial/no" in problems[0]


def test_check_manifest_status_vocabulary_coverage_accepts_a_covered_pair() -> None:
    """A phase's (shipped, usable) pair with a matching status_vocabulary key passes."""
    manifest = {
        "phases": {"5": {"shipped": "partial", "usable": "partial"}},
        "status_vocabulary": {"partial/partial": "partially delivered"},
    }
    assert (
        _MODULE._check_manifest_status_vocabulary_coverage(
            manifest, Path("plan-manifest.toml")
        )
        == []
    )


def test_check_manifest_status_values_flags_an_out_of_vocabulary_value() -> None:
    """A shipped/usable value outside yes/partial/no is reported."""
    manifest = {"phases": {"0": {"shipped": "definitely", "usable": "yes"}}}
    problems = _MODULE._check_manifest_status_values(
        manifest, Path("plan-manifest.toml")
    )
    assert len(problems) == 1
    assert "definitely" in problems[0]


@pytest.mark.parametrize("shipped", ["yes", "partial", "no"])
@pytest.mark.parametrize("usable", ["yes", "partial", "no"])
def test_check_manifest_status_values_accepts_every_valid_combination(
    shipped: str, usable: str
) -> None:
    """Every combination of the three valid shipped/usable values passes."""
    manifest = {"phases": {"0": {"shipped": shipped, "usable": usable}}}
    assert (
        _MODULE._check_manifest_status_values(manifest, Path("plan-manifest.toml"))
        == []
    )


def test_check_manifest_phase_7_excluded_from_r2_flags_phase_7_in_r2() -> None:
    """Phase 7 appearing in R2's requires_phases is the one load-bearing regression this check
    exists to catch: it breaks the fact that TestFlight (R2) can ship before the Kids compliance
    checklist (Phase 7) finishes.
    """
    manifest = {"rungs": {"R2": {"requires_phases": ["6", "7"]}}}
    problems = _MODULE._check_manifest_phase_7_excluded_from_r2(
        manifest, Path("plan-manifest.toml")
    )
    assert len(problems) == 1
    assert "R2" in problems[0]
    assert "7" in problems[0]


def test_check_manifest_phase_7_excluded_from_r2_accepts_phase_7_absent_from_r2() -> (
    None
):
    """R2 not requiring phase 7 at all is the expected, passing shape."""
    manifest = {"rungs": {"R2": {"requires_phases": ["6", "8"]}}}
    assert (
        _MODULE._check_manifest_phase_7_excluded_from_r2(
            manifest, Path("plan-manifest.toml")
        )
        == []
    )


def test_check_manifest_phase_7_excluded_from_r2_accepts_the_real_manifest() -> None:
    """The real plan-manifest.toml currently keeps phase 7 out of R2's requires_phases."""
    manifest = _MODULE._load_manifest(_MODULE._DEFAULT_MANIFEST, [])
    assert manifest is not None
    assert (
        _MODULE._check_manifest_phase_7_excluded_from_r2(
            manifest, _MODULE._DEFAULT_MANIFEST
        )
        == []
    )


def test_check_manifest_integrity_returns_no_problems_for_the_real_manifest() -> None:
    """The real plan-manifest.toml is internally consistent end to end."""
    manifest = _MODULE._load_manifest(_MODULE._DEFAULT_MANIFEST, [])
    assert manifest is not None
    assert _MODULE._check_manifest_integrity(manifest, _MODULE._DEFAULT_MANIFEST) == []


def test_check_linkage_reports_a_manifest_integrity_problem_end_to_end(
    tmp_path: Path,
) -> None:
    """Phase 7 leaking into R2's requires_phases surfaces through check_linkage."""
    register_path = _write(tmp_path / "register.md", _register())
    broken_manifest = _VALID_MANIFEST.replace(
        '[rungs.R2]\nrequires_phases = ["0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5", "6"]',
        '[rungs.R2]\nrequires_phases = ["0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5", "6", "7"]',
    )
    assert broken_manifest != _VALID_MANIFEST
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", broken_manifest),
    )
    assert any("R2" in p and "7" in p for p in problems)


# ---------------------------------------------------------------------------
# F. roadmap phase-status prose vs manifest [status_vocabulary]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("✅ Delivered", "delivered"),
        ("✅ Delivered (backend)", "delivered"),
        ("✅ Delivered (R1 feature-complete)", "delivered"),
        ("✅ Substantially delivered (2026-07-20 audit)", "substantially delivered"),
        ("🟡 Partially delivered", "partially delivered"),
    ],
)
def test_normalize_roadmap_status_prose_strips_glyph_and_trailing_qualifier(
    cell: str, expected: str
) -> None:
    """Leading status glyphs and trailing parenthetical qualifiers are noise, not signal."""
    assert _MODULE._normalize_roadmap_status_prose(cell) == expected


def test_roadmap_phase_status_rows_returns_no_rows_when_the_table_is_absent() -> None:
    """A roadmap with no phase-status table (every fixture in this suite) has nothing to check,
    not a malformed-structure failure; the real roadmap.md's table is what this check exists to
    validate.
    """
    assert _MODULE._roadmap_phase_status_rows(_VALID_ROADMAP.splitlines()) == []


def test_roadmap_phase_status_rows_parses_phase_token_and_raw_status_cell() -> None:
    """The phase token is the leading word of column 1; the status cell is passed through raw
    for the caller to normalize."""
    text = (
        "| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 0 Foundations | ✅ Delivered | done |\n"
        "| 5 Hardening | \U0001f7e1 Partially delivered | wip |\n"
    )
    rows = _MODULE._roadmap_phase_status_rows(text.splitlines())
    assert [(token, status) for _line, token, status in rows] == [
        ("0", "✅ Delivered"),
        ("5", "\U0001f7e1 Partially delivered"),
    ]


def test_check_roadmap_phase_status_ignores_a_phase_token_unknown_to_the_manifest() -> (
    None
):
    """A status row for a phase token the manifest does not declare is not this check's
    finding; the vocabulary-drift check reports that mismatch instead."""
    manifest = {"phases": {}, "status_vocabulary": {}}
    lines = (
        "| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 99 Unknown | ✅ Delivered | n/a |\n"
    ).splitlines()
    assert (
        _MODULE._check_roadmap_phase_status(lines, Path("roadmap.md"), manifest) == []
    )


def test_check_roadmap_phase_status_ignores_a_pair_with_no_vocabulary_entry() -> None:
    """A phase whose (shipped, usable) pair has no status_vocabulary key is not this check's
    finding; the manifest-integrity check reports that gap instead."""
    manifest = {
        "phases": {"0": {"shipped": "yes", "usable": "no"}},
        "status_vocabulary": {"yes/yes": "delivered"},
    }
    lines = (
        "| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 0 Foundations | ✅ Shipped but unusable | n/a |\n"
    ).splitlines()
    assert (
        _MODULE._check_roadmap_phase_status(lines, Path("roadmap.md"), manifest) == []
    )


def test_check_linkage_accepts_matching_roadmap_phase_status(tmp_path: Path) -> None:
    """A roadmap status cell whose normalized term matches the manifest's derived term is
    clean."""
    register_path = _write(tmp_path / "register.md", _register())
    roadmap = _VALID_ROADMAP + (
        "\n| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 0 Foundations | ✅ Delivered | done |\n"
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", roadmap),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
    )
    assert problems == []


def test_check_linkage_reports_a_roadmap_phase_status_mismatch(tmp_path: Path) -> None:
    """A roadmap status cell whose normalized term disagrees with the manifest is reported."""
    register_path = _write(tmp_path / "register.md", _register())
    roadmap = _VALID_ROADMAP + (
        "\n| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 0 Foundations | \U0001f7e1 Partially delivered | wrong |\n"
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", roadmap),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
    )
    mismatches = [p for p in problems if "status column" in p]
    assert len(mismatches) == 1
    assert "'0'" in mismatches[0]
    assert "delivered" in mismatches[0]


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


def test_main_accepts_a_manifest_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The --manifest flag is wired through to check_linkage like the other path flags."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster A: ADR follow-ons\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-A01 | Do the thing | 5 | unscheduled |\n"
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
            "--manifest",
            str(_write(tmp_path / "manifest.toml", _VALID_MANIFEST)),
        ]
    )

    assert exit_code == 0
    assert "ok:" in capsys.readouterr().out


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


def test_main_default_invocation_never_calls_subprocess() -> None:
    """The default (no-flags) CLI path never shells out; --check-issues is opt-in precisely so
    pre-commit stays offline."""
    with patch("subprocess.run") as mock_run:
        exit_code = _MODULE.main([])
    assert exit_code == 0
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# G. capability-register status vocabulary (Task A)
# ---------------------------------------------------------------------------


def test_capability_register_status_rows_returns_line_id_docs_notes_tuples() -> None:
    """Each row's line number, id, Docs cell, and Notes cell are returned in document order."""
    lines = (
        _CAPABILITY_TABLE_HEADER
        + "| K1 | Kid thing | \U0001f7e1 | needs work |\n"
        + "| K2 | Done thing | ✅ | |\n"
    ).splitlines()
    rows = _MODULE._capability_register_status_rows(lines)
    assert rows == [
        (3, "K1", "\U0001f7e1", "needs work"),
        (4, "K2", "✅", ""),
    ]


def test_check_capability_status_vocabulary_accepts_every_glyph_and_tallies_counts() -> (
    None
):
    """Each of the three recognised glyphs passes, and the glyph tally is exact."""
    rows = [
        (10, "K1", "✅", "done"),
        (11, "K2", "\U0001f7e1", "partial notes"),
        (12, "K3", "❌", "missing notes"),
    ]
    problems, counts = _MODULE._check_capability_status_vocabulary(
        rows, Path("capability-register.md")
    )
    assert problems == []
    assert counts == {"✅": 1, "\U0001f7e1": 1, "❌": 1}


def test_check_capability_status_vocabulary_rejects_an_unrecognised_glyph() -> None:
    """A Docs cell holding anything other than the three status glyphs fails, naming the row,
    line, and offending cell content."""
    rows = [(5, "K9", "\U0001f7e2", "notes")]
    problems, counts = _MODULE._check_capability_status_vocabulary(
        rows, Path("capability-register.md")
    )
    assert len(problems) == 1
    assert "K9" in problems[0]
    assert "5" in problems[0]
    assert "\U0001f7e2" in problems[0]
    assert counts == {}


@pytest.mark.parametrize("glyph", ["\U0001f7e1", "❌"])
def test_check_capability_status_vocabulary_rejects_empty_notes_on_an_open_row(
    glyph: str,
) -> None:
    """A partial or missing capability with an empty Notes cell fails: not-delivered with no
    explanation of what is missing is not useful scope tracking."""
    rows = [(7, "K5", glyph, "")]
    problems, counts = _MODULE._check_capability_status_vocabulary(
        rows, Path("capability-register.md")
    )
    assert len(problems) == 1
    assert "K5" in problems[0]
    assert "empty" in problems[0]
    assert counts == {glyph: 1}


def test_check_capability_status_vocabulary_allows_empty_notes_on_a_done_row() -> None:
    """A done (checkmark) row needs no Notes cell; only partial/missing rows require one."""
    rows = [(8, "K6", "✅", "")]
    problems, counts = _MODULE._check_capability_status_vocabulary(
        rows, Path("capability-register.md")
    )
    assert problems == []
    assert counts == {"✅": 1}


def test_check_linkage_reports_an_unrecognised_capability_docs_glyph_end_to_end(
    tmp_path: Path,
) -> None:
    """A bad Docs glyph in the real capability-register shape surfaces through check_linkage."""
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K1 | Something | \U0001f7e2 | notes |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert any(
        "K1" in problem and "not one of the three status glyphs" in problem
        for problem in problems
    )


def test_check_linkage_reports_empty_notes_on_an_open_capability_row_end_to_end(
    tmp_path: Path,
) -> None:
    """A partial capability with an empty Notes cell surfaces through check_linkage, cited in
    the mapping section so the only expected problem is the empty-Notes one."""
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K1 | Kid-facing thing | \U0001f7e1 | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert len(problems) == 1
    assert "K1" in problems[0]
    assert "empty" in problems[0]


def test_capability_summary_reports_per_glyph_counts(tmp_path: Path) -> None:
    """The success-summary helper reports total row count and per-glyph tally, checkmark first,
    matching the cluster-count summary's format convention."""
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER
        + "| K1 | Done | ✅ | |\n"
        + "| K2 | Partial | \U0001f7e1 | needs work |\n"
        + "| K3 | Missing | ❌ | needs build |\n",
    )
    summary = _MODULE._capability_summary(capability_path)
    assert "3 capability row(s)" in summary
    assert "✅=1" in summary
    assert "\U0001f7e1=1" in summary
    assert "❌=1" in summary


def test_main_prints_capability_summary_line_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI's success path prints the capability glyph summary after the cluster summary."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster A: ADR follow-ons\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-A01 | Do the thing | 5 | unscheduled |\n"
        ),
    )
    roadmap = _VALID_ROADMAP + (
        "\n### Where every open register item lands\n\n"
        "| Register items | Phase |\n"
        "|----------------|-------|\n"
        "| K2 partial | 4b |\n"
        "| K3 missing | 4b |\n"
    )
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER
        + "| K1 | Done | ✅ | |\n"
        + "| K2 | Partial | \U0001f7e1 | needs work |\n"
        + "| K3 | Missing | ❌ | needs build |\n",
    )
    exit_code = _MODULE.main(
        [
            "--register",
            str(register_path),
            "--roadmap",
            str(_write(tmp_path / "roadmap.md", roadmap)),
            "--debt-register",
            str(_write(tmp_path / "debt.md", "")),
            "--lessons-log",
            str(_write(tmp_path / "lessons.md", "")),
            "--capability-register",
            str(capability_path),
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "3 capability row(s): ✅=1, \U0001f7e1=1, ❌=1" in out


def test_check_linkage_against_the_real_capability_register_status_vocabulary() -> None:
    """The real capability-register.md's Docs/Notes cells satisfy the new status-vocabulary
    rules with zero problems: this is the "if real rows violate these rules, report that as a
    finding" case from a clean baseline, pinning that the real document has no such violations
    as of this change."""
    lines = _MODULE._DEFAULT_CAPABILITY_REGISTER.read_text(
        encoding="utf-8"
    ).splitlines()
    rows = _MODULE._capability_register_status_rows(lines)
    problems, counts = _MODULE._check_capability_status_vocabulary(
        rows, _MODULE._DEFAULT_CAPABILITY_REGISTER
    )
    assert problems == []
    assert sum(counts.values()) == len(rows)


# ---------------------------------------------------------------------------
# H. GitHub issue checks (Task B): --check-issues / --check-issue-orphans
# ---------------------------------------------------------------------------


def test_collect_register_issue_citations_extracts_phase_and_cluster_d_references(
    tmp_path: Path,
) -> None:
    """Both citation shapes are collected: an issue:NNN Phase value, and bare #NNN references
    inside a cluster D row's Issues column."""
    register = _register(
        "## Cluster A: ADR follow-ons\n\n"
        "| ID | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A01 | Tracks a live defect | issue:460 | unscheduled |\n",
        "## Cluster D: untracked GitHub issues\n\n"
        "| ID | Issues | Theme | Phase | Status |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| UW-D01 | #249, #250 | Something | 5 | unscheduled |\n",
    )
    register_path = _write(tmp_path / "register.md", register)
    lines = register_path.read_text(encoding="utf-8").splitlines()
    clusters = _MODULE._find_clusters(lines)
    citations = _MODULE._collect_register_issue_citations(clusters)
    assert citations[460] == [("UW-A01", "unscheduled")]
    assert citations[249] == [("UW-D01", "unscheduled")]
    assert citations[250] == [("UW-D01", "unscheduled")]


def test_check_cited_issues_not_closed_flags_closed_issue_on_non_done_row() -> None:
    """A not-done row citing a CLOSED issue is a problem naming the row, issue, and title."""
    citations = {460: [("UW-A01", "unscheduled")]}
    issues: list[dict[str, Any]] = [
        {"number": 460, "state": "CLOSED", "title": "Some bug"}
    ]
    problems = _MODULE._check_cited_issues_not_closed(
        citations, issues, Path("unscheduled-work-register.md")
    )
    assert len(problems) == 1
    assert "UW-A01" in problems[0]
    assert "#460" in problems[0]
    assert "Some bug" in problems[0]
    assert "CLOSED" in problems[0]


def test_check_cited_issues_not_closed_allows_closed_issue_on_a_done_row() -> None:
    """A row already marked done citing a closed issue is not a problem: the row and the issue
    agree that the work is finished."""
    citations = {460: [("UW-A01", "done")]}
    issues: list[dict[str, Any]] = [
        {"number": 460, "state": "CLOSED", "title": "Some bug"}
    ]
    assert (
        _MODULE._check_cited_issues_not_closed(
            citations, issues, Path("unscheduled-work-register.md")
        )
        == []
    )


def test_check_cited_issues_not_closed_allows_an_open_issue_on_any_row() -> None:
    """An issue GitHub still reports OPEN is never a problem, regardless of the citing row's
    status."""
    citations = {460: [("UW-A01", "unscheduled")]}
    issues: list[dict[str, Any]] = [
        {"number": 460, "state": "OPEN", "title": "Some bug"}
    ]
    assert (
        _MODULE._check_cited_issues_not_closed(
            citations, issues, Path("unscheduled-work-register.md")
        )
        == []
    )


def test_check_cited_issues_not_closed_flags_a_nonexistent_issue_number() -> None:
    """A citation to an issue number GitHub has never heard of is its own problem, independent
    of open/closed state."""
    citations = {999999: [("UW-A01", "unscheduled")]}
    problems = _MODULE._check_cited_issues_not_closed(
        citations, [], Path("unscheduled-work-register.md")
    )
    assert len(problems) == 1
    assert "999999" in problems[0]
    assert "does not exist" in problems[0]


def test_extract_issue_numbers_from_text_finds_both_citation_shapes() -> None:
    """A bare #NNN and an inline issue:NNN mention are both recognised, from the same text."""
    text = "See #460 and issue:472 in the same paragraph, plus PR #99."
    assert _MODULE._extract_issue_numbers_from_text(text) == {460, 472, 99}


def test_planning_docs_cited_issue_numbers_scans_every_markdown_file_recursively(
    tmp_path: Path,
) -> None:
    """Every *.md file under the given directory is searched, recursively; non-markdown files
    are not."""
    _write(tmp_path / "a.md", "cites #1\n")
    sub = tmp_path / "adr"
    sub.mkdir()
    _write(sub / "b.md", "cites issue:2\n")
    _write(tmp_path / "not-markdown.txt", "cites #3\n")
    assert _MODULE._planning_docs_cited_issue_numbers(tmp_path) == {1, 2}


def test_check_issue_orphans_flags_an_uncited_open_issue_without_the_unplanned_label() -> (
    None
):
    """An open issue cited nowhere and carrying no 'unplanned' label is an orphan."""
    issues: list[dict[str, Any]] = [
        {"number": 5, "state": "OPEN", "title": "Do a thing", "labels": []}
    ]
    problems = _MODULE._check_issue_orphans(issues, cited_numbers=set())
    assert problems == ["#5 Do a thing"]


def test_check_issue_orphans_accepts_a_cited_open_issue() -> None:
    """An open issue cited somewhere under docs/planning/ is not an orphan."""
    issues: list[dict[str, Any]] = [
        {"number": 5, "state": "OPEN", "title": "Do a thing", "labels": []}
    ]
    assert _MODULE._check_issue_orphans(issues, cited_numbers={5}) == []


def test_check_issue_orphans_accepts_an_unplanned_labelled_issue_even_if_uncited() -> (
    None
):
    """The 'unplanned' label is an explicit, deliberate escape hatch from the citation
    requirement."""
    issues: list[dict[str, Any]] = [
        {
            "number": 5,
            "state": "OPEN",
            "title": "Do a thing",
            "labels": [{"name": "unplanned"}],
        }
    ]
    assert _MODULE._check_issue_orphans(issues, cited_numbers=set()) == []


def test_check_issue_orphans_ignores_closed_issues() -> None:
    """A closed issue is never an orphan candidate; only OPEN issues need a home."""
    issues: list[dict[str, Any]] = [
        {"number": 5, "state": "CLOSED", "title": "Old", "labels": []}
    ]
    assert _MODULE._check_issue_orphans(issues, cited_numbers=set()) == []


def _completed(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    """Build a subprocess.CompletedProcess fixture for mocking subprocess.run's return value.

    Args:
        returncode: The process exit code to simulate.
        stdout: The captured stdout text to simulate.
        stderr: The captured stderr text to simulate.

    Returns:
        subprocess.CompletedProcess[str]: The fixture, matching the shape
        ``_fetch_github_issues`` reads (``.returncode``, ``.stdout``, ``.stderr``).
    """
    return subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_fetch_github_issues_returns_parsed_list_on_success() -> None:
    """A clean gh invocation returns the parsed issue list and appends no problems."""
    problems: list[str] = []
    completed = _completed(
        0, '[{"number": 1, "state": "OPEN", "title": "x", "labels": []}]'
    )
    with patch("subprocess.run", return_value=completed) as mock_run:
        issues = _MODULE._fetch_github_issues(problems)
    assert problems == []
    assert issues == [{"number": 1, "state": "OPEN", "title": "x", "labels": []}]
    mock_run.assert_called_once()
    call_args, call_kwargs = mock_run.call_args
    assert call_args[0][:3] == ["gh", "issue", "list"]
    assert call_kwargs["timeout"] == _MODULE._GH_ISSUE_LIST_TIMEOUT_SECONDS
    assert call_kwargs["check"] is False


def test_fetch_github_issues_reports_a_nonzero_returncode() -> None:
    """A non-zero gh exit is a reported problem, not a silent empty result."""
    problems: list[str] = []
    completed = _completed(1, "", "not authenticated")
    with patch("subprocess.run", return_value=completed):
        issues = _MODULE._fetch_github_issues(problems)
    assert issues is None
    assert len(problems) == 1
    assert "not authenticated" in problems[0]


def test_fetch_github_issues_reports_a_missing_gh_binary() -> None:
    """gh not being installed/on PATH is a clear, named failure, not a crash."""
    problems: list[str] = []
    with patch("subprocess.run", side_effect=FileNotFoundError):
        issues = _MODULE._fetch_github_issues(problems)
    assert issues is None
    assert len(problems) == 1
    assert "not installed" in problems[0]


def test_fetch_github_issues_reports_a_timeout() -> None:
    """A hung gh call is bounded by the timeout and reported, not left to block forever."""
    problems: list[str] = []
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
    ):
        issues = _MODULE._fetch_github_issues(problems)
    assert issues is None
    assert len(problems) == 1
    assert "did not complete within" in problems[0]


def test_fetch_github_issues_reports_unparsable_json() -> None:
    """Non-JSON stdout from gh is a reported problem, not an unhandled exception."""
    problems: list[str] = []
    completed = _completed(0, "not json")
    with patch("subprocess.run", return_value=completed):
        issues = _MODULE._fetch_github_issues(problems)
    assert issues is None
    assert len(problems) == 1
    assert "unparsable JSON" in problems[0]


def test_fetch_github_issues_reports_json_that_is_not_a_list() -> None:
    """Valid JSON of the wrong shape (not a list of issues) is also a reported problem."""
    problems: list[str] = []
    completed = _completed(0, '{"not": "a list"}')
    with patch("subprocess.run", return_value=completed):
        issues = _MODULE._fetch_github_issues(problems)
    assert issues is None
    assert len(problems) == 1
    assert "not a list" in problems[0]


def test_check_issues_returns_empty_and_skips_network_when_both_flags_are_false(
    tmp_path: Path,
) -> None:
    """Neither flag set means no gh call at all: --check-issues/--check-issue-orphans are the
    only things gating any network access."""
    with patch("subprocess.run") as mock_run:
        problems = _MODULE._check_issues(
            tmp_path / "register.md",
            tmp_path,
            check_issues=False,
            check_issue_orphans=False,
        )
    assert problems == []
    mock_run.assert_not_called()


def test_check_issues_runs_cited_issue_check_when_flag_set(tmp_path: Path) -> None:
    """--check-issues alone finds a not-done row citing a closed issue."""
    register = _register(
        "## Cluster A: ADR follow-ons\n\n"
        "| ID | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A01 | Tracks a live defect | issue:460 | unscheduled |\n"
    )
    register_path = _write(tmp_path / "register.md", register)
    completed = _completed(
        0, '[{"number": 460, "state": "CLOSED", "title": "Old bug", "labels": []}]'
    )
    with patch("subprocess.run", return_value=completed):
        problems = _MODULE._check_issues(
            register_path, tmp_path, check_issues=True, check_issue_orphans=False
        )
    assert any("UW-A01" in p and "#460" in p for p in problems)


def test_check_issues_runs_orphan_check_when_flag_set(tmp_path: Path) -> None:
    """--check-issue-orphans alone finds an uncited open issue."""
    register_path = _write(tmp_path / "register.md", _register())
    completed = _completed(
        0, '[{"number": 7, "state": "OPEN", "title": "Untracked", "labels": []}]'
    )
    with patch("subprocess.run", return_value=completed):
        problems = _MODULE._check_issues(
            register_path, tmp_path, check_issues=False, check_issue_orphans=True
        )
    assert problems == ["#7 Untracked"]


def test_check_issues_reports_gh_failure_once_and_skips_downstream_checks(
    tmp_path: Path,
) -> None:
    """A gh failure is reported once and short-circuits both downstream checks, rather than
    running them against no data."""
    register_path = _write(tmp_path / "register.md", _register())
    with patch("subprocess.run", side_effect=FileNotFoundError):
        problems = _MODULE._check_issues(
            register_path, tmp_path, check_issues=True, check_issue_orphans=True
        )
    assert len(problems) == 1
    assert "not installed" in problems[0]


def test_check_issues_shares_one_gh_call_across_both_flags(tmp_path: Path) -> None:
    """Both flags set together still make exactly one batched gh call, not one each."""
    register_path = _write(tmp_path / "register.md", _register())
    completed = _completed(0, "[]")
    with patch("subprocess.run", return_value=completed) as mock_run:
        _MODULE._check_issues(
            register_path, tmp_path, check_issues=True, check_issue_orphans=True
        )
    mock_run.assert_called_once()


def test_main_check_issues_flag_wired_through(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--check-issues on the CLI surfaces a closed-issue-cited-by-a-not-done-row failure."""
    register_path = _write(
        tmp_path / "register.md",
        _register(
            "## Cluster A: ADR follow-ons\n\n"
            "| ID | Item | Phase | Status |\n"
            "| --- | --- | --- | --- |\n"
            "| UW-A01 | Tracks a live defect | issue:460 | unscheduled |\n"
        ),
    )
    completed = _completed(
        0, '[{"number": 460, "state": "CLOSED", "title": "Old bug", "labels": []}]'
    )
    with patch("subprocess.run", return_value=completed):
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
                "--check-issues",
            ]
        )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "UW-A01" in out
    assert "#460" in out


def test_main_check_issue_orphans_flag_wired_through(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--check-issue-orphans on the CLI surfaces an uncited open issue."""
    register_path = _write(tmp_path / "register.md", _register())
    completed = _completed(
        0, '[{"number": 7, "state": "OPEN", "title": "Untracked", "labels": []}]'
    )
    with patch("subprocess.run", return_value=completed):
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
                "--check-issue-orphans",
            ]
        )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "#7 Untracked" in out
