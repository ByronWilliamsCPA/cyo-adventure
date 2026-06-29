---
title: "Phase 3: Safety and Approval Workflow (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "roadmap.md Phase 3, PROJECT-PLAN.md section 3 + Phase 3, ADR-005 mandatory human approval, completion-plan.md C3-1..C3-6, 2026-06-29 backend inventory"
purpose: "Design for the Phase 3 safety and approval workflow: the publish state machine, guardian approval endpoints, the no-unapproved-publish invariant (slice 1), and the two-stage content-moderation pass (slice 2)."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/phase-3-safety-review` | Date: 2026-06-29 | Author: Byron Williams (with Claude)
> Implements: [roadmap Phase 3](../../planning/roadmap.md#phase-3-safety-and-review-workflow-3-4-weeks-overlaps-phase-2),
> [completion-plan C3-1..C3-6](../../planning/completion-plan.md), [ADR-005](../../planning/adr/adr-005-mandatory-human-approval.md).

## 1. Problem and scope

Generated stories currently land in the database as `storybook.status = "draft"` and
nothing ever moves them forward. The library read path only shows `published` books, so
in practice no generated story can reach a child at all, and there is no mechanism to make
one reachable *safely*. Phase 3 makes the kids-facing guarantee real and enforced: **no
story reaches a child profile without a recorded guardian approval**, and machine-generated
content is screened before a human ever sees it.

The database is already Phase-3-ready (`storybook.status`, `current_published_version`,
`storybook_version.approved_by` / `published_at` / `moderation_report`). The deterministic
age-band policy gate (`validator/policy.py`, PL-15..18) already runs inside the validation
gate. What is missing is the *workflow*: state transitions, guardian endpoints, the enforced
invariant, and the moderation pass.

Phase 3 is delivered in three slices, each its own PR:

- **Slice 1 (this plan): the approval spine.** State machine + guardian approve/send-back/
  archive endpoints + the enforced no-unapproved-publish invariant + authz/IDOR tests.
- **Slice 2: the moderation pass.** Two-stage screening that scores content against
  per-age-band policy and routes any hit to human review.
- **Slice 3: the review-surface read API.** One endpoint returning the story plus flagged
  passages plus the moderation report, shaped for the Phase-4a guardian review UI.

## 2. Current state (what exists)

| Component | State | Location |
|-----------|-------|----------|
| Story lifecycle column | `status` defaults `"draft"`; only `"published"` is read | `db/models.py` Storybook |
| Approval provenance columns | `approved_by`, `published_at`, `moderation_report` exist, never written | `db/models.py` StorybookVersion |
| Library visibility | filters `status == "published"` and `current_published_version is not None` | `api/library.py` |
| Deterministic age-band policy gate | implemented (PL-15..18) | `validator/policy.py`, `validator/band_profile.py` |
| LLM moderation seam | stub returning an empty report (`SAFE-14`) | `validator/safety.py` |
| Auth seam | `Principal` (role, family, profiles), `is_guardian`, `authorize_family`, `authorize_profile` | `api/deps.py` |
| Story persistence | creates `Storybook(status="draft")` + first version | `generation/persistence.py` |

## 3. Slice 1 design: the approval spine

A new isolated package `publishing/` holds the lifecycle logic, keeping it out of the API
and generation layers so it is testable in isolation.

### 3.1 State machine (`publishing/state_machine.py`)

A pure, dependency-free transition table over `storybook.status`. No DB, no I/O.

```text
draft ──submit──▶ in_review ──approve──▶ published ──archive──▶ archived
                     │  ▲                    │
              send_back │ resubmit           └──archive──▶ archived
                     ▼  │
                 needs_revision
```

States: `draft`, `in_review`, `needs_revision`, `published`, `archived`. The documented
`approved` state is collapsed into the `approve` action (see 3.2); it is not a distinct
resting state. (The `generating` / `auto_check` states from the PROJECT-PLAN diagram are
generation-job concerns tracked on `generation_job.status`, not story lifecycle states.)

Legal transitions:

| From | Action | To | Who |
|------|--------|----|----|
| `draft` | submit | `in_review` | guardian or system |
| `needs_revision` | submit | `in_review` | guardian or system |
| `in_review` | approve | `published` | guardian only |
| `in_review` | send_back | `needs_revision` | guardian only |
| `published` | archive | `archived` | guardian only |

`assert_transition(current, action)` returns the target state or raises
`BusinessLogicError` on any illegal hop. A frozen mapping is the single source of truth;
the matrix is exhaustively unit-tested (every legal hop succeeds, every other pair raises).

### 3.2 Service (`publishing/service.py`)

DB-touching operations that wrap a transition and stamp provenance. They flush, not commit
(the request unit-of-work in `api/deps.py` commits once at request end).

- `approve(session, principal, storybook, version)`: asserts `in_review → published`,
  sets `storybook.status = "published"`, `storybook.current_published_version = version`,
  and stamps `storybook_version.approved_by = principal.user_id` and
  `published_at = now()`. **This is the only path that may set `published`.** Collapsing
  approve and publish into one guardian action is deliberate: for a four-child family app,
  "approve" is "make visible."
- `submit(session, storybook)`: `draft|needs_revision → in_review`.
- `send_back(session, principal, storybook, reason)`: `in_review → needs_revision`,
  recording the reason (persisted in slice 2 alongside the moderation report; in slice 1 it
  is logged and returned).
- `archive(session, principal, storybook)`: `published → archived`.

### 3.3 API (`api/approval.py`)

A guardian-only router following the existing `Context` / `Principal` pattern. Routes:

- `POST /api/v1/storybooks/{storybook_id}/submit`
- `POST /api/v1/storybooks/{storybook_id}/approve`
- `POST /api/v1/storybooks/{storybook_id}/send-back` (body: `{ "reason": str }`)
- `POST /api/v1/storybooks/{storybook_id}/archive`

Every handler, in order: load the storybook (404 if absent) -> `authorize_family` against
its `family_id` (403 cross-family) -> require `principal.is_guardian` (403 for child) ->
call the service (409 `BusinessLogicError` on an illegal transition). All handlers are
`async def` and carry RAD markers (security: guardian-only mutation; data integrity: ORM
boundary) per the package CLAUDE.md.

### 3.4 The enforced invariant

**No `published` storybook without a recorded approver.** Three reinforcing layers:

1. **Single write path.** `service.approve` is the only code that sets `status="published"`,
   and it always stamps `approved_by` in the same operation. No other path writes
   `published`.
2. **Read-path defense.** The library query is tightened so a story is visible to a child
   only if its `current_published_version` row has `approved_by IS NOT NULL` (defends
   against any future or manual status write that skips the service).
3. **Test lock.** A test asserts that across every reachable transition path, any storybook
   in `published` has a `current_published_version` whose `approved_by` is non-null, and
   that no endpoint sequence can publish without stamping it.

A DB CHECK constraint cannot express this (it spans `storybook` and `storybook_version`); a
trigger is deferred as optional hardening (Phase 5). The single-write-path plus read-path
defense plus the test is the enforcement for slice 1.

### 3.5 Tests (TDD)

- Unit: the full transition matrix (legal succeed, illegal raise).
- Unit: `service.approve` stamps `approved_by` + `published_at` + `current_published_version`
  and sets `published`.
- Integration: guardian approves an `in_review` story -> `published` + stamped.
- Integration (IDOR/authz): a child token gets 403 on approve/submit/send-back/archive; a
  guardian from another family gets 403; an illegal transition returns 409.
- Integration (invariant): no endpoint sequence reaches `published` without `approved_by`.

### 3.6 Files touched (slice 1)

- New: `src/cyo_adventure/publishing/__init__.py`, `state_machine.py`, `service.py`
- New: `src/cyo_adventure/api/approval.py` (router) + registration in `app.py`
- Edit: `api/library.py` (tighten the read path to require `approved_by`)
- New tests under `tests/unit/` and `tests/integration/`

No schema migration is needed: all columns already exist.

## 4. Slice 2 design (deferred): the two-stage moderation pass

Captured now so the slice-1 seam is shaped correctly; built in a follow-up PR. The validator
gate already calls a `SAFE-14` seam (`validator/safety.py`); slice 2 replaces the stub.

**Two stages, in order:**

1. **Prebuilt classifier pre-filter.** Off-the-shelf, free, key-available classifiers run
   first and produce category findings: **OpenAI Moderation** (`omni-moderation-latest`,
   has a dedicated `sexual/minors` category) and **Google Perspective** (toxicity / threat /
   sexually-explicit). We integrate, we do not build a classifier. An egregious bright-line
   hit (e.g. `sexual/minors`) is a hard block that routes straight to `needs_revision`.
2. **LLM-reviewer.** An independent reviewer that takes the story **plus the stage-1
   classifier findings as input** and produces the age-band-relative judgment a fixed-taxonomy
   classifier cannot (scored against `band_profile` ceilings for violence / scariness / peril).

**Design constraints (from the owner):**

- **Provider optionality mirrors generation.** The LLM-reviewer runs behind a
  `ModerationProvider` abstraction with the same backend optionality as generation: local
  Ollama, OpenRouter, and Modal. It reuses the generation provider-config pattern.
- **Independence: the reviewer must not be the creator.** The reviewing model/provider for a
  given story MUST differ from the provider/model that generated it (recorded on
  `storybook_version.model` / `generation_job.provider`). `build_moderation_provider`
  enforces or selects a different backend so a model never grades its own homework.
- **Findings shape.** The seam returns a list of moderation findings (source, category,
  score, node id, severity). Both stages append to the same list, so either mechanism can be
  added, reordered, or run alone without rework. The aggregate is persisted to
  `storybook_version.moderation_report` and any hit forces `in_review` (never auto-publish).
- **PII egress.** Moderation prompts and classifier payloads are story content (no child
  PII), but they still flow through the existing PII egress guard
  (`generation/guarded.py`) before any external call, consistent with generation.

**Open question for slice 2:** confirm "Modal" means Modal.com auto-endpoints (as in
`2026-06-23-modal-generation-tiers-design.md`); whether the classifier stage is mandatory or
best-effort when a key is absent; and the exact OpenAI/Perspective model identifiers
(verify at integration time, RAD external-resource).

## 5. Slice 3 design (deferred): review-surface read API

A guardian-only `GET /api/v1/storybooks/{id}/versions/{version}/review` returning the story
blob, the flagged passages (derived from `moderation_report`), and the validation +
moderation reports, shaped for the Phase-4a guardian review UI. Read-only; reuses the
family-ownership authorization. Detailed in its own slice once slices 1 and 2 land.

## 6. Sequencing and out of scope

Order: slice 1 (approval spine) -> slice 2 (moderation) -> slice 3 (review-surface API).
Slice 1 has no dependency on slices 2 or 3 and delivers the irreducible safety guarantee on
its own. Out of scope for all of Phase 3: any frontend (the guardian review UI is Phase 4a,
which consumes slice 3's API); the deferred trigger-based invariant hardening (Phase 5); the
`generation_job.stage_log` retention column (Phase 5).

## 7. Open questions

1. Slice 2 "Modal" backend: confirm Modal.com auto-endpoints, matching the existing
   generation tier design.
2. Slice 2 classifier behavior when a provider key is unset: hard-require, or skip that
   classifier and rely on the remaining stage(s)?
3. Slice 1 `send_back` reason: persist where in slice 1 (a lightweight audit row), or log
   only until slice 2 adds the moderation report? Current plan: log + return in slice 1.
