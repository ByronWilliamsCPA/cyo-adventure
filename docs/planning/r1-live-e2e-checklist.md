---
schema_type: planning
title: "R1 Live E2E Checklist (cyo.williamshome.family)"
description: "End-to-end verification checklist for the R1 internal-web deployment, covering the full
  kid-request, guardian-review, assign, and read journey against the production stack. Steps are settled
  either by an automated production test or by a manual pass, per the evidence tiers below."
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

## Status at a glance (updated 2026-11-20)

Two step populations live in this document, counted separately so that the "10 of 38" other documents cite
stays meaningful. The original 38 steps (Sections 0 to 6) are unchanged in wording, order, and tick state; where
one is now wrong or superseded it carries a dated note in place. The 2026-11 additions have their own identifiers
(letter plus number, for example `A3`) and their own count.

| Population | Steps | Ticked | Last run | Where |
| --- | --- | --- | --- | --- |
| Original R1 checklist | 38 | 10 | 2026-08-08, revision `631c0d8a` (v0.68.0) | Sections 0 to 6 |
| 2026-11 additions | 41 | 0 | not yet run; written against `main` at v0.92.0 | [2026-11 additions](#2026-11-additions) |
| First family session (catalog only) | 53 required, 2 optional | 0 | not yet run | [run list](#first-family-session-catalog-only) |

**How to cite an original step.** The original 38 boxes carry no numbers, and they are not renumbered here. Cite
them by section and position: `0.3` is the third box in Section 0, `1a.2` the second box in Section 1a, `5.4`
the fourth box in Section 5. No box is ever inserted into an original section, so those positions are stable.

## First family session (catalog only)

Added 2026-11-20. This is the run list for the first session with real readers: the owner's four children,
roughly ages 9 to 15, each on their own device, reading **catalog books only**. It is self-contained: work it
top to bottom, and follow each step reference to its full text for the expected result and evidence.

**Owner decisions that shape this path (2026-11-20).**

- **Catalog only.** No on-demand generation and no kid story requests in this session. Sections 2 and 4 (intake,
  generation, send-back, the kid request loop, and their funded generation quota) are **deferred** for this path,
  with one exception: step `4.1` (the guardian-to-kid hand-off) exercises no generation and is included. Sections
  2 and 4 remain valid for a later sign-off.
- **Deploy parity comes before anything else.** Production image pulls involve a manual step, and migrations are
  applied separately by dispatching `supabase-production.yml`, so the app and the schema can drift apart. They
  have before (register row `UW-C363`: 18 migrations behind, every authenticated adult request 500ing, fixed by
  hand 2026-08-24), and the daily `e2e-prod` run has failed since 2026-09-14 on the guardian books page and the
  kid library, which is consistent with drift. Block 1 settles that first.
- **Review quota is still needed, generation quota is not.** Re-moderating a book (step `D2`'s sequencing for the
  two `UW-L08` books, and step `D4`'s five revised books) makes real reviewer and classifier calls, so the
  configured review provider and `OPENAI_API_KEY` must have working quota even though nothing is generated.

**Roles.** "Operator" is the owner at a workstation with repository access and a shell on the docker host.
"Admin" is the owner signed in with the admin-capable account. "Guardian" is the owner signed in with the
guardian account (the admin-capable account is also a guardian and can do these steps; see the Accounts note
below). "Child" is each reader on their own device.

| Block | Who | Steps, in order | Evidence to record | Rough time |
| --- | --- | --- | --- | --- |
| 1. Deploy parity | Operator | `A1` to `A10`, then re-confirm `0.3` and `0.6` | Revisions, pending-migration list, workflow run id, parity verdict, `e2e-prod` run id | 60 to 120 min |
| 2. Configuration and consent posture | Operator | `B1` to `B6` | Env preflight output, readiness JSON excerpt, flag values | 15 min |
| 3. Catalog readiness | Admin | re-confirm `1a.1`, then `C3`, `D1` to `D7`, `E1` (`E2` optional) | Census table, `UW-L08` ruling, approved book list with bands, covers approved | 60 to 120 min, plus re-moderation run time |
| 4. Family setup | Guardian | `C1` (`C2` optional), `1.3`, `1.4`, `F1` to `F4`, `3.1`, `3.2`, `F6` | Profile list with bands, assignments per child | 45 min |
| 5. Devices | Guardian, then child | per device: `G1`, `F5`, `4.1` | Device list on `/guardian/devices` | 10 min per device |
| 6. The session | Child, owner observing | `G2`, `5.1`, `5.2`, `5.3`, `5.4`, `5.5`, then `H1` to `H4` if deployed | Observation notes (guide below), progress view screenshots | 45 to 90 min |
| 7. Close-out | Operator, Guardian | `J1`, `6.1`, sign-off row | Sign-off row, notes filed | 20 min |

Count: 14 original steps (`0.3`, `0.6`, `1a.1`, `1.3`, `1.4`, `3.1`, `3.2`, `4.1`, `5.1` to `5.5`, `6.1`; three of
them already ticked and only re-confirmed) plus 39 additions, 53 in all; `C2` and `E2` are optional and not
counted. Steps marked "applies once deployed" (`B6`, `D4`, `H1` to `H4`) are skipped, not failed, if the deployed
revision predates them; record which.

**Do not do in this session:** run any Section 2 or Section 4 step other than `4.1`; set
`KWS_VERIFICATION_REQUIRED=true` (step `B4`); type the confirmation word on the family-deletion dialog (step
`J1`); approve any book on the hold-back list (step `D3`).

### Observation guide for the session

The owner's notes are the primary data from a first session; the app's own records are secondary. Watch, do not
help, and write down what you see with a timestamp and the child's name or initial.

- **Hesitation at real forks.** Where a child pauses before choosing, rereads, or asks what a choice means. Note
  the book and roughly where. A fork nobody hesitates at may not be a real choice.
- **Reaction at endings.** Surprise, disappointment, laughter, "that's it?", or a shrug. Note whether the ending
  felt earned or abrupt to them, in their words if they say anything.
- **Whether they replay.** Unprompted rereads, going back to try another branch, or moving straight to a new
  book. Note which, and after which ending.
- **What pulls them out of the story.** A word they stumble on, a slow load, a confusing button, the device
  itself, a sibling. Note anything in the app's chrome (buttons, dialogs, offline banners) they had to ask about.
- **Comfort with content.** Any moment a child seems uneasy, and in which book. Report it on the guardian surface
  afterward rather than interrupting.

Ask each child two questions afterward, separately, and write down the answers verbatim:

1. "What was the best moment in the story you read, and why?"
2. "Was there a time you wanted to do something the story didn't let you do?"

## How to use this checklist

Run top to bottom against `https://cyo.williamshome.family` after every deploy. The PR #112 real-backend
smoke tier (`frontend/e2e-real/`, `npm run test:e2e:real`, local-only, `--workers=1`) is the automated
pre-deploy gate against a local stack; this checklist is the post-deploy verification against prod.

**A step is settled by evidence, not by who produced it.** Changed 2026-08-08: this document was
originally manual-only, on the assumption that nothing automated ran against production. The daily
`e2e-prod` cron changed that, so a step may now be ticked from an automated production test under the
tier rules below, or from a manual pass. What has not changed is that every mutating step, and every
step spending provider quota, stays manual: automation is admitted as evidence, not as authority to
write to the real family.

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

Since 2026-08-05 the tier has also stopped being uniformly green: four consecutive
runs failed on the two profile-count assertions (the most recent 2026-08-08 14:07 UTC,
run `31261130564`), which is how issue
[#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639) was found. A red
tier is doing its job here. Note the corollary for the steps it covers: a serial
describe block aborts at its first failure, so a green *tier* is not the same as an
executed *step*, and any step ticked from this tier must cite a test that actually
ran rather than a suite that passed.

**Note 2026-11-20.** The tier has failed daily since 2026-09-14, on the guardian books page and the kid library.
v0.89.0, released that day, maps three new `storybook_version` columns from migration
`20260908000000_add_cover_review_columns`, which has no recorded production apply, and both failing pages read
that table, so the failure is consistent with schema drift. That is a hypothesis, not a diagnosis: the
deploy-parity gate (steps `A1` to `A10`) is what settles it, and `A10` re-runs this tier afterward.

### Known blockers (resolve before running this checklist end to end)

- **API keys must be funded before Sections 2 and 4.** Both OpenRouter
  (generation) and the OpenAI classifier (Stage-0 moderation) need funded
  quota before the generation-touching sections run. A 429 quota exhaustion on
  the classifier fails silently from the operator's point of view: the
  generation job stalls at the moderation step with no obvious error in the
  UI, so check worker logs for 429s if a job hangs there.

  **Note 2026-11-20.** Generation quota is not a prerequisite of the
  [catalog-only first family session](#first-family-session-catalog-only),
  which defers Sections 2 and 4. Review quota still is: re-moderating a
  catalog book calls the configured review provider and the OpenAI
  classifier (steps `D2` and `D4`). The OpenRouter key exposed in August
  (`UW-M09`) has since been rotated and is not an open prerequisite.
- **Deploy parity (added 2026-11-20).** Run the [deploy-parity gate](#a-deploy-parity-gate)
  before any other section. Since 2026-09-14 the daily `e2e-prod` run has
  failed on the guardian books page and the kid library, which is consistent
  with the app image running ahead of the production schema (`UW-C363`
  describes the same shape from August).

## 0. Infrastructure probes

- [x] `https://cyo.williamshome.family` resolves through Pangolin to docker-host:443 with a valid TLS cert
      (2026-08-04: HTTP 200, OpenSSL verify result 0, wildcard `CN=*.williamshome.family` issued by
      ZeroSSL RSA DV SSL CA 2, valid 2026-06-23 to 2026-09-21)
      **Note 2026-11-20: the evidence above has expired.** The certificate it records was valid only to
      2026-09-21, so the tick describes a past state, not the current one. Re-verify with step `A1`
      before relying on it; the tick is kept because the 2026-08-04 observation was true when made.
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
      was blocked on has happened: production serves the `UW-L04` fix, and as of 2026-08-07 serves
      revision `631c0d8a` (v0.68.0). The evidence is `frontend/e2e-prod/health-probe.spec.ts` on the
      daily cron, whose three tests have passed against live production on 2026-08-05, 2026-08-06 and
      2026-08-07 (runs `31014411104`, `31117078366`, `31188046612`): the canonical endpoint answers as
      real FastAPI JSON, the old shadowed `/health` path returns exactly 404, and the `/nginx-health`
      control answers. Note that `631c0d8a` was not committed until 2026-08-07 05:26 UTC, so the two
      earlier passes were served by an earlier revision. That widens rather than weakens the claim: the
      fix has been live across at least two deployed revisions, not just the current one. Those three
      tests together are what a bare status
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
      **Note 2026-11-20: superseded as a standing check by steps `A4` to `A8`.** The tick records a true
      2026-08-04 state that did not last: by 2026-08-24 production was 18 migrations behind (`UW-C363`),
      and `--linked` in the wording above points at whichever project the checkout is linked to, which
      the runbook records as staging. The repository now holds 70 migration files; the last recorded
      production apply reached `20260823160000` (67), and `20260831120000`, `20260831130000` and
      `20260908000000_add_cover_review_columns` have landed since with no recorded production apply.
- [x] Backups confirmed: the local `db-backup` container is healthy (`docker ps` on docker-host)
      AND a fresh `.dump` file is present under
      `/mnt/unraid/appdata/cyo-adventure/backups`. As of 2026-07-07 this container runs a daily
      `pg_dump -Fc` of the LIVE Supabase database's `public` schema (14-day retention), fixed via
      homelab-infra #585/#586; Supabase-side backups/PITR also exist independently. Do not assume
      Supabase backups alone satisfy this check: verify the local dump too. Verified 2026-08-04:
      `cyo-adventure-db-backup` up 3h (healthy); newest dump `cyo_adventure_20260804_185541.dump`
      (1,189,372 bytes) written the same day, with an unbroken daily series behind it and `.last_success`
      also stamped that day.
      **Note 2026-11-20:** this evidence is from 2026-08-04; re-confirm it in Block 1 of the catalog-only
      path, because step `A5`'s pre-flight leans on knowing a recent restore point exists. It covers the
      local `pg_dump` container only. The separate `supabase-backup.yml` R2 workflow is a different
      mechanism with its own recorded credential gap (`UW-C363` item (c), runbook section 6).
- [ ] Worker survives a restart (`docker compose restart worker`; queued/in-flight jobs resume or
      re-queue rather than being lost). NOT RUN on 2026-08-04: this is the only Section 0 step that
      mutates production, so it was deliberately left for an authorized maintenance window rather than
      bounced during an unattended verification pass.
      **Note 2026-11-20:** not part of the catalog-only path. Recreating the containers in step `A2`
      restarts the worker too, but that is not this step's claim (in-flight jobs survive), so it does not
      tick it.

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
      **Note 2026-11-20:** the #639 defect named above was fixed in code by PR #641 (released in v0.68.2),
      so once production serves a later revision the serial block should no longer abort there. Step `F2`
      (four profiles with correct age bands) performs the create/edit half of this step.
- [ ] Sign out and back in; session resumes. **NOT RUN on 2026-08-08**, same serial-block abort as
      above. Nothing suggests it is broken; it simply never executed. Note that
      `guardian-profiles.spec.ts:104` covers only the sign-out half (it asserts the return to the login
      screen); nothing automated asserts that signing back in resumes the session, so even a green tier
      would leave the second half of this step manual.
      **Note 2026-11-20:** v0.84.0 (#763) changed guardian sign-out from Supabase's default `global`
      scope to `local`, so signing out on one device no longer revokes the adult's sessions on every other
      device. When running this step with the adult signed in on two devices, confirm that signing out on
      one leaves the other signed in. The same release fixed a Google sign-in loop; password sign-in was
      never affected.

## 1a. Admin sign-in and review queue access

Approving account: `byronawilliams@gmail.com` (sub `21985c35`, `role='guardian'` with
`is_admin=true`, family `3a152319`). It is not `role='admin'`; see the Correction in
the Accounts section above.

- [x] Admin email/password sign-in succeeds. Verified 2026-08-08 by `guardian-admin-smoke.spec.ts:67`
      on the daily production cron. Note the account: that spec calls `signInAsProdTestAdmin`, so it
      drives sub `774ea02b` (family `84b96700`), not the approving account named above. Both hold
      `is_admin=true`, and this step asserts the admin capability rather than anything family-specific,
      so the substitution is sound; it is called out so the "this account" below is not misread.
      All nine surfaces render for it, four under `/admin`
      (`/admin`, `/admin/requests`, `/admin/moderation-thresholds`, `/admin/moderation-dashboard`),
      which an account without the admin capability could not reach.
- [x] Sign-in lands on the **Guardian** console (`/guardian`); the Admin console is reachable from
      there via the "Admin console" nav link. **The expectation was re-derived on 2026-08-08 and this
      line was corrected: the old "not the guardian console" wording was wrong, not the product.**
      `LoginPage.tsx` computes the post-sign-in destination as
      `principal?.role === 'admin' ? ADMIN_CONSOLE_PATH : GUARDIAN_CONSOLE_PATH`, so it branches on the
      base `role` alone and `is_admin` does not affect the landing surface at all. This account is
      `role='guardian'` with `is_admin=true`, so `/guardian` is the correct and intended destination.
      The capability surfaces as cross-links instead: `GuardianShell.tsx:168` renders the "Admin console"
      link only when `principal?.isAdmin`, and `AdminShell.tsx` renders the return link only when
      `role === 'guardian'`. No defect: the old assertion would have been satisfiable only by an account
      with `role='admin'`, and no production account has that role.

      **Evidence scope, stated precisely because this tick is settled from code plus a unit test rather
      than from production.** The landing destination is settled from `LoginPage.tsx` above. The nav link
      itself is asserted only at `GuardianShell.test.tsx:161,169` (jsdom, both the present-when-admin and
      absent-when-not cases); no spec in `frontend/e2e-prod/` asserts the "Admin console" string, so the
      cron run does not cover it. Closing that gap is the one piece of automatable work this step still
      wants: an `e2e-prod` assertion that the link renders for the admin-capable account.

## 2. Guardian authoring path (intake to published book)

**All 7 steps NOT RUN on 2026-08-08, for a stated reason rather than by omission.** Every step here spends live provider quota (OpenRouter generation plus the OpenAI Stage-0 classifier) and writes real content into the real family, and it needs an interactive sign-in as both `c1f33430` and `21985c35`. None of that is available to an unattended pass, and none of it is engineering work: it is an owner decision to authorize the spend and the writes. Tracked under `UW-F17`. Also re-read the Known blockers note above before starting: classifier quota exhaustion surfaces as a job that stalls at the moderation step with no error in the UI, so a hang here is a 429 in the worker logs until proven otherwise.

**Deferred for the catalog-only first family session (owner decision, 2026-11-20).** None of these 7 steps is a
prerequisite for that session; they remain valid for a later sign-off. Two notes for when they do run: the
send-back in step `2.7` now requires a structured reason code as well as free text (v0.75.0), and approving a
story whose report carries a block or high finding requires a written override reason (see step `D5`).

- [ ] Submit a story request via Intake; job status shows "Generating..."
- [ ] RQ worker picks up the job (worker logs show the generation; OpenRouter + classifier calls succeed)
- [ ] Story lands in the review queue; queue orders Flagged, then Ready, then processing
- [ ] Review detail shows the story and any moderation flags
- [ ] Guardian account (`byron.a.williams`) attempting approve gets the 403 "safety reviewer" notice
      (ADR-005: approve is admin-only)
- [ ] Approve as ADMIN (`byronawilliams`) succeeds
- [ ] Send-back / revision loop works on a second story

## 3. Assignment surfaces

**All 3 steps NOT RUN on 2026-08-08.** They depend on Section 2 having produced a published book in the real family, so they inherit its provider-quota and interactive-session gates. The read-only halves closest to these steps *are* covered daily by `guardian-books-and-isolation.spec.ts` (the books page lists assigned books with a content-review badge each, and the assign dialog surfaces only redacted content-review tags), and both passed against live production on 2026-08-07. That is not a tick, because these steps assert the *act* of assigning in the real family, which is mutating.

**Note 2026-11-20: steps `3.1` and `3.2` no longer depend on Section 2.** Approved catalog books
(`visibility='catalog'`) appear on every family's `/guardian/books` page with a "Catalog" pill, and the same
Assign dialog applies, so the catalog-only path runs both. Two rules worth knowing before assigning: a child sees
a catalog book only when an assignment row exists for that profile, and the library additionally hides any book
banded above the profile's age band even if assigned (`src/cyo_adventure/api/library.py`). Step `3.3` stays
deferred: its "Assign more" entry point is on the intake page, which belongs to the generation path; the dialog
behind it is the same one `3.1` exercises.

- [ ] Books page lists published books with content badges; assign to a child from there
- [ ] Assign dialog shows redacted content-review tags (category/verdict/message only; no raw
      moderation payloads anywhere in guardian-facing responses)
- [ ] "Assign more" flow from the console works

## 4. Kid request-a-story loop (the completed R1 journey)

**All 8 steps NOT RUN on 2026-08-08**, same two gates as Section 2 (provider quota plus an interactive session), with one addition worth stating: several steps here are deliberately destructive of quota by design, notably submitting 5 pending requests to observe the 6th return the 409 cap message. The device-grant leg that this journey opens with *is* exercised daily against live production by `kid-device-grant.spec.ts` (authorize, open the kid library, revoke), all three green on 2026-08-07, so the mechanism is not the risk here. The untested part is the request-to-published journey itself.

**Deferred for the catalog-only first family session (owner decision, 2026-11-20), except step `4.1`.** Step
`4.1` (guardian console hands off to the kid picker, picking a profile lands on that child's library) exercises
no generation and is part of Block 5 of that path; the console button is "Hand device to a child", which signs
the adult out. The other 7 steps remain valid for a later sign-off.

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

**All 5 steps NOT RUN on 2026-08-08.** These need an assigned book from Sections 2 to 4, so they carry those gates, plus one this pass cannot satisfy by any means: a **second physical device** and a **real offline transition**. Airplane mode is not simulable in a way that would make the offline step's pass meaningful, since the point is the browser's own network-loss handling and the service worker's cached state, not a mocked failure. This is the one section that stays manual permanently rather than pending automation.

**Note 2026-11-20: runnable on the catalog-only path.** An assigned catalog book (steps `D5`, `3.1`) satisfies
the "assigned book" precondition, so Sections 2 to 4 are no longer needed first. Two changes since these steps
were written:

- **Refresh every device before testing (step `G1`).** v0.86.0 changed the reading-state contract: a profile with
  no saved progress now gets `200` with `{"state": null}` instead of `404`. A PWA still running an older cached
  bundle can misread that, so a failure on a stale device is not evidence about the deployed build.
- **Offline debt to watch for.** `UW-F39` (an offline read of a flowed stop syncing one transition short while
  the app said "All caught up") was closed by #761 in v0.84.0; a recurrence is a regression, so note it. `UW-C09`
  is still open and includes "reconnect teleport": reconnecting mid-read can move the reader backwards. If a child
  reports being sent back to an earlier page, record the book, the device, and whether the device had just come
  back online.

- [ ] Open an assigned book; reader plays through choices to an ending
- [ ] Completion is recorded (guardian progress view reflects it)
- [ ] Close mid-story, reopen on a second device/browser; progress resumes from the server
- [ ] Offline read works (airplane mode after load); progress syncs on reconnect
      (KNOWN DEBT: offline completions are fire-and-forget; see the deferred-debt register)
- [ ] Rate a finished book
      **Note 2026-11-20:** today the rating control is the star row on the book's card in the kid library.
      A rating prompt on the ending screen is landing in the same batch as this update; once deployed,
      step `H3` covers it and either surface settles this step.

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

**Correction 2026-11-20: `0ca7a109` is not an orphan.** It is the system catalog family, by design:
`src/cyo_adventure/db/models.py` defines `CATALOG_FAMILY_ID = 0ca7a109-0000-4000-8000-000000000000`
(`CATALOG_FAMILY_NAME = "Catalog (system)"`, the prefix a mnemonic for "catalog"), seeded by migration, owning
every catalog-origin storybook. It has no users because nobody signs into it, and it has no profiles,
assignments, grants, requests, or reading states because those belong to real families. The inventory queries
above counted those tables and not `storybook`, which is why it read as empty. So the "orphan" label in the table
and the atomicity concern `UW-L05` raises do not apply to it; `adb9e257` remains the one unexplained row. Two
further cautions: the family and profile counts here have moved more than once and other documents now disagree
with this table (some cite three family rows), so re-query before relying on any of them; and "onboarding has no
signup form" is no longer the whole story, since a self-signup now lands in a fresh family at
`status='awaiting_approval'` until an admin approves it (step `C2`).

**A drift trap this creates, worth fixing before it bites.** `guardian-books-and-isolation.spec.ts:212`
carries a comment justifying its `toHaveCount(1)`. All three numbers in it are now wrong, not just the
two in its closing clause: it opens "The real family has 2 child profiles" (it now has 3), then reasons
"not 2, and certainly not 3, the sum across every family in the database" (the database-wide sum is now
4). The opening sentence matters most, because it is the first thing a reader re-deriving the
expectation hits. The assertion itself is still correct and still fails correctly; only its stated
reason no longer distinguishes the case it was written to catch. Assertions pinned to live production
data need their justifying counts re-checked whenever this table moves. Tracked as `UW-L05`, alongside
the two unexplained families that caused the drift.

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
      count.
      #ASSUME: data integrity: a rendered-page control is assumed to distinguish "scoped correctly to
      zero rows" from "scoped to zero rows for everyone", and #639 shows it does not: both render
      identically. #VERIFY: an emptiness assertion over a Tier 1 table needs a non-empty companion
      assertion in the same test, over a table subject to the same policy; a rendered-heading control
      proves the page loaded, never that the scoping mechanism ran.
      **Note 2026-11-20:** the #639 fix (PR #641) was released in v0.68.2, so the do-not-tick condition
      above is satisfiable once production serves a later revision. Tick this step only from an `e2e-prod`
      run that executed `guardian-books-and-isolation.spec.ts` green after the deploy-parity gate (step
      `A10`); that spec has failed daily since 2026-09-14, so a pre-gate run is not evidence either way.
- [ ] Kid surfaces never expose guardian-only fields. The concrete contract (`api/review_surface.py`)
      is that guardian-facing responses are story-level and node-id-free: they carry `flagged_count`,
      `node_count`, and merged concern rows, and never `flagged_passages` or raw node `prose`.
      **Partially automated**: the spec above scans every observed `/api/v1/**` JSON body for those two
      forbidden keys. The kid-surface half (story-request responses carrying id/status only) is NOT
      automated, because the test family has 0 story requests, so the assertion would pass vacuously.
      Creating one costs LLM spend, which is why this is still a manual step.

## 2026-11 additions

Added 2026-11-20 against `main` at v0.92.0, to cover roughly 24 releases of surfaces the original 38 steps
predate and to make the [catalog-only first family session](#first-family-session-catalog-only) runnable. **41
steps, 0 ticked.** These are counted separately from the original 38 and never folded into "N of 38".

Each step is one action with its expected result and the evidence to record. Steps marked **applies once
deployed** describe work landing in the same batch as this update (`B6`, `D4`, `H1` to `H4`); if the deployed
revision predates it, skip the step and write "not deployed" against it rather than failing it.

### A. Deploy parity gate

Run this block before every session and after every image pull. It is ordered: do not start a later step while
an earlier one is red. The migration mechanics live in [the operations runbook](../operations/runbook.md),
section 2.5 ("Applying pending migrations to production"); this block names the checks and the evidence, and
defers to the runbook for the commands.

- [ ] **A1.** Check the TLS certificate the public host serves now:

      ```bash
      host=cyo.williamshome.family
      openssl s_client -connect "$host:443" -servername "$host" </dev/null 2>/dev/null \
        | openssl x509 -noout -dates -issuer
      ```

      Expected: `notAfter` in the future, verify result 0. Evidence: issuer and validity window. Step `0.1`'s
      recorded certificate expired 2026-09-21.
- [ ] **A2.** On the docker host, read the revision label of the running backend, worker, and frontend containers:

      ```bash
      docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
        cyo-adventure-backend cyo-adventure-worker cyo-adventure-frontend
      ```

      Expected: all three print the same SHA, and it is the release you mean to test (v0.92.0 or later). If not,
      pull and recreate the containers (the manual homelab step) and read the labels again. Evidence: the SHA, the
      release it maps to, and both image digests. `org.opencontainers.image.version` reads `0.1.0` and tracks
      nothing; use the revision only.
- [ ] **A3.** Run `uv run python scripts/check_env_boots.py /path/to/backend.env --integrations` from a checkout
      of the ref you will deploy, against a copy of the production backend env file, and again against the
      worker's. It loads `Settings` exactly as the app does, isolated from your shell, and reports every boot-time
      validation failure in one pass, naming the setting and the rule and never printing a value. Expected:
      `BOOTS` (exit 0) for each file; `WOULD REFUSE TO BOOT` (exit 1) lists what to fix. The `--integrations` block
      names which optional integrations are configured; use it for steps `B1` to `B3`. Evidence: the verdict line
      for each file. Do this before recreating a container on a changed env file; a config error stops uvicorn
      importing the app at all, and has taken the frontend down with it before.
- [ ] **A4.** List pending migrations with the "Detect drift" commands in runbook section 2.5 (applied set on
      production via `--db-url`, never `--linked`, compared with `git ls-tree` at the ref you will deploy).
      Expected at time of writing: at least `20260831120000_seed_moderation_threshold_grid`,
      `20260831130000_add_storybook_recalled_to_pipeline_event` and `20260908000000_add_cover_review_columns`
      pending, unless applied since. Evidence: the pending list, verbatim.
- [ ] **A5.** Complete runbook section 2.5's Pre-flight: a dump or a written targeted-snapshot rationale, staging
      green on the **same migration set** (not merely an ancestor commit), and the pending set read rather than
      counted. Expected: all three satisfied. Evidence: where the dump is (or the rationale), and the "same
      migration set" line.
- [ ] **A6.** Dispatch `gh workflow run supabase-production.yml --ref "$REF"` and approve it as the `production`
      environment's reviewer. Expected: the run succeeds. Evidence: the run id. Skip only if `A4` listed nothing.
- [ ] **A7.** Run all four Post-deploy verification checks in runbook section 2.5. For this pending set that
      includes: `storybook_recalled` present in `ck_pipeline_event_event_type` (a constraint-widening migration);
      `moderation_threshold` now holding rows (the seed is behaviour-preserving: every row has `min_score` NULL
      and `min_verdict` `flag`); the three `cover_review_*` columns present on `storybook_version`; and an
      authenticated `GET /api/v1/me` answering 200. Evidence: each result.
- [ ] **A8.** Run `SCHEMA_PARITY_DATABASE_URL="$SUPABASE_DB_URL" uv run python scripts/check_schema_parity.py`
      against production, from a checkout of the deployed ref (read-only transaction; compares applied migrations
      and ORM-mapped tables and columns against the live database; prints names only, never the URL). Expected:
      `IN PARITY` (exit 0). `DATABASE BEHIND` (exit 1) lists the pending migrations and missing columns, so go
      back to `A4`; `DATABASE AHEAD` means the image is older than the schema, so go back to `A2`; `INCOMPLETE`
      (exit 3) means the role could not read the migration history, so rerun with the `postgres` session-pooler
      string or add `--schema-only`. Before the 2026-11 deploy this is expected to report BEHIND by
      `20260831120000`, `20260831130000`, and `20260908000000`. Evidence: the verdict line.
- [ ] **A9.** Fetch `/api/v1/health/ready` from outside the LAN (or read the `health-probe.spec.ts` result from
      `A10`). Expected: 200 `application/json`, and every entry in `checks` (`database`, `database_privilege`,
      `cache`, `generation_queue`, `generation_cascade`, `kws_verification`) reports `status: true`. Evidence:
      the JSON. Readiness is a connectivity probe and cannot see schema drift, which is why it comes after `A8`.
- [ ] **A10.** Dispatch the `e2e-prod` workflow (`workflow_dispatch`) and wait for it. Expected: every spec green,
      including every spec that has been red since 2026-09-14 (the alert issue is #824; the guardian books page
      in `guardian-books-and-isolation.spec.ts` and the kid library in `kid-device-grant.spec.ts` among them).
      Evidence: the run id. If `A8` said `IN PARITY` and these are still red, stop: the cause is not
      drift, and the session should not proceed until it is understood.

### B. Configuration and consent posture

Read these from the production env files `A3` checked, plus the readiness JSON from `A9`. Record values as
"set"/"unset" or the literal non-secret value; never copy a secret into notes.

- [ ] **B1.** Confirm `ENVIRONMENT=production` is set explicitly in the backend and worker env files. Expected:
      present and `production`. A deployed process with OIDC config and no `ENVIRONMENT` refuses to boot rather
      than defaulting to `local` (`src/cyo_adventure/core/config.py`, `_require_explicit_environment_when_deployed`),
      so `A3` would already have failed; this step records the value.
- [ ] **B2.** Confirm a real moderation reviewer: `CYO_ADVENTURE_REVIEW_PROVIDER` is `openrouter` or `modal` (the
      default is `mock`), and `CYO_ADVENTURE_ALLOW_MOCK_REVIEW` and `CYO_ADVENTURE_MOCK_REVIEW_JUDGES_SAFE` are
      unset. Expected: as stated. The allow-mock hatch makes a mock reviewer bootable outside local; it must never
      be set in production, because everything re-moderated in steps `D2` and `D4` would then carry mock reports
      that cannot clear the review gate.
- [ ] **B3.** Confirm `OPENAI_API_KEY` is set and its account has quota. Expected: set (boot refuses a non-mock
      reviewer without it; `PERSPECTIVE_API_KEY` no longer satisfies the rule). Evidence: "set", plus the date
      you checked the provider's billing page.
- [ ] **B4.** Confirm parent verification is off and unconfigured: the readiness JSON's `kws_verification` check
      reports `state: "unconfigured"` (which it does exactly when `KWS_VERIFICATION_REQUIRED` is false), and the
      four KWS credentials (`KWS_ORGANIZATION_ID`, `KWS_API_ORIGIN`, `KWS_CLIENT_ID`, `KWS_API_KEY`) are all
      blank. Expected: as stated. **Do not turn verification on for this session.** The owner and any guardian
      who consented with the typed-name attestation would lose child-profile creation until they re-verify, and
      a new adult would be held on a verification screen that cannot send an email while KWS is unconfigured
      ([KWS consent-gate handoff](handoff-kws-consent-gate-2026-08-10.md), section 5 item 4). Setting some but
      not all four credentials refuses to boot by design.
- [ ] **B5.** Confirm the frontend image was built without `VITE_FEATURE_PERSONALIZATION`. Expected: no such build
      argument in the homelab frontend build. `frontend/Dockerfile` declares no such `ARG`, so it is off unless
      the out-of-repo build injects it, and `frontend/src/env.ts` records that it must not be enabled where a
      real family can reach it until its gating task has merged. Evidence: the build arguments you checked.
- [ ] **B6.** *Applies once deployed.* Decide whether the reading-trail capture (reads started, choices taken,
      rewinds, endings reached, where a read was left) is on for this session. It ships off. To turn it on, apply
      migration `20261120120000_add_reading_trail` (step `A5` does this) and set `READING_TRAIL_ENABLED=true` on
      the backend container, then restart it. Expected: the setting matches your decision. What it stores is
      described in `docs/planning/privacy-model.md` ("Reading Trail"): per read, an ordered list of node and
      choice ids with whole seconds since the read began and one date; no free text, device, or network data;
      first-party only; erased with the profile; purged after 30 days. It is data about your own children, and it
      is not yet described on any in-app privacy page, which is why it must stay off for any other family.

### C. Adult accounts

- [ ] **C1.** Sign in as the guardian account. Expected: you land on `/guardian`. If you land on
      `/guardian/consent` instead, complete the typed-name attestation (your name, residence country, and the
      adulthood confirmation); profile creation is refused until the signed-in guardian has a recorded consent
      (`src/cyo_adventure/api/profiles.py`, `_require_consent`). Evidence: which page you landed on.
- [ ] **C2.** *Optional.* Add a second adult (for example a spouse) **by invitation, not by self-signup.** Either
      invite them from `/admin/users` ("Invite a guardian or admin", choosing the real family), which binds them
      as active on first sign-in, or from the guardian console's "Invite a co-parent", which lands them at
      `awaiting_approval` until you approve them. To approve, open `/admin/users`, find their row (status
      `awaiting_approval`), and press its **Reactivate** button, which is how that transition is labelled.
      Expected: they reach `/guardian` after their own consent step and see the family's profiles. A self-signup
      instead creates a **separate, new family** held at `awaiting_approval`, which is not what you want.
- [ ] **C3.** Open `/admin/users` and read the Users and Families tabs. Expected: no account you do not recognise
      at `awaiting_approval` or `active`. Do not approve an account you cannot identify; `adb9e257` (Section 6)
      is still unexplained. Evidence: the count of adults and families, and any row you could not identify.

### D. Catalog readiness

Catalog books are owned by the system catalog family and reach a child only when an admin approves them with
catalog visibility **and** a guardian assigns them. The review surface is `/admin/review/<storybook-id>`, reached
from the queue at `/admin` (books `in_review`) or from `/admin/library` (any status). Work it with the
[reviewer SOP](../operations/reviewer-sop.md) open.

- [ ] **D1.** Take a census. Open `/admin/library`, filter **Published**, then **In review**, and record each book's
      title, age band, and status. Optional read-only cross-check against production (latest version of every
      catalog-family book):

      ```sql
      select s.id, s.status, s.visibility,
             v.blob->>'title' as title, v.blob->'metadata'->>'age_band' as band,
             v.approved_by is not null as approved, v.cover_status
      from storybook s
      join storybook_version v on v.storybook_id = s.id
       and v.version = (select max(x.version) from storybook_version x where x.storybook_id = s.id)
      where s.family_id = '0ca7a109-0000-4000-8000-000000000000'
      order by s.status, band;
      ```

      Expected (2026-08-31 census, re-derive rather than trust): 13 published, all in younger bands; 13 in review,
      skewed older ([review-screen remediation plan](review-screen-remediation-plan-2026-08-31.md), section 2.2).
      Evidence: the table.
- [ ] **D2.** Rule on the two published books with severe findings, register row `UW-L08`: `sk_vault_of_nine_iron`
      (block/high, drowning) and `sk_ninth_hand` (flag/high, suicidal intent). Open each in `/admin/review/<id>`
      and read the findings. The ratified sequence is to re-moderate each first
      (`scripts/remoderate_books.py --book-id <id> --execute`, run as an operator role, spending review quota)
      and decide on the fresh report. Decide per book: keep, recall to review (from `/admin/outstanding-decisions`
      if listed there; recoverable, assignments survive), or archive (the Archive button on the review page;
      absorbing). Expected: a written decision per book. **Minimum before children browse:** neither book is
      assigned to any child, which by itself keeps it off every shelf. Evidence: the decision and date.
- [ ] **D3.** Check the hold-back list. Expected: none of these is published or assigned, and none is approved in
      this session: `the-clocktower-cipher`, `the-sunken-signal` and `the-lost-mitten` (MVP/Test-tier fills that
      gate rule PL-28 refuses); `the-sunken-temple` and `the-harrowstone-keep` (held per owner ruling OG1); and,
      for this session only, the high-failure gamebooks `the-sunspire-ascent` and `the-thornwood-trial`.
      Production ids may differ from these file slugs; match by title. Evidence: "none present", or the book and
      its state.
- [ ] **D4.** *Applies once deployed.* Five catalog books received an editorial revision: *The Signal in the
      Static* (13-16), *The Hollow Lighthouse* (10-13), *The Midnight Museum* (10-13), *The Sky-Ship Stowaway*
      (8-11), *The Cave of Echoes* (8-11). The plain catalog import skips any story id that already exists, so
      import the revisions as a second edition beside the first, the same way the first catalog import was run
      (issue #347), with the production backend env loaded and a real reviewer configured (step `B2`):
      `uv run python -m cyo_adventure.generation.import_catalog --only the-signal-in-the-static --only
      the-hollow-lighthouse --only the-midnight-museum --only the-sky-ship-stowaway --only the-cave-of-echoes
      --edition r2`. Expected: the summary reads `imported: 5`; each revision is a NEW story whose id ends in
      `__r2`, at `in_review`, with a fresh moderation report whose reviewer is not the mock. The first editions
      are not changed: afterwards retire each one by hand so the two do not sit side by side under one title (send
      it back if it is `in_review`; use **Archive** on `/admin/review/<id>` if it is published, and unassign it
      first if a child has it). Evidence: the import summary, and each first edition's final state.
- [ ] **D5.** Approve each book you intend to offer. In `/admin/review/<id>`, read the summary and findings, press
      **Approve**, and in the confirm dialog choose **"Catalog (every family)"** under "Who can see this book?".
      Expected: the book is Published with catalog visibility. Three traps: the dialog **defaults to "This family
      only"**, which publishes a catalog-owned book to the catalog family alone so no child can read it; when the
      report carries a block or high finding, **Confirm approve** stays disabled until you type an override reason
      of at least 10 characters (logged for audit, not stored on the story); and if Approve is disabled with a
      "moderation unavailable" hint, the report is unusable and the book must be re-moderated first. For the first
      session, prefer holding a book back over writing an override you would not defend. Evidence: each approved
      book, and any override reason you wrote.
- [ ] **D6.** Check band coverage. For each child's intended age band (step `F2`), count published catalog books at
      or below that band. Expected: enough choice per child for a session (your call; two or three each is a
      reasonable floor), with the 13-16 band in particular not empty, since the published set skewed younger.
      Evidence: count per band.
- [ ] **D7.** Sign in as the guardian and open `/guardian/books`. Expected: every book approved in `D5` is listed
      with a "Catalog" pill and the right age band, and nothing from `D2` or `D3` is offered. Evidence: the list.

### E. Covers

- [ ] **E1.** For each book you will assign, open `/admin/review/<id>` (published books via `/admin/library`). If a
      "Generated cover" block shows a cover pending review, look at it, read any AI-review note, and press
      **Approve cover**. Expected: "Cover approved.", and the cover appears on the child's library card; only an
      approved cover ever reaches a child. Approving a book does not approve its cover; they are separate gates.
      As of the 2026-08-31 census no cover had been approved in production, and two published books had a cover
      waiting. Evidence: books whose covers you approved. A book with no cover still reads normally.
- [ ] **E2.** *Optional.* Generate a cover for a book that has none with **Generate cover** on the same page.
      Expected: it moves to pending review, then `E1` applies. This needs `GEMINI_API_KEY` and the `R2_*` settings
      configured (otherwise the request fails with "cover generation is not configured") and runs on the worker.

### F. Profiles and devices

- [ ] **F1.** Open `/guardian/profiles` and count the real family's child profiles. Expected: a number you can
      reconcile; this document recorded 3 on 2026-08-08 and a later count has been cited as 2. Evidence: the count
      and names.
- [ ] **F2.** Make sure each of the four children has exactly one profile ("Add child", or "Edit" an existing one)
      with an age band that fits them. The bands are `3-5`, `5-8`, `8-11`, `10-13`, `13-16` and `16+`; for ages 9
      to 15 the candidates are `8-11`, `10-13` and `13-16`. The band is a ceiling: a child never sees a book banded
      above it, even when assigned. Expected: four profiles, bands recorded. This performs step `1.3`'s
      create/edit half.
- [ ] **F3.** For each profile, choose whether to set a picker PIN (Edit, "Picker PIN", 4 to 8 digits; the field
      exists only when editing, not when creating). Expected: your choice applied. Recommended for siblings who
      share devices, since an authorized device's picker offers every profile in the family.
- [ ] **F4.** Leave "Read-aloud" unchecked on each profile unless a child asks for it (it is per profile and off by
      default). Expected: as chosen. Evidence: which profiles, if any, have it on.
- [ ] **F5.** On each child's device: sign in as the guardian, press **"Set up this device for your kids"** on the
      console, then continue with step `4.1`. Expected: the device appears on `/guardian/devices`. Evidence: the
      device count and labels there. Revoking a device stops new reading sessions at once, but a session already
      running continues until it expires on its own.
- [ ] **F6.** Before handing over, use **Preview** next to each profile on `/guardian/profiles`. Expected: the shelf
      shows exactly the books assigned to that child in `3.1`, nothing banded above their profile, and nothing from
      `D2` or `D3`. Evidence: titles per child.

### G. Reading on real devices

- [ ] **G1.** Refresh the app on every device that has opened it before: close every tab and the installed app
      completely, then reopen it (the service worker updates on the next full load). Expected: the app loads, and
      opening a book the child has never read starts at the beginning with no error. Why it matters: v0.86.0
      changed "no saved progress" from a `404` to `200` with `{"state": null}`, and a device still running an
      older cached bundle is testing the old client, not the deployed one.
- [ ] **G2.** Each of the four children, on their own device, picks their profile and opens a book of their
      choosing from their shelf. Expected: all four are reading at the same time without errors. Evidence: per
      child, device, first book opened, and anything that went wrong. This is the end state the catalog-only path
      exists to reach.

### H. Reader features landing in the 2026-11 batch

All four steps **apply once deployed**. They were first written before the code landed and were rewritten on
2026-11-20 against the merged implementation and its screenshots, but never against a deployed build; correct
any wording that differs the first time you run them.

- [ ] **H1.** From the library, open a book the child has not started. Expected: a title page with the cover (the
      letter tile if the book has no approved cover), the title, and one **Start** button, with the text-size
      control available before page one; **Start** begins the story. Then leave and reopen it. Expected: a book in
      progress resumes on its page with no title page.
- [ ] **H2.** Reach a setback ending. Expected: a one-line invitation under the ending text (for example "Not the
      ending you hoped for? Stories can go lots of ways."), and **"Try a different choice"** as the leading
      button. Tap it. Expected: the reader returns to the most recent point where two or more choices were
      visible, with a note naming the choice taken last time; picking the other choice continues from there, and
      the guardian progress view stays consistent with what was read. On a happy ending the same button is
      present but secondary; when a read has no earlier fork it is absent.
- [ ] **H3.** Reach an ending while online. Expected: "How did you like this story?" with five stars below the
      ending buttons; the rating given there shows on the book's library card. Offline, the prompt is hidden.
      This settles step `5.5` as well.
- [ ] **H4.** With the reading-trail setting on (step `B6`), complete one read, rewind once from an ending, and
      leave another read midway. Then, on the deployment host, run `READING_TRAIL_REPORT_DATABASE_URL=<owner or
      worker DSN> uv run python scripts/report_reading_trail.py` (add `--by-profile` to split by child, and
      `--storybook <id>` for one book). Expected: per book, reads started and finished, endings reached, the nodes
      where reads stopped, and for each real decision the picks per choice and the rewinds back to it. With the
      setting off, nothing is stored and the report is empty. Run it within 30 days of the session; trails are
      purged after that. Evidence: the report, kept on that host.

### J. Privacy and erasure (non-destructive)

- [ ] **J1.** **Smoke check only; this must not delete the real family.** Signed in as the guardian, open
      `/guardian/privacy`, scroll to "Delete your family account", press **Delete family account**, confirm that
      **Delete everything** is disabled until the confirmation word is typed, then press **Cancel**. Expected:
      dialog opens, destructive button disabled, Cancel closes it. **Never type the confirmation word on this
      account.** A real erasure run belongs against the E2E test family or staging, never in this checklist.

## Sign-off

| Run date | Image tags (backend/frontend) | Result | Notes |
| --- | --- | --- | --- |
| 2026-08-04 | both at revision `f1b561b6` (v0.63.0); backend `@sha256:de9a9f6a`, frontend `@sha256:4d608898` | PARTIAL, 5 of 38 steps | Section 0 only. Sections 1 to 6 not run. Detail below. |
| 2026-08-08 | both at revision `631c0d8a` (v0.68.0); backend `@sha256:6a92ab44`, frontend `@sha256:7d7bd249` | **PARTIAL, 10 of 38 steps, and a live P1 defect found** | Sections 0, 1, 1a advanced from CI evidence. `UW-L04` confirmed deployed. Section 1a's open routing question resolved from code. Guardian profile resolution is broken in production: [#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639) / `UW-L07`. Detail below. |
| *(catalog-only first family session, not yet run)* | | | |

**Template for the catalog-only session row (added 2026-11-20).** Fill the blank row above rather than adding a
new one, and keep the two counts separate: the original population as "N of 38" and the additions as "M of 41".

- **Run date:** the session date.
- **Image tags:** backend, worker and frontend revision from step `A2`, plus both digests.
- **Result:** "N of 38, M of 41", the parity verdict from `A8`, and the `e2e-prod` run id from `A10`.
- **Notes:** the `UW-L08` ruling from `D2`; books approved in `D5` with bands; covers approved in `E1`; which
  "applies once deployed" steps were skipped as not deployed; anything a child hit that the observation guide
  recorded; and a link to a dated detail section below, written in the same shape as the two above.

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
  a comment but is applied to one call site is a half fix. Sharper still: two `#CRITICAL` blocks in
  `deps.py` assert as fact the very thing the bug disproves, one of them claiming the device read is
  "the ONLY pre-principal read" of a Tier 1 table. See `UW-L07` for the exact lines; the fix has to
  correct those comments too.
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

**Owner-gated remainder, unchanged in shape from 2026-08-04.** Of the 28 untouched steps, 26 need one
of four things this pass could not supply, none of which is engineering work: interactive credentials
for subs `c1f33430` and `21985c35`; an authorized maintenance window for the single mutating Section 0
step (worker restart); funded OpenRouter and classifier quota plus permission to write real content
into the live family (Sections 2 and 4); and a second physical device with a real offline transition
(Section 5).

**The remaining 2 are the exception, and are engineering-blocked.** Section 1's two unticked steps are
blocked twice over: they are gated on an interactive session like the other 26, *and* their automated
read-only halves cannot execute until #639 / `UW-L07` is fixed, because the serial describe block
aborts at the failing test ahead of them. Section 6's cross-family step is blocked the same way and is
explicitly marked do-not-tick above. So the honest summary is "owner-gated except for the #639 fix",
not "owner-gated throughout".
