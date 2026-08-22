# Generating choose-your-own-adventure books with LLMs: a framework, a pipeline, and what the evidence says

Version of 2026-08-22. This supersedes the
[2026-08-10 brief](./cyo-generation-research-brief-2026-08-10.md) as the current account of the
programme; that document remains the deeper treatment of the diversity problem, the literature, and
the S0-S9 design history, and is cited throughout rather than repeated. What is new here: the
framework section distills what the whole evidence base now supports, the pipeline section describes
the system as it actually runs today, and the analysis section incorporates the 2026-08-21 skeleton
sourcing experiments (register rows `S-0`..`S-5`), which changed our understanding of where model
selection matters.

> Evidence classes, used throughout: **deterministic** (a script anyone can re-run), **model-judged**
> (blind LLM raters, the weak class), and **human-gated** (a person approved it). Every load-bearing
> claim below names its class and its artifact.

---

## 1. The core challenge

A choose-your-own-adventure book for children is a composite artifact with two halves that stress
different capabilities:

- **A story graph**: every path terminates, no trap loops, endings are reachable at qualifying
  depth, branching cadence fits the age band, and the graph's shape is admissible for its declared
  topology. This is constraint satisfaction, and models cannot reliably verify it by rereading
  their own output (2026-08-10 brief, sections 3.1-3.6).
- **Branching prose**: age-banded reading level, craft, coherence across reconverging paths, and
  fidelity to what each node was commissioned to do. This is generation under constraint, where
  quality is judged, not computed.

The scale makes one-pass generation untenable: the catalog spans 61 graphs and 11,458 nodes, from
~800-word books at ages 3-5 to a 677-node, ~118,000-word graph at 16+. The product constraints make
shortcuts untenable: this is a children's app, so every published book passes deterministic safety
and structure gates plus mandatory human approval (ADR-005), and unit economics cap what any one
book may cost to produce.

Two findings sharpen the challenge beyond "generate a big correct artifact cheaply":

1. **The quality defect that matters is decision regurgitation, not structural reuse.** A reader
   tracks what they were asked to decide, not the shape of the tree recording it. Two books may
   share a graph byte-for-byte and read as different adventures; two books with different graphs
   that offer the same decisions in the same order read as the same book re-skinned (2026-08-10
   brief, section 1.3; operationalized by the worked open-the-door example there).
2. **A passing gate is not quality.** The strongest recent demonstration: a live fill run delivered
   38.9-52.9% of commissioned words while every book passed the deterministic gate (`AL-490`,
   `UW-C307`). Gates are floors; quality lives above them and must be measured separately.

## 2. The framework: quality CYO books from LLMs at acceptable cost

Eight principles. Each is load-bearing in the pipeline of section 3 and earned by an analysis in
section 4; none is aspiration.

**F1. Split structure from prose, and treat them as different engineering problems.** The skeleton
(a story graph whose node bodies are `<<FILL role=... words=... beats='...'>>` directives) is
authored, validated, and reviewed separately from the prose that fills it. Everything downstream
(validation, model selection, cost control, reuse policy) depends on this split.

**F2. Deterministic gates come first, and they are floors, not scores.** Structure, budgets,
reading level, safety classification, and graph soundness are checked by code before any model or
human judges anything. Because of finding 2 above, every gate is paired with a delivery measurement
(fill rate, word delivery) so a hollow pass is visible.

**F3. Put the checker in the author's loop.** The single largest quality lever we have measured is
not model choice but authoring regime: blind generate-and-repair produced 2 strict passes in 21
attempts across seven models; the same models with permission to run the validator themselves
passed 12 of 21 at ages 5-8 and 15 of 21 at ages 10-13 (section 4.2). Structure authoring is
tool-use, not text generation.

**F4. Select models per stage, not per pipeline.** The best prose model measured (DeepSeek V4 Pro)
is the worst structure author measured (0 of 6 tool-assisted passes across two cells, with two
distinct failure modes). The cheap tier of the same family is a competent first-pass reviewer. One
model choice per book is a category error; the authoring plan needs a model per stage.

**F5. Reuse structure freely; never reuse decisions; generate the decisional layer per book.** The
stratified-plan result: topology and a bare-names fact graph can be shared across books without
measurable prose convergence (2.3 shared 4-grams per 1000, under the 4.0 budget and below the 3.3
generator idiom floor), while every prose-bearing plan layer leaks (D-6, D-7, D-7b). Per-request
single-parent mutation is refuted as a variety multiplier (S8; the per-request mutation pilot).

**F6. Trust no instrument until it survives a known-answer test, and pre-register everything.**
Our first decision-similarity vocabulary ranked book pairs opposite to readers (D-3); the
six-question rating instrument compressed to uselessness (register section A); the automated
recognition protocol failed its own control when we finally ran the validation (register `S-0`).
The instruments that survive are deterministic (solution transfer, shared-gram counts, structural
distance) plus blinded raters used to confirm, never to produce, rankings.

**F7. Engineer the cost, not just the prompt.** Measured levers, in order of impact: authoring
regime (F3 turns failed spend into passes); model tier where the regime carries quality (Haiku
authored passing hard-band shells at zero marginal cost; premium Western legs were 90% of one
comparison's bill for no additional passes); completion caps sized to reasoning overhead (a cap
below a reasoning model's hidden burn returns empty content billed as a full call, `AL-328`);
repair loops in the harness with hard round caps; and spend guards, because the one thing worse
than an expensive run is a run that dies mid-grid on an exhausted balance.

**F8. A human approves every book a child can see.** Deterministic gates and model review gate
what reaches the human; nothing replaces the human (ADR-005). Sourcing architectures are therefore
also judged on what they ask that human to review (a fill over a known-good shell versus a fill
over an unreviewed one), which is a live open question tracked as register row `S-5`.

## 3. The current pipeline

Five stages. Roles: the catalog is grown offline; a story request selects and fills a skeleton;
gates and review sit between the fill and the human who approves publication.

### 3.1 Skeleton development

- **Constraint brief.** `scripts/generate_drafting_brief.py` emits the complete constraint set for
  one production cell (band x length x style), read live from the enforced rule sources
  (`validator/band_profile.py`, `validator/policy.py`, `scripts/check_skeleton.py`), never
  hand-copied. Hand-written briefs drifted from the code twice before this existed (`AL-149`).
- **Authoring.** Today skeletons are authored in tool-assisted LLM sessions (the `cyo-author`
  skill mechanism): the author drafts the full graph with `<<FILL>>` directives and runs the
  strict checker against its own draft until it passes. Section 4.2 is the controlled measurement
  of exactly this regime.
- **Offline accelerators.** `scripts/mutate_skeleton.py` (ADR-020) mutates existing skeletons
  under an acceptance battery; `scripts/parameterize_skeleton.py` lifts a skeleton into a theme
  contract for per-request binding. Both are catalog-time tools, never in the request path.
- **Promotion.** A skeleton enters `skeletons/<band>/` only through a reviewed pull request; CI
  re-proves every changed skeleton from scratch (`.github/workflows/skeleton-promotion.yml`).

### 3.2 Skeleton checks

`scripts/check_skeleton.py --strict` is the authoring bar; `uv run` it on any shell:

- **Layer 1 structure**: schema conformance, reference integrity, reachability, termination, and
  per-cell budgets (node count, branch depth, ending count, words-per-node envelope).
- **Topology**: the declared topology must be admissible for the actual graph shape (PL-18) and
  permitted for the band (PL-29).
- **Policy and grammar**: story-mean pacing (PL-19), derived reading clock versus declared minutes
  (PL-23), ending mix (PL-24), first-decision window (PL-25), corridor density (PL-26), and the
  choice-grammar rows (CG-1 single-choice cadence, CG-3 words-per-stop).
- **Reader-experience floors**: a random-walk satisfying-ending probability floor per band, a max
  in-degree reconvergence cap, and a depth-qualified endings floor.
- **Anti-clone**: `structural_distance` against every in-cell tree must clear `TAU_CELL` (0.05,
  calibrated in `docs/planning/ws5_floor_baseline.json`).
- **Graph soundness** independent of the gate: `scripts/check_graph_structure.py` classifies six
  failure modes and repairability.

### 3.3 Story development

- **Selection.** `generation/skeleton_match.py` matches the request's cell, filters to
  production-eligible skeletons, and picks with recency weighting so a family sees the least
  recently used armature; admin override exists but warns.
- **Binding.** Theme contracts bind per-request settings, casts, and props
  (`scripts/bind_theme.py`); the differentiation directive
  (`build_differentiation_directive`) instructs the fill away from sibling books.
- **Fill.** `generation/orchestrator.py::fill_skeleton` drives a staged fill through pluggable
  providers (Anthropic, OpenRouter, Modal, Ollama), with chunked fills for large books, completion
  caps sized per model, and bounded repair attempts. Every call is metered
  (`generation/usage.py`); cost accounting is response-level where the provider reports it.

### 3.4 Story automated checks

- **Stage-1 fidelity gate** (`generation/fidelity.py`): the filled book is checked against its
  skeleton's directives before anything else runs.
- **The story gate** (`scripts/run_story_gate.py`, `validator/`): Layer 1 and Layer 2 rules,
  reading level against the band target, safety findings, and band-profile conformance. Blocking
  findings stop the book; advisories are recorded.
- **Delivery measurements**, because of F2's floor problem: `check_fill_integrity.py` enforces a
  minimum fill rate (0.6, calibrated so the `UW-C307` under-delivering books fail), and
  `check_sibling_fills.py` measures shared 4-grams against same-skeleton siblings (budget 4.0 per
  1000; production wiring of this check is open work, `UW-C315`).
- **Craft checks**: `check_prose_craft.py` (tense, told-emotion, moral tags) and the per-path
  measures used in evaluation.

### 3.5 Story LLM checks, then the human

- **Moderation pipeline** (`moderation/`): safety classifiers and fidelity review over the filled
  book; DeepSeek V4 Flash currently performs well as the deterministic-style first-pass reviewer
  ahead of costlier review (owner practice, 2026-08; the review-model distillation plan tracks
  formalizing this).
- **Evaluation-side judging** (not in the publish path): blind cross-lab panels via
  `scripts/blind_books.py` and `scripts/judge_books.py`, provenance-stripped (`AL-207`,
  `AL-226`), self-family flagged, used for experiments like the vendor comparison.
- **Human approval** (`publishing/`): a guardian or admin approves and publishes; nothing reaches
  a child without it (ADR-005). This is the stage the sourcing decision must not degrade.

## 4. What the analyses found: what works and what does not

### 4.1 Fill-stage model selection (2026-08 vendor comparison and live runs)

Six legs across five labs, backend-pinned with fallbacks disabled, blind cross-lab judging
(`docs/planning/vendor-comparison/`): model choice measurably moves prose quality, and DeepSeek V4
Pro emerged as the best judged prose at roughly a fifth the cost of the premium Western legs. The
same programme produced two cautionary results: the fp4-quantization headline did not survive
scrutiny (one bad book, not a quantization effect; README run-6), and the live fill run surfaced
the fill-rate hole (38.9-52.9% delivery through a passing gate, `AL-490`..`AL-498`), which is why
delivery floors now exist. Same-skeleton sibling fills without the differentiation directive shared
96.3 4-grams per 1000 (24x budget, `AL-498`); measuring what the directive actually buys is open.

### 4.2 Skeleton-stage model selection (register `S-1`, 2026-08-21)

Two conditions over the same premises, briefs, and strict bar. **Blind** (stateless
generate-and-repair, six-round cap): 2 passes in 21 attempts across seven legs; every family
censored at the cap almost everywhere, and the pre-registered repair-rounds endpoint was degenerate
under that censoring. **Tool-assisted** (the author may run the checker, ten-invocation cap):

| Leg | Ages 5-8 (cell A) | Ages 10-13 (cell D) |
| --- | --- | --- |
| claude-fable (subagent) | 3/3, 4-6 checker runs | 3/3, 2-3 runs |
| claude-opus (subagent) | 3/3, 5-7 | 3/3, 3-3-3 |
| claude-sonnet (subagent) | 1/3 (topology trap x2) | 3/3, 3-5 |
| claude-haiku (subagent) | 2/3 | 1/3 |
| moonshot Kimi-K3 (owner Modal endpoint) | 2/3, 7-8 | 3/3, 3-5 |
| deepseek-v4-flash (OpenRouter) | 1/3 (call budget lost to unparseable output) | 2/3, 5-10 runs |
| deepseek-v4-pro (OpenRouter) | 0/3 | 0/3 |

What works: the tool-assisted regime, for every family; frontier Anthropic tiers converge fastest
and most reliably; the hard band is not the hard part once the regime is right (capable legs
converged faster at 10-13 than at 5-8, whose tight budgets and topology trap bit harder). What
does not: blind authoring at any tier; DeepSeek V4 Pro as a structure author (0/6 tool-assisted,
failing by structural churn and by losing JSON discipline in multi-turn repair); and the checker's
PL-18 message, which cost three legs grid points by naming the admissible set without saying why
the graph is not tree-shaped (`AL-503`, fix proposed; the brief-side menu defect is `UW-C306`).
Consequence for the product: fill with V4 Pro, author structure with a tool-assisted Anthropic
tier, review first-pass with V4 Flash; per-stage model selection in the authoring plan is the
enabling change.

### 4.3 Diversity: ten designs, three levers that failed, one that stands

The S0-S9 history (2026-08-10 brief, section 4) plus this programme's follow-ups:

- **Refuted as variety levers**: theme binding and device pools (solved their own metrics,
  recognition unmoved, S3/S5/S6); model tier (recognition identical at both craft extremes, S7);
  per-request single-parent mutation (shape-preserving operators are perceptual no-ops; the only
  floor-clearing mutant grafted a second skeleton, S8 and the mutation pilot); multiple obligation
  contracts over one graph (recognition landed earlier, S9); instructing independence between
  authors (does nothing; withholding shared material works completely, M-4 series).
- **Confirmed mechanisms**: contract sharing is a convergence cause (D-6); fact-gloss prose is the
  dominant leak (D-7b: deleting 422 gloss words moved sharing from 13.6 to 2.3 per 1000); and the
  stratified plan follows: share the wordless structural stratum, generate `choice_semantics`,
  beats, devices, and stakes per book (the architecture re-specification).
- **Capital facts**: a child exhausts a cell by roughly the fourth request at 3-4 skeletons per
  cell (Q-1), so full-skeleton reuse is bounded by depth against demand; and premise convergence
  is invariant across tiers within a family (Q-3c), so premise curation is a control, not a nicety.

### 4.4 Instruments: what we can trust

Works: solution transfer (`D-4`, the only computed measure that reproduced reader orderings, and
only its taxonomy-free tier); shared 4-gram counting with its calibrated budget and idiom floor;
structural distance with calibrated floors (with its self-declared topology component split out);
provenance-stripped blind judging with self-family flags. Does not work: the DecisionSignature
vocabularies (v1 and v2 both invert against readers, D-3); the six-question instrument (pinned and
compressed scales); and the automated recognition protocol, which failed its pre-registered control
on 2026-08-21 (both raters called a cross-graph pair the same adventure, partly because the control
itself carried the catalog's convergent decision structure; repair path in
`evidence/recognition-protocol-pilot/results.md`, `AL-500`). Perceptual claims, including the
mutation pilot's, stay marked unconfirmed until a validated instrument exists.

### 4.5 Cost: where the money actually went

Deterministic accounting from run records: in the aborted premium-slate comparison, three Western
premium legs consumed 90% of spend (Sonnet 5 $4.43, Gemini $3.52, GPT-5.6-sol $3.38) against $1.30
for both DeepSeek legs across the same grid; the replacement slate ran both DeepSeek legs for
~$1.30 and four Anthropic tiers plus the harness at zero marginal provider cost as subagents. The
dominant waste modes measured: blind repair loops that cannot converge (up to 45k completion tokens
per censored attempt on a reasoning model), caps below reasoning overhead (`AL-328`), and a
mid-grid balance exhaustion (76 shells lost to HTTP 402 before spend guards existed). All three now
have countermeasures in the harness (`--resume`, preflight, credits checks, sized caps).

## 5. Status and open work

Skeleton sourcing rows `S-0`..`S-5` in the [diversity test register](./diversity-test-register.md)
carry the pre-registrations, margins, and current status of this programme; `S-2` (stratified reuse
end-to-end), `S-3` (bespoke versus catalog on premise fit), `S-4` (repeat-reader distinctness), and
`S-5` (the safety floor for unreviewed shells) are the open experiments, gated on the plan in
[skeleton-sourcing-test-plan-2026-08-21.md](./skeleton-sourcing-test-plan-2026-08-21.md). The
recognition instrument repair and the PL-18 message fix are the two cheapest quality levers on the
board. Lessons `AL-499`..`AL-503` and work rows `UW-C316`..`UW-C319` record what this cycle taught.

## Related

- [2026-08-10 research brief](./cyo-generation-research-brief-2026-08-10.md): the deep treatment
  this version builds on (defect definition, literature, S0-S9, methods)
- [Diversity test register](./diversity-test-register.md): every experiment, falsifier, and status
- [Skeleton sourcing test plan](./skeleton-sourcing-test-plan-2026-08-21.md) and
  `evidence/skeleton-author-vendors/`: the S-1 data behind section 4.2
- [Vendor comparison](./vendor-comparison/README.md): the fill-stage methodology and runs
- [Architecture re-specification](./architecture-respecification-2026-08-10.md): the stratified
  plan behind F5
