---
schema_type: planning
title: "WS-G PR 2: Continuation Runtime Implementation Plan"
description: "Task-by-task implementation plan for WS-G PR 2: the series-next API, the reader's
  Continue-the-series surface with entry-node jump and name-matched var-state seeding, the client
  regeneration, and e2e coverage in both Playwright tiers."
tags:
  - planning
  - series
  - implementation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give a zero-context implementer everything needed to build WS-G PR 2 (spec section 4 of
  docs/planning/ws-g-series-chaining-spec.md) as bite-sized TDD tasks with complete code, exact
  commands, and the discovery facts that must not be re-derived."
component: Reading
source: "docs/planning/ws-g-series-chaining-spec.md sections 4 and 8 (ratified 2026-07-09);
  codebase discovery 2026-07-10 against origin/main 4c44907 (post WS-G PR 1 #184, WS-E #180,
  kid frontend #185)."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal

A kid who reaches a satisfying ending of a non-final series book sees "Continue the series" and
opens the next book at its declared entry node with name-matched variable state carried across
(state-carrying series only), backed by a new kid-scoped `GET /api/v1/series-next` endpoint.

## Architecture

One new backend route in the existing reading router behind the existing single read gate
(`_load_readable_storybook`); a regenerated client; a pure `startContinuation` engine function
mirroring the server's structural-floor invariants; a `ContinueSeries` component on the ending
screen; a continuation seed passed through router location state into `ReaderPage`'s fresh-state
branch. No migration, no new event types, no offline-layer changes.

## Global constraints (binding for every task)

- Worktree `.worktrees/ws-g-pr2`, branch `feat/ws-g-continuation-runtime` (cut from `4c44907`).
  Never commit to main.
- Sign every commit (`git commit -S`), Conventional Commits, NO em-dash characters anywhere
  (pre-commit enforced). Stage only the files you changed (`git add <paths>`, never `-A`/`.`).
- Backend: ruff format/lint (88 chars), basedpyright strict, RAD markers on async/db/auth code
  per `src/cyo_adventure/CLAUDE.md`. Exceptions only from `core/exceptions.py`.
- Frontend: ESLint + Prettier + `tsc`; snake_case reading-state fields (they serialize directly
  to the API payload).
- `GET /api/v1/series-next` returns **200 with `next: null`** for every expected absence (not a
  series book, no next book, next unpublished, next not readable). Errors are reserved for the
  CURRENT book being unknown/unreadable and for profile authorization, exactly like the other
  kid-scoped reading routes.
- Continuation saves MUST NOT carry `choice_path` (see Key facts item 2).
- Regenerated client under `frontend/src/client/` is committed; CI fails on drift.
- TDD: write the failing test first for every code change; run it, watch it fail, implement,
  watch it pass, commit.

## Key facts an implementer must not re-derive

1. **The single read gate.** `_load_readable_storybook(ctx, storybook_id, profile_id)` in
   [reading.py:81-132](../../src/cyo_adventure/api/reading.py) is the ONLY access check on every
   reading route: published + own-family always readable; cross-family requires
   `visibility == "catalog"` plus a `StorybookAssignment` row, else 403; unknown id 404. The new
   route reuses it for both the current book (raise) and the sibling (catch, map to null).
2. **Structural floor vs replay.** `player/replay.py::validate_reading_state` runs the structural
   floor on EVERY reading-state write: every declared variable present, values correctly typed
   and in-bounds, all node ids known, `current_node == path[-1]`. Full engine replay-from-start
   runs ONLY when `choice_path` is present, and the frontend never sends it today. A continuation
   state (fresh state at the entry node with seeded vars) passes the floor but can never pass a
   replay-from-start; `api/reading.py:149-150` tags a plan to make `choice_path` required, so
   `startContinuation` carries a `#CRITICAL` marker naming this coupling.
3. **Ending kinds are lowercase strings.** `EndingKind` (storybook/models.py:97-105) values are
   `"success"`, `"setback"`, `"death"`, `"capture"`, `"completion"`, `"discovery"`. Satisfying =
   `{"success", "completion"}` only (mirrors `validator/series.py::_SATISFYING_KINDS`;
   `"discovery"` is NOT satisfying).
4. **The frontend `Ending` interface is wrong today.** `player/types.ts:20-24` declares
   `type: string`, but every blob carries `kind` and `valence` (see any fixture, e.g.
   `tests/fixtures/storybook/valid/03_tier2_lantern.json`). Verified 2026-07-10: NO frontend code
   reads `ending.type`, so replacing the field is safe and required (Task 3).
5. **The embedded series block shape** (written by PR 1's `generation/series_link.py`):
   `blob["metadata"]["series"] = {series_id: str, book_index: int, series_entry_node: str | null,
   is_final: bool, carries_state: bool}`. Legacy (pre-WS-G) published blobs have NO block.
   The `series` DB table row (`carries_state` column) is authoritative; the block copies it.
6. **Reader remount semantics.** `ReaderRoute` keys `ReaderPage` by
   `${profileId}:${storybookId}:${version}` (ReaderRoute.tsx), so navigating from book 1's reader
   to book 2's reader fully remounts `ReaderPage`; the continuation seed is consumed exactly once
   by the remounted instance's `load()`. Location state does not survive a hard refresh: a
   refreshed book-2 page falls back to a plain fresh start (accepted v1 edge, spec section 6).
7. **Fresh vs resume.** `ReaderPage.load()` (ReaderPage.tsx:144-218) resolves `saved` from local
   IndexedDB, then the server; `initialReading: undefined` means the machine calls
   `start(story)`. The continuation seed applies ONLY in the `saved === undefined` branch, which
   is exactly the spec's no-clobber rule.
8. **Test scaffolding that exists** (verified): `tests/integration/conftest.py` `Seed` dataclass
   (family_id, child/guardian/admin tokens, other_child_* fields, storybook_id, version), `auth()`
   helper, `client` fixture, `sessions` fixture (`async_sessionmaker`; same usage as
   `tests/integration/test_series_approval_gate.py`); `tests/integration/_series_utils.py`
   `seed_published_anchor`; `tests/integration/test_seed_dev_data.py` for the seed script;
   frontend colocated `*.test.tsx` with MemoryRouter (Reader.test.tsx uses the lantern story from
   `schema/conformance/player_traces.json` traces[0].story); Playwright mocked tier in
   `frontend/e2e/` (route interception, see reader.spec.ts), real tier in `frontend/e2e-real/`
   (requires local stack + `scripts/seed_dev_data.py`, NOT run in CI).
9. **Client regen without a live server**: dump the schema in-process and point `OPENAPI_INPUT`
   at it (same recipe as ci.yml's `contract` job):

   ```bash
   uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" > "$SCHEMA"
   cd frontend && OPENAPI_INPUT="$SCHEMA" npm run generate-client
   ```

10. **Name collisions**: `cyo_adventure.db.models.Series` (ORM row) vs the embedded pydantic
    `Series` in `storybook/models.py`. Backend code in this PR touches only the ORM `Series`.
    The frontend `Storybook.metadata` is `Record<string, unknown>`; parse defensively.

## File structure

| File | Change |
| --- | --- |
| `src/cyo_adventure/api/schemas.py` | Add `SeriesNextBook`, `SeriesNextView` |
| `src/cyo_adventure/api/reading.py` | Add `GET /series-next/{profile_id}/{storybook_id}` |
| `tests/integration/test_series_next.py` | New: endpoint integration tests |
| `frontend/src/client/*` | Regenerated (committed) |
| `frontend/src/player/types.ts` | Fix `Ending`: `kind`/`valence` replace dead `type` |
| `frontend/src/player/engine.ts` | Add `startContinuation` |
| `frontend/src/player/series.ts` | New: `seriesMeta`, `SATISFYING_ENDING_KINDS`, `ContinuationSeed`, `parseContinuation` |
| `frontend/src/player/engine.test.ts`, `series.test.ts` | Engine + helper tests |
| `frontend/src/api/readerApi.ts` | Add `makeFetchSeriesNext` + `SeriesNextBookInfo` alias |
| `frontend/src/reader/ContinueSeries.tsx` (+ test) | New component |
| `frontend/src/reader/Reader.tsx` (+ test) | Ending-screen wiring |
| `frontend/src/reader/ReaderPage.tsx` (+ test) | Continuation seed in fresh branch |
| `frontend/src/reader/ReaderRoute.tsx` (+ test) | Location-state parse + fetcher prop |
| `frontend/e2e/series-continue.spec.ts` | New mocked-tier e2e |
| `frontend/e2e-real/series-continue-real.spec.ts` | New real-tier e2e |
| `scripts/seed_dev_data.py` + `tests/integration/test_seed_dev_data.py` | Seed a two-book series |
| `CHANGELOG.md` | Unreleased entry |

---

### Task 0: Verify base state

Operational task; no code.

- [ ] **Step 1: Confirm worktree and branch**

Run: `cd /home/byron/dev/CYO_Adventure/.worktrees/ws-g-pr2 && git branch --show-current && git log --oneline -1`
Expected: `feat/ws-g-continuation-runtime`, HEAD `4c44907`.
Abort if: branch or base differs.

- [ ] **Step 2: Backend suite green**

Run: `uv run pytest -q 2>&1 | tail -3`
Expected: all passed (main was green at the base commit; ~2100+ tests, several minutes).
Abort if: any failure (report; do not fix pre-existing failures silently).

- [ ] **Step 3: Frontend suite green**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run 2>&1 | tail -5`
Expected: all pass.
Abort if: failures.

---

### Task 1: Backend series-next endpoint

**Files:**

- Modify: `src/cyo_adventure/api/schemas.py`
- Modify: `src/cyo_adventure/api/reading.py`
- Test: `tests/integration/test_series_next.py` (new)

- [ ] **Step 1: Write the failing integration tests**

Create `tests/integration/test_series_next.py`. Copy the auth/client usage exactly from
`tests/integration/test_reading_state.py` (same `client`, `seed`, `sessions` fixtures and
`auth()` helper; `sessions` is used the same way as in
`tests/integration/test_series_approval_gate.py`).

```python
"""Integration tests for GET /api/v1/series-next (WS-G PR 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    Series,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _blob(
    story_id: str,
    *,
    series_id: str | None,
    book_index: int,
    entry: str = "n_start",
) -> dict[str, object]:
    """A minimal schema-valid two-node story blob, optionally series-embedded."""
    metadata: dict[str, object] = {"age_band": "10-13"}
    if series_id is not None:
        metadata["series"] = {
            "series_id": series_id,
            "book_index": book_index,
            "series_entry_node": entry,
            "is_final": False,
            "carries_state": True,
        }
    return {
        "schema_version": "2.0",
        "id": story_id,
        "version": 1,
        "title": f"Book {book_index}",
        "metadata": metadata,
        "variables": [
            {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5}
        ],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Onward.",
                "is_ending": False,
                "choices": [{"id": "c_go", "label": "Go", "target": "n_end"}],
            },
            {
                "id": "n_end",
                "body": "Done.",
                "is_ending": True,
                "ending": {
                    "id": "e_done",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
    }


async def _seed_series(
    session: AsyncSession, family_id: uuid.UUID, created_by: uuid.UUID
) -> Series:
    series = Series(
        family_id=family_id,
        title="Ember Trail",
        age_band="10-13",
        carries_state=True,
        created_by=created_by,
    )
    session.add(series)
    await session.flush()
    return series


async def _seed_book(
    session: AsyncSession,
    series: Series,
    seed: Seed,
    *,
    story_id: str,
    book_index: int,
    status: str = "published",
    published: bool = True,
    embed: bool = True,
    visibility: str = "family",
    assign_to: uuid.UUID | None = None,
) -> Storybook:
    book = Storybook(
        id=story_id,
        family_id=seed.family_id,
        status=status,
        visibility=visibility,
        current_published_version=1 if published else None,
        series_id=series.id,
        book_index=book_index,
    )
    session.add(book)
    session.add(
        StorybookVersion(
            storybook_id=story_id,
            version=1,
            blob=_blob(
                story_id,
                series_id=str(series.id) if embed else None,
                book_index=book_index,
            ),
            approved_by=seed.admin_user_id,
        )
    )
    if assign_to is not None:
        session.add(
            StorybookAssignment(
                child_profile_id=assign_to,
                storybook_id=story_id,
                assigned_by=seed.admin_user_id,
            )
        )
    await session.flush()
    return book


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_returns_next_published_book(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Book 1 of an own-family series resolves book 2 with its declared entry node."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_a1", book_index=1)
        await _seed_book(session, series, seed, story_id="s_next_a2", book_index=2)
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_a1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    nxt = resp.json()["next"]
    assert nxt == {
        "storybook_id": "s_next_a2",
        "version": 1,
        "title": "Book 2",
        "series_entry_node": "n_start",
        "carries_state": True,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_null_for_non_series_book(
    client: AsyncClient, seed: Seed
) -> None:
    """A storybook with no series linkage answers next: null."""
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_null_for_last_book(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The top-index book has no next; expected absence is null, not an error."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_b1", book_index=1)
        await _seed_book(session, series, seed, story_id="s_next_b2", book_index=2)
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_b2",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_null_when_next_unpublished(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An in-review next book is invisible to the reader."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_c1", book_index=1)
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_c2",
            book_index=2,
            status="in_review",
            published=False,
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_c1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_unassigned_catalog_sibling_is_null(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A cross-family catalog next book without an assignment answers null."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_d1",
            book_index=1,
            visibility="catalog",
            assign_to=seed.other_child_profile_id,
        )
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_d2",
            book_index=2,
            visibility="catalog",
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.other_child_profile_id}/s_next_d1",
        headers=auth(seed.other_child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_assigned_catalog_sibling_returned(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Assigning the catalog next book makes it resolvable for that profile."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_e1",
            book_index=1,
            visibility="catalog",
            assign_to=seed.other_child_profile_id,
        )
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_e2",
            book_index=2,
            visibility="catalog",
            assign_to=seed.other_child_profile_id,
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.other_child_profile_id}/s_next_e1",
        headers=auth(seed.other_child_token),
    )
    assert resp.status_code == 200
    assert resp.json()["next"]["storybook_id"] == "s_next_e2"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_legacy_sibling_has_null_entry_node(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A pre-WS-G next book (no embedded block) is returned with entry null."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_f1", book_index=1)
        await _seed_book(
            session, series, seed, story_id="s_next_f2", book_index=2, embed=False
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_f1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    nxt = resp.json()["next"]
    assert nxt["storybook_id"] == "s_next_f2"
    assert nxt["series_entry_node"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_other_familys_profile_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token cannot query another family's profile id."""
    resp = await client.get(
        f"/api/v1/series-next/{seed.other_child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_unknown_current_book_is_404(
    client: AsyncClient, seed: Seed
) -> None:
    """The CURRENT book being unknown is an error, not an expected absence."""
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_does_not_exist",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/integration/test_series_next.py -q`
Expected: FAIL (404 route not found on every request-shaped test).

- [ ] **Step 3: Add the response schemas**

In `src/cyo_adventure/api/schemas.py`, next to the other reading views:

```python
class SeriesNextBook(BaseModel):
    """The next readable book in a series, resolved for one profile."""

    model_config = ConfigDict(extra="forbid")

    storybook_id: str
    version: int
    title: str
    series_entry_node: str | None = None
    carries_state: bool


class SeriesNextView(BaseModel):
    """GET /series-next response; ``next`` is null for every expected absence."""

    model_config = ConfigDict(extra="forbid")

    next: SeriesNextBook | None = None
```

- [ ] **Step 4: Add the route**

In `src/cyo_adventure/api/reading.py`: add `Series` to the `cyo_adventure.db.models` import and
`SeriesNextBook, SeriesNextView` to the schemas import, then add after `get_reading_state`:

```python
@router.get("/series-next/{profile_id}/{storybook_id}")
async def get_series_next(
    profile_id: str,
    storybook_id: str,
    ctx: Context,
) -> SeriesNextView:
    """Resolve the next book in this storybook's series for a profile.

    Expected absences (not a series book, no next book yet, next book
    unpublished, next book not readable by this profile) answer 200 with
    ``next: null``; errors are reserved for the CURRENT book being unknown
    or unreadable, matching the other kid-scoped reading routes (WS-G spec
    section 4).

    Args:
        profile_id: The child profile asking to continue.
        storybook_id: The series book the profile just finished.
        ctx: The request context.

    Returns:
        SeriesNextView: The next book's id, published version, title,
            declared entry node, and state-carry flag, or ``next: null``.

    Raises:
        ResourceNotFoundError: If the current storybook does not exist.
        AuthorizationError: If the profile is not the principal's, or the
            CURRENT book is not readable by it.
    """
    # #CRITICAL: security: profile authorization and the current book's read
    # gate run before any series resolution so this route cannot be used to
    # probe another family's series structure.
    # #VERIFY: test_series_next_other_familys_profile_forbidden,
    # test_series_next_unknown_current_book_is_404.
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    book = await _load_readable_storybook(ctx, storybook_id, parsed)
    if book.series_id is None or book.book_index is None:
        return SeriesNextView(next=None)
    sibling = await ctx.session.scalar(
        select(Storybook).where(
            Storybook.series_id == book.series_id,
            Storybook.book_index == book.book_index + 1,
        )
    )
    published_version = sibling.current_published_version if sibling else None
    if sibling is None or sibling.status != "published" or published_version is None:
        return SeriesNextView(next=None)
    # #ASSUME: security: the next book must pass the SAME read gate as any
    # direct open; reusing _load_readable_storybook keeps this route from
    # becoming a second, divergent access path. Expected absence maps a
    # sibling 403/404 to next=null, which also avoids an existence oracle
    # (unreadable and nonexistent answer identically).
    # #VERIFY: test_series_next_unassigned_catalog_sibling_is_null vs
    # test_series_next_assigned_catalog_sibling_returned.
    try:
        await _load_readable_storybook(ctx, sibling.id, parsed)
    except (AuthorizationError, ResourceNotFoundError):
        return SeriesNextView(next=None)
    version_row = await ctx.session.get(
        StorybookVersion, (sibling.id, published_version)
    )
    if version_row is None:
        return SeriesNextView(next=None)
    series_row = await ctx.session.get(Series, book.series_id)
    blob = version_row.blob
    title = blob.get("title")
    # #EDGE: data integrity: a pre-WS-G sibling blob carries no embedded
    # series block; the declared entry node is then unknown and the client
    # falls back to the document's start_node (identical in v1 by G2).
    # #VERIFY: test_series_next_legacy_sibling_has_null_entry_node.
    entry: str | None = None
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        series_block = metadata.get("series")
        if isinstance(series_block, dict):
            raw_entry = series_block.get("series_entry_node")
            if isinstance(raw_entry, str):
                entry = raw_entry
    return SeriesNextView(
        next=SeriesNextBook(
            storybook_id=sibling.id,
            version=published_version,
            title=title if isinstance(title, str) else "",
            series_entry_node=entry,
            carries_state=series_row.carries_state if series_row else False,
        )
    )
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `uv run pytest tests/integration/test_series_next.py -q`
Expected: all PASS.

- [ ] **Step 6: Lint, typecheck, targeted regression**

Run: `uv run ruff format src/cyo_adventure/api tests/integration/test_series_next.py && uv run ruff check src/cyo_adventure/api tests/integration/test_series_next.py && uv run basedpyright src/ && uv run pytest tests/integration/test_reading_state.py -q`
Expected: clean; reading-state suite unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/cyo_adventure/api/schemas.py src/cyo_adventure/api/reading.py tests/integration/test_series_next.py
git commit -S -m "feat(reading): add kid-scoped series-next endpoint (WS-G PR 2)"
```

---

### Task 2: Regenerate the API client

depends-on: Task1 [output]. Operational task.

- [ ] **Step 1: Dump the schema in-process and regenerate**

Run:

```bash
SCHEMA="$(mktemp --suffix=.json)"
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" > "$SCHEMA"
cd frontend && OPENAPI_INPUT="$SCHEMA" npm run generate-client && cd ..
rm -f "$SCHEMA"
```

Expected: `git status --short frontend/src/client` shows modified `types.gen.ts`/`sdk.gen.ts`
(and possibly `index.ts`) containing `SeriesNextView`/`SeriesNextBook`.
Abort if: no diff (regen silently hit the localhost default; re-check `OPENAPI_INPUT`).

- [ ] **Step 2: Frontend typecheck still green**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit ONLY the generated client**

```bash
git add frontend/src/client
git commit -S -m "feat(client): regenerate API client for series-next (WS-G PR 2)"
```

---

### Task 3: Player types fix, series helpers, startContinuation

depends-on: Task0 [completion] (parallel-safe with Tasks 1-2).

**Files:**

- Modify: `frontend/src/player/types.ts`
- Modify: `frontend/src/player/engine.ts`
- Create: `frontend/src/player/series.ts`
- Test: `frontend/src/player/engine.test.ts`, `frontend/src/player/series.test.ts` (new)

- [ ] **Step 1: Fix the Ending interface**

In `frontend/src/player/types.ts` replace the `Ending` interface (the `type` field is dead:
no code reads it, and blobs carry `kind`/`valence`; see Key facts item 4):

```typescript
export interface Ending {
  id: string
  kind: string
  valence: string
  title: string
}
```

Run: `cd frontend && npm run typecheck`
Expected: PASS (nothing consumed `type`).

- [ ] **Step 2: Write failing tests for the series helpers**

Create `frontend/src/player/series.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'

import { SATISFYING_ENDING_KINDS, parseContinuation, seriesMeta } from './series'
import type { Storybook } from './types'

const base: Storybook = {
  schema_version: '2.0',
  id: 's_x',
  version: 1,
  title: 'X',
  metadata: {},
  variables: [],
  start_node: 'n_a',
  nodes: [{ id: 'n_a', body: '', is_ending: true, ending: null, choices: [] }],
}

const block = {
  series_id: 'ser-1',
  book_index: 1,
  series_entry_node: 'n_a',
  is_final: false,
  carries_state: true,
}

describe('seriesMeta', () => {
  it('parses a well-formed embedded block', () => {
    const story = { ...base, metadata: { series: block } }
    expect(seriesMeta(story)).toEqual({
      seriesId: 'ser-1',
      bookIndex: 1,
      entryNode: 'n_a',
      isFinal: false,
      carriesState: true,
    })
  })

  it('returns null when metadata has no series block', () => {
    expect(seriesMeta(base)).toBeNull()
  })

  it('returns null when the block is malformed', () => {
    const story = { ...base, metadata: { series: { series_id: 7 } } }
    expect(seriesMeta(story)).toBeNull()
  })

  it('maps a missing entry node to null', () => {
    const story = {
      ...base,
      metadata: { series: { ...block, series_entry_node: undefined } },
    }
    expect(seriesMeta(story)?.entryNode).toBeNull()
  })
})

describe('SATISFYING_ENDING_KINDS', () => {
  it('matches the validator: success and completion only', () => {
    expect([...SATISFYING_ENDING_KINDS].sort()).toEqual(['completion', 'success'])
    expect(SATISFYING_ENDING_KINDS.has('discovery')).toBe(false)
  })
})

describe('parseContinuation', () => {
  it('parses a navigation-state continuation seed', () => {
    const state = { continuation: { entryNode: 'n_a', varState: { courage: 3 } } }
    expect(parseContinuation(state)).toEqual({ entryNode: 'n_a', varState: { courage: 3 } })
  })

  it('returns undefined for absent or malformed state', () => {
    expect(parseContinuation(null)).toBeUndefined()
    expect(parseContinuation({})).toBeUndefined()
    expect(parseContinuation({ continuation: 'nope' })).toBeUndefined()
  })

  it('defaults a missing entryNode to null', () => {
    expect(parseContinuation({ continuation: {} })).toEqual({
      entryNode: null,
      varState: undefined,
    })
  })
})
```

Run: `cd frontend && npx vitest run src/player/series.test.ts`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Implement `frontend/src/player/series.ts`**

```typescript
/**
 * Series-chaining helpers (WS-G): parse the embedded series block from a
 * story's loose metadata and define the reader-side continuation contract.
 * Kinds mirror the backend validator's _SATISFYING_KINDS (validator/series.py).
 */

import type { Storybook, VarState } from './types'

export interface SeriesMeta {
  seriesId: string
  bookIndex: number
  entryNode: string | null
  isFinal: boolean
  carriesState: boolean
}

/** Ending kinds that may offer "Continue the series" (spec section 1). */
export const SATISFYING_ENDING_KINDS: ReadonlySet<string> = new Set([
  'success',
  'completion',
])

/** Parse the embedded series block from story metadata, or null when absent/malformed. */
export function seriesMeta(story: Storybook): SeriesMeta | null {
  const block = (story.metadata as { series?: unknown }).series
  if (typeof block !== 'object' || block === null) return null
  const b = block as Record<string, unknown>
  if (typeof b.series_id !== 'string' || typeof b.book_index !== 'number') return null
  return {
    seriesId: b.series_id,
    bookIndex: b.book_index,
    entryNode: typeof b.series_entry_node === 'string' ? b.series_entry_node : null,
    isFinal: b.is_final === true,
    carriesState: b.carries_state === true,
  }
}

/** What a continuation navigation carries to the next book's reader. */
export interface ContinuationSeed {
  entryNode: string | null
  varState?: VarState
}

/**
 * Parse a router location.state into a ContinuationSeed, defensively: state
 * is attacker-shapeable via history manipulation, so every field is checked.
 * Carried var values are re-filtered by startContinuation (type and bounds),
 * so a forged varState can never seed an invalid value.
 */
export function parseContinuation(state: unknown): ContinuationSeed | undefined {
  if (typeof state !== 'object' || state === null) return undefined
  const c = (state as { continuation?: unknown }).continuation
  if (typeof c !== 'object' || c === null) return undefined
  const cc = c as Record<string, unknown>
  return {
    entryNode: typeof cc.entryNode === 'string' ? cc.entryNode : null,
    varState:
      typeof cc.varState === 'object' && cc.varState !== null
        ? (cc.varState as VarState)
        : undefined,
  }
}
```

Run: `cd frontend && npx vitest run src/player/series.test.ts`
Expected: PASS.

- [ ] **Step 4: Write failing tests for startContinuation**

Append to `frontend/src/player/engine.test.ts` (follow the file's existing story-fixture style;
build a local story with variables `courage` int 0..5 initial 0 and `brave` bool initial false,
whose entry node `n_two` has an on_enter `inc courage 1`):

```typescript
describe('startContinuation', () => {
  const story: Storybook = {
    schema_version: '2.0',
    id: 's_cont',
    version: 1,
    title: 'Continuation',
    metadata: {},
    variables: [
      { name: 'courage', type: 'int', initial: 0, min: 0, max: 5 },
      { name: 'brave', type: 'bool', initial: false },
    ],
    start_node: 'n_one',
    nodes: [
      { id: 'n_one', body: 'one', is_ending: false, choices: [] },
      {
        id: 'n_two',
        body: 'two',
        is_ending: false,
        on_enter: [{ op: 'inc', var: 'courage', value: 1 }],
        choices: [],
      },
    ],
  }

  it('starts at the entry node with seeded name-matched values', () => {
    const state = startContinuation(story, 'n_two', { courage: 2, brave: true, ghost: 9 })
    expect(state.current_node).toBe('n_two')
    expect(state.path).toEqual(['n_two'])
    // seeded 2, then n_two's on_enter inc applies on top
    expect(state.var_state).toEqual({ courage: 3, brave: true })
    expect(state.state_revision).toBe(0)
  })

  it('skips wrong-typed and non-integer carried values', () => {
    const state = startContinuation(story, 'n_one', { courage: true, brave: 3.5 })
    expect(state.var_state).toEqual({ courage: 0, brave: false })
  })

  it('clamps an out-of-bounds carried int to the declared bounds', () => {
    const state = startContinuation(story, 'n_one', { courage: 99 })
    expect(state.var_state.courage).toBe(5)
  })

  it('falls back to start_node for a null or unknown entry node', () => {
    expect(startContinuation(story, null, undefined).current_node).toBe('n_one')
    expect(startContinuation(story, 'n_missing', undefined).current_node).toBe('n_one')
  })

  it('without carried state behaves like start() at the entry node', () => {
    const state = startContinuation(story, 'n_two', undefined)
    expect(state.var_state).toEqual({ courage: 1, brave: false })
    expect(state.visit_set).toEqual(['n_two'])
  })
})
```

Run: `cd frontend && npx vitest run src/player/engine.test.ts`
Expected: FAIL (`startContinuation` is not exported).

- [ ] **Step 5: Implement startContinuation in `frontend/src/player/engine.ts`**

Add after `start()`:

```typescript
// #CRITICAL: data-integrity: a continuation state cannot be reproduced by
// replaying choices from start_node, so continuation saves MUST NOT carry a
// choice_path (the server would replay-from-start and reject them; see
// api/reading.py's note that choice_path may become required). The server's
// structural floor (player/replay.py::_check_structure) is what admits these
// saves, so this function must uphold its exact invariants: every declared
// variable present, values correctly typed and in-bounds (clamped below),
// current_node === path[path.length - 1], all node ids known.
// #VERIFY: engine.test.ts "startContinuation" describe block; if choice_path
// ever becomes required server-side, the server needs a continuation-aware
// replay mode first.
/** Begin a continuation read at a declared entry node, seeding name-matched
 * carried variables (WS-G decision G3). Wrong-typed carried values are
 * skipped (the declared initial stands); carried ints are clamped to the
 * variable's declared bounds. */
export function startContinuation(
  story: Storybook,
  entryNode: string | null,
  carriedVarState?: VarState
): ReadingState {
  const bounds = intBounds(story)
  const varState: VarState = {}
  for (const v of story.variables) {
    varState[v.name] = v.initial
    const carried = carriedVarState?.[v.name]
    if (carried === undefined) continue
    if (v.type === 'bool' && typeof carried === 'boolean') {
      varState[v.name] = carried
    } else if (v.type === 'int' && typeof carried === 'number' && Number.isInteger(carried)) {
      varState[v.name] = clamp(bounds, v.name, carried)
    }
  }
  const nodeId =
    entryNode !== null && story.nodes.some((n) => n.id === entryNode)
      ? entryNode
      : story.start_node
  const state: ReadingState = {
    current_node: nodeId,
    var_state: varState,
    path: [nodeId],
    visit_set: [],
    version: story.version,
    state_revision: 0,
    save_slots: {},
  }
  enterNode(story, state, nodeId, true, bounds)
  return state
}
```

- [ ] **Step 6: Run tests, verify pass, full frontend unit suite**

Run: `cd frontend && npx vitest run src/player && npm run test:run && npm run lint && npm run typecheck`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/player/types.ts frontend/src/player/engine.ts frontend/src/player/series.ts frontend/src/player/engine.test.ts frontend/src/player/series.test.ts
git commit -S -m "feat(player): startContinuation, series metadata helpers, honest Ending type (WS-G PR 2)"
```

---

### Task 4: series-next fetcher and ContinueSeries component

depends-on: Task2 [output] (generated `SeriesNextView` type), Task3 [output].

**Files:**

- Modify: `frontend/src/api/readerApi.ts`
- Create: `frontend/src/reader/ContinueSeries.tsx`
- Test: `frontend/src/reader/ContinueSeries.test.tsx` (new)

- [ ] **Step 1: Add the fetcher to readerApi.ts**

Follow the file's factory style; alias the generated type like the existing `ConflictBody` alias:

```typescript
import type { ConflictView, SeriesNextView } from '../client/types.gen'

/** The generated non-null payload of GET /v1/series-next (single source of truth). */
export type SeriesNextBookInfo = NonNullable<SeriesNextView['next']>

/**
 * Resolve the next readable book in a series for a profile. Returns null when
 * the server answers next: null (every expected absence). Errors propagate;
 * the caller treats any failure as "no continuation offered" (best-effort).
 */
export function makeFetchSeriesNext(
  api: AxiosInstance
): (profileId: string, storybookId: string) => Promise<SeriesNextBookInfo | null> {
  return async (profileId, storybookId) => {
    const res = await api.get<SeriesNextView>(`/v1/series-next/${profileId}/${storybookId}`)
    return res.data.next ?? null
  }
}
```

Note: if the generated field name differs (inspect `frontend/src/client/types.gen.ts` for
`SeriesNextView` after Task 2), align to the generated name; do not hand-write a shadow type.

- [ ] **Step 2: Write failing component tests**

Create `frontend/src/reader/ContinueSeries.test.tsx`. Follow `BackToLibrary.test.tsx` for the
navigation-assertion pattern (MemoryRouter + route probe or spy):

```tsx
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ContinueSeries } from './ContinueSeries'

afterEach(cleanup)

const NEXT = {
  storybook_id: 's_book2',
  version: 1,
  title: 'Book 2',
  series_entry_node: 'n_start',
  carries_state: true,
}

function Probe() {
  const location = useLocation()
  return (
    <p data-testid="probe">
      {location.pathname}|{JSON.stringify(location.state)}
    </p>
  )
}

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={['/end']}>
      <Routes>
        <Route path="/end" element={ui} />
        <Route path="/read/:profileId/:storybookId/:version" element={<Probe />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ContinueSeries', () => {
  it('shows the button when a next book resolves, and navigates with the seed', async () => {
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockResolvedValue(NEXT)}
        finalVarState={{ courage: 3 }}
        carriesState={true}
      />
    )
    const button = await screen.findByTestId('continue-series')
    fireEvent.click(button)
    const probe = await screen.findByTestId('probe')
    expect(probe.textContent).toContain('/read/p1/s_book2/1')
    expect(probe.textContent).toContain('"entryNode":"n_start"')
    expect(probe.textContent).toContain('"courage":3')
  })

  it('omits the carried var state for an episodic series', async () => {
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockResolvedValue(NEXT)}
        finalVarState={{ courage: 3 }}
        carriesState={false}
      />
    )
    fireEvent.click(await screen.findByTestId('continue-series'))
    const probe = await screen.findByTestId('probe')
    expect(probe.textContent).not.toContain('courage')
  })

  it('renders nothing when there is no next book', async () => {
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockResolvedValue(null)}
        finalVarState={{}}
        carriesState={true}
      />
    )
    await waitFor(() => {
      expect(screen.queryByTestId('continue-series')).toBeNull()
    })
  })

  it('renders nothing when the lookup fails', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockRejectedValue(new Error('boom'))}
        finalVarState={{}}
        carriesState={true}
      />
    )
    await waitFor(() => {
      expect(spy).toHaveBeenCalled()
    })
    expect(screen.queryByTestId('continue-series')).toBeNull()
    spy.mockRestore()
  })
})
```

Run: `cd frontend && npx vitest run src/reader/ContinueSeries.test.tsx`
Expected: FAIL (component does not exist).

- [ ] **Step 3: Implement `frontend/src/reader/ContinueSeries.tsx`**

```tsx
/**
 * "Continue the series" for the ending screen (WS-G decision G1): queries
 * series-next once on mount and, when a readable next book exists, offers a
 * jump to it carrying the continuation seed (entry node plus, for
 * state-carrying series, the finished book's final var_state) through router
 * location state. Absence of a button is the v1 answer to every miss.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@ds/components/Button'

import type { SeriesNextBookInfo } from '../api/readerApi'
import type { ContinuationSeed } from '../player/series'
import type { VarState } from '../player/types'

export interface ContinueSeriesProps {
  profileId: string
  storybookId: string
  fetchSeriesNext: (
    profileId: string,
    storybookId: string
  ) => Promise<SeriesNextBookInfo | null>
  finalVarState: VarState
  carriesState: boolean
}

export function ContinueSeries({
  profileId,
  storybookId,
  fetchSeriesNext,
  finalVarState,
  carriesState,
}: ContinueSeriesProps) {
  const navigate = useNavigate()
  const [next, setNext] = useState<SeriesNextBookInfo | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchSeriesNext(profileId, storybookId)
      .then((info) => {
        if (!cancelled) setNext(info)
      })
      .catch((error: unknown) => {
        // #EDGE: external-resources: continuation is best-effort; a failed
        // lookup must never break the ending screen. No button is the v1
        // fallback for every absence, including transport errors.
        // #VERIFY: ContinueSeries.test.tsx "renders nothing when the lookup fails".
        console.error('[reader] series-next lookup failed', {
          profileId,
          storybookId,
          error,
        })
      })
    return () => {
      cancelled = true
    }
  }, [fetchSeriesNext, profileId, storybookId])

  if (!next) return null
  const target = next
  const continueSeries = () => {
    const continuation: ContinuationSeed = {
      entryNode: target.series_entry_node ?? null,
      varState: carriesState ? finalVarState : undefined,
    }
    void navigate(`/read/${profileId}/${target.storybook_id}/${target.version}`, {
      state: { continuation },
    })
  }
  return (
    <Button variant="primary" size="lg" data-testid="continue-series" onClick={continueSeries}>
      Continue the series
    </Button>
  )
}
```

- [ ] **Step 4: Run tests, lint, typecheck; commit**

Run: `cd frontend && npx vitest run src/reader/ContinueSeries.test.tsx && npm run lint && npm run typecheck`
Expected: PASS.

```bash
git add frontend/src/api/readerApi.ts frontend/src/reader/ContinueSeries.tsx frontend/src/reader/ContinueSeries.test.tsx
git commit -S -m "feat(reader): series-next fetcher and ContinueSeries component (WS-G PR 2)"
```

---

### Task 5: Wire continuation through Reader, ReaderPage, ReaderRoute

depends-on: Task3 [output], Task4 [output].

**Files:**

- Modify: `frontend/src/reader/Reader.tsx`
- Modify: `frontend/src/reader/ReaderPage.tsx`
- Modify: `frontend/src/reader/ReaderRoute.tsx`
- Test: `frontend/src/reader/Reader.test.tsx`, `frontend/src/reader/ReaderPage.test.tsx`,
  `frontend/src/reader/ReaderRoute.test.tsx`

- [ ] **Step 1: Write failing Reader visibility tests**

Append to `Reader.test.tsx` (reuse the file's lantern fixture; the lantern's
`e_treasure_found` ending has kind `success`). Build series variants by spreading:

```tsx
const seriesBlock = {
  series_id: 'ser-1',
  book_index: 1,
  series_entry_node: 'n_entrance',
  is_final: false,
  carries_state: true,
}
const seriesStory = { ...lantern, metadata: { ...lantern.metadata, series: seriesBlock } }
const finalStory = {
  ...lantern,
  metadata: { ...lantern.metadata, series: { ...seriesBlock, is_final: true } },
}
const fetchNext = () =>
  Promise.resolve({
    storybook_id: 's_book2',
    version: 1,
    title: 'Book 2',
    series_entry_node: 'n_start',
    carries_state: true,
  })
```

Test cases (each drives the two clicks Reader.test.tsx already uses to reach the
`e_treasure_found` ending, then asserts on `continue-series`):

- series story + satisfying ending + `fetchSeriesNext` prop: `await screen.findByTestId('continue-series')` resolves.
- final book (`finalStory`): `queryByTestId('continue-series')` stays null.
- non-series story (`lantern`) with the prop: stays null.
- series story WITHOUT the prop: stays null.

Run: `cd frontend && npx vitest run src/reader/Reader.test.tsx`
Expected: new tests FAIL (prop not accepted / nothing rendered).

- [ ] **Step 2: Wire Reader.tsx**

Add to `ReaderProps`:

```tsx
  /** Resolves the next readable series book; when provided, a satisfying
   * ending of a non-final series book offers "Continue the series". */
  fetchSeriesNext?: (
    profileId: string,
    storybookId: string
  ) => Promise<SeriesNextBookInfo | null>
```

Imports: `SATISFYING_ENDING_KINDS, seriesMeta` from `../player/series`,
`ContinueSeries` from `./ContinueSeries`, `type SeriesNextBookInfo` from `../api/readerApi`.

In the ended branch (before the `return`):

```tsx
    const meta = seriesMeta(story)
    const showContinue =
      fetchSeriesNext !== undefined &&
      meta !== null &&
      !meta.isFinal &&
      SATISFYING_ENDING_KINDS.has(ending?.kind ?? '')
```

Inside `.reader-ending__actions`, after the Read again button:

```tsx
            {showContinue && meta && fetchSeriesNext ? (
              <ContinueSeries
                profileId={profileId}
                storybookId={story.id}
                fetchSeriesNext={fetchSeriesNext}
                finalVarState={reading.var_state}
                carriesState={meta.carriesState}
              />
            ) : null}
```

Run: `cd frontend && npx vitest run src/reader/Reader.test.tsx`
Expected: PASS.

- [ ] **Step 3: Write failing ReaderPage continuation tests**

Append to `ReaderPage.test.tsx`, following the file's existing mocking pattern for
`fetchStory`/`fetchServerState` and the offline/db module (read the file's existing setup first
and reuse its helpers verbatim; do not invent a parallel harness). Two tests:

- `seeds a fresh read from a continuation` : story with entry node `n_two` (reuse the Task 3
  fixture shape), `fetchServerState` resolves null, no local state,
  `continuation={{ entryNode: 'n_two', varState: { courage: 2 } }}`; assert the first
  `onProgress` reading has `current_node === 'n_two'` and the seeded var value (2 plus any
  on_enter effect the fixture applies).
- `ignores a continuation when saved progress exists`: `fetchServerState` resolves an existing
  state at `n_one`; same continuation prop; assert the reader resumes at `n_one` with the saved
  var_state (no seeding, no entry jump).

Run: `cd frontend && npx vitest run src/reader/ReaderPage.test.tsx`
Expected: new tests FAIL.

- [ ] **Step 4: Wire ReaderPage.tsx**

Props:

```tsx
  /** One-shot continuation seed for a fresh read (WS-G); ignored whenever any
   * saved progress exists (spec section 6 no-clobber rule). */
  continuation?: ContinuationSeed
  /** Forwarded to the Reader's ending screen. */
  fetchSeriesNext?: (
    profileId: string,
    storybookId: string
  ) => Promise<SeriesNextBookInfo | null>
```

Imports: `startContinuation` from `../player/engine`, `type ContinuationSeed` from
`../player/series`, `type SeriesNextBookInfo` from `../api/readerApi`.

In `load()`, replace the final two lines (`revisionRef.current = ...; setPageState(...)`) with:

```tsx
    revisionRef.current = saved?.state_revision ?? 0
    // #ASSUME: data-integrity: the continuation seed applies ONLY to a fresh
    // read (no local and no server state); any existing progress wins so a
    // re-continue can never clobber a child's place (WS-G spec section 6).
    // #VERIFY: ReaderPage.test.tsx "ignores a continuation when saved
    // progress exists".
    const initialReading =
      saved === undefined && continuation !== undefined
        ? startContinuation(cached, continuation.entryNode, continuation.varState)
        : saved
    setPageState({ phase: 'reading', story: cached, initialReading })
```

Add `continuation` to the `load` useCallback dependency array. Pass
`fetchSeriesNext={fetchSeriesNext}` to `<Reader />`.

Run: `cd frontend && npx vitest run src/reader/ReaderPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Wire ReaderRoute.tsx and add a route test**

In `ReaderRoute`:

```tsx
import { useLocation } from 'react-router-dom'  // extend the existing react-router-dom import
import { makeFetchSeriesNext } from '../api/readerApi'  // extend the existing readerApi import
import { parseContinuation } from '../player/series'
```

```tsx
  const location = useLocation()
  const continuation = useMemo(() => parseContinuation(location.state), [location.state])
  const fetchSeriesNext = useMemo(() => makeFetchSeriesNext(api), [api])
```

Pass `continuation={continuation}` and `fetchSeriesNext={fetchSeriesNext}` to `<ReaderPage />`.

Append one test to `ReaderRoute.test.tsx` (reuse its existing render harness): navigating to the
reader route with `state: { continuation: { entryNode: 'n_x', varState: { courage: 1 } } }`
renders ReaderPage with that continuation (assert indirectly via the same observable the file
already uses, or by mocking ReaderPage as the file's harness allows; if the harness mocks
ReaderPage, assert the prop).

Run: `cd frontend && npx vitest run src/reader && npm run lint && npm run typecheck && npm run test:run`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/reader/Reader.tsx frontend/src/reader/ReaderPage.tsx frontend/src/reader/ReaderRoute.tsx frontend/src/reader/Reader.test.tsx frontend/src/reader/ReaderPage.test.tsx frontend/src/reader/ReaderRoute.test.tsx
git commit -S -m "feat(reader): continue-the-series jump with continuation seeding (WS-G PR 2)"
```

---

### Task 6: Mocked-tier e2e

depends-on: Task5 [output].

**Files:**

- Create: `frontend/e2e/series-continue.spec.ts`

- [ ] **Step 1: Write the spec**

Model the route mocking on `frontend/e2e/reader.spec.ts` (auth_token init script, `page.route`
with `route.fulfill`). Two inline story blobs; book 2's start node has a choice whose condition
requires the carried variable, so seeding is observable in the UI:

```typescript
import { expect, test } from '@playwright/test'

const SERIES_ID = 'ser-e2e-1'

function seriesBlock(bookIndex: number, entry: string) {
  return {
    series_id: SERIES_ID,
    book_index: bookIndex,
    series_entry_node: entry,
    is_final: false,
    carries_state: true,
  }
}

const BOOK1 = {
  schema_version: '2.0',
  id: 's_ember_1',
  version: 1,
  title: 'Ember Trail 1',
  metadata: { series: seriesBlock(1, 'n_b1_start') },
  variables: [{ name: 'courage', type: 'int', initial: 0, min: 0, max: 5 }],
  start_node: 'n_b1_start',
  nodes: [
    {
      id: 'n_b1_start',
      body: 'The trail begins.',
      is_ending: false,
      choices: [
        {
          id: 'c_brave',
          label: 'Face the ember wolf',
          target: 'n_b1_end',
          effects: [{ op: 'set', var: 'courage', value: 3 }],
        },
      ],
    },
    {
      id: 'n_b1_end',
      body: 'You did it.',
      is_ending: true,
      ending: { id: 'e_b1_done', valence: 'positive', kind: 'success', title: 'Brave!' },
      choices: [],
    },
  ],
}

const BOOK2 = {
  schema_version: '2.0',
  id: 's_ember_2',
  version: 1,
  title: 'Ember Trail 2',
  metadata: { series: seriesBlock(2, 'n_b2_start') },
  variables: [{ name: 'courage', type: 'int', initial: 0, min: 0, max: 5 }],
  start_node: 'n_b2_start',
  nodes: [
    {
      id: 'n_b2_start',
      body: 'The trail continues.',
      is_ending: false,
      choices: [
        {
          id: 'c_carried',
          label: 'Roar with carried courage',
          target: 'n_b2_end',
          condition: { '>=': [{ var: 'courage' }, 2] },
        },
        { id: 'c_plain', label: 'Walk on', target: 'n_b2_end' },
      ],
    },
    {
      id: 'n_b2_end',
      body: 'Onward.',
      is_ending: true,
      ending: { id: 'e_b2_done', valence: 'positive', kind: 'success', title: 'Done' },
      choices: [],
    },
  ],
}

const SERIES_NEXT = {
  next: {
    storybook_id: 's_ember_2',
    version: 1,
    title: 'Ember Trail 2',
    series_entry_node: 'n_b2_start',
    carries_state: true,
  },
}

test.beforeEach(async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  await page.route('**/api/v1/storybooks/s_ember_1/**', (route) =>
    route.fulfill({ json: BOOK1 })
  )
  await page.route('**/api/v1/storybooks/s_ember_2/**', (route) =>
    route.fulfill({ json: BOOK2 })
  )
  await page.route('**/api/v1/series-next/**', (route) =>
    route.fulfill({ json: SERIES_NEXT })
  )
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    const body = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({
      status: 200,
      json: { ...body, state_revision: (body.state_revision as number) + 1 },
    })
  })
  await page.route('**/api/v1/completions', (route) =>
    route.fulfill({
      status: 200,
      json: {
        child_profile_id: 'child-a',
        storybook_id: 's_ember_1',
        version: 1,
        ending_id: 'e_b1_done',
        found_at: new Date().toISOString(),
      },
    })
  )
})

test('continues a series into the next book with carried state', async ({ page }) => {
  await page.goto('/read/child-a/s_ember_1/1')
  await expect(page.getByTestId('reader')).toBeVisible()
  await page.getByTestId('choice-c_brave').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()

  const continueButton = page.getByTestId('continue-series')
  await expect(continueButton).toBeVisible()
  await continueButton.click()

  // Book 2 opens at its entry node...
  await expect(page.getByTestId('passage-body')).toContainText('The trail continues.')
  // ...and the carried courage (3) makes the conditional choice visible.
  await expect(page.getByTestId('choice-c_carried')).toBeVisible()
})
```

The condition uses the evaluator's verified JSONLogic encoding
(`frontend/src/player/evaluator.ts`: `{ '>=': [{ var: name }, literal] }`; ordering operators
`<`, `<=`, `>`, `>=` plus `==`, `!=`, `and`, `or`, `!`, `var`).

- [ ] **Step 2: Run the mocked tier**

Run: `cd frontend && npx playwright test e2e/series-continue.spec.ts --project=chromium`
Expected: PASS (run `npx playwright install chromium` first if the browser is missing).

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/series-continue.spec.ts
git commit -S -m "test(e2e): mocked-tier series continuation flow (WS-G PR 2)"
```

---

### Task 7: Dev seed series and real-tier e2e

depends-on: Task1 [output] (block shape), Task5 [completion] (testids).

**Files:**

- Modify: `scripts/seed_dev_data.py`
- Test: `tests/integration/test_seed_dev_data.py`
- Create: `frontend/e2e-real/series-continue-real.spec.ts`

- [ ] **Step 1: Write the failing seed test**

Append to `tests/integration/test_seed_dev_data.py` (reuse the file's existing fixtures and
assertion style; read its existing tests first):

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_dev_data_seeds_series_chain(...) -> None:
    """The dev seed creates a two-book, state-carrying series for the dev profile."""
```

Assertions: one `Series` row titled "Ember Trail" with `carries_state=True`; storybooks
`s_dev_ember_1` and `s_dev_ember_2` published with `series_id` set and `book_index` 1 and 2;
each version blob has `blob["metadata"]["series"]["series_id"] == str(series.id)` and
`series_entry_node == blob["start_node"]`; both assigned to the dev profile. Follow the exact
fixture signature the existing tests in that file use.

Run: `uv run pytest tests/integration/test_seed_dev_data.py -q`
Expected: new test FAILS.

- [ ] **Step 2: Extend `scripts/seed_dev_data.py`**

Inside the guarded section (after the review-story block, before `await session.commit()`), add a
`_seed_series_chain(session, family_id, profile_id, guardian_id)` helper called there. Build the
two blobs inline (module-level `_series_blob(story_id, title, book_index, series_id)` function
following the Task 1 `_blob` shape but with 3 nodes and the `courage` variable, ids
`s_dev_ember_1`/`s_dev_ember_2`, entry = start_node, and the block's `series_id` set from the
just-flushed `Series` row). Insert `Series` (title "Ember Trail", age_band "10-13",
`carries_state=True`, created_by=guardian), two `Storybook` rows (published,
`current_published_version=1`, `series_id`, `book_index` 1/2), two `StorybookVersion` rows
(blob, `approved_by=guardian.id`, `published_at`), and two `StorybookAssignment` rows for the dev
profile. The existing guardian-existence early return remains the sole idempotency guard (same
`#ASSUME` as the surrounding loops); update the final `print` summary line.

Run: `uv run pytest tests/integration/test_seed_dev_data.py -q`
Expected: all PASS (including the existing idempotency test).

- [ ] **Step 3: Write the real-tier spec**

Create `frontend/e2e-real/series-continue-real.spec.ts` modeled on
`frontend/e2e-real/kid-reads.spec.ts` (same `requireBackend()` gate and login flow): the dev
reader opens `s_dev_ember_1`, plays to its satisfying ending, sees `continue-series`, clicks,
and lands in `s_dev_ember_2`'s first passage. Use the fixed ids from Step 2. Assert the
continue button and the book-2 passage text.

- [ ] **Step 4: Run what can run**

Run: `uv run pytest tests/integration/test_seed_dev_data.py -q && cd frontend && npm run typecheck`
Expected: PASS.
The real tier itself (`npm run test:e2e:real`) runs only against a local stack (Postgres +
seeded uvicorn) and is NOT in CI; run it if the stack is up, otherwise record in the PR body
that the real-tier spec awaits a local run.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_dev_data.py tests/integration/test_seed_dev_data.py frontend/e2e-real/series-continue-real.spec.ts
git commit -S -m "test(e2e): seed dev series chain and real-tier continuation spec (WS-G PR 2)"
```

---

### Task 8: CHANGELOG and full gates

depends-on: all prior tasks [completion].

- [ ] **Step 1: CHANGELOG entry**

Add under `## [Unreleased]` / `### Added` in `CHANGELOG.md`:

```markdown
- Series continuation runtime (WS-G PR 2): kid-scoped `GET /api/v1/series-next` endpoint,
  "Continue the series" on satisfying endings of non-final series books with entry-node jump
  and name-matched variable-state seeding for state-carrying series, regenerated API client,
  and chained-reading e2e coverage in both Playwright tiers.
```

- [ ] **Step 2: Full backend gates**

Run:

```bash
uv run pytest --cov=src --cov-fail-under=80 -q 2>&1 | tail -3
uv run ruff check .
uv run basedpyright src/
uv run bandit -c pyproject.toml -r src -q
```

Expected: all green, coverage >= 80 percent.

- [ ] **Step 3: Full frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run && npm run build && npx playwright test --project=chromium`
Expected: all green (the mocked e2e tier runs fully; the real tier is excluded by project).

- [ ] **Step 4: Contract drift self-check**

Re-run the Task 2 dump + regen and confirm `git diff --exit-code -- frontend/src/client`
exits 0 (no drift between the committed client and the final backend schema).

- [ ] **Step 5: Pre-commit and commit**

Run: `pre-commit run --all-files`
Expected: pass.

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): WS-G PR 2 continuation runtime entry"
```

## Self-review notes

- Spec section 4 clause coverage: series-next resolution incl. readability gate (Task 1),
  200-with-null semantics (Task 1 tests 2-5), Continue visibility rule satisfying+non-final
  (Task 5), entry-node jump honoring the declared field (Tasks 3/5), name-matched seeding with
  episodic skip (Tasks 3/4) and no-clobber (Task 5), client regen (Task 2), e2e both tiers
  (Tasks 6/7). Spec section 8 frontend bullets map to Tasks 3-5 tests.
- Every code fact this plan asserts was verified against the worktree on 2026-07-10, including
  the JSONLogic condition encoding, the `ending.kind`/`valence` blob fields, the dead
  `Ending.type` field (zero usages), the structural-floor invariants, and the test fixtures
  (`Seed` fields, `sessions`, `auth`, `_series_utils.py`, `test_seed_dev_data.py`).
- Out of scope here (PR 3): `AnchorContext` variable names and continuation prompts.
