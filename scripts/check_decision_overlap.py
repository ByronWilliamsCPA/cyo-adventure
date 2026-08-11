"""Score decision repetition between two books built from one skeleton.

Usage:
    uv run python scripts/check_decision_overlap.py <contract.json> <contract.json>
        [--max-exact 0] [--max-family-rate 0.6] [--check]

The instrument the diversity program has been missing. Every prior measure
scored either surface form (shared n-grams, lexical similarity) or whole-book
sameness ("does this read as the same book"), and the owner's definition is
neither: the defect is **close regurgitation of process**, the reader being
asked to make the same decisions in the same order. Shared world, cast, and
graph shape are the series contract and must not count against a book.

Two books may therefore be structurally identical and still pass. A fork
offering "open the door / go around back" in one book and "go upstairs /
go downstairs" in another is not a repeat, even at the same vertex with the
same downstream branches.

Reads the ``decisions`` block a contract declares per node::

    "decisions": {
      "c_examine": {
        "action": "decode_a_written_clue",
        "action_family": "INFORMATION",
        "target_role": "ARTIFACT",
        "tradeoff": "TIME_VS_CERTAINTY",
        "consequence": "KNOWLEDGE"
      }
    }

Four separate scores, deliberately not collapsed into one. An external
review of this program (2026-08-10) argued that a single number cannot
distinguish "same act, new paint" from "different act, same underlying
decision", and that collapsing them early would repeat the mistake that
produced a perceived-similarity metric scoring 0.548 against 0.547 for
pairs a human separated instantly:

1. **Exact action reuse** at the same fork and position. The owner's bar,
   and the only hard failure. Budget 0.
2. **Action-family reuse** at the same fork. Graded, not fatal: a series may
   reasonably reuse "investigate" choices, and the series-fiction literature
   says the constant layer is load-bearing. Maximizing distinctness is the
   wrong target (Berlyne's inverted-U), so this is a ceiling and not a
   minimand.
3. **Tradeoff and consequence reuse**, which detects choices that differ in
   wording and family while still offering the same bargain.
4. **Ordered sequence reuse** along a canonical path, which detects a repeated
   decision *program* even when individual forks differ.

Options are aligned by choice id where ids match and by optimal bipartite
matching on the remaining ones, because two forks may offer two, three, or
four alternatives.

Worst-fork reporting (2026-08-10 external review): ``worst_fork_family_rate``
already exists and is gated separately from the ``action_family_rate`` mean
(see the #CRITICAL note on the 0.486-vs-0.67/0.75/0.75/1.00 measurement
below). Tradeoff and consequence reuse were still mean-only scores with no
worst-fork counterpart, so the same treatment is applied to both:
``worst_fork_tradeoff_rate`` and ``worst_fork_consequence_rate``, each
reported with the node id it came from and each gated via its own
``--max-worst-fork-*-rate`` flag, defaulted to the same 0.5 ceiling as
family on the grounds that a reader's first hard forks deserve the same
scrutiny regardless of which axis repeats.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import permutations
from pathlib import Path
from typing import Any, cast

_HARD_EXACT_BUDGET = 0
_FAMILY_RATE_CEILING = 0.6
_SEQUENCE_CEILING = 0.6
_WORST_FORK_CEILING = 0.5
_TRADEOFF_CEILING = 0.6
_WORST_FORK_TRADEOFF_CEILING = 0.5
_WORST_FORK_CONSEQUENCE_CEILING = 0.5


def _decisions(contract: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    """Return {node_id: {choice_id: signature}} for every declared decision."""
    out: dict[str, dict[str, dict[str, str]]] = {}
    nodes = cast("dict[str, Any]", contract.get("nodes") or {})
    for node_id, node in nodes.items():
        block = cast("dict[str, Any]", node.get("decisions") or {})
        sigs = {
            str(cid): {str(k): str(v) for k, v in cast("dict[str, Any]", sig).items()}
            for cid, sig in block.items()
            if isinstance(sig, dict)
        }
        # #CRITICAL: data-integrity: the hard bar must compare the DECISION, not
        # the nouns. Measured live: two contracts scored 0/35 identical `action`
        # strings while a blind annotator judged 34/35 the same decision, because
        # "set_the_dial_deliberately" and "set_the_levers_deliberately" differ as
        # strings and are the same act. A free-text field makes the owner's
        # "exact action repetition" bar vacuous, since the surface changing while
        # the decision does not IS the defect being measured.
        # #VERIFY: exact reuse is computed on the normalized act (family, target,
        # tradeoff); the raw string is retained for reporting only.
        for sig in sigs.values():
            sig["_normalized_act"] = "|".join(
                sig.get(k, "") for k in ("action_family", "target_role", "tradeoff")
            )
        if sigs:
            out[str(node_id)] = sigs
    return out


def _best_alignment(
    left: dict[str, dict[str, str]],
    right: dict[str, dict[str, str]],
    field: str,
) -> int:
    """Return the max number of matching ``field`` values over any pairing.

    Choice ids are shared when the skeleton is shared, so ids align directly.
    When they do not, fall back to the best bipartite matching, brute-forced
    because a fork carries at most four options by band rule.

    Args:
        left: Signatures for one book's fork, keyed by choice id.
        right: Signatures for the other book's fork.
        field: The signature field to compare.

    Returns:
        Count of positions whose ``field`` values are equal.
    """
    shared = set(left) & set(right)
    if shared and len(shared) == max(len(left), len(right)):
        return sum(1 for cid in shared if left[cid].get(field) == right[cid].get(field))
    lvals = [sig.get(field) for sig in left.values()]
    rvals = [sig.get(field) for sig in right.values()]
    if not lvals or not rvals:
        return 0
    if len(lvals) > len(rvals):
        lvals, rvals = rvals, lvals
    best = 0
    for perm in permutations(rvals, len(lvals)):
        best = max(best, sum(1 for a, b in zip(lvals, perm, strict=True) if a == b))
    return best


def compare(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[dict[str, float], list[str], dict[str, str]]:
    """Compare two contracts' decision programs.

    Args:
        left: One decoded contract.
        right: The other decoded contract.

    Returns:
        A (scores, notes, worst_nodes) triple. ``worst_nodes`` maps
        ``"family"``, ``"tradeoff"``, and ``"consequence"`` to the node id
        whose fork carried the highest reuse rate on that axis (empty
        string when no shared node exists), so the worst-fork scores are
        actionable rather than bare numbers.
    """
    a, b = _decisions(left), _decisions(right)
    # #CRITICAL: data-integrity: a node offering ONE option is not a decision, it
    # is a page turn. Counting them inflates the denominator with non-choices and
    # lets a mean pass while every real fork is unchanged. Measured live: a
    # contract pair scored 0.486 aggregate family overlap (inside a 0.6 ceiling)
    # while its three principal forks sat at 0.67, 0.75 and 0.75 and two forks sat
    # at 1.00, because six single-option nodes scoring 0.00 dragged the mean down.
    # Excluding them and weighting by option count puts the same pair at 0.615,
    # which fails. This is the third instance of a threshold hiding the thing it
    # was built to catch (see AL-182, AL-186).
    # #VERIFY: worst_fork_family_rate is reported and gated separately, so a mean
    # can never again pass on the strength of nodes that ask nothing of the reader.
    shared_nodes = sorted(n for n in set(a) & set(b) if len(a[n]) > 1 and len(b[n]) > 1)
    skipped = sorted((set(a) & set(b)) - set(shared_nodes))
    notes: list[str] = []
    if not shared_nodes:
        return (
            {},
            ["no node declares a multi-option decisions block in both contracts"],
            {},
        )
    if skipped:
        notes.append(
            f"  excluded {len(skipped)} single-option node(s), not decisions: "
            f"{', '.join(skipped)}"
        )

    total_options = 0
    exact = family = tradeoff = consequence = 0
    # #CRITICAL: data-integrity: worst_family/tradeoff/consequence must track
    # WHICH node produced the max, not only the value, or the worst-fork
    # score is unactionable (a bare number a reviewer cannot go open). An
    # earlier version of this file derived the node id after the fact by
    # regexing notes for the string "same action family", which silently
    # returned the FIRST matching node in shared_nodes order rather than the
    # actual argmax whenever two nodes tied or the true worst node's note
    # text did not match the search string (as would happen for tradeoff or
    # consequence, which never wrote that note at all).
    # #VERIFY: each worst_* value and its *_node id are updated together, in
    # the same branch, so they can never point at different nodes.
    worst_family = 0.0
    worst_family_node = ""
    worst_tradeoff = 0.0
    worst_tradeoff_node = ""
    worst_consequence = 0.0
    worst_consequence_node = ""
    for node_id in shared_nodes:
        la, lb = a[node_id], b[node_id]
        options = max(len(la), len(lb))
        total_options += options
        hits = _best_alignment(la, lb, "_normalized_act")
        exact += hits
        fam_hits = _best_alignment(la, lb, "action_family")
        family += fam_hits
        tradeoff_hits = _best_alignment(la, lb, "tradeoff")
        tradeoff += tradeoff_hits
        consequence_hits = _best_alignment(la, lb, "consequence")
        consequence += consequence_hits

        rate = fam_hits / float(options)
        if rate > worst_family:
            worst_family, worst_family_node = rate, node_id
        tradeoff_rate = tradeoff_hits / float(options)
        if tradeoff_rate > worst_tradeoff:
            worst_tradeoff, worst_tradeoff_node = tradeoff_rate, node_id
        consequence_rate = consequence_hits / float(options)
        if consequence_rate > worst_consequence:
            worst_consequence, worst_consequence_node = consequence_rate, node_id

        if hits:
            notes.append(
                f"  {node_id}: {hits} option(s) ask the same decision "
                f"(same family, target and tradeoff)"
            )
        if rate >= 0.5:
            notes.append(
                f"  {node_id}: {fam_hits}/{options} options keep the same action family "
                f"({rate:.2f})"
            )

    # Ordered sequence: the family of each fork, in node order, compared as a
    # multiset-free ordered signature. A repeated decision program shows up here
    # even when individual forks pass.
    seq_a = [
        sorted(sig.get("action_family", "") for sig in a[n].values())
        for n in shared_nodes
    ]
    seq_b = [
        sorted(sig.get("action_family", "") for sig in b[n].values())
        for n in shared_nodes
    ]
    seq_match = sum(1 for x, y in zip(seq_a, seq_b, strict=True) if x == y)

    denom = float(total_options or 1)
    return (
        {
            "forks_compared": float(len(shared_nodes)),
            "options_compared": float(total_options),
            "same_decision_reuse": float(exact),
            "action_family_rate": family / denom,
            "tradeoff_rate": tradeoff / denom,
            "consequence_rate": consequence / denom,
            "ordered_sequence_rate": seq_match / float(len(shared_nodes) or 1),
            "worst_fork_family_rate": worst_family,
            "worst_fork_tradeoff_rate": worst_tradeoff,
            "worst_fork_consequence_rate": worst_consequence,
        },
        notes,
        {
            "family": worst_family_node,
            "tradeoff": worst_tradeoff_node,
            "consequence": worst_consequence_node,
        },
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 unless --check and a budget is breached."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contracts", nargs=2, help="Two contracts to compare.")
    parser.add_argument("--max-exact", type=int, default=_HARD_EXACT_BUDGET)
    parser.add_argument("--max-family-rate", type=float, default=_FAMILY_RATE_CEILING)
    parser.add_argument("--max-sequence-rate", type=float, default=_SEQUENCE_CEILING)
    parser.add_argument(
        "--max-worst-fork-family-rate",
        type=float,
        default=_WORST_FORK_CEILING,
        help=(
            "Ceiling on the single most-unchanged fork. A mean cannot substitute: "
            "the forks a reader meets first are the ones that decide recognition."
        ),
    )
    parser.add_argument(
        "--max-tradeoff-rate",
        type=float,
        default=_TRADEOFF_CEILING,
        help=(
            "Ceiling on repeated tradeoffs. Two options can differ in verb and "
            "family while offering the reader the identical bargain, which "
            "external review identified as the failure a surface metric misses."
        ),
    )
    parser.add_argument(
        "--max-worst-fork-tradeoff-rate",
        type=float,
        default=_WORST_FORK_TRADEOFF_CEILING,
        help=(
            "Ceiling on the single fork with the most repeated tradeoff, "
            "same treatment as --max-worst-fork-family-rate: --max-tradeoff-"
            "rate is a mean across every shared fork and can pass while the "
            "forks a reader meets first offer the identical bargain twice."
        ),
    )
    parser.add_argument(
        "--max-worst-fork-consequence-rate",
        type=float,
        default=_WORST_FORK_CONSEQUENCE_CEILING,
        help=(
            "Ceiling on the single fork with the most repeated consequence. "
            "consequence_rate itself is reported but not gated as a mean "
            "(pre-existing behavior, unchanged here); this worst-fork gate "
            "is additive and catches a concentrated repeat that a mean, "
            "gated or not, would still average away."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    left, right = (
        cast("dict[str, Any]", json.loads(Path(p).read_text(encoding="utf-8")))
        for p in args.contracts
    )
    scores, notes, worst_nodes = compare(left, right)
    if not scores:
        for note in notes:
            sys.stderr.write(f"{note}\n")
        return 2

    for key, value in scores.items():
        shown = (
            f"{value:.0f}"
            if value.is_integer() and "rate" not in key
            else f"{value:.3f}"
        )
        sys.stdout.write(f"{key:24s} {shown}\n")
    sys.stdout.write(
        f"{'worst_fork_family_node':24s} {worst_nodes['family'] or 'n/a'}\n"
    )
    sys.stdout.write(
        f"{'worst_fork_tradeoff_node':24s} {worst_nodes['tradeoff'] or 'n/a'}\n"
    )
    sys.stdout.write(
        f"{'worst_fork_consequence_node':24s} {worst_nodes['consequence'] or 'n/a'}\n"
    )
    for note in notes:
        sys.stdout.write(f"{note}\n")

    breaches: list[str] = []
    if scores["same_decision_reuse"] > args.max_exact:
        breaches.append(
            f"same-decision reuse {scores['same_decision_reuse']:.0f} > {args.max_exact} "
            f"(options identical in family, target and tradeoff)"
        )
    if scores["action_family_rate"] > args.max_family_rate:
        breaches.append(
            f"action-family rate {scores['action_family_rate']:.3f} > "
            f"{args.max_family_rate}"
        )
    if scores["worst_fork_family_rate"] > args.max_worst_fork_family_rate:
        breaches.append(
            f"worst fork ({worst_nodes['family'] or 'n/a'}) family rate "
            f"{scores['worst_fork_family_rate']:.3f} > {args.max_worst_fork_family_rate}"
        )
    if scores["tradeoff_rate"] > args.max_tradeoff_rate:
        breaches.append(
            f"tradeoff rate {scores['tradeoff_rate']:.3f} > {args.max_tradeoff_rate}"
        )
    if scores["worst_fork_tradeoff_rate"] > args.max_worst_fork_tradeoff_rate:
        breaches.append(
            f"worst fork ({worst_nodes['tradeoff'] or 'n/a'}) tradeoff rate "
            f"{scores['worst_fork_tradeoff_rate']:.3f} > "
            f"{args.max_worst_fork_tradeoff_rate}"
        )
    if scores["worst_fork_consequence_rate"] > args.max_worst_fork_consequence_rate:
        breaches.append(
            f"worst fork ({worst_nodes['consequence'] or 'n/a'}) consequence rate "
            f"{scores['worst_fork_consequence_rate']:.3f} > "
            f"{args.max_worst_fork_consequence_rate}"
        )
    if scores["ordered_sequence_rate"] > args.max_sequence_rate:
        breaches.append(
            f"ordered-sequence rate {scores['ordered_sequence_rate']:.3f} > "
            f"{args.max_sequence_rate}"
        )
    for breach in breaches:
        sys.stderr.write(f"FAIL {breach}\n")
    sys.stdout.write(f"{'FAIL' if breaches else 'ok  '}: {len(breaches)} breach(es)\n")
    return 1 if (breaches and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
