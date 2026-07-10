---
schema_type: planning
title: "Story Development Lifecycle Redesign"
description: "Umbrella design for the second-generation story development process: enriched request
  lifecycle (child/guardian/admin initiators), skeleton variety across the full ADR-011
  band/length/style matrix, series tagging and
  full ADR-011 chaining, per-request provider/model assignment, age-band moderation thresholds,
  pipeline event log with a learning suggestion dashboard, and an admin-gated global catalog."
tags:
  - planning
  - architecture
  - moderation
  - generation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Record the ratified design decisions and workstream decomposition for the story lifecycle
  redesign so each workstream can be planned and executed in its own session with full context."
component: Strategy
source: "Brainstorming session 2026-07-06 (Fable 5); current-state codebase exploration of
  story_requests, generation, moderation, publishing, and assignments modules."
---

> **Status: Complete.** All seven workstreams (WS-A through WS-G) are merged as of
> 2026-07-10. See [roadmap.md](./roadmap.md#story-lifecycle-redesign-2026-07-06-to-2026-07-10-post-r1)
> and [PROJECT-PLAN.md](./PROJECT-PLAN.md#1-executive-summary) for the delivered-scope
> summary and merged-PR groupings. This document remains the design record; workstream-level
> implementation plans and handoffs have been retired now that their content is either
> shipped or migrated to a permanent home (ADRs, docstrings, or the debt register).

## Why this redesign

Skeletons were introduced because LLMs struggled to produce structurally sound
branching stories from prompts alone: the skeleton predefines the paths and nodes,
and the LLM fills in prose. They were never intended to be the only themes or
stories. This design extends the pipeline so that:

- Each age-band and length combination offers one or more skeletons for variety.
- Stories can belong to a series, started or continued by a child or guardian.
- Requests can originate from a child, guardian, or admin, with the redundant
  approval steps skipped for the initiating role.
- Admins assign the generation process and model per request.
- Moderation tags surface only above an age-appropriate threshold instead of
  the current wall of flags.
- Pipeline outcomes feed a self-learning loop (capture plus a suggestion
  dashboard, no auto-calibration).
- Admin-approved books can be shared to a global catalog that any guardian can
  assign from.

## Ratified decisions (2026-07-06)

All ten decisions below were put to the owner as structured options and
ratified. They are settled; do not re-litigate them in workstream sessions.

| # | Decision | Choice |
| --- | --- | --- |
| 1 | Guardian library scope | Admin-gated global: admin marks each book family-only or catalog-visible at release approval |
| 2 | Moderation threshold fix | Record all findings; filter at serialization so guardian/kid surfaces only show tags at or above the age-band threshold; admins see everything |
| 3 | Learning loop scope | Capture outcomes now AND build an admin suggestion dashboard; ratified changes apply without a deploy; no auto-calibration |
| 4 | Series semantics | Full ADR-011 chaining: entry-node convergence, state carry for higher bands, episodic for 3-5 and 5-8 |
| 5 | Skeleton pick | Auto-vary among production-eligible skeletons in the band/length/style cell (narrative style per ADR-011, bands 13-16 and 16+ only), weighted against the family's recently used skeletons; admin can override in the authoring plan |
| 6 | Series anchor scope | Continuations can anchor on any series-tagged book the family can see (family books plus catalog); a family continuation of a catalog series becomes a family book |
| 7 | Initiator flows | Skip redundant approvals: guardian-initiated requests are created pre-approved; admin-initiated skip the guardian gate and may target the catalog with no family |
| 8 | Threshold storage | DB-backed, admin-editable with audit trail, seeded from code defaults |
| 9 | Delivery architecture | Evolve existing models/endpoints in place, plus an append-only `pipeline_event` table that doubles as the learning-loop capture layer |
| 10 | Sequencing | Thresholds first (live pain), series chaining last (largest build); full order in Workstreams below |

## Current state (verified 2026-07-06)

Facts established by codebase exploration; verify again before building on
them in a later session.

- `StoryRequest` (`src/cyo_adventure/db/models.py`, `api/story_requests.py`,
  `story_requests/service.py`) carries only `request_text` plus family/profile
  FKs; statuses are `pending / approved / declined / blocked`. No band, length,
  or series fields exist on the request; the generation brief derives age band
  from the child profile.
- Skeleton matching (`generation/skeleton_match.py::select_skeleton_for_band`)
  is band-only and deterministically returns the first production-eligible
  skeleton in the band directory. No variety, no length dimension in matching.
- Series is modeled but dormant: `storybook/models.py::Series` (series_id,
  book_index, series_entry_node, is_final_book, carries_state) and validator
  rules SR-1..SR-7 in `validator/series.py` exist per ADR-011 section 8, but
  there is no DB table, no generation path, no request-time tagging, no UI.
- Provider selection is global config (`core/config.py::Settings.generation_provider`,
  built in `generation/provider.py::build_provider`). The admin authoring-plan
  endpoint (`story_requests/authoring_plan.py`, admin-only) already picks
  method (skeleton_fill vs fresh_generation), mechanism (skill vs
  automated_provider), and prep model per request, but not provider. The
  direct-Anthropic provider (`"claude"`) currently raises ConfigurationError
  (deferred).
- Moderation (`moderation/pipeline.py`, `stages.py`, `report.py`) runs stages
  0-4 and adds every finding it receives to the report unconditionally. The
  only existing filter sits upstream: PR #141 (`899db43b`) added a global
  advisory noise floor in `classifiers.py` (`_ADVISORY_SCORE_FLOOR = 0.01`)
  that drops sub-floor graded Stage-0 scores before they become findings.
  `age_band` is passed to the safety stage as prompt context only; there is
  no age-band threshold and no serialization-boundary filtering anywhere.
  That absence is the structural cause of the wall-of-flags issue.
- Storybook statuses: `draft / in_review / needs_revision / published /
  archived`. Admin-only release approval (`publishing/service.py::approve`,
  ADR-005 amended) stamps `approved_by` and `published_at` per version.
- Guardians see all published books in their own family (`GET /guardian/books`)
  and assign via `StorybookAssignment` (`api/assignments.py`); assignment is
  the read gate for children.
- Ratings exist (`db/models.py::Rating`, per-child per-book, mutable 1-5) but
  feed nothing. No moderation or approval outcomes are persisted for analysis.

## Design

### 1. Request lifecycle and roles

`StoryRequest` gains: `initiator_role` (child/guardian/admin), `age_band`,
`length` (short/medium/long), `narrative_style` (prose/gamebook, per ADR-011),
`series_id` (nullable FK), and `anchor_storybook_id` (nullable FK, set when
continuing a series). `family_id` and `profile_id` become nullable to support
admin-initiated catalog requests and guardian-initiated requests not tied to
one child.

- `narrative_style` follows ADR-011's rule: meaningful only for bands 13-16
  and 16+; all lower bands are implicitly prose. The API rejects
  `gamebook` for lower bands and defaults the field to `prose`. Style is a
  real scale choice, not cosmetic: the same length maps to fewer, denser
  nodes (prose) or more, shorter nodes (gamebook).
- Child-initiated: `age_band` defaults from the child profile at creation;
  status `pending`. Guardian approval requires confirming or setting
  `age_band` and `length`, plus `narrative_style` when the band allows a
  choice (the approve endpoint rejects approval without them). The child may
  propose a series tag; the guardian confirms or edits it at approval.
- Guardian-initiated: created directly in `approved` status with band, length,
  style, and series set at creation; goes straight to the admin queue.
- Admin-initiated: created in `approved` status; may have no family attached
  (catalog-targeted).
- Existing statuses and the blocked/PII screening path are unchanged.
- The request becomes the single source of truth for band and length. The
  generation brief must read them from the request, not the child profile.
  This derivation flip is the most invasive change in the design despite
  looking like a field addition; it is what makes no-child requests possible.

### 2. Skeleton matrix and selection

- Matching moves from band-only to the full ADR-011 cell:
  band-by-length-by-narrative-style. Skeleton metadata gains an explicit
  `length` field; `narrative_style` already exists on skeletons (prose vs
  gamebook) and now participates in matching. For bands below 13-16 the style
  axis collapses to prose, so their cells are band-by-length in practice.
- Selection auto-varies: choose among all production-eligible skeletons in the
  cell, weighted against skeletons the family used recently. Recency comes
  from a new `skeleton_slug` provenance field on `StorybookVersion`.
- The authoring-plan response shows the pick plus eligible alternatives; the
  admin can override. `fresh_generation` remains available, preserving the
  intent that skeletons are not the only stories.

### 3. Series

- New `series` DB table: id, title, `family_id` (nullable; null means catalog
  series), `created_by`, `carries_state`, band. It backs the existing embedded
  Pydantic `Series` schema.
- Tagging (WS-B): new-series creation and continuation anchoring at request
  time, from any series-tagged book the family can see.
- Chaining (WS-G): successful endings of book N converge on book N+1's
  `series_entry_node`; state carry for higher bands, episodic for 3-5 and
  5-8; enforced by the existing SR validator rules.
- `book_index` assignment needs a concurrency guard.
  `#CRITICAL: concurrency: two continuations of the same series racing on
  book_index` / `#VERIFY: unique constraint on (series_id, book_index) plus
  retry-on-conflict in the service layer`.

### 4. Admin processing (per-request provider and model)

- The authoring-plan step is the explicit processing gate for every request.
- It gains `provider` (anthropic / openrouter / modal / ollama) and `model`,
  validated against a server-side allowlist (no free-string model IDs
  reaching billing).
- `build_provider()` becomes a per-job factory taking these overrides and
  falling back to global `Settings`. The deferred direct-Anthropic provider
  gets implemented. Mock stays for CI.

### 5. Moderation thresholds and surfacing

- The pipeline keeps recording every finding that clears the Stage-0 advisory
  noise floor (PR #141; sub-0.01 classifier scores are dropped before the
  report), preserving training signal for the learning loop.
- New `moderation_threshold` table keyed on (age_band, category): minimum
  verdict level that surfaces as a tag, plus an optional classifier-score
  floor. Seeded from code defaults; admin-editable with an audit trail.
- v1 seeding (ratified 2026-07-07): WS-A ships zero override rows; the code
  default (surface `flag` and above) applies to every band and category.
  Per-band overrides are expected to come from WS-F dashboard evidence rather
  than being guessed up front.
- Guardian- and kid-facing serializers filter findings through the threshold
  for the book's band. Admin endpoints bypass the age-band threshold entirely
  and return every finding.
- Addendum (implemented in PR #162): a separate, global,
  admin-editable noise floor (seeded 0.05) denoises only the admin storybook
  review surface by hiding low-score ADVISORY findings; FLAG and BLOCK
  findings (including bright-line score-0.0 blocks) and unscored findings
  always surface. This floor is orthogonal to the per-band threshold: the
  age-band policy governs the guardian/kid surfaces, the noise floor governs
  admin denoising. Landed in PR #162; see the `ModerationSetting` model
  docstring (`db/models.py`) for the design rationale.
- Because the filter lives at the serialization boundary, it applies
  retroactively to every already-moderated book the moment it ships; no
  re-moderation pass is needed.

### 6. Learning loop: event log, capture, dashboard

- Append-only `pipeline_event` table: occurred_at, actor id and role, entity
  type and id, event_type, from_state, to_state, JSONB payload. Written from
  the service layer at every transition: request created / approved /
  declined, plan assigned, generation started / finished, moderation
  completed, repair applied, sent back (with reason), released, threshold
  changed or overridden, book assigned, rated.
- The suggestion dashboard (WS-F) aggregates events (for example, "category X
  advisory in band 8-11 is overridden 85% of the time") and proposes
  threshold or prompt adjustments. An admin ratifies; ratified changes write
  to the threshold table and are themselves evented. No auto-calibration.

### 7. Catalog and guardian assignment

- `Storybook` gains `visibility` (family / catalog), chosen by the admin at
  release approval, defaulting to family.
- Guardian library = family books plus catalog books; assignment works on
  anything visible. The assignment route verifies visibility server-side so a
  child can never be assigned a book their guardian cannot see.
- The admin approval UI carries a reminder that catalog books must be free of
  personal details; that human gate is what the admin-gated model relies on.
- Guardian-defined book groups by age and topic are a future phase, out of
  scope here.

### 8. Error handling, security, testing

- Provider and model inputs validated against an allowlist.
- Threshold edits and catalog publishes are admin-only and evented.
- Tests: migration round-trips with pinned revision IDs; contract tests that
  guardian and kid endpoints never leak below-threshold tags; integration
  tests asserting every state transition writes a pipeline event; e2e updates
  in both `e2e/` and `e2e-real/` tiers.

## Workstreams (in delivery order)

Each workstream is its own spec, plan, and implementation cycle. This
document is the umbrella; workstream sessions should re-verify the Current
state section before building.

| WS | Name | Scope | Depends on |
| --- | --- | --- | --- |
| A | Moderation thresholds | `moderation_threshold` table, admin editor, serialization filter | none |
| B | Request lifecycle | New request fields, three initiator flows, series tagging (table + request-time anchor), brief derivation flip | none |
| C | Admin processing | Per-request provider/model, allowlist, per-job provider factory, direct-Anthropic provider, band/length/style auto-vary skeleton matching + admin override | B (band/length/style on request) |
| D | Event log | `pipeline_event` table + instrumentation of all transitions | none (richer after B, C) |
| E | Catalog | `visibility` flag, guardian catalog browse and assign, visibility check on assignment | B (for admin catalog requests) |
| F | Suggestion dashboard | Aggregation views, propose-and-ratify flow writing to thresholds | A, D (needs captured data) |
| G | Series chaining | Full ADR-011 generation path: entry-node convergence, state carry, SR validation in the pipeline | B (tagging), C (skeleton matching) |

## Open items deferred to workstream planning

- Exact threshold default values per band and category (seed matrix):
  resolved 2026-07-07. v1 ships zero seed rows; the code default applies
  everywhere (see Design section 5). Future per-band values come from WS-F
  dashboard evidence.
- Event taxonomy enumeration (the event_type list above is the starting set).
- Whether catalog series continuations need admin notification when a family
  branches a catalog trunk.
- Prompt-adjustment suggestions in the dashboard (threshold suggestions are
  the v1; prompt suggestions may need more data).

## Related documents

- ADR-011 story-scale framework (skeleton matrix, series invariant):
  `docs/planning/adr/adr-011-story-scale-framework.md`
- ADR-005 mandatory human approval (admin release gate)
- ADR-010 Modal review and gated generation (provider strategy)
- Authorization matrix: `docs/planning/authorization-matrix.md`
