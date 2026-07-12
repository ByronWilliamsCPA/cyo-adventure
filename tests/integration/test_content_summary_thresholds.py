"""Threshold filtering on guardian content summary and books list."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    Family,
    ModerationThreshold,
    Storybook,
    StorybookVersion,
    User,
)

from .conftest import auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A report with one advisory (below default threshold) and one flag (at it).
_MIXED_REPORT: dict[str, object] = {
    "findings": [
        {
            "stage": 0,
            "source": "openai",
            "category": "toxicity",
            "node_id": None,
            "verdict": "advisory",
            "score": 0.02,
            "message": "graded classifier advisory",
        },
        {
            "stage": 1,
            "source": "llm_safety",
            "category": "safety",
            "node_id": None,
            "verdict": "flag",
            "score": None,
            "message": "mild peril",
        },
    ],
    "summary": {
        "count": 2,
        "hard_block": False,
        "soft_flag": True,
        "repaired": False,
        "reviewer_independent": True,
    },
}


async def _seed_banded_published(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed a family and a published 8-11 story carrying _MIXED_REPORT."""
    async with sessions() as session:
        fam = Family(name="T")
        session.add(fam)
        await session.flush()
        admin = User(
            family_id=fam.id, role="admin", authn_subject="admin-t", is_admin=True
        )
        session.add_all(
            [
                admin,
                User(family_id=fam.id, role="guardian", authn_subject="guardian-t"),
            ]
        )
        await session.flush()
        story_id = "threshold-me"
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
                moderation_report=_MIXED_REPORT,
                approved_by=admin.id,
                published_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return story_id


async def test_guardian_summary_hides_below_threshold_advisory(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Guardian sees the flag finding but not the 0.02 advisory."""
    story_id = await _seed_banded_published(sessions)
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/content-summary",
        headers=auth("guardian-t"),
    )
    assert res.status_code == 200
    body = res.json()
    categories = [f["category"] for f in body["findings"]]
    assert "safety" in categories
    assert "toxicity" not in categories
    assert body["flagged_count"] == 1


async def test_admin_review_surface_ignores_age_band_threshold_policy(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The admin review surface bypasses the per-band ThresholdPolicy entirely.

    Seeds a ('8-11', 'safety') override raising min_verdict to BLOCK. The
    ``safety`` finding is a FLAG (severity below BLOCK), so the override HIDES
    it for guardians. The admin surface must still SHOW it, proving admin does
    not apply ThresholdPolicy (and is not being gated like a guardian). The
    ``safety`` finding carries score ``None`` (unscored), so the admin noise
    floor is not a confound here: only the age-band-policy hypothesis explains
    the divergence.

    The 0.02 ADVISORY is hidden on the admin surface too, but by the separate
    WS-A admin noise-floor addendum (default floor 0.05), not by
    ThresholdPolicy; see tests/integration/test_review_surface_noise_floor.py.
    """
    story_id = await _seed_banded_published(sessions)
    async with sessions() as session:
        session.add(
            ModerationThreshold(
                age_band="8-11",
                category="safety",
                min_verdict="block",
                min_score=None,
            )
        )
        await session.commit()

    # Guardian: the override raises the safety threshold to BLOCK, so the
    # FLAG-level safety finding is hidden for the guardian.
    guardian_res = await client.get(
        f"/api/v1/storybooks/{story_id}/content-summary",
        headers=auth("guardian-t"),
    )
    assert guardian_res.status_code == 200
    guardian_categories = [f["category"] for f in guardian_res.json()["findings"]]
    assert "safety" not in guardian_categories

    # Admin: the same override does NOT gate the admin review surface, so the
    # safety FLAG still surfaces. Were the admin path wrongly gated by the
    # per-band policy (like a guardian), this assertion would fail.
    admin_res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-t"),
    )
    assert admin_res.status_code == 200
    admin_categories = [f["category"] for f in admin_res.json()["story_level_findings"]]
    assert "safety" in admin_categories
    assert "toxicity" not in admin_categories


async def test_threshold_row_lowers_floor_for_matching_band(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An override row ('8-11', 'toxicity') -> advisory surfaces the advisory."""
    story_id = await _seed_banded_published(sessions)
    async with sessions() as session:
        session.add(
            ModerationThreshold(
                age_band="8-11",
                category="toxicity",
                min_verdict="advisory",
                min_score=None,
            )
        )
        await session.commit()
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/content-summary",
        headers=auth("guardian-t"),
    )
    body = res.json()
    assert "toxicity" in [f["category"] for f in body["findings"]]
    assert body["flagged_count"] == 2
