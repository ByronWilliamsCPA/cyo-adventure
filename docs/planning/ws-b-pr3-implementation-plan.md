---
schema_type: planning
title: "WS-B PR 3: Series Tagging and Soft Continuation Implementation Plan"
description: "Task-by-task implementation plan for WS-B PR 3: the series table migration,
  request-time series tagging and continuation anchoring, anchor context in the concept brief,
  book_index assignment at generation completion under a UNIQUE-plus-retry guard, and the kid
  and guardian series UI."
tags:
  - planning
  - architecture
  - story-requests
  - series
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an implementer with zero session context everything needed to build WS-B PR 3
  task by task against the approved spec."
component: Strategy
source: "docs/planning/ws-b-request-lifecycle-plan.md (spec, sections 1/2/4/5/6); codebase
  discovery 2026-07-08 on feat/ws-b-series-continuation at 71552d7 (main after PR #164 and
  PR #165)."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Let stories chain into series: a kid proposes a series title or continues an existing
series-tagged book, the guardian ratifies (or edits, or removes) the proposal at approval,
guardians and admins can create series-tagged requests directly, the generation brief carries a
deterministic `anchor_context` extracted from the continued book, and each generated book gets a
race-safe `book_index` in its series at generation completion.

## Architecture

Series linkage is DB-columns-only in WS-B (decision B2): a new `series` table plus nullable
columns on `story_request` (`series_id`, `anchor_storybook_id`, `proposed_series_title`) and
`storybook` (`series_id`, `book_index` with UNIQUE `(series_id, book_index)`). The embedded
Pydantic `Series` document block is never written, so validator rules SR-1..SR-7 stay dormant
until WS-G. The concept brief gains an optional `anchor_context` field; because
`build_structure_prompt` injects `brief.model_dump_json()` wholesale (`generation/prompts.py:306`)
and skeleton-fill jobs stash the whole `concept.brief` as `theme_brief`
(`story_requests/authoring_plan.py:190`), the new field reaches both generation methods with no
prompt-template change. `book_index` is assigned once, in the worker right after
`persist_storybook`, as `max(book_index) + 1` under the UNIQUE constraint with one retry on
conflict (the ratified concurrency guard).

## Tech stack

FastAPI + Pydantic v2, async SQLAlchemy 2.x, Alembic, pytest + testcontainers Postgres,
React 19 + Vite + Vitest + Playwright, `@hey-api/openapi-ts` generated client.

## Conventions that bind every task

- Worktree: `.worktrees/ws-b-pr3`, branch `feat/ws-b-series-continuation`, cut from `main` at
  `71552d7`. All commands below run from the worktree root unless stated otherwise.
- Signed commits (`git commit -S`), Conventional Commits, never `git add -A` (stage named paths).
- No em-dash characters anywhere (pre-commit hook rejects them).
- RAD markers (`#CRITICAL`/`#ASSUME`/`#EDGE` + `#VERIFY`) on assumptions in the mandatory
  categories; the spec MANDATES this pair verbatim on the book_index guard:
  `#CRITICAL: concurrency: two continuations of the same series racing on book_index` /
  `#VERIFY: unique constraint plus one retry on conflict; concurrency test in PR 3`.
- Closed vocabularies (binding literals): age bands `'3-5','5-8','8-11','10-13','13-16','16+'`;
  lengths `'short','medium','long'`; styles `'prose','gamebook'`; teen bands (gamebook-eligible
  and state-carry) `'13-16','16+'`; episodic bands (carries_state false) `'3-5','5-8'`.
- Backend gates per task: the covering tests plus `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run basedpyright src/`. Frontend gates:
  `npm run lint && npm run typecheck && npm run test:run` from `frontend/`.
- `frontend/src/client/` is build output: never hand-edit; regenerate in Task 7 only.
- Error mapping (centralized exceptions): `ValidationError` -> 422, `ResourceNotFoundError` ->
  404, `AuthorizationError` -> 403, `StateTransitionError` -> 409. Anchor scope failures use
  404-over-403 existence hiding, mirroring `_load_scoped_request`
  (`api/story_requests.py:468-509`).
- Blocked-row redaction: raw text of a blocked request is never surfaced; PR 3 extends this to
  `proposed_series_title` (screened content, same redaction rationale).

## Decisions resolved during planning (bind the tasks below)

1. `anchor_storybook_id` is `String(120)` (storybook PK is a string like `s_<job_id>`, not a
   UUID).
2. Field naming: the kid body uses `proposed_series_title` (a proposal the guardian ratifies);
   the authored-create and approve bodies use `series_title` (creates the series immediately).
   Authored rows never persist `proposed_series_title` (the title is consumed at creation or,
   when screening blocks the row, dropped: blocked rows are terminal).
3. A guardian may supply `series_title` at approval even when the kid proposed nothing (the
   "edit the title" operation generalizes); omitting it is the "remove" operation. Supplying it
   on a continuation (anchored) request is a 422.
4. `resolve_anchor` enforces, in order: anchor exists in the caller's family (404 otherwise,
   existence hiding), anchor is published (status `published`, `current_published_version` set,
   that version has `approved_by`; the kid-library filter mirrored), anchor is series-linked
   (422 otherwise), and the expected band equals the series band (422 otherwise). It runs at
   creation (kid and authored) and again at approval.
5. Anchored requests get `series_id` stamped at creation (the series already exists, so a later
   decline leaves no orphan series row). Proposal requests get `series_id` only when a series
   row is created (authored create, or guardian approval).
6. Screening: when a kid proposes a title, one `screen_request_text` call screens
   `f"{title}\n{text}"` (one classifier round trip; the PII guard covers both). Same for
   authored create. At approval, the guardian's `series_title` is screened alone; a blocked
   title fails the approve with a 422 whose message never echoes the title.
7. `AnchorContext` is deterministic extraction, not an LLM summary: the anchor blob's title, the
   protagonist name recovered via the anchor's GenerationJob -> Concept brief, and up to 3
   truncated ending-node excerpts.
8. `book_index` is assigned together with `storybook.series_id` right after `persist_storybook`
   in the worker, before the moderation pipeline (a moderation failure rolls the whole persist
   back, so no index hole). A moderation-rejected book keeps its index (accepted; the spec
   assigns at row creation).
9. Storybook pairing CHECK `(series_id IS NULL) = (book_index IS NULL)` enforces that the
   assignment is atomic; the UNIQUE constraint allows unlimited `(NULL, NULL)` rows (Postgres
   NULL semantics), so non-series books are unaffected.
10. Frontend scope: kid RequestStory gains the optional series-title input and the
    library-driven "Continue this story" entry; the guardian approve strip gains the series
    ratify/edit input (hidden for anchored rows, whose band select is disabled);
    RequestStoryForm gains a series-title input in both modes. No anchor picker on the authored
    form (anchored authored requests are API-only for now; a book picker is out of scope).

## File structure

Create:

- `migrations/versions/20260708_1600_add_series_and_soft_continuation.py` (revision
  `e1f2a3b4c5d6`, down `d0e1f2a3b4c5`)
- `src/cyo_adventure/story_requests/anchoring.py` (anchor validation + context extraction)
- `src/cyo_adventure/generation/series_link.py` (book_index assignment + worker hook)
- `tests/integration/test_series_migration.py`
- `tests/integration/test_series_requests.py`
- `tests/integration/test_series_link.py`
- `tests/unit/test_anchoring.py`

Modify:

- `src/cyo_adventure/db/models.py` (Series model; StoryRequest and Storybook columns)
- `src/cyo_adventure/api/schemas.py` (body/view fields, `SeriesTitle`/`AnchorId` types)
- `src/cyo_adventure/generation/concept.py` (`AnchorContext`, `ConceptBrief.anchor_context`)
- `src/cyo_adventure/story_requests/brief.py` (`anchor_context` passthrough)
- `src/cyo_adventure/story_requests/service.py` (`create_series`, approve/authored extensions,
  `_build_concept` anchor loading)
- `src/cyo_adventure/api/story_requests.py` (kid create, authored create, approve, `_to_view`)
- `src/cyo_adventure/api/library.py` (series fields on listing items)
- `src/cyo_adventure/generation/worker.py` (series-link call after persist)
- `frontend/src/library/{storyRequestApi.ts,RequestStory.tsx,libraryApi.ts,BookCard.tsx,LibraryPage.tsx}`
- `frontend/src/guardian/{RequestsPage.tsx,RequestStoryForm.tsx}`
- `frontend/e2e/{story-requests-kid,story-requests,story-requests-authored}.spec.ts`
- `frontend/e2e-real/authored-request.spec.ts`
- `CHANGELOG.md`

---

### Task 1: Migration and ORM (series table, request and storybook columns)

**Files:**
- Create: `migrations/versions/20260708_1600_add_series_and_soft_continuation.py`
- Modify: `src/cyo_adventure/db/models.py`
- Test: `tests/integration/test_series_migration.py`

- [ ] **Step 1: Write the migration**

Revision `e1f2a3b4c5d6` chaining onto `d0e1f2a3b4c5`, mirroring the style of
`migrations/versions/20260708_0900_add_story_request_lifecycle_fields.py`:

```python
"""Add series table and soft-continuation columns (WS-B PR 3).

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-08 16:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create series, then link story_request and storybook to it."""
    op.create_table(
        "series",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "family_id", sa.Uuid(), sa.ForeignKey("family.id"), nullable=False
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("age_band", sa.String(length=16), nullable=False),
        sa.Column("carries_state", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "age_band IN ('3-5', '5-8', '8-11', '10-13', '13-16', '16+')",
            name="ck_series_age_band",
        ),
    )
    op.create_index("ix_series_family_id", "series", ["family_id"])

    op.add_column("story_request", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.add_column(
        "story_request",
        sa.Column("anchor_storybook_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "story_request",
        sa.Column("proposed_series_title", sa.String(length=120), nullable=True),
    )
    op.create_foreign_key(
        "fk_story_request_series_id_series",
        "story_request",
        "series",
        ["series_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_story_request_anchor_storybook_id_storybook",
        "story_request",
        "storybook",
        ["anchor_storybook_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_story_request_series_xor",
        "story_request",
        "NOT (proposed_series_title IS NOT NULL AND anchor_storybook_id IS NOT NULL)",
    )

    op.add_column("storybook", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.add_column("storybook", sa.Column("book_index", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_storybook_series_id_series", "storybook", "series", ["series_id"], ["id"]
    )
    # #CRITICAL: concurrency: two continuations of the same series racing on book_index
    # #VERIFY: unique constraint plus one retry on conflict; concurrency test in PR 3
    op.create_unique_constraint(
        "uq_storybook_series_book_index", "storybook", ["series_id", "book_index"]
    )
    op.create_check_constraint(
        "ck_storybook_book_index", "storybook", "book_index IS NULL OR book_index >= 1"
    )
    op.create_check_constraint(
        "ck_storybook_series_index_pairing",
        "storybook",
        "(series_id IS NULL) = (book_index IS NULL)",
    )


def downgrade() -> None:
    """Drop the soft-continuation columns and the series table."""
    op.drop_constraint(
        "ck_storybook_series_index_pairing", "storybook", type_="check"
    )
    op.drop_constraint("ck_storybook_book_index", "storybook", type_="check")
    op.drop_constraint(
        "uq_storybook_series_book_index", "storybook", type_="unique"
    )
    op.drop_constraint("fk_storybook_series_id_series", "storybook", type_="foreignkey")
    op.drop_column("storybook", "book_index")
    op.drop_column("storybook", "series_id")
    op.drop_constraint("ck_story_request_series_xor", "story_request", type_="check")
    op.drop_constraint(
        "fk_story_request_anchor_storybook_id_storybook",
        "story_request",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_story_request_series_id_series", "story_request", type_="foreignkey"
    )
    op.drop_column("story_request", "proposed_series_title")
    op.drop_column("story_request", "anchor_storybook_id")
    op.drop_column("story_request", "series_id")
    op.drop_index("ix_series_family_id", table_name="series")
    op.drop_table("series")
```

- [ ] **Step 2: Add the ORM model and columns**

In `src/cyo_adventure/db/models.py`:

Add near the other `_FK_*` constants (models.py top, around line 30):

```python
_FK_SERIES = "series.id"
```

Add the `Series` class after `Family` (keep FK-dependency reading order; anywhere before
`StoryRequest` is fine):

```python
class Series(Base):
    """A named, family-owned chain of storybooks (WS-B PR 3, decision B2).

    DB-level linkage only in WS-B: books reference a series via
    ``storybook.series_id``/``book_index``; the embedded document ``Series``
    metadata block (storybook/models.py) is NOT written, so the SR-1..SR-7
    cross-book validator stays dormant until WS-G adds structural chaining.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family (NOT NULL, decision B3; widening is WS-E).
        title: Guardian- or admin-ratified series title (screened at intake).
        age_band: The band every book in the series targets; continuations
            must match it (approval rejects a mismatch).
        carries_state: ADR-011 band rule: False (episodic) for '3-5'/'5-8',
            True for all higher bands.
        created_by: The ratifying user, or None.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "series"
    __table_args__ = (
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_series_age_band",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY), index=True)
    title: Mapped[str] = mapped_column(String(120))
    age_band: Mapped[str] = mapped_column(String(16))
    carries_state: Mapped[bool] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
```

Note: `_AGE_BAND_VALUES` already exists (used by `ck_story_request_age_band`); reuse it, do not
redefine.

On `StoryRequest`, add to `__table_args__`:

```python
        CheckConstraint(
            "NOT (proposed_series_title IS NOT NULL "
            "AND anchor_storybook_id IS NOT NULL)",
            name="ck_story_request_series_xor",
        ),
```

and add the columns (after `concept_id`):

```python
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_SERIES), default=None
    )
    anchor_storybook_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey(_FK_STORYBOOK), default=None
    )
    proposed_series_title: Mapped[str | None] = mapped_column(
        String(120), default=None
    )
```

Extend the StoryRequest docstring Attributes section with the three new fields (one line each:
series link, continuation anchor, kid's unratified title proposal).

On `Storybook` (the DB model, models.py line ~127), extend `__table_args__`:

```python
        UniqueConstraint(
            "series_id", "book_index", name="uq_storybook_series_book_index"
        ),
        CheckConstraint(
            "book_index IS NULL OR book_index >= 1",
            name="ck_storybook_book_index",
        ),
        CheckConstraint(
            "(series_id IS NULL) = (book_index IS NULL)",
            name="ck_storybook_series_index_pairing",
        ),
```

and add the columns:

```python
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_SERIES), default=None
    )
    book_index: Mapped[int | None] = mapped_column(default=None)
```

`UniqueConstraint` needs importing from `sqlalchemy` if not already imported.

- [ ] **Step 3: Write the migration round-trip tests**

Create `tests/integration/test_series_migration.py` mirroring
`tests/integration/test_story_request_lifecycle_migration.py` (same `_env` helper, same
`migration_pg_url` module-scoped fixture from `tests/integration/conftest.py`, same
`run_alembic`/`PROJECT_ROOT` imports from `tests/integration/_migration_utils.py`):

```python
"""Round-trip and constraint tests for the WS-B PR 3 series migration."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

REVISION = "e1f2a3b4c5d6"
DOWN_REVISION = "d0e1f2a3b4c5"


def _env(pg_url: str) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["CYO_ADVENTURE_DATABASE_URL"] = pg_url
    return env


@pytest.fixture
def upgraded_engine(migration_pg_url: str) -> sa.engine.Engine:
    """Land on DOWN_REVISION, clear rows, seed a family, upgrade to REVISION."""
    env = _env(migration_pg_url)
    up = run_alembic(PROJECT_ROOT, env, "upgrade", DOWN_REVISION)
    assert up.returncode == 0, up.stderr
    down = run_alembic(PROJECT_ROOT, env, "downgrade", DOWN_REVISION)
    assert down.returncode == 0, down.stderr
    sync_url = migration_pg_url.replace("+asyncpg", "+psycopg")
    engine = sa.create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM story_request"))
        conn.execute(sa.text("DELETE FROM storybook_version"))
        conn.execute(sa.text("DELETE FROM storybook"))
        conn.execute(sa.text("DELETE FROM family"))
        conn.execute(
            sa.text("INSERT INTO family (id, name) VALUES (:id, 'Fam')"),
            {"id": str(uuid.uuid4())},
        )
    result = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr
    return engine


def _family_id(conn: sa.Connection) -> str:
    return str(conn.execute(sa.text("SELECT id FROM family LIMIT 1")).scalar_one())


def _seed_series(conn: sa.Connection, family_id: str, band: str = "8-11") -> str:
    series_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO series (id, family_id, title, age_band, carries_state) "
            "VALUES (:id, :family_id, 'Fox Tales', :band, true)"
        ),
        {"id": series_id, "family_id": family_id, "band": band},
    )
    return series_id


def _seed_storybook(
    conn: sa.Connection,
    family_id: str,
    *,
    series_id: str | None = None,
    book_index: int | None = None,
) -> str:
    storybook_id = f"s_{uuid.uuid4().hex[:12]}"
    conn.execute(
        sa.text(
            "INSERT INTO storybook (id, family_id, status, series_id, book_index) "
            "VALUES (:id, :family_id, 'published', :series_id, :book_index)"
        ),
        {
            "id": storybook_id,
            "family_id": family_id,
            "series_id": series_id,
            "book_index": book_index,
        },
    )
    return storybook_id


def test_series_table_accepts_valid_row(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        _seed_series(conn, _family_id(conn))


def test_series_rejects_bad_band(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        with pytest.raises(IntegrityError, match="ck_series_age_band"):
            with conn.begin():
                _seed_series(conn, family_id, band="4-7")


def test_storybook_unique_series_index(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        family_id = _family_id(conn)
        series_id = _seed_series(conn, family_id)
        _seed_storybook(conn, family_id, series_id=series_id, book_index=1)
    with upgraded_engine.connect() as conn:
        with pytest.raises(IntegrityError, match="uq_storybook_series_book_index"):
            with conn.begin():
                _seed_storybook(conn, family_id, series_id=series_id, book_index=1)


def test_storybook_null_pair_rows_unlimited(
    upgraded_engine: sa.engine.Engine,
) -> None:
    """(NULL, NULL) never collides: non-series books are unaffected."""
    with upgraded_engine.begin() as conn:
        family_id = _family_id(conn)
        _seed_storybook(conn, family_id)
        _seed_storybook(conn, family_id)


def test_storybook_rejects_zero_index(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        with upgraded_engine.begin() as seed:
            series_id = _seed_series(seed, family_id)
        with pytest.raises(IntegrityError, match="ck_storybook_book_index"):
            with conn.begin():
                _seed_storybook(conn, family_id, series_id=series_id, book_index=0)


def test_storybook_rejects_unpaired_series_fields(
    upgraded_engine: sa.engine.Engine,
) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        with upgraded_engine.begin() as seed:
            series_id = _seed_series(seed, family_id)
        with pytest.raises(IntegrityError, match="ck_storybook_series_index_pairing"):
            with conn.begin():
                _seed_storybook(conn, family_id, series_id=series_id, book_index=None)


def test_story_request_rejects_proposal_and_anchor(
    upgraded_engine: sa.engine.Engine,
) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        with upgraded_engine.begin() as seed:
            anchor_id = _seed_storybook(seed, family_id)
        with pytest.raises(IntegrityError, match="ck_story_request_series_xor"):
            with conn.begin():
                conn.execute(
                    sa.text(
                        "INSERT INTO story_request (id, family_id, request_text, "
                        "status, age_band, proposed_series_title, anchor_storybook_id) "
                        "VALUES (:id, :family_id, 'x', 'pending', '8-11', "
                        "'Fox Tales', :anchor)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "family_id": family_id,
                        "anchor": anchor_id,
                    },
                )


def test_downgrade_round_trip(upgraded_engine: sa.engine.Engine) -> None:
    """Downgrade drops the table and columns; a re-upgrade restores them."""
    # Re-derive the env from the engine URL (the fixture consumed the raw URL).
    url = upgraded_engine.url.render_as_string(hide_password=False).replace(
        "+psycopg", "+asyncpg"
    )
    env = _env(url)
    down = run_alembic(PROJECT_ROOT, env, "downgrade", DOWN_REVISION)
    assert down.returncode == 0, down.stderr
    with upgraded_engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        }
    assert "series" not in tables
    up = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert up.returncode == 0, up.stderr
```

Adapt the seeding details to the real initial-schema column list if an INSERT fails (the
`_migration_utils` docstrings and `test_story_request_lifecycle_migration.py` show the minimal
valid rows); keep the constraint names and assertions exactly as written.

- [ ] **Step 4: Run the migration tests**

Run: `uv run pytest tests/integration/test_series_migration.py -v`
Expected: all tests pass (requires Docker; they skip if unavailable, in which case run them via
the existing testcontainers setup before marking this task done).

- [ ] **Step 5: Run the full backend gates**

Run: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: no failures, no lint or type errors.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/20260708_1600_add_series_and_soft_continuation.py \
  src/cyo_adventure/db/models.py tests/integration/test_series_migration.py
git commit -S -m "feat(db): add series table and soft-continuation columns (WS-B PR 3)"
```

---

### Task 2: API schemas (bodies, views, library item)

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/api/schemas.py`
- Test: `tests/unit/test_schemas.py` (extend; check the file for the existing body-validator
  test style and reuse its helpers before adding new ones)

- [ ] **Step 1: Add the shared constrained types**

Next to `RequestText` (schemas.py ~line 367):

```python
SeriesTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

AnchorId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
```

- [ ] **Step 2: Extend the three bodies**

`StoryRequestCreateBody` (kid) gains:

```python
    proposed_series_title: SeriesTitle | None = None
    anchor_storybook_id: AnchorId | None = None

    @model_validator(mode="after")
    def _proposal_xor_anchor(self) -> StoryRequestCreateBody:
        if (
            self.proposed_series_title is not None
            and self.anchor_storybook_id is not None
        ):
            msg = "a request may propose a new series or continue one, not both"
            raise ValueError(msg)
        return self
```

`StoryRequestAuthoredCreateBody` gains (same shape, different first field name):

```python
    series_title: SeriesTitle | None = None
    anchor_storybook_id: AnchorId | None = None

    @model_validator(mode="after")
    def _series_xor_anchor(self) -> StoryRequestAuthoredCreateBody:
        if self.series_title is not None and self.anchor_storybook_id is not None:
            msg = "a request may create a new series or continue one, not both"
            raise ValueError(msg)
        return self
```

`StoryRequestApproveBody` gains one field (no validator; the anchored-plus-title conflict is a
service-layer check because it needs the row):

```python
    series_title: SeriesTitle | None = None
```

Update each body's docstring with one sentence describing the new fields (kid: an unratified
proposal or a continuation anchor; authored: creates the series immediately; approve: ratify or
edit the kid's proposal, omit to decline it).

- [ ] **Step 3: Extend the views**

`StoryRequestView` gains (after `narrative_style`):

```python
    series_id: str | None
    proposed_series_title: str | None
    anchor_storybook_id: str | None
```

Docstring: note that `proposed_series_title` is `None` for blocked rows (screened content,
same redaction as `request_text`).

`LibraryItem` gains (after `progress`):

```python
    series_id: str | None = None
    book_index: int | None = None
```

- [ ] **Step 4: Write the validator unit tests**

Extend the existing schema unit-test file with:

```python
def test_kid_body_rejects_proposal_and_anchor() -> None:
    with pytest.raises(PydanticValidationError, match="not both"):
        StoryRequestCreateBody(
            profile_id="p1",
            request_text="a fox story",
            proposed_series_title="Fox Tales",
            anchor_storybook_id="s_abc",
        )


def test_authored_body_rejects_series_and_anchor() -> None:
    with pytest.raises(PydanticValidationError, match="not both"):
        StoryRequestAuthoredCreateBody(
            request_text="a fox story",
            age_band=AgeBand.BAND_8_11,
            length=Length.SHORT,
            series_title="Fox Tales",
            anchor_storybook_id="s_abc",
        )


def test_kid_body_accepts_proposal_alone() -> None:
    body = StoryRequestCreateBody(
        profile_id="p1",
        request_text="a fox story",
        proposed_series_title="  Fox Tales  ",
    )
    assert body.proposed_series_title == "Fox Tales"


def test_series_title_over_cap_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        StoryRequestCreateBody(
            profile_id="p1", request_text="x", proposed_series_title="t" * 121
        )
```

Match the enum-member spellings to the actual `AgeBand`/`Length` definitions in
`storybook/models.py` (read them; do not guess member names).

- [ ] **Step 5: Run tests and gates, then commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run basedpyright src/`
Expected: pass.

```bash
git add src/cyo_adventure/api/schemas.py tests/unit/test_schemas.py
git commit -S -m "feat(contract): series fields on request bodies and views (WS-B PR 3)"
```

(If the schema tests live in a differently named unit file, stage that file instead.)

---

### Task 3: AnchorContext and the anchoring module

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/generation/concept.py`, `src/cyo_adventure/story_requests/brief.py`
- Create: `src/cyo_adventure/story_requests/anchoring.py`
- Test: `tests/unit/test_anchoring.py`; extend `tests/unit/test_brief.py` (or wherever
  `brief_from_request` tests live; find with `grep -rl brief_from_request tests/`)

- [ ] **Step 1: Add `AnchorContext` to `generation/concept.py`**

Place immediately before `ConceptBrief` (it must be defined first):

```python
class AnchorContext(BaseModel):
    """Soft-continuation context extracted from a series anchor storybook.

    Deterministic extraction, not an LLM summary (WS-B PR 3, decision B2): the
    anchor document's title, the protagonist name recovered from the anchor's
    concept brief, and truncated ending excerpts. Serialized into the Stage A
    prompt with the rest of the brief (build_structure_prompt injects
    ``model_dump_json`` wholesale), so the generated book can follow on
    thematically without embedding document-level Series metadata (SR-1..SR-7
    stay dormant until WS-G).
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    character_names: list[_BoundedText] = Field(default_factory=list, max_length=5)
    ending_summary: str = Field(default="", max_length=600)
```

Add to `ConceptBrief` (after `special_constraints`):

```python
    anchor_context: AnchorContext | None = Field(
        default=None,
        description="Soft-continuation context from a series anchor (WS-B PR 3).",
    )
```

Note: `_strip_control_chars` walks nested dicts and list items already (see its docstring); no
change needed there.

- [ ] **Step 2: Thread it through `brief_from_request`**

In `story_requests/brief.py`, change the signature and the constructor call:

```python
def brief_from_request(
    request: StoryRequest,
    profile: ChildProfile | None,
    anchor_context: AnchorContext | None = None,
) -> ConceptBrief:
```

Add an Args line ("Soft-continuation context from the request's anchor, or None") and pass
`anchor_context=anchor_context` in the `ConceptBrief(...)` call. Import `AnchorContext` from
`cyo_adventure.generation.concept` under `TYPE_CHECKING` if the module already imports lazily,
otherwise as a plain import (match the file's existing import style).

- [ ] **Step 3: Create `story_requests/anchoring.py`**

```python
"""Anchor validation and soft-continuation context for series requests (WS-B PR 3).

``resolve_anchor`` is the single seam every continuation entry point uses (kid
create, authored create, and approve re-validation), so the published/family/
series/band rules cannot drift apart between paths. ``load_anchor_context``
feeds the concept brief; extraction is deterministic (no LLM call).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import (
    Concept,
    GenerationJob,
    Series,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.generation.concept import AnchorContext

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

_MAX_ENDING_EXCERPTS = 3
_EXCERPT_CHARS = 150
_SUMMARY_CHARS = 600
_TITLE_CHARS = 200
_MAX_CHARACTER_NAMES = 5


async def resolve_anchor(
    session: AsyncSession,
    anchor_storybook_id: str,
    *,
    family_id: uuid.UUID,
    expected_band: str,
) -> Series:
    """Validate a continuation anchor and return its series.

    Args:
        session: The request session.
        anchor_storybook_id: The storybook named as the continuation anchor.
        family_id: The resolved target family of the request being created or
            approved; the anchor must belong to it.
        expected_band: The band the request targets; must equal the series
            band (continuations inherit the series band, never fork it).

    Returns:
        Series: The anchor's series row.

    Raises:
        ResourceNotFoundError: Missing anchor or outside the family (-> 404,
            existence hiding, mirroring _load_scoped_request).
        ValidationError: Anchor not published, not series-linked, or band
            mismatch (-> 422).
    """
    storybook = await session.get(Storybook, anchor_storybook_id)
    # #CRITICAL: security: 404-over-403 for an anchor outside the caller's
    # family, so this endpoint cannot be used to probe other families' books.
    # #VERIFY: test_series_requests.py::test_kid_anchor_cross_family_is_404.
    if storybook is None or storybook.family_id != family_id:
        msg = f"storybook '{anchor_storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    version = None
    if storybook.current_published_version is not None:
        version = await session.scalar(
            select(StorybookVersion).where(
                StorybookVersion.storybook_id == storybook.id,
                StorybookVersion.version == storybook.current_published_version,
            )
        )
    # Mirrors the kid-library visibility filter (api/library.py): published
    # status, a current published version, and an approved version row.
    if (
        storybook.status != "published"
        or version is None
        or version.approved_by is None
    ):
        msg = "anchor storybook is not published"
        raise ValidationError(
            msg, field="anchor_storybook_id", value=anchor_storybook_id
        )
    if storybook.series_id is None:
        msg = "anchor storybook is not part of a series"
        raise ValidationError(
            msg, field="anchor_storybook_id", value=anchor_storybook_id
        )
    series = await session.get(Series, storybook.series_id)
    if series is None:
        msg = "series not found"
        raise ResourceNotFoundError(msg)
    if series.age_band != expected_band:
        msg = "request age band does not match the series band"
        raise ValidationError(msg, field="age_band", value=expected_band)
    return series


async def load_anchor_context(
    session: AsyncSession, anchor_storybook_id: str
) -> AnchorContext | None:
    """Extract the soft-continuation context from a validated anchor.

    Defensive by design: the anchor was validated at creation and approval,
    but this runs later (inside _build_concept) and degrades to None or to
    partial context rather than failing the approve on a malformed blob.
    """
    storybook = await session.get(Storybook, anchor_storybook_id)
    if storybook is None or storybook.current_published_version is None:
        return None
    version = await session.scalar(
        select(StorybookVersion).where(
            StorybookVersion.storybook_id == storybook.id,
            StorybookVersion.version == storybook.current_published_version,
        )
    )
    if version is None or not isinstance(version.blob, dict):
        return None
    names = await _protagonist_names(session, anchor_storybook_id)
    return anchor_context_from_blob(version.blob, character_names=names)


async def _protagonist_names(
    session: AsyncSession, storybook_id: str
) -> list[str]:
    """Recover the anchor's protagonist name via its GenerationJob's concept.

    The document blob carries no character list; the protagonist lives on the
    concept brief the anchor was generated from. Empty on any missing link.
    """
    brief = await session.scalar(
        select(Concept.brief)
        .join(GenerationJob, GenerationJob.concept_id == Concept.id)
        .where(GenerationJob.storybook_id == storybook_id)
        .limit(1)
    )
    if not isinstance(brief, dict):
        return []
    protagonist = brief.get("protagonist")
    if not isinstance(protagonist, dict):
        return []
    name = protagonist.get("name")
    if isinstance(name, str) and name:
        return [name]
    return []


def anchor_context_from_blob(
    blob: Mapping[str, object], *, character_names: list[str]
) -> AnchorContext:
    """Build an AnchorContext from a stored Storybook blob (pure function).

    Every field is read defensively (mirroring api/library.py::_library_item):
    a malformed value degrades to a safe default rather than raising.
    """
    title = blob.get("title")
    safe_title = title if isinstance(title, str) and title else "Untitled story"
    excerpts: list[str] = []
    nodes = blob.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if len(excerpts) >= _MAX_ENDING_EXCERPTS:
                break
            if not isinstance(node, dict) or not node.get("is_ending"):
                continue
            ending = node.get("ending")
            label = ending.get("title") if isinstance(ending, dict) else None
            body = node.get("body")
            body_text = body if isinstance(body, str) else ""
            piece = (
                f"{label}: {body_text}"
                if isinstance(label, str) and label
                else body_text
            )
            if piece:
                excerpts.append(piece[:_EXCERPT_CHARS])
    summary = " | ".join(excerpts)[:_SUMMARY_CHARS]
    return AnchorContext(
        title=safe_title[:_TITLE_CHARS],
        character_names=character_names[:_MAX_CHARACTER_NAMES],
        ending_summary=summary,
    )
```

- [ ] **Step 4: Write the unit tests**

Create `tests/unit/test_anchoring.py` covering `anchor_context_from_blob` (pure function, no
DB):

```python
"""Unit tests for anchor-context extraction (WS-B PR 3)."""

from __future__ import annotations

from cyo_adventure.story_requests.anchoring import anchor_context_from_blob


def _blob() -> dict[str, object]:
    return {
        "title": "The Fox and the Map",
        "nodes": [
            {"id": "n1", "body": "You set off.", "is_ending": False},
            {
                "id": "n2",
                "body": "You find the treasure and share it with the village.",
                "is_ending": True,
                "ending": {"id": "e1", "title": "Treasure shared"},
            },
            {
                "id": "n3",
                "body": "You head home for supper.",
                "is_ending": True,
                "ending": {"id": "e2", "title": "Home again"},
            },
        ],
    }


def test_extracts_title_names_and_ending_excerpts() -> None:
    ctx = anchor_context_from_blob(_blob(), character_names=["Robin"])
    assert ctx.title == "The Fox and the Map"
    assert ctx.character_names == ["Robin"]
    assert "Treasure shared: You find the treasure" in ctx.ending_summary
    assert "Home again" in ctx.ending_summary


def test_caps_excerpt_count_and_length() -> None:
    blob = _blob()
    nodes = blob["nodes"]
    assert isinstance(nodes, list)
    for i in range(5):
        nodes.append(
            {
                "id": f"x{i}",
                "body": "y" * 500,
                "is_ending": True,
                "ending": {"id": f"ex{i}", "title": "Long"},
            }
        )
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert len(ctx.ending_summary) <= 600
    assert ctx.ending_summary.count("|") <= 2


def test_malformed_blob_degrades_to_defaults() -> None:
    ctx = anchor_context_from_blob(
        {"title": 7, "nodes": "not-a-list"}, character_names=[]
    )
    assert ctx.title == "Untitled story"
    assert ctx.ending_summary == ""
```

Also extend the `brief_from_request` unit tests with one case: passing an `AnchorContext`
surfaces on the returned brief (`brief.anchor_context is ctx`), and the default stays `None`.

- [ ] **Step 5: Run tests and gates, then commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run basedpyright src/`
Expected: pass.

```bash
git add src/cyo_adventure/generation/concept.py src/cyo_adventure/story_requests/brief.py \
  src/cyo_adventure/story_requests/anchoring.py tests/unit/test_anchoring.py
git commit -S -m "feat(generation): anchor context extraction for soft continuation (WS-B PR 3)"
```

(Also stage the brief test file you extended.)

---

### Task 4: Service layer (create_series, approve and authored extensions)

depends-on: Task2 [completion], Task3 [output]

**Files:**
- Modify: `src/cyo_adventure/story_requests/service.py`
- Test: extend the service-level tests (find with
  `grep -rl approve_story_request tests/ | head`)

- [ ] **Step 1: Add `create_series`**

In `service.py`, after the imports add the band constant, and after
`count_pending_for_profile` add the function:

```python
# ADR-011 band rule: young bands run episodic series that carry no state.
_EPISODIC_BANDS = frozenset({"3-5", "5-8"})


async def create_series(
    session: AsyncSession,
    principal: Principal,
    *,
    title: str,
    family_id: uuid.UUID,
    age_band: str,
) -> Series:
    """Create a series row (guardian ratification or authored creation).

    Args:
        session: The request session (caller owns the transaction).
        principal: The ratifying guardian or admin.
        title: The screened series title.
        family_id: The owning family (NOT NULL, decision B3).
        age_band: The band every book in the series will target;
            ``carries_state`` derives from it (ADR-011: episodic for 3-5 and
            5-8, state-carry for higher bands).

    Returns:
        Series: The flushed row (id assigned).
    """
    series = Series(
        family_id=family_id,
        title=title,
        age_band=age_band,
        carries_state=age_band not in _EPISODIC_BANDS,
        created_by=principal.user_id,
    )
    session.add(series)
    await session.flush()
    return series
```

Import `Series` alongside the other model imports and `ValidationError` from
`cyo_adventure.core.exceptions` (needed in Step 2), plus `resolve_anchor` and
`load_anchor_context` from `cyo_adventure.story_requests.anchoring` (no import cycle: anchoring
does not import service).

- [ ] **Step 2: Extend `approve_story_request`**

New signature and series handling, inserted between the profile load and the confirmation
stamping (keep every existing line, including the row-lock RAD block):

```python
async def approve_story_request(
    session: AsyncSession,
    principal: Principal,
    request: StoryRequest,
    *,
    confirmation: ApprovalConfirmation,
    series_title: str | None = None,
) -> str:
```

```python
    # WS-B PR 3: series ratification. An anchored (continuation) request
    # already carries its series; the guardian's confirmed band must match the
    # series band (a mismatch would silently fork the series). A non-anchored
    # request may ratify the kid's proposal, or any guardian-chosen title.
    if request.anchor_storybook_id is not None:
        if series_title is not None:
            msg = "a continuation request cannot also create a new series"
            raise ValidationError(msg, field="series_title", value=series_title)
        await resolve_anchor(
            session,
            request.anchor_storybook_id,
            family_id=request.family_id,
            expected_band=confirmation.age_band.value,
        )
    elif series_title is not None:
        series = await create_series(
            session,
            principal,
            title=series_title,
            family_id=request.family_id,
            age_band=confirmation.age_band.value,
        )
        request.series_id = series.id
```

Extend the docstring: `series_title` arg line, and Raises lines for the new 422s (anchored plus
title; anchor no longer published; band mismatch). The endpoint screens `series_title` before
calling this function (Task 5); the service receives already-screened text.

- [ ] **Step 3: Extend `create_authored_request` and `_build_concept`**

`create_authored_request` gains two keyword args, stamped onto the row:

```python
async def create_authored_request(
    session: AsyncSession,
    principal: Principal,
    *,
    family_id: uuid.UUID,
    profile: ChildProfile | None,
    request_text: str,
    confirmation: ApprovalConfirmation,
    screening: ScreeningResult,
    series_id: uuid.UUID | None = None,
    anchor_storybook_id: str | None = None,
) -> tuple[StoryRequest, str | None]:
```

with, in the `StoryRequest(...)` constructor:

```python
        series_id=series_id,
        anchor_storybook_id=anchor_storybook_id,
```

Docstring: both args are endpoint-resolved (the endpoint validates the anchor and creates the
series row only for non-blocked outcomes).

`_build_concept` loads the anchor context just before building the brief:

```python
    anchor_context = None
    if request.anchor_storybook_id is not None:
        anchor_context = await load_anchor_context(
            session, request.anchor_storybook_id
        )
    brief = brief_from_request(request, profile, anchor_context=anchor_context)
```

Update `_build_concept`'s docstring (one line: anchored requests get their soft-continuation
context loaded here, the shared tail of both approval and authored creation).

- [ ] **Step 4: Service-level tests**

Extend the existing service test file (reuse its fixtures; do not invent new session
scaffolding). Cases:

- `create_series` derives `carries_state`: False for `'5-8'`, True for `'13-16'`.
- Approving a non-anchored pending request with `series_title="Fox Tales"` creates a Series row
  (query it), sets `request.series_id`, and still returns a concept id.
- Approving with `series_title=None` creates no Series row.
- Approving an anchored request with `series_title` raises `ValidationError`.
- Approving an anchored request whose confirmed band differs from the series band raises
  `ValidationError` (seed a published, approved, series-linked anchor; see Task 5's
  `_publish_anchor` helper and put it in a shared place if both files need it, e.g.
  `tests/integration/_series_utils.py`).
- `_build_concept` on an anchored request produces a Concept whose
  `brief["anchor_context"]["title"]` equals the anchor blob's title.

- [ ] **Step 5: Run tests and gates, then commit**

Run: `uv run pytest tests/ -q -k "service or approve or authored" && uv run ruff check . && uv run basedpyright src/`
Then: `uv run pytest tests/ -x -q` (full suite; the approve contract changed).
Expected: pass.

```bash
git add src/cyo_adventure/story_requests/service.py tests/
git commit -S -m "feat(story-requests): series ratification and anchor context in service layer (WS-B PR 3)"
```

Stage only the test files you actually touched, not `tests/` wholesale, if other work is
in flight (there should be none in this worktree).

---

### Task 5: Endpoints (kid create, authored create, approve, library fields)

depends-on: Task4 [output]

**Files:**
- Modify: `src/cyo_adventure/api/story_requests.py`, `src/cyo_adventure/api/library.py`
- Test: create `tests/integration/test_series_requests.py` (and
  `tests/integration/_series_utils.py` for the shared anchor-seeding helper)

- [ ] **Step 1: Kid create endpoint**

In `create_story_request` (`api/story_requests.py:245`), after the pending-cap check and before
the screening call, add:

```python
    series_id: uuid.UUID | None = None
    if body.anchor_storybook_id is not None:
        # #CRITICAL: security: the anchor is validated against the caller's own
        # family and the profile's band before anything persists; a kid cannot
        # anchor onto another family's book or fork a series onto a new band.
        # #VERIFY: test_series_requests.py anchor matrix (404/422 cases).
        series = await resolve_anchor(
            ctx.session,
            body.anchor_storybook_id,
            family_id=ctx.principal.family_id,
            expected_band=profile.age_band,
        )
        series_id = series.id
```

Change the screening input so a proposed title is screened with the text (one call):

```python
    screen_input = (
        f"{body.proposed_series_title}\n{body.request_text}"
        if body.proposed_series_title is not None
        else body.request_text
    )
    result = await screen_request_text(
        screen_input,
        child_names=child_names,
        openai_key=settings.openai_api_key,
        perspective_key=settings.perspective_api_key,
    )
```

And extend the `StoryRequest(...)` constructor:

```python
        series_id=series_id,
        anchor_storybook_id=body.anchor_storybook_id,
        proposed_series_title=body.proposed_series_title,
```

Import `resolve_anchor` from `cyo_adventure.story_requests.anchoring` and `uuid` if not already
imported (it is: `parse_uuid` usage implies helpers exist; check the imports block).

- [ ] **Step 2: Authored create endpoint**

In `create_authored_story_request`, after the profile block and before the screening call:

```python
    series_id: uuid.UUID | None = None
    if body.anchor_storybook_id is not None:
        anchor_series = await resolve_anchor(
            ctx.session,
            body.anchor_storybook_id,
            family_id=family_uuid,
            expected_band=body.age_band.value,
        )
        series_id = anchor_series.id
```

Screening input (same combined pattern):

```python
    screen_input = (
        f"{body.series_title}\n{body.request_text}"
        if body.series_title is not None
        else body.request_text
    )
    result = await screen_request_text(
        screen_input,
        child_names=child_names,
        openai_key=settings.openai_api_key,
        perspective_key=settings.perspective_api_key,
    )
```

Between screening and the service call, create the series only for a non-blocked outcome
(blocked rows are terminal and must leave no orphan series row):

```python
    if not result.blocked and body.series_title is not None:
        series = await service.create_series(
            ctx.session,
            ctx.principal,
            title=body.series_title,
            family_id=family_uuid,
            age_band=body.age_band.value,
        )
        series_id = series.id
```

And pass both through the service call:

```python
        series_id=series_id,
        anchor_storybook_id=body.anchor_storybook_id,
```

Update the endpoint docstring (series creation, anchoring, and the new 422s).

- [ ] **Step 3: Approve endpoint**

In `approve_story_request_endpoint`, after `_load_scoped_request` and before the service call,
screen a supplied title (the service receives screened text only):

```python
    if body.series_title is not None:
        child_names = await _family_child_names(ctx, request.family_id)
        title_screen = await screen_request_text(
            body.series_title,
            child_names=child_names,
            openai_key=settings.openai_api_key,
            perspective_key=settings.perspective_api_key,
        )
        if title_screen.blocked:
            # #CRITICAL: security: never echo blocked content back; the message
            # and value are both generic (same redaction as blocked requests).
            # #VERIFY: test_series_requests.py::test_approve_blocked_title_is_422.
            msg = "series title failed content screening"
            raise ValidationError(msg, field="series_title", value=None)
```

and extend the service call:

```python
        series_title=body.series_title,
```

Update the endpoint docstring (ratify/edit/remove semantics; anchored re-validation; new 422s).
Import `ValidationError` if the module does not already import it (it does, for `parse_uuid`
paths; verify).

- [ ] **Step 4: View mapping**

In `_to_view` (`api/story_requests.py:190`), add to the returned `StoryRequestView`:

```python
        series_id=str(request.series_id) if request.series_id is not None else None,
        proposed_series_title=(
            None if request.status == "blocked" else request.proposed_series_title
        ),
        anchor_storybook_id=request.anchor_storybook_id,
```

- [ ] **Step 5: Library listing fields**

In `api/library.py`, widen the `books` tuple collection (line ~287) to carry the series fields:

```python
    books = [
        (book.id, book.current_published_version, book.series_id, book.book_index)
        for book in rows.all()
        if book.current_published_version is not None
    ]
```

Adjust the two downstream consumers: `book_ids = [b[0] for b in books]`, the blob filter tuple
`(b[0], b[1])`, and the item build:

```python
    items = [
        _library_item(
            storybook_id,
            blobs[(storybook_id, version)],
            version,
            rating=ratings.get(storybook_id),
            state=states.get(storybook_id),
            series_id=str(series_id) if series_id is not None else None,
            book_index=book_index,
        )
        for storybook_id, version, series_id, book_index in books
        if (storybook_id, version) in blobs
    ]
```

`_library_item` gains the two keyword params and passes them to `LibraryItem(...)`:

```python
    *,
    rating: int | None = None,
    state: ReadingState | None = None,
    series_id: str | None = None,
    book_index: int | None = None,
```

- [ ] **Step 6: Integration test matrix**

Create `tests/integration/_series_utils.py` with one shared helper (used here and in Task 4's
band-mismatch test): seed a series row plus a published, approved storybook linked to it, using
the suite's existing ORM session fixtures (read `tests/integration/conftest.py` and an existing
test that seeds `Storybook`/`StorybookVersion` rows; reuse that seeding style, including
`approved_by` and `current_published_version`).

Create `tests/integration/test_series_requests.py` reusing the auth/client fixtures from
`tests/integration/test_story_requests_authored.py` (read it first; same tokens, same client
setup). Cases, each asserting status code AND persisted DB state:

Kid create:
- proposal stored: POST with `proposed_series_title` -> 201; row has the title, `series_id` is
  None.
- proposal containing a family child's name -> 201 with status `blocked` (the combined
  screening covers the title); no series anywhere.
- proposal plus anchor -> 422 (Pydantic XOR).
- anchor unknown id -> 404; anchor in another family -> 404 (seed a second family).
- anchor not published (status `draft` or unapproved version) -> 422.
- anchor published but `series_id` None -> 422.
- anchor band != profile band -> 422.
- anchor happy path -> 201; row has `series_id` = anchor's series and `anchor_storybook_id`.

Authored create (guardian token):
- `series_title` -> 201 approved; a Series row exists with `carries_state` False for `'5-8'`
  and True for `'13-16'` (two cases); row `series_id` set; `proposed_series_title` is None.
- `series_title` whose text triggers the PII guard -> 201 blocked; NO Series row exists.
- anchor happy path -> 201 approved; concept created; `series_id` = anchor's series.
- anchor band != body band -> 422.

Approve (guardian token, pending kid request):
- request with a proposal, approve body `series_title` edited -> 200; Series row has the edited
  title; `request.series_id` set; `proposed_series_title` still stored (audit trail).
- approve body omits `series_title` -> 200; no Series row (removal).
- anchored request, approve with matching band -> 200.
- anchored request, approve with a different band -> 422.
- anchored request, approve with `series_title` -> 422.
- approve body `series_title` containing a family child's name -> 422 and the response detail
  does NOT contain the submitted title.

Views:
- guardian list shows `proposed_series_title` and `anchor_storybook_id` on pending rows and
  `proposed_series_title` is None on a blocked row.
- kid library listing: a series-linked published book (seed `series_id` + `book_index=1`
  directly) surfaces `series_id` and `book_index`; a non-series book surfaces None for both.

- [ ] **Step 7: Run the matrix, the full suite, and gates, then commit**

Run: `uv run pytest tests/integration/test_series_requests.py -v`
Then: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: pass (full suite: the approve and create contracts changed; run it all).

```bash
git add src/cyo_adventure/api/story_requests.py src/cyo_adventure/api/library.py \
  tests/integration/test_series_requests.py tests/integration/_series_utils.py
git commit -S -m "feat(api): series tagging, anchoring, and ratification endpoints (WS-B PR 3)"
```

---

### Task 6: book_index assignment at generation completion

depends-on: Task1 [completion] (parallel-safe with Tasks 2-5; runs after them in serial order)

**Files:**
- Create: `src/cyo_adventure/generation/series_link.py`
- Modify: `src/cyo_adventure/generation/worker.py`
- Test: `tests/integration/test_series_link.py`

- [ ] **Step 1: Create `generation/series_link.py`**

```python
"""Series position assignment at generation completion (WS-B PR 3).

``book_index`` is assigned exactly here, when the storybook row is created,
never at request time (declined or failed requests would leave holes). The
uniqueness guard is the DB constraint plus one retry, per the ratified
umbrella decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.db.models import Storybook, StoryRequest
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_MAX_ATTEMPTS = 2


async def link_series_position(
    session: AsyncSession, *, story_id: str, concept_id: uuid.UUID
) -> None:
    """Link a freshly persisted storybook into its request's series, if any.

    Resolves the originating StoryRequest by ``concept_id``; a concept created
    outside the request flow (direct POST /concepts) has no request row and is
    a silent no-op, as is a request with no series.
    """
    request = await session.scalar(
        select(StoryRequest).where(StoryRequest.concept_id == concept_id)
    )
    if request is None or request.series_id is None:
        return
    index = await assign_book_index(
        session, story_id=story_id, series_id=request.series_id
    )
    logger.info(
        "storybook.series_position_assigned",
        storybook_id=story_id,
        series_id=str(request.series_id),
        book_index=index,
    )


async def assign_book_index(
    session: AsyncSession, *, story_id: str, series_id: uuid.UUID
) -> int:
    """Assign the next book_index in a series to a storybook row.

    # #CRITICAL: concurrency: two continuations of the same series racing on book_index
    # #VERIFY: unique constraint plus one retry on conflict; concurrency test in PR 3
    The read-compute-write is not atomic: two workers can both read
    ``max(book_index) == N`` and both try ``N + 1``. Postgres blocks the
    second flush on the first transaction's unique-index entry; once the
    first commits, the second raises IntegrityError, the savepoint unwinds,
    and the single retry recomputes against the now-visible row. A second
    consecutive conflict re-raises (three-way races are not a WS-B scale
    concern; the job then fails loudly rather than corrupting the chain).

    Returns:
        int: The assigned 1-based index.

    Raises:
        IntegrityError: If both attempts conflict.
    """
    storybook = await session.get(Storybook, story_id)
    if storybook is None:
        msg = f"storybook '{story_id}' not found for series assignment"
        raise ValueError(msg)
    last_error: IntegrityError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        next_index = await _next_index(session, series_id)
        storybook.series_id = series_id
        storybook.book_index = next_index
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError as exc:
            last_error = exc
            logger.warning(
                "storybook.book_index_conflict",
                storybook_id=story_id,
                series_id=str(series_id),
                attempt=attempt,
            )
            continue
        return next_index
    assert last_error is not None  # noqa: S101 - loop always sets it before falling through
    raise last_error


async def _next_index(session: AsyncSession, series_id: uuid.UUID) -> int:
    """Compute max(book_index) + 1 for a series (module-level for testability)."""
    current = await session.scalar(
        select(func.max(Storybook.book_index)).where(
            Storybook.series_id == series_id
        )
    )
    return int(current or 0) + 1
```

If ruff rejects the bare `assert` (S101 is usually test-only; the repo may disallow it in src),
replace the last two lines with an explicit guard:

```python
    if last_error is None:  # pragma: no cover - loop invariant
        msg = "retry loop exited without an error"
        raise RuntimeError(msg)
    raise last_error
```

Use whichever form passes `uv run ruff check .` without adding a suppression.

- [ ] **Step 2: Wire it into the worker**

In `generation/worker.py::_persist_and_moderate`, immediately after
`ctx.job_row.version = _FIRST_VERSION` (line ~417) and before the
`generation_job.storybook_persisted` log call, add:

```python
    await link_series_position(
        session, story_id=story_id, concept_id=ctx.job_row.concept_id
    )
```

Import `link_series_position` from `cyo_adventure.generation.series_link`. Placement matters: a
moderation-pipeline failure after this point rolls back the whole persist (existing behavior),
so a failed book never holds an index.

- [ ] **Step 3: Integration tests**

Create `tests/integration/test_series_link.py` using the ORM session fixtures (same conftest as
the other integration tests; read how `test_story_requests_authored.py` obtains sessions).
Seed helper reuse: `tests/integration/_series_utils.py` from Task 5 (if executing this task
before Task 5, create the helper here and Task 5 reuses it). Cases:

```python
async def test_sequential_assignment_is_contiguous(...):
    # seed series; persist two storybook rows; assign each; indices are 1 then 2.


async def test_retry_recovers_from_stale_read(...):
    # Seed series and a COMMITTED storybook at (series, 1).
    # Monkeypatch series_link._next_index to return 1 on the first call and
    # delegate to the real implementation afterwards:
    #
    #   real = series_link._next_index
    #   calls = {"n": 0}
    #   async def stale_once(session, series_id):
    #       calls["n"] += 1
    #       if calls["n"] == 1:
    #           return 1
    #       return await real(session, series_id)
    #   monkeypatch.setattr(series_link, "_next_index", stale_once)
    #
    # assign_book_index on a new row must hit a REAL IntegrityError from the
    # REAL unique constraint, retry, and return 2.


async def test_two_conflicts_raise(...):
    # Monkeypatch _next_index to always return 1 against the same seeded
    # committed row; assign_book_index raises IntegrityError.


async def test_no_series_request_is_noop(...):
    # link_series_position with a concept whose request has series_id None
    # leaves the storybook row untouched.


async def test_direct_concept_is_noop(...):
    # link_series_position with a concept_id that matches no request row
    # returns without error.
```

Write these as real tests (the comments above specify the scenario; the code is yours to write
against the suite's actual fixtures). The retry test is the concurrency test the spec mandates:
it simulates the racing read deterministically while the IntegrityError and recovery are real.

- [ ] **Step 4: Run tests and gates, then commit**

Run: `uv run pytest tests/integration/test_series_link.py -v`
Then: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: pass.

```bash
git add src/cyo_adventure/generation/series_link.py src/cyo_adventure/generation/worker.py \
  tests/integration/test_series_link.py
git commit -S -m "feat(generation): race-safe book_index assignment at completion (WS-B PR 3)"
```

---

### Task 7: Regenerate the OpenAPI client

depends-on: Task5 [completion], Task6 [completion]

**Files:**
- Modify: `frontend/src/client/*` (generated; never hand-edit)

- [ ] **Step 1: Dump the schema in-process and regenerate**

Run (from the worktree root; same recipe as PR 1/PR 2 and the CI drift gate):

```bash
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" \
  > /tmp/claude-1000/-home-byron-dev-CYO-Adventure/94ba09fb-ad7f-4e4b-a4d8-8e5454331cad/scratchpad/openapi-pr3.json
cd frontend && OPENAPI_INPUT=/tmp/claude-1000/-home-byron-dev-CYO-Adventure/94ba09fb-ad7f-4e4b-a4d8-8e5454331cad/scratchpad/openapi-pr3.json npm run generate-client
```

Expected: `git status` shows only `frontend/src/client/` changes; `types.gen.ts` now carries
`proposed_series_title`/`anchor_storybook_id` on `StoryRequestCreateBody`, `series_title` on
the approve and authored bodies, and the new `StoryRequestView`/`LibraryItem` fields.

- [ ] **Step 2: Frontend gates, then commit**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run`
Expected: pass (no consumer uses the new fields yet).

```bash
git add frontend/src/client
git commit -S -m "chore(contract): regenerate client for series fields (WS-B PR 3)"
```

---

### Task 8: Kid UI (series proposal + continue-this-story)

depends-on: Task7 [output]

**Files:**
- Modify: `frontend/src/library/storyRequestApi.ts`, `frontend/src/library/RequestStory.tsx`,
  `frontend/src/library/libraryApi.ts`, `frontend/src/library/BookCard.tsx`,
  `frontend/src/library/LibraryPage.tsx`
- Test: `frontend/src/library/RequestStory.test.tsx`, `frontend/src/library/BookCard.test.tsx`
  (or the existing card/library test file; check what exists)

- [ ] **Step 1: Extend the kid API wrapper**

In `storyRequestApi.ts`:

```typescript
export interface CreateStoryRequestExtras {
  proposedSeriesTitle?: string
  anchorStorybookId?: string
}
```

and change `create`:

```typescript
    async create(
      profileId: string,
      requestText: string,
      extras: CreateStoryRequestExtras = {}
    ): Promise<KidStoryRequest> {
      const res = await api.post<WireStoryRequest>('/v1/story-requests', {
        profile_id: profileId,
        request_text: requestText,
        ...(extras.proposedSeriesTitle !== undefined
          ? { proposed_series_title: extras.proposedSeriesTitle }
          : {}),
        ...(extras.anchorStorybookId !== undefined
          ? { anchor_storybook_id: extras.anchorStorybookId }
          : {}),
      })
      return { id: res.data.id, status: res.data.status }
    },
```

Absent fields are OMITTED, not sent as null (the mocked e2e tier asserts body shape with
`toEqual`, proving absence structurally, same convention as PR 2).

- [ ] **Step 2: Library item series fields**

In `libraryApi.ts`, add to `LibraryItemView`:

```typescript
  series_id: string | null
  book_index: number | null
```

and thread them through the wire mapping the same way the existing fields flow (read the file;
if the wrapper passes wire objects through, extending the interface is the whole change).

- [ ] **Step 3: Continue button on the book card**

`BookCard.tsx`: add to `BookCardProps` an optional `onContinue?: (item: LibraryItemView) => void`
and render, after `<StarRating .../>`:

```tsx
      {item.series_id !== null && onContinue ? (
        <Button variant="ghost" onClick={() => onContinue(item)}>
          Continue this story
        </Button>
      ) : null}
```

- [ ] **Step 4: Wire LibraryPage and RequestStory**

`RequestStory.tsx` props and new state:

```typescript
export interface ContinueAnchor {
  id: string
  title: string
}

export function RequestStory({
  profileId,
  anchor = null,
  onClearAnchor,
}: {
  profileId: string
  anchor?: ContinueAnchor | null
  onClearAnchor?: () => void
}) {
```

- `const [seriesTitle, setSeriesTitle] = useState('')`
- An effect opens the form when an anchor arrives:

```typescript
  useEffect(() => {
    if (anchor !== null) setOpen(true)
  }, [anchor])
```

- In the open form, when `anchor` is set render a friendly chip instead of the series input:

```tsx
          {anchor ? (
            <p className="request-story__continuing">
              Continuing: {anchor.title}{' '}
              <Button variant="ghost" disabled={saving} onClick={() => onClearAnchor?.()}>
                Not this one
              </Button>
            </p>
          ) : (
            <label className="request-story__label">
              Part of a series? Give it a name! (optional)
              <input
                type="text"
                value={seriesTitle}
                onChange={(e) => setSeriesTitle(e.target.value)}
                maxLength={120}
              />
            </label>
          )}
```

- `send()` builds the extras:

```typescript
      const extras = anchor
        ? { anchorStorybookId: anchor.id }
        : seriesTitle.trim().length > 0
          ? { proposedSeriesTitle: seriesTitle.trim() }
          : {}
      await requestApi.create(profileId, idea, extras)
```

  and on success also `setSeriesTitle('')` and `onClearAnchor?.()`. `cancel()` clears both too.

`LibraryPage.tsx`: hold the anchor state and pass it down:

```tsx
  const [continueAnchor, setContinueAnchor] = useState<ContinueAnchor | null>(null)
```

pass `onContinue={(item) => setContinueAnchor({ id: item.id, title: item.title })}` into each
`BookCard`, and `anchor={continueAnchor}` / `onClearAnchor={() => setContinueAnchor(null)}`
into `RequestStory`. Import `ContinueAnchor` from `./RequestStory`. Adapt to the page's actual
render structure (hero card vs shelf) so every card gets the handler.

- [ ] **Step 5: Vitest coverage**

Extend `RequestStory.test.tsx` (existing `vi.mock('../hooks/useApi')` pattern with the stable
`fakeApi`; keep it):

- typing a series name posts `proposed_series_title` alongside the idea (assert the full POST
  body with `toHaveBeenCalledWith('/v1/story-requests', {...})`).
- leaving the series name blank posts a body WITHOUT the key (assert with the exact two-key
  object).
- anchor mode: render with `anchor={{ id: 's_1', title: 'The Fox' }}`; the form is open,
  "Continuing: The Fox" is visible, no series input exists, and send posts
  `anchor_storybook_id: 's_1'` with no `proposed_series_title` key.
- "Not this one" calls `onClearAnchor`.

Extend the BookCard/library tests: the continue button renders only when `series_id` is
non-null and `onContinue` fires with the item.

- [ ] **Step 6: Run the frontend gates, then commit**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run`
Expected: pass.

```bash
git add frontend/src/library
git commit -S -m "feat(frontend): kid series proposal and continue-this-story entry (WS-B PR 3)"
```

---

### Task 9: Guardian UI (ratify at approve, authored series title)

depends-on: Task7 [output] (parallel-safe with Task 8)

**Files:**
- Modify: `frontend/src/guardian/RequestsPage.tsx`, `frontend/src/guardian/RequestStoryForm.tsx`
- Test: `frontend/src/guardian/RequestsPage.test.tsx`,
  `frontend/src/guardian/RequestStoryForm.test.tsx`

- [ ] **Step 1: Approve strip series control**

In `RequestsPage.tsx` (read the existing `decisionFor`/`setDecision` implementation first and
extend it, keeping its shape):

- The per-row decision state gains `series_title: string`, initialized from
  `req.proposed_series_title ?? ''`.
- In the confirm strip, for rows where `req.anchor_storybook_id === null`, render after the
  style select:

```tsx
                  <label>
                    Series title (optional)
                    <input
                      type="text"
                      value={decision.series_title}
                      maxLength={120}
                      onChange={(e) => setDecision(req, { series_title: e.target.value })}
                    />
                  </label>
```

- For anchored rows (`req.anchor_storybook_id !== null`): render
  `<p className="console-row__series-note">Continues an existing series</p>` instead of the
  series input, and disable the Age band select (`disabled`), since the service rejects a band
  that differs from the series band; keep its value at `req.age_band`.
- The approve payload includes the title only when non-empty:

```typescript
  async function approve(req: StoryRequestView) {
    const decision = decisionFor(req)
    const title = decision.series_title.trim()
    const payload = {
      age_band: decision.age_band,
      length: decision.length,
      narrative_style: decision.narrative_style,
      ...(title.length > 0 ? { series_title: title } : {}),
    }
    await runRowAction(req.id, () => queueApi.approve(req.id, payload))
  }
```

Adapt to the actual `queueApi.approve` signature (read the queue wrapper; if it takes the
decision object through unchanged, only the object construction here changes).

- [ ] **Step 2: Authored form series title**

In `RequestStoryForm.tsx`: add `const [seriesTitle, setSeriesTitle] = useState('')`, an input
between the request-text field and the submit button:

```tsx
        <label>
          Series title (optional)
          <input
            type="text"
            value={seriesTitle}
            maxLength={120}
            onChange={(e) => setSeriesTitle(e.target.value)}
          />
        </label>
```

and extend BOTH body branches in `submit()` with:

```typescript
              ...(seriesTitle.trim().length > 0
                ? { series_title: seriesTitle.trim() }
                : {}),
```

Reset `setSeriesTitle('')` in the success branch alongside the other resets.

- [ ] **Step 3: Vitest coverage**

`RequestsPage.test.tsx`:
- a pending row with `proposed_series_title: 'Fox Tales'` prefills the series input; approving
  sends `series_title: 'Fox Tales'` in the body (assert the full payload).
- clearing the input and approving sends a body WITHOUT the `series_title` key.
- an anchored row (`anchor_storybook_id: 's_1'`) shows "Continues an existing series", has no
  series input, and its band select is disabled.
- NOTE: the mocked request fixtures in this file gain the three new view fields
  (`series_id: null, proposed_series_title: null, anchor_storybook_id: null` by default);
  update every fixture the file defines.

`RequestStoryForm.test.tsx`:
- guardian submit with a series title includes `series_title` in the POST body; without it the
  key is absent (extend the existing full-body assertions).

- [ ] **Step 4: Run the frontend gates, then commit**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run`
Expected: pass.

```bash
git add frontend/src/guardian
git commit -S -m "feat(frontend): guardian series ratification and authored series title (WS-B PR 3)"
```

---

### Task 10: e2e updates, both tiers

depends-on: Task8 [completion], Task9 [completion]

**Files:**
- Modify: `frontend/e2e/story-requests-kid.spec.ts`, `frontend/e2e/story-requests.spec.ts`,
  `frontend/e2e/story-requests-authored.spec.ts`, `frontend/e2e-real/authored-request.spec.ts`

- [ ] **Step 1: Mocked-tier kid cases**

In `story-requests-kid.spec.ts` (same `page.route` + `postDataJSON` + full-body `toEqual`
pattern as the existing test):

- new test: filling the series name posts
  `{ profile_id: 'p1', request_text: ..., proposed_series_title: 'Fox Tales' }` (exact
  `toEqual`, proving no anchor key).
- new test: continue flow. Mock the library route with one series-tagged book (full
  `LibraryItem` shape; base it on whatever fixture the library specs already use and add
  `series_id: 'ser-1', book_index: 1`; non-series books get `series_id: null,
  book_index: null`). Click "Continue this story", verify the form opens showing
  "Continuing:", fill the idea, send, and assert the body equals
  `{ profile_id: 'p1', request_text: ..., anchor_storybook_id: <book id> }`.

- [ ] **Step 2: Mocked-tier guardian cases**

In `story-requests.spec.ts`: the existing fixtures (`DRAGON_REQUEST` etc.) gain
`series_id: null, proposed_series_title: null, anchor_storybook_id: null`. Add one test: a
request fixture with `proposed_series_title: 'Dragon Tales'`; approve after choosing a length;
assert the approve body equals
`{ age_band: ..., length: 'medium', narrative_style: 'prose', series_title: 'Dragon Tales' }`.

In `story-requests-authored.spec.ts`: extend one guardian case to fill the series title and
assert it appears in the body; keep one case asserting the key is absent when the field is
blank.

- [ ] **Step 3: Run the mocked tier**

Run: `cd frontend && npx playwright test e2e/story-requests-kid.spec.ts e2e/story-requests.spec.ts e2e/story-requests-authored.spec.ts`
Expected: all pass. Then run the full mocked tier (`npx playwright test e2e`) to catch fixture
drift in other specs.

- [ ] **Step 4: Real-tier spec (typecheck-only, same disclosure as PR 1/PR 2)**

Extend `frontend/e2e-real/authored-request.spec.ts` with a series-title submission variant
(fill the new input before sending). Do not run the real tier; it stays typecheck/lint clean
and its non-execution is disclosed in the PR body.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e frontend/e2e-real
git commit -S -m "test(e2e): series proposal, continuation, and ratification flows (WS-B PR 3)"
```

---

### Task 11: CHANGELOG, full gates, and PR

depends-on: everything above

- [ ] **Step 1: CHANGELOG entry**

Add under the Unreleased section (match the existing entry style exactly; read the file):
one `### Added` bullet: series tagging and soft continuation for story requests (kid proposal
and continue-this-story, guardian ratification at approval, authored series creation, and
race-safe series book numbering at generation completion).

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): series tagging and soft continuation entry (WS-B PR 3)"
```

- [ ] **Step 2: Full backend gates**

Run: `uv run pytest --cov=src --cov-fail-under=80 -q`
Expected: pass, coverage at or above the current baseline (96%+).
Run: `uv run ruff check . && uv run ruff format --check . && uv run basedpyright src/ && uv run bandit -r src -q`
Expected: clean (bandit's single pre-existing Medium B104 in middleware/security.py:376 is not
from this branch).

- [ ] **Step 3: Full frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run && npm run build`
Expected: clean.

- [ ] **Step 4: Client-drift self-check**

Re-run the Task 7 schema dump + generate-client; `git status` must show no changes (backend
docstring edits change the schema, so any post-Task-7 endpoint-docstring change requires a
regen commit; this is the drift gate CI enforces).

- [ ] **Step 5: pre-commit on all files**

Run: `pre-commit run --all-files`
Expected: all hooks pass.

- [ ] **Step 6: Push and open the PR**

Abort if: any gate above failed.

```bash
git push -u origin feat/ws-b-series-continuation
gh pr create --title "feat(story-requests): series tagging and soft continuation (WS-B PR 3)" \
  --body-file <path to the prepared PR body>
```

PR body sections (mirror PR #164/#165): Summary; Changes (migration, anchoring, service,
endpoints, worker, frontend); Security (anchor 404-over-403, screened titles, blocked-title
redaction, band-fork rejection, book_index race guard); Impact; Testing checklist with real
numbers; Notes (e2e-real tier not executed; anchored authored requests API-only, no picker UI;
Series document metadata deliberately not embedded, SR rules dormant until WS-G). Do NOT
auto-merge; the owner merges.

---

## Self-review record

Checks run against the spec (sections 1, 2, 4, 5, 6) after drafting:

1. **Clause coverage**: every spec clause for PR 3 maps to a task: series table columns
   (Task 1); request columns + XOR (Task 1); storybook UNIQUE + retry guard with the mandated
   RAD pair verbatim (Tasks 1 and 6); kid create extension (Tasks 2, 5); guardian ratify /
   edit / remove at approve (Tasks 2, 4, 5, 9); authored direct series creation (Tasks 2, 4,
   5, 9); anchor validation at creation AND approval incl. published + family + band (Tasks 3,
   4, 5); band inheritance with mismatch rejection (Tasks 3, 4, 5); anchor_context in the brief
   (Task 3; prompt reach verified: build_structure_prompt serializes the whole brief, and
   skeleton-fill's theme_brief is the whole concept.brief); book_index at completion, not
   request time (Task 6); concurrency test (Task 6); anchor rejection matrix tests (Task 5);
   title length-cap + screening for every initiator (Tasks 2, 5); e2e both tiers (Task 10);
   client regen via the drift-gate recipe (Task 7); episodic/carry band rule (Tasks 1, 4).
2. **Deliberate scope decisions**: no anchor picker on the authored form (decision 10); a
   moderation-rejected book keeps its index (decision 8); `proposed_series_title` kept on
   approved kid rows as audit trail but redacted on blocked rows; guardian may set a title even
   without a kid proposal (decision 3). "How it ended" extraction is deterministic excerpts,
   not an LLM summary (decision 7); revisit in WS-G if thematic follow-on proves weak.
3. **Type consistency**: `series_id` is UUID in the DB/ORM and `str | None` in every view;
   `anchor_storybook_id` is `String(120)`/`str` everywhere (storybook PK is a string);
   `SeriesTitle`/`AnchorId` cap at 120 matching the column widths; `expected_band` is the plain
   string value (`.value` at enum call sites).
4. **Test-helper consistency**: migration tests reuse `_migration_utils` + `migration_pg_url`;
   endpoint tests reuse the authored-suite fixtures; the anchor-seeding helper is shared via
   `_series_utils.py`; frontend tests keep the stable-`fakeApi` `vi.mock` pattern; e2e keeps
   full-body `toEqual` assertions.
5. **Known verify-at-implementation points** (flagged in-task, not placeholders): exact enum
   member names in schema tests; the initial-schema minimal-row columns for seeding storybook
   rows in migration tests; `decisionFor`'s exact shape; `queueApi.approve`'s signature;
   whether ruff permits the `assert` form in Task 6.
