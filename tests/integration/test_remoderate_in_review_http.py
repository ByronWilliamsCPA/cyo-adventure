"""Integration proof that re-moderation admits an ``in_review`` book intact.

The unit suite pins each half of this change in isolation: that
``REMODERATABLE_STATUSES`` admits ``in_review``, that the slot contract is
resolved from the VERSION on that arm, and that the terminal
``StateTransitionError`` is swallowed. None of those can answer the question
the whole design turns on, because answering it needs the real route, the
real status machinery, a real database row, and the real skeleton catalog on
disk at once:

    does an ``in_review`` book survive a re-moderation unchanged in status,
    with a refreshed report, and WITHOUT a manufactured sentinel finding?

The fixture is built to DISCRIMINATE rather than to pass. Its version carries
``skeleton_slug="the-midnight-museum"``, the only slug in the production
catalog whose contract sidecar declares a personalizable slot (``HERO``), and
its blob carries a matching ``{~HERO:...~}`` sentinel in a node body. It has
no ``generation_job`` row, which is the shape 17 of 17 production ``in_review``
books have. Route the contract lookup through the story instead of the
version and the declared set collapses to empty, every sentinel in the blob
reads as ``unknown_slot``, and
``moderation/pipeline.py`` turns that into a BLOCK finding: the assertions
below fail. A sentinel-free blob, or any other slug, would pass either way and
prove nothing.

The sentinel sits in a node BODY, never the title: a sentinel in the title is
an ``in_title`` violation regardless of what a story declares
(``validator/sentinel_integrity.py``), so a title placement would fail on a
rule unrelated to the contract under test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, create_autospec

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.moderation.classifiers import run_classifiers as _real_classifiers
from cyo_adventure.moderation.stages import (
    run_coherence_stage as _real_coherence,
)
from cyo_adventure.moderation.stages import (
    run_engagement_stage as _real_engagement,
)
from cyo_adventure.moderation.stages import (
    run_safety_stage as _real_safety,
)
from cyo_adventure.storybook.sentinels import wrap

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_STORY_ID = "remod-in-review-museum"
_VERSION = 1
_SLUG = "the-midnight-museum"
_TOKEN = wrap("HERO", "Explorer")
_STALE = "stale-marker-that-must-not-survive"

_LANTERN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)


def _sentinel_bearing_blob() -> dict[str, object]:
    """Return a real valid storybook whose first node body carries a sentinel.

    A real fixture rather than a minimal hand-built dict: this blob is parsed
    by ``StoryModel.model_validate`` inside the pipeline and re-gated twice by
    ``run_fill_gate``, so a schema-light stand-in would hard-block on its own
    invalidity and mask whatever the sentinel check actually said.
    """
    blob: dict[str, object] = json.loads(_LANTERN.read_text(encoding="utf-8"))
    nodes = blob["nodes"]
    assert isinstance(nodes, list)
    first = nodes[0]
    assert isinstance(first, dict)
    first["body"] = f"{_TOKEN} lifted the lantern. {first['body']}"
    return blob


@pytest.fixture
def clean_llm_stages(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub the pipeline's four LLM seams clean, leaving everything else real.

    Stubbing is load-bearing, not convenience. The settings-level mock review
    backend returns ``"{}"`` bodies, which fail-safe to FLAG on every node; a
    soft flag on the ``in_review`` arm ENABLES auto-repair, and an adopted
    repair replaces ``version_row.blob`` wholesale with the canned story. That
    would delete the very sentinel this test exists to prove was tolerated,
    and the assertions would then pass for the wrong reason.

    Each stub is built with ``create_autospec`` (testing standard section 4.2)
    so a signature drift in the pipeline's calls fails here loudly rather than
    passing silently; a bare ``AsyncMock(spec=fn)`` constrains attribute
    access only and would not catch it.

    Returns:
        The safety-stage stub, so the test can assert the pipeline actually
        REACHED the LLM stages. ``_run_all_stages`` returns immediately after
        the classifiers when the report already carries a hard block, so an
        un-awaited safety stage is a precise signal that something blocked the
        run at moderation entry.
    """
    safety = create_autospec(_real_safety, return_value=[])
    monkeypatch.setattr(
        pipeline_mod,
        "run_classifiers",
        create_autospec(_real_classifiers, return_value=[]),
    )
    monkeypatch.setattr(pipeline_mod, "run_safety_stage", safety)
    for name, real in (
        ("run_coherence_stage", _real_coherence),
        ("run_engagement_stage", _real_engagement),
    ):
        monkeypatch.setattr(pipeline_mod, name, create_autospec(real, return_value=[]))
    return safety


async def test_in_review_book_remoderates_without_a_manufactured_sentinel_block(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    clean_llm_stages: AsyncMock,
) -> None:
    """An in_review, job-less, sentinel-bearing book survives re-moderation."""
    async with sessions() as session:
        session.add(
            Storybook(
                id=_STORY_ID,
                family_id=seed.family_id,
                status="in_review",
                current_published_version=None,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=_STORY_ID,
                version=_VERSION,
                blob=_sentinel_bearing_blob(),
                # The provenance an offline cyo-author import leaves behind:
                # a skeleton slug, the "import" provider sentinel, and no
                # generation_job row anywhere.
                skeleton_slug=_SLUG,
                provider="import",
                # Both reports carry a marker no fresh derivation can produce,
                # so "refreshed" is proven by the marker's absence rather than
                # by a shape that a no-op would also satisfy.
                validation_report={"context": _STALE, "findings": []},
                moderation_report={"findings": [], "summary": {"note": _STALE}},
            )
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/admin/remoderate/{_STORY_ID}/{_VERSION}",
        headers=auth(seed.admin_token),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The endpoint reports the book's status AFTER the run. ADR-005 reserves
    # every status change for a human, and both terminal transitions the
    # pipeline attempts from IN_REVIEW are illegal, so the swallow must leave
    # the book exactly where the reviewer left it.
    assert body["status"] == "in_review"
    # No manufactured coverage gap: this field is derived from the findings'
    # fail-safe concerns, so a sentinel-driven run that fell back to
    # "reviewer_unavailable" would show up here. It is asserted at the wire
    # rather than the row because the endpoint derives it independently, and an
    # earlier revision derived it from the APPROVAL predicate, which reported
    # incomplete coverage for the mock reviewer this suite runs under while the
    # row it had just written said the opposite.
    assert body["coverage_complete"] is True
    # ``overall_verdict`` is deliberately NOT asserted here. Under test
    # settings the review backend is the mock, so run_moderation_pipeline
    # stamps the report ``reviewer_independent: False`` and the endpoint
    # derives "block" from that stamp alone: correct behavior (a substituted
    # reviewer must never report success, the 2026-07-21 incident) and
    # orthogonal to the slot contract under test. The hard-block question this
    # assertion used to stand in for is asked precisely against the stored
    # summary below, where the stamp cannot confound it.
    # The review stages ran at all. A hard block recorded at moderation ENTRY
    # short-circuits ``_run_all_stages`` right after the classifiers, so this
    # fails on the entry sentinel block independently of the report contents.
    clean_llm_stages.assert_awaited_once()

    async with sessions() as session:
        storybook = await session.get(Storybook, _STORY_ID)
        assert storybook is not None
        assert storybook.status == "in_review"

        version_row = (
            await session.execute(
                select(StorybookVersion).where(
                    StorybookVersion.storybook_id == _STORY_ID,
                    StorybookVersion.version == _VERSION,
                )
            )
        ).scalar_one()

        moderation_report = version_row.moderation_report
        assert moderation_report is not None
        assert _STALE not in json.dumps(moderation_report)
        # The precise form of the old wire-verdict assertion: a manufactured
        # sentinel finding is a hard block, and so is any other block this run
        # could have produced, but the mock-reviewer stamp is not.
        summary = moderation_report["summary"]
        assert isinstance(summary, dict)
        assert summary["hard_block"] is False
        findings = moderation_report["findings"]
        assert isinstance(findings, list)
        categories = [f["category"] for f in findings if isinstance(f, dict)]
        assert "sentinel_integrity_violation" not in categories

        validation_report = version_row.validation_report
        assert validation_report is not None
        assert _STALE not in json.dumps(validation_report)

        # The blob is untouched: nothing on this path rewrote the prose, so
        # the sentinel that drove the whole test is still where it was put.
        blob_nodes = version_row.blob["nodes"]
        assert isinstance(blob_nodes, list)
        assert _TOKEN in str(blob_nodes[0]["body"])
