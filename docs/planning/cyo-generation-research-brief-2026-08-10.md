# Generating choose-your-own-adventure books with LLMs: problem statement, capability analysis, and an open puzzle

> **Status: research brief prepared for external analysis.** Written to be handed to a
> language model with no access to our codebase, so it is self-contained. Its purpose is to
> get independent theorizing on a problem we have attacked from ten directions without
> solving.
>
> **Citations.** Every reference in section 10 was verified against a primary source
> (publisher page, ACL Anthology, or proceedings entry). Six entries in an earlier draft were
> wrong and are corrected here; two claims that could not be verified were removed rather
> than softened. Where a finding is ours rather than published, it is marked as such.

---

## 0. What we are asking you to do

Read sections 1 through 7, then answer section 8.

We are not asking whether LLMs can write stories. They can. We are asking something
narrower: **what architecture produces a large branching narrative that one child can be
given repeatedly, over months, without that child perceiving they are reading the same book
with new paint?**

We have a deployed system that satisfies every requirement except that one. We have measured
ten interventions. Nine did nothing. The tenth pointed at an answer we find expensive and
would like to be wrong about.

Two things we would specifically value:

1. **Attack our framing.** Section 1.4 argues our entire diversity program may rest on a
   category error about what child readers want. The literature search we ran while
   preparing this brief made that argument *stronger* than we expected, and we have not
   acted on it.
2. **Attack our conclusion.** Section 6 concludes that reader-perceived sameness tracks graph
   topology, so variety must come from more graphs. If there is a cheaper mechanism we have
   not tested, we want it.

---

## 1. The product goal, from first principles

### 1.1 The artifact

A guardian requests a story for a specific child. The system generates a **choose-your-own
adventure book**: a directed graph whose nodes carry prose and whose edges are labeled
choices. The child reads on a tablet, offline, choosing at each fork. Every path terminates
at an ending. An adult approves each book before the child sees it.

### 1.2 What we know readers of this form want

**Choice produces engagement, and the effect is strongest for our users.** Patall, Cooper and
Robinson's meta-analysis of 41 studies [41] found choice reliably raised intrinsic
motivation, effort, task performance, and perceived competence. Two moderators matter for
design: the effect is **stronger for children than adults**, and the optimum is around
**two to four successive choices** rather than more. Self-determination theory [42] supplies
the mechanism, with autonomy as one of three basic psychological needs.

Our per-band rules cap options per choice at two to four. That was arrived at
independently and turns out to match the meta-analytic optimum.

Survey evidence points the same way. Scholastic's *Kids & Family Reading Report* [52] reports
**93% of children agree that "my favorite books are the ones I have picked out myself"**
(8th edition, 2024; the comparable 5th-edition figure was 91%).

**Agency is not branching.** Murray [5] named agency as one of three characteristic pleasures
of digital environments, defining it as "the satisfying power to take meaningful action and
see the results of our decisions." The common design error is reading that as an argument for
wide graphs. Mawhorter and colleagues' choice poetics [2] locates the effect one level down:
a choice reads as meaningful based on how it is structured and framed, not merely on what it
leads to. Riedl and Bulitko's survey [3] frames the whole field as managing the tension
between authorial intent and player agency.

This matters because it puts reader experience in the **local texture of a single choice**,
which is the opposite of where our engineering effort has gone. Ryan [6] makes the wider
point that interactive media produce genuinely new narrative modes rather than degraded
literary ones, which is a caution against evaluating our books as if they were novels that
happen to fork.

**Structure has a small vocabulary.** Ashwell's survey of choice-based games [1] identifies
eight recurring macro-topologies: Time Cave, Gauntlet, Branch and Bottleneck, Quest, Open
Map, Sorting Hat, Floating Modules, and Loop and Grow. His observation is that widely
branching shapes are rare because authoring cost explodes, and that branch-and-bottleneck
dominates published work because reconvergence bounds that cost while preserving local
choice.

Our catalog reproduced this independently. Of 61 graphs: 22 branch-and-bottleneck, 11 open
map, 9 sorting hat, 7 time cave, 6 gauntlet, 6 loop and grow. That is six of Ashwell's eight
patterns, with the same shape dominant, arrived at by our authors without reference to his
taxonomy. Weak evidence that we are in the right design space; **strong evidence that the
space is small**, which becomes the problem in section 6.

**Formula is the product in this genre.** This is the literature we had been ignoring, and
the one our verification pass strengthened most.

Ross's study of series-book readers [48] is the direct evidence. Drawing on 142 open-ended
interviews with adult pleasure readers reflecting on childhood reading, plus textual
analysis, it argues that the **predictability of series books is what does the developmental
work**: reliable structure lets a beginning reader practise sense-making across extended
text, and series reading "far from being harmful, might be for some readers an essential
stage in their development as powerful literates." Gannon [49] argues from children's
literature theory that repetition clarifies narrative structure, aids recall, and supplies
ritual pleasure, and that a series book "can only be properly appreciated" against the
pattern of its siblings. Merga [50] found "series adherence" among five recurring themes
when Year 4 and Year 6 children were asked what would make them read more; Loh and
colleagues [51] found series books and repeated reading persistently popular across primary
years.

The general theory sits behind this. Cawelti [46] treats formula as an artistic resource
rather than a mark of failure; Radway's ethnography [47] found romance readers reject books
that *violate* the formula. Nell [45] found ludic reading depends on absorption that
predictability supports, and that readers' pleasure is not predicted by literary quality.
Berlyne [43] gives the shape: hedonic value is an inverted-U function of novelty and
complexity, so both total predictability and total novelty are aversive. Zajonc [44] shows
mere exposure alone increases liking.

### 1.3 Where the tension actually sits

Two literatures pull against each other, and the resolution is not obvious:

- Diversity is what we have been buying. Sameness across books is what we treat as the defect.
- Series-fiction research says formula is the contract, and readers seek it.

The reconciliation is presumably Berlyne's inverted-U [43]: some layer must stay constant
for the series contract to hold, and some layer must vary for the book to be worth reading.
**We have never identified which layer is which.** We have been varying every layer we could
reach and measuring whether readers still notice the constant one.

### 1.4 The reframe we think may invalidate our own program

Our diversity work assumes, untested, that **a child detecting the shared armature is a
failure.**

Our measurement protocol asks a rater to find the reading position at which a child would
conclude "this is the same book in different clothes." **That measures detectability, not
dissatisfaction.** We have been optimizing against detectability and calling it quality.

| | Reader notices shared structure | Reader does not notice |
| --- | --- | --- |
| **Reader is satisfied** | Series pleasure: the case Ross [48] documents | Ideal, and expensive |
| **Reader is dissatisfied** | The failure we assume we measure | Failure for other reasons |

Three consequences we have not tested:

1. If series pleasure dominates, the correct move is the inverse of ours: make the armature
   *legible and consistent*, brand it as a series, and spend the diversity budget on
   scene-level texture rather than graph variety.
2. If it does not, we need the actual dissatisfaction trigger. The leading candidate from
   [2] is local rather than global: the reader's choices stop feeling consequential because
   the same fork recurs, which is a choice-poetics failure and not a topology failure.
3. The moderator is probably elapsed time. Series formula tolerance is measured over books
   read weeks apart. Our rater compares two books back to back, which is the condition
   least favorable to formula tolerance and therefore biases every number we have toward
   "too similar."

**A literature search run specifically to find the counterargument found none.** We looked
for peer-reviewed work arguing that series readers experience formula as a defect and did
not find it; the classic anti-series position in librarianship is prescriptive rather than
reader-evidence-based, and [48] is explicitly a rebuttal to it. We report that as a strike
against our own program.

### 1.5 Operational success criteria

Deterministic code enforces, independent of provenance: graph reachability and termination,
no trap loops, per-band word envelopes, reading level, ending economy and valence mix,
condition and effect coherence across branches, safety classification, and mandatory human
approval.

The unsolved criterion: **the book should be distinct from the other books this same child
has read.** It is the only one that cannot be evaluated on a single artifact, being a
property of a pair relative to one reader's memory. The unit is the child, not the household.

---

## 2. Scale

61 graphs, 11,458 nodes total.

| Band (reader age) | Graphs | Nodes min / median / max | Words per node | Median book |
| --- | --- | --- | --- | --- |
| 3-5 | 7 | 11 / 20 / 32 | 40 | ~800 words |
| 5-8 | 6 | 35 / 57 / 62 | 70 | ~4,000 words |
| 8-11 | 9 | 65 / 121 / 191 | 100 | ~12,100 words |
| 10-13 | 11 | 26 / 149 / 250 | 100 | ~14,900 words |
| 13-16 | 14 | 124 / 277 / 551 | 140 | ~38,800 words |
| 16+ | 14 | 33 / 248 / 677 | 175 | ~43,400 words |

The largest graph is 677 nodes, roughly 118,000 words of branching prose in which every path
must terminate, hold reading level, and not contradict itself where paths reconverge. A novel
with a graph, not a long short story.

---

## 3. Capability analysis: why one pass cannot do this

### 3.1 A composite of two tasks with different profiles

The artifact requires solving a **combinatorial structure problem** (global reachability,
termination, reconvergence consistency) and a **creative generation problem** (controlled
reading level, consistent voice) at once. Our original finding, which motivated the
architecture, was that a single prompt asking for both produced acceptable neither.

The literature supplies a mechanism rather than just a description. Tam et al. [38] found
that imposing structured output formats measurably degrades reasoning, with larger drops
under stricter constraints. Park et al. [39] showed grammar-constrained decoding distorts the
model's learned distribution rather than sampling from it conditioned on validity, and built
a "grammar-aligned" alternative precisely because the naive version costs quality.

**Structural constraint is not free. It is paid for out of the budget that produces content
quality.** That argues for separating the jobs across calls, which is what we do.

Worth noting the alternative this suggests: if validity can be guaranteed by construction
rather than by asking the model, the tension disappears. Regex and grammar-guided decoding
[40] does this at token level, and classical narrative planning [4] did it at plot level long
before LLMs, generating plots that are causally sound by construction. Question 4 in section 8
asks whether that is the right move for graph synthesis.

### 3.2 Hierarchical planning is the established remedy, with a known ceiling

The plan-then-write tradition is well developed for *linear* fiction. Fan et al. [7]
established hierarchical generation, producing a premise then conditioning on it, roughly
doubling human preference. Rashkin et al. [8] added dynamic plot-state tracking against an
outline. Yang et al. [9] scaled to 2,000+ word stories through recursive reprompting
(+14% plot coherence, +20% premise relevance), then showed [10] that pushing creative burden
into a *detailed* outline plus a controller beat that by a further 22.5% absolute. Mirowski
et al. [11] took the strongest version for our purposes: Dramatron generates log line, then
characters, then beats, then dialogue, and 15 industry professionals found it useful for
structure while criticizing logical gaps.

Our architecture is this pattern with the plan **precomputed and human-reviewed** rather
than generated per request.

The ceiling is visible in the same literature. Dramatron's professional evaluators noted
structural sameness across runs. **A fixed plan is a fixed story.** This tradition optimizes
coherence, which is a within-book property. Our problem is a between-book property, and we
found no work in this line that treats it as an objective.

Tian et al. [12] give the quality-side limit: measured on story arcs, turning points, and
arousal/valence, LLM narratives are homogeneously positive and structurally flat relative to
human ones, placing setbacks and climaxes prematurely so suspense collapses in the second
half. That is a *narrative* limitation distinct from the structural ones, and it bears on
whether more graphs would even be well-used.

### 3.3 The branching-specific literature is thin, and what exists agrees with us

Most story-generation work is linear. The choice-based subset is small and recent:

- Mateas, Mawhorter and Wardrip-Fruin [13] used choice poetics as a *generative* target, so
  choices are produced to achieve intended narrative effects rather than merely to be valid.
  This remains the closest thing to a foundational treatment of choice generation as its own
  problem.
- Harmon and Rutman [14] evaluated open-source LLMs generating choices and consequences at
  plot crossroads, producing a taxonomy of 18 failure types graded mild, severe, and
  catastrophic.
- Tikhonov [15] treats identifying *where* a branch should occur as a detection task in its
  own right.
- Wu et al. [16] built an authoring system in which the narrative is specified as a directed
  tree with per-node causal constraints and the LLM fills responses inside it. Their
  design-study finding: **authorial control has to be structural rather than prompt-level to
  keep branches consistent.**

That last result is independent corroboration of our own most expensive finding (section 6).
We arrived at it by refuting prompt-level control ten times; they arrived at it from a
design study. We take the convergence seriously.

**The gap:** we found no benchmark, metric, or method addressing *between-artifact
distinctness* for branching narrative. If that gap is real, question 2 in section 8 may not
have a literature answer waiting.

### 3.4 Compositional degradation predicts where a single pass breaks

Dziri et al. [19] showed transformers reduce multi-step compositional reasoning to
linearized subgraph matching, with performance collapsing as depth and width exceed training
patterns, and errors accumulating rather than cancelling. Zhang et al. [20] showed models
commit to an early wrong answer and generate further false claims to justify it, claims they
can independently recognize as false 67-94% of the time. Error does not stay local.

The planning literature agrees from another direction. Valmeekam et al. [17] found LLM
autonomous plan-generation accuracy very low on classical planning domains, including
name-obfuscated variants that strip linguistic cues, indicating retrieval rather than
planning. Kambhampati [18] argues LLMs are better understood as approximate retrievers of
plan-shaped text.

**The prediction we rely on:** supply the graph and the model performs; ask for the graph and
it degrades. This is what we observe, and it is the strongest theoretical support for the
skeleton architecture.

### 3.5 Long context does not rescue it

Holding a book in context is not using it. Liu et al. [24] found a U-shaped position curve,
with middle-of-context information used far worse than the ends. Hsieh et al. [25] found only
about half of models claiming 32K context hold up at 32K once the task exceeds retrieval.
Karpinska et al. [26] found that on 1,001 minimally-different true/false claim pairs about
recent novels, no open-weight model beat chance and the best model reached 55.8%, despite
near-perfect needle-in-haystack scores. Chang et al. [27] found book-length summarization
suffers systematic coherence failures.

Our requirement is **constraint maintenance across a long generation**, which is the
capability this cluster is least optimistic about.

### 3.6 Self-verification limits force an external gate

This is the single most load-bearing result for our design. Huang et al. [21] found that
without external feedback, intrinsic self-correction generally *degrades* reasoning accuracy,
and that prior reported gains came from oracle labels leaking in. Stechly et al. [22] found
GPT-4 self-verification does not help and often hurts on Game of 24, graph coloring, and
STRIPS planning, while a sound external verifier does: the assumption that verification is
easier than generation does not hold for LLMs. Gou et al. [23] supply the complement:
grounding critique in external tools produces reliable self-correction where unaided
critique does not.

**Never ask the model whether its graph is valid. Compute it.** Our validator is a program,
not a prompt, because of this.

We see the predicted effect directly. Our agents, given a checker to run in a loop, produced
a 31-fact narrative contract passing every coherence check on the first attempt and closed a
large convergence gap in one revision round with no human repair. Without the checker they
do not. The capability is unlocked by external verification exactly as [23] predicts.

### 3.7 Output diversity is the actual bottleneck, and it is a model-level property

Everything above concerns producing **one** good book. Our problem is producing **many
different** ones.

Kirk et al. [30] found RLHF improves out-of-distribution generalisation while substantially
reducing output diversity both per-input and across inputs, evidencing a
generalisation/diversity tradeoff. **The models best at following our constraints are the
ones worst at varying.**

The effect propagates. Padmakumar and He [31] found LLM-assisted writing reduced lexical and
content diversity and made different authors' essays more similar to each other, with the
model contributing the homogenizing text. Doshi and Hauser [32] found generative AI raised
individual story quality while making the resulting corpus measurably more similar. Anderson
et al. [33] found ideation homogenized across users of the same model. Chakrabarty et al.
[34] found LLM stories pass 3-10x fewer expert creativity tests than professional writing,
and that LLM judges do not correlate positively with expert assessment.

Holtzman et al. [28] give the mechanical version: likelihood maximization is the wrong
objective for open-ended generation, and the remedy trades along a diversity/coherence axis
we cannot escape by tuning.

**Our direct observation, which we consider the cleanest finding we have.** Two agents on the
same model, given different narrative contracts, different settings, different device
vocabularies, and no access to each other, produced 21 identical four-word phrases including
"a sky gone properly dark" and "carry the rhythm up", none of which appear in any input we
supplied. After a revision round eliminated those, both agents independently rewrote the same
choice label to the identical new string, "Head up the spiral stair."

This is not a prompting failure. It is what sampling one model twice does, and it bounds how
different two books can be when the same model writes both.

### 3.8 Our evaluation instruments were themselves a source of error

Tevet and Berant [35] argued diversity metrics must be validated against the specific notion
of diversity a task cares about, and found humans estimate content diversity far better than
automatic metrics, while decoding-parameter tuning moves *form* diversity rather than
*content* diversity.

We rediscovered this expensively. Our deterministic similarity bench scored a pair of books
sharing their narrative obligations at 0.548 perceived similarity, and a pair not sharing
them at 0.547. A human rater separated the pairs immediately. **The metric had no
discriminative power on the exact distinction the product depends on**, while returning
stable, plausible numbers throughout. Distinct-n style metrics [29] have the same character:
they measure form.

Related hazards, two of which we walked into:

- Panickssery et al. [37] found LLM evaluators recognize their own generations and that this
  causally drives self-preference. Our rater and authors shared a model family.
- Zheng et al. [36] documented position, verbosity, and self-enhancement biases in LLM
  judges. Our protocol presents two books in a fixed order.
- We measured the same books at 2.2 in isolation and 3.0 comparatively. The review surface
  determines the verdict.

---

## 4. What we built, and what each intervention measured

Ten designs, chronological, each a response to the measured failure of the previous.

| | Design | Result |
| --- | --- | --- |
| S0 | Zero-shot single call | Failed on structure and prose together |
| S1 | Staged pipeline: structure, then prose, then repair | Shipped; inadequate on six specific defects |
| S2 | Human-authored graph, per-node prescribed beats | Works; the beats *are* the book (prescription ratio 0.83 at ages 3-5, 0.40 catalog-wide) |
| S3 | Slot-parameterized graphs, per-request theme binding | Varies what is slotted; freezes the rest byte-identically |
| S4 | Per-node obligation contracts (what a scene is *for*) | Lowered the sameness ceiling; did not lift it |
| S5 | Per-request device pools from a per-binding bible | **Solved on its own terms** (divergence 0.41 to 0.978); recognition unmoved |
| S6 | Sibling-convergence measurement fed back for revision | **Solved on its own terms** (shared 4-grams 20.4 to 1.2 per 1000); recognition unmoved |
| S7 | Varying model tier | Craft 4.9 / 4.0 / 2.2 across three tiers; recognition 2.5 at *both* ends |
| S8 | Per-request graph mutation | Refuted: shape-preserving operators give structural distance exactly 0.0000; all mutants retain 100% of the parent's authored beats |
| S9 | Multiple complete obligation contracts over one graph | Refuted: recognition landed *earlier* (position 2) than the single-contract control (position 4) |

**Instrument.** A rater blind to the design walks a path through two books and reports the
reading position at which a child who just finished book one would conclude book two is the
same book, plus a five-point distinctness score anchored at "position 2 is 2.0" and
"position 4 is 2.5."

---

## 5. The empirical result

**Recognition tracks graph topology. Everything else we varied sits downstream of it.**

The decisive case is S9. We wrote two complete narrative contracts over one unchanged graph,
every node serving a different narrative function. At the fork where recognition lands, the
contracts framed the three options completely differently: one as "lead with patience / lead
with self-reliance / lead with humility", the other as "follow the maker's own words / follow
his handiwork / follow his confidant."

The blind rater recorded the same fork, in the same order, at position 2.

The reason is structural. A choice's *destination* is an edge, not a property of the
contract:

```
n_start  -> n_note, n_door, n_keeper
n_inside -> n_stairs, n_study, n_pendulum, n_basement
```

Whatever the contract says choice 1 *means*, it still leads to the decode-the-note scene, and
both authors must still write a stair, a study, a catwalk, and a basement. **A reader
perceives where choices lead, not why the author was told they were offered.**

This unifies the nine prior nulls rather than adding a tenth. Devices change the nouns in the
rooms; prose changes the wording; model tier changes the quality; obligations change why the
rooms matter. None changes the rooms, because the rooms are edges. Consistent with this: the
only intervention that moved recognition was graph mutation (S8), and the only mechanism that
cleared our structural-distance floor was grafting a subtree from a *different* graph, which
is recombination rather than variation.

It also matches Wu et al. [16] arriving independently at the conclusion that authorial
control must be structural rather than prompt-level.

**Uncomfortable corollary.** If variety requires distinct graphs, and the space of workable
shapes is as small as Ashwell's eight patterns [1] and our own convergence onto six of them
suggest, then topological variety is bounded well below what combinatorics implies. Two
branch-and-bottleneck graphs of similar size may be perceptually the same graph.

---

## 6. Where theory and our evidence pull apart

1. **The plan-then-write literature optimizes coherence; we need decorrelation.** No work we
   found treats between-artifact distinctness as an objective, for linear or branching
   narrative. Is there a formulation of this as diversity-constrained generation rather than
   a quality problem?
2. **Our strongest theoretical support is for the thing that causes our problem.** Sections
   3.4 and 3.6 argue for supplying a fixed plan and verifying externally. That is exactly
   what freezes the topology. The architecture is well-founded *and* is the defect.
3. **Diversity collapse (3.7) is model-level, so it may bound any architecture.** If two
   samples converge on "a sky gone properly dark" with no shared input, is architectural
   variety the right lever at all, or does this need different models, different decoding, or
   explicit inter-sample repulsion?
4. **Reader preference may not want what we are building (1.4),** and the literature leans
   against us.
5. **We may be measuring the wrong construct (3.8).** Detectability is not dissatisfaction,
   and our automatic metrics have demonstrated zero discriminative power on the target.

---

## 7. Methods appendix, so you can weight the evidence

**Protocol.** Two books are authored by independently-prompted agents that cannot see each
other's inputs or outputs; tool-call logs are audited afterwards to confirm isolation. A
rater agent, blind to what is being tested, walks one path through each and reports
recognition position and a five-point score against fixed anchors. Deterministic checks run
alongside as quality guards, so an intervention cannot buy distinctness by degrading books.

**Weaknesses, stated plainly.**

- n=1 graph for the decisive result, one rated pair per condition, one pass.
- Control and treatment were rated by *separate* rater instances; inter-rater reliability is
  unmeasured. Differences under one full position should not be treated as signal.
- The pilot graph is a 26-node outlier, chosen because it alone had both a validated contract
  and a prior baseline. The catalog median is 151 nodes.
- The rater compares books back to back: the condition least favorable to formula tolerance.
- Author and rater shared a model family, engaging the self-preference effect in [37].
- Several automatic metrics were later shown uninformative or miscalibrated (3.8).

**What we consider solid regardless:** the deterministic convergence measurements (they
replicate exactly), the same-model idiom convergence observation (a direct observation, not
an inference), and the structural claim in section 5 (it follows from graph definitions, not
from the rating).

---

## 8. Questions for you

Ranked by what would change our decisions most.

1. **Is the reframe in 1.4 correct?** If children's series readers value the armature, what
   is the actual failure mode we should measure instead of detectability, and how would you
   measure it? Note that [48] and [2] suggest different answers: developmental value of
   predictability versus local choice-poetics failure.
2. **Is there a mechanism for perceived distinctness that does not require distinct graphs?**
   We have refuted devices, prose, model tier, per-node obligations, and bounded mutation.
3. **Can inter-sample diversity be engineered against a shared plan?** Given 3.7, is there a
   decoding-level, prompting-level, or population-level method (determinantal point
   processes, explicit repulsion against prior outputs, model ensembling, persona
   conditioning) with evidence at this scale?
4. **How would you make the graph itself cheap to vary?** If topology is the fingerprint, the
   bottleneck becomes producing many *validated* graphs. Is graph synthesis under hard global
   constraints a place where grammars, planners, or constraint solvers beat LLM generation
   outright, perhaps as a generative grammar over Ashwell-style patterns [1]?
5. **What is the right unit of reuse?** We assume the graph. Alternatives: reuse a *pattern*
   and synthesize graphs from it; reuse *fragments* and recombine; reuse nothing. Which gives
   the best distinctness per unit of human review?
6. **What experiment falsifies our topology conclusion most cheaply?** Design the replication.

---

## 9. Glossary

- **Band**: an age range with its own word, reading-level, and safety envelope.
- **Skeleton / graph**: the reusable directed graph, human-authored and reviewed.
- **Binding**: the per-request setting and cast bound into a graph's slots.
- **Obligation contract**: per-node declaration of what a scene must establish, must not
  establish, what the reader knows on arrival, and what each choice means.
- **Recognition position**: the reading position at which a rater judges a child would call
  two books the same book.

---

## 10. References

All entries verified against a primary source.

**Interactive narrative and choice structure**

1. Ashwell, S. K. (2015). *Standard Patterns in Choice-Based Games*. These Heterogenous
   Tasks, 26 January 2015. Defines eight topologies: Time Cave, Gauntlet, Branch and
   Bottleneck, Quest, Open Map, Sorting Hat, Floating Modules, Loop and Grow.
2. Mawhorter, P., Mateas, M., Wardrip-Fruin, N., & Jhala, A. (2014). Towards a Theory of
   Choice Poetics. *Foundations of Digital Games (FDG)*, paper 19.
3. Riedl, M. O., & Bulitko, V. (2013). Interactive Narrative: An Intelligent Systems
   Approach. *AI Magazine*, 34(1), 67-77.
4. Riedl, M. O., & Young, R. M. (2010). Narrative Planning: Balancing Plot and Character.
   *JAIR*, 39, 217-267.
5. Murray, J. H. (1997). *Hamlet on the Holodeck: The Future of Narrative in Cyberspace*.
   Free Press.
6. Ryan, M.-L. (2006). *Avatars of Story*. University of Minnesota Press.

**Story generation with language models (linear)**

7. Fan, A., Lewis, M., & Dauphin, Y. N. (2018). Hierarchical Neural Story Generation. *ACL*.
8. Rashkin, H., Celikyilmaz, A., Choi, Y., & Gao, J. (2020). PlotMachines:
   Outline-Conditioned Generation with Dynamic Plot State Tracking. *EMNLP*.
9. Yang, K., Tian, Y., Peng, N., & Klein, D. (2022). Re3: Generating Longer Stories With
   Recursive Reprompting and Revision. *EMNLP*.
10. Yang, K., Klein, D., Peng, N., & Tian, Y. (2023). DOC: Improving Long Story Coherence
    With Detailed Outline Control. *ACL*.
11. Mirowski, P., Mathewson, K. W., Pittman, J., & Evans, R. (2023). Co-Writing Screenplays
    and Theatre Scripts with Language Models: Evaluation by Industry Professionals. *CHI*.
12. Tian, Y., Huang, T., Liu, M., Jiang, D., Spangher, A., Chen, M., May, J., & Peng, N.
    (2024). Are Large Language Models Capable of Generating Human-Level Narratives? *EMNLP*.

**Branching and choice-based narrative generation**

13. Mateas, M., Mawhorter, P., & Wardrip-Fruin, N. (2015). Intentionally Generating Choices
    in Interactive Narratives. *ICCC*, 292-299.
14. Harmon, S., & Rutman, S. (2023). Prompt Engineering for Narrative Choice Generation.
    *ICIDS*, Springer LNCS.
15. Tikhonov, A. (2024). Branching Narratives: Character Decision Points Detection. *Games
    and NLP workshop, LREC-COLING*.
16. Wu, Z., Kumyol, S., Wong, S. Y., Hu, X., Tong, X., & Braud, T. (2025). Orchid: A Creative
    Approach for Authoring LLM-Driven Interactive Narratives. *Creativity & Cognition*,
    774-791.

**Planning, compositionality, self-correction**

17. Valmeekam, K., Marquez, M., Olmo, A., Sreedharan, S., & Kambhampati, S. (2023).
    PlanBench: An Extensible Benchmark for Evaluating Large Language Models on Planning and
    Reasoning about Change. *NeurIPS Datasets & Benchmarks*.
18. Kambhampati, S. (2024). Can large language models reason and plan? *Annals of the New
    York Academy of Sciences*, 1534(1), 15-18.
19. Dziri, N., et al. (2023). Faith and Fate: Limits of Transformers on Compositionality.
    *NeurIPS* (Spotlight).
20. Zhang, M., Press, O., Merrill, W., Liu, A., & Smith, N. A. (2024). How Language Model
    Hallucinations Can Snowball. *ICML*.
21. Huang, J., Chen, X., Mishra, S., Zheng, H. S., Yu, A. W., Song, X., & Zhou, D. (2024).
    Large Language Models Cannot Self-Correct Reasoning Yet. *ICLR*.
22. Stechly, K., Valmeekam, K., & Kambhampati, S. (2025). On the Self-Verification
    Limitations of Large Language Models on Reasoning and Planning Tasks. *ICLR* (arXiv
    2402.08115, 2024).
23. Gou, Z., Shao, Z., Gong, Y., Shen, Y., Yang, Y., Duan, N., & Chen, W. (2024). CRITIC:
    Large Language Models Can Self-Correct with Tool-Interactive Critiquing. *ICLR*.

**Long context**

24. Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P.
    (2024). Lost in the Middle: How Language Models Use Long Contexts. *TACL*, 12.
25. Hsieh, C.-P., et al. (2024). RULER: What's the Real Context Size of Your Long-Context
    Language Models? *COLM*.
26. Karpinska, M., Thai, K., Lo, K., Goyal, T., & Iyyer, M. (2024). One Thousand and One
    Pairs: A "novel" challenge for long-context language models. *EMNLP*.
27. Chang, Y., Lo, K., Goyal, T., & Iyyer, M. (2024). BooookScore: A systematic exploration
    of book-length summarization in the era of LLMs. *ICLR* (Oral).

**Diversity and homogenization**

28. Holtzman, A., Buys, J., Du, L., Forbes, M., & Choi, Y. (2020). The Curious Case of Neural
    Text Degeneration. *ICLR*.
29. Li, J., Galley, M., Brockett, C., Gao, J., & Dolan, B. (2016). A Diversity-Promoting
    Objective Function for Neural Conversation Models. *NAACL-HLT*, 110-119. Origin of
    distinct-n.
30. Kirk, R., Mediratta, I., Nalmpantis, C., Luketina, J., Hambro, E., Grefenstette, E., &
    Raileanu, R. (2024). Understanding the Effects of RLHF on LLM Generalisation and
    Diversity. *ICLR*.
31. Padmakumar, V., & He, H. (2024). Does Writing with Language Models Reduce Content
    Diversity? *ICLR*.
32. Doshi, A. R., & Hauser, O. P. (2024). Generative AI enhances individual creativity but
    reduces the collective diversity of novel content. *Science Advances*, 10(28).
33. Anderson, B. R., Shah, J. H., & Kreminski, M. (2024). Homogenization Effects of Large
    Language Models on Human Creative Ideation. *Creativity & Cognition*, 413-425.
34. Chakrabarty, T., Laban, P., Agarwal, D., Muresan, S., & Wu, C.-S. (2024). Art or
    Artifice? Large Language Models and the False Promise of Creativity. *CHI*.
35. Tevet, G., & Berant, J. (2021). Evaluating the Evaluation of Diversity in Natural
    Language Generation. *EACL*, 326-346.

**Model-based evaluation**

36. Zheng, L., Chiang, W.-L., Sheng, Y., et al. (2023). Judging LLM-as-a-Judge with MT-Bench
    and Chatbot Arena. *NeurIPS Datasets & Benchmarks*.
37. Panickssery, A., Bowman, S. R., & Feng, S. (2024). LLM Evaluators Recognize and Favor
    Their Own Generations. *NeurIPS*.

**Constrained generation**

38. Tam, Z. R., Wu, C.-K., Tsai, Y.-L., Lin, C.-Y., Lee, H.-Y., & Chen, Y.-N. (2024). Let Me
    Speak Freely? A Study On The Impact Of Format Restrictions On Large Language Model
    Performance. *EMNLP Industry Track*, 1218-1236.
39. Park, K., Wang, J., Berg-Kirkpatrick, T., Polikarpova, N., & D'Antoni, L. (2024).
    Grammar-Aligned Decoding. *NeurIPS*.
40. Willard, B. T., & Louf, R. (2023). Efficient Guided Generation for Large Language Models.
    arXiv:2307.09702. Preprint, not peer reviewed; implemented as Outlines.

**Reader psychology, children's reading, and formula**

41. Patall, E. A., Cooper, H., & Robinson, J. C. (2008). The effects of choice on intrinsic
    motivation and related outcomes: A meta-analysis of research findings. *Psychological
    Bulletin*, 134(2), 270-300.
42. Deci, E. L., & Ryan, R. M. (2000). The "what" and "why" of goal pursuits: Human needs and
    the self-determination of behavior. *Psychological Inquiry*, 11(4), 227-268.
43. Berlyne, D. E. (1970). Novelty, complexity, and hedonic value. *Perception &
    Psychophysics*, 8(5), 279-286.
44. Zajonc, R. B. (1968). Attitudinal effects of mere exposure. *JPSP*, 9(2, Pt. 2), 1-27.
45. Nell, V. (1988). *Lost in a Book: The Psychology of Reading for Pleasure*. Yale
    University Press.
46. Cawelti, J. G. (1976). *Adventure, Mystery, and Romance: Formula Stories as Art and
    Popular Culture*. University of Chicago Press.
47. Radway, J. A. (1984). *Reading the Romance: Women, Patriarchy, and Popular Literature*.
    University of North Carolina Press.
48. Ross, C. S. (1995). "If they read Nancy Drew, so what?": Series book readers talk back.
    *Library & Information Science Research*, 17(3), 201-236.
49. Gannon, S. R. One More Time: Approaches to Repetition in Children's Literature.
    *Children's Literature Association Quarterly*.
50. Merga, M. K. (2017). What would make children read for pleasure more frequently?
    *English in Education*.
51. Loh, C. E., et al. (2022). What Do Children Want to Read? *Journal of Library
    Administration*.
52. Scholastic. *Kids & Family Reading Report*, 8th edition (2024). 93% of children agree
    "my favorite books are the ones I have picked out myself."
