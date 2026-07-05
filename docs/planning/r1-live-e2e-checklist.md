---
schema_type: planning
title: "R1 Live E2E Checklist (cyo.williamshome.family)"
description: "Manual end-to-end verification checklist for the R1 internal-web deployment, covering the full
  kid-request, guardian-review, assign, and read journey against the production stack."
tags:
  - planning
  - testing
  - release
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Task 4.1 of the R1 gap-closure plan: a repeatable checklist to verify the live deployment end to end
  before declaring R1 done, and after any subsequent image redeploy."
component: Strategy
source: "docs/planning/r1-gap-closure-plan.md Task 4.1; journey map in docs/architecture/user-journeys.md;
  PR #112 smoke tier (frontend/e2e-real/) as the pre-deploy harness"
---

## How to use this checklist

Run top to bottom against `https://cyo.williamshome.family` after every deploy. The PR #112 real-backend
smoke tier (`frontend/e2e-real/`, `npm run test:e2e:real`, local-only, `--workers=1`) is the automated
pre-deploy gate against a local stack; this checklist is the manual post-deploy verification against prod.

**Accounts** (prod seeding is manual; NEVER run `scripts/seed_dev_data.py` in prod).
Source the real email + Supabase `sub` for each role from the private deployment
runbook (kept out of the repo); the placeholders below stand in for them:

| Role | Email | Supabase sub |
| --- | --- | --- |
| Guardian | `<GUARDIAN_EMAIL>` | `<GUARDIAN_SUB>` |
| Admin | `<ADMIN_EMAIL>` | `<ADMIN_SUB>` |

The real read gate is `approved_by` + an assignment, not `published_at` alone.

## 0. Infrastructure probes

- [ ] `https://cyo.williamshome.family` resolves through Pangolin to docker-host:443 with a valid TLS cert
- [ ] Frontend loads (React shell renders, no console errors about missing Supabase config; this proves the
      image was built with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` build args)
- [ ] `GET /api/v1/health/live` and `/api/v1/health/ready` return 200 (ready proves DB connectivity)
- [ ] Redis and the RQ worker containers are up (`docker ps` on docker-host; worker listens on queue
      `generation`)
- [ ] Alembic migrations current (migrate profile ran; `alembic current` matches head)

## 1. Guardian sign-in and profiles

- [ ] Unauthenticated visit to `/guardian` redirects to login
- [ ] Guardian email/password sign-in succeeds (Apple button hidden behind its config flag per ADR-009)
- [ ] Create or edit a child profile; preset avatar picker works
- [ ] Sign out and back in; session resumes

## 2. Guardian authoring path (intake to published book)

- [ ] Submit a story request via Intake; job status shows "Generating..."
- [ ] RQ worker picks up the job (worker logs show the generation; OpenRouter + classifier calls succeed)
- [ ] Story lands in the review queue; queue orders Flagged, then Ready, then processing
- [ ] Review detail shows the story and any moderation flags
- [ ] Approve as ADMIN succeeds (ADR-005: approve is admin-only; verify the guardian account gets the
      403 "safety reviewer" notice instead)
- [ ] Send-back / revision loop works on a second story

## 3. Assignment surfaces

- [ ] Books page lists published books with content badges; assign to a child from there
- [ ] Assign dialog shows redacted content-review tags (category/verdict/message only; no raw
      moderation payloads anywhere in guardian-facing responses)
- [ ] "Assign more" flow from the console works

## 4. Kid request-a-story loop (the completed R1 journey)

- [ ] Kid library shows the request-a-story affordance
- [ ] Submit a request; friendly status appears in the kid's status list (id/status only on the wire)
- [ ] Submit text with obvious PII (a phone number); PII guard blocks it before classifier spend
- [ ] Submit 5 pending requests; the 6th gets the distinct 409 cap message
- [ ] Guardian Requests queue shows the pending request with redacted screening flags
- [ ] Approve creates a Concept + GenerationJob; generation runs; book publishes (admin approve)
- [ ] Assign the generated book; it appears in the kid's library

## 5. Kid reading loop

- [ ] Open an assigned book; reader plays through choices to an ending
- [ ] Completion is recorded (guardian progress view reflects it)
- [ ] Close mid-story, reopen on a second device/browser; progress resumes from the server
- [ ] Offline read works (airplane mode after load); progress syncs on reconnect
      (KNOWN DEBT: offline completions are fire-and-forget; see the deferred-debt register)
- [ ] Rate a finished book

## 6. Cross-family isolation spot check

- [ ] A second family's guardian (if seeded) cannot see the first family's requests, books, or children
- [ ] Kid surfaces never expose guardian-only fields (spot check network tab: story-request responses
      carry id/status only)

## Sign-off

| Run date | Image tags (backend/frontend) | Result | Notes |
| --- | --- | --- | --- |
|  |  |  |  |
