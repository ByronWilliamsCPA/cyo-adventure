"""ADR-022 regression: the digest job must apply Tier 1 RLS context per family.

``notifications/digest.py::run_notification_digest`` runs with no ``Principal``
(it is scheduled infrastructure, not a request handler), yet it calls
``notifications/service.py::list_family_notifications``, whose entity
resolvers read Tier 1 ``family_scoped`` tables (``story_request``,
``child_profile``) for the least-privilege ``cyo_api`` role. Without the
``app.family_id`` GUC those Tier 1 reads return zero rows fail-closed, so
``_resolve_story_request`` never finds the request row, the event's
``EntityContext`` never resolves, and ``service.py``'s "ctx is None"
fail-safe drops the notification silently: no exception, no log, just an
undercounted digest. The fix is one line inside the digest job's per-family
loop (``await apply_family_rls_context(session, family_id=family_id,
is_admin=False)``); this test is the regression pin for that line.

Real-migration schema, not ORM ``create_all``: the ADR-022 policies live in
``supabase/migrations``, never in ``Base.metadata``, so the ordinary
``engine``/``sessions`` fixtures in ``conftest.py`` connect as the container
superuser (implicit BYPASSRLS) and could never make this bug reproduce --
see that file's "ADR-021/ADR-022 RLS-enforcement harness note". This test
instead builds a fully migrated database and connects as the real
``cyo_api`` role via ``_migration_utils.migrate_and_connect_as``, the same
helper ``test_rls_tier1_enforcement.py`` and ``test_rls_service_roles.py``
use.
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

# ADR-021 least-privilege role the digest job actually connects as in
# production; the Tier 1 policies this test pins are role-scoped, so any
# other NOBYPASSRLS role would match no policy and prove nothing.
_CYO_API_ROLE = "cyo_api"

# A fixed instant so the digest job's "no prior cursor -> 24h lookback"
# first-run default always covers the single event this test seeds.
_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _DigestRlsEnv:
    """A migrated database seeded with one real family's approved request.

    ``family_id`` is a real (non-catalog) family so it survives
    ``digest.py::_real_family_ids``'s ``Family.id != CATALOG_FAMILY_ID``
    filter and actually reaches the per-family RLS-context loop under test.
    """

    sessions: async_sessionmaker[AsyncSession]
    family_id: uuid.UUID


@pytest_asyncio.fixture
async def digest_rls_env(pg_url: str) -> AsyncIterator[_DigestRlsEnv]:
    """Build a migrated DB, seed one family's approved request, yield a ``cyo_api`` factory.

    Baseline rows (family, child profile, story request, and the
    ``REQUEST_APPROVED`` event) are seeded through the RLS-bypassing owner
    connection, mirroring ``tier1_env`` in ``test_rls_tier1_enforcement.py``,
    so they exist regardless of any policy. The test itself then reads and
    writes through the NOBYPASSRLS ``cyo_api`` connection this fixture
    yields, where the Tier 1 ``family_scoped`` policy on ``story_request``
    is what decides whether ``run_notification_digest`` can see the request
    at all.
    """
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
                request_text="a dragon who learns to share",
                age_band="8-11",
            )
            session.add(request)
            await session.flush()
            # REQUEST_APPROVED composes to an info-severity, non-digest
            # notification with no payload preconditions (registry.py's
            # _compose_request_approved always returns one), which is
            # exactly what run_notification_digest counts.
            await record_event(
                session,
                Actor.system(),
                entity_type="story_request",
                entity_id=str(request.id),
                event_type=EventType.REQUEST_APPROVED,
                payload={},
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


async def test_digest_counts_story_request_notifications_under_cyo_api(
    digest_rls_env: _DigestRlsEnv,
) -> None:
    """The digest job must count a real family's story-request notification.

    Runs ``run_notification_digest`` on a session authenticated as the real
    ``cyo_api`` role against a fully migrated schema, so the Tier 1
    ``family_scoped`` policy on ``story_request`` is live. Without
    ``digest.py``'s ``apply_family_rls_context`` call, the resolver's read of
    ``story_request`` returns zero rows (fail-closed, no ``app.family_id``
    set), the event's family never resolves, and ``service.py`` drops it
    silently: ``written`` would be 0 and no
    ``NOTIFICATION_DIGEST_READY`` event would exist. With the fix, the
    request resolves, the notification is counted, and both the return
    value and the written event must reflect exactly one pending item.
    """
    async with digest_rls_env.sessions() as session:
        written = await run_notification_digest(session, now=_NOW)
        await session.commit()
    assert written == 1

    async with digest_rls_env.sessions() as session:
        event = (
            await session.scalars(
                select(PipelineEvent).where(
                    PipelineEvent.entity_type == "family",
                    PipelineEvent.entity_id == str(digest_rls_env.family_id),
                    PipelineEvent.event_type == EventType.NOTIFICATION_DIGEST_READY,
                )
            )
        ).one()
    assert event.payload == {"digest_count": 1}
