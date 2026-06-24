---
title: "Ratings (Phase A) Implementation Plan"
schema_type: planning
status: draft
owner: core-maintainer
component: Development-Tools
source: "docs/superpowers/specs/2026-06-23-ratings-and-family-sharing-design.md"
purpose: >-
  Implement Phase A of the ratings and family-sharing design: a child rates a
  finished storybook 1-5, stored per-child-per-book, mutable, family-scoped.
  Backend-only vertical slice (model, migration, schemas, endpoints, tests,
  client regen). Phase B (sharing) is a separate plan.
tags:
  - planning
  - development
  - specifications
authors:
  - name: "Byron Williams"
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal

A child can rate a storybook in their own family 1-5, change that rating later, and read back their ratings, all behind the existing family/profile authorization.

## Architecture

A new `rating` table mirrors the per-child grain of the existing `Completion` table, but at the coarser `(child_profile_id, storybook_id)` level (a rating is about the book, not a specific immutable version) and is **mutable** (re-rating overwrites). A new focused router `api/ratings.py` exposes an upsert `POST /ratings` and a `GET /ratings/{profile_id}` list, reusing the existing `Context` unit-of-work dependency and the `authorize_profile` / `authorize_family` gates. No business logic touches the `Family` boundary; ratings are strictly family-scoped.

## Tech Stack

FastAPI (async), SQLAlchemy 2.x async ORM, Pydantic v2 (`ConfigDict(extra="forbid")`), Alembic (async, autogenerate-based), pytest + pytest-asyncio with testcontainers Postgres. Frontend client is generated from OpenAPI via `@hey-api/openapi-ts`.

## Scope

In scope: backend model, migration, schemas, two endpoints, full unit + integration tests, and a regenerated frontend API client. Out of scope (deferred to follow-up plans): the kid-facing rating **widget** (stars vs faces is an undecided UI call per the spec), a DELETE/un-rate endpoint, and all of Phase B (connected families, sharing, visible relative ratings).

## Deliberate divergences from the `Completion` precedent (do not "fix" these)

- **Grain:** `rating` keys on `(child_profile_id, storybook_id)` with a plain FK to `storybook`, NOT the composite `(storybook_id, version)` FK to `storybook_version` that `Completion` uses. A rating is about the book; this grain is also what Phase B's lineage join needs.
- **Mutability:** `POST /ratings` is an **upsert** (re-rating overwrites `value` and bumps `updated_at`), unlike `record_completion` which is insert-once-idempotent.

---

## Task 1: Add the `Rating` ORM model

**Files:**
- Modify: `src/cyo_adventure/db/models.py` (add a class after `Completion`, which ends at line 183)
- Test: `tests/unit/test_rating_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_rating_model.py`:

```python
"""Unit tests for the Rating ORM model registration."""

from __future__ import annotations

from cyo_adventure.core.database import Base


def test_rating_table_registered() -> None:
    """The rating table is registered with the expected PK and columns."""
    table = Base.metadata.tables["rating"]
    assert set(table.primary_key.columns.keys()) == {
        "child_profile_id",
        "storybook_id",
    }
    for col in ("value", "rated_at", "updated_at"):
        assert col in table.columns


def test_rating_storybook_fk_targets_storybook() -> None:
    """storybook_id is a plain FK to storybook.id (not storybook_version)."""
    table = Base.metadata.tables["rating"]
    fk_targets = {fk.target_fullname for fk in table.foreign_keys}
    assert "storybook.id" in fk_targets
    assert "child_profile.id" in fk_targets
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_rating_model.py -v`
Expected: FAIL with `KeyError: 'rating'` (table not registered yet).

- [ ] **Step 3: Add the model**

In `src/cyo_adventure/db/models.py`, add this class immediately after the `Completion` class (after line 183). All needed imports (`uuid`, `datetime`, `ForeignKey`, `String`, `Uuid`, `func`, `Mapped`, `mapped_column`, `_TS`, `_FK_CHILD_PROFILE`, `_FK_STORYBOOK`) already exist in the file.

```python
class Rating(Base):
    """A child's 1-5 rating of a storybook.

    Unlike ``Completion``, which pins to an immutable ``storybook_version`` via a
    composite FK, a rating is about the *book* as a whole and is **mutable**: a
    child may re-rate, overwriting the prior value. The coarser
    ``(child_profile_id, storybook_id)`` grain is also what the cross-family
    lineage join in Phase B will need.
    """

    __tablename__ = "rating"

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(
        ForeignKey(_FK_STORYBOOK), primary_key=True
    )
    # #ASSUME: data integrity: ``value`` is constrained to 1-5 by the RatingBody
    # Pydantic model at the API boundary; the column itself stores any integer.
    # #VERIFY: every write path goes through RatingBody validation before insert.
    value: Mapped[int] = mapped_column()
    rated_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_rating_model.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/db/models.py tests/unit/test_rating_model.py
git commit -S -m "feat(db): add Rating model (per-child, per-book, mutable)"
```

---

## Task 2: Add the Alembic migration for `rating`

depends-on: Task 1 [output] (the migration mirrors the model's table shape)

**Files:**
- Create: `migrations/versions/20260623_1200_add_rating_table.py`

This repo's current Alembic head is `78336bfff81e` (verified via the `revision`/`down_revision` chain in `migrations/versions/`). The new migration chains onto it. The file content is given explicitly below so it does not depend on autogenerate having a live DB.

- [ ] **Step 1: Create the migration file**

Create `migrations/versions/20260623_1200_add_rating_table.py`:

```python
"""add rating table

Revision ID: a1b2c3d4e5f6
Revises: 78336bfff81e
Create Date: 2026-06-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '78336bfff81e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('rating',
    sa.Column('child_profile_id', sa.Uuid(), nullable=False),
    sa.Column('storybook_id', sa.String(length=120), nullable=False),
    sa.Column('value', sa.Integer(), nullable=False),
    sa.Column('rated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_profile_id'], ['child_profile.id'], ),
    sa.ForeignKeyConstraint(['storybook_id'], ['storybook.id'], ),
    sa.PrimaryKeyConstraint('child_profile_id', 'storybook_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('rating')
```

- [ ] **Step 2: Verify the revision chain has a single head**

Run: `uv run alembic heads`
Expected: exactly one head, `a1b2c3d4e5f6 (head)`. (This reads the migration files only; no database connection required.)
Abort if: more than one head is printed (means the file's `down_revision` is wrong).

- [ ] **Step 3 (conditional): Apply the migration if a dev DB is available**

If a local Postgres is running (e.g. `docker compose up -d db`), apply and round-trip the migration:

Run: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: no errors; the `rating` table is created, dropped, recreated.
Abort if: any Alembic error. If no dev DB is available, skip this step (the integration tests in later tasks build the schema from `Base.metadata.create_all`, so they do not depend on this migration).

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/20260623_1200_add_rating_table.py
git commit -S -m "feat(db): add rating table migration"
```

---

## Task 3: Add the rating request/response schemas

**Files:**
- Modify: `src/cyo_adventure/api/schemas.py` (append after the existing `Completion` schemas, the file ends near line 144)
- Test: `tests/unit/test_rating_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_rating_schemas.py`:

```python
"""Unit tests for rating request schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cyo_adventure.api.schemas import RatingBody


def test_rating_body_accepts_valid() -> None:
    body = RatingBody(profile_id="p", storybook_id="s", value=3)
    assert body.value == 3


def test_rating_body_rejects_zero() -> None:
    with pytest.raises(ValidationError):
        RatingBody(profile_id="p", storybook_id="s", value=0)


def test_rating_body_rejects_above_five() -> None:
    with pytest.raises(ValidationError):
        RatingBody(profile_id="p", storybook_id="s", value=6)


def test_rating_body_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RatingBody(profile_id="p", storybook_id="s", value=3, surprise="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_rating_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'RatingBody'`.

- [ ] **Step 3: Add the schemas**

In `src/cyo_adventure/api/schemas.py`, append the following. The file already imports `datetime`, `BaseModel`, `ConfigDict`, and `Field` (used by `CompletionBody`/`CompletionView`); reuse those imports.

```python
class RatingBody(BaseModel):
    """A request to set or update a child's rating of a storybook."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    storybook_id: str
    value: int = Field(ge=1, le=5)


class RatingView(BaseModel):
    """A child's recorded rating of a storybook."""

    child_profile_id: str
    storybook_id: str
    value: int
    rated_at: datetime
    updated_at: datetime


class RatingListView(BaseModel):
    """All ratings recorded by a single child profile."""

    ratings: list[RatingView]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_rating_schemas.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/api/schemas.py tests/unit/test_rating_schemas.py
git commit -S -m "feat(api): add Rating request/response schemas"
```

---

## Task 4: Add `POST /ratings` (upsert) and register the router

depends-on: Task 1 [output], Task 3 [output]

**Files:**
- Create: `src/cyo_adventure/api/ratings.py`
- Modify: `src/cyo_adventure/app.py:14` (import) and `src/cyo_adventure/app.py:80` (include_router)
- Test: `tests/integration/test_ratings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_ratings.py`:

```python
"""Integration tests for the rating endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_recorded(client: "AsyncClient", seed: Seed) -> None:
    """A valid rating is stored and echoed back."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 4,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["value"] == 4
    assert body["storybook_id"] == seed.storybook_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_is_upserted(client: "AsyncClient", seed: Seed) -> None:
    """Re-rating the same book overwrites the prior value (no 409)."""
    first = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 2,
        },
        headers=auth(seed.child_token),
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 5,
        },
        headers=auth(seed.child_token),
    )
    assert second.status_code == 200, second.text
    assert second.json()["value"] == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_out_of_range_rejected(client: "AsyncClient", seed: Seed) -> None:
    """A value above 5 is rejected at the schema boundary (422)."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 6,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_wrong_profile_forbidden(
    client: "AsyncClient", seed: Seed
) -> None:
    """A child cannot rate using a profile that is not theirs (403)."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 3,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_foreign_storybook_forbidden(
    client: "AsyncClient", seed: Seed
) -> None:
    """A child in family B cannot rate a storybook owned by family A (403)."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 3,
        },
        headers=auth(seed.other_child_token),
    )
    assert resp.status_code == 403, resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_ratings.py -v`
Expected: FAIL with 404s (route `/api/v1/ratings` not registered).

- [ ] **Step 3: Create the router**

Create `src/cyo_adventure/api/ratings.py`:

```python
"""Rating endpoints: a child rates a storybook 1-5.

A rating is a per-child fact about a *book* (not a specific version) and is
mutable: re-rating overwrites the prior value. This is a deliberately coarser
grain than ``Completion``; see the ``Rating`` model docstring. All access is
scoped to the principal's own family and profile.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context, authorize_family, authorize_profile
from cyo_adventure.api.schemas import RatingBody, RatingListView, RatingView
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import Rating, Storybook

router = APIRouter(prefix="/api/v1", tags=["ratings"])


def _parse_profile_id(raw: str) -> uuid.UUID:
    """Parse a profile id, raising a 422-mapped error on bad input."""
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = "profile_id must be a UUID"
        raise ValidationError(msg, field="profile_id", value=raw) from exc


def _rating_view(row: Rating) -> RatingView:
    """Build the response view from a Rating row."""
    return RatingView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        value=row.value,
        rated_at=row.rated_at,
        updated_at=row.updated_at,
    )


@router.post("/ratings")
async def record_rating(body: RatingBody, ctx: Context) -> RatingView:
    """Set or update the calling child's rating of a storybook.

    Args:
        body: The rating request (profile, storybook, value 1-5).
        ctx: The request context (principal + unit-of-work session).

    Returns:
        RatingView: The stored rating.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the profile or storybook is not the caller's.
        ResourceNotFoundError: If the storybook does not exist.
    """
    # #CRITICAL: security: authorize the profile AND the storybook's family
    # before any write, so a child cannot rate another profile's or family's
    # book (IDOR).
    # #VERIFY: authorize_profile / authorize_family raise AuthorizationError -> 403.
    profile_id = _parse_profile_id(body.profile_id)
    authorize_profile(ctx.principal, profile_id)
    book = await ctx.session.get(Storybook, body.storybook_id)
    if book is None:
        msg = f"storybook '{body.storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, book.family_id)
    # #ASSUME: data integrity: re-rating overwrites in place (upsert); the
    # composite PK (child_profile_id, storybook_id) guarantees one row per pair.
    # #VERIFY: the get-then-update path below never inserts a duplicate.
    row = await ctx.session.get(Rating, (profile_id, body.storybook_id))
    if row is None:
        row = Rating(
            child_profile_id=profile_id,
            storybook_id=body.storybook_id,
            value=body.value,
        )
        ctx.session.add(row)
    else:
        row.value = body.value
    # The unit-of-work dependency commits on success; flush + refresh to read
    # back server-generated timestamps without an explicit commit here.
    await ctx.session.flush()
    await ctx.session.refresh(row, ["rated_at", "updated_at"])
    return _rating_view(row)


@router.get("/ratings/{profile_id}")
async def list_ratings(profile_id: str, ctx: Context) -> RatingListView:
    """List all ratings recorded by a child profile.

    Args:
        profile_id: The child profile whose ratings are requested.
        ctx: The request context (principal + session).

    Returns:
        RatingListView: The profile's ratings.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the profile is not the caller's.
    """
    # #CRITICAL: security: a caller may only read ratings for a profile it owns.
    # #VERIFY: authorize_profile raises AuthorizationError -> 403.
    parsed = _parse_profile_id(profile_id)
    authorize_profile(ctx.principal, parsed)
    rows = await ctx.session.scalars(
        select(Rating).where(Rating.child_profile_id == parsed)
    )
    return RatingListView(ratings=[_rating_view(row) for row in rows.all()])
```

Note: the `if TYPE_CHECKING: pass` block is a placeholder to keep the import style consistent; remove it if BasedPyright flags it as unused, it carries no behavior.

- [ ] **Step 4: Register the router in `app.py`**

Modify `src/cyo_adventure/app.py` line 14, from:

```python
from cyo_adventure.api import generation, health, library, reading
```

to:

```python
from cyo_adventure.api import generation, health, library, ratings, reading
```

Then add after line 80 (`app.include_router(generation.router)`):

```python
    app.include_router(ratings.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_ratings.py -v`
Expected: PASS (5 tests). If your environment cannot start the testcontainers Postgres, run the full integration suite the way CI does and confirm no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/api/ratings.py src/cyo_adventure/app.py tests/integration/test_ratings.py
git commit -S -m "feat(api): add POST /ratings upsert endpoint"
```

---

## Task 5: Add `GET /ratings/{profile_id}` coverage

depends-on: Task 4 [completion] (the GET handler ships in Task 4's `ratings.py`; this task adds its tests)

**Files:**
- Modify: `tests/integration/test_ratings.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_ratings.py`:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_ratings_returns_profile_ratings(
    client: "AsyncClient", seed: Seed
) -> None:
    """A recorded rating appears in the profile's rating list."""
    await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 5,
        },
        headers=auth(seed.child_token),
    )
    resp = await client.get(
        f"/api/v1/ratings/{seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    ratings = resp.json()["ratings"]
    assert any(
        r["storybook_id"] == seed.storybook_id and r["value"] == 5 for r in ratings
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_ratings_other_profile_forbidden(
    client: "AsyncClient", seed: Seed
) -> None:
    """A child cannot list another profile's ratings (403)."""
    resp = await client.get(
        f"/api/v1/ratings/{seed.other_child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_ratings.py -v`
Expected: PASS (7 tests total). The `list_ratings` handler already exists from Task 4, so these pass immediately; if `test_list_ratings_other_profile_forbidden` does not return 403, the auth gate in `list_ratings` is missing, fix it in `ratings.py` before continuing.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_ratings.py
git commit -S -m "test(api): cover GET /ratings list and its auth gate"
```

---

## Task 6: Regenerate the frontend API client

depends-on: Task 4 [completion], Task 5 [completion]

The frontend's request/response types are generated from the backend OpenAPI schema (per the root CLAUDE.md architecture note); the new rating endpoints must be reflected so the contract stays in sync.

- [ ] **Step 1: Start the backend**

Run: `uv run uvicorn cyo_adventure.app:app --port 8000 &`
Expected: server listening on `http://localhost:8000`. Confirm the new routes exist:
Run: `curl -s http://localhost:8000/openapi.json | grep -o '/api/v1/ratings[^"]*'`
Expected: `/api/v1/ratings` appears in the output.
Abort if: the path is absent (router not registered, revisit Task 4 Step 4).

- [ ] **Step 2: Regenerate the client**

Run: `cd frontend && npm run generate-client`
Expected: files under `frontend/src/client/` regenerate with rating operations. Stop the backend afterward (`kill %1`).

- [ ] **Step 3: Type-check the frontend**

Run: `cd frontend && npm run typecheck`
Expected: no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/client
git commit -S -m "chore(frontend): regenerate API client with rating endpoints"
```

---

## Task 7: Update CHANGELOG and run the full gate

depends-on: Task 6 [completion]

OpenSSF baseline requires the CHANGELOG to be updated for new features. This task also runs the project's full pre-commit and test gate before the branch is opened for review.

- [ ] **Step 1: Add a CHANGELOG entry**

In `CHANGELOG.md`, under the `Unreleased` section's `Added` heading (create the heading if absent, matching the existing Keep-a-Changelog style in the file), add:

```markdown
- Ratings: a child can rate a storybook 1-5 (`POST /api/v1/ratings`) and read back their ratings (`GET /api/v1/ratings/{profile_id}`). Ratings are per-child, per-book, mutable, and family-scoped.
```

- [ ] **Step 2: Run the full unit + integration suite with coverage**

Run: `uv run pytest --cov=src --cov-fail-under=80`
Expected: all tests pass; coverage at or above 80%.
Abort if: any failure or coverage below threshold.

- [ ] **Step 3: Lint, type-check, and security scan**

Run: `uv run ruff check . && uv run basedpyright src/ && uv run bandit -r src`
Expected: no errors from any tool.

- [ ] **Step 4: Run pre-commit on all files**

Run: `pre-commit run --all-files`
Expected: all hooks pass (including front-matter validation and the no-em-dash check).

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): record ratings feature"
```

---

## Self-review notes (author)

- **Spec coverage (Phase A clauses):** "child rates a finished book 1-5" -> Tasks 1/3/4 (model, validation, POST). "private to the family" -> `authorize_profile` + `authorize_family` gates, Task 4 (tests `test_rating_wrong_profile_forbidden`, `test_rating_foreign_storybook_forbidden`). "syncs like reading state / works offline" -> the rating write is a plain idempotent-by-overwrite POST; offline queueing reuses the existing sync layer and is NOT re-implemented here (out of scope, noted). "re-rating overwrites" -> Task 4 `test_rating_is_upserted`. Rating widget (stars vs faces) -> explicitly deferred. Cross-family visibility, lineage, sharing -> Phase B, separate plan.
- **No placeholders:** every code step contains complete code; the one `if TYPE_CHECKING: pass` block is annotated as removable.
- **Type consistency:** `RatingBody.value`, `Rating.value`, `RatingView.value`, and the `value` column are consistent; `_rating_view` is defined once and reused by both endpoints; `Context`, `authorize_profile`, `authorize_family` match `deps.py` exports verified during discovery.
- **Shell environment:** all `uv run` commands run from repo root; frontend commands are prefixed `cd frontend`; the uvicorn background job is stopped before the client commit.
- **Alembic names:** head `78336bfff81e` confirmed from the migration chain; new revision `a1b2c3d4e5f6` produces a single head (Task 2 Step 2 verifies offline).

## Open items for the eventual Phase B plan (not this plan)

- `Storybook.lineage_id` column + backfill migration.
- `family_link`, `family_invite`, `book_share` tables.
- The share workflow endpoints and the safety re-validation at import.
- The cross-family `relative-ratings` read endpoint (highest IDOR-risk surface; needs explicit negative tests).
