"""Build the D-6 rig: does sharing one contract cause the convergence in D-2?

D-2 put three books on ONE narrative contract and they converged catastrophically
(59 to 64 shared 4-grams per 1000 against a budget of 4.0, and 41 to 51 identical
choice menus of 131). The pilot put its books on DIFFERENT contracts and stayed at
1.8 to 2.7. `AL-208` proposed the difference is the cause: sharing a plan means
sharing its prose, and authors converge on the sentence they were all handed.

That is a diagnosis, not a result, and it has never been tested directly. D-6 does
that, at pilot scale where the baseline is known, holding everything constant except
how `choice_semantics` reaches the author.

**Design.** One contract (`contract_v2`, 26 nodes), two bindings held constant
(`armC` and `armD`, the pilot's own), three conditions, six fills:

- `verbatim`  the contract's `choice_semantics` exactly as written
- `neutral`   `choice_semantics` rewritten flat: the act and its object in the
              plainest words, no metaphor, no virtue noun, no imperative colour
- `diverge`   `choice_semantics` as written, plus an explicit instruction not to
              reuse its wording

Every other input is held constant, and two candidate confounds are already ruled
out. The two books of a condition are authored by agents that cannot see each
other, so convergence cannot come from collaboration. And D-2's three arms carried
*different* `label_style` values ("imperative and verb-first", "name the place you
are going to", "physical verbs for physical legs"), so a shared house style is not
what made them converge; the same holds here, where `armC` and `armD` bring their
own distinct styles into all three conditions.

**Outcome is deterministic and needs no rater**: shared 4-grams per 1000 and
identical choice menus between the two books of each condition.

**Prediction, fixed before any fill exists.** `verbatim` lands far above the pilot's
1.8 to 2.7, reproducing D-2's failure at 26 nodes. `neutral` and `diverge` land
materially below `verbatim`.

**Falsifier.** If `verbatim` lands near the pilot baseline, contract sharing is not
the cause and D-2's convergence was a scale effect that `AL-208` misdiagnosed. If
all three conditions converge equally, the repairs do not work and every
reusable-plan architecture inherits the problem with no cheap fix.

**Why labels are stripped.** `armC_shell.json` ships pre-bound labels ("Examine the
flag code note pinned to the door."), which is the `AL-195` contamination vector:
a label the author never wrote is a label every arm shares. Every label here is a
FILL directive, so all six books author their own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).parent
SRC = HERE.parent / "obligation-variance"
_MIN_FORK_OPTIONS = 2

# The neutral condition, written under one stated rule: name the act and its
# object in the plainest words available. No metaphor, no virtue noun, no
# imperative colour, no word implying how the act should feel. Every option
# keeps the distinction the original drew; only the colour is gone.
NEUTRAL: dict[tuple[str, str], str] = {
    ("n_open", "c_open"): "start on the sealed door together",
    ("n_start", "c_examine"): "work on the note",
    ("n_start", "c_door"): "look for another entrance",
    ("n_start", "c_keeper"): "ask the keeper",
    ("n_note", "c_note_key"): "go to the place the note points to",
    ("n_note", "c_note_inside"): "act on the note now",
    ("n_door", "c_door_force"): "get through the low gap",
    ("n_door", "c_door_window"): "climb to the high window",
    ("n_keeper", "c_keeper_enter"): "take the offer and go in",
    ("n_keeper", "c_keeper_story"): "stay and hear the maker's story",
    ("n_keyhunt", "c_keyhunt_in"): "go in the confirmed way",
    ("n_keeper_story", "c_story_in"): "go in after the story",
    ("n_window", "c_window_in"): "drop down inside",
    ("n_inside", "c_inside_stairs"): "go up the stairs",
    ("n_inside", "c_inside_study"): "go to the study",
    ("n_inside", "c_inside_pendulum"): "cross the pendulum walk",
    ("n_inside", "c_inside_basement"): "go down to the basement",
    ("n_stairs", "c_stairs_face"): "go on to the dial",
    ("n_study", "c_study_face"): "go on to the dial",
    ("n_study", "c_study_logs"): "stay and read the records",
    ("n_pendulum", "c_pendulum_oil"): "cross and take the set-aside item",
    ("n_pendulum", "c_pendulum_giveup"): "turn back from the crossing",
    ("n_basement", "c_basement_face"): "go up to the dial",
    ("n_clockface", "c_face_correct"): "set the dial using the code",
    ("n_clockface", "c_face_jam"): "force the dial",
    ("n_clockface", "c_face_panel"): "look behind the dial instead",
    ("n_clockface", "c_face_random"): "guess a setting",
    ("n_setcorrect", "c_correct_vault"): "go through the opened way",
    ("n_setjam", "c_jam_oil"): "fix the jam and set the dial again",
    ("n_setjam", "c_jam_stuck"): "stop for tonight",
    ("n_backpanel", "c_panel_vault"): "take the way to the strongroom",
    ("n_backpanel", "c_panel_secret"): "take the way to the unlisted room",
    ("n_vault", "c_vault_share"): "bring the letter to the settlement",
    ("n_vault", "c_vault_keep"): "keep the letter among the friends",
    ("n_vault", "c_vault_grab"): "take the contents for themselves",
}


def _load(path: Path) -> dict[str, Any]:
    """Load a JSON object from path."""
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def build_shell(skeleton: dict[str, Any]) -> dict[str, Any]:
    """Return a shell whose every body, label, title and ending is a directive.

    Args:
        skeleton: The pilot shell, used only for its topology.

    Returns:
        A shell carrying no authored prose of any kind.
    """
    shell = json.loads(json.dumps(skeleton))
    # The skeleton id leaked the book title in D-2; it carries no topology.
    shell["id"] = "d6"
    shell["title"] = "<<FILL book_title>>"
    for node in cast("list[dict[str, Any]]", shell["nodes"]):
        node_id = str(node["id"])
        for choice in cast("list[dict[str, Any]]", node.get("choices") or []):
            choice["label"] = f"<<FILL label contract='{node_id}.{choice['id']}'>>"
        ending = cast("dict[str, Any] | None", node.get("ending"))
        if ending is not None:
            ending["title"] = "<<FILL ending_title>>"
    return shell


def neutralise(contract: dict[str, Any]) -> dict[str, Any]:
    """Replace every fork's choice semantics with flat functional phrasing.

    **The obvious construction was tried first and is unusable, which is itself
    a result.** Deriving each branch's semantics mechanically from the fact
    graph, as the facts its destination presupposes that the fork does not
    already guarantee, needs no author and cannot smuggle in a voice. It also
    destroys the fork. At `n_clockface` all four options, answering the code,
    forcing the dial, going round the back and guessing at random, own exactly
    the same obligation, so all four neutralise to the identical sentence.

    That is `AL-197` restated from the other side: **the fact graph does not
    contain the decision**, so nothing derived from it can neutralise the
    wording while preserving the choice. The same layer finding D-3 and D-3b
    reached, arrived at here by trying to build on the layer below it.

    So the neutral phrasing is written by hand under a stated rule: **name the
    act and its object, in the plainest words available; no metaphor, no virtue
    noun, no imperative colour, no word that implies how the act should feel.**
    "Lead with patience: sit with the note until it yields" becomes "work on
    the note". The rule is what is on trial, and one author's flat sentence
    handed to two books is precisely the condition being tested.

    Args:
        contract: The decoded narrative contract.

    Returns:
        A copy of the contract with flat choice semantics at every fork.

    Raises:
        KeyError: If the neutral table and the contract's forks disagree, which
            would mean the condition silently dropped or invented an option.
    """
    out = json.loads(json.dumps(contract))
    nodes = cast("dict[str, Any]", out["nodes"])
    covered: set[tuple[str, str]] = set()
    for node_id, node in nodes.items():
        semantics = cast("dict[str, str]", node.get("choice_semantics") or {})
        for choice_id in semantics:
            key = (node_id, choice_id)
            if key not in NEUTRAL:
                msg = f"no neutral phrasing for {node_id}.{choice_id}"
                raise KeyError(msg)
            semantics[choice_id] = NEUTRAL[key]
            covered.add(key)
    if covered != set(NEUTRAL):
        msg = f"neutral table has {len(set(NEUTRAL) - covered)} unused entries"
        raise KeyError(msg)
    return out


def main() -> int:
    """Write the shared shell and the neutralised contract."""
    skeleton = _load(SRC / "armC_shell.json")
    contract = _load(SRC / "contract_v2.json")

    shell = build_shell(skeleton)
    (HERE / "shell.json").write_text(
        json.dumps(shell, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (HERE / "contract_neutral.json").write_text(
        json.dumps(neutralise(contract), indent=1, ensure_ascii=False),
        encoding="utf-8",
    )

    blob = json.dumps(shell)
    forks = sum(
        1
        for n in cast("list[dict[str, Any]]", shell["nodes"])
        if len(cast("list[Any]", n.get("choices") or [])) >= _MIN_FORK_OPTIONS
    )
    print(f"shell: {len(cast('list[Any]', shell['nodes']))} nodes, {forks} forks")
    print(f"shell carries no authored label: {'<<FILL label' in blob}")
    print(f"shell mentions no book title:    {'clocktower' not in blob.lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
