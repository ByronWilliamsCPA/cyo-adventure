"""WS-G G4: chain-so-far series validation at release approval."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.db.models import Family, Series, Storybook, StorybookVersion, User
from cyo_adventure.publishing.service import approve
from cyo_adventure.storybook.models import (
    AgeBand,
    Choice,
    Ending,
    EndingKind,
    Node,
    ReadingLevel,
    StoryMetadata,
    Topology,
    Valence,
)
from cyo_adventure.storybook.models import Series as SeriesBlock
from cyo_adventure.storybook.models import Storybook as StorybookDoc
from tests.conftest import make_clean_moderation_report

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _doc(
    story_id: str,
    *,
    series_id: str,
    book_index: int,
    entry: str | None = None,
    win: bool = True,
    with_series: bool = True,
) -> dict[str, object]:
    """A minimal schema-valid document blob, optionally series-tagged."""
    kind = EndingKind.SUCCESS if win else EndingKind.SETBACK
    valence = Valence.POSITIVE if win else Valence.NEGATIVE
    doc = StorybookDoc(
        id=story_id,
        version=1,
        title="T",
        start_node="n0",
        nodes=[
            Node(
                id="n0", body="go", choices=[Choice(id="c1", label="x", target="n_end")]
            ),
            Node(
                id="n_end",
                body="done",
                is_ending=True,
                ending=Ending(id="e1", valence=valence, kind=kind, title="End"),
            ),
        ],
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_10_13,
            reading_level=ReadingLevel(target=2.0),
            tier=2,
            estimated_minutes=5,
            ending_count=1,
            topology=Topology.GAUNTLET,
            series=SeriesBlock(
                series_id=series_id,
                book_index=book_index,
                series_entry_node=entry,
                is_final=False,
                carries_state=True,
            )
            if with_series
            else None,
        ),
    )
    return doc.model_dump(mode="json")


async def _seed_series(session: AsyncSession) -> tuple[Series, uuid.UUID]:
    fam = Family(name="Fam")
    session.add(fam)
    await session.flush()
    admin = User(family_id=fam.id, role="guardian", authn_subject="g")
    session.add(admin)
    await session.flush()
    series = Series(
        family_id=fam.id,
        title="Camp",
        age_band="10-13",
        carries_state=True,
    )
    session.add(series)
    await session.flush()
    return series, admin.id


async def _seed_book(
    session: AsyncSession,
    series: Series,
    *,
    story_id: str,
    book_index: int,
    status: str,
    blob: dict[str, object],
) -> Storybook:
    book = Storybook(
        id=story_id,
        family_id=series.family_id,
        status=status,
        current_published_version=1 if status == "published" else None,
        series_id=series.id,
        book_index=book_index,
    )
    session.add(book)
    await session.flush()
    session.add(
        StorybookVersion(
            storybook_id=story_id,
            version=1,
            blob=blob,
            moderation_report=make_clean_moderation_report(),
        )
    )
    await session.flush()
    return book


def _principal(user_id: uuid.UUID, family_id: uuid.UUID) -> object:
    """Build an admin approver Principal for series-gate service tests.

    approve() is admin-only in production (api/approval.py gates every handler
    through ``_load_admin_story`` on ``principal.is_admin``, and approve()
    re-checks it at the service boundary), so the approver principal carries
    the admin capability (a valid ``role=guardian, is_admin=True`` adult).
    """
    from cyo_adventure.api.deps import Principal

    return Principal(
        subject="g",
        user_id=user_id,
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(),
        is_admin=True,
    )


async def test_valid_chain_approves(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="published",
            blob=_doc("b1", series_id=sid, book_index=1),
        )
        book2 = await _seed_book(
            session,
            series,
            story_id="b2",
            book_index=2,
            status="in_review",
            blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
        )
        principal = _principal(admin_id, series.family_id)
        row = await approve(session, principal, book2, 1)
        assert row.approved_by is not None
        assert book2.status == "published"


async def test_archived_sibling_still_counts_in_chain(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Archiving book 1 must not break SR-2 contiguity for later approvals:
    # archive() only flips status and no archived->published transition
    # exists, so a status=="published" sibling filter would block book 2's
    # approval forever. The gate keys on current_published_version instead.
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        book1 = await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="published",
            blob=_doc("b1", series_id=sid, book_index=1),
        )
        # Mirror publishing.service.archive(): a status flip only; the
        # published version pointer and the book_index slot are retained.
        book1.status = "archived"
        await session.flush()
        book2 = await _seed_book(
            session,
            series,
            story_id="b2",
            book_index=2,
            status="in_review",
            blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
        )
        principal = _principal(admin_id, series.family_id)
        row = await approve(session, principal, book2, 1)
        assert row.approved_by is not None
        assert book2.status == "published"


async def test_sr_violation_blocks_approval(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Book 1 published with NO satisfying ending: SR-5 fires for the chain.
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="published",
            blob=_doc("b1", series_id=sid, book_index=1, win=False),
        )
        book2 = await _seed_book(
            session,
            series,
            story_id="b2",
            book_index=2,
            status="in_review",
            blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
        )
        principal = _principal(admin_id, series.family_id)
        with pytest.raises(BusinessLogicError, match="SR-5") as excinfo:
            await approve(session, principal, book2, 1)
        assert excinfo.value.details["rule"] == "series_validation"
        assert book2.status == "in_review"  # transition never happened


async def test_out_of_order_approval_blocked_sr2(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Book 1 exists but is not yet published; approving book 2 sees a chain
    # of {2} which is not contiguous from 1.
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="in_review",
            blob=_doc("b1", series_id=sid, book_index=1),
        )
        book2 = await _seed_book(
            session,
            series,
            story_id="b2",
            book_index=2,
            status="in_review",
            blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
        )
        principal = _principal(admin_id, series.family_id)
        with pytest.raises(BusinessLogicError, match="SR-2"):
            await approve(session, principal, book2, 1)


async def test_legacy_chain_is_grandfathered(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Book 1 predates WS-G: schema-valid blob, no series block. The gate is
    # skipped for the whole chain and approval proceeds.
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="published",
            blob=_doc("b1", series_id=sid, book_index=1, with_series=False),
        )
        book2 = await _seed_book(
            session,
            series,
            story_id="b2",
            book_index=2,
            status="in_review",
            blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
        )
        principal = _principal(admin_id, series.family_id)
        row = await approve(session, principal, book2, 1)
        assert row.approved_by is not None


async def test_self_legacy_book_is_grandfathered(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # The book under approval itself lacks the block (generated pre-deploy).
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        book1 = await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="in_review",
            blob=_doc("b1", series_id=sid, book_index=1, with_series=False),
        )
        principal = _principal(admin_id, series.family_id)
        row = await approve(session, principal, book1, 1)
        assert row.approved_by is not None


async def test_unparseable_sibling_blob_is_grandfathered(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Book 1 is PUBLISHED but its blob fails schema validation outright (not
    # merely missing the series block): _series_chain_docs must hit the
    # `except PydanticValidationError` branch and skip the gate, same as the
    # legacy-chain grandfather rule, so approval of book 2 succeeds.
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="published",
            blob={"id": "b1"},
        )
        book2 = await _seed_book(
            session,
            series,
            story_id="b2",
            book_index=2,
            status="in_review",
            blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
        )
        principal = _principal(admin_id, series.family_id)
        row = await approve(session, principal, book2, 1)
        assert row.approved_by is not None
        assert book2.status == "published"


async def test_single_book_series_approves_cleanly(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # New-series common case: book_index=1 with its own embedded series block
    # and zero published siblings. The chain is just the book under approval.
    async with sessions() as session:
        series, admin_id = await _seed_series(session)
        sid = str(series.id)
        book1 = await _seed_book(
            session,
            series,
            story_id="b1",
            book_index=1,
            status="in_review",
            blob=_doc("b1", series_id=sid, book_index=1),
        )
        principal = _principal(admin_id, series.family_id)
        row = await approve(session, principal, book1, 1)
        assert row.approved_by is not None
        assert book1.status == "published"
