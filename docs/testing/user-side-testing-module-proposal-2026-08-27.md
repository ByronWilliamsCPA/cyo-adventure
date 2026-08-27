---
title: "User-Side Testing Module Proposal"
schema_type: common
status: draft
owner: core-maintainer
purpose: "Compares the programmatic-review structure against the current test process and proposes a user-side testing module."
tags:
  - testing
  - evaluation
---

This document does three things, in order:

1. Inventories the testing process this repo actually runs today (2026-08-27).
2. Compares that process against the standard "programmatic review" structure that external recommendations
   (including the LLM response this task was asked to evaluate) prescribe, and marks which elements would be
   beneficial to adopt.
3. Designs a **user-side testing module**: a new tier whose job is to find the issues our current, script-first
   process structurally cannot, the ones real users hit.

**Provenance note**: the external LLM response this document compares against did not arrive with the original
task, so the first draft compared against the canonical programmatic-review checklist such responses follow
(section 2). The full text (a four-layer "synthetic beta" recommendation: programmatic journey testing, synthetic
child personas, per-story automated evaluation, and choice-tree traversal, plus multi-model judging, a
deterministic-first rule, and a staged pre-human rollout) was delivered on review, and section 2b now holds the
line-by-line comparison against what this repo actually runs.

## 1. Current process inventory (as of 2026-08-27)

### Backend (Python)

| Check | Tooling | Where it runs |
| --- | --- | --- |
| Unit + integration tests, 80% coverage floor | pytest, coverage, hypothesis | `ci.yml` (3.14), `python-compatibility.yml` (3.11-3.14) |
| Property-based testing | hypothesis | inside the pytest suite |
| Fuzzing | ClusterFuzzLite | `cifuzzy.yml` |
| Mutation testing | mutmut | `mutation-testing.yml` (weekly; currently red, issue #302) |
| Performance regression | `pytest -m perf`, complexity-class budgets | `perf.yml` (weekly, backend-only, files a tracking issue) |
| Adversarial LLM safety eval | `tests/llm_eval/`, majority-of-k scoring | `safety-eval.yml` (weekly, fails closed on missing creds) |
| Static analysis / types | Ruff (PyStrict-aligned), BasedPyright strict | `ci.yml`, pre-commit |
| Security (SAST + deps) | Bandit, OSV-Scanner, Semgrep, pip-audit, SonarCloud | `security-analysis.yml`, `sonarcloud.yml`, `dependency-review.yml` |

### Frontend, by tier (see `docs/testing/README.md` for the environment model)

| Tier | Location | Backend | Cadence |
| --- | --- | --- | --- |
| Unit / component | `frontend/src/**/*.test.{ts,tsx}` (Vitest) | mocked at module boundary | per PR |
| E2E mocked | `frontend/e2e/` (~50 specs) | route-intercepted | per PR (`frontend-e2e`) |
| E2E real backend | `frontend/e2e-real/` | local Postgres + uvicorn + Supabase CLI | nightly + PR smoke |
| E2E staging | `frontend/e2e-staging/` + fail-closed leak sweep | shared staging project, seeded fixtures | scheduled + manual |
| E2E production | `frontend/e2e-prod/` | live production, default-deny CI guard | manual + one scheduled workflow |

### Cross-cutting frontend checks

- **Accessibility**: axe (WCAG 2.1 AA) per PR across every top-level page and dialog; WCAG 2.2 plus
  best-practice rules weekly via `accessibility-compliance-weekly.yml` (ADR-029). Known residual gap: most
  surfaces are scanned in one fixed mock state, not every loading/error variant (`coverage-matrix.md`).
- **Keyboard operability**: `keyboard-nav.spec.ts` pins the dialog focus-trap contract.
- **Visual regression**: `visual.spec.ts` screenshot baselines, one state per surface.
- **Responsive / cross-device**: `responsive.spec.ts` (3 widths) and `cross-device-e2e.yml` (Pixel 7, iPad,
  iPhone 14/webkit, desktop Firefox), informational rather than merge-gating.
- **Deterministic misuse suite**: `frontend/e2e/naive-user/` covers double-submit, browser-back resubmit,
  hand-typed URLs into dead states, and session expiry mid-task; `naive-kid-misuse-real.spec.ts` re-runs the
  kid cases against a real backend.
- **Resilience**: `guardian-backend-unavailable.spec.ts`, offline/conflict specs (two real `BrowserContext`s
  provoking genuine 409s in `e2e-real`).
- **Contract**: generated OpenAPI client committed, `contract` CI job fails on drift; `api-tests` job runs the
  Postman collection.

### Human-in-the-loop and production signal

- **naive-ux-check skill**: 17 persona comprehension scenarios (K0-K4, G0-G7, A0-A3) pasted by hand into
  Claude-for-Chrome, verdicts logged to `docs/qa/naive-ux-reports/` (gitignored), dead-ends filed as issues.
  Manual, unscheduled, one scenario per invocation.
- **Error tracking**: `frontend/src/observability.ts`, Sentry with `beforeSend` scrubbing, no Session Replay
  and no BrowserTracing by deliberate children's-privacy posture; a documented no-op unless `VITE_SENTRY_DSN`
  is set.
- **Scheduled-failure triage pattern**: every scheduled workflow files or updates exactly one tracking issue on
  failure (`e2e-alert` / `ci-failure` labels) rather than failing silently.
- **Coverage accounting**: `docs/testing/coverage-matrix.md` maps every journey to the tests covering it per
  tier, with a keep-current policy.

### Where it hurts today

The scheduled user-facing suites carry open red streaks: #290 (`e2e-real-nightly`), #623 (`e2e-prod`), #700
(a11y weekly), #302 (mutation weekly). Notably, the nightly real-backend tier keeps proving its worth: the
save-concurrency defects fixed in PR #761 and the sign-in loop fixed in PR #763 were exactly the class of
user-visible issue only that tier caught. The lesson for anything new: scheduled user-side signal is valuable
but must arrive pre-triaged, or it becomes another lingering red issue.

## 2. Comparison against the programmatic-review structure

Canonical programmatic-review recommendations prescribe a layered pyramid: static analysis, unit, integration,
contract, end-to-end journeys, accessibility, visual, cross-browser, performance, security, resilience,
usability simulation, and production monitoring, orchestrated in CI with quality gates. Verdict per element:

| Review element | Status here | Notes |
| --- | --- | --- |
| Static analysis, types, lint | **Exceeded** | Strict BasedPyright, PyStrict Ruff, ESLint max-warnings=0 |
| Unit tests + coverage gates | **Covered** | 80% floor enforced in CI |
| Integration tests | **Covered** | pytest integration tier + e2e-real full pipeline |
| API / contract testing | **Exceeded** | Generated-client drift gate is stronger than typical advice |
| E2E user journeys | **Exceeded** | Five tiers vs the usual one; journey-by-layer matrix |
| Accessibility | **Covered** | Per-PR WCAG 2.1 AA + weekly 2.2; fixed-state gap remains |
| Visual regression | **Covered** | One state per surface |
| Cross-browser / device | **Covered** | Separate informational workflow |
| Security (SAST, deps, supply chain) | **Exceeded** | Plus SLSA, SBOM, scorecard, container scanning |
| Security (DAST) | **Gap** | No runtime scanner (for example ZAP baseline) against staging |
| Backend performance | **Covered** | Budgeted `pytest -m perf`, weekly |
| Frontend performance | **Gap** | No Lighthouse CI, no Web Vitals budget, nothing asserts LCP/INP/CLS |
| Load / stress testing | **Gap** | No k6/locust tier; deferred until Track 2 (public launch) makes it real |
| Mutation testing | **Covered (backend)** | Frontend Stryker absent; poor value/cost right now |
| Resilience / negative paths | **Covered** | Backend-unavailable, offline/conflict, misuse suite |
| Usability / user simulation | **Partial** | naive-ux-check exists but is manual, unscheduled, non-repeatable |
| Runtime error invariants in E2E | **Gap** | No spec fails on `pageerror` or `console.error`; a page can render, pass its assertions, and still be throwing |
| Production user-side monitoring | **Partial** | Scrubbed Sentry errors only; UX friction (dead clicks, slow vitals, sync failures) is invisible, and third-party RUM is rightly off the table |
| CI orchestration + gates | **Exceeded** | `ci-gate` rollup, scheduled-failure issue filing |
| Automated review layer | **Covered** | CodeRabbit + `claude-baseline-review.yml` |

**Bottom line of the comparison**: a generic programmatic-review prescription would mostly tell this repo to
build things it already has, frequently in stronger form. The elements genuinely worth adopting are the four
gaps and two partials above, and three of them (runtime error invariants, repeatable user simulation,
privacy-safe production friction signal) share one root cause: **nothing tests or observes the app the way a
user experiences it, unscripted**. That is the module section 3 designs. The remaining gaps get one-line
dispositions:

- **Frontend performance budgets**: adopt separately; a weekly, non-blocking Lighthouse CI run against the
  built app (later staging), budgets on LCP/INP/CLS/bundle size, using the existing tracking-issue pattern.
- **Load testing**: defer to the Track 2 hardening phase; pointless against a homelab-scale R1.
- **DAST**: defer; a ZAP baseline scan against staging is cheap to add later, but authenticated scanning needs
  the same seeded-credential and concurrency discipline as `e2e-staging`, so it should ride after the module.
- **Frontend mutation testing**: rejected for now; runtime cost is high and the deterministic misuse +
  real-backend tiers already kill the survivor classes Stryker would target.

## 2b. Line-by-line: the delivered recommendation vs this repo

The delivered response proposes a four-layer "synthetic beta" (programmatic journey testing, synthetic child
personas, automated per-story evaluation, choice-tree traversal) plus supporting practices. Two of its framing
assumptions do not hold here, and both work in this repo's favor:

- **It assumes runtime, per-choice story generation.** This app generates the complete Storybook graph up
  front and gates it behind `validator/` + `moderation/` + mandatory human approval before any child can open
  it. Consequences: path exploration does not need sampling ("run 500 synthetic playthroughs") because the
  graph is finite and enumerable, and "which 5% should a human inspect" is moot pre-publish, since a human
  already reviews 100% of stories. Triage value shifts to review-queue prioritization and post-publish
  catalog analysis, not to replacing inspection.
- **It assumes a native mobile app** (Appium / Maestro / Detox / XCTest / Espresso). This is a web PWA;
  Playwright is the correct harness and already runs five tiers of it.

Verdicts per element of the response, verified against the actual modules rather than assumed:

| Response element | Repo reality | Verdict |
| --- | --- | --- |
| Layer 1: programmatic journeys (resume, back out, force-close, connectivity loss, odd tap orders) | `reader-reload-resume`, `reader-go-back`, `offline-reconnect/conflict`, `guardian-backend-unavailable`, the `naive-user/` misuse suite, all across five tiers | Covered; legs A/B below extend it |
| Layer 1: LLM picks the next action, harness executes (structured `{action, target, reason}`) | Not present | Adopt: this is exactly leg B's loop |
| Layer 2: 12-20 fixed personas with behavioral constraints | 17 comprehension scenarios exist by role (kid/guardian/admin), none age-banded by reader profile | Adopt: persona-condition leg B |
| Layer 3: coherence, character, world consistency | `validator/character.py` (CH-* envelope rules), `validator/continuity.py`, moderation stages 3-4 | Covered; see the continuity warning below |
| Layer 3: choice agency ("did my choice matter") | `validator/consequence.py`: per-fork rejoin distance plus variable-state delta over the exhaustive configuration graph | Exceeded: deterministic and total beats a sampled 1-5 LLM score |
| Layer 3: choice distinctiveness, repetition | `moderation/leaf_diversity.py` (anti-template guard), `diversity/` gram/lexical/structural metrics | Covered |
| Layer 3: reading level (formulas + LLM age fit) | RL-13 Flesch-Kincaid advisory (`validator/reading_level.py`) plus Stage 4's holistic note; a per-node LLM readability stage was built and retired for duplicating RL-13 | Covered: the repo already landed on the exact split the response recommends |
| Layer 3: engagement | Moderation Stage 4, whole-story LLM engagement advisory | Covered (advisory, as it should be) |
| Layer 3: safety, age appropriateness | Stage 1 hard gate, classifiers, `imitable.py`, `theme_leak.py`, `band_profile.py`, plus the weekly adversarial corpus in `safety-eval.yml` with majority-of-k scoring | Exceeded |
| Layer 4: traverse the choice tree (random walks, BFS, coverage sampling) | `validator/walk.py`: exhaustive BFS over every reachable (node, variable-state, visit-set) configuration, with soundness handling for once-effects | Exceeded by architecture: enumeration, not sampling |
| Multi-model judging (generator never grades itself) | Stage-0 classifier (OpenAI) + independent Stage-1/3/4 review model (OpenRouter-pinned) + optional Perspective + deterministic Python + a human on every story | Covered |
| Deterministic checks do everything they can | The layer-1/layer-2 validator design law; the retired LLM readability stage is this principle applied retroactively | Covered |
| Comprehension self-test (generate 3 questions, check answerability elsewhere) | Not present | Adopt as a measured pilot (conditions below) |
| Adversarial "weird kid" agent | Deterministic misuse suites exist; unscripted chaos is exactly leg A | Covered by this proposal |
| Evaluation DB + structured per-run result | Persisted moderation reports, append-only pipeline events, thresholds dashboard | Covered |
| CI fails on quality thresholds | The validator gate blocks structurally; safety-eval gates weekly per class; `AL-337` sets a deliberately higher bar: a computable statistic becomes a gate only with reader-impact evidence | Covered, with a better-informed promotion rule |
| Cheap-to-strong judge cascade | Review batching exists; no confidence cascade | Note: adopt as leg B and pilot cost posture |
| Calibrate synthetic predictions against real child behavior | `reading_history`, `reading_time`, ratings, and flags are collected; nothing joins them back to Stage-4 advisories or validator statistics | Adopt: the strongest new idea in the response |

The response's own warnings (LLM judges miss subtle incoherence; an AI score is not proof of quality) are
already institutional knowledge here, in stronger, measured form: `validator/continuity.py` built three LLM/
lexical continuity formulations, measured 3.48 findings per node and a 1-in-6 true-positive rate, and shipped
none as a rule; `AL-337` records the cost of promoting a computable number to a gate; `validator/
blind_spots.py` makes the gate report what it did NOT check, with witness documents proving the declarations
stay true. Any new LLM judge proposed below inherits that discipline: measured before believed, advisory
before gating, never a silent pass.

### Genuinely new adoptions from the response

1. **Persona-conditioned agents for leg B** (response layer 2): define roughly ten fixed, age-banded reader
   personas (emerging/average/strong/reluctant readers across the app's age bands) with the response's
   constraint style ("do not infer functionality that is not visible; prefer what this persona would
   attempt"), and run leg B under them. The same personas drive kid-surface story-reading walks against
   seeded staging stories, which turns leg B into a story-experience probe as well as a UI one.
2. **Comprehension probe pilot** (response's self-testing idea): an offline script over the committed story
   corpus in `skeletons/`: one model generates "what happened / why / what should the reader remember"
   questions per passage, a different model answers from the story text alone, and unanswerable questions
   flag ambiguity, missing causal links, or unclear referents. Pilot terms are non-negotiable given the
   continuity.py precedent: run against human-reviewed stories first, measure precision, and only a result
   materially better than continuity's 1-in-6 earns promotion to an advisory moderation stage.
3. **Prediction-vs-behavior calibration loop** (the response's "defensible capability" point): a read-only
   analysis job joining Stage-4 engagement advisories and validator statistics (consequence distance,
   reconvergence, diversity scores) with aggregated real outcomes (completion rate, return reads, ratings,
   flags) per storybook. Output feeds the flywheel's candidate strategy, which today triggers on
   request-side saturation only, and over time calibrates which synthetic scores actually predict that a
   band's readers finish and return. Hard precondition, same as leg C: an ADR-018 children's-privacy review;
   aggregate-only, per-storybook not per-child, and no new collection, only analysis of what the reading
   APIs already store.

### Explicit do-not-build list (things the response suggests that would duplicate or regress what exists)

- A standalone "Story QA Harness" service: `validator/` + `moderation/` + the events pipeline + the
  thresholds dashboard already are that harness, wired into the request path and the human review surface.
- Sampled path traversal (random walks / 500 playthroughs) for story QA: `walk.py` enumerates the space
  exhaustively; sampling would be a strict downgrade. Random walks stay valuable only where the space is not
  enumerable, which is the live UI, and that is leg A.
- A per-node LLM readability judge: built once, retired once (duplicated RL-13); the holistic Stage-4 note is
  the surviving channel.
- LLM continuity gating: measured and rejected; continuity stays a reported statistic until a formulation
  beats the recorded false-positive wall.
- A commercial synthetic-user platform: the response itself concludes in-house is better given this stack,
  and the module below is that in-house build.

## 3. The user-side testing module

### What "user-side" means here, concretely

Every current tier asserts *scripted* expectations: the test knows the journey and checks the known outcome.
The issues that reach users (the #763 sign-in loop, the #761 save races, the dead-ends the naive-ux prompts
hunt by hand) live in *unscripted* space: states no author enumerated, errors no assertion watched, friction no
metric recorded. The module attacks that space from three sides, sharing one findings contract.

### Leg A: invariant-based persona walks (deterministic, no LLM)

A new Playwright project, `frontend/e2e-usersim/`, that walks the app the way a user might instead of the way
a script says: from each persona's entry point (kid picker, guardian console, admin console), repeatedly pick a
visible, enabled interactive element (role-based locators only, same discipline as the existing suites) using a
**seeded** PRNG, act on it, and after every step assert global invariants instead of scripted outcomes:

- **I1 clean console**: no `pageerror`, no unhandled rejection, no `console.error` (with a small, commented
  allowlist file for known third-party noise). This also closes the runtime-error gap for free wherever the
  walk reaches.
- **I2 no dead ends**: every state offers at least one enabled interactive element, or is a recognized
  terminal (the auth gates that naive-ux-check's K0/G0/A0 already define as legitimate stops).
- **I3 no stuck loading**: spinners and skeletons resolve within a budget; a state that never settles is the
  #763-shaped failure users describe as "it just hangs".
- **I4 layout sanity**: zero page-level horizontal overflow, reusing `frontend/e2e/support/responsiveChecks.ts`.
- **I5 role and family isolation**: mocked fixtures embed canary strings for the "other" family and role;
  a kid-persona walk failing to keep guardian/admin chrome and family-B canaries off-screen is a hard failure.
  This is the highest-severity invariant: it is the three-ring boundary (ADR-016) checked continuously rather
  than at hand-picked spots.
- **I6 history safety**: a random back/forward step must land in a state that still satisfies I1-I4 (the
  misuse suite checks specific back-button cases; the walk generalizes them).
- **I7 accessibility of newly reached states**: an axe scan the first time a distinct state signature
  (route + main heading) is visited. This directly widens the known "one fixed state per surface" gap in
  `coverage-matrix.md`. Scans run in this module's own workflow, never inside the required `frontend-e2e`
  job, so ADR-029's scope constraint on the merge gate is untouched.

Determinism is the design center: the seed is printed on failure and settable via `USERSIM_SEED`, so any
finding replays exactly. The route universe comes from a small checked-in manifest derived from
`frontend/src/router.tsx`, with a unit test asserting the manifest and the route table stay in sync, so a new
surface must register itself for walking (the same forcing function the coverage matrix uses socially, made
mechanical).

Tiers, reusing what exists: a mocked-tier walk (fast, per-PR-capable but started as informational) on the
existing route fixtures, and a real-tier nightly variant joining `e2e-real-nightly.yml`'s stack so walks
exercise genuine state transitions.

### Leg B: agentic persona comprehension runs (automating naive-ux-check)

The 17 naive-ux scenarios are the best user-side test asset this repo has and the least exercised, because a
human must paste each one into a browser extension. Leg B turns the skill's prompt set into a scheduled runner:
a Playwright-driven loop in `tools/usersim-agent/` where an LLM plays the persona (observe accessibility-tree
snapshot, decide, act), executes one scenario per invocation, and emits the same structured verdict the skill
defines (`pass` / `friction-found` / `dead-end`, plus the four rubric answers). Runs are persona-conditioned
per section 2b: the agent receives one fixed age-banded reader persona plus a constraint block (act only on
what is visible, prefer what this persona would attempt, report where a child could misunderstand a control),
and each step is a structured `{action, target, reason}` decision that the harness, not the model, executes.

Postures inherited from the skill verbatim, not renegotiated:

- Credentialed scenarios run only against staging's seeded accounts; production gets only K0 (signed-out,
  non-mutating). The mutating scenarios (G4/G5/G6, A2/A3) never point at production.
- Any run touching the shared staging project joins the `e2e-staging` concurrency group before it is enabled
  (the `#CRITICAL` in `docs/testing/README.md` applies to this workflow like any other).
- Transcripts are redacted before persistence (emails, display names, tokens, correlation ids to
  placeholders); raw model output never lands in an artifact. Reports append to `docs/qa/naive-ux-reports/`
  exactly as the manual skill does, so the two entry points share one history.
- Cadence and failure handling copy `safety-eval.yml`: weekly plus manual dispatch, fail closed when
  credentials are missing, one tracking issue updated on `dead-end` verdicts, model id and prompt-set version
  recorded per run. Token spend is bounded per scenario and the run stops at the cap rather than free-running.

The manual skill remains for exploratory passes; leg B makes the floor scheduled and repeatable, so a
regression in comprehension (a renamed button, a gate that turns into a retry loop) surfaces in days, not
whenever someone remembers to run a pass.

### Leg C: first-party, privacy-safe friction beacon (production signal)

Today a production issue is visible only if it throws and only if `VITE_SENTRY_DSN` is set. The failures users
actually report (taps that do nothing, saves that silently fail offline, pages that take seconds to become
usable) never throw. Third-party RUM and session replay are permanently off the table for this app, so the
answer is a minimal first-party beacon:

- **Client**: a small module beside `observability.ts` batching a closed enum of events via `sendBeacon` on
  `visibilitychange`: bucketed Web Vitals (LCP/INP/CLS), error-boundary hits (component-stack hash only),
  offline-sync failure counts, rage clicks (3+ clicks, same target, under a second) and dead clicks (click
  with no DOM or network consequence) identified by role + testid only. No free text, no story content, no
  names, no per-child identifiers: role class (kid/guardian/admin) plus a non-persistent random session id.
  Kill switch via env flag; fire-and-forget with local rate limiting.
- **Server**: `POST /api/v1/client-events` writing through the existing append-only `events/` pipeline with a
  short retention window (30 days), rate-limited per the existing middleware.
- **Consumption**: a weekly digest job in the mold of `moderation-report-health.yml` that thresholds the
  aggregates (new error-boundary hash, INP p75 regression, rage-click hotspot on one testid) and files or
  updates one tracking issue.
- **Hard precondition**: a short ADR plus a privacy-model update reviewed against ADR-018's children's-privacy
  commitments before any code. Even first-party and anonymous, this is new data collection in a kids' app;
  the beacon ships only if that review agrees the payload contract collects nothing attributable. The
  Session Replay ban in `observability.ts` stays absolute.

`#ASSUME: security: the leg C payload enum can be kept free of attributable child data (no names, no free
text, no stable per-profile identifiers) while still being useful for triage. #VERIFY: the ADR review for leg
C must walk every enum variant against the privacy model in docs/planning/ and against observability.ts's
existing scrubbing rules before implementation starts; if any variant needs an identifier to be actionable,
that variant is dropped rather than the rule bent.`

### One findings contract, one triage loop

All three legs emit findings in a single JSONL schema: `{leg, persona, scenario_or_seed, url, invariant_or
verdict, severity, evidence_path}`. Triage rules are the skill's, promoted to module policy:

- A `dead-end` or invariant violation files a GitHub issue immediately (`ux-finding` label), carrying the
  replay seed or scenario id.
- A single `friction-found` is logged; it escalates only when it reproduces on the next run.
- Every confirmed finding gets a deterministic regression spec in the matching existing tier plus a
  `coverage-matrix.md` row, per that file's keep-current policy. The walk found it; a scripted test keeps it
  found.

### What this module deliberately does not do

- **No new merge gates at first.** Every workflow starts informational (the `cross-device-e2e.yml` /
  `e2e-real-pr-smoke.yml` posture) and files exactly one tracking issue, because the open #290/#623 streaks
  show what un-triaged scheduled red costs. Promotion to gating is a later, explicit decision per leg.
- **No widening of the required a11y job** (ADR-029 constraint stands; I7 lives in the module's own workflow).
- **No production mutation.** Legs A and B in production are restricted to the signed-out K0 posture;
  `e2e-prod`'s default-deny CI guard is not touched.
- **No third-party telemetry expansion.** Leg C is first-party or nothing.

### Build order

| Phase | Deliverable | Depends on |
| --- | --- | --- |
| 1 | Leg A mocked-tier walk, invariants I1-I6, seed replay, `usersim.yml` (informational) + route manifest sync test | nothing new |
| 2 | Leg A real-tier nightly variant; I7 axe-on-new-states in the weekly slot | phase 1 |
| 3 | Leg B runner behind `workflow_dispatch`, then weekly once verdict quality is trusted; staging concurrency-group membership | seeded staging creds, LLM budget sign-off |
| 4 | Leg C beacon + digest, gated on the privacy ADR | ADR accepted |

Phase 1 is one PR-sized step and delivers the two cheapest wins on day one: the global clean-console invariant
across everything the walk reaches, and mechanical dead-end detection for all three personas.
