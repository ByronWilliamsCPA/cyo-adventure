"""Integration tests for the WS-F moderation dashboard (loader + endpoints)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

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


async def _seed_malformed_rows(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Seed three malformed version shapes plus one valid moderated version.

    Covers three independent malformed-data boundaries the loader must
    survive: a ``findings`` value that is a bare string rather than a list,
    a ``moderation_report`` value that is not an object at all, and a
    ``blob`` whose ``metadata`` is not an object (so age_band extraction
    yields null). None of the three should crash either endpoint; only the
    valid version (``s_good``) contributes to insights/suggestions.
    """
    async with sessions() as session:
        session.add(
            Storybook(id="s_bad_findings", family_id=seed.family_id, status="in_review")
        )
        session.add(
            StorybookVersion(
                storybook_id="s_bad_findings",
                version=1,
                blob={"metadata": {"age_band": "8-11"}},
                moderation_report={"findings": "not-a-list"},
            )
        )
        session.add(
            Storybook(id="s_bad_report", family_id=seed.family_id, status="in_review")
        )
        session.add(
            StorybookVersion(
                storybook_id="s_bad_report",
                version=1,
                blob={"metadata": {"age_band": "8-11"}},
                moderation_report=cast("dict[str, object]", "not-a-report"),
            )
        )
        session.add(
            Storybook(id="s_bad_blob", family_id=seed.family_id, status="in_review")
        )
        session.add(
            StorybookVersion(
                storybook_id="s_bad_blob",
                version=1,
                blob={"metadata": "not-an-object"},
                moderation_report=_report(_finding("violence", "advisory")),
            )
        )
        await _seed_moderated_version(
            session,
            seed,
            storybook_id="s_good",
            findings=[_finding("violence", "advisory")],
            decision=EventType.RELEASED,
        )
        await session.commit()


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

    async def test_loader_attributes_decisions_across_a_storybooks_versions(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """Two moderated versions of one storybook, decided by two separate
        decision events on the shared storybook-level stream: each version
        attributes to the first decision at or after its own moderation
        completed, splitting the stream by time order.
        """
        storybook_id = "s_multi_version"
        t1 = _T0
        t2 = _T0 + timedelta(hours=1)
        t3 = _T0 + timedelta(hours=2)
        t4 = _T0 + timedelta(hours=3)

        async with sessions() as session:
            session.add(
                Storybook(id=storybook_id, family_id=seed.family_id, status="in_review")
            )
            session.add(
                StorybookVersion(
                    storybook_id=storybook_id,
                    version=1,
                    blob={"metadata": {"age_band": "8-11"}},
                    moderation_report=_report(_finding("violence", "advisory")),
                )
            )
            session.add(
                StorybookVersion(
                    storybook_id=storybook_id,
                    version=2,
                    blob={"metadata": {"age_band": "8-11"}},
                    moderation_report=_report(_finding("violence", "advisory")),
                )
            )
            session.add(
                _event(
                    entity_type="storybook_version",
                    entity_id=f"{storybook_id}:1",
                    event_type=EventType.MODERATION_COMPLETED,
                    occurred_at=t1,
                )
            )
            session.add(
                _event(
                    entity_type="storybook",
                    entity_id=storybook_id,
                    event_type=EventType.SENT_BACK,
                    occurred_at=t2,
                )
            )
            session.add(
                _event(
                    entity_type="storybook_version",
                    entity_id=f"{storybook_id}:2",
                    event_type=EventType.MODERATION_COMPLETED,
                    occurred_at=t3,
                )
            )
            session.add(
                _event(
                    entity_type="storybook",
                    entity_id=storybook_id,
                    event_type=EventType.RELEASED,
                    occurred_at=t4,
                )
            )
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        by_version = {
            record.version: record
            for record in records
            if record.storybook_id == storybook_id
        }
        assert by_version[1].outcome.decided is True
        assert by_version[1].outcome.released is False
        assert by_version[2].outcome.decided is True
        assert by_version[2].outcome.released is True

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

    async def test_dashboard_shows_recent_noise_floor_change(
        self, client: AsyncClient, seed: Seed
    ) -> None:
        put = await client.put(
            "/api/v1/admin/moderation/noise-floor",
            json={"value": 0.1},
            headers=auth(seed.admin_token),
        )
        assert put.status_code == 200

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        changes = res.json()["recent_changes"]
        assert changes, "expected the noise_floor_changed event to appear"
        assert changes[0]["event_type"] == "noise_floor_changed"
        assert changes[0]["entity_id"] == "admin_noise_floor"

    async def test_dashboard_empty_database_returns_200_with_empty_collections(
        self, client: AsyncClient, seed: Seed
    ) -> None:
        """No moderated versions and no threshold/noise-floor changes: the
        endpoint still returns 200 with empty collections rather than a
        404 or 500."""
        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        body = res.json()
        assert body["insights"] == []
        assert body["recent_changes"] == []

    async def test_recent_changes_excludes_non_threshold_events(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """A RELEASED pipeline event is not a threshold/noise-floor change;
        the event_type filter (a payload-exposure safety boundary, see the
        #CRITICAL marker on the query in moderation_dashboard.py) must keep
        it out of recent_changes."""
        async with sessions() as session:
            session.add(
                _event(
                    entity_type="storybook",
                    entity_id="s_released_event",
                    event_type=EventType.RELEASED,
                    occurred_at=_T0,
                )
            )
            await session.commit()

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        assert res.json()["recent_changes"] == []

    async def test_recent_changes_honors_limit_and_desc_order(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """25 seeded threshold_changed events, each with a distinct
        timestamp: only the newest 20 (_RECENT_CHANGES_LIMIT) come back,
        ordered newest-first."""
        async with sessions() as session:
            for index in range(25):
                session.add(
                    _event(
                        entity_type="moderation_threshold",
                        entity_id=f"8-11:violence:{index}",
                        event_type=EventType.THRESHOLD_CHANGED,
                        occurred_at=_T0 + timedelta(minutes=index),
                    )
                )
            await session.commit()

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        changes = res.json()["recent_changes"]
        assert len(changes) == 20
        occurred_ats = [change["occurred_at"] for change in changes]
        assert occurred_ats == sorted(occurred_ats, reverse=True)
        assert changes[0]["entity_id"] == "8-11:violence:24"
        assert changes[-1]["entity_id"] == "8-11:violence:5"

    async def test_dashboard_skips_malformed_moderation_rows(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """Malformed report/blob shapes never crash the endpoint; only the
        one valid moderated version contributes to insights."""
        await _seed_malformed_rows(sessions, seed)

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        rows = {
            (row["age_band"], row["category"]): row for row in res.json()["insights"]
        }
        assert ("8-11", "violence") in rows
        assert rows[("8-11", "violence")]["advisory_findings"] == 1


async def _seed_high_override_corpus(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Six released versions with a violence flag in band 8-11 (rate 1.0)."""
    async with sessions() as session:
        for index in range(6):
            await _seed_moderated_version(
                session,
                seed,
                storybook_id=f"s_corpus_{index}",
                findings=[_finding("violence", "flag")],
                decision=EventType.RELEASED,
                moderated_at=_T0 + timedelta(hours=index),
            )
        await session.commit()


class TestSuggestionsEndpoint:
    async def test_suggestion_appears_above_gates(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        await _seed_high_override_corpus(sessions, seed)

        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        body = res.json()
        assert body["min_decided_versions"] == 5
        assert body["min_override_rate"] == 0.8
        assert len(body["suggestions"]) == 1
        suggestion = body["suggestions"][0]
        assert suggestion["age_band"] == "8-11"
        assert suggestion["category"] == "violence"
        assert suggestion["current_min_verdict"] == "flag"
        assert suggestion["suggested_min_verdict"] == "block"
        assert suggestion["override_rate"] == 1.0
        assert suggestion["decided_versions"] == 6

    async def test_no_suggestion_below_volume(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_lone",
                findings=[_finding("violence", "flag")],
                decision=EventType.RELEASED,
            )
            await session.commit()

        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        assert res.json()["suggestions"] == []

    async def test_applying_a_suggestion_retires_it(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """The F3 ratify loop: apply via the WS-A PUT, suggestion disappears."""
        await _seed_high_override_corpus(sessions, seed)

        put = await client.put(
            "/api/v1/admin/moderation-thresholds/8-11",
            params={"category": "violence"},
            json={"min_verdict": "block", "min_score": None},
            headers=auth(seed.admin_token),
        )
        assert put.status_code == 200

        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        assert res.json()["suggestions"] == []

    async def test_guardian_gets_403(self, client: AsyncClient, seed: Seed) -> None:
        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.guardian_token)
        )
        assert res.status_code == 403

    async def test_suggestions_empty_database_returns_200_with_empty_list(
        self, client: AsyncClient, seed: Seed
    ) -> None:
        """No moderated versions at all: the endpoint still returns 200
        with an empty suggestions list rather than a 404 or 500."""
        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        assert res.json()["suggestions"] == []

    async def test_suggestions_skips_malformed_moderation_rows(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """Malformed report/blob shapes never crash the endpoint; the one
        valid moderated version is below the volume gate, so no suggestion
        is produced but the response is still 200."""
        await _seed_malformed_rows(sessions, seed)

        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        assert res.json()["suggestions"] == []
