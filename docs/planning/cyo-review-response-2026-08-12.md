---
title: "Response to the third external review"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Record the first review returned against section 32's widened remit, verify its checkable claims against the artifact, and triage its twenty proposals into an order of work."
tags:
  - planning
  - research
  - review-response
component: Research
source: "third external review of cyo-generation-research-brief-2026-08-10.md, returned against section 32"
---

# Response to the third external review

> **Date**: 2026-08-12
> **Responds to**: the first review returned against
> [the research brief](./cyo-generation-research-brief-2026-08-10.md) section 32,
> which widened the remit past architecture and metrics
> **Status**: draft, pending owner sign-off

## 0. Summary

This is the first review to answer section 32 rather than section 18, and it is the most
actionable we have received. It accepts the invitation to stay out of the architecture layer
and spends its whole budget on the two layers section 32.2 identified as under-examined:
whether the quality instrument measures anything, and whether cheap generation-side levers
we never tried would move the result.

Three of its sharpest claims are literally true and we confirmed them by grep before
answering. The programme has run ten designs, three review rounds, a nine-model sweep and a
quantization matrix without ever varying a decoding parameter, without ever generating more
than one candidate per node, and without ever varying reasoning effort. None of those three
words appears anywhere in the 2,850-line brief.

The review's central structural claim is also correct, and it restates our own section 14
finding in a form we had not applied to the quality panel: we are ranking suppliers on an
instrument nobody has validated. Section 20 built a known-bad battery for the transfer
instrument and it was the first measure in the programme validated against something other
than a model's opinion. The quality panel never got that treatment, and its dialogue
criterion has already failed the implicit version by returning a near-constant across a
deterministic 25-fold spread.

We accept the review's proposed sequence with one qualification about evidence class
(section 3.1) and one about cost (section 3.2).

## 1. What we checked before answering

The brief's own standard is that a claim carries its evidence class. We applied that to the
review. Every row below is a check we ran against the artifact, not against our description
of it.

| Review claim | Check | Result |
| --- | --- | --- |
| Best-of-N selection appears nowhere in the programme | `grep -ni "best-of\|best of n\|rejection sampling"` over the brief | 0 hits. **Confirmed.** |
| Temperature, top-p and min-p appear nowhere | `grep -nic "temperature\|top_p\|top-p\|min-p\|nucleus"` over the brief | 0 hits. **Confirmed.** |
| Reasoning budget is untested as a variable | `grep -ni "reasoning effort"` over the brief | 0 hits. Grok-4.6's 74% thinking share is *measured* (section 30, line 2607) but effort was never *varied*. **Confirmed.** |
| "You already compute `dialogue_share`" | `grep -rn dialogue_share src/ scripts/` | True, but relocated: it exists only in `scripts/evaluate_books.py`, the offline evaluation harness. It is absent from `validator/` and from the repair loop. **Confirmed with a correction, see 3.2.** |
| Nearly every quality number is per node or per whole book | `validator/reading_level.py` exposes `score_body` (node) and `measure_book` (book); no path-level aggregate exists anywhere in `validator/` or `measurement/` | **Confirmed, and cheaper than the reviewer assumes, see 2.2.** |

## 2. Where the review is right, and where it is right in a way we had not seen

### 2.1 The quality panel has never been validated, and section 31 rests on it

We built a known-bad battery for the transfer instrument in section 20 and treated that as a
methodological win. We then stood up a seven-criterion quality panel, ran 84 verdicts through
it, and used the resulting spread to rank suppliers in section 31, without ever asking whether
the panel separates a good book from a deliberately damaged one.

The dialogue criterion is the proof that this matters. It returned sd 0.19 across every book
from every lab while the deterministic `dialogue_share` measure showed a spread from
near-zero to 5%. One of those two instruments is not measuring dialogue. We know which,
because the deterministic one is arithmetic. The review is right that the criterion should
come out of the pool immediately, and right that the rest of the panel is under the same
suspicion until a battery says otherwise.

**This is the blocking item.** Every supplier-selection conclusion in Part IV is downstream
of it, and it requires no new instrument and no new vendor spend: degrade books we already
have by targeted surgery, and check the panel notices.

### 2.2 The path is the missing unit of measurement, and the enumerator already exists

We nominate this as the strongest single line in the review, and it answers section 32.4's
invitation to say what we should have measured and did not.

A child reads one path. Almost every craft number in the brief is computed per node or per
whole book. Whole-book Flesch-Kincaid masks path-level variance exactly the way section 29
showed the mean grade masking the in-band rate: a book at 85% in-band can contain a path at
50%, and the child who walks that path is the one we failed. The same holds for dialogue,
arc, and ending payoff, where the mismatch is sharpest: ending quality is judged per book
while a child experiences exactly one ending per read.

The review calls this "nearly free" and undersells its own case. `validator/walk.py`
already exposes `walk_configurations`, which enumerates reachable configurations for the
Layer 2 state-space check. The path enumerator is built, tested and in production; it has
simply never been used as an aggregation unit for craft statistics. Re-pointing existing
per-node measures at it is a smaller change than the review assumed.

It also subsumes 16b. The path-dependent under-preparation defect is the only reader-facing
defect the programme has found that no whole-book measure can see, and it is an instance of
this class rather than a separate finding.

### 2.3 The unattacked layers are genuinely unattacked

Section 1 confirms this by grep. We had assumed the cheap serving-side levers were covered
because we had swept nine models; sweeping models is not the same as sweeping the knobs on
one model, and the review is correct that we conflated them. The reasoning-effort ablation
(3b) is the most valuable of the three, because it decides the real price of our
near-dominant supplier and costs under $10 by our own probe economics.

## 3. Where the review needs a qualification

### 3.1 Instrumenting the approval step yields a single-rater column, not human ground truth

The review ranks 1a first and calls it near-zero marginal cost. The cost estimate is right.
The evidence class is overstated.

Requirement 4 guarantees an adult reads every published book, but today that adult is the
owner, who is also the person who commissioned the book and built the pipeline. A
questionnaire attached to approval therefore produces one interested rater's opinion. It
cannot establish inter-rater reliability, it cannot be treated as independent of the
generation decision, and correlating the judge panel against it would tell us the panel
agrees with the owner rather than that the panel is valid.

That is not an argument against building it. It is the only human column that accrues
automatically, it costs nothing, it becomes a real population the moment other guardians
exist, and the schema is worth designing now for the same reason 1d's telemetry schema is.
But the review's own 1c is what buys independence, and 1c should not be deferred on the
grounds that 1a covers the same ground. It does not.

### 3.2 The dialogue gate is two pieces of work, not one, and we have priced this shape before

`dialogue_share` lives in `scripts/evaluate_books.py`, not in `validator/`. "Add it to the
repair loop" therefore means: lift the statistic into the validator, then add a node-scoped
repair prompt and wire it into the loop.

We know what that costs because we just did it for reading level: it was four separate units
of work (lift the whole-book aggregate into the validator, write the node-scoped repair
prompt, build the measure-repair-remeasure loop, wire it into the orchestrator as its own
stage). The good news is that the loop itself now exists and is generic, so the dialogue
version reuses it. The correction is to the framing: this is harness work of a familiar size,
not an afternoon, and calling it "no new spend" is true only of vendor spend.

### 3.3 The two external methods need verification before they enter the brief

Section 10 states that all reference entries are verified against a primary source. Verbalized
Sampling and quality-diversity through AI feedback are both real published lines of work and
both are well-aimed at problems we have failed to move, particularly premise convergence,
where QDAIF's archive-over-behaviour-descriptors formulation is a direct answer to section 18's
open problem 2 and our enumerated axes are ready-made descriptors. But the specific figures the
review quotes (1.6 to 2.1 times diversity gain; human agreement with AI assessment) are quoted
from the review, not verified by us. They enter as numbered references only after that check.

### 3.4 A shared arc contour must be measured against section 21, not assumed past it

The review anticipates the objection and answers it well: a scalar primes structure, not
sentences, so it clears the corrected 16l rule (share the structure, share no prose). We
accept that reasoning. We are adding one requirement: section 21's convergent-elaboration
finding was that anything priming two authors identically converges their prose, and it
surprised us once already. The arc pilot must measure prose convergence as an outcome rather
than assume the scalar is safe. That is a check to include, not a reason to skip the item.

## 4. Triage and order of work

We accept the review's cheapest-first sequence. Our only change is to pin 1b explicitly as
blocking rather than merely first, because it decides whether Part IV's supplier ranking is
reportable at all.

| Order | Item | Class | Why here |
| --- | --- | --- | --- |
| 1 (blocking) | **1b** known-bad battery for the quality panel | harness, no vendor spend | Everything in section 31 is downstream. Method already proven in section 20. |
| 2 | **2c** per-path craft statistics | harness | Enumerator exists (`walk.py`). Subsumes 16b. Changes what every later item measures, so it belongs before them. |
| 3 | **1a** approval questionnaire | product, near-zero | Accrues automatically; build early so the pool grows. Single-rater until launch (3.1). |
| 4 | **3b** + **3c** reasoning and decoding ablations | vendor spend under $20 | Decides the real price of our best supplier. |
| 5 | **2a** dialogue floor and repair | harness, familiar shape (3.2) | Largest concrete named product defect. Needs 1b to score it. |
| 6 | **1c** adult-expert read | ~$300 | The only item that buys instrument independence. |
| 7 | **4a** human premise pool | one afternoon plus curation | Attacks the largest measured channel (156 shared four-grams per 1000). |
| 8 | **2b** arc contour pilot | harness plus fills | Include the 3.4 convergence check. |
| 9 | **3a** best-of-N, **3e** QD framing | vendor spend | Both select on the instrument, so both are gated on item 1. |
| 10 | **3d** Verbalized Sampling, **4b** editor defect taxonomy, **4c** reading-level standard experiments | mixed | Real, and none is blocking. |
| deferred | **1d** consented telemetry | schema now, data at launch | Design the schema with 1a; the data cannot exist yet. |

We also accept all three items on the review's stop list: retire the panel's dialogue
criterion from the 84-verdict pool; defer any preference tuning until item 1 exists, since
tuning on an unvalidated judge distills its biases permanently; and stop buying cross-vendor
*diversity* measurements, which sections 27 and 31 (rho -0.11) already establish that money
does not buy.

## 5. Changes this forces in the brief

1. **Section 29** must record that the dialogue criterion is retired and why, so the 84-verdict
   pool is not read as seven live criteria.
2. **Section 31** must carry a validity caveat naming the panel as unvalidated, since its
   supplier ranking is the most quotable output in the document and is currently stated
   without one.
3. **Section 32.4's** invitation asked what we should have measured and did not. The answer is
   section 2.2 above, and it belongs in the brief rather than only in this response.
4. **A new subsection** should record the three untested layers (selection, decoding, reasoning
   budget) as known gaps, so the next reviewer is not the third person to find them.
5. **Section 10** gains two references once 3.3's verification is done.
