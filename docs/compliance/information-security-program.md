---
title: "Information Security Program"
schema_type: planning
status: published
owner: core-maintainer
purpose: "Internal information-security program artifact required by COPPA 312.8 and GDPR Article 32(1)(d), covering the FastAPI backend, frontend, and supporting infrastructure."
tags:
  - compliance
  - security
component: Development-Tools
source: "Compliance program artifact tracked in coppa-gdpr-remediation-plan.md Phase 6b; last reviewed 2026-07-20."
---

Status: living document. Owner: Byron Williams (byronawilliams@gmail.com). Last reviewed:
2026-07-20.

## 1. Purpose and scope

This document is the internal information-security program artifact required by two
overlapping obligations tracked in `docs/compliance/coppa-gdpr-remediation-plan.md` Phase 6b:

- **COPPA 312.8** (as amended, 2025 effective date): an operator must establish, implement, and
  maintain a written information security program appropriate to the sensitivity of the
  children's personal information collected, including a designated coordinator, regular risk
  assessments, and oversight of any service provider or third party to whom children's
  information is disclosed.
- **GDPR Article 32(1)(d)**: the controller must have "a process for regularly testing, assessing
  and evaluating the effectiveness of technical and organisational measures for ensuring the
  security of the processing."

It covers every system in scope of `SECURITY.md`'s security surface: the FastAPI backend, the
React frontend, Supabase-managed Postgres, Redis/RQ, and every third-party processor listed in
Section 4. It does not restate `SECURITY.md`'s external vulnerability-reporting policy or
`docs/compliance/breach-notification-runbook.md`'s incident procedure; both are referenced, not
duplicated, from Section 3 and Section 5.

## 2. Designated security contact

A single named coordinator satisfies both COPPA 312.8's "designated employee" requirement and
GDPR's accountability expectation that someone owns Article 32 compliance:

| Role | Contact |
|---|---|
| Security coordinator | Byron Williams, byronawilliams@gmail.com |
| External vulnerability reports | [GitHub Security Advisories](https://github.com/ByronWilliamsCPA/cyo-adventure/security/advisories/new) or byronawilliams@gmail.com (see `SECURITY.md`) |
| Breach/incident escalation | Same coordinator; see `docs/compliance/breach-notification-runbook.md` for the escalation procedure and notification clocks |

At the project's current single-maintainer scale, the security coordinator, the data controller
(for GDPR purposes), and the COPPA-designated employee are the same person. If the team grows,
split these roles explicitly here rather than letting the assumption go stale.

## 3. Risk-assessment cadence

| Trigger | Assessment |
|---|---|
| **Annual** (or on the anniversary of the prior assessment) | Full re-run of `docs/compliance/coppa-compliance-audit.md` and `docs/compliance/gdpr-compliance-review.md`'s finding registers against whatever has shipped since (remediation plan Phase 8c); update severities and close resolved findings. |
| **Before any major feature that touches child-linked data** | A scoped review: does the new feature introduce a new processing purpose (needs an Article 6 basis and, if applicable, a Records of Processing Activities update per `docs/compliance/records-of-processing-activities.md`), a new third-party disclosure (needs Section 4's vendor-oversight process below), or a new data category (needs a data-minimization check against the existing `AgeBand`/no-birthdate/no-photo design). |
| **Before onboarding a new processor, or materially changing terms with an existing one** | Section 4's vendor-oversight process, before the integration ships, not after. |
| **On every dependency-scanning finding** (Bandit, OSV-Scanner, pip-audit, CodeQL, Dependabot, SonarCloud; see `SECURITY.md`'s CI/CD list) | Triaged per `SECURITY.md`'s existing severity/response-timeline table; this is the day-to-day mechanism, not a separate annual-only process. |
| **After any security incident** (regardless of whether it met the breach-notification runbook's reportable threshold) | A post-incident review feeding back into this cadence: did the incident reveal a gap this program should have caught earlier? |

Each assessment's outcome (findings, severity changes, remediation status) is recorded by
updating the relevant document in `docs/compliance/` directly, so the finding registers stay the
single source of truth rather than accumulating a parallel assessment-log file.

## 4. Vendor and service-provider oversight

COPPA 312.8 and GDPR Article 28 both require oversight of any processor that touches
children's or other users' personal data, not just a one-time DPA signature. This is the
operative process; `docs/compliance/coppa-gdpr-remediation-plan.md` Phase 5 tracks executing it
against every processor currently in use.

**Before onboarding a processor** that will receive any user- or child-linked data (even
PII-scrubbed data, per the same standard applied to `pipeline_event` in the Phase 4d Article
17(3) analysis):

1. Confirm what data reaches the processor and why, using the same categories as
   `docs/planning/privacy-model.md`'s data classification.
2. Confirm a Data Processing Agreement (and, since every processor evaluated to date is
   US-hosted, Standard Contractual Clauses or DPF self-certification) is in place before the
   first real request, not retrofitted after.
3. Record the outcome in `docs/planning/privacy-model.md`'s processor list (remediation plan
   Phase 5c) and, once it exists, `docs/compliance/records-of-processing-activities.md`.

**Ongoing, per processor already in use:**

| Processor | Data received | Oversight mechanism |
|---|---|---|
| Supabase (Postgres, auth) | Full application database, including child-linked tables | DPA/SCC execution tracked (Phase 5a); region choice reviewed (Phase 4a, already resolved to a US region) |
| OpenRouter + downstream model providers | Story-generation prompts (PII-guarded; see `assert_prompt_pii_safe`) | Zero-data-retention terms are the standing blocker (Phase 5b); DPA/SCC execution tracked (Phase 5a) |
| Anthropic (direct) | Story-generation prompts, same guard as above | DPA/SCC execution tracked (Phase 5a) |
| OpenAI Moderation | Generated story prose, child-typed request text (Stage-0 classifier) | DPA/SCC execution tracked (Phase 5a); PII egress guard applied as of #304 |
| Google Perspective | Same as OpenAI Moderation | DPA/SCC execution tracked (Phase 5a); PII egress guard applied as of #304 |
| Google Gemini (nano banana cover art) | Cover-art prompts (PII-guarded as of #304) | DPA/SCC execution tracked (Phase 5a) |
| Cloudflare R2 | Cover images (private bucket, presigned-URL access only as of Phase 1d) | DPA/SCC execution tracked (Phase 5a) |
| Sentry | Error telemetry; hardcoded to exclude child-linked PII by design | DPA/SCC execution close to a formality given the no-PII design (Phase 5a); still tracked, not assumed unnecessary |

A processor is removed from active oversight only when it is fully decommissioned from the
codebase (no config referencing it, no residual data), not merely unused in the current
deployment tier.

## 5. Incident response

Breach classification, escalation, and the Article 33/34 notification clocks are documented
separately in `docs/compliance/breach-notification-runbook.md`, so that document can be handed
to someone mid-incident without wading through this program's broader scope. This program's
role in an incident is upstream: the risk-assessment cadence above is what is expected to
surface a vulnerability before it becomes an incident, and Section 3's post-incident review step
is what feeds a closed incident back into this program.

## 6. Relationship to other compliance documents

| Document | Relationship |
|---|---|
| `SECURITY.md` | External-facing vulnerability-reporting policy and known infrastructure limitations; this program is the internal-facing counterpart COPPA 312.8 and GDPR Article 32(1)(d) require. |
| `docs/compliance/coppa-compliance-audit.md` | COPPA finding register this program's annual cadence re-runs. |
| `docs/compliance/gdpr-compliance-review.md` | GDPR finding register this program's annual cadence re-runs. |
| `docs/compliance/coppa-gdpr-remediation-plan.md` | The phased plan this document is Phase 6b of; Phase 5 is the vendor-oversight execution tracker Section 4 above points to. |
| `docs/compliance/breach-notification-runbook.md` | The incident procedure this program references in Section 5 rather than duplicating. |
| `docs/compliance/records-of-processing-activities.md` | The Article 30 record Section 4's onboarding step feeds. |
| `docs/planning/privacy-model.md` | The processor data-classification source this program's vendor table (Section 4) is built from. |
