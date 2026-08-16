"""Emit schema-v2 copies of pre-v2 filled books, for harnesses that need valid ones.

Three books in ``out/`` predate Storybook schema v2 and are quarantined as strict
xfails in ``tests/unit/test_filled_story_corpus.py``. They fail
``Storybook.model_validate`` on three counts: they declare ``schema_version``
``"1.0"``, ``metadata.topology`` is absent, and each ending carries a free-text
``type`` where v2 wants a ``kind`` and a ``valence``.

That is a schema gap, not a prose one, and it is expensive here because two of
the three are the only *short* books in the catalogue that carry substantial
dialogue: `the-lost-mitten` at a 0.818 body-level share across 11 nodes and
`the-clocktower-cipher` at 1.000 across 26. Every other dialogue-carrying book
runs from 124 to 551 nodes. Without them, W7's `dialogue_flat` arm has exactly
one usable book and the `dialogue` criterion cannot get a verdict at all, which
is the question the whole detour exists to answer.

**Both backfills are derived, not chosen.** The topology comes from
``validator.topology.admissible_topologies``, the deterministic classifier the
gate itself uses for rule PL-18, so this asserts nothing the graph does not
already say; where the classifier admits more than one label the first in enum
order is written and the alternatives are reported. The valence and kind come
from a fixed table over the four ``type`` values the corpus actually uses.

**This writes copies and never touches the input.** The originals stay as they
are: migrating the tracked fixtures is a separate decision, since it would drop
three entries from ``_LEGACY_PRE_V2`` and that is a claim about the corpus rather
than a convenience for one harness.

Usage::

    uv run python scripts/normalize_pre_v2.py out/the-lost-mitten.filled.json \\
        --out out/w7/corpus
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import networkx as nx

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.storybook.models import Storybook  # noqa: E402
from cyo_adventure.validator.topology import admissible_topologies  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["normalize"]

# The four `type` values the pre-v2 books use, mapped to the (kind, valence)
# pair v2 splits them into. Deliberately exhaustive rather than defaulted: an
# unrecognised type should stop the run, because guessing a valence would put a
# content judgement into a file described as a mechanical copy.
_ENDING_TYPES: Final[dict[str, tuple[str, str]]] = {
    "completion": ("completion", "positive"),
    "good": ("success", "positive"),
    "neutral": ("completion", "neutral"),
    "failure": ("setback", "negative"),
    "death": ("death", "negative"),
}

# The oldest version this build implements. Written only after the structural
# backfills above, and only because `Storybook.model_validate` then agrees: the
# declaration is a claim about the document's shape, so it is made last and the
# validation in `main` is what substantiates it.
_TARGET_SCHEMA_VERSION: Final[str] = "2.0"


def _graph(doc: dict[str, Any]) -> nx.DiGraph[str]:
    """Return the choice graph of *doc*.

    Args:
        doc: A filled story document.

    Returns:
        Node ids as vertices, choices as directed edges.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        return graph
    for node in nodes:
        if not isinstance(node, dict):
            continue
        graph.add_node(str(node.get("id")))
    for node in nodes:
        if not isinstance(node, dict):
            continue
        choices = node.get("choices")
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if isinstance(choice, dict) and choice.get("target"):
                graph.add_edge(str(node.get("id")), str(choice.get("target")))
    return graph


def normalize(doc: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a schema-v2 copy of *doc* and a note of every derivation made.

    Args:
        doc: A pre-v2 filled story document.

    Returns:
        The copy, and one human-readable line per backfill, so a caller can put
        the derivations in its report rather than leaving them implicit in a
        file that now looks native.

    Raises:
        ValueError: If an ending carries a ``type`` outside ``_ENDING_TYPES``.
            Stopping is the point: a defaulted valence would be a content claim
            wearing a mechanical copy's clothes.
    """
    out = copy.deepcopy(doc)
    notes: list[str] = []

    if out.get("schema_version") != _TARGET_SCHEMA_VERSION:
        was = out.get("schema_version")
        out["schema_version"] = _TARGET_SCHEMA_VERSION
        notes.append(f"schema_version {was!r} -> {_TARGET_SCHEMA_VERSION!r}")

    metadata = out.get("metadata")
    if isinstance(metadata, dict) and "topology" not in metadata:
        admissible = sorted(t.value for t in admissible_topologies(_graph(out)))
        if not admissible:
            msg = "the choice graph admits no topology; refusing to invent one"
            raise ValueError(msg)
        metadata["topology"] = admissible[0]
        notes.append(
            f"metadata.topology derived as {admissible[0]!r}"
            + (f" (also admissible: {admissible[1:]})" if len(admissible) > 1 else "")
        )

    nodes = out.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            ending = node.get("ending")
            if not isinstance(ending, dict) or "type" not in ending:
                continue
            raw = str(ending.pop("type"))
            if raw not in _ENDING_TYPES:
                msg = f"unmapped ending type {raw!r} on node {node.get('id')!r}"
                raise ValueError(msg)
            kind, valence = _ENDING_TYPES[raw]
            ending.setdefault("kind", kind)
            ending.setdefault("valence", valence)
            notes.append(
                f"node {node.get('id')}: ending.type={raw!r} -> "
                f"kind={kind!r}, valence={valence!r}"
            )

    return out, notes


def main(argv: Sequence[str] | None = None) -> int:
    """Normalise each input book and report what was derived.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        ``0`` when every output validates, ``1`` otherwise. A copy that still
        does not validate is worse than no copy, because the caller asked for a
        valid document and would otherwise discover this mid-run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("books", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    failures = 0
    for path in args.books:
        doc = json.loads(path.read_text(encoding="utf-8"))
        normalized, notes = normalize(doc)
        try:
            Storybook.model_validate(normalized)
        except ValueError as exc:
            print(f"  FAIL {path.name}: still invalid: {exc}", file=sys.stderr)
            failures += 1
            continue
        target = args.out / path.name
        target.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
        print(f"  ok   {path.name} -> {target}")
        for note in notes:
            print(f"         {note}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
