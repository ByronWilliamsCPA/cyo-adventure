---
schema_type: planning
title: "WS-E Implementation Plan: Catalog and Guardian Assignment"
description: "Task-level implementation plan for WS-E: Storybook.visibility set at release approval,
  guardian catalog browse and assign, server-side visibility checks, family-scoped assignment
  reads, frontend approval toggle and catalog badges, migration gated on WS-C PR2."
tags:
  - planning
  - authorization
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an engineer with zero context every file path, code block, command, and expected
  output needed to implement WS-E task by task."
component: Strategy
source: "docs/planning/ws-e-catalog-spec.md (E1-E5 + E-mig ratified 2026-07-09); codebase
  discovery 2026-07-09 against feat/ws-e-catalog-assignment @ b15ed15."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Admin-approved books become shareable to a global catalog: a `visibility` column on `Storybook`
chosen at release approval, guardian browse widened to family-plus-catalog, and a server-side
visibility check on assignment so a child is never assigned a book their guardian cannot see.

## Architecture

One new string-enum column (`Storybook.visibility`, `family`/`catalog`), threaded through the
single publish path (`publishing/service.py::approve`), three read/write endpoints in
`api/assignments.py`, and the approval endpoint in `api/approval.py`. Frontend adds a
family/catalog radio to the approve dialog and a catalog badge to the guardian books list. The
Alembic migration chains onto WS-C PR2's head `228c68e8f1e7` (ratified decision E-mig) and is
therefore GATED until WS-C PR2 is on `origin/main`.

## Tech Stack

FastAPI + async SQLAlchemy 2.x + Alembic + Pydantic v2 (backend); React 19 + Vite + TS + Vitest +
Playwright (frontend); pytest + testcontainers Postgres (integration tests).

## Deviations from the spec discovered during planning (authoritative)

1. **`released` event carries NO payload today.** `events/writer.py:33` pins
   `EventType.RELEASED: frozenset()` in `_PAYLOAD_ALLOWLIST`. The spec's "the event already
   carries visibility" is wrong. Task 2 extends the allowlist to `frozenset({"visibility"})`.
2. **Cross-family profile-id leak must be prevented.** Three code paths read the GLOBAL
   `StorybookAssignment` set for a book and return or project the profile ids
   (`api/assignments.py:226`, `:282`, `:438`). For catalog books this would leak other
   families' child profile UUIDs. Tasks 4 and 5 scope every returned assignment set to the
   caller's family via a `ChildProfile.family_id` join. This is a `#CRITICAL security` item.
3. **`_require_guardian_family_book` is shared** by `assign_storybook` AND `list_assignments`;
   both are intentionally widened (a guardian assigning a catalog book must read its own-family
   assignment set). `_authorize_content_summary` (used by the assign dialog) must also be
   widened or assigning a catalog book breaks in the UI. Task 6 covers it.

## Preconditions and coordination

- Worktree: `/home/byron/dev/CYO_Adventure/.worktrees/ws-e`, branch `feat/ws-e-catalog-assignment`
  cut from `origin/main` @ `b15ed15`. Backend env already synced (`uv sync --all-extras`).
  Frontend needs `cd frontend && npm install` once (worktrees do not share `node_modules`).
- **Task 10 (migration) is EXTERNALLY GATED**: it requires WS-C PR2 (migration `228c68e8f1e7`)
  merged to `origin/main` first, then `git merge origin/main` into this branch. All other tasks
  proceed now; app-level integration tests use `Base.metadata.create_all`, not Alembic, so the
  suite stays green without the migration file. Do NOT add the migration file before the gate
  passes: a `down_revision` pointing at a revision absent from `migrations/versions/` breaks the
  entire Alembic revision map and every migration test in the branch.
- Repo process: signed commits (`git commit -S`), Conventional Commits, no em-dash characters,
  stage only files you changed (`git add <paths>`), CHANGELOG entry (Task 11).

## File structure

| File | Change |
| --- | --- |
| `src/cyo_adventure/publishing/state_machine.py` | Add `Visibility` StrEnum (app-boundary type, mirrors `Status`) |
| `src/cyo_adventure/db/models.py` | `_STORYBOOK_VISIBILITY_VALUES`, `ck_storybook_visibility`, `Storybook.visibility` column |
| `src/cyo_adventure/events/writer.py` | `RELEASED` payload allowlist gains `visibility` |
| `src/cyo_adventure/publishing/service.py` | `approve()` gains keyword-only `visibility`, stamps column, event payload |
| `src/cyo_adventure/api/schemas.py` | `ApproveBody` (new), `ApprovedView.visibility`, `GuardianBookItem.visibility` |
| `src/cyo_adventure/api/approval.py` | Endpoint accepts optional body, returns visibility |
| `src/cyo_adventure/api/assignments.py` | Visibility gate helper, widened listing WHERE, family-scoped assignment reads, content-summary widening |
| `migrations/versions/20260709_1500_add_storybook_visibility.py` | New (Task 10, gated) |
| `tests/integration/test_approval_api.py` | Approve-with-visibility tests |
| `tests/integration/test_guardian_books_api.py` | Catalog listing + scoping tests |
| `tests/integration/test_assignments_api.py` | Catalog assign/deny + scoping tests |
| `tests/integration/test_pipeline_event_instrumentation.py` | Released-event payload assertion |
| `tests/integration/test_storybook_visibility_migration.py` | New (Task 10, gated) |
| `tests/unit/test_visibility.py` | New enum unit test |
| `frontend/src/guardian/assignApi.ts` | `GuardianBookItem.visibility` |
| `frontend/src/guardian/BooksPage.tsx` (+ its CSS) | Catalog badge |
| `frontend/src/guardian/reviewApi.ts` | `approve(id, visibility)`, `ApprovedResult.visibility` |
| `frontend/src/guardian/ReviewDetailPage.tsx` | Family/catalog radio in approve dialog |
| `frontend/src/guardian/BooksPage.test.tsx`, `ReviewDetailPage.test.tsx` | Unit tests |
| `frontend/e2e/guardian-books.spec.ts`, `frontend/e2e/assignments.spec.ts` | Fixture + flow updates |
| `frontend/src/client/*` | Regenerated (Task 7) |
| `CHANGELOG.md` | Unreleased > Added entry |

---

### Task 1: Visibility enum and ORM column

**Files:**

- Modify: `src/cyo_adventure/publishing/state_machine.py` (after the `Status` enum, ~line 42)
- Modify: `src/cyo_adventure/db/models.py` (constant ~line 53, `Storybook` class ~line 192)
- Create: `tests/unit/test_visibility.py`

- [ ] **Step 1: Write the failing unit test**

```python
"""Unit tests for the Visibility app-boundary enum (WS-E, decision E1)."""

from __future__ import annotations

import pytest

from cyo_adventure.publishing.state_machine import Visibility


def test_visibility_values_are_closed() -> None:
    """The enum holds exactly the two ratified visibility states."""
    assert {v.value for v in Visibility} == {"family", "catalog"}


def test_visibility_rejects_unknown_value() -> None:
    """Coercing an unmodeled string raises rather than silently authorizing."""
    with pytest.raises(ValueError, match="public"):
        Visibility("public")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_visibility.py -v`
Expected: FAIL with `ImportError: cannot import name 'Visibility'`

- [ ] **Step 3: Add the enum to `publishing/state_machine.py`** (directly after the `Status` class)

```python
class Visibility(StrEnum):
    """Who may browse and assign a published book (WS-E, decision E1).

    Chosen by the admin at release approval and stored on ``storybook.visibility``.
    ``family`` restricts the book to its owning family; ``catalog`` shares it with
    every family's guardian browse-and-assign surface. Coercing the ORM string
    through ``Visibility(...)`` rejects any value outside this closed set.
    """

    FAMILY = "family"
    CATALOG = "catalog"
```

- [ ] **Step 4: Add the column to `db/models.py`**

Next to `_STORYBOOK_STATUS_VALUES` (~line 53) add:

```python
_STORYBOOK_VISIBILITY_VALUES = "'family', 'catalog'"
```

In `Storybook.__table_args__` (after `ck_storybook_status`) add:

```python
        CheckConstraint(
            f"visibility IN ({_STORYBOOK_VISIBILITY_VALUES})",
            name="ck_storybook_visibility",
        ),
```

After the `status` column declaration add (import `text` from `sqlalchemy` if not present):

```python
    # #CRITICAL: security: ``visibility`` widens who can browse/assign this book
    # (WS-E decision E1/E5); the CHECK is the at-rest backstop and the app
    # boundary coerces through publishing.state_machine.Visibility.
    # #VERIFY: Visibility(storybook.visibility) raises on any value outside the set.
    visibility: Mapped[str] = mapped_column(
        String(16), default="family", server_default=text("'family'")
    )
```

- [ ] **Step 5: Run tests and type checks**

Run: `uv run pytest tests/unit/test_visibility.py -v && uv run ruff check src/ tests/unit/test_visibility.py && uv run basedpyright src/cyo_adventure/db/models.py src/cyo_adventure/publishing/state_machine.py`
Expected: PASS, no lint or type errors

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/publishing/state_machine.py src/cyo_adventure/db/models.py tests/unit/test_visibility.py
git commit -S -m "feat(db): add Storybook.visibility column and Visibility enum (WS-E E1)"
```

---

### Task 2: Thread visibility through approve() and the released event

`depends-on: Task1 [output]`

**Files:**

- Modify: `src/cyo_adventure/events/writer.py:33`
- Modify: `src/cyo_adventure/publishing/service.py:111-190` (the `approve` function)
- Test: `tests/integration/test_pipeline_event_instrumentation.py`

- [ ] **Step 1: Find the existing released-event test**

Run: `grep -n "released" tests/integration/test_pipeline_event_instrumentation.py | head`
Expected: a test named like `test_approve_writes_released_event` (referenced by the RAD marker in
`publishing/service.py`). Read the test to reuse its seeding helpers.

- [ ] **Step 2: Extend that test (failing first)**

In the existing released-event test, after the event-row assertions, add:

```python
    assert event.payload == {"visibility": "family"}
```

And add a sibling test in the same file, reusing the file's existing seed helper and imports
(match its local naming exactly; the shape below shows the assertions that matter):

```python
async def test_approve_with_catalog_visibility_stamps_event_payload(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Approving with visibility=catalog records it on the released event."""
    story_id = await _seed_in_review(sessions)  # use this file's seed helper name
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth("admin-a"),
        json={"visibility": "catalog"},
    )
    assert resp.status_code == 200, resp.text
    async with sessions() as session:
        event = (
            await session.scalars(
                select(PipelineEvent).where(
                    PipelineEvent.event_type == "released",
                    PipelineEvent.entity_id == story_id,
                )
            )
        ).one()
    assert event.payload == {"visibility": "catalog"}
```

Note: this test also exercises Task 3's endpoint body; it stays red until Task 3 lands. That is
expected; run only the first (default-payload) assertion's test at this task's Step 3 if you want
a green checkpoint, and re-run both after Task 3.

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/integration/test_pipeline_event_instrumentation.py -k released -v`
Expected: FAIL on the payload assertion (payload is `{}` or NULL today)

- [ ] **Step 4: Extend the payload allowlist** in `events/writer.py:33`:

```python
    EventType.RELEASED: frozenset({"visibility"}),
```

- [ ] **Step 5: Thread visibility through `approve()`** in `publishing/service.py`.

Change the signature (add the import `from cyo_adventure.publishing.state_machine import Visibility`
style to match the file's existing imports; `Status`/`Action` are already imported from
`.state_machine`, so extend that import):

```python
async def approve(
    session: AsyncSession,
    principal: Principal,
    storybook: Storybook,
    version: int,
    *,
    visibility: Visibility = Visibility.FAMILY,
) -> StorybookVersion:
```

Add to the docstring Args: `visibility: Who may browse/assign the published book (WS-E E2);
defaults to family.`

After `storybook.current_published_version = version` add:

```python
    # #CRITICAL: security: visibility is stamped ONLY here, inside the sole
    # publish path, so the release transition and the sharing decision are
    # atomic (WS-E decision E2). A catalog value widens who can assign this
    # book (E5); it must never be settable outside an admin-gated approve.
    # #VERIFY: api/approval.py is the only caller and is admin-only.
    storybook.visibility = visibility.value
```

Change the `record_event(...)` call to pass the payload:

```python
        event_type=EventType.RELEASED,
        from_state="in_review",
        to_state="published",
        payload={"visibility": visibility.value},
```

- [ ] **Step 6: Run the default-visibility test**

Run: `uv run pytest tests/integration/test_pipeline_event_instrumentation.py -k released -v`
Expected: the pre-existing released test PASSES with `{"visibility": "family"}`; the new
catalog test still fails (endpoint body lands in Task 3).

- [ ] **Step 7: Check for allowlist-enumerating unit tests**

Run: `grep -rn "RELEASED" tests/unit/ | head`
Expected: if a unit test enumerates `_PAYLOAD_ALLOWLIST` keys for RELEASED, update it to
`frozenset({"visibility"})`; if none, proceed.

- [ ] **Step 8: Commit**

```bash
git add src/cyo_adventure/events/writer.py src/cyo_adventure/publishing/service.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(publishing): stamp visibility at approve and on the released event (WS-E E2)"
```

---

### Task 3: Approval endpoint accepts visibility

`depends-on: Task2 [output]`

**Files:**

- Modify: `src/cyo_adventure/api/schemas.py` (`ApprovedView` ~line 768; add `ApproveBody` near it)
- Modify: `src/cyo_adventure/api/approval.py` (`approve_storybook` ~line 119)
- Test: `tests/integration/test_approval_api.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/integration/test_approval_api.py`,
reusing its `_seed_in_review` helper and `auth`):

```python
async def test_approve_default_visibility_is_family(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Approving without a body publishes with visibility=family."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["visibility"] == "family"
    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        assert book.visibility == "family"


async def test_approve_with_catalog_visibility_sets_column(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Approving with visibility=catalog stamps the column and the response."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth("admin-a"),
        json={"visibility": "catalog"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["visibility"] == "catalog"
    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        assert book.visibility == "catalog"


async def test_approve_rejects_unknown_visibility(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An unmodeled visibility value is a 422, not a silent default."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth("admin-a"),
        json={"visibility": "public"},
    )
    assert resp.status_code == 422, resp.text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_approval_api.py -k visibility -v`
Expected: FAIL (KeyError `visibility` in response / 200-vs-422)

- [ ] **Step 3: Add `ApproveBody` and extend `ApprovedView`** in `api/schemas.py`:

```python
class ApproveBody(BaseModel):
    """Optional approve-time release options (WS-E decision E2).

    ``visibility`` defaults to ``family`` so an approve with no body keeps the
    pre-WS-E behavior; ``catalog`` shares the book with every family.
    """

    visibility: Literal["family", "catalog"] = "family"
```

And add to `ApprovedView` (after `published_at`):

```python
    visibility: Literal["family", "catalog"]
```

- [ ] **Step 4: Thread through the endpoint** in `api/approval.py`. Extend the imports
(`ApproveBody` from `.schemas`; `Visibility` from `..publishing.state_machine` matching the
file's relative-import style). Change the handler:

```python
@router.post("/storybooks/{storybook_id}/approve")
async def approve_storybook(
    storybook_id: str, ctx: Context, body: ApproveBody | None = None
) -> ApprovedView:
    """Approve and publish the latest version of an in-review story (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    version = await _latest_version(ctx.session, storybook_id)
    # #ASSUME: data integrity: a missing body means visibility=family (the
    # pre-WS-E contract); ApproveBody's Literal rejects unmodeled values at 422.
    # #VERIFY: test_approve_rejects_unknown_visibility.
    visibility = Visibility(body.visibility) if body is not None else Visibility.FAMILY
    version_row = await approval_service.approve(
        ctx.session, ctx.principal, book, version, visibility=visibility
    )
```

and extend the return:

```python
    return ApprovedView(
        id=book.id,
        status=cast("Literal['published']", book.status),
        current_published_version=version,
        approved_by=str(version_row.approved_by),
        published_at=version_row.published_at,
        visibility=cast("Literal['family', 'catalog']", book.visibility),
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/integration/test_approval_api.py tests/integration/test_pipeline_event_instrumentation.py -v`
Expected: ALL PASS, including Task 2's catalog event test and every pre-existing approval test
(they post no body and must keep passing)

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/api/schemas.py src/cyo_adventure/api/approval.py tests/integration/test_approval_api.py
git commit -S -m "feat(api): accept visibility on approve and return it (WS-E E2)"
```

---

### Task 4: Guardian listing widens to catalog, with family-scoped assignment sets

`depends-on: Task1 [output]` (parallel-safe with Task 3)

**Files:**

- Modify: `src/cyo_adventure/api/schemas.py` (`GuardianBookItem` ~line 318)
- Modify: `src/cyo_adventure/api/assignments.py` (`_guardian_book_item` ~line 307, `list_guardian_books` ~line 372)
- Test: `tests/integration/test_guardian_books_api.py`

- [ ] **Step 1: Read the existing test file's seed helpers**

Run: `grep -n "def \|Seed\|visibility" tests/integration/test_guardian_books_api.py | head -30`
Expected: seed helpers creating two families (the file asserts cross-family exclusion today).
Reuse them; where a helper creates a `Storybook`, it will now need `visibility="catalog"` for the
new cases (the column defaults to `family` otherwise).

- [ ] **Step 2: Write the failing tests** (append; adapt helper names to the file's own):

```python
async def test_catalog_book_from_other_family_is_listed_with_badge(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A published catalog book owned by family B appears in family A's browse."""
    # Seed a published+approved book for the OTHER family with visibility=catalog,
    # using this file's existing published-book seed helper, then:
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    books = {b["storybook_id"]: b for b in resp.json()["books"]}
    assert "catalog-book" in books
    assert books["catalog-book"]["visibility"] == "catalog"
    assert books[seed.storybook_id]["visibility"] == "family"


async def test_other_family_private_book_stays_hidden(
    client: AsyncClient, seed: Seed
) -> None:
    """Family B's visibility=family book never appears in family A's browse."""
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    ids = [b["storybook_id"] for b in resp.json()["books"]]
    # the fixture's other-family book has default visibility=family
    assert all(i != "other-family-book" for i in ids)


async def test_catalog_book_assignment_set_is_family_scoped(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """assigned_profile_ids on a catalog book excludes other families' children.

    #CRITICAL security regression guard: without the ChildProfile.family_id
    join, family B's child profile UUIDs would leak into family A's browse.
    """
    # Seed: catalog book owned by family B, assigned to BOTH families' children
    # (insert StorybookAssignment rows directly via the session).
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    books = {b["storybook_id"]: b for b in resp.json()["books"]}
    assert books["catalog-book"]["assigned_profile_ids"] == [
        str(seed.child_profile_id)
    ]
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/integration/test_guardian_books_api.py -k catalog -v`
Expected: FAIL (catalog book absent from the listing; no `visibility` key)

- [ ] **Step 4: Extend `GuardianBookItem`** in `api/schemas.py` (after `age_band`):

```python
    visibility: Literal["family", "catalog"]
```

- [ ] **Step 5: Widen the query and scope the bulk assignment load** in
`api/assignments.py::list_guardian_books`. Add `or_` to the existing `sqlalchemy` import and
`ChildProfile` to the models import and `Visibility` to the state-machine import.

Replace the WHERE clause (line ~426):

```python
            .where(
                or_(
                    Storybook.family_id == ctx.principal.family_id,
                    Storybook.visibility == Visibility.CATALOG.value,
                ),
                Storybook.status == _PUBLISHED,
                Storybook.current_published_version.is_not(None),
                StorybookVersion.approved_by.is_not(None),
            )
```

Update the `#CRITICAL security` comment above it: family isolation for `family` books is the
`or_` clause's first arm; `catalog` books are globally browsable BY DESIGN (WS-E decision E3).

Replace the bulk assignment load (lines ~438-447):

```python
    # #CRITICAL: security: scope the assignment projection to the CALLER's
    # family. A catalog book may be assigned by many families; projecting the
    # global set would leak other families' child profile UUIDs (WS-E plan
    # deviation 2). #VERIFY: test_catalog_book_assignment_set_is_family_scoped.
    assign_rows = await ctx.session.execute(
        select(
            StorybookAssignment.storybook_id,
            StorybookAssignment.child_profile_id,
        )
        .join(
            ChildProfile,
            StorybookAssignment.child_profile_id == ChildProfile.id,
        )
        .where(
            StorybookAssignment.storybook_id.in_(book_ids),
            ChildProfile.family_id == ctx.principal.family_id,
        )
    )
    assigned: dict[str, list[str]] = {}
    for assignment_storybook_id, child_profile_id in assign_rows:
        assigned.setdefault(assignment_storybook_id, []).append(str(child_profile_id))
```

- [ ] **Step 6: Project visibility** in `_guardian_book_item` (add `cast` import if the file
lacks it; `typing.cast` is already used in `approval.py` style):

```python
        visibility=cast("Literal['family', 'catalog']", book.visibility),
```

(added to the `GuardianBookItem(...)` constructor call, after `age_band=`).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/integration/test_guardian_books_api.py -v`
Expected: ALL PASS (new catalog tests plus every pre-existing exclusion/badge test)

- [ ] **Step 8: Commit**

```bash
git add src/cyo_adventure/api/schemas.py src/cyo_adventure/api/assignments.py tests/integration/test_guardian_books_api.py
git commit -S -m "feat(api): widen guardian browse to catalog books with family-scoped assignment sets (WS-E E3)"
```

---

### Task 5: Assignment visibility gate and scoped assignment responses

`depends-on: Task4 [output]` (same file; serialize after Task 4)

**Files:**

- Modify: `src/cyo_adventure/api/assignments.py` (`_require_guardian_family_book` ~line 67, `assign_storybook` ~line 191, `list_assignments` ~line 264)
- Test: `tests/integration/test_assignments_api.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/integration/test_assignments_api.py`;
the module already imports `Seed`, `auth`, and the ORM models):

```python
async def test_guardian_assigns_other_family_catalog_book(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A guardian may assign a catalog book owned by another family (E5)."""
    async with sessions() as session:
        other_fam = Family(name="Catalog Owner")
        session.add(other_fam)
        await session.flush()
        session.add(
            Storybook(
                id="catalog-assignable",
                family_id=other_fam.id,
                status="published",
                current_published_version=1,
                visibility="catalog",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="catalog-assignable",
                version=1,
                blob={"id": "catalog-assignable", "title": "Shared"},
                moderation_report=make_clean_moderation_report(),
                approved_by=seed.admin_user_id,
                published_at=datetime.now(UTC),
            )
        )
        await session.commit()
    resp = await client.post(
        "/api/v1/storybooks/catalog-assignable/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["profile_ids"] == [str(seed.child_profile_id)]


async def test_guardian_cannot_assign_other_family_private_book(
    client: AsyncClient, seed: Seed
) -> None:
    """Another family's visibility=family book stays 403 (E5 negative arm)."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.other_guardian_token),
        json={"profile_ids": [str(seed.other_child_profile_id)]},
    )
    assert resp.status_code == 403, resp.text


async def test_catalog_assignment_listing_is_family_scoped(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """GET assignments on a catalog book excludes other families' profile ids.

    #CRITICAL security regression guard for the profile-UUID leak (plan
    deviation 2): assign from BOTH families, then each family's GET must see
    only its own children.
    """
    # seed a catalog book as in test_guardian_assigns_other_family_catalog_book,
    # id "catalog-scoped"; then assign from both guardians:
    for token, pid in (
        (seed.guardian_token, seed.child_profile_id),
        (seed.other_guardian_token, seed.other_child_profile_id),
    ):
        resp = await client.post(
            "/api/v1/storybooks/catalog-scoped/assignments",
            headers=auth(token),
            json={"profile_ids": [str(pid)]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["profile_ids"] == [str(pid)]  # POST response scoped too
    mine = await client.get(
        "/api/v1/storybooks/catalog-scoped/assignments",
        headers=auth(seed.guardian_token),
    )
    assert mine.json()["profile_ids"] == [str(seed.child_profile_id)]
    theirs = await client.get(
        "/api/v1/storybooks/catalog-scoped/assignments",
        headers=auth(seed.other_guardian_token),
    )
    assert theirs.json()["profile_ids"] == [str(seed.other_child_profile_id)]
```

Note: `seed.storybook_id` has default `visibility="family"`, which is exactly what the negative
test needs. Keep the pre-existing `test_cross_family_guardian_gets_403` untouched; it must still
pass (same book, now denied by the visibility gate instead of `authorize_family`).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_assignments_api.py -k catalog -v`
Expected: FAIL with 403 on the catalog assign (cross-family check still absolute)

- [ ] **Step 3: Rewrite the shared gate.** Rename `_require_guardian_family_book` to
`_require_guardian_visible_book` (two call sites: `assign_storybook` line ~215,
`list_assignments` line ~281; plus the RAD comment at ~278-280) and replace its body:

```python
async def _require_guardian_visible_book(ctx: Context, storybook_id: str) -> Storybook:
    """Return the storybook after guardian-only and visibility checks.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path.

    Returns:
        Storybook: A story that is either owned by the guardian's family or
            shared to the catalog.

    Raises:
        AuthorizationError: If the caller is not a guardian, or the story is
            neither own-family nor catalog (403).
        ResourceNotFoundError: If the story does not exist (404).
    """
    # #CRITICAL: security: E5's server-side visibility gate; the UI badge is a
    # convenience, never the gate. Guard order is unchanged from the pre-WS-E
    # helper: guardian-only (403) -> missing (404) -> visibility (403). A
    # cross-family book is assignable ONLY when visibility='catalog'; the
    # child read gate (StorybookAssignment in library.py) is untouched.
    # #VERIFY: test_guardian_assigns_other_family_catalog_book (allow) and
    # test_guardian_cannot_assign_other_family_private_book (deny).
    if not ctx.principal.is_guardian:
        msg = "only a guardian may manage assignments"
        raise AuthorizationError(msg)
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if (
        book.family_id != ctx.principal.family_id
        and book.visibility != Visibility.CATALOG.value
    ):
        msg = "storybook is not visible to this family"
        raise AuthorizationError(msg, resource=storybook_id)
    return book
```

Drop the now-unused `authorize_family` import ONLY if `_authorize_content_summary` (Task 6) no
longer uses it either; check with `grep -n authorize_family src/cyo_adventure/api/assignments.py`
after Task 6.

- [ ] **Step 4: Scope both assignment reads.** Add a module-level helper (near
`_assignment_list`, ~line 57):

```python
def _family_assignment_ids_stmt(
    storybook_id: str, family_id: uuid.UUID
) -> Select[tuple[uuid.UUID]]:
    """Select the book's assigned profile ids belonging to one family.

    #CRITICAL: security: every assignment set returned to a guardian must be
    scoped to their own family; a catalog book's global set would leak other
    families' child profile UUIDs (WS-E plan deviation 2).
    #VERIFY: test_catalog_assignment_listing_is_family_scoped.
    """
    return (
        select(StorybookAssignment.child_profile_id)
        .join(
            ChildProfile,
            StorybookAssignment.child_profile_id == ChildProfile.id,
        )
        .where(
            StorybookAssignment.storybook_id == storybook_id,
            ChildProfile.family_id == family_id,
        )
    )
```

(`from sqlalchemy import Select` for the annotation; follow the file's import grouping. `uuid` is
already imported wherever `parse_uuid` results are typed; verify with `grep -n "^import uuid" src/cyo_adventure/api/assignments.py`
and add if missing.)

In `assign_storybook`, replace the `existing = set(...)` read (lines ~226-232) with:

```python
    existing = set(
        await ctx.session.scalars(
            _family_assignment_ids_stmt(storybook_id, ctx.principal.family_id)
        )
    )
```

(Idempotency is preserved: this guardian can only insert own-family profile ids, and any
pre-existing row for those ids is in the scoped set. The PK-collision `#EDGE` note above the read
still holds.)

In `list_assignments`, replace the `rows = await ctx.session.scalars(...)` read (lines ~282-286)
with:

```python
    rows = await ctx.session.scalars(
        _family_assignment_ids_stmt(storybook_id, ctx.principal.family_id)
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/integration/test_assignments_api.py tests/unit/test_assignments_api_unit.py -v`
Expected: ALL PASS, including the untouched `test_cross_family_guardian_gets_403`

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/api/assignments.py tests/integration/test_assignments_api.py
git commit -S -m "feat(api): visibility-gated assignment with family-scoped assignment sets (WS-E E5)"
```

---

### Task 6: Content summary readable for catalog books

`depends-on: Task5 [output]` (same file)

**Files:**

- Modify: `src/cyo_adventure/api/assignments.py` (`_authorize_content_summary` ~line 99)
- Test: `tests/integration/test_assignments_api.py` (or the file housing existing content-summary tests; locate with `grep -rln "content-summary" tests/integration/`)

- [ ] **Step 1: Write the failing tests** (append next to the existing content-summary tests,
seeding a catalog book exactly as in Task 5 Step 1):

```python
async def test_guardian_reads_catalog_book_content_summary(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The assign dialog's summary fetch works for another family's catalog book."""
    # seed catalog book id "catalog-summary" owned by another family (Task 5 pattern)
    resp = await client.get(
        "/api/v1/storybooks/catalog-summary/content-summary",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text


async def test_guardian_cannot_read_private_cross_family_summary(
    client: AsyncClient, seed: Seed
) -> None:
    """A cross-family visibility=family book's summary stays 403."""
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/content-summary",
        headers=auth(seed.other_guardian_token),
    )
    assert resp.status_code == 403, resp.text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/ -k "content_summary and catalog" -v` (adjust `-k` to the
new test names)
Expected: FAIL with 403 on the catalog summary

- [ ] **Step 3: Widen the gate.** In `_authorize_content_summary`, replace lines ~133-134:

```python
    # #CRITICAL: security: a guardian may read a cross-family summary ONLY for a
    # catalog-shared book (WS-E E3: the assign dialog needs the badge detail for
    # anything assignable); a family-visibility book keeps the family gate. An
    # admin remains global. #VERIFY: catalog summary 200 / private cross-family 403.
    if not ctx.principal.is_admin and book.visibility != Visibility.CATALOG.value:
        authorize_family(ctx.principal, book.family_id)
```

- [ ] **Step 4: Run tests, then the full backend suite checkpoint**

Run: `uv run pytest tests/integration/test_assignments_api.py -v && uv run pytest -q`
Expected: ALL PASS (full suite; nothing else reads these gates)

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/api/assignments.py tests/integration/test_assignments_api.py
git commit -S -m "feat(api): allow catalog-book content summaries cross-family (WS-E E3)"
```

---

### Task 7: Regenerate the OpenAPI client

`depends-on: Task3, Task6 [completion]` (backend schema final)

**Files:**

- Modify: `frontend/src/client/*` (generated; never hand-edit)

- [ ] **Step 1: One-time frontend setup in this worktree**

Run: `cd frontend && npm install`
Expected: clean install (lockfile untouched)

- [ ] **Step 2: Dump the schema in-process and regenerate** (mirrors `.github/workflows/ci.yml`
lines ~221-247; NEVER sort keys):

```bash
cd /home/byron/dev/CYO_Adventure/.worktrees/ws-e
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" > /tmp/ws-e-openapi.json
cd frontend && OPENAPI_INPUT=/tmp/ws-e-openapi.json npm run generate-client
```

Expected: `frontend/src/client/types.gen.ts` diff shows `visibility` on `GuardianBookItem` and
`ApprovedView`, plus the new `ApproveBody` type.
Abort if: the diff touches unrelated endpoints wholesale (a sorted or reordered dump; do not
commit, re-dump without sorting).

- [ ] **Step 3: Verify drift-gate parity**

Run: `git status --short frontend/src/client && cd frontend && npm run typecheck`
Expected: only expected generated diffs; typecheck passes

- [ ] **Step 4: Commit**

```bash
git add frontend/src/client
git commit -S -m "chore(frontend): regenerate OpenAPI client for visibility fields (WS-E)"
```

---

### Task 8: Guardian books UI shows catalog badge

`depends-on: Task4 [completion], Task7 [completion]`

**Files:**

- Modify: `frontend/src/guardian/assignApi.ts` (`GuardianBookItem` interface)
- Modify: `frontend/src/guardian/BooksPage.tsx` (~lines 167-185 row markup)
- Modify: the stylesheet defining `books__*` classes (locate: `grep -rn "books__list" frontend/src --include="*.css"`)
- Test: `frontend/src/guardian/BooksPage.test.tsx`

- [ ] **Step 1: Write the failing test** (follow the file's existing `routeGet`/fixture pattern;
add `visibility: 'family'` to existing fixture items so they stay type-correct, and one catalog
item):

```typescript
it('badges catalog books and not family books', async () => {
  routeGet([
    { ...BOOK, storybook_id: 's-fam', title: 'Ours', visibility: 'family' },
    { ...BOOK, storybook_id: 's-cat', title: 'Shared', visibility: 'catalog' },
  ])
  renderPage()
  const shared = (await screen.findByText('Shared')).closest('li')
  expect(shared).not.toBeNull()
  expect(within(shared as HTMLElement).getByText('Catalog')).toBeInTheDocument()
  const ours = screen.getByText('Ours').closest('li')
  expect(within(ours as HTMLElement).queryByText('Catalog')).not.toBeInTheDocument()
})
```

(Adapt `routeGet`'s parameterization to the file's actual helper; if it takes no argument, add an
optional books parameter defaulting to the current fixture.)

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/guardian/BooksPage.test.tsx`
Expected: FAIL (type error on `visibility` first; then missing badge)

- [ ] **Step 3: Add the field** in `assignApi.ts` `GuardianBookItem` (after `age_band`):

```typescript
  visibility: 'family' | 'catalog'
```

- [ ] **Step 4: Render the badge** in `BooksPage.tsx` next to the title span (~line 169):

```tsx
{book.visibility === 'catalog' && (
  <span className="books__catalog-badge">Catalog</span>
)}
```

Add a style block to the stylesheet housing `books__*` (match its naming and spacing scale):

```css
.books__catalog-badge {
  margin-left: 0.5rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  background: var(--color-accent-soft, #eef2ff);
  color: var(--color-accent, #3730a3);
}
```

(If the stylesheet has an existing pill/badge utility class, reuse it instead of new CSS.)

- [ ] **Step 5: Run tests**

Run: `cd frontend && npx vitest run src/guardian/BooksPage.test.tsx && npm run lint && npm run typecheck`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/guardian/assignApi.ts frontend/src/guardian/BooksPage.tsx frontend/src/guardian/BooksPage.test.tsx <stylesheet path>
git commit -S -m "feat(frontend): catalog badge on the guardian books list (WS-E E3)"
```

---

### Task 9: Approve dialog gains the family/catalog choice

`depends-on: Task3 [completion], Task7 [completion]` (parallel-safe with Task 8)

**Files:**

- Modify: `frontend/src/guardian/reviewApi.ts` (approve signature ~line 116, `ApprovedResult` ~line 58)
- Modify: `frontend/src/guardian/ReviewDetailPage.tsx` (approve dialog ~lines 355-387)
- Test: `frontend/src/guardian/ReviewDetailPage.test.tsx`

- [ ] **Step 1: Write the failing tests** (the file's existing approve test asserts
`mockPost.toHaveBeenCalledWith('/v1/storybooks/s1/approve')`; update it and add the catalog case):

```typescript
it('approves with family visibility by default', async () => {
  const user = userEvent.setup()
  mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
  renderAt('s1')
  await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
  await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
  expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
    visibility: 'family',
  })
})

it('approves to the catalog when the admin selects it', async () => {
  const user = userEvent.setup()
  mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
  renderAt('s1')
  await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
  await user.click(
    await screen.findByRole('radio', { name: /Catalog/i })
  )
  await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
  expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
    visibility: 'catalog',
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/guardian/ReviewDetailPage.test.tsx`
Expected: FAIL (post called without a body; no radio present)

- [ ] **Step 3: Extend the adapter** in `reviewApi.ts`:

```typescript
export type Visibility = 'family' | 'catalog'
```

`ApprovedResult` gains `visibility: Visibility` (the closed union above, never a bare
`string`, so the response type keeps the same compile-time guarantee as the request
side). The interface method and implementation become:

```typescript
  approve(storybookId: string, visibility: Visibility): Promise<ApprovedResult>
```

```typescript
    async approve(
      storybookId: string,
      visibility: Visibility
    ): Promise<ApprovedResult> {
      const res = await api.post<ApprovedResult>(
        `/v1/storybooks/${storybookId}/approve`,
        { visibility }
      )
      return res.data
    },
```

- [ ] **Step 4: Add the radio group to the approve dialog** in `ReviewDetailPage.tsx`. State near
the dialog's existing state hooks:

```typescript
const [visibility, setVisibility] = useState<Visibility>('family')
```

Inside the approve-confirm dialog (before the confirm button; mirror the fieldset/radio pattern
from `ProfileFormDialog.tsx` lines ~143-165):

```tsx
<fieldset className="review-detail__visibility">
  <legend>Who can see this book?</legend>
  <label>
    <input
      type="radio"
      name="visibility"
      checked={visibility === 'family'}
      onChange={() => setVisibility('family')}
    />
    This family only
  </label>
  <label>
    <input
      type="radio"
      name="visibility"
      checked={visibility === 'catalog'}
      onChange={() => setVisibility('catalog')}
    />
    Catalog (every family)
  </label>
  {visibility === 'catalog' && (
    <p className="review-detail__visibility-warning">
      Catalog books are visible to every family. Confirm the story contains
      no names, photos, or personal details before sharing.
    </p>
  )}
</fieldset>
```

Confirm handler becomes `reviewApi.approve(storybookId, visibility)`. Reset `visibility` to
`'family'` when the dialog opens (in `openDialog('approve')` or equivalent) so a second approval
does not inherit the previous choice.

- [ ] **Step 5: Run tests**

Run: `cd frontend && npx vitest run src/guardian/ReviewDetailPage.test.tsx && npm run lint && npm run typecheck && npm run test:run`
Expected: PASS (full unit suite; other specs touching approve must still pass)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/guardian/reviewApi.ts frontend/src/guardian/ReviewDetailPage.tsx frontend/src/guardian/ReviewDetailPage.test.tsx
git commit -S -m "feat(frontend): family/catalog visibility choice at approve (WS-E E2)"
```

---

### Task 10: Alembic migration and round-trip tests (EXTERNALLY GATED)

`depends-on: Task1 [completion]; HARD GATE: WS-C PR2 merged to origin/main`

**Files:**

- Create: `migrations/versions/20260709_1500_add_storybook_visibility.py`
- Create: `tests/integration/test_storybook_visibility_migration.py`

- [ ] **Step 1: Gate check (abort if it fails)**

Run: `git fetch origin && git cat-file -e origin/main:migrations/versions/20260709_0900_add_storybook_version_skeleton_slug.py && echo GATE-OPEN`
Expected: `GATE-OPEN` (WS-C PR2's migration is on main)
Abort if: the command errors. Do NOT create the migration file yet; complete other tasks and
re-check later. (Ratified decision E-mig: WS-E chains onto `228c68e8f1e7` and merges second.)

- [ ] **Step 2: Merge main and confirm the head**

Run: `git merge origin/main` then `grep -rn "228c68e8f1e7" migrations/versions/*.py`
Expected: clean merge (CHANGELOG conflict possible; resolve keeping both sides); exactly ONE hit,
a `revision: str = "228c68e8f1e7"` line in the skeleton_slug migration, and NO file lists it as a
`down_revision` (it is the head). If WS-C PR2 was re-keyed before merging, run the repo's
head-detection drill (the revision no other file names as its `down_revision`) and use that id
everywhere below instead.

- [ ] **Step 3: Write the migration**

```python
"""Add storybook.visibility for the guardian catalog (WS-E, decision E1).

Revision ID: 9c4e7d2a5b18
Revises: 228c68e8f1e7
Create Date: 2026-07-09 15:00:00
"""

from __future__ import annotations

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4e7d2a5b18"
down_revision: Union[str, Sequence[str], None] = "228c68e8f1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the visibility column; existing rows backfill to 'family'."""
    op.add_column(
        "storybook",
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'family'"),
        ),
    )
    op.create_check_constraint(
        "ck_storybook_visibility",
        "storybook",
        "visibility IN ('family', 'catalog')",
    )


def downgrade() -> None:
    """Drop the visibility constraint and column."""
    op.drop_constraint("ck_storybook_visibility", "storybook", type_="check")
    op.drop_column("storybook", "visibility")
```

(Match the header-comment style of `20260709_1000_add_provider_model_allowlist.py`; the import
order above follows those files. Adjust `Revises:` and `down_revision` if Step 2 found a
different merged id.)

- [ ] **Step 4: Write the migration tests** (mirror
`tests/integration/test_storybook_version_provider_migration.py` exactly: three tests):

```python
"""Migration round-trip for storybook.visibility (WS-E, decision E1)."""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

# Pinned ids per repo convention (see test_assignments_migration.py):

_PREV_HEAD = "228c68e8f1e7"
_VISIBILITY_HEAD = "9c4e7d2a5b18"


@pytest.mark.integration
def test_visibility_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains to head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_storybook_visibility*.py"))
    assert files, f"visibility migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_visibility_migration", files[0])
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert callable(getattr(mod, "upgrade", None))
    assert callable(getattr(mod, "downgrade", None))
    assert mod.down_revision == _PREV_HEAD


@pytest.mark.integration
def test_visibility_migration_upgrade_downgrade(migration_pg_url: str) -> None:
    """alembic upgrade then downgrade of the visibility revision succeed."""
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}
    up = run_alembic(PROJECT_ROOT, env, "upgrade", _VISIBILITY_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    down = run_alembic(PROJECT_ROOT, env, "downgrade", _PREV_HEAD)
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_existing_rows_backfill_to_family(migration_pg_url: str) -> None:
    """A storybook row inserted before the migration reads visibility='family'."""
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}
    up = run_alembic(PROJECT_ROOT, env, "upgrade", _PREV_HEAD)
    assert up.returncode == 0, f"upgrade to prev failed:\n{up.stdout}\n{up.stderr}"
    fam_id = str(uuid.uuid4())
    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO family (id, name) VALUES (:id, 'Legacy Fam')"),
                {"id": fam_id},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO storybook (id, family_id, status) "
                    "VALUES ('legacy-book', :fam, 'published')"
                ),
                {"fam": fam_id},
            )
        up2 = run_alembic(PROJECT_ROOT, env, "upgrade", _VISIBILITY_HEAD)
        assert up2.returncode == 0, f"upgrade failed:\n{up2.stdout}\n{up2.stderr}"
        async with engine.connect() as conn:
            row = await conn.execute(
                sa.text("SELECT visibility FROM storybook WHERE id = 'legacy-book'")
            )
            assert row.scalar_one() == "family"
    finally:
        await engine.dispose()
```

(If the `family` table's columns differ at `_PREV_HEAD`, adapt the INSERT: check with
`grep -n "op.create_table" migrations/versions/*family*.py` or the earliest migration.)

- [ ] **Step 5: Run the migration tests**

Run: `uv run pytest tests/integration/test_storybook_visibility_migration.py -v`
Expected: 3 PASS
Also run: `uv run pytest tests/integration/ -k migration -q`
Expected: every other pinned round-trip still passes (the new head does not retarget them)

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/20260709_1500_add_storybook_visibility.py tests/integration/test_storybook_visibility_migration.py
git commit -S -m "feat(db): alembic migration for storybook.visibility (WS-E E1, chains on WS-C PR2)"
```

---

### Task 11: e2e (mocked tier) coverage

`depends-on: Task8, Task9 [completion]`

**Files:**

- Modify: `frontend/e2e/guardian-books.spec.ts` (BOOKS fixture ~lines 62-74; new test)
- Modify: `frontend/e2e/assignments.spec.ts` (fixture parity)
- Check-only: `frontend/e2e/library.spec.ts`, `frontend/e2e/guardian-console.spec.ts` (update only if they assert guardian-book shapes)

- [ ] **Step 1: Add `visibility` to every guardian-book fixture item** in both spec files
(`visibility: 'family'` for existing items) so mocked responses match the real contract.

- [ ] **Step 2: Add the catalog browse-and-assign e2e test** to `guardian-books.spec.ts`
(same route-interception pattern as the existing test at lines ~95-117):

```typescript
test('guardian sees a catalog badge and assigns a shared book', async ({ page }) => {
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: ME }))
  await page.route('**/api/v1/guardian/books', (route) =>
    route.fulfill({
      json: {
        books: [
          {
            storybook_id: 'story-cat',
            title: 'The Shared Lantern',
            version: 1,
            age_band: '10-13',
            screened: true,
            flagged_count: 0,
            assigned_profile_ids: [],
            visibility: 'catalog',
          },
        ],
      },
    })
  )
  let body: unknown = null
  await page.route('**/api/v1/storybooks/story-cat/assignments', (route) => {
    if (route.request().method() === 'POST') {
      body = route.request().postDataJSON()
      return route.fulfill({
        json: { storybook_id: 'story-cat', profile_ids: ['p1'] },
      })
    }
    return route.fulfill({
      json: { storybook_id: 'story-cat', profile_ids: [] },
    })
  })
  // reuse this spec's existing navigation + profiles mocks verbatim
  await page.goto('/guardian/books')
  await expect(page.getByText('Catalog')).toBeVisible()
  // drive the existing assign dialog for profile p1, then:
  await expect.poll(() => body).toEqual({ profile_ids: ['p1'] })
})
```

(Reuse the file's `ME`/profiles fixtures and its dialog-driving steps verbatim; the excerpt shows
the WS-E-specific parts. Mock `**/api/v1/storybooks/story-cat/content-summary` too if the dialog
fetches it; copy the shape from the existing test's summary mock.)

- [ ] **Step 3: Run the e2e suite**

Run: `cd frontend && npx playwright test e2e/ --workers=1`
Expected: ALL PASS (rate limiter requires `--workers=1` per repo convention)

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/guardian-books.spec.ts frontend/e2e/assignments.spec.ts
git commit -S -m "test(e2e): catalog badge and shared-book assignment flow (WS-E)"
```

---

### Task 12: CHANGELOG and full gate run

`depends-on: all previous [completion]`

- [ ] **Step 1: CHANGELOG entry** under `## [Unreleased]` > `### Added` (create the subsection if
absent; match the existing prose style):

```markdown
- Story catalog: at release approval an admin now chooses whether a book stays
  family-only or joins the shared catalog (`visibility` on `Storybook`). Guardian
  browse lists catalog books from every family with a "Catalog" badge, and
  assignment enforces visibility server-side: any guardian may assign a catalog
  book, while another family's private book stays 403. Assignment sets returned
  to a guardian are always scoped to their own family's children. Admin-initiated
  catalog-origin requests are deferred (#173).
```

- [ ] **Step 2: Full backend gates**

Run: `uv run pytest --cov=src --cov-fail-under=80 -q && uv run ruff check . && uv run basedpyright src/ && uv run bandit -r src -q`
Expected: all pass, coverage >= 80%

- [ ] **Step 3: Full frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run && npm run build`
Expected: all pass

- [ ] **Step 4: Pre-commit over the branch**

Run: `pre-commit run --all-files`
Expected: all hooks pass (no em-dash, frontmatter, secrets, formatting)

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): WS-E catalog and guardian assignment entry"
```

---

### Task 13: Child read paths honor catalog visibility (added post-final-review, owner-ratified)

`depends-on: Task5 [completion]`

**Files:**

- Modify: `src/cyo_adventure/api/library.py` (`list_library` WHERE ~line 288; `get_storybook_version` family check ~line 388)
- Modify: `src/cyo_adventure/api/ratings.py` (`record_rating` family check ~line 69)
- Test: the integration files covering library and ratings (locate with `grep -rln "list_library\|/library\|record_rating\|/ratings" tests/integration/`)

**Why:** the final whole-branch review confirmed an assigned cross-family catalog book was
invisible to the child (family filter alongside the assignment gate). Owner ratified fixing in
WS-E. The `StorybookAssignment` gate stays REQUIRED for child reads; only the family filters
widen.

- [ ] **Step 1: Write the failing tests** (adapt seeding to each file's local helpers; the
      behavioral assertions are verbatim requirements):

  - Child of family A, assigned a family-B `visibility='catalog'` published+approved book:
    the book appears in `GET /api/v1/library/{profile_id}` AND
    `GET /api/v1/storybooks/{id}/versions/{v}` returns the blob (200) AND
    `POST /api/v1/ratings` for it returns 200.
  - Same child, UNASSIGNED family-B catalog book: absent from the listing, blob fetch 404
    (existence hidden), rating 403.
  - Cross-family `family`-visibility book: still absent / 403-or-404 exactly as before
    (regression guard; do not weaken existing tests).

- [ ] **Step 2: Run to verify failure** (listing missing / blob 403 / rating 403)

- [ ] **Step 3: `list_library`**: replace the family filter (library.py:288) with

```python
            or_(
                Storybook.family_id == principal.family_id,
                Storybook.visibility == Visibility.CATALOG.value,
            ),
```

(add `or_` to the sqlalchemy import and `Visibility` to the state-machine import), and update
the adjacent #CRITICAL/#VERIFY comment: catalog books are listable when assigned; the EXISTS
assignment clause is unchanged and remains the gate.

- [ ] **Step 4: `get_storybook_version`**: the family check (library.py:388-389) becomes

```python
    if not principal.is_admin and book.visibility != Visibility.CATALOG.value:
        authorize_family(principal, book.family_id)
```

The non-admin published/approved/current 404 gate and the child assignment gate below it stay
untouched (they already apply to catalog books). Update the #CRITICAL comment: a catalog book is
readable cross-family (guardian preview parity with content-summary; child still needs the
assignment row).

- [ ] **Step 5: `record_rating`**: replace `authorize_family(ctx.principal, book.family_id)`
      (ratings.py:69) with

```python
    if book.family_id != ctx.principal.family_id:
        # #CRITICAL: security: cross-family rating is allowed ONLY for a catalog
        # book that is actually assigned to this profile; an unassigned catalog
        # book is not ratable (prevents drive-by ratings polluting suggestion
        # data), and a family-visibility book stays fully blocked (IDOR guard).
        # #VERIFY: catalog+assigned -> 200; catalog+unassigned -> 403;
        # cross-family family-visibility -> 403.
        if book.visibility != Visibility.CATALOG.value:
            authorize_family(ctx.principal, book.family_id)
        else:
            assigned = await ctx.session.scalar(
                select(StorybookAssignment.storybook_id).where(
                    StorybookAssignment.storybook_id == book.id,
                    StorybookAssignment.child_profile_id == profile_id,
                )
            )
            if assigned is None:
                msg = "storybook is not accessible to this profile"
                raise AuthorizationError(msg, resource=book.id)
```

(imports: `select` if absent, `StorybookAssignment`, `Visibility`.)

- [ ] **Step 6: Run the touched test files plus**
      `uv run pytest tests/integration/test_assignments_api.py tests/integration/test_guardian_books_api.py -q`
      Expected: ALL PASS

- [ ] **Step 7: CHANGELOG amendment**: extend the WS-E Unreleased entry's final sentence
      (before "Admin-initiated") with: "Children can read and rate an assigned catalog book
      from another family; unassigned catalog books stay hidden from child accounts."

- [ ] **Step 8: Commit**

```bash
git add src/cyo_adventure/api/library.py src/cyo_adventure/api/ratings.py CHANGELOG.md <test files>
git commit -S -m "fix(api): child read and rating paths honor catalog visibility (WS-E E5 amendment)"
```

## Post-plan process (not tasks)

Per the ratified process: subagent-driven development with per-task reviews, then an Opus
whole-branch review BEFORE opening the PR. PR is owner-gated, merge queue only, and merges AFTER
WS-C PR2 (decision E-mig). If WS-C PR2 is abandoned or re-keyed, re-point Task 10's
`down_revision` and `_PREV_HEAD` to the live main head.

## Test traceability (spec clause -> task)

| Spec clause | Task |
| --- | --- |
| Migration round-trip + existing rows default family | 10 |
| Listing returns catalog + own-family, never foreign family-visibility | 4 |
| Guardian assigns catalog book they do not own | 5 |
| Guardian cannot assign foreign family-visibility book (403) | 5 |
| Child read gate unchanged | 5 (no library.py change; existing suite is the guard) |
| Approve with catalog sets column + event payload; default family | 2, 3 |
| e2e catalog browse-and-assign | 11 |
| Assignment sets never leak foreign profile ids (plan deviation 2) | 4, 5 |
| Content summary follows visibility (plan deviation 3) | 6 |
