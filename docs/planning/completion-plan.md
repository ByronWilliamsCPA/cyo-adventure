---
title: "CYO Adventure - Completion Plan (path to v1)"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Define the concrete remaining work from the 2026-06-29 status baseline to the first usable release and full v1."
tags:
  - planning
  - project_management
component: Strategy
source: "2026-06-29 status review against merged code (Phases 0-2b delivered)"
---

> **Status**: Active | **Created**: 2026-06-29
> **Baseline**: Phases 0, 1, 2, and 2b delivered and merged. See
> [`roadmap.md`](./roadmap.md) for the phase definitions this plan executes against.

## TL;DR

The validation and generation halves of the system are built and merged: a child can
read hand-authored stories offline, and the pipeline generates stories that clear the
full gate at 70% live yield. What stands between here and a **first usable release** is
two phases of work that are almost entirely greenfield:

1. **Phase 3 (Safety and approval workflow)** on a Phase-3-ready database but with no
   workflow logic yet, and
2. **Phase 4a (Library, profiles, and the guardian app shell)**, where the frontend is
   still a single-page reader demo with no routing.

The first release is roughly half-done by phase count, but the remaining half is the
harder half: it is the parent-facing product, not the engine. Estimated **6 to 10 weeks**
to the first release for a 1 to 2 developer team, then **4 to 7 weeks** for Phase 4b and
Phase 5 to reach full v1.

## Where we are (2026-06-29 baseline)

| Area | State |
|------|-------|
| Storybook schema + Layer-1/Layer-2 validator + policy gate | ✅ Built, merged |
| Offline PWA reader (play, state-gated choices, 409 sync, PWA install) | ✅ Built, merged |
| Staged generation pipeline + live providers (OpenRouter, Ollama) | ✅ Built, merged; 70% yield |
| Concept intake + RQ worker + guardian-only generation API | ✅ Built, merged |
| Library + ratings API (backend) | ✅ Built, merged |
| Safety/moderation **logic** | ⏸️ `validator/safety.py` is a stub |
| Publish state machine + approval/send-back endpoints | ⏸️ Absent (DB columns exist) |
| Guardian/parent **frontend** (review, library, profiles, intake) | ⏸️ Absent; no routing |
| Hardening (Redis rate limiter, backups, restore drill, Sentry) | ⏸️ Absent |

The keystone insight: **the database is ready for Phase 3** (`storybook.status`,
`storybook_version.approved_by` / `published_at` / `moderation_report` all exist), and
the **deterministic age-band policy gate** (`validator/policy.py`, PL-15..18) already
runs. The missing pieces are workflow code and UI, not schema.

## Definition of "complete"

The project reaches **first usable release** when a generated story can travel concept ->
generation -> validation -> moderation -> guardian approval -> a child's library and play
offline to multiple endings, with the invariant that **no story is visible to a child
without a recorded guardian approval**, all reachable through the UI by a non-technical
parent.

It reaches **full v1** when Phase 4b (in-UI editing, ending tracker, read-aloud) and
Phase 5 (hardening, deploy behind Pangolin/Authentik, tested restore) are also done, per
the [roadmap Definition of Done](./roadmap.md#definition-of-done).

## Remaining work

### Phase 3: Safety and approval workflow (next on the critical path)

**Goal**: make the kids-facing guarantee real and enforced. ADR-005 (mandatory human
approval) governs.

| ID | Workstream | Notes |
|----|-----------|-------|
| C3-1 | Implement the LLM moderation pass behind the `SAFE-14` seam in `validator/safety.py` | Provider moderation + independent LLM-reviewer, scored against the existing band profiles; any hit flags nodes and forces review. Persist the result to `storybook_version.moderation_report`. |
| C3-2 | Publish state machine | Encode `draft -> generating -> auto_check -> in_review -> approved -> published -> archived` with `needs_revision` on gate/moderation failure. Enforce transitions in one service module, not ad hoc in endpoints. |
| C3-3 | Guardian approval/send-back endpoints | Guardian-only `approve` (stamps `approved_by` + `published_at`, sets `storybook.status=published` and `current_published_version`) and `send-back` (-> `needs_revision`). Child tokens rejected. |
| C3-4 | Review-surface read API | One endpoint returning the story blob plus flagged passages plus the moderation report, shaped for the parent review UI (built in 4a). |
| C3-5 | Enforce the core invariant | A `published` storybook must reference a version whose `approved_by` is non-null. Enforce in the publish service and back it with a DB CHECK/constraint or a tested guard; add the negative test. |
| C3-6 | Authorization + IDOR tests | Child A cannot reach child B; cross-family guardian access denied; child cannot call approve/publish. All green. |

**Acceptance**: every transition path is tested; no path reaches a child profile without a
recorded approval; adversarial briefs flag and cannot auto-publish; 90% coverage on the
publish state machine and authorization checks.

### Phase 4a: Library, profiles, and the guardian app shell (closes the first release)

**Goal**: make the whole flow reachable by a parent through the browser. This is the
**largest remaining build** because the frontend has no app shell.

| ID | Workstream | Notes |
|----|-----------|-------|
| C4a-1 | Frontend app shell + routing | Introduce a router and an authenticated layout. Today `App.tsx` is a single hard-coded reader page; every screen below needs routing and an auth context (Authentik/OIDC session). This is the prerequisite for all other 4a UI. |
| C4a-2 | Profile management UI | Create/select per-child profiles; surface age-band and reading-level caps (backed by `child_profile`). Child sessions land directly in their own library. |
| C4a-3 | Library browsing UI | Consume the existing `library` API; a child sees only `published`, profile-permitted books; ratings shown/edited via the `ratings` API. |
| C4a-4 | Guardian console: review + approve | Wire the Phase-3 review-surface API (C3-4) and approval endpoints (C3-3) into a UI where a parent reads a story, sees flagged passages, and approves or sends back in a few minutes. |
| C4a-5 | Concept intake UI + job status | Form posting to the concept/generation API; show job status (queued/running/passed/needs_review/failed) without exposing raw model output. |
| C4a-6 | Assign-to-profile UI | Guardian assigns an approved story to one or more children. |

**Acceptance**: concept -> approved -> assigned -> a child reads it offline, entirely
through the UI; a child never sees a non-permitted or unapproved story.

### First release cut

Ships: Phases 0-3 + 4a. A parent generates, reviews, approves, and assigns a story; a
child reads it offline. Deferred to after the release: in-UI editing, TTS, ending tracker
(4b), and production hardening/deploy (5). The release can run on the homelab in a
trusted-network configuration before the full Phase 5 hardening lands, if desired, but
**Phase 5's auth/ingress (Pangolin + Authentik) is required before any exposure beyond a
trusted LAN**.

### Phase 4b: Editor and engagement (post-release)

Lightweight node editor (read as a playthrough + node list, edit a passage, re-roll one
branch, re-run validation), ending tracker ("3 of 7 found"), bookmarks, and read-aloud
(TTS) for the youngest band. None started.

### Phase 5: Hardening and deploy (post-release)

Performance + offline-edge hardening; WCAG AA basics; Sentry on client and server;
**replace the in-memory `RateLimitMiddleware` with a Redis-backed limiter** (it is
single-process only today, documented in SECURITY.md); backups and a tested restore
drill; deploy behind Pangolin + Authentik; operator runbook + short authoring guide.
Also lands the deferred `GenerationJob.stage_log` column + API so the ADR-007 raw-output
purge can null `report` while keeping an auditable log.

## Sequencing and critical path

```text
Phase 3 (C3-1..C3-6)  ─┐
                       ├─► Phase 4a guardian console (C4a-4) needs C3-3/C3-4
C4a-1 app shell ───────┘   (start C4a-1 in parallel with Phase 3; it has no Phase-3 dep)
        │
        ├─► C4a-2 profiles ─► C4a-3 library ─► C4a-6 assign
        └─► C4a-5 concept intake
                                   ▼
                          FIRST USABLE RELEASE
                                   ▼
                    Phase 4b (editor/TTS/tracker) ── Phase 5 (hardening/deploy)
```

The one true ordering constraint is that the **guardian console (C4a-4) depends on the
Phase-3 approval and review APIs (C3-3, C3-4)**. Everything else in 4a (app shell,
profiles, library, concept intake) can proceed in parallel with Phase 3, so the frontend
app shell (C4a-1) should start immediately rather than waiting on Phase 3 to finish.

## Carried debt and risks

| Item | Severity | Action |
|------|----------|--------|
| **Tier-2 generation yield weak (3/7)** | Medium | Tighten the Stage A structure prompt to state band budgets inline and numerically (highest-leverage, model-independent lever; see [`phase-2b-live-provider.md`](./phase-2b-live-provider.md)). Re-measure. Do before relying on Tier-2 generation in production. |
| **In-memory rate limiter** | Medium | Phase 5: replace with Redis-backed limiter before multi-process/exposed deployment. |
| **No frontend routing / app shell** | High (effort) | Phase 4a C4a-1 is a prerequisite for all guardian/library UI; size it as real work, not a wrapper. |
| **esbuild Renovate re-proposal** | Low | Open a `renovate.json` rule pinning/grouping `esbuild` to Vite's range so the #22 bump is not re-proposed (carried TODO). |
| **markdownlint whole-repo table/heading debt** | Low | Non-gating (pre-push only). Address opportunistically; do not block planning-doc updates on it. |
| **`GenerationJob.stage_log` deferral** | Low | Phase 5: add the redacted stage-log column + API so the ADR-007 purge keeps an auditable trail. |

## Estimate

| Band | Scope | Estimate (1-2 devs) |
|------|-------|---------------------|
| Phase 3 | Safety + approval workflow + tests | 3-4 weeks |
| Phase 4a | App shell, profiles, library, guardian console, intake | 3-5 weeks (overlaps Phase 3) |
| **First usable release** | Phases 3 + 4a combined, with overlap | **6-10 weeks** |
| Phase 4b | Editor, TTS, ending tracker | 2-4 weeks |
| Phase 5 | Hardening, deploy, restore drill | 2-3 weeks |
| **Full v1** | First release + 4b + 5 | **+4-7 weeks** |

## Related documents

- [Development Roadmap](./roadmap.md) (phase definitions)
- [Project Plan](./PROJECT-PLAN.md) (detailed phase tasks and quality gates)
- [Phase 2b: live providers and yield](./phase-2b-live-provider.md)
- [ADR-005: mandatory human approval](./adr/adr-005-mandatory-human-approval.md)
