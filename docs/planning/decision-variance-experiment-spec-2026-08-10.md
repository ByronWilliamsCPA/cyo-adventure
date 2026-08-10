# Experiment spec: does varying the decisions break repetition? (2026-08-10)

> The test of the one lever ten prior designs never pulled. Run after two independent
> external reviews of `cyo-generation-research-brief-2026-08-10.md` converged, separately,
> on the same first step: manually author a different decision program over the same graph
> before building any compiler.

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
agents authoring from files), the deterministic quality guards, and the rater instance.

## 4. The instrument, which is new

The prior instrument asked for the position at which a reader would conclude "this is the
same book." That measures armature detectability, which is **not the defect**: a child
noticing they are in a familiar series is having the intended experience (research brief
section 1.4). It is dropped.

The rater answers five narrow questions per pair, adapted from external review:

1. Were you asked to choose the same kinds of actions?
2. Did the options present the same tradeoff?
3. Would the choices predictably produce different consequences?
4. Did the sequence of decisions feel repeated?
5. Was each choice meaningful and sufficiently informed?

**One rater instance rates both pairs**, in counterbalanced order, and then makes a direct
forced comparison: which pair asked the reader to do more similar things? Prior runs used
separate rater instances, which is why no difference under one full position was safe to
interpret; the within-rater comparison is the fix.

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
graded ceilings in the checker (0.6) are guesses. This run's rater judgments are what
calibrate them, by showing which score tracks the human verdict.

## 7. Known limitations, stated in advance

- n=1 graph, one pair per condition, one pass. The 26-node pilot graph is an outlier against
  a catalog median of 151 nodes and is not production-eligible.
- The control pair's existing rating came from the old instrument; only the new within-rater
  comparison is used for the primary outcome.
- Author and rater share a model family, engaging the self-preference effect documented in
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

An independent annotator then labelled both contracts blind: stripped of all prior
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
still produced 28 of 28 options that a blind annotator called the same decision. The one
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
