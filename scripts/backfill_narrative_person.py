"""Backfill ``metadata.narrative_person`` across the skeleton catalog.

One-shot mechanical backfill for the 2026-08-21 `UW-C328` ruling (section 9.4
of ``docs/planning/live-structural-round-2026-08-21.md``): every skeleton
declares the grammatical person its prose is told in, so a fill can be held to
it and same-skeleton siblings cannot ship in different persons.

Inference order, most explicit source first:

1. ``narrative_style == "gamebook"``: ``second`` (genre convention; committed
   gamebook fills measure 0.715-1.0 second-person node rates).
2. The beats' own pronouns: a skeleton whose ``<<FILL ... beats='...'>>``
   text uses second-person tokens on at least ``--beats-threshold`` of its
   directive nodes declares ``second``; the live rounds showed fills track
   the beats' person closely where it is declared (0.45 beats gave a 0.448
   fill). The default is 0.5, the SAME floor ``check_prose_craft.py`` holds
   a declared-second book to: an earlier 0.3 default declared books
   ``second`` that the gate would then fail on the fills the beats predict
   (PR #737 review, I2; `the-orchard-signal` at 0.31 was the reproduced
   victim, corrected in the same commit).
3. A committed fill at ``out/<slug>.filled.json``: its measured second-person
   node rate decides at 0.5.
4. Otherwise ``third``, the committed-prose norm (0.0-0.27 measured).

The 0.5 beats threshold is not a taste call: ``scripts/check_prose_craft.py``
fails any book declared ``second`` whose measured prose rate falls below its
``--min-gamebook-second-person`` (default 0.5). Inferring ``second`` from a
lower beats rate would hand the checker a book that faithfully tracks its own
beats and still fails, so the inference boundary is pinned to the enforcement
boundary, matching rule 3, which already decided at 0.5.

Idempotent: a skeleton already declaring ``narrative_person`` is left alone.
Because of that, changing an inference rule does NOT propagate on a plain
re-run; pass ``--rederive`` to re-infer declared skeletons and rewrite any
whose committed value no longer matches the rules.

The write is a one-line textual insertion inside the ``"metadata"`` block that
copies the file's own indentation and line terminator (the catalog mixes
indent widths), verified by re-parsing; nothing else in the file moves.

Usage:
    uv run python scripts/backfill_narrative_person.py [--dry-run]
    uv run python scripts/backfill_narrative_person.py --rederive
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

from cyo_adventure.generation.skeleton import is_sidecar

_SECOND_RE = re.compile(r"\b(you|your|yours|yourself)\b", re.IGNORECASE)
_FILL_MARKER = "<<FILL"
_METADATA_MARKER = '"metadata": {'
_DECLARATION_RE = re.compile(r'("narrative_person"\s*:\s*")[^"]*(")')

# #CRITICAL: data integrity: every write in this module edits a COMMITTED
# catalog skeleton in place by textual splice rather than by parse-and-redump,
# so a mis-located splice silently corrupts a tracked story graph that no
# runtime check re-validates before a fill is bound to it.
# #VERIFY: every writer re-parses its own output and refuses to persist unless
# the top-level ``metadata.narrative_person`` reads back as the intended value;
# the splice never lands blind. Covered by
# ``test_insert_person_rejects_single_line_metadata_block``,
# ``test_insert_person_rejects_nested_metadata_marker``, and
# ``test_replace_person_rejects_nested_declaration`` in
# ``tests/unit/test_backfill_narrative_person.py``.


def _second_person_rate(bodies: list[str]) -> float:
    """Return the fraction of non-empty texts containing a second-person token.

    Args:
        bodies: Candidate texts; blank entries are ignored.

    Returns:
        The fraction in ``[0.0, 1.0]``, or 0.0 when nothing is measurable.
    """
    texts = [body for body in bodies if body.strip()]
    if not texts:
        return 0.0
    return sum(1 for body in texts if _SECOND_RE.search(body)) / len(texts)


def _infer(
    skeleton: dict[str, Any], slug: str, *, beats_threshold: float
) -> tuple[str, str]:
    """Return (person, source) for one skeleton.

    Args:
        skeleton: The parsed skeleton object.
        slug: The skeleton's file stem, used to locate a committed fill.
        beats_threshold: Fraction of directive nodes whose beats must carry a
            second-person token for rule 2 to decide ``second``.

    Returns:
        A ``(person, source)`` pair naming the rule that decided.
    """
    metadata = cast("dict[str, Any]", skeleton.get("metadata") or {})
    if metadata.get("narrative_style") == "gamebook":
        return "second", "gamebook convention"
    nodes = cast("list[dict[str, Any]]", skeleton.get("nodes") or [])
    beats = [
        cast("str", node.get("body") or "")
        for node in nodes
        if _FILL_MARKER in cast("str", node.get("body") or "")
    ]
    beats_rate = _second_person_rate(beats)
    if beats_rate >= beats_threshold:
        return "second", f"beats second-person rate {beats_rate:.2f}"
    filled_path = Path("out") / f"{slug}.filled.json"
    if filled_path.exists():
        # #ASSUME: data integrity: an unreadable or malformed committed fill is
        # treated as absent, so the skeleton falls through to the ``third``
        # prose default rather than aborting the catalog sweep. A corrupt fill
        # that was in fact second-person therefore mis-declares as ``third``.
        # #VERIFY: the fallback is exercised, and its declared outcome pinned,
        # by ``test_infer_corrupt_committed_fill_falls_back_to_default`` in
        # ``tests/unit/test_backfill_narrative_person.py``. Re-run with
        # ``--rederive`` once a fill is repaired to correct any such row.
        try:
            filled = json.loads(filled_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # #ASSUME: data-integrity: a committed fill that fails to parse
            # is treated as absent (rule 4 decides), never as evidence; the
            # skeleton itself is untouched either way.
            filled = None
        if isinstance(filled, dict):
            bodies = [
                cast("str", node.get("body") or "")
                for node in cast(
                    "list[dict[str, Any]]",
                    cast("dict[str, Any]", filled).get("nodes") or [],
                )
            ]
            fill_rate = _second_person_rate(bodies)
            person = "second" if fill_rate >= 0.5 else "third"
            return person, f"committed fill second-person rate {fill_rate:.2f}"
    return "third", "prose default"


def _read_preserving_newlines(path: Path) -> str:
    """Read a file without translating its line endings.

    ``Path.read_text`` applies universal-newline translation, which turns a
    CRLF checkout into LF in memory and then writes LF back out, moving every
    line in the file. Opening with ``newline=""`` disables translation in both
    directions so only the spliced line changes.

    Args:
        path: The file to read.

    Returns:
        The file's exact text, CR characters included.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_preserving_newlines(path: Path, text: str) -> None:
    """Write text verbatim, without re-translating line endings.

    Args:
        path: The file to overwrite.
        text: The exact text to persist.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _verified(path: Path, edited: str, person: str) -> str:
    """Return ``edited`` once it re-parses to the intended declaration.

    Args:
        path: The file the edit came from, for the error message.
        edited: The candidate file text.
        person: The narrative person the edit was meant to declare.

    Returns:
        The unchanged ``edited`` text.

    Raises:
        ValueError: If the edited text no longer parses, or the top-level
            ``metadata.narrative_person`` does not read back as ``person``.
    """
    try:
        reparsed = json.loads(edited)
    except json.JSONDecodeError as exc:
        msg = f"{path}: edit produced invalid JSON ({exc})"
        raise ValueError(msg) from exc
    if not isinstance(reparsed, dict):
        msg = f"{path}: edit produced a non-object document"
        raise ValueError(msg)
    document = cast("dict[str, Any]", reparsed)
    metadata = cast("dict[str, Any]", document.get("metadata") or {})
    if metadata.get("narrative_person") != person:
        msg = f"{path}: edited file does not carry narrative_person={person!r}"
        raise ValueError(msg)
    return edited


def _insert_person(path: Path, person: str) -> None:
    """Insert ``"narrative_person"`` textually, preserving the file's format.

    The catalog mixes indent widths (indent=1 and indent=2 files both exist),
    so a parse-and-redump would reformat whole files and drown the mechanical
    change in noise. Instead the key is inserted as the first line inside the
    ``"metadata"`` object, copying the indentation of the line that follows
    the opening brace and that line's terminator; the result is re-parsed to
    prove the file is still valid JSON carrying the new value.

    ``str.find`` takes the FIRST ``"metadata": {`` in the file, which is not
    necessarily the top-level one: a node-level ``metadata`` object declared
    earlier in the document matches first and would take the splice. The
    re-parse in :func:`_verified` is what catches that, and its ``ValueError``
    is the caller's signal to SKIP the file, never to abort the sweep.

    Args:
        path: The skeleton file to edit in place.
        person: The inferred narrative person value.

    Raises:
        ValueError: If the metadata block cannot be located, if the marker is
            the last line of the file, or if the edited file no longer parses
            to the expected value.
    """
    # #CRITICAL: data-integrity: this edits every catalog skeleton IN PLACE
    # by textual splice. The splice is only trusted because the edited text
    # is re-parsed below and asserted to carry exactly the inserted value;
    # any failure raises before the write, so a skeleton is never written
    # half-edited.
    # #VERIFY: the re-parse assertion in :func:`_verified`; corrupt output
    # raises ValueError before ``_write_preserving_newlines`` is reached.
    raw = _read_preserving_newlines(path)
    at = raw.find(_METADATA_MARKER)
    if at == -1:
        msg = f"{path}: no multi-line metadata block found"
        raise ValueError(msg)
    # #EDGE: data integrity: a file whose metadata marker sits on its final
    # line has no newline after ``at``; ``str.index`` would raise a bare
    # ValueError from inside the splice with no path context.
    # #VERIFY: guarded below and pinned by
    # ``test_insert_person_rejects_marker_without_trailing_newline`` in
    # ``tests/unit/test_backfill_narrative_person.py``.
    line_end = raw.find("\n", at)
    if line_end == -1:
        msg = f"{path}: no newline after the metadata marker"
        raise ValueError(msg)
    eol = "\r\n" if line_end > 0 and raw[line_end - 1] == "\r" else "\n"
    next_line = raw[line_end + 1 :]
    indent = next_line[: len(next_line) - len(next_line.lstrip(" "))]
    insertion = f'{indent}"narrative_person": "{person}",{eol}'
    edited = raw[: line_end + 1] + insertion + raw[line_end + 1 :]
    _write_preserving_newlines(path, _verified(path, edited, person))


def _replace_person(path: Path, person: str) -> None:
    """Rewrite an existing ``"narrative_person"`` value in place.

    Used only by ``--rederive``. Like :func:`_insert_person` this is a textual
    edit that touches one line, and like it the substitution targets the first
    match in the file, so the re-parse in :func:`_verified` is the guard that a
    nested declaration was not the one rewritten.

    Args:
        path: The skeleton file to edit in place.
        person: The re-inferred narrative person value.

    Raises:
        ValueError: If no declaration is present, or the edited file no longer
            parses to the expected value.
    """
    raw = _read_preserving_newlines(path)
    edited, count = _DECLARATION_RE.subn(rf"\g<1>{person}\g<2>", raw, count=1)
    if count == 0:
        msg = f"{path}: no narrative_person declaration to rewrite"
        raise ValueError(msg)
    _write_preserving_newlines(path, _verified(path, edited, person))


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report, write nothing.")
    parser.add_argument(
        "--rederive",
        action="store_true",
        help=(
            "Re-infer skeletons that already declare narrative_person and "
            "rewrite any whose committed value no longer matches the rules. "
            "Without this the run is idempotent and a rule change never "
            "propagates to already-backfilled files."
        ),
    )
    parser.add_argument(
        "--beats-threshold",
        type=float,
        default=0.5,
        help=(
            "Fraction of directive nodes whose beats must use second-person "
            "tokens for the beats to decide 'second' (default 0.5, the SAME "
            "floor check_prose_craft.py holds a declared-second book to, so "
            "the backfill never declares a person its own gate predicts the "
            "fills will fail; PR #737 review, I2)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Walks ``skeletons/*/*.json`` relative to the current working directory, so
    it must be run from the repository root.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        0 when every catalog file was handled, 1 when one or more files were
        skipped. A skip never aborts the sweep: the backfill is mechanical and
        an odd file is reported and stepped over so the catalog is never left
        half-written.
    """
    args = _build_parser().parse_args(argv)
    counts: dict[str, int] = {}
    skipped: list[tuple[Path, str]] = []
    for path in sorted(Path("skeletons").glob("*/*.json")):
        if is_sidecar(path):
            continue
        try:
            loaded = json.loads(_read_preserving_newlines(path))
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append((path, f"unreadable: {exc}"))
            continue
        if not isinstance(loaded, dict):
            skipped.append((path, "not a JSON object"))
            continue
        skeleton = cast("dict[str, Any]", loaded)
        metadata = cast("dict[str, Any]", skeleton.get("metadata") or {})
        declared = cast("str | None", metadata.get("narrative_person"))
        if declared and not args.rederive:
            counts["already declared"] = counts.get("already declared", 0) + 1
            continue
        person, source = _infer(
            skeleton, path.stem, beats_threshold=cast("float", args.beats_threshold)
        )
        if declared == person:
            counts["already correct"] = counts.get("already correct", 0) + 1
            continue
        key = f"{person} ({source.split(' rate')[0]})"
        counts[key] = counts.get(key, 0) + 1
        verb = f"{declared} -> {person}" if declared else person
        sys.stdout.write(f"{path}: {verb}  [{source}]\n")
        if args.dry_run:
            continue
        write = _replace_person if declared else _insert_person
        try:
            write(path, person)
        except (OSError, ValueError) as exc:
            skipped.append((path, str(exc)))
    for key, value in sorted(counts.items()):
        sys.stdout.write(f"  {value:>4}  {key}\n")
    for path, reason in skipped:
        sys.stdout.write(f"SKIPPED {path}: {reason}\n")
    if skipped:
        sys.stdout.write(f"  {len(skipped):>4}  skipped\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
