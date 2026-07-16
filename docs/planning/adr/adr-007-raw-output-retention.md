---
title: "ADR-007: Raw LLM output retention policy for GenerationJob.report"
schema_type: planning
status: proposed
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
completion or when the produced storybook version reaches `published` status,
whichever comes first. Access to `report` is restricted to admin/system role
only. Implementation is a Phase 5 scheduled RQ job.

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

**Mechanism**: A periodic RQ job (Phase 5) queries for jobs where:

```sql
(updated_at < NOW() - INTERVAL '30 days' OR linked_version.status = 'published')
AND report IS NOT NULL
```

and sets `report = NULL` on matching rows. The job runs daily. It does not
delete the `GenerationJob` row; only the `report` column is nulled.

**Access control**: `report` must not be exposed via guardian or child API
endpoints. Only internal admin/system paths (e.g. a future ops dashboard or
support tooling) may read `report`. Guardian-facing status polling
(`GET /generation-jobs/{id}`) returns `status`, `stage_log`, and error
information only.

**Audit log**: When a purge job nulls a `report`, it logs the job ID and
purge reason (`expired` or `published`) at INFO level with a structured key.

## Consequences

**Positive**:
- Minimal raw LLM output retained: aligns with privacy model.
- Reduces storage footprint for high-volume generation.
- Limits exposure if the database is compromised.

**Negative**:
- Debugging a generation failure after 30 days is harder; `stage_log` and
  `error` columns remain, but the raw LLM output is gone.
- Requires a scheduled worker (Phase 5); the mechanism does not exist yet.

## Implementation Notes

Phase 5 task: add `generation_job_purge` to the RQ scheduler with a 24-hour
interval. The purge query must use an index on `(updated_at, status)` to avoid
full-table scans on large deployments.

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
