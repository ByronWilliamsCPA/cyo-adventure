---
purpose: Hand the Sprint 3 work (declare R1 full, M5.1, on evidence rather than on documents) to the implementing
  session, separating the owner-gated live checklist from engineering work and from a stale-positive audit of the plan
component: docs/planning/r1-live-e2e-checklist.md, docs/operations/runbook.md (section 6), docs/planning/roadmap.md,
  docs/planning/capability-register.md, docs/planning/unscheduled-work-register.md
source: project review session 2026-09-19 (branch claude/project-review-critical-path-kbz6zn); one of four sprint handoffs
---

# Handoff: Sprint 3, R1 (full) sign-off

Written 2026-09-19 from a read-only review of `main` at `2ca65e1` (v0.89.0), production, GitHub, and the
planning corpus. A plan for work not yet started: every claim below is a dated snapshot, re-probe before
acting.

**Prerequisites: Sprints 1 and 2 are done.** Production is green on the daily E2E tier, the seven red
scheduled workflows are green or removed, and the catalog is reachable for kid bands. Without Sprint 1 the
live checklist would be executed against a broken books surface; without Sprint 2 the `M5.1` row stays
blocked by `UW-G14` regardless of what else passes.

Sibling handoffs: Sprint 1 (restore production), Sprint 2 (catalog unblock), Sprint 4 (R2 preparation),
all dated 2026-09-19.

## Goal / Intent

`roadmap.md` defines `M5.1 = R1 (full)` as "every family-tier register row at delivered status; the five
golden journeys green on the full test ladder". The project has twice declared parts of this done and
twice corrected itself (2026-07-20 and 2026-08-09 audits). Sprint 3 gets to a sign-off row that is backed
by evidence a later reader can re-run, and it fixes the two structural reasons past declarations went
stale: capabilities marked delivered whose job never ran, and a plan whose headers lag its rows by weeks.

## Current State

- **Live E2E checklist** (`r1-live-e2e-checklist.md`): 38 steps, 10 ticked as of 2026-08-08 at v0.68.0.
  Sections 0, 1, 1a advanced from CI evidence. Sections 2 to 6 (28 steps) are owner-gated: interactive
  sign-in as both test accounts, funded provider quota (Sections 2 and 4 spend real generation and Stage-0
  classifier calls), a maintenance window for the mutating worker-restart step, and a second physical
  device with a real offline transition for Section 5. Section 5 "stays manual permanently".
- **Issue #639 / `UW-L07`** (guardian profile resolution before RLS context): fixed in PR #641, shipped in
  v0.68.2. Production reports v0.89.0 as of 2026-09-19, so the fix is deployed. The register row still
  says `unscheduled` and the roadmap `M4.1` row still says "stays live in production until redeployed".
  Both are stale positives in the other direction: work done, record not updated.
- **Notification digest (`S9`)**: `roadmap.md` marks it delivered 2026-08-09. The scheduled workflow
  `notification-digest.yml` has no green run in its recorded history (23 runs by the 2026-09-03 health
  rollup, issue #801); each run parks in `waiting` behind the `production` environment's required
  reviewer and is cancelled by the next day's cron, so the job has never executed. Sprint 1 owns the
  fix; Sprint 3 owns the audit that finds the next one of these.
- **Backups and restore** (runbook section 6): first successful scheduled backup 2026-08-27 after weeks of
  silent failure; the restore procedure is documented and carries a `#CRITICAL` stating it "has NOT been
  exercised end-to-end against a real Supabase project". Cover-art object storage in R2 has no backup.
- **Retention policy**: `data-retention-policy.md` is `status: draft`; three data classes (consent
  evidence, product analytics, application logs) read "Not yet set, owner ruling required" (`UW-N07`,
  status `decision`).
- **Register rows still open under `M4b` to `M5`** per `roadmap.md`: G15 removal path not wired into
  client eviction (narrow, deliberate); no integration or e2e test drives ring-2 dual consent over the
  real stack (`M4d`); H1 band check fail-open on blobs lacking band metadata; H2 automated image
  classifier (the AI cover review gate in #816 may close this, unverified); Phase 5 performance pass.
- **Test suite**: `CLAUDE.md` targets under 30 seconds for the full suite; this session's collection-only
  run did not finish in five minutes across 442 test files. Lint and type checks are clean (Ruff 0,
  BasedPyright 0 errors, `tsc` and ESLint clean).
- **Plan staleness**: `roadmap.md` header "Updated 2026-07-20", "Current Status (2026-07-03)";
  `PROJECT-PLAN.md` v2.8 "Updated 2026-07-20"; `capability-register.md` v1.10 (2026-08-08). Rows inside
  carry edits to 2026-08-22. The project's own history shows two full audits triggered by gaps of 10 and
  12 days; this gap is about six weeks.

## What Was Done

No code changed. State established from: `r1-live-e2e-checklist.md` (sections 0 to 6 and Sign-off),
`roadmap.md` (Milestones table, Phase 5 deliverables), `docs/operations/runbook.md` sections 6 and 7,
GitHub issues #639, #801, #824, the register rows named above, and this session's toolchain run
(`uv run ruff check .`, `uv run basedpyright src/`, `npm run typecheck`, `npm run lint`, all clean).

## What Remains

Ordered by what unblocks the sign-off soonest. Goal first; mechanism only where obvious or flagged.

1. **Stale-positive audit of every delivered claim in the `M4.1` to `M5.1` rows.** Goal: each ✅ names
   the evidence that proves it today (a green scheduled run, a test file, a production probe), and each
   claim without evidence is flipped to 🟡 with a probe. Method: for every capability whose delivery
   depends on a scheduled job, check the workflow's run history, not the merge (the `S9` pattern). For
   every "fixed" defect, check the deployed version against the fixing release (the `UW-L07` pattern).
   Lesson `AL-723` in `authoring-lessons-log.md` already names this failure class; cite it. This item is
   Fable-tier: it is adversarial verification of claims the documents have repeatedly gotten wrong.
   Probe for the deployed release:

   ```bash
   curl -s https://cyo.williamshome.family/api/v1/health/ | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])'
   ```

2. **Execute the live E2E checklist Sections 2 to 6.** Goal: the 28 owner-gated steps get a real run
   and a dated sign-off row at the current release. Owner supplies: both interactive sign-ins, a spend
   authorisation for Sections 2 and 4, a maintenance window for the worker restart, and the second
   device for Section 5. Engineering prepares: the exact release under test (record image digests as the
   2026-08-08 row did), a fresh backup before the mutating steps, and the "Known blockers" list re-read.
   Do not advance a step from CI evidence unless it asserts a property of the deployed system rather
   than a journey through specific data (the checklist's own 2026-08-08 rule).

3. **Restore drill.** Goal: prove a tiered R2 backup restores to a working database. Mechanism (runbook
   section 6, "Restore procedure"): restore into a scratch Supabase project or branch, never production,
   then run the read-only Section 0 infrastructure probes against it. Record duration and every deviation
   from the runbook in the runbook itself. Remove the `#CRITICAL` "never exercised" line only when the
   drill has a dated row. Sonnet-suitable once the scratch target exists (owner creates it).

4. **Back up cover-art object storage.** Goal: an R2 bucket loss does not lose every cover. Mechanism
   assumed, not decided: extend `scripts/backup_database.py`'s tiered upload with an object-storage sync,
   or a bucket-to-bucket replication rule. Reuse the `.cyo-backup-bucket` marker guard.

5. **Retention policy rulings and publication.** Goal: `data-retention-policy.md` moves from `draft` to
   active with a window for all classes. Owner rules on the three unset classes (`UW-N07`); engineering
   confirms each window has a purge job or a documented manual step (`notifications/`, `events/`,
   `ADR-007` purge job).

6. **Close or explicitly defer the narrow `M4b` to `M5` residuals.** Goal: each has a decision, not a
   drift. G15 eviction wiring (`downloadBudget.ts`, `revocation.ts`, both deliberately network-free);
   ring-2 dual-consent e2e over the real stack; H1 fail-open on missing band metadata (recommend
   fail-closed, it is a kids' safety check); H2, verify whether #816's cover review gate satisfies it and
   update the row either way.

7. **Test-suite time.** Goal: a measured number against the 30-second target and a decision. Measure
   collection and execution separately (`uv run pytest --co -q` timed, then the unit tier). If the target
   is unreachable, change the target in `CLAUDE.md` rather than leaving a fiction; if it is a collection
   cost (import-time work in `tests/conftest.py` or plugin autoload), fix that first.

8. **Reconcile the plan.** Goal: `roadmap.md`, `PROJECT-PLAN.md`, `capability-register.md`, and
   `docs/planning/index.md` carry current headers and agree on `M4.1`, `M5.1`, `UW-G14`, `UW-L07`, and
   `S9`. Bump the register version. Then write the `M5.1` sign-off row with the release, digests, and
   the checklist count.

## Key Decisions

- **Audit before checklist.** Running the 28 live steps first would sign off against a plan that still
  says a fixed bug is live and a never-run job is delivered. The audit is cheaper than a wrong sign-off.
- **Restore into scratch, never production.** Migrations are forward-only (ADR-012) and the only recovery
  from a bad restore is another restore.
- **Change unreachable targets rather than ignore them.** The 30-second test target is either a real
  constraint that shapes the suite or noise; leaving it as noise trains readers to ignore `CLAUDE.md`.

## Dead Ends / Rejected Approaches

- Advancing checklist steps from daily CI evidence for journey steps: the checklist's 2026-08-08
  revision already ruled this out; it settles property steps only.
- Simulating airplane mode for Section 5: rejected by the checklist because the point is the browser's
  own network-loss handling and the service worker's cached state.
- Declaring `M5.1` from register symbols alone: v1.7 of the register had to be issued specifically to
  resync symbols with delivery notes; symbols are not evidence.

## User Corrections / Constraints

**Standing constraints:** `CLAUDE.md` (signed commits, Conventional Commits, no em-dash, 80 percent
coverage, RAD tagging). Owner ruling OG7 makes `UW-G14` an `M5.1` blocker. The checklist's own rules on
what counts as a tick.
**Corrections made this session:** none.

## Files Touched

None by this session. Files the sprint will touch, with their consumers:

- `docs/planning/r1-live-e2e-checklist.md` Sign-off table: read by humans; the `M5.1` row cites it.
- `docs/operations/runbook.md` section 6: read by the operator during an incident; keep commands
  paste-correct and note which checkout is linked to which project (the runbook warns `--linked`
  points at staging).
- `docs/planning/unscheduled-work-register.md`: read by `scripts/check_work_linkage.py`; a row moved to
  `done` needs a `Ref` that proves it (PR or commit).
- `docs/planning/authoring-lessons-log.md`: read by `scripts/check_lessons_log.py`; any gate or
  validator change (H1 fail-closed would be one) requires a row.
- `data-retention-policy.md` (under `docs/`, locate with `find docs -name data-retention-policy.md`):
  excluded or included by `mkdocs.yml` `exclude_docs`; a `status:` change may affect the docs build
  under `strict: true`. `[VERIFY]`
- `CLAUDE.md` Performance Targets table, only if item 7 changes the target.

## How to Resume

1. Confirm Sprint 1 and 2 exits: issue #824 closed, health rollup issue #801 shows no escalated
   workflows, kid library lists catalog books for the catalog family.
2. Start with item 1: list every ✅ in `roadmap.md`'s Milestones table and Phase 5 checklist into a
   scratch table with an evidence column; fill it from CI run history and production probes, not from
   PR merges.
3. Send the owner one message with the Sprint 3 asks batched: the four checklist gates (credentials,
   spend, window, device), the scratch Supabase target for the restore drill, and the three retention
   windows.
4. Branch: `git checkout -b docs/r1-full-signoff` from `origin/main`; code changes (H1, G15, backup
   sync) go on their own `fix/` or `feat/` branches.

## Gotchas

- `/api/v1/health/ready` opens a connection and returns `database: true`; it never inspects the schema
  (runbook 2.5). Green readiness is not evidence the deployed ORM matches production.
- The runbook checkout is linked to staging; `--linked` commands report the wrong database. Always pass
  `--db-url "$SUPABASE_DB_URL"` for production reads.
- The 2026-08-08 checklist run found a live P1 (#639) that had passed every unit and integration test
  because RLS never applies to a table's owner and the tests ran as the owner. Section 0 probes that run
  as `cyo_api` are the only ones that would catch a recurrence.
- The register permits one token per `Phase` cell; `UW-G14`'s `M5.1` linkage is stated in its text,
  not its `Phase`. Do not "fix" that.
- Model tier: item 1 is Fable-tier (adversarial verification with a history of confident wrong claims);
  items 2 to 8 are Sonnet-suitable, with item 6's H1 fail-closed change reviewed by a stronger model
  because it is a kids' safety gate.

## Next-Session Kickoff Prompt

Resuming work on cyo-adventure. Goal: Sprint 3, sign off `R1 (full)` (`M5.1`) on evidence: a
stale-positive audit of every delivered claim, the 28 owner-gated live checklist steps, a restore drill,
retention rulings, and a reconciled plan.

First, refresh state before acting (this handoff is a snapshot):

```bash
git fetch origin main && git status --short && git log --oneline -5
```

Confirm Sprints 1 and 2 exited (issue #824 closed, #801 shows no escalated workflows, catalog books
reachable). Immediate next action: build the evidence table for every ✅ in `roadmap.md`'s Milestones
table, sourcing from CI run history and production probes rather than PR merges; the known stale
positives are `S9` (digest job never executed) and `UW-L07` (fixed and deployed, row says unscheduled).
Then batch the owner asks: checklist gates, a scratch Supabase target for the restore drill, three
retention windows (`UW-N07`).

Hard constraints: signed Conventional Commits, no em-dash, restore into scratch never production,
checklist ticks follow the checklist's own 2026-08-08 rule.
Full handoff: docs/planning/handoff-sprint-3-r1-signoff-2026-09-19.md.
