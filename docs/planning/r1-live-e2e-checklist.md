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
Both accounts below are real Supabase email/password logins. `User.role` is an
exclusive enum, so one account cannot be both roles: author with the guardian
account, then switch to the admin account to approve. Values current as of
2026-07-05:

| Role | Email | Supabase sub | Sign-in |
| --- | --- | --- | --- |
| Guardian (author, assign) | `byron.a.williams@gmail.com` | `c1f33430` | email/password |
| Admin (content approver) | `byronawilliams@gmail.com` | `21985c35` | email/password |

The real read gate is `approved_by` + an assignment, not `published_at` alone.
Approval is admin-only per ADR-005 (`storybook_version.approved_by`); the guardian
account will correctly get a 403 on approve.

### Known blockers (resolve before running this checklist end to end)

- **API keys must be funded before Sections 2 and 4.** Both OpenRouter
  (generation) and the OpenAI classifier (Stage-0 moderation) need funded
  quota before the generation-touching sections run. A 429 quota exhaustion on
  the classifier fails silently from the operator's point of view: the
  generation job stalls at the moderation step with no obvious error in the
  UI, so check worker logs for 429s if a job hangs there.

## 0. Infrastructure probes

- [ ] `https://cyo.williamshome.family` resolves through Pangolin to docker-host:443 with a valid TLS cert
- [ ] Frontend loads (React shell renders, no console errors about missing Supabase config; this proves the
      image was built with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` build args)
- [ ] `GET /api/v1/health/live` and `/api/v1/health/ready` return 200 (ready proves DB connectivity)
- [ ] Redis and the RQ worker containers are up (`docker ps` on docker-host; worker listens on queue
      `generation`)
- [ ] Alembic migrations current (migrate profile ran; `alembic current` matches head)
- [ ] Supabase backups confirmed (DB is on the Supabase session pooler post-cutover; Supabase owns
      backups/PITR. The old local `db-backup` sidecar is retired via homelab-infra #577, so do NOT
      expect a local backup container.)
- [ ] Worker survives a restart (`docker compose restart worker`; queued/in-flight jobs resume or
      re-queue rather than being lost)

## 1. Guardian sign-in and profiles

- [ ] Unauthenticated visit to `/guardian` redirects to login
- [ ] Guardian email/password sign-in succeeds (Apple button hidden behind its config flag per ADR-009)
- [ ] Create or edit a child profile; preset avatar picker works
- [ ] Sign out and back in; session resumes

## 1a. Admin sign-in and review queue access

Admin account: `byronawilliams@gmail.com` (role `admin`, sub `21985c35`).

- [ ] Admin email/password sign-in succeeds
- [ ] Sign-in lands on a review queue that loads (not the guardian console)

## 2. Guardian authoring path (intake to published book)

- [ ] Submit a story request via Intake; job status shows "Generating..."
- [ ] RQ worker picks up the job (worker logs show the generation; OpenRouter + classifier calls succeed)
- [ ] Story lands in the review queue; queue orders Flagged, then Ready, then processing
- [ ] Review detail shows the story and any moderation flags
- [ ] Guardian account (`byron.a.williams`) attempting approve gets the 403 "safety reviewer" notice
      (ADR-005: approve is admin-only)
- [ ] Approve as ADMIN (`byronawilliams`) succeeds
- [ ] Send-back / revision loop works on a second story

## 3. Assignment surfaces

- [ ] Books page lists published books with content badges; assign to a child from there
- [ ] Assign dialog shows redacted content-review tags (category/verdict/message only; no raw
      moderation payloads anywhere in guardian-facing responses)
- [ ] "Assign more" flow from the console works

## 4. Kid request-a-story loop (the completed R1 journey)

- [ ] From the guardian console, hand off to the kid surface; the profile picker appears and selecting a
      profile lands on that child's library
- [ ] Kid library shows the request-a-story affordance
- [ ] Submit a request; friendly status appears in the kid's status list (id/status only on the wire)
- [ ] Submit text with obvious PII (a phone number); PII guard blocks it before classifier spend
- [ ] Submit 5 pending requests; the 6th gets the distinct 409 cap message
- [ ] Guardian Requests queue shows the pending request with redacted screening flags
- [ ] Guardian approves the request; a Concept + GenerationJob is created, generation runs, and the book
      reaches the admin review queue with content tags
- [ ] Admin (`byronawilliams`) approves; guardian then assigns from the browse
      page, seeing the same content tags, and the book appears in the kid's library

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
