"""WS-A admin noise-floor addendum (Task A2): admin review surface filtering.

Exercises the admin review endpoint end to end. The default noise floor
(0.05, ``ADMIN_NOISE_FLOOR_DEFAULT``) applies since no ``moderation_setting``
row is seeded and the test schema is built from ORM metadata, matching
``load_admin_noise_floor``'s documented fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Family, Storybook, StorybookVersion, User

from .conftest import auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# One advisory below the default floor (hidden), one advisory above it (shown),
# and a bright-line BLOCK carrying score 0.0 (always shown, safety-critical).
_NOISY_REPORT: dict[str, object] = {
    "findings": [
        {
            "stage": 0,
            "source": "openai",
            "category": "toxicity",
            "node_id": None,
            "verdict": "advisory",
            "score": 0.02,
            "message": "near-zero advisory noise",
        },
        {
            "stage": 0,
            "source": "openai",
            "category": "engagement",
            "node_id": None,
            "verdict": "advisory",
            "score": 0.09,
            "message": "real advisory signal",
        },
        {
            "stage": 1,
            "source": "llm_safety",
            "category": "safety",
            "node_id": None,
            "verdict": "block",
            "score": 0.0,
            "message": "bright-line block",
        },
    ],
    "summary": {
        "count": 3,
        "hard_block": True,
        "soft_flag": True,
        "repaired": False,
        "reviewer_independent": True,
    },
}


async def _seed_published_with_noisy_report(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed a family and a published story carrying ``_NOISY_REPORT``."""
    async with sessions() as session:
        fam = Family(name="NoiseFloorFamily")
        session.add(fam)
        await session.flush()
        admin = User(family_id=fam.id, role="admin", authn_subject="admin-nf")
        session.add_all(
            [
                admin,
                User(family_id=fam.id, role="guardian", authn_subject="guardian-nf"),
            ]
        )
        await session.flush()
        story_id = "noise-floor-story"
        session.add(
            Storybook(
                id=story_id,
                family_id=fam.id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={
                    "id": story_id,
                    "metadata": {"age_band": "8-11"},
                    "nodes": [{"id": "n1", "body": "Prose."}],
                },
                moderation_report=_NOISY_REPORT,
                approved_by=admin.id,
                published_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return story_id


async def test_admin_review_hides_advisory_below_default_floor(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A 0.02 advisory is hidden from the admin review surface at floor 0.05."""
    story_id = await _seed_published_with_noisy_report(sessions)
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["story_level_findings"]]
    assert "toxicity" not in categories


async def test_admin_review_shows_advisory_above_default_floor(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A 0.09 advisory still surfaces since it clears the 0.05 floor."""
    story_id = await _seed_published_with_noisy_report(sessions)
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["story_level_findings"]]
    assert "engagement" in categories


async def test_admin_review_never_hides_bright_line_block(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A BLOCK finding carrying score 0.0 always surfaces (safety-critical)."""
    story_id = await _seed_published_with_noisy_report(sessions)
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["story_level_findings"]]
    assert "safety" in categories


async def _seed_in_review_with_noisy_report(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed a family and an ``in_review`` story carrying ``_NOISY_REPORT``."""
    async with sessions() as session:
        fam = Family(name="NoiseFloorQueueFamily")
        session.add(fam)
        await session.flush()
        admin = User(family_id=fam.id, role="admin", authn_subject="admin-nf-queue")
        session.add(admin)
        await session.flush()
        story_id = "noise-floor-queue-story"
        session.add(Storybook(id=story_id, family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={
                    "id": story_id,
                    "title": "Queue Story",
                    "metadata": {"age_band": "8-11"},
                    "nodes": [{"id": "n1", "body": "Prose."}],
                },
                moderation_report=_NOISY_REPORT,
            )
        )
        await session.commit()
        return story_id


async def test_review_queue_flagged_count_respects_admin_noise_floor(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The queue's flagged_count is denoised exactly like the detail view.

    The near-zero (0.02) toxicity advisory is hidden by the 0.05 default
    floor; the above-floor (0.09) advisory and the bright-line BLOCK both
    still count, so the badge the console shows matches what the floored
    detail view will render.
    """
    story_id = await _seed_in_review_with_noisy_report(sessions)
    res = await client.get("/api/v1/review-queue", headers=auth("admin-nf-queue"))
    assert res.status_code == 200
    items = {item["storybook_id"]: item for item in res.json()["items"]}
    item = items[story_id]
    assert item["screened"] is True
    assert item["flagged_count"] == 2


async def test_guardian_content_summary_unaffected_by_admin_noise_floor(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The guardian content summary is untouched: ThresholdPolicy gates it, not
    the admin noise floor. Both advisories are already hidden by the default
    min_verdict=FLAG policy; only the BLOCK finding surfaces.
    """
    story_id = await _seed_published_with_noisy_report(sessions)
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/content-summary",
        headers=auth("guardian-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["findings"]]
    assert categories == ["safety"]
