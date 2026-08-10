"""Gate the admissibility of narrative-contract variants over one skeleton.

Usage:
    uv run python docs/planning/evidence/obligation-variance/check_variant_divergence.py \
        <contract.json> <contract.json> [<contract.json>...] [--check]

The obligation-variance experiment
(``docs/planning/obligation-variance-experiment-spec-2026-08-09.md``) varies
the one layer every prior pilot held constant: what each node is *for*. A
variant only counts as a variant if it changes the node's job rather than
its wording, so this script is the admissibility gate for section 4.

Two criteria, both enforced per node and per contract pair:

1. **Field divergence.** A node must differ in at least two of
   ``establishes``, ``choice_semantics``, ``affect``, and ``function``.
   Ending nodes carry no ``choice_semantics``, so the achievable maximum
   there is three, and the two-of-four bar still applies.
2. **Beat-hint divergence.** ``beat_hint`` similarity must stay below
   ``--max-hint-similarity`` (default 0.60, difflib ratio).

Criterion 2 exists because criterion 1 alone passed a contract set whose
``beat_hint`` strings were the shipped contract's sentences with single
nouns swapped: 22 of 26 nodes above 0.60 against v1, and one ending
byte-identical across all three variants (AL-182). ``beat_hint`` is the
most direct instruction a fill agent reads, so holding it constant leaves
the intervention largely undelivered and would make a null result
uninterpretable: "obligation variance does not work" could not be
separated from "the obligations were never varied."

With ``--check``, exits 1 when any pair breaches either criterion.
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import sys
from pathlib import Path
from typing import Any, cast

_FIELDS = ("establishes", "choice_semantics", "affect", "function")
_MIN_DIVERGENT_FIELDS = 2
_MAX_HINT_SIMILARITY = 0.60


def _norm(value: object) -> str | None:
    """Return an order-insensitive canonical form of a contract field.

    Args:
        value: The raw field value from a contract node.

    Returns:
        A canonical string, or None when the field is absent.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return json.dumps(sorted(json.dumps(item, sort_keys=True) for item in value))
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _hint_similarity(left: str, right: str) -> float:
    """Return the difflib ratio between two beat hints."""
    return difflib.SequenceMatcher(None, left, right).ratio()


def compare(
    contracts: dict[str, dict[str, Any]], *, max_hint_similarity: float
) -> tuple[list[str], list[str]]:
    """Compare every contract pair node by node.

    Args:
        contracts: Mapping of label to decoded contract JSON.
        max_hint_similarity: Exclusive upper bound on beat_hint similarity.

    Returns:
        A (errors, notes) pair; errors are admissibility breaches.
    """
    errors: list[str] = []
    notes: list[str] = []
    node_sets = {
        label: set(cast("dict[str, Any]", contract.get("nodes") or {}))
        for label, contract in contracts.items()
    }
    shared = set.intersection(*node_sets.values()) if node_sets else set()
    for label, ids in node_sets.items():
        if ids != shared:
            errors.append(
                f"{label}: node set differs from the shared set by "
                f"{sorted(ids.symmetric_difference(shared))}"
            )
    for left, right in itertools.combinations(sorted(contracts), 2):
        field_ok = 0
        hint_ok = 0
        worst_hint = 0.0
        for node_id in sorted(shared):
            a = cast("dict[str, Any]", contracts[left]["nodes"][node_id])
            b = cast("dict[str, Any]", contracts[right]["nodes"][node_id])
            divergent = [f for f in _FIELDS if _norm(a.get(f)) != _norm(b.get(f))]
            if len(divergent) >= _MIN_DIVERGENT_FIELDS:
                field_ok += 1
            else:
                errors.append(
                    f"{left} vs {right} [{node_id}]: only {len(divergent)} of "
                    f"{len(_FIELDS)} fields differ ({divergent or 'none'}); "
                    f"needs {_MIN_DIVERGENT_FIELDS}"
                )
            ratio = _hint_similarity(
                str(a.get("beat_hint") or ""), str(b.get("beat_hint") or "")
            )
            worst_hint = max(worst_hint, ratio)
            if ratio < max_hint_similarity:
                hint_ok += 1
            else:
                errors.append(
                    f"{left} vs {right} [{node_id}]: beat_hint similarity "
                    f"{ratio:.2f} >= {max_hint_similarity:.2f}; this is a "
                    f"paraphrase, not a variant"
                )
        notes.append(
            f"{left} vs {right}: fields {field_ok}/{len(shared)} pass, "
            f"beat_hints {hint_ok}/{len(shared)} pass "
            f"(worst similarity {worst_hint:.2f})"
        )
    return errors, notes


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 when every pair is admissible."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contracts", nargs="+", help="Two or more contract JSONs.")
    parser.add_argument(
        "--max-hint-similarity",
        type=float,
        default=_MAX_HINT_SIMILARITY,
        help=(
            "Exclusive upper bound on beat_hint difflib ratio (default "
            "0.60; the rejected first draft scored 1.00 at n_end_library "
            "and >= 0.85 at 10 of 26 nodes against v1)."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if len(args.contracts) < 2:
        sys.stderr.write("need at least two contracts\n")
        return 2
    contracts = {
        Path(p).stem: cast(
            "dict[str, Any]", json.loads(Path(p).read_text(encoding="utf-8"))
        )
        for p in args.contracts
    }
    errors, notes = compare(contracts, max_hint_similarity=args.max_hint_similarity)
    for note in notes:
        sys.stdout.write(f"{note}\n")
    for error in errors:
        sys.stderr.write(f"FAIL {error}\n")
    sys.stdout.write(
        f"{'FAIL' if errors else 'ok  '}: {len(errors)} admissibility breach(es)\n"
    )
    return 1 if (errors and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
