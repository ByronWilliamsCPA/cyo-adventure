"""Integration tests for the WS-F moderation dashboard (loader + endpoints)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import PipelineEvent, Storybook, StorybookVersion
from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import load_version_records

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.integration.conftest import Seed

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
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        assert all(record.storybook_id != "s_no_band" for record in records)
