#!/usr/bin/env python3
"""Validate the work-linkage contract in the unscheduled-work register.

The register (``docs/planning/unscheduled-work-register.md``) is the join table that gives
every piece of directed-but-unscheduled work a phase. Its "## The linkage contract" section is
the enforced specification, not advice: every row in every cluster table must resolve to exactly
one disposition (``scheduled``, ``blocked``, ``decision``, ``verify``, or ``done``), and the three
other registers it links (the R1 deferred-debt register, the authoring lessons log, and the
capability register) must have every still-open row cited back into the register. A row with a
status but no evidence, or a ``Phase`` value outside the closed vocabulary, is an orphan; orphan
count is the health metric this script exists to keep at zero.

Checks:

Within the unscheduled-work register itself, for every cluster table (``## Cluster <letter>:``):

1. Every id matches ``UW-[A-M]NN``.
2. Every ``Status`` is one of: unscheduled, blocked, decision, verify, done.
3. Where a ``Phase`` column exists (clusters L and M have none), its value is in the closed
   phase vocabulary, which is read from the manifest the run actually loaded.
4. A ``Phase`` value never holds more than one value (no comma).
5. A ``Phase`` value never repeats a ``Status`` value.
6. A ``Phase`` value is never empty on a row whose ``Status`` still needs a phase home (every
   status except ``done``, whose evidence is a PR reference rather than a future phase).
7. Ids are unique across the whole register, not just within one cluster.

Vocabulary drift: ``docs/planning/plan-manifest.toml`` (the "plan manifest") is the source of
truth for the phase vocabulary, the phase-to-rung mapping, and the two-axis (``shipped``/
``usable``) status model; ``roadmap.md`` is checked against it, not the other way around. This
script parses ``## Phase`` headings (and the ``2b``/``4a``/``4b`` sub-headings that do not follow
that exact shape) out of ``roadmap.md`` and fails if the manifest's track-1 phase set disagrees
with what the roadmap actually contains, so a new phase added to the roadmap without a matching
manifest entry is caught here rather than discovered later. Two further checks guard the manifest
and the roadmap's prose against each other:

* ``_check_manifest_integrity``: the manifest is structurally present (the ``[phases]`` and
  ``[rungs]`` tables exist, are tables, and are non-empty, and the ``R1``/``R2``/``R3`` rungs are
  declared) and then internally consistent (every rung's phase references exist,
  ``requires_phases``/``excludes_phases`` are disjoint, the rungs are monotonic, every phase's
  status pair has a matching ``[status_vocabulary]`` entry, and Phase 7 does not gate R2). The
  structural precondition runs first and short-circuits the rest: a manifest missing ``[rungs]``
  entirely would otherwise pass every one of those six checks vacuously.
* ``_check_roadmap_phase_status``: the roadmap's phase-status table prose (for example
  "Substantially delivered") matches the term the manifest's ``[status_vocabulary]`` derives from
  that phase's ``(shipped, usable)`` pair, and its leading glyph matches that phase's ``shipped``
  axis. A roadmap that carries tables but no locatable phase-status header is reported rather
  than skipped, since a renamed header would otherwise drop every checked row and still pass.

The manifest named on the command line is the only one a run consults. The register's own
``Phase`` cell vocabulary is derived from it and threaded down to the row checks, so a
``--manifest`` run cannot end up validating the register against one manifest and the roadmap
against another. An unloadable manifest yields an empty vocabulary, which rejects every phase
token; the load failure itself is reported separately, so the cause is named, not inferred.

Cross-register linkage:

1. Every row in ``r1-deferred-debt-register.md`` whose first cell is a debt id (``C\\d+``,
   ``GS\\d+``, ``U\\d+``, ``T\\d+``, ``P\\d+``, or ``SL\\d+``) and which is not marked
   ``[Closed]`` or ``[Resolved]`` (the register uses both markers interchangeably) must be cited
   somewhere in cluster B of the unscheduled register.
2. Every lesson in ``authoring-lessons-log.md`` whose ``Status`` is not ``applied``, ``rejected``,
   or ``superseded`` must be cited somewhere in cluster C of the unscheduled register.
3. Every row in ``capability-register.md`` (four tables: K, G, A, S) whose ``Docs`` cell is not
   the done checkmark must appear in ``roadmap.md``'s "Where every open register item lands"
   mapping section.

Two further checks are opt-in, because they need network access and ``gh`` auth that
pre-commit's offline posture cannot assume: ``--check-issues`` (no register row cites a GitHub
issue that is CLOSED while the row itself is not done, and every cited issue exists) and
``--check-issue-orphans`` (every OPEN issue is cited by some markdown or TOML document under
``docs/planning/``, or carries the ``unplanned`` label). Both share one capped ``gh issue list``
call, pinned to this repository's own checkout, that refuses to hand back a possibly-truncated
result.

Usage::

    uv run python scripts/check_work_linkage.py
    uv run python scripts/check_work_linkage.py --register path/to/register.md
    uv run python scripts/check_work_linkage.py --check-issues --check-issue-orphans

Exit codes:
    0 - every check passed.
    1 - at least one check failed, or a required document could not be read.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_REGISTER = _REPO_ROOT / "docs" / "planning" / "unscheduled-work-register.md"
_DEFAULT_ROADMAP = _REPO_ROOT / "docs" / "planning" / "roadmap.md"
_DEFAULT_DEBT_REGISTER = (
    _REPO_ROOT / "docs" / "planning" / "r1-deferred-debt-register.md"
)
_DEFAULT_LESSONS_LOG = _REPO_ROOT / "docs" / "planning" / "authoring-lessons-log.md"
_DEFAULT_CAPABILITY_REGISTER = (
    _REPO_ROOT / "docs" / "planning" / "capability-register.md"
)
_DEFAULT_MANIFEST = _REPO_ROOT / "docs" / "planning" / "plan-manifest.toml"
# roadmap.md details phases 0-5 and says so ("Phases 6 through 9 ... are not detailed here").
# Track-2 phases are narrated here instead, which is why their status needs its own check.
_DEFAULT_PROJECT_PLAN = _REPO_ROOT / "docs" / "planning" / "PROJECT-PLAN.md"

_UW_ID_RE = re.compile(r"^UW-[A-M]\d{2}$")

_STATUSES = frozenset({"unscheduled", "blocked", "decision", "verify", "done"})
# Every status except `done` still needs the phase the row will land in: the linkage contract's
# "Not allowed" list spells this out for `blocked` and `decision` ("a row in either state still
# needs the phase it will land in once resolved"), and `verify` is a row that will land somewhere
# once confirmed. `done` is the one status whose required evidence is a PR/commit/issue reference
# rather than a future phase, so an empty Phase on a closed row is not an orphan.
_STATUSES_REQUIRING_PHASE = _STATUSES - {"done"}

_MANIFEST_STATUS_VALUES = frozenset({"yes", "partial", "no"})
# The top-level manifest tables every downstream integrity check reads, and the rungs those
# checks name directly. Absent or empty, each of those checks iterates nothing and reports a
# clean manifest, so their structural presence is asserted before any of them runs.
_MANIFEST_REQUIRED_TABLES = ("phases", "rungs")
_MANIFEST_REQUIRED_RUNGS = ("R1", "R2", "R3")


def _load_manifest(path: Path, problems: list[str]) -> dict[str, Any] | None:
    """Read and parse ``plan-manifest.toml``, recording a problem instead of raising.

    Uses the standard-library ``tomllib`` parser rather than a third-party TOML or YAML
    library: this script also runs under pre-commit and in CI, contexts where the dev extras
    that a third-party parser would live in may not be installed.

    ``tomllib.load`` decodes the file as UTF-8 before it parses anything, so invalid UTF-8
    surfaces as ``UnicodeDecodeError`` rather than ``TOMLDecodeError``. That is caught here for
    the same reason ``_read_lines`` catches it: an undecodable planning document is a reported
    problem, not a traceback, and the two readers must not disagree about which of them a
    corrupt byte crashes.

    Args:
        path: The plan manifest TOML file.
        problems: The running problem list; a read, decode, or parse failure is appended here.

    Returns:
        dict[str, Any] | None: The parsed manifest, or None if it could not be read or parsed.
    """
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, UnicodeDecodeError) as exc:
        problems.append(f"cannot read {path}: {exc}")
        return None
    except tomllib.TOMLDecodeError as exc:
        problems.append(f"cannot parse {path}: {exc}")
        return None


def _manifest_phases_for_track(manifest: dict[str, Any], track: int) -> frozenset[str]:
    """Return the phase tokens in a parsed manifest that belong to one release track.

    Args:
        manifest: The parsed plan-manifest.toml document, as returned by ``_load_manifest``.
        track: The track number to filter phases by (1 for the R1/R2/R3 web ladder, 2 for the
            App Store track).

    Returns:
        frozenset[str]: Every phase token whose ``[phases.<token>].track`` field equals
            ``track``.
    """
    phases = manifest.get("phases", {})
    if not isinstance(phases, dict):
        return frozenset()
    return frozenset(
        token
        for token, entry in phases.items()
        if isinstance(entry, dict) and entry.get("track") == track
    )


def _manifest_phase_vocabulary(manifest: dict[str, Any] | None) -> frozenset[str]:
    """Return every phase token the given manifest declares, across all tracks.

    This is the vocabulary ``_check_row_phase`` validates register ``Phase`` cells against. It is
    derived from the manifest ``check_linkage`` actually loaded rather than from a module-level
    default, so a run passing ``--manifest alt.toml`` validates every document against that one
    manifest instead of splitting the run across two vocabularies.

    Args:
        manifest: The parsed plan-manifest.toml document, or None when it could not be loaded.

    Returns:
        frozenset[str]: Every ``[phases.<token>]`` key declared, or an empty set when the
            manifest is missing or its ``[phases]`` table is not a table.
    """
    # #CRITICAL: data integrity: a manifest that could not be loaded must not leave the phase
    # vocabulary permissive, or an unreadable manifest would silently turn the closed-vocabulary
    # check into a no-op that accepts any Phase value.
    # #VERIFY: None and a non-table [phases] both return an empty frozenset here, so every
    # non-sentinel Phase value is rejected; check_linkage separately reports the load failure
    # itself, so the root cause is named rather than inferred from the symptom.
    if manifest is None:
        return frozenset()
    phases = manifest.get("phases", {})
    if not isinstance(phases, dict):
        return frozenset()
    return frozenset(phases)


_RELEASE_RUNGS = frozenset({"R1", "R2", "R3"})
_NAMED_WORKSTREAMS = frozenset({"content", "now"})
_SENTINELS_EXACT = frozenset({"CI hygiene", "doc", "recurring", "post-launch"})
_MILESTONE_RE = re.compile(r"^M[0-7](\.\d+)?$")
_EXTERNAL_RE = re.compile(r"^external:.+$")
_ISSUE_RE = re.compile(r"^issue:\d+$")

_CLUSTER_HEADING_RE = re.compile(r"^## Cluster ([A-M]):")

# Debt ids in r1-deferred-debt-register.md, matched as a whole first cell.
_DEBT_ROW_ID_RE = re.compile(r"^(?:C\d+|GS\d+|U\d+|T\d+|P\d+|SL\d+)$")
# The same alternation, used to find citations inside prose (word-bounded, no anchors).
_DEBT_ID_RE = re.compile(r"\b(?:C\d+|GS\d+|U\d+|T\d+|P\d+|SL\d+)\b")

_AL_ROW_ID_RE = re.compile(r"^AL-\d{3}$")
_AL_ID_RE = re.compile(r"\bAL-\d+\b")
_AL_CLOSED_STATUSES = frozenset({"applied", "rejected", "superseded"})

# Capability ids in capability-register.md (four tables: K, G, A, S), matched as a whole first
# cell, and the same alternation word-bounded for finding citations inside roadmap.md prose.
_CAP_ROW_ID_RE = re.compile(r"^[KGAS]\d+$")
_CAP_ID_RE = re.compile(r"\b[KGAS]\d+\b")
# The three status glyphs, defined once and derived everywhere else (the recognised-glyph set,
# the open-glyph set, and the CLI summary's display order all read from these), so a fourth copy
# of the glyph literals cannot drift from the register's actual vocabulary.
_CAP_DONE_MARK = "✅"  # the register's "done" checkmark cell value (U+2705).
_CAP_PARTIAL_MARK = "🟡"  # partial (U+1F7E1).
_CAP_MISSING_MARK = "❌"  # missing (U+274C).
# Display order, worst-last, for the CLI's per-glyph tally.
_CAP_STATUS_GLYPH_ORDER = (_CAP_DONE_MARK, _CAP_PARTIAL_MARK, _CAP_MISSING_MARK)
_CAP_OPEN_GLYPHS = frozenset({_CAP_PARTIAL_MARK, _CAP_MISSING_MARK})
_CAP_STATUS_GLYPHS = frozenset(_CAP_STATUS_GLYPH_ORDER)

# An "issue:NNN" Phase cell, capturing the number (the vocabulary check, _ISSUE_RE above, only
# needs to confirm the shape; the GitHub issue checks need the number itself).
_ISSUE_PHASE_NUMBER_RE = re.compile(r"^issue:(\d+)$")
# A bare "#NNN" reference, used both inside a cluster D row's Issues column and when scanning
# the wider docs/planning/ tree for citations (the orphan check). The guards on both sides are
# load-bearing, not defensive decoration: this pattern decides whether an open issue counts as
# cited, so anything it over-matches silently converts an orphaned issue into a "cited" one.
#   * the leading `(?<![#0-9A-Za-z_])` rejects a "#" that is itself part of a longer token or a
#     heading run, so "###5" and the tail of a hex colour never yield a number;
#   * the `(?<!PR )` / `(?<!pr )` / `(?<!PRs )` guards reject a pull-request reference, which
#     this tree writes as "PR #270" in several planning documents and which is not an issue;
#   * the trailing `(?![0-9A-Za-z_-])` rejects "#4a4a4a" (a hex colour) and "#4-heading" (a
#     markdown anchor), and deliberately also rejects the first half of a "#105-#109" span,
#     since dropping an ambiguous reference over-reports orphans while keeping one under-reports
#     them, and only under-reporting is silent.
_BARE_ISSUE_REF_RE = re.compile(
    r"(?<![#0-9A-Za-z_])(?<!PR )(?<!pr )(?<!PRs )#(\d+)(?![0-9A-Za-z_-])"
)
# An inline "issue:NNN" mention in prose (not anchored like _ISSUE_PHASE_NUMBER_RE, since prose
# can carry it mid-sentence rather than as a whole Phase cell value).
_PROSE_ISSUE_REF_RE = re.compile(r"\bissue:(\d+)\b")

# #ASSUME: external resource: gh issue list over the network can hang on a stalled connection.
# #VERIFY: _fetch_github_issues passes this as subprocess.run's timeout, so a hung call becomes
# a reported problem (TimeoutExpired caught explicitly) rather than blocking the run forever.
_GH_ISSUE_LIST_TIMEOUT_SECONDS = 30
# #CRITICAL: data integrity: gh issue list truncates silently at --limit. A truncated set makes
# --check-issues report real issues as "does not exist on GitHub" and makes --check-issue-orphans
# miss every open issue past the cut, both of which read as findings about the documents rather
# than as a fetch that came back short.
# #VERIFY: _fetch_github_issues compares the returned count against this bound and reports a
# problem instead of returning a partial list, so no check ever runs on truncated data.
_GH_ISSUE_LIST_LIMIT = 500

# The mapping section roadmap.md's linkage contract points at for capability-register linkage.
_ROADMAP_MAPPING_HEADING = "### Where every open register item lands"

# The header cell names a cluster table uses for its GitHub-issue citation column. Both
# spellings are live in the register today, and a cluster is free to use either.
_CLUSTER_ISSUE_COLUMN_NAMES = ("Issues", "Issue")

# The deliberate, explicit escape hatch from the "every open issue needs a citation" rule.
_UNPLANNED_LABEL = "unplanned"
# File suffixes the orphan check scans for citations. plan-manifest.toml is part of the plan's
# machine-readable spine, so a citation living there satisfies the rule exactly as a markdown
# one does; scanning markdown alone made the manifest unable to give an issue a home.
_PLANNING_DOC_SUFFIXES = frozenset({".md", ".toml"})

# "`SL1` through `SL10`" style natural-language ranges: a same-prefix id range spelled out with
# "through" instead of listing every id, used once in cluster B for the ten SL debts (each id is
# itself wrapped in backticks as inline code, hence the optional backtick on both sides).
# Expanding it is a deliberate reading of the document's own convention, not a relaxation of the
# check: the alternative is flagging SL2..SL9 as false-positive orphans despite being plainly in
# scope. The optional hyphen in the prefix group is what lets the lessons log's own id shape
# ("AL-001 through AL-005") expand: without it the prefix stopped at "AL", the backreference
# could not match "AL-005", and every id between the two endpoints became a false orphan.
_THROUGH_RANGE_RE = re.compile(r"`?\b([A-Z]{1,2}-?)(\d+)`?\s+through\s+`?\1(\d+)`?\b")
# A same-prefix range wider than this is almost certainly a typo (transposed digits, wrong
# id) rather than a real citation span; expanding it anyway would silently manufacture
# thousands of ids that were never actually cited, masking the typo as ordinary bulk linkage.
# A reversed range ("SL10 through SL2") is the same class of typo and is reported the same way:
# the span bound alone never catches it, because a negative span passes any upper bound and the
# expansion quietly produces nothing.
_THROUGH_RANGE_MAX_SPAN = 100

# "## Phase <N>" headings in roadmap.md, for example "## Phase 4c: Family loops...".
_ROADMAP_PHASE_HEADING_RE = re.compile(r"^## Phase (\d+[a-zA-Z]?)\b")
# "### Phase 2b (closed)": a lettered phase that is its own sub-heading rather than a "## Phase"
# heading.
_ROADMAP_SUB_PHASE_HEADING_RE = re.compile(r"^### Phase (\d+[a-zA-Z])\b")
# "### Deliverables (4a, in R1)" / "### Deliverables (4b, after R1...)": 4a and 4b never appear as
# their own "## Phase" or "### Phase" heading, only nested inside Phase 4's deliverables headings.
_ROADMAP_DELIVERABLES_RE = re.compile(r"Deliverables \((\d+[a-zA-Z])\b")
# Phase 4's own "## Phase 4:" heading is a container for 4a/4b, not itself a schedulable phase
# token (the closed vocabulary has "4a" and "4b" but no bare "4"), so it is excluded on sight.
_ROADMAP_CONTAINER_PHASE = "4"

# A pipe that is not preceded by a backslash: the markdown table cell delimiter. Compiled once at
# module scope rather than per call, since _split_row runs on every line of five documents plus
# an rglob sweep of the whole planning tree.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def _split_row(line: str) -> list[str]:
    """Split one markdown table row into its trimmed cell values.

    A literal pipe inside a cell is written escaped (``\\|``); the split honours that escape and
    then unescapes it, so such a cell counts as one column rather than being torn in two.

    Args:
        line: A single table line, with or without surrounding pipes.

    Returns:
        list[str]: The cell values, with the outer empty strings from the leading and trailing
            pipes removed.
    """
    cells = [
        cell.strip().replace("\\|", "|")
        for cell in _UNESCAPED_PIPE_RE.split(line.strip())
    ]
    if cells and not cells[0]:
        cells = cells[1:]
    if cells and not cells[-1]:
        cells = cells[:-1]
    return cells


def _is_separator(cells: list[str]) -> bool:
    """Report whether a split row is a markdown header separator (``---``).

    Args:
        cells: A row's split cell values.

    Returns:
        bool: True when every cell is made up only of ``-`` and ``:`` characters.
    """
    return bool(cells) and all(set(cell) <= {"-", ":"} and cell for cell in cells)


def _read_lines(path: Path, problems: list[str]) -> list[str] | None:
    """Read a document's lines, recording a problem instead of raising on failure.

    Args:
        path: The document to read.
        problems: The running problem list; a read failure is appended here.

    Returns:
        list[str] | None: The document's lines, or None if it could not be read.
    """
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        problems.append(f"cannot read {path}: {exc}")
        return None


def _phase_in_vocabulary(phase: str, phase_vocabulary: frozenset[str]) -> bool:
    """Report whether a ``Phase`` value is in the linkage contract's closed vocabulary.

    Args:
        phase: A single, already-trimmed ``Phase`` cell value (never comma-separated; callers
            check that separately).
        phase_vocabulary: Every phase token the run's manifest declares, as returned by
            ``_manifest_phase_vocabulary``. Passed in rather than read from module state so the
            manifest named on the command line is the one register rows are validated against;
            an empty set (an unloadable manifest) rejects every phase token, which is the
            intended fail-closed behaviour.

    Returns:
        bool: True when the value is a recognised phase, milestone, release rung, named
            workstream, or sentinel.
    """
    return (
        phase in phase_vocabulary
        or phase in _RELEASE_RUNGS
        or phase in _NAMED_WORKSTREAMS
        or phase in _SENTINELS_EXACT
        or bool(_MILESTONE_RE.match(phase))
        or bool(_EXTERNAL_RE.match(phase))
        or bool(_ISSUE_RE.match(phase))
    )


def _find_id_header(lines: list[str], start: int, end: int) -> tuple[int, list[str]]:
    """Return the 1-based line number and cells of a cluster's table header row.

    The header is identified by its first cell (``ID``) rather than by position, so the prose
    introducing each cluster can be edited freely.

    Args:
        lines: The register's lines.
        start: 0-based index of the first line to search (the cluster's heading line).
        end: 0-based index one past the last line to search (the next cluster heading, or the
            end of the file).

    Returns:
        tuple[int, list[str]]: The header's 1-based line number and its cells.

    Raises:
        LookupError: If no row starting with the cell ``ID`` is found in range.
    """
    for index in range(start, end):
        line = lines[index]
        if "|" not in line:
            continue
        cells = _split_row(line)
        if cells and cells[0] == "ID":
            return index + 1, cells
    msg = f"no table header (a row starting with 'ID') found between lines {start + 1} and {end}"
    raise LookupError(msg)


def _collect_rows(
    lines: list[str], header_line: int, end: int
) -> list[tuple[int, list[str]]]:
    """Return the data rows following a cluster table's header, bounded to that cluster.

    Args:
        lines: The register's lines.
        header_line: 1-based line number of the header row.
        end: 0-based index one past the last line that belongs to this cluster.

    Returns:
        list[tuple[int, list[str]]]: One (1-based line number, cells) pair per data row, stopping
            at the first line that is not part of the table or at ``end``, whichever comes first.
    """
    rows: list[tuple[int, list[str]]] = []
    for offset, line in enumerate(lines[header_line:end], start=header_line + 1):
        if "|" not in line:
            break
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        rows.append((offset, cells))
    return rows


def _find_clusters(
    lines: list[str],
) -> dict[str, tuple[list[str], list[tuple[int, list[str]]]]]:
    """Locate every ``## Cluster <letter>:`` table in the register.

    Args:
        lines: The register's lines.

    Returns:
        dict[str, tuple[list[str], list[tuple[int, list[str]]]]]: Cluster letter mapped to its
            header cells and its (line number, cells) data rows.

    Raises:
        LookupError: If one or more ``## Cluster <letter>:`` sections have no locatable
            ``ID`` table header. A cluster silently omitted here would silently validate
            zero rows, defeating the whole point of the check.
    """
    headings = [
        (index, match.group(1))
        for index, line in enumerate(lines)
        if (match := _CLUSTER_HEADING_RE.match(line)) is not None
    ]
    clusters: dict[str, tuple[list[str], list[tuple[int, list[str]]]]] = {}
    unlocatable: list[str] = []
    for position, (start, letter) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        try:
            header_line, header_cells = _find_id_header(lines, start, end)
        except LookupError:
            unlocatable.append(letter)
            continue
        rows = _collect_rows(lines, header_line, end)
        clusters[letter] = (header_cells, rows)
    if unlocatable:
        joined = ", ".join(unlocatable)
        msg = f"cluster(s) {joined} have a '## Cluster <letter>:' heading but no locatable 'ID' table header"
        raise LookupError(msg)
    return clusters


def _check_row_id(cluster: str, number: int, entry_id: str) -> list[str]:
    """Return problems if a register row's id is malformed or filed under the wrong cluster.

    Args:
        cluster: The cluster letter the row belongs to (the table it was found in), for the
            message and the cluster-match check.
        number: The row's 1-based line number.
        entry_id: The row's ``ID`` cell value.

    Returns:
        list[str]: Problems found; empty when the id is well formed and its letter matches the
            cluster it was found in.
    """
    if not _UW_ID_RE.match(entry_id):
        return [
            f"cluster {cluster} line {number}: id '{entry_id}' does not match UW-[A-M]NN"
        ]
    id_letter = entry_id[3]
    if id_letter != cluster:
        return [
            (
                f"cluster {cluster} line {number}: id '{entry_id}' belongs to cluster "
                f"'{id_letter}', not the cluster '{cluster}' table it was found in"
            )
        ]
    return []


def _check_row_status(
    cluster: str, number: int, entry_id: str, status: str
) -> list[str]:
    """Return a problem if a register row's ``Status`` is outside the closed vocabulary.

    Args:
        cluster: The cluster letter the row belongs to, for the message.
        number: The row's 1-based line number.
        entry_id: The row's ``ID`` cell value, for the message.
        status: The row's ``Status`` cell value.

    Returns:
        list[str]: One problem, or an empty list when the status is valid.
    """
    if status in _STATUSES:
        return []
    allowed = ", ".join(sorted(_STATUSES))
    return [
        f"{entry_id} (cluster {cluster} line {number}): status '{status}' is not one of: {allowed}"
    ]


def _check_row_phase(
    cluster: str,
    number: int,
    entry_id: str,
    phase: str,
    status: str,
    phase_vocabulary: frozenset[str],
) -> list[str]:
    """Return problems with a register row's ``Phase`` value.

    Checks, in order: empty on a row whose status still needs a phase home; more than one value;
    repeating a ``Status`` value; and membership in the closed phase vocabulary. A
    comma-separated or status-echoing value is reported once and not also checked against the
    vocabulary, since it fails on its own terms regardless of vocabulary membership.

    Args:
        cluster: The cluster letter the row belongs to, for the message.
        number: The row's 1-based line number.
        entry_id: The row's ``ID`` cell value, for the message.
        phase: The row's ``Phase`` cell value.
        status: The row's ``Status`` cell value, to check the phase does not repeat it and, when
            phase is empty, whether that emptiness is itself the problem.
        phase_vocabulary: Every phase token the run's manifest declares.

    Returns:
        list[str]: Problems found; empty when the phase is well formed.
    """
    if not phase:
        if status in _STATUSES_REQUIRING_PHASE:
            return [
                (
                    f"{entry_id} (cluster {cluster} line {number}): Phase is empty but Status is "
                    f"'{status}', which still needs the phase this row will land in"
                )
            ]
        return []

    if "," in phase:
        return [
            (
                f"{entry_id} (cluster {cluster} line {number}): Phase '{phase}' holds more than one "
                f"value; work spanning phases takes the earliest phase and says so in the Item text"
            )
        ]

    if phase in _STATUSES:
        return [
            (
                f"{entry_id} (cluster {cluster} line {number}): Phase '{phase}' repeats a Status "
                f"value instead of naming the phase this row will land in"
            )
        ]

    if not _phase_in_vocabulary(phase, phase_vocabulary):
        return [
            (
                f"{entry_id} (cluster {cluster} line {number}): Phase '{phase}' is not in the closed "
                f"phase vocabulary"
            )
        ]

    return []


def _extract_roadmap_product_phases(text: str) -> set[str]:
    """Return the product-phase tokens the roadmap's own headings declare.

    Most phases appear as ``## Phase <N>`` headings. Three do not: ``2b`` is a ``### Phase 2b``
    sub-heading, and ``4a``/``4b`` appear only inside ``### Deliverables (4a, ...)`` /
    ``(4b, ...)`` sub-headings nested under Phase 4's own heading. Phase 4's bare ``## Phase 4``
    heading is a container for 4a and 4b and is excluded: the closed vocabulary has no bare
    ``4``.

    Args:
        text: The full text of ``roadmap.md``.

    Returns:
        set[str]: The phase tokens the roadmap declares, for comparison against the hardcoded
            vocabulary.
    """
    tokens: set[str] = set()
    for line in text.splitlines():
        heading_match = _ROADMAP_PHASE_HEADING_RE.match(line)
        if heading_match:
            token = heading_match.group(1)
            if token != _ROADMAP_CONTAINER_PHASE:
                tokens.add(token)
            continue
        sub_heading_match = _ROADMAP_SUB_PHASE_HEADING_RE.match(line)
        if sub_heading_match:
            tokens.add(sub_heading_match.group(1))
            continue
        deliverables_match = _ROADMAP_DELIVERABLES_RE.search(line)
        if deliverables_match:
            tokens.add(deliverables_match.group(1))
    return tokens


def _extract_citations(text: str, id_re: re.Pattern[str]) -> set[str]:
    """Return every id cited in a block of prose, expanding "X through Y" ranges.

    Args:
        text: The prose to search (typically one cluster's ``Item`` column text, joined).
        id_re: A word-bounded pattern matching one id family (debt ids or ``AL-`` ids).

    Returns:
        set[str]: Every id cited directly, plus every id implied by a same-prefix "through" range
            such as "SL1 through SL10".

    Raises:
        ValueError: If a "through" range runs backwards (its second endpoint is lower than its
            first), or spans more than ``_THROUGH_RANGE_MAX_SPAN`` ids. Both are far more likely
            to be typos than real citation ranges, and expanding either would silently
            manufacture, or silently drop, ids nobody actually cited.
    """
    cited = set(id_re.findall(text))
    for match in _THROUGH_RANGE_RE.finditer(text):
        prefix, start_digits, end_digits = (
            match.group(1),
            match.group(2),
            match.group(3),
        )
        start, end = int(start_digits), int(end_digits)
        if end < start:
            msg = (
                f"'{match.group(0)}' runs backwards ({end} is lower than {start}); a range "
                f"whose endpoints are transposed expands to no ids at all, so every id it "
                f"meant to cite would be reported as an orphan"
            )
            raise ValueError(msg)
        if end - start > _THROUGH_RANGE_MAX_SPAN:
            msg = (
                f"'{match.group(0)}' spans {end - start + 1} ids, more than the "
                f"{_THROUGH_RANGE_MAX_SPAN}-id sanity bound; check for a typo in the range"
            )
            raise ValueError(msg)
        # Zero-padding is reproduced from the range's own first endpoint, so "AL-001 through
        # AL-005" expands to the "AL-001" form the log actually writes rather than to "AL-1".
        width = len(start_digits)
        cited.update(f"{prefix}{number:0{width}d}" for number in range(start, end + 1))
    return cited


def _debt_register_open_ids(lines: list[str]) -> dict[str, int]:
    """Return debt ids not marked ``[Closed]`` or ``[Resolved]``, mapped to their line number.

    Ids are matched against the whole first cell, so decorated variants such as ``U9a`` (a
    debt-register sub-item, not a distinct debt id in the pattern the linkage contract names) do
    not match and are correctly excluded rather than silently mis-tracked. The register uses
    ``[Closed]`` and ``[Resolved]`` interchangeably as closure markers (per the linkage contract's
    "How the other three registers link in" table); both are honoured here, because treating
    ``[Resolved]`` rows as open would report already-closed work as a gap. The marker is only
    checked in the ``Debt`` cell (index 1, present in both of the register's table shapes): every
    other column is free-text prose (``Source``, ``Severity``, ``Suggested action``) that can
    legitimately mention another row's closure without describing this row's own state, so
    joining every cell before matching would both mis-close open rows and mis-open closed ones.

    Args:
        lines: The debt register's lines.

    Returns:
        dict[str, int]: Open (neither ``[Closed]`` nor ``[Resolved]``) debt ids mapped to the line
            they were found on.
    """
    debt_cell_idx = 1
    open_ids: dict[str, int] = {}
    for number, line in enumerate(lines, start=1):
        if "|" not in line:
            continue
        cells = _split_row(line)
        if not cells or not _DEBT_ROW_ID_RE.match(cells[0]):
            continue
        debt_cell = cells[debt_cell_idx] if len(cells) > debt_cell_idx else ""
        if "[Closed]" in debt_cell or "[Resolved]" in debt_cell:
            continue
        open_ids[cells[0]] = number
    return open_ids


def _find_lessons_status_column(lines: list[str]) -> int:
    """Return the authoring lessons log table header's ``Status`` column index.

    Args:
        lines: The authoring lessons log's lines.

    Returns:
        int: The 0-based ``Status`` column index.

    Raises:
        LookupError: If no row starting with the cell ``ID`` and containing a ``Status``
            column is found.
    """
    for line in lines:
        if "|" not in line:
            continue
        cells = _split_row(line)
        if cells and cells[0] == "ID" and "Status" in cells:
            return cells.index("Status")
    msg = "no table header with 'ID' and 'Status' columns found"
    raise LookupError(msg)


def _is_open_lesson_row(cells: list[str], status_idx: int) -> bool:
    """Report whether a split row is a lesson row still needing cross-register citation.

    Args:
        cells: A row's split cell values.
        status_idx: The lessons log header's ``Status`` column index.

    Returns:
        bool: True when the row's id matches the lesson id shape, it has a ``Status`` cell, and
            that cell is not one of the closed statuses.
    """
    if not cells or _is_separator(cells) or not _AL_ROW_ID_RE.match(cells[0]):
        return False
    if len(cells) <= status_idx:
        return False
    return cells[status_idx] not in _AL_CLOSED_STATUSES


def _lessons_needing_citation(lines: list[str]) -> dict[str, int]:
    """Return lessons whose status is not applied/rejected/superseded, with line numbers.

    The log's own structure (header shape, id sequence, required fields) is validated
    separately by ``scripts/check_lessons_log.py``; this function still refuses to report zero
    open lessons when the document has table-like content but the header itself cannot be
    found, since that condition means the linkage check ran without reading anything rather
    than confirming there is nothing to link. A document with no pipe-containing line at all
    (freshly scaffolded, not yet holding a table) is not that failure mode: it genuinely has
    no lessons to cite yet, so it returns no rows rather than raising.

    Args:
        lines: The authoring lessons log's lines.

    Returns:
        dict[str, int]: Lesson ids still needing linkage, mapped to the line they were found on.

    Raises:
        LookupError: If the document has table-like content but no locatable header with
            ``ID`` and ``Status`` columns.
    """
    if not any("|" in line for line in lines):
        return {}
    status_idx = _find_lessons_status_column(lines)

    open_lessons: dict[str, int] = {}
    for number, line in enumerate(lines, start=1):
        if "|" not in line:
            continue
        cells = _split_row(line)
        if _is_open_lesson_row(cells, status_idx):
            open_lessons[cells[0]] = number
    return open_lessons


def _capability_header_docs_index(cells: list[str]) -> int | None:
    """Return a row's ``Docs`` column index if it is a capability table header, else None.

    Args:
        cells: A row's split cell values.

    Returns:
        int | None: The ``Docs`` column index when the row is a ``| ID | ... | Docs | ... |``
            header row; None otherwise.
    """
    if cells and cells[0] == "ID" and "Docs" in cells:
        return cells.index("Docs")
    return None


def _capability_register_status_rows(
    lines: list[str],
) -> list[tuple[int, str, str, str]]:
    """Return every capability row's line number, id, ``Docs`` cell, and ``Notes`` cell.

    The register holds four separate tables (K, G, A, S), each headed by its own
    ``| ID | Capability | Docs | Notes |`` row; this walks the whole file once and tracks
    whichever header was most recently seen, so a row only counts once a header naming a ``Docs``
    column has been observed. Each ``## `` section heading resets the tracked header, so a
    same-shaped table appearing later in the document (outside the four capability sections)
    cannot be mistaken for a capability row under a stale header.

    This is the single walk both ``_capability_register_open_ids`` (open-vs-done linkage) and
    ``_check_capability_status_vocabulary`` (glyph and Notes validity) build on, so the document
    is only parsed once and a malformed header is only ever reported once rather than by both
    checks independently.

    Args:
        lines: The capability register's lines.

    Returns:
        list[tuple[int, str, str, str]]: One (1-based line number, id, ``Docs`` cell, ``Notes``
            cell) tuple per capability row. The ``Notes`` cell is empty string when the table has
            no ``Notes`` column or the row has too few cells to reach it.

    Raises:
        LookupError: If any row shaped like a capability row (its first cell matches the
            ``[KGAS]NN`` id pattern) is found with no header located for its table, whether
            because the whole document has no locatable header or because one table's header
            specifically was renamed or dropped while the others stayed intact. Catching only
            the all-tables-missing case would leave a single corrupted header (e.g. just the K
            table's) silently invisible: that table's rows would fall under ``docs_idx=None``
            and every one of them would be dropped rather than flagged. A document with no
            pipe-containing line at all is not this failure mode and returns no rows instead.
        ValueError: If a capability row has too few cells to reach its table's ``Docs`` column.
            Skipping such a row was defensible while this walk only derived open ids, but
            ``_check_capability_status_vocabulary`` now rides on the same walk, so a truncated
            row would silently escape the glyph and Notes-non-empty checks rather than fail
            them: exactly the "check that can only pass" shape this script exists to avoid.
    """
    if not any("|" in line for line in lines):
        return []
    docs_idx: int | None = None
    notes_idx: int | None = None
    tables_found = 0
    rows: list[tuple[int, str, str, str]] = []
    unlocated: list[tuple[str, int]] = []
    truncated: list[tuple[str, int, int, int]] = []
    for number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            docs_idx = None
            notes_idx = None
            continue
        if "|" not in line:
            continue
        cells = _split_row(line)
        if not cells:
            continue
        header_docs_idx = _capability_header_docs_index(cells)
        if header_docs_idx is not None:
            docs_idx = header_docs_idx
            notes_idx = cells.index("Notes") if "Notes" in cells else None
            tables_found += 1
            continue
        if _is_separator(cells) or not _CAP_ROW_ID_RE.match(cells[0]):
            continue
        if docs_idx is None:
            unlocated.append((cells[0], number))
            continue
        if len(cells) <= docs_idx:
            truncated.append((cells[0], number, len(cells), docs_idx + 1))
            continue
        notes_val = (
            cells[notes_idx] if notes_idx is not None and len(cells) > notes_idx else ""
        )
        rows.append((number, cells[0], cells[docs_idx], notes_val))
    if tables_found == 0:
        msg = "no table header with 'ID' and 'Docs' columns found"
        raise LookupError(msg)
    if unlocated:
        ids_listed = ", ".join(
            f"{cap_id} (line {number})" for cap_id, number in unlocated
        )
        msg = (
            f"found capability row(s) with no locatable 'ID'/'Docs' header for their table: "
            f"{ids_listed}"
        )
        raise LookupError(msg)
    if truncated:
        rows_listed = ", ".join(
            f"{cap_id} (line {number}: {found} cell(s), fewer than the {needed} needed "
            f"to reach its table's 'Docs' column)"
            for cap_id, number, found, needed in truncated
        )
        msg = (
            f"found capability row(s) too short to reach their table's 'Docs' column, so "
            f"their status glyph cannot be read or validated: {rows_listed}"
        )
        raise ValueError(msg)
    return rows


def _capability_register_open_ids(lines: list[str]) -> dict[str, int]:
    """Return capability ids not marked done, mapped to their 1-based line number.

    The ``Docs`` cell holds exactly one status glyph (verified against the current document: no
    row mixes a glyph with other text), so an equality check against the done mark is reliable
    rather than a loose substring test.

    This is the one definition of "open capability" in the module: ``_check_capability_linkage``
    calls it rather than re-deriving the same ``docs_val != _CAP_DONE_MARK`` rule inline, so the
    rule cannot be changed in one place and left stale in the other. It costs a second linear
    walk of a document ``check_linkage`` has already walked; that is cheap next to two copies of
    the rule, and the duplicate walk can never double-report a malformed header because
    ``check_linkage`` only reaches ``_check_capability_linkage`` once the first walk has
    succeeded.

    Args:
        lines: The capability register's lines.

    Returns:
        dict[str, int]: Open (not done) capability ids mapped to the line they were found on.

    Raises:
        LookupError: See ``_capability_register_status_rows``, which this delegates the walk to.
        ValueError: See ``_capability_register_status_rows``.
    """
    return {
        entry_id: number
        for number, entry_id, docs_val, _notes_val in _capability_register_status_rows(
            lines
        )
        if docs_val != _CAP_DONE_MARK
    }


def _check_capability_status_vocabulary(
    capability_rows: list[tuple[int, str, str, str]],
    capability_register_path: Path,
) -> tuple[list[str], dict[str, int]]:
    """Check every capability row's ``Docs`` glyph, and ``Notes`` when the row is not done.

    Two rules: the ``Docs`` cell must be exactly one of the three recognised status glyphs
    (checkmark, yellow circle, cross), and a row marked partial or missing must carry a
    non-empty ``Notes`` cell naming what is missing, since "not delivered" with no explanation
    is not useful scope tracking.

    Args:
        capability_rows: The capability register's rows, as returned by
            ``_capability_register_status_rows``.
        capability_register_path: The capability register's path, for message text.

    Returns:
        tuple[list[str], dict[str, int]]: Problems found, and each recognised glyph mapped to
            its row count (for the CLI's success-summary line); a row with an unrecognised glyph
            is not counted under any key.
    """
    problems: list[str] = []
    counts: dict[str, int] = {}
    for number, entry_id, docs_val, notes_val in capability_rows:
        if docs_val not in _CAP_STATUS_GLYPHS:
            problems.append(
                f"{capability_register_path.name}:{number}: capability '{entry_id}' Docs "
                f"cell is '{docs_val}', not one of the three status glyphs (checkmark, "
                f"yellow circle, or cross)"
            )
            continue
        counts[docs_val] = counts.get(docs_val, 0) + 1
        if docs_val in _CAP_OPEN_GLYPHS and not notes_val.strip():
            problems.append(
                f"{capability_register_path.name}:{number}: capability '{entry_id}' is "
                f"'{docs_val}' but its Notes cell is empty; a capability that is not "
                f"delivered must name what is missing"
            )
    return problems, counts


def _extract_roadmap_mapping_section(lines: list[str]) -> str:
    """Return the text of roadmap.md's "Where every open register item lands" section.

    This is the section the linkage contract names as the exit point for capability-register
    ids: a row not marked done must appear here rather than anywhere else in the document, so the
    search is deliberately scoped to this section and not the whole file.

    Args:
        lines: ``roadmap.md``'s lines.

    Returns:
        str: The section's text, from its heading up to (not including) the next ``## `` heading;
            empty string if the heading itself is not found.
    """
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == _ROADMAP_MAPPING_HEADING
        ),
        None,
    )
    if start is None:
        return ""
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("## ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _check_register_rows(
    clusters: dict[str, tuple[list[str], list[tuple[int, list[str]]]]],
    phase_vocabulary: frozenset[str],
) -> tuple[list[str], dict[str, str]]:
    """Run every row-level check across all cluster tables, plus the register-wide id check.

    Args:
        clusters: Cluster letter mapped to its header cells and data rows, as returned by
            ``_find_clusters``.
        phase_vocabulary: Every phase token the run's manifest declares, threaded down to
            ``_check_row_phase``.

    Returns:
        tuple[list[str], dict[str, str]]: The problems found, and each cluster letter mapped to
            its joined ``Item`` column text, for the cross-register citation checks that follow.
    """
    problems: list[str] = []
    all_ids: dict[str, list[int]] = {}
    cluster_item_text: dict[str, str] = {}

    for letter, (header_cells, rows) in sorted(clusters.items()):
        row_problems, item_texts, row_ids = _check_cluster_rows(
            letter, header_cells, rows, phase_vocabulary
        )
        problems.extend(row_problems)
        cluster_item_text[letter] = "\n".join(item_texts)
        for entry_id, number in row_ids:
            all_ids.setdefault(entry_id, []).append(number)

    for entry_id, line_numbers in sorted(all_ids.items()):
        if len(line_numbers) > 1:
            lines_listed = ", ".join(str(number) for number in line_numbers)
            problems.append(
                f"id '{entry_id}' is used on {len(line_numbers)} rows (lines {lines_listed}); "
                f"ids must be unique across the whole register"
            )

    return problems, cluster_item_text


def _resolve_column_indexes(header_cells: list[str]) -> dict[str, int | None]:
    """Resolve the ``ID``/``Status``/``Phase``/``Item`` column indexes from a header row.

    Args:
        header_cells: A cluster table's header cells.

    Returns:
        dict[str, int | None]: Each of the four column names mapped to its 0-based index, or
            None when that cluster's table has no such column (clusters L and M have no
            ``Phase``).
    """
    return {
        name: header_cells.index(name) if name in header_cells else None
        for name in ("ID", "Status", "Phase", "Item")
    }


def _check_one_row(
    letter: str,
    number: int,
    cells: list[str],
    indexes: dict[str, int | None],
    phase_vocabulary: frozenset[str],
) -> tuple[list[str], str | None, str]:
    """Run the id, status, and phase checks on one already length-checked cluster row.

    Args:
        letter: The cluster letter, for message text.
        number: The row's 1-based line number.
        cells: The row's cell values, already confirmed to match the header's column count.
        indexes: The header's resolved column indexes, as returned by
            ``_resolve_column_indexes``.
        phase_vocabulary: Every phase token the run's manifest declares.

    Returns:
        tuple[list[str], str | None, str]: The problems found, the row's ``Item`` text (None if
            the cluster has no ``Item`` column), and the row's id (empty string if the cluster
            has no ``ID`` column).
    """
    id_idx, status_idx, phase_idx, item_idx = (
        indexes["ID"],
        indexes["Status"],
        indexes["Phase"],
        indexes["Item"],
    )
    problems: list[str] = []

    entry_id = cells[id_idx] if id_idx is not None else ""
    problems.extend(_check_row_id(letter, number, entry_id))

    status = cells[status_idx] if status_idx is not None else ""
    if status_idx is not None:
        problems.extend(_check_row_status(letter, number, entry_id, status))

    if phase_idx is not None:
        problems.extend(
            _check_row_phase(
                letter, number, entry_id, cells[phase_idx], status, phase_vocabulary
            )
        )

    item_text = cells[item_idx] if item_idx is not None else None

    return problems, item_text, entry_id


def _check_cluster_rows(
    letter: str,
    header_cells: list[str],
    rows: list[tuple[int, list[str]]],
    phase_vocabulary: frozenset[str],
) -> tuple[list[str], list[str], list[tuple[str, int]]]:
    """Run the id, status, and phase checks on one cluster table's data rows.

    A row whose column count disagrees with its header is reported and then skipped for the
    per-cell checks, but its id is still collected first: the register-wide uniqueness check runs
    on the collected ids, so skipping the row before collecting let a duplicate id hide behind a
    malformed row, escaping the uniqueness check entirely rather than being reported twice.

    Args:
        letter: The cluster letter, for message text and the returned id list.
        header_cells: The cluster table's header cells, used to resolve column indexes.
        rows: The cluster's (1-based line number, cells) data rows.
        phase_vocabulary: Every phase token the run's manifest declares.

    Returns:
        tuple[list[str], list[str], list[tuple[str, int]]]: The problems found, the ``Item``
            column text of every row (for later citation checks), and each row's (id, line
            number) pair (for the register-wide id-uniqueness check).
    """
    indexes = _resolve_column_indexes(header_cells)
    id_idx = indexes["ID"]

    problems: list[str] = []
    item_texts: list[str] = []
    row_ids: list[tuple[str, int]] = []

    for number, cells in rows:
        if len(cells) != len(header_cells):
            problems.append(
                f"cluster {letter} line {number}: expected {len(header_cells)} columns, "
                f"found {len(cells)}"
            )
            if id_idx is not None and id_idx < len(cells):
                row_ids.append((cells[id_idx], number))
            continue

        row_problems, item_text, entry_id = _check_one_row(
            letter, number, cells, indexes, phase_vocabulary
        )
        problems.extend(row_problems)
        row_ids.append((entry_id, number))
        if item_text is not None:
            item_texts.append(item_text)

    return problems, item_texts, row_ids


def _check_roadmap_vocabulary(
    roadmap_lines: list[str],
    roadmap_path: Path,
    manifest_track1_phases: frozenset[str],
) -> list[str]:
    """Check the roadmap's phase headings agree with the manifest's track-1 phase vocabulary.

    Track-2 phases (6, 7, 8, 9) are declared in the manifest but never appear as their own
    ``roadmap.md`` headings, so the comparison is scoped to track-1 phases only; comparing
    against the full manifest vocabulary would report every track-2 phase as a permanent,
    spurious "missing heading".

    Args:
        roadmap_lines: ``roadmap.md``'s lines.
        roadmap_path: ``roadmap.md``'s path, for message text.
        manifest_track1_phases: The track-1 phase tokens declared in
            ``plan-manifest.toml``'s ``[phases]`` table.

    Returns:
        list[str]: One problem if the derived and manifest vocabularies disagree; empty
            otherwise.
    """
    derived = frozenset(_extract_roadmap_product_phases("\n".join(roadmap_lines)))
    if derived == manifest_track1_phases:
        return []
    missing = ", ".join(sorted(manifest_track1_phases - derived)) or "(none)"
    extra = ", ".join(sorted(derived - manifest_track1_phases)) or "(none)"
    return [
        (
            f"product-phase vocabulary drift: {roadmap_path.name} is missing headings for "
            f"{missing} and declares unrecognised phase(s) {extra}; update "
            f"plan-manifest.toml's [phases] table and this check together with the roadmap "
            f"change"
        )
    ]


# The roadmap phase-status table's header, identified by its cells rather than a line number:
# the first cell must be "Phase" and a "Status" column must sit alongside it.
_ROADMAP_PHASE_STATUS_HEADER_CELLS = ("Phase", "Status")
# "5 Hardening" -> "5"; "4c Family Loops (NEW 2026-07-16)" -> "4c". The phase token is always
# the first whitespace-separated word of the roadmap phase-status table's first column.
_ROADMAP_PHASE_STATUS_TOKEN_RE = re.compile(r"^(\S+)")
# A leading status glyph (for example the checkmark or the yellow-circle emoji) plus any
# whitespace before the prose proper begins.
_ROADMAP_STATUS_LEADING_GLYPH_RE = re.compile(r"^[^A-Za-z]+")
# The glyph a roadmap status cell must lead with, keyed by the phase's `shipped` axis: a phase
# that shipped is a checkmark, one partly shipped is the yellow circle, one not shipped at all is
# the cross. Same three glyphs the capability register uses, so the two documents cannot drift
# into separate conventions.
_ROADMAP_STATUS_GLYPH_BY_SHIPPED = {
    "yes": _CAP_DONE_MARK,
    "partial": _CAP_PARTIAL_MARK,
    "no": _CAP_MISSING_MARK,
}


def _strip_trailing_parentheticals(text: str) -> str:
    """Remove every trailing parenthetical qualifier from a status cell, innermost nesting first.

    "``Delivered (backend) (2026-07-20 audit)``" becomes "``Delivered``". A single-pass regex
    strips only the last qualifier, leaving "delivered (backend)" to be compared against the
    manifest term and reported as a spurious mismatch; a regex that cannot count parentheses also
    mis-handles "(a (b))". This scans backwards with a depth counter instead, so both shapes
    normalize correctly.

    Args:
        text: The status cell text, with any leading glyph already removed.

    Returns:
        str: The text with every balanced trailing ``(...)`` group, and the whitespace before
            it, removed. An unbalanced trailing ``)`` is left in place rather than guessed at.
    """
    stripped = text.rstrip()
    while stripped.endswith(")"):
        depth = 0
        opened_at: int | None = None
        for index in range(len(stripped) - 1, -1, -1):
            char = stripped[index]
            if char == ")":
                depth += 1
            elif char == "(":
                depth -= 1
                if depth == 0:
                    opened_at = index
                    break
        if opened_at is None:
            break
        stripped = stripped[:opened_at].rstrip()
    return stripped


def _normalize_roadmap_status_prose(status_cell: str) -> str:
    """Strip a roadmap phase-status cell down to its bare, lower-cased status term.

    "``✅ Substantially delivered (2026-07-20 audit)``" becomes "``substantially delivered``":
    the leading glyph and the trailing qualifiers are noise around the one term this check
    actually compares against the manifest's ``[status_vocabulary]``. The glyph itself is not
    noise, but it is validated separately (``_check_roadmap_status_glyph``) rather than folded
    into the term comparison.

    Args:
        status_cell: The roadmap phase-status table's ``Status`` column value for one row.

    Returns:
        str: The lower-cased status term, with the leading glyph and every trailing
            parenthetical qualifier removed.
    """
    without_glyph = _ROADMAP_STATUS_LEADING_GLYPH_RE.sub("", status_cell)
    return _strip_trailing_parentheticals(without_glyph).strip().lower()


def _find_roadmap_phase_status_header(
    lines: list[str],
) -> tuple[int, int, int] | None:
    """Locate the roadmap's phase-status table header by its cells, not a fixed line number.

    Args:
        lines: ``roadmap.md``'s lines.

    Returns:
        tuple[int, int, int] | None: The header's 0-based line index, ``Phase`` column index,
            and ``Status`` column index; None if no row's first cell is ``Phase`` with a
            ``Status`` column alongside it.
    """
    phase_cell, status_cell = _ROADMAP_PHASE_STATUS_HEADER_CELLS
    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = _split_row(line)
        if cells and cells[0] == phase_cell and status_cell in cells:
            return index, 0, cells.index(status_cell)
    return None


def _roadmap_phase_status_rows(lines: list[str]) -> list[tuple[int, str, str]]:
    """Return each row of the roadmap's phase-status table as (line, phase token, status prose).

    A roadmap with no table-like content at all (the minimal fixtures this suite builds from
    headings alone) genuinely has nothing for this check to compare and returns no rows. A
    roadmap that does carry tables but no locatable phase-status header is the opposite case and
    raises: renaming the header's first cell used to drop the checked rows from ten to zero and
    report nothing at all, which is the "check that can only pass" failure this module treats as
    worse than no check. This is the same discrimination ``_lessons_needing_citation`` and
    ``_capability_register_status_rows`` already make between an empty document and a corrupted
    one.

    Args:
        lines: ``roadmap.md``'s lines.

    Returns:
        list[tuple[int, str, str]]: One (1-based line number, phase token, raw ``Status`` cell
            text) tuple per data row; empty when the document holds no table at all.

    Raises:
        LookupError: If the document has table-like content but no row whose first cell is
            ``Phase`` with a ``Status`` column alongside it.
    """
    located = _find_roadmap_phase_status_header(lines)
    if located is None:
        if not any("|" in line for line in lines):
            return []
        phase_cell, status_cell = _ROADMAP_PHASE_STATUS_HEADER_CELLS
        msg = (
            f"has table content but no phase-status table header (a row whose first cell is "
            f"'{phase_cell}' with a '{status_cell}' column alongside it); the roadmap status "
            f"cross-check cannot run and would otherwise report a clean result"
        )
        raise LookupError(msg)
    header_index, phase_col, status_col = located

    rows: list[tuple[int, str, str]] = []
    for offset, line in enumerate(lines[header_index + 1 :], start=header_index + 2):
        if "|" not in line:
            break
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        if len(cells) <= max(phase_col, status_col):
            continue
        token_match = _ROADMAP_PHASE_STATUS_TOKEN_RE.match(cells[phase_col])
        if token_match is None:
            continue
        rows.append((offset, token_match.group(1), cells[status_col]))
    return rows


def _check_roadmap_phase_status(
    roadmap_lines: list[str],
    roadmap_path: Path,
    manifest: dict[str, Any],
) -> list[str]:
    """Check the roadmap's phase-status table prose against the manifest's status vocabulary.

    For each row, the phase's ``(shipped, usable)`` pair is looked up in the manifest and mapped
    to its prose term via ``[status_vocabulary]``; that term is compared, case-insensitively,
    against the roadmap cell with its leading glyph and trailing parenthetical qualifiers
    stripped, and the stripped glyph is itself checked against the phase's ``shipped`` axis. A
    phase token the manifest does not recognise, or a ``(shipped, usable)`` pair with no
    ``[status_vocabulary]`` entry, is not reported here: those are the vocabulary-drift and
    manifest-integrity checks' findings respectively, and reporting them a second time here
    would just be duplicate noise about the same root cause.

    Args:
        roadmap_lines: ``roadmap.md``'s lines.
        roadmap_path: ``roadmap.md``'s path, for message text.
        manifest: The parsed plan-manifest.toml document.

    Returns:
        list[str]: One problem per row whose status glyph or prose disagrees with the
            manifest-derived value; empty when every row matches (including when the document
            holds no table at all).

    Raises:
        LookupError: See ``_roadmap_phase_status_rows``, which locates the table.
    """
    phases = manifest.get("phases", {})
    if not isinstance(phases, dict):
        return []
    vocabulary = manifest.get("status_vocabulary", {})

    problems: list[str] = []
    for line_number, phase_token, status_cell in _roadmap_phase_status_rows(
        roadmap_lines
    ):
        entry = phases.get(phase_token)
        if not isinstance(entry, dict):
            continue
        problems.extend(
            _check_roadmap_status_glyph(
                line_number, phase_token, status_cell, entry, roadmap_path
            )
        )
        key = f"{entry.get('shipped')}/{entry.get('usable')}"
        expected_term = vocabulary.get(key)
        if not isinstance(expected_term, str):
            continue
        actual_term = _normalize_roadmap_status_prose(status_cell)
        if actual_term != expected_term.strip().lower():
            problems.append(
                f"{roadmap_path.name}:{line_number}: phase '{phase_token}' status column "
                f"reads '{status_cell}' (normalized to '{actual_term}'), but "
                f"plan-manifest.toml's [status_vocabulary] derives '{expected_term}' from "
                f"(shipped={entry.get('shipped')!r}, usable={entry.get('usable')!r})"
            )
    return problems


def _check_roadmap_status_glyph(
    line_number: int,
    phase_token: str,
    status_cell: str,
    entry: dict[str, Any],
    roadmap_path: Path,
) -> list[str]:
    """Check a roadmap status cell's leading glyph agrees with the phase's ``shipped`` axis.

    ``_normalize_roadmap_status_prose`` throws the glyph away before comparing the prose term, so
    without this check a cell reading "cross Delivered" matched a ``yes/yes`` phase perfectly: the
    most visible half of the cell, the one a reader scans first, was the only unvalidated half.
    ``_check_capability_status_vocabulary`` already validates the same three glyphs on the
    capability register; this is the roadmap's equivalent.

    Args:
        line_number: The row's 1-based line number, for message text.
        phase_token: The row's phase token, for message text.
        status_cell: The raw ``Status`` cell text.
        entry: The manifest's ``[phases.<token>]`` table for this phase.
        roadmap_path: ``roadmap.md``'s path, for message text.

    Returns:
        list[str]: One problem when the cell's leading glyph is missing or is not the one the
            phase's ``shipped`` value implies; empty when it matches, or when the phase's
            ``shipped`` value is outside the closed vocabulary (the manifest-integrity check's
            finding, not this one's).
    """
    expected_glyph = _ROADMAP_STATUS_GLYPH_BY_SHIPPED.get(str(entry.get("shipped")))
    if expected_glyph is None:
        return []
    leading = _ROADMAP_STATUS_LEADING_GLYPH_RE.match(status_cell)
    actual_glyph = leading.group(0).strip() if leading else ""
    if actual_glyph == expected_glyph:
        return []
    reads = (
        f"leads with '{actual_glyph}'" if actual_glyph else "carries no status glyph"
    )
    return [
        (
            f"{roadmap_path.name}:{line_number}: phase '{phase_token}' status column "
            f"{reads}, but plan-manifest.toml records shipped="
            f"{entry.get('shipped')!r}, whose glyph is '{expected_glyph}'"
        )
    ]


# "### Phase 6: Public Authentication and Multi-Tenancy (3-4 weeks)" -> "6". PROJECT-PLAN.md
# narrates each track-2 phase under a heading of this shape; the token is the word after "Phase".
_PROJECT_PLAN_PHASE_HEADING_RE = re.compile(r"^#{2,4}\s+Phase\s+(\S+?):")
# The bolded status line that opens each of those sections.
_PROJECT_PLAN_STATUS_RE = re.compile(r"^\*\*Status\*\*:\s*(.+)$")
# Where the status term ends and the narrative qualifying it begins. Unlike a roadmap table cell,
# a PROJECT-PLAN.md status line runs on into wrapped prose ("Partially delivered, ahead of
# schedule, corrected 2026-07-20 (this section had said ..."), so the term is the first clause
# rather than the whole cell with trailing parentheticals stripped.
_PROJECT_PLAN_STATUS_TERM_END_RE = re.compile(r"[,.;(]")


def _project_plan_phase_status_lines(lines: list[str]) -> dict[str, tuple[int, str]]:
    """Map each ``## Phase <token>:`` section in PROJECT-PLAN.md to its ``**Status**:`` line.

    Args:
        lines: ``PROJECT-PLAN.md``'s lines.

    Returns:
        dict[str, tuple[int, str]]: Phase token to its status line's 1-based line number and raw
            status text. A section with no ``**Status**:`` line before the next phase heading is
            absent from the mapping, which the caller reports as a missing status rather than
            silently treating as a match.
    """
    found: dict[str, tuple[int, str]] = {}
    current: str | None = None
    for index, line in enumerate(lines):
        heading = _PROJECT_PLAN_PHASE_HEADING_RE.match(line)
        if heading:
            current = heading.group(1)
            continue
        if current is None or current in found:
            continue
        status = _PROJECT_PLAN_STATUS_RE.match(line)
        if status:
            found[current] = (index + 1, status.group(1).strip())
    return found


def _normalize_project_plan_status_prose(status_text: str) -> str:
    """Strip a PROJECT-PLAN.md status line down to its bare, lower-cased status term.

    Args:
        status_text: Everything after ``**Status**:`` on one phase section's status line.

    Returns:
        str: The lower-cased status term: the leading glyph removed and everything from the
            first comma, period, semicolon, or opening parenthesis onward discarded.
    """
    without_glyph = _ROADMAP_STATUS_LEADING_GLYPH_RE.sub("", status_text)
    return (
        _PROJECT_PLAN_STATUS_TERM_END_RE.split(without_glyph, maxsplit=1)[0]
        .strip()
        .lower()
    )


def _check_project_plan_phase_status(
    plan_lines: list[str],
    plan_path: Path,
    manifest: dict[str, Any],
) -> list[str]:
    """Check PROJECT-PLAN.md's track-2 phase sections agree with the manifest's status model.

    ``_check_roadmap_phase_status`` iterates roadmap rows, not manifest phases, so a manifest
    phase with no roadmap row is never compared to anything. Track-2 phases (6-9) are exactly
    that case by design: ``roadmap.md`` states outright that they "are not detailed here", and
    ``_check_roadmap_vocabulary`` excludes them for the same reason. The effect was that four
    phases' ``shipped``/``usable`` values were asserted in the manifest and validated against no
    document at all, which is the same vacuous pass this whole gate exists to prevent. This is
    the track-2 half of the drift check, reading the narrative document that does cover them.

    Only the status *term* is compared. PROJECT-PLAN.md writes an unstarted phase as the pause
    glyph where the capability register writes a cross, so importing ``_check_roadmap_status_glyph``
    here would force a cosmetic rewrite of the document to satisfy a vocabulary built for a
    different one, with no accuracy gained.

    Args:
        plan_lines: ``PROJECT-PLAN.md``'s lines.
        plan_path: ``PROJECT-PLAN.md``'s path, for message text.
        manifest: The parsed plan-manifest.toml document.

    Returns:
        list[str]: One problem per track-2 phase with no section, no status line, or a status
            term the manifest does not derive; empty when every track-2 phase matches.
    """
    phases = manifest.get("phases", {})
    if not isinstance(phases, dict):
        return []
    vocabulary = manifest.get("status_vocabulary", {})
    sections = _project_plan_phase_status_lines(plan_lines)

    problems: list[str] = []
    for token in sorted(_manifest_phases_for_track(manifest, 2)):
        entry = phases[token]
        found = sections.get(token)
        if found is None:
            problems.append(
                f"{plan_path.name}: track-2 phase '{token}' has no '## Phase {token}:' section "
                f"with a '**Status**:' line; roadmap.md does not cover track-2 phases, so "
                f"without one this phase's manifest status is checked against nothing"
            )
            continue
        line_number, status_text = found
        key = f"{entry.get('shipped')}/{entry.get('usable')}"
        expected_term = vocabulary.get(key)
        if not isinstance(expected_term, str):
            continue
        actual_term = _normalize_project_plan_status_prose(status_text)
        if actual_term != expected_term.strip().lower():
            problems.append(
                f"{plan_path.name}:{line_number}: phase '{token}' status line reads "
                f"'{status_text}' (normalized to '{actual_term}'), but plan-manifest.toml's "
                f"[status_vocabulary] derives '{expected_term}' from "
                f"(shipped={entry.get('shipped')!r}, usable={entry.get('usable')!r})"
            )
    return problems


def _check_manifest_structure(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check the manifest declares the tables and rungs every other integrity check reads.

    Every check that follows starts from ``manifest.get("phases", {})`` or
    ``manifest.get("rungs", {})`` and iterates. On a manifest missing either table, all of them
    iterate nothing and report a clean result, including the ``#CRITICAL`` Phase 7 assertion:
    deleting ``[rungs]`` made the whole integrity suite pass vacuously. This runs first and
    short-circuits the rest, so a structurally absent manifest is reported as the structural
    problem it is rather than silently certified consistent.

    It also fixes the shape assumptions those checks make. ``phases = "x"`` is valid TOML and
    would reach ``phases.items()`` as an ``AttributeError`` traceback; requiring a table here
    turns that into a reported problem before any check reads it.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem per missing, mistyped, or empty required table, plus one per
            missing required rung; empty when the manifest's structural spine is intact.
    """
    # #CRITICAL: data integrity: without this precondition, a manifest with no [rungs] table
    # makes six integrity checks (including the Phase 7 / R2 assertion this file calls the single
    # most load-bearing dependency fact in the plan) return zero problems, which the CLI reports
    # as a passing run.
    # #VERIFY: _check_manifest_integrity returns these problems and does NOT run the six when
    # this list is non-empty, so a structurally broken manifest can never report clean.
    problems: list[str] = []
    for table in _MANIFEST_REQUIRED_TABLES:
        value = manifest.get(table)
        if value is None:
            problems.append(
                f"{manifest_path.name}: required table [{table}] is missing; every "
                f"manifest-integrity check reads it, so its absence would otherwise make all "
                f"of them pass without checking anything"
            )
        elif not isinstance(value, dict):
            problems.append(
                f"{manifest_path.name}: [{table}] is {type(value).__name__}, not a table"
            )
        elif not value:
            problems.append(
                f"{manifest_path.name}: [{table}] is empty; a manifest declaring no "
                f"{table} cannot be validated against the plan"
            )
    rungs = manifest.get("rungs")
    if isinstance(rungs, dict) and rungs:
        problems.extend(
            (
                f"{manifest_path.name}: required rung [rungs.{name}] is missing; the release "
                f"ladder checks name it directly and silently skip it when it is absent"
            )
            for name in _MANIFEST_REQUIRED_RUNGS
            if name not in rungs
        )
    return problems


def _check_manifest_rung_phase_references(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check every phase token a rung requires or excludes is declared in ``[phases]``.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem per rung phase-list entry with no matching ``[phases]`` table.
    """
    phases = manifest.get("phases", {})
    rungs = manifest.get("rungs", {})
    problems: list[str] = []
    for rung_name, rung in sorted(rungs.items()):
        if not isinstance(rung, dict):
            continue
        for field in ("requires_phases", "excludes_phases"):
            problems.extend(
                (
                    f"{manifest_path.name}: rungs.{rung_name}.{field} references phase "
                    f"'{token}', which has no [phases.\"{token}\"] entry"
                )
                for token in rung.get(field, [])
                if token not in phases
            )
    return problems


def _check_manifest_rung_requires_excludes_disjoint(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check a rung never lists the same phase in both ``requires_phases`` and ``excludes_phases``.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem per rung whose two phase lists overlap.
    """
    rungs = manifest.get("rungs", {})
    problems: list[str] = []
    for rung_name, rung in sorted(rungs.items()):
        if not isinstance(rung, dict):
            continue
        requires = set(rung.get("requires_phases", []))
        excludes = set(rung.get("excludes_phases", []))
        overlap = requires & excludes
        if overlap:
            listed = ", ".join(sorted(overlap))
            problems.append(
                f"{manifest_path.name}: rungs.{rung_name} lists {listed} in both "
                f"requires_phases and excludes_phases; a rung cannot both require and "
                f"exclude the same phase"
            )
    return problems


def _check_manifest_rung_monotonicity(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check each rung's required phases are a superset of the rung below it.

    The release ladder is an overlay on the phase plan: R2 must require everything R1 requires,
    and R3 must require everything R2 requires. A rung that drops a phase the lower rung needed
    would silently un-gate a release that should still be blocked on it.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem per broken (lower, higher) rung pair.
    """
    rungs = manifest.get("rungs", {})
    problems: list[str] = []
    for lower_name, higher_name in (("R1", "R2"), ("R2", "R3")):
        lower = rungs.get(lower_name, {})
        higher = rungs.get(higher_name, {})
        if not isinstance(lower, dict) or not isinstance(higher, dict):
            continue
        lower_requires = set(lower.get("requires_phases", []))
        higher_requires = set(higher.get("requires_phases", []))
        dropped = lower_requires - higher_requires
        if dropped:
            listed = ", ".join(sorted(dropped))
            problems.append(
                f"{manifest_path.name}: rungs.{higher_name}.requires_phases drops "
                f"{listed} from rungs.{lower_name}.requires_phases; the release ladder "
                f"must be monotonic, each rung requiring everything the rung below it "
                f"requires"
            )
    return problems


def _check_manifest_status_vocabulary_coverage(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check every phase's ``(shipped, usable)`` pair has a matching ``[status_vocabulary]`` key.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem per phase whose status pair has no matching vocabulary entry.
    """
    phases = manifest.get("phases", {})
    vocabulary = manifest.get("status_vocabulary", {})
    problems: list[str] = []
    for token, entry in sorted(phases.items()):
        if not isinstance(entry, dict):
            continue
        key = f"{entry.get('shipped')}/{entry.get('usable')}"
        if key not in vocabulary:
            problems.append(
                f'{manifest_path.name}: phases."{token}" has '
                f"(shipped={entry.get('shipped')!r}, usable={entry.get('usable')!r}), "
                f"but [status_vocabulary] has no '{key}' entry to derive its roadmap "
                f"prose term from"
            )
    return problems


def _check_manifest_status_values(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check every phase's ``shipped``/``usable`` value is one of yes, partial, or no.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem per phase with an out-of-vocabulary ``shipped`` or ``usable``
            value.
    """
    phases = manifest.get("phases", {})
    problems: list[str] = []
    for token, entry in sorted(phases.items()):
        if not isinstance(entry, dict):
            continue
        for field in ("shipped", "usable"):
            value = entry.get(field)
            if value not in _MANIFEST_STATUS_VALUES:
                problems.append(
                    f'{manifest_path.name}: phases."{token}".{field} is {value!r}, not '
                    f"one of 'yes', 'partial', or 'no'"
                )
    return problems


def _check_manifest_phase_7_excluded_from_r2(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check Phase 7 never appears in R2's ``requires_phases``.

    This is the single most load-bearing dependency fact in the plan: Phase 7 (Kids compliance
    and account lifecycle) gates R3 (the public App Store launch) but must NOT gate R2 (the
    TestFlight limited release), which is exactly what lets TestFlight ship before the
    compliance checklist is signed off. That fact is deliberately asserted here rather than left
    for the monotonicity check to imply, because monotonicity alone would stay green even if
    Phase 7 were added to both R2 and R3 at once; only an explicit check catches Phase 7 leaking
    into R2 specifically.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem if Phase 7 is in R2's requires_phases; empty otherwise.
    """
    # #CRITICAL: data integrity: Phase 7 gating R2 would reorder the critical path (compliance
    # work would block TestFlight, not just the App Store submission) without any other check
    # in this script failing.
    # #VERIFY: covered by test_check_manifest_phase_7_excluded_from_r2_flags_phase_7_in_r2, which
    # asserts this specific regression rather than relying on the monotonicity check to catch it.
    r2 = manifest.get("rungs", {}).get("R2", {})
    if not isinstance(r2, dict):
        return []
    if "7" in set(r2.get("requires_phases", [])):
        return [
            (
                f"{manifest_path.name}: rungs.R2.requires_phases includes phase '7', which "
                f"breaks the load-bearing dependency fact that Phase 7 (Kids compliance and "
                f"account lifecycle) gates R3 (public App Store launch) only, not R2 "
                f"(TestFlight limited release); TestFlight can currently ship before the "
                f"compliance checklist finishes, and this change would silently block that"
            )
        ]
    return []


def _check_manifest_integrity(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Validate the plan manifest's internal consistency.

    Runs a structural precondition first (``_check_manifest_structure``: the required tables and
    rungs are present, are tables, and are non-empty), and only then every self-consistency check
    the manifest can be validated against without reference to any other document: rung phase
    references resolve, requires/excludes never overlap, the release ladder is monotonic, every
    phase's status pair has a vocabulary term, every status value is in the closed vocabulary,
    and Phase 7 does not gate R2.

    The precondition short-circuits deliberately. Each of the six consistency checks iterates a
    table it fetches with a ``{}`` default, so on a manifest missing that table it reports
    nothing; running them anyway would bury the one real finding under six false all-clears.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: Problems found; empty when the manifest is structurally present and
            internally consistent.
    """
    structural_problems = _check_manifest_structure(manifest, manifest_path)
    if structural_problems:
        return structural_problems

    problems: list[str] = []
    problems.extend(_check_manifest_rung_phase_references(manifest, manifest_path))
    problems.extend(
        _check_manifest_rung_requires_excludes_disjoint(manifest, manifest_path)
    )
    problems.extend(_check_manifest_rung_monotonicity(manifest, manifest_path))
    problems.extend(_check_manifest_status_vocabulary_coverage(manifest, manifest_path))
    problems.extend(_check_manifest_status_values(manifest, manifest_path))
    problems.extend(_check_manifest_phase_7_excluded_from_r2(manifest, manifest_path))
    return problems


def _check_debt_linkage(
    debt_lines: list[str],
    debt_register_path: Path,
    register_path: Path,
    cluster_b_text: str,
) -> list[str]:
    """Check every open debt-register id is cited in cluster B of the unscheduled register.

    Args:
        debt_lines: The R1 deferred-debt register's lines.
        debt_register_path: The debt register's path, for message text.
        register_path: The unscheduled-work register's path, for message text.
        cluster_b_text: Cluster B's joined ``Item`` column text.

    Returns:
        list[str]: One problem per uncited open debt id.
    """
    problems: list[str] = []
    open_debt_ids = _debt_register_open_ids(debt_lines)
    cited_debt_ids = _extract_citations(cluster_b_text, _DEBT_ID_RE)
    for debt_id, line_number in sorted(open_debt_ids.items()):
        if debt_id not in cited_debt_ids:
            problems.append(
                f"{debt_register_path.name}:{line_number}: debt '{debt_id}' is not marked "
                f"[Closed] or [Resolved] and is not cited by any row in cluster B of "
                f"{register_path.name}"
            )
    return problems


def _check_lessons_linkage(
    lessons_lines: list[str],
    lessons_log_path: Path,
    register_path: Path,
    cluster_c_text: str,
) -> list[str]:
    """Check every lesson still needing linkage is cited in cluster C of the unscheduled register.

    Args:
        lessons_lines: The authoring lessons log's lines.
        lessons_log_path: The lessons log's path, for message text.
        register_path: The unscheduled-work register's path, for message text.
        cluster_c_text: Cluster C's joined ``Item`` column text.

    Returns:
        list[str]: One problem per uncited open lesson id.
    """
    problems: list[str] = []
    open_lesson_ids = _lessons_needing_citation(lessons_lines)
    cited_lesson_ids = _extract_citations(cluster_c_text, _AL_ID_RE)
    for lesson_id, line_number in sorted(open_lesson_ids.items()):
        if lesson_id not in cited_lesson_ids:
            problems.append(
                f"{lessons_log_path.name}:{line_number}: lesson '{lesson_id}' status is not "
                f"applied/rejected/superseded and is not cited by any row in cluster C of "
                f"{register_path.name}"
            )
    return problems


def _check_capability_linkage(
    capability_lines: list[str],
    capability_register_path: Path,
    roadmap_lines: list[str],
    roadmap_path: Path,
) -> list[str]:
    """Check every open capability id appears in roadmap.md's register-item mapping section.

    Args:
        capability_lines: The capability register's lines. ``_capability_register_open_ids``
            derives the open set from these, so the "not marked done" rule has exactly one
            definition in this module; ``check_linkage`` only calls this once its own walk of the
            same document has already succeeded, so the walk here cannot raise a second copy of a
            structural problem the caller already reported.
        capability_register_path: The capability register's path, for message text.
        roadmap_lines: ``roadmap.md``'s lines.
        roadmap_path: ``roadmap.md``'s path, for message text.

    Returns:
        list[str]: One problem per open capability id missing from the mapping section.
    """
    problems: list[str] = []
    open_capability_ids = _capability_register_open_ids(capability_lines)
    mapping_text = _extract_roadmap_mapping_section(roadmap_lines)
    cited_capability_ids = _extract_citations(mapping_text, _CAP_ID_RE)
    for capability_id, line_number in sorted(open_capability_ids.items()):
        if capability_id not in cited_capability_ids:
            problems.append(
                f"{capability_register_path.name}:{line_number}: capability "
                f"'{capability_id}' is not marked done and does not appear in "
                f'{roadmap_path.name}\'s "Where every open register item lands" mapping'
            )
    return problems


def check_linkage(
    register_path: Path,
    roadmap_path: Path,
    debt_register_path: Path,
    lessons_log_path: Path,
    capability_register_path: Path,
    *,
    manifest_path: Path = _DEFAULT_MANIFEST,
    project_plan_path: Path = _DEFAULT_PROJECT_PLAN,
) -> list[str]:
    """Validate the work-linkage contract across all five planning documents plus the manifest.

    Args:
        register_path: The unscheduled-work register markdown file.
        roadmap_path: ``roadmap.md``, checked against the manifest's phase vocabulary and status
            vocabulary, and the home of the capability-register mapping section.
        debt_register_path: The R1 deferred-debt register markdown file.
        lessons_log_path: The authoring lessons log markdown file.
        capability_register_path: The capability register markdown file.
        manifest_path: ``plan-manifest.toml``, the phase vocabulary, phase-to-rung mapping, and
            two-axis status model's source of truth. Keyword-only with a default so existing
            callers passing five positional arguments keep working unchanged. Every check in
            this run, including the register's own ``Phase`` cell vocabulary, reads from this
            one file: a run cannot validate one document against this manifest and another
            against a different one.
        project_plan_path: ``PROJECT-PLAN.md``, which narrates the track-2 phases (6-9) that
            ``roadmap.md`` explicitly does not cover. Their manifest status is drift-checked
            against this document because there is no roadmap row to check it against.

    Returns:
        list[str]: One problem per failed check; empty when every check passes.
    """
    problems: list[str] = []

    register_lines = _read_lines(register_path, problems)
    if register_lines is None:
        return problems

    try:
        clusters = _find_clusters(register_lines)
    except LookupError as exc:
        problems.append(f"{register_path.name}: {exc}")
        return problems
    if not clusters:
        problems.append(f"no '## Cluster <letter>:' tables found in {register_path}")
        return problems

    # Loaded before the register rows are checked, because the phase vocabulary those rows are
    # validated against comes from this manifest and no other. Reading it from a module-level
    # default instead is what let a --manifest run validate Phase cells against one manifest and
    # everything else against another.
    manifest = _load_manifest(manifest_path, problems)
    phase_vocabulary = _manifest_phase_vocabulary(manifest)

    row_problems, cluster_item_text = _check_register_rows(clusters, phase_vocabulary)
    problems.extend(row_problems)

    if manifest is not None:
        problems.extend(_check_manifest_integrity(manifest, manifest_path))

    roadmap_lines = _read_lines(roadmap_path, problems)
    if roadmap_lines is not None and manifest is not None:
        track1_phases = _manifest_phases_for_track(manifest, 1)
        problems.extend(
            _check_roadmap_vocabulary(roadmap_lines, roadmap_path, track1_phases)
        )
        try:
            problems.extend(
                _check_roadmap_phase_status(roadmap_lines, roadmap_path, manifest)
            )
        except LookupError as exc:
            problems.append(f"{roadmap_path.name}: {exc}")

    if manifest is not None:
        plan_lines = _read_lines(project_plan_path, problems)
        if plan_lines is not None:
            problems.extend(
                _check_project_plan_phase_status(
                    plan_lines, project_plan_path, manifest
                )
            )

    debt_lines = _read_lines(debt_register_path, problems)
    if debt_lines is not None:
        try:
            problems.extend(
                _check_debt_linkage(
                    debt_lines,
                    debt_register_path,
                    register_path,
                    cluster_item_text.get("B", ""),
                )
            )
        except ValueError as exc:
            problems.append(f"{debt_register_path.name}: {exc}")

    lessons_lines = _read_lines(lessons_log_path, problems)
    if lessons_lines is not None:
        try:
            problems.extend(
                _check_lessons_linkage(
                    lessons_lines,
                    lessons_log_path,
                    register_path,
                    cluster_item_text.get("C", ""),
                )
            )
        except (LookupError, ValueError) as exc:
            problems.append(f"{lessons_log_path.name}: {exc}")

    capability_lines = _read_lines(capability_register_path, problems)
    capability_rows: list[tuple[int, str, str, str]] | None = None
    if capability_lines is not None:
        try:
            capability_rows = _capability_register_status_rows(capability_lines)
        except (LookupError, ValueError) as exc:
            problems.append(f"{capability_register_path.name}: {exc}")

    if capability_rows is not None:
        status_problems, _capability_glyph_counts = _check_capability_status_vocabulary(
            capability_rows, capability_register_path
        )
        problems.extend(status_problems)

    if (
        capability_rows is not None
        and capability_lines is not None
        and roadmap_lines is not None
    ):
        try:
            problems.extend(
                _check_capability_linkage(
                    capability_lines,
                    capability_register_path,
                    roadmap_lines,
                    roadmap_path,
                )
            )
        except ValueError as exc:
            problems.append(f"{capability_register_path.name}: {exc}")

    return problems


def _summary(register_path: Path) -> str:
    """Return a one-line-per-cluster row tally for a register already known to be well formed.

    Args:
        register_path: The validated register markdown file.

    Returns:
        str: A newline-terminated summary, one line per cluster plus a total.
    """
    lines = register_path.read_text(encoding="utf-8").splitlines()
    clusters = _find_clusters(lines)
    total = 0
    parts: list[str] = []
    for letter, (_header_cells, rows) in sorted(clusters.items()):
        total += len(rows)
        parts.append(f"{letter}={len(rows)}")
    return (
        f"     {total} row(s) across {len(clusters)} cluster(s): {', '.join(parts)}\n"
    )


def _capability_summary(capability_register_path: Path) -> str:
    """Return a one-line per-glyph tally for a capability register already known well formed.

    Args:
        capability_register_path: The validated capability register markdown file.

    Returns:
        str: A newline-terminated summary of ``Docs`` glyph counts, in checkmark/yellow/cross
            order.
    """
    lines = capability_register_path.read_text(encoding="utf-8").splitlines()
    rows = _capability_register_status_rows(lines)
    _problems, counts = _check_capability_status_vocabulary(
        rows, capability_register_path
    )
    total = sum(counts.values())
    parts = [
        f"{glyph}={counts[glyph]}"
        for glyph in _CAP_STATUS_GLYPH_ORDER
        if glyph in counts
    ]
    return f"     {total} capability row(s): {', '.join(parts)}\n"


def _resolve_cluster_issues_index(header_cells: list[str]) -> int | None:
    """Return a cluster header's issue-citation column index, or None when it has no such column.

    Any cluster whose header carries an issue-citation column participates in the bare-``#NNN``
    half of citation collection; clusters without one are skipped for that half and contribute
    only their ``issue:NNN`` ``Phase`` values. Both the plural and singular spellings of the
    column are accepted, because the register's cluster tables use both: matching only the plural
    silently dropped every row of the cluster headed ``| ID | Item | Issue | Status |``, so its
    citations were never checked against GitHub at all. Which clusters happen to have the column
    today is a fact about a different file and is deliberately not asserted here.

    Args:
        header_cells: A cluster table's header cells.

    Returns:
        int | None: The 0-based index of the first issue-citation column, or None.
    """
    return next(
        (
            header_cells.index(name)
            for name in _CLUSTER_ISSUE_COLUMN_NAMES
            if name in header_cells
        ),
        None,
    )


def _collect_register_issue_citations(
    clusters: dict[str, tuple[list[str], list[tuple[int, list[str]]]]],
) -> dict[int, list[tuple[str, str]]]:
    """Collect every GitHub issue number cited in the register, with each citing row's id/status.

    Two citation shapes are recognised: an ``issue:NNN`` ``Phase`` value (any cluster with a
    ``Phase`` column), and a bare ``#NNN`` reference inside any cluster's issue-citation column
    (see ``_resolve_cluster_issues_index``).

    Args:
        clusters: Cluster letter mapped to its header cells and data rows, as returned by
            ``_find_clusters``.

    Returns:
        dict[int, list[tuple[str, str]]]: Issue number mapped to every (row id, row ``Status``)
            pair that cites it. A number cited by more than one row keeps every citation, since
            each citing row's own ``Status`` independently determines whether citing a closed
            issue is a problem.
    """
    citations: dict[int, list[tuple[str, str]]] = {}

    def _add(number: int, entry_id: str, status: str) -> None:
        citations.setdefault(number, []).append((entry_id, status))

    for header_cells, rows in clusters.values():
        indexes = _resolve_column_indexes(header_cells)
        id_idx, status_idx, phase_idx = (
            indexes["ID"],
            indexes["Status"],
            indexes["Phase"],
        )
        issues_idx = _resolve_cluster_issues_index(header_cells)
        for _line_number, cells in rows:
            if len(cells) != len(header_cells):
                continue
            entry_id = cells[id_idx] if id_idx is not None else ""
            status = cells[status_idx] if status_idx is not None else ""
            if phase_idx is not None:
                phase_match = _ISSUE_PHASE_NUMBER_RE.match(cells[phase_idx])
                if phase_match:
                    _add(int(phase_match.group(1)), entry_id, status)
            if issues_idx is not None:
                for issue_match in _BARE_ISSUE_REF_RE.finditer(cells[issues_idx]):
                    _add(int(issue_match.group(1)), entry_id, status)

    return citations


def _validate_github_issue_payload(
    payload: object, problems: list[str]
) -> list[dict[str, Any]] | None:
    """Confirm a decoded ``gh issue list`` payload has the shape every caller assumes.

    ``_check_cited_issues_not_closed`` indexes ``issue["number"]`` and ``_check_issue_orphans``
    calls ``label.get("name")`` over ``issue["labels"]``. Both assumptions were unchecked, so a
    malformed entry surfaced as a ``KeyError``/``TypeError``/``AttributeError`` traceback deep in
    a check rather than as a reported problem at the boundary where the data enters. Validating
    once here is what lets those two functions state their preconditions instead of guarding
    them.

    Args:
        payload: The decoded JSON document, of unknown shape.
        problems: The running problem list; every shape violation is appended here.

    Returns:
        list[dict[str, Any]] | None: The payload as a list of issue objects, or None when it does
            not have that shape.
    """
    if not isinstance(payload, list):
        problems.append("gh issue list returned JSON that is not a list of issues")
        return None

    shape_problems: list[str] = []
    for position, entry in enumerate(payload):
        if not isinstance(entry, dict):
            shape_problems.append(
                f"entry {position} is {type(entry).__name__}, not an issue object"
            )
            continue
        number = entry.get("number")
        # bool is an int subclass; a JSON `true` here would otherwise pass as issue number 1.
        if not isinstance(number, int) or isinstance(number, bool):
            shape_problems.append(
                f"entry {position} has number={number!r}, which is not an integer"
            )
        labels = entry.get("labels", [])
        if not isinstance(labels, list) or not all(
            isinstance(label, dict) for label in labels
        ):
            shape_problems.append(
                f"entry {position} (issue {number!r}) has labels={labels!r}, which is not a "
                f"list of label objects"
            )
    if shape_problems:
        joined = "; ".join(shape_problems)
        problems.append(f"gh issue list returned unexpected-shape JSON: {joined}")
        return None

    return payload


def _fetch_github_issues(problems: list[str]) -> list[dict[str, Any]] | None:
    """Fetch issues (open and closed) via one batched, capped ``gh issue list`` call.

    A single call fetches number/state/title/labels for at most ``_GH_ISSUE_LIST_LIMIT`` issues,
    so both ``--check-issues`` (cited issue not CLOSED) and ``--check-issue-orphans`` (every OPEN
    issue cited somewhere) share this one network round trip rather than one call per issue
    number. The cap is real, not nominal: a repository that outgrows it makes this function
    report a problem rather than hand back a partial list.

    # #ASSUME: external resource: gh is installed, authenticated, and the network is reachable.
    # --check-issues/--check-issue-orphans are opt-in specifically so this call only ever runs
    # when a caller (CI, not pre-commit) has deliberately asked for it.
    # #VERIFY: every failure mode (missing binary, timeout, non-zero exit, unparsable JSON,
    # unexpected-shape JSON per _validate_github_issue_payload, and a result at the --limit cap)
    # is turned into an appended problem and a None return, never a silent empty or partial
    # result: a check that can only pass is worse than no check at all.
    # #ASSUME: external resource: `gh` resolves the target repository from its working
    # directory's git remote, so a run started from another clone or worktree would validate this
    # register against a different repository's issues.
    # #VERIFY: cwd is pinned to _REPO_ROOT, derived from this file's own location, so the issues
    # fetched always belong to the repository the script ships in; no owner/repo string is
    # hardcoded, so a fork or a rename needs no edit here.

    Args:
        problems: The running problem list; a missing gh, an auth or network failure, a
            timeout, a non-zero exit, unparsable or unexpected-shape JSON, or a truncated result
            is appended here instead of raised.

    Returns:
        list[dict[str, Any]] | None: The parsed issue list (each entry carrying an integer
            ``number`` and a list of label objects), or None if the call could not be completed
            or its result cannot be trusted to be complete.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "all",
                "--limit",
                str(_GH_ISSUE_LIST_LIMIT),
                "--json",
                "number,state,title,labels",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_ISSUE_LIST_TIMEOUT_SECONDS,
            check=False,
            cwd=_REPO_ROOT,
        )
    except FileNotFoundError:
        problems.append(
            "gh is not installed or not on PATH; --check-issues/--check-issue-orphans "
            "require the GitHub CLI"
        )
        return None
    except subprocess.TimeoutExpired:
        problems.append(
            f"gh issue list did not complete within {_GH_ISSUE_LIST_TIMEOUT_SECONDS}s"
        )
        return None

    if result.returncode != 0:
        problems.append(
            f"gh issue list failed (exit {result.returncode}): {result.stderr.strip()}"
        )
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        problems.append(f"gh issue list returned unparsable JSON: {exc}")
        return None

    issues = _validate_github_issue_payload(payload, problems)
    if issues is None:
        return None

    if len(issues) >= _GH_ISSUE_LIST_LIMIT:
        problems.append(
            f"gh issue list returned {len(issues)} issues, at or above its --limit of "
            f"{_GH_ISSUE_LIST_LIMIT}, so the result may be truncated; raise the limit or page "
            f"the query. Continuing on a partial set would report real issues as nonexistent "
            f"and under-report orphans"
        )
        return None

    return issues


def _check_cited_issues_not_closed(
    citations: dict[int, list[tuple[str, str]]],
    issues: list[dict[str, Any]],
    register_path: Path,
) -> list[str]:
    """Check every cited issue exists and, when its citing row is not done, is not CLOSED.

    Args:
        citations: Issue number mapped to citing (row id, row ``Status``) pairs, as returned by
            ``_collect_register_issue_citations``.
        issues: The fetched issue list, as returned by ``_fetch_github_issues``, whose entries
            are already validated to be objects with an integer ``number``.
        register_path: The unscheduled-work register's path, for message text.

    Returns:
        list[str]: One problem per citation of a nonexistent issue, plus one problem per
            not-done row citing an issue GitHub reports CLOSED.
    """
    problems: list[str] = []
    lookup = {issue["number"]: issue for issue in issues}
    for number, citers in sorted(citations.items()):
        issue = lookup.get(number)
        if issue is None:
            problems.extend(
                f"{register_path.name}: row '{entry_id}' cites issue #{number}, which "
                f"does not exist on GitHub"
                for entry_id, _status in citers
            )
            continue
        if issue.get("state") != "CLOSED":
            continue
        problems.extend(
            f"{register_path.name}: row '{entry_id}' (status '{status}') cites issue "
            f"#{number} ('{issue.get('title', '')}'), which GitHub reports CLOSED"
            for entry_id, status in citers
            if status != "done"
        )
    return problems


def _extract_issue_numbers_from_text(text: str) -> set[int]:
    """Return every GitHub issue number cited in a block of prose.

    Recognises both a bare ``#NNN`` reference and an inline ``issue:NNN`` mention.

    Args:
        text: The prose to search.

    Returns:
        set[int]: Every issue number cited.
    """
    numbers = {int(match) for match in _BARE_ISSUE_REF_RE.findall(text)}
    numbers |= {int(match) for match in _PROSE_ISSUE_REF_RE.findall(text)}
    return numbers


def _planning_docs_cited_issue_numbers(planning_dir: Path) -> set[int]:
    """Return every issue number cited anywhere in the planning tree under ``planning_dir``.

    Args:
        planning_dir: The directory to search recursively for planning documents (in the real
            repository, ``docs/planning/``). Both markdown and TOML are searched: see
            ``_PLANNING_DOC_SUFFIXES``.

    Returns:
        set[int]: Every issue number cited in any planning document found.
    """
    numbers: set[int] = set()
    for path in sorted(planning_dir.rglob("*")):
        if path.suffix not in _PLANNING_DOC_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        numbers |= _extract_issue_numbers_from_text(text)
    return numbers


def _check_issue_orphans(
    issues: list[dict[str, Any]], cited_numbers: set[int]
) -> list[str]:
    """Check every OPEN issue is either cited under docs/planning/ or labelled ``unplanned``.

    Args:
        issues: The fetched issue list, as returned by ``_fetch_github_issues``, whose entries
            are already validated to carry a list of label objects.
        cited_numbers: Every issue number cited anywhere under docs/planning/, as returned by
            ``_planning_docs_cited_issue_numbers``.

    Returns:
        list[str]: One problem per orphaned open issue, worded like every other message in this
            module: the rule broken, then the remedy. Emitting a bare ``"#NNN <title>"`` made
            these the only entries in the shared problem list that named a fact without naming
            what to do about it.
    """
    problems: list[str] = []
    for issue in issues:
        if issue.get("state") != "OPEN":
            continue
        number = issue.get("number")
        if number in cited_numbers:
            continue
        labels = {label.get("name", "") for label in issue.get("labels", [])}
        if _UNPLANNED_LABEL in labels:
            continue
        problems.append(
            f"issue #{number} ('{issue.get('title', '')}') is OPEN but is cited in no "
            f"document under docs/planning/ and does not carry the '{_UNPLANNED_LABEL}' "
            f"label; give it a phase home (cite it from a planning document, for example an "
            f"'issue:{number}' Phase value or a register row's issue column) or label it "
            f"'{_UNPLANNED_LABEL}'"
        )
    return problems


def _check_issues(
    register_path: Path,
    planning_dir: Path,
    *,
    check_issues: bool,
    check_issue_orphans: bool,
) -> list[str]:
    """Run the opt-in GitHub issue checks, sharing one batched ``gh issue list`` call.

    Both checks are off by default (see ``main``'s ``--check-issues``/``--check-issue-orphans``
    flags): they need network access and ``gh`` auth, which pre-commit's offline, fast posture
    cannot assume, so only an explicit flag (as CI passes) runs them at all.

    Args:
        register_path: The unscheduled-work register markdown file, searched for citations by
            ``--check-issues``.
        planning_dir: The directory searched recursively for citations by
            ``--check-issue-orphans`` (in the real repository, ``docs/planning/``).
        check_issues: Whether to run the cited-issue-not-closed check.
        check_issue_orphans: Whether to run the open-issue-cited-somewhere check.

    Returns:
        list[str]: Problems found; empty when neither flag is set or every check passes.
    """
    if not check_issues and not check_issue_orphans:
        return []

    problems: list[str] = []
    issues = _fetch_github_issues(problems)
    if issues is None:
        return problems

    if check_issues:
        register_lines = _read_lines(register_path, problems)
        if register_lines is not None:
            try:
                clusters = _find_clusters(register_lines)
            except LookupError as exc:
                problems.append(f"{register_path.name}: {exc}")
            else:
                citations = _collect_register_issue_citations(clusters)
                problems.extend(
                    _check_cited_issues_not_closed(citations, issues, register_path)
                )

    if check_issue_orphans:
        cited_numbers = _planning_docs_cited_issue_numbers(planning_dir)
        problems.extend(_check_issue_orphans(issues, cited_numbers))

    return problems


def main(argv: list[str] | None = None) -> int:
    """Validate the work-linkage contract using paths named on the command line.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        int: 0 when every check passes, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Validate the unscheduled-work register's work-linkage contract."
    )
    parser.add_argument(
        "--register",
        default=str(_DEFAULT_REGISTER),
        help="Path to the unscheduled-work register markdown file.",
    )
    parser.add_argument(
        "--roadmap",
        default=str(_DEFAULT_ROADMAP),
        help="Path to roadmap.md, checked against the manifest's phase vocabulary.",
    )
    parser.add_argument(
        "--manifest",
        default=str(_DEFAULT_MANIFEST),
        help=(
            "Path to plan-manifest.toml, the phase vocabulary, phase-to-rung mapping, and "
            "status model's source of truth. Every check in the run reads from this one file, "
            "including the register's Phase-cell vocabulary."
        ),
    )
    parser.add_argument(
        "--project-plan",
        default=str(_DEFAULT_PROJECT_PLAN),
        help=(
            "Path to PROJECT-PLAN.md, which narrates the track-2 phases roadmap.md states it "
            "does not cover. Their manifest status is drift-checked against this file."
        ),
    )
    parser.add_argument(
        "--debt-register",
        default=str(_DEFAULT_DEBT_REGISTER),
        help="Path to the R1 deferred-debt register markdown file.",
    )
    parser.add_argument(
        "--lessons-log",
        default=str(_DEFAULT_LESSONS_LOG),
        help="Path to the authoring lessons log markdown file.",
    )
    parser.add_argument(
        "--capability-register",
        default=str(_DEFAULT_CAPABILITY_REGISTER),
        help="Path to the capability register markdown file.",
    )
    parser.add_argument(
        "--check-issues",
        action="store_true",
        help=(
            "Also validate that a register row citing a GitHub issue (an 'issue:NNN' Phase "
            "value, or a bare '#NNN' inside a cluster D row) never cites an issue GitHub "
            "reports CLOSED while the row itself is not done, and that every cited issue "
            "number exists. Off by default: needs network access and 'gh' auth, so pre-commit "
            "stays offline; only CI passes this flag."
        ),
    )
    parser.add_argument(
        "--check-issue-orphans",
        action="store_true",
        help=(
            "Also validate that every OPEN GitHub issue is cited by some markdown or TOML "
            "document under docs/planning/, or carries the 'unplanned' label. Off by default, "
            "independent of --check-issues: needs network access and 'gh' auth."
        ),
    )
    args = parser.parse_args(argv)

    register_path = Path(args.register)
    capability_register_path = Path(args.capability_register)
    problems = check_linkage(
        register_path,
        Path(args.roadmap),
        Path(args.debt_register),
        Path(args.lessons_log),
        capability_register_path,
        manifest_path=Path(args.manifest),
        project_plan_path=Path(args.project_plan),
    )
    problems.extend(
        _check_issues(
            register_path,
            register_path.parent,
            check_issues=args.check_issues,
            check_issue_orphans=args.check_issue_orphans,
        )
    )
    if problems:
        sys.stdout.write(f"FAIL {register_path}:\n")
        for problem in problems:
            sys.stdout.write(f"  - {problem}\n")
        return 1

    sys.stdout.write(f"ok: {register_path.name} satisfies the work-linkage contract\n")
    sys.stdout.write(_summary(register_path))
    sys.stdout.write(_capability_summary(capability_register_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
