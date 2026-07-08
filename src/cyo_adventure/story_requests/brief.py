"""Build a ConceptBrief from an approved child story request.

The premise is the child's own text; the age band, length, and narrative style
now come from the request row itself (WS-B derivation flip), stamped there by
the guardian's approval confirmation. Every other field is a repo-derived
default so an approved request produces the same brief shape as the guardian
intake flow (mirrors frontend guardian/intakeApi.ts::buildBrief). The
protagonist name is a generic fictional default and is NEVER a real child's
display name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.concept import ConceptBrief, Protagonist, StructurePattern
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle
from cyo_adventure.validator.band_profile import profile_for

if TYPE_CHECKING:
    from cyo_adventure.db.models import ChildProfile, StoryRequest

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


def brief_from_request(
    request: StoryRequest, profile: ChildProfile | None
) -> ConceptBrief:
    """Assemble a ConceptBrief for an approved request.

    Args:
        request: The approved story request; source of truth for premise,
            age band, length, and narrative style (WS-B derivation flip).
        profile: The requesting child's profile, or None for requests not
            tied to one child (guardian/admin initiated). Contributes only
            the reading-level cap; band never comes from here.

    Returns:
        ConceptBrief: A fully populated brief with a generic fictional
            protagonist and band-derived structural budgets.
    """
    # #CRITICAL: data integrity: request.age_band is the single source of truth
    # after the WS-B flip; the migration backfilled every historical row.
    # #VERIFY: test_brief_from_request_band_comes_from_request_not_profile.
    age_band = AgeBand(request.age_band)
    band = profile_for(request.age_band)
    node_count = band.min_nodes if band is not None else _FALLBACK_NODES
    ending_count = band.min_endings if band is not None else _FALLBACK_ENDINGS
    reading_target = (
        profile.reading_level_cap
        if profile is not None and profile.reading_level_cap < _READING_CAP_SENTINEL
        else _BAND_FK_TARGET[age_band]
    )
    return ConceptBrief(
        premise=request.request_text,
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
        length=Length(request.length) if request.length is not None else None,
        # #ASSUME: data integrity: the ORM column default ("prose") only
        # applies at flush/INSERT time, not at Python object construction, so
        # an in-memory request built without an explicit narrative_style (the
        # common unit-test shape, and any pre-flush caller) still needs the
        # same fallback here.
        # #VERIFY: covered by the unit tests for band/protagonist derivation
        # in tests/unit/test_story_requests.py. The ``Mapped[str]`` annotation
        # on the ORM column is only true post-flush, so the value is cast to
        # ``str | None`` here to match the real pre-flush runtime shape.
        narrative_style=(
            NarrativeStyle(narrative_style_value)
            if (narrative_style_value := cast("str | None", request.narrative_style))
            is not None
            else NarrativeStyle.PROSE
        ),
    )
