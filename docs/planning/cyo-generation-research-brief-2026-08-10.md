# Generating choose-your-own-adventure books with LLMs: problem statement, capability analysis, and an open puzzle

> **Status: research brief prepared for external analysis.** Written to be handed to readers
> with no access to the system it describes, so it is self-contained: every term is defined
> in section 9 and no claim depends on inspecting our code. Its purpose is to get independent
> theorizing on a problem we have attacked from ten directions without solving.
>
> **Citations.** Every reference in section 10 was verified against a primary source
> (publisher page, ACL Anthology, or proceedings entry). Six entries in an earlier draft were
> wrong and are corrected here; two claims that could not be verified were removed rather
> than softened. Where a finding is ours rather than published, it is marked as such.

> [!IMPORTANT]
> **Provenance of every rating in this document.** All ratings, annotations and "reader"
> judgments reported here, in both parts, were produced by **LLM agent instances**. **No human
> and no child has read or rated any generated book.** These results are model-based
> hypotheses about reader response, not reader evidence. The reported Fleiss kappas are
> **inter-model agreement**: they measure consistency among those instances and establish
> nothing about validity. Authors and evaluators shared a model family throughout, so the
> whole evaluation battery is exposed to the self-preference effect identified in 3.8 and
> [37].
>
> Deterministic measurements are separate and are **not** affected by this limitation:
> four-gram convergence, graph and schema validation, overlap counts, reading level, and every
> guard in 16n. Read the document with three evidence classes in mind:
>
> | Evidence class | Status here | Permitted use |
> | --- | --- | --- |
> | Deterministic validation | strongest evidence we hold | hard engineering gates |
> | LLM-evaluator judgment | internally consistent, potentially biased | exploratory ranking, failure discovery |
> | Human or child reader evidence | **none** | must not be claimed or assumed |
>
> This banner was added 2026-08-11 after an external reviewer asked which of these our raters
> were. The question was fair and one answer in 14 was wrong; see the correction recorded
> there. Reader-facing optimization in this programme remains provisional.

---

## 0. What we are asking you to do

Read sections 1 through 7, then produce what section 8 asks for: **two to four concrete
architectures we could build and test.** Section 8.1 gives the specification each proposal
should meet, 8.2 the hard constraints, 8.3 the design questions we expect a good proposal to
take a position on, and 8.4 some undeveloped families you are free to extend or dismiss.

We are not asking whether LLMs can write stories. They can. We are asking something
narrower: **what architecture lets one reusable story graph produce many books in which the
reader is asked to decide genuinely different things?**

Sharing an armature across books is fine and intended; the product already supports series.
The defect is narrower, and section 1.3 defines it precisely: the reader being asked to make
the same decisions, in the same order, book after book.

We have a deployed system that satisfies every other requirement. We have measured ten
interventions against this one. All ten varied something other than the decisions
themselves, which we did not realize until we tabulated them (section 5.3).

The central design problem, which every proposal has to solve somehow: **how do you keep a
plan strict enough for a program to verify, while leaving the scene content and the offered
choices free to vary per request?** Our plans currently fix both, and we do not know whether
that is necessary or just how we built it.

Two further things we would value:

1. **A valid instrument.** Section 1.4 shows ours measures the wrong construct. We need one
   that scores decision repetition and ignores shared world, cast, and shape.
2. **Attack the framing.** If you think 1.3 draws the line in the wrong place, say so. It is
   an owner judgment informed by the literature in 1.2, not an experimental result, and an
   architecture aimed at the wrong target is worse than none.

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
space is small**. That mattered while we believed shape was the fingerprint; it matters much
less now, for reasons in 5.4.

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

### 1.3 What actually counts as the defect

Two literatures appear to pull against each other. Diversity is what we have been buying;
series-fiction research says formula is the contract and readers seek it. Berlyne's
inverted-U [43] implies some layer must stay constant and some must vary, and the design
question is which is which.

**We can now answer that, and the answer is narrower than "the books must differ."** Series
framing is already supported in the product, so the constant layer is settled: shared world,
shared cast register, shared scale and format, recurring shape. Those are assets.

The defect is **close regurgitation of process: the reader being asked to make the same
decisions, in the same order.**

Worked example, which is the operational definition we now use.

| | First book | Second book | Verdict |
| --- | --- | --- | --- |
| Setting | unicorn | goblin | (varies in all cases) |
| Choice at the opening fork | "Open the door" / "Go around back" | "Open the door" / "Go around back" | **Defect.** Same decision, new paint. |
| Choice at the opening fork | "Open the door" / "Go around back" | "Go upstairs" / "Go downstairs" | **Acceptable.** |

The second row is the important one, and it is counterintuitive from an engineering seat.
The two books there may be **structurally identical**: the same binary fork, the same
downstream branch shape, the same reconvergence, the same node count. The reader does not
experience that as repetition, because what a reader tracks is **what they were asked to
decide**, not the shape of the decision tree that recorded it.

Two consequences that shape everything below:

1. **Graph shape is reusable. Decision content is not.** Reusing an armature is not the
   defect and never was. Reusing the *decisions* is.
2. This is a property of the choice's **action semantics**, meaning the concrete act the
   reader picks between. It is not a property of the choice's *motivation*, its emotional
   framing, its narrative function, or the props in the room. Those are all things we varied
   at length; see section 5.

### 1.4 Our measurement does not match that definition

Having stated the defect precisely, we have to admit our instrument does not measure it.

Our protocol asks a rater for the reading position at which a child would conclude "this is
the same book in different clothes." **That measures detectability of the shared armature.**
By 1.3, detecting the armature is not the defect: a child who notices they are reading
another book in a familiar series is having the intended experience.

| | Reader notices shared structure | Reader does not notice |
| --- | --- | --- |
| **Reader is satisfied** | Series pleasure, the case Ross [48] documents. Intended. | Ideal, and expensive |
| **Reader is dissatisfied** | **The real defect: decisions repeat** | Failure for other reasons |

Our instrument cannot separate the top-left cell from the bottom-left one, and every number
in section 5 is subject to that confound.

The literature supports the distinction. [2] locates reader experience in the structure and
framing of individual choices, which is the level 1.3 identifies, rather than in global
shape. And a search run specifically to find the counterargument found no peer-reviewed work
holding that series readers experience formula as a defect; the classic anti-series position
in librarianship is prescriptive rather than reader-evidence-based, and [48] is explicitly a
rebuttal to it.

One further bias worth stating: series formula tolerance is measured over books read weeks
apart, while our rater compares two books back to back. That is the condition least
favorable to formula tolerance, so our numbers are biased toward "too similar."

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
before LLMs, generating plots that are causally sound by construction. Question 3 in section 8.1
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

That last result is independent corroboration of our own most expensive finding (5.4).
We arrived at it by refuting prompt-level control ten times; they arrived at it from a
design study. We take the convergence seriously.

**The gap:** we found no benchmark, metric, or method addressing *between-artifact
distinctness* for branching narrative. If that gap is real, the Measurement item in section 8.3
may not have a literature answer waiting.

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
them at 0.547. A model evaluator separated the pairs immediately. **The metric had no
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

**Read this table with 5.3 in hand.** Every row varied something other than scene identity
and the actions offered at each choice, so none of these results speaks to the lever
identified in 1.3. Rows S5 and S6 are genuine successes at what they set out to do; they are
listed as failures only against a target we now think was the wrong one.

---

## 5. The empirical result, and a correction to how we first read it

### 5.1 What the rater actually reported

The decisive case is S9. We wrote two complete narrative contracts over one unchanged graph,
every node serving a different narrative function. At the fork where recognition landed, the
two contracts framed the three options completely differently: one as "lead with patience /
lead with self-reliance / lead with humility", the other as "follow the maker's own words /
follow his handiwork / follow his confidant."

The blind rater recorded the same fork, in the same order, at position 2. Its stated evidence
was not about graph shape. It was:

> Same three doors, decode the note / read the building for a way in / go find the last
> person who remembers, in the same sequence.

and at position 5, four rooms of the same four kinds in the same order.

That is **decision content**, in the exact sense of 1.3. The reader was asked to make the
same three decisions, in the same order, in both books.

### 5.2 The correction

We first read this as "recognition tracks graph topology, therefore variety requires more
graphs." That reading is **too strong, and probably wrong.**

What is fixed in our architecture is not only the shape. Each node also carries a **scene
identity**: a vertex is not an abstract position, it is *the note-decoding scene*. An edge
pointing to an abstract vertex carries no information a reader can perceive; an edge pointing
to "the scene where you decode the note" is the entire fingerprint. Our skeletons bind both,
and we had been attributing to the first what belongs to the second.

The strongest evidence against the topology reading is our own S8. Mutation **changed the
graph** and recognition barely moved, and the mutants retained **100% of the parent's
authored scene directives**. If shape were the fingerprint, rearranging it should have
helped substantially. It did not, because the scenes came along unchanged.

Restated to match 1.3: **shape is reusable; the decisions are not.** Two books can share a
graph and not read as the same book, provided the reader is asked to decide different things.

### 5.3 The cell we never tested

Cataloguing what each intervention actually varied makes the gap embarrassing.

| | What it varied | Scene identity | Action offered at each choice |
| --- | --- | --- | --- |
| S2, S3 | world, cast, props via slots | fixed | fixed |
| S4 | what each scene is *for* | fixed | fixed |
| S5 | props and clues inside scenes | fixed | fixed |
| S6 | wording | fixed | fixed |
| S7 | model quality | fixed | fixed |
| S8 | edges between scenes | fixed | fixed |
| S9 | what each scene is *for*, harder | fixed | fixed |

**Scene identity and action semantics were held constant from S2 onward, in the eight designs
the table covers.** They were constant by construction, because a human-authored skeleton names
each scene at authoring time and every later mechanism was built to vary things *around* that.
S0 and S1 are absent from the table because neither had an authored skeleton to fix them.

So the ten results do not show that the problem is hard. They show that we varied every
layer except the one that 1.3 identifies as the defect, and then measured whether readers
still noticed the layer we never varied.

S9 is the sharpest illustration. It appeared to vary choice semantics and did not: it varied
the *motivation* for each choice while the *act* stayed "examine the note", "search the
building", "find the keeper" in both books. Rewriting why a choice is offered does not change
what the reader is choosing to do.

### 5.4 What survives

Two claims are unaffected and we still hold them:

- **Same-model idiom convergence** (3.7) is real and independent of any of this.
- **Authorial control must be structural rather than prompt-level.** We refuted prompt-level
  control ten times; Wu et al. [16] reached the same conclusion from a design study. But
  "structural" should now be read as *the scene and choice content are specified data*, not
  as *the graph must be regenerated*.

The expensive conclusion, that variety requires many more graphs, is **withdrawn pending a
test of the untested cell**. If it had been right, it would also have been bad news on
Ashwell's evidence [1]: only eight macro-topologies exist, our catalog uses six, and two
branch-and-bottleneck graphs of similar size may well be perceptually one graph. That
argument is now moot if shape is reusable.

---

## 6. Where theory and our evidence pull apart

1. **The plan-then-write literature optimizes coherence; we need decorrelation.** No work we
   found treats between-artifact distinctness as an objective, for linear or branching
   narrative. Is there a formulation of this as diversity-constrained generation rather than
   a quality problem?
2. **Our strongest theoretical support argues for freezing exactly what must vary.** Sections
   3.4 and 3.6 argue for supplying a fixed plan and verifying externally, because models
   plan poorly and cannot self-verify. But a plan detailed enough to be verifiable is a plan
   that names the scenes, and naming the scenes is what 5.2 identifies as the fingerprint.
   **The open architectural question is whether a plan can be strict enough to verify while
   leaving scene and choice content free.** Our skeletons conflate the two, and we do not
   know whether that is necessary or merely how we built it.
3. **Diversity collapse (3.7) is model-level, so it may bound any architecture.** If two
   samples converge on "a sky gone properly dark" with no shared input, is architectural
   variety the right lever at all, or does this need different models, different decoding, or
   explicit inter-sample repulsion?
4. **Our instrument measures the wrong construct (1.4, 3.8).** It scores detectability of the
   armature, which by 1.3 is not the defect. Our automatic metrics separately showed zero
   discriminative power. We do not currently have a valid measurement of the thing we care
   about, which means every number in section 4 needs re-reading before it is trusted.

---

## 7. Methods appendix, so you can weight the evidence

**Protocol.** Two books are authored by independently-prompted agents that cannot see each
other's inputs or outputs; tool-call logs are audited afterwards to confirm isolation. A
rater agent, blind to what is being tested, walks one path through each and reports
recognition position and a five-point score against fixed anchors. Deterministic checks run
alongside as quality guards, so an intervention cannot buy distinctness by degrading books.

**Weaknesses, stated plainly.**

- n=1 graph for the decisive result, one rated pair per condition, one pass.
- Control and treatment were rated by *separate* model-evaluator instances; inter-model agreement is
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

## 8. What we want from you: candidate architectures

**Primary deliverable: two to four concrete architectures we could build and test**, each
aimed at producing many books from reusable material in which the reader is asked to decide
genuinely different things (1.3). We are past the point of wanting a diagnosis. We want
designs, stated precisely enough to implement and to falsify.

Propose designs you think are *right*, not designs you think we will like. If your reading
of sections 3 and 5 says our whole premise is wrong, propose the architecture that follows
from your reading instead.

### 8.1 What each proposal should specify

1. **Name and thesis**, one line.
2. **The fixed/generated split.** What is authored once and reused, what is generated per
   request, and what is human-reviewed. This is the axis every one of our ten designs
   differs on, so state it first.
3. **How structural validity is guaranteed.** Section 3.6 is not negotiable: we will not
   accept "the model checks its own graph." Say what program, grammar, solver, or invariant
   makes reachability, termination, and merge-consistency true, and *when* it runs relative
   to prose generation.
4. **How the decisions vary.** The lever in 1.3. Concretely: at a given fork, what makes one
   book offer "open the door / go around back" and another "go upstairs / go downstairs"?
5. **What stays constant**, and why that preserves the series contract (1.2).
6. **Where the human attaches.** One adult approves every published book regardless. What
   are they looking at, and does your design make that review cheaper or dearer per book?
7. **Expected failure modes**, including the ones that would show up only at book 20 rather
   than book 2.
8. **A falsifiable prediction.** What should this do to decision repetition that our current
   architecture does not, and how would we see it?
9. **The cheapest discriminating experiment**, with a rough cost in generations and human
   hours.
10. **Which of our ten results already bears on it**, including any that count against it.

### 8.2 Constraints any proposal must respect

- Every path terminates; no unreachable nodes; no trap loops.
- Scenes where paths reconverge must be writable from every incoming path, so what the
  reader can be assumed to know at that point has to be knowable in advance.
- Per-band word envelopes, reading level, ending count and valence mix, safety limits.
- A human approves every finished book. Amortizing human review is valuable but cannot be
  achieved by removing the final approval.
- Books are read offline from a static artifact. Nothing may depend on calling a model at
  read time.
- Cost per book must be plausible for a consumer product, so an architecture requiring
  hundreds of frontier generations per book needs to justify itself.

### 8.3 Design considerations we would like addressed

Not separate questions, but the things we expect a good proposal to have a position on.

- **The verifiability/freedom tension (section 6, item 2).** A plan detailed enough to verify is a plan
  that names the scenes, and naming the scenes is what 5.2 identifies as the fingerprint. Is
  that tension real, or an artifact of how we represent plans? A representation that
  separates *shape* from *scene identity*, in the sense of the glossary, is the thing we most
  want to see.
- **Measurement.** We need an instrument that scores decision repetition across two books and
  ignores shared world, cast, and shape (1.4). Candidates we are weighing: action-semantic
  labelling of each choice with set overlap on the labels; embedding distance over choice
  text with setting nouns stripped; or asking a rater the narrow question "were you asked to
  decide the same things" rather than "is this the same book." If your architecture implies a
  different metric, say so.
- **Model-level diversity collapse (3.7).** Two samples converged on "a sky gone properly
  dark" with no shared input. If that floor binds, architecture may not be the lever at all,
  and the answer is decoding-level or population-level: explicit repulsion against prior
  outputs, determinantal point processes, model or persona ensembling. Does your design
  assume that floor away, work around it, or attack it?
- **How much variety is enough.** Berlyne [43] implies an optimum rather than a maximum, and
  the series literature [46, 47, 48] says the constant layer is load-bearing. Maximizing
  distinctness is probably wrong. Is there a principled target?
- **Unit of reuse.** We reuse the graph *and* its scenes. If those separate, the options
  multiply: reuse a shape and synthesize scenes; keep a scene library and recombine; reuse a
  pattern in Ashwell's sense [1] and synthesize both; invert the order and sample the
  decision set first, then build a shape to carry it. Which gives the most decision variety
  per unit of human review?

### 8.4 Families we have considered but not developed

Listed to save you time and to be argued with, not to constrain you. We have no evidence for
any of these; extend, combine, or dismiss them.

- **Shape-only skeletons.** The reusable asset is the graph with *no* scene identities. Scene
  content and choices are synthesized per request against typed constraints at each node.
- **Scene library plus recombination.** Reusable assets are validated scene fragments with
  declared preconditions and effects; a solver assembles a valid graph per request. The one
  mechanism that ever cleared our structural-distance floor was grafting a subtree from a
  different graph, which is a crude version of this.
- **Grammar over patterns.** A generative grammar whose productions are Ashwell-style
  patterns [1], emitting a fresh shape per request that is valid by construction.
- **Planner-based.** Classical narrative planning [4] over preconditions and effects, with
  scene content as free variables, so validity is a property of the plan rather than of a
  reviewed artifact.
- **Decision-first inversion.** Sample the *set of decisions* the book will ask, deliberately
  decorrelated from decisions this child has already seen, then construct a shape that
  carries them. This makes 1.3 the primary object rather than a downstream consequence.
- **Explicit inter-book repulsion.** Keep the current architecture and condition generation
  on the child's prior books with a decorrelation objective, attacking 3.7 directly rather
  than routing around it.

---

## 9. Glossary

- **Band**: an age range with its own word, reading-level, and safety envelope.
- **Skeleton / graph**: the reusable directed graph, human-authored and reviewed. Currently
  fixes both the *shape* and the *scene identity* at every node; 5.2 argues those should be
  separable.
- **Shape**: the graph's structure alone. Which vertices exist, which edges connect them,
  where paths reconverge, how many endings. Carries no information a reader can perceive.
- **Scene identity**: what the scene at a given node *is*, for example "the scene where you
  decode the note." Fixed at authoring time in our system.
- **Action semantics**: the concrete act a choice asks the reader to perform, for example
  "open the door", as distinct from the choice's motivation, emotional framing, or narrative
  function. Section 1.3 argues this is the layer that must vary.
- **Binding**: the per-request setting and cast bound into a graph's slots.
- **Obligation contract**: per-node declaration of what a scene must establish, must not
  establish, what the reader knows on arrival, and what each choice means.
- **Recognition position**: the reading position at which a rater judges a child would call
  two books the same book. Note 1.4: this measures armature detectability, not the defect.

---

## 10. References

All entries verified against a primary source.

### Interactive narrative and choice structure

- **[1]** Ashwell, S. K. (2015). *Standard Patterns in Choice-Based Games*. These Heterogenous
   Tasks, 26 January 2015. Defines eight topologies: Time Cave, Gauntlet, Branch and
   Bottleneck, Quest, Open Map, Sorting Hat, Floating Modules, Loop and Grow.
- **[2]** Mawhorter, P., Mateas, M., Wardrip-Fruin, N., & Jhala, A. (2014). Towards a Theory of
   Choice Poetics. *Foundations of Digital Games (FDG)*, paper 19.
- **[3]** Riedl, M. O., & Bulitko, V. (2013). Interactive Narrative: An Intelligent Systems
   Approach. *AI Magazine*, 34(1), 67-77.
- **[4]** Riedl, M. O., & Young, R. M. (2010). Narrative Planning: Balancing Plot and Character.
   *JAIR*, 39, 217-267.
- **[5]** Murray, J. H. (1997). *Hamlet on the Holodeck: The Future of Narrative in Cyberspace*.
   Free Press.
- **[6]** Ryan, M.-L. (2006). *Avatars of Story*. University of Minnesota Press.

### Story generation with language models (linear)

- **[7]** Fan, A., Lewis, M., & Dauphin, Y. N. (2018). Hierarchical Neural Story Generation. *ACL*.
- **[8]** Rashkin, H., Celikyilmaz, A., Choi, Y., & Gao, J. (2020). PlotMachines:
   Outline-Conditioned Generation with Dynamic Plot State Tracking. *EMNLP*.
- **[9]** Yang, K., Tian, Y., Peng, N., & Klein, D. (2022). Re3: Generating Longer Stories With
   Recursive Reprompting and Revision. *EMNLP*.
- **[10]** Yang, K., Klein, D., Peng, N., & Tian, Y. (2023). DOC: Improving Long Story Coherence
  With Detailed Outline Control. *ACL*.
- **[11]** Mirowski, P., Mathewson, K. W., Pittman, J., & Evans, R. (2023). Co-Writing Screenplays
  and Theatre Scripts with Language Models: Evaluation by Industry Professionals. *CHI*.
- **[12]** Tian, Y., Huang, T., Liu, M., Jiang, D., Spangher, A., Chen, M., May, J., & Peng, N.
  (2024). Are Large Language Models Capable of Generating Human-Level Narratives? *EMNLP*.

### Branching and choice-based narrative generation

- **[13]** Mateas, M., Mawhorter, P., & Wardrip-Fruin, N. (2015). Intentionally Generating Choices
  in Interactive Narratives. *ICCC*, 292-299.
- **[14]** Harmon, S., & Rutman, S. (2023). Prompt Engineering for Narrative Choice Generation.
  *ICIDS*, Springer LNCS.
- **[15]** Tikhonov, A. (2024). Branching Narratives: Character Decision Points Detection. *Games
  and NLP workshop, LREC-COLING*.
- **[16]** Wu, Z., Kumyol, S., Wong, S. Y., Hu, X., Tong, X., & Braud, T. (2025). Orchid: A Creative
  Approach for Authoring LLM-Driven Interactive Narratives. *Creativity & Cognition*,
  774-791.

### Planning, compositionality, self-correction

- **[17]** Valmeekam, K., Marquez, M., Olmo, A., Sreedharan, S., & Kambhampati, S. (2023).
  PlanBench: An Extensible Benchmark for Evaluating Large Language Models on Planning and
  Reasoning about Change. *NeurIPS Datasets & Benchmarks*.
- **[18]** Kambhampati, S. (2024). Can large language models reason and plan? *Annals of the New
  York Academy of Sciences*, 1534(1), 15-18.
- **[19]** Dziri, N., et al. (2023). Faith and Fate: Limits of Transformers on Compositionality.
  *NeurIPS* (Spotlight).
- **[20]** Zhang, M., Press, O., Merrill, W., Liu, A., & Smith, N. A. (2024). How Language Model
  Hallucinations Can Snowball. *ICML*.
- **[21]** Huang, J., Chen, X., Mishra, S., Zheng, H. S., Yu, A. W., Song, X., & Zhou, D. (2024).
  Large Language Models Cannot Self-Correct Reasoning Yet. *ICLR*.
- **[22]** Stechly, K., Valmeekam, K., & Kambhampati, S. (2025). On the Self-Verification
  Limitations of Large Language Models on Reasoning and Planning Tasks. *ICLR* (arXiv
  2402.08115, 2024).
- **[23]** Gou, Z., Shao, Z., Gong, Y., Shen, Y., Yang, Y., Duan, N., & Chen, W. (2024). CRITIC:
  Large Language Models Can Self-Correct with Tool-Interactive Critiquing. *ICLR*.

### Long context

- **[24]** Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P.
  (2024). Lost in the Middle: How Language Models Use Long Contexts. *TACL*, 12.
- **[25]** Hsieh, C.-P., et al. (2024). RULER: What's the Real Context Size of Your Long-Context
  Language Models? *COLM*.
- **[26]** Karpinska, M., Thai, K., Lo, K., Goyal, T., & Iyyer, M. (2024). One Thousand and One
  Pairs: A "novel" challenge for long-context language models. *EMNLP*.
- **[27]** Chang, Y., Lo, K., Goyal, T., & Iyyer, M. (2024). BooookScore: A systematic exploration
  of book-length summarization in the era of LLMs. *ICLR* (Oral).

### Diversity and homogenization

- **[28]** Holtzman, A., Buys, J., Du, L., Forbes, M., & Choi, Y. (2020). The Curious Case of Neural
  Text Degeneration. *ICLR*.
- **[29]** Li, J., Galley, M., Brockett, C., Gao, J., & Dolan, B. (2016). A Diversity-Promoting
  Objective Function for Neural Conversation Models. *NAACL-HLT*, 110-119. Origin of
  distinct-n.
- **[30]** Kirk, R., Mediratta, I., Nalmpantis, C., Luketina, J., Hambro, E., Grefenstette, E., &
  Raileanu, R. (2024). Understanding the Effects of RLHF on LLM Generalisation and
  Diversity. *ICLR*.
- **[31]** Padmakumar, V., & He, H. (2024). Does Writing with Language Models Reduce Content
  Diversity? *ICLR*.
- **[32]** Doshi, A. R., & Hauser, O. P. (2024). Generative AI enhances individual creativity but
  reduces the collective diversity of novel content. *Science Advances*, 10(28).
- **[33]** Anderson, B. R., Shah, J. H., & Kreminski, M. (2024). Homogenization Effects of Large
  Language Models on Human Creative Ideation. *Creativity & Cognition*, 413-425.
- **[34]** Chakrabarty, T., Laban, P., Agarwal, D., Muresan, S., & Wu, C.-S. (2024). Art or
  Artifice? Large Language Models and the False Promise of Creativity. *CHI*.
- **[35]** Tevet, G., & Berant, J. (2021). Evaluating the Evaluation of Diversity in Natural
  Language Generation. *EACL*, 326-346.

### Model-based evaluation

- **[36]** Zheng, L., Chiang, W.-L., Sheng, Y., et al. (2023). Judging LLM-as-a-Judge with MT-Bench
  and Chatbot Arena. *NeurIPS Datasets & Benchmarks*.
- **[37]** Panickssery, A., Bowman, S. R., & Feng, S. (2024). LLM Evaluators Recognize and Favor
  Their Own Generations. *NeurIPS*.

### Constrained generation

- **[38]** Tam, Z. R., Wu, C.-K., Tsai, Y.-L., Lin, C.-Y., Lee, H.-Y., & Chen, Y.-N. (2024). Let Me
  Speak Freely? A Study On The Impact Of Format Restrictions On Large Language Model
  Performance. *EMNLP Industry Track*, 1218-1236.
- **[39]** Park, K., Wang, J., Berg-Kirkpatrick, T., Polikarpova, N., & D'Antoni, L. (2024).
  Grammar-Aligned Decoding. *NeurIPS*.
- **[40]** Willard, B. T., & Louf, R. (2023). Efficient Guided Generation for Large Language Models.
  arXiv:2307.09702. Preprint, not peer reviewed; implemented as Outlines.

### Reader psychology, children's reading, and formula

- **[41]** Patall, E. A., Cooper, H., & Robinson, J. C. (2008). The effects of choice on intrinsic
  motivation and related outcomes: A meta-analysis of research findings. *Psychological
  Bulletin*, 134(2), 270-300.
- **[42]** Deci, E. L., & Ryan, R. M. (2000). The "what" and "why" of goal pursuits: Human needs and
  the self-determination of behavior. *Psychological Inquiry*, 11(4), 227-268.
- **[43]** Berlyne, D. E. (1970). Novelty, complexity, and hedonic value. *Perception &
  Psychophysics*, 8(5), 279-286.
- **[44]** Zajonc, R. B. (1968). Attitudinal effects of mere exposure. *JPSP*, 9(2, Pt. 2), 1-27.
- **[45]** Nell, V. (1988). *Lost in a Book: The Psychology of Reading for Pleasure*. Yale
  University Press.
- **[46]** Cawelti, J. G. (1976). *Adventure, Mystery, and Romance: Formula Stories as Art and
  Popular Culture*. University of Chicago Press.
- **[47]** Radway, J. A. (1984). *Reading the Romance: Women, Patriarchy, and Popular Literature*.
  University of North Carolina Press.
- **[48]** Ross, C. S. (1995). "If they read Nancy Drew, so what?": Series book readers talk back.
  *Library & Information Science Research*, 17(3), 201-236.
- **[49]** Gannon, S. R. (1987). One More Time: Approaches to Repetition in Children's
   Literature. *Children's Literature Association Quarterly*, 12(1), 2-5.
   <https://muse.jhu.edu/article/248501>
- **[50]** Merga, M. K. (2017). What would make children read for pleasure more frequently?
   *English in Education*, 51(2), 207-223. DOI 10.1111/eie.12143
- **[51]** Loh, C. E., Gan, S., & Mounsey, S. (2022). What do children want to read? A case
   study of how one primary school library supported reading for pleasure. *Journal of
   Library Administration*, 62(7), 931-945. DOI 10.1080/01930826.2022.2117955
- **[52]** Scholastic (2024). *Kids & Family Reading Report*, 8th edition, released August
   2024; survey fielded by Fluent Research, December 2022 to January 2023, n = 1,724 parents
   and children. <https://www.scholastic.com/readingreport>. The 93% figure ("my favorite
   books are the ones I have picked out myself") appears in Scholastic's editorial coverage
   of the 8th edition rather than on its Key Findings page; the 5th edition (2015) reported
   91% for the same item.

---

## Part II. Results since this brief was circulated

> Added 2026-08-10 and extended 2026-08-11, after two external reviewers returned candidate
> architectures. The document is named for the day it was created, not the day it last changed;
> Part II is dated per section and a third reviewer's corrections landed on 2026-08-11. Part I
> above is unchanged apart from three edits made on 2026-08-11: the provenance banner at the head
> of the document, which governs both parts, and two places where "rater" became "model
> evaluator", in section 7's methods bullet and in 3.8. All three are listed in section 17. Part I
> otherwise remains the document those reviews responded to.
> Like Part I this is written to be read without access to our code.

### How to read Part II

It has grown to twenty-two sections across two working days. If you are reviewing rather than
re-reading, **the four that carry the argument are 14, 16d, 16l and 16m**, and the rest are
supporting or negative results.

| | Section | Result |
| --- | --- | --- |
| **The instrument** | 14, 15 | Our decision-signature vocabulary ranks book pairs **backwards** against our six-question battery. Both are model-based; no reader has judged either. The property lives in the binding, not in the plan. |
| | 16e | Solution transfer *is* computable from a plan, but only its device-identity half generalises. |
| | **16m** | **An audit of every rating cell we hold: one instrument item has never varied in 12 of 12, and the item that carried every result tied in the one round we ran clean.** |
| **The reuse problem** | **16d** | **Books built from one shared plan converge catastrophically. This was our biggest surprise.** |
| | 16g.1 | Both cheap repairs fail. The leak has five prose channels and we had repaired one. |
| | 16j | Independence comes from what an author is *not shown*, not from what it is told. 126.7 to 1.0 per 1000. |
| | **16l** | **Resolved, with the mechanism restated. A plan can be shared without converging: 13.6 to 2.3 from deleting 422 words of fact glosses. The rule is not "no free text at all"; the passing kernel still carries 473 words. See the correction in 16l.** |
| **Scale and capital** | 16c, 16f | Narrative contracts exist for 2 of 61 skeletons; that, not skeleton count, is the binding cost. |
| | 16i | A model builds structurally valid graphs unaided, 6 of 6, and fails only rules we never gave it. All six are the same story. |
| **Negative results** | 16b, 16h, 16k | Obligation *coverage* is complete, but 5 of 49 deliver only partially and one of those is a real reader-facing defect; "graphs are worlds" is refuted for 18 of 21 graphs; stake economics returns a null. |
| **Our own thresholds** | **16n, 16o** | **Every guard, every threshold, which we inherited, which we invented, and a sensitivity check on the one the headline rests on.** |

**The headline has changed since the first circulation.** Section 18 then asked you to resolve a
dilemma: a plan must reach the bound device to represent what readers respond to, but every shared
sentence makes books converge. **16l resolves it**, and the answer is duller and better than we
expected: share structure and identifiers, share no prose, and generate the rest per book.

## 11. What we did with the reviews

Both reviewers, independently, named the same first step, and neither proposed building anything
before it: **manually author a different decision program over one unchanged graph and see whether
readers notice.** That is precisely the untested cell of 5.3. We ran it.

Design. One 26-node graph, held fixed. Three complete books over it:

| | Goal | World | Puzzle the book is indexed by | Role |
| --- | --- | --- | --- | --- |
| Book A | prove-and-earn | river lock-house | arithmetic: add two numbers, carry past twelve | base |
| Book B | reconstruct-and-remember | bell foundry | rhythm: read pulls as long or short | **control** |
| Book C | salvage-and-triage | river lock-house | drawn outlines: match a silhouette to the object | **treatment** |

The control pair is A against B, which is what our existing pipeline already produces: change the
world wholesale, keep the decisions. The treatment pair is A against C, which varies the acts
offered while **keeping the world A uses**. The treatment therefore carries a handicap the control
does not, which was deliberate: it is the actual series condition, and it biases the comparison
against the treatment.

Instrument. Two rater instances, each rating both pairs, in opposite pair orders, blind to the
design, answering six questions per pair and then a forced choice of which pair asked the reader to
do more similar things. The sixth question is new and is discussed in 13.2.

## 12. Two preparation failures, reported because they would catch anyone

Two rounds were run and discarded before the round that counted. Both passed every automated guard
we had. Anyone attempting this comparison should expect both.

**Failure one: the fill shell leaked the control's vocabulary.** Our authoring shells carried the
skeleton's own choice labels. Thirteen of thirty-five of those labels contain no substitutable
slot, so they reach the author as fixed text from an unrelated book. The author rewrote all
thirty-five labels and still stayed inside the frame it had been handed, turning "force the hands
by guesswork" into "force the hands into place instead" for a story with no clock in it. Every
guard passed. Shared four-gram density between the two books hit 28.8 per thousand words, with four
choice menus opening on identical wording. Rebuilding the shell so that every author-controlled
string is an explicit blank took the same pair to 8.9 and zero.

> [!WARNING]
> **Correction, 2026-08-11: this paragraph called 28.8 "the highest we have ever measured", and
> later sections of this same document falsify it.** 16d reports **59.2 and 63.8** on the 101-node
> replication, and 16l's table carries a **50.1**. 28.8 is the fourth highest figure we report, not
> the first. The comparison against 16d is scope-valid, since 16d's own parenthetical records that
> that round was scored with choice labels included, which is the scope 28.8 was scored under too;
> the 50.1 is body-only and would be lower still on a label-inclusive denominator, so it clears 28.8
> either way. The superlative was written before those rounds existed and was never revisited when
> they landed.

**Failure two: the two books shared their props.** The treatment book's binding reused fourteen of
twenty-four concrete devices from the control base, including the code the whole book is indexed
by. Two blind model evaluators both named exactly those props as their decisive evidence, and one said that
removing two of the affected forks would have left the pairs indistinguishable. That round measured
our binding, not our contract.

Only six of the fourteen shared props sat at the same node. The other eight were the same props
**relocated**, which a same-position comparison scores as fresh, and which one rater described
unprompted as reading like variety fork by fork while being pure rearrangement at the book level.
Any collision check must therefore compare every prop against every prop, not position against
position.

The general lesson, and the reason we report it: **sharing a world is the series contract and must
never be penalised, but sharing the devices inside that world reads to a reader as the same book.**
Those two are easy to conflate when holding the world fixed is a deliberate part of the design.

## 13. The result

### 13.1 Readers: the treatment is less decision-repetitive, thinly

Both raters, in opposite orders, chose the **control** pair as the more decision-repetitive one.
Scores are (rater 1, rater 2), where a high score is bad except where marked.

| Question | Control A/B | Treatment A/C |
| --- | --- | --- |
| Same kinds of actions | 5, 5 | 4, 5 |
| Same tradeoffs | 5, 5 | **4, 4** |
| Different consequences *(high good)* | 2, 2 | **3, 3** |
| Repeated sequence | 5, 5 | 5, 5 |
| Meaningful and informed *(high good)* | 3, 4 | 4, 4 |
| Solution transfer *(high bad)* | 4, 4 | **3, 3** |
| Forced comparison | **more similar** | less similar |

Both converged unprompted on the same three decisive forks and on the same mechanism: the control
changes every noun and almost no decision, while the treatment keeps the nouns and changes the act.
Both books in the control pair decode a notation and set a brass dial at the top of a tower; the
treatment checks an object's orientation against a full-size drawing and seats it at a bench.

**Both also called the effect thin**, and we report it as thin: "three re-skins of one graph",
separation resting on three forks out of eleven, one rater at medium confidence. One rater added
that the treatment would *feel* more repetitive to a child than it scores, because it reuses the
world, and that the verdict flips if shared world is counted against a book. Under the definition
in 1.3 it must not be, so the treatment wins while carrying the heavier load.

### 13.2 The raters designed the only question that worked

The instrument of Part I asked five questions. Both raters of a discarded round independently
reported that two of them saturate: with all books on one graph, "same kinds of actions" and
"repeated sequence" are answered before a word is read. Both then proposed **the same missing
question, without conferring**: *did solving the first book hand you the answer to the second?*

We added it. On first use only one of the two structural questions saturated as predicted: "sequence
repeats" sat at the ceiling in every cell and contributed nothing, while "same kinds of actions" went
on separating the pairs in every round (the audit in 16m has the cell-level counts). The new question
separated the pairs cleanly and consistently. Anyone building an
instrument for this defect should start there rather than with action taxonomies.

### 13.3 The treatment bundled more than one change

Stated against our own interest: the treatment differs from the control base in at least three
ways, not one. It varies the kind of act, it gives four otherwise-decorative rooms a distinct
component each, and it imposes a live global constraint (a closing clock and a carrying limit, and
damage that persists) that re-prices every fork. Raters cited the act at one fork and the stakes at
two. **We cannot presently attribute the effect to decision variation alone.**

The stake observation was not something we had proposed and is now a candidate lever in its own
right: in the control pair, forcing a mechanism is a free retry in both books, and in the treatment
it costs something. That is a property of the consequence graph rather than of the choice.

### 13.4 The instrument was then tested against a pair we knew was bad

The round discarded in 12 was not thrown away. Its contaminated book, sharing fourteen of
twenty-four props with the base book, is the closest thing we have to a known-bad answer, so we
kept it as a negative control and rated it with the same six questions.

| Question | Contaminated pair | Clean pair |
| --- | --- | --- |
| Same kinds of actions | 5, 5 | 5, 4 |
| Same tradeoffs | 5, 5 | 4, 4 |
| Different consequences *(high good)* | 2, 2 | 3, 3 |
| Repeated sequence | 5, 5 | 5, 5 |
| Meaningful and informed *(high good)* | 3, 4 | 4, 5 |
| **Solution transfer** *(high bad)* | **5, 5** | **2, 2** |
| Forced comparison | **more similar**, high confidence both | less similar |

Both raters chose the contaminated pair, in opposite orders, and both independently found the
verbatim sentence the shared binding had produced in both books, and noticed that the two puzzles
reduce to the same arithmetic and land on the same answer. One summarised it better than we could:
"A child who read alpha does not solve delta's puzzle; they recognise it."

We report this because a reader is entitled to ask whether the six questions measure anything. On
the one case where the answer is known in advance, they separate it by three points on the item
that matters, unanimously. That is the evidence the 13.1 result rests on.

It also settles the fate of one question. **"Repeated sequence" has now scored 5 for every pair in
three consecutive runs**, because every book sits on one graph. "Same kinds of actions" runs high
but does vary and does separate the pairs, so it stays; an earlier draft of this paragraph condemned
both, and our own audit in 16m contradicts that for the second. Both raters warned, unprompted and
in nearly the same words, that an evaluator scoring on fork shape alone would report a null result
and be wrong. Anyone reusing this instrument should drop the sequence item from the score and keep
it only as a description of the condition.

## 14. The main finding: our measurement instrument ranks the pairs backwards

> **Correction, 2026-08-11.** This section previously described its input as "blind **human**
> annotation". That was false. Every model evaluator here, and every evaluator anywhere in this
> document, was an LLM agent instance. The error was caught when an external reviewer asked
> which they were. The measurements below are unchanged; only the description of who produced
> them is corrected, along with the wording throughout this section.

We had built a deterministic decision-overlap score on top of blind **model-evaluator**
annotation, precisely to avoid trusting a single judgment. Evaluator instances received each
book's plan stripped of prior annotations, neutrally named, with no knowledge of what was being
compared or which was the control, and applied a written convention whose decisive rule is that
two choices asking the reader to do the same thing get the same labels however the story dresses
them.

| Measure | Control pair | Treatment pair |
| --- | --- | --- |
| Same-decision reuse, one evaluator over all three plans | 24 / 28 | **28 / 28** |
| Action-family reuse | 0.929 | **1.000** |
| Tradeoff reuse | 0.893 | **1.000** |
| Ordered-sequence reuse | 0.909 | **1.000** |
| Two blind model evaluators of the finished books | **more repetitive** | less repetitive |

**The instrument ranks the two pairs in the opposite order from the model evaluators reading the
finished books, on every axis.** Note what this does and does not say: it is a disagreement
between two model-based measures of the same artifacts, not between a metric and a reader.
Replicated across three independent model evaluators. It is not unreliability: inter-model Fleiss
kappa on the same artifacts is 0.96 on action family and 1.00 on consequence.

This is the result we would most like reviewers to sit with, because it invalidates a scoring
approach that both reviews assumed. An architecture that emits decision signatures and is selected
on them would, on this evidence, select the pattern the model evaluators liked least.

## 15. Why it inverts, and why that is worse news than a coarse vocabulary

Our first diagnosis was that the vocabulary was too coarse. We tested that directly by enriching
it: we added a **reasoning-kind** dimension (compute, match, recall, infer, perceive, negotiate,
exert) and a **stake** dimension (nothing, time, resource, access, standing, permanent), and had
two fresh blind model evaluators relabel all three plans.

**Enrichment changed nothing.** Reasoning-kind inverted exactly as action-family had, under both
model evaluators, and stake tied. Zero and one of six fields respectively ordered the pairs as
the model evaluators of the finished books did. The new fields were perfectly labellable, with
kappa 0.77 to 0.81 on reasoning-kind and 0.72
on stake. They were reliable and uninformative at the same time.

The cause is verifiable without any model evaluator. Here is the decisive fork as our plans describe it:

- Book A: "answer the test on its own terms, set it deliberately"
- Book C: "fit the piece the way the diagram shows, deliberately"

A model evaluator following the convention correctly calls those the same decision, because **at the
plan layer they are the same decision.** Adding two numbers and carrying, against holding a part
against its outline to see which way round it goes, is a distinction that lives in the book's
**binding**, one layer below the artifact being annotated. Our plans are deliberately
device-agnostic so that one plan can be bound many ways, and that abstraction is exactly what
discards the property readers respond to.

We then re-ran the identical annotation with each plan's binding attached. Reasoning-kind became
the one field of six that orders the pairs as the model evaluators of the finished books did.
Restricting to the six forks the book's code actually runs through, which our own world recipe
defines in advance as running "from the notice to the bench to the back panel", one model
evaluator scored the control at 1.000 reuse and the treatment at 0.000: the control's two books
bind *different* codes that are the *same kind of thinking*, so they carry identical reasoning
kinds down the whole chain.

**We are not claiming this as a solved metric.** A second model evaluator reproduced the
direction and lost most of the magnitude (0.333 against 0.167), and over the full option set
tied. The
disagreement is localised to one unwritten boundary: is decoding a symbolic notation "compute" or
"match"? Kappa on reasoning-kind is 1.00 on the arithmetic book and 0.92 on the drawn-outline book,
but 0.72 on the rhythm book, and that single call decides most of the effect. Sharpening the
definition would resolve the ambiguous case in whichever direction we wrote it, so we are treating
that as a reliability fix that cannot re-confirm the hypothesis on these same three books.

## 16. What this does to the architectures you proposed

Between the two reviews we received six candidate architectures, which with our own decision-axis
scheduling makes seven designs to weigh. The layer finding in 15 cuts
across them in a way none of us anticipated, so we set it out plainly rather than quietly
re-ranking.

**Three architectures plan decision variety at the layer that provably omits the property.**
Decision-first abstract routing, the decision-program compiler on a fixed topology, and our own
decision-axis scheduling all schedule decisions over device-agnostic plans. On this evidence those
plans cannot express the difference between arithmetic and shape-matching, which is what our raters
actually responded to. This is a defect in the specifications rather than in our instrument, and we
think each needs re-specifying to plan over the plan-and-binding pair.

**Two repulsion architectures inherit the scoring problem.** Repulsive generation via obligation
contracts, and portfolio generation with semantic repulsion, both optimise a novelty objective over
decision semantics. Section 14 says that objective currently points the wrong way. Neither is
refuted, but neither can be evaluated until the objective is fixed.

**Two library architectures are untouched by this finding.** The typed choice-capsule library and
component-based narrative assembly do not depend on scoring decision signatures, and the capsule
proposal's instinct that the reusable unit is a fork-to-join package rather than a scene is
consistent with everything above. We have not tested either.

One reviewer's specific prediction is worth recording as unresolved: that extracting choice text
and stripping setting nouns would separate books by embedding distance. Our results suggest the
separation would be small, because the acts remain the same after noun-stripping, but we have not
run it.

## 16b. A separate question, answered along the way: does the prose deliver the plan?

Our architecture has carried an unverified assumption since we adopted skeletons. The pipeline
checks that a book's graph is valid, that its prose is safe and age-appropriate, and that the
authoring shell survived intact. **Nothing checked whether a scene actually establishes the facts
its plan obliged it to establish.** A node could promise "the friends are now inside" and deliver a
paragraph that never gets them in, and every gate would pass.

We had one book judged blind against all 49 of its obligations.

| Verdict | Count |
| --- | --- |
| Delivered | 44 |
| Partial | 5 |
| Missing | 0 |
| Contradicted | 0 |

**Nothing was missing and nothing was contradicted**, including the structurally awkward
cases: the two merge points where several paths converge and the node may only assume what every
path guarantees, and all eight endings.

**That is coverage, not delivery, and the five partials are the difference.** One of them is a
genuine reader-facing defect and would not have been found any other way. The book's finale requires a grasp of its code, and two of its four exploration rooms teach
that code while the other two do not. A child entering the finale through the wrong two rooms
arrives holding a pattern with no way to use it. **That is path-dependent under-preparation, and no
whole-book measure can see it**, because the book as a whole plainly does teach the code.

We also tried to do this deterministically first, and report the failure because the cheap version
is tempting. A lexical measure comparing each obligation's definition against the prose of the node
meant to establish it scored **precision 0.167 and recall 0.600** against the judged pass. The
misses are the diagnosis: both scored above zero, because lexical overlap tracks whether a node is
*about* the right subject, while the failures that matter are nodes about the right subject that
never close the obligation. Verifying an obligation is a paraphrase problem. "The friends stand
past the tower's seal" is delivered by a boot on a drainpipe bracket and a hand on a sill, and no
word-overlap measure reaches that.

## 16c. An external-validity problem we did not know we had

Setting up the replication turned up something we should have known before running anything.

Every measure in this brief, the branch-obligation screen, the decision-overlap score, all nine
blind annotations, the reasoning-kind result of section 15, is computed from a **narrative
contract**: a per-node object declaring what facts a scene may assume, what it must establish, what
it must not make true, and what each choice asks the reader to do, together with a recipe for the
devices a binding will supply.

That artifact exists for **two** stories in our catalog. One is the 26-node pilot every result here
rests on. The other is for a much younger age band. Our catalog holds eleven skeletons in the band
under discussion and twenty-three finished books, and not one of the production skeletons has a
narrative contract. The catalog's other contract files are a different thing entirely: lists of
substitutable roles, with no nodes, no facts, and no choice semantics, and no measure here can run
against them.

**So this work is n=1 in a stronger sense than "one graph".** It is one representation instance,
hand-built for one small skeleton. Not one of our measures can currently be run against a
production-scale story, and because every finished book in our catalog sits on a distinct skeleton,
there is not even an accidental pair lying around to measure.

We report this for two reasons.

The first is honesty about the weight of Part II. The finding in 15 is real and mechanistic, and it
has been reproduced across model evaluators, but it has been reproduced on one 26-node artifact with
eleven forks, three of which carried the effect. Whether it survives a graph with 39 forks is
genuinely unknown, and we are now authoring a contract for a 101-node skeleton to find out.

The second matters to anyone proposing an architecture. A decision-program compiler, or
decision-first routing, or decision-axis scheduling, all assume a plan object of roughly this shape
is available per request. Producing one is presently a hand-authoring job of around 1.7KB per node
with a fact-closure obligation across every path, and nobody has produced one at production scale.
**That prerequisite is unstated in every proposal we received, including our own.** Whatever the
right architecture turns out to be, generating this artifact at catalog scale is on its critical
path, and it is a larger and less glamorous problem than choosing between the candidates.

## 16d. Reusing one plan across books makes the plan the fingerprint

We attempted the replication described in 16c on a 101-node skeleton with 39 forks, roughly three
and a half times the pilot's eleven. We authored a narrative contract for it, bound three books from that
one contract with devices verified non-colliding, and had three isolated authors write about 10,000
words each. The books are structurally sound and the design was realised exactly.

**We did not rate them, because the convergence guard failed by an order of magnitude.**

| Pair | Shared four-grams per 1000 words (budget 4) | Identical choice menus |
| --- | --- | --- |
| control pair | **59.2** | **51** of 131 |
| treatment pair | **63.8** | **41** of 131 |
| the pilot's clean pair | 1.8 to 2.7 | 0 |

*(That 1.8 to 2.7 range is the per-pair spread across the pilot's sibling set, scored with choice
labels included, which is how this round was originally run. Scored body-only, as every later
section is, the pilot's clean pair is 2.9. The two figures are the same books under two scopes, and
16l states the scope we standardised on.)*

Forty-one to fifty-one of the 131 choice menus open with the same words in two books whose authors
could not see each other's work.

The obvious explanation is that our contract was lexically over-prescriptive, handing every author
the same verbs. **We measured it and it is false.** Labels reuse a distinctive word from their own
choice semantics at 46.6 percent in the converged books and 54.3 percent in the pilot books that
did not converge. Per-book reuse is *higher* in the case that worked.

The real cause is structural, and it is the point worth taking away. **The pilot's books were
written from different contracts**, whose choice semantics were identical at 0 of 35 choices. These
three books were written from **one shared contract**, identical at 131 of 131 by construction.
Sharing the plan means sharing its prose, and three authors writing from one sentence converge on
that sentence.

This is a constraint on every architecture proposed to us that reuses a plan across many books, and
we did not anticipate it. A choice-capsule library, a reusable topology with per-request semantics,
a compiler emitting one decision program per graph: each makes the reusable artifact's own wording a
fingerprint that no amount of binding diversity removes. It is invisible to a device-collision check,
which passed these three books at zero, and it will not show up until books built from the same plan
are compared for shared language.

Three repairs are available and we do not know which works: neutralise the plan's phrasing to
something deliberately flat, generate the phrasing per book while keeping the structure shared, or
require authors to diverge from the wording they are given. Each is far cheaper than authoring one
plan per book, which is what our pilot did without realising that was the load-bearing difference.

**A second finding from the same battery.** All three books landed at whole-book Flesch-Kincaid
8.14 to 8.41 against a 5.5 target with 1.5 tolerance, with only 16 to 20 of 101 nodes inside the
band, and our gate passed all three because at that time every reading-level finding was advisory.
Reading level degrades at scale and nothing was watching the book. **We have since added a blocking
whole-book check at grade 7.0** (appendix 16n), which rejects all three of these; the result above
is what the gate did before that check existed, not a description of the gate today.

## 16e. Your first subsidiary question, answered: solution transfer is computable, halfway

The first circulation's section 18 asked whether "solution transfer" can be computed from a
plan-and-binding pair, since it
is what our raters actually used and it is the only instrument item that discriminated. It can, and
the half that works is not the half we expected.

We score, for every prop on a book's **solution chain** (every prop bound in a device category that
carries the puzzle), the strongest transfer available to it in the other book:

1. **Answer transfer**, the same device, so the second puzzle is recognised rather than solved.
   Detected by text identity, near-identity, or shared vocabulary that almost nothing else in
   either book uses. **No taxonomy of any kind.**
2. **Operation transfer**, different devices resolving by the same operation.
3. **Family transfer**, different operations of the same kind, converting a notation against
   recognising a correspondence.

Scored against all three pairs our blind model evaluators have ranked on the solution-transfer question:

| Pair | Raters | Answer transfer alone | Full score |
| --- | --- | --- | --- |
| base against the contaminated arm | 5, 5 | **1.000** | 1.000 |
| base against the control | 4, 4 | **0.167** | 0.467 |
| base against the treatment | 3, 3 and 2, 2 | **0.000** | 0.225 |

**The ordering is reproduced strictly, and tier 1 reproduces it alone.** That matters more than the
agreement does. Tiers 2 and 3 encode a distinction we discovered on these same artifacts, so their
agreeing with these raters would have proved nothing. Tier 1 encodes nothing, and it does the whole
job.

**Then we ran tiers 2 and 3 against the 101-node bindings, whose vocabulary the classifier had
never seen, and they collapsed**: 2 of 6 chain props classified, the rest unclassifiable. Two
failure modes, neither repairable by extending a word list. It cannot read negation, so "a page of
small hand-drawn icons instead of numbers" scores as arithmetic. And its markers are polysemous, so
"a short tail" on a drawn symbol scores as rhythm. The single operation match it did report between
two arms was an artifact of the slot, not a fact about either puzzle.

So our answer to your question is: **device identity is computable from a plan and generalises;
operation identity is not, and needs a model reading the device.** This is the second time in this
programme that the deterministic version of a question has been good enough to rank and not good
enough to gate, the first being 16b's obligation check. We now treat that as the expected shape of
these measures rather than as bad luck.

**One thing this measure says about section 13 rather than about itself, which we would rather
report than sit on.** The control pair's 0.167 is one link: that book's rhythm hint carrier against
the other's rhythm cipher, a device collision we had already found by hand, sitting on the control
pair's own solution chain. **The 4-against-3 gap in section 13 may therefore be driven by an
uncontrolled collision rather than by the treatment.** The 5-against-2 gap in 13.4 is not exposed
to this, since that pair shares 14 props against none, and it is the stronger of the two results.

## 16f. What the capital question turns out to be

We had filed "does catalog depth solve this" as a purchasing decision requiring no research. The
counting had never actually been done, so we did it:

| | Count |
| --- | --- |
| Skeletons in the catalog | 61 |
| Band-by-length cells | 17 |
| Cells holding 4 skeletons or fewer | **13 of 17** |
| **Skeletons carrying a narrative contract** | **2 of 61** |

The exhaustion premise holds. But the shelf we were counting is the wrong one. Every measure in
this programme, and every architecture proposed to us, runs off a narrative contract, and 3 percent
of the catalog has one; a contract costs roughly 1.7KB per node of hand-authored specification, so
the catalog's 11,458 nodes represent about 19.5MB of writing that does not exist.

**And 16d decides the unit that has to be bought.** If a contract can be shared across the books of
a series, this is a bounded one-time cost per skeleton. If it cannot, the unit is one contract per
*book*, the cost scales with readership rather than with catalog size, and buying more skeletons
buys nothing: a deeper shelf of graphs does not reduce how many contracts you must write per child.
That makes 16d the most commercially consequential result in Part II, which is not how it looked
when we found it.

## 16g. Testing 16d's diagnosis rather than believing it

16d gives a cause and three candidate repairs. It does not test any of them, and we would rather
not hand you a diagnosis we have only reasoned our way to. So we are running the direct test at
pilot scale, where the baseline is known: one contract, two bindings held constant, three
conditions differing only in how the choice semantics reach the author (verbatim, deliberately
flattened, and verbatim-plus-an-instruction-to-diverge), six independently authored books.

The outcome measure is the convergence guard itself, so no rater is involved and the scoring is
repeatable. That is a claim about reproducibility and not about validity: the guard counts verbatim
overlap, and whether verbatim overlap tracks a reader's sense of repetition is exactly the
unvalidated proxy we flag in 16o. We have fixed the prediction and the falsifiers before authoring: if the verbatim
condition lands near the pilot's 1.8 to 2.7 per 1000, our diagnosis in 16d is wrong and the
convergence was a scale effect.

**One thing already fell out of building it.** We first tried to construct the flattened condition
mechanically, deriving each branch's semantics from the fact graph so that no author's voice could
enter. It destroys the fork: at the story's central four-way decision, answering the code, forcing
the mechanism, going round the back and guessing at random all carry exactly the same obligation
and so flatten to exactly the same sentence. That is our own one-way-screen finding arriving from
the other direction. **The fact graph does not contain the decision**, so nothing derived from it
can neutralise the wording while preserving the choice, and the flattening has to be authored under
a stated rule instead. The rule is what is on trial.

### 16g.1 The result: our diagnosis was right and our repairs were aimed at the wrong thing

| Condition | Shared four-grams per 1000 | Against a budget of 4 |
| --- | --- | --- |
| one contract, wording as written | **17.2** | 4.3x |
| one contract, wording flattened | **11.8** | 2.9x |
| one contract, authors told to diverge from it | **13.6** | 3.4x |
| **different** contracts, same graph, same bindings | **2.9** | passes |

**16d is confirmed.** Changing only whether two arms read one contract or two, with graph, bindings,
model and isolation all held constant, moves convergence by a factor of 5.9.

**And neither repair is enough.** The best lands at 11.8, a third off, still around three times
budget. We report the two repairs as indistinguishable from each other: at one book pair per
condition their ordering flips depending on whether choice labels are counted, so the finding is
that neither suffices, not that one beats the other.

> [!WARNING]
> **Correction, 2026-08-11: the three one-contract rows are re-derived from the artifacts. Published
> 16.9, 11.4 and 12.9; measured 17.2, 11.8 and 13.6.**
> Every figure in the table above is now taken directly from `docs/planning/evidence/d6-contract-sharing/`
> and `docs/planning/evidence/obligation-variance/`, using the gram and tokenizer primitives in
> `scripts/check_sibling_fills.py`, at the body-only scope 16l standardises on. The three originally
> published one-contract values do not fall out of the frozen artifacts at either scope:
>
> | Condition | Files | Shared grams | Mean body words | Body-only | Label-inclusive | Published |
> | --- | --- | --- | --- | --- | --- | --- |
> | wording as written | `filled_verbatim_{C,D}` | 48 | 2,784.0 | **17.24** | 16.67 | 16.9 |
> | wording flattened | `filled_neutral_{C,D}` | 34 | 2,894.0 | **11.75** | 13.43 | 11.4 |
> | told to diverge | `filled_diverge_{C,D}` | 38 | 2,801.0 | **13.57** | 12.40 | 12.9 |
> | different contracts | `obligation-variance/filled_{C,D}` | 9 | 3,073.0 | **2.93** | 2.74 | 2.9 |
>
> **The control row reproduces exactly and the three treatment rows do not.** That asymmetry inside one
> table is what makes this a fact about the figures rather than about the harness, and the same harness
> also reproduces all four cells of 16l's re-derivation block below (7 over 3,001.5, 10 over 3,134.0, 40
> over 2,943.0, 40 over 3,110.0) to the gram and the tenth of a word. We have not established how the
> three published values were produced and we are not going to guess: note only that all three sit
> *below* their body-only re-derivation, so this is not the mixed-scope error 16l corrected, whose
> signature was one figure moving in each direction. The artifacts are the authority and the table now
> states what they contain.
>
> **Cite the body-only column, not the label-inclusive one.** The metric concatenates each node body
> with the labels that follow it, which manufactures four-grams spanning the join that exist in neither
> the body nor the label: seven of them in the flattened arm alone, including `drop down inside inside`,
> which is a label's last three words meeting the next body's first. Measured per unit, labels share
> **zero** four-grams in all three conditions and in the control, exactly as reported below. At body-only
> scope the same contamination is one gram across all four pairs.
>
> **What does not change.** 16d is confirmed under either scope: the ratio is 5.9x body-only and 6.1x
> label-inclusive, against the 5.8x first published. Neither repair suffices under either scope, at 2.9x
> and 3.4x budget. And the two repairs stay indistinguishable for the reason already given, their
> ordering flipping with scope: 11.8 below 13.6 body-only, 13.4 above 12.4 label-inclusive. The only
> sentence that moves is "the best lands at 11.4", now 11.8.

We checked the confound before believing any of this. Our pilot's shells shipped draft choice labels
and our new books wrote every label from scratch, which is a second difference that could have
carried the whole effect. It did not: **labels contribute zero shared four-grams in every condition,
including the pilot.** The entire signal is in the bodies, which were written from scratch
throughout, so the comparison is clean. We note without explaining it that this sits alongside 16d,
where 41 to 51 of 131 choice menus were identical, which is not a contradiction once the two
measures are distinguished as 16l does: menu identity is a two-word prefix match per position, and
shared four-grams need four consecutive words; scale and how orthogonal the arms' house styles
happened to be are both candidates.

**The part that changes what we would build.** Tracing each shared gram to the contract field whose
vocabulary it draws on, `choice_semantics` is well under half. The **premise** carries as much or
more, and about a quarter of shared grams trace to no contract field at all and are simply what one
model writes twice: "let out a breath", "for a long moment". The categories overlap, so treat this
as indicative rather than as a partition, but the shape is not subtle.

So the leak has at least four channels and both our repairs addressed one. Three consequences we
would rather state than discover later:

1. A "reusable plan" that shares the dramatic question is already sharing the largest traceable
   channel. If a plan is to be reused, its premise has to vary per book, which is a much stronger
   constraint than it sounds and may not leave much that is reusable.
2. **There is an idiom floor no plan-level intervention reaches, and we measured it: 3.3 shared
   four-grams per 1000**, on book pairs sharing nothing but the model and the age band. Two books
   written by one model from one situation converge on stock phrasing whatever the plan says. We
   checked this because the obvious worry was that the floor sits at our budget of 4.0, in which
   case every architecture fails on a technicality. It does not: the floor is below the budget, so
   the guard is achievable. The more useful thing the floor establishes is that our pilot's
   one-contract-per-book design already scores 2.9, statistically indistinguishable from books
   sharing nothing at all. **Not converging is a solved problem.** The whole question is whether
   reuse can be bought back without giving that up, and our repairs failed at 3.6 times the floor
   with a factor of three of headroom unclaimed.
3. The third repair we named in 16d, generating the plan's decisional content per book, is still
   untested, and **we now predict it will also fall short on its own**, because the premise and the
   idiom floor survive it.

## 16h. Our own "graphs are worlds" proposal, mostly refuted from the graphs alone

One of our in-house options held that a large graph is not a book but a *world*, and a book is a
validated tour through part of it. We hold graphs at 677, 551 and 250 nodes, so the appeal was
obvious: cut two disjoint tours, get two books, pay nothing for a new graph. We had filed this as
needing a fill and a rating to settle. Most of it is decidable from the graphs, for free.

**The first measurement was wrong in an instructive way.** Maximum node-disjoint start-to-ending
paths returns **1 for all 21 of our graphs over 200 nodes**, which reads as a flat refutation. It is
not: the single cut node is the world's **hub** in every case, sitting three to five nodes in. A hub
is what a hub-and-spoke world is supposed to have, and two tours of one world would both cross the
town square. Strict node-disjointness was simply the wrong requirement, and we nearly published the
wrong conclusion from it.

**The right test partitions the spokes**, taking the connected components of what remains once the
hub is removed:

| | Spoke sizes, regions containing endings |
| --- | --- |
| the-skyrail-heist, 246 nodes, **10-13** | **83, 82, 77** |
| the-year-of-four-banners, 212 nodes | 83, 70, 56 |
| the-tricameral-city, 240 nodes | 100, 73, 64 |
| the-tenfold-siege, 677 nodes | **656**, 3, 3, 3, 3, 3 |
| *(17 others)* | same shape: one giant region, remainder 1 to 4 nodes |

**Eighteen of twenty-one put nearly every node in a single region after the hub**, with the rest
being short early-exit endings. There is no second region from which to cut a tour, so the proposal's
own falsifier is confirmed for those graphs on structure alone: they were authored as long stories
with decorations, not as worlds. Scale does not rescue it, and the largest graph is the worst
offender.

**Three are genuinely world-shaped**, and one of them is in the band we study. So the option is
neither dead nor open: its scope is three named graphs rather than "the largest ones", and until now
nobody could have said which graph the proposal meant.

We include this because it generalises past our catalog. **If you are proposing an architecture that
tours a large graph, the graph has to have been authored as a world**, and a graph authored as a
branching story will not become one by being large. That is a property worth checking before
building on it, and it costs a dominator computation.

## 16i. The skeleton-free path, run at last, and what it says about the model

Section 5.3 identified this as the untested cell before this programme began, since every one of the
ten designs held scene identity fixed, and it was never run. 16d gave it a new reason to matter: a
story generated without a skeleton shares no plan
with anything, so it is the only option on our list that structurally cannot hit the convergence
wall. We ran it: six graphs, six isolated authors, the JSON format and nothing else. No skeleton, no
example story, and deliberately **no validator in the loop**, so this is first-pass yield rather
than what the path could reach with repair.

**Structurally, six of six.** Zero dangling targets, zero unreachable nodes, zero nodes with no way
out, zero cycles a reader could be trapped in, at 27 to 35 nodes with 7 to 9 endings each. The thing
we assumed a hand-authored skeleton was load-bearing for, a well-formed graph, this model does
unaided and reliably.

**And our gate blocked all six.** The two findings are not in tension, and the reason matters more
than either:

| Blocking finding | Graphs | What it is |
| --- | --- | --- |
| branch depth 10 to 14, budget 0 to 9 | 4 of 6 | a band budget |
| first decision 1 node in, band floor 2 | 2 of 6 | a band policy |
| ending object fails our schema | 2 of 6 | a schema shape |

**Every blocking finding violates a constraint we never told the author about.** We stated the
structural rules and the model met all of them. We did not state the depth budget, the opening floor
or the ending schema, and those are precisely what failed. As a measure of story-graph competence
this is a pass; as a measure of our brief it is a failure, and the brief was ours. We have not tested
whether stating the constraints closes the gap, and that is the obvious next run.

**On convergence, which is why 16d promoted this.** Across fifteen pairs, bodies only, the mean is
**3.5 shared four-grams per 1000 against a floor of 3.3 and a budget of 4.0.** Six stories sharing no
plan sit at the generator's floor. That is the cleanest evidence we have that the convergence in 16d
came from the shared contract and not from the model.

**But four of fifteen pairs breach the budget, and the reason connects the two results.** Our six
titles are *The Time Capsule of Widow's Watch*, *The Sparrow Hollow Observatory*, *The Bell Beneath
Pike's Cove*, *The Moonbloom Grove*, *The Kite That Remembered* and *The Lighthouse Frequency*. Two
coastal mysteries about a lost signal, two woodland camp discoveries, and **all six are the same
story: children find a thing left behind by an older person and follow clues to it.** No coordination
and no shared plan.

16d found the premise to be the largest traceable channel of convergence and we concluded a reusable
plan must vary its premise per book. This says **removing the plan does not vary the premise**,
because the model converges there on its own. Taken together: the premise has to be varied by
something that actively pushes candidates apart. Sharing less will not do it and neither will asking.
If you are proposing a repulsion mechanism, the premise is a target it must include.

**Limits, fixed before we looked.** Six graphs, one model, 27 to 35 nodes against a catalog median
of 149. This is the easy end and licenses nothing about production scale.

## 16j. How to get an independently worded plan: do not show the author another one

16d left a question we could not answer: if a plan must be generated per book, what stops each
generation converging on the last? We now have a clean answer, from a comparison that fell out of
building an unrelated arm.

Two plans were authored for the same graph under the same requirement, differing in one variable:
whether the author could see an existing plan for that graph. The first was shown it and told, as a
hard and itemised experimental constraint, not to reuse its wording.

| | Shared four-grams per 1000 with the existing plan |
| --- | --- |
| shown it, and instructed to diverge | **126.7** |
| **not shown it**, format given as a written schema | **1.0** |

**A 127-fold reduction from one change to what the author was shown.** Both plans are structurally
sound on identical independent checks, and the second's author found and fixed two real closure
defects of its own.

The first attempt is worth dwelling on, because it looked like a success. It had a different world,
a different slug, and **zero shared fact names**: every marker of independence that an instruction
can be checked against was satisfied. Its `beat_hint` fields shared 260 four-grams per 1000 with
their source. **Instructing divergence buys the appearance of independence and not the substance**,
and it is the first intervention most proposals reach for.

**The premise converged anyway, and this is the useful part.** The author who never saw the reference
independently chose a **clock tower**, against a reference set in a clocktower. Its wording is as
independent as anything we have measured; its setting is the same. Read alongside 16i, where six
authors sharing no plan all wrote "children find a thing left by an older person", the conclusion is
that these are two separate channels needing two separate mechanisms: **withholding closes the
wording channel completely and does nothing whatsoever to the premise.**

**A correction we owe on 16d, found while checking this comparison for confounds.** We had read
16d as saying plan similarity leaks into books by degree, and concluded a per-book plan must be
independently worded. Checking the new plan against the one whose books we had already rated shows
otherwise: **our pilot's two plans are 118.4 shared four-grams per 1000, almost exactly as similar as
the attempt we discarded as unusable, and their books sat at the floor, 2.9.** They share vocabulary
heavily while sharing **zero of thirty-five choice-semantics strings**.

So convergence does not scale with lexical similarity in the way we assumed. **We state the
conclusion as a hypothesis, because the comparison confounds two variables**: our pilot's two plans
differ both in their sentences and in their premise, and 16d identifies the premise as the largest
single channel. What the evidence supports is an association, that plans sharing no sentence
produced books at the floor while plans sharing every sentence did not. **Whether sentence identity
is the operative threshold, and whether separate generation is therefore sufficient, is not
established.** One later arm bears on it: a plan sharing the base's premise engine and none of its
sentences also filled at the floor. That is one observation, not the controlled test, and the
same-premise different-sentence experiment remains unrun.

One limit we cannot resolve with what we hold: our pilot's two plans also differ in *premise*, so
sentence-difference and premise-difference are bundled in the single comparison available, and 16d
found the premise to be the largest channel. Two plans sharing a premise but not a sentence, filled
and measured, is the cheapest experiment left in this line and we have not run it.

For anyone proposing an architecture, in summary: generating a plan per book is sufficient for
wording independence provided no generation sees a sibling plan, near-total independence is more than
the job needs, and **nothing we have found is sufficient for premise independence**. The premise needs
something that actively pushes candidates apart.

## 16k. Stake economics, the option our own raters invented, does not survive a clean test

Both raters in our original run cited, unprompted, something none of our proposals had named: not
*what* the goal is but whether failure costs anything. Our treatment's world imposed a closing clock,
a carrying limit and damage that persists; the control's did not. We built the test.

**Round one looked like a clean positive.** Two blind model evaluators, opposite orders, both ranked the
free-failure pair as more decision-repetitive, with a consistent one-point gap on the
solution-transfer question. We had a result.

**It was our own contamination, twice over, and our raters found both.** The treatment contract
offered "name the cost before the reward" among its label styles, its author took it, and 35 of 35
choice labels began with the word "Spend". One rater called it "the single most distinctive
authorial signature among the three texts". Separately, our blinding renamed the files and left the
provenance inside them: two books carried the same internal `id` and the third did not, which the
second rater found unaided and called "the single most concrete signal in the whole set".

**Rebuilt with both removed, the effect disappears.** The arm was re-filled with the neutral label
style its comparison books use, and all three were blinded by a tool that rebuilds each book from
only what a child sees. Two fresh raters, opposite orders: **they disagree about which pair is more
repetitive, both call it close, and solution transfer ties at 5 and 5.** One volunteers that a
reader weighting the evidence differently "could reasonably call it a tie".

So our own most promising in-house option returns a null. We report it because the confounded version
would have been publishable with a footnote, and because it is the sharpest demonstration we have of
why we terminate a contaminated round rather than caveat it.

**One tension we could not design around, stated so you can weigh the null.** The option requires
"same goal, differing only in whether failure is free", which forces the treatment arm to share the
base book's premise while the *control* arm has a different one. 16d found the premise to be the
largest single channel of similarity, so the treatment was handicapped on exactly that axis, and
both raters noticed the shared framing. The null may understate the effect. Removing the handicap
means abandoning the option's defining requirement.

**What did survive is narrow and worth keeping.** Both raters credited exactly one thing: permanent
damage. Forcing the mechanism "snapped for good" and the repair "would always show", against a
control where the same act jams reversibly. That is one node in twenty-six, which is about the size
of the effect the scores show. If stake economics is worth anything, our evidence says it is the
irreversibility rather than the clock or the carrying limit.

## 16l. The reuse dilemma, resolved: share the structure, share no prose

16d found that books written from one shared plan converge at three to fifteen times our budget.
16g.1 found that both cheap repairs fail. This is the resolution, and it took two runs because the
first was wrong in an instructive way.

**The proposal.** Split a plan in two. A **structural** half (topology, per-node obligations, fact
names, device categories) shared freely, and a **decisional** half (premise, choice semantics, beat
hints, the bound devices) generated per book. The structural half looked safe to share precisely
because of a weakness we had already documented: it provably does not determine what decision a fork
asks, so sharing it cannot make the decisions repeat.

**First run: it failed, at 13.6 per 1000**, indistinguishable from where "tell the author to diverge
from the shared plan" landed, also 13.6 once that figure is re-derived at this scope (16g.1).
Generating the decisional half per book bought nothing measurable.

**Why, and it was our error rather than the idea's.** We traced every shared four-gram to the field
it drew on. **62 percent came from the one prose our "wordless" structural half still carried: 32
one-line definitions of what each fact name means** (that 62 percent is **retracted**, see
immediately below), read by both authors. "The clocktower stands sealed, and the seal reads like a
test rather than an accident." We had called that structure.

> [!WARNING]
> **Retraction, 2026-08-11: the 62 percent in the paragraph above does not reproduce.** Re-tracing
> the failing arm under a strict attribution, only **five of its forty shared grams** come from the
> deleted glosses. That is 12.5 percent, not 62, so the published figure overstates gloss-derived
> convergence by a factor of five. The original number's method was never written down and we cannot
> reconstruct it, so we withdraw it rather than repair it; read it as retracted wherever it appears.
>
> What survives is the deletion's effect rather than this account of it. The glosses are still the
> only thing that differed between the two runs and the convergence still fell. The mechanism the
> re-trace actually supports is convergent elaboration rather than copying, and it is argued in
> section 21, which is where this retraction was made.

**Second run: delete the 32 glosses, change nothing else.** Every other key verified byte-identical,
so the difference is attributable to the glosses alone. 422 words left the shared artifact.

**The metric, defined once and used everywhere below.** Numerator: distinct word four-grams present
in both books, excluding grams made entirely of function words. Denominator: the mean word count of
the two books, per 1000. **Scope: node bodies only.**

Choice labels are excluded, and they have to be. The two conditions differ in how many label words
they contain, 167 against 132.5 on average, against bodies of 2,943 and 3,001.5, so a label-inclusive
denominator moves the rate even when labels share no grams at all. That is not hypothetical: under
the label-inclusive scope the two repair conditions swap places, which is why we report them as
indistinguishable rather than ranking them.

**A second measure appears in these tables and is not the same thing.** "Identical choice menus"
counts, for each node and each choice position, whether two books' labels begin with the same two
content-bearing words. It is a prefix match on a per-position basis, not an overlap over the label
corpus. A pair of books can therefore share 41 menu openings while contributing **zero** shared
four-grams from labels, because two shared content words are not four consecutive words: "Ask the
warden" and "Ask the bell-ringer" share an opening and no four-gram. The two figures measure
different surfaces and both are reported because a reader meets both.

**Correcting our own table.** Two rows below were previously quoted at the wrong scope, with labels
included where every other row excluded them. Recomputed consistently, all rows are body-only:

Three further rows moved on 2026-08-11, in a second pass that checked the claim rather than repeating
it. The three D-6 rows carried their originally published values while this table asserted every row
was body-only, and they were not: re-derived from the artifacts they are 11.8, 13.6 and 17.2, not
11.4, 12.9 and 16.9. The re-derivation, the control that separates a wrong figure from a wrong
harness, and what survives are all in the correction block under 16g.1. The two rows now reading 13.6
are separate measurements that happen to coincide, 13.57 for the diverging repair and 13.59 for the
glossed kernel, and no comparison should be drawn between them at this precision.

| | shared four-grams per 1000, bodies only |
| --- | --- |
| **shared structure, bare identifiers** | **2.3** |
| our pilot, wholly separate plans | 2.9 |
| generator idiom floor, books sharing nothing at all | 3.3 |
| **budget** | **4.0** |
| shared plan, wording flattened | 11.8 |
| shared plan, author told to diverge from it | 13.6 |
| shared structure **with** fact glosses | 13.6 |
| shared plan as written | 17.2 |
| one shared plan, 101 nodes | 50.1 |

The two corrected figures are the stratified designs: with glosses 13.6 rather than the 12.9 we
first published, and without them 2.3 rather than 3.2. Only the first of those is a scope change on
its own. Dropping 167 label words from a 3,110-word label-inclusive denominator can only raise a
rate, and it raises 12.9 to 13.6 exactly with the numerator held at 40; the stratified row moved the
other way and further, so its correction carries a numerator change as well as a scope change, from
ten shared grams to seven. **The direction and the conclusion are unchanged under either scope**,
which we checked before correcting rather than after, but the published numbers were mixed-scope and
that was our error, caught in review. The provenance of the stratified row is now settled and is in
the block below. The table is safe to cite as it now stands.

> [!WARNING]
> **Correction, 2026-08-11, withdrawn the same day: the stratified row is 2.3, as first published.**
> A correction posted earlier today raised this row to 2.5 and asserted that the 2.3 was
> label-inclusive. Both claims were wrong, and they were wrong for one reason: the denominator was
> taken from the surrounding prose rather than measured off the artifacts. The artifacts land in the
> repository with PR #687, under `docs/planning/evidence/d7-stratified-plan/` and
> `docs/planning/evidence/d7b-bare-names/`; until that merges, the paths cited here resolve only on
> that branch. The row is re-derived below directly from those directories' `filled_C.json` and
> `filled_D.json`, using the gram and tokenizer primitives in `scripts/check_sibling_fills.py`:
>
> | | shared grams | mean words | rate |
> | --- | --- | --- | --- |
> | stratified, bodies only | 7 | 3,001.5 | **2.33** |
> | stratified, label-inclusive | 10 | 3,134.0 | **3.19** |
> | glossed, bodies only | 40 | 2,943.0 | **13.59** |
> | glossed, label-inclusive | 40 | 3,110.0 | **12.86** |
>
> Every published figure falls out of that table. Body-only gives 2.3 and 13.6, the two corrected
> values; label-inclusive gives 3.2 and 12.9, the two originally published ones. So 2.3 was always
> the body-only figure and 3.2 was always the label-inclusive one, exactly as the paragraph above
> states, and the withdrawn correction contradicted that paragraph while sitting beside it.
>
> **What went wrong is worth keeping.** The withdrawn block reasoned from a body count of 2,801 for
> the passing pair and 2,894 for the glossed one. Measured, they are 3,001.5 and 2,943. Seven grams
> over the wrong 2,801 gives 2.5, which is where the raised figure came from. The block also treated
> "no whole number of shared grams yields 2.3 at 2,801 words, it would take 6.44" as the tell that
> something was off. It was a real tell, but it pointed at the denominator rather than at the rate:
> at the measured 3,001.5, seven grams yields 2.33, a whole numerator and no anomaly left to explain.
>
> The label word counts were also wrong and inverted. The two conditions carry 167 and 132.5 label
> words on average, glossed and stratified respectively; the withdrawn block used 160 and 182 and had
> the passing arm carrying more, when it carries fewer.
>
> Nothing downstream reverses, and the sixfold range quoted in 16o stands: 13.59 / 2.33 = 5.8.

**13.6 to 2.3 from deleting 422 words**, landing under budget and below the floor. This is the first
artifact in the programme to share a plan and still be indistinguishable, on this measure, from books
that share nothing.

**The obvious objection, which we tested rather than argued.** A fact name without a definition might
be too vague to bind two authors to the same story. It is not. Given only names, each node's
declared function, and their own bound props, the two authors wrote **zero of 32 identical definition
sentences and zero of 35 identical choice semantics**, chose different story engines, and agreed in
meaning on every fact we sampled: `logic_earned` read as "one real, usable piece of the tide
arithmetic needed to set the dial" against "one working piece of the peal-cipher's logic, enough to
actually attempt a setting on the dial". A name plus a function plus a binding is a sufficient
specification.

**The rule we would now state, and the reason it is stated by exclusion.** A shareable plan may
contain identifiers, relations and enumerated categories, and **no free text of any kind**. We tried
twice to enumerate the prose fields instead and missed some both times, first two fields carrying
choice semantics under other names, then the fact glosses. Exclusion is the only formulation that has
survived contact with our own contracts.

> [!WARNING]
> **Correction, 2026-08-11: the rule above is not what the passing artifact implements.** An
> external reviewer objected that the shared kernel still carries device categories, so the rule
> was stated too loosely. We checked the artifact rather than our description of it, and it is
> worse than the objection: the kernel we published as containing no free text still carries
> **473 words** of it, in binding notes, per-node invention notes, eight title constraints and
> the affect ceiling. That is **more than the 422 words the experiment deleted** (895 down to
> 473). One survivor, present identically in both books' shared half: *"one cipher form per
> story, chosen at bind and used consistently from note to clockface to back panel."*
>
> **The measurement stands and the explanation does not.** Convergence still fell from 13.6 to
> 2.3 when those 422 words were deleted with everything else held constant, and 2.3 is still
> below the 3.3 generator floor. But "no free text at all" cannot be what made it pass, because
> the passing arm does not satisfy it. The honest restatement is narrower:
>
> > Free text attached to the **fact vocabulary that nodes reference** drove convergence. Free
> > text **instructing the binding process** did not, at this volume.
>
> The glosses were pulled into local context at every node establishing or assuming that fact;
> the binding notes appear once, in a global preamble. Whether the operative variable is *what
> the text describes* or *how often it is re-read* is now open, and a third arm that deletes the
> 473 while keeping the 422 settles it. It needs no reader and is the highest-value single
> experiment we can currently run.
>
> A second channel this exposes is unguarded: both books draw their cipher form from one shared
> five-element category list, so two books collide by chance about one time in five, and the
> four-gram measure cannot see it by construction. Categories are not free text and are not
> therefore safe.
>
> The rule we adopt in place of ours, after the reviewer's formulation: the shared kernel may
> contain identifiers, topology, formal relations, invariants and genuinely non-semantic
> categories; anything determining what the reader does, thinks about, or uses to solve a
> problem belongs in the per-book layer; **and any free text in the shared half must be
> justified individually rather than by category.**
>
> The process failure is worth naming: we described the artifact from the build script's intent
> instead of asserting the claim against the artifact. Any future claim of the form "the shared
> artifact contains no X" is now checked programmatically before it is published.

**What we cannot tell you.** Eleven of thirty-five choices share their opening verb across the two
books ("Ask the Warden" against "Ask the bell-ringer"; "Turn Back Together" against "Turn back now").
That is the shared structure surfacing at the label layer, and it is arguably the series contract
working as designed, since the same acts are available at the same forks. Whether a child reads
shared opening verbs as repetition is a reader question and no measure we have can answer it.

## 16m. An audit of our own instrument, which changes what we will run next

Before commissioning three more arms for the experiment that would separate our treatment's three
bundled changes, we audited every cell the six-question instrument has produced. Three rounds with
per-question scores, twelve cells each:

| Item | At ceiling | Range | Rounds where it separated the two pairs |
| --- | --- | --- | --- |
| Q1 same kinds of action | 7 of 12 | 4 to 5 | 3 of 3 |
| Q2 same tradeoffs | 6 of 12 | 3 to 5 | 3 of 3 |
| Q3 different consequences | 0 of 12 | **2 to 3** | 2 of 3 |
| **Q4 sequence repeats** | **12 of 12** | **5 to 5** | **0 of 3** |
| Q5 meaningful and informed | 1 of 12 | 2 to 5 | 1 of 3 |
| **Q6 solution transfer** | 7 of 12 | 2 to 5 | 2 of 3 |

**Q4 has never varied.** Twelve cells, every one a 5, and it has never separated the pairs it exists
to separate. Two of our raters recommended retiring it unprompted after an earlier round; we recorded
that and did not act on it. Q3 has never left a two-point band.

**And Q6, the only item that ever carried a result, tied at 5, 5 in the one uncontaminated round we
have run** (16k). On this graph, cleanly presented, our discriminating item is at its ceiling.

So we are not running that experiment. It would spend three plans and three fills to produce a null
that is a property of the instrument rather than of the story. We record this because the temptation
to run it anyway was strong, and because **auditing accumulated cells for ceiling effects costs
nothing and we should have been doing it from the start**.

## 16n. Appendix: the guards, their thresholds, and what they cannot see

Part II cites deterministic measurements against thresholds throughout, and until now it never
showed you the thresholds. That is a real gap for a reviewer: several of our strongest claims are
"this number cleared that budget", and you could not check whether the budget was chosen before or
after the number it judges. Every threshold below was fixed before the result it is used to judge,
except where the row says otherwise.

**Gating guards.** All are deterministic, all run before any human reads a book, and all are
runnable in one command.

| Guard | Measures | Threshold | Where it came from |
| --- | --- | --- | --- |
| graph structure | dangling targets, unreachable nodes, sinks, endings with choices, trapped cycles, missing start | zero of each | properties a reader hits directly; 0 false positives on 3 known-good graphs, all 6 classes caught on a constructed bad one |
| fill integrity | did the fill change anything but bodies, labels and deferred titles | byte-identical elsewhere | verified still catches a retargeted choice and a metadata drift |
| story gate | safety, schema, band profile | not blocked | the production validator |
| prose craft | tense stability, told emotion, moral tags in ending closings | 0 unstable nodes, 0 moral tags, 0.5 told-emotion per 1000 | pre-existing |
| **shared four-grams** | verbatim convergence across sibling books | **4.0 per 1000** | pre-existing budget. **We later measured the generator's own floor at 3.3**, so the budget has 0.7 of headroom, and we report that rather than adjusting either number |
| reading level | whole-book Flesch-Kincaid | **7.0**, the band's own upper edge (5.5 + 1.5) | new. Deliberately *not* chosen to make current work pass: it rejects 9 of our 22 books |
| device collision | do sibling books share their props: **every bound prop of one book against every bound prop of the other**, ignoring which slot each sits in, since a relocated prop is still the same prop | **0 props that are byte-identical or whose content-word Jaccard exceeds 0.5.** A pair at exactly 0.5 passes; the comparison is strictly greater-than | calibrated on one known-bad pair (0.583 of props colliding) and one known-good (0.000) |
| label template | is a book identifiable from its labels with the prose removed | 0.20 first-word concentration | new, after a spoiled round. The spoiled arm scored 1.000; its comparison books 0.057 and 0.171 |
| promise discharge | a choice promising a fact its destination does not carry | zero | new. Two of its four flags on our base contract match defects blind model evaluators reported in separate rounds |

**Non-gating measures, and why they are not gates.**

| Measure | Why it cannot gate |
| --- | --- |
| solution transfer, tiers 2 and 3 | the operation classifier reads 2 of 6 props on an unseen contract; fails on negation and polysemy |
| fill fidelity | precision 0.167, recall 0.600 against a model-judged pass on the same 49 obligations |
| prose review worklist | assembles the label-against-destination and merge-assumption questions; the judging is a model call |

**What a green battery does not mean, stated because it would be easy to over-read.** It does not
mean the prose delivers its obligations, that a label leads where it promises, or that a merge node
avoids assuming a path the reader did not take. Those are entailment questions, and we have twice
measured that attempting them lexically produces false confidence.

Two defects reported by blind model evaluators are of exactly that kind, and both were in books every guard
above had passed: a choice reading "call the risk not worth it" whose destination has the character
attempt the crossing and slip, and a merge node naming clues from two of four rooms when a reader
visits one. A third, the path-dependent under-preparation in 16b, is the same class again and was
found by a model pass rather than by a reader. We say "two readers found two" rather than a rounder
number because the guard table only evidences those two.

**One honest asymmetry.** The convergence budget is the threshold most of Part II turns on, and it
is the one we did not set: it predates this work. What we contributed is the floor beneath it, and
the finding that every artifact we have ever measured sits either at that floor or at three to
fifteen times the budget, with nothing in between until 16l.

## 16o. Every assumption and threshold we set, and whether anything depends on it

The appendix above lists the guards. This lists the *choices* inside them, separated into what we
inherited and what we invented, because a reviewer should not have to reverse-engineer which numbers
are evidence and which are taste. Where a number is arbitrary we say so in those words.

### Thresholds we inherited and did not choose

| | Value | Source |
| --- | --- | --- |
| shared four-gram budget | 4.0 per 1000 | predates this work |
| reading-level band | grade 5.5, tolerance 1.5 | product spec |
| model evaluator agreement floor | kappa 0.60 | Landis, J. R., & Koch, G. G. (1977). The Measurement of Observer Agreement for Categorical Data. *Biometrics* 33(1), 159-174, whose "substantial" band begins at 0.61 |
| minimum words for a stable Flesch-Kincaid | 20 | a rule of thumb in our own validator, **not traceable to a specific source**; we inherited it and have not verified its provenance |

**The first is the one most of Part II turns on and it is not ours.** We contributed the floor
beneath it, not the budget.

### Thresholds we chose, with what each rests on

| | Value | Rests on | Honest description |
| --- | --- | --- | --- |
| generator idiom floor | 3.3 per 1000 | **3 book pairs**, one model, one age band, range 1.9 to 5.0 | an observation on a small sample, not a threshold. We quote it like one, and a reader should not take 3.3 as a general property of language models, or read a single result near it as established equivalence |
| label-template ceiling | 0.20 first-word share | 3 books: 1.000 bad, 0.057 and 0.171 good | **arbitrary within a wide gap.** Anything from about 0.25 to 0.9 separates the observed cases identically |
| label shape advisory | 0.65 | none | **arbitrary.** Advisory only, never gates |
| whole-book reading grade | 7.0 | the inherited band's own edge | derived, not chosen, but it inherits the band's authority |
| share of nodes in band | 0.50 | none | **arbitrary.** Advisory only |
| device-collision Jaccard | **exceeds 0.5**, same definition as 16n | 1 known-bad pair, 1 known-good | thin, and we said so when we built it. The 0.583 and 0.000 quoted in 16n are collision *rates* over the prop set, not Jaccard values; the two numbers are different quantities and we have seen them confused |
| rare-vocabulary signal | 3 shared words, each in at most 2 props | one worked example | **arbitrary**, and it inverted on a short chain until we fixed the corpus |
| solution-transfer tier weights | 1.0, 0.6, 0.3 | **nothing** | **purely invented.** See below |
| solution-transfer ceiling | 0.35 | nothing | **arbitrary** |

**The tier weights deserve their own sentence because they are the worst offender in this
programme.** We assigned 1.0, 0.6 and 0.3 to three grades of puzzle-solution transfer with no
justification whatsoever; any monotone triple would have served. **Nothing we report depends on
them**, because the result that section 16e rests on was reproduced by the top tier *alone*, which
carries no weights and no taxonomy. We would ask you to read the weighted score as decoration.

### Does the headline depend on any threshold? We checked

The claim in 16l, as corrected there, is that free text attached to the fact vocabulary nodes
reference drove convergence while free text instructing the binding process did not, at this volume.
It is stated against the 4.0 budget, so we varied the budget. The rows below are recomputed against
the corrected body-only figures, 2.3 for the stratified pair and 13.6 for the glossed one:

| Budget | Does "the stratified plan works and the glossed one fails" still hold? |
| --- | --- |
| 2.0 | no, nothing passes |
| **2.5 to 13.5** | **yes** |
| 14.0 and above | no, the failing design starts passing |

The middle row is a sampled band, not a boundary: the stratified pair's own value is 2.33, so a
budget of 2.5 sits just inside it. No cell moved when the stratified figure was briefly raised to
2.5 and then withdrawn back to 2.3, which is the useful part of that episode: the band is wide
enough that the disputed tenth never reached a verdict.

**The conclusion survives every budget across roughly a sixfold range**, 2.3 to 13.6, a ratio of
5.8, so it is not an artifact of the number we were handed. And there is a stronger statement that
needs no budget at all: at 2.3 the stratified pair sits **below our measured floor of 3.3**, meaning
it is not
distinguishable from two books that share nothing whatsoever. We would rather you judged 16l on that
than on a threshold, subject to the caveat on the floor's own provenance in the threshold table
above: three pairs is an observation, not an established equivalence.

### Assumptions that are not numbers

These are load-bearing and none is established by our evidence.

1. **That shared four-grams measure "reads like the same book".** It is a proxy for verbatim
   convergence, it is deterministic and cheap, and no reader has ever been asked whether it tracks
   their experience. Every convergence claim in Part II inherits this.
2. **That one model's idiom floor generalises.** We measured 3.3 on one model. A different generator
   has a different floor, and every margin we quote moves with it.
3. **That shared world, cast and graph shape must never count against a pair.** This is our product
   owner's ruling on what a series *is*, not a finding, and our rating instrument is built on it.
4. **That loop-back exploration is a convention rather than a flaw.** Also an owner ruling, made
   against both raters' stated view, and recorded as overriding them.
5. **That a 26-node graph tells us anything about a 149-node one.** Our decisive results are on the
   26-node pilot; the one attempt at production scale halted at the guards, and reading level
   degraded badly there.
6. **That author and rater sharing a model family is tolerable.** It engages self-preference, we
   flagged it in Part I, and we have not controlled for it since.

### Where an arbitrary choice could have changed a result, and did

We record one, because it is the argument for taking this section seriously. We discarded a
stake-economics contract for sharing 126.7 four-grams per 1000 with its reference, on the reasonable
but unexamined assumption that convergence scales with lexical similarity. It does not: the threshold
is sentence identity, and by that criterion the discarded artifact was the *correct* arm and we had
thrown away the better experiment. The criterion was arbitrary, we had not written it down as a
choice, and it cost us a round.

## 17. Corrections to Part I

- **Three edits were made to Part I's own text on 2026-08-11**, and they are the only ones. The
  provenance banner was added at the head of the document; section 7's methods bullet now reads
  "separate *model-evaluator* instances" and "inter-model agreement" where it read "separate *rater*
  instances" and "inter-rater reliability"; and 3.8's "a human rater separated the pairs
  immediately" now reads "a model evaluator", the one place the first sweep missed. Everything else
  in Part I is as the reviewers received it.
- **5.3's "untested cell" has been tested**, and the result is not the simple one either reading
  predicted. Varying the acts offered does reduce perceived decision repetition, thinly, but it is
  much harder to do on a fixed graph than we assumed, and our first two attempts to do it failed
  while appearing to succeed.
- **A hypothesis we advanced after Part I and have since refuted:** that the graph plus fact-graph
  closure pins the decisions, so a branch's obligations determine its decision. We built a
  deterministic checker for this and it reproduced two known failures. Book C then rebuilt the fact
  graph completely, scoring zero on that checker, and blind annotation still called 28 of 28
  options the same decision. The checker is a one-way screen: a high score is evidence the
  decisions repeat, a low score is no evidence they differ.
- **3.8 understated the problem.** It said our instruments were a source of error. Section 14 shows
  one of them ranked the pairs in the opposite order from the judgement it existed to predict,
  which is a stronger claim than "noisy". With two pair conditions that is a rank reversal, not a
  computed correlation, and we no longer describe it as anti-correlation.
- **A product judgment we withdrew.** Both raters reported that most forks on this graph reconverge
  with no differing consequence and called it illusory choice. Our own product owner rejected the
  framing: loop-back exploration paths are a convention of the form, on the analogy that in tabletop
  play a party sweeps every room precisely because some rooms are empty and you cannot know which
  without looking. The structural observation stands and the defect framing does not.

## 18. What we would ask you now

**The question we put to you last time is answered, and by us rather than by you**, so this section
is rewritten rather than extended. We asked: at what layer must a plan be specified so the property
readers respond to is representable in it while the plan stays reusable? We framed it as a dilemma
with two horns, abstraction that discards what readers notice against binding that destroys reuse,
and said no architecture proposed to us had named it.

**16l dissolves it.** A plan may share structure, identifiers and enumerated categories freely,
while the prose attached to the fact vocabulary its nodes reference must not be shared. That
formulation reaches the generator's own floor while still binding two independent authors to the
same story. The horns were an artifact of our plans mixing structure and prose in one object and
sharing the whole thing.

We first stated this as "and must share no free text at all", which is stronger than our evidence
and is not what the passing artifact implements: it still carries 473 words of binding-process
prose. The correction in 16l gives the measured version and the experiment that would settle the
mechanism. The dissolution survives the correction; the clean slogan does not.

That closes the largest thing we were stuck on. What we would now value from a reviewer, in order:

1. **Attack 16l, because we have one pair of books at one graph size.** It is a single 26-node
   graph, one model, two arms, and a deterministic measure of verbatim overlap. The specific weakness
   we can see is that our convergence measure counts shared four-grams and our result rests on
   landing at a floor defined by that same measure. **Is there a way this passes our check and still
   reads as the same book?** The candidate we already found and cannot resolve is that eleven of
   thirty-five choices share an opening verb; we think that is the series contract working, and we
   would like to be told if it is not.

2. **The premise problem, which nothing we have tried touches.** Six authors given no shared plan at
   all still wrote the same story: children find a thing left behind by an older person and follow
   clues to it (16i). Withholding a reference plan closes the wording channel completely and does
   nothing to this (16j). It is the one channel where sharing less does not help and instruction does
   not help. **Is there a formulation of premise repulsion that does not degenerate into
   novelty-for-its-own-sake?** This is now our largest open problem and it was nobody's proposal.

3. **A plan-level representation of "the same kind of thinking".** Our deterministic attempt failed
   on negation and polysemy, which are properties of language and not of our word list, and three
   attempts to recover the property by annotation inverted or tied (14, 16e). We think it must be
   *declared* in the plan rather than inferred from it, which means a schema field we have never
   written. If you disagree, the disagreement is worth more to us than agreement.

4. **A measurement question, asked because 16m embarrassed us.** One item of our six-question
   instrument has never varied in twelve cells and the item carrying every result has now saturated.
   **What should a reader instrument for this property actually contain?** We would rather be told
   ours is the wrong shape than keep patching it, and we are no longer confident that asking readers
   to score a pair on six axes is the right instrument at all.

**One methodological note, offered because it may be the most transferable thing here.** Of the
results in Part II, five came from measurements taken to check a confound rather than to test a
hypothesis, and two of those overturned a conclusion we had already written down. The single most
productive rule we adopted was terminating a contaminated round instead of caveating it: our
stake-economics result had two blind model evaluators agreeing before we removed a label template and a
provenance leak, after which the model evaluators split and the effect vanished (16k). **The caveated version
would have been publishable.**
---

## Part III. What we ran after the second round of reviews

> Added 2026-08-11. Two reviewers returned architecture proposals against Part II. Rather
> than answer their strongest objection in prose, we ran it. This part reports eight runs,
> five of which cost no generations at all, and it corrects two Part II claims and two
> claims made in this round: our first reading of the solution-transfer tiers in 19, and
> this round's own assertion in 21 that the residual-words arm was cancelled, which is
> withdrawn there in favour of deprioritised.
>
> **Everything in the provenance banner at the head of this document applies here without
> exception.** No human and no child has read any of it.

### 19. The objection both reviewers raised, and what happened when we measured it

Both reviewers, working independently and from different directions, made the same
argument: **16l measures verbatim overlap, and the defect this programme exists to attack
is decision repetition.** One reached it through the device categories our shareable layer
still contains; the other through the plan-and-binding pair that 14 and 15 identified as
the layer readers actually respond to. Neither had to guess whether the stratified pair had
been tested for the second property. It had not.

The books already existed, so the test cost nothing.

| pair, same contract and same chain | solution transfer |
| --- | ---: |
| identical binding, built as a control | 1.000 |
| same solution chain, everything else re-dressed | 1.000 |
| the known-contaminated pair from 12 | 1.000 |
| solution chain relocated to other nodes | 0.700 |
| **the 16l stratified pair** | **0.467** |
| the most distinct real pair we hold | 0.225 |

**Four of the 16l pair's six chain props transfer at some tier.** That is materially short
of clean and well short of catastrophic, and it means the headline was never a distinctness
result. It is a convergence result, and we should have said so.

Separately, on aligned choice positions across the two books: **zero identical labels and
eleven of thirty-five choices sharing their first content word**, several of them the same
act with a different noun. "Turn Back Together" against "Turn back now". "Stay and Read"
against "Stay and read the logs." One reviewer argued these are the defect surfacing
through a guard that cannot see it; four-gram measures do not reach "Ask X" against "Ask Y".
On the evidence we now have, that reading is better supported than ours was.

**A correction to this section, made the same day.** Our first reading of these numbers was
wrong. We reported the pair as the worst we hold on operation transfer, having failed to
notice that the tiers are exclusive and the strongest wins, so a prop matching by answer
never counts as an operation match and a deliberately identical binding scores zero there.
The composite is the only rankable column. The battery in 20 caught this on its first use,
which is the argument for having built it.

### 20. A battery of known-bad artifacts, because readers are not available to us

We cannot recruit children in the relevant age bands. That is settled, and it has a
consequence the programme had not drawn: **the only validation available to any new
instrument is a deliberately constructed known-bad artifact.** Not a rated pair, not a
model's opinion, an artifact whose defect is known because we built the defect.

We constructed three by re-binding: an identical binding, a pair sharing its whole solution
chain with everything else re-dressed, and a pair with the chain relocated to other nodes.
The first is the ceiling. The second is the worked example this document's own problem
statement opens with. The third is the case an earlier round found readers noticing.

The ordering in 19 is that battery. The instrument places both maximal known-bads at 1.000,
the relocation case at 0.700, and the real pairs below. **This is the first measure in the
programme validated against anything other than another model's judgment**, and every probe
proposed by either reviewer should be calibrated this way before it is trusted.

### 21. The rule from 16l, now measured rather than asserted

16l claimed a shareable plan must contain no free text at all. A reviewer objected that the
shared kernel still carries device categories. Checking the artifact rather than our
description of it, the objection understated the problem: **the kernel we published as
containing no free text still carries 473 words of it**, more than the 422 the experiment
deleted.

So we traced every shared four-gram in the passing pair to its source. Of seven, **none
appears verbatim in the residual 473 words** and one matches only by vocabulary. The
restated rule survives contact with the artifact:

> Free text attached to the **fact vocabulary that nodes reference** drove convergence. The
> experiment did **not isolate** free text instructing the binding process as a cause at this
> volume.

The distinction matters and an earlier draft of this section blurred it. Deleting the 422 gloss
words is what moved the measurement, and no shared gram in the passing pair traces to the 473 words
that remained. Both are evidence of association. Neither shows the residual words are harmless, and
only an arm that deletes them while keeping the glosses would.

That arm was previously called cancelled here on the grounds that its outcome is predictable. That
was an overstatement of what this trace licenses, and it is withdrawn: the arm is **deprioritised**
rather than settled, because the trace makes a null outcome likely but does not establish it.

**But the control run found something we cannot yet explain, and it matters more than the
confirmation.** Under the same strict attribution, only five of the failing arm's forty
shared grams trace to the deleted glosses. The failing arm carried forty shared grams and the
passing arm carries seven, so thirty-three went away; five of those were gloss-derived, which
leaves **twenty-eight shared grams removed that were not copied from the deleted words**, still
5.6 times the number that were. (An earlier draft of this paragraph said thirty-three, having
subtracted nothing for the five that were copied.) The mechanism is therefore not copying. It
is convergent elaboration: two authors read the same gloss, wrote different sentences about
the same idea, and converged anyway.

That is worse news than plagiarism would have been, because **anything that primes two
authors identically will do this, and an enumerated category primes without being prose at
all.** It is the reviewer's category objection arriving by a route neither of us predicted.
We also note that Part II reported 62 percent of the failing arm's grams as gloss-derived;
that figure does not reproduce under the attribution above, and its method was never
documented.

### 22. The arithmetic nobody had done: when does a series run out?

Both reviewers built their book-20 arguments on a quantity neither had. We computed it.

The pilot contract admits **40,007,520,000 distinct bindings**. The number is worthless.
What matters is the scarcest axis, and the scarcest axis is the one that decides the puzzle:

| axis | vocabulary | picks | forced repeat by |
| --- | ---: | ---: | --- |
| **the cipher form, which sets the cognitive operation** | **5** | 1 | **book 6** |
| vault contents | 6 | 3 | later |
| room curiosities | 9 | 4 | later |

**A child reading this world gets a repeated puzzle device by their sixth book**, whatever
architecture produced it. In the youngest band the contract we hold enumerates exactly one
obstacle kind and one help mode, so the forced repeat arrives at **book two**, and all
variation must come from open axes where the generator's own modes operate (23).

This reframes the whole programme. Device-category vocabulary is the binding constraint on
series novelty. Not plan sharing, not prose, not topology. No architecture in either
reviewer's proposal changes it, because all three draw from the same curated vocabulary,
and the fix is not architectural: somebody has to write more kinds.

For a baseline against that: across 105 sibling pairs we hold on a single skeleton, **83
exceed the convergence budget** and 17 sit at or below the generator floor, with a median
of 9.2. Most of those books were built as experimental arms deliberately sharing contracts,
so the figure overstates production. It is nonetheless the first all-pairs number the
programme has, and only deliberately stratified pairs reach the floor.

### 23. Generation without any reusable narrative artifact

One reviewer ranked constraint-free generation first for production and the other kept it
as the yardstick every reuse design must beat. Both rankings turned on one unknown: whether
it survives past the small pilot. We ran it at two scales, with the constraint classes the
earlier attempt was never given.

**At roughly thirty nodes, six mutually isolated authors, one pass, no repair round and no
self-review prompt:**

| | result |
| --- | --- |
| structurally clean | **6 of 6** |
| repair rounds | **0** |
| the entire band-budget failure class that sank the first attempt | **0 of 6** |
| reading level at or under the band edge | **1 of 6** |

Writing the omitted constraints down eliminated every failure they described. Two
independent checkers agree on all six graphs.

**At roughly one hundred nodes, two isolated authors:**

| | first | second |
| --- | --- | --- |
| nodes, endings | 103, 20 | 101, 20 |
| structural failures | **0** | **0** |
| Flesch-Kincaid, share of nodes in band | **5.12, 84%** | **8.35, 11%** |
| one pass | **no** | **no** |
| approximate tokens, tool calls | 210k, 60 | 337k, 269 |

**Structure survives the scale jump.** That is a real answer to the question both rankings
depended on, and it favours generation without reuse.

**Nothing else came free.** Neither author managed one pass; the first built a scripted
build-validate-repair loop, and the second's initial draft produced a longest path of 43
against a ceiling of 24. Cost is dominated by that loop rather than by node count, which is
the first evidence available for pricing any of the proposed architectures and the reason
cost instrumentation should precede the comparison rather than follow it.

**And reading level split, with a cause.** Both authors were given the same explicit target
in the same prompt. The one that added readability work to its repair loop produced the
first book in this programme to pass reading level at production scale, against an earlier
101-node attempt that reached 8.1 to 8.4. The one that instrumented depth and word count
but not readability produced a book with eleven percent of its nodes in band.

The generalisation covers both scales:

> A model meets constraints it can verify by tracing its own artifact. It misses constraints
> requiring a statistic it cannot compute. Stating the constraint is not merely insufficient
> for the second class, it is a coin flip resolved by an authoring choice nobody specified.

So the repair loop belongs in the harness, not the prompt. On the evidence in this part
that is the best-supported build item the programme has.

### 24. The premise, across models and across scales

Part II reported that removing the shared plan does not vary the premise. This round tested
whether that was one model's mode, holding the task and prompt fixed and varying the model.

It is not. Two independent instances of one model, sharing no context and reading no file,
invented **the same place name** and produced titles differing by a single preposition:
*The Lantern Under Marrow Hill* against *The Lantern Beneath Marrow Hill*. Four of five
words identical. Later, at production scale, a third author independently reproduced
**word for word** the title of one of the thirty-node graphs, *The Lantern Keeper's
Apprentice*.

Pooled across every generation in this part: **ten of twelve independent generations, across
three model tiers and two scales, put a light-or-signal beacon at the centre of the story**,
most of them coastal or fog-bound, several with an elder keeper. The two exceptions were a
kite race and a forest threatened by a shopping mall.

Convergence is not lexical. Median shared four-grams across the thirty-node set was 1.56 per
1000, with eleven of fifteen pairs at or below the generator floor. Wording independence is
free when nothing is shared, exactly as Part II found. But four of fifteen pairs breach the
budget and **every breach is a same-archetype pair**, the scale pair among them at 5.18.

**A collision on an invented proper noun is as far below the plan layer as a collision can
get.** No architecture that shares less can reach it. Premise allocation from a curated
enumerated space stops being one design's feature and becomes a precondition for all of
them.

The limit on this claim must travel with it: all three tiers belong to one model family, so
this establishes that the mode is not a per-model artifact and says nothing about whether it
is training-distribution-level across vendors. That replication is the open version of the
question, and until it runs, no idiom floor or diversity margin in this document should be
quoted as general.

### 25. Where this leaves the architecture question

Three things are now properties every candidate must supply, rather than advantages any one
of them has:

1. **Premise allocation from a curated enumerated space** (24). Independent generation buys
   wording independence and nothing above it.
2. **A reading-level repair loop in the harness** (23). Not promptable, and invisible to
   every per-node advisory check.
3. **A wider device-category vocabulary** (22). The binding constraint on series novelty,
   and the one problem on this list that no architecture solves.

What genuinely separates the candidates has narrowed to review economics and cost, and
neither is measurable today, because generation cost is not recorded anywhere in our system.
The comparison should not be run until it is.

One reuse-based design cleared its own cheapest kill test: the pilot contract decomposes
into fork-to-join segments whose entry knowledge is entailed on every incoming path, with
zero type errors across twenty-five nodes carrying declared entry states. We report it as
weak evidence rather than a result, because that graph has eleven forks and only three
joins, so the property was barely exercised.

### 26. What we still cannot answer

- **Whether any of this tracks a reader.** Unchanged and unchangeable here. Every rating in
  this document is a model's.
- **Whether the premise mode is a family artifact or a distribution artifact** (24).
- **What any of it costs.** No token, cost or duration figure is recorded by our pipeline,
  so every economic claim in Part III is an observation about two runs rather than a price.
- **Whether structural success at one hundred nodes reaches one hundred and fifty**, which
  is the catalog median. We tested the scale that was in dispute, not the scale we ship.
