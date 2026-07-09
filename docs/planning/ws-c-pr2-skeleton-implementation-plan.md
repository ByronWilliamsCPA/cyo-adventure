---
schema_type: planning
title: "WS-C PR 2: Cell-Aware Skeleton Matching Implementation Plan"
description: "Task-by-task implementation plan for WS-C PR 2: the skeleton_slug provenance
  column, a pure/impure split for band x length x style cell matching with recency-weighted
  variety, and the authoring-plan alternatives/override surface."
tags:
  - planning
  - project
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an implementer with zero session context everything needed to build WS-C PR 2
  task by task against the approved spec."
component: Strategy
source: "docs/planning/ws-c-admin-processing-spec.md (PR2 section, decisions C-4 and C-6);
  codebase discovery 2026-07-08 on feat/ws-c-admin-processing at main @ d17ccce."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Replace band-only, style/length-blind skeleton auto-match
(`generation/skeleton_match.py::select_skeleton_for_band`) with matching against the full
ADR-011 cell (age band x length x narrative style, with style collapsing to prose below bands
`13-16`/`16+`). The pick is weighted against the family's recently-used skeletons (inverse
frequency with an implicit nonzero floor, so nothing is ever fully excluded), falls back to
uniform when there is no usage history, and the admin sees every in-cell alternative and may
override to any skeleton on disk, including a non-production or out-of-cell one, with a
non-blocking warning when the override is a mismatch.

## Architecture

`generation/skeleton_match.py` is rewritten around a **pure core, impure edge** split:

- Pure: metadata loading and cell matching from the filesystem (`candidates_for_cell`,
  `find_skeleton_metadata`, `skeleton_matches_cell`) and the weighted pick itself
  (`select_skeleton_for_cell`, injected `random.Random`, fully deterministic under a seed).
- Impure: `recent_skeleton_usage`, one async query joining `storybook_version` to `storybook`
  on the request's family, over the most recent `_RECENT_WINDOW = 20` versions.

`story_requests/authoring_plan.py::build_authoring_plan` is the only caller that combines the
two: it derives `(band, length, style)` from the concept brief (length null collapses to
`"short"`), loads in-cell candidates, and either honors an admin `skeleton_slug` override
(unconstrained, warned-not-blocked on mismatch) or draws a weighted pick using
`recent_skeleton_usage` plus a real (non-seeded) `random.SystemRandom()`.

A new nullable `storybook_version.skeleton_slug` column (this PR's migration, chained onto
PR1's head) records which skeleton produced a version; `persist_storybook` stamps it from
`StorybookParams.skeleton_slug`, and the worker threads it through from
`job_row.authoring_metadata["skeleton_slug"]` (already written by `build_authoring_plan`),
mirroring the existing `provider` provenance column exactly.

## Tech Stack

FastAPI + Pydantic v2, async SQLAlchemy 2.x, Alembic, pytest + testcontainers Postgres,
`@hey-api/openapi-ts` generated client (regenerated, not hand-edited).

## Conventions that bind every task

- Worktree: `.worktrees/ws-c`, branch `feat/ws-c-admin-processing`. All commands run from the
  worktree root unless stated otherwise.
- Signed commits (`git commit -S`), Conventional Commits, never `git add -A` (stage named
  paths only).
- No em-dash characters anywhere (pre-commit hook rejects them).
- RAD markers (`#CRITICAL`/`#ASSUME`/`#EDGE` + `#VERIFY`) on data-integrity assumptions,
  mandatory in `src/cyo_adventure/` per `src/cyo_adventure/CLAUDE.md`.
- Closed vocabularies used throughout: age bands `'3-5','5-8','8-11','10-13','13-16','16+'`;
  lengths `'short','medium','long'`; styles `'prose','gamebook'`; style-aware (teen) bands
  `'13-16','16+'`.
- Backend gates per task: the covering tests plus `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run basedpyright src/`.
- Error mapping (centralized exceptions): `ValidationError` -> 422, `ResourceNotFoundError` ->
  404, `StateTransitionError` -> 409.
- `frontend/src/client/` is build output: never hand-edit; regenerate only in Task 7.
- `random.Random()` construction is flagged by ruff's `S311` in `src/` (verified: not
  ignored there, only in `tests/**` and `scripts/**` per-file-ignores); production code uses
  `random.SystemRandom()` instead (a `random.Random` subclass, so it satisfies the same type
  hint, and is not flagged), so no `# noqa` is needed anywhere in this plan. Tests use plain
  seeded `random.Random(seed)` freely.

## Decisions resolved during planning (bind the tasks below)

1. `down_revision` for this PR's migration is PR1's head revision, unknown until PR1 merges.
   Task 0 is a hard precondition that resolves it before Task 1 can be written for real.
2. Cell match: `metadata.age_band == band` and `metadata.length == length` always; for
   `band in {"13-16", "16+"}` also `metadata.narrative_style == style`; for every other band the
   style axis is not checked (ADR-011: implicitly prose below teen bands).
3. Null `request.length` (nullable since #164) collapses to `"short"` for cell formation.
   Verified in `story_requests/brief.py:112`: a null `request.length` is stored as a literal
   JSON `null` in `concept.brief["length"]`; the existing fixture in
   `tests/unit/test_authoring_plan.py::_concept` omits the key entirely (never sets it), so the
   fallback helper must treat both "key absent" and "value is JSON null" identically.
4. `select_skeleton_for_cell` is pure: `candidates: list[str]`, `recent_usage: dict[str, int]`,
   `rng: random.Random` in, `Selection(slug, alternatives)` out. Weight per candidate is
   `1 / (1 + recent_usage.get(slug, 0))`; empty `recent_usage` gives every candidate weight 1.0
   (uniform). It requires a non-empty `candidates` list; the caller (`build_authoring_plan`)
   already raises `ValidationError` on an empty cell before ever calling it, exactly mirroring
   today's `select_skeleton_for_band is None` check.
5. `recent_skeleton_usage(session, family_id)` returns `{}` immediately when `family_id is
   None` (admin/catalog requests carry no family) with no query issued; otherwise it counts
   `storybook_version.skeleton_slug` (skipping `NULL`) over the most recent
   `_RECENT_WINDOW = 20` `storybook_version` rows for that family, ordered by `created_at desc`.
6. The admin's `skeleton_slug` override is unconstrained (C-6): a slug that does not exist on
   disk (searched across every band directory, not just the request's own) is a 422; a slug
   that exists but is non-production-eligible or outside the cell is accepted with a warning
   appended to `AuthoringPlanResponse.warnings`, never blocked.
7. `AuthoringPlanResponse.skeleton_alternatives` is `list[AlternativeView]` (one field: `slug:
   str`), populated from every in-cell production-eligible skeleton (the same list
   `select_skeleton_for_cell` drew from), for both the auto-picked and the overridden path.
   `fresh_generation` plans get an empty list, matching today's `skeleton_slug: None`.

## File structure

Create:

- `migrations/versions/20260709_0900_add_storybook_version_skeleton_slug.py` (revision
  `228c68e8f1e7`, down `<PR1_HEAD>`, filled in by Task 0)
- `tests/integration/test_storybook_version_skeleton_slug_migration.py`
- `tests/integration/test_skeleton_recency.py`

Modify:

- `src/cyo_adventure/db/models.py` (`StorybookVersion.skeleton_slug`)
- `src/cyo_adventure/generation/persistence.py` (`StorybookParams.skeleton_slug`,
  `persist_storybook`)
- `src/cyo_adventure/generation/worker.py` (`_skeleton_slug_of`, `_persist_and_moderate`)
- `src/cyo_adventure/generation/skeleton_match.py` (full rewrite: cell matching + weighting +
  recency query; `select_skeleton_for_band` removed)
- `src/cyo_adventure/story_requests/authoring_plan.py` (cell derivation, override handling,
  `AuthoringPlanResult.skeleton_alternatives`)
- `src/cyo_adventure/api/schemas.py` (`AlternativeView`, `AuthoringPlanRequest.skeleton_slug`,
  `AuthoringPlanResponse.skeleton_alternatives`)
- `src/cyo_adventure/api/story_requests.py` (`create_authoring_plan` response mapping)
- `tests/unit/test_persistence.py`, `tests/integration/test_generation_worker.py`,
  `tests/unit/test_skeleton_match.py` (rewritten), `tests/unit/test_authoring_plan.py`,
  `tests/integration/test_authoring_plan_api.py`
- `CHANGELOG.md`
- `frontend/src/client/` (regenerated, Task 7)

No e2e change: `grep -rl "authoring-plan\|AuthoringPlan" frontend/src frontend/e2e
frontend/e2e-real` matches only the generated client (`frontend/src/client/{index,sdk.gen,
types.gen}.ts`); no app source or e2e spec calls this endpoint today, so neither `e2e/` nor
`e2e-real/` needs a change for this PR.

---

### Task 0: Precondition: resolve PR1's head revision (Operational Task)

depends-on: PR1 merged (or rebased onto, in this worktree)

This is a hard gate: PR2's migration chains onto PR1's `provider_model_allowlist` /
`provider_model_allowlist_audit` migration, which does not exist yet in this worktree. Task 1
cannot be committed with a real `down_revision` until this resolves.

- [ ] **Step 1: Confirm PR1 is present on this branch**

Command:

```bash
git log --oneline -1 -- migrations/versions/ | head -1
ls migrations/versions/ | sort | tail -5
```

Expected: the newest migration file's name/content is PR1's allowlist migration (grep its
docstring for "provider_model_allowlist"). If PR1 has merged to `main` but this worktree's
branch has not been rebased, rebase now:

```bash
git fetch origin main
git rebase origin/main
```

Abort-if: PR1 is not yet merged to `main` and no local rebase target exists. Stop here and
resume this plan only after PR1 lands; do not invent a placeholder revision id and proceed,
since alembic will silently create a second head if the real chain is wrong.

- [ ] **Step 2: Read PR1's real head revision id**

Command:

```bash
uv run alembic heads
```

Expected: exactly one head, printed as `<hex-id> (head)`. That hex id is `<PR1_HEAD>` for every
reference in this plan (Task 1's migration file and its test file). Record it now; Task 1's
code blocks below use the literal placeholder text `<PR1_HEAD>` everywhere it must be
substituted.

Abort-if: `alembic heads` prints more than one head (a branch point). Resolve the branch
(coordinate with WS-D per the spec's "Migration chain and WS-D coordination" section) before
continuing; do not chain PR2 onto an ambiguous head.

---

### Task 1: `skeleton_slug` migration and ORM column

depends-on: Task0 [completion]

**Files:**

- Create: `migrations/versions/20260709_0900_add_storybook_version_skeleton_slug.py`
- Modify: `src/cyo_adventure/db/models.py`
- Test: `tests/integration/test_storybook_version_skeleton_slug_migration.py`

- [ ] **Step 1: Write the failing migration test first**

Mirrors `tests/integration/test_storybook_version_provider_migration.py` exactly (same
`_migration_utils` helpers, same fixture). Substitute the real `<PR1_HEAD>` value from Task 0
Step 2 for both placeholders below.

```python
"""Migration round-trip for the storybook_version.skeleton_slug column (WS-C PR2)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

# Pin the round-trip to explicit revision ids rather than "head"/"-1": a
# relative target silently retargets whenever a later migration lands on top
# (the lesson from PR #108; see test_storybook_version_provider_migration.py
# for the same pattern).
_PREV_HEAD = "<PR1_HEAD>"
_SKELETON_SLUG_HEAD = "228c68e8f1e7"


@pytest.mark.integration
def test_skeleton_slug_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains onto PR1's head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_storybook_version_skeleton_slug*.py"))
    assert files, f"skeleton_slug migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_skeleton_slug_migration", files[0])
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
def test_skeleton_slug_migration_upgrade_downgrade(
    migration_pg_url: str,
) -> None:
    """alembic upgrade then downgrade of the skeleton_slug revision succeed."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _SKELETON_SLUG_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    assert "Running upgrade" in up.stderr

    down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    assert "Running downgrade" in down.stderr


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skeleton_slug_column_present_only_while_upgraded(
    migration_pg_url: str,
) -> None:
    """The column exists after upgrade and is gone again after downgrade."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _SKELETON_SLUG_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'storybook_version' "
                    "AND column_name = 'skeleton_slug'"
                )
            )
            assert result.first() is not None, (
                "storybook_version.skeleton_slug column missing after upgrade"
            )

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'storybook_version' "
                    "AND column_name = 'skeleton_slug'"
                )
            )
            assert result.first() is None, (
                "storybook_version.skeleton_slug column still present after downgrade"
            )
    finally:
        await engine.dispose()
```

Run: `uv run pytest tests/integration/test_storybook_version_skeleton_slug_migration.py -v`
Expected FAIL: `test_skeleton_slug_migration_imports_and_chains` fails with
`AssertionError: skeleton_slug migration not found` (the file does not exist yet); the other two
error before running (no such head revision).

- [ ] **Step 2: Write the migration**

Mirrors `migrations/versions/20260706_1500_add_storybook_version_provider.py` exactly. Replace
`<PR1_HEAD>` with the real value from Task 0.

```python
"""add storybook_version skeleton_slug column

Revision ID: 228c68e8f1e7
Revises: <PR1_HEAD>
Create Date: 2026-07-09 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "228c68e8f1e7"
down_revision: Union[str, Sequence[str], None] = "<PR1_HEAD>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable storybook_version.skeleton_slug column (WS-C PR2).

    Nullable, no backfill: fresh_generation and imported-book versions never
    had a skeleton, and every pre-PR2 skeleton_fill row predates this
    provenance column, so both simply have no recorded slug, which degrades
    to "unknown" for display rather than an error (mirrors the provider
    column's own null semantics, migration 20260706_1500).
    """
    op.add_column(
        "storybook_version",
        sa.Column("skeleton_slug", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    """Drop storybook_version.skeleton_slug."""
    op.drop_column("storybook_version", "skeleton_slug")
```

- [ ] **Step 3: Add the ORM column**

In `src/cyo_adventure/db/models.py`, on `StorybookVersion` (after the `provider` column,
before `created_at`, around line 242):

```python
    # Which production skeleton (skeletons/<band>/<slug>.json) this version was
    # filled from, or None for a fresh_generation version, an imported book, or
    # any version predating this column (WS-C PR2). Set once, at persist time,
    # from the job's authoring_metadata["skeleton_slug"]; never backfilled.
    skeleton_slug: Mapped[str | None] = mapped_column(String(120), default=None)
```

- [ ] **Step 4: Run the migration tests**

Run: `uv run pytest tests/integration/test_storybook_version_skeleton_slug_migration.py -v`
Expected PASS: all three tests green (requires Docker/testcontainers; if unavailable locally,
run in CI before marking this task done).

- [ ] **Step 5: Run the full backend gates**

Run: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: no failures, no lint or type errors.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/20260709_0900_add_storybook_version_skeleton_slug.py \
  src/cyo_adventure/db/models.py \
  tests/integration/test_storybook_version_skeleton_slug_migration.py
git commit -S -m "feat(db): add storybook_version.skeleton_slug provenance column (WS-C PR2)"
```

---

### Task 2: Thread `skeleton_slug` through persistence and the worker

depends-on: Task1 [completion]

**Files:**

- Modify: `src/cyo_adventure/generation/persistence.py`, `src/cyo_adventure/generation/worker.py`
- Test: `tests/unit/test_persistence.py`, `tests/integration/test_generation_worker.py`

- [ ] **Step 1: Write the failing unit test for `persist_storybook`**

Append to `tests/unit/test_persistence.py` (reuse its existing `_FakeSession`/`_added` helpers):

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_stamps_skeleton_slug_when_provided() -> None:
    session = _FakeSession()
    params = StorybookParams(
        story_id="s_demo2",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
        skeleton_slug="the-cave-of-echoes",
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].skeleton_slug == "the-cave-of-echoes"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_skeleton_slug_defaults_to_none() -> None:
    session = _FakeSession()
    params = StorybookParams(
        story_id="s_demo3",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].skeleton_slug is None
```

Run: `uv run pytest tests/unit/test_persistence.py -v`
Expected FAIL: `TypeError: StorybookParams.__init__() got an unexpected keyword argument
'skeleton_slug'` on the first new test.

- [ ] **Step 2: Add the field to `StorybookParams` and stamp it in `persist_storybook`**

In `src/cyo_adventure/generation/persistence.py`, add to `StorybookParams` (after `provider`,
before `validation_report`):

```python
    skeleton_slug: str | None = None
```

Update the class docstring's Attributes with one line: `skeleton_slug: The production skeleton
this version was filled from, or None for fresh_generation/import (WS-C PR2).`

In `persist_storybook`, add to the `StorybookVersion(...)` constructor call (after
`provider=params.provider,`):

```python
        skeleton_slug=params.skeleton_slug,
```

- [ ] **Step 3: Run the unit tests**

Run: `uv run pytest tests/unit/test_persistence.py -v`
Expected PASS: both new tests, plus every pre-existing test in the file, green.

- [ ] **Step 4: Write the failing worker integration assertion**

`tests/integration/test_generation_worker.py::test_passing_run_creates_storybook_version`
already seeds a skeleton-fill job with `authoring_metadata={"skeleton_slug": _SKELETON_SLUG,
...}` (see the `gen_seed` fixture, `_SKELETON_SLUG = "the-cave-of-echoes"`). Add one assertion
at the end of that test, right after the existing `assert sv.provider == job.provider`:

```python
        # WS-C PR2: the version's skeleton_slug matches the job's
        # authoring_metadata, threaded through at persist time.
        assert sv.skeleton_slug == _SKELETON_SLUG
```

Run: `uv run pytest tests/integration/test_generation_worker.py::test_passing_run_creates_storybook_version -v`
Expected FAIL: `AttributeError: 'StorybookVersion' object has no attribute 'skeleton_slug'` is
already fixed by Task 1's column; the real failure here is
`assert None == "the-cave-of-echoes"` (the worker does not thread it yet).

- [ ] **Step 5: Thread it through the worker**

In `src/cyo_adventure/generation/worker.py`, add a small pure helper right after
`_review_stage2_override` (mirrors its exact shape):

```python
def _skeleton_slug_of(authoring: dict[str, object] | None) -> str | None:
    """Return the skeleton slug recorded on the job, if any.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None`` for a
            fresh (non-skeleton) generation that carries no skeleton.

    Returns:
        The skeleton slug when ``authoring`` carries a string
        ``skeleton_slug``; otherwise ``None`` (fresh_generation, or a
        skeleton_fill job somehow missing the key).
    """
    if authoring is None:
        return None
    value = authoring.get("skeleton_slug")
    return value if isinstance(value, str) else None
```

In `_persist_and_moderate`, add to the `StorybookParams(...)` call (after
`provider=_provider_label(ctx.effective_provider),`):

```python
            skeleton_slug=_skeleton_slug_of(ctx.authoring),
```

- [ ] **Step 6: Run the integration test, then the full suite**

Run: `uv run pytest tests/integration/test_generation_worker.py -v`
Expected PASS: all tests in the file, including the new assertion.

Run: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: no failures, no lint or type errors.

- [ ] **Step 7: Commit**

```bash
git add src/cyo_adventure/generation/persistence.py src/cyo_adventure/generation/worker.py \
  tests/unit/test_persistence.py tests/integration/test_generation_worker.py
git commit -S -m "feat(generation): thread skeleton_slug provenance through persist and worker (WS-C PR2)"
```

---

### Task 3: Cell-matching candidate loader (typed metadata, band collapse)

depends-on: Task1 [completion] (no runtime dependency on Task 1/2; ordered here per the spec's
suggested sequence)

**Files:**

- Modify (full rewrite): `src/cyo_adventure/generation/skeleton_match.py`
- Modify (full rewrite): `tests/unit/test_skeleton_match.py`

This task replaces `select_skeleton_for_band` (band-only, style/length-blind) with the cell
candidate loader. Task 4 adds the weighted pick to the same file/test file.

- [ ] **Step 1: Write the failing unit tests**

Replace the entire contents of `tests/unit/test_skeleton_match.py`:

```python
"""Unit tests for cell-aware skeleton matching (WS-C PR2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.generation import skeleton_match
from cyo_adventure.generation.skeleton_match import (
    candidates_for_cell,
    find_skeleton_metadata,
    skeleton_matches_cell,
)
from cyo_adventure.storybook.models import AgeBand, NarrativeStyle, StoryMetadata

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_candidates_for_cell_matches_real_library_singleton_cell() -> None:
    """10-13/medium/prose has exactly one production skeleton on disk today."""
    assert candidates_for_cell("10-13", "medium", "prose") == ["the-hollow-lighthouse"]


def test_candidates_for_cell_excludes_non_eligible_and_length_mismatch() -> None:
    """10-13/short/prose excludes the non-eligible clocktower-cipher (which has no
    length/style at all) and every other length in the band."""
    assert candidates_for_cell("10-13", "short", "prose") == ["the-midnight-museum"]


def test_candidates_for_cell_matches_style_for_teen_band() -> None:
    """13-16/medium: prose and gamebook are different cells (style-aware band)."""
    assert candidates_for_cell("13-16", "medium", "prose") == [
        "the-signal-in-the-static"
    ]
    assert candidates_for_cell("13-16", "medium", "gamebook") == [
        "the-sunspire-ascent"
    ]


def test_candidates_for_cell_ignores_style_below_teen_band() -> None:
    """8-11 is not style-aware: a "gamebook" request still matches the prose skeleton."""
    assert candidates_for_cell("8-11", "short", "gamebook") == ["the-cave-of-echoes"]


def test_candidates_for_cell_returns_empty_for_unknown_band() -> None:
    assert candidates_for_cell("99-100", "short", "prose") == []


def test_candidates_for_cell_returns_empty_for_no_matching_cell() -> None:
    """8-11 has no "long"+"gamebook" skeleton (nor any gamebook skeleton at all)."""
    assert candidates_for_cell("8-11", "long", "gamebook") == []


def test_candidates_for_cell_skips_malformed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt JSON file must be skipped, not crash the scan (mirrors the
    old select_skeleton_for_band contract)."""
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    (band_dir / "aaa-broken.json").write_text("{ not valid json", encoding="utf-8")
    good = {
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "time_cave",
            "length": "short",
            "narrative_style": "prose",
        }
    }
    (band_dir / "zzz-good.json").write_text(json.dumps(good), encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    assert candidates_for_cell("8-11", "short", "prose") == ["zzz-good"]


def test_find_skeleton_metadata_scans_every_band() -> None:
    """The override lookup is not scoped to any one band directory."""
    metadata = find_skeleton_metadata("the-sunspire-ascent")
    assert metadata is not None
    assert metadata.age_band == AgeBand.BAND_13_16
    assert metadata.narrative_style == NarrativeStyle.GAMEBOOK


def test_find_skeleton_metadata_returns_none_for_unknown_slug() -> None:
    assert find_skeleton_metadata("does-not-exist-anywhere") is None


def test_skeleton_matches_cell_true_for_exact_match() -> None:
    metadata = StoryMetadata.model_validate(
        {
            "age_band": "13-16",
            "reading_level": {"target": 8.0},
            "tier": 1,
            "estimated_minutes": 20,
            "ending_count": 2,
            "topology": "time_cave",
            "length": "long",
            "narrative_style": "gamebook",
        }
    )
    assert skeleton_matches_cell(metadata, band="13-16", length="long", style="gamebook")


def test_skeleton_matches_cell_false_for_style_mismatch_in_teen_band() -> None:
    metadata = StoryMetadata.model_validate(
        {
            "age_band": "13-16",
            "reading_level": {"target": 8.0},
            "tier": 1,
            "estimated_minutes": 20,
            "ending_count": 2,
            "topology": "time_cave",
            "length": "long",
            "narrative_style": "gamebook",
        }
    )
    assert not skeleton_matches_cell(metadata, band="13-16", length="long", style="prose")


def test_skeleton_matches_cell_ignores_style_below_teen_band() -> None:
    metadata = StoryMetadata.model_validate(
        {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "time_cave",
            "length": "short",
            "narrative_style": "prose",
        }
    )
    assert skeleton_matches_cell(metadata, band="8-11", length="short", style="gamebook")
```

Every test builds `StoryMetadata` via `model_validate` on a real dict rather than a shortcut
constructor call: `ReadingLevel` is a required nested model (no default), so a bare keyword
constructor call would need one anyway, and `model_validate` on a raw dict is also what
`_load_metadata` itself does, so the tests exercise the same code path as production.

Run: `uv run pytest tests/unit/test_skeleton_match.py -v`
Expected FAIL: `ImportError: cannot import name 'candidates_for_cell' from
'cyo_adventure.generation.skeleton_match'` (the module still only exports
`select_skeleton_for_band`).

- [ ] **Step 2: Rewrite `skeleton_match.py`'s pure candidate-loading half**

Replace the full contents of `src/cyo_adventure/generation/skeleton_match.py` with (Task 4
appends the weighting/recency sections below the `# --- weighting ---` marker in the next task;
write everything up to and including `find_skeleton_metadata` now):

```python
"""Cell-aware skeleton selection for a story's (band, length, style) cell.

Replaces the old band-only, style/length-blind ``select_skeleton_for_band``
(WS-C PR2). Splits into a pure core (metadata loading, cell matching, the
weighted pick) and one impure recency query
(:func:`recent_skeleton_usage`), so the selection logic itself is fully
unit-testable without a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import StoryMetadata

# #ASSUME: external-resources: the skeleton library is read cwd-relative
# ("skeletons/<band>/*.json"), matching the existing discovery convention in
# tests/unit/test_skeleton.py (Path("skeletons").glob(...)); the app and test
# suite are always invoked from the repository root.
# #VERIFY: a deployment that changes the working directory must mount or copy
# skeletons/ at that same relative path, or cell matching silently finds
# nothing (returns an empty list, surfaced by the caller as a 422, not a
# crash).
_SKELETON_ROOT = Path("skeletons")

# Bands where the narrative-style axis is meaningful (ADR-011); below these,
# style collapses to prose and is not matched.
_STYLE_AWARE_BANDS = frozenset({"13-16", "16+"})


@dataclass(frozen=True, slots=True)
class Selection:
    """A weighted-random skeleton pick plus the full in-cell candidate list."""

    slug: str
    alternatives: list[str]


def _load_metadata(path: Path) -> StoryMetadata | None:
    """Return the typed metadata for a skeleton file, or None if unreadable.

    Mirrors the old select_skeleton_for_band contract: a corrupt or
    unreadable file must not crash the scan (this runs synchronously inside
    POST /authoring-plan). Malformed or schema-invalid metadata is treated
    the same as a missing file: skipped, not raised.

    Args:
        path: Path to a skeleton JSON file.

    Returns:
        The typed StoryMetadata, or None on any read/parse/schema failure.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        data = cast("dict[str, object]", json.loads(raw))
    except (OSError, json.JSONDecodeError):
        return None
    meta = data.get("metadata") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        return None
    try:
        return StoryMetadata.model_validate(meta)
    except PydanticValidationError:
        return None


def _production_candidates(band: str) -> list[tuple[str, StoryMetadata]]:
    """Return (slug, metadata) for every production-eligible skeleton in a band.

    Args:
        band: The age band directory name (e.g. "8-11").

    Returns:
        Sorted-by-filename (slug, metadata) pairs; empty if the band
        directory does not exist or has no production-eligible skeleton.
    """
    band_dir = _SKELETON_ROOT / band
    if not band_dir.is_dir():
        return []
    candidates: list[tuple[str, StoryMetadata]] = []
    for path in sorted(band_dir.glob("*.json")):
        metadata = _load_metadata(path)
        if metadata is None or not metadata.production_eligible:
            continue
        candidates.append((path.stem, metadata))
    return candidates


def skeleton_matches_cell(
    metadata: StoryMetadata, *, band: str, length: str, style: str
) -> bool:
    """Return whether a skeleton's metadata matches a (band, length, style) cell.

    Args:
        metadata: The skeleton's typed metadata.
        band: The request's age band.
        length: The request's length ("short"/"medium"/"long"); a null
            request length must already be collapsed to a default by the
            caller (see story_requests/authoring_plan.py::_length_of).
        style: The request's narrative style; ignored for every band except
            "13-16" and "16+" (ADR-011: style collapses to prose below the
            teen bands).

    Returns:
        True if age_band and length match, and (for the two teen bands only)
        narrative_style also matches.
    """
    if metadata.age_band != band:
        return False
    metadata_length = metadata.length if metadata.length is not None else None
    if metadata_length != length:
        return False
    if band in _STYLE_AWARE_BANDS and metadata.narrative_style != style:
        return False
    return True


def candidates_for_cell(band: str, length: str, style: str) -> list[str]:
    """Return slugs of every production-eligible skeleton matching a cell.

    Args:
        band: The request's age band.
        length: The request's length, already defaulted if the request's own
            length was null.
        style: The request's narrative style.

    Returns:
        Sorted-by-filename slugs; empty if no skeleton matches (the caller
        must treat an empty list as "no skeleton available", exactly as the
        old select_skeleton_for_band's None return was treated).
    """
    return [
        slug
        for slug, metadata in _production_candidates(band)
        if skeleton_matches_cell(metadata, band=band, length=length, style=style)
    ]


def find_skeleton_metadata(slug: str) -> StoryMetadata | None:
    """Return a skeleton's typed metadata by scanning every band directory.

    Used for the admin's unconstrained skeleton_slug override (decision C-6),
    which may name a skeleton outside the request's own band directory (an
    explicitly out-of-cell pick), or a non-production-eligible one.

    Args:
        slug: The skeleton's filename stem, as supplied by the admin.

    Returns:
        The typed metadata, or None if no band directory has a file named
        "<slug>.json" (or that file is unreadable/malformed).
    """
    if not _SKELETON_ROOT.is_dir():
        return None
    for band_dir in sorted(_SKELETON_ROOT.iterdir()):
        if not band_dir.is_dir():
            continue
        path = band_dir / f"{slug}.json"
        if path.is_file():
            return _load_metadata(path)
    return None
```

Note: `find_skeleton_metadata` does not filter on `production_eligible` (unlike
`_production_candidates`); the override path in Task 6 needs to see a non-eligible skeleton's
metadata in order to warn about it, not silently treat it as absent.

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_skeleton_match.py -v`
Expected PASS: every test in the rewritten file.

- [ ] **Step 4: Fix the now-broken caller and its tests (mechanical, not new behavior yet)**

`story_requests/authoring_plan.py` still imports `select_skeleton_for_band`, which no longer
exists. This step only makes the build importable again; Task 6 does the real integration.
Temporarily replace the import and the one call site so the existing test suite still passes
unchanged in the interim:

In `src/cyo_adventure/story_requests/authoring_plan.py`, change:

```python
from cyo_adventure.generation.skeleton_match import select_skeleton_for_band
```

to:

```python
from cyo_adventure.generation.skeleton_match import candidates_for_cell
```

and change the `if method == "skeleton_fill":` block's first two lines from:

```python
    if method == "skeleton_fill":
        skeleton_slug = select_skeleton_for_band(band)
        if skeleton_slug is None:
```

to:

```python
    if method == "skeleton_fill":
        _candidates = candidates_for_cell(band, "short", "prose")
        skeleton_slug = _candidates[0] if _candidates else None
        if skeleton_slug is None:
```

This is intentionally the narrowest possible patch (hardcoded "short"/"prose", first-candidate
pick) purely to keep `tests/unit/test_authoring_plan.py` and
`tests/integration/test_authoring_plan_api.py` green between Task 3 and Task 6; Task 6 replaces
this whole block with the real cell derivation, override, and weighted pick.

Run: `uv run pytest tests/unit/test_authoring_plan.py tests/integration/test_authoring_plan_api.py -v`
Expected PASS: unchanged (every existing 8-11/10-13 fixture in those files has exactly one
short+prose skeleton today, so the hardcoded patch is behaviorally identical to the old
alphabetical-first-in-band pick for every existing test case).

- [ ] **Step 5: Run the full backend gates**

Run: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: no failures, no lint or type errors.

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/generation/skeleton_match.py \
  src/cyo_adventure/story_requests/authoring_plan.py tests/unit/test_skeleton_match.py
git commit -S -m "feat(generation): cell-aware skeleton candidate matching (WS-C PR2)"
```

---

### Task 4: Pure weighted selection (recency floor, determinism, uniform fallback)

depends-on: Task3 [completion]

**Files:**

- Modify: `src/cyo_adventure/generation/skeleton_match.py` (append)
- Modify: `tests/unit/test_skeleton_match.py` (append)

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/unit/test_skeleton_match.py` (add `import random` to the top-level imports,
and `select_skeleton_for_cell` to the existing `from cyo_adventure.generation.skeleton_match
import (...)` block):

```python
def test_weight_never_reaches_zero() -> None:
    """The inverse-frequency floor: however often a slug was used, its weight
    stays strictly positive, so it is never fully excluded from the draw."""
    assert skeleton_match._weight(0) == 1.0
    assert skeleton_match._weight(1) == 0.5
    assert skeleton_match._weight(1000) == 1.0 / 1001


def test_select_skeleton_for_cell_is_deterministic_under_seeded_rng() -> None:
    """The same seed and inputs always produce the same pick."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    recent_usage = {
        "cave-of-echoes": 5,
        "clockwork-menagerie": 0,
        "sky-ship-stowaway": 0,
    }
    first = skeleton_match.select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42)
    )
    second = skeleton_match.select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42)
    )
    assert first.slug == second.slug == "sky-ship-stowaway"
    assert first.alternatives == candidates


def test_select_skeleton_for_cell_uniform_fallback_when_recent_usage_empty() -> None:
    """No recency history (new family, or no family at all) is a uniform draw."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    selection = skeleton_match.select_skeleton_for_cell(
        candidates, {}, random.Random(7)
    )
    assert selection.slug == "cave-of-echoes"


def test_select_skeleton_for_cell_returns_full_candidate_list_as_alternatives() -> None:
    candidates = ["a", "b", "c"]
    selection = skeleton_match.select_skeleton_for_cell(
        candidates, {"a": 2}, random.Random(1)
    )
    assert selection.alternatives == ["a", "b", "c"]
    assert selection.slug in candidates


def test_select_skeleton_for_cell_raises_on_empty_candidates() -> None:
    """An internal-invariant guard: the caller must check candidates_for_cell(...)
    for emptiness before calling this (mirrors the old None-check contract)."""
    with pytest.raises(ValueError, match="at least one candidate"):
        skeleton_match.select_skeleton_for_cell([], {}, random.Random(0))
```

This last test needs `pytest` imported at module scope (not just under `TYPE_CHECKING`, since
`pytest.raises` is a runtime call); change the existing `if TYPE_CHECKING: ... import pytest`
to a plain top-level `import pytest` (the `Path`/`monkeypatch` type-only usages stay under
`TYPE_CHECKING`, but `pytest.raises` and `pytest.MonkeyPatch` as a type annotation both need the
real module now).

Run: `uv run pytest tests/unit/test_skeleton_match.py -v`
Expected FAIL: `AttributeError: module 'cyo_adventure.generation.skeleton_match' has no
attribute '_weight'` (and `select_skeleton_for_cell` is likewise undefined).

- [ ] **Step 2: Append the weighting section to `skeleton_match.py`**

Add at the end of `src/cyo_adventure/generation/skeleton_match.py` (after
`find_skeleton_metadata`):

```python
def _weight(recent_count: int) -> float:
    """Return the inverse-frequency weight for a candidate's recent-use count.

    Args:
        recent_count: How many times this slug appeared in the family's
            recent storybook_version history (0 if never, or no history).

    Returns:
        1 / (1 + recent_count): 1.0 for an unused candidate, strictly
        decreasing but never zero as recent_count grows (the "implicit
        nonzero floor" from decision C-4: nothing is ever fully excluded).
    """
    return 1.0 / (1 + recent_count)


def select_skeleton_for_cell(
    candidates: list[str],
    recent_usage: dict[str, int],
    rng: random.Random,
) -> Selection:
    """Weighted-random pick from an in-cell candidate list.

    Args:
        candidates: Production-eligible skeleton slugs whose metadata matches
            the request's cell (from candidates_for_cell); must be
            non-empty. The caller is responsible for the "no matching
            skeleton" 422 before ever calling this.
        recent_usage: {slug: count} of how many times each slug was recently
            used by the family (from recent_skeleton_usage); an empty map
            (no family, or no history) yields a uniform pick.
        rng: An injected random.Random, so callers get deterministic
            behavior under a seeded instance (tests) and real randomness in
            production (see story_requests/authoring_plan.py, which passes a
            random.SystemRandom() rather than random.Random()).

    Returns:
        Selection: the weighted pick, plus every in-cell candidate as
        `alternatives` (so the admin sees every option, including the ones
        not drawn).

    Raises:
        ValueError: If candidates is empty (an internal-invariant
            violation; callers must check candidates_for_cell(...) first).
    """
    if not candidates:
        msg = "select_skeleton_for_cell requires at least one candidate"
        raise ValueError(msg)
    weights = [_weight(recent_usage.get(slug, 0)) for slug in candidates]
    pick = rng.choices(candidates, weights=weights, k=1)[0]
    return Selection(slug=pick, alternatives=list(candidates))
```

Add `import random` to the module's imports, but under `TYPE_CHECKING` (the module never
constructs a `random.Random` itself, only receives one as a parameter, so the import is
type-annotation-only and ruff's TC003 would otherwise flag a top-level import):

```python
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import random
```

(Merge this into the existing `from typing import cast` line and add the `if TYPE_CHECKING`
block right after the other module-level imports, before `_SKELETON_ROOT`.)

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_skeleton_match.py -v`
Expected PASS: every test in the file, including the five new ones.

- [ ] **Step 4: Run the full backend gates**

Run: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: no failures, no lint or type errors (verify specifically that ruff raises no `S311`
on this file: it never constructs `random.Random()` itself, only calls `.choices()` on an
injected instance, and a prior spike confirmed `rng.choices(...)` on a parameter is not flagged,
only `random.Random()`/`random.choices()` module-level construction is).

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/generation/skeleton_match.py tests/unit/test_skeleton_match.py
git commit -S -m "feat(generation): recency-weighted skeleton pick with a nonzero floor (WS-C PR2)"
```

---

### Task 5: Family recency query

depends-on: Task1 [completion], Task4 [completion]

**Files:**

- Modify: `src/cyo_adventure/generation/skeleton_match.py` (append)
- Create: `tests/integration/test_skeleton_recency.py`

- [ ] **Step 1: Write the failing integration test**

```python
"""Integration tests for recent_skeleton_usage (WS-C PR2)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Family, Storybook, StorybookVersion
from cyo_adventure.generation.skeleton_match import recent_skeleton_usage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed_version(
    session: AsyncSession,
    family_id: uuid.UUID,
    *,
    storybook_id: str,
    skeleton_slug: str | None,
) -> None:
    session.add(Storybook(id=storybook_id, family_id=family_id, status="draft"))
    await session.flush()
    session.add(
        StorybookVersion(
            storybook_id=storybook_id,
            version=1,
            blob={"id": storybook_id, "title": "T", "nodes": []},
            skeleton_slug=skeleton_slug,
        )
    )
    await session.flush()


async def test_recent_skeleton_usage_counts_within_family(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family = Family(name="Recency Fam")
        session.add(family)
        await session.flush()
        await _seed_version(
            session, family.id, storybook_id="s_r1", skeleton_slug="the-cave-of-echoes"
        )
        await _seed_version(
            session, family.id, storybook_id="s_r2", skeleton_slug="the-cave-of-echoes"
        )
        await _seed_version(
            session, family.id, storybook_id="s_r3", skeleton_slug="the-sky-ship-stowaway"
        )
        await _seed_version(session, family.id, storybook_id="s_r4", skeleton_slug=None)
        await session.commit()

        usage = await recent_skeleton_usage(session, family.id)
        assert usage == {"the-cave-of-echoes": 2, "the-sky-ship-stowaway": 1}


async def test_recent_skeleton_usage_returns_empty_for_none_family_id(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        assert await recent_skeleton_usage(session, None) == {}


async def test_recent_skeleton_usage_returns_empty_for_family_with_no_history(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family = Family(name="Empty Fam")
        session.add(family)
        await session.flush()
        await session.commit()

        assert await recent_skeleton_usage(session, family.id) == {}


async def test_recent_skeleton_usage_ignores_other_families(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family_a = Family(name="Fam A")
        family_b = Family(name="Fam B")
        session.add_all([family_a, family_b])
        await session.flush()
        await _seed_version(
            session, family_a.id, storybook_id="s_a1", skeleton_slug="the-cave-of-echoes"
        )
        await _seed_version(
            session, family_b.id, storybook_id="s_b1", skeleton_slug="the-sky-ship-stowaway"
        )
        await session.commit()

        usage = await recent_skeleton_usage(session, family_a.id)
        assert usage == {"the-cave-of-echoes": 1}
```

Run: `uv run pytest tests/integration/test_skeleton_recency.py -v`
Expected FAIL: `ImportError: cannot import name 'recent_skeleton_usage' from
'cyo_adventure.generation.skeleton_match'`.

- [ ] **Step 2: Append the recency query to `skeleton_match.py`**

Add at the end of the file, and add the two new runtime imports (`select` from `sqlalchemy`,
`Storybook`/`StorybookVersion` from `cyo_adventure.db.models`) alongside the existing
`TYPE_CHECKING`-only `AsyncSession`/`uuid`:

```python
from sqlalchemy import func, select

from cyo_adventure.db.models import Storybook, StorybookVersion

if TYPE_CHECKING:
    import random
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession
```

```python
# How many of the family's most recent storybook_version rows to weight
# selection against (decision C-4: "proposed 20", ratified as the final
# value for WS-C PR2). A module constant, not configurable, so behavior is
# stable across restarts and does not need a settings round trip.
_RECENT_WINDOW = 20


async def recent_skeleton_usage(
    session: AsyncSession, family_id: uuid.UUID | None
) -> dict[str, int]:
    """Return {slug: count} of skeleton usage over the family's recent history.

    Args:
        session: An open async session.
        family_id: The request's owning family, or None for a family-less
            (admin/catalog) request.

    Returns:
        A recency-window usage count per slug; empty when family_id is None,
        the family has no storybook_version history, or every recent version
        has a null skeleton_slug (fresh_generation/import versions).
    """
    if family_id is None:
        return {}
    stmt = (
        select(StorybookVersion.skeleton_slug)
        .join(Storybook, Storybook.id == StorybookVersion.storybook_id)
        .where(Storybook.family_id == family_id)
        .order_by(StorybookVersion.created_at.desc())
        .limit(_RECENT_WINDOW)
    )
    result = await session.execute(stmt)
    counts: dict[str, int] = {}
    for (slug,) in result.all():
        if slug is None:
            continue
        counts[slug] = counts.get(slug, 0) + 1
    return counts
```

Drop the unused `func` import if the final code does not need it (it does not; `func.now()` is
not used here). Only import `select` from `sqlalchemy`.

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/integration/test_skeleton_recency.py -v`
Expected PASS: all four tests (requires Docker/testcontainers).

- [ ] **Step 4: Run the full backend gates**

Run: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: no failures, no lint or type errors.

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/generation/skeleton_match.py tests/integration/test_skeleton_recency.py
git commit -S -m "feat(generation): family recency query for skeleton weighting (WS-C PR2)"
```

---

### Task 6: authoring-plan integration (cell derivation, alternatives, override, warnings)

depends-on: Task3 [completion], Task4 [completion], Task5 [completion]

**Files:**

- Modify: `src/cyo_adventure/story_requests/authoring_plan.py`, `src/cyo_adventure/api/schemas.py`,
  `src/cyo_adventure/api/story_requests.py`
- Test: `tests/unit/test_authoring_plan.py`, `tests/integration/test_authoring_plan_api.py`

- [ ] **Step 1: Update `_FakeSession` first (mechanical, keeps existing tests running)**

`build_authoring_plan` is about to call `session.execute(...)` (via `recent_skeleton_usage`) for
the first time. In `tests/unit/test_authoring_plan.py`, extend `_FakeSession`:

```python
class _FakeResult:
    """A no-op result for the recent-usage query; every test starts with no history."""

    def all(self) -> list[tuple[str | None]]:
        return []


class _FakeSession:
    """Minimal async session double for build_authoring_plan.

    Mirrors the _FakeSession pattern in tests/unit/test_story_requests.py,
    extended with a singular ``scalar`` for the idempotency lookup and
    ``execute`` for the recency query (WS-C PR2).
    """

    def __init__(self, *, existing_job: GenerationJob | None = None) -> None:
        self._existing_job = existing_job
        self.added: list[object] = []

    async def scalar(self, statement: object) -> GenerationJob | None:
        """Return the seeded existing job (or None), ignoring the statement."""
        _ = statement
        return self._existing_job

    async def execute(self, statement: object) -> _FakeResult:
        """Return an empty recency result; every unit test starts with no history."""
        _ = statement
        return _FakeResult()

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Assign a UUID to any tracked object still missing an id."""
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()  # pyright: ignore[reportAttributeAccessIssue]
```

Run: `uv run pytest tests/unit/test_authoring_plan.py -v`
Expected PASS: unchanged (this step adds capability, does not change behavior yet).

- [ ] **Step 2: Write the new failing unit tests**

Append to `tests/unit/test_authoring_plan.py`:

```python
async def test_skeleton_fill_populates_alternatives() -> None:
    """The result carries every in-cell candidate, not just the pick."""
    session = _FakeSession()
    concept = _concept("8-11")
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
    )
    # 8-11/short/prose has exactly one production skeleton on disk today.
    assert result.skeleton_alternatives == ["the-cave-of-echoes"]
    assert result.skeleton_slug == "the-cave-of-echoes"


async def test_fresh_generation_has_no_alternatives() -> None:
    session = _FakeSession()
    result = await build_authoring_plan(
        session,
        _request(),
        _concept(),
        AuthoringPlanRequest(
            method="fresh_generation",
            mechanism="automated_provider",
            prep_model="openrouter/some-model",
        ),
    )
    assert result.skeleton_alternatives == []


async def test_skeleton_fill_honors_unconstrained_override() -> None:
    """An out-of-cell override is accepted with a warning, never blocked."""
    session = _FakeSession()
    concept = _concept("8-11")
    plan = AuthoringPlanRequest(
        method="skeleton_fill",
        mechanism="skill",
        prep_model="sonnet",
        skeleton_slug="the-sunspire-ascent",  # a real 13-16/medium/gamebook skeleton
    )
    result = await build_authoring_plan(session, _request(), concept, plan)
    assert result.skeleton_slug == "the-sunspire-ascent"
    assert any("outside the request's cell" in w for w in result.warnings)


async def test_skeleton_fill_override_unknown_slug_is_rejected() -> None:
    session = _FakeSession()
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept("8-11"),
            AuthoringPlanRequest(
                method="skeleton_fill",
                mechanism="skill",
                prep_model="sonnet",
                skeleton_slug="does-not-exist-anywhere",
            ),
        )


async def test_skeleton_fill_null_length_falls_back_to_short() -> None:
    """concept.brief with no "length" key at all still forms a cell (decision 3)."""
    session = _FakeSession()
    concept = Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={"age_band": "8-11", "premise": "a fox finds a lantern"},
    )
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
    )
    assert result.skeleton_slug == "the-cave-of-echoes"
```

Run: `uv run pytest tests/unit/test_authoring_plan.py -v`
Expected FAIL: `AttributeError: 'AuthoringPlanResult' object has no attribute
'skeleton_alternatives'` on the first new test; `AuthoringPlanRequest(...)` raises a pydantic
`ValidationError` on `skeleton_slug` (unexpected keyword, `extra="forbid"`) on the override
tests.

- [ ] **Step 3: Add `skeleton_slug` to `AuthoringPlanRequest` and `AlternativeView`/
  `skeleton_alternatives` to `AuthoringPlanResponse`**

In `src/cyo_adventure/api/schemas.py`, add before `AuthoringPlanRequest` (around line 573):

```python
class AlternativeView(BaseModel):
    """One in-cell, production-eligible skeleton the admin could pick instead."""

    slug: str
```

Add to `AuthoringPlanRequest` (after `review_stage2_model`):

```python
    skeleton_slug: str | None = None
```

Update its docstring with one sentence: `skeleton_slug` is an optional, unconstrained admin
override (decision C-6): any slug on disk is accepted, including a non-production-eligible or
out-of-cell one, with a warning surfaced on mismatch rather than a rejection.

Add to `AuthoringPlanResponse` (after `skeleton_slug`):

```python
    skeleton_alternatives: list[AlternativeView] = Field(default_factory=list)
```

- [ ] **Step 4: Rewrite `build_authoring_plan`'s skeleton_fill branch**

In `src/cyo_adventure/story_requests/authoring_plan.py`, replace the module-level import (from
Task 3 Step 4's interim patch):

```python
from cyo_adventure.generation.skeleton_match import candidates_for_cell
```

with:

```python
import random

from cyo_adventure.generation.skeleton_match import (
    candidates_for_cell,
    find_skeleton_metadata,
    recent_skeleton_usage,
    select_skeleton_for_cell,
    skeleton_matches_cell,
)
```

(`import random` is a genuine top-level import, not `TYPE_CHECKING`-only: `build_authoring_plan`
constructs a real `random.SystemRandom()` below.)

Add `from dataclasses import dataclass, field` (replacing the current `from dataclasses import
dataclass`), and extend `AuthoringPlanResult`:

```python
@dataclass(frozen=True, slots=True)
class AuthoringPlanResult:
    """Everything the endpoint needs to build its response.

    Attributes:
        job: The newly created (and flushed) GenerationJob row.
        skeleton_slug: The matched or overridden skeleton's slug, or None
            for fresh_generation.
        warnings: Non-blocking eligibility and override-mismatch warnings.
        skeleton_alternatives: Every in-cell production-eligible skeleton
            slug (WS-C PR2), or an empty list for fresh_generation.
    """

    job: GenerationJob
    skeleton_slug: str | None
    warnings: list[str]
    skeleton_alternatives: list[str] = field(default_factory=list)
```

Add the two fallback helpers right after `_band_of`:

```python
_DEFAULT_LENGTH = "short"
_DEFAULT_STYLE = "prose"


def _length_of(concept: Concept) -> str:
    """Return the concept brief's length, defaulting to "short" when null/absent.

    #ASSUME: data-integrity: request.length is nullable (WS-B #164);
    brief_from_request carries that null straight onto ConceptBrief.length,
    so concept.brief["length"] may be a literal JSON null, or the key may be
    absent entirely for a pre-length-field concept (both observed in
    existing test fixtures). Cell formation must always have a length axis
    to match against, so either case collapses to the band's default rather
    than failing to form a cell.
    #VERIFY: test_skeleton_fill_null_length_falls_back_to_short.
    """
    value = concept.brief.get("length") if isinstance(concept.brief, dict) else None
    return value if isinstance(value, str) else _DEFAULT_LENGTH


def _style_of(concept: Concept) -> str:
    """Return the concept brief's narrative_style, defaulting to "prose".

    ConceptBrief.narrative_style itself defaults to NarrativeStyle.PROSE, so
    a missing/malformed value here mirrors that same default rather than
    inventing a new one.
    """
    value = (
        concept.brief.get("narrative_style")
        if isinstance(concept.brief, dict)
        else None
    )
    return value if isinstance(value, str) else _DEFAULT_STYLE
```

Replace the entire skeleton_fill block (from Task 3 Step 4's interim patch) with:

```python
    band = _band_of(concept)
    skeleton_slug: str | None = None
    skeleton_alternatives: list[str] = []
    override_warnings: list[str] = []
    if method == "skeleton_fill":
        length = _length_of(concept)
        style = _style_of(concept)
        skeleton_alternatives = candidates_for_cell(band, length, style)
        if not skeleton_alternatives:
            msg = (
                f"no production-eligible skeleton available for band '{band}', "
                f"length '{length}', style '{style}'"
            )
            raise ValidationError(msg, field="band", value=band)
        if plan.skeleton_slug is not None:
            # #CRITICAL: security: the override is unconstrained (decision
            # C-6), but only among skeletons that actually exist on disk; an
            # unknown slug never silently proceeds as if it had matched.
            # #VERIFY: test_skeleton_fill_override_unknown_slug_is_rejected.
            override_metadata = find_skeleton_metadata(plan.skeleton_slug)
            if override_metadata is None:
                msg = f"skeleton_slug '{plan.skeleton_slug}' does not exist"
                raise ValidationError(
                    msg, field="skeleton_slug", value=plan.skeleton_slug
                )
            skeleton_slug = plan.skeleton_slug
            if not override_metadata.production_eligible:
                override_warnings.append(
                    f"skeleton_slug override '{skeleton_slug}' is not "
                    "production-eligible."
                )
            elif not skeleton_matches_cell(
                override_metadata, band=band, length=length, style=style
            ):
                override_warnings.append(
                    f"skeleton_slug override '{skeleton_slug}' is outside the "
                    f"request's cell (band='{band}', length='{length}', "
                    f"style='{style}')."
                )
        else:
            recent_usage = await recent_skeleton_usage(session, request.family_id)
            selection = select_skeleton_for_cell(
                skeleton_alternatives, recent_usage, random.SystemRandom()
            )
            skeleton_slug = selection.slug

    warnings = eligibility_warnings(method, mechanism, band, prep_model)
    warnings.extend(override_warnings)
```

Update `eligibility_warnings`'s call site: it already runs after `band` is computed, unchanged;
only the two lines above (assembling `warnings` from both sources) replace the prior single-line
`warnings = eligibility_warnings(...)`.

Finally, update the `return AuthoringPlanResult(...)` call at the function's end to add the new
field:

```python
    return AuthoringPlanResult(
        job=job,
        skeleton_slug=skeleton_slug,
        warnings=warnings,
        skeleton_alternatives=skeleton_alternatives,
    )
```

Update the function's own docstring: add a `Raises` line for the new unknown-override 422, and
extend the `Returns` line to mention `skeleton_alternatives`.

- [ ] **Step 5: Run the unit tests**

Run: `uv run pytest tests/unit/test_authoring_plan.py -v`
Expected PASS: every test in the file, including the five new ones.

- [ ] **Step 6: Wire the endpoint response**

In `src/cyo_adventure/api/story_requests.py`, add `AlternativeView,` to the `AuthoringPlanRequest`
import block (alphabetically, before `AuthoringPlanRequest,`), and change the
`create_authoring_plan` endpoint's return statement:

```python
    return AuthoringPlanResponse(
        request_id=str(request.id),
        concept_id=str(concept.id),
        job_id=str(result.job.id),
        method=body.method,
        mechanism=body.mechanism,
        status=cast("JobStatusLiteral", result.job.status),
        skeleton_slug=result.skeleton_slug,
        skeleton_alternatives=[
            AlternativeView(slug=slug) for slug in result.skeleton_alternatives
        ],
        warnings=result.warnings,
    )
```

Update the endpoint's docstring `Returns` line to mention `skeleton_alternatives`, and add one
`Raises` sentence: an unknown `skeleton_slug` override is a 422 (`ValidationError`).

- [ ] **Step 7: Write the failing integration test for the endpoint surface**

Append to `tests/integration/test_authoring_plan_api.py`:

```python
async def test_skeleton_fill_response_includes_alternatives(
    client: AsyncClient, seed: Seed
) -> None:
    """10-13/medium/prose has exactly one production skeleton on disk today."""
    req_id = await _approved_request_id(client, seed, "a lighthouse keeper returns")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={"method": "skeleton_fill", "mechanism": "skill", "prep_model": "sonnet"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["skeleton_slug"] == "the-hollow-lighthouse"
    assert body["skeleton_alternatives"] == [{"slug": "the-hollow-lighthouse"}]


async def test_skeleton_fill_override_out_of_cell_warns(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin override outside the request's cell is accepted, with a warning."""
    req_id = await _approved_request_id(client, seed, "a lantern in the fog")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "skill",
            "prep_model": "sonnet",
            "skeleton_slug": "the-cave-of-echoes",  # a real 8-11 skeleton, not 10-13
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["skeleton_slug"] == "the-cave-of-echoes"
    assert any("outside the request's cell" in w for w in body["warnings"])


async def test_skeleton_fill_override_unknown_slug_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    req_id = await _approved_request_id(client, seed, "a raincloud named gus")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "skill",
            "prep_model": "sonnet",
            "skeleton_slug": "does-not-exist-anywhere",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text
```

Run: `uv run pytest tests/integration/test_authoring_plan_api.py -v`
Expected FAIL (before Steps 3/6): `KeyError: 'skeleton_alternatives'` or a 500/422 mismatch;
after Steps 3-6 land, expected PASS.

- [ ] **Step 8: Run the full backend gates**

Run: `uv run pytest tests/ -x -q && uv run ruff check . && uv run basedpyright src/`
Expected: no failures, no lint or type errors.

- [ ] **Step 9: Commit**

```bash
git add src/cyo_adventure/story_requests/authoring_plan.py src/cyo_adventure/api/schemas.py \
  src/cyo_adventure/api/story_requests.py tests/unit/test_authoring_plan.py \
  tests/integration/test_authoring_plan_api.py
git commit -S -m "feat(story-requests): cell-aware skeleton pick, alternatives, and admin override (WS-C PR2)"
```

---

### Task 7: Client regeneration, CHANGELOG, and the full gate (Operational Task)

depends-on: Task6 [completion]

**Files:**

- Modify (generated): `frontend/src/client/`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Dump the OpenAPI schema and regenerate the client**

Command:

```bash
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" > /tmp/cyo-openapi.json
cd frontend && OPENAPI_INPUT="/tmp/cyo-openapi.json" npm run generate-client && cd ..
```

Expected: the command exits 0 and `git status --porcelain -- frontend/src/client` shows changes
(new `AlternativeView` type, `skeleton_slug` on the authoring-plan request type,
`skeleton_alternatives` on the response type).

Abort-if: the dump command fails (import error) -- fix the backend import before regenerating;
do not hand-edit `frontend/src/client/` to work around it.

- [ ] **Step 2: Verify no drift**

Command:

```bash
git diff --exit-code -- frontend/src/client || echo "drift present (expected here; will be staged)"
```

Expected: the diff is non-empty (this is the change we want staged), and running
`generate-client` a second time in a row produces no further diff (idempotent).

- [ ] **Step 3: Frontend gates**

Command: `cd frontend && npm run lint && npm run typecheck && npm run test:run && cd ..`
Expected: all pass (the client is generated code; no hand-written frontend logic in this PR
consumes the new fields yet, matching the spec's "no frontend UI beyond the mandatory
regenerated client" non-goal).

- [ ] **Step 4: Add the CHANGELOG entry**

Add to `CHANGELOG.md` under `## [Unreleased]` -> `### Added` (create the subsection if the
current `[Unreleased]` block does not yet have one):

```markdown
### Added
- Cell-aware skeleton matching for skeleton-fill authoring plans (WS-C PR 2): selection now
  matches the full ADR-011 `(age band, length, narrative style)` cell instead of band-only,
  weights the pick against the family's recently-used skeletons with a nonzero floor, and lets
  an admin override to any skeleton on disk (with a non-blocking warning on a non-production or
  out-of-cell pick). `AuthoringPlanResponse` now returns every in-cell alternative, and
  `storybook_version.skeleton_slug` records which skeleton produced each version.
```

- [ ] **Step 5: Run the full repo gate**

Command:

```bash
uv run pytest --cov=src --cov-fail-under=80 && uv run ruff check . && uv run ruff format --check . && \
  uv run basedpyright src/ && uv run bandit -r src && pre-commit run --all-files
```

Expected: all green. `pre-commit run --all-files` in particular re-checks the no-em-dash hook
across every file this plan touched.

Abort-if: coverage falls under 80% -- add the missing test case to the exact task above that
introduced the uncovered branch, do not add a blanket integration smoke test instead.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/client CHANGELOG.md
git commit -S -m "chore(frontend): regenerate OpenAPI client for cell-aware skeleton matching (WS-C PR2)"
```

---

## PR body disclosure checklist (fill in before opening the PR)

- [ ] Note the exact `<PR1_HEAD>` revision id this PR's migration chains onto, and confirm PR1
  is merged (not just rebased-onto in a stale local branch).
- [ ] Confirm no `e2e/` or `e2e-real/` spec changes were needed (verified in File structure
  above; re-verify if PR1 or another concurrent change added a frontend consumer of
  `/authoring-plan` in the interim).
- [ ] List the three new endpoint-observable behaviors for reviewers: cell-aware pick (band x
  length x style, not band-only), `skeleton_alternatives` in the response, and the unconstrained
  `skeleton_slug` override with its warning-not-block semantics.
- [ ] Flag the WS-D shared-file conflict risk named in the spec (`story_requests/authoring_plan.py`,
  `generation/worker.py`, `CHANGELOG.md`) for whichever of WS-C/WS-D merges second.
