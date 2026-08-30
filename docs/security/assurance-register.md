---
title: "Security and Privacy Assurance Register"
schema_type: common
status: published
owner: core-maintainer
purpose: "CYO Adventure's instantiation of the portable assurance spine: which of the seventeen
  categories and which regulatory regimes apply to this product, the audited state of existing
  gates, and the register rows with their verification methods. Phase homes are declared but not
  yet assigned; see the Contract section."
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

Applied to this document as it currently stands, that contract convicts it: **every one of the 122
rows carries `Phase home: unassigned`, so by the register's own definition all 122 are open
defects.** This is stated rather than left to be inferred, because a register that defines a defect
and then quietly exhibits it everywhere is the hollow artifact SP-17 is about. It is not a reason
to soften the definition. Nothing can be assigned a phase home until the `UW-*` linkage in
prerequisite 1 can cite these IDs, which is why that prerequisite is first and why this file claims
no verification status beyond *drafted*.

## Category applicability

All seventeen categories apply. None is N/A for this product, which is itself worth noting: a
children's application with an LLM content pipeline, offline sync, a self-managed origin, and
planned store distribution touches the whole spine.

Sub-scope exclusions recorded rather than dropped:

| Excluded | Category | Reason | Reassessment trigger |
| --- | --- | --- | --- |
| ASVS V17 WebRTC | SP-03, SP-06 | No peer-to-peer media | Any voice or video reading feature |
| AISVS C1 training data | SP-14 | No training or fine-tuning; hosted inference only | Any fine-tune or LoRA |
| AISVS C10 MCP | SP-06 | MCP is development tooling, not in the product | Any MCP surface shipped to users |
| AISVS C8 embeddings | SP-02, SP-12 | **Verified 2026-08-02.** `diversity/` computes hand-built structural feature vectors compared by Canberra distance, and cosine similarity over token-count `Counter` objects, which is a bag-of-words measure. It imports no ML or embedding library and holds no learned representation, so there is no embedding or vector store to govern | Any introduction of a learned embedding, a vector store, or an ANN index anywhere in the pipeline |
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
| --- | --- | --- |
| **FTC Act §5** | Any consumer-facing product. Security and privacy claims in the notice become enforceable representations | O-38, O-62, O-94 |
| **COPPA** (compliance date 22 Apr 2026, therefore live) | Children under 13, child-directed service | O-35, O-36, O-61, O-62, O-31, O-122, O-123, O-124, O-125 |
| **State breach notification** | The regime attaches with the first non-household user; the notice duty itself fires on discovery of a qualifying breach | O-92 |
| **ADA / WCAG** | Consumer-facing; also overlaps the age-appropriate-design duty to be understandable | O-95 |

### Regimes that attach at a named trigger

Recorded now with the trigger, so that crossing it is a scheduling decision rather than a
discovery. This is the same treatment GDPR gets: written down before it binds.

| Regime | Trigger | Status |
| --- | --- | --- |
| **State comprehensive privacy** (20 states as of Feb 2026) | First user outside the operator's household in a covered state, above any applicable threshold | O-97 jurisdiction matrix owns the determination |
| **State minors' design codes** (CA AADC, MD, NE, VT, CT, TX SCOPE, FL HB 3, UT) | Public launch. Track enactment and litigation status separately; several are partially enjoined | O-94, O-97 |
| **State information-security statutes** (NY SHIELD Act, Massachusetts 201 CMR 17.00) | Not residency alone: both statutes key on a defined data class (NY GBL 899-aa(1) "private information"; MA 201 CMR 17.02 "personal information"), each a name plus a specific sensitive identifier: SSN, driver's license/state-ID number, or a financial-account, credit-card, or debit-card number, **with or without** an accompanying security code, access code, PIN, or password (neither statute requires the credential; a bare card or account number combined with a name is already covered), plus biometric data, or, for NY only, a username/email combined with a password or security question and answer. T1 records no SSN/DL/financial-account/card/biometric data; T1's guardian email and auth identity is the one class that plausibly meets NY's username-plus-credential prong, an open question O-120 records rather than resolves. "First NY or MA resident outside the operator's household" is this project's own internal readiness marker, not a statutory threshold; neither statute has a company-size or record-count floor | O-120. Distinct from O-97's comprehensive-privacy/design-code determination and from O-61's COPPA-scoped, children-only security program: SHIELD and 201 CMR protect residents' private/personal information as each statute defines it, not "all" data about them |
| **App store accountability acts** (TX SB 2420, UT, LA, AL) | Store distribution at R2/R3. Duties land on the **developer**: age rating, ingest store age and consent signals, re-trigger consent on significant change | O-98 |
| **App store policies** (Apple Kids, Google Play Families) | Store submission | O-99 |
| **GDPR / UK GDPR** | First EU or UK child or guardian | O-57 to O-60, O-93, O-34, O-121 (Art. 8 child-consent age, added post-2026-08-02), O-125 (Art. 28/44-49, added 2026-08-10) |
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
still worth considering at public launch), NIS2, DORA, DMA, Data Act, eIDAS 2 (no trigger),
**NYDFS Part 500 / 23 NYCRR 500** (not a "Covered Entity" under the regulation's own authorization
test, 23 NYCRR 500.1: "any person operating under or required to operate under a license,
registration, charter, certificate, permit, accreditation or similar authorization under the
Banking Law, the Insurance Law or the Financial Services Law." This product holds none of those
authorizations; "not a financial-services sector business" is directionally right but not the
regulation's actual test, so cite the authorization requirement, not the sector, when this row is
next revisited), **California SB-327** (Cal. Civil Code §§ 1798.91.04-1798.91.06; not a
manufacturer of a physical connected/IoT device, the product is software-only).
Each carries the obvious reassessment trigger: the fact that made it N/A changing (for NYDFS, the
product itself becoming licensed, registered, or chartered under NY Banking, Insurance, or
Financial Services Law, not merely "adding a DFS-licensed offering" as a feature; for SB-327,
manufacturing or white-labeling a physical connected device).

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
| --- | --- | --- |
| Admin-gated connection creation | `api/family_connections.py` `_require_admin` | An auto-accepting invite link is exactly Recital 14's "admitted without a human decision" |
| Dual guardian consent, both sides | `_is_active` requires both timestamps | One-sided push weakens the closed-group characterisation |
| No discovery surface | absence of any family or profile search | A directory makes the recipient set potentially unlimited at point of search |
| No free text between users | whitelisted recommendation fields only | Highest-cost reversal: converts provider content into user content and engages Art. 16, 17, and 20 plus the OSA illegal-content duties at once |
| Directional and revocable | revoke deactivates immediately | Supports the closed-group reading |

**Still open.** Is an EU representative required under Art. 27 when EU users are first admitted.

## Existing gate coverage

Audited 2026-08-02 against twelve areas. The "can it fail" column is the one that matters.

| Area | Verdict | Can it fail? |
| ------ | --------- | -------------- |
| Privacy / RLS correctness | PARTIAL | Yes in CI, but RLS is a no-op in production |
| Authentication edge cases | PARTIAL | Yes; role-change and concurrent-session slices absent |
| Duplicate / divergent workflows | PARTIAL | Mostly no |
| DB structure and field types | COVERED | Yes |
| Query efficiency / N+1 | PARTIAL | Yes for 2 of 37 routers (the 2 is as measured; the denominator was recorded as 32 and is refreshed here, so the ratio does not read better than it is) |
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
- **Scoping exists for 3 of 25 RLS tables.** `20260724120000_scoped_rls_tier1_family_scoping.sql`
  scopes `child_profile`, `story_request`, `device_grant`. The other 22 carry a blanket
  `USING(true)`; their privacy rests entirely on the FastAPI layer. The denominator is 25
  distinct tables carrying `ENABLE ROW LEVEL SECURITY` across `supabase/migrations/` (28 raw
  statements, 25 unique tables, since some are enabled twice across migrations), which matches
  `control-inheritance.md` row B1.
- **The pre-push hook tier does not exist.** `.git/hooks/` contains only `pre-commit`, and
  `default_install_hook_types` is absent. Nine hooks staged `pre-push` have never run:
  `detect-secrets`, `bandit-full`, `basedpyright`, `frontend-typecheck`, `yamllint`, `qlty-check`,
  `qlty-full`, `pydoclint`, `markdownlint`. CI recovers three of them.
- **pre-commit.ci is not installed**, so the `ci:`/`skip:` block at `.pre-commit-config.yaml:12-15`
  is inert and there is no hosted fallback. No workflow runs `pre-commit run --all-files`.
- **A required check failed on third-party availability, including in files outside the diff.**
  *Largely remediated 2026-08-03; the residual is stated at the end of this entry.*
  `Dependency & Standards Validation` is a required status check (ruleset `cyo-require-ci-gate`)
  and fans in from the lychee link check, which scanned the **whole tree**, not the PR's diff. So an
  external site that was slow, or that rejected a HEAD request, turned a required gate red on a PR
  that did not touch the file. Observed on **three consecutive runs of PR #562 within twenty
  minutes, producing three disjoint failure sets**: a 520 on `readingrockets.org`, then a 415 on
  `hiwavemakers.com`, then connection failures on `eis.ucsc.edu` (three references) and
  `securityscorecards.dev`. Every one of those URLs returned 200 in under 1.2 seconds when probed
  directly. Attribution splits: the third run's failures were in
  `docs/planning/research/choice-agency-pacing-and-failure.md` and `docs/PROJECT_SETUP.md`, neither
  of which #562 touches, so that run failed purely on unrelated files. The first two were in
  `docs/planning/gamification-recommendation-2026-08-01.md`, which #562 does touch. That distinction
  matters for the remedy and not for the finding: diff-scoping removes the third class outright and
  shrinks the first two from a draw against ~129 hosts to a draw against the handful a PR cites,
  but it does not make a required gate immune to a live host having a bad minute. The failing set
  differed every run because the scan covered several hundred external URLs, so per-URL remediation
  could not converge. Compounding it, `pr-validation.yml` had no `push` trigger, so main was never
  link-checked and a bad URL was only ever discovered by, and attributed to, the next unrelated PR.
  `--accept` omitted 415, which servers return when they refuse the HEAD method rather than when a
  link is broken. Two effects, both bad: real link rot was indistinguishable from third-party
  flakiness, and the standing incentive was to re-run until green, which is precisely how a gate
  stops being read.

  **Remediated 2026-08-03 by PR #563 (`4e54fade`), verified against the merged workflows.** The
  blocking check now computes the PR's changed files from the merge base and scans only those, so
  the exposure scales with what a PR touches rather than with the size of the corpus; `--accept` is
  now `200,204,206,301,302,403,415,429`, so a HEAD refusal no longer reads as link rot; and a new
  `link-check-full.yml` runs the whole corpus on a schedule and files a `ci-failure` issue, so rot
  on main surfaces as its own issue instead of being attributed to the next unrelated PR. The
  absence of a `push` trigger on `pr-validation.yml` is no longer the gap it was, because the
  scheduled workflow now owns corpus coverage.

  Measured on this PR after the remediation merged, using lychee 0.24.2 with the merged workflow's
  own accept and exclude flags: **3 links extracted, all local file references, 0 external hosts
  contacted, exit 0.** The same PR previously drew against roughly 129 hosts. The URL in this
  register's companion file is not counted because it sits inside a `console` block and lychee's
  `include_verbatim` defaults to false, which is worth recording as a fact about the tool rather
  than luck: evidence transcripts pasted as verbatim blocks are not link-checked.

  **Residual, and it is the honest part.** A live host returning 5xx on a URL cited by a file the
  PR *does* edit still turns a required gate red, and #563's own header comment says so rather than
  claiming otherwise: replayed against #562's history, the scoping drops two of the three failure
  classes and does not drop the 520. So the category of defect is narrowed, not eliminated, and the
  re-run-until-green incentive survives in the narrowed case.

  Status: **finding open**, downgraded from *evidence invalid*. The distinction is the point of the
  status model: the gate is no longer measuring the wrong thing, it is measuring the right thing
  with a known residual failure mode. This entry is retained rather than deleted because a register
  that silently drops a finding once it is fixed cannot show that its own findings ever led
  anywhere.
- **CodeQL is disabled as of 2026-08-03; AISVS AC.4.2 fails on SAST coverage.** Read the
  supersession paragraph below before acting on the rest of this entry. The earlier text is kept
  because the reasoning error it records is still the instructive part.

  An earlier revision of this section recorded "CodeQL does not run" and "no CI-side secret
  scanning" as AISVS AC.4.2 failures. Both were wrong at the time, and wrong for the same reason:
  the method was a grep of `.github/workflows/`, and neither control is configured in a workflow
  file. Verified against the repository's own configuration and against PR #562's checks:
  - **CodeQL ran via code scanning default setup**, state `configured`, `extended` query suite,
    over `javascript-typescript`, `typescript`, `python`, and `actions`. Default setup has no
    workflow file by design, which is precisely why the grep missed it. The claim that there was
    "no SAST over the TypeScript tree" was, at that point, the inverse of the truth.
  - **Secret scanning, push protection, and validity checks are all enabled** at repository level,
    and `GitGuardian Security Checks` runs on pull requests. Push protection is strictly stronger
    than a CI-stage scan: it refuses the push rather than reporting after the secret is already in
    history.

  The residual finding was documentation, not coverage: `CLAUDE.md` states that
  `security-analysis.yml` runs CodeQL, and it does not; that workflow runs Bandit and OSV-Scanner,
  and the repo-wide `github/codeql-action` uses are `upload-sarif` steps. On the state above,
  **AISVS AC.4.2 was met**, not failed.

  **Superseded 2026-08-03: CodeQL default setup has been disabled, and AC.4.2 now fails on SAST.**
  The control was turned off deliberately, on a billing rationale, by
  `PATCH /repos/ByronWilliamsCPA/cyo-adventure/code-scanning/default-setup` with
  `state=not-configured`; the endpoint now returns `{"state":"not-configured","updated_at":null}`.
  The consequence is a real coverage loss, not a documentation change: **no SAST runs over
  `frontend/` at all.** SonarCloud does not close the gap, because `sonar-project.properties:26`
  sets `sonar.sources=src/`, the Python backend only, and the SonarCloud gate cannot block a PR
  regardless (see the SonarCloud entry below). Bandit and OSV-Scanner remain, and both are
  Python-only. The claim in `CLAUDE.md` that there is "no SAST over the TypeScript tree", which was
  the inverse of the truth when written, has become true by a change in the world rather than by a
  correction in the document. Secret scanning, push protection, validity checks, and the
  GitGuardian PR status are unaffected and remain enabled, so the secret-scanning half of AC.4.2
  still holds. Re-enabling is the same PATCH with `state=configured`, but that is not a free
  action: **as of 2026-08-24 the account holder confirms GitHub code scanning is no longer free on
  public repositories.** An earlier revision of this entry read "this repository is public, where
  code scanning is not metered, so ... re-enabling here may cost nothing", and concluded the
  billing pressure must originate elsewhere in the account. That was overtaken by a change in
  GitHub's terms rather than by an error in reasoning, and it inverted the conclusion: the
  2026-08-03 disable was a sound cost decision, not a mistake to reverse. Closing AC.4.2 therefore
  means adding an analyzer that is free or already paid for, not restoring default setup by
  default. The ranked routes are in the AC.4.2 row below.

  This entry is retained rather than deleted because the error is the instructive part. A control
  configured outside the artifact being searched is invisible to a search of that artifact, and
  reporting its absence as a finding is the exact failure mode the verification vantage rule in
  `control-inheritance.md` exists to prevent. Applied to a control plane rather than a network
  boundary, the rule reads: establish where a control is configured before concluding from one
  vantage that it is not configured at all.
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

One hundred and eighteen items, carrying provisional `O-nn` IDs that become `SEC-nnn` when the
namespace lands. Three are deferred triggers (O-76, O-98, O-99), so the active count is one hundred
and fifteen, which is **far above** the ~60 ceiling one maintainer can review meaningfully.
Trimming is the maintainer's decision, not a silent truncation.

**O-120 and O-121 added post-reconciliation (compliance-verification pass, after 2026-08-02).** The
2026-08-02 reconciliation below fixed the count at 116/113; a subsequent compliance-verification
pass found two gaps in the regulatory-applicability tables above and closed both. First, the state
information-security-statute family (NY SHIELD Act, Massachusetts 201 CMR 17.00, NYDFS Part 500,
California SB-327) was absent entirely; O-120 plus the two not-applicable determinations (NYDFS,
SB-327) closed it. Second, GDPR Art. 8's member-state child-consent-age table had no row despite
GDPR itself being tracked; O-121 closed it. Both are genuine gaps under this document's own
instantiation contract. The count is 118/115 as of both additions; recount before trusting either
figure further, per the method below.

Each row carries the fifteen fields the spine's row schema requires. Where a field could not be
derived from the row's own check, the enclosing section, or this document's audit sections, it
records an honest placeholder (`not determined`, `none`, `unassigned`, `not verified`) rather than
a plausible-looking value. That is deliberate: a register of invented failure oracles reads as
verified and is not, which is the exact defect SP-17 exists to catch. The placeholders are the
work queue. Every row's `Phase home` is `unassigned` today, because no `UW-*` row can cite these
IDs until the namespace in prerequisite 1 lands.

Earlier revisions of this paragraph said "seventy-eight items ... twelve deferred ... sixty-six
active", and the lifecycle section separately recorded a decision to accept "81 rows". All three
figures were wrong, and the error was load-bearing rather than cosmetic: it presented the register
as six rows over a review ceiling it is actually fifty-three rows over, and it recorded a
row-budget decision whose stated purpose was to prevent a budget being silently exceeded. The
authoritative count is a count of `#### O-<digits>` headings within this section: 122 rows, IDs
running O-01 to O-125 with O-63, O-64, and O-65 unassigned. Recount with
`grep -cE '^#### O-[0-9]+$'`. Note that O-117 and O-119 also appear as the first cell of the
initial-build commitments table below; those are cross-references to rows defined here, not
additional rows, and the heading-anchored pattern above deliberately excludes them.

### SP-17 Assurance Validity and Change Lifecycle

Listed first because it gates the credibility of every other row. Legal basis GDPR Art. 32(1)(d);
US equivalents are COPPA §312.8 ongoing safeguard testing and annual evaluation.

#### O-27

- **Category:** SP-17
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** MANUAL
- **Protected property:** every verification method in this register has a demonstrated ability to
  report a failure (a deliberate failing fixture exists for it)
- **Verification target:** this register's own row set and each row's recorded negative-control
  fixture
- **Failure oracle:** a row carries a status other than *mechanism unproven* while no deliberate
  failing fixture is recorded for it
- **Negative control:** a row entered or promoted with no deliberate failing fixture on record
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every verification method in this register has a deliberate failing fixture proving it
  can report a failure. Checks with no such fixture hold status *mechanism unproven*

#### O-66

- **Category:** SP-17
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** STATIC
- **Protected property:** every automated check's row records its verification target, trigger,
  existing coverage, failure oracle, and owner
- **Verification target:** this register's row set, queried for field completeness
- **Failure oracle:** a quarterly query over the register finds an automated-check row missing its
  verification target, trigger, existing coverage, failure oracle, or owner
- **Negative control:** a row saved with one of those required fields blank
- **Trigger:** quarterly
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every automated check records its verification target, trigger, existing coverage,
  failure oracle, and owner, named with the spine's own schema fields so the query is writable
  against real rows; a quarterly query finds rows missing any field

#### O-67

- **Category:** SP-17
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** DYNAMIC
- **Protected property:** each check's execution path is confirmed by observation, not inferred:
  the hook fired, or the workflow ran on the relevant event, against the right revision, over the
  right paths, with its exit code propagated
- **Verification target:** CI workflow run logs and hook execution records for each registered
  check
- **Failure oracle:** a check's row is treated as having run while no observed log confirms the
  hook fired or the workflow ran on the relevant event, revision, and paths with exit code
  propagated
- **Negative control:** a check whose hook or workflow did not fire, or fired on the wrong revision
  or paths, recorded as having run
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Each check's execution path is **observed, not inferred**: the hook fired, the
  workflow ran on the relevant event, against the right revision, over the right paths, with exit
  code propagated

#### O-68

- **Category:** SP-17
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** RUNTIME-CONFIG
- **Protected property:** each deployment records a diff of vendor control-plane settings against
  the last known-good baseline, so dashboard drift is visible
- **Verification target:** vendor control-plane settings (dashboards) at each deployment, diffed
  against the last known-good baseline
- **Failure oracle:** a deployment occurs with no recorded diff of vendor control-plane settings
  against the last known-good baseline, or drift exists that no diff surfaced
- **Negative control:** a control-plane setting changed between deployments with no diff recorded
- **Trigger:** each deployment
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Each deployment records a diff of vendor control-plane settings against the last
  known-good baseline, so dashboard drift is visible

#### O-69

- **Category:** SP-17
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** MANUAL
- **Protected property:** sampled control evidence, traced from source to deployed effect, could
  not have been produced if the protected property it attests to were actually false
- **Verification target:** the control-evidence trail from source to deployed effect, for a
  quarterly sample of rows
- **Failure oracle:** the quarterly sample finds evidence that could have been produced regardless
  of whether the protected property was true or false
- **Negative control:** not determined
- **Trigger:** quarterly
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Quarterly, a named maintainer samples control evidence from source to deployed effect
  and records whether that evidence could have been produced while the protected property was false

#### O-70

- **Category:** SP-17
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** STATIC
- **Protected property:** reassessment of register rows is triggered by which control surface a
  change affects, not by whether that change was authored by a human or an AI tool
- **Verification target:** the reassessment-trigger process applied to changes touching identity,
  authorization, tenancy or schema; provider, SDK, dependency, model, prompt, moderation threshold,
  or parser; child-visible storage, sync, logging, or publication state; data field, purpose,
  recipient, jurisdiction, or retention rule; or control-plane configuration
- **Failure oracle:** a change to one of the listed control surfaces lands without a corresponding
  reassessment record for the affected register rows
- **Negative control:** a listed control-surface change merged with no reassessment record
- **Trigger:** identity, authorization, tenancy or schema change; new or changed provider, SDK,
  dependency, model, prompt, moderation threshold, or parser; change to child-visible storage,
  sync, logging, or publication state; new data field, purpose, recipient, jurisdiction, or
  retention rule; control-plane change
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Reassessment is triggered by **affected control surface, not by authorship**.
  Triggers: identity, authorization, tenancy or schema change; new or changed provider, SDK,
  dependency, model, prompt, moderation threshold, or parser; change to child-visible storage,
  sync, logging, or publication state; new data field, purpose, recipient, jurisdiction, or
  retention rule; control-plane change

#### O-107

- **Category:** SP-17
- **Framework ref:** AISVS AC.1.1 to AC.1.3
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** MANUAL
- **Protected property:** a written AI-assisted-coding workflow document names approved tools,
  prohibited use cases, permitted input data classifications, the SSDLC phases it covers, the gates
  that stay mandatory regardless of AI involvement, and the adversarial scenarios it mitigates
- **Verification target:** the written AI-assisted-coding workflow document
- **Failure oracle:** the workflow document does not exist, or is missing one of: approved tools,
  prohibited use cases, permitted input data classifications, SSDLC phases covered, mandatory
  gates, or adversarial scenarios mitigated
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AISVS AC.1.1-AC.1.3**: a written AI-assisted-coding workflow names approved tools,
  prohibited use cases, permitted input data classifications, the SSDLC phases covered, the gates
  that stay mandatory regardless of AI involvement, and the adversarial scenarios it mitigates

#### O-108

- **Category:** SP-17
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 32(1)(d) / COPPA 312.8
- **Class:** MANUAL
- **Protected property:** US state privacy-law applicability recorded in this register is refreshed
  quarterly against the IAPP and Bloomberg trackers, with enactment status tracked separately from
  litigation status
- **Verification target:** this register's regulatory-applicability section, cross-checked against
  the IAPP and Bloomberg law trackers
- **Failure oracle:** a quarter passes with no recorded refresh against the trackers, or a tracked
  state-law enactment or litigation change is not reflected in the register within a quarter
- **Negative control:** not determined
- **Trigger:** quarterly
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **Quarterly US state-law refresh** against the IAPP and Bloomberg trackers, tracking
  enactment and litigation status separately. The spine's own volatility table makes this the
  fastest-decaying input to this register

O-27 is the register's own health check. This repository has already produced multiple distinct
silent-pass failures; a register whose checks cannot fail reproduces the exact pathology it exists
to prevent, so canary work belongs in the same phase as the first batch of automated verifications.

O-70 replaces "re-test after every AI-assisted change". Authorship is not the risk: an AI-generated
comment does not warrant what a hand-written authorization change warrants.

### SP-15 Human Decision Gates and Publication Integrity

The last barrier before content reaches a child. Fails differently from the model layer: through
mis-defaulted visibility and reviewer incompleteness, not through prompt injection.

#### O-17

- **Category:** SP-15
- **Framework ref:** AISVS C9.2 (analogy, not citation; see section note below)
- **Legal ref:** not determined
- **Class:** DYNAMIC (secondary: STATIC, already named in the Check text as "enforced in the read
  path")
- **Protected property:** no reader-visible node body exists without both a passing validator
  report and a human approval record
- **Verification target:** the read path's node-visibility enforcement, confirmed by a data
  invariant query over stored node and approval records
- **Failure oracle:** the data invariant query finds a reader-visible node body with no passing
  validator report, or no human approval record
- **Negative control:** a node body marked reader-visible in test data with no validator report or
  no approval record attached
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** No reader-visible node body exists without both a passing validator report and a
  human approval record, enforced in the read path and confirmed by a data invariant query

#### O-53

- **Category:** SP-15
- **Framework ref:** AISVS C9.2 (analogy, not citation; see section note below)
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** the schema default for content visibility is invisible, so a row the
  application forgets to set is safe
- **Verification target:** the schema/migration definition of the content-visibility column's
  default value
- **Failure oracle:** the schema default for the content-visibility column is anything other than
  invisible
- **Negative control:** a migration or schema change setting the visibility default to visible
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The **schema default** for content visibility is invisible, so a row the application
  forgets to set is safe

#### O-52

- **Category:** SP-15
- **Framework ref:** AISVS 9.2.2 (pattern analogy, not citation)
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** the reviewer interface exposes every reachable branch, personalization
  substitution, moderation warning, media asset, and validation exception for a story under review
- **Verification target:** the admin/guardian reviewer interface's rendering of a story under
  review
- **Failure oracle:** a reachable branch, personalization substitution, moderation warning, media
  asset, or validation exception exists in the story but does not appear to the reviewer
- **Negative control:** a hidden unsafe branch inserted into a test artifact must appear to the
  reviewer
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The reviewer interface exposes every reachable branch, personalization substitution,
  moderation warning, media asset, and validation exception. Negative control: a hidden unsafe
  branch inserted into a test artifact must appear to the reviewer. Pattern analogy, not a
  citation: AISVS 9.2.2 is scoped to agent runtimes, and this pipeline is staged RQ jobs (see the
  section note below)

#### O-54

- **Category:** SP-15
- **Framework ref:** AISVS C9.2 (analogy, not citation; see section note below)
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** any post-approval change to text, graph, personalization, media, or
  policy version invalidates the existing approval and returns the artifact to review
- **Verification target:** the publishing state machine's approval-invalidation logic on edit
- **Failure oracle:** a post-approval edit to text, graph, personalization, media, or policy
  version occurs and the artifact remains in an approved or publishable state
- **Negative control:** an edit made to an approved artifact that does not trigger re-review
- **Trigger:** any post-approval change to text, graph, personalization, media, or policy version
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Any post-approval change to text, graph, personalization, media, or policy version
  invalidates approval and returns the artifact to review

#### O-55

- **Category:** SP-15
- **Framework ref:** AISVS C9.2 (analogy, not citation; see section note below)
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** a moderation classifier timeout, refusal, malformed response, quota
  exhaustion, or threshold misconfiguration always routes content to a human and can never be
  represented as approval
- **Verification target:** the moderation pipeline's error and exception handling path
- **Failure oracle:** a classifier timeout, refusal, malformed response, quota exhaustion, or
  threshold misconfiguration results in a state recorded or treated as approval rather than routed
  to a human
- **Negative control:** injecting a classifier timeout, malformed response, or quota exhaustion and
  observing whether the pipeline defaults to an approval-equivalent state
- **Trigger:** classifier timeout, refusal, malformed response, quota exhaustion, or threshold
  misconfiguration event
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Moderation classifier timeout, refusal, malformed response, quota exhaustion, or
  threshold misconfiguration routes to a human and **cannot be represented as approval**

#### O-71

- **Category:** SP-15
- **Framework ref:** AISVS C9.2 (analogy, not citation; see section note below)
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** approval is bound to an immutable content digest plus reviewer identity,
  policy version, and timestamp, and cannot be satisfied by replaying a prior approval or by a
  default-true field
- **Verification target:** the approval record schema and the code path that checks approval
  validity
- **Failure oracle:** an approval is accepted as valid without matching the current content digest,
  reviewer identity, policy version, and timestamp, for example by replay of a prior approval or a
  field defaulting to true
- **Negative control:** replaying a prior approval record against changed content, or a
  default-true field satisfying the approval check
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Approval is bound to an immutable content digest plus reviewer identity, policy
  version, and timestamp; it cannot be satisfied by replaying a prior approval or by a default-true
  field

#### O-72

- **Category:** SP-15
- **Framework ref:** AISVS C9.2 (analogy, not citation; see section note below)
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** no child-scoped principal can retrieve a story in any pre-approval state,
  through any path: endpoint, cache, signed URL, offline bundle, notification, or search result
- **Verification target:** every child-facing retrieval path: API endpoints, caches, signed URLs,
  offline sync bundles, notifications, and search results
- **Failure oracle:** a child-scoped principal successfully retrieves pre-approval-state story
  content through any of the listed paths
- **Negative control:** a child session attempting to retrieve a not-yet-approved story through
  each listed path
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** No child-scoped principal can retrieve a story in any pre-approval state through any
  path: endpoint, cache, signed URL, offline bundle, notification, or search result

AISVS C9.2 is the nearest published anchor for this category. It is an **analogy, not a citation**:
C9.2 is scoped to agent runtimes and this pipeline is staged RQ jobs. The DTSP Best Practices
Framework (2025) and ISO/IEC 25389:2025 clauses 4 and 5 describe human review only as illustrative
non-prescriptive practice, so these controls are locally authored.

O-17's violation is a child-safety incident rather than a security finding, which is why it is the
one item worth a later conversation about enforcement in the read path itself. That would be a
product control, not a CI gate, and is therefore compatible with the no-blocking decision.

### SP-14 AI and Model Layer

#### O-14

- **Category:** SP-14
- **Framework ref:** AISVS C2.1
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** untrusted intake text is always passed in a data position with
  delimiters, never concatenated into system-prompt position
- **Verification target:** the prompt-construction code paths in `generation/` that assemble LLM
  system prompts from story-request intake
- **Failure oracle:** a code path concatenates untrusted intake text directly into system-prompt
  position rather than a delimited data position
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Untrusted intake text is passed in a data position with delimiters, never concatenated
  into system-prompt position (AISVS C2.1)

#### O-15

- **Category:** SP-14
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** content re-entering a later pipeline stage (series continuation, mutated
  skeletons) is re-classified before reuse
- **Verification target:** the series-continuation and skeleton-mutation code paths that reuse
  prior content
- **Failure oracle:** previously generated content is reused at a later stage without being
  re-classified first
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Content re-entering a later stage (series continuation, mutated skeletons) is
  re-classified before reuse

#### O-16

- **Category:** SP-14
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** every provider path (Anthropic, OpenRouter, Modal, fallback)
  terminates in the identical validator plus moderation gate, with no provider-specific shortcut
- **Verification target:** each provider module under `generation/providers/` and its call path
  into `validator/` and `moderation/`
- **Failure oracle:** a provider path reaches a publishable or reviewable state without passing
  through the same validator and moderation gate as the other providers
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every provider path (Anthropic, OpenRouter, Modal, fallback) terminates in the
  identical validator plus moderation gate, with no provider-specific shortcut

#### O-18

- **Category:** SP-14
- **Framework ref:** AISVS C11.1
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** a maintained adversarial corpus is run against live moderation
  thresholds at each release, with pass rate recorded as a trend over time
- **Verification target:** the adversarial test corpus and the moderation threshold configuration
  in effect at release time
- **Failure oracle:** a release occurs with no adversarial corpus run recorded against it, or the
  pass-rate trend is not recorded
- **Negative control:** not determined
- **Trigger:** each release
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A maintained adversarial corpus runs against live thresholds each release; pass rate
  recorded with a trend (AISVS C11.1)

#### O-19

- **Category:** SP-14
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** worker network egress is allowlisted to approved provider endpoints only,
  and child identifiers are pseudonymized before crossing that boundary
- **Verification target:** the deployed worker's network egress allowlist/firewall configuration
  and the outbound request payload sent to providers
- **Failure oracle:** a worker process reaches a non-allowlisted endpoint, or an outbound request
  carries a raw, non-pseudonymized child identifier
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Worker egress is allowlisted to approved provider endpoints; child identifiers
  pseudonymized before crossing the boundary

#### O-20

- **Category:** SP-14
- **Framework ref:** AISVS C3.1
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** each enabled generation provider has a recorded DPA/zero-data-retention
  posture and a pinned (non-floating) model identifier
- **Verification target:** the provider allowlist/configuration records and each enabled provider's
  DPA/ZDR documentation
- **Failure oracle:** an enabled provider has no recorded DPA/ZDR posture, or its configured model
  identifier is unpinned (a floating alias rather than a fixed version)
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Each enabled provider has a recorded DPA/ZDR posture and a pinned model identifier
  (AISVS C3.1)

#### O-56

- **Category:** SP-14
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** the admin review dashboard does not act as an XSS sink for
  pipeline-generated text
- **Verification target:** the admin review dashboard's rendering of pipeline-generated story text
- **Failure oracle:** markup injected via a guardian prompt into generated text executes or renders
  as active content in the admin review dashboard
- **Negative control:** a guardian-authored prompt injection that produces markup in generated
  text, rendered to check for execution on the admin review dashboard
- **Trigger:** not determined
- **Existing coverage:** none (the Check text records that the validator checks topology and
  reading level, but explicitly not markup safety)
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The admin review dashboard is not an XSS sink for pipeline output. Composite path:
  guardian prompt injection produces markup in generated text, the validator checks topology and
  reading level but not markup safety, and it renders on the highest-privilege surface in the
  system

#### O-73

- **Category:** SP-14
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** a provider timeout, refusal, malformed output, content-filter response,
  or model removal always produces an explicit non-publishable state, never an unmoderated fallback
  or a partial story
- **Verification target:** the generation orchestrator's error-handling path for each provider
  failure mode
- **Failure oracle:** one of the listed provider failure modes results in content reaching a
  publishable or reviewable state without moderation, or a partial story being retained as a
  candidate
- **Negative control:** injecting a provider timeout, refusal, malformed output, content-filter
  response, or a simulated model removal and observing the resulting state
- **Trigger:** provider timeout, refusal, malformed output, content-filter response, or model
  removal event
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Provider timeout, refusal, malformed output, content-filter response, or model removal
  produces an explicit non-publishable state, never an unmoderated fallback or a partial story

#### O-74

- **Category:** SP-14
- **Framework ref:** not determined
- **Legal ref:** EU AI Act (generated-content disclosure, conditional on EU market entry)
- **Class:** RUNTIME-CONFIG
- **Protected property:** any provider or model change, including a silent hosted-model alias
  change, triggers a regression run against the structural, safety, and privacy corpora, with
  results retained by exact model version
- **Verification target:** the provider/model version pinning configuration and the regression
  corpus run records, keyed by exact model version
- **Failure oracle:** a provider or model change, including a silent hosted-model alias swap,
  occurs with no corresponding regression run recorded against the structural, safety, and privacy
  corpora for that exact model version
- **Negative control:** a simulated silent model-alias change with no regression run triggered
- **Trigger:** provider or model change, including silent hosted-model aliases; also the trigger
  for EU AI Act generated-content disclosure if EU market entry occurs
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Provider or model changes, including silent hosted-model aliases, trigger regression
  against the structural, safety, and privacy corpora, retained by exact model version. Also the
  hook for EU AI Act generated-content disclosure if EU market entry occurs

### SP-10 Build and Software Supply Chain

Substantially expanded after reading AISVS Appendix C in full. Sections AC.11 to AC.13 cover the
development pipeline being attacked *through* the AI tooling, a surface this register did not
previously touch at all. It is live here: CodeRabbit and `claude-baseline-review.yml` both consume
PR content.

**Appendix C coverage, stated rather than implied.** Of AC.1 through AC.14, eleven are cited by a
row somewhere in this register. **Three are cited by nothing: AC.2** (tool qualification and threat
modeling, including vendor model supply chain and pre-onboarding adversarial testing), **AC.6**
(continuous feedback, red-teaming of the AI tooling itself, regression harness after every prompt
or model change), and **AC.9** (artifact origin validation at deploy: signed provenance, trusted
verifier, quarantine on failure).

Recount only with a pattern scoped to row blocks, because this paragraph names the three uncovered
sections and a whole-file `grep -oE 'AC\.[0-9]+'` therefore finds all fourteen and reports full
coverage. That trap was hit while writing this entry, which is why the working recipe is recorded
rather than left to be reconstructed:

```console
$ awk '/^#### O-[0-9]+$/{r=1} /^### |^## /{r=0} r' docs/security/assurance-register.md \
    | grep -oE 'AC\.[0-9]+' | sort -u
```

A verification method that reads the sentence describing a gap and concludes the gap is closed is
the register's own subject matter, one level up.

No rows are added for them here, deliberately. The row count is already the subject of an open
budget decision (prerequisite 6), and adding three more would pre-empt a call that belongs to the
maintainer. The gap is recorded instead, which is the whole point of a spine: an uncovered section
is visible as a section with no rows rather than as a question nobody asked.

#### O-24

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C (inherited from the section intro; no specific AC clause
  cited in this row)
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** Released container images carry verifiable provenance and are deployed
  pinned by digest, never by mutable tag.
- **Verification target:** the release/deployment configuration's image reference (digest vs. tag)
  and the provenance attestation attached to the released container digest.
- **Failure oracle:** A deployment configuration references a container image by tag rather than
  digest, or the deployed digest has no verifiable provenance attestation attached.
- **Negative control:** not determined
- **Trigger:** each container release and deployment
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Released container digests carry verifiable provenance; deployment pins by digest,
  not tag

#### O-25

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.12.1
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** All GitHub Actions are pinned by commit SHA, and no `pull_request_target`
  or `workflow_run` trigger executes untrusted code with write permissions or secret access; no
  secret is reachable from a fork-triggered job.
- **Verification target:** `.github/workflows/*.yml` action references (`uses:` lines) and the
  trigger/permissions configuration of any `pull_request_target` or `workflow_run` workflow.
- **Failure oracle:** A workflow references an action by a mutable tag or branch rather than a
  commit SHA, or a `pull_request_target`/`workflow_run` workflow executes checked-out PR code with
  write permissions or secret access reachable from a fork.
- **Negative control:** not determined
- **Trigger:** any change to a workflow file
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Actions pinned by commit SHA; no `pull_request_target` or `workflow_run` executing
  untrusted code with write permissions or secret access; no secret reachable from a
  fork-triggered job (**AC.12.1**)

#### O-26

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C (inherited from the section intro; no specific AC clause
  cited in this row)
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** The frontend API client stays in sync with the backend OpenAPI contract,
  and installed dependencies match their lockfile.
- **Verification target:** the `contract` CI job that dumps the OpenAPI schema and diffs the
  generated client, and the package manager's lockfile-integrity check at install time.
- **Failure oracle:** A backend contract change merges without the generated client being
  regenerated and committed, or a dependency installs at a version that does not match its
  lockfile entry.
- **Negative control:** not determined
- **Trigger:** every backend contract change (route or Pydantic model change) and every dependency
  install
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The client drift job runs on every contract change; lockfile integrity verified at
  install

#### O-81

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.4.2
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** SAST, secret scanning, IaC scanning, and SCA run on every pull request
  before merge.
- **Verification target:** the repository's code scanning default setup configuration (CodeQL
  state, query suite, and covered languages) and the repository's secret scanning, push
  protection, and validity-check settings, plus the GitGuardian Security Checks PR status.
- **Failure oracle:** A pull request merges without CodeQL (or another SAST tool), secret
  scanning, IaC scanning, or SCA having run against it; or code scanning default setup, secret
  scanning, or push protection is found disabled at the repository level.
- **Negative control:** `tests/fixtures/semgrep-canary.tsx`, added by PR
  [#754](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/754). It carries one instance of
  every in-repo Semgrep rule, and the `semgrep-frontend` job fails unless every rule fires on it
  and unless the defined rule count stays above a pinned floor. This is the first entry in this
  register whose negative control is enforced by CI rather than described: a drifted SAST ruleset
  and a clean tree are otherwise indistinguishable.
- **Trigger:** every pull request
- **Existing coverage:** secret scanning half met; **SAST half now met over `frontend/`**, by a
  different route than CodeQL. Repository-level secret scanning, push protection, and validity
  checks, plus GitGuardian Security Checks on pull requests, cover the secret-scanning half and are
  unaffected throughout. For the SAST half, PR #754 merged 2026-08-24 as `36dad55e` and closed the
  gap on three of the four ranked routes below: routes 1 (`eslint-plugin-security` and
  `eslint-plugin-no-unsanitized` on the `npm run lint` pass that already blocks merges), 2 (a
  `semgrep-frontend` job with an in-repo ruleset, failing the build directly rather than via SARIF
  upload, so no code-scanning metering is re-incurred), and 3 (`-Dsonar.sources=src,frontend/src`).
  Route 4 stays deliberately unused. Code scanning default setup remains `not-configured` and is
  not the mechanism here.

  Re-verified against `main` rather than against the pull request, as this row required:
  `.semgrep/frontend-security.yml` is the in-repo ruleset, `security-analysis.yml:139` defines the
  `semgrep-frontend` job, and that job **gates merges** rather than merely reporting. The org
  ruleset requires `Security Gate Validation`; that job declares
  `needs: [security, semgrep-frontend]` and, because `if: always()` would otherwise let a failed
  upstream job pass unread, its "Check security scan results" step reads
  `needs.semgrep-frontend.result` explicitly and exits 1 on any non-`success`. An unread result
  would have been an ignored result, so the explicit read is what makes this gating rather than
  advisory. IaC scanning and SCA coverage remain unconfirmed and are untouched by #754.
- **Residual after #754**, all raised by the authors of the change rather than found in
  review, and all carrying register rows: `UW-C365` (Semgrep's OSS TypeScript parser fails on 5
  frontend test files, which are therefore analysed by nothing; pinned by identity, not by count,
  so fixing five tests while breaking five production modules cannot hide the hole), `UW-C366`
  (the SonarCloud widening rests on an unverified assumption about repeated `-D` precedence and
  cannot be confirmed from a green run), `UW-C367` (frontend test files are excluded from Sonar
  rather than declared as tests), and `UW-C369` (Semgrep pinned by version without a hash, unlike
  every other pinned action in this repository).
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** 2026-08-30, against `main` at `6cc33aa5`: `.semgrep/frontend-security.yml`
  and `tests/fixtures/semgrep-canary.tsx` present, `security-analysis.yml:139` defines
  `semgrep-frontend`, and `security-analysis.yml:396-440` reads its result into the required
  `Security Gate Validation` check. Code scanning default setup last checked 2026-08-24 via the
  live `GET /repos/ByronWilliamsCPA/cyo-adventure/code-scanning/default-setup` (returns
  `state: not-configured`). Verified by API and by file read, not by grepping
  `.github/workflows/`, which cannot see default setup at all.
- **Status:** SAST half met by #754; four residual rows open (`UW-C365`, `UW-C366`, `UW-C367`,
  `UW-C369`). IaC and SCA coverage still unconfirmed.
- **Check:** **AC.4.2**: SAST, secret scanning, IaC scanning, and SCA run on every pull request.
  **Failed on SAST from 2026-08-03; restored 2026-08-24 by a different mechanism.** Code
  scanning default setup was deliberately disabled on a
  billing rationale (`PATCH .../code-scanning/default-setup` with `state=not-configured`, endpoint
  now returns `{"state":"not-configured","updated_at":null}`), removing the only SAST that covered
  `frontend/`. Secret scanning, push protection, validity checks, and GitGuardian Security Checks
  are unaffected and still satisfy the secret-scanning half. Two earlier revisions of this row were
  wrong in opposite directions and are kept in the narrative above: the first read "CodeQL does not
  run and no CI secret scanning exists", false at the time and found by grepping
  `.github/workflows/`, which misses default setup because it has no workflow file; the second read
  "AISVS AC.4.2 is met, not failed", true when written and made false by the disable rather than by
  any error in it. Closing this required restoring SAST over `frontend/`, and the route mattered
  because re-enabling is no longer free: **as of 2026-08-24 the account holder confirms GitHub code
  scanning is no longer free on public repositories**, so the same PATCH with `state=configured`
  carries a real recurring cost. Ranked by cost, and by whether the result can actually block a
  merge. **Routes 1, 2 and 3 were taken by #754 on 2026-08-24; route 4 remains deliberately
  unused**, so the ranking below is retained as the record of why, not as an open menu:

  1. **Add security rules to the ESLint pass that already gates every pull request.**
     `npm run lint` runs at `.github/workflows/ci.yml:191` with `--max-warnings=0` and already
     covers `src/`, all five e2e directories, and the four Playwright configs. Adding
     `eslint-plugin-security` and `eslint-plugin-no-unsanitized` costs nothing and blocks merges
     today. This is lint-grade pattern matching, materially weaker than a taint engine, so treat
     it as a floor rather than a complete answer.
  2. **Add Semgrep OSS to CI** for genuine cross-file TypeScript rules. The CLI is free.
     #VERIFY: whether SARIF upload into GitHub code scanning is itself metered under the current
     terms; if it is, have the job fail on findings directly instead of routing through code
     scanning alerts.
  3. **Widen SonarCloud to `frontend/src`.** No new tooling cost, since SonarCloud already
     analyzes this repository. Two limits: the effective `-Dsonar.sources=src` is set in the org
     reusable workflow `ByronWilliamsCPA/.github/.github/workflows/python-sonarcloud.yml`, a
     different repository, so the change is cross-repo; and per the entry above the SonarCloud
     gate cannot block a pull request, so this buys visibility rather than enforcement.
  4. **Re-enable code scanning default setup** (`state=configured`). Best analysis of the four,
     and now a paid line item. This is an owner decision, not a remediation to apply.

#### O-82

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.4.1
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** AI-generated code is reviewed by a human who is not the identity that
  requested the generation (separation of duties).
- **Verification target:** PR review attribution (author vs. approver identity) on AI-assisted
  commits in this repository.
- **Failure oracle:** An AI-generated change is merged with no distinct-identity human review
  recorded, and no accepted-exception record with compensating controls and an expiry exists to
  cover the gap.
- **Negative control:** none (a single-maintainer repository cannot structurally trip a
  distinct-reviewer check; there is no second identity to demonstrate the control)
- **Trigger:** every AI-generated change, and periodic exception review at expiry
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** finding open (the spine defines *accepted exception* as risk, compensating controls,
  and expiry recorded. None of the three exists yet, so claiming that status here would assert the
  work the Check below prescribes as already done)
- **Check:** **AC.4.1** requires AI-generated code to be reviewed by a human who is not the
  identity that requested the generation. A single-maintainer AI-assisted repository cannot
  satisfy this as written. Record as an **accepted exception with compensating controls and an
  expiry**, not a silent skip

#### O-83

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.3.1-AC.3.2
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Secrets, credentials, and PII never enter AI tool context windows.
- **Verification target:** pre-commit/CI hooks that scan and redact AI tool context windows
  (prompts, session transcripts) before they are persisted or transmitted.
- **Failure oracle:** A secret, credential, or PII value is found unredacted inside an AI tool's
  context window, prompt log, or transcript.
- **Negative control:** not determined
- **Trigger:** every hook invocation and CI run that touches AI tool context
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.3.1-AC.3.2**: secrets, credentials, and PII never enter AI tool context,
  enforced in hooks and CI, with automated redaction of context windows

#### O-84

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.7.1-AC.7.3
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** AI-generated infrastructure and pipeline artifacts are labeled as such,
  human-reviewed before running outside a sandbox, and pass policy-as-code checks at least as
  strictly as human-authored changes.
- **Verification target:** infrastructure-as-code and pipeline artifact changes (labels/metadata)
  and the policy-as-code gate applied to them.
- **Failure oracle:** An AI-generated infrastructure or pipeline artifact runs outside a sandbox
  without a human review recorded, lacks an AI-generated label, or is subject to a looser
  policy-as-code check than a human-authored equivalent.
- **Negative control:** not determined
- **Trigger:** any AI-generated infrastructure or pipeline artifact change
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.7.1-AC.7.3**: AI-generated infrastructure and pipeline artifacts are labeled,
  human-reviewed before running outside a sandbox, and pass policy-as-code at least as strictly as
  human-authored changes

#### O-109

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.8.1
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** An AI agent cannot approve, merge, sign, or deploy an artifact it
  generated, enforced mechanically by branch protection, CI, and the registry rather than by
  policy alone.
- **Verification target:** branch protection rules, auto-merge settings, and merge permissions on
  this repository's pull requests.
- **Failure oracle:** An assistant/agent identity enables auto-merge, approves, or merges a PR it
  authored, with no branch-protection, CI, or registry control blocking it.
- **Negative control:** not determined
- **Trigger:** every PR authored by an assistant/agent identity
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** finding open
- **Check:** **AC.8.1**: an agent cannot approve, merge, sign, or deploy an artifact it generated,
  enforced by branch protection, CI, and the registry. AISVS is explicit that "policy alone does
  not satisfy this control". **Live exposure**: assistants in this repo can enable auto-merge on
  PRs they authored

#### O-110

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.11.1-AC.11.3
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** AI review bots treat all PR-controlled content as untrusted input, run
  with hash-pinned system prompts immune to repository/PR-controlled modification, and produce
  schema-validated output that is never executed.
- **Verification target:** the AI review bot integrations in this repository (CodeRabbit,
  `claude-baseline-review.yml`) and their prompt-configuration and output-handling paths.
- **Failure oracle:** An AI review bot's behavior changes based on PR-controlled content (diff,
  title, body, comments, commit messages, or linked URLs) beyond its intended review function, or
  its output is executed rather than schema-validated and displayed.
- **Negative control:** not determined
- **Trigger:** every PR reviewed by an AI bot
- **Existing coverage:** CLAUDE.md's standing rule to treat issue, PR, and external web content as
  untrusted data, which this section's trailing note calls a hand-derived version of AC.3.3 and
  AC.11.1; the published AISVS requirements are stricter and are the better citation than the
  hand-derived rule.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.11.1-AC.11.3**: AI review bots treat PR diff, title, body, comments, commit
  messages, and linked URLs as untrusted; their system prompts are hash-pinned and not modifiable
  from repository or PR-controlled input; their output is schema-validated and never executed

#### O-111

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.11.7 + AC.12.3 + AC.13.2
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Fork and first-time-contributor PRs run AI review only in read-only
  shadow mode, and no secret-bearing or privileged workflow processes them without maintainer
  approval enforced at the platform level.
- **Verification target:** GitHub environment protection rules and workflow-level approval gates
  for fork and first-time-contributor PRs.
- **Failure oracle:** A fork or first-time-contributor PR triggers a secret-bearing or privileged
  workflow without a platform-level (not merely bot-level) maintainer approval gate having run.
- **Negative control:** not determined
- **Trigger:** every PR from a fork or a first-time contributor
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.11.7 + AC.12.3 + AC.13.2**: fork and first-time-contributor PRs run AI review in
  read-only shadow mode and require maintainer approval before any secret-bearing or privileged
  workflow processes them. Bot-level enforcement does not substitute for platform-level
  environment protection

#### O-112

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.12.5
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Changes to workflow definition files route through an elevated review
  path regardless of author, and no agent holds bypass authority over that path.
- **Verification target:** branch protection / CODEOWNERS rules covering `.github/workflows/` and
  the list of identities with bypass authority.
- **Failure oracle:** A workflow-definition-file change merges without the elevated review path
  having run, or an agent identity is found with bypass authority over that path.
- **Negative control:** not determined
- **Trigger:** every change to a workflow definition file
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.12.5**: changes to workflow definition files route through an elevated review
  path regardless of author, and no agent holds bypass authority over it

#### O-113

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.12.8
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** Remediating a vulnerable workflow invalidates or re-validates every PR
  opened before the fix, so a later commit to an old PR cannot pick up the stale workflow
  definition.
- **Verification target:** the workflow-remediation process itself: whether fixing a vulnerable
  workflow triggers re-validation of open PRs predating the fix.
- **Failure oracle:** A PR opened before a workflow-vulnerability fix later picks up the pre-fix
  (stale) workflow definition via a new commit, without having been invalidated or re-validated.
- **Negative control:** not determined
- **Trigger:** every workflow-vulnerability remediation
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.12.8**: remediating a vulnerable workflow invalidates or re-validates every PR
  opened before the fix, so a later commit to an old PR cannot pick up the stale definition and
  route around it

#### O-114

- **Category:** SP-10 Build and Software Supply Chain
- **Framework ref:** AISVS Appendix C AC.10.1 + AC.5.1
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Every AI-generated artifact carries model identity and version, tool
  identity, prompt hash, human involvement, and correlation IDs sufficient to replay the full
  prompt-to-response-to-commit-to-build-to-deployment chain.
- **Verification target:** commit metadata, CI build metadata, and deployment records for
  AI-generated artifacts.
- **Failure oracle:** An AI-generated artifact's commit, build, or deployment record is missing
  model identity/version, tool identity, prompt hash, human-involvement record, or correlation ID,
  such that the generation chain cannot be replayed end to end.
- **Negative control:** not determined
- **Trigger:** every AI-generated artifact reaching commit, build, or deployment
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.10.1 + AC.5.1**: AI-generated artifacts carry model identity and version, tool
  identity, prompt hash, human involvement, and correlation IDs, sufficient to replay prompt to
  response to commit to build to deployment

O-82 is the honest version of a control this project structurally cannot meet. Recording it as an
exception with an expiry is the difference between a known gap and an invisible one. Note that
CLAUDE.md's standing rule to treat issue and PR content as untrusted data is a hand-derived version
of AC.3.3 and AC.11.1; the published requirements are stricter and are the better citation.

### SP-09 Runtime Configuration and Control-Plane Drift

#### O-48

- **Category:** SP-09 Runtime Configuration and Control-Plane Drift
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** The origin server accepts public traffic only through the intended edge
  (reverse proxy/CDN), or requires mTLS from that edge.
- **Verification target:** the origin's exposed network listeners and firewall/mTLS configuration,
  as deployed.
- **Failure oracle:** The origin accepts a request that did not traverse the intended edge, or
  accepts a connection from the edge without mTLS being enforced.
- **Negative control:** not determined
- **Trigger:** on closure (`control-inheritance.md` names A9's re-validation trigger as
  *On closure*)
- **Existing coverage:** none; this row is a confirmed open finding (`control-inheritance.md` item
  A9), not a passing gate
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** finding open
- **Check:** The origin accepts public traffic only through the intended edge, or requires mTLS
  from it. **This is A9 in `control-inheritance.md`, confirmed open**

#### O-47

- **Category:** SP-09 Runtime Configuration and Control-Plane Drift
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Forwarded headers (`X-Forwarded-*`) are honored only when received from
  the known proxy hop, and client-supplied correlation IDs are sanitized before being logged.
- **Verification target:** the reverse-proxy/edge trust configuration and the middleware that
  parses forwarded headers and correlation IDs (`CorrelationMiddleware`).
- **Failure oracle:** A forwarded header or correlation ID supplied directly by a client (bypassing
  the known proxy hop) is honored or logged unsanitized.
- **Negative control:** not determined
- **Trigger:** every inbound request
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Forwarded headers are honored only from the known proxy hop; client-supplied
  correlation IDs are sanitized before logging

#### O-85

- **Category:** SP-09 Runtime Configuration and Control-Plane Drift
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** Auth, database, CDN, WAF, object-store, queue, CORS, redirect, logging,
  retention, and backup settings held only in vendor dashboards match an approved baseline.
- **Verification target:** the live configuration of each named vendor dashboard/control plane
  (auth provider, database, CDN, WAF, object store, queue, CORS/redirect config, logging,
  retention, backup settings), exported or queried.
- **Failure oracle:** An exported or queried dashboard setting diverges from its approved baseline
  without a recorded, approved change.
- **Negative control:** not determined
- **Trigger:** on a defined cadence (cadence not stated in this row)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Auth, database, CDN, WAF, object-store, queue, CORS, redirect, logging, retention,
  and backup settings held in dashboards are exported or queried on a cadence and compared with an
  approved baseline

#### O-86

- **Category:** SP-09 Runtime Configuration and Control-Plane Drift
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** The production deployment has debug behaviors, default credentials,
  permissive CORS, and test tenants disabled.
- **Verification target:** deployed production endpoints, exercised directly (not a fixture), plus
  the `ENVIRONMENT` setting's effect on rate limiting.
- **Failure oracle:** A production endpoint responds with debug output, accepts a default
  credential, honors a permissive CORS origin, exposes a test tenant, or has rate limiting silently
  disabled because `ENVIRONMENT=local`.
- **Negative control:** not determined
- **Trigger:** verified against deployed endpoints (cadence not stated in this row)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Production disables debug behaviors, default credentials, permissive CORS, and test
  tenants, verified against deployed endpoints. Interacts with `ENVIRONMENT=local` silently
  disabling rate limiting

#### O-87

- **Category:** SP-09 Runtime Configuration and Control-Plane Drift
- **Framework ref:** CIS Benchmarks (host, container runtime, reverse proxy subset; explicit in
  this row's Check text)
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** The host, container runtime, and reverse-proxy layers this operator runs
  conform to the applicable CIS Benchmark subset, excluding managed Postgres internals which are
  out of scope as vendor-operated.
- **Verification target:** the deployed host OS configuration, container runtime configuration,
  and reverse-proxy configuration.
- **Failure oracle:** A CIS Benchmark control in the host, container-runtime, or reverse-proxy
  subset is found unmet on the deployed system.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** CIS Benchmark subset for layers we operate: host, container runtime, reverse proxy.
  Not the managed Postgres internals

#### O-115

- **Category:** SP-09 Runtime Configuration and Control-Plane Drift
- **Framework ref:** AISVS Appendix C AC.7.5 + AC.12.4
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** Drift detection compares deployed infrastructure and live workflow
  configuration against signed baselines, and runners processing untrusted or AI-generated
  artifacts are ephemeral and isolated from production credentials.
- **Verification target:** the drift-detection mechanism's comparison output against its signed
  baseline, and the runner configuration (ephemerality, credential scope) for jobs processing
  untrusted or AI-generated artifacts.
- **Failure oracle:** Deployed infrastructure or live workflow configuration diverges from its
  signed baseline without drift detection flagging it, or a runner processing an untrusted or
  AI-generated artifact retains production credentials or persists beyond the job.
- **Negative control:** not determined
- **Trigger:** not determined (drift-detection cadence not stated in this row)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.7.5 + AC.12.4**: drift detection compares deployed infrastructure and live
  workflow configuration against signed baselines; runners processing untrusted or AI-generated
  artifacts are ephemeral and isolated from production credentials

### SP-02 Authorization and Tenancy Isolation

Two mandatory subsections: vertical (role and capability) and horizontal (cross-family).

#### O-05

- **Category:** SP-02
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** A guardian authenticated to family A cannot reach any resource that
  belongs to family B.
- **Verification target:** every resource-bearing router (including cursors, object keys, job
  IDs, and nested relationship IDs), exercised with a family-A guardian token against family-B
  resource IDs.
- **Failure oracle:** a request for a family-B resource ID, made with a family-A guardian's
  credentials, returns anything other than 403 or 404 (for example a 200 with data, or a leak in
  an error body).
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A guardian in family A receives 403/404 for every resource ID from family B,
  enumerated across all resource-bearing routers, including cursors, object keys, job IDs, and
  nested relationship IDs

#### O-06

- **Category:** SP-02
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** cross-family recommendation payloads (ADR-016) expose only an approved
  whitelist of fields, never child identity or reading history.
- **Verification target:** the cross-family recommendation-sharing payload and response schema
  (the ADR-016 feature).
- **Failure oracle:** a cross-family recommendation response contains a field outside the
  approved whitelist, or contains child identity or reading-history data.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Cross-family recommendation payloads (ADR-016) contain only whitelisted fields,
  never child identity or reading history

#### O-07

- **Category:** SP-02
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** a guardian-only token is rejected by every `/admin` route and every
  moderation-threshold mutation.
- **Verification target:** all `/admin`-prefixed routes and all moderation-threshold mutation
  endpoints, exercised with a guardian-only token.
- **Failure oracle:** any `/admin` route or moderation-threshold mutation accepts a guardian-only
  token instead of returning 401/403.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A guardian-only token is rejected by every `/admin` route and every
  moderation-threshold mutation

#### O-08

- **Category:** SP-02
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** every secondary object reference (storybook version, node, assignment,
  cover asset) is authorization-checked at the leaf, not inherited from a parent check.
- **Verification target:** leaf-level access-control logic for storybook version, node,
  assignment, and cover-asset endpoints.
- **Failure oracle:** a leaf resource is reachable without an independent leaf-level
  authorization check, solely because the parent resource's check passed.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every secondary object reference (storybook version, node, assignment, cover asset)
  is authorization-checked at the leaf, not inherited from a parent check

#### O-09

- **Category:** SP-02
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** background workers connect to the database using a least-privilege
  role subject to RLS, not the service key.
- **Verification target:** the deployed background-worker process's Postgres connection
  role/DSN.
- **Failure oracle:** a background worker's deployed session connects as the service key, the
  table owner, or any role with `rolbypassrls` set, rather than a scoped least-privilege role
  subject to RLS.
- **Negative control:** `tests/integration/test_worker_role_posture.py::
  test_posture_on_a_migrated_schema_separates_the_bypass_paths[pre-cutover-table-owner]` connects
  as the baseline dump's `postgres` owner role (no `rolsuper`, no `rolbypassrls`, owner of every
  RLS-enabled table) and asserts the probe reports a bypass via the ownership path. That is the
  failure oracle above, fired deliberately, so the measurement is known to be capable of
  reporting the bad state rather than only ever reporting the good one.
- **Trigger:** ADR-021 cutover (the Check text names this as the current blocker)
- **Existing coverage:** the gate-coverage audit row "Privacy / RLS correctness" (PARTIAL: yes in
  CI, but RLS is a no-op in production); the cross-cutting gate defects list records that the
  application connects as the Postgres table owner pre-cutover, which is the specific gap this
  row targets. PR #608 adds the runtime half: the worker probes its own engine once per process
  start and logs `generation_worker.role_least_privileged` /
  `generation_worker.role_bypasses_rls` / `generation_worker.rls_posture_unknown`, so the
  verification target is now observable from the deployed process itself instead of requiring a
  `pg_stat_activity` snapshot timed to a live job.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** finding open
- **Check:** Background workers connect with a least-privilege role subject to RLS, not the
  service key. Blocked on the ADR-021 cutover.

  Two reasons this stays open even though a runtime signal now exists. First, the signal is a log
  line an operator has to read; nothing gates on it, by design, so an unread affirmative event is
  not a verification. Second, and more specifically: `CYO_ADVENTURE_WORKER_DATABASE_URL` is unset
  in production, so the worker reaches a least-privilege role only by falling back to the API DSN
  and connecting as `cyo_api`. That satisfies the failure oracle's letter (not the owner, not a
  superuser, no `rolbypassrls`) while leaving the queue path on the request path's credential,
  which is the separation this row exists to assert. Closing it needs the worker DSN set
  explicitly and a startup line showing `role=cyo_worker` with
  `worker_dsn_explicitly_set=true`.

#### O-77

- **Category:** SP-02
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** the production database connection's identity (`current_user`,
  `rolbypassrls`, table ownership) is asserted from the deployed session, not assumed from a
  fixture.
- **Verification target:** the deployed production session's `current_user`, `rolbypassrls`
  flag, and table ownership.
- **Failure oracle:** the deployed session shows `current_user` as the table owner, or a role
  with `rolbypassrls = true`, rather than the intended scoped, RLS-subject role.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** the current RLS enforcement test suite, which the cross-cutting gate
  defects list describes as forcing the `cyo_api` role in its own fixture and therefore
  "structurally cannot observe" the deployed connection identity. This row is named in the Check
  text as its non-hollow replacement.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The **production** connection identity is asserted from the deployed session
  (`current_user`, `rolbypassrls`, table ownership), not from a fixture. The non-hollow
  replacement for the current RLS suite

#### O-78

- **Category:** SP-02
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** every RLS policy has a mutation test that fails when the policy is
  removed.
- **Verification target:** RLS policies defined under `supabase/migrations/` and their paired
  test suite.
- **Failure oracle:** dropping an RLS policy does not turn any test red; the full test suite
  remains green.
- **Negative control:** dropping the RLS policy under test (stated directly in the Check text).
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every RLS policy has a mutation test: dropping the policy turns at least one test
  red

### SP-01 Identity, Authentication, Session Lifecycle

Two mandatory subsections, because this system has two independent session lifecycles.

*Adult, OIDC:*

#### O-02

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** JWT verification rejects a wrong `iss`, a wrong `aud`, an `alg`
  substitution attack, and an unknown `kid`, and the verifier refreshes its JWKS cache on key
  rotation.
- **Verification target:** the JWT/OIDC verification logic covered by
  `tests/unit/test_oidc_verification.py`, and the JWKS-refresh path.
- **Failure oracle:** a token with a wrong `iss`, wrong `aud`, substituted `alg`, or unknown `kid`
  is accepted, or a rotated JWKS key is never picked up by the verifier.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** `tests/unit/test_oidc_verification.py` (Check text states this is
  "largely covered").
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** JWT verification rejects wrong `iss`, wrong `aud`, `alg` substitution, unknown
  `kid`, and refreshes JWKS on rotation. Largely covered by
  `tests/unit/test_oidc_verification.py`

#### O-03

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** adult elevation has both an absolute timeout and an idle timeout, and
  the elevated state is never persisted to durable storage.
- **Verification target:** the adult elevation/step-up mechanism and its timeout configuration.
- **Failure oracle:** elevated state remains valid past its absolute or idle timeout, or elevated
  state is found written to durable storage (database, disk, or a durable cache).
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Adult elevation has absolute and idle timeouts and is not persisted to durable
  storage

#### O-42

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** the deployed issuer, audience, signing algorithms, redirect and
  callback URIs, MFA policy, non-enumerable-response behavior, and account-linking settings match
  an exported approved baseline.
- **Verification target:** the deployed identity-provider configuration, exported or queried from
  the provider's control plane (not visible from source review because auth is delegated).
- **Failure oracle:** any exported/queried provider setting diverges from the approved baseline
  (for example, an added redirect URI, a weakened signing algorithm, MFA disabled, or an
  enumerable error response).
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Deployed issuer, audience, signing algorithms, redirect and callback URIs, MFA
  policy, non-enumerable responses, and account-linking settings match an exported approved
  baseline. Invisible to source-based review because auth is delegated

#### O-43

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** no self-service path grants `is_admin`; elevation happens only
  out-of-band and is audit-logged.
- **Verification target:** all account/profile mutation endpoints and the admin-elevation
  process's audit log.
- **Failure oracle:** any self-service API call sets `is_admin` to true, or an elevation occurs
  with no corresponding audit-log entry.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** No self-service path grants `is_admin`; elevation is out-of-band and audit-logged

#### O-100

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** password reset, email change, and recovery cannot be used to acquire
  membership in another family or to retain sessions issued before the change, and reset tokens
  have bounded expiry.
- **Verification target:** the provider-hosted (Supabase-hosted) password reset, email-change,
  and recovery flow, exercised end-to-end rather than through a mocked callback.
- **Failure oracle:** after a reset/email-change/recovery flow, the account is associated with a
  different family, a pre-change session token remains valid, or a reset/recovery token remains
  valid past its bound.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** the gate-coverage audit row "Password reset / enumeration" (PARTIAL:
  covered on PR runs, not enforced in the merge queue).
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Password reset, email change, and recovery cannot acquire another family or retain
  old sessions, with bounded token expiry, exercised through the **provider-hosted** flow rather
  than a mocked callback

*Child, device grant:*

#### O-01

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** revoking a device grant immediately terminates any in-flight child
  session tied to it and blocks reissuance of a new child session within a stated bound.
- **Verification target:** the device-grant revocation path exercised in
  `tests/integration/test_child_sessions.py`, specifically the assertion pinned at line 792.
- **Failure oracle:** after a device grant is revoked, a previously minted child token remains
  valid, or a new child session can be issued against the revoked grant. Currently observed: a
  revoked grant leaves a minted child token valid for up to 12 hours.
- **Negative control:** revoking an active device grant while a minted child token is still
  within its validity window (the case pinned at `test_child_sessions.py:792`).
- **Trigger:** not determined
- **Existing coverage:** `tests/integration/test_child_sessions.py:792`, which the Check text
  says pins the gap rather than closing it.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** finding open
- **Check:** Revoking a device grant terminates in-flight child sessions and blocks reissue
  within a stated bound. Known gap pinned at `tests/integration/test_child_sessions.py:792`: a
  revoked grant leaves a minted child token valid up to 12h

#### O-04

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** offline reading mode enforces a maximum offline-validity window, and
  the client is forced to re-verify with the server on reconnect.
- **Verification target:** the offline-mode validity-window enforcement logic and the reconnect
  re-verification path.
- **Failure oracle:** a client remains usable offline past the maximum validity window, or
  reconnecting does not trigger server re-verification.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Offline mode enforces a maximum offline validity window and forces server
  re-verification on reconnect

#### O-101

- **Category:** SP-01
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** the 4-digit child PIN is protected by an attempt cap, or by a
  documented and accepted compensating control if no cap exists.
- **Verification target:** `api/child_sessions.py:159-167`, the PIN-check/attempt logic.
- **Failure oracle:** the PIN can be attempted an unbounded number of times, with no attempt cap
  and no documented, accepted compensating control in place.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none (Check text states the code "currently declines a cap").
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** finding open
- **Check:** The 4-digit PIN has an attempt cap or a documented, accepted compensating control.
  `api/child_sessions.py:159-167` currently declines a cap

### SP-05 Client-Side Storage, Offline Sync, Client Surface

Two mandatory subsections: data at rest (confidentiality) and sync (integrity).

#### O-39

- **Category:** SP-05
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Offline client-side stores (IndexedDB, Cache Storage, localStorage) are keyed
  per profile, purged on logout and on device-grant revocation, and hold no authentication secret.
- **Verification target:** the frontend offline storage layer (`frontend/src/offline/`) and its
  IndexedDB, Cache Storage, and localStorage usage
- **Failure oracle:** a store found shared across profiles rather than keyed per profile, a store
  not purged after logout or grant revocation, or an authentication secret or token found in
  client-side storage
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** none. The Check text records "Currently NOT COVERED", matching the
  existing-gate-coverage table's "Client-side data at rest: NOT COVERED, Nothing to fail"
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Offline stores are keyed per profile, purged on logout and grant revocation, and hold no
  auth secret. Currently NOT COVERED

#### O-40

- **Category:** SP-05
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** the service worker carries a versioned kill-switch and never caches an
  authenticated response under a profile-agnostic cache key.
- **Verification target:** the frontend service worker and its cache-key scheme
- **Failure oracle:** an authenticated response found cached under a key that is not scoped to a
  profile, or no mechanism exists to version or invalidate the service-worker cache
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** none, per the existing-gate-coverage table's "Client-side data at rest:
  NOT COVERED, Nothing to fail"
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The service worker has a versioned kill-switch and never caches authenticated responses
  in a profile-agnostic key

#### O-41

- **Category:** SP-05
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** switching profiles on a shared device evicts the previous profile's cached
  content and player state.
- **Verification target:** the client-side profile-switch flow and its cache and player-state
  eviction behavior
- **Failure oracle:** after a profile switch, cached content or player state belonging to the
  previous profile remains readable
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** none, per the existing-gate-coverage table's "Client-side data at rest:
  NOT COVERED, Nothing to fail"
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Switching profiles evicts the previous profile's cached content and player state

#### O-50

- **Category:** SP-05
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** on reconnect, the server treats client-supplied offline state as untrusted
  and re-authorizes it before accepting it.
- **Verification target:** the server-side sync or reconnect endpoint that ingests client-reported
  offline state
- **Failure oracle:** a tampered client payload claiming a gated level was completed, or claiming
  approval, is accepted by the server rather than rejected
- **Negative control:** a tampered payload claiming a gated level was completed, or claiming
  approval (named directly in the Check text)
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** On reconnect the server treats client-supplied state as untrusted and **re-authorizes
  it**. Negative control: a tampered payload claiming a gated level was completed, or claiming
  approval, is rejected

#### O-51

- **Category:** SP-05
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** sync conflict resolution cannot move reading history, choices, ratings, or
  stories between children or between families.
- **Verification target:** the sync conflict-resolution logic, server and client sides
- **Failure oracle:** a sync conflict resolves in a way that attributes or transfers reading
  history, choices, ratings, or story access from one child or family to another
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Sync conflict resolution cannot move reading history, choices, ratings, or stories
  between children or families

#### O-75

- **Category:** SP-05
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** a documented inventory names every child-data element stored in
  IndexedDB, Cache Storage, localStorage, and service-worker caches, with purpose and expiry
  recorded for each.
- **Verification target:** a client-storage data inventory document (none currently exists)
- **Failure oracle:** a child-data element found in client-side storage that is not named in the
  inventory, or an inventory entry missing a stated purpose or expiry
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** none. The section's trailing note states "Nothing currently asserts a
  policy over client storage and no lint rule restricts `localStorage`"
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A documented inventory names every child-data element in IndexedDB, Cache Storage,
  localStorage, and service-worker caches, with purpose and expiry

#### O-76

- **Category:** SP-05
- **Framework ref:** MASVS L1 / MASVS-PRIVACY (named directly in the Check text; corroborated by
  the sub-scope exclusion table's "MASVS | SP-05 | No native or wrapped mobile client yet | Mobile
  wrapper enters design (R2)")
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** the mobile client, once built, conforms to MASVS L1 plus the
  MASVS-PRIVACY subset.
- **Verification target:** not determined. No native or wrapped mobile client exists yet; the
  verification target is the future mobile wrapper, not yet built.
- **Failure oracle:** not determined. Conformance cannot be assessed before the mobile wrapper
  exists.
- **Negative control:** none
- **Trigger:** R2, when the mobile wrapper enters design (per the Check text and the sub-scope
  exclusion table's reassessment trigger)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** verification scheduled
- **Check:** MASVS L1 plus the MASVS-PRIVACY subset activates when the mobile wrapper enters design

`personalization_values` in IndexedDB holds children's real first names, sibling names, and kinship
labels. Nothing currently asserts a policy over client storage and no lint rule restricts
`localStorage`.

### SP-03 Input Validation, Encoding, Injection

#### O-102

- **Category:** SP-03
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** every externally writable field, including generated model output, is
  constrained server-side by a defined type, length, structural constraint, normalization rule, and
  rejection behavior; state-changing forms carry CSRF protection; non-serializable internal values
  are transformed at the API boundary.
- **Verification target:** the FastAPI request and response schema layer (Pydantic models) and the
  API-boundary serialization and validation code across all routers
- **Failure oracle:** a writable field, including generated story content, accepted without its
  defined type, length, or structural constraint; a state-changing form found without CSRF
  protection; or a non-serializable internal value crossing the API boundary unconverted
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every externally writable field, **including generated model output**, has a defined
  type, length, structural constraint, normalization rule, and rejection behavior enforced
  server-side. Includes CSRF protection on state-changing forms and transformation of
  non-serializable internal values at the API boundary [Secondary class recorded in the source
  table: DYNAMIC.]

#### O-103

- **Category:** SP-03
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** child-visible text is rendered with context-appropriate encoding, so
  stored HTML, script, URL, Markdown, Unicode-control, and bidirectional-text payloads remain inert
  on every child-facing surface.
- **Verification target:** every child-facing rendering surface (reader and player UI, story
  content display)
- **Failure oracle:** a stored HTML, script, URL, Markdown, Unicode-control, or bidirectional-text
  payload executes, renders as markup, or alters display or reading order on a child-facing surface
  instead of rendering inert
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Child-visible text is rendered with context-appropriate encoding; stored HTML, script,
  URL, Markdown, Unicode-control, and bidirectional-text payloads remain inert on every child-facing
  surface

#### O-104

- **Category:** SP-03
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** parsing failures, malformed story graphs, oversized payloads, duplicate
  identifiers, and recursive structures fail predictably, without partial writes or internal error
  disclosure, and without permitting OS command injection or remote code execution.
- **Verification target:** the story-graph and Storybook ingestion and parsing paths
  (`generation/`, `storybook/`, `validator/`)
- **Failure oracle:** a malformed graph, oversized payload, duplicate identifier, or recursive
  structure produces a partial write, discloses internal error detail, or reaches an OS command
  injection or remote-code-execution path
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Parsing failures, malformed graphs, oversized payloads, duplicate identifiers, and
  recursive structures fail predictably without partial writes or internal error disclosure.
  Includes OS command injection and RCE paths

### SP-04 Business Logic and Abuse Resistance

#### O-10

- **Category:** SP-04
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** story-request creation enforces a per-family windowed generation budget
  that is independent of HTTP-layer rate limits.
- **Verification target:** the story-request creation endpoint and its budget-enforcement logic
  (`story_requests/`)
- **Failure oracle:** a family creates story requests beyond the windowed generation budget while
  HTTP rate limits alone are not exercised or are bypassed
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Story-request creation enforces a per-family windowed generation budget independent of
  HTTP rate limits

#### O-11

- **Category:** SP-04
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** the publish state machine is the sole writer of reader-visible story
  state; no other code path mutates it.
- **Verification target:** the `publishing/` state machine and every other code path that could
  write reader-visible storybook state
- **Failure oracle:** reader-visible state is found mutated by a code path other than the publish
  state machine
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The publish state machine is the only writer of reader-visible state

#### O-12

- **Category:** SP-04
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** concurrent approve attempts and concurrent grant-redeem attempts converge
  on a single terminal state under load, without a double-approval or double-redemption outcome.
- **Verification target:** the approval workflow and the device-grant redemption workflow under
  concurrent load
- **Failure oracle:** concurrent approve or concurrent grant-redeem requests produce more than one
  terminal state, for example a story approved twice or a device grant redeemed more than once
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Concurrent approve and concurrent grant-redeem attempts converge on a single terminal
  state under load

#### O-13

- **Category:** SP-04
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** flag submission is idempotent per actor-target pair and is rate-shaped.
- **Verification target:** the flag-submission endpoint (`api/flags`)
- **Failure oracle:** a repeated flag submission from the same actor against the same target
  creates duplicate records, or flag submission is not rate-shaped
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Flag submission is idempotent per actor-target pair and rate-shaped

### SP-06 API Surface, Egress, SSRF

#### O-21

- **Category:** SP-06
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** outbound URL fetches are restricted to an allowlist and reject
  link-local, metadata, and private IP ranges, checked after DNS resolution and after following
  redirects.
- **Verification target:** `middleware/security.py` `_is_blocked_url` and the outbound-fetch
  allowlist enforcement path
- **Failure oracle:** an outbound fetch reaches a link-local, metadata, or private-range address
  after DNS resolution or redirect, or `_is_blocked_url` returns not-blocked when host parsing
  fails
- **Negative control:** a host string that fails parsing in `_is_blocked_url`, which the Check text
  records as currently returning not-blocked; this is a confirmed open defect, not a hypothetical
- **Trigger:** not established; the defect is recorded from source reading, not surfaced by an
  automated check
- **Existing coverage:** none. This is a confirmed open defect in `middleware/security.py`
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** finding open
- **Check:** Outbound URL fetches use an allowlist and reject link-local, metadata, and private
  ranges **after** DNS resolution and redirects. Known defect: `middleware/security.py`
  `_is_blocked_url` returns not-blocked when host parsing fails

#### O-79

- **Category:** SP-06
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** the deployed route inventory, its methods, auth dependencies, and
  audience designation are enumerated and reconciled against intent; no undocumented or
  accidentally public route exists.
- **Verification target:** the FastAPI route registration surface (`app.py`, 32 `include_router`
  calls) and each router's auth dependencies
- **Failure oracle:** a route is found in the deployed inventory that is undocumented, has no
  matching intent record, is accidentally public, or an orphaned endpoint (no longer called by any
  UI) remains reachable
- **Negative control:** none
- **Trigger:** not established; no verification mechanism currently exists
- **Existing coverage:** not determined
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The deployed route inventory, methods, auth dependencies, and audience designation are
  enumerated and reconciled against intent; undocumented or accidentally public routes are
  reported. Material here: 37 routers, and orphaned endpoints outlive the UI that called them
  [Secondary class recorded in the source table: DYNAMIC.]

URL parsing belongs to input handling; destination authorization belongs to egress. O-21 is owned
here rather than by SP-14 on that basis.

### SP-07 File, Object Storage, Media

#### O-22

- **Category:** SP-07
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** Cover and avatar objects are reachable only via short-lived signed URLs
  or an authorizing proxy, and the bucket denies public listing.
- **Verification target:** the object storage bucket configuration (listing/ACL settings) and the
  URL-signing or authorizing-proxy mechanism that issues access to cover and avatar objects.
- **Failure oracle:** an unauthenticated request lists bucket contents, or a cover or avatar object
  is reachable via a long-lived or unsigned URL, or without passing through the authorizing proxy.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Cover and avatar objects served via short-lived signed URLs or an authorizing proxy;
  the bucket denies public listing

#### O-23

- **Category:** SP-07
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** uploaded images are re-encoded server-side, have EXIF metadata stripped,
  and have their type verified by content sniffing rather than trusted from client-supplied
  metadata.
- **Verification target:** the server-side image upload-handling path for cover and avatar images.
- **Failure oracle:** a stored or served uploaded image retains original EXIF metadata, was not
  re-encoded server-side, or had its type accepted solely from a client-supplied MIME type or
  filename extension.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Uploaded images are re-encoded server-side, EXIF stripped, and type-sniffed rather
  than trusted

#### O-80

- **Category:** SP-07
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** object keys for family media cannot be predicted or substituted to reach
  another family's media, and authorization is checked before every signed URL is issued rather
  than being implied by the key name.
- **Verification target:** the object-key generation scheme and the authorization check performed
  at signed-URL issuance time for cover and avatar objects.
- **Failure oracle:** a request for a signed URL to another family's object succeeds without an
  authorization check, or an object key from one family predictably yields, or can be substituted
  to reach, another family's object.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Object keys cannot be predicted or substituted to reach another family's media;
  authorization is checked before every signed URL is issued, not embedded in the key name

### SP-08 Cryptography, Secrets, Key Management, Transport

#### O-88

- **Category:** SP-08
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** secrets are absent from source, client bundles, container images, logs,
  generated stories, prompts, and build artifacts; deployed secrets each have a recorded owner,
  scope, rotation procedure, and a tested revocation path; webhook signature verification uses
  production secrets rather than test-mode secrets.
- **Verification target:** the source tree, client bundle build output, container images, log
  output, generated story artifacts, prompts, and build artifacts, plus the deployed secret
  inventory (owners, scopes, rotation, revocation) and the webhook signature-verification code
  path.
- **Failure oracle:** a secret value is found in source, a client bundle, a container image, a log
  line, generated story content, a prompt, or a build artifact; or a deployed secret lacks a
  recorded owner, scope, rotation procedure, or revocation test; or webhook signature verification
  accepts a test-mode secret in production.
- **Negative control:** none
- **Trigger:** push to the repository (GitHub secret scanning push protection) and pull request
  open or update (GitGuardian Security Checks); no stated trigger for the deployed-secret
  owner/scope/rotation/revocation half of this check.
- **Existing coverage:** GitHub secret scanning, push protection, and validity checks are enabled
  at repository level, and `GitGuardian Security Checks` runs on pull requests (corrected in this
  register's own "Existing gate coverage" audit, which also notes an earlier, wrong claim of "no
  CI secret scanning"; push protection refuses the push rather than reporting after the fact). A
  local pre-commit `detect-secrets` hook also runs, but the `pre-push` hook tier is not installed
  per this register's Cross-cutting gate defects, so `detect-secrets` there does not run. No
  coverage is recorded for the deployed-secret owner/scope/rotation/revocation half of this check.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Secrets absent from source, client bundles, images, logs, generated stories, prompts,
  and build artifacts; deployed secrets have owners, scopes, rotation procedures, and revocation
  tests. Includes webhook signature verification using production rather than test-mode secrets
  (Secondary class: RUNTIME-CONFIG, for the deployed secret inventory: owners, scopes, rotation,
  and revocation state, which lives in the vendor control plane rather than in source.)

#### O-89

- **Category:** SP-08
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** TLS policy, origin certificate validation, HSTS, redirect behavior, and
  backend-to-provider transport hold when verified from an external vantage point, outside the
  trust boundary being described.
- **Verification target:** the deployed TLS chain (Cloudflare Tunnel `cloudflared`, Pangolin, and
  the nginx origin, per `crypto-inventory.md` section 2, lines 61 to 69) and backend-to-provider
  egress TLS (OpenRouter, Anthropic, Gemini, Supabase JWKS, Modal).
- **Failure oracle:** a check run from inside the network, or against an internal or loopback
  endpoint, is credited as verifying external TLS posture; or TLS policy, certificate validation,
  HSTS, or redirect behavior fails when probed from outside the network.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** `crypto-inventory.md` section 2 documents the TLS chain and names a
  "negotiated-group check" as the `homelab-infra` acceptance test for edge-to-origin PQC; that
  test lives in `homelab-infra`, not this repository, and no gate in this repository verifies TLS
  posture from an external vantage point.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** TLS policy, origin certificate validation, HSTS, redirect behavior, and backend-to-
  provider transport verified **from an external vantage point**

#### O-90

- **Category:** SP-08
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** every encryption-at-rest claim in this register names the specific threat
  it addresses, and vendor disk encryption is not credited with protecting against application or
  administrator access, which it does not address.
- **Verification target:** encryption-at-rest claims recorded elsewhere in this register and in
  `crypto-inventory.md`, checked against the threat model each actually covers.
- **Failure oracle:** a row or document credits vendor disk or volume encryption with protecting
  against application-level or administrator access, when disk encryption protects only against
  physical media loss.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Encryption-at-rest claims identify the threat actually addressed. Where vendor disk
  encryption does not protect against application or administrator access, the register does not
  credit it as solving that different threat

O-89 encodes the verification vantage rule from `control-inheritance.md`: a control describing
posture at a trust boundary must be verified from outside that boundary.

### SP-11 Logging, Audit Integrity, Alerting, Incident Response

#### O-28

- **Category:** SP-11
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** the events table grants the application role no UPDATE or DELETE
  privilege, and each entry carries a chained digest linking it to the prior entry.
- **Verification target:** the Postgres role privileges granted on the events table, and the
  chained-digest computation in the events-writing code path.
- **Failure oracle:** the application role can execute an UPDATE or DELETE against the events
  table, or an entry's digest does not chain to, or fails to validate against, the prior entry.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The events table grants no UPDATE or DELETE to the application role; entries carry a
  chained digest

#### O-29

- **Category:** SP-11
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** no child identifier, story body, or token appears anywhere in log output,
  as asserted by an emitted-field allowlist test using seeded sensitive markers.
- **Verification target:** the emitted-field allowlist test and the log-emission code paths it
  exercises.
- **Failure oracle:** a seeded child identifier, story body, or token marker appears in log output
  and the allowlist test does not catch it.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** `tests/unit/test_logging_security.py` partially overlaps: it verifies
  bearer tokens are absent from authentication-failure log output, but does not test child
  identifier or story body fields, so it does not fully cover this row's claim.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** An emitted-field allowlist test asserts no child identifier, story body, or token
  appears in log output, verified with seeded sensitive markers

#### O-30

- **Category:** SP-11
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** named detections exist for approval-bypass attempts, 403 spikes, and
  moderation-provider outage, and each has a routed recipient.
- **Verification target:** the deployed alerting or monitoring configuration (vendor control
  plane) where these named detections and their routed recipients are configured.
- **Failure oracle:** an approval-bypass attempt, a 403 spike, or a moderation-provider outage
  occurs and no corresponding detection fires, or fires without reaching a routed recipient.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Named detections exist for approval-bypass attempts, 403 spikes, and
  moderation-provider outage, each with a routed recipient

#### O-91

- **Category:** SP-11
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** a synthetic high-value event, injected end to end, traverses the
  deployed alerting pipeline to its actual maintained destination and is acknowledged by the
  named responder.
- **Verification target:** the deployed alerting pipeline end to end, from event source through to
  the maintained destination and the named responder, not a unit-level assertion that a logger
  function was invoked.
- **Failure oracle:** a synthetic high-value event fails to reach the actual maintained
  destination, or reaches it but no named responder acknowledges it, or the only evidence offered
  is that a logging call occurred.
- **Negative control:** none
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A synthetic high-value event traverses the **deployed** pipeline to the actual
  maintained destination and is acknowledged by the named responder. Verifying that a logger was
  called does not satisfy this

#### O-92

- **Category:** SP-11
- **Framework ref:** not determined
- **Legal ref:** State breach notification (all US states); GDPR Art. 33-34 (once EU users exist)
- **Class:** MANUAL
- **Protected property:** the incident plan can trace a child-data event across edge, application,
  identity provider, database, queue, model provider, object storage, and client sync, and
  includes state breach-notification decision points, plus GDPR Art. 33/34 decision points once EU
  users exist.
- **Verification target:** the incident response plan or runbook document.
- **Failure oracle:** the incident plan cannot trace a child-data event through one or more of the
  named components, lacks a decision point for state breach notification, or, once EU users exist,
  lacks a decision point for GDPR Art. 33/34.
- **Negative control:** none
- **Trigger:** first non-household user, which is when state breach notification attaches per this
  register's regulatory applicability table; first EU or UK child or guardian, which is when GDPR
  attaches per the same table, for the Art. 33/34 portion.
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The incident plan can trace a child-data event across edge, application, identity
  provider, database, queue, model provider, object storage, and client sync, and includes state
  breach-notification decision points, plus Art. 33/34 once EU users exist

#### O-116

- **Category:** SP-11
- **Framework ref:** AISVS 1.0 Appendix C, AC.14 (Compromise containment for AI-in-pipeline),
  requirements AC.14.1 to AC.14.3
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** an AI-in-pipeline compromise playbook exists; any secret touched by a
  suspect workflow run is rotated automatically; agent identities can be revoked within a written,
  annually tested target time.
- **Verification target:** the compromise-containment playbook document, the automated
  secret-rotation mechanism triggered by a suspect workflow run, and the agent-identity revocation
  mechanism plus its annual test record.
- **Failure oracle:** no compromise playbook exists for an AI-in-pipeline incident; a secret
  touched by a suspect workflow run is not rotated automatically; or agent-identity revocation has
  no written target time, or that target time has not been tested within the past year.
- **Negative control:** none
- **Trigger:** annual test cadence, per the Check text's "annually tested target time"
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** **AC.14.1-AC.14.3**: an AI-in-pipeline compromise playbook exists; any secret touched
  by a suspect workflow run is rotated automatically; agent identities can be revoked within a
  written, annually tested target time

#### O-120

- **Category:** SP-11
- **Framework ref:** not determined
- **Legal ref:** NY SHIELD Act (NY General Business Law §899-bb, amending §899-aa); Massachusetts
  201 CMR 17.00 (Standards for the Protection of Personal Information of Residents of the
  Commonwealth, M.G.L. c. 93H)
- **Class:** MANUAL
- **Protected property:** A written information security program exists covering NY and MA
  residents' statutorily-defined private/personal information (see Trigger below for the
  data-class gate this depends on), not only children's: reasonable administrative, technical, and
  physical safeguards (SHIELD, GBL §899-bb(2)(a); a small business may instead meet a safeguards
  standard "appropriate for the size and complexity of the small business, the nature and scope of
  [its] activities, and the sensitivity of the personal information [it] collects", GBL
  §899-bb(2)(c), the more favorable route if CYO Adventure qualifies), and, once a Massachusetts
  resident whose 201 CMR-defined personal information CYO holds exists, 201 CMR 17.04's eight named
  technical requirements, not the four this row previously listed: secure user authentication
  protocols, access control restricting personal information to need-to-know, encryption of records
  transmitted across public networks, encryption of data transmitted wirelessly, reasonable
  monitoring for unauthorized access, up-to-date firewalls and OS security patches, up-to-date
  malware protection, and employee training (201 CMR 17.04(1)-(8)). **The statute itself qualifies
  all eight**: 17.04's chapeau requires them "at a minimum, and to the extent technically feasible,"
  a standard that shifts with available technology rather than a flat mandate; a control found
  genuinely infeasible does not fail this row if a documented risk analysis and mitigation covers
  the gap, but "infeasible" is a high bar in practice (regulators have rejected affordability/burden
  arguments for the encryption items specifically) and is not a default to reach for. Encryption of
  personal information stored on laptops or other portable devices is one of the eight (17.04(5)); a
  blanket "encrypt the primary database at rest" mandate is not itself one of them, and is a project
  control choice rather than a 201 CMR requirement.
- **Verification target:** The written information security program document, checked specifically
  for statutorily-defined-data-class scope (not the COPPA-scoped, children-only program at O-61),
  and, once an MA resident whose covered personal information CYO holds exists, all eight 201 CMR
  17.04 technical controls named above in the deployed system (or a documented feasibility-based
  risk analysis and mitigation in place of any control found genuinely infeasible), not a generic
  "data is encrypted" claim or a four-item subset.
- **Failure oracle:** A NY or MA resident's statutorily-defined private/personal information is
  collected with no written security program covering it, or, once an MA resident whose covered
  information CYO holds exists, the program is missing one of 201 CMR 17.04's eight named
  requirements with no documented feasibility-based risk analysis and mitigation covering the gap,
  or this row's evidence substitutes general at-rest database encryption for the statute's actual
  eight-item scope.
- **Negative control:** not determined
- **Trigger:** Two independent gates, not one, and this row previously collapsed them. **(1) A data-class
  gate, keyed on the statutes' own defined terms, not on residency alone**: NY SHIELD attaches to
  "private information" (GBL 899-aa(1): a name plus SSN, driver's license number, a financial-account,
  credit-card, or debit-card number, biometric data, or a username/email combined with a password or
  security question and answer); MA 201 CMR attaches to "personal information" (201 CMR 17.02: a
  Massachusetts resident's name plus SSN, driver's license/state-ID number, or a financial-account,
  credit-card, or debit-card number). **Neither statute requires an accompanying security code,
  access code, PIN, or password for the card/account prong**; both cover the bare number combined
  with a name (confirmed against 201 CMR 17.02's own "with or without any required security code,
  access code, personal identification number or password" text; a prior version of this row
  incorrectly implied an access-credential requirement for both statutes). Per T1 above, CYO
  Adventure holds none of SSN, driver's license, financial-account/card, or biometric data; the one
  plausible match is T1's "guardian email and auth identity" against NY's username-plus-credential
  prong, an open question, not a resolved one, this row records rather than answers. If that prong
  does not resolve in the affirmative, SHIELD may not attach even after a NY resident is onboarded,
  and 201 CMR's definition has no comparable email-plus-password prong at all, so 201 CMR may not
  attach on CYO's current data classes regardless of residency. **(2) The residency/operating-condition
  gate**, in the same sense every other state-law trigger in this register uses "household": a
  marker of this project's own current single-family operating condition, not a term either statute
  defines or exempts by. The two statutes do not attach identically once that marker clears.
  **NY SHIELD's reasonable-safeguards duty (GBL §899-bb(2)(a), not §899-bb(1)(a), which defines
  "compliant regulated entity") has no size, revenue, or commercial-context carve-out**: it applies
  to "any person or business that owns or licenses computerized data" including a NY resident's
  private information, though §899-bb(2)(c)'s small-business scaled standard (see Protected property
  above) is the more favorable outcome if it applies. **MA 201 CMR 17.00 is narrower on its face**:
  "owns or licenses" is defined at 201 CMR 17.02 as receiving, storing, maintaining, processing, or
  otherwise having access to personal information "in connection with the provision of goods or
  services or in connection with employment". Rest the point on that definition rather than on the
  Commonwealth's FAQ guidance, which says the same thing (the regulation does not reach a natural
  person managing personal or household information outside a commercial or employment context) but
  is informal guidance this register cannot cite to a stable, verifiable location; 17.02's own text
  carries the substance, so the FAQ is corroboration and not the basis. Whether a single-family
  homelab deployment already sits
  outside 201 CMR's scope on that basis, independent of both the data-class gate and whether an MA
  resident has ever been onboarded, is a genuinely open, more favorable question than SHIELD's and
  has not been asked of counsel; do not assume either statute is equally deferred by the same
  household framing, and do not assume either gate alone is sufficient without the other.
- **Existing coverage:** none. O-61's written children's-data security program (COPPA §312.8) is
  adjacent but does not satisfy this row on its own: SHIELD and 201 CMR protect residents' data as
  each statute's own data-class definition scopes it (see Trigger above), not "all" data about a
  resident and not only children's, and 201 CMR's eight specific technical mandates go beyond what
  O-61's Check text names. A single written program could satisfy both rows if scoped and drafted
  to cover both populations and both data-class definitions; that scoping decision has not been
  made, and the data-class gate above should be resolved (with counsel, per T1's own open question)
  before assuming this row is even reachable on CYO's current data.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A written information security program, distinct in scope from O-61's children-only
  program, covers NY and MA residents' statutorily-defined private/personal information (a data
  class T1 may not currently include; see Trigger) with reasonable safeguards (SHIELD Act, GBL
  §899-bb(2)(a), or the §899-bb(2)(c) small-business standard if applicable) and 201 CMR 17.04's
  eight specific technical requirements, each "at a minimum, and to the extent technically feasible"
  per the statute's own chapeau (secure authentication, access control, public-network and wireless
  transmission encryption, monitoring, firewall/patching, malware protection, employee training, and
  portable-device storage encryption; not a four-item subset and not a blanket at-rest mandate), in
  place before the first NY or MA resident outside the operator's household,
  whose data meets the applicable statute's data-class definition, is onboarded. Filed under SP-11
  rather than SP-13 because, unlike O-61 and the state minors' design codes at O-94/O-97, neither
  statute is a protected-population duty: both attach, subject to the data-class gate above, to any
  resident's covered information regardless of age. Whether MA 201 CMR already sits outside scope
  for a single-family deployment independent of the household trigger is a distinct, open question
  the Trigger field above records rather than answers

### SP-12 Data Lifecycle, Rights, Processors, Transfers

#### O-31

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** COPPA (16 CFR 312; per the regulatory-applicability table row mapping COPPA to
  this ID, not named in the Check text itself)
- **Class:** MANUAL
- **Protected property:** Personal data (including children's data) is completely removable from
  every store that holds it, within the stated SLA.
- **Verification target:** The erasure runbook document plus the stores it enumerates: Postgres,
  R2, Redis payloads, retained raw LLM output, offline IndexedDB on family devices, backups.
- **Failure oracle:** A test deletion leaves residue in any enumerated store, or completes outside
  the stated SLA.
- **Negative control:** not determined (Check text does not describe a deliberately seeded
  residual record used to prove the test deletion can fail)
- **Trigger:** not determined (no cadence or event named in Check text)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** An erasure runbook enumerates every store (Postgres, R2, Redis payloads, retained raw
  LLM output, offline IndexedDB on family devices, backups) and a test deletion demonstrates
  residue-free removal within the stated SLA

#### O-32

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Every data class has a bounded retention period enforced by an
  automated mechanism, not merely a stated policy.
- **Verification target:** The TTL/retention configuration per data class and the reaper job's
  execution evidence (last successful run record).
- **Failure oracle:** A data class exists with no stated TTL, or a stated TTL exists with no
  automated reaper, or the reaper's last successful run cannot be evidenced.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every data class has a stated TTL with an automated reaper and evidence of its last
  successful run

#### O-33

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** MANUAL
- **Protected property:** Backups are demonstrably restorable, not merely taken.
- **Verification target:** The scratch-environment restore record/log for the most recent
  quarter.
- **Failure oracle:** No restore record exists within the last quarter, or the recorded restore
  did not target a scratch environment separate from production.
- **Negative control:** not determined
- **Trigger:** Quarterly (per Check text: "within the last quarter")
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** An actual restore into a scratch environment was performed and recorded within the
  last quarter

#### O-34

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** not determined (Check text says only "the statutory window" without naming which
  regime; several regimes in the spine's catalog could apply)
- **Class:** DYNAMIC
- **Protected property:** A guardian's data export is complete, machine-readable, delivered
  within the statutory window, and scoped to only their own family's data.
- **Verification target:** The live export endpoint/flow exercised by an actual guardian account
  against the deployed system.
- **Failure oracle:** The export is not machine-readable, arrives outside the statutory window, or
  contains any record belonging to a different family.
- **Negative control:** not determined (Check text does not describe a seeded cross-family record
  used to prove the isolation check can fail)
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A guardian can obtain a machine-readable export within the statutory window, without
  receiving another family's data

#### O-57

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** COPPA 312.8 (explicitly named in Check text: "COPPA additionally requires written
  assurances from recipients of children's data")
- **Class:** MANUAL
- **Protected property:** Every data-processing provider has a recorded controller, processor, or
  recipient classification with documented subprocessors, locations, retention, training-use
  terms, deletion support, security commitments, and (for children's-data recipients) written
  COPPA assurances.
- **Verification target:** The provider/subprocessor register covering every third-party data
  processor.
- **Failure oracle:** A provider exists that lacks a classification, lacks any of the documented
  terms, or (for a children's-data recipient) lacks a written COPPA assurance.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Each provider is classified controller/processor/recipient with documented
  subprocessors, locations, retention, training-use terms, deletion support, and security
  commitments. COPPA additionally requires written assurances from recipients of children's data

#### O-58

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 44-49
- **Class:** MANUAL
- **Protected property:** Every non-US processor handling personal data has a recorded lawful
  transfer mechanism.
- **Verification target:** The processor register's transfer-mechanism field for each non-US
  processor.
- **Failure oracle:** A non-US processor exists with no recorded transfer mechanism, once the
  EU/UK entry trigger has fired.
- **Negative control:** not determined
- **Trigger:** EU/UK market entry (per Check text: "activated on EU/UK entry")
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A transfer mechanism is recorded per non-US processor, activated on EU/UK entry
  (Art. 44-49)

#### O-59

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 35 (DPIA duty, per the spine's regulatory catalog; not cited by article
  number in the Check text itself); state minors' design codes require an equivalent on US public
  launch (individual states not named in the Check text)
- **Class:** MANUAL
- **Protected property:** A Data Protection Impact Assessment exists, covers the
  children-plus-profiling-plus-generative-AI risk combination, and is revisited whenever a defined
  trigger fires.
- **Verification target:** The DPIA document and its revision history/trigger log.
- **Failure oracle:** No DPIA exists once the EU-entry trigger has fired, or an existing DPIA was
  not revisited after a named trigger fired.
- **Negative control:** not determined
- **Trigger:** EU entry; US public launch (per state minors' codes); and other unnamed triggers
  referenced generically as "on trigger"
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A DPIA is completed and revisited on trigger. Effectively mandatory on EU entry
  (children plus profiling plus generative AI), and several state minors' codes require the
  equivalent on US public launch

#### O-60

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 27
- **Class:** MANUAL
- **Protected property:** A recorded, reasoned determination exists on whether an EU
  representative is required.
- **Verification target:** The Art. 27 determination record.
- **Failure oracle:** No determination is recorded, or a determination is recorded without stated
  reasoning.
- **Negative control:** not determined
- **Trigger:** not determined (no cadence named)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** An Art. 27 EU-representative determination is recorded, with reasoning

#### O-93

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 30 (Records of processing; the Check text's language matches the
  spine's regulatory catalog entry for GDPR Art. 30, but is not cited by article number in the
  Check text itself)
- **Class:** STATIC
- **Protected property:** A records-of-processing register exists and is complete: purposes,
  recipients, transfers, deletion periods, and security measures, for every processing activity.
- **Verification target:** The records-of-processing register/document.
- **Failure oracle:** A processing activity exists with no corresponding record, or a record is
  missing any of the five required fields.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Records of processing are maintained with purposes, recipients, transfers, deletion
  periods, and a description of security measures

#### O-125

- **Category:** SP-12
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 28 (processor engaged only under a contract), Art. 44-49 (transfers),
  Art. 13(1)(e)-(f) (recipients and transfers must be disclosed at the point of collection)
- **Class:** MANUAL
- **Protected property:** No adult's email address is disclosed to Kids Web Services from a tier
  serving real families until a DPA is executed with the receiving Epic entity, the transfer
  mechanism for that entity is recorded, and the disclosure is stated to the guardian before they
  trigger it.
- **Verification target:** The executed Epic/KWS DPA and its named counterparty entity;
  `processor-dpa-checklist.md`'s row for that vendor; the guardian-facing copy on
  `GuardianVerificationPage` and the processor table in `privacy-notice.md`; and
  `KWS_VERIFICATION_REQUIRED` on each deployed tier. Since 2026-08-12 also the retained vendor
  terms at `docs/compliance/vendor-terms/epic-kws/`, which are what the clause citations below are
  checkable against; a claim about what Epic's terms say is verified against the retained bytes,
  not against whatever the vendor is serving today.
- **Failure oracle:** `KWS_VERIFICATION_REQUIRED` is true on a tier serving real families while
  any of the three preconditions is unmet. Equivalently: a `kws_verification` row exists for a
  real guardian and `processor-dpa-checklist.md` has no executed Epic entry.
- **Negative control:** none, and this is the honest state rather than an oversight. The
  precondition is contractual and editorial, so there is nothing in the code that could refuse;
  the only mechanical lever is the flag itself, which defaults false
  (`tests/unit/test_config.py::TestKwsEvidenceSettings::test_verification_is_not_required_by_default`)
  and therefore fails safe without proving anything about this row.
- **Trigger:** Before the first production switch-on of `KWS_VERIFICATION_REQUIRED`, and on any
  change to the receiving Epic entity or to the KWS request payload.
- **Existing coverage:** partial, on the minimisation side only. The outbound body carries the
  adult's email, country, language, and an opaque reference and nothing else; `kws_verification`
  has **no** email column under any name, enforced by an AST-based source guard, so the address is
  transmitted and not retained by us. None of that touches the three gaps this row is about.
  **Distinct from O-123 and O-124**, which govern *which* KWS environment and *which* methods a
  verification relied on: those ask whether the evidence is sound, this asks whether the
  disclosure that produces the evidence is lawful at all. All three are switch-on preconditions
  and none substitutes for another.
- **Recorded 2026-08-10**, when the gate was built and wired on staging against the vendor's Test
  environment. The disclosure is inherent to the design and not deferrable: the address is sent
  when the check *starts*, so an applicant who is refused, who abandons, or who never creates a
  child profile has still had their address disclosed. This is the only processor in the RoPA that
  receives data about people who never become users.
- **Third limb closed 2026-08-12: the pre-send disclosure now exists.**
  `GuardianVerificationPage` states what is sent, to whom, and when, immediately above the button
  that sends it, and asserts that nothing child-derived travels. It names every field of the
  request body in `consent/kws_client.py` that varies per guardian: email, location, language, and
  the opaque per-attempt correlation token. The fifth key, `userContext`, is deliberately not named
  because it is the fixed string `"parent"` on every request and says nothing about the person
  reading the page; that omission is permitted only while the value stays constant. Two properties
  are asserted by test rather than left to convention: **order**, since copy moved below the submit
  button would satisfy a presence check while no longer being pre-send, and **completeness**
  field by field, since the guard that matters is against the copy silently narrowing back to a
  shorter list, which a substring check on its opening clause would not catch. What no frontend
  test can assert is copy-equals-body, because the body is built server-side; that pairing is held
  by a comment on the copy, and it is the weakest link in this limb.
  **Do not read KWS's own email as satisfying this.** Its "Verify you're an adult" message says
  "CYO Adventure will share your email address with KWS", which reads exactly like the disclosure
  this row requires, but that email is delivered *by KWS* and therefore exists only because the
  address had already been shared. It is post-send by construction, and it was the near-miss worth
  recording: a disclosure that arrives through the channel it is disclosing can never be prior to
  it. **The row stays open**, because its protected property is conjunctive and the DPA and the
  transfer mechanism are still absent; one of three parts closing does not move the gate.
- **Counterparty entity RESOLVED 2026-08-12, and it is neither candidate this row considered.**
  The vendor's own terms, now retained at `docs/compliance/vendor-terms/epic-kws/`, open by naming
  the contracting party: "We are Kids Web Services Ltd, a private limited company incorporated in
  England (Company Number 13351982) with our registered office at C/O Shepherd And Wedderburn LLP,
  1-6 Lombard Street, London, England, EC3V 9AA, United Kingdom". Governing law is England and
  Wales with exclusive jurisdiction in the courts of London (General Terms cl. 12.11). Every prior
  record, this row included, hedged between "a US and an EU entity"; the answer is a **UK** entity,
  so the hedge was not merely unresolved, it was framed over the wrong two options. The transfer to
  price is therefore US-to-UK, which is the UK IDTA or the UK Addendum to the EU SCCs, not the DPF.
  Note the interaction with **O-117**: this project keeps UK *users* out of scope by design, but
  the processor performing its adult check is itself a UK company, and those are different facts.
- **A DPA already binds us, incorporated by reference; it has never been retrieved.** General Terms
  cl. 6 and PV Terms cl. 6 both read "DATA PRIVACY: The Data Processing Addendum located here
  applies between you and us", the link resolving to `kidswebservices.com/data-processing-addendum`.
  This converts the first limb from a negotiation into a retrieve-read-record task, which is a real
  reduction in effort but **not a closure**: an incorporated document is as binding as the one
  incorporating it, and we have accepted terms whose data-protection annex we have not read. Until
  it is retrieved into `vendor-terms/` and its transfer mechanism recorded, this limb is open, and
  it is now open in a worse way than before, because the gap is no longer "no contract exists" but
  "a contract exists and we do not know what it says".
- **[COUNSEL] The processor framing may be wrong for six of the eight activities in scope.**
  PV Terms cl. 5 does not treat the flow as a single relationship. For activity 2.1 (our API call
  transferring the parent's email) and 2.2 (KWS emailing that parent), it states we are the
  controller and KWS the processor, Business and Service Provider under CCPA. For 2.3 through 2.8
  (AgeGraph lookup, direct collection from the parent, the verification itself, hashing the email
  into the AgeGraph, returning the result to us, notifying the parent) it states that "you and KWS
  are each independent controllers". If that reading is right, three consequences follow and none
  is cosmetic: a DPA is the wrong instrument for the majority of the processing, so executing it
  cannot by itself satisfy this row's protected property as currently written; Art. 28 is not the
  operative article for those activities; and `privacy-notice.md`'s blanket claim that every
  processor "acts on our instructions only" is false as to this vendor. **Recorded as a finding,
  not a conclusion.** The protected property above is deliberately left unamended pending counsel,
  because rewriting a gate's definition on our own reading of a counterparty's terms is exactly the
  move this register exists to prevent. Cited to the retained PV Terms so the reading is checkable.
- **[COUNSEL] KWS retains the verification durably and reuses it across its other customers.**
  "AgeGraph Data" is defined in the **General** Terms' Definitions section, not in the PV Terms,
  as the individual's "hashed email address, the method, status and the
  timestamp of the first verification and the timestamp of subsequent verifications..., the country
  in which their device is located, the Apps in connection with which the individual verifies their
  age, a KWS generated transaction ID... and any transaction IDs provided to us by our verification
  partners, such as Stripe". **General** Terms cl. 5.1 states KWS owns that data and that it "is used to
  provide KWS Services to you and our other customers." The PV Terms contain no clause 5.1 at all;
  both citations belong to the General Terms, and a reader sent to the PV Terms will not find them.
  So an adult who verifies for this app is
  durably recorded, keyed to a hash of their address, as having verified *for this app*, in a graph
  Epic reuses commercially. Nothing guardian-facing says so: not the pre-send copy closed above,
  not `privacy-notice.md`. This is what makes the independent-controller finding concrete rather
  than formal, and it is the Art. 13(1)(e) limb of this row rather than the Art. 28 limb. It is
  also the one part of the flow where "we send them nothing about your child" stays true while the
  overall picture is still more than a guardian would infer.
- **[COUNSEL] The definition of "AgeGraph Data" can widen without notice, 2026-08-12.** The quote
  above is elided at its end. The definition closes "and any other AgeGraph data as may be expressly
  set out in the KWS Privacy Policy", so the set of fields Epic durably retains about a verifying
  adult is not fixed by the contract at all: it is whatever a document Epic edits unilaterally says
  it is. This is the same defect shape as the cl. 4 finding recorded under O-122 below, and it is
  strictly worse. Clause 4 at least names a trigger (a notified method change) and a period (up to
  14 days), which is what let that finding be written as "a named trigger and no detector". This
  clause names no trigger, no notice period, and no assent mechanism, so there is nothing to detect
  even in principle short of diffing Epic's Privacy Policy on a schedule. Recorded so the elision
  in the quote above cannot be mistaken for a complete reading of the definition.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** An executed DPA, a recorded transfer mechanism for the named receiving entity, and
  pre-send guardian disclosure all exist before any real family's email address reaches Kids Web
  Services

### SP-13 Protected-Population Duties and Age-Appropriate Design

#### O-35

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** COPPA (16 CFR 312; per the regulatory-applicability table row mapping COPPA to
  this ID, not named in the Check text itself)
- **Class:** STATIC
- **Protected property:** Consent records are immutable, timestamped, version-linked to the exact
  notice text shown at consent time, and non-repudiable.
- **Verification target:** The consent-record schema/table and its write path (append-only,
  versioned to notice text).
- **Failure oracle:** A consent record can be altered or deleted after creation, lacks a
  timestamp, is not linked to the specific notice-text version shown, or has no non-repudiation
  evidence.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Consent records are immutable, timestamped, versioned to the exact notice text
  displayed, and non-repudiable. Not a timeless boolean

#### O-36

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** COPPA (16 CFR 312; per the regulatory-applicability table row mapping COPPA to
  this ID, not named in the Check text itself)
- **Class:** STATIC
- **Protected property:** A child's age/reading-band can only be changed by a verified guardian,
  and every change is audit-logged.
- **Verification target:** The age/band-change code path, its authorization check, and the audit
  log entries it produces.
- **Failure oracle:** An age or band change succeeds without guardian verification, or succeeds
  without producing an audit log entry.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Age and band changes are restricted to a verified guardian and audit-logged. Age is
  a safety parameter, not a preference: it determines what content the pipeline will send a child

#### O-37

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** A kid-facing API response contains only fields on the declared
  allowlist; no unlisted field can pass through undetected.
- **Verification target:** The kid-scoped response schema definitions and the diff check against
  the OpenAPI schema.
- **Failure oracle:** A field appears in a kid-scoped response that is not on the allowlist, or
  the OpenAPI contract changes without the diff check running.
- **Negative control:** not determined
- **Trigger:** OpenAPI contract change (per Check text: "diffed against the OpenAPI schema on
  contract change")
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Kid-scoped response schemas are field-allowlisted and diffed against the OpenAPI
  schema on contract change

#### O-38

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** FTC Act §5
- **Class:** MANUAL
- **Protected property:** The privacy notice's stated third-party list matches the actual
  measured set of third parties data egresses to.
- **Verification target:** The published privacy notice's third-party list, reconciled against a
  measured egress inventory.
- **Failure oracle:** A third party receives data via measured egress that is not named in the
  published privacy notice, or a named third party receives no measured egress.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The published privacy notice's third-party list reconciles against the measured
  egress inventory. Divergence is an FTC Act §5 misrepresentation, not only a privacy gap

#### O-61

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** COPPA 312.8
- **Class:** MANUAL
- **Protected property:** A written, named-coordinator children's-data security program exists
  and performs annual risk assessment, ongoing safeguard testing, and annual evaluation.
- **Verification target:** The written security program document and its named coordinator,
  risk-assessment, testing, and evaluation records.
- **Failure oracle:** No written program exists, no coordinator is named, or any of the
  annual/ongoing activities has no record within its required cadence.
- **Negative control:** not determined
- **Trigger:** Annual (per Check text: "annual risk assessment", "annual evaluation")
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A written children's-data security program exists with a named coordinator, annual
  risk assessment, ongoing safeguard testing, and annual evaluation (COPPA §312.8)

#### O-62

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** COPPA
- **Class:** STATIC
- **Protected property:** The retention policy (purpose, business need, specific deletion
  timeframe) is published as the text of the online privacy notice itself, not merely linked.
- **Verification target:** The online privacy notice's rendered content.
- **Failure oracle:** The privacy notice links out to a separate retention policy instead of
  stating purpose, business need, and deletion timeframe inline, or omits any of those three
  elements.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The data retention policy states purpose, business need, and a specific deletion
  timeframe, and is **published directly in the online privacy notice**; a link to a separate
  policy does not satisfy the rule (COPPA)

#### O-94

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** State minors' design codes (US); UK AADC; GDPR Art. 25 (on EU entry)
- **Class:** DYNAMIC
- **Protected property:** Every child-facing default minimizes visibility, sharing, profiling,
  location, personalization, and persistent identifiers, and any weakening of a default is
  traceable to an attributable decision.
- **Verification target:** The deployed default configuration values for child-facing settings.
- **Failure oracle:** A child-facing default is set to a less-protective value than the minimizing
  baseline, with no attributable decision record explaining the change.
- **Negative control:** not determined
- **Trigger:** EU entry (for GDPR Art. 25 applicability, per Check text)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Child-facing defaults minimize visibility, sharing, profiling, location,
  personalization, and persistent identifiers; weakening a protection requires an attributable
  decision (state minors' design codes; UK AADC and GDPR Art. 25 on EU entry)

#### O-95

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** ADA Title III / Section 508 (WCAG conformance; the Check text's own phrase
  "Overlaps the WCAG duty" points to this spine catalog entry, but does not cite the statute
  directly)
- **Class:** MANUAL
- **Protected property:** Child-facing notices and error messages are comprehension-tested
  separately for each of roughly ages 5 to 7, 8 to 10, and 11 to 12.
- **Verification target:** The notice/error-message comprehension test records for each named age
  band.
- **Failure oracle:** A child-facing notice or error message has no comprehension test recorded
  for one or more of the three named age bands, or was tested only with an adult-oriented notice.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Notices and error messages are tested separately for roughly ages 5-7, 8-10, and
  11-12, not with one adult notice. Overlaps the WCAG duty

#### O-96

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** MANUAL (secondary: DYNAMIC, per the original composite tag "MANUAL + DYNAMIC" in the
  source table)
- **Protected property:** A child-facing, age-appropriate disclosure exists describing what a
  guardian or administrator can see and do.
- **Verification target:** The child-facing disclosure content/UI surface.
- **Failure oracle:** No such disclosure exists, or its content is not age-appropriate for the
  child's band.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The child is told, age-appropriately, what a guardian or administrator can see and do

#### O-97

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** State comprehensive privacy laws; state minors'-design codes (named as categories
  in the Check text; no single statute cited)
- **Class:** MANUAL
- **Protected property:** Every child's residence is mapped to the regulatory regimes it
  activates, per the spine's T4 rule.
- **Verification target:** The jurisdiction-trigger matrix document/table.
- **Failure oracle:** A child's residence has no corresponding entry in the matrix, or the matrix
  omits an applicable state-comprehensive-privacy or minors'-design-code regime for that
  residence.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A jurisdiction-trigger matrix maps each child's residence to the regimes it
  activates, per the spine's T4 rule. Owns the state-comprehensive-privacy and
  minors'-design-code determinations

#### O-98

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** TX SB 2420; UT, LA, AL app-store accountability laws (individual citations
  beyond the state abbreviations are not given in the Check text)
- **Class:** MANUAL (inferred: designating an age rating and deciding when a change is
  "significant" enough to re-trigger consent are judgment calls; the Check text describes no
  automated pass/fail criterion. The original table carried `*deferred, R2*` in this position,
  which is a status and a trigger, not a class)
- **Protected property:** The app's store listing carries a correct designated age rating,
  ingests store-provided age/consent signals, and parental consent is re-triggered on any
  significant app change.
- **Verification target:** The app-store listing configuration (age rating) and the consent
  re-trigger logic/record.
- **Failure oracle:** The app carries no designated age rating, store-provided signals are not
  ingested, or a significant change ships without re-triggering parental consent.
- **Negative control:** not determined
- **Trigger:** R2 (app-store launch), plus "significant change" to the app (per Check text:
  "re-trigger parental consent on significant change")
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** verification scheduled
- **Check:** App-store accountability: designate an age rating, ingest store-provided age and
  consent signals via the platform API, re-trigger parental consent on significant change (TX
  SB 2420, UT, LA, AL)

#### O-99

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** not determined (Apple Kids Category and Google Play Families are platform
  policies, not statutes; the app-store accountability statutes named at O-98 are the adjacent
  statutory trigger but are not named in this row's Check text)
- **Class:** MANUAL (inferred: a reviewed pre-submission checklist. The original table carried
  `*deferred, R2*` in this position, which is a status and a trigger, not a class)
- **Protected property:** The app's pre-submission posture satisfies the current Apple Kids
  Category and Google Play Families requirements, reviewed on a quarterly cadence with dated
  evidence of the reviewed page.
- **Verification target:** The pre-submission checklist and its captured page-date evidence.
- **Failure oracle:** No checklist review is recorded within a quarter, or a recorded review has
  no captured page date evidencing what version of the platform policy was checked.
- **Negative control:** not determined
- **Trigger:** R2 (app-store launch), plus quarterly review (per Check text: "reviewed
  quarterly")
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** verification scheduled
- **Check:** Apple Kids Category and Google Play Families pre-submission checklist, reviewed
  quarterly with captured page dates

#### O-117

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** DSA Art. 2(1); GDPR Art. 3(2)
- **Class:** STATIC (secondary: DYNAMIC, per the original composite tag "STATIC + DYNAMIC" in
  the source table)
- **Protected property:** Every account records a country-of-residence signal at creation, and
  that signal is queryable per account.
- **Verification target:** The account schema's country-of-residence field and its query path.
- **Failure oracle:** An account exists with no recorded country-of-residence signal, or the
  signal cannot be queried per account.
- **Negative control:** not determined
- **Trigger:** Account creation (per Check text); recording is cheap pre-launch, but adding it
  afterward requires a re-consent campaign (per Check text)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A country-of-residence signal is recorded at account creation and is queryable per
  account. Without it the DSA Art. 2(1) and GDPR Art. 3(2) targeting tests cannot be answered,
  and a market can be excluded by design rather than by hope. Cheap pre-launch, requires a
  re-consent campaign afterwards

#### O-118

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** DSA Art. 3(i)
- **Class:** STATIC
- **Protected property:** All five structures (admin-gated connection creation, dual guardian
  consent, no discovery surface, no free text between users, directional and revocable
  connections) hold simultaneously, keeping the product outside DSA Art. 3(i) classification.
- **Verification target:** The connection-creation code path and its consent-gating logic.
- **Failure oracle:** A test that creates an active connection without two distinct guardian
  consents does not fail (quoted directly from Check text's own named failure oracle).
- **Negative control:** A test that attempts to create an active connection with only one
  guardian's consent, or none, and asserts it does NOT become active.
- **Trigger:** Any change to one of the five named structures (per Check text: "A change to any
  one re-opens the classification")
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The five structures that keep the product outside DSA Art. 3(i) hold: admin-gated
  connection creation, dual guardian consent, no discovery surface, no free text between users,
  directional and revocable connections. A change to any one re-opens the classification and
  must be an attributable decision, not a refactor. **Failure oracle**: a test that creates an
  active connection without two distinct guardian consents must fail

#### O-119

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** not determined (Check text says "every age regime" generically, without naming
  one)
- **Class:** STATIC
- **Protected property:** Every guardian account carries a timestamped adulthood-attestation
  signal.
- **Verification target:** The guardian-account schema's adulthood-attestation field.
- **Failure oracle:** A guardian account exists with no adulthood-attestation signal, or with a
  signal that carries no timestamp.
- **Negative control:** not determined
- **Trigger:** R2 (per Check text: "every age regime that can attach at R2"); recording is
  trivial pre-launch, but requires a backfill campaign against live accounts afterward (per
  Check text)
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The guardian account carries an adulthood attestation signal with a timestamp.
  Every age regime that can attach at R2 locates its duty on the adult account, not the kid
  profile; today only kid profiles carry age data. Trivial pre-launch, requires backfill against
  live accounts afterwards

#### O-121

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** GDPR Art. 8(1)-(2) (EU 2016/679, member-state consent age 13-16; the EU text has
  only three paragraphs, Art. 8(3) being a contract-law savings clause with no counselling-service
  carve-out, confirmed against the official EUR-Lex consolidated text, 2026-08-09); UK GDPR Art. 8
  as onshored and amended by The Data Protection, Privacy and Electronic Communications
  (Amendments etc) (EU Exit) Regulations 2019 (SI 2019/419), which rewrote the UK GDPR text itself
  to read "13 years" in place of "16 years" and inserted a new **Art. 8(4)**, unique to the UK
  version and with no EU-GDPR equivalent, carving preventive or counselling services out of "the
  reference to information society services" in Art. 8(1) entirely. **Corrected 2026-08-09**: an
  earlier draft of this row cited this as "Art. 8(2A)/(2B) in the UK GDPR's own numbering," which
  was not found in any source and should not be repeated; the correct UK citation is Art. 8(4)
  itself. **Not** DPA 2018 s.9, which performed the 13-year substitution by cross-reference to GDPR
  from 25 May 2018 but was omitted (repealed) 31 December 2020 by that same SI once the
  substitution was folded directly into the onshored UK GDPR text. This specific point was
  independently re-checked twice in this row's history: a fresh review pass on 2026-08-09 flagged
  it as possibly wrong, citing ICO guidance that describes s.9 as currently "modifying Article
  8(1)"; a direct fetch of legislation.gov.uk's own "Latest available (Revised)" page for section 9
  (current as of 2026-08-06) confirms the omission stands: "Section 9 has been omitted (repealed)"
  as of 31.12.2020 by SI 2019/419, Schedule 2, paragraph 12, with no operative text remaining. ICO's
  guidance describes the substantive 13-year rule in informal, present-tense terms without being
  precise about which provision currently codifies it; legislation.gov.uk's own status annotation on
  the provision itself is the more authoritative source for whether s.9 specifically is in force, and
  it is not. Citing s.9 as the current legal basis for the age rule is citing a repealed provision
  for a rule that is now, and independently, written into UK GDPR Art. 8(1) itself. CYO Adventure's
  story generation and reading is not a preventive or counselling service, so the Art. 8(4) carve-out
  does not apply here, but a future feature (e.g. a guardian-support or crisis-resource surface)
  would need this row re-examined before assuming Art. 8 governs it. Art. 8 applies specifically
  where consent under Art. 6(1)(a) is the chosen legal basis for offering an information society
  service directly to a child; it is not a general age-gate on every legal basis GDPR recognizes
  (confirmed against primary text and ICO guidance, 2026-08-09).
- **Class:** MANUAL
- **Protected property:** A per-member-state (13-16) and UK (13) child-consent-age table exists
  and is consulted specifically in the Art. 8 pathway: before any EU or UK child's own consent,
  relied on as the Art. 6(1)(a) legal basis for offering the service directly to that child, is
  treated as valid without a holder-of-parental-responsibility's consent. Processing under a
  different lawful basis (contract with the guardian, legitimate interest) is not gated by this
  table; scope it to the consent pathway only, not to "all child processing."
- **Verification target:** The consent-age determination table or logic, and the point in the
  **consent-based** signup/onboarding flow where an EU/UK-resident child's age is checked against
  it before the child's own consent is accepted as the Art. 6(1)(a) basis. Not a general audit of
  every processing activity's legal basis.
- **Failure oracle:** An EU or UK child below their applicable Article 8 threshold has their own
  consent treated as the valid Art. 6(1)(a) basis for the service without a holder of parental
  responsibility's consent, or a member state's specific threshold (which varies 13-16 by state)
  is missing or wrong in the table.
- **Negative control:** not determined
- **Trigger:** First EU or UK child or guardian. This is reused as a convenient, consistent timing
  anchor, the same one every other GDPR-triggered row in this register uses, not a claim that the
  age table itself is a precondition of GDPR attaching generally. GDPR attaches on that trigger
  regardless of legal basis; this row's table only becomes load-bearing if and when the product
  relies on a child's own consent (Art. 6(1)(a)) rather than another lawful basis for that
  processing.
- **Existing coverage:** none. Absent from this register entirely until this row: neither O-117
  (country-of-residence signal) nor O-97 (jurisdiction-trigger matrix for state comprehensive-
  privacy and minors'-design-code regimes) extends to GDPR Art. 8's member-state consent-age
  table. O-117's country signal is a necessary input to the table this row requires but does not
  itself supply the age-threshold determination. Low urgency while GDPR has not attached (T4:
  US-only today, per the regulatory-applicability determination above), but recorded now rather
  than left silently absent, consistent with how GDPR is written down before it binds elsewhere
  in this register. **No refresh mechanism covers this row's own volatility once built**: O-108,
  the register's only recurring refresh commitment, is explicitly scoped to "US state privacy-law
  applicability... against the IAPP and Bloomberg trackers" and names no EU/UK source; the
  per-member-state ages this row's table would hold (13-16, set individually by each EU member
  state) have no equivalent recurring check anywhere in this register. That gap is demonstrable,
  not hypothetical: a general search for "which EU states set the Article 8 age at 13" returns
  answers that are wrong on inspection against primary sources (e.g. misstating Ireland, whose DPC
  sets 16, and Spain, whose LOPDGDD Art. 7(1) sets 14, not 13, for either). Building this row's
  table from an unverified search result would import exactly that kind of error; the table's
  source and refresh cadence need to be decided together with the build itself, not deferred to
  whoever builds it.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A per-member-state (13-16) and UK (13) child-consent-age table exists and is
  consulted before treating any EU/UK child's own consent as the Art. 6(1)(a) legal basis for
  offering the service directly to that child (GDPR/UK GDPR Art. 8), in place before the first EU
  or UK child or guardian is onboarded. Does not gate processing under any other lawful basis

#### O-122

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** 16 CFR 312.5(a)(1) (consent gates collection), 312.5(b)(1) (the general standard:
  any method must be "reasonably calculated, in light of available technology, to ensure that the
  person providing consent is the child's parent"), 312.5(b)(2) (the enumerated methods),
  312.5(b)(3) (an FTC-approved Safe Harbor program may approve a method not enumerated in (b)(2)
  that meets the (b)(1) standard)
- **Class:** MANUAL
- **Protected property:** The verifiable-parental-consent method the product actually relies on is
  either an enumerated 312.5(b)(2) method, or a non-enumerated method approved under 312.5(b)(3) by
  an FTC-approved Safe Harbor program, and the register names which one.
- **Verification target:** The shipped consent flow as built, not as described: the typed
  full-legal-name attestation captured by `frontend/src/auth/GuardianConsentPage.tsx` and persisted
  through `api/onboarding.py::_record_consent` to `user.consent_accepted_at`,
  `consent_policy_version`, `consent_signer_name`, `consent_ip`, mapped against the (b)(2) list
  provision by provision.
- **Failure oracle:** The relied-on method matches no 312.5(b)(2) provision and carries no Safe
  Harbor approval under 312.5(b)(3), while children's personal information is being collected.
- **Negative control:** not determined. A negative control here would have to be an adversarial
  mapping attempt (an independent reader asked to defeat, not confirm, the claimed provision match),
  because the failure mode this row exists to catch is a plausible-sounding citation that nobody
  opened.
- **Trigger:** Any change to how consent is captured, and any change to the enumerated list.
- **Existing coverage:** none, and this row is the register's first coverage of the VPC mechanism
  itself. Until it was added the register cited COPPA against O-35, O-36, O-61, O-62, and O-31, none
  of which asks *by what method* consent is verified; the word "verifiable" did not appear in the
  file. **A defect is already recorded against this row, in ADR-018 D1**: three documents asserted
  the shipped flow targets a "sign and submit electronically" method at 312.5(b)(2)(i). Reading the
  rule text directly on 2026-08-08 found no such method: (i) describes a *return channel*, a form
  signed away from the service and returned by postal mail, facsimile, or electronic scan. An
  electronic signature captured inside our own application may therefore not be an enumerated method
  **at all**, which is a strictly larger question than "is our signature good enough", and it makes
  312.5(b)(3) Safe Harbor a candidate mechanism for legality rather than an optional cost-saver.
  Note also what the flow is not: it captures a **typed name only**. There is no drawn signature;
  `GuardianConsentPage.tsx` has one text input, two checkboxes, and one select, with no `<canvas>`,
  no `getContext`, and no `toDataURL`, though several documents described a canvas that was
  considered in the 2026-07-20 framing and never built. Two of the cheaper enumerated routes,
  "email plus" (312.5(b)(2)(viii)) and its neighbour (ix), require no disclosure of the child's
  information to third parties, and a child's free-text story wish reaches third-party classifiers.
  **Corrected 2026-08-09: that is a conditional bar, not a foreclosure, and an earlier draft of
  this row overstated it.**

  **Verified against the current rule text on 2026-08-09** via eCFR's renderer API, after the
  section's HTML page proved bot-blocked. The amended Rule was published 90 FR (April 22, 2025),
  effective 2025-06-23, with full compliance required by 2026-04-22, a date that has now passed, so
  the text below binds. Four findings, three confirming what this register already said and one
  changing it:

  - **(b)(2)(i) reads "postal mail, facsimile, or electronic scan."** There is still no "sign and
    submit electronically" method. The 2026-08-08 finding survives contact with current text.
  - **(b)(2)(ii) reads "in connection with a transaction", not "monetary transaction"**, confirming
    the payment-card withdrawal was right. The second limb is verbatim: the card or payment system
    must "provide notification of each discrete transaction to the primary account holder". A
    zero-charge authorisation generating no cardholder notification is therefore an open question
    about the *method*, not a quibble, which is why Gate 1's Q2 is load-bearing.
  - **The list runs (i) through (ix), and (ix) is a text-message method**, the sibling of (viii)
    email-plus. This register's lettering was correct, and "text plus" is a real route, not a
    colloquialism.
  - **The condition on (viii) and (ix) is narrower than "we only use data internally."** The rule
    conditions both on an operator that does not "disclose" **as that term is defined at § 312.2**.
    That definition carves out release to "a person who provides support for the internal
    operations", and § 312.2 then defines *that* phrase with a **closed enumerated list**: maintain
    or analyze functioning; perform network communications; authenticate users or personalize
    content; serve contextual advertising or cap frequency; protect security or integrity; ensure
    legal or regulatory compliance; and fulfil a child's request per § 312.5(c)(3) and (4). It
    carries a second limb of its own: the information "cannot be used or disclosed to contact a
    specific individual ... to amass a profile ... or for any other purpose", which the "Third
    party" definition restates.

  **What that means for this project, and it is not what the earlier draft implied.** The *purpose*
  limb is the easier one: story generation from a child's typed wish reads plausibly as
  "personalize content" or "fulfil a child's request", and moderation reads plausibly as "protect
  security or integrity" and "ensure legal or regulatory compliance". The binding constraint is the
  *second* limb, that no recipient use the data for any other purpose, and that is an **execution
  problem rather than an interpretive one**: it is closed by paperwork, not by architecture.
  `processor-dpa-checklist.md` records it as open on exactly the vendors that would matter
  (OpenRouter's Zero Data Retention coverage of the downstream model providers it routes to, which
  Anthropic terms tier this account sits on, and whether Google Perspective specifically falls under
  the Cloud DPA). Question 1B remains the live counsel ask on the characterisation; the DPAs are the
  owner-side work that has to land regardless of how 1B is answered. Until both limbs hold,
  email-plus and text-plus are unavailable; neither is permanently unavailable.
- **Acceptance record (2026-08-09).** The owner ruled that the approach as built meets the
  requirement and withdrew parts 1C and 1D from the counsel engagement
  (`docs/compliance/counsel-engagement-brief.md` Sections 1.0, 1.3, 6). Recording the three things
  the spine requires of an accepted exception, so the acceptance is a decision rather than a
  disappearance:
  - **Risk accepted.** That the in-app typed-name flow is neither an enumerated 312.5(b)(2) method
    nor defensible under the 312.5(b)(1) general standard. The specific adverse authority is the
    FTC's **January 2015 AgeCheq** decision, which declined to approve a structurally analogous
    method (a signature artifact plus a step binding it to a real adult) on the ground that it was
    not reasonably calculated to ensure the consenting person was the parent, and which noted that
    the 2013 Rule **excluded digital signatures** from the enumerated methods because a digital
    signature alone is not a reliable means of obtaining consent. This authority was identified by
    the operator against the operator's own position and is retained verbatim in the brief; it is
    not disputed here, it is accepted. Its force is not confined to the enumerated list: it is an
    application of 312.5(b)(1) itself, so it bears on the fallback as well.
  - **Compensating controls.** (a) Exposure is bounded by population: T2 records one household plus
    invited families, with the public consumer population arriving only at R2/R3. (b) The flow logs
    more than a signature: a typed legal name, an adulthood attestation, a guardianship attestation,
    a residence country, a consent-language version, an IP address, a timestamp, and an OAuth-bound
    account identity, which is the combination the 312.5(b)(1) argument rests on. (c) Two
    independent enforcement gates refuse child-data collection without a consent record
    (`api/profiles.py::_require_consent` on the caller's record,
    `api/admin_profiles.py::_require_family_consent` on the target family's), so the accepted risk
    is about the *quality* of consent, never about its *absence*. (d) The KWS evaluation at O-123
    and O-124 is a live route to a stronger mechanism and is not foreclosed by this acceptance.
  - **Expiry.** R2, the first distribution beyond the operator's household and invited families,
    whichever comes first with any change to how consent is captured. **The intended retirement
    mechanism, recorded 2026-08-09, is a KWS card or debit-card verification required at every
    guardian signup**, which reaches the enumerated method at 312.5(b)(2)(ii) and makes the
    AgeCheq authority beside the point rather than answered. That reframes this exception as an
    interim covering the population verified between now and KWS reaching the enforcement path,
    not as a permanent posture. **It is not yet earned**: the (b)(2)(ii) text requires the card be
    used "in connection with a transaction" *and* that the card "provides notification of each
    discrete transaction to the primary account holder", so a zero-charge authorisation that
    generates no cardholder notification may not land inside the method. Gate 1's question Q2
    (`docs/operations/kws-test-runbook.md`) is what settles it, and it is now the highest-value
    experiment in the gate because the retirement plan rests on its answer. Two further events
    retire the exception earlier rather than renewing it: a counsel answer to Section 1.6 (whether
    a separate signature step is required at all) that removes the need for the step, or a counsel
    answer to Question 1B that opens "email plus" at 312.5(b)(2)(viii). Both remain live asks.
- **Superseded 2026-08-10, and the acceptance record above is preserved rather than edited.** The
  owner ruled that KWS card or debit verification is the **sole** VPC method and that **no parent is
  verified until it is active**. A risk the owner has decided to eliminate before first real use is
  scheduled remediation, not an exception being carried, so the status moves off `accepted
  exception`. What that changes, and what it does not:
  - **The typed-name attestation is retained in a different role**, as the record of what the parent
    agreed to under 312.5(a)(1) and 312.4. 312.5(b)(2) establishes that the consenting person is a
    parent; it does not capture the agreement. This row's Verification target therefore still points
    at that flow, but the property it protects is now "the method **relied on** is enumerated",
    which the attestation no longer claims to satisfy.
  - **The retirement mechanism named on 2026-08-09 is now the only mechanism**, so its unearned
    status is more consequential, not less. Gate 1's Q2 is promoted from the highest-value
    experiment to the **viability gate**: a zero-charge authorisation generating no cardholder
    notification leaves (b)(2)(ii)'s second limb unmet with no fallback behind it.
  - **The ruling is not yet a control.** `api/profiles.py::_require_consent` and
    `api/admin_profiles.py::_require_family_consent` still read `user.consent_*` and nothing else,
    and nothing reads a `kws_verification` row for any decision, so the typed-name path remains
    fully reachable in production. Until the gates require a KWS-verified record, this is a policy
    the operator holds, not a mechanism. That gate change has a precondition at **O-123**, which is
    promoted accordingly: without a refusal of `kws_environment = 'test'`, a staging-era row could
    satisfy a production consent decision.
  - **Compensating control (c) is unaffected** and remains the reason this is a quality question
    rather than an absence question: both gates still refuse child-data collection without a consent
    record.
  - **Question 1A now bears only on the installed base.** Any child profile already created behind
    the typed-name gate was collected under a mechanism the product declines to rely on going
    forward. Whether that set is non-empty, and whether every member is the operator's own household,
    is **not established**; establishing it is a precondition for closing 1A rather than narrowing
    it, and it is a read-only query against the production project, not an inference.
- **The gate is built, 2026-08-10, and the bullet above is superseded on its factual half only.**
  Both child-profile creation routes now refuse when `settings.kws_verification_required` is set and
  the adult holds no usable verification (`api/profiles.py`, `api/admin_profiles.py`, via
  `consent/service.py::has_usable_verification`), and `api/onboarding.py::_record_consent` stamps the
  corroborating verification id onto the consent record. **The flag is off in production**, so the
  typed-name path is still fully reachable there and the ruling is still policy rather than control
  on the tier that matters; what changed is that switching it on is now a configuration decision
  instead of unbuilt work. Three things this does **not** change, listed because a "built" note
  invites over-reading:
  - **It answers nothing about the method.** Q2's notification limb still decides whether
    (b)(2)(ii) is reachable at all, and this row's Check turns on that, not on whether a gate exists.
  - **It adds a precondition rather than removing one.** The check discloses an adult's email to
    Epic Games at the moment it **starts**, so refused and abandoned applicants are disclosed too,
    to a processor with no executed DPA and an unresolved counterparty entity. That is **O-125**,
    and it gates the switch-on independently of anything in this row.
  - **O-123 shipped with it**, as that row required, so the gate cannot be satisfied by a sandbox
    verification. Had the consumer landed first, this row's remediation would have opened a worse
    hole than the one it closes.
- **Owner ruling 2026-08-10, later the same day: 312.5(b)(2)(ii)'s notification limb is accepted as
  satisfied, and the question is withdrawn from the counsel engagement.** Recording the three things
  the spine requires, so this is a decision rather than a disappearance:
  - **Risk accepted.** That "provides notification of each discrete transaction to the primary
    account holder" is met by a statement line item rather than by an issuer push alert. The basis
    is the observed design: Epic's method creates a real **PaymentIntent for $0.05** refunded in 8 to
    13 business days, so the capture and the refund post as **two discrete statement entries** rather
    than a same-day pair an issuer might net out before the statement closes. The structural limb
    ("in connection with a transaction") is not accepted risk at all; it was answered by observation,
    including a real `pi_...` identifier, and the parent-facing screen commits to the charge in
    writing. What is accepted is the *reading* of the second limb, which no run could have settled:
    the Test environment uses Stripe test cards, so no real notification exists there by
    construction, and the only instrument that could produce the evidence is a production
    verification, which is a genuine VPC event and cannot be spent as a test.
  - **Compensating controls.** (a) The charge is real rather than a zero-amount authorisation, which
    is the branch this limb was written to exclude. (b) The refund lag makes two entries rather than
    one, so the notification survives an issuer that nets same-day pairs. (c) Nothing about the
    method is built here: the card never touches this application, so the behaviour being relied on
    is the vendor's and is uniform across its customers.
  - **Expiry.** Reassess if Epic changes the method (a switch to a zero-amount authorisation, a
    same-day refund, or a `SetupIntent` would each retire the basis above), and at R2 alongside this
    row's other acceptance. **This does not convert the open question into a closed one**: it is an
    owner reading of rule text, taken without counsel review, and the register says so rather than
    presenting it as settled law.
  - **What it unblocks.** Q2 leaves the Gate 1 run list, so no production verification is needed to
    answer it. That removes a real ordering collision: the run that would have answered this limb is
    itself a disclosure of a real adult's email to Epic, which is precisely what **O-125** gates.
  - **Corroborating artifact, 2026-08-12.** A completed Test-environment verification produced a KWS
    email to the enrolling address, subject "You're successfully verified for CYO Adventure",
    stating: "KWS will charge your payment card $0.05, which will be refunded within approximately
    8-13 business days." That is the vendor's own written commitment to both facts the acceptance
    rests on, the real charge and the refund lag, now sourced from a delivered message rather than
    from the parent-facing screen alone. It is the artifact to re-read first if the expiry condition
    above is ever tested, because a switch to a zero-amount authorisation or a same-day refund would
    change this sentence before it changed anything observable in our own code. Held by the owner
    and deliberately not reproduced here, since it is addressed to a real person.
    **It is not evidence for the notification limb**, and reading it as such is the specific error
    this bullet exists to prevent. The message travels from KWS to the address that *started* the
    flow, whereas 312.5(b)(2)(ii) asks for notification from the card or payment system to the
    **primary account holder**. Those two differ exactly where the rule does its work: a child using
    a parent's card with their own email address receives the vendor's message and the cardholder
    receives nothing. Test mode cannot produce the cardholder notification in any case, because
    Stripe test cards move no funds, which is the same reason the limb was accepted rather than
    observed.
  - **The expiry condition has a named trigger and no detector, 2026-08-12.** The Expiry bullet
    above says "reassess if Epic changes the method" without saying how that would ever come to our
    attention. The retained PV Terms answer it, and the answer is unfavourable: cl. 4 reserves to
    KWS the right, "upon reasonable notice (up to 14 days) at any time", to "use, test or introduce
    different verification methods or remove old ones", and provides that "Your continued use of or
    access to Parent Verification after the advised implementation date of any notified different
    verification method constitutes your agreement to the applicable verification method". Read the
    trigger precisely: assent attaches at the *implementation date Epic advises*, not at the notice,
    so the window to object is whatever Epic leaves between the two and is not necessarily the full
    14 days. So the entire basis
    of the acceptance above, a real charge with a multi-day refund lag, is a vendor setting that the
    vendor may change unilaterally, on two weeks' notice, with our silence counting as assent. The
    notice arrives at whatever address holds the KWS account, which is not a monitored channel and
    is not wired to anything in this repository. **Nothing here would notice.** The same clause has a
    second consequence, at **O-124**: that row already records that `KWS_ENABLED_METHODS` is asserted
    by the operator and never reconciled against the Control Panel, so a vendor-side method change
    would silently falsify the declaration too, and the two rows fail together from one cause.
    Cheapest control, and the reason the terms are now retained rather than linked: re-fetch the PV
    Terms at each gate, compare against the SHA-256 in
    `docs/compliance/vendor-terms/README.md`, and treat any change as re-opening this row and
    O-124 together. A hash comparison is not notice, but it converts a silent lapse into a
    detectable one at a cadence we control.
  - **The vendor disclaims the legality of the method, 2026-08-12.** PV Terms cl. 3 excludes KWS
    liability for, among other things, whether "the method of verification (such as payment card or
    government ID) is valid in, and/or complies with, the Applicable Laws of, the applicable
    country". Epic sells a parent-verification service and contractually declines to warrant that
    the verification it performs satisfies any particular law. This forecloses a line of argument
    that would otherwise be tempting whenever this row is revisited, that the vendor's own
    compliance posture can carry the reading: it cannot, because the vendor has said in the
    contract that it does not. It also agrees with, rather than duplicating, the finding already on
    file that Epic's own documentation declines to present the PV Service as a COPPA mechanism. The
    determination is ours to make and ours to defend, which is what leaves this row's status at
    *finding open* rather than *risk accepted* despite two owner rulings sitting inside it.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified. **Neither an accepted exception nor a decision to remediate is a
  verification**: nothing below has been checked against the rule text by anyone qualified to do so.
  The 2026-08-09 record says who decided to carry the risk and on what basis; the 2026-08-10 record
  says who decided to eliminate it and by what mechanism. Neither converts the open question into a
  closed one.
- **Status:** finding open
- **Check:** The VPC method relied on is named, and is either an enumerated 16 CFR 312.5(b)(2)
  method identified by provision, or a non-enumerated method carrying a 312.5(b)(3) Safe Harbor
  approval. "An electronic signature is captured" is not an answer to this check

#### O-123

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** 16 CFR 312.5(a)(1), 312.5(b)(1)
- **Class:** RUNTIME-CONFIG
- **Protected property:** No verification performed against a vendor's **sandbox** environment is
  ever relied on as evidence that a real parent consented, and no deployed tier that serves real
  families is wired to one.
- **Verification target:** The KWS configuration actually in force on each deployed tier
  (`KWS_ENVIRONMENT` plus the four all-or-none API credentials), and the `kws_environment` column on
  every `kws_verification` row treated as consent evidence.
- **Failure oracle:** A tier serving real families holds `kws_environment = 'test'` while its
  verifications are treated as VPC evidence, or any consent decision cites a `kws_verification` row
  whose `kws_environment` is `test`.
- **Negative control:** partial, and one-directional by design. `core/config.py::
  _reject_production_kws_from_a_local_app` refuses to boot when `kws_environment == "production"`
  and `environment == "local"`, proven by
  `tests/unit/test_config.py::TestKwsSettings::test_production_kws_environment_rejected_from_a_local_app`.
  **The opposite direction has no control at all, deliberately**: a deployed tier pointed at the
  Test environment boots normally, because that is the intended staging posture. That decision is
  correct for staging and is exactly the uncovered case for production, and it cannot be closed by
  reusing the same guard, because the app's own `ENVIRONMENT` does not distinguish the tiers:
  **staging declares `ENVIRONMENT=production`**, so every `environment == "local"` predicate is inert
  on both deployed tiers.
- **Trigger:** Any KWS configuration change on any tier, and the first production KWS wiring.
- **Existing coverage:** partial. The `kws_environment` column exists, is `CHECK`-constrained to
  `test | production` at rest, and is stamped per row at send time, so the partition is legible
  afterwards; that legibility is load-bearing because the KWS API reports nothing that would let the
  environment be re-derived later. What has no mechanism is the *reliance* rule: nothing refuses to
  treat a `test` row as evidence, because nothing yet consumes these rows for a consent decision at
  all. **Live state, 2026-08-09**: the integration is wired on staging against the KWS **Test**
  environment; production's compose (`services/cyo-adventure/docker-compose.yml`) contains zero
  `KWS_*` references, so KWS credentials present in production's Portainer stack environment are
  inert **by coincidence of sequencing, not by any control**, and would be picked up silently by the
  deploy that first lands the KWS block in that compose file. Removing them is the cheap mitigation
  and needs no production redeploy.
- **Promoted 2026-08-10 from follow-on work to a precondition.** The owner ruling recorded at O-122
  makes KWS the sole VPC method, which means the consent gates must stop reading `user.consent_*`
  and start requiring a `kws_verification` row. The moment that consumer exists, the gap this row
  describes stops being theoretical: a `test` row becomes capable of satisfying a production consent
  decision, and no deployed tier can detect it, because `_reject_production_kws_from_a_local_app`
  fires only when `environment == "local"` and **staging declares `ENVIRONMENT=production`**. The
  refusal to treat a `test` row as evidence must therefore ship **in the same change as the
  consumer**, not after it. Shipping the consumer first would create, for the duration of the gap, a
  production consent path satisfiable by a staging artifact, which is a worse posture than the one
  the ruling was made to improve.
- **Reliance rule shipped with the consumer, 2026-08-10, which is what the bullet above required.**
  `consent/service.py::usable_verification_id` is the single source of both the gate answer and the
  evidence link, and it refuses a Test verification **before the query runs**, so there is no
  ordering of the remaining conditions under which a sandbox row can be read as evidence. The query
  additionally filters on `kws_environment`, closing the opposite direction: a production-configured
  process must not count a leftover Test row from before a cutover. The guard keys on
  `kws_environment`, never on `settings.environment`, precisely because **staging declares
  `ENVIRONMENT=production`** and the obvious predicate would be inert on every deployed tier. Both
  child-profile creation routes (`api/profiles.py`, `api/admin_profiles.py`) consume it, and
  `api/onboarding.py::_record_consent` stamps the same id onto the consent record, so a record
  cannot cite a verification the gate would have refused. Unit coverage:
  `tests/unit/test_kws_verification_service.py::test_a_test_environment_verification_is_not_usable_by_default`
  and `::test_the_test_refusal_never_reaches_the_database`. Two limits stay open and are the reason
  this row does not close: the escape hatch `KWS_ACCEPT_TEST_EVIDENCE` exists and nothing outside
  code review stops an operator setting it on a tier serving real families, and the whole mechanism
  has never executed on such a tier, because production still has no KWS wiring.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified on any tier serving real families; unit-verified 2026-08-10
- **Status:** mechanism unproven (downgraded 2026-08-10 from *evidence invalid*: the reliance rule
  the earlier status recorded as absent now exists and is consumed, so the invalidating gap is
  closed; what remains is an unexercised mechanism, which is this register's entry state, not a
  finding)
- **Check:** Every deployed tier's KWS environment is the one appropriate to that tier, and no
  `kws_verification` row carrying `kws_environment = 'test'` is relied on as evidence that a real
  parent consented

#### O-124

- **Category:** SP-13
- **Framework ref:** not determined
- **Legal ref:** 16 CFR 312.5(b)(1) (the method must be reasonably calculated to ensure the person
  is the parent, which presupposes knowing what the method was)
- **Class:** RUNTIME-CONFIG
- **Protected property:** For every parent verification obtained through a third-party service, a
  non-retroactive record exists of which verification methods that service was permitted to use at
  the moment the verification was requested.
- **Verification target:** The `kws_verification.enabled_methods` value on each row, and the
  boot-time validator that requires the declaration to be non-empty whenever the credentials are
  complete.
- **Failure oracle:** A verification is recorded with an empty or absent `enabled_methods`, or the
  stored value changes when an operator changes the current setting.
- **Negative control:** **tripped in the field on 2026-08-09**, not in a drill.
  `core/config.py::_require_declared_kws_methods_when_configured` refused to start the staging
  backend the moment KWS was switched on with `KWS_ENABLED_METHODS` empty, raising
  `ConfigurationError: KWS is configured but KWS_ENABLED_METHODS is empty`. That is a genuine
  demonstration that the check can fail, and it is worth recording that it stayed dormant through
  every prior redeploy: the predicate is `kws_configured and not kws_enabled_methods`, so it can only
  fire once all four credentials are present. A control whose first firing is an outage has proven it
  can fail, but has not proven anyone rehearsed it. Unit coverage:
  `tests/unit/test_config.py::TestKwsEnabledMethods::test_configured_kws_requires_declared_methods`.
- **Trigger:** Any change to the enabled-methods declaration or to the vendor's Control Panel
  configuration.
- **Existing coverage:** yes, and this row exists because the vendor forecloses the obvious
  alternative. The `parent-verified` callback reports **no verification method at all**, and KWS's
  AgeGraph branch can verify a parent by inheritance from a different KWS-enabled service, so the
  product cannot evidence *how* a given parent was verified from anything the vendor sends. The
  operator's own declaration is therefore the only bound that will ever exist on it, which is why
  `consent/service.py` copies `list(settings.kws_enabled_methods)` into the row at send time rather
  than holding a reference: a shared reference would make a past row's evidence mutate with a present
  setting, which is precisely the retroactivity this row forbids. **The declaration is asserted, not
  reconciled**: there is no KWS API to read the Control Panel's own configuration from, so nothing
  can detect an operator whose declaration and Control Panel disagree. That is a known limit of this
  control, stated here rather than left for a reader to discover.
- **Confirmed from vendor documentation, 2026-08-10.** The premise this row rests on was previously
  inferred from the callback schema. Epic's Developer Portal pages now state it directly: the
  `parent-verified` payload carries `parentEmail`, `externalPayload`, and a `status` object holding
  `verified` and `transactionId`, alongside envelope fields `name`, `time`, `orgId`, and
  `productId`. There is no method field anywhere in it. The same pages describe the pre-verified
  AgeGraph path as one where the parent "doesn't receive a verification request" at all, so on that
  branch no method runs for us even in principle. Both readings strengthen this row rather than
  changing it: the operator's send-time declaration remains the only bound that will ever exist, and
  on the inheritance branch it is a bound on a method that was never exercised. The declaration
  should be read as *what we permitted*, never as *what happened*, and any surface that renders it
  to a human must not imply otherwise.
- **Refined 2026-08-12 from the retained vendor terms: the method is recorded, it is simply never
  transmitted to us.** The **General** Terms' Definitions section defines "AgeGraph Data" to include
  "the **method**, status and
  the timestamp of the first verification", and **General** Terms cl. 5.1 states KWS owns that data.
  Both citations are to the General Terms, not the PV Terms, which have no clause 5.1. So this row's
  premise needs splitting into the part that holds and the part that does not. **Holds:** nothing
  the vendor sends us carries a method, on either branch, so the operator's send-time declaration
  remains the only bound we can hold, and every mechanism above is unchanged and still correct.
  **Does not hold:** the claim that the method "cannot be reconstructed after the record is written",
  which this row's rationale carried and which `core/config.py`'s boot-guard error message repeated
  verbatim. It is reconstructible, by Epic, from data Epic holds. It is unavailable to *us*.
  The error message was corrected the same day to "no interface returns it to us afterwards".
  The distinction is not pedantry: a claim of impossibility tells the next reader there is nothing
  to ask for, while a claim of unavailability tells them exactly what to ask the vendor for, which
  is a hardening route this row had written off. Raise it alongside the DPA retrieval at O-125
  rather than as separate work; both are questions for the same conversation with the same vendor.
- **Available hardening, not yet taken:** the payload's `productId` is checkable, and
  `api/kws_webhook.py` already compares it against `settings.kws_product_id`. That comparison is
  vacuously true today because `KWS_PRODUCT_ID` is unset on staging, so a delivery naming any
  product passes. The value is visible in the Developer Portal and can be pinned whenever the
  branding work takes an operator there.
- **Consequence raised, not changed, 2026-08-10.** A consumer of these rows now exists: child-profile
  creation refuses without a usable verification, and the consent record cites the verification id.
  Nothing in that path reads `enabled_methods`, so this row's mechanism is untouched. What changed is
  what a wrong declaration costs. Before, an inaccurate snapshot was a defect in an unread record;
  now it is the only description of how the adult behind a live consent decision was checked, and the
  vendor supplies no field that could contradict it. Read the stored value as *what we permitted*,
  never as *what happened*, and hold that line hardest on the AgeGraph inheritance branch, where no
  method ran for us at all.
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** 2026-08-09 (staging only; the control has never run on a tier serving real
  families, because production has no KWS wiring)
- **Status:** verification scheduled
- **Check:** Every third-party parent verification carries a send-time snapshot of the verification
  methods the vendor was permitted to use, and that snapshot does not change when the current
  setting does

### SP-16 Availability, Resilience, Recovery

#### O-44

- **Category:** SP-16
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Every expensive operation is queued, never run on the request thread,
  with bounded overall concurrency and a per-tenant cap.
- **Verification target:** The queueing configuration/code path for generation, cover art,
  full-graph validation, and re-screen operations.
- **Failure oracle:** Any of the four named operations executes on the request thread, or runs
  without a bounded-concurrency or per-tenant cap.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every expensive operation (generation, cover art, full-graph validation, re-screen)
  is queued with bounded concurrency and a per-tenant cap, never executed on the request thread

#### O-45

- **Category:** SP-16
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** A queued job's authorization is re-derived from the database at job
  start, never trusted from the enqueued payload.
- **Verification target:** The worker's job-start authorization code path.
- **Failure oracle:** A worker executes a job's privileged action using authorization data taken
  from the payload without re-deriving it from the database.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** The worker re-derives and re-validates authorization from the database at job start
  rather than trusting the payload

#### O-46

- **Category:** SP-16
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** RUNTIME-CONFIG
- **Protected property:** Redis is network-isolated to the compose network, and queued payloads
  carry only identifiers, never PII directly.
- **Verification target:** The deployed Redis network configuration/firewall rules, and the
  shape of queued job payloads.
- **Failure oracle:** Redis is reachable from outside the compose network, or a queued payload
  contains PII rather than an identifier reference.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Redis is unreachable from outside the compose network; payloads carry identifiers
  rather than PII

#### O-105

- **Category:** SP-16
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** Generation and sync jobs are idempotent or deduplicated, preserve
  tenant context, and cannot publish or corrupt state under duplicate, delayed, or out-of-order
  execution, including connection-pool release under concurrent load.
- **Verification target:** The running job-execution system under duplicate, delayed,
  out-of-order, and concurrent-load conditions.
- **Failure oracle:** A duplicate, delayed, or out-of-order execution publishes content twice,
  corrupts state, loses tenant context, or a connection pool is not released correctly under
  concurrent load.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Generation and sync jobs are idempotent or uniquely deduplicated, preserve tenant
  context, and cannot publish or corrupt state after duplicate, delayed, or out-of-order
  execution. Includes connection-pool release under concurrent load

#### O-106

- **Category:** SP-16
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** DYNAMIC
- **Protected property:** A backup restoration cannot bring back a deleted account or republish
  withdrawn content unless reconciled against the deletion, revocation, and publication records.
- **Verification target:** The restore process, exercised against a backup that predates a known
  deletion, revocation, or unpublication event.
- **Failure oracle:** A restoration resurrects a deleted account or republishes withdrawn content
  without first reconciling against deletion, revocation, and publication records.
- **Negative control:** not determined
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** A restoration cannot resurrect a deleted account or republish withdrawn content
  without reconciliation against deletion, revocation, and publication records

### Cross-cutting

This grouping is deliberate: it is not one of the spine's seventeen `SP-nn` categories, and holds
the single item that constrains every other row's default failure behavior rather than one
system layer.

#### O-49

- **Category:** Cross-cutting (not an SP-nn category; see note)
- **Framework ref:** not determined
- **Legal ref:** not determined
- **Class:** STATIC
- **Protected property:** Every approval/moderation gate defaults to not-approved (fails closed)
  when an exception occurs during its evaluation.
- **Verification target:** Each gate's exception-handling code path, verified via a
  fault-injection test per gate.
- **Failure oracle:** A fault-injected exception in a gate's evaluation logic results in an
  approved/pass outcome rather than not-approved.
- **Negative control:** A fault-injection test per gate that forces an exception and asserts the
  gate does NOT approve (per Check text: "verified by a fault-injection test per gate").
- **Trigger:** not determined
- **Existing coverage:** none
- **Phase home:** unassigned
- **Owner:** core-maintainer
- **Last verified:** not verified
- **Status:** mechanism unproven
- **Check:** Every gate defaults to not-approved on exception, verified by a fault-injection test
  per gate. For this product a fail-open moderation gate is the worst possible outcome

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

**Known gap, not closed here.** The runs are identified by vote count and date only. There is no
per-run identifier, no retrieval date or document version for the primary sources each claim was
checked against, and no evidence artifact a reader could re-open. The load-bearing claims that
would need such citations are the state-law counts, the AISVS Appendix C coverage figure, and the
regime-applicability determinations. Making those reproducible means a source-and-evidence table
with stable IDs cited from each claim, which is a deliverable in its own right rather than a
correction to this one, and it is recorded here instead of built so that the deficiency is visible
in the document that has it. Until it exists, treat the reconciliation narrative below as an
account of how the structure was reached, not as evidence for any individual fact in it; the facts
carry their own citations where they are used.

### Adopted on multi-run agreement

| Change | Votes |
| -------- | ------- |
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
- **"Cut cryptography and secrets."** The secrets half is not vendor-managed. The original grounds
  given here were wrong and are corrected: CI-side secret scanning does exist, as GitHub secret
  scanning with push protection and validity checks at repository level, plus GitGuardian on pull
  requests. The rejection stands on the narrower and still-true point that key custody, rotation,
  and the negotiated TLS parameters at the edge are operator-owned and no scanner observes them.
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
   `[rungs]`, `[status_vocabulary]`, and `[validation]`, of which the checker reads the first three.
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

2. **Rename `O-nn` to `SEC-nnn` when the namespace lands, and prefix the inheritance-map IDs in
   the same change.** The identifiers are provisional. `O-01` reads as a zero and the letter
   carries no meaning. `SQ-*` was previously suspected of colliding with these; it does not, being
   an unrelated story-structure track. There is, however, a real collision that the earlier
   analysis missed: `control-inheritance.md` uses bare `A1` through `A12` as its Plane A row IDs,
   and those are exact word-bounded matches for the capability register's `\b[KGAS]\d+\b` pattern
   at `scripts/check_work_linkage.py:234`. The collision is inert today only because the checker
   never reads `docs/security/`. Making the checker data-driven over declared register paths, which
   is item 1 above, is exactly what would activate it, so the two changes must land together or the
   first will manufacture twelve false capability citations.
3. **Confirm no ASVS 5.0.x patch has shipped since 5.0.0.**
4. ~~**Confirm AISVS C8 applicability**: whether `diversity/` uses embeddings or only structural
   and lexical similarity.~~ **Confirmed 2026-08-02: structural and lexical only.** `diversity/`
   imports no ML or embedding library; its feature vectors are hand-built structural tuples
   compared by Canberra distance, and its cosine similarity runs over token-count `Counter`
   objects. The exclusion table now records this as a verified reason rather than a belief.
5. **Counsel scoping decision on UK OSA only.** DSA Art. 28 is resolved above.
6. **Decide the row budget, against the corrected count.** A prior entry recorded "Decided
   2026-08-02: 81 rows accepted, no trimming", on the reasoning that a budget silently exceeded is
   indistinguishable from one never considered. That reasoning holds; the number did not. The
   register carried 116 rows, 113 of them active, as of the 2026-08-02 reconciliation, so the
   decision was taken against a figure 35 rows below the real one and the budget was silently
   exceeded after all, by the very entry written to prevent it. A subsequent compliance-verification
   pass added O-120 (state information-security statutes) and O-121 (GDPR Art. 8 child-consent-age
   table), both absent from every applicability table until then, moving the count to 118 rows, 115
   active. A further pass on 2026-08-09 added O-122 (which VPC method is relied on), O-123 (the
   vendor sandbox/production partition), and O-124 (the send-time snapshot of permitted verification
   methods), moving the count to 121 rows, 118 active. Those three closed a gap worth naming: the
   register cited COPPA against five rows, none of which asked *by what method* consent is verified,
   and the word "verifiable" appeared nowhere in the file. Building that verification gate on
   2026-08-10 then added O-125 (the processor disclosure the gate performs, as distinct from the
   evidence it produces), moving the count to 122 rows, 119 active. Reopened: decide whether the
   active count, now 119, is accepted, or trim to the ~60 ceiling. This is the maintainer's call and is deliberately left open rather than re-decided here;
   the point of recording each new addition here is so the next person who reopens this item
   recounts rather than trusts any historical figure.
7. **Promote the spine.** `assurance-spine.md` is written to be lifted into whatever global
   standards set the operator's tooling keeps, so other projects instantiate it rather than
   rediscovering it. The spine deliberately names no concrete install path, because that path is a
   property of the tool rather than of the document; `~/.claude/standards/` is this operator's.

## Initial-build commitments

Approved 2026-08-02. These are the only rows promoted out of the general register into
pre-launch build work, because each is cheap now and requires a re-consent or backfill campaign
once real accounts exist.

| Row | Commitment | Why it cannot wait |
| --- | --- | --- |
| O-117 | Country of residence captured at signup, queryable per account | Answers the DSA Art. 2(1) and GDPR Art. 3(2) targeting tests and lets the UK and EU be excluded by design. For the UK specifically the gate is necessary but not sufficient: OSA s.4 also finds links through capability-plus-material-risk, so the gate holds only in combination with the O-118 structures |
| O-119 | Guardian adulthood attestation with timestamp | Every age regime reachable at R2 attaches its duty to the adult account; today only kid profiles carry age data. Scope is deliberately **attestation, not verification**: DSA Art. 28(3) forecloses an obligation to collect additional personal data to detect minors, and the app-store age signals at O-98 supersede this at R2 |

The country field is itself personal data and inherits the minimization, retention, and access
duties in SP-12.
