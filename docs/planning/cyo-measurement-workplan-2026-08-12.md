---
title: "Measurement workplan: what to build, how to test it, and what would make us drop it"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Turn the third, fourth and fifth external reviews into thirteen work items, each carrying a pre-registered decision rule that says what evidence would keep it and what would drop it."
tags:
  - planning
  - research
  - measurement
component: Research
source: "synthesis of docs/planning/cyo-review-response-2026-08-12.md and cyo-review-response-2026-08-12b.md"
---

# Measurement workplan

> **Date**: 2026-08-12
> **Derived from**: [third review response](./cyo-review-response-2026-08-12.md),
> [fourth and fifth review response](./cyo-review-response-2026-08-12b.md)
> **Status**: draft, pending owner sign-off. Register rows are added on sign-off, not before.

## 0. How an item earns its place

Every item below carries a **decision rule written before the work runs**. This is not ceremony. Six
of the thirteen items are cheap enough that they will get built regardless, and an item that is
already built is included by default unless something can say no to it. The rule is the thing that
can say no.

Three constraints on how rules are written here:

1. **A rule must be able to return "drop".** If no plausible measurement outcome would remove the
   item, it is not a candidate and should be marked infrastructure instead. Three items below are
   marked that way honestly rather than dressed up as candidates.
2. **A rule may not appeal to the judge panel until the judge panel is validated.** Section 32 of
   the brief and all three reviews agree the instrument is unvalidated. Any item whose rule needs a
   quality score is blocked on **W7**. Items whose rules need only a deterministic count are not,
   and that split is what makes most of this plan runnable now.
3. **A metric is not promoted to a blocking gate on the strength of being computable.** That is the
   mistake `AL-337` records. Deterministic measures enter as *reported statistics* first; promotion
   to a rule that blocks a book requires evidence that a reader is affected.

## 1. Sequencing

Three tracks. Only one of them is blocked on anything.

```text
Track D (deterministic, runnable now, no judge, no human)
  W1 path enumerator ──┬── W2 per-path re-unit
                       ├── W3 consequence distance
                       └── W6 blind-spot manifest ── W15 declared information state
  W4 instrument variance      (independent)
  W5 bootstrap intervals      (independent)
  W8 decoding/effort ablation (scored deterministically, so not blocked on W7)
  W9 cross-stage routing      (output is cost, which is a fact not a ranking)
  W10 MoPS premise pool       (scored against the 156.35 convergence figure)
  W14 context composition     (blocked on UW-C239: input rates are all None today)

Track J (judged)
  W7 known-bad battery ──> every ranking-shaped claim, W11 pilot scoring, best-of-N

Track H (human, ~$300, settles constructs nothing else can)
  W12 child + adult read ──> promotes or retires W3's gate, settles requirement 2's construct
  W13 age-appropriateness rubric (rides with W12)
```

The load-bearing observation: **W8, W9 and W10 all have deterministic decision rules, so none of
them waits for the instrument.** Previous plans assumed the opposite and would have idled three
cheap experiments behind one expensive one.

## 2. Track D: deterministic work

### W1. Path enumerator and its sampling rule

**Infrastructure, not a candidate.** Five items depend on it.

*Build.* `validator/paths.py`, over `WalkResult.edges` from `walk_configurations`. Two outputs, kept
separate and never pooled:

- a **covering set**: a set of root-to-ending paths that traverses every reachable edge at least
  once, so no fork escapes measurement. Greedy, not minimal: a path is kept whenever it covers
  something new, and no attempt is made to find the fewest such paths. `edge_coverage` is the
  result; `len(paths)` is incidental;
- a **reader sample** of n paths under a fixed seed, drawn uniformly over the *choices* visible at
  each fork rather than uniformly over paths, because the former is the distribution an actual
  reader draws from and the latter is not.

They answer different questions. Covering answers "is any path bad"; sampling answers "is a typical
path bad". Reporting one as the other is the failure mode to guard against.

*The real difficulty.* Root-to-ending path count is exponential in fork count even when
`walk_configurations` caps *configurations*. `WalkResult.capped` must propagate into every derived
statistic, and a capped walk must make the derived metric report "incomplete", not a number.

The corollary, learned by shipping the wrong thing first: **enumerate-and-filter cannot build a
covering set.** Depth-first enumeration under a path budget spends the whole budget inside whichever
subtree it entered first, then reports an honest and useless coverage number (30 percent on a real
catalogue title, with every unit test green). The covering set must be *constructed* per target,
shortest-route-in plus the choice plus shortest-route-out over the configuration graph, which makes
coverage independent of search order and of how many readings the book admits.

*Test.* Hand-built fixtures: a linear book (one path), a diamond (two), a reconverging spine with a
carried flag (state-dependent path count). Assert the covering set touches every edge; assert the
sample is byte-identical under a fixed seed; assert `capped` propagates and suppresses the number
rather than shrinking it. Mutation check: delete the `capped` propagation and a test must fail.

*Decision rule.* Feasibility only. **Ship if the covering set computes in under 2 seconds for a
101-node ceiling-scale book.** If it does not, ship sampling alone and record that per-fork coverage
is not guaranteed, because a silently partial covering set is worse than an admitted sample.

*Outcome (2026-08-12): shipped with both modes.* Measured over all 61 skeleton-catalogue books:
61/61 at `edge_coverage == 1.0`, 61/61 `complete`, 2.666 s for the whole catalogue. The 101-node
ceiling-scale book in the decision rule takes 0.001 s; the largest book in the catalogue (677 nodes)
takes 0.917 s. The rule is met with about three orders of magnitude of headroom, which is a property
of the redesign rather than of tuning: cost now scales with the configuration graph, not with the
reading count.

*Cost.* Zero spend, roughly a day.

### W2. Re-unit existing metrics from book to path

*Build.* No new metrics. Call `reading_level.measure_book` and the `check_prose_craft` functions
(dialogue share, tense breach rate, told-emotion rate, moral tags) with a path's bodies instead of a
book's. `measure_book` already takes `Iterable[str]`, so this is a caller change.

*Test, and it is the decision.* Run over the existing book corpus, which is already paid for. For
each measure compute the within-book spread across paths.

*Decision rule.* **Keep a per-path measure iff it disagrees with its book-level parent often enough
to change a verdict: for at least 10 percent of books, one path falls outside the acceptable band
while the book aggregate falls inside, or the reverse. Otherwise the book aggregate is a sufficient
statistic and the per-path version is complexity bought for nothing, and it is dropped.**

This rule can genuinely return "drop", and it is the reason to run W2 before W3 and W6: if per-path
measurement turns out to be redundant, two of the three reviews' central recommendation is wrong on
our corpus and we should say so rather than build on it.

*Outcome (2026-08-12): mixed, and the rule needed a directional refinement to be usable.*

Corpus: 60 filled books (`out/*.filled.json`, the non-dry `out/vendor-comparison/run-*/books/`,
and the two mutation pilot books). 53 measured; 4 skipped for retained `<<FILL` residue (the same
four `AL-335` found) and 3 skipped because they fail `Storybook.model_validate` on
`metadata.topology`, an older schema version. Paths are the W1 covering set, which is the right
set for "is any reading bad".

| measure | book in, path out | book out, path in | either | share | median within-book path spread |
| --- | --- | --- | --- | --- | --- |
| reading level (FK grade vs `target ± tolerance`) | 7 | 3 | 10 | **18.9%** | 0.878 grades |
| told-emotion (per 1000 narration words, band 0.5) | 6 | 1 | 7 | **13.2%** | 0.000 |
| tense instability (unstable nodes, band 0) | 0 | 2 | 2 | 3.8% | 0.000 |
| moral tags (count over endings, band 0) | 0 | 9 | 9 | 17.0% | 0.000 |

**Reading level: keep.** Clears the bar bidirectionally, and the disagreement is not
small-denominator noise: the disagreeing paths run 364 to 969 words over 5 to 12 nodes. The
mechanism is sound. The book aggregate is length-weighted over every node, so it systematically
understates the hardest single reading; `sk_night_market` measures 3.50 whole-book inside a 1.0-4.0
band while one covering path measures 4.03, and `sk_school_garden_mystery` 4.07 against a path at
5.09. This is the concentration effect the reviews predicted, and it is the one place we have
evidence for it.

**Told-emotion: keep the unit, re-derive the threshold before using it.** The 13.2% is real
disagreement but it is evidence about the threshold rather than about per-path sensitivity. All six
book-passes-path-fails cases are exactly `k x 1000 / path_words`, the smallest nonzero rate each
path length admits (1075 words to 0.930, 570 to 1.754, 1856 to 0.539, 643 to 1.555, 536 to 1.866,
and 1187 to 2.527 at k=3). The 0.5 band was calibrated on books of 2,344 to 24,601 words; on a
600-word path a single hit already scores 1.67, so the band never binds and the measure degenerates
from a rate into "does this path contain a told-emotion phrase at all". Either re-derive the band at
path scale or express the path-scope version as a count with a path-appropriate allowance.

**Tense instability: drop.** 3.8%, below the bar, and both disagreements point the weaker way.

**Moral tags: drop, despite a literal 17%.** Every one of the nine disagreements is
book-fails-path-passes, and that is structural rather than incidental: a path's ending set is a
subset of the book's, so a path's moral-tag count can never exceed the book's. A per-path check here
can only ever pass books the book-level check fails, which is a laxer gate, not a more sensitive
one.

*Rule refinement, applied above and carried forward to W3 and W6.* The rule as written counts
either direction of disagreement as evidence. For any measure that is monotone under path-subsetting
(a count over a subset of nodes or endings), the book-fails-path-passes direction is dilution, not
sensitivity, and must not count toward the 10 percent. Before applying the rule to a new measure,
ask whether the path-scope value can exceed the book-scope value at all; if it cannot, the per-path
version is weaker by construction and the rule should not be run.

*Cost.* Zero spend. Blocked by W1.

### W3. Consequence distance per fork

*Build.* For each decision node, walk both branches to their reconvergence point. Record distance in
nodes and the set of state flags that differ on arrival. A fork reconverging in one node with an
identical state is a false choice.

*Test.* Fixtures for each shape: false choice (distance 1, empty state delta), real choice
(distance 8, two flags differ), never-reconverging fork, and a fork whose branches reconverge only
under one condition. Then run over the shipped catalogue.

*Decision rule, in two stages.* Stage one, now: **report it as a statistic, and keep it iff it
discriminates on our own catalogue.** If nearly every fork in every shipped book is a false choice,
that is a finding worth acting on immediately. If nearly none is, the measure has no discriminating
power here and parks until the corpus changes. A measure that returns the same verdict for every
book is measuring nothing, which is exactly how the dialogue criterion failed.

Stage two, later: **promotion to a blocking validator rule requires W12.** `BandProfile` already has
an unenforced `reconvergence_ceiling` field waiting for a number, and we will not invent that number
from a measure no reader has been asked about. This staging is the direct application of `AL-337`.

*Cost.* Zero spend. Blocked by W1 for the path context; the fork walk itself is graph-local.

### W4. Per-criterion instrument variance

*Build.* For every judge run, compute each criterion's standard deviation across cells and flag any
criterion whose spread is below a threshold as saturated.

*Test, and it is a known-answer test.* Replay the existing 84-verdict pool. **The check must flag the
dialogue criterion**, whose mean was 3.04 at SD 0.19 across twelve cells while deterministic parsing
found one leg at 100 percent narration. We found that by accident; the check must find it on purpose.

*Decision rule.* **Keep iff it flags the dialogue criterion and does not flag criteria we have
independent reason to believe are working.** A check that flags everything is as useless as one that
flags nothing, so both failure directions are tested.

*Cost.* Zero spend, half a day. Independent of everything.

### W5. Bootstrap intervals on ranked quantities

*Build.* Resample books within each cell; report an interval alongside every mean currently
presented as a rank.

*Test.* Assert interval width shrinks as n grows; assert a synthetically separated pair reports
non-overlapping intervals; assert a synthetically identical pair overlaps.

*Decision rule.* **Infrastructure, not a candidate: reporting uncertainty is a correction, not a
feature.** But the consequence is a decision we pre-commit to now: **if the intervals overlap across
the whole supplier slate, Part IV's ranking is retracted rather than caveated.** At single-digit n
per cell that is the likely outcome, and agreeing to it in advance is the point of writing it here.

*Cost.* Zero spend, half a day.

### W6. Gate blind-spot manifest

*Build.* Each checker declares the dimensions it observes. The gate emits the complement: the set of
dimensions on which *every* constituent checker abstained, alongside its verdict.

*Test, including the one that decides the design.* Assert it names the qualitative
age-appropriateness dimensions as unobserved (the `AL-337` case) and, with PL-27 disabled, names
filled-prose as unobserved (the `AL-325` case). Then the decisive test: **mutate a checker so it
stops checking something, and require the manifest to notice.**

*Decision rule.* **Keep iff the declaration cannot drift from behaviour.** If the manifest is a
hand-maintained constant per checker that the mutation test cannot catch going stale, drop it: a
manifest that lies is worse than no manifest, because it converts an unknown blind spot into a
false assurance, which is the exact harm `AL-337` describes. If it cannot be made drift-proof, fall
back to a documentation-only list with no machine-readable claim attached.

*Cost.* Zero spend, one to two days.

### W8. Decoding and reasoning-effort ablation

*Build.* Vary temperature, top-p and reasoning effort across a small grid on one fixed brief and
skeleton set. Never done once in the whole programme.

The sixth review supplies the grid this item previously left unspecified, and it is adopted as the
starting point: prose at (0.7, 0.9), (0.9, 0.95), (1.0, 1.0) and (1.1, 1.0); planning at 0.3 to 0.7;
premise generation at 0.8 to 1.0. One correction to it. The same review reports the vendor model
card recommending temperature 1.0 with top_p 1.0 for maximum reasoning, which its own planning rows
at 0.3 to 0.7 sit well below. **Carry the vendor-recommended point as an explicit baseline cell at
every stage**, so a low-temperature planning result is measured against the card rather than
quietly replacing it. The card reading is confirmed: the DeepSeek-V4-Pro and V4-Flash model cards
both recommend temperature 1.0 with top_p 1.0 (verified 2026-08-12), so the baseline cell is a real
vendor position rather than a paraphrase.

*Test.* Score **only on deterministic measures**: shared four-gram convergence, leaf diversity, gate
pass rate, cost per delivered book. This is what lets it run before W7.

*Decision rule.* **Adopt a parameter change into the production config iff it moves a deterministic
measure beyond that measure's own noise floor**, where the noise floor is the generator's measured
idiom floor of 3.3 per 1000 for convergence and a re-run spread for the others. **Explicitly do not
adopt on a judge score**, whatever the judge says, until W7 clears.

*Cost.* $10 to $20.

### W9. Cross-stage model routing

*Build.* Route the structure stage to a reasoner and the prose stage to a cheap fast model. The
repair tier already exists as `generation/reading_level_loop.py`.

*Test.* Cost per delivered book and gate pass rate, against the current single-model configuration
on matched briefs.

*Decision rule.* **Adopt iff cost per delivered book falls materially with no regression in gate
pass rate or deterministic craft measures.** Cost is a fact rather than a ranking, so this is not
blocked on W7. Note the fifth review's recommended model names are stale; the tiering transfers and
its instantiation does not, so the slate is chosen from current models at run time.

The sixth review's staged allocation is the same tiering at finer grain and is adopted as this
item's slate shape rather than as a new item: highest reasoning for premise, character and
whole-book review; middle reasoning for graph and scene plans; middle or fast for prose; a
non-reasoning or local model for JSON normalisation. Model names are again deliberately not fixed
here. The normalisation tier is the one rung with an independent justification already on file:
`UW-C233` records a fill returning no parseable document seeding the repair loop with the unfilled
skeleton, which is structurally valid by construction and therefore certified. **A deterministic
parse-and-repair step is the cheaper answer to that defect than a local model**, and W9 should
measure the deterministic option before spending a routing rung on it.

*Cost.* One matched run, comparable to a vendor-comparison leg.

### W10. MoPS premise pool

*Build.* Verify the citation first (section 5.3 of the fourth/fifth review response). Then enumerate
orthogonal premise modules, sample algorithmically, and generate.

*Test, and it is the cleanest in this plan, because the comparator already exists.* Same-brief
cross-lab premise convergence currently measures **156.35 shared four-grams per 1000**, against a
generator idiom floor of **3.3**. Generate n books from MoPS-sampled premises and measure the same
quantity the same way.

*Decision rule.* **Adopt iff convergence drops to within a small multiple of the 3.3 idiom floor.
Drop if it stays in the tens per 1000**, because a curated space that still converges is not solving
the problem it was chosen for. This is deterministic, pre-registered, and unambiguous.

*Cost.* Generation for n books, plus curation time for the module dictionary.

### W14. Context composition

*Source.* Sixth review, experiment C, which flags its own central claim as expert judgment rather
than measurement: that a compact state ledger plus the relevant path beats passing the whole graph.
That is the correct reason to test it and the wrong reason to adopt it.

*Why it is here at all.* W8 varies decoding, W9 varies which model, W10 varies the premise. Nothing
in this plan varies **what each stage is given**, and on a 1M-context model that is a first-order
lever on both quality and cost. It is the one axis the programme has never moved.

*Build.* Three context regimes for the prose stage on a fixed brief and skeleton set: the whole
graph as passed today; the current node plus its ancestors on the path being written; and a compact
state ledger (accumulated flags, characters introduced, facts established) plus that path. Vary
nothing else.

*Test.* Deterministic only, so it runs before W7: gate pass rate, shared four-gram convergence
against the 3.3 idiom floor, leaf diversity, and cost per delivered book split into input and output.

*A confound this item must hold fixed, found while verifying the review's figures.* The DeepSeek-V4
model card states a **384K minimum context window for its Think Max reasoning mode** (verified
2026-08-12 on the V4-Pro card). Context composition and reasoning effort are therefore not
independent variables on this model: an ablation that shrinks the configured window along with the
prompt would silently drop out of Think Max, and the result would read as "less context, worse
book" when the actual cause is "less reasoning". **Hold the configured context window fixed at or
above 384K across all three regimes and vary only what the prompt contains.** If a regime cannot be
run that way, report it as a different experiment rather than as a fourth cell.

*Blocked, and the blocker is ours.* Half of this item is a cost measurement over input tokens, and
`core/pricing.py` sets `input_usd_per_mtok=None` on every cloud entry, so `estimate_cost` marks every
row incomplete (`AL-333` / `UW-C239`). **Close UW-C239 before running W14** or the cost half is
unmeasurable and only the quality half survives.

*Decision rule.* **Adopt a regime iff it moves a deterministic measure beyond that measure's noise
floor, or holds every deterministic measure flat while reducing measured input cost.** The second
clause is the point: a context regime that changes nothing about the book and costs less is a win on
cost alone, which is a fact rather than a ranking. **Drop the whole item if all three regimes sit
inside the noise floor on every measure**, which would say context composition is not a lever here
and would retire the review's expert-judgment claim on our corpus.

*Cost.* One matched run per regime, comparable to a vendor-comparison leg.

### W15. Declared information state as a deterministic instrument

*Source.* Sixth review's scene state packet, inverted. The review proposes it as a generation
artifact, and in that form it is the architecture layer this plan already deferred. The half worth
having is the measurement half: a node that *declares* what it withholds can be checked for whether
the prose leaks it.

*Why this is not the deferred planner.* `AL-337` says the four qualitative age-appropriateness
dimensions are observed by nothing in the pipeline, and section 5 of this plan rejects inventing
deterministic proxies for them. This is not a proxy. It is a checker over an author-declared
contract: the packet's `unknowns_to_preserve` states an intent, and leak detection tests compliance
with that stated intent rather than guessing at an unstated construct.

*Build.* Extend the skeleton node schema with an optional `unknowns_to_preserve` list (entities,
facts or relationships the node must not reveal). Add a checker that fails a filled node whose prose
names any of them. Author the field on a small set of catalogue nodes rather than the whole tree.

*Test.* A node declaring a withheld fact whose fill states it plainly must fail; the same node whose
fill withholds it must pass; a node declaring nothing must be unaffected, so the field's absence is
never a finding. Then the decisive one, mirroring W6: **a fill that reveals the fact through an
obvious synonym or paraphrase must also fail, or the checker is a substring match wearing the
language of an information-state check.**

*Decision rule.* **Keep iff the paraphrase test passes and the false-positive rate on already-shipped
catalogue nodes is zero.** If it only catches literal restatement, drop it and record that the
information-state dimension stays uninstrumented, because a checker that catches only the naive case
and reports clean otherwise is the `AL-337` harm rather than its fix. **Reported statistic first;
promotion to a blocking rule requires W12**, per admission rule 3.

*Cost.* Zero spend. Blocked by W6, whose declaration mechanism this rides on.

## 3. Track J: the blocking item

### W7. Known-bad battery for the quality panel

**This is the blocking item and it should start first among the judged work.**

*Build.* Take real books that currently pass and seed one known defect each: flatten dialogue to
zero, break narrative tense in a third of nodes, replace a real fork with a false choice, raise
reading level by three grades, duplicate a sibling book's premise. Keep an unmodified control arm.

*Test.* Run the existing panel blind over seeded and control books. Per criterion, compute detection
rate on its own defect and false-positive rate on the control.

*Decision rule, per criterion rather than per panel.* **Retire any criterion that fails to detect
its own seeded defect, or that fires on the clean control.** Agreement is scored against our existing
floor of **kappa 0.60**, cited to Landis and Koch (1977), and explicitly **not** the fifth review's
proposed 0.80, which sits in the "almost perfect" band that human raters routinely miss (see the
review response, section 5.4).

We already know one criterion this will retire: the dialogue criterion scored 3.04 at SD 0.19 while
one leg contained no dialogue at all. If the battery does not retire it, the battery is broken.

*What it unblocks.* Every ranking-shaped claim, W11's scoring, and best-of-N.

*Cost.* Judge calls over roughly 20 to 30 books. Modest.

## 4. Track H: the referee

### W12. Child and adult-expert read

*Build.* A read protocol over a small matched set, with a questionnaire covering four things rather
than one:

1. enjoyment and completion;
2. **familiarity and comfort with repetition**, which is the series-contract question the fifth
   review raised and which decides whether requirement 2's construct is monotone or inverted-U;
3. whether choices felt consequential, which is what promotes or retires W3's gate;
4. comprehension, which is the age-appropriateness question `AL-337` opened.

*Decision rule.* **This item is the referee, not a candidate.** It does not get a keep/drop rule; it
issues them. Specifically it settles: whether `reconvergence_ceiling` gets a number, whether
requirement 2 is reformulated, and whether the qualitative age dimensions need instrumenting at all.

*Cost.* Roughly $300 for the adult-expert half. The child half is a protocol and consent question
before it is a money question, and it must be scoped against ADR-018 before anything is scheduled.

### W13. Age-appropriateness rubric

Rides with W12. A human-rater rubric over the qualitative dimensions, **not** a set of deterministic
proxies. Section 3.2 of the review response gives the reasoning: writing four more formulas that
proxy for dimensions no formula observes recreates `AL-337` rather than closing it.

*Decision rule.* **Build the rubric only if W12's comprehension results show band-appropriate books
failing readers.** If comprehension tracks Flesch-Kincaid closely, the quantitative leg was
sufficient after all and the honest outcome is to say so and stop.

## 5. Deferred, with the reason

| Item | Source | Why deferred |
| --- | --- | --- |
| W11 prose-first (DSR) pilot | 5th review | Real, but its scoring needs W7. Design note held: the pilot must measure what happens when the slicer *cannot* find cut points respecting reconvergence and conditions, since the proposal assumes that away |
| Best-of-N at pivotal forks | 3rd, 4th, 6th | Selects on the instrument by construction. Strictly after W7. The sixth review re-proposes it three times under new names (candidate generation at high-leverage nodes, a local story-quality selector, a Tinker preference model); all three select or train on a quality score and all three are the same deferral. Training is the worse form: `W4` exists because the dialogue criterion returned 3.04 at SD 0.19 while deterministic parsing found one leg at 100 percent narration, and a preference model fitted to that pool launders a saturated instrument into weights, where it is far harder to detect than in a score column |
| Fine-tuning anything on the Thinking Machines credit | 6th | **Premise verified 2026-08-12** against `https://tinker-docs.thinkingmachines.ai/tinker/models/`: the catalogue lists DeepSeek-V3.1 at $3.718/MTok and Qwen3-8B at $0.44/MTok, and contains **no DeepSeek-V4 variant of any kind**, Pro or Flash. The credit therefore cannot produce a V4 adapter, so every Tinker item is really "train a different, smaller companion model", a different proposition with a different value case and one nothing in this plan currently needs. Independently, most Tinker uses proposed are the selector deferral above |
| Character-causal planner, consistency checker | 4th | Architecture layer, which section 32.2 shows is the layer we already understand best |
| Illustrated and read-aloud track | 4th | Product scope, not a research question |
| Kappa > 0.80, Z > 1 deprecation | 5th | Rejected, not deferred. Our floor is cited and theirs is not |
| Deterministic age-appropriateness proxies | inferred | Rejected, not deferred. Building them is the `AL-337` failure, not its fix |

## 6. What a "final version" decision looks like

At the end of Track D we expect to be able to say, for each of W2, W3, W4, W6, W8, W9, W10, W14 and
W15, either "included, and here is the measurement that kept it" or "dropped, and here is the
measurement that removed it". W1 and W5 ship as infrastructure. W7 changes what the judge panel contains rather
than being kept or dropped itself. W12 and W13 decide the two construct questions that no amount of
deterministic work can settle.

The outcome we should be least surprised by, and are pre-committing to accepting: **W2 returns
"drop" and Part IV's supplier ranking is retracted by W5.** Both are live possibilities on the
evidence we have, and a plan that cannot produce them is not a plan, it is a build order.

---

## 7. Status as of 2026-08-13, and the order the rest should run in

> Written against `feat/reading-level-repair-loop` at `20dec2e5` (PR #708, open). Section 2's
> per-item *Outcome* notes stay authoritative for W1 and W2; this section is the whole-plan view
> and the running order, and it is meant to be edited in place as items close.

### 7.1 Where the fifteen items stand

| Item | Track | Built | Run | Blocker |
| --- | --- | --- | --- | --- |
| W1 path enumerator | D | yes, `validator/paths.py` | yes, 61/61 books at coverage 1.0 in 2.666 s | none, shipped |
| W2 re-unit to path | D | measurement only, no committed script | yes | told-emotion needs `UW-C244` before its verdict stands |
| W3 consequence distance | D | no | no | W1 (met) |
| W4 criterion variance | J-adjacent | yes, `judge_books.criterion_spread` | no | needs the verdict pool, see 7.4 |
| W5 bootstrap intervals | D | yes, `scripts/instrument.py` | no | needs the run artifacts, see 7.4 |
| W6 blind-spot manifest | D | no | no | none |
| W7 known-bad battery | J | no | no | none, and it blocks Track J entirely |
| W8 decoding ablation | D | no | no | Tier 0 below |
| W9 cross-stage routing | D | no | no | Tier 0 below |
| W10 MoPS premise pool | D | no | no | Tier 0 below |
| W11 prose-first pilot | deferred | no | no | W7 |
| W12 child + expert read | H | no | no | ADR-018 consent scoping |
| W13 age rubric | H | no | no | W12 |
| W14 context composition | D | no | no | `UW-C239`, plus Tier 0 |
| W15 declared information state | D | no | no | W6 |

Two of fifteen are closed. `band_profile.py` still carries `reconvergence_ceiling` unenforced, and
no `unknowns_to_preserve` field exists anywhere, so W3 and W15 are untouched rather than partial.

W4 and W5 are built but not decided, and the distinction is the whole point of this plan: each now
computes on demand, and neither has been pointed at the real pool, so neither has returned the
evidence its rule asks for. Both are wired into `scripts/judge_books.py`, which grew a
`--judgements` replay mode so a finished pool can be re-analysed with no network call and no cost.
That mode is what W4's rule means by "replay the existing 84-verdict pool".

### 7.1.1 A blocker found while wiring them, and fixed here

The panel could not have scored a single book. `GenerationProvider.complete` returns a `Completion`
rather than a `str` since #701, and `judge_books.judge_book` handed that object straight to a parser
that runs a regex over it. The broad handler one line below turns the resulting `TypeError` into a
per-book recorded failure, so the panel would emit an empty scorecard and report all three judges
contributing nothing, which reads as an unlucky run against flaky endpoints. Every provider stub in
the panel's tests returned a bare `str`, so the suite asserted against a contract that no longer
existed, and no gate type-checks `scripts/`. This is the same defect PR #708 fixed at the
reading-level loop's own call site, missed in the sibling script the same branch introduced.
Recorded as `AL-351`, with the coverage gap that hid it as `AL-352` and `UW-C248`.

Consequence for sequencing: **W7 and any judged work were blocked and nobody knew.** The fix is on
this branch with a regression test that drives a real `Completion`.

### 7.2 Tier 0: harness repairs that precede any further paid run

This tier is not in section 2, because these are not candidate measures. They are the register rows
this branch filed, and each one silently corrupts a deterministic measure that W8, W9, W10 and W14
are scored on. Run-6 is the demonstration rather than the hypothesis: one book whose repair was
discarded moved a leg mean 22 points and was written up as a quantisation effect.

| Row | What it corrupts |
| --- | --- |
| `UW-C233` | an unparseable fill returns the skeleton and the gate certifies it `passed`, so gate pass rate counts total failures as successes |
| `UW-C230` | `fill_skeleton(settings=...)` disarms the Stage 1 fidelity gate for the comparison harness, and nothing in the outcome records which gate ran |
| `UW-C240` | the diversity verdict is gated on schema validity rather than content completeness |
| `UW-C247` | `discarded_for_gate` reaches no caller and no artifact, so a silently degraded book is indistinguishable post hoc |
| `UW-C246` | no drop-worst column, so one book can again become a property of the variable under test |
| `UW-C245` | no pre-flight refusal when a field the run exists to populate is structurally unpopulable |
| `UW-C234`, `UW-C235` | `max_tokens` is not reported as a measured condition and `finish_reason` is not surfaced, so a budget failure and an empty endpoint look alike |

**Rule for this tier**: no item in Tier 3 is worth its spend until every row above is closed, because
each of them can produce the effect the item is looking for.

### 7.3 Running order

1. **W4 and W5 first.** Both are now built, so what remains is one command each against a real
   `judgements.json`:

   ```bash
   uv run python scripts/judge_books.py --judgements out/vendor-comparison/evaluation/judgements.json
   ```

   Zero spend, no network call. W4's rule is met if the run flags `dialogue` and leaves the
   criteria we believe are working unflagged; W5's pre-registered consequence fires if the printed
   pair count is zero, in which case the ranking is retracted rather than caveated. Running this
   before more legs are bought decides whether that spend buys a finding or decoration.
2. **Tier 0**, in the order above.
3. **W3, W6, W15, and the W2 re-run** for told-emotion once its band is re-derived at path scale.
4. **W7**, which unblocks every ranking-shaped claim. Note that the known-bad battery already on
   file (brief section 20) validates the *diversity* metric, not the panel; W7 needs its own seeded
   corpus. `scripts/check_annotator_agreement.py` and `scripts/blind_books.py` supply the agreement
   and blinding legs.
5. **W8, W9, W10, W14**, the paid ablations, W14 last because `UW-C239` gates its cost half.
6. **W12 and W13.**

### 7.4 Five gaps in the plan itself

1. **Nothing measures the thing this branch built.** Stage D drives reading grade into band. Section
   31 of the brief puts compliance against judged quality at rho +0.50, so in-band is related to good
   and is not the same as it. No item asks whether the repair loop trades voice for compliance, and
   that question only became load-bearing when Stage D started shipping. It wants a pre-registered
   rule of its own before the loop's parameters are tuned on anything.
2. **W1's output has no caller.** `covering_paths`, `reader_sample_paths` and `path_bodies` are
   imported by nothing outside `validator/paths.py` and its tests. W2's measurement was run ad hoc
   and no committed script reproduces it, so the W2 table cannot be regenerated and the five items
   that depend on W1 will each rebuild the same plumbing.
3. **The measurement artifacts are not in the repository.** `out/vendor-comparison/` is untracked and
   is not in `.gitignore` either. The vendor-comparison README instructs anyone quoting the fp4 leg
   to use 0.89 rather than 0.70, but `evaluation.json`, the file that correction was computed from,
   exists only on the machine that ran it. W4's decision rule says to replay the existing 84-verdict
   pool and W5 resamples books within each cell; **both are implemented and neither can be run by
   anyone but the machine holding the artifacts.** Decide between committing the frozen artifacts
   and accepting that both items are single-machine. This is the one blocker on section 7.3 step 1,
   and it is a `git add` rather than a measurement.
4. **The W5 pre-commitment interacts with sample size.** At four books per leg, overlapping intervals
   across the slate are the likely outcome, and the plan pre-commits to retracting rather than
   caveating. That is the right commitment and it should be made before more legs are bought.
5. **The `AL-343` monotonicity precondition is documented, not enforced.** W3 and W6 are told to
   inherit it. Nothing makes them.

### 7.5 One note on PR #708 itself

`CI (Python 3.14) / Unit Tests` is red on `20dec2e5`, taking `CI Gate` with it, and the workflow API
surfaces only the security agent's post-steps rather than the pytest output. The full unit suite is
green on that same commit locally: 7530 passed, 6 skipped, 3 xfailed in 9m27s, matching the PR
description. A re-run is the cheap first move before anything is diagnosed.
