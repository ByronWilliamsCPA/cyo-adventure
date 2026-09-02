# B4: testing and reproducibility engineering

Companions checked: 08-10 brief, register, test plan, authoring-lessons-log (AL-490..503), unscheduled-work-register (UW-C273, C80, C307, C311, C315-C319, C31/C32/C55), ws5_floor_baseline.json, evidence READMEs and run records, code and tests in the research worktree.

1. [CRITICAL] [3.4, F2] The calibrated delivery floor is not an always-on control, and the brief reads as if it were.
Brief: "check_fill_integrity.py enforces a minimum fill rate (0.6...)", attaching "production wiring open" only to the sibling check. UW-C307: "Still open: whether the deterministic gate carries the check"; no production code or CI workflow invokes the script (grep finds only comments). The request path's only delivery control is _WORD_COUNT_TOLERANCE = 0.4 in generation/fidelity.py ("A generous starting tolerance, not calibrated against real fill runs yet"); the AL-490 harness path bypassed it entirely. F2's headline ("every gate is paired with a delivery measurement so a hollow pass is visible") is true of the measurement rig, not the pipeline children's books travel.
Recommendation: wire the fill-rate check into the worker after stage-1 (or as a blocking fill_result gate rule); correct 3.4's wording until then.

2. [HIGH] [3.4, 4.1, F5] Sibling 4-gram budget: unwired, its enabling measurement blocked, no interim mitigation.
Register adds facts the brief omits: the committed pair reproduces at 96.3/1000 (24x budget); the directive-delta run "could NOT execute from the 2026-08-20 remote session" (environment 403s openrouter.ai) and has sat unrun since; compare_vendors.py passed no differentiation directive, so production's directive value is unmeasured while skeleton reuse across families ships today (skeleton_match recency weighting only). scripts/analyze_sibling_exposure.py exists, also unwired. Top wiring gap by product risk: the defect is the brief's own definition of the quality defect that matters.
Recommendation: until the gate lands, surface same-skeleton sibling count plus shared-gram score on the human approval surface (ADR-005 already puts a human there); family-level reuse cap in skeleton_match.

3. [HIGH] [3.1, 3.2] "CI re-proves every changed skeleton from scratch" is true only at the default bar: the promotion prover omits --strict, and the anti-clone check is not in check_skeleton at all.
check_promotion_bundle.py:323-330 builds skeleton_argv = [str(shell_path)] plus at most --allow-mvp; never --strict. Per check_skeleton.py (lines 17-34, 91, 770-930), the walk floor (_WALK_FLOORS line 122), reconvergence cap, depth-qualified endings floor, PL-19/23/24/26 escalations, and enforced choice grammar are all strict-only, so a post-merge hand edit degrading any of them rides a green promotion PR. Brief 3.2 lists "Anti-clone... TAU_CELL" as a check_skeleton --strict check; the script contains no TAU/structural_distance code. Real homes: the prover's lineage-only leg (skipped for hand-authored originals) and tests/unit/test_incell_clone_audit.py::test_committed_catalog_passes_the_gate (whole live catalog per PR: the clone floor IS covered); the strict-bar floors are not.
Recommendation: stamp strict-conformance into skeleton metadata and have the prover enforce --strict for shells claiming it; fix 3.2's attribution.

4. [HIGH] [3.3, 4.1, F4] Model drift: experiments pin, production deliberately does not, and nothing re-benchmarks.
providers/openrouter.py:81-94: provider_order sets allow_fallbacks: false for measurements, "so production behaviour is unchanged", i.e. production OpenRouter calls float across backends and quantizations under one slug: the mechanism behind the fp4/run-6 scare. generation/usage.py records (provider, model) only, never the served backend, so post-hoc drift attribution is impossible. No re-benchmark cadence for fill quality (vendor comparison one-shot; only scheduled live eval is safety-eval.yml, moderation-only), no canary, no deprecation handling beyond FallbackProvider silently cascading to a different model.
Recommendation: capture OpenRouter's served-provider field into usage rows; a small scheduled canary (~$0.3-1.2 per 4-book leg) with z-score drift alarm against archived panel scores; alert on allowlisted-model call failures.

5. [HIGH] [4.3, F5] The 4.0 budget and 3.3 idiom floor are three-pair, one-model, one-band observations now load-bearing for the architecture, and the fill model is about to change.
08-10 brief's own caveat table (line 1986): 3.3 is "an observation on a small sample, not a threshold... 3 book pairs, one model, one age band, range 1.9 to 5.0". F5's stratified verdict (2.3 below the 3.3 floor) and the 4.0-vs-3.3 headroom argument lean on it, while 4.2's consequence is "fill with V4 Pro", a model the floor was never measured on. Neither 4.0 nor 3.3 lives in a committed baseline with a --check (contrast ws5_floor_baseline.json + calibrate_mutation_floors.py --check); the 0.6 floor's comment says "Revisit with the calibration rerun, not by hand" but no rerun script exists. UW-C80 (PL-24 firing 14/14 after a rescale, with a false calibration claim committed in validator/policy.py) shows what an undetected now-wrong constant looks like.
Recommendation: a diversity_floor_baseline.json (budget, floor, model, band, n_pairs) with a calibration script; rule: any fill-model change re-measures the idiom floor before the budget is quoted.

6. [MEDIUM] [5, 4.2] Evidence reproducibility: excellent skeleton, four concrete holes.
A stranger could re-run S-1's paid legs (run.json conditions, --resume command, records/, pre-registered permutation seed) and the vendor comparison (pins, prices, skeleton rationale). But: (a) UW-C316: three merged evidence rigs (recognition pilot, d7c, w16) pre-registered against books never committed, died with a branch; (b) no run record captures harness git SHA or sampling parameters (no temperature anywhere in compare_skeleton_authors.py, compare_vendors.py, or providers, so runs inherit mutable provider defaults, unrecorded); (c) run.json stores an absolute /home/user/... premises path; (d) the tool-assisted condition carrying F3/F4 ran on subagent legs "tier-labeled, not backend-pinned: tier-level conclusions only" (register S-1): the winning condition is the least re-runnable.
Recommendation: run-record schema (git SHA, resolved params, relative paths); UW-C316's present/pending artifact manifest per evidence README.

7. [MEDIUM] [3.2, 4.2] Checker tests are strong, but the named known-bad cases are not CI regression fixtures.
Strengths: test_policy.py pins PL-18 firing and clean; test_topology.py pins UW-C272 PL-18/PL-29 agreement; test_check_skeleton.py covers --strict escalation and the walk floor; test_filled_story_corpus.py and test_skeleton.py re-gate every committed fill and skeleton per PR; test_ci_gate_contract.py executes the CI gate script against synthetic results. Gaps: the AL-490 under-delivering books are committed (vendor-comparison/runs/deepseek-v4-pro-2026-08-20/) but no test re-runs check_fill_integrity over them (one-time manual verification only), so a refactor of commissioned_words_by_node or capping logic could silently move the corpus off the 0.6 floor. The AL-503 PL-18 trap (multi-parent endings) has no committed fixture; S-5's adversarial shell corpus and catch-rate runner are "buildable now" but unbuilt.
Recommendation: committed-corpus calibration test (48 known-good pass, 3 AL-490 books fail); trap-shape fixture landed with the PL-18 message fix.

8. [MEDIUM] [3.4] The gate's blocking claims overstate two rules: reading level never blocks, and gate-side safety is an empty stub.
validator/gate.py documents "RL-13: advisory reading-level check (WARNING, never blocks)" and "SAFE-14: safety content check (Phase-2 stub, always empty)"; generation/reading_level_loop.py records the deliberate ruling (a blocking 7.0 rule would reject 9 of 22 books) and supplies best-effort repair instead; real safety lives in moderation/ plus the weekly live eval. Defensible decisions, but the brief's enforcement map should say "advisory plus harness repair" and "moderation-side" or a reader assumes floors that do not exist.
Recommendation: wording pass on 3.4; surface final FK-vs-band on the approval screen.

9. [MEDIUM] [3.1] skeleton-promotion.yml edge holes: deletion-only PRs skip everything; the no-auto-merge guard is label-gated.
Changed-file collection uses --diff-filter=AM (line 92); prover and "Derived artifacts must be current" step gated on count != 0 (lines 118, 134), so a deletion-only skeletons PR runs neither, though deleting a skeleton invalidates the floor baseline and catalog diagrams (the baseline has "left a required check red on main" once already per the workflow's own comment). no-auto-merge job runs only with the 'skeleton-promotion' label (line 143), so an unlabeled skeletons PR with auto-merge is guarded by nothing here; a paths-filtered workflow cannot be a uniformly required check.
Recommendation: drop the AM filter for the derived-artifacts step (or run calibrate_mutation_floors.py --check in ci.yml); key no-auto-merge on the paths trigger, not the label.

10. [MEDIUM] [3.3] Prompt and template provenance: one hand-bumped string covers fourteen templates, with recorded drift precedents.
generation/worker.py:130 sets _PROMPT_VERSION = "v2", stamped per job row (db/models.py:1487, 2580 persist prompt_version; version_row.model records the generator; moderation reports persist per version with thresholds applied at read time: good design). Nothing binds "v2" to the content of generation/templates/*.md: an edit without a bump leaves records claiming an unchanged prompt. Logged drift precedents: UW-C63 (planning snapshot of prose.md contradicting the live template), UW-C311 (template, SKILL.md, chunking.py disagreeing on whether ending.title is writable).
Recommendation: derive or test-pin the version against a hash manifest of templates/; stamp the validator/gate git version into version_row alongside the model.

11. [LOW] [3.2] TAU_CELL has two loaders with opposite failure semantics; the promotion path uses the permissive one.
diversity/incell.py::load_tau_cell raises ConfigurationError on missing/malformed baseline (tested); mutation/floors.py:62-104 returns hardcoded _FALLBACK_TAU_CELL = 0.05 (and fallback TAU_STRUCT/TAU_STATE) when the baseline cannot load; check_promotion_bundle.py imports floors from mutation.floors. Today fallback equals committed value; after the next recalibration it silently will not, and the prover would enforce a stale floor without failing.
Recommendation: delete the fallback (fail loud) or add a test asserting floors.TAU_CELL == load_tau_cell().

12. [LOW] [4.5, F7] Cost-model inputs are hand-synced with no currency check.
scripts/refresh_pricing.py renders paste-ready _PRICES entries and is wired into no workflow; the provider allowlist seed is "hand-synced" with its migration by admission. Stale unit prices skew exactly the comparisons the framework uses to pick models.
Recommendation: scheduled or pre-run refresh_pricing --check failing when a live price diverges beyond tolerance.

Hardening list, ranked by cost (cheapest first)
1. Wording fixes in the brief: 3.2 anti-clone home, 3.4 fill-rate/sibling wiring status, RL-13 advisory, SAFE-14 stub.
2. Test pinning mutation.floors.TAU_CELL == diversity.incell.load_tau_cell(), or delete the silent fallback.
3. Committed-corpus calibration regression test for check_fill_integrity (48 known-good pass, 3 AL-490 books fail).
4. Run-record schema: git SHA, resolved sampling params, relative paths; present/pending artifact manifest per evidence README.
5. AL-503 trap fixture: multi-parent-endings shell; assert PL-18's message names the first reconverging node; test-first with the message fix.
6. skeleton-promotion.yml: run derived-artifacts currency on deletions; key no-auto-merge on paths, not label.
7. Hash-manifest binding for _PROMPT_VERSION over generation/templates/.
8. Capture OpenRouter's served-backend field into usage.py records.
9. refresh_pricing.py --check on a schedule.
10. Wire fill-rate 0.6 into the worker/gate per the UW-C307 decision.
11. Sibling-fills interim mitigation on the approval surface plus family reuse cap; then the full pipeline gate (UW-C315).
12. Strict-conformance stamp in skeleton metadata, enforced by check_promotion_bundle.py.
13. Diversity-floor baseline JSON with calibration script and fill-model-change re-measurement rule (unblocks the V4 Pro migration safely).
14. Build the S-5/E5 adversarial shell corpus and catch-rate runner.
15. Scheduled fill-quality canary with drift alarm (small paid grid, quarterly or per model change).

Strengths
- Rare meta-testing depth: the CI gate's own shell logic executed against synthetic results; shrink-only allowlists with stale-entry failures; every committed skeleton and filled book re-gated per PR.
- A genuinely enforced deterministic/model-judged/human split: llm_eval tier scheduled, credential-gated, off the PR path; judge panels blinded, cross-lab, pinned, verified by exit code.
- Evidence hygiene that admits failures: pre-registration, backend pins with unit tests on request body shape, halted runs documented with exact resume commands, headline results retracted on scrutiny (fp4/run-6, S-0).

Top 3
1. Wire the two floors the programme invented for F2 (fill-rate 0.6, sibling 4.0) into an always-on path; today the "hollow pass" defense exists only where nobody ships from.
2. Close the strict-bar gap at promotion: CI proves a weaker bar than the one S-1 selects models against; strict-only floors are unenforceable after merge.
3. Give every calibrated constant a committed baseline, a --check, and a model-change recalibration trigger; the V4 Pro migration invalidates the measured basis of 3.3/4.0 the day it lands.
