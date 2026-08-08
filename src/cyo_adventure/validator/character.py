"""CH-* character envelope rules (ADR-028 decision 5).

These rules prove that a book declaring ``accepts_character`` is safe across
exactly the states a seeded reader can arrive in. They sit in their own
namespace rather than extending ``L2-*`` because, like ``SR-*``, they prove a
cross-artifact handoff rather than a within-story property: the character comes
from outside the book.

CH-1, CH-2, CH-5, CH-6, and CH-7 need no state-space walk; CH-3a, CH-3b, and
CH-4 below walk the story once per envelope entry state (plus once more for
the book's own declared initial) to prove a property across the states a
seeded reader can actually arrive in. CH-8 walks the story once more, always
against the book's own declared initials (never an envelope entry state), to
catch a build node whose branching would multiply that single baseline walk
past the cap before ``L2-12`` does; it runs whenever the envelope declares an
``archetype`` span, independent of the CH-3a/CH-3b/CH-4 walk-rule tier and
envelope-size gates below. It fires on every book that declares an
``archetype`` span at all, whether or not that book's own graph contains a
build node: a later, carrier-only book in a series receives an already-built
character and never sets ``archetype``, so the variable costs nothing in its
own walk, yet CH-8 still pays for (and can still reject on) the pre-flight
walk for it. That is a deliberate over-approximation rather than a claim the
book contains a build node; see the CH-8 row in
``docs/planning/validator-rules.md`` for the same statement.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Final

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.storybook.character_vocabulary import (
    ARCHETYPE_ROSTER,
    ARCHETYPE_VARIABLE_NAME,
    CANONICAL_CHARACTER_VARIABLES,
)
from cyo_adventure.validator.layer2 import ever_visible_choice_ids, validate_layer2
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)
from cyo_adventure.validator.series import (
    MAX_ENTRY_STATES,
    satisfying_ending_reachable,
)
from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    from cyo_adventure.storybook.evaluator import VarState
    from cyo_adventure.storybook.models import CharacterRange, Storybook, Variable


def validate_character(story: Storybook) -> ValidationReport:
    """Run every CH-* rule against one story.

    Args:
        story: The parsed story to validate.

    Returns:
        ValidationReport: Findings from all CH-* rules. Empty for a book that
        neither declares ``accepts_character`` nor uses a canonical name.
    """
    report = ValidationReport()
    declared = {variable.name: variable for variable in story.variables}

    # #CRITICAL: data integrity: `story.accepts_character` distinguishes
    # `None` ("did not opt in") from `{}` ("opted in and declared an empty
    # envelope"); `Storybook.accepts_character` carries its own #CRITICAL
    # marker protecting that round trip. This is the first place a `None`-vs-
    # `{}` collapse would change behaviour: a slip to `if not
    # story.accepts_character:` would route an opted-in empty envelope
    # through the opt-out branch below (CH-6's reserved-name check) instead of
    # the opt-in branch (CH-1/CH-2/CH-6/CH-5/CH-7), changing which findings an
    # opted-in-with-nothing-declared book can receive.
    # #VERIFY: tests/unit/test_character_rules.py::
    # test_ch7_still_runs_for_an_opted_in_book_with_an_empty_envelope
    if story.accepts_character is None:
        _check_ch6_reserved_names(story, declared, report)
        return report

    _check_ch1_names_and_types(story, declared, report)
    _check_ch2_range_equality(story, declared, report)
    _check_ch6_uncovered_canonical_names(story, declared, report)
    _check_ch5_envelope_size(story, report)
    _check_ch7_series_exclusivity(story, report)
    _check_ch8_build_node_cost(story, report)

    # CH-3a/CH-3b/CH-4 walk the story once per envelope entry state. Tier-1
    # mirrors Layer 2's own short-circuit (`validate_layer2` returns an empty
    # report for `story.metadata.tier == 1`), and a Tier-1 book can only reach
    # this branch with an empty envelope in the first place (any canonical
    # name in `accepts_character` would already be a CH-1 "no variable of
    # that name" finding, since Tier-1 stories declare no variables at all),
    # so skipping the walk here costs nothing a Tier-1 book could use anyway.
    #
    # #CRITICAL: data integrity: `envelope_states` materializes the full
    # Cartesian product and its own docstring says it is "not safe to call on
    # an envelope CH-5 has flagged without also checking CH-5's result".
    # `_check_ch5_envelope_size` above only *reports* an oversized envelope;
    # it does not stop this function from reaching `envelope_states` next. A
    # schema-valid Tier-2 story can declare a huge range (nothing upstream
    # bounds it beyond `MAX_ABS_STORY_INT`), so calling `envelope_states`
    # unconditionally lets a single crafted-or-buggy generation output drive
    # `run_gate` to a `MemoryError`, which in production is the generation
    # worker process, not a request handler with a timeout. Recompute the
    # size cheaply (`envelope_size` is O(#vars), never materializes a state)
    # and skip straight past the walk block when it is already over the cap.
    #
    # The same reasoning generalises past CH-5 to *any* CH ERROR already in
    # the report: the book is blocked either way, so the walk below would
    # prove nothing that is not already settled, and it is not free. Each
    # walk rule re-walks the story once per entry state, so an envelope at
    # the cap multiplies the Layer-2 walk by up to `MAX_ENTRY_STATES`;
    # measured on the largest catalog book, a CH-8 rejection that is already
    # decided in under a second then spent roughly eleven further seconds
    # walking a rejected book. Both conditions are kept rather than folded
    # into one: the size check is the memory guard and must survive
    # independently of CH-5's severity, while the error check is the time
    # guard and covers the rules (CH-8 above all) that decide rejection
    # without saying anything about envelope size.
    # #VERIFY: tests/unit/test_character_rules.py::
    # test_ch_walk_rules_skip_an_oversized_envelope_instead_of_enumerating_it
    # and test_ch_walk_rules_do_not_run_on_a_book_ch8_has_already_blocked
    envelope = story.accepts_character or {}
    if (
        story.metadata.tier != 1
        and not report.errors
        and envelope_size(envelope) <= MAX_ENTRY_STATES
    ):
        states = envelope_states(envelope)
        _check_ch3a_union_dead_branches(story, states, report)
        _check_ch3b_per_state_regressions(story, states, report)
        _check_ch4_satisfying_ending_reachable(story, states, report)

    return report


def _finding(story: Storybook, rule_id: str, message: str) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        story_id=story.id,
        message=message,
    )


def _check_ch1_names_and_types(
    story: Storybook, declared: dict[str, Variable], report: ValidationReport
) -> None:
    """CH-1: every envelope name is canonical and declared with a matching type."""
    envelope = story.accepts_character or {}
    for name in sorted(envelope):
        canonical = CANONICAL_CHARACTER_VARIABLES.get(name)
        if canonical is None:
            report.add(
                _finding(
                    story,
                    "CH-1",
                    (
                        f"CH-1 character: accepts_character declares '{name}', "
                        f"which is not in the canonical vocabulary "
                        f"{sorted(CANONICAL_CHARACTER_VARIABLES)}"
                    ),
                )
            )
            continue
        variable = declared.get(name)
        if variable is None:
            report.add(
                _finding(
                    story,
                    "CH-1",
                    (
                        f"CH-1 character: accepts_character declares '{name}' "
                        f"but the story declares no variable of that name"
                    ),
                )
            )
            continue
        if variable.type is not canonical.type:
            report.add(
                _finding(
                    story,
                    "CH-1",
                    (
                        f"CH-1 character: '{name}' is declared as "
                        f"{variable.type.value} but the canonical vocabulary "
                        f"defines it as {canonical.type.value}"
                    ),
                )
            )


def _check_ch2_range_equality(
    story: Storybook, declared: dict[str, Variable], report: ValidationReport
) -> None:
    """CH-2: each envelope range equals its variable's bounds and fits the vocabulary.

    Two requirements that are easy to conflate, with different jobs.

    **Equality** with the declared bounds, not containment, because G3's runtime
    clamp is to *declared* bounds. A narrower envelope would let the runtime
    silently admit a state the validator never walked, and the clamp is what
    makes that failure invisible.

    **Containment** within the canonical vocabulary range. This one is not part
    of ADR-028's "every state a reader can arrive in has been walked"
    guarantee, and it is worth being precise about why, so it is not later
    mistaken for a load-bearing part of it and relaxed on that basis. A book
    declaring ``archetype: 0..3`` walks exactly ``0..3`` and clamps a reader
    carrying ``5`` down to ``3``, so narrowing is already safe by the equality
    rule above. Containment earns its place against the *wider* direction, on
    two other grounds: CH-8 derives arity from ``len(ARCHETYPE_ROSTER)`` rather
    than from the document, so a wider-than-canonical declaration silently
    under-measures the real configuration count and falls through to L2-12
    blowing the walk cap, which is the opaque failure CH-8 exists to replace;
    and it keeps the proven state space inside the vocabulary, which the
    character writer path will assume when it projects a walked value back onto
    a persistent character.
    """
    envelope = story.accepts_character or {}
    for name in sorted(envelope):
        variable = declared.get(name)
        if variable is None:
            # CH-1 already reported this; a second finding adds no information.
            continue
        span = envelope[name]
        # #CRITICAL: data integrity: Variable.min and Variable.max default to
        # None, and you cannot equal an absent bound. Treating None as
        # "unbounded, therefore containing" would readmit exactly the silent
        # admission this rule exists to stop.
        # #VERIFY: tests/unit/test_character_rules.py::
        # test_ch2_rejects_a_variable_with_absent_bounds
        if variable.min is None or variable.max is None:
            report.add(
                _finding(
                    story,
                    "CH-2",
                    (
                        f"CH-2 character: '{name}' is in accepts_character but "
                        f"declares no min/max bounds; an opted-in variable must "
                        f"declare bounds equal to its envelope range "
                        f"{span.min}-{span.max}"
                    ),
                )
            )
            continue
        if (variable.min, variable.max) != (span.min, span.max):
            report.add(
                _finding(
                    story,
                    "CH-2",
                    (
                        f"CH-2 character: accepts_character range for '{name}' "
                        f"is {span.min}-{span.max} but the variable declares "
                        f"{variable.min}-{variable.max}; they must be equal"
                    ),
                )
            )
            continue
        canonical = CANONICAL_CHARACTER_VARIABLES.get(name)
        if canonical is None:
            # CH-1 already reported a non-canonical name; there is no
            # vocabulary range to contain it to.
            continue
        # #CRITICAL: data integrity: the canonical bounds are the only
        # code-owned bound on the envelope. Every other operand here comes
        # from the document, so a rule that compares only document values to
        # each other cannot bound the document at all: `archetype: 0..9`
        # declared consistently on both sides satisfies the equality check
        # above with zero findings.
        # #VERIFY: tests/unit/test_character_rules.py::
        # test_ch2_rejects_a_range_wider_than_the_canonical_vocabulary asserts
        # the canonical range appears in the message, so the check provably
        # reads CANONICAL_CHARACTER_VARIABLES and not a document value; and
        # test_ch2_rejects_a_lower_bound_below_the_canonical_vocabulary covers
        # the other side, since containment is two-sided.
        if not (canonical.min <= span.min and span.max <= canonical.max):
            report.add(
                _finding(
                    story,
                    "CH-2",
                    (
                        f"CH-2 character: accepts_character range for '{name}' "
                        f"is {span.min}-{span.max}, outside the canonical "
                        f"vocabulary range {canonical.min}-{canonical.max}; a "
                        f"book may narrow a canonical range but never widen it"
                    ),
                )
            )


def envelope_size(envelope: dict[str, CharacterRange]) -> int:
    """Return the number of states a character envelope admits.

    The product of each variable's inclusive range width. An empty envelope is
    one state, the empty assignment, which is the mathematically consistent
    value and keeps CH-5 silent for a book that opted in and declared nothing.

    Args:
        envelope: The parsed ``accepts_character`` mapping.

    Returns:
        int: The number of distinct entry states.
    """
    size = 1
    for span in envelope.values():
        size *= span.max - span.min + 1
    return size


def _check_ch5_envelope_size(story: Storybook, report: ValidationReport) -> None:
    """CH-5: an envelope above the entry-state cap is an ERROR, never truncated.

    SR-9 truncates and warns because a series chain's entry-state count is
    emergent from the sending book and the author cannot control it directly.
    An envelope is declared, so exceeding the cap is an authoring mistake with
    an obvious fix, and validating a truncated sample of a declared envelope
    would report a book clean over states nobody walked.
    """
    envelope = story.accepts_character or {}
    size = envelope_size(envelope)
    if size > MAX_ENTRY_STATES:
        report.add(
            _finding(
                story,
                "CH-5",
                (
                    f"CH-5 character: accepts_character admits {size} entry "
                    f"states, above the {MAX_ENTRY_STATES} cap; narrow a range "
                    f"or declare fewer variables"
                ),
            )
        )


def _check_ch6_reserved_names(
    story: Storybook, declared: dict[str, Variable], report: ValidationReport
) -> None:
    """CH-6 (opt-out half): a book that has not opted in may not use a canonical name.

    CH-6's full statement is "a canonical variable name may be declared only
    by a book that opted in AND covered it in the envelope"; this half proves
    the non-participating side, called only when ``story.accepts_character is
    None``. Without it, "a book omitting accepts_character behaves exactly as
    today" is false: G3 carry is name-match, so it seeds *any* book declaring
    a canonical name, opted in or not. The catalog scan found zero current
    clashes, so reserving the names costs nothing today. The opted-in half is
    ``_check_ch6_uncovered_canonical_names`` below.
    """
    for name in sorted(declared):
        if name in CANONICAL_CHARACTER_VARIABLES:
            report.add(
                _finding(
                    story,
                    "CH-6",
                    (
                        f"CH-6 character: '{name}' is a reserved canonical "
                        f"character variable, but this story declares no "
                        f"accepts_character envelope; rename the variable or "
                        f"opt in"
                    ),
                )
            )


def _check_ch6_uncovered_canonical_names(
    story: Storybook, declared: dict[str, Variable], report: ValidationReport
) -> None:
    """CH-6 (opt-in half): a declared canonical name must be covered by the envelope.

    CH-1 quantifies over *envelope* names, proving each is declared as a
    variable. This is the converse direction of the same correspondence: an
    opted-in book may still declare a canonical-named variable its envelope
    omits, and G3 carry is name-match, so the runtime would seed that
    variable from the reader's character over states this book's own Layer 2
    walk never proved, having walked only from the book's own declared
    initial for that variable. CH-2 does not catch this: it only ever walks
    envelope -> variable, never variable -> envelope. Called only when
    ``story.accepts_character is not None``.
    """
    envelope = story.accepts_character or {}
    for name in sorted(declared):
        if name in CANONICAL_CHARACTER_VARIABLES and name not in envelope:
            report.add(
                _finding(
                    story,
                    "CH-6",
                    (
                        f"CH-6 character: '{name}' is a reserved canonical "
                        f"character variable declared by this story, but "
                        f"accepts_character does not cover it; add it to the "
                        f"envelope or rename the variable"
                    ),
                )
            )


def _check_ch7_series_exclusivity(story: Storybook, report: ValidationReport) -> None:
    """CH-7: no character in a non-first book of a state-carrying series.

    Two independent sources of carried state entering one book is a
    composition this design has not proved, so v1 forbids it outright rather
    than guessing at precedence.
    """
    series = story.metadata.series
    if series is None:
        return
    if series.carries_state and series.book_index > 1:
        report.add(
            _finding(
                story,
                "CH-7",
                (
                    f"CH-7 character: book {series.book_index} of "
                    f"state-carrying series '{series.series_id}' may not also "
                    f"declare accepts_character"
                ),
            )
        )


def envelope_states(envelope: dict[str, CharacterRange]) -> list[VarState]:
    """Enumerate every distinct entry state a character envelope admits.

    The Cartesian product of each variable's inclusive range, in sorted
    variable-name order for determinism. An empty envelope returns a single
    empty-dict state (the empty assignment), matching :func:`envelope_size`'s
    convention that an opted-in-with-nothing-declared book still has exactly
    one state: the book's own declared initials.

    Args:
        envelope: The parsed ``accepts_character`` mapping.

    Returns:
        list[VarState]: One dict per distinct entry state. Bounded by
        :data:`~cyo_adventure.validator.series.MAX_ENTRY_STATES` in practice,
        because CH-5 already errors on any envelope admitting more; this
        function does not itself enforce the cap, so it is not safe to call
        on an envelope CH-5 has flagged without also checking CH-5's result.
    """
    names = sorted(envelope)
    ranges = [range(envelope[name].min, envelope[name].max + 1) for name in names]
    return [
        dict(zip(names, combination, strict=True))
        for combination in itertools.product(*ranges)
    ]


def _check_ch3a_union_dead_branches(
    story: Storybook, states: list[VarState], report: ValidationReport
) -> None:
    """CH-3a: a conditional choice invisible across every configuration, union-wide.

    L2-11 already proves this from the book's own declared initials alone.
    This rule extends the same "is this choice ever visible" test to the
    union of the baseline walk and a walk from every envelope entry state,
    because a choice a non-carried reader would never see might still be
    reachable for a reader who arrives already carrying some variable value,
    or vice versa (a book whose own internal effects, not any envelope state,
    set the variable in question can make a choice visible from the baseline
    walk alone, as in the "six-way archetype" fixture in
    ``tests/unit/test_character_rules.py``).

    Deliberately union-quantified rather than per-state: a choice invisible
    in one envelope state but visible in another (or at baseline) is not
    dead, it is state-gated exactly as its condition intends. Reporting it
    per state would rediscover every legitimately state-gated choice in a
    book like the six-way fixture as a false dead branch.

    Iterates every node rather than restricting to walk-reachable ones the
    way L2-11 does: a walk-unreachable node is already blocked by topology
    rules, so the extra findings here are noise on an already-failing book,
    not an unsound verdict on a clean one, and narrowing to reachable-only
    would need its own reachable-node computation this rule does not
    otherwise require.
    """
    engine = StoryEngine(story)
    baseline_result = walk_configurations(story)
    ever_visible = ever_visible_choice_ids(baseline_result, engine)
    capped = baseline_result.capped
    for state in states:
        state_result = walk_configurations(story, carried=state)
        capped = capped or state_result.capped
        ever_visible |= ever_visible_choice_ids(state_result, engine)

    # #CRITICAL: data integrity: a capped walk yields a partial `configs` map
    # (see `WalkResult.capped`'s docstring), so `ever_visible` is a partial
    # union, not the true one, whenever any walk above capped. This rule's
    # finding is a positive claim, "this choice is dead everywhere", which a
    # partial union cannot prove; it can only under-report visibility. Fail
    # OPEN here (stay silent) rather than raise a spurious ERROR off
    # incomplete data, the mirror image of `_check_ch3b_per_state_
    # regressions` below, which fails CLOSED on the same signal because its
    # finding is a negative claim ("no new defect") that a capped walk
    # equally cannot prove. `satisfying_ending_reachable` (CH-4's helper)
    # makes this same fail-open choice for the same reason: "cannot prove the
    # negative" defaults to "assume the positive holds", not to a report.
    # #VERIFY: tests/unit/test_character_rules.py::
    # test_ch3a_stays_silent_when_a_walk_caps
    if capped:
        return

    for node in story.nodes:
        for choice in node.choices:
            if choice.condition is None:
                continue  # unconditional choices are never dead branches
            if choice.id in ever_visible:
                continue
            report.add(
                ValidationFinding(
                    rule_id="CH-3a",
                    severity=Severity.ERROR,
                    story_id=story.id,
                    node_id=node.id,
                    choice_id=choice.id,
                    message=(
                        f"CH-3a character: choice '{choice.id}' on node "
                        f"'{node.id}' is never visible in the baseline walk "
                        f"or in any of the {len(states)} accepts_character "
                        f"entry states, in story '{story.id}'"
                    ),
                )
            )


_PER_STATE_RULES: Final[frozenset[str]] = frozenset({"L2-9", "L2-10", "L2-14"})


def _signature(finding: ValidationFinding) -> str:
    """Return an identity for a Layer-2 finding, for baseline diffing.

    #ASSUME: data integrity: this deliberately includes ``message``, unlike
    ``series._l2_error_signatures``'s ``rule_id|node_id`` (SR-9 needs to match
    the SAME structural defect across a DIFFERENT var_state: a continuation's
    carried state is almost never equal to the receiving book's own declared
    initial, so a message, which embeds var_state, would never match there
    even for the same defect). CH-3b's comparison runs the other way: it
    diffs each envelope state's findings against this SAME book's own
    baseline, and none of L2-9, L2-10, or L2-14 (``_PER_STATE_RULES``) ever
    set ``choice_id`` (only L2-11 does, and L2-11 is CH-3a's rule). Without
    the message, two dead ends on the same node at two different var_states
    collapse into one signature, and a reader who arrives at a var_state the
    book's own baseline never suffers gets silently waved through as "already
    known". Including the message, which embeds var_state, is what lets a
    truly new per-state defect survive the diff while the book's own,
    already-known baseline defect still gets suppressed.
    #VERIFY: test_ch3b_distinguishes_two_dead_branches_on_one_node exercises
    this directly; docs/planning/authoring-lessons-log.md records the
    fixture/signature investigation that found the weaker signature masks it.

    Args:
        finding: A Layer-2 ``ValidationFinding``.

    Returns:
        str: A signature stable across runs for the same book and var_state.
    """
    return (
        f"{finding.rule_id}|{finding.node_id or ''}|{finding.choice_id or ''}"
        f"|{finding.message}"
    )


def _render_state(state: VarState) -> str:
    """Render an entry state compactly and deterministically for a message."""
    return "{" + ", ".join(f"{name}={state[name]}" for name in sorted(state)) + "}"


def _check_ch3b_per_state_regressions(
    story: Storybook, states: list[VarState], report: ValidationReport
) -> None:
    """CH-3b: an envelope entry state must not introduce a new per-state defect.

    L2-9 (stateful dead end), L2-10 (loop escape), and L2-14 (all-forbidden
    decision) are per-state properties: whether a configuration is a dead
    end, cannot escape, or offers only forbidden outcomes depends on the
    variable state it is reached in, unlike L2-11's union-wide "ever visible"
    question (CH-3a's rule). A book may already carry one of these defects
    from its own declared initials; that is this book's own accepted
    baseline, not a regression the envelope introduced. This rule walks each
    envelope state, and reports the L2-9/L2-10/L2-14 findings that do not
    also appear in the baseline walk, per :func:`_signature`. Because the
    signature embeds the raising state's own values, a structurally
    identical baseline defect is suppressed once per matching state rather
    than once overall; a differing entry state re-reports it, which is
    harmless (any baseline L2-9/L2-10/L2-14 ERROR already blocks the gate
    through the ``"L2"`` prefix in ``gate.py``) but means "does not also
    appear in the baseline walk" above is a per-state, not a global,
    statement.
    """
    baseline_errors = validate_layer2(story).errors
    baseline = {
        _signature(finding)
        for finding in baseline_errors
        if finding.rule_id in _PER_STATE_RULES
    }
    for state in states:
        state_errors = validate_layer2(story, carried=state).errors
        # #CRITICAL: data integrity: `validate_layer2` returns *only* an
        # L2-12 finding when its own walk caps (see its docstring), and
        # L2-12 is not in `_PER_STATE_RULES`, so the loop below would
        # otherwise drop a capped state silently: it would contribute no
        # finding and read exactly like a state with no defect at all. Fail
        # CLOSED here, unlike `_check_ch3a_union_dead_branches` above, which
        # fails open on the same signal: that rule's finding is a positive
        # claim a partial walk cannot prove, but this rule's whole job is to
        # prove a negative ("no new defect"), and a capped walk cannot prove
        # a negative either. Reporting a capped state as clean would be a
        # silent false negative on exactly the case this rule exists to
        # catch.
        # #VERIFY: tests/unit/test_character_rules.py::
        # test_ch3b_reports_a_capped_per_state_walk_instead_of_passing_it_clean
        if any(finding.rule_id == "L2-12" for finding in state_errors):
            report.add(
                ValidationFinding(
                    rule_id="CH-3b",
                    severity=Severity.ERROR,
                    story_id=story.id,
                    message=(
                        f"CH-3b character: accepts_character entry state "
                        f"{_render_state(state)} could not be fully walked "
                        f"(L2-12 configuration cap), so its L2-9/L2-10/"
                        f"L2-14 safety cannot be proven, in story "
                        f"'{story.id}'"
                    ),
                )
            )
            continue
        for finding in state_errors:
            if finding.rule_id not in _PER_STATE_RULES:
                continue
            if _signature(finding) in baseline:
                continue
            report.add(
                ValidationFinding(
                    rule_id="CH-3b",
                    severity=Severity.ERROR,
                    story_id=story.id,
                    node_id=finding.node_id,
                    choice_id=finding.choice_id,
                    message=(
                        f"CH-3b character: accepts_character entry state "
                        f"{_render_state(state)} raises {finding.rule_id}, "
                        f"which this book's own baseline walk does not: "
                        f"{finding.message}"
                    ),
                )
            )


def _check_ch4_satisfying_ending_reachable(
    story: Storybook, states: list[VarState], report: ValidationReport
) -> None:
    """CH-4: every envelope entry state must still be able to reach a win.

    Reuses SR-9's own reachability test
    (:func:`~cyo_adventure.validator.series.satisfying_ending_reachable`)
    rather than a second implementation, so "the reader can still win" cannot
    silently drift between the series continuation case and the character
    envelope case.
    """
    for state in states:
        if satisfying_ending_reachable(story, state):
            continue
        report.add(
            ValidationFinding(
                rule_id="CH-4",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"CH-4 character: accepts_character entry state "
                    f"{_render_state(state)} cannot reach any satisfying "
                    f"ending, in story '{story.id}'"
                ),
            )
        )


# The walk cap CH-8 divides by. Kept as a module constant rather than read from
# walk_configurations' default so that changing the walk's cap is a deliberate
# two-place edit; silently re-deriving this threshold would move the authoring
# contract without anyone deciding to.
_WALK_CAP: Final[int] = 100_000


def build_node_headroom(story: Storybook, *, arity: int) -> bool:
    """Report whether a story's base closure can host a build node.

    A declared-but-never-set variable is a constant within a walk and costs
    nothing. A build node sets ``archetype``, so it takes ``arity`` distinct
    values along different paths and every downstream node forks that many
    ways. Measured at 6.00x on ``10-13/the-glass-comet``.

    Args:
        story: The story to measure.
        arity: The build node's branching factor, that is, how many distinct
            values it can set.

    Returns:
        bool: True if the base closure leaves room for the idiom.
    """
    if arity < 1:
        msg = f"build node arity must be at least 1, got {arity}"
        raise ValueError(msg)
    baseline = walk_configurations(story)
    if baseline.capped:
        return False
    return len(baseline.configs) <= _WALK_CAP // arity


def _check_ch8_build_node_cost(story: Storybook, report: ValidationReport) -> None:
    """CH-8: a book too large to host its build node fails before L2-12.

    Without this the author meets the same wall as an opaque L2-12 cap ERROR,
    which names the walk rather than the cause and offers no fix.

    Fires whenever the envelope declares an ``archetype`` span at all, even
    for a carrier-only later book in a series whose own graph never sets
    ``archetype`` and so pays no real build-node cost; see the module
    docstring above and the CH-8 row in ``docs/planning/validator-rules.md``
    for the same over-approximation statement.

    #CRITICAL: data integrity: ``arity`` must never be read from the
    envelope's declared ``archetype`` span (``span.min``/``span.max``),
    because those bounds are schema-valid, attacker-influenced values from a
    generation-pipeline artifact, and nothing upstream ties either bound to
    the canonical archetype count: CH-1 checks only the variable's *type*
    against the vocabulary, and CH-2 checks only that the envelope equals
    the *declared* variable, not that the declared variable equals the
    canonical ``0..6``. A book can declare both its ``archetype`` variable
    and its envelope span as ``1..6``, which is schema-valid, passes CH-1 and
    CH-2, and still lets an in-story build node set any of the same six real
    archetype values (1-6) that a full ``0..6`` declaration would; reading
    ``span.max - span.min`` from that declaration computes 5, not 6, moving
    this rule's threshold from 16,666 to 20,000 configurations and letting a
    19,236-config book through with zero findings from any rule, with
    ``run_gate`` then returning ``blocked=False``. Deriving ``arity`` from
    ``len(ARCHETYPE_ROSTER)`` instead reads the one place the real count is
    not document-controlled: the roster is a module-level ``Final`` tuple
    this rule's caller cannot influence.
    ``len(ARCHETYPE_ROSTER)`` is a CHOICES count (the build node sets one of
    six real archetypes, values 1-6), not a STATES count: ``ARCHETYPE_UNCHOSEN``
    (0) is a seventh legal *state* the variable can rest in before the build
    node runs, but the build node itself never *sets* that state, so it does
    not enter the branching factor this rule measures.
    #VERIFY: tests/unit/test_character_rules.py::
    test_ch8_rejects_a_narrow_declared_span_that_still_means_six_archetypes
    """
    envelope = story.accepts_character or {}
    if ARCHETYPE_VARIABLE_NAME not in envelope:
        # Only a mutable in-book variable multiplies the walk. Gamebook stats
        # are seeded and never set, so they stay constant and cost nothing.
        return
    arity = len(ARCHETYPE_ROSTER)
    # Reruns its own baseline walk rather than reusing CH-3a's (measured at
    # about 0.3s of a 4.8s gate run on the largest catalog book): the two
    # rules stay independent modules that never need to agree on a shared
    # walk's lifetime. Cheap enough at this scale that the coupling is not
    # worth the cost of a shared cache.
    if build_node_headroom(story, arity=arity):
        return
    threshold = _WALK_CAP // arity
    report.add(
        _finding(
            story,
            "CH-8",
            (
                f"CH-8 character: a {arity:,}-way build node needs a base "
                f"closure at or under {threshold:,} configurations, which "
                f"this book exceeds; it cannot host the archetype "
                f"build-node idiom"
            ),
        )
    )
