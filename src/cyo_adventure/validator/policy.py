"""Age-policy gate layer (rules PL-15..PL-26, plus the PL-22 fail-closed guard).

Runs after Layer 1 passes and the Storybook parses, on the typed model plus the
choice graph. Most findings are ERROR-severity and blocking; the PL-19 story-mean
words-per-node check, the PL-20 arc ceiling, PL-25's *ceiling* short of its hard
limit, and all of PL-26 are advisory (WARNING). PL-25's floor is an ERROR. These
rules convert age-safety, shape, and story-scale judgments into deterministic
invariants.

Path-length rules grade in two tiers on purpose. A *floor* violation (PL-20: too
short to be a story) is a correctness failure and blocks. A *ceiling* violation
(PL-20's long arc, PL-25's buried first choice) is a craft failure and warns,
because the ERROR tier means unpublishable. PL-25 keeps one blocking tier past
``ARC_CEILING_MULTIPLE`` times the band ceiling, where the shape has left the
observed genre rather than merely run slow. Both of PL-25's bounds are measured
in nodes *or* in the words those nodes stand for, because its source corpus
counts pages rather than authoring units; see ``_opening_in_word_window``.

Two axes are in play and are easy to confuse. PL-17 measures *breadth*: how many
decision and ending nodes exist anywhere in the graph. PL-20, PL-25, and PL-26
measure *depth along a walk*: how long the reader travels, how soon they first
steer, and how often they steer after that. A story can satisfy every breadth
floor while walking the reader down a corridor, which is the gap PL-26 closes.

Rule sources: docs/planning/validator-rules.md (PL-15..PL-18);
docs/planning/adr/adr-011-story-scale-framework.md (PL-19
words-per-node, PL-20 fastest-finish arc floor, and PL-21 off-matrix rejection).
PL-22 (band profile not configured, fail closed) is a runtime invariant added
2026-07-16 and is not yet reflected in validator-rules.md. PL-25
(depth to first decision) and PL-26 (decision density on the fastest finish) are
anchored on Adams, Beckelhymer and Marr, Journal of Humanistic Mathematics 9(2),
2019, DOI 10.5642/jhummath.201902.05; see band_profile for the measurements.
"""

from __future__ import annotations

import heapq
import math
import re
from dataclasses import dataclass
from typing import Literal

import networkx as nx

from cyo_adventure.storybook.models import (
    EndingKind,
    NarrativeStyle,
    Storybook,
    Valence,
    level_rank,
)
from cyo_adventure.validator.band_profile import (
    ARC_CEILING_MULTIPLE,
    BandProfile,
    breadth_scaled_floors,
    cell_ending_bounds,
    first_decision_window,
    is_offered_cell,
    min_complete_floor,
    nodes_per_decision_ceiling,
    profile_for,
    reading_pace_wpm,
    words_per_node_profile,
)
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)
from cyo_adventure.validator.topology import (
    BAND_TOPOLOGIES,
    admissible_topologies,
)

# A skeleton node body is a ``<<FILL role=... words=N ...>>`` directive carrying
# the author's declared word target; a filled node body is prose. The
# words-per-node check reads the declared target for skeletons and the actual
# word count for prose, so it applies pre-fill and post-fill. This regex is a
# local copy (not imported from generation.diagram) to keep the validator from
# depending on the generation layer.
_FILL_MARKER = "<<FILL"
_FILL_WORDS_RE = re.compile(r"\bwords=(\d+)")

# Endings that count as a *satisfying* completion for the PL-20 arc floor. A
# fail-fast negative ending (setback/death/capture) may be reached quickly; only
# a win must be earned over the cell's minimum node count.
_SATISFYING_KINDS = frozenset({EndingKind.SUCCESS, EndingKind.COMPLETION})


def check_fill_residue(story: Storybook) -> ValidationReport:
    """Run PL-27: no prose of a *fill result* may still be a directive.

    Covers node bodies and choice labels: both are fillable, both are
    reader-visible, and only the body was checked until `AL-430`.

    Deliberately not part of :func:`validate_policy`, because it is the one
    policy rule whose correctness depends on what the caller is validating.
    Every other checker in the gate treats a ``<<FILL ...>>`` body as input it
    cannot judge and skips it, which is right at catalog time (a skeleton is
    supposed to be directives) and wrong after a fill (a directive means the
    node was never written). Collectively those skips mean an unwritten book
    clears topology, safety, choice grammar and reading level without a single
    finding: a gate assembled entirely from abstainers has no floor (AL-325).

    #CRITICAL: data integrity: this is the only deterministic check standing
    between an unwritten book and a human reviewer. AL-327 showed the
    orchestrator returns the authoring skeleton as a passing book when a fill
    produces no parseable document, and AL-324 showed Stage 1 fidelity review
    is off by default for every non-worker caller, so without PL-27 there is
    no automated floor at all on that path.
    #VERIFY: see test_gate.py, functions
    test_fill_result_context_blocks_on_retained_directive and
    test_skeleton_context_tolerates_retained_directive, which prove the rule
    blocks under the fill-result posture and stays silent under the skeleton
    posture.

    Args:
        story: The validated Storybook (Layer 1 has already passed).

    Returns:
        ValidationReport: One ERROR finding per node whose body retains a
        directive, plus one per choice whose label retains one; empty when every
        body and every label holds prose.
    """
    report = ValidationReport()
    for node in story.nodes:
        if _FILL_MARKER in node.body:
            report.add(
                ValidationFinding(
                    rule_id="PL-27",
                    severity=Severity.ERROR,
                    story_id=story.id,
                    node_id=node.id,
                    message=(
                        f"PL-27 policy: node '{node.id}' of story '{story.id}' was "
                        f"validated as a fill result but its body still holds a "
                        f"'{_FILL_MARKER}' directive, so the node was never written"
                    ),
                )
            )
        # A choice label is reader-visible button text, and it was the one piece
        # of fillable prose no deterministic rule covered: this checker tested
        # `node.body` only, `has_unfilled_directives` likewise, and `Choice.label`
        # carries only `min_length=1`. The chunked fill writes labels as well as
        # bodies, so a reply echoing its directive back under `choices` produced a
        # book that cleared this gate unblocked with a raw directive on a button.
        # Guarded at the merge too (`generation/chunking.py::_merged_labels`);
        # this is the deterministic floor that does not depend on which fill path
        # wrote the document (`AL-430`).
        for choice in node.choices:
            if _FILL_MARKER not in choice.label:
                continue
            report.add(
                ValidationFinding(
                    rule_id="PL-27",
                    severity=Severity.ERROR,
                    story_id=story.id,
                    node_id=node.id,
                    message=(
                        f"PL-27 policy: choice '{choice.id}' of node '{node.id}' in "
                        f"story '{story.id}' was validated as a fill result but its "
                        f"label still holds a '{_FILL_MARKER}' directive, so the "
                        f"choice text was never written"
                    ),
                )
            )
    return report


def check_mvp_firewall(story: Storybook) -> ValidationReport:
    """Run PL-28: an MVP/Test seed may not be imported as a child-facing book.

    ADR-011 section 1a creates a below-Short **MVP/Test tier** for cheap
    prototyping shells and its Consequences require that the tier be
    "firewalled from production: a skeleton tagged ``tier = 'mvp'`` must never
    be selectable for a child-facing story. The selection layer, not just the
    validator, has to enforce the exclusion."

    The selection layer does enforce it:
    ``generation/skeleton_match.py::_production_candidates`` drops any skeleton whose
    ``production_eligible`` is ``False``, so the automated request path cannot
    pick a seed to fill. That covers generation and nothing else.

    #CRITICAL: security: the *manual* path had no such guard. A seed filled by
    hand (the `cyo-author` skill) and imported through
    ``generation/import_cli`` reached the store, publishing and a child's
    library with nothing anywhere reading ``production_eligible``: the flag's
    only other consumers are ``generation/diagram.py`` (rendering) and
    ``generation/import_catalog.py`` (backfill). Worse than a missing check,
    the flag makes the gate *more* permissive rather than less, because
    ``validator/layer1.py`` budgets an MVP story against the loosest cell. So
    a prototype shell was both easier to validate and unblocked to publish.
    Measured 2026-08-16: all three seeds ADR-011 names by slug (Lost Mitten,
    Clocktower Cipher, Sunken Signal) already had filled books sitting in the
    corpus.
    #VERIFY: see test_gate.py::test_fill_result_context_blocks_an_mvp_seed,
    ::test_skeleton_context_tolerates_an_mvp_seed, and
    ::test_a_production_story_is_untouched_by_the_mvp_firewall.

    Context-gated for the same reason PL-27 is: at catalog time a seed is a
    legitimate object that ``check_skeleton.py --allow-mvp`` is built to
    inspect, so this must stay silent under the ``"skeleton"`` posture and
    fire only once the document is being treated as a finished book.

    Args:
        story: The validated Storybook (Layer 1 has already passed).

    Returns:
        ValidationReport: One ERROR finding when the story is an MVP seed,
        empty otherwise.
    """
    report = ValidationReport()
    if story.metadata.production_eligible:
        return report
    report.add(
        ValidationFinding(
            rule_id="PL-28",
            severity=Severity.ERROR,
            story_id=story.id,
            node_id=None,
            message=(
                f"PL-28 policy: story '{story.id}' declares "
                f"production_eligible=false (the ADR-011 MVP/Test tier) and so "
                f"may not be imported as a child-facing book; MVP seeds are "
                f"prototyping shells and are budgeted against the loosest cell"
            ),
        )
    )
    return report


def validate_policy(story: Storybook) -> ValidationReport:
    """Run PL-15..PL-18 over a parsed story.

    When the story's band has no configured :class:`BandProfile`, the gate
    fails CLOSED: it returns a single blocking PL-22 finding instead of
    silently skipping the remaining age-safety checks (owner ruling
    2026-07-16).

    Args:
        story: The validated Storybook (Layer 1 has already passed).

    Returns:
        ValidationReport: Policy findings; ``ok`` is ``True`` when none are errors.
    """
    report = ValidationReport()
    profile = profile_for(story.metadata.age_band.value)
    if profile is None:
        # #CRITICAL: security: a band with no configured profile must fail
        # CLOSED. Owner ruling 2026-07-16: this branch used to return an
        # empty report, which silently skipped every age-safety check
        # (PL-15/16/17) for the band, so a forbidden ending or over-ceiling
        # content could pass review unvalidated. It now emits a blocking
        # PL-22 finding through the same report mechanism as every other
        # policy rule, so an unconfigured band can never reach a human
        # reviewer without a visible, blocking finding.
        # #VERIFY: see test_policy.py, function
        # test_validate_policy_fails_closed_when_profile_is_none, which proves
        # this branch blocks at runtime. See also test_band_profile.py,
        # function test_profiles_match_age_band_enum_exactly, kept as defense
        # in depth: it asserts the AgeBand enum and band_profile._PROFILES
        # keys stay in lockstep, so this branch stays unreachable through any
        # valid, enum-constrained age_band; the PL-22 finding is the runtime
        # backstop if that lockstep ever drifts.
        report.add(
            ValidationFinding(
                rule_id="PL-22",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-22 policy: band profile not configured for band "
                    f"'{story.metadata.age_band.value}' in story '{story.id}'; "
                    f"refusing to validate age safety"
                ),
            )
        )
        return report
    _check_forbidden_kinds(story, profile, report)
    _check_band_topology(story, report)
    _check_content_ceiling(story, profile, report)
    _check_floors(story, profile, report)
    _check_topology(story, report)
    _check_words_per_node(story, report)
    _check_min_to_complete(story, report)
    _check_first_decision_depth(story, report)
    _check_declared_read_time(story, report)
    _check_ending_mix(story, report)
    _check_off_matrix_cell(story, report)
    return report


def _check_forbidden_kinds(
    story: Storybook, profile: BandProfile, report: ValidationReport
) -> None:
    """PL-15: no ending may use a kind forbidden for the band."""
    # #CRITICAL: security: this is the age-safety boundary, an ending whose kind
    # is forbidden for the band (e.g. a 'death' ending for ages 3-5) must block.
    # #VERIFY: profile.forbidden_ending_kinds is the per-band denylist; tests
    # cover both forbidden kinds (death and capture) for the young bands.
    for node in story.nodes:
        if (
            node.ending is None
            or node.ending.kind not in profile.forbidden_ending_kinds
        ):
            continue
        report.add(
            ValidationFinding(
                rule_id="PL-15",
                severity=Severity.ERROR,
                story_id=story.id,
                node_id=node.id,
                message=(
                    f"PL-15 policy: ending kind '{node.ending.kind.value}' is "
                    f"forbidden for band '{story.metadata.age_band.value}' in story "
                    f"'{story.id}'"
                ),
            )
        )


def _check_content_ceiling(
    story: Storybook, profile: BandProfile, report: ValidationReport
) -> None:
    """PL-16: each declared content flag must not exceed the band ceiling."""
    flags = story.metadata.content_flags
    declared = (
        ("violence", flags.violence),
        ("scariness", flags.scariness),
        ("peril", flags.peril),
    )
    for name, level in declared:
        ceiling = profile.content_ceiling[name]
        if level_rank(level) > level_rank(ceiling):
            report.add(
                ValidationFinding(
                    rule_id="PL-16",
                    severity=Severity.ERROR,
                    story_id=story.id,
                    message=(
                        f"PL-16 policy: {name} '{level.value}' exceeds band "
                        f"'{story.metadata.age_band.value}' ceiling "
                        f"'{ceiling.value}' in story '{story.id}'"
                    ),
                )
            )


def _build_graph(story: Storybook) -> nx.DiGraph[str]:
    """Build the directed choice graph from a parsed story."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node.id for node in story.nodes)
    for node in story.nodes:
        for choice in node.choices:
            graph.add_edge(node.id, choice.target)
    return graph


def _effective_floors(story: Storybook, profile: BandProfile) -> tuple[int, int, bool]:
    """Return the ``(min_endings, min_decisions, scaled)`` PL-17 floors.

    A scale-classified production story (one that declares a ``length``) scales
    its floors with node count so a large world cannot pass with the band-scale
    minimums: the effective floor is the ``max`` of the band floor and the
    breadth-scaled floor, so a small scale story never drops below its band
    minimum. Any other story keeps the band floors unchanged. See ADR-011
    section 6.

    Args:
        story: The parsed Storybook.
        profile: The band policy profile supplying the absolute floors.

    Returns:
        The effective ``min_endings`` and ``min_decisions`` and whether the
        breadth-scaled floor was applied (for the finding message).
    """
    if story.metadata.length is None or not story.metadata.production_eligible:
        return profile.min_endings, profile.min_decisions, False
    bounds = cell_ending_bounds(
        story.metadata.age_band.value,
        story.metadata.length.value,
        story.metadata.narrative_style.value,
    )
    scaled_endings, scaled_decisions = breadth_scaled_floors(
        len(story.nodes),
        story.metadata.narrative_style.value,
        None if bounds is None else bounds[1],
    )
    return (
        max(profile.min_endings, scaled_endings),
        max(profile.min_decisions, scaled_decisions),
        True,
    )


def _check_floors(
    story: Storybook, profile: BandProfile, report: ValidationReport
) -> None:
    """PL-17: endings and decision nodes must meet the (possibly scaled) floors."""
    endings = sum(1 for node in story.nodes if node.is_ending)
    decisions = sum(
        1 for node in story.nodes if not node.is_ending and len(node.choices) >= 2
    )
    min_endings, min_decisions, scaled = _effective_floors(story, profile)
    scope = "scale-adjusted" if scaled else f"band '{story.metadata.age_band.value}'"
    if endings < min_endings:
        report.add(
            ValidationFinding(
                rule_id="PL-17",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-17 floor: {endings} ending(s) below {scope} minimum "
                    f"{min_endings} in story '{story.id}'"
                ),
            )
        )
    if decisions < min_decisions:
        report.add(
            ValidationFinding(
                rule_id="PL-17",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-17 floor: {decisions} decision node(s) below {scope} "
                    f"minimum {min_decisions} in story '{story.id}'"
                ),
            )
        )
    _check_ending_ceiling(story, endings, report)


def _check_ending_ceiling(
    story: Storybook, endings: int, report: ValidationReport
) -> None:
    """PL-17: warn when a story exceeds ADR-011 section 5's endings maximum.

    NEW capability rather than a tightening. PL-17 floored endings and nothing
    ceilinged them, yet "too many endings" is a real failure mode: paths become
    individual, and in a series every satisfying ending has to hand off to the
    next book. This reads the ceiling off ADR-011 section 5's own per-cell
    column, so it states the ADR rather than inventing a number.

    **Advisory on purpose.** Applying these numbers fails 7 committed skeletons,
    5 of them at 3-5, and one of those (`the-last-blue-cup`) was authored to the
    strict bar. A ceiling a fresh strict-bar skeleton violates is more likely
    miscalibrated than the skeleton is, and the same table is degenerate at
    3-5/short (its floor and ceiling meet at the top of the node range) and was
    inverted in three more cells before the floor was capped. So this reports
    rather than blocks until the owner rules on ADR section 5 versus section 6
    (`UW-C283`).

    Args:
        story: The parsed Storybook.
        endings: The story's ending-node count, already computed by the caller.
        report: The report to append to.
    """
    if story.metadata.length is None or not story.metadata.production_eligible:
        return
    bounds = cell_ending_bounds(
        story.metadata.age_band.value,
        story.metadata.length.value,
        story.metadata.narrative_style.value,
    )
    if bounds is None or endings <= bounds[1]:
        return
    report.add(
        ValidationFinding(
            rule_id="PL-17",
            severity=Severity.WARNING,
            story_id=story.id,
            message=(
                f"PL-17 ceiling: {endings} ending(s) above the ADR-011 section 5 "
                f"maximum {bounds[1]} for cell "
                f"'{story.metadata.age_band.value}/{story.metadata.length.value}/"
                f"{story.metadata.narrative_style.value}' in story '{story.id}' "
                f"(advisory only, pending the section 5 versus section 6 ruling)"
            ),
        )
    )


def _check_topology(story: Storybook, report: ValidationReport) -> None:
    """PL-18: declared topology must be admissible for the graph shape."""
    admissible = admissible_topologies(_build_graph(story))
    if story.metadata.topology not in admissible:
        report.add(
            ValidationFinding(
                rule_id="PL-18",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-18 topology: declared '{story.metadata.topology.value}' is "
                    f"not admissible for the graph (admissible: "
                    f"{sorted(t.value for t in admissible)}) in story '{story.id}'"
                ),
            )
        )


def _check_band_topology(story: Storybook, report: ValidationReport) -> None:
    """PL-29: declared topology must be allowed for the band (ADR-011 s7).

    Independent of PL-18 and both must hold. PL-18 asks whether the declared
    label fits the graph's *shape*; PL-29 asks whether the band is permitted to
    use that label at all. ``branch_and_bottleneck`` is a well-formed shape that
    a 3-5 or 5-8 book may not declare, so a skeleton can satisfy PL-18 and still
    be wrong for its band.

    #CRITICAL: data-integrity: the band row was enforced only by the offline
    mutation core, never by the gate authors actually run. Three skeletons
    drafted 2026-08-16 declared ``branch_and_bottleneck`` at 3-5 and 5-8,
    passed ``check_skeleton --strict`` clean, and failed only once the mutation
    operators ran over them, which is far too late and only happens for
    catalog-time work. Every committed skeleton already satisfies its row, so
    this rule blocks nothing that exists and would have blocked all three.
    #VERIFY: test_policy.py::test_pl29_rejects_a_topology_the_band_forbids and
    ::test_pl29_accepts_every_committed_skeleton.

    Args:
        story: The validated Storybook.
        report: The report to add findings to.
    """
    allowed = BAND_TOPOLOGIES.get(story.metadata.age_band.value)
    if allowed is None or story.metadata.topology in allowed:
        return
    report.add(
        ValidationFinding(
            rule_id="PL-29",
            severity=Severity.ERROR,
            story_id=story.id,
            message=(
                f"PL-29 topology: band '{story.metadata.age_band.value}' may not "
                f"declare '{story.metadata.topology.value}' (allowed: "
                f"{sorted(t.value for t in allowed)}) in story '{story.id}'"
            ),
        )
    )


def node_word_count(body: str) -> int:
    """Return a node's word count: the declared FILL target, else prose words.

    A skeleton node body is a ``<<FILL ... words=N ...>>`` directive; its budget
    is the declared ``N``. A filled node body is prose; its count is the number
    of whitespace-separated tokens. A FILL directive without a ``words=`` token
    counts as 0 (below every per-node max, and there is no per-node minimum).

    Args:
        body: The node ``body`` string.

    Returns:
        The word count used by the PL-19 words-per-node check.
    """
    if _FILL_MARKER in body:
        match = _FILL_WORDS_RE.search(body)
        return int(match.group(1)) if match is not None else 0
    return len(body.split())


def _check_words_per_node(story: Storybook, report: ValidationReport) -> None:
    """PL-19: per-node word wall guard (ERROR) and story-mean advisory (WARNING).

    The per-node maximum is a hard wall guard applied to every story: a single
    node whose word budget exceeds the band+style maximum blocks. The story-mean
    advisory band is checked only for a scale-classified production story (one
    that declares a ``length``), because the mean is meaningful only against a
    chosen scale cell; it is a WARNING and never blocks. There is no per-node
    minimum (a one-line beat is legitimate). See ADR-011 section 3.
    """
    band = story.metadata.age_band.value
    style = story.metadata.narrative_style.value
    profile = words_per_node_profile(band, style)
    if profile is None:
        return
    _mean_target, advisory_lo, advisory_hi, per_node_max = profile
    counts: list[int] = []
    for node in story.nodes:
        count = node_word_count(node.body)
        counts.append(count)
        if count > per_node_max:
            report.add(
                ValidationFinding(
                    rule_id="PL-19",
                    severity=Severity.ERROR,
                    story_id=story.id,
                    node_id=node.id,
                    message=(
                        f"PL-19 words: node '{node.id}' body is {count} words, over "
                        f"the band '{band}' {style} per-node max {per_node_max} in "
                        f"story '{story.id}'"
                    ),
                )
            )
    scale_classified = (
        story.metadata.length is not None and story.metadata.production_eligible
    )
    if scale_classified and counts:
        mean = sum(counts) / len(counts)
        if not advisory_lo <= mean <= advisory_hi:
            report.add(
                ValidationFinding(
                    rule_id="PL-19",
                    severity=Severity.WARNING,
                    story_id=story.id,
                    message=(
                        f"PL-19 words: story-mean {mean:.1f} words/node is outside the "
                        f"band '{band}' {style} advisory {advisory_lo}-{advisory_hi} in "
                        f"story '{story.id}'"
                    ),
                )
            )


def _check_first_decision_depth(story: Storybook, report: ValidationReport) -> None:
    """PL-25: the first decision must arrive inside the band's depth window.

    Measures nodes on the shortest path from ``start_node`` up to and including
    the first node offering two or more choices, then grades that depth in two
    tiers:

    - **Past the band ceiling: WARNING.** A buried first choice is a craft
      defect, not an unpublishable one, and the gate's ERROR tier means
      unpublishable. This mirrors PL-20, whose *floor* (too short to be a story)
      errors while whose *ceiling* (a long arc) warns. Grading a one-node
      overshoot as fatal would also retroactively unpublish committed work on a
      margin narrower than the calibration's own confidence.
    - **Past ``ARC_CEILING_MULTIPLE`` times the ceiling: ERROR.** That multiple
      is the JHM corpus's own longest-to-shortest playthrough ratio, so a story
      that far past the window is outside the observed genre rather than merely
      slow. This is the long unbranching prologue the rule exists to catch, and
      the shape an LLM generator produces most readily.

    Under the floor is an **ERROR**, graded in one tier. A story that opens on
    its first choice asks the reader to pick before any situation exists, which
    is a correctness failure in the same sense as PL-20's floor rather than a
    matter of pacing degree: there is no "slightly too little establishing" the
    way there is a slightly-too-long prologue. The drafting guide states the same
    constraint from the other side (max choiceless stops in a row is at least 1
    in every band). It was introduced as a WARNING only because 20 skeletons
    predated the rule; those were fixed first (AL-086), and the escalation
    followed a clean sweep.

    **Both bounds also admit a word-equivalent reading**, so a story that is
    outside the node window but inside the prose window it stands for passes.
    See :func:`_opening_in_word_window` for why the units differ and for the
    proof that the relaxation is one-way.

    Applies to every story with a configured band, scale-classified or not,
    because a buried first choice is a band-level pacing defect rather than a
    scale one. A story with no decision node at all is left to PL-17, which
    already floors decision count. See ``band_profile._FIRST_DECISION_DEPTH``
    for the JHM 2019 anchor.
    """
    window = first_decision_window(story.metadata.age_band.value)
    if window is None:
        return
    floor, ceiling = window
    decisions = _decision_node_ids(story)
    if not decisions:
        return
    extent = _opening_extent(story, _build_graph(story), decisions)
    if extent is None:
        return
    depth = extent.depth
    band = story.metadata.age_band.value
    hard_ceiling = int(ceiling * ARC_CEILING_MULTIPLE)
    if depth > ceiling and not _opening_in_word_window(story, extent, high=ceiling):
        blocking = depth > hard_ceiling and not _opening_in_word_window(
            story, extent, high=hard_ceiling
        )
        limits = (
            f"ceiling {ceiling} and its hard limit {hard_ceiling}"
            if blocking
            else f"ceiling {ceiling}"
        )
        report.add(
            ValidationFinding(
                rule_id="PL-25",
                severity=Severity.ERROR if blocking else Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PL-25 opening: first decision is {depth} node(s) in, past the "
                    f"band '{band}' {limits}, and the prose before it runs past the "
                    f"words those nodes stand for, in story '{story.id}'"
                ),
            )
        )
    elif depth < floor and not _opening_in_word_window(story, extent, low=floor):
        report.add(
            ValidationFinding(
                rule_id="PL-25",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-25 opening: first decision is {depth} node(s) in, under the "
                    f"band '{band}' floor {floor}, and the prose before it does not "
                    f"cover the ground those nodes stand for, in story '{story.id}'"
                ),
            )
        )


@dataclass(frozen=True, slots=True)
class _OpeningExtent:
    """How far the reader travels before the first decision, three ways.

    ``fewest_words`` and ``most_words`` bracket the prose over *equally short*
    openings, which is what keeps PL-25's word reading a property of the graph
    rather than of the node ids. Equally short paths can carry very different
    word counts, so reading one arbitrarily chosen path would let a rename flip
    the verdict. PL-26 hit the same trap and fixed it a different way; see
    :func:`_fewest_decision_shortest_path`.
    """

    depth: int
    fewest_words: int
    most_words: int


def _opening_extent(
    story: Storybook, graph: nx.DiGraph[str], decisions: set[str]
) -> _OpeningExtent | None:
    """Measure the opening's node depth and its word range over equally short walks.

    Runs the same layered dynamic program as :func:`_fewest_decision_shortest_path`
    over the shortest-path DAG, in O(V+E), carrying a running minimum and maximum
    word sum instead of a decision count. Enumerating the shortest paths would be
    exponential in the worst case and this sits in the gate's request path.

    No tie-break is needed and none is taken: the result is the min and the max
    over a set of numbers, so it cannot depend on visit order, on node ids, or on
    ``PYTHONHASHSEED``.

    Args:
        story: The parsed Storybook, read for its start node and node bodies.
        graph: The story's directed choice graph.
        decisions: Ids of the nodes that count as a decision.

    Returns:
        The :class:`_OpeningExtent`, or ``None`` when the start node is absent
        from the graph or no decision is reachable from it.
    """
    start = story.start_node
    if start not in graph:
        return None
    level, by_level = _breadth_first_levels(graph, start)
    reachable = [level[target] for target in decisions if target in level]
    if not reachable:
        return None
    distance = min(reachable)
    words = {node.id: node_word_count(node.body) for node in story.nodes}
    fewest: dict[str, int] = {start: words.get(start, 0)}
    most: dict[str, int] = {start: words.get(start, 0)}
    for depth in range(distance):
        for node in by_level[depth]:
            if node not in fewest:
                continue
            for successor in graph.successors(node):
                if level.get(successor) != depth + 1:
                    continue
                carried = words.get(successor, 0)
                low = fewest[node] + carried
                high = most[node] + carried
                if successor not in fewest or low < fewest[successor]:
                    fewest[successor] = low
                if successor not in most or high > most[successor]:
                    most[successor] = high
    arrivals = [target for target in decisions if level.get(target) == distance]
    return _OpeningExtent(
        depth=distance + 1,
        fewest_words=min(fewest[target] for target in arrivals),
        most_words=max(most[target] for target in arrivals),
    )


def _opening_in_word_window(
    story: Storybook,
    extent: _OpeningExtent,
    *,
    low: int | None = None,
    high: int | None = None,
) -> bool:
    """Report whether the opening satisfies a PL-25 bound counted in words.

    RULED 2026-08-17 (owner). PL-25's anchor is JHM 2019 Table 4, which measures
    **pages** to the first decision (median 4, range 2 to 8.25). A CYOA page is a
    quantity of prose; a node in this framework is an authoring unit that may
    hold anywhere from a fifth of a page to two pages. Implementing the rule
    against raw node count therefore graded a story on where its node boundaries
    happened to fall rather than on how much situation the reader had been given.
    Both bounds inverted under that reading:

    - The floor failed a single 530-word opening scene while passing two 40-word
      stubs, though the long opening is the one that establishes more. That is
      the shape a story-first author produces, and it is the case the owner
      raised: at the start especially, ground has to be covered before a choice
      means anything.
    - The ceiling failed an opening told in eight 40-word beats (320 words) while
      passing five 200-word pages (1,000 words), though the second buries the
      choice three times as deep in reading time.

    So each bound is also tested in words, against itself times the band's mean
    words per node. The conversion factor is the same table PL-19 grades against,
    so the two rules cannot drift apart on what a node's worth of prose is.

    **The relaxation is one-way by construction.** A bound is violated only when
    *both* the node count and the word count are outside it, so no story that
    passes today can start failing. Each bound is read against the extreme that
    favours the story (the longest equally short opening for the floor, the
    shortest for the ceiling), which keeps the one-way property true for every
    story rather than only for those with a single shortest opening.

    The defect each bound exists to catch is untouched: a story that truly opens
    cold has almost no words before its first choice, and a genuine unbranching
    prologue runs long in words as well as in nodes. A tiny-node corridor that
    slips under the word ceiling still meets CG-1's consecutive-single-choice run
    cap, which bounds that shape directly.

    Args:
        story: The parsed Storybook, read for its band and narrative style.
        extent: The measured opening, from :func:`_opening_extent`.
        low: A node floor to test as ``words >= low * mean``, or ``None``.
        high: A node ceiling to test as ``words <= high * mean``, or ``None``.

    Returns:
        bool: True when the opening's word count satisfies the given bound.
            False when the band has no words-per-node profile, so an
            unconfigured band falls back to the node-count verdict.
    """
    profile = words_per_node_profile(
        story.metadata.age_band.value, story.metadata.narrative_style.value
    )
    if profile is None:
        return False
    mean_words = profile[0]
    if low is not None:
        return extent.most_words >= low * mean_words
    if high is not None:
        return extent.fewest_words <= high * mean_words
    return False


def _check_min_to_complete(story: Storybook, report: ValidationReport) -> None:
    """PL-20 arc length and PL-26 decision density on the fastest-finish path.

    Only a scale-classified production story (one that declares a ``length``) has
    a fastest-finish floor, taken from the ADR-011 cell. All three checks read one
    walk, but that walk is chosen for PL-26's sake alone: it is the equally fast
    finish carrying the FEWEST decisions. PL-20 is indifferent to the choice
    because it reads only the walk's length, and every fewest-node walk has the
    same length by definition; PL-26 is not, because equally fast walks can carry
    different decision counts. See :func:`_fewest_decision_shortest_path` for why
    a rule that reads a per-node property of a walk must not inherit another
    rule's tie-break:

    - **PL-20 floor (ERROR).** The shortest path in nodes from ``start_node`` to
      any success/completion ending must be at least the cell floor; a hollow
      quick win blocks.
    - **PL-20 ceiling (WARNING).** That path running past
      ``ARC_CEILING_MULTIPLE`` times the floor is a slog to the nearest win.
    - **PL-26 density (WARNING).** Nodes per decision along the *worst* equally
      fast walk (the one carrying the fewest decisions) must not exceed
      ``nodes_per_decision_ceiling``. This is the axis PL-17 cannot see: PL-17
      counts decision nodes across the whole graph, so a story can meet every
      breadth floor while the reader walks a corridor.

    Fail-fast negative endings are unaffected, and a story with no satisfying
    ending is left to PL-17. See ADR-011 section 4.
    """
    length = story.metadata.length
    if length is None or not story.metadata.production_eligible:
        return
    band = story.metadata.age_band.value
    style = story.metadata.narrative_style.value
    floor = min_complete_floor(band, length.value, style)
    if floor is None:
        return
    satisfying = {
        node.id
        for node in story.nodes
        if node.ending is not None and node.ending.kind in _SATISFYING_KINDS
    }
    if not satisfying:
        return
    path = _fewest_decision_shortest_path(
        _build_graph(story), story.start_node, satisfying, _decision_node_ids(story)
    )
    if path is None:
        return
    # Every fewest-node walk has the same length, so PL-20's two tiers read the
    # same number they read before PL-26 began choosing among those walks.
    shortest = len(path)
    if shortest < floor:
        report.add(
            ValidationFinding(
                rule_id="PL-20",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-20 arc: shortest satisfying completion is {shortest} node(s), "
                    f"below the '{band}' {length.value} {style} floor {floor} in story "
                    f"'{story.id}'"
                ),
            )
        )
    ceiling = int(floor * ARC_CEILING_MULTIPLE)
    if shortest > ceiling:
        report.add(
            ValidationFinding(
                rule_id="PL-20",
                severity=Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PL-20 arc: shortest satisfying completion is {shortest} node(s), "
                    f"over the '{band}' {length.value} {style} advisory ceiling "
                    f"{ceiling} ({ARC_CEILING_MULTIPLE}x the floor {floor}) in story "
                    f"'{story.id}'"
                ),
            )
        )
    _check_decision_density(story, path, report)


def _check_decision_density(
    story: Storybook, path: list[str], report: ValidationReport
) -> None:
    """PL-26: nodes per decision along the fastest-finish path (WARNING).

    A ceiling only. The rule guards the corridor shape (few or no choices on the
    way through), which is the gap PL-17's breadth floors cannot see. It does not
    bound density from below, because a shortest path is biased toward decision
    nodes by construction; see ``band_profile._NODES_PER_DECISION_CEILING``.

    Because it is a ceiling, the path handed in must be the *fewest-decision*
    fastest finish (see :func:`_fewest_decision_shortest_path`), so the density
    reported is the worst case among equally fast walks rather than whichever
    walk a tie-break happened to pick.

    Args:
        story: The parsed story.
        path: The fewest-decision fastest-finish node path.
        report: The report to append findings to.
    """
    on_path = set(path)
    decisions = sum(
        1
        for node in story.nodes
        if node.id in on_path and not node.is_ending and len(node.choices) >= 2
    )
    if decisions == 0:
        report.add(
            ValidationFinding(
                rule_id="PL-26",
                severity=Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PL-26 density: the {len(path)}-node fastest finish in story "
                    f"'{story.id}' offers no decision at all"
                ),
            )
        )
        return
    ceiling = nodes_per_decision_ceiling(
        story.metadata.narrative_style.value, story.metadata.age_band.value
    )
    density = len(path) / decisions
    if density > ceiling:
        report.add(
            ValidationFinding(
                rule_id="PL-26",
                severity=Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PL-26 density: fastest finish averages {density:.1f} node(s) per "
                    f"decision ({decisions} decision(s) over {len(path)} nodes), "
                    f"over the {ceiling} advisory ceiling in story '{story.id}'"
                ),
            )
        )


def _check_off_matrix_cell(story: Storybook, report: ValidationReport) -> None:
    """PL-21: a scale-classified story must declare an offered scale cell.

    A story that declares a ``length`` places itself on the ADR-011
    ``(band, length, style)`` matrix. If that combination is not an offered cell
    (for example a ``3-5`` ``long``, or an ``8-11`` ``gamebook``), the L1-7 budget
    silently falls back to the band-level budget; this rule surfaces that as an
    ERROR instead, so a mis-declared scale is caught rather than quietly
    downgraded. A story with no ``length`` (or an MVP story) is not
    scale-classified and is not checked. See ADR-011 (the story-scale matrix).
    """
    length = story.metadata.length
    if length is None or not story.metadata.production_eligible:
        return
    band = story.metadata.age_band.value
    style = story.metadata.narrative_style.value
    if not is_offered_cell(band, length.value, style):
        report.add(
            ValidationFinding(
                rule_id="PL-21",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-21 scale: ({band}, {length.value}, {style}) is not an "
                    f"offered story-scale cell in story '{story.id}'; declare an "
                    f"offered cell or remove the length"
                ),
            )
        )


# How far a declared estimated_minutes may sit from the derived fastest-finish
# clock before PL-23 warns. Generous: a deliberately rounded or padded editorial
# figure is fine, a 3-6x mismatch is a broken promise to the reader.
_READ_TIME_TOLERANCE = 0.25

# Below this many words on the fastest-finish path the derived clock is noise: at
# any band anchor it rounds to a minute or two, so a percentage drift against a
# declared integer is meaningless. Mirrors RL-13's _MIN_WORDS_FOR_FK floor, which
# exists for the same reason at passage scale.
_MIN_PATH_WORDS_FOR_CLOCK = 200

# Share of endings one kind may occupy before PL-24 warns. A gamebook is
# deliberately "few wins and many fails" (ADR-011 section 5), so the bar is
# loose; it exists so the number becomes visible to a reviewer instead of being
# an unexamined consequence of how many failure leaves the author happened to
# write.
_ENDING_KIND_SHARE_CEILING = 0.60

# The winnability floor is style-aware, because a single share threshold is not a
# meaningful measure across both styles. Calibrated against all 23 committed
# fills: every gamebook sits at 2.1-4.8% positive-valence endings and every prose
# story at 15.2-70.0%, with no overlap. That is not nine defective gamebooks, it
# is ADR-011 section 5's declared "few wins and many fails" shape, whose
# denominator is inflated by failure leaves on purpose. So a share floor would
# flag an entire style and signal nothing.
#
# Prose keeps a share floor. Gamebooks get a floor on distinct winnable endings
# instead, which catches the real defect (a large branching book with one or no
# way to win) without punishing the style. Ruled 2026-08-09 (review Part 4, R1):
# the floor scales as max(3, ceil(5% of endings)), so a 200-ending book cannot
# clear it with the same 2-3 wins that satisfy a 30-ending one; the original
# absolute floor of 3 had been calibrated below the whole corpus and was
# exercised only by unit test.
_POSITIVE_VALENCE_SHARE_FLOOR_PROSE = 0.10
_POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK = 3
_POSITIVE_ENDING_SHARE_FLOOR_GAMEBOOK = 0.05


def words_on_shortest_satisfying_path(story: Storybook) -> int | None:
    """Return the fewest words on any satisfying path, or None.

    Node-weighted uniform-cost (Dijkstra) search from the start node, each node
    weighted by its body word count, so the result is the *fewest words* to reach
    a satisfying ending, not the fewest nodes. This mirrors the canonical writer
    ``mutation.identity.recompute_estimated_minutes`` (its ``_fastest_finish_words``)
    exactly, so PL-23 can never warn against a value that clock produced. A
    fewest-node path can carry more words than the fewest-word path, which is the
    disagreement this closes. The heap tie-breaks equal distances by node id, so
    the result is deterministic under ``PYTHONHASHSEED``.

    Reuses the same satisfying-ending definition and graph as PL-20, so the two
    rules can never disagree about which path is "the fastest finish".

    Public (not underscore-prefixed) so a skeleton-context caller
    (``scripts/check_skeleton.py``, UW-C261/AL-391/AL-395) can compute the same
    fastest-finish clock ``_check_declared_read_time`` uses, rather than
    reimplementing this search. Both read a node's word count through
    :func:`node_word_count`, which already substitutes a ``<<FILL ... words=N
    ...>>`` directive's declared ``N`` for its placeholder body, so calling this
    on an unfilled skeleton yields the fastest-finish clock the shell's own word
    hints promise, before any prose exists.

    Args:
        story: The parsed story.

    Returns:
        int | None: Total words on the fewest-word satisfying path, or ``None``
            when no satisfying ending is reachable.
    """
    satisfying = {
        node.id
        for node in story.nodes
        if node.ending is not None and node.ending.kind in _SATISFYING_KINDS
    }
    if not satisfying:
        return None
    weights = {node.id: node_word_count(node.body) for node in story.nodes}
    start = story.start_node
    if start not in weights:
        return None
    graph = _build_graph(story)
    settled: set[str] = set()
    frontier: list[tuple[int, str]] = [(weights[start], start)]
    while frontier:
        distance, current = heapq.heappop(frontier)
        if current in settled:
            continue
        settled.add(current)
        if current in satisfying:
            return distance
        for target in graph.successors(current):
            if target not in settled:
                heapq.heappush(frontier, (distance + weights.get(target, 0), target))
    return None


def _check_declared_read_time(story: Storybook, report: ValidationReport) -> None:
    """PL-23: declared ``estimated_minutes`` must match the derived clock.

    ADR-011 section 4 defines ``estimated_minutes`` as the **fastest-finish**
    clock: words on the shortest satisfying path divided by the band's pace
    anchor. Nothing validated it, so on any hand-authored or imported story the
    field was whatever the author typed, and it is the figure a child sees when
    choosing a book. Advisory, because a rounded or deliberately padded editorial
    number is a legitimate choice; a large mismatch is not.
    """
    words = words_on_shortest_satisfying_path(story)
    if words is None or words < _MIN_PATH_WORDS_FOR_CLOCK:
        return
    derived = max(1, round(words / reading_pace_wpm(story.metadata.age_band.value)))
    declared = story.metadata.estimated_minutes
    if declared <= 0:
        return
    drift = abs(declared - derived) / derived
    if drift <= _READ_TIME_TOLERANCE:
        return
    report.add(
        ValidationFinding(
            rule_id="PL-23",
            severity=Severity.WARNING,
            story_id=story.id,
            message=(
                f"PL-23 clock: declared estimated_minutes {declared} differs from the "
                f"derived fastest-finish clock {derived} min ({words} words on the "
                f"shortest satisfying path at "
                f"{reading_pace_wpm(story.metadata.age_band.value)} wpm) by "
                f"{drift:.0%} in story '{story.id}' (advisory only)"
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class ReadTimeDrift:
    """PL-23's declared-versus-derived clock comparison, with its direction.

    ``_check_declared_read_time`` folds this same comparison into a single
    pass/fail finding and never says which way the mismatch runs. AL-395
    measured that the two directions are two different defects (an
    under-declared skeleton is a plain metadata error a hint-sized fill will
    overrun; an over-declared one, concentrated at the longest cells, reads as
    the author recording a typical read instead of ADR-011's fastest-finish
    definition), so a caller that wants to name the remedy needs the
    direction, not just the drift.

    Attributes:
        declared_minutes: The story's ``metadata.estimated_minutes``.
        derived_minutes: The fastest-finish clock computed from
            :func:`words_on_shortest_satisfying_path`.
        words: Words on the fewest-word satisfying path.
        wpm: The band's reading-pace anchor used to derive the clock.
        drift: The fractional difference, ``abs(declared - derived) / derived``.
        direction: ``"under-declared"`` when the declared value is below the
            derived clock, ``"over-declared"`` when it is above, or
            ``"exact"`` when they match exactly (``drift == 0``).
        breaches_tolerance: Whether ``drift`` exceeds PL-23's own tolerance
            (``_READ_TIME_TOLERANCE``), i.e. whether this is the same breach
            ``_check_declared_read_time`` would warn on.
    """

    declared_minutes: int
    derived_minutes: int
    words: int
    wpm: int
    drift: float
    direction: Literal["under-declared", "over-declared", "exact"]
    breaches_tolerance: bool


def read_time_drift(story: Storybook) -> ReadTimeDrift | None:
    """Compute PL-23's clock comparison at any context, skeleton or filled.

    Reuses :func:`words_on_shortest_satisfying_path`, the same search
    ``_check_declared_read_time`` uses, and applies the identical skip
    conditions (the fastest-finish path must clear
    ``_MIN_PATH_WORDS_FOR_CLOCK`` words, and ``estimated_minutes`` must be
    declared positive) so a caller here can never disagree with the fill-time
    PL-23 finding about whether the clock even applies. This is a read-only
    measurement: it does not raise a :class:`ValidationFinding` and does not
    change what ``_check_declared_read_time`` does, warns on, or skips
    (UW-C261). ``scripts/check_skeleton.py`` calls this to report the breach
    direction when a skeleton is validated, before any prose exists
    (AL-391, AL-395).

    Args:
        story: The parsed story: a catalog skeleton (node bodies still
            ``<<FILL ... words=N ...>>`` directives) or a filled book.

    Returns:
        ReadTimeDrift | None: ``None`` under the same conditions
            ``_check_declared_read_time`` silently skips (no satisfying path
            long enough to measure, or a non-positive declared value);
            otherwise the comparison, whether or not it breaches tolerance.
    """
    words = words_on_shortest_satisfying_path(story)
    if words is None or words < _MIN_PATH_WORDS_FOR_CLOCK:
        return None
    wpm = reading_pace_wpm(story.metadata.age_band.value)
    derived = max(1, round(words / wpm))
    declared = story.metadata.estimated_minutes
    if declared <= 0:
        return None
    drift = abs(declared - derived) / derived
    direction: Literal["under-declared", "over-declared", "exact"]
    if declared < derived:
        direction = "under-declared"
    elif declared > derived:
        direction = "over-declared"
    else:
        direction = "exact"
    return ReadTimeDrift(
        declared_minutes=declared,
        derived_minutes=derived,
        words=words,
        wpm=wpm,
        drift=drift,
        direction=direction,
        breaches_tolerance=drift > _READ_TIME_TOLERANCE,
    )


def _check_ending_mix(story: Storybook, report: ValidationReport) -> None:
    """PL-24: no single ending kind may dominate the story's ending mix.

    PL-15 forbids specific kinds per band and PL-17 enforces an ending count, but
    nothing looked at the *mix*, so a 746-node gamebook that was 51% death
    endings gated clean and a 95%-death one would too. Advisory: at 16+ "few wins
    and many fails" is the declared intent, so this reports a shape a reviewer
    should look at rather than a rule violation.
    """
    kinds = [node.ending.kind for node in story.nodes if node.ending is not None]
    total = len(kinds)
    if total == 0:
        return
    counts: dict[EndingKind, int] = {}
    for kind in kinds:
        counts[kind] = counts.get(kind, 0) + 1
    dominant, count = max(counts.items(), key=lambda item: item[1])
    share = count / total
    if share > _ENDING_KIND_SHARE_CEILING:
        report.add(
            ValidationFinding(
                rule_id="PL-24",
                severity=Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PL-24 mix: ending kind '{dominant.value}' is {count} of {total} "
                    f"endings ({share:.0%}), above the "
                    f"{_ENDING_KIND_SHARE_CEILING:.0%} share ceiling in story "
                    f"'{story.id}' (advisory only)"
                ),
            )
        )

    positive = sum(
        1
        for node in story.nodes
        if node.ending is not None and node.ending.valence is Valence.POSITIVE
    )
    if story.metadata.narrative_style is NarrativeStyle.GAMEBOOK:
        gamebook_floor = max(
            _POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK,
            math.ceil(_POSITIVE_ENDING_SHARE_FLOOR_GAMEBOOK * total),
        )
        if positive < gamebook_floor:
            report.add(
                ValidationFinding(
                    rule_id="PL-24",
                    severity=Severity.WARNING,
                    story_id=story.id,
                    message=(
                        f"PL-24 mix: only {positive} positive-valence ending(s) in "
                        f"{total} in story '{story.id}', below the gamebook floor of "
                        f"{gamebook_floor} distinct winnable endings "
                        f"(max of {_POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK} and "
                        f"{_POSITIVE_ENDING_SHARE_FLOOR_GAMEBOOK:.0%} of endings; "
                        f"advisory only)"
                    ),
                )
            )
        return
    positive_share = positive / total
    if positive_share < _POSITIVE_VALENCE_SHARE_FLOOR_PROSE:
        report.add(
            ValidationFinding(
                rule_id="PL-24",
                severity=Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PL-24 mix: only {positive} of {total} endings "
                    f"({positive_share:.1%}) are positive-valence, below the prose "
                    f"floor of {_POSITIVE_VALENCE_SHARE_FLOOR_PROSE:.0%} in story "
                    f"'{story.id}' (advisory only)"
                ),
            )
        )


def _walk_back(parents: dict[str, str], start: str, target: str) -> list[str]:
    """Rebuild the ``start`` to ``target`` path from a BFS parent map.

    Args:
        parents: Each visited node mapped to the node it was reached from.
        start: The node the search began at.
        target: The node to walk back from.

    Returns:
        The node-id path in forward order, including both endpoints.
    """
    path = [target]
    while path[-1] != start:
        path.append(parents[path[-1]])
    path.reverse()
    return path


def _decision_node_ids(story: Storybook) -> set[str]:
    """Return the ids of every decision node in a story.

    A decision node is a non-ending node offering two or more choices. This is
    the single definition PL-25, PL-26 and the fewest-decision path search all
    read, so they cannot drift apart on what "a decision" is.

    Args:
        story: The parsed story.

    Returns:
        The set of decision-node ids (empty when the story offers no choice).
    """
    return {
        node.id for node in story.nodes if not node.is_ending and len(node.choices) >= 2
    }


def _breadth_first_levels(
    graph: nx.DiGraph[str], start: str
) -> tuple[dict[str, int], list[list[str]]]:
    """Return each reachable node's hop distance from ``start``, and by-level ids.

    Step 1 of :func:`_fewest_decision_shortest_path`, split out because the
    layered dynamic program that follows reads both results and because the two
    phases fail differently: this one is a plain BFS with no tie-break at all,
    while the DP's every choice is a tie-break that has to be justified.

    Args:
        graph: The story's directed choice graph; ``start`` must be a node in it.
        start: The node to measure from.

    Returns:
        ``(level, by_level)`` where ``level[node]`` is the fewest hops from
        ``start`` and ``by_level[k]`` lists the ids at distance ``k``, sorted so
        the caller's sweep order is stable under ``PYTHONHASHSEED``.
    """
    level: dict[str, int] = {start: 0}
    by_level: list[list[str]] = [[start]]
    frontier: list[str] = [start]
    while frontier:
        following: list[str] = []
        for node in frontier:
            for successor in graph.successors(node):
                if successor not in level:
                    level[successor] = level[node] + 1
                    following.append(successor)
        if not following:
            break
        by_level.append(sorted(following))
        frontier = following
    return level, by_level


def _fewest_decision_shortest_path(
    graph: nx.DiGraph[str],
    start: str,
    targets: set[str],
    decisions: set[str],
) -> list[str] | None:
    """Return a fewest-node path to a target carrying the fewest decisions.

    Among every path of the minimum node length from ``start`` to any of
    ``targets``, this returns one holding as few nodes from ``decisions`` as
    possible, which is the *highest* nodes-per-decision case among equally fast
    finishes. PL-26 is a ceiling, so reporting the worst equally fast walk is the
    only choice that makes its verdict a property of the graph rather than of the
    node ids: equally short paths can carry different decision counts, and an
    arbitrary tie-break flipped the verdict on renaming alone.

    Runs in O(V+E) via a layered dynamic program over the shortest-path DAG, not
    by enumerating shortest paths. That matters because the number of shortest
    paths is exponential in the graph size in the worst case (a chain of parallel
    two-way detours doubles it per link) and this code sits in the request path
    behind the generation gate.
    #ASSUME: timing-dependencies: the layered DP visits each node and edge at
    most once, so gate cost stays linear in graph size even for the largest
    offered cell (a 750-node 16+ long gamebook).
    #VERIFY: see ``test_pl26_density_scales_past_exponential_path_counts`` in
    tests/unit/test_policy.py, which gates a graph holding 2**20 equally short
    satisfying paths and asserts the report still comes back.

    Ties are broken deterministically: candidate targets by ``(decisions, id)``
    and predecessors by id, so the chosen walk is stable under
    ``PYTHONHASHSEED``. The choice here is semantic first (fewest decisions) and
    lexical only to settle a genuine tie, so renaming nodes cannot change the
    reported density. An earlier version shared a purely lexical breadth-first
    tie-break and its verdict flipped on node renaming alone.

    Args:
        graph: The story's directed choice graph.
        start: The start node id.
        targets: Candidate destination node ids; unreachable ones are ignored.
        decisions: Ids of the nodes that count as a decision.

    Returns:
        The node-id path including both endpoints, or ``None`` when no target is
        reachable from ``start``.
    """
    if start not in graph:
        return None
    level, by_level = _breadth_first_levels(graph, start)
    depths = [level[target] for target in targets if target in level]
    if not depths:
        return None
    distance = min(depths)
    # 2/3. Layered DP over the shortest-path DAG: an edge u -> v belongs to it
    # exactly when level[v] == level[u] + 1, and every in-edge of a level-k node
    # comes from level k-1, so one forward sweep settles each level in turn.
    fewest: dict[str, int] = {start: int(start in decisions)}
    parents: dict[str, str] = {}
    for depth in range(distance):
        for node in by_level[depth]:
            if node not in fewest:
                continue
            for successor in sorted(graph.successors(node)):
                if level.get(successor) != depth + 1:
                    continue
                cost = fewest[node] + int(successor in decisions)
                if successor not in fewest or cost < fewest[successor]:
                    fewest[successor] = cost
                    parents[successor] = node
    # 4. Recover the argmin path; ``distance`` came from a reachable target, so
    # at least one candidate exists and each was reached through the layered DAG.
    chosen = min(
        (target for target in targets if level.get(target) == distance),
        key=lambda target: (fewest[target], target),
    )
    return _walk_back(parents, start, chosen)
