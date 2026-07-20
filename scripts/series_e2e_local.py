"""End-to-end series test: import, link, approve, and publish both books.

Mirrors the worker's series linkage (assign_book_index + embed_series_block)
because import_filled_story alone performs no series linkage; that path is
worker-only via StoryRequest. Run from the repo root with
CYO_ADVENTURE_DATABASE_URL set.
"""

import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import select

import cyo_adventure.moderation.pipeline as _pipeline
from cyo_adventure.api.deps import Principal, Role
from cyo_adventure.core.database import get_session
from cyo_adventure.db.models import Family, Series, Storybook, StorybookVersion, User
from cyo_adventure.generation.import_story import ImportRequest, import_filled_story
from cyo_adventure.generation.series_link import assign_book_index, embed_series_block
from cyo_adventure.publishing.service import approve


async def _no_repair(**_kwargs: object) -> None:
    """Disable auto-repair for the local run.

    With all-mock providers the review stage fail-safes unknown verdicts to
    FLAG, and the repair path would then replace the 550-node blob with the
    mock generation stub (see the series stress test findings report). A
    discarded repair routes the soft-flagged story to in_review with its real
    content intact, which is the honest local approximation of production.
    """


# #ASSUME: external-resources: all providers are the mock defaults here; the
# repair hook is disabled so the imported blobs survive moderation intact.
# #VERIFY: docs/planning/series-stress-test-findings.md, finding F2.
_pipeline.attempt_repair = _no_repair

BOOK1 = "out/the-harrowstone-keep.filled.json"
BOOK2 = "out/the-sunken-temple.filled.json"


async def main(blob1: dict[str, object], blob2: dict[str, object]) -> None:
    """Drive both books through import, linkage, approval, and publish."""
    family_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # 1. Seed a family and an admin guardian.
    async with get_session() as session:
        session.add(Family(id=family_id, name="Williams Test Family"))
        session.add(
            User(
                id=user_id,
                family_id=family_id,
                role="guardian",
                is_admin=True,
                authn_subject=f"e2e|{user_id}",
                email="manager@williamsfamilyfund.com",
            )
        )
        await session.commit()
    print(f"[1] seeded family={family_id} admin user={user_id}")

    principal = Principal(
        subject=f"e2e|{user_id}",
        user_id=user_id,
        role=Role.GUARDIAN,
        family_id=family_id,
        profile_ids=frozenset(),
        is_admin=True,
    )

    # 2. Import book 1 (gate + persist + mock moderation).
    async with get_session() as session:
        story1 = await import_filled_story(
            session,
            ImportRequest(
                family_id=family_id,
                blob=blob1,
                created_by=user_id,
                model="skill-author",
                skeleton_slug="the-harrowstone-keep",
            ),
        )
        await session.commit()
    print(f"[2] imported book 1 story_id={story1}")

    # 3. Create the series row and link book 1 as index 1, embedding the block.
    series_id = uuid.uuid4()
    async with get_session() as session:
        session.add(
            Series(
                id=series_id,
                family_id=family_id,
                title="The Company of the Brass Lantern",
                age_band="13-16",
                carries_state=True,
                created_by=user_id,
            )
        )
        await session.flush()
        idx1 = await assign_book_index(session, story_id=story1, series_id=series_id)
        await embed_series_block(session, story_id=story1, version=1)
        await session.commit()
    print(f"[3] linked book 1 to series={series_id} book_index={idx1}")

    # 4. Approve and publish book 1.
    async with get_session() as session:
        row1 = await session.get(Storybook, story1)
        ver = await approve(session, principal, row1, 1)
        await session.commit()
        print(
            f"[4] book 1 approved: status={row1.status} version={ver.version} "
            f"approved_by={ver.approved_by}"
        )

    # 5. Import book 2.
    async with get_session() as session:
        story2 = await import_filled_story(
            session,
            ImportRequest(
                family_id=family_id,
                blob=blob2,
                created_by=user_id,
                model="skill-author",
                skeleton_slug="the-sunken-temple",
            ),
        )
        await session.commit()
    print(f"[5] imported book 2 story_id={story2}")

    # 6. Link book 2 as index 2 and embed its series block.
    async with get_session() as session:
        idx2 = await assign_book_index(session, story_id=story2, series_id=series_id)
        await embed_series_block(session, story_id=story2, version=1)
        await session.commit()
    print(f"[6] linked book 2 to series={series_id} book_index={idx2}")

    # 7. Approve book 2; the series chain gate (SR-1..SR-7) fires here.
    async with get_session() as session:
        row2 = await session.get(Storybook, story2)
        ver2 = await approve(session, principal, row2, 1)
        await session.commit()
        print(
            f"[7] book 2 approved with series chain gate: status={row2.status} "
            f"version={ver2.version}"
        )

    # 8. Verify final database state.
    async with get_session() as session:
        books = (
            await session.scalars(
                select(Storybook)
                .where(Storybook.series_id == series_id)
                .order_by(Storybook.book_index)
            )
        ).all()
        print("[8] final series state:")
        for b in books:
            v = await session.scalar(
                select(StorybookVersion).where(
                    StorybookVersion.storybook_id == b.id,
                    StorybookVersion.version == 1,
                )
            )
            blob_series = v.blob["metadata"]["series"]
            print(
                f"    book_index={b.book_index} id={b.id} "
                f"status={b.status} embedded_series="
                f"{{id:{blob_series['series_id']}, idx:{blob_series['book_index']}, "
                f"entry:{blob_series['series_entry_node']}, "
                f"carries:{blob_series['carries_state']}, "
                f"final:{blob_series['is_final']}}}"
            )
    print("E2E COMPLETE")


asyncio.run(
    main(
        json.loads(Path(BOOK1).read_text()),
        json.loads(Path(BOOK2).read_text()),
    )
)
