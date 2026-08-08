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
purpose: "A repeatable checklist to verify the live deployment end to end before declaring R1 done, and
  after any subsequent image redeploy."
component: Strategy
source: "Originated as Task 4.1 of the R1 gap-closure plan (merged, doc archived); journey map in
  docs/architecture/user-journeys.md; PR #112 smoke tier (frontend/e2e-real/) as the pre-deploy harness"
---

## How to use this checklist

Run top to bottom against `https://cyo.williamshome.family` after every deploy. The PR #112 real-backend
smoke tier (`frontend/e2e-real/`, `npm run test:e2e:real`, local-only, `--workers=1`) is the automated
pre-deploy gate against a local stack; this checklist is the manual post-deploy verification against prod.

**Accounts** (prod seeding is manual; NEVER run `scripts/seed_dev_data.py` in prod).
Both accounts below are real Supabase email/password logins. Role columns verified
directly against the production database on 2026-08-04:

| Capability | Email | Supabase sub | `role` | `is_admin` | Family |
| --- | --- | --- | --- | --- | --- |
| Guardian (author, assign) | `byron.a.williams@gmail.com` | `c1f33430` | `guardian` | `false` | `3a152319` |
| Guardian + admin (approver) | `byronawilliams@gmail.com` | `21985c35` | `guardian` | `true` | `3a152319` |

**Correction, 2026-08-04.** This section previously stated that `User.role` is an
exclusive enum so "one account cannot be both roles", and labelled the second
account's role as `admin`. Neither holds against the live schema. `role` is the
base enum; `is_admin` is an **orthogonal boolean capability**. Sub `21985c35` is
therefore a guardian in family `3a152319` *and* an admin at the same time, and no
account in production has `role = 'admin'` at all. Two consequences for the steps
below: switching accounts to approve is a convenience rather than a requirement,
because the approving account sits in the same family and can both author and
approve (the four-eyes collapse this project accepted for a single family); and
Section 1a's "lands on a review queue, not the guardian console" expectation needs
re-deriving, because a `role='guardian'` account lands on the guardian console by
design and reaches `/admin` as an added capability.

**That re-derivation was done on 2026-08-08 and Section 1a is rewritten.** The old
expectation was unsatisfiable by any production account, so it was a defect in this
checklist rather than in the product; the corrected assertion and the code that
settles it are recorded in Section 1a.

A third adult account exists that this checklist does not use and must not
disturb: sub `774ea02b`, also dual-role, in its own isolated "E2E Test Family"
(`84b96700`). It belongs to the automated `e2e-prod` tier described below. Its
login is the `E2E_PROD_TEST_EMAIL` secret in the `production-e2e` environment,
named here rather than written out: this repository is public, and an address
that signs in with `is_admin` should not be published as a phishing or
credential-stuffing target. The secret is also the authoritative source, so a
literal copy here could go stale against the account the workflow actually uses.

The real read gate is `approved_by` + an assignment, not `published_at` alone.
Approval requires `is_admin` per ADR-005 (`storybook_version.approved_by`); the
guardian-only account (`c1f33430`) will correctly get a 403 on approve.

### What the automated `e2e-prod` tier already covers

`.github/workflows/e2e-prod.yml` runs `frontend/e2e-prod/` against this same live
host on a daily cron, using the isolated `774ea02b` test account. As of run
[30918192801](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30918192801)
(2026-08-04, success, 2m50s) that tier is green again, having been queue-starved
from 2026-07-18 to 2026-08-02 by the `waiting`-run defect its own workflow comments
describe. It asserts, unattended and every day:

- The landing page renders its `h1` and both audience doors.
- The guardian sign-in form renders its email, password, and submit controls.
- A dual-role adult reaches all nine `/guardian/*` and `/admin/*` pages with the
  expected `h1` and no error boundary.
- A real device grant round-trips: authorize, open the kid library on the
  authorized device, revoke.

**Revised 2026-08-08.** The paragraph that stood here said none of those steps could
be ticked from this tier, because it drives a *different* account in a *different*
family and asserts renders rather than journeys. That reasoning was too strict, and
holding to it left steps unticked that the tier genuinely settles. The distinction
that actually matters is what a step claims, not which account produced the evidence:

- Steps that assert a **property of the deployed system** are settled by this tier
  whichever account exercises them. An unauthenticated redirect, the absence of the
  Apple button, the readiness probe's content type, and a dual-role adult's landing
  surface do not vary by family. Those are ticked, each citing the spec and date.
- Steps that assert a **journey through specific data** are not. Anything about the
  real family's books, requests, or children needs the accounts in the table above,
  because the test account's family is separately seeded.

Since 2026-08-05 the tier has also stopped being uniformly green: three consecutive
runs failed on the two profile-count assertions, which is how issue
[#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639) was found. A red
tier is doing its job here. Note the corollary for the steps it covers: a serial
describe block aborts at its first failure, so a green *tier* is not the same as an
executed *step*, and any step ticked from this tier must cite a test that actually
ran rather than a suite that passed.

### Known blockers (resolve before running this checklist end to end)

- **API keys must be funded before Sections 2 and 4.** Both OpenRouter
  (generation) and the OpenAI classifier (Stage-0 moderation) need funded
  quota before the generation-touching sections run. A 429 quota exhaustion on
  the classifier fails silently from the operator's point of view: the
  generation job stalls at the moderation step with no obvious error in the
  UI, so check worker logs for 429s if a job hangs there.

## 0. Infrastructure probes

- [x] `https://cyo.williamshome.family` resolves through Pangolin to docker-host:443 with a valid TLS cert
      (2026-08-04: HTTP 200, OpenSSL verify result 0, wildcard `CN=*.williamshome.family` issued by
      ZeroSSL RSA DV SSL CA 2, valid 2026-06-23 to 2026-09-21)
- [x] Frontend loads (React shell renders, no console errors about missing Supabase config; this proves the
      image was built with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` build args). Verified 2026-08-04
      by fetching all 75 served chunks: `assets/supabaseClient-UGD8VVQK.js` carries both the
      `cvrnaydpzijtszfbsraq.supabase.co` project URL and an anon-key JWT, so the build args were present at
      image build time. That is the direct form of this check; absence of console errors is only its proxy.
      `sw.js` and `registerSW.js` also return `Cache-Control: no-store, no-cache, must-revalidate`, so the
      stale-service-worker login loop that `frontend/nginx.conf` guards against cannot recur.
- [x] `GET /api/v1/health/live` and `/api/v1/health/ready` return 200 **with
      `content-type: application/json`**. Assert the content type, not just the status: see the defect
      below for why a bare 200 is not evidence here. **Verified 2026-08-08**, and the redeploy this step
      was blocked on has happened: production now serves revision `631c0d8a` (v0.68.0), which carries the
      `UW-L04` fix. The evidence is `frontend/e2e-prod/health-probe.spec.ts` on the daily cron, whose
      three assertions have passed against live production on 2026-08-05, 2026-08-06 and 2026-08-07:
      the canonical endpoint answers as real FastAPI JSON, the old shadowed `/health` path returns
      exactly 404, and the `/nginx-health` control answers. Those three together are what a bare status
      check cannot give you: the 404 proves nginx's stub is gone rather than merely moved, and the
      control proves nginx is up, so a green canonical probe cannot be nginx answering for FastAPI.
      Prefer that spec over a hand-run `curl` from a workstation, which on this network resolves
      `cyo.williamshome.family` to a LAN address by split-horizon DNS and does not traverse the ingress
      path CI exercises.

      **The prior "verified live 2026-07-07: both 200" note was a false pass, and the defect it hid is
      worth understanding.** Established 2026-08-04: every backend router except `health` carried its own
      `/api/v1` prefix, and `frontend/nginx.conf` proxies only `location /api/`. `health.router` was
      declared `APIRouter(prefix="/health")`, so it sat outside the proxied prefix and was unreachable
      through the ingress. Meanwhile nginx defined `location /health { return 200 'OK'; }` for its own
      container probe, which shadowed the path entirely. So `GET /health/ready` returned a two-byte
      `text/plain` `OK` from nginx (note the duplicated `Content-Type` header, and `server: nginx`)
      while FastAPI's readiness logic never executed. The 200 proved nothing about database
      connectivity, and any uptime monitor pointed at that URL would have reported healthy with the
      database completely down. Contrast `GET /api/v1/me`, which correctly returned
      `401 application/json` from FastAPI.

      Fixed on this branch (`UW-L04`): the health router is now also mounted at `/api/v1/health/*`, which
      is the canonical form and the only one reachable from outside; nginx's own stub moved to the exact
      path `= /nginx-health`; and `location /health` now returns `404` so a stale probe fails loudly
      instead of silently receiving the SPA shell. The un-prefixed `/health/*` still answers on port 8000
      inside the container, because the production healthcheck lives out-of-repo in homelab-infra and
      polls it. `/nginx-health` is the useful control: if it answers while `/api/v1/health/ready` does
      not, the frontend is serving and the backend is unreachable behind it.
- [x] Redis and the RQ worker containers are up (`docker ps` on docker-host; worker listens on queue
      `generation`). Verified 2026-08-04: `cyo-adventure-redis` up 3h (healthy), `cyo-adventure-worker`
      up 2h (healthy), and worker logs show repeated `BLMOVE` polling on `rq:queue:generation`.
- [x] Migrations current (migrate profile ran; `supabase migration list --linked` shows no pending
      migrations). As of 2026-07-10 this replaces the prior `alembic current` check: schema migrations
      moved from Alembic to Supabase CLI SQL migrations (ADR-012). Verified 2026-08-04 against the live
      project: 49 files in `supabase/migrations/` and 49 applied versions, an exact set match in both
      directions (nothing pending, nothing applied that is missing locally), newest
      `20260804070000_add_security_event_table`.
- [x] Backups confirmed: the local `db-backup` container is healthy (`docker ps` on docker-host)
      AND a fresh `.dump` file is present under
      `/mnt/unraid/appdata/cyo-adventure/backups`. As of 2026-07-07 this container runs a daily
      `pg_dump -Fc` of the LIVE Supabase database's `public` schema (14-day retention), fixed via
      homelab-infra #585/#586; Supabase-side backups/PITR also exist independently. Do not assume
      Supabase backups alone satisfy this check: verify the local dump too. Verified 2026-08-04:
      `cyo-adventure-db-backup` up 3h (healthy); newest dump `cyo_adventure_20260804_185541.dump`
      (1,189,372 bytes) written the same day, with an unbroken daily series behind it and `.last_success`
      also stamped that day.
- [ ] Worker survives a restart (`docker compose restart worker`; queued/in-flight jobs resume or
      re-queue rather than being lost). NOT RUN on 2026-08-04: this is the only Section 0 step that
      mutates production, so it was deliberately left for an authorized maintenance window rather than
      bounced during an unattended verification pass.

## 1. Guardian sign-in and profiles

- [x] Unauthenticated visit to `/guardian` redirects to login. Verified 2026-08-08 by
      `guardian-profiles.spec.ts:36` on the daily production cron; it asserts the destination pathname
      (`ProtectedRoute` carries the attempted location in router state, not the URL) plus the rendered
      sign-in heading.
- [x] Guardian email/password sign-in succeeds (Apple button hidden behind its config flag per ADR-009).
      Verified 2026-08-08. Two independent signals in the same run: `signInAsProdTestAdmin` completes
      and every authenticated test downstream of it reaches a rendered console, and
      `guardian-profiles.spec.ts:48` asserts Apple is absent *while* asserting Google is present, so a
      page that rendered no provider buttons at all cannot satisfy the absence claim vacuously.
- [ ] Create or edit a child profile; preset avatar picker works. **NOT RUN on 2026-08-08.** The
      read-only half (opening the dialog to confirm the avatar picker renders) is automated at
      `guardian-profiles.spec.ts:89`, but it did not execute: its serial describe block aborted at the
      preceding test, which failed on issue [#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639).
      The create/edit half mutates the live family and stays manual regardless.
- [ ] Sign out and back in; session resumes. **NOT RUN on 2026-08-08**, same serial-block abort as
      above (`guardian-profiles.spec.ts:104`). Nothing suggests it is broken; it simply never executed.

## 1a. Admin sign-in and review queue access

Approving account: `byronawilliams@gmail.com` (sub `21985c35`, `role='guardian'` with
`is_admin=true`, family `3a152319`). It is not `role='admin'`; see the Correction in
the Accounts section above.

- [x] Admin email/password sign-in succeeds. Verified 2026-08-08 by `guardian-admin-smoke.spec.ts:67`
      on the daily production cron: all nine surfaces render for this account, four under `/admin`
      (`/admin`, `/admin/requests`, `/admin/moderation-thresholds`, `/admin/moderation-dashboard`),
      which an account without the admin capability could not reach.
- [x] Sign-in lands on the **Guardian** console (`/guardian`); the Admin console is reachable from
      there via the "Admin console" nav link. **The expectation was re-derived on 2026-08-08 and this
      line was corrected: the old "not the guardian console" wording was wrong, not the product.**
      `LoginPage.tsx` computes the post-sign-in destination as
      `principal?.role === 'admin' ? ADMIN_CONSOLE_PATH : GUARDIAN_CONSOLE_PATH`, so it branches on the
      base `role` alone and `is_admin` does not affect the landing surface at all. This account is
      `role='guardian'` with `is_admin=true`, so `/guardian` is the correct and intended destination.
      The capability surfaces as cross-links instead: `GuardianShell.tsx` renders the "Admin console"
      link only when `principal?.isAdmin`, and `AdminShell.tsx` renders the return link only when
      `role === 'guardian'`. Verified against live production in the same cron run, whose captured
      guardian navigation carries the Admin console link. No defect: the old assertion would have been
      satisfiable only by an account with `role='admin'`, and no production account has that role.

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

The "if seeded" hedge below is obsolete, and resolving it makes this section cheaper to run than it
looks. **Re-verified by direct read-only query on 2026-08-08: production now holds four families, not
the three recorded on 2026-08-04, and the real family has gained a third child profile.** Re-run this
query rather than trusting the table, because both numbers have moved once already:

| Family | Created | Contents | Role here |
| --- | --- | --- | --- |
| `3a152319` | 2026-07-05 | **3** active profiles, 4 users, 1 story request | the real family |
| `84b96700` | 2026-07-15 | 1 active profile, 2 users, 0 story requests | E2E test family |
| `0ca7a109` | 2026-07-20 | nothing at all, and **no user rows** | orphan, see `UW-L05` |
| `adb9e257` | 2026-08-05 | 0 profiles, 0 requests, but **1 guardian user** | new, see `UW-L05` |

The automated test account already sits in `84b96700`, so it *is* the second family's guardian. That
makes this section verifiable read-only with no extra seeding: the assertion is that the test account
sees exactly its own 1 profile and 0 story requests while the real family has 3 and 1.

`adb9e257` is a different shape from `0ca7a109` and is the more interesting of the two. It has a
guardian user, so unlike the orphan it is reachable and could in principle be signed into, which makes
it the first genuine third-family cross-family subject this checklist has ever had. It is folded into
`UW-L05` because it is the same provenance question: guardian accounts are created by an empty
`POST /v1/onboarding` with no signup form, so both rows sit on the path a partially-failed or
unattended JIT provisioning would leave behind.

**A drift trap this creates, worth fixing before it bites.** `guardian-books-and-isolation.spec.ts`
carries a comment justifying its `toHaveCount(1)` as "not 2, and certainly not 3, the sum across every
family in the database". Both numbers in that sentence are now wrong: the real family holds 3 and the
database-wide sum is 4. The assertion is still correct and still fails correctly, but its stated reason
no longer distinguishes the case it was written to catch, so anyone re-deriving the expectation from
the comment will reach a false conclusion. Assertions pinned to live production data need their
justifying counts re-checked whenever this table moves.

- [ ] A second family's guardian cannot see the first family's requests, books, or children.
      **Automated** in `frontend/e2e-prod/guardian-books-and-isolation.spec.ts`.
      **FAILING against live production as of 2026-08-08**: issue
      [#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639) / `UW-L07`. Do not tick this
      until that fix is deployed. The failure is not an isolation breach; it is the opposite, an
      over-restriction that returns zero rows to everyone.
      #ASSUME: data integrity: this is an emptiness assertion, so it passes vacuously against a page
      that failed to render at all. #VERIFY: the spec asserts the heading and empty-state copy render
      *before* asserting the count; keep that positive control if you edit it.
      **The positive control was necessary but not sufficient, and #639 is the proof.** The requests
      half of this test asserts the E2E family sees zero story requests, with the heading and the
      component's own empty-state copy as its control. Under #639 the page renders perfectly and the
      count is genuinely zero, because `story_request` is `family_scoped` too and the same missing GUC
      empties it for every caller. So that assertion passed, on a build where cross-family scoping was
      not working at all. Only the profiles half caught it, and only because it expects a **non-zero**
      count. #VERIFY: an emptiness assertion over a Tier 1 table needs a non-empty companion assertion
      in the same test, over a table subject to the same policy; a rendered-heading control proves the
      page loaded, never that the scoping mechanism ran.
- [ ] Kid surfaces never expose guardian-only fields. The concrete contract (`api/review_surface.py`)
      is that guardian-facing responses are story-level and node-id-free: they carry `flagged_count`,
      `node_count`, and merged concern rows, and never `flagged_passages` or raw node `prose`.
      **Partially automated**: the spec above scans every observed `/api/v1/**` JSON body for those two
      forbidden keys. The kid-surface half (story-request responses carrying id/status only) is NOT
      automated, because the test family has 0 story requests, so the assertion would pass vacuously.
      Creating one costs LLM spend, which is why this is still a manual step.

## Sign-off

| Run date | Image tags (backend/frontend) | Result | Notes |
| --- | --- | --- | --- |
| 2026-08-04 | both at revision `f1b561b6` (v0.63.0); backend `@sha256:de9a9f6a`, frontend `@sha256:4d608898` | PARTIAL, 5 of 38 steps | Section 0 only. Sections 1 to 6 not run. Detail below. |
| 2026-08-08 | both at revision `631c0d8a` (v0.68.0); backend `@sha256:6a92ab44`, frontend `@sha256:7d7bd249` | **PARTIAL, 10 of 38 steps, and a live P1 defect found** | Sections 0, 1, 1a advanced from CI evidence. `UW-L04` confirmed deployed. Section 1a's open routing question resolved from code. Guardian profile resolution is broken in production: [#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639) / `UW-L07`. Detail below. |

### 2026-08-04 partial run

This checklist has 38 steps, not the 39 the work register long claimed; the register row
has been corrected.

**Deployed revision.** Established from image labels on `docker-host`, not from an HTTP
probe: `/openapi.json` at the public host returns the SPA shell rather than the schema, so
it cannot identify the backend. Both `cyo-adventure-backend` and `cyo-adventure-frontend`
carry `org.opencontainers.image.revision=f1b561b6156b1f68177ca472fa042a40fbaea445`, which
is `chore(release): v0.63.0 (#606)`. Production is one release behind `main`, which reached
v0.64.0 (`b53cd765`) the same day. Note that `org.opencontainers.image.version` reads
`0.1.0` on both images and does not track releases, so the revision SHA is the only
reliable deployed-version identifier here.

**What ran.** Section 0 only, from this repository plus `docker-host` and the live Supabase
project. 5 of its 7 steps are ticked. The two that are not fail for different reasons: the
health-probe step is not runnable as written and turned out to be a false pass (`UW-L04`),
and the worker-restart step mutates production, so it was left for an authorized
maintenance window rather than bounced during an unattended pass.

**What did not run.** Sections 1, 1a, 2, 3, 4, 5, and 6, all 31 remaining steps. Every one
needs interactive sign-in as `c1f33430` or `21985c35`, whose credentials this pass did not
have. Sections 2 and 4 additionally spend real OpenRouter and classifier quota and write
real content into the live family, so they need explicit authorization rather than just
credentials. Sections 5 and 6 also need a second device and a real offline
transition. Section 6's premise was revisited rather than assumed: the live database holds
**three** `family` rows, not the two an earlier draft of this note claimed, but the third
(`0ca7a109`) has no `user` rows and so cannot be signed into or used as a cross-family
subject; it is recorded as a finding in its own right (`UW-L05`). The check is still
meaningful with two usable families, because the test account sits in `84b96700` while
`3a152319` holds data it must never see, which is what Section 6 below now asserts.

**What was automated instead of left manual.** The 33 unticked steps are two populations
with different gates, not one: 31 in Sections 1 to 6 that need interactive credentials, plus
the 2 Section 0 blockers, which needed a code fix (the health probe, `UW-L04`) and an
authorized maintenance window (the worker restart) rather than a sign-in. Rather than leaving
all of them waiting on a human, the read-only remainder moved into the existing `frontend/e2e-prod/`
tier, which already signs in as a real production account unattended on a daily cron. Three
specs were added: `health-probe.spec.ts` (the Section 0 step this pass got wrong, now
asserted by content type with an `/nginx-health` control so a failure distinguishes "backend
unreachable through the ingress" from "site down"), `guardian-profiles.spec.ts` (Section 1's
route guard, login surface, profile list, and sign-out), and
`guardian-books-and-isolation.spec.ts` (Section 3's books and review surface, the guardian
redaction contract enforced by scanning every `/api/v1` JSON body the suite sees, and
Section 6's cross-family isolation). A count or empty-state assertion is only trustworthy
if the page rendered at all, so each one is preceded by a positive control, and the
redaction scan asserts the collector captured something before concluding it found no
leaks.

Two honest limits on that automation. It asserts the **post-fix** state of the ingress, so
the daily cron will fail until production redeploys both the backend and frontend images;
that failure is the redeploy reminder, not a regression. And assertions that depend on live
moderation content are deliberately conditional, because a clean catalog at test time would
otherwise make them vacuous, which means a break in the redacted-projection rendering path
would be caught only by the response-body scan.

**Confirmed alongside this run, closing the one leg `UW-A03` left open.** The RQ worker
authenticates to production as `cyo_worker`. Proof is read-only and was taken from inside
the running `cyo-adventure-worker` container through the application's own
`get_worker_session()`: `current_user` and `session_user` both return `cyo_worker`,
`rolbypassrls` is `false` so the ADR-022 Tier 1 policies bind, and `pg_stat_activity`
observed from that same connection showed `cyo_api` on 5 connections, `cyo_worker` on 1,
and `postgres` on none. No generation job was triggered and no LLM quota was spent: the
credential path was what needed proving, not the pipeline.

One nuance to carry forward from that check. `WORKER_DATABASE_URL` is **unset** on the
deployed worker container. `worker_database_url_effective` falls back to `database_url`,
and the homelab stack sets that container's own `DATABASE_URL` to the `cyo_worker` DSN, so
the correct role is reached by container-level environment rather than by the
`WORKER_DATABASE_URL` split that this repository's `docker-compose.prod.yml` configures.
The outcome is right and the ADR-021 goal is met, but the mechanism differs from the
compose file, and inside the worker process `get_session()` and `get_worker_session()`
resolve to the same identity. A regression in which worker code calls `get_session()`
would therefore be invisible in production. Tracked as `UW-A44`.

### 2026-08-08 partial run

**Deployed revision.** Both `cyo-adventure-backend` and `cyo-adventure-frontend` on `docker-host`
carry `org.opencontainers.image.revision=631c0d8a1ed7d9e69ea0dee73607009b31dd4c6d`, which is
`chore(release): v0.68.0 (#638)`. Production is level with `main` for the first time in this
checklist's history; the 2026-08-04 run found it one release behind. As before,
`org.opencontainers.image.version` reads `0.1.0` on both images and tracks nothing, so the revision
SHA remains the only reliable deployed-version identifier.

**What ran, and what it cost.** No interactive session and no production mutation. Everything ticked
here rests on the daily `e2e-prod` cron (`.github/workflows/e2e-prod.yml`), which signs into live
production as the real isolated test account, plus read-only queries against the live Supabase project
and `docker inspect` on `docker-host`. The run for `631c0d8a` on 2026-08-07 reports **21 passed, 2
failed**. Five further steps ticked, taking the checklist from 5 to 10 of 38.

**`UW-L04` is closed out here.** The health-probe step had been blocked on a redeploy since 2026-08-04.
That redeploy has happened, and `health-probe.spec.ts`'s three assertions have passed on three
consecutive days. This also corrects a stale belief worth naming: the fix was recorded internally as
"merged but not deployed", and the CI evidence falsifies that. A merge-versus-deploy claim about
production should be settled against a probe that ran from outside, not against merge state.

**Section 1a's open question is resolved, and the checklist was wrong, not the product.** The old
assertion demanded that the approving account land somewhere other than the guardian console.
`LoginPage.tsx` branches solely on the base `role`, so a `role='guardian'` account with `is_admin=true`
lands on `/guardian` by design and reaches `/admin` through a capability-gated nav link. Since no
production account has `role='admin'`, the old assertion was unsatisfiable by anything in production.
The step is rewritten to assert the real contract and is ticked.

**A live P1 defect, found by the run rather than by the checklist.**
Issue [#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639), register row `UW-L07`.
`require_principal` resolves a guardian's child profiles from the Tier 1 `child_profile` table roughly
36 lines *before* it calls `apply_family_rls_context`. With `app.family_id` unset,
`current_setting(..., true)` is NULL, the `family_scoped` predicate is unsatisfiable, and the read
returns zero rows. Every guardian in production therefore has an empty `profile_ids`;
`GET /v1/profiles` short-circuits on it and the console renders "No profiles yet" over a family that
has three children. The failure is fail-closed, so this is an outage of the profiles surface and not a
data leak, and the underlying rows are intact.

Three things about it are worth carrying forward:

- **Why it stayed invisible.** RLS never applies to a table's owner. Before ADR-021 the API connected
  as `postgres`, so the policy was inert and the ordering bug had no effect. The cutover to `cyo_api`
  is what activated it. Any ordering bug of this shape is undetectable until the cutover lands, which
  is an argument for testing as the non-owner role rather than for testing more.
- **It is a recurrence, not a novel bug.** `_device_principal` already applies the context before its
  Tier 1 reads and carries a `#CRITICAL` comment naming the identical staging outage of 2026-07-18 to
  2026-08-02. That fix was applied to the device branch only. A fix that names its own failure mode in
  a comment but is applied to one call site is a half fix.
- **The regression test that would have caught it did not exist.**
  `tests/integration/test_rls_tier1_enforcement.py` covers the device branch and has no guardian
  equivalent exercising the real `require_principal` path as `cyo_api`.

**An isolation assertion that passed for the wrong reason.** See Section 6. The requests-queue half of
the cross-family test was satisfied *by* #639: `story_request` is `family_scoped` too, so it returned
zero rows to everyone while the page rendered perfectly and its positive control held. Only the
profiles half, which expects a non-zero count, caught the failure. A rendered-heading control proves
the page loaded; it never proves the scoping mechanism ran.

**Production data has drifted since 2026-08-04** in two ways that affect assertions, not just
inventory: a fourth family (`adb9e257`) appeared on 2026-08-05 carrying one guardian user and no
profiles, and the real family gained a third child profile. Section 6's table is updated and the
consequences for the isolation spec's justifying comment are recorded there.

**Owner-gated remainder, unchanged in shape from 2026-08-04.** The 28 untouched steps need one of
four things this pass could not supply: interactive credentials for subs `c1f33430` and `21985c35`;
an authorized maintenance window for the single mutating Section 0 step (worker restart); funded
OpenRouter and classifier quota plus permission to write real content into the live family
(Sections 2 and 4); and a second physical device with a real offline transition (Section 5). None is
blocked on engineering. Note also that Section 1's remaining steps are now blocked twice over: they
are gated on an interactive session, and their automated read-only halves cannot execute until #639
is fixed, because the serial describe block aborts at the failing test ahead of them.
