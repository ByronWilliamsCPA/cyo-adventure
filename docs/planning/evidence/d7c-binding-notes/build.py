"""Build D-7c: keep the fact glosses, delete every other word of shared free text.

The 16l correction block names this "the highest-value single experiment we can
currently run". D-7's kernel was published as wordless and still carried two
prose loads: the 32 fact glosses (422 words, deleted by D-7b, convergence fell
13.6 to 2.3 per 1000) and 473 further words nobody had counted: the binding
notes inside `world_recipe`, the per-node `invention` notes, the eight
`title_contract` entries, and the `affect_ceiling` sentence. D-7b deleted the
glosses and KEPT the 473, so the pair of runs cannot say which text class did
the work, only that the glosses were sufficient to remove. The strict re-trace
in section 21 found only 5 of the failing arm's 40 shared grams were copied
from the glosses, so the mechanism is convergent elaboration, and an elaboration
mechanism could in principle elaborate from the binding notes just as well.

**The change is exactly one thing, mirrored from D-7b.** Starting from D-7's
`structural.json` (glosses present), delete the non-gloss free text:

- every `note` key under `world_recipe` (the binding notes),
- every `note` key inside per-node `invention` entries (the invention notes),
- `title_contract` on all eight ending nodes (the title constraints),
- `safety_envelope.affect_ceiling` (the affect ceiling sentence).

`facts` keeps its glosses byte-identically. Formal machinery stays: category
kind lists, counts, pick/from/unique_within_story, forbid lists.

**Design.** Because the original fills were authored by a different model
generation in a different session, D-7c re-baselines all three kernels with the
same author model and the same protocol in one session: R-glossed (D-7 kernel),
R-bare (D-7b kernel), R-notes (this kernel). Two isolated authors per arm, arm
bindings held to the pilot's own two shells, single-pass fills, no revision
round. Authors see their kernel, their shell, and a fixed instruction file that
is byte-identical across arms; they never see a sibling artifact or another
arm. The measure is `scripts/check_sibling_fills.py`, bodies only, the project
metric unchanged.

**Prediction, fixed before any artifact exists.** The section 21 trace supports
gloss-driven convergence: R-notes lands nearer R-glossed than R-bare.
Operationally, with M the midpoint of the two re-baselines: R-notes >= M.

**Falsifiers, fixed before any artifact exists.**

1. R-notes at or below 1.5x R-bare: the gloss attribution is wrong, total
   free-text volume or re-read frequency is the operative variable, and the
   16l restated rule ("free text attached to the fact vocabulary drove
   convergence") needs re-deriving rather than defending.
2. R-glossed and R-bare re-baselines fail to reproduce the historical ORDER
   (glossed materially above bare): then no cell of this run is interpretable
   against the 13.6 / 2.3 anchors, and the run reports instead as a failed
   cross-generation replication of 16l, which is itself a result the brief
   says it needs (its single-family figures are flagged non-portable).

**Guards, not success criteria.** Fill integrity against the shell, the full
story gate, menu-frame overlap, prose-craft checks, an em-dash scan, and a
title-drift report for R-notes (whose kernel deletes the only title-length
constraint; drift there is a finding about constraint text, not a defect).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).parent
SRC = HERE.parent / "d7-stratified-plan"


def _words(x: Any) -> int:
    """Count whitespace-separated words in every string under x."""
    if isinstance(x, str):
        return len(x.split())
    if isinstance(x, list):
        return sum(_words(i) for i in cast("list[Any]", x))
    if isinstance(x, dict):
        return sum(_words(v) for v in cast("dict[str, Any]", x).values())
    return 0


def strip_binding_prose(stratum: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return (kernel with non-gloss free text removed, words removed).

    Args:
        stratum: The D-7 structural stratum, glosses present.

    Returns:
        The D-7c kernel and the exact word count deleted.
    """
    out = cast("dict[str, Any]", json.loads(json.dumps(stratum)))
    removed = 0

    def _strip_notes(obj: Any) -> None:
        nonlocal removed
        if isinstance(obj, dict):
            d = cast("dict[str, Any]", obj)
            if "note" in d:
                removed += _words(d["note"])
                del d["note"]
            for v in d.values():
                _strip_notes(v)
        elif isinstance(obj, list):
            for v in cast("list[Any]", obj):
                _strip_notes(v)

    _strip_notes(out["world_recipe"])
    for node in cast("dict[str, Any]", out["nodes"]).values():
        n = cast("dict[str, Any]", node)
        if "invention" in n:
            _strip_notes(n["invention"])
        if "title_contract" in n:
            removed += _words(n["title_contract"])
            del n["title_contract"]
    env = cast("dict[str, Any]", out["safety_envelope"])
    if "affect_ceiling" in env:
        removed += _words(env["affect_ceiling"])
        del env["affect_ceiling"]
    out["stratum"] = "structural-noteless"
    return out, removed


def main() -> int:
    """Write the D-7c kernel and report exactly what moved."""
    full = cast(
        "dict[str, Any]",
        json.loads((SRC / "structural.json").read_text(encoding="utf-8")),
    )
    kernel, removed = strip_binding_prose(full)
    (HERE / "kernel_notes.json").write_text(
        json.dumps(kernel, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    gloss_words = _words(full["facts"])
    same_facts = json.dumps(full["facts"], sort_keys=True) == json.dumps(
        kernel["facts"], sort_keys=True
    )
    moved = [
        k
        for k in set(full) | set(kernel)
        if k not in ("stratum",)
        and json.dumps(full.get(k), sort_keys=True)
        != json.dumps(kernel.get(k), sort_keys=True)
    ]
    print(f"glosses kept intact: {same_facts} ({gloss_words} words)")
    print(f"free text removed  : {removed} words (16l counted 473)")
    print(f"keys that moved    : {sorted(moved)}")
    print(f"total words before : {_words(full)}  after: {_words(kernel)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
