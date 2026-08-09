"""S9 server-scheduled digest job: a periodic, batched per-family summary.

Distinct from both the poll and the SSE push (``notifications/service.py``,
``api/notifications.py``), neither of which is scheduled infrastructure: a
guardian who never opens the app and whose stream never connects still gets
nothing from either path. This job runs independently (see
``scripts/run_notification_digest.py`` and its scheduled workflow) and
writes one ``NOTIFICATION_DIGEST_READY`` event per family that has pending
info-severity notifications waiting, which then appears on that family's
ordinary feed like any other notification (G10's "digest by default" half).

Out of scope: this only ever writes an IN-APP event. An out-of-band channel
(email, push notification) that could reach a guardian who is not polling
the app at all would need a chosen email/push provider and credentials this
change does not introduce; see docs/planning/roadmap.md's S9 entry.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.database import apply_family_rls_context
from cyo_adventure.db.models import CATALOG_FAMILY_ID, Family, PipelineEvent
from cyo_adventure.events.models import Actor, EventType
from cyo_adventure.events.writer import record_event
from cyo_adventure.notifications.service import list_family_notifications

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

_DIGEST_ENTITY_TYPE = "family"
_DIGEST_CANDIDATE_LIMIT = 200

# #ASSUME: timing dependencies: a family with no prior digest has no cursor to
# resume from; a fresh deployment or a brand-new family should not have its
# first digest dump the family's entire history. 24 hours is a reasonable
# first-run default (matches this job's intended daily cadence), not a
# measurement of real usage.
# #VERIFY: after the first real deployment, confirm the digest job actually
# runs at roughly this cadence (scripts/run_notification_digest.py's
# scheduled workflow); widen or narrow if the cadence changes.
_DEFAULT_LOOKBACK_HOURS = 24


async def _last_digest_at(
    session: AsyncSession, family_id: uuid.UUID
) -> datetime | None:
    """Return this family's most recent digest event's timestamp, or None."""
    return await session.scalar(
        select(PipelineEvent.occurred_at)
        .where(
            PipelineEvent.entity_type == _DIGEST_ENTITY_TYPE,
            PipelineEvent.entity_id == str(family_id),
            PipelineEvent.event_type == EventType.NOTIFICATION_DIGEST_READY,
        )
        .order_by(PipelineEvent.occurred_at.desc())
        .limit(1)
    )


async def _real_family_ids(session: AsyncSession) -> list[uuid.UUID]:
    """Return every family id except the catalog sentinel (owns no guardian)."""
    rows = await session.scalars(
        select(Family.id).where(Family.id != CATALOG_FAMILY_ID)
    )
    return list(rows.all())


async def run_notification_digest(session: AsyncSession, *, now: datetime) -> int:
    """Write one digest event per family with pending info-severity notifications.

    For each real family: resolve its own last-digest cursor (or a default
    lookback window if it has never had one), fetch its notification feed
    since that cursor, and count the info-severity items (an alert has
    already pushed immediately via SSE/toast and does not need batching,
    matching G10's "digest by default, alert on safety" split; a prior
    digest item is excluded so digests never count themselves). A family
    with nothing pending gets no event at all -- a digest job that always
    fires is noise, not a digest.

    Args:
        session: The database session. Callers own the transaction; this
            function flushes (via ``record_event``) but never commits.
        now: The wall-clock time to use for a family's first-ever digest
            lookback window. Passed in rather than read internally so this
            function is deterministic and testable.

    Returns:
        int: The number of families a digest event was written for.
    """
    default_since = now - timedelta(hours=_DEFAULT_LOOKBACK_HOURS)
    written = 0
    for family_id in await _real_family_ids(session):
        # #CRITICAL: security: this job connects as cyo_api (per
        # notification-digest.yml, deliberately bound by the same RLS
        # posture as every other write path), so the Tier 1 family_scoped
        # policy (ADR-022) filters every child_profile/story_request row
        # unless app.family_id is set for the family currently being read.
        # Without this, every Tier 1-backed notification kind (request_*,
        # plan_assigned) silently vanishes from every digest with no
        # exception and no log; kid_flag/storybook/storybook_assignment
        # (Tier 2) are unaffected, which is what makes the gap look like a
        # quiet undercount rather than an outage.
        # #VERIFY: tests/integration/test_notification_digest_rls.py::
        # test_digest_counts_tier1_backed_notifications.
        await apply_family_rls_context(session, family_id=family_id, is_admin=False)
        cursor = await _last_digest_at(session, family_id)
        since = cursor if cursor is not None else default_since
        items = await list_family_notifications(
            session, family_id, since=since, limit=_DIGEST_CANDIDATE_LIMIT
        )
        pending = sum(
            1 for item in items if item.severity == "info" and item.kind != "digest"
        )
        if pending == 0:
            continue
        await record_event(
            session,
            Actor.system(),
            entity_type=_DIGEST_ENTITY_TYPE,
            entity_id=str(family_id),
            event_type=EventType.NOTIFICATION_DIGEST_READY,
            payload={"digest_count": pending},
        )
        written += 1
    return written
