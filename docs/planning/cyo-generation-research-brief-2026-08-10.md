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

That last result is independent corroboration of our own most expensive finding (5.4).
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
identity**: node 3 is not an abstract vertex, it is *the note-decoding scene*. An edge to
"node 3" carries no information a reader can perceive; an edge to "the scene where you
decode the note" is the entire fingerprint. Our skeletons bind both, and we had been
attributing to the first what belongs to the second.

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

**Scene identity and action semantics were held constant in all ten designs.** They were
constant by construction from S2 onward, because a human-authored skeleton names each scene
at authoring time and every later mechanism was built to vary things *around* that.

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
