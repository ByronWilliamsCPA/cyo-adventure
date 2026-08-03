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
import json
import re
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

# The real default manifest's phase vocabulary, computed once at import time. `_check_row_phase`
# no longer reads a module-level default (fix S1/Group A: the vocabulary is now threaded in from
# whichever manifest a run actually loads), so tests that want to accept every real phase token
# (including track-2 tokens like "9", which no small inline fixture manifest declares) load the
# real manifest here instead.
_REAL_PHASE_VOCABULARY = _MODULE._manifest_phase_vocabulary(
    _MODULE._load_manifest(_MODULE._DEFAULT_MANIFEST, [])
)

# A synthetic phase vocabulary for row-phase tests that only need *some* concrete tokens to
# exist, and are not themselves about which tokens the vocabulary contains (comma-separated
# values, status-echoing values, and empty-phase rules all fail before the vocabulary is ever
# consulted).
_SAMPLE_PHASE_VOCABULARY = frozenset(
    {"0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5"}
)

# Test-local literal copies of the real manifest's [namespaces.*] patterns, for tests that call
# the low-level id-checking functions directly rather than through check_linkage's manifest
# resolution. Kept identical to plan-manifest.toml's [namespaces] table (and to _VALID_MANIFEST's
# copy of it above) on purpose: these are the same fail-closed patterns the checker resolves at
# runtime, just precompiled here so a unit test does not need a manifest fixture on disk to
# exercise a single row-id or citation function.
_UW_ID_PATTERN = re.compile(r"^UW-[A-M]\d{2}$")
_DEBT_ID_PATTERN = re.compile(r"^(?:C\d+|GS\d+|U\d+|T\d+|P\d+|SL\d+)$")
_DEBT_CITATION_PATTERN = re.compile(r"\b(?:C\d+|GS\d+|U\d+|T\d+|P\d+|SL\d+)\b")
_AL_ID_PATTERN = re.compile(r"^AL-\d{3}$")
_AL_CITATION_PATTERN = re.compile(r"\bAL-\d+\b")
_CAP_ID_PATTERN = re.compile(r"^[KGAS]\d+$")
_CAP_CITATION_PATTERN = re.compile(r"\b[KGAS]\d+\b")
_SQ_ID_PATTERN = re.compile(r"^SQ-\d{2}$")

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

# `_ROADMAP_WITH_MAPPING` plus a phase-status table matching `_VALID_MANIFEST`'s phase "0" entry
# (shipped=yes, usable=yes -> "delivered", glyph checkmark). Fix F4 made a document that carries
# table content but no locatable ("Phase", "Status") header raise instead of silently returning
# zero rows; `_ROADMAP_WITH_MAPPING`'s own mapping table gives it exactly that "has pipes, no
# phase-status header" shape, so any test built on it that also passes a manifest and asserts an
# exact problem count needs a real, matching phase-status table added, not just the mapping one.
_ROADMAP_WITH_MAPPING_AND_PHASE_STATUS = _ROADMAP_WITH_MAPPING + (
    "\n| Phase | Status | Evidence |\n"
    "|-------|--------|----------|\n"
    "| 0 Foundations | ✅ Delivered | done |\n"
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

[namespaces.uw]
prefix = "UW"
source = "docs/planning/unscheduled-work-register.md"
pattern = "^UW-[A-M]\\\\d{2}$"

[namespaces.debt]
prefix = "debt"
source = "docs/planning/r1-deferred-debt-register.md"
pattern = "^(?:C\\\\d+|GS\\\\d+|U\\\\d+|T\\\\d+|P\\\\d+|SL\\\\d+)$"
citation_pattern = "\\\\b(?:C\\\\d+|GS\\\\d+|U\\\\d+|T\\\\d+|P\\\\d+|SL\\\\d+)\\\\b"

[namespaces.al]
prefix = "AL"
source = "docs/planning/authoring-lessons-log.md"
pattern = "^AL-\\\\d{3}$"
citation_pattern = "\\\\bAL-\\\\d+\\\\b"

[namespaces.cap]
prefix = "cap"
source = "docs/planning/capability-register.md"
pattern = "^[KGAS]\\\\d+$"
citation_pattern = "\\\\b[KGAS]\\\\d+\\\\b"

[namespaces.sq]
prefix = "SQ"
source = "docs/planning/story-structure-improvement-plan.md"
pattern = "^SQ-\\\\d{2}$"

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


_MATCHING_PROJECT_PLAN = """\
### Phase 6: Public Authentication and Multi-Tenancy

**Status**: ⏸️ Not started

### Phase 7: Kids Compliance and Account Lifecycle

**Status**: ⏸️ Not started
"""


def _write_matching_project_plan(tmp_path: Path) -> Path:
    """Write a PROJECT-PLAN.md whose track-2 statuses agree with ``_VALID_MANIFEST``.

    ``check_linkage`` drift-checks the manifest's track-2 phases against PROJECT-PLAN.md, so a
    test pairing a fixture manifest with the repository's real plan document is validating two
    documents that were never meant to describe each other. This gives such tests a plan that
    matches their manifest, the same way ``_VALID_ROADMAP`` matches it for track 1.

    Args:
        tmp_path: The pytest ``tmp_path`` fixture's directory.

    Returns:
        Path: The written file's path.
    """
    return _write(tmp_path / "PROJECT-PLAN.md", _MATCHING_PROJECT_PLAN)


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
    assert _MODULE._check_row_id("A", 10, "UW-A01", _UW_ID_PATTERN) == []


def test_check_row_id_rejects_malformed_id() -> None:
    """An id missing the zero-padded two digits fails with a message naming it."""
    problems = _MODULE._check_row_id("A", 10, "UW-A1", _UW_ID_PATTERN)
    assert len(problems) == 1
    assert "UW-A1" in problems[0]
    assert "does not match UW-[A-M]NN" in problems[0]


def test_check_row_id_rejects_id_filed_under_the_wrong_cluster() -> None:
    """A well-formed id whose letter does not match the cluster table it was found in fails.

    A row copy-pasted between clusters (or a typo'd id, e.g. 'UW-A01' inside the Cluster B
    table) previously passed the id-format check silently, since it only validated the regex
    shape and never compared the id's own letter against the cluster it was found in.
    """
    problems = _MODULE._check_row_id("B", 10, "UW-A01", _UW_ID_PATTERN)
    assert len(problems) == 1
    assert "UW-A01" in problems[0]
    assert "belongs to cluster 'A'" in problems[0]
    assert "cluster 'B' table" in problems[0]


def test_check_row_id_accepts_id_matching_its_cluster() -> None:
    """A well-formed id whose letter matches the cluster table it was found in still passes."""
    assert _MODULE._check_row_id("B", 10, "UW-B01", _UW_ID_PATTERN) == []


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
    """Every category of the closed phase vocabulary is accepted.

    ``_check_row_phase`` no longer reads a module-level default vocabulary (fix S1): the
    vocabulary is threaded in from whichever manifest a run actually loaded. The real default
    manifest's derived vocabulary is used here rather than a small inline fixture, since this
    parametrization needs track-2 tokens like "9" that only the real manifest declares.
    """
    assert (
        _MODULE._check_row_phase(
            "A", 1, "UW-A01", phase, "unscheduled", _REAL_PHASE_VOCABULARY
        )
        == []
    )


def test_check_row_phase_rejects_value_outside_vocabulary() -> None:
    """A phase spelled outside the closed vocabulary fails."""
    problems = _MODULE._check_row_phase(
        "A", 1, "UW-A01", "42", "unscheduled", _SAMPLE_PHASE_VOCABULARY
    )
    assert len(problems) == 1
    assert "not in the closed phase vocabulary" in problems[0]


# ---------------------------------------------------------------------------
# A.4 comma-separated phase
# ---------------------------------------------------------------------------


def test_check_row_phase_rejects_comma_separated_value() -> None:
    """A Phase column holding more than one value is rejected."""
    problems = _MODULE._check_row_phase(
        "A", 1, "UW-A01", "4b, 5", "unscheduled", _SAMPLE_PHASE_VOCABULARY
    )
    assert len(problems) == 1
    assert "more than one" in problems[0]


# ---------------------------------------------------------------------------
# A.5 phase repeating a status value
# ---------------------------------------------------------------------------


def test_check_row_phase_rejects_phase_equal_to_a_status() -> None:
    """A Phase column that just repeats a Status word is rejected."""
    problems = _MODULE._check_row_phase(
        "A", 1, "UW-A01", "blocked", "decision", _SAMPLE_PHASE_VOCABULARY
    )
    assert len(problems) == 1
    assert "repeats a Status value" in problems[0]


# ---------------------------------------------------------------------------
# A.6 empty phase
# ---------------------------------------------------------------------------


def test_check_row_phase_rejects_empty_phase_on_unscheduled_row() -> None:
    """An empty Phase on an unscheduled row is one of the disallowed empty cases."""
    problems = _MODULE._check_row_phase(
        "A", 1, "UW-A01", "", "unscheduled", _SAMPLE_PHASE_VOCABULARY
    )
    assert len(problems) == 1
    assert "Phase is empty" in problems[0]


@pytest.mark.parametrize("status", ["blocked", "decision", "verify"])
def test_check_row_phase_rejects_empty_phase_on_a_row_that_still_needs_a_phase_home(
    status: str,
) -> None:
    """An empty Phase is a problem for every status except ``done`` (fix S6).

    This inverts the assertion the old
    ``test_check_row_phase_allows_empty_phase_on_a_non_unscheduled_row`` made: that test asserted
    an empty Phase was fine on a ``blocked`` row, which was the very silent-pass gap fix S6
    closes. ``blocked``/``decision``/``verify`` rows still need the phase they will eventually
    land in, exactly like ``unscheduled`` rows; only ``done`` is exempt, since its required
    evidence is a PR/commit/issue reference rather than a future phase.
    """
    problems = _MODULE._check_row_phase(
        "A", 1, "UW-A01", "", status, _SAMPLE_PHASE_VOCABULARY
    )
    assert len(problems) == 1
    assert "Phase is empty" in problems[0]
    assert status in problems[0]


def test_check_row_phase_allows_empty_phase_on_a_done_row() -> None:
    """An empty Phase is fine on a ``done`` row: its required evidence is a PR/commit/issue
    citation (per the linkage contract), not a future phase to land in."""
    assert (
        _MODULE._check_row_phase("A", 1, "UW-A01", "", "done", _SAMPLE_PHASE_VOCABULARY)
        == []
    )


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


def test_check_linkage_reports_duplicate_id_when_one_occurrence_is_a_malformed_row(
    tmp_path: Path,
) -> None:
    """A duplicate id is still caught even when one of its two rows has the wrong column count
    (fix S5).

    ``_check_cluster_rows`` skips a malformed row's per-cell checks (its column count already
    disagrees with the header, so id/status/phase indexes cannot be trusted), but it must still
    collect the row's id for the register-wide uniqueness walk. Before this fix, a malformed row
    was skipped before its id was collected at all, so an id reused on a well-formed row and a
    malformed row was invisible to the uniqueness check: the malformed-row problem fired, but the
    duplicate the malformed row was hiding did not.
    """
    register = _register(
        "## Cluster A: ADR follow-ons\n\n"
        "| ID | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A01 | First use, well-formed | 5 | unscheduled |\n",
        "## Cluster B: debt-register phase linkage\n\n"
        "| ID | Item | Phase | Status |\n"
        "| --- | --- | --- | --- |\n"
        "| UW-A01 | Reused id, missing a column |\n",
    )
    register_path = _write(tmp_path / "register.md", register)
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
    )
    assert any("expected 4 columns, found 2" in p for p in problems)
    assert any("used on 2 rows" in p and "UW-A01" in p for p in problems)


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


def test_extract_roadmap_product_phases_matches_the_manifest_derived_track1_vocabulary(
    tmp_path: Path,
) -> None:
    """The roadmap parser derives exactly the track-1 phase set a manifest declares.

    ``_MODULE._PRODUCT_PHASES`` (a hardcoded, import-time module constant) no longer exists:
    that was the dual source of truth fix S1 removed. The phase vocabulary is now derived from
    whichever manifest a run actually loads. ``_VALID_MANIFEST``'s track-1 phases are defined to
    match ``_VALID_ROADMAP``'s headings exactly (see its own comment above), so comparing against
    ``_manifest_phases_for_track(manifest, 1)`` is the manifest-driven equivalent of the old
    hardcoded-constant comparison.
    """
    manifest_path = _write(tmp_path / "manifest.toml", _VALID_MANIFEST)
    manifest = _MODULE._load_manifest(manifest_path, [])
    assert manifest is not None
    assert _MODULE._extract_roadmap_product_phases(
        _VALID_ROADMAP
    ) == _MODULE._manifest_phases_for_track(manifest, 1)


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
    """A missing manifest is reported, and does not silently pass as a clean run.

    Before every id namespace's pattern moved into the manifest, the debt-register linkage
    check used a hardcoded regex with no dependency on the manifest at all, so it kept finding
    open debt ids even when the manifest could not be read. That independence is gone by
    design: the debt id pattern now lives in ``[namespaces.debt]`` in this same file, so a
    missing manifest leaves the debt-linkage check with no pattern to find open debt ids with,
    and it correctly finds none rather than guessing one. What this test still pins is the one
    guarantee that survives: the manifest failure itself is always reported, never swallowed,
    so a human has the actual root cause instead of a puzzling absence of findings.
    """
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
    assert not any("debt 'C2'" in problem for problem in problems)


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


# ---------------------------------------------------------------------------
# E.1 manifest structural preconditions (fix F3)
# ---------------------------------------------------------------------------
#
# Before fix F3, every one of the six consistency checks above read [phases]/[rungs] with a {}
# default and iterated it, so a manifest missing either table (or one deleted down to an empty
# table) made all six report zero problems: a manifest that declared nothing to check "passed"
# every check that would have caught it. _check_manifest_structure runs first and short-circuits
# the rest so that shape is reported directly instead of certified clean.


def test_check_manifest_structure_flags_a_missing_phases_table() -> None:
    """A manifest with no [phases] table at all is reported by name, not silently iterated as
    an empty dict by every downstream check."""
    manifest = {"rungs": {"R1": {}, "R2": {}, "R3": {}}}
    problems = _MODULE._check_manifest_structure(manifest, Path("plan-manifest.toml"))
    assert any("[phases]" in p and "missing" in p for p in problems)


def test_check_manifest_structure_flags_a_non_table_phases_value() -> None:
    """A [phases] value that parsed as a string ('phases = \"x\"' is valid TOML) is reported
    instead of reaching a downstream ``.items()`` call as an AttributeError traceback."""
    manifest = {"phases": "x", "rungs": {"R1": {}, "R2": {}, "R3": {}}}
    problems = _MODULE._check_manifest_structure(manifest, Path("plan-manifest.toml"))
    assert any("[phases]" in p and "not a table" in p for p in problems)


def test_check_manifest_structure_flags_an_empty_phases_table() -> None:
    """A [phases] table present but declaring no phases at all is reported."""
    manifest = {"phases": {}, "rungs": {"R1": {}, "R2": {}, "R3": {}}}
    problems = _MODULE._check_manifest_structure(manifest, Path("plan-manifest.toml"))
    assert any("[phases]" in p and "empty" in p for p in problems)


def test_check_manifest_structure_flags_a_missing_rungs_table() -> None:
    """A manifest with no [rungs] table at all is reported by name.

    This is the real defect fix F3 exists to close: deleting [rungs] used to make the whole
    manifest-integrity suite, including the #CRITICAL Phase-7-excluded-from-R2 assertion, return
    zero problems.
    """
    manifest = {"phases": {"0": {}}}
    problems = _MODULE._check_manifest_structure(manifest, Path("plan-manifest.toml"))
    assert any("[rungs]" in p and "missing" in p for p in problems)


def test_check_manifest_structure_flags_an_empty_rungs_table() -> None:
    """A [rungs] table present but declaring no rungs at all is reported."""
    manifest = {"phases": {"0": {}}, "rungs": {}}
    problems = _MODULE._check_manifest_structure(manifest, Path("plan-manifest.toml"))
    assert any("[rungs]" in p and "empty" in p for p in problems)


@pytest.mark.parametrize("missing_rung", ["R1", "R2", "R3"])
def test_check_manifest_structure_flags_a_missing_required_rung(
    missing_rung: str,
) -> None:
    """Each of R1/R2/R3 is required individually; dropping just one is named, not absorbed into
    a generic "[rungs] is wrong" message."""
    rungs = {name: {} for name in ("R1", "R2", "R3") if name != missing_rung}
    manifest = {"phases": {"0": {}}, "rungs": rungs}
    problems = _MODULE._check_manifest_structure(manifest, Path("plan-manifest.toml"))
    assert any(f"[rungs.{missing_rung}]" in p and "missing" in p for p in problems)


def test_check_manifest_integrity_regression_deleting_rungs_table_is_not_clean() -> (
    None
):
    """A manifest missing [rungs] must not report a clean result: this is the exact regression
    fix F3 closes.

    Before the fix, ``_check_manifest_integrity`` ran its six consistency checks directly. Every
    one of them reads ``manifest.get("rungs", {})`` (or ``"phases"``) with an empty-dict default
    and iterates it, so on this manifest all six would iterate nothing and return []: a manifest
    that deleted its entire release ladder, including the #CRITICAL Phase-7-excluded-from-R2
    assertion this file calls the single most load-bearing dependency fact in the plan, would
    have "passed" manifest integrity. If ``_check_manifest_structure`` (or the short-circuit
    that runs it first) were removed, this assertion would fail: ``problems`` would come back
    ``[]`` for a manifest that plainly has no release ladder at all.
    """
    manifest = {
        "phases": {"0": {"shipped": "yes", "usable": "yes"}},
        "status_vocabulary": {"yes/yes": "delivered"},
    }
    problems = _MODULE._check_manifest_integrity(manifest, Path("plan-manifest.toml"))
    assert problems != []
    assert any("[rungs]" in p for p in problems)


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
    ("text", "expected"),
    [
        ("Delivered (backend) (2026-07-20 audit)", "Delivered"),
        ("Delivered (a (b))", "Delivered"),
        ("Delivered (a) (b) (c)", "Delivered"),
    ],
)
def test_strip_trailing_parentheticals_handles_multiple_and_nested_groups(
    text: str, expected: str
) -> None:
    """Fix S3: strips every trailing balanced ``(...)`` group, not just the last one, and counts
    nesting depth rather than matching the first ``)`` a single-pass regex would find.

    A regex-based single strip (``r" \\([^)]*\\)$"``) leaves "Delivered (backend)" behind after
    stripping only "(2026-07-20 audit)" from the first case, and mis-splits "(a (b))" at the
    inner ``)`` in the second, leaving a dangling "(a (b))" fragment instead of removing the
    whole balanced group. Both would then be compared against the manifest's clean "delivered"
    term and reported as spurious mismatches.
    """
    assert _MODULE._strip_trailing_parentheticals(text) == expected


def test_strip_trailing_parentheticals_leaves_an_unbalanced_trailing_paren_in_place() -> (
    None
):
    """An unbalanced trailing ``)`` with no matching ``(`` is left alone rather than guessed at;
    a malformed cell should surface as a mismatch, not be silently repaired into a false match."""
    assert (
        _MODULE._strip_trailing_parentheticals("Delivered notes)") == "Delivered notes)"
    )


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


def test_roadmap_phase_status_rows_returns_no_rows_when_the_document_has_no_pipe_content() -> (
    None
):
    """A roadmap with no table-like content at all (``_VALID_ROADMAP`` is headings only, no "|"
    anywhere) genuinely has nothing to check and returns no rows.

    This is the "empty document" branch of ``_roadmap_phase_status_rows``, distinct from the
    "corrupted document" branch covered by
    ``test_roadmap_phase_status_rows_raises_when_pipe_content_exists_but_the_header_is_gone``:
    a roadmap that has other tables but no locatable phase-status header must raise, not also
    return ``[]``.
    """
    assert "|" not in _VALID_ROADMAP
    assert _MODULE._roadmap_phase_status_rows(_VALID_ROADMAP.splitlines()) == []


def test_roadmap_phase_status_rows_raises_when_pipe_content_exists_but_the_header_is_gone() -> (
    None
):
    """A roadmap that carries table-like content but no row whose first cell is ``Phase`` with a
    ``Status`` column alongside it must raise, not silently return ``[]`` (fix F4).

    Before this fix, renaming or reformatting the phase-status header dropped the checked row
    count from however many the table held to zero, and the caller could not tell that apart
    from a roadmap that legitimately carries no phase-status table: both returned ``[]``. This is
    the same "a check that can only pass is worse than no check" shape as the capability-register
    and lessons-log header checks elsewhere in this module.
    """
    lines = ("| Some Other Table | Column |\n|---|---|\n| a | b |\n").splitlines()
    with pytest.raises(
        LookupError, match="table content but no phase-status table header"
    ):
        _MODULE._roadmap_phase_status_rows(lines)


def test_check_linkage_reports_a_roadmap_with_pipe_content_but_no_phase_status_header(
    tmp_path: Path,
) -> None:
    """End to end: a roadmap with an unrelated table and no phase-status header surfaces as a
    problem instead of a clean run (fix F4)."""
    register_path = _write(tmp_path / "register.md", _register())
    roadmap = _VALID_ROADMAP + (
        "\n| Some Other Table | Column |\n|---|---|\n| a | b |\n"
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", roadmap),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
    )
    assert any("table content but no phase-status table header" in p for p in problems)


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
        project_plan_path=_write_matching_project_plan(tmp_path),
    )
    assert problems == []


def test_check_linkage_reports_a_roadmap_phase_status_prose_mismatch(
    tmp_path: Path,
) -> None:
    """A roadmap status cell whose normalized term disagrees with the manifest is reported.

    Fix S2 added a second, independent check on the same cell: the leading glyph must agree
    with the phase's ``shipped`` axis (``_check_roadmap_status_glyph``). Both checks' messages
    contain the substring "status column", so this row's glyph is deliberately kept correct
    (``✅`` for phase "0"'s ``shipped='yes'``) and only the prose is wrong, isolating the
    assertion to the one finding this test names. See
    ``test_check_linkage_reports_a_roadmap_phase_status_glyph_mismatch`` for the glyph half.
    """
    register_path = _write(tmp_path / "register.md", _register())
    roadmap = _VALID_ROADMAP + (
        "\n| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 0 Foundations | ✅ Partially delivered | wrong |\n"
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", roadmap),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
    )
    mismatches = [p for p in problems if "normalized to" in p]
    assert len(mismatches) == 1
    assert "'0'" in mismatches[0]
    assert "delivered" in mismatches[0]
    assert not any("glyph is" in p for p in problems)


def test_check_linkage_reports_a_roadmap_phase_status_glyph_mismatch(
    tmp_path: Path,
) -> None:
    """A roadmap status cell whose leading glyph disagrees with the manifest's ``shipped`` value
    is reported (fix S2).

    Before this check, ``_normalize_roadmap_status_prose`` threw the glyph away before comparing
    the prose term, so a cell reading "🟡 Delivered" against a ``yes/yes`` phase matched the
    manifest-derived term perfectly: the most visible half of the cell, the one a reader scans
    first, was the only unvalidated half. This row's prose is deliberately kept correct
    ("Delivered" matches phase "0"'s ``yes/yes`` -> "delivered") so only the glyph mismatch
    fires, isolating the assertion from the prose check
    (``test_check_linkage_reports_a_roadmap_phase_status_prose_mismatch``).
    """
    register_path = _write(tmp_path / "register.md", _register())
    roadmap = _VALID_ROADMAP + (
        "\n| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 0 Foundations | \U0001f7e1 Delivered | wrong |\n"
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", roadmap),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
    )
    glyph_mismatches = [p for p in problems if "glyph is" in p]
    assert len(glyph_mismatches) == 1
    assert "'0'" in glyph_mismatches[0]
    assert not any("normalized to" in p for p in problems)


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
        _MODULE._extract_citations("`SL1` through `SL9999`", _DEBT_CITATION_PATTERN)


def test_extract_citations_expands_a_hyphenated_al_prefix_through_range() -> None:
    """Fix S4: a "through" range whose ids carry a hyphenated prefix (``AL-001 through
    AL-005``, the authoring-lessons-log's own id shape) expands correctly.

    ``_THROUGH_RANGE_RE``'s prefix group used to be ``[A-Z]{1,2}`` with no hyphen, so it could
    never match "AL-001 through AL-005" at all (the literal "-" between the letters and the
    first digit broke the match before "through" was even reached): every AL-prefixed range
    citation silently expanded to nothing, and every id it meant to cite was reported as an
    orphan lesson. Zero-padding is reproduced from the range's own first endpoint, so this
    expands to "AL-001".."AL-005", not "AL-1".."AL-5".
    """
    cited = _MODULE._extract_citations(
        "`AL-001` through `AL-005`", _AL_CITATION_PATTERN
    )
    assert cited == {"AL-001", "AL-002", "AL-003", "AL-004", "AL-005"}


def test_extract_citations_rejects_a_backwards_through_range() -> None:
    """A "through" range whose endpoints are transposed (fix S4) fails loud instead of silently
    expanding to no ids at all, which would report every id it meant to cite as an orphan."""
    with pytest.raises(ValueError, match="runs backwards"):
        _MODULE._extract_citations("`SL9` through `SL1`", _DEBT_CITATION_PATTERN)


def test_debt_register_open_ids_excludes_lettered_sub_item_ids() -> None:
    """A decorated id like U9a is not one of the debt-id families the contract names."""
    lines = (
        _DEBT_TABLE_HEADER + "| U9a | A dark-mode polish item | src | Low | none |\n"
    ).splitlines()
    assert _MODULE._debt_register_open_ids(lines, _DEBT_ID_PATTERN) == {}


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
    assert _MODULE._debt_register_open_ids(lines, _DEBT_ID_PATTERN) == {"C1": 3}


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
    assert _MODULE._lessons_needing_citation([], _AL_ID_PATTERN) == {}


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
    """An open capability named inside the mapping section satisfies the linkage obligation.

    Uses ``_ROADMAP_WITH_MAPPING_AND_PHASE_STATUS`` plus an explicit ``_VALID_MANIFEST`` rather
    than the bare mapping fixture: fix F4 made a document with table content but no locatable
    phase-status header raise, and ``_ROADMAP_WITH_MAPPING`` alone has exactly that shape (its
    mapping table gives it pipes with no ``('Phase', 'Status')`` header). Without a real
    phase-status table this test's ``problems == []`` assertion would always fail on the
    unrelated header problem, regardless of whether the capability-linkage rule under test still
    worked.
    """
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K1 | Kid-facing thing | \U0001f7e1 | notes |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING_AND_PHASE_STATUS),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
    )
    assert problems == []


def test_check_linkage_treats_done_capability_as_satisfied(tmp_path: Path) -> None:
    """A capability already marked done (✅) needs no mapping citation, even if absent.

    See ``test_check_linkage_accepts_open_capability_cited_in_mapping_section`` for why this
    needs ``_ROADMAP_WITH_MAPPING_AND_PHASE_STATUS`` and an explicit manifest (fix F4).
    """
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K9 | Shelf presentation | ✅ | notes |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING_AND_PHASE_STATUS),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
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
    open_ids = _MODULE._capability_register_open_ids(lines, _CAP_ID_PATTERN)
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
    open_ids = _MODULE._capability_register_open_ids(lines, _CAP_ID_PATTERN)
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
        _MODULE._capability_register_open_ids(lines, _CAP_ID_PATTERN)


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
        _MODULE._capability_register_open_ids(lines, _CAP_ID_PATTERN)


def test_capability_register_open_ids_returns_no_rows_for_a_genuinely_empty_document() -> (
    None
):
    """A document with no table-like content at all is not the malformed-header failure mode;
    it has nothing to report and does not raise."""
    assert _MODULE._capability_register_open_ids([], _CAP_ID_PATTERN) == {}


def test_check_linkage_reports_a_capability_register_with_no_locatable_header(
    tmp_path: Path,
) -> None:
    """The malformed-header failure surfaces end to end through check_linkage as a problem.

    Uses ``_ROADMAP_WITH_MAPPING_AND_PHASE_STATUS`` plus an explicit ``_VALID_MANIFEST`` so the
    only problem in play is the capability-register header under test, not also the unrelated
    roadmap phase-status-header LookupError fix F4 introduced (see
    ``test_check_linkage_accepts_open_capability_cited_in_mapping_section`` for the full
    explanation); otherwise this exact ``len(problems) == 1`` assertion would always fail.
    """
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        "| ID | Capability | State | Notes |\n"
        "| --- | --- | --- | --- |\n"
        "| K1 | Kid thing | open | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING_AND_PHASE_STATUS),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
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
            "--project-plan",
            str(_write_matching_project_plan(tmp_path)),
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
    rows = _MODULE._capability_register_status_rows(lines, _CAP_ID_PATTERN)
    assert rows == [
        (3, "K1", "\U0001f7e1", "needs work"),
        (4, "K2", "✅", ""),
    ]


def test_capability_register_status_rows_raises_on_a_row_too_short_to_reach_docs() -> (
    None
):
    """A capability row with too few cells to reach its table's ``Docs`` column (fix S11) fails
    loud instead of being silently dropped from the walk.

    Before this fix, such a row was simply skipped: it never reached
    ``_check_capability_status_vocabulary``, so a K/G/A/S row that lost its trailing cells (a
    common markdown-table editing slip) would never have its status glyph validated at all,
    escaping the check entirely rather than failing it.
    """
    lines = (_CAPABILITY_TABLE_HEADER + "| K1 | Kid thing |\n").splitlines()
    with pytest.raises(ValueError, match="too short to reach"):
        _MODULE._capability_register_status_rows(lines, _CAP_ID_PATTERN)


def test_check_linkage_reports_a_too_short_capability_row_end_to_end(
    tmp_path: Path,
) -> None:
    """End to end: a truncated capability row surfaces as a problem, not a silently clean run
    (fix S11)."""
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability-register.md",
        _CAPABILITY_TABLE_HEADER + "| K1 | Kid thing |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
    )
    assert any("too short to reach" in p and "K1" in p for p in problems)


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
    the mapping section so the only expected problem is the empty-Notes one.

    Uses ``_ROADMAP_WITH_MAPPING_AND_PHASE_STATUS`` plus an explicit ``_VALID_MANIFEST`` for the
    same reason as ``test_check_linkage_accepts_open_capability_cited_in_mapping_section``: fix
    F4 would otherwise add an unrelated roadmap-header problem and break this exact
    ``len(problems) == 1`` assertion.
    """
    register_path = _write(tmp_path / "register.md", _register())
    capability_path = _write(
        tmp_path / "capability.md",
        _CAPABILITY_TABLE_HEADER + "| K1 | Kid-facing thing | \U0001f7e1 | |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _ROADMAP_WITH_MAPPING_AND_PHASE_STATUS),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        capability_path,
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
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
    summary = _MODULE._capability_summary(capability_path, _CAP_ID_PATTERN)
    assert "3 capability row(s)" in summary
    assert "✅=1" in summary
    assert "\U0001f7e1=1" in summary
    assert "❌=1" in summary


def test_main_prints_capability_summary_line_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI's success path prints the capability glyph summary after the cluster summary.

    Passes an explicit ``--manifest _VALID_MANIFEST`` and adds a matching phase-status table to
    the roadmap: without one, this roadmap's mapping table gives it pipes but no locatable
    phase-status header, which fix F4 now reports as its own problem (see
    ``test_check_linkage_accepts_open_capability_cited_in_mapping_section`` for the full
    explanation) and would break the ``exit_code == 0`` assertion below.
    """
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
        "\n| Phase | Status | Evidence |\n"
        "|-------|--------|----------|\n"
        "| 0 Foundations | ✅ Delivered | done |\n"
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
            "--manifest",
            str(_write(tmp_path / "manifest.toml", _VALID_MANIFEST)),
            "--project-plan",
            str(_write_matching_project_plan(tmp_path)),
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
    rows = _MODULE._capability_register_status_rows(lines, _CAP_ID_PATTERN)
    problems, counts = _MODULE._check_capability_status_vocabulary(
        rows, _MODULE._DEFAULT_CAPABILITY_REGISTER
    )
    assert problems == []
    assert sum(counts.values()) == len(rows)


# ---------------------------------------------------------------------------
# I. id namespace resolution ([namespaces] table)
# ---------------------------------------------------------------------------
#
# _manifest_namespace_pattern is the abstraction every id namespace (uw, debt, al, cap, sq) now
# resolves its pattern through, replacing what used to be six hardcoded module-level regex
# constants. These tests exercise that resolution directly: each namespace declared in a real
# manifest shape resolves to the expected pattern, and a namespace the manifest fails to declare
# (a missing table, a missing field, or an unparsable regex) fails loud rather than silently
# falling back to a permissive default.


@pytest.mark.parametrize(
    ("namespace", "field", "sample_match", "sample_reject"),
    [
        ("uw", "pattern", "UW-A01", "UW-A1"),
        ("debt", "pattern", "C1", "U9a"),
        ("debt", "citation_pattern", "C1", ""),
        ("al", "pattern", "AL-001", "AL-1"),
        ("al", "citation_pattern", "AL-1", ""),
        ("cap", "pattern", "K1", "Z1"),
        ("cap", "citation_pattern", "K1", ""),
        ("sq", "pattern", "SQ-01", "SQ-1"),
    ],
)
def test_manifest_namespace_pattern_resolves_each_declared_namespace_and_field(
    namespace: str, field: str, sample_match: str, sample_reject: str
) -> None:
    """Every [namespaces.<namespace>].<field> in the real manifest compiles and matches the id
    shape it names, for every namespace and field this checker actually consumes."""
    manifest = _MODULE._load_manifest(_MODULE._DEFAULT_MANIFEST, [])
    assert manifest is not None
    problems: list[str] = []
    pattern = _MODULE._manifest_namespace_pattern(
        manifest, _MODULE._DEFAULT_MANIFEST, namespace, field, problems
    )
    assert problems == []
    assert pattern.match(sample_match) is not None
    if sample_reject:
        assert pattern.match(sample_reject) is None


def test_manifest_namespace_pattern_returns_never_matches_for_none_manifest() -> None:
    """A manifest that failed to load resolves every namespace to a pattern matching nothing,
    and does not append a second problem: _load_manifest already reported the root cause."""
    problems: list[str] = []
    pattern = _MODULE._manifest_namespace_pattern(
        None, Path("plan-manifest.toml"), "uw", "pattern", problems
    )
    assert pattern.match("UW-A01") is None
    assert problems == []


def test_manifest_namespace_pattern_reports_a_non_table_namespaces_value() -> None:
    """A [namespaces] value that parsed as a non-table ('namespaces = "x"' is valid TOML) is
    reported by name, instead of reaching the per-entry lookup as if it were an empty table."""
    problems: list[str] = []
    pattern = _MODULE._manifest_namespace_pattern(
        {"namespaces": "x"}, Path("plan-manifest.toml"), "uw", "pattern", problems
    )
    assert pattern.match("UW-A01") is None
    assert len(problems) == 1
    assert "[namespaces]" in problems[0]
    assert "not a table" in problems[0]


def test_manifest_namespace_pattern_reports_a_wholly_absent_namespaces_table() -> None:
    """A manifest with no [namespaces] key at all resolves the same as an empty one (``.get``
    defaults to {}), so the failure surfaces as the specific entry being missing, not a
    top-level '[namespaces] missing' message; either way the pattern still fails closed."""
    problems: list[str] = []
    pattern = _MODULE._manifest_namespace_pattern(
        {"phases": {}}, Path("plan-manifest.toml"), "uw", "pattern", problems
    )
    assert pattern.match("UW-A01") is None
    assert len(problems) == 1
    assert "[namespaces.uw]" in problems[0]
    assert "missing" in problems[0]


def test_manifest_namespace_pattern_reports_a_missing_namespace_entry() -> None:
    """A [namespaces] table missing one specific namespace's sub-table fails loud, naming it."""
    problems: list[str] = []
    pattern = _MODULE._manifest_namespace_pattern(
        {"namespaces": {"debt": {"pattern": "^C\\d+$"}}},
        Path("plan-manifest.toml"),
        "sq",
        "pattern",
        problems,
    )
    assert pattern.match("SQ-01") is None
    assert len(problems) == 1
    assert "[namespaces.sq]" in problems[0]
    assert "missing" in problems[0]


def test_manifest_namespace_pattern_reports_a_missing_field() -> None:
    """A namespace entry present but missing the requested field (e.g. [namespaces.uw] with no
    citation_pattern, which it legitimately never declares) fails loud, naming the field."""
    problems: list[str] = []
    pattern = _MODULE._manifest_namespace_pattern(
        {"namespaces": {"uw": {"pattern": "^UW-[A-M]\\d{2}$"}}},
        Path("plan-manifest.toml"),
        "uw",
        "citation_pattern",
        problems,
    )
    assert pattern.match("UW-A01") is None
    assert len(problems) == 1
    assert "[namespaces.uw].citation_pattern" in problems[0]
    assert "missing" in problems[0]


def test_manifest_namespace_pattern_reports_an_unparsable_regex() -> None:
    """A namespace field that fails to compile as a regex fails loud, naming the bad pattern."""
    problems: list[str] = []
    pattern = _MODULE._manifest_namespace_pattern(
        {"namespaces": {"sq": {"pattern": "^SQ-[0-9$"}}},
        Path("plan-manifest.toml"),
        "sq",
        "pattern",
        problems,
    )
    assert pattern.match("SQ-01") is None
    assert len(problems) == 1
    assert "[namespaces.sq].pattern" in problems[0]


def test_check_linkage_reports_a_namespace_the_manifest_never_declares(
    tmp_path: Path,
) -> None:
    """End to end: a manifest missing the debt namespace fails loud through check_linkage, and
    the debt-linkage check correctly finds no open debt ids (it has no pattern to find them
    with) instead of guessing."""
    manifest_without_debt = re.sub(
        r"\[namespaces\.debt\]\n(?:.+\n)+?\n", "", _VALID_MANIFEST, count=1
    )
    assert "[namespaces.debt]" not in manifest_without_debt
    assert "[namespaces.uw]" in manifest_without_debt
    register_path = _write(tmp_path / "register.md", _register())
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(
            tmp_path / "debt.md",
            _DEBT_TABLE_HEADER + "| C1 | Open | src | Low | fix |\n",
        ),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", manifest_without_debt),
        project_plan_path=_write_matching_project_plan(tmp_path),
    )
    assert any("[namespaces.debt]" in p and "missing" in p for p in problems)
    assert not any("debt 'C1'" in p for p in problems)


# ---------------------------------------------------------------------------
# I.1 SQ-to-register map table (story-structure-improvement-plan.md)
# ---------------------------------------------------------------------------

_SQ_TABLE = (
    "## 11. Relationship to existing planning, and the SQ-to-register map\n\n"
    "| SQ | Register / source | SQ | Register / source |\n"
    "| --- | --- | --- | --- |\n"
    "| SQ-01 | UW-G14 | SQ-02 | UW-C07 |\n"
    "| SQ-03 | new | SQ-04 | new |\n"
)


def test_find_sq_table_header_locates_the_two_pair_header_row() -> None:
    """The header's two id/source column pairs are matched by cell value, not position."""
    lines = _SQ_TABLE.splitlines()
    assert _MODULE._find_sq_table_header(lines) == 2


def test_find_sq_table_header_raises_when_absent() -> None:
    """A document with no SQ-to-register map table fails loud, not with an empty result."""
    with pytest.raises(LookupError, match="no 'SQ \\| Register"):
        _MODULE._find_sq_table_header(["# Nothing here\n"])


def test_sq_table_ids_reads_both_column_positions() -> None:
    """Both the first and third column of every data row contribute an id, in document order."""
    lines = _SQ_TABLE.splitlines()
    header_index = _MODULE._find_sq_table_header(lines)
    ids = _MODULE._sq_table_ids(lines, header_index)
    assert [entry_id for _number, entry_id in ids] == [
        "SQ-01",
        "SQ-02",
        "SQ-03",
        "SQ-04",
    ]


def test_check_sq_namespace_accepts_well_formed_unique_ids() -> None:
    """A small, well-formed SQ table with no duplicate ids reports no problems."""
    problems = _MODULE._check_sq_namespace(
        _SQ_TABLE.splitlines(),
        Path("story-structure-improvement-plan.md"),
        _SQ_ID_PATTERN,
    )
    assert problems == []


def test_check_sq_namespace_rejects_a_malformed_id() -> None:
    """An id that does not match the sq namespace pattern is reported by line and value."""
    lines = (
        "| SQ | Register / source | SQ | Register / source |\n"
        "| --- | --- | --- | --- |\n"
        "| SQ-1 | bad | SQ-02 | ok |\n"
    ).splitlines()
    problems = _MODULE._check_sq_namespace(
        lines, Path("story-structure-improvement-plan.md"), _SQ_ID_PATTERN
    )
    assert len(problems) == 1
    assert "SQ-1" in problems[0]
    assert "does not match the sq namespace pattern" in problems[0]


def test_check_sq_namespace_rejects_a_duplicate_id() -> None:
    """The same id appearing on two rows is reported, naming both line numbers."""
    lines = (
        "| SQ | Register / source | SQ | Register / source |\n"
        "| --- | --- | --- | --- |\n"
        "| SQ-01 | first | SQ-02 | ok |\n"
        "| SQ-01 | duplicate | SQ-03 | ok |\n"
    ).splitlines()
    problems = _MODULE._check_sq_namespace(
        lines, Path("story-structure-improvement-plan.md"), _SQ_ID_PATTERN
    )
    assert len(problems) == 1
    assert "SQ-01" in problems[0]
    assert "2 rows" in problems[0]
    assert "unique" in problems[0]


def test_check_sq_namespace_raises_when_no_table_header_found() -> None:
    """A document with no locatable SQ table header fails loud through _check_sq_namespace too."""
    with pytest.raises(LookupError, match="no 'SQ \\| Register"):
        _MODULE._check_sq_namespace(
            ["# Nothing here\n"],
            Path("story-structure-improvement-plan.md"),
            _SQ_ID_PATTERN,
        )


def test_check_linkage_validates_the_real_sq_to_register_map_table() -> None:
    """The real story-structure-improvement-plan.md's 24-row SQ table validates cleanly through
    check_linkage's default story_structure_plan_path, against the real manifest's sq pattern."""
    problems = _MODULE.check_linkage(
        _MODULE._DEFAULT_REGISTER,
        _MODULE._DEFAULT_ROADMAP,
        _MODULE._DEFAULT_DEBT_REGISTER,
        _MODULE._DEFAULT_LESSONS_LOG,
        _MODULE._DEFAULT_CAPABILITY_REGISTER,
    )
    assert not any("story-structure-improvement-plan.md" in p for p in problems)


def test_check_linkage_reports_a_malformed_sq_id_end_to_end(tmp_path: Path) -> None:
    """A malformed id in a custom story-structure-plan document surfaces through check_linkage."""
    register_path = _write(tmp_path / "register.md", _register())
    bad_sq_plan = _write(
        tmp_path / "story-structure-improvement-plan.md",
        "| SQ | Register / source | SQ | Register / source |\n"
        "| --- | --- | --- | --- |\n"
        "| SQ-1 | bad | SQ-02 | ok |\n",
    )
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=_write(tmp_path / "manifest.toml", _VALID_MANIFEST),
        project_plan_path=_write_matching_project_plan(tmp_path),
        story_structure_plan_path=bad_sq_plan,
    )
    assert any("SQ-1" in p and "does not match" in p for p in problems)


def test_check_linkage_skips_sq_check_when_manifest_is_unreadable(
    tmp_path: Path,
) -> None:
    """When the manifest itself cannot be read, the SQ check does not also run and pile on a
    second, redundant problem: the manifest failure is the one thing reported."""
    register_path = _write(tmp_path / "register.md", _register())
    problems = _MODULE.check_linkage(
        register_path,
        _write(tmp_path / "roadmap.md", _VALID_ROADMAP),
        _write(tmp_path / "debt.md", ""),
        _write(tmp_path / "lessons.md", ""),
        _write_no_open_capability_register(tmp_path),
        manifest_path=tmp_path / "missing-manifest.toml",
    )
    assert any("cannot read" in p for p in problems)
    assert not any("story-structure-improvement-plan.md" in p for p in problems)


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


@pytest.mark.parametrize("column_name", ["Issues", "Issue"])
def test_resolve_cluster_issues_index_accepts_both_column_spellings(
    column_name: str,
) -> None:
    """Both the plural and singular spellings of the issue-citation column resolve to the same
    index (fix F1); the register's cluster tables use both spellings in practice."""
    header_cells = ["ID", column_name, "Theme", "Phase", "Status"]
    assert _MODULE._resolve_cluster_issues_index(header_cells) == 1


def test_resolve_cluster_issues_index_returns_none_when_neither_spelling_is_present() -> (
    None
):
    """A cluster header with no issue-citation column at all is None, not a spurious match."""
    header_cells = ["ID", "Item", "Phase", "Status"]
    assert _MODULE._resolve_cluster_issues_index(header_cells) is None


def test_collect_register_issue_citations_reads_the_singular_issue_column(
    tmp_path: Path,
) -> None:
    """A cluster whose header spells the column ``Issue`` (singular) has its bare #NNN references
    collected exactly like the plural ``Issues`` spelling (fix F1).

    Before this fix, ``_resolve_cluster_issues_index`` matched only ``"Issues"``, so a cluster
    headed ``| ID | Item | Issue | Status |`` had every row of its issue-citation column silently
    dropped: those citations were never checked against GitHub at all, and the check reported a
    clean result on a table it had not actually read.
    """
    register = _register(
        "## Cluster D: untracked GitHub issues\n\n"
        "| ID | Item | Issue | Phase | Status |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| UW-D01 | Something | #251 | 5 | unscheduled |\n",
    )
    register_path = _write(tmp_path / "register.md", register)
    lines = register_path.read_text(encoding="utf-8").splitlines()
    clusters = _MODULE._find_clusters(lines)
    citations = _MODULE._collect_register_issue_citations(clusters)
    assert citations[251] == [("UW-D01", "unscheduled")]


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
    text = "See #460 and issue:472 in the same paragraph, plus a bare #99."
    assert _MODULE._extract_issue_numbers_from_text(text) == {460, 472, 99}


def test_extract_issue_numbers_from_text_excludes_a_pr_reference() -> None:
    """ "PR #99" is a pull-request reference, not an issue citation (fix F8).

    This is a false-positive fix, not a relaxation: this tree writes pull-request references as
    "PR #NNN" in several planning documents, and the issue and PR id spaces overlap, so treating
    a PR reference as an issue citation could silently satisfy an issue's citation requirement
    with a PR number that names something else entirely.
    """
    assert _MODULE._extract_issue_numbers_from_text("See PR #99 for the fix.") == set()


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


def test_planning_docs_cited_issue_numbers_scans_toml_files_too(tmp_path: Path) -> None:
    """A citation living in a bare ``#NNN`` inside a ``.toml`` file (fix S8), such as
    ``plan-manifest.toml``'s own ``Phase = "issue:NNN"`` style values, is picked up: the
    citation scan used to be markdown-only, so an issue cited only from plan-manifest.toml was
    invisible to the orphan check and reported as untracked even though the manifest named it.
    """
    _write(tmp_path / "plan-manifest.toml", '# tracks #4\nnote = "issue:5"\n')
    assert _MODULE._planning_docs_cited_issue_numbers(tmp_path) == {4, 5}


def test_check_issue_orphans_flags_an_uncited_open_issue_without_the_unplanned_label() -> (
    None
):
    """An open issue cited nowhere and carrying no 'unplanned' label is an orphan.

    Reworded (fix F): the message now states the rule broken and the remedy, rather than a bare
    ``"#NNN <title>"`` string that named a fact without naming what to do about it. Asserted on
    the issue number plus a distinctive, stable phrase rather than the full message verbatim
    (brittle to reword) or a bare non-empty check (vacuous).
    """
    issues: list[dict[str, Any]] = [
        {"number": 5, "state": "OPEN", "title": "Do a thing", "labels": []}
    ]
    problems = _MODULE._check_issue_orphans(issues, cited_numbers=set())
    assert len(problems) == 1
    assert "#5" in problems[0]
    assert "is OPEN but is cited in no document under docs/planning/" in problems[0]


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


def test_validate_github_issue_payload_flags_a_non_dict_entry() -> None:
    """An entry that is not an object at all (fix F5) is reported by position, not left to reach
    ``entry.get("number")`` as an AttributeError."""
    problems: list[str] = []
    result = _MODULE._validate_github_issue_payload(["not an object"], problems)
    assert result is None
    assert len(problems) == 1
    assert "entry 0 is str, not an issue object" in problems[0]


def test_validate_github_issue_payload_flags_a_non_integer_number() -> None:
    """An entry whose ``number`` is not an integer (fix F5) is reported instead of reaching
    ``_check_cited_issues_not_closed``'s ``issue["number"]`` index as a bad key."""
    problems: list[str] = []
    result = _MODULE._validate_github_issue_payload(
        [{"number": "12", "labels": []}], problems
    )
    assert result is None
    assert len(problems) == 1
    assert "number='12'" in problems[0]


def test_validate_github_issue_payload_flags_a_boolean_number() -> None:
    """A JSON ``true``/``false`` for ``number`` (fix F5) is rejected explicitly: ``bool`` is an
    ``int`` subclass in Python, so an unguarded ``isinstance(number, int)`` check would silently
    accept ``true`` as issue number 1."""
    problems: list[str] = []
    result = _MODULE._validate_github_issue_payload(
        [{"number": True, "labels": []}], problems
    )
    assert result is None
    assert len(problems) == 1
    assert "number=True" in problems[0]


def test_validate_github_issue_payload_flags_labels_that_are_not_a_list_of_objects() -> (
    None
):
    """An entry whose ``labels`` is not a list of label objects (fix F5) is reported instead of
    reaching ``_check_issue_orphans``'s ``label.get("name")`` call as a crash."""
    problems: list[str] = []
    result = _MODULE._validate_github_issue_payload(
        [{"number": 1, "labels": ["unplanned"]}], problems
    )
    assert result is None
    assert len(problems) == 1
    assert "issue 1" in problems[0]
    assert "not a list of label objects" in problems[0]


def test_validate_github_issue_payload_accepts_a_well_shaped_payload() -> None:
    """A payload matching every assumed shape passes through unchanged with no problems."""
    problems: list[str] = []
    payload = [
        {"number": 1, "state": "OPEN", "title": "x", "labels": [{"name": "bug"}]}
    ]
    result = _MODULE._validate_github_issue_payload(payload, problems)
    assert result == payload
    assert problems == []


def test_fetch_github_issues_reports_every_shape_problem_joined_in_one_message() -> (
    None
):
    """Multiple malformed entries in one gh response (fix F5) are reported together, by position,
    in a single problem rather than only the first one found or a bare traceback."""
    problems: list[str] = []
    completed = _completed(
        0,
        '[{"number": "bad", "labels": []}, "not an object"]',
    )
    with patch("subprocess.run", return_value=completed):
        issues = _MODULE._fetch_github_issues(problems)
    assert issues is None
    assert len(problems) == 1
    assert "entry 0 has number='bad'" in problems[0]
    assert "entry 1 is str, not an issue object" in problems[0]


def _issue_json(count: int) -> str:
    """Build a ``gh issue list`` JSON payload of ``count`` minimal, well-shaped issues."""
    return json.dumps(
        [
            {"number": n, "state": "OPEN", "title": f"issue {n}", "labels": []}
            for n in range(1, count + 1)
        ]
    )


def test_fetch_github_issues_returns_the_full_list_one_below_the_truncation_limit() -> (
    None
):
    """A result one short of ``_GH_ISSUE_LIST_LIMIT`` is trusted as complete and returned."""
    problems: list[str] = []
    count = _MODULE._GH_ISSUE_LIST_LIMIT - 1
    completed = _completed(0, _issue_json(count))
    with patch("subprocess.run", return_value=completed):
        issues = _MODULE._fetch_github_issues(problems)
    assert problems == []
    assert issues is not None
    assert len(issues) == count


def test_fetch_github_issues_reports_truncation_at_exactly_the_limit() -> None:
    """A result exactly at ``_GH_ISSUE_LIST_LIMIT`` (fix F6) is treated as possibly truncated and
    reported, not trusted as a complete, coincidentally round-numbered result.

    Before this fix, a repository whose issue count reached the ``--limit`` cap had its result
    silently accepted as complete: real issues past the cap would read as nonexistent to
    ``_check_cited_issues_not_closed`` and as orphans to ``_check_issue_orphans``, both worse than
    reporting nothing.
    """
    problems: list[str] = []
    count = _MODULE._GH_ISSUE_LIST_LIMIT
    completed = _completed(0, _issue_json(count))
    with patch("subprocess.run", return_value=completed):
        issues = _MODULE._fetch_github_issues(problems)
    assert issues is None
    assert len(problems) == 1
    assert str(count) in problems[0]
    assert "may be truncated" in problems[0]


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
    assert len(problems) == 1
    assert "#7" in problems[0]
    assert "is OPEN but is cited in no document under docs/planning/" in problems[0]


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
    assert "#7" in out
    assert "Untracked" in out
    assert "is OPEN but is cited in no document under docs/planning/" in out


# ---------------------------------------------------------------------------
# PROJECT-PLAN.md track-2 phase status
# ---------------------------------------------------------------------------

_TRACK2_MANIFEST: dict[str, object] = {
    "phases": {
        "5": {"track": 1, "shipped": "partial", "usable": "partial"},
        "8": {"track": 2, "shipped": "no", "usable": "no"},
    },
    "status_vocabulary": {
        "partial/partial": "partially delivered",
        "no/no": "not started",
    },
}


def test_project_plan_phase_status_lines_maps_each_section_to_its_status_line() -> None:
    """Each '## Phase <token>:' heading binds to the first **Status**: line beneath it."""
    lines = (
        "### Phase 8: iOS Shell (3-5 weeks)\n"
        "**Branch**: `feat/phase-8`\n"
        "**Status**: ⏸️ Not started\n"
        "### Phase 9: Launch\n"
        "**Status**: ⏸️ Not started\n"
    ).splitlines()
    assert _MODULE._project_plan_phase_status_lines(lines) == {
        "8": (3, "⏸️ Not started"),
        "9": (5, "⏸️ Not started"),
    }


def test_project_plan_phase_status_lines_takes_only_the_first_status_line_per_section() -> (
    None
):
    """A later **Status**: line inside the same section does not overwrite the section's own."""
    lines = (
        "### Phase 8: iOS Shell\n**Status**: ⏸️ Not started\n**Status**: ✅ Delivered\n"
    ).splitlines()
    assert _MODULE._project_plan_phase_status_lines(lines) == {
        "8": (2, "⏸️ Not started")
    }


def test_normalize_project_plan_status_prose_keeps_only_the_first_clause() -> None:
    """A status line running on into wrapped narrative normalizes to its bare term."""
    assert (
        _MODULE._normalize_project_plan_status_prose(
            "🟡 Partially delivered, ahead of schedule, corrected 2026-07-20 (this section"
        )
        == "partially delivered"
    )


def test_check_project_plan_phase_status_accepts_a_matching_track2_section() -> None:
    """A track-2 status term the manifest derives is clean."""
    lines = ("### Phase 8: iOS Shell\n**Status**: ⏸️ Not started\n").splitlines()
    assert (
        _MODULE._check_project_plan_phase_status(
            lines, Path("PROJECT-PLAN.md"), _TRACK2_MANIFEST
        )
        == []
    )


def test_check_project_plan_phase_status_rejects_a_drifted_track2_status() -> None:
    """A track-2 status term the manifest does not derive is reported with both values."""
    lines = ("### Phase 8: iOS Shell\n**Status**: ✅ Delivered\n").splitlines()
    problems = _MODULE._check_project_plan_phase_status(
        lines, Path("PROJECT-PLAN.md"), _TRACK2_MANIFEST
    )
    assert len(problems) == 1
    assert "phase '8'" in problems[0]
    assert "normalized to 'delivered'" in problems[0]
    assert "derives 'not started'" in problems[0]


def test_check_project_plan_phase_status_reports_a_track2_phase_with_no_section() -> (
    None
):
    """A manifest track-2 phase PROJECT-PLAN.md never narrates is reported, not skipped.

    This is the regression the check exists for: roadmap.md does not cover track-2 phases, so
    a phase missing from both documents previously had its status validated against nothing.
    """
    problems = _MODULE._check_project_plan_phase_status(
        ["# Plan", "no phase sections here"], Path("PROJECT-PLAN.md"), _TRACK2_MANIFEST
    )
    assert len(problems) == 1
    assert "track-2 phase '8' has no '## Phase 8:' section" in problems[0]
    assert "checked against nothing" in problems[0]


def test_check_project_plan_phase_status_ignores_track1_phases() -> None:
    """Track-1 phases are the roadmap check's business; a missing section here is not a finding."""
    lines = ("### Phase 8: iOS Shell\n**Status**: ⏸️ Not started\n").splitlines()
    problems = _MODULE._check_project_plan_phase_status(
        lines, Path("PROJECT-PLAN.md"), _TRACK2_MANIFEST
    )
    assert not any("'5'" in problem for problem in problems)
