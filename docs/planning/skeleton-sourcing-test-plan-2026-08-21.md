# Skeleton sourcing test plan: catalog reuse against request-time generation

Date: 2026-08-21. Status: registered and partially executed. S-0 ran (instrument validation
FAILED on its control) and S-1 ran to completion under the revision-3 descope plus a
mid-run-approved tool-assisted condition; results and the authoritative final design live in
register rows S-0/S-1 and `evidence/skeleton-author-vendors/README.md`. E2-E5 have not started.
Revision 2, same date: rebuilt after an adversarial review found three blocking defects (a decision
table that did not cover the outcome space, an E1 design that could not answer its own question at
n=2, and rater-decided falsifiers hanging on an instrument that has never been validated blind).
Section 9 records every finding and its disposition.

Owner question: the original plan built a catalog of reusable skeletons, authored offline and promoted
through a human-gated PR, with story generation as a separate downstream workflow. Model-selection work
on the fill stage (DeepSeek v4 Pro best for prose, v4 Flash effective as a deterministic-style first-pass
reviewer) raises two coupled questions:

1. Does model selection matter for **skeleton development** the way it did for story development?
2. Should skeleton development stay a separate, reusable-catalog workflow, or be tied directly to each
   story request (a bespoke skeleton per request), or something between?

This plan defines the option space, the instruments, and an ordered set of experiments with
pre-registered falsifiers, following the conventions of the
[diversity test register](./diversity-test-register.md): every experiment gets a register row before it
runs, an evidence directory under `docs/planning/evidence/`, an analysis pre-registered before artifacts
exist, and a stated falsifier. Cost estimates are mine and are recorded rather than trusted.

**Hard gate on the whole plan:** the register rows `S-0`..`S-5`, including the numeric margins the
decision rules in section 6 consume, must land before the first token is spent. A margin chosen after
a result exists voids that experiment's pre-registration.

---

## 1. What "better results" has to mean

A sourcing architecture is not judged on one axis. The arms below are scored on all five, because the
plausible outcome is that different arms win different axes and the decision is a trade:

| Axis | What it measures | Instrument tier |
| --- | --- | --- |
| Per-book quality | Is this one story good: structure, pacing, reading level, fill success | Deterministic gate + blind judging |
| Cross-book distinctness | Do two books delivered to the **same reader** read as different books | Deterministic guards + recognition protocol |
| Premise fit | Does the book reflect what the requesting family actually asked for | Judged (new instrument, section 4) |
| Economics | Tokens, wall-clock latency in the request path, repair rounds, amortized capital | Counted from run artifacts, accounting basis in section 5 E5 |
| Safety and review load | What a human must review per book, validator catch-rate on unreviewed shells | Adversarial shell corpus + accounting |

**Scope of the verdict.** The decision this plan produces governs prose cells in the 5-8 through 16+
bands. It does not license anything about: gamebook cells (245-750 nodes per
`band_profile._PRODUCTION_CELLS`, where the Q-3d cost curve is untested and likely prohibitive), the
3-5 band (bespoke reading-level control is weakest exactly where the band is least forgiving), or
series books (structural continuity across books is a designed constraint that bespoke-per-request
breaks by construction; `validator/series` exists to enforce it). Those three surfaces stay on the
catalog path regardless of outcome until separately tested.

---

## 2. Priors: what is already answered, so we do not pay for it twice

The register and evidence directories already constrain this question heavily. The plan below is shaped
around not re-running settled results.

**P1: Reusing a full skeleton fails perceptual distinctness for a repeat reader, and single-parent
mutation does not rescue it.** The
[per-request mutation pilot](./evidence/mutation-per-request-pilot/README.md) filled two mutants of the
same parent with different theme bindings; a pattern-sharp 10-13 reader's same-book verdict lands at
reading position 3, score 2.0/5. Shape-preserving mutants sit at `structural_distance` 0.0000 from the
parent; no bounded single-parent mutant cleared `TAU_CELL` (0.05). Decisive mechanism: every mutant
retained 100% of the parent's `<<FILL>>` beat directives, and recognition anchored on beat-level detail.
**The beats are the fingerprint.** Any arm that re-serves the same beat set to the same reader is
presumed recognized; re-binding the theme does not change that. Two caveats the pilot itself records:
the rating was author-scored, not blind (so the position-3 number is provisional until the protocol
validation in E0 below), and the one mutant that did clear the floor (X, 0.0726) did so by grafting 32
nodes from a **different** catalog skeleton, which is Q-2 cross-skeleton recombination, not
multiplication of one parent.

**P2: Skeleton-free graph generation is structurally viable when the constraints are stated, and its
weak axes are known.** Q-3b: 6/6 structurally clean once the band budgets were in the brief; every
earlier failure violated a constraint never stated to the author. Q-3d: structure survives at 100+
nodes, but one-pass yield collapses, the repair loop belongs in the harness (210k and 337k tokens for
the two large graphs), and reading level splits on whether the author ran a repair loop. So
request-time generation is not blocked on feasibility; it is priced in repair rounds and gated on
reading level. A comparison run against an incomplete brief measures the brief, not the model
(`UW-C199`); briefs must come from `scripts/generate_drafting_brief.py`.

**P3: Premise convergence is invariant across tiers within one model family; cross-vendor is open.**
Q-3c: generations across three tiers of a single family converged on the same motif when the premise
was free, and its README states it is silent on whether the mode holds across vendors. Both readings
point the same way for design: premises must be allocated from a curated enumerated list, never
invented by a leg, or the premise axis contaminates every between-leg measurement. Because the
cross-vendor half is open, E1 additionally cannot read between-leg `structural_distance` as pure
structural competence; section 5 E1 handles this.

**P4: Sharing prose-bearing plan layers leaks wording; a bare-names structural stratum does not.**
D-6 confirmed contract sharing as a convergence cause; D-7 showed fact-gloss prose drove it; D-7b's
bare-names stratum came in at 2.3 shared 4-grams per 1000, under the 4.0 budget and below the 3.3
generator idiom floor. The
[architecture re-specification](./architecture-respecification-2026-08-10.md) splits a plan into a
**structural stratum** (topology and fact graph, shareable freely) and a **decisional stratum**
(choice semantics, beat hints, devices, operations, stakes, generated per book). This names a middle
option between full reuse and full bespoke, and it is the one the existing evidence most favors.
Caveats E2 must inherit: D-7b is n=1 pair on a 26-node graph; its passing stratum is **not wordless**
(473 words of binding-process free text remain, and the arm deleting them was deferred, not run).

**P5: Catalog depth against the demand curve is a purchasing question with an answer.** Q-1: at 3-4
skeletons per cell a child exhausts a cell by roughly their fourth request, and demand concentrates on
medium length. Full reuse only works if depth outruns per-profile demand; the counting has been done.

**P6: A passing gate is not a quality measure, and the current best fill model fails its own fill-rate
floor.** The v4 Pro live fill run delivered 38.9-52.9% of commissioned words with every book passing
the gate (`UW-C307`); `check_fill_integrity.py` now blocks below fill-rate 0.6, calibrated so exactly
those books fail. Every experiment below reports fill-rate and word-budget delivery alongside
pass/fail, and section 7 states the fill-model policy this forces.

**P7: A cross-vendor comparison harness pattern exists and works.** `scripts/compare_vendors.py` plus
[vendor-comparison/README.md](./vendor-comparison/README.md): vendor legs as
`{label, model, provider_order, family}`, backend pinning with `allow_fallbacks: false`, preflight
probing, blind judging via `scripts/blind_books.py` and `scripts/judge_books.py` with self-family
flagging. It varies the model only on the fill stage; the skeleton-stage sibling does not exist yet.

**P8: Same-skeleton similarity is also a fill-layer problem, and one directive mediates it.** AL-498:
two v4 Pro fills of one skeleton from deliberately distant briefs shared 96.3 4-grams per 1000 (24x
budget) when the harness passed no `differentiation_directive`; production's orchestrator passes one.
Independent of beat recognition, this sharpens the case against S0 at the fill layer, and it makes the
directive a configuration every arm must hold constant (section 7).

---

## 3. The option space: three arms, one cross-cutting axis

Each arm is defined by what is **reused across requests** versus **generated per request**. Fill model
and fill configuration are held constant across arms (section 7) so the arms measure sourcing, not
filling.

| Arm | Reused across requests | Generated per request | Maps to |
| --- | --- | --- | --- |
| **S0** Full reuse (status quo) | Entire skeleton: topology, beats, choice labels | Theme binding, prose fill | Production today (`skeleton_match.py` recency-weighted pick) |
| **S2** Stratified reuse | Structural stratum only (topology, bare-names fact graph) | Decisional stratum (beats, choice semantics, devices, stakes), binding, fill | Re-specified R2-1b / R1-1; D-7b's passing configuration |
| **S3** Full bespoke | Nothing (brief and format reference only) | Entire skeleton, then fill | Q-3b protocol at production constraint level; R1-3 generates a fresh contract per book by construction |

Two options are deliberately **not** arms:

- **Per-request single-parent mutation** is settled negative by P1 (the pilot's own verdict:
  shape-preserving operators perceptually null, shape-changing ones marginal, multiplier far smaller
  than k). It is cited as a prior, not re-run.
- **Cross-skeleton recombination (Q-2)** is the only mechanism P1's evidence shows clearing the
  anti-clone floor, but the register has it blocked on narrative-contract coverage (2 of 61 skeletons,
  `AL-213`). It is out of scope here for that stated reason, and it **re-enters** the moment contract
  coverage moves: under decision rule R6 or R7 below (reuse-favoring outcomes), funding contract
  coverage to unblock Q-2 is the named next investment, since E2's structural-stratum artifacts are
  exactly the class that feeds it.

**Axis M (model selection)** applies to every generative stage an arm has: the decisional-stratum
author in S2, the skeleton author in S3, and the offline catalog author that keeps S0 supplied. The
first funded experiment measures this axis in isolation so later arms can fix it and stop paying for
it.

S0 keeps one advantage no other arm has: every shell a child can receive was individually
human-reviewed at promotion time. S2 and S3 ship shells no human approved (the filled story still gets
guardian/admin approval per the mandatory-human-approval ADR, but the reviewer is no longer looking at
a known-good structure). E5 tests that risk directly; it is not merely priced.

---

## 4. Instruments

Three tiers, cheapest first. Nothing advances to a costlier tier without surviving the cheaper one,
and no rater **decides** an outcome: deterministic guards lead, raters confirm. Any falsifier below
that names a rater reading is a confirmation step on a deterministically screened result.

**Tier 1, deterministic structure (free, no model):**
`scripts/check_skeleton.py --strict` (walk floors, in-degree caps, depth-qualified endings, escalated
policy advisories, choice grammar), `scripts/check_graph_structure.py` (six failure classes plus
repairability), per-cell budgets from `validator/band_profile.py`. Report **one-pass yield and repair
rounds separately from final pass rate**; Q-3d shows they diverge sharply and repair cost dominates
spend.

**Tier 2, deterministic distinctness (free, no model):**
pairwise `diversity.structure.structural_distance` against `docs/planning/ws5_floor_baseline.json`
(baseline version 2: `TAU_CELL` 0.05 fixed per the ADR-020 recalibration amendment; hand-authored
same-cell p25 0.298, median 0.380; `TAU_STRUCT` is documentation-only and gates nothing). Because 20%
of `structural_distance` rides on the self-declared `metadata.topology` field and freshly generated
shells control their own declaration, every between-leg use reports the topology-flag component
separately from the numeric-feature component. Also: the shared-gram guard (`check_sibling_fills`,
budget 4.0 per 1000, idiom floor 3.3) and solution transfer (`scripts/check_solution_transfer.py`,
D-4 tier 1), the only instrument that has reproduced reader orderings, needing no taxonomy.

**Tier 3, judged (model or rater cost):**

- *Recognition protocol*: the **frozen** instrument in `evidence/recognition-protocol-pilot/`
  (pairwise: book one in full, book two scene by scene, landing position plus 1-5 score), not the
  pilot's author-scored ad-hoc run. It has never been executed by a rater, so E0 below runs its own
  pre-specified known-answer validation before any experiment consumes it. Production form: two
  counterbalanced raters per pair. Anchors are re-derived on the skeleton family under test; the
  pilot's anchors came from a different skeleton and are not carried over.
- *Blind story judging* via the existing `blind_books.py` / `judge_books.py` stack (provenance
  stripped per AL-226/AL-207, cross-lab panel, self-family flagged).
- *Shell rubric* (**to build**, section 8): blind judging of unfilled shells on beat coherence along a
  path, whether decision points are meaningfully different choices, ending differentiation, and
  whether word budgets and beats set the fill up to succeed.
- *Premise-fit instrument* (**to build**, section 8): **forced-choice identification**, not a 1-5
  score. Given a finished book with provenance stripped, a blind judge picks which of N cell-matched
  request briefs it serves; chance-corrected accuracy is the premise-fit measure. Forced choice
  resists the lexical-echo gaming a free rating invites, since a bespoke book that merely parrots
  brief vocabulary must still out-compete distractor briefs from the same cell.

---

## 5. The experiments

Ordered so each buys information the next one needs. Register each as a row (`S-0`..`S-5`) with its
margins before running; evidence directory named per experiment below.

### E0: instrument validation and shared materials (gate for everything below)

Evidence dir: `evidence/recognition-protocol-pilot/` (existing) plus `evidence/sourcing-materials/`.
Cost (mine): 2 raters over the protocol's pre-specified validation pairs; no generation.

- Run the recognition protocol's own known-answer validation exactly as its README pre-registers it:
  the same-armature pairs must fire, the cross-skeleton control must not, keep the instrument iff
  both hold. Two counterbalanced raters. **If validation fails, E2 and E4 are blocked until an
  instrument that passes exists**; the deterministic guards still run but no perceptual claim is made.
- Build the **curated premise list** (P3): enumerated premises per cell, with a counterbalanced
  allocation rule (which premise goes to which cell x leg x replicate) fixed in the register row.
- Fix the **brief author**: all cell briefs come from `generate_drafting_brief.py`; the 6 request
  briefs for E3 are written once, by hand, before any arm runs, and are shared verbatim across arms.
- **Falsifier:** the protocol validation itself (either known-answer check fails). Firing does not
  kill the programme; it reroutes E2/E4 to deterministic-only endpoints and flags every perceptual
  claim in this plan, including P1's position-3 number, as unconfirmed.

### E1: does model selection matter for skeleton authoring? (axis M in isolation)

> Superseded in part: the 80-shell, 5-leg design below is the original registration, kept for the
> record. The design that actually ran is section 10's revision (2 cells, 3 replicates, 7 legs,
> blind plus a tool-assisted condition); the register row S-1 carries the final grid and result.

Evidence dir: `evidence/skeleton-author-vendors/`. Cost (mine, priced from Q-3d's measured curves, not
generation counts): 3 cheap-band cells at ~5-20k tokens per shell plus 1 hard-band cell at ~100-350k
tokens per shell with repair loops; ~80 shells total; 0 raters for the primary.

- **Cells:** 3 from the cheaper bands plus 1 hard band (10-13+), from `band_profile.offered_cells()`;
  briefs per E0; premises per E0's allocation rule.
- **Legs (named):** `deepseek-v4-pro`, `deepseek-v4-flash`, plus three drawn from the six configured
  in `vendor-comparison/vendors.json` (anthropic-sonnet-5, openai-gpt-5.6-sol, google-gemini-3.1-pro),
  final slate fixed in the `S-1` row. 5 legs x 4 cells x 4 replicates = 80 shells.
- **Harness:** `compare_skeleton_authors.py` (section 8). This is not a single-call sibling of
  `compare_vendors.py`: Q-3d establishes the repair loop belongs in the harness, so the build item
  includes a **shared repair-loop contract** (same validator feedback format, same maximum rounds,
  same patch protocol) applied identically to every leg, because a per-leg repair harness would be the
  treatment. Fill path per cell (one-shot vs chunked, given the 32k single-call cap and AL-494's
  chunked-path caveat) is fixed per cell and identical across legs.
- **One pre-registered primary endpoint: repair rounds to strict pass** (a count; diverges per Q-3d;
  dominates cost), pooled across cells, tested with a permutation test over leg assignment. Everything
  else (one-pass yield, walk probability, failure classes, between-leg `structural_distance` with the
  topology component split out, shell rubric on the top shell per leg, one fill per leg scored with
  `evaluate_books.py`) is **exploratory**: reported, never triggering a decision, because 10 pairwise
  leg comparisons x 5 endpoints x 4 cells guarantees spurious separation somewhere.
- **Falsifier:** the primary endpoint shows no leg separation exceeding the permutation null at the
  pre-registered level. If it fires, model choice does not matter for skeleton structure at the
  resolution this screen can see; the axis is dropped and downstream arms use the cheapest leg that
  passes strict. E1 is a **gross-difference screen** and its register row says so: a null here bounds
  the effect size, it does not prove equivalence.
- Decision use: fixes the authoring model for E2/E3 so arm comparisons stop paying for the model axis.
  Because P3's cross-vendor half is open, a leg whose exploratory distinctness numbers look aberrant
  gets a premise-mode check (same leg, three premises) before any structural conclusion is drawn.

### E2: stratified reuse (S2), the middle option the evidence favors

Evidence dir: `evidence/stratified-per-request/`. Cost (mine): 2 fills for the D-7b deferred arm, then
1 structural stratum, 4-6 decisional strata, 4-6 fills, 2 raters for confirmation only.

- **Precondition:** run D-7b's deferred arm first (delete the 473 words of binding-process free text,
  keep the fact glosses out; two fills). E2's stratum must either byte-match D-7b's passing
  configuration or use the stricter wordless one this arm validates; silently testing a third,
  unmeasured stratum is the failure mode.
- One structural stratum (topology plus bare-names fact graph). **Scale is declared up front:** if the
  stratum is 26-node-scale, the register row states the verdict licenses nothing at production scale
  and a production-scale replication is a named follow-up; preferred is a production-eligible stratum
  accepting the higher fill cost. Generate 4-6 independent decisional strata against it (E1's winning
  model), each bound to a different curated premise, each filled per section 7.
- Screen strata deterministically before any fill: no two sharing a `choice_semantics` string, D-4
  tier 1 transfer near zero pairwise. This **partially satisfies** the re-specified R2-1b screening
  step (which calls for 20 candidates); the remaining 14-16 candidates are what R2-1b still owes.
- Endpoints and pre-registered statistics:
  - Shared-gram guard across all fills: **fires on the condition mean against the 4.0 budget**; the
    worst pair is reported, and a lone same-archetype worst-pair breach (Q-3b showed 4 of 15
    unshared-plan pairs breach through archetype content alone) triggers premise-allocation review,
    not arm death.
  - Recognition protocol (post-E0, two counterbalanced raters) on the two most similar books by
    deterministic screen, as **confirmation** of the deterministic result.
  - Strict-bar yield and repair rounds of the composed shells.
- **Falsifiers, either fires and S2 is out:** (a) the condition-mean shared-gram rate breaches budget
  (the re-specified R2-1b falsifier: the structural stratum leaks wording too); (b) the deterministic
  distinctness screen passes but **both** raters land same-book verdicts at or before position 4 on
  the most-similar pair, meaning topology plus facts alone fingerprint the book and only S3 can help.

### E3: bespoke against catalog, end-to-end on real request shapes (S3 vs S0)

> Superseded in part: section 10 descopes E3 to 4 briefs x 2 arms = 8 fills with the three-judge
> blind panel deferred; the forced-choice premise-fit endpoint below remains the primary.

Evidence dir: `evidence/bespoke-vs-catalog/`. Cost (mine): ~6 bespoke shells with repair loops (hard
bands priced per Q-3d), 12-18 fills, 3-judge blind panel plus forced-choice premise-fit judging.

- **What this compares, stated plainly:** production-catalog-as-it-exists (mature, human-reviewed,
  iterated shells) against fresh bespoke generation. That is a **systems comparison**, the one the
  deployment decision actually needs, not a pure architecture comparison; decision rules read it as
  such. An optional third sub-arm (fresh catalog-style shells authored offline by E1's winner, then
  promoted-style reviewed) separates provenance from reuse if the S0-vs-S3 gap needs attribution; it
  is funded only if rules R3-R5 turn on that attribution.
- 6 request briefs (fixed in E0), spanning 3 cells, **2 of the 6 containing elements the catalog
  demonstrably cannot serve** (thin-cell or unserved-element requests), so the coverage falsifier
  below is decidable. For each request: S0 picks via `skeleton_match` and fills; S3 generates a shell
  from the cell brief plus the request premise (E1's winner, stated constraints, the E1 repair-loop
  contract), then fills. Fill per section 7, Stage-1 gate on, both arms.
- Endpoints: blind judged story quality (existing panel); **premise fit by forced-choice
  identification** (section 4), the axis S3 should win; fill-rate and word delivery as covariates on
  every judged endpoint (P6); reading-level findings **reported jointly with fill-rate**, because
  AL-491 shows thin books read as in-band for the wrong reason; tokens and wall-clock per book
  including repair rounds.
- **Falsifier for bespoke:** S3 does not beat S0 on chance-corrected premise-fit or judged quality by
  the pre-registered margin while costing more per book.
- **Falsifier for the catalog:** on the 2 unservable-element briefs, S0's books are not identifiable
  as serving their brief above chance while S3's are; then reuse is capped by catalog coverage, not
  quality, which is a purchasing decision per Q-1's reframing.

### E4: repeat-reader distinctness, the decisive test of the original reuse plan

Evidence dir: `evidence/repeat-reader-sequence/`. Cost (mine): 3 arms x 4-book sequences, adjacent-pair
recognition confirmation; reuses E2/E3 artifacts where cells match.

- Simulate one profile's four sequential requests inside a single cell (P5: the fourth request is
  where the catalog runs out) under S0, S2, and S3. Recency weighting configured exactly as production
  (`select_skeleton_for_cell`); when S0 must repeat a skeleton, that is the point, not a bug in the
  sim. Include one cross-profile pair (two connected-family readers, per the recommendation-sharing
  three-ring boundary), since shared books make skeleton reuse visible across households.
- **The deterministic measures decide; raters confirm.** The recognition protocol is pairwise and has
  not been validated for a reader carrying three prior books, so the sequence-level endpoints are
  deterministic: solution transfer across the whole sequence, shared-gram rate per adjacent pair,
  `structural_distance` per adjacent pair. Recognition readings (post-E0, two raters) run on adjacent
  pairs only, as confirmation.
- **Falsifier for S0:** any same-skeleton adjacent pair confirmed recognized at or before position 4
  (expected from P1; running it inside the production recency policy establishes how often a real
  profile hits it and at which request index).
- **Falsifier for S2/S3:** bespoke or stratified sequences score no better than S0's non-repeat pairs
  on the deterministic sequence measures, i.e. the D-6 generator-idiom and premise-engine floor
  dominates and per-request generation does not buy perceptible variety either. That would be the most
  decision-relevant negative available, and it is decided deterministically, not by a rater.

### E5: safety, operations, and review economics

Evidence dir: `evidence/sourcing-ops-accounting/`. Cost (mine): adversarial shell corpus authoring
(~15-20 shells, scripted mutations plus hand-seeded defects), one gate run per shell, plus accounting
over E1-E4 artifacts.

- **Safety is tested, not priced, and it has a falsifier.** Build an **adversarial shell corpus**:
  bespoke-style and S2-composed shells seeded with the six `check_graph_structure` failure classes
  plus the two defect classes only readers have ever caught (AL-227: a choice label contradicting its
  own destination; AL-228: prose assuming facts `entry_state` does not guarantee). Measure the
  validator gate's catch-rate on it. Note the existing `adversarial_harness.py` does not do this (it
  feeds a passage corpus to moderation) and `run_guard_battery.py` tests books you hand it; the shell
  corpus is a new build item (section 8).
- **Safety floor, pre-registered and blocking:** if the gate's catch-rate on the corpus is below the
  `S-5` row's floor, no decision rule that ships unreviewed shells to children (R3, R4, R5) may be
  selected; generation is confined to offline catalog growth with promotion review (R6) until the
  gate is extended. This is decision rule R1 and it dominates everything.
- From run artifacts: tokens and latency per delivered book per arm, repair-round distributions,
  projected queue impact (request-time skeleton generation adds a serial stage before fill in
  `generation/worker.py`'s pipeline).
- Review-load accounting: what the human approver sees per arm; enumerate which promotion-time checks
  (`check_promotion_bundle`, strict bar, human read) have no request-time equivalent.
- **Accounting basis, pre-registered:** arm costs are reported both marginal (tokens and latency per
  delivered book) and amortized (S0's offline authoring and promotion-review hours, S2's stratum
  authoring, spread over an assumed catalog lifetime fixed in the `S-5` row). Decision rules consume
  the amortized figure; the marginal figure is reported so the assumption is auditable.

---

## 6. Decision framework, pre-registered

Outcome variables, each defined by exactly one experiment above:

- **SAFE**: E5's gate catch-rate on the adversarial shell corpus meets the `S-5` floor.
- **E2ok**: neither E2 falsifier fired (condition-mean grams within budget, recognition confirmation
  did not land at or before position 4).
- **E3fit**: S3 beat S0 on chance-corrected premise fit or judged quality by the `S-3` margin.
- **E3cov**: E3's catalog-coverage falsifier fired on the unservable-element briefs.
- **E4null**: E4's S2/S3 falsifier fired (per-request generation no better than S0 non-repeat pairs
  on the deterministic sequence measures).
- **COST**: E5's amortized request-path cost and latency for the relevant generated-shell arm are
  within the `S-5` ceilings.

Rules, evaluated in order; the first whose condition holds decides. R1 and R2 are dominance rules and
are checked first by construction; R3-R7 partition the remaining space over (E2ok, E3fit, COST), so
every outcome maps to exactly one rule.

| # | Condition | Architecture decision |
| --- | --- | --- |
| R1 | not SAFE | No unreviewed shell reaches a child. All generation is offline catalog growth with promotion review, targeted at thin cells if E3cov. Re-run E5 after the gate is extended; only then may R3-R5 be revisited. |
| R2 | SAFE and E4null | Per-request generation buys no perceptible variety: **full reuse plus depth purchase** per Q-1, plus per-profile no-repeat guarantees in `skeleton_match`. If E3cov, the depth purchase is targeted at coverage gaps, and offline bespoke generation (promotion-reviewed) is the supply mechanism. This rule deliberately overrides a passing E2: adopting per-request generation that E4 shows readers cannot perceive is spend without benefit. |
| R3 | SAFE, not E4null, E2ok, E3fit, COST | **Stratified reuse as the default serving path, bespoke per-request for thin-cell and unserved-element requests.** The catalog keeps structural capital and human review of topology; the decisional stratum is generated per request with E1's model. |
| R4 | SAFE, not E4null, E2ok, E3fit, not COST | **Stratified reuse serving path; bespoke confined to offline, promotion-reviewed catalog growth** targeted at the coverage gaps E3cov names (the premise-fit edge is real but not affordable in the request path). |
| R5 | SAFE, not E4null, not E2ok, E3fit, COST | **Bespoke per request**, catalog retained for cold start and for the out-of-scope surfaces in section 1. |
| R6 | SAFE, not E4null, not E2ok, E3fit, not COST | **Hybrid**: catalog serves synchronously; bespoke runs offline as flywheel-fed, promotion-reviewed catalog growth targeted at thin cells. Q-2 recombination re-enters here as the cheaper alternative supply mechanism once contract coverage moves. |
| R7 | SAFE, not E4null, not E3fit | **Reuse wins**: stratified if E2ok (structural capital plus per-request decisional variety at no premise-fit sacrifice), otherwise full reuse plus depth purchase per R2's mechanism. Q-2 re-enters as in R6. |

Axis M feeds every rule: if E1's falsifier fired, "E1's model" everywhere above means the cheapest leg
that passes strict. Margins and ceilings (`S-3` premise-fit and quality margins, `S-5` safety floor,
cost and latency ceilings, catalog-lifetime assumption) are fixed in the register rows before any
spend, per the hard gate in the preamble.

---

## 7. Threats to validity, and the controls this plan commits to

- **Brief completeness** (P2): all generation against `generate_drafting_brief.py` output; a failure
  against an unstated constraint indicts the brief and is fed back to the brief generator, not scored
  against the arm.
- **Premise allocation** (P3): curated premise list with a counterbalanced allocation rule, built in
  E0, never invented by a leg.
- **Fill-model policy** (P6, P8): one fill model everywhere downstream, chosen as follows: if a model
  at or above the 0.6 fill-rate floor in the W4/W5 measurements is judged adequate on prose, use it;
  if v4 Pro is retained for prose quality despite its measured 38.9-52.9% delivery, the repair-loop
  policy per fill is pre-registered and fill-rate is carried as a covariate on every judged endpoint.
  The production `differentiation_directive` is passed in **all** arms (S0 included), matching the
  production orchestrator, and stated in every register row.
- **Multiplicity discipline**: one pre-registered primary endpoint per experiment; everything else is
  exploratory and cannot trigger a decision rule.
- **Blinding**: provenance stripped per `blind_books.py`; judging panels cross-lab with self-family
  flagging; recognition raters see books, never arm labels. Self-family flagging covers judges, not
  the author-fill pairing, so E3 reports whether S3's shells share a model family with the fill model,
  and the optional provenance sub-arm exists to control it if the gap needs attribution.
- **Instrument limits**: the six-question instrument is not used at all (its compression record,
  register section A); the recognition protocol is used only after E0 validates it, only pairwise,
  only with two counterbalanced raters, and only to confirm deterministic screens.
- **Gate is not quality** (P6): fill-rate and word-delivery reported on every fill; reading-level
  findings always reported jointly with fill-rate (AL-491).
- **Recency confound in E4**: production `select_skeleton_for_cell` weighting used verbatim; the sim
  measures the policy the child actually experiences.
- **Metric self-declaration** (Tier 2): between-leg `structural_distance` always splits out the
  self-declared topology component.

---

## 8. Build list (gaps this plan needs closed, in order)

0. **Curated premise list plus allocation rule** (E0). Needed by every experiment.
1. **Recognition-protocol validation run** (E0): no new build, the frozen protocol and its
   known-answer pairs exist in `evidence/recognition-protocol-pilot/`; what is owed is two raters
   executing it. Gate for E2/E4's perceptual confirmations.
2. `scripts/compare_skeleton_authors.py`: cross-vendor shell-generation harness with the **shared
   repair-loop contract** (identical validator-feedback format, round cap, and patch protocol across
   legs), Tier 1/2 scoring, standard `runs/` layout. Reuses `_load_vendors`, pricing guard, preflight
   from `compare_vendors.py`, but is an agentic loop, not a single-call sibling. Needed by E1.
3. Shell-judging rubric (section 4, Tier 3). Needed by E1 exploratory, E2.
4. Premise-fit forced-choice instrument: brief-lineup construction, chance correction, judging script.
   Needed by E3.
5. Decisional-stratum generation harness over a fixed structural stratum (the re-specified R2-1b
   screening step largely specifies it). Needed by E2.
6. **Adversarial shell corpus** plus a gate catch-rate runner (E5): scripted seeding of the six
   `check_graph_structure` failure classes plus AL-227/AL-228-shaped defects into bespoke-style and
   S2-composed shells. Needed by E5 and by decision rule R1.
7. Register rows `S-0`..`S-5` with margins, floors, and ceilings fixed, added to the
   [diversity test register](./diversity-test-register.md) **before any spend** (preamble gate).

Nothing here touches the production request path; every harness is offline, like `compare_vendors.py`
and the mutation CLI. Wiring a per-stage model choice or a bespoke path into
`story_requests/authoring_plan.py` is deliberately out of scope until the decision framework has an
answer.

---

## 9. Review record

An adversarial review (2026-08-21, independent reviewer session) returned 17 findings against
revision 1: 3 blocking, 7 major, 7 minor, verdict "not runnable as-is". All 17 were accepted; the
dispositions below produced revision 2. The reviewer also verified P1, P2, P4-P7's citations as
accurate against their primary sources.

| # | Severity | Finding (compressed) | Disposition in revision 2 |
| --- | --- | --- | --- |
| 1 | blocking | Decision table did not cover the outcome space; rows 1/4 could both match; row 5 circular | Section 6 rebuilt as ordered rules over defined outcome variables with an exhaustiveness argument; E4-null and safety made dominance rules; the old row-1/row-4 conflict resolved explicitly in R2 |
| 2 | blocking | E1 undecidable at n=2 with an any-endpoint falsifier; w7 variance method misapplied | E1 redesigned: one primary endpoint (repair rounds), 4 replicates per cell x leg, permutation test, secondaries exploratory, reframed as a gross-difference screen |
| 3 | blocking | Recognition protocol never validated blind; anchors from a different skeleton; raters were deciding falsifiers | E0 added as a hard gate running the frozen protocol's known-answer validation; two counterbalanced raters; raters confirm, deterministic screens decide (E2b, E4) |
| 4 | major | Constant fill model fails its own 0.6 fill-rate floor; differentiation directive unstated | Section 7 fill-model policy: floor-passing model or pre-registered repair policy plus fill-rate covariate; directive passed in all arms |
| 5 | major | E5 safety used instruments that measure something else; safety had no falsifier | Adversarial shell corpus added (build item 6); pre-registered catch-rate floor; safety is dominance rule R1 |
| 6 | major | E1 harness scoped as single-call sibling; hard-band cost understated; "E3 most expensive" inverted | E1 re-scoped (3 cheap + 1 hard cell), priced from Q-3d curves, shared repair-loop contract specified, fill path fixed per cell |
| 7 | major | P3 overstated (cross-vendor open); curated premise list absent from build list | P3 restated; premise list is build item 0 with an allocation rule; E1 gains a premise-mode check |
| 8 | major | E3 confounded (provenance vs architecture, premise fit gameable, coverage falsifier unsampled, brief author unspecified) | E3 reframed as a systems comparison with optional provenance sub-arm; forced-choice premise fit; 2 of 6 unservable briefs required; brief author fixed in E0 |
| 9 | major | E2 inherited D-7b's caveats silently (473-word residue, n=1, 26-node scale); gram statistic undefined | D-7b's deferred arm is an E2 precondition; stratum byte-match required; condition-mean statistic pre-registered; scale licensing stated |
| 10 | major | S1 was an arm in name only; Q-2 recombination missing from the option space | S1 removed (P1 cites it as settled); section 3 records Q-2's exclusion reason and re-entry conditions (R6/R7) |
| 11 | minor | Stale floor-baseline numbers (p25 0.332 vs current 0.298) | Corrected; Tier 2 now cites the file and notes TAU_STRUCT is documentation-only |
| 12 | minor | `structural_distance` topology component is self-declared by generated shells | Component split out in every between-leg use (Tier 2, section 7) |
| 13 | minor | "Doubles as R2-1b" overclaimed at 4-6 of 20 candidates | Restated as "partially satisfies", remainder named |
| 14 | minor | Deferred margins made the table undecidable; E1 leg arithmetic wrong | Preamble hard gate: S-rows with margins before any spend; E1 slate named (5 legs from the 8 available) |
| 15 | minor | E5 economics had no amortization rule | Marginal and amortized both reported; rules consume amortized; lifetime assumption in `S-5` |
| 16 | minor | Scope silence on gamebook, 3-5 band, series | Scope paragraph added to section 1 |
| 17 | minor | AL-498 missing from priors | Added as P8; drives the differentiation-directive control |

---

## 10. Budget revision (2026-08-21, revision 3)

Declared after the registered S-1 run halted on provider credits at 4 of 80 shells and before any
primary-endpoint result existed (the 4 completed shells' exploratory records had been seen; that is
the full extent of data contact). The owner capped programme spend well below the original
estimate, so the experiments are re-scoped to what the sourcing decision actually turns on. Target:
**the whole programme at or under ~$40 of provider credit**, likely ~$25-30.

**What the decision turns on, restated.** The production question is not "which of five labs
authors the best skeleton"; it is (a) does skeleton authoring need the pro tier or is the flash
tier sufficient, (b) does either beat the current practice (a Claude session authoring via the
cyo-author skill mechanism), and (c) which sourcing architecture wins. That needs three legs, two
of them cheap and one free.

Changes, item by item; everything not listed is unchanged:

- **E1 slate**: `deepseek-v4-pro` and `deepseek-v4-flash` as the paid legs (both DeepSeek legs
  together cost about $1.30 across 36 shells in this session's runs; the halted premium slate's
  cost was 90% Sonnet 5, Gemini 3.1 Pro, and GPT-5.6-sol), plus **four Anthropic subagent legs**
  at zero provider cost: `claude-haiku-subagent`, `claude-sonnet-subagent`,
  `claude-opus-subagent`, `claude-fable-subagent`, each authored by isolated subagents at that
  model tier under the identical shared repair-loop contract (same system prompt, same brief,
  same feedback shape, same round cap, driven through the harness's `--emit-prompts` and
  `--score-shell` modes so the loop is reproducible). This closes a real coverage gap: the fill
  slate only ever represented Anthropic by Sonnet checkpoints, and the sonnet leg doubles as the
  current-practice authoring baseline. Declared limitation: subagent legs are tier-labeled, not
  backend-pinned; the serving snapshot is whatever the harness serves that tier, recorded per
  run, so subagent legs support tier-level conclusions, not checkpoint-level ones.
  `google-gemini-3.1-pro` (the only leg with a proven strict pass) stays optional at roughly
  +$12; run it only if the six-leg result is close enough that a premium reference would change
  the decision.
- **E1 grid**: 2 cells (A: 5-8 short; D: 10-13 short) x 3 replicates x 3 legs = 18 shells, round
  cap 6, cap 65536. The 4 already-paid shells from the halted run are reused via `--resume` where
  they fit the reduced grid. Estimated provider cost: **$6-12** (both DeepSeek legs are $2-4 per
  million output tokens; smoke shells ran 40-130k output tokens).
- **E1 inference, honestly downgraded**: at 6-9 observations per leg the permutation screen detects
  only gross differences; the register row already frames E1 as a gross-difference screen and that
  framing now carries more weight. A null is a cost bound, not equivalence.
- **E2**: unchanged in shape (it was never expensive); fills with v4 Pro. Estimated **$5-8**.
- **E3**: descoped. 4 briefs (2 servable, 2 unservable) x 2 arms = 8 fills. The three-judge blind
  quality panel is **deferred**; the primary judged endpoint becomes the forced-choice premise-fit
  identification, scored by two v4-flash judges (the tier already trusted for first-pass review),
  plus the deterministic endpoints (fill-rate, gate findings, cost). The quality-panel margin in
  row `S-3` is suspended until someone funds the panel; the premise-fit margin stands. Estimated
  **$8-12**.
- **E4**: built entirely from E2/E3 artifacts plus catalog fills that already exist; recognition
  raters are session subagents (free); deterministic measures decide, as already required by the
  E0 outcome. Estimated **$0-4**.
- **E5**: adversarial shell corpus is authored by session subagents and scored by the local gate:
  **$0** provider cost.
- **Spend guard**: every live invocation of `compare_skeleton_authors.py` is preceded by a credits
  check (`/api/v1/credits`) and the run report records the before/after balance, so a halt like
  the 2026-08-21 one is a announced stop, not 76 silent 402s.

The decision framework in section 6 is unchanged: nothing in this revision touches a margin that
gates an architecture choice except the suspended S-3 quality-panel margin, whose role is covered
by the premise-fit margin that remains.

**Execution record (2026-08-22).** What actually ran, extending this revision with one
mid-run-approved change: the blind condition ran cell A only, 3 replicates x 7 legs (the two
DeepSeek legs, `moonshot-kimi-k3-modal` on the owner's Modal endpoint, and the four Anthropic
subagent legs) = 21 shells, 2 strict passes; the owner then approved a tool-assisted condition
(author sees the checker's full output, cap 10 invocations per point) which ran cells A and D, 3
replicates x 7 legs = 42 points, 27 passes. Conditions, per-leg results, and reading caveats:
`evidence/skeleton-author-vendors/README.md` (runs `e1r3-2026-08-21` and
`e1r3-tools-2026-08-21`); close-out in register row S-1.

---

## Related

- [Diversity test register](./diversity-test-register.md), conventions and the architecture rows this
  plan composes with (Q-3 family, R1-3, R2-1b, R2-4, Q-1, Q-2)
- [Architecture re-specification](./architecture-respecification-2026-08-10.md), the stratified-plan
  split behind arm S2
- [Per-request mutation pilot](./evidence/mutation-per-request-pilot/README.md), prior P1 and the
  origin of the recognition protocol
- [Recognition protocol pilot](./evidence/recognition-protocol-pilot/README.md), the frozen instrument
  E0 validates
- [Cross-vendor fill comparison](./vendor-comparison/README.md), the harness pattern and judging stack
- [DeepSeek v4 Pro live fill plan](./deepseek-v4-pro-live-fill-plan-2026-08-20.md), priors P6 and P8
  (`AL-490`..`AL-498`, `UW-C307`..`UW-C315`)
