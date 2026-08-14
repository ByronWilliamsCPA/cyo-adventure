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
dialogue criterion**, whose per-leg cell means were 3.00 for seven of eight legs and 3.25 for the
eighth (`AL-330`), a spread of **0.088**. We found that by accident; the check must find it on
purpose.

*Correction, 2026-08-13.* This rule previously read "mean 3.04 at SD 0.19 across twelve cells",
which spliced two different instruments: the 0.19 is section 29's spread across all 84 individual
verdicts, and "twelve cells" comes from section 16m's six-question diversity rubric over 3 rounds by
4 cells. `criterion_spread` averages books into `(leg, judge)` cells before taking a spread, so on
the real pool it returns 0.088. The decision is unchanged, 0.088 still clears the 0.25 threshold,
but a replay pinned to 0.19 would have sent someone hunting a bug in a working function.

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

*Removed 2026-08-13.* This paragraph previously read "We already know one criterion this will
retire ... If the battery does not retire it, the battery is broken." That pre-commits the verdict,
and a seed that silently fails to land yields an arm byte-identical to its control, a detection rate
of zero, and exactly the pre-registered reading. The battery would then have measured the fixture
while this sentence read the result as an instrument verdict. The rule above stands on its own: a
criterion is retired by failing to detect its own seeded defect, and the seed has to be shown to
have landed first.

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
| W2 re-unit to path | D | yes, `scripts/measure_per_path.py` | yes, twice | **closed**: told-emotion band is inert at path scale |
| W3 consequence distance | D | yes, `validator/consequence.py` | yes, 61-book catalogue | **KEEP as a reported statistic** |
| W4 criterion variance | J-adjacent | yes, `judge_books.criterion_spread` | no | needs the verdict pool, see 7.4 |
| W5 bootstrap intervals | D | yes, `scripts/instrument.py` | no | needs the run artifacts, see 7.4 |
| W6 blind-spot manifest | D | yes, `validator/blind_spots.py` | yes | **KEEP**: declarations are drift-proof by witness |
| W7 known-bad battery | J | no | no | none, and it blocks Track J entirely |
| W8 decoding ablation | D | no | no | `UW-C239` (pricing) |
| W9 cross-stage routing | D | no | no | `UW-C239` (pricing) |
| W10 MoPS premise pool | D | no | no | `UW-C239` (pricing) |
| W11 prose-first pilot | deferred | no | no | W7 |
| W12 child + expert read | H | no | no | ADR-018 consent scoping |
| W13 age rubric | H | no | no | W12 |
| W14 context composition | D | no | no | `UW-C239` |
| W15 declared information state | D | probe only, in tests | yes | **DROP**: catches no paraphrase |

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

**Closed 2026-08-13.** All eight rows are `done`; the table below is kept as the record of what
each one corrupted, since the next paid run's results have to be read against it.

| Row | What it corrupted | How it closed |
| --- | --- | --- |
| `UW-C233` | an unparseable fill returned the skeleton, so a total failure counted as a delivered book | `fill_skeleton` never returns its own input; verdict taken regardless of the gate |
| `UW-C230` | `settings` alone armed the Stage 1 gate, so three harness scripts ran ungated against the same `status` field | explicit `stage1_gate` posture, stamped on every outcome report |
| `UW-C240` | the diversity verdict participated any book that parsed | participation is content completeness; exclusions named; median beside every mean, and a verdict the two disagree on is refused |
| `UW-C247` | Stage D's discard and partial salvage reached no artifact | `nodes_dropped` and `degraded` on the result and in `books.jsonl` |
| `UW-C246` | no drop-worst column, so one book could be a property of the variable | drop-worst column plus a one-sd mover flag |
| `UW-C245` | no refusal when a column the run exists to populate cannot be | `unpopulable_fields` refuses; per-book metering now populates cost |
| `UW-C234` | the cap was not reported as a condition | cap on every row, mixed-cap warning, fill rate suppressed with no headroom |
| `UW-C235` | a budget failure and a dead endpoint looked alike | `finish_reason` and `reasoning_tokens` surfaced; a truncation is no longer retried |

**Rule for this tier**: no item in Tier 3 is worth its spend until every row above is closed, because
each of them can produce the effect the item is looking for. That condition is now met.

**One thing this surfaced, and it is a real blocker rather than a side effect.** `UW-C245`'s refusal
fires on every live slate today, because no cloud entry in `core/pricing.py` is fully priced: every
one sets `input_usd_per_mtok=None` (`AL-333` / `UW-C239`). That is the correct reading rather than an
accident, and `--allow-unpriced` is the deliberate override, but it means **`UW-C239` is now on the
critical path for every paid item, not just W14.** Prices were deliberately not invented here; the
vendor-comparison README carries measured per-MTok rates from the 2026-08-12 billing probe, and
seeding the table from them is a decision for the owner because the cached legs' figures are
effective rather than list rates.

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
2. ~~**Tier 0**, in the order above.~~ **Done 2026-08-13**, except that it promoted `UW-C239`
   (populate `core/pricing.py`'s input rates) into a blocker for every paid item.
3. ~~**W3, W6, W15, and the W2 re-run**~~ **Done 2026-08-13.** Outcomes in 7.6.
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


## 7.6 Track D outcomes, 2026-08-13

Four items closed in one pass. Two kept, one kept with a caveat, one dropped, which
is roughly the mix section 6 said to expect.

### W2, re-run and made reproducible

`scripts/measure_per_path.py` is the method the original run lacked, and it enforces
two things the first pass needed a human to remember: a measure monotone under
path-subsetting is **refused** rather than scored, and a rate measure reports the
smallest nonzero value its new denominator admits.

**Told-emotion: closed, and worse than `AL-342` recorded.** The band is 0.5 hits per
1000 narration words and needs a passage over 2,000 words before one hit scores under
it. Covering paths run in the hundreds. The band therefore cannot bind on **20 of the
20** committed books, not the six cases the original run happened to surface. `UW-C244`
stands as written: re-derive at path scale or express the path-scope version as a count.

**Reading level: the number moved, and the reason is the corpus, not the measure.**
The published outcome is 18.9 percent disagreement over 53 books; this run measures
0 percent over 20. Those are different corpora. The published one included
`out/vendor-comparison/`, which is untracked and absent from every checkout but the
machine that produced it, and the committed books are hand-authored catalogue fills
rather than machine-generated comparison books. **The published figure is not
overturned and must not be reported as such.** The script prints its corpus for this
reason. This is section 7.4 gap 3 arriving with a bill attached.

### W3, fork consequence: KEEP as a reported statistic

Mean 14.5 percent false choices, spread 0.190 across the 23 books that report complete.
It separates books from each other, which is the stage-one bar.
`BandProfile.reconvergence_ceiling` stays unenforced; promotion needs W12.

Two limits the tool states itself: 47 of 61 books declare no variables at all, so their
forks are scored on distance alone and their state delta is empty by construction; and
a spread over fewer than three complete books is refused rather than published.

The design error worth recording: the first version scored a fork whose branches run to
different endings as an unmeasured horizon hit. Every book has such forks, so every book
came back incomplete and the scan returned "not measured" over the whole catalogue.
Terminal divergence is an answer, and the most consequential one a fork can have.

### W6, blind-spot manifest: KEEP, because the declaration is drift-proof

The rule was the demanding one: keep only if the declaration cannot drift from
behaviour, and drop to prose otherwise. The mechanism that earns it is a **witness** per
observed dimension, a document built to trip one of that dimension's rules.
`verify_declarations()` runs the battery through the real gate, so a checker that stops
checking makes its own declaration report stale. A test disables a checker and asserts
exactly that; if it could be made to pass with the checker off, the rule says delete the
module.

The manifest reproduces both cases it was specified against. It names the four
qualitative age dimensions as unobserved in every context (`AL-337`), and it names
filled prose as unobserved under skeleton context and observed under fill-result
(`AL-325`), which is the same distinction `PL-27` closed.

### W15, declared information state: DROP

Built and run as a probe rather than shipped. The candidate passes the three easy cases
and fails the decisive one: a declared secret restated in different words goes
undetected, because detecting it is an entailment question and nothing here answers one.
"The lighthouse keeper is the thief" leaks just as completely through "the man who
tended the light had been taking the cargo", which shares no content word with the
declaration. No lexical or semantic resource is in the dependency set, and adding one
would not close that gap.

Per the pre-registered rule, the information-state dimension **stays uninstrumented**
and is now listed in `blind_spots.UNOBSERVED` beside the four qualitative age
dimensions. The probe stays in the test suite as the evidence, since a negative result
is the deliverable and deleting it would leave only a commit message behind.

## 7.7 Sprint: validate the rulers before the judge (2026-08-13)

An adversarial review of the W7 fixture, run before any judge call was paid for, refuted the premise
the arm was being built on and found a class of defect rather than an instance: **the deterministic
measures W7 depends on are less sensitive than we assumed, and this plan pre-registered figures that
do not reproduce.** Running the battery on top of that would have measured the fixture while section
3's own wording read the result as an instrument verdict.

The sprint is therefore the rulers, not the run. Every item below is unpaid.

### What the review established

| Claim under review | Outcome |
| --- | --- |
| The W7 corpus contains no dialogue | **Refuted.** `the-backyard-treasure-map` carries 15 spoken lines across 18 of 62 nodes as *unquoted tagged* speech ("Let's try this one, they said."). The corpus has dialogue; our detectors cannot see it |
| The dialogue criterion's 3.04 is the anchor firing correctly | **Refuted as stated.** The rubric has two competing anchors and the governing one is "1 = ... absent where it is clearly needed", which was omitted. Six of eight vendor legs had nonzero dialogue, so "uniformly narration-free" is false for the pool the figure came from |
| `AL-330` and `UW-C236` rest on that inversion | **Refuted.** `AL-330` lists "badly anchored" as one of its three disjuncts, so it does not make the claim. The real target is section 3's pre-commitment |
| The `dialogue_flat` arm is dead on these five books | **Confirmed**, empirically, though for a different reason than argued |
| Section 3's "if the battery does not retire it, the battery is broken" is a methodological error | **Confirmed.** A no-op seed yields an arm byte-identical to its control, detection rate 0, and the pre-registered reading is "criterion retired" |

### The sprint, in dependency order

1. **Fix the dialogue detector.** Three quote-only implementations (`evaluate_books.py`,
   `check_prose_craft.py`, `seed_defects.py`) are blind to tagged direct speech. This is first
   because it is load-bearing twice: it blocks W7's dialogue arm, and it is the deterministic
   measure `UW-C236` proposes to **prefer over** the panel. Replacing a possibly-insensitive judge
   with a definitely-insensitive regex is not an upgrade.
2. **Re-measure the corpus and re-open `AL-330` / `UW-C236`.** The 25-fold spread that made the
   panel look broken may shrink or invert once the detector sees tagged speech. Stated limit: the
   eight vendor legs **cannot** be rechecked, because `out/vendor-comparison/` is untracked. That is
   section 7.4 gap 3 arriving with a second bill.
3. **Retract the "SD 0.19 across twelve cells" splice.** Two instruments spliced together: the 0.19
   is the spread across 84 individual verdicts (section 29 of the brief); "twelve cells" is the
   six-question diversity rubric over 3 rounds by 4 cells (section 16m). `criterion_spread` averages
   books into `(leg, judge)` cells first and returns **0.088** on the real pool. W4's decision is
   unchanged, 0.088 still clears the 0.25 threshold, but the pre-registered number is not one the
   implemented function will produce.
4. **Delete section 3's pre-committed verdict.** Replace with the per-criterion rule that section
   already states. Cheapest item here and the largest effect on the run's validity.
5. **Parameterise the judge prompt by age band.** `judge_books.py` hardcodes "children aged 5 to 8"
   in three places while the panel is run across 3-5 to 16+. It is running off-prompt today,
   independent of any corpus choice, so every existing verdict carries it. Changing it makes the new
   pool not strictly comparable to the 84-verdict one, which is a reason to decide it before W7 runs
   rather than during.
6. **Then run W7.**

### Not doing, and why

- **The inverse seed** (add dialogue, check the score rises): confounds four criteria at once, since
  LLM-added dialogue moves length, reading level and voice together, and it spends a generation call
  on a defect the repo can seed deterministically.
- **The corpus swap as proposed**: two of the three suggested books (`the-clocktower-cipher`,
  `the-lost-mitten`) fail `Storybook.model_validate`, being pre-schema-v2 xfails. W7 needs books that
  currently pass. Only `the-thornwood-trial` is usable and it carries one dialogue node at 27k input
  tokens.

### The generalisable finding

Bigger than dialogue, and the reusable output of the whole detour: **before a judge criterion is
compared against a deterministic measure, the deterministic measure needs its own sensitivity
check.** We have been treating "deterministic" as a synonym for "correct". A regex that returns 0.000
and a judge that returns 3.00 can both be wrong about the same book, and only one of them looks like
an opinion.

### 7.7.1 Outcome of items 1 to 5 (2026-08-14)

All five are done and unpaid. Item 6 is treated separately in 7.7.2.

**Item 1, the detector.** `src/cyo_adventure/validator/dialogue.py` now recognises quoted and
tagged speech and is the single implementation behind all four callers: `seed_defects.py`,
`evaluate_books.py::_dialogue_share`, `check_prose_craft.py::strip_dialogue` (composed onto its
existing `strip_quoted`, whose single-quote-versus-possessive handling is better than a general
detector's and was kept), and `measure_per_path.py`'s narration denominator.

Writing its tests found a second instance of the bug the module was written to fix. Locating
quoted spans over the whole text before splitting into sentences was the first fix; the *tagged*
case had the same flaw and survived it, because a spoken line cut at its own "!" leaves the tag
half matching on its own. The detector therefore looked correct while reporting "he whispered."
as the spoken line, leaving "Right here!" in the narration for every caller that strips, and
leaving the tag in place for the seeder. Regions are now found over the whole text for every
pattern, and the halves are rejoined only when the same region reaches across both.

**Item 2, the re-measurement.** Over the 23 filled books in `out/`:

| | Quote-only | Quoted and tagged |
| --- | --- | --- |
| Books scoring exactly 0.000 | 20 of 23 | 6 of 23 |
| Mean body-level share | 0.079 | 0.137 |
| Books carrying any dialogue | 3 | 17 |

Fourteen books the old measure called dialogue-free carry between 2 and 92 spoken lines.
`the-backyard-treasure-map` goes 0.000 to 0.258, `the-vanishing-orchard` to 0.225,
`the-harrowstone-keep` to 0.145 across 92 lines.

The consequence for `AL-330` / `UW-C236`: the row's remedy is "prefer a deterministic measure
wherever one exists for the same property", and the deterministic measure it would have preferred
was wrong about 61 percent of the catalogue. The 25-fold spread that made the panel's `dialogue`
criterion look degenerate cannot be rechecked, since the eight vendor legs are in the untracked
`out/vendor-comparison/` (section 7.4 gap 3, second bill). What can be said is that the corpus is
not the near-dialogue-free thing the figures implied, and that a criterion returning about 3.00
across books clustered between 0.01 and 0.26 is a plausible reading rather than a stuck one. Both
rows stay open, with their remedy narrowed: report per-criterion spread, yes; prefer the
deterministic measure only after the deterministic measure has passed its own sensitivity check.

**Sensitivity of the two measures that consume the exemption**, since widening it changes their
denominators and this is exactly the check the sprint says to run:

- *Told emotion* (`check_prose_craft.py`, and W2's path-scoped re-unit): narration denominators
  fall 0 to 4 percent, and no book's per-1000 rate moves by more than 0.013. W2's told-emotion
  figures stand as published.
- *Tense stability*: 4 of 23 books change their unstable-node count, the largest being
  `the-sunken-temple` at 69 to 59. The direction is almost entirely downward and the cause is
  specific: quote-stripping leaves the attribution fragment ("he whispered.") behind, every
  spoken line contributes one, and its tense is the tag verb's rather than the narration's. The
  detector was taking a free tense vote per line of dialogue.

**Items 3 and 4** are the workplan edits above: W4's rule no longer cites the spliced "SD 0.19
across twelve cells", and section 3 no longer pre-commits to "if the battery does not retire it,
the battery is broken".

**Item 5**: `judge_books.py` derives the band phrase from the book's own declared band and falls
back to the historical "5 to 8" wording when a book declares none, so the existing 84 verdicts
remain reproducible while a book declaring 10-13 is no longer judged against a 5-to-8 rubric.

### 7.7.2 W7's corpus, and three harness defects found building it (2026-08-14)

The corpus was rebuilt rather than reused, because the fixed detector changed which books
can carry the `dialogue_flat` arm and because pricing the previously-planned corpus made it
unaffordable.

**Why not the corpus in the "Not doing" note above.** That note ruled the swap out on the
grounds that `the-clocktower-cipher` and `the-lost-mitten` fail `Storybook.model_validate`
as pre-schema-v2 documents. Correct as far as it went, and it stopped one step early: the
three failures (`schema_version` "1.0", absent `metadata.topology`, `ending.type` where v2
wants `kind` and `valence`) are all mechanically derivable. `scripts/normalize_pre_v2.py`
derives the topology from `validator.topology.admissible_topologies`, the classifier the
gate itself uses for PL-18, and maps the five `type` values the corpus uses onto
`(kind, valence)` from a fixed exhaustive table that raises on anything unlisted. It writes
copies and never touches the tracked fixtures.

That produced a finding worth keeping: the xfail reason on all three legacy books reads
"migrate to v2 then drop from `_LEGACY_PRE_V2`", and after migration only `the-lost-mitten`
passes the gate. `the-clocktower-cipher` and `the-sunken-signal` are blocked by L1-7 on
branch depth (9 against a limit of 8, and 13 against 12), which is a content property, not a
schema gap. The xfail reason is therefore accurate for one of the three books and misleading
for the other two.

**The corpus.** Six books, every one gate-passing under `fill_result` context, chosen
smallest-first for cost with the two dialogue-carrying books included deliberately:

| Book | Nodes | Words | Dialogue share |
| --- | --- | --- | --- |
| `the-lost-mitten` (normalised) | 11 | 760 | 0.818 |
| `the-clover-and-the-butterfly` | 20 | 663 | 0.000 |
| `the-teddy-bears-picnic` | 29 | 1,172 | 0.000 |
| `the-lantern-festival` | 37 | 1,948 | 0.000 |
| `the-backyard-treasure-map` | 62 | 4,052 | 0.258 |
| `the-cave-of-echoes` | 65 | 4,906 | 0.000 |

Stated limits. These are the small end of a catalogue running to 551 nodes, which the
per-criterion rule tolerates (the question is the judge's sensitivity to a seeded defect, and
a shorter book gives the defect less room to be noticed, so the bias runs conservative) but
which a later reader should not mistake for a representative sample. The bands span 3-5 to
10-13, which item 5's per-book band phrasing now handles.

**Three harness defects, all found before spending:**

1. **`harden_book` had no caller.** The function that seeds `reading_level_up` was defined
   and never invoked from `main`, so a run would have judged five arms, found no
   `reading_level_up` arm, and reported `age_fit` UNTESTED without saying why. Now behind
   `--prepare`, deliberately a separate invocation so a retried judging pass does not repeat
   the paid rewrite.
2. **The seeder wrote arms that did not land.** `seed_defects.py` reported MISS and wrote the
   file anyway. A non-landing seed yields an arm byte-identical to its control, the battery
   counts it as an opportunity, the delta is zero, and the pre-registered reading of a zero
   detection rate is "retire the criterion". That is precisely the error item 4 deleted from
   section 3, sitting in the harness rather than in the prose. Non-landing arms are now
   withheld and named, so the affected criterion runs at reduced n instead of being handed a
   manufactured failure. Five arms were withheld on this corpus: `dialogue_flat` on the four
   books with no dialogue, and `false_choice` on `the-lost-mitten`, whose forks are already
   false (4 of 4).
3. **`harden_book` was sequential.** 224 rewrite calls at one at a time is most of an hour of
   wall clock. Bounded to 6 concurrent.

**Arm counts going into the run**: 6 controls, 6 `tense_break`, 5 `false_choice`,
6 `premise_duplicate`, 2 `dialogue_flat`, 6 `reading_level_up`. The `dialogue` criterion gets
2 opportunities, both with strong seeds (0.818 and 0.258 to 0.000), against the 1 dead
opportunity the previously-planned corpus offered.

### 7.7.3 The reading-level seed overshot by a factor of three (2026-08-14)

The `reading_level_up` seed asks a model to rewrite each passage "about 3 US reading grades
harder". It does not take direction on magnitude. Across the six-book corpus it delivered:

| Book | Band target | Control grade | Full rewrite | Delta |
| --- | --- | --- | --- | --- |
| `the-lost-mitten` | 1.0 | -0.02 | 8.14 | +8.16 |
| `the-teddy-bears-picnic` | 1.0 | 0.76 | 10.40 | +9.63 |
| `the-clover-and-the-butterfly` | 1.0 | 0.85 | 10.97 | +10.12 |
| `the-lantern-festival` | 2.5 | 1.79 | 12.85 | +11.06 |
| `the-backyard-treasure-map` | 2.5 | 2.65 | 12.43 | +9.78 |
| `the-cave-of-echoes` | 4.5 | 4.55 | 13.33 | +8.78 |

Books whose bands target grades 1.0 to 4.5, rewritten to grades 8.1 to 13.3. That is not a
book too old for its band, which is the defect; it is a different genre, and it breaks the
fixture two ways. `age_fit` detection becomes trivial, so the arm stops measuring the
criterion's sensitivity to a realistic miss and starts confirming that the panel can read.
And voice, engagement and dialogue all move genuinely, which this battery's false-positive
rule (any non-target arm moving a criterion by more than 0.5) would charge against those
criteria for correctly noticing a real change.

The seed was left in place and the arm composed from it instead. `blend_to_grade` swaps
hardened bodies into the control one at a time, spread across the book by a low-discrepancy
order rather than front-to-back, until the whole-book grade reaches the target:

| Book | Control | Blended arm | Delta | Nodes swapped |
| --- | --- | --- | --- | --- |
| `the-lost-mitten` | -0.02 | 3.05 | +3.07 | 3 of 11 |
| `the-teddy-bears-picnic` | 0.76 | 4.17 | +3.41 | 7 of 29 |
| `the-clover-and-the-butterfly` | 0.85 | 4.27 | +3.42 | 5 of 20 |
| `the-lantern-festival` | 1.79 | 5.06 | +3.26 | 9 of 37 |
| `the-backyard-treasure-map` | 2.65 | 5.68 | +3.03 | 18 of 62 |
| `the-cave-of-echoes` | 4.55 | 7.63 | +3.07 | 21 of 65 |

This is deterministic, exact to within one node's worth of grade, and free, since the
generation is already paid for and `--reblend` calls no provider. It also seeds a defect
closer to the real failure mode: a book whose passages drift too hard in places is what the
pipeline produces when it misses a band, not one uniformly rewritten into academic prose.

**A second finding from the same run.** The prepare step reported `$0.0000 spent hardening`.
That is `UW-C239` arriving where it does damage: `core/pricing.py` leaves input rates unset
for every cloud model, so an unpriced run and a free one print identically. The harness now
prints "spend unpriced" and names the row, because a dollar figure in a measurement record is
read as measured.

### 7.7.4 W7 result: three criteria kept, two retired, and half the instrument still unvalidated (2026-08-14)

Ran on the six-book corpus, 31 arms, 3 judges, 93 scorings, all successful (no errors, no
empty score sets). Total spend measured against the provider's balance: **$6.29**, of which
$0.85 was the harden and about $2.5 was a duplicate concurrent panel run (`AL-364`).

**The run first reported seven UNTESTED verdicts over 93 good scorings**, which was a join
defect rather than a result: `judge_book` labels each verdict `f"{leg}#{brief_index}"`, right
for the vendor comparison it was written for, and the battery joined on the bare stem. The
tell was that the failure was total; a battery merely short of data reports some numbers. The
fix was free, and the numbers below come from replaying the same verdicts.

#### Detection, per criterion

| Criterion | Defect | Detected | Median delta | Verdict |
| --- | --- | --- | --- | --- |
| `age_fit` | `reading_level_up` | 6/6 | -2.00 | **KEEP** |
| `choice_quality` | `false_choice` | 5/5 | -1.33 | **KEEP** |
| `engagement` | `premise_duplicate` | 4/6 | -0.67 | **KEEP** |
| `voice` | `tense_break` | 2/6 | -0.17 | **RETIRE** |
| `dialogue` | `dialogue_flat` | 1/2 | -0.83 | **RETIRE** |
| `imagery` | none | - | - | UNTESTED |
| `ending_quality` | none | - | - | UNTESTED |

`age_fit` and `choice_quality` are unambiguous: every book, every time, with deltas from
-0.67 to -2.33 against a 0.5 margin. Note that `age_fit` cleared it on the *blended* seed, at
+3 grades rather than the +9.6 the raw rewrite would have given it, so this is a pass at a
realistic defect size rather than a demonstration that the panel can read.

`voice` fails outright. Its six deltas are -0.33, 0.00, 0.00, -0.67, +0.33, -0.67: noise
around zero, including a book where the criterion moved *up* after the tense was broken.

`engagement` is a marginal keep and should be read as one. Its four detections are -0.67,
-0.67, -0.67 and -1.00, so three of the four sit one third of a point past the margin, and
the two misses are -0.33 and 0.00. The verdict is what the pre-registered rule says; the
effect size is small enough that a slightly different margin would flip it.

`dialogue` retires on n=2, which is thin, but the *shape* is worse than the count suggests.
The book it missed is `the-lost-mitten`, whose 0.818 dialogue share is the highest in the
catalogue: every spoken line in the book was converted to narration and the criterion scored
it 2.67 before and 2.67 after. The arm where detection should have been easiest is the one it
failed. Set against `AL-330`, this is the answer that section could not previously give: the
`dialogue` criterion really is insensitive, and the earlier evidence for that claim was
simply the wrong evidence.

#### Two parts of the battery's own rule that do not hold up

**The false-positive column measures something other than false positives.** The rule counts
any non-target arm moving a criterion by more than 0.5. But `reading_level_up` rewrites a
third of the prose, so `voice` and `imagery` genuinely change; `premise_duplicate` replaces
the opening node, so `engagement` genuinely changes. Every one of the 4-to-10 "false
positives" per criterion is of that kind. The column charges a criterion for correctly
noticing a real change. It drives no verdict here (the KEEP/RETIRE strings cite detection
only) and no conclusion above rests on it, but it must not be read as evidence against any
criterion, and the rule needs restating before it is.

**The agreement figure is not interpretable as computed.** All three pairs came in below the
0.60 floor (+0.16, +0.58, +0.14), and that number should not be quoted. `cohens_kappa` is a
categorical statistic and it is being fed the *mean across all seven criteria*, rounded to an
integer. After rounding, `judge-gpt-5.6` uses two categories with 24 of 31 books in one, and
`judge-grok-4.6` uses three with 23 of 31 in one. That is the classic skewed-marginals regime
where kappa collapses despite high raw agreement, and it explains the pattern exactly: the
two judges with similarly skewed marginals score +0.58, while both pairings with
`judge-gemini-3.1` (four categories, sd 0.79 against 0.31) fall to about +0.15. Rounding a
seven-criterion mean also discards the per-criterion structure that W7 exists to examine.
Agreement has to be computed per criterion, and with a statistic suited to ordinal data, before
this half of the instrument says anything.

**Where that leaves W7.** The detection half is done and gives a usable answer: three criteria
support a ranking, two do not, two were never exercised. The agreement half is unrun, because
what ran was the wrong calculation. Any Part IV claim resting on the panel may use `age_fit`,
`choice_quality` and (with the caveat above) `engagement`; it may not use `voice` or
`dialogue`, and it may not yet cite inter-judge agreement at all.
