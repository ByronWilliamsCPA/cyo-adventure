"""Backfill ``metadata.narrative_person`` across the skeleton catalog.

One-shot mechanical backfill for the 2026-08-21 `UW-C324` ruling (section 9.4
of ``docs/planning/live-structural-round-2026-08-21.md``): every skeleton
declares the grammatical person its prose is told in, so a fill can be held to
it and same-skeleton siblings cannot ship in different persons.

Inference order, most explicit source first:

1. ``narrative_style == "gamebook"``: ``second`` (genre convention; committed
   gamebook fills measure 0.715-1.0 second-person node rates).
2. The beats' own pronouns: a skeleton whose ``<<FILL ... beats='...'>>``
   text uses second-person tokens on at least ``--beats-threshold`` of its
   directive nodes (default 0.3) declares ``second``; the live rounds showed
   fills track the beats' person closely where it is declared (0.45 beats
   gave a 0.448 fill).
3. A committed fill at ``out/<slug>.filled.json``: its measured second-person
   node rate decides at 0.5.
4. Otherwise ``third``, the committed-prose norm (0.0-0.27 measured).

Idempotent: a skeleton already declaring ``narrative_person`` is left alone.
The write is a one-line textual insertion inside the ``"metadata"`` block that
copies the file's own indentation (the catalog mixes indent widths), verified
by re-parsing; nothing else in the file moves.

Usage:
    uv run python scripts/backfill_narrative_person.py [--dry-run]
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


def _second_person_rate(bodies: list[str]) -> float:
    """Return the fraction of non-empty texts containing a second-person token."""
    texts = [body for body in bodies if body.strip()]
    if not texts:
        return 0.0
    return sum(1 for body in texts if _SECOND_RE.search(body)) / len(texts)


def _infer(
    skeleton: dict[str, Any], slug: str, *, beats_threshold: float
) -> tuple[str, str]:
    """Return (person, source) for one skeleton."""
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
        try:
            filled = json.loads(filled_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
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


def _insert_person(path: Path, person: str) -> None:
    """Insert ``"narrative_person"`` textually, preserving the file's format.

    The catalog mixes indent widths (indent=1 and indent=2 files both exist),
    so a parse-and-redump would reformat whole files and drown the mechanical
    change in noise. Instead the key is inserted as the first line inside the
    ``"metadata"`` object, copying the indentation of the line that follows
    the opening brace; the result is re-parsed to prove the file is still
    valid JSON carrying the new value.

    Args:
        path: The skeleton file to edit in place.
        person: The inferred narrative person value.

    Raises:
        ValueError: If the metadata block cannot be located, or the edited
            file no longer parses to the expected value.
    """
    raw = path.read_text(encoding="utf-8")
    marker = '"metadata": {'
    at = raw.find(marker)
    if at == -1:
        msg = f"{path}: no multi-line metadata block found"
        raise ValueError(msg)
    line_end = raw.index("\n", at)
    next_line = raw[line_end + 1 :]
    indent = next_line[: len(next_line) - len(next_line.lstrip(" "))]
    insertion = f'{indent}"narrative_person": "{person}",\n'
    edited = raw[: line_end + 1] + insertion + raw[line_end + 1 :]
    reparsed = cast("dict[str, Any]", json.loads(edited))
    got = cast("dict[str, Any]", reparsed.get("metadata") or {}).get("narrative_person")
    if got != person:
        msg = f"{path}: edited file does not carry narrative_person={person!r}"
        raise ValueError(msg)
    path.write_text(edited, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code 0; the backfill is mechanical and skips rather than fails.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report, write nothing.")
    parser.add_argument(
        "--beats-threshold",
        type=float,
        default=0.3,
        help=(
            "Fraction of directive nodes whose beats must use second-person "
            "tokens for the beats to decide 'second' (default 0.3)."
        ),
    )
    args = parser.parse_args(argv)
    counts: dict[str, int] = {}
    for path in sorted(Path("skeletons").glob("*/*.json")):
        if is_sidecar(path):
            continue
        skeleton = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
        metadata = cast("dict[str, Any]", skeleton.get("metadata") or {})
        if metadata.get("narrative_person"):
            counts["already declared"] = counts.get("already declared", 0) + 1
            continue
        person, source = _infer(
            skeleton, path.stem, beats_threshold=cast("float", args.beats_threshold)
        )
        counts[f"{person} ({source.split(' rate')[0]})"] = (
            counts.get(f"{person} ({source.split(' rate')[0]})", 0) + 1
        )
        sys.stdout.write(f"{path}: {person}  [{source}]\n")
        if not args.dry_run:
            _insert_person(path, person)
    for key, value in sorted(counts.items()):
        sys.stdout.write(f"  {value:>4}  {key}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
