"""Find choices that promise something the story never delivers.

Usage:
    uv run python scripts/check_promise_discharge.py <skeleton.json>
        <contract.json> [--check]

**Found by a reader, in three books at once, after every guard had passed
them.** A blind rater reported that the crossing choice promises an object in
all three books of a round and that none of them ever mentions the reader
picking it up: "the label promises an object; the text simply drops it". Traced
into the contracts, the defect is exact and it is structural:

- `n_pendulum` establishes `reward_glimpsed`, "something the maker set aside
  for whoever passes waits at the crossing's far end".
- Its option `c_pendulum_oil` reads "cross with care and **claim** the maker's
  set-aside reward", and its destination's `entry_state` does not carry
  `reward_glimpsed` at all.
- Its option `c_pendulum_giveup` reads "decline it", and *that* destination
  does carry it.

**The fact naming the reward survives only on the branch that refuses it.** The
claiming branch has no fact standing for possession, so no author can write the
payoff and none did. The same shape appears in three independently authored
contracts, one written without sight of the others, so the graph invites it
rather than one author slipping.

**Why nothing caught it.** Fact-graph closure forbids a node *assuming* what its
parents do not guarantee; dropping a fact is always safe under closure, so
closure is structurally blind to this. `check_branch_obligations.py` computes
what a branch must deliver, not what it silently discards. This is the missing
third question: **not what a branch owes, and not what it may assume, but what
it quietly stops carrying.**

**The signal.** At a fork, a fact established by the fork itself that some
branches carry forward and others do not. Asymmetry is what makes it
suspicious: a fact dropped by *every* branch is a scene detail that has served
its purpose, while a fact dropped by one branch and kept by its sibling is a
promise honoured on one path and forgotten on the other.

**Two tiers, and only the second gates.** A plain asymmetric drop is reported.
A drop is escalated to a failure when the dropping branch's own
`choice_semantics` refers to the dropped fact, because then the option's stated
meaning names something its destination cannot know about. That is the exact
shape of the defect above and it needs no interpretation to see.

**Calibration, on the contract the defect was found in.** Twelve asymmetric
drops, four escalated to failures, and the flags are not diffuse:

| Flagged | Says | Independently confirmed? |
| --- | --- | --- |
| `n_pendulum.c_pendulum_oil` drops `reward_glimpsed` | "cross with care and claim the maker's set-aside reward" | **yes**, the rater finding this was built from |
| `n_setjam.c_jam_oil` drops `test_forced` | "find the honest way back and retake the test properly" | **yes**, a second rater found the forced damage not persisting into the next scene |
| `n_keeper.c_keeper_enter` drops `keeper_offer_earned` | "take the earned offer and go now" | plausible, unconfirmed |
| `n_backpanel.c_panel_vault` drops `second_test_found` | "solve the hidden test toward what everyone came for" | plausible, unconfirmed |

Two of four flags correspond to defects blind readers reported without seeing
this checker, in separate rounds, and the second one is the reason this matters:
a rater found a book whose "leave the lever broken" option led to a scene
saying the splice held. That is `test_forced` being dropped, visible in the
contract before a word of prose existed.

All six contracts in the programme fail, including one authored without sight
of the others, which is consistent with the graph inviting the error.

**What it cannot do.** It reads fact names and semantics, not prose, so a
contract that never names the promise as a fact will pass while its books still
disappoint a reader. The prose-level version of this question needs a model
reading each label against its destination, which is a separate check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

_WORD_RE = re.compile(r"[a-z']+")
_MIN_FORK_OPTIONS = 2
_STOPWORDS = frozenset(
    """a an and are as at be by for from in into is it its of on or the their them
    they this to with you your not no but so than then there up down out over
    under one two do does did if all any some more most such very just only also
    about after before will would could should can may might must""".split()
)


class Drop(NamedTuple):
    """A fact the fork establishes that this branch stops carrying."""

    fork: str
    choice: str
    target: str
    fact: str
    named_in_semantics: bool
    kept_by: tuple[str, ...]


def _load(path: str) -> dict[str, Any]:
    """Load a JSON object from path."""
    return cast(
        "dict[str, Any]", json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    )


def _stems(text: str) -> set[str]:
    """Return crudely stemmed content words, so 'reward' matches 'rewards'."""
    out: set[str] = set()
    for word in _WORD_RE.findall(text.lower()):
        if word in _STOPWORDS:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > len(suffix) + 2 and word.endswith(suffix):
                word = word[: -len(suffix)]
                break
        out.add(word)
    return out


def drops(skeleton: dict[str, Any], contract: dict[str, Any]) -> list[Drop]:
    """Return every fact a fork establishes that some branch stops carrying.

    Args:
        skeleton: The decoded skeleton, source of graph shape.
        contract: The decoded narrative contract.

    Returns:
        One Drop per (fork, branch, dropped fact), asymmetric cases only.
    """
    nodes = cast("dict[str, Any]", contract.get("nodes") or {})
    out: list[Drop] = []
    for node in cast("list[dict[str, Any]]", skeleton.get("nodes") or []):
        fork = str(node["id"])
        choices = cast("list[dict[str, Any]]", node.get("choices") or [])
        if len(choices) < _MIN_FORK_OPTIONS or fork not in nodes:
            continue
        established = set(cast("list[str]", nodes[fork].get("establishes") or []))
        if not established:
            continue

        carried: dict[str, set[str]] = {}
        for choice in choices:
            target = str(choice.get("target") or "")
            if target in nodes:
                carried[str(choice["id"])] = established & set(
                    cast("list[str]", nodes[target].get("entry_state") or [])
                )
        if len(carried) < _MIN_FORK_OPTIONS:
            continue

        semantics = cast("dict[str, str]", nodes[fork].get("choice_semantics") or {})
        targets = {str(c["id"]): str(c.get("target") or "") for c in choices}
        for fact in sorted(established):
            keeps = [cid for cid, kept in carried.items() if fact in kept]
            # Symmetric drops are scene detail that has done its job. Only a
            # fact kept by one sibling and dropped by another is a promise.
            if not keeps or len(keeps) == len(carried):
                continue
            for choice_id, kept in carried.items():
                if fact in kept:
                    continue
                out.append(
                    Drop(
                        fork,
                        choice_id,
                        targets.get(choice_id, ""),
                        fact,
                        bool(
                            _stems(fact.replace("_", " "))
                            & _stems(semantics.get(choice_id, ""))
                        ),
                        tuple(sorted(keeps)),
                    )
                )
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 with --check on any semantics-named drop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", help="The skeleton JSON.")
    parser.add_argument("contract", help="A narrative contract over it.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    contract = _load(args.contract)
    found = drops(_load(args.skeleton), contract)
    failures = [d for d in found if d.named_in_semantics]
    semantics_of = cast("dict[str, Any]", contract.get("nodes") or {})

    sys.stdout.write(f"{'asymmetric drops':28s} {len(found)}\n")
    sys.stdout.write(f"{'named in own semantics':28s} {len(failures)}\n")
    for drop in found:
        mark = "FAIL " if drop.named_in_semantics else "note "
        sys.stdout.write(
            f"  {mark}{drop.fork}.{drop.choice} -> {drop.target}\n"
            f"        drops {drop.fact!r}, kept by {', '.join(drop.kept_by)}\n"
        )
        if drop.named_in_semantics:
            said = cast("dict[str, str]", semantics_of[drop.fork]["choice_semantics"])
            sys.stdout.write(
                f"        this option says: {said.get(drop.choice, '')!r}\n"
            )

    if failures:
        sys.stderr.write(
            f"FAIL promise discharge: {len(failures)} choice(s) name a fact in their "
            f"own semantics that their destination does not carry, so the option "
            f"promises something no later node can know about and no author can "
            f"pay off\n"
        )
    sys.stdout.write(f"{'FAIL' if failures else 'ok  '}: promise discharge\n")
    return 1 if (failures and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
