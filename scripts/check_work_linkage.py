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
   phase vocabulary.
4. A ``Phase`` value never holds more than one value (no comma).
5. A ``Phase`` value never repeats a ``Status`` value.
6. A ``Phase`` value is never empty when ``Status`` is ``unscheduled``.
7. Ids are unique across the whole register, not just within one cluster.

Vocabulary drift: ``docs/planning/plan-manifest.toml`` (the "plan manifest") is the source of
truth for the phase vocabulary, the phase-to-rung mapping, and the two-axis (``shipped``/
``usable``) status model; ``roadmap.md`` is checked against it, not the other way around. This
script parses ``## Phase`` headings (and the ``2b``/``4a``/``4b`` sub-headings that do not follow
that exact shape) out of ``roadmap.md`` and fails if the manifest's track-1 phase set disagrees
with what the roadmap actually contains, so a new phase added to the roadmap without a matching
manifest entry is caught here rather than discovered later. Two further checks guard the manifest
and the roadmap's prose against each other:

* ``_check_manifest_integrity``: the manifest is internally consistent (every rung's phase
  references exist, ``requires_phases``/``excludes_phases`` are disjoint, the rungs are
  monotonic, every phase's status pair has a matching ``[status_vocabulary]`` entry, and Phase 7
  does not gate R2).
* ``_check_roadmap_phase_status``: the roadmap's phase-status table prose (for example
  "Substantially delivered") matches the term the manifest's ``[status_vocabulary]`` derives from
  that phase's ``(shipped, usable)`` pair.

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

Usage::

    uv run python scripts/check_work_linkage.py
    uv run python scripts/check_work_linkage.py --register path/to/register.md

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

_UW_ID_RE = re.compile(r"^UW-[A-M]\d{2}$")

_STATUSES = frozenset({"unscheduled", "blocked", "decision", "verify", "done"})

_MANIFEST_STATUS_VALUES = frozenset({"yes", "partial", "no"})


def _load_manifest(path: Path, problems: list[str]) -> dict[str, Any] | None:
    """Read and parse ``plan-manifest.toml``, recording a problem instead of raising.

    Uses the standard-library ``tomllib`` parser rather than a third-party TOML or YAML
    library: this script also runs under pre-commit and in CI, contexts where the dev extras
    that a third-party parser would live in may not be installed.

    Args:
        path: The plan manifest TOML file.
        problems: The running problem list; a read or parse failure is appended here.

    Returns:
        dict[str, Any] | None: The parsed manifest, or None if it could not be read or parsed.
    """
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
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
    return frozenset(
        token
        for token, entry in phases.items()
        if isinstance(entry, dict) and entry.get("track") == track
    )


def _bootstrap_phase_vocabulary() -> tuple[frozenset[str], frozenset[str]]:
    """Load the default plan manifest's track-1/track-2 phase vocabulary at import time.

    ``_phase_in_vocabulary`` (and everything built on it, such as ``_check_row_phase``) needs a
    phase vocabulary available without every call site threading a manifest through to validate
    one already-known value. Loading the default manifest once here, rather than hardcoding the
    phase sets, is what removes the old dual source of truth (a hardcoded frozenset that could
    silently drift from ``plan-manifest.toml``). A missing or unparseable manifest does not raise
    here: it falls back to an empty vocabulary so importing this module never crashes;
    ``check_linkage()`` loads the manifest itself and reports a clear problem for that same
    failure when it actually runs the checks that depend on it.

    Returns:
        tuple[frozenset[str], frozenset[str]]: The track-1 and track-2 phase token sets.
    """
    # #ASSUME: external resource: the default manifest exists and parses at import time.
    # #VERIFY: a missing/broken manifest degrades to an empty vocabulary rather than an
    # ImportError, so every _check_row_phase call fails closed (every phase value rejected)
    # instead of the module refusing to load; check_linkage() separately loads and reports the
    # same failure explicitly, so the root cause is not left to be inferred from the symptom.
    bootstrap_problems: list[str] = []
    manifest = _load_manifest(_DEFAULT_MANIFEST, bootstrap_problems)
    if manifest is None:
        return frozenset(), frozenset()
    return (
        _manifest_phases_for_track(manifest, 1),
        _manifest_phases_for_track(manifest, 2),
    )


# The phase vocabulary, derived from plan-manifest.toml's [phases] table rather than
# hardcoded: see _bootstrap_phase_vocabulary. plan-manifest.toml is now the single source of
# truth for phase tokens; roadmap.md's headings are checked against it (_check_roadmap_vocabulary)
# instead of the other way around.
_PRODUCT_PHASES, _TRACK2_PHASES = _bootstrap_phase_vocabulary()
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
_CAP_DONE_MARK = "✅"  # the register's "done" checkmark cell value (U+2705).
_CAP_OPEN_GLYPHS = frozenset({"🟡", "❌"})  # partial (U+1F7E1) and missing (U+274C).
_CAP_STATUS_GLYPHS = frozenset({_CAP_DONE_MARK}) | _CAP_OPEN_GLYPHS

# An "issue:NNN" Phase cell, capturing the number (the vocabulary check, _ISSUE_RE above, only
# needs to confirm the shape; the GitHub issue checks need the number itself).
_ISSUE_PHASE_NUMBER_RE = re.compile(r"^issue:(\d+)$")
# A bare "#NNN" reference, used both inside a cluster D row's Issues column and when scanning
# the wider docs/planning/ tree for citations (the orphan check).
_BARE_ISSUE_REF_RE = re.compile(r"#(\d+)")
# An inline "issue:NNN" mention in prose (not anchored like _ISSUE_PHASE_NUMBER_RE, since prose
# can carry it mid-sentence rather than as a whole Phase cell value).
_PROSE_ISSUE_REF_RE = re.compile(r"\bissue:(\d+)\b")

# #ASSUME: external resource: gh issue list over the network can hang on a stalled connection.
# #VERIFY: _fetch_github_issues passes this as subprocess.run's timeout, so a hung call becomes
# a reported problem (TimeoutExpired caught explicitly) rather than blocking the run forever.
_GH_ISSUE_LIST_TIMEOUT_SECONDS = 30

# The mapping section roadmap.md's linkage contract points at for capability-register linkage.
_ROADMAP_MAPPING_HEADING = "### Where every open register item lands"

# "`SL1` through `SL10`" style natural-language ranges: a same-prefix id range spelled out with
# "through" instead of listing every id, used once in cluster B for the ten SL debts (each id is
# itself wrapped in backticks as inline code, hence the optional backtick on both sides).
# Expanding it is a deliberate reading of the document's own convention, not a relaxation of the
# check: the alternative is flagging SL2..SL9 as false-positive orphans despite being plainly in
# scope.
_THROUGH_RANGE_RE = re.compile(r"`?\b([A-Z]{1,2})(\d+)`?\s+through\s+`?\1(\d+)`?\b")
# A same-prefix range wider than this is almost certainly a typo (transposed digits, wrong
# id) rather than a real citation span; expanding it anyway would silently manufacture
# thousands of ids that were never actually cited, masking the typo as ordinary bulk linkage.
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
    unescaped_pipe = re.compile(r"(?<!\\)\|")
    cells = [
        cell.strip().replace("\\|", "|") for cell in unescaped_pipe.split(line.strip())
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


def _phase_in_vocabulary(phase: str) -> bool:
    """Report whether a ``Phase`` value is in the linkage contract's closed vocabulary.

    Args:
        phase: A single, already-trimmed ``Phase`` cell value (never comma-separated; callers
            check that separately).

    Returns:
        bool: True when the value is a recognised phase, milestone, release rung, named
            workstream, or sentinel.
    """
    return (
        phase in _PRODUCT_PHASES
        or phase in _TRACK2_PHASES
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
    cluster: str, number: int, entry_id: str, phase: str, status: str
) -> list[str]:
    """Return problems with a register row's ``Phase`` value.

    Checks, in order: empty on an ``unscheduled`` row; more than one value; repeating a ``Status``
    value; and membership in the closed phase vocabulary. A comma-separated or status-echoing
    value is reported once and not also checked against the vocabulary, since it fails on its own
    terms regardless of vocabulary membership.

    Args:
        cluster: The cluster letter the row belongs to, for the message.
        number: The row's 1-based line number.
        entry_id: The row's ``ID`` cell value, for the message.
        phase: The row's ``Phase`` cell value.
        status: The row's ``Status`` cell value, to check the phase does not repeat it and, when
            phase is empty, whether that emptiness is itself the problem.

    Returns:
        list[str]: Problems found; empty when the phase is well formed.
    """
    if not phase:
        if status == "unscheduled":
            return [
                (
                    f"{entry_id} (cluster {cluster} line {number}): Phase is empty but Status is "
                    f"'unscheduled'"
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

    if not _phase_in_vocabulary(phase):
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
        ValueError: If a "through" range spans more than ``_THROUGH_RANGE_MAX_SPAN`` ids; such a
            span is far more likely to be a typo than a real citation range, and expanding it
            would silently manufacture ids nobody actually cited.
    """
    cited = set(id_re.findall(text))
    for match in _THROUGH_RANGE_RE.finditer(text):
        prefix, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        if end - start > _THROUGH_RANGE_MAX_SPAN:
            msg = (
                f"'{match.group(0)}' spans {end - start + 1} ids, more than the "
                f"{_THROUGH_RANGE_MAX_SPAN}-id sanity bound; check for a typo in the range"
            )
            raise ValueError(msg)
        cited.update(f"{prefix}{number}" for number in range(start, end + 1))
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
            cell) tuple per capability row. A row with fewer cells than the ``Docs`` column
            index is silently skipped, mirroring the original single-purpose walk this replaces:
            such a row is malformed in a way no check here is positioned to name usefully. The
            ``Notes`` cell is empty string when the table has no ``Notes`` column or the row has
            too few cells to reach it.

    Raises:
        LookupError: If any row shaped like a capability row (its first cell matches the
            ``[KGAS]NN`` id pattern) is found with no header located for its table, whether
            because the whole document has no locatable header or because one table's header
            specifically was renamed or dropped while the others stayed intact. Catching only
            the all-tables-missing case would leave a single corrupted header (e.g. just the K
            table's) silently invisible: that table's rows would fall under ``docs_idx=None``
            and every one of them would be dropped rather than flagged. A document with no
            pipe-containing line at all is not this failure mode and returns no rows instead.
    """
    if not any("|" in line for line in lines):
        return []
    docs_idx: int | None = None
    notes_idx: int | None = None
    tables_found = 0
    rows: list[tuple[int, str, str, str]] = []
    unlocated: list[tuple[str, int]] = []
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
    return rows


def _capability_register_open_ids(  # pyright: ignore[reportUnusedFunction]
    lines: list[str],
) -> dict[str, int]:
    """Return capability ids not marked done, mapped to their 1-based line number.

    The ``Docs`` cell holds exactly one status glyph (verified against the current document: no
    row mixes a glyph with other text), so an equality check against the done mark is reliable
    rather than a loose substring test.

    Kept as a standalone, from-raw-lines entry point even though ``check_linkage`` now derives
    open ids inline from ``_capability_register_status_rows`` (to avoid re-parsing the register
    and reporting a malformed-header ``LookupError`` twice): ``tests/unit/test_check_work_linkage.py``
    exercises this function's from-raw-lines contract directly, including the malformed-header
    and corrupted-single-table cases, so it stays production code rather than test-only fixture
    logic, just with no in-module caller.

    Args:
        lines: The capability register's lines.

    Returns:
        dict[str, int]: Open (not done) capability ids mapped to the line they were found on.

    Raises:
        LookupError: See ``_capability_register_status_rows``, which this delegates the walk to.
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
) -> tuple[list[str], dict[str, str]]:
    """Run every row-level check across all cluster tables, plus the register-wide id check.

    Args:
        clusters: Cluster letter mapped to its header cells and data rows, as returned by
            ``_find_clusters``.

    Returns:
        tuple[list[str], dict[str, str]]: The problems found, and each cluster letter mapped to
            its joined ``Item`` column text, for the cross-register citation checks that follow.
    """
    problems: list[str] = []
    all_ids: dict[str, list[int]] = {}
    cluster_item_text: dict[str, str] = {}

    for letter, (header_cells, rows) in sorted(clusters.items()):
        row_problems, item_texts, row_ids = _check_cluster_rows(
            letter, header_cells, rows
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
    letter: str, number: int, cells: list[str], indexes: dict[str, int | None]
) -> tuple[list[str], str | None, str]:
    """Run the id, status, and phase checks on one already length-checked cluster row.

    Args:
        letter: The cluster letter, for message text.
        number: The row's 1-based line number.
        cells: The row's cell values, already confirmed to match the header's column count.
        indexes: The header's resolved column indexes, as returned by
            ``_resolve_column_indexes``.

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
            _check_row_phase(letter, number, entry_id, cells[phase_idx], status)
        )

    item_text = cells[item_idx] if item_idx is not None else None

    return problems, item_text, entry_id


def _check_cluster_rows(
    letter: str, header_cells: list[str], rows: list[tuple[int, list[str]]]
) -> tuple[list[str], list[str], list[tuple[str, int]]]:
    """Run the id, status, and phase checks on one cluster table's data rows.

    Args:
        letter: The cluster letter, for message text and the returned id list.
        header_cells: The cluster table's header cells, used to resolve column indexes.
        rows: The cluster's (1-based line number, cells) data rows.

    Returns:
        tuple[list[str], list[str], list[tuple[str, int]]]: The problems found, the ``Item``
            column text of every row (for later citation checks), and each row's (id, line
            number) pair (for the register-wide id-uniqueness check).
    """
    indexes = _resolve_column_indexes(header_cells)

    problems: list[str] = []
    item_texts: list[str] = []
    row_ids: list[tuple[str, int]] = []

    for number, cells in rows:
        if len(cells) != len(header_cells):
            problems.append(
                f"cluster {letter} line {number}: expected {len(header_cells)} columns, "
                f"found {len(cells)}"
            )
            continue

        row_problems, item_text, entry_id = _check_one_row(
            letter, number, cells, indexes
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


_MANIFEST_PHASE_STATUS_HEADER_CELLS = ("Phase", "Status")
# "5 Hardening" -> "5"; "4c Family Loops (NEW 2026-07-16)" -> "4c". The phase token is always
# the first whitespace-separated word of the roadmap phase-status table's first column.
_ROADMAP_PHASE_STATUS_TOKEN_RE = re.compile(r"^(\S+)")
# A leading status glyph (for example the checkmark or the yellow-circle emoji) plus any
# whitespace before the prose proper begins.
_ROADMAP_STATUS_LEADING_GLYPH_RE = re.compile(r"^[^A-Za-z]+")
# A single trailing parenthetical qualifier, for example "(backend)" or "(2026-07-20 audit)".
_ROADMAP_STATUS_TRAILING_QUALIFIER_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _normalize_roadmap_status_prose(status_cell: str) -> str:
    """Strip a roadmap phase-status cell down to its bare, lower-cased status term.

    "``✅ Substantially delivered (2026-07-20 audit)``" becomes "``substantially delivered``":
    the leading glyph and the trailing qualifier are noise around the one term this check
    actually compares against the manifest's ``[status_vocabulary]``.

    Args:
        status_cell: The roadmap phase-status table's ``Status`` column value for one row.

    Returns:
        str: The lower-cased status term, with the leading glyph and trailing parenthetical
            qualifier removed.
    """
    without_glyph = _ROADMAP_STATUS_LEADING_GLYPH_RE.sub("", status_cell)
    without_qualifier = _ROADMAP_STATUS_TRAILING_QUALIFIER_RE.sub("", without_glyph)
    return without_qualifier.strip().lower()


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
    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = _split_row(line)
        if cells and cells[0] == "Phase" and "Status" in cells:
            return index, 0, cells.index("Status")
    return None


def _roadmap_phase_status_rows(lines: list[str]) -> list[tuple[int, str, str]]:
    """Return each row of the roadmap's phase-status table as (line, phase token, status prose).

    A roadmap document that simply has no such table (every test fixture in this suite, and
    conceivably a future roadmap restructure) is not a failure: it has nothing for this check to
    compare, the same "genuinely nothing here yet" treatment ``_lessons_needing_citation`` and
    ``_capability_register_open_ids`` give a document with no table-like content at all. The
    table's own presence and shape are not this script's concern; only its status prose, once
    found, is.

    Args:
        lines: ``roadmap.md``'s lines.

    Returns:
        list[tuple[int, str, str]]: One (1-based line number, phase token, raw ``Status`` cell
            text) tuple per data row; empty if the table cannot be located.
    """
    located = _find_roadmap_phase_status_header(lines)
    if located is None:
        return []
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
    against the roadmap cell with its leading glyph and trailing parenthetical qualifier
    stripped. A phase token the manifest does not recognise, or a ``(shipped, usable)`` pair
    with no ``[status_vocabulary]`` entry, is not reported here: those are the vocabulary-drift
    and manifest-integrity checks' findings respectively, and reporting them a second time here
    would just be duplicate noise about the same root cause.

    Args:
        roadmap_lines: ``roadmap.md``'s lines.
        roadmap_path: ``roadmap.md``'s path, for message text.
        manifest: The parsed plan-manifest.toml document.

    Returns:
        list[str]: One problem per row whose status prose does not match the manifest-derived
            term; empty when every row matches (including when the table is not found at all).
    """
    phases = manifest.get("phases", {})
    vocabulary = manifest.get("status_vocabulary", {})

    problems: list[str] = []
    for line_number, phase_token, status_cell in _roadmap_phase_status_rows(
        roadmap_lines
    ):
        entry = phases.get(phase_token)
        if not isinstance(entry, dict):
            continue
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

    Runs every self-consistency check the manifest can be validated against without reference to
    any other document: rung phase references resolve, requires/excludes never overlap, the
    release ladder is monotonic, every phase's status pair has a vocabulary term, every status
    value is in the closed vocabulary, and Phase 7 does not gate R2.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: Problems found; empty when the manifest is internally consistent.
    """
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
    capability_rows: list[tuple[int, str, str, str]],
    capability_register_path: Path,
    roadmap_lines: list[str],
    roadmap_path: Path,
) -> list[str]:
    """Check every open capability id appears in roadmap.md's register-item mapping section.

    Args:
        capability_rows: The capability register's rows, as returned by
            ``_capability_register_status_rows``; taking the already-walked rows rather than raw
            lines means a malformed header is only reported once, by the caller that first walks
            the document, not duplicated here.
        capability_register_path: The capability register's path, for message text.
        roadmap_lines: ``roadmap.md``'s lines.
        roadmap_path: ``roadmap.md``'s path, for message text.

    Returns:
        list[str]: One problem per open capability id missing from the mapping section.
    """
    problems: list[str] = []
    open_capability_ids = {
        entry_id: number
        for number, entry_id, docs_val, _notes_val in capability_rows
        if docs_val != _CAP_DONE_MARK
    }
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
            callers passing five positional arguments keep working unchanged.

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

    row_problems, cluster_item_text = _check_register_rows(clusters)
    problems.extend(row_problems)

    manifest = _load_manifest(manifest_path, problems)
    if manifest is not None:
        problems.extend(_check_manifest_integrity(manifest, manifest_path))

    roadmap_lines = _read_lines(roadmap_path, problems)
    if roadmap_lines is not None and manifest is not None:
        track1_phases = _manifest_phases_for_track(manifest, 1)
        problems.extend(
            _check_roadmap_vocabulary(roadmap_lines, roadmap_path, track1_phases)
        )
        problems.extend(
            _check_roadmap_phase_status(roadmap_lines, roadmap_path, manifest)
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
        except LookupError as exc:
            problems.append(f"{capability_register_path.name}: {exc}")

    if capability_rows is not None:
        status_problems, _capability_glyph_counts = _check_capability_status_vocabulary(
            capability_rows, capability_register_path
        )
        problems.extend(status_problems)

    if capability_rows is not None and roadmap_lines is not None:
        try:
            problems.extend(
                _check_capability_linkage(
                    capability_rows,
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
        for glyph in (_CAP_DONE_MARK, "🟡", "❌")
        if glyph in counts
    ]
    return f"     {total} capability row(s): {', '.join(parts)}\n"


def _resolve_cluster_issues_index(header_cells: list[str]) -> int | None:
    """Return a cluster header's ``Issues`` column index, or None when it has no such column.

    Only cluster D currently has an ``Issues`` column; every other cluster's rows are simply
    skipped for the bare-``#NNN`` half of citation collection.

    Args:
        header_cells: A cluster table's header cells.

    Returns:
        int | None: The 0-based ``Issues`` column index, or None.
    """
    return header_cells.index("Issues") if "Issues" in header_cells else None


def _collect_register_issue_citations(
    clusters: dict[str, tuple[list[str], list[tuple[int, list[str]]]]],
) -> dict[int, list[tuple[str, str]]]:
    """Collect every GitHub issue number cited in the register, with each citing row's id/status.

    Two citation shapes are recognised: an ``issue:NNN`` ``Phase`` value (any cluster with a
    ``Phase`` column), and a bare ``#NNN`` reference inside a cluster D row's ``Issues`` column.

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


def _fetch_github_issues(problems: list[str]) -> list[dict[str, Any]] | None:
    """Fetch every issue (open and closed) via one batched ``gh issue list`` call.

    A single call fetches number/state/title/labels for up to 500 issues, so both
    ``--check-issues`` (cited issue not CLOSED) and ``--check-issue-orphans`` (every OPEN issue
    cited somewhere) share this one network round trip rather than one call per issue number.

    # #ASSUME: external resource: gh is installed, authenticated against this repository, and
    # the network is reachable. --check-issues/--check-issue-orphans are opt-in specifically so
    # this call only ever runs when a caller (CI, not pre-commit) has deliberately asked for it.
    # #VERIFY: every failure mode (missing binary, timeout, non-zero exit, unparsable or
    # unexpected-shape JSON) is turned into an appended problem and a None return, never a
    # silent empty result: a check that can only pass is worse than no check at all.

    Args:
        problems: The running problem list; a missing gh, an auth or network failure, a
            timeout, a non-zero exit, or unparsable JSON is appended here instead of raised.

    Returns:
        list[dict[str, Any]] | None: The parsed issue list (each entry carrying at least
            ``number``, ``state``, ``title``, ``labels``), or None if the call could not be
            completed.
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
                "500",
                "--json",
                "number,state,title,labels",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_ISSUE_LIST_TIMEOUT_SECONDS,
            check=False,
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
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        problems.append(f"gh issue list returned unparsable JSON: {exc}")
        return None

    if not isinstance(issues, list):
        problems.append("gh issue list returned JSON that is not a list of issues")
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
        issues: The fetched issue list, as returned by ``_fetch_github_issues``.
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
    """Return every issue number cited anywhere in the markdown tree under ``planning_dir``.

    Args:
        planning_dir: The directory to search recursively for ``*.md`` files (in the real
            repository, ``docs/planning/``).

    Returns:
        set[int]: Every issue number cited in any markdown file found.
    """
    numbers: set[int] = set()
    for path in sorted(planning_dir.rglob("*.md")):
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
        issues: The fetched issue list, as returned by ``_fetch_github_issues``.
        cited_numbers: Every issue number cited anywhere under docs/planning/, as returned by
            ``_planning_docs_cited_issue_numbers``.

    Returns:
        list[str]: One ``"#NNN <title>"`` entry per orphaned open issue.
    """
    problems: list[str] = []
    for issue in issues:
        if issue.get("state") != "OPEN":
            continue
        number = issue.get("number")
        if number in cited_numbers:
            continue
        labels = {label.get("name", "") for label in issue.get("labels", [])}
        if "unplanned" in labels:
            continue
        problems.append(f"#{number} {issue.get('title', '')}")
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
            "status model's source of truth."
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
            "Also validate that every OPEN GitHub issue is cited somewhere under "
            "docs/planning/ or carries the 'unplanned' label. Off by default, independent of "
            "--check-issues: needs network access and 'gh' auth."
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
