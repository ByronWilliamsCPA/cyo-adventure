"""Age-policy gate layer (rules PL-15..PL-26, plus the PL-22 fail-closed guard).

Runs after Layer 1 passes and the Storybook parses, on the typed model plus the
choice graph. Most findings are ERROR-severity and blocking; the PL-19 story-mean
words-per-node check, the PL-20 arc ceiling, PL-25 other than its hard limit, and
all of PL-26 are advisory (WARNING). These rules convert age-safety, shape, and
story-scale judgments into deterministic invariants.

Path-length rules grade in two tiers on purpose. A *floor* violation (PL-20: too
short to be a story) is a correctness failure and blocks. A *ceiling* violation
(PL-20's long arc, PL-25's buried first choice) is a craft failure and warns,
because the ERROR tier means unpublishable. PL-25 keeps one blocking tier past
``ARC_CEILING_MULTIPLE`` times the band ceiling, where the shape has left the
observed genre rather than merely run slow.

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
import re

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
from cyo_adventure.validator.topology import admissible_topologies

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
    scaled_endings, scaled_decisions = breadth_scaled_floors(
        len(story.nodes), story.metadata.narrative_style.value
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

    Under the floor is a WARNING: a story that opens on its first choice gives
    the reader no situation to choose about.

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
    decisions = {
        node.id for node in story.nodes if not node.is_ending and len(node.choices) >= 2
    }
    if not decisions:
        return
    depth = _shortest_path_nodes(_build_graph(story), story.start_node, decisions)
    if depth is None:
        return
    band = story.metadata.age_band.value
    hard_ceiling = int(ceiling * ARC_CEILING_MULTIPLE)
    if depth > ceiling:
        blocking = depth > hard_ceiling
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
                    f"band '{band}' {limits} in story '{story.id}'"
                ),
            )
        )
    elif depth < floor:
        report.add(
            ValidationFinding(
                rule_id="PL-25",
                severity=Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PL-25 opening: first decision is {depth} node(s) in, under the "
                    f"band '{band}' floor {floor} in story '{story.id}'"
                ),
            )
        )


def _check_min_to_complete(story: Storybook, report: ValidationReport) -> None:
    """PL-20 arc length and PL-26 decision density on the fastest-finish path.

    Only a scale-classified production story (one that declares a ``length``) has
    a fastest-finish floor, taken from the ADR-011 cell. Three checks share the
    one computed path so they can never disagree about which walk that is:

    - **PL-20 floor (ERROR).** The shortest path in nodes from ``start_node`` to
      any success/completion ending must be at least the cell floor; a hollow
      quick win blocks.
    - **PL-20 ceiling (WARNING).** That path running past
      ``ARC_CEILING_MULTIPLE`` times the floor is a slog to the nearest win.
    - **PL-26 density (WARNING).** Nodes per decision along the same path must
      not exceed ``nodes_per_decision_ceiling``. This is the axis PL-17 cannot
      see: PL-17 counts decision nodes across the whole graph, so a story can
      meet every breadth floor while the reader walks a corridor.

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
    path = _shortest_path_to(_build_graph(story), story.start_node, satisfying)
    if path is None:
        return
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

    Args:
        story: The parsed story.
        path: The fastest-finish node path PL-20 measured.
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
    ceiling = nodes_per_decision_ceiling(story.metadata.narrative_style.value)
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
# Prose keeps a share floor. Gamebooks get an ABSOLUTE floor on distinct winnable
# endings instead, which catches the real defect (a large branching book with one
# or no way to win) without punishing the style. Every catalog gamebook currently
# has 5, so the floor is set below that and the rule is exercised by unit test
# rather than by the corpus.
_POSITIVE_VALENCE_SHARE_FLOOR_PROSE = 0.10
_POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK = 3


def _words_on_shortest_satisfying_path(story: Storybook) -> int | None:
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
    words = _words_on_shortest_satisfying_path(story)
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
        if positive < _POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK:
            report.add(
                ValidationFinding(
                    rule_id="PL-24",
                    severity=Severity.WARNING,
                    story_id=story.id,
                    message=(
                        f"PL-24 mix: only {positive} positive-valence ending(s) in "
                        f"{total} in story '{story.id}', below the gamebook floor of "
                        f"{_POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK} distinct winnable "
                        f"endings (advisory only)"
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


def _shortest_path_to(
    graph: nx.DiGraph[str], start: str, targets: set[str]
) -> list[str] | None:
    """Return the fewest-node path from ``start`` to any of ``targets``.

    Ties between equally short paths are broken by target id, so the chosen path
    is stable under ``PYTHONHASHSEED``. PL-20 and PL-26 both read this one
    result, so the arc-length rule and the decision-density rule can never
    disagree about which walk is "the fastest finish".

    Args:
        graph: The story's directed choice graph.
        start: The start node id.
        targets: Candidate destination node ids; unreachable ones are ignored.

    Returns:
        The node-id path including both endpoints, or ``None`` when no target is
        reachable from ``start``.
    """
    if start not in graph:
        return None
    parents: dict[str, str] = {}
    seen: set[str] = {start}
    frontier: list[str] = [start]
    while frontier:
        # A whole breadth-first level is settled before any of it is inspected,
        # so the nearest target wins and equal-distance targets tie-break by id.
        reached = sorted(node for node in frontier if node in targets)
        if reached:
            return _walk_back(parents, start, reached[0])
        following: list[str] = []
        for node in frontier:
            for successor in sorted(graph.successors(node)):
                if successor not in seen:
                    seen.add(successor)
                    parents[successor] = node
                    following.append(successor)
        frontier = following
    return None


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


def _shortest_path_nodes(
    graph: nx.DiGraph[str], start: str, targets: set[str]
) -> int | None:
    """Return the fewest nodes on any path from ``start`` to a target.

    Path length is measured in nodes (hops + 1). Unreachable targets are
    ignored; returns ``None`` when no target is reachable from ``start``.
    """
    path = _shortest_path_to(graph, start, targets)
    return None if path is None else len(path)
