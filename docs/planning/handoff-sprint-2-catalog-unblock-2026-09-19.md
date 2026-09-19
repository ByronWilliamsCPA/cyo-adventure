---
purpose: Hand the Sprint 2 work (make catalog books reachable for kids by clearing the in_review queue honestly)
  to the implementing session, separating what is measured from what is an owner ruling and what is still unverified
component: src/cyo_adventure/api/remoderate.py, scripts/remoderate_books.py, src/cyo_adventure/publishing/catalog_publish.py,
  src/cyo_adventure/api/review_surface.py, frontend/src/admin/ReviewDetailPage.tsx
source: project review session 2026-09-19 (branch claude/project-review-critical-path-kbz6zn); one of four sprint handoffs
---

# Handoff: Sprint 2, unblock the catalog

Written 2026-09-19 from a read-only review of `main` at `2ca65e1` (v0.89.0), production, and the planning
corpus. This is a plan for work not yet started, so every "Current State" claim is a dated snapshot and
every "What Remains" item is a hypothesis until the probe next to it is re-run.

**Prerequisite: Sprint 1 is done.** The three pending production migrations must be applied (one of them,
`20260831120000_seed_moderation_threshold_grid.sql`, seeds the threshold grid the admin console reads) and
the daily production E2E tier must be green. See `handoff-sprint-1-restore-production-2026-09-19.md`.

Sibling handoffs: Sprint 1 (restore production), Sprint 3 (R1 full sign-off), Sprint 4 (R2 preparation),
all dated 2026-09-19.

## Goal / Intent

A family that has not completed a custom story request should open the kid library and find books. Owner
ruling OG7 (2026-08-06, `story-structure-improvement-plan.md` section 8.1) made this an R1 usability gap
and a named blocker of the `M5.1` sign-off: the register row is `UW-G14`. The blocker is not "an admin
finding time to promote"; it is that most of the queued books cannot honestly clear the review gate
because their stored reports were produced by a mock or fail-safe reviewer. Sprint 2 clears the queue
honestly: real verdicts, a human decision per book on a surface that makes the decision possible, kid
bands first, and promotion to `visibility='catalog'`.

## Current State

Two censuses disagree about the queue, and the discrepancy is the first thing to resolve:

- **2026-08-25 census** (`safety/moderation-review-current-state-2026-08-25.md`, cited by `UW-G14` and
  `UW-C364`): 17 books at `in_review`, 10 published to `visibility='catalog'`. 12 of the 17 hold reports
  with no real verdict at all (every finding reads `unknown verdict; defaulted to fail-safe`; 5,856
  findings over 2,916 nodes). The other 5 hold real verdicts and 122 actionable findings. Two of those
  five carry hidden fail-safe PASSes on a large share of nodes (24 of 148, 22 of 25).
- **2026-08-31 census** (`review-screen-remediation-plan-2026-08-31.md` section 2.2): 13 books in the
  queue; across all 31 books carrying a report on their latest version, **zero are unusable**, because
  "the 2026-08-27 re-moderation sweep cleared the coverage gaps that PR #776 fixed".

The register row `UW-C364` (status `unscheduled`) still says the seventeen-book sweep "has not been run".
Either the 08-27 sweep is what it describes as not yet run and the row is stale, or the 08-27 sweep
covered only the published books and the 13 queued ones still carry mock verdicts. Do not resolve this
from the documents. Resolve it from production (probe below).

What is built and merged, with the PR that carried it:

| Capability | Where | PR / date |
| --- | --- | --- |
| Re-moderation admits `in_review` books, fail-closed slot contract | `api/remoderate.py`, `scripts/remoderate_books.py` (`--in-review`, `--book-id`, `--mock-moderated`, `--execute`, `--per-book-timeout`) | #760, #762 (2026-08-25) |
| Mock reviewer identifies itself; unusable reports are unapprovable; severe-finding overrides audited | `moderation/review_provider.py`, `publishing/service.py::approve` (`moderation_report_unusable`) | #769, #764 (2026-08-26/28) |
| Unreviewed story can no longer pass as soft-flagged; repaired report stamped from the resolved reviewer | `moderation/` | #776, #778 (2026-08-28) |
| Review surface made decidable: low advisories collapsed, findings-first, one canonical count, per-finding triage, queue triage, RECALL transition, recalled-books surface | `api/review_surface.py`, `frontend/src/admin/ReviewDetailPage.tsx`, `publishing/state_machine.py` | #797 (2026-09-03), plan section 12 |
| Pending-cover approval surfaced above the fold; AI cover review gate | `frontend/src/admin/`, `covers/review.py` | #795, #799, #816 |

Still not done (plan section 12 and register): `RS-CAL3`/`RS-CAL4` calibration (`UW-C476`, blocked on paid
classifier calls and a re-scope), `RS-B4` re-moderation of the queued books (`UW-J42`, `blocked`), and the
`RS-B2` migration (applied in Sprint 1, verify).

## What Was Done

This session changed no code. It established the state above from:

- `docs/planning/unscheduled-work-register.md` rows `UW-G14` (line ~907), `UW-C364` (~618), `UW-E17`
  (~810), `UW-L08` (~1047), `UW-C476`, `UW-J42`.
- `docs/planning/review-screen-remediation-plan-2026-08-31.md` sections 2, 3, 4, 5.5, 12.
- `docs/planning/safety/moderation-review-current-state-2026-08-25.md` sections 4.3, 6.1, 7.2.
- `git log` on `main` from 2026-08-25 to 2026-09-15.

## What Remains

Ordered. Each item states the goal; a mechanism is given only where it is the obvious one, and it is
flagged when assumed.

1. **Re-count the queue from production, read-only.** Goal: know how many books are at `in_review`, how
   many are at `visibility='catalog'`, and for each queued book whether its latest report carries real
   verdicts. Probe (read-only SQL through the authorised Supabase connection; column names `[VERIFY]`
   against `db/models.py` before running):

   ```sql
   select s.status, s.visibility, count(*) from storybook s group by 1, 2 order by 1, 2;
   select s.id, s.title, v.version,
          (v.moderation_report::text like '%unknown verdict; defaulted to fail-safe%') as has_failsafe_text,
          v.moderation_report->'summary'->>'reviewer_independent' as reviewer_independent,
          v.moderation_report->'summary'->>'reviewer' as reviewer
   from storybook s join storybook_version v on v.storybook_id = s.id
   where s.status = 'in_review'
     and v.version = (select max(version) from storybook_version where storybook_id = s.id)
   order by s.title;
   ```

   Update `UW-C364` and `UW-G14` with the result and the date. This closes the census discrepancy.

2. **If any queued book still lacks real verdicts: owner decides the sweep mechanism, then canary, then
   sweep.** Goal: every queued book has a report produced by an independent, non-mock reviewer.
   - Owner decision (recorded in `UW-C364` (a)): the script runs in-process against a chosen
     `DATABASE_URL` and stamps `Actor.system()`; the alternative is calling the deployed
     `api/remoderate.py` endpoint with an admin bearer token. Recommendation: the deployed endpoint,
     because it runs audited code under the production role model and leaves the pipeline event trail;
     runbook section 11.3 says operator scripts must not run as `cyo_api`. Assumption, not a finding:
     confirm the endpoint accepts a batch or loop over ids.
   - Canary first: `sk_sunken_signal` (32 nodes), dry run then `--execute`. Success is a report whose
     findings contain no `unknown verdict; defaulted to fail-safe` text and whose `summary.reviewer` is
     the live provider. A seventeen-book run against a still-broken reviewer spends on 2,916 nodes to
     reproduce the same non-result (census section 4.3).
   - Then the remainder with `--in-review` and a `--per-book-timeout`. Budget the run first from
     `unit-cost-model.md` `[VERIFY]` and record the spend authorisation as an owner decision.

3. **Review the books a human can decide today.** Goal: each queued book gets a human decision on the
   decidable surface (#797). The five books with real verdicts (census section 2.2) can be reviewed before
   any sweep. Order per owner ruling OG1: kid bands first (3-5, 6-8, 10-13), then 13-16 and 16+. Hold
   `the-sunken-temple` and `the-harrowstone-keep` pending the A9 restructure (OG1). Ruling 3 of
   2026-08-31 applies: the reviewer adjudicates findings, they do not read the whole book.

4. **Promote what passes.** Goal: reviewed books reach `visibility='catalog'`. Mechanism:
   `publishing/catalog_publish.py::promote_catalog_story`, which also has a CLI `main()`; the runbook
   route is the SQ-01 runbook referenced by `UW-G14`. Verify after each promotion that the kid library
   for the catalog family lists the book (the daily `e2e-prod` `kid-device-grant.spec.ts` covers the
   library opening but not book count, so check by hand once).

5. **Three owner rulings that sit inside this chain.** Put them to the owner together, early in the
   sprint, with the recommendation stated:
   - **Hidden fail-safe PASS threshold** (census section 7.2): the surface now renders a partly-unjudged
     report as one structural finding, but whether a partly-unjudged story is also *unapprovable* is an
     open decision. Recommendation: a per-book share threshold, stated in the register, above which the
     book is re-moderated rather than approved; below it, the reviewer decides with the finding visible.
   - **Hard block versus publish** (`UW-E17`, GA-D1): (a) hard block becomes publish-blocking, or (b) the
     override stays and becomes accountable. The register's review recommends (b) because (a)
     contradicts a twice-affirmed ADR-005 position. Under either, the five accountability requirements
     (typed override reason, blocking finding ids copied onto the approval, version hash pinned,
     separation of duties, audit trail) are the real work. Step 0 is a production query for published
     versions with `summary.hard_block: true`; a nonzero count makes this a live incident. Run it in
     item 1's probe session.
   - **Recall two published books** (`UW-L08`): `sk_vault_of_nine_iron` (block/high, drowning) and
     `sk_ninth_hand` (flag/high, suicidal intent). The RECALL transition now exists (`RS-C1`, #797), so
     this is a decision, not a build: recall now and re-moderate, or re-moderate in place first.
     Recommendation: recall first; they are child-facing today.

6. **Register and roadmap updates on exit.** `UW-G14` status and count; `UW-C364` (a) closed;
   `UW-L08` resolved; `UW-E17` ruling recorded; `M5.1` row in `roadmap.md` updated with the reachable
   catalog count.

## Key Decisions

- **Promotion does not wait for threshold calibration.** `RS-CAL3`/`RS-CAL4` stay blocked and that is
  acceptable: owner ruling 4 (2026-08-31) says unresolved findings must not automatically gate a book,
  and `RS-CAL1` showed the ratified floors remove 0.2 to 0.6 percent of surfaced occurrences while the
  shipped low-advisory collapse removed 96 to 100 percent. Calibration is a recall question now
  (plan section 5.5), not a reviewer-load question, so it belongs in Sprint 3 or later.
- **Canary before sweep.** Chosen because the 08-25 census showed size is not the selector for broken
  reports (import order is), so a full run cannot be reasoned about from one book's success unless that
  book was itself a mock-report case.
- **Kid bands first** is an owner ruling (OG1), not a preference.

## Dead Ends / Rejected Approaches

- Reading the whole book to review it: rejected by ruling 3; the plan's own census measured roughly
  1,360 screens and 481,000 words in the queue.
- Threshold recalibration as the path to a smaller queue: inverted by `RS-CAL1` (plan section 5.5).
- Selecting mock-moderated books by `reviewer_independent: false`: does not work, because the mock
  provider is constructed with `independent=True` and stamps itself independent (census section 6.1,
  fixed forward by #769 but historical rows keep the stamp). Only the fail-safe text substring reaches
  them.

## User Corrections / Constraints

**Standing constraints:** `CLAUDE.md` (signed commits, Conventional Commits, no em-dash, RAD tagging,
authoring-lessons requirement for any validator or gate change). Owner rulings OG1 and OG7
(`story-structure-improvement-plan.md` section 8) and rulings 1 to 6 of 2026-08-31
(`review-screen-remediation-plan-2026-08-31.md` section 3) govern scope.
**Corrections made this session:** none.

## Files Touched

None by this session. Files the sprint will touch, with the consumer that reads each:

- `docs/planning/unscheduled-work-register.md` rows `UW-G14`, `UW-C364`, `UW-E17`, `UW-L08`: read by
  `scripts/check_work_linkage.py` (pre-commit and the Planning Linkage workflow), so keep the status
  vocabulary exact.
- `docs/planning/roadmap.md` `M5.1` row: read by humans only.
- If `UW-E17` ruling (b) is chosen: `api/approval.py` (`ApproveBody`), `publishing/service.py::approve`,
  `db/models.py`, a new migration under `supabase/migrations/`, and `tests/unit/test_node_edit.py:846`
  which currently locks the present behaviour. Any validator or gate change here requires a row in
  `docs/planning/authoring-lessons-log.md` (`CLAUDE.md`, Authoring Lessons Requirement).

## How to Resume

1. Confirm Sprint 1 exit: `curl -s https://cyo.williamshome.family/api/v1/health/` reports the current
   release, issue #824 is closed, and `supabase migration list --db-url "$SUPABASE_DB_URL"` shows
   `20260908000000` applied.
2. Run the item 1 probes read-only and record the counts in `UW-G14` and `UW-C364` with today's date.
3. Batch the three owner rulings in item 5 into one message to the owner with recommendations.
4. Branch: `git checkout -b feat/catalog-unblock` from `origin/main`.
5. Proceed by the branch the probe result puts you on: reports usable, go to items 3 and 4; reports
   not usable, go to item 2.

## Gotchas

- Classifier quota exhaustion surfaces as a job that stalls at the moderation step with no error in the
  UI; a hang is a 429 in the worker logs until proven otherwise (`r1-live-e2e-checklist.md`, Known
  blockers).
- `moderation_report_unusable` returns `False` at the first genuine finding, so a report that is 88
  percent fail-safe PASS still reads as usable to the approval gate (census 7.2). The surface shows it;
  the gate does not.
- The queue count in the two censuses differs (17 versus 13) and the register still says the sweep is
  unrun. Treat both as stale until the probe runs. `[VERIFY]`
- Re-moderation of a `published` book may never auto-repair; only `in_review` books may be repaired
  (`UW-C364`). Do not widen that.
- Model tier: item 5's `UW-E17` design and the threshold framing are Fable-tier reasoning (safety
  invariants across three packages, an ADR position, and a locked test). Items 1 to 4 and 6 are
  well specified for Sonnet.

## Next-Session Kickoff Prompt

Resuming work on cyo-adventure. Goal: Sprint 2, make catalog books reachable for kids by clearing the
`in_review` queue with real verdicts and human decisions, kid bands first (`UW-G14`, owner ruling OG7).

First, refresh state before acting (this handoff is a snapshot):

```bash
git fetch origin main && git status --short && git log --oneline -5
```

Confirm Sprint 1 exit first: production health reports the current release, issue #824 is closed, and
migration `20260908000000` is applied. Then run the read-only production probes in "What Remains" item 1
and record the counts in `UW-G14` and `UW-C364`; the 08-25 and 08-31 censuses disagree and the probe
settles it. Batch the three owner rulings (fail-safe PASS threshold, `UW-E17` hard-block accountability,
`UW-L08` recall of two published books) into one message with recommendations.

Hard constraints: signed Conventional Commits, no em-dash, kid bands first, hold `the-sunken-temple` and
`the-harrowstone-keep` (OG1), canary `sk_sunken_signal` before any sweep.
Full handoff: docs/planning/handoff-sprint-2-catalog-unblock-2026-09-19.md.
