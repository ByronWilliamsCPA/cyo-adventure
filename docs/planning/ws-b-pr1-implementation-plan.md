---
schema_type: planning
title: "WS-B PR 1: Enriched Child Flow Implementation Plan"
description: "Task-by-task implementation plan for WS-B PR 1: StoryRequest lifecycle columns with
  backfill, the brief derivation flip, the strict approve contract, and the guardian approve UI."
tags:
  - planning
  - architecture
  - story-requests
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an implementer with zero session context everything needed to build WS-B PR 1
  task by task against the approved spec."
component: Strategy
source: "docs/planning/ws-b-request-lifecycle-plan.md (spec); codebase discovery 2026-07-08 on
  feat/ws-b-request-lifecycle at 5fc4864."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Add `initiator_role`, `age_band`, `length`, `narrative_style` to `StoryRequest` (with backfill
and CHECK constraints, `profile_id` nullable), flip brief and moderation-context derivation from
the child profile to the request, require band/length at approval, and update the guardian
approve UI to send them.

## Architecture

One Alembic migration (add nullable, backfill, tighten to NOT NULL, constrain), then the
derivation flip in `brief.py`/`service.py`/`api/story_requests.py`, a new approve body schema,
and a per-row confirm strip in `RequestsPage.tsx`. The generated API client is regenerated from
an in-process schema dump. `ConceptBrief` already has optional `length`/`narrative_style`
fields; this PR populates them, it does not add them.

## Tech stack

FastAPI + Pydantic v2, async SQLAlchemy 2.x, Alembic, pytest (+ testcontainers via
`tests/integration/_migration_utils.py` and the `migration_pg_url` conftest fixture), React 19 +
Vitest + Playwright, `@hey-api/openapi-ts` client generation.

## Conventions that bind every task

- Branch: `feat/ws-b-request-lifecycle` (already exists; work on it directly).
- Signed conventional commits (`git commit -S`); stage only the files you changed; never
  `git add -A`. No em-dash characters anywhere.
- Run `uv run ruff format . && uv run ruff check .` and `uv run basedpyright src/` before each
  commit; `pre-commit run --files <changed files>` must pass.
- New/changed functions touching DB or auth need RAD markers per `src/cyo_adventure/CLAUDE.md`.
- Enum string literals: band values are `'3-5', '5-8', '8-11', '10-13', '13-16', '16+'`
  (`AgeBand`, `src/cyo_adventure/storybook/models.py:32`); `Length` is
  `'short', 'medium', 'long'` (`:126`); `NarrativeStyle` is `'prose', 'gamebook'` (`:140`).

---

### Task 1: Migration + ORM columns (TDD via migration round-trip test)

**Files:**
- Create: `migrations/versions/20260708_0900_add_story_request_lifecycle_fields.py`
- Modify: `src/cyo_adventure/db/models.py` (constants near line 46; `StoryRequest` class lines 340-406; move `_AGE_BAND_VALUES` from line 412 to the constants block)
- Test: `tests/integration/test_story_request_lifecycle_migration.py` (new)

- [ ] **Step 1: Write the failing migration test**

Use the shared helpers from `tests/integration/_migration_utils.py` (`PROJECT_ROOT`,
`run_alembic`) and the module-scoped `migration_pg_url` fixture from
`tests/integration/conftest.py` (postgres:16-alpine testcontainer; skips without Docker). Model
the file on `tests/integration/test_moderation_threshold_migration.py`. The test must:

```python
"""Round-trip and backfill tests for the WS-B story_request lifecycle migration."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

REVISION = "d0e1f2a3b4c5"
DOWN_REVISION = "c9d0e1f2a3b4"


def _env(pg_url: str) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["CYO_ADVENTURE_DATABASE_URL"] = pg_url
    return env


@pytest.fixture
def upgraded_engine(migration_pg_url: str) -> sa.engine.Engine:
    """Upgrade to the previous head, seed a legacy row, then upgrade to REVISION."""
    env = _env(migration_pg_url)
    result = run_alembic(PROJECT_ROOT, env, "upgrade", DOWN_REVISION)
    assert result.returncode == 0, result.stderr
    sync_url = migration_pg_url.replace("+asyncpg", "")
    engine = sa.create_engine(sync_url)
    with engine.begin() as conn:
        family_id = str(uuid.uuid4())
        profile_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                'INSERT INTO "user" (id, email, role) '
                "VALUES (:id, 'g@example.com', 'guardian')"
            ),
            {"id": user_id},
        )
        conn.execute(
            sa.text("INSERT INTO family (id, name) VALUES (:id, 'Fam')"),
            {"id": family_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO child_profile (id, family_id, display_name, age_band) "
                "VALUES (:id, :family_id, 'Kid', '8-11')"
            ),
            {"id": profile_id, "family_id": family_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO story_request (id, family_id, profile_id, request_text, status) "
                "VALUES (:id, :family_id, :profile_id, 'a fox story', 'pending')"
            ),
            {"id": str(uuid.uuid4()), "family_id": family_id, "profile_id": profile_id},
        )
    result = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr
    return engine


def test_backfill_band_from_profile_and_role_default(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT age_band, initiator_role, length, narrative_style FROM story_request")
        ).one()
    assert row.age_band == "8-11"
    assert row.initiator_role == "child"
    assert row.length is None
    assert row.narrative_style == "prose"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("initiator_role", "robot"),
        ("age_band", "2-4"),
        ("length", "epic"),
        ("narrative_style", "opera"),
    ],
)
def test_check_constraints_reject_bad_values(
    upgraded_engine: sa.engine.Engine, column: str, value: str
) -> None:
    with upgraded_engine.connect() as conn:
        family_id = conn.execute(sa.text("SELECT id FROM family")).scalar_one()
        profile_id = conn.execute(sa.text("SELECT id FROM child_profile")).scalar_one()
        defaults = {
            "id": str(uuid.uuid4()),
            "family_id": family_id,
            "profile_id": profile_id,
            "age_band": "8-11",
            "initiator_role": "child",
            "length": "short",
            "narrative_style": "prose",
        }
        defaults[column] = value
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO story_request "
                    "(id, family_id, profile_id, request_text, status, age_band, "
                    "initiator_role, length, narrative_style) "
                    "VALUES (:id, :family_id, :profile_id, 't', 'pending', :age_band, "
                    ":initiator_role, :length, :narrative_style)"
                ),
                defaults,
            )
        conn.rollback()


def test_gamebook_below_teen_band_rejected(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.connect() as conn:
        family_id = conn.execute(sa.text("SELECT id FROM family")).scalar_one()
        profile_id = conn.execute(sa.text("SELECT id FROM child_profile")).scalar_one()
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO story_request "
                    "(id, family_id, profile_id, request_text, status, age_band, "
                    "initiator_role, narrative_style) "
                    "VALUES (:id, :family_id, :profile_id, 't', 'pending', '8-11', "
                    "'child', 'gamebook')"
                ),
                {"id": str(uuid.uuid4()), "family_id": family_id, "profile_id": profile_id},
            )
        conn.rollback()


def test_downgrade_round_trip(migration_pg_url: str) -> None:
    env = _env(migration_pg_url)
    assert run_alembic(PROJECT_ROOT, env, "upgrade", REVISION).returncode == 0
    assert run_alembic(PROJECT_ROOT, env, "downgrade", DOWN_REVISION).returncode == 0
    assert run_alembic(PROJECT_ROOT, env, "upgrade", REVISION).returncode == 0
```

Before finalizing the seed SQL, open `migrations/versions/` for the tables' actual required
columns (`user`, `family`, `child_profile` may carry more NOT NULL columns; copy the seed
pattern used by `tests/integration/test_assignments_migration.py`, which already inserts these
parents). Adjust the INSERTs to match; keep the assertions unchanged.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/integration/test_story_request_lifecycle_migration.py -v`
Expected: FAIL (`alembic upgrade d0e1f2a3b4c5` fails: unknown revision).

- [ ] **Step 3: Write the migration**

Create `migrations/versions/20260708_0900_add_story_request_lifecycle_fields.py` (filename
template `%(year)d%(month).2d%(day).2d_%(hour).2d%(minute).2d_%(slug)s`), modeled on
`20260706_1600_add_moderation_threshold.py`:

```python
"""add story_request lifecycle fields (WS-B PR 1)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-08 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add lifecycle columns, backfill band from the profile, then constrain."""
    op.add_column(
        "story_request",
        sa.Column(
            "initiator_role",
            sa.String(length=16),
            server_default=sa.text("'child'"),
            nullable=False,
        ),
    )
    op.add_column(
        "story_request", sa.Column("age_band", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "story_request", sa.Column("length", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "story_request",
        sa.Column(
            "narrative_style",
            sa.String(length=16),
            server_default=sa.text("'prose'"),
            nullable=False,
        ),
    )
    # #CRITICAL: data integrity: every historical row must get a band before the
    # NOT NULL tightening; the moderation flag context reads it after the flip.
    # #VERIFY: test_backfill_band_from_profile_and_role_default.
    op.execute(
        "UPDATE story_request SET age_band = child_profile.age_band "
        "FROM child_profile WHERE story_request.profile_id = child_profile.id"
    )
    op.alter_column("story_request", "age_band", nullable=False)
    op.alter_column("story_request", "profile_id", nullable=True)
    op.create_check_constraint(
        "ck_story_request_initiator_role",
        "story_request",
        "initiator_role IN ('child', 'guardian', 'admin')",
    )
    op.create_check_constraint(
        "ck_story_request_age_band",
        "story_request",
        "age_band IN ('3-5', '5-8', '8-11', '10-13', '13-16', '16+')",
    )
    op.create_check_constraint(
        "ck_story_request_length",
        "story_request",
        "length IS NULL OR length IN ('short', 'medium', 'long')",
    )
    op.create_check_constraint(
        "ck_story_request_narrative_style",
        "story_request",
        "narrative_style IN ('prose', 'gamebook')",
    )
    op.create_check_constraint(
        "ck_story_request_style_band",
        "story_request",
        "narrative_style = 'prose' OR age_band IN ('13-16', '16+')",
    )


def downgrade() -> None:
    """Drop the WS-B lifecycle columns and restore profile_id NOT NULL."""
    op.drop_constraint("ck_story_request_style_band", "story_request", type_="check")
    op.drop_constraint(
        "ck_story_request_narrative_style", "story_request", type_="check"
    )
    op.drop_constraint("ck_story_request_length", "story_request", type_="check")
    op.drop_constraint("ck_story_request_age_band", "story_request", type_="check")
    op.drop_constraint(
        "ck_story_request_initiator_role", "story_request", type_="check"
    )
    op.alter_column("story_request", "profile_id", nullable=False)
    op.drop_column("story_request", "narrative_style")
    op.drop_column("story_request", "length")
    op.drop_column("story_request", "age_band")
    op.drop_column("story_request", "initiator_role")
```

- [ ] **Step 4: Update the ORM model**

In `src/cyo_adventure/db/models.py`:

1. Move the line `_AGE_BAND_VALUES = ", ".join(f"'{band.value}'" for band in AgeBand)` (currently
   line 412, with its two-line derivation comment) up into the module constants block after
   `_STORY_REQUEST_STATUS_VALUES` (near line 46). It must be defined before the `StoryRequest`
   class body evaluates. Confirm `AgeBand` is already imported at module top (it is, for
   `ModerationThreshold`); also import `Length` and `NarrativeStyle` are NOT needed here (string
   columns only).
2. Add alongside it:

```python
_STORY_REQUEST_INITIATOR_VALUES = "'child', 'guardian', 'admin'"
_STORY_REQUEST_LENGTH_VALUES = "'short', 'medium', 'long'"
_STORY_REQUEST_STYLE_VALUES = "'prose', 'gamebook'"
```

3. In `StoryRequest.__table_args__`, append after the status CheckConstraint:

```python
        CheckConstraint(
            f"initiator_role IN ({_STORY_REQUEST_INITIATOR_VALUES})",
            name="ck_story_request_initiator_role",
        ),
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_story_request_age_band",
        ),
        CheckConstraint(
            f"length IS NULL OR length IN ({_STORY_REQUEST_LENGTH_VALUES})",
            name="ck_story_request_length",
        ),
        CheckConstraint(
            f"narrative_style IN ({_STORY_REQUEST_STYLE_VALUES})",
            name="ck_story_request_narrative_style",
        ),
        CheckConstraint(
            "narrative_style = 'prose' OR age_band IN ('13-16', '16+')",
            name="ck_story_request_style_band",
        ),
```

4. Change `profile_id` to nullable and add the four columns after `request_text`:

```python
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), default=None
    )
    initiator_role: Mapped[str] = mapped_column(
        String(16), default="child", server_default="child"
    )
    age_band: Mapped[str] = mapped_column(String(16))
    length: Mapped[str | None] = mapped_column(String(16), default=None)
    narrative_style: Mapped[str] = mapped_column(
        String(16), default="prose", server_default="prose"
    )
```

`age_band` gets no default on purpose: every creation path must set it explicitly, and a missed
path fails loudly at flush. Update the class docstring Attributes list for the five changes.

- [ ] **Step 5: Run the migration test to verify it passes**

Run: `uv run pytest tests/integration/test_story_request_lifecycle_migration.py -v`
Expected: PASS (all 4 test functions; parametrized rejections included).

- [ ] **Step 6: Fix direct ORM constructions in existing tests**

`age_band` is now required at flush for rows built directly. Find them:

Run: `grep -rn "StoryRequest(" tests/ src/ --include='*.py' | grep -v "def \|#"`

For each direct construction (known: `tests/unit/test_story_requests.py`,
`tests/integration/test_story_requests_api.py`, `tests/integration/test_story_request_flag_thresholds.py`,
and `api/story_requests.py::create_story_request` which Task 4 rewrites), add
`age_band="<the band the test's profile uses>"` to the constructor call. Do not add `length`
(nullable) or `initiator_role`/`narrative_style` (defaulted).

Run: `uv run pytest tests/unit/test_story_requests.py tests/integration/test_story_requests_api.py tests/integration/test_story_request_flag_thresholds.py -v`
Expected: PASS (construction fixes only; behavior unchanged until Task 3).

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/20260708_0900_add_story_request_lifecycle_fields.py \
  src/cyo_adventure/db/models.py \
  tests/integration/test_story_request_lifecycle_migration.py \
  tests/unit/test_story_requests.py tests/integration/test_story_requests_api.py \
  tests/integration/test_story_request_flag_thresholds.py
git commit -S -m "feat(story-requests): add lifecycle columns with backfill (WS-B PR1)"
```

---

### Task 2: Approve body schema (depends-on: Task1 [completion])

**Files:**
- Modify: `src/cyo_adventure/api/schemas.py` (near StoryRequestCreateBody, line ~372)
- Test: `tests/unit/test_schemas_story_request_approve.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""Validation tests for the WS-B approve confirmation body."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import StoryRequestApproveBody
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle


def test_defaults_style_to_prose() -> None:
    body = StoryRequestApproveBody(age_band=AgeBand.BAND_8_11, length=Length.SHORT)
    assert body.narrative_style is NarrativeStyle.PROSE


def test_gamebook_allowed_for_teen_bands() -> None:
    body = StoryRequestApproveBody(
        age_band=AgeBand.BAND_13_16,
        length=Length.LONG,
        narrative_style=NarrativeStyle.GAMEBOOK,
    )
    assert body.narrative_style is NarrativeStyle.GAMEBOOK


def test_gamebook_rejected_below_teen_bands() -> None:
    with pytest.raises(PydanticValidationError, match="gamebook"):
        StoryRequestApproveBody(
            age_band=AgeBand.BAND_8_11,
            length=Length.SHORT,
            narrative_style=NarrativeStyle.GAMEBOOK,
        )


def test_length_is_required() -> None:
    with pytest.raises(PydanticValidationError):
        StoryRequestApproveBody(age_band=AgeBand.BAND_8_11)  # type: ignore[call-arg]
```

Check the exact enum member names first (`grep -n "class Length" -A 8
src/cyo_adventure/storybook/models.py`); use the declared members verbatim.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_schemas_story_request_approve.py -v`
Expected: FAIL with ImportError (StoryRequestApproveBody not defined).

- [ ] **Step 3: Add the schema**

In `api/schemas.py`, extend the existing `from cyo_adventure.storybook.models import ...`
import (or add one) to include `AgeBand, Length, NarrativeStyle`, ensure `model_validator` is
imported from pydantic, and add after `StoryRequestCreateBody`:

```python
_TEEN_BANDS = frozenset({AgeBand.BAND_13_16, AgeBand.BAND_16_PLUS})


class StoryRequestApproveBody(BaseModel):
    """Guardian confirmation required to approve a request (WS-B).

    The request becomes the source of truth for band and length at approval;
    ``narrative_style`` follows ADR-011: gamebook only for 13-16 and 16+.
    """

    model_config = ConfigDict(extra="forbid")

    age_band: AgeBand
    length: Length
    narrative_style: NarrativeStyle = NarrativeStyle.PROSE

    @model_validator(mode="after")
    def _style_allowed_for_band(self) -> "StoryRequestApproveBody":
        if self.narrative_style is NarrativeStyle.GAMEBOOK and self.age_band not in _TEEN_BANDS:
            msg = "narrative_style 'gamebook' requires age band 13-16 or 16+"
            raise ValueError(msg)
        return self
```

Do NOT extend `StoryRequestView` in this task; its new read fields land in Task 4 together
with the `_to_view` projection change, so every commit keeps the full suite green.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_schemas_story_request_approve.py tests/unit/ -v`
Expected: PASS (4 new tests; rest of the unit suite unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/api/schemas.py tests/unit/test_schemas_story_request_approve.py
git commit -S -m "feat(api): add story-request approve confirmation body (WS-B PR1)"
```

---

### Task 3: Derivation flip in brief and service (depends-on: Task2 [output])

**Files:**
- Modify: `src/cyo_adventure/story_requests/brief.py:58-92`
- Modify: `src/cyo_adventure/story_requests/service.py:73-139`
- Test: `tests/unit/test_story_requests.py` (existing tests updated + new)

- [ ] **Step 1: Update the unit tests first**

In `tests/unit/test_story_requests.py`:

1. `test_brief_from_request_uses_band_budget_and_generic_protagonist` (line ~51): call with a
   request row instead of text+profile:

```python
def test_brief_from_request_uses_band_budget_and_generic_protagonist() -> None:
    """The brief inherits band node/ending budgets and a generic protagonist."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
        length="short",
    )
    brief = brief_from_request(request, _profile("8-11"))
    assert isinstance(brief, ConceptBrief)
    assert brief.premise == "a story about a brave fox"
    assert brief.age_band == AgeBand.BAND_8_11
    assert brief.length == Length.SHORT
    assert brief.narrative_style == NarrativeStyle.PROSE
    assert brief.target_node_count == 15  # band_profile 8-11 min_nodes
    assert brief.ending_count == 3  # band_profile 8-11 min_endings
    assert brief.protagonist.name == "Explorer"  # never a real child name
    assert brief.tier == 1
```

2. Add two new tests:

```python
def test_brief_from_request_band_comes_from_request_not_profile() -> None:
    """The flip: a request band different from the profile band wins."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a mystery",
        status="pending",
        age_band="10-13",
    )
    brief = brief_from_request(request, _profile("8-11"))
    assert brief.age_band == AgeBand.BAND_10_13


def test_brief_from_request_without_profile_uses_band_reading_target() -> None:
    """A profile-less request (PR 2 flows) gets the band FK target."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        request_text="a space story",
        status="pending",
        age_band="8-11",
    )
    brief = brief_from_request(request, None)
    assert brief.reading_level_target == 4.0  # _BAND_FK_TARGET[8-11]
```

3. `test_approve_stamps_and_builds_brief_from_stored_text` (line ~233): the service call gains
   the confirmation values and the assertions gain the stamps:

```python
    concept_id = await service.approve_story_request(
        session,
        principal,
        request,
        age_band=AgeBand.BAND_8_11,
        length=Length.MEDIUM,
        narrative_style=NarrativeStyle.PROSE,
    )

    assert request.status == "approved"
    assert request.age_band == "8-11"
    assert request.length == "medium"
    assert request.narrative_style == "prose"
```

Add the needed imports (`AgeBand, Length, NarrativeStyle` from
`cyo_adventure.storybook.models`). Update every other `service.approve_story_request(...)`
call site in the file the same way (grep the file; use each test's profile band).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_story_requests.py -v`
Expected: FAIL with TypeError (unexpected keyword arguments / signature mismatch).

- [ ] **Step 3: Flip `brief_from_request`**

Replace the function in `brief.py` (keep module constants unchanged; update the module
docstring's first paragraph to say the band/length now come from the request):

```python
def brief_from_request(
    request: StoryRequest, profile: ChildProfile | None
) -> ConceptBrief:
    """Assemble a ConceptBrief for an approved request.

    Args:
        request: The approved story request; source of truth for premise,
            age band, length, and narrative style (WS-B derivation flip).
        profile: The requesting child's profile, or None for requests not
            tied to one child (guardian/admin initiated). Contributes only
            the reading-level cap; band never comes from here.

    Returns:
        ConceptBrief: A fully populated brief with a generic fictional
            protagonist and band-derived structural budgets.
    """
    # #CRITICAL: data integrity: request.age_band is the single source of truth
    # after the WS-B flip; the migration backfilled every historical row.
    # #VERIFY: test_brief_from_request_band_comes_from_request_not_profile.
    age_band = AgeBand(request.age_band)
    band = profile_for(request.age_band)
    node_count = band.min_nodes if band is not None else _FALLBACK_NODES
    ending_count = band.min_endings if band is not None else _FALLBACK_ENDINGS
    reading_target = (
        profile.reading_level_cap
        if profile is not None and profile.reading_level_cap < _READING_CAP_SENTINEL
        else _BAND_FK_TARGET[age_band]
    )
    return ConceptBrief(
        premise=request.request_text,
        protagonist=Protagonist(
            name=_DEFAULT_PROTAGONIST_NAME,
            age=_BAND_PROTAGONIST_AGE[age_band],
            role=_DEFAULT_PROTAGONIST_ROLE,
        ),
        age_band=age_band,
        reading_level_target=reading_target,
        tier=1,
        tone="gentle",
        target_node_count=node_count,
        ending_count=ending_count,
        structure_pattern=StructurePattern.BRANCH_AND_BOTTLENECK,
        length=Length(request.length) if request.length is not None else None,
        narrative_style=NarrativeStyle(request.narrative_style),
    )
```

Imports: add `Length, NarrativeStyle` to the existing `storybook.models` import; move
`StoryRequest` into the TYPE_CHECKING import next to `ChildProfile`.

- [ ] **Step 4: Update `approve_story_request`**

In `service.py`, change the signature and body (docstring Args updated to match):

```python
async def approve_story_request(
    session: AsyncSession,
    principal: Principal,
    request: StoryRequest,
    *,
    age_band: AgeBand,
    length: Length,
    narrative_style: NarrativeStyle,
) -> str:
```

After `ensure_pending(request)` and the profile load (profile load becomes conditional), stamp
before building the brief:

```python
    ensure_pending(request)
    profile: ChildProfile | None = None
    if request.profile_id is not None:
        profile = await session.get(ChildProfile, request.profile_id)
        if profile is None:
            msg = "requesting profile no longer exists"
            raise ResourceNotFoundError(msg)

    # WS-B: the guardian's confirmation is stamped onto the request BEFORE the
    # brief builds, keeping the request the single source of truth from here on.
    request.age_band = age_band.value
    request.length = length.value
    request.narrative_style = narrative_style.value

    brief = brief_from_request(request, profile)
```

The rest of the function (PII backstop, Concept creation, status stamps) is unchanged. Add
`from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle` (runtime import;
the enums are used at runtime).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_story_requests.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/story_requests/brief.py src/cyo_adventure/story_requests/service.py \
  tests/unit/test_story_requests.py
git commit -S -m "feat(story-requests): flip brief derivation to the request (WS-B PR1)"
```

---

### Task 4: API endpoints: strict approve, band stamp at creation, join removal (depends-on: Task3 [output])

**Files:**
- Modify: `src/cyo_adventure/api/story_requests.py` (create endpoint ~234-291, list ~294-350, approve ~397-433, `_to_view`/`_FlagContext` ~97-232)
- Test: `tests/integration/test_story_requests_api.py`, `tests/integration/test_story_request_flag_thresholds.py`

- [ ] **Step 1: Write/adjust the failing integration tests**

In `tests/integration/test_story_requests_api.py` add:

```python
async def test_approve_without_body_returns_422(
    client: AsyncClient, seed: Seed
) -> None:
    """WS-B strict contract: approval requires band and length."""
    request_id = await _create_pending_request(client, seed)
    resp = await client.post(
        f"/api/v1/story-requests/{request_id}/approve",
        headers=auth(seed.guardian_token),
        json={},
    )
    assert resp.status_code == 422


async def test_approve_with_confirmation_stamps_request(
    client: AsyncClient, seed: Seed, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    request_id = await _create_pending_request(client, seed)
    resp = await client.post(
        f"/api/v1/story-requests/{request_id}/approve",
        headers=auth(seed.guardian_token),
        json={"age_band": "8-11", "length": "medium", "narrative_style": "prose"},
    )
    assert resp.status_code == 200
    async with sessionmaker() as session:
        row = await session.get(StoryRequest, uuid.UUID(request_id))
        assert row is not None
        assert row.age_band == "8-11"
        assert row.length == "medium"


async def test_gamebook_below_teen_band_rejected_at_approve(
    client: AsyncClient, seed: Seed
) -> None:
    request_id = await _create_pending_request(client, seed)
    resp = await client.post(
        f"/api/v1/story-requests/{request_id}/approve",
        headers=auth(seed.guardian_token),
        json={"age_band": "8-11", "length": "short", "narrative_style": "gamebook"},
    )
    assert resp.status_code == 422


async def test_create_stamps_band_from_profile_and_child_role(
    client: AsyncClient, seed: Seed, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    request_id = await _create_pending_request(client, seed)
    async with sessionmaker() as session:
        row = await session.get(StoryRequest, uuid.UUID(request_id))
        assert row is not None
        assert row.age_band == seed.profile_age_band
        assert row.initiator_role == "child"
```

Before writing these, read the file's existing helper for creating a pending request and its
fixture names (`Seed`, `auth`, sessionmaker fixture); reuse them verbatim rather than the
sketched `_create_pending_request`/`seed.profile_age_band` names, which are illustrative. Update
every existing approve call in this file and in
`tests/integration/test_story_request_flag_thresholds.py` to send the JSON confirmation body
(band = the seeded profile's band, length "medium", style "prose").

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/integration/test_story_requests_api.py -v`
Expected: new tests FAIL (approve accepts empty body today; no stamps).

- [ ] **Step 3: Implement the endpoint changes**

In `api/story_requests.py`:

1. Approve endpoint gains the body and passes enums through:

```python
@router.post("/story-requests/{request_id}/approve")
async def approve_story_request_endpoint(
    request_id: str, body: StoryRequestApproveBody, ctx: Context
) -> StoryRequestApprovedView:
```

and the service call becomes:

```python
    concept_id = await service.approve_story_request(
        ctx.session,
        ctx.principal,
        request,
        age_band=body.age_band,
        length=body.length,
        narrative_style=body.narrative_style,
    )
```

Import `StoryRequestApproveBody` alongside the other schema imports. Docstring: add
`body: The guardian's band/length/style confirmation (WS-B).` and note the 422 on a
gamebook/band mismatch.

2. Create endpoint stamps band and role. After `authorize_profile(...)` add:

```python
    profile = await ctx.session.get(ChildProfile, profile_uuid)
    if profile is None:
        msg = "profile not found"
        raise ResourceNotFoundError(msg)
```

and extend the constructor:

```python
    request = StoryRequest(
        family_id=ctx.principal.family_id,
        profile_id=profile_uuid,
        request_text=body.request_text,
        status=status,
        moderation_flags=flags_payload,
        age_band=profile.age_band,
        initiator_role="child",
    )
```

(`ChildProfile` and `ResourceNotFoundError` are already imported in this module; verify with a
grep and add if not.)

3. List endpoint: remove the `ChildProfile` join (and its `#EDGE` comment); the statement
becomes `select(StoryRequest).order_by(StoryRequest.created_at.desc())`, iteration becomes
`rows = (await ctx.session.scalars(stmt)).all()`, and the projection call becomes
`_to_view(request, policy=policy, surface_all=ctx.principal.is_admin)`.

4. Extend `StoryRequestView` in `api/schemas.py` (line ~393) with the new read fields so the
guardian UI can prefill (moved here from Task 2 so the suite stays green between tasks; add the
`AgeBand, Length, NarrativeStyle` import to schemas.py if Task 2 did not already):

```python
    initiator_role: Literal["child", "guardian", "admin"]
    age_band: AgeBand
    length: Length | None
    narrative_style: NarrativeStyle
```

5. `_FlagContext.age_band` docstring changes to "The request's age band (WS-B: request-sourced,
backfilled for historical rows)". `_to_view` drops its `age_band` parameter and uses
`request.age_band` when building `_FlagContext`, and the returned view gains the new fields:

```python
    return StoryRequestView(
        id=str(request.id),
        profile_id=str(request.profile_id) if request.profile_id is not None else "",
        status=cast("StoryRequestStatus", request.status),
        request_text=None if request.status == "blocked" else request.request_text,
        moderation_flags=flags,
        created_at=request.created_at,
        initiator_role=cast(
            "Literal['child', 'guardian', 'admin']", request.initiator_role
        ),
        age_band=AgeBand(request.age_band),
        length=Length(request.length) if request.length is not None else None,
        narrative_style=NarrativeStyle(request.narrative_style),
    )
```

Decision point encoded here: `StoryRequestView.profile_id` stays `str` in PR 1 (empty string is
unreachable until PR 2 creates profile-less rows; PR 2 changes the field to `str | None`).
Import `AgeBand, Length, NarrativeStyle` from `cyo_adventure.storybook.models`.

- [ ] **Step 4: Run the integration suites**

Run: `uv run pytest tests/integration/test_story_requests_api.py tests/integration/test_story_request_flag_thresholds.py tests/unit/ -v`
Expected: PASS.

- [ ] **Step 5: Run the FULL backend suite (post-refactor rule)**

Run: `uv run pytest --cov=src --cov-fail-under=80 -q`
Expected: PASS at >= 80% coverage. Other modules construct StoryRequest rows in fixtures
(authoring-plan and generation tests may seed requests); fix any missed `age_band=` the same
way as Task 1 Step 6.

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/api/story_requests.py tests/integration/test_story_requests_api.py \
  tests/integration/test_story_request_flag_thresholds.py
git commit -S -m "feat(api): strict approve contract + request-sourced band (WS-B PR1)"
```

---

### Task 5: Regenerate the OpenAPI client (depends-on: Task4 [output])

**Files:**
- Modify: `frontend/src/client/*` (generated; never hand-edit)

- [ ] **Step 1: Dump the schema in-process and regenerate**

Run:
```bash
cd /home/byron/dev/CYO_Adventure && uv run python -c "
import json
from cyo_adventure.app import app
print(json.dumps(app.openapi()))
" > /tmp/claude-1000/-home-byron-dev-CYO-Adventure/94ba09fb-ad7f-4e4b-a4d8-8e5454331cad/scratchpad/openapi.json
cd frontend && OPENAPI_INPUT=/tmp/claude-1000/-home-byron-dev-CYO-Adventure/94ba09fb-ad7f-4e4b-a4d8-8e5454331cad/scratchpad/openapi.json npm run generate-client
```
Expected: `src/client/types.gen.ts` gains `StoryRequestApproveBody` and the new
`StoryRequestView` fields. Verify the import path for the app module first
(`grep -rn "app = FastAPI" src/cyo_adventure/` to confirm `cyo_adventure.app`); if the
attribute lives elsewhere (e.g. `main.py`), use that module path.
Abort if: the dump prints a Python traceback (schema regression; fix before continuing).

- [ ] **Step 2: Typecheck against the regenerated client**

Run: `cd frontend && npm run typecheck`
Expected: FAILS in `storyRequestQueueApi.ts`/`RequestsPage.tsx` only if those files reference
changed generated types (they define local types today, so expect PASS; treat any failure
outside `src/client/` as Task 6 work arriving early, not a regeneration problem).

- [ ] **Step 3: Commit**

```bash
cd /home/byron/dev/CYO_Adventure
git add frontend/src/client
git commit -S -m "chore(frontend): regenerate API client for WS-B PR1 contract"
```

---

### Task 6: Guardian approve UI (depends-on: Task5 [completion])

**Files:**
- Modify: `frontend/src/guardian/storyRequestQueueApi.ts`
- Modify: `frontend/src/guardian/RequestsPage.tsx`
- Test: `frontend/src/guardian/RequestsPage.test.tsx`

- [ ] **Step 1: Update the adapter and its local types**

In `storyRequestQueueApi.ts`, extend the local `StoryRequestView` type with
`initiator_role: 'child' | 'guardian' | 'admin'`, `age_band: string`,
`length: string | null`, `narrative_style: string`, add:

```typescript
export type StoryRequestApproveBody = {
  age_band: string
  length: string
  narrative_style: string
}
```

and change approve to:

```typescript
    async approve(
      id: string,
      body: StoryRequestApproveBody
    ): Promise<StoryRequestApproved> {
      const res = await api.post<StoryRequestApproved>(
        `/v1/story-requests/${id}/approve`,
        body
      )
      return res.data
    },
```

Update the `StoryRequestQueueApi` interface signature to match.

- [ ] **Step 2: Write the failing component tests**

In `RequestsPage.test.tsx` (reuse the existing `mockGet`/`mockPost` pattern and the seeded
pending request the file already renders; extend the mock row with
`initiator_role: 'child'`, `age_band: '8-11'`, `length: null`, `narrative_style: 'prose'`):

```typescript
it('approve is disabled until a length is chosen, then sends the confirmation body', async () => {
  mockPost.mockResolvedValue({
    data: { id: 'req-1', status: 'approved', concept_id: 'concept-1' },
  })
  render(<RequestsPage />)
  await screen.findByText('A story about a friendly dragon')
  const approveButton = screen.getByRole('button', { name: 'Approve' })
  expect(approveButton).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Story length'), {
    target: { value: 'medium' },
  })
  expect(approveButton).toBeEnabled()
  fireEvent.click(approveButton)
  await waitFor(() =>
    expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/approve', {
      age_band: '8-11',
      length: 'medium',
      narrative_style: 'prose',
    })
  )
})

it('style select renders only for teen bands', async () => {
  // seed the mock list with age_band: '13-16'
  render(<RequestsPage />)
  await screen.findByText('A story about a friendly dragon')
  expect(screen.getByLabelText('Story style')).toBeInTheDocument()
})
```

For the second test, set the mocked GET row's `age_band` to `'13-16'` in that test's own mock
setup; the first test's `'8-11'` row must NOT render the style select
(`queryByLabelText('Story style')` returns null; add that assertion to the first test).

- [ ] **Step 3: Run to verify failure**

Run: `cd frontend && npx vitest run src/guardian/RequestsPage.test.tsx`
Expected: FAIL (no length select exists; approve enabled immediately).

- [ ] **Step 4: Implement the confirm strip**

In `RequestsPage.tsx` add per-row decision state and selects. State:

```typescript
type RowDecision = { age_band: string; length: string; narrative_style: string }
const [decisions, setDecisions] = useState<Record<string, RowDecision>>({})

const TEEN_BANDS = ['13-16', '16+']
const AGE_BANDS = ['3-5', '5-8', '8-11', '10-13', '13-16', '16+']
const LENGTHS = ['short', 'medium', 'long']

function decisionFor(req: StoryRequestView): RowDecision {
  return (
    decisions[req.id] ?? {
      age_band: req.age_band,
      length: '',
      narrative_style: 'prose',
    }
  )
}
```

`setDecision` (band changes force prose for non-teen bands, ADR-011):

```typescript
function setDecision(req: StoryRequestView, patch: Partial<RowDecision>) {
  setDecisions((prev) => {
    const current = prev[req.id] ?? {
      age_band: req.age_band,
      length: '',
      narrative_style: 'prose',
    }
    const next = { ...current, ...patch }
    if (!TEEN_BANDS.includes(next.age_band)) next.narrative_style = 'prose'
    return { ...prev, [req.id]: next }
  })
}
```

In the row JSX, inside `console-row__actions` before the Approve button (labels must match the
test's `getByLabelText` strings exactly):

```tsx
<label>
  Age band
  <select
    value={decision.age_band}
    onChange={(e) => setDecision(req, { age_band: e.target.value })}
  >
    {AGE_BANDS.map((b) => (
      <option key={b} value={b}>
        {b}
      </option>
    ))}
  </select>
</label>
<label>
  Story length
  <select
    value={decision.length}
    onChange={(e) => setDecision(req, { length: e.target.value })}
  >
    <option value="">Choose…</option>
    {LENGTHS.map((l) => (
      <option key={l} value={l}>
        {l}
      </option>
    ))}
  </select>
</label>
{TEEN_BANDS.includes(decision.age_band) ? (
  <label>
    Story style
    <select
      value={decision.narrative_style}
      onChange={(e) => setDecision(req, { narrative_style: e.target.value })}
    >
      <option value="prose">prose</option>
      <option value="gamebook">gamebook</option>
    </select>
  </label>
) : null}
```

with `const decision = decisionFor(req)` computed alongside `isInFlight`, the Approve button
gaining `disabled={isInFlight || !isActionable || decision.length === ''}`, and:

```typescript
async function approve(req: StoryRequestView) {
  const decision = decisionFor(req)
  await runRowAction(req.id, () => queueApi.approve(req.id, decision))
}
```

Follow the existing accessible-markup patterns in the file (the `<label>` wrapping shown gives
`getByLabelText` its accessible name); match the file's className conventions for the new strip
(reuse `console-row__actions` spacing or add a `console-row__confirm` class in the co-located
stylesheet if one exists; check with `grep -rn "console-row" frontend/src/`).

- [ ] **Step 5: Run the component tests, then the full frontend gate**

Run: `cd frontend && npx vitest run src/guardian/RequestsPage.test.tsx`
Expected: PASS.
Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run`
Expected: PASS (fix any other component tests that render RequestsPage rows without the new
fields by extending their mock rows).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/guardian/storyRequestQueueApi.ts frontend/src/guardian/RequestsPage.tsx \
  frontend/src/guardian/RequestsPage.test.tsx
git commit -S -m "feat(frontend): guardian approve confirmation (band/length/style) (WS-B PR1)"
```

---

### Task 7: e2e updates, both tiers (depends-on: Task6 [output])

**Files:**
- Modify: `frontend/e2e/story-requests.spec.ts`, `frontend/e2e/guardian-review.spec.ts` (if it approves), `frontend/e2e/naive-user/*.spec.ts` (only if they click Approve)
- Modify: `frontend/e2e-real/approval-flow.spec.ts`

- [ ] **Step 1: Find every Approve interaction in both tiers**

Run: `grep -rn "Approve" frontend/e2e/ frontend/e2e-real/`
Expected: a list of specs clicking the Approve button and any route mocks for
`/v1/story-requests`. Every mocked list response needs the four new fields
(`initiator_role`, `age_band`, `length`, `narrative_style`); every Approve click needs a
preceding length selection:

```typescript
await page.getByLabel('Story length').selectOption('medium')
await page.getByRole('button', { name: 'Approve' }).click()
```

For mocked-tier specs asserting the approve request payload, extend the assertion to the JSON
body. For `e2e-real/approval-flow.spec.ts` the same two-line interaction change applies (the
real backend now requires the body; the UI sends it).

- [ ] **Step 2: Run the mocked tier**

Run: `cd frontend && npm run test:e2e`
Expected: PASS.

- [ ] **Step 3: Run the real tier if the local stack is up; otherwise record it as a pre-merge step**

Run: `cd frontend && npm run test:e2e:real`
Expected: PASS with the local backend + db running (see repo CLAUDE.md "Local run recipe").
Abort if: failures implicate the new contract (fix before commit); infra-unavailable skips are
acceptable and must be noted in the PR body.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e frontend/e2e-real
git commit -S -m "test(e2e): approve flow sends band/length confirmation (WS-B PR1)"
```

---

### Task 8: CHANGELOG, gates, PR (depends-on: Task7 [completion])

- [ ] **Step 1: CHANGELOG entry**

Add under Unreleased/Added in `CHANGELOG.md` (entry-or-label gate requires it; this PR is a
feature, so an entry, not the label):

```markdown
- Story requests carry `initiator_role`, `age_band`, `length`, and `narrative_style`;
  guardians confirm band and length at approval, and generation reads them from the
  request instead of the child profile (WS-B PR 1).
```

- [ ] **Step 2: Full local gate sweep**

Run:
```bash
uv run pytest --cov=src --cov-fail-under=80 -q && uv run ruff check . && \
uv run basedpyright src/ && uv run bandit -r src -q && \
cd frontend && npm run lint && npm run typecheck && npm run test:run && cd .. && \
pre-commit run --all-files
```
Expected: all PASS.
Abort if: any gate fails (fix root cause; never suppress).

- [ ] **Step 3: Push and open the PR (after explicit user approval to push)**

PR title: `feat(story-requests): enriched child flow with request-sourced band/length (WS-B PR 1)`.
Body: summary of the four changes, the backfill note, breaking-contract note (approve body now
required; UI updated in the same PR), spec/plan links, test evidence. Do NOT enable auto-merge;
the owner merges.

---

## Self-review record

- Spec clause coverage: request columns + CHECKs + backfill (Task 1), profile_id nullable
  (Task 1), strict approve contract + 422s (Tasks 2/4), gamebook band rule at DB (Task 1) and
  schema (Task 2), derivation flip in brief (Task 3), moderation context flip + join removal
  (Task 4), ConceptBrief length/style population (Task 3), kid create stamps band + child role
  (Task 4), approve UI in same PR (Task 6), e2e both tiers (Task 7), client regen (Task 5),
  flag-threshold re-pin (Task 4), CHANGELOG (Task 8). PR 2/3 clauses intentionally out of scope.
- Known sketches an implementer must resolve against the real files (called out inline):
  integration-test fixture names (Task 4 Step 1), migration seed SQL columns (Task 1 Step 1),
  app module path for the schema dump (Task 5), stylesheet class names (Task 6).
- Type consistency: `approve_story_request` keyword-only enums used identically in Tasks 3/4;
  `StoryRequestApproveBody` field names match the UI body keys and the migration CHECK values.
