---
title: "Security and Privacy Assurance Register"
schema_type: common
status: published
owner: core-maintainer
purpose: "Register of security and privacy assurance items for CYO Adventure, spined on OWASP
  ASVS 5.0.0 and AISVS 1.0 plus GDPR and children's-privacy obligations plus curated operational
  content, recording for each item how it is verified, whether the verification can fail, and
  whether an existing gate already covers it."
tags:
  - security
  - compliance
  - reference
---

Drafted 2026-08-02. Revised 2026-08-02 after a three-way external research reconciliation and a
primary-source read of OWASP AISVS 1.0.
Companion to [`control-inheritance.md`](control-inheritance.md), which records inherited posture
in out-of-repo control planes. That file records *where* controls live; this one records *what is
asserted* and *how the assertion could fail*.

## Contract

This register does not block releases. An item is correctly handled when it has a named
verification method and a home in the project plan, not when a check passes. The defect this
register detects is *an item with no phase home*, not *an item with a failing check*.

### Row schema

`ID | spine category | framework ref | legal ref | class | protected property | verification
target | failure oracle | negative control | trigger | existing coverage | phase home | owner |
last verified | status`

Four of those fields are the anti-hollow machinery and are what distinguish this from a topic
list:

- **Protected property**: the condition claimed to be true, stated so that it could be false.
- **Verification target**: the actual deployed role, endpoint, artifact, dashboard, or workflow
  examined, as opposed to a fixture standing in for it.
- **Failure oracle**: the observable result that distinguishes true from false.
- **Negative control**: the deliberate violation demonstrated to trip the check.

### Verification classes

| Class | Meaning |
|-------|---------|
| STATIC | Assertable from source, schema, policy-as-code, or version-controlled configuration |
| DYNAMIC | Must be exercised against a running system |
| RUNTIME-CONFIG | Authoritative state lives in a deployed service or vendor control plane |
| MANUAL | Judgment is unavoidable, so the item carries an owner, trigger, cadence, and retained evidence |

### Status model

A binary pass/fail cannot express the failure this project actually suffers from, so it is not
used. Seven states:

| Status | Meaning |
|--------|---------|
| Evidence current | Verified against the correct target within cadence |
| Finding open | A defect was found and the phase home is named |
| Verification scheduled | Method and owner exist, evidence is not yet current |
| **Evidence invalid** | The check ran but targeted the wrong environment, role, path, or version |
| **Mechanism unproven** | The check has never demonstrated an ability to fail |
| Accepted exception | Risk and expiry explicitly recorded |
| Not applicable | Reason and reassessment trigger recorded |

The two bolded states are the point. They make a hollow check visible without turning the register
into a release gate. Every automated check enters at *mechanism unproven* and only leaves once a
negative control has tripped it.

Automated verifications run report-only: they write a status and a scheduled summary, and exit
zero.

## Source set

### Verified from primary sources

**OWASP ASVS 5.0.0**, released 30 May 2025 at Global AppSec EU Barcelona; current, not superseded;
around 350 requirements in **17 chapters**. The chapter list is confirmed by three independent
research runs plus this project's own inference, agreeing ordinal-for-ordinal, which closes
prerequisite 1 of the previous revision:

| # | Title | # | Title |
|---|-------|---|-------|
| V1 | Encoding and Sanitization | V10 | OAuth and OIDC |
| V2 | Validation and Business Logic | V11 | Cryptography |
| V3 | Web Frontend Security | V12 | Secure Communication |
| V4 | API and Web Service | V13 | Configuration |
| V5 | File Handling | V14 | Data Protection |
| V6 | Authentication | V15 | Secure Coding and Architecture |
| V7 | Session Management | V16 | Security Logging and Error Handling |
| V8 | Authorization | V17 | WebRTC |
| V9 | Self-contained Tokens | | |

Two migration facts constrain this register. Of the 286 requirements in 4.0.3, only 11 carried
forward unchanged and 15 took grammatical edits; 109 ceased to exist as separate requirements (50
deleted, 28 duplicates removed, 31 merged). **Requirement IDs must therefore be version-qualified**
(`v5.0.0-...`); a bare `V8.2.1` is ambiguous across editions. Separately, OWASP **removed the
embedded external-standard mappings** from the core document and moved crosswalks to the Common
Requirement Enumeration ecosystem, so the framework-reference column here is hand-maintained with
no official crosswalk to align to.

Canary for unreliable secondary sources: any reference stating ASVS 5.0 has **14 chapters** is
reproducing the 4.0.3 count and should not be trusted on anything else.

**OWASP AISVS 1.0**, June 2026, 76 pages, **12 chapters C1 to C12** plus three appendices. Read
directly. Its scope statement is the most useful thing in it and settles several questions the
external research left open:

> "AISVS is intentionally narrow. It only defines security requirements that are specific to AI
> and ML systems... It is not a self-contained security program for an AI application."

AISVS levels align 1:1 with ASVS levels: verifying against AISVS Level N *assumes* the application
has been verified against ASVS Level N. It is an overlay, not an alternative.

AISVS **explicitly places out of scope**, and names the source it defers to:

| Out of AISVS scope | Deferred to |
|---|---|
| General application security | ASVS |
| General software supply chain | OWASP SCVS, SLSA, CIS Controls |
| General infrastructure and platform hardening | CIS Benchmarks, NIST SP 800-53, SP 800-190, CSF |
| **General data protection and privacy operations**, including consent-management operation | ASVS, ISO/IEC 27001, GDPR |
| General logging and monitoring | ASVS |
| AI governance and risk management | ISO/IEC 42001, ISO/IEC 23894, NIST AI RMF |

Two corrections follow, both against claims made in the external research: AISVS does **not** cover
privacy (it is named in the exclusion list), and AISVS has **no human-oversight chapter**
(`AD.19 Human Oversight & Shutdown Control` is an entry in Appendix B's cross-reference inventory
of defence techniques, not a requirements chapter).

That table is also OWASP's own answer to the "do we need infrastructure baselines" question: yes,
for the layers we operate. This origin is self-managed hardware, so CIS Benchmarks are in scope for
the host, container runtime, and reverse proxy even though the managed Postgres internals are not.

**AISVS chapter applicability to this system:**

| Chapter | Verdict |
|---|---|
| C1 Training Data Integrity and Traceability | N/A, no training or fine-tuning. Reassess if fine-tuning is adopted |
| C2 Input Validation (prompt injection, content and policy screening) | **Core** |
| C3 Model Lifecycle Management and Change Control | Partial: C3.1 model authorization and C3.3 controlled deployment apply to provider and model pinning |
| C4 Infrastructure, Configuration and Deployment | Partial: C4.1 workload sandboxing applies to the self-hosted provider path |
| C5 Access Control and Identity for AI Components | Applies, notably C5.3 multi-tenant isolation |
| C6 Supply Chain Security for Models (AI BOM) | Partial |
| C7 Model Behavior, Output Control and Safety Assurance | **Core** |
| C8 Memory, Embeddings and Vector Database Security | Needs check: `diversity/` uses structural and lexical similarity, not embeddings, but this has not been confirmed against the code |
| C9 Orchestration and Agentic Security | Mostly N/A, the pipeline is staged jobs, not an agent loop. See C9.2 below |
| C10 Model Context Protocol Security | N/A in the product; MCP is development tooling only |
| C11 Adversarial Robustness | Partial |
| C12 Monitoring, Logging and Anomaly Detection | Applies |
| Appendix C, AC.1 to AC.14 AI-Assisted Secure Coding | **Applies strongly**; see SP-10 |

**GDPR**, Regulation (EU) 2016/679. Art. 32(1)(a) to (d), 32(2), 32(3), 32(4) as quoted in the
official text. Art. 32(1)(d), the duty to regularly test and evaluate effectiveness, is the legal
basis for the assurance-validity category: a check structurally incapable of detecting failure is
not an assessment of effectiveness. Adjacent articles carrying concrete obligations: 5, 6, 7, 8, 9,
12, 15 to 22, 24, 25, 27, 28, 29, 30, 33, 34, 35, 44 to 49.

**COPPA**, amended rule published 22 April 2025 (90 FR 16977), effective 23 June 2025, compliance
date 22 April 2026 (except §312.11(d)(1), (d)(4), (g)), therefore **enforceable now**.

### Recorded but not verified here

Claims from external research that this project has not independently confirmed, retained because
they are decision-relevant and marked so they are not laundered into fact: OWASP MASTG 2.0.0 (July
2026); CSA AICM 1.1 (June 2026); NIST SSDF 1.2 initial public draft (December 2025); Ninth Circuit
*NetChoice v. Bonta* (12 March 2026); FTC age-verification enforcement policy statement (25
February 2026); Maryland, Vermont, Nebraska, South Carolina design codes; Texas SB 2420, Utah,
Louisiana and Alabama App Store Accountability Acts; Brazil Law 15,211/2025; DTSP Best Practices
Framework 2025 and ISO/IEC 25389:2025; Verizon DBIR 2026 figures.

### Framework dispositions

| Source | Disposition |
|---|---|
| OWASP ASVS 5.0.0 | Spine, machine-readable (CSV, CycloneDX JSON) |
| OWASP AISVS 1.0 | Spine for the AI overlay, at the level matching the ASVS level |
| GDPR, UK GDPR, COPPA, UK AADC | Spine for legal obligations, hand-derived rows |
| OWASP LLM Top 10 (2025) | Consult: threat enumeration for building the adversarial corpus, not a control catalogue. AISVS supersedes it as the verification source |
| OWASP API Security Top 10 (2023) | Consult: pressure-test authorization and egress. Not a second spine |
| OWASP SCVS and SLSA | Consult for supply chain; named by AISVS as the deferral target and missed by all three research runs |
| CIS Benchmarks | Consult, bounded to layers we operate: host, container runtime, reverse proxy. Not the managed Postgres internals |
| NIST SSDF 800-218 / 800-218A | Consult, lift a handful of practices for the build and AI-change categories |
| MITRE ATLAS | Consult once for threat modelling. Not a maintained crosswalk |
| App store policies (Apple Kids, Google Play Families) | Release-channel checklist, activates at R2 |
| OWASP MASVS 2.1.0 | Dormant. Activates when the mobile wrapper enters design |
| ISO 27001 / 27701 / 42001, CSA CCM and AICM, SAMM, BSIMM, NIST CSF | Ignore for this register at this team size |

### Human-in-the-loop moderation

All three research runs concluded independently that **no purpose-built, auditable control set
exists** for human approval as the last barrier before generated content reaches a child. The
nearest published anchors are the DTSP Best Practices Framework (2025) and ISO/IEC 25389:2025
clauses 4 and 5, which describe human review as illustrative non-prescriptive practice.

One partial counterexample the research missed: **AISVS C9.2, High-Impact Action Approval and
Irreversibility Controls**, contains requirements that map well:

- `9.2.1` blocks execution of high-impact or irreversible actions "until explicit human approval is
  received and verified"
- `9.2.2` requires approval requests to display "canonicalized and complete action parameters...
  **without truncation or unsafe transformation**"
- `9.2.3` requires a trusted reversibility classification per action

`9.2.2` is the reviewer-completeness assertion this register needs. **It is an analogy, not a
citation**: C9.2 is scoped to agent runtimes and this pipeline is not agentic. Cite it as a pattern
source and state that the controls are locally authored.

## The spine

Seventeen categories, revised from sixteen. Changes and their evidence are in the reconciliation
record at the end.

| ID | Category | ASVS | AISVS | Legal |
|----|----------|------|-------|-------|
| SP-01 | Identity, Authentication, and Session Lifecycle | V6, V7, V9, V10 | C5.1 | 32(1)(b) |
| SP-02 | Authorization and Family Tenancy Isolation | V8, V4 | C5.2, C5.3 | 32(1)(b), 32(2) |
| SP-03 | Input Validation, Encoding, Injection | V1, V2 | C2 | 32(1)(b) |
| SP-04 | Business Logic and Abuse Resistance | V2, V4 | C9.1 | 32(1)(b) |
| SP-05 | Client-Side Storage, Offline Sync, Mobile Surface | V3, V14 | - | 32(1)(a), 32(2) |
| SP-06 | API Surface, Egress, SSRF | V4, V12 | C7.3 | 32(1)(b) |
| SP-07 | File, Object Storage, Media | V5, V8 | - | 32(1)(a) |
| SP-08 | Cryptography, Secrets, Key Management | V11, V12, V13 | - | 32(1)(a) |
| SP-09 | Runtime Configuration and Control-Plane Drift | V13, V12 | C4 | 32(1)(b) |
| SP-10 | Build and Software Supply Chain | V13, V15 | C6, App. C | 32(1)(b), 32(1)(d) |
| SP-11 | Logging, Audit Integrity, Alerting, Incident Response | V16 | C12 | 32(1)(b); Art. 33, 34 |
| SP-12 | Data Lifecycle, Rights, Processors, Transfers | V14 | - | 32(1)(a),(c); Art. 5, 15-22, 28-30, 44-49 |
| SP-13 | Children's Privacy, Consent, Age-Appropriate Design | - | - | Art. 8, 12, 25, 35; COPPA; UK AADC |
| SP-14 | AI Generation, Models, Prompts, Providers | - | C2, C3, C7, C11 | 32(1)(b), 32(2) |
| SP-15 | Human Approval Gate and Publication Integrity | V2 | C9.2 (analogy) | 32(2) |
| SP-16 | Availability, Resilience, Recovery | V13 | - | 32(1)(b),(c) |
| SP-17 | Assurance Validity and Change Lifecycle | V15 | App. C | **32(1)(d)** |

ASVS V17 (WebRTC) is **not applicable**: no peer-to-peer media. Re-review trigger: any proposal for
voice or video reading features. Recorded rather than silently dropped.

Three categories have no ASVS chapter and three have no AISVS chapter. SP-13, SP-15, and SP-17 sit
outside both. Roughly a fifth of the real risk surface for a children's application with an LLM
content pipeline is outside the two OWASP verification standards, which is the evidence for spining
on frameworks **and** legal obligations **and** curated content rather than on ASVS alone.

### Jurisdiction model

Obligations attach **per child, by the child's residence**, not by the operator's location. A single
US state resident pulls in that state's design code and app-store accountability act. The register
therefore carries a jurisdiction-trigger column rather than an assumed US-plus-UK/EU pair.

Two scoping decisions are open and belong to counsel, not to this file:

1. **Whether the UK Online Safety Act user-to-user duties and EU DSA Art. 28 bind this product.**
   External research reasoned they probably do not, because the product delivers operator-gated
   content within one family. **That premise is incomplete**: ADR-017 specifies cross-family
   recommendation sharing across a three-ring social boundary, which is user-initiated
   dissemination to other users and may flip the classification. Resolve before R2, because the
   answer determines whether age-assurance machinery is owed at all.
2. Whether an EU representative is required under Art. 27.

## What the source checklist missed

The originating 10-item "common issues in vibe coded apps" scorecard maps to: SP-08, SP-01, SP-02
(one probe), SP-03, SP-04 (HTTP rate limiting only), SP-05 (localStorage only), SP-05 and SP-09,
SP-11 (one facet), SP-03, SP-10 (one facet).

**Eight of seventeen categories receive zero questions**: SP-06, SP-07, SP-12, SP-13, SP-14, SP-15,
SP-16, SP-17. It contains no privacy question of any kind, nothing about the LLM pipeline, and
nothing about whether its own checks can fail.

## Existing gate coverage

Audited 2026-08-02 against twelve areas. The "can it fail" column is the one that matters.

| Area | Verdict | Can it fail? |
|------|---------|--------------|
| Privacy / RLS correctness | PARTIAL | Yes in CI, but RLS is a no-op in production |
| Authentication edge cases | PARTIAL | Yes; role-change and concurrent-session slices absent |
| Duplicate / divergent workflows | PARTIAL | Mostly no |
| DB structure and field types | COVERED | Yes |
| Query efficiency / N+1 | PARTIAL | Yes for 2 of 28 routers |
| Error handling and logging | PARTIAL | Yes; one test pins a gap rather than closing it |
| Hardcoded credentials / keys | PARTIAL | Local pre-commit only; no CI secret scan |
| Security response headers | PARTIAL | Yes for FastAPI; no gate on the nginx edge |
| Auth rate limiting / brute force | PARTIAL | Yes for IP-based; no per-account protection exists |
| Password reset / enumeration | PARTIAL | Yes on PR, not in the merge queue |
| Client-side data at rest | **NOT COVERED** | Nothing to fail |
| Frontend bundle contents | **NOT COVERED** | Nothing to fail |

### Cross-cutting gate defects

First tranche of work. Each invalidates multiple rows at once.

- **RLS is inert in production.** `core/database.py:265-268` records that the application connects
  as the Postgres owner pre-cutover, and RLS never applies to a table's owner, making
  `apply_family_rls_context` a no-op. The enforcement suite forces the `cyo_api` role in its own
  fixture, so it structurally cannot observe this. No gate asserts the deployed DSN role. Distinct
  from the PostgREST anon path, verified closed in `control-inheritance.md` Plane B; the gap here
  is the loss of defence-in-depth behind an application-layer authorization bug. Status:
  **evidence invalid**.
- **Scoping exists for 3 of ~20 RLS tables.** `20260724120000_scoped_rls_tier1_family_scoping.sql`
  scopes `child_profile`, `story_request`, `device_grant`. The other 17 carry a blanket
  `USING(true)`; their privacy rests entirely on the FastAPI layer.
- **The pre-push hook tier does not exist.** `.git/hooks/` contains only `pre-commit`, and
  `default_install_hook_types` is absent. Nine hooks staged `pre-push` have never run:
  `detect-secrets`, `bandit-full`, `basedpyright`, `frontend-typecheck`, `yamllint`, `qlty-check`,
  `qlty-full`, `pydoclint`, `markdownlint`. CI recovers three of them.
- **pre-commit.ci is not installed**, so the `ci:`/`skip:` block at `.pre-commit-config.yaml:12-15`
  is inert and there is no hosted fallback. No workflow runs `pre-commit run --all-files`.
- **No CI-side secret scanning.** No trufflehog, gitleaks, or detect-secrets in any workflow.
  Detection is one local commit-stage hook, bypassable by `--no-verify` or by a clone that never
  ran `pre-commit install`.
- **CodeQL does not run.** `CLAUDE.md` states `security-analysis.yml` runs it; that workflow runs
  Bandit and OSV-Scanner only, and the repo-wide `github/codeql-action` uses are `upload-sarif`
  steps. There is no SAST over the TypeScript tree at all. This is also a direct **AISVS AC.4.2**
  failure, which requires SAST on every pull request containing AI-generated code. The
  documentation must be corrected as well as the gap closed.
- **Source maps are served in production.** `frontend/vite.config.ts:188` `sourcemap: 'hidden'`
  emits the `.map` files and only omits the `sourceMappingURL` comment; `frontend/Dockerfile:101`
  copies `dist/` wholesale; `frontend/nginx.conf:69`'s asset regex does not match `.map`, so they
  fall through to `location /` and are served at predictable URLs.
- **SonarCloud cannot gate a PR.** `sonarcloud.yml:13-36` triggers on push to main/develop and
  `workflow_dispatch` only, and `:68` sets `fail-on-quality-gate` only for `push`. Scope narrowed
  twice: CI overrides `sonar.sources=src`, excluding the frontend, and
  `sonar-project.properties:76` excludes tests.
- **Merge-queue holes.** `frontend` and `frontend-e2e` carry `if: github.event_name !=
  'merge_group'` (`ci.yml:156`) and `ci-gate` counts `skipped` as pass (`ci.yml:969-971`). The
  `ci-gate` `needs` list (`ci.yml:935`) omits `diversity`, `api-tests`, and `coverage-upload`.
- **Vulture is warn-only**, emitting `::warning::` and continuing.
- **One test pins a gap.** `tests/unit/test_logging_security.py:262` asserts `api/deps.py` has no
  logger, so there is zero observability on authentication failures and the gate enforces the
  absence. Legitimate as a deliberate marker; must not be counted as coverage.

## Register rows

Seventy items. Provisional `O-nn` IDs pending the `SQ-*` reconciliation. Twelve are deferred
triggers that activate at R2 or on a named event, so the active count is fifty-eight, which is at
the upper end of what one maintainer can review meaningfully. **Trimming is a decision for the
maintainer, not a silent truncation.**

### SP-17 Assurance Validity and Change Lifecycle

The category that catches hollow checks. Listed first because it gates the credibility of every
other row. Legal basis Art. 32(1)(d).

| ID | Class | Check |
|----|-------|-------|
| O-27 | MANUAL | Every verification method in this register has a deliberate failing fixture proving it can report a failure. Checks with no such fixture hold status *mechanism unproven* |
| O-66 | STATIC | Every automated check records its production control target, execution trigger, evidence artifact, failure oracle, and owner; a quarterly query finds rows missing any field |
| O-67 | DYNAMIC | Each check's execution path is **observed, not inferred**: the hook fired, the workflow ran on the relevant event, against the right revision, over the right paths, with exit code propagated |
| O-68 | RUNTIME-CONFIG | Each deployment records a diff of vendor control-plane settings against the last known-good baseline, so dashboard drift is visible |
| O-69 | MANUAL | Quarterly, a named maintainer samples control evidence from source to deployed effect and records whether that evidence could have been produced while the protected property was false |
| O-70 | STATIC | Reassessment is triggered by **affected control surface, not by authorship**. Triggers: identity, authorization, tenancy or schema change; new or changed provider, SDK, dependency, model, prompt, moderation threshold, or parser; change to child-visible storage, sync, logging, or publication state; new data field, purpose, recipient, jurisdiction, or retention rule; control-plane change |

O-27 is the register's own health check. This repository has already produced multiple distinct
silent-pass failures; a register whose checks cannot fail reproduces the exact pathology it exists
to prevent, so canary work belongs in the same phase as the first batch of automated verifications,
not after it.

O-70 replaces "re-test after every AI-assisted change", the process item the previous revision could
not place. Authorship is not the risk: an AI-generated comment does not warrant what a hand-written
authorization change warrants. This converts an unscalable ritual into a testable change-control
assertion.

### SP-15 Human Approval Gate and Publication Integrity

Split from generation. The last barrier before content reaches a child, and it fails differently
from the model layer: through mis-defaulted visibility and reviewer incompleteness, not through
prompt injection.

| ID | Class | Check |
|----|-------|-------|
| O-17 | STATIC + DYNAMIC | No reader-visible node body exists without both a passing validator report and a human approval record, enforced in the read path and confirmed by a data invariant query |
| O-53 | STATIC | The **schema default** for content visibility is invisible, so a row the application forgets to set is safe |
| O-52 | DYNAMIC | The reviewer interface exposes every reachable branch, personalization substitution, moderation warning, media asset, and validation exception. Negative control: a hidden unsafe branch inserted into a test artifact must appear to the reviewer. Pattern source AISVS 9.2.2 |
| O-54 | DYNAMIC | Any post-approval change to text, graph, personalization, media, or policy version invalidates approval and returns the artifact to review |
| O-55 | DYNAMIC | Moderation classifier timeout, refusal, malformed response, quota exhaustion, or threshold misconfiguration routes to a human and **cannot be represented as approval** |
| O-71 | STATIC | Approval is bound to an immutable content digest plus reviewer identity, policy version, and timestamp; it cannot be satisfied by replaying a prior approval or by a default-true field |
| O-72 | DYNAMIC | No child-scoped principal can retrieve a story in any pre-approval state through any path: endpoint, cache, signed URL, offline bundle, notification, or search result |

O-72 generalizes O-17 across delivery paths. O-17's violation is a child-safety incident rather than
a security finding, which is why it is the one item worth a later conversation about enforcement in
the read path itself. That would be a product control, not a CI gate, and is therefore compatible
with the no-blocking decision. Not proposed now.

### SP-14 AI Generation, Models, Prompts, Providers

| ID | Class | Check |
|----|-------|-------|
| O-14 | STATIC | Untrusted intake text is passed in a data position with delimiters, never concatenated into system-prompt position (AISVS C2.1) |
| O-15 | STATIC | Content re-entering a later stage (series continuation, mutated skeletons) is re-classified before reuse |
| O-16 | STATIC | Every provider path (Anthropic, OpenRouter, Ollama, Modal, fallback) terminates in the identical validator plus moderation gate, with no provider-specific shortcut |
| O-18 | MANUAL | A maintained adversarial corpus runs against live thresholds each release; pass rate recorded with a trend (AISVS C11.1) |
| O-19 | RUNTIME-CONFIG | Worker egress is allowlisted to approved provider endpoints; child identifiers pseudonymized before crossing the boundary |
| O-20 | MANUAL | Each enabled provider has a recorded DPA/ZDR posture and a pinned model identifier (AISVS C3.1) |
| O-56 | DYNAMIC | The admin review dashboard is not an XSS sink for pipeline output. Composite path: guardian prompt injection produces markup in generated text, the validator checks topology and reading level but not markup safety, and it renders on the highest-privilege surface in the system |
| O-73 | DYNAMIC | Provider timeout, refusal, malformed output, content-filter response, or model removal produces an explicit non-publishable state, never an unmoderated fallback or a partial story |
| O-74 | RUNTIME-CONFIG | Provider or model changes, including silent hosted-model aliases, trigger regression against the structural, safety, and privacy corpora, retained by exact model version |

### SP-05 Client-Side Storage, Offline Sync, Mobile Surface

Two mandatory subsections: data at rest (confidentiality) and sync (integrity). They share a
category but not a threat, and the sync half was absent from the previous revision entirely.

| ID | Class | Check |
|----|-------|-------|
| O-39 | STATIC | Offline stores are keyed per profile, purged on logout and grant revocation, and hold no auth secret. Currently NOT COVERED |
| O-40 | STATIC | The service worker has a versioned kill-switch and never caches authenticated responses in a profile-agnostic key |
| O-41 | DYNAMIC | Switching profiles evicts the previous profile's cached content and player state |
| O-50 | DYNAMIC | On reconnect the server treats client-supplied state as untrusted and **re-authorizes it**. Negative control: a tampered payload claiming a gated level was completed, or claiming approval, is rejected |
| O-51 | DYNAMIC | Sync conflict resolution cannot move reading history, choices, ratings, or stories between children or families |
| O-75 | STATIC | A documented inventory names every child-data element in IndexedDB, Cache Storage, localStorage, and service-worker caches, with purpose and expiry |
| O-76 | *deferred, R2* | MASVS L1 plus the MASVS-PRIVACY subset activates when the mobile wrapper enters design |

`personalization_values` in IndexedDB holds children's real first names, sibling names, and kinship
labels. Nothing currently asserts a policy over client storage and no lint rule restricts
`localStorage`.

### SP-02 Authorization and Family Tenancy Isolation

Two mandatory subsections: vertical (role and capability) and horizontal (cross-family). Opposite
coverage states today.

| ID | Class | Check |
|----|-------|-------|
| O-05 | DYNAMIC | A guardian in family A receives 403/404 for every resource ID from family B, enumerated across all resource-bearing routers, including cursors, object keys, job IDs, and nested relationship IDs |
| O-06 | DYNAMIC | Cross-family recommendation payloads (ADR-017) contain only whitelisted fields, never child identity or reading history |
| O-07 | DYNAMIC | A guardian-only token is rejected by every `/admin` route and every moderation-threshold mutation |
| O-08 | DYNAMIC | Every secondary object reference (storybook version, node, assignment, cover asset) is authorization-checked at the leaf, not inherited from a parent check |
| O-09 | RUNTIME-CONFIG | Background workers connect with a least-privilege role subject to RLS, not the service key. Blocked on the ADR-021 cutover |
| O-77 | RUNTIME-CONFIG | The **production** connection identity is asserted from the deployed session (`current_user`, `rolbypassrls`, table ownership), not from a fixture. The non-hollow replacement for the current RLS suite |
| O-78 | DYNAMIC | Every RLS policy has a mutation test: dropping the policy turns at least one test red |

### SP-04 Business Logic and Abuse Resistance

| ID | Class | Check |
|----|-------|-------|
| O-10 | STATIC | Story-request creation enforces a per-family windowed generation budget independent of HTTP rate limits |
| O-11 | STATIC | The publish state machine is the only writer of reader-visible state |
| O-12 | DYNAMIC | Concurrent approve and concurrent grant-redeem attempts converge on a single terminal state under load |
| O-13 | DYNAMIC | Flag submission is idempotent per actor-target pair and rate-shaped |

### SP-06 API Surface, Egress, SSRF

| ID | Class | Check |
|----|-------|-------|
| O-21 | STATIC | Outbound URL fetches use an allowlist and reject link-local, metadata, and private ranges **after** DNS resolution and redirects. Known defect: `middleware/security.py` `_is_blocked_url` returns not-blocked when host parsing fails |
| O-79 | STATIC + DYNAMIC | The deployed route inventory, methods, auth dependencies, and audience designation are enumerated and reconciled against intent; undocumented or accidentally public routes are reported. Material here: 28 routers, and orphaned endpoints outlive the UI that called them |

O-21 is owned here rather than by SP-14, resolving a boundary the research flagged: URL parsing
belongs to input handling, destination authorization belongs to egress.

### SP-07 File, Object Storage, Media

| ID | Class | Check |
|----|-------|-------|
| O-22 | RUNTIME-CONFIG | Cover and avatar objects served via short-lived signed URLs or an authorizing proxy; the bucket denies public listing |
| O-23 | STATIC | Uploaded images are re-encoded server-side, EXIF stripped, and type-sniffed rather than trusted |
| O-80 | DYNAMIC | Object keys cannot be predicted or substituted to reach another family's media; authorization is checked before every signed URL is issued, not embedded in the key name |

### SP-10 Build and Software Supply Chain

| ID | Class | Check |
|----|-------|-------|
| O-24 | RUNTIME-CONFIG | Released container digests carry verifiable provenance; deployment pins by digest, not tag |
| O-25 | STATIC | Actions pinned by commit SHA; no `pull_request_target` checking out untrusted head; no secret reachable from a fork-triggered job |
| O-26 | STATIC | The client drift job runs on every contract change; lockfile integrity verified at install |
| O-81 | STATIC | **AISVS AC.4.2**: SAST, secret scanning, IaC scanning, and SCA run on every pull request. Currently failing: CodeQL does not run and no CI secret scanning exists |
| O-82 | MANUAL | **AISVS AC.4.1** requires AI-generated code to be reviewed by a human who is not the identity that requested the generation. A single-maintainer AI-assisted repository cannot satisfy this as written. Record as an **accepted exception with compensating controls** and an expiry, not as a silent skip |
| O-83 | STATIC | **AISVS AC.3.1**: secrets, credentials, and PII are never placed in AI tool context |
| O-84 | STATIC | **AISVS AC.7.2**: AI-generated infrastructure and pipeline configurations receive human review |

O-82 is the honest version of a control this project structurally cannot meet. Recording it as an
exception with an expiry is the difference between a known gap and an invisible one.

### SP-09 Runtime Configuration and Control-Plane Drift

Split from build and supply chain. Two of the three documented hollow checks are config-placement
problems, and `control-inheritance.md` names five out-of-repo planes, so drift demonstrably goes
unreviewed here.

| ID | Class | Check |
|----|-------|-------|
| O-48 | RUNTIME-CONFIG | The origin accepts public traffic only through the intended edge, or requires mTLS from it. **This is A9 in `control-inheritance.md`, confirmed open** |
| O-47 | STATIC | Forwarded headers are honored only from the known proxy hop; client-supplied correlation IDs are sanitized before logging |
| O-85 | RUNTIME-CONFIG | Auth, database, CDN, WAF, object-store, queue, CORS, redirect, logging, retention, and backup settings held in dashboards are exported or queried on a cadence and compared with an approved baseline |
| O-86 | DYNAMIC | Production disables debug behaviors, default credentials, permissive CORS, and test tenants, verified against deployed endpoints. Interacts with `ENVIRONMENT=local` silently disabling rate limiting |
| O-87 | RUNTIME-CONFIG | CIS Benchmark subset for layers we operate: host, container runtime, reverse proxy. Not the managed Postgres internals |

### SP-08 Cryptography, Secrets, Key Management

Absorbs the transport items formerly in a standalone Secure Communication category.

| ID | Class | Check |
|----|-------|-------|
| O-88 | STATIC + RUNTIME-CONFIG | Secrets absent from source, client bundles, images, logs, generated stories, prompts, and build artifacts; deployed secrets have owners, scopes, rotation procedures, and revocation tests. Includes webhook signature verification using production rather than test-mode secrets |
| O-89 | DYNAMIC | TLS policy, origin certificate validation, HSTS, redirect behavior, and backend-to-provider transport verified **from an external vantage point** |
| O-90 | MANUAL | Encryption-at-rest claims identify the threat actually addressed. Where vendor disk encryption does not protect against application or administrator access, the register does not credit it as solving that different threat |

O-89 encodes the verification vantage rule from `control-inheritance.md`: a control describing
posture at a trust boundary must be verified from outside that boundary.

### SP-11 Logging, Audit Integrity, Alerting, Incident Response

| ID | Class | Check |
|----|-------|-------|
| O-28 | STATIC | The events table grants no UPDATE or DELETE to the application role; entries carry a chained digest |
| O-29 | STATIC | An emitted-field allowlist test asserts no child identifier, story body, or token appears in log output, verified with seeded sensitive markers |
| O-30 | RUNTIME-CONFIG | Named detections exist for approval-bypass attempts, 403 spikes, and moderation-provider outage, each with a routed recipient |
| O-91 | DYNAMIC | A synthetic high-value event traverses the **deployed** pipeline to the actual maintained destination and is acknowledged by the named responder. Verifying that a logger was called does not satisfy this |
| O-92 | MANUAL | The incident plan can trace a child-data event across edge, application, identity provider, database, queue, model provider, object storage, and client sync, and includes Art. 33/34 and COPPA decision points |

### SP-12 Data Lifecycle, Rights, Processors, Transfers

| ID | Class | Check |
|----|-------|-------|
| O-31 | MANUAL | An erasure runbook enumerates every store (Postgres, R2, Redis payloads, retained raw LLM output, offline IndexedDB on family devices, backups) and a test deletion demonstrates residue-free removal within the stated SLA |
| O-32 | STATIC | Every data class has a stated TTL with an automated reaper and evidence of its last successful run |
| O-33 | MANUAL | An actual restore into a scratch environment was performed and recorded within the last quarter |
| O-34 | DYNAMIC | A guardian can obtain a machine-readable export within the statutory window, without receiving another family's data (Art. 20) |
| O-57 | MANUAL | Each provider is classified controller/processor/recipient with documented subprocessors, locations, retention, training-use terms, deletion support, and security commitments (Art. 28, 29) |
| O-58 | MANUAL | A transfer mechanism is recorded per non-EEA processor (Art. 44 to 49) |
| O-59 | MANUAL | A DPIA is completed and revisited on trigger. Effectively mandatory here: children plus profiling plus generative AI (Art. 35) |
| O-60 | MANUAL | An Art. 27 EU-representative determination is recorded, with reasoning |
| O-93 | STATIC | Records of processing are maintained with purposes, recipients, transfers, deletion periods, and a description of security measures (Art. 30) |

### SP-13 Children's Privacy, Consent, Age-Appropriate Design

| ID | Class | Check |
|----|-------|-------|
| O-35 | STATIC | Consent records are immutable, timestamped, versioned to the exact notice text displayed, and non-repudiable. Not a timeless boolean |
| O-36 | STATIC | Age and band changes are restricted to a verified guardian and audit-logged. Age is a safety parameter, not a preference: it determines what content the pipeline will send a child |
| O-37 | STATIC | Kid-scoped response schemas are field-allowlisted and diffed against the OpenAPI schema on contract change |
| O-38 | MANUAL | The published privacy notice's third-party list reconciles against the measured egress inventory |
| O-61 | MANUAL | A written children's-data security program exists with a named coordinator, annual risk assessment, ongoing safeguard testing, and annual evaluation (COPPA §312.8) |
| O-62 | STATIC | The data retention policy states purpose, business need, and a specific deletion timeframe, and is **published directly in the online privacy notice**; a link to a separate policy does not satisfy the rule (COPPA) |
| O-94 | DYNAMIC | Child-facing defaults minimize visibility, sharing, profiling, location, personalization, and persistent identifiers; weakening a protection requires an attributable decision (UK AADC, Art. 25) |
| O-95 | MANUAL | Notices and error messages are tested separately for roughly ages 5-7, 8-10, and 11-12, not with one adult notice (Art. 12, UK AADC) |
| O-96 | MANUAL + DYNAMIC | The child is told, age-appropriately, what a guardian or administrator can see and do (UK AADC monitoring transparency) |
| O-97 | MANUAL | A jurisdiction-trigger matrix maps each child's residence to the regimes it activates |
| O-98 | *deferred, R2* | App-store accountability: designate an age rating, ingest store-provided age and consent signals via the platform API, re-trigger parental consent on significant change |
| O-99 | *deferred, R2* | Apple Kids Category and Google Play Families pre-submission checklist, reviewed quarterly with captured page dates |

### SP-01 Identity, Authentication, Session Lifecycle

Merged from two categories on three-way research agreement, with two mandatory subsections because
this system has **two independent session lifecycles**, not one.

*Adult, OIDC:*

| ID | Class | Check |
|----|-------|-------|
| O-02 | STATIC | JWT verification rejects wrong `iss`, wrong `aud`, `alg` substitution, unknown `kid`, and refreshes JWKS on rotation. Largely covered by `tests/unit/test_oidc_verification.py` |
| O-03 | STATIC | Adult elevation has absolute and idle timeouts and is not persisted to durable storage |
| O-42 | RUNTIME-CONFIG | Deployed issuer, audience, signing algorithms, redirect and callback URIs, MFA policy, non-enumerable responses, and account-linking settings match an exported approved baseline. Invisible to any source-based review because auth is delegated |
| O-43 | STATIC | No self-service path grants `is_admin`; elevation is out-of-band and audit-logged |
| O-100 | DYNAMIC | Password reset, email change, and recovery cannot acquire another family or retain old sessions, with bounded token expiry, exercised through the **provider-hosted** flow rather than a mocked callback |

*Child, device grant:*

| ID | Class | Check |
|----|-------|-------|
| O-01 | DYNAMIC | Revoking a device grant terminates in-flight child sessions and blocks reissue within a stated bound. Known gap pinned at `tests/integration/test_child_sessions.py:792`: a revoked grant leaves a minted child token valid up to 12h |
| O-04 | STATIC | Offline mode enforces a maximum offline validity window and forces server re-verification on reconnect |
| O-101 | STATIC | The 4-digit PIN has an attempt cap or a documented, accepted compensating control. `api/child_sessions.py:159-167` currently declines a cap |

### SP-03 Input Validation, Encoding, Injection

| ID | Class | Check |
|----|-------|-------|
| O-102 | STATIC + DYNAMIC | Every externally writable field, **including generated model output**, has a defined type, length, structural constraint, normalization rule, and rejection behavior enforced server-side. Includes CSRF protection on state-changing forms and transformation of non-serializable internal values at the API boundary |
| O-103 | DYNAMIC | Child-visible text is rendered with context-appropriate encoding; stored HTML, script, URL, Markdown, Unicode-control, and bidirectional-text payloads remain inert on every child-facing surface |
| O-104 | DYNAMIC | Parsing failures, malformed graphs, oversized payloads, duplicate identifiers, and recursive structures fail predictably without partial writes or internal error disclosure. Includes OS command injection and RCE paths |

### SP-16 Availability, Resilience, Recovery

| ID | Class | Check |
|----|-------|-------|
| O-44 | STATIC | Every expensive operation (generation, cover art, full-graph validation, re-screen) is queued with bounded concurrency and a per-tenant cap, never executed on the request thread |
| O-45 | STATIC | The worker re-derives and re-validates authorization from the database at job start rather than trusting the payload |
| O-46 | RUNTIME-CONFIG | Redis is unreachable from outside the compose network; payloads carry identifiers rather than PII |
| O-105 | DYNAMIC | Generation and sync jobs are idempotent or uniquely deduplicated, preserve tenant context, and cannot publish or corrupt state after duplicate, delayed, or out-of-order execution. Includes connection-pool release under concurrent load |
| O-106 | DYNAMIC | A restoration cannot resurrect a deleted account or republish withdrawn content without reconciliation against deletion, revocation, and publication records |

### Cross-cutting

| ID | Class | Check |
|----|-------|-------|
| O-49 | STATIC | Every gate defaults to not-approved on exception, verified by a fault-injection test per gate. For this product a fail-open moderation gate is the worst possible outcome |

## Reconciliation record

Three external deep-research runs, 2026-08-02, all treated as untrusted data per OWASP LLM01 and
verified against primary sources where a claim was load-bearing. All three disclosed or exhibited
anchoring on the sixteen-category spine they were shown; convergence with it is partly contaminated
and divergence from it is the higher-signal part.

### Adopted on multi-run agreement

| Change | Votes |
|--------|-------|
| Split generation into model-layer and human-approval-gate | 3 of 3; two called it the most important recommendation |
| Add an assurance-validity meta category for hollow checks | 2 of 3, and the dissent contradicted its own Part 2 |
| Add offline sync integrity as distinct from client data at rest | 3 of 3 |
| Merge session into identity, with mandatory subsections | 3 of 3 |
| Fold the Secure Communication heading, keep its assertions | 3 of 3 |
| Split vendor runtime config from build and supply chain | 2 of 3, one conditional on dashboard drift going unreviewed, which it demonstrably does here |
| Adopt a multi-state status model over pass/fail | 1 of 3, adopted on merit |
| Add failure-oracle and negative-control row fields | 1 of 3, adopted on merit |
| Jurisdiction triggers keyed to child residence | 1 of 3, adopted on merit |

The merge of session into identity was initially resisted here on the grounds that this system has
two independent session lifecycles. That objection is an argument for more rows, not for a separate
heading, so the merge was accepted with both subsections made mandatory.

### Rejected, with the evidence

- **"Remove the process items from the register."** Contradicted by Art. 32(1)(d), which the same
  report quoted correctly in its own factual section. Removal recreates the maintainer's stated
  failure mode: not done, and not in the plan.
- **"Ignore cloud and container baselines, the vendor owns it."** Refuted by AISVS's own scope
  statement, which names CIS Benchmarks and NIST SP 800-53/190 as the deferral target for
  infrastructure hardening, and by A9: the origin is self-managed hardware with a confirmed bypass.
- **"Cut cryptography and secrets."** The secrets half is not vendor-managed, and no CI-side secret
  scanning exists anywhere in the repository.
- **"Cut availability and recovery."** Art. 32(1)(c) makes restorability binding.
- **"Merge input validation with client-side data at rest."** Conflates DOM output encoding with
  children's names in IndexedDB: no shared threat, method, or owner.

### Corrected against the primary document

One run recommended AISVS on the grounds that it covers privacy and contains a human-oversight
chapter. Reading AISVS 1.0 directly: privacy operations are in its **explicit exclusion list**, and
there is no human-oversight chapter. The recommendation to adopt AISVS survives; the reasons given
for it did not. The genuinely valuable finding, which no run reported, is **Appendix C
(AC.1 to AC.14, AI-Assisted Secure Coding)**, a published control set addressing exactly the
AI-assisted-change question all three runs answered differently from first principles.

### Prompt defects worth recording

Two facts were sanitized out of the research brief, and both produced confidently wrong conclusions:
the origin is self-managed hardware behind a third-party edge, not fully managed cloud; and ADR-017
cross-family recommendation sharing exists, which bears directly on DSA Art. 28 classification.
Over-sanitizing a brief does not produce a vaguer answer, it produces a confident answer to a
different question.

## Remaining prerequisites

1. **Register the `SQ-*` namespace in `plan-manifest.toml`.** No such namespace exists on main, so
   `scripts/check_work_linkage.py` cannot see any of these rows.
2. **Reconcile numbering against the roughly 24 `SQ-*` items already drafted elsewhere.** The `O-nn`
   identifiers are provisional to avoid claiming IDs that may already be taken.
3. **Confirm no ASVS 5.0.x patch has shipped since 5.0.0.** Repository listings name 5.0.1 as the
   next target, not a release.
4. **Confirm AISVS C8 applicability**: whether `diversity/` uses embeddings or only structural and
   lexical similarity.
5. **Counsel scoping decision** on UK OSA and DSA Art. 28, per the jurisdiction model above.
6. **Decide the row budget.** Seventy items with fifty-eight active is at the upper end for one
   maintainer. Trimming is the maintainer's call.

## Source-quality note

Of the "50 most common errors in vibe-coded apps" source, only about 18 items are
security-checkable; the remainder are ordinary build and runtime bugs (hydration mismatches, hook
rules, type errors, cold starts). They were not forced into security categories. Both web sources
were treated as untrusted data, and neither contained content directed at an automated reader.
