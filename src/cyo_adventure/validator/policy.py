"""Age-policy gate layer (rules PL-15..PL-21, plus the PL-22 fail-closed guard).

Runs after Layer 1 passes and the Storybook parses, on the typed model plus the
choice graph. Most findings are ERROR-severity and blocking; the PL-19 story-mean
words-per-node check is advisory (WARNING). These rules convert age-safety, shape,
and story-scale judgments into deterministic invariants.

Rule sources: docs/planning/validator-rules.md (PL-15..PL-18);
docs/planning/adr/adr-011-story-scale-framework.md (PL-19
words-per-node, PL-20 fastest-finish arc floor, and PL-21 off-matrix rejection).
PL-22 (band profile not configured, fail closed) is a runtime invariant added
2026-07-16 and is not yet reflected in validator-rules.md.
"""

from __future__ import annotations

import re

import networkx as nx

from cyo_adventure.storybook.models import EndingKind, Storybook, level_rank
from cyo_adventure.validator.band_profile import (
    BandProfile,
    breadth_scaled_floors,
    is_offered_cell,
    min_complete_floor,
    profile_for,
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


def _check_min_to_complete(story: Storybook, report: ValidationReport) -> None:
    """PL-20: the shortest satisfying-completion path must meet the arc floor.

    Only a scale-classified production story (one that declares a ``length``) has
    a fastest-finish floor, taken from the ADR-011 cell. The shortest path in
    nodes from ``start_node`` to any success/completion ending must be at least
    that floor; a too-short winning path (a hollow quick win) blocks. Fail-fast
    negative endings are unaffected, and a story with no satisfying ending is
    left to the ending-floor rules (PL-17). See ADR-011 section 4.
    """
    length = story.metadata.length
    if length is None or not story.metadata.production_eligible:
        return
    floor = min_complete_floor(
        story.metadata.age_band.value,
        length.value,
        story.metadata.narrative_style.value,
    )
    if floor is None:
        return
    satisfying = {
        node.id
        for node in story.nodes
        if node.ending is not None and node.ending.kind in _SATISFYING_KINDS
    }
    if not satisfying:
        return
    graph = _build_graph(story)
    shortest = _shortest_path_nodes(graph, story.start_node, satisfying)
    if shortest is not None and shortest < floor:
        report.add(
            ValidationFinding(
                rule_id="PL-20",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-20 arc: shortest satisfying completion is {shortest} node(s), "
                    f"below the '{story.metadata.age_band.value}' {length.value} "
                    f"{story.metadata.narrative_style.value} floor {floor} in story "
                    f"'{story.id}'"
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


def _shortest_path_nodes(
    graph: nx.DiGraph[str], start: str, targets: set[str]
) -> int | None:
    """Return the fewest nodes on any path from ``start`` to a target.

    Path length is measured in nodes (hops + 1). Unreachable targets are
    ignored; returns ``None`` when no target is reachable from ``start``.
    """
    best: int | None = None
    for target in targets:
        if target not in graph or start not in graph:
            continue
        if not nx.has_path(graph, start, target):
            continue
        hops = int(nx.shortest_path_length(graph, start, target))
        nodes = hops + 1
        if best is None or nodes < best:
            best = nodes
    return best
