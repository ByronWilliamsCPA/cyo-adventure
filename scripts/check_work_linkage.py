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

Vocabulary drift: the contract claims ``roadmap.md`` is the source of truth for the product-phase
vocabulary. This script parses ``## Phase`` headings (and the ``2b``/``4a``/``4b`` sub-headings
that do not follow that exact shape) out of ``roadmap.md`` and fails if the hardcoded vocabulary
disagrees with what the roadmap actually contains, so a new phase added to the roadmap without a
vocabulary update is caught here rather than discovered later.

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
import re
import sys
from pathlib import Path

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

_UW_ID_RE = re.compile(r"^UW-[A-M]\d{2}$")

_STATUSES = frozenset({"unscheduled", "blocked", "decision", "verify", "done"})

# The closed phase vocabulary from "### Phase vocabulary (closed set)" and
# "### Non-phase dispositions (closed set)" in the linkage contract.
_PRODUCT_PHASES = frozenset({"0", "1", "2", "2b", "3", "4a", "4b", "4c", "4d", "5"})
_TRACK2_PHASES = frozenset({"6", "7", "8", "9"})
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


def _capability_register_open_ids(lines: list[str]) -> dict[str, int]:
    """Return capability ids not marked done, mapped to their 1-based line number.

    The register holds four separate tables (K, G, A, S), each headed by its own
    ``| ID | Capability | Docs | Notes |`` row; this walks the whole file once and tracks
    whichever header was most recently seen, so a row only counts once a header naming a ``Docs``
    column has been observed. Each ``## `` section heading resets the tracked header, so a
    same-shaped table appearing later in the document (outside the four capability sections)
    cannot be mistaken for an open capability row under a stale header. The ``Docs`` cell holds
    exactly one status glyph (verified against the current document: no row mixes a glyph with
    other text), so an equality check against the done mark is reliable rather than a loose
    substring test.

    Args:
        lines: The capability register's lines.

    Returns:
        dict[str, int]: Open (not done) capability ids mapped to the line they were found on.

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
        return {}
    docs_idx: int | None = None
    tables_found = 0
    open_ids: dict[str, int] = {}
    unlocated: list[tuple[str, int]] = []
    for number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            docs_idx = None
            continue
        if "|" not in line:
            continue
        cells = _split_row(line)
        if not cells:
            continue
        header_docs_idx = _capability_header_docs_index(cells)
        if header_docs_idx is not None:
            docs_idx = header_docs_idx
            tables_found += 1
            continue
        if _is_separator(cells) or not _CAP_ROW_ID_RE.match(cells[0]):
            continue
        if docs_idx is None:
            unlocated.append((cells[0], number))
        elif len(cells) > docs_idx and cells[docs_idx] != _CAP_DONE_MARK:
            open_ids[cells[0]] = number
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
    return open_ids


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
    roadmap_lines: list[str], roadmap_path: Path
) -> list[str]:
    """Check the roadmap's phase headings agree with the hardcoded product-phase vocabulary.

    Args:
        roadmap_lines: ``roadmap.md``'s lines.
        roadmap_path: ``roadmap.md``'s path, for message text.

    Returns:
        list[str]: One problem if the derived and hardcoded vocabularies disagree; empty
            otherwise.
    """
    derived = frozenset(_extract_roadmap_product_phases("\n".join(roadmap_lines)))
    if derived == _PRODUCT_PHASES:
        return []
    missing = ", ".join(sorted(_PRODUCT_PHASES - derived)) or "(none)"
    extra = ", ".join(sorted(derived - _PRODUCT_PHASES)) or "(none)"
    return [
        (
            f"product-phase vocabulary drift: {roadmap_path.name} is missing headings for "
            f"{missing} and declares unrecognised phase(s) {extra}; update the hardcoded "
            f"vocabulary and this check together with the roadmap change"
        )
    ]


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
        capability_lines: The capability register's lines.
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
) -> list[str]:
    """Validate the work-linkage contract across all five planning documents.

    Args:
        register_path: The unscheduled-work register markdown file.
        roadmap_path: ``roadmap.md``, the product-phase vocabulary's source of truth and the home
            of the capability-register mapping section.
        debt_register_path: The R1 deferred-debt register markdown file.
        lessons_log_path: The authoring lessons log markdown file.
        capability_register_path: The capability register markdown file.

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

    roadmap_lines = _read_lines(roadmap_path, problems)
    if roadmap_lines is not None:
        problems.extend(_check_roadmap_vocabulary(roadmap_lines, roadmap_path))

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
    if capability_lines is not None and roadmap_lines is not None:
        try:
            problems.extend(
                _check_capability_linkage(
                    capability_lines,
                    capability_register_path,
                    roadmap_lines,
                    roadmap_path,
                )
            )
        except (LookupError, ValueError) as exc:
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
        help="Path to roadmap.md, the product-phase vocabulary's source of truth.",
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
    args = parser.parse_args(argv)

    register_path = Path(args.register)
    problems = check_linkage(
        register_path,
        Path(args.roadmap),
        Path(args.debt_register),
        Path(args.lessons_log),
        Path(args.capability_register),
    )
    if problems:
        sys.stdout.write(f"FAIL {register_path}:\n")
        for problem in problems:
            sys.stdout.write(f"  - {problem}\n")
        return 1

    sys.stdout.write(f"ok: {register_path.name} satisfies the work-linkage contract\n")
    sys.stdout.write(_summary(register_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
