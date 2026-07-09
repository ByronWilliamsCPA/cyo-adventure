---
schema_type: planning
title: "WS-D: Pipeline Event Log Specification"
description: "Design spec for workstream D of the story lifecycle redesign: the append-only
  pipeline_event table and service-layer instrumentation of every lifecycle transition, the
  capture layer that the WS-F suggestion dashboard learns from."
tags:
  - planning
  - observability
  - specification
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Capture the ratified WS-D design (four owner-gated decisions plus the event taxonomy,
  data model, instrumentation map, PII contract, and testing bar) so the implementation plan and
  build can proceed without re-deriving scope."
component: Observability
source: "docs/planning/story-lifecycle-redesign.md (umbrella, ratified 2026-07-06, Design section
  6 and decisions 3 and 9); docs/planning/ws-d-handoff-2026-07-08.md; codebase discovery
  2026-07-08 against origin/main d17ccce."
---

## Overview

WS-D adds an append-only `pipeline_event` table and instruments every story-lifecycle state
transition to write one event row from the transaction that performs the transition. This is
the **capture layer only**. Aggregation and the admin suggestion dashboard are WS-F; series
chaining events beyond what already exists are out of scope. No auto-calibration, ever
(umbrella decision 3).

WS-D has no hard dependency on other workstreams and is backend-only. It unblocks WS-F, which
needs captured event data before per-band threshold overrides can be evidence-based.

## Ratified decisions (2026-07-08)

All four were put to the owner as structured options and ratified. They are settled.

| # | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| D1 | Transactional posture | **Same-transaction (atomic)**: the event `INSERT` rides the same session/`flush()` as the transition; both commit or both roll back | The unit-of-work pattern (`get_db_session` commits once at request end; handlers/services only `flush()`) makes this the idiomatic, zero-extra-machinery choice, and it makes the "every transition writes an event" test bar deterministic. |
| D2 | System-transition actor | **Nullable `actor_id` + `actor_role='system'`**: system transitions set `actor_id=NULL`, `actor_role='system'`; API transitions stamp `principal.user_id` + `principal.role` | Honest (no fake user row), queryable, no seed data or special-case joins. |
| D3 | Payload PII discipline | **Structured, PII-free only**: payloads carry ids, enum values, scores, counts, controlled-vocab reasons; no free text, titles, names, prose, or moderation snippets | The append-only log is a durable PII surface; keeping it PII-free bounds the blast radius. WS-F joins back to source rows under admin auth when it needs text. |
| D4 | Append-only enforcement | **DB-level trigger**: a `BEFORE UPDATE OR DELETE` trigger raises on any `pipeline_event` row mutation | Real guarantee independent of connection role; `TRUNCATE` bypasses row triggers so test teardown and future retention/partition drops still work. Supersedes the "append-only by convention" approach of `moderation_threshold_audit`; this is the data the whole learning loop trusts. |

## Current-state facts (verified 2026-07-08 against d17ccce)

- **Session/commit model**: API handlers receive a `Context` (`api/deps.py`) whose `session` is
  the request-scoped unit-of-work from `get_db_session`, which commits once at request end and
  rolls back on exception. Per `src/cyo_adventure/CLAUDE.md`, handlers and services **never**
  call `commit()`; they `flush()` only. The **worker** (`generation/worker.py`) is the
  exception: it owns its session and commits explicitly.
- **Actor in the API layer** is always `ctx.principal` (`Principal`: `user_id`, `role`,
  `family_id`, `profile_ids`). The worker and moderation pipeline have no principal (system).
- **Migration head** is `e1f2a3b4c5d6`
  (`migrations/versions/20260708_1600_add_series_and_soft_continuation.py`), verified as the
  unique head of a single-line chain.
- **Model conventions** (`db/models.py`): SQLAlchemy 2.x typed ORM (`Mapped`/`mapped_column`),
  `Uuid` PKs with `default=uuid.uuid4`, `_TS = DateTime(timezone=True)` for timestamps,
  `postgresql.JSONB` for JSON, string-enum-plus-`CheckConstraint` (not native PG enums), shared
  FK-target constants (`_FK_USER = "user.id"`, etc.). Enums are Python `StrEnum` coerced at the
  application boundary. The direct precedent to mirror is `ModerationThresholdAudit`, whose
  docstring already states "WS-D's pipeline_event log will subsume this role."
- **RAD**: every async function touching DB, external APIs, auth, or concurrency must carry a
  `#CRITICAL`/`#ASSUME`/`#EDGE` marker paired with a `#VERIFY` line (per package CLAUDE.md).

### Corrections to the handoff inventory

- **"Repair applied" is not in `publishing/service.py`.** Repair is an LLM re-prompt in
  `moderation/repair.py`, adopted inside `moderation/pipeline.py`. It is evented there.
- **"Blocked" is not a transition.** It is only a creation status set when screening
  bright-lines fire, so it is captured as the `to_state` of `request_created`.
- **`decline_story_request` is currently sync and sessionless** (mutates the loaded ORM object).
  Instrumenting it requires refactoring it to `async` taking the session.

## Data model: `PipelineEvent`

New model in `db/models.py`, table `pipeline_event`.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `Uuid` PK, `default=uuid4` | |
| `occurred_at` | `_TS`, `server_default=func.now()` | |
| `actor_id` | `Uuid`, FK→`_FK_USER`, **nullable** | NULL for system transitions (D2) |
| `actor_role` | `String(16)`, CHECK | `Role` values + `'system'` |
| `entity_type` | `String(32)`, CHECK | controlled vocab (see below) |
| `entity_id` | `String(120)` | universal holder: entities mix `Uuid` and `String(120)` PKs |
| `event_type` | `String(48)`, CHECK | `EventType` StrEnum values |
| `from_state` | `String(32)`, nullable | |
| `to_state` | `String(32)`, nullable | |
| `payload` | `JSONB`, `default={}`, not null | PII-free (contract below) |

**Indexes**: `(entity_type, entity_id)`, `event_type`, `occurred_at` (WS-F aggregation access
paths).

**`entity_type` vocab**: `story_request`, `generation_job`, `storybook`, `storybook_version`,
`series`, `storybook_assignment`, `rating`, `moderation_threshold`, `moderation_setting`.

CHECK constraints derive their value lists from the corresponding Python enums where one exists,
matching the `_AGE_BAND_VALUES` pattern in `db/models.py`.

## Event taxonomy

`EventType` (new `StrEnum`), one member per umbrella-enumerated transition:

`request_created`, `request_approved`, `request_declined`, `plan_assigned`,
`generation_started`, `generation_finished`, `moderation_completed`, `repair_applied`,
`sent_back`, `released`, `threshold_changed`, `noise_floor_changed`, `book_assigned`, `rated`.

**Deliberate consolidations / omissions:**

- **blocked** → `to_state` on `request_created` (creation status, not a transition).
- **submit vs auto-reject** → both captured by `moderation_completed`'s `to_state` (`in_review`
  vs `needs_revision`); they are mechanics of the moderation outcome, not separate admin actions.
- **series `book_index`** assignment → payload field on `generation_finished` (internal;
  distinct from the guardian `book_assigned`).
- **archive** → out of scope for v1 (not in the umbrella's enumerated list); follow-up.

`from_state`/`to_state` use the `publishing/state_machine.py` `Status` vocabulary for storybook
transitions and the request status vocabulary (`pending`/`approved`/`declined`/`blocked`) for
request transitions.

## Event writer

New module `src/cyo_adventure/events/`:

```python
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
) -> None: ...
```

plus a small `Actor` value object with `Actor.from_principal(principal)` (stamps
`user_id`/`role`) and `Actor.system()` (stamps `None`/`'system'`). `record_event` adds the row
to the passed-in session and `flush()`es, inheriting that transaction (D1). It carries RAD
markers for external-resource (DB), data-integrity (append-only ORM boundary), and concurrency
(worker-session race).

The umbrella says "written from the service layer"; where a transition is performed in the
handler rather than a service (ratings, assignments), `record_event` is called in the handler
with `ctx.principal` and `ctx.session`. This is called out so it is a stated choice, not drift.

## Instrumentation map

One `record_event` call at each site, in the transaction that performs the transition:

| Transition | Site | `event_type` | Payload (PII-free) |
| --- | --- | --- | --- |
| Request created (kid + authored) | `story_requests/service.py`, `api/story_requests.py` | `request_created` | `initiator_role`, `to_state` reflects `pending`/`blocked` |
| Request approved | `story_requests/service.py::approve_story_request` | `request_approved` | `series_created` (bool), `anchor_resolved` (bool), `series_id` |
| Request declined | `story_requests/service.py::decline_story_request` (refactor to async+session) | `request_declined` | none |
| Plan assigned | `story_requests/authoring_plan.py::build_authoring_plan` | `plan_assigned` | `job_status`, `plan_kind` |
| Generation started | `generation/worker.py::_load_and_start_job` | `generation_started` | none |
| Generation finished | `generation/worker.py::_persist_passed_outcome` / `_record_failure` | `generation_finished` | `outcome`, `provider`, `model`, `prompt_version`, `book_index` (if series) |
| Moderation completed | `moderation/pipeline.py` | `moderation_completed` | `overall_verdict`, `repaired` (bool), per-category/verdict **counts** |
| Repair applied | `moderation/pipeline.py` (on adopting a repaired blob) | `repair_applied` | `stage` |
| Released | `publishing/service.py::approve` | `released` | `visibility` |
| Sent back | `publishing/service.py::send_back` | `sent_back` | reason referenced by version id, **not** copied |
| Threshold changed | `api/moderation_thresholds.py` upsert/delete | `threshold_changed` | `age_band`, `category`, `action`, `min_verdict`, `min_score` |
| Noise floor changed | `api/moderation_thresholds.py` noise-floor update | `noise_floor_changed` | `value` |
| Book assigned | `api/assignments.py::assign_storybook` | `book_assigned` | `child_profile_id` |
| Rated | `api/ratings.py::record_rating` | `rated` | `value`, `is_update` (bool) |

`moderation_completed` is emitted once by the pipeline after the outcome is decided; the
`submit`/`auto_reject` mechanics in `publishing/service.py` are **not** separately evented.
`approve` (`released`) and `send_back` (`sent_back`) are separate admin actions and are evented.

## Payload PII contract

Payloads carry only: entity ids, enum values, numeric scores/counts, and booleans. **Forbidden**:
`request_text`, series/story titles, child or profile names, story prose, and moderation
flagged-text snippets.

**Enforcement**: the spec ships a per-`event_type` payload-key allowlist. A unit test asserts
every emitted payload's keys fall within its event type's allowlist. This is the mechanism that
backs the no-free-text rule (code review alone is not enough).

## Error handling

`record_event` `flush()`es and lets any exception propagate; the unit-of-work rolls the
transition back with it (D1). No exception is swallowed. In the worker, the event is in the
worker's own session and rolls back with the generation-outcome persist, consistent with D1.
RAD markers document these invariants.

## Append-only enforcement

The migration adds a trigger function that `RAISE`s on `UPDATE` or `DELETE` of any
`pipeline_event` row, and a `BEFORE UPDATE OR DELETE` trigger bound to it. `INSERT` is
unaffected; DDL (migrations) is unaffected; `TRUNCATE` bypasses row triggers so test teardown
and future retention work. A test asserts both `UPDATE` and `DELETE` raise.

## Migration

A **single** Alembic revision (proposed `revision='f2a3b4c5d6e7'`,
`down_revision='e1f2a3b4c5d6'`) creating the `pipeline_event` table, its indexes, the trigger
function, and the trigger. Single revision keeps the WS-C rebase trivial (see coordination).

## Testing (umbrella bar)

- **Migration round-trip** with the pinned revision id via `tests/integration/_migration_utils.py`.
- **Per-transition integration tests**: drive each transition and assert exactly one
  `pipeline_event` row with the correct `event_type`, `from_state`, `to_state`, and actor. This
  is the umbrella's "every state transition writes a pipeline event" requirement.
- **Append-only test**: `UPDATE` and `DELETE` on a `pipeline_event` row both raise; `TRUNCATE`
  succeeds.
- **Payload-allowlist test**: every emitted payload's keys are within its event type's allowlist.
- **Actor test**: system transitions record `actor_id IS NULL` and `actor_role='system'`; API
  transitions record `principal.user_id` and `principal.role`.

## Scope boundaries

- **Backend-only.** WS-D adds no public endpoint, so the OpenAPI schema is unchanged and the CI
  drift gate should come back clean (run it anyway before the PR, in-process dump, never sort
  keys). No UI flow changes, so both e2e tiers (`e2e/`, `e2e-real/`) are untouched; this is
  stated so it is explicit, not implicit.
- **Delivery**: a single PR (one table, one instrumentation sweep, tests).
- **Not in scope**: aggregation/dashboard (WS-F); removing or deduplicating
  `moderation_threshold_audit` (its docstring anticipates WS-D but removal is a later concern);
  eventing WS-C's new per-plan provider-override transition (small follow-up after both merge);
  `archive` events.

## Concurrent-session coordination (WS-C in parallel)

- Work happens in `.worktrees/ws-d` on `feat/ws-d-pipeline-event-log`, cut from `origin/main`.
- WS-C and WS-D both chain a migration onto `e1f2a3b4c5d6`. Whichever PR merges second rebases
  and bumps its migration's `down_revision` to the other's head. WS-D is a single revision to
  make that bump trivial.
- WS-C edits `story_requests/authoring_plan.py`, `generation/provider.py`,
  `generation/worker.py`, `generation/skeleton_match.py`; WS-D instruments some of the same
  files. Expect mechanical rebase conflicts there and in `CHANGELOG.md`. Do **not** event the
  transitions WS-C newly introduces.

## Process

Signed commits (`git commit -S`), Conventional Commits, no em-dash characters (pre-commit hook),
CHANGELOG entry or skip-changelog label, owner-gated merge (never auto-merge), merge queue only.
Every new async DB function carries RAD markers. Cycle: this spec, then writing-plans for a
task-level plan, then subagent-driven development with per-task reviews and an Opus whole-branch
review before the PR opens.
