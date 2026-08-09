"""ADR-022 regression: the S9 digest must see Tier 1-backed notifications.

``notification-digest.yml`` deliberately connects as the least-privilege
``cyo_api`` role (the same role every other write path uses), not
``cyo_worker``. That means ``run_notification_digest`` is subject to the
Tier 1 ``family_scoped`` policy exactly like a normal request: without
setting ``app.family_id`` before reading ``story_request``, the fail-closed
policy filters every row and ``_resolve_story_request`` (notifications/
service.py) silently resolves nothing, dropping every request-backed
notification from every family's digest with no exception and no log.

This mirrors ``test_rls_tier1_enforcement.py``'s fixture pattern (a real
migrated database, connect as ``cyo_api``, never BYPASSRLS) rather than the
plain ``sessions``/``seed`` fixtures the rest of ``test_notification_digest.py``
uses, because those connect as the owner role and would never observe this
class of bug.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.db.models import ChildProfile, Family, PipelineEvent, StoryRequest
from cyo_adventure.events.models import Actor, EventType
from cyo_adventure.events.writer import record_event
from cyo_adventure.notifications.digest import run_notification_digest
from tests.integration._migration_utils import migrate_and_connect_as

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CYO_API_ROLE = "cyo_api"
_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _DigestRlsEnv:
    """A migrated database, seeded with one family's pending request, as ``cyo_api``."""

    sessions: async_sessionmaker[AsyncSession]
    family_id: uuid.UUID


@pytest_asyncio.fixture
async def digest_rls_env(pg_url: str) -> AsyncIterator[_DigestRlsEnv]:
    admin_url, role_url = await migrate_and_connect_as(
        pg_url, "notification_digest_rls", _CYO_API_ROLE
    )
    family_id = uuid.uuid4()

    admin_engine = create_async_engine(admin_url, poolclass=NullPool)
    admin_sessions = async_sessionmaker(admin_engine, expire_on_commit=False)
    try:
        async with admin_sessions() as session:
            session.add(Family(id=family_id, name="Digest RLS Family"))
            await session.flush()
            profile = ChildProfile(
                family_id=family_id, display_name="Reader", age_band="8-11"
            )
            session.add(profile)
            await session.flush()
            request = StoryRequest(
                family_id=family_id,
                profile_id=profile.id,
                request_text="A fox who learns to fly.",
                age_band="8-11",
            )
            session.add(request)
            await session.flush()
            await record_event(
                session,
                Actor.system(),
                entity_type="story_request",
                entity_id=str(request.id),
                event_type=EventType.REQUEST_CREATED,
                to_state=request.status,
                payload={"initiator_role": "child"},
            )
            await session.commit()
    finally:
        await admin_engine.dispose()

    api_engine = create_async_engine(role_url, poolclass=NullPool)
    api_sessions = async_sessionmaker(api_engine, expire_on_commit=False)
    try:
        yield _DigestRlsEnv(sessions=api_sessions, family_id=family_id)
    finally:
        await api_engine.dispose()


async def test_digest_counts_tier1_backed_notifications(
    digest_rls_env: _DigestRlsEnv,
) -> None:
    """A REQUEST_CREATED (child-initiated) notification must reach the digest.

    Without ``apply_family_rls_context`` inside ``run_notification_digest``'s
    per-family loop, the ``cyo_api``-connected read of ``story_request``
    returns zero rows regardless of which family is being processed, so
    ``_resolve_story_request`` never resolves the event's entity, the event
    is dropped, and no digest event is written at all -- this test would see
    zero events, not a wrong count, if the regression reappeared.
    """
    async with digest_rls_env.sessions() as session:
        written = await run_notification_digest(session, now=_NOW)
        await session.commit()
    assert written == 1

    async with digest_rls_env.sessions() as session:
        events = (
            await session.scalars(
                select(PipelineEvent).where(
                    PipelineEvent.entity_type == "family",
                    PipelineEvent.entity_id == str(digest_rls_env.family_id),
                    PipelineEvent.event_type == EventType.NOTIFICATION_DIGEST_READY,
                )
            )
        ).all()
    assert len(events) == 1
    assert events[0].payload == {"digest_count": 1}
