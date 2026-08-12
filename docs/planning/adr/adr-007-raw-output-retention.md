---
title: "ADR-007: Raw LLM output retention policy for GenerationJob.report"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the retention policy for raw LLM outputs stored in GenerationJob.report."
tags:
  - planning
  - architecture
  - decisions
  - privacy
---

# ADR-007: Raw LLM output retention policy for `GenerationJob.report`

> **Status**: Accepted (2026-07-16; see Amendment below)
> **Date**: 2026-06-29

## Amendment (2026-08-11): the on-publish purge is removed

**This reverses a decision this ADR previously took deliberately, so read the reversal, not
just the new state.** The 2026-08-10 amendment below explicitly left the on-publish purge in
`publishing/service.py::approve` alone, describing it as "unchanged". That is no longer true:
the purge is deleted, and the nightly `pg_cron` predicate is now the sole thing that decides
this column's retention.

The reason is that the two mechanisms contradicted each other. The 2026-08-10 exemption has an
approve half: a `generation_job` whose storybook reaches `published` or `archived` is skipped
by the sweep, so its raw output survives to serve the calibration corpus. But `approve()` is
the *only* path that sets `storybook.status = "published"`, and in the same transaction it
nulled that version's own `report`. The exemption therefore protected a column that was already
NULL by the time it could ever apply. The approve half of the exemption preserved nothing for
the version that was published; it reached only earlier sent-back versions on the same
storybook, which the send-back half already covers. Whatever the on-publish purge was worth
when the sweep was unqualified, once the exemption shipped the two encoded opposite intents
about the same rows, and the one that ran first always won.

Consequences, stated plainly because this widens retention:

- **A reviewed book's raw LLM output now persists.** Before this change, a published version's
  `report` was nulled within milliseconds of approval. After it, that report is retained for
  the life of the storybook, exactly as long as the send-back case already was. This is the
  behaviour the 2026-08-10 amendment argued for; it simply did not take effect on the approve
  path.
- **Nothing is retained by *this exemption* without a human decision attached.** The nightly sweep
  still nulls the report of any job whose storybook never reached a human (a `draft` or `in_review`
  with no send-back event, or a job whose `storybook_id` resolves to no row) after 30 days. The
  machine-rejected `auto_reject` path writes no `sent_back` event and so is still purged.

  The claim is scoped to the exemption on purpose, because the unscoped version is false and was
  stated that way in an earlier draft. The sweep's predicate is gated on
  `status IN ('passed', 'needs_review', 'failed')`, and `generation_job.status` has six legal
  values, so `queued`, `running` and `awaiting_manual_fill` are matched by no purge condition at
  all and their `report` is never nulled on any timer, decision or no decision. `queued` and
  `running` are transient and normally carry no report; `awaiting_manual_fill` is by definition a
  run parked waiting on a person and can sit indefinitely. That gap predates both amendments and
  neither closes it.

  A second, opposite gap belongs to the 2026-08-10 amendment itself: the exemption is evaluated
  when the sweep runs, not when the decision is recorded, so it does not protect a slow review.
  A job at status `passed` whose storybook is still `in_review` on day 31 is purged, and the
  approval on day 32 flips the storybook to `published` against a column that is already NULL.
  The calibration-corpus rationale below therefore holds only for reviews concluding inside 30
  days of the job's last update. Tracked as `UW-C227` with
  `test_slow_review_report_is_purged_before_the_human_decides` pinning the current behaviour. Closing it means widening the predicate to every non-exempt status, which is a
  separate decision with its own deletion consequences and is tracked as a known gap in
  `docs/compliance/data-retention-policy.md` Section 4 rather than assumed here.
- **The rollback coupling is gone, and is not needed.** The old purge lived in the publish
  transaction so a rolled-back publish also rolled back the purge. With no purge on that path,
  there is nothing to keep consistent; a rolled-back publish leaves a non-`published`
  storybook, which the nightly sweep then treats as undecided and purges on the normal 30-day
  schedule.
- **The compliance record is updated in the same change**, closing the documentation debt the
  2026-08-10 amendment flagged: `docs/compliance/data-retention-policy.md`'s
  `generation_job.report` row and its Section 4 list now describe the amended predicate and the
  removal of the on-publish leg.

`tests/unit/test_report_retention.py::test_approve_does_not_purge_generation_job_report` and
`::test_approve_issues_no_update_statements` assert the absence, so a future change that
reintroduces the purge fails rather than silently re-emptying the corpus.

## Amendment (2026-08-10): reviewed-storybook exemption for the 30-day sweep

The review-scorecard calibration effort needs a corpus of human-reviewed books
paired with their original raw generation output (`GenerationJob.report`) and
the reviewer's decision. The unqualified 30-day sweep below destroys that
pairing for any job whose storybook took longer than 30 days to reach a
decision, one day at a time, so it now carries a narrow exemption:
`supabase/migrations/20260810000000_exempt_reviewed_generation_job_report_from_purge.sql`
amends the `purge_generation_job_report` pg_cron job in place (same job
name, unschedule-then-reschedule) to skip a `generation_job` row when a
**human** review decision was reached about the storybook it produced, in
either direction:

- **approve**: `storybook.status` is `published` or `archived` (archived is a
  published book pulled later; both required a human approve).
- **send-back**: a `sent_back` row exists in `pipeline_event` for that
  storybook.

The send-back half deliberately keys on the **event**, not on
`storybook.status = "needs_revision"`. A story reaches `needs_revision`
without any human seeing it via the `draft --auto_reject--> needs_revision`
hop that `moderation/pipeline.py` drives on a hard classifier BLOCK.
Exempting on that status would preserve every machine-rejected story's raw
output indefinitely, which widens this ADR's retention window with no human
decision to justify it, and fills the calibration corpus the exemption exists
to serve with rows carrying no reviewer judgment. Only
`publishing/service.py::send_back` writes a `SENT_BACK` event, so it is the
human-only marker. (Note `publishing/state_machine.py`'s docstring still
describes the `auto_reject` hop as having "no slice-1 caller"; that is stale.)

`draft` and `in_review` storybooks with no send-back event, and jobs whose
`storybook_id` resolves to no row at all, are not exempt: the default 30-day
retention this ADR decided still applies to a job that never reached a human. The on-publish
purge in `publishing/service.py::approve` (below) is unchanged: it still
nulls the just-published version's own `report` immediately, so the
exemption's practical effect is mostly for a storybook that was sent back
(and any earlier job/version on the same storybook once any later job on it
is decided) rather than for the version that ends up published.

> **Superseded 2026-08-11**: the paragraph above is the reason the on-publish purge was
> removed a day later. Leaving it in place meant the approve half of this exemption could
> never preserve anything, since the only path that sets `published` nulled the report in the
> same transaction. See the 2026-08-11 amendment at the top of this ADR. Everything else in
> this amendment still holds.

**What the retained label actually is.** The corpus this exemption preserves pairs raw output
with an approve or a send-back, and that is a *decision*, not evidence that anyone read the
book. Approval is a single state transition with no attestation, no per-passage
acknowledgement and no reading-progress requirement (see
`docs/planning/cyo-review-response-2026-08-11.md` Q2), so a scorecard calibrated on this
corpus inherits whatever sampling the reviewer actually did rather than a full read.

**Known ordering hazard: this change is split across two pull requests.** The migration that
implements the exemption is in PR #684; this ADR amendment is in PR #685. Whichever merges
first leaves `main` briefly inconsistent: either the schema skips human-decided jobs while the
ADR still records an unqualified sweep, or the ADR records an exemption the database does not
yet perform. Neither state is harmful, but neither is self-describing either, so read the two
together until both have landed.

**Known documentation debt: the compliance record is in neither PR.**
`docs/compliance/data-retention-policy.md` (the `generation_job.report` row, around line 66,
and its Section 4 "Enforced by shipped code" list) still states the unconditional 30-day
purge and marks it **Enforced**, citing only the original
`20260718000000_add_report_retention_purge.sql`. That file is out of scope for both PRs, so
until it is updated the compliance record asserts an enforcement the schema no longer
performs for human-decided jobs.

> **Closed 2026-08-11**: both places named above now describe the amended predicate and the
> removal of the on-publish leg.

## Amendment (2026-07-17): purge implemented (Phase 5, M5 register item S10)

Both halves of the purge described in the TL;DR and Decision sections below are now
built, closing the "raw output currently persists indefinitely" gap the 2026-07-16
amendment flagged:

- **30-day sweep**: `supabase/migrations/20260718000000_add_report_retention_purge.sql`
  registers a daily `pg_cron` job (`purge_generation_job_report`) that nulls
  `generation_job.report` for jobs in a terminal status (`passed`, `needs_review`,
  `failed`) whose `updated_at` is more than 30 days old. `queued`, `running`, and
  `awaiting_manual_fill` are excluded as non-terminal. The migration guards
  `CREATE EXTENSION pg_cron` in an exception-catching block (`RAISE NOTICE` on
  failure) and unschedules-then-reschedules by job name, so it never hard-fails on a
  Postgres without `pg_cron` and is safe to re-apply. An index on
  `(status, updated_at)` backs the purge predicate per this ADR's Implementation
  Notes.
- **On-publish purge**: `publishing/service.py::approve` (the sole path that sets
  `storybook.status = "published"`) nulls the matching `generation_job.report` (by
  `storybook_id` and `version`) in the same transaction as the publish write, so a
  rollback of the publish also rolls back the purge.
  **Removed 2026-08-11**: this leg no longer exists; it defeated the approve half of the
  2026-08-10 exemption. See the 2026-08-11 amendment at the top.

## Amendment (2026-07-16): access-control ruling and code reconciliation

The 2026-07-16 traceability review found the code had drifted from this ADR:
`GET /generation-jobs/{id}` returned the full `report` to any guardian in the owning
family, and the privacy model had been updated to document that reality rather than this
ADR's admin-only rule. The owner ruled the same day: **the admin reviews generated output
first, then it reaches the parent**, with a dual-role adult covered by the admin
capability. The parent may ultimately receive unedited LLM output when the admin approves
without changes; that is accepted, because by then it has passed the automated gates and
admin review. Consequences:

- The single-job endpoint is tightened so `report` is returned only to principals with
  the admin capability; guardians keep status, stage log, and error information.
  Implemented on branch `claude/app-capabilities-review-wm6gt3`.
- Guardians see generated content through the normal post-approval surfaces, never
  through raw job output.
- The privacy model's guardian-visibility wording is corrected back to admin-only.
- The 30-day/on-publish purge below remains decided and remains unbuilt (Phase 5); raw
  output currently persists until that job ships, which is tracked as a known gap.

## TL;DR

Purge `GenerationJob.report` (raw staged LLM outputs) 30 days after job
completion, **except** for a job whose storybook reached a human
review decision (approve or send-back), which the 2026-08-10 amendment above
exempts. Access to `report` is restricted to admin/system
role only. Implementation shipped as a daily `pg_cron` job
(`purge_generation_job_report`, migration `20260718000000_add_report_retention_purge.sql`),
not as the Phase 5 RQ worker this ADR originally proposed; see the 2026-07-17
amendment above. The original policy also purged immediately on publish, whichever came
first; the 2026-08-11 amendment removed that leg, because it fired before the approve
exemption could ever apply.

## Context

### Problem

`GenerationJob.report` stores the full `GenerationOutcome` JSON, which includes
the raw text output from each stage of the generation pipeline (Structure, Prose,
Repair passes). These raw outputs may contain:

- Prompt reflections or elaborations of the concept brief.
- Intermediate story drafts that were rejected by the validator.
- Stage-specific LLM reasoning that is not part of the published story.

The privacy model in `docs/planning/tech-spec.md` specifies that raw outputs
should be "short-lived and admin-only." Currently, `report` is retained
indefinitely with no access control at the API level.

### Why This Matters

This is a kids' app. Even though the concept brief itself is guardian-authored
and fictional (protagonist names are not real child names, per `generation/pii.py`),
raw multi-stage LLM outputs are a novel data category with unclear long-term
privacy implications. Minimizing retention reduces risk.

## Decision

**Retention window**: 30 calendar days from `GenerationJob.updated_at` (the
timestamp of the final status transition), OR when the linked
`StorybookVersion.status` reaches `published`, whichever comes first.

> **Amended 2026-08-10**: the 30-day leg no longer applies to a job whose
> storybook reached a human review decision, in either direction. The
> Amendment at the top of this ADR carries the exact predicate, what it
> deliberately excludes, and why.
>
> **Amended 2026-08-11**: the `OR ... published` leg of the retention window above is
> withdrawn. Publishing no longer purges anything; the 30-day sweep with its
> human-decision exemption is the whole policy.

**Mechanism**: A periodic RQ job (Phase 5) queries for jobs where:

```sql
(updated_at < NOW() - INTERVAL '30 days' OR linked_version.status = 'published')
AND report IS NOT NULL
```

and sets `report = NULL` on matching rows. The job runs daily. It does not
delete the `GenerationJob` row; only the `report` column is nulled. The
predicate above is the original decision as taken; the shipped job additionally
excludes human-decided storybooks per the 2026-08-10 amendment, and its
`linked_version.status = 'published'` disjunct is withdrawn per the 2026-08-11
amendment (published is now an exemption from the purge, not a trigger for it).

**Access control**: `report` must not be exposed via guardian or child API
endpoints. Only internal admin/system paths (e.g. a future ops dashboard or
support tooling) may read `report`. Guardian-facing status polling
(`GET /generation-jobs/{id}`) returns `status`, `stage_log`, and error
information only.

**Audit log**: When a purge job nulls a `report`, it logs the job ID and
purge reason (`expired` or `published`) at INFO level with a structured key.
Only `expired` remains reachable after the 2026-08-11 amendment.

## Consequences

**Positive**:

- Minimal raw LLM output retained: aligns with privacy model.
- Reduces storage footprint for high-volume generation.
- Limits exposure if the database is compromised.

**Negative**:

- Debugging a generation failure after 30 days is harder; `stage_log` and
  `error` columns remain, but the raw LLM output is gone.
- Requires a scheduled worker (Phase 5); the mechanism does not exist yet.
  **Superseded 2026-07-17**: it does exist, as a daily `pg_cron` job rather than
  an RQ worker, so this consequence no longer holds as written.

## Implementation Notes

Phase 5 task: add `generation_job_purge` to the RQ scheduler with a 24-hour
interval. The purge query must use an index on `(updated_at, status)` to avoid
full-table scans on large deployments.

> **Superseded 2026-07-17**: shipped instead as the daily `pg_cron` job
> `purge_generation_job_report`, so no RQ scheduler entry exists or is wanted.
> The index shipped as `(status, updated_at)`, the reverse of the order written
> above, which is the correct order for this predicate: `status` is matched by
> equality against a terminal-status set and `updated_at` by range, and a
> composite index is only usable for a range scan when the equality column comes
> first. Read the column order above as an error in the original note, not as a
> divergence in the migration.

Interim (Phases 3-4): add the `#CRITICAL` privacy comment on the `report`
column in `db/models.py` (done in this cleanup) and ensure no guardian/child
endpoint returns `report` content.

## Alternatives Considered

- **Never retain raw output**: Simpler, but loses debugging capability entirely.
  Stage logs and validator reports are insufficient for diagnosing subtle LLM
  coherence failures.
- **Shorter window (7 days)**: More aggressive but makes debugging a generation
  failure over a weekend harder. 30 days is a reasonable balance.
- **Encrypt `report` at rest**: Adds operational complexity (key rotation) for
  marginal gain given the data is already inside the encrypted database volume.
  Not adopted for Phase 5; revisit if regulatory requirements emerge.
