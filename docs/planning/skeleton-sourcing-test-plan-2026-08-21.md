# Skeleton sourcing test plan: catalog reuse against request-time generation

Date: 2026-08-21. Status: proposed, no experiment started.
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

---

## 1. What "better results" has to mean

A sourcing architecture is not judged on one axis. The arms below are scored on all five, because the
plausible outcome is that different arms win different axes and the decision is a trade:

| Axis | What it measures | Instrument tier |
| --- | --- | --- |
| Per-book quality | Is this one story good: structure, pacing, reading level, fill success | Deterministic gate + blind judging |
| Cross-book distinctness | Do two books delivered to the **same reader** read as different books | Deterministic guards + recognition protocol |
| Premise fit | Does the book reflect what the requesting family actually asked for | Judged (new instrument, section 4) |
| Economics | Tokens, wall-clock latency in the request path, repair rounds | Counted from run artifacts |
| Safety and review load | What a human must review per book, validator coverage on unreviewed shells | Accounting + adversarial battery |

---

## 2. Priors: what is already answered, so we do not pay for it twice

The register and evidence directories already constrain this question heavily. The plan below is shaped
around not re-running settled results.

**P1: Reusing a full skeleton fails perceptual distinctness for a repeat reader, and mutation does not
rescue it.** The
[per-request mutation pilot](./evidence/mutation-per-request-pilot/README.md) filled two mutants of the
same parent with different theme bindings; a pattern-sharp 10-13 reader's same-book verdict lands at
reading position 3, score 2.0/5. Shape-preserving mutants sit at `structural_distance` 0.0000 from the
parent; no bounded single-parent mutant cleared `TAU_CELL` (0.05). Decisive mechanism: every mutant
retained 100% of the parent's `<<FILL>>` beat directives, and recognition anchored on beat-level detail.
**The beats are the fingerprint.** Any arm that re-serves the same beat set to the same reader is
presumed recognized; re-binding the theme does not change that.

**P2: Skeleton-free graph generation is structurally viable when the constraints are stated, and its
weak axes are known.** Q-3b: 6/6 structurally clean once the band budgets were in the brief; every
earlier failure violated a constraint never stated to the author. Q-3d: structure survives at 100+
nodes, but one-pass yield collapses and reading level splits on whether the author ran a repair loop.
So request-time generation is not blocked on feasibility; it is priced in repair rounds and gated on
reading level. A comparison run against an incomplete brief measures the brief, not the model
(`UW-C199`); briefs must come from `scripts/generate_drafting_brief.py`.

**P3: Premise convergence is model-family-invariant.** Q-3c: generations across three model tiers
converged on the same motif when the premise was free. Any arm's novelty measurement must allocate
premises from a curated enumerated space, or the premise axis will drown the arm axis.

**P4: Sharing prose-bearing plan layers leaks wording; a bare-names structural stratum does not.**
D-6 confirmed contract sharing as a convergence cause; D-7 showed fact-gloss prose drove it; D-7b's
bare-names stratum came in at 2.3 shared 4-grams per 1000, under the 4.0 budget and below the 3.3
generator idiom floor. The
[architecture re-specification](./architecture-respecification-2026-08-10.md) splits a plan into a
**structural stratum** (topology and fact graph, shareable freely) and a **decisional stratum**
(choice semantics, beat hints, devices, operations, stakes, generated per book). This names a middle
option between full reuse and full bespoke, and it is the one the existing evidence most favors.

**P5: Catalog depth against the demand curve is a purchasing question with an answer.** Q-1: at 3-4
skeletons per cell a child exhausts a cell by roughly their fourth request, and demand concentrates on
medium length. Full reuse only works if depth outruns per-profile demand; the counting has been done.

**P6: A passing gate is not a quality measure.** The v4 Pro live fill run delivered 38.9-52.9% of
commissioned words with every book passing the gate (`UW-C307`). Every experiment below reports
fill-rate and word-budget delivery alongside pass/fail.

**P7: A cross-vendor comparison harness pattern exists and works.** `scripts/compare_vendors.py` plus
[vendor-comparison/README.md](./vendor-comparison/README.md): vendor legs as
`{label, model, provider_order, family}`, backend pinning with `allow_fallbacks: false`, preflight
probing, blind judging via `scripts/blind_books.py` and `scripts/judge_books.py` with self-family
flagging. It varies the model only on the fill stage; the skeleton-stage sibling does not exist yet.

---

## 3. The option space: four arms, one cross-cutting axis

Each arm is defined by what is **reused across requests** versus **generated per request**. Fill model
is held constant across arms (v4 Pro) so the arms measure sourcing, not filling.

| Arm | Reused across requests | Generated per request | Maps to |
| --- | --- | --- | --- |
| **S0** Full reuse (status quo) | Entire skeleton: topology, beats, choice labels | Theme binding, prose fill | Production today (`skeleton_match.py` recency-weighted pick) |
| **S1** Reuse + per-request mutation | Parent skeleton | Mutant shell, binding, fill | ADR-020 per-request proposal; **already answered weakly by P1, kept only as a baseline arm, never re-piloted alone** |
| **S2** Stratified reuse | Structural stratum only (topology, bare-names fact graph) | Decisional stratum (beats, choice semantics, devices, stakes), binding, fill | Re-specified R2-1b / R1-1; D-7b's passing configuration |
| **S3** Full bespoke | Nothing (brief and format reference only) | Entire skeleton, then fill | Q-3b protocol at production constraint level; R1-3 generates a fresh contract per book by construction |

**Axis M (model selection)** applies to every generative stage an arm has: the decisional-stratum
author in S2, the skeleton author in S3, and the offline catalog author that keeps S0 supplied. The
first experiment measures this axis in isolation so later arms can fix it and stop paying for it.

S0 keeps one advantage no other arm has: every shell a child can receive was individually
human-reviewed at promotion time. S2 and S3 ship shells no human approved (the filled story still gets
guardian/admin approval per the mandatory-human-approval ADR, but the reviewer is no longer looking at
a known-good structure). Section 7 prices that.

---

## 4. Instruments

Three tiers, cheapest first. Nothing advances to a costlier tier without surviving the cheaper one.

**Tier 1, deterministic structure (free, no model):**
`scripts/check_skeleton.py --strict` (walk floors, in-degree caps, depth-qualified endings, escalated
policy advisories, choice grammar), `scripts/check_graph_structure.py` (six failure classes plus
repairability), per-cell budgets from `validator/band_profile.py`. Report **one-pass yield and repair
rounds separately from final pass rate**; Q-3d shows they diverge sharply and repair cost dominates
spend.

**Tier 2, deterministic distinctness (free, no model):**
pairwise `diversity.structure.structural_distance` against the calibrated floors in
`docs/planning/ws5_floor_baseline.json` (`TAU_CELL` 0.05, hand-authored same-cell p25 0.332); the
shared-gram guard (`check_sibling_fills`, budget 4.0 per 1000, idiom floor 3.3); solution transfer
(`scripts/check_solution_transfer.py`, D-4 tier 1), which is the only instrument that has reproduced
reader orderings and needs no taxonomy.

**Tier 3, judged (model or rater cost):**

- *Recognition protocol* from the mutation pilot, unchanged: a pattern-sharp in-band reader who read
  book 1 last week starts book 2 today; record the reading position where the same-book verdict lands
  and the 1-5 score. This instrument has calibration anchors (position 2 -> 2.0, position 4 -> 2.5) and
  it worked; the six-question instrument's record (Q4 pinned at 5, Q3 compressed) says raters confirm
  rankings here, they do not produce them.
- *Blind story judging* via the existing `blind_books.py` / `judge_books.py` stack (provenance
  stripped per AL-226/AL-207, cross-lab panel, self-family flagged).
- *Shell rubric* (**to build**, section 8): blind judging of unfilled shells on beat coherence along a
  path, whether decision points are meaningfully different choices, ending differentiation, and
  whether word budgets and beats set the fill up to succeed.
- *Premise-fit score* (**to build**, section 8): given the request brief and the finished book, a blind
  judge scores how specifically the book serves that request rather than any request in the cell. This
  is the axis on which bespoke arms should win if they win anywhere, and no instrument for it exists.

---

## 5. The experiments

Ordered so each buys information the next one needs. Register each as a row (proposed prefix `S-`)
before running; evidence directory named per experiment below.

### E1: does model selection matter for skeleton authoring? (axis M in isolation)

Evidence dir: `evidence/skeleton-author-vendors/`. Cost (mine): ~30-40 shell generations, 0 raters for
the primary; one optional shell-rubric round.

- 4 production cells from `band_profile.offered_cells()`, at least one hard band (10-13 or above);
  per-cell briefs from `generate_drafting_brief.py` (P2); 4 fixed premises from a curated list (P3).
- 4-5 vendor legs (v4 Pro, v4 Flash, plus the labs already configured in
  `vendor-comparison/vendors.json`), 2 replicates per cell x leg, via a `compare_skeleton_authors.py`
  sibling of `compare_vendors.py` (section 8).
- Primary endpoints, all Tier 1/2: one-pass strict yield, repair rounds to strict pass, walk
  probability, `check_graph_structure` failure classes, `structural_distance` to the in-cell catalog
  and between legs. Secondary: shell rubric on the top shell per leg; one fill per leg (same fill
  model) scored with `evaluate_books.py` to measure how well each leg's shells commission prose.
- **Falsifier:** no vendor separates from the others beyond replicate variance (bounded with the
  `w7_run_to_run.py` approach) on any primary endpoint. If it fires, model choice does not matter for
  skeleton structure, the axis is dropped, and S2/S3 use whatever is cheapest that passes strict.
- Decision use: fixes the authoring model for E2/E3 so arm comparisons stop paying for the model axis.

### E2: stratified reuse (S2), the middle option the evidence favors

Evidence dir: `evidence/stratified-per-request/`. Cost (mine): 1 structural stratum, 4-6 decisional
strata, 4-6 fills, 1-2 raters for confirmation only.

- One production-eligible structural stratum (topology plus bare-names fact graph per D-7b's passing
  configuration). Generate 4-6 independent decisional strata against it, each bound to a different
  curated premise, each filled with the constant fill model.
- Screen strata deterministically before any fill: no two sharing a `choice_semantics` string, D-4
  tier 1 transfer near zero pairwise (the re-specified R2-1b screening step).
- Endpoints: shared-gram guard across all fills (budget 4.0); recognition protocol on the two most
  similar books by deterministic screen; strict-bar yield of the composed shells; repair rounds.
- **Falsifiers, either fires and S2 is out:** (a) prose from a shared structural stratum still
  breaches the shared-gram budget (the re-specified R2-1b falsifier: the structural stratum leaks
  wording too); (b) recognition lands at or before position 4 on the most-similar pair despite fully
  per-book beats, meaning topology plus facts alone fingerprint the book and only S3 can help.
- Note: this experiment is deliberately shaped so its artifacts double as the R2-1b screening run; if
  the register runs R1-3/R2-1b first, E2 consumes those artifacts instead of generating its own.

### E3: bespoke against catalog, end-to-end on real request shapes (S3 vs S0)

Evidence dir: `evidence/bespoke-vs-catalog/`. Cost (mine): ~6 bespoke shells with repair loops, 12
fills, 3-judge blind panel plus premise-fit judging; the most expensive experiment here.

- 6 realistic story-request briefs (drawn from the `story_requests` intake shape: age band, length,
  interests, requested elements), spanning 3 cells. For each request: arm S0 picks via
  `skeleton_match` and fills; arm S3 generates a shell from the cell brief plus the request premise
  (E1's winning model, Q-3b-style stated constraints, repair loop instrumented), then fills. Same fill
  model, both arms; Stage-1 gate on for both.
- Endpoints: blind judged story quality (existing panel), **premise fit** (new instrument, the axis S3
  should win), fill-rate and word delivery (P6), reading level findings, tokens and wall-clock per
  book including repair rounds.
- **Falsifier for bespoke:** S3 does not beat S0 on premise fit or judged quality by a pre-registered
  margin while costing more per book; then request-time generation buys nothing the catalog does not
  already provide, and the sourcing question reduces to E2 plus catalog depth (P5).
- **Falsifier for the catalog:** S0 books score materially worse on premise fit across requests whose
  elements the catalog cannot serve (the empty-cell and thin-cell cases); then reuse is capped by
  catalog coverage, not quality, which is a purchasing decision per Q-1's reframing.

### E4: repeat-reader distinctness, the decisive test of the original reuse plan

Evidence dir: `evidence/repeat-reader-sequence/`. Cost (mine): 3 arms x 4-book sequences, recognition
rating on adjacent pairs; reuses E2/E3 artifacts where cells match.

- Simulate one profile's four sequential requests inside a single cell (P5 says the fourth request is
  where the catalog runs out) under S0, S2, and S3. Recency weighting configured exactly as production
  (`select_skeleton_for_cell`); when S0 must repeat a skeleton, that is the point, not a bug in the
  sim. Include one cross-profile pair (two connected-family readers, per the recommendation-sharing
  three-ring boundary) since shared books make skeleton reuse visible across households.
- Endpoints: recognition position and score on each adjacent pair and on the repeat pair; solution
  transfer across the whole sequence; shared-gram rate per pair.
- **Falsifier for S0:** any same-skeleton pair recognized at or before position 4 (expected from P1;
  running it inside the production recency policy establishes how often a real profile hits it).
- **Falsifier for S2/S3:** bespoke or stratified sequences score no better than S0's non-repeat pairs,
  i.e. the D-6 generator-idiom and premise-engine floor dominates and per-request generation does not
  buy perceptible variety either. That would be the most decision-relevant negative available.

### E5: operations, safety, and review economics (no model comparison)

Evidence dir: `evidence/sourcing-ops-accounting/`. Cost (mine): accounting over E1-E4 artifacts plus
one adversarial battery run.

- From run artifacts: tokens and latency per delivered book per arm, repair-round distributions,
  projected queue impact (request-time skeleton generation adds a serial stage before fill in
  `generation/worker.py`'s pipeline).
- Review-load accounting: what the human approver sees per arm. S0: fill over a promoted shell. S2/S3:
  fill over an unreviewed shell; enumerate which promotion-time checks (`check_promotion_bundle`,
  strict bar, human read) have no request-time equivalent and which are already automated.
- Run `scripts/adversarial_harness.py` / `run_guard_battery.py` against bespoke shells specifically:
  the validator gate was tuned on catalog-shaped inputs, and P2's lesson (failures come from unstated
  constraints) cuts both ways; a bespoke path widens the input distribution the gate must hold
  against.
- No falsifier; this is a costing exercise. Its output is the economics column of the decision table.

---

## 6. Decision framework, pre-registered

To be read top to bottom after E1-E5 report; first matching row decides.

| # | Outcome pattern | Architecture decision |
| --- | --- | --- |
| 1 | E2 passes both falsifiers and E3 shows no bespoke premise-fit edge | **Stratified reuse**: catalog keeps structural capital and human review of topology; decisional stratum and binding generated per request with E1's model. Original reuse intent survives at the stratum level. |
| 2 | E2 fails on recognition (topology fingerprints) but E3/E4 show bespoke distinct and premise-fit edge, and E5 cost acceptable | **Bespoke per request**, catalog retained for cold-start, fallback, and the 3-5 band if bespoke reading-level control stays weak (P2). |
| 3 | E3 bespoke edge exists but E5 pricing fails (latency or review load) | **Hybrid**: catalog serves the request synchronously; bespoke generation runs offline as flywheel-fed catalog growth targeted at thin cells, keeping promotion review. |
| 4 | E4's S2/S3 falsifier fires (idiom floor dominates everywhere) | **Full reuse with depth purchase** per Q-1's counting, plus per-profile no-repeat guarantees in `skeleton_match`; stop spending on per-request generation. |
| 5 | E1's falsifier fires but arms still separate | Model axis closed; sourcing decision proceeds on rows 1-4 with the cheapest passing model. |

Margins (judged-quality delta, premise-fit delta, cost ceilings) are to be fixed in the register rows
before each run, not chosen after results exist.

---

## 7. Threats to validity, and the controls this plan commits to

- **Brief completeness** (P2): all generation against `generate_drafting_brief.py` output; a failure
  against an unstated constraint indicts the brief and is fed back to the brief generator, not scored
  against the arm.
- **Premise allocation** (P3): curated premise list, assigned to arms, never invented by a leg.
- **Fill-model constancy**: v4 Pro everywhere downstream; the arms differ only in sourcing.
- **Blinding**: provenance stripped per `blind_books.py`; judging panels cross-lab with self-family
  flagging; recognition raters see books, never arm labels.
- **Instrument limits**: the six-question instrument is not used to produce rankings (its compression
  record, register section A); deterministic guards lead, raters confirm.
- **Gate is not quality** (P6): fill-rate and word-delivery reported on every fill.
- **Replicate variance**: E1 runs 2 replicates per cell x leg and bounds separation with the
  `w7_run_to_run.py` method before claiming any vendor difference.
- **Recency confound in E4**: production `select_skeleton_for_cell` weighting used verbatim; the sim
  measures the policy the child actually experiences.

---

## 8. Build list (gaps this plan needs closed, in order)

1. `scripts/compare_skeleton_authors.py`: sibling of `compare_vendors.py`; takes a cell brief plus a
   premise, asks each vendor leg for a shell, runs Tier 1/2 scoring, writes the standard `runs/`
   layout. Reuses `_load_vendors`, pricing guard, preflight. Needed by E1.
2. Shell-judging rubric (section 4, Tier 3). Needed by E1 secondary, E2.
3. Premise-fit instrument: brief-plus-book blind judging protocol and script. Needed by E3.
4. Decisional-stratum generation harness over a fixed structural stratum (the re-specified R2-1b
   screening step largely specifies it). Needed by E2.
5. Register rows `S-1`..`S-5` with margins fixed, added to the
   [diversity test register](./diversity-test-register.md) as each experiment starts.

Nothing here touches the production request path; every harness is offline, like `compare_vendors.py`
and the mutation CLI. Wiring a per-stage model choice or a bespoke path into
`story_requests/authoring_plan.py` is deliberately out of scope until the decision table has an answer.

---

## Related

- [Diversity test register](./diversity-test-register.md), conventions and the architecture rows this
  plan composes with (Q-3 family, R1-3, R2-1b, R2-4, Q-1, Q-2)
- [Architecture re-specification](./architecture-respecification-2026-08-10.md), the stratified-plan
  split behind arm S2
- [Per-request mutation pilot](./evidence/mutation-per-request-pilot/README.md), prior P1 and the
  recognition protocol
- [Cross-vendor fill comparison](./vendor-comparison/README.md), the harness pattern and judging stack
- [DeepSeek v4 Pro live fill plan](./deepseek-v4-pro-live-fill-plan-2026-08-20.md), prior P6
  (`AL-490`..`AL-498`, `UW-C307`..`UW-C315`)
