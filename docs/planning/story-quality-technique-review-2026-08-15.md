---
title: "Story-quality technique review: what has not been tried"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Systematic sweep for generation, testing, and feedback techniques the programme has not
  considered, verified against the brief and reviews by grep rather than memory, with three of the
  gaps piloted the same day and pre-registered decision rules for the rest."
tags:
  - planning
  - research
  - quality
component: Research
source: "coverage audit of cyo-generation-research-brief-2026-08-10.md, the five review responses,
  the measurement workplan, the diversity docs, and generation/templates/, 2026-08-15; evidence in
  docs/planning/evidence/{d7c-binding-notes,w16-fill-guide-ablation,recognition-protocol-pilot}"
---

# Story-quality technique review: what has not been tried

> **Date**: 2026-08-15 | **Status**: draft, pending owner sign-off
> **Provenance**: every experimental number produced today is model-generated and
> model-measured; no human and no child has read any book. Deterministic measures are named as
> such; everything else is the weak evidence class.

## 0. Summary

A systematic candidate list of twenty technique families was checked against the research brief
(all 2,951 lines), the five review responses, the measurement workplan, the diversity documents,
the lessons log, and the live prompt templates, by grep with synonym expansion rather than from
memory. Verdicts:

- **Five families appear nowhere**: endings-first authoring, simulated naive-reader comprehension
  probes, per-node ensemble splice, within-book difficulty pacing, and choice-level pick-rate
  telemetry.
- **Prompt-content A/B testing, the question that prompted this review, sits in a gap the workplan
  does not cover**: W8 ablates decoding parameters and W14 ablates context composition, but no
  experiment has ever varied what the prompt says. The one proposal in that direction
  (skeleton-free alternatives proposal, section 9 step 0d and section 11.3) was never run.
  **A pilot ran today** (section 3).
- **Three further families were run today** in some form: the brief's own named highest-value
  experiment (the D-7c binding-notes arm, with matched re-baselines), the fill-prompt guide
  ablation above, and an automated, frozen version of the blind recognition protocol with a
  pre-registered known-answer validation.
- Everything else is either already designed, already refuted, or on the accepted stop list;
  section 5 lists those with citations so they are not re-proposed.

## 1. Method

Twenty candidates were graded NOT MENTIONED / MENTIONED, not designed or run / DESIGNED or RUN,
each with a file and line citation. The section 8.4 families ("considered but not developed") and
the accepted stop list (third review response, section 4) were extracted verbatim as exclusion
sets. Anything proposed here respects requirement 4 (safety and human approval are untouched) and
the workplan's admission rule 3: deterministic measures enter as reported statistics, and nothing
is promoted to a blocking gate without reader evidence.

## 2. The direct answer on prompt A/B testing

**Yes, and the reason it was missed is structural.** The programme's ablations all vary the
machine (model, decoding, quantization, context length) or the inputs (premise, skeleton,
binding); the prompt text has been treated as a constant of the environment. It is not. The
drafting guide is roughly 3,500 words spliced into every generation call, it is identical across
every book the system has ever generated, and the diversity work already names "the shared prompt
is a fixed armature" as a suspected recognition channel (11.3, Layer 1 item 2) with no fill-stage
measurement behind it.

Two distinct questions hide under "A/B test the prompts", and they need different rigs:

1. **Does guide bulk prime convergence?** Two authors reading the same 3,500 words may converge
   the way two authors reading the same fact glosses did (brief section 21: convergent
   elaboration; anything that primes two authors identically converges them). If so, the guide is
   itself part of the armature, and parameterizing it per request stops being a style choice and
   becomes a diversity lever.
2. **Which guide sections buy anything?** Sections that move no deterministic measure are cost
   (every call pays their tokens) and armature surface with no offsetting benefit.

The right experimental shape is **component ablation with deterministic outcomes and
pre-registered rules**, not vibes-based prompt comparison, and not judge-scored comparison (the
panel is unvalidated until W7). The pilot that ran today (`docs/planning/evidence/
w16-fill-guide-ablation/`, results in section 6.2) instantiates the shape: three guide variants
(FULL 3,517 words / NOCRAFT 2,558 / MIN 101), two isolated authors per variant on one bound
skeleton, everything else byte-constant, scored only on deterministic measures (gate pass, FK and
in-band, words per node, dialogue share, second-person density, told-emotion, within-arm shared
four-grams at two scopes).

**Proposed standing item (W16), with rules that can say no.** Run the ablation at n high enough
for a spread estimate (three or more author pairs per arm, two or more skeletons and bands).
Adopt a shorter production guide iff every deterministic measure holds flat within its noise
floor while prompt cost falls; adopt per-request guide parameterization iff within-arm
convergence rises with guide bulk beyond the four-gram noise floor (3.3 per 1000). Drop the item
if neither moves: that would retire 11.3's fill-stage premise, which is a result, not a failure.
Related instrumentation gap worth closing first: run artifacts do not record a prompt or guide
hash, so a retroactive ablation across historical runs is unattributable (section 7, lesson).

## 3. Techniques not considered anywhere, ranked

Each entry: what it is, why it plausibly matters here, evidence class of its outcome, cost, the
falsifier, and a disposition. Register linkage forthcoming on owner sign-off, per the register's
add-work rule.

### T1. Endings-first (backward) authoring

Author the ending set first (kinds, valences, what each pays off), then derive each fork by
walking backward from the endings it serves. Zero hits in the corpus under any synonym. Why it
matters: ending quality (3.92) and choice quality (3.75) are the two lowest live criteria in the
84-verdict pool, PL-24 found a 51 percent single-kind ending mix shipping clean, and the arc
floors are enforced only post-hoc. Backward authoring makes ending payoff and consequence
distance design inputs instead of residues; it is also the natural producer for the
`resolution_space` field the obligation contracts already carry. Outcome class: deterministic
(ending-mix, consequence distance per fork once W3 lands, arc-floor margins) plus judged later.
Cost: one skeleton authored both directions, two fills each. Falsifier: backward-authored
structure scores no better on ending-mix and consequence-distance statistics than the shipped
catalog's forward-authored equivalents. Disposition: **pilot after W3 ships**, since W3 is its
natural scorecard.

### T2. Deterministic-selector best-of-N

Best-of-N is deferred because every proposed form selects on the unvalidated judge (stop list,
third review). But selection on arithmetic is not selection on the instrument: generate N fills,
keep the one with the best in-band rate, dialogue share, told-emotion, and second-person density,
tie-broken by cost. The audit confirms no proposal in the corpus has ever used a deterministic
selector. Why it matters: section 30 shows cheap vendors at $0.04 per book against $0.19 to
$1.42; three cheap candidates plus a deterministic pick costs less than one expensive fill and
can only improve deterministic compliance. Outcome class: deterministic by construction. Cost:
one W9-shaped run. Falsifier: selected-of-three moves no deterministic measure beyond re-run
spread against one-shot on the same vendor. Disposition: **fold into W9 as an extra arm**; it
shares W9's harness and its 20 percent cost rule. Judged-quality effects stay unmeasured until
W7, and that is fine: the selector never sees a judge.

### T3. Per-node ensemble splice (repair-scoped)

The reading-level loop already re-generates failing nodes. Generalize: for any node failing any
deterministic measure, generate k candidate bodies and splice the best by that measure,
re-gating after (the existing loop's adoption rules). Distinct from T2 (whole-book) and absent
from the corpus. Why it matters: repair is currently one re-prompt with findings; a k-candidate
node repair attacks the known worst deterministic defects (dialogue share near zero everywhere,
per-node FK outliers) at the smallest unit, and W2 just showed per-path reading level changes
verdicts on 18.9 percent of books, so node-scoped repair has real targets. Outcome class:
deterministic. Cost: bounded, nodes-that-fail only. Falsifier: k=3 node splice does not beat
k=1 re-prompt on repair success rate at matched spend. Disposition: **build as an extension of
`generation/reading_level_loop.py` once the dialogue floor lands**, since dialogue repair is the
named next loop and gives it a second measure to select on.

### T4. Simulated naive-reader comprehension probe

A cheap model, constrained to a child persona of the target band, reads one path scene by scene
and answers fixed probes: what just happened, what do you think each choice leads to, which
choice would you take and why. Zero corpus hits (the naive-ux-check skill uses real testers on
app mechanics, not story content). Why it matters: three of the four age-appropriateness
dimensions are observed by nothing (AL-337), W13 deliberately refuses deterministic proxies, and
the real child read (W12) is scarce and expensive; a simulated probe is not a reader and must
never be called one, but it is an instrument that can be validated the only way this programme
validates instruments: seed known defects (a non-sequitur merge, a chronology break, a
vocabulary spike) and require the probe to catch them while passing clean books. Prediction
accuracy per fork also gives the first operational proxy for "informed choice". Outcome class:
weak (model judgment) with a known-answer battery, the same posture as W7. Cost: pennies per
book on a cheap tier. Falsifier: the probe fails to separate seeded-defect books from clean ones
(then it joins the dialogue criterion in the bin). Disposition: **build alongside W7's battery**,
which it reuses; keep it out of any gate until W12 can calibrate it against real comprehension.

### T5. Choice-level pick-rate telemetry

Which option children actually take at each fork, aggregated per skeleton and node with the
privacy model's cohort floors. The corpus designs depth/completion telemetry (D16) and never the
per-choice signal. Why it matters: it is the only signal that can ever say a fork is dead in
practice (everyone picks option one), which no similarity metric and no rater sees; it directly
serves the false-choice question (W3) and the inverted-U question (do children re-pick the same
options on re-reads, which is the comfort-of-formula behavior the fifth review predicts). Outcome
class: deterministic once data exists. Cost: schema now, data at launch, so the cost of designing
it now is one migration and the cost of not designing it is losing the first cohort's data.
Falsifier: not applicable pre-launch; the design is falsified only by the privacy review.
Disposition: **design the schema with 1a/1d now** (the third review already ordered the approval
questionnaire and telemetry schema early for exactly this reason); aggregate-only by
construction, minimum-cohort floors per the privacy model.

### T6. Within-book difficulty pacing

Per-path FK slope and per-scene new-entity rate as reported statistics: does a book get harder
as it goes, and is the last act of a long path above band while the book average sits inside?
Zero corpus hits; W2's concentration finding (the aggregate hides the hardest reading) makes the
slope the obvious next cut. Outcome class: deterministic, computable today off W1 paths with
existing `score_body`. Cost: near zero. Falsifier: slope adds no verdict changes beyond W2's
level check (then it is complexity bought for nothing, W2's own drop rule). Disposition: **add to
the W2 family as a reported statistic**; no gate without W12.

## 4. Considered-but-undeveloped techniques worth designing now

- **Persona conditioning (T8).** "Persona ensembling" appears once as an unelaborated phrase.
  The voice criterion is the second-lowest live score (3.49) and the idiom floor (3.3 per 1000)
  is task-driven, so a per-book authorial persona is the only untested lever aimed at both.
  Deterministic outcome available: cross-book shared four-grams between different-persona books
  against same-persona books, same harness as today's pilots. Judged voice effects wait for W7.
  One caution transfers from 16j: a persona must be assigned, not offered, and never shown to a
  sibling author.
- **Automated recognition gate (T9).** The manual blind read is the programme's most
  decision-bearing instrument and has never been runnable twice the same way. Frozen today as
  `docs/planning/evidence/recognition-protocol-pilot/protocol.py` (child-visible surfaces only,
  ids withheld, breadth-first order, sequential commitment) with pre-registered known answers
  (section 6.3). If validation holds across more pairs, promote to `scripts/` and run it at
  catalog-admission time against the requesting child's prior books, which is the assignment-time
  use the exposure analysis already argues for.
- **Prosody statistics for 3-5 (T10).** The guide says rhythm and repetition beat FK at 3-5 and
  nothing measures either. Sentence-length variance, refrain detection (repeated-line rate), and
  page-turn hook presence are all deterministic and cheap. Enter as reported statistics; the
  construct question (does prosody as measured track read-aloud quality) is a W12 questionnaire
  line, not a formula.
- **Embedding-based paraphrase detection (T11).** Proposed twice, never run, and W15's own
  falsifier (a paraphrase leak must be caught or the checker is a substring match in disguise)
  practically requires it. Needs one dependency decision (a small vendored embedder against the
  no-heavy-NLP precedent RL-13 set); the decision, not the code, is the work item.
- **Cross-vendor staged ensemble (T12).** The 12b response flags "no proposal runs different
  stages on different models" and W9 now routes stages by cost tier. The untested quality-side
  variant is plan-vendor rotation: whether a plan authored by vendor A and filled by vendor B
  breaks the premise mode that intra-family instances share. Deterministic outcome (premise
  convergence per section 24's method). One run, W9's harness.

## 5. Do not re-propose

Verified refuted, null, or stop-listed, with the ruling citation: same-parent mutation as a
multiplier (alternatives proposal 11.5.1); obligation variance for recognition
(obligation-variance spec section 12); instructed divergence (16j, 126.7 against 1.0); vendor
rotation for lexical variety (section 27, ratio 1.28); buying diversity with spend (section 31,
rho -0.11); judge-selected best-of-N, preference tuning on the panel, and cross-vendor diversity
sweeps (stop list, third review response section 4); kappa 0.80 and Z-based judge deprecation
(12b section 5.4); deterministic proxies for the qualitative age dimensions (12b section 3.2);
sentence-level beats (framework doc S2). The section 8.4 families (shape-only skeletons, scene
library plus recombination, grammar over patterns, planner-based, decision-first inversion,
explicit inter-book repulsion) remain open design directions the brief itself holds; nothing
here duplicates them, and T1 is deliberately the cheapest entry into the planner-shaped family.

## 6. What ran today

Three experiments, all pre-registered before any author or rater ran, all committed under
`docs/planning/evidence/`. Numbers below are filled in from the frozen results files; the
directories are the source of record.

### 6.1 D-7c: the binding-notes arm, with matched re-baselines

The brief's named highest-value experiment (16l correction block): delete the 473 words of
non-gloss free text while keeping the 422 gloss words, closing the confound D-7/D-7b left open.
Because the historical fills were authored by a different model generation (and, the scorer
shows, in third person throughout: `you_per_1000 = 0.0` on every historical clocktower fill),
all three kernels were re-authored today by same-generation isolated authors under one fixed
instruction file. Results: section 6.4 table and `d7c-binding-notes/results.md`.

### 6.2 W16 pilot: fill-prompt guide ablation

Section 2's pilot. Results: section 6.4 table and `w16-fill-guide-ablation/results.md`.

### 6.3 Recognition protocol validation

Known-answer validation of the frozen automated protocol on today's same-armature pairs plus a
cross-skeleton control. Results: `recognition-protocol-pilot/results.md`.

### 6.4 A catalog baseline nobody had computed: the W2.3 measure on the committed fills

Running the pilot's you-density measure (the deferred W2.3 check, prototyped in today's scorer)
over all 23 committed catalog fills in `out/`, with dialogue share alongside:

- **14 of 23 books sit at or under 6.6 "you" per 1000 words**, the design review's own measured
  third-person range, including **every** 3-5, 5-8, and 8-11 book and four of five 10-13 books.
  Only teen-band books (20.8 to 79.0 per 1000) are second-person compliant. The guide's D11
  grandfathering is not an edge case; it is most of the catalog, and every kid-band cell needs a
  compliant replacement before D11's "stop offering once a compliant skeleton exists" rule can
  bite on anything.
- **Dialogue share is 0.000 on 20 of 23 books.** The two exceptions are legacy-shaped early
  fills (`the-lost-mitten` 0.19, `the-clocktower-cipher` 0.30), so the near-zero-dialogue defect
  section 29 measured across eight vendors is also the committed catalog's own state, and the
  dialogue floor-and-repair item is a catalog remediation, not only a generation fix.
- The two 3-5 books post the catalog's worst in-band rates (0.455, 0.69), consistent with the
  guide's own position that FK is the wrong line-by-line target at 3-5 (T10 is the follow-up).

### 6.5 Results of the three runs

**Status 2026-08-15, 07:40 UTC: interrupted by the session usage limit before any fill
landed.** All twelve isolated authors (six D-7c, six W16) were terminated by the account's
usage reset window with zero output files written, so no result exists and nothing here is
partial: the arms are clean to re-run. Every input needed to resume is committed (kernels,
bound skeleton, prompt files, instruction file, scorer, protocol), so a resume re-stages from
git alone. The scorer's known-answer validation (it reproduces the corrected 16l anchors, 2.33
and 13.59 per 1000, exactly on the frozen d7/d7b artifacts) and the section 6.4 catalog
baseline are the run's completed measurements. When the fills are re-run, each evidence
directory's `results.md` is the frozen source of record and this section gains the numbers.

## 7. Testing-structure improvements this review recommends

1. **Prompt provenance on every artifact.** Record a hash of the rendered prompt (and the guide
   text) in every generated book's run record, so any future prompt change is attributable and
   any historical comparison can be stratified by prompt version. Today no run artifact carries
   one, which is why W16 had to be run forward rather than mined from history.
2. **Land AL-309's fix.** `check_sibling_fills.py` grams a single concatenated string and
   manufactures junction grams; today's scorer implements the proposed per-unit gramming
   alongside the legacy scope and reproduced the corrected 16l anchors exactly (2.33 and 13.59
   per 1000) on first use. Promote the two-scope form into the script as flags.
3. **Fix `bind_theme.py`'s default path.** `validate_slot_bindings` has an `is_default` escape
   for exactly the legacy-lexicon self-collision the default binding creates, and the CLI never
   passes it, so the documented no-bindings reference render fails on any contract whose lexicon
   names its own default values. One-line fix plus a regression test.
4. **Freeze instruments as code, not session lore.** The recognition protocol existed only as
   per-session hand-built prompts; it is now a file. The same treatment is owed to the blind
   rater questionnaire and the fill-author instruction sheet, both of which have drifted across
   experiments (the D-7 series' author prompts were never saved, which is why today's
   re-baselines were required at all).
5. **Known-answer batteries before trust, for every new instrument.** Today's scorer and
   protocol were both validated against known answers before producing a new number. This is
   brief section 20's rule; it should be stated once in the measurement workplan as binding on
   any instrument, not re-derived per experiment.

## 8. Related documents

- [Research brief](./cyo-generation-research-brief-2026-08-10.md), sections 8.4, 16l, 20, 21,
  27, 29 to 32
- [Measurement workplan](./cyo-measurement-workplan-2026-08-12.md), W1 to W15 and the admission
  rules this review's proposals follow
- [Framework problem and structures](./cyo-framework-problem-and-structures-2026-08-10.md),
  the S0 to S9 ledger section 5 cites
- [Skeleton-free alternatives proposal](./skeleton-free-alternatives-proposal-2026-08-09.md),
  section 9 step 0d and section 11.3 (the un-run prompt-ablation proposals)
- Review responses: [third](./cyo-review-response-2026-08-12.md),
  [fourth and fifth](./cyo-review-response-2026-08-12b.md),
  [second](./cyo-review-response-2026-08-11.md)
- Evidence: `evidence/d7c-binding-notes/`, `evidence/w16-fill-guide-ablation/`,
  `evidence/recognition-protocol-pilot/`
