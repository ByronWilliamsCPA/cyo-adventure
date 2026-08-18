"""ADR-011 section 10 per-band choice-grammar advisories (W2.1, D2/D15).

Implements, as WARNING-severity advisories that never block, the ratified
per-band choice grammar table (``docs/planning/adr/adr-011-story-scale-framework.md``
section 10):

* **CG-1 choiceless-run cap**: how many consecutive single-choice, non-ending
  nodes ("choiceless stops in a row") a band tolerates before the flavor mix
  drifts from "Continue" corridor toward the discrete-page bands' intended
  pacing, or (for the flowed bands, 8-11 and up) before one rendered stop
  (ADR-026) grows past a reasonable felt page.
* **CG-2 options-per-choice bounds**: how many options a decision node (a
  non-ending node with 2+ choices) may offer for its band.
* **CG-3 words-per-stop ceiling**: for the flowed bands only, the concatenated
  word count of a composed stop (mirrors ``player/stops.py::compose_stop``'s
  node sequence: the single-choice run plus the branch/ending node it flows
  into) must not exceed the band's words-per-stop ceiling.
* **CG-4 fill-gate acknowledgment**: a decision-child node's opening sentence
  should share at least one content word with the choice label that leads to
  it (ADR-011 section 10's cross-cutting "every choice is acknowledged in the
  immediately following prose" rule). This is a **heuristic**, not a
  semantic check: presence-based token overlap can neither prove an
  acknowledgment is present (a well-written acknowledgment need not reuse any
  word from the label) nor that it is absent (a shared word does not prove
  the prose actually registers the pick). #ASSUME: data-integrity: token
  overlap is a weak, false-positive/false-negative-prone proxy for "the prose
  acknowledges the choice"; a human reviewer, not this check, makes the real
  call. #VERIFY: tests/unit/test_choice_grammar.py exercises both a body that
  shares a word with its choice label (no finding) and one that does not (a
  finding), plus the FILL-marker skip.

Grandfathering (D3/D11), and what "inert" means today
-----------------------------------------------------
The existing 61-skeleton catalog predates this grammar and is grandfathered:
no machine-readable "this skeleton is grandfathered" marker exists yet (the
D11 ``deprecated`` marker is tracked as future work, W2.4). Until that marker
lands, every check in this module is gated behind the ``enforce_grammar``
keyword (default ``False``) on :func:`check_choice_grammar`; a promotion-path
caller for genuinely new skeletons opts in explicitly. The individual
``check_*`` functions below run unconditionally when called directly (for
unit testing and for a future promotion path that wants one rule at a time);
only the combinator applies the gate.

Be precise about the current state, because "advisory" understates it: **no
production caller passes the flag**, so CG-1 through CG-4 emit no finding on
any real story. ``validator/gate.py::run_gate`` defaults it ``False`` and
forwards it, and the only call site anywhere that passes ``True`` is
``tests/unit/test_choice_grammar.py``. That is grandfathering by omission
rather than by decision, so state the flip condition rather than leaving it
implied:

**Flip condition.** When the D11 ``deprecated`` per-skeleton marker lands
(W2.4), a story carrying it is grandfathered and one that does not is new,
which is the discrimination the flag is standing in for. At that point
``check_choice_grammar`` can key off the marker and ``enforce_grammar`` can
default ``True``. Tracked as ``UW-C24``; the decision to flip is the owner's,
not this module's.

Rule id family
--------------
``CG-*`` is a new rule-id family, deliberately outside the
``L1|L2|PL|RL|SAFE|SR`` set ``tests/unit/test_validator_rules_catalog.py``
lockstep-checks against ``docs/planning/validator-rules.md``. Registering the
family in that catalog is out of this change's scope (see the implementation
plan's W2.1); mirrors how PL-22 shipped ahead of its catalog row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.diversity.normalize import STOPWORDS, tokenize
from cyo_adventure.storybook.sentinels import strip_sentinels
from cyo_adventure.utils.sentences import split_sentences
from cyo_adventure.validator.report import Severity, ValidationFinding, ValidationReport

if TYPE_CHECKING:
    from cyo_adventure.storybook.models import Node, Storybook

# A skeleton body is a ``<<FILL role=... words=N ...>>`` directive, not prose;
# mirrors reading_level.py's and policy.py's identical constant (each
# validator module keeps its own copy deliberately, per policy.py's header
# note, so no module depends on another for a one-line marker).
_FILL_MARKER = "<<FILL"
_FILL_WORDS_RE = re.compile(r"\bwords=(\d+)")

# Choiceless-run cap. The two halves have different provenance, and an
# earlier version of this comment blurred them by citing the ADR for both.
#
# Discrete-page bands (3-5, 5-8) read straight off ADR-011 section 10's "Max
# choiceless stops in a row" column (2-3 and 2), and one node IS one stop at
# these bands, so the numbers transfer unit-for-unit. This is also the only
# enforcement section 10 asks for: its closing paragraph scopes graph-level
# run caps to "the discrete-page bands".
#
# The flowed cap is NOT from the ADR. Section 10's flowed rows read
# "1, prefer 0" (8-11) and "0-1" (10-13/13-16/16+), and they count STOPS,
# where a stop is a whole flowed multi-node passage (ADR-026). The number 6
# appears nowhere in the ADR. It is a derived NODE-level backstop: past about
# six single-choice nodes a composed stop blows the words-per-stop ceiling
# for any plausible per-node length, which is why the finding message
# reports the composed word count alongside it.
#
# #ASSUME: data-integrity: this cap is a proxy, not the section 10
# constraint. The real flowed rule ("at most one choiceless STOP in a row")
# needs stop-level adjacency, which nothing here computes; it is unimplemented,
# not enforced-by-another-name. Reading a green CG-1 as "section 10 satisfied"
# at a flowed band is wrong in both directions: a story can sit under 6 nodes
# and still chain several choiceless stops, and a 7-node run inside one stop
# is not a section 10 violation at all.
# #VERIFY: UW-C10 tracks implementing the stop-level rule; until it lands,
# CG-1's own message says "advisory only".
_DISCRETE_RUN_CAP: dict[str, int] = {"3-5": 3, "5-8": 3}
_FLOWED_RUN_CAP = 6

# Share of a story's non-ending nodes that may be single-choice, per band.
# RULED 2026-08-17 (owner): every band gets an allowed portion of no-decision
# nodes, so a scene that needs runway can take it.
#
# This is the faithful reading of ADR-011 section 10's cadence column, which
# states an AVERAGE ("choice every 2nd-4th page" at 3-5, "every 1st-2nd" at
# 5-8) rather than a local maximum. The run cap alone could not express an
# average: it forbade a single four-page scene even in a story whose overall
# cadence was well inside the research. The two rules now split that work, the
# share carrying the average and the run cap remaining as a local backstop
# against one endless corridor. The 5-8 run cap rises 2 to 3 in the same
# change, because a cap that binds before the share makes the share dead
# letter.
#
# Derivation, so these are not free parameters:
#   3-5   section 10 allows up to 4 pages per choice, so 3 corridors in 4 nodes.
#   5-8   section 10 allows up to 2 pages per choice, so 1 corridor in 2 nodes.
#   8-11+ a node is not a page; nodes inside a stop are flowed and invisible
#         (ADR-026), so the meaningful figure is how many nodes compose one
#         stop: the top of the band's words-per-stop range over the low end of
#         its per-node band gives 1.8 to 2.1 nodes, i.e. about one corridor per
#         decision.
#
# #ASSUME: data-integrity: the share is measured over non-ending nodes, since
# an ending can never be single-choice and would otherwise dilute the ratio in
# proportion to how many endings a story happens to have.
# #VERIFY: tests/unit/test_choice_grammar.py::
# test_choiceless_share_ignores_endings_in_the_denominator
_CHOICELESS_SHARE: dict[str, float] = {
    "3-5": 0.75,
    "5-8": 0.50,
    "8-11": 0.50,
    "10-13": 0.50,
    "13-16": 0.50,
    "16+": 0.50,
}
_FLOWED_BANDS: frozenset[str] = frozenset({"8-11", "10-13", "13-16", "16+"})

# The global envelope every decision node sits inside regardless of band, and
# the share of a story's decision nodes that may sit one step outside their
# band's target. RULED 2026-08-17 (owner): the per-band rows below became
# targets rather than hard bounds, because three of the six bands pinned the fan
# to a single value, which left an author no way to vary rhythm and, combined
# with the walk and arc floors, made the no-reconvergence topologies unbuildable
# above 3-5 (`AL-442`, `UW-C272`).
#
# The allowance is deliberately expressed against the band's whole target range
# rather than a single number, so a band that already carries a range (5-8 at
# [2, 3], the teen bands at [3, 4]) keeps it and gains one step either side.
# Every skeleton passing --strict when this landed used zero variance, so the
# change cannot retroactively invalidate committed work.
_OPTIONS_HARD_FLOOR = 2
_OPTIONS_HARD_CEILING = 4
_OPTIONS_VARIANCE_SHARE = 0.20

# Options-per-choice targets (inclusive), ADR-011 section 10 "Options per
# choice" column.
_OPTIONS_BOUNDS: dict[str, tuple[int, int]] = {
    "3-5": (2, 2),
    "5-8": (2, 3),
    "8-11": (3, 3),
    "10-13": (3, 3),
    "13-16": (3, 4),
    "16+": (3, 4),
}

# Words-per-stop ceiling (the upper bound of the ADR-011 section 10 "Words
# per stop" column), flowed bands only.
_WORDS_PER_STOP_CEILING: dict[str, int] = {
    # 3-5 and 5-8 added 2026-08-18 from ADR-011 section 10's own column, which
    # rules a words-per-stop range for all SIX bands where this table carried
    # four. At those bands a node IS a stop (ADR-026 decision 4 renders one node
    # per page), so the substitute was `words_per_node_profile`, about 2.2x more
    # permissive at the top: 90 and 155 hard against the ADR's 40 and 70
    # (`AL-454`, `UW-C276`).
    #
    # Cost measured before adding them: 160 findings across the committed young
    # bands. Kept anyway, because the two skeletons authored to the strict bar in
    # this workstream (`the-last-blue-cup` at 3-5, `the-seedling-thief` at 5-8)
    # sit EXACTLY at these ceilings with zero violations, so the bound is
    # demonstrably achievable and the findings are legacy content. That is the
    # opposite conclusion from PL-17's new endings ceiling, which a fresh
    # strict-bar skeleton did violate and which therefore ships advisory-only;
    # the same test gave opposite answers and both were followed.
    "3-5": 40,
    "5-8": 70,
    "8-11": 135,
    "10-13": 150,
    "13-16": 200,
    "16+": 230,
}


def words_per_stop_ceiling(age_band: str) -> int | None:
    """Return the CG-3 words-per-rendered-stop ceiling for a band.

    Public so the generation prompt can STATE the bound the gate will grade
    against. Four story-first drafts measured a median scene length of 246, 439,
    400 and 279 words at 5-8, 8-11, 10-13 and 13-16: no trend, so the model does
    not infer the range from the age band and the brief has to say it
    (`UW-C278`).

    Args:
        age_band: The story age band value (for example ``"8-11"``).

    Returns:
        The band's ceiling, or ``None`` at a band CG-3 does not cover. 3-5 and
        5-8 render one node per page (ADR-026 decision 4), so a stop is a node
        there and PL-19 bounds it instead; the two missing entries are tracked
        by ``UW-C276``.
    """
    return _WORDS_PER_STOP_CEILING.get(age_band)


def _word_count(body: str) -> int:
    """Return a body's word count, pre- or post-fill.

    An unfilled ``<<FILL ...>>`` directive is not prose; its declared
    ``words=N`` target(s) are summed instead, so this check can run against a
    skeleton (at promotion time) as well as a filled story. Mirrors
    ``validator/policy.py``'s PL-19 words-per-node check, which reads the same
    directive the same way.

    Args:
        body: A node's body text, filled or unfilled.

    Returns:
        int: The word count (post-fill) or the sum of declared ``words=``
            targets (pre-fill).
    """
    if _FILL_MARKER in body:
        match = _FILL_WORDS_RE.search(body)
        return int(match.group(1)) if match is not None else 0
    return len(strip_sentinels(body).split())


def _is_single_choice(node: Node) -> bool:
    """Return whether a node is a non-ending node with exactly one choice."""
    return not node.is_ending and len(node.choices) == 1


def _is_decision(node: Node) -> bool:
    """Return whether a node is a non-ending node with 2+ choices."""
    return not node.is_ending and len(node.choices) >= 2


@dataclass(frozen=True, slots=True)
class _Run:
    """One maximal chain of consecutive single-choice, non-ending nodes.

    Attributes:
        node_ids: The chain, head to tail, each a single-choice non-ending
            node whose sole choice leads to the next entry (or to
            ``terminal_id``).
        terminal_id: The node the chain's last choice flows into, when that
            node is a real branch (2+ choices) or an ending -- i.e. the node
            ``player/stops.py::compose_stop`` would also add to the stop.
            ``None`` when the chain ends in a loop-back (the target is
            already in this chain) or an unresolved reference, in which case
            no further node contributes to the stop's word count.
    """

    node_ids: tuple[str, ...]
    terminal_id: str | None


def _find_runs(story: Storybook) -> list[_Run]:
    """Return every maximal single-choice run in the story.

    Structural walk over ``choice.target`` only; it does not evaluate
    ``choice.condition`` against any variable state (there is no reading
    session here, only the static graph). #ASSUME: data-integrity: a
    condition-gated single choice is walked as if always taken, so a run that
    a real reader would never fully traverse (because a condition is false in
    some reachable state) can still be reported here. This mirrors
    ``player/stops.py``'s own condition-blind structural shape for the
    *un-gated* case and is a deliberate advisory-only simplification: a false
    positive here costs nothing (the check never blocks) and Layer 2 already
    owns condition-correctness. #VERIFY: tests/unit/test_choice_grammar.py
    covers the unconditional-chain case; a condition-aware refinement is
    tracked as future work if advisory noise on Tier-2 stories proves high.

    Args:
        story: The parsed Storybook to walk.

    Returns:
        list[_Run]: Every maximal run, one entry per run head. A run head is
            a single-choice node that is not itself the sole target of
            another single-choice node (so each run is counted exactly once
            from its start).
    """
    nodes_by_id = {node.id: node for node in story.nodes}
    incoming_single: set[str] = set()
    for node in story.nodes:
        if _is_single_choice(node):
            incoming_single.add(node.choices[0].target)

    runs: list[_Run] = []
    for node in story.nodes:
        if not _is_single_choice(node) or node.id in incoming_single:
            continue
        chain: list[str] = [node.id]
        seen: set[str] = {node.id}
        current = node
        terminal: str | None = None
        while True:
            target_id = current.choices[0].target
            if target_id in seen:
                terminal = None
                break
            target = nodes_by_id.get(target_id)
            if target is None:
                terminal = None
                break
            if _is_single_choice(target):
                chain.append(target_id)
                seen.add(target_id)
                current = target
                continue
            terminal = target_id
            break
        runs.append(_Run(node_ids=tuple(chain), terminal_id=terminal))
    return runs


def check_choiceless_run_cap(story: Storybook) -> ValidationReport:
    """CG-1: cap consecutive single-choice, non-ending nodes per band.

    Args:
        story: The parsed Storybook to check.

    Returns:
        ValidationReport: WARNING findings, one per over-cap run.
    """
    report = ValidationReport()
    band = story.metadata.age_band.value
    if band in _DISCRETE_RUN_CAP:
        cap = _DISCRETE_RUN_CAP[band]
    elif band in _FLOWED_BANDS:
        cap = _FLOWED_RUN_CAP
    else:
        return report

    nodes_by_id = {node.id: node for node in story.nodes}
    for run in _find_runs(story):
        length = len(run.node_ids)
        if length <= cap:
            continue
        head_id = run.node_ids[0]
        detail = ""
        if band in _FLOWED_BANDS and band in _WORDS_PER_STOP_CEILING:
            words = sum(_word_count(nodes_by_id[nid].body) for nid in run.node_ids)
            if run.terminal_id is not None and run.terminal_id in nodes_by_id:
                words += _word_count(nodes_by_id[run.terminal_id].body)
            ceiling = _WORDS_PER_STOP_CEILING[band]
            detail = (
                f"; composed stop is ~{words} words, "
                f"{'above' if words > ceiling else 'within'} the {ceiling}-word "
                "words-per-stop ceiling"
            )
        report.add(
            ValidationFinding(
                rule_id="CG-1",
                severity=Severity.WARNING,
                story_id=story.id,
                node_id=head_id,
                message=(
                    f"CG-1 grammar: node '{head_id}' starts a run of {length} "
                    f"consecutive single-choice nodes in band '{band}' (cap {cap}) "
                    f"in story '{story.id}' (advisory only, new-content grammar "
                    f"per ADR-011 section 10){detail}"
                ),
            )
        )

    share_cap = _CHOICELESS_SHARE.get(band)
    if share_cap is not None:
        non_ending = [node for node in story.nodes if not node.is_ending]
        choiceless = [node for node in non_ending if _is_single_choice(node)]
        # A share is a statement about cadence, and cadence is undefined with
        # nothing to pace against. A story with no decision at all is PL-17's
        # subject (it floors decision count), not this rule's, so skip rather
        # than report every such graph as 100 percent over its allowance.
        if not any(_is_decision(node) for node in non_ending):
            return report
        allowed = int(len(non_ending) * share_cap)
        if len(choiceless) > allowed:
            report.add(
                ValidationFinding(
                    rule_id="CG-1",
                    severity=Severity.WARNING,
                    story_id=story.id,
                    node_id=choiceless[allowed].id,
                    message=(
                        f"CG-1 grammar: {len(choiceless)} of {len(non_ending)} "
                        f"non-ending nodes are single-choice, above band "
                        f"'{band}'s {share_cap:.0%} allowance of {allowed} in "
                        f"story '{story.id}'; the band's cadence is an average, "
                        f"so a long scene is fine only if the story spends "
                        f"decisions elsewhere (advisory only, new-content "
                        "grammar per ADR-011 section 10)"
                    ),
                )
            )
    return report


def check_options_per_choice(story: Storybook) -> ValidationReport:
    """CG-2: bound how many choices a decision node offers, per band.

    Three tiers, ruled 2026-08-17 (owner). A band's ``_OPTIONS_BOUNDS`` entry is
    its *target* set, and a node inside it always conforms. Beyond that:

    - **One step outside the target, within the global [2, 4] envelope**: a
      permitted variant, capped at :data:`_OPTIONS_VARIANCE_SHARE` of the
      story's decision nodes. This is the flexibility the rule exists to give:
      pinning a band to a single fan (3-5, 8-11 and 10-13 are all exact) left an
      author no way to vary rhythm, and made the reconverging topologies the
      only buildable ones above 3-5.
    - **Outside the global envelope**, fewer than 2 or more than 4: always a
      finding, at any share. A two-way fan is the least a decision can be and a
      five-way fan is past what any band's reader is asked to hold.
    - **Two or more steps from the target** while still inside [2, 4]: a
      finding, because the variance allowance is for a step of rhythm, not for
      a different grammar.

    Args:
        story: The parsed Storybook to check.

    Returns:
        ValidationReport: WARNING findings, one per offending decision node,
            plus one summary finding when permitted variants exceed their share.
    """
    report = ValidationReport()
    band = story.metadata.age_band.value
    bounds = _OPTIONS_BOUNDS.get(band)
    if bounds is None:
        return report
    lo, hi = bounds
    decisions = [node for node in story.nodes if _is_decision(node)]
    variants: list[str] = []
    for node in decisions:
        count = len(node.choices)
        if lo <= count <= hi:
            continue
        one_step = count in {lo - 1, hi + 1}
        in_envelope = _OPTIONS_HARD_FLOOR <= count <= _OPTIONS_HARD_CEILING
        if one_step and in_envelope:
            variants.append(node.id)
            continue
        report.add(
            ValidationFinding(
                rule_id="CG-2",
                severity=Severity.WARNING,
                story_id=story.id,
                node_id=node.id,
                message=(
                    f"CG-2 grammar: node '{node.id}' offers {count} choices, "
                    f"outside band '{band}' target [{lo}, {hi}] by more than one "
                    f"step or outside the global envelope "
                    f"[{_OPTIONS_HARD_FLOOR}, {_OPTIONS_HARD_CEILING}] in story "
                    f"'{story.id}' (advisory only, new-content grammar per "
                    "ADR-011 section 10)"
                ),
            )
        )

    # #ASSUME: data-integrity: the share is measured against decision nodes
    # only, not all nodes, because a story's single-choice corridors are CG-1's
    # subject and would otherwise dilute the allowance into meaninglessness (a
    # corridor-heavy story could carry far more odd fans than a branchy one).
    # #VERIFY: tests/unit/test_choice_grammar.py::
    # test_variance_share_is_measured_against_decision_nodes_not_all_nodes
    allowance = int(len(decisions) * _OPTIONS_VARIANCE_SHARE)
    if len(variants) > allowance:
        report.add(
            ValidationFinding(
                rule_id="CG-2",
                severity=Severity.WARNING,
                story_id=story.id,
                node_id=variants[allowance],
                message=(
                    f"CG-2 grammar: {len(variants)} of {len(decisions)} decision "
                    f"nodes vary from band '{band}' target [{lo}, {hi}], above the "
                    f"{_OPTIONS_VARIANCE_SHARE:.0%} allowance of {allowance} in "
                    f"story '{story.id}'; varying nodes: "
                    f"{', '.join(sorted(variants))} (advisory only, new-content "
                    "grammar per ADR-011 section 10)"
                ),
            )
        )
    return report


def check_words_per_stop(story: Storybook) -> ValidationReport:
    """CG-3: cap a composed stop's word count for the flowed bands.

    Mirrors ``player/stops.py::compose_stop``'s node sequence: a run's
    consecutive single-choice nodes plus the branch/ending node it flows
    into. Skips a run whose word count cannot be determined (any member body
    still carries a ``<<FILL`` directive but the story is not otherwise
    unfilled -- see :func:`_word_count`, which handles the pre-fill case by
    reading the declared target, so this only truly skips a mixed
    filled/unfilled body, which should not occur in practice).

    Args:
        story: The parsed Storybook to check.

    Returns:
        ValidationReport: WARNING findings, one per over-ceiling composed
            stop.
    """
    report = ValidationReport()
    band = story.metadata.age_band.value
    ceiling = _WORDS_PER_STOP_CEILING.get(band)
    if ceiling is None:
        return report
    nodes_by_id = {node.id: node for node in story.nodes}
    for run in _find_runs(story):
        run_length = len(run.node_ids)
        head_id = run.node_ids[0]
        if run_length < 2 and run.terminal_id is None:
            # A trivial single-node, no-terminal shape (a loop of length 1, or a
            # dangling reference) has no composed stop to measure; the standalone
            # sweep below covers the node on its own.
            continue
        member_ids = list(run.node_ids)
        if run.terminal_id is not None:
            member_ids.append(run.terminal_id)
        bodies = [nodes_by_id[nid].body for nid in member_ids if nid in nodes_by_id]
        if len(bodies) != len(member_ids):
            continue
        words = sum(_word_count(body) for body in bodies)
        if words <= ceiling:
            continue
        report.add(
            ValidationFinding(
                rule_id="CG-3",
                severity=Severity.WARNING,
                story_id=story.id,
                node_id=head_id,
                message=(
                    f"CG-3 grammar: composed stop starting at node '{head_id}' "
                    f"totals ~{words} words, above band '{band}' words-per-stop "
                    f"ceiling {ceiling} in story '{story.id}' (advisory only; "
                    f"stop nodes: {member_ids})"
                ),
            )
        )
    _check_standalone_stops(story, band, ceiling, report)
    return report


def _check_standalone_stops(
    story: Storybook, band: str, ceiling: int, report: ValidationReport
) -> None:
    """CG-3 for a node that is a rendered stop all by itself.

    ``_find_runs`` yields runs of consecutive SINGLE-CHOICE nodes, so a decision
    or ending node with nothing in front of it heads no run and was never
    measured. That inverted the rule's own incentive: at 8-11 a single 200-word
    decision node drew no finding, while the same material split into a 70-word
    no-decision node plus a 70-word decision, **60 words fewer in total**, fired
    CG-3. An author could silence the rule by MERGING nodes, which is the
    opposite of what it wants, and up to PL-19's per-node max went unmeasured at
    every band (`AL-452`, `UW-C276`).

    A node the reader meets on its own IS a stop of one, so it is measured
    against the same ceiling. This is the same rule, not a second one; it is
    split out only because the run sweep above cannot express it.

    Args:
        story: The parsed Storybook.
        band: The story's age band value.
        ceiling: The band's words-per-stop ceiling.
        report: The report to append to.
    """
    composed: set[str] = set()
    for run in _find_runs(story):
        composed.update(run.node_ids)
        if run.terminal_id is not None:
            composed.add(run.terminal_id)
    for node in story.nodes:
        if node.id in composed:
            continue
        words = _word_count(node.body)
        if words <= ceiling:
            continue
        report.add(
            ValidationFinding(
                rule_id="CG-3",
                severity=Severity.WARNING,
                story_id=story.id,
                node_id=node.id,
                message=(
                    f"CG-3 grammar: node '{node.id}' is a rendered stop on its "
                    f"own at ~{words} words, above band '{band}' words-per-stop "
                    f"ceiling {ceiling} in story '{story.id}' (advisory only)"
                ),
            )
        )


def check_fill_gate_acknowledgment(story: Storybook) -> ValidationReport:
    """CG-4: flag a decision-child whose opening sentence shares no content word with its choice label.

    A heuristic proxy for ADR-011 section 10's "every choice is acknowledged
    in the immediately following prose" cross-cutting rule (see module
    docstring #ASSUME). Skips a target node whose body still carries a
    ``<<FILL`` directive (unfilled; nothing to check), and skips a
    comparison where either side tokenizes to zero content words (nothing
    meaningful to compare, e.g. an all-stopword label).

    Args:
        story: The parsed Storybook to check.

    Returns:
        ValidationReport: WARNING findings, one per unacknowledged choice.
    """
    report = ValidationReport()
    nodes_by_id = {node.id: node for node in story.nodes}
    for node in story.nodes:
        if not _is_decision(node):
            continue
        for choice in node.choices:
            target = nodes_by_id.get(choice.target)
            if target is None or _FILL_MARKER in target.body:
                continue
            body = strip_sentinels(target.body).strip()
            if not body:
                continue
            # #ASSUME: data-integrity: the opening sentence must come from a
            # splitter that knows an abbreviation from a full stop.
            # `utils.sentences.split_sentences` replaced a borrowed
            # `diversity.normalize.split_sentences` here (UW-C260, AL-390): a
            # node opening "Mr. Fez's table was..." previously had its
            # opening sentence read as the bare string "Mr.", which shares no
            # content word with any choice label and fired CG-4 unfixably.
            # #VERIFY: tests/unit/test_choice_grammar.py's
            # TestFillGateAcknowledgment covers the abbreviation-opening case;
            # tests/unit/test_sentences.py pins the splitter itself.
            sentences = split_sentences(body)
            opening = sentences[0] if sentences else body
            body_tokens = {
                tok.lower() for tok in tokenize(opening) if tok.lower() not in STOPWORDS
            }
            label_tokens = {
                tok.lower()
                for tok in tokenize(choice.label)
                if tok.lower() not in STOPWORDS
            }
            if not body_tokens or not label_tokens:
                continue
            if body_tokens & label_tokens:
                continue
            report.add(
                ValidationFinding(
                    rule_id="CG-4",
                    severity=Severity.WARNING,
                    story_id=story.id,
                    node_id=target.id,
                    choice_id=choice.id,
                    message=(
                        f"CG-4 grammar: node '{target.id}' (reached via choice "
                        f"'{choice.id}' labeled {choice.label!r} from node "
                        f"'{node.id}') has no content-word overlap between its "
                        f"opening sentence and the choice label in story "
                        f"'{story.id}' (advisory heuristic; may be a false "
                        "positive, see module docstring)"
                    ),
                )
            )
    return report


def check_choice_grammar(
    story: Storybook,
    *,
    enforce_grammar: bool = False,
    is_fill_result: bool = False,
) -> ValidationReport:
    """Run the CG-* advisories, each behind the flag that actually fits it.

    The two flags gate different rules on purpose, because CG-1 through CG-3
    and CG-4 need opposite inputs:

    - **CG-1/2/3 read STRUCTURE** (run lengths, fan widths, declared word
      targets), which a skeleton has, so they run behind ``enforce_grammar``
      per the D3/D11 grandfathering.
    - **CG-4 reads PROSE.** It compares a decision-child's opening sentence
      with its choice label, and skips any node whose body still holds a
      ``<<FILL`` directive. So it needs a fill RESULT and gets its own flag.

    Until 2026-08-18 one flag gated all four, and the only callers that set it
    (``scripts/check_skeleton.py --strict`` and ``generation.skeleton``) pass
    skeletons, where every body is a directive. **CG-4 therefore could not
    produce a finding anywhere**: across 70 skeletons the counts were CG-1 80,
    CG-2 344, CG-3 1617, CG-4 zero, so ADR-011 section 10's one explicit
    fill-gate rule ran at no gate at all (``UW-C280``). ``check_skeleton.py``'s
    own header said "CG-4 needs filled prose" while nothing ran it on filled
    prose.

    Splitting rather than flipping the single flag is deliberate: flipping it
    on the fill path would also switch CG-1/2/3 on there, which is a separate
    calibration decision with its own volume, not a side effect to take by
    accident.

    Args:
        story: The parsed Storybook to check.
        enforce_grammar: Run the structural advisories CG-1, CG-2 and CG-3.
            ``False`` (the default) keeps the grandfathered catalog silent.
        is_fill_result: Run CG-4. Set by the gate when ``context`` is
            ``"fill_result"``, the only posture where node bodies hold prose.

    Returns:
        ValidationReport: The enabled CG-* WARNING findings; ``report.ok`` is
            always ``True`` (advisory only, never blocks).
    """
    report = ValidationReport()
    if enforce_grammar:
        for finding in check_choiceless_run_cap(story).findings:
            report.add(finding)
        for finding in check_options_per_choice(story).findings:
            report.add(finding)
        for finding in check_words_per_stop(story).findings:
            report.add(finding)
    if is_fill_result:
        for finding in check_fill_gate_acknowledgment(story).findings:
            report.add(finding)
    return report
