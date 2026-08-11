#!/usr/bin/env python3
"""D-3: does the v2 vocabulary agree with readers where v1 inverted them?

plan_three = contract_v2 (control base, filled_C)
plan_one   = contract_v3 (control,      filled_D)
plan_two   = contract_v5 (treatment,    filled_V5c)

Readers, twice, in opposite orders: the CONTROL pair (three vs one) is the MORE
decision-repetitive one. v1 said the opposite on every axis. A v2 field passes
only if its control-pair reuse is HIGHER than its treatment-pair reuse.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIELDS = ("action_family", "reasoning_kind", "target_role", "tradeoff", "consequence", "stake")
MIN_FORK_OPTIONS = 2


def forks(plan):
    """Node ids offering a real choice, single-option page turns excluded."""
    return {
        nid: list(node["choice_semantics"])
        for nid, node in plan["nodes"].items()
        if len(node.get("choice_semantics") or {}) >= MIN_FORK_OPTIONS
    }


def reuse(labels_a, labels_b, keys, field):
    """Share of fork options carrying the same value for `field` in both books."""
    same = sum(
        1
        for nid, cid in keys
        if labels_a.get(nid, {}).get(cid, {}).get(field)
        == labels_b.get(nid, {}).get(cid, {}).get(field)
    )
    return same / len(keys)


def main(tag):
    plans = {n: json.loads((HERE / f"plan_{n}.json").read_text(encoding="utf-8"))
             for n in ("one", "two", "three")}
    labels = {n: json.loads((HERE / f"v3_{tag}_{n}.json").read_text(encoding="utf-8"))
              for n in ("one", "two", "three")}

    keys = [(nid, cid) for nid, cids in forks(plans["three"]).items() for cid in cids]
    print(f"annotator {tag}: {len(forks(plans['three']))} forks, {len(keys)} options\n")

    print(f"{'field':16s} {'control pair':>13s} {'treatment pair':>15s}   verdict")
    print("-" * 62)
    agree = 0
    for field in FIELDS:
        c = reuse(labels["three"], labels["one"], keys, field)
        t = reuse(labels["three"], labels["two"], keys, field)
        if c > t:
            verdict, ok = "agrees with readers", True
        elif c == t:
            verdict, ok = "no signal (tied)", False
        else:
            verdict, ok = "INVERTS", False
        agree += ok
        print(f"{field:16s} {c:13.3f} {t:15.3f}   {verdict}")
    print(f"\n{agree} of {len(FIELDS)} fields order the two pairs the way readers did")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "A"))
