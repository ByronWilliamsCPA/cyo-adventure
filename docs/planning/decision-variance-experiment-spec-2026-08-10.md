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
