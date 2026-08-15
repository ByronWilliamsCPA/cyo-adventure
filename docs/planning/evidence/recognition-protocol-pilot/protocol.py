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

An earlier version rendered ending scenes as ``## Scene 7 (an ending: ...)``.
``an ending`` is the graph's own ``is_ending`` flag, not child-visible text,
and sibling books share their topology by construction, so that heading told
a rater "both books end at scene 7" in the renderer's voice rather than the
prose's. The classification is gone; the ending title, which a child does
see, is kept. Residual, declared rather than hidden: an ending scene is the
only kind that carries a title suffix, so topology is still weakly inferable
from the shape of the headings. Removing ending titles entirely would blind
the rater to real child-visible text, so the weaker leak is the one kept.

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
  "per_scene": ["no", "no", "yes", "yes"],
  "first_yes_position": 3,
  "same_adventure": "yes",
  "distinctness_1_to_5": 2,
  "strongest_signal": "one sentence naming what convinced you"
}

The example above is a complete, valid four-scene verdict; your per_scene
array must have one entry per Book Two scene, not four.

Rules: per_scene has one entry per Book Two scene, in order, and every entry
is exactly "yes" or "no". Once an entry is "yes", every later entry is "yes"
(verdicts are never revised). first_yes_position is the 1-based position of
the first "yes". If you never commit yes, first_yes_position is null and
same_adventure is "no"; otherwise same_adventure is "yes".
distinctness_1_to_5: 5 means completely distinct adventures, 1 means the same
adventure re-skinned. Reply in chat with a single line: your same_adventure
verdict and first_yes_position.
"""


def reading_order(story: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic breadth-first reading order from start_node.

    Raises on an unresolvable ``start_node`` or ``choice.target`` rather than
    skipping it. Silently dropping an unknown reference shortens the rendered
    script, and the rater is told to return one verdict per scene, so a
    dangling edge would yield a verdict file that looks well-formed and is
    quietly measuring a smaller book. The upstream graph contract already
    treats a dangling target as a structural failure.
    """
    nodes = {
        str(n["id"]): cast("dict[str, Any]", n)
        for n in cast("list[dict[str, Any]]", story["nodes"])
    }
    start = str(story["start_node"])
    if start not in nodes:
        msg = f"start_node {start!r} is not present in nodes"
        raise ValueError(msg)

    seen: list[dict[str, Any]] = []
    queue: deque[str] = deque([start])
    visited: set[str] = set()
    while queue:
        nid = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes[nid]
        seen.append(node)
        for choice in cast("list[dict[str, Any]]", node.get("choices") or []):
            target = str(choice.get("target"))
            if target not in nodes:
                msg = (
                    f"choice target {target!r} on node {nid!r} is not present "
                    "in nodes; the graph is structurally invalid"
                )
                raise ValueError(msg)
            queue.append(target)
    return seen


def render_script(story: dict[str, Any], label: str) -> str:
    """Render the child-visible reading script, node ids withheld."""
    out: list[str] = [f"# {label}: {story.get('title', 'Untitled')}", ""]
    for k, node in enumerate(reading_order(story), start=1):
        ending = cast("dict[str, Any]", node.get("ending") or {})
        ending_title = str(ending.get("title", "")).strip() if node.get("is_ending") else ""
        # The ending TITLE is child-visible and is kept; the "an ending"
        # classification is graph metadata and is not rendered. See the module
        # docstring for the residual signal this still leaves.
        out.append(f"## Scene {k}: {ending_title}" if ending_title else f"## Scene {k}")
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


def validate_verdict(verdict: dict[str, Any], scene_count: int) -> list[str]:
    """Check one rater verdict against the pre-registered contract.

    Returns a list of human-readable violations; empty means well-formed. The
    protocol pre-registers these rules but nothing enforced them, so a verdict
    that silently broke one (a short ``per_scene``, a "yes" that later reverts
    to "no", a ``first_yes_position`` disagreeing with the array) could have
    been recorded as a validation outcome. A verdict that fails here is not
    softened into a caveat; it is a failed run of the instrument.
    """
    errors: list[str] = []

    per_scene = verdict.get("per_scene")
    if not isinstance(per_scene, list):
        errors.append("per_scene must be a list")
        return errors

    if len(per_scene) != scene_count:
        errors.append(
            f"per_scene has {len(per_scene)} entries, expected one per Book Two "
            f"scene ({scene_count})"
        )

    bad = [(i, v) for i, v in enumerate(per_scene, start=1) if v not in ("yes", "no")]
    if bad:
        errors.append(
            "per_scene entries must be exactly 'yes' or 'no'; offending "
            f"positions: {[i for i, _ in bad]}"
        )
        return errors

    # Sequential commitment: once "yes", never back to "no".
    reverted = [i for i, v in enumerate(per_scene, start=1) if v == "no" and "yes" in per_scene[: i - 1]]
    if reverted:
        errors.append(
            f"verdicts are never revised, but 'no' follows a 'yes' at positions {reverted}"
        )

    observed = next((i for i, v in enumerate(per_scene, start=1) if v == "yes"), None)
    declared = verdict.get("first_yes_position")
    if declared != observed:
        errors.append(
            f"first_yes_position is {declared!r} but the first 'yes' in per_scene "
            f"is at {observed!r}"
        )

    expected_same = "no" if observed is None else "yes"
    if verdict.get("same_adventure") != expected_same:
        errors.append(
            f"same_adventure is {verdict.get('same_adventure')!r} but per_scene "
            f"implies {expected_same!r}"
        )

    distinctness = verdict.get("distinctness_1_to_5")
    if not isinstance(distinctness, int) or not 1 <= distinctness <= 5:
        errors.append("distinctness_1_to_5 must be an integer from 1 to 5")

    if not str(verdict.get("strongest_signal", "")).strip():
        errors.append("strongest_signal must be a non-empty sentence")

    return errors


def main() -> int:
    """Build a rater prompt, or validate a returned verdict."""
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="write a rater prompt for one book pair")
    build.add_argument("book_one")
    build.add_argument("book_two")
    build.add_argument("--out", required=True)

    check = sub.add_parser("validate", help="check a verdict against the contract")
    check.add_argument("verdict")
    check.add_argument(
        "--book-two",
        required=True,
        help="the Book Two used for this verdict; fixes the expected scene count",
    )

    args = ap.parse_args()

    if args.command == "build":
        a = json.loads(Path(args.book_one).read_text(encoding="utf-8"))
        b = json.loads(Path(args.book_two).read_text(encoding="utf-8"))
        Path(args.out).write_text(build_prompt(a, b), encoding="utf-8")
        print(f"wrote {args.out}")
        return 0

    verdict = json.loads(Path(args.verdict).read_text(encoding="utf-8"))
    book_two = json.loads(Path(args.book_two).read_text(encoding="utf-8"))
    errors = validate_verdict(verdict, len(reading_order(book_two)))
    if errors:
        print(f"INVALID: {args.verdict}")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"ok: {args.verdict} satisfies the pre-registered verdict contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
