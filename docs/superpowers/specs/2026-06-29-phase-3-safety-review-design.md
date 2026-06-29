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
- **Slice 2: the CYO-native review pipeline.** A classifier pre-filter, a hard safety/age-policy
  gate, soft readability and branch-coherence gates, and an advisory engagement pass, all
  feeding one report; hard blocks auto-reject, everything else routes to guardian review.
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
  │                  │  ▲
  └──auto_reject──┐  send_back │ resubmit
                  ▼  ▼  │
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
| `draft` | auto_reject | `needs_revision` | system (slice-2 moderation) |
| `needs_revision` | submit | `in_review` | guardian or system |
| `in_review` | approve | `published` | guardian only |
| `in_review` | send_back | `needs_revision` | guardian only |
| `published` | archive | `archived` | guardian only |

The `draft → auto_reject → needs_revision` hop is added now (even though slice 1 has no
caller for it) so the slice-2 moderation pipeline can route an automatically-rejected story
without it ever passing through `in_review` or reaching a human. Including it in the slice-1
matrix keeps the state machine complete and avoids a slice-2 schema/contract change. The
moderation pipeline (slice 2) sits between generation and `in_review`: a clean story is
`submit`-ed to `in_review`; a hard-blocked one is `auto_reject`-ed to `needs_revision`.

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

## 4. Slice 2 design (deferred): staged moderation and editorial review

Captured now so the slice-1 seam is shaped correctly; built in a follow-up PR (slice 2 or 3).
The validator gate already calls a `SAFE-14` seam (`validator/safety.py`); this work replaces
the stub with a CYO-native multi-stage review pipeline.

The pipeline **borrows the mechanism** of the reference-library writing pipeline
(`/home/byron/dev/reference-library`): sequential stages, each emitting a structured verdict
that accumulates into one report, gated progression, a bounded remediation loop, and human
escalation as the terminal gate. It does **not** copy that pipeline's four doc-editing stages;
those are an example of the pattern from a professional document-review setting. The *reviews
themselves are designed for this domain*, branching choose-your-own-adventure stories for
children, and target what the deterministic gate (Layer-1/Layer-2 validator plus the PL-15..18
policy gate) cannot judge: age-relative safety, readability fit, cross-branch narrative
coherence, and choice quality. Two differences from the source pattern: the stages run
**server-side** inside the generation/moderation pipeline (LLM calls behind a provider
abstraction, emitting verdicts rather than rewriting in place), not as interactive subagents;
and human escalation is not a bolted-on fallback but the mandatory guardian approval ADR-005
already requires.

The pipeline runs between generation and `in_review`: after a story passes the deterministic
gate (status `draft`), the review pipeline runs; a clean result is `submit`-ed to `in_review`
for the guardian, a hard-blocked one is `auto_reject`-ed to `needs_revision` (the slice-1
state-machine hops added in 3.1).

### 4.1 Stage 0: classifier pre-filter (deterministic, free)

Run **OpenAI Moderation** (`omni-moderation-latest`) and **Google Perspective** over each
node's prose. We leverage the full taxonomy, not one category, splitting it by role:

| Classifier category | Policy dimension | Role |
|---------------------|------------------|------|
| OpenAI `sexual`, `sexual/minors`; Perspective `SEXUALLY_EXPLICIT` | sexual | **Hard block** (any band) |
| OpenAI `self-harm/instructions`, `self-harm/intent` | self-harm | **Hard block** |
| OpenAI `illicit/violent`, `hate/threatening`, `harassment/threatening` | hate / unsafe instruction | **Hard block** |
| OpenAI `violence`, `violence/graphic`; Perspective `THREAT` | violence / peril | **Graded** (vs band ceiling) |
| OpenAI `self-harm` (non-instructional); Perspective `SEVERE_TOXICITY` | scariness / peril | **Graded** |
| OpenAI `hate`, `harassment`, `illicit`; Perspective `IDENTITY_ATTACK`, `INSULT` | hate / harassment | **Graded** |
| Perspective `TOXICITY`, `PROFANITY` | language / tone | **Graded** (advisory-leaning) |

Bright-line hits route straight to `needs_revision` with no LLM spend. Graded scores are not
auto-blocking; they are passed forward as inputs to the band reviewer. Each classifier result
becomes a moderation finding `(source, category, score, node_id)`. Both keys are optional: a
missing key skips that classifier and the pipeline relies on the remaining stages.

The review set below is the proposed CYO pipeline: one deterministic pre-filter, one hard
safety gate, two soft quality gates, and one advisory pass. The two domain-unique reviews,
which a general document pipeline does not have, are **branch coherence** and **choice
quality**, because branching is where LLM story generation most often breaks.

### 4.2 Stage 1: safety and age-policy review (LLM, hard gate)

An independent LLM-reviewer takes each node's prose **plus the Stage-0 graded signals** plus
the `band_profile` ceilings, and returns a per-node verdict (`safe` / `flag` / `block`) scored
against that band's violence / scariness / peril ceilings and forbidden ending kinds. It also
applies a small set of **values red-lines** appropriate to children's content (e.g. cruelty
rewarded as the "good" outcome, self-harm or dangerous real-world acts modeled as achievable),
which a category classifier does not capture. This is the age-relative judgment a fixed-taxonomy
classifier structurally cannot make. Any `block`, or an unresolved `flag`, forces human review;
nothing here can auto-publish. This is the only **hard safety gate**.

### 4.3 Stage 2: age-fit and readability (LLM, soft gate)

Vocabulary, sentence complexity, and Flesch-Kincaid grade vs the band's `reading_level_cap`
(textstat is already in the stack), plus thematic maturity fit. A story far off its
reading-level target is a **soft gate**: it gets one bounded auto-repair pass and, if still
off, is surfaced to the guardian (per the owner decision: reading level is a quality, not a
safety, property, so it never hard-blocks on its own).

### 4.4 Stage 3: narrative and branch coherence (LLM, soft gate)

The CYOA keystone review. Across **all paths**, not just one: plot, character, setting, and
tracked state (items/variables) stay consistent; each choice's stated consequence actually
follows; no branch contradicts an earlier passage; every ending is reachable in tone and
sensible for the path that led there. The deterministic Layer-2 validator proves the graph is
*structurally* sound (reachable, terminating, no traps); this stage judges whether the prose is
*semantically* coherent across that graph, which determinism cannot. Severe incoherence is a
**soft gate** (auto-repair once, then surface); minor inconsistencies are flagged.

### 4.5 Stage 4: engagement, choice quality, and voice (LLM, advisory)

Are the choices meaningful, distinct, and consequential (not "go left / go right" with
identical outcomes); is pacing and stakes appropriate and fun for the band; does the prose read
as written-for-children rather than generic AI boilerplate (AI-tell detection folded in here).
Advisory to the guardian and may feed a regeneration request, but does not gate on its own.

### 4.6 Aggregation, gating, and remediation

All five stages append to one findings list persisted on `storybook_version.moderation_report`,
mirroring the reference-library accumulating status block. Gating, by stage role:

- **Hard safety gate.** Stage 0 hard block **or** Stage 1 `block` -> `auto_reject` to
  `needs_revision` immediately, no human spend.
- **Soft quality gates.** Stage 1 `flag`, Stage 2 (reading level) far-off, or Stage 3 (branch
  coherence) severe -> one bounded auto-repair pass (reuse the orchestrator's existing
  3-attempt repair cap and no-progress abort), then `submit` to `in_review` with the findings
  attached for the guardian.
- **Advisory.** Stage 4 findings, and any minor Stage 2/3 flags, never gate; they ride along
  in the report for the guardian to weigh.
- A clean (or repaired) story is `submit`-ed to `in_review`, **never** `published`. The
  guardian is always the final gate (ADR-005); the pipeline only decides what to surface and
  pre-flag.

One finding has the shape:
`{ stage, source: openai|perspective|llm_safety|llm_readability|llm_coherence|llm_engagement, category, score|severity, node_id, verdict: block|flag|advisory|pass, message }`.

### 4.7 Provider abstraction and independence

The four LLM stages (1-4) run behind a `ReviewProvider` mirroring `GenerationProvider`'s
backend optionality: **local Ollama, OpenRouter, and Modal**. `build_review_provider` enforces
**reviewer != generator**: it compares against `storybook_version.model` /
`generation_job.provider` and selects a different backend so a model never reviews its own
output. Every review prompt flows through the existing PII egress guard
(`generation/guarded.py`) before any external call, exactly as generation does.

### 4.8 Open questions (slice 2)

1. Confirm "Modal" means Modal.com auto-endpoints (as in
   `2026-06-23-modal-generation-tiers-design.md`).
2. Classifier behavior when a key is unset: skip that classifier (current plan) or hard-require.
3. Exact reading-level thresholds per band for Stage 2 (reuse `band_profile.reading_level_cap`;
   confirm the Flesch-Kincaid grade bands).
4. Exact OpenAI/Perspective category-to-dimension thresholds (verify at integration time, RAD
   external-resource; the 4.1 table is the starting map).
5. Whether Stage 4 (engagement/choice quality) belongs in slice 2 or is split into slice 3,
   given it is the only purely-advisory stage and adds the most prompt-tuning cost.

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

Slice-2 moderation/editorial questions are listed in section 4.8. The remaining cross-slice
question:

1. Slice 1 `send_back` reason: persist where in slice 1 (a lightweight audit row), or log
   only until slice 2 adds the moderation report? Current plan: log + return in slice 1.
