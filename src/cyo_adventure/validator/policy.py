"""Age-policy gate layer (rules PL-15..PL-18).

Runs after Layer 1 passes and the Storybook parses, on the typed model plus the
choice graph. All findings are ERROR-severity and blocking. These rules convert
age-safety and shape judgments into deterministic invariants.

Rule source: docs/superpowers/specs/2026-06-24-typed-story-metadata-design.md.
"""

from __future__ import annotations

import networkx as nx

from cyo_adventure.storybook.models import Storybook, level_rank
from cyo_adventure.validator.band_profile import BandProfile, profile_for
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)
from cyo_adventure.validator.topology import admissible_topologies


def validate_policy(story: Storybook) -> ValidationReport:
    """Run PL-15..PL-18 over a parsed story.

    Args:
        story: The validated Storybook (Layer 1 has already passed).

    Returns:
        ValidationReport: Policy findings; ``ok`` is ``True`` when none are errors.
    """
    report = ValidationReport()
    profile = profile_for(story.metadata.age_band.value)
    if profile is None:
        # #CRITICAL: security: a band with no configured profile makes this gate
        # fail OPEN, every age-safety check (PL-15/16/17) is skipped for that
        # band, so a forbidden ending or over-ceiling content would pass review.
        # #VERIFY: test_profiles_match_age_band_enum_exactly asserts the AgeBand enum and
        # band_profile._PROFILES keys stay in lockstep, so this branch is
        # unreachable for any valid (enum-constrained) age_band.
        return report
    _check_forbidden_kinds(story, profile, report)
    _check_content_ceiling(story, profile, report)
    _check_floors(story, profile, report)
    _check_topology(story, report)
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


def _check_floors(
    story: Storybook, profile: BandProfile, report: ValidationReport
) -> None:
    """PL-17: endings and decision nodes must meet the band floors."""
    endings = sum(1 for node in story.nodes if node.is_ending)
    decisions = sum(
        1 for node in story.nodes if not node.is_ending and len(node.choices) >= 2
    )
    if endings < profile.min_endings:
        report.add(
            ValidationFinding(
                rule_id="PL-17",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-17 floor: {endings} ending(s) below band "
                    f"'{story.metadata.age_band.value}' minimum "
                    f"{profile.min_endings} in story '{story.id}'"
                ),
            )
        )
    if decisions < profile.min_decisions:
        report.add(
            ValidationFinding(
                rule_id="PL-17",
                severity=Severity.ERROR,
                story_id=story.id,
                message=(
                    f"PL-17 floor: {decisions} decision node(s) below band "
                    f"'{story.metadata.age_band.value}' minimum "
                    f"{profile.min_decisions} in story '{story.id}'"
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
