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

> **Status**: Active | **Created**: 2026-06-29 | **Updated**: 2026-07-01
> **Baseline**: Phases 0, 1, 2, 2b, and the **Phase 3 backend** delivered and merged. See
> [`roadmap.md`](./roadmap.md) for the phase definitions this plan executes against.

## TL;DR

The validation, generation, and **safety/approval** halves of the system are built and
merged: a child can read hand-authored stories offline, the pipeline generates stories
that clear the full gate at 70% live yield, and every generated story now flows through
content moderation and a guardian approval state machine before it can reach a child. What
stands between here and a **first usable release** is one phase:

- **Phase 4a (Library, profiles, and the guardian app shell)**, where the frontend is
  still a single-page reader demo with no routing. The Phase 3 approval and review APIs
  exist and are enforced; they are simply not reachable through a browser yet.

Phase 3 (Safety and approval workflow) shipped across three PRs (#34, #36, #45); the
remaining work is the parent-facing frontend, not the engine or the workflow. Estimated
**3 to 5 weeks** to the first release for a 1 to 2 developer team (Phase 4a), then **4 to
7 weeks** for Phase 4b and Phase 5 to reach full v1.

## Where we are (2026-07-01)

| Area | State |
|------|-------|
| Storybook schema + Layer-1/Layer-2 validator + policy gate | ✅ Built, merged |
| Offline PWA reader (play, state-gated choices, 409 sync, PWA install) | ✅ Built, merged |
| Staged generation pipeline + live providers (OpenRouter, Ollama) | ✅ Built, merged; 70% yield |
| Concept intake + RQ worker + guardian-only generation API | ✅ Built, merged |
| Library + ratings API (backend) | ✅ Built, merged |
| Safety/moderation **logic** | ✅ Built, merged (staged pipeline behind `SAFE-14`, #36) |
| Publish state machine + approval/send-back + review-surface API | ✅ Built, merged (#34, #45) |
| Reading-state save integrity (validate against pinned version) | ✅ Built, merged (#45) |
| Guardian/parent **frontend** (review, library, profiles, intake) | ⏸️ Absent; no routing (wireframes #47, design system #44) |
| Hardening (Redis rate limiter, backups, restore drill, Sentry) | ⏸️ Absent |

The keystone insight has now flipped: **the entire Phase 3 backend is built and merged**
(moderation pipeline, publish state machine, guardian approval/send-back, review-surface
read API, and the enforced no-publish-without-approval invariant), on top of the schema
and the deterministic age-band policy gate (`validator/policy.py`, PL-15..18). The only
missing piece for the first release is the **guardian/parent UI** that exercises these
APIs, which is Phase 4a.

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

### Phase 3: Safety and approval workflow (✅ delivered, merged)

**Goal**: make the kids-facing guarantee real and enforced. ADR-005 (mandatory human
approval) governs. **All six workstreams are merged** across three PRs: slice 1 (#34,
approval spine), slice 2 (#36, moderation pipeline), and slice 3 (#45, review surface +
save-state integrity).

| ID | Workstream | Status |
|----|-----------|--------|
| C3-1 | LLM moderation pass behind the `SAFE-14` seam (provider moderation + independent LLM-reviewer, persisted to `storybook_version.moderation_report`) | ✅ #36 |
| C3-2 | Publish state machine (`draft -> ... -> published -> archived`, `needs_revision` on failure), enforced in one service module | ✅ #34 |
| C3-3 | Guardian approval/send-back endpoints (stamps `approved_by` + `published_at`, sets `published`; child tokens rejected) | ✅ #34 |
| C3-4 | Review-surface read API (story blob + flagged passages + moderation report for the parent UI; the consuming UI is Phase 4a C4a-4) | ✅ #45 |
| C3-5 | Core invariant enforced: a `published` storybook must reference a version whose `approved_by` is non-null, backed by a tested guard | ✅ #34 |
| C3-6 | Authorization + IDOR tests (cross-child, cross-family, child cannot approve/publish) | ✅ #34 |

Also delivered in slice 3 (#45): reading-state saves are validated against the pinned
version (a structural floor always runs, with full deterministic replay when the optional
`choice_path` is present), closing red-team Finding 2.

**Acceptance (partially met; one item reframed)**: every transition path is tested; no path
reaches a child profile without a recorded approval (holds); coverage on the new Phase 3
code is at or above the 90% bar. The "adversarial briefs flag and cannot auto-publish"
criterion is **reframed**: "cannot auto-publish" holds; the import and admin-submit paths no
longer reach a publishable state without moderation (closed structurally: the import path now
runs the moderation pipeline before returning, and `approve` refuses to publish any version
with `moderation_report is None`); what remains unmet is "flag and route to human review" for
the model-dependent classes, which is not yet backed by a live-model run. See
[adversarial-safety-evaluation.md](./safety/adversarial-safety-evaluation.md) and the
carried-debt table below (C3-SAFETY). The other Phase 3 capability not yet reachable is the
browser UI, which is Phase 4a (C4a-4).

### Phase 4a: Library, profiles, and the guardian app shell (closes the first release)

**Goal**: make the whole flow reachable by a parent through the browser. This is the
**largest remaining build** because the frontend has no app shell. Design groundwork is in
place: a mobile-UI wireframe concept spec (#47) and a K-12 design system synced to
claude.ai/design (#44). The build (routing, auth context, real components) has not started.

| ID | Workstream | Notes |
|----|-----------|-------|
| C4a-1 | Frontend app shell + routing | ✅ Router (two disjoint route trees: kid `/`, `/read/*` and guardian `/guardian/*`) and an authenticated layout backed by a real Supabase Auth session (ADR-009), including guardian-tier JWKS-backed JWT verification on the backend (Phase 6 P6-01/P6-02 pulled forward; see [adr-009](./adr/adr-009-supabase-platform.md)). This is the prerequisite for all other 4a UI. |
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
Phase 3 (C3-1..C3-6)  ✅ DONE (#34/#36/#45)
        │
C4a-1 app shell ──► C4a-2 profiles ─► C4a-3 library ─► C4a-6 assign
        │       └─► C4a-4 guardian console (consumes the merged C3-3/C3-4 APIs)
        └─────────► C4a-5 concept intake
                                   ▼
                          FIRST USABLE RELEASE
                                   ▼
                    Phase 4b (editor/TTS/tracker) ── Phase 5 (hardening/deploy)
```

Phase 3 is complete, so its former ordering constraint is discharged: the **guardian
console (C4a-4) can now consume the merged approval and review APIs (C3-3, C3-4)**
directly. Phase 4a is now the entire critical path to the first release, and the frontend
app shell (C4a-1) is the prerequisite for everything else in it.

## Carried debt and risks

| Item | Severity | Action |
|------|----------|--------|
| **C3-SAFETY: adversarial safety gate unbacked (live-run pending)** | Medium | (a) and (b) are closed: `import_filled_story` now runs the moderation pipeline before returning (mirroring the generation worker), and `publishing.service.approve` structurally refuses to publish any version with `moderation_report is None`, so no unmoderated path reaches `published` regardless of route. The review surface also now exposes `screened: bool` for C4a-4. Remaining before the first release: (c) run the credentialed adversarial harness against a live review model and archive per-class results for the model-dependent classes (A, B, E); this environment has no live LLM credentials, so it is blocked on credential availability, not code. See [`safety/adversarial-safety-evaluation.md`](./safety/adversarial-safety-evaluation.md). |
| **Tier-2 generation yield weak (3/7)** | Medium | Tighten the Stage A structure prompt to state band budgets inline and numerically (highest-leverage, model-independent lever; see [`phase-2b-live-provider.md`](./phase-2b-live-provider.md)). Re-measure. Do before relying on Tier-2 generation in production. |
| **In-memory rate limiter** | Medium | Phase 5: replace with Redis-backed limiter before multi-process/exposed deployment. |
| **No frontend routing / app shell** | High (effort) | Phase 4a C4a-1 is a prerequisite for all guardian/library UI; size it as real work, not a wrapper. |
| **esbuild Renovate re-proposal** | Low | Open a `renovate.json` rule pinning/grouping `esbuild` to Vite's range so the #22 bump is not re-proposed (carried TODO). |
| **markdownlint whole-repo table/heading debt** | Low | Non-gating (pre-push only). Address opportunistically; do not block planning-doc updates on it. |
| **`GenerationJob.stage_log` deferral** | Low | Phase 5: add the redacted stage-log column + API so the ADR-007 purge keeps an auditable trail. |
| **`choice_path` optional in reading-state saves** | Medium | Slice 3 shipped save-state replay validation with `choice_path` optional (structural floor always runs; full replay only when present). Follow-up: update the React player to send `choice_path`, regenerate the client, then make the field required so replay runs on every save. |

## Estimate

| Band | Scope | Estimate (1-2 devs) |
|------|-------|---------------------|
| Phase 3 | Safety + approval workflow + tests | ✅ Done (#34/#36/#45) |
| Phase 4a | App shell, profiles, library, guardian console, intake | 3-5 weeks |
| **First usable release** | Phase 4a (Phase 3 already merged) | **3-5 weeks** |
| Phase 4b | Editor, TTS, ending tracker | 2-4 weeks |
| Phase 5 | Hardening, deploy, restore drill | 2-3 weeks |
| **Full v1** | First release + 4b + 5 | **+4-7 weeks** |

## Related documents

- [Development Roadmap](./roadmap.md) (phase definitions)
- [Project Plan](./PROJECT-PLAN.md) (detailed phase tasks and quality gates)
- [Phase 2b: live providers and yield](./phase-2b-live-provider.md)
- [ADR-005: mandatory human approval](./adr/adr-005-mandatory-human-approval.md)
