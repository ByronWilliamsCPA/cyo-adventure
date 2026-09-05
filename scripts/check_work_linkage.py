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

1. Every id matches the manifest's ``[namespaces.uw]`` pattern, and the cluster letter that
   pattern captures matches the cluster table the row was found in.
2. Every ``Status`` is one of: unscheduled, blocked, decision, verify, done.
3. Where a ``Phase`` column exists (clusters L and M have none), its value is in the closed
   phase vocabulary, which is read from the manifest the run actually loaded.
4. A ``Phase`` value never holds more than one value (no comma).
5. A ``Phase`` value never repeats a ``Status`` value.
6. A ``Phase`` value is never empty on a row whose ``Status`` still needs a phase home (every
   status except ``done``, whose evidence is a PR reference rather than a future phase).
7. Ids are unique across the whole register, not just within one cluster.
8. Every column name in a cluster's header row is one of the closed set of known register
   columns (ID, Item, Issues, Issue, Theme, Source, ADR, Owner, Phase, Status). Before this
   check, only the four columns the row checks read were ever looked at, so a cluster whose
   header carried a typo'd or invented column name shipped an unchecked column and nobody was
   told.
9. Where an ``Issue`` or ``Issues`` column exists (clusters L and D), each cell is either the
   literal ``(no issue)`` or one or more issue references separated by commas and/or
   whitespace, each a bare ``#N`` or a markdown link to this repository's
   ``issues/N`` or ``pull/N`` URL. Nothing is resolved against GitHub; this is a shape check.
10. No cell in a non-``Phase`` column (Issue, Issues, Source, ADR, Owner, Theme) holds a phase
    token as its whole content, after stripping backticks and whitespace. A phase written in the
    wrong column passes the ``Phase`` check on its own row and then reads as a source or owner
    to every consumer; the exact-token match keeps Item-like prose that merely mentions a phase
    word out of scope.

Vocabulary drift: ``docs/planning/plan-manifest.toml`` (the "plan manifest") is the source of
truth for the phase vocabulary, the phase-to-rung mapping, the two-axis (``shipped``/``usable``)
status model, and every id namespace's regex (``[namespaces.*]``); ``roadmap.md`` is checked
against it, not the other way around. No id pattern is written twice: this module holds none,
and the regexes quoted below are descriptions of what the manifest currently declares, not a
second copy the code reads. This
script parses ``## Phase`` headings (and the ``2b``/``4a``/``4b`` sub-headings that do not follow
that exact shape) out of ``roadmap.md`` and fails if the manifest's track-1 phase set disagrees
with what the roadmap actually contains, so a new phase added to the roadmap without a matching
manifest entry is caught here rather than discovered later. Two further checks guard the manifest
and the roadmap's prose against each other:

* ``_check_manifest_integrity``: the manifest is structurally present (the ``[phases]``,
  ``[rungs]``, and ``[namespaces]`` tables exist, are tables, and are non-empty, and the
  ``R1``/``R2``/``R3`` rungs are declared) and then internally consistent (the declared id
  namespaces match the closed set this module consumes and each one's ``source`` resolves to a
  real file, every rung's phase references exist, ``requires_phases``/``excludes_phases`` are
  disjoint, the rungs are monotonic, every phase's status pair has a matching
  ``[status_vocabulary]`` entry, and Phase 7 does not gate R2). The structural precondition runs
  first and short-circuits the rest: a manifest missing ``[rungs]`` entirely would otherwise
  pass every one of those seven checks vacuously.
* ``_check_roadmap_phase_status``: the roadmap's phase-status table prose (for example
  "Substantially delivered") matches the term the manifest's ``[status_vocabulary]`` derives from
  that phase's ``(shipped, usable)`` pair, and its leading glyph matches that phase's ``shipped``
  axis. A roadmap that carries tables but no locatable phase-status header is reported rather
  than skipped, since a renamed header would otherwise drop every checked row and still pass.

The manifest named on the command line is the only one a run consults. The register's own
``Phase`` cell vocabulary and every id pattern are derived from it and threaded down to the row
checks, so a ``--manifest`` run cannot end up validating the register against one manifest and
the roadmap against another. An unloadable manifest is reported and then stops the run: with no
phase vocabulary and no id patterns, every remaining check would reject every row it saw, and
several hundred lines of "malformed id" would bury the one line naming the actual cause.

Cross-register linkage:

1. Every row in ``r1-deferred-debt-register.md`` whose first cell matches ``[namespaces.debt]``
   (``C``, ``GS``, ``U``, ``T``, ``P``, or ``SL`` followed by digits, as the manifest declares
   it) and which is not marked ``[Closed]`` or ``[Resolved]`` (the register uses both markers
   interchangeably) must be cited somewhere in cluster B of the unscheduled register.
2. Every lesson in ``authoring-lessons-log.md`` whose ``Status`` is not ``applied``, ``rejected``,
   or ``superseded`` must be cited somewhere in cluster C of the unscheduled register.
3. Every row in ``capability-register.md`` (four tables: K, G, A, S) whose ``Docs`` cell is not
   the done checkmark must appear in ``roadmap.md``'s "Where every open register item lands"
   mapping section.

Every check reads local files only. Two GitHub-facing checks once lived here behind
``--check-issues`` and ``--check-issue-orphans`` flags; they were removed because tying every
open issue to the phase plan cost more upkeep than it returned, and because a checker that
needs network access and ``gh`` auth cannot run identically in the pre-commit hook and in CI.
An ``issue:NNN`` Phase value remains valid vocabulary; nothing resolves it against GitHub.

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
# Holds the SQ-to-register map (section 11) that registers the SQ-* namespace's ids.
_DEFAULT_STORY_STRUCTURE_PLAN = (
    _REPO_ROOT / "docs" / "planning" / "story-structure-improvement-plan.md"
)

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
_MANIFEST_REQUIRED_TABLES = ("phases", "rungs", "namespaces")
_MANIFEST_REQUIRED_RUNGS = ("R1", "R2", "R3")

# The closed set of id namespaces this checker consumes, and the fields it requires of each.
# Moving the patterns into the manifest made them data, which removed them from every tool
# that reads Python: nothing reports an unread TOML key, so without this contract a namespace
# table with a typo'd name is silently inert and a `prefix`/`source` field can rot unnoticed
# because no code path ever reads it. Declaring the contract here and checking the manifest
# against it in both directions restores the "wrong name is an error" property the module-level
# constants had for free.
#
# `citation_pattern` is deliberately per-namespace rather than universal: uw and sq ids are
# validated only inside their own document and are never cited from another, so requiring the
# field would force a pattern that nothing runs.
# Every `citation_pattern` must refuse to match a fragment of a longer id, at BOTH ends. `\b` does
# not do this at either end, because a hyphen IS a word boundary:
#
#   left  `\b[KGAS]\d+\b` matched `K16` inside `UW-K16`, so capability K16's only apparent citation
#         in roadmap.md was a fragment of an unscheduled-work id. Measured before the guard
#         existed: 18 phantom capability ids in roadmap.md and 25 phantom debt ids in the register,
#         every one a fragment of a longer `UW-*` id.
#   right the same `\b` is satisfied by a digit-to-hyphen transition, so the debt pattern read `P9`
#         out of `P9-05` in cluster B of the unscheduled-work register. `P9-05` is PROJECT-PLAN.md's
#         `<letter><phase>-<item>` task numbering, unrelated to the debt namespace's `P1`-`P4`.
#
# Guarding one end and not the other leaves the same defect class live, mirrored. Measured over the
# three texts the citation checks actually scan, adding the right guard removes exactly one id, the
# phantom `P9`, and loses no real citation: pure-digit truncation (`C123` -> `C12`) was never
# possible, since `\d+` is greedy and backtracking cannot manufacture a boundary between digits.
#
# The guards belong in the pattern, not in the ids. Renaming `A1` to `CI-A1` does not help, because
# `\b` matches the `A1` inside the renamed form just as happily; that rename was tried and measured
# to have changed nothing.
_CITATION_LEFT_GUARD = r"(?<![-\w])"
_CITATION_RIGHT_GUARD = r"(?![-\w])"

_NAMESPACE_REGISTRY_CONTRACT: dict[str, tuple[str, ...]] = {
    "uw": ("prefix", "source", "pattern"),
    "debt": ("prefix", "source", "pattern", "citation_pattern"),
    "al": ("prefix", "source", "pattern", "citation_pattern"),
    "cap": ("prefix", "source", "pattern", "citation_pattern"),
    "sq": ("prefix", "source", "pattern"),
}


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


# A sentinel pattern that matches nothing, used as the fail-closed return value of
# ``_manifest_namespace_pattern`` when a namespace cannot be resolved. `(?!)` is a negative
# lookahead on nothing, which never succeeds, so `.match()` against any string is always None.
# This keeps every namespace-pattern caller Optional-free: they always get a real
# ``re.Pattern``, and an unresolvable namespace rejects every id rather than needing its own
# None-handling branch at every call site.
_NEVER_MATCHES_RE = re.compile(r"(?!)")

# Bounds on a manifest-supplied regex, checked before it is compiled or run.
#
# #CRITICAL: external resources: `[namespaces.*].pattern` and `.citation_pattern` are compiled
# from a planning document and then run against whole cluster bodies of a ~75KB register, so a
# pattern with nested quantifiers (`([\w ]+)+Q`) backtracks catastrophically. Python's `re` has
# no timeout, and this script runs both in CI (bounded only by the job's 10-minute cap) and in
# the `check-work-linkage` pre-commit hook (bounded by nothing at all), so an unbounded pattern
# wedges every local commit with no diagnostic. This mirrors the reasoning behind
# `_GH_ISSUE_LIST_TIMEOUT_SECONDS` below: an unbounded external input becomes a reported
# problem rather than a hang.
# #VERIFY: both bounds below reject before `re.compile` runs, and the rejection is appended to
# `problems` so the run fails loudly with the offending pattern named. The nested-quantifier
# check is a conservative heuristic, not a proof of safety: it catches the `(X+)+` shape that
# causes exponential backtracking and is verified to accept every pattern the manifest ships.
# A pattern that is pathological in some other way remains possible, so keep this paired with
# the length bound rather than relying on either alone.
_MAX_NAMESPACE_PATTERN_LENGTH = 200
_NESTED_QUANTIFIER_RE = re.compile(r"\([^()]*[+*][^()]*\)\s*[+*{]")


def _manifest_namespace_pattern(
    manifest: dict[str, Any] | None,
    manifest_path: Path,
    namespace: str,
    field: str,
    problems: list[str],
) -> re.Pattern[str]:
    """Return one compiled regex from the manifest's ``[namespaces.<namespace>]`` table.

    Mirrors ``_manifest_phase_vocabulary``'s fail-closed shape, but unlike that function this
    one reports its own failures: a namespace's id pattern has no other check standing behind
    it the way the phase-vocabulary check backstops an empty phase set, so a silent
    ``_NEVER_MATCHES_RE`` here would surface only as every row in that namespace being reported
    "malformed", with no problem naming the actual root cause (the manifest not declaring the
    namespace). The one exception is ``manifest is None``: that failure was already reported by
    ``_load_manifest`` itself, so this does not report it a second time.

    Args:
        manifest: The parsed plan-manifest.toml document, or None when it could not be loaded.
        manifest_path: The manifest's path, for message text.
        namespace: The ``[namespaces.<namespace>]`` table key (for example ``"uw"``, ``"debt"``,
            ``"sq"``).
        field: The field to compile, ``"pattern"`` or ``"citation_pattern"``.
        problems: The running problem list; a missing namespace, missing field, or invalid
            regex is appended here.

    Returns:
        re.Pattern[str]: The compiled regex, or ``_NEVER_MATCHES_RE`` when the namespace or
            field could not be resolved.
    """
    if manifest is None:
        return _NEVER_MATCHES_RE
    namespaces = manifest.get("namespaces", {})
    if not isinstance(namespaces, dict):
        problems.append(
            f"{manifest_path.name}: [namespaces] is {type(namespaces).__name__}, not a table"
        )
        return _NEVER_MATCHES_RE
    entry = namespaces.get(namespace)
    if not isinstance(entry, dict):
        problems.append(
            f"{manifest_path.name}: [namespaces.{namespace}] is missing or not a table; the "
            f"'{namespace}' id namespace cannot be validated without it"
        )
        return _NEVER_MATCHES_RE
    raw_pattern = entry.get(field)
    # .strip() and not just falsiness: `pattern = "  "` compiles to a regex that matches at
    # every position, so a whitespace-only field is the fail-open case, not a stylistic one.
    if not isinstance(raw_pattern, str) or not raw_pattern.strip():
        problems.append(
            f"{manifest_path.name}: [namespaces.{namespace}].{field} is missing or empty"
        )
        return _NEVER_MATCHES_RE
    if len(raw_pattern) > _MAX_NAMESPACE_PATTERN_LENGTH:
        problems.append(
            f"{manifest_path.name}: [namespaces.{namespace}].{field} is "
            f"{len(raw_pattern)} characters, over the {_MAX_NAMESPACE_PATTERN_LENGTH}-"
            f"character bound; an id pattern this long is not an id pattern"
        )
        return _NEVER_MATCHES_RE
    if _NESTED_QUANTIFIER_RE.search(raw_pattern):
        problems.append(
            f"{manifest_path.name}: [namespaces.{namespace}].{field} '{raw_pattern}' nests a "
            f"quantifier inside a quantified group, which backtracks catastrophically against "
            f"the register text this pattern is run over; rewrite it without the nesting"
        )
        return _NEVER_MATCHES_RE
    try:
        return re.compile(raw_pattern)
    except re.error as exc:
        problems.append(
            f"{manifest_path.name}: [namespaces.{namespace}].{field} '{raw_pattern}' is not "
            f"a valid regex: {exc}"
        )
        return _NEVER_MATCHES_RE


_RELEASE_RUNGS = frozenset({"R1", "R2", "R3"})
_NAMED_WORKSTREAMS = frozenset({"content", "now"})
_SENTINELS_EXACT = frozenset({"CI hygiene", "doc", "recurring", "post-launch"})
_MILESTONE_RE = re.compile(r"^M[0-7](\.\d+)?$")
_EXTERNAL_RE = re.compile(r"^external:.+$")
_ISSUE_RE = re.compile(r"^issue:\d+$")

_CLUSTER_HEADING_RE = re.compile(r"^## Cluster ([A-N]):")

# The closed set of column names a cluster table header may carry. Six of the register's header
# schemas carry a column other than ID/Item/Phase/Status, and until this set existed those
# columns were never named anywhere in the checker, so a header could gain a misspelled or
# invented column and the run stayed green with that column unvalidated.
_KNOWN_REGISTER_COLUMNS = frozenset(
    {
        "ID",
        "Item",
        "Issues",
        "Issue",
        "Theme",
        "Source",
        "ADR",
        "Owner",
        "Phase",
        "Status",
    }
)
# The two column names whose cells hold GitHub issue references (cluster D uses the plural,
# cluster L the singular).
_ISSUE_COLUMNS = frozenset({"Issues", "Issue"})
# Columns whose whole-cell content must never be a phase token. ``Item`` is deliberately absent:
# it is free prose and the exact-token match below would still be correct on it, but a one-word
# Item is not a shape this register uses and the check's purpose is the third-column slot.
_PHASE_FORBIDDEN_COLUMNS = frozenset(
    {"Issues", "Issue", "Source", "ADR", "Owner", "Theme"}
)
# The literal an Issue/Issues cell carries when a row has no GitHub issue behind it.
_NO_ISSUE_SENTINEL = "(no issue)"
# One issue reference: a bare ``#N`` or a markdown link to this repository's issue or pull URL.
# The link text is any non-empty run without a closing bracket, so ``[#558](...)`` and a
# worded link both pass; the URL path is fixed to this repository so a link to some other
# tracker cannot masquerade as an issue reference.
_ISSUE_REFERENCE_PATTERN = (
    r"(?:#\d+|\[[^\]]+\]\(https://github\.com/ByronWilliamsCPA/cyo-adventure/"
    r"(?:issues|pull)/\d+\))"
)
# A whole Issue/Issues cell: one reference, then zero or more further references each preceded
# by a comma and/or whitespace run. Anchored on both ends so a stray word fails the cell.
_ISSUE_CELL_RE = re.compile(
    rf"^{_ISSUE_REFERENCE_PATTERN}(?:[\s,]+{_ISSUE_REFERENCE_PATTERN})*$"
)

# Debt, AL, and capability id row/citation patterns used to live here as hardcoded module-level
# constants (_DEBT_ROW_ID_RE, _DEBT_ID_RE, _AL_ROW_ID_RE, _AL_ID_RE, _CAP_ROW_ID_RE, _CAP_ID_RE).
# They are now resolved from plan-manifest.toml's [namespaces.debt/al/cap] tables via
# ``_manifest_namespace_pattern`` and threaded through the functions that need them, alongside
# the uw and sq namespaces, so a namespace's shape lives in exactly one place.

_AL_CLOSED_STATUSES = frozenset({"applied", "rejected", "superseded"})

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

# The mapping section roadmap.md's linkage contract points at for capability-register linkage.
_ROADMAP_MAPPING_HEADING = "### Where every open register item lands"

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
# module scope rather than per call, since _split_row runs on every line of the six markdown
# documents this script reads (register, roadmap, debt register, lessons log, capability
# register, story-structure plan) plus an rglob sweep of the whole planning tree.
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


def _check_row_id(
    cluster: str, number: int, entry_id: str, id_pattern: re.Pattern[str]
) -> list[str]:
    """Return problems if a register row's id is malformed or filed under the wrong cluster.

    Args:
        cluster: The cluster letter the row belongs to (the table it was found in), for the
            message and the cluster-match check.
        number: The row's 1-based line number.
        entry_id: The row's ``ID`` cell value.
        id_pattern: The ``[namespaces.uw].pattern`` regex the id must fully match, resolved
            from the run's manifest. It should expose the cluster letter as a named
            ``(?P<cluster>...)`` group; see the cluster-letter note in the body.

    Returns:
        list[str]: Problems found; empty when the id is well formed and its letter matches the
            cluster it was found in.
    """
    match = id_pattern.match(entry_id)
    if match is None:
        # Quote the pattern rather than naming a shape. The literal "UW-[A-M]NN" used to be
        # written here, which silently became a lie the moment the shape moved into the
        # manifest: a reader who widened [namespaces.uw].pattern would be told their id failed
        # to match a rule the run was no longer applying.
        return [
            (
                f"cluster {cluster} line {number}: id '{entry_id}' does not match the uw "
                f"namespace pattern '{id_pattern.pattern}'"
            )
        ]
    # The cluster letter comes from the pattern's named group, not from a fixed offset into the
    # id. `entry_id[3]` used to be read directly, which re-hardcoded the very layout the
    # manifest now owns and raised IndexError (an uncaught crash, not a reported problem) for
    # any id shorter than four characters that a widened pattern let through.
    id_letter = match.groupdict().get("cluster")
    if id_letter is None:
        return [
            (
                f"cluster {cluster} line {number}: the uw namespace pattern "
                f"'{id_pattern.pattern}' has no '(?P<cluster>...)' group, so the cluster letter "
                f"in id '{entry_id}' cannot be checked against the table it was found in"
            )
        ]
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


def _check_cluster_header(letter: str, header_cells: list[str]) -> list[str]:
    """Return a problem per header column outside the closed set of known register columns.

    Args:
        letter: The cluster letter, for message text.
        header_cells: The cluster table's header cells.

    Returns:
        list[str]: One problem per unknown column name, in header order; empty when every
            column is known.
    """
    header = "| " + " | ".join(header_cells) + " |"
    known = ", ".join(sorted(_KNOWN_REGISTER_COLUMNS))
    return [
        (
            f"cluster {letter} header '{header}': column '{column}' is not one of the known "
            f"register columns: {known}"
        )
        for column in header_cells
        if column not in _KNOWN_REGISTER_COLUMNS
    ]


def _check_row_issue_cell(
    cluster: str, number: int, entry_id: str, column: str, cell: str
) -> list[str]:
    """Return a problem if an ``Issue``/``Issues`` cell is not a well-formed reference list.

    A cell is accepted when it is exactly ``(no issue)``, or when it is one or more references
    separated by commas and/or whitespace, each either ``#N`` or a markdown link whose target
    is this repository's ``issues/N`` or ``pull/N`` URL. The check is offline: it validates
    the shape of the reference, never whether the issue exists.

    Args:
        cluster: The cluster letter the row belongs to, for the message.
        number: The row's 1-based line number.
        entry_id: The row's ``ID`` cell value, for the message.
        column: The column name (``Issue`` or ``Issues``), for the message.
        cell: The cell's already-trimmed value.

    Returns:
        list[str]: One problem, or an empty list when the cell is well formed.
    """
    if cell == _NO_ISSUE_SENTINEL or _ISSUE_CELL_RE.match(cell):
        return []
    return [
        (
            f"{entry_id} (cluster {cluster} line {number}): {column} '{cell}' is neither "
            f"'{_NO_ISSUE_SENTINEL}' nor a list of issue references (each '#N' or a markdown "
            f"link to https://github.com/ByronWilliamsCPA/cyo-adventure/issues/N or /pull/N, "
            f"separated by commas or whitespace)"
        )
    ]


def _check_row_non_phase_cell(
    cluster: str,
    number: int,
    entry_id: str,
    column: str,
    cell: str,
    phase_vocabulary: frozenset[str],
) -> list[str]:
    """Return a problem if a non-``Phase`` column's whole cell is a phase-vocabulary token.

    The cell is stripped of backticks and surrounding whitespace and then compared as an exact
    token against everything ``_phase_in_vocabulary`` accepts, so a backtick-quoted ``5`` in a
    ``Source`` column is caught while a sentence that merely mentions a phase word is not.

    Args:
        cluster: The cluster letter the row belongs to, for the message.
        number: The row's 1-based line number.
        entry_id: The row's ``ID`` cell value, for the message.
        column: The column name the cell was found in, for the message.
        cell: The cell's already-trimmed value.
        phase_vocabulary: Every phase token the run's manifest declares.

    Returns:
        list[str]: One problem, or an empty list when the cell is not a bare phase token.
    """
    token = cell.strip().strip("`").strip()
    if not token or not _phase_in_vocabulary(token, phase_vocabulary):
        return []
    return [
        (
            f"{entry_id} (cluster {cluster} line {number}): {column} '{cell}' is a phase "
            f"token; a phase belongs in the Phase column, not in {column}"
        )
    ]


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


def _debt_register_open_ids(
    lines: list[str], id_pattern: re.Pattern[str]
) -> dict[str, int]:
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
        id_pattern: The ``[namespaces.debt].pattern`` regex a row's whole first cell must match.

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
        if not cells or not id_pattern.match(cells[0]):
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


def _is_open_lesson_row(
    cells: list[str], status_idx: int, id_pattern: re.Pattern[str]
) -> bool:
    """Report whether a split row is a lesson row still needing cross-register citation.

    Args:
        cells: A row's split cell values.
        status_idx: The lessons log header's ``Status`` column index.
        id_pattern: The ``[namespaces.al].pattern`` regex a row's whole first cell must match.

    Returns:
        bool: True when the row's id matches the lesson id shape, it has a ``Status`` cell, and
            that cell is not one of the closed statuses.
    """
    if not cells or _is_separator(cells) or not id_pattern.match(cells[0]):
        return False
    if len(cells) <= status_idx:
        return False
    return cells[status_idx] not in _AL_CLOSED_STATUSES


def _lessons_needing_citation(
    lines: list[str], id_pattern: re.Pattern[str]
) -> dict[str, int]:
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
        id_pattern: The ``[namespaces.al].pattern`` regex, threaded down to
            ``_is_open_lesson_row``.

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
        if _is_open_lesson_row(cells, status_idx, id_pattern):
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
    id_pattern: re.Pattern[str],
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
        id_pattern: The ``[namespaces.cap].pattern`` regex a row's whole first cell must match.

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
        if _is_separator(cells) or not id_pattern.match(cells[0]):
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


def _capability_register_open_ids(
    lines: list[str], id_pattern: re.Pattern[str]
) -> dict[str, int]:
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
        id_pattern: The ``[namespaces.cap].pattern`` regex, threaded down to
            ``_capability_register_status_rows``.

    Returns:
        dict[str, int]: Open (not done) capability ids mapped to the line they were found on.

    Raises:
        LookupError: See ``_capability_register_status_rows``, which this delegates the walk to.
        ValueError: See ``_capability_register_status_rows``.
    """
    return {
        entry_id: number
        for number, entry_id, docs_val, _notes_val in _capability_register_status_rows(
            lines, id_pattern
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
    id_pattern: re.Pattern[str],
) -> tuple[list[str], dict[str, str]]:
    """Run every row-level check across all cluster tables, plus the register-wide id check.

    Args:
        clusters: Cluster letter mapped to its header cells and data rows, as returned by
            ``_find_clusters``.
        phase_vocabulary: Every phase token the run's manifest declares, threaded down to
            ``_check_row_phase``.
        id_pattern: The ``[namespaces.uw].pattern`` regex, threaded down to ``_check_row_id``.

    Returns:
        tuple[list[str], dict[str, str]]: The problems found, and each cluster letter mapped to
            its joined ``Item`` column text, for the cross-register citation checks that follow.
    """
    problems: list[str] = []
    all_ids: dict[str, list[int]] = {}
    cluster_item_text: dict[str, str] = {}

    for letter, (header_cells, rows) in sorted(clusters.items()):
        row_problems, item_texts, row_ids = _check_cluster_rows(
            letter, header_cells, rows, phase_vocabulary, id_pattern
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
    """Resolve every known register column's index from a header row.

    Args:
        header_cells: A cluster table's header cells.

    Returns:
        dict[str, int | None]: Each name in ``_KNOWN_REGISTER_COLUMNS`` mapped to its 0-based
            index, or None when that cluster's table has no such column (clusters L and M have
            no ``Phase``; only D has ``Issues``, only L has ``Issue``, and so on). A column
            name the header carries but the closed set does not know is not resolved here; it
            is reported by ``_check_cluster_header``.
    """
    return {
        name: header_cells.index(name) if name in header_cells else None
        for name in _KNOWN_REGISTER_COLUMNS
    }


def _check_one_row(
    letter: str,
    number: int,
    cells: list[str],
    indexes: dict[str, int | None],
    phase_vocabulary: frozenset[str],
    id_pattern: re.Pattern[str],
) -> tuple[list[str], str | None, str]:
    """Run the id, status, phase, issue-cell, and non-phase-cell checks on one cluster row.

    The row has already been length-checked against its header. The issue-cell and
    non-phase-cell checks only fire for columns the header actually carries, so a cluster with
    the plain ``ID | Item | Phase | Status`` shape runs exactly the checks it always did.

    Args:
        letter: The cluster letter, for message text.
        number: The row's 1-based line number.
        cells: The row's cell values, already confirmed to match the header's column count.
        indexes: The header's resolved column indexes, as returned by
            ``_resolve_column_indexes``.
        phase_vocabulary: Every phase token the run's manifest declares.
        id_pattern: The ``[namespaces.uw].pattern`` regex, threaded down to ``_check_row_id``.

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
    problems.extend(_check_row_id(letter, number, entry_id, id_pattern))

    status = cells[status_idx] if status_idx is not None else ""
    if status_idx is not None:
        problems.extend(_check_row_status(letter, number, entry_id, status))

    if phase_idx is not None:
        problems.extend(
            _check_row_phase(
                letter, number, entry_id, cells[phase_idx], status, phase_vocabulary
            )
        )

    for column in sorted(_PHASE_FORBIDDEN_COLUMNS):
        column_idx = indexes[column]
        if column_idx is None:
            continue
        cell = cells[column_idx]
        if column in _ISSUE_COLUMNS:
            problems.extend(
                _check_row_issue_cell(letter, number, entry_id, column, cell)
            )
        problems.extend(
            _check_row_non_phase_cell(
                letter, number, entry_id, column, cell, phase_vocabulary
            )
        )

    item_text = cells[item_idx] if item_idx is not None else None

    return problems, item_text, entry_id


def _check_cluster_rows(
    letter: str,
    header_cells: list[str],
    rows: list[tuple[int, list[str]]],
    phase_vocabulary: frozenset[str],
    id_pattern: re.Pattern[str],
) -> tuple[list[str], list[str], list[tuple[str, int]]]:
    """Check one cluster table's header columns, then run the row checks on its data rows.

    The header is checked against the closed set of known column names first, so an invented
    column is reported by name rather than silently going unvalidated; the row checks still run
    on the columns the header does declare correctly.

    A row whose column count disagrees with its header is reported and then skipped for the
    per-cell checks, but its id is still collected first: the register-wide uniqueness check runs
    on the collected ids, so skipping the row before collecting let a duplicate id hide behind a
    malformed row, escaping the uniqueness check entirely rather than being reported twice.

    Args:
        letter: The cluster letter, for message text and the returned id list.
        header_cells: The cluster table's header cells, used to resolve column indexes.
        rows: The cluster's (1-based line number, cells) data rows.
        phase_vocabulary: Every phase token the run's manifest declares.
        id_pattern: The ``[namespaces.uw].pattern`` regex, threaded down to ``_check_one_row``.

    Returns:
        tuple[list[str], list[str], list[tuple[str, int]]]: The problems found, the ``Item``
            column text of every row (for later citation checks), and each row's (id, line
            number) pair (for the register-wide id-uniqueness check).
    """
    indexes = _resolve_column_indexes(header_cells)
    id_idx = indexes["ID"]

    problems: list[str] = _check_cluster_header(letter, header_cells)
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
            letter, number, cells, indexes, phase_vocabulary, id_pattern
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


def _check_namespace_registry(
    manifest: dict[str, Any], manifest_path: Path
) -> list[str]:
    """Check the declared id namespaces match the closed set this checker consumes.

    Moving the id patterns out of Python and into ``[namespaces]`` traded one failure mode for
    another. As module constants a typo'd name was a ``NameError`` at import; as TOML keys a
    typo'd name is just an unread table, and the namespace it was supposed to define resolves
    to the fail-closed sentinel at the one call site that asks for it. This compares the two
    directions explicitly so neither a missing table nor a stray one can sit unnoticed.

    It also gives ``prefix`` and ``source`` a reader. Both were pure documentation: no code
    path touched them, so nothing detected a renamed register or an emptied field. Resolving
    ``source`` against the repo root turns a moved document into a reported problem instead of
    a comment that quietly stops being true.

    It also enforces `_CITATION_LEFT_GUARD` and `_CITATION_RIGHT_GUARD` on every declared
    ``citation_pattern``. Putting the patterns in the manifest made a latent defect into a
    declared contract: the shipped capability and debt citation patterns were word-bounded only,
    so they read ids out of the middle of longer ids from other namespaces. Both ends are required
    because a hyphen is a word boundary on either side, which makes that class unrepresentable
    rather than fixed once at whichever end happened to be noticed first.

    Args:
        manifest: The parsed plan-manifest.toml document.
        manifest_path: The manifest's path, for message text.

    Returns:
        list[str]: One problem per undeclared, unexpected, incomplete, unresolvable, or
            insufficiently guarded namespace entry; empty when the registry matches the
            contract exactly.
    """
    # #CRITICAL: data integrity: a namespace the checker consumes but the manifest does not
    # declare resolves to _NEVER_MATCHES_RE, which matches no id at all. Every row in that
    # namespace then fails, or (where the pattern gates a search rather than a match) every
    # citation check for it silently finds nothing.
    # #VERIFY: this runs inside _check_manifest_integrity, whose problems are surfaced by
    # check_linkage before any namespace-dependent check consumes a pattern.
    problems: list[str] = []
    namespaces = manifest.get("namespaces")
    if not isinstance(namespaces, dict):
        # _check_manifest_structure already reported this and short-circuits before we run;
        # the guard exists so this function is safe to call on its own in a test.
        return problems

    declared = set(namespaces)
    expected = set(_NAMESPACE_REGISTRY_CONTRACT)
    problems.extend(
        (
            f"{manifest_path.name}: [namespaces.{name}] is missing; check_work_linkage.py reads "
            f"this namespace, and an undeclared one resolves to a pattern that matches nothing"
        )
        for name in sorted(expected - declared)
    )
    problems.extend(
        (
            f"{manifest_path.name}: [namespaces.{name}] is declared but no code reads it; add it "
            f"to _NAMESPACE_REGISTRY_CONTRACT or remove the table, because an unread namespace "
            f"looks enforced and is not"
        )
        for name in sorted(declared - expected)
    )

    for name in sorted(expected & declared):
        entry = namespaces[name]
        if not isinstance(entry, dict):
            problems.append(
                f"{manifest_path.name}: [namespaces.{name}] is {type(entry).__name__}, not a "
                f"table"
            )
            continue
        required = _NAMESPACE_REGISTRY_CONTRACT[name]
        for field in required:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(
                    f"{manifest_path.name}: [namespaces.{name}] field '{field}' is missing or "
                    f"empty; it is required for this namespace"
                )
        problems.extend(
            (
                f"{manifest_path.name}: [namespaces.{name}] has unrecognised field '{field}'; "
                f"nothing reads it, so a typo'd field name would otherwise disable the check it "
                f"was meant to configure"
            )
            for field in sorted(set(entry) - set(required))
        )
        # An absent or blank citation_pattern is already reported by the required-field loop
        # above; re-reporting it here as an unguarded pattern would name a second cause for
        # one defect and send the reader looking for a regex that does not exist.
        citation = entry.get("citation_pattern")
        if isinstance(citation, str) and citation.strip():
            problems.extend(
                (
                    f"{manifest_path.name}: [namespaces.{name}] citation_pattern must "
                    f"{position} with the guard {guard} so it cannot match a fragment of a "
                    f"longer id. A '\\b' there is not enough: a hyphen is a word boundary, so "
                    f"such a pattern reads a {name}-namespace id out of a longer id that "
                    f"merely contains one, the way '\\b[KGAS]\\d+\\b' read 'K16' out of "
                    f"'UW-K16' and '(?:P\\d+)\\b' read 'P9' out of 'P9-05'"
                )
                for position, guard, satisfied in (
                    ("start", _CITATION_LEFT_GUARD, citation.startswith),
                    ("end", _CITATION_RIGHT_GUARD, citation.endswith),
                )
                if not satisfied(guard)
            )
        source = entry.get("source")
        if isinstance(source, str) and source.strip():
            if (_REPO_ROOT / source).is_file():
                continue
            problems.append(
                f"{manifest_path.name}: [namespaces.{name}] source '{source}' does not resolve "
                f"to a file under the repository root"
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
    the manifest can be validated against without reference to any other document: the declared
    id namespaces match the closed set the checker consumes, rung phase references resolve,
    requires/excludes never overlap, the release ladder is monotonic, every phase's status pair
    has a vocabulary term, every status value is in the closed vocabulary, and Phase 7 does not
    gate R2.

    The precondition short-circuits deliberately. Each of the seven consistency checks iterates a
    table it fetches with a ``{}`` default, so on a manifest missing that table it reports
    nothing; running them anyway would bury the one real finding under seven false all-clears.

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
    problems.extend(_check_namespace_registry(manifest, manifest_path))
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
    id_pattern: re.Pattern[str],
    citation_pattern: re.Pattern[str],
) -> list[str]:
    """Check every open debt-register id is cited in cluster B of the unscheduled register.

    Args:
        debt_lines: The R1 deferred-debt register's lines.
        debt_register_path: The debt register's path, for message text.
        register_path: The unscheduled-work register's path, for message text.
        cluster_b_text: Cluster B's joined ``Item`` column text.
        id_pattern: The ``[namespaces.debt].pattern`` regex, threaded down to
            ``_debt_register_open_ids``.
        citation_pattern: The ``[namespaces.debt].citation_pattern`` regex, used to find debt-id
            mentions in cluster B's prose.

    Returns:
        list[str]: One problem per uncited open debt id.
    """
    problems: list[str] = []
    open_debt_ids = _debt_register_open_ids(debt_lines, id_pattern)
    cited_debt_ids = _extract_citations(cluster_b_text, citation_pattern)
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
    id_pattern: re.Pattern[str],
    citation_pattern: re.Pattern[str],
) -> list[str]:
    """Check every lesson still needing linkage is cited in cluster C of the unscheduled register.

    Args:
        lessons_lines: The authoring lessons log's lines.
        lessons_log_path: The lessons log's path, for message text.
        register_path: The unscheduled-work register's path, for message text.
        cluster_c_text: Cluster C's joined ``Item`` column text.
        id_pattern: The ``[namespaces.al].pattern`` regex, threaded down to
            ``_lessons_needing_citation``.
        citation_pattern: The ``[namespaces.al].citation_pattern`` regex, used to find lesson-id
            mentions in cluster C's prose.

    Returns:
        list[str]: One problem per uncited open lesson id.
    """
    problems: list[str] = []
    open_lesson_ids = _lessons_needing_citation(lessons_lines, id_pattern)
    cited_lesson_ids = _extract_citations(cluster_c_text, citation_pattern)
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
    id_pattern: re.Pattern[str],
    citation_pattern: re.Pattern[str],
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
        id_pattern: The ``[namespaces.cap].pattern`` regex, threaded down to
            ``_capability_register_open_ids``.
        citation_pattern: The ``[namespaces.cap].citation_pattern`` regex, used to find
            capability-id mentions in the roadmap mapping section.

    Returns:
        list[str]: One problem per open capability id missing from the mapping section.
    """
    problems: list[str] = []
    open_capability_ids = _capability_register_open_ids(capability_lines, id_pattern)
    mapping_text = _extract_roadmap_mapping_section(roadmap_lines)
    cited_capability_ids = _extract_citations(mapping_text, citation_pattern)
    for capability_id, line_number in sorted(open_capability_ids.items()):
        if capability_id not in cited_capability_ids:
            problems.append(
                f"{capability_register_path.name}:{line_number}: capability "
                f"'{capability_id}' is not marked done and does not appear in "
                f'{roadmap_path.name}\'s "Where every open register item lands" mapping'
            )
    return problems


def _find_sq_table_header(lines: list[str]) -> int:
    """Return the SQ-to-register map table's header line index.

    The table's header row repeats the id/source column pair twice on one line (``| SQ |
    Register / source | SQ | Register / source |``), because the source document lays the 24
    rows out two per line rather than one long single-pair table. Matching on the literal column
    labels, not on position, is what lets this survive a reflow of the surrounding prose.

    Only the first such header is returned, unlike ``_find_sq_work_table_headers``, which
    returns every deliverables-table header. That asymmetry is deliberate but narrow: the map
    is one table by contract, where deliverables are split one table per stage. A document that
    grew a second map table would have its rows silently ignored here, which the coverage rule
    would then report as deliverables with "no recorded scheduling home" rather than as the
    split map it actually is. Split the map and this needs to return a list.

    Args:
        lines: The story-structure-improvement-plan.md document's lines.

    Returns:
        int: The 0-based index of the first matching header row.

    Raises:
        LookupError: If no such header row is found.
    """
    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = _split_row(line)
        if len(cells) >= 3 and cells[0] == "SQ" and cells[2] == "SQ":
            return index
    msg = "no 'SQ | Register / source | SQ | Register / source' table header found"
    raise LookupError(msg)


def _sq_table_ids(lines: list[str], header_index: int) -> list[tuple[int, str]]:
    """Return every SQ id in the map table, in both column positions, with line numbers.

    The table separator row directly follows the header; data rows follow until the first line
    that no longer contains a pipe, which the source document uses as the table's end (a blank
    line back into prose).

    Args:
        lines: The story-structure-improvement-plan.md document's lines.
        header_index: The header row's 0-based index, as returned by ``_find_sq_table_header``.

    Returns:
        list[tuple[int, str]]: Each ``(line_number, id)`` pair found in either the first or third
            column, in document order. ``line_number`` is 1-based, matching the rest of this
            module's message text.
    """
    ids: list[tuple[int, str]] = []
    for number, line in enumerate(lines[header_index + 1 :], start=header_index + 2):
        if "|" not in line:
            break
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        if cells and cells[0]:
            ids.append((number, cells[0]))
        if len(cells) > 2 and cells[2]:
            ids.append((number, cells[2]))
    return ids


# A deliverable that belongs to no single stage is written as a bolded cross-cutting paragraph
# lead rather than a stage-table row (SQ-24, the ADR-011 amendment, is the current instance).
# The anchor is deliberately narrow: a looser "any bolded line naming an SQ id" rule would also
# match the value-chain and dependency-chain prose, which cite ids without defining them, and
# would inflate the defined-id set until the coverage check stopped meaning anything. A prose
# deliverable written in some other style is simply not found here, which surfaces as a loud
# "mapped but not defined" problem rather than a silent pass.
_SQ_CROSS_CUTTING_RE = re.compile(r"^\*\*Cross-cutting: (?P<id>SQ-\d+)\b")


def _find_sq_work_table_headers(lines: list[str]) -> list[int]:
    """Return every SQ deliverables table's header line index.

    These are the tables that *define* each SQ item (``| ID | Deliverable | Evidence / register |
    Effort | Acceptance |``), as distinct from the two-pair map table that records where each
    item's scheduling record lives. The source document splits the deliverables across one table
    per stage rather than a single long one, so this collects all of them; taking only the first
    would silently limit the check to stage one. Matching on the first two literal column labels
    keeps this stable against added trailing columns and a reflow of the surrounding prose.

    Args:
        lines: The story-structure-improvement-plan.md document's lines.

    Returns:
        list[int]: Every matching header row's 0-based index, in document order.

    Raises:
        LookupError: If no such header row is found.
    """
    indexes = [
        index
        for index, line in enumerate(lines)
        if "|" in line and _split_row(line)[:2] == ["ID", "Deliverable"]
    ]
    if not indexes:
        msg = "no 'ID | Deliverable | ...' SQ deliverables table header found"
        raise LookupError(msg)
    return indexes


def _sq_work_table_ids(lines: list[str]) -> list[tuple[int, str]]:
    """Return every id in the first column of every SQ deliverables table, with line numbers.

    Args:
        lines: The story-structure-improvement-plan.md document's lines.

    Returns:
        list[tuple[int, str]]: Each ``(line_number, id)`` pair with 1-based line numbers. Not
            in document order: every stage table's rows come first, in table order, and the
            cross-cutting prose deliverables are appended afterwards by a second pass over the
            whole document. Every caller treats this as a set (a coverage difference, a
            duplicate check, or a count), so the order is unspecified rather than sorted; do
            not add a caller that depends on it without sorting first.

    Raises:
        LookupError: If no SQ deliverables table header can be located.
    """
    ids: list[tuple[int, str]] = []
    for header_index in _find_sq_work_table_headers(lines):
        for number, line in enumerate(
            lines[header_index + 1 :], start=header_index + 2
        ):
            if "|" not in line:
                break
            cells = _split_row(line)
            if _is_separator(cells):
                continue
            if cells and cells[0]:
                ids.append((number, cells[0]))
    for number, line in enumerate(lines, start=1):
        match = _SQ_CROSS_CUTTING_RE.match(line)
        if match:
            ids.append((number, match.group("id")))
    return ids


def _check_sq_namespace(
    lines: list[str], path: Path, id_pattern: re.Pattern[str]
) -> list[str]:
    """Validate the SQ-to-register map table's ids against the manifest's sq namespace pattern.

    Unlike the uw/debt/al/cap namespaces, sq ids are never cited from another document, so there
    is no cross-document citation-linkage check here to mirror ``_check_debt_linkage`` or
    ``_check_lessons_linkage``. The linkage this namespace does have is internal, between the
    two tables in this one document: the deliverables table defines each item and the map table
    records where its scheduling record lives. This function enforces that both tables use
    well-formed, unique ids AND that they cover each other exactly.

    That mutual-coverage rule is most of what keeps the check from being hollow, but not all of
    it. Validating the map table alone passes vacuously when the table is emptied:
    ``_find_sq_table_header`` only proves the *header* survived, and a zero-row table yields
    zero problems. Requiring every deliverable to appear in the map (and no map entry to name an
    item that does not exist) means deleting rows from *one* table is reported rather than
    silently accepted.

    Mutual coverage alone does not close the symmetric case. ``deliverables - map`` and
    ``map - deliverables`` are both empty when both sets are populated and consistent AND when
    both sets are empty, so emptying both tables at once passes every coverage rule. The
    non-empty floor below is what distinguishes those two states; the coverage rules cannot.

    #CRITICAL: data integrity: an assurance check that returns no problems when it inspected no
    rows is indistinguishable from one that passed, and this repo has a documented history of
    exactly that failure mode.
    #VERIFY: any future edit here must keep three tests, because the one-table and both-table
    cases fail through different rules: empty the map table's data rows only, empty the
    deliverables tables' data rows only, and empty BOTH at once, each leaving the headers
    intact, and assert a non-empty problem list in all three. A test suite that covers only the
    one-table cases leaves the symmetric case open while appearing to satisfy this marker.

    Args:
        lines: The story-structure-improvement-plan.md document's lines.
        path: The document's path, for message text.
        id_pattern: The ``[namespaces.sq].pattern`` regex every id must match.

    Returns:
        list[str]: One problem per malformed id, per id used on more than one row within a
            table, and per id present in one table but absent from the other.

    Raises:
        LookupError: If either the SQ-to-register map table header or the SQ deliverables table
            header cannot be located.
    """
    problems: list[str] = []
    map_ids = _sq_table_ids(lines, _find_sq_table_header(lines))
    work_ids = _sq_work_table_ids(lines)
    for label, entries in (("map", map_ids), ("deliverables", work_ids)):
        if not entries:
            problems.append(
                f"{path.name}: the SQ {label} table has a header but no data rows; an sq "
                f"namespace with nothing in it cannot be distinguished from one that passed"
            )
    valid: dict[str, set[str]] = {"map": set(), "deliverables": set()}
    for label, entries in (("map", map_ids), ("deliverables", work_ids)):
        seen: dict[str, list[int]] = {}
        for number, entry_id in entries:
            if not id_pattern.match(entry_id):
                problems.append(
                    f"{path.name}:{number}: id '{entry_id}' does not match the sq namespace "
                    f"pattern"
                )
                continue
            seen.setdefault(entry_id, []).append(number)
        for entry_id, numbers in sorted(seen.items()):
            if len(numbers) > 1:
                lines_listed = ", ".join(str(n) for n in numbers)
                problems.append(
                    f"{path.name}: id '{entry_id}' is used on {len(numbers)} rows of the "
                    f"{label} table (lines {lines_listed}); sq ids must be unique"
                )
        valid[label] = set(seen)
    problems.extend(
        f"{path.name}: id '{entry_id}' is defined in the SQ deliverables table but has no row "
        f"in the SQ-to-register map table, so it has no recorded scheduling home"
        for entry_id in sorted(valid["deliverables"] - valid["map"])
    )
    problems.extend(
        f"{path.name}: id '{entry_id}' appears in the SQ-to-register map table but is not "
        f"defined in the SQ deliverables table"
        for entry_id in sorted(valid["map"] - valid["deliverables"])
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
    story_structure_plan_path: Path = _DEFAULT_STORY_STRUCTURE_PLAN,
) -> list[str]:
    """Validate the work-linkage contract across all six planning documents plus the manifest.

    Args:
        register_path: The unscheduled-work register markdown file.
        roadmap_path: ``roadmap.md``, checked against the manifest's phase vocabulary and status
            vocabulary, and the home of the capability-register mapping section.
        debt_register_path: The R1 deferred-debt register markdown file.
        lessons_log_path: The authoring lessons log markdown file.
        capability_register_path: The capability register markdown file.
        manifest_path: ``plan-manifest.toml``, the phase vocabulary, phase-to-rung mapping,
            two-axis status model, and id-namespace patterns' source of truth. Keyword-only with
            a default so existing callers passing five positional arguments keep working
            unchanged. Every check in this run, including the register's own ``Phase`` cell
            vocabulary and every id namespace's pattern, reads from this one file: a run cannot
            validate one document against this manifest and another against a different one.
        project_plan_path: ``PROJECT-PLAN.md``, which narrates the track-2 phases (6-9) that
            ``roadmap.md`` explicitly does not cover. Their manifest status is drift-checked
            against this document because there is no roadmap row to check it against.
        story_structure_plan_path: ``story-structure-improvement-plan.md``, home of the
            SQ-to-register map table checked against the manifest's ``sq`` namespace.

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

    # Loaded before the register rows are checked, because the phase vocabulary and every id
    # namespace pattern those rows are validated against come from this manifest and no other.
    # Reading it from a module-level default instead is what let a --manifest run validate Phase
    # cells against one manifest and everything else against another.
    manifest = _load_manifest(manifest_path, problems)
    if manifest is None:
        # Every downstream check is parameterised by this manifest: the phase vocabulary is
        # empty and every namespace pattern is _NEVER_MATCHES_RE, so continuing would report
        # each of the register's ~240 rows as both a malformed id and an out-of-vocabulary
        # phase. That cascade buries the one problem that explains all of them, which
        # `_load_manifest` has already appended. Stopping here is safe precisely because the
        # run is already failing: the caller sees a non-empty problem list either way, and the
        # line below states plainly which checks did not run so the short list is not mistaken
        # for a clean bill of health.
        problems.append(
            f"{manifest_path.name} could not be loaded, so the register row, cross-register "
            f"linkage, roadmap, and sq checks were all skipped; fix the manifest and re-run to "
            f"see them"
        )
        return problems
    phase_vocabulary = _manifest_phase_vocabulary(manifest)
    # The eight resolutions below share their whole-table failure modes: `[namespaces] = "x"` or
    # a wholly absent table produces the same message from each call, and from the structural
    # precondition as well. Each still reports its own specific failure ("[namespaces.al]
    # .citation_pattern is missing"); the deduplication at this function's return collapses the
    # shared ones back to a single line.
    uw_id_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "uw", "pattern", problems
    )
    debt_id_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "debt", "pattern", problems
    )
    debt_citation_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "debt", "citation_pattern", problems
    )
    al_id_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "al", "pattern", problems
    )
    al_citation_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "al", "citation_pattern", problems
    )
    cap_id_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "cap", "pattern", problems
    )
    cap_citation_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "cap", "citation_pattern", problems
    )
    sq_id_pattern = _manifest_namespace_pattern(
        manifest, manifest_path, "sq", "pattern", problems
    )

    row_problems, cluster_item_text = _check_register_rows(
        clusters, phase_vocabulary, uw_id_pattern
    )
    problems.extend(row_problems)

    problems.extend(_check_manifest_integrity(manifest, manifest_path))

    roadmap_lines = _read_lines(roadmap_path, problems)
    if roadmap_lines is not None:
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

    plan_lines = _read_lines(project_plan_path, problems)
    if plan_lines is not None:
        problems.extend(
            _check_project_plan_phase_status(plan_lines, project_plan_path, manifest)
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
                    debt_id_pattern,
                    debt_citation_pattern,
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
                    al_id_pattern,
                    al_citation_pattern,
                )
            )
        except (LookupError, ValueError) as exc:
            problems.append(f"{lessons_log_path.name}: {exc}")

    capability_lines = _read_lines(capability_register_path, problems)
    capability_rows: list[tuple[int, str, str, str]] | None = None
    if capability_lines is not None:
        try:
            capability_rows = _capability_register_status_rows(
                capability_lines, cap_id_pattern
            )
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
                    cap_id_pattern,
                    cap_citation_pattern,
                )
            )
        except ValueError as exc:
            problems.append(f"{capability_register_path.name}: {exc}")

    sq_lines = _read_lines(story_structure_plan_path, problems)
    if sq_lines is not None:
        try:
            problems.extend(
                _check_sq_namespace(sq_lines, story_structure_plan_path, sq_id_pattern)
            )
        except LookupError as exc:
            problems.append(f"{story_structure_plan_path.name}: {exc}")

    # Deduplicate, preserving first-seen order. Independent checks can reach the same conclusion
    # about the manifest: `[namespaces] = "x"` is reported once by the structural precondition
    # and once by whichever namespace resolution hit it first, in identical words. Every problem
    # this module emits names a location, an id, or a specific table, so two byte-identical
    # sentences are the same finding reported twice, never two findings that happen to read
    # alike. Printing it twice inflates the count a reader uses to judge how bad a run was.
    return list(dict.fromkeys(problems))


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


def _capability_summary(
    capability_register_path: Path, id_pattern: re.Pattern[str]
) -> str:
    """Return a one-line per-glyph tally for a capability register already known well formed.

    Args:
        capability_register_path: The validated capability register markdown file.
        id_pattern: The ``[namespaces.cap].pattern`` regex, threaded down to
            ``_capability_register_status_rows``.

    Returns:
        str: A newline-terminated summary of ``Docs`` glyph counts, in checkmark/yellow/cross
            order.
    """
    lines = capability_register_path.read_text(encoding="utf-8").splitlines()
    rows = _capability_register_status_rows(lines, id_pattern)
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


def _sq_summary(story_structure_plan_path: Path) -> str:
    """Return a row tally for an sq namespace already known to be well formed.

    Printing the count is not cosmetic. Without it, a green run cannot be distinguished from a
    run that inspected an emptied table, which is the reader-facing half of the hollow-check
    problem ``_check_sq_namespace`` guards against structurally.

    The deliverable count and the map count are deliberately NOT both printed. This function is
    reached only on the success path, and success means ``_check_sq_namespace`` already proved
    the two id sets are equal and duplicate-free, so a second number would be the first one
    again wearing a different label: it would read as a cross-check while being incapable of
    disagreeing. The stage-table count beside it is genuinely independent information, because
    the deliverables live in one table per stage and dropping a whole stage table is a real
    failure the id total alone can hide.

    Args:
        story_structure_plan_path: The validated story-structure-improvement-plan.md file.

    Returns:
        str: A newline-terminated summary naming the deliverable count and the number of stage
            tables those deliverables were collected from.

    Raises:
        LookupError: If the SQ deliverables table header cannot be located. Unreachable on the
            success path, where ``_check_sq_namespace`` has already located it.
    """
    lines = story_structure_plan_path.read_text(encoding="utf-8").splitlines()
    defined = len(_sq_work_table_ids(lines))
    stage_tables = len(_find_sq_work_table_headers(lines))
    return (
        f"     {defined} SQ deliverable(s) across {stage_tables} stage table(s), each mapped "
        f"to a scheduling record\n"
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
        "--story-structure-plan",
        default=str(_DEFAULT_STORY_STRUCTURE_PLAN),
        help=(
            "Path to story-structure-improvement-plan.md, home of the SQ-to-register map table "
            "checked against the manifest's sq namespace pattern."
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
        story_structure_plan_path=Path(args.story_structure_plan),
    )
    if problems:
        sys.stdout.write(f"FAIL {register_path}:\n")
        for problem in problems:
            sys.stdout.write(f"  - {problem}\n")
        return 1

    sys.stdout.write(f"ok: {register_path.name} satisfies the work-linkage contract\n")
    sys.stdout.write(_summary(register_path))
    # check_linkage already proved the manifest and its cap namespace resolve cleanly (the
    # success path above is only reached with an empty problems list), so re-resolving the
    # pattern here for the summary's own read of the capability register cannot newly fail; a
    # throwaway list absorbs the call's signature without adding a second problems channel.
    summary_manifest_path = Path(args.manifest)
    cap_id_pattern = _manifest_namespace_pattern(
        _load_manifest(summary_manifest_path, []),
        summary_manifest_path,
        "cap",
        "pattern",
        [],
    )
    sys.stdout.write(_capability_summary(capability_register_path, cap_id_pattern))
    sys.stdout.write(_sq_summary(Path(args.story_structure_plan)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
