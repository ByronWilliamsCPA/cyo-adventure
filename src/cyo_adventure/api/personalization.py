"""Story personalization API: ring-1/ring-2 CRUD, consent, and values lookup.

Ring-1 CRUD, ring-2 disclosure consent, and the resolved values payload a
reader fetches for one book (ADR-023 P4/P5). Three route groups, per
``docs/planning/story-personalization-implementation-plan.md`` section 6:

1. ``GET``/``PUT /profiles/{profile_id}/personalization``: guardian-only,
   ownership-scoped CRUD over one profile's slot values and ring flags. The
   PUT is a whole-state replace, never a patch (section 6.1): a partial patch
   over a per-slot table invites ambiguity about whether an absent slot_type
   means "unchanged" or "cleared".
2. ``POST``/``DELETE /profiles/{profile_id}/ring2-consent[/{connection_id}]``:
   the SHARER-side guardian's grant or revoke of a ring-2 disclosure consent.
   ``FamilyConnection.family_id`` is the viewer, ``connected_family_id`` is
   the sharer (db/models.py), the opposite of the intuitive reading; get the
   direction right or consent is collected from the wrong household.
3. ``GET /storybooks/{storybook_id}/personalization-values``: the single
   route that resolves EITHER ring's values payload, keyed only on the book
   (section 8.3). The client never names a connection or a subject profile;
   the server derives both from the caller's own principal and the book's
   ``personalization_subject_profile_id``. Every failure mode (missing
   subject, receive-toggle off, unconnected family, revoked consent, a
   deactivated or processing-restricted subject) renders as the identical
   empty payload rather than a 403 or a narrower shape, so the route leaks
   nothing about whether a subject or connection exists (section 8.4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from sqlalchemy import select

from cyo_adventure.api.deps import (
    Context,
    Principal,
    authorize_profile,
    parse_uuid,
)
from cyo_adventure.api.schemas import (
    PersonalizationSlotBody,
    PersonalizationSlotView,
    PersonalizationUpdateBody,
    PersonalizationValuesView,
    PersonalizationView,
    Ring2ConsentGrantBody,
    Ring2ConsentView,
    error_responses,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    ChildProfile,
    ChildProfilePersonalization,
    Family,
    FamilyConnection,
    PersonalizationDisclosureConsent,
    Storybook,
)
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.personalization_values import (
    SIBLING_SLOT_TYPE,
    personalization_value_for_payload,
    validate_personalization_value,
)
from cyo_adventure.storybook.theme_contract import PERSONALIZATION_FIELDS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1", tags=["personalization"], responses=error_responses(401, 403)
)

# ADR-023 5.1: the ring-2 taxonomy ceiling excludes pronoun_set (grammatical
# choice, outing risk) and dedication (addressed to the giver's own
# household). Encoded here as an API-layer pre-check so a bad request 422s
# cleanly instead of surfacing as a raw ck_cpp_ring2_ceiling IntegrityError.
_RING2_EXCLUDED_SLOT_TYPES = frozenset({"pronoun_set", "dedication"})

_PROTAGONIST_NAME_SLOT = "protagonist_first_name"

# The values route's response is "both rings, identical shape" (plan section
# 6.1), including policy_version. Ring 1 needs no signed disclosure consent,
# so there is no real consent_policy_version to surface for it.
# #ASSUME: product: ADR-023 does not name a ring-1 policy_version value; this
# constant is a deliberate placeholder documenting "no consent was required"
# rather than leaving the field unexplained. #VERIFY: revisit if product
# defines a real ring-1 policy string.
_RING1_POLICY_VERSION = "ring1-no-consent-required"


def _empty_values_view() -> PersonalizationValuesView:
    """Return the universal empty-payload response (plan section 8.4).

    Every predicate failure, of any kind, renders identically: this is what
    keeps the route from leaking whether a subject or a connection exists.
    """
    return PersonalizationValuesView(
        subject_profile_id=None,
        ring=None,
        policy_version=None,
        resolved_at=datetime.now(UTC),
        values={},
    )


def _require_guardian(principal: Principal) -> None:
    """Reject principals that may not manage a profile's personalization.

    Args:
        principal: The authenticated caller.

    Raises:
        AuthorizationError: If the caller does not hold the guardian role.
    """
    # #CRITICAL: security: personalization values render into a child's own
    # story prose and (ring 2) another household's; only the guardian role
    # may write them. Mirrors profiles.py::_require_guardian exactly.
    # #VERIFY: tests/integration/test_personalization_api.py::
    # test_child_cannot_write_personalization.
    if not principal.is_guardian:
        msg = "guardian role required"
        raise AuthorizationError(msg)


def _require_sharer_side(connection: FamilyConnection, family_id: uuid.UUID) -> None:
    """Reject a caller whose family is not the SHARER side of a connection.

    Ring-2 disclosure consent is granted only by the sharer-side guardian
    (plan section 6 routing notes): ``FamilyConnection.family_id`` is the
    viewer, ``connected_family_id`` is the sharer, the opposite of the
    intuitive reading; get the direction wrong and consent is collected from
    the wrong household.

    Args:
        connection: The connection row.
        family_id: The caller's own family id.

    Raises:
        AuthorizationError: If the caller's family is not the sharer side.
    """
    # #CRITICAL: security: this is the sole cross-family gate on the ring-2
    # consent routes; a viewer-side guardian (or an unrelated family guessing
    # a connection id) must never grant or revoke disclosure on the
    # sharer's behalf.
    # #VERIFY: tests/integration/test_personalization_api.py::
    # test_viewer_side_guardian_cannot_grant_ring2_consent.
    if connection.connected_family_id != family_id:
        msg = "only the sharer-side family's guardian may manage this consent"
        raise AuthorizationError(msg)


async def _load_profile(session: AsyncSession, profile_id: uuid.UUID) -> ChildProfile:
    """Load a child profile or raise 404.

    Args:
        session: The request session.
        profile_id: The profile id.

    Returns:
        ChildProfile: The row.

    Raises:
        ResourceNotFoundError: If no profile with this id exists.
    """
    row = await session.get(ChildProfile, profile_id)
    if row is None:
        msg = f"profile '{profile_id}' not found"
        raise ResourceNotFoundError(msg)
    return row


async def _family_profile_ids(
    session: AsyncSession, family_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return every child profile id in a family (for the sibling-in-family check).

    Args:
        session: The request session.
        family_id: The family id.

    Returns:
        set[uuid.UUID]: Every ``ChildProfile.id`` in that family.
    """
    rows = await session.scalars(
        select(ChildProfile.id).where(ChildProfile.family_id == family_id)
    )
    return set(rows.all())


def _slot_view(row: ChildProfilePersonalization) -> PersonalizationSlotView:
    """Build one slot's response view from its stored row.

    Args:
        row: The ORM row.

    Returns:
        PersonalizationSlotView: The wire-safe view, including the derived
        ``ring2_eligible`` ceiling.
    """
    return PersonalizationSlotView(
        slot_type=row.slot_type,
        value_text=row.value_text,
        value_enum=row.value_enum,
        value_profile_id=(
            str(row.value_profile_id) if row.value_profile_id is not None else None
        ),
        ring1_enabled=row.ring1_enabled,
        ring2_enabled=row.ring2_enabled,
        ring2_eligible=row.slot_type not in _RING2_EXCLUDED_SLOT_TYPES,
    )


async def _existing_slots(
    session: AsyncSession, profile_id: uuid.UUID
) -> dict[str, ChildProfilePersonalization]:
    """Load every stored slot row for a profile, keyed by slot_type.

    Args:
        session: The request session.
        profile_id: The profile id.

    Returns:
        dict[str, ChildProfilePersonalization]: slot_type -> row.
    """
    rows = await session.scalars(
        select(ChildProfilePersonalization).where(
            ChildProfilePersonalization.child_profile_id == profile_id
        )
    )
    return {row.slot_type: row for row in rows.all()}


@router.get("/profiles/{profile_id}/personalization", responses=error_responses(404))
async def get_personalization(profile_id: str, ctx: Context) -> PersonalizationView:
    """Read a profile's personalization state for the guardian settings UI.

    Args:
        profile_id: The child profile (path).
        ctx: The request context (principal + unit-of-work session).

    Returns:
        PersonalizationView: The real-name ring flags plus every stored slot,
        each with a read-only ``ring2_eligible`` ceiling.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the caller is not a guardian, or the profile
            is not in the caller's family (403; no existence oracle).
        ResourceNotFoundError: If the row vanished between authorization and
            load.
    """
    _require_guardian(ctx.principal)
    parsed = parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    profile = await _load_profile(ctx.session, parsed)
    slots = await _existing_slots(ctx.session, parsed)
    return PersonalizationView(
        real_name_ring1_enabled=profile.real_name_ring1_enabled,
        real_name_ring2_enabled=profile.real_name_ring2_enabled,
        slots=[_slot_view(slots[slot_type]) for slot_type in sorted(slots)],
    )


def _validate_and_parse_slots(
    body: PersonalizationUpdateBody,
    age_band: AgeBand,
    family_profile_ids: set[uuid.UUID],
) -> list[tuple[PersonalizationSlotBody, uuid.UUID | None]]:
    """Validate every incoming slot and resolve its ``value_profile_id``.

    Split out of ``put_personalization`` to keep the route's own cyclomatic
    complexity within the project's lint threshold; raises on the first
    invalid slot rather than persisting anything (plan section 6.1: the PUT
    is atomic, never partially applied).

    Args:
        body: The incoming whole-state replace body.
        age_band: The profile's age band (drives the band-mandatory denylist).
        family_profile_ids: Every child profile id in the profile's family
            (the sibling-in-family check).

    Returns:
        list[tuple[PersonalizationSlotBody, uuid.UUID | None]]: Each incoming
        slot paired with its parsed ``value_profile_id`` (or ``None``).

    Raises:
        ValidationError: If a slot_type requests a ring-2 ceiling it may not
            hold, or any slot value fails the write-time validation gate.
    """
    parsed_slots: list[tuple[PersonalizationSlotBody, uuid.UUID | None]] = []
    for slot in body.slots:
        if slot.ring2_enabled and slot.slot_type in _RING2_EXCLUDED_SLOT_TYPES:
            msg = f"slot_type '{slot.slot_type}' cannot be ring-2 enabled"
            raise ValidationError(msg, field="ring2_enabled", value=slot.slot_type)
        value_profile_uuid = (
            parse_uuid(slot.value_profile_id, "value_profile_id")
            if slot.value_profile_id is not None
            else None
        )
        violations = validate_personalization_value(
            slot.slot_type,
            age_band,
            value_text=slot.value_text,
            value_enum=slot.value_enum,
            value_profile_id=value_profile_uuid,
            family_profile_ids=family_profile_ids,
        )
        if violations:
            msg = "; ".join(v.message for v in violations)
            raise ValidationError(msg, field=slot.slot_type, value=msg)
        parsed_slots.append((slot, value_profile_uuid))
    return parsed_slots


async def _apply_slot_replace(
    session: AsyncSession,
    profile_id: uuid.UUID,
    existing: dict[str, ChildProfilePersonalization],
    parsed_slots: list[tuple[PersonalizationSlotBody, uuid.UUID | None]],
) -> list[dict[str, object]]:
    """Delete dropped slots, upsert the rest, and collect the toggle events.

    Split out of ``put_personalization`` to keep the route's own cyclomatic
    complexity within the project's lint threshold. Mutates ``session`` (adds
    or deletes ``ChildProfilePersonalization`` rows) but never flushes or
    commits: the caller owns the unit of work.

    Args:
        session: The request session.
        profile_id: The profile whose slots are being replaced.
        existing: The profile's current slot_type -> row mapping.
        parsed_slots: The validated incoming slots from
            :func:`_validate_and_parse_slots`.

    Returns:
        list[dict[str, object]]: One ``PERSONALIZATION_TOGGLED`` payload per
        slot that was disabled, newly enabled, or changed.
    """
    new_slot_types = {slot.slot_type for slot, _ in parsed_slots}
    events: list[dict[str, object]] = []

    for slot_type, row in list(existing.items()):
        if slot_type not in new_slot_types:
            events.append(
                {
                    "slot_type": slot_type,
                    "ring": 2 if row.ring2_enabled else 1,
                    "action": "disabled",
                }
            )
            await session.delete(row)

    for slot, value_profile_uuid in parsed_slots:
        prior = existing.get(slot.slot_type)
        changed = (
            prior is None
            or prior.value_text != slot.value_text
            or prior.value_enum != slot.value_enum
            or prior.value_profile_id != value_profile_uuid
            or prior.ring1_enabled != slot.ring1_enabled
            or prior.ring2_enabled != slot.ring2_enabled
        )
        row = prior
        if row is None:
            row = ChildProfilePersonalization(
                child_profile_id=profile_id, slot_type=slot.slot_type
            )
            session.add(row)
        row.value_text = slot.value_text
        row.value_enum = slot.value_enum
        row.value_profile_id = value_profile_uuid
        row.ring1_enabled = slot.ring1_enabled
        row.ring2_enabled = slot.ring2_enabled
        if changed:
            events.append(
                {
                    "slot_type": slot.slot_type,
                    "ring": 2 if slot.ring2_enabled else 1,
                    "action": "enabled" if prior is None else "updated",
                }
            )
    return events


@router.put("/profiles/{profile_id}/personalization", responses=error_responses(404))
async def put_personalization(
    profile_id: str, body: PersonalizationUpdateBody, ctx: Context
) -> PersonalizationView:
    """Replace a profile's whole personalization state (plan section 6.1).

    A full replace, never a patch: any slot_type stored today but absent
    from ``body.slots`` is cleared. Every incoming value clears the write-time
    validation gate (structural injection guard, band-mandatory denylist,
    closed-enum membership, sibling-in-family) before anything is persisted.

    Args:
        profile_id: The child profile (path).
        body: The whole new personalization state.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        PersonalizationView: The stored state after the replace.

    Raises:
        ValidationError: If profile_id is not a UUID, a slot_type requests a
            ring-2 ceiling it may not hold, or any slot value fails the
            write-time validation gate (422).
        AuthorizationError: If the caller is not a guardian, or the profile
            is not in the caller's family (403).
        ResourceNotFoundError: If the row vanished between authorization and
            load.
    """
    _require_guardian(ctx.principal)
    parsed = parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    profile = await _load_profile(ctx.session, parsed)
    age_band = AgeBand(profile.age_band)
    family_profile_ids = await _family_profile_ids(ctx.session, profile.family_id)

    parsed_slots = _validate_and_parse_slots(body, age_band, family_profile_ids)
    existing = await _existing_slots(ctx.session, parsed)
    events = await _apply_slot_replace(ctx.session, parsed, existing, parsed_slots)

    if (
        profile.real_name_ring1_enabled != body.real_name_ring1_enabled
        or profile.real_name_ring2_enabled != body.real_name_ring2_enabled
    ):
        events.append(
            {
                "slot_type": _PROTAGONIST_NAME_SLOT,
                "ring": 2 if body.real_name_ring2_enabled else 1,
                "action": "updated",
            }
        )
    profile.real_name_ring1_enabled = body.real_name_ring1_enabled
    profile.real_name_ring2_enabled = body.real_name_ring2_enabled

    await ctx.session.flush()
    for payload in events:
        await record_event(
            ctx.session,
            Actor.from_principal(ctx.principal),
            entity_type="child_profile_personalization",
            entity_id=str(parsed),
            event_type=EventType.PERSONALIZATION_TOGGLED,
            payload=payload,
        )

    slots = await _existing_slots(ctx.session, parsed)
    return PersonalizationView(
        real_name_ring1_enabled=profile.real_name_ring1_enabled,
        real_name_ring2_enabled=profile.real_name_ring2_enabled,
        slots=[_slot_view(slots[slot_type]) for slot_type in sorted(slots)],
    )


@router.post(
    "/profiles/{profile_id}/ring2-consent",
    status_code=201,
    responses=error_responses(404),
)
async def grant_ring2_consent(
    profile_id: str,
    body: Ring2ConsentGrantBody,
    ctx: Context,
    request: Request,
) -> Ring2ConsentView:
    """Grant, or supersede, a ring-2 disclosure consent (sharer-side only).

    Re-consent supersedes the existing row in place with a new
    ``consent_accepted_at``/``consent_policy_version`` (plan section 5.3,
    ADR-023 OD-5(c)); narrowing ``covered_slot_types`` does not require
    re-signing.

    Args:
        profile_id: The subject child profile, in the SHARER family (path).
        body: The consent grant.
        ctx: The request context (principal + unit-of-work session).
        request: The inbound request, read only for its client address
            (stamped server-side, never accepted from the client).

    Returns:
        Ring2ConsentView: The stored consent row.

    Raises:
        ValidationError: If profile_id or family_connection_id is not a
            UUID, covered_slot_types names an ineligible slot, or the
            sibling slot is covered without ``sibling_authority_attested``
            (422).
        AuthorizationError: If the caller is not a guardian, the profile is
            not in the caller's family, or the caller's family is not the
            connection's sharer side (403).
        ResourceNotFoundError: If the profile or connection does not exist.
    """
    _require_guardian(ctx.principal)
    parsed = parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_profile(ctx.session, parsed)
    connection_id = parse_uuid(body.family_connection_id, "family_connection_id")
    connection = await ctx.session.get(FamilyConnection, connection_id)
    if connection is None:
        msg = f"family connection '{body.family_connection_id}' not found"
        raise ResourceNotFoundError(msg)
    _require_sharer_side(connection, ctx.principal.family_id)

    invalid_slots = sorted(
        slot_type
        for slot_type in body.covered_slot_types
        if slot_type not in PERSONALIZATION_FIELDS
        or slot_type in _RING2_EXCLUDED_SLOT_TYPES
    )
    if invalid_slots:
        msg = f"covered_slot_types contains ineligible slot type(s): {invalid_slots}"
        raise ValidationError(msg, field="covered_slot_types", value=invalid_slots)
    # Plan section 6.1: required true when covered_slot_types includes the
    # sibling slot (design plan 10.1's attestation ceremony).
    if SIBLING_SLOT_TYPE in body.covered_slot_types and not (
        body.sibling_authority_attested
    ):
        msg = (
            "sibling_authority_attested must be true when covered_slot_types "
            "includes the sibling slot"
        )
        raise ValidationError(
            msg,
            field="sibling_authority_attested",
            value=body.sibling_authority_attested,
        )

    existing = await ctx.session.scalar(
        select(PersonalizationDisclosureConsent).where(
            PersonalizationDisclosureConsent.child_profile_id == parsed,
            PersonalizationDisclosureConsent.family_connection_id == connection_id,
        )
    )
    sharer_family = await ctx.session.get(Family, connection.connected_family_id)
    label = sharer_family.name if sharer_family is not None else None
    # #CRITICAL: security: consent_ip and consent_accepted_at are stamped
    # server-side and never accepted from the client, mirroring
    # POST /v1/onboarding's ADR-018 D1 consent (plan section 6.1).
    # #VERIFY: tests/integration/test_personalization_api.py::
    # test_ring2_consent_ignores_client_supplied_ip_and_timestamp.
    client_ip = request.client.host if request.client is not None else None
    now = datetime.now(UTC)
    row = existing
    if row is None:
        row = PersonalizationDisclosureConsent(
            child_profile_id=parsed,
            family_connection_id=connection_id,
        )
        ctx.session.add(row)
    row.connected_family_label = label
    row.covered_slot_types = list(body.covered_slot_types)
    row.sibling_authority_attested = bool(body.sibling_authority_attested)
    row.consent_accepted_at = now
    row.consent_policy_version = body.policy_version
    row.consent_signer_name = body.signer_name
    row.consent_ip = client_ip
    row.revoked_at = None
    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="personalization_consent",
        entity_id=str(row.id),
        event_type=EventType.RING2_CONSENT_GRANTED,
        payload={
            "connected_family_id": str(connection.family_id),
            "slot_type_count": len(body.covered_slot_types),
        },
    )
    return Ring2ConsentView(
        id=str(row.id),
        child_profile_id=str(row.child_profile_id),
        family_connection_id=(
            str(row.family_connection_id)
            if row.family_connection_id is not None
            else None
        ),
        covered_slot_types=list(row.covered_slot_types or []),
        sibling_authority_attested=row.sibling_authority_attested,
        consent_accepted_at=row.consent_accepted_at,
        consent_policy_version=row.consent_policy_version,
        consent_signer_name=row.consent_signer_name,
        revoked_at=row.revoked_at,
    )


@router.delete(
    "/profiles/{profile_id}/ring2-consent/{connection_id}",
    responses=error_responses(404),
)
async def revoke_ring2_consent(
    profile_id: str, connection_id: str, ctx: Context
) -> Ring2ConsentView:
    """Revoke a ring-2 disclosure consent (sharer-side only).

    Args:
        profile_id: The subject child profile, in the SHARER family (path).
        connection_id: The connection the consent was granted on (path).
        ctx: The request context (principal + unit-of-work session).

    Returns:
        Ring2ConsentView: The revoked (but not deleted) consent row.

    Raises:
        ValidationError: If either id is not a UUID.
        AuthorizationError: If the caller is not a guardian, the profile is
            not in the caller's family, or the caller's family is not the
            connection's sharer side (403).
        ResourceNotFoundError: If the profile, connection, or consent row
            does not exist.
    """
    _require_guardian(ctx.principal)
    parsed_profile = parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed_profile)
    await _load_profile(ctx.session, parsed_profile)
    parsed_connection = parse_uuid(connection_id, "connection_id")
    connection = await ctx.session.get(FamilyConnection, parsed_connection)
    if connection is None:
        msg = f"family connection '{connection_id}' not found"
        raise ResourceNotFoundError(msg)
    _require_sharer_side(connection, ctx.principal.family_id)
    row = await ctx.session.scalar(
        select(PersonalizationDisclosureConsent).where(
            PersonalizationDisclosureConsent.child_profile_id == parsed_profile,
            PersonalizationDisclosureConsent.family_connection_id == parsed_connection,
        )
    )
    if row is None:
        msg = "no ring-2 disclosure consent exists for this profile and connection"
        raise ResourceNotFoundError(msg)
    row.revoked_at = datetime.now(UTC)
    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="personalization_consent",
        entity_id=str(row.id),
        event_type=EventType.RING2_CONSENT_REVOKED,
        payload={"connected_family_id": str(connection.family_id)},
    )
    return Ring2ConsentView(
        id=str(row.id),
        child_profile_id=str(row.child_profile_id),
        family_connection_id=(
            str(row.family_connection_id)
            if row.family_connection_id is not None
            else None
        ),
        covered_slot_types=list(row.covered_slot_types or []),
        sibling_authority_attested=row.sibling_authority_attested,
        consent_accepted_at=row.consent_accepted_at,
        consent_policy_version=row.consent_policy_version,
        consent_signer_name=row.consent_signer_name,
        revoked_at=row.revoked_at,
    )


def _is_dual_consented(connection: FamilyConnection) -> bool:
    """Return whether both guardians have actively consented (ADR-016).

    Mirrors ``recommendations.py::_is_dual_consented`` /
    ``family_connections.py::_is_active`` exactly; duplicated per this
    codebase's small-helper-duplication convention (each router owns its own
    copy rather than importing across a router boundary).

    Args:
        connection: The connection row.

    Returns:
        bool: True only when both consent columns are set.
    """
    return (
        connection.consented_by_viewer_user_id is not None
        and connection.consented_by_sharer_user_id is not None
    )


async def _live_consent(
    session: AsyncSession, profile_id: uuid.UUID, connection_id: uuid.UUID
) -> PersonalizationDisclosureConsent | None:
    """Return the non-revoked ring-2 consent row for (profile, connection), if any.

    Args:
        session: The request session.
        profile_id: The subject profile id.
        connection_id: The connection id.

    Returns:
        PersonalizationDisclosureConsent | None: The live row, or None if
        revoked or never granted.
    """
    return await session.scalar(
        select(PersonalizationDisclosureConsent).where(
            PersonalizationDisclosureConsent.child_profile_id == profile_id,
            PersonalizationDisclosureConsent.family_connection_id == connection_id,
            PersonalizationDisclosureConsent.revoked_at.is_(None),
        )
    )


def _is_live(profile: ChildProfile) -> bool:
    """Return whether a profile is neither deactivated nor processing-restricted.

    Plan section 8.4 conditions 4/8: a deactivated or Article-18-restricted
    profile's details must not flow outward, in either ring.

    Args:
        profile: The profile row.

    Returns:
        bool: True when both timestamps are None.
    """
    return profile.deactivated_at is None and profile.processing_restricted_at is None


async def _ring1_values(session: AsyncSession, subject: ChildProfile) -> dict[str, str]:
    """Resolve the ring-1 (own-family) values payload for a subject profile.

    Args:
        session: The request session.
        subject: The subject profile.

    Returns:
        dict[str, str]: slot_type -> rendered value, for every ring-1-enabled
        slot (plus the real-name slot) whose value clears the render-time
        fallback check. An invalid or missing value is simply omitted
        (ADR-023's render-time fallback contract), never an error.
    """
    values: dict[str, str] = {}
    family_profile_ids = await _family_profile_ids(session, subject.family_id)
    if subject.real_name_ring1_enabled:
        values[_PROTAGONIST_NAME_SLOT] = subject.display_name
    rows = await session.scalars(
        select(ChildProfilePersonalization).where(
            ChildProfilePersonalization.child_profile_id == subject.id,
            ChildProfilePersonalization.ring1_enabled.is_(True),
        )
    )
    for row in rows:
        rendered = personalization_value_for_payload(
            row.slot_type,
            AgeBand(subject.age_band),
            value_text=row.value_text,
            value_enum=row.value_enum,
            value_profile_id=row.value_profile_id,
            family_profile_ids=family_profile_ids,
        )
        if rendered is None:
            continue
        if row.slot_type == SIBLING_SLOT_TYPE and isinstance(rendered, uuid.UUID):
            sibling = await session.get(ChildProfile, rendered)
            if sibling is not None:
                values[row.slot_type] = sibling.display_name
            continue
        values[row.slot_type] = str(rendered)
    return values


async def _ring2_sibling_value(
    session: AsyncSession,
    sibling_id: uuid.UUID,
    connection: FamilyConnection,
) -> str | None:
    """Resolve a sibling slot's disclosed name under ITS OWN ring-2 settings.

    Plan section 8.4 condition 8: B's name is disclosed under B's own
    name-sharing settings and B's own consent record on this same
    connection, never under A's. Any failure omits only the sibling slot.

    Args:
        session: The request session.
        sibling_id: The referenced sibling profile's id (A's stored
            ``value_profile_id``).
        connection: The (A-viewer, B-sharer) connection already resolved for
            A's own payload.

    Returns:
        str | None: B's display name if every condition holds, else None.
    """
    sibling = await session.get(ChildProfile, sibling_id)
    if sibling is None:
        return None
    if sibling.family_id != connection.connected_family_id:
        return None
    if not _is_live(sibling):
        return None
    if not sibling.real_name_ring2_enabled:
        return None
    consent = await _live_consent(session, sibling_id, connection.id)
    if consent is None or _PROTAGONIST_NAME_SLOT not in (
        consent.covered_slot_types or []
    ):
        return None
    return sibling.display_name


async def _ring2_values(
    session: AsyncSession, subject: ChildProfile, connection: FamilyConnection
) -> tuple[dict[str, str], str | None]:
    """Resolve the ring-2 (cross-family) values payload for a subject profile.

    Args:
        session: The request session.
        subject: The subject profile (the sharer-family child).
        connection: The resolved (viewer=caller, sharer=subject) connection.

    Returns:
        tuple[dict[str, str], str | None]: slot_type -> rendered value,
        filtered per-slot (plan section 8.4: a slot failing the ring-2
        predicate is omitted individually, never all-or-nothing), paired
        with A's own live consent's ``consent_policy_version``. Returning
        the policy version alongside the values (rather than the caller
        re-querying consent afterward) closes a TOCTOU window: a second,
        later query could observe a consent revoked between the two reads
        and fall back to a value that misrepresents a ring-2 response as
        needing no consent.
    """
    values: dict[str, str] = {}
    consent = await _live_consent(session, subject.id, connection.id)
    policy_version = consent.consent_policy_version if consent is not None else None
    covered: frozenset[str] = (
        frozenset(consent.covered_slot_types or [])
        if consent is not None
        else frozenset()
    )
    if subject.real_name_ring2_enabled and _PROTAGONIST_NAME_SLOT in covered:
        values[_PROTAGONIST_NAME_SLOT] = subject.display_name
    rows = await session.scalars(
        select(ChildProfilePersonalization).where(
            ChildProfilePersonalization.child_profile_id == subject.id,
            ChildProfilePersonalization.ring2_enabled.is_(True),
        )
    )
    for row in rows:
        if row.slot_type in _RING2_EXCLUDED_SLOT_TYPES or row.slot_type not in covered:
            continue
        if row.slot_type == SIBLING_SLOT_TYPE:
            if row.value_profile_id is None:
                continue
            sibling_value = await _ring2_sibling_value(
                session, row.value_profile_id, connection
            )
            if sibling_value is not None:
                values[row.slot_type] = sibling_value
            continue
        rendered = personalization_value_for_payload(
            row.slot_type,
            AgeBand(subject.age_band),
            value_text=row.value_text,
            value_enum=row.value_enum,
            value_profile_id=row.value_profile_id,
        )
        if rendered is not None:
            values[row.slot_type] = str(rendered)
    return values, policy_version


async def _resolve_ring1_view(
    session: AsyncSession, subject: ChildProfile
) -> PersonalizationValuesView:
    """Resolve the ring-1 (own-family) values view for a live subject.

    Split out of ``get_personalization_values`` to keep the route's own
    cyclomatic complexity within the project's lint threshold.

    Args:
        session: The request session.
        subject: The book's personalization subject (already known to be in
            the caller's own family).

    Returns:
        PersonalizationValuesView: The ring-1 payload, or the universal
        empty payload if the subject is not live or has no eligible values.
    """
    if not _is_live(subject):
        return _empty_values_view()
    values = await _ring1_values(session, subject)
    if not values:
        return _empty_values_view()
    return PersonalizationValuesView(
        subject_profile_id=str(subject.id),
        ring=1,
        policy_version=_RING1_POLICY_VERSION,
        resolved_at=datetime.now(UTC),
        values=values,
    )


async def _resolve_ring2_view(
    session: AsyncSession, subject: ChildProfile, caller_family_id: uuid.UUID
) -> PersonalizationValuesView:
    """Resolve the ring-2 (cross-family) values view for a subject.

    Split out of ``get_personalization_values`` to keep the route's own
    cyclomatic complexity within the project's lint threshold. Implements
    plan section 8.6's condition 0 plus the connection/consent/liveness
    predicate (section 8.4): every failure renders the identical empty
    payload, never a 403.

    Args:
        session: The request session.
        subject: The book's personalization subject (already known to be in
            a different family than the caller).
        caller_family_id: The caller's own family id (the viewer side).

    Returns:
        PersonalizationValuesView: The ring-2 payload, or the universal
        empty payload on any predicate failure.
    """
    # The server resolves the connection; the client never names it.
    connection = await session.scalar(
        select(FamilyConnection).where(
            FamilyConnection.family_id == caller_family_id,
            FamilyConnection.connected_family_id == subject.family_id,
        )
    )
    if connection is None:
        return _empty_values_view()
    # Condition 0: the viewer-side receive toggle, evaluated before any
    # sharer-side lookup.
    viewer_family = await session.get(Family, caller_family_id)
    if viewer_family is None or not viewer_family.personalization_receive_enabled:
        return _empty_values_view()
    if not _is_dual_consented(connection):
        return _empty_values_view()
    if not _is_live(subject):
        return _empty_values_view()
    values, policy_version = await _ring2_values(session, subject, connection)
    if not values:
        return _empty_values_view()
    return PersonalizationValuesView(
        subject_profile_id=str(subject.id),
        ring=2,
        policy_version=policy_version,
        resolved_at=datetime.now(UTC),
        values=values,
    )


@router.get(
    "/storybooks/{storybook_id}/personalization-values",
    responses=error_responses(404),
)
async def get_personalization_values(
    storybook_id: str, ctx: Context
) -> PersonalizationValuesView:
    """Resolve the values payload for one book, at whichever ring applies.

    No requested-slot-type parameter exists (plan section 6.1): the server
    returns every slot the subject has enabled and consented for at the
    applicable ring, and the client discards what it does not need. This is
    a genuinely new authorization shape (plan section 8.5): the route does
    NOT authorize on the subject profile via ``authorize_profile``; it
    authorizes on the connection (a family-level fact) plus the caller's own
    family membership, so a child session in the viewer family may read a
    payload about a profile it could never otherwise act on.

    Args:
        storybook_id: The book (path).
        ctx: The request context (principal + unit-of-work session).

    Returns:
        PersonalizationValuesView: The resolved payload, or the universal
        empty payload (never a 403) on any predicate failure.

    Raises:
        ResourceNotFoundError: If no storybook with this id exists.
    """
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if book.personalization_subject_profile_id is None:
        return _empty_values_view()
    subject = await ctx.session.get(
        ChildProfile, book.personalization_subject_profile_id
    )
    if subject is None:
        return _empty_values_view()

    caller_family_id = ctx.principal.family_id
    if subject.family_id == caller_family_id:
        return await _resolve_ring1_view(ctx.session, subject)
    return await _resolve_ring2_view(ctx.session, subject, caller_family_id)
