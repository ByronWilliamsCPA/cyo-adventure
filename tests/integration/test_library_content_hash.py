"""Content identity for a served Storybook version (offline-cache staleness).

``StorybookVersion`` is documented as immutable, but
``scripts/retrofit_personalization.py`` rewrote ``blob`` in place for 15
already-published rows without bumping ``version``. The offline cache
(``frontend/src/offline/db.ts``) keys downloaded blobs by ``id@version`` alone
and never re-fetches on a hit, so every device that downloaded one of those
books before the retrofit keeps the pre-retrofit prose permanently.

``LibraryItem.content_hash`` is the signal that makes that detectable. These
tests pin the two properties the client depends on: the digest is taken over
the exact bytes the read route serves, and it moves when, and only when, those
bytes move.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import StorybookVersion
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _listed_hash(client: AsyncClient, seed: Seed) -> str:
    """Return the seeded book's ``content_hash`` from the library listing."""
    listing = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert listing.status_code == 200, listing.text
    item = next(s for s in listing.json()["stories"] if s["id"] == seed.storybook_id)
    value: str = item["content_hash"]
    return value


async def test_library_content_hash_matches_served_version_bytes(
    client: AsyncClient, seed: Seed
) -> None:
    """The listed digest equals sha256 of the read route's raw response body.

    The load-bearing assertion for the whole feature. The client compares an
    opaque server string against the one it stored for the payload it cached;
    if the listing hashed a different serialization than the read route emits,
    every book would read as permanently changed and the client's eviction
    check would re-download the entire shelf on every load. This asserts over
    ``response.content`` (the real wire bytes), not a re-serialized dict.
    """
    listed = await _listed_hash(client, seed)
    served = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(seed.child_token),
    )
    assert served.status_code == 200, served.text

    expected = f"sha256:{hashlib.sha256(served.content).hexdigest()}"
    assert listed == expected


async def test_library_content_hash_is_stable_across_repeat_listings(
    client: AsyncClient, seed: Seed
) -> None:
    """An unchanged blob keeps the same digest, so a fresh cache stays fresh.

    Guards the other half of the client contract: the digest must not depend
    on dict iteration order, request identity, or anything else that varies
    between two calls, or every shelf load would evict every cached book.
    """
    first = await _listed_hash(client, seed)
    second = await _listed_hash(client, seed)
    assert first == second
    assert first.startswith("sha256:")


async def test_library_content_hash_changes_when_blob_is_rewritten_in_place(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The exact production defect: same version, mutated blob, new digest.

    Reproduces what the retrofit did (rewrite ``blob``, leave ``version``
    alone) and asserts the one thing the offline cache needs in order to
    notice: the identity the client stored no longer matches the identity the
    server now advertises.
    """
    before = await _listed_hash(client, seed)

    async with sessions() as session:
        row = (
            await session.scalars(
                select(StorybookVersion).where(
                    StorybookVersion.storybook_id == seed.storybook_id,
                    StorybookVersion.version == seed.version,
                )
            )
        ).one()
        mutated = dict(row.blob)
        mutated["title"] = "{~HERO:Explorer~} and the Lantern"
        row.blob = mutated
        await session.commit()

    after = await _listed_hash(client, seed)
    assert after != before
    assert after.startswith("sha256:")
