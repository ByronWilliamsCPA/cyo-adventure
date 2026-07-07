---
schema_type: planning
title: "WS-A: Age-Band Moderation Thresholds Implementation Plan"
description: "Task-level implementation plan for workstream A of the story lifecycle redesign:
  moderation_threshold table, serialization-boundary filtering of moderation tags for guardian and
  kid surfaces, and the admin threshold editor with audit trail."
tags:
  - planning
  - moderation
  - implementation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an engineer with zero context everything needed to implement WS-A task by task:
  exact files, complete code, test-first steps, and verification commands."
component: Moderation
source: "docs/planning/story-lifecycle-redesign.md (umbrella design, decisions 2 and 8); codebase
  discovery 2026-07-06 against origin/main c6915bf."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Stop the wall of flags: record every moderation finding, but surface tags to guardians and kids
only when they meet a per-(age_band, category) threshold; give admins full visibility plus an
editor for the thresholds, with every change audited.

## Architecture

A pure-logic `ThresholdPolicy` (code default: surface `flag` and above) resolves sparse DB
override rows from a new `moderation_threshold` table. Filtering happens at the serialization
boundary only: `build_content_summary` (which both the guardian content-summary route and the
guardian books list reuse) and the story-request list projection. The moderation pipeline and the
admin review surface are untouched. An admin-only CRUD router edits threshold rows and writes an
audit row per change.

## Root cause being fixed

`moderation/classifiers.py` emits `Verdict.ADVISORY` findings for OpenAI graded categories at
scores as low as 0.01, and no surface filters findings by severity or age band. With the code
default `min_verdict = flag`, those advisories stop reaching guardians the moment this ships,
retroactively for already-moderated books (the filter is at read time).

## Tech stack

FastAPI (async), SQLAlchemy 2.x `Mapped[]` models, Alembic, Pydantic v2, pytest +
testcontainers Postgres, React 19 + generated openapi-ts client, Vitest.

## Verified base facts (origin/main c6915bf)

- Alembic head: `a7b8c9d0e1f2` (`migrations/versions/20260706_1500_add_storybook_version_provider.py`).
- `Verdict` StrEnum (`block/flag/advisory/pass`) and frozen `Finding` dataclass:
  `src/cyo_adventure/moderation/report.py`.
- Guardian moderation surfaces: `build_content_summary` in `src/cyo_adventure/api/review_surface.py`
  lines 284-340 (called by `get_content_summary` and `_guardian_book_item` in
  `src/cyo_adventure/api/assignments.py`); story-request flags in `_to_view`,
  `src/cyo_adventure/api/story_requests.py` lines 95-150 (list handler does NOT join ChildProfile,
  so the age band is not currently available there).
- Storybook age band lives in the blob: `_book_age_band(blob)` helper,
  `src/cyo_adventure/api/assignments.py` lines 272-286 (`metadata.age_band`).
- Admin gate pattern: explicit `ctx.principal.is_admin` check before any load
  (`src/cyo_adventure/api/approval.py`).
- Routers registered in `src/cyo_adventure/app.py` lines 168-177.
- Migration round-trip test pattern with PINNED revision ids:
  `tests/integration/test_storybook_version_provider_migration.py`.
- Integration fixtures: `tests/integration/conftest.py` (`client: AsyncClient`, `seed: Seed`,
  `auth(token)`; schema via `Base.metadata.create_all`, so new models are visible to API tests
  without running Alembic).
- Age band values: `"3-5", "5-8", "8-11", "10-13", "13-16", "16+"` (`AgeBand` StrEnum in
  `src/cyo_adventure/storybook/models.py`).

## Out of scope (deferred)

- Annotating the ADMIN review surface with per-finding below-threshold markers (dashboard, WS-F).
- Any change to the moderation pipeline itself (it keeps recording everything).
- pipeline_event rows for threshold changes (WS-D will subsume the audit table's role; the audit
  table here is deliberately minimal).
- Kid-facing endpoints currently expose no moderation fields; Task 5 adds a contract test locking
  that in, nothing more.

## Conventions that apply to every task

- Branch: `feat/ws-a-moderation-thresholds` off `origin/main`, in worktree
  `.worktrees/ws-a-moderation-thresholds` (run `uv sync --all-extras` after creating it).
- Sign every commit: `git commit -S`. Conventional Commits. Never use an em-dash in any text.
- Stage only the files you changed (`git add <paths>`), never `git add -A`.
- Python: 88-char lines, BasedPyright strict, Google docstrings, RAD tags on functions touching
  DB/auth (see `src/cyo_adventure/CLAUDE.md`).
- Raise only exceptions from `core/exceptions.py` in routes/services.
- Before each commit: `uv run ruff format <files> && uv run ruff check <files> && uv run
  basedpyright src/`.

---

### Task 0: Branch and worktree setup (operational)

- [ ] **Step 1: Create the worktree**

Run:

```bash
cd /home/byron/dev/CYO_Adventure
git fetch origin main
git worktree add .worktrees/ws-a-moderation-thresholds -b feat/ws-a-moderation-thresholds origin/main
cd .worktrees/ws-a-moderation-thresholds && uv sync --all-extras
```

Expected: worktree created, deps installed.
Abort if: `git worktree add` reports the path already exists (a prior run owns it; coordinate,
do not delete).

- [ ] **Step 2: Confirm the Alembic head is still `a7b8c9d0e1f2`**

Run: `uv run alembic heads`
Expected: exactly one head, `a7b8c9d0e1f2`.
Abort if: a different head exists. Another migration landed; update Task 2's `down_revision` and
the pinned ids in Task 2 Step 6 to the new head before proceeding.

---

### Task 1: Threshold policy module (pure logic)

**Files:**

- Create: `src/cyo_adventure/moderation/thresholds.py`
- Test: `tests/unit/test_moderation_thresholds.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the age-band moderation threshold policy."""

from __future__ import annotations

import pytest

from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import (
    DEFAULT_THRESHOLD,
    Threshold,
    ThresholdPolicy,
)

pytestmark = pytest.mark.unit


def _policy(rows: dict[tuple[str, str], Threshold] | None = None) -> ThresholdPolicy:
    return ThresholdPolicy(rows=rows or {})


def test_default_hides_advisory() -> None:
    """With no override rows, an advisory finding does not surface."""
    assert not _policy().surfaces(
        age_band="8-11", category="toxicity", verdict=Verdict.ADVISORY, score=0.4
    )


def test_default_surfaces_flag_and_block() -> None:
    """Flag and block findings surface under the code default."""
    policy = _policy()
    assert policy.surfaces(
        age_band="8-11", category="safety", verdict=Verdict.FLAG, score=None
    )
    assert policy.surfaces(
        age_band="8-11", category="safety", verdict=Verdict.BLOCK, score=None
    )


def test_pass_never_surfaces() -> None:
    """A pass verdict never surfaces, even if a row lowers the floor."""
    rows = {("3-5", "safety"): Threshold(min_verdict=Verdict.ADVISORY, min_score=None)}
    assert not _policy(rows).surfaces(
        age_band="3-5", category="safety", verdict=Verdict.PASS, score=None
    )


def test_row_lowers_floor_to_advisory() -> None:
    """An override row can surface advisories for a specific band and category."""
    rows = {("3-5", "violence"): Threshold(min_verdict=Verdict.ADVISORY, min_score=None)}
    policy = _policy(rows)
    assert policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=0.2
    )
    # Other bands still use the default.
    assert not policy.surfaces(
        age_band="13-16", category="violence", verdict=Verdict.ADVISORY, score=0.2
    )


def test_min_score_floor_applies_to_scored_findings_only() -> None:
    """min_score hides low-scored findings but never unscored ones."""
    rows = {("3-5", "violence"): Threshold(min_verdict=Verdict.ADVISORY, min_score=0.3)}
    policy = _policy(rows)
    assert not policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=0.1
    )
    assert policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=0.31
    )
    assert policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=None
    )


def test_string_verdict_is_coerced() -> None:
    """Callers holding serialized verdict strings get the same behavior."""
    assert _policy().surfaces(
        age_band="8-11", category="safety", verdict="flag", score=None
    )


def test_unknown_string_verdict_does_not_surface() -> None:
    """A malformed stored verdict is treated as not surfaceable, not a crash."""
    assert not _policy().surfaces(
        age_band="8-11", category="safety", verdict="banana", score=None
    )


def test_default_threshold_is_flag() -> None:
    """Lock the code default so it cannot drift silently."""
    assert DEFAULT_THRESHOLD == Threshold(min_verdict=Verdict.FLAG, min_score=None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_moderation_thresholds.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cyo_adventure.moderation.thresholds'`

- [ ] **Step 3: Implement the module**

```python
"""Age-band moderation surfacing thresholds (WS-A).

The moderation pipeline records every finding. This module decides which
recorded findings SURFACE on guardian- and kid-facing responses, per
(age_band, category). Admin surfaces never filter.

Policy resolution: an exact (age_band, category) row wins; otherwise the code
default applies. The DB table is a sparse override set, not a full matrix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cyo_adventure.moderation.report import Verdict

if TYPE_CHECKING:
    from collections.abc import Mapping

# Severity ordering for surfacing decisions. PASS is deliberately absent: a
# pass finding never surfaces regardless of thresholds.
_SEVERITY: dict[Verdict, int] = {
    Verdict.ADVISORY: 1,
    Verdict.FLAG: 2,
    Verdict.BLOCK: 3,
}

# Known category values across pipeline stages, for the admin editor's
# suggestion list ONLY. Categories are open-ended strings (Stage-0 classifier
# payload keys are provider-defined), so this list is advisory, never a gate.
KNOWN_CATEGORIES: tuple[str, ...] = (
    "coherence",
    "engagement",
    "harassment/threatening",
    "hate/threatening",
    "identity_attack",
    "illicit/violent",
    "insult",
    "invalid_story",
    "personal_information",
    "profanity",
    "reading_level",
    "reviewer_independence",
    "safety",
    "self-harm/instructions",
    "self-harm/intent",
    "severe_toxicity",
    "sexual",
    "sexual/minors",
    "sexually_explicit",
    "threat",
    "toxicity",
)


@dataclass(frozen=True, slots=True)
class Threshold:
    """Minimum verdict (and optional score floor) at which a finding surfaces."""

    min_verdict: Verdict
    min_score: float | None


DEFAULT_THRESHOLD = Threshold(min_verdict=Verdict.FLAG, min_score=None)


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    """Resolved surfacing policy: sparse override rows over a code default."""

    rows: Mapping[tuple[str, str], Threshold]
    default: Threshold = field(default=DEFAULT_THRESHOLD)

    def resolve(self, age_band: str, category: str) -> Threshold:
        """Return the threshold for a band and category (row or default)."""
        return self.rows.get((age_band, category), self.default)

    def surfaces(
        self,
        *,
        age_band: str,
        category: str,
        verdict: Verdict | str,
        score: float | None,
    ) -> bool:
        """Return whether a recorded finding surfaces on a filtered response.

        Args:
            age_band: The story's (or requesting child's) age band; an empty
                string resolves to the code default.
            category: The finding's category string.
            verdict: The finding's verdict; serialized strings are coerced.
            score: The finding's classifier score, if any.

        Returns:
            bool: True when the finding meets the resolved threshold.
        """
        # #ASSUME: data-integrity: verdicts arrive from unconstrained JSONB, so
        # an out-of-enum string must degrade to "hidden", never raise.
        # #VERIFY: test_unknown_string_verdict_does_not_surface.
        if not isinstance(verdict, Verdict):
            try:
                verdict = Verdict(verdict)
            except ValueError:
                return False
        severity = _SEVERITY.get(verdict)
        if severity is None:  # Verdict.PASS
            return False
        threshold = self.resolve(age_band, category)
        if severity < _SEVERITY[threshold.min_verdict]:
            return False
        if (
            threshold.min_score is not None
            and score is not None
            and score < threshold.min_score
        ):
            return False
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_moderation_thresholds.py -v`
Expected: 8 passed

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff format src/cyo_adventure/moderation/thresholds.py tests/unit/test_moderation_thresholds.py
uv run ruff check src/cyo_adventure/moderation/thresholds.py tests/unit/test_moderation_thresholds.py
uv run basedpyright src/
git add src/cyo_adventure/moderation/thresholds.py tests/unit/test_moderation_thresholds.py
git commit -S -m "feat(moderation): add age-band threshold policy for finding surfacing"
```

---

### Task 2: DB models, migration, round-trip test

`depends-on: Task0 [completion]` (independent of Task 1's output; parallelizable with it)

**Files:**

- Modify: `src/cyo_adventure/db/models.py` (append after `StoryRequest`, around line 403)
- Create: `migrations/versions/20260706_1600_add_moderation_threshold.py`
- Test: `tests/integration/test_moderation_threshold_migration.py`

- [ ] **Step 1: Add the ORM models**

Append to `src/cyo_adventure/db/models.py`, matching the file's existing `Mapped[]` +
`CheckConstraint` style (see `StoryRequest`, lines 338-403). Reuse the module's existing
`_FK_USER` and `_TS` constants.

```python
_MIN_VERDICT_VALUES = "'advisory', 'flag', 'block'"


class ModerationThreshold(Base):
    """Sparse per-(age_band, category) override of the surfacing default.

    Absence of a row means the code default applies
    (``moderation/thresholds.py::DEFAULT_THRESHOLD``). The table is small
    (admin-curated), so policy loads read it whole.
    """

    __tablename__ = "moderation_threshold"
    __table_args__ = (
        CheckConstraint(
            f"min_verdict IN ({_MIN_VERDICT_VALUES})",
            name="ck_moderation_threshold_min_verdict",
        ),
        CheckConstraint(
            "min_score IS NULL OR (min_score >= 0.0 AND min_score <= 1.0)",
            name="ck_moderation_threshold_min_score",
        ),
        UniqueConstraint(
            "age_band", "category", name="uq_moderation_threshold_band_category"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    age_band: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    min_verdict: Mapped[str] = mapped_column(String(16))
    min_score: Mapped[float | None] = mapped_column(default=None)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


class ModerationThresholdAudit(Base):
    """Append-only audit of threshold edits (who changed what, when).

    Deliberately minimal: WS-D's pipeline_event log will subsume this role;
    keep this table write-only until then.
    """

    __tablename__ = "moderation_threshold_audit"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    age_band: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # 'upsert' | 'delete'
    old_min_verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    new_min_verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    old_min_score: Mapped[float | None] = mapped_column(default=None)
    new_min_score: Mapped[float | None] = mapped_column(default=None)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_USER))
    changed_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
```

If `UniqueConstraint` is not already imported in models.py, add it to the existing
`sqlalchemy` import line.

- [ ] **Step 2: Write the migration**

Create `migrations/versions/20260706_1600_add_moderation_threshold.py`. The style template is
`migrations/versions/20260704_1300_add_story_request.py` (create_table with inline constraints).

```python
"""add moderation_threshold and moderation_threshold_audit tables (WS-A)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-06 16:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the threshold override table and its append-only audit table."""
    op.create_table(
        "moderation_threshold",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("age_band", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("min_verdict", sa.String(length=16), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "min_verdict IN ('advisory', 'flag', 'block')",
            name="ck_moderation_threshold_min_verdict",
        ),
        sa.CheckConstraint(
            "min_score IS NULL OR (min_score >= 0.0 AND min_score <= 1.0)",
            name="ck_moderation_threshold_min_score",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "age_band", "category", name="uq_moderation_threshold_band_category"
        ),
    )
    op.create_table(
        "moderation_threshold_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("age_band", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("old_min_verdict", sa.String(length=16), nullable=True),
        sa.Column("new_min_verdict", sa.String(length=16), nullable=True),
        sa.Column("old_min_score", sa.Float(), nullable=True),
        sa.Column("new_min_score", sa.Float(), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "changed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop both WS-A threshold tables."""
    op.drop_table("moderation_threshold_audit")
    op.drop_table("moderation_threshold")
```

IMPORTANT: before writing, confirm the user table's real name for the FK target:
Run: `grep -n "__tablename__" src/cyo_adventure/db/models.py | head -8`
If the user table is not `app_user`, use the actual name in both `ForeignKeyConstraint` lines
(match what `_FK_USER` points at).

- [ ] **Step 3: Write the migration round-trip test**

Create `tests/integration/test_moderation_threshold_migration.py`, copying the structure of
`tests/integration/test_storybook_version_provider_migration.py` verbatim, with these
substitutions: module docstring `"""Migration round-trip for the WS-A moderation threshold
tables."""`, `_PREV_HEAD = "a7b8c9d0e1f2"`, `_THRESHOLD_HEAD = "b8c9d0e1f2a3"`, glob pattern
`*add_moderation_threshold*.py`, and the column-presence probe replaced with a table-presence
probe:

```python
sa.text(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_name = 'moderation_threshold'"
)
```

asserting the table exists after upgrade to `_THRESHOLD_HEAD` and is gone after downgrade to
`_PREV_HEAD` (same for `moderation_threshold_audit`). Keep the pinned-revision comment; it is the
lesson this pattern encodes.

- [ ] **Step 4: Run the migration tests**

Run: `uv run pytest tests/integration/test_moderation_threshold_migration.py -v`
Expected: 3 passed (skips are acceptable only if Docker is unavailable; do not proceed on skips,
fix Docker instead).

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff format src/cyo_adventure/db/models.py migrations/versions/20260706_1600_add_moderation_threshold.py tests/integration/test_moderation_threshold_migration.py
uv run ruff check src/cyo_adventure/db/models.py migrations/versions/20260706_1600_add_moderation_threshold.py tests/integration/test_moderation_threshold_migration.py
uv run basedpyright src/
git add src/cyo_adventure/db/models.py migrations/versions/20260706_1600_add_moderation_threshold.py tests/integration/test_moderation_threshold_migration.py
git commit -S -m "feat(db): add moderation_threshold and audit tables with migration"
```

---

### Task 3: Async policy loader

`depends-on: Task1 [output]`, `depends-on: Task2 [output]`

**Files:**

- Modify: `src/cyo_adventure/moderation/thresholds.py` (append)
- Test: `tests/integration/test_threshold_policy_loader.py`

- [ ] **Step 1: Write the failing integration test**

```python
"""Loader test: DB rows become a ThresholdPolicy; empty table means defaults."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cyo_adventure.db.models import ModerationThreshold
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import (
    DEFAULT_THRESHOLD,
    Threshold,
    load_threshold_policy,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_empty_table_yields_default_only_policy(engine: AsyncEngine) -> None:
    """No rows: every lookup resolves to the code default."""
    async with AsyncSession(engine) as session:
        policy = await load_threshold_policy(session)
    assert policy.resolve("3-5", "toxicity") == DEFAULT_THRESHOLD


async def test_rows_load_into_policy(engine: AsyncEngine) -> None:
    """A stored override row resolves for its exact (band, category) key."""
    async with AsyncSession(engine) as session:
        session.add(
            ModerationThreshold(
                age_band="3-5",
                category="violence",
                min_verdict="advisory",
                min_score=0.3,
            )
        )
        await session.commit()
    async with AsyncSession(engine) as session:
        policy = await load_threshold_policy(session)
    assert policy.resolve("3-5", "violence") == Threshold(
        min_verdict=Verdict.ADVISORY, min_score=0.3
    )
    assert policy.resolve("5-8", "violence") == DEFAULT_THRESHOLD
```

Note: the `engine` fixture comes from `tests/integration/conftest.py` and creates a fresh schema
per test via `Base.metadata.create_all`, so the Task 2 models are already present.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_threshold_policy_loader.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_threshold_policy'`

- [ ] **Step 3: Implement the loader**

Append to `src/cyo_adventure/moderation/thresholds.py`:

```python
async def load_threshold_policy(session: "AsyncSession") -> ThresholdPolicy:
    """Load all threshold override rows into an immutable policy.

    The table is admin-curated and small; a whole-table read per filtered
    request is deliberate (no cache invalidation machinery).

    Args:
        session: The request-scoped async session.

    Returns:
        ThresholdPolicy: Override rows over the code default.
    """
    # #ASSUME: external-resources: one small SELECT per filtered request; if
    # this table ever grows past a few hundred rows, add request-scope caching.
    # #VERIFY: tests/integration/test_threshold_policy_loader.py.
    from sqlalchemy import select

    from cyo_adventure.db.models import ModerationThreshold

    rows: dict[tuple[str, str], Threshold] = {}
    for row in await session.scalars(select(ModerationThreshold)):
        try:
            verdict = Verdict(row.min_verdict)
        except ValueError:
            continue  # CHECK constraint should prevent this; skip defensively.
        rows[(row.age_band, row.category)] = Threshold(
            min_verdict=verdict, min_score=row.min_score
        )
    return ThresholdPolicy(rows=rows)
```

Add `from sqlalchemy.ext.asyncio import AsyncSession` under `if TYPE_CHECKING:` at the top of the
module (keep the runtime imports inside the function to avoid a hard db dependency for the pure
logic unit tests).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/integration/test_threshold_policy_loader.py tests/unit/test_moderation_thresholds.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/cyo_adventure/moderation/thresholds.py tests/integration/test_threshold_policy_loader.py
uv run ruff check src/cyo_adventure/moderation/thresholds.py tests/integration/test_threshold_policy_loader.py
uv run basedpyright src/
git add src/cyo_adventure/moderation/thresholds.py tests/integration/test_threshold_policy_loader.py
git commit -S -m "feat(moderation): load threshold policy from db rows"
```

---

### Task 4: Filter guardian storybook surfaces (content summary + books list)

`depends-on: Task3 [output]`

**Files:**

- Modify: `src/cyo_adventure/api/review_surface.py` (`build_content_summary`, lines 284-340)
- Modify: `src/cyo_adventure/api/assignments.py` (`get_content_summary` line 154-182,
  `_guardian_book_item` line 289 onward, and the books-list handler that calls it)
- Test: `tests/integration/test_content_summary_thresholds.py`

- [ ] **Step 1: Write the failing integration test**

Reuse the seeding pattern from `tests/integration/test_assignments_api.py::_seed_published_with_report`
(line 320): fresh Family + users via the `sessions: async_sessionmaker[AsyncSession]` fixture,
tokens are the `authn_subject` strings passed to `auth()`. Do NOT invent a parallel seeding path.
Note the existing helper's blob has NO `metadata.age_band`; this test seeds its own story WITH one
so the override row in the third test has a band to target.

```python
"""Threshold filtering on guardian content summary and books list."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cyo_adventure.db.models import (
    Family,
    ModerationThreshold,
    Storybook,
    StorybookVersion,
    User,
)
from tests.integration.conftest import auth

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A report with one advisory (below default threshold) and one flag (at it).
_MIXED_REPORT: dict[str, object] = {
    "findings": [
        {
            "stage": 0,
            "source": "openai",
            "category": "toxicity",
            "node_id": None,
            "verdict": "advisory",
            "score": 0.02,
            "message": "graded classifier advisory",
        },
        {
            "stage": 1,
            "source": "llm_safety",
            "category": "safety",
            "node_id": None,
            "verdict": "flag",
            "score": None,
            "message": "mild peril",
        },
    ],
    "summary": {
        "count": 2,
        "hard_block": False,
        "soft_flag": True,
        "repaired": False,
        "reviewer_independent": True,
    },
}


async def _seed_banded_published(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed a family and a published 8-11 story carrying _MIXED_REPORT."""
    async with sessions() as session:
        fam = Family(name="T")
        session.add(fam)
        await session.flush()
        admin = User(family_id=fam.id, role="admin", authn_subject="admin-t")
        session.add_all(
            [
                admin,
                User(family_id=fam.id, role="guardian", authn_subject="guardian-t"),
            ]
        )
        await session.flush()
        story_id = "threshold-me"
        session.add(
            Storybook(
                id=story_id,
                family_id=fam.id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={
                    "id": story_id,
                    "metadata": {"age_band": "8-11"},
                    "nodes": [{"id": "n1", "body": "Prose."}],
                },
                moderation_report=_MIXED_REPORT,
                approved_by=admin.id,
                published_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return story_id


async def test_guardian_summary_hides_below_threshold_advisory(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Guardian sees the flag finding but not the 0.02 advisory."""
    story_id = await _seed_banded_published(sessions)
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/content-summary",
        headers=auth("guardian-t"),
    )
    assert res.status_code == 200
    body = res.json()
    categories = [f["category"] for f in body["findings"]]
    assert "safety" in categories
    assert "toxicity" not in categories
    assert body["flagged_count"] == 1


async def test_admin_review_surface_still_shows_everything(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The admin review surface is NOT filtered: both findings appear."""
    story_id = await _seed_banded_published(sessions)
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/review",
        headers=auth("admin-t"),
    )
    assert res.status_code == 200
    body = res.json()
    categories = [f["category"] for f in body["story_level_findings"]]
    assert "toxicity" in categories
    assert "safety" in categories


async def test_threshold_row_lowers_floor_for_matching_band(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An override row ('8-11', 'toxicity') -> advisory surfaces the advisory."""
    story_id = await _seed_banded_published(sessions)
    async with sessions() as session:
        session.add(
            ModerationThreshold(
                age_band="8-11",
                category="toxicity",
                min_verdict="advisory",
                min_score=None,
            )
        )
        await session.commit()
    res = await client.get(
        f"/api/v1/storybooks/{story_id}/content-summary",
        headers=auth("guardian-t"),
    )
    body = res.json()
    assert "toxicity" in [f["category"] for f in body["findings"]]
    assert body["flagged_count"] == 2
```

Check the `sessions` fixture name in `tests/integration/conftest.py` first (test_assignments_api
imports it; mirror exactly). If `Family`/`User` constructor signatures differ, copy them verbatim
from `_seed_published_with_report`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_content_summary_thresholds.py -v`
Expected: FAIL on the first test (advisory currently present, flagged_count == 2)

- [ ] **Step 3: Thread the policy through build_content_summary**

In `src/cyo_adventure/api/review_surface.py`, change the signature and filtering of
`build_content_summary` (keep `build_review_surface` untouched; it serves the unfiltered admin
surface):

```python
def build_content_summary(
    *,
    storybook_id: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
    age_band: str,
    policy: ThresholdPolicy,
) -> ContentSummaryView:
```

and replace the `flagged_count` / `findings` computation with:

```python
    surface = build_review_surface(
        status="published",
        storybook_id=storybook_id,
        version=version,
        blob=blob,
        moderation_report=moderation_report,
    )

    def _surfaces(
        category: str, verdict: Verdict | str, score: float | None
    ) -> bool:
        return policy.surfaces(
            age_band=age_band, category=category, verdict=verdict, score=score
        )

    # #CRITICAL: security: guardian/kid surfaces filter by threshold; the admin
    # review surface (build_review_surface) never does. flagged_count MUST count
    # only surfaced findings or the badge contradicts the visible list.
    # #VERIFY: test_guardian_summary_hides_below_threshold_advisory.
    flagged_count = sum(
        1
        for passage in surface.flagged_passages
        for finding in passage.findings
        if _surfaces(finding.category, finding.verdict, finding.score)
    ) + sum(
        1
        for finding in surface.story_level_findings
        if _surfaces(finding.category, finding.verdict, finding.score)
    )
    findings = [
        GuardianFinding(
            category=finding.category,
            verdict=finding.verdict,
            message=finding.message,
        )
        for finding in surface.story_level_findings
        if _surfaces(finding.category, finding.verdict, finding.score)
    ]
```

Add the imports at the top:
`from cyo_adventure.moderation.report import Verdict` and
`from cyo_adventure.moderation.thresholds import ThresholdPolicy`.
Check the actual attribute names and types on the surface's finding views first
(`grep -n "class FindingView" -A 10 src/cyo_adventure/api/schemas.py`); if `FindingView` lacks a
`score` attribute, pass `None` for score, and if its `verdict` field is typed as something other
than `Verdict` or `str`, adjust `_surfaces`'s parameter type to match. Never suppress the type
checker here (repo rule: no type-ignore without a ticket).

- [ ] **Step 4: Update the two call sites in assignments.py**

In `get_content_summary` (line 176-182):

```python
    version_row, version = await _authorize_content_summary(ctx, storybook_id)
    policy = await load_threshold_policy(ctx.session)
    return build_content_summary(
        storybook_id=storybook_id,
        version=version,
        blob=version_row.blob,
        moderation_report=version_row.moderation_report,
        age_band=_book_age_band(version_row.blob),
        policy=policy,
    )
```

In the guardian books-list handler: load the policy ONCE before the per-book loop
(`policy = await load_threshold_policy(ctx.session)`) and pass `age_band=_book_age_band(...)` and
`policy=policy` through `_guardian_book_item` into its `build_content_summary` call (add both as
parameters to `_guardian_book_item`). Import `load_threshold_policy` from
`cyo_adventure.moderation.thresholds`.

- [ ] **Step 5: Run the new tests plus the touched suites**

Run: `uv run pytest tests/integration/test_content_summary_thresholds.py -v`
Expected: 3 passed
Run: `uv run pytest tests/integration -k "content_summary or assignments or books" -v`
Expected: KNOWN casualties whose expectations must be updated (verified against origin/main
during planning):

- `tests/integration/test_assignments_api.py::test_guardian_sees_content_summary`: its seeded
  report (`_report_with_flags`, line 287) holds one per-node "violence" flag plus one
  story-level "coherence" advisory. Under the new default the assertions become
  `flagged_count == 1` and `findings == []` (the advisory no longer surfaces).
- `tests/integration/test_guardian_books_api.py`: seeds moderation reports around lines 154 and
  213; recheck any flagged_count expectations the same way.

Update ONLY filter-explainable expectations. If a failure is not explainable by the new filter,
STOP and debug; do not adjust unrelated expectations.

- [ ] **Step 6: Commit**

```bash
uv run ruff format src/cyo_adventure/api/review_surface.py src/cyo_adventure/api/assignments.py tests/integration/test_content_summary_thresholds.py
uv run ruff check src/cyo_adventure/api/review_surface.py src/cyo_adventure/api/assignments.py tests/integration/test_content_summary_thresholds.py
uv run basedpyright src/
git add src/cyo_adventure/api/review_surface.py src/cyo_adventure/api/assignments.py tests/integration/test_content_summary_thresholds.py <any updated existing test files>
git commit -S -m "feat(api): filter guardian content summary and books badges by age-band threshold"
```

---

### Task 5: Filter story-request flags; lock kid surfaces flag-free

`depends-on: Task3 [output]` (parallel with Task 4)

**Files:**

- Modify: `src/cyo_adventure/api/story_requests.py` (`_to_view` lines 95-150 and the list handler
  around lines 213-250)
- Test: `tests/integration/test_story_request_flag_thresholds.py`

- [ ] **Step 1: Write the failing integration test**

Seed rows directly with the `sessions: async_sessionmaker[AsyncSession]` fixture (same
conftest as Task 4) against the `seed` fixture's family and child profile, so the guardian token
`seed.guardian_token` can list them:

```python
"""Threshold filtering on guardian story-request flag projections."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cyo_adventure.db.models import StoryRequest
from tests.integration.conftest import Seed, auth

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_request(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    *,
    status: str,
    flags: dict[str, object],
) -> str:
    """Insert a story-request row with pre-set moderation flags; return its id."""
    async with sessions() as session:
        row = StoryRequest(
            family_id=seed.family_id,
            profile_id=seed.child_profile_id,
            request_text="a story about a brave turtle",
            status=status,
            moderation_flags=flags,
        )
        session.add(row)
        await session.commit()
        return str(row.id)


async def test_guardian_request_list_hides_advisory_flags(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The 0.01-floor classifier advisories no longer reach the guardian list."""
    request_id = await _seed_request(
        sessions,
        seed,
        status="pending",
        flags={
            "blocked": False,
            "flags": [
                {
                    "category": "toxicity",
                    "verdict": "advisory",
                    "message": "graded advisory",
                },
                {"category": "safety", "verdict": "flag", "message": "needs review"},
            ],
        },
    )
    res = await client.get(
        "/api/v1/story-requests", headers=auth(seed.guardian_token)
    )
    assert res.status_code == 200
    target = next(r for r in res.json()["requests"] if r["id"] == request_id)
    categories = [f["category"] for f in target["moderation_flags"]]
    assert categories == ["safety"]


async def test_blocked_request_flags_still_surface(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Bright-line BLOCK flags always surface (block >= flag >= default)."""
    request_id = await _seed_request(
        sessions,
        seed,
        status="blocked",
        flags={
            "blocked": True,
            "flags": [
                {
                    "category": "personal_information",
                    "verdict": "block",
                    "message": "names a real child",
                }
            ],
        },
    )
    res = await client.get(
        "/api/v1/story-requests", headers=auth(seed.guardian_token)
    )
    target = next(r for r in res.json()["requests"] if r["id"] == request_id)
    assert target["request_text"] is None  # existing hiding rule unchanged
    assert [f["verdict"] for f in target["moderation_flags"]] == ["block"]
```

Check the `StoryRequest` constructor kwargs against an existing direct construction first
(`grep -rn "StoryRequest(" tests/ src/cyo_adventure/story_requests/service.py | head`); if the
model requires additional fields, copy the construction from the closest existing usage.

Also add the kid-surface contract test in the same file:

```python
async def test_kid_library_exposes_no_moderation_fields(
    client: AsyncClient, seed: Seed
) -> None:
    """Kid-facing library payloads carry no findings/flags/moderation keys."""
    res = await client.get("/api/v1/library", headers=auth(seed.child_token))
    assert res.status_code == 200
    text = res.text.lower()
    for needle in ("moderation", "finding", "verdict", "flagged"):
        assert needle not in text, f"kid library leaked moderation field: {needle}"
```

Confirm the kid library route path first with
`grep -n "router.get" src/cyo_adventure/api/library.py`; adjust the URL if it differs.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_story_request_flag_thresholds.py -v`
Expected: the advisory-hiding test FAILS (both categories currently returned); the other two may
already pass (that is fine; they lock behavior).

- [ ] **Step 3: Join the profile band and filter in _to_view**

In the list handler, change the query to also fetch the profile's band. The current handler
selects `StoryRequest` rows only; replace with:

```python
    rows = (
        await ctx.session.execute(
            select(StoryRequest, ChildProfile.age_band)
            .join(ChildProfile, StoryRequest.profile_id == ChildProfile.id)
            .where(...)  # keep the existing family/status where-clauses verbatim
            .order_by(...)  # keep the existing ordering verbatim
        )
    ).all()
    policy = await load_threshold_policy(ctx.session)
    requests = [
        _to_view(request, age_band=age_band, policy=policy)
        for request, age_band in rows
    ]
```

(Import `ChildProfile` from `cyo_adventure.db.models` and `load_threshold_policy` /
`ThresholdPolicy` from `cyo_adventure.moderation.thresholds`.)

Change `_to_view(request: StoryRequest)` to
`_to_view(request: StoryRequest, *, age_band: str, policy: ThresholdPolicy)` and, inside the flag
loop, after the existing `parsed_verdict = Verdict(verdict)` succeeds, add:

```python
            # Stored request flags carry no score; verdict-level filtering only.
            if not policy.surfaces(
                age_band=age_band,
                category=category,
                verdict=parsed_verdict,
                score=None,
            ):
                continue
```

Keep the existing malformed-verdict skip-and-log behavior exactly as is. Fix any other `_to_view`
callers the type checker finds (grep `_to_view(` in the file).

- [ ] **Step 4: Run to verify pass, plus the request suite**

Run: `uv run pytest tests/integration/test_story_request_flag_thresholds.py tests/integration/test_story_requests_api.py -v`
Expected: new tests pass; any pre-existing test asserting advisory flags visible needs its
expectation updated (same rule as Task 4 Step 5: only filter-explainable updates).

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/cyo_adventure/api/story_requests.py tests/integration/test_story_request_flag_thresholds.py
uv run ruff check src/cyo_adventure/api/story_requests.py tests/integration/test_story_request_flag_thresholds.py
uv run basedpyright src/
git add src/cyo_adventure/api/story_requests.py tests/integration/test_story_request_flag_thresholds.py <any updated existing test files>
git commit -S -m "feat(api): filter story-request moderation flags by age-band threshold"
```

---

### Task 6: Admin threshold CRUD router with audit

`depends-on: Task3 [output]`

**Files:**

- Modify: `src/cyo_adventure/api/schemas.py` (append views/bodies)
- Create: `src/cyo_adventure/api/moderation_thresholds.py`
- Modify: `src/cyo_adventure/app.py` (register router, after line 175's approval router)
- Test: `tests/integration/test_moderation_thresholds_api.py`

- [ ] **Step 1: Write the failing integration tests**

```python
"""Admin CRUD for moderation thresholds: auth, upsert, delete, audit."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cyo_adventure.db.models import ModerationThreshold, ModerationThresholdAudit
from tests.integration.conftest import Seed, auth

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_URL = "/api/v1/admin/moderation-thresholds"


async def test_guardian_gets_403(client: AsyncClient, seed: Seed) -> None:
    """Non-admin callers are rejected before any read."""
    res = await client.get(_URL, headers=auth(seed.guardian_token))
    assert res.status_code == 403


async def test_list_returns_defaults_and_rows(
    client: AsyncClient, seed: Seed
) -> None:
    """The list view exposes the code default and known categories."""
    res = await client.get(_URL, headers=auth(seed.admin_token))
    assert res.status_code == 200
    body = res.json()
    assert body["default_min_verdict"] == "flag"
    assert body["default_min_score"] is None
    assert "toxicity" in body["known_categories"]
    assert body["rows"] == []


async def test_upsert_creates_then_updates_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """PUT creates a row, a second PUT updates it, both write audit rows."""
    res = await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "advisory", "min_score": 0.3},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    res = await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "advisory", "min_score": 0.5},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    listed = await client.get(_URL, headers=auth(seed.admin_token))
    rows = listed.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["min_score"] == 0.5
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert [a.action for a in audits] == ["upsert", "upsert"]
    assert audits[1].old_min_score == 0.3
    assert audits[1].new_min_score == 0.5


async def test_delete_removes_row_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """DELETE removes the override (falling back to default) and audits it."""
    await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    res = await client.delete(
        f"{_URL}/3-5/violence", headers=auth(seed.admin_token)
    )
    assert res.status_code == 200
    assert (
        await client.get(_URL, headers=auth(seed.admin_token))
    ).json()["rows"] == []
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert audits[-1].action == "delete"


async def test_delete_missing_row_404(client: AsyncClient, seed: Seed) -> None:
    """Deleting a non-existent override is a 404, not a silent no-op."""
    res = await client.delete(
        f"{_URL}/3-5/never-set", headers=auth(seed.admin_token)
    )
    assert res.status_code == 404


async def test_invalid_band_and_verdict_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """Unknown age band -> 422; 'pass'/'block-typo' min_verdict -> 422."""
    res = await client.put(
        f"{_URL}/4-6/violence",
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
    res = await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "pass", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
```

Note: if the conftest's exception handling maps `ValidationError` to a different status than 422,
match the codebase's actual mapping (check `core/exceptions.py` handlers) and adjust asserts.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_moderation_thresholds_api.py -v`
Expected: FAIL with 404s (router not registered)

- [ ] **Step 3: Add schemas**

Append to `src/cyo_adventure/api/schemas.py` (match the file's BaseModel style):

```python
# The surfacing floor domain; PASS is deliberately excluded (never surfaces).
MinVerdict = Literal["advisory", "flag", "block"]


class ThresholdView(BaseModel):
    """One stored (age_band, category) surfacing override."""

    age_band: str
    category: str
    min_verdict: MinVerdict
    min_score: float | None


class ThresholdListView(BaseModel):
    """All overrides plus the code default and the category suggestion list."""

    default_min_verdict: MinVerdict
    default_min_score: float | None
    known_categories: list[str]
    rows: list[ThresholdView]


class ThresholdUpsertBody(BaseModel):
    """PUT body for a threshold override."""

    min_verdict: MinVerdict
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
```

- [ ] **Step 4: Implement the router**

First check the existing router declaration style:
Run: `grep -n "APIRouter(" src/cyo_adventure/api/approval.py src/cyo_adventure/api/assignments.py`
and copy that exact prefix/tags pattern. Then create
`src/cyo_adventure/api/moderation_thresholds.py`:

```python
"""Admin CRUD for age-band moderation surfacing thresholds (WS-A)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    MinVerdict,
    ThresholdListView,
    ThresholdUpsertBody,
    ThresholdView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import ModerationThreshold, ModerationThresholdAudit
from cyo_adventure.moderation.thresholds import DEFAULT_THRESHOLD, KNOWN_CATEGORIES
from cyo_adventure.storybook.models import AgeBand

router = APIRouter(prefix="/api/v1", tags=["moderation-thresholds"])
# ^ adjust prefix/tags to the grep result above if the codebase differs.

_VALID_BANDS = frozenset(band.value for band in AgeBand)


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write."""
    # #CRITICAL: security: threshold edits change what EVERY family's guardians
    # see; the role gate runs before any query so non-admins learn nothing.
    # #VERIFY: test_guardian_gets_403.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


def _validate_band(age_band: str) -> None:
    if age_band not in _VALID_BANDS:
        msg = f"unknown age band '{age_band}'"
        raise ValidationError(msg, field="age_band", value=age_band)


@router.get("/admin/moderation-thresholds")
async def list_thresholds(ctx: Context) -> ThresholdListView:
    """List all overrides plus the code default (admin only)."""
    _require_admin(ctx)
    rows = (
        await ctx.session.scalars(
            select(ModerationThreshold).order_by(
                ModerationThreshold.age_band, ModerationThreshold.category
            )
        )
    ).all()
    return ThresholdListView(
        default_min_verdict=cast("MinVerdict", DEFAULT_THRESHOLD.min_verdict.value),
        default_min_score=DEFAULT_THRESHOLD.min_score,
        known_categories=list(KNOWN_CATEGORIES),
        rows=[
            ThresholdView(
                age_band=row.age_band,
                category=row.category,
                # DB CHECK constraint guarantees the enum domain; cast, don't
                # suppress (repo rule: no type-ignore without a ticket).
                min_verdict=cast("MinVerdict", row.min_verdict),
                min_score=row.min_score,
            )
            for row in rows
        ],
    )


async def _get_row(
    ctx: Context, age_band: str, category: str
) -> ModerationThreshold | None:
    return await ctx.session.scalar(
        select(ModerationThreshold).where(
            ModerationThreshold.age_band == age_band,
            ModerationThreshold.category == category,
        )
    )


@router.put("/admin/moderation-thresholds/{age_band}/{category}")
async def upsert_threshold(
    age_band: str, category: str, body: ThresholdUpsertBody, ctx: Context
) -> ThresholdView:
    """Create or update one override; write an audit row (admin only)."""
    _require_admin(ctx)
    _validate_band(age_band)
    row = await _get_row(ctx, age_band, category)
    old_verdict = row.min_verdict if row else None
    old_score = row.min_score if row else None
    if row is None:
        row = ModerationThreshold(
            age_band=age_band,
            category=category,
            min_verdict=body.min_verdict,
            min_score=body.min_score,
            updated_by=ctx.principal.user_id,
        )
        ctx.session.add(row)
    else:
        row.min_verdict = body.min_verdict
        row.min_score = body.min_score
        row.updated_by = ctx.principal.user_id
    ctx.session.add(
        ModerationThresholdAudit(
            age_band=age_band,
            category=category,
            action="upsert",
            old_min_verdict=old_verdict,
            new_min_verdict=body.min_verdict,
            old_min_score=old_score,
            new_min_score=body.min_score,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.flush()
    return ThresholdView(
        age_band=age_band,
        category=category,
        min_verdict=body.min_verdict,
        min_score=body.min_score,
    )


@router.delete("/admin/moderation-thresholds/{age_band}/{category}")
async def delete_threshold(
    age_band: str, category: str, ctx: Context
) -> ThresholdListView:
    """Remove one override (reverting to the default); audit it (admin only)."""
    _require_admin(ctx)
    _validate_band(age_band)
    row = await _get_row(ctx, age_band, category)
    if row is None:
        msg = f"no threshold override for ({age_band}, {category})"
        raise ResourceNotFoundError(msg)
    ctx.session.add(
        ModerationThresholdAudit(
            age_band=age_band,
            category=category,
            action="delete",
            old_min_verdict=row.min_verdict,
            new_min_verdict=None,
            old_min_score=row.min_score,
            new_min_score=None,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.delete(row)
    await ctx.session.flush()
    return await list_thresholds(ctx)
```

Verify `Context`'s import path and the `ValidationError(msg, field=..., value=...)` signature
against `core/exceptions.py` before committing (grep both; match reality over this sketch).

- [ ] **Step 5: Register the router**

In `src/cyo_adventure/app.py`, add to the imports the other routers use and after line 175
(`app.include_router(approval.router)`):

```python
    app.include_router(moderation_thresholds.router)
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/integration/test_moderation_thresholds_api.py -v`
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
uv run ruff format src/cyo_adventure/api/moderation_thresholds.py src/cyo_adventure/api/schemas.py src/cyo_adventure/app.py tests/integration/test_moderation_thresholds_api.py
uv run ruff check src/cyo_adventure/api/moderation_thresholds.py src/cyo_adventure/api/schemas.py src/cyo_adventure/app.py tests/integration/test_moderation_thresholds_api.py
uv run basedpyright src/
git add src/cyo_adventure/api/moderation_thresholds.py src/cyo_adventure/api/schemas.py src/cyo_adventure/app.py tests/integration/test_moderation_thresholds_api.py
git commit -S -m "feat(api): admin moderation-threshold CRUD with audit trail"
```

---

### Task 7: Regenerate the OpenAPI client; admin editor page

`depends-on: Task6 [output]`

**Files:**

- Regenerate: `frontend/src/client/` (build output; never hand-edit)
- Create: `frontend/src/guardian/ModerationThresholdsPage.tsx`
- Modify: `frontend/src/router.tsx` (admin-only route)
- Test: `frontend/src/guardian/ModerationThresholdsPage.test.tsx`

- [ ] **Step 1: Regenerate the client (REQUIRED; CI has an OpenAPI drift gate)**

Run:

```bash
uv run uvicorn cyo_adventure.app:create_app --factory --port 8000 &
sleep 3
cd frontend && npm install && npm run generate-client
kill %1
```

Expected: `frontend/src/client/types.gen.ts` gains `ThresholdListView`, `ThresholdView`,
`ThresholdUpsertBody`; `sdk.gen.ts` gains three functions (names follow the pattern
`listThresholdsApiV1AdminModerationThresholdsGet` etc.).
Abort if: generation fails or the new types are absent. Confirm the backend factory invocation
matches how the dev server is normally started (check `README.md` or `docker-compose.yml` for the
canonical uvicorn target) before assuming the app factory path above.
Then: `grep -n "ModerationThresholds" frontend/src/client/sdk.gen.ts` and record the exact three
generated function names for Step 2.

- [ ] **Step 2: Write the page**

Before writing, read `frontend/src/guardian/ReviewDetailPage.tsx` and copy its data-fetching
pattern (client call + loading/error state idiom) rather than the sketch below if they differ.
Create `frontend/src/guardian/ModerationThresholdsPage.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react';
// Import the three generated functions recorded in Step 1; the names below are
// the expected pattern; use the actual generated identifiers.
import {
  deleteThresholdApiV1AdminModerationThresholdsAgeBandCategoryDelete as deleteThreshold,
  listThresholdsApiV1AdminModerationThresholdsGet as listThresholds,
  upsertThresholdApiV1AdminModerationThresholdsAgeBandCategoryPut as upsertThreshold,
} from '../client/sdk.gen';
import type { ThresholdListView } from '../client/types.gen';

const AGE_BANDS = ['3-5', '5-8', '8-11', '10-13', '13-16', '16+'] as const;
const VERDICTS = ['advisory', 'flag', 'block'] as const;

export default function ModerationThresholdsPage() {
  const [data, setData] = useState<ThresholdListView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [band, setBand] = useState<string>('3-5');
  const [category, setCategory] = useState('');
  const [verdict, setVerdict] = useState<string>('advisory');
  const [score, setScore] = useState<string>('');

  const refresh = useCallback(() => {
    listThresholds()
      .then((res) => setData(res.data ?? null))
      .catch(() => setError('Could not load thresholds.'));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error) return <p role="alert">{error}</p>;
  if (!data) return <p>Loading…</p>;

  const save = async () => {
    if (!category) return;
    await upsertThreshold({
      path: { age_band: band, category },
      body: {
        min_verdict: verdict as (typeof VERDICTS)[number],
        min_score: score === '' ? null : Number(score),
      },
    });
    setCategory('');
    setScore('');
    refresh();
  };

  const remove = async (rowBand: string, rowCategory: string) => {
    await deleteThreshold({ path: { age_band: rowBand, category: rowCategory } });
    refresh();
  };

  return (
    <main>
      <h1>Moderation thresholds</h1>
      <p>
        Default: findings surface to families at <strong>{data.default_min_verdict}</strong> and
        above. Overrides below change that for one age band and category.
      </p>
      <table>
        <thead>
          <tr>
            <th>Age band</th>
            <th>Category</th>
            <th>Surfaces at</th>
            <th>Score floor</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <tr key={`${row.age_band}:${row.category}`}>
              <td>{row.age_band}</td>
              <td>{row.category}</td>
              <td>{row.min_verdict}</td>
              <td>{row.min_score ?? '-'}</td>
              <td>
                <button type="button" onClick={() => remove(row.age_band, row.category)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Add or update an override</h2>
      <label>
        Age band
        <select value={band} onChange={(e) => setBand(e.target.value)}>
          {AGE_BANDS.map((b) => (
            <option key={b}>{b}</option>
          ))}
        </select>
      </label>
      <label>
        Category
        <input
          list="known-categories"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <datalist id="known-categories">
          {data.known_categories.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </label>
      <label>
        Surfaces at
        <select value={verdict} onChange={(e) => setVerdict(e.target.value)}>
          {VERDICTS.map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </label>
      <label>
        Score floor (0-1, optional)
        <input
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={score}
          onChange={(e) => setScore(e.target.value)}
        />
      </label>
      <button type="button" onClick={save} disabled={!category}>
        Save override
      </button>
    </main>
  );
}
```

- [ ] **Step 3: Register the admin-only route**

In `frontend/src/router.tsx`, mirror the ReviewDetailPage registration (line ~102) but with
`allowedRoles={['admin']}` on its ProtectedRoute group:

```tsx
{ path: 'moderation-thresholds', element: suspended(<ModerationThresholdsPage />) }
```

placed inside (or wrapped by) a `ProtectedRoute` that allows only `admin`. Follow the file's
existing lazy-import pattern for the page component.

- [ ] **Step 4: Write the Vitest test**

Create `frontend/src/guardian/ModerationThresholdsPage.test.tsx`, pattern-matching an existing
page test (run `ls frontend/src/guardian/*.test.tsx` and copy its mock style for sdk.gen):

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ModerationThresholdsPage from './ModerationThresholdsPage';

vi.mock('../client/sdk.gen', () => ({
  listThresholdsApiV1AdminModerationThresholdsGet: vi.fn().mockResolvedValue({
    data: {
      default_min_verdict: 'flag',
      default_min_score: null,
      known_categories: ['toxicity'],
      rows: [
        { age_band: '3-5', category: 'violence', min_verdict: 'advisory', min_score: 0.3 },
      ],
    },
  }),
  upsertThresholdApiV1AdminModerationThresholdsAgeBandCategoryPut: vi.fn(),
  deleteThresholdApiV1AdminModerationThresholdsAgeBandCategoryDelete: vi.fn(),
}));

describe('ModerationThresholdsPage', () => {
  it('renders the default policy and override rows', async () => {
    render(<ModerationThresholdsPage />);
    await waitFor(() => {
      expect(screen.getByText(/surface to families at/i)).toBeInTheDocument();
    });
    expect(screen.getByText('violence')).toBeInTheDocument();
    expect(screen.getByText('0.3')).toBeInTheDocument();
  });
});
```

(Adjust the mocked identifiers to the actual generated names from Step 1.)

- [ ] **Step 5: Run frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run`
Expected: all pass.

- [ ] **Step 6: Check e2e suites for route collisions**

Run: `grep -rn "moderation-thresholds" frontend/e2e frontend/e2e-real 2>/dev/null; true`
Expected: no hits (new route, nothing to update). If route-map fixtures enumerate all routes,
add the new one in BOTH tiers.

- [ ] **Step 7: Commit**

```bash
cd frontend
git add src/client src/guardian/ModerationThresholdsPage.tsx src/guardian/ModerationThresholdsPage.test.tsx src/router.tsx
git commit -S -m "feat(frontend): admin moderation-threshold editor page"
```

---

### Task 8: Full-suite verification and PR readiness (operational)

`depends-on: Task4 [completion]`, `depends-on: Task5 [completion]`, `depends-on: Task7 [completion]`

- [ ] **Step 1: Backend gates**

Run: `uv run pytest --cov=src --cov-fail-under=80 && uv run ruff check . && uv run basedpyright src/ && uv run bandit -r src`
Expected: all green, coverage >= 80%.
Abort if: any unrelated test fails; investigate before touching it (concurrent PRs may own it).

- [ ] **Step 2: Frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run && npm run build`
Expected: all green.

- [ ] **Step 3: Pre-commit over the branch**

Run: `pre-commit run --all-files`
Expected: all hooks pass (including no-em-dash).

- [ ] **Step 4: CHANGELOG entry**

Add an entry under Unreleased per the repo convention (or apply the `skip-changelog` process if
the maintainer directs); check `CHANGELOG.md`'s existing entry format and match it.

- [ ] **Step 5: Live smoke of the fix (the only reviewer with no plan blind spots)**

Bring up the local stack per `docs/planning/` local-run recipe (db on 5442, uvicorn + npm run
dev), moderate-or-seed one story with a low-score advisory finding, and confirm: guardian
content summary hides it, admin review surface shows it, threshold editor lowers the floor and
the guardian view updates on refresh.
Expected: all three observations hold.

- [ ] **Step 6: Stop for user gate**

Do NOT push or open a PR. Report branch state and wait for explicit approval (repo rule:
pushing is user-gated).
