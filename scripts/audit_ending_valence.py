"""Audit ending valence against ending prose across the skeleton and fill catalog.

Usage:
    uv run python scripts/audit_ending_valence.py [--json] [--band BAND ...]
        [--suspect-only] [--skeletons-root PATH] [--out-root PATH]

Walks every skeleton under ``skeletons/**/*.json`` (skipping the WS-2 theme
contract and WS-5 lineage sidecars via ``is_sidecar``, the same predicate
every other catalog scanner uses) and every filled story under
``out/*.filled.json``. For each ending node it reports: file, ending id,
title, kind, declared valence, and the final ~40 words of the ending node's
body prose. A skeleton's ending body is frequently still an unfilled
``<<FILL ...>>`` directive rather than prose; the report marks those rows
"UNFILLED" in the tail column instead of guessing at text that does not
exist yet.

This is the W0.2 triage script from
``docs/planning/kid-appeal-implementation-plan.md`` (see also
``docs/planning/design-review-kid-appeal-2026-08-01.md`` section 2.7): it
flags a negative-valence ending as SUSPECT when its closing prose matches a
transparent, hand-reviewable heuristic word list for warmth, laughter,
comfort, hope, or an explicit try-again invitation (the four signals named
in the design review). It is a triage aid, not an oracle: both false
positives (a genuinely sad ending that happens to end on the word "hope")
and false negatives (a warm ending phrased outside the word list) are
expected. A human makes every re-tag decision; this script only narrows
where to look.

Structural defects are reported separately from SUSPECT triage rows and are
NOT informational. An ending the audit could not actually audit (no ending
object, a missing or unrecognized ``valence``) is the strongest form of the
defect this script exists to catch, so it is surfaced as a PROBLEM row and
changes the exit code rather than being dropped or silently treated as
benign.

Exit codes:
    0 - scan completed cleanly (SUSPECT findings are informational)
    1 - a catalog file failed to load or parse
    2 - the scan completed but at least one ending could not be audited
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cyo_adventure.generation.skeleton import FILL_MARKER, is_sidecar

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SKELETONS_ROOT = _REPO_ROOT / "skeletons"
_DEFAULT_OUT_ROOT = _REPO_ROOT / "out"

_TAIL_WORD_COUNT = 40

# Transparent triage heuristic (NOT an oracle -- see the module docstring).
# A negative-valence ending is flagged SUSPECT when its closing ~40 words
# contain any of these lowercase tokens or phrases, grouped by the four
# signals the design review names in section 2.7: warmth, laughter/comfort,
# hope, and an explicit try-again invitation. Kept as short, literal
# substrings on purpose, so a reviewer can read this list top to bottom and
# know exactly why any given row was flagged.
_WARMTH_WORDS: tuple[str, ...] = (
    "happy",
    "warm",
    "cozy",
    "snug",
    "safe",
    "loved",
    "gentle",
    "glad",
)
_LAUGHTER_COMFORT_WORDS: tuple[str, ...] = (
    "laugh",
    "laughed",
    "laughing",
    "giggle",
    "giggled",
    "giggling",
    "smile",
    "smiled",
    "smiling",
    "hug",
    "hugged",
    "comfort",
    "comforted",
    "funny",
)
_HOPE_WORDS: tuple[str, ...] = (
    "hope",
    "hopeful",
    "wish",
    "someday",
    "excited",
    "looking forward",
)
_TRY_AGAIN_PHRASES: tuple[str, ...] = (
    "try again",
    "time to try",
    "try it again",
    "another try",
    "next time",
    "one more try",
)

_SUSPECT_HEURISTIC_WORDS: tuple[str, ...] = (
    _WARMTH_WORDS + _LAUGHTER_COMFORT_WORDS + _HOPE_WORDS + _TRY_AGAIN_PHRASES
)


_VALID_VALENCES: frozenset[str] = frozenset({"positive", "neutral", "negative"})


@dataclass
class EndingRow:
    """One ending's audit record: identity, declared valence, and closing prose."""

    source: str
    file: str
    band: str
    ending_id: str
    title: str
    kind: str
    valence: str
    unfilled: bool
    tail: str
    suspect: bool
    # Empty when the ending was auditable. Otherwise names why it was not:
    # the row is still emitted and counted, never dropped.
    problem: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict for JSON export.

        Returns:
            A dict with the same fields as this dataclass.
        """
        return asdict(self)


def _display_path(path: Path) -> str:
    """Return ``path`` relative to the repo root, or absolute if outside it.

    ``--skeletons-root`` / ``--out-root`` accept ANY directory, so a bare
    ``relative_to(_REPO_ROOT)`` raises ValueError and crashes the whole scan
    on a perfectly valid invocation (and made this script untestable against
    a tmp_path fixture).

    Args:
        path: The catalog file path.

    Returns:
        A repo-relative path string when possible, else the absolute path.
    """
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _tail_words(body: str, count: int = _TAIL_WORD_COUNT) -> str:
    """Return the final ``count`` whitespace-separated words of ``body``.

    Args:
        body: The node's body text (prose, or a skeleton ``<<FILL`` directive).
        count: How many trailing words to keep.

    Returns:
        The joined tail words, or the whole body if it has fewer than ``count``
        words.
    """
    words = body.split()
    return " ".join(words[-count:])


def _is_suspect(valence: str, tail_text: str) -> bool:
    """Return whether a negative-valence ending's tail trips the heuristic.

    Args:
        valence: The ending's declared ``valence`` string.
        tail_text: The final ~40 words of the ending node's body.

    Returns:
        True when ``valence`` is "negative" and the tail contains any of the
        heuristic warmth, laughter/comfort, hope, or try-again words/phrases.
    """
    if valence != "negative":
        return False
    lowered = tail_text.lower()
    return any(phrase in lowered for phrase in _SUSPECT_HEURISTIC_WORDS)


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON object from ``path``, or report and return None.

    Args:
        path: File path to read.

    Returns:
        The decoded object, or None on any load failure (written to stderr).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        sys.stderr.write(f"FAIL load {path}: {exc}\n")
        return None
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"FAIL parse {path}: {exc}\n")
        return None
    if not isinstance(data, dict):
        sys.stderr.write(f"FAIL load {path}: top-level JSON is not an object\n")
        return None
    return data


def _rows_for_story(
    path: Path, source: str, default_band: str, story: dict[str, Any]
) -> list[EndingRow]:
    """Return one EndingRow per ending node in a decoded story file.

    Args:
        path: The story file path (skeleton or filled), for the ``file`` column.
        source: "skeleton" or "filled", recorded on each row.
        default_band: The age band to use when ``metadata.age_band`` is
            missing (for skeletons this is the containing band directory).
        story: The already-decoded story object. Passed in rather than loaded
            here so the caller reads each file exactly once; loading inside
            meant a load failure was reported twice and re-read the file.

    Returns:
        A list of EndingRow, one per ending node, including rows whose
        ``problem`` is set. Empty only when the file declares no ending nodes.
    """
    metadata = story.get("metadata")
    band = default_band
    if isinstance(metadata, dict) and isinstance(metadata.get("age_band"), str):
        band = metadata["age_band"]
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        # Not a load failure (the JSON parsed), but the file contributes zero
        # rows, which is indistinguishable from a story that legitimately has
        # no endings unless it says so.
        sys.stderr.write(f"PROBLEM {path}: 'nodes' is not a list; no endings audited\n")
        return []
    rows: list[EndingRow] = []
    for node in nodes:
        if not isinstance(node, dict) or not node.get("is_ending"):
            continue
        ending = node.get("ending")
        body = node.get("body")
        body_text = body if isinstance(body, str) else ""
        unfilled = FILL_MARKER in body_text
        tail = "UNFILLED" if unfilled else _tail_words(body_text)
        if not isinstance(ending, dict):
            # A node claiming to BE an ending with no ending object is a data
            # defect, not a row to skip. It was silently dropped before, so
            # the audit reported a smaller catalog than it scanned.
            rows.append(
                EndingRow(
                    source=source,
                    file=_display_path(path),
                    band=band,
                    ending_id=str(node.get("id", "")),
                    title="",
                    kind="",
                    valence="",
                    unfilled=unfilled,
                    tail=tail,
                    suspect=False,
                    problem="no-ending-object",
                )
            )
            continue
        raw_valence = ending.get("valence")
        valence = str(raw_valence) if isinstance(raw_valence, str) else ""
        # #CRITICAL: data-integrity: a MISSING valence used to collapse into
        # "" via `.get("valence", "")`, and `_is_suspect` returns False for
        # anything that is not exactly "negative". An ending with no declared
        # valence is the strongest form of the mis-tagging this audit exists
        # to find, and it was the one case guaranteed to be invisible.
        # #VERIFY: tests/unit/test_audit_ending_valence.py::
        # test_missing_valence_is_reported_as_a_problem.
        problem = (
            ""
            if valence in _VALID_VALENCES
            else f"bad-valence:{valence or '<missing>'}"
        )
        rows.append(
            EndingRow(
                source=source,
                file=_display_path(path),
                band=band,
                ending_id=str(ending.get("id", "")),
                title=str(ending.get("title", "")),
                kind=str(ending.get("kind", "")),
                valence=valence,
                unfilled=unfilled,
                tail=tail,
                suspect=False if unfilled else _is_suspect(valence, tail),
                problem=problem,
            )
        )
    return rows


def _iter_skeleton_files(root: Path) -> list[Path]:
    """Return every non-sidecar skeleton JSON path under ``root``, sorted.

    Args:
        root: The skeletons/ tree to walk.

    Returns:
        Sorted list of skeleton file paths (contract/lineage sidecars excluded).
    """
    return sorted(p for p in root.rglob("*.json") if not is_sidecar(p))


def _iter_filled_files(root: Path) -> list[Path]:
    """Return every ``*.filled.json`` path directly under ``root``, sorted.

    Args:
        root: The out/ tree to scan (non-recursive: filled stories live flat).

    Returns:
        Sorted list of filled-story file paths.
    """
    return sorted(root.glob("*.filled.json"))


def _collect_rows(skeletons_root: Path, out_root: Path) -> tuple[list[EndingRow], bool]:
    """Scan both catalogs and return every ending row plus a load-failure flag.

    Args:
        skeletons_root: The skeletons/ tree to walk.
        out_root: The out/ tree of filled stories to scan.

    Returns:
        A tuple of (rows, any_load_failed). ``any_load_failed`` is True if any
        file under either root failed to load or parse as a JSON object; those
        files contribute no rows but do not stop the scan of the rest.
    """
    rows: list[EndingRow] = []
    any_failed = False
    if skeletons_root.is_dir():
        for path in _iter_skeleton_files(skeletons_root):
            band_dir = path.relative_to(skeletons_root).parts[0]
            story = _load_json(path)
            if story is None:
                any_failed = True
                continue
            rows.extend(_rows_for_story(path, "skeleton", band_dir, story))
    if out_root.is_dir():
        for path in _iter_filled_files(out_root):
            story = _load_json(path)
            if story is None:
                any_failed = True
                continue
            rows.extend(_rows_for_story(path, "filled", "?", story))
    return rows, any_failed


def _print_table(rows: list[EndingRow]) -> None:
    """Print a human-readable, column-aligned table of ending rows.

    Args:
        rows: The rows to print, in the order given.
    """
    if not rows:
        print("no ending rows matched the given filters")
        return
    header = (
        f"{'FLAG':8} {'BAND':6} {'FILE':45} {'ENDING ID':22} {'KIND':10} "
        f"{'VALENCE':9} TITLE / TAIL"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        flag = "PROBLEM" if row.problem else ("SUSPECT" if row.suspect else "")
        print(
            f"{flag:8} {row.band:6} {row.file:45} {row.ending_id:22} "
            f"{row.kind:10} {row.valence:9} {row.title}"
        )
        if row.problem:
            print(f"{'':8} {'':6} problem: {row.problem}")
        print(f"{'':8} {'':6} tail: {row.tail}")

    suspects = [row for row in rows if row.suspect]
    problems = [row for row in rows if row.problem]
    print("-" * len(header))
    print(
        f"total endings: {len(rows)}  SUSPECT: {len(suspects)}  "
        f"PROBLEM (not auditable): {len(problems)}"
    )
    by_band: dict[str, int] = {}
    for row in suspects:
        by_band[row.band] = by_band.get(row.band, 0) + 1
    for band in sorted(by_band):
        print(f"  SUSPECT in {band}: {by_band[band]}")


def main(argv: list[str] | None = None) -> int:
    """Audit every ending's declared valence against its closing prose.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 on a clean scan, 1 if any catalog file failed to load or
        parse, 2 if the scan completed but some ending could not be audited.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skeletons-root",
        type=Path,
        default=_DEFAULT_SKELETONS_ROOT,
        help="Root of the skeletons/ tree (default: repo skeletons/).",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=_DEFAULT_OUT_ROOT,
        help="Root of the filled-story out/ tree (default: repo out/).",
    )
    parser.add_argument(
        "--band",
        action="append",
        default=None,
        help="Restrict to one age band (repeatable); matches metadata.age_band.",
    )
    parser.add_argument(
        "--suspect-only",
        action="store_true",
        help="Only list SUSPECT endings (negative valence, warm-sounding tail).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON array instead of the human-readable table.",
    )
    args = parser.parse_args(argv)

    rows, any_failed = _collect_rows(args.skeletons_root, args.out_root)
    # Computed over the FULL scan, before --band/--suspect-only narrow the
    # printed table: a filter chosen for readability must not be able to
    # silence a defect the scan actually found.
    any_problem = any(row.problem for row in rows)

    if args.band:
        wanted_bands = set(args.band)
        rows = [row for row in rows if row.band in wanted_bands]
    if args.suspect_only:
        rows = [row for row in rows if row.suspect]

    if args.json:
        print(json.dumps([row.to_dict() for row in rows], indent=2))
    else:
        _print_table(rows)

    if any_failed:
        return 1
    return 2 if any_problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
