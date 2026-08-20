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

W2.2 unforce (design review finding 2.5): tone is derived from the request's
own text (``story_requests/tone.py::derive_tone``, D5/D18) instead of the
former hardcoded ``"gentle"``, and the structural target is the middle of the
band's node envelope with the ending count scaled to match, instead of the
band floor. ``tier`` stays fixed at 1 and ``structure_pattern`` stays
``BRANCH_AND_BOTTLENECK``; both are out of this change's scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.generation.concept import (
    AnchorContext,
    ConceptBrief,
    Protagonist,
    StructurePattern,
)
from cyo_adventure.story_requests.tone import derive_tone
from cyo_adventure.storybook.models import (
    AgeBand,
    ContentFlagLevel,
    Length,
    NarrativeStyle,
    level_rank,
)
from cyo_adventure.validator.band_profile import (
    BandProfile,
    breadth_scaled_floors,
    cell_ending_bounds,
    clamp_target_to_cap,
    production_cell_budget,
    profile_for,
    reading_level_target_for,
)

if TYPE_CHECKING:
    from cyo_adventure.db.models import ChildProfile, StoryRequest

# The three content-sensitivity flags a profile's allowed_content_flags dict
# may cap; mirrors storybook.models.ContentFlags' field set.
_CONTENT_FLAG_NAMES = ("violence", "scariness", "peril")

# reading_level_cap defaults to 99.0 server-side (an unset ceiling, not a target);
# at or above this sentinel the band-default FK target applies.
_READING_CAP_SENTINEL = 99.0

# FK targets now come from `band_profile._READING_LEVEL_TARGET`, the single
# source of record ruled 2026-08-18. This table used to restate them and drifted:
# it said 4.0 at 8-11 and 6.0 at 10-13 where the catalog declares 4.5 and 5.5,
# and 8.0/10.0 at the teen bands where the catalog declares 7.0/9.0. Three other
# sites carried three more sets; see `docs/planning/reading-level-source-table.md`
# (`UW-C281`).
# #ASSUME: data-integrity: every band this function can be called with is
# configured in that table. `reading_level_target_for` returns None for an
# unconfigured band, which `_reading_target_for` below turns into a loud failure
# rather than a silent default, since a wrong FK target reaches a child as prose
# at the wrong difficulty.
# #VERIFY: test_reading_level_sources.py::test_reading_level_target_covers_every_band.

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


def _reading_target_for(age_band: AgeBand, profile: object) -> float:
    """Return the FK target for a band, tightened by a guardian's cap.

    A `reading_level_cap` is a CEILING (`api/schemas.py`: "can only ever
    tighten"), and RL-13 reads a target as the CENTRE of a plus-or-minus window.
    Substituting the cap for the target therefore admitted prose a full grade
    ABOVE the maximum a guardian asked for: a cap of 2.0 passed FK 3.00. Clamping
    keeps a cap from ever raising a band's target and from becoming a target in
    its own right (`UW-C281`).

    Args:
        age_band: The story's age band.
        profile: The child's personalization profile, or None.

    Returns:
        The band target, lowered to the cap when the guardian set one.

    Raises:
        ConfigurationError: When the band has no configured FK target. Failing
            closed beats defaulting: a wrong target reaches a child as prose at
            the wrong difficulty, which no later gate re-derives.
    """
    target = reading_level_target_for(age_band.value)
    if target is None:
        msg = f"no reading-level target configured for age band '{age_band.value}'"
        raise ConfigurationError(msg)
    cap = getattr(profile, "reading_level_cap", None)
    if cap is not None and cap < _READING_CAP_SENTINEL:
        return clamp_target_to_cap(target, cap)
    return target


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


def _budget_for(
    request: StoryRequest,
    age_band: AgeBand,
    band: BandProfile | None,
    narrative_style: str,
) -> tuple[int, int]:
    """Return the ``(node_count, ending_count)`` the prompt should ask for.

    #CRITICAL: data-integrity: this must derive from the SAME envelope PL-17
    grades against, or the prompt asks for a story the gate rejects. It used to
    take the midpoint of the BAND envelope while PL-17 floors from the CELL
    envelope, and `generation/prompts.py` renders the result as "produce EXACTLY
    N ending node(s) ... Not more, not fewer" in the same block that states the
    cell's node range. In 17 of the 18 offered cells the two disagreed, often by
    an order of magnitude: 8-11/long asked for 4 endings where the gate needs 24,
    13-16/long/gamebook asked 7 where it needs 93. A generator obeying the prompt
    exactly could not pass, and one passing the gate was disobeying an
    instruction marked EXACTLY (`UW-C279`).
    #VERIFY: test_story_requests.py::test_brief_ending_count_satisfies_the_gate_in_every_cell
    renders the number for all 18 cells and checks it against the floor the gate
    will apply.

    Both counts are derived rather than restated, so a future change to
    `breadth_scaled_floors` (see `UW-C283`) moves the prompt with it instead of
    reopening the same gap.

    Args:
        request: The story request, read for its declared length.
        age_band: The resolved age band.
        band: The band profile, or None when the band is unconfigured.
        narrative_style: The resolved narrative style.

    Returns:
        The ``(node_count, ending_count)`` pair for the brief.
    """
    if band is None:
        return _FALLBACK_NODES, _FALLBACK_ENDINGS

    length = cast("str | None", request.length)
    cell = (
        production_cell_budget(age_band.value, length, narrative_style)
        if length is not None
        else None
    )
    if cell is not None:
        min_nodes, max_nodes, _max_depth = cell
    else:
        # Off-matrix or length-less: the band envelope is what L1-7 falls back
        # to as well, so prompt and gate still agree.
        min_nodes, max_nodes = band.min_nodes, band.max_nodes

    node_count = round((min_nodes + max_nodes) / 2)
    # The ending floor is derived from the TOP of the node range, not from the
    # midpoint the brief suggests as a node count. `generation/prompts.py`
    # authorises the whole range ("produce between {min_nodes} and {max_nodes}
    # nodes total") while rendering this number as "produce EXACTLY N ending
    # node(s) ... Not more, not fewer", and PL-17 floors from the story's ACTUAL
    # `len(story.nodes)`. `breadth_scaled_floors` is monotonically increasing in
    # node count, so the least favourable case a compliant generator can land on
    # is `max_nodes`, not `min_nodes`: deriving from the midpoint left the ask
    # below the floor in 17 of the 18 offered cells, by 1 to 16 endings.
    #
    # `cell_ceiling` is passed for the same reason `_effective_floors` passes it
    # (`policy.py`): PL-17 caps the scaled floor at the cell's ending ceiling, so
    # omitting it here would over-ask where a ceiling binds.
    bounds = (
        None
        if length is None
        else cell_ending_bounds(age_band.value, length, narrative_style)
    )
    scaled_min_endings, _ = breadth_scaled_floors(
        max_nodes, narrative_style, None if bounds is None else bounds[1]
    )
    return node_count, max(band.min_endings, scaled_min_endings)


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
    narrative_style_str = narrative_style_value or NarrativeStyle.PROSE.value
    node_count, ending_count = _budget_for(request, age_band, band, narrative_style_str)
    reading_target = _reading_target_for(age_band, profile)
    content_nogo, content_flag_constraints = _content_controls(profile, age_band)
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
        tone=derive_tone(request.request_text, age_band),
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
