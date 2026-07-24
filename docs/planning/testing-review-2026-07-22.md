---
purpose: Comprehensive critical review of the test suite (coverage by test type, test
  quality, and mocking vs real data), with prioritized findings and recommendations.
component: testing
source: session 2026-07-22, branch claude/testing-coverage-quality-review-eyceyy
related: handoff-comprehensive-e2e-audit-2026-07-22.md,
  handoff-test-coverage-robustness-2026-07-22.md
---

# Critical Review: CYO Adventure Test Suite (2026-07-22)

## Methodology and caveat

This review was produced by six parallel deep-dive analyses (backend unit, backend
integration, coverage-by-type, specialized test types, frontend, and cross-cutting
infra/data-realism), plus direct inspection of the CI wiring and the Playwright E2E
tiers. Every Critical and High finding below was re-verified against source before
being recorded.

One caveat: Docker was unavailable in the review environment, so the integration
suite could not be executed and no live combined-coverage number was produced. The
coverage picture is drawn from the CI gate configuration (which runs unit,
integration, and security as separate coverage buckets combined against an 80%
floor) and from static mapping, not from a local run.

This document is a companion to the two same-day handoffs it references: the E2E
audit (environment/readiness focus) and the test-coverage-robustness handoff. Where
they overlap, this review takes the test-design and mocking-discipline view.

## Bottom line

This is a top-decile test suite for a project of this size. The plumbing is
excellent: a genuine pyramid (unit, integration on real Postgres, component, browser
E2E, deployed smoke), disciplined mocking that inverts correctly by tier, real
fuzzing, cross-language conformance, a real hand-authored story corpus, strong
determinism, and a systematic authorization matrix. The weaknesses are not in the
mechanics; they cluster at two altitudes: proving the AI safety gate actually works
against real adversarial content, and drift-proofing a handful of hand-maintained
contract seams. There is also a real hole in non-functional (performance) testing.

Quick answers to the three questions this review was asked:

| Axis | Grade | One-line verdict |
| --- | --- | --- |
| Coverage by test type | A- base/mid, C at top | Every one of 28 routers is covered; unit/integration/component/E2E/contract/fuzz/property/conformance are all real and gated. Missing: performance testing, and any behavioral safety evaluation. |
| Test quality | A- | Unit discipline is exemplary (real domain objects, not mock bags); integration is honest; frontend asserts real DOM. Deductions for a misleading "mutation" label, a thin safety corpus, and a few dead assertions. |
| Mocking vs actual data | B+ | Excellent at unit (real ORM objects), integration (zero DB mocks, real Postgres), and E2E (network-boundary plus a real-stack tier). The soft spot is the frontend: hand-mirrored API adapters plus no MSW plus no test pinned to a real payload. |

## Scale

- Backend: 249 test files, roughly 3,776 test functions and 7,500 assertions.
- Frontend: 119 vitest files (2,252 DOM assertions), plus 13 design-system tests.
- E2E: 48 Playwright specs across four tiers.
- Test-to-source LOC ratio is roughly 1.45:1 (92.6k test LOC vs 63.7k source LOC).

## Part 1: Coverage by test type

The type taxonomy is real and mostly gated, not aspirational.

| Test type | Present | Scale / location | Gated in CI? | Load-bearing? |
| --- | --- | --- | --- | --- |
| Unit | Yes | ~124 files (`unit` marker) | Yes (bucket) | Yes, primary base |
| Integration (real Postgres) | Yes | 53 files, testcontainers `postgres:16` | Yes (bucket) | Yes, stops at API+DB |
| Component (vitest + Testing Library) | Yes | 119 files, 2,252 `screen.` assertions | Yes | Yes |
| E2E browser (Playwright) | Yes | `e2e/` 34 (mocked API) incl. a11y (axe) + visual snapshots + naive-user misuse | Yes, per-PR | Yes |
| E2E full-stack (real backend) | Yes | `e2e-real/` 9 specs, zero mocks | Nightly only | Yes, off PR path |
| Deployed smoke | Yes | `e2e-staging/` 2, `e2e-prod/` 3 | Scheduled | Yes |
| Contract (OpenAPI drift) | Yes | `contract` CI job + `test_schema_parity` (ORM to SQL) | Yes | Yes, strong |
| Property-based (Hypothesis) | Yes | 6-7 files (player, evaluator, mutation ops) | Yes | Yes where present |
| Fuzz (atheris + ClusterFuzzLite) | Yes | 2 targets, harness re-checked every CI run | Weekly + per-run guard | Yes |
| Conformance (Python to TS parity) | Yes | shared `schema/conformance/*.json` | Yes | Yes |
| Mutation (mutmut) | Yes | `nox -s mutate` + weekly workflow | Reports only, no gate | Partial |
| Security | Yes | 18 files (authz, JWT/OIDC, PII, RLS, PIN/device) | Yes (bucket) | Yes |
| AI-security / adversarial | Thin | 1 corpus file, 13 items | Deterministic-only | Weak (see C1) |
| Performance / load | No | markers defined, 0 usages, no k6/locust | No | Absent |
| `llm_eval` behavioral tier | No | marker defined, 0 tests, 0 CI | No | Absent |

What is strong: the base and middle are genuinely deep. `test_authz_matrix.py` builds a
`ROUTE_TABLE` asserted to match the app's live-discovered routes (so a new endpoint
without an authz spec fails CI), then parametrizes 401-without-token, an allow/deny
matrix across all roles, and cross-family IDOR rejection driven by a dedicated
`stranger` family. That single file kills whole bug classes.

What is missing (the gaps that matter):

- No behavioral safety evaluation (see Critical C1). Most consequential gap for a
  children's product.
- Zero performance/load testing. `perf`, `performance`, `benchmark`, `slow`, `smoke`,
  `regression` are all defined-but-unused dead markers. Nothing measures library-list
  latency (an N+1 enrichment risk exists), worker throughput, or the condition
  evaluator on worst-case graphs.
- Full-stack E2E is nightly-only and never drives the RQ worker in-loop. The
  request to generate to gate to moderate to publish to read pipeline is only ever
  asserted in fragments; no single test drives an actual generation job through the
  worker to a kid-readable book.
- Three to five routers are unit-only at the integration layer. `node_edit` is the
  notable one: it is a content-mutation router (guardian edits to story nodes with
  re-screen implications), yet its DB round-trip and side effects are never exercised
  against real Postgres.

## Part 2: Test quality

Backend unit tests: exemplary discipline. The dominant pattern is a hand-rolled fake
session that returns real ORM instances (`Storybook`, `StorybookVersion`, `Rating`,
`GenerationJob`), so a divergence from the real model breaks the test. Core-logic
tests (`test_player_engine.py`, `test_layer1_validator.py`) run zero mocks against
real validated fixtures. There are SQL-level regression pins (for example
`test_approval_unit.py:145` renders the statement under the Postgres dialect to catch
a weakened `FOR UPDATE`; `test_library_api_unit.py:434` inspects WHERE clauses and
bind params to pin IDOR scope and prevent N+1) and mutation-grade boundary tests
(`test_player_engine.py:326` distinguishes `> high` from `>= high`).

The blemishes are minor and each was verified:

- One genuinely dead assertion: `test_node_edit.py:409` ends `... or True`, so the
  intended check (edited prose surfaces in `flagged_passages`) never actually runs.
  Only one such in the whole suite.
- Four tautological "default is None" tests in `test_correlation.py:38-91` that assert
  `result is None or isinstance(result, str)` (always true) and do not reset the
  context var.
- A few `SimpleNamespace` casts to real ORM types (`test_anchoring.py`,
  `test_worker.py`) that forgo the schema-drift safety net the rest of the suite is
  careful to preserve.

Backend integration tests: honest. Nothing mocks the DB, session, or engine anywhere;
every test runs against a real container through the app's real unit-of-work. External
seams (LLM providers, RQ enqueue, R2, cover art, Supabase JWT) are faked at their
network boundaries, not by hollowing out pipeline logic. RLS is genuinely exercised in
a dedicated real-migrations test, and the append-only event trigger is tested against
real Postgres trigger semantics.

Frontend: strong component testing. 2,252 real DOM assertions via Testing Library;
components render for real against the real shared story fixture (`Reader.test.tsx`
wraps the real engine, covers conditional-choice visibility, endings,
corrupted-transition recovery, TTS lifecycle). The offline layer is excellent
(realistic `fake-indexeddb`, deep coverage of 409 conflict, rebase, replay-dedupe,
revocation reference-counting).

Specialized types: mostly load-bearing, one misleading label.

- Fuzzing is real (atheris + ClusterFuzzLite, with an explicit anti-rot guard so a
  broken harness cannot stay green).
- Cross-language conformance is real and bidirectional: the Python `StoryEngine` and
  the TypeScript player run the same `conditions.json` (42 cases) and
  `player_traces.json`.
- The roughly 30 `test_mutation_*.py` files are NOT mutmut mutation testing. They are
  unit tests for a domain package, `cyo_adventure.mutation` (story-tree variation
  operators). Real mutmut exists but enforces no kill-floor on PRs or on any automatic
  schedule (it reports weekly, gates only on manual dispatch). So the suite looks like
  it has rigorous test-effectiveness enforcement (roughly 30 "mutation" files) while
  actually having none continuously enforced. This is the single most misleading thing
  in the suite.

## Part 3: Mocking vs actual data

The good news: mocking discipline is correct and tiered. Mock density inverts the way
it should: the unit dir has 619 mock/patch lines, the integration dir only about 73,
and the integration dir mocks zero DB/session/engine. E2E goes further: `e2e/` mocks
at the network boundary (`page.route`), and `e2e-real/` uses no mocks at all against a
real backend. Test data is realistic: a committed corpus of 9 hand-authored Storybooks
(17-43 nodes each) plus 16 labeled-invalid fixtures, round-tripped through the
production `Storybook.model_validate` / `validate_layer1` / `StoryEngine`, not
synthetic stub dicts. For the backend this answers the question in the affirmative:
real data is used where it matters.

The soft spots, ranked by risk:

1. Frontend hand-mirrored API adapters (acute). A tier of adapters (`libraryApi.ts`,
   `recommendationsApi.ts`, `intakeApi.ts`, `reviewApi.ts`, `budgetApi.ts`) explicitly
   bypasses the generated client ("the generated client is unused", verified at
   `libraryApi.ts:7`). They hand-type the response interfaces and their tests inject a
   hand-rolled fake axios returning hand-authored payloads. Because these modules
   import nothing from `frontend/src/client/`, the CI drift gate (which only diffs the
   generated client) does not protect them: a backend field rename regenerates the
   client cleanly, `tsc` passes, and the stale mirror plus its green test ship a bug
   that only an E2E run or production catches.

2. No frontend test pins to a real backend payload, and no MSW. 631 `vi.mock`/`vi.fn`
   calls, zero MSW, and a grep for any test referencing the OpenAPI schema or a real
   payload returns empty. Even the "good" adapters that import generated types only get
   compile-time shape checks; the runtime values every test asserts are invented, and
   the request paths/params are hand-written strings the drift gate never checks (the
   generated SDK functions are deliberately unused).

3. Player parity corpus is thin and omits the offline-resume paths. Forward traversal
   is pinned identically across Python and TypeScript, but only via 3 traces, and
   `back()`/replay and `startContinuation()` seeding are tested only on the frontend
   with no backend counterpart. Those are precisely the offline paths where a kid could
   see different branching offline vs online.

4. Integration schema is `create_all`, not production migrations (mostly fine, one real
   hole). About 56 of 59 integration files build their schema from
   `Base.metadata.create_all`, so RLS, triggers, functions, grants, and FK
   delete-actions are absent from the schema most tests run against. This is a
   deliberate speed tiering and is mostly safe because `test_schema_parity.py` diffs
   structural DDL and the two highest-blast-radius objects (RLS grants, append-only
   trigger) each get a dedicated real-migrations test. But the parity snapshot drops FK
   `ON DELETE` actions (verified: `test_schema_parity.py:143-145`), which the GDPR/COPPA
   erasure-cascade drill (`test_deletion_drill.py`) depends on, and the erasure
   migration's own header falsely claims parity keeps those in sync (verified:
   `20260720170000_add_erasure_cascades.sql:48-49`). That is a compliance-grade
   divergence risk with a one-line fix.

Note: the E2E audit's P0-1 defect (offline multi-device resync `422 extra_forbidden`)
is a real-world instance of this same thesis. The mocked E2E tier did not enforce the
backend's strict `extra=forbid`, so the bug surfaced only against the real backend
(`offline-conflict-real.spec.ts:157`). The unit guard added afterward
(`offline/sync.test.ts` `FORBIDDEN_VIEW_KEYS`) is itself a hand-maintained mirror of
the backend model and can drift again for the same reason.

## Prioritized findings

| # | Sev | Finding | Evidence | Fix effort |
| --- | --- | --- | --- | --- |
| C1 | Critical | No behavioral safety evaluation. The moderation gate (real OpenAI Moderation + Perspective adapters) is validated with mocks only; the adversarial corpus is 13 items and self-asserts `is_evidence is False`; the `llm_eval` tier is 0 tests / 0 CI. Nothing measures the real catch-rate against unsafe/jailbreak content on any cadence. | `test_ai_security_corpus.py:172`; `llm_eval` 0 usages | Medium-Large |
| H1 | High | FK `ON DELETE` parity gap leaves erasure-cascade correctness unguarded; migration header falsely claims coverage. | `test_schema_parity.py:143-145`; erasure migration header 48-49 | 1 line |
| H2 | High | Frontend hand-mirrored adapters bypass the generated client; no real-payload/OpenAPI-pinned test; paths/params unchecked. | `libraryApi.ts:7`, +4 adapters | Medium |
| H3 | High | "Mutation testing" is a domain-feature naming collision; real mutmut enforces no kill-floor on PRs/schedule. | 23/24 `test_mutation_*` import `cyo_adventure.mutation`; `mutation-testing.yml:78` | Small-Medium |
| H4 | High | Zero performance/load testing; `perf`/`benchmark`/etc. are dead markers. | 0 marker usages; no k6/locust | Medium |
| M1 | Med | Full-stack E2E is nightly-only and never drives the RQ worker; pipeline asserted only in fragments. | `e2e-real-nightly.yml` | Medium |
| M2 | Med | Schema parity omits policy/trigger/function presence, so a new security-relevant DB object can reach prod untested. | `test_schema_parity.py` `_snapshot` | Small |
| M3 | Med | Player parity corpus thin (3 traces); back()/continuation untested cross-language. | `player_traces.json` | Small-Medium |
| M4 | Med | `interrogate` + `pydoclint` "gates" only wired into `nox`, which CI never invokes. | `pyproject.toml:770`; no workflow | Small |
| M5 | Med | `-n=auto` coverage-combine verified only on a ~140-test subset while the 80% floor gates. | `pyproject.toml:681` `#VERIFY` | Small |
| M6 | Med | Security blind spots: no behavioral rate-limit test, no CORS/header negative assertions. | middleware tests only | Small-Medium |
| L1 | Low | `node_edit` (content-mutation router) is unit-only, no functional integration/DB round-trip. Also rescreen/audit/reading_history/recommendations/notifications thin at integration. | authz-matrix presence only | Small |
| L2 | Low | Dead assertion `test_node_edit.py:409` `or True`; four tautological `test_correlation.py` tests. | verified | Small |
| L3 | Low | `SimpleNamespace` cast to real ORM types forgoes schema-drift safety net. | `test_anchoring.py`, `test_worker.py` | Small |
| L4 | Low | Index method/predicate (btree vs GIN, partial WHERE) not compared in schema parity. | `test_schema_parity.py:153-156` | Small |
| L5 | Low | Frontend coverage gate 70% per-file vs backend 80%. | `frontend/vite.config.ts:210-216` | Small |
| L6 | Low | No `@example` regression seeds; no stateful (`RuleBasedStateMachine`) property tests. | property test files | Small |

## Recommended next actions

Quick wins (hours, high leverage):

- H1: add `fk["options"].get("ondelete")`/`onupdate` to the parity snapshot tuple.
  Closes a compliance gap the migration already assumes is closed.
- H3: either make the weekly mutmut run gate on a committed baseline score, or rename
  the domain tests (`test_skeleton_mutation_*`) to end the collision. Ideally both.
- L2: delete the `or True` at `test_node_edit.py:409` and assert the real condition;
  fix the four `test_correlation.py` tautologies.
- Dead markers: retire `perf`/`slow`/`smoke`/`regression`/`llm_eval` or start using
  them; stop describing `interrogate`/`pydoclint` as gates (M4) or wire them into
  `ci.yml`.

Highest-value investment (C1): stand up the scheduled `llm_eval` tier that the marker
already anticipates. Run the A-F adversarial taxonomy against the real classifiers with
an asserted minimum catch-rate and a PII-egress floor, weekly, opening an issue on
regression (mirror `mutation-testing.yml`). Grow the corpus well beyond 13 items. For a
kids' safety product this is the gap most worth closing.

Medium investments: type the five hand-mirrored frontend adapters against `types.gen`
so `tsc` catches drift, and add one MSW-backed contract smoke seeded from OpenAPI
examples (H2); add a small perf tier with real latency/throughput budgets (H4); extend
the shared player corpus with back/continuation traces run through both engines (M3);
add policy/trigger/function presence to schema parity (M2); add rate-limit + CORS tests
(M6); one nightly full-pipeline E2E through the real worker (M1).

## What is genuinely strong (do not regress)

- Disciplined, tier-appropriate mocking; real ORM objects behind fake sessions.
- Real-Postgres integration with zero DB mocking and a systematic authz/IDOR matrix.
- Real hand-authored story corpus round-tripped through production validation.
- Strong determinism (0 `time.sleep`, 0 `utcnow`, all randomness seeded,
  `pytest-randomly` on) and excellent skip/xfail hygiene (0 bare skips, 0 xfails).
- Real fuzzing with an anti-rot guard, and genuine bidirectional Python/TS conformance.
- A complete browser E2E pyramid including a real-stack tier, deployed smoke, visual
  regression, accessibility (axe), and adversarial naive-user misuse specs.
