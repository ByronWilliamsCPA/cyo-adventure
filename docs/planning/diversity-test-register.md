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
optimise them. **Any such row run before D-3 lands is measuring with an instrument known to point
the wrong way**, and a positive result from it would be uninterpretable. That is why the D rows
sort above the architecture rows, and it is a change from the reviewers' recommended orders, which
were written before this was known.

---

## A. Instrument and replication work (do first)

| ID | Test | Question it settles | Method | Cost | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| D-1 | Separate the treatment's two bundled changes | Was the 2026-08-10 effect from varied decisions, or from the four rooms yielding distinct components? One rater credited the latter explicitly, and they are confounded. | Third arm on the same graph: varied decisions, rooms restored to yielding the same thing. Rate against the same base book with the six-question instrument. | ~1 fill, 2 raters | The varied-decision-only arm rates the same as the control, meaning the whole effect was the components. | queued |
| D-2 | Replicate on a production-eligible graph | Does any of this survive off a 26-node outlier? The catalog median is 151 nodes and the pilot graph is not production-eligible. | Repeat the winning arm on a median-size 10-13 skeleton, same protocol, same instrument. | 2 fills, 2 raters | The effect vanishes or inverts at production scale. | queued |
| D-3 | DecisionSignature v2 with a reasoning-kind dimension | Can a signature vocabulary be built that agrees with readers instead of inverting them? Gates six architecture rows. | Add reasoning-kind (compute, match, recall, infer, negotiate, exert) plus the three gaps from `AL-193`. Re-annotate the three existing plans blind, re-measure kappa, and check the ordering against the ratings already taken. | 3 annotators over 3 plans | v2 still ranks the treatment pair as the more repetitive one, or kappa falls below 0.60. | queued |
| D-4 | Solution-transfer metric | Is the item that actually discriminated computable from a plan, rather than only ratable by a reader? | Formalise "these two puzzles resolve by the same operation to the same answer" against the three existing contracts, and check it reproduces the raters' Q6 ordering (4,4 against 3,3). | deterministic, no model | It cannot reproduce the known ordering on the pair we have already rated. | queued |
| D-5 | Rate the discarded contaminated arm as a negative control | Does the six-question instrument correctly detect a pair we know is contaminated? | The 14-of-24 shared-prop binding is preserved. Feed `filled_V5b` to fresh blind raters and confirm it scores worse than `filled_V5c` on Q6. | 2 raters | The instrument cannot separate a known-contaminated pair from a clean one, which would invalidate every rating taken with it. | queued |

## B. Architectures that do not depend on the broken instrument

| ID | Test | Source | Thesis | Cheapest experiment (proposer's) | Falsifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| M-1 | Goal transform | in-house | Vary what the *reader is trying to do* as one global variable that re-reads every fork. We varied why each scene exists and failed; we never varied the reader's objective. | Two books, same graph, same binding, different goal. Existing rig, one afternoon. | The two books rate as repetitive as the control pair, meaning the objects at each fork dominate the reader's goal. | queued |
| M-2 | World-graph tours | in-house | A graph is a *world*, not a book; a book is a validated subgraph tour. The catalog already holds graphs at 677, 551 and 250 nodes. | Take the largest 10-13 graph, cut two disjoint tours by hand, fill both, rate. Tests coherence as much as diversity. | Tours read as incoherent, because the large graphs were authored assuming roughly linear progression rather than as worlds. | queued |
| Q-2 | Cross-skeleton recombination | framework Q2 | Subtree grafting is the only mechanism that has ever cleared the anti-clone floor, and has never been evaluated for reader-perceived distinctness or coherence cost. | Graft subtrees between two catalog graphs, fill, rate for distinctness and for coherence damage. | Grafts read as incoherent, or as no more distinct than a plain sibling pair. | queued |
| Q-3 | How close is the skeleton-free path | framework Q3, brief 5.3 | Named the cheapest outstanding experiment before this programme started, and never run. | Per brief section 5.3. | The skeleton-free path produces structurally invalid graphs at a rate that no gate can absorb. | queued |
| Q-5 | Does the fill match its contract | framework Q5 | Nothing verifies finished prose against the node obligations it was written to satisfy. This is S4's unaddressed second weakness and it is independent of everything else here. | Check each filled node against its contract's `establishes` and `forbids`. | Fills already satisfy their contracts, making the check redundant. | queued |

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
| Q-1 | Does catalog depth solve it | framework Q1 | A child exhausts a cell by roughly their fourth request at 3 to 4 skeletons per cell, and demand concentrates on medium length while the catalog is flat across lengths. | Not a research question. A capital question about depth against the demand curve. | Not falsifiable as stated; it is a purchasing decision, and is listed only so it is not mistaken for outstanding research. | queued |

## E. Retired

| ID | Test | Why retired |
| --- | --- | --- |
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
