"""Write-time and payload-build-time personalization value validation, ADR-023 Task B5.

`ChildProfilePersonalization` (`db/models.py`) stores one guardian-set value
per `(child_profile_id, slot_type)` pair, in exactly one of three shapes:
free text (`value_text`), a closed-enum choice (`value_enum`), or a reference
to another profile in the same family (`value_profile_id`, the sibling slot).
This module is the single deterministic gate a candidate value must clear
before either of its two call sites accepts it:

1. **Write time** (the personalization-values API route): a guardian
   proposes a value; an invalid one must be rejected with a reason, not
   silently stored.
2. **Payload-build time** (the render payload builder): a value already at
   rest is re-checked before it is handed to the reader. ADR-023's render-time
   fallback contract is that an invalid value here is never a hard failure:
   the slot is silently OMITTED from the payload and the story renders its
   generic default instead (`personalization_value_for_payload`).

Both call sites reuse the SAME checks so a value accepted at write time can
never later be treated as valid-but-rejected at render time for a reason the
write-time gate should have already caught (and vice versa: a value that
somehow reached storage invalid, e.g. a pre-B5 row, is still caught at render
time rather than shown to a reader).

Four checks, run per candidate value:

1. **Structural injection guard**
   (`cyo_adventure.validator.slots.structural_value_violations`): the same
   charset/length/control-character/fence-marker checks the pre-fill slot
   binder applies to every LLM-proposed value, reused here so a personalization
   value cannot forge a `{SLOT}` token, a `<<FILL>>` directive, or an
   untrusted-input fence marker.
2. **Band-mandatory denylist**
   (`cyo_adventure.validator.slots.denylisted_bundles` against
   `band_mandatory_bundles(age_band)`): the same lethal/weapon/toxic/capture/
   graphic/despair floor the theme-contract slot gate enforces, so a
   personalized detail cannot introduce content the reading band already
   forbids everywhere else.
3. **Closed-enum membership** (`CLOSED_VOCABULARIES`): an enum-shaped slot's
   value must be a member of its shipped vocabulary; free text is never
   accepted for these slots regardless of what the structural/denylist checks
   would otherwise allow.
4. **Sibling-in-family** (`SIBLING_SLOT_TYPE` only): a sibling slot's
   `value_profile_id` must be one of the requesting family's own profile ids.
   This module is deliberately pure and does not resolve that set itself: the
   caller (a route handler) resolves it via
   `cyo_adventure.api.deps.authorize_family` / the family's profile roster,
   and passes the resolved id collection in as `family_profile_ids`. Keeping
   the authorization lookup out of this module is what keeps it importable,
   without a database, from both the write route and the payload builder.

Pure module: stdlib + `cyo_adventure.storybook.models` (`AgeBand`) +
`cyo_adventure.validator.slots` only. No generation, db, sqlalchemy, LLM,
randomness, or I/O of any kind, mirroring `validator/slots.py`'s own
pure-module contract.

**On `CLOSED_VOCABULARIES`'s empty vocabularies (ADR-023 rows 4a/5/6/7/8).**
ADR-023's taxonomy table describes these five enum slots conceptually and
gives a handful of illustrative examples, but never enumerates a shippable,
exhaustive closed vocabulary for any of them: row 7 (home type) explicitly
trails off with "house, apartment, farm, ..."; row 6 (favorite) names
categories (color, food, hobby), not values; row 4a (pet species) names no
example at all; row 5 (kinship label) gives four quoted examples ("Grandma",
"Abuela", "Auntie", "Grandpa") without stating they are the complete list;
row 8 (dedication) stores a kinship label in the same shape as row 5, added
by ADR-023 Stage C Task C0e (it was missing from this dict until then, which
made the dedication a free-text channel onto a kid-facing screen; see
`CLOSED_VOCABULARIES`'s inline comment). Seeding a vocabulary here would mean
inventing values no design document actually ratified. Each entry is
therefore left empty (fail-closed: every enum candidate for that slot is
rejected as "not a member") until
`docs/planning/story-personalization-implementation-plan.md` or a future
ADR-023 amendment supplies the real, shippable lists.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from cyo_adventure.validator.slots import (
    SlotViolation,
    band_mandatory_bundles,
    denylisted_bundles,
    structural_value_violations,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable, Collection, Sequence

    from cyo_adventure.storybook.models import AgeBand

# The sibling-or-family-child slot (ADR-023 row 3): the only slot_type whose
# value is a value_profile_id rather than free text or a closed enum.
SIBLING_SLOT_TYPE = "sibling_name"

# #EDGE: data-integrity: every entry is empty (see the module docstring's
# "On CLOSED_VOCABULARIES's empty vocabularies" note); this fails closed, so
# every enum candidate for these five slots is rejected until product/ADR-023
# supplies the real, shippable lists.
# #VERIFY: docs/planning/story-personalization-implementation-plan.md is
# where the concrete lists belong; do not hand-add values here without a
# design-plan update or an ADR-023 amendment recording the vocabulary.
CLOSED_VOCABULARIES: dict[str, frozenset[str]] = {
    "pet_species": frozenset(),
    "kinship_label": frozenset(),
    "favorite": frozenset(),
    "home_type": frozenset(),
    # ADR-023 row 8 / design plan section 9: the dedication stores a KINSHIP
    # LABEL, the same closed shape as `kinship_label` above, because the "from"
    # kinship can legitimately differ from the in-story trusted-adult kinship.
    # It was missing from this dict until ADR-023 Stage C Task C0e, which meant
    # `_shape_violations` permitted `value_text` on it and the membership check
    # below never fired, making the dedication a free-text channel onto a
    # kid-facing screen. Empty, like its four neighbours, until product supplies
    # the real list.
    "dedication": frozenset(),
}


def _shape_violations(
    slot_type: str,
    value_text: str | None,
    value_enum: str | None,
    value_profile_id: uuid.UUID | None,
) -> list[SlotViolation]:
    """Reject values whose column does not match what the slot type permits.

    #CRITICAL: security: without this, every other check in this module is
    opt-in by column choice. `ck_cpp_exactly_one_value` counts NOT NULLs but
    never binds WHICH column a given slot_type may use, so a caller picks
    which validations run simply by choosing a JSON field name:

    - `value_profile_id` on any non-sibling slot ran zero checks. The
      structural and denylist checks read only text/enum, and the
      sibling-in-family check is gated on `slot_type == SIBLING_SLOT_TYPE`.
      The FK requires the UUID to name *some* child_profile, including
      another family's, and the render path stringifies whatever it finds,
      injecting a raw cross-family UUID into child-facing prose.
    - `value_text` on a closed-vocabulary slot skipped the vocabulary check
      entirely, so the deliberately fail-closed empty vocabularies were one
      JSON field name away from unbounded free text.
    - `value_text` or `value_enum` on the sibling slot skipped the
      sibling-in-family check, which is the same cross-family hole entered
      from the other side.

    `pronoun_set` is deliberately unconstrained here: no design document
    states its shape, and the existing fixtures use free text
    (`measurement/fixtures.py`). Constraining it would be inventing product
    policy rather than closing a hole.

    #VERIFY: tests/unit/test_personalization_values.py asserts each of the
    three rules rejects, and that a correctly-shaped value still passes.

    Args:
        slot_type: The slot the value is bound to.
        value_text: The candidate free-text value, or None.
        value_enum: The candidate closed-enum choice, or None.
        value_profile_id: The candidate profile reference, or None.

    Returns:
        A list of `SlotViolation`s, empty when the shape is permitted.
    """
    violations: list[SlotViolation] = []
    reasons: list[str] = []

    if value_profile_id is not None and slot_type != SIBLING_SLOT_TYPE:
        reasons.append(f"only '{SIBLING_SLOT_TYPE}' may carry a value_profile_id")

    if slot_type == SIBLING_SLOT_TYPE and (
        value_text is not None or value_enum is not None
    ):
        reasons.append("this slot must use value_profile_id, not text or enum")

    if slot_type in CLOSED_VOCABULARIES and value_text is not None:
        reasons.append("this slot has a closed vocabulary and must use value_enum")

    violations.extend(
        SlotViolation(slot_type, "value_shape", f"slot '{slot_type}': {reason}")
        for reason in reasons
    )
    return violations


# Ruff PLR0913 (too many arguments) is suppressed on this function and on
# `personalization_value_for_payload` below. Every parameter past `age_band`
# is keyword-only and models one column of the row being checked, so the
# count is the data's shape, not a design smell: a caller writes
# `value_text=...` at the call site and cannot transpose two of them. The
# usual remedy, folding them into a parameter object, would mean this pure
# module either imports the ORM row type (it must not; that is what keeps it
# importable without a database) or ships a second near-duplicate value type
# for callers to construct. Neither is an improvement over five named
# keywords.
def validate_personalization_value(  # noqa: PLR0913
    slot_type: str,
    age_band: AgeBand,
    *,
    value_text: str | None = None,
    value_enum: str | None = None,
    value_profile_id: uuid.UUID | None = None,
    family_profile_ids: Collection[uuid.UUID] = (),
) -> list[SlotViolation]:
    """Return every reason a proposed personalization value should be rejected.

    Pure and total: no I/O, no LLM calls, no randomness, no database access.
    Calling this twice with the same arguments always returns an equal list.
    An empty list means the value passes and may be written or rendered.

    Exactly one of `value_text`, `value_enum`, `value_profile_id` is expected
    to be non-None, mirroring `ChildProfilePersonalization`'s
    `ck_cpp_exactly_one_value` CHECK constraint; this function does not itself
    enforce that shape (the caller's own row/payload already guarantees it),
    it only validates whichever value is present.

    #CRITICAL: security: the structural and denylist checks are this
    project's only defense against a personalization value forging a
    template token or introducing band-forbidden content into rendered prose;
    the sibling check is this project's only defense against a family reading
    a profile it does not own into its own story.
    #VERIFY: tests/unit/test_personalization_values.py exercises all four
    rejection classes.

    Args:
        slot_type: The `ChildProfilePersonalization.slot_type` this value is
            bound to (e.g. `"protagonist_first_name"`, `"pet_species"`).
        age_band: The subject profile's reading age band, used to resolve the
            band-mandatory denylist floor.
        value_text: The candidate free-text value, or None if this slot's
            value is enum- or profile-shaped.
        value_enum: The candidate closed-enum choice, or None if this slot's
            value is text- or profile-shaped.
        value_profile_id: The candidate sibling profile id, or None if this
            slot's value is text- or enum-shaped.
        family_profile_ids: The requesting family's own child profile ids,
            resolved by the caller (never by this module). Only consulted
            when `slot_type` is `SIBLING_SLOT_TYPE`.

    Returns:
        A list of every `SlotViolation` found (each carrying `slot_type` as
        its `slot_id`), in a fixed, deterministic order: structural, then
        denylist, then enum membership, then sibling-in-family. Empty when
        the value passes.
    """
    violations: list[SlotViolation] = []
    candidate = value_text if value_text is not None else value_enum

    violations.extend(
        _shape_violations(slot_type, value_text, value_enum, value_profile_id)
    )

    if candidate is not None:
        violations.extend(
            replace(violation, slot_id=slot_type)
            for violation in structural_value_violations(candidate)
        )
        hit_bundles = denylisted_bundles(candidate, band_mandatory_bundles(age_band))
        violations.extend(
            SlotViolation(
                slot_type,
                f"forbid:{bundle_id}",
                f"value matches a denylisted term in bundle '{bundle_id}'",
            )
            for bundle_id in sorted(hit_bundles)
        )

    if value_enum is not None and slot_type in CLOSED_VOCABULARIES:
        vocabulary = CLOSED_VOCABULARIES[slot_type]
        if value_enum not in vocabulary:
            # #CRITICAL: security: name the SLOT, never the candidate.
            # SlotViolation.message's contract (validator/slots.py:219-221)
            # is that it never contains the candidate story text, and this
            # message flows to logger.warning("project_error", ...) in
            # app.py and into the 422 body (_client_safe_error strips
            # `value` and `context`, not `message`). Every vocabulary here
            # ships empty by design, so EVERY value_enum submission for these
            # five slots takes this branch; kinship_label is designed to hold
            # values like "Grandma Rosita". Application logs have no erasure
            # path, so echoing the value here writes a child's kinship term
            # for a real relative into log storage on the default path.
            # #VERIFY: tests/unit/test_personalization_values.py asserts the
            # message does not contain the candidate.
            enum_message = (
                f"value for slot '{slot_type}' is not a member of its closed vocabulary"
            )
            violations.append(SlotViolation(slot_type, "enum_membership", enum_message))

    if slot_type == SIBLING_SLOT_TYPE and value_profile_id not in family_profile_ids:
        sibling_message = "sibling slot's value_profile_id is not one of the requesting family's own profile ids"
        violations.append(
            SlotViolation(slot_type, "sibling_outside_family", sibling_message)
        )

    return violations


# PLR0913: see the note above `validate_personalization_value`.
def personalization_value_for_payload(  # noqa: PLR0913
    slot_type: str,
    age_band: AgeBand,
    *,
    value_text: str | None = None,
    value_enum: str | None = None,
    value_profile_id: uuid.UUID | None = None,
    family_profile_ids: Collection[uuid.UUID] = (),
    on_reject: Callable[[Sequence[SlotViolation]], None] | None = None,
) -> str | uuid.UUID | None:
    """Return the render-ready value, or None to omit an invalid slot.

    Embodies ADR-023's render-time fallback contract: a value that fails
    `validate_personalization_value` at payload-build time is never raised as
    an error, it is treated exactly like a slot the guardian never set. The
    caller drops the corresponding key from the render payload and the story
    falls back to its generic, non-personalized default for that slot.

    Args:
        slot_type: The `ChildProfilePersonalization.slot_type` this value is
            bound to.
        age_band: The subject profile's reading age band.
        value_text: The stored free-text value, or None.
        value_enum: The stored closed-enum choice, or None.
        value_profile_id: The stored sibling profile id, or None.
        family_profile_ids: The requesting family's own child profile ids;
            see `validate_personalization_value`.
        on_reject: Called with the violations when a value is dropped, and
            not called at all when it passes. The observability seam for
            this function's silent-omission contract: a value reaching here
            invalid means it was accepted at write time and has since gone
            bad (a row written before this gate existed, a vocabulary that
            tightened, a sibling profile that left the family), which is a
            real event a reader silently loses a personalized detail to. The
            module stays pure by taking a callback rather than logging
            itself, so the impure caller decides where the signal goes.
            Callers that genuinely do not care may omit it.

    Returns:
        `value_text`, `value_enum`, or `value_profile_id` (whichever is
        non-None), unchanged, when the value passes every check. `None` when
        any check fails, signaling the caller to omit this slot from the
        payload.
    """
    # #ASSUME: data-integrity: dropping the slot is CORRECT (ADR-023's
    # render-time fallback contract is that a bad value degrades to the
    # story's generic default, never to an error), but dropping it without a
    # trace is not: the same row will fail on every subsequent render and
    # nothing would ever surface it. `on_reject` is how the caller learns.
    # #VERIFY: violations carry the slot id and rule name only, never the
    # candidate text, so a caller can log them directly; that is
    # `SlotViolation.message`'s own documented contract and the reason the
    # enum-membership message above names the slot instead of the value.
    violations = validate_personalization_value(
        slot_type,
        age_band,
        value_text=value_text,
        value_enum=value_enum,
        value_profile_id=value_profile_id,
        family_profile_ids=family_profile_ids,
    )
    if violations:
        if on_reject is not None:
            on_reject(violations)
        return None
    if value_text is not None:
        return value_text
    if value_enum is not None:
        return value_enum
    return value_profile_id
