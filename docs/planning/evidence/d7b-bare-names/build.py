"""Build D-7b: strip the fact glosses, and measure what D-7 could only estimate.

D-7 shared a "wordless" structural stratum and generated the decisional stratum
per book. It landed at 13.6 shared 4-grams per 1000 against a budget of 4.0,
exactly where D-6's `diverge` condition landed, and **62 percent of its shared
grams trace to the one prose the stratum still carried: the fact definitions.**
(Both figures read 12.9 when this file was written; both were re-derived on
2026-08-11, having been published as body-only while actually label-inclusive.
They still coincide after the correction, so the sentence above holds as written
rather than by luck.)
Thirty-two one-line glosses, one per fact, read by both authors: "the clocktower
stands sealed, and the seal reads like a test rather than an accident".

Removing them and leaving bare fact names would, on a linear reading of that
trace, land near 4.8. That is an estimate, and estimates in this line have been
wrong twice, so it is measured here instead.

**The change is exactly one thing.** `facts` becomes a list of names with no
glosses. Everything else is identical to D-7: same graph, same bindings, same
per-node obligations, same `function` and `tier`, same device categories, same
safety envelope. Two decisional strata authored from it by agents that see
neither each other nor D-7's strata, then two fills.

**Prediction, fixed before any artifact exists:** at or under 4.8, and the
question that matters is whether it clears the budget of 4.0.

**Two falsifiers, because there are two ways this can fail.**

1. *It does not clear budget.* Then no shareable plan exists at any level of
   wordlessness we can construct, because there is nothing left to strip: what
   remains after this is topology and fact names, and a name is the minimum an
   obligation can be stated in.
2. *It clears budget but the books stop honouring the structure.* A bare name
   like `keeper_offer_earned` has to be interpreted, and two authors may
   interpret it differently. That is a real cost and it is measured here rather
   than assumed away: both fills are checked for fact-closure coherence against
   the shared structure, and a pass on convergence bought with a failure on
   fidelity is not a pass.

The second is the interesting one. If it fires, the finding is that a plan can
be made shareable only by making it too vague to bind two authors to the same
story, which is a different and more fundamental limit than the gram budget.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).parent
SRC = HERE.parent / "d7-stratified-plan"


def strip_glosses(stratum: dict[str, Any]) -> dict[str, Any]:
    """Return the stratum with fact definitions replaced by bare names.

    Args:
        stratum: The D-7 structural stratum, whose `facts` maps name to gloss.

    Returns:
        A copy whose `facts` is a sorted list of names and nothing else.
    """
    out = json.loads(json.dumps(stratum))
    out["facts"] = sorted(cast("dict[str, str]", stratum["facts"]))
    out["stratum"] = "structural-bare"
    return out


def main() -> int:
    """Write the gloss-free structural stratum and confirm nothing else moved."""
    full = cast(
        "dict[str, Any]",
        json.loads((SRC / "structural.json").read_text(encoding="utf-8")),
    )
    bare = strip_glosses(full)
    (HERE / "structural_bare.json").write_text(
        json.dumps(bare, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    # Everything except `facts` and the stratum label must be byte-identical,
    # so that any difference in the fills is attributable to the glosses alone.
    moved = [
        k
        for k in set(full) | set(bare)
        if k not in ("facts", "stratum")
        and json.dumps(full.get(k), sort_keys=True)
        != json.dumps(bare.get(k), sort_keys=True)
    ]
    print(f"facts: {len(full['facts'])} glosses -> {len(bare['facts'])} bare names")
    print(f"  e.g. {full['facts']['tower_sealed'][:64]!r}")
    print(f"    -> {bare['facts'][bare['facts'].index('tower_sealed')]!r}")
    print(f"  every other top-level key unchanged: {not moved}  {moved or ''}")
    gloss_words = sum(len(v.split()) for v in full["facts"].values())
    print(f"  prose removed from the shared artifact: {gloss_words} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
