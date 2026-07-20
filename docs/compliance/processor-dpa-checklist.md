---
title: "Phase 5 Processor DPA Checklist"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Working checklist for executing Data Processing Agreements with each processor CYO Adventure uses, tracked per coppa-gdpr-remediation-plan.md Section 6."
tags:
  - compliance
  - privacy
  - legal
component: Development-Tools
source: "Working checklist tracked in coppa-gdpr-remediation-plan.md Section 6; execution decided 2026-07-20."
---

Status: working checklist, not a compliance record. Owner: Byron Williams (execution decided
2026-07-20: the account owner works through this directly, per
`coppa-gdpr-remediation-plan.md` Section 6). Once a row is executed, record the outcome in
`docs/planning/privacy-model.md`'s processor list (Phase 5c) and
`records-of-processing-activities.md` Section 4/5, not just here — this file is the to-do
list, not the durable record.

Every processor below is US-hosted (`gdpr-compliance-review.md`'s "all current users are US"
finding), so a DPA alone is not the full transfer-mechanism story if any EEA/UK user is ever
in scope (currently: none, per the 2026-07-20 decision recorded in the remediation plan) —
each row also needs Standard Contractual Clauses or Data Privacy Framework self-certification
confirmed before that changes, not necessarily before this checklist is worked through.

## How to work this checklist

For each row: open the DPA link, confirm the current version, execute it (most of these are
self-serve click-through or dashboard-signed, not something requiring a sales call), and note
the execution date and any deviation from the standard terms. OpenRouter is the one row that
needs an actual conversation, not just a click-through (see its row).

## Checklist

| Processor | What they receive | DPA / terms link | Standard mechanism | Status |
|---|---|---|---|---|
| Supabase | Full application database (Postgres, auth) | [supabase.com/legal/dpa](https://supabase.com/legal/dpa) (request the signable PandaDoc version from the dashboard's legal-documents page; [trust.supabase.io/documents](https://trust.supabase.io/documents) has supporting trust-center material) | DPA incorporates SCCs + the UK ICO addendum | Not yet executed |
| OpenRouter (+ downstream model providers it routes to) | Story-generation prompts (PII-guarded) | [openrouter.ai/docs/guides/features/zdr](https://openrouter.ai/docs/guides/features/zdr) for the Zero Data Retention feature itself; DPA/enterprise terms via [openrouter.ai/enterprise](https://openrouter.ai/enterprise) | ZDR can be enforced account-wide via privacy settings (not just per-request) — confirm this is actually turned ON, not merely available, since ADR-018 already flags this as the standing blocker | **Needs a real conversation, not just a click-through.** Confirm (a) account-wide ZDR is enabled, and (b) it covers every downstream model/provider OpenRouter routes this app's traffic to, not just OpenRouter's own layer — the ZDR docs note plugins/tools you enable may have their own retention policies, so confirm this app enables none of those. Not yet executed. |
| Anthropic (direct) | Story-generation prompts (PII-guarded), same guard as above | [privacy.claude.com/en/articles/7996862](https://privacy.claude.com/en/articles/7996862-how-do-i-view-and-sign-your-data-processing-addendum-dpa) | DPA is incorporated into Anthropic's **Commercial** Terms of Service automatically once accepted — confirm this account is actually on commercial terms, not the free/consumer terms, since the DPA does not apply to `claude.ai` free accounts | Not yet confirmed which terms tier this account is under; execute after confirming |
| OpenAI Moderation | Generated story prose, child-typed request text (Stage-0 classifier) | [openai.com/policies/data-processing-addendum](https://openai.com/policies/data-processing-addendum/) | 30-day API data retention by default, per OpenAI's own DPA terms; supports GDPR/CCPA | Not yet executed |
| Google Perspective / Google Gemini (cover art) | Generated prose + child-typed text (Perspective); cover-art prompts (Gemini) | [cloud.google.com/terms/data-processing-addendum](https://cloud.google.com/terms/data-processing-addendum) (the Cloud DPA); confirm Perspective API specifically is in scope of this DPA or needs its own terms acceptance — the search that produced this checklist could not confirm Perspective's coverage directly, flagged below | **Verify Perspective API is actually covered** by the Cloud DPA (not confirmed by this checklist's research; may need a direct check of the Perspective API terms of service) before treating this row as closed by the Cloud DPA alone | Not yet executed; Perspective coverage unconfirmed |
| Cloudflare (R2) | Cover images (private bucket, presigned-URL access only) | [cloudflare.com/cloudflare-customer-dpa](https://www.cloudflare.com/cloudflare-customer-dpa/); SCCs at [cloudflare.com/cloudflare-customer-scc](https://www.cloudflare.com/cloudflare-customer-scc/) | DPA forms part of the main agreement on acceptance; also DPF-certified per Cloudflare's own trust-hub material | Not yet executed |
| Sentry | Error telemetry; hardcoded to exclude child-linked PII by design | [sentry.io/legal/dpa](https://sentry.io/legal/dpa/) (current version 5.1.0, 2024-05-29 — confirm no newer version before signing) | Signable via DocuSign from the Legal & Compliance section of the Sentry org dashboard (Owner/Billing role required) | Close to a formality given the no-PII-by-design finding (`gdpr-compliance-review.md`), but "compliant from the start" means closing it rather than assuming it's unnecessary; not yet executed |

## Notes

- Every link above was verified live (web search, 2026-07-20) rather than reused from
  training-data memory or guessed, since a stale/wrong legal-document link in a compliance
  record is worse than no link. Re-verify before relying on this checklist if it is used long
  after this date — legal-document URLs and version numbers do change.
- None of these require a paid enterprise tier to access a DPA, based on this checklist's
  research, except possibly Anthropic (flagged above) — confirm account tier before assuming a
  self-serve DPA is available if a vendor's page suggests otherwise.
- This checklist does not cover SCC/DPF execution specifically (only DPA execution); revisit
  that separately if/when the UK/EEA-user status decision (`coppa-gdpr-remediation-plan.md`
  Section 2) changes from "none."

## Relationship to other compliance documents

| Document | Relationship |
|---|---|
| `coppa-gdpr-remediation-plan.md` | Phase 5, whose execution-tracking checklist this document is. |
| `docs/planning/privacy-model.md` | The durable processor-list record Phase 5c asks outcomes to be recorded in, once each row above is executed. |
| `records-of-processing-activities.md` | Section 4/5's recipient and transfer-mechanism tables, which should be updated to reflect "executed" status once this checklist closes each row. |
| `information-security-program.md` | Section 4's vendor-oversight table and process, which this checklist is the first pass at executing. |
