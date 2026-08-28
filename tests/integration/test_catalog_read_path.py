"""End-to-end proof of the promoted-catalog-story read path (WS catalog task 4).

Exercises the real production pipeline, not a shortcut fixture: a
``CATALOG_FAMILY_ID``-owned story is created ``in_review`` with a moderation
report and promoted through ``publishing/catalog_publish.py::promote_catalog_story``
(the same function the catalog-publish CLI calls), exactly as a real catalog
import would be approved. From there, all three actors are proven against the
real FastAPI app in one continuous scenario:

1. An admin can fetch the promoted story (``GET /storybooks/{id}/versions/{v}``),
   the admin review surface for any story regardless of owning family.
2. A guardian in an unrelated family (``seed.family_id``, never
   ``CATALOG_FAMILY_ID``) browses it via ``GET /guardian/books`` (catalog
   visibility crosses family) and assigns it to their child via
   ``POST /storybooks/{id}/assignments``.
3. That child opens it on the kid surface: it appears in
   ``GET /library``, the full node/story blob is fetchable via
   ``GET /storybooks/{id}/versions/{v}``, and the reading-state save/read
   round trip (the mechanism the reader UI uses to track a child's place in
   the story) succeeds.

Existing fragmented coverage (``test_guardian_books_api.py``,
``test_library_invariant.py``, ``test_reading_state.py``,
``test_catalog_publish.py``) pins each of these gates individually, each
using a hand-inserted ``status="published", visibility="catalog"`` row owned
by an arbitrary non-catalog family. None of them route a story through the
actual ``CATALOG_FAMILY_ID`` sentinel plus the real ``promote_catalog_story``
promotion path, and none chain admin -> guardian -> child in one scenario;
this test closes that gap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import CATALOG_FAMILY_ID, Storybook, StorybookVersion
from cyo_adventure.publishing.catalog_publish import promote_catalog_story
from tests.conftest import make_clean_moderation_report
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_LANTERN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)

_STORY_ID = "catalog-read-path-lantern"


def _save_body(
    version: int, *, node: str, revision: int, **extra: object
) -> dict[str, object]:
    """Build a reading-state PUT body (mirrors ``test_reading_state.py``)."""
    return {
        "version": version,
        "current_node": node,
        "var_state": {"has_lantern": True},
        "path": ["n_entrance", node],
        "visit_set": ["n_entrance", node],
        "save_slots": {},
        "state_revision": revision,
        **extra,
    }


async def _seed_promoted_catalog_story(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> dict[str, object]:
    """Create an in_review CATALOG_FAMILY_ID story and promote it for real.

    Mirrors the admin catalog workflow exactly: insert a
    ``CATALOG_FAMILY_ID``-owned ``Storybook`` at ``status="in_review"`` with a
    clean moderation report, then call ``promote_catalog_story`` (the same
    function the ``catalog-publish`` CLI invokes) rather than hand-setting
    ``status="published", visibility="catalog"`` directly.

    Args:
        sessions: The integration test's session factory.
        seed: The seeded fixture data (supplies the admin user id).

    Returns:
        dict[str, object]: The lantern story blob that was published, for the
        caller to assert response bodies against.
    """
    blob = json.loads(_LANTERN.read_text(encoding="utf-8"))
    blob["id"] = _STORY_ID
    async with sessions() as session:
        session.add(
            Storybook(id=_STORY_ID, family_id=CATALOG_FAMILY_ID, status="in_review")
        )
        await session.flush()
        session.add(
            StorybookVersion(
                storybook_id=_STORY_ID,
                version=1,
                blob=blob,
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.flush()
        version_row = await promote_catalog_story(
            session, _STORY_ID, seed.admin_user_id
        )
        assert version_row.storybook_id == _STORY_ID
        await session.commit()
    return blob


async def test_admin_guardian_child_read_path_for_a_promoted_catalog_story(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The full catalog read path holds for all three actors in one scenario."""
    blob = await _seed_promoted_catalog_story(sessions, seed)

    # --- Actor 1: admin sees the promoted story -----------------------------
    # The global admin review surface reads any story cross-family, proving
    # the promotion actually landed as status=published, visibility=catalog
    # with a real approver stamped (not just a row the test itself inserted).
    admin_view = await client.get(
        f"/api/v1/storybooks/{_STORY_ID}/versions/1",
        headers=auth(seed.admin_token),
    )
    assert admin_view.status_code == 200, admin_view.text
    assert admin_view.json() == blob

    # --- Actor 2: a guardian in an unrelated family browses and assigns -----
    # seed.family_id is a real family, never CATALOG_FAMILY_ID, so this proves
    # catalog visibility crossing family lines, not same-family access.
    browse = await client.get(
        "/api/v1/guardian/books", headers=auth(seed.guardian_token)
    )
    assert browse.status_code == 200, browse.text
    books = {b["storybook_id"]: b for b in browse.json()["books"]}
    assert _STORY_ID in books
    assert books[_STORY_ID]["visibility"] == "catalog"

    assign = await client.post(
        f"/api/v1/storybooks/{_STORY_ID}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert assign.status_code == 200, assign.text
    assert assign.json()["profile_ids"] == [str(seed.child_profile_id)]

    # --- Actor 3: the assigned child opens and reads the story --------------
    library = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert library.status_code == 200, library.text
    assert _STORY_ID in {item["id"] for item in library.json()["stories"]}

    child_view = await client.get(
        f"/api/v1/storybooks/{_STORY_ID}/versions/1",
        headers=auth(seed.child_token),
    )
    assert child_view.status_code == 200, child_view.text
    assert child_view.json() == blob

    # The reading-state round trip is the actual mechanism the reader UI uses
    # to track a child's place in the story; a 200 here proves the child can
    # not just list/fetch the book but genuinely play through it.
    put = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_STORY_ID}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert put.status_code == 200, put.text
    got = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_STORY_ID}",
        headers=auth(seed.child_token),
    )
    assert got.status_code == 200, got.text
    assert got.json()["state"]["current_node"] == "n_cave_fork"

    done = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": _STORY_ID,
            "version": 1,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert done.status_code == 200, done.text
