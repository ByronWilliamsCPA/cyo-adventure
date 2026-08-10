# Re-specifying the three gated architectures

> Opened 2026-08-10. R2-1b, R1-1 and M-3 are marked `blocked on D-3` in the
> [diversity test register](./diversity-test-register.md), but that label is wrong in a way that
> matters: they are not waiting for a metric to be repaired, they are **specified to plan at a layer
> that provably does not contain the property they exist to vary**. Rescheduling them changes
> nothing. This document re-specifies each one, and states the two constraints all three now inherit.

## 1. The two constraints, and why they pull against each other

Everything below follows from two measured results. Neither was known when the three architectures
were proposed, and each on its own would be a design note; together they are a dilemma.

**Constraint A, the layer constraint.** A device-agnostic plan does not contain the property readers
respond to. Three independent blind annotators scoring plans alone ranked our book pairs in the
*opposite* order from readers, on every field of two successive vocabularies (D-3). Attaching each
plan's binding flipped the decisive field into agreement (D-3b, replicated in direction by D-3c).
The plans describe one fork as "answer the test on its own terms" and another as "fit the piece the
way the diagram shows"; the arithmetic-against-shape-matching distinction that both readers named
lives in the *binding*. A separate result closes the escape route: the fact graph does not carry the
decision either, since four materially different options at one fork own an identical obligation
(`AL-197`, and `AL-212` arriving at it from the other side).

> **So: to represent what readers respond to, a plan must reach down to the bound device.**

**Constraint B, the sharing constraint.** Any artifact reused verbatim across books becomes those
books' shared fingerprint, in its own wording. Three isolated authors writing from one narrative
contract produced 59 to 64 shared four-grams per 1000 against a budget of 4.0, and 41 to 51
identical choice menus of 131, where arms reading *different* contracts scored 1.8 to 2.7 and zero
(`AL-208`). Bindings were verified non-colliding and label styles differed across arms, so neither
explains it. The shared wording does.

> **So: the more of a plan is shared across books, the more those books converge.**

**The dilemma.** Constraint A pushes the binding up into the plan. Constraint B punishes every
sentence the plan holds. Satisfying A by binding the plan makes the plan per-book, which destroys
the reuse the plan exists for. This is the question put to our reviewers in the brief's section 18,
and none of the three architectures below names it.

## 2. The move that resolves it: stratify the plan by whether it carries words

The dilemma dissolves once you notice that constraints A and B bite on **different parts of the same
object**. Constraint B is about *wording*. Constraint A is about *the decision*. A narrative contract
currently mixes both into one artifact and shares the whole thing.

Split it:

| Stratum | Contents | Shared across books? | Why that is safe |
| --- | --- | --- | --- |
| **Structural** | topology, fact graph, `entry_state`, `establishes`, `forbids`, typed slot declarations, `world_recipe` categories | **yes, freely** | Carries no prose that reaches an author's page. `AL-197` and `AL-212` show it provably does not determine the decision, which is exactly why sharing it cannot make the decisions repeat. Its long-standing weakness becomes its licence. |
| **Decisional** | `choice_semantics`, `beat_hint`, the bound devices, the operation each puzzle asks, the stake each option carries | **no, generated per book** | This is where constraint A locates the property and where constraint B locates the fingerprint. They are the same stratum. Generating it per book satisfies both at once. |

**The single concrete change this implies:** `choice_semantics` and `beat_hint` move out of the
reusable contract and into the per-book binding step, alongside the devices. Today they sit in the
contract, which is the shared artifact, and that is precisely the placement `AL-208` punishes.

This is cheap. It does not require authoring one contract per book, which is what our pilot did
without realising that was the load-bearing difference. It requires authoring one contract per
*skeleton*, with a hole where the wording goes.

**It is also, as of this writing, not proven.** D-6 tests the weakest version of it (flatten the
shared wording, rather than remove it) against two alternatives, with the prediction and falsifiers
fixed in advance. If D-6's `verbatim` condition does not converge, constraint B is misdiagnosed and
section 2 should be discarded rather than defended.

### 2.1 D-6 reported, and it corrects section 2 rather than confirming it

D-6 has since run. Constraint B survives: holding graph, bindings, model and isolation constant and
changing only whether two arms read one contract or two moves convergence from 2.9 to 16.9 shared
four-grams per 1000, against a budget of 4.0. Sharing a plan does make books converge.

**But the stratification above is necessary and demonstrably not sufficient, and the reason is that
section 2 put the leak in the wrong place.** Tracing shared grams to the contract field they draw
on, `choice_semantics` accounts for well under half; the `premise` carries as much or more, and
roughly a quarter of shared grams trace to no contract field at all and are same-model idiom
(`AL-207`). Flattening the shared wording bought a 33 percent reduction and left the result at
roughly three times budget.

Three corrections follow, and they should be read as amendments to the table in section 2 rather
than as footnotes to it:

1. **The `premise` belongs in the decisional stratum, not the structural one.** It looks structural,
   it is the story's dramatic question, and section 2 tacitly left it shared. D-6 says that is the
   single largest traceable channel. A structural stratum that is genuinely wordless holds topology,
   fact *names*, typed slots and categories, and no prose at all, the premise included.
   **Read this as "not the same sentences", not as "a different story every time".** D-6 measured the
   premise's weight *within a shared contract*, where it is shared verbatim; section 2.2's finding
   then shows the threshold is sentence identity. Two books may pose the same dramatic question in
   separately written words. Indeed the pilot pair that filled at the floor shares 312 shared
   four-grams per 1000 of premise vocabulary, more than the arm that holds the goal constant does.
2. **There is an idiom floor no wording intervention reaches, and it has since been measured at
   3.3 shared four-grams per 1000**, on book pairs sharing nothing but the model and the age band.
   Two books written by one model from one situation converge on "let out a breath" and "for a long
   moment" whatever the plan says. **The budget is 4.0, so the floor is below it and the guard is
   achievable**; an earlier draft of this point implied the floor might make the budget unreachable
   and that was wrong. What the floor actually establishes is the opposite and more useful thing:
   the pilot's one-contract-per-book design already sits at 2.9, indistinguishable from books that
   share nothing, so **not converging is a solved problem** and the entire question is whether reuse
   can be bought back without giving it up. D-6's repairs sit at 3.5 times the floor, so they failed
   with a factor of three of headroom still unclaimed.
3. **Section 2 claimed the dilemma "dissolves". It does not; it narrows.** Stratifying removes the
   part of constraint B that comes from shared wording, which is most of the traceable part and
   about two thirds of the total. What remains is a shared *situation* producing shared idiom, and
   nothing in this document addresses that. The honest claim is that stratification is a necessary
   first move whose sufficiency is now measured and inadequate.

### 2.2 The mechanism, now measured: generate from the structure, never from a sibling

Section 2 says the decisional stratum must be generated per book and does not say how to stop each
generation converging on the last. That gap has since been closed by measurement, and the answer is
blunt.

Two contracts were authored for the same 26-node graph under the same requirement, differing in one
variable: whether the author could see an existing contract for that graph.

| | Shared 4-grams per 1000 with the existing contract |
| --- | --- |
| reference shown, plus an itemised instruction to diverge from it | **126.7** |
| **reference withheld**, format supplied as a written schema | **1.0** |

**A 127-fold reduction from a single change to what the author was shown**, with both artifacts
structurally sound on the same independent checks. Instructing divergence is close to useless here,
and it is the intervention every proposal reaches for first, including two of the five below.

So the mechanism is: **generate each book's decisional stratum from the structural stratum alone,
and never from a sibling book.** The structural stratum is wordless by section 2.1's amendment, so
there is nothing there to converge on. This is implementable, cheap, and it is the concrete form of
`AL-208`'s untested third repair.

**And the bar is lower than section 2.1 implied, which is a correction to this document.** Checking
the new contract against the one whose fills were already rated turned up something unexpected: the
pilot's two contracts are **118.4** shared four-grams per 1000, almost exactly as similar as the
attempt discarded above as unusable, and **their fills sat at the floor, 2.9**. They share vocabulary
heavily while sharing **0 of 35 `choice_semantics` strings**.

Convergence therefore does not work by degree of lexical similarity, which is how 2.1 read it. Two
authors handed *the same sentence* converge on it; two authors handed *different sentences sharing
vocabulary* do not, even at 118 per 1000. **The threshold is sentence identity.** A per-book
decisional stratum does not have to be independent of its siblings, only separately written, which
any separate generation gives for free. Withholding the reference is good practice and is not the
requirement.

*Limit:* the pilot's contracts also differ in premise, so sentence-difference and premise-difference
are bundled in the single available comparison. Which one does the work is untested and is the
cheapest open question in this line.

**It does not touch the premise, and that is now measured too.** The author who never saw the
reference independently chose a clock tower, against a reference set in a clocktower. Wording as
independent as anything in this programme; the same setting. Withholding closes the wording channel
completely and the premise channel not at all, which means section 2.1's point 1 needs a mechanism
of its own rather than the same one. A repulsion term over premises is the obvious candidate and is
where R1-3 should point.

The re-specifications in sections 3 to 5 are unaffected in substance: each is still unblocked, and
each still wants the same contract field. What changes is the guard they must pass. **Any of them
that reuses one structural stratum across books must run the shared-gram check across the whole
generated set, and must expect to fail it on the first attempt.** That check is the one that stopped
D-2, no proposal we received includes it, and D-6 shows it is not a formality.

## 3. R2-1b, the decision-program compiler

**As proposed.** Define a minimal DecisionProgram schema, compile 20 candidate decision maps without
prose, rate them blind, write full prose for the best four to six.

**Why it cannot run as written.** A DecisionProgram without prose is exactly the device-agnostic
artifact constraint A rules out. Twenty such maps would differ in ways three annotators have already
shown do not track what readers notice, and the blinded rating would rank them with an instrument
measured to invert. The proposal's own cheapest experiment is the part that breaks.

**Re-specified.**

1. A DecisionProgram is a set of **(act, bound device, stake, consequence)** tuples, not a set of
   abstract decision descriptions. The device is part of the program, not a later substitution.
   This is the minimum that makes the artifact scoreable at all.
2. Compile 20 candidates over one **structural** stratum, generating the decisional stratum fresh
   for each. No two candidates may share a `choice_semantics` string; that is checkable
   deterministically before any rating and costs nothing.
3. Score candidates on **solution transfer, tier 1** (`scripts/check_solution_transfer.py`), which
   reproduces every reader ranking we hold and uses no taxonomy. Do **not** score on
   decision-signature overlap, which inverts, and do not score on the operation tiers, which do not
   generalise off the contract their lexicon came from (`AL-211`).
4. Blinded human rating is still required, but it now confirms a ranking rather than producing one,
   which is a much cheaper use of rater time.
5. Prose for the best four to six, then the full guard battery **including the shared-gram check
   across all six**, which is the check that stopped D-2 and which no proposal currently includes.

**New falsifier.** Twenty programs compiled over one structural stratum still converge on shared
four-grams above budget once prose is written. That would mean the structural stratum leaks wording
too, and section 2 is wrong.

**Cost change.** Lower than proposed, not higher: step 3 replaces most of the rating with a
deterministic screen.

## 4. R1-1, decision-first abstract routing

**As proposed.** Treat a shape-only graph as a state-routing machine, sample the decision set away
from the child's prior books, map onto the graph; measure choice-text overlap by embedding.

**Why it cannot run as written.** Two independent failures. The "decision set" is sampled at the
abstract layer, which constraint A rules out. And the proposed measure, embedding distance over
choice text, is now known to move for a reason that has nothing to do with decisions: `AL-208` shows
choice text converges hard when the plan's wording is shared, so the metric would report repulsion
working or failing on the basis of how the plan was worded.

**Re-specified.**

1. Sample the **bound solution chain**, not the abstract decision set. The repulsion target is: the
   devices this child's prior books used, the operations those puzzles asked, and the answers they
   resolved to. That is the object D-4 showed reproduces reader judgement.
2. The shape-only graph stays shape-only, which is now a *virtue* rather than an accident: it is the
   structural stratum, and section 2 licenses sharing it freely.
3. Measure with solution transfer against the child's prior books, not with choice-text embedding.
   Report choice-text overlap too, but as a **convergence guard**, which is what it actually
   measures.
4. The proposer's five books on one abstract skeleton is still the right experiment, unchanged in
   size.

**New falsifier, replacing the proposer's.** Repulsion on the bound chain succeeds (transfer near
zero across all five books) while blind readers still call the books decision-repetitive. That would
mean solution transfer is necessary but not sufficient, and would be the most informative negative
result available from any row in the register.

## 5. M-3, decision-axis scheduling

**As proposed.** Classify every fork by the kind of decision it asks, and schedule kinds per book, so
decision variety becomes a solvable scheduling problem.

**Why it cannot run as written.** It needs a classifier, and we have now measured what a classifier
of this kind does. The v1 signature vocabulary inverted against readers. The v2 vocabulary inverted
again and tied, with inter-annotator kappa comfortably clear of the floor, so the fields are
labellable and simply do not discriminate. The deterministic version classified 2 of 6 props on an
unseen contract, failing on negation and polysemy (`AL-211`). Three attempts, three failures, and
the third one localises the cause: **the axis is not recoverable from the artifact, by model or by
word list.**

**Re-specified, and this is the largest change of the three.** Stop trying to classify. **Declare.**

1. Add an explicit field to the narrative contract's decisional stratum: for each fork option, the
   **operation** it asks (what the reader does to resolve it) and the **stake** it carries. Authored
   at contract time, when the author already knows, rather than inferred afterwards when nobody does.
2. M-3 then becomes a scheduling problem over declared values, which is what it always claimed to
   be, and it becomes tractable the moment the field exists. Scheduling over declared axes needs no
   annotator, no kappa study, and no lexicon.
3. This subsumes the brief's open question about whether a plan-level representation of "the same
   operation" is deterministically readable. Our answer is that it is not, and the response is to
   write it down rather than to read it off.

**Dependency, stated plainly.** M-3 is now blocked on a **schema change**, not on a metric. That is a
smaller and much better-defined blocker, and the schema change is independently justified: it is the
same field R2-1b's tuples need and the same field R1-1 repels on. All three re-specifications
converge on it, which is mild evidence it is the right field.

**New falsifier.** Authors cannot agree on the declared operation for a fork at acceptable
reliability. This is testable for the cost of one annotation round over an existing contract, and it
should be run *before* the schema change, because it is the whole premise. Note that D-3c already
found the boundary between "derive a value by rule" and "compare against a pattern" contested at
kappa 0.719 between two annotators, so this falsifier has a live chance of firing and the operation
vocabulary needs settling first.

## 5b. R1-3 and R2-4, the two repulsion rows

These were filed separately from the three above, as "optimising the inverted objective" rather than
planning at the wrong layer. That is right, and it makes them the cheapest two to fix: **neither
needs re-scoping, both need their objective swapped.**

**R1-3, repulsive generation via obligation contracts.** Feed the child's prior action semantics
into contract generation as a repulsion penalty. Two changes:

1. Repel on the **bound solution chain** and score with solution transfer tier 1, not on action
   semantics, which are a device-agnostic artifact and which D-3 shows do not carry the property.
2. **Add the shared-gram guard across the generated set.** The proposal has no convergence check at
   all, and its own stated failure mode ("repulsion exhausts natural choices and produces bizarre
   action semantics") is not the one D-6 predicts it will hit first.

R1-3 has an advantage none of the others has, and it is worth naming because it was invisible before
D-6: **it generates a fresh contract per book by construction.** That is precisely the untested third
repair from `AL-208`, so R1-3 doubles as the experiment that would settle it. It should probably run
before R2-1b for that reason alone. Note it inherits section 2.1's caution: per-book generation still
leaves the premise and the idiom floor unless the premise is varied too.

**R2-4, portfolio generation with semantic repulsion.** Generate K decision programs per request,
select on quality-minus-novelty before any prose. The selection layer is sound; its novelty term is
measured against a signature vocabulary that inverts. Replace the novelty term with solution
transfer tier 1 plus, once prose exists for the selected candidates, the shared-gram rate. Both are
deterministic, so the selection stays cheap, which was the proposal's main attraction.

**One warning specific to R2-4 that D-6 sharpens.** Selecting K candidates from one generator and
keeping the most novel does not escape the idiom floor: every candidate is the same model writing
the same situation, and the floor is a property of that generator rather than of the candidates.
A portfolio can only select away variance it actually produces, and D-6 measured roughly a quarter
of the convergence to be generator idiom that no plan-level choice touches.

## 6. What changed, in one table

| | Was blocked on | Is actually blocked on | Cheapest unblocking step |
| --- | --- | --- | --- |
| R2-1b | D-3, a metric | nothing, once its programs carry bindings | re-scope to bound tuples, score with D-4 tier 1 |
| R1-1 | D-3, a metric | nothing, once it repels on the bound chain | swap the repulsion target and the measure |
| M-3 | D-3, a metric | a **schema field**, plus a reliability check on it | one annotation round on declared operations |

None of the three is blocked on repairing the signature vocabulary, which is the thing the register
said they were waiting for. Two are unblocked by re-scoping alone. The third is blocked on something
much smaller than it looked, and all three want the same new contract field.

## Related

- [Diversity test register](./diversity-test-register.md), rows R2-1b, R1-1, M-3, D-3, D-4, D-6
- [Research brief](./cyo-generation-research-brief-2026-08-10.md), Part II sections 14 to 16g
- [Authoring lessons log](./authoring-lessons-log.md), `AL-197`, `AL-208`, `AL-211`, `AL-212`
