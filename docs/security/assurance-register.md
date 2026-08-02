---
title: "Security and Privacy Assurance Register"
schema_type: common
status: published
owner: core-maintainer
purpose: "Register of security and privacy assurance items for CYO Adventure, spined on OWASP
  ASVS 5.0.0 plus GDPR Art. 32 plus curated content for children's privacy and the LLM
  generation pipeline, recording for each item how it is verified and whether an existing gate
  already covers it."
tags:
  - security
  - compliance
  - reference
---

Drafted: 2026-08-02.
Companion to: [`control-inheritance.md`](control-inheritance.md), which records inherited
posture in out-of-repo control planes. This file records assurance items and their verification
methods.

## Contract

This register does not block releases. That is a deliberate decision by the maintainer: an item
must have **a phase home and a named verification method**, not a passing gate. The defect this
register detects is *an item with no phase home*, not *an item with a failing check*.

Row schema: `ID | spine category | ASVS ref | Art. 32 ref | class | verification method |
existing coverage | phase home | owner | last verified | status`.

Verification classes:

| Class | Meaning |
|-------|---------|
| STATIC | Assertable from source by a linter, type checker, SAST pass, schema comparison, or unit test |
| DYNAMIC | Requires a running application: DAST, probe, live request |
| RUNTIME-CONFIG | Lives in a deployed control plane (see `control-inheritance.md`) |
| MANUAL | Requires human judgment or attestation; carries a cadence and a named owner, never a bare checkbox |

Automated verifications run **report-only**: they write a finding into the status column and a
scheduled summary, and exit zero. That preserves the no-blocking decision while still moving the
majority of the register off human memory.

## Prerequisites

Three things must happen before rows in this file are machine-visible. They are prerequisites,
not follow-ups.

1. **Reconcile the ASVS 5.0.0 chapter table below against the published document.** The
   structural changes in 5.0.0 are established (encoding promoted to the front, authorization
   split from access control, dedicated chapters for self-contained tokens and for OAuth/OIDC, a
   new web-frontend chapter, WebRTC added, the old standalone architecture chapter dissolved).
   The exact chapter ordinals and titles below are **inferred and unverified**. Publishing a
   spine on an unverified chapter list would reproduce the failure mode this register exists to
   catch.
2. **Register the `SQ-*` namespace in `plan-manifest.toml`.** No such namespace exists on main,
   so `scripts/check_work_linkage.py` cannot see these rows at all.
3. **Reconcile numbering against the roughly 24 `SQ-*` items already drafted elsewhere.** The
   `O-nn` identifiers used below are provisional precisely to avoid claiming IDs that may already
   be taken.

## The spine

Sixteen categories. Every ASVS chapter maps to at least one; every Art. 32 clause maps to at
least one.

| ID | Category | ASVS 5.0.0 (unverified ordinals) | Art. 32 and adjacent |
|----|----------|----------------------------------|----------------------|
| SP-01 | Identity and Authentication | V6, V10 | 32(1)(b) |
| SP-02 | Session Lifecycle and Token Handling | V7, V9 | 32(1)(b), 32(4) |
| SP-03 | Authorization and Family Tenancy Isolation | V8, V4 | 32(1)(b), 32(2) |
| SP-04 | Input Validation, Encoding, Injection | V1, V2 | 32(1)(b) |
| SP-05 | Business Logic and Abuse Resistance | V2, V4 | 32(1)(b) |
| SP-06 | Web Frontend and Client-Side Data at Rest | V3, V14 | 32(1)(a), 32(2) |
| SP-07 | API Surface, Egress, and SSRF | V4, V12 | 32(1)(b) |
| SP-08 | File, Object Storage, and Media | V5, V8 | 32(1)(a), 32(1)(b) |
| SP-09 | Cryptography, Secrets, Key Management | V11, V13 | 32(1)(a) |
| SP-10 | Secure Communication and Edge Trust Boundary | V12, V13 | 32(1)(a), 32(1)(b) |
| SP-11 | Configuration, Build, and Supply Chain | V13, V15 | 32(1)(b), 32(1)(d) |
| SP-12 | Logging, Audit Integrity, Alerting, Errors | V16 | 32(1)(b), 32(1)(d); Art. 33 |
| SP-13 | Data Protection, Retention, Subject Rights | V14 | 32(1)(a), 32(1)(c); Art. 5(1)(e), 15, 17 |
| SP-14 | Children's Privacy and Consent Assurance | *(none)* | 32(2); Art. 8, 25 |
| SP-15 | Generation Pipeline Assurance (LLM) | *(none)* | 32(1)(b), 32(2) |
| SP-16 | Availability, Resilience, Recovery | V13, V4 | 32(1)(b), 32(1)(c) |

ASVS V17 (WebRTC) is recorded as **explicitly not applicable**: the product has no peer-to-peer
media. Re-review trigger: any proposal for voice or video reading features. Recorded as an N/A
row rather than silently dropped.

**Three categories have no ASVS chapter.** SP-14 and SP-15 have none at all, and ASVS barely
touches SP-16's availability half. For a children's application with an LLM content pipeline,
roughly a fifth of the real risk surface is outside ASVS. A register spined only on ASVS would be
structurally blind exactly where this product is most exposed. This is the evidence for the
maintainer's requirement that the spine cover ASVS **and** GDPR **and** curated operational
content.

Art. 32(1)(d) requires "a process for regularly testing, assessing and evaluating the
effectiveness" of security measures. This register is itself that process, so its existence is a
control, not merely a tracker for controls.

## What the source checklist missed

The originating 10-item "common issues in vibe coded apps" scorecard maps as: 1 to SP-09, 2 to
SP-01, 3 to SP-03 (one probe), 4 to SP-04, 5 to SP-05 (HTTP rate limiting only), 6 to SP-06
(localStorage only), 7 to SP-06 and SP-10, 8 to SP-12 (one facet), 9 to SP-04, 10 to SP-11 (one
facet).

**Six of sixteen categories receive zero questions**: SP-02, SP-08, SP-13, SP-14, SP-15, SP-16.
Five more receive a single-facet touch that misses the dominant risk in the category. The list
contains no privacy question of any kind, and no question about the LLM pipeline.

## Existing gate coverage

Audited 2026-08-02 against twelve areas drawn from external reviewer checklists. Verdicts below
are evidence-backed; the "can it fail" column is the one that matters, because a gate that cannot
fail is worse than no gate.

| Area | Verdict | Can it fail? |
|------|---------|--------------|
| Privacy / RLS correctness | PARTIAL | Yes in CI, but RLS is a no-op in production (see below) |
| Authentication edge cases | PARTIAL | Yes; role-change and concurrent-session slices absent |
| Duplicate / divergent workflows | PARTIAL | Mostly no |
| DB structure and field types | COVERED | Yes |
| Query efficiency / N+1 | PARTIAL | Yes for 2 of 28 routers |
| Error handling and logging | PARTIAL | Yes; one test pins a gap rather than closing it |
| Hardcoded credentials / keys | PARTIAL | Local pre-commit only; no CI secret scan at all |
| Security response headers | PARTIAL | Yes for FastAPI; no gate on the nginx edge |
| Auth rate limiting / brute force | PARTIAL | Yes for IP-based; no per-account protection exists |
| Password reset / enumeration | PARTIAL | Yes on PR, not in the merge queue |
| Client-side data at rest | **NOT COVERED** | Nothing to fail |
| Frontend bundle contents | **NOT COVERED** | Nothing to fail |

### Cross-cutting gate defects

These invalidate or weaken multiple rows at once and should be treated as the first tranche of
work.

- **RLS is inert in production.** `core/database.py:265-268` records that the application
  connects as the Postgres owner pre-cutover, and RLS never applies to a table's owner, making
  `apply_family_rls_context` a no-op. The enforcement suite forces the `cyo_api` role in its own
  fixture, so it structurally cannot observe that production bypasses the mechanism entirely. No
  gate asserts the deployed `DATABASE_URL` resolves to `cyo_api`. ADR-022 remains `proposed` and
  the ADR-021 cutover is a manual runbook step. Note this is a different question from the
  PostgREST anon path, which is verified closed in `control-inheritance.md` Plane B; the gap here
  is that RLS provides no defence-in-depth against an application-layer authorization bug.
- **Scoping exists for 3 of ~20 RLS tables.** `20260724120000_scoped_rls_tier1_family_scoping.sql`
  scopes `child_profile`, `story_request`, `device_grant`. The other 17 carry a blanket
  `USING(true)` that filters nothing; their privacy rests entirely on the FastAPI layer.
- **The pre-push hook tier does not exist.** `.git/hooks/` contains only `pre-commit`, and
  `default_install_hook_types` is absent from `.pre-commit-config.yaml`. Nine hooks configured
  `stages: [pre-push]` have never run and cannot run: `detect-secrets`, `bandit-full`,
  `basedpyright`, `frontend-typecheck`, `yamllint`, `qlty-check`, `qlty-full`, `pydoclint`,
  `markdownlint`. CI independently recovers basedpyright, yamllint, and pydoclint. It does not
  recover detect-secrets, gitleaks-via-qlty, or qlty smells.
- **pre-commit.ci is not installed.** No such check run exists on `main`, so the `ci:`/`skip:`
  block at `.pre-commit-config.yaml:12-15` is inert and there is no hosted fallback. No workflow
  runs `pre-commit run --all-files`.
- **No CI-side secret scanning exists.** Across all workflows there is no trufflehog, gitleaks, or
  detect-secrets invocation. Secret detection is one local pre-commit hook, bypassable by
  `--no-verify` or by a clone that never ran `pre-commit install`.
- **CodeQL does not run.** `CLAUDE.md` states that `security-analysis.yml` runs CodeQL. It does
  not; that workflow runs Bandit and OSV-Scanner only. The only `github/codeql-action` uses
  repo-wide are `upload-sarif` steps. There is no SAST over the TypeScript tree at all. The
  documentation must be corrected as well as the gap closed.
- **Source maps are served in production.** `frontend/vite.config.ts:188` uses
  `sourcemap: 'hidden'`, which still emits `.map` files and only omits the `sourceMappingURL`
  comment; `frontend/Dockerfile:101` copies `dist/` wholesale; and the asset `location` regex at
  `frontend/nginx.conf:69` does not cover `.map`, so those files fall through to `location /` and
  are served at predictable URLs. The inline comment claiming production source is not exposed is
  true only against a casual devtools open.
- **SonarCloud cannot gate a PR.** `sonarcloud.yml:13-36` triggers on push to main/develop and
  `workflow_dispatch` only, and `:68` sets `fail-on-quality-gate` only for `push`, so it fails
  after merge. Scope is narrowed twice: CI overrides `sonar.sources=src`, excluding the entire
  frontend tree from duplication analysis, and `sonar-project.properties:76` excludes tests.
- **Merge-queue coverage holes.** The `frontend` and `frontend-e2e` jobs carry
  `if: github.event_name != 'merge_group'` (`ci.yml:156`), and `ci-gate` treats `skipped` as pass
  (`ci.yml:969-971`), so a merge-queue-only regression in those suites is never re-checked. The
  `ci-gate` `needs` list (`ci.yml:935`) also omits `diversity`, `api-tests`, and
  `coverage-upload`, which therefore cannot block the gate.
- **Vulture dead-code detection is warn-only**, emitting `::warning::` and continuing.
- **One test pins a gap rather than closing it.** `tests/unit/test_logging_security.py:262`
  asserts that `api/deps.py` has no logger at all, so there is zero observability on
  authentication failures, and the gate enforces the absence. It is a gap marker, not coverage.
  This is legitimate as a deliberate pin, but it must not be counted as a passing control.

## Register rows

Forty-nine items, provisional IDs. Class distribution: 26 STATIC (53%), 9 DYNAMIC (18%),
8 RUNTIME-CONFIG (16%), 6 MANUAL (12%). 71% is machine-assertable from artifacts the project
already produces.

Two honest qualifications on that figure. "STATIC" means assertable, not off-the-shelf: roughly a
third of the static rows need a purpose-written assertion. And several rows are STATIC only
because migrations are committed SQL rather than dashboard clicks, which suggests a lever, moving
RUNTIME-CONFIG rows into version control converts them to STATIC. `O-22` (R2 bucket policy) and
`O-46` (Redis exposure) are the two clearest candidates.

### SP-02 Session Lifecycle and Token Handling

| ID | Class | Check |
|----|-------|-------|
| O-01 | DYNAMIC | Revoking a device grant terminates in-flight child sessions and blocks reissue within a stated bound. Known gap pinned at `tests/integration/test_child_sessions.py:792`: a revoked grant leaves a minted child token valid up to 12h |
| O-02 | STATIC | JWT verification rejects wrong `iss`, wrong `aud`, `alg` substitution, unknown `kid`, and refreshes JWKS on rotation. Largely covered by `tests/unit/test_oidc_verification.py` |
| O-03 | STATIC | Adult elevation has absolute and idle timeouts and is not persisted to durable storage |
| O-04 | STATIC | Offline mode enforces a maximum offline validity window and forces server re-verification on reconnect |

### SP-03 Authorization and Family Tenancy Isolation

| ID | Class | Check |
|----|-------|-------|
| O-05 | DYNAMIC | A guardian in family A receives 403/404 for every resource ID from family B, enumerated across all resource-bearing routers |
| O-06 | DYNAMIC | Cross-family recommendation payloads (ADR-017) contain only whitelisted fields, never child identity or reading history |
| O-07 | DYNAMIC | A guardian-only token is rejected by every `/admin` route and every moderation-threshold mutation |
| O-08 | DYNAMIC | Every secondary object reference (storybook version, node, assignment, cover asset) is authorization-checked at the leaf, not inherited from a parent check |
| O-09 | RUNTIME-CONFIG | Background workers connect with a least-privilege role subject to RLS, not the service key. Blocked on the ADR-021 cutover |

### SP-05 Business Logic and Abuse Resistance

| ID | Class | Check |
|----|-------|-------|
| O-10 | STATIC | Story-request creation enforces a per-family windowed generation budget independent of HTTP rate limits |
| O-11 | STATIC | The publish state machine is the only writer of reader-visible state, and post-approval edits force re-approval |
| O-12 | DYNAMIC | Concurrent approve and concurrent grant-redeem attempts converge on a single terminal state under load |
| O-13 | DYNAMIC | Flag submission is idempotent per actor-target pair and rate-shaped |

### SP-15 Generation Pipeline Assurance

| ID | Class | Check |
|----|-------|-------|
| O-14 | STATIC | Untrusted intake text is passed in a data position with delimiters, never concatenated into system-prompt position |
| O-15 | STATIC | Any content re-entering a later pipeline stage (series continuation, mutated skeletons) is re-classified before reuse |
| O-16 | STATIC | Every provider path (Anthropic, OpenRouter, Ollama, Modal, fallback) terminates in the identical validator plus moderation gate, with no provider-specific shortcut |
| O-17 | STATIC | **No reader-visible node body exists without both a passing validator report and a human approval record**, enforced in the read path and confirmed by a data invariant query |
| O-18 | MANUAL | A maintained adversarial corpus is run against live thresholds each release and the pass rate is recorded with a trend |
| O-19 | RUNTIME-CONFIG | Worker egress is allowlisted to approved provider endpoints and child identifiers are pseudonymized before crossing the boundary |
| O-20 | MANUAL | Each enabled provider has a recorded DPA/ZDR posture and a pinned model identifier |

O-17 is the highest-value assertion in this register. Its violation is a child-safety incident
rather than a security finding, which is why it is the one item worth a later conversation about
enforcement in the read path itself. That would be a product control rather than a CI gate, and
therefore compatible with the no-blocking decision. Not proposed now.

### SP-07 API Surface, Egress, SSRF

| ID | Class | Check |
|----|-------|-------|
| O-21 | STATIC | All outbound URL fetches use an allowlist and reject link-local, metadata, and private ranges **after** DNS resolution. Known defect: `middleware/security.py` `_is_blocked_url` returns not-blocked when host parsing fails |

### SP-08 File, Object Storage, and Media

| ID | Class | Check |
|----|-------|-------|
| O-22 | RUNTIME-CONFIG | Cover and avatar objects are served via short-lived signed URLs or an authorizing proxy, and the bucket denies public listing |
| O-23 | STATIC | Uploaded images are re-encoded server-side, EXIF stripped, and type-sniffed rather than trusted |

### SP-11 Configuration, Build, and Supply Chain

| ID | Class | Check |
|----|-------|-------|
| O-24 | RUNTIME-CONFIG | Released container digests carry verifiable provenance and deployment pins by digest, not tag |
| O-25 | STATIC | All actions pinned by commit SHA, no `pull_request_target` checking out untrusted head, no secret reachable from a fork-triggered job |
| O-26 | STATIC | The client drift job runs on every contract change and lockfile integrity is verified at install |
| O-27 | MANUAL | **Every verification method in this register has a deliberate failing fixture proving it can report a failure** |

O-27 is the register's own health check. This repository has already produced multiple distinct
silent-pass failures. A register whose checks cannot fail reproduces the exact pathology it exists
to prevent, so canary work belongs in the same phase as the first batch of automated
verifications, not after it.

### SP-12 Logging, Audit Integrity, Alerting, Errors

| ID | Class | Check |
|----|-------|-------|
| O-28 | STATIC | The events table grants no UPDATE or DELETE to the application role, and entries carry a chained digest |
| O-29 | STATIC | An emitted-field allowlist test asserts no child identifier, story body, or token appears in log output |
| O-30 | RUNTIME-CONFIG | Named detections exist for approval-bypass attempts, 403 spikes, and moderation-provider outage, each with a routed recipient |

### SP-13 Data Protection, Retention, Subject Rights

| ID | Class | Check |
|----|-------|-------|
| O-31 | MANUAL | An erasure runbook enumerates every store (Postgres, R2, Redis payloads, retained raw LLM output, offline IndexedDB on family devices, backups) and a test deletion demonstrates residue-free removal within the stated SLA |
| O-32 | STATIC | Every data class has a stated TTL with an automated reaper and evidence of its last successful run |
| O-33 | MANUAL | An actual restore into a scratch environment was performed and recorded within the last quarter |
| O-34 | DYNAMIC | A guardian can obtain a machine-readable export of their family's data through a defined path within the statutory window |

### SP-14 Children's Privacy and Consent Assurance

| ID | Class | Check |
|----|-------|-------|
| O-35 | STATIC | Consent records are immutable, timestamped, versioned to the exact notice text displayed, and non-repudiable |
| O-36 | STATIC | Age and band changes are restricted to a verified guardian and written to the audit log. Age is a safety parameter here, not a preference: it determines what content the pipeline will send a child |
| O-37 | STATIC | Kid-scoped response schemas are field-allowlisted and the allowlist is diffed against the OpenAPI schema on contract change |
| O-38 | MANUAL | The published privacy notice's third-party list reconciles against the measured egress inventory |

### SP-06 Web Frontend and Client-Side Data at Rest

| ID | Class | Check |
|----|-------|-------|
| O-39 | STATIC | Offline stores are keyed per profile, purged on logout and grant revocation, and hold no auth secret. Currently NOT COVERED: no allowlist test over object stores or `localStorage` keys |
| O-40 | STATIC | The service worker has a versioned kill-switch and never caches authenticated responses in a profile-agnostic key |
| O-41 | DYNAMIC | Switching profiles evicts the previous profile's cached content and player state |

`personalization_values` in IndexedDB holds children's real first names, sibling names, and
kinship labels. Nothing currently asserts a policy over client storage, and no lint rule restricts
`localStorage` use.

### SP-01 Identity, Recovery, Enumeration

| ID | Class | Check |
|----|-------|-------|
| O-42 | RUNTIME-CONFIG | Supabase auth settings enforce non-enumerable responses and require verified email before identity linking. Invisible to any source-based review because auth is delegated |
| O-43 | STATIC | No self-service path grants `is_admin`; elevation is out-of-band and audit-logged |

### SP-16 Availability, Resilience, Recovery

| ID | Class | Check |
|----|-------|-------|
| O-44 | STATIC | Every expensive operation (generation, cover art, full-graph validation, re-screen) is queued with bounded concurrency and a per-tenant cap, never executed on the request thread |
| O-45 | STATIC | The worker re-derives and re-validates authorization from the database at job start rather than trusting the payload |
| O-46 | RUNTIME-CONFIG | Redis is unreachable from outside the compose network and payloads carry identifiers rather than PII |

### SP-10 Secure Communication and Edge Trust Boundary

| ID | Class | Check |
|----|-------|-------|
| O-47 | STATIC | Forwarded headers are honored only from the known proxy hop, and client-supplied correlation IDs are sanitized before logging |
| O-48 | RUNTIME-CONFIG | The origin firewall accepts only edge source ranges or requires mTLS from the edge. **This is A9 in `control-inheritance.md`, confirmed open** |

### Cross-cutting

| ID | Class | Check |
|----|-------|-------|
| O-49 | STATIC | Every gate defaults to not-approved on exception, verified by a fault-injection test per gate. For this product a fail-open moderation gate is the worst possible outcome |

## External checklist mapping

Five external sources have been folded in. The four already-analysed operational sources
contribute the twelve gate-coverage areas above. Two web sources were extracted separately and
deduplicated to 22 distinct concerns from 55 raw items; both were treated as untrusted data per
OWASP LLM01, and neither contained content directed at an automated reader.

Concerns from those two sources that are **not** otherwise represented, and their spine homes:

| Concern | Spine | Note |
|---------|-------|------|
| Orphaned endpoints left live after their UI was removed, or generated mid-session and never inventoried | SP-03, SP-05 | Material for this repo: 28 routers |
| OAuth callback URL matches the production domain | SP-01 | RUNTIME-CONFIG; a control-plane row |
| Webhook signature verification uses production, not test-mode, secrets | SP-09 | |
| CSRF protection on state-changing forms | SP-01 | Absent from the 10-item list |
| Password-reset token expiry bounded | SP-01 | Absent from the 10-item list |
| Non-serializable internal values transformed before crossing the API boundary | SP-04 | |
| Database connections pooled and released under concurrent load | SP-16 | |
| OS command injection and RCE paths tested | SP-04 | |
| Third-party integration data leakage tested | SP-07 | |
| No debug or development settings exposed in production | SP-11 | Interacts with `ENVIRONMENT=local` silently disabling rate limiting |
| Re-test after every AI-assisted change; treat each deployment as a new risk event | *(process)* | See below |

The last row exposed a genuine gap in the spine: five items from the Invicti source are
process and SDLC cadence rules rather than vulnerability classes, and had to be mapped to
configuration as the nearest fit. The spine needs a **process category** rather than pretending
that fit is clean. Deferred pending the ASVS reconciliation in Prerequisites, since ASVS 5.0.0
may already provide a home.

One observation on source quality worth recording so it is not re-litigated: of the "50 most
common errors" source, only about 18 items are security-checkable. The remainder are ordinary
build and runtime bugs (hydration mismatches, hook rules, type errors, cold starts). It was not
forced into security categories.
