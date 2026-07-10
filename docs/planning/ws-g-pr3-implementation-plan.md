---
schema_type: planning
title: "WS-G PR 3: Generation Continuity Implementation Plan"
description: "Task-by-task implementation plan for WS-G PR 3: AnchorContext variable names, the
  continuation instruction in the structure prompt, template accuracy fixes, the F11 worker-path
  integration tests, and the client regeneration."
tags:
  - planning
  - series
  - implementation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give a zero-context implementer everything needed to build WS-G PR 3 (spec section 5 of
  docs/planning/ws-g-series-chaining-spec.md, plus the F11 worker-path test deferred from PR 1's
  review) as bite-sized TDD tasks with complete code, exact commands, and the discovery facts that
  must not be re-derived."
component: Generation
source: "docs/planning/ws-g-series-chaining-spec.md section 5 (ratified 2026-07-09); PR #184 review
  finding F11/F7 (issuecomment-4935226310); codebase discovery 2026-07-10 against origin/main
  6c42867 (post WS-G PR 2 #192)."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Close out WS-G: give continuation (series-anchored) generation jobs the anchor book's declared
variable names and a prompt instruction to reuse them, so PR 2's name-matched var-state seeding
lands on real carryover for tier-2 books; and add the F11 integration tests that drive the REAL
`_persist_and_moderate` worker path (repair round-trip and embed-failure rollback).

## Architecture

`AnchorContext` (a deterministic extraction from the anchor's published blob, embedded in
`ConceptBrief`) gains a `variable_names` field read from the blob's top-level `variables` array.
The brief is injected wholesale into the Stage A prompt (`model_dump_json`), so the new field
reaches the model automatically; the template change tells the model what to do with it. No DB
migration, no new endpoint. The field changes the OpenAPI contract (AnchorContext rides in
ConceptBrief), so the generated frontend client must be regenerated and committed.

## Tech Stack

FastAPI + Pydantic v2 (backend), pytest + testcontainers Postgres (integration tests),
@hey-api/openapi-ts (client regen). No new dependencies.

---

## Key facts an implementer must not re-derive

1. **The anchor blob DOES carry declared variables.** The Storybook document schema has a
   top-level `variables: list[Variable]` field (`src/cyo_adventure/storybook/models.py:470`);
   `Variable` (models.py:244-258) = `{name, type, initial, min, max, description}` with
   `name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")`. An earlier exploration report claimed
   variables live only in `Concept.brief`; that claim is WRONG. Extraction is a pure blob read.
2. **AnchorContext** lives at `src/cyo_adventure/generation/concept.py:170-186` with fields
   `title`, `character_names: list[_BoundedText]` (max 5 items), `ending_summary` (max 600).
   `_BoundedText` (concept.py:40) = `Annotated[str, StringConstraints(min_length=1, max_length=200)]`.
   `model_config = ConfigDict(extra="forbid")`.
3. **Extraction site**: `src/cyo_adventure/story_requests/anchoring.py::anchor_context_from_blob`
   (lines 187-221), a pure function; module constants at lines 34-38 (`_MAX_ENDING_EXCERPTS = 3`,
   `_EXCERPT_CHARS = 150`, `_SUMMARY_CHARS = 600`, `_TITLE_CHARS = 200`,
   `_MAX_CHARACTER_NAMES = 5`). House defensive style: `isinstance` checks, degrade to a safe
   default, never raise on a malformed blob (the function's docstring cites
   `api/library.py::_library_item` as the pattern). New extraction code MUST follow it: a
   malformed `variables` entry is skipped, an overlong name is truncated, never a raise.
4. **Prompt injection is wholesale**: `build_structure_prompt`
   (`src/cyo_adventure/generation/prompts.py:274-308`) replaces `{concept_brief}` with
   `brief.model_dump_json(indent=2)`, so `variable_names` reaches the user block automatically.
   `StagePrompt` (prompts.py:72-84) has `.system` (text before the `<!-- @user -->` marker in the
   template) and `.user` (after). The "Your Task" section of `structure.md` lands in `.system`.
5. **structure.md stale spots to fix while editing it** (all verified against
   `storybook/models.py` on 6c42867):
   - Task item 1 (lines 27-31) lists the `metadata` block WITHOUT `topology`, but
     `StoryMetadata` requires it (PR 2's a49c178 lesson: missing required metadata fields fail
     `Storybook.model_validate`). `reading_level` is an object `{scheme, target}`, not a scalar.
   - Task item 4's ending bullet (lines 52-53) says ending nodes carry `type`
     (`success`/`failure`/`bittersweet`/`open`). The enforced `Ending` model (models.py:408-416)
     has NO `type` field: it requires `kind` from `EndingKind`
     (`success|setback|death|capture|completion|discovery`, models.py:97-105) AND `valence` from
     `Valence` (`positive|neutral|negative`, models.py:89-94). The injected `{schema_rules}` JSON
     Schema is why generation works today despite the contradiction; fixing the instruction text
     removes wasted repair cycles.
6. **Worker path**: `_persist_and_moderate` (`src/cyo_adventure/generation/worker.py:461-614`)
   runs `persist_storybook` then `link_series_position`, then inside one `try`:
   `run_moderation_pipeline` then `embed_series_block` (embed AFTER moderation is a #CRITICAL
   ordering invariant; see the RAD marker at worker.py:552-576). The `except` path calls
   `session.rollback()`, re-fetches the job row, and calls `_record_failure` (which COMMITS the
   failure; see its docstring "record the truncated error, and commit"), then re-raises. The
   HAPPY path does NOT commit; the caller does (worker.py, end of `run_generation_job`). Any test
   driving `_persist_and_moderate` directly must commit afterward to make the write durable.
   `_PersistContext` (worker.py:430-458) is a frozen dataclass:
   `{job_id: uuid.UUID, job_row: GenerationJob, concept_row: Concept, effective_provider,
   authoring: dict | None, pii: PiiContext}`. `worker._default_settings` is the global `settings`
   singleton imported at worker.py:33 (`from cyo_adventure.core.config import settings as
   _default_settings`); monkeypatch it on the worker module for a deterministic
   `review_provider="mock"`.
7. **GenerationOutcome** (`src/cyo_adventure/generation/orchestrator.py:100-121`):
   `GenerationOutcome(status="passed", storybook=<dict>, report=<dict>, attempts=0,
   stage_log=[...])`. `_should_persist_storybook` persists `"passed"` outcomes (and
   `"needs_review"` only with `stage1_fidelity_violations` in the report).
8. **The existing regression test to model on**:
   `tests/integration/test_series_link.py::test_embed_series_block_survives_moderation_repair`
   (lines 457-596). It seeds Family, User, Series (`carries_state=True`), Concept (`brief={}`),
   StoryRequest (linking concept + series), then monkeypatches on
   `cyo_adventure.moderation.pipeline` (imported there as `pipeline_mod`):
   `run_classifiers`/`run_safety_stage`/`run_coherence_stage`/`run_engagement_stage` to
   `AsyncMock(return_value=[])`, `run_readability_stage` to
   `AsyncMock(side_effect=[[flag_finding], []])` (first call FLAGs, post-repair call clean), and
   `attempt_repair` to return a revised blob carrying NO `metadata.series`. These patches work
   identically when the pipeline is entered via `_persist_and_moderate`, because they patch the
   functions run_moderation_pipeline calls internally. PR #184 review F7/F11: that test
   REPLICATES the worker's call sequence instead of driving it, so a reorder of the real calls
   fails nothing. This plan's Task 3 fixes that.
9. **Test fixtures and imports that exist** (verified): `sessions` fixture
   (`async_sessionmaker[AsyncSession]`) in `tests/integration/conftest.py`; `_pii()` helper and
   `_CANNED_STORY` import (`from cyo_adventure.generation.provider import _CANNED_STORY`) already
   in `test_series_link.py`; `MockProvider` from `cyo_adventure.generation.provider`
   (`MockProvider(responses=[])`, has a `name` attribute so `_provider_label` works); minimal job
   seeding is `GenerationJob(concept_id=concept.id, status="queued")`
   (`tests/integration/test_generation_worker.py:225-228`); `minimal_brief` fixture in
   `tests/unit/test_prompts.py` (lines 51-66). Test conventions per `tests/CLAUDE.md`:
   `@pytest.mark.asyncio` per test, strict typing on fixtures/helpers, unit tests never hit a DB.
10. **Client regen without a live server** (same recipe as ci.yml's `contract` job and the PR 2
    plan): dump the schema in-process and point `OPENAPI_INPUT` at it. Abort if regen produces no
    diff (it silently hit the localhost default).
11. **Name collisions**: `cyo_adventure.db.models.Series` (ORM row) vs the pydantic `Series`
    block in `storybook/models.py`. This PR touches only the ORM `Series` (in test seeding).
12. **Out of scope**: F12-F23 from the PR #184 review (tracked in its Fix Summary comment); the
    v2 declared-export block (spec section 5 explicitly defers it); any reader/frontend behavior
    change (PR 2 shipped it); prose/fill/repair template changes (anchor context feeds Stage A
    only).

## File Structure

- Modify: `src/cyo_adventure/generation/concept.py` (AnchorContext field)
- Modify: `src/cyo_adventure/story_requests/anchoring.py` (extraction + constants)
- Modify: `src/cyo_adventure/generation/templates/structure.md` (continuation instruction +
  accuracy fixes)
- Modify: `tests/unit/test_anchoring.py`, `tests/unit/test_prompts.py`
- Modify: `tests/integration/test_series_link.py` (two new worker-path tests)
- Regenerate: `frontend/src/client/*` (committed, drift-checked in CI)
- Modify: `CHANGELOG.md`

---

### Task 0: Verify base state

Operational task.

- [ ] **Step 1: Confirm branch and base**

Run: `git -C /home/byron/dev/CYO_Adventure/.worktrees/ws-g-pr3 branch --show-current && git -C /home/byron/dev/CYO_Adventure/.worktrees/ws-g-pr3 rev-parse --short HEAD`
Expected: `feat/ws-g-generation-continuity` at `6c42867`.
Abort if: different branch or base.

- [ ] **Step 2: Sanity-run the nearest test files**

Run: `cd /home/byron/dev/CYO_Adventure/.worktrees/ws-g-pr3 && uv run pytest tests/unit/test_anchoring.py tests/unit/test_prompts.py -q`
Expected: all pass.
Abort if: any failure (the base is broken; report BLOCKED).

---

### Task 1: AnchorContext gains `variable_names`, extracted from the anchor blob

**Files:**
- Modify: `src/cyo_adventure/generation/concept.py:170-186`
- Modify: `src/cyo_adventure/story_requests/anchoring.py` (constants at 34-38, function at 187-221)
- Test: `tests/unit/test_anchoring.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_anchoring.py` (module already imports `anchor_context_from_blob` and
defines `_blob()`):

```python
def test_extracts_variable_names_from_blob() -> None:
    blob = _blob()
    blob["variables"] = [
        {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5},
        {"name": "has_lantern", "type": "bool", "initial": False},
    ]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.variable_names == ["courage", "has_lantern"]


def test_variable_names_default_empty_when_absent() -> None:
    ctx = anchor_context_from_blob(_blob(), character_names=[])
    assert ctx.variable_names == []


def test_malformed_variables_degrade_not_raise() -> None:
    blob = _blob()
    blob["variables"] = [
        "not_a_dict",
        {"name": 7},
        {"name": ""},
        {"type": "int"},
        {"name": "kindness", "type": "int", "initial": 1},
    ]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.variable_names == ["kindness"]


def test_variable_names_capped_at_ten() -> None:
    blob = _blob()
    blob["variables"] = [
        {"name": f"var_{i:02d}", "type": "bool", "initial": False} for i in range(12)
    ]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert len(ctx.variable_names) == 10
    assert ctx.variable_names[0] == "var_00"


def test_overlong_variable_name_is_truncated_not_rejected() -> None:
    """A malformed blob must degrade, not raise: 200 chars is _BoundedText's cap."""
    blob = _blob()
    blob["variables"] = [{"name": "x" * 500, "type": "bool", "initial": False}]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.variable_names == ["x" * 200]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_anchoring.py -q`
Expected: the five new tests FAIL (`AnchorContext` has no `variable_names`; `extra="forbid"`).

- [ ] **Step 3: Implement**

In `src/cyo_adventure/generation/concept.py`, add to `AnchorContext` after `ending_summary`:

```python
    variable_names: list[_BoundedText] = Field(default_factory=list, max_length=10)
```

and append to the class docstring (before the closing quotes):

```text
    ``variable_names`` (WS-G PR 3, decision G3) lists the anchor's declared
    story-state variable names, read from the published blob's top-level
    ``variables`` array. The structure prompt instructs the generator to reuse
    these exact names where the continuation tracks the same state; the
    reader's name-matched var-state seeding (spec section 4, PR 2) only
    carries state when the names match.
```

In `src/cyo_adventure/story_requests/anchoring.py`, add after `_MAX_CHARACTER_NAMES = 5`:

```python
_MAX_VARIABLE_NAMES = 10
_VARIABLE_NAME_CHARS = 200  # matches concept._BoundedText's max_length
```

and in `anchor_context_from_blob`, replace the final `return AnchorContext(...)` with:

```python
    variable_names: list[str] = []
    variables = blob.get("variables")
    if isinstance(variables, list):
        for variable in variables:
            if len(variable_names) >= _MAX_VARIABLE_NAMES:
                break
            if not isinstance(variable, dict):
                continue
            name = variable.get("name")
            if isinstance(name, str) and name:
                variable_names.append(name[:_VARIABLE_NAME_CHARS])
    return AnchorContext(
        title=safe_title[:_TITLE_CHARS],
        character_names=character_names[:_MAX_CHARACTER_NAMES],
        ending_summary=summary,
        variable_names=variable_names,
    )
```

- [ ] **Step 4: Run tests, lint, typecheck**

Run: `uv run pytest tests/unit/test_anchoring.py -q && uv run ruff format src/cyo_adventure/generation/concept.py src/cyo_adventure/story_requests/anchoring.py tests/unit/test_anchoring.py && uv run ruff check src/cyo_adventure/generation/concept.py src/cyo_adventure/story_requests/anchoring.py tests/unit/test_anchoring.py && uv run basedpyright src/cyo_adventure/generation/concept.py src/cyo_adventure/story_requests/anchoring.py`
Expected: tests PASS, ruff clean, basedpyright 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/generation/concept.py src/cyo_adventure/story_requests/anchoring.py tests/unit/test_anchoring.py
git commit -S -m "feat(generation): AnchorContext carries the anchor's declared variable names (WS-G PR 3)"
```

---

### Task 2: Continuation instruction and accuracy fixes in the structure template

depends-on: Task1 [output] (the prompt test constructs an `AnchorContext` with `variable_names`).

**Files:**
- Modify: `src/cyo_adventure/generation/templates/structure.md`
- Test: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_prompts.py` (add `AnchorContext` to the existing
`from cyo_adventure.generation.concept import ...` import; the `minimal_brief` fixture already
exists at the top of the module):

```python
def test_structure_prompt_carries_anchor_variable_names(
    minimal_brief: ConceptBrief,
) -> None:
    """The brief's anchor variable names ride into the user block wholesale."""
    brief = minimal_brief.model_copy(
        update={
            "anchor_context": AnchorContext(
                title="Book One", variable_names=["courage"]
            )
        }
    )
    stage = build_structure_prompt(brief)
    assert '"variable_names"' in stage.user
    assert '"courage"' in stage.user


def test_structure_prompt_instructs_anchor_variable_reuse(
    minimal_brief: ConceptBrief,
) -> None:
    """The static task framing tells the model what to do with variable_names."""
    stage = build_structure_prompt(minimal_brief)
    assert "variable_names" in stage.system
    assert "same name" in stage.system


def test_structure_prompt_instructs_valid_ending_shape(
    minimal_brief: ConceptBrief,
) -> None:
    """The ending instruction matches the enforced Ending model (kind + valence).

    Regression pin for the stale `ending.type` instruction: the schema has no
    `type` field, and the old vocabulary (failure/bittersweet/open) is not in
    EndingKind. See storybook/models.py:408-416, 89-105.
    """
    stage = build_structure_prompt(minimal_brief)
    assert "`kind`" in stage.system
    assert "`valence`" in stage.system
    assert "bittersweet" not in stage.system
```

- [ ] **Step 2: Run to verify the template tests fail**

Run: `uv run pytest tests/unit/test_prompts.py -q`
Expected: `test_structure_prompt_carries_anchor_variable_names` PASSES already (serialization is
wholesale; that is the point of pinning it), the other two FAIL against the current template.

- [ ] **Step 3: Edit the template**

In `src/cyo_adventure/generation/templates/structure.md`:

(a) Replace task item 1 (lines 27-31) with:

```text
1. The top-level metadata fields: `schema_version`, `id` (use a UUID v4), `version`
   (set to 1), `title` (propose one if not in the brief), and the `metadata` block
   (`age_band`, `reading_level` as an object with `scheme` and `target`, `tier`,
   `themes`, `estimated_minutes`, `ending_count`, `topology`, `content_flags`). Set
   `metadata.ending_count` to the exact number of endings stated in the Budget
   section of the user message.
```

(b) Replace task item 2 (lines 33-34) with:

```text
2. A `variables` array (empty for Tier 1; for Tier 2, declare each variable with
   `name`, `type`, `initial`, `min` and `max` for integers, and `description`).
   If the concept brief includes `anchor_context` with a non-empty
   `variable_names` list, this story continues an earlier book in a series:
   wherever the new story tracks the same state as the earlier book (for
   example a courage or kindness meter), declare that variable with EXACTLY the
   same name from `variable_names` instead of inventing a renamed duplicate.
   Reader progress carries across books only when the names match. Do not
   declare an anchor variable this story never uses.
```

(c) Replace the ending bullet (lines 52-53) with:

```text
   - `ending`: include on ending nodes only, with `id` (a stable slug), `kind`
     (`success`, `setback`, `death`, `capture`, `completion`, or `discovery`),
     `valence` (`positive`, `neutral`, or `negative`), and `title`.
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_prompts.py -q`
Expected: PASS (all three new tests plus the existing suite; if an existing test pins the old
template text, update its expectation to the corrected text in the same commit and say so in the
report).

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/generation/templates/structure.md tests/unit/test_prompts.py
git commit -S -m "feat(generation): instruct anchor variable-name reuse and fix stale ending/metadata guidance in the structure prompt (WS-G PR 3)"
```

---

### Task 3: F11 worker-path integration tests driving the real `_persist_and_moderate`

depends-on: Task1 [completion] (no output consumed; keeps commits ordered).

**Files:**
- Test: `tests/integration/test_series_link.py`

The two tests drive `_persist_and_moderate` ITSELF (not a replica of its call sequence), closing
PR #184 review F7/F11. Reuse the module's existing imports (`pipeline_mod`, `_CANNED_STORY`,
`_pii`, ORM models, `Settings`, `Finding`/`Source`/`Verdict`, `AsyncMock`) and its seeding shape
(see Key fact 8).

- [ ] **Step 1: Add imports**

Add to the import block of `tests/integration/test_series_link.py`:

```python
from cyo_adventure.db.models import GenerationJob
from cyo_adventure.generation import worker as worker_mod
from cyo_adventure.generation.orchestrator import GenerationOutcome
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.generation.worker import _persist_and_moderate, _PersistContext
from cyo_adventure.core.exceptions import ValidationError
```

(`GenerationJob` joins the existing `from cyo_adventure.db.models import (...)` list; keep ruff
isort happy by letting `ruff format`/`ruff check --fix` order them.)

- [ ] **Step 2: Write the failing tests**

Append:

```python
def _series_seed_rows(
    family: Family, user: User, series: Series, concept: Concept
) -> StoryRequest:
    """A StoryRequest linking concept to series (the worker's series signal)."""
    return StoryRequest(
        family_id=family.id,
        request_text="a story",
        age_band="8-11",
        concept_id=concept.id,
        series_id=series.id,
    )


def _stub_moderation_stages(
    monkeypatch: pytest.MonkeyPatch, *, readability: AsyncMock
) -> None:
    """All-clean moderation stages except the supplied readability stub."""
    monkeypatch.setattr(pipeline_mod, "run_classifiers", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_mod, "run_safety_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_mod, "run_coherence_stage", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        pipeline_mod, "run_engagement_stage", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(pipeline_mod, "run_readability_stage", readability)


async def test_persist_and_moderate_repair_roundtrip_embeds_series_block(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #184 F7/F11: drive the REAL _persist_and_moderate through a soft repair.

    Unlike test_embed_series_block_survives_moderation_repair (which replicates
    the worker's call sequence), this drives the worker helper itself, so a
    reorder of persist/link/moderate/embed inside _persist_and_moderate fails
    THIS test even if each callee still works in isolation.
    """
    async with sessions() as session:
        family = Family(name="Worker Roundtrip Family")
        session.add(family)
        await session.flush()
        user = User(family_id=family.id, role="guardian", authn_subject="g-worker")
        session.add(user)
        await session.flush()
        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=True,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()
        concept = Concept(family_id=family.id, brief={}, created_by=user.id)
        session.add(concept)
        await session.flush()
        session.add(_series_seed_rows(family, user, series, concept))
        await session.flush()
        job = GenerationJob(concept_id=concept.id, status="running")
        session.add(job)
        await session.flush()

        flag_finding = Finding(
            stage=2,
            source=Source.LLM_READABILITY,
            category="reading_level",
            node_id="n_start",
            verdict=Verdict.FLAG,
            message="too hard",
        )
        _stub_moderation_stages(
            monkeypatch,
            readability=AsyncMock(side_effect=[[flag_finding], []]),
        )
        story_id = f"s_{job.id}"
        revised_blob: dict[str, object] = {
            **dict(_CANNED_STORY),
            "id": story_id,
            "title": "The Forest Path (revised)",
        }
        monkeypatch.setattr(
            pipeline_mod, "attempt_repair", AsyncMock(return_value=revised_blob)
        )
        monkeypatch.setattr(
            worker_mod, "_default_settings", Settings(review_provider="mock")
        )

        outcome = GenerationOutcome(
            status="passed",
            storybook=dict(_CANNED_STORY),
            report={"ok": True},
            attempts=0,
            stage_log=["stage_a:gate_ok"],
        )
        ctx = _PersistContext(
            job_id=job.id,
            job_row=job,
            concept_row=concept,
            effective_provider=MockProvider(responses=[]),
            authoring=None,
            pii=_pii(),
        )
        await _persist_and_moderate(session, ctx, outcome)
        # The worker's caller owns the happy-path commit (worker.py docstring).
        await session.commit()

    async with sessions() as session:
        row = await session.get(StorybookVersion, (story_id, 1))
        assert row is not None
        assert row.blob["title"] == "The Forest Path (revised)"
        meta = row.blob["metadata"]
        assert isinstance(meta, dict)
        block = meta["series"]
        assert isinstance(block, dict)
        assert block["series_entry_node"] == row.blob["start_node"]
        assert block["carries_state"] is True
        refreshed_job = await session.get(GenerationJob, job.id)
        assert refreshed_job is not None
        assert refreshed_job.storybook_id == story_id


async def test_persist_and_moderate_embed_failure_rolls_back_and_fails_job(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #184 F11: an embed_series_block failure rolls back the persist.

    Asserts the invariant the worker's except path promises: the unreviewed
    storybook persist is discarded (no row survives, so an RQ retry of the same
    job cannot collide on the per-job story id), the job lands committed as
    "failed" with the error recorded, and the exception propagates.
    """
    async with sessions() as session:
        family = Family(name="Worker Rollback Family")
        session.add(family)
        await session.flush()
        user = User(family_id=family.id, role="guardian", authn_subject="g-rollback")
        session.add(user)
        await session.flush()
        series = Series(
            family_id=family.id,
            title="Fox Tales",
            age_band="8-11",
            carries_state=True,
            created_by=user.id,
        )
        session.add(series)
        await session.flush()
        concept = Concept(family_id=family.id, brief={}, created_by=user.id)
        session.add(concept)
        await session.flush()
        session.add(_series_seed_rows(family, user, series, concept))
        await session.flush()
        job = GenerationJob(concept_id=concept.id, status="running")
        session.add(job)
        # The rollback in the except path discards flushed-but-uncommitted rows,
        # so the job row must be durable BEFORE _persist_and_moderate runs (in
        # production it is: the worker commits the running transition first).
        await session.commit()

        _stub_moderation_stages(monkeypatch, readability=AsyncMock(return_value=[]))
        monkeypatch.setattr(
            worker_mod, "_default_settings", Settings(review_provider="mock")
        )
        monkeypatch.setattr(
            worker_mod,
            "embed_series_block",
            AsyncMock(
                side_effect=ValidationError(
                    "embed exploded", field="blob", value=None
                )
            ),
        )

        outcome = GenerationOutcome(
            status="passed",
            storybook=dict(_CANNED_STORY),
            report={"ok": True},
            attempts=0,
            stage_log=["stage_a:gate_ok"],
        )
        ctx = _PersistContext(
            job_id=job.id,
            job_row=job,
            concept_row=concept,
            effective_provider=MockProvider(responses=[]),
            authoring=None,
            pii=_pii(),
        )
        story_id = f"s_{job.id}"
        with pytest.raises(ValidationError, match="embed exploded"):
            await _persist_and_moderate(session, ctx, outcome)

    async with sessions() as session:
        # The persist was rolled back: no storybook row survives.
        assert await session.get(Storybook, story_id) is None
        assert await session.get(StorybookVersion, (story_id, 1)) is None
        # The failure was recorded and committed by _record_failure.
        refreshed_job = await session.get(GenerationJob, job.id)
        assert refreshed_job is not None
        assert refreshed_job.status == "failed"
        assert refreshed_job.error is not None
        assert "embed exploded" in refreshed_job.error
```

Notes for the implementer:
- If `Finding`/`Source`/`Verdict` or `Settings` are not yet imported at module top, they are (see
  the current import block); do not re-import.
- No `@pytest.mark.asyncio` decorator: the module applies
  `pytestmark = [pytest.mark.integration, pytest.mark.asyncio]` at line 48 (every test in the
  module is async, so the module-level mark is the established convention here).
- `_persist_and_moderate` and `_PersistContext` are private; importing them in tests follows the
  existing precedent in `tests/unit/test_worker_persistence.py`.

- [ ] **Step 3: Run the two tests (testcontainers Postgres)**

Run: `uv run pytest tests/integration/test_series_link.py -q -k "persist_and_moderate"`
Expected: both PASS. If the roundtrip test fails on moderation wiring (a stage not stubbed, or a
review-provider call escaping the stubs), compare against
`test_embed_series_block_survives_moderation_repair`'s passing setup before touching production
code; the stubs must be sufficient because they were for the direct pipeline call.

- [ ] **Step 4: Prove the tests bite (temporary mutation, then revert)**

Temporarily swap the `run_moderation_pipeline` and `embed_series_block` calls inside
`_persist_and_moderate` (move the embed call above the pipeline call), run the roundtrip test,
and confirm it FAILS (the repair discards the pre-moderation embed). Revert the swap
(`git checkout -- src/cyo_adventure/generation/worker.py`) and re-run to green. Record both
outputs in the task report; this is the evidence F7 asked for.

- [ ] **Step 5: Run the whole module + lint/typecheck**

Run: `uv run pytest tests/integration/test_series_link.py -q && uv run ruff format tests/integration/test_series_link.py && uv run ruff check tests/integration/test_series_link.py && uv run basedpyright tests/integration/test_series_link.py`
Expected: all pass, 0 errors.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_series_link.py
git commit -S -m "test(generation): drive _persist_and_moderate directly for repair round-trip and embed-failure rollback (PR #184 F11)"
```

---

### Task 4: Regenerate the frontend client

depends-on: Task1 [output]. Operational task (AnchorContext rides in ConceptBrief through the
OpenAPI schema; CI's contract job fails on drift).

- [ ] **Step 1: Dump the schema in-process and regenerate**

Run:

```bash
SCHEMA="$(mktemp --suffix=.json)"
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" > "$SCHEMA"
cd frontend && OPENAPI_INPUT="$SCHEMA" npm run generate-client && cd ..
rm -f "$SCHEMA"
```

Expected: `git status --short frontend/src/client` shows a modified `types.gen.ts` whose
`AnchorContext` type gains `variable_names?: Array<string>`.
Abort if: no diff (regen silently hit the localhost default; re-check `OPENAPI_INPUT`).

- [ ] **Step 2: Frontend typecheck**

Run: `cd frontend && npm run typecheck && cd ..`
Expected: PASS (no hand-written code reads AnchorContext today; the field is additive).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/client
git commit -S -m "chore(frontend): regenerate API client for AnchorContext.variable_names (WS-G PR 3)"
```

---

### Task 5: Full gates and CHANGELOG

depends-on: Task2 [completion], Task3 [completion], Task4 [completion]. Operational task.

- [ ] **Step 1: Backend gates**

Run: `uv run pytest --cov=src --cov-fail-under=80 -q && uv run ruff check . && uv run basedpyright src/ && uv run bandit -c pyproject.toml -r src -q`
Expected: full suite green (baseline before this PR: 2192 passed at 95.76 percent), ruff clean,
basedpyright 0 errors (pre-existing warnings acceptable), bandit no new findings.

- [ ] **Step 2: Frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run && cd ..`
Expected: PASS (one pre-existing lint warning in FlagBadge.tsx is known and acceptable).

- [ ] **Step 3: CHANGELOG entry**

Add under `## [Unreleased]` / `### Added` in `CHANGELOG.md`:

```markdown
- Generation continuity for series (WS-G PR 3): `AnchorContext` now carries the anchor book's
  declared variable names, and the structure prompt instructs continuations to reuse those exact
  names so reader progress carries across books; stale ending/metadata guidance in the structure
  template corrected to the enforced schema (`kind`/`valence`, `topology`); worker-path
  integration tests now drive `_persist_and_moderate` directly (repair round-trip and
  embed-failure rollback, PR #184 F11).
```

- [ ] **Step 4: Pre-commit and commit**

Run: `pre-commit run --all-files`
Expected: all hooks pass.

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): WS-G PR 3 generation continuity entry"
```

---

## Self-review notes (author)

- Spec section 5 clause coverage: "AnchorContext gains declared variable names from the blob's
  variables" = Task 1; "continuation prompts instruct reuse of the anchor's variable names" =
  Task 2; "tier-1 no-op" needs no code (tier-1 blobs have empty `variables`, so extraction yields
  `[]` and the instruction is conditional on a non-empty list); "v2 declared-export block out of
  scope" = excluded (Key fact 12).
- F11 coverage: Task 3 drives the real function for both the repair round-trip (F7's complaint)
  and the embed-failure rollback (F11 proper), with a bite-proof mutation step.
- Fixture-vs-gate check (obs 1048): the only plan-supplied fixtures are `variables` entries inside
  `_blob()` copies consumed ONLY by `anchor_context_from_blob` (defensive, never validating) and
  `_CANNED_STORY` (already schema-valid, already used by the existing tests on the same paths,
  including the reading-state PUT-free worker path). No fixture in this plan reaches
  `Storybook.model_validate` with new content.
- Type consistency: `variable_names` is `list[_BoundedText]` on the model, built as `list[str]`
  truncated to 200 chars and capped at 10 items before construction, so validation cannot raise.
- Commands: all pytest/ruff/basedpyright commands run from the worktree root via `uv run`; the
  regen recipe is copied verbatim from the PR 2 plan (proven on this repo).
