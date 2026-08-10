"""Prepare storybooks for blind rating by stripping everything but the reading.

Usage:
    uv run python scripts/blind_books.py <out_dir> <name>=<filled.json> ...

**Written because hand-blinding failed twice, both times the same way.** A
rating round renames the files and hands them over, and something inside the
file still says where it came from. In the round that prompted this, two books
carried ``"id": "sk_clocktower_cipher"`` while the third carried ``"id":
"d6"``; a blind rater found it unaided and reported it as "the single most
concrete signal in the whole set", noting it traced two of the three books to
one origin (`AL-226`). Earlier, a shell `id` leaked a book title into three
arms that were supposed to have their own (`AL-207`).

**The rule this encodes: a rater may see only what a child would see.** That is
node bodies, choice labels, the book title, and ending titles. Everything else
is provenance, and provenance is exactly what a careful rater will notice and
use, because noticing things is the job.

So every book is rebuilt from scratch here rather than edited: node ids and
choice ids are rewritten to a per-book scheme, `id` and `version` are replaced
with the blind code, and any top-level key that is not needed to read the story
is dropped. Structure is preserved exactly, since the graph shape is the series
contract and rating depends on being able to follow it.

**Node ids are renamed per book, and that deserves a word**, because it costs
something real. Shared node ids let a rater line two books up node by node,
which is genuinely useful for judging whether decisions repeat. It also tells
them the books came off one skeleton, which is the leak. The leak wins: a rater
who can see the books share a skeleton will grade the pair that shares it more
harshly, and that pair is usually the one under test. Renaming preserves the
comparison a reader can actually make, which is following each book through and
noticing what they were asked to decide.

**What this cannot do.** It cannot blind prose. If two books share a world,
share a cast, or share a distinctive label template, a rater will see that and
should. This removes only what a reader would never have access to.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

# Everything a child sees, and nothing else. Anything not listed is dropped.
_KEEP_TOP = ("schema_version", "title", "start_node", "nodes")
_KEEP_NODE = ("id", "body", "is_ending", "choices", "ending")
_KEEP_CHOICE = ("id", "label", "target")
_KEEP_ENDING = ("title",)


def blind(story: dict[str, Any], code: str) -> dict[str, Any]:
    """Return a copy of one book carrying only what a reader would see.

    Args:
        story: The decoded filled storybook.
        code: The blind code for this book, used to build opaque node ids.

    Returns:
        A rebuilt storybook with provenance removed and ids renamed.
    """
    nodes = cast("list[dict[str, Any]]", story.get("nodes") or [])
    # Renamed in traversal-independent file order, so the mapping cannot itself
    # encode which book is which.
    rename = {str(n["id"]): f"{code}_{i:03d}" for i, n in enumerate(nodes)}

    out_nodes: list[dict[str, Any]] = []
    for i, node in enumerate(nodes):
        fresh: dict[str, Any] = {"id": rename[str(node["id"])]}
        for key in _KEEP_NODE:
            if key in ("id", "choices", "ending") or key not in node:
                continue
            fresh[key] = node[key]
        choices: list[dict[str, Any]] = []
        for j, choice in enumerate(
            cast("list[dict[str, Any]]", node.get("choices") or [])
        ):
            kept = {k: choice[k] for k in _KEEP_CHOICE if k in choice}
            kept["id"] = f"{code}_{i:03d}_c{j}"
            if "target" in kept:
                kept["target"] = rename.get(str(kept["target"]), str(kept["target"]))
            choices.append(kept)
        if choices:
            fresh["choices"] = choices
        ending = cast("dict[str, Any] | None", node.get("ending"))
        if ending is not None:
            fresh["ending"] = {k: ending[k] for k in _KEEP_ENDING if k in ending}
        out_nodes.append(fresh)

    blinded: dict[str, Any] = {
        k: story[k] for k in _KEEP_TOP if k in story and k != "nodes"
    }
    blinded["start_node"] = rename.get(
        str(story.get("start_node") or ""), str(story.get("start_node") or "")
    )
    blinded["nodes"] = out_nodes
    return blinded


def leaks(blinded: dict[str, Any], originals: list[dict[str, Any]]) -> list[str]:
    """Return any value in the blinded book that also identifies an original.

    A self-check rather than a promise: it catches the class of leak that has
    actually happened twice, a shared identifier surviving into the handout.

    Args:
        blinded: One blinded book.
        originals: Every original book in the round.

    Returns:
        Human-readable descriptions of surviving identifiers.
    """
    blob = json.dumps(blinded)
    found: list[str] = []
    for original in originals:
        for key in ("id", "version"):
            value = original.get(key)
            if isinstance(value, str) and len(value) > 3 and value in blob:
                found.append(f"original {key} {value!r} survives in the handout")
    return found


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 if any provenance survived blinding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", help="Directory to write blinded books into.")
    parser.add_argument(
        "books",
        nargs="+",
        metavar="CODE=PATH",
        help="Blind code and source path, e.g. alpha=docs/.../filled_C.json",
    )
    args = parser.parse_args(argv)

    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    pairs: list[tuple[str, dict[str, Any]]] = []
    for spec in args.books:
        if "=" not in spec:
            sys.stderr.write(f"expected CODE=PATH, got {spec!r}\n")
            return 2
        code, path = spec.split("=", 1)
        pairs.append(
            (
                code,
                cast(
                    "dict[str, Any]",
                    json.loads(Path(path).resolve().read_text(encoding="utf-8")),
                ),
            )
        )

    originals = [story for _, story in pairs]
    failed = False
    for code, story in pairs:
        blinded = blind(story, code)
        surviving = leaks(blinded, originals)
        (out / f"{code}.json").write_text(
            json.dumps(blinded, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        sys.stdout.write(
            f"{code:10s} {len(cast('list[Any]', blinded['nodes'])):4d} nodes  "
            f"{'LEAK: ' + '; '.join(surviving) if surviving else 'clean'}\n"
        )
        failed = failed or bool(surviving)

    sys.stdout.write(f"\nwrote {len(pairs)} blinded book(s) to {out}\n")
    if failed:
        sys.stderr.write("FAIL: provenance survived blinding\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
