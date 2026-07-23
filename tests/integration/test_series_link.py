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
from cyo_adventure.core.exceptions import BusinessLogicError, ValidationError
from cyo_adventure.db.models import (
    Concept,
    Family,
    GenerationJob,
    Series,
    Storybook,
    StorybookVersion,
    StoryRequest,
    User,
)
from cyo_adventure.generation import series_link
from cyo_adventure.generation import worker as worker_mod
from cyo_adventure.generation.orchestrator import GenerationOutcome
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import _CANNED_STORY, MockProvider
from cyo_adventure.generation.series_link import (
    assign_book_index,
    embed_series_block,
    link_series_position,
)
from cyo_adventure.generation.worker import _persist_and_moderate, _PersistContext
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


async def test_embed_series_block_replaces_non_dict_metadata(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A blob whose ``metadata`` key is present but not a dict is replaced, not raised on.

    ``embed_series_block`` reads ``raw_meta = blob.get("metadata")`` and only
    treats it as a base to merge into when ``isinstance(raw_meta, dict)``;
    otherwise it falls back to a fresh ``{}`` before writing ``metadata.series``
    (see ``generation/series_link.py``). This pins that a corrupted/malformed
    ``metadata`` value (a string here) is silently discarded and replaced with
    a dict containing only the new ``series`` key, rather than raising or
    preserving the non-dict value.
    """
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
        blob = _minimal_blob()
        blob["metadata"] = "not-a-dict"
        await persist_storybook(
            session,
            StorybookParams(
                story_id=story_id,
                blob=blob,
                family_id=family.id,
                created_by=user.id,
            ),
        )

        await link_series_position(session, story_id=story_id, concept_id=concept.id)
        # #ASSUME: data-integrity: a non-dict metadata value must not raise;
        # the isinstance guard falls back to a fresh {} instead.
        # #VERIFY: the resulting metadata is a dict with only "series" set,
        # never the original string.
        await embed_series_block(session, story_id=story_id, version=1)
        await session.commit()

    # Fresh session for the same identity-map reason as the tests above.
    async with sessions() as session:
        row = await session.get(StorybookVersion, (story_id, 1))
        assert row is not None
        meta = row.blob["metadata"]
        assert isinstance(meta, dict)
        assert set(meta) == {"series"}
        block = meta["series"]
        assert isinstance(block, dict)
        storybook = await session.get(Storybook, story_id)
        assert storybook is not None
        assert block["series_id"] == str(storybook.series_id)


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
    return PiiContext(child_names=frozenset())


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

        random_series_id = uuid.uuid4()
        with pytest.raises(IntegrityError) as exc_info:
            await assign_book_index(
                session, story_id=book.id, series_id=random_series_id
            )

        assert "uq_storybook_series_book_index" not in str(exc_info.value.orig)


def _series_seed_rows(family: Family, series: Series, concept: Concept) -> StoryRequest:
    """A StoryRequest linking concept to series (the worker's series signal)."""
    return StoryRequest(
        family_id=family.id,
        request_text="a story",
        age_band="8-11",
        concept_id=concept.id,
        series_id=series.id,
    )


def _stub_moderation_stages(
    monkeypatch: pytest.MonkeyPatch, *, readability: AsyncMock
) -> None:
    """All-clean moderation stages except the supplied readability stub."""
    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_mod, "run_safety_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_mod, "run_coherence_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        pipeline_mod, "run_engagement_stage", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(pipeline_mod, "run_readability_stage", readability)


async def test_persist_and_moderate_repair_roundtrip_embeds_series_block(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #184 F7/F11: drive the REAL _persist_and_moderate through a soft repair.

    Unlike test_embed_series_block_survives_moderation_repair (which replicates
    the worker's call sequence), this drives the worker helper itself, so a
    reorder of persist/link/moderate/embed inside _persist_and_moderate fails
    THIS test even if each callee still works in isolation.
    """
    async with sessions() as session:
        family = Family(name="Worker Roundtrip Family")
        session.add(family)
        await session.flush()
        user = User(family_id=family.id, role="guardian", authn_subject="g-worker")
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
        session.add(_series_seed_rows(family, series, concept))
        await session.flush()
        job = GenerationJob(concept_id=concept.id, status="running")
        session.add(job)
        await session.flush()

        flag_finding = Finding(
            stage=2,
            source=Source.LLM_READABILITY,
            category="reading_level",
            node_id="n_start",
            verdict=Verdict.FLAG,
            message="too hard",
        )
        _stub_moderation_stages(
            monkeypatch,
            readability=AsyncMock(side_effect=[[flag_finding], []]),
        )
        story_id = f"s_{job.id}"
        revised_blob: dict[str, object] = {
            **dict(_CANNED_STORY),
            "id": story_id,
            "title": "The Forest Path (revised)",
        }
        monkeypatch.setattr(
            pipeline_mod, "attempt_repair", AsyncMock(return_value=revised_blob)
        )
        monkeypatch.setattr(
            worker_mod, "_default_settings", Settings(review_provider="mock")
        )

        outcome = GenerationOutcome(
            status="passed",
            storybook=dict(_CANNED_STORY),
            report={"ok": True},
            attempts=0,
            stage_log=["stage_a:gate_ok"],
        )
        ctx = _PersistContext(
            job_id=job.id,
            job_row=job,
            concept_row=concept,
            effective_provider=MockProvider(responses=[]),
            authoring=None,
            pii=_pii(),
        )
        await _persist_and_moderate(session, ctx, outcome)
        # The worker's caller owns the happy-path commit (worker.py docstring).
        await session.commit()

    async with sessions() as session:
        row = await session.get(StorybookVersion, (story_id, 1))
        assert row is not None
        assert row.blob["title"] == "The Forest Path (revised)"
        meta = row.blob["metadata"]
        assert isinstance(meta, dict)
        block = meta["series"]
        assert isinstance(block, dict)
        assert block["series_entry_node"] == row.blob["start_node"]
        assert block["carries_state"] is True
        refreshed_job = await session.get(GenerationJob, job.id)
        assert refreshed_job is not None
        assert refreshed_job.storybook_id == story_id


async def test_persist_and_moderate_embed_failure_rolls_back_and_fails_job(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #184 F11: an embed_series_block failure rolls back the persist.

    Asserts the invariant the worker's except path promises: the unreviewed
    storybook persist is discarded (no row survives, so an RQ retry of the
    same job cannot collide on the per-job story id), the job lands committed
    as "failed" with the error recorded, and the exception propagates.
    """
    async with sessions() as session:
        family = Family(name="Worker Rollback Family")
        session.add(family)
        await session.flush()
        user = User(family_id=family.id, role="guardian", authn_subject="g-rollback")
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
        session.add(_series_seed_rows(family, series, concept))
        await session.flush()
        job = GenerationJob(concept_id=concept.id, status="running")
        session.add(job)
        # The rollback in the except path discards flushed-but-uncommitted rows,
        # so the job row must be durable BEFORE _persist_and_moderate runs (in
        # production it is: the worker commits the running transition first).
        await session.commit()

        _stub_moderation_stages(monkeypatch, readability=AsyncMock(return_value=[]))
        monkeypatch.setattr(
            worker_mod, "_default_settings", Settings(review_provider="mock")
        )
        monkeypatch.setattr(
            worker_mod,
            "embed_series_block",
            AsyncMock(
                side_effect=ValidationError("embed exploded", field="blob", value=None)
            ),
        )

        outcome = GenerationOutcome(
            status="passed",
            storybook=dict(_CANNED_STORY),
            report={"ok": True},
            attempts=0,
            stage_log=["stage_a:gate_ok"],
        )
        ctx = _PersistContext(
            job_id=job.id,
            job_row=job,
            concept_row=concept,
            effective_provider=MockProvider(responses=[]),
            authoring=None,
            pii=_pii(),
        )
        story_id = f"s_{job.id}"
        with pytest.raises(ValidationError, match="embed exploded"):
            await _persist_and_moderate(session, ctx, outcome)

    async with sessions() as session:
        # The persist was rolled back: no storybook row survives.
        assert await session.get(Storybook, story_id) is None
        assert await session.get(StorybookVersion, (story_id, 1)) is None
        # The failure was recorded and committed by _record_failure.
        refreshed_job = await session.get(GenerationJob, job.id)
        assert refreshed_job is not None
        assert refreshed_job.status == "failed"
        assert refreshed_job.error is not None
        assert "embed exploded" in refreshed_job.error
