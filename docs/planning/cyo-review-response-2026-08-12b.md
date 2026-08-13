---
title: "Response to the fourth and fifth external reviews"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Record the second batch of reviews returned against section 32's widened remit, verify their checkable claims, and merge their priorities into the order of work already accepted."
tags:
  - planning
  - research
  - review-response
component: Research
source: "fourth and fifth external reviews of cyo-generation-research-brief-2026-08-10.md, returned against section 32"
---

# Response to the fourth and fifth external reviews

> **Date**: 2026-08-12
> **Responds to**: two reviews returned against
> [the research brief](./cyo-generation-research-brief-2026-08-10.md) section 32. The **fourth** is a
> prose critique with a 0-9 priority table. The **fifth** is a deep-research report with a 37-entry
> works-cited list, whose first cited work is our own brief.
> **Companion**: [the third review's response](./cyo-review-response-2026-08-12.md), whose order of
> work this document merges into rather than replaces
> **Status**: draft, pending owner sign-off

## 0. Summary

The fourth review's bottom line is that we have largely solved the engineering problem of generating
structurally valid branching books, and have not shown that the resulting books are enjoyable,
developmentally appropriate, or different in ways a child notices. Two thirds of that restates our
own section 32.1, which already rates requirements 1 and 2 at low confidence and says in as many
words that no human or child has read any book. The new third lands on requirement 4, the row we
mark **highest evidence we hold**, and it is correct: that row makes two claims and we can support
one of them (2.1).

The fifth review is a different kind of artifact and needs reading differently. Its works-cited entry
1 is `cyo-generation-research-brief-CURRENT.md`, and the great majority of its superscripts point
there. Every figure it quotes back at us is accurate, which is worth knowing: a careful outside
reader reproduces our numbers without distortion, with one exception noted in 5.5. But a document
that restates our measurements is a summary, not evidence, and it must not be read as independent
confirmation of anything.

What is genuinely new in the fifth review is one argument and three proposals. The argument is that
**requirement 2 may be the wrong goal**, because formula and predictability are load-bearing in
children's series fiction rather than defects in it. That is the premise attack section 32.3 asked
for, and section 4.1 takes it seriously. The three proposals are a named published method for the
premise pool we had already decided we need (4.2), cross-stage model routing (4.3), and a
prose-first generation order (4.4).

Set against that, its external evidence base has problems serious enough that most of it cannot
enter the brief as cited support (5.2, 5.3), and one of its recommended thresholds is weaker than the
one we already run (5.4).

## 1. What we checked before answering

| Claim | Review | How we checked it | Verdict |
| --- | --- | --- | --- |
| [41]'s two-to-four moderator is *successive choices*, not options per choice | 4th | read the brief's own lines 112-119 | **confirmed**, corrected in section 17 (commit `3df82254`) |
| Readability is not age appropriateness | 4th | read `validator/reading_level.py` and `validator/band_profile.py` | **confirmed**, and it lands on the cell we rate highest (2.1) |
| The supplier ranking carries no uncertainty | 4th | grepped `confidence interval\|bootstrap\|\bCI\b` across all 2,850 lines | **confirmed**: zero occurrences (2.2) |
| A reader experiences a path, not a graph | 4th | second independent review to say it; `walk.py::walk_configurations` already enumerates paths | **confirmed**, already ordered at position 2 |
| The same-brief comparison bundles treatments | 4th | read the cited figure (n=80, 156.35 shared four-grams per 1000) | **partly**: the figure is a description, not a treatment comparison (3.1) |
| Every figure the fifth review quotes back | 5th | grepped each of 3.3, 2.3, 59.2, 63.8, 156.35, 3.04, 0.19, $0.040, $1.419, 74%, 44%, 101-node | **all present and correctly stated** |
| "rotating vendors yields a mere 28 percent variance" | 5th | the brief's figure is a **ratio of 1.28** | **misstated quantity, same conclusion** (5.5) |
| The series contract is an unconsidered frame | 5th | grepped the brief: four occurrences, at lines 652, 995, 1830, 2066 | **already present as a caveat**; the escalation is what is new (4.1) |
| Premise must come from a curated enumerated space | 5th | already a brief conclusion at lines 2313, 2336, 2457 | **agreed before the review**; MoPS is the new part (4.2) |
| Tier 3 node-scoped readability repair should be built | 5th | `generation/reading_level_loop.py`, wired into the orchestrator | **already shipped on this branch** (5.6) |
| Judge validation should target Cohen's kappa > 0.80 | 5th | the brief already sets a floor of kappa 0.60, cited to Landis and Koch (1977) | **our threshold has a primary source; theirs does not** (5.4) |
| [41] three-to-five options not robust under random effects | 4th | not checked | **unverified**, no primary source read |
| The child-versus-adult moderator is model-dependent | 4th | not checked | **unverified**, no primary source read |
| MoPS, DSR, ReSET, contrastive decoding, Dramatron, NARRABENCH, ConStory-Bench, Avoidance Decoding, SWAG | 4th, 5th | not checked | **unverified** (3.4, 5.3) |

## 2. Fourth review: where it is right

### 2.1 "Age-appropriate" is two claims wearing one word, and we graded the wrong one

Section 32.1 row 4 claims "Safe **and age-appropriate**, verifiably", justified by the deterministic
validator, the moderation gate, and mandatory human approval, at **highest evidence we hold**. Split
the claim and the two halves are not close in strength.

**Safe** is earned. Content-flag ceilings and forbidden ending kinds are enforced per band, the
moderation classifiers run before any human sees a book, and no book reaches a child without a human
approving it. Three independent mechanisms, one of them a person.

**Age-appropriate** rests on two things. `reading_level.py::_flesch_kincaid_grade` computes a
Flesch-Kincaid grade from syllables per word and words per sentence, per node body. `band_profile.py`
adds per-band node and depth budgets and ending and decision floors, and its own module docstring
says: "Only bands near 9-12 are research-measured; 3-5 and 16+ ceilings and floors are
product-defined and tunable."

Flesch-Kincaid is the quantitative leg of a three-leg construct. The qualitative leg (levels of
meaning, text structure, language conventionality, knowledge demands) and the reader-and-task leg are
not observed anywhere in the pipeline. A book can sit dead centre of its band on Flesch-Kincaid and
still turn on an irony, a non-linear chronology, or a piece of background knowledge a seven-year-old
does not have. Nothing we run would notice.

That is worse than it sounds, because of where it sits. Rows 1 through 3 are labelled low or medium
confidence, so nobody is relying on them. Row 4 is the row a reader would rely on, and half of it is
carried by a syllable-counting formula. The right repair is to split the row: **safe** keeps its
rating, **age-appropriate** drops to low with an explicit note that only the quantitative dimension
is instrumented.

This is the same failure shape as AL-310, one lesson later and one layer up. There, four checkers
each correctly abstained on an unfilled body and the aggregate of four correct abstentions was a
clean verdict on an unwritten book. Here, every instrument we run is silent on three of the four
qualitative dimensions, and the aggregate silence reads as a verified property. **A gate assembled
from measures that all abstain on dimension X certifies X.** That generalisation is worth a lessons
entry in its own right, because we have now been bitten by it twice in two days at different scales.

### 2.2 The supplier ranking carries no uncertainty at all

Zero occurrences of any interval or resampling vocabulary across the whole brief. Every ranking in
Part IV is a point estimate over single-digit books per cell, presented as an order. The review asks
for confidence intervals and we accept, with one caveat about what the honest output will be: at
these n, bootstrapping a per-vendor mean will usually produce overlapping intervals, and the correct
report is then "these three are indistinguishable", not a reordered list. That is a less satisfying
table and a more truthful one.

This composes with the third review's item 1b. Retiring the panel's dialogue criterion changes the
point estimates; adding intervals changes whether the remaining differences survive at all. Do both
before quoting any ranking again.

### 2.3 The path is the unit, and two independent reviews now say so

The third review reached this from measurement design, the fourth from reader experience. Two
reviewers converging on the same reformulation from different directions is stronger evidence than
either argument alone, and it moves this from "a good idea we accepted" to "the thing our
whole-graph framing has been wrong about". It stays at position 2 in the order of work; nothing here
changes its priority, only our confidence in it.

## 3. Fourth review: where it needs a qualification

### 3.1 The ablation ladder is right; the example it attaches to is a description

We accept the five-rung ablation ladder on its merits: any result that changes brief, lab, and
context at once cannot attribute an effect to any of them, and we have run comparisons in that shape.

The specific figure the review points at is not one of them. The same-brief cross-lab number
(n = 80 pairs, 156.35 shared four-grams per 1000) is a **descriptive measurement of convergence**,
not a treatment comparison: it reports how similar two labs' outputs are when handed the same brief,
which is the finding, not a confound in it. There is nothing to unbundle. The ladder still gets
built, and it should be built against a named baseline rung, which the proposal leaves implicit.

### 3.2 The three-factor model is a rubric, not a checker

The qualitative dimensions come from a curriculum standard written for a human rater reading a whole
text. Adopting them buys us a rubric, not a gate. That matters for sequencing: the age-appropriateness
repair is a **human-rater** work item, in the same cost bucket as the adult-expert read (third review
item 1c, roughly $300), not in the harness bucket where it would otherwise be scheduled early and
cheap. We should not pretend otherwise by writing four more deterministic checkers that proxy for
dimensions no formula observes; that would recreate exactly the problem in 2.1.

### 3.3 Renaming the four-gram metric is cheap, and must not move the number

We accept the rename in principle. Section 14 already established that our vocabulary was itself a
contaminant, and "shared four-grams" invites readers to hear "similarity" when the metric measures
verbatim overlap only. One constraint: the term appears in roughly twenty numbered places, carries a
budget of 4.0 per 1000, and has a measured generator floor of 3.3. The rename is a documentation
edit and must leave every figure, the budget, and the floor bit-identical. Anything that changes a
number is a different change and needs its own justification.

### 3.4 Claims needing primary-source verification before they enter the brief

Section 10 states "All entries verified against a primary source." That standard binds these reviews'
citations exactly as it binds ours. From the fourth review: the two further claims about [41]'s
internals (three-to-five options not robust under random effects; the child-versus-adult moderator
being model-dependent), plus NARRABENCH, ConStory-Bench, Avoidance Decoding, SWAG, the
playwriting-guided story generation work, and the EMNLP children's lexical simplification study.
Carried forward from the third review and still unverified: Verbalized Sampling and QDAIF. The fifth
review's citations are handled separately in 5.3, because they fail for a different reason.

## 4. Fifth review: what is actually new in it

### 4.1 The series contract, escalated from a caveat into a governing frame

This is the review's real contribution and the only one of five reviews to attack a premise rather
than propose an architecture.

Our brief already invokes the series contract four times, and always defensively: to explain why
thirty-five choices sharing an opening verb is acceptable (line 2066), why label-layer overlap is
arguably fine (line 1830), and why sharing a world is a feature (line 995). Section 14 goes further
and concedes that our raters measured detectability of the shared armature rather than repetition of
the action semantics, and that recognising a shared armature is the intended experience of series
fiction, not a defect in it.

The review's move is to stop treating that as a caveat on individual findings and make it the frame:
if formula is load-bearing for developing readers, then **requirement 2 as written is measuring a
property whose optimum is not "maximal"**, and the whole diversity workstream has been optimising a
monotone objective for a construct that is plausibly inverted-U. It proposes replacing the construct
with emotional consistency and consequence: does the character behave consistently, does a choice
carry weight, does the reader's attachment survive across books.

We accept the reframing as a live and serious hypothesis, and we note it costs us nothing to hold,
because it is decided by the same missing evidence as everything else. No child has read a book, so
we cannot currently tell a reader who finds the repetition comforting from one who finds it stale.
The consequence for ordering is concrete: **the child-reader work (third review item 1c, position 6)
now decides two questions rather than one**, and its questionnaire must ask about familiarity and
attachment, not only about enjoyment. That is a cheap addition to an item already scheduled and it
raises that item's value materially.

What we do not accept is the implied corollary that the diversity measurements were wasted. They
established the mechanism (convergent elaboration on shared free text) and the fix (the stratified
plan, 2.3 per 1000, below the generator's own floor). Those hold whichever way the construct
question resolves, because they are statements about the generator, not about the reader.

### 4.2 MoPS gives a name and a published method to a conclusion we had already reached

The brief already concludes, at three separate places, that premise allocation must come from a
curated enumerated space rather than from the generator, and calls it "a precondition for every
candidate". The third review independently proposed a human-authored premise pool (its item 4a).

What the fifth review adds is a specific published decomposition (protagonist background, persona,
setting, inciting incident, goal, conflict, twist) sampled from a nested dictionary, with an ACL
Anthology identifier attached. If it verifies, that converts "build a premise pool" from a design
task into an implementation of a described method, which is materially cheaper and gives the pool a
principled factorisation instead of an ad-hoc one. **This is the single most actionable item in the
fifth review**, and two reviews now independently pointing at the same fix raises item 4a's priority.
Gated on 5.3 verification.

### 4.3 Cross-stage model routing is genuinely absent from the brief

We searched: the brief contains no proposal to run different stages on different models. Given
section 30's finding that cost varies 36x per delivered book and tracks reasoning tokens rather than
output length, routing the structure stage to an expensive reasoner and the prose stage to a cheap
fast model is an obvious lever we never wrote down. It is testable with the harness we already have.

Two cautions. The specific model names it recommends are stale (it proposes Claude 3.5 Sonnet as a
frontier tier), so the tiering idea transfers and its instantiation does not. And the prompt-caching
advice, static content first and dynamic content last, is sound and orthogonal; it should be checked
against what our prompt templates already do rather than adopted blind.

### 4.4 Prose-first generation is a real alternative ordering with a named risk

The Dual-Stage Refinement proposal inverts our order: draft unconstrained prose first, then slice it
onto the skeleton in a second pass. Our Stage A/Stage B split is structure-first and fill-second.

This is a genuine alternative and worth a pilot, with the risk stated up front: slicing free prose
onto a fixed topology is a harder constraint-satisfaction problem than filling a fixed topology,
because the prose was written without knowledge of the reconvergence points and condition
invariants it must respect. The proposal assumes stage two can always find the cut points. Our
experience with the repair loop suggests the interesting question is what happens when it cannot, and
that failure mode should be what a pilot measures.

## 5. Fifth review: what is not new, and what does not hold

### 5.1 Most of it is our brief read back to us

Works-cited entry 1 is our own document, and the sections on the idiom floor, convergent elaboration,
the stratified plan, cross-vendor premise convergence, the dialogue-score hallucination, and unit
economics are all sourced to it. Every figure checks out (see the table in section 1). That is
genuinely reassuring about the brief's clarity and it is not evidence about the world. The risk is
citation laundering: a claim of ours, restated in a document with 37 references, reads as
externally corroborated when it is not. Any future quotation of this review must preserve which
claims carry reference 1.

### 5.2 The parasocial evidence base is adults, video games, and romance games

The attachment argument in 4.1 is worth taking seriously. The literature offered in support of it
mostly is not, for the population it is applied to. The cited work covers adult attachment and
engagement with fictional characters, a systematic review of adolescents and adults, emotional
attachment to *game* characters, parasocial intimacy among Chinese female players of *otome*
(romance) games, and one paper on game character attachment and real-world fertility desires.

None of that is children reading branching books. Borrowing a construct measured on adults playing
romance games to make a claim about seven-year-olds is structurally the same error the fourth review
just corrected us for on Patall: a result measured on one population and one quantity, applied to
another. We should not repeat it in the other direction just because the conclusion suits us. The
hypothesis in 4.1 stands on its own reasoning and on our section 14 finding; it does not yet stand on
this bibliography.

### 5.3 Several citations do not support the claims attached to them

Applying the section 10 standard, these fail before verification even begins:

- **Contrastive decoding** is sourced to a summary of a paper on *visual* contrastive decoding for
  vision-language models. That technique addresses hallucination in multimodal models; it is not the
  text-generation contrastive decoding the review describes.
- **ReSET** and the contrastive decoding entry are both cited via `chat.powerdrill.ai` summary pages
  rather than the papers. A summary site is not a primary source.
- **Quantization degrades lexical diversity** is supported by a forum post about quantization effects
  on small language models doing *multilingual mathematical reasoning*. That is a different task,
  different models, and a different output property. See section 6, because this one matters.
- **Academic partnerships** are supported by links to a university course catalog, an engineering
  program page, and a child development center homepage. Those are directory entries, not findings.
- One entry is an audiobook listing for a book about the meanings of madness, which appears to be a
  stray with no connection to any claim in the document.
- Two arXiv identifiers are near-future relative to today and need checking rather than assuming.
- Reddit threads, a picture-book studio's marketing blog, a game studio's blog, and a Medium post
  appear in support of psychological claims.

**MoPS, Dramatron, and the decomposed-screenwriting paper are the three that look real and
checkable**, and they happen to be the three carrying the proposals in 4.2, 4.4, and the
human-in-the-loop argument. Verify those; discard the rest as support.

### 5.4 The proposed judge threshold is weaker than the one we already run

The review recommends Cohen's kappa above 0.80 as the "industry standard" for judge validation. Our
brief already sets an evaluator agreement floor at kappa 0.60, cited to Landis and Koch (1977), whose
"substantial" band begins at 0.61. Ours has a primary source attached; the proposed 0.80 does not.

0.80 is also probably the wrong number for this task. Landis and Koch put 0.81 and above in the
"almost perfect" band, which is a bar that human raters frequently miss on subjective narrative
judgments. A threshold that would deprecate human agreement is not a usable threshold for machine
agreement. We keep 0.60 and record why.

The related proposal, that judges showing Z above 1 are "super-consistent" and should be deprecated,
is offered without a definition of what the Z is computed over. We are not adopting a deprecation
rule we cannot compute.

### 5.5 The one figure it restates incorrectly

The review reports that rotating vendors "yields a mere 28 percent variance". Our figure is a
**ratio of 1.28** between the within-vendor and cross-vendor conditions. The conclusion it draws
(rotating vendors to buy lexical variety is close to a null intervention) is the conclusion we drew,
so nothing downstream changes, but "28 percent variance" is not a quantity we measured and should not
be quoted back to us as one. Noting it here so it does not propagate.

### 5.6 Its Tier 3 proposal is already shipped

The proposal that a node failing a Flesch-Kincaid check should be isolated and re-routed to a repair
pass describes `generation/reading_level_loop.py`, which is built and wired into the orchestrator on
this branch. The review cites our brief for the surrounding context, so this is a case of the
document describing delivered work as future work.

## 6. Where the three reviews converge

Convergence across reviews that did not see each other is the strongest signal in this batch:

| Point | 3rd | 4th | 5th |
| --- | --- | --- | --- |
| No human or child has read a book, and that is the binding constraint | yes | yes | yes |
| The LLM judge panel is unvalidated and everything downstream inherits that | yes | yes | yes |
| Premise must come from a curated enumerated space, not the generator | yes (4a) | yes (item 2) | yes (MoPS) |
| The path, not the graph, is the unit of evaluation | yes (2c) | yes (item 1) | implied |
| The decoding layer has never been touched | yes (3c) | yes (item 8) | yes (ReSET, contrastive) |
| Dialogue percentage is not dialogue quality, and the panel hallucinated it | yes | yes | yes |
| Best-of-N belongs at pivotal points only | yes (3a) | yes (item 7) | not raised |

Three independent reviews agreeing that the instrument is the blocker is as close to a settled
finding as this programme has produced without running an experiment.

## 7. Triage: merging both reviews into the accepted order

The third review's order of work is accepted and in progress; this table maps the new priorities onto
it rather than restarting the sequence.

| Item | Source | Disposition | Where it lands |
| --- | --- | --- | --- |
| Split section 32.1 row 4 | 4th | **accept, do now** | documentation edit, no spend, corrects our strongest published claim |
| Uncertainty on the supplier ranking | 4th | **accept, new** | alongside position 1b; both change the same table |
| Human reader and editor benchmark | 4th (0) | **accept, already scheduled, now higher value** | position 6, questionnaire widened to cover familiarity and attachment (4.1) |
| Path-level house-style contracts | 4th (1) | **accept, already scheduled** | position 2, as the contract layer above per-path statistics |
| Choice-quality compiler | 4th (3) | **accept, merge** | folds into position 2; a choice-quality measure is a per-path statistic |
| Human premise pool, now as MoPS | 4th (2), 5th | **accept, priority raised** | position 7 moves up; gated on verifying the MoPS reference (5.3) |
| Cross-stage model routing | 5th | **accept, new** | testable on the existing harness; sits with the cost work, not the quality work |
| Prose-first generation pilot | 5th | **accept, small pilot** | after position 2, and the pilot measures the failure mode, not the happy path (4.4) |
| Targeted age-adaptation pass | 4th (6) | **accept, reprice** | human-rater bucket per 3.2, so it sits with position 6, not earlier |
| Best-of-N at pivotal units | 4th (7) | **accept, gated** | position 9; selects on the instrument, so blocked on 1b |
| Branch-aware avoidance decoding, ReSET, contrastive decoding | 4th (8), 5th | **accept, gated** | position 9, and blocked on 3.4 and 5.3 verification |
| Character-causal planner, consistency checker | 4th (4, 5) | **defer** | architecture layer, which section 32.2 shows is our best-understood layer |
| Illustrated and read-aloud track | 4th (9) | **defer** | product scope, not a research question |
| Kappa > 0.80, Z > 1 deprecation | 5th | **reject** | our floor is cited and theirs is not (5.4) |
| The 2x2 pilot, 24 books, pre-registered | 4th | **accept in principle, sequence later** | the shape of the first *good* experiment, downstream of 1b |

## 8. Changes this forces in the brief

1. **Section 32.1 row 4 splits.** "Safe" keeps **highest evidence we hold**; "age-appropriate" drops
   to low, with the note that only the quantitative dimension is instrumented. (2.1)
2. **Section 17 gains the Patall bullet.** Done, commit `3df82254`.
3. **Requirement 2 gains the inverted-U hypothesis** as an explicit open question rather than an
   assumption, cross-referenced to the four existing series-contract passages. (4.1)
4. **Part IV rankings gain an uncertainty statement**, and no ranking is quoted again until they do.
   (2.2)
5. **The four-gram metric is renamed**, with every figure held constant. (3.3)
6. **Section 10 gains a pending-verification list** covering both reviews' citations, so they are
   visible as not-yet-references rather than absent. (3.4, 5.3)
7. **The evaluator agreement floor gains a note** recording why 0.60 was kept over a proposed 0.80.
   (5.4)

## 9. Where we are not following the recommendation

The fourth review recommends pausing broad generator sweeps until the measurement layer exists. We
accept this for **diversity** sweeps; they were already on the stop list, and sections 27 and 31
established that spend does not buy diversity (rho -0.11).

We are continuing the in-flight **cost and serving-reliability** probe, and the reasoning is section
32.2's own table. The findings that cost us most to not know were not quality findings: cost tracks
reasoning tokens rather than output length and varies 36x per delivered book; a pinned endpoint
returned `finish_reason=error` on every call while the same model unpinned worked; a provider
reported `reasoning_tokens=0` while emitting 5,339 characters of reasoning. None of those is
downstream of the quality instrument, none would have been found by building the instrument first,
and every one of them was found by running a sweep.

The fifth review sharpens this rather than contradicting it. It asserts as established that
quantization degrades lexical diversity and that procurement should mandate precision floors, and it
supports that with a forum post about small models doing multilingual mathematics. **That claim, on
that evidence, is exactly what the in-flight run measures directly on our own task.** A review
telling us to stop measuring something while asserting its conclusion from an unrelated task is the
strongest argument available for finishing the measurement.

The distinction we are drawing, and the one we would defend: **pause the sweeps whose output is a
ranking; keep the sweeps whose output is a fact about the supplier.**
