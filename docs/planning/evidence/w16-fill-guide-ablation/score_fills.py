"""Deterministic scorer for sibling-fill experiments in this directory.

Reuses the project's own gram tokenizer (`scripts/check_sibling_fills.py`)
via import so every rate here is commensurable with the corrected 16l table.
Two gram scopes are reported for every pair, because AL-309 (open) documents
that concatenation manufactures junction grams spanning unit boundaries:

- ``concat``: bodies joined with spaces, then grammed (the scope the corrected
  16l figures were re-derived at, junction defect included);
- ``per_node``: each body grammed separately, per-book union (junction-free).

Per book, the scorer also reports: body words, mean words per node against the
shell's ``words=N`` directives, whole-book Flesch-Kincaid and in-band rate
(``validator.reading_level.measure_book``), dialogue share (fraction of
sentences containing a quote character), second-person density per 1000 words
(a prototype of the deferred W2.3 check), told-emotion is left to
``scripts/check_prose_craft.py``, em-dash count, and any ``<<FILL`` residue.

Usage::

    uv run python score_fills.py --shell <shell.json> \
        --pair NAME=<a.json>:<b.json> [--pair ...] --out results.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location(
    "csf", REPO / "scripts" / "check_sibling_fills.py"
)
assert _spec is not None and _spec.loader is not None
csf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csf)

from cyo_adventure.validator.reading_level import measure_book  # noqa: E402

_SENT_RE = re.compile(r"[^.!?]+[.!?]?")
_QUOTE_RE = re.compile(r"[\"“”]")
_YOU_RE = re.compile(r"\b(you|your|yours|yourself)\b")
_FILL_RE = re.compile(r"<<FILL")
_WORDS_RE = re.compile(r"words=(\d+)")


def _bodies(story: dict[str, Any]) -> list[str]:
    return [
        str(n.get("body", ""))
        for n in cast("list[dict[str, Any]]", story.get("nodes") or [])
    ]


def _word_count(text: str) -> int:
    return len(csf._WORD_RE.findall(text.lower()))


def book_stats(story: dict[str, Any], shell: dict[str, Any]) -> dict[str, Any]:
    """Per-book deterministic measures."""
    bodies = _bodies(story)
    text = " ".join(bodies)
    words = _word_count(text)
    targets = [
        int(m.group(1)) if (m := _WORDS_RE.search(str(n.get("body", "")))) else None
        for n in cast("list[dict[str, Any]]", shell.get("nodes") or [])
    ]
    target_mean = (
        sum(t for t in targets if t) / max(1, sum(1 for t in targets if t))
        if any(targets)
        else None
    )
    sentences = [s for s in _SENT_RE.findall(text) if s.strip()]
    dialogue = sum(1 for s in sentences if _QUOTE_RE.search(s)) / max(1, len(sentences))
    rl = cast("dict[str, Any]", story.get("metadata", {})).get("reading_level", {})
    level = measure_book(
        bodies,
        target=float(rl.get("target", 5.5)),
        tolerance=float(rl.get("tolerance", 1.5)),
    )
    grade = getattr(level, "grade", None)
    if isinstance(grade, (int, float)):
        fk_grade: Any = round(grade, 2)
    else:
        # A missing grade stays null in the report rather than becoming the
        # string "None", which would lose the null signal for a consumer. Any
        # other non-numeric value is stringified so an unexpected grade type
        # stays visible instead of being silently coerced.
        fk_grade = None if grade is None else str(grade)
    in_band = None
    for name in ("in_band", "in_band_rate", "in_band_share"):
        if hasattr(level, name):
            in_band = getattr(level, name)
            break
    return {
        "title": story.get("title"),
        "body_words": words,
        "mean_words_per_node": round(words / max(1, len(bodies)), 1),
        "shell_target_mean": round(target_mean, 1) if target_mean else None,
        "fk_grade": fk_grade,
        "in_band": in_band if not isinstance(in_band, float) else round(in_band, 3),
        "dialogue_share": round(dialogue, 4),
        "you_per_1000": round(
            len(_YOU_RE.findall(text.lower())) / max(1, words) * 1000, 1
        ),
        # Escaped rather than literal: the repo forbids a literal U+2014 in
        # tracked source, and this counter is the one place that needs the
        # character as data. "\u2014" is the same string at runtime.
        "em_dashes": text.count("\u2014"),
        "fill_residue": len(_FILL_RE.findall(text)),
        "level_repr": repr(level),
    }


def pair_stats(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Bodies-only shared four-grams at both scopes, plus label frames."""
    a_bodies, b_bodies = _bodies(a), _bodies(b)
    a_words, b_words = _word_count(" ".join(a_bodies)), _word_count(" ".join(b_bodies))
    mean_words = (a_words + b_words) / 2.0

    concat_a = csf._grams(" ".join(a_bodies))
    concat_b = csf._grams(" ".join(b_bodies))
    concat_shared = concat_a & concat_b

    union_a: set[tuple[str, ...]] = set().union(*(csf._grams(t) for t in a_bodies))
    union_b: set[tuple[str, ...]] = set().union(*(csf._grams(t) for t in b_bodies))
    node_shared = union_a & union_b

    frames = csf.menu_frame_overlap([a, b])
    return {
        "mean_body_words": round(mean_words, 1),
        "concat_shared": len(concat_shared),
        "concat_per_1000": round(len(concat_shared) / max(mean_words, 1) * 1000, 2),
        "per_node_shared": len(node_shared),
        "per_node_per_1000": round(len(node_shared) / max(mean_words, 1) * 1000, 2),
        "shared_examples": [" ".join(g) for g in sorted(node_shared)[:12]],
        "menu_frames_shared": len(frames),
    }


def main() -> int:
    """Score the configured pairs and write a JSON report."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shell", required=True)
    ap.add_argument("--pair", action="append", required=True, metavar="NAME=A:B")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    shell = json.loads(Path(args.shell).read_text(encoding="utf-8"))
    report: dict[str, Any] = {"pairs": {}, "books": {}}
    for spec in args.pair:
        name, _, rest = spec.partition("=")
        a_path, _, b_path = rest.partition(":")
        a = json.loads(Path(a_path).read_text(encoding="utf-8"))
        b = json.loads(Path(b_path).read_text(encoding="utf-8"))
        report["pairs"][name] = pair_stats(a, b)
        report["books"][f"{name}:A"] = book_stats(a, shell)
        report["books"][f"{name}:B"] = book_stats(b, shell)

    Path(args.out).write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    for name, p in report["pairs"].items():
        print(
            f"{name:12s} concat {p['concat_per_1000']:6.2f}/1000  "
            f"per-node {p['per_node_per_1000']:6.2f}/1000  "
            f"frames {p['menu_frames_shared']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
