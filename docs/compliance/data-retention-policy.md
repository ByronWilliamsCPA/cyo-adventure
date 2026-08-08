---
title: "Data Retention Policy"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Published written data-retention policy naming the business need and hard deletion timeline for each class of children's and adult personal information, as mandated by the amended COPPA Rule and required by ADR-018 decision D4."
tags:
  - compliance
  - privacy
component: Development-Tools
source: "Consolidates the per-category retention schedule resolved 2026-07-20 in coppa-gdpr-remediation-plan.md Section 5 (which governs, and is reproduced here rather than re-derived) with the guardian-facing table in privacy-notice.md and the per-activity view in records-of-processing-activities.md, and adopts the additional categories docs/planning/unscheduled-work-register.md row UW-N07 names. Created 2026-08-06 for ADR-018 decision D4."
---

Status: living document. Owner: Byron Williams (byronawilliams@gmail.com). Drafted: 2026-08-06.
Pending counsel review as an ADR-018 D4 artifact (see `counsel-engagement-brief.md` Section 3).

This document is a compliance artifact, not legal advice. It states company policy and its
current implementation status; it does not represent a legal conclusion that the policy or its
implementation satisfies any specific statute, and every claim below should be read subject to
the verification caveats in Section 4.

## 1. Purpose and scope

This is the published, written data-retention policy required by two overlapping obligations:

- **COPPA 16 CFR 312.10**, as amended by the FTC's 2025 amendments (general compliance date
  2026-04-22): an operator must not retain a child's personal information for longer than
  reasonably necessary to fulfill the purpose for which it was collected, and must delete it
  using reasonable measures once that purpose has been fulfilled. The amended Rule's written-policy
  mandate requires this to be stated, for each class of children's personal information, as a
  named business need for retention paired with a hard deletion timeline, rather than left
  implicit. [COUNSEL: `counsel-engagement-brief.md` Section 4 asks counsel to independently
  confirm this mandate is a rule requirement and not merely FTC best-practice guidance; treat
  that confirmation as still outstanding.]
- **GDPR Article 5(1)(e)** (storage limitation): personal data must be kept in a form that
  permits identification of the data subject for no longer than necessary for the purposes for
  which it is processed. This is the parallel EU/UK obligation covering the same data where a
  guardian's residence brings GDPR into scope.

**Scope**: every system that stores personal data about a guardian, a child profile, or an
adult account, as inventoried in `records-of-processing-activities.md` Section 3. This includes
the FastAPI backend's PostgreSQL database (Supabase-managed), the append-only `pipeline_event`
and `security_event` audit tables, application container logs, and the encrypted database
backups described in `docs/operations/runbook.md` Section 6. It does not cover a third-party
processor's own internal retention (for example Sentry's platform-level log retention); that is
tracked as a vendor-oversight item in `information-security-program.md` Section 4, not restated
here.

## 2. The retention schedule

**This table governs.** The first eight rows reproduce, without modification, the
category-by-category schedule resolved 2026-07-20 in `coppa-gdpr-remediation-plan.md` Section 5
("Resolved 2026-07-20: accepted as drafted"). The remaining rows adopt the additional categories
that `docs/planning/unscheduled-work-register.md` row UW-N07 identifies as omitted from that
resolved schedule.

| Data class | What it is | Retention window | Business need justifying retention | Deletion mechanism / status |
|---|---|---|---|---|
| Active profile/reading data | `reading_state`, `completion`, and `rating` rows for a child profile | Life of the active profile, plus 30-90 days after deactivation before purge | Grace period covers accidental deactivation/reactivation without permanent data loss | Enforced. Three `pg_cron` jobs (`purge_stale_deactivated_profile_activity`, `_completions`, `_ratings`, migration `supabase/migrations/20260720150000_add_retention_purge_jobs.sql`) delete rows for any profile deactivated more than 90 days ago. |
| Approved/published story requests and their stories | The `story_request` row and its resulting `storybook`/`storybook_version` rows, once approved and published | Life of the active account | Matches the product's core value; this is delivered content the guardian and child use, not incidental collection | On-demand only. Cascades away via `DELETE /api/v1/profiles/{profile_id}` or `DELETE /api/v1/me/family` (`src/cyo_adventure/api/me.py::delete_my_family`); no scheduled purge job exists because deletion is guardian-triggered, not time-triggered. |
| Blocked or declined story requests (raw `request_text`) | The `story_request.request_text` column on rows with `status IN ('blocked', 'declined')` | 30 days from decision (`COALESCE(reviewed_at, created_at)`), then the raw text is overwritten and only the redacted category/verdict remains | Short window covers guardian review/appeal; raw declined text has no ongoing purpose after that | Enforced. `pg_cron` job `purge_blocked_declined_story_request_text` (migration `20260720150000_add_retention_purge_jobs.sql`), daily at 03:00, overwrites `request_text` with a fixed placeholder. |
| `generation_job.report` (raw LLM output) | The raw model output column on a generation job | 30 days, or immediately on publish, whichever comes first | ADR-007's original design; the raw output has no purpose once its content is either published or discarded | Enforced. `pg_cron` job scheduled in `supabase/migrations/20260718000000_add_report_retention_purge.sql`. |
| Moderation reports | Classifier verdicts, scores, and reviewer decisions recorded during safety review | 1-2 years | Balances safety/audit value (a pattern of prior flags on a request source) against indefinite retention | **Policy-only, not enforced.** No `pg_cron` job, scheduled task, or application code was found that purges moderation-report rows on any schedule (verified by grepping `supabase/migrations/` and `src/cyo_adventure/` for `purge`/`retention`/`pg_cron`, 2026-08-06). See Section 4. |
| `pipeline_event` audit log | The append-only accountability log written by `events/writer.py::record_event` (`db/models.py::PipelineEvent`) | No fixed purge; retained under a documented Article 17(3)/312.10 safety-and-integrity justification | Already PII-scrubbed by a closed-vocabulary allowlist contract (never free text, per `events/writer.py`), so the retention-risk profile is much lower than raw free text; the full balancing test is in `coppa-gdpr-remediation-plan.md`'s "4d artifact" section and `dpia.md` Section 2.5 | By design. No deletion path exists, and none is intended; this row survives a profile/family erasure request as a documented exception (see Section 3). |
| Erasure request: response to the guardian | The obligation to communicate what action was taken on an erasure request | Acknowledge and respond within 1 month of the request (GDPR Article 12(3)); may be extended by up to 2 further months for complex/numerous requests, but only if the guardian is notified of the extension and the reason within the initial 1-month window | This is the deadline to communicate *what action was taken*, a distinct obligation from the deletion itself | Process obligation; see Section 3. No automated tracking of this clock was found in the codebase (manual/support-channel process today). |
| Erasure request: actual purge | The obligation to actually delete the data an erasure request targets | Purge within 30 days of the request, well inside the Article 12(3) response window above | Article 17's "without undue delay" duty; the two deadlines (respond vs. purge) are tracked separately so a fast purge doesn't imply a fast response is optional, and vice versa | Enforced for the on-demand deletion paths (`DELETE /api/v1/profiles/{profile_id}`, `DELETE /api/v1/me/family`), both of which delete synchronously on request rather than on a 30-day timer, so they clear this window with margin. See Section 3. |
| Adult account/household | The `user` row and its account-level fields (email, auth identity, role, `residence_country`, `adulthood_attested_at`) | Life of the active account | Contract: operating the guardian's account and determining which regulatory regime applies (`records-of-processing-activities.md` row 1) | Enforced. Cascades away via `DELETE /api/v1/me/family` (`src/cyo_adventure/api/me.py`); every `user` row in the family, including the caller's own, is deleted at the database level. |
| Consent evidence | The guardian's typed legal name, consent date, policy version, and IP address at consent time (`User.consent_accepted_at`/`consent_policy_version`/`consent_signer_name`/`consent_ip`), and the parallel personalization-consent and cross-family-connection-consent columns | **Not yet set, owner ruling required** | Proving verifiable parental consent was obtained is itself a COPPA/GDPR Article 8 accountability requirement, in tension with the guardian's own erasure right over the same fields | **Gap.** `DELETE /api/v1/me/family` deletes the `user` row outright, so consent evidence does not survive account deletion today; there is no separate evidentiary-retention path analogous to `pipeline_event`'s Article 17(3) exception. See Section 5. |
| Product analytics | Day-grain active-reading-time rows (`reading_activity_day`: `child_profile_id`, `activity_date`, `active_seconds`) | **Not yet set, owner ruling required.** A 12-month retention default has been proposed internally (migration `supabase/migrations/20260801040000_add_reading_activity_day.sql`'s header comment, citing the kid-appeal implementation plan's "Plan defaults" item 2) but has not been ruled on as accepted compliance policy the way the Section 2 rows above were on 2026-07-20 | Supports the reading-streak/badge feature (W3.3-W3.5); detail is proposed to roll into a running total after the window, with lifetime days-read surviving | **Gap.** The table and its cascade/RLS exist; the migration's own comment states the rollover/purge job is "explicitly OUT OF SCOPE for this migration." No purge job exists. See Section 4 and Section 5. |
| Application logs | Structured JSON log lines (stdout, `JSON_LOGS=true`), including security events (`client_ip`, `path`) per `docs/operations/security-events.md` | **Not yet set, owner ruling required.** Currently size-bounded, not time-bounded | Operational debugging and the real-time/alerting surface for security events | **Gap.** `docker-compose.prod.yml` sets a size-based cap (`max-size: 50m`, `max-file: 5`) on the `app`/`worker` services, but `docs/operations/security-events.md` Section 4 states plainly that this gives no time-based deletion guarantee, and that the live production host (`homelab-infra`) has not been confirmed to have an equivalent bound at all. See Section 4. |
| Financial records | Payment or billing records | Not applicable today; no financial or payment data is collected. The product is pre-monetization at family-tier scale (`docs/planning/unscheduled-work-register.md` row UW-N10) | None yet; no data exists to retain | No mechanism needed today. A window must be ruled on by the owner and finance before any payment feature (for example the nominal card-verification step floated in `coppa-gdpr-remediation-plan.md`'s VPC options) ships. See Section 5. |
| Backups | Encrypted, tiered database dumps (`scripts/backup_database.py`, `.github/workflows/supabase-backup.yml`) | Daily tier: 7 days (floor 3). Weekly tier: 28 days. Monthly tier: 180 days (floor 90). These are the script's documented GFS lifecycle defaults | Disaster recovery and a tested restore path (`docs/operations/runbook.md` Section 6, `docs/planning/unscheduled-work-register.md` row UW-D27) | Enforced via R2 bucket lifecycle rules that the script both writes and verifies (`ensure_lifecycle_rules`, `verify_backup_bucket`). A backup inherits the same personal data as the live database it was taken from, so a guardian's erasure request is not reflected in an already-taken backup until that backup ages out under this schedule; this consequence has not been separately ruled on. See Section 5. |

**Note on the reading-progress row.** `docs/planning/unscheduled-work-register.md` row UW-N07
records that an external planning document proposed a different default for reading progress:
"target 12 months' inactivity," against the resolved policy's "life of the active profile plus
30-90 days after deactivation." **The resolved policy governs until deliberately changed.** The
row above states the resolved window, not the external default; nothing in this document should
be read as adopting the 12-month figure for reading progress.

## 3. Deletion on request

An erasure request carries two separate clocks, tracked independently so that meeting one does
not imply the other is optional:

- **The response clock (GDPR Article 12(3)).** The company must acknowledge the request and
  communicate what action was taken within 1 month. This deadline may be extended by up to 2
  further months for complex or numerous requests, but only if the guardian is notified of the
  extension and the reason for it within the initial 1-month window. Missing this clock is a
  failure to communicate, independent of whether the underlying deletion happened.
- **The purge clock (Article 17's "without undue delay" duty).** The data itself must be purged
  within 30 days of the request, a window that sits entirely inside the response clock above.

In practice, the company's two guardian-facing deletion routes, `DELETE /api/v1/profiles/{profile_id}`
(single child profile) and `DELETE /api/v1/me/family` (entire family account), execute the
underlying deletion synchronously at request time rather than on a scheduled timer, so both
routes clear the 30-day purge clock with substantial margin whenever they are the mechanism used.
The response clock is a communication obligation layered on top of that technical deletion and,
per Section 2's table, has no automated tracking today; it depends on a manual or support-channel
process, which is not itself a database-purge concern but is noted here because the resolved
schedule tracks it as part of the same policy.

The one documented exception to "the data itself is purged" is the `pipeline_event` audit log
(Section 2), which survives an erasure request under a stated Article 17(3) balancing
justification rather than by an oversight.

## 4. Known gaps between policy and implementation

This section states plainly which windows in Section 2 are enforced by shipped code today, and
which are policy-only. Every claim below was verified by grepping `supabase/migrations/` and
`src/cyo_adventure/` for `pg_cron`, `purge`, and `retention` on 2026-08-06, and by reading the
specific files cited.

**Enforced by shipped code:**

- Active profile/reading data purge: three `pg_cron` jobs in
  `supabase/migrations/20260720150000_add_retention_purge_jobs.sql`.
- Blocked/declined `request_text` purge: `pg_cron` job in the same migration.
- `generation_job.report` purge: `pg_cron` job in
  `supabase/migrations/20260718000000_add_report_retention_purge.sql`.
- `story_request.interpretation` element purge:
  `supabase/migrations/20260720000000_add_story_request_interpretation.sql` (an additional
  purge job not itemized as its own row in Section 2's table because it is a sub-field of the
  blocked/declined story-request category already covered there).
- On-demand account/profile deletion: `DELETE /api/v1/profiles/{profile_id}` and
  `DELETE /api/v1/me/family` in `src/cyo_adventure/api/me.py`, both executing synchronously.
- Backup lifecycle: R2 bucket lifecycle rules written and verified by
  `scripts/backup_database.py`.

**Policy-only, with no purge job:**

- **Moderation reports** (1-2 years). No `pg_cron` job, RQ scheduled task, or application-code
  purge path exists for moderation-report rows. `docs/compliance/coppa-gdpr-remediation-plan.md`
  Phase 4b (this document) is listed as "unblocked, not yet published" for the policy itself;
  the corresponding purge job was never listed as a Phase 4c deliverable and does not exist.
- **`reading_activity_day` product analytics** (proposed 12 months). The table, RLS, and cascade
  exist as of `supabase/migrations/20260801040000_add_reading_activity_day.sql`; that migration's
  own header comment states the rollover/purge job is "explicitly OUT OF SCOPE for this
  migration." No purge job exists.
- **Application logs.** Container-level logs are size-bounded (`docker-compose.prod.yml`,
  `max-size: 50m` / `max-file: 5`) but not time-bounded, and `docs/operations/security-events.md`
  Section 4 states the production deployment orchestrator (`homelab-infra`) has not been
  confirmed to carry an equivalent bound at all. A size cap is not a deletion timeline: a
  low-volume log stream could retain lines well past any window this policy states.

**`security_event` table: verified, no retention or purge mechanism.** `docs/planning/`
`unscheduled-work-register.md` row UW-D28 asserts the `security_event` table has no retention or
purge mechanism; this was independently verified rather than repeated on trust.
`supabase/migrations/20260804070000_add_security_event_table.sql` implements the table with an
append-only trigger (`security_event_append_only`) that blocks `UPDATE` and `DELETE` outright, and
its own header comment states: "these rows have NO deletion path at all today: ADR-018 requires a
hard deletion timeline per data class, and this table does not yet have one." That comment is
marked `#CRITICAL`, paired with a `#VERIFY` instruction that this is "tracked as a follow-up; do
not treat this table as satisfying ADR-018 on its own." The table carries `client_ip` (personal
data) and `path` (which can embed a profile identifier), so this gap is a genuine ADR-018
shortfall, not a hypothetical one, and it is not yet resolved anywhere in this repository.

## 5. Open items requiring an owner or counsel ruling

- **Consent evidence retention.** `DELETE /api/v1/me/family` deletes the `user` row outright,
  including every consent-related column. No policy states whether consent evidence should
  survive account deletion for accountability purposes (the way `pipeline_event` does under its
  Article 17(3) exception), or whether full deletion including consent evidence is the intended
  behavior. Owner and counsel ruling needed; `docs/planning/unscheduled-work-register.md` row
  UW-N07 names privacy counsel as an owner for this category.
- **Product analytics (`reading_activity_day`) retention window.** A 12-month default has been
  proposed internally but not ruled on as accepted policy. Ruling needed before a purge job is
  built, per UW-N07 (privacy counsel and finance named as owners).
- **Application log retention window.** No hard deletion timeline has been proposed for
  container-level application logs, including the security-event log lines described in
  `docs/operations/security-events.md`. A window needs to be set, and the production
  `homelab-infra` log-driver configuration needs to be confirmed to actually bound retention
  before this policy can state it is enforced.
- **Financial records retention window.** No financial data is collected today, so no window is
  needed yet, but one must be ruled on before any payment or billing feature ships (finance and
  privacy counsel, per UW-N07).
- **Backup retention and an in-flight erasure request.** A guardian's erasure request is not
  reflected in an already-taken backup until that backup ages out under the daily/weekly/monthly
  schedule in Section 2. Whether this residual-copy window is acceptable as-is, or needs a
  documented exception analogous to `pipeline_event`'s, has not been separately ruled on.
- **Moderation-report purge job.** The 1-2 year window is accepted policy (resolved 2026-07-20)
  but has no enforcing purge job. This is an engineering gap to schedule, not an open policy
  question, and is listed here so it is not lost between this document and
  `coppa-gdpr-remediation-plan.md` Phase 4c.
- **`security_event` retention.** No window has been proposed at all for this table, and its
  append-only trigger currently forecloses any deletion path. A ruling is needed both on the
  window and on how a purge would coexist with the append-only guarantee (for example, a
  time-boxed archival-then-delete pattern rather than a raw `DELETE`).
- **The five citations `counsel-engagement-brief.md` Section 4 asks counsel to verify against
  the Federal Register** apply to this document by extension, in particular whether the amended
  COPPA Rule actually mandates a published written retention policy (as opposed to recommending
  one as best practice) and whether the 2026-04-22 general compliance date is accurate. This
  document was drafted on the assumption that the mandate is real; if counsel's independent
  verification says otherwise, this document's own justification for existing should be revisited
  accordingly.

## 6. Relationship to other compliance documents

| Document | Relationship |
|---|---|
| [coppa-gdpr-remediation-plan.md](./coppa-gdpr-remediation-plan.md) | Section 5 holds the authoritative, already-resolved per-category schedule this document reproduces in Section 2 without modification; Phase 4b is the plan item this document satisfies, and Phase 4c is the purge-job work this document's Section 4 checks against. |
| [privacy-notice.md](./privacy-notice.md) | The guardian-facing plain-language rendering of the same retention policy ("How long we keep information"); this document is the internal, fuller-detail counterpart and must not contradict that table. |
| [records-of-processing-activities.md](./records-of-processing-activities.md) | Section 3's per-activity "Retention" column is the system-level view this document consolidates alongside the resolved schedule; both must stay consistent with Section 2 above. |
| [information-security-program.md](./information-security-program.md) | The house style this document follows (frontmatter shape, section numbering, closing cross-reference section); also the document that tracks vendor-level retention (for example Sentry's platform retention) that this document deliberately does not restate. |
| [../planning/unscheduled-work-register.md](../planning/unscheduled-work-register.md) (row UW-N07) | The row that defines this document's exact delta from the resolved schedule: which categories to adopt, and how the reading-progress disagreement was resolved. |
| [counsel-engagement-brief.md](./counsel-engagement-brief.md) | Section 3 lists this document as a parallel D4 deliverable for counsel to review and redline, and Section 4 lists the citations whose independent verification this document's Section 1 and Section 5 depend on. |
| [ADR-018](../planning/adr/adr-018-childrens-privacy-compliance.md) | Decision D4 names this document by path as one of the two rule-mandated D4 artifacts (alongside the Information Security Program), and records its creation date. |
