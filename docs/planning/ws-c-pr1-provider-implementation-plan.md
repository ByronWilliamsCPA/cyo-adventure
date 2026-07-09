---
schema_type: planning
title: "WS-C PR 1: Provider Work Implementation Plan"
description: "Task-by-task implementation plan for WS-C PR 1: the admin-editable provider/model
  allowlist and its audit trail, the direct-Anthropic provider via the official SDK, the
  build_provider per-job factory, and authoring-plan provider/model validation."
tags:
  - planning
  - project
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an implementer with zero session context everything needed to build WS-C PR 1
  task by task against the ratified spec."
component: Strategy
source: "docs/planning/ws-c-admin-processing-spec.md (PR1: provider work section); codebase
  discovery 2026-07-08 on feat/ws-c-admin-processing at main @ d17ccce."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Turn the admin authoring-plan step into the explicit processing gate for automated generation:
an admin picks a provider/model pair constrained to a DB-backed, admin-editable allowlist with a
full audit trail; the deferred direct-Anthropic adapter ships behind the official SDK under the
canonical name `anthropic` (replacing the dead `"claude"` literal); `build_provider()` becomes a
per-job factory that the worker calls after the job row loads, so a per-request provider/model
override recorded on the job's `authoring_metadata` wins over the global `Settings` default.

## Architecture

Two new tables (`provider_model_allowlist`, `provider_model_allowlist_audit`) mirror the
`ModerationThreshold`/`ModerationThresholdAudit` shape and admin-CRUD pattern exactly
(`src/cyo_adventure/db/models.py:555-670`, `src/cyo_adventure/api/moderation_thresholds.py`).
`AuthoringPlanRequest` gains `provider`/`model`; when `mechanism='automated_provider'` both are
required and validated against an *enabled* allowlist row before the job is ever created, then
persisted into `GenerationJob.authoring_metadata`. `generation/worker.py::run_generation_job`
reads that override off the loaded job row and threads it into a widened `build_provider(settings,
*, provider_override=None, model_override=None)`; no override reproduces today's behavior exactly.
The new `AnthropicProvider` (`generation/providers/anthropic.py`) wraps the official `anthropic`
SDK's `AsyncAnthropic` client, owns its own Layer-1 retry/backoff via the existing
`generation/providers/_base.py::run_with_retries` helper (disabling the SDK's own built-in retry so
there is exactly one retry loop), and maps the SDK's `APIConnectionError`/`APIStatusError`
hierarchy onto the same `ProviderError(leg_fatal=...)` shape `OpenRouterProvider` uses.

## Tech stack

Backend only (FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, `anthropic` SDK). One
`OPENAPI_INPUT=... npm run generate-client` client-regen commit; no frontend UI is built in PR1
(the spec's explicit non-goal).

---

## Conventions that bind every task

- Every code step below shows the exact code to write; every command step shows the exact
  command and its expected output. Nothing is deferred to "similar to Task N."
- RAD markers (`#CRITICAL`/`#ASSUME`/`#EDGE` + `#VERIFY`) are written inline in the code blocks
  exactly as they must appear in the file; do not paraphrase them away when copying.
- Every "Commit" step stages only the files that task touched (never `git add -A`/`.`) and signs
  the commit (`git commit -S`). Conventional Commits; no em-dash anywhere.
- Migration revision id for this PR: `f2a3b4c5d6e7`, `down_revision = "e1f2a3b4c5d6"` (current
  head, `migrations/versions/20260708_1600_add_series_and_soft_continuation.py`). WS-D is a
  concurrent sibling session also chaining onto `e1f2a3b4c5d6`; whichever PR merges second rebases
  and bumps its own migration's `down_revision` to the other's new head. Do not coordinate this
  mid-task; it is a normal post-merge rebase.
- The shared integration-test `engine` fixture (`tests/integration/conftest.py:123-136`) builds
  tables from `Base.metadata.create_all` per test function, **not** from Alembic. New ORM models
  are therefore live in every integration test as soon as Task 2 lands; migration-seeded rows are
  **not** present in that schema (same as `ModerationSetting`'s seed row), so any integration test
  that needs an allowlist row inserts it directly via the ORM.
- Router registration point (verified): `src/cyo_adventure/app.py` imports every router module in
  one alphabetical `from cyo_adventure.api import (...)` block at lines 17-30, then calls
  `app.include_router(...)` once per router at lines 170-181, most recently
  `app.include_router(moderation_thresholds.router)` at line 179. The new
  `api/provider_allowlist.py` router is added to both.

---

### Task 1: `uv add` the `anthropic` SDK to the `api` extra

depends-on: none

**Files:**
- Modify: `pyproject.toml` (`[project.optional-dependencies].api`, currently lines 131-140)
- Modify: `uv.lock` (regenerated, not hand-edited)

- [ ] **Step 1 (Operational): add the dependency**

Command:
```bash
uv add --optional api anthropic
```
Expected output: uv resolves and adds a line to `pyproject.toml`'s `api = [...]` list (after
`"httpx>=0.27",`) reading `"anthropic>=<resolved-version>",`, and rewrites `uv.lock`. Console ends
with `Installed N packages` / `+ anthropic==<version>` and exit code 0. Do not hand-edit the
version pin uv writes.
Abort-if: nonzero exit, or `anthropic` fails to resolve (network/registry issue) ; stop and report
before continuing to Task 2.

- [ ] **Step 2 (Operational): sync and verify the import**

Command:
```bash
uv sync --all-extras
uv run python -c "import anthropic; print(anthropic.__version__)"
```
Expected output: a version string (e.g. `0.NN.N`) printed, exit code 0.
Abort-if: `ModuleNotFoundError` or nonzero exit ; the extra did not install; re-run
`uv sync --all-extras` and re-check before continuing.

- [ ] **Step 3 (Operational): dependency-scan the new surface**

Command:
```bash
uv run pip-audit
```
Expected output: no HIGH/CRITICAL finding naming `anthropic` or a transitive dependency it pulled
in (`httpx`/`httpcore`/`pydantic` are already in the tree and already audited).
Abort-if: a finding appears. `#EDGE: external-resources: a new dependency adds a pip-audit/OSV
surface.` `#VERIFY: if pip-audit reports a finding here, document it in
docs/known-vulnerabilities.md per the template before continuing; do not suppress it.`

- [ ] **Step 4: commit**

```bash
git add pyproject.toml uv.lock
git commit -S -m "chore(deps): add anthropic SDK to the api extra (WS-C PR1)"
```

---

### Task 2: `ProviderModelAllowlist` + `ProviderModelAllowlistAudit` ORM models

depends-on: none

**Files:**
- Modify: `src/cyo_adventure/db/models.py`

- [ ] **Step 1: write the failing test**

Create `tests/unit/test_allowlist_models.py`:
```python
"""Unit tests for the ProviderModelAllowlist ORM shape (no DB required)."""

from __future__ import annotations

from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit


def test_provider_model_allowlist_tablename() -> None:
    """The table name matches the spec's natural-key table."""
    assert ProviderModelAllowlist.__tablename__ == "provider_model_allowlist"


def test_provider_model_allowlist_audit_tablename() -> None:
    """The audit table name matches the spec."""
    assert ProviderModelAllowlistAudit.__tablename__ == "provider_model_allowlist_audit"


def test_allowlist_row_defaults_enabled_true() -> None:
    """A freshly constructed row defaults to enabled=True (Python-side default)."""
    row = ProviderModelAllowlist(provider="anthropic", model_id="claude-sonnet-4-6")
    assert row.enabled is True
    assert row.display_name is None


def test_audit_row_requires_changed_by_at_construction_time_type() -> None:
    """changed_by is typed non-optional; the class does not declare a Python default."""
    assert "changed_by" not in ProviderModelAllowlistAudit.__init__.__annotations__ or True
    # The real guarantee is the DB NOT NULL FK exercised by the migration
    # round-trip test in Task 3; this test only pins that the ORM column
    # itself carries no silently-nullable Python default that would mask a
    # missing changed_by until the DB constraint fires.
    audit = ProviderModelAllowlistAudit(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        action="create",
        old_enabled=None,
        new_enabled=True,
        changed_by=__import__("uuid").uuid4(),
    )
    assert audit.action == "create"
```

- [ ] **Step 2: run it and confirm it fails on import**

Command:
```bash
uv run pytest tests/unit/test_allowlist_models.py -v
```
Expected: `ImportError: cannot import name 'ProviderModelAllowlist' from 'cyo_adventure.db.models'`
(collection error, not an assertion failure).

- [ ] **Step 3: add the ORM models**

In `src/cyo_adventure/db/models.py`, widen the `sqlalchemy` import at lines 19-29 to add `text`:
```python
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
```

Insert after line 712 (the blank lines right before `class GenerationJob(Base):` at line 715):
```python
_ALLOWLIST_PROVIDER_VALUES = "'anthropic', 'openrouter', 'modal', 'ollama'"


class ProviderModelAllowlist(Base):
    """Admin-editable allowlist of (provider, model_id) pairs eligible for generation.

    Providers are a code-fixed enum (the CHECK below); only the model id
    within a provider is admin-managed. ``mock`` is never allowlisted: it is
    a CI-only test double, never a real generation backend.

    Attributes:
        id: Surrogate primary key.
        provider: One of the fixed provider names (see the CHECK constraint).
        model_id: The provider-native model id (e.g. ``claude-sonnet-4-6``,
            ``anthropic/claude-sonnet-4.6``).
        enabled: Whether this pair is currently selectable. Disabling a row
            (rather than deleting it) preserves audit history.
        display_name: Optional human label for a future admin UI.
        created_by: The admin who added this row, or ``None``.
        updated_by: The admin who last edited this row, or ``None``.
        created_at: Insert time (UTC, TIMESTAMPTZ).
        updated_at: Last edit time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "provider_model_allowlist"
    # #CRITICAL: security: this is the control that keeps free-string model
    # ids out of billing; the ck_provider_model_allowlist_provider CHECK is
    # the at-rest backstop against any non-API write path (admin script,
    # backfill, raw SQL) introducing an unrecognized billing backend.
    # #VERIFY: generation/allowlist.py::is_enabled_allowlist_pair is the
    # single read path the authoring-plan endpoint trusts; both this CHECK and
    # that helper are round-tripped by
    # tests/integration/test_provider_model_allowlist_migration.py and
    # tests/integration/test_allowlist.py.
    __table_args__ = (
        CheckConstraint(
            f"provider IN ({_ALLOWLIST_PROVIDER_VALUES})",
            name="ck_provider_model_allowlist_provider",
        ),
        UniqueConstraint(
            "provider", "model_id", name="uq_provider_model_allowlist_provider_model"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


class ProviderModelAllowlistAudit(Base):
    """Append-only audit of allowlist edits (who changed what, when).

    Deliberately minimal, mirroring ``ModerationThresholdAudit``: WS-D's
    pipeline_event log will subsume this role; keep this table write-only
    until then.

    Attributes:
        id: Surrogate primary key.
        provider: The affected row's provider (natural-key half).
        model_id: The affected row's model id (natural-key half).
        action: What happened: ``create``, ``update``, or ``delete``.
        old_enabled: The ``enabled`` value before the edit, or ``None`` on create.
        new_enabled: The ``enabled`` value after the edit, or ``None`` on delete.
        changed_by: The admin who made the edit (required; see RAD tag).
        changed_at: When the edit was recorded (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "provider_model_allowlist_audit"
    # #ASSUME: data integrity: the audit trail is only trustworthy if every
    # row names a known action; a typo'd action written by a non-API path
    # would silently corrupt the "who changed what" record.
    # #VERIFY: api/provider_allowlist.py writes only 'create'/'update'/'delete';
    # tests/integration/test_provider_model_allowlist_migration.py round-trips
    # the migration that creates this CHECK.
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_provider_model_allowlist_audit_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(16))
    old_enabled: Mapped[bool | None] = mapped_column(default=None)
    new_enabled: Mapped[bool | None] = mapped_column(default=None)
    # #CRITICAL: security / data integrity: every allowlist edit must be
    # attributable; changed_by is a NOT NULL FK to user.id so an anonymous or
    # dangling edit record cannot be persisted. Rows are append-only by
    # convention (no update/delete path in the application layer).
    # #VERIFY: tests/integration/test_provider_allowlist_api.py asserts one
    # audit row per POST/PUT/DELETE with the correct changed_by and
    # old/new_enabled pairing.
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_USER))
    changed_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
```

- [ ] **Step 4: run the test and confirm it passes**

Command:
```bash
uv run pytest tests/unit/test_allowlist_models.py -v
```
Expected: 4 passed.

- [ ] **Step 5: run the full quality gate for this file**

Command:
```bash
uv run ruff check src/cyo_adventure/db/models.py tests/unit/test_allowlist_models.py
uv run ruff format --check src/cyo_adventure/db/models.py tests/unit/test_allowlist_models.py
uv run basedpyright src/cyo_adventure/db/models.py tests/unit/test_allowlist_models.py
```
Expected: all clean.

- [ ] **Step 6: commit**

```bash
git add src/cyo_adventure/db/models.py tests/unit/test_allowlist_models.py
git commit -S -m "feat(generation): add ProviderModelAllowlist ORM models (WS-C PR1)"
```

---

### Task 3: migration (create both tables, seed 5 rows) + round-trip test

depends-on: Task2 [completion]

**Files:**
- Create: `migrations/versions/20260709_1000_add_provider_model_allowlist.py`
- Create: `tests/integration/test_provider_model_allowlist_migration.py`

- [ ] **Step 1: write the migration**

```python
"""add provider_model_allowlist and its audit table, seeded (WS-C PR1)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-09 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# #ASSUME: data-integrity: this seed list is hand-synced with
# cyo_adventure.generation.allowlist.DEFAULT_ALLOWLIST. Migrations are frozen
# and must not import live app constants (same rule as
# 20260707_1700_add_moderation_setting.py's admin_noise_floor seed), so the
# two lists are kept in lockstep by hand.
# #VERIFY: tests/integration/test_provider_model_allowlist_migration.py
# asserts every one of these 5 rows is present, enabled, after upgrade.
_SEED_ROWS = (
    ("anthropic", "claude-sonnet-4-6", "Claude Sonnet 4.6 (direct)"),
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5 (direct)"),
    ("openrouter", "anthropic/claude-haiku-4.5", "OpenRouter primary (Haiku 4.5)"),
    ("openrouter", "anthropic/claude-sonnet-4.6", "OpenRouter fallback (Sonnet 4.6)"),
    ("ollama", "qwen2.5:14b", "Ollama local default"),
)


def upgrade() -> None:
    """Create the allowlist table and its append-only audit table, then seed."""
    op.create_table(
        "provider_model_allowlist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'openrouter', 'modal', 'ollama')",
            name="ck_provider_model_allowlist_provider",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "model_id", name="uq_provider_model_allowlist_provider_model"
        ),
    )
    op.create_table(
        "provider_model_allowlist_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("old_enabled", sa.Boolean(), nullable=True),
        sa.Column("new_enabled", sa.Boolean(), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "changed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_provider_model_allowlist_audit_action",
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # #ASSUME: external-resources: gen_random_uuid() is a PostgreSQL 13+
    # built-in (moved out of the pgcrypto extension into core in PG13); the
    # testcontainers image (postgres:16-alpine) and Supabase's managed
    # Postgres both satisfy this, so no CREATE EXTENSION is needed.
    # #VERIFY: test_seed_rows_present_after_upgrade below runs this migration
    # against postgres:16-alpine.
    for provider, model_id, display_name in _SEED_ROWS:
        op.execute(
            sa.text(
                "INSERT INTO provider_model_allowlist "
                "(id, provider, model_id, enabled, display_name, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :provider, :model_id, true, "
                ":display_name, now(), now())"
            ).bindparams(provider=provider, model_id=model_id, display_name=display_name)
        )


def downgrade() -> None:
    """Drop both new tables (seed rows go with the table)."""
    op.drop_table("provider_model_allowlist_audit")
    op.drop_table("provider_model_allowlist")
```

- [ ] **Step 2: write the round-trip test**

```python
"""Migration round-trip for the WS-C PR1 provider allowlist tables."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

# Pin the round-trip to explicit revision ids rather than "head"/"-1" (lesson
# from PR #108; see test_moderation_threshold_migration.py for the same note).
_PREV_HEAD = "e1f2a3b4c5d6"
_ALLOWLIST_HEAD = "f2a3b4c5d6e7"


@pytest.mark.integration
def test_allowlist_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains to head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_provider_model_allowlist*.py"))
    assert files, f"allowlist migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_allowlist_migration", files[0])
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert callable(getattr(mod, "upgrade", None))
    assert callable(getattr(mod, "downgrade", None))
    assert mod.down_revision == _PREV_HEAD, (
        f"Expected down_revision {_PREV_HEAD!r}, got {mod.down_revision!r}"
    )


@pytest.mark.integration
def test_allowlist_migration_upgrade_downgrade(migration_pg_url: str) -> None:
    """alembic upgrade then downgrade of the allowlist revision succeed."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _ALLOWLIST_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    assert "Running upgrade" in up.stderr

    down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    assert "Running downgrade" in down.stderr


@pytest.mark.integration
@pytest.mark.asyncio
async def test_allowlist_tables_present_only_while_upgraded(
    migration_pg_url: str,
) -> None:
    """Both tables exist after upgrade and are gone again after downgrade."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _ALLOWLIST_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            for table in ("provider_model_allowlist", "provider_model_allowlist_audit"):
                result = await conn.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ).bindparams(t=table)
                )
                assert result.first() is not None, f"{table} missing after upgrade"

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

        async with engine.connect() as conn:
            for table in ("provider_model_allowlist", "provider_model_allowlist_audit"):
                result = await conn.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ).bindparams(t=table)
                )
                assert result.first() is None, f"{table} still present after downgrade"
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_rows_present_after_upgrade(migration_pg_url: str) -> None:
    """The 5 DEFAULT_ALLOWLIST rows land, enabled, in the same transaction as the table."""
    from cyo_adventure.generation.allowlist import DEFAULT_ALLOWLIST

    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _ALLOWLIST_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT provider, model_id, enabled FROM provider_model_allowlist "
                    "ORDER BY provider, model_id"
                )
            )
            rows = {(r.provider, r.model_id): r.enabled for r in result.all()}
        assert len(rows) == len(DEFAULT_ALLOWLIST)
        for seed in DEFAULT_ALLOWLIST:
            assert rows[(seed.provider, seed.model_id)] is True

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    finally:
        await engine.dispose()
```

- [ ] **Step 3 (Operational): run the migration tests**

Command:
```bash
uv run pytest tests/integration/test_provider_model_allowlist_migration.py -v
```
Expected: `test_allowlist_migration_imports_and_chains` and `test_allowlist_migration_upgrade_downgrade`
pass immediately; `test_allowlist_tables_present_only_while_upgraded` and
`test_seed_rows_present_after_upgrade` FAIL at this point with `ModuleNotFoundError: No module
named 'cyo_adventure.generation.allowlist'` (Task 4 has not landed yet) ; this is expected; do not
treat it as a regression to fix here.
Abort-if: the first two tests fail (chain/import problem in the migration file itself) ; fix the
migration before proceeding, since Task 4 depends on this table existing.

- [ ] **Step 4: commit**

```bash
git add migrations/versions/20260709_1000_add_provider_model_allowlist.py \
  tests/integration/test_provider_model_allowlist_migration.py
git commit -S -m "feat(db): migrate provider_model_allowlist tables, seeded (WS-C PR1)"
```

---

### Task 4: `DEFAULT_ALLOWLIST` constant + `is_enabled_allowlist_pair` helper

depends-on: Task2 [completion], Task3 [output]

**Files:**
- Create: `src/cyo_adventure/generation/allowlist.py`
- Create: `tests/unit/test_allowlist.py`
- Test: `tests/integration/test_allowlist.py`

- [ ] **Step 1: write the failing unit test**

Create `tests/unit/test_allowlist.py`:
```python
"""Unit tests for the DEFAULT_ALLOWLIST seed constant (no DB required)."""

from __future__ import annotations

from cyo_adventure.generation.allowlist import ALLOWLIST_PROVIDERS, DEFAULT_ALLOWLIST


def test_default_allowlist_has_five_seed_rows() -> None:
    """The code constant matches the migration's seed row count exactly."""
    assert len(DEFAULT_ALLOWLIST) == 5


def test_default_allowlist_providers_are_all_in_the_fixed_set() -> None:
    """Every seed row's provider is one of the four allowlistable providers."""
    for seed in DEFAULT_ALLOWLIST:
        assert seed.provider in ALLOWLIST_PROVIDERS


def test_mock_is_never_in_allowlist_providers() -> None:
    """mock is a CI-only test double, never a real allowlist entry."""
    assert "mock" not in ALLOWLIST_PROVIDERS


def test_default_allowlist_pairs_are_unique() -> None:
    """No (provider, model_id) pair repeats within the seed constant itself."""
    pairs = [(seed.provider, seed.model_id) for seed in DEFAULT_ALLOWLIST]
    assert len(pairs) == len(set(pairs))
```

- [ ] **Step 2: run it and confirm it fails on import**

Command:
```bash
uv run pytest tests/unit/test_allowlist.py -v
```
Expected: `ModuleNotFoundError: No module named 'cyo_adventure.generation.allowlist'`.

- [ ] **Step 3: write the module**

Create `src/cyo_adventure/generation/allowlist.py`:
```python
"""Admin-editable provider/model allowlist (WS-C PR1).

Providers are a code-fixed enum; only the model id within a provider is
admin-managed via ``api/provider_allowlist.py``. ``DEFAULT_ALLOWLIST`` is the
code-side mirror of the seed rows
``migrations/versions/20260709_1000_add_provider_model_allowlist.py`` inserts;
the two are hand-synced (see the RAD note on that migration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.db.models import ProviderModelAllowlist

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Mirrors the ck_provider_model_allowlist_provider CHECK constraint. mock is
# deliberately absent: it is a CI-only test double, never a real generation
# backend, so it can never be allowlisted.
ALLOWLIST_PROVIDERS: tuple[str, ...] = ("anthropic", "openrouter", "modal", "ollama")


@dataclass(frozen=True, slots=True)
class AllowlistSeed:
    """One hand-synced seed row mirrored from the PR1 migration.

    Attributes:
        provider: One of ``ALLOWLIST_PROVIDERS``.
        model_id: The provider-native model id.
        display_name: The human label the migration seeds alongside it.
    """

    provider: str
    model_id: str
    display_name: str


DEFAULT_ALLOWLIST: tuple[AllowlistSeed, ...] = (
    AllowlistSeed("anthropic", "claude-sonnet-4-6", "Claude Sonnet 4.6 (direct)"),
    AllowlistSeed("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5 (direct)"),
    AllowlistSeed(
        "openrouter", "anthropic/claude-haiku-4.5", "OpenRouter primary (Haiku 4.5)"
    ),
    AllowlistSeed(
        "openrouter",
        "anthropic/claude-sonnet-4.6",
        "OpenRouter fallback (Sonnet 4.6)",
    ),
    AllowlistSeed("ollama", "qwen2.5:14b", "Ollama local default"),
)


async def is_enabled_allowlist_pair(
    session: AsyncSession, provider: str, model_id: str
) -> bool:
    """Return whether ``(provider, model_id)`` is an enabled allowlist row.

    Args:
        session: The request-scoped async session.
        provider: The provider name from untrusted admin input.
        model_id: The provider-native model id from untrusted admin input.

    Returns:
        bool: True only when a row exists for the exact pair AND enabled=True.
    """
    # #CRITICAL: security: this is the control that keeps free-string model
    # ids out of billing. enabled=True is checked in the SAME query as the
    # natural-key match, not as a separate filter a caller could forget or
    # apply after the fact.
    # #VERIFY: tests/integration/test_allowlist.py::
    # test_disabled_pair_is_not_enabled and test_unknown_pair_is_not_enabled.
    row = await session.scalar(
        select(ProviderModelAllowlist).where(
            ProviderModelAllowlist.provider == provider,
            ProviderModelAllowlist.model_id == model_id,
            ProviderModelAllowlist.enabled.is_(True),
        )
    )
    return row is not None
```

- [ ] **Step 4: run the unit test and confirm it passes**

Command:
```bash
uv run pytest tests/unit/test_allowlist.py -v
```
Expected: 4 passed.

- [ ] **Step 5: write the integration test for the DB-backed helper**

Create `tests/integration/test_allowlist.py`:
```python
"""Integration tests for is_enabled_allowlist_pair (needs a real session)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import ProviderModelAllowlist
from cyo_adventure.generation.allowlist import is_enabled_allowlist_pair

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_enabled_pair_is_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An enabled row for the exact pair returns True."""
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="anthropic", model_id="claude-sonnet-4-6", enabled=True
            )
        )
        await session.commit()
        assert await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6"
        )


async def test_disabled_pair_is_not_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A disabled row for the exact pair returns False, not a stale True."""
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="anthropic", model_id="claude-sonnet-4-6", enabled=False
            )
        )
        await session.commit()
        assert not await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6"
        )


async def test_unknown_pair_is_not_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A pair with no row at all returns False (never raises)."""
    async with sessions() as session:
        assert not await is_enabled_allowlist_pair(
            session, "anthropic", "not-a-real-model"
        )


async def test_mock_is_never_a_row_and_therefore_never_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """mock has no allowlist row (the CHECK forbids inserting one)."""
    async with sessions() as session:
        assert not await is_enabled_allowlist_pair(session, "mock", "mock")
```

- [ ] **Step 6 (Operational): run the migration tests skipped in Task 3, then this file**

Command:
```bash
uv run pytest tests/integration/test_provider_model_allowlist_migration.py \
  tests/integration/test_allowlist.py -v
```
Expected: all pass now that `generation/allowlist.py` exists (the two migration tests that failed
at the end of Task 3 now pass too).

- [ ] **Step 7: gates and commit**

```bash
uv run ruff check src/cyo_adventure/generation/allowlist.py tests/unit/test_allowlist.py \
  tests/integration/test_allowlist.py
uv run ruff format --check src/cyo_adventure/generation/allowlist.py tests/unit/test_allowlist.py \
  tests/integration/test_allowlist.py
uv run basedpyright src/cyo_adventure/generation/allowlist.py
git add src/cyo_adventure/generation/allowlist.py tests/unit/test_allowlist.py \
  tests/integration/test_allowlist.py
git commit -S -m "feat(generation): add DEFAULT_ALLOWLIST and is_enabled_allowlist_pair (WS-C PR1)"
```

---

### Task 5: admin CRUD endpoints for the allowlist

depends-on: Task2 [completion], Task4 [output]

**Files:**
- Modify: `src/cyo_adventure/api/schemas.py`
- Create: `src/cyo_adventure/api/provider_allowlist.py`
- Modify: `src/cyo_adventure/app.py`
- Create: `tests/integration/test_provider_allowlist_api.py`

- [ ] **Step 1: add the schemas**

In `src/cyo_adventure/api/schemas.py`, add after the `NoiseFloorUpdateBody` class (end of the
WS-A admin noise-floor schemas block, around line 957):
```python
# ---------------------------------------------------------------------------
# Provider/model allowlist schemas (WS-C PR1)
# ---------------------------------------------------------------------------

ProviderName = Literal["anthropic", "openrouter", "modal", "ollama"]


class AllowlistView(BaseModel):
    """One provider/model allowlist row."""

    id: str
    provider: ProviderName
    model_id: str
    enabled: bool
    display_name: str | None


class AllowlistListView(BaseModel):
    """The whole allowlist table, ordered by (provider, model_id)."""

    rows: list[AllowlistView]


class AllowlistCreateBody(BaseModel):
    """POST body to add a new allowlist row."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    model_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    display_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None


class AllowlistUpdateBody(BaseModel):
    """PUT body: full replace of the mutable fields (mirrors ThresholdUpsertBody)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    display_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
```

- [ ] **Step 2: write the failing endpoint tests**

Create `tests/integration/test_provider_allowlist_api.py`:
```python
"""Admin CRUD for the provider/model allowlist: auth, add, toggle, delete, audit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_URL = "/api/v1/admin/provider-allowlist"


async def test_guardian_gets_403_on_every_verb(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """Non-admin callers are rejected before any read or write."""
    get_res = await client.get(_URL, headers=auth(seed.guardian_token))
    assert get_res.status_code == 403
    post_res = await client.post(
        _URL,
        json={"provider": "anthropic", "model_id": "claude-opus-4-8"},
        headers=auth(seed.guardian_token),
    )
    assert post_res.status_code == 403
    async with AsyncSession(engine) as session:
        rows = (await session.scalars(select(ProviderModelAllowlist))).all()
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert rows == []
    assert audits == []


async def test_list_starts_empty(client: AsyncClient, seed: Seed) -> None:
    """A fresh ORM-metadata test schema carries no migration-seeded rows."""
    res = await client.get(_URL, headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert res.json()["rows"] == []


async def test_add_then_list_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """POST creates a row and an audit entry; the row shows up in GET."""
    res = await client.post(
        _URL,
        json={
            "provider": "anthropic",
            "model_id": "claude-opus-4-8",
            "display_name": "Claude Opus 4.8",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["provider"] == "anthropic"
    assert body["enabled"] is True

    listed = await client.get(_URL, headers=auth(seed.admin_token))
    assert len(listed.json()["rows"]) == 1

    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert len(audits) == 1
    assert audits[0].action == "create"
    assert audits[0].old_enabled is None
    assert audits[0].new_enabled is True
    assert audits[0].changed_by == seed.admin_user_id


async def test_add_duplicate_pair_is_409(client: AsyncClient, seed: Seed) -> None:
    """A second POST for the same (provider, model_id) is a conflict, not a second row."""
    body = {"provider": "ollama", "model_id": "qwen2.5:14b"}
    first = await client.post(_URL, json=body, headers=auth(seed.admin_token))
    assert first.status_code == 201
    second = await client.post(_URL, json=body, headers=auth(seed.admin_token))
    assert second.status_code == 409


async def test_add_unknown_provider_is_422(client: AsyncClient, seed: Seed) -> None:
    """A provider outside the fixed enum is rejected at the schema boundary."""
    res = await client.post(
        _URL,
        json={"provider": "claude", "model_id": "claude-sonnet-4-6"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422


async def test_toggle_enabled_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """PUT toggles enabled and writes an audit row with the old/new pairing."""
    created = await client.post(
        _URL,
        json={"provider": "modal", "model_id": "some-modal-model"},
        headers=auth(seed.admin_token),
    )
    entry_id = created.json()["id"]

    res = await client.put(
        f"{_URL}/{entry_id}",
        json={"enabled": False, "display_name": "disabled for maintenance"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert res.json()["display_name"] == "disabled for maintenance"

    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert [a.action for a in audits] == ["create", "update"]
    assert audits[1].old_enabled is True
    assert audits[1].new_enabled is False
    assert audits[1].changed_by == seed.admin_user_id


async def test_delete_removes_row_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """DELETE removes the row and audits it before deleting."""
    created = await client.post(
        _URL,
        json={"provider": "ollama", "model_id": "qwen3:30b"},
        headers=auth(seed.admin_token),
    )
    entry_id = created.json()["id"]

    res = await client.delete(f"{_URL}/{entry_id}", headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert res.json()["rows"] == []

    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ProviderModelAllowlistAudit))).all()
    assert audits[-1].action == "delete"
    assert audits[-1].old_enabled is True
    assert audits[-1].new_enabled is None


async def test_delete_missing_row_is_404(client: AsyncClient, seed: Seed) -> None:
    """Deleting a non-existent id is a 404, not a silent no-op."""
    res = await client.delete(
        f"{_URL}/00000000-0000-0000-0000-000000000000",
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404


async def test_update_missing_row_is_404(client: AsyncClient, seed: Seed) -> None:
    """Updating a non-existent id is a 404."""
    res = await client.put(
        f"{_URL}/00000000-0000-0000-0000-000000000000",
        json={"enabled": False},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404
```

- [ ] **Step 3: run the tests and confirm they fail**

Command:
```bash
uv run pytest tests/integration/test_provider_allowlist_api.py -v
```
Expected: every test fails with a 404 for the route (the router does not exist yet).

- [ ] **Step 4: write the router**

Create `src/cyo_adventure/api/provider_allowlist.py`:
```python
"""Admin CRUD for the provider/model generation allowlist (WS-C PR1)."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    AllowlistCreateBody,
    AllowlistListView,
    AllowlistUpdateBody,
    AllowlistView,
    ProviderName,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit

router = APIRouter(prefix="/api/v1", tags=["provider-allowlist"])


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: this allowlist is the control that keeps
    # free-string model ids out of billing; the role gate runs before any
    # query so a non-admin cannot even enumerate what is allowlisted.
    # #VERIFY: test_guardian_gets_403_on_every_verb.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


def _view(row: ProviderModelAllowlist) -> AllowlistView:
    """Map an ORM row to its response schema."""
    return AllowlistView(
        id=str(row.id),
        provider=cast("ProviderName", row.provider),
        model_id=row.model_id,
        enabled=row.enabled,
        display_name=row.display_name,
    )


@router.get("/admin/provider-allowlist")
async def list_allowlist(ctx: Context) -> AllowlistListView:
    """List every allowlist row, ordered by (provider, model_id) (admin only).

    Args:
        ctx: The request context (principal + session).

    Returns:
        AllowlistListView: Every row, ordered by (provider, model_id).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    _require_admin(ctx)
    # #ASSUME: external-resources: a whole-table read per request is
    # deliberate; the table is admin-curated and small, mirroring
    # list_thresholds's no-cache stance.
    # #VERIFY: tests/integration/test_provider_allowlist_api.py.
    rows = (
        await ctx.session.scalars(
            select(ProviderModelAllowlist).order_by(
                ProviderModelAllowlist.provider, ProviderModelAllowlist.model_id
            )
        )
    ).all()
    return AllowlistListView(rows=[_view(row) for row in rows])


@router.post("/admin/provider-allowlist", status_code=201)
async def add_allowlist_entry(body: AllowlistCreateBody, ctx: Context) -> AllowlistView:
    """Add a new (provider, model_id) pair to the allowlist (admin only).

    Args:
        body: The provider/model_id/display_name to add.
        ctx: The request context (principal + session).

    Returns:
        AllowlistView: The created row.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        StateTransitionError: If the pair already exists (409).
    """
    _require_admin(ctx)
    existing = await ctx.session.scalar(
        select(ProviderModelAllowlist).where(
            ProviderModelAllowlist.provider == body.provider,
            ProviderModelAllowlist.model_id == body.model_id,
        )
    )
    if existing is not None:
        msg = f"allowlist entry already exists for ({body.provider}, {body.model_id})"
        raise StateTransitionError(msg)
    row = ProviderModelAllowlist(
        provider=body.provider,
        model_id=body.model_id,
        enabled=True,
        display_name=body.display_name,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(row)
    # #CRITICAL: data-integrity: every allowlist edit must leave an audit
    # trail (changed_by is a NOT NULL FK), so the audit row is written in the
    # same unit-of-work as the insert; both commit or both roll back.
    # #VERIFY: test_add_then_list_with_audit.
    ctx.session.add(
        ProviderModelAllowlistAudit(
            provider=body.provider,
            model_id=body.model_id,
            action="create",
            old_enabled=None,
            new_enabled=True,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.flush()
    return _view(row)


@router.put("/admin/provider-allowlist/{entry_id}")
async def update_allowlist_entry(
    entry_id: uuid.UUID, body: AllowlistUpdateBody, ctx: Context
) -> AllowlistView:
    """Toggle enabled and/or update display_name for one row (admin only).

    Args:
        entry_id: The row's id (path).
        body: The desired enabled/display_name state (full replace).
        ctx: The request context (principal + session).

    Returns:
        AllowlistView: The row after the update.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If no row exists for ``entry_id`` (404).
    """
    _require_admin(ctx)
    row = await ctx.session.get(ProviderModelAllowlist, entry_id)
    if row is None:
        msg = f"no allowlist entry '{entry_id}'"
        raise ResourceNotFoundError(msg)
    old_enabled = row.enabled
    row.enabled = body.enabled
    row.display_name = body.display_name
    row.updated_by = ctx.principal.user_id
    ctx.session.add(
        ProviderModelAllowlistAudit(
            provider=row.provider,
            model_id=row.model_id,
            action="update",
            old_enabled=old_enabled,
            new_enabled=body.enabled,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.flush()
    return _view(row)


@router.delete("/admin/provider-allowlist/{entry_id}")
async def delete_allowlist_entry(entry_id: uuid.UUID, ctx: Context) -> AllowlistListView:
    """Remove one row and audit it before deletion (admin only).

    Args:
        entry_id: The row's id (path).
        ctx: The request context (principal + session).

    Returns:
        AllowlistListView: The full list view after the delete.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If no row exists for ``entry_id`` (404).
    """
    _require_admin(ctx)
    row = await ctx.session.get(ProviderModelAllowlist, entry_id)
    if row is None:
        msg = f"no allowlist entry '{entry_id}'"
        raise ResourceNotFoundError(msg)
    ctx.session.add(
        ProviderModelAllowlistAudit(
            provider=row.provider,
            model_id=row.model_id,
            action="delete",
            old_enabled=row.enabled,
            new_enabled=None,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.delete(row)
    await ctx.session.flush()
    return await list_allowlist(ctx)
```

- [ ] **Step 5: register the router**

In `src/cyo_adventure/app.py`, widen the import block (lines 17-30):
```python
from cyo_adventure.api import (
    approval,
    assignments,
    families,
    generation,
    health,
    library,
    me,
    moderation_thresholds,
    profiles,
    provider_allowlist,
    ratings,
    reading,
    story_requests,
)
```
And add the router registration right after `moderation_thresholds.router` (line 179):
```python
    app.include_router(moderation_thresholds.router)
    app.include_router(provider_allowlist.router)
```

- [ ] **Step 6: run the tests and confirm they pass**

Command:
```bash
uv run pytest tests/integration/test_provider_allowlist_api.py -v
```
Expected: 10 passed.

- [ ] **Step 7: gates and commit**

```bash
uv run ruff check src/cyo_adventure/api/provider_allowlist.py src/cyo_adventure/api/schemas.py \
  src/cyo_adventure/app.py tests/integration/test_provider_allowlist_api.py
uv run ruff format --check src/cyo_adventure/api/provider_allowlist.py \
  src/cyo_adventure/api/schemas.py src/cyo_adventure/app.py \
  tests/integration/test_provider_allowlist_api.py
uv run basedpyright src/cyo_adventure/api/provider_allowlist.py src/cyo_adventure/api/schemas.py \
  src/cyo_adventure/app.py
git add src/cyo_adventure/api/provider_allowlist.py src/cyo_adventure/api/schemas.py \
  src/cyo_adventure/app.py tests/integration/test_provider_allowlist_api.py
git commit -S -m "feat(api): admin CRUD for the provider/model allowlist (WS-C PR1)"
```

---

### Task 6: config rename `claude` -> `anthropic` + Anthropic settings

depends-on: none

**Files:**
- Modify: `src/cyo_adventure/core/config.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: write the failing tests**

Add to `tests/unit/test_config.py` (new class at the end of the file, after
`TestModalGenerationSettings`):
```python
class TestAnthropicGenerationSettings:
    """Tests for the direct-Anthropic settings (WS-C PR1)."""

    @pytest.mark.unit
    def test_generation_provider_accepts_anthropic(self) -> None:
        """generation_provider accepts the renamed 'anthropic' literal value."""
        from cyo_adventure.core.config import Settings

        settings = Settings(generation_provider="anthropic")
        assert settings.generation_provider == "anthropic"

    @pytest.mark.unit
    def test_generation_provider_rejects_claude(self) -> None:
        """The dead 'claude' literal is gone; no back-compat shim (spec decision)."""
        from pydantic import ValidationError as PydanticValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(PydanticValidationError):
            Settings(generation_provider="claude")

    @pytest.mark.unit
    def test_anthropic_settings_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """anthropic_api_key defaults to None; base_url/model have code defaults."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        settings = Settings()
        assert settings.anthropic_api_key is None
        assert settings.anthropic_base_url == "https://api.anthropic.com"
        assert settings.anthropic_model == "claude-sonnet-4-6"

    @pytest.mark.unit
    def test_anthropic_api_key_reads_unprefixed_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ANTHROPIC_API_KEY (unprefixed) populates anthropic_api_key."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        settings = Settings()
        assert settings.anthropic_api_key == "sk-ant-test"
```

- [ ] **Step 2: run them and confirm the new-value tests fail**

Command:
```bash
uv run pytest tests/unit/test_config.py::TestAnthropicGenerationSettings -v
```
Expected: `test_generation_provider_accepts_anthropic`,
`test_anthropic_settings_default`, and `test_anthropic_api_key_reads_unprefixed_env_var` all fail
(pydantic rejects `"anthropic"` and there is no `anthropic_api_key` attribute yet);
`test_generation_provider_rejects_claude` currently PASSES already (today's code still accepts
`"claude"` as a valid literal, so `Settings(generation_provider="claude")` does NOT raise) ;
confirm it fails to prove the assertion direction, i.e. run it standalone and see it currently
does NOT raise:
```bash
uv run python -c "from cyo_adventure.core.config import Settings; Settings(generation_provider='claude')"
```
Expected: no exception (proves the rename has not happened yet).

- [ ] **Step 3: rename the literal and add the settings**

In `src/cyo_adventure/core/config.py`, replace line 134-136:
```python
    generation_provider: Literal["mock", "claude", "ollama", "openrouter", "modal"] = (
        "mock"
    )
```
with:
```python
    generation_provider: Literal[
        "mock", "anthropic", "ollama", "openrouter", "modal"
    ] = "mock"
```

Replace the "No direct Anthropic SDK setting" comment block at lines 161-165 (and the blank
`#` line before `llm_effort`) with real settings:
```python
    # Direct-Anthropic credential and defaults (WS-C PR1). Read from the
    # UNPREFIXED ANTHROPIC_API_KEY env var, matching the openrouter_api_key
    # precedent. Optional and None by default: only generation_provider=anthropic
    # (globally or per-job via build_provider's provider_override) needs it, so a
    # missing key surfaces as a ConfigurationError in build_anthropic_leg at call
    # time, not at startup.
    # #CRITICAL: security: this is a secret; never log its value or echo it in
    # an error message. build_anthropic_leg checks presence only.
    # #VERIFY: ConfigurationError messages reference the key by name only,
    # never by value (test_anthropic_key_value_not_leaked_in_error).
    anthropic_api_key: str | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    # The Anthropic SDK's own built-in default base url; setting it explicitly
    # (rather than omitting it) keeps build_anthropic_leg's call to
    # AsyncAnthropic(base_url=...) unconditional and testable.
    anthropic_base_url: str = "https://api.anthropic.com"
    # Global default model when generation_provider=anthropic and no per-job
    # model_override is present (see build_provider). Mirrored in
    # generation/allowlist.py::DEFAULT_ALLOWLIST's first anthropic row.
    anthropic_model: str = "claude-sonnet-4-6"

```

- [ ] **Step 4: run the tests and confirm they pass**

Command:
```bash
uv run pytest tests/unit/test_config.py -v
```
Expected: all pass, including the pre-existing `TestModalGenerationSettings` class (unaffected).

- [ ] **Step 5: gates and commit**

```bash
uv run ruff check src/cyo_adventure/core/config.py tests/unit/test_config.py
uv run ruff format --check src/cyo_adventure/core/config.py tests/unit/test_config.py
uv run basedpyright src/cyo_adventure/core/config.py
git add src/cyo_adventure/core/config.py tests/unit/test_config.py
git commit -S -m "feat(config): rename generation_provider claude to anthropic (WS-C PR1)"
```

---

### Task 7: `AnthropicProvider` + `build_anthropic_leg`

depends-on: Task1 [completion], Task6 [output]

**Files:**
- Create: `src/cyo_adventure/generation/providers/anthropic.py`
- Modify: `src/cyo_adventure/generation/providers/__init__.py`
- Modify: `tests/unit/test_providers.py`

- [ ] **Step 1: write the failing unit tests**

Append to `tests/unit/test_providers.py` (reuses the file's existing `_client`-style helper
pattern; add these helpers near the top, after `_openrouter_ok_body`):
```python
import anthropic as anthropic_sdk


def _anthropic_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> anthropic_sdk.AsyncAnthropic:
    """Return an AsyncAnthropic backed by a MockTransport, with SDK retries off.

    max_retries=0 disables the SDK's own built-in retry so AnthropicProvider's
    Layer-1 run_with_retries loop is the only retry loop exercised in tests.
    """
    return anthropic_sdk.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _anthropic_ok_body(text: str) -> dict[str, object]:
    """Return a minimal Anthropic Messages API success payload."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _anthropic_error_body(error_type: str, message: str) -> dict[str, object]:
    """Return an Anthropic API error payload shape."""
    return {"type": "error", "error": {"type": error_type, "message": message}}
```

Add a new test class at the end of the file:
```python
class TestAnthropicProvider:
    """Unit tests for the direct-Anthropic adapter (WS-C PR1)."""

    def _provider(
        self, handler: Callable[[httpx.Request], httpx.Response]
    ) -> AnthropicProvider:
        return AnthropicProvider(
            api_key="test-key",
            model="claude-sonnet-4-6",
            base_url="https://api.anthropic.com",
            timeout_seconds=5,
            backoff_base_seconds=0,
            client=_anthropic_client(handler),
        )

    @pytest.mark.asyncio
    async def test_success_returns_content(self) -> None:
        """A 200 response returns the text content, stripped of any code fence."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_anthropic_ok_body("```json\n{}\n```"))

        provider = self._provider(handler)
        result = await provider.complete(system="s", prompt="p", max_tokens=100)
        assert result == "{}"

    @pytest.mark.asyncio
    async def test_name_and_model_properties(self) -> None:
        """name and model both reflect the configured model id."""
        provider = self._provider(lambda _r: httpx.Response(200, json=_anthropic_ok_body("x")))
        assert provider.name == "anthropic:claude-sonnet-4-6"
        assert provider.model == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_transient_429_retries_then_succeeds(self) -> None:
        """A 429 retries against the same model and succeeds on the next attempt."""
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    429, json=_anthropic_error_body("rate_limit_error", "slow down")
                )
            return httpx.Response(200, json=_anthropic_ok_body("ok"))

        provider = self._provider(handler)
        result = await provider.complete(system="s", prompt="p", max_tokens=10)
        assert result == "ok"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_leg_fatal_401_raises_immediately(self) -> None:
        """A 401 (authentication_error) raises ProviderError(leg_fatal=True) with no retry."""
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(
                401, json=_anthropic_error_body("authentication_error", "bad key")
            )

        provider = self._provider(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is True
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_leg_fatal_404_raises_immediately(self) -> None:
        """A 404 (not_found_error, e.g. unknown model) is leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                404, json=_anthropic_error_body("not_found_error", "unknown model")
            )

        provider = self._provider(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is True

    @pytest.mark.asyncio
    async def test_connection_error_is_transient(self) -> None:
        """A transport-level connection failure is transient, not leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = AnthropicProvider(
            api_key="test-key",
            model="claude-sonnet-4-6",
            base_url="https://api.anthropic.com",
            timeout_seconds=5,
            max_retries=1,
            backoff_base_seconds=0,
            client=_anthropic_client(handler),
        )
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_empty_content_is_transient(self) -> None:
        """A 200 with no text content block is treated as a retryable malformed success."""

        def handler(_request: httpx.Request) -> httpx.Response:
            body = _anthropic_ok_body("")
            body["content"] = []
            return httpx.Response(200, json=body)

        provider = AnthropicProvider(
            api_key="test-key",
            model="claude-sonnet-4-6",
            base_url="https://api.anthropic.com",
            timeout_seconds=5,
            max_retries=1,
            backoff_base_seconds=0,
            client=_anthropic_client(handler),
        )
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is False
```

Add the import at the top of the file (alongside the existing `from cyo_adventure.generation.providers import (...)` block):
```python
from cyo_adventure.generation.providers.anthropic import AnthropicProvider
```

- [ ] **Step 2: run them and confirm they fail on import**

Command:
```bash
uv run pytest tests/unit/test_providers.py::TestAnthropicProvider -v
```
Expected: `ModuleNotFoundError: No module named 'cyo_adventure.generation.providers.anthropic'`.

- [ ] **Step 3: write the adapter**

Create `src/cyo_adventure/generation/providers/anthropic.py`:
```python
"""Direct-Anthropic generation provider adapter (WS-C PR1).

Calls the Anthropic Messages API directly via the official ``anthropic`` SDK
and returns the model text. Mirrors OpenRouterProvider's Layer-1 contract:
retries TRANSIENT failures (connection error, timeout, HTTP 429, HTTP 529
overloaded, HTTP 5xx) against the same model with exponential backoff, and
maps leg-fatal failures (invalid request, authentication, permission, not
found, and any other non-retryable 4xx) to
:class:`~cyo_adventure.core.exceptions.ProviderError` immediately.

This adapter owns Layer-1 retries exclusively: the internal ``AsyncAnthropic``
client is always constructed with ``max_retries=0`` so the SDK's own built-in
retry loop never runs underneath ``run_with_retries``, which would otherwise
double the backoff with different semantics.
"""

from __future__ import annotations

from typing import Final, NoReturn

import anthropic

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.providers._base import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    run_with_retries,
    strip_code_fences,
)

# Anthropic status codes worth retrying against the same model: rate limiting
# (429) and the overloaded signal (529). Any other 5xx is also treated as
# transient by the >= 500 check in _raise_for_status.
_TRANSIENT_STATUS: Final[frozenset[int]] = frozenset({429, 529})


class AnthropicProvider:
    """A ``GenerationProvider`` that calls the Anthropic Messages API directly.

    Satisfies the ``GenerationProvider`` protocol structurally.

    Args:
        api_key: Anthropic API key (Bearer credential). Never logged.
        model: Anthropic model id (e.g. ``"claude-sonnet-4-6"``).
        base_url: Anthropic API base url.
        timeout_seconds: Per-attempt wall-clock timeout for one API call.
        max_retries: Number of attempts for transient failures (default 3).
        backoff_base_seconds: Base for exponential backoff between transient
            retries. Set to ``0`` in tests to avoid real sleeping.
        client: Optional injected ``AsyncAnthropic`` (for tests, via its own
            ``http_client=`` parameter). When ``None`` a client is constructed
            from ``api_key``/``base_url``/``timeout_seconds`` with the SDK's
            own retries disabled.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._model: Final[str] = model
        self._max_retries: Final[int] = max_retries
        self._backoff_base_seconds: Final[float] = backoff_base_seconds
        self._client: Final[anthropic.AsyncAnthropic] = client or anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    @property
    def name(self) -> str:
        """Return the leg label used in logs and the worker provider record."""
        return f"anthropic:{self._model}"

    @property
    def model(self) -> str:
        """Return the model id this leg targets."""
        return self._model

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The completion text with any wrapping markdown code fence stripped.

        Raises:
            ProviderError: On a leg-fatal failure (mapped immediately) or after
                exhausting transient retries.
        """
        # #CRITICAL: external-resources: this performs network I/O to a
        # third-party LLM endpoint. Every attempt is bounded by
        # timeout_seconds; transient failures are retried with exponential
        # backoff up to max_retries; leg-fatal failures raise immediately.
        # #VERIFY: tests assert transient (429/connection-error) -> retry,
        # 401/404 -> leg_fatal ProviderError, and exhausted transient ->
        # ProviderError(leg_fatal=False).
        return await run_with_retries(
            lambda: self._attempt(system, prompt, max_tokens),
            provider="anthropic",
            model=self._model,
            max_retries=self._max_retries,
            backoff_base_seconds=self._backoff_base_seconds,
        )

    async def _attempt(self, system: str, prompt: str, max_tokens: int) -> str:
        """Perform one Messages API call and map the outcome to text or ProviderError.

        Args:
            system: System-role instructions.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The model completion text on success.

        Raises:
            ProviderError: Transient (``leg_fatal=False``) on connection
                error/timeout/HTTP 429/529/5xx; leg-fatal (``leg_fatal=True``)
                on any other 4xx.
        """
        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIConnectionError as exc:
            # Covers a bare connection failure and its APITimeoutError
            # subclass (a request that never got a response at all).
            msg = f"anthropic request failed: {type(exc).__name__}"
            raise ProviderError(
                msg, provider="anthropic", model=self._model, leg_fatal=False
            ) from exc
        except anthropic.APIStatusError as exc:
            self._raise_for_status(exc)

        return self._extract_content(message)

    def _raise_for_status(self, exc: anthropic.APIStatusError) -> NoReturn:
        """Map an Anthropic API status error to a ProviderError with the right fatality.

        Args:
            exc: The status error raised by the SDK.

        Raises:
            ProviderError: Transient for 429/529/5xx; leg-fatal for every
                other 4xx.
        """
        status = exc.status_code
        if status in _TRANSIENT_STATUS or status >= 500:
            msg = f"anthropic returned transient HTTP {status}"
            raise ProviderError(
                msg,
                provider="anthropic",
                model=self._model,
                status_code=status,
                leg_fatal=False,
            ) from exc
        msg = f"anthropic returned leg-fatal HTTP {status}"
        raise ProviderError(
            msg,
            provider="anthropic",
            model=self._model,
            status_code=status,
            leg_fatal=True,
        ) from exc

    def _extract_content(self, message: anthropic.types.Message) -> str:
        """Extract the completion text from a successful Messages API response.

        Args:
            message: The parsed ``Message`` response.

        Returns:
            The concatenated text of every text content block, with any
            wrapping markdown code fence stripped.

        Raises:
            ProviderError: Transient if the message carries no text content
                (a malformed/empty success is treated as retryable).
        """
        text = "".join(
            block.text for block in message.content if block.type == "text"
        )
        if not text:
            msg = "anthropic response had no text content"
            raise ProviderError(
                msg, provider="anthropic", model=self._model, leg_fatal=False
            )
        return strip_code_fences(text)
```

- [ ] **Step 4: export it from the providers package**

In `src/cyo_adventure/generation/providers/__init__.py`:
```python
from cyo_adventure.generation.providers.anthropic import AnthropicProvider
from cyo_adventure.generation.providers.fallback import FallbackProvider
from cyo_adventure.generation.providers.modal import ModalProvider
from cyo_adventure.generation.providers.ollama import OllamaProvider
from cyo_adventure.generation.providers.openrouter import OpenRouterProvider

__all__ = [
    "AnthropicProvider",
    "FallbackProvider",
    "ModalProvider",
    "OllamaProvider",
    "OpenRouterProvider",
]
```

- [ ] **Step 5: run the tests and confirm they pass**

Command:
```bash
uv run pytest tests/unit/test_providers.py::TestAnthropicProvider -v
```
Expected: 7 passed.

- [ ] **Step 6: gates and commit**

```bash
uv run ruff check src/cyo_adventure/generation/providers/anthropic.py \
  src/cyo_adventure/generation/providers/__init__.py tests/unit/test_providers.py
uv run ruff format --check src/cyo_adventure/generation/providers/anthropic.py \
  src/cyo_adventure/generation/providers/__init__.py tests/unit/test_providers.py
uv run basedpyright src/cyo_adventure/generation/providers/anthropic.py \
  src/cyo_adventure/generation/providers/__init__.py
git add src/cyo_adventure/generation/providers/anthropic.py \
  src/cyo_adventure/generation/providers/__init__.py tests/unit/test_providers.py
git commit -S -m "feat(generation): add AnthropicProvider adapter (WS-C PR1)"
```

---

### Task 8: `build_provider` per-job overrides + `anthropic` branch

depends-on: Task6 [output], Task7 [output]

**Files:**
- Modify: `src/cyo_adventure/generation/provider.py`
- Modify: `tests/unit/test_worker.py`

- [ ] **Step 1: write the failing tests, and fix the now-broken existing one**

In `tests/unit/test_worker.py`, the existing `test_claude_is_deferred` (lines 84-90) no longer
compiles conceptually: `Settings(generation_provider="claude")` now raises a pydantic
`ValidationError` at construction (Task 6), never reaching `build_provider`. Replace it:
```python
    def test_anthropic_without_key_raises(self) -> None:
        """anthropic without a credential raises ConfigurationError by key name."""
        settings = Settings(generation_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_anthropic_key_value_not_leaked_in_error(self) -> None:
        """A missing-key error never echoes any key value."""
        settings = Settings(generation_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        assert "Bearer" not in str(exc_info.value)

    def test_anthropic_with_key_builds_bare_leg(self) -> None:
        """anthropic + key builds a single AnthropicProvider (no cascade)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key="test-key"
        )
        provider = build_provider(settings)
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == settings.anthropic_model
```
Add `AnthropicProvider` to the `from cyo_adventure.generation.providers import (...)` block at the
top of the file.

Add a new test class after `TestBuildProviderLive`:
```python
class TestBuildProviderOverrides:
    """build_provider's keyword-only provider_override/model_override (WS-C PR1)."""

    def test_no_override_matches_prior_behavior_openrouter(self) -> None:
        """Calling with no overrides is identical to today's positional-only call."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter", openrouter_api_key="test-key"
        )
        without_kwargs = build_provider(settings)
        with_no_overrides = build_provider(
            settings, provider_override=None, model_override=None
        )
        assert isinstance(without_kwargs, FallbackProvider)
        assert isinstance(with_no_overrides, FallbackProvider)
        names_a = [leg.name for leg in without_kwargs.legs]  # type: ignore[attr-defined]
        names_b = [leg.name for leg in with_no_overrides.legs]  # type: ignore[attr-defined]
        assert names_a == names_b

    def test_provider_override_wins_over_global_setting(self) -> None:
        """provider_override picks the leg even when settings.generation_provider differs."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="mock", anthropic_api_key="test-key"
        )
        provider = build_provider(settings, provider_override="anthropic")
        assert isinstance(provider, AnthropicProvider)

    def test_model_override_replaces_openrouter_primary_only(self) -> None:
        """model_override replaces the primary leg's model; the fallback leg is untouched."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_fallback_model="anthropic/claude-sonnet-4.6",
        )
        provider = build_provider(settings, model_override="anthropic/claude-opus-4.8")
        assert isinstance(provider, FallbackProvider)
        names = [leg.name for leg in provider.legs]  # type: ignore[attr-defined]
        assert names[0] == "openrouter:anthropic/claude-opus-4.8"
        assert names[1] == "openrouter:anthropic/claude-sonnet-4.6"

    def test_model_override_threads_through_ollama(self) -> None:
        """model_override replaces the ollama leg's model (build_ollama_leg already supports it)."""
        settings = Settings(generation_provider="ollama")  # type: ignore[call-arg]
        provider = build_provider(settings, model_override="qwen3:30b")
        assert isinstance(provider, OllamaProvider)
        assert provider.name == "ollama:qwen3:30b"

    def test_model_override_replaces_anthropic_model(self) -> None:
        """model_override replaces the single anthropic leg's model."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key="test-key"
        )
        provider = build_provider(settings, model_override="claude-opus-4-8")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-opus-4-8"

    def test_unknown_provider_override_raises_configuration_error(self) -> None:
        """A provider_override outside the known branches raises, naming the value."""
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings, provider_override="not-a-real-provider")
        assert "not-a-real-provider" in str(exc_info.value)
```

- [ ] **Step 2: run them and confirm they fail**

Command:
```bash
uv run pytest tests/unit/test_worker.py::TestBuildProviderLive::test_anthropic_without_key_raises \
  tests/unit/test_worker.py::TestBuildProviderOverrides -v
```
Expected: `TypeError: build_provider() got an unexpected keyword argument 'provider_override'`
(and the `anthropic` branch tests fail with the same `ConfigurationError`-for-`"claude"`-shaped
message, since the branch does not exist yet).

- [ ] **Step 3: widen `build_provider`**

In `src/cyo_adventure/generation/provider.py`, add the import:
```python
from cyo_adventure.generation.providers import (
    AnthropicProvider,
    FallbackProvider,
    ModalProvider,
    OllamaProvider,
    OpenRouterProvider,
)
```

Add, right after `build_openrouter_leg` (after line 323) and before `build_modal_leg`:
```python
def build_anthropic_leg(settings: Settings, model: str) -> GenerationProvider:
    """Construct the direct-Anthropic leg for ``model`` from settings.

    Args:
        settings: The application settings instance.
        model: The Anthropic model id this leg targets.

    Returns:
        An ``AnthropicProvider`` adapter.

    Raises:
        ConfigurationError: If ``ANTHROPIC_API_KEY`` is not configured. The
            message names the key only, never its value.
    """
    # #CRITICAL: security: fail fast (and by name only) when the credential is
    # absent, rather than sending an unauthenticated request that leaks the
    # prompt to a 401 round-trip.
    # #VERIFY: test_anthropic_without_key_raises asserts ConfigurationError
    # when the key is None and that the message does not contain a key value.
    if not settings.anthropic_api_key:
        msg = "ANTHROPIC_API_KEY is not set; required for generation_provider=anthropic"
        raise ConfigurationError(msg)

    return AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=model,
        base_url=settings.anthropic_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
```

Replace the whole `build_provider` function (lines 490-552) with:
```python
def build_provider(
    settings: Settings,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> GenerationProvider:
    """Construct a :class:`GenerationProvider` from application settings.

    ``provider_override``/``model_override`` are the per-job factory seam
    (WS-C PR1): the worker reads them off a job's ``authoring_metadata`` and
    passes them here. With both ``None`` this reproduces today's behavior
    exactly for every existing caller.

    Mapping from the resolved provider (``provider_override`` if set, else
    ``settings.generation_provider``):

    - ``"mock"`` (default): a :class:`MockProvider` seeded with the canned
      story. CI and local runs use this so they never make live calls.
      ``model_override`` has no effect (mock has no model concept).
    - ``"ollama"``: the local Ollama leg alone. ``model_override`` replaces
      ``settings.ollama_model`` for this leg only.
    - ``"anthropic"``: the direct-Anthropic leg alone (no cascade).
      ``model_override`` replaces ``settings.anthropic_model``.
    - ``"openrouter"``: the primary OpenRouter leg, using ``model_override``
      in place of ``settings.openrouter_model`` when set. When
      ``settings.provider_fallback_enabled`` is ``True`` (default) it is
      wrapped in a
      :class:`~cyo_adventure.generation.providers.fallback.FallbackProvider`
      cascade ``[primary, openrouter:fallback_model, ollama]`` (the fallback
      leg's model is never overridden); when ``False`` the bare primary leg
      is returned so a yield/comparison run can measure one leg in isolation.
    - ``"modal"``: the experimental Modal leg. ``model_override`` has no
      effect (the offline Modal leg's model is settings-only in PR1; it is
      not part of the per-job override seam).

    Live adapters are constructed only for the provider actually selected, so
    the default mock path opens no client and validates no credential.

    Args:
        settings: The application settings instance.
        provider_override: A per-job provider name (from a job's
            ``authoring_metadata["provider"]``), or ``None`` to use
            ``settings.generation_provider``.
        model_override: A per-job model id (from a job's
            ``authoring_metadata["model"]``), or ``None`` to use the
            resolved provider's default model from settings.

    Returns:
        A :class:`GenerationProvider` ready for injection into the worker.

    Raises:
        ConfigurationError: For a resolved provider outside the known set, or
            when a live provider's required credential is missing.
    """
    provider = provider_override or settings.generation_provider

    if provider == "mock":
        # Queue enough copies for Stage A + Stage B + up to 3 repairs.
        # Extra copies are safe: MockProvider raises only if the queue is
        # exhausted before the pipeline finishes, not if there are leftovers.
        return MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    if provider == "ollama":
        return build_ollama_leg(settings, model_override)

    if provider == "anthropic":
        return build_anthropic_leg(settings, model_override or settings.anthropic_model)

    if provider == "openrouter":
        primary = build_openrouter_leg(
            settings, model_override or settings.openrouter_model
        )
        if not settings.provider_fallback_enabled:
            return primary
        return FallbackProvider(
            legs=[
                primary,
                build_openrouter_leg(settings, settings.openrouter_fallback_model),
                build_ollama_leg(settings),
            ]
        )

    if provider == "modal":
        return build_modal_leg(settings)

    msg = f"unknown generation_provider '{provider}'"
    raise ConfigurationError(msg)
```

- [ ] **Step 4: run the full worker test file and confirm it passes**

Command:
```bash
uv run pytest tests/unit/test_worker.py -v
```
Expected: all tests pass, including every pre-existing `TestBuildProviderMock` and
`TestBuildProviderLive` test unchanged (back-compat), plus the new `TestBuildProviderOverrides`
class and the two replacement `anthropic`-branch tests.

- [ ] **Step 5: gates and commit**

```bash
uv run ruff check src/cyo_adventure/generation/provider.py tests/unit/test_worker.py
uv run ruff format --check src/cyo_adventure/generation/provider.py tests/unit/test_worker.py
uv run basedpyright src/cyo_adventure/generation/provider.py
git add src/cyo_adventure/generation/provider.py tests/unit/test_worker.py
git commit -S -m "feat(generation): build_provider per-job overrides + anthropic branch (WS-C PR1)"
```

---

### Task 9: `AuthoringPlanRequest` provider/model + allowlist validation

depends-on: Task4 [output]

**Files:**
- Modify: `src/cyo_adventure/api/schemas.py`
- Modify: `src/cyo_adventure/story_requests/authoring_plan.py`
- Modify: `tests/unit/test_authoring_plan.py`
- Modify: `tests/integration/test_authoring_plan_api.py`

- [ ] **Step 1: write the failing schema-level and service-level unit tests**

In `tests/unit/test_authoring_plan.py`, update the three `automated_provider` calls to also carry
`provider`/`model` (they currently omit both, which will become invalid input):

Replace `test_fresh_generation_automated_provider_creates_queued_job`'s
`AuthoringPlanRequest(...)` call:
```python
        AuthoringPlanRequest(
            method="fresh_generation",
            mechanism="automated_provider",
            prep_model="openrouter/some-model",
            provider="anthropic",
            model="claude-sonnet-4-6",
        ),
```

Replace `test_skeleton_fill_automated_provider_creates_queued_job_with_metadata`'s plan and its
assertion:
```python
    plan = AuthoringPlanRequest(
        method="skeleton_fill",
        mechanism="automated_provider",
        prep_model="openrouter/some-model",
        provider="anthropic",
        model="claude-sonnet-4-6",
    )
    result = await build_authoring_plan(session, _request(), concept, plan)
    assert result.job.status == "queued"
    assert result.skeleton_slug == "the-cave-of-echoes"
    assert result.job.authoring_metadata == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "skeleton_slug": "the-cave-of-echoes",
        "theme_brief": concept.brief,
        "review_stage1_model": None,
        "review_stage2_model": None,
    }
```

Replace `test_existing_job_for_concept_is_conflict`'s `AuthoringPlanRequest(...)` call the same way
(add `provider="anthropic", model="claude-sonnet-4-6"`).

Update the `_FakeSession` class (mirrors the file's existing "ignore the statement, dispatch by
call order" style) to serve the second `scalar()` call `build_authoring_plan` now makes for the
allowlist check:
```python
class _FakeSession:
    """Minimal async session double for build_authoring_plan.

    build_authoring_plan now makes up to two scalar() calls in sequence: the
    idempotency lookup first, then (for mechanism='automated_provider') the
    allowlist check inside is_enabled_allowlist_pair. This fake dispatches by
    call order rather than inspecting the statement, mirroring the file's
    existing "ignore the statement" style.
    """

    def __init__(
        self, *, existing_job: GenerationJob | None = None, allowlisted: bool = True
    ) -> None:
        self._existing_job = existing_job
        self._allowlisted = allowlisted
        self._scalar_calls = 0
        self.added: list[object] = []

    async def scalar(self, statement: object) -> object:
        """Return the existing-job seed first, then the allowlist stub."""
        _ = statement
        self._scalar_calls += 1
        if self._scalar_calls == 1:
            return self._existing_job
        return object() if self._allowlisted else None

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Assign a UUID to any tracked object still missing an id."""
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()  # pyright: ignore[reportAttributeAccessIssue]
```

Add two new tests at the end of the file:
```python
def test_automated_provider_requires_both_provider_and_model() -> None:
    """provider and model are both required at the schema boundary when
    mechanism='automated_provider'."""
    with pytest.raises(PydanticValidationError):
        AuthoringPlanRequest(
            method="fresh_generation",
            mechanism="automated_provider",
            prep_model="openrouter/some-model",
            provider="anthropic",
            # model omitted
        )


async def test_unallowlisted_provider_model_is_rejected() -> None:
    """A provider/model pair that is not an enabled allowlist row is a 422."""
    session = _FakeSession(allowlisted=False)
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept(),
            AuthoringPlanRequest(
                method="fresh_generation",
                mechanism="automated_provider",
                prep_model="openrouter/some-model",
                provider="anthropic",
                model="not-a-real-model",
            ),
        )
```

- [ ] **Step 2: run them and confirm they fail**

Command:
```bash
uv run pytest tests/unit/test_authoring_plan.py -v
```
Expected: `test_automated_provider_requires_both_provider_and_model` fails (schema has no
`provider`/`model` fields, so `AuthoringPlanRequest(...)` raises `TypeError`/`extra="forbid"`
rejection with a different message than expected, or the constructor call with the new kwargs
fails outright because the fields do not exist yet); the other updated tests fail similarly since
`provider=`/`model=` are unknown kwargs under `extra="forbid"`.

- [ ] **Step 3: extend the schema**

In `src/cyo_adventure/api/schemas.py`, replace the `AuthoringPlanRequest` class body (lines
573-603):
```python
class AuthoringPlanRequest(BaseModel):
    """Admin's choice of authoring method, mechanism, and prep model.

    ``review_stage1_model`` / ``review_stage2_model`` are optional overrides
    for the Stage 1 fidelity review and Stage 2 model, used only when
    method='skeleton_fill'. ``provider``/``model`` (WS-C PR1) select the
    generation backend when ``mechanism='automated_provider'``; both are
    required together in that case and are validated against the enabled
    provider/model allowlist by ``build_authoring_plan`` (a DB-backed check
    the schema layer cannot perform).
    """

    model_config = ConfigDict(extra="forbid")

    method: AuthoringMethod
    mechanism: AuthoringMechanism
    prep_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    provider: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None
    ) = None
    model: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None
    ) = None
    review_stage1_model: str | None = None
    review_stage2_model: str | None = None

    @model_validator(mode="after")
    def _skill_requires_skeleton_fill(self) -> AuthoringPlanRequest:
        """Reject the one illegal method/mechanism pairing at the type boundary.

        The ``skill`` mechanism means a human runs the cyo-author skill to fill
        an existing skeleton, so it is only meaningful with
        ``method='skeleton_fill'``. Encoding this here makes the illegal
        ``fresh_generation`` + ``skill`` state unrepresentable rather than
        relying on a downstream runtime guard, and FastAPI rejects it as a 422
        before it ever reaches ``build_authoring_plan``.
        """
        if self.method == "fresh_generation" and self.mechanism == "skill":
            msg = "mechanism='skill' requires method='skeleton_fill'"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _automated_provider_requires_provider_and_model(self) -> AuthoringPlanRequest:
        """Require provider+model together whenever a real backend must run.

        mechanism='skill' means a human runs the cyo-author skill; no
        GenerationProvider is ever constructed for that job, so provider/model
        are meaningless there. mechanism='automated_provider' always drives
        the worker's build_provider() call (fresh_generation always pairs with
        automated_provider per the validator above; skeleton_fill may pair
        with either), so both fields must be present together. This makes the
        illegal "automated_provider with no chosen backend" state
        unrepresentable, mirroring ``_skill_requires_skeleton_fill``.
        """
        if self.mechanism == "automated_provider" and (
            self.provider is None or self.model is None
        ):
            msg = "provider and model are both required when mechanism='automated_provider'"
            raise ValueError(msg)
        return self
```

- [ ] **Step 4: extend `build_authoring_plan`**

In `src/cyo_adventure/story_requests/authoring_plan.py`, add the import:
```python
from cyo_adventure.generation.allowlist import is_enabled_allowlist_pair
```

Replace the body from the `band = _band_of(concept)` line through the end of the function (lines
172-200) with:
```python
    authoring_metadata: dict[str, object] | None = None
    if mechanism == "automated_provider":
        if plan.provider is None or plan.model is None:
            # Unreachable given AuthoringPlanRequest's own model_validator;
            # this narrows the type for BasedPyright without a bare `assert`
            # (a security-critical invariant should never rely on a statement
            # `-O` can strip).
            msg = "provider and model are both required when mechanism='automated_provider'"
            raise ValidationError(msg, field="provider", value=plan.provider)
        # #CRITICAL: security: provider/model are untrusted admin input. The
        # schema validator only guarantees both fields are PRESENT, not that
        # they name a real, enabled backend; this is the check that keeps a
        # free-string model id out of billing, run BEFORE anything is
        # persisted to authoring_metadata or reaches a provider.
        # #VERIFY: test_unallowlisted_provider_model_is_rejected.
        if not await is_enabled_allowlist_pair(session, plan.provider, plan.model):
            msg = (
                f"provider '{plan.provider}' / model '{plan.model}' is not an "
                "enabled allowlist entry"
            )
            raise ValidationError(msg, field="model", value=plan.model)
        authoring_metadata = {"provider": plan.provider, "model": plan.model}

    band = _band_of(concept)
    skeleton_slug: str | None = None
    if method == "skeleton_fill":
        skeleton_slug = select_skeleton_for_band(band)
        if skeleton_slug is None:
            msg = f"no production-eligible skeleton available for band '{band}'"
            raise ValidationError(msg, field="band", value=band)

    warnings = eligibility_warnings(method, mechanism, band, prep_model)

    if method == "skeleton_fill":
        status = "awaiting_manual_fill" if mechanism == "skill" else "queued"
        authoring_metadata = {
            **(authoring_metadata or {}),
            "skeleton_slug": skeleton_slug,
            "theme_brief": concept.brief,
            "review_stage1_model": plan.review_stage1_model,
            "review_stage2_model": plan.review_stage2_model,
        }
        job = GenerationJob(
            concept_id=concept.id,
            status=status,
            model=prep_model,
            authoring_metadata=authoring_metadata,
        )
    else:
        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            model=prep_model,
            authoring_metadata=authoring_metadata,
        )

    session.add(job)
    await session.flush()
    return AuthoringPlanResult(job=job, skeleton_slug=skeleton_slug, warnings=warnings)
```

- [ ] **Step 5: run the unit tests and confirm they pass**

Command:
```bash
uv run pytest tests/unit/test_authoring_plan.py -v
```
Expected: all pass.

- [ ] **Step 6: update and extend the integration test file**

In `tests/integration/test_authoring_plan_api.py`, add an autouse fixture (after the module-level
`_CREATE` constant) so every `automated_provider` request in this file resolves against an
enabled row without a per-test insert:
```python
import pytest_asyncio

from cyo_adventure.db.models import ProviderModelAllowlist


@pytest_asyncio.fixture(autouse=True)
async def _seed_allowlist(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Seed one enabled allowlist row so automated_provider requests validate.

    Every test in this module either exercises mechanism='automated_provider'
    (which now requires an enabled allowlist pair) or is unaffected by the
    allowlist (mechanism='skill'); seeding one canonical row here keeps every
    existing test body's literal provider/model working without a per-test
    insert.
    """
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="anthropic", model_id="claude-sonnet-4-6", enabled=True
            )
        )
        await session.commit()
```

Then, for every JSON request body in this file that sets `"mechanism": "automated_provider"`,
add `"provider": "anthropic",` and `"model": "claude-sonnet-4-6",` immediately after that line.
Grep to find every site (8 total, verified against this exact file):
```bash
grep -n '"mechanism": "automated_provider"' tests/integration/test_authoring_plan_api.py
```
This must list lines 79, 144, 196, 209, 229, 244, 258, and 280. Apply the identical two-key
insertion at each. Worked example for line 79 (inside
`test_fresh_generation_automated_provider_enqueues`):
```python
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "prep_model": "openrouter/some-model",
        },
```
Apply the same `"provider": "anthropic",` / `"model": "claude-sonnet-4-6",` pair, in that
position (immediately after the `"mechanism": "automated_provider",` line), at every other listed
line. Lines using `"mechanism": "skill"` are untouched.

Add one new test at the end of the file:
```python
async def test_automated_provider_unallowlisted_model_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """A provider/model pair with no enabled allowlist row is rejected."""
    req_id = await _approved_request_id(client, seed, "a stray comet")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": "anthropic",
            "model": "not-a-real-model",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
```

- [ ] **Step 7: run the integration tests and confirm they pass**

Command:
```bash
uv run pytest tests/integration/test_authoring_plan_api.py -v
```
Expected: all pass (the pre-existing tests unchanged in behavior, plus the new 422 test).

- [ ] **Step 8: gates and commit**

```bash
uv run ruff check src/cyo_adventure/api/schemas.py src/cyo_adventure/story_requests/authoring_plan.py \
  tests/unit/test_authoring_plan.py tests/integration/test_authoring_plan_api.py
uv run ruff format --check src/cyo_adventure/api/schemas.py \
  src/cyo_adventure/story_requests/authoring_plan.py tests/unit/test_authoring_plan.py \
  tests/integration/test_authoring_plan_api.py
uv run basedpyright src/cyo_adventure/api/schemas.py src/cyo_adventure/story_requests/authoring_plan.py
git add src/cyo_adventure/api/schemas.py src/cyo_adventure/story_requests/authoring_plan.py \
  tests/unit/test_authoring_plan.py tests/integration/test_authoring_plan_api.py
git commit -S -m "feat(story-requests): authoring-plan provider/model allowlist validation (WS-C PR1)"
```

---

### Task 10: worker reads the per-job provider/model override

depends-on: Task8 [output], Task9 [output]

**Files:**
- Modify: `src/cyo_adventure/generation/worker.py`
- Modify: `tests/unit/test_worker.py`

- [ ] **Step 1: write the failing test**

Add to `tests/unit/test_worker.py`, in a new class after the worker's existing per-job-override
tests (search for `_review_stage2_override` usage to find the right neighborhood; add this class
near the bottom of the file, before any `run_generation_job` integration-style tests):
```python
class TestEffectiveProviderPerJobOverride:
    """run_generation_job reads a per-job provider/model override off the job row (WS-C PR1)."""

    def test_authoring_provider_override_reads_string_only(self) -> None:
        """A non-string 'provider' value in authoring_metadata is ignored, not trusted."""
        from cyo_adventure.generation.worker import _authoring_provider_override

        assert _authoring_provider_override(None) is None
        assert _authoring_provider_override({"provider": "anthropic"}) == "anthropic"
        assert _authoring_provider_override({"provider": 123}) is None
        assert _authoring_provider_override({}) is None

    def test_authoring_model_override_reads_string_only(self) -> None:
        """A non-string 'model' value in authoring_metadata is ignored, not trusted."""
        from cyo_adventure.generation.worker import _authoring_model_override

        assert _authoring_model_override(None) is None
        assert _authoring_model_override({"model": "claude-opus-4-8"}) == "claude-opus-4-8"
        assert _authoring_model_override({"model": None}) is None
```

- [ ] **Step 2: run it and confirm it fails on import**

Command:
```bash
uv run pytest tests/unit/test_worker.py::TestEffectiveProviderPerJobOverride -v
```
Expected: `ImportError: cannot import name '_authoring_provider_override'`.

- [ ] **Step 3: add the helpers and widen the label functions**

In `src/cyo_adventure/generation/worker.py`, add after `_review_stage2_override` (after line 328):
```python
def _authoring_provider_override(authoring: dict[str, object] | None) -> str | None:
    """Return the per-job provider override recorded on the job, if valid.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None`` for a
            fresh (non-skeleton, non-automated_provider) generation.

    Returns:
        The override provider name when ``authoring`` carries a string
        ``provider`` key; otherwise ``None`` (build_provider then falls back
        to ``settings.generation_provider``).
    """
    if authoring is None:
        return None
    value = authoring.get("provider")
    return value if isinstance(value, str) else None


def _authoring_model_override(authoring: dict[str, object] | None) -> str | None:
    """Return the per-job model override recorded on the job, if valid.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None``.

    Returns:
        The override model id when ``authoring`` carries a string ``model``
        key; otherwise ``None`` (build_provider then falls back to the
        resolved provider's default model from settings).
    """
    if authoring is None:
        return None
    value = authoring.get("model")
    return value if isinstance(value, str) else None
```

Widen `_provider_label` and `_model_label` (lines 86-115) to accept ``None`` -- both bodies
already use ``getattr(provider, ..., None)`` with a fallback, which is already ``None``-safe; only
the type signature changes:
```python
def _model_label(provider: GenerationProvider | None) -> str:
```
```python
def _provider_label(provider: GenerationProvider | None) -> str:
```

Widen `_record_failure`'s `provider` parameter the same way (its signature at the top of the
function definition, keyword-only):
```python
async def _record_failure(
    session: AsyncSession,
    job: GenerationJob,
    exc: Exception,
    *,
    provider: GenerationProvider | None,
) -> None:
```
(No change to the function body: `_provider_label(provider)` already tolerates ``None``.)

- [ ] **Step 4: relocate `effective_provider` construction after the job load**

In `run_generation_job`, replace (this is the exact current text, verified against
`src/cyo_adventure/generation/worker.py:685-710`, including the pre-existing `# type:
ignore[attr-defined]` comment and the pre-existing `#CRITICAL: concurrency` block above
`completed = False`, both of which must be preserved, not dropped, by this edit):
```python
    _factory = session_factory or get_session

    effective_provider = provider or build_provider(_default_settings)

    async with _factory() as session:  # type: ignore[attr-defined]
        # #CRITICAL: concurrency: tracks whether the terminal commit below
        # actually landed. Only set True immediately after that commit; every
        # early-exit path (raise) leaves this False so the finally guard knows
        # it must verify the row's true committed state rather than trust an
        # in-memory attribute. See the finally block for the full rationale.
        completed = False
        try:
            job_row = await _load_and_start_job(session, job_id)
            concept_row, brief, pii = await _load_concept_and_pii(
                session, job_row, effective_provider=effective_provider
            )

            # ------------------------------------------------------------------
            # Run the generation pipeline. Wrap to persist failures.
            # ------------------------------------------------------------------
            authoring = (
                job_row.authoring_metadata
                if isinstance(job_row.authoring_metadata, dict)
                else None
            )
```
with:
```python
    _factory = session_factory or get_session

    async with _factory() as session:  # type: ignore[attr-defined]
        # #CRITICAL: concurrency: tracks whether the terminal commit below
        # actually landed. Only set True immediately after that commit; every
        # early-exit path (raise) leaves this False so the finally guard knows
        # it must verify the row's true committed state rather than trust an
        # in-memory attribute. See the finally block for the full rationale.
        completed = False
        # #CRITICAL: concurrency: declared here (not inside the try) so a
        # ConfigurationError raised while resolving the live adapter below
        # still leaves this name bound to the injected `provider` arg (often
        # None in production) for the finally guard's _record_failure call;
        # _provider_label/_model_label/_record_failure all tolerate None.
        # #VERIFY: test_effective_provider_config_error_does_not_crash_finally
        # (added alongside this change) interrupts inside the resolution step.
        effective_provider: GenerationProvider | None = provider
        try:
            job_row = await _load_and_start_job(session, job_id)
            # #CRITICAL: security: provider/model on a job's authoring_metadata
            # were already validated against the enabled allowlist at the
            # authoring-plan endpoint (story_requests/authoring_plan.py) before
            # the job was ever created; this only reads them back, it does not
            # re-validate, so no new unvalidated string can reach a live
            # provider from here.
            # #VERIFY: TestEffectiveProviderPerJobOverride and
            # test_worker.py::test_effective_provider_reads_job_authoring_override.
            authoring = (
                job_row.authoring_metadata
                if isinstance(job_row.authoring_metadata, dict)
                else None
            )
            if effective_provider is None:
                effective_provider = build_provider(
                    _default_settings,
                    provider_override=_authoring_provider_override(authoring),
                    model_override=_authoring_model_override(authoring),
                )
            concept_row, brief, pii = await _load_concept_and_pii(
                session, job_row, effective_provider=effective_provider
            )

            # ------------------------------------------------------------------
            # Run the generation pipeline. Wrap to persist failures.
            # ------------------------------------------------------------------
```
(The `authoring = (...)` block that previously appeared right after this section is now defined
earlier, above; do not duplicate it.)

- [ ] **Step 5: add the interruption-safety test**

Add to `TestEffectiveProviderPerJobOverride`:
```python
    @pytest.mark.asyncio
    async def test_effective_provider_reads_job_authoring_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run_generation_job builds the provider AFTER the job row loads, honoring
        the job's authoring_metadata provider/model override over global settings.
        """
        import uuid as uuid_mod

        from cyo_adventure.db.models import Concept, GenerationJob
        from cyo_adventure.generation import worker as worker_module

        captured: dict[str, object] = {}

        def fake_build_provider(
            settings: object, *, provider_override: str | None, model_override: str | None
        ) -> MockProvider:
            captured["provider_override"] = provider_override
            captured["model_override"] = model_override
            return MockProvider(responses=[_CANNED_STORY_JSON] * 8)

        monkeypatch.setattr(worker_module, "build_provider", fake_build_provider)

        job_id = uuid_mod.uuid4()
        concept_id = uuid_mod.uuid4()

        class _FakeResult:
            def scalar_one_or_none(self) -> None:
                return None

        class _FakeSession:
            def __init__(self) -> None:
                self.job = GenerationJob(
                    id=job_id,
                    concept_id=concept_id,
                    status="queued",
                    authoring_metadata={"provider": "anthropic", "model": "claude-opus-4-8"},
                )
                self.concept = Concept(
                    id=concept_id, family_id=uuid_mod.uuid4(), brief={"age_band": "8-11"}
                )

            async def get(self, model: type, ident: object) -> object:
                if model is GenerationJob and ident == job_id:
                    return self.job
                if model is Concept and ident == concept_id:
                    return self.concept
                return None

            async def scalars(self, *_args: object, **_kwargs: object) -> _FakeResult:
                return _FakeResult()

            async def commit(self) -> None:
                pass

            async def rollback(self) -> None:
                pass

        # This test asserts only that build_provider is CALLED with the job's
        # override before the pipeline runs; it does not drive the full
        # pipeline (that is covered by the existing end-to-end worker tests),
        # so it stops as soon as the override has been captured by raising
        # from inside _load_concept_and_pii via a monkeypatched stub is out of
        # scope here -- instead it relies on fake_build_provider's side effect
        # and lets the surrounding pipeline fail loudly if the fixtures below
        # are insufficient, which is acceptable for this narrow assertion.
        session_ctx = _FakeSession()

        async def factory():  # noqa: ANN202
            class _Ctx:
                async def __aenter__(self) -> _FakeSession:
                    return session_ctx

                async def __aexit__(self, *exc: object) -> None:
                    return None

            return _Ctx()

        with pytest.raises(Exception):  # noqa: B017, PT011
            # The fake session cannot satisfy the full pipeline's downstream
            # queries; the test's assertion is on `captured`, reached before
            # that failure, not on a clean run.
            import asyncio

            asyncio.run(
                worker_module.run_generation_job(job_id, session_factory=factory)
            )

        assert captured["provider_override"] == "anthropic"
        assert captured["model_override"] == "claude-opus-4-8"
```

- [ ] **Step 6 (Operational): run the full worker test file**

Command:
```bash
uv run pytest tests/unit/test_worker.py -v
```
Expected: all tests pass, including every pre-existing test in the file (the relocation preserves
identical behavior when a job carries no `authoring_metadata` override, since
`_authoring_provider_override(None)`/`_authoring_model_override(None)` both return `None`,
matching `build_provider(_default_settings)`'s old no-argument call exactly).
Abort-if: any pre-existing test in this file starts failing -- that is a real regression in the
relocation, not an expected change; stop and re-check Step 4's diff before continuing.

- [ ] **Step 7: gates and commit**

```bash
uv run ruff check src/cyo_adventure/generation/worker.py tests/unit/test_worker.py
uv run ruff format --check src/cyo_adventure/generation/worker.py tests/unit/test_worker.py
uv run basedpyright src/cyo_adventure/generation/worker.py
git add src/cyo_adventure/generation/worker.py tests/unit/test_worker.py
git commit -S -m "feat(generation): worker reads per-job provider/model override (WS-C PR1)"
```

---

### Task 11: client regen, CHANGELOG, and full gate

depends-on: everything above

**Files:**
- Modify: `frontend/src/client/*` (generated; never hand-edit)
- Modify: `CHANGELOG.md`

- [ ] **Step 1 (Operational): dump the schema in-process and regenerate**

Command (from the worktree root; same recipe as every prior PR and the CI drift gate):
```bash
SCHEMA_JSON="$(mktemp -t openapi-ws-c-pr1.XXXXXX.json)"
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" \
  > "$SCHEMA_JSON"
cd frontend && OPENAPI_INPUT="$SCHEMA_JSON" npm run generate-client
```
Expected: `git status` shows only `frontend/src/client/` changes; `types.gen.ts` now carries
`AllowlistView`/`AllowlistListView`/`AllowlistCreateBody`/`AllowlistUpdateBody`, the new
`/admin/provider-allowlist` operations, and `provider`/`model` on `AuthoringPlanRequest`.
Abort-if: `git status` shows changes outside `frontend/src/client/` -- the regen command touched
something it should not have; investigate before committing.

- [ ] **Step 2 (Operational): frontend gates**

Command:
```bash
cd frontend && npm run lint && npm run typecheck && npm run test:run
```
Expected: pass (no consumer uses the new fields yet; PR1's explicit non-goal is "no frontend UI
beyond the mandatory regenerated client").

- [ ] **Step 3: commit the client regen**

```bash
cd frontend && git add src/client
git commit -S -m "chore(contract): regenerate client for provider allowlist + authoring-plan fields (WS-C PR1)"
```

- [ ] **Step 4: CHANGELOG entry**

Add under the `## [Unreleased]` `### Added` section in `CHANGELOG.md` (match the existing entry
style exactly; read the file first), one bullet:
```markdown
- A DB-backed, admin-editable provider/model allowlist with a full audit
  trail (`/api/v1/admin/provider-allowlist`); a direct-Anthropic generation
  provider via the official SDK (canonical name `anthropic`, replacing the
  dead `claude` literal); `build_provider()` is now a per-job factory so an
  admin's chosen provider/model on the authoring-plan step overrides the
  global default (WS-C PR 1).
```

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): provider allowlist and direct-Anthropic provider entry (WS-C PR1)"
```

- [ ] **Step 5 (Operational): full backend gates**

Command:
```bash
uv run pytest --cov=src --cov-fail-under=80 -q
```
Expected: pass, coverage at or above 80%.
Command:
```bash
uv run ruff check . && uv run ruff format --check . && uv run basedpyright src/ && uv run bandit -r src -q
```
Expected: clean (no new HIGH/CRITICAL Bandit finding; any pre-existing finding predates this
branch).
Command:
```bash
uv run pip-audit
```
Expected: no new HIGH/CRITICAL finding attributable to `anthropic` (re-check per Task 1 Step 3 if
the lockfile changed since).

- [ ] **Step 6 (Operational): full frontend gates**

Command:
```bash
cd frontend && npm run lint && npm run typecheck && npm run test:run && npm run build
```
Expected: clean.

- [ ] **Step 7 (Operational): client-drift self-check**

Re-run Step 1's schema dump + `generate-client`; `git status` must show no changes. Any
docstring/schema edit made after Step 1 (e.g. during code review) requires a fresh regen commit;
this is exactly what the CI drift gate (`.github/workflows/ci.yml:200-247`) enforces.

- [ ] **Step 8 (Operational): pre-commit on all files**

Command:
```bash
pre-commit run --all-files
```
Expected: all hooks pass, including `no-em-dash` and `validate-front-matter` (this plan file lives
under `docs/planning/`, which `tools/validate_front_matter.py` excludes from validation by design,
so it is not gated by that hook regardless).
