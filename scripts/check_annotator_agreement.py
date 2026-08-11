"""Measure inter-annotator agreement on decision signatures.

Usage:
    uv run python scripts/check_annotator_agreement.py <labels.json> <labels.json>
        [<labels.json>...] [--min-kappa 0.6] [--check]

The precondition for trusting any signature-derived diversity metric, and a
precondition this project learned the hard way.

Decision signatures (`action_family`, `target_role`, `tradeoff`,
`consequence`) are assigned by an annotator reading a story's choices. Every
metric built on them inherits that annotator's judgment. When the labelling
convention is left implicit, two annotators acting in complete good faith can
disagree across the metric's entire range: the same two contracts scored
tradeoff reuse of 0.179 and 1.000 depending only on who assigned the labels
(AL-188). The lower figure came from the party being measured, which is a
second and separate defect, but even two disinterested annotators are
worthless to a threshold if their agreement is unknown.

So: before a signature-derived score routes anything, its fields must clear an
agreement floor, and fields that do not clear it may be reported as diagnostics
but must carry zero decision weight.

Computes Fleiss' kappa per field over the items every annotator labelled.
Kappa corrects for agreement expected by chance, which matters here because
the vocabularies are small: four annotators guessing at random among seven
tradeoff values would still agree often enough to look meaningful raw.

Interpretation follows the conventional Landis and Koch bands. The default
floor of 0.6 ("substantial") is the usual bar for a measure that drives a
decision; below it the field is a hint, not a measurement.

Input files are shaped as the annotation schema::

    {"n_start": {"c_examine": {"action_family": "INFORMATION", ...}}}

Items absent from any annotator's file are skipped, and the number skipped is
reported, because silently narrowing the item set inflates agreement.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

_FIELDS = ("action_family", "target_role", "tradeoff", "consequence")
_MIN_KAPPA = 0.6
_MIN_ANNOTATORS = 2


def _bands(kappa: float) -> str:
    """Return the conventional Landis and Koch label for a kappa value."""
    if kappa < 0:
        return "poor"
    if kappa <= 0.20:
        return "slight"
    if kappa <= 0.40:
        return "fair"
    if kappa <= 0.60:
        return "moderate"
    if kappa <= 0.80:
        return "substantial"
    return "almost perfect"


def _items(labels: dict[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    """Flatten a label file to {(node, choice): signature}."""
    out: dict[tuple[str, str], dict[str, str]] = {}
    for node_id, block in labels.items():
        if not isinstance(block, dict):
            continue
        for choice_id, sig in cast("dict[str, Any]", block).items():
            if isinstance(sig, dict):
                out[(str(node_id), str(choice_id))] = {
                    str(k): str(v) for k, v in cast("dict[str, Any]", sig).items()
                }
    return out


def fleiss_kappa(assignments: list[list[str]]) -> float:
    """Return Fleiss' kappa for one field.

    Args:
        assignments: One list per item, holding each annotator's category.

    Returns:
        Kappa in [-1, 1]. Returns 1.0 when every annotator agrees on every
        item, which is the degenerate but legitimate perfect case.
    """
    if not assignments:
        return 0.0
    n_raters = len(assignments[0])
    if n_raters < _MIN_ANNOTATORS:
        return 0.0
    categories = sorted({c for row in assignments for c in row})
    n_items = len(assignments)

    # Per-item agreement, then the mean.
    p_i: list[float] = []
    for row in assignments:
        counts = Counter(row)
        total = sum(n * (n - 1) for n in counts.values())
        p_i.append(total / (n_raters * (n_raters - 1)))
    p_bar = sum(p_i) / n_items

    # Chance agreement from the marginal category distribution.
    marginals = Counter(c for row in assignments for c in row)
    p_e = sum((marginals[c] / (n_items * n_raters)) ** 2 for c in categories)

    if p_e >= 1.0:
        # Every annotator used exactly one category everywhere. Agreement is
        # total but chance-corrected kappa is undefined; report the honest
        # perfect-agreement value rather than a divide-by-zero.
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 unless --check and a field is below floor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", nargs="+", help="Two or more annotators' labels.")
    parser.add_argument("--min-kappa", type=float, default=_MIN_KAPPA)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if len(args.labels) < _MIN_ANNOTATORS:
        sys.stderr.write("need at least two annotators\n")
        return 2

    sets = [
        _items(cast("dict[str, Any]", json.loads(Path(p).read_text(encoding="utf-8"))))
        for p in args.labels
    ]
    shared = sorted(set.intersection(*(set(s) for s in sets)))
    dropped = max(len(s) for s in sets) - len(shared)
    if not shared:
        sys.stderr.write("no item was labelled by every annotator\n")
        return 2

    sys.stdout.write(
        f"annotators {len(sets)}, items compared {len(shared)}, "
        f"items dropped as not labelled by all {dropped}\n"
    )

    below: list[str] = []
    for field in _FIELDS:
        rows = [[s[item].get(field, "") for s in sets] for item in shared]
        if all(all(v == "" for v in row) for row in rows):
            sys.stdout.write(f"{field:16s}    not annotated, skipped\n")
            continue
        kappa = fleiss_kappa(rows)
        raw = sum(1 for row in rows if len(set(row)) == 1) / len(rows)
        flag = "" if kappa >= args.min_kappa else "   BELOW FLOOR"
        sys.stdout.write(
            f"{field:16s} kappa {kappa:6.3f}  ({_bands(kappa)}), "
            f"raw agreement {raw:.3f}{flag}\n"
        )
        if kappa < args.min_kappa:
            below.append(field)

    for field in below:
        sys.stderr.write(
            f"FAIL {field}: kappa below {args.min_kappa}, so any metric derived "
            f"from it must carry zero decision weight until the labelling "
            f"convention is tightened\n"
        )
    sys.stdout.write(
        f"{'FAIL' if below else 'ok  '}: {len(below)} field(s) below the floor\n"
    )
    return 1 if (below and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
