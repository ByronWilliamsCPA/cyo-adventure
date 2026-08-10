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

**That re-specification is now done, and it changes this section.** All five architecture rows in
section C have been re-specified in
[the architecture re-specification](./architecture-respecification-2026-08-10.md). **None turns out
to be blocked on repairing the signature vocabulary.** Four are unblocked by swapping their
objective or their layer; M-3 is blocked on a contract schema field, which is smaller and far
better defined. The framing above, that six rows wait on an instrument, is superseded: they waited
on a re-specification, and what replaces the broken instrument for these purposes is D-4 tier 1
plus the shared-gram guard, both deterministic and both already built.

---

## A. Instrument and replication work (do first)

| ID | Test | Question it settles | Method | Cost | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| D-1 | Separate the treatment's **three** bundled changes | Was the 2026-08-10 effect from the different kind of act, from the stake economics, or from the four rooms yielding distinct components? Raters cited act-kind at one fork and stakes at two, so the original two-way framing understated the confound. | Three arms on the same graph, each restoring one change to the control's setting while holding the other two. Rate each against the same base book with the six-question instrument. | 3 fills, 2 raters | Restoring any single change collapses the effect, which would name that change as the whole lever rather than one of three. | queued |
| D-2 | Replicate on a production-eligible graph | Does any of this survive off a 26-node outlier? The catalog median is 151 nodes and the pilot graph is not production-eligible. | Repeat the winning arm on a production-scale 10-13 skeleton, same protocol, same instrument. **Blocked on an artifact nobody noticed was missing: see below.** | **badly underestimated, see below** | The effect vanishes or inverts at production scale. | **running, at rating prep**: contract authored and independently verified (101 nodes, 39 forks, 0 closure violations); three bindings verified at 0.000 collision with only the 6 designed shared-world props; three fills complete and structurally clean (10.2k to 10.6k words each); cast renamed and titles separated. **HALTED AT THE GUARD BATTERY, not rated.** D-6 has since supplied the way forward and priced it: neither cheap repair suffices, so resuming D-2 needs the decisional stratum generated per book **and** the premise varied across arms. See below. |
| D-3 | DecisionSignature v2 over the contracts | Can a richer vocabulary agree with readers instead of inverting them? | Added `reasoning_kind` (compute, match, recall, infer, perceive, negotiate, exert) and `stake` (nothing, time, resource, access, standing, permanent) plus the three `AL-193` gaps, and re-annotated the three plans blind. | 2 annotators over 3 plans | Hit its own falsifier: still ranks the treatment pair as the more repetitive one. Annotator A 0 of 6 fields agreeing with readers, annotator B 1 of 6. `reasoning_kind` inverts under both (0.929 against 1.000, and 0.857 against 0.964). Not a reliability failure: kappa between the two annotators is 0.77 to 0.81 on `reasoning_kind` and 0.72 on `stake`, both clear of the floor. The new fields are labellable and do not discriminate. | **done, NEGATIVE** |
| D-3b | Same vocabulary over contract **plus binding** | Is the inversion a vocabulary problem or a layer problem? The contracts describe `n_clockface` as "answer the test on its own terms" and "fit the piece the way the diagram shows", which Rule 2 correctly calls one decision; the mechanic readers responded to lives in the binding (`clock_arithmetic`, `rhythm_code`, `pictogram_code`). | Identical annotation pass with each plan's bound devices attached. | 1 to 2 annotators over 3 plans | Ordering still inverts with the binding visible, which would mean the discriminating property is not in the plan at all and only the filled prose carries it. Did not fire. | **done, POSITIVE, 1 annotator** |
| D-3c | Confirm D-3b with a second blind annotator | Is D-3b reproducible, and does it survive a subset fixed in advance? | Second independent annotator, same three bundles, same brief. Analysis pre-registered below before the labels exist. | 1 annotator over 3 plans | The second annotator's `reasoning_kind` does not separate the pairs in the readers' direction over the pre-registered fork subset. Did not fire, but the margin nearly vanished. | **done, PARTIAL** |
| D-4 | Solution-transfer metric | Is the item that actually discriminated computable from a plan, rather than only ratable by a reader? | Formalise "these two puzzles resolve by the same operation to the same answer" against the three existing contracts, and check it reproduces the raters' Q6 ordering (4,4 against 3,3). Scored against **three** rated pairs rather than the one the row asked for, since D-5 supplied a second ordering. | deterministic, no model | Did not fire. Reproduces all three orderings strictly, and does so on the tier that uses no taxonomy. | **done, POSITIVE but narrow** |
| D-6 | Which repair unblocks D-2 | `AL-208` says D-2 converged because its arms shared one contract. That is a diagnosis nothing has tested, and three candidate repairs were proposed with no way to choose between them. | One contract, two bindings held constant, three conditions (`verbatim`, `neutral`, `diverge`), six independent 26-node fills. Outcome is the guard battery itself, so no rater is needed. | 6 fills, 0 raters | First falsifier did not fire: `verbatim` reaches 16.9 per 1000 against the pilot's 2.9, so contract sharing is confirmed as a cause. **Second falsifier substantially fired**: the best repair reaches 11.4, still roughly 3x budget and 4x the pilot. | **done, MIXED: diagnosis confirmed, neither tested repair sufficient** |
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

### D-6 result: the diagnosis is right, the cheap repairs are not enough, and the leak is not where we said

Six books authored, all six structurally clean (26 nodes, 2,722 to 2,865 words, no directive left,
no em-dash). Measured on **bodies only**, for a reason given below.

| Condition | Shared 4-grams per 1000 | Against budget 4.0 |
| --- | --- | --- |
| `verbatim`, one contract as written | **16.9** | 4.2x |
| `neutral`, wording flattened | **11.4** | 2.9x |
| `diverge`, told not to reuse the wording | **12.9** | 3.2x |
| pilot, **different** contracts, same graph, same bindings | **2.9** | passes |

**The first falsifier did not fire, so `AL-208` is confirmed as a cause.** Holding the graph, the
two bindings, the model and the isolation constant and changing only whether the arms read one
contract or two moves convergence from 2.9 to 16.9, a factor of 5.8.

**The second falsifier substantially fired, and this is the operative result.** The best repair
lands at 11.4, a 33 percent reduction that is still roughly three times budget and four times the
pilot. **Neither tested repair unblocks D-2.** `neutral` and `diverge` are within noise of each
other at n=1 per condition, and their ordering flips depending on whether labels are counted, so no
claim is made about which is better; the claim is that neither is enough.

**A confound was checked and eliminated rather than assumed away.** The pilot's shells shipped
pre-written choice labels, 13 of 35 identical between its two arms, while D-6's authors wrote every
label from scratch. That is a second difference between the two setups and it could have carried
the whole effect. It does not: **labels contribute zero shared 4-grams in every condition,
including the pilot**, so the entire signal lives in the bodies, which were authored from scratch
everywhere. Hence bodies-only above. (That labels do not converge here at all is itself a mismatch
with D-2's 41 to 51 identical menus, and is unexplained; the two candidates are scale and how
orthogonal the arms' `label_style` values happen to be.)

**Where the leak actually is, which is not where `AL-208` put it.** Tracing each shared gram to the
contract field whose vocabulary it draws on:

| Condition | shared | traces to `choice_semantics` | to `beat_hint` | to `premise` | to none of them |
| --- | --- | --- | --- | --- | --- |
| `verbatim` | 47 | 18 | 19 | **23** | 11 |
| `neutral` | 33 | 10 | 12 | **17** | 8 |
| `diverge` | 36 | 10 | 10 | **13** | 12 |

These categories overlap heavily, since premise vocabulary is largely just this story's subject
matter, so the attribution is indicative and not a partition. But the shape is clear and it
contradicts the diagnosis: **`choice_semantics` is not the main channel.** Roughly a quarter of
shared grams trace to no contract field at all and are same-model idiom (`AL-207`), which no
wording intervention touches, and the premise, which every condition shared by construction,
carries as much as either field a repair addressed.

### D-6 addendum: the generator's idiom floor, measured, and the budget is above it

The attribution above says roughly a quarter of shared grams trace to no contract field and are
same-model idiom. That invites a worry big enough to check directly: **if the floor is near the
budget, the guard is asking for something no generator can deliver and every architecture is
doomed on a technicality.** So the floor was measured, on book pairs sharing nothing but the model
and the age band, different graph, different contract, different world:

| Pair | Shared 4-grams per 1000 |
| --- | --- |
| clocktower/river against midnight-frequency/radio | 2.9 |
| clocktower/foundry against midnight-frequency/radio | 5.0 |
| clocktower/river against midnight-frequency, world 2 | 1.9 |
| **mean floor** | **3.3** |

Everything measured in this programme, on one scale:

| | per 1000 |
| --- | --- |
| generator idiom floor (nothing shared but the model) | **3.3** |
| **budget** | **4.0** |
| pilot pair, different contracts, same graph, same bindings | 2.9 |
| D-6 `neutral`, one contract, wording flattened | 11.4 |
| D-6 `diverge`, one contract, divergence instructed | 12.9 |
| D-6 `verbatim`, one contract as written | 16.9 |
| D-2 pair, one contract, 101 nodes | 50.1 |

Three things follow, and the first is a correction.

1. **The budget is above the floor, so it is reachable.** 4.0 against 3.3 is tight but real, and
   the worry is retired. Nothing said elsewhere in this programme should be read as implying the
   guard is unachievable.
2. **The pilot design already achieves the floor.** At 2.9 against a floor of 3.3, two books written
   from independently worded contracts over the same graph with the same bindings are
   indistinguishable from two books that share nothing at all. **One contract per book is not merely
   better, it is a solved problem**, and the only question is whether reuse can be bought back
   without giving that up.
3. **The repairs are nowhere near the floor.** 11.4 is 3.5 times it, so D-6's negative result is not
   a story about hitting an unavoidable limit. There is a factor of three of headroom that flattening
   the wording did not touch, which is consistent with the attribution finding that the repairs
   addressed one channel of at least four.

The floor also corroborates the attribution independently: a quarter of `verbatim`'s 16.9 is 4.2 per
1000, against a directly measured 3.3. Two different methods agreeing on the size of the
unreachable component is the strongest thing in this section.

**What that does to the repair list.** `AL-208` named three repairs and D-6 tested the two that
only touch `choice_semantics`. Both fall well short, and now we know why: they repair one of at
least four channels. The third repair, generating the decisional stratum per book, remains
untested, is the one [the architecture re-specification](./architecture-respecification-2026-08-10.md)
proposes, and **D-6 predicts it will also fall short of budget on its own**, because the shared
premise and the idiom floor survive it. Getting under budget looks likely to need the premise
varied per book as well, which is a much larger claim about what a reusable plan can hold.

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

### Q-3 design, pre-registered 2026-08-10 before any graph exists

Six story graphs for the 10-13 band, generated from scratch by six isolated authors given the JSON
format and nothing else: no skeleton, no catalog, no example story, and **no validator in the loop**.
Each is asked for 25 to 35 nodes, 5 to 9 endings, fully written prose, and is told which structural
properties matter.

**Withholding the validator is deliberate and it changes what this measures.** A production system
would run the gate and repair, so this is not a measure of what the skeleton-free path could
achieve. It is the **first-pass yield**, which is the number that decides the cost, and it is the
number nobody has.

**Scored deterministically**, no rater and no model:

1. **Hard structural failures**: a dangling choice target, an unreachable node, a non-ending node
   with no choices, an ending node carrying choices, a start node that is not the declared one, or
   any node from which no ending is reachable.
2. **The project gate** (`scripts/run_story_gate.py`), reported as blocked or not, with findings.
3. For each failure class, whether repair needs **authorial judgement** or is **mechanical** (a
   dangling target needs someone to decide where it should point; an ending carrying a leftover
   choice does not).

**Primary measure, fixed now:** the share of the six with zero hard structural failures.

**The falsifier requires both halves, stated before the numbers exist.** Q-3's falsifier as written
is "produces structurally invalid graphs at a rate no gate can absorb". A gate detects all six
failure classes above with certainty, so detection is never the issue and the falsifier has to be
read as a yield-and-repairability claim. It fires only if **fewer than half are clean AND the
dominant failure class needs authorial judgement.** A poor yield whose failures a repair pass fixes
mechanically is a cost to be priced, not a refutation.

**Two limits on whatever comes back.** Six graphs from one model is a small sample, and at 25 to 35
nodes against a catalog median of 149 this tests the easy end. A clean result licenses nothing about
production scale, and the register should not let it.

### Q-3 result: the graphs are sound, the policy is not, and nobody told the author the policy

**The pre-registered primary passed outright.** Six authors, no skeleton, no example story, no
validator in the loop, scored by `scripts/check_graph_structure.py` rather than by their own
self-checks:

| | Nodes | Endings | Forks | Structural failures |
| --- | --- | --- | --- | --- |
| graph_A | 30 | 7 | 10 | 0 |
| graph_B | 29 | 8 | 11 | 0 |
| graph_C | 33 | 9 | 18 | 0 |
| graph_D | 35 | 7 | 10 | 0 |
| graph_E | 34 | 7 | 25 | 0 |
| graph_F | 27 | 8 | 9 | 0 |

**Six of six, no dangling target, no unreachable node, no sink, no trapped cycle.** The thing a
skeleton was assumed to be load-bearing for, a well-formed graph, an unaided model does reliably at
this scale.

**And all six are blocked by the project gate.** That looks like a contradiction and is not:

| Blocking finding | Graphs | What it is |
| --- | --- | --- |
| `L1-7` branch depth out of range (10 to 14, allowed 0 to 9) | A, D, E, F | a band budget |
| `PL-25` first decision 1 node in, band floor 2 | B, C | a band policy |
| `L1-1` ending object fails the Storybook schema | D, E | a schema shape |

**Every one of these violates a constraint the author was never given.** The brief stated the
structural rules and the model hit all of them; it stated nothing about depth budgets, opening
floors or the ending-object schema, and those are exactly what failed. Read as a measure of story-
graph competence this is a pass; read as a measure of the brief it is a fail, and the brief was
mine. **What Q-3 has not tested is whether stating the constraints closes the gap**, which is the
obvious and cheap follow-up.

**Convergence, the reason D-6 promoted this row.** Fifteen pairs, bodies only:

| | per 1000 |
| --- | --- |
| generator idiom floor | 3.3 |
| budget | 4.0 |
| **Q-3, mean of 15 pairs** | **3.5** |
| Q-3, worst pair | 6.1 |

**On average, six stories sharing no plan at all sit at the idiom floor**, which is the cleanest
demonstration available that the convergence D-2 and D-6 measured comes from the shared plan and not
from the model. But 4 of 15 pairs breach the 4.0 budget, so "no shared plan" is not a guarantee.

**The worst pairs are the ones that converged on a premise, and this is where Q-3 meets D-6.**
The six titles are *The Time Capsule of Widow's Watch*, *The Sparrow Hollow Observatory*, *The Bell
Beneath Pike's Cove*, *The Moonbloom Grove*, *The Kite That Remembered* and *The Lighthouse
Frequency*. Two coastal mysteries about a lost signal or bell, two summer-camp discoveries in
woodland, and **all six are the same story: children find a thing left behind by an older person and
follow clues to it.** Nobody coordinated and nobody shared a plan.

D-6 found the `premise` to be the largest traceable channel of convergence and concluded that a
reusable plan must vary its premise per book. Q-3 shows that **removing the plan entirely does not
vary the premise**, because the model converges there on its own. The two results together say the
premise has to be varied by something that actively pushes them apart, and that neither sharing less
nor asking nicely will do it.

**Limits, as pre-registered.** Six graphs, one model, 27 to 35 nodes against a catalog median of
149. This tests the easy end and licenses nothing about production scale.

## A2. What D-6 costs every remaining fill-based row

D-6 is a result about method, not only about architecture, and it re-prices four rows that were
costed before it existed. **Any row that puts two or more books on one narrative contract will hit
the guard wall D-2 hit**, and no rating can be spent on the output. The pilot's structure, one
independently worded contract per arm, is the only fill design measured to pass.

| Row | Exposed to D-6? | Re-priced method |
| --- | --- | --- |
| **D-1** | **yes, badly** | "Three arms on the same graph" reads naturally as one contract with one change restored per arm. That is exactly D-6's `verbatim` condition, three times over. D-1 needs **three independently worded contracts**, not three fills over one. Its cost was "3 fills, 2 raters"; the real cost is three contract-authoring jobs on top. |
| **M-4** | **yes** | Same. Isolating stake economics tempts you to copy a contract and edit the stakes, which is the worst case: near-identical wording. Needs an independently worded contract per arm. |
| **M-2** | **no** | Two *disjoint* tours of one large graph share no nodes, so there is no shared per-node contract to leak. D-6 leaves M-2 alone. |
| **Q-2** | not by D-6 | Grafting needs contracts for both source graphs, and 2 of 61 skeletons have one (`AL-213`). Q-2 is blocked by contract coverage, not by convergence. |
| **Q-3** | **no, and this now counts in its favour** | The skeleton-free path has no shared plan by construction, so it sidesteps both the layer dilemma and the sharing constraint. It was filed as the cheapest untried experiment; D-6 makes it the only queued row that structurally cannot hit this wall. |

**One general lesson for the programme's costing.** Three rows in a row (D-2, M-4, D-1) were costed
in fills when the expensive artifact is the contract. Contract authoring is the unit of work here,
and until `AL-213` is addressed it is a hand job of roughly 1.7KB per node.

## B. Architectures that do not depend on the broken instrument

| ID | Test | Source | Thesis | Cheapest experiment (proposer's) | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| M-4 | Stake economics | in-house, from rater testimony | Not *what* the goal is but whether failure costs anything. The treatment's goal imposed a live global constraint, a closing clock and a carrying limit and damage that persists, which re-prices every fork; the control's goal change did not. Both raters cited this unprompted, one noting that forcing is a free do-over in both control books and has a price in the treatment. | Two books, same graph, non-colliding bindings, same goal, differing only in whether failure is free. Existing rig. | The two books rate as repetitive as each other, meaning a reader does not price failure into how a choice feels. | queued |
| M-2 | World-graph tours | in-house | A graph is a *world*, not a book; a book is a validated subgraph tour. The catalog already holds graphs at 677, 551 and 250 nodes. | Take the largest 10-13 graph, cut two disjoint tours by hand, fill both, rate. Tests coherence as much as diversity. | **Structurally confirmed for 18 of 21 large graphs, without a single fill**: they are linear-with-decorations, not worlds, so no two disjoint tours exist to cut. Three graphs survive, one of them in-band. See below. | **partially done, DETERMINISTIC PRE-TEST; the fill-and-rate half is unblocked on exactly 3 named graphs** |
| Q-2 | Cross-skeleton recombination | framework Q2 | Subtree grafting is the only mechanism that has ever cleared the anti-clone floor, and has never been evaluated for reader-perceived distinctness or coherence cost. | Graft subtrees between two catalog graphs, fill, rate for distinctness and for coherence damage. | Grafts read as incoherent, or as no more distinct than a plain sibling pair. | queued |
| Q-3 | How close is the skeleton-free path | framework Q3, brief 5.3 | Named the cheapest outstanding experiment before this programme started, and never run. **D-6 promotes it: a skeleton-free graph shares no plan by construction, so it is the only queued row that structurally cannot hit the convergence wall.** | Six graphs generated from scratch by isolated authors, format reference only, no skeleton and no validator in the loop. Score deterministically against the structural rules and the project gate. Analysis pre-registered below before the artifacts exist. | 6 generations, 0 raters | Did not fire. **6 of 6 structurally clean.** All six are nonetheless blocked by the project gate, and every blocking finding violates a constraint that was never stated to the author. | **done, POSITIVE on the pre-registered primary; see the split below** |
| Q-5 | Does the fill match its contract | framework Q5 | Nothing verifies finished prose against the node obligations it was written to satisfy. This is S4's unaddressed second weakness and it is independent of everything else here. | One model pass judging entailment over all 49 obligations of one book, plus a deterministic lexical triage scored against it. | Fired in the useful direction: fills do substantially satisfy their contracts, so the interesting result is that a deterministic check cannot verify it. | **done** |

### M-2 pre-test: 18 of 21 large graphs cannot supply two disjoint tours, and 3 can

M-2's falsifier ("tours read as incoherent, because the large graphs were authored assuming roughly
linear progression rather than as worlds") was written as something only a fill and a rating could
settle. Most of it is decidable from the graphs alone, and doing so costs nothing.

**The first attempt measured the wrong thing, and is recorded because the error is instructive.**
Maximum node-disjoint start-to-ending paths, by max-flow with unit node capacities, returns **1 for
all 21 graphs of 200-plus nodes**. Read naively that kills M-2 outright. It does not, because the
single cut node is in every case the world's **hub** (`n_hub`, `n_sort`, `c01_gate`, `muster_gate`)
sitting at depth 1 to 5. A hub is what a hub-and-spoke world is *supposed* to have, and two tours of
one world would both cross the town square. Strict node-disjointness is simply the wrong
requirement.

**The right test is whether the spokes can be partitioned.** Removing the hub and taking the
connected components of what remains gives the independent regions a tour could be cut from:

| Graph | Band | Nodes | Hub | Spoke sizes (those containing endings) |
| --- | --- | --- | --- | --- |
| **the-skyrail-heist** | **10-13** | 246 | `n_sort` | **83, 82, 77** |
| the-year-of-four-banners | 13-16 | 212 | `n_sort` | 83, 70, 56 |
| the-tricameral-city | 16+ | 240 | `n03` | 100, 73, 64 |
| the-tenfold-siege | 16+ | 677 | `a01_g1` | **656**, 3, 3, 3, 3, 3 |
| the-sunken-temple | 13-16 | 551 | `n_start` | **549** |
| the-pale-road | 16+ | 498 | `c01_gate` | **481**, 3, 3, 3, 3 |
| the-mapmakers-island | 10-13 | 225 | `n_start` | **223** |
| the-winter-of-the-wolf-queen | 10-13 | 250 | `n_hub` | **242**, 4 |
| *(13 further graphs)* | | | | same shape: one giant spoke, the rest of size 1 to 4 |

**Eighteen of the twenty-one have one spoke holding nearly every node**, with the remainder being
short early-exit endings of one to four nodes. There is no second region to cut a tour from. M-2's
falsifier is confirmed for those graphs on structure alone, and the size of the catalog is no help:
the 677-node graph is the worst offender at 656 of 677 in a single mass.

**Three are genuinely world-shaped**, with three balanced regions apiece. One of them,
`the-skyrail-heist`, is in the 10-13 band this programme studies, is 246 nodes, and offers three
regions of 83, 82 and 77 nodes each containing endings. **That is the graph M-2 should use, and
before this nobody knew which graph M-2 meant.**

So M-2 is neither dead nor open: its scope is now three named graphs instead of "the largest", and
its remaining half is the fill-and-rate, which is exposed to the contract-coverage problem
(`AL-213`) like everything else rather than to D-6.

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

**Three of these have now been re-specified, and "gated on D-3" turns out to be the wrong label for
all three.** See [the architecture re-specification](./architecture-respecification-2026-08-10.md).
In summary:

| | Was blocked on | Is actually blocked on | Cheapest unblocking step |
| --- | --- | --- | --- |
| R2-1b | D-3, a metric | nothing, once its programs carry bindings | re-scope to bound tuples, score with D-4 tier 1 |
| R1-1 | D-3, a metric | nothing, once it repels on the bound chain | swap the repulsion target and the measure |
| M-3 | D-3, a metric | a **contract schema field**, plus a reliability check on it | one annotation round on declared operations |

Two are unblocked by re-scoping alone; none needs the signature vocabulary repaired. The
re-specification also resolves the dilemma the brief's section 18 put to the reviewers, by
stratifying the plan into a **structural** part that may be shared freely (topology and fact graph,
which `AL-197` and `AL-212` prove do not determine the decision, so sharing them cannot make the
decisions repeat) and a **decisional** part that must be generated per book (`choice_semantics`,
`beat_hint`, the devices, the operation and the stake, which is simultaneously where D-3b locates
the property and where `AL-208` locates the fingerprint). The concrete change is that
`choice_semantics` and `beat_hint` move out of the reusable contract into the per-book bind step.
**D-6 tests the weakest version of that claim, so section 2 of the re-specification is provisional
until D-6 reports.**

| ID | Test | Source | Thesis | Cheapest experiment (proposer's) | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R2-1b | Decision-program compiler | reviewer 2 | **Re-specified**: a DecisionProgram is a set of (act, bound device, stake, consequence) tuples, not abstract decision descriptions, because a prose-free program is exactly the artifact D-3 rules out. | 20 candidates over one structural stratum, no two sharing a `choice_semantics` string, screened on D-4 tier 1, then blinded rating to confirm rather than produce a ranking, then prose for the best 4 to 6 with the shared-gram guard across all of them. | Twenty programs over one structural stratum still breach the shared-gram budget once prose exists, which would mean the structural stratum leaks wording too. | **re-specified, unblocked; cost now LOWER than proposed** |
| M-3 | Decision-axis scheduling | in-house | **Re-specified, and it is the biggest change of the three: stop classifying, declare.** Three attempts to recover the axis from an artifact have failed (v1 inverts, v2 inverts and ties with kappa clear of the floor, the deterministic version classifies 2 of 6 props on an unseen contract). The axis is not recoverable by model or by word list. | Add `operation` and `stake` to each fork option in the contract's decisional stratum, authored when the author already knows. Scheduling over declared values then needs no annotator, no kappa study and no lexicon. | Authors cannot agree on the declared operation at acceptable reliability. **Live chance of firing**: D-3c already found the derive-against-compare boundary contested at kappa 0.719, so the operation vocabulary needs settling first. | **re-specified; blocked on a schema field, not a metric** |
| R1-1 | Decision-first abstract routing | reviewer 1 | **Re-specified**: repel on the **bound solution chain** (devices used, operations asked, answers reached), not on the abstract decision set. Its shape-only graph is now a virtue rather than an accident: it is the structural stratum, which may be shared freely. | Unchanged in size, 5 books on one abstract skeleton. Measure with solution transfer against the child's prior books; keep choice-text overlap but demote it to a convergence guard, which is what `AL-208` shows it actually measures. | **Replaces the proposer's**: repulsion succeeds on the bound chain (transfer near zero across all five) and blind readers still call the books decision-repetitive. That would be the most informative negative available from any row here. | **re-specified, unblocked** |
| R1-3 | Repulsive generation via obligation contracts | reviewer 1 | **Re-specified, and promoted.** Needs no re-scoping, only its objective swapped: repel on the bound solution chain and score with D-4 tier 1, not on device-agnostic action semantics. **It generates a fresh contract per book by construction**, which is exactly `AL-208`'s untested third repair, so it doubles as the experiment that would settle D-6's open half. | Unchanged in size, 2 generations. Add the shared-gram guard across the generated set, which the proposal lacks entirely. | The proposer's own (bizarre action semantics) still stands, but D-6 predicts it hits a different one first: per-book contracts still share a premise and a generator idiom, so it may miss budget without varying the premise too. | **re-specified; run BEFORE R2-1b** |
| R2-4 | Portfolio generation with semantic repulsion | reviewer 2 | **Re-specified**: the selection layer is sound, its novelty term is not. Replace signature overlap with D-4 tier 1, plus the shared-gram rate once prose exists for the selected few. Both deterministic, so selection stays cheap, which was the proposal's main attraction. | Unchanged, 80 plan generations. | The proposer's second falsifier is now measured rather than hypothetical: D-6 puts roughly a quarter of convergence in generator idiom, and **a portfolio can only select away variance it produces**, so the floor survives any K. | **re-specified, unblocked** |

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
