"""Concept brief intake model for the CYO Adventure generation pipeline.

A ConceptBrief captures the guardian-supplied creative parameters that drive
a single story-generation job. All fields in this model represent story design
decisions, NOT real-child identifying data.

Privacy note on protagonist.name
---------------------------------
The ``protagonist.name`` field is a FICTIONAL character name chosen by the
guardian for the story (e.g. "Captain Rosa"). It is entirely separate from
any real child's display name stored in a ``child_profile`` row. The PII guard
in ``cyo_adventure.generation.pii`` screens prompts against real-child names
supplied via ``PiiContext`` (populated from the authenticated family's child
profiles). It does NOT screen against ``protagonist.name``, because that is
not a real-child identifier and screening it would incorrectly block the very
content we want to generate.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

# Bounded free-text list item: non-empty and length-capped so a single brief
# field cannot inflate prompt size unbounded or smuggle a large payload into a
# generation prompt. Lists of these are themselves count-capped via Field.
_BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=200)]

__all__ = [
    "ConceptBrief",
    "Protagonist",
    "StructurePattern",
]


class StructurePattern(StrEnum):
    """Narrative-structure templates available for story generation.

    Patterns follow the vocabulary from "Choose Your Own Adventure" design
    theory. Each describes how branches and convergence points are arranged.
    """

    TIME_CAVE = "time_cave"
    GAUNTLET = "gauntlet"
    BRANCH_AND_BOTTLENECK = "branch_and_bottleneck"
    QUEST = "quest"
    LOOP_AND_GROW = "loop_and_grow"


class Protagonist(BaseModel):
    """The fictional story character whose role the reader takes.

    This is a STORY character defined by the guardian for the narrative. It is
    not a real child's profile. The ``name`` field here is a fictional character
    name and is not subject to PII screening (see module docstring).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=100,
        description="Fictional character name for the story.",
    )
    age: int = Field(
        ge=0,
        le=18,
        description="Story character's age in years (0-18, for a children's app).",
    )
    role: str = Field(
        min_length=1,
        max_length=200,
        description="Character's narrative role (e.g. 'young explorer').",
    )


class ConceptBrief(BaseModel):
    """Guardian-supplied creative brief for a single story-generation job.

    Passed to the generation orchestrator after PII screening. Fields map
    directly to the intake spec in ``docs/planning/tech-spec.md`` (section
    "Concept brief (intake fields)"). Free-text fields carry ``max_length``
    bounds (and list fields a count cap) so a brief cannot inflate prompt size
    or smuggle an oversized payload into a generation prompt; the API layer
    should additionally strip control characters before the brief reaches the
    orchestrator.

    ``extra="forbid"`` ensures that any unexpected field name is rejected at
    parse time, preventing accidental injection of undeclared data.
    """

    model_config = ConfigDict(extra="forbid")

    # Optional story title supplied by the guardian.
    title: str | None = Field(default=None, max_length=200)

    # Required story setup.
    premise: str = Field(
        min_length=1,
        max_length=2000,
        description="Short story premise; the seed for generation.",
    )
    protagonist: Protagonist = Field(
        description="Fictional story character (name/age/role). NOT a real child."
    )
    point_of_view: str = Field(
        default="second",
        max_length=50,
        description="Narrative POV (default: second person).",
    )

    # Reading and audience targeting.
    age_band: AgeBand = Field(description="Target reading age band.")
    reading_level_target: float = Field(
        ge=0.0,
        description="Target Flesch-Kincaid grade level.",
    )
    tier: int = Field(
        ge=1,
        le=2,
        description="Story tier: 1 = simple (no variables), 2 = stateful.",
    )

    # Tone and content guidance.
    tone: str = Field(
        min_length=1,
        max_length=100,
        description="Desired narrative tone (e.g. 'adventurous', 'cosy').",
    )
    themes_allowed: list[_BoundedText] = Field(
        default_factory=list,
        max_length=20,
        description="Themes the story is allowed to explore.",
    )
    content_nogo: list[_BoundedText] = Field(
        default_factory=list,
        max_length=20,
        description="Content categories explicitly prohibited in this story.",
    )

    # Structural parameters.
    target_node_count: int = Field(
        ge=1,
        description="Desired number of passage nodes.",
    )
    ending_count: int = Field(
        ge=1,
        description="Number of distinct endings to generate.",
    )
    structure_pattern: StructurePattern = Field(
        description="Narrative-structure template to apply.",
    )

    # Optional ADR-011 story-scale placement. When ``length`` names an offered
    # ``(age_band, length, narrative_style)`` cell, the Stage A prompt promises
    # that cell's genre-faithful node budget, words-per-node envelope, and
    # fastest-finish arc floor instead of the band-level budget, so generation
    # can request a scale-classified production story. A brief with no ``length``
    # keeps the band-level budget (backward compatible). ``narrative_style``
    # changes the envelope only for 13-16/16+; lower bands are implicitly prose.
    length: Length | None = Field(
        default=None,
        description="Story-scale length tier (short/medium/long); None = band budget.",
    )
    narrative_style: NarrativeStyle = Field(
        default=NarrativeStyle.PROSE,
        description="Prose or gamebook chunking of the word budget (ADR-011).",
    )

    # Optional Tier-2 variable hints and free-form constraints.
    desired_variables: list[_BoundedText] = Field(
        default_factory=list,
        max_length=20,
        description="Names of state variables the story should declare (Tier-2).",
    )
    special_constraints: list[_BoundedText] = Field(
        default_factory=list,
        max_length=20,
        description="Free-text constraints passed to the generator as guidance.",
    )
