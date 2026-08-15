"""Automated same-adventure recognition protocol: prompt builder and schema.

The manual version of this protocol is the most-run instrument in the
diversity programme (blind rater reads book one, then book two in reading
order, calls the first position at which they are the same adventure; see
AL-170 and the obligation-variance spec section 9). It has never existed as a
runnable harness, so every use costs a hand-built prompt and the protocol
drifts between runs. This file freezes it.

Blinding: the rendered reading script contains only what a child sees. Node
ids are dropped (they are identical across sibling books by construction and
would leak the armature instantly); titles, bodies, choice labels, and ending
titles are kept, in a deterministic breadth-first reading order from
``start_node``.

Sequential commitment: the rater is instructed to read book two scene by
scene, committing a per-scene verdict before reading on, and never revising
an earlier verdict. This is a single-prompt approximation of a true
incremental reveal; a multi-turn reveal would be stronger and costs one call
per scene. The approximation is declared rather than hidden, and matches how
the manual protocol was actually run.

Known-answer validation, pre-registered before any rater runs:

- The three same-armature D-7c pairs (R-glossed, R-bare, R-notes, C vs D)
  must be called same-adventure with first-yes position at or before scene 5
  on at least two of three (the manual protocol's history lands at 2 to 4).
- One cross-skeleton control (a D-7c clocktower book against a W16
  school-garden book: different graph, band, and world) must NOT be called
  same-adventure.
- Keep the instrument iff both hold; otherwise record that the automated
  form is not yet a substitute for the manual one, and why.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any, cast

INSTRUCTIONS = """\
You are rating two branching storybooks written for a children's reading app.

Read Book One in full first. Then read Book Two scene by scene, in the order
given. For each Book Two scene, BEFORE reading any further, commit a verdict:
"is this the same adventure as Book One, re-skinned?" Once you commit "yes"
you may not revert it at a later scene; earlier verdicts are never revised.
Different settings, names, and objects do NOT by themselves make two books
different adventures; judge whether a child who read Book One would feel they
are living the same adventure again in Book Two: the same situations in the
same order, the same choices meaning the same things, the same shape of
story.

When you have finished, write a file named verdict.json in your working
directory, valid JSON, exactly this shape:

{
  "per_scene": ["no", "no", "yes", ...],
  "first_yes_position": 3,
  "same_adventure": "yes",
  "distinctness_1_to_5": 2,
  "strongest_signal": "one sentence naming what convinced you"
}

Rules: per_scene has one entry per Book Two scene, in order. If you never
commit yes, first_yes_position is null and same_adventure is "no".
distinctness_1_to_5: 5 means completely distinct adventures, 1 means the same
adventure re-skinned. Reply in chat with a single line: your same_adventure
verdict and first_yes_position.
"""


def reading_order(story: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic breadth-first reading order from start_node."""
    nodes = {
        str(n["id"]): cast("dict[str, Any]", n)
        for n in cast("list[dict[str, Any]]", story["nodes"])
    }
    seen: list[dict[str, Any]] = []
    queue: deque[str] = deque([str(story["start_node"])])
    visited: set[str] = set()
    while queue:
        nid = queue.popleft()
        if nid in visited or nid not in nodes:
            continue
        visited.add(nid)
        node = nodes[nid]
        seen.append(node)
        for choice in cast("list[dict[str, Any]]", node.get("choices") or []):
            queue.append(str(choice.get("target")))
    return seen


def render_script(story: dict[str, Any], label: str) -> str:
    """Render the child-visible reading script, node ids withheld."""
    out: list[str] = [f"# {label}: {story.get('title', 'Untitled')}", ""]
    for k, node in enumerate(reading_order(story), start=1):
        if node.get("is_ending"):
            ending = cast("dict[str, Any]", node.get("ending") or {})
            out.append(f"## Scene {k} (an ending: {ending.get('title', '')})")
        else:
            out.append(f"## Scene {k}")
        out.append(str(node.get("body", "")).strip())
        labels = [
            str(c.get("label", ""))
            for c in cast("list[dict[str, Any]]", node.get("choices") or [])
        ]
        if labels:
            out.append("Choices: " + " / ".join(labels))
        out.append("")
    return "\n".join(out)


def build_prompt(book_a: dict[str, Any], book_b: dict[str, Any]) -> str:
    """Assemble the full single-prompt protocol."""
    return (
        INSTRUCTIONS
        + "\n\n"
        + render_script(book_a, "BOOK ONE")
        + "\n\n"
        + render_script(book_b, "BOOK TWO")
    )


def main() -> int:
    """Write a rater prompt for one ordered pair of filled books."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("book_one")
    ap.add_argument("book_two")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    a = json.loads(Path(args.book_one).read_text(encoding="utf-8"))
    b = json.loads(Path(args.book_two).read_text(encoding="utf-8"))
    Path(args.out).write_text(build_prompt(a, b), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
