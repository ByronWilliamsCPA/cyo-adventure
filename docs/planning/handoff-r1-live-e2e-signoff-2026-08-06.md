---
purpose: What remains to complete r1-live-e2e-checklist.md and record the M4.1 sign-off row, with
  the 2026-08-04 partial run's findings so the next pass does not re-derive them
component: docs/planning/r1-live-e2e-checklist.md, frontend/e2e-prod/, .github/workflows/e2e-prod.yml
source: R1-completion review session, 2026-08-06; prior partial run 2026-08-04
---

# Handoff: R1 live E2E checklist to M4.1 sign-off

Written 2026-08-06. This is item 2 of a four-item R1-completion handoff set; see the sibling
handoffs for the CVE gate/live defects (item 1), ADR-018 counsel engagement (item 3), and the
OG1/OG7 owner decisions (item 4).

## 1. Where this actually stands

`r1-live-e2e-checklist.md` is the manual post-deploy verification gate for calling **M4.1 sign-off**
done (`roadmap.md`'s Milestones table names this checklist, "0/38 steps, no sign-off row," as the one
concrete thing still open on that gate). It is **closer than that framing suggests**: a
2026-08-04 pass logged as `PARTIAL, 5 of 38 steps` in the checklist's own Sign-off table, and that
pass did real, verifiable infrastructure work, not just ticking boxes.

**Do not re-run Section 0 from scratch.** Read the "2026-08-04 partial run" narrative at the bottom
of the checklist file first, it records exactly what was checked, how, and why two items are
still open, plus a live-database finding (a third, empty orphan family, `UW-L05`) that the next
runner should not be surprised by.

## 2. What's ticked and what isn't

**Section 0 (Infrastructure probes): 5 of 7 done.**

- ✅ Pangolin TLS, frontend loads with build-time Supabase config, Redis/RQ worker up, migrations
  current (49/49 matched), local DB backup container healthy with a same-day dump.
- ❌ `/api/v1/health/*` returning 200 with `application/json`, **blocked on a production redeploy**,
  not on a verifier. The fix is already on a branch (`UW-L04`): the health router was mounted
  outside the proxied `/api/` prefix, so nginx's own container-probe stub silently shadowed it and a
  bare `200 OK` from nginx was mistaken for a real readiness check for months. The fix moves the
  router under `/api/v1/health/*`, moves nginx's stub to `/nginx-health`, and makes `/health` 404 so a
  stale probe fails loudly. **Tick this only after prod runs an image built from that fix**, checking
  today would just reproduce the same false pass.
- ❌ Worker survives a restart, not run 2026-08-04 on purpose: it's the one Section 0 step that
  mutates production, deliberately left for an authorized maintenance window rather than bounced
  during an unattended pass. **This needs a scheduled window, not more verification tooling.**

**Sections 1-6: 0 of 31 done, but a meaningful slice is now covered by automation instead.** Every
one of these needs interactive sign-in as `c1f33430` (guardian) or `21985c35` (guardian+admin), which
the 2026-08-04 pass didn't have. Rather than leave all 31 waiting on a human, three read-only-safe
specs were added to `frontend/e2e-prod/` (the daily-cron real-account tier) to close what could be
closed without spending money or writing content:

| New spec | Covers | Checklist step(s) it closes |
| --- | --- | --- |
| `health-probe.spec.ts` | Asserts content-type, not just status, with `/nginx-health` as a control | Section 0's health check, once prod redeploys |
| `guardian-profiles.spec.ts` | Route guard, login form, profile list, sign-out | Section 1 |
| `guardian-books-and-isolation.spec.ts` | Books/review-surface redaction contract (scans every `/api/v1` JSON body for `flagged_passages`/raw `prose`) and Section 6 cross-family isolation | Section 3 (partial), Section 6 (partial) |

**What automation cannot close, and needs a human with real credentials and authorization:**

- **Section 2** (guardian authoring path) and **Section 4** (kid request-a-story loop) spend real
  OpenRouter and OpenAI-classifier quota and write real content into the live family. These need
  explicit authorization to spend money, not just credentials.
- **Section 1a** has an open question, not just an unticked box: its written expectation ("lands on a
  review queue, not the guardian console") is very likely **wrong** for the current role model.
  `role='guardian'` with `is_admin=true` routes to the guardian console by design and reaches
  `/admin` as an added capability, that's correct behavior, not a bug, per the checklist's own
  2026-08-04 correction note. **Re-derive the expected landing surface for a dual-role adult before
  ticking or filing this line; don't just click through it.**
- **Section 5** needs a second device/browser for the offline-transition step, and carries one
  already-known, already-accepted piece of debt: offline completions are fire-and-forget (see the
  deferred-debt register), that's expected behavior, not something to file as a new finding.
- **Section 6** premise was already re-verified 2026-08-04: production holds **three** families, not
  two. The third (`0ca7a109`) has no `user` rows at all and can't be signed into, it's recorded as
  its own finding (`UW-L05`), not a blocker for this section. The isolation check is meaningful with
  the two usable families (`3a152319` real, `84b96700` E2E test) and is what
  `guardian-books-and-isolation.spec.ts` already automates part of.

## 3. Concrete next steps, in order

1. **Get the health-probe fix (`UW-L04`) deployed to production**, then tick Section 0's health
   check by re-running `health-probe.spec.ts` (already wired into the daily `e2e-prod` cron, so this
   may just need waiting for the next scheduled run and reading its result, not a manual pass).
2. **Schedule an authorized maintenance window** for the worker-restart check, this is a
   coordination task, not an engineering one.
3. **Get funded API quota confirmed** for OpenRouter and the OpenAI classifier before attempting
   Sections 2 and 4 (the checklist's own "Known blockers" note: a 429 on the classifier stalls a
   generation job at the moderation step with no obvious UI error, check worker logs for 429s if a
   job hangs there).
4. **Run Sections 1, 1a, 2, 3, 4, 5, 6 interactively** as `c1f33430`/`21985c35`, in that order (the
   checklist is written to be run top to bottom because later sections depend on state Section 2/4
   create, a published book, an assignment). Resolve Section 1a's routing-expectation question
   first, since it blocks correctly interpreting that section's result.
5. **Record the sign-off row** in the checklist's own Sign-off table (date, image revision from
   `docker-host` labels, not `org.opencontainers.image.version`, which reads `0.1.0` on both images
   and does not track releases, result, notes). This row is what `roadmap.md`'s M4.1 milestone is
   actually waiting on.
6. **Re-verify Now-queue items 1-4** in `roadmap.md` (last checked 2026-07-20, now stale) alongside
   this pass, since M4.1's exit criteria names them explicitly.

## 4. Do not re-litigate

These were checked and closed in the 2026-08-04 pass; don't re-derive them:

- ADR-021 production cutover: confirmed live both by `pg_authid`/`pg_stat_activity` snapshot and,
  independently, by a startup role probe now standing in CI (`UW-A03`, `UW-A44`).
- The RQ worker authenticates as `cyo_worker` with `rolbypassrls=false`, proven read-only from
  inside the running container via `get_worker_session()`, no generation job triggered, no quota
  spent.
- Migrations: 49/49 exact match between `supabase/migrations/` and the live project.
- Backups: local `db-backup` container healthy with a same-day dump on top of an unbroken daily
  series; Supabase-side backups/PITR exist independently.

## 5. Definition of done

- All 38 checklist steps ticked or explicitly re-scoped with a filed reason (not silently skipped).
- A completed Sign-off table row with a PASS/PARTIAL/FAIL result and the deployed image revision.
- Now-queue items 1-4 re-verified and their status updated in `roadmap.md`.
- If any step surfaces a new defect, file it as a GitHub issue with a `UW-*` register row per the
  unscheduled-work register's linkage contract, do not just note it inline in the checklist and
  leave it unrouted, which is exactly the failure mode the 2026-07-28 sweep exists to prevent.
