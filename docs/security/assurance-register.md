---
title: "Security and Privacy Assurance Register"
schema_type: common
status: published
owner: core-maintainer
purpose: "CYO Adventure's instantiation of the portable assurance spine: which of the seventeen
  categories and which regulatory regimes apply to this product, the audited state of existing
  gates, and the register rows with their verification methods and phase homes."
tags:
  - security
  - compliance
  - reference
---

Drafted 2026-08-02. Restructured 2026-08-02 into an instantiation of
[`assurance-spine.md`](assurance-spine.md).

**This file is project-specific.** The categories, the status model, the row schema, the framework
layer, and the regulatory catalog all live in the spine, which is portable across projects. This
file records what CYO Adventure does with them: which categories and regimes apply, which are N/A
and why, what the existing gates actually verify, and the rows themselves.

Companion: [`control-inheritance.md`](control-inheritance.md) records inherited posture in the five
out-of-repo control planes. The spine says what to assert, this file says what we assert, and
control-inheritance says where the asserted thing lives.

## Contract

Per the spine's instantiation contract, and reaffirming the maintainer's decision: **this register
does not block releases.** An item is correctly handled when it has a named verification method and
a home in the project plan, not when a check passes. The defect this register detects is *an item
with no phase home*.

Automated verifications run report-only: they write a status and a scheduled summary, and exit
zero. Every automated check enters at status *mechanism unproven* and leaves only once a negative
control has tripped it.

## Category applicability

All seventeen categories apply. None is N/A for this product, which is itself worth noting: a
children's application with an LLM content pipeline, offline sync, a self-managed origin, and
planned store distribution touches the whole spine.

Sub-scope exclusions recorded rather than dropped:

| Excluded | Category | Reason | Reassessment trigger |
|---|---|---|---|
| ASVS V17 WebRTC | SP-03, SP-06 | No peer-to-peer media | Any voice or video reading feature |
| AISVS C1 training data | SP-14 | No training or fine-tuning; hosted inference only | Any fine-tune or LoRA |
| AISVS C10 MCP | SP-06 | MCP is development tooling, not in the product | Any MCP surface shipped to users |
| AISVS C8 embeddings | SP-02, SP-12 | **Unconfirmed.** `diversity/` is believed to use structural and lexical similarity, not embeddings | Confirm against the code; any vector store |
| MASVS | SP-05 | No native or wrapped mobile client yet | Mobile wrapper enters design (R2) |
| PCI DSS | SP-08 | No payment processing | Any payment, subscription, or in-app purchase |

## Regulatory applicability

Run against the spine's seven triggers, 2026-08-02.

**T1 data classes.** Children's given names, ages and reading bands, sibling and kinship labels,
reading history and choices, guardian email and auth identity, AI-generated story content, cover
imagery. No health, financial, card, biometric, genetic, precise-geolocation, or government-ID
data.

**T2 subjects.** Children under 13 (primary), minors 13-17, guardian adults. Currently one
household plus invited families; public consumer population at R2/R3.

**T3 sector.** General consumer. Not health, financial services, education, or government
contracting.

**T4 residence.** US only today. No EU, UK, or non-US users.

**T5 business model.** No sale or sharing of personal data, no targeted advertising, no profiling
with legal or similarly significant effect. Two features matter for classification:
**cross-family recommendation sharing (ADR-016)** is user-initiated dissemination to other users,
and **app-store distribution (ADR-008)** is planned for R2/R3.

**T6 deployment.** Self-managed homelab hardware behind a third-party edge, plus a BaaS identity
and database plane, an object-store plane, and an infrastructure-repo plane. Five control planes
sit outside this repository; see `control-inheritance.md`.

**T7 contractual.** App-store policies at R2/R3. No customer DPAs, no PCI obligation, no
government contract clauses.

### Regimes that attach now

| Regime | Why | Register rows |
|---|---|---|
| **FTC Act §5** | Any consumer-facing product. Security and privacy claims in the notice become enforceable representations | O-38, O-62, O-94 |
| **COPPA** (compliance date 22 Apr 2026, therefore live) | Children under 13, child-directed service | O-35, O-36, O-61, O-62, O-31 |
| **State breach notification** | Attaches with the first non-household user | O-92 |
| **ADA / WCAG** | Consumer-facing; also overlaps the age-appropriate-design duty to be understandable | O-95 |

### Regimes that attach at a named trigger

Recorded now with the trigger, so that crossing it is a scheduling decision rather than a
discovery. This is the same treatment GDPR gets: written down before it binds.

| Regime | Trigger | Status |
|---|---|---|
| **State comprehensive privacy** (20 states as of Feb 2026) | First user outside the operator's household in a covered state, above any applicable threshold | O-97 jurisdiction matrix owns the determination |
| **State minors' design codes** (CA AADC, MD, NE, VT, CT, TX SCOPE, FL HB 3, UT) | Public launch. Track enactment and litigation status separately; several are partially enjoined | O-94, O-97 |
| **App store accountability acts** (TX SB 2420, UT, LA, AL) | Store distribution at R2/R3. Duties land on the **developer**: age rating, ingest store age and consent signals, re-trigger consent on significant change | O-98 |
| **App store policies** (Apple Kids, Google Play Families) | Store submission | O-99 |
| **GDPR / UK GDPR** | First EU or UK child or guardian | O-57 to O-60, O-93, O-34 |
| **DSA Art. 28** | Analysed: does not engage, the service is not an Art. 3(i) online platform. Re-open if any O-118 structure changes | O-118 |
| **EU AI Act** transparency | EU market entry; generated content disclosure | O-74 |
| **CRA** | Placing the product on the EU market | Deferred |
| **UK Online Safety Act** | UK users. The s.3(1) user-to-user test is broader than the DSA's and is **not** clearly failed here | **Open counsel question**, see below |
| **CAN-SPAM / TCPA** | Any marketing email or SMS beyond transactional guardian notifications | Deferred |
| **CIPA / session replay** | Adding third-party analytics, replay, or advertising tags | Deferred |
| **BIPA / CUBI** | Any face, voice, or fingerprint processing. Note: a child avatar photo is not biometric data unless a face template is derived | Deferred |
| **PCI DSS** | Any payment path | Deferred |
| **FERPA** | Any sale to or deployment through a school | Deferred |
| **State AI laws** (CO, TX TRAIGA, IL, NYC LL144) | Consequential decisions about people, or AI-in-hiring. Story generation is not a consequential decision; disclosure duties may still attach | Monitor |

### Regimes determined not applicable

HIPAA (no PHI), GLBA (not a financial institution), SOX and SEC disclosure (not a public company),
FCRA (no consumer reports or eligibility decisions), VPPA (no video), FedRAMP, CMMC, NIST 800-171,
DFARS (no government contract), EAR/ITAR/OFAC (no export-controlled technology; geo-restriction
still worth considering at public launch), NIS2, DORA, DMA, Data Act, eIDAS 2 (no trigger).
Each carries the obvious reassessment trigger: the fact that made it N/A changing.

### DSA Art. 28 and UK OSA classification

Analysed 2026-08-02 against primary text. Three external research runs concluded neither binds, but
each reasoned from an incomplete premise (they were not told ADR-016 exists). The conclusion holds;
the reasoning below replaces theirs.

**DSA: Art. 28 does not engage.** Art. 28 applies to providers of *online platforms*. An online
platform (Art. 3(i)) requires *dissemination to the public*, defined at Art. 3(k) as "making
available of information to a potentially unlimited number of persons." Recital 14 supplies the
test for group-admission cases: information behind registration or group admission is publicly
disseminated only "where recipients of the service seeking to access the information are
automatically registered or admitted without a human decision."

Admission here requires three human decisions: an admin creates the connection
(`POST /admin/family-connections`, `_require_admin`), then each side's guardian separately consents
(`_require_guardian`, setting `consented_by_sharer_*` and `consented_by_viewer_*`), and `_is_active`
requires both. Either side revoking deactivates immediately. ADR-016 forecloses a "receive from
everyone" option, user discovery, and free text. The recipient set is individually named and
individually approved, so Recital 14's automatic-admission test fails and Art. 3(k) is not
satisfied. Art. 19 (micro and small enterprises are excluded from all of Section 3, where Art. 28
sits) is an independent second line that we do not need to rely on. Art. 28(2) is satisfied by
having no advertising; Art. 28(3) forecloses a mandate to collect more data to detect minors.

**UK OSA is unresolved and is the harder case.** OSA s.3(1) defines a user-to-user service with no
"dissemination to the public" qualifier and no Recital 14 equivalent, so a recommendation shared
between two consented guardians is caught on the face of the definition. There is no
micro-enterprise exemption, and Schedule 1's limited-functionality exemption enumerates comments and
reviews on provider content plus likes, emoji, and yes/no voting, which does not squarely reach a
structured recommendation. **Counsel question, narrowly framed**: does a structured, non-free-text
recommendation exchanged between two mutually consented guardian accounts constitute user-generated
content encountered by another user, and if so does Schedule 1 para 4 reach it? Owned by O-97.
Practical hedge: keep the UK out of scope by design via the jurisdiction signal at O-117.

**Structures that carry the DSA conclusion.** Each is currently doing legal work; changing any one
of them re-opens the classification. Tracked as O-118.

| Structure | Where | Why it matters |
|---|---|---|
| Admin-gated connection creation | `api/family_connections.py` `_require_admin` | An auto-accepting invite link is exactly Recital 14's "admitted without a human decision" |
| Dual guardian consent, both sides | `_is_active` requires both timestamps | One-sided push weakens the closed-group characterisation |
| No discovery surface | absence of any family or profile search | A directory makes the recipient set potentially unlimited at point of search |
| No free text between users | whitelisted recommendation fields only | Highest-cost reversal: converts provider content into user content and engages Art. 16, 17, and 20 plus the OSA illegal-content duties at once |
| Directional and revocable | revoke deactivates immediately | Supports the closed-group reading |

**Still open.** Is an EU representative required under Art. 27 when EU users are first admitted.

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
- **A required check fails on third-party availability, in files outside the diff.**
  `Dependency & Standards Validation` is a required status check (ruleset `cyo-require-ci-gate`)
  and fans in from the lychee link check, which scans the **whole tree**, not the PR's diff. So an
  external site that is slow, or that rejects a HEAD request, turns a required gate red on a PR
  that did not touch the file. Observed twice within ten minutes on PR #562, each time on a
  different URL in someone else's document. Compounding it, `pr-validation.yml` has no `push`
  trigger, so main is never link-checked and a bad URL is only ever discovered by, and attributed
  to, the next unrelated PR. `--accept` omits 415, which servers return when they refuse the HEAD
  method rather than when a link is broken. Two effects, both bad: real link rot is indistinguishable
  from third-party flakiness, and the standing incentive is to re-run until green, which is
  precisely how a gate stops being read. Status: **evidence invalid**.
- **No CI-side secret scanning.** No trufflehog, gitleaks, or detect-secrets in any workflow.
  Detection is one local commit-stage hook, bypassable by `--no-verify` or by a clone that never
  ran `pre-commit install`. Fails **AISVS AC.4.2**.
- **CodeQL does not run.** `CLAUDE.md` states `security-analysis.yml` runs it; that workflow runs
  Bandit and OSV-Scanner only, and the repo-wide `github/codeql-action` uses are `upload-sarif`
  steps. There is no SAST over the TypeScript tree at all. Also fails **AISVS AC.4.2**. The
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

Seventy-eight items. Provisional `O-nn` IDs pending the `SQ-*` reconciliation. Twelve are deferred
triggers, so the active count is sixty-six, which is **above** the ~60 ceiling one maintainer can
review meaningfully. Trimming is the maintainer's decision, not a silent truncation.

### SP-17 Assurance Validity and Change Lifecycle

Listed first because it gates the credibility of every other row. Legal basis GDPR Art. 32(1)(d);
US equivalents are COPPA §312.8 ongoing safeguard testing and annual evaluation.

| ID | Class | Check |
|----|-------|-------|
| O-27 | MANUAL | Every verification method in this register has a deliberate failing fixture proving it can report a failure. Checks with no such fixture hold status *mechanism unproven* |
| O-66 | STATIC | Every automated check records its production control target, execution trigger, evidence artifact, failure oracle, and owner; a quarterly query finds rows missing any field |
| O-67 | DYNAMIC | Each check's execution path is **observed, not inferred**: the hook fired, the workflow ran on the relevant event, against the right revision, over the right paths, with exit code propagated |
| O-68 | RUNTIME-CONFIG | Each deployment records a diff of vendor control-plane settings against the last known-good baseline, so dashboard drift is visible |
| O-69 | MANUAL | Quarterly, a named maintainer samples control evidence from source to deployed effect and records whether that evidence could have been produced while the protected property was false |
| O-70 | STATIC | Reassessment is triggered by **affected control surface, not by authorship**. Triggers: identity, authorization, tenancy or schema change; new or changed provider, SDK, dependency, model, prompt, moderation threshold, or parser; change to child-visible storage, sync, logging, or publication state; new data field, purpose, recipient, jurisdiction, or retention rule; control-plane change |
| O-107 | MANUAL | **AISVS AC.1.1-AC.1.3**: a written AI-assisted-coding workflow names approved tools, prohibited use cases, permitted input data classifications, the SSDLC phases covered, the gates that stay mandatory regardless of AI involvement, and the adversarial scenarios it mitigates |
| O-108 | MANUAL | **Quarterly US state-law refresh** against the IAPP and Bloomberg trackers, tracking enactment and litigation status separately. The spine's own volatility table makes this the fastest-decaying input to this register |

O-27 is the register's own health check. This repository has already produced multiple distinct
silent-pass failures; a register whose checks cannot fail reproduces the exact pathology it exists
to prevent, so canary work belongs in the same phase as the first batch of automated verifications.

O-70 replaces "re-test after every AI-assisted change". Authorship is not the risk: an AI-generated
comment does not warrant what a hand-written authorization change warrants.

### SP-15 Human Decision Gates and Publication Integrity

The last barrier before content reaches a child. Fails differently from the model layer: through
mis-defaulted visibility and reviewer incompleteness, not through prompt injection.

| ID | Class | Check |
|----|-------|-------|
| O-17 | STATIC + DYNAMIC | No reader-visible node body exists without both a passing validator report and a human approval record, enforced in the read path and confirmed by a data invariant query |
| O-53 | STATIC | The **schema default** for content visibility is invisible, so a row the application forgets to set is safe |
| O-52 | DYNAMIC | The reviewer interface exposes every reachable branch, personalization substitution, moderation warning, media asset, and validation exception. Negative control: a hidden unsafe branch inserted into a test artifact must appear to the reviewer. Pattern source AISVS 9.2.2 |
| O-54 | DYNAMIC | Any post-approval change to text, graph, personalization, media, or policy version invalidates approval and returns the artifact to review |
| O-55 | DYNAMIC | Moderation classifier timeout, refusal, malformed response, quota exhaustion, or threshold misconfiguration routes to a human and **cannot be represented as approval** |
| O-71 | STATIC | Approval is bound to an immutable content digest plus reviewer identity, policy version, and timestamp; it cannot be satisfied by replaying a prior approval or by a default-true field |
| O-72 | DYNAMIC | No child-scoped principal can retrieve a story in any pre-approval state through any path: endpoint, cache, signed URL, offline bundle, notification, or search result |

AISVS C9.2 is the nearest published anchor for this category. It is an **analogy, not a citation**:
C9.2 is scoped to agent runtimes and this pipeline is staged RQ jobs. The DTSP Best Practices
Framework (2025) and ISO/IEC 25389:2025 clauses 4 and 5 describe human review only as illustrative
non-prescriptive practice, so these controls are locally authored.

O-17's violation is a child-safety incident rather than a security finding, which is why it is the
one item worth a later conversation about enforcement in the read path itself. That would be a
product control, not a CI gate, and is therefore compatible with the no-blocking decision.

### SP-14 AI and Model Layer

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
| O-74 | RUNTIME-CONFIG | Provider or model changes, including silent hosted-model aliases, trigger regression against the structural, safety, and privacy corpora, retained by exact model version. Also the hook for EU AI Act generated-content disclosure if EU market entry occurs |

### SP-10 Build and Software Supply Chain

Substantially expanded after reading AISVS Appendix C in full. Sections AC.11 to AC.13 cover the
development pipeline being attacked *through* the AI tooling, a surface this register did not
previously touch at all. It is live here: CodeRabbit and `claude-baseline-review.yml` both consume
PR content.

| ID | Class | Check |
|----|-------|-------|
| O-24 | RUNTIME-CONFIG | Released container digests carry verifiable provenance; deployment pins by digest, not tag |
| O-25 | STATIC | Actions pinned by commit SHA; no `pull_request_target` or `workflow_run` executing untrusted code with write permissions or secret access; no secret reachable from a fork-triggered job (**AC.12.1**) |
| O-26 | STATIC | The client drift job runs on every contract change; lockfile integrity verified at install |
| O-81 | STATIC | **AC.4.2**: SAST, secret scanning, IaC scanning, and SCA run on every pull request. **Currently failing**: CodeQL does not run and no CI secret scanning exists |
| O-82 | MANUAL | **AC.4.1** requires AI-generated code to be reviewed by a human who is not the identity that requested the generation. A single-maintainer AI-assisted repository cannot satisfy this as written. Record as an **accepted exception with compensating controls and an expiry**, not a silent skip |
| O-83 | STATIC | **AC.3.1-AC.3.2**: secrets, credentials, and PII never enter AI tool context, enforced in hooks and CI, with automated redaction of context windows |
| O-84 | STATIC | **AC.7.1-AC.7.3**: AI-generated infrastructure and pipeline artifacts are labeled, human-reviewed before running outside a sandbox, and pass policy-as-code at least as strictly as human-authored changes |
| O-109 | STATIC | **AC.8.1**: an agent cannot approve, merge, sign, or deploy an artifact it generated, enforced by branch protection, CI, and the registry. AISVS is explicit that "policy alone does not satisfy this control". **Live exposure**: assistants in this repo can enable auto-merge on PRs they authored |
| O-110 | STATIC | **AC.11.1-AC.11.3**: AI review bots treat PR diff, title, body, comments, commit messages, and linked URLs as untrusted; their system prompts are hash-pinned and not modifiable from repository or PR-controlled input; their output is schema-validated and never executed |
| O-111 | STATIC | **AC.11.7 + AC.12.3 + AC.13.2**: fork and first-time-contributor PRs run AI review in read-only shadow mode and require maintainer approval before any secret-bearing or privileged workflow processes them. Bot-level enforcement does not substitute for platform-level environment protection |
| O-112 | STATIC | **AC.12.5**: changes to workflow definition files route through an elevated review path regardless of author, and no agent holds bypass authority over it |
| O-113 | MANUAL | **AC.12.8**: remediating a vulnerable workflow invalidates or re-validates every PR opened before the fix, so a later commit to an old PR cannot pick up the stale definition and route around it |
| O-114 | STATIC | **AC.10.1 + AC.5.1**: AI-generated artifacts carry model identity and version, tool identity, prompt hash, human involvement, and correlation IDs, sufficient to replay prompt to response to commit to build to deployment |

O-82 is the honest version of a control this project structurally cannot meet. Recording it as an
exception with an expiry is the difference between a known gap and an invisible one. Note that
CLAUDE.md's standing rule to treat issue and PR content as untrusted data is a hand-derived version
of AC.3.3 and AC.11.1; the published requirements are stricter and are the better citation.

### SP-09 Runtime Configuration and Control-Plane Drift

| ID | Class | Check |
|----|-------|-------|
| O-48 | RUNTIME-CONFIG | The origin accepts public traffic only through the intended edge, or requires mTLS from it. **This is A9 in `control-inheritance.md`, confirmed open** |
| O-47 | STATIC | Forwarded headers are honored only from the known proxy hop; client-supplied correlation IDs are sanitized before logging |
| O-85 | RUNTIME-CONFIG | Auth, database, CDN, WAF, object-store, queue, CORS, redirect, logging, retention, and backup settings held in dashboards are exported or queried on a cadence and compared with an approved baseline |
| O-86 | DYNAMIC | Production disables debug behaviors, default credentials, permissive CORS, and test tenants, verified against deployed endpoints. Interacts with `ENVIRONMENT=local` silently disabling rate limiting |
| O-87 | RUNTIME-CONFIG | CIS Benchmark subset for layers we operate: host, container runtime, reverse proxy. Not the managed Postgres internals |
| O-115 | RUNTIME-CONFIG | **AC.7.5 + AC.12.4**: drift detection compares deployed infrastructure and live workflow configuration against signed baselines; runners processing untrusted or AI-generated artifacts are ephemeral and isolated from production credentials |

### SP-02 Authorization and Tenancy Isolation

Two mandatory subsections: vertical (role and capability) and horizontal (cross-family).

| ID | Class | Check |
|----|-------|-------|
| O-05 | DYNAMIC | A guardian in family A receives 403/404 for every resource ID from family B, enumerated across all resource-bearing routers, including cursors, object keys, job IDs, and nested relationship IDs |
| O-06 | DYNAMIC | Cross-family recommendation payloads (ADR-016) contain only whitelisted fields, never child identity or reading history |
| O-07 | DYNAMIC | A guardian-only token is rejected by every `/admin` route and every moderation-threshold mutation |
| O-08 | DYNAMIC | Every secondary object reference (storybook version, node, assignment, cover asset) is authorization-checked at the leaf, not inherited from a parent check |
| O-09 | RUNTIME-CONFIG | Background workers connect with a least-privilege role subject to RLS, not the service key. Blocked on the ADR-021 cutover |
| O-77 | RUNTIME-CONFIG | The **production** connection identity is asserted from the deployed session (`current_user`, `rolbypassrls`, table ownership), not from a fixture. The non-hollow replacement for the current RLS suite |
| O-78 | DYNAMIC | Every RLS policy has a mutation test: dropping the policy turns at least one test red |

### SP-01 Identity, Authentication, Session Lifecycle

Two mandatory subsections, because this system has two independent session lifecycles.

*Adult, OIDC:*

| ID | Class | Check |
|----|-------|-------|
| O-02 | STATIC | JWT verification rejects wrong `iss`, wrong `aud`, `alg` substitution, unknown `kid`, and refreshes JWKS on rotation. Largely covered by `tests/unit/test_oidc_verification.py` |
| O-03 | STATIC | Adult elevation has absolute and idle timeouts and is not persisted to durable storage |
| O-42 | RUNTIME-CONFIG | Deployed issuer, audience, signing algorithms, redirect and callback URIs, MFA policy, non-enumerable responses, and account-linking settings match an exported approved baseline. Invisible to source-based review because auth is delegated |
| O-43 | STATIC | No self-service path grants `is_admin`; elevation is out-of-band and audit-logged |
| O-100 | DYNAMIC | Password reset, email change, and recovery cannot acquire another family or retain old sessions, with bounded token expiry, exercised through the **provider-hosted** flow rather than a mocked callback |

*Child, device grant:*

| ID | Class | Check |
|----|-------|-------|
| O-01 | DYNAMIC | Revoking a device grant terminates in-flight child sessions and blocks reissue within a stated bound. Known gap pinned at `tests/integration/test_child_sessions.py:792`: a revoked grant leaves a minted child token valid up to 12h |
| O-04 | STATIC | Offline mode enforces a maximum offline validity window and forces server re-verification on reconnect |
| O-101 | STATIC | The 4-digit PIN has an attempt cap or a documented, accepted compensating control. `api/child_sessions.py:159-167` currently declines a cap |

### SP-05 Client-Side Storage, Offline Sync, Client Surface

Two mandatory subsections: data at rest (confidentiality) and sync (integrity).

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

### SP-03 Input Validation, Encoding, Injection

| ID | Class | Check |
|----|-------|-------|
| O-102 | STATIC + DYNAMIC | Every externally writable field, **including generated model output**, has a defined type, length, structural constraint, normalization rule, and rejection behavior enforced server-side. Includes CSRF protection on state-changing forms and transformation of non-serializable internal values at the API boundary |
| O-103 | DYNAMIC | Child-visible text is rendered with context-appropriate encoding; stored HTML, script, URL, Markdown, Unicode-control, and bidirectional-text payloads remain inert on every child-facing surface |
| O-104 | DYNAMIC | Parsing failures, malformed graphs, oversized payloads, duplicate identifiers, and recursive structures fail predictably without partial writes or internal error disclosure. Includes OS command injection and RCE paths |

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

URL parsing belongs to input handling; destination authorization belongs to egress. O-21 is owned
here rather than by SP-14 on that basis.

### SP-07 File, Object Storage, Media

| ID | Class | Check |
|----|-------|-------|
| O-22 | RUNTIME-CONFIG | Cover and avatar objects served via short-lived signed URLs or an authorizing proxy; the bucket denies public listing |
| O-23 | STATIC | Uploaded images are re-encoded server-side, EXIF stripped, and type-sniffed rather than trusted |
| O-80 | DYNAMIC | Object keys cannot be predicted or substituted to reach another family's media; authorization is checked before every signed URL is issued, not embedded in the key name |

### SP-08 Cryptography, Secrets, Key Management, Transport

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
| O-92 | MANUAL | The incident plan can trace a child-data event across edge, application, identity provider, database, queue, model provider, object storage, and client sync, and includes state breach-notification decision points, plus Art. 33/34 once EU users exist |
| O-116 | MANUAL | **AC.14.1-AC.14.3**: an AI-in-pipeline compromise playbook exists; any secret touched by a suspect workflow run is rotated automatically; agent identities can be revoked within a written, annually tested target time |

### SP-12 Data Lifecycle, Rights, Processors, Transfers

| ID | Class | Check |
|----|-------|-------|
| O-31 | MANUAL | An erasure runbook enumerates every store (Postgres, R2, Redis payloads, retained raw LLM output, offline IndexedDB on family devices, backups) and a test deletion demonstrates residue-free removal within the stated SLA |
| O-32 | STATIC | Every data class has a stated TTL with an automated reaper and evidence of its last successful run |
| O-33 | MANUAL | An actual restore into a scratch environment was performed and recorded within the last quarter |
| O-34 | DYNAMIC | A guardian can obtain a machine-readable export within the statutory window, without receiving another family's data |
| O-57 | MANUAL | Each provider is classified controller/processor/recipient with documented subprocessors, locations, retention, training-use terms, deletion support, and security commitments. COPPA additionally requires written assurances from recipients of children's data |
| O-58 | MANUAL | A transfer mechanism is recorded per non-US processor, activated on EU/UK entry (Art. 44-49) |
| O-59 | MANUAL | A DPIA is completed and revisited on trigger. Effectively mandatory on EU entry (children plus profiling plus generative AI), and several state minors' codes require the equivalent on US public launch |
| O-60 | MANUAL | An Art. 27 EU-representative determination is recorded, with reasoning |
| O-93 | STATIC | Records of processing are maintained with purposes, recipients, transfers, deletion periods, and a description of security measures |

### SP-13 Protected-Population Duties and Age-Appropriate Design

| ID | Class | Check |
|----|-------|-------|
| O-35 | STATIC | Consent records are immutable, timestamped, versioned to the exact notice text displayed, and non-repudiable. Not a timeless boolean |
| O-36 | STATIC | Age and band changes are restricted to a verified guardian and audit-logged. Age is a safety parameter, not a preference: it determines what content the pipeline will send a child |
| O-37 | STATIC | Kid-scoped response schemas are field-allowlisted and diffed against the OpenAPI schema on contract change |
| O-38 | MANUAL | The published privacy notice's third-party list reconciles against the measured egress inventory. Divergence is an FTC Act §5 misrepresentation, not only a privacy gap |
| O-61 | MANUAL | A written children's-data security program exists with a named coordinator, annual risk assessment, ongoing safeguard testing, and annual evaluation (COPPA §312.8) |
| O-62 | STATIC | The data retention policy states purpose, business need, and a specific deletion timeframe, and is **published directly in the online privacy notice**; a link to a separate policy does not satisfy the rule (COPPA) |
| O-94 | DYNAMIC | Child-facing defaults minimize visibility, sharing, profiling, location, personalization, and persistent identifiers; weakening a protection requires an attributable decision (state minors' design codes; UK AADC and GDPR Art. 25 on EU entry) |
| O-95 | MANUAL | Notices and error messages are tested separately for roughly ages 5-7, 8-10, and 11-12, not with one adult notice. Overlaps the WCAG duty |
| O-96 | MANUAL + DYNAMIC | The child is told, age-appropriately, what a guardian or administrator can see and do |
| O-97 | MANUAL | A jurisdiction-trigger matrix maps each child's residence to the regimes it activates, per the spine's T4 rule. Owns the state-comprehensive-privacy and minors'-design-code determinations |
| O-98 | *deferred, R2* | App-store accountability: designate an age rating, ingest store-provided age and consent signals via the platform API, re-trigger parental consent on significant change (TX SB 2420, UT, LA, AL) |
| O-99 | *deferred, R2* | Apple Kids Category and Google Play Families pre-submission checklist, reviewed quarterly with captured page dates |
| O-117 | STATIC + DYNAMIC | A country-of-residence signal is recorded at account creation and is queryable per account. Without it the DSA Art. 2(1) and GDPR Art. 3(2) targeting tests cannot be answered, and a market can be excluded by design rather than by hope. Cheap pre-launch, requires a re-consent campaign afterwards |
| O-118 | STATIC | The five structures that keep the product outside DSA Art. 3(i) hold: admin-gated connection creation, dual guardian consent, no discovery surface, no free text between users, directional and revocable connections. A change to any one re-opens the classification and must be an attributable decision, not a refactor. **Failure oracle**: a test that creates an active connection without two distinct guardian consents must fail |
| O-119 | STATIC | The guardian account carries an adulthood attestation signal with a timestamp. Every age regime that can attach at R2 locates its duty on the adult account, not the kid profile; today only kid profiles carry age data. Trivial pre-launch, requires backfill against live accounts afterwards |

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

## What the source checklist missed

The originating 10-item "common issues in vibe coded apps" scorecard maps to: SP-08, SP-01, SP-02
(one probe), SP-03, SP-04 (HTTP rate limiting only), SP-05 (localStorage only), SP-05 and SP-09,
SP-11 (one facet), SP-03, SP-10 (one facet).

**Eight of seventeen categories receive zero questions**: SP-06, SP-07, SP-12, SP-13, SP-14, SP-15,
SP-16, SP-17. It contains no privacy question of any kind, nothing about the LLM pipeline, and
nothing about whether its own checks can fail.

Of the "50 most common errors in vibe-coded apps" source, only about 18 items are
security-checkable; the remainder are ordinary build and runtime bugs. They were not forced into
security categories. Both web sources were treated as untrusted data per OWASP LLM01, and neither
contained content directed at an automated reader.

## Reconciliation record

Three external deep-research runs, 2026-08-02, all treated as untrusted data and verified against
primary sources where a claim was load-bearing. All three disclosed or exhibited anchoring on the
sixteen-category spine they were shown; convergence with it is partly contaminated and divergence
from it is the higher-signal part.

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
| Jurisdiction triggers keyed to subject residence | 1 of 3, adopted on merit, generalized into the spine's T4 |

The merge of session into identity was initially resisted here because this system has two
independent session lifecycles. That is an argument for more rows, not for a separate heading, so
it was accepted with both subsections made mandatory.

### Rejected, with the evidence

- **"Remove the process items from the register."** Contradicted by Art. 32(1)(d), which the same
  report quoted correctly in its own factual section, and by COPPA §312.8. Removal recreates the
  maintainer's stated failure mode: not done, and not in the plan.
- **"Ignore cloud and container baselines, the vendor owns it."** Refuted by AISVS's own scope
  statement, which names CIS Benchmarks and NIST SP 800-53/190 as the deferral target for
  infrastructure hardening, and by A9: the origin is self-managed hardware with a confirmed bypass.
- **"Cut cryptography and secrets."** The secrets half is not vendor-managed, and no CI-side secret
  scanning exists anywhere in the repository.
- **"Cut availability and recovery."** Art. 32(1)(c) makes restorability binding.
- **"Merge input validation with client-side data at rest."** Conflates DOM output encoding with
  children's names in IndexedDB: no shared threat, method, or owner.

### Corrected against primary documents

One run recommended AISVS on the grounds that it covers privacy and contains a human-oversight
chapter. Reading AISVS 1.0 directly: privacy operations are in its **explicit exclusion list**, and
there is no human-oversight chapter. The recommendation survives; the reasons given for it did not.
The valuable finding no run reported is **Appendix C**, whose full text (fetched 2026-08-02) has
fourteen sections and roughly sixty level-tagged requirements, three of which cover the AI-tooling
attack surface on the development pipeline.

A web search summary during this work returned a confidently wrong list of states with
comprehensive privacy laws, internally inconsistent (claimed 20, listed 21, included states that
have none). The verified figure, from the cited tracker, is **20 states as of Feb 2026 counting
Florida's narrower scope**. This is why the spine requires state enumerations to carry a date and
source, and why O-108 owns the refresh.

### Prompt defects worth recording

Two facts were sanitized out of the research brief, and both produced confidently wrong conclusions:
the origin is self-managed hardware behind a third-party edge, not fully managed cloud; and ADR-016
cross-family recommendation sharing exists, which bears directly on DSA Art. 28 classification.
Over-sanitizing a brief does not produce a vaguer answer, it produces a confident answer to a
different question.

## Remaining prerequisites

1. **Make this register a namespace `scripts/check_work_linkage.py` can see.** This is the item
   that decides whether the rows below are audited or merely written down, and it is the only
   mechanism in the repo that enforces the contract at the top of this file.

   The obstacle is not a missing manifest entry. `plan-manifest.toml` contains `[phases]`,
   `[rungs]`, and `[status_vocabulary]`, and those are the only sections the checker reads from it.
   There is no namespace registry. All four existing namespaces (`UW-[A-M]NN`, the debt register's
   `C/GS/U/T/P/SL` shapes, the capability register's `[KGAS]NN`, and `AL-NNN`) are hardcoded in the
   checker as a path constant plus row and citation regexes.

   Two routes were considered. Hardcode a fifth namespace, matching precedent and repeating the
   work for the sixth; or add a `[namespaces]` table to the manifest declaring prefix, register
   path, and linkage rule, and make the checker data-driven. **Decided 2026-08-02: the second.**
   The rationale is the manifest's own stated reason for existing: it was created so the phase
   vocabulary would be "read from the manifest rather than hardcoding it", after the duplication
   between a Python frozenset and a roadmap scrape proved unmaintainable. The four namespaces are
   in that same pre-manifest state today.

   The `SQ-*` story-structure track is blocked behind the identical obstacle and clears with the
   same change, so the two should land together. Note that
   `story-structure-improvement-plan.md` section 11 still attributes the block to the manifest not
   existing on main, which stopped being true at `fc36b51a`; retire that paragraph in the same
   change.

2. **Rename `O-nn` to `SEC-nnn` when the namespace lands.** The identifiers are provisional. `O-01`
   reads as a zero and the letter carries no meaning. `SQ-*` was previously suspected of colliding
   with these; it does not, being an unrelated story-structure track.
3. **Confirm no ASVS 5.0.x patch has shipped since 5.0.0.**
4. **Confirm AISVS C8 applicability**: whether `diversity/` uses embeddings or only structural and
   lexical similarity.
5. **Counsel scoping decision on UK OSA only.** DSA Art. 28 is resolved above.
6. ~~Decide the row budget.~~ **Decided 2026-08-02: 81 rows accepted, no trimming.** Recorded
   because a budget silently exceeded is indistinguishable from one never considered.
7. **Promote the spine.** `assurance-spine.md` is written to be lifted into `~/.claude/standards/`
   so other projects instantiate it rather than rediscovering it.

## Initial-build commitments

Approved 2026-08-02. These are the only rows promoted out of the general register into
pre-launch build work, because each is cheap now and requires a re-consent or backfill campaign
once real accounts exist.

| Row | Commitment | Why it cannot wait |
|---|---|---|
| O-117 | Country of residence captured at signup, queryable per account | Answers the DSA Art. 2(1) and GDPR Art. 3(2) targeting tests and lets the UK and EU be excluded by design. For the UK specifically the gate is necessary but not sufficient: OSA s.4 also finds links through capability-plus-material-risk, so the gate holds only in combination with the O-118 structures |
| O-119 | Guardian adulthood attestation with timestamp | Every age regime reachable at R2 attaches its duty to the adult account; today only kid profiles carry age data. Scope is deliberately **attestation, not verification**: DSA Art. 28(3) forecloses an obligation to collect additional personal data to detect minors, and the app-store age signals at O-098 supersede this at R2 |

The country field is itself personal data and inherits the minimization, retention, and access
duties in SP-12.
