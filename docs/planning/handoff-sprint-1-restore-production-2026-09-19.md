---
purpose: Hand the Sprint 1 work (restore the production books and kid-library surfaces, make schema and app deploys
  fail loudly when they diverge, and clear the seven red scheduled workflows so a red run means something) to the
  implementing session, separating measured facts from inferred cause and from owner-gated steps
component: supabase/migrations/, .github/workflows/supabase-production.yml, .github/workflows/build-images.yml,
  .github/workflows/notification-digest.yml, .github/workflows/e2e-prod.yml, docs/operations/runbook.md (section 2.5)
source: project review session 2026-09-19 (branch claude/project-review-critical-path-kbz6zn); one of four sprint handoffs
---

# Handoff: Sprint 1, restore production and make red mean something

Written 2026-09-19 from a read-only review of `main` at `2ca65e1` (v0.89.0), the live production host, GitHub
Actions run history, and the planning corpus. Nothing in this document has been fixed yet. Every "Current
State" claim carries the probe that re-establishes it; run the probe before acting, because the daily
tiers keep moving.

Sibling handoffs: Sprint 2 (catalog unblock), Sprint 3 (R1 full sign-off), Sprint 4 (R2 preparation), all
dated 2026-09-19. Sprints 2 and 3 name this sprint as their prerequisite.

## Goal / Intent

Two goals, in order. First, a guardian can open the Books page and a kid can open the library in
production again. Second, the alerting that should have caught the outage within a day is restored to a
state where a newly red scheduled workflow is visible: today seven are on escalated red streaks, so an
eighth is invisible, and one of them is a product feature that has never executed.

## Current State

### The production outage

- **Symptom.** The daily `e2e-prod` tier (`.github/workflows/e2e-prod.yml`, cron 13:30 UTC) has failed
  the same three specs on every run from 2026-09-14 through 2026-09-18 (issue #824, one comment per
  run): `guardian-admin-smoke.spec.ts` "/guardian/books renders without the error boundary",
  `guardian-books-and-isolation.spec.ts` "the books page lists the family's assigned books", and
  `kid-device-grant.spec.ts` "the authorized device opens the test kid library". The captured error on
  every run is `Expected the <h1> "Books" to be visible, and it was not.` with an empty `role=status`.
  The other six smoke routes (`/guardian`, `/guardian/intake`, `/guardian/requests`, `/guardian/profiles`,
  the admin routes) pass.
- **Deployed release.** `https://cyo.williamshome.family/api/v1/health/` returns `version: 0.89.0`
  (checked 2026-09-19 11:32 UTC). v0.89.0 was released 2026-09-14 (PR #823); the first red run is the
  same day.
- **Schema state.** The last production migration deploy (`supabase-production.yml`, `workflow_dispatch`
  only, gated by the `production` environment's required reviewer) ran 2026-08-24 at `bfcfd8d2`. Three
  migrations merged to `main` after that date and are therefore not applied `[VERIFY with the probe
  below]`:

  | Migration | Merged | What the deployed code does with it |
  | --- | --- | --- |
  | `20260831120000_seed_moderation_threshold_grid.sql` | #797, 2026-09-03 | `moderation_threshold` rows the admin console's threshold editor reads (`RS-B2`; the remediation plan records it as "not applied to production") |
  | `20260831130000_add_storybook_recalled_to_pipeline_event.sql` | #797, 2026-09-03 | `EventType.STORYBOOK_RECALLED` written by the new RECALL transition |
  | `20260908000000_add_cover_review_columns.sql` | #816, 2026-09-13 | Three `storybook_version` columns (`cover_review_verdict`, `cover_review_notes`, `cover_review_attempts`) mapped in `db/models.py` and selected by every ORM load of `StorybookVersion` |

- **Inferred cause, not yet observed.** The books page calls `assignApi.listBooks()`
  (`frontend/src/guardian/BooksPage.tsx:91`), whose backend (`api/assignments.py`) loads
  `StorybookVersion`; the kid library (`api/library.py:520`) runs `select(StorybookVersion)`. Under
  v0.89.0 both select the three cover-review columns. If production lacks them, the first such query
  raises an undefined-column error, the endpoint returns 500, and the page renders the error boundary
  while `/health/ready` stays green because its database check opens a connection and never inspects the
  schema. Runbook section 2.5 describes this exact class ("the deployed app declares ORM columns and
  tables the live database does not have ... a 500 on real traffic against a service whose health
  endpoint is green"). The profiles route passes because `child_profile` gained no columns. This session
  did not capture the 500 body or the Playwright `error-context.md`, so the cause is inferred from
  four consistent facts, not observed. The probe settles it:

  ```bash
  # Applied on PRODUCTION (session-mode pooler URL from runbook section 6; never --linked, that is staging)
  supabase migration list --db-url "$SUPABASE_DB_URL"
  # What main carries
  git ls-tree --name-only origin/main supabase/migrations/ | tail -5
  # Direct check of the column
  psql "$SUPABASE_DB_URL" -c "select column_name from information_schema.columns where table_name='storybook_version' and column_name like 'cover_review%';"
  ```

  If the three migrations are listed as applied and the column exists, the inference is wrong: go to
  the Playwright `error-context.md` artifact of the latest #824 run and the backend logs for the
  correlation id, and treat this as an ordinary regression in #816 or #797.

### The scheduled-workflow red streak

Issue #801 (health rollup, 2026-09-03) lists seven workflows at or above the three-failure escalation
bar. A subagent pulled the latest failing run of each on 2026-09-19; the classification is that
subagent's and this author's, from log text, and should be re-derived from the current run before
fixing:

| Workflow | Latest run state | What the log says | Class |
| --- | --- | --- | --- |
| `notification-digest.yml` | Every scheduled run since 2026-08-09 ends `cancelled`; no green run ever (23 by 09-03) | No step fails. The job declares `environment: production`, whose required-reviewer rule parks each run in `waiting` until the next day's cron displaces it as `cancelled`. `e2e-prod.yml`'s own header comment documents this pattern for its environment key; `supabase-backup.yml` hit it for weeks (runbook section 6). The daily digest that `roadmap.md` marks delivered (`S9`, 2026-08-09) has never executed | Infra: environment gating, and a stale-positive in the plan |
| `mutation-testing.yml` | 10 of 10 recorded runs failed, latest 2026-09-13 | `FileNotFoundError: .../mutants/.claude/skills/naive-ux-check/render.py` during baseline collection: `tests/unit/test_naive_ux_scenarios.py` loads `render.py` from `.claude/skills/`, which mutmut's copied tree omits, so no mutant ever runs | Test defect |
| `e2e-real-nightly.yml` | 37 consecutive by 09-03; identical failures 09-15 to 09-19 | `real-backend` step passes; `full-pipeline` and `usersim-real` fail: `full-pipeline-real.spec.ts` (guardian concept to `in_review`), `full-pipeline-negative-real.spec.ts` (worker HARD-BLOCKS the invalid fixture), `connections-enforcement-real.spec.ts`, and `e2e-usersim/walk-real.spec.ts > admin` | Product defect in the real generation and gate path, or its fixtures; not a flake |
| `e2e-staging.yml` | 30 consecutive by 09-03; latest 2026-09-19 | `kws-public-urls.spec.ts:154` service-worker navigation assertion `Expected: true, Received: false`; plus `Leaked staging device grant id-not-captured, revoke it manually` from `moderation-qa-invisibility` teardown, which the workflow itself flags as a potential unrevoked grant | Product or test defect, plus a security-relevant teardown gap |
| `container-security.yml` | 4 consecutive by 09-03; latest 2026-09-16 | Trivy: `CVE-2026-76957 libexpat ... Memory corruption` above the HIGH/CRITICAL gate | Dependency drift in the base image (same family as #798's Expat acceptance) |
| `python-compatibility.yml` | Red 08-16 to 08-30; green 09-06 and 09-13 | Recovered | Not currently failing; the rollup is stale |
| `link-check-full.yml` | 3 consecutive; latest 2026-09-14 | lychee rejects `https://pubmed.ncbi.nlm.nih.gov/15968234/` for HTTP `203 Non Authoritative Information` (2 errors of 2,115) | Tooling config: 203 not in the accepted-status list |
| `security-analysis.yml` (not in #801) | Green 09-17, red 09-18 and 09-19 | OSV-Scanner exit 1 over `frontend/package-lock.json`, `frontend/design-system/package-lock.json`, `uv.lock`; Semgrep passed; advisory ids are only in `osv-scanner-report.json` | Dependency drift, new advisory |

Five Renovate PRs (#825 to #829, opened 2026-09-15) are waiting on automerge; one may carry the OSV fix.

### What is healthy

`ci.yml` green on `main` (2026-09-15); release, backup, scorecard, and the weekly accessibility scan
green; Ruff 0, BasedPyright 0 errors, `tsc` and ESLint clean; generated client in sync with the API.

## What Was Done

No fix was applied. This session established the state above by: reading issue #824 and its four
comments; pulling the failed job log of run 35351212259; probing the production health endpoint;
listing `supabase-production.yml` run history; diffing `main` for migrations added after 2026-08-24;
reading runbook section 2.5 and `build-images.yml`; and delegating the per-workflow log extraction.

## What Remains

Ordered. Goal first; mechanism only where obvious or flagged as assumed.

1. **Confirm the cause with the probe, then apply the pending migrations.** Goal: production schema
   matches v0.89.0. Owner-gated: `supabase-production.yml` is `workflow_dispatch` behind a required
   reviewer. Follow runbook section 2.5 exactly: take a fresh three-file dump first (roles, schema,
   data, with `--db-url`, never `--linked`), confirm the tiered R2 backups actually hold a recent
   artifact, dispatch at the ref you measured against, and run all four post-deploy checks. Production
   pushes without `--include-all`, so an out-of-order file is skipped silently; the three files sort
   after `20260823160000`, so they will apply, but check the applied list afterwards anyway.
2. **Verify recovery from the outside.** Goal: the next `e2e-prod` run is green and #824 closes itself.
   Do not wait for the cron: dispatch `e2e-prod.yml` manually if it allows it `[VERIFY]`, or run the
   three specs locally against production with the test account. Confirm the guardian Books page and the
   kid library in a browser once.
3. **Make schema and app deploys fail loudly when they diverge.** Goal: this class of outage cannot
   recur silently. Three layers, weakest first; the design choice among them is a Fable-tier item
   because each moves risk somewhere (a refused start is itself an outage):
   - A startup or readiness schema self-check in the API and worker: compare the ORM's mapped columns
     against `information_schema.columns` and fail `/health/ready` (not `/health/`) with a named
     reason. Cheapest; catches drift after deploy.
   - A publish-time preflight in `build-images.yml`: before "Build and push image", read production's
     applied migration list (read-only, session-mode URL) and refuse to publish an image whose ref
     carries migrations production lacks, with an actionable error naming them. Catches drift before
     deploy; needs a read-only production credential in CI, which is a security decision.
   - Coupling the migration dispatch into the release flow so the `chore(release)` merge cannot produce
     an image without the same ref's migrations being applied or explicitly deferred. Strongest;
     changes the release process the owner just rebuilt (#813, #767).
   Record the choice in the runbook section 2.5 and in an ADR amendment if the release process changes.
4. **Digest job: let it run, then decide whether it should have.** Goal: the daily digest either
   executes in production or its `S9` claim is corrected. Mechanism: either approve the pending run once
   and move the job off the required-reviewer environment (a separate environment holding only
   `CYO_ADVENTURE_DATABASE_URL`, as `supabase-backup.yml` eventually did) or keep the gate and change the
   claim. Then watch the first real run: a job that has never executed against production data will
   find its first bug on day one. Update `roadmap.md`'s 4c row and `capability-register.md` `S9`.
5. **Mutation testing: fix the collection defect.** Goal: mutmut reaches its baseline. Mechanism:
   make `test_naive_ux_scenarios.py` resolve `render.py` relative to the repository root it can find,
   or skip cleanly when `.claude/skills/` is absent, or include the path in mutmut's copied tree. Then
   look at what mutmut reports, because a job that has never passed has never reported a kill rate.
6. **Nightly real-backend E2E: root-cause the pipeline failures.** Goal: a guardian concept reaches
   `in_review` through the real worker and the invalid fixture is hard-blocked, nightly. Start with the
   worker logs of the latest run and the fixtures the three specs use; the identical failure set across
   five nights says deterministic. Escalate to a stronger model if the failure is in the generation and
   gate path rather than in the fixtures, because that path is the product's safety core.
7. **Staging E2E: two fixes.** Goal: the KWS public-URL service-worker assertion passes or is corrected,
   and the device-grant teardown always captures the id it must revoke. Sweep the staging test family's
   device-grant list by hand first, as the workflow instructs; an unrevoked grant is a security event
   on staging, not a diagnostic.
8. **Dependency and tooling drift.** Goal: `container-security.yml`, `security-analysis.yml`, and
   `link-check-full.yml` are green for reasons, not by suppression. Read `osv-scanner-report.json` from
   the latest run for the advisory ids and check whether #825 to #829 fix them; refresh the base-image
   digest for the Expat CVE as #798 did, accepting only with a written reason; add `203` to lychee's
   accepted status codes or replace the PubMed URL with its DOI.
9. **Rollup hygiene.** Goal: `#801` reflects reality. Close the `python-compatibility` entry; ensure every
   scheduled workflow has a per-workflow alert step (the rollup marks two as NOT TRACKED); mark the
   `security-analysis` failure so it appears in the next rollup.
10. **Record the stale positives.** `UW-L07` to `done` with `Ref` v0.68.2 and the 2026-09-19 health
    probe; `S9` corrected per item 4; a new register row for the deploy-coupling gap (cluster E or F) and
    a new `AL-*` lesson if any gate or validator changes as a result.

## Key Decisions

- **Apply migrations before any code change.** The fix for the outage is operational, not a commit;
  writing code first would delay recovery by a release cycle.
- **Prefer fail-loud over auto-apply for schema coupling.** Auto-applying migrations from the image
  start would give the app write access to production schema under the least-privilege `cyo_api` role
  the ADR-021 cutover deliberately removed; runbook 11.3 forbids operator scripts running as that role.
- **Clear the red streak rather than raise the escalation bar.** The rollup's purpose is to make a
  new red visible; that requires the baseline to be green or the workflow to be removed.

## Dead Ends / Rejected Approaches

- Trusting `/api/v1/health/ready` as evidence of schema state: it returns `database: true` on a
  connection open (runbook 2.5).
- Treating the `e2e-prod` failures as credential or account problems: the other six routes sign in
  and render, so the account and login work.
- Re-running the failing tiers to see if they pass: five identical nights on `e2e-prod`, five on
  `e2e-real-nightly`, and the `notification-digest` cancellation pattern are deterministic.

## User Corrections / Constraints

**Standing constraints:** `CLAUDE.md` (signed commits, Conventional Commits, no em-dash, RAD tagging,
security findings addressed rather than dismissed, never bypass a scanner without a written reason,
authoring-lessons row for any gate or validator change). Runbook section 2.5 pre-flight and post-deploy
checks. ADR-012 (forward-only migrations) and ADR-021 (service-account cutover).
**Corrections made this session:** none.

## Files Touched

None by this session. Files the sprint will touch, with the consumer that reads each:

- `supabase/migrations/` (nothing new; the three pending files are applied by `supabase-production.yml`,
  read by the Supabase CLI's migration history table).
- `.github/workflows/build-images.yml` "Build and push image" step, if the preflight is chosen: read
  by GitHub Actions on every push to `main`; the workflow's own `#CRITICAL` block explains its trigger
  set.
- `src/cyo_adventure/api/health.py::check_database` and the readiness model, if the self-check is
  chosen: read by the homelab health probe and by `e2e-prod` Section 0.
- `.github/workflows/notification-digest.yml` `environment:` key: read by GitHub's environment
  protection rules; the secret it needs lives on the `production` environment today.
- `tests/unit/test_naive_ux_scenarios.py:171` (`_load_render_module`): read by pytest under mutmut's
  copied tree at `mutants/`.
- `osv-scanner.toml`: read by the OSV-Scanner action; every `IgnoredVulns` entry needs a dated reason.
- `docs/operations/runbook.md` section 2.5 and section 7: read by the operator during the next
  incident; keep commands paste-correct.
- `docs/planning/unscheduled-work-register.md` (`UW-L07`, new row): read by
  `scripts/check_work_linkage.py`.

## How to Resume

1. Run the three probe commands under "Inferred cause" against production, read-only.
2. If confirmed: follow runbook 2.5 pre-flight (dump first), dispatch `supabase-production.yml` at the
   measured ref, run its four post-deploy checks, then item 2.
3. If not confirmed: fetch the `error-context.md` artifact from the latest #824 run and the backend log
   for its correlation id; treat as a regression in #816 or #797.
4. Then item 4 (approve one digest run and observe), then items 5 to 9 on a `fix/scheduled-ci-red-streak`
   branch, one PR per workflow so each fix is reviewable.
5. Item 3's design goes to a stronger model with this document; implement the chosen layer on
   `feat/schema-deploy-coupling`.

## Gotchas

- The runbook checkout is linked to **staging**; `--linked` reports the wrong database. Always
  `--db-url "$SUPABASE_DB_URL"` (session-mode pooler, port 5432; the direct host is IPv6-only).
- `supabase db push` on production runs without `--include-all`; an out-of-order migration is skipped,
  not applied, and the run still reports success.
- A `cancelled` scheduled run files no failure issue; the rollup is the only thing that surfaces it.
- The `production` GitHub environment's required-reviewer rule is load-bearing for
  `supabase-production.yml` and must stay; the digest job is the one that does not need it.
- The `e2e-prod` cron sits `pending` behind a required-reviewer rule the same way; read the
  `#CRITICAL` note at the top of `e2e-prod.yml` before adding any environment key to a scheduled job.
- Model tier: item 3 (deploy coupling design) is Fable-tier; item 6 escalates to a stronger model if
  the failure is in the generation and gate path. Items 1, 2, 4, 5, 7, 8, 9, 10 are Sonnet-suitable,
  with item 1 executed by the owner.

## Next-Session Kickoff Prompt

Resuming work on cyo-adventure. Goal: Sprint 1, restore the production Books page and kid library (red
on `e2e-prod` since v0.89.0 shipped 2026-09-14, issue #824), then clear the seven red scheduled
workflows in issue #801 so a new red is visible.

First, refresh state before acting (this handoff is a snapshot):

```bash
git fetch origin main && git status --short && git log --oneline -5
```

Immediate next action: confirm the inferred cause read-only, that three migrations merged after the
2026-08-24 production deploy (`20260831120000`, `20260831130000`, `20260908000000`) are unapplied while
v0.89.0 maps their columns:

```bash
supabase migration list --db-url "$SUPABASE_DB_URL"
```

If confirmed, follow runbook section 2.5 (dump first, dispatch `supabase-production.yml`, four
post-deploy checks), then verify `e2e-prod` goes green. Then approve one `notification-digest` run
(it has only ever been cancelled by the `production` environment gate) and fix the mutmut collection
path in `tests/unit/test_naive_ux_scenarios.py`.

Hard constraints: signed Conventional Commits, no em-dash, never `--linked` against production, no
scanner suppression without a written reason, migrations are forward-only.
Full handoff: docs/planning/handoff-sprint-1-restore-production-2026-09-19.md.
