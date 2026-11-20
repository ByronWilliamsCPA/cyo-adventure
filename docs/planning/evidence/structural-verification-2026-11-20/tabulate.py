"""Print the side-by-side Markdown tables the findings document quotes.

Usage::

    python docs/planning/evidence/structural-verification-2026-11-20/tabulate.py \
        docs/planning/evidence/structural-verification-2026-11-20/metrics/*.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROWS: list[tuple[str, str]] = [
    ("served model(s)", "served_models"),
    ("status / repairs", "status"),
    ("gate blocked", "gate.blocked"),
    ("state contract exact (raw reply)", "raw_first_reply_state.exact"),
    ("state contract exact (delivered)", "delivered_state.exact"),
    ("merge nodes", "prose_craft.merge_nodes"),
    ("merge seams", "prose_craft.merge_seams"),
    ("option recaps", "prose_craft.option_recaps"),
    ("second-person labels", "prose_craft.second_person_labels"),
    ("meta / jargon labels", "labels"),
    ("give-up endings", "prose_craft.give_up_endings"),
    ("early setbacks", "prose_craft.early_setbacks"),
    ("dialogue share", "dialogue.share"),
    ("nodes with dialogue", "dialogue.nodes_with_dialogue"),
    ("moral-tag nodes", "prose_craft.moral_tag_nodes"),
    ("told emotion / 1000", "prose_craft.told_emotion_per_1000"),
    ("words delivered / commissioned", "words"),
    ("story fill rate", "words.story_fill_rate"),
    ("calls", "calls"),
    ("tokens in / out", "tokens"),
    ("est. cost USD", "estimated_cost_usd"),
    ("wall clock s", "elapsed_s"),
]


def _get(d: dict[str, object], dotted: str) -> object:
    if dotted == "status":
        return f"{d.get('status')} / {d.get('attempts')}"
    if dotted == "labels":
        pc = d.get("prose_craft") or {}
        assert isinstance(pc, dict)
        return f"{_n(pc.get('meta_labels'))} / {_n(pc.get('jargon_labels'))}"
    if dotted == "words":
        w = d.get("words") or {}
        assert isinstance(w, dict)
        return f"{w.get('delivered')} / {w.get('commissioned')}"
    if dotted == "tokens":
        return f"{d.get('input_tokens')} / {d.get('output_tokens')}"
    cur: object = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return "n/a"
        cur = cur.get(part)
    if isinstance(cur, list):
        if dotted == "served_models":
            return ", ".join(str(x).split("/")[-1] for x in cur)
        return len(cur)
    return "n/a" if cur is None else cur


def _n(v: object) -> object:
    return len(v) if isinstance(v, list) else v


def main() -> int:
    runs = [json.loads(Path(p).read_text("utf-8")) for p in sys.argv[1:]]
    labels = [r["label"] for r in runs]
    print("| metric | " + " | ".join(labels) + " |")
    print("| --- | " + " | ".join("---" for _ in labels) + " |")
    for title, key in ROWS:
        print(f"| {title} | " + " | ".join(str(_get(r, key)) for r in runs) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
