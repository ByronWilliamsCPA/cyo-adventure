"""The first-family-test path for a catalog book, end to end over HTTP.

The owner's first family session is catalog only: an admin approves and
publishes a pre-authored catalog book that sits at ``in_review``, a guardian
assigns it to a child profile, and the child reads it. This module drives
exactly that path against the real migrated schema and the real FastAPI app,
starting from the real importer rather than a hand-inserted row:

1. ``generation/import_catalog.py::import_catalog`` imports a real manifest
   entry under ``CATALOG_FAMILY_ID``, running the validator gate and the
   moderation pipeline with the reviewer this test suite is configured with
   (``review_provider="mock"``, the default), with the mock opted into
   per-node safe verdicts (``mock_review_judges_safe``) exactly as the
   real-backend nightly runs it, so the book lands at ``in_review`` the way a
   catalog import that passed review does.
2. The admin console's own call, ``POST /storybooks/{id}/approve`` with
   ``visibility="catalog"``, is REFUSED for that mock-reviewed report. This is
   the trap the family test can hit: a catalog imported on a deployment whose
   reviewer was the mock is permanently unapprovable until it is re-moderated
   by a real reviewer (``POST /admin/remoderate/{id}/{version}``).
3. With a genuine, independent report in place (what that re-moderation
   writes), the same approve succeeds, a guardian in an unrelated family sees
   and assigns the book, and the child lists it, fetches it, saves reading
   state, and records a completion.

``test_catalog_read_path.py`` covers the read path after the CLI promotion
(``promote_catalog_story``) of a hand-inserted row; this module covers the
admin-console approve call on an importer-produced row, which is the path the
family test actually uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, update

from cyo_adventure.core.config import settings
from cyo_adventure.db.models import CATALOG_FAMILY_ID, Storybook, StorybookVersion
from cyo_adventure.generation.import_catalog import (
    CATALOG_ENTRIES,
    CatalogEntry,
    ImportConfig,
    import_catalog,
)
from cyo_adventure.moderation.report import moderation_report_unusable
from tests.conftest import make_clean_moderation_report
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _entry(title: str) -> CatalogEntry:
    """Return the CATALOG_ENTRIES row with the given title, or raise."""
    for entry in CATALOG_ENTRIES:
        if entry.title == title:
            return entry
    msg = f"no CATALOG_ENTRIES row titled {title!r}"
    raise AssertionError(msg)


# A small current-shape manifest entry (also used by test_import_catalog.py),
# so the import stays fast while still exercising the real importer.
_CLOVER = _entry("Clover and the Butterfly")


async def _latest_version(
    sessions: async_sessionmaker[AsyncSession], story_id: str
) -> StorybookVersion:
    """Load the newest version row for ``story_id``."""
    async with sessions() as session:
        return (
            await session.execute(
                select(StorybookVersion)
                .where(StorybookVersion.storybook_id == story_id)
                .order_by(StorybookVersion.version.desc())
                .limit(1)
            )
        ).scalar_one()


async def test_admin_approves_an_imported_catalog_book_then_guardian_and_child_use_it(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import, approve to catalog, assign, and read, over the real HTTP surface."""
    # Without this the default mock answers "{}" and the fail-closed review
    # stage (#776) sends the book to needs_revision, so it would never reach
    # the in_review state the family test starts from.
    monkeypatch.setattr(settings, "mock_review_judges_safe", True)
    # --- 1. Real import -----------------------------------------------------
    outcomes = await import_catalog(
        sessions, ImportConfig(repo_root=_REPO_ROOT), entries=(_CLOVER,)
    )
    assert len(outcomes) == 1
    assert outcomes[0].outcome == "imported", outcomes[0].detail
    story_id = outcomes[0].story_id
    assert story_id is not None

    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        assert book.family_id == CATALOG_FAMILY_ID
        assert book.status == "in_review"
    version_row = await _latest_version(sessions, story_id)
    version = version_row.version
    # The mock reviewer's report is stamped unusable by design
    # (moderation/pipeline.py::_stamp_mock_reviewer).
    assert moderation_report_unusable(version_row.moderation_report)

    # --- 2. The mock-reviewed import is refused at approval -----------------
    refused = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth(seed.admin_token),
        json={"visibility": "catalog"},
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["details"]["rule"] == "approve_with_unusable_moderation"

    # --- 3. A genuine report in place: approve, assign, read ----------------
    # Stands in for what POST /admin/remoderate writes after a real,
    # independent reviewer passes the book; this test makes no LLM call.
    async with sessions() as session:
        await session.execute(
            update(StorybookVersion)
            .where(
                StorybookVersion.storybook_id == story_id,
                StorybookVersion.version == version,
            )
            .values(moderation_report=make_clean_moderation_report())
        )
        await session.commit()

    approved = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth(seed.admin_token),
        json={"visibility": "catalog"},
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "published"
    assert body["visibility"] == "catalog"
    assert body["current_published_version"] == version
    assert body["approved_by"] == str(seed.admin_user_id)

    # A guardian in an unrelated family (never CATALOG_FAMILY_ID) browses it.
    browse = await client.get(
        "/api/v1/guardian/books", headers=auth(seed.guardian_token)
    )
    assert browse.status_code == 200, browse.text
    books = {b["storybook_id"]: b for b in browse.json()["books"]}
    assert story_id in books
    assert books[story_id]["visibility"] == "catalog"

    assign = await client.post(
        f"/api/v1/storybooks/{story_id}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert assign.status_code == 200, assign.text

    # The child lists it, fetches the full blob, saves a place, and finishes.
    library = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert library.status_code == 200, library.text
    assert story_id in {item["id"] for item in library.json()["stories"]}

    child_view = await client.get(
        f"/api/v1/storybooks/{story_id}/versions/{version}",
        headers=auth(seed.child_token),
    )
    assert child_view.status_code == 200, child_view.text
    blob = child_view.json()
    start = blob["start_node"]
    first_choice = next(
        node for node in blob["nodes"] if node["id"] == start and node.get("choices")
    )["choices"][0]
    next_node = first_choice["target"]

    put = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json={
            "version": version,
            "current_node": next_node,
            "var_state": {},
            "path": [start, next_node],
            "visit_set": [start, next_node],
            "save_slots": {},
            "state_revision": 0,
        },
        headers=auth(seed.child_token),
    )
    assert put.status_code == 200, put.text

    ending_id = next(
        node["ending"]["id"] for node in blob["nodes"] if node.get("is_ending")
    )
    done = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "version": version,
            "ending_id": ending_id,
        },
        headers=auth(seed.child_token),
    )
    assert done.status_code == 200, done.text
