---
schema_type: planning
title: "WS-D: Pipeline Event Log Implementation Plan"
description: "Task-level implementation plan for workstream D: the append-only pipeline_event
  table, the record_event writer, and instrumentation of every story-lifecycle transition, with
  complete code, TDD steps, and verification commands."
tags:
  - planning
  - observability
  - implementation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an engineer with zero project context everything needed to implement WS-D task by
  task: exact files, complete code, test-first steps, and verification commands."
component: Strategy
source: "docs/planning/ws-d-pipeline-event-log-spec.md (ratified 2026-07-08); codebase discovery
  2026-07-08 against origin/main d17ccce."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Add an append-only `pipeline_event` table and write one event row from the transaction that
performs each of the 14 enumerated story-lifecycle transitions, the capture layer the WS-F
suggestion dashboard will learn from.

## Architecture

A single `record_event(session, actor, ...)` writer adds a `PipelineEvent` row to the caller's
session and `flush()`es, so the event inherits that transaction (atomic with the transition per
spec decision D1). API transitions pass `Actor.from_principal(ctx.principal)`; system
transitions (worker, moderation) pass `Actor.system()` (`actor_id=NULL`, `actor_role='system'`).
Payloads are PII-free structured dicts gated by a per-event-type key allowlist and its test.
Append-only is enforced by a Postgres trigger created in the migration.

## Tech Stack

Python 3.12, async SQLAlchemy 2.x (typed ORM), FastAPI, Alembic, Postgres 16, pytest +
pytest-asyncio + testcontainers (real Postgres). Package rules: handlers/services never
`commit()` (unit-of-work commits at request end); every async DB function carries RAD markers
(`src/cyo_adventure/CLAUDE.md`); raise only from `core/exceptions.py`; BasedPyright strict.

## Deviations from the spec (flagged for reviewers)

- **`generation_finished` payload drops `book_index`.** The series `book_index` lives on the
  storybook row, not in scope at `_persist_passed_outcome` (the job-finish point). It is
  joinable from the storybook by `entity_id`; omitting it avoids threading state through the
  worker for a value WS-F can derive.
- **`released` payload drops `visibility`.** The `Storybook.visibility` column is introduced by
  WS-E and does not exist yet on `main`. Adding it here would be a forward reference.

Both are payload-only reductions; the event rows themselves are unchanged. If WS-E lands first,
a follow-up adds `visibility` to the `released` payload.

## File Structure

**Create:**
- `src/cyo_adventure/events/__init__.py` -- public exports (`record_event`, `Actor`, `EventType`).
- `src/cyo_adventure/events/models.py` -- `EventType` StrEnum, `Actor` value object.
- `src/cyo_adventure/events/writer.py` -- `record_event` + the payload-key allowlist.
- `migrations/versions/20260708_1800_add_pipeline_event.py` -- table, indexes, append-only trigger.
- `tests/unit/test_pipeline_event_writer.py` -- writer + allowlist unit tests.
- `tests/integration/test_pipeline_event_migration.py` -- migration round-trip + append-only.
- `tests/integration/test_pipeline_event_instrumentation.py` -- per-transition event assertions.
- `tests/integration/_event_assertions.py` -- shared `fetch_events` / `assert_single_event` helper.

**Modify:**
- `src/cyo_adventure/db/models.py` -- add `PipelineEvent` model (mirrors `ModerationThresholdAudit`).
- `src/cyo_adventure/story_requests/service.py` -- `create_authored_request`, `approve_story_request`, `decline_story_request` (refactor to async+session).
- `src/cyo_adventure/api/story_requests.py` -- kid `create_story_request`; the `decline` call site.
- `src/cyo_adventure/story_requests/authoring_plan.py` -- `build_authoring_plan` (thread `actor`).
- `src/cyo_adventure/generation/worker.py` -- `_load_and_start_job`, `_persist_passed_outcome`, `_record_failure`.
- `src/cyo_adventure/moderation/pipeline.py` -- outcome + repair-adoption points.
- `src/cyo_adventure/publishing/service.py` -- `approve`, `send_back`.
- `src/cyo_adventure/api/moderation_thresholds.py` -- `upsert_threshold`, `delete_threshold`, `update_noise_floor`.
- `src/cyo_adventure/api/assignments.py` -- `assign_storybook`.
- `src/cyo_adventure/api/ratings.py` -- `record_rating`.
- `CHANGELOG.md` -- feature entry.

---

## Task 1: Event module (EventType, Actor, record_event, allowlist)

**Files:**
- Create: `src/cyo_adventure/events/models.py`, `src/cyo_adventure/events/writer.py`, `src/cyo_adventure/events/__init__.py`
- Test: `tests/unit/test_pipeline_event_writer.py`

- [ ] **Step 1: Write `events/models.py`**

```python
"""Value types for the pipeline event log (WS-D capture layer)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class EventType(StrEnum):
    """Every enumerated story-lifecycle transition (spec section 'Event taxonomy')."""

    REQUEST_CREATED = "request_created"
    REQUEST_APPROVED = "request_approved"
    REQUEST_DECLINED = "request_declined"
    PLAN_ASSIGNED = "plan_assigned"
    GENERATION_STARTED = "generation_started"
    GENERATION_FINISHED = "generation_finished"
    MODERATION_COMPLETED = "moderation_completed"
    REPAIR_APPLIED = "repair_applied"
    SENT_BACK = "sent_back"
    RELEASED = "released"
    THRESHOLD_CHANGED = "threshold_changed"
    NOISE_FLOOR_CHANGED = "noise_floor_changed"
    BOOK_ASSIGNED = "book_assigned"
    RATED = "rated"


SYSTEM_ACTOR_ROLE = "system"


@dataclass(frozen=True)
class Actor:
    """Who caused a transition. System transitions carry no user id."""

    actor_id: uuid.UUID | None
    actor_role: str

    @classmethod
    def from_principal(cls, principal: object) -> Actor:
        """Build an Actor from an api.deps.Principal (duck-typed to avoid an import cycle).

        # #ASSUME: data-integrity: principal exposes user_id (uuid) and role (StrEnum)
        # #VERIFY: covered by the per-transition integration tests that pass a real Principal
        """
        return cls(
            actor_id=principal.user_id,  # type: ignore[attr-defined]
            actor_role=str(principal.role),  # type: ignore[attr-defined]
        )

    @classmethod
    def system(cls) -> Actor:
        """The actor for worker/moderation transitions with no request principal."""
        return cls(actor_id=None, actor_role=SYSTEM_ACTOR_ROLE)
```

- [ ] **Step 2: Write `events/writer.py` (writer + allowlist)**

```python
"""Append a PipelineEvent row from the transaction performing a transition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events.models import Actor, EventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Per-event-type payload key allowlist. Keys not listed are rejected before write.
# This is the enforcement mechanism for the PII-free payload contract (spec D3):
# ids, enum values, scores, counts, controlled-vocab reasons only; never free text.
_PAYLOAD_ALLOWLIST: dict[EventType, frozenset[str]] = {
    EventType.REQUEST_CREATED: frozenset({"initiator_role"}),
    EventType.REQUEST_APPROVED: frozenset({"series_created", "anchor_resolved", "series_id"}),
    EventType.REQUEST_DECLINED: frozenset(),
    EventType.PLAN_ASSIGNED: frozenset({"job_status", "plan_kind"}),
    EventType.GENERATION_STARTED: frozenset(),
    EventType.GENERATION_FINISHED: frozenset({"outcome", "provider", "model", "prompt_version"}),
    EventType.MODERATION_COMPLETED: frozenset({"overall_verdict", "repaired", "counts"}),
    EventType.REPAIR_APPLIED: frozenset({"stage"}),
    EventType.SENT_BACK: frozenset(),
    EventType.RELEASED: frozenset(),
    EventType.THRESHOLD_CHANGED: frozenset(
        {"age_band", "category", "action", "min_verdict", "min_score"}
    ),
    EventType.NOISE_FLOOR_CHANGED: frozenset({"value"}),
    EventType.BOOK_ASSIGNED: frozenset({"child_profile_id"}),
    EventType.RATED: frozenset({"value", "is_update"}),
}


def _validate_payload(event_type: EventType, payload: dict[str, object]) -> None:
    allowed = _PAYLOAD_ALLOWLIST[event_type]
    extra = set(payload) - allowed
    if extra:
        msg = f"payload for {event_type} has disallowed keys: {sorted(extra)}"
        raise ValidationError(msg, field="payload", value=sorted(extra))


async def record_event(
    session: AsyncSession,
    actor: Actor,
    *,
    entity_type: str,
    entity_id: str,
    event_type: EventType,
    from_state: str | None = None,
    to_state: str | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    """Add one append-only PipelineEvent to the caller's session and flush.

    The row inherits the caller's transaction: it commits with the transition and
    rolls back with it (spec decision D1). Never opens or commits its own transaction.

    # #CRITICAL: data-integrity: an event with an out-of-contract payload would leak
    #   PII into a durable append-only log (spec D3).
    # #VERIFY: _validate_payload rejects any key outside the per-event allowlist;
    #   tested in tests/unit/test_pipeline_event_writer.py.
    # #CRITICAL: external-resources: this writes to Postgres inside the caller's unit
    #   of work; a failure here must roll the transition back, not be swallowed.
    # #VERIFY: no try/except; the exception propagates to the unit-of-work.
    """
    data = payload or {}
    _validate_payload(event_type, data)
    session.add(
        PipelineEvent(
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=str(event_type),
            from_state=from_state,
            to_state=to_state,
            payload=data,
        )
    )
    await session.flush()
```

- [ ] **Step 3: Write `events/__init__.py`**

```python
"""Pipeline event log (WS-D): append-only capture of lifecycle transitions."""

from __future__ import annotations

from cyo_adventure.events.models import SYSTEM_ACTOR_ROLE, Actor, EventType
from cyo_adventure.events.writer import record_event

__all__ = ["SYSTEM_ACTOR_ROLE", "Actor", "EventType", "record_event"]
```

- [ ] **Step 4: Write the failing unit test** (`tests/unit/test_pipeline_event_writer.py`)

```python
"""Unit tests for the pipeline-event writer and payload allowlist."""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.events import Actor, EventType
from cyo_adventure.events.models import SYSTEM_ACTOR_ROLE
from cyo_adventure.events.writer import _PAYLOAD_ALLOWLIST, _validate_payload


def test_every_event_type_has_an_allowlist_entry() -> None:
    assert set(_PAYLOAD_ALLOWLIST) == set(EventType)


def test_validate_payload_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError, match="disallowed keys"):
        _validate_payload(EventType.RATED, {"value": 5, "child_name": "Ada"})


def test_validate_payload_accepts_allowlisted_keys() -> None:
    _validate_payload(EventType.RATED, {"value": 5, "is_update": True})


def test_actor_system_has_no_user_id() -> None:
    actor = Actor.system()
    assert actor.actor_id is None
    assert actor.actor_role == SYSTEM_ACTOR_ROLE


def test_actor_from_principal_copies_id_and_role() -> None:
    uid = uuid.uuid4()

    class _P:
        user_id = uid
        role = "admin"

    actor = Actor.from_principal(_P())
    assert actor.actor_id == uid
    assert actor.actor_role == "admin"
```

- [ ] **Step 5: Run the test, expect failure** (PipelineEvent not yet in models)

Run: `cd /home/byron/dev/CYO_Adventure/.worktrees/ws-d && uv run pytest tests/unit/test_pipeline_event_writer.py -v`
Expected: FAIL at import (`cannot import name 'PipelineEvent'`). This is expected; Task 2 adds it.

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/events/ tests/unit/test_pipeline_event_writer.py
git commit -S -m "feat(events): pipeline event writer, EventType, and payload allowlist"
```

---

## Task 2: PipelineEvent model

depends-on: Task1 [output] (imports `PipelineEvent`)

**Files:**
- Modify: `src/cyo_adventure/db/models.py`

- [ ] **Step 1: Add the model** (append near `ModerationThresholdAudit`; mirror its shape)

```python
class PipelineEvent(Base):
    """Append-only log of every story-lifecycle transition (WS-D capture layer).

    Written from the transaction performing the transition (spec decision D1). Rows
    are enforced append-only by a DB trigger created in the migration; the ORM never
    updates or deletes them. ``actor_id`` is NULL for system transitions (worker,
    moderation), which carry ``actor_role='system'`` (spec decision D2). ``payload``
    is PII-free by contract, gated by events/writer.py::_PAYLOAD_ALLOWLIST (D3).
    """

    __tablename__ = "pipeline_event"
    __table_args__ = (
        Index("ix_pipeline_event_entity", "entity_type", "entity_id"),
        Index("ix_pipeline_event_event_type", "event_type"),
        Index("ix_pipeline_event_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), nullable=True
    )
    actor_role: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(48))
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
```

Note: `sa_text` is `sqlalchemy.text`. If `db/models.py` does not already import it, add
`from sqlalchemy import text as sa_text` to the existing `from sqlalchemy import (...)` block
(check first: `grep -n "text as sa_text\|^from sqlalchemy import" src/cyo_adventure/db/models.py`).

- [ ] **Step 2: Run the Task 1 unit test again, expect pass**

Run: `uv run pytest tests/unit/test_pipeline_event_writer.py -v`
Expected: PASS (import now resolves).

- [ ] **Step 3: Type-check**

Run: `uv run basedpyright src/cyo_adventure/db/models.py src/cyo_adventure/events/`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add src/cyo_adventure/db/models.py
git commit -S -m "feat(events): add append-only PipelineEvent model"
```

---

## Task 3: Migration (table, indexes, append-only trigger) + round-trip test

depends-on: Task2 [completion]

**Files:**
- Create: `migrations/versions/20260708_1800_add_pipeline_event.py`
- Create: `tests/integration/test_pipeline_event_migration.py`

- [ ] **Step 1: Write the migration**

```python
"""Add append-only pipeline_event table (WS-D).

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-08 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

_APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION pipeline_event_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'pipeline_event is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER trg_pipeline_event_append_only
BEFORE UPDATE OR DELETE ON pipeline_event
FOR EACH ROW EXECUTE FUNCTION pipeline_event_append_only();
"""


def upgrade() -> None:
    """Create pipeline_event, its indexes, and the append-only trigger."""
    op.create_table(
        "pipeline_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("actor_role", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=True),
        sa.Column(
            "payload",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_pipeline_event_entity", "pipeline_event", ["entity_type", "entity_id"]
    )
    op.create_index("ix_pipeline_event_event_type", "pipeline_event", ["event_type"])
    op.create_index(
        "ix_pipeline_event_occurred_at", "pipeline_event", ["occurred_at"]
    )
    op.execute(_APPEND_ONLY_FN)
    op.execute(_APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    """Drop the trigger, function, indexes, and table."""
    op.execute("DROP TRIGGER IF EXISTS trg_pipeline_event_append_only ON pipeline_event")
    op.execute("DROP FUNCTION IF EXISTS pipeline_event_append_only()")
    op.drop_index("ix_pipeline_event_occurred_at", table_name="pipeline_event")
    op.drop_index("ix_pipeline_event_event_type", table_name="pipeline_event")
    op.drop_index("ix_pipeline_event_entity", table_name="pipeline_event")
    op.drop_table("pipeline_event")
```

Note: if `import sqlalchemy as sa` does not expose `sa.dialects.postgresql`, add
`from sqlalchemy.dialects import postgresql` and use `postgresql.JSONB()` instead (match whatever
a prior migration that uses JSONB does; `grep -rn "JSONB" migrations/versions/`).

- [ ] **Step 2: Write the round-trip + append-only test**

```python
"""Round-trip and append-only-trigger tests for the WS-D pipeline_event migration."""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

REVISION = "f2a3b4c5d6e7"
DOWN_REVISION = "e1f2a3b4c5d6"


def _env(pg_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["CYO_ADVENTURE_DATABASE_URL"] = pg_url
    return env


@pytest.fixture
def upgraded_engine(migration_pg_url: str) -> sa.engine.Engine:
    """Land on DOWN_REVISION, then upgrade to REVISION; yield a sync engine."""
    env = _env(migration_pg_url)
    up = run_alembic(PROJECT_ROOT, env, "upgrade", DOWN_REVISION)
    assert up.returncode == 0, up.stderr
    result = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr
    sync_url = migration_pg_url.replace("+asyncpg", "+psycopg")
    return sa.create_engine(sync_url)


def _insert_event(conn: sa.Connection) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO pipeline_event "
            "(id, actor_role, entity_type, entity_id, event_type) "
            "VALUES (:id, 'system', 'storybook', 's_x', 'generation_started')"
        ),
        {"id": event_id},
    )
    return event_id


def test_insert_is_allowed(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        _insert_event(conn)


def test_update_is_rejected(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        event_id = _insert_event(conn)
    with (
        upgraded_engine.connect() as conn,
        pytest.raises(DBAPIError, match="append-only"),
        conn.begin(),
    ):
        conn.execute(
            sa.text("UPDATE pipeline_event SET to_state = 'x' WHERE id = :id"),
            {"id": event_id},
        )


def test_delete_is_rejected(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        event_id = _insert_event(conn)
    with (
        upgraded_engine.connect() as conn,
        pytest.raises(DBAPIError, match="append-only"),
        conn.begin(),
    ):
        conn.execute(
            sa.text("DELETE FROM pipeline_event WHERE id = :id"), {"id": event_id}
        )


def test_truncate_bypasses_the_trigger(upgraded_engine: sa.engine.Engine) -> None:
    """TRUNCATE is a statement-level op; row triggers do not fire, so teardown works."""
    with upgraded_engine.begin() as conn:
        _insert_event(conn)
    with upgraded_engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE pipeline_event"))
        remaining = conn.execute(
            sa.text("SELECT count(*) FROM pipeline_event")
        ).scalar_one()
    assert remaining == 0


def test_downgrade_removes_table_and_function(
    upgraded_engine: sa.engine.Engine,
) -> None:
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
        fns = {
            r[0]
            for r in conn.execute(
                sa.text("SELECT proname FROM pg_proc WHERE proname = :n"),
                {"n": "pipeline_event_append_only"},
            )
        }
    assert "pipeline_event" not in tables
    assert not fns
    up = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert up.returncode == 0, up.stderr
```

- [ ] **Step 3: Run the migration test**

Run: `uv run pytest tests/integration/test_pipeline_event_migration.py -v`
Expected: 5 passed. (Requires Docker for testcontainers; skips locally if absent, fails in CI if `CI` truthy.)

- [ ] **Step 4: Verify single head**

Run: `uv run alembic heads`
Expected: exactly one head, `f2a3b4c5d6e7 (head)`.
Abort if: two heads appear (a WS-C migration merged onto `e1f2a3b4c5d6`; rebase and bump `down_revision`).

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260708_1800_add_pipeline_event.py tests/integration/test_pipeline_event_migration.py
git commit -S -m "feat(events): pipeline_event migration with append-only trigger"
```

---

## Task 4: Shared event-assertion test helper

depends-on: Task2 [completion]

**Files:**
- Create: `tests/integration/_event_assertions.py`

This helper keeps every per-transition test in Task 5+ short and complete (reuses one query
path rather than each test inventing its own). Underscore-prefixed so pytest does not collect it.

- [ ] **Step 1: Write the helper**

```python
"""Shared assertions for pipeline_event instrumentation tests.

Underscore-prefixed module name so pytest does not collect it as a test module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa

from cyo_adventure.db.models import PipelineEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession


async def fetch_events(
    sessions: async_sessionmaker[AsyncSession], event_type: str
) -> list[PipelineEvent]:
    """Return all pipeline_event rows of a given event_type, oldest first."""
    async with sessions() as session:
        rows = await session.execute(
            sa.select(PipelineEvent)
            .where(PipelineEvent.event_type == event_type)
            .order_by(PipelineEvent.occurred_at)
        )
        return list(rows.scalars())


async def assert_single_event(
    sessions: async_sessionmaker[AsyncSession],
    *,
    event_type: str,
    entity_type: str,
    to_state: str | None = None,
    actor_role: str | None = None,
    actor_is_system: bool | None = None,
) -> PipelineEvent:
    """Assert exactly one event of event_type exists and matches the given fields."""
    events = await fetch_events(sessions, event_type)
    assert len(events) == 1, f"expected 1 {event_type}, found {len(events)}"
    event = events[0]
    assert event.entity_type == entity_type
    if to_state is not None:
        assert event.to_state == to_state
    if actor_role is not None:
        assert event.actor_role == actor_role
    if actor_is_system is not None:
        assert (event.actor_id is None) == actor_is_system
    return event
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/_event_assertions.py
git commit -S -m "test(events): shared pipeline-event assertion helper"
```

---

## Task 5: Instrument story-request transitions

depends-on: Task1 [completion], Task4 [completion]

Covers `request_created` (kid + authored), `request_approved`, `request_declined`. The decline
function is refactored from sync/sessionless to `async` + session so it can write an event.

**Files:**
- Modify: `src/cyo_adventure/api/story_requests.py`, `src/cyo_adventure/story_requests/service.py`
- Test: `tests/integration/test_pipeline_event_instrumentation.py`

- [ ] **Step 1: Instrument kid create** in `api/story_requests.py::create_story_request`

Find the line `await ctx.session.flush()` after the `StoryRequest(...)` add (discovery: ~L350).
Immediately after it, insert:

```python
        await record_event(
            ctx.session,
            Actor.from_principal(ctx.principal),
            entity_type="story_request",
            entity_id=str(request.id),
            event_type=EventType.REQUEST_CREATED,
            to_state=request.status,
            payload={"initiator_role": request.initiator_role},
        )
```

Add the import at the top of the file: `from cyo_adventure.events import Actor, EventType, record_event`.

- [ ] **Step 2: Instrument authored create** in `service.py::create_authored_request`

After the `session.add(request)` + `await session.flush()` (discovery: ~L353), and only on the
non-blocked path is not required (event fires for both; `to_state` records `blocked`), insert:

```python
    await record_event(
        session,
        Actor.from_principal(principal),
        entity_type="story_request",
        entity_id=str(request.id),
        event_type=EventType.REQUEST_CREATED,
        to_state=request.status,
        payload={"initiator_role": request.initiator_role},
    )
```

Add the import: `from cyo_adventure.events import Actor, EventType, record_event`.

- [ ] **Step 3: Instrument approve** in `service.py::approve_story_request`

In the `_build_concept` tail, after `request.status = "approved"` and `request.reviewed_by` are
set (discovery: ~L272-275), insert (compute the two booleans from what the approve path already
knows; `series_created` is True when `create_series` ran, `anchor_resolved` when an anchor was
re-validated):

```python
    await record_event(
        session,
        Actor.from_principal(principal),
        entity_type="story_request",
        entity_id=str(request.id),
        event_type=EventType.REQUEST_APPROVED,
        from_state="pending",
        to_state="approved",
        payload={
            "series_created": series_created,
            "anchor_resolved": anchor_resolved,
            "series_id": str(request.series_id) if request.series_id else None,
        },
    )
```

If `_build_concept` does not have `series_created`/`anchor_resolved` in scope, thread them as
parameters from `approve_story_request` (which computes them at ~L195-218) into `_build_concept`,
defaulting both to `False` for the non-approve callers of `_build_concept`.

- [ ] **Step 4: Refactor decline to async+session** in `service.py::decline_story_request`

Current (discovery ~L360): `def decline_story_request(principal, request)` (sync, sessionless).
Replace with:

```python
async def decline_story_request(
    session: AsyncSession, principal: Principal, request: StoryRequest
) -> None:
    """Decline a pending request and record the transition.

    # #CRITICAL: security: only the guardian's own family or an admin may decline;
    #   the endpoint enforces this before calling (api/story_requests.py).
    # #VERIFY: covered by existing decline authorization tests.
    """
    ensure_pending(request)
    request.status = "declined"
    request.reviewed_by = principal.user_id
    request.reviewed_at = datetime.now(UTC)
    await record_event(
        session,
        Actor.from_principal(principal),
        entity_type="story_request",
        entity_id=str(request.id),
        event_type=EventType.REQUEST_DECLINED,
        from_state="pending",
        to_state="declined",
    )
```

Keep the existing `ensure_pending`/field-assignment lines; only the signature, `async`, and the
`record_event` call are new. Confirm `AsyncSession`, `Principal`, `datetime`, `UTC` are imported
in `service.py` (they are used elsewhere in the module; `grep -n "AsyncSession\|^from datetime"`).

- [ ] **Step 5: Update the decline call site** in `api/story_requests.py`

Find the `decline_story_request(...)` call in the decline endpoint (discovery ~L783 handler) and
change it to await with the session:

```python
    await decline_story_request(ctx.session, ctx.principal, request)
```

- [ ] **Step 6: Write the tests** (append to `tests/integration/test_pipeline_event_instrumentation.py`; create the file with this header if new)

```python
"""Integration tests: every lifecycle transition writes exactly one pipeline_event."""

from __future__ import annotations

import pytest

from tests.integration._event_assertions import assert_single_event
from tests.integration.conftest import Seed, auth

if False:  # typing-only imports kept out of runtime
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_kid_create_writes_request_created(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    resp = await client.post(
        "/api/v1/story-requests",
        headers=auth(seed.child_token),
        json={"request_text": "a story about a brave fox"},
    )
    assert resp.status_code in (200, 201), resp.text
    await assert_single_event(
        sessions,
        event_type="request_created",
        entity_type="story_request",
        actor_role="child",
    )


@pytest.mark.asyncio
async def test_decline_writes_request_declined(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        "/api/v1/story-requests",
        headers=auth(seed.child_token),
        json={"request_text": "a story about a brave fox"},
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"/api/v1/story-requests/{request_id}/decline",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_declined",
        entity_type="story_request",
        to_state="declined",
        actor_role="guardian",
    )
```

Note: the exact create-request body and decline route are the current shapes from discovery;
if the request schema requires more fields (e.g. no free-text screening trips `blocked`), read
`api/story_requests.py` request model and adjust the JSON. The `request_approved` test needs the
guardian approve flow; add it mirroring the decline test using the `approve` endpoint and
asserting `event_type="request_approved"`, `to_state="approved"`.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/integration/test_pipeline_event_instrumentation.py -v`
Expected: story-request tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/cyo_adventure/api/story_requests.py src/cyo_adventure/story_requests/service.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument story-request created/approved/declined"
```

---

## Task 6: Instrument plan assignment

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/story_requests/authoring_plan.py`, and its caller `api/story_requests.py::create_authoring_plan`

- [ ] **Step 1: Thread an `actor` into `build_authoring_plan`**

Change the signature `async def build_authoring_plan(session, request, concept, plan)` to accept
`actor: Actor` and, after the `session.add(job)` + `await session.flush()` (discovery ~L198-199),
insert:

```python
    await record_event(
        session,
        actor,
        entity_type="generation_job",
        entity_id=str(job.id),
        event_type=EventType.PLAN_ASSIGNED,
        to_state=job.status,
        payload={"job_status": job.status, "plan_kind": plan.method},
    )
```

Import: `from cyo_adventure.events import Actor, EventType, record_event`. If `plan.method` is
not the attribute name for the plan kind, use the field that distinguishes skeleton_fill vs
automated (read the `plan` type; discovery said status is `awaiting_manual_fill` for
skeleton+skill else `queued`, so `payload={"job_status": job.status}` alone is acceptable if no
clean plan-kind field exists, drop `plan_kind` and its allowlist entry in that case).

- [ ] **Step 2: Update the caller** in `api/story_requests.py::create_authoring_plan`

Pass the admin actor: `await build_authoring_plan(ctx.session, request, concept, plan, actor=Actor.from_principal(ctx.principal))` (match the existing call's argument order; add the import).

- [ ] **Step 3: Add a test** to `test_pipeline_event_instrumentation.py`

Drive the admin authoring-plan endpoint against an approved request and assert:

```python
    await assert_single_event(
        sessions,
        event_type="plan_assigned",
        entity_type="generation_job",
        actor_role="admin",
    )
```

(Arrange: create a request, approve it as guardian/admin, then POST the authoring plan as
`seed.admin_token`. Reuse the approve arrangement from Task 5's approved test.)

- [ ] **Step 4: Run + commit**

Run: `uv run pytest tests/integration/test_pipeline_event_instrumentation.py -k plan -v` (expect PASS)

```bash
git add src/cyo_adventure/story_requests/authoring_plan.py src/cyo_adventure/api/story_requests.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument plan assignment"
```

---

## Task 7: Instrument generation start/finish (worker)

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/generation/worker.py`

The worker owns its own session (`session`) and commits explicitly; events ride that commit.

- [ ] **Step 1: generation_started** in `_load_and_start_job`

After `job_row.status = "running"` + flush (discovery ~L506-507), insert:

```python
    await record_event(
        session,
        Actor.system(),
        entity_type="generation_job",
        entity_id=str(job_row.id),
        event_type=EventType.GENERATION_STARTED,
        from_state="queued",
        to_state="running",
    )
```

Confirm the in-scope session variable name in `_load_and_start_job` (discovery: the worker's
`session`); use whatever the function's parameter is called. Import
`from cyo_adventure.events import Actor, EventType, record_event`.

- [ ] **Step 2: generation_finished** in `_persist_passed_outcome` and `_record_failure`

In `_persist_passed_outcome`, after `job_row.status = outcome.status` and the report/provider/
model fields are set (discovery ~L567-593), insert:

```python
    await record_event(
        session,
        Actor.system(),
        entity_type="generation_job",
        entity_id=str(job_row.id),
        event_type=EventType.GENERATION_FINISHED,
        from_state="running",
        to_state=job_row.status,
        payload={
            "outcome": job_row.status,
            "provider": job_row.provider,
            "model": job_row.model,
            "prompt_version": job_row.prompt_version,
        },
    )
```

In `_record_failure` (discovery ~L118-158, which sets `status="failed"` and commits), insert the
same call with `to_state="failed"` and `payload={"outcome": "failed"}` **before** its explicit
`commit()` so the event is in the failure transaction. Any payload field that is `None` at
failure time is fine (JSONB stores null); do not add keys outside the allowlist.

- [ ] **Step 3: Add a test**

The worker is not HTTP-driven. Call `run_generation_job` (or its testable inner entry) directly
with a `sessions()`-backed session factory against a queued job seeded via `sessions()`, then:

```python
    await assert_single_event(
        sessions, event_type="generation_started", entity_type="generation_job",
        actor_is_system=True,
    )
    await assert_single_event(
        sessions, event_type="generation_finished", entity_type="generation_job",
        actor_is_system=True,
    )
```

Reuse any existing worker-test arrangement (`grep -rn "run_generation_job" tests/`) for seeding a
job and stubbing the generation provider; do not build a new provider stub if one exists.

- [ ] **Step 4: Run + commit**

```bash
git add src/cyo_adventure/generation/worker.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument generation start and finish"
```

---

## Task 8: Instrument moderation completion + repair

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/moderation/pipeline.py`

- [ ] **Step 1: moderation_completed** after the outcome is decided

After `version_row.moderation_report = report.to_dict()` and the `auto_reject`/`submit` call
(discovery ~L183-192), insert (compute counts from the report; no snippets):

```python
    await record_event(
        session,
        Actor.system(),
        entity_type="storybook_version",
        entity_id=f"{story_id}:{version}",
        event_type=EventType.MODERATION_COMPLETED,
        to_state=storybook.status,
        payload={
            "overall_verdict": report.overall_verdict,
            "repaired": report.repaired,
            "counts": report.category_counts(),
        },
    )
```

Use the report's real attribute/method names for the overall verdict, repaired flag, and a
PII-free per-category/verdict count mapping (read `moderation/report.py`; if there is no
`category_counts()` helper, build the count dict inline from the report's findings, keys =
category or verdict, values = int). `storybook.status` reflects `in_review` (submit) or
`needs_revision` (auto_reject). Import the events symbols.

- [ ] **Step 2: repair_applied** where the repaired blob is adopted

At the point the pipeline sets `version_row.blob = revised` / marks `repaired = True` (discovery
~L179-181), insert **before** the moderation_completed call:

```python
    await record_event(
        session,
        Actor.system(),
        entity_type="storybook_version",
        entity_id=f"{story_id}:{version}",
        event_type=EventType.REPAIR_APPLIED,
        payload={"stage": "moderation"},
    )
```

- [ ] **Step 3: Add tests**

Drive `run_moderation_pipeline` directly with a stubbed generation provider (reuse existing
moderation-test stubs; `grep -rn "run_moderation_pipeline" tests/`) for two cases: a clean run
(assert one `moderation_completed`, `to_state="in_review"`, `actor_is_system=True`) and a
repaired run (assert one `repair_applied` plus one `moderation_completed` with
`payload["repaired"] is True`).

- [ ] **Step 4: Run + commit**

```bash
git add src/cyo_adventure/moderation/pipeline.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument moderation completion and repair"
```

---

## Task 9: Instrument release + send-back (publishing)

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/publishing/service.py`

- [ ] **Step 1: released** in `approve`

After `version_row.approved_by = principal.user_id` / `published_at` / `storybook.status =
"published"` are set (discovery ~L167-170), insert:

```python
    await record_event(
        session,
        Actor.from_principal(principal),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.RELEASED,
        from_state="in_review",
        to_state="published",
    )
```

- [ ] **Step 2: sent_back** in `send_back`

After the transition to `needs_revision` (discovery ~L195-197), insert (reason is NOT copied;
the version id is the reference):

```python
    await record_event(
        session,
        Actor.from_principal(principal),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.SENT_BACK,
        from_state="in_review",
        to_state="needs_revision",
    )
```

Import the events symbols. `storybook.id` is a `str` (storybook PKs are `String(120)`), so no
`str(...)` wrapper needed.

- [ ] **Step 3: Add tests**

Drive the admin approve and send-back endpoints (`api/approval.py`, admin token) against a
storybook in `in_review`. Seed a storybook version in `in_review` via `sessions()` (mirror the
`seed` fixture's Storybook/StorybookVersion inserts but with `status="in_review"`). Assert one
`released` (`to_state="published"`, `actor_role="admin"`) and, in a separate test, one
`sent_back` (`to_state="needs_revision"`).

- [ ] **Step 4: Run + commit**

```bash
git add src/cyo_adventure/publishing/service.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument release and send-back"
```

---

## Task 10: Instrument threshold + noise-floor changes

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/api/moderation_thresholds.py`

- [ ] **Step 1: threshold_changed** in `upsert_threshold` and `delete_threshold`

After the `ModerationThreshold` write + audit write + flush (discovery ~L181-211), insert in
`upsert_threshold`:

```python
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="moderation_threshold",
        entity_id=age_band,
        event_type=EventType.THRESHOLD_CHANGED,
        payload={
            "age_band": age_band,
            "category": category,
            "action": "upsert",
            "min_verdict": min_verdict,
            "min_score": min_score,
        },
    )
```

In `delete_threshold`, the same call with `"action": "delete"` and only the keys known at delete
time (`age_band`, `category`, `action`); omit `min_verdict`/`min_score`. Use the real in-scope
variable names for `category`/`min_verdict`/`min_score` (discovery: `category` is a query param;
the verdict/score come from the request body on upsert).

- [ ] **Step 2: noise_floor_changed** in `update_noise_floor`

After the `ModerationSetting` upsert + flush (discovery ~L303), insert:

```python
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="moderation_setting",
        entity_id="admin_noise_floor",
        event_type=EventType.NOISE_FLOOR_CHANGED,
        payload={"value": value},
    )
```

Use the real in-scope name for the new floor value. Import the events symbols.

- [ ] **Step 3: Add tests**

Drive the admin threshold upsert and noise-floor endpoints (`seed.admin_token`). Assert one
`threshold_changed` (`entity_type="moderation_threshold"`, `actor_role="admin"`) and one
`noise_floor_changed`.

- [ ] **Step 4: Run + commit**

```bash
git add src/cyo_adventure/api/moderation_thresholds.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument threshold and noise-floor changes"
```

---

## Task 11: Instrument book assignment

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/api/assignments.py`

- [ ] **Step 1: book_assigned** in `assign_storybook`

Inside the per-profile insert (after each `StorybookAssignment(...)` add + flush, discovery
~L235-245), insert one event per newly-created assignment:

```python
        await record_event(
            ctx.session,
            Actor.from_principal(ctx.principal),
            entity_type="storybook_assignment",
            entity_id=f"{pid}:{storybook_id}",
            event_type=EventType.BOOK_ASSIGNED,
            payload={"child_profile_id": str(pid)},
        )
```

Match the loop variable name for the profile id (discovery uses `pid`). If assignment is
idempotent (skips when already assigned), emit the event only when a new row is actually created,
place the call inside the create branch, not the skip branch. Import the events symbols.

- [ ] **Step 2: Add a test**

Drive the guardian assign endpoint (`seed.guardian_token`) assigning `seed.storybook_id` to a
child profile in the same family. Assert one `book_assigned` (`entity_type="storybook_assignment"`,
`actor_role="guardian"`). Note the `seed` fixture already assigns the lantern story to
`profile_a`; assign to a different profile or use a fresh storybook to keep the count at one.

- [ ] **Step 3: Run + commit**

```bash
git add src/cyo_adventure/api/assignments.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument book assignment"
```

---

## Task 12: Instrument ratings

depends-on: Task1 [completion]

**Files:**
- Modify: `src/cyo_adventure/api/ratings.py`

- [ ] **Step 1: rated** in `record_rating`

At the upsert (discovery ~L76-89), track whether the row was newly created vs overwritten
(`is_update`) and after the flush insert:

```python
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="rating",
        entity_id=f"{body.child_profile_id}:{body.storybook_id}",
        event_type=EventType.RATED,
        payload={"value": body.value, "is_update": is_update},
    )
```

Use the real in-scope names for the profile id, storybook id, and value (discovery: from the
request `body`). Set `is_update` from the branch that distinguishes insert vs overwrite (the
existing upsert logic already knows which path it took). Import the events symbols.

- [ ] **Step 2: Add a test**

Drive the child ratings endpoint twice for the same book: first POST asserts `is_update` False,
second asserts a second `rated` event with `is_update` True. Since two events are expected here,
use `fetch_events(sessions, "rated")` and assert `len == 2` and `[e.payload["is_update"] for e]
== [False, True]` rather than `assert_single_event`.

- [ ] **Step 3: Run + commit**

```bash
git add src/cyo_adventure/api/ratings.py tests/integration/test_pipeline_event_instrumentation.py
git commit -S -m "feat(events): instrument ratings"
```

---

## Task 13: Full gate, CHANGELOG, and OpenAPI drift check

depends-on: Task5 [completion] .. Task12 [completion]

- [ ] **Step 1: Run the full backend quality gate**

Run:
```bash
uv run ruff format . && uv run ruff check . && \
uv run basedpyright src/ && \
uv run pytest --cov=src --cov-fail-under=80 && \
uv run bandit -r src && uv run pip-audit
```
Expected: all pass, coverage >= 80%.
Abort if: coverage drops below 80% (add tests for any uncovered new branch).

- [ ] **Step 2: OpenAPI drift check** (WS-D adds no public endpoint; schema must be unchanged)

Run the in-process schema dump and diff against the committed client schema (never sort keys):
```bash
uv run python -c "import json, sys; from cyo_adventure.app import app; json.dump(app.openapi(), sys.stdout)" > /tmp/ws-d-openapi.json
```
Expected: the drift-gate comparison the CI uses is clean (no route/model change). If the CI drift
gate compares against a committed `openapi.json`, run the repo's documented drift command; WS-D
should produce no diff. If a diff appears, a docstring or model change leaked into a public route;
regenerate the frontend client (`cd frontend && npm run generate-client`) and include it.

- [ ] **Step 3: Add the CHANGELOG entry** under the Unreleased section of `CHANGELOG.md`

```markdown
### Added
- Append-only `pipeline_event` log capturing every story-lifecycle transition
  (request, plan, generation, moderation, release, threshold, assignment, rating),
  the capture layer for the learning loop (WS-D).
```

- [ ] **Step 4: Confirm single migration head** (final rebase check before PR)

Run: `uv run alembic heads`
Expected: one head `f2a3b4c5d6e7`.
Abort if: two heads (WS-C merged first); rebase, bump `down_revision` to the new head, re-run Task 3 Step 3.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(events): changelog entry for pipeline event log"
```

---

## Self-review notes (author)

- **Clause coverage:** all 14 taxonomy events map to a Task 5-12 step; the four ratified
  decisions map to Task 1 (D1 atomic flush, D2 Actor.system), Task 1 allowlist (D3), Task 3
  trigger (D4). The umbrella test bar maps to Task 3 (migration round-trip + append-only) and
  Tasks 5-12 (per-transition assertions).
- **Anchors are approximate line numbers** from 2026-07-08 discovery; each step says what code to
  find (a specific assignment/flush), not only a line, so drift within a function is survivable.
- **`is_update` / `series_created` / `anchor_resolved` / report count helper**: each step names
  the branch or value to source these from and a fallback if the exact helper name differs, so no
  step invents an undefined symbol.
- **Test infra reuse:** every test uses the existing `client`/`sessions`/`seed`/`auth` fixtures
  and the Task 4 helper; no parallel fixture infrastructure is introduced.
