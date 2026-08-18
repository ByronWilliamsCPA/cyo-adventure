"""Every gated rule must be capable of producing a finding at a real call path.

`UW-C280`. Three rules were dead and the whole suite was green:

- **CG-4** skipped any node whose body held a ``<<FILL`` directive, and the only
  callers enabling grammar checks passed skeletons, where every body is one.
  Across 70 skeletons the counts were CG-1 80, CG-2 344, CG-3 1617, CG-4 zero.
- **The M2 anti-clone floor** fell between a structural check that deferred to
  the state floor and a state floor that returned early for Tier-1.
- **The R4 theme gate** scored a different function on a different signature
  than production, so it was green while measuring a quantity nothing computes.

The obvious guard is a loop over the rule registry calling each rule directly.
**That would have caught none of them**, because all three were dead in the
WIRING rather than in the rule body: called directly, each one fires. So this
module asserts the harder property, that a violating artifact pushed through a
real ENTRY POINT yields the finding, with the flags a production caller actually
passes.

Scope is deliberately narrow and honest: it covers the rules whose entry-point
wiring has already failed, plus the neighbours sharing that wiring. It is not a
completeness claim over every rule in the gate, and it should grow whenever a
rule's plumbing is touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cyo_adventure.validator.gate import run_gate

_SKELETON = Path("skeletons/3-5/the-last-blue-cup.json")
# A committed skeleton that violates CG-1, CG-2 and CG-3 together.
_VIOLATING_SKELETON = Path("skeletons/10-13/the-cinderwick-exchange.json")


def _story() -> dict[str, Any]:
    """Return a committed skeleton as a mutable dict."""
    return json.loads(_SKELETON.read_text(encoding="utf-8"))


def _filled(story: dict[str, Any], body: str, label: str) -> dict[str, Any]:
    """Replace every FILL directive with prose so the story is a fill result."""
    for node in story["nodes"]:
        node["body"] = body
        for choice in node.get("choices", []):
            choice["label"] = label
    return story


def _rule_ids(result: object) -> set[str]:
    """Collect the rule ids present in a gate result."""
    return {finding.rule_id for finding in result.report.findings}  # type: ignore[attr-defined]


def test_cg4_fires_through_the_fill_result_entry_point() -> None:
    """CG-4 must produce a finding when a fill result ignores its choice label.

    The regression that matters: CG-4 needs PROSE, and for as long as it shared
    one flag with the structural CG rules the only callers that enabled it
    passed skeletons. Every body a directive means every target skipped, so the
    rule could not fire anywhere. This drives the real ``run_gate`` at the real
    ``context="fill_result"``, which is the posture the fill path uses.
    """
    story = _filled(
        _story(),
        body="Completely unrelated prose sharing no content word with any label.",
        label="wander toward the lighthouse",
    )

    fired = _rule_ids(run_gate(story, context="fill_result"))

    assert "CG-4" in fired, "CG-4 cannot fire at its own entry point"


def test_cg4_stays_silent_on_a_skeleton() -> None:
    """The other half of the contract: CG-4 must not fire where it cannot judge.

    A skeleton's bodies are directives, so there is no prose to compare against
    a label. Firing here would be a false positive on every catalog entry, and
    it is why the rule skips FILL bodies in the first place. Pinning both
    directions keeps a future fix from making the rule fire everywhere instead
    of nowhere.
    """
    fired = _rule_ids(run_gate(_story(), context="skeleton", enforce_grammar=True))

    assert "CG-4" not in fired


@pytest.mark.parametrize("rule_id", ["CG-1", "CG-2", "CG-3"])
def test_structural_grammar_rules_fire_behind_their_own_flag(rule_id: str) -> None:
    """CG-1, CG-2 and CG-3 must each fire on a real skeleton when grammar is on.

    These share the flag CG-4 used to be gated behind, so splitting that flag
    could have silenced them by accident; their entry point is pinned too.

    Uses a committed skeleton that genuinely violates all three rather than a
    synthetic mutation. The first attempt here fanned one node to nine
    self-pointing choices, which broke reachability instead: Layer 1 failed with
    L1-3/L1-4/L1-5 and the gate never reached the grammar layer at all. A
    fixture that stops the gate early proves nothing about a later rule, which
    is the same shape of mistake as a rule that cannot fire.
    """
    story = json.loads(_VIOLATING_SKELETON.read_text(encoding="utf-8"))

    fired = _rule_ids(run_gate(story, context="skeleton", enforce_grammar=True))

    assert rule_id in fired, f"{rule_id} did not fire at its own entry point"


def test_grammar_rules_are_silent_without_their_flag() -> None:
    """The grandfathering contract: no CG-* finding without an opted-in caller."""
    story = json.loads(_VIOLATING_SKELETON.read_text(encoding="utf-8"))

    fired = _rule_ids(run_gate(story, context="skeleton"))

    assert not {rule for rule in fired if rule.startswith("CG-")}


def test_pl27_fires_on_a_fill_result_that_kept_its_directive() -> None:
    """PL-27 is the deterministic floor under an unwritten book; pin its wiring.

    It is context-sensitive in the same way CG-4 is, and it is the single rule
    standing between an unwritten book and a human reviewer (AL-325, AL-327), so
    a wiring regression here is the most expensive one in the gate.
    """
    fired = _rule_ids(run_gate(_story(), context="fill_result"))

    assert "PL-27" in fired
