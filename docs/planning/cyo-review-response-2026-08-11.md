---
title: "Response to the second external review"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Answer the reviewer's clarifying questions 1-8 from measurement, and record the two defects their questions exposed in our own brief."
tags:
  - planning
  - research
  - review-response
component: Research
source: "second external review of cyo-generation-research-brief-2026-08-10.md"
---

# Response to the second external review

> **Date**: 2026-08-11
> **Responds to**: the executive assessment returned against
> [the research brief](./cyo-generation-research-brief-2026-08-10.md), Part II
> **Status**: draft, pending owner sign-off before it goes back to the reviewer

## 0. Summary

The review is correct on its central technical objection, and correct in a way we had not
seen. Checking it against the artifact rather than against our own description of the
artifact turned up two defects in the brief, one of them a false statement:

1. **The "prose-free" kernel is not prose-free.** It still shares 473 words of free text.
   We deleted 422 and left more than we removed. The measured result is unaffected; the rule
   we stated to explain it is wrong.
2. **The brief calls model raters "human".** Section 14 says "blind human annotation".
   No human and no child has read any book in this programme for rating purposes.

Both are corrected in section 3. We are reporting them rather than quietly restating the
numbers, on the same principle that governed the metric-scope correction in 16l.

Answers to questions 1 to 8 are in section 2. Question 9 is answered by the owner: we
cannot recruit readers in the relevant age bands, so every reader-facing claim in this
programme stays a hypothesis about readers, and section 4 says what we will do instead.

## 1. Evaluation of the review

### 1.1 Where it is right, and what it costs us

**The device-category objection (review section 2) is correct and understated.** The review
argues that the shared kernel still contains device categories, that a category can carry no
prose and still push two books toward the same kind of puzzle, and that our safe rule was
therefore stated too loosely. That is right. It is also worse than the review could see from
the document.

Measuring the actual shared artifact:

| Shared artifact | Free-text words |
| --- | ---: |
| stratified kernel with fact glosses (the failing arm, 13.6 per 1000) | 895 |
| "prose-free" kernel (the passing arm, 2.3 per 1000) | **473** |
| deleted between them | 422 |

The 473 words that remain are the `world_recipe` binding notes, the per-node `invention`
notes, eight `title_contract.must_not` clauses, and the affect ceiling. Example, present
identically in both books' shared half:

> one cipher form per story, chosen at bind and used consistently from note to clockface to
> back panel

That is free text, visible to both authoring models, in the artifact we published as
carrying none.

**The empirical result survives; the explanation does not.** Convergence still fell from 13.6
to 2.3 when we deleted those 422 words, holding everything else constant, and 2.3 is still
below the 3.3 generator floor. What we cannot claim is the mechanism. "No free text at all"
is not what the passing artifact implements, so it cannot be what made it pass.

The honest restatement is narrower and more useful:

> Free text attached to the **fact vocabulary that nodes reference** drove convergence.
> Free text that **instructs the binding process** did not, at this volume.

The fact glosses were pulled into local context at every node that established or assumed
that fact; the binding notes appear once, in a global preamble. Whether the operative
variable is *what the text describes* (story content against process instruction) or *how
often it is re-read* (per-node against global) is now an open question, and it is directly
testable by a third arm that deletes the 473 and keeps the 422. We had not seen the question
because we believed our own summary of the artifact.

The review's proposed rule is better than ours and we adopt it, with one addition:

> The shared kernel may contain identifiers, topology, formal relations, invariants, and
> genuinely non-semantic categories. Anything determining what the reader does, thinks about,
> or uses to solve a problem belongs in the per-book layer, **and any free text in the shared
> half must be justified individually rather than by category.**

**The category channel is real and currently unguarded.** Both books draw their cipher form
from one shared five-element list. With one form per story, two books collide by chance about
one time in five, and nothing in the design prevents it. The four-gram guard cannot see this,
by construction.

**The three-outcome separation (review 6.1) is right and we adopt it.** We have been asking
one number to carry verbatim convergence, procedural reuse, and reader experience. It was
validated for the first only. The reframing of the construct as procedural redundancy, "how
much does the earlier book let the child skip the work the later one asks for", is better than
our "same decisions" wording and explains our own 14 result rather than restating it.

**Premise repulsion as a shared service** matches our 16j finding independently: withholding
the reference beat instructing divergence, 126.7 to 1.0. We agree it is a mandatory service
rather than a property of any one architecture.

### 1.2 Where it is wrong or works from stale numbers

**It read the pre-correction figures.** The review quotes 12.9 to 3.2. Those were published at
a mixed metric scope, corrected in review before this response: body-only throughout, the
figures are **13.6 to 2.3**. The direction and the conclusion are unchanged, and the reduction
is slightly larger than the review credits.

**"Only 2 of 61 skeletons have contract structure" conflates two artifacts.** Measured:

| Artifact | Count | Contents |
| --- | ---: | --- |
| base skeletons | 61 | topology, 11,458 nodes, `variables` on 60 |
| `*.contract.json` (**binding** contracts) | **47** | slots, legacy lexicon, default binding |
| `*.narrative.json` (**narrative** contracts) | **2** | tier, function, entry_state, establishes, forbids, affect, choice_semantics |

The 2-of-61 bottleneck is real and it is the right thing to worry about, but the remaining 59
are not bare topology. They carry a binding-slot layer in 47 cases, and sparse formal
structure everywhere: 331 of 13,425 choices have `effects`, 182 have `condition`, 61 of 11,458
nodes have `on_enter`. So a migration starts from more than the review assumes, and from far
less than the word "contract" in our own filenames implies. Our filenames caused this
confusion and should be disambiguated.

**Review 6.3's behavioral telemetry is not available, by design.** This is the one
recommendation we must decline on grounds the review could not have known. Time-to-choice,
hesitation, retry latency and abandonment timing are precisely what our privacy posture
forbids collecting. `reading_activity_day` is day-grain by deliberate design, with the
governing comment "no session rows and no timestamp finer than a day ever reaches the server"
(capability K23, extending S10, ADR-018). This is an owner-ratified child-privacy commitment
carrying a 12-month retention default, not an unbuilt feature.

What *is* available or already designed is coarser and still useful: node arrivals, stop
rate per node, choice take rates, unreached endings, depth before stopping, and re-read rate,
all de-identified with a minimum-population floor. That design exists and is unbuilt
(`reader-path-engagement-design.md`), and its own section 10 recommends against
choice-by-choice replay to a guardian.

So the behavioral instrument the review wants is available in aggregate and forbidden per
child. We think that is the right trade and we are not proposing to revisit it.

**Architecture B's central justification weakens** now that the owner has answered question 5
(below): if we launch all-new rather than retrofitting, bypassing a 59-skeleton conversion is
no longer the prize it was.

### 1.3 The document-control points

Both are fair.

- Part I still solicits candidate architectures for a question Part II partly answers. We
  agree with splitting this into an archived brief plus a current decision memo, and will do
  it rather than continue appending.
- The August 11 extension line against an August 10 filename is accurate but reads as an
  error. The file is named for its creation date. We will make that explicit.

## 2. Answers to questions 1 to 8

### Q1. Who were the raters and annotators?

**All of them were LLM agent instances. No human has rated any book in this programme, and no
child has read one.** Stated per experiment:

| Experiment | Rater / annotator | Count |
| --- | --- | --- |
| Part I section 13, six-question ratings | model agents, blind to condition | 2 per pair |
| D-5 negative control (contaminated arm) | model agents, opposite presentation orders | 2, then 2 fresh on replication |
| Section 14 decision-overlap annotation | model agents, blind, neutrally-named plans | 3 independent |
| 16l bare-names authoring (books C and D) | model agents, mutually isolated | 2 authors |
| Every "blind reader of the finished books" verdict | model agents | 2 per pair |

The Fleiss kappa figures (0.96 action family, 1.00 consequence) are **inter-model** agreement,
not inter-human agreement. Authors and raters shared a model family throughout, which engages
the self-preference effect the brief flags in Part I and has never controlled for.

The brief states this correctly in its Part I methods appendix ("a rater agent, blind to what
is being tested") and then **incorrectly in section 14, which says "blind human annotation".
That is false and we are correcting it.** Everywhere else the words "rater", "annotator" and
"reader" are used without qualification, which is ambiguous in exactly the way the review
suspected.

The consequence the review draws is the right one and we accept it without reservation:
**every verdict in this programme is a hypothesis about reader response, not reader evidence.**
The deterministic measurements (four-gram convergence, graph structure, reading level) are
unaffected, because no rater touches them.

### Q2. What does adult approval mean operationally?

**The full text is presented; reading it is neither required nor verified.**

The guardian review page renders flagged passages first, then a complete read-through of every
reachable node in order, then unreachable nodes, with a coverage line ("N passages, M reachable
from the start, K endings"). Approval is a single state transition
(`POST /storybooks/{id}/approve`). There is no attestation, no per-passage acknowledgement, no
reading-progress requirement, and no sampling protocol.

ADR-005 claims option 1 gives "a hard guarantee that a parent saw every story" and estimates
"a few minutes" of review. **Those two statements are in tension with the artifact sizes**, and
the review is right that this dominates the economics. Measured across the 61 shipped
skeletons, using ADR-011's band means:

| Band | Skeletons | Median whole-graph words | Largest | Words on one child's path |
| --- | ---: | ---: | ---: | ---: |
| 3-5 | 7 | 800 | 1,280 | 280 |
| 5-8 | 6 | 3,325 | 4,340 | 630 |
| 8-11 | 9 | 12,100 | 19,100 | 1,200 |
| 10-13 | 11 | 14,900 | 25,000 | 1,400 |
| 13-16 | 14 | 37,100 | 77,140 | 2,100 |
| 16+ | 14 | 42,700 | **118,475** | 2,800 |

The review's "40,000 to 118,000 words" is exactly right for the top two bands; the maximum is
118,475.

**The median column does not reproduce from the brief's band table; the maxima column does.**
Multiplying the brief's section 2 node counts by its per-band words-per-node reproduces `Largest`
exactly in all six bands (32x40, 62x70, 191x100, 250x100, 551x140, 677x175 give 1,280 / 4,340 /
19,100 / 25,000 / 77,140 / 118,475). The identical method reproduces the median for 3-5 (20x40),
8-11 (121x100) and 10-13 (149x100), and misses it in the other three: 5-8 gives 3,990 against the
3,325 above (665 low, -16.7%), 13-16 gives 38,780 against 37,100 (1,680 low, -4.3%), and 16+ gives
43,400 against 42,700 (700 low, -1.6%). A method that reproduces six of six maxima and three of six
medians in the same table is an internal inconsistency, not rounding, and we cannot say from here
which column is wrong: the per-graph word counts a median would be taken over are emitted nowhere in
the repo. We publish both columns unchanged and flag the gap rather than reconcile it by guess.
Settling it requires emitting per-graph word counts and taking the median of those directly, instead
of multiplying a median node count by a band constant.

The asymmetry is the point: at 16+ the **median** book is roughly **15 times** what any single
reading exposes (42,700 against 2,800), and the **largest** is roughly **42 times** (118,475 against
2,800). The argument holds at either end. "A few minutes" is achievable only by reviewing flagged
passages plus a sample, which is what the UI actually optimizes for and what the ADR does not
say. We regard this as an unresolved gap between a stated safety guarantee and the implemented
surface, and it is now the strongest argument in the review for amortized formal verification.

### Q3. What does path telemetry currently capture?

Against the code, not the roadmap. Persisted today:

| Item | Status |
| --- | --- |
| book version | **yes**, `ReadingState.version`, composite FK to the published version |
| scenes displayed | **partly**: `path` is an ordered node list for the *current* read-through only |
| alternatives displayed | **no** |
| selected edge | **no**: `choice_path` exists in the request schema but the shipped client never sends it, so the server replay is dormant |
| timestamps | **no**, at choice grain. Row-level `updated_at` / `last_synced_at` only |
| retries / backtracking | **no** history; `save_slots` and `state_revision` are live state, overwritten |
| completion | **yes**, `Completion` is append-only per ending with `found_at` |
| reading time | day-grain seconds only (`reading_activity_day`), never finer |

Two facts matter more than the table.

**The route data already arrives and is deliberately discarded.** The offline client sends the
full accumulated `path` on every save and the server overwrites it. There is one mutable row
per (child, storybook), so nothing survives a re-read. Retaining it needs no client change and
no contract change; it needs the tables, the rollup, the purge job and the deletion-drill
extension, all designed and none built.

**The dormant replay is a live data-integrity caveat.** Because `choice_path` is never sent,
every route we would retain today is unverified reader-reported data. That is acceptable for
finding book defects and is explicitly not acceptable as an input to catalog automation.

So the review's proposed ledger is buildable in its structural half (which scenes, which
endings, how far, how often) and blocked in its behavioral half (timing, hesitation, retry
latency) by the privacy posture in 1.2.

### Q4. What is the target repetition window?

**Owner ruling: there is no window. Treat it as all-pairs.**

We do not know, and will not know, which two books a child reads back to back. A reader may by
chance pick any two books in their library consecutively. The consequence is stronger than the
review assumed when it proposed time decay: **novelty must hold pairwise across the entire set
a child holds, not against a recent-history window.** A ledger with time decay would be
measuring the wrong thing.

Two things follow. Comparison cost is quadratic in library size rather than linear in a
window, which makes cheap deterministic screens more valuable than expensive per-pair judging.
And the "book 20" failure mode is not a distant horizon: it is reachable on the second book
if the two collide.

The one budget that is set bounds the rate of accumulation: the platform default is **10
story requests per family per month** (`default_monthly_story_quota`, per family and not per
child, overridable per family, with a separate per-child auto-approval envelope). A single
child in a one-child family could therefore reach 20 books in about two months.

### Q5. Must the architecture retrofit all 61 skeletons?

**Owner ruling: no. The team may launch all new.**

This materially reranks the four candidate architectures. Converting 59 legacy skeletons is
not a requirement, so Architecture B's principal justification, avoiding that conversion, is
no longer load-bearing. The choice should be made on which architecture produces the best new
books per unit of cost and review, not on migration cost.

The 2-of-61 figure remains relevant for a different reason: it bounds what we can *experiment*
on today. Both narrative contracts we hold are the only substrate for any near-term test, and
one of them is the 26-node outlier that carries most of Part II's decisive results.

### Q6. What per-book budget and latency are acceptable?

**Owner ruling: no budget is currently set. Finding the quality-cost balance is itself the
work, because it will drive subscriber pricing.**

We must also report that **we cannot currently answer this from data.** `GenerationJob`
records status, model, provider, prompt version, report and authoring metadata; it records no
token counts, no cost, and no wall-clock duration. The only budget in the system is denominated
in requests per family per month, not dollars. So there is no cost telemetry to reason from,
and any figure we offered today would be an estimate presented as a measurement.

This is a gap we should close before the architecture bake-off rather than after, since the
review's four candidates differ mostly in where they spend: Architecture C amortizes formal
verification across books, D pays per book and repairs, B pays once for a compiler. Choosing
between them on cost without cost instrumentation would repeat the mistake the brief's own
16o section warns about. Adding token, cost and duration columns to the generation job record
is small and unblocks the comparison.

### Q7. Are the 59 non-contracted skeletons structured beyond topology?

**Yes, but thinly, and less than our filenames suggest.** Measured across all 61 (11,458 nodes,
13,425 choices):

| Field | Coverage |
| --- | --- |
| `variables` (top level) | 60 / 61 skeletons |
| node `body` | 11,458 / 11,458 (fill directives, prose-style scene direction) |
| node `is_ending` | 11,458 / 11,458 |
| node `ending` (kind, valence) | 2,865 nodes |
| node `safety_scope` | 560 nodes |
| node `on_enter` | **61 nodes (0.5%)** |
| choice `effects` | **331 / 13,425 (2.5%)** |
| choice `condition` | **182 / 13,425 (1.4%)** |
| choice `label`, `target` | 13,425 / 13,425 |

So: conditions and effects exist as a mechanism and are almost unused. There are no merge
facts, no choice semantics, no cognitive-operation declarations, and no per-node obligations
outside the two narrative contracts. Scene content is carried as prose-style directives in
`body`, which is exactly the free-text form section 16l now warns against reusing.

Separately, 47 skeletons carry a `*.contract.json`, which is a **binding** contract (slots,
lexicon, default binding) and not the narrative contract the architectures depend on. Our
naming invites the confusion the review fell into and we will rename.

### Q8. Are the world / cast / topology exclusions permanent?

**Owner ruling: they should not be considered permanent.**

They are therefore hypotheses the reader study may overturn, not product axioms. The brief
already records them as an owner ruling rather than a finding (16o assumption 3), and records
that the related loop-back ruling was made **against both raters' stated view**. That is now
the right posture for all of them.

The practical consequence is a change to the instrument: world, cast and graph-shape similarity
should be **measured and reported** rather than excluded by fiat, so that if readers do respond
to them we will see it rather than having defined it away. Our current six-question instrument
cannot, because the exclusion is written into the prompt.

## 3. Corrections required to the brief

Three, all consequences of this review:

1. **Section 14: "blind human annotation" is false.** Replace with model-rater provenance and
   add a single provenance statement covering every rated result in Parts I and II.
2. **Section 16l: the "no free text at all" rule is not what the artifact implements.** Report
   the 473 residual words, restate the rule as in 1.1, and record the mechanism as open.
3. **Naming and document control**: disambiguate binding contracts from narrative contracts;
   make the August 10 / August 11 relationship explicit; split the archived brief from a
   current decision memo.

Item 1 is a published factual error in a document under external circulation and should be
fixed first.

## 4. What we propose next, given no reader recruitment

Question 9 is answered: we cannot recruit children in the relevant age bands. Every
reader-facing claim therefore stays a hypothesis, and we should stop generating more of them.
That argues for reordering the review's experiment sequence toward what can be settled
deterministically:

1. **The third arm of 16l** (delete the 473 residual words, keep the 422 fact glosses). Cheap,
   deterministic, and it settles whether the operative variable is what the text describes or
   how often it is re-read. This is now the highest-value single experiment we can run.
2. **A category-collision guard.** Deterministic, gates on shared device category and shared
   bound device across a child's whole library, and closes the channel the four-gram guard
   cannot see. All-pairs per question 4.
3. **Cost instrumentation** on the generation job, per question 6, before any architecture
   comparison claims a cost advantage.
4. **The premise portfolio selector**, which needs no reader to evaluate on its own terms:
   premise-engine coverage is countable.

Held back until there is a reader: anything whose outcome measure is "feels different to a
child". We will say so rather than substitute a model rater and call it a finding, which is
the error this review caught us making.
