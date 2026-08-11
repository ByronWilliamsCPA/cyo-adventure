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
| OpenRouter (+ downstream model providers it routes to) | Story-generation prompts (PII-guarded) | [openrouter.ai/docs/guides/features/zdr](https://openrouter.ai/docs/guides/features/zdr) for the Zero Data Retention feature itself; DPA/enterprise terms via [openrouter.ai/enterprise](https://openrouter.ai/enterprise) | ZDR is enforced by a guardrail on a dedicated, key-scoped workspace (see Status). Since 2026-07-28 this backs ADR-003's production-routing control rather than a dispatch blocker, which makes keeping it verified more important, not less: it is now the control, not a second layer under a vendor rule | **Routing controls CONFIGURED 2026-07-28; DPA still NOT EXECUTED.** A dedicated OpenRouter workspace was created for this project with its own API key, and a guardrail set to require ZDR endpoints across non-frontier, Anthropic, OpenAI, Google, and xAI routing, plus all three data-training paths disabled (paid-trains, free-trains, free-publishes-prompts). No individual provider or model is blocked: eligibility is by data policy, by design. The plugins/tools carve-out is closed for this app and verified in code, not assumed: the generation request body has no `plugins` or `tools` key (`generation/providers/openrouter.py:154-164`). **Still open**: (a) execute the DPA / enterprise terms, which a routing guardrail does not substitute for; (b) re-confirm guardrail state at P7-08 and on any credential rotation, since console settings are mutable. |
| AWS Bedrock (OpenRouter sub-processor) | Story-generation prompts (PII-guarded), for Anthropic-family traffic OpenRouter routes here since the 2026-07-28 ZDR toggles disabled first-party Anthropic endpoints | No direct link: coverage would flow through OpenRouter's own sub-processor terms, not a DPA CYO Adventure signs | **Sub-processor, not a direct counterparty.** There is no contractual relationship to execute here; the mechanism is whatever OpenRouter's DPA/enterprise terms commit for its sub-processors, which is part of what the OpenRouter row above has to establish | Not applicable as a direct DPA. **Open**: confirm, as part of the OpenRouter conversation, that its terms name and bind its sub-processors, and that ZDR routing actually holds at this endpoint |
| Microsoft Azure (OpenRouter sub-processor) | Story-generation prompts (PII-guarded), for OpenAI-family traffic OpenRouter routes here since the 2026-07-28 ZDR toggles disabled first-party OpenAI endpoints | As above: via OpenRouter's sub-processor terms | **Sub-processor, not a direct counterparty**; same mechanism as the Bedrock row | Not applicable as a direct DPA; same open item as the Bedrock row |
| Google Vertex (OpenRouter sub-processor) | Story-generation prompts (PII-guarded), for Google-family traffic OpenRouter routes here since the 2026-07-28 ZDR toggle disabled AI Studio endpoints | As above: via OpenRouter's sub-processor terms | **Sub-processor, not a direct counterparty**; same mechanism as the Bedrock row. Distinct from the Google Perspective / Gemini row below, which is a direct integration | Not applicable as a direct DPA; same open item as the Bedrock row |
| Anthropic (direct) | Story-generation prompts (PII-guarded), same guard as above | [privacy.claude.com/en/articles/7996862](https://privacy.claude.com/en/articles/7996862-how-do-i-view-and-sign-your-data-processing-addendum-dpa) | DPA is incorporated into Anthropic's **Commercial** Terms of Service automatically once accepted; confirm this account is actually on commercial terms, not the free/consumer terms, since the DPA does not apply to `claude.ai` free accounts | Not yet confirmed which terms tier this account is under; execute after confirming. **Row stays as of 2026-07-28, and is not superseded by the OpenRouter ZDR toggles.** Those toggles remove first-party Anthropic endpoints from the *OpenRouter* route only. The direct leg is a separate, built path: `AnthropicProvider` (`generation/providers/anthropic.py`) is dispatched whenever `generation_provider="anthropic"` (`generation/provider.py:659-660`), the admin allowlist seeds two direct-Anthropic models (`generation/allowlist.py`), and `records-of-processing-activities.md` lists "Anthropic (direct)" as a live recipient of request text. That leg inherits none of the OpenRouter guardrail, so this row is more load-bearing than before, not less |
| OpenAI Moderation | Generated story prose, child-typed request text (Stage-0 classifier) | [openai.com/policies/data-processing-addendum](https://openai.com/policies/data-processing-addendum/) | 30-day API data retention by default, per OpenAI's own DPA terms; supports GDPR/CCPA | Not yet executed |
| Google Perspective / Google Gemini (cover art) | Generated prose + child-typed text (Perspective); cover-art prompts (Gemini) | [cloud.google.com/terms/data-processing-addendum](https://cloud.google.com/terms/data-processing-addendum) (the Cloud DPA); confirm Perspective API specifically is in scope of this DPA or needs its own terms acceptance — the search that produced this checklist could not confirm Perspective's coverage directly, flagged below | **Verify Perspective API is actually covered** by the Cloud DPA (not confirmed by this checklist's research; may need a direct check of the Perspective API terms of service) before treating this row as closed by the Cloud DPA alone | Not yet executed; Perspective coverage unconfirmed |
| Cloudflare (R2) | Cover images (private bucket, presigned-URL access only) | [cloudflare.com/cloudflare-customer-dpa](https://www.cloudflare.com/cloudflare-customer-dpa/); SCCs at [cloudflare.com/cloudflare-customer-scc](https://www.cloudflare.com/cloudflare-customer-scc/) | DPA forms part of the main agreement on acceptance; also DPF-certified per Cloudflare's own trust-hub material | Not yet executed |
| Epic Games (Kids Web Services) | **A guardian's email address**, the country they selected, a language tag, and an opaque reference number. No child data of any kind | Vendor terms reachable from the KWS Control Panel; no DPA has been requested or reviewed as of 2026-08-10 | **Not determined, and the counterparty entity is itself unresolved**: Epic operates KWS from both US and EU entities, and which one receives our traffic has not been established, so no transfer mechanism can be named yet | **Not executed, and this row is the only one where that blocks a switch-on rather than trailing a live integration.** Added 2026-08-10 when the KWS adult-check gate was built (staging only, against the vendor's Test environment; production flag off). Three properties make it unlike every other row: the address is sent when the check *starts*, so refused and abandoned applicants are disclosed too; it is therefore the only processor here that receives data about people who never become users; and unlike the rows above, nothing is live in production yet, so the gap is closable before any real family's data moves rather than after. Tracked at assurance-register row **O-125** and DPIA section 2.8 |
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
- **Added 2026-07-28**: the AWS Bedrock, Microsoft Azure, and Google Vertex rows are
  sub-processor entries, present so the record follows the routing change ADR-003's 2026-07-28
  amendment describes. They are not rows to execute; they are rows the OpenRouter conversation
  has to cover.
- **Known gap, 2026-07-28**: **Modal** is absent from this checklist despite being a hosted
  third-party platform (ADR-010: "Modal is a second serverless vendor") with a built generation
  adapter and configured endpoint settings (`core/config.py:529-554`). It is also absent from
  ADR-018 item 6 and `docs/planning/privacy-model.md`. Add a row before the Modal leg is enabled
  on any deployed tier; the omission is not an exemption.

## Relationship to other compliance documents

| Document | Relationship |
|---|---|
| `coppa-gdpr-remediation-plan.md` | Phase 5, whose execution-tracking checklist this document is. |
| `docs/planning/privacy-model.md` | The durable processor-list record Phase 5c asks outcomes to be recorded in, once each row above is executed. |
| `records-of-processing-activities.md` | Section 4/5's recipient and transfer-mechanism tables, which should be updated to reflect "executed" status once this checklist closes each row. |
| `information-security-program.md` | Section 4's vendor-oversight table and process, which this checklist is the first pass at executing. |
