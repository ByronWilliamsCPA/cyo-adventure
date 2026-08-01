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

Grandfathering (D3/D11)
------------------------
The existing 61-skeleton catalog predates this grammar and is grandfathered:
no machine-readable "this skeleton is grandfathered" marker exists yet (the
D11 ``deprecated`` marker is tracked as future work, W2.4). Until that marker
lands, every check in this module is gated behind the ``enforce_grammar``
keyword (default ``False``) on :func:`check_choice_grammar`; a promotion-path
caller for genuinely new skeletons opts in explicitly. The individual
``check_*`` functions below run unconditionally when called directly (for
unit testing and for a future promotion path that wants one rule at a time);
only the combinator applies the gate.

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

from cyo_adventure.diversity.normalize import STOPWORDS, split_sentences, tokenize
from cyo_adventure.storybook.sentinels import strip_sentinels
from cyo_adventure.validator.report import Severity, ValidationFinding, ValidationReport

if TYPE_CHECKING:
    from cyo_adventure.storybook.models import Node, Storybook

# A skeleton body is a ``<<FILL role=... words=N ...>>`` directive, not prose;
# mirrors reading_level.py's and policy.py's identical constant (each
# validator module keeps its own copy deliberately, per policy.py's header
# note, so no module depends on another for a one-line marker).
_FILL_MARKER = "<<FILL"
_FILL_WORDS_RE = re.compile(r"\bwords=(\d+)")

# Choiceless-run cap: discrete-page bands (3-5, 5-8) cap the run length
# directly; flowed bands (8-11 and up) tolerate longer linear beats in the
# graph (ADR-026: they flow into one rendered stop) and are capped instead at
# the point a composed run would blow the words-per-stop budget for any
# plausible per-node length, which the ADR-011 section 10 table amendment
# fixes at 6.
_DISCRETE_RUN_CAP: dict[str, int] = {"3-5": 3, "5-8": 2}
_FLOWED_RUN_CAP = 6
_FLOWED_BANDS: frozenset[str] = frozenset({"8-11", "10-13", "13-16", "16+"})

# Options-per-choice bounds (inclusive), ADR-011 section 10 "Options per
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
    "8-11": 135,
    "10-13": 150,
    "13-16": 200,
    "16+": 230,
}


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
    return report


def check_options_per_choice(story: Storybook) -> ValidationReport:
    """CG-2: bound how many choices a decision node offers, per band.

    Args:
        story: The parsed Storybook to check.

    Returns:
        ValidationReport: WARNING findings, one per out-of-bounds decision
            node.
    """
    report = ValidationReport()
    band = story.metadata.age_band.value
    bounds = _OPTIONS_BOUNDS.get(band)
    if bounds is None:
        return report
    lo, hi = bounds
    for node in story.nodes:
        if not _is_decision(node):
            continue
        count = len(node.choices)
        if lo <= count <= hi:
            continue
        report.add(
            ValidationFinding(
                rule_id="CG-2",
                severity=Severity.WARNING,
                story_id=story.id,
                node_id=node.id,
                message=(
                    f"CG-2 grammar: node '{node.id}' offers {count} choices, "
                    f"outside band '{band}' bounds [{lo}, {hi}] in story "
                    f"'{story.id}' (advisory only, new-content grammar per "
                    "ADR-011 section 10)"
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
            # A trivial single-node, no-terminal shape (a loop of length 1,
            # or a dangling reference) carries no composed word budget of its
            # own; the per-node ceiling (PL-19/words_per_node_profile) already
            # covers a single node.
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
    return report


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
    story: Storybook, *, enforce_grammar: bool = False
) -> ValidationReport:
    """Run every CG-* advisory, gated behind ``enforce_grammar`` (D3/D11).

    Args:
        story: The parsed Storybook to check.
        enforce_grammar: When ``False`` (the default), returns an empty
            report unconditionally -- the grandfathered catalog and any
            caller that has not opted in produce no CG-* findings. When
            ``True``, runs CG-1 through CG-4 and merges their findings. A
            future promotion-path caller for genuinely new skeletons is
            expected to pass ``True``.

    Returns:
        ValidationReport: All CG-* WARNING findings; ``report.ok`` is always
            ``True`` (advisory only, never blocks).
    """
    report = ValidationReport()
    if not enforce_grammar:
        return report
    for finding in check_choiceless_run_cap(story).findings:
        report.add(finding)
    for finding in check_options_per_choice(story).findings:
        report.add(finding)
    for finding in check_words_per_stop(story).findings:
        report.add(finding)
    for finding in check_fill_gate_acknowledgment(story).findings:
        report.add(finding)
    return report
