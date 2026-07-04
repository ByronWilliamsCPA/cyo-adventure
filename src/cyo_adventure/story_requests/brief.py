"""Build a ConceptBrief from an approved child story request.

The premise is the child's own text; every other field is a repo-derived default
so an approved request produces the same brief shape as the guardian intake flow
(mirrors frontend guardian/intakeApi.ts::buildBrief). The protagonist name is a
generic fictional default and is NEVER a real child's display name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.generation.concept import ConceptBrief, Protagonist, StructurePattern
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.validator.band_profile import profile_for

if TYPE_CHECKING:
    from cyo_adventure.db.models import ChildProfile

# reading_level_cap defaults to 99.0 server-side (an unset ceiling, not a target);
# at or above this sentinel the band-default FK target applies.
_READING_CAP_SENTINEL = 99.0

# #ASSUME: data-integrity: band_profile.py carries no per-band reading-level
# values, so these FK targets mirror frontend intakeApi.ts BAND_DEFAULTS
# (monotonic with band). Used only when the child's reading_level_cap is the
# unset 99 sentinel.
# #VERIFY: revisit when validator policy grows per-band reading-level values;
# test_story_requests covers the sentinel path.
_BAND_FK_TARGET: dict[AgeBand, float] = {
    AgeBand.BAND_3_5: 1.0,
    AgeBand.BAND_5_8: 2.0,
    AgeBand.BAND_8_11: 4.0,
    AgeBand.BAND_10_13: 6.0,
    AgeBand.BAND_13_16: 8.0,
    AgeBand.BAND_16_PLUS: 10.0,
}

# #ASSUME: data-integrity: band lower-bound protagonist age, mirroring the
# frontend default; a fictional character age, not a real child's age.
_BAND_PROTAGONIST_AGE: dict[AgeBand, int] = {
    AgeBand.BAND_3_5: 3,
    AgeBand.BAND_5_8: 5,
    AgeBand.BAND_8_11: 8,
    AgeBand.BAND_10_13: 10,
    AgeBand.BAND_13_16: 13,
    AgeBand.BAND_16_PLUS: 16,
}

# Generic fictional protagonist; NEVER a real child's display name.
_DEFAULT_PROTAGONIST_NAME = "Explorer"
_DEFAULT_PROTAGONIST_ROLE = "a curious young adventurer"
# Band-independent structural fallbacks when profile_for returns None.
_FALLBACK_NODES = 8
_FALLBACK_ENDINGS = 2


def brief_from_request(request_text: str, profile: ChildProfile) -> ConceptBrief:
    """Assemble a ConceptBrief for an approved request.

    Args:
        request_text: The child's free-text idea; becomes the brief premise.
        profile: The requesting child's profile (age band and reading cap).

    Returns:
        ConceptBrief: A fully populated brief with a generic fictional
            protagonist and band-derived structural budgets.
    """
    age_band = AgeBand(profile.age_band)
    band = profile_for(profile.age_band)
    node_count = band.min_nodes if band is not None else _FALLBACK_NODES
    ending_count = band.min_endings if band is not None else _FALLBACK_ENDINGS
    reading_target = (
        profile.reading_level_cap
        if profile.reading_level_cap < _READING_CAP_SENTINEL
        else _BAND_FK_TARGET[age_band]
    )
    return ConceptBrief(
        premise=request_text,
        protagonist=Protagonist(
            name=_DEFAULT_PROTAGONIST_NAME,
            age=_BAND_PROTAGONIST_AGE[age_band],
            role=_DEFAULT_PROTAGONIST_ROLE,
        ),
        age_band=age_band,
        reading_level_target=reading_target,
        tier=1,
        tone="gentle",
        target_node_count=node_count,
        ending_count=ending_count,
        structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
    )
