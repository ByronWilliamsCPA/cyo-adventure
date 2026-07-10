"""Integration tests for race-safe book_index assignment (WS-B PR 3, Task 6).

Exercises ``cyo_adventure.generation.series_link`` against a real Postgres
unique constraint (``uq_storybook_series_book_index``). The retry test is the
concurrency test the spec mandates: it simulates a racing stale read
deterministically (monkeypatching only the module-level ``_next_index``
helper for its first call), while the IntegrityError raised, the savepoint
rollback, and the retry's recovery are all real, not mocked.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.db.models import (
    Concept,
    Family,
    Series,
    Storybook,
    StorybookVersion,
    StoryRequest,
    User,
)
from cyo_adventure.generation import series_link
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import _CANNED_STORY
from cyo_adventure.generation.series_link import (
    assign_book_index,
    embed_series_block,
    link_series_position,
)
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.moderation.report import Finding, Source, Verdict

from ._series_utils import seed_published_anchor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_family_and_user(session: AsyncSession) -> tuple[Family, User]:
    """Seed a bare family and guardian user for series-link tests."""
    family = Family(name="Fam")
    session.add(family)
    await session.flush()
    user = User(family_id=family.id, role="guardian", authn_subject="g")
    session.add(user)
    await session.flush()
    return family, user


async def _bare_storybook(session: AsyncSession, *, family_id: uuid.UUID) -> Storybook:
    """Create an unindexed draft storybook row for assignment tests."""
    storybook = Storybook(
        id=f"s_{uuid.uuid4().hex[:12]}", family_id=family_id, status="draft"
    )
    session.add(storybook)
    await session.flush()
    return storybook


async def test_sequential_assignment_is_contiguous(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Two successive assignments against a fresh series land at 1 then 2."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=True,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()

        book_one = await _bare_storybook(session, family_id=family.id)
        book_two = await _bare_storybook(session, family_id=family.id)

        index_one = await assign_book_index(
            session, story_id=book_one.id, series_id=series.id
        )
        index_two = await assign_book_index(
            session, story_id=book_two.id, series_id=series.id
        )
        assert index_one == 1
        assert index_two == 2

        book_one_id = book_one.id
        book_two_id = book_two.id
        await session.commit()

    async with sessions() as session:
        refreshed_one = await session.get(Storybook, book_one_id)
        refreshed_two = await session.get(Storybook, book_two_id)
        assert refreshed_one is not None
        assert refreshed_two is not None
        assert refreshed_one.series_id == series.id
        assert refreshed_one.book_index == 1
        assert refreshed_two.series_id == series.id
        assert refreshed_two.book_index == 2


async def test_retry_recovers_from_stale_read(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale ``_next_index`` read collides for real, and the retry recovers."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        series, _anchor = await seed_published_anchor(
            session, family_id=family.id, approved_by=user.id, book_index=1
        )
        await session.commit()
        series_id = series.id

    async with sessions() as session:
        new_book = await _bare_storybook(session, family_id=family.id)
        await session.commit()

        real_next_index = series_link._next_index
        calls = {"n": 0}

        async def stale_once(session: AsyncSession, series_id: uuid.UUID) -> int:
            calls["n"] += 1
            if calls["n"] == 1:
                return 1
            return await real_next_index(session, series_id)

        monkeypatch.setattr(series_link, "_next_index", stale_once)

        index = await assign_book_index(
            session, story_id=new_book.id, series_id=series_id
        )

        assert index == 2
        assert calls["n"] == 2


async def test_two_conflicts_raise(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two consecutive conflicts against the same taken index re-raise."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        series, _anchor = await seed_published_anchor(
            session, family_id=family.id, approved_by=user.id, book_index=1
        )
        await session.commit()
        series_id = series.id

    async with sessions() as session:
        new_book = await _bare_storybook(session, family_id=family.id)
        await session.commit()

        async def always_one(session: AsyncSession, series_id: uuid.UUID) -> int:
            return 1

        monkeypatch.setattr(series_link, "_next_index", always_one)

        with pytest.raises(IntegrityError):
            await assign_book_index(session, story_id=new_book.id, series_id=series_id)


async def test_no_series_request_is_noop(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A request with no series leaves the storybook row untouched."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        concept = Concept(family_id=family.id, brief={}, created_by=user.id)
        session.add(concept)
        await session.flush()

        book = await _bare_storybook(session, family_id=family.id)

        story_request = StoryRequest(
            family_id=family.id,
            request_text="a story",
            age_band="8-11",
            concept_id=concept.id,
            series_id=None,
        )
        session.add(story_request)
        await session.flush()

        await link_series_position(session, story_id=book.id, concept_id=concept.id)

        refreshed = await session.get(Storybook, book.id)
        assert refreshed is not None
        assert refreshed.series_id is None
        assert refreshed.book_index is None


async def test_direct_concept_is_noop(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A concept_id with no owning request row is a silent no-op."""
    async with sessions() as session:
        family, _user = await _seed_family_and_user(session)
        book = await _bare_storybook(session, family_id=family.id)

        await link_series_position(session, story_id=book.id, concept_id=uuid.uuid4())

        refreshed = await session.get(Storybook, book.id)
        assert refreshed is not None
        assert refreshed.series_id is None
        assert refreshed.book_index is None


def _minimal_blob() -> dict[str, object]:
    """A blob shaped enough to carry ``start_node`` and ``metadata`` (WS-G G2)."""
    return {"title": "T", "start_node": "n0", "metadata": {}, "nodes": []}


async def test_embed_series_block_writes_metadata(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The embed step writes metadata.series sourced from linkage + the series row."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=False,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()

        concept = Concept(family_id=family.id, brief={}, created_by=user.id)
        session.add(concept)
        await session.flush()

        story_request = StoryRequest(
            family_id=family.id,
            request_text="a story",
            age_band="8-11",
            concept_id=concept.id,
            series_id=series.id,
        )
        session.add(story_request)
        await session.flush()

        story_id = f"s_{uuid.uuid4().hex[:12]}"
        await persist_storybook(
            session,
            StorybookParams(
                story_id=story_id,
                blob=_minimal_blob(),
                family_id=family.id,
                created_by=user.id,
            ),
        )

        await link_series_position(session, story_id=story_id, concept_id=concept.id)
        await embed_series_block(session, story_id=story_id, version=1)
        await session.commit()

    # Re-read in a FRESH session (mirrors test_sequential_assignment_is_contiguous):
    # the writing session's identity map would satisfy session.get() without a
    # query, hiding a silently-skipped JSONB UPDATE (the exact regression the
    # RAD marker in embed_series_block guards against).
    async with sessions() as session:
        row = await session.get(StorybookVersion, (story_id, 1))
        assert row is not None
        meta = row.blob["metadata"]
        assert isinstance(meta, dict)
        block = meta["series"]
        assert isinstance(block, dict)
        storybook = await session.get(Storybook, story_id)
        assert storybook is not None
        assert block["series_id"] == str(storybook.series_id)
        assert block["book_index"] == storybook.book_index
        assert block["series_entry_node"] == row.blob["start_node"]
        assert block["is_final"] is False
        assert block["carries_state"] is False  # copied from the series row


async def test_embed_series_block_noop_for_non_series(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A book with no series linkage leaves the blob's metadata untouched."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        story_id = f"s_{uuid.uuid4().hex[:12]}"
        await persist_storybook(
            session,
            StorybookParams(
                story_id=story_id,
                blob=_minimal_blob(),
                family_id=family.id,
                created_by=user.id,
            ),
        )

        await embed_series_block(session, story_id=story_id, version=1)
        await session.commit()

    # Fresh session for the same identity-map reason as the test above.
    async with sessions() as session:
        row = await session.get(StorybookVersion, (story_id, 1))
        assert row is not None
        assert "series" not in row.blob.get("metadata", {})


async def test_embed_series_block_refuses_published_blob(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The immutability guard rejects embedding into an approved (published) blob.

    The approval gate's grandfather rule reasons that approved blobs can never
    change; this pins that invariant structurally so a future backfill caller
    cannot silently rewrite a published blob.
    """
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=True,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()

        concept = Concept(family_id=family.id, brief={}, created_by=user.id)
        session.add(concept)
        await session.flush()

        story_request = StoryRequest(
            family_id=family.id,
            request_text="a story",
            age_band="8-11",
            concept_id=concept.id,
            series_id=series.id,
        )
        session.add(story_request)
        await session.flush()

        story_id = f"s_{uuid.uuid4().hex[:12]}"
        await persist_storybook(
            session,
            StorybookParams(
                story_id=story_id,
                blob=_minimal_blob(),
                family_id=family.id,
                created_by=user.id,
            ),
        )
        await link_series_position(session, story_id=story_id, concept_id=concept.id)

        storybook = await session.get(Storybook, story_id)
        assert storybook is not None
        storybook.status = "published"
        storybook.current_published_version = 1
        await session.flush()

        with pytest.raises(BusinessLogicError, match="immutable") as excinfo:
            await embed_series_block(session, story_id=story_id, version=1)
        assert excinfo.value.details["rule"] == "embed_into_approved_blob"


def _pii() -> PiiContext:
    """An empty PiiContext; no real-child identifiers to guard in this test."""
    return PiiContext(child_names=frozenset(), birthdates=frozenset())


async def test_embed_series_block_survives_moderation_repair(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WS-G final review C1: embed_series_block must run AFTER moderation.

    Replicates ``generation/worker.py::_persist_and_moderate``'s exact
    post-fix call sequence -- ``persist_storybook``, ``link_series_position``,
    ``run_moderation_pipeline``, then ``embed_series_block`` -- and drives the
    REAL soft-repair path (``moderation/pipeline.py``'s ``attempt_repair``)
    using the same fakes as
    ``tests/unit/test_moderation_pipeline.py::test_soft_flag_triggers_repair_then_submits``
    and
    ``tests/integration/test_pipeline_event_instrumentation.py::test_repaired_moderation_writes_repair_applied_then_completed``:
    readability FLAGs once, everything else is clean, and ``attempt_repair``
    is stubbed to return a schema-valid revised blob that carries NO
    ``metadata.series`` -- exactly the shape a real repair produces, since
    its prompt only asks the model to preserve node ids/choices/branching,
    never ``metadata.series`` (that key does not exist on the blob until
    ``embed_series_block`` writes it).

    Regression coverage for the bug this guards: with the pre-fix ordering
    (embed called BEFORE moderation), the repair's
    ``version_row.blob = revised`` reassignment inside
    ``run_moderation_pipeline`` would silently discard the embedded block,
    and the assertions below would fail against a re-read blob with no
    ``metadata.series`` at all. Manually swapping this test's own
    ``run_moderation_pipeline``/``embed_series_block`` call order reproduces
    that failure (see the task report for the swapped-order run's output).
    """
    async with sessions() as session:
        family = Family(name="Repair Survival Family")
        session.add(family)
        await session.flush()
        user = User(family_id=family.id, role="guardian", authn_subject="g-repair")
        session.add(user)
        await session.flush()

        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=True,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()

        concept = Concept(family_id=family.id, brief={}, created_by=user.id)
        session.add(concept)
        await session.flush()

        story_request = StoryRequest(
            family_id=family.id,
            request_text="a story",
            age_band="8-11",
            concept_id=concept.id,
            series_id=series.id,
        )
        session.add(story_request)
        await session.flush()

        story_id = f"s_{uuid.uuid4().hex[:12]}"
        await persist_storybook(
            session,
            StorybookParams(
                story_id=story_id,
                blob=dict(_CANNED_STORY),
                family_id=family.id,
                created_by=user.id,
            ),
        )
        await link_series_position(session, story_id=story_id, concept_id=concept.id)

        monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            pipeline_mod, "run_safety_stage", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            pipeline_mod, "run_coherence_stage", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            pipeline_mod, "run_engagement_stage", AsyncMock(return_value=[])
        )
        flag_finding = Finding(
            stage=2,
            source=Source.LLM_READABILITY,
            category="reading_level",
            node_id="n_start",
            verdict=Verdict.FLAG,
            message="too hard",
        )
        # First call (initial moderation) FLAGs; second call (post-repair
        # re-moderation) is clean, so the repair is adopted.
        monkeypatch.setattr(
            pipeline_mod,
            "run_readability_stage",
            AsyncMock(side_effect=[[flag_finding], []]),
        )
        revised_blob: dict[str, object] = {
            **dict(_CANNED_STORY),
            "id": story_id,
            "title": "The Forest Path (revised)",
        }
        monkeypatch.setattr(
            pipeline_mod, "attempt_repair", AsyncMock(return_value=revised_blob)
        )

        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=Settings(review_provider="mock"),
            generation_provider=AsyncMock(),
            pii=_pii(),
        )
        # Post-fix ordering: embed runs AFTER moderation returns, so it reads
        # the post-repair blob.
        await embed_series_block(session, story_id=story_id, version=1)
        await session.commit()

    # Fresh session: the writing session's identity map would satisfy
    # session.get() without a query, hiding a silently-skipped write.
    async with sessions() as session:
        row = await session.get(StorybookVersion, (story_id, 1))
        assert row is not None
        # The repair really landed (not the pre-repair blob).
        assert row.blob["title"] == "The Forest Path (revised)"
        meta = row.blob["metadata"]
        assert isinstance(meta, dict)
        block = meta["series"]
        assert isinstance(block, dict)
        storybook = await session.get(Storybook, story_id)
        assert storybook is not None
        assert storybook.series_id == series.id
        assert block["series_id"] == str(storybook.series_id)
        assert block["book_index"] == storybook.book_index
        assert block["series_entry_node"] == row.blob["start_node"]
        assert block["is_final"] is False
        assert block["carries_state"] is True


async def test_link_series_position_assigns_index_and_logs(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A request with a series_id drives a real book_index assignment."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=True,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()

        concept = Concept(family_id=family.id, brief={}, created_by=user.id)
        session.add(concept)
        await session.flush()

        book = await _bare_storybook(session, family_id=family.id)

        story_request = StoryRequest(
            family_id=family.id,
            request_text="a story",
            age_band="8-11",
            concept_id=concept.id,
            series_id=series.id,
        )
        session.add(story_request)
        await session.flush()

        await link_series_position(session, story_id=book.id, concept_id=concept.id)

        refreshed = await session.get(Storybook, book.id)
        assert refreshed is not None
        assert refreshed.series_id == series.id
        assert refreshed.book_index == 1


async def test_assign_book_index_raises_value_error_when_storybook_missing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A story_id with no storybook row raises ValueError, not a DB error."""
    async with sessions() as session:
        family, user = await _seed_family_and_user(session)
        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=True,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()

        with pytest.raises(ValueError, match="not found for series assignment"):
            await assign_book_index(
                session, story_id="s_doesnotexist", series_id=series.id
            )


async def test_assign_book_index_reraises_non_unique_constraint_integrity_error(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A non-unique-constraint IntegrityError (FK violation) is not retried."""
    async with sessions() as session:
        family, _user = await _seed_family_and_user(session)
        book = await _bare_storybook(session, family_id=family.id)

        with pytest.raises(IntegrityError) as exc_info:
            await assign_book_index(session, story_id=book.id, series_id=uuid.uuid4())

        assert "uq_storybook_series_book_index" not in str(exc_info.value.orig)
