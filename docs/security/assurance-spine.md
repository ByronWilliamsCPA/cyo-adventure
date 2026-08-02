---
title: "Portable Security and Privacy Assurance Spine"
schema_type: common
status: published
owner: core-maintainer
purpose: "Project-agnostic assurance spine: seventeen control categories, the frameworks that
  spine them, and a trigger-driven catalog of US federal, US state, and EU/UK regulatory regimes,
  so any project can instantiate a register by marking categories and regimes applicable or not
  applicable with a recorded reason and reassessment trigger."
tags:
  - security
  - compliance
  - reference
  - legal
  - privacy
---

Drafted 2026-08-02.

This file is **portable**. It describes no product. A project instantiates it by producing a
register that marks every category and every regime applicable or not applicable, with a reason
and a reassessment trigger for each N/A. The worked instantiation for this repository is
[`assurance-register.md`](assurance-register.md).

Intended destination is the global standards set (`~/.claude/standards/`), so that a new project
starts from the spine rather than rediscovering it. Nothing below depends on this repository.

## Why a spine rather than a checklist

A checklist enumerates findings someone else once had. A spine enumerates the places a system can
fail, so a gap in your own product is visible as a category with no rows rather than as a question
nobody asked. The originating artifact for this work was a 10-item "common issues" list; when
mapped against the categories below, **eight of seventeen received zero questions**. That is the
argument for the structure, not for any particular item on it.

Three properties are load-bearing and are what make the spine reusable:

1. **Categories are defined by what fails**, not by what technology is present. "Authorization and
   tenancy isolation" survives a move from Postgres to DynamoDB; "RLS policy coverage" does not.
2. **Regimes attach by trigger**, not by assumption. A project does not decide it is
   GDPR-in-scope; it determines whether the triggers fire.
3. **N/A is a recorded decision with an expiry**, not an omission. The failure this spine exists
   to prevent is *not done and not in the plan*, and a silently dropped category is exactly that.

## Instantiation contract

A project's register MUST:

- Carry every one of the seventeen categories, including the N/A ones, with a reason and a
  reassessment trigger on each N/A.
- Run the applicability determination in the next section and record which regimes attach, which
  do not, and why.
- Give every row a named verification method and a phase home in the project plan. **A passing
  check is not required.** An item is correctly handled when it is planned, not when it is green.
- Enter every automated check at status *mechanism unproven* and only promote it once a negative
  control has demonstrably tripped it.

A project's register MAY add categories. It may not silently delete one.

### Row schema

`ID | category | framework ref | legal ref | class | protected property | verification target |
failure oracle | negative control | trigger | existing coverage | phase home | owner | last
verified | status`

Four of these fields are the anti-hollow machinery and are the difference between a register and
a topic list:

- **Protected property**: the condition claimed true, stated so that it could be false.
- **Verification target**: the actual deployed role, endpoint, artifact, dashboard, or workflow
  examined, as distinct from a fixture standing in for it.
- **Failure oracle**: the observable result distinguishing true from false.
- **Negative control**: the deliberate violation demonstrated to trip the check.

### Verification classes

| Class | Meaning |
|-------|---------|
| STATIC | Assertable from source, schema, policy-as-code, or version-controlled configuration |
| DYNAMIC | Must be exercised against a running system |
| RUNTIME-CONFIG | Authoritative state lives in a deployed service or vendor control plane |
| MANUAL | Judgment is unavoidable, so the item carries an owner, trigger, cadence, and retained evidence |

### Status model

Binary pass/fail cannot express the dominant real-world failure, which is a check that runs and
tells you nothing. Seven states:

| Status | Meaning |
|--------|---------|
| Evidence current | Verified against the correct target within cadence |
| Finding open | A defect was found and the phase home is named |
| Verification scheduled | Method and owner exist, evidence is not yet current |
| **Evidence invalid** | The check ran but targeted the wrong environment, role, path, or version |
| **Mechanism unproven** | The check has never demonstrated an ability to fail |
| Accepted exception | Risk, compensating controls, and expiry recorded |
| Not applicable | Reason and reassessment trigger recorded |

## Applicability determination

Run these seven questions before writing any row. Each answer switches regimes on. Re-run on any
change to the answers; that re-run is itself a register row.

| # | Question | Switches on |
|---|----------|-------------|
| T1 | **What data classes are handled?** Personal data, sensitive personal data, biometric, precise geolocation, health, genetic, financial account, card data, government ID, credentials, children's data, education records, employment data, video-viewing records, communications content | Sectoral and data-class regimes |
| T2 | **Who are the data subjects?** General consumers, children under 13, minors 13-17, patients, students, employees, job applicants, EU/UK residents, residents of specific US states | Protected-population and jurisdictional regimes |
| T3 | **What sector does the operator sit in?** Health, financial services, education, government contracting, critical infrastructure, telecommunications, ad tech, general commercial | Sectoral regimes, which in the US are the primary vector |
| T4 | **Where do users reside?** Determined **per user**, not by operator location. One resident of a state or country pulls in that regime | Jurisdictional regimes |
| T5 | **What is the business model?** Sale or sharing of personal data, targeted advertising, profiling with legal or similarly significant effect, subscription, marketplace, user-to-user distribution, app-store distribution | Opt-out rights, DPIA duties, platform duties, store duties |
| T6 | **What is the deployment and operating model?** Self-managed hardware, IaaS, PaaS, BaaS, third-party edge or CDN, on-device, hybrid. Which control planes are outside the repository | Infrastructure baselines, shared-responsibility boundaries, inheritance mapping |
| T7 | **What contractual regimes bind, independent of statute?** PCI DSS, customer DPAs, insurance warranties, app-store policies, government contract clauses, SOC 2 or ISO commitments | Contractual obligations, which are enforceable without any statute |

Two rules that repeatedly get this wrong:

- **US obligations stack; they rarely preempt.** There is no general federal consumer privacy
  statute. Federal sectoral law, state comprehensive law, state sectoral law, and contract all
  apply simultaneously, and the strictest wins per-obligation rather than per-statute.
- **Jurisdiction attaches per data subject.** A US-only operator with one EU user, or one
  Illinois user whose face is scanned, is in scope for that regime. Decide from where the users
  are, never from where the company is.

## The seventeen categories

| ID | Category | Fails as |
|----|----------|----------|
| SP-01 | Identity, Authentication, Session Lifecycle | Wrong principal is admitted, or a session outlives its authority |
| SP-02 | Authorization and Tenancy Isolation | Right principal reaches the wrong object, or crosses a tenant boundary |
| SP-03 | Input Validation, Encoding, Injection | Untrusted data is interpreted as instruction, code, or markup |
| SP-04 | Business Logic and Abuse Resistance | Every request is individually valid and the sequence is still an attack |
| SP-05 | Client-Side Storage, Offline Sync, Client Surface | Data at rest on a device leaks, or client-asserted state is trusted on return |
| SP-06 | API Surface, Egress, SSRF | An undocumented route exists, or the server is used as a proxy into trusted networks |
| SP-07 | File, Object Storage, Media | Uploaded content executes, or stored objects are reachable without authorization |
| SP-08 | Cryptography, Secrets, Key Management, Transport | A secret is where it should not be, or a transport claim is untrue |
| SP-09 | Runtime Configuration and Control-Plane Drift | Deployed state diverges from reviewed state, in places source review cannot see |
| SP-10 | Build and Software Supply Chain | A trusted artifact is not the artifact that was reviewed |
| SP-11 | Logging, Audit Integrity, Alerting, Incident Response | The event happened and nobody can prove it, or nobody was told |
| SP-12 | Data Lifecycle, Rights, Processors, Transfers | Data outlives its purpose, crosses a border unlawfully, or a right cannot be honored |
| SP-13 | Protected-Population Duties and Age-Appropriate Design | A heightened duty owed to a specific population is met only for the general case |
| SP-14 | AI and Model Layer: Generation, Prompts, Providers, Output | The model is steered, or its output is trusted |
| SP-15 | Human Decision Gates and Publication Integrity | The last human barrier is bypassed, mis-defaulted, or shown an incomplete picture |
| SP-16 | Availability, Resilience, Recovery | The system is unavailable, or recovery reintroduces removed state |
| SP-17 | Assurance Validity and Change Lifecycle | The controls above are asserted by checks that cannot fail |

Notes on the three least obvious:

**SP-13 generalizes beyond children.** The pattern is a population to whom the law owes more than
the general case: children under 13 (COPPA), minors 13-17 (state design codes and app-store acts),
patients (HIPAA), students (FERPA), employees and applicants (state AI-in-hiring law), and
consumers subject to automated decisions. A project with none of these marks the category N/A with
a trigger, and re-runs on any change to T2.

**SP-15 generalizes beyond content moderation.** The pattern is any workflow where a human decision
is the last barrier before an irreversible or externally-visible effect: content publication,
payment release, access provisioning, clinical sign-off, model promotion, production deploy. It
fails through mis-defaulted state and incomplete reviewer context, not through the failures in
SP-14, which is why it is a separate category.

**SP-17 is a legal obligation, not hygiene.** GDPR Art. 32(1)(d) requires "a process for regularly
testing, assessing and evaluating the effectiveness" of security measures. A check structurally
incapable of detecting failure is not an assessment of effectiveness. Multiple US regimes carry
the equivalent: the GLBA Safeguards Rule requires continuous monitoring or annual penetration
testing plus biannual vulnerability assessment, and COPPA §312.8 requires ongoing testing of
safeguards and an annual evaluation.

## Framework layer

| Source | Role | Notes |
|---|---|---|
| **OWASP ASVS 5.0.0** | Primary spine for application security | 17 chapters, ~350 requirements, released 30 May 2025. Machine-readable (CSV, CycloneDX JSON) |
| **OWASP AISVS 1.0** | Overlay for AI-specific surface | 12 chapters + 3 appendices, June 2026. Levels align 1:1 with ASVS |
| **OWASP MASVS 2.1.0** | Overlay for mobile | Activates on a native or wrapped mobile client |
| **OWASP SCVS / SLSA** | Overlay for supply chain | AISVS names these as its own deferral target |
| **CIS Benchmarks** | Overlay for operated infrastructure | Scope to layers actually operated, not vendor-managed internals |
| **NIST SSDF SP 800-218 / 218A** | Consult for SDLC practices | 218A is the generative-AI addendum |
| **NIST CSF 2.0 / SP 800-53** | Consult; required where a contract names them | |
| **PCI DSS 4.0.1** | Binding by contract where card data is handled | Not a statute; enforceable anyway |
| OWASP LLM Top 10, API Top 10, MITRE ATLAS | Threat enumeration for corpus building | Not control catalogs. Do not spine on them |
| ISO 27001 / 27701 / 42001, CSA CCM/AICM, SAMM, BSIMM | Ignore below enterprise scale unless a customer contract requires certification | |

### Two facts about ASVS 5.0.0 that change how references are written

Both verified against the published document and confirmed by three independent research runs.

1. **Requirement IDs must be version-qualified** (`v5.0.0-V8.2.1`). Of 286 requirements in 4.0.3,
   only 11 carried forward unchanged and 15 took grammatical edits; 109 ceased to exist as
   separate requirements. A bare `V8.2.1` is ambiguous across editions.
2. **5.0.0 removed the embedded external-standard mappings**, moving crosswalks to the OWASP CRE
   ecosystem. Any framework-reference column is therefore hand-maintained, with no official
   crosswalk to align to.

Canary for bad secondary sources: any reference stating ASVS 5.0 has **14 chapters** is reproducing
the 4.0.3 count and should not be trusted on anything else.

| # | ASVS 5.0.0 chapter | # | ASVS 5.0.0 chapter |
|---|---|---|---|
| V1 | Encoding and Sanitization | V10 | OAuth and OIDC |
| V2 | Validation and Business Logic | V11 | Cryptography |
| V3 | Web Frontend Security | V12 | Secure Communication |
| V4 | API and Web Service | V13 | Configuration |
| V5 | File Handling | V14 | Data Protection |
| V6 | Authentication | V15 | Secure Coding and Architecture |
| V7 | Session Management | V16 | Security Logging and Error Handling |
| V8 | Authorization | V17 | WebRTC |
| V9 | Self-contained Tokens | | |

### AISVS 1.0 scope boundary

AISVS states its own limits, and the statement is more useful than most of its requirements
because it tells you what you still owe elsewhere:

> "AISVS is intentionally narrow. It only defines security requirements that are specific to AI
> and ML systems... It is not a self-contained security program for an AI application."

Verifying against AISVS Level N **assumes** verification against ASVS Level N. Explicitly out of
scope, with AISVS's own named deferral target:

| Out of AISVS scope | Deferred to |
|---|---|
| General application security | ASVS |
| General software supply chain | OWASP SCVS, SLSA, CIS Controls |
| General infrastructure and platform hardening | CIS Benchmarks, NIST SP 800-53, SP 800-190, CSF |
| **Data protection and privacy operations**, incl. consent-management operation | ASVS, ISO/IEC 27001, GDPR |
| General logging and monitoring | ASVS |
| AI governance and risk management | ISO/IEC 42001, ISO/IEC 23894, NIST AI RMF |

Two corrections worth recording, because secondary summaries get both wrong: AISVS does **not**
cover privacy, and it has **no human-oversight requirements chapter**. `AD.19 Human Oversight &
Shutdown Control` is an entry in Appendix B's cross-reference inventory of defence techniques.

The scope table also answers the recurring "the vendor owns infrastructure, skip CIS" argument:
OWASP's own position is that infrastructure hardening is still owed, just from a different
standard, for whatever layers you operate.

| AISVS chapter | Lands in |
|---|---|
| C1 Training Data Integrity and Traceability | SP-14, SP-10 |
| C2 Input Validation (prompt injection, content and policy screening) | SP-03, SP-14 |
| C3 Model Lifecycle Management and Change Control | SP-14, SP-09 |
| C4 Infrastructure, Configuration and Deployment | SP-09 |
| C5 Access Control and Identity for AI Components | SP-01, SP-02 |
| C6 Supply Chain Security for Models (AI BOM) | SP-10 |
| C7 Model Behavior, Output Control and Safety Assurance | SP-14, SP-03 |
| C8 Memory, Embeddings and Vector Database Security | SP-02, SP-12 |
| C9 Orchestration and Agentic Security | SP-04, SP-15 |
| C10 Model Context Protocol Security | SP-06, SP-10 |
| C11 Adversarial Robustness | SP-14 |
| C12 Monitoring, Logging and Anomaly Detection | SP-11 |
| **Appendix C, AC.1-AC.14 AI-Assisted Secure Coding** | **SP-10, SP-17** |

### AISVS Appendix C: the AI-assisted development control set

Source: `OWASP/AISVS`, `1.0/en/0x92-Appendix-C_AI_for_Code_Generation.md`. Fetched and read
2026-08-02. Fourteen sections, roughly sixty level-tagged requirements.

**This applies to any project developed with AI assistance, which for this operator is all of
them.** It is the published answer to a question that otherwise gets answered from first
principles every time, and three of its sections cover a surface most security programs miss
entirely: the development pipeline being attacked *through* the AI tooling.

| Section | Subject | Lands in |
|---|---|---|
| AC.1 | AI-assisted secure-coding workflow: written scope, SSDLC coverage, named adversarial scenarios, metrics vs a human-only baseline | SP-17 |
| AC.2 | Tool qualification and threat modeling, incl. vendor model supply chain and pre-onboarding adversarial testing | SP-10, SP-17 |
| AC.3 | Secure prompt and context management: no secrets or PII in prompts, automated redaction, **external context treated as untrusted**, instruction hierarchy, no silent truncation | SP-03, SP-08 |
| AC.4 | Validation of AI-generated code: human review by a **different identity**, full scanner set per PR, merge block at CVSS >= 9.0, elevated review for security-critical files | SP-10 |
| AC.5 | Explainability and traceability: prompt to response to commit to build to deployment replay chain, tamper-evident | SP-11, SP-17 |
| AC.6 | Continuous feedback, red-teaming of the AI tooling itself, regression harness after every prompt or model change | SP-17 |
| AC.7 | AI-generated infrastructure and pipeline artifacts: labeled, human-reviewed, policy-as-code gated, dual control on high-impact triggers, drift detection vs signed baselines | SP-09, SP-10 |
| AC.8 | Autonomous agent change control: an agent **cannot approve, merge, sign, or deploy what it generated**, enforced by SCM, CI, and registry. "Policy alone does not satisfy this control" | SP-10, SP-15 |
| AC.9 | Artifact origin validation at deploy: signed provenance, trusted verifier, quarantine on failure | SP-10 |
| AC.10 | Generation audit trail completeness: model identity and version, prompt hash, human involvement, correlation IDs; reject on incomplete metadata | SP-10, SP-11 |
| AC.11 | **AI review and assistant bot hardening**: PR content is untrusted input, signed and hash-pinned system prompts, schema-validated output only, network-isolated least-privilege sandbox, privileged actions adjudicated by a policy engine and not by the LLM, read-only shadow mode for fork PRs, continuous injection replay | SP-03, SP-10 |
| AC.12 | **CI/CD hardening for AI augmentation**: `pull_request_target` and `workflow_run` never execute untrusted code with write permissions or secrets, no persisted credentials, environment protection for fork and first-time contributors, ephemeral runners, elevated review on workflow-file changes, real-time pipeline audit streaming, and **re-validation of PRs opened before a workflow fix landed** | SP-10, SP-09 |
| AC.13 | **Adversarial AI detection in inbound contributions**: contribution-velocity and reputation analytics, maintainer approval gate for first-time contributors, typosquat and phantom-dependency detection, ATT&CK T1195 and ATLAS tagging, automated containment | SP-10, SP-11 |
| AC.14 | Compromise containment for AI-in-pipeline: playbook, automatic rotation of every secret touched by a suspect run, rapid agent-identity revocation with a tested target time, provenance-driven blast-radius identification, annual live-fire | SP-11, SP-17 |

Three requirements are worth quoting because they are unusually precise and are commonly failed:

- **AC.4.1 (L1)**: "AI-generated code always goes through code review by a qualified human
  engineer. The reviewer must not be the same identity that asked for the AI generation in the
  first place (separation of duties). And the AI agent itself does not count as the human
  reviewer." A single-maintainer AI-assisted repository **cannot satisfy this as written**. The
  correct handling is an accepted exception with compensating controls and an expiry, not a
  silent skip.
- **AC.8.1 (L1)**: an agent cannot approve, merge, sign, or deploy its own artifacts, "enforced by
  the source-control system, the CI system, and the artifact registry. Policy alone does not
  satisfy this control." Any setup where an assistant can enable auto-merge on a PR it authored
  fails this.
- **AC.12.8 (L2)**: remediating a vulnerable workflow must invalidate or re-validate PRs opened
  before the fix, "without this step, a later commit to the same PR can pick up the stale workflow
  definition and route around the fix."

## Regulatory catalog

Organized by trigger. Each entry names what it adds beyond the baseline and where it lands. This
is a scoping aid, not legal advice; every entry with real exposure needs counsel.

### Always on, US

| Regime | Adds | Lands in |
|---|---|---|
| **FTC Act §5** (unfair or deceptive acts) | The catch-all. Security claims in a privacy policy or marketing page become enforceable representations. Covers dark patterns, deceptive defaults, and "reasonable security" as an unfairness theory. Enforced through consent decrees with 20-year terms | SP-13, SP-12, all |
| **State breach notification** (50 states + DC + territories) | Divergent definitions of covered data, harm thresholds, notice deadlines, AG and credit-bureau thresholds. The strictest applicable deadline governs a multi-state incident | SP-11 |

### US federal, sectoral (trigger T1/T3)

| Regime | Trigger | Adds | Lands in |
|---|---|---|---|
| **COPPA** (16 CFR 312; amended rule 90 FR 16977, effective 23 Jun 2025, compliance 22 Apr 2026) | Personal info from children under 13, or a child-directed service | Verifiable parental consent, separate consent for third-party disclosure, direct notice, **retention policy published in the privacy notice itself, not linked**, §312.8 written security program with a named coordinator, annual risk assessment, ongoing safeguard testing, annual evaluation, and written assurances from recipients | SP-13, SP-12, SP-17 |
| **HIPAA** (Privacy, Security 45 CFR 164.302-318, Breach Notification) | PHI, as covered entity or business associate | Risk analysis, workforce controls, audit controls, BAAs, 60-day breach notice, minimum necessary | SP-02, SP-11, SP-12 |
| **GLBA Safeguards Rule** (16 CFR 314, amended 2021) | "Financial institution", read broadly: mortgage brokers, auto dealers, tax preparers, collection agencies, some fintech | Named **Qualified Individual**, written risk assessment, MFA or equivalent for any system holding customer information, encryption in transit and at rest, secure disposal, change management, continuous monitoring **or** annual pen test plus biannual vulnerability assessment, service-provider oversight, written IR plan, annual written report to the board | SP-01, SP-08, SP-11, SP-17 |
| **FERPA / PPRA** | Education records, or a school-directed service | School-official exception terms, directory-information handling, parental rights, survey restrictions | SP-13, SP-12 |
| **SOX §404** | Public company financial reporting | ITGC: access provisioning and review, change management, segregation of duties | SP-02, SP-10 |
| **SEC cybersecurity disclosure** | Public company | Material incident on Form 8-K Item 1.05 within four business days of materiality determination; annual risk-management and governance disclosure | SP-11 |
| **FCRA** | Consumer reports, eligibility decisions | Permissible purpose, accuracy, adverse-action notice, disposal rule | SP-12 |
| **CAN-SPAM / TCPA** | Commercial email, SMS, autodialed or prerecorded calls | Consent capture and proof, opt-out honored within statutory windows. TCPA carries a private right of action with statutory damages | SP-12, SP-04 |
| **VPPA** | Video content plus disclosure to a third party | Consent for disclosure of viewing records. The active litigation vector is advertising pixels on pages with video | SP-12, SP-06 |
| **ECPA / Wiretap Act** and state two-party-consent analogues (notably California CIPA) | Session replay, chat interception, third-party tags reading form input | Consent for interception. Also a live litigation vector | SP-12, SP-05 |
| **ADA Title III / Section 508** | Public accommodation, or federal procurement | WCAG conformance as the de facto standard | SP-13 |
| **NIST SP 800-171 / CMMC** | Federal contract involving CUI | 110 controls, SSP and POA&M, assessment level by contract | all |
| **FedRAMP** | Selling a cloud service to a federal agency | Authorization boundary, control baseline, continuous monitoring | all |
| **EAR / ITAR / OFAC** | Export-controlled technology, or users in sanctioned jurisdictions | Encryption export classification, geo-restriction, screening | SP-02, SP-12 |
| **PCI DSS 4.0.1** (contractual) | Card data touched, transmitted, or influenced | Scoping and segmentation, SAQ or ROC by level, and 4.x additions: client-side script integrity and change-and-tamper detection on payment pages, targeted risk analyses, expanded MFA | SP-08, SP-05, SP-09 |

### US state (trigger T4)

The state layer is the fastest-moving part of this catalog and the part most likely to be stale.
**Do not treat any enumeration below as current without re-checking.** Maintain against the IAPP
US State Privacy Legislation Tracker and the Bloomberg Law tracker; the refresh is register row
material, not a footnote.

| Family | Status as verified | What it adds |
|---|---|---|
| **Comprehensive consumer privacy** | **20 states have laws on the books as of Feb 2026**, counting Florida's narrower scope. Indiana, Kentucky, and Rhode Island took effect 1 Jan 2026; Connecticut, Arkansas, and Utah changes 1 Jul 2026 | Notice; access, delete, correct, portability; opt-out of sale, sharing, and targeted advertising; sensitive-data opt-in or opt-out depending on state; **universal opt-out signal (Global Privacy Control) recognition** in a growing subset; data-protection assessments for high-risk processing; processor contract terms; profiling opt-out. Cure periods are sunsetting, so enforcement risk is rising even where the substantive law is unchanged |
| **Breach notification** | All states | See "always on" above |
| **Biometric** | Illinois BIPA, Texas CUBI, Washington HB 1493, plus biometric clauses inside comprehensive laws | Written policy with a retention and destruction schedule, informed written consent before collection, no sale. **BIPA carries a private right of action with per-violation statutory damages**, which makes it the single highest-exposure US privacy statute for a small operator |
| **Consumer health data** | Washington My Health My Data, Nevada SB 370, Connecticut | Broad definition of health data reaching well past HIPAA, separate consent for collection and for sharing, geofencing prohibitions near health facilities. **MHMDA carries a private right of action** |
| **Minors and age-appropriate design** | California AADC (partially enjoined, *NetChoice v. Bonta*), Maryland Kids Code, Nebraska, Vermont, Connecticut SB 3 amendments, Texas SCOPE Act, Florida HB 3, Utah Minor Protection | DPIA for features likely to be accessed by minors, high-privacy defaults, no profiling by default, no dark patterns, age-appropriate notice language, limits on precise geolocation. Constitutional challenges are active, so track litigation status per state rather than assuming enforceability |
| **App store accountability** | Texas SB 2420 (1 Jan 2026), Utah (6 May 2026), Louisiana, Alabama | **Obligations land on the developer, not only the store**: designate an age rating, ingest age-category and parental-consent signals from the store API, re-trigger parental consent on a significant change to the app. Directly relevant to any project planning store distribution |
| **AI-specific** | Colorado AI Act (SB 24-205, implementation delayed to Jun 2026), Texas TRAIGA/HB 149 (1 Jan 2026), Illinois HB 3773 (employment AI, 1 Jan 2026), NYC Local Law 144 (AEDT bias audit), California CPPA ADMT regulations, Utah AI disclosure | Impact assessments for consequential decisions, notice that AI is in use, human review or appeal, bias audit and public posting, developer-to-deployer documentation duties |
| **State sectoral security** | New York SHIELD Act, NYDFS Part 500 (amended Nov 2023, phased through Nov 2025), Massachusetts 201 CMR 17.00, California SB-327 IoT | Written information security program, MFA, CISO designation and board reporting, 72-hour incident notice (NYDFS), encryption of personal information (MA), no default passwords (CA IoT) |
| **Data broker registration** | California Delete Act, Texas, Oregon, Vermont | Registration, and for California the DROP deletion-request mechanism |

### EU, UK, and other non-US readiness (trigger T4)

Handled the same way COPPA and GDPR are handled: recorded now with triggers, so that expansion is
a scoping decision rather than a discovery.

| Regime | Trigger | Adds |
|---|---|---|
| **GDPR** (EU 2016/679) | Offering goods or services to, or monitoring, EU data subjects | Lawful basis; Art. 5 principles; Art. 8 child consent age (13-16, set per member state); Art. 12 transparency; Art. 15-22 rights incl. portability and automated-decision safeguards; Art. 24-25 accountability and data protection by design and by default; Art. 27 EU representative; Art. 28-29 processor and subprocessor terms; Art. 30 records of processing; **Art. 32(1)(a)-(d) security, with (d) the testing-effectiveness duty**; Art. 33-34 breach notice at 72 hours; Art. 35 DPIA; Art. 44-49 transfers |
| **UK GDPR + DPA 2018**, as amended by the Data (Use and Access) Act 2025 | UK data subjects | Largely parallel; separate transfer regime, separate regulator, separate representative requirement |
| **ePrivacy Directive** and national implementations | Cookies, similar storage, unsolicited communications | Prior consent for non-essential storage, independent of GDPR lawful basis |
| **EU AI Act** (2024/1689) | Placing an AI system on the EU market or its output used in the EU | Phased: prohibited practices and AI literacy from Feb 2025; GPAI obligations from Aug 2025; high-risk obligations from Aug 2026 and Aug 2027. Risk classification, transparency for systems interacting with people, technical documentation, logging, human oversight, post-market monitoring |
| **DSA** (2022/2065) | Intermediary, hosting, or online platform | Tiered. **Art. 28 requires a high level of privacy, safety, and security for minors** and prohibits profiling-based advertising to minors. The classification question is whether users disseminate content to other users, which catches features that look internal |
| **NIS2** (2022/2555) | Essential or important entity in listed sectors | Risk-management measures, supply-chain security, 24-hour early warning and 72-hour notification, management-body accountability |
| **DORA** (2022/2554) | Financial entities and their ICT third parties | ICT risk framework, incident classification and reporting, threat-led penetration testing, third-party register and contractual terms |
| **Cyber Resilience Act** (2024/2847) | Placing a product with digital elements on the EU market | Security by design, vulnerability handling for the support period, SBOM, **actively-exploited-vulnerability reporting from Sep 2026**, main obligations Dec 2027 |
| **European Accessibility Act** | Consumer-facing e-commerce, e-books, banking, transport | EN 301 549 conformance, in force since Jun 2025 |
| **Product Liability Directive** (2024/2853) | Software placed on the EU market | Software is a product; defective-security claims become product-liability claims |
| **Data Act**, **eIDAS 2**, **DMA** | Connected products and data sharing; digital identity wallets; gatekeepers | Recorded for completeness; each has a narrow trigger |
| **UK Online Safety Act** | User-to-user or search service with UK users | Illegal-content and children's-safety duties, risk assessments, age assurance where required |
| **Other** | Per-country users | Brazil LGPD; Canada PIPEDA and Quebec Law 25; Australia Privacy Act and the Children's Online Privacy Code; India DPDP Act; China PIPL; Japan APPI; South Korea PIPA; Switzerland revFADP |

## Volatility and refresh

Parts of this file decay at very different rates, and treating them uniformly is how a spine goes
quietly wrong.

| Layer | Half-life | Refresh |
|---|---|---|
| The seventeen categories | Years | Only on a genuine new failure mode |
| Framework versions (ASVS, AISVS, MASVS, PCI) | 1-3 years | Check on major release; re-verify chapter lists from the primary document, never a summary |
| US federal sectoral | Slow, but rule amendments matter | Annual, plus on any FTC or sector-regulator rulemaking |
| **US state** | **Months** | **Quarterly**, against IAPP and Bloomberg trackers. Track litigation status separately from enactment status: several minors' design codes are enacted and partially enjoined |
| EU phased regimes (AI Act, CRA, NIS2) | Known dates, moving guidance | Semi-annual, against the phase calendar |

Two standing rules that follow from the table:

- **Re-verify framework structure from primary sources.** A published, confident, wrong summary of
  a standard is common; one specimen states ASVS 5.0 has 14 chapters. Chapter and requirement
  lists come from the standard, not from an article about the standard.
- **Enumerations of the state layer are dated snapshots, not facts.** Any register citing "20
  states" carries the date and source of that count, and a refresh row that owns it.
