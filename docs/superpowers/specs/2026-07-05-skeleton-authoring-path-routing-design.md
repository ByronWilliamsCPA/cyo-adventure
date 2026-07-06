---
title: "Authoring-Path Routing for Approved Story Requests (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md sections 5-7, 12; docs/planning/adr/adr-011-story-scale-framework.md; docs/planning/skeleton-corpus-story-generation-test-plan.md; src/cyo_adventure/api/story_requests.py; src/cyo_adventure/api/generation.py; src/cyo_adventure/api/approval.py; src/cyo_adventure/generation/{orchestrator,provider,persistence,import_story,import_cli}.py; src/cyo_adventure/moderation/pipeline.py; .claude/skills/cyo-author/SKILL.md"
purpose: "Design the admin-facing step, between guardian approval and generation, where an admin picks how an approved story request gets authored (skeleton-fill vs fresh generation, skill vs automated provider) and which models do the prep and review work, implementing the worker-wiring step the tiered-backends spec deferred."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/authoring-path-routing` | Date: 2026-07-05 | Author: Byron Williams (with Claude)
> Implements the deferred "skeleton-fill wiring into the worker/orchestrator" step
> from `docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md`
> (Sections 5-6, called a non-goal in the 2026-07-04 Modal-leg design), and adds a
> new admin-workflow layer that spec did not cover: how a *live, approved child
> story request* picks an authoring backend and which models do the work.

## 1. Problem and goal

Two pipelines exist today and neither is chosen deliberately:

- The concept-brief API (`POST /api/v1/concepts/{id}/generate` ->
  `generation/worker.py` -> `orchestrator.generate_story()`) always invents fresh
  structure from an LLM. It never reads the skeleton library at all;
  `select_skeleton(band, length, theme)` was speced (tiered-backends Section 5)
  but never implemented.
- The `cyo-author` skill fills an existing skeleton's `<<FILL>>` directives, but
  only as a manual, offline, one-skeleton-at-a-time developer action, with no
  connection to a live child story request.

An approved story request (child requests, guardian approves) has no path today
that lets an admin choose *which* of these to use, or which model does the
prep/review work. This design adds that choice as one new step, wires the
skeleton-fill flow into the automated backend for the first time, and reuses the
fill-contract shape the tiered-backends spec already defined instead of inventing
a new one.

**Non-goals** (explicitly out of scope, tracked elsewhere or deferred):

- **Admin-facing UI.** This design specifies the API only. A UI can be layered on
  later (following the existing `frontend/src/guardian/ReviewDetailPage.tsx`
  pattern, which already serves the admin reviewer for the review-queue
  approve/send-back flow) without changing this contract.
- The empirical model-alignment calibration table (tiered-backends Section 7) is
  a future input to this design's warn-only eligibility check, not something this
  design builds. Until it exists, the eligibility check uses a small,
  hand-authored starting table.
- Deploying new Modal endpoints, procedural skeleton generation, series
  generation: unrelated phased-rollout steps (tiered-backends Section 12, items
  6-9), untouched here.
- Staleness handling for a job parked at `awaiting_manual_fill`: explicitly
  deferred (see Section 6).
- Theme-aware skeleton selection at library scale (picking among many
  same-band, same-theme skeletons): the library currently has 1-3 skeletons per
  band, each with one fixed baked-in theme, so this design reskins the nearest
  band/length/style match instead. Revisit once the library has enough per-theme
  breadth for true selection (the original design intent).

## 2. End-to-end flow

Step 1 is existing behavior, **modified** (see the callout below); step 7 is
existing, unchanged; steps 3-6 are new.

1. **Child requests a story; guardian approves -- MODIFIED.** Today,
   `approve_story_request` (`story_requests/service.py:70-139`) creates the
   `Concept` **and** a `GenerationJob(status="queued")`, then
   `approve_story_request_endpoint` (`api/story_requests.py:294-329`)
   immediately enqueues it to the worker -- generation starts before any
   authoring method is chosen, which conflicts with this design's premise.
   **Resolved:** approval still creates the `Concept` (band/theme, no admin
   input needed) but **no longer creates or enqueues a `GenerationJob`**. Job
   creation and enqueueing move entirely to step 3. This is a real, breaking
   contract change: `StoryRequestApprovedView.job_id` (`api/schemas.py:364-369`)
   no longer exists at approval time (no job exists yet) and must be dropped
   from that response model; existing tests asserting approval creates a job
   (`tests/integration/test_story_requests_api.py`,
   `tests/unit/test_story_requests.py`) need updating to assert only a
   `concept_id`.
2. *(implicit)* the approved request carries the data an authoring plan needs:
   `request.concept_id` (band/theme already captured in the `Concept.brief`
   built by `brief_from_request`, `story_requests/brief.py:58-92`).
3. **NEW: admin creates an authoring plan.**
   `POST /story-requests/{id}/authoring-plan`

   ```json
   {
     "method": "skeleton_fill" | "fresh_generation",
     "mechanism": "skill" | "automated_provider",
     "prep_model": "...",
     "review_stage1_model": "...",
     "review_stage2_model": "..."
   }
   ```

   - `method`, `mechanism`, and `prep_model` are required. `review_stage1_model`
     and `review_stage2_model` are optional: omitted, Stage 1's semantic check
     (Section 2, step 6) defaults to `prep_model` (the same model that wrote the
     prose judges its own fidelity to the directive -- adequate for v1; an
     independent reviewer is a future refinement, not required now), and Stage 2
     defaults to `run_moderation_pipeline()`'s existing default review model
     (today's unchanged behavior).
   - `fresh_generation` requires `mechanism = automated_provider`; the reverse
     combination (`fresh_generation` + `skill`) is a 422 -- the `cyo-author` skill
     only fills existing structure, it has no fresh-structure mode.
   - The endpoint runs the warn-only eligibility check (Section 5) and returns any
     warnings in the response, but always proceeds -- per decision, the admin can
     pick any syntactically-valid model.
   - Requires `request.status == "approved"` (409 if `pending`/`declined`/
     `blocked`). Loads the request's existing `concept_id` (created at
     approval, step 1); does **not** create a second `Concept`. Idempotency:
     if a `GenerationJob` already exists for that `concept_id`, this is also a
     409 (one authoring plan per request; no duplicate-job path).
   - On success this creates **one** `GenerationJob` row against that existing
     `concept_id`, carrying the new `authoring_metadata` (Section 4), and (for
     `automated_provider`) enqueues it exactly as today's
     `enqueue_concept_generation` (`api/generation.py:179-241`) does; for
     `skill` it is created directly at `status="awaiting_manual_fill"`, never
     enqueued.
4. **Skeleton auto-match** (`skeleton_fill` only): pick the best `production_eligible`
   library skeleton for the request's band (nearest length/style; first match if
   several tie -- no admin picking, see non-goals). No matching skeleton for the
   band -> 422 naming `fresh_generation` as the alternative.
5. **Prep**, branching on `mechanism`:
   - `automated_provider` + `fresh_generation`: unchanged `generate_story()`
     (Stage A structure, Stage B prose, Stage C repair) against the concept brief,
     using `prep_model` as the `GenerationProvider` model.
   - `automated_provider` + `skeleton_fill`: **new** Stage B' -- load the matched
     skeleton, build one **fill-contract** payload per `<<FILL>>` node
     (`{arc_role, incoming_context, reachable_state, choice_slots, reading_level,
     fail_state_policy, content_policy}`, per tiered-backends Section 5, plus one
     added field: `theme_brief`, the child's requested theme, so the same contract
     also carries the reskin instruction), call `prep_model` per node (or batched),
     assemble, run `run_gate()`.
   - `skill` + `skeleton_fill`: job parks at `authoring_metadata.status =
     "awaiting_manual_fill"`; the matched skeleton and its fill-contract payloads
     (including `theme_brief`) are exposed via `GET /generation-jobs/{id}` for a
     human to hand to the `cyo-author` skill (told to also reskin the theme per
     `theme_brief`, while leaving structure untouched, exactly as its existing
     "structure is immutable" rule already requires). Resuming: `import_cli` gains
     an optional `--job <id>` flag; supplying it transitions that job out of
     `awaiting_manual_fill` instead of creating an unlinked standalone import
     (today's behavior, unchanged when `--job` is omitted).
6. **NEW Stage 1 review -- fidelity to the directive.** Runs before Stage 2,
   regardless of mechanism:
   - Pure code, no model: every `words=N` budget is honored within tolerance, no
     `<<FILL` markers remain, and (skeleton_fill only) structure is byte-identical
     to the source skeleton (`id`, `choices[].target`, `start_node`, node ids,
     `is_ending`, `ending`, `variables`, `metadata` all unchanged -- the same
     invariant the `cyo-author` skill's "Hard rules" already state, now enforced
     in code rather than only by instruction).
   - One semantic check needs judgment: does the prose honor each node's
     `beats=`? Uses `review_stage1_model`.
   - A failure here re-enters the existing repair-loop machinery (Stage C);
     exhausting repairs uses the same failure semantics moderation failures use
     today (`needs_revision`), not a new status.
7. **Existing Stage 2 review -- moderation.** `run_moderation_pipeline()`,
   unchanged, gains one new optional parameter: an override for its default LLM
   review model, sourced from `review_stage2_model` when the admin set one.
8. **Existing admin review-queue** (`api/approval.py`: submit/approve/send-back/
   archive, `GET /review-queue`) is the unchanged final human gate. This design
   does not touch it.

## 3. Two backends, one contract (reused, not reinvented)

This reuses tiered-backends Section 6's framing directly:

| | `automated_provider` | `skill` |
| --- | --- | --- |
| Where it runs | `GenerationProvider` call inside the FastAPI worker | Claude Code session, offline, human-in-the-loop |
| Model universe | OpenRouter/Ollama/Modal model ids (`generation/provider.py`) | Claude Code session models (Sonnet/Opus/Fable/Haiku) |
| Valid for | `fresh_generation` and `skeleton_fill` | `skeleton_fill` only |
| Resumption | Fully automatic; worker completes the job | Job parks at `awaiting_manual_fill` until `import_cli --job <id>` runs |

The fill-contract payload (Section 2, step 5) is the same shape regardless of
which mechanism consumes it, per tiered-backends Section 5's "transport-agnostic"
design goal -- the automated path builds it and calls a provider directly; the
skill path builds it and hands it to a human running `cyo-author`.

## 4. Data model changes

No new tables (this is what Approach C, which you chose, buys):

- `GenerationJob.authoring_metadata`: new nullable JSON column --
  `{method, mechanism, prep_model, review_stage1_model, review_stage2_model,
  skeleton_slug, warnings: [...]}`. Keeps this routing data out of `ConceptBrief`,
  which stays purely "what the story is about."
- `GenerationJob.status`: one new value, `awaiting_manual_fill`. Only reachable
  via `mechanism = skill`; `automated_provider` jobs never see it.
- `import_cli`: new optional `--job <uuid>` argument. Ties a manually-filled
  story back to the job it fulfills; omitted, today's standalone behavior
  (library-seeding via `cyo-author`, unrelated to any live request, per
  `docs/planning/skeleton-corpus-story-generation-test-plan.md`) is unchanged.

## 5. Model routing and eligibility (warn-only)

Two model universes, kept apart by `mechanism`, never mixed:

- **Hard validation (422):** `prep_model` must syntactically belong to the
  universe `mechanism` implies (an OpenRouter model id submitted with
  `mechanism: skill` is a category error, not a judgment call).
- **Soft warning (never blocks):** a small code-level lookup keyed on
  `(method, mechanism, band, tier)` flags likely-poor fits (e.g. a lightweight
  model against a Tier-2 stateful `16+` skeleton) as a warning string. Seeded from
  the "starting model hypothesis" column in tiered-backends Section 7; replace
  with the real alignment table once that calibration run exists (non-goal here).
  The admin can proceed past any warning.

## 6. Error handling

| Condition | Response |
| --- | --- |
| `request.status != "approved"` | 409 |
| A `GenerationJob` already exists for the request's `concept_id` | 409 (one authoring plan per request) |
| `method=fresh_generation` with `mechanism=skill` | 422 |
| `prep_model` outside the universe `mechanism` implies | 422 |
| No `production_eligible` skeleton for the request's band (`skeleton_fill`) | 422, names `fresh_generation` as the alternative |
| Stage 1 fidelity check fails | Existing repair-loop / `needs_revision` semantics, not new ones |
| Job stuck at `awaiting_manual_fill` indefinitely | **Out of scope for v1** (explicit decision) -- no timeout, no automated reminder; visible today via `GET /generation-jobs/{id}` for anyone who checks |

## 7. Testing

- **Unit:** authoring-plan request validation (422 branches: schema-level
  method/mechanism rejection plus service-level prep_model/band checks), the
  eligibility-warning function (pure; table-driven test), skeleton auto-match
  tie-break, Stage 1's word-count / leftover-marker / structure-diff checks (pure
  code, no model, straightforward to test exhaustively).
- **Integration:** extend the existing `test_generation_worker.py` /
  `test_generation_api.py` pattern for both mechanisms; a new test for the
  `awaiting_manual_fill` -> `import_cli --job` resume round trip; `MockProvider`
  covers `automated_provider` tests exactly as today's tests already do.
- **Manual/E2E:** one full run per method
  (`skeleton_fill`+`automated_provider`, `skeleton_fill`+`skill`,
  `fresh_generation`) against the dev DB. This is the same exercise
  `docs/planning/skeleton-corpus-story-generation-test-plan.md` already scoped;
  that doc's results table can absorb these runs rather than duplicating a
  tracking table here.
