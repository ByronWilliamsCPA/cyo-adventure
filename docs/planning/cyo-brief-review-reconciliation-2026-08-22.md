# Reconciliation: two independent reviews of the 2026-08-22 brief, against the live round

Reconciliation of 2026-08-22. Three sources, produced independently and in parallel, that now
disagree in places and supersede each other in others.

> ## Supersession notice, 2026-08-30
>
> **A fourth source now postdates all three below.** Read
> [the gap analysis's supersession notice](./cyo-brief-gap-analysis-2026-08-22.md#supersession-notice-2026-08-30)
> first. The material corrections to this document: the "live structural round" it treats as the
> newest evidence has itself been overtaken by the ADR-005 amendments of 2026-08-25 and 2026-08-28
> (#764, #769, #776, #778) and by #784's [unit-cost-model.md](./unit-cost-model.md); the parallel
> `R-1`..`R-14` review it reconciles against is now scheduled on `main` by
> [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md),
> so the two tracks are one programme rather than competing accounts; the live round produced
> **eight** owner rulings, not nine (see section 8 below); and **V7's standing correction is void and
> now points backwards**, because `3ad864a3` (#747, 2026-08-24) made `deepseek/deepseek-v4-pro` the
> production fill model, which is the exact model V7 said the figures were wrongly derived from.

| Source | Method | Branch |
| --- | --- | --- |
| **This review** | 12 reviewers, then 12 adversarial validators told to refute before confirming | `claude/cyo-brief-analysis-jys942` |
| **Parallel review** (`R-1`..`R-14`) | 13 agents in three groups, no second-pass validation | `claude/stoic-maxwell-60szsf`; now scheduled on `main` by [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md) |
| **Live structural round** | Real spend, real fills, three owner rulings | `claude/cyo-live-story-generation-kxm0ya` (PR #737) |

**Read this first.** The live round is empirical and postdates both reviews. Where it speaks, it
wins. Several findings both reviews rated critical are now answered, and one is answered in the
opposite direction from what either predicted.

---

## 1. What the live round settles, superseding both reviews

### 1.1 The differentiation directive is refuted as a variety lever

Both reviews flagged the directive as the only shipped defence against sibling convergence and
noted its effect had never been measured. It has now been measured, and it makes convergence
**worse**.

| Condition | Shared 4-grams | Per 1000 mean leaf words |
| --- | ---: | ---: |
| Raw undirected pair | 1,350 | 96.3 |
| **Best-case directed pair** | 1,565 | **110.7** |
| Budget | | 4.0 |

The strongest spec `build_differentiation_directive` can emit moved the number the wrong way by 15%
normalized, on near-identical delivered volume. Committed hand-authored same-skeleton twins score
**202.0**. The round's conclusion is decision-grade: **shared-structure convergence is intrinsic,
and a prompt block does not counter it.** Cross-family reuse needs a structural lever (per-family
mutation, or a reuse cap), not a directive.

**Consequences.** The parallel review's `R-2` fix ("run the blocked directive-delta measurement")
is done, and its premise is dead. This review's F5 concerns are strengthened from an
argument-about-instruments into a measured result. `check_sibling_fills` still belongs in the
pipeline as the **detector**, which is the one part of both reviews' recommendations that survives
intact.

### 1.2 The fill-rate hole is substantially vendor-shaped, and the 0.6 floor does bite

Both reviews treated under-delivery as a pipeline defect. The live round re-ran the two worst
mid-band pairs on the production-family model:

| Pair (identical skeleton and brief) | v4-pro fill | sonnet-5 fill | v4-pro in-band | sonnet-5 in-band |
| --- | ---: | ---: | ---: | ---: |
| the-half-hour-call (8-11) | 58.9% FAIL | **66.7%** pass | 67% | **90%** |
| the-iron-spire-trial (13-16 gb) | 56.7% FAIL | **80.4%** pass | 43% | **61%** |

**This corrects this review directly.** Validators V6 and V7 found that 0 of 43 *committed* pairs
fail at 0.6 and concluded that wiring the floor "blocks zero books". That was true of the archived
corpus and is false of current output: four v4-pro fills of one pair span **42.9% to 65.2%**, so the
floor is a per-book coin flip at that vendor's variance. Wiring it is enforcement, not
instrumentation. The recommendation stands; the stated rationale was wrong.

It also sharpens the fill-model question into the priced trade the parallel review's `R-1` asked
for: sonnet-5 clears the floor and the band where v4-pro fails both, at roughly **7x unit cost**
($2.43 for one 13-16 gamebook at bedrock prices).

---

## 2. Where both reviews independently agree

Reached twice by separate teams, several verified by hand here. Treat as high confidence.

| Finding | This review | Parallel |
| --- | --- | --- |
| The fill-model claim inverts the programme's own evidence | B1-2 | **R-1** (better detail: V4 Pro at -0.13, fifth of eight; the real trade is 4.9x cheaper for 0.74 z) |
| Brief's scale numbers are wrong: 677-node book commissions **42,233** words, catalog max **49,953** | verified | **R-7** (recomputed identically) |
| Promotion CI invokes the checker without `--strict` | verified | **R-9** |
| S-1's per-model rankings are unsupported; only tool-vs-blind and v4-pro 0/6 separate | B3-7, V5 | **R-8** |
| The human gate is the least measured stage; reviewer minutes are the binding constraint | A1/A2/A3, C4 | **R-11** (four fresh-eyes agents, same conclusion) |
| "Refuted" overstates instruments that never discriminate; downgrade to "not detected" | C3, V2 | **R-12** |
| Delivery floors are not in the shipping path | B2-4, C5-3 | **R-3** |
| Model drift, pinning and provenance are unhandled in production | C2-10, C2-11 | **R-10** (stronger: 18 endpoints on the slug, 16k to 1M ceilings) |

---

## 3. What the parallel review found that this one missed

Net-new and worth adopting.

1. **The mechanism behind the fill-rate hole** (`R-3`). Verified here: `fidelity.py:30` sets
   `_WORD_COUNT_TOLERANCE = 0.4` with the comment "not calibrated against real fill runs yet", and
   the persisted per-book metric counts filled **nodes**, not words, so it reads 1.0 on a book that
   delivered 38.9% of its commission. This review had the symptom; the parallel review has the
   cause.
2. **The directive renders its weakest level for the load-bearing case** (`R-2`): cross-family
   same-skeleton siblings always get the "write it straight" TREE paragraph, because escalation is
   per-family and theme-gated. (Now moot as a lever per section 1.1, but it explains the result.)
3. **The fidelity judge defaults to the model that wrote the fill**, reviewing itself.
4. **Safety corpus has zero items for the 13-16 and 16+ bands**, and the prompt-injection class is
   caught at 0.0, unfixed and unscheduled (`R-6`).
5. **F3's "14 of 21" is an arithmetic slip**; the brief's own table sums to 12 (`R-7`).
6. **ADR-023 personalization and ADR-028 persistent characters** operate on the same prose layer and
   appear nowhere in the brief, register, or test plan (`R-14`). Persistent per-child casts push
   toward sameness exactly where S-4 measures distinctness. This fills the "nobody looked at the
   product" gap this review flagged but did not close.
7. **Provider ToS and output-licensing risk** for DeepSeek and Moonshot outputs in a commercial
   children's product is unassessed, and the recommended assignment concentrates fill and first-pass
   review in one vendor against ADR-010's independence rationale (`R-14`).
8. **Procedural or grammar-based graph sampling as the skeleton factory** (fresh-eyes item 10):
   correctness-by-construction plus checker-validated sampling as the challenger to LLM authoring.
   Nobody on this review's team named it, and nothing in the record rules it in or out.
9. **Workflow holes** (`R-9`): the anti-clone floor is not in `--strict` at all, deletion-only
   skeleton PRs skip re-proving, and the no-auto-merge guard is label-gated with nothing applying
   the label.

---

## 4. Corrections this review's validation round applies to the parallel review

The parallel review ran no adversarial second pass, so it inherits three errors this review also
made in round 1 and retracted in round 2. Flagged for its author.

### 4.1 `check_sibling_fills.py` and the fill-rate floor are not "imported nowhere"

`R-2` and `R-3` state that these are invoked by no production module. Both are in fact registered
`gating=True` in `scripts/run_guard_battery.py` (lines 130 and 166) with tests. **The defect is one
level up: the battery itself is invoked by nothing but its own test.** `AL-305` already states the
registry rule and names this file. The fix is a runner, not wiring each script separately.

### 4.2 "All four raters called the pair the same adventure" overstates the rater data

`R-4` reads the S-0 verdicts as four raters on one configuration. "All four" spans **both** pairs;
it is two per pair. More importantly, `results.md` line 7 describes them as "independent, blind
subagent sessions of the serving frontier model (`claude-fable-5`)", so they are **one model in
counterbalanced sessions, not independent raters**, and on the control pair the two sessions did not
even rate the same stimulus (95 versus 26 `per_scene` entries). The adverse reading of F5 survives,
but it rests on ordinal separation, not on four agreeing raters.

### 4.3 The catalog-conformity result is confounded with graph size

`R-8` reports that passing Anthropic shells sit nearest the catalog (one pass 0.0007 above the
anti-clone floor; 8 of 26 below the hand-authored 5th percentile) and reads it as the experiment
partly measuring resemblance to the incumbent author. This review's validator replicated the
statistic exactly (Spearman -0.9820, exact p=0.00159, leave-one-out stable) and then broke the
interpretation: at leg level, **catalog distance is rank-identical to mean node count
(rho = -1.0000)**, because cell D's catalog runs 91-105 nodes while `--allow-mvp` caps shells at 45.
Splitting `structural_distance` into gate-policed and gate-free features puts the whole association
inside what the validator constrains (rho -0.982 versus -0.673, p=0.108). **Zero of 190 shell-catalog
pairs breach TAU_CELL.** It is the same constraint measured twice.

What the same data does show, and neither review reported: **7 of 342 shell-shell pairs breach
TAU_CELL, all cross-vendor** (Opus and Kimi at 0.0191), with three labs independently emitting 45
nodes, 91 choices, branching exactly 3.000. Models converge on **each other**, not on the catalog.

---

## 5. Corrections the parallel review and the live round apply to this review

Recorded symmetrically.

- **The 0.6 floor blocks zero books** (validators V6, V7). True of the committed corpus, false of
  current v4-pro output. See section 1.2.
- **The fill-rate mechanism.** This review attributed under-delivery to prompt licensing (refuted by
  V7) and left the cause open. `R-3` has it: an uncalibrated per-node tolerance plus a node-counting
  metric.
- **Scope.** This review never opened the frontend, personalization, or persistent characters and
  said so; `R-14` shows at least one of those omissions is load-bearing for S-4.

---

## 6. The reframe neither review had: CG-2 may be generating the defect

Commit `cc3d5f7` on main ("cover all 18 offered cells at the strict bar") explains the `--strict`
picture both reviews puzzled over. **The team deliberately built strict cover of one to two shells
per cell**; the remaining ~54 are legacy. That reconciles exactly with this review's measurement
that enforcing `--strict` collapses selection from 74 shells to 20, one per cell in 16 of 18: it
would delete the legacy catalog and leave the deliberately-built cover.

Its commit message also carries the sharpest line in the subject matter:

> CG-2 caps a decision node at three options at 5-8, so a seven-lane market square and a four-quest
> hub become chains of three-way stops, which also breaks the single-choice runs CG-1 was...

That is very likely the origin of `the-observatory-shift`'s 102 phantom three-way fans, which this
review's round 1 mistook for authoring sloppiness and round 2 downgraded to a 1.71% catalog-wide
outlier. **The rule may be generating the structure it then penalises.** The same commit states
outright that "passing `--strict` is not the bar", with four reader-visible defects found by walking
concrete paths that no deterministic layer measures.

This raises `W8` (CG-1/2/3 recalibration against the JHM anchor) from a cleanup to the highest-value
structural item on either review's list.

---

## 7. Merged priority list

Superseding section 8 of the [gap analysis](./cyo-brief-gap-analysis-2026-08-22.md) and section 7
of the parallel review.

**Answered, close them out.**

1. The directive-delta measurement (`UW-C315`) is run. Record that the directive is refuted as a
   lever and stop treating it as a defence.

**Decisions.**

2. **Cross-family reuse needs a structural lever.** The live round names per-family mutation or a
   reuse cap. Both reviews' F5 concerns now converge here.
3. **The fill-model choice is a priced trade**, not a quality ranking: sonnet-5 delivers and
   conforms where v4-pro fails both, at ~7x unit cost. Restate 4.1 and F4 accordingly (`R-1`).
4. **Hard-block publish override**: query production for `summary.hard_block: true`, then rule.

**Cheap and now certain.**

5. Recalibrate CG-1/2/3 against the 40 JHM digraphs (section 6). Blocks all `--strict` work.
6. Wire the fill-rate floor **and** fix the node-counting metric (`R-3`), now known to bite.
7. Add a runner for `run_guard_battery.py` (section 4.1), not per-script wiring.
8. Documentation pass: `R-7`'s numbers, `R-1`'s restatement, the safety-stub sentence, rater
   provenance ("one model in counterbalanced sessions; no child has read any book").
9. Fix the job lifecycle (`queued->running`, `rq_job_id`), the only live money leak.
10. Cap the reading-level loop (38-59% of a book's bill).

**Larger.**

11. Compose ADR-023 and ADR-028 with the framework before S-4 runs (`R-14`).
12. Assess provider ToS and output licensing for a commercial children's product (`R-14`).
13. Evaluate procedural graph sampling as the skeleton factory (fresh-eyes 10).
14. Safety corpus for 13-16 and 16+, and the prompt-injection class at 0.0 (`R-6`).

---

## 8. PR sweep 715-737: what has landed since, and what the owner has already ruled

Five agents summarized every PR from 715 to 737 and tagged each against the analysis findings.
Raw summaries in
[evidence/brief-gap-analysis-2026-08-22/pr-sweep-715-737/](./evidence/brief-gap-analysis-2026-08-22/pr-sweep-715-737/).
Two of the highest-impact PRs (**729** and **737**) are still **open**, so what they change is
pending, not landed.

### 8.1 Findings superseded by merged work

| Finding | Superseded by | What changed |
| --- | --- | --- |
| Fill feasibility: 36 of 59 skeletons infeasible, 13-16 and 16+ infeasible entirely | **#727** (merged) | `is_fill_feasible` is now wired as a selection filter (`skeleton_match.py:193`) and `MAX_FILL_OUTPUT_TOKENS = 131_072`. `UW-C07` status is `done`: all 59 production skeletons feasible. **Verified.** |
| Catalog is 76% non-compliant with its own strict bar | **#730** (merged) | Coverage went 0 to **20 strict-passing shells across all 18 offered cells**. Those 20 are the deliberately-built cover, which is why enforcing `--strict` collapses selection to exactly them. |
| Chunked-fill context overflow (274k input, 154k last batch) | **#727** (merged) | Still true as mechanics, but **the chunked path is now reached by zero production requests**, since every skeleton is feasible one-shot at the new cap. A dormant path, not a live cost. |

### 8.2 Findings explicitly confirmed as still live at HEAD

- **`--strict` is still enforced by no caller.** #730 added the shells; `check_promotion_bundle.py`
  still passes only `--allow-mvp`. The enforcement half of the finding is untouched.
- **Content-filter retried forever.** #731's own `AL-492` records a live incident: `content_filter`
  flattened to a generic transient failure and retried **7 of 7**, open and unfixed at HEAD.
- **Provider cascade unpinned.** #729 (open) swaps Ollama for Modal but `build_provider()` still has
  no `provider_order` parameter and `FallbackProvider` still has no `.model`. Retiring a leg changes
  which model a silent degradation lands on, not that it happens.
- **Hard-block publish path.** Untouched by all 23 PRs. #718 changed only the *copy*, from "you
  approve" to "a reviewer approves", matching admin-only RBAC.
- **Reading level.** #719 rebuilt the syllable counter against CMUdict ground truth (a real fix that
  removed the `AL-389` Goodharting root cause), but `reading_level_loop.py:35` still reads "It never
  blocks. RL-13 stays advisory", and the in-band / fill-rate confound is now documented rather than
  fixed.

### 8.3 The eight owner rulings in PR #737, and what each settles

> **Correction (2026-08-30).** This section counted nine. `#737` landed **eight** rulings:
> `live-structural-round-2026-08-21.md` on `main` records 8.1-8.3 and 9.1-9.5, and the merged
> commit `41d30909` is titled "eight owner rulings". Row 5 below is not a ruling: it is the
> **ADR-011 amendment** that ruling 9.1 (row 4) commissioned. Rows 1-4 are rulings 8.1-8.3 and
> 9.1; rows 6-9 are rulings 9.2-9.5.

Several of this review's open recommendations are **already ruled on**. Marked against the
[remediation plan](./cyo-brief-gap-remediation-plan-2026-08-22.md).

| # | Ruling | Effect on this review |
| --- | --- | --- |
| 1 | **Reuse (`UW-C315`)**: the diversity bar is any-reader, not social distance. Interim rule: same-skeleton books must not be served to the same reader. | Confirms F5 **and extends it**: the structural-mutation machinery is *also* ruled out as a lever. Both candidate levers this review named are now excluded, which materially narrows `D2`. |
| 2 | **Freeze split (`UW-C317`)**: machine-critical fields are normalized post-fill rather than trusted to model obedience. | Changes how the fill-integrity contract is enforced; bears on `W3` and the delivery findings. |
| 3 | **`ending.title` (`UW-C311`)**: titles are writable leaf content, not frozen. | Resolves the mutation-census ambiguity flagged in the live round's 7.1 and 7.4. |
| 4 | **ADR-011 window (`UW-C323`)**: ruling deferred pending a commissioned consistency audit. | Deliberate deferral, not an omission. |
| 5 | **ADR-011 amendment** (ratified 2026-08-22): per-cell derived decision windows, **gamebook exemption**, recalibrated endings ceilings. | **Partly answers `W6`.** The gamebook exemption is exactly the form-split this review recommended for the walk floor. |
| 6 | **Bulk vendor direction**: reject sonnet-for-everything on cost; invest in cheap models reaching quality by engineering; widen the bake-off to grok and gemini. | Directly addresses `W10` and the parallel review's `R-1`. Non-closed direction rather than a decision. |
| 7 | **Fill-rate gate (`UW-C307`)**: the floor becomes a non-blocking `needs_review` forcer, never a hard block, until per-vendor and per-band calibration exists. | **Answers `W5`'s fill-rate leg exactly as recommended.** Close that item. |
| 8 | **Narrative person (`UW-C324`)**: add a `metadata.narrative_person` field rather than an inferred convention. | Resolves the unpinned-person defect the live round measured (second-person node rates 0.648 versus 0.254 on one skeleton). |
| 9 | **Pair-unfillable policy (`UW-C325`)**: cap identical zero-content `content_filter` retries at two; production direction is re-pairing, not blind retry. | **Answers `W4`.** Interim cap is ruled; the terminal-classification work remains. |

### 8.4 Consequences for the remediation plan

- **Close `W5`'s fill-rate leg** (ruling 7) and **`W4`'s retry cap** (ruling 9); both are ruled.
- **`W6` is half-answered** (ruling 5 supplies the gamebook exemption); the prose-band enforcement
  and the 5 shells at P=0.0000 remain.
- **`GA-D2` is harder than written**: rulings 1 and 6 exclude both the differentiation directive and
  per-request mutation, so "cross-family reuse needs a structural lever" now has no surviving
  candidate lever. That elevates it from a decision to an open design problem.
- **`W9` gains urgency.** The renumbering hazard has now fired twice in two weeks: #719's merge
  renumbered **322 published lesson and register IDs across 35 files** (the PR states no existing
  check would catch a bad resolution), and commit `6fc2b34` renumbered colliding register rows when
  main merged into the sourcing branch.
- **A new register-integrity defect class**: `UW-C07`'s row *body* still narrates "enforcement
  deliberately NOT enabled" while its *status column* reads `done`. A reviewer reading the prose
  reaches the opposite conclusion from one reading the status. This misled this review's own
  component agent. Add "row body contradicts row status" to `W9`'s checker set.

## Related

- [Handoff](./cyo-brief-remediation-handoff-2026-08-22.md) for a team planning the remediation
- [Gap analysis](./cyo-brief-gap-analysis-2026-08-22.md) and its
  [remediation plan](./cyo-brief-gap-remediation-plan-2026-08-22.md)
- [Evidence](./evidence/brief-gap-analysis-2026-08-22/README.md), all 24 reports
- Parallel review: `cyo-generation-research-brief-review-2026-08-22.md` on
  `claude/stoic-maxwell-60szsf`
- Live structural round: `live-structural-round-2026-08-21.md` on
  `claude/cyo-live-story-generation-kxm0ya` (PR #737)
