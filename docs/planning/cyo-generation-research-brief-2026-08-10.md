# Generating choose-your-own-adventure books with LLMs: problem statement, capability analysis, and an open puzzle

> **Status: research brief prepared for external analysis.** It is written to be handed to a
> language model with no access to our codebase, so it is self-contained. Its purpose is to
> get independent theorizing on a problem we have attacked from ten directions and not
> solved.
>
> **Citation caveat.** References were assembled from model knowledge and verified by web
> search where possible. Verification status is marked per entry in section 9. Treat any
> entry marked *unverified* as a pointer to check, not as an established fact.

---

## 0. What we are asking you to do

Read sections 1 through 6, then answer section 7.

We are not asking whether LLMs can write stories. They can. We are asking a narrower and
harder question: **what architecture produces a large branching narrative that a single
child can be given repeatedly, over months, without the child perceiving that they are
reading the same book with new paint?**

We have a working system that satisfies every requirement except that one. We have measured
ten interventions against it. Nine did nothing. The tenth pointed at an answer we find
expensive and would like to be wrong about.

Two things we would specifically value:

1. **Attack our framing.** Section 1.3 argues our whole diversity program may rest on a
   category error about what child readers want. We believe this argument is strong and we
   have not acted on it. Tell us if it is wrong, or if it is right and we have understated
   it.
2. **Attack our conclusion.** Section 5 concludes that reader-perceived sameness tracks
   graph topology, and therefore that variety must come from more graphs. That conclusion
   is expensive. If there is a cheaper mechanism we have not tested, we want it.

---

## 1. The product goal, from first principles

### 1.1 The artifact

A guardian requests a story for a specific child. The system generates a **choose-your-own
adventure book**: a directed graph whose nodes carry prose and whose edges are labeled
choices. The child reads on a tablet, offline, choosing at each fork. Every path must
terminate at an ending. An adult approves each book before the child sees it.

The system is real and deployed. Generation is a staged pipeline behind a deterministic
validation gate and a human approval step.

### 1.2 What we know readers of this form actually want

Four literatures bear on this, and they do not all point the same way.

**Choice as autonomy.** The strongest general result is that choice raises intrinsic
motivation and engagement. Patall, Cooper and Robinson's meta-analysis [37] found a reliable
positive effect of choice on intrinsic motivation, effort, and task performance, with the
effect moderated by the number and type of options: two to four options outperform more.
This sits inside self-determination theory [38], where autonomy is one of three basic needs
alongside competence and relatedness. For a reading product aimed at children, this is the
core mechanism: choosing is what converts reading from assignment to play.

Note the moderation result, because it is directly actionable. Our own band rules cap
options per choice at two to four depending on age band, which the meta-analysis supports,
and which also happens to be what the authoring literature recommends.

**Agency is not the same as branching.** Murray's account of agency [5] is the origin of the
common design error: readers report agency when their choices feel consequential, not when
the graph is objectively wide. Wardrip-Fruin and colleagues sharpened this: perceived agency
comes from the fit between what the system invites the player to attempt and what it can
actually respond to, not from raw option count. Mawhorter's choice poetics [2] gives the
mechanism at the level of a single choice: a choice reads as meaningful when its options are
*distinguishable in kind*, when the reader can form an expectation about outcomes, and when
the outcome bears a legible relation to that expectation.

This matters for us because it locates reader experience in the **local texture of a
choice**, not in global graph size, which is the opposite of where our engineering effort
has gone.

**Structure has a small vocabulary.** Ashwell's survey of choice-based games [1] identified a
handful of recurring macro-shapes: time cave, gauntlet, branch and bottleneck, quest, open
map, sorting hat, loop and grow. His observation is that the widely-branching shapes are
rare in practice because authoring cost explodes, and that **branch and bottleneck**
dominates published work: the story fans out, then reconverges at checkpoints, which bounds
the authoring burden while preserving local choice.

Our catalog independently converged on exactly this distribution. Of 61 skeletons: 22
branch-and-bottleneck, 11 open map, 9 sorting hat, 7 time cave, 6 gauntlet, 6 loop and grow.
We did not set out to reproduce Ashwell's taxonomy; the economics reproduced it for us. That
is weak evidence that we are in the right design space, and strong evidence that the space
is small, which becomes important in section 5.

**Formula is not a defect in this genre.** This is the literature we think we have been
ignoring. Cawelti's theory of formula fiction [39] and Radway's ethnography of romance
readers [40] both find that readers of formulaic genres are not tolerating repetition, they
are seeking it: the formula is the contract, and satisfaction comes from skilled variation
*within* a known shape. Nell's work on reading for pleasure [41] describes the absorbed
"ludic" reading state as depending partly on fluency and predictability. Children's series
publishing is the commercial expression of this: Magic Tree House, Goosebumps, Nancy Drew,
and Rainbow Magic sell precisely because book N+1 is structurally book N.

Berlyne's inverted-U [42] gives the general form: hedonic value peaks at intermediate
novelty, and both total predictability and total novelty are aversive. Zajonc's mere
exposure effect [43] pushes the optimum further toward familiarity than designers expect.

### 1.3 The reframe we think may invalidate our own program

Our diversity work has assumed, without ever testing, that **a child detecting the shared
armature is a failure**.

The formula literature suggests that is not obviously true. A ten-year-old who liked book one
may want book two to be structurally book one. The thing they do not want is to feel
*cheated*, and those are different failures with different triggers.

The distinction we have never operationalized:

| | Reader notices shared structure | Reader does not notice |
| --- | --- | --- |
| **Reader is satisfied** | Series pleasure: the Magic Tree House case | Ideal, and expensive |
| **Reader is dissatisfied** | The failure we assume we are measuring | Failure for other reasons |

Our measurement protocol asks a rater to find the position at which a reader would conclude
"this is the same book in different clothes." **That measures detectability, not
dissatisfaction.** We have been optimizing against detectability and calling it quality.

Three testable consequences, which we have not tested:

1. If series pleasure dominates, the correct move is the opposite of ours: make the
   armature *legible and consistent*, brand it as a series, and spend the diversity budget
   on scene-level texture rather than graph variety.
2. If it does not, we need to know what the actual dissatisfaction trigger is. Candidates:
   the reader's *choices* stop mattering because the same fork recurs (a Mawhorter-style
   local failure, not a global one), or the reader can predict outcomes and stops reading.
3. The moderator is probably the gap between reads. Formula tolerance in series fiction is
   measured over books read weeks apart; our rater compares two books back to back, which
   is the maximally unfavorable condition.

We flag this as our own most likely error, and we have not corrected for it.

### 1.4 Operational success criteria

Everything below is enforced by deterministic code, independent of how a story was made:
graph reachability and termination, no trap loops, per-band word envelopes, reading level,
ending economy and valence mix, condition/effect coherence across branches, safety
classification, and mandatory human approval.

The unsolved criterion is the sixth: **the book should be distinct from the other books this
same child has read.** It is the only criterion that cannot be evaluated on a single
artifact. It is a property of a pair, relative to one reader's memory. The unit is the
child, not the household: two siblings can read the same book with no issue.

---

## 2. Scale, which is what rules out the obvious approach

Our catalog holds 61 story graphs totaling 11,458 nodes.

| Band (reader age) | Graphs | Nodes min / median / max | Words per node | Median book |
| --- | --- | --- | --- | --- |
| 3-5 | 7 | 11 / 20 / 32 | 40 | ~800 words |
| 5-8 | 6 | 35 / 57 / 62 | 70 | ~4,000 words |
| 8-11 | 9 | 65 / 121 / 191 | 100 | ~12,100 words |
| 10-13 | 11 | 26 / 149 / 250 | 100 | ~14,900 words |
| 13-16 | 14 | 124 / 277 / 551 | 140 | ~38,800 words |
| 16+ | 14 | 33 / 248 / 677 | 175 | ~43,400 words |

The largest graph is 677 nodes, roughly 118,000 words of branching prose in which every path
must terminate, hold reading level, and never contradict itself where paths reconverge.

This is a novel with a graph, not a long short story, and it is why single-pass generation
was never a candidate.

---

## 3. Capability analysis: why one pass cannot do this

This section is the part we most want challenged, because our architecture is a direct
consequence of it.

### 3.1 The task is a composite of two tasks with different profiles

Generating this artifact requires simultaneously solving a **combinatorial structure
problem** (a graph with global reachability, termination, and reconvergence-consistency
properties) and a **creative generation problem** (prose at a controlled reading level with
consistent voice). Our original finding, which motivated the whole architecture, was that a
single prompt asking for both produced acceptable neither.

The literature offers a mechanism rather than just a description. Tam et al. [34] found that
imposing format restrictions on generation measurably degrades reasoning performance, with
the degradation increasing as the format constraint tightens. Park et al. [35] showed that
grammar-constrained decoding, which guarantees syntactic validity, distorts the model's
learned distribution rather than sampling from it conditioned on validity. Both results
point the same way: **structural constraint is not free, it is paid for out of the same
budget that produces content quality.**

If that is the right mechanism, the architectural implication is to *separate the two jobs
into different calls*, which is what plan-then-write systems do, and what we do.

### 3.2 Hierarchical planning is the established remedy, and it has a known ceiling

The plan-then-write tradition is well developed for linear fiction. Fan et al. [10]
established hierarchical generation, generating a premise then conditioning the story on it.
Rashkin et al. [11] added explicit plot-state tracking against an outline. Yang et al. [7,8]
scaled this to novel-length output through recursive reprompting, and then showed that
*detailed* outline control improves long-range coherence over coarse plans. Mirowski et al.
[9] took the strongest version for our purposes: Dramatron generates a log line, then
characters, then a beat sheet, then dialogue, and evaluation with professional writers
found the hierarchy produced usable long-form structure.

Our skeleton architecture is this pattern with the plan **precomputed and human-reviewed**
rather than generated per request.

The known ceiling is also visible in this literature. Mirowski et al. report that
professionals valued the tool while noting the output's structural sameness across runs, and
this is the exact failure we hit. **A fixed plan is a fixed story.** The plan-then-write
literature optimizes for coherence, and coherence is a within-book property; our problem is
a between-book property, which that literature was not built to address.

### 3.3 Compositional degradation predicts where a single pass breaks

Dziri et al. [15] showed transformers solve compositional tasks by matching linearized
subgraph patterns rather than by executing the composition, with accuracy collapsing as
compositional depth grows, and errors accumulating rather than self-cancelling. Related
work on hallucination snowballing [18] shows models commit to an early error and then
generate consistently with it rather than correcting.

For a 277-node graph this predicts the observed failure precisely: node-local decisions are
fine, and the global properties that depend on composing 277 of them are not.

The planning literature says the same thing from another direction. Valmeekam et al. [13]
found LLM plan-generation accuracy on classical planning benchmarks far below what
autoregressive fluency suggests, and Kambhampati [14] argues LLMs are better understood as
approximate retrievers of plan-shaped text than as planners, which is why they do well when
a plan template is supplied and poorly when one must be constructed.

**Prediction we rely on:** supply the graph, and the model performs. Ask for the graph, and
it degrades. This is exactly what we observe, and it is the strongest theoretical support
for the skeleton.

### 3.4 Long context does not rescue it

A tempting counterargument is that modern context windows can simply hold the whole book.
The evidence says holding is not the same as using. Liu et al. [20] found retrieval accuracy
degrades for information in the middle of long contexts. Hsieh et al. [23] found effective
context length far below advertised length once the task requires more than retrieval.
Karpinska et al. [21] found that verifying claims over book-length narrative, which requires
global comprehension rather than lookup, remains hard even for frontier models. Chang et al.
[22] found book-length summarization suffers coherence failures that scale with length.

The relevant capability for us is not retrieval but **constraint maintenance across a long
generation**, and it is the capability these results are least optimistic about.

### 3.5 Self-verification limits force an external gate

Our architecture puts a deterministic validator between generation and human review. The
literature supports this strongly. Huang et al. [16] found that LLMs asked to self-correct
reasoning without external feedback often degrade their answers. Stechly et al. [17] found
self-verification unreliable on reasoning and planning, with models failing to detect their
own invalid plans. Gou et al. [19] found the decisive variable is *external* feedback:
tool-interactive critiquing improves output where pure self-critique does not.

**This is the single most load-bearing result for our design.** It says: never ask the model
whether its graph is valid, compute it. Our validator is a program, not a prompt, and this
literature is why.

We have direct evidence for it. Our own agents, given a checker to run in a loop, produced a
31-fact narrative contract that passed every coherence check on the first attempt and closed
a large convergence gap in one revision round without human repair. The same agents without
the checker do not. The capability is real; it is unlocked by external verification, exactly
as [19] predicts.

### 3.6 Output diversity is the actual bottleneck, and it is a property of the model

Everything above concerns whether the model can produce **one** good book. Our problem is
producing **many different** ones, and here the literature is both clearer and more
pessimistic.

Alignment training reduces output diversity. Kirk et al. [24] found RLHF improves
out-of-distribution generalization while measurably reducing output diversity relative to
the base model, and specifically that RLHF'd models produce lower variance across samples
for a fixed prompt. This is a direct statement that the models best at following our
constraints are the ones worst at varying.

The effect propagates to human work products. Padmakumar and He [25] found that writing
assisted by an LLM produced less diverse content across writers than unassisted writing.
Doshi and Hauser [26] found generative AI raised individual creativity while reducing
collective diversity of the resulting corpus, which is precisely our situation: each book is
fine, the set is repetitive. Anderson et al. [27] found homogenization of ideation among
people using the same model. Chakrabarty et al. [28] found LLM-generated creative writing
scores lower than professional writing on originality dimensions specifically.

Holtzman et al. [29] gives the older, mechanical version: likelihood-maximizing decoding
produces degenerate repetition, and the fix is stochastic decoding, which trades diversity
against coherence along a single axis we cannot escape by tuning.

**We observe this directly and it is the cleanest finding we have.** Two agents on the same
model, given different narrative contracts, different settings, different device
vocabularies, and no access to each other's work, produced 21 identical four-word phrases
including "a sky gone properly dark" and "carry the rhythm up", none of which appear in any
input we gave them. After a revision round eliminated those, both agents independently
rewrote the same choice label to the identical new string, "Head up the spiral stair."

This is not a prompting failure. It is what sampling the same model twice does. It bounds
how different two books can be when the same model writes both, and no amount of
architectural cleverness upstream changes it.

### 3.7 Our evaluation instruments were themselves a source of error

We report this because it may be the most transferable lesson.

Tevet and Berant [30] argued that diversity metrics must be validated against the specific
notion of diversity a task cares about, and that commonly used automatic metrics correlate
poorly with human judgments of it. We rediscovered this the hard way. Our deterministic
similarity bench scored a pair of books that shared their narrative obligations at 0.548
perceived similarity, and a pair that did not at 0.547. A human rater separated the same two
pairs immediately. **Our automatic metric had no discriminative power on the exact
distinction the product depends on**, while returning stable, plausible numbers throughout.

Related hazards we hit or should have anticipated:

- Panickssery et al. [33] found LLM evaluators favor their own generations, which is a live
  risk whenever the rater and the author share a model family, as ours did.
- Zheng et al. [32] documented position and verbosity biases in LLM judges, relevant because
  our protocol asks a model to compare two books in a fixed order.
- We found the same books scored 2.2 in isolation and 3.0 comparatively. Whatever the review
  surface shows determines what gets approved.

---

## 4. What we built and what each intervention measured

Ten designs, chronological. Each was a response to the measured failure of the previous one.

| | Design | Result |
| --- | --- | --- |
| S0 | Zero-shot single call | Failed on structure and prose together |
| S1 | Staged pipeline, structure then prose then repair | Shipped; judged inadequate on six specific defects |
| S2 | Human-authored graph, per-node prescribed beats | Works; the beats *are* the book (prescription ratio 0.83 at ages 3-5, 0.40 catalog-wide) |
| S3 | Slot-parameterized graphs with per-request theme binding | Varies what is slotted; freezes everything else byte-identically |
| S4 | Per-node narrative obligation contracts (what a scene is *for*) | Lowered the sameness ceiling; did not lift it |
| S5 | Per-request device pools drawn from a per-binding bible | **Solved on its own terms** (divergence 0.41 to 0.978); recognition unmoved |
| S6 | Sibling-convergence measurement fed back for revision | **Solved on its own terms** (shared 4-grams 20.4 to 1.2 per 1000); recognition unmoved |
| S7 | Varying model tier | Craft scores 4.9 / 4.0 / 2.2 across three tiers; recognition 2.5 at *both* ends |
| S8 | Per-request mutation of the graph | Refuted: shape-preserving operators give structural distance exactly 0.0000; all mutants retain 100% of the parent's authored beats |
| S9 | Multiple complete obligation contracts over one graph | Refuted: recognition landed *earlier* (position 2) than the single-contract control (position 4) |

The measurement instrument throughout: a rater blind to the design walks a path through two
books and reports the reading position at which a child who had just finished book one would
conclude book two is the same book, plus a five-point distinctness score anchored at
"position 2 corresponds to 2.0" and "position 4 corresponds to 2.5".

---

## 5. The empirical result

**Recognition tracks graph topology, and everything else we varied sits downstream of it.**

The decisive case is S9. We wrote two complete narrative contracts over one unchanged graph,
in which every node served a different narrative function. At the fork where recognition
lands, the two contracts framed the three options completely differently: one as "lead with
patience / lead with self-reliance / lead with humility", the other as "follow the maker's
own words / follow his handiwork / follow his confidant."

The blind rater recorded the same fork, in the same order, at position 2.

The reason is structural. A choice's *destination* is an edge in the graph, not a property of
the contract:

```
n_start  -> n_note, n_door, n_keeper
n_inside -> n_stairs, n_study, n_pendulum, n_basement
```

Whatever the contract says choice 1 *means*, it still leads to the decode-the-note scene, and
both authors must still write a stair, a study, a catwalk, and a basement. **A reader
perceives where choices lead, not why the author was told they were offered.**

This unifies the nine prior nulls rather than adding a tenth. Devices change the nouns in the
rooms. Prose changes the wording. Model tier changes the quality. Obligations change why the
rooms matter. None of them changes the rooms, because the rooms are edges.

Consistent with this: the only intervention that moved recognition at all was graph mutation
(S8), and the only mechanism that ever cleared our structural-distance floor was grafting a
subtree from a *different* graph, which is recombination of two structures rather than
variation of one.

**Uncomfortable corollary.** If variety requires distinct graphs, and the space of workable
graph shapes is as small as Ashwell's taxonomy [1] and our own convergence onto it suggest,
then topological variety is bounded by something much smaller than combinatorics implies.
Two branch-and-bottleneck graphs of similar size may be perceptually the same graph.

---

## 6. Where theory and our evidence pull apart

Places we cannot reconcile, offered as leverage:

1. **The plan-then-write literature optimizes coherence; we need decorrelation.** No work we
   found treats between-artifact distinctness as the objective. Is there a formulation of
   this as a diversity-constrained generation problem rather than a quality problem?
2. **Our strongest theoretical support is for the thing that causes our problem.** Sections
   3.3 and 3.5 argue for supplying a fixed plan and verifying externally. That is exactly
   what freezes the topology. The architecture is well-founded *and* is the defect.
3. **Diversity collapse (3.6) is model-level, so it may bound any architecture.** If two
   samples from one model converge on "a sky gone properly dark" with no shared input, is
   architectural variety even the right lever, or does this require different models,
   different decoding, or explicit inter-sample repulsion?
4. **Reader preference may not want what we are building (1.3).** Unresolved and untested.
5. **We may be measuring the wrong construct (3.7).** Detectability is not dissatisfaction,
   and our automatic metrics have demonstrated zero discriminative power on the target
   construct.

---

## 7. Questions for you

Ranked by what would change our decisions most.

1. **Is the formula-fiction reframe in 1.3 correct?** If children's series readers value the
   armature, what is the actual failure mode we should be measuring instead of
   detectability, and how would you measure it?
2. **Is there a mechanism for perceived distinctness that does not require distinct graphs?**
   We have refuted devices, prose, model tier, per-node obligations, and bounded mutation.
   What is left that we have not tried?
3. **Can inter-sample diversity be engineered against a shared plan?** Given 3.6, is there a
   decoding-level, prompting-level, or population-level method (determinantal point
   processes, explicit repulsion against prior outputs, model ensembling, persona
   conditioning) with evidence behind it at this scale?
4. **How would you make the graph itself cheap to vary?** If topology is the fingerprint, the
   bottleneck becomes producing many *validated* graphs. Is graph synthesis under hard
   global constraints a place where classical methods (grammars, planners, constraint
   solvers, generative grammars over Ashwell-style patterns) beat LLM generation outright?
5. **What is the right unit of reuse?** We assume the graph. Alternatives: reuse a *pattern*
   and synthesize graphs from it, reuse *fragments* and recombine, reuse nothing and pay
   per-request. Which has the best diversity-per-unit-of-human-review?
6. **What experiment would falsify our topology conclusion most cheaply?** It rests on n=1
   with separate rater instances on one non-representative graph. Design the replication.

---

## 8. Methods appendix, so you can weight the evidence

**Protocol.** Two books are authored by independently-prompted agents that cannot see each
other's inputs or outputs; tool-call logs are audited afterwards to confirm isolation. A
rater agent, blind to what is being tested, walks one path through each and reports the
recognition position and a five-point score against fixed anchors. Deterministic checks run
alongside as quality guards, so an intervention cannot buy distinctness by degrading books.

**Known weaknesses, stated plainly.**

- n=1 graph for the decisive result, one rated pair per condition, one pass.
- Control and treatment were rated by *separate* rater instances; inter-rater reliability on
  our rubric is unmeasured. Differences under one full position should not be treated as
  signal.
- The graph used for the pilots is a 26-node outlier chosen because it was the only one with
  both a validated contract and a prior recognition baseline. It is not representative of the
  catalog median of 151 nodes.
- The rater compares books back to back, the condition least favorable to formula tolerance.
- Author and rater shared a model family, engaging the self-preference risk in [33].
- Several of our automatic metrics were later shown to be uninformative or miscalibrated;
  section 3.7.

**What we consider solid despite the above:** the deterministic convergence measurements
(they replicate exactly), the same-model idiom convergence observation (it is a direct
observation, not an inference), and the structural claim in section 5 (it follows from graph
definitions, not from the rating).

---

## 9. References

Verification status: **[C]** confirmed by search, **[U]** unverified, cite with caution.

1. Ashwell, S. K. (2015). *Standard Patterns in Choice-Based Games*. These Heterogenous
   Tasks. **[U]**
2. Mawhorter, P., Mateas, M., Wardrip-Fruin, N., & Jhala, A. (2014). Towards a Theory of
   Choice Poetics. *FDG*. **[U]**
3. Riedl, M. O., & Bulitko, V. (2013). Interactive Narrative: An Intelligent Systems
   Approach. *AI Magazine*. **[U]**
4. Riedl, M. O., & Young, R. M. (2010). Narrative Planning: Balancing Plot and Character.
   *JAIR*. **[U]**
5. Murray, J. (1997). *Hamlet on the Holodeck*. Free Press. **[U]**
6. Ryan, M.-L. (2006). *Avatars of Story*. University of Minnesota Press. **[U]**
7. Yang, K., Peng, N., Tian, Y., & Klein, D. (2022). Re3: Generating Longer Stories With
   Recursive Reprompting and Revision. *EMNLP*. **[U]**
8. Yang, K., Klein, D., Peng, N., & Tian, Y. (2023). DOC: Improving Long Story Coherence
   With Detailed Outline Control. *ACL*. **[U]**
9. Mirowski, P., Mathewson, K. W., Pittman, J., & Evans, R. (2023). Co-Writing Screenplays
   and Theatre Scripts with Language Models. *CHI*. **[U]**
10. Fan, A., Lewis, M., & Dauphin, Y. (2018). Hierarchical Neural Story Generation. *ACL*.
    **[U]**
11. Rashkin, H., Celikyilmaz, A., Choi, Y., & Gao, J. (2020). PlotMachines. *EMNLP*. **[U]**
12. (narrative arc evaluation, EMNLP 2024) **[U]**
13. Valmeekam, K., et al. (2023). PlanBench. *NeurIPS Datasets & Benchmarks*. **[U]**
14. Kambhampati, S. (2024). Can Large Language Models Reason and Plan? *Annals of the NYAS*.
    **[U]**
15. Dziri, N., et al. (2023). Faith and Fate: Limits of Transformers on Compositionality.
    *NeurIPS*. **[U]**
16. Huang, J., et al. (2024). Large Language Models Cannot Self-Correct Reasoning Yet.
    *ICLR*. **[U]**
17. Stechly, K., Valmeekam, K., & Kambhampati, S. (2024). On the Self-Verification
    Limitations of LLMs on Reasoning and Planning Tasks. **[U]**
18. (hallucination snowballing, ICML 2024) **[U]**
19. Gou, Z., et al. (2024). CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing.
    *ICLR*. **[U]**
20. Liu, N. F., et al. (2024). Lost in the Middle. *TACL*. **[U]**
21. Karpinska, M., et al. (2024). One Thousand and One Pairs (NoCha). *EMNLP*. **[U]**
22. Chang, Y., et al. (2024). BooookScore. *ICLR*. **[U]**
23. Hsieh, C.-P., et al. (2024). RULER. *COLM*. **[U]**
24. Kirk, R., et al. (2024). Understanding the Effects of RLHF on LLM Generalisation and
    Diversity. *ICLR*. **[U]**
25. Padmakumar, V., & He, H. (2024). Does Writing with Language Models Reduce Content
    Diversity? *ICLR*. **[U]**
26. Doshi, A. R., & Hauser, O. P. (2024). Generative AI enhances individual creativity but
    reduces the collective diversity of novel content. *Science Advances*. **[U]**
27. Anderson, B. R., et al. (2024). Homogenization Effects of Large Language Models on Human
    Creative Ideation. *Creativity & Cognition*. **[U]**
28. Chakrabarty, T., et al. (2024). Art or Artifice? *CHI*. **[U]**
29. Holtzman, A., et al. (2020). The Curious Case of Neural Text Degeneration. *ICLR*.
    **[U]**
30. Tevet, G., & Berant, J. (2021). Evaluating the Evaluation of Diversity in NLG. *EACL*.
    **[U]**
31. Li, J., et al. (2016). A Diversity-Promoting Objective Function. *NAACL*. **[U]**
32. Zheng, L., et al. (2023). Judging LLM-as-a-Judge with MT-Bench. *NeurIPS*. **[U]**
33. Panickssery, A., et al. (2024). LLM Evaluators Recognize and Favor Their Own
    Generations. *NeurIPS*. **[U]**
34. Tam, Z. R., et al. (2024). Let Me Speak Freely? *EMNLP Industry Track*. **[U]**
35. Park, K., et al. (2024). Grammar-Aligned Decoding. *NeurIPS*. **[U]**
36. Willard, B. T., & Louf, R. (2023). Efficient Guided Generation for LLMs. **[U]**
37. Patall, E. A., Cooper, H., & Robinson, J. C. (2008). The effects of choice on intrinsic
    motivation and related outcomes. *Psychological Bulletin*. **[U]**
38. Deci, E. L., & Ryan, R. M. (2000). The "what" and "why" of goal pursuits.
    *Psychological Inquiry*. **[U]**
39. Cawelti, J. G. (1976). *Adventure, Mystery, and Romance*. University of Chicago Press.
    **[U]**
40. Radway, J. (1984). *Reading the Romance*. University of North Carolina Press. **[U]**
41. Nell, V. (1988). *Lost in a Book*. Yale University Press. **[U]**
42. Berlyne, D. E. (1971). *Aesthetics and Psychobiology*. Appleton-Century-Crofts. **[U]**
43. Zajonc, R. B. (1968). Attitudinal effects of mere exposure. *JPSP*. **[U]**
44. Ross, C. S. (1999). Finding without seeking. *Information Processing & Management*.
    **[U]**
45. Scholastic. *Kids & Family Reading Report*. **[U]**
