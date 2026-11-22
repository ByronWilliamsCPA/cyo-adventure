# What has actually improved story quality: a review of every stage (2026-11-22)

Requested by the owner after the plan reviewer failed its held-out gate. Six stage reviews read the raw evidence
(structure and variety, prose generation, measurement, gates and reviews, the Story Plan layer, reader experience).
Each was told to separate "improved what a child reads" from "improved detection, process or cost" and to say "not
shown" where it is not shown. This note is the synthesis. The headline claims were spot-checked against the sources
(see the last section); the stage reports themselves are working papers and are not committed.

## Bottom line

1. **No approach at any stage has been shown to improve what a child experiences.** Every quality figure in the project
   comes from a deterministic checker, an LLM judge, or an LLM agent reading. No child has read a generated book, no
   instrument has been compared with a human preference, and the family test has not run. The project says so itself:
   the 2026-11-20 architecture review (F8) found "no decision to date has used a child's read" and that the measurement
   programme "was rigorous about the wrong dependent variable".
2. **What demonstrably improved is narrower:** continuity contradictions removed from seven books (each replayed with
   the engine and string-matched, so these are real defects gone), unplayable or unsafe books kept out by the structural
   gate, and cost and yield figures. Whether a child ever noticed those contradictions is untested.
3. **The plan reviewer is not worth more spend now, and the plan layer as a whole has no evidence that it improves a
   story.** The sceptical view is right on the evidence, with one qualification below.
4. **This session's own work continued the pattern.** The Story Plan layer, its validation set, the seeded plans and the
   reviewer are all detection infrastructure, built after F8 had named that as the gap.

## Stage by stage

| Stage | What was tried | Best-supported result | Verdict on story quality |
| --- | --- | --- | --- |
| Structure and variety | Catalog depth and reskins; obligation contracts; per-request mutation; shared structure with per-book decisions; skeleton-free generation; tool-assisted skeleton authoring | Reuse of one skeleton is clearly repetitive (96 to 243 shared 4-grams per 1000, against about 1.2 across skeletons). Only a 32-node graft from a second skeleton moved structural distance | Not shown; contracts, mutation and the differentiation directive had no effect |
| Prose generation | Vendor and model choice; drafting guide; agency prompt rules; reading-level loop; length directive; chunking | The vendor quality ranking was retracted by the project's own bootstrap. Prompt rules lost to contradicting beats; the length directive was ignored by two models | Not shown; findings-driven repair removed continuity defects |
| Measurement | LLM judge panel; deterministic instruments; recognition protocol | The panel notices seeded damage but has no positive control and no human anchor; `age_fit` agrees worst (kappa 0.39) | Not an outcome measure |
| Gates and reviews | Structural validator, safety, fidelity, agency and craft detectors, second reads, residual checks | Gates keep broken books out. Agent second reads found about 160 defects in seven gate-clean books, then 20, then 9 | Defect detection only; the funnel ends in wording |
| Story Plan layer | Hand and blind plans, checks SP-0 to SP-9, LLM plan generation, LLM plan reviewer | The checker finds presupposition and contradiction defects in existing books. Plan generation passes checks only after density fixes, and the one medium shape has no passing plan | No evidence a plan improves a story; plan-to-prose stages are not built |
| Reader experience | Agency detectors and revisions, state promotion, kid UI, trail capture, personalization | Detector counts fell on the revised books; payoffs are reached by 3 to 4 percent of random readers | Never checked against a reader |

## What actually improved things

- **Read, then fix, with replayed witnesses.** Agent readers walked every state of a book, quoted the sentence and a
  route that reaches it, and the fix was a small wording change. About 160 findings in seven books, then 20, then 9.
  This is the one loop with a real before and after.
- **The structural gate and reading-level repair loop** do what they claim, with two caveats: a green gate is not a
  clean book, and reading-level compliance was partly won by joining and splitting sentences (185 of 212 outliers in
  AL-005).
- **A rule placed in the skeleton beat, not the prompt,** went with 0 merge seams in 470 passages, against prompt rules
  that lose to a beat asking for the opposite (AL-797). Confounded, but the only structural lever with a signal.
- **Cost and choice of default model.** A real, durable result: prose volume varies 1.36 times across vendors while
  the bill varies 8.8 times per call.

## What did not

- **Variety levers.** Obligation contracts, device pools, mutation, the differentiation directive, and a stronger model
  (which converged harder) all failed to move reader-visible sameness. The metric that did move (4-grams) was never
  tied to a reader, and the only perceptual read called even the best arm "the same adventure".
- **Vendor ranking, length directive, prompt nudges.** Retracted, ignored, and in one case a regression (one sentence
  cut hero-name coverage from about 27 to 42 percent down to 4.9 percent).
- **The plan reviewer** (below).

## The plan reviewer

Held-out result: recall 15/17, clean false-flag 6/10, agreement 18/22. I agree it should not get more spend, for these
reasons:

- **It duplicates the checker where the plan is visible.** 13 of the 17 defective plans were caught with no model call;
  the reviewer's own recall is 2 of 4 (interval 0.15 to 0.85).
- **Its distinct value needs prose.** Label versus outcome and gift versus truth cannot be judged from a plan and a
  prose-free graph. The two plans it passed carry prose defects the plan never recorded.
- **The labels are weak.** A defective plan carries every defect of its book, and no human has adjudicated the six
  flagged clean plans. Some may be true flags: blind extraction found real residuals in all five "clean" books.
- **Even a passing reviewer would certify plan consistency,** which has no demonstrated link to reader experience.

One qualification, so the failure is not overstated: of the six flagged clean plans, four are split verdicts (one run
passed, one rejected) and two are double rejects. Counting only double rejects the flag rate is 0.20. The excess is
mostly run instability, which a three-run majority might reduce. That is a reason the failure is not proven structural,
not a reason to pursue it: the job would still be consistency checking.

## The Story Plan layer overall

No evidence exists that a plan improves a story. The stages that turn a plan into prose (the compiler and scene fill)
are not built, so nothing has been generated from a plan. Cost so far: about 43 agent-hours of blind extraction, seven
hand-written plans, about 10,600 lines in `storyplan/`, and about 18 USD of provider spend. Its output is continuity
defects found in existing books, which a read-and-fix loop already finds. The checks that map most plausibly to
something a child meets are SP-2 and SP-3 (a fact never shown, two backstories). SP-7 only checks that a gift string
exists, SP-8 measures how the plan's author writes costs, and SP-9 is hygiene.

## Where to try next, in order

1. **Get one reader signal, now.** Put the pre-fix and post-fix editions of the same book in front of one child or adult,
   order alternated, and record the reaction. Both editions are hash-pinned and importable, which removes the
   book-and-topic confound the family-test design has. Also switch on reading-trail capture (finish rate, stops,
   rewinds) and ask whether stops cluster at nodes the readers flagged. Everything else waits on this.
2. **Calibrate the judge against the owner.** The owner already sorted 31 fills into 4 fit and 27 not. Rank-correlate
   that with panel scores. Score the stored Haiku and Sonnet drafts of one book (the owner called Haiku
   "unpublishable") and the pinned pre and post-fix editions as positive controls, at about 1 USD. Add a coherence
   criterion: the Cave of Echoes control in the W7 corpus (which a stage review says carries sentences a reader later
   flagged among ten recorded contradictions) scored joint highest of the six control books on imagery and highest on
   choice quality and engagement.
3. **Move craft rules into skeleton beats.** Dialogue (every vendor writes near-zero), choice acknowledgement and
   humour are prompt rules that lose to beats. The beat lint and rewrite were frozen under D2.
4. **Let a choice be acknowledged in later text.** The schema forces every body to be true on every path, which is why
   merges say nothing about the reader's route; payoffs are reached by 3 to 4 percent of random readers. The literature's
   strongest agency finding is explicit acknowledgement. This is an inference from structure, not a reader result.
5. **Premise allocation.** Premise convergence is vendor-independent and untouched by every other lever (10 of 12 stories
   at scale are lighthouse or lantern). A recipe exists in `evidence/sourcing-materials/`.
6. **Automate the one loop that worked.** A patch-only repair that uses the checker as the oracle, since the last nine
   fixes were one-phrase, route-safe edits. This is the plan layer's useful residue without the plan.

## Measuring the right thing

The vision's success metrics (correctness, generation yield, defect capture, safety, offline) contain no
reader-enjoyment measure, so nothing in the programme could have told it quality was not improving. Add one, and require
a human read before building further detection tooling. Treat as outcome measures none of: detector counts (they fall
when a model stops touching a field), reading-level in-band rate, four-gram overlap, any-reject recall, plan yield, or
gate-clean status.

## How far to trust this review

The stage reviews rest mostly on the project's own documents, which are self-reports, and on agents' reads of them. Spot
checks I made against the sources: the "no child has read any generated book" provenance statements and F8 are quoted as
stated; the judge rubric has no coherence criterion (`scripts/judge_books.py`, `_CRITERIA`); the Cave of Echoes
control scores 4.0, 4.0 and 4.0 on imagery, choice quality and engagement in `out/w7-run4/verdicts.json`, the highest
of the six control books on the last two; the family test and trail capture are recorded as not yet run in
`r1-live-e2e-checklist.md`; the W16 ablation directory holds the rig and no results; the reviewer's split-verdict
counts match the held-out results. I did not recompute the other figures, and I did not confirm that the W7 Cave
corpus file is the pre-fix revision (the stage report says it contains the sentences a reader later flagged).
