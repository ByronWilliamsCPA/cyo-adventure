"""Check that finished prose delivers the facts its contract obliged it to.

Usage:
    uv run python scripts/check_fill_fidelity.py <contract.json> <filled.json>
        [--min-hit-rate 0.7]

The gap this closes is old and was named before it was measured: nothing in the
pipeline verified finished prose against the node obligations it was written to
satisfy. The validator checks topology, safety and reading level; the fill
integrity checker confirms the shell's structure survived and no directives
remain. Neither reads what the prose actually says. A node could establish
nothing it promised and pass every gate we had.

**What it checks.** A contract gives each node an `establishes` list: the facts
that must be true when the reader leaves it. Each fact has a plain-language
definition in the contract's `facts` dictionary. This looks for evidence of
each obligation in the node's own prose, scoring the overlap between the fact's
definition vocabulary and the node body.

**What it cannot do, stated plainly.** This is lexical evidence, not
entailment. A node that establishes `keeper_enlisted` by writing "she agreed to
put them on the roster" shares few content words with a definition reading "the
outgoing keeper agrees to let the friends join the sanctioned clearance crew",
and will score low while being perfectly correct. It therefore reports a
*ranking* of obligations by how much textual support they have, and its low
scorers are a read-this-node list rather than a verdict. Treat a failure as
"nobody has checked this" and not as "this is wrong".

**That caveat was tested immediately and is worse than feared.** The first
draft of this docstring claimed that zero-support obligations "are worth a
human's attention almost every time". Three zero-support flags from the first
book were then read: `n_window.past_the_seal` (the friends climb through the
hatch and are inside), `n_setcorrect.test_passed` (they set the dial correctly
and the board clicks open), and `n_end_giveup.composure_kept` ("They didn't
call it giving up... nobody looked over their shoulder twice"). **All three
deliver their obligation perfectly and share no vocabulary with its
definition.** Precision at zero support was 0 of 3 on its first sample.

So the claim is withdrawn. Roughly a third of obligations score zero here and
the sampled ones were all correct, which means this measure **must not gate
anything** and `--check` is deliberately absent. Verifying an obligation is a
paraphrase problem: "past the seal" is delivered by a boot on a drainpipe
bracket, and no lexical measure reaches that.

What survives is narrow. The score is comparable *across arms of one
experiment*, where the books are written from a shared fact vocabulary, so a
large gap between arms says something about one author even though the
absolute numbers do not. And the ranking is a cheap reading order for a human
reviewer who was going to read the nodes anyway.

The real check for this property needs a model reading each node against its
obligation and judging entailment, at roughly one call per obligation. This
script is the triage in front of that, not a substitute for it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

_WORD_RE = re.compile(r"[a-z']+")
_MIN_HIT_RATE = 0.7
_ZERO = 0.0
_STOPWORDS = frozenset(
    """a an and are as at be been by for from had has have he her his in into is it
    its of on or she that the their them they this to was were what when which who
    with you your not no but so than then there here up down out over under have
    has had do does did can could would should will shall may might must one two
    all any each every some such own same other another""".split()
)


class Obligation(NamedTuple):
    """One fact a node was contracted to establish, and its textual support."""

    node_id: str
    fact: str
    support: float
    definition: str


def _tokens(text: str) -> set[str]:
    """Return content words of a passage."""
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _stem(word: str) -> str:
    """Crude suffix strip so 'agreed' matches 'agrees'.

    Deliberately not a real stemmer: this is a lexical-evidence heuristic, and
    a heavier dependency would imply a precision the measure does not have.
    """
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _stems(text: str) -> set[str]:
    """Return stemmed content words of a passage."""
    return {_stem(w) for w in _tokens(text)}


def obligations(contract: dict[str, Any], filled: dict[str, Any]) -> list[Obligation]:
    """Score every node obligation against the prose that was meant to deliver it.

    Args:
        contract: The decoded narrative contract.
        filled: The decoded finished storybook.

    Returns:
        One Obligation per (node, established fact), with lexical support in
        [0, 1] measuring how much of the fact's definition vocabulary appears
        in that node's body.
    """
    facts = cast("dict[str, str]", contract.get("facts") or {})
    bodies = {
        str(n["id"]): str(n.get("body") or "")
        for n in cast("list[dict[str, Any]]", filled.get("nodes") or [])
    }
    out: list[Obligation] = []
    for node_id, node in cast("dict[str, Any]", contract.get("nodes") or {}).items():
        body = bodies.get(str(node_id))
        if body is None:
            continue
        prose = _stems(body)
        for fact in cast("list[str]", node.get("establishes") or []):
            definition = str(facts.get(fact, fact))
            # The fact's own name carries signal too: `keeper_enlisted` shares
            # 'keeper' with the prose even when the definition is paraphrased.
            wanted = _stems(definition) | _stems(fact.replace("_", " "))
            support = len(wanted & prose) / len(wanted) if wanted else 0.0
            out.append(Obligation(str(node_id), fact, support, definition))
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Always returns 0: this measure may not gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", help="The narrative contract.")
    parser.add_argument("filled", help="The finished storybook.")
    parser.add_argument(
        "--min-hit-rate",
        type=float,
        default=_MIN_HIT_RATE,
        help=(
            "Share of obligations that must show any lexical support at all. "
            "Deliberately not a per-obligation threshold: the measure is too "
            "weak to gate an individual fact."
        ),
    )
    args = parser.parse_args(argv)

    contract = cast(
        "dict[str, Any]",
        json.loads(Path(args.contract).resolve().read_text(encoding="utf-8")),
    )
    filled = cast(
        "dict[str, Any]",
        json.loads(Path(args.filled).resolve().read_text(encoding="utf-8")),
    )

    scored = obligations(contract, filled)
    if not scored:
        sys.stderr.write("no node declares an obligation this storybook covers\n")
        return 2

    unsupported = [o for o in scored if o.support == _ZERO]
    hit_rate = 1.0 - len(unsupported) / len(scored)
    mean = sum(o.support for o in scored) / len(scored)

    sys.stdout.write(f"{'obligations':28s} {len(scored)}\n")
    sys.stdout.write(f"{'mean lexical support':28s} {mean:.3f}\n")
    sys.stdout.write(f"{'with any support':28s} {hit_rate:.3f}\n")
    sys.stdout.write(f"{'with none at all':28s} {len(unsupported)}\n")

    weakest = sorted(scored, key=lambda o: o.support)[:12]
    if weakest:
        sys.stdout.write("\nread these nodes first, weakest support first:\n")
        for o in weakest:
            sys.stdout.write(
                f"  {o.support:.2f}  {o.node_id}.{o.fact}\n         "
                f"contracted to mean: {o.definition[:78]}\n"
            )

    if hit_rate < args.min_hit_rate:
        sys.stdout.write(
            f"\nnote: {len(unsupported)} obligation(s) show no lexical support, "
            f"hit rate {hit_rate:.3f} below {args.min_hit_rate}. Sampled flags from "
            f"this measure have been wrong every time they were checked, so this is "
            f"a reading order and never a verdict. Exit status stays 0 by design.\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
