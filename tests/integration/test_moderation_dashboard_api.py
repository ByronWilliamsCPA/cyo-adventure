"""Integration tests for the WS-F moderation dashboard (loader + endpoints)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import PipelineEvent, Storybook, StorybookVersion
from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import load_version_records
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _report(*findings: dict[str, object]) -> dict[str, object]:
    return {
        "findings": list(findings),
        "summary": {
            "count": len(findings),
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


def _finding(category: str, verdict: str) -> dict[str, object]:
    return {
        "stage": 1,
        "source": "openai",
        "category": category,
        "node_id": None,
        "verdict": verdict,
        "score": 0.4,
        "message": "graded signal",
    }


def _event(
    *,
    entity_type: str,
    entity_id: str,
    event_type: EventType,
    occurred_at: datetime,
) -> PipelineEvent:
    return PipelineEvent(
        id=uuid.uuid4(),
        occurred_at=occurred_at,
        actor_id=None,
        actor_role="system",
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type.value,
        payload={},
    )


async def _seed_moderated_version(
    session: AsyncSession,
    seed: Seed,
    *,
    storybook_id: str,
    age_band: str = "8-11",
    findings: list[dict[str, object]],
    decision: EventType | None,
    moderated_at: datetime = _T0,
) -> None:
    """Insert one storybook version with a report and its event trail."""
    session.add(
        Storybook(id=storybook_id, family_id=seed.family_id, status="in_review")
    )
    session.add(
        StorybookVersion(
            storybook_id=storybook_id,
            version=1,
            blob={"metadata": {"age_band": age_band}},
            moderation_report=_report(*findings),
        )
    )
    session.add(
        _event(
            entity_type="storybook_version",
            entity_id=f"{storybook_id}:1",
            event_type=EventType.MODERATION_COMPLETED,
            occurred_at=moderated_at,
        )
    )
    if decision is not None:
        session.add(
            _event(
                entity_type="storybook",
                entity_id=storybook_id,
                event_type=decision,
                occurred_at=moderated_at + timedelta(minutes=5),
            )
        )


class TestLoadVersionRecords:
    async def test_loader_builds_records_with_outcomes(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_released",
                findings=[_finding("violence", "advisory")],
                decision=EventType.RELEASED,
            )
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_sent_back",
                findings=[_finding("violence", "flag")],
                decision=EventType.SENT_BACK,
            )
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_pending",
                findings=[_finding("violence", "advisory")],
                decision=None,
            )
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        by_id = {record.storybook_id: record for record in records}
        assert by_id["s_released"].outcome.decided is True
        assert by_id["s_released"].outcome.released is True
        assert by_id["s_released"].age_band == "8-11"
        assert by_id["s_released"].moderated_at == _T0
        assert by_id["s_sent_back"].outcome.decided is True
        assert by_id["s_sent_back"].outcome.released is False
        assert by_id["s_pending"].outcome.decided is False

    async def test_loader_skips_versions_without_band(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            session.add(
                Storybook(id="s_no_band", family_id=seed.family_id, status="in_review")
            )
            session.add(
                StorybookVersion(
                    storybook_id="s_no_band",
                    version=1,
                    blob={"metadata": {}},
                    moderation_report=_report(_finding("violence", "advisory")),
                )
            )
            session.add(
                Storybook(
                    id="s_empty_band", family_id=seed.family_id, status="in_review"
                )
            )
            session.add(
                StorybookVersion(
                    storybook_id="s_empty_band",
                    version=1,
                    blob={"metadata": {"age_band": ""}},
                    moderation_report=_report(_finding("violence", "advisory")),
                )
            )
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        assert all(
            record.storybook_id not in {"s_no_band", "s_empty_band"}
            for record in records
        )

    async def test_loader_falls_back_to_approved_by_without_decision_event(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """A version with ``approved_by`` set but no ``released``/``sent_back``
        event still resolves to a decided+released outcome (the loader-level
        approved_by fallback in ``attribute_outcome``, for pre-WS-D history).
        """
        async with sessions() as session:
            session.add(
                Storybook(
                    id="s_approved_only", family_id=seed.family_id, status="in_review"
                )
            )
            session.add(
                StorybookVersion(
                    storybook_id="s_approved_only",
                    version=1,
                    blob={"metadata": {"age_band": "8-11"}},
                    moderation_report=_report(_finding("violence", "advisory")),
                    approved_by=seed.admin_user_id,
                )
            )
            session.add(
                _event(
                    entity_type="storybook_version",
                    entity_id="s_approved_only:1",
                    event_type=EventType.MODERATION_COMPLETED,
                    occurred_at=_T0,
                )
            )
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        by_id = {record.storybook_id: record for record in records}
        assert by_id["s_approved_only"].outcome.decided is True
        assert by_id["s_approved_only"].outcome.released is True

    async def test_loader_falls_back_to_created_at_without_moderation_event(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """A version with no ``moderation_completed`` event falls back to the
        version row's own ``created_at`` for ``moderated_at``.
        """
        async with sessions() as session:
            session.add(
                Storybook(id="s_no_event", family_id=seed.family_id, status="in_review")
            )
            version_row = StorybookVersion(
                storybook_id="s_no_event",
                version=1,
                blob={"metadata": {"age_band": "8-11"}},
                moderation_report=_report(_finding("violence", "advisory")),
            )
            session.add(version_row)
            await session.flush()
            expected_created_at = version_row.created_at
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        by_id = {record.storybook_id: record for record in records}
        assert by_id["s_no_event"].moderated_at == expected_created_at

    async def test_loader_skips_malformed_moderation_event_entity_ids(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """Malformed ``moderation_completed`` entity ids (no colon, or a
        non-numeric version suffix) never crash the loader; the affected
        version falls back to ``created_at`` while a valid id seeded alongside
        it still resolves normally.
        """
        async with sessions() as session:
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_valid_alongside",
                findings=[_finding("violence", "advisory")],
                decision=EventType.RELEASED,
            )
            session.add(
                Storybook(
                    id="s_malformed", family_id=seed.family_id, status="in_review"
                )
            )
            version_row = StorybookVersion(
                storybook_id="s_malformed",
                version=1,
                blob={"metadata": {"age_band": "8-11"}},
                moderation_report=_report(_finding("violence", "advisory")),
            )
            session.add(version_row)
            session.add(
                _event(
                    entity_type="storybook_version",
                    entity_id="no-colon-id",
                    event_type=EventType.MODERATION_COMPLETED,
                    occurred_at=_T0,
                )
            )
            session.add(
                _event(
                    entity_type="storybook_version",
                    entity_id="sid:notanumber",
                    event_type=EventType.MODERATION_COMPLETED,
                    occurred_at=_T0,
                )
            )
            await session.flush()
            expected_created_at = version_row.created_at
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        by_id = {record.storybook_id: record for record in records}
        assert by_id["s_malformed"].moderated_at == expected_created_at
        assert by_id["s_valid_alongside"].moderated_at == _T0


class TestDashboardEndpoint:
    async def test_dashboard_aggregates_override_rate(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_released",
                findings=[_finding("violence", "advisory")],
                decision=EventType.RELEASED,
            )
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_sent_back",
                findings=[_finding("violence", "flag")],
                decision=EventType.SENT_BACK,
            )
            await session.commit()

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        body = res.json()
        rows = {(row["age_band"], row["category"]): row for row in body["insights"]}
        row = rows[("8-11", "violence")]
        assert row["advisory_findings"] == 1
        assert row["flag_findings"] == 1
        assert row["decided_versions"] == 2
        assert row["released_versions"] == 1
        assert row["override_rate"] == 0.5
        assert body["recent_changes"] == []

    async def test_dashboard_shows_recent_threshold_changes(
        self,
        client: AsyncClient,
        seed: Seed,
    ) -> None:
        put = await client.put(
            "/api/v1/admin/moderation-thresholds/8-11",
            params={"category": "violence"},
            json={"min_verdict": "block", "min_score": None},
            headers=auth(seed.admin_token),
        )
        assert put.status_code == 200

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        changes = res.json()["recent_changes"]
        assert changes, "expected the threshold_changed event to appear"
        assert changes[0]["event_type"] == "threshold_changed"
        assert changes[0]["entity_id"] == "8-11"

    async def test_guardian_gets_403(self, client: AsyncClient, seed: Seed) -> None:
        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.guardian_token)
        )
        assert res.status_code == 403
