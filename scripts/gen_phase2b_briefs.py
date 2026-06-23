"""Generate the Phase 2b yield-measurement brief sample.

Builds a representative 20-brief sample (13 Tier-1 + 7 Tier-2) as type-checked
:class:`~cyo_adventure.generation.concept.ConceptBrief` instances and writes them
as a JSON array that ``scripts/yield_harness.py --briefs`` consumes.

The sample spans all three age bands and several structure patterns so the
measured acceptance rate reflects the real intake distribution, not a single
easy shape. Tier-2 briefs declare ``desired_variables`` to exercise the Layer-2
state validator. Node-count hints stay inside each band's L1-7 budget.

Run::

    PYTHONPATH=. .venv/bin/python scripts/gen_phase2b_briefs.py

Output: ``docs/planning/yield-results/phase-2b-briefs.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.generation.concept import (
    ConceptBrief,
    Protagonist,
    StructurePattern,
)
from cyo_adventure.storybook.models import AgeBand

_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "planning"
    / "yield-results"
    / "phase-2b-briefs.json"
)


def _tier1_briefs() -> list[ConceptBrief]:
    """Return the 13 Tier-1 (stateless) briefs across bands and structures."""
    return [
        ConceptBrief(
            title="The Lighthouse Key",
            premise=(
                "A child finds an old brass key on the beach and follows clues to "
                "a locked lighthouse."
            ),
            protagonist=Protagonist(name="Maya", age=9, role="curious beachcomber"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=3.5,
            tier=1,
            tone="gentle mystery",
            themes_allowed=["curiosity", "friendship"],
            content_nogo=["graphic violence", "death of a parent"],
            target_node_count=18,
            ending_count=2,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
        ),
        ConceptBrief(
            title="Garden of Tiny Doors",
            premise=(
                "A girl discovers miniature doors among the vegetables and meets the "
                "creatures who live behind them."
            ),
            protagonist=Protagonist(name="Iris", age=8, role="young gardener"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=3.0,
            tier=1,
            tone="whimsical",
            themes_allowed=["kindness", "wonder"],
            content_nogo=["scary monsters"],
            target_node_count=16,
            ending_count=3,
            structure_pattern=StructurePattern.TIME_CAVE,
        ),
        ConceptBrief(
            title="The Sleepy Dragon",
            premise=(
                "A village child must wake a friendly dragon before the winter frost "
                "without startling it."
            ),
            protagonist=Protagonist(name="Tomas", age=10, role="village helper"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=4.0,
            tier=1,
            tone="cosy adventure",
            themes_allowed=["patience", "courage"],
            content_nogo=["graphic violence"],
            target_node_count=22,
            ending_count=2,
            structure_pattern=StructurePattern.QUEST,
        ),
        ConceptBrief(
            title="Lost on the Tide Pools",
            premise=(
                "Two friends explore tide pools and must find their way back before "
                "the tide comes in."
            ),
            protagonist=Protagonist(name="Priya", age=9, role="tide-pool explorer"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=3.5,
            tier=1,
            tone="adventurous",
            themes_allowed=["teamwork", "problem solving"],
            content_nogo=["drowning peril"],
            target_node_count=20,
            ending_count=3,
            structure_pattern=StructurePattern.GAUNTLET,
        ),
        ConceptBrief(
            title="The Paper Airplane Pilot",
            premise=(
                "A boy's paper airplane carries him on a tiny flight over the "
                "neighbourhood rooftops."
            ),
            protagonist=Protagonist(name="Leo", age=8, role="daydreaming inventor"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=3.0,
            tier=1,
            tone="playful",
            themes_allowed=["imagination", "bravery"],
            content_nogo=["falling injury"],
            target_node_count=15,
            ending_count=2,
            structure_pattern=StructurePattern.LOOP_AND_GROW,
        ),
        ConceptBrief(
            title="The Midnight Library Cat",
            premise=(
                "A student stays late and follows the library's cat through shelves "
                "that rearrange themselves into puzzles."
            ),
            protagonist=Protagonist(name="Noor", age=11, role="bookish detective"),
            age_band=AgeBand.BAND_10_13,
            reading_level_target=5.0,
            tier=1,
            tone="mysterious",
            themes_allowed=["cleverness", "perseverance"],
            content_nogo=["graphic violence"],
            target_node_count=30,
            ending_count=3,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
        ),
        ConceptBrief(
            title="Signal from the Old Radio",
            premise=(
                "A kid repairs a vintage radio and starts receiving messages from a "
                "research team stranded on a mountain."
            ),
            protagonist=Protagonist(name="Dev", age=12, role="amateur tinkerer"),
            age_band=AgeBand.BAND_10_13,
            reading_level_target=5.5,
            tier=1,
            tone="suspenseful",
            themes_allowed=["responsibility", "courage"],
            content_nogo=["graphic injury", "character death"],
            target_node_count=34,
            ending_count=3,
            structure_pattern=StructurePattern.QUEST,
        ),
        ConceptBrief(
            title="The Marble Championship",
            premise=(
                "A new kid enters the schoolyard marble tournament and must earn the "
                "trust of rival teams."
            ),
            protagonist=Protagonist(name="Sam", age=11, role="new student"),
            age_band=AgeBand.BAND_10_13,
            reading_level_target=5.0,
            tier=1,
            tone="upbeat",
            themes_allowed=["fair play", "belonging"],
            content_nogo=["bullying that is not resolved"],
            target_node_count=28,
            ending_count=2,
            structure_pattern=StructurePattern.GAUNTLET,
        ),
        ConceptBrief(
            title="The Greenhouse on Mars",
            premise=(
                "A colony kid tends the only greenhouse and must save the seedlings "
                "during a dust storm."
            ),
            protagonist=Protagonist(name="Ada", age=12, role="junior botanist"),
            age_band=AgeBand.BAND_10_13,
            reading_level_target=6.0,
            tier=1,
            tone="hopeful sci-fi",
            themes_allowed=["resourcefulness", "stewardship"],
            content_nogo=["life-threatening peril"],
            target_node_count=32,
            ending_count=3,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
        ),
        ConceptBrief(
            title="The Understudy",
            premise=(
                "A shy teen must step into the lead role on opening night when the "
                "star loses their voice."
            ),
            protagonist=Protagonist(name="Jordan", age=13, role="theatre understudy"),
            age_band=AgeBand.BAND_13_16,
            reading_level_target=7.0,
            tier=1,
            tone="warm coming-of-age",
            themes_allowed=["self-confidence", "friendship"],
            content_nogo=["graphic content"],
            target_node_count=36,
            ending_count=3,
            structure_pattern=StructurePattern.QUEST,
        ),
        ConceptBrief(
            title="Trail of the River Map",
            premise=(
                "A teen guides a younger sibling down a marked river trail after the "
                "main bridge washes out."
            ),
            protagonist=Protagonist(name="Wren", age=14, role="weekend trail guide"),
            age_band=AgeBand.BAND_13_16,
            reading_level_target=7.5,
            tier=1,
            tone="grounded adventure",
            themes_allowed=["leadership", "caution"],
            content_nogo=["serious injury", "character death"],
            target_node_count=40,
            ending_count=4,
            structure_pattern=StructurePattern.GAUNTLET,
        ),
        ConceptBrief(
            title="The Coral Census",
            premise=(
                "A teen volunteer surveys a reef and uncovers why one section is "
                "quietly recovering."
            ),
            protagonist=Protagonist(name="Kai", age=14, role="reef volunteer"),
            age_band=AgeBand.BAND_13_16,
            reading_level_target=7.5,
            tier=1,
            tone="curious and reflective",
            themes_allowed=["science", "patience"],
            content_nogo=["graphic content"],
            target_node_count=34,
            ending_count=3,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
        ),
        ConceptBrief(
            title="The Repair Shop After Hours",
            premise=(
                "A teen apprentice locks up the bike shop and must solve a chain of "
                "small mysteries to find a missing delivery."
            ),
            protagonist=Protagonist(name="Esme", age=15, role="bike-shop apprentice"),
            age_band=AgeBand.BAND_13_16,
            reading_level_target=8.0,
            tier=1,
            tone="light mystery",
            themes_allowed=["diligence", "honesty"],
            content_nogo=["graphic violence"],
            target_node_count=38,
            ending_count=3,
            structure_pattern=StructurePattern.TIME_CAVE,
        ),
    ]


def _tier2_briefs() -> list[ConceptBrief]:
    """Return the 7 Tier-2 (stateful) briefs that declare desired_variables."""
    return [
        ConceptBrief(
            title="The Clockmaker's Apprentice",
            premise=(
                "An apprentice must wind the town's great clock, gathering the right "
                "gears in the right order before noon."
            ),
            protagonist=Protagonist(name="Otto", age=10, role="clock apprentice"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=4.0,
            tier=2,
            tone="ticking adventure",
            themes_allowed=["precision", "courage"],
            content_nogo=["graphic violence"],
            target_node_count=24,
            ending_count=3,
            structure_pattern=StructurePattern.LOOP_AND_GROW,
            desired_variables=["gears_collected", "clock_wound"],
        ),
        ConceptBrief(
            title="The Lantern Festival",
            premise=(
                "A child collects three coloured flames to light the festival lantern "
                "without letting any go out."
            ),
            protagonist=Protagonist(name="Lin", age=9, role="festival helper"),
            age_band=AgeBand.BAND_8_11,
            reading_level_target=3.5,
            tier=2,
            tone="festive",
            themes_allowed=["generosity", "care"],
            content_nogo=["fire injury"],
            target_node_count=20,
            ending_count=2,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
            desired_variables=["flames_lit", "has_oil"],
        ),
        ConceptBrief(
            title="The Backpack Inventory",
            premise=(
                "A scout must pack exactly the right supplies, trading items at camp "
                "to be ready for an overnight hike."
            ),
            protagonist=Protagonist(name="Remy", age=11, role="junior scout"),
            age_band=AgeBand.BAND_10_13,
            reading_level_target=5.0,
            tier=2,
            tone="practical adventure",
            themes_allowed=["preparation", "teamwork"],
            content_nogo=["serious injury"],
            target_node_count=30,
            ending_count=3,
            structure_pattern=StructurePattern.GAUNTLET,
            desired_variables=["supplies", "has_map", "morale"],
        ),
        ConceptBrief(
            title="Currents and Codes",
            premise=(
                "A young diver collects code fragments from sunken buoys to unlock a "
                "weather station before a storm."
            ),
            protagonist=Protagonist(name="Talia", age=12, role="junior diver"),
            age_band=AgeBand.BAND_10_13,
            reading_level_target=6.0,
            tier=2,
            tone="tense sci-fi",
            themes_allowed=["focus", "bravery"],
            content_nogo=["drowning peril", "character death"],
            target_node_count=34,
            ending_count=3,
            structure_pattern=StructurePattern.QUEST,
            desired_variables=["code_fragments", "air_reserve"],
        ),
        ConceptBrief(
            title="The Debate Cup",
            premise=(
                "A teen earns confidence points through practice rounds, deciding when "
                "to take risks before the final debate."
            ),
            protagonist=Protagonist(name="Mara", age=13, role="debate team rookie"),
            age_band=AgeBand.BAND_13_16,
            reading_level_target=7.0,
            tier=2,
            tone="motivational",
            themes_allowed=["self-confidence", "preparation"],
            content_nogo=["humiliation that is not resolved"],
            target_node_count=36,
            ending_count=3,
            structure_pattern=StructurePattern.LOOP_AND_GROW,
            desired_variables=["confidence", "rounds_won"],
        ),
        ConceptBrief(
            title="The Relay Beacon",
            premise=(
                "A teen ranger lights a chain of mountain beacons, managing fuel and "
                "daylight to signal the valley in time."
            ),
            protagonist=Protagonist(name="Soren", age=14, role="trainee ranger"),
            age_band=AgeBand.BAND_13_16,
            reading_level_target=7.5,
            tier=2,
            tone="determined adventure",
            themes_allowed=["endurance", "responsibility"],
            content_nogo=["serious injury", "character death"],
            target_node_count=42,
            ending_count=4,
            structure_pattern=StructurePattern.GAUNTLET,
            desired_variables=["beacons_lit", "fuel", "daylight"],
        ),
        ConceptBrief(
            title="The Archive Restoration",
            premise=(
                "A teen intern restores damaged records, choosing which to repair "
                "first as a deadline and budget shrink."
            ),
            protagonist=Protagonist(name="Quinn", age=15, role="archive intern"),
            age_band=AgeBand.BAND_13_16,
            reading_level_target=8.0,
            tier=2,
            tone="thoughtful",
            themes_allowed=["judgement", "diligence"],
            content_nogo=["graphic content"],
            target_node_count=40,
            ending_count=3,
            structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
            desired_variables=["records_saved", "budget"],
        ),
    ]


def main() -> None:
    """Build the brief sample and write it as a JSON array."""
    briefs = _tier1_briefs() + _tier2_briefs()
    payload = [brief.model_dump(mode="json") for brief in briefs]
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tier1 = sum(1 for b in briefs if b.tier == 1)
    tier2 = sum(1 for b in briefs if b.tier == 2)
    print(f"Wrote {len(briefs)} briefs ({tier1} Tier-1, {tier2} Tier-2) to {_OUTPUT}")


if __name__ == "__main__":
    main()
