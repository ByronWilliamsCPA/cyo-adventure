"""Build a ConceptBrief from an approved child story request.

The premise is the child's own text; the age band, length, and narrative style
now come from the request row itself (WS-B derivation flip), stamped there by
the guardian's approval confirmation. Every other field is a repo-derived
default so an approved request produces the same brief shape as the guardian
intake flow (mirrors frontend guardian/intakeApi.ts::buildBrief). The
protagonist name is a generic fictional default and is NEVER a real child's
display name.

G2 per-child content controls (``ChildProfile.banned_themes`` and
``allowed_content_flags``, surfaced by ``api/profiles.py``) are folded in
here too: ``banned_themes`` becomes the brief's ``content_nogo`` verbatim,
and any set content-flag cap is clamped to the requesting age band's own
ceiling (a guardian can only tighten what the band already enforces, never
loosen it) and carried as a plain-language line in ``special_constraints``,
since ``ConceptBrief`` has no structured per-flag cap field of its own. The
deterministic validation gate (``validator/policy.py``) still enforces only
the band ceiling unconditionally; this is guidance to the generator, not a
second enforcement point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.concept import (
    AnchorContext,
    ConceptBrief,
    Protagonist,
    StructurePattern,
)
from cyo_adventure.storybook.models import (
    AgeBand,
    ContentFlagLevel,
    Length,
    NarrativeStyle,
    level_rank,
)
from cyo_adventure.validator.band_profile import profile_for

if TYPE_CHECKING:
    from cyo_adventure.db.models import ChildProfile, StoryRequest

# The three content-sensitivity flags a profile's allowed_content_flags dict
# may cap; mirrors storybook.models.ContentFlags' field set.
_CONTENT_FLAG_NAMES = ("violence", "scariness", "peril")

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


def _content_controls(
    profile: ChildProfile | None, age_band: AgeBand
) -> tuple[list[str], list[str]]:
    """Derive ``(content_nogo, special_constraints)`` from a child's G2 controls.

    Args:
        profile: The requesting child's profile, or None for a profile-less
            request (no G2 controls to apply).
        age_band: The story's target age band; supplies the ceiling each
            content-flag cap is clamped against.

    Returns:
        A ``(content_nogo, special_constraints)`` pair: ``content_nogo`` is
        the profile's ``banned_themes`` verbatim (already normalized at the
        profiles API boundary); ``special_constraints`` is one
        plain-language line per content-flag cap the guardian has set,
        clamped to the band's own ceiling.

    # #ASSUME: data-integrity: an in-memory ChildProfile built without
    # explicit allowed_content_flags/banned_themes (the common pre-flush
    # unit-test shape) has both as None, not the ORM column's post-flush
    # default (`{}` / None respectively); both are treated the same way
    # here ("no controls set"), so the distinction is invisible to callers.
    # #VERIFY: test_story_requests.py::test_brief_from_request_profile_with_no_g2_controls_is_unaffected.
    """
    if profile is None:
        return [], []
    content_nogo = list(profile.banned_themes or [])
    # #ASSUME: data-integrity: allowed_content_flags is declared non-Optional
    # (Mapped[dict[str, object]]) because its ORM column default applies at
    # flush/INSERT time, not at Python object construction (same gap as
    # request.narrative_style below); an in-memory profile built without an
    # explicit value is None at runtime despite the static type, hence the cast.
    caps = cast("dict[str, object] | None", profile.allowed_content_flags) or {}
    band = profile_for(age_band.value)
    if band is None:
        return content_nogo, []
    constraints: list[str] = []
    for flag_name in _CONTENT_FLAG_NAMES:
        raw_cap = caps.get(flag_name)
        if raw_cap is None:
            continue
        try:
            child_level = ContentFlagLevel(raw_cap)
        except ValueError:
            # #EDGE: data-integrity: a stored cap outside the closed
            # ContentFlagLevel vocabulary (should be unreachable; the
            # profiles API validates every write) is skipped rather than
            # raising, so a bad row degrades to "no cap on this flag"
            # instead of failing the whole generation request.
            continue
        ceiling = band.content_ceiling[flag_name]
        # #CRITICAL: security: a guardian's cap can only tighten the band
        # ceiling, never loosen it; clamp to whichever is stricter. The
        # deterministic gate (validator/policy.py PL-16) enforces the band
        # ceiling regardless of this brief, so this clamp only prevents the
        # generator from being told a looser-than-band target.
        # #VERIFY: test_story_requests.py::test_content_flag_cap_looser_than_band_is_clamped.
        effective = (
            child_level if level_rank(child_level) <= level_rank(ceiling) else ceiling
        )
        constraints.append(f"Keep {flag_name} at or below '{effective.value}'.")
    return content_nogo, constraints


def brief_from_request(
    request: StoryRequest,
    profile: ChildProfile | None,
    anchor_context: AnchorContext | None = None,
) -> ConceptBrief:
    """Assemble a ConceptBrief for an approved request.

    Args:
        request: The approved story request; source of truth for premise,
            age band, length, and narrative style (WS-B derivation flip).
        profile: The requesting child's profile, or None for requests not
            tied to one child (guardian/admin initiated). Contributes only
            the reading-level cap; band never comes from here.
        anchor_context: Soft-continuation context from the request's anchor,
            or None.

    Returns:
        ConceptBrief: A fully populated brief with a generic fictional
            protagonist, band-derived structural budgets, and the child's
            G2 content controls (``content_nogo`` / ``special_constraints``).
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
    content_nogo, content_flag_constraints = _content_controls(profile, age_band)
    # #ASSUME: data integrity: the ORM column default ("prose") only applies
    # at flush/INSERT time, not at Python object construction, so an
    # in-memory request built without an explicit narrative_style (the common
    # unit-test shape, and any pre-flush caller) still needs the same
    # fallback here.
    # #VERIFY: covered by the unit tests for band/protagonist derivation in
    # tests/unit/test_story_requests.py. The ``Mapped[str]`` annotation on
    # the ORM column is only true post-flush, so the value is cast to
    # ``str | None`` here to match the real pre-flush runtime shape.
    narrative_style_value = cast("str | None", request.narrative_style)
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
        content_nogo=content_nogo,
        special_constraints=content_flag_constraints,
        length=Length(request.length) if request.length is not None else None,
        narrative_style=(
            NarrativeStyle(narrative_style_value)
            if narrative_style_value is not None
            else NarrativeStyle.PROSE
        ),
        anchor_context=anchor_context,
    )
