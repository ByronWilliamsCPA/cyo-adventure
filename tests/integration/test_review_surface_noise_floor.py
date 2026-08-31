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
        admin = User(
            family_id=fam.id, role="admin", authn_subject="admin-nf", is_admin=True
        )
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
        admin = User(
            family_id=fam.id,
            role="admin",
            authn_subject="admin-nf-queue",
            is_admin=True,
        )
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
    # The summary block is the pipeline's persisted gate record and is
    # deliberately NOT floored: it must keep reporting the raw count (3) and
    # gate booleans even while flagged_count is denoised. A regression that
    # floored (or dropped) the summary would silently change what the console
    # gates on.
    assert item["summary"] == {
        "count": 3,
        "hard_block": True,
        "soft_flag": True,
        "repaired": False,
        "reviewer_independent": True,
    }


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


# ---------------------------------------------------------------------------
# `RS-B3`: a seeded moderation_threshold row makes the admin floor band-aware.
#
# These cases are what prove the wiring is real rather than plausible: the
# band comes off the stored blob's metadata and the floor comes out of the
# database, so a break anywhere between the router and admin_surfaces (a
# dropped age_band, an unloaded policy) shows up here as a finding that stops
# being hidden or starts being hidden.
# ---------------------------------------------------------------------------


async def _seed_threshold_row(
    sessions: async_sessionmaker[AsyncSession],
    *,
    age_band: str,
    category: str,
    min_score: float | None,
) -> None:
    """Seed one moderation_threshold override row."""
    async with sessions() as session:
        session.add(
            ModerationThreshold(
                age_band=age_band,
                category=category,
                min_verdict="flag",
                min_score=min_score,
            )
        )
        await session.commit()


async def test_a_band_row_hides_an_advisory_the_flat_floor_would_show(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A 0.5 row on (8-11, engagement) hides the 0.09 advisory (`RS-B3`).

    Without the row that advisory clears the 0.05 flat floor and surfaces (see
    test_admin_review_shows_advisory_above_default_floor above), so the change
    in visibility is attributable to the row and nothing else.
    """
    story_id = await _seed_published_with_noisy_report(sessions)
    await _seed_threshold_row(
        sessions, age_band="8-11", category="engagement", min_score=0.5
    )
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["story_level_findings"]]
    assert "engagement" not in categories
    # The BLOCK is still there: no row can hide a bright-line finding.
    assert "safety" in categories


async def test_a_band_row_can_reveal_an_advisory_the_flat_floor_hides(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A 0.001 row on (8-11, toxicity) reveals the 0.02 advisory (`RS-B3`).

    The band row replaces the flat floor rather than being combined with it,
    which is what lets a younger band be tuned to see MORE than the global
    floor allows. This is the direction that matters for recall.
    """
    story_id = await _seed_published_with_noisy_report(sessions)
    await _seed_threshold_row(
        sessions, age_band="8-11", category="toxicity", min_score=0.001
    )
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["story_level_findings"]]
    assert "toxicity" in categories


async def test_a_row_for_another_band_leaves_this_story_alone(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A row on 3-5 does not denoise an 8-11 story (`RS-B3`).

    If ``age_band`` were dropped anywhere on the way to the resolver, the
    surface would fall back to the empty-string band, every row would miss,
    and this test would keep passing while its sibling above failed. Both
    directions are asserted for exactly that reason.
    """
    story_id = await _seed_published_with_noisy_report(sessions)
    await _seed_threshold_row(
        sessions, age_band="3-5", category="engagement", min_score=0.5
    )
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["story_level_findings"]]
    assert "engagement" in categories


async def test_a_row_with_a_null_min_score_leaves_the_flat_floor_in_place(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A verdict-only row is not a score override (`RS-B3`).

    ``min_verdict`` rows are the table's original purpose. A row that carries
    no ``min_score`` must leave the admin floor exactly where it was, and must
    NOT drag ``min_verdict=flag`` into the admin lane (which would hide the
    above-floor advisory too).
    """
    story_id = await _seed_published_with_noisy_report(sessions)
    await _seed_threshold_row(
        sessions, age_band="8-11", category="engagement", min_score=None
    )
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["story_level_findings"]]
    assert "engagement" in categories
    assert "toxicity" not in categories


async def test_a_band_row_does_not_reach_the_guardian_content_summary(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The guardian lane still resolves through ThresholdPolicy.surfaces.

    `RS-B3` touched the admin lane only. Seeding a permissive score row must
    not widen what a guardian sees, because the guardian gate is the verdict
    (``min_verdict``), and this row's verdict is still ``flag``.
    """
    story_id = await _seed_published_with_noisy_report(sessions)
    await _seed_threshold_row(
        sessions, age_band="8-11", category="toxicity", min_score=0.001
    )
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/content-summary",
        headers=auth("guardian-nf"),
    )
    assert res.status_code == 200
    categories = [f["category"] for f in res.json()["findings"]]
    assert categories == ["safety"]
