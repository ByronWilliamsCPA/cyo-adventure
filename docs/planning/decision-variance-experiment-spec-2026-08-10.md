# Experiment spec: does varying the decisions break repetition? (2026-08-10)

> The test of the one lever ten prior designs never pulled. Run after two independent
> external reviews of `cyo-generation-research-brief-2026-08-10.md` converged, separately,
> on the same first step: manually author a different decision program over the same graph
> before building any compiler.

## 0. Provenance of every rating in this spec

> [!IMPORTANT]
> **Every rating, annotation and judgment of a finished book reported here was produced by LLM
> agent instances.** **No human and no child has read or rated any book in this run.** Following
> the research brief, those instances are called **model evaluators** throughout, and what they
> produce is a model-based hypothesis about reader response, not reader evidence. The Fleiss
> kappas below are **inter-model agreement**: they measure consistency among those instances and
> establish nothing about validity. Author and evaluators shared a model family, so the whole
> battery is exposed to the self-preference effect (research brief reference 37). The
> deterministic measurements are separate and are not affected: guard battery, shared four-grams,
> device collision, overlap counts.

## 1. The question

Every prior intervention held two things constant: **what each scene is**, and **what act
each choice asks the reader to perform**. Devices, prose, model tier, graph shape, and the
stated purpose of each scene were all varied, and none moved the result (spec
`obligation-variance-experiment-spec-2026-08-09.md` section 12, and section 5.3 of the
research brief).

**Does varying scene identity and action semantics, on an unchanged graph in an unchanged
world, reduce perceived decision repetition?**

## 2. Design

| | Control pair | Treatment pair |
| --- | --- | --- |
| Graph | identical | identical |
| World, cast, place names | **differs** (river lock-house vs bell foundry) | **identical** (both river lock-house) |
| Scene identity | identical | **differs** |
| Action at each choice | identical | **differs** |
| Node purpose / motivation | differs | differs |

Control pair: `filled_C` vs `filled_D`, the obligation-variance arms, already authored and
already rated at recognition position 2.

Treatment pair: `filled_C` vs `filled_H`, where `filled_H` is a new fill of the same graph
under a new contract (`contract_v4`) that changes every scene and every offered action,
**bound to the same river lock-house world as `filled_C`**.

**The treatment pair shares strictly more than the control pair.** Same world, same town,
same cast register, same building. That is deliberate: it is the actual series condition,
and it biases the experiment **against** the treatment. If the treatment pair still reads as
less decision-repetitive while sharing the world the control pair does not, the effect is
real and understated.

## 3. Held fixed

Graph, node ids, edges, ending kinds and valences, band (10-13), the fill protocol (isolated
agents authoring from files), the deterministic quality guards, and the model evaluator instance.

## 4. The instrument, which is new

The prior instrument asked for the position at which a reader would conclude "this is the
same book." That measures armature detectability, which is **not the defect**: a child
noticing they are in a familiar series is having the intended experience (research brief
section 1.4). It is dropped.

The model evaluator answers five narrow questions per pair, adapted from external review:

1. Were you asked to choose the same kinds of actions?
2. Did the options present the same tradeoff?
3. Would the choices predictably produce different consequences?
4. Did the sequence of decisions feel repeated?
5. Was each choice meaningful and sufficiently informed?

**One model evaluator instance rates both pairs**, in counterbalanced order, and then makes a direct
forced comparison: which pair asked the reader to do more similar things? Prior runs used
separate model evaluator instances, which is why no difference under one full position was safe to
interpret; the within-evaluator comparison is the fix.

Deterministically, `scripts/check_decision_overlap.py` scores both pairs on exact action
reuse, action-family rate, tradeoff rate, consequence rate, and ordered-sequence rate.

## 5. Pre-registered outcomes

| Outcome | Reading |
| --- | --- |
| Treatment pair rated **less** decision-repetitive than control on Q1/Q4, and chosen as less similar in the forced comparison | The lever is real. Proceed to a decision-program compiler. |
| Treatment ≈ control | Varying decisions does not help. The defect is elsewhere, and no proposed architecture is worth building. |
| Treatment **more** repetitive | Shared world dominates decisions. The series contract is doing more work than the decisions are, which would reframe the whole program. |

Deterministic guards, unchanged from prior runs and still quality gates rather than success
criteria: fill integrity, full validator gate not blocked, prose craft clean, zero
em-dashes, no title reuse.

## 6. The disagreement this run adjudicates

Two definitions of the defect are live, and the instrument now separates them numerically.

The owner's operational definition treats "open the door / go around back" against "go
upstairs / go downstairs" as **acceptably different**. External review argues both are the
same higher-order decision, choose a route through a location, and that a child may read
them as the same choice repainted.

Run through `check_decision_overlap.py`, that exact example scores **exact action reuse 0**,
passing the owner's bar, and **action-family rate 1.000**, failing the stricter reading. The
graded ceilings in the checker (0.6) are guesses. This run's model evaluator judgments are what
calibrate them, by showing which score tracks the model evaluator's verdict. No human verdict is
available to this programme, which is a weaker calibration than the word "calibrate" suggests.

## 7. Known limitations, stated in advance

- n=1 graph, one pair per condition, one pass. The 26-node pilot graph is an outlier against
  a catalog median of 151 nodes and is not production-eligible.
- The control pair's existing rating came from the old instrument; only the new within-evaluator
  comparison is used for the primary outcome.
- Author and model evaluator share a model family, engaging the self-preference effect documented in
  the research brief's reference 37.
- Rating compares books back to back, the condition least favorable to formula tolerance.
- A positive result licenses building a compiler; it does not establish the magnitude, which
  needs replication on a production-eligible graph in a real cell.

---

## 8. Results (2026-08-10)

**The experiment terminated before the fill, because the intervention could not be
constructed.** That is the result, and it is more informative than the rating would have
been.

### 8.1 The treatment was not delivered

Two authoring attempts were made over the fixed 26-node graph in a fixed world. The first
changed every scene identity and every action string. The second was sent back with explicit
instruction to move `tradeoff` and `consequence` rather than the verb, and iterated against
the instrument until it passed.

An independent model evaluator then labelled both contracts blind: stripped of all prior
annotations, renamed A and B, with no knowledge that they were being compared, which was the
control, or that divergence was the goal. It applied one written principle whose decisive
rule was that two choices asking the reader to do the same thing get the same labels however
the story dresses them.

Its verdict: **one fork of eighteen asks a genuinely different decision** (`n_open`, where
the premise itself changed from prove-yourself to rescue-before-the-tide). Every other fork,
including all four principal ones, mapped to identical labels.

| Measure | Author's own labels | Independent labels |
| --- | --- | --- |
| Same-decision reuse (family, target, tradeoff) | 1 / 28 | **28 / 28** |
| Action-family rate | 0.286 | **1.000** |
| Tradeoff rate | 0.179 | **1.000** |
| Consequence rate | 0.464 | **1.000** |
| Ordered-sequence rate | 0.000 | **1.000** |

### 8.2 Three instrument defects, all found by running it

1. **Single-option nodes are not decisions.** Six of eighteen nodes offered one option. They
   scored 0.00 overlap because there was nothing to repeat, and dragged the aggregate under
   its ceiling while every real fork was far worse. Excluded, and a `worst_fork_family_rate`
   gate added so a mean can never again pass on the strength of nodes that ask nothing.
2. **A declared-label metric is gameable by whoever declares the labels.** The same two
   artifacts score 0.179 and 1.000 on tradeoff reuse depending only on who annotated them.
   The author was not cheating; it was asked to minimise a score computed from labels it
   also wrote. Annotation must be independent of authoring.
3. **A free-text action field makes the hard bar vacuous.** Zero of 35 action strings matched
   while 34 of 35 shared a family: `set_the_dial_deliberately` against
   `set_the_levers_deliberately` is one act and two strings. The hard bar now compares the
   normalized act (family, target role, tradeoff); the raw string is reporting only.

### 8.3 What this says about the lever

The leading explanation is that **the graph plus fact-graph closure pins the decisions.**
Each fork's children must deliver what their own descendants require, and merge closure
propagates those requirements backward, so the *kind* of thing each branch accomplishes is
fixed even when every prop, name and sentence changes. An author may repaint a fork freely
and cannot repurpose it.

The competing explanation is authorial limitation. It is not fully excluded by one run, but
it is strained: two attempts, the second explicitly targeting the lever with metric feedback,
still produced 28 of 28 options that a blind model evaluator called the same decision. The one
fork that did move, `n_open`, is the one with no incoming constraint.

This reframes the topology conclusion withdrawn in the research brief rather than restoring
it. Topology is not itself the fingerprint. Topology **pins the decisions**, and the
decisions are the fingerprint. The causal chain is graph, then pinned decisions, then
recognition.

### 8.4 Consequences for the proposed architectures

All three externally proposed designs assume scene and decision content can be freed while
the graph stays verifiable. This run is evidence that the two are coupled through the fact
graph, not merely through our representation of it:

- A **shape-only skeleton** is only decision-free if its declared entry and exit facts are
  also free, and if those are free the merge cannot be verified before prose. That is the
  verifiability/freedom tension, now with evidence that it is real rather than an artifact.
- A **decision-program compiler** must therefore generate the fact graph and the decisions
  together, not assign decisions onto a fixed fact skeleton.
- Any **DecisionSignature** scoring must be computed by a party that did not author the
  program. Section 8.2 defect 2 applies directly to a compiler that emits its own signatures
  and is scored on them.

### 8.5 What was not learned

No fill was generated and no reader-facing rating was taken, so this run says nothing about
whether varying decisions *would* move recognition. It says only that varying them on a
fixed graph is much harder than assumed, and that our first attempt to do so failed while
appearing to succeed. Testing the lever still requires an architecture that can actually
produce different decisions, which is now the gating problem rather than a downstream one.

---

## 9. Results, second attempt (2026-08-10)

Section 8 recorded a run that terminated before any fill. This section records the run that
completed: a third contract (`contract_v5`) over the same graph, filled, guarded, and rated.

**Headline.** With a clean fill, two blind model evaluators in counterbalanced order both judged the
treatment pair **less** decision-repetitive than the control pair, which is the pre-registered
outcome 1 in direction. Both also called the effect thin. And the deterministic signature
instrument ranked the same two pairs in the **opposite** order, on every axis, under three
independent model evaluators. That contradiction, not the rating, is this run's main result.

### 9.1 Two prep defects invalidated the first two attempts

Both were mine, both were invisible to every guard then in place, and both are now checkable.

**Shell contamination (`AL-195`).** The fill shell carried the skeleton's own choice labels with
slot tokens bound. Because 13 of 35 skeleton labels carry no slot token (`AL-184`), the treatment
author was handed clocktower-dial vocabulary for a salvage story. It rewrote all 35 labels and
still stayed inside the frame, producing "Force the hands into place instead" against the shell's
"Force the hands by guesswork". Every deterministic guard passed while sibling grams hit 28.8 per
1000, the highest ever measured, with 4 shared menu frames. Rebuilding the shell with every label
as a `<<FILL label contract='node.choice'>>` directive took the same pair to 8.9 and 0.

**Device collision (`AL-196`).** The treatment binding shared 14 of 24 props with the control,
including the cipher itself. Two blind model evaluators, opposite orders, both named exactly those props as
decisive, and one added that stripping two of the affected forks would have left the pairs
indistinguishable. That rating measured the binding, not the contract, and was discarded. Only 6
of the 14 sat at the same node; the other 8 were the same props relocated, which a same-slot diff
scores as fresh and which a model evaluator described unprompted as "variety fork by fork but pure
rearrangement at the book level". `scripts/check_device_collision.py` now compares every prop
against every prop and scores that binding 0.583.

### 9.2 The clean treatment was delivered

`armV5b_selection.json` rebinds every device with no collision, keeping the shared world. The
resulting fill, `filled_V5c.json`, passes the whole battery (`eval_v5c.sh`):

| Guard | Treatment pair (C vs V5c) | Control pair (C vs D) |
| --- | --- | --- |
| Device collision rate | 0.000 | 0.000 |
| Shared 4-grams per 1000 | **1.8** | 2.7 (post-revision) |
| Shared menu frames (margin 0) | 0 | 0 |
| Validator gate | not blocked, 1 advisory | not blocked |
| Prose craft, em-dashes, titles | clean | clean |

The treatment pair is now *less* lexically convergent than the control pair while sharing the
world the control pair does not.

### 9.3 The model evaluators: treatment less decision-repetitive, thinly

Two model evaluator instances, each rating both pairs within-evaluator, in opposite pair orders, blind to the
design. Scores are (evaluator A, evaluator B).

| # | Question | Control α+β | Treatment α+γ |
| --- | --- | --- | --- |
| 1 | Same kinds of actions | 5, 5 | 4, 5 |
| 2 | Same tradeoffs | 5, 5 | **4, 4** |
| 3 | Different consequences *(high good)* | 2, 2 | **3, 3** |
| 4 | Repeated sequence | 5, 5 | 5, 5 |
| 5 | Meaningful and informed *(high good)* | 3, 4 | 4, 4 |
| 6 | Solution transfer *(high bad)* | 4, 4 | **3, 3** |
| | **Forced comparison** | **more similar** (high conf. / medium conf.) | less similar |

Both model evaluators converged unprompted on the same three decisive forks, `n_clockface`, `n_vault` and
`n_setjam`, and on the same mechanism: the control changes every noun and almost no decision,
while the treatment keeps the nouns and changes the act. The control and its base both decode a
notation and set a brass dial at the top of the tower; the treatment checks an object's
orientation against a full-size drawing and seats it at a bench.

**The result survives a stacked deck.** The treatment shares the control base's entire world while
the control changes world wholesale. One model evaluator flagged this directly: the treatment "will *feel*
more repetitive to a child than it scores here, and if you disagree with excluding [world], the
answer flips." Excluding shared world is the owner's operational definition (section 6), so under
that definition the treatment wins while carrying the heavier load.

**Both model evaluators called the effect thin,** and it is recorded as thin: "three re-skins of one graph",
separation resting on three forks out of eleven, one model evaluator at medium confidence.

### 9.4 Q6 was invented by the model evaluators, and it is the item that worked

The five-question instrument of section 4 was amended before this run. Both model evaluators of the
discarded round, independently and without conferring, reported that Q1 and Q4 saturate at 5 for
both pairs because all three books share one skeleton, and both proposed the same missing item:
*did solving the first book hand you the answer to the second* (`AL-198`). It was added as Q6.

On first use, Q1 and Q4 saturated exactly as predicted (Q4 is 5,5 against 5,5, contributing
nothing), and Q6 separated the pairs cleanly and consistently, 4,4 against 3,3. Q2, Q3 and Q6
carried the entire judgement. Two model evaluators converging on an unprompted diagnosis, which then
replicates on the next run, is the strongest instrument evidence this programme has produced.

### 9.5 The signature instrument inverts the model evaluator ordering

This is the finding that matters. Blind model evaluators labelled the contracts from
`choice_semantics` alone, stripped of prior annotations, neutrally named, with no knowledge of
what was being compared or that divergence was the goal.

| Measure | Control pair (v2 vs v3) | Treatment pair (v2 vs v5) |
| --- | --- | --- |
| Same-decision reuse, one model evaluator over all three plans | 24 / 28 | **28 / 28** |
| Action-family rate | 0.929 | **1.000** |
| Tradeoff rate | 0.893 | **1.000** |
| Consequence rate | 0.857 | **0.964** |
| Ordered-sequence rate | 0.909 | **1.000** |
| Two blind model evaluators of the filled books | **more repetitive** | less repetitive |

Replicated across model evaluators: two further independent model evaluators scored the control pair
at 24/28 and 23/28 (family 0.893 both), against the earlier pair of model evaluators' 28/28 and
1.000 for the treatment. Every annotation ranks the treatment as the more repetitive pair; every
model evaluator of the filled books ranks it as the less repetitive one.

Unreliability does not explain it, and here is the whole agreement set rather than its best rows.
Fleiss' kappa between the two independent model evaluators, both measurements per field:

| Field | Fleiss' kappa | Lower measurement, above the 0.60 floor by |
| --- | --- | --- |
| `consequence` | 1.000 | 0.400 |
| `action_family` | 0.961, 0.962 | 0.361 |
| `target_role` | 0.924, 0.803 | 0.203 |
| **`tradeoff`** | **0.675, 0.672** | **0.072** |

All four clear the floor, and the set is not uniform: quoting only `action_family` and `consequence`
reports the two strongest of the four fields and makes agreement look better than it is.
**`tradeoff` is the weakest axis and sits roughly 0.07 above the floor**, in Landis and Koch's
substantial band but nowhere near the almost-perfect one, and it is one of the three fields
same-decision reuse is computed from (family, target role, tradeoff). So the inversion rests on a
measurement that is near-perfectly reproducible on two of its axes and only marginally so on a
third. Read the reuse figures with that in mind; nothing here licenses the shorter claim that
agreement is uniformly almost perfect.

### 9.6 Why it inverts, exactly

Two errors in opposite directions, both visible in one diff.

**Blind where it matters.** At the three forks both model evaluators called decisive, the signatures are
*identical across all three plans*, choice for choice:

| Fork | v2 | v3 | v5 |
| --- | --- | --- | --- |
| `n_clockface.c_face_correct` | CRAFT / EFFORT_VS_SHORTCUT | CRAFT / EFFORT_VS_SHORTCUT | CRAFT / EFFORT_VS_SHORTCUT |
| `n_vault.c_vault_share` | MORAL / NONE | MORAL / NONE | MORAL / NONE |
| `n_setjam.c_jam_oil` | CRAFT / NONE | CRAFT / NONE | CRAFT / NONE |

"Compute a value and dial it" and "match a shape and seat the part" are one signature and two
kinds of thinking. The vocabulary has no dimension for **what kind of reasoning the choice
demands**, which is precisely the axis the model evaluators responded to and precisely what Q6 measures.

**Leaking scenery where it should not.** The control pair's entire measured advantage comes from
four entry forks, `n_start.c_door`, `n_start.c_keeper`, `n_door.c_door_force` and
`n_door.c_door_window`, where the control's world change turns "get past the building" into "read
what the building remembers": PHYSICAL_RISK/BARRIER/ACCESS becomes INFORMATION/LOCATION/KNOWLEDGE.
The act is the same, the framing changed with the scenery, and the labels followed. Rule 2 of the
labelling principle forbids exactly this, and the model evaluators were not at fault: they labelled the
`choice_semantics` text faithfully, and the scenery had already entered the plan.

So the instrument is deaf at the climax and over-sensitive at the door. Both errors push the same
way here, which is why the inversion is clean rather than noisy.

### 9.7 Consequences for the proposed architectures

- **A decision-program compiler that emits DecisionSignatures and is scored on them would optimise
  the wrong direction** on this evidence. It would read the control pair as the more diverse of
  the two and reproduce the pattern the model evaluators liked least. `AL-188` established that the scorer must
  be independent of the author; this run establishes something worse, that the v1 scoring
  construct is not merely coarse but anti-correlated with the judgement it exists to predict.
- **A v2 vocabulary needs a reasoning-kind dimension** (compute, match, recall, infer, negotiate,
  exert) before any signature metric routes anything. The three gaps both earlier model evaluators
  raised (`AL-193`) remain, and this run adds the decisive fourth.
- **Solution transfer is the construct to build the metric around**, not action families. It is
  what the model evaluators used, it is what discriminated, and it is plausibly computable from the plan:
  two puzzles that resolve by the same operation to the same answer are the defect.
- **The branch-obligation screen is one-way** (`AL-197`). `contract_v5` scores same-shape rate
  0.000 with zero renames and is still 28/28 identical by signature and still recognisably the
  same book at three of eleven forks. A pass buys nothing.

### 9.8 What was not learned, and what is now suspect

- n=1 graph, one pair per condition, one fill each, two model evaluators. The 26-node pilot graph is an
  outlier against a catalog median of 151 nodes and is not production-eligible.
- The treatment bundles two changes: different decision content *and* four rooms that each yield a
  distinct physical component. One model evaluator credited the latter explicitly. They are not separated
  here, so the effect cannot be attributed to decision content alone.
- Author and model evaluators share a model family, engaging the self-preference effect (research brief
  reference 37).
- **Both model evaluators independently reported a defect the pair framing cannot see** (`AL-199`): the
  four-room `n_inside` fork has no consequence in *any* of the three books, and roughly seven of
  nine forks either do not branch or reconverge one node later. Because the defect is identical
  everywhere it cancels out of every pairwise comparison. Illusory choice may be the larger threat
  to the reading experience than cross-book repetition, and the entire diversity programme is
  currently blind to it.

### 9.9 Owner ruling: reconverging exploration is not a defect (2026-08-10)

Section 9.8 reported, from both model evaluators, that most forks on this graph reconverge with no differing
consequence, and proposed a per-book illusory-choice check. **That proposal is rejected.**

The owner's ruling: choice paths that do not progress the story and loop back so the reader can
explore another option are a convention of the form, not a flaw. The comparison offered is
tabletop play, where a party sweeps every room in an area precisely because some rooms hold
nothing and you cannot know which until you look. The checking is the play. A reader who takes
the catwalk, finds a hint, and returns to take the stair has not been cheated; they have explored.

This is the same class of correction as the one that redefined the central defect earlier in this
programme. The model evaluators were reporting a structural fact accurately and then attaching a product
judgment to it that is not the owner's. Recording it here so the fact stays and the judgment goes.

Two things survive the ruling, both narrow:

- Single-option nodes remain excluded from decision metrics (`AL-189`). A node offering one option
  is a page turn, and counting it as a decision pads any rate with units that cannot repeat. That
  is an arithmetic point about denominators, not a claim that such nodes are bad.
- The *proportion* is unmeasured, not ruled on. Nobody has established what share of forks should
  reconverge for this form and this age band, and no gate should be built until someone does.

No illusory-choice gate will be built. `AL-199` is closed as rejected.
