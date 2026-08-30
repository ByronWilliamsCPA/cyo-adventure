# B3: Evidence and methodology audit of the 2026-08-22 generation research brief

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure/.worktrees/brief-evidence/`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

Subject: `docs/planning/cyo-generation-research-brief-2026-08-22.md`.
Evidence audited from the full source branch at `/home/user/cyo-adventure/.worktrees/brief-evidence/`
(`claude/model-selection-skeleton-dev-78yp7u`): the diversity test register (section F, rows
`S-0`..`S-5`), `docs/planning/skeleton-sourcing-test-plan-2026-08-21.md`,
`docs/planning/evidence/**` (including `skeleton-author-vendors/` with 291 files across five run
directories, and `recognition-protocol-pilot/` with `results.md` and six rater verdicts),
`docs/planning/vendor-comparison/**`, `cyo-measurement-workplan-2026-08-12.md`,
`authoring-lessons-log.md` (`AL-510`..`AL-514`), `unscheduled-work-register.md`
(`UW-C317`..`UW-C320`), and `scripts/compare_skeleton_authors.py`, `scripts/judge_books.py`,
`scripts/check_sibling_fills.py`, `src/cyo_adventure/diversity/incell.py`.

## Retractions

An earlier pass of this audit was run against a branch carrying only the brief. Four findings that
rested on the absence of artifacts are **withdrawn in full and were wrong**:

- *"Section 4.2 has no pre-registration"*, **retracted.** `skeleton-sourcing-test-plan-2026-08-21.md`
  (562 lines) and register section F (`S-0`..`S-5`) both exist, pre-date the runs, and are unusually
  detailed: named legs, named cells, a single named primary endpoint, a named permutation test with
  seed and alpha, explicit multiplicity discipline, and a threats-to-validity section that commits to
  specific controls.
- *"No S-1 raw data"*, **retracted.** `evidence/skeleton-author-vendors/` carries per-shell records,
  final shells, run conditions, and summaries for five runs including two declared-excluded smokes.
- *"The recognition-protocol result has no artifact"*, **retracted.** `results.md` and six verdict
  JSONs exist; the brief's "both raters called a cross-graph pair the same adventure" is accurate.
- *"`AL-510`..`AL-514` / `UW-C317`..`UW-C320` do not exist"*, **retracted.** All eight exist and are
  substantive.

**Standing assessment.** The register, the test plan, and the evidence READMEs are among the more
rigorous experimental records I have audited: pre-registration with named falsifiers, declared
deviations with explicit statements of data contact, excluded smoke runs, retracted attributions, and
self-reported instrument failures. Almost every finding below is a defect in **the brief's rendering
of that evidence**, or a signal present in the raw records that the brief does not report. Two
findings (B3-1, B3-4) are new results I computed from the committed data that point against the
brief's conclusions.

Conventions: binomial intervals are Clopper-Pearson exact two-sided 95%; unpaired 2x2 tests are
Fisher exact two-sided; the S-1 grid is a **paired** design (premise held constant per cell x
replicate across all seven legs, verified from the records), so exact McNemar is also reported.
All arithmetic is reproduced in Appendix A.

---

## B3-1: The recognition verdicts say F5's passing arm reads as the same adventure at scene 2, and the brief reports only the gram number
- **Severity**: critical
- **Category**: instrument validity
- **Locus**: brief:75-78 "topology and a bare-names fact graph can be shared across books without measurable prose convergence (2.3 shared 4-grams per 1000, under the 4.0 budget and below the 3.3 generator idiom floor)" against `evidence/recognition-protocol-pilot/results.md` and `verdict_d7b-bare-CD_r{1,2}.json`
- **Problem**: The S-0 validation used D-7b's C/D pair, **the exact artifact F5 rests on**, as a known-answer same-armature pair. All four same-armature verdicts (both pairs, both orders) came back `same_adventure: yes`, `first_yes_position: 2`, `distinctness_1_to_5: 1`. The D-7b (bare-names, "passing", 2.3 grams/1000) pair and the D-7 (glossed, "failing", 13.6 grams/1000) pair produced **identical verdicts on every dimension**. The rater's cited signal for D-7b is decision-level, not lexical: *"Scene 2 repeats Book One's exact three-way opening choice (wait patiently for a clue / work the structure with your own hands / ask the old keeper who knew the builder), and every scene after maps one-to-one onto the same beats, hub, dial, and endings."* So deleting 422 gloss words moved the deterministic metric by a factor of six and moved the perceptual read by exactly zero. This is not a marginal reading: the register already flagged the exposure, *"11 of 35 choices share their opening verb across the two books ... A reader study would be needed to say whether shared opening verbs read as repetition; no measure here can"*, and something has now read it. The instrument's known failure mode is **over-firing on a control** (false positives on genuinely different books); that failure mode does not explain a positive on a pair that genuinely shares its armature, and it is orthogonal to the fact that D-7b scored identically to D-7.
- **Why it matters for the goal**: The brief's own section 1 defines the defect that matters: *"A reader tracks what they were asked to decide, not the shape of the tree ... two books with different graphs that offer the same decisions in the same order read as the same book re-skinned."* F5 then declares victory on **shared 4-grams**, a wording metric, for an arm that four raters say offers the same decisions in the same order. F5 is the architecture, it sets what is authored once versus per book and therefore the marginal cost of every book the product ships. If the shareable structural stratum reproduces the decision sequence, then "reuse structure freely" delivers exactly the defect the programme exists to prevent, and the gram budget is measuring the wrong layer. This is the single largest gap between what was measured and what is claimed.
- **Recommendation**: (1) Report the D-7b recognition verdict in the brief beside the 2.3, as a directly contradicting observation, not as an instrument footnote. (2) Do not treat F5 as established until a *decision-level* deterministic measure adjudicates the D-7b pair, solution transfer (D-4 tier 1) is already built, deterministic, taxonomy-free, and the only computed measure that has tracked readers; run it on `d7b-bare-names/filled_C` vs `filled_D` today, at zero cost. (3) If solution transfer also says the pair converges, F5 needs restating: the shareable stratum must exclude the `choice_semantics`-bearing layer at a coarser grain than bare names achieve, and the shared-gram budget must be demoted from an architecture gate to a wording hygiene check.
- **How to check I'm right**: `python3 -c "import json;d=json.load(open('.worktrees/brief-evidence/docs/planning/evidence/recognition-protocol-pilot/verdict_d7b-bare-CD_r1.json'));print(d['first_yes_position'],d['distinctness_1_to_5'],d['strongest_signal'])"`, then the same for `_r2` and for `verdict_d7-glossed-CD_r{1,2}`. Compare against the register's D-7b row (2.3 per 1000) and its "11 of 35 opening verbs" qualification.

---

## B3-2: S-1's pre-registered primary endpoint was degenerate in both runs, and every decision now rests on endpoints the registration declared decision-inert
- **Severity**: critical
- **Category**: pre-registration
- **Locus**: register `S-1` row: "**Primary endpoint only**: repair rounds to strict pass, pooled across cells, permutation test over leg assignment, 10,000 permutations, alpha 0.05. Falsifier: no leg pair separates at that level; then the model axis is dropped and downstream arms use the cheapest strict-passing leg. **All other endpoints exploratory, decision-inert.**" Against `runs/e1r3-2026-08-21/summary.md` and `runs/e1r3-tools-2026-08-21/summary.md`, and brief:207-214
- **Problem**: Three linked failures.
  1. **Both runs' primary endpoint is vacuous.** The blind run reports `between-leg statistic 2.571, p = 1.0000` with mean repair rounds of 6.00 for six of seven legs, fully censored at the cap (`AL-513`: 14 of 15 cell-A points hit it). The tool-assisted run reports `between-leg statistic 0.000, p = 1.0000` because **every leg's mean repair rounds is 0.00**: the harness's `--score-shell` mode was called once per shell, so `repair_rounds` is structurally zero for all 42 shells. The tool-assisted permutation test is a test on an all-zero vector. The brief discloses the blind degeneracy ("the pre-registered repair-rounds endpoint was degenerate under that censoring") and **does not disclose the tool-assisted one**, which is the run every conclusion comes from.
  2. **The pre-registered falsifier fired and its pre-registered consequence was not followed.** "No leg pair separates at that level" is exactly what p=1.0000 reports, twice. The registered consequence is "the model axis is dropped and downstream arms use the cheapest strict-passing leg." The brief instead concludes the model axis matters (F4) and names a specific tier. The register's justification, that p=1.0 is the cap speaking, not equivalence, is correct and honest, but it means the experiment produced **no valid reading on its primary endpoint**, not a reading in the other direction.
  3. **The decision moved onto an exploratory endpoint.** Strict pass/fail and checker invocations are the tool-assisted condition's endpoints, added after the blind primary went degenerate. The plan's multiplicity rule is explicit: *"one pre-registered primary endpoint per experiment; everything else is exploratory and cannot trigger a decision rule"*, and E1 warns *"10 pairwise leg comparisons x 5 endpoints x 4 cells guarantees spurious separation somewhere"*, with 7 legs that is 21 pairwise comparisons. Section F's own amendment rule states: *"amending one after its experiment has produced artifacts voids that experiment's pre-registration and must be recorded here as such."* The S-1 row records the amendment in narrative but does not record the pre-registration as voided, and the brief presents the result with no indication that its endpoint was not the registered one.
- **Why it matters for the goal**: F4 and the per-stage routing recommendation are the brief's main architectural output from this cycle. They are derived from a decision-inert endpoint after the decision-bearing endpoint failed. The programme's pre-registration machinery is genuinely good; this is the case where it was written down, fired, and then routed around, which is precisely the situation pre-registration exists to make visible. Left unmarked, it teaches the next cycle that a degenerate primary can be replaced post hoc.
- **Recommendation**: (1) Record `S-1`'s pre-registration as **voided** per section F's own rule, and re-register the tool-assisted condition as `S-1b` with a primary endpoint that is not structurally zero (candidate: strict pass at first checker invocation, or checker invocations to pass with censored observations handled by a survival/Cox model rather than a mean). (2) Rewrite brief section 4.2's opening to state that the registered primary endpoint returned no reading in either condition and that the table is exploratory. (3) Do not act on F4's routing until `S-1b` returns a primary result.
- **How to check I'm right**: `head -4 .worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/summary.md` → "statistic 0.000, p = 1.0000 ... Everything below is exploratory." Same for `e1r3-2026-08-21/summary.md` → "2.571, p = 1.0000". `python3 -c "import json;print(json.load(open('...records/A__r1__claude-fable-subagent.json.record.json'))['repair_rounds'])"` → 0, for every leg. Register section F preamble for the amendment rule.

---

## B3-3: The decision-bearing tool-assisted arm ran outside the instrumented harness; its entire record is a hand-maintained three-field file, so the harness-versus-model confound is unresolvable from the artifacts
- **Severity**: critical
- **Category**: confound
- **Locus**: `runs/e1r3-tools-2026-08-21/tools-meta.json`; the 42 records in that run; `scripts/compare_skeleton_authors.py:748-758`; `UW-C320`
- **Problem**: The blind arm is fully instrumented: `run.json` fixes conditions (cells, replicates, `max_repair_rounds: 6`, `max_tokens: 65536`, premises file, vendors file), and records carry attempts, repair rounds, per-round validator feedback, output tokens and finish reasons. The tool-assisted arm has none of that. **Every one of its 42 records reads `attempts: 1`, `repair_rounds: 0`, `latency_s: 0.0`, `input_tokens: null`, `output_tokens: null`, `finish_reasons: []`**, the harness only scored the final submitted shell. There is no `run.json`. The only record of the condition that produced the brief's entire table is `tools-meta.json`: a hand-written dict of `{checker_runs, reported}` plus three free-text notes. `UW-C320` confirms the mode does not exist in the harness yet ("Add a labeled `tool-assisted` condition to `compare_skeleton_authors.py`'s subagent driver").

  Consequences, in order of severity:
  - **The scaffold-equality claim cannot be verified for this arm.** For the *blind* arm it can and does hold: `--emit-prompts` writes one `system.md` and one author prompt per grid point handed "verbatim" to every leg, and `--score-shell` "applies the identical strict check the provider legs get". That is a real control and my earlier suspicion of unequal blind scaffolds is withdrawn. But the tool-assisted arm bypassed both modes for the iteration loop.
  - **The two conditions are structurally different for subagent versus API legs.** The register defines tool-assisted as "the author may run `check_skeleton.py --strict --allow-mvp` against its own draft up to 10 times and **iterates in one session**". A subagent can literally do that: stateful session, direct CLI invocation, full stdout. An OpenRouter or Modal leg cannot; per the harness docstring the driver "relays it verbatim into the **stateless** repair prompt". So four of seven legs got stateful self-serve tool use and three got a relayed stateless loop with more rounds. Nothing in the artifacts records which of the two each non-Anthropic leg actually received.
  - **The driver is not blind and is in-family.** The relaying session is itself a Claude session (the S-0 raters are recorded as `claude-fable-5`), deciding how to relay and when to stop, for the legs it is being compared against.
  - **No token or cost accounting exists for the deciding arm**, for any leg, so the cost half of F7 cannot be computed from it at all.
  - **`tools-meta.json` is incomplete**: two of 42 shells (`D__r1__deepseek-v4-flash`, `D__r1__deepseek-v4-pro`) have no `checker_runs` entry, and four have no `min_catalog_distance`.
  - The one control that *does* hold: I checked all 42 shells' self-reported `PASS`/`FAIL` against the harness's independent `strict_pass`. **Zero mismatches.** The pass/fail column is trustworthy; it is the process behind it that is unrecorded.
- **Why it matters for the goal**: F4's routing recommendation ("author structure with a tool-assisted Anthropic tier") is exactly the claim that a harness confound would fabricate, and the arm that produced it is the one arm with no harness record. The repository has paid for this class of error twice already, `AL-327` (an unparseable fill returned the skeleton and the gate certified it as a pass) and `AL-328` (*"a fixed `max_tokens` is not a neutral condition in a cross-vendor comparison"*; Sonnet 5's fill rate was "a property of `_MAX_TOKENS_PROSE`, not of Anthropic"). Brief:204's "call budget lost to unparseable output" for v4 Flash is the same shape and, on this evidence, cannot be classified as a model finding.
- **Recommendation**: (1) Build the tool-assisted mode into `compare_skeleton_authors.py` per `UW-C320` before any further reading is taken from this arm, it must log per-invocation checker calls, the exact feedback returned, whether the loop was stateful, and tokens where the provider reports them. (2) Re-run at least one Anthropic tier and one DeepSeek leg under the *same* driving procedure (both relayed statelessly, or both self-serve via a tool-calling loop) as an explicit harness control; that 2x2 is cheap and decides whether F4 is about models. (3) Until then, restate brief:207-213 as "under a tool-assisted regime whose per-leg driving procedure was not instrumented".
- **How to check I'm right**: `python3 -c "import json,glob;print({json.load(open(f))['leg']:(json.load(open(f))['attempts'],json.load(open(f))['repair_rounds'],json.load(open(f))['output_tokens']) for f in glob.glob('.worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/records/*.json')})"` → all `(1, 0, None)`. `ls runs/e1r3-tools-2026-08-21/` → no `run.json`. `sed -n '748,760p' scripts/compare_skeleton_authors.py` for "stateless repair prompt". `grep UW-C320 docs/planning/unscheduled-work-register.md`.

---

## B3-4: Strict-pass rate is almost perfectly rank-inverted with structural novelty (Spearman -0.982, exact p = 0.0016): the brief's recommended structure authors are the ones producing the most catalog-like graphs
- **Severity**: critical
- **Category**: confound
- **Locus**: `runs/e1r3-tools-2026-08-21/summary.md` and the 42 records' `min_catalog_distance`; brief:207-214; `docs/planning/ws5_floor_baseline.json`
- **Problem**: The harness scores every authored shell's `structural_distance` against its in-cell catalog peers, and the plan pre-registered this as an exploratory Tier-2 endpoint. The brief reports none of it. Computed per leg (median of `min_catalog_distance`, all 42 shells):

  | leg | pass | median min catalog distance | closest single shell |
  |---|---|---|---|
  | claude-opus-subagent | 6/6 | 0.1131 | **0.0507** |
  | claude-fable-subagent | 6/6 | 0.1152 | 0.0665 |
  | moonshot-kimi-k3-modal | 5/6 | 0.1302 | 0.0630 |
  | claude-sonnet-subagent | 4/6 | 0.1674 | 0.0833 |
  | deepseek-v4-flash | 3/6 | 0.1731 | 0.1499 |
  | claude-haiku-subagent | 3/6 | 0.1904 | 0.1381 |
  | deepseek-v4-pro | 0/6 | 0.2155 | 0.1719 |

  Spearman rank correlation between pass rate and median catalog distance is **-0.982**; the exact two-sided permutation test over all 5,040 orderings of seven legs gives **p = 0.0016**. This is by a wide margin the best-powered leg-level effect in the S-1 dataset, better powered than any pass-rate contrast, and it is the one the brief omits. Two readings, both consequential: either the strict bar rewards conventional graph shapes, or the legs that pass are the ones that reproduce the catalog's existing structures. Either way, **selecting a structure author on strict-pass rate selects against structural novelty**, which is the programme's own stated primary quality objective. The margin is not academic: the recommended leg's closest shell sits at 0.0507 against `TAU_CELL` 0.05, a 1.4% margin from being rejected by the anti-clone gate, and Opus produced two of the three closest shells in the entire grid.
- **Why it matters for the goal**: The brief's section 1 names catalog convergence as the defect the whole programme exists to fight, and S-0's own control failure is diagnosed as *"the programme's own catalog-convergence finding ... appearing inside a 'different graph, different world' pair"*. F4 then recommends, on the basis of pass rate alone, the two legs whose output is closest to the existing catalog. That is a direct optimization against the objective. It is also the mechanism by which the catalog would silently accumulate near-clones that every gate certifies.
- **Recommendation**: (1) Report `min_catalog_distance` in section 4.2's table beside the pass counts, it is already computed and committed, so this costs nothing. (2) Make the authoring-leg decision multi-objective: strict pass **and** a minimum catalog distance well above `TAU_CELL` (the hand-authored p05 is 0.155; nothing below that should be promoted). (3) Implement the pre-registered control that was specified and not built: the plan requires *"between-leg `structural_distance` always splits out the self-declared topology component"*, and `compare_skeleton_authors.py:358-362` concedes the split "is carried in the note field here because the metric exposes only the combined value", but the emitted note is `"vs 5 in-cell peers"`, which carries no split at all. 20% of the score rides on a field the authoring leg chooses for itself, so the correlation above could be partly a topology-declaration effect; splitting it out is the way to tell.
- **How to check I'm right**: the per-leg table is reproducible from the records with the script in Appendix A; `head -14 runs/e1r3-tools-2026-08-21/summary.md` carries the same column. `python3 -m json.tool docs/planning/ws5_floor_baseline.json` for `tau_cell` 0.05 and `same_cell_structural.p05` 0.154657. `grep -n "catalog_distance_note" runs/e1r3-tools-2026-08-21/records/*.json | head`.

---

## B3-5: The brief reinstates a supplier ranking that a pre-registered rule formally retracted
- **Severity**: critical
- **Category**: pre-registration
- **Locus**: brief:183-185 "DeepSeek V4 Pro emerged as the best judged prose at roughly a fifth the cost of the premium Western legs"; `cyo-measurement-workplan-2026-08-12.md:231-243` (W5 pre-commitment) and `:1226-1249` (W5 closes)
- **Problem**: W5's rule was pre-registered on 2026-08-12: *"if the intervals overlap across the whole supplier slate, Part IV's ranking is retracted rather than caveated. At single-digit n per cell that is the likely outcome, and agreeing to it in advance is the point of writing it here."* On 2026-08-14 it fired: zero of one comparable pair separated (`xai-grok-4.6` +0.57 [+0.07,+1.08]; `google-gemini-3.1-pro` -0.48 [-1.33,+0.46]; `anthropic-sonnet-5` excluded at n=1), and the workplan records *"Part IV's ranking is retracted rather than caveated."* Eight days later the brief publishes a supplier ranking again, from the same instrument at the same n-per-cell regime, with no new bootstrap intervals, no pair-separation count, and no mention of the retraction. Note also that the sourcing plan itself is more careful than the brief here: it treats V4 Pro's prose quality as an open assumption, writing *"if v4 Pro is retained for prose quality despite its measured 38.9-52.9% delivery, the repair-loop policy per fill is pre-registered and fill-rate is carried as a covariate on every judged endpoint"*, and it **suspends** the blind quality panel and its +0.5z margin as unfunded.
- **Why it matters for the goal**: The fill-model choice is the most-repeated cost in the product. Reinstating a retracted ranking converts a formally unsupported claim into an architectural default, and it undercuts every other pre-registration in the programme by demonstrating that a pre-committed retraction can be reversed by writing a new document.
- **Recommendation**: Delete the ranking claim or restore it with a named non-overlapping interval. State in the brief that the blind quality panel is currently unfunded and suspended per the plan's section 10, so the reader knows no judged quality margin is live.
- **How to check I'm right**: `sed -n '1226,1250p' docs/planning/cyo-measurement-workplan-2026-08-12.md`; `grep -n "SUSPENDED unfunded" docs/planning/diversity-test-register.md`; `grep -rn "retract" docs/planning/cyo-generation-research-brief-2026-08-22.md` → nothing.

---

## B3-6: The model-judged class is a measured-saturated instrument whose scoring pool is unrecoverable
- **Severity**: critical
- **Category**: instrument validity
- **Locus**: brief:20 "model-judged (blind LLM raters, the weak class)"; brief:183-185; `cyo-measurement-workplan-2026-08-12.md:1200-1224`; `AL-379`, `AL-362`
- **Problem**: (a) **Saturation, measured 2026-08-14.** The `dialogue` criterion has SD **0.00** across 9 book-cells (flagged SATURATED); the other six span SD 0.38-0.62 on a 1-5 scale. W7 independently flags the same criterion, so its weakness is attested twice by different methods on different corpora. A panel that moves by under 0.65 SD cannot separate legs whose true quality differs by less. (b) **The pool is gone.** `AL-379`: `out/vendor-comparison/` held the 32-book run and the 84-verdict judge pool; "it exists on no checkout", and its loss already forced W2's published 18.9% figure to stand unverifiable. (c) **The panel was silently broken for an unknown window** (`AL-362`: a `Completion` object handed to a regex, every scoring swallowed by a broad handler, emitting an empty scorecard that read as flaky endpoints); nothing establishes which judged results predate the fix. The panel's *design* is sound, blind, cross-lab, z-scored within judge, `self_family` flagged and droppable at `judge_books.py:498`, so this is an execution-record problem, not a design problem.
- **Why it matters for the goal**: The concrete risk is that V4 Pro's win is judge preference. Its measured profile, 0% reasoning tokens, cheapest per call, and (per `AL-490`) delivering 38.9-52.9% of commissioned words, is precisely what a saturated rubric scoring terse, clean, on-band prose rewards and a child would experience as thin. No human and no child has read any book in this programme; every evidence README says so in its own provenance block, and W12/W13 are blocked on ADR-018 consent scoping. The whole quality stack is proxies with no anchor at the end.
- **Recommendation**: (1) Name the fill model as cost-and-delivery-selected, quality unranked, until a human-anchored measurement exists. (2) Re-derive any judged comparison on a committed pool via `scripts/_paid_output.py` and publish per-judge, self-family-dropped tables plus W5 intervals. (3) Retire or rewrite the `dialogue` criterion. (4) Cross-check any judged winner against the deterministic craft measures that do discriminate, `AL-330`'s 25-fold dialogue spread between legs is exactly the signal the judge cannot see.
- **How to check I'm right**: `sed -n '1200,1224p' docs/planning/cyo-measurement-workplan-2026-08-12.md`; `grep -n "AL-379" docs/planning/authoring-lessons-log.md`; `git ls-files out/` → empty.

---

## B3-7: n=3 per cell supports one leg-level conclusion; "frontier Anthropic tiers converge fastest and most reliably" is not it
- **Severity**: critical
- **Category**: power/statistics
- **Locus**: brief:198-208
- **Problem**: The design is paired (premise fixed per cell x replicate across all legs, verified from the records), so both paired and unpaired tests apply; both give the same answer. Exact 95% intervals: 3/3 → [0.292, 1.000]; 2/3 → [0.094, 0.992]; 1/3 → [0.008, 0.906]; 0/3 → [0.000, 0.708]. The 3/3 and 0/3 intervals overlap over [0.292, 0.708]; the most extreme single-cell contrast possible has Fisher p = **0.10**, so **no single-cell comparison in this table can reach p<0.05 at any effect size**. Pooled over both cells (n=6):

  | contrast | Fisher p | exact McNemar p (paired) | verdict |
  |---|---|---|---|
  | 6/6 (fable, opus) vs 0/6 (v4-pro) | **0.0022** | **0.031** | separated |
  | 5/6 (kimi) vs 0/6 (v4-pro) | 0.0152 | 0.063 | marginal |
  | 4/6 (sonnet) vs 0/6 | 0.0606 | 0.125 | not separated |
  | 3/6 (haiku, flash) vs 0/6 | 0.1818 | 0.250 | not separated |
  | 6/6 vs 5/6 (Anthropic frontier vs Kimi K3) | **1.0000** | 1.000 | indistinguishable |
  | 6/6 vs 4/6 (fable vs sonnet) | 0.4545 | 0.500 | indistinguishable |
  | 6/6 vs 3/6 (fable vs haiku) | 0.1818 | 0.250 | indistinguishable |
  | 12/21 (cell A) vs 15/21 (cell D) | 0.5199 | - | "the hard band is not the hard part" is not a finding |

  So: **"DeepSeek V4 Pro is the worst structure author (0/6)"** is safe only against the top legs. It is statistically indistinguishable from Sonnet, Haiku and V4 Flash. The defensible statement is "V4 Pro failed all six attempts and is separated from the best legs", not "worst". **"Frontier Anthropic tiers converge fastest and most reliably"** does not survive at all: an owner-run open-weight Modal endpoint (Kimi K3, 5/6) is indistinguishable from both frontier tiers at p=1.00, and the family is internally inconsistent (sonnet 1/3 at cell A, haiku 1/3 at cell D), which is what four legs of three coin flips look like. On speed, the checker-run counts are three observations per cell reported as bare ranges with no dispersion statistic and no test; for two independent n=3 samples the minimum attainable two-sided Mann-Whitney p is 2/C(6,3) = **0.10**, so no speed comparison in this table can be significant at any separation.
- **Why it matters for the goal**: F4 commits the authoring plan to a per-stage vendor split with real operational and contractual complexity, on a table that supports exactly one model-level conclusion. It also forecloses the cheaper reading the same data supports: a self-hosted open-weight endpoint may be as good a structure author as a frontier tier, at an endpoint the owner controls.
- **Recommendation**: Raise n to at least 10 per leg per cell before any ranking language (10/10 vs 5/10 reaches p=0.033; three attempts never can). Report every cell as x/n with an exact interval. Rewrite 4.2 to report only: tool-assisted >> blind; V4 Pro 0/6 with two named failure modes; all other legs indistinguishable at this n; and Kimi K3 at parity with the frontier tiers.
- **How to check I'm right**: Appendix A. Table arithmetic is internally sound first: cell A sums 3+3+1+2+2+1+0 = 12 ✓, cell D 3+3+3+1+3+2+0 = 15 ✓, and both match `summary.md`'s per-leg strict-pass column.

---

## B3-8: The checker-run endpoint is censored at the cap for 18 of 42 tool-assisted shells, and the brief's ranges handle the censoring inconsistently
- **Severity**: high
- **Category**: power/statistics
- **Locus**: `runs/e1r3-tools-2026-08-21/tools-meta.json`; brief:199-205
- **Problem**: Every tool-assisted failure sits at exactly the 10-invocation cap. Per leg, invocations at cap: haiku 4/6, v4-pro 4/5 recorded, sonnet 3/6, flash 2/5 recorded, kimi 1/6, fable 0/6, opus 0/6. So "checker runs to pass" is right-censored in the same way the blind arm's repair rounds were, the degeneracy the brief discloses for the blind arm applies, undisclosed, to the tool-assisted convergence-speed claim. Worse, the brief's ranges treat censored observations inconsistently: for Kimi at cell A the censored failure (10) is **excluded** and the range is reported as "7-8" (the two passes); for V4 Flash at cell D the censored failure (10) is **included** and the range is reported as "5-10". Same censoring, opposite handling, and the inconsistency runs in the direction that flatters the leg the brief recommends against reporting well. Two shells (`D__r1__deepseek-v4-flash`, `D__r1__deepseek-v4-pro`) have no `checker_runs` record at all, so the denominators for those ranges are 5, not 6.
- **Why it matters for the goal**: "Frontier Anthropic tiers converge fastest" is the claim that would justify paying a premium tier for structure authoring. It is built on a censored, inconsistently summarised endpoint with three observations per cell and no test.
- **Recommendation**: Report checker invocations as a survival quantity (Kaplan-Meier median with censored points marked, or simply "k of n reached the cap") rather than as a range. Apply one censoring convention across all legs and state it. Fill the two missing `tools-meta` entries or mark those grid points unscored.
- **How to check I'm right**: `python3 -m json.tool runs/e1r3-tools-2026-08-21/tools-meta.json` and count entries equal to 10; cross-reference against `strict_pass` in the matching record. Compare Kimi cell A (10 FAIL, 8 PASS, 7 PASS → brief "7-8") with Flash cell D (missing, 10 FAIL, 5 PASS → brief "5-10").

---

## B3-9: The registered design was changed substantially before the run and the brief reports none of the changes
- **Severity**: high
- **Category**: pre-registration
- **Locus**: register `S-1` registered method vs brief:198-206; test plan section 10
- **Problem**: Registered: 5 legs (`deepseek-v4-pro`, `deepseek-v4-flash`, `anthropic-sonnet-5`, `openai-gpt-5.6-sol`, `google-gemini-3.1-pro`) x 4 cells (3 cheap-band, 1 hard-band) x 4 replicates = 80 shells. Run: 7 legs (GPT-5.6-sol and Gemini 3.1 Pro dropped; four Anthropic subagent tiers and a Moonshot Modal endpoint added) x 2 cells x 3 replicates = 42 tool-assisted shells. The register and plan **declare all of it properly**, with the data-contact statement ("4 completed shells' exploratory records were seen, no primary result existed") and the reason (owner budget cap after an HTTP 402 halt at 4 of 80 shells), that part is exemplary. The defect is entirely on the brief's side: section 4.2 presents the seven-leg two-cell table with no indication that the slate, cell count and replicate count all changed, that two premium legs were dropped for cost, that the added legs are tier-labeled rather than backend-pinned (so, per the register, they support "tier-level conclusions, not checkpoint-level ones"), or that the only leg with a proven strict pass in the smokes (Gemini 3.1 Pro) was dropped as optional. A reader of the brief alone would take the table for the registered experiment.
- **Why it matters for the goal**: The dropped legs are the two the original design included to answer "does a premium Western tier author better structure". The brief's F7 claim that "premium Western legs were 90% of one comparison's bill for no additional passes" is then made about legs that were removed before the deciding run, their zero passes come from the *halted* 80-shell run, where 76 of 80 shells died on HTTP 402 and `summary.md` shows 16 errors of 16 for both Sonnet 5 and Gemini 3.1 Pro. They authored essentially nothing; "no additional passes" describes a payment failure, not a capability.
- **Recommendation**: Add a design-provenance paragraph to section 4.2 naming the registered design, the revision, its reason, its data-contact statement, and the tier-labeled limitation. Delete or correct the "90% of the bill for no additional passes" sentence: `runs/e1-2026-08-21/summary.md` shows those legs erred on 16 of 16 shells each.
- **How to check I'm right**: `head -12 .worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/runs/e1-2026-08-21/summary.md` → `anthropic-sonnet-5 16 shells 16 errors 0 pass`, `google-gemini-3.1-pro 16 16 0`. Register `S-1` registered-method cell vs the brief's table.

---

## B3-10: The shared-4-gram rate is not scale-invariant, and the "24x budget" headline is largely arithmetic
- **Severity**: high
- **Category**: instrument validity
- **Locus**: brief:189; `scripts/check_sibling_fills.py:16-22`; register D-6/D-7 comparison table
- **Problem**: The metric is a **type count over a token denominator** ("every gram appearing in two or more sibling fills ... per 1000 mean leaf words"), so dividing by words does not remove length. The programme's own data proves it: under the same condition (one shared contract), the 26-node D-6 `verbatim` arm scores 17.2 and the 101-node D-2 pair scores 50.1, a 2.91x rate increase for a 3.88x node increase, i.e. rate ∝ N^0.788. The 96.3 headline was measured on `the-tin-whistle-map` at **193 nodes and 8.4k-12.8k words per book** (verified from the committed books). Extrapolating: 17.2 x (193/26)^0.788 = **83.4**, so 96.3 is ~1.15x what a shared-*contract* pair scores at that scale. `AL-498`'s "3.9x the worst previously measured arm" compares a 193-node pair against arms measured at 26 nodes. Both the 4.0 budget and the 3.3 floor were established on ~2,600-3,000-word books, the vendor-comparison README chose its skeletons to sit "close to the ~2,801-word books the 3.3 figure was computed over" for exactly this reason, and are being applied to books up to ~118,000 words.
- **Why it matters for the goal**: `UW-C315` proposes wiring `check_sibling_fills.py` into the fill pipeline as a blocking gate at 4.0. At production scale essentially every pair breaches it for arithmetic reasons, so the gate would either block the catalog or be relaxed until it blocks nothing. And the alarm is driving an architecture proposal (per-family structural mutation, or a cap on skeleton reuse) that would be among the most expensive things the programme could build.
- **Recommendation**: Before any gate wiring, run the same-scale floor control: two fills of two different 193-node skeletons from unrelated briefs. Then either express the budget as a function of length fitted across four sizes, or switch the numerator to a scale-stable statistic (shared-gram token share, or containment/Jaccard over 4-gram sets). Restate `AL-498` and brief:189 with the scale beside every number and withdraw "24x budget".
- **How to check I'm right**: node counts via `python3 -c "import json;print(len(json.load(open('docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/shared-skeleton-pair/books/deepseek-v4-pro__00.json'))['nodes']))"` → 193, versus 26 for the D-6/D-7 arms; register's one-scale table for 17.2 and 50.1; then ln(50.1/17.2)/ln(101/26) = 0.788.

---

## B3-11: F5's deterministic evidence is one 26-node pair, and the brief claims it for a 149-node median catalog
- **Severity**: high
- **Category**: generalization
- **Locus**: brief:75-78
- **Problem**: D-7b is **one pair of 26-node, ~3,000-word books**; no replicate, no interval, one premise. The production 10-13 band is "11 skeletons over 1,610 nodes with a median of 149" (Q-1). Given the N^0.788 scale exponent above, the 2.3 projects to 2.3 x (149/26)^0.788 ≈ **9.4** at production scale, over twice budget. Two register-stated limits the brief drops: the passing stratum is **not wordless**, it carries 473 words of binding-process free text, "more than the 422 words the experiment deleted", and *"only an arm that deletes the 473 while keeping the 422 settles which variable is operative, and that arm is deprioritised rather than cancelled"*. That arm is D-7c; `AL-510` and `UW-C317` record that its fills were never committed (PR #715 merged the rigs while the books stayed on a deleted branch), which is also what forced S-0 to re-base its control and is implicated in the S-0 failure. Combined with B3-1, F5 currently has: one small-scale deterministic pair, an unrun mechanism arm, and four recognition verdicts saying the pair reads as one book.
- **Why it matters for the goal**: F5 determines what is authored once versus per book. It is the highest-cost decision in the programme resting on the thinnest evidence.
- **Recommendation**: Replicate D-7b at production scale with at least three independent pairs so an interval exists, pre-registering the falsifier as "the pair rate exceeds the same-scale measured floor"; run the same-scale floor control alongside it. Re-run D-7c and commit its fills. Until both land, restate F5 as validated at ~3,000 words and unvalidated at catalog scale.
- **How to check I'm right**: register D-7b row including both correction boxes; `ls docs/planning/evidence/d7c-binding-notes/` → rig only, no fills; `grep "| AL-510 |" docs/planning/authoring-lessons-log.md`.

---

## B3-12: Two production thresholds are calibrated on the data they judge, and one has an unstated 6% false-block bound
- **Severity**: high
- **Category**: instrument validity
- **Locus**: brief:159-161; `scripts/check_sibling_fills.py:18-22`; `AL-490`, `AL-267`
- **Problem**: **0.6 fill rate**: `AL-490` records the derivation, nine passing books at 0.715-0.990, three DeepSeek books at 0.389-0.529, "so 0.6 splits the gap". A threshold chosen to separate two known label sets with no held-out set has no measured error rate; the brief states the circularity in the same sentence that presents it as a gate ("calibrated so the `UW-C307` under-delivering books fail"). The lessons log supplies the number the brief omits: across all 48 committed (skeleton, filled) pairs the tightest known-good pair is **0.635**, a margin of 0.035. With 0 of 48 known-good books below 0.6, the exact 95% upper bound on the false-block rate is 1 - 0.05^(1/48) = **6.05%**. **4.0 gram budget**: `AL-267` states it "was never validated against what the generator can actually achieve"; its calibration set is four arms from one pilot, three to reject and one (2.8) to accept, with the threshold placed 1.2 units above the single accepted point.
- **Why it matters for the goal**: These are F2's two delivery gates. A threshold fitted to its own training examples will pass the next hollow book that fails differently and block good books at an unmeasured rate; ~1 in 16 false blocks is a direct unit-cost tax on a paid pipeline.
- **Recommendation**: Split the 48 pairs into calibration and validation halves, refit, and publish validation-set false-block and false-pass rates beside each constant. Better, make the fill-rate expectation per band and length, a 632-node book and a 26-node book should not share one number, using the `commissioned_words_by_node` data already in hand.
- **How to check I'm right**: `grep -n "AL-490" docs/planning/authoring-lessons-log.md`; `grep -n "AL-267" ditto`; 1 - 0.05**(1/48) = 0.0605.

---

## B3-13: `TAU_CELL` = 0.05 is owner-chosen, sits three-fold below the 5th percentile of hand-authored pairs, and the brief calls it calibrated twice
- **Severity**: high
- **Category**: instrument validity
- **Locus**: brief:134-135 and brief:230; `docs/planning/ws5_floor_baseline.json`; `src/cyo_adventure/diversity/incell.py:59-80`
- **Problem**: The cited file says the opposite of the brief. `derivation.tau_cell`: *"**owner-chosen fixed** anti-duplication floor"*. The number that *was* calibrated, `tau_struct` = 0.298321 (p25 of 145 hand-authored same-cell pairs), is marked **"DOCUMENTATION ONLY ... No longer gates mutants"**. The same file records the hand-authored same-cell distribution as min 0.000469, p05 **0.154657**, p25 0.298321, median 0.379906, so 0.05 sits three-fold below the bottom fifth of genuinely distinct pairs and can only catch near-identical trees. The mutation pilot confirms the metric's blindness independently (M1 and M2 produce `structural_distance` exactly **0.0000** on every pair tried while changing `structure_fingerprint`), and `incell.py` already carries a debt-register allowlist for a pair identical on every structural feature but one. The sourcing plan describes the floor accurately ("TAU_CELL 0.05 fixed per the ADR-020 recalibration amendment"); only the brief calls it calibrated. B3-4 shows the practical consequence: the recommended leg's closest shell is 0.0507.
- **Why it matters for the goal**: F2 lists anti-clone among the deterministic checks that run before anything else. A nominal constant three-fold below the acceptable distribution lets the catalog accumulate re-skinned twins that every gate certifies, the exact defect the diversity programme exists to prevent.
- **Recommendation**: Say "owner-chosen" wherever 0.05 appears, or calibrate it: label a sample of the 145 same-cell pairs for "same book re-skinned" and set the floor at the separating operating point, publishing the false-accept rate at 0.05. Implement the pre-registered topology-component split numerically rather than in a note field (B3-4).
- **How to check I'm right**: `python3 -m json.tool docs/planning/ws5_floor_baseline.json`; `sed -n '59,82p' src/cyo_adventure/diversity/incell.py`; `sed -n '355,365p' scripts/compare_skeleton_authors.py` for the note-field concession.

---

## B3-14: The "3.3 generator idiom floor" is n=3 with a 95% CI of about [-0.7, 7.2]
- **Severity**: high
- **Category**: power/statistics
- **Locus**: brief:76-77; register D-6 addendum
- **Problem**: The floor is three measurements: 2.9, 5.0, 1.9. Mean 3.267, sample SD **1.582**, SEM 0.913, t(2)=4.303 → 95% CI **[-0.66, 7.19]**, which contains both the 4.0 budget and D-7b's 2.3. So "the budget is above the floor, so it is reachable" is not established, and "D-7b is below the floor, so sharing this plan is indistinguishable from sharing nothing" compares an n=1 point to an n=3 point whose SEM alone is 0.91 (gap 1.0 ≈ 1.1 SEM, one-sample t p ≈ 0.36). The register's own care shows the fragility: the whole at-the-floor/below-the-floor distinction turned on a 0.9-unit re-derivation inside a 1.58-unit SD. `AL-267` also records that the floor "is a property of the model rather than of any architecture" and must be re-measured when the generation model changes, the brief cites 3.3 while recommending a different fill model than the one it was measured on.
- **Why it matters for the goal**: The floor is the reference point for F5, for the 4.0 budget, and for every verdict in 4.3. A reference with an interval three times its own value cannot adjudicate the 1.7-unit differences F5 turns on.
- **Recommendation**: Re-measure with n ≥ 15 pairs stratified by length, on the model actually used for fills, and publish mean ± CI. Restate every floor comparison as a difference with an interval.
- **How to check I'm right**: register D-6 addendum table; `python3 -c "import statistics as s;v=[2.9,5.0,1.9];m=s.mean(v);sd=s.stdev(v);print(m,sd,m-4.303*sd/3**.5,m+4.303*sd/3**.5)"`.

---

## B3-15: F3's headline confounds authoring regime with a 6-versus-10 budget difference, and the blind arm's denominator is not stated
- **Severity**: high
- **Category**: confound
- **Locus**: brief:58-63, brief:194-196; `runs/e1r3-2026-08-21/run.json` (`max_repair_rounds: 6`); register `S-1` (tool-assisted "up to 10 times")
- **Problem**: This is the one statistically solid result in the brief (2/21 vs 12/21, Fisher p = **0.0013**; against pooled 27/42, p < 0.0001), and its design still confounds three things. (1) **Budget.** Blind gets 6 rounds, confirmed in `run.json`; tool-assisted gets 10 invocations. The arms differ in both the treatment and the attempt budget by a factor of 1.67, and several tool-assisted passes consumed 7-10 invocations, more than the blind arm ever had. A blind arm at ten rounds is the missing control and costs almost nothing for the zero-cost legs. (2) **Denominator.** "2 passes in 21 attempts across seven legs" versus tool-assisted "12 of 21" per cell: the blind figure is one cell (7 legs x 3), matching `e1r3`'s three replicates on cell A, but the brief never says so, and its "21" reads as the same denominator by coincidence. (3) **Failure classification.** `AL-513` records that blind failures are censored at the cap and that "each round fixes the named findings and surfaces new ones"; nothing separates structural-invalid failures from unparseable-output failures in either arm, and brief:204's "call budget lost to unparseable output" shows the second class is material.
- **Why it matters for the goal**: F3 is called the largest measured lever and the pipeline is already built around it. It is probably true, and `AL-513`'s mechanistic account is convincing. But its stated magnitude is inflated by whatever share the extra four rounds contribute, and nobody has estimated that share. If half the effect is budget, "give the author more attempts" is a cheaper change than "put the checker in the loop".
- **Recommendation**: Run blind at ten rounds on the four zero-cost legs, same premises, and report the three-way comparison. State the blind denominator explicitly. Classify every failure as structural-invalid versus unparseable and report both classes in both arms.
- **How to check I'm right**: `python3 -m json.tool runs/e1r3-2026-08-21/run.json` → `max_repair_rounds: 6`, `cells: ["A"]`, `replicates: 3`. Register `S-1` for the ten-invocation tool-assisted cap.

---

## B3-16: The recognition instrument is a single-model, in-family panel, and the sourcing plan's judged endpoints inherit that
- **Severity**: high
- **Category**: instrument validity
- **Locus**: `evidence/recognition-protocol-pilot/results.md` provenance block: "All six raters are model raters: independent, blind subagent sessions of the serving frontier model (session model id `claude-fable-5`)"; test plan section 4 Tier 3
- **Problem**: The instrument the whole sourcing programme's perceptual half depends on was validated by six sessions of **one model**, which is the same family as four of the seven S-1 legs and the same model as the driving session. The plan's own blinding control specifies "cross-lab with self-family flagging" for blind story judging, and Tier 3's recognition entry does not carry that requirement; nothing in the run reports a self-family flag. Separately, the plan's descoped E3 makes "two v4-flash judges" the sole judged primary for premise fit, which is a two-rater single-model panel from the same lab whose model is under test elsewhere in the programme. The S-0 result is exemplary in every other respect, pre-registered, tightened from 2-of-3 to 2-of-2 on re-basing, counterbalanced, verdicts machine-validated before recording, failure reported as failure with the repair path, so this is the one gap in an otherwise model piece of instrument work.
- **Why it matters for the goal**: A single-model rater panel cannot distinguish "these two books are the same adventure" from "this model finds these two books similar". Given B3-1 leans on these verdicts, and given the programme's own D-3 history of an instrument that confidently inverted against readers at kappa 0.96, the panel's homogeneity is load-bearing.
- **Recommendation**: Re-validate with raters from at least two labs and record self-family per verdict, exactly as `judge_books.py` already does for prose. Adopt the three repairs `results.md` names (symmetric position-bounded firing rule, a true cross-band control, fresh pairs) as a single re-registration. Note the repair is cheap and the results file already specifies it.
- **How to check I'm right**: `head -12 docs/planning/evidence/recognition-protocol-pilot/results.md`; `grep -n "self-family" docs/planning/skeleton-sourcing-test-plan-2026-08-21.md`.

---

## B3-17: The fill-rate headline is n=3 books selected on having passed, across three different cells
- **Severity**: high
- **Category**: power/statistics
- **Locus**: brief:44-46 and brief:187; `deepseek-v4-pro-live-fill-plan-2026-08-20.md:318-332`
- **Problem**: The run was five fills; three passed. Book 0 errored (transient empty 200) and book 4 errored (`content_filter`). The 38.9-52.9% range is conditioned on passing, so "every book passed the deterministic gate" is true only of the books that produced a gate verdict. The three books are `the-last-cartage` (16+ gamebook), `the-quarry-signal` (13-16 gamebook), `the-tin-whistle-map` (8-11 prose), three bands, two styles, one book per cell, one model, one endpoint, one date. Their in-band reading-level fractions are 15.5%, 5.6% and 73.1%, a 13-fold spread, which is itself evidence they are not exchangeable draws. `AL-490`'s stranger claim, per-node correlation between commissioned and delivered of 0.527, -0.027 and **-0.405**, rests on one book for the negative case.
- **Why it matters for the goal**: F2's mechanism (PL-19 is a ceiling; nothing floors delivery) is correct and well-earned. The magnitude is now a production constant (the 0.6 threshold), derived from three non-exchangeable books.
- **Recommendation**: Re-measure delivery as at least two models x two bands x three books per cell, with an interval per cell. Report "3 of 5 fills produced a gate verdict" in the brief. Check whether the anti-correlation replicates.
- **How to check I'm right**: `sed -n '318,332p' docs/planning/deepseek-v4-pro-live-fill-plan-2026-08-20.md`.

---

## B3-18: The surviving instruments' known-answer tests are individually underpowered; D-4's best case is a permutation p of 0.167
- **Severity**: medium
- **Category**: instrument validity
- **Locus**: brief:227-230; register D-4 result
- **Problem**: D-4's validation is that its tier-1 score reproduces the raters' Q6 ordering on **three** pairs. Under a null of random ordering, recovering the exact order of 3 items has p = 1/3! = **0.167**; no three-pair ordering test can reach p<0.05 (four pairs would give 0.042). The register itself flags that one of the three may be an artifact: *"The control pair's 0.167 is a single link ... the `AL-185` collision ... The 4-against-3 gap may therefore be driven by an uncontrolled device collision rather than by the treatment."* Removing it leaves two orderings, p = 0.5. Could it invert like DecisionSignature? Less likely, tier 1 uses no taxonomy and so could not have been fitted to the raters, and the register makes that argument correctly, but "could not have been fitted" is an argument against circularity, not evidence of validity. The register's own generalisation is the prior the brief's "Works" list does not carry: *"the lexical version of a question in this programme has never yet been good enough to gate"*, two for two.
- **Why it matters for the goal**: Section 4.4 is the warrant for trusting anything. The programme is far better at killing instruments (kappa 0.96 refutations) than at establishing them (p ≈ 0.17 validations), and the brief presents the survivors as established. D-4 is also the instrument B3-1 recommends using to adjudicate F5, so its power matters immediately.
- **Recommendation**: Add rated pairs. Four gets D-4 to p=0.042; six to 0.0014. This is the cheapest instrument work available. Re-run D-4 on the pair exposed to the `AL-185` collision with the collision removed, and state the permutation p beside every "reproduces reader orderings" claim.
- **How to check I'm right**: register D-4 result section, three-pair table and the `AL-185` caveat; 1/3! = 0.1667, 1/4! = 0.0417.

---

## B3-19: Four of the eight principles are unfalsifiable as written, including two that drive spend
- **Severity**: medium
- **Category**: falsifiability
- **Locus**: brief:52-96

  | | Refuting observation | Can the programme see it? |
  |---|---|---|
  | **F1** split structure/prose | A joint (unsplit) authoring regime matching split quality at equal or lower cost | **No.** No unsplit arm has ever been run; Q-3/Q-3b/Q-3d test skeleton-free *generation*, not joint authoring under the same gate. F1 is assumed by every rig. |
  | **F2** gates are floors | A gate-passing book a human judges good, or a hollow book the delivery measures miss | **Partly.** Delivery measures exist, but `AL-490`-style hollowness was found by hand, and no human has judged any book, so the half that matters is unfalsifiable. |
  | **F3** checker in the loop | Blind authoring at equal budget matching tool-assisted | **No**, that arm was never run (B3-15). As specified (6 rounds vs 10 invocations) the comparison cannot come out the other way. |
  | **F4** per-stage model selection | One model best at both stages, or the stage ranking not replicating | **In principle; not at n=3** (B3-7): a leg would have to move 0/6 → 6/6 to register. |
  | **F5** share structure, not decisions | A shared decisional layer at the floor, or a bare-names plan exceeding budget at scale, or the passing pair reading as one book | **Yes, and the third has now been observed and not reported** (B3-1). |
  | **F6** trust no instrument | An instrument passing its known-answer test and still misleading | **Yes, and this is the programme's strongest habit**, three instruments killed by it, S-0 the most recent. Applied asymmetrically: survivors are not re-tested (B3-18). |
  | **F7** engineer the cost | A prompt/model change moving cost more than the named levers | **No.** The deciding arm records no tokens or cost for any leg (B3-3), and "zero marginal provider cost as subagents" is an accounting boundary, not an economic fact, so a cost ranking built on it cannot be refuted by measurement. |
  | **F8** human approves every book | Nothing, it is a policy commitment (ADR-005) | **N/A**, correctly, but the brief lists it among principles "earned by an analysis in section 4" and no analysis bears on it. Its live empirical sub-question is `S-5`, whose safety floor (100% catch on six structural failure classes, ≥90% on the seeded defect class) is registered and unrun. |

- **Why it matters for the goal**: F1, F3 and F7 set the shape and budget of the pipeline and none has a live falsifier. The register's own opening rule is *"A test with no falsifier is a demonstration, and a demonstration cannot change anyone's mind"*, the brief's principles do not meet the standard the register sets for its own rows, even though the S rows themselves do.
- **Recommendation**: Write the falsifying observation into the brief for F1, F3 and F7 and name the experiment that could produce it, or demote them to working assumptions. F1's is overdue and cheap: one arm where a tool-assisted author writes structure *and* prose in a single pass against the same gate. F7's requires shadow-pricing subagent tokens at published rates.
- **How to check I'm right**: register "How to read this" section for the falsifier rule; then search the brief for a falsifier attached to any of F1-F8, there is none.

---

## B3-20: Capital facts in sections 1 and 4.3 are stale by 35-60% against the catalog on disk
- **Severity**: medium
- **Category**: generalization
- **Locus**: brief:31 "the catalog spans 61 graphs and 11,458 nodes"; brief 4.3 "a child exhausts a cell by roughly the fourth request at 3-4 skeletons per cell (Q-1)"
- **Problem**: Measured on this checkout: **86** skeletons carrying nodes, **15,507** nodes, **18** cells; **81** production-eligible across **14** production cells, mean **5.79** per cell, min 4, max 10. The node count is 35% low and per-cell depth is 61% low. Q-1's direction survives (a cell is still exhaustible) but "roughly the fourth request" is now the fifth to eleventh, which changes the reuse-versus-purchase arithmetic Q-1 exists to inform. `AL-481` already generalised this exact failure, *"A number measured against a growing artifact set has a shelf life, and a comment has no way to say so"*, and proposed dating every catalog-derived number.
- **Why it matters for the goal**: Q-1 is cited as a capital fact bounding full-skeleton reuse and feeds the purchasing decision.
- **Recommendation**: Date every catalog-derived number in the brief and regenerate the census as part of the brief's build; `UW-C274`'s census script is the intended mechanism.
- **How to check I'm right**: the census one-liner in Appendix A.

---

## B3-21: Results from n=1 per condition are promoted to programme principles without their stated caveats
- **Severity**: medium
- **Category**: power/statistics
- **Locus**: brief:78-83, brief:86-88
- **Problem**: **M-4 withholding (127-fold)**: one shown-plus-instructed attempt (126.7) versus one withheld attempt (1.0); no replicate, no interval, and the register's dropped caveat, *"the 3.3 floor was measured on story prose, and these are specifications, a different text type, so 1.0 should not be read as 'below the floor'"*, plus the observation that withholding did nothing to premise convergence (the withheld author independently chose a clock tower). **Q-3c invariance**: two generations per tier at two tiers plus six from an earlier single-model run; "invariant" is a claim about equality that n=2 per tier cannot support, and the README's own "does not establish" section says the tiers share one family. **Mutation refutation**: the deterministic half is solid (M1/M2 at `structural_distance` 0.0000 across five swap pairs; all mutants retaining 100% of parent FILL beats) and would replicate; the perceptual half is explicitly *"n=1 parent, one rated pair, one rater pass ... not blind and not run in a separate agent ... Treat the landing node and the score as author-scored"*, with a documented authoring confound (first draft 302 shared grams/1000, brought to 70.4 by two deliberate de-convergence passes). S-0 has since marked that perceptual claim unconfirmed; the brief's 4.3 still lists the refutation flat, while 4.4 marks it unconfirmed, an internal contradiction.
- **Why it matters for the goal**: These feed directly into pipeline behaviour (withhold sibling material, curate premises, do not use per-request mutation). Two are probably right, but n=1 conclusions carried into a summary lose the information about which would fall over first, and the mutation refutation retires an entire built subsystem on one non-blind author-scored read.
- **Recommendation**: Annotate each claim with its replicate count. Replicate M-4's withholding contrast twice more (two contract-authoring runs plus a deterministic score). Reconcile 4.3 and 4.4 on the mutation claim: keep the deterministic verdict, mark the perceptual one unconfirmed in both places.
- **How to check I'm right**: register M-4 controlled-result table; `docs/planning/evidence/q3c-premise-mode/README.md`; `docs/planning/evidence/mutation-per-request-pilot/README.md` Limitations.

---

## B3-22: The cheapest decisive experiments are unrun, and the most expensive decision rests on the weakest class
- **Severity**: medium
- **Category**: missing experiment
- **Locus**: whole brief; `cyo-measurement-workplan-2026-08-12.md:553-556`
- **Problem and recommendation**, ranked by information per unit cost.

  **Cheapest experiments that could most change direction** (all free or near-free, and all decisive):
  1. **Solution transfer on the D-7b pair** (B3-1). `check_solution_transfer.py` already exists, is deterministic, and adjudicates whether F5's passing arm converges at the decision layer. Minutes of compute; it can overturn the programme's central architectural claim.
  2. **Same-scale gram floor** (B3-10). One `compare_vendors.py` invocation at 193 nodes. Decides whether the 96.3 alarm, the `UW-C315` reuse-cap proposal, and the 4.0 gate are real or arithmetic.
  3. **D-7c** (B3-11). Rig committed, no rater needed; decides F5's mechanism.
  4. **Blind at ten rounds** on the four zero-cost legs (B3-15). Decides how much of F3 is budget.
  5. **Harness 2x2** (B3-3): one Anthropic tier driven exactly as the API legs were, one API leg driven with real tool-calling. Decides whether F4 is about models.
  6. **The differentiation-directive delta** (`UW-C315`): the spec is committed at `runs/.../shared-skeleton-pair-directed/differentiation.json` and blocked only on network egress. The pipeline ships the directive and nothing records what it buys.

  **Highest-cost decision on the weakest evidence**: the **fill-model choice**, per book, forever, resting on a ranking W5 retracted, a panel with one dead criterion and a lost pool, and a cost comparison that measures cost per call rather than cost per commissioned word delivered. Extend the vendor README's cost-per-delivered-book table to cost per commissioned word delivered; at 38.9-52.9% delivery, V4 Pro's $0.0398/call advantage may reverse.

  **Experiments the framework's claims require and that nobody has designed**: any human or child reading anything (W12/W13 blocked on ADR-018 consent scoping, every evidence README states "No human and no child has read any of it"); an F1 control (joint structure+prose authoring); a cross-family premise-convergence test, which Q-3c names as the open version of its own question; and a false-block-rate measurement for the 0.6 gate.

  The cheapest human anchor that does not need child consent: 10 books, two paid adult expert readers (a children's librarian and a primary teacher), forced-choice comparisons plus a three-item rubric. It is the only thing that would tell the programme whether its proxy chain points at quality at all, and it does not require ADR-018 to move.
- **How to check I'm right**: `grep -rn "No human and no child has read" docs/planning/evidence/`; `sed -n '553,556p' docs/planning/cyo-measurement-workplan-2026-08-12.md`.

---

## B3-23: Section 4.1 conflates three separate runs, and the evidence README omits the two decision-bearing ones
- **Severity**: low
- **Category**: confound
- **Locus**: brief:181-189; `docs/planning/vendor-comparison/vendors.json`; `evidence/skeleton-author-vendors/README.md`
- **Problem**: The "six legs across five labs" slate is `vendors.json`: Sonnet 4.6, Sonnet 5, GPT-5.6-sol, Grok 4.6, Kimi K3, Gemini 3.1 Pro. **DeepSeek V4 Pro is not in it.** V4 Pro appears in the billing probe (8 legs), in run-6 (a five-leg DeepSeek quantisation matrix whose cross-vendor figure "rests on one lab pair"), and in the separate 2026-08-20 live fill run. Three slates, three questions, collapsed into one sentence implying a single six-leg blind comparison produced a V4 Pro win. Independently, `evidence/skeleton-author-vendors/README.md` documents only `smoke`, `smoke2` and the halted `e1` run, it says nothing about `e1r3-2026-08-21` or `e1r3-tools-2026-08-21`, which are the two runs every section 4.2 conclusion comes from.
- **Why it matters for the goal**: A reader will believe one well-designed six-leg blind comparison stands behind the fill-model choice, and a reader of the S-1 evidence directory will not find the runs that produced the result. Compounded with B3-5 and B3-6, the apparent evidential weight substantially exceeds the reality.
- **Recommendation**: Split brief:181-189 into one sentence per run, naming the slate file and the question each answered. Add `e1r3` and `e1r3-tools` to the evidence README with their conditions, their declared deviations, and the note that the tool-assisted arm was not harness-driven.
- **How to check I'm right**: `grep -c deepseek docs/planning/vendor-comparison/vendors.json` → 0; `grep -c "e1r3" docs/planning/evidence/skeleton-author-vendors/README.md` → 0, against `ls .../runs/` showing five directories.

---

## Appendix A: arithmetic

```python
from math import comb
def bcdf(k,n,p): return sum(comb(n,i)*p**i*(1-p)**(n-i) for i in range(k+1))
def bis(f,lo,hi):
    for _ in range(300):
        m=(lo+hi)/2; lo,hi=(m,hi) if f(m)<0 else (lo,m)
    return (lo+hi)/2
def cp(x,n,a=.05):                       # Clopper-Pearson exact two-sided
    lo=0.0 if x==0 else bis(lambda p:(1-bcdf(x-1,n,p))-a/2,0,1)
    hi=1.0 if x==n else bis(lambda p:-(bcdf(x,n,p)-a/2),0,1)
    return round(lo,3),round(hi,3)
def fisher(a,b,c,d):                     # two-sided
    n=a+b+c+d
    def p(x):
        y,z,w=a+b-x,a+c-x,d-(x-a)
        return 0 if min(x,y,z,w)<0 else comb(a+b,x)*comb(c+d,z)/comb(n,a+c)
    o=p(a); return round(sum(p(x) for x in range(min(a+b,a+c)+1) if p(x)<=o+1e-12),4)
def mcnemar(disc, one_way):              # exact, two-sided
    return round(2*sum(comb(disc,k) for k in range(one_way,disc+1))/2**disc,4)
```

**Exact 95% intervals on pass probability**

| x/n | interval | x/n | interval |
|---|---|---|---|
| 0/3 | [0.000, 0.708] | 0/6 | [0.000, 0.459] |
| 1/3 | [0.008, 0.906] | 3/6 | [0.118, 0.882] |
| 2/3 | [0.094, 0.992] | 4/6 | [0.223, 0.957] |
| 3/3 | [0.292, 1.000] | 5/6 | [0.359, 0.996] |
| | | 6/6 | [0.541, 1.000] |

**Tests** (S-1 is paired: premise fixed per cell x replicate across all seven legs)

| comparison | Fisher (unpaired) | McNemar (paired) |
|---|---|---|
| 3/3 vs 0/3, best possible single-cell contrast | 0.1000 | 0.250 |
| 6/6 vs 0/6 (fable, opus vs v4-pro) | **0.0022** | **0.031** |
| 5/6 vs 0/6 (kimi vs v4-pro) | 0.0152 | 0.063 |
| 4/6 vs 0/6 (sonnet vs v4-pro) | 0.0606 | 0.125 |
| 3/6 vs 0/6 (haiku, flash vs v4-pro) | 0.1818 | 0.250 |
| 6/6 vs 5/6 (Anthropic frontier vs Kimi K3) | **1.0000** | 1.000 |
| 6/6 vs 4/6 | 0.4545 | 0.500 |
| 6/6 vs 3/6 | 0.1818 | 0.250 |
| 12/21 vs 15/21 (cell A vs cell D) | 0.5199  - |
| 2/21 vs 12/21 (blind vs tool-assisted, cell A) | **0.0013**  - |
| 2/21 vs 27/42 (blind vs tool-assisted, pooled) | **<0.0001**  - |

Rank-test ceiling: for two independent n=3 samples the minimum two-sided Mann-Whitney p is
2/C(6,3) = 0.10, so no checker-run comparison in the S-1 table can be significant.
Ordering-test ceiling: recovering k pairs' exact order by chance has p = 1/k!; k=3 → 0.167
(D-4's best case), k=4 → 0.042, k=6 → 0.0014.

**Pass rate versus catalog distance (B3-4)**, per-leg median `min_catalog_distance` from the 42
tool-assisted records against strict-pass rate:

```python
passr=[1.0,1.0,0.833,0.667,0.5,0.5,0.0]           # fable,opus,kimi,sonnet,haiku,flash,pro
dist =[0.1152,0.1131,0.1302,0.1674,0.1904,0.1731,0.2155]
# Spearman rho = -0.982; exact two-sided permutation over all 7! = 5040 orderings: p = 0.00159
```

Reproduce the distances with:
```bash
python3 -c "
import json,glob,collections,statistics as st
d=collections.defaultdict(list)
for f in glob.glob('.worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/records/*.json'):
    r=json.load(open(f))
    if r['min_catalog_distance'] is not None: d[r['leg']].append(r['min_catalog_distance'])
for k,v in sorted(d.items()): print(k, len(v), round(st.median(v),4), round(min(v),4))"
```

**Censoring (B3-8)**, tool-assisted checker invocations at the 10-cap: haiku 4/6, v4-pro 4/5,
sonnet 3/6, flash 2/5, kimi 1/6, fable 0/6, opus 0/6. Every failure sits at the cap.
Self-report versus independent score: **0 mismatches across all 42 shells.**

**Idiom floor, n=3**, 2.9, 5.0, 1.9: mean 3.267, SD 1.582, SEM 0.913, t(2)=4.303 →
95% CI **[-0.66, 7.19]**, containing both 4.0 and 2.3.

**Gram-rate scale exponent**, same condition at two sizes: 17.2/1000 at 26 nodes, 50.1 at 101.
slope = ln(50.1/17.2)/ln(101/26) = 1.0684/1.3558 = **0.788**.
Projection to 193 nodes: 17.2 x (193/26)^0.788 = **83.4**, against the observed 96.3 (~1.15x).
Projection of D-7b's 2.3 to a 149-node median: 2.3 x (149/26)^0.788 ≈ **9.4**, over twice budget.

**0.6 fill-rate floor**, 0 of 48 known-good pairs below 0.6; exact 95% upper bound on the
false-block rate = 1 - 0.05^(1/48) = **6.05%**. Tightest known-good pair 0.635 (margin 0.035).

**Catalog census on this checkout**
```bash
python3 -c "
import json,glob,collections
c=collections.Counter(); prod=collections.Counter(); tot=0
for f in glob.glob('skeletons/*/*.json'):
    if 'lineage' in f: continue
    d=json.load(open(f))
    if 'nodes' not in d: continue
    tot+=len(d['nodes']); m=d.get('metadata',{})
    k=(m.get('age_band'),m.get('length'),m.get('style')); c[k]+=1
    if m.get('production_eligible'): prod[k]+=1
print(sum(c.values()),'skeletons',tot,'nodes',len(c),'cells')
print(sum(prod.values()),'production over',len(prod),'cells, mean',round(sum(prod.values())/len(prod),2))"
```
→ 86 skeletons, 15,507 nodes, 18 cells; 81 production over 14 cells, mean 5.79
(brief:31 says 61 / 11,458; 4.3 says 3-4 per cell).

---

## Appendix B: the eight audit questions, mapped

1. **Statistical power**: B3-7 (S-1: only 0/6-vs-6/6 and 0/6-vs-5/6 separate; "frontier Anthropic converges fastest" fails at p=1.00 against Kimi K3; "worst structure author" holds only against the top legs), B3-8 (censored checker runs), B3-14 (3.3 floor CI), B3-17 (fill rate n=3 selected on passing), B3-10 (96.3 is largely scale), B3-11 (2.3 vs 4.0 vs 3.3 is n=1 against n=3 with SEM 0.91), B3-18 (D-4 p=0.167). The 2-in-21 result is the one adequately powered comparison and is confounded separately (B3-15).
2. **Confounds**: B3-3 (the deciding arm ran outside the harness; subagent legs stateful and self-serve, API legs relayed into a stateless prompt; no tokens or cost for any leg; the driver is in-family and unblinded; **the blind arm's scaffold equality does hold** via `--emit-prompts`/`--score-shell`, so that part of the suspicion is withdrawn), B3-4 (pass rate confounded with catalog conformity), B3-15 (regime confounded with a 6-vs-10 budget), B3-16 (single-model rater panel), B3-23 (three runs conflated), B3-21 (mutation pilot's non-blind author-scored rating). On the specific question: V4 Flash's "call budget lost to unparseable output" is a **harness finding** on this evidence, by the precedent of `AL-327`/`AL-328`, and cannot be attributed to the model until the driving procedure is instrumented. "Zero marginal provider cost" is an accounting boundary, so F7's lever ranking is not cost-controlled.
3. **Pre-registration integrity**: B3-2 (primary endpoint degenerate in both runs; decisions taken on endpoints registered as decision-inert; the registered falsifier's consequence not followed; section F's own amendment rule not applied), B3-9 (slate, cells and replicates all changed, properly declared in the register, entirely undeclared in the brief), B3-5 (W5's retraction reversed), B3-4 and B3-13 (the pre-registered topology-split control specified but not implemented numerically). Degenerate endpoints found: the brief admits one (blind repair rounds); the **tool-assisted permutation test on an all-zero vector** is the second and is undisclosed.
4. **Instrument validity**: B3-1 (the gram instrument measures wording while F5's claim is about decisions, and the recognition verdicts say so), B3-10 (scale non-invariance), B3-13 (`TAU_CELL` owner-chosen, three-fold below p05, blind to M1/M2 edits at exactly 0.0000, 20% self-declared topology), B3-12 (circular calibration of 0.6 and 4.0), B3-14 (3.3 floor), B3-18 (solution transfer), B3-6 (blind judging saturated), B3-16 (single-model recognition panel). Inversion risk: `structural_distance` is the closest analogue to DecisionSignature, never validated against a reader ordering, and B3-4 shows it correlates with authoring success in a direction nobody intended.
5. **Generalization**: B3-11 (26-node result claimed for a 149-node median), B3-17 (three cells, one book each), B3-20 (stale capital facts), B3-7 ("the hard band is not the hard part", p=0.52, from two cells). Skeleton-to-prose leakage runs both ways: F5 licenses a *structural* reuse policy from a *prose* wording metric, and `structural_distance` (a skeleton measure) appears in 4.4's "Works" list on the strength of a prose-level reader read.
6. **Missing experiments**: B3-22 (ranked; cheapest decisive is solution transfer on the D-7b pair, already built and free; highest-cost-on-weakest is the fill-model choice; largest structural gap is that no human or child has read any book).
7. **Falsifiability**: B3-19 (per-principle table: F1, F3 and F7 have no live falsifier; F8 is policy, not a claim; F4 is falsifiable only in principle at n=3; F5's third falsifier has now fired unreported).
8. **The model-judged class**: B3-6 (one criterion at SD 0.00, the rest under 0.65 SD, pool unrecoverable, panel silently broken for an unknown window; the risk that V4 Pro's win is judge preference is concrete because its profile, terse, on-band, 39-53% delivery, is what a saturated rubric rewards) and B3-5 (the ranking was formally retracted). Note the sourcing plan is more careful than the brief here: it suspends the blind quality panel as unfunded and carries fill rate as a covariate on every judged endpoint.
