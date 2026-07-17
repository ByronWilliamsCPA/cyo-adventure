"""DB-touching projection: pipeline_event rows -> family-scoped NotificationItems.

Read-only (S9 delivery infrastructure, G10 first slice): never writes to
``pipeline_event`` or any other table. Family scoping is the load-bearing
security property this module provides. ``pipeline_event`` carries no
``family_id`` column (events/writer.py's D3 payload contract keeps rows
PII-free and entity-scoped, not family-scoped, and db/models.py's
``PipelineEvent`` docstring confirms the schema), so every event's family
membership is derived by joining back to the entity table its
``(entity_type, entity_id)`` names. An event whose ``entity_type`` this
module has no resolver for, or whose resolved family does not match the
caller, is dropped -- never surfaced. That drop is enforced in exactly one
place (``list_guardian_notifications`` below) so no future entity resolver
or composer can accidentally leak a cross-family row.

#EDGE: external-resources/performance: because there is no family_id column,
the candidate query below cannot push family scoping into SQL; it fetches the
N most recent guardian-relevant events ACROSS ALL FAMILIES (bounded by
``_candidate_cap``) and only then resolves and filters by family. In a busy
multi-tenant deployment this could starve out an older-but-still-recent
notification for a quiet family behind a burst of unrelated-family activity
between ``since`` and now. Accepted for this first slice (the project's
homelab-first / small-tenant deployment target, per
docs/planning/adr/adr-004-homelab-first-deployment.md); a durable fix is a
backfill migration adding ``pipeline_event.family_id``, which is future work,
not a defect in this slice.
#VERIFY: tests/unit/test_notifications_service.py::
test_candidate_cap_is_generous_relative_to_requested_limit pins the
multiplier/floor/ceiling; revisit if real traffic is ever seen to truncate.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from sqlalchemy import select, tuple_

from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    GenerationJob,
    KidFlag,
    PipelineEvent,
    Storybook,
    StorybookVersion,
    StoryRequest,
)
from cyo_adventure.notifications.models import (
    EntityContext,
    NotificationItem,
    RawNotification,
)
from cyo_adventure.notifications.registry import compose, relevant_event_type_values

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal

EntityResolver = Callable[
    ["AsyncSession", "list[str]"], "Awaitable[dict[str, EntityContext]]"
]

_CANDIDATE_MULTIPLIER = 20
_CANDIDATE_FLOOR = 200
_CANDIDATE_CEILING = 1000


def _candidate_cap(limit: int) -> int:
    """Return the candidate-fetch cap for a requested page size.

    Args:
        limit: The caller's requested (already bounds-checked) page size.

    Returns:
        int: ``limit`` scaled up generously, clamped to a floor and ceiling
        so a tiny ``limit`` still leaves room for family-filtering losses and
        a huge one cannot force an unbounded fetch.
    """
    return min(max(limit * _CANDIDATE_MULTIPLIER, _CANDIDATE_FLOOR), _CANDIDATE_CEILING)


def _parse_uuids(raw_ids: list[str]) -> dict[str, uuid.UUID]:
    """Return the subset of ``raw_ids`` that parse as UUIDs, keyed by the original.

    A malformed id is never written by this codebase's own ``record_event``
    call sites, but this module must not trust that from a durable log it
    only reads; a corrupt row is silently excluded rather than raising, so it
    cannot 500 the whole feed.

    Args:
        raw_ids: Candidate ``pipeline_event.entity_id`` strings.

    Returns:
        dict[str, uuid.UUID]: Only the ids that parsed, original -> parsed.
    """
    parsed: dict[str, uuid.UUID] = {}
    for raw in raw_ids:
        try:
            parsed[raw] = uuid.UUID(raw)
        except ValueError:
            continue
    return parsed


async def _profile_names(
    session: AsyncSession, profile_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Return ``{profile_id: display_name}`` for the given profiles.

    Args:
        session: The request database session.
        profile_ids: The profile ids to look up.

    Returns:
        dict[uuid.UUID, str]: Display names for whichever ids exist.
    """
    if not profile_ids:
        return {}
    rows = (
        await session.execute(
            select(ChildProfile.id, ChildProfile.display_name).where(
                ChildProfile.id.in_(profile_ids)
            )
        )
    ).all()
    # A plain dict(rows) is what ruff (C416) wants here, but basedpyright's
    # dict() overload resolution picks the wrong overload for a sequence of
    # SQLAlchemy Row tuples and reports a spurious dict[bytes, bytes] return
    # type error; the comprehension sidesteps that and type-checks cleanly.
    return {profile_id: display_name for profile_id, display_name in rows}  # noqa: C416


async def _titles_for_pairs(
    session: AsyncSession, pairs: list[tuple[str, int]]
) -> dict[str, str]:
    """Return ``{storybook_id: title}`` for exactly the given (id, version) pairs.

    Args:
        session: The request database session.
        pairs: ``(storybook_id, version)`` pairs to fetch titles for; callers
            pass each book's ``current_published_version``, never an
            arbitrary version, so the title shown always matches what a
            guardian would see on the shelf today.

    Returns:
        dict[str, str]: Titles for pairs whose version row exists and carries
        a well-formed ``blob["title"]``. An id absent from the map (no
        published version, a missing row, or a malformed/blank title) is
        left for the caller to fall back on, mirroring
        api/library.py::_str_field's degrade-not-crash posture for the same
        blob field.
    """
    if not pairs:
        return {}
    versions = (
        await session.scalars(
            select(StorybookVersion).where(
                tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                    pairs
                )
            )
        )
    ).all()
    titles: dict[str, str] = {}
    for version in versions:
        blob = version.blob
        title = blob.get("title") if isinstance(blob, dict) else None
        if isinstance(title, str) and title:
            titles[version.storybook_id] = title
    return titles


async def _resolve_story_request(
    session: AsyncSession, ids: list[str]
) -> dict[str, EntityContext]:
    """Resolve ``story_request``-entity events: family + requesting child's name."""
    id_map = _parse_uuids(ids)
    if not id_map:
        return {}
    rows = (
        await session.scalars(
            select(StoryRequest).where(StoryRequest.id.in_(id_map.values()))
        )
    ).all()
    by_id = {row.id: row for row in rows}
    profile_ids = {row.profile_id for row in rows if row.profile_id is not None}
    names = await _profile_names(session, profile_ids)
    result: dict[str, EntityContext] = {}
    for raw, parsed in id_map.items():
        row = by_id.get(parsed)
        if row is None:
            continue
        result[raw] = EntityContext(
            family_id=row.family_id,
            request_id=raw,
            profile_id=row.profile_id,
            profile_name=names.get(row.profile_id) if row.profile_id else None,
        )
    return result


async def _resolve_generation_job(
    session: AsyncSession, ids: list[str]
) -> dict[str, EntityContext]:
    """Resolve ``generation_job``-entity events: family via the job's concept.

    ``GenerationJob`` carries no ``family_id`` of its own (see its class
    docstring); ``Concept.family_id`` is the only path back to a family.
    """
    id_map = _parse_uuids(ids)
    if not id_map:
        return {}
    rows = (
        await session.execute(
            select(GenerationJob, Concept.family_id)
            .join(Concept, GenerationJob.concept_id == Concept.id)
            .where(GenerationJob.id.in_(id_map.values()))
        )
    ).all()
    by_id = {job.id: (job, family_id) for job, family_id in rows}
    result: dict[str, EntityContext] = {}
    for raw, parsed in id_map.items():
        found = by_id.get(parsed)
        if found is None:
            continue
        job, family_id = found
        result[raw] = EntityContext(family_id=family_id, storybook_id=job.storybook_id)
    return result


async def _resolve_storybook(
    session: AsyncSession, ids: list[str]
) -> dict[str, EntityContext]:
    """Resolve ``storybook``-entity events (RELEASED): family + current title."""
    rows = (await session.scalars(select(Storybook).where(Storybook.id.in_(ids)))).all()
    pairs = [
        (row.id, row.current_published_version)
        for row in rows
        if row.current_published_version is not None
    ]
    titles = await _titles_for_pairs(session, pairs)
    return {
        row.id: EntityContext(
            family_id=row.family_id,
            storybook_id=row.id,
            storybook_title=titles.get(row.id),
        )
        for row in rows
    }


async def _resolve_storybook_version(
    session: AsyncSession, ids: list[str]
) -> dict[str, EntityContext]:
    """Resolve ``storybook_version``-entity events: id is ``storybook_id:version``.

    Mirrors the parse in moderation/insights.py's own reader of this same
    entity_id shape (``entity_id.rpartition(":")``), so a storybook id that
    itself happens to contain a colon still splits on the LAST colon (the one
    the writer actually used to append the version number).
    """
    parsed: dict[str, tuple[str, int]] = {}
    for raw in ids:
        storybook_id, sep, version_text = raw.rpartition(":")
        if not sep:
            continue
        try:
            parsed[raw] = (storybook_id, int(version_text))
        except ValueError:
            continue
    if not parsed:
        return {}
    pairs = list(parsed.values())
    rows = (
        await session.execute(
            select(StorybookVersion, Storybook.family_id)
            .join(Storybook, StorybookVersion.storybook_id == Storybook.id)
            .where(
                tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                    pairs
                )
            )
        )
    ).all()
    by_pair = {
        (version.storybook_id, version.version): (version, family_id)
        for version, family_id in rows
    }
    result: dict[str, EntityContext] = {}
    for raw, pair in parsed.items():
        found = by_pair.get(pair)
        if found is None:
            continue
        version, family_id = found
        blob = version.blob
        title = blob.get("title") if isinstance(blob, dict) else None
        result[raw] = EntityContext(
            family_id=family_id,
            storybook_id=version.storybook_id,
            storybook_title=title if isinstance(title, str) and title else None,
        )
    return result


async def _resolve_storybook_assignment(
    session: AsyncSession, ids: list[str]
) -> dict[str, EntityContext]:
    """Resolve ``storybook_assignment``-entity events (BOOK_ASSIGNED).

    ``entity_id`` is ``child_profile_id:storybook_id`` (api/assignments.py).
    Family membership is taken from the CHILD's family, not the storybook's:
    a catalog-visibility book can be assigned across families (WS-E), and the
    assignment always belongs to the assigning guardian's own family.
    """
    parsed: dict[str, tuple[uuid.UUID, str]] = {}
    for raw in ids:
        profile_text, sep, storybook_id = raw.partition(":")
        if not sep:
            continue
        try:
            parsed[raw] = (uuid.UUID(profile_text), storybook_id)
        except ValueError:
            continue
    if not parsed:
        return {}
    profile_ids = {profile_id for profile_id, _ in parsed.values()}
    profiles = (
        await session.scalars(
            select(ChildProfile).where(ChildProfile.id.in_(profile_ids))
        )
    ).all()
    profile_by_id = {row.id: row for row in profiles}
    storybook_ids = sorted({storybook_id for _, storybook_id in parsed.values()})
    books = (
        await session.scalars(select(Storybook).where(Storybook.id.in_(storybook_ids)))
    ).all()
    pairs = [
        (book.id, book.current_published_version)
        for book in books
        if book.current_published_version is not None
    ]
    titles = await _titles_for_pairs(session, pairs)
    result: dict[str, EntityContext] = {}
    for raw, (profile_id, storybook_id) in parsed.items():
        profile = profile_by_id.get(profile_id)
        if profile is None:
            continue
        result[raw] = EntityContext(
            family_id=profile.family_id,
            storybook_id=storybook_id,
            storybook_title=titles.get(storybook_id),
            profile_id=profile_id,
            profile_name=profile.display_name,
        )
    return result


async def _resolve_kid_flag(
    session: AsyncSession, ids: list[str]
) -> dict[str, EntityContext]:
    """Resolve ``kid_flag``-entity events (KID_FLAGGED): family via the flag row.

    ``KidFlag.family_id`` is denormalized from the flagging profile
    (mirrors ``StoryRequest.family_id``), so this is a single-table lookup
    plus the same title projection the other resolvers use, pinned to the
    version the child was actually reading (``KidFlag.version``), not
    necessarily the book's current published version.
    """
    id_map = _parse_uuids(ids)
    if not id_map:
        return {}
    rows = (
        await session.scalars(select(KidFlag).where(KidFlag.id.in_(id_map.values())))
    ).all()
    by_id = {row.id: row for row in rows}
    profile_ids = {row.profile_id for row in rows}
    names = await _profile_names(session, profile_ids)
    pairs = [(row.storybook_id, row.version) for row in rows]
    titles = await _titles_for_pairs(session, pairs)
    result: dict[str, EntityContext] = {}
    for raw, parsed in id_map.items():
        row = by_id.get(parsed)
        if row is None:
            continue
        result[raw] = EntityContext(
            family_id=row.family_id,
            storybook_id=row.storybook_id,
            storybook_title=titles.get(row.storybook_id),
            profile_id=row.profile_id,
            profile_name=names.get(row.profile_id),
        )
    return result


# #ASSUME: data-integrity: this is the single point mapping a pipeline_event
# entity_type string to the resolver that knows that entity's shape and how
# to reach its family. A candidate event whose entity_type is not one of
# these six resolves to no EntityContext and is silently dropped in
# list_guardian_notifications below -- see notifications/registry.py's
# module docstring for why that is the correct, fail-safe behavior (never a
# leak, never a crash) rather than a bug to fix reactively. "kid_flag" is the
# entity_type the sibling K15 workstream actually writes EventType.KID_FLAGGED
# against (api/flags.py::flag_passage); EventType.FLAG_RESOLVED also targets
# this entity_type but is not in notifications/registry.py's composer set
# (it is an admin-side event, out of G10's four guardian-alert kinds), so a
# FLAG_RESOLVED row is resolved here but then dropped by registry.compose's
# unmapped-event_type branch, not by this dict.
# #VERIFY: tests/unit/test_notifications_service.py::
# test_unknown_entity_type_is_dropped_not_raised;
# test_resolve_kid_flag_reads_family_from_the_flag_row.
_ENTITY_RESOLVERS: dict[str, EntityResolver] = {
    "story_request": _resolve_story_request,
    "generation_job": _resolve_generation_job,
    "storybook": _resolve_storybook,
    "storybook_version": _resolve_storybook_version,
    "storybook_assignment": _resolve_storybook_assignment,
    "kid_flag": _resolve_kid_flag,
}


async def _fetch_candidates(
    session: AsyncSession, *, since: datetime | None, limit: int
) -> list[PipelineEvent]:
    """Return the most recent guardian-relevant events, across ALL families.

    Args:
        session: The request database session.
        since: Only events strictly after this timestamp, or None.
        limit: The caller's requested page size, used to size the candidate
            fetch (see ``_candidate_cap``).

    Returns:
        list[PipelineEvent]: Newest-first, bounded by ``_candidate_cap(limit)``.
        Never family-filtered -- see the module docstring for why that
        cannot be pushed into this query.
    """
    event_type_values = relevant_event_type_values()
    if not event_type_values:
        return []
    stmt = select(PipelineEvent).where(PipelineEvent.event_type.in_(event_type_values))
    if since is not None:
        stmt = stmt.where(PipelineEvent.occurred_at > since)
    stmt = stmt.order_by(
        PipelineEvent.occurred_at.desc(), PipelineEvent.id.desc()
    ).limit(_candidate_cap(limit))
    return list((await session.scalars(stmt)).all())


async def _resolve_all_contexts(
    session: AsyncSession, candidates: list[PipelineEvent]
) -> dict[tuple[str, str], EntityContext]:
    """Resolve every candidate event's ``EntityContext``, grouped by entity_type.

    One resolver call per distinct entity_type present in ``candidates``
    (never one per event), regardless of how many events share that type.

    Args:
        session: The request database session.
        candidates: The candidate events to resolve entities for.

    Returns:
        dict[tuple[str, str], EntityContext]: Keyed by
        ``(entity_type, entity_id)``; an event whose entity_type has no
        resolver, or whose entity id did not resolve, has no entry.
    """
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for event in candidates:
        ids_by_type[event.entity_type].add(event.entity_id)

    contexts: dict[tuple[str, str], EntityContext] = {}
    for entity_type, ids in ids_by_type.items():
        resolver = _ENTITY_RESOLVERS.get(entity_type)
        if resolver is None:
            continue
        resolved = await resolver(session, sorted(ids))
        for entity_id, ctx in resolved.items():
            contexts[(entity_type, entity_id)] = ctx
    return contexts


def _to_item(
    event: PipelineEvent, ctx: EntityContext, raw: RawNotification
) -> NotificationItem:
    """Assemble the wire-ready item from an event, its context, and its composition."""
    return NotificationItem(
        id=str(event.id),
        occurred_at=event.occurred_at,
        kind=raw.kind,
        severity=raw.severity,
        title=raw.title,
        body=raw.body,
        storybook_id=ctx.storybook_id,
        request_id=ctx.request_id,
        profile_id=str(ctx.profile_id) if ctx.profile_id else None,
    )


async def list_guardian_notifications(
    session: AsyncSession,
    principal: Principal,
    *,
    since: datetime | None,
    limit: int,
) -> list[NotificationItem]:
    """Return the caller's family's notification feed, newest first.

    Read-only projection over ``pipeline_event`` (S9); never writes. Family
    scoping is enforced here, not by the caller: every candidate event's
    owning entity is resolved and compared against ``principal.family_id``
    before it can appear in the result (see the module docstring).

    Args:
        session: The request database session.
        principal: The authenticated (guardian) principal; ``family_id`` is
            the scoping key. The caller (api/notifications.py) is
            responsible for confirming this principal actually holds the
            guardian role before calling; this function does not re-check
            the role, only the family.
        since: Only events strictly after this timestamp, or None for no
            lower bound.
        limit: The maximum number of items to return; must be positive (the
            caller bounds-checks it).

    Returns:
        list[NotificationItem]: Up to ``limit`` items, newest first.
    """
    if limit <= 0:
        return []
    candidates = await _fetch_candidates(session, since=since, limit=limit)
    if not candidates:
        return []
    contexts = await _resolve_all_contexts(session, candidates)

    items: list[NotificationItem] = []
    for event in candidates:
        ctx = contexts.get((event.entity_type, event.entity_id))
        # #CRITICAL: security: an event whose entity did not resolve, or whose
        # resolved family does not match the caller, is dropped here. This is
        # the SOLE family-scoping gate for the entire feed; no composer and no
        # entity resolver re-checks it.
        # #VERIFY: tests/unit/test_notifications_service.py::
        # test_family_scoping_negative_other_family_events_never_appear.
        if ctx is None or ctx.family_id != principal.family_id:
            continue
        raw = compose(event, ctx)
        if raw is None:
            continue
        items.append(_to_item(event, ctx, raw))
        if len(items) >= limit:
            break
    return items
