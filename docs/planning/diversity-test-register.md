# Diversity test register

> Every test the diversity programme still owes, in one place, so none is lost while others run.
> Opened 2026-08-10 after the decision-variance run closed. Update the status column in the same
> commit as the work; a test that moved without this file moving is a bookkeeping bug.

## How to read this

**Status vocabulary.** `queued` (not started), `running` (in flight), `done` (result recorded and
linked), `blocked` (waiting on another row), `retired` (will not run, with the reason stated).

**Cost** is the estimate from whoever proposed the test, marked as theirs. Our own estimates have
been wrong in both directions on this programme, so they are recorded rather than trusted.

**Every row names what would falsify it.** A test with no falsifier is a demonstration, and a
demonstration cannot change anyone's mind. Rows that cannot state one are marked as such.

**Results flow into the paper.** Every row that reaches `done` must also be reflected in Part II
of [the research brief](./cyo-generation-research-brief-2026-08-10.md), which is the document
external reviewers read. A result recorded here but absent there is half-delivered: this file
tracks the work, that one is the work's account of itself.

**Sources.** `R1-*` and `R2-*` are the two external reviewers' candidate architectures, `M-*` are
the three options identified in-house, `Q-*` are the open questions in
[cyo-framework-problem-and-structures](./cyo-framework-problem-and-structures-2026-08-10.md)
section 6, `D-*` are follow-ups the 2026-08-10 decision-variance run created.
The six families in [the research brief](./cyo-generation-research-brief-2026-08-10.md) section 8.4
are not listed separately: each is a less-developed statement of a row below, mapped in the
duplicates table at the end.

---

## The gating result every architecture row now inherits

The decision-variance run (spec sections 9.5 and 9.6) found that the DecisionSignature v1
vocabulary **ranks book pairs in the opposite order from readers**, under three independent blind
annotators, with inter-annotator kappa of 0.96 on `action_family`. It is deaf at the forks readers
call decisive and follows scenery at the entry forks.

Six of the ten architecture rows below either emit these signatures, score against them, or
optimise them. **Any such row run before the instrument is fixed is measuring with something known
to point the wrong way**, and a positive result from it would be uninterpretable. That is why the
D rows sort above the architecture rows, and it is a change from the reviewers' recommended
orders, which were written before this was known.

**D-3 has since narrowed the problem, and widened who it affects.** Enriching the vocabulary
changed nothing: annotated over the contracts, `reasoning_kind` inverts exactly as
`action_family` did and `stake` ties, zero of six fields ordering the pairs as readers did. The
cause is that the contracts do not contain the property. They describe the decisive fork as
"answer the test on its own terms" and "fit the piece the way the diagram shows"; the arithmetic
against shape-matching distinction that both raters named lives in the binding. So **R2-1b, R1-1
and M-3 are not merely blocked on a metric, they are specified to plan at a layer that provably
omits what readers respond to**, and each needs re-specifying rather than re-scheduling.

---

## A. Instrument and replication work (do first)

| ID | Test | Question it settles | Method | Cost | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| D-1 | Separate the treatment's **three** bundled changes | Was the 2026-08-10 effect from the different kind of act, from the stake economics, or from the four rooms yielding distinct components? Raters cited act-kind at one fork and stakes at two, so the original two-way framing understated the confound. | Three arms on the same graph, each restoring one change to the control's setting while holding the other two. Rate each against the same base book with the six-question instrument. | 3 fills, 2 raters | Restoring any single change collapses the effect, which would name that change as the whole lever rather than one of three. | queued |
| D-2 | Replicate on a production-eligible graph | Does any of this survive off a 26-node outlier? The catalog median is 151 nodes and the pilot graph is not production-eligible. | Repeat the winning arm on a production-scale 10-13 skeleton, same protocol, same instrument. **Blocked on an artifact nobody noticed was missing: see below.** | **badly underestimated, see below** | The effect vanishes or inverts at production scale. | **running, at rating prep**: contract authored and independently verified (101 nodes, 39 forks, 0 closure violations); three bindings verified at 0.000 collision with only the 6 designed shared-world props; three fills complete and structurally clean (10.2k to 10.6k words each); cast renamed and titles separated. **HALTED AT THE GUARD BATTERY, not rated.** See below. |
| D-3 | DecisionSignature v2 over the contracts | Can a richer vocabulary agree with readers instead of inverting them? | Added `reasoning_kind` (compute, match, recall, infer, perceive, negotiate, exert) and `stake` (nothing, time, resource, access, standing, permanent) plus the three `AL-193` gaps, and re-annotated the three plans blind. | 2 annotators over 3 plans | Hit its own falsifier: still ranks the treatment pair as the more repetitive one. Annotator A 0 of 6 fields agreeing with readers, annotator B 1 of 6. `reasoning_kind` inverts under both (0.929 against 1.000, and 0.857 against 0.964). Not a reliability failure: kappa between the two annotators is 0.77 to 0.81 on `reasoning_kind` and 0.72 on `stake`, both clear of the floor. The new fields are labellable and do not discriminate. | **done, NEGATIVE** |
| D-3b | Same vocabulary over contract **plus binding** | Is the inversion a vocabulary problem or a layer problem? The contracts describe `n_clockface` as "answer the test on its own terms" and "fit the piece the way the diagram shows", which Rule 2 correctly calls one decision; the mechanic readers responded to lives in the binding (`clock_arithmetic`, `rhythm_code`, `pictogram_code`). | Identical annotation pass with each plan's bound devices attached. | 1 to 2 annotators over 3 plans | Ordering still inverts with the binding visible, which would mean the discriminating property is not in the plan at all and only the filled prose carries it. Did not fire. | **done, POSITIVE, 1 annotator** |
| D-3c | Confirm D-3b with a second blind annotator | Is D-3b reproducible, and does it survive a subset fixed in advance? | Second independent annotator, same three bundles, same brief. Analysis pre-registered below before the labels exist. | 1 annotator over 3 plans | The second annotator's `reasoning_kind` does not separate the pairs in the readers' direction over the pre-registered fork subset. Did not fire, but the margin nearly vanished. | **done, PARTIAL** |
| D-4 | Solution-transfer metric | Is the item that actually discriminated computable from a plan, rather than only ratable by a reader? | Formalise "these two puzzles resolve by the same operation to the same answer" against the three existing contracts, and check it reproduces the raters' Q6 ordering (4,4 against 3,3). Scored against **three** rated pairs rather than the one the row asked for, since D-5 supplied a second ordering. | deterministic, no model | Did not fire. Reproduces all three orderings strictly, and does so on the tier that uses no taxonomy. | **done, POSITIVE but narrow** |
| D-6 | Which repair unblocks D-2 | `AL-208` says D-2 converged because its arms shared one contract. That is a diagnosis nothing has tested, and three candidate repairs were proposed with no way to choose between them. | One contract, two bindings held constant, three conditions (`verbatim`, `neutral`, `diverge`), six independent 26-node fills. Outcome is the guard battery itself, so no rater is needed. | 6 fills, 0 raters | `verbatim` lands near the pilot's 1.8 to 2.7 per 1000, which would mean contract sharing is not the cause and `AL-208` misdiagnosed D-2. Or all three conditions converge alike, which would mean no cheap repair exists. | **running** |
| D-5 | Rate the discarded contaminated arm as a negative control | Does the six-question instrument correctly detect a pair we know is contaminated? | The 14-of-24 shared-prop binding is preserved. Feed `filled_V5b` to fresh blind raters and confirm it scores worse than `filled_V5c` on Q6. | 2 raters | Did not fire. Both raters, opposite orders, scored the contaminated pair Q6 = 5 and the clean pair Q6 = 2, and both chose the contaminated pair as more similar at high confidence. A three-point gap on the item that matters. **Re-run independently 2026-08-10 because the original result was not produced here: two fresh raters in opposite orders reproduced it exactly, Q6 = 5 for the contaminated pair against 2 for the clean one, both choosing the contaminated pair at high confidence.** The instrument detects a known-bad pair, so the ratings in section 13 stand. | **done, PASS, replicated** |

### D-4 result: solution transfer is computable from a plan, but only its taxonomy-free half

`scripts/check_solution_transfer.py` scores, for each prop on a book's solution chain, the
strongest transfer available to it in the other book: **answer transfer** (the same device, so the
puzzle is recognised rather than solved), **operation transfer** (a different device resolving by
the same operation), or **family transfer** (a different operation of the same kind). The chain is
every prop bound in a puzzle-carrying device category; no fork or node is hand-picked.

D-5 handed this row a second rated ordering the register did not anticipate, so it was scored
against three pairs rather than one.

| Pair | Raters' Q6 | Answer transfer alone | Full score |
| --- | --- | --- | --- |
| base against the contaminated arm | 5, 5 | **1.000** | 1.000 |
| base against the control | 4, 4 | **0.167** | 0.467 |
| base against the treatment | 3, 3 and 2, 2 | **0.000** | 0.225 |

**The falsifier did not fire, and the reason it did not is the interesting part.** The worry going
in was circularity: tiers 2 and 3 encode the D-3b distinction, which was discovered on these same
plans, so agreement would prove nothing. It does not arise, because **tier 1 reproduces the whole
ordering by itself** and tier 1 uses no taxonomy at all. The part that matches the readers is the
part that could not have been fitted to them.

**Tiers 2 and 3 were then run against the 101-node bindings and did not survive.** On vocabulary
the lexicon has never seen it classifies 2 of 6 chain props and returns nothing for the rest, with
two failure modes neither fixable by adding words: no negation, so "a page of small hand-drawn
icons instead of numbers" reads as arithmetic, and polysemy, so "a short tail" on a drawn symbol
reads as rhythm. The one operation match it does report between arms is both waypoint marks
scoring `MATCH`, an artifact of the slot rather than a fact about either puzzle. `--check`
therefore gates on tier 1 only.

**So the honest headline is narrow: device identity is computable and generalises; operation
identity needs a model.** That is the same boundary Q-5 found for obligation delivery, reached
independently from the other end, and it is now two-for-two: the lexical version of a question in
this programme has never yet been good enough to gate.

**One caveat this raises about section 13 rather than about the metric.** The control pair's 0.167
is a single link: that pair's rhythm hint carrier against the other book's rhythm cipher, which is
the `AL-185` collision, sitting on the control pair's own solution chain. The 4-against-3 gap may
therefore be driven by an uncontrolled device collision rather than by the treatment. The
5-against-2 gap is not exposed to this, since that pair shares 14 props against none.

**A defect in the first version, recorded because the failure mode generalises.** Rarity was first
computed inside the solution chain, which is vacuous when the chain is short: two props per book
make a four-prop corpus in which nearly every word is "used by at most two props". It reported
three plainly different waypoint marks (a scratched star, a painted spiral, an inked triangle) as
the same device, on the shared words `logbook's`, `mark` and `margins`, which are the contract's
framing for the slot. Rarity is now judged over both bindings entire. **Any threshold calibrated on
a large corpus and then applied to a subset inherits this**, and `check_device_collision.py` is the
tool that calibration came from.

### D-2 halted at the guard battery: sharing a contract makes the contract the fingerprint

The three books are structurally sound and the design was realised: 101 nodes each, 10.2k to 10.6k
words, fill integrity clean, validator gate not blocked, prose craft clean, zero em-dashes, bindings
at 0.000 collision with only the six designed shared-world props, P/Q sharing no proper noun and P/R
sharing town, family and destination.

**They cannot be rated.** The convergence guard fails by an order of magnitude:

| Pair | Shared 4-grams per 1000 (budget 4.0) | Identical choice menus (margin 0) |
| --- | --- | --- |
| P vs Q, the control pair | **59.2** | **51** of 131 |
| P vs R, the treatment pair | **63.8** | **41** of 131 |
| pilot's clean pair, for reference | 1.8 to 2.7 | 0 |

Forty-one to fifty-one choice menus open with the same words in two books that no author could see
past. Rating this would measure convergence, not the treatment, and the discipline recorded in
`AL-191` says terminate rather than spend a measurement on an artifact the guards reject.

**The first diagnosis was wrong and was refuted by measurement.** The obvious culprit is a
lexically over-prescriptive contract handing authors its verbs. Measured: D-2 labels reuse a
distinctive word from their own `choice_semantics` at 46.6 percent, and the *pilot* does so at 54.3
percent. Per-book reuse is higher in the case that did not converge.

**The real cause is structural, and it is a design error in D-2.** The pilot's arms read
**different contracts**: their `choice_semantics` were identical at 0 of 35 choices. D-2's three
arms read **one contract**, identical at 131 of 131 by construction. Sharing the plan means sharing
its prose, and three authors writing from one sentence converge on it. D-2 mirrored the pilot's arm
structure while varying only bindings, where the pilot varied contracts.

**This is a bigger result than the replication would have been.** Every architecture proposed to us
that reuses one plan across many books inherits this: the plan's own wording becomes the
fingerprint, and no binding diversity can remove it. It is invisible to the device-collision check,
which passed at 0.000, and it is exactly the failure the shared-gram guard exists to catch.

To resume D-2, one of three things has to happen: neutralise `choice_semantics` to non-evocative
phrasing, generate the semantics per book, or require authors to diverge from the given wording
explicitly. All three are cheaper than the three contracts the pilot's structure implies, and which
of them works is itself worth testing. **That test is now D-6**, below.

**One candidate confound is already excluded.** D-2's three arms carried *different* `label_style`
values ("imperative and verb-first, said out loud", "name the place you are going to, let the
reason stay implied", "physical verbs for physical legs, quiet verbs for the choices about
people"). A shared house style is therefore not what made them converge, which leaves the shared
contract as the live hypothesis rather than one of two.

### D-6, pre-registered before any fill exists: which repair actually works

`AL-208` is a diagnosis, not a result. D-6 tests it directly, at pilot scale where the baseline is
known, holding every input constant except how `choice_semantics` reaches the author.

One contract (`contract_v2`, 26 nodes), two bindings held constant (`armC` and `armD`, the pilot's
own), three conditions, six fills authored by agents that cannot see each other:

| Condition | What the author is handed |
| --- | --- |
| `verbatim` | the contract's `choice_semantics` exactly as written |
| `neutral` | the act and its object in the plainest words, no metaphor, no virtue noun, no colour |
| `diverge` | the semantics as written, plus an explicit instruction not to reuse their wording |

**The outcome measure is the guard battery itself**, shared 4-grams per 1000 and identical choice
menus between the two books of each condition, so D-6 needs no rater and cannot be argued with.

Anchors: D-2, one shared contract, 59.2 to 63.8 per 1000. The pilot, different contracts, 1.8 to
2.7. Budget 4.0.

**Prediction, fixed now:** `verbatim` lands far above the pilot baseline, reproducing D-2's failure
at 26 nodes; `neutral` and `diverge` land materially below `verbatim`.

**Falsifiers, stated in advance:** if `verbatim` lands near 1.8 to 2.7, contract sharing is not the
cause and `AL-208` misdiagnosed D-2, which would most likely mean the convergence was a scale
effect. If all three conditions converge alike, no cheap repair exists and every reusable-plan
architecture inherits the problem.

**The obvious construction of `neutral` was tried first and is unusable, which is a result in its
own right.** Deriving each branch's semantics mechanically from the fact graph, as the facts its
destination presupposes that the fork does not already guarantee, needs no author and so cannot
smuggle in a voice. It also destroys the fork: at `n_clockface` all four options, answering the
code, forcing the dial, going round the back and guessing at random, own exactly the same
obligation, so all four neutralise to the identical sentence. That is `AL-197` reached from the
opposite direction, **the fact graph does not contain the decision**, so nothing derived from it
can flatten the wording while preserving the choice. The neutral phrasing is therefore hand-written
under a stated rule, and the rule is what is on trial.

**A second guard finding, independent of the above.** All three books landed at whole-book
Flesch-Kincaid 8.14 to 8.41 against a 5.5 target, with only 16 to 20 of 101 nodes inside the band
and 81 to 85 advisory warnings each, while the gate returned `blocked=False` on all three
(`AL-209`).

### D-2 discovered a hole under the whole programme

Setting up D-2 turned up something more consequential than the test itself.

**The narrative contract exists for exactly two skeletons in the catalog, and neither is
production-eligible for this band.** Every artifact in this programme, the branch-obligation
screen, the decision-overlap metric, all nine blind annotations, the reasoning-kind measure, is
computed from a narrative contract: the per-node object carrying `entry_state`, `establishes`,
`forbids`, `choice_semantics` and a `world_recipe`. The catalog has eleven 10-13 skeletons, and
narrative contracts exist for the 26-node pilot and for one 3-5 band story. Nothing else.

The catalog's `.contract.json` files are a different artifact entirely: slot and theme contracts
under ADR-019, listing substitutable roles (`HERO`, `THRESHOLD`, `OPENING_MOMENT`) with no nodes,
no facts, and no choice semantics. They cannot carry any measure in this programme.

**So the programme is n=1 in a stronger sense than "one graph".** It is one *representation
instance*, hand-built for one 26-node skeleton, and no measure we have built can be run against a
single production skeleton today. Twenty-three filled books exist in the repository and every one
sits on a distinct skeleton, so there is not even an accidental pair to measure.

This also lands on the proposals. Reviewer 2's decision-program compiler and reviewer 1's
decision-first routing both assume a plan object of roughly this shape is available per request.
Producing one is currently a hand-authoring job of about 1.7KB per node, and nobody has produced
one at production scale. That prerequisite is unstated in both proposals and in our own roadmap.

**Revised D-2 cost.** The register's "2 fills, 2 raters" was wrong, which is exactly the failure
mode the header warns about. The real sequence is: author a narrative contract for a
production-scale skeleton, then bind devices for each arm, then fill, then rate. Contract authoring
for the 101-node `the-midnight-frequency` (39 forks, 18 endings) is in flight as the first step,
and is useful under every version of D-2 and to anyone re-specifying an architecture, so it is not
wasted if the rest is rescoped.

The catalog median is 149 nodes. 101 was chosen over 149 deliberately: it is a fourfold increase in
forks over the pilot (39 against 11), which is enough to answer whether an effect resting on three
forks dilutes at scale, at roughly two-thirds the authoring cost. If the effect survives at 101 a
further test at 149-plus is warranted; that tradeoff is recorded rather than hidden.

### D-2 design, pre-registered 2026-08-10 before any binding or fill exists

The contract is authored and independently verified: 101 nodes, 39 forks, 18 endings, 122 facts,
zero fact-closure violations under a second implementation of the closure check, zero em-dashes,
and `choice_semantics` written at the reference's device-agnostic altitude throughout.

Three books over that one contract, mirroring the pilot exactly:

| Book | World | Bound code form | Reasoning kind of its code chain | Role |
| --- | --- | --- | --- | --- |
| P | world 1 | `number_group_code` | COMPUTE, derive a value by rule | base |
| Q | **world 2** | `letter_grid` | COMPUTE, derive coordinates by rule | **control** |
| R | **world 1**, same as P | `pictogram_code` | MATCH, recognise a correspondence | **treatment** |

`rhythm_code` is deliberately excluded from all three. It is the exact case two annotators split on
in D-3c, and using it here would import an unresolved vocabulary boundary into a test meant to
settle something else.

As in the pilot, the treatment shares the base book's world while the control changes world
wholesale, so the comparison is again biased against the treatment.

**The prediction, fixed now:** raters will judge the P/Q pair MORE decision-repetitive than the P/R
pair, and the `reasoning_kind` measure over the code chain will order them the same way. If the
effect is real and survives a fourfold increase in forks, both hold. If it is an artifact of an
eleven-fork graph, the rating ordering will collapse or reverse.

**What would falsify it, stated in advance:**

1. Raters do not order the pairs P/Q more repetitive than P/R, or split.
2. The ordering holds for raters but the `reasoning_kind` chain measure does not reproduce it,
   which would mean the measure worked on the pilot by luck.
3. The measure reproduces it but only on a fork subset chosen after the fact. The chain is defined
   in advance by the contract's own `code_forms` note, which names its nodes: `n_start`, `n_decode`,
   `wt_gate`, `cn_marquee`, `hb_shed`, `lb_green`, `bh_wind`, `f_answer_script`, `e_win_signoff`.

**Guards before any rating**, unchanged from the pilot: device collision 0.000 between all three
bindings, fill integrity, full validator gate, prose craft, zero em-dashes, distinct titles. A
round that fails a guard is rebuilt, not caveated.

### D-3b result, and the pre-registration D-3c must satisfy

Attaching each plan's binding flips the field the test was built around. Over all 28 fork options,
`reasoning_kind` becomes the one field of six that orders the pairs as readers did, control 0.857
against treatment 0.750. Every other field still inverts, `stake` among them.

Splitting the forks by what they touch shows why the blended number is muted, and gives a far
sharper picture. **Both subsets are defined from the contract's own `world_recipe`, which states
that the book's one indexing code is "used consistently from the notice to the bench to the back
panel" with one hint carrier per zone. They are derivable without seeing a single label.**

| Fork subset | Control pair | Treatment pair | |
| --- | --- | --- | --- |
| Puzzle-chain forks, the six the code runs through | **1.000**, identical at every one | **0.000**, different at every one | agrees with readers |
| Entry forks, the three the world change reframes | 0.000 | 1.000 | inverts |

The control's two books bind different codes, `clock_arithmetic` and `rhythm_code`, that are the
same *kind of thinking*: decode a notation, set a dial. They therefore carry identical reasoning
kinds down the whole chain. The treatment's `pictogram_code` matches a shape to an object and
differs at every link. That is exactly the split both raters drew unprompted, recovered here from
the plans alone with no prose.

The entry forks are the scenery leak in isolation: the control's world change turns `PERCEIVE` and
`EXERT` into `INFER` with no change of act, inverting perfectly.

**Stated honestly:** the subsets are principled and derivable in advance, but they were applied
after these labels existed, and this is one annotator. That is why D-3c exists and why its analysis
is fixed here first.

**Pre-registered for D-3c**, before the second annotator's labels exist:

1. Primary: `reasoning_kind` over the six puzzle-chain forks must show control reuse strictly
   greater than treatment reuse.
2. The entry forks are expected to invert again. That is the scenery-leak prediction, and its
   failing would itself be informative.
3. Nothing else will be reported as a headline. Any further slicing is exploratory and labelled so.

### D-3c result: the direction replicates, the magnitude does not

| Pre-registered measure | Annotator C | Annotator D |
| --- | --- | --- |
| `reasoning_kind`, puzzle chain, control | 1.000 | 0.333 |
| `reasoning_kind`, puzzle chain, treatment | 0.000 | 0.167 |
| Primary verdict | agrees with readers | agrees with readers |
| Entry forks (predicted to invert) | inverts | inverts |
| All 28 options, `reasoning_kind` | agrees (0.857 / 0.750) | tied (0.750 / 0.750) |

**The pre-registered primary passed under both annotators, and the scenery-leak prediction held
under both.** That is the honest positive. But annotator C separated the pairs 1.000 against 0.000
and annotator D only 0.333 against 0.167, and over the full option set D's `reasoning_kind` ties
rather than agreeing. A result that survives replication in sign but loses most of its magnitude is
not yet a metric.

**The cause is localised and nameable.** Inter-annotator kappa on `reasoning_kind` is 1.000 on the
arithmetic plan and 0.919 on the pictogram plan, but **0.719 on the rhythm plan**. The two
annotators split on one judgement: is "read each pull as long or short and let the repeating phrase
spell out the setting" `COMPUTE` or `MATCH`? C said `COMPUTE`, D said `MATCH`. Both readings are
defensible, and that single call drives most of C's clean separation, because it decides whether the
control's two books share a reasoning kind or not.

So the v2 vocabulary has an underspecified boundary exactly where the construct does its work:
**decoding a symbolic notation** sits between "derive a value by rule" and "compare against a
pattern", and the definitions do not say which.

**A warning about the obvious next move.** Sharpening the boundary would resolve the ambiguous case
in whichever direction the sharpening is written, and the direction that rescues the clean result is
the one a motivated author would choose. Any such rule must therefore be treated as a *reliability*
fix and must not be reported as re-confirming the hypothesis on these same three plans, which would
be circular. Re-testing validity requires artifacts this vocabulary has never seen, which is D-2.

### D-5 result: the instrument detects a pair we know is bad

The contaminated arm was kept precisely so the instrument could be tested against a known answer.
Both raters read it blind, in opposite orders, against the same base book.

| Question | Contaminated pair | Clean pair |
| --- | --- | --- |
| Same kinds of actions | 5, 5 | 5, 4 |
| Same tradeoffs | 5, 5 | 4, 4 |
| Different consequences *(high good)* | 2, 2 | 3, 3 |
| Repeated sequence | 5, 5 | 5, 5 |
| Meaningful and informed *(high good)* | 3, 4 | 4, 5 |
| **Solution transfer** *(high bad)* | **5, 5** | **2, 2** |
| Forced comparison | **more similar**, high confidence both | less similar |

Both raters independently found the verbatim reuse the binding had caused, quoting the identical
remedy sentence from both books and noting that the two puzzles reduce to the same arithmetic and
land on the same answer. One put it exactly right: "A child who read alpha does not solve delta's
puzzle; they recognise it."

**This validates the ratings behind the headline result.** An instrument that could not separate a
pair sharing 14 of 24 props from a clean one would have made every earlier rating uninterpretable.
It separates them by three points on Q6, unanimously.

**Q4 saturated for the third consecutive run** (5, 5 against 5, 5), and Q1 nearly so. Both raters
warned, unprompted and in the same terms, that an evaluator scoring on fork shape alone would
report a null and be wrong. Q1 and Q4 should be retired from the scored instrument and kept only as
a description of the condition.

One rater noted a mismatch that strengthens rather than weakens the result: the contaminated book
and the clean book share a framing the base book does not, so the contaminated pair had the *less*
similar opening premise and still won on decision repetition.

## B. Architectures that do not depend on the broken instrument

| ID | Test | Source | Thesis | Cheapest experiment (proposer's) | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| M-4 | Stake economics | in-house, from rater testimony | Not *what* the goal is but whether failure costs anything. The treatment's goal imposed a live global constraint, a closing clock and a carrying limit and damage that persists, which re-prices every fork; the control's goal change did not. Both raters cited this unprompted, one noting that forcing is a free do-over in both control books and has a price in the treatment. | Two books, same graph, non-colliding bindings, same goal, differing only in whether failure is free. Existing rig. | The two books rate as repetitive as each other, meaning a reader does not price failure into how a choice feels. | queued |
| M-2 | World-graph tours | in-house | A graph is a *world*, not a book; a book is a validated subgraph tour. The catalog already holds graphs at 677, 551 and 250 nodes. | Take the largest 10-13 graph, cut two disjoint tours by hand, fill both, rate. Tests coherence as much as diversity. | Tours read as incoherent, because the large graphs were authored assuming roughly linear progression rather than as worlds. | queued |
| Q-2 | Cross-skeleton recombination | framework Q2 | Subtree grafting is the only mechanism that has ever cleared the anti-clone floor, and has never been evaluated for reader-perceived distinctness or coherence cost. | Graft subtrees between two catalog graphs, fill, rate for distinctness and for coherence damage. | Grafts read as incoherent, or as no more distinct than a plain sibling pair. | queued |
| Q-3 | How close is the skeleton-free path | framework Q3, brief 5.3 | Named the cheapest outstanding experiment before this programme started, and never run. | Per brief section 5.3. | The skeleton-free path produces structurally invalid graphs at a rate that no gate can absorb. | queued |
| Q-5 | Does the fill match its contract | framework Q5 | Nothing verifies finished prose against the node obligations it was written to satisfy. This is S4's unaddressed second weakness and it is independent of everything else here. | One model pass judging entailment over all 49 obligations of one book, plus a deterministic lexical triage scored against it. | Fired in the useful direction: fills do substantially satisfy their contracts, so the interesting result is that a deterministic check cannot verify it. | **done** |

### Q-5 result: the fills are faithful, and only a model can tell you so

A blind pass judged every one of the 49 `(node, obligation)` pairs of one book against its prose.

| Verdict | Count |
| --- | --- |
| DELIVERED | 44 |
| PARTIAL | 5 |
| MISSING | 0 |
| CONTRADICTED | 0 |

Nothing is missing or contradicted, including the hard cases: the two multi-parent merges, the
four-way room split, and all eight endings. **S4's unaddressed second weakness turns out not to be
a defect in practice**, at least on this book, which is a real answer to a question that has been
open since the skeleton architecture was adopted.

The five partials are specific and worth fixing rather than dismissing:

- `logic_earned` at `n_stairs` and `n_pendulum`. Two of the four exploration rooms do not teach the
  dial's arithmetic the way the other two do, so a reader entering the finale by those paths carries
  a pattern with no way to convert it. This is **path-dependent under-preparation**, invisible to
  any whole-book measure, and it is the only finding here with a direct reader consequence.
- `dial_test_live` at `n_clockface`. The plate states what to set but never that guessing costs
  anything; the stated cost belongs to forcing, a different option.
- `trust_bond_formed` at two of its three endings, where the bond is implied rather than made.

**The deterministic triage failed against this ground truth**, and the numbers are worth recording
because they set expectations for anyone tempted by the cheap version: precision 0.167, recall
0.600. It flags 18 obligations, of which 3 are real, and misses 2 of the 5. The two misses both
scored *above* zero, which is the diagnosis: lexical support tracks whether a node is about the
right subject, and the failures that matter are nodes about the right subject that do not close
the obligation. `scripts/check_fill_fidelity.py` is kept as a reading order and cannot gate.

### Q-1 result: the shelf is as thin as claimed, and it is the wrong shelf to count

The counting was never done, so it is done here. Across all six bands:

| | Count |
| --- | --- |
| Skeletons in the catalog | 61 |
| Band-by-length cells | 17 |
| Mean skeletons per cell | 3.6 |
| Cells holding 4 or fewer | **13 of 17** |
| **Skeletons carrying a narrative contract** | **2 of 61** |

The framework's premise holds: 13 of 17 cells hold four skeletons or fewer, so a child who
requests four books in one cell has met every distinct graph it contains. The 10-13 band is 11
skeletons over 1,610 nodes with a median of 149.

**But depth in this catalog is not the capital that matters, and this programme is why.** Every
measure built here runs off a *narrative contract*, and 2 of 61 skeletons have one. Measured on the
one that ships with the catalog, a contract costs about 1.7KB per node of hand-authored
specification; the catalog's 11,458 nodes would be roughly 17MB of it. Buying more skeletons buys
graphs that no measure in this programme can score and that no architecture proposed to us can plan
over.

**And the unit of that purchase is not yet known, because D-6 decides it.** If contracts can be
shared across the books of a series, the unit is contracts-per-skeleton and depth is a bounded,
one-time cost. If `AL-208` stands unrepaired and each book needs its own contract, the unit is
contracts-per-book, the cost scales with readership rather than with catalog size, and **skeleton
depth buys nothing at all**: a deeper shelf of graphs does not reduce the number of contracts you
must author per child.

So Q-1 is answered as far as counting can answer it, and it is downstream of D-6 rather than
independent of it. That is a change from how this row was filed: it was listed as a purchasing
decision that needed no research, and it turns out the research decides which purchase it is.

## C. Architectures gated on D-3

Each of these emits, scores, or optimises decision signatures. Running one before D-3 lands
measures with an instrument known to invert.

| ID | Test | Source | Thesis | Cheapest experiment (proposer's) | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R2-1b | Decision-program compiler | reviewer 2 | The manual precondition test is **done** and passed, thinly. Next step is a minimal DecisionProgram schema, 20 candidate maps without prose, blinded rating, full prose for the best 4 to 6. | 20 plan-only generations, blinded rating | Compiled decision maps rate no better than hand-authored ones. | blocked on D-3 |
| M-3 | Decision-axis scheduling | in-house | Classify every fork by the kind of decision it asks and schedule kinds per book, making decision variety a solvable, verifiable scheduling problem. | Schedule axes over the pilot graph, fill, rate. | Second-order by construction: it needs scene identity already free, so it fails if forks cannot be repurposed. | blocked on D-3 |
| R1-1 | Decision-first abstract routing | reviewer 1 | Shape-only graph as a state-routing machine; sample the decision set away from the child's prior books, then map onto the graph. | 5 books on one abstract skeleton with explicitly varied decision sets; measure choice-text overlap by embedding. Proposer: ~10 generations, 2 human hours. | Choice embeddings are no more separated than S4's, or the abstract state changes cannot be cleanly mapped to varied decisions. | blocked on D-3 |
| R1-3 | Repulsive generation via obligation contracts | reviewer 1 | Keep the current architecture; feed the child's prior action semantics in as a repulsion penalty during contract generation. | Generate book 2 with book 1's action semantics as a negative prompt; compare action overlap against the S9 baseline. Proposer: 2 generations, 1 human hour. | Repulsion exhausts natural choices and produces bizarre action semantics, the proposer's own stated failure mode. | blocked on D-3 |
| R2-4 | Portfolio generation with semantic repulsion | reviewer 2 | Generate K decision programs per request, validate, and select on a quality-minus-novelty objective before any prose. A cross-cutting selection layer over R1-1 or R2-3, not a standalone fix. | 10 requests by 8 programs, 80 short plan generations, no prose. Compare random, best-quality, and combined-objective selections; blinded raters see only choice maps. Proposer: 4 to 8 rating hours. | The novelty scorer rewards bizarre or low-quality decisions, or all candidates share one model's preferred patterns. | blocked on D-3 |

## D. Capital and library work, not research

| ID | Test | Source | Thesis | Cheapest experiment (proposer's) | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R2-2 | Typed choice-capsule library | reviewer 2 | The reusable unit is a fork-to-join *choice capsule*, not a scene. Mine the existing 11,458 nodes across 61 graphs rather than authoring a new library. | Extract 12 to 20 capsules from three existing graphs, place into compatible regions of the pilot graph, produce six decision programs as scene plans and choice cards only. Proposer: 20 to 40 human hours for the first set. | Cosmetically different capsules collapse to the same decision family, making the library a new finite formula. | queued |
| R1-2 | Component-based narrative assembly | reviewer 1 | Classical planner (ASP or STRIPS) over a scene library with preconditions and effects; validity by construction rather than by LLM verification. | 10 plot outlines from a 20-scene library; evaluate cohesion and decision overlap manually. Proposer: low compute, ~4 human hours. | The solver produces logically valid but narratively disjointed sequences, the proposer's stated "so what?" problem. | queued |
| R2-3 | Decision-first attributed graph grammar | reviewer 2 | Compile a valid topology from invariant-preserving productions after sampling the decision portfolio. Most ambitious; the proposer explicitly says it must not precede the manual test, which is now done. | One branch-and-bottleneck grammar, three productions, 12 hand-authored decision frames, 50 structural plans without prose, deterministic verification, prose for 4. Proposer: 2 to 4 engineer-weeks after the decision schema exists. | Generated shapes are valid but dramatically flat, or the grammar's production repertoire becomes its own fingerprint. | queued |
| Q-1 | Does catalog depth solve it | framework Q1 | A child exhausts a cell by roughly their fourth request at 3 to 4 skeletons per cell, and demand concentrates on medium length while the catalog is flat across lengths. | Not a research question. A capital question about depth against the demand curve. | Not falsifiable as stated; it is a purchasing decision. **But which purchase is now decided by D-6, and the counting has been done.** See below. | **done, ANSWERED and reframed** |

## E. Retired

| ID | Test | Why retired |
| --- | --- | --- |
| M-1 | Goal transform | **Refuted for free from data already held, no fill spent.** The option proposed varying what the reader is trying to do. All three books in the 2026-08-10 run already have different goals (prove-and-earn, reconstruct-and-remember, salvage-and-triage), and the control pair differs in goal while rating as the *more* repetitive of the two. Varying the dramatic question is therefore not sufficient. Superseded by M-4, which names the property the treatment's goal actually carried. |
| AL-199 | Per-book illusory-choice gate | Owner ruling, spec section 9.9. Loop-back exploration paths are a convention of the form, not a flaw; sweeping every room is the play. The structural observation stands, the defect framing does not. |
| Q-4 | Replicate the topology finding | The finding it would replicate was withdrawn. Topology is not itself the fingerprint (spec section 8.3), and the branch-obligation screen that replaced the claim has since been shown one-way (`AL-197`). Superseded by D-2. |

---

## Duplicate map

The research brief's section 8.4 families, and where each is actually tracked:

| Brief 8.4 family | Tracked as |
| --- | --- |
| Shape-only skeletons | R1-1 |
| Scene library plus recombination | R1-2 and R2-2 |
| Grammar over patterns | R2-3 |
| Planner-based | R1-2 |
| Decision-first inversion | R1-1 and M-3 |
| Explicit inter-book repulsion | R1-3 and R2-4 |

## Related

- [Decision-variance experiment spec](./decision-variance-experiment-spec-2026-08-10.md), the run that produced the D rows
- [Decision signature labelling principle](./decision-signature-labelling-principle.md), the instrument D-3 must replace
- [Research brief](./cyo-generation-research-brief-2026-08-10.md), the document handed to the two external reviewers
- [Framework problem and structures](./cyo-framework-problem-and-structures-2026-08-10.md), section 6, the Q rows
- [Authoring lessons log](./authoring-lessons-log.md), `AL-195` to `AL-202`
