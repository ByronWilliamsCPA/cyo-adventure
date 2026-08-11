"""Score how much of one book's puzzle solution transfers to another's.

Usage:
    uv run python scripts/check_solution_transfer.py <contract.json>
        <selection.json> <selection.json> [--check] [--max-transfer 0.35]

**The item this formalises is the only one that discriminated.** Across every
rating round, the six-question instrument's Q6 ("would a child who read the
first book already know how to solve the second's puzzle?", high is bad) is the
question that separated pairs the way readers ranked them, while Q1 and Q4
saturated at 5 and the signature vocabulary inverted outright. One rater stated
the construct better than the instrument did: *"A child who read alpha does not
solve delta's puzzle; they recognise it."* Everything below is an attempt to
compute that sentence from a plan, before a word of prose exists.

**The chain, named once per contract and then derived.** A book's solution
chain is every prop bound in a device category that carries the puzzle:
`cipher_forms`, `cipher_hint_carriers` and `remedies` by default, overridable
with ``--chain-category`` because each contract names its categories itself
(the 101-node contract calls them `code_forms` and `waypoint_marks`, both of
which its own `world_recipe` marks BOUND ONCE, USED THROUGHOUT).

**Naming those categories is the single hand-set input here, and it is where
this measure could be gerrymandered.** Everything downstream is derived: which
nodes bind those categories comes from the contract, and no fork or node list
is picked by hand. That matters, because a measure allowed to choose its own
forks can reproduce any ordering asked of it. Choosing categories is a much
smaller degree of freedom than choosing nodes, but it is not zero, so the
categories used for any reported result belong in the report.

**Transfer is graded, because the evidence says it is.** Three tiers, in
descending strength:

1. **Answer transfer.** Both books bind the same device. The second puzzle is
   not solved, it is recognised. Detected without any taxonomy: identical text,
   near-identical text by content-word Jaccard, or three or more shared words
   that almost nothing else in either book uses. This tier is fully
   deterministic and carries no assumption beyond the collision signals already
   calibrated in ``check_device_collision.py``.
2. **Operation transfer.** Different devices that resolve by the same
   operation. A reader re-derives the answer but already owns the method.
3. **Family transfer.** Different operations of the same kind: both convert a
   notation into a setting, or both recognise a correspondence.

**Tiers 2 and 3 rest on a declared taxonomy, and that is this measure's whole
soft underbelly.** ``_OPERATIONS`` maps operation-marker vocabulary to
`COMPUTE`, `SEQUENCE` and `MATCH`, and ``_FAMILIES`` groups the first two as
`SYMBOLIC` against `PERCEPTUAL`. That grouping is not invented here: it is the
D-3b finding written down, that "decode a notation, set a dial" is one kind of
thinking whether the notation is arithmetic or rhythm, and that matching a
shape to an object is a different one.

**Which means the reproduction below would be only half a validation, and the
half it fails to be has to be said first.** The D-3b split was discovered on
the same three plans this checker is scored against, so tier 3 agreeing with
those raters would be confirmatory, not independent.

**Measured, and the circularity turns out not to arise.** Scored against all
three pairs that blind raters have already ranked on Q6, the ordering is
reproduced strictly, and it is reproduced by tier 1 alone:

| Pair | Raters' Q6 | Answer transfer only | Full score |
| --- | --- | --- | --- |
| base against the contaminated arm | 5, 5 | **1.000** | 1.000 |
| base against the control | 4, 4 | **0.167** | 0.467 |
| base against the treatment | 3, 3 and 2, 2 | **0.000** | 0.225 |

The taxonomy changes the magnitudes and not the order. Since tier 1 uses no
taxonomy at all, the part of this measure that reproduces the readers' ranking
is exactly the part that could not have been fitted to it.

**Tiers 2 and 3 were then tested on an unseen contract and did not survive.**
Run against the three 101-node bindings, whose vocabulary this lexicon has
never seen, `operation` returns a usable answer for 2 of the 6 chain props and
`None` for the rest:

| Prop | Classified | Why |
| --- | --- | --- |
| `number_group_code` | `COMPUTE` | correct |
| `letter_grid` | `None` | "rows of two-letter map references" trips no marker at all |
| `pictogram_code` | `None` | ties, on `numbers` inside the phrase *instead of numbers* |
| waypoint marks (3) | 2 `MATCH`, 1 `None` | `MATCH` on `drawn`, and a tie on `short` in "a short tail" |

Two failure modes, both fatal to a word list and neither fixable by adding
words: it has no negation, so *instead of numbers* counts as arithmetic; and
markers are polysemous, so a short tail on a drawn symbol reads as rhythm. The
one operation transfer it does report between the arms is both waypoint marks
scoring `MATCH`, which is an artifact of the slot (every waypoint mark in this
world is a drawn symbol) and not a fact about either puzzle.

**So the finding is narrow and should be stated narrowly.** Solution transfer
*is* computable from a plan before any prose exists, but only its
device-identity tier generalises. `--check` therefore gates on tier 1 alone.
Tiers 2 and 3 are printed as commentary, and classifying an operation needs a
model reading the device, which is the same conclusion `check_fill_fidelity.py`
reached about verifying an obligation.

**A prediction, on the record before any rating exists.** Over the 101-node
bindings, tier 1 scores every pair at 0.000, and the full score orders the
designed control pair above the designed treatment pair, 0.300 against 0.000.
Those books are built but unrated, so this is a standing prediction rather than
a result, and the 0.300 is the slot artifact named above rather than a real
operation match.

**One caveat this measure raises about the result it reproduces, rather than
about itself.** The control pair's 0.167 is not diffuse: it is one link, the
book's rhythm hint carrier ("the weir gates sluice in a repeating run, long,
long, short") against the other book's rhythm cipher ("read each pull as long
or short and let the repeating phrase spell out the setting"). That is the
`AL-185` collision, and it sits *on the solution chain of the control pair*.
So the 4-against-3 gap that this reproduces may be driven by an uncontrolled
device collision rather than by the treatment. The 5-against-2 gap is not
exposed to this: that pair shares 14 props against none.

**A false positive, recorded rather than tuned away.** "A lock tally shaved
thin off the bench's own scrap box" is classified `COMPUTE`, because `tally`
is a counting marker and here it is a wooden token. Rewriting the lexicon after
seeing which way it errs is the motivated-author move this module already warns
about at the `SEQUENCE` boundary, so the marker stays and the error is
published instead.

**A three-way split is also how the one measured reliability failure is
handled.** Two blind annotators disagreed (kappa 0.719) on whether reading a
rhythm as long-or-short is `COMPUTE` or `MATCH`, and that single call drove
most of D-3c's separation. Rather than sharpen the boundary in whichever
direction rescues the result, which is the move a motivated author would make,
`SEQUENCE` is given its own operation and joined to `COMPUTE` only at the
family level. The contested case therefore lands in a class of its own and the
result no longer depends on resolving it.

Exits 1 with ``--check`` above the ANSWER-transfer ceiling. The operation and
family tiers never gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple, cast

_WORD_RE = re.compile(r"[a-z']+")
_TEXT_JACCARD_CEILING = 0.5
_MIN_RARE_SHARED = 3
_RARE_PROP_COUNT = 2
_TRANSFER_CEILING = 0.35
_CHAIN_CATEGORIES = ("cipher_forms", "cipher_hint_carriers", "remedies")
# Sentinel accepted by `chain` to mean "every category", used to build the
# rarity corpus from both bindings entire rather than from the chain subset.
_EVERY = ("*",)

# **These three weights are invented and rest on nothing.** Any monotone triple
# would have served, and no result reported from this module depends on them:
# the reader-ranking reproduction in D-4 was achieved by the ANSWER tier alone,
# which carries no weight and no taxonomy. Read the combined score as
# decoration and `answer_transfer` as the measure. The ceiling below is
# arbitrary in the same way and gates the untaxonomised tier only.
_ANSWER, _OPERATION, _FAMILY = 1.0, 0.6, 0.3

# Operation markers. Deliberately coarse and deliberately three-way: see the
# module docstring on why the contested rhythm case gets its own class.
_OPERATIONS: dict[str, frozenset[str]] = {
    "COMPUTE": frozenset(
        """add adds adding carry carries sum sums subtract count counts counting
        arithmetic number numbers figure figures digit digits hour hours tally
        total scale notches notch calibration multiply divide reckon""".split()
    ),
    "SEQUENCE": frozenset(
        """long short repeating repeats order ordering sequence rhythm peal
        peals run runs spell spells pattern patterns beat beats interval
        intervals alternating""".split()
    ),
    "MATCH": frozenset(
        """match matches matching outline outlines silhouette silhouettes shape
        shapes picture pictures drawing drawings drawn pictogram symbol symbols
        corresponds correspondence likeness image icon stencil""".split()
    ),
}
_FAMILIES: dict[str, str] = {
    "COMPUTE": "SYMBOLIC",
    "SEQUENCE": "SYMBOLIC",
    "MATCH": "PERCEPTUAL",
}
_STOPWORDS = frozenset(
    """a an and are as at be been by for from had has have he her his in into is it
    its of on or she that the their them they this to was were what when which who
    with you your not no but so than then there here up down out over under each
    every own same other another one two every""".split()
)


class Prop(NamedTuple):
    """One bound prop on a book's solution chain."""

    node_id: str
    slot: str
    kind: str
    text: str
    category: str


class Link(NamedTuple):
    """The strongest transfer found for one prop of the first book."""

    prop: Prop
    partner: Prop | None
    tier: str
    weight: float
    evidence: str


def _load(path: str) -> dict[str, Any]:
    """Load a JSON object from path."""
    return cast(
        "dict[str, Any]", json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    )


def _tokens(text: str) -> set[str]:
    """Return the content words of a prop description."""
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _jaccard(left: set[str], right: set[str]) -> float:
    """Return the Jaccard similarity of two token sets, 0.0 when both are empty."""
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


def categories(contract: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Map every (node, slot) the contract invents to its device category.

    Args:
        contract: The decoded narrative contract.

    Returns:
        Mapping of (node id, slot name) to the contract's own category name.
    """
    out: dict[tuple[str, str], str] = {}
    for node_id, node in cast("dict[str, Any]", contract.get("nodes") or {}).items():
        invention = cast("dict[str, Any]", node.get("invention") or {})
        for slot, spec in invention.items():
            category = str(cast("dict[str, Any]", spec).get("category") or "")
            out[(str(node_id), str(slot))] = category
    return out


def chain(
    selection: dict[str, Any],
    category_of: dict[tuple[str, str], str],
    wanted: tuple[str, ...] = _CHAIN_CATEGORIES,
) -> list[Prop]:
    """Return the props a reader must read to solve this book's puzzle.

    Args:
        selection: The decoded binding for one book.
        category_of: Category lookup built from the shared contract.
        wanted: Device categories that carry the puzzle, per contract.

    Returns:
        Every bound prop whose contract category carries the puzzle.
    """
    out: list[Prop] = []
    for node_id, block in selection.items():
        if not isinstance(block, dict):
            continue
        for slot, value in cast("dict[str, Any]", block).items():
            category = category_of.get((str(node_id), str(slot)), "")
            if wanted != _EVERY and category not in wanted:
                continue
            if isinstance(value, dict):
                entry = cast("dict[str, Any]", value)
                kind, text = str(entry.get("kind") or ""), str(entry.get("text") or "")
            elif isinstance(value, str):
                kind, text = "", value
            else:
                continue
            out.append(Prop(str(node_id), str(slot), kind, text, category))
    return out


def operation(text: str) -> str | None:
    """Classify what a solver does with this device, or None if unmarked.

    Args:
        text: The bound prop's description.

    Returns:
        The operation name with the most marker hits, or None on a tie at zero.
    """
    words = _tokens(text)
    hits = {name: len(words & markers) for name, markers in _OPERATIONS.items()}
    best = max(hits, key=lambda name: hits[name])
    if hits[best] == 0:
        return None
    # A tie between two operations is genuinely ambiguous and is reported as
    # such rather than broken by dictionary order.
    if sum(1 for name in hits if hits[name] == hits[best]) > 1:
        return None
    return best


def _rare_vocabulary(corpus: list[Prop]) -> set[str]:
    """Return words used by at most `_RARE_PROP_COUNT` props across both books.

    **The corpus must be both books entire, not the solution chain.** Rarity is
    a claim about a book's whole vocabulary, and scoring it inside the chain
    alone silently inverts the measure when the chain is short: a 2-prop chain
    gives a 4-prop corpus, where a threshold of "used by at most 2 props" is
    satisfied by very nearly every word. Measured on the 101-node books, the
    chain-scoped version reported the three arms' waypoint marks (a scratched
    star, a painted spiral, an inked triangle, three plainly different devices)
    as answer-transferring, on the shared words `logbook's`, `mark` and
    `margins` (which are the contract's framing for the slot and appear in
    every binding of it). Against the full corpus those words are common and
    the false positive disappears.

    Args:
        corpus: Every bound prop of both books, chain and non-chain alike.

    Returns:
        The words rare enough that sharing one is evidence of a shared device.
    """
    frequency: Counter[str] = Counter()
    for prop in corpus:
        frequency.update(_tokens(prop.text))
    return {word for word, n in frequency.items() if n <= _RARE_PROP_COUNT}


def _answer_transfer(one: Prop, other: Prop, rare: set[str]) -> str | None:
    """Return evidence that two props are the same device, or None.

    Args:
        one: A prop from the first book.
        other: A prop from the second book.
        rare: Words almost nothing else in either book uses.

    Returns:
        A short evidence string, or None when the props are not the same device.
    """
    if one.text and one.text == other.text:
        return "identical text"
    score = _jaccard(_tokens(one.text), _tokens(other.text))
    if score > _TEXT_JACCARD_CEILING:
        return f"near-identical text ({score:.2f})"
    shared = _tokens(one.text) & _tokens(other.text) & rare
    if len(shared) >= _MIN_RARE_SHARED:
        return f"rare shared vocabulary ({', '.join(sorted(shared))})"
    return None


def transfer(
    left: list[Prop], right: list[Prop], corpus: list[Prop] | None = None
) -> list[Link]:
    """Score the strongest transfer available for each prop of the first book.

    Every prop is compared against every prop of the other book, not slot
    against slot: a device that moved node is still the same device, and the
    relocation case is 8 of the 14 collisions that wasted a rating round.

    Args:
        left: The first book's solution chain.
        right: The second book's solution chain.
        corpus: Every prop of both books, the rarity corpus. Defaults to the
            two chains, which is only safe when the chains are long.

    Returns:
        One Link per prop of the first book, carrying its best transfer.
    """
    rare = _rare_vocabulary(corpus if corpus is not None else [*left, *right])
    links: list[Link] = []
    for one in left:
        best = Link(one, None, "none", 0.0, "")
        for other in right:
            evidence = _answer_transfer(one, other, rare)
            if evidence is not None:
                best = Link(one, other, "answer", _ANSWER, evidence)
                break
            op_one, op_other = operation(one.text), operation(other.text)
            if op_one is None or op_other is None:
                continue
            if op_one == op_other and best.weight < _OPERATION:
                best = Link(one, other, "operation", _OPERATION, f"both {op_one}")
            elif (
                _FAMILIES.get(op_one) == _FAMILIES.get(op_other)
                and best.weight < _FAMILY
            ):
                best = Link(
                    one,
                    other,
                    "family",
                    _FAMILY,
                    f"{op_one}/{op_other}, both {_FAMILIES.get(op_one)}",
                )
        links.append(best)
    return links


def score(
    left: list[Prop], right: list[Prop], corpus: list[Prop] | None = None
) -> tuple[dict[str, float], list[Link]]:
    """Score solution transfer in both directions and average.

    Args:
        left: The first book's solution chain.
        right: The second book's solution chain.
        corpus: Every prop of both books, the rarity corpus.

    Returns:
        A (scores, links) pair; links are from the first book's side.
    """
    forward = transfer(left, right, corpus)
    backward = transfer(right, left, corpus)
    both = (*forward, *backward)
    total = float(len(both))
    if not total:
        return {}, []
    return (
        {
            "chain_props": float(len(left)),
            "answer_transfer": sum(1 for k in both if k.tier == "answer") / total,
            "operation_transfer": sum(1 for k in both if k.tier == "operation") / total,
            "family_transfer": sum(1 for k in both if k.tier == "family") / total,
            "solution_transfer": sum(k.weight for k in both) / total,
        },
        list(forward),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 unless --check and the ceiling is breached."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", help="The shared narrative contract.")
    parser.add_argument("selections", nargs=2, help="Two books' device selections.")
    parser.add_argument(
        "--chain-category",
        action="append",
        dest="chain_categories",
        help=(
            "A device category that carries the puzzle, repeatable. Defaults to "
            f"{', '.join(_CHAIN_CATEGORIES)}. Report whatever you used."
        ),
    )
    parser.add_argument(
        "--max-transfer",
        type=float,
        default=_TRANSFER_CEILING,
        help=(
            "Ceiling on ANSWER transfer, the taxonomy-free tier. The operation "
            "and family tiers do not generalise off the contract their lexicon "
            "was written from and are reported without gating."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    category_of = categories(_load(args.contract))
    wanted = tuple(args.chain_categories or _CHAIN_CATEGORIES)
    selections = [_load(path) for path in args.selections]
    chains = [chain(sel, category_of, wanted) for sel in selections]
    # Rarity is judged against both books entire; see `_rare_vocabulary`.
    corpus = [p for sel in selections for p in chain(sel, category_of, _EVERY)]
    if not chains[0] or not chains[1]:
        sys.stderr.write("no solution chain: the contract invents no puzzle props\n")
        return 2

    scores, links = score(chains[0], chains[1], corpus)
    for key, value in scores.items():
        shown = f"{value:.0f}" if key == "chain_props" else f"{value:.3f}"
        sys.stdout.write(f"{key:24s} {shown}\n")

    sys.stdout.write("\nchain, strongest transfer per prop:\n")
    for link in links:
        where = (
            f"-> {link.partner.node_id}.{link.partner.slot}"
            if link.partner is not None
            else "-> nothing"
        )
        sys.stdout.write(
            f"  {link.tier:9s} {link.prop.node_id}.{link.prop.slot:14s} {where}"
            f"{'  [' + link.evidence + ']' if link.evidence else ''}\n"
        )

    # Gated on tier 1 only: it is the tier that reproduced the readers' ranking
    # and the only one that survived an unseen contract. See the module docstring.
    breached = scores["answer_transfer"] > args.max_transfer
    if breached:
        sys.stderr.write(
            f"FAIL answer transfer {scores['answer_transfer']:.3f} > "
            f"{args.max_transfer}: the two books bind the same puzzle devices, so a "
            f"reader of the first does not solve the second's puzzle so much as "
            f"recognise it\n"
        )
    sys.stdout.write(
        f"{'FAIL' if breached else 'ok  '}: answer transfer "
        f"(operation and family tiers advisory, they do not generalise)\n"
    )
    return 1 if (breached and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
