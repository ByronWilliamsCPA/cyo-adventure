# Gap analysis of the 2026-08-22 generation research brief

Analysis of 2026-08-22, revised the same day after adversarial validation. Subject:
[cyo-generation-research-brief-2026-08-22.md](./cyo-generation-research-brief-2026-08-22.md).

> ## Supersession notice, 2026-08-30
>
> **This document was written on 2026-08-22 as a current-state account. `main` has moved 45 commits
> since, and several of its load-bearing claims are now wrong. Read this notice before citing
> anything below.** The decision ids in this review are namespaced `GA-D1` and `GA-D2` so they
> cannot be confused with the four `D1`..`D4` decisions in
> [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md)
> or with ADR-005's "gate D2" referenced in `publishing/service.py`.
>
> **Answered since.**
>
> - **`GA-D1` (hard-block publish override) is largely ANSWERED.** ADR-005 carries amendments dated
>   2026-08-25 ("overriding automated severe findings") and 2026-08-28 ("an absent judgment is not an
>   overridable one"), landed via #764, #769, #776 and #778. `approve()` now runs four ordered
>   refusals: no report at all, a report with no genuine judgment in it (`moderation_report_unusable`),
>   a report whose reviewer did not see every node (`moderation_coverage_incomplete`), and a report
>   carrying a severe finding, which a human may approve over but only with a recorded
>   `override_reason` of at least 10 characters, stamped into the audit log with the overridden
>   counts. The shipped admin console disables Approve until that reason is typed. **Three residuals
>   survive and are the only live part of `GA-D1`:** the audit payload records override *counts*,
>   not the ids of the findings overridden, so a later re-moderation makes an override
>   unreconstructible from durable state; `ApproveBody` still carries no `version` field, so approve
>   still re-derives the latest version rather than binding to the one the reviewer read; and the
>   dual-role self-approve leg is stamped, not refused, so there is still no four-eyes requirement.
>   One adjacent claim outside `GA-D1`'s five requirements also still stands: `submit()`
>   (`publishing/service.py:161`) still guards only `moderation_report is None`, so the
>   `needs_revision -> in_review` hop still re-admits a BLOCK-carrying report with no forced
>   re-screen.
> - **The economics work is SUPERSEDED.** #784 (`2b8bc8e1`, 2026-08-30) landed
>   [unit-cost-model.md](./unit-cost-model.md), `scripts/unit_cost_model.py` and
>   `src/cyo_adventure/core/pricing.py`: a per-book cost model generated from billed prose-fill
>   records rather than from model defaults. `main`'s revenue anchor is now a $1.99 or $4.99
>   subscription, not the "$5-8 catalog subscription with metered credit packs" assumed here. Treat
>   every dollar figure in this review, and all of `V4-economics.md`, as pre-#784.
> - **V7's entire standing correction is VOID, and it now points backwards.** `V7-fill-stage.md`
>   opens by correcting the fill-stage numbers on the grounds that they were derived from DeepSeek
>   V4 Pro at cap 131,072 while production shipped `anthropic/claude-haiku-4.5` at 64,000, chunking
>   19 of 84 skeletons. `3ad864a3` (#747, 2026-08-24) set `core/config.py:490` to
>   `deepseek/deepseek-v4-pro` (cap 393,216). **Production now runs the exact model V7 said the
>   figures were wrongly derived from**, so V7's correction inverts. Its "every batch asks for the
>   full model cap" finding is separately fixed: `orchestrator.py` now runs a per-batch
>   context-window guard.
> - **V11's "sweep 2 is dead" is FIXED.** `queue.py`'s second sweep now selects `running` rows past
>   the timeout margin, force-fails them with `interrupted: worker died`, records a
>   `GENERATION_FINISHED` event, and **commits**.
> - **V1's claim that no committed script implements a body-only gram scope is FALSE on `main`.**
>   `scripts/check_corpus_convergence.py:145` passes `include_choice_labels=False`, as do
>   `moderation/leaf_diversity.py:183` and `validator/series.py:194`. The narrow claim that
>   `check_sibling_fills.py` itself hardcodes `True` still holds; the remedy was implemented
>   elsewhere and never pointed at the sibling check.
> - **`W1` is HALF fixed.** `api/generation.py:181` now passes `rq_job_id`; `api/story_requests.py:107`
>   still does not. Only that second leg is live work.
>
> **Arithmetic that is stale, where the finding's shape survives.**
>
> - **V9's rule arithmetic:** 58 distinct validator rule ids on `main`, not 55 (`CG-6`, `PN-1` and
>   `L2-15` were added). Its structural findings, including that SAFE-14 is unfireable by
>   construction, hold.
> - **V4's "86 shells" was ALREADY WRONG when written.** The authoritative census is
>   [catalog-census.md](./catalog-census.md) (#740): **84 shells, 15,470 nodes, 81 declaring
>   production-eligible, 74 reachable in an offered cell, 18 offered cells all covered.** V4's +1
>   errors match a failure to exclude `.narrative.json` sidecars.
> - **"63 migrations" is now 67**, and **"nine owner rulings" is eight**, plus the ADR-011 amendment
>   that ruling 9.1 commissioned and that this review counted as a ninth ruling.
> - **V9's testing-ladder findings must be re-read against `6cc33aa5` (#780)** before any of them is
>   cited as current. That commit touches 134 files and is aimed squarely at the subject matter
>   ("make the testing ladder's checks fail when their subjects break"). Which of V9's findings it
>   closes has not been determined.
>
> **Reproducibility.** Several V reports state figures computed by harnesses that were never
> committed (`scratchpad/validation/v5_stats.py`, `v7_econ.py`, `v3run.py`, `scratchpad/canon/`) and
> cite paths under `/home/user/` and `/tmp/claude-0/` that do not exist in this repository. **Every
> figure resting on those harnesses is unreproducible from this branch.** This is the same failure
> mode `AL-510` and `UW-C317` record and that these very reports criticise, so it is disclosed here
> rather than left implicit. Affected files carry their own notice.
>
> **What survives, and must not be softened.**
>
> - `validator/blind_spots.py` and `validator/imitable.py` still have zero production callers.
> - V1's 148-pair null control puts the published 3.3 idiom floor at the **80th percentile of the
>   true null**.
> - V5's finding that **7 of 342 shell-shell pairs breach `TAU_CELL` and all seven are cross-vendor**,
>   while **0 of 190 shell-catalog pairs** do.
> - **No caller anywhere passes `check_skeleton.py --strict` on the gate path.**
> - **`UW-C290` is still falsely marked done**; `gate.py:269` still calls `check_safety`.
> - V9's finding that `bf7cad1` edited three already-completed pre-registrations, flipping D-7b from
>   at the floor to below it, and that **those rows are still not voided on `main`**.
>
> **Programme context.** [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md)
> already exists on `main` and schedules the parallel `R-1`..`R-14` review that
> [the reconciliation](./cyo-brief-review-reconciliation-2026-08-22.md) compares against. The two
> tracks are one programme; read them together rather than as competing accounts.

> **Superseded in part.** A live structural round (PR #737, branch
> `claude/cyo-live-story-generation-kxm0ya`) has since measured the differentiation directive and
> re-run the worst fill pairs on the production-family model. It refutes the directive as a variety
> lever and shows the 0.6 fill-rate floor does bite on current output, correcting section 4.3 and
> recommendation 7 of this document. See
> [cyo-brief-review-reconciliation-2026-08-22.md](./cyo-brief-review-reconciliation-2026-08-22.md),
> which also reconciles this review against the parallel 13-agent review on
> `claude/stoic-maxwell-60szsf`.

**Per-item remediation plans are in
[cyo-brief-gap-remediation-plan-2026-08-22.md](./cyo-brief-gap-remediation-plan-2026-08-22.md); all
24 raw reports are preserved in
[evidence/brief-gap-analysis-2026-08-22/](./evidence/brief-gap-analysis-2026-08-22/README.md).**

Twelve reviewers analysed the brief, its evidence, and the code it describes. Twelve adversarial
validators then tried to break every load-bearing finding and stress-test every recommendation.
**The validation pass overturned more of the first-round output than it confirmed**, so this
document leads with what survived, and section 2 is a full correction log rather than a quiet edit.

> **Why the correction log is the most useful part.** The first round was run under an instruction
> to find gaps, which reliably inflates severity and rewards reading a number off a nearby structure
> instead of out of the branch that consumes it. The programme's own `AL-479` names that exact
> failure mode from a prior adversarial review ("five of six claims wrong in some part, three of
> them quoting a bound I had not executed"). This review committed it at least four times. Anyone
> reading first-round findings elsewhere should check them against section 2 first.

---

## 0. Method and calibration

**Round 1.** Three blank-slate reviewers (barred from `docs/planning/`, given only the product goal,
producing 191 yes/no requirements), three structural reviewers, six component reviewers. 161
findings.

**Round 2.** Twelve validators, each told to refute before confirming, and to review the
recommendation for correctness, blast radius, and omissions.

**Calibration measured by the red team:**

| Metric | Value |
|---|---|
| Criticality inflation | **63%** (10 of 16 sampled critical/high survive only at lower severity; 3 drop two notches) |
| Findings in top two severity bands | 65% of 161 |
| Framed as an absence | 64 of 161 (40%), of which >=24 restate an existing UW row, owner ruling, or in-code self-label |
| Value of claimed reviewer "convergence" | ~1/4 of its billing (the blank-slate trio is one model sampled three times; two "independent" code findings read the same 20 lines) |

Confidence markers below: **[verified]** re-run by the synthesis author; **[validated]** survived a
validator's refutation attempt; **[code]** grounded at `file:line`, not independently re-run.

---

## 1. What survived, ranked

### 1.1 F5's flagship result was changed from null to positive by an undisclosed second method change

This replaces the first round's "the number does not reproduce", which was wrong (see 2.1).

The chain, established by three validators and re-verified here:

- The register's D-7b row originally read **3.2 per 1000, "at the 3.3 floor"**: a null result, at the
  measurement's own noise floor.
- Commit **`bf7cad1`** (2026-08-12, PR #703) rewrote that closed, pre-registered row to **2.3,
  "*below* the 3.3 floor"**, converting it into the positive finding F5 rests on **[verified]**. Two
  other already-`done` rows were rewritten in the same commit (D-6 16.9->17.2, D-7 12.9->13.6). None
  was marked voided, which the register's own section F requires. The commit body does disclose the
  re-derivation, so this is method drift with partial disclosure, not concealment.
- The published 2.3 requires **two** method changes, per-body units **and** body-only scope, and only
  one is disclosed **[validated]**.
- The shipped `check_sibling_fills.py` still returns **3.2** because it grams a joined string, a
  defect already registered as **`UW-C225`** with a proposed fix and pre-established regression
  counts, status `unscheduled` **[verified]**. So the production gate and the published calibration
  disagree about what they measure.
- The floor itself does not survive contact with a control. A validator built the one the programme
  never did (148 unrelated pairs at matched scale): mean **1.94**, bootstrap CI **[1.25, 2.64]**,
  P(mean >= 3.3) = 0.0008. The published 3.3 is the **80th percentile of the true null**, and D-7b at
  2.33 sits at the **66th**, above the median. "Below the idiom floor" should read "more similar than
  a typical unrelated pair" **[validated]**.

**And the buried result.** The D-7b **recognition verdicts** are committed in the evidence tree:
`first_yes_position: 2`, `distinctness 1/5`, both raters naming an identical three-way opening act
with one-to-one scene mapping. That is the programme's own pre-registered falsifier firing on F5's
flagship artifact. The brief reports only the 2.3.

**Root cause, and the most useful single fact in this document:** `world_recipe.requires` is
**byte-identical across both D-7b contracts**, and it is a closed, enumerated menu of narrative
decisions with draw counts (`cipher_forms` 1 of 5, `access_details` 3 of 7, `remedies` 1 of 6, and
six more) **[verified]**. The shared "structural" stratum *is* the decision space. F5 says never
reuse decisions; D-7b reuses the decision menu and generates only its realisation. That is a
defensible architecture, but it is not the one F5 states, and it explains the scene-2 verdicts with
no appeal to prose convergence at all.

**Recommendation.** Put the recognition verdicts into the F5 decision. Void and re-close the three
edited rows per section F. Land `UW-C225`. Do **not** reconstruct D-7b selections to run solution
transfer: tier 1 of that tool is a text-similarity test, so whoever writes the reconstruction sets
the answer, a larger degree of freedom than the one its own docstring warns about.

### 1.2 Five shells give a child essentially zero chance of a satisfying ending

Measured across the 84 real graphs, sidecars excluded **[verified]**:

```text
0.0000  the-labyrinth-of-glass (13-16)   0.0000  the-tenfold-siege (16+)
0.0000  the-ashfall-expedition (16+)     0.0000  the-drowned-court (16+)
0.0000  the-pale-road (16+)              0.0000  the-thornwood-trial (13-16)
0.0000  the-red-meridian-run (16+)       0.0000  the-iron-spire-trial (13-16)
0.0006  the-blackwood-sanatorium (16+)   0.0047  the-smugglers-cut (13-16)
```

Five are exactly zero, eight are at or below 0.00005. The rule that prevents this exists, these
breach it, and they remain selectable; 11 selectable shells breach the floor in total
**[validated]**. Honest caveat: the 16+ cell is gamebook-form where a punishing win rate is a genre
convention, and the cell median is 0.0000 by design. At 13-16 it is much harder to defend.

**Recommendation.** Split the floor by form: enforce it for prose CYO, declare and document the
gamebook exemption rather than leaving it as an unenforced rule.

### 1.3 A hard-blocked book can be published in two clicks, by design

> **Correction, 2026-08-30: the two-clicks finding below is CLOSED; three narrower defects it names
> still stand.** This section records what was true on 2026-08-22 and is left as written. What
> changed: `approve()` no longer runs a single `moderation_report is None` check. Four ordered
> refusals now stack in `publishing/service.py::_assert_report_permits_approval` (`:356` onward):
> `approve_without_moderation` (`:409`), `approve_with_unusable_moderation` (`:422`),
> `approve_with_incomplete_coverage` (`:444`), and `approve_requires_override_reason` (`:474`).
> The fourth is gate D2 of the **ADR-005 amendment of 2026-08-25** (`#CRITICAL` comment at `:445`):
> approving over a block or high-severity finding is refused unless a non-whitespace
> `override_reason` is supplied, and the approval stamps `overridden_block_count` /
> `overridden_high_count` onto the RELEASED audit payload (`:670`). So "two clicks" and "leaves no
> distinguishable trace" are both retired.
>
> Still standing, verified against `origin/main` on 2026-08-30: `submit()` guards only
> `moderation_report is None` (`service.py:161`, rule `submit_without_moderation`), so the
> screened-ness-not-block-freeness reading of the invariant is unchanged for that hop;
> `ApproveBody` (`api/schemas.py:1828`) still carries no `version` field, so approval still pins no
> artifact hash; and the dual-role self-approve leg is stamped `guardian` by
> `Principal.acting_role()`, not refused. The `has_hard_block` symbol is still read only inside
> `moderation/`, because the new guard is expressed through `severe_finding_counts()`; grepping for
> that symbol reports the guard as absent when it is present.

`publishing/service.py:412` guards only `moderation_report is None`; `has_hard_block` is read at
eight sites, all inside `moderation/`; no DB constraint exists across the 67 migrations on `main` as of 2026-08-30 (63 when written); the frontend
gates on status alone **[verified]**. The shortest path is two clicks: edit any node of an
`in_review` book, the fresh BLOCK merges while status stays `in_review`, then Approve. That
behaviour is deliberate, commented `#CRITICAL` in `node_edit.py`, and locked by a passing test
**[validated]**.

So this is not a bug. ADR-005 only ever claimed no *auto*-publish, and the service comment states the
invariant as "no *unmoderated* path reaches published", which is screened-ness, not block-freeness.
The real defects are narrower and real: **the override leaves no distinguishable trace, `ApproveBody`
pins no version, and a dual-role adult self-approves.**

**Recommendation.** This needs an owner ruling, not a patch. If override stays, make it explicit:
a typed override reason, the blocking finding ids copied onto the approval record, a pinned version
hash, and separation of duties for dual-role adults. **First action, which I could not run here:
query production for any published version with `summary.hard_block: true`.** Nonzero means this is
a live incident rather than a latent design gap.

### 1.4 The reading-level loop is the one real cost lever

Confirmed at n=3 and **understated** by the first round: **38%, 51%, 59%** of a book's bill, not 46%,
with an uncapped call count, for an `in_band` result of 0.155 **[validated]**.

Everything else in the fill stage is small. Total recoverable across all fill-stage fixes is
**$0.05-0.08 per book** (~4% of machine cost), $0.30-0.46 on a 16+ book. Caching yields ~$0.007
because `cache_control` is already set and the user block is ordered volatile-first.

Two measured waste modes worth more attention than the token levers:

- **154,253 output tokens billed to retain 38,176 tokens of text**, a 4.0x ratio larger than every
  F7 lever combined **[validated]**.
- A content filter can be **deterministic for a (skeleton, brief) pair** (`AL-492`: book 0 failed 7
  of 7) and is reported as a generic transient failure, so the harness retries what can never
  succeed. A validator drove the parsers live and showed a content-block response yields
  `dig_content=None` with `finish_reason='stop'`, classified transient, **retried forever**
  **[validated]**.

### 1.5 The only live money leak: the job lifecycle

`queued->running` is never committed in its own transaction, so one sweep is dead and another
re-enqueues live jobs, and the story_requests enqueue omits `rq_job_id`, producing double spend
**[code]**. Every other cost finding measures or increases cost; this one loses money now. It is
also a prerequisite: changing fill timeouts is unsafe until it ships **[validated]**.

### 1.6 New: models from different labs converge on each other, not on the catalog

**7 of 342 shell-shell pairs breach TAU_CELL, all cross-vendor** (Opus and Kimi at 0.0191), with
three separate labs independently emitting 45 nodes, 91 choices, and branching factor exactly 3.000.
Meanwhile **zero of 190 shell-catalog pairs breach it** **[validated]**. Nobody had reported this,
and it bears directly on whether model diversity can ever serve as a variety lever.

### 1.7 The honesty machinery has real holes, though smaller than first reported

Confirmed by independent reconstruction **[validated]**: the lessons log's "append-only" docstring is
false (deleting the newest lesson, or any lesson plus a tail renumber, passes); the consecutive-id
rule *forces* renumbering and has already broken a real citation (`bf7cad1` cites AL-296/297 for
content now at AL-309); a register row may cite a nonexistent lesson; a `rejected` lesson can be
flipped to `applied` with one `sed`; and pre-registration precedence rests on branch-local commit
order that this squash-only repo destroys at merge, so the sourcing branch will collapse S-1's
registration and its results into a single commit.

---

## 2. Correction log: what validation overturned

Recorded in full because these claims circulated before they were checked.

| First-round claim | Status after validation |
|---|---|
| F5's 2.3 does not reproduce (tool returns 3.2) | **Retracted.** 2.3 is the documented body-only scope; 3.2 is the superseded label-inclusive one the shipped tool still computes. Real defect is `UW-C225`, already registered. Replaced by 1.1. |
| Catalog is convergent across different graphs in different worlds | **Substantially weakened.** The control shared band, tier, topology and reading level, 3 of 4 themes, and ranks 6th most similar of 105 pairs. "Both raters" is one model (`claude-fable-5`) in two counterbalanced sessions rating two different-length stimuli. The instrument has never returned "different" in the programme's history, so it cannot be positive evidence. |
| All three surviving instruments miss the control pair (false negative) | **Retracted, and it was my error not a reviewer's.** The 0.925 / 0-of-26 ATG figures belong to a different pair; the ATG raises `ValidationError` on the control. Structural distance 0.1239 is *below* same-cell p05, so it agrees with the raters. Threshold misapplication, not blindness. |
| Cosmetic choice is rampant; gate `consequence.py`; enforce `--strict` | **Retracted on three independent grounds.** (a) Catalog-wide cosmetic choice is **378 of 22,165 choices = 1.71%**, and **306 of those are one shell** **[verified]**; 105 duplicate-target choices carry differing effects that downstream conditions read. (b) **`UW-C181` is an explicit owner ruling rejecting the illusory-choice gate**, on the ground that loop-back exploration is a convention of the form. (c) Enforcing `--strict` collapses selection from **74 shells to 20, one per cell in 16 of 18 cells**, causing a worse variety problem than it solves. Also: `consequence.py` returns `None` for 48 of 84 books and is self-labelled "a reported statistic, not a gate". |
| Economics over by 4-28x at $10/70% margin | **Denominator retracted.** ADR-008 and PROJECT-PLAN show generation sold as metered credit packs with a ~$5-8 catalog subscription and 15% Apple take. Corrected all-in: **$1.51 / $5.70 / $24.52** (low/central/high), the whole spread being one unmeasured quantity, actual review minutes. |
| Model ranking measures catalog conformity (Spearman -0.982) | **Statistic replicates exactly; interpretation retracted.** At leg level, catalog distance is rank-identical to mean node count (rho = -1.0000) because cell D's catalog is 91-105 nodes while `--allow-mvp` caps shells at 45. The association lives entirely inside gate-policed features and vanishes in gate-free ones. Same constraint measured twice. Replaced by 1.6. |
| F3's tool-assisted regime exists as code nowhere | **Retracted.** `modal_kimi_leg.py:341-412` (`run_grid_point_tools`), `--mode tools`, `_TOOLS_CHECKER_CAP = 10` **[verified]**. Hand-recorded `tools-meta.json` agrees with harness verdicts 42 of 42, and the deterministic half reproduces exactly (27/15, 0 disagreements). Surviving finding: `cyo-author` is a *fill* skill and cannot author skeletons, so brief §3.1 and `AL-513` mis-attribute the mechanism. |
| Seven detectors built and gating nothing | **Reduced to two plus an unrun registry.** `check_fill_integrity` and `check_sibling_fills` are registered `gating=True` in `run_guard_battery.py` with tests; the battery has no runner **[verified]**. `consequence.py` and `paths.py` are documented KEEP/infrastructure. `safety.py` is real but `validator-rules.md` says "NOT IMPLEMENTED IN THE GATE" in bold twice. Genuine cases: `imitable.py`, and a new one, **`validator/blind_spots.py`**, the module built to make gate silence legible, itself silent. **`AL-305` already states the proposed rule, better, and names the registry.** |
| Every large fill times out, retries 3x, degrades to a fallback tier | **Consequence retracted.** 120s is per HTTP call; the 469-1874s figures are per-*book* sums dominated by ~72 reading-level calls. `AL-492` records 397s attempts completing through this adapter. Mechanism stands, consequence does not. Critical -> high. |
| Wire the 0.6 fill-rate floor | **No-op.** 0 of 43 committed pairs fail at 0.6 (tightest good 0.634). Ship as `needs_review`, not a block. |
| The `drafting_guide` line licenses under-delivery | **Retracted.** Across 9 books and 3 vendors on the same prompt, fill rate spans 0.714-0.982. Model-driven, not prompt-driven. |
| ~594k input tokens/book, over the context window | **Numbers wrong, defect narrowed.** That used a non-shipped model's 32,768 cap. Shipped Haiku 64,000 gives 274k total / 154k last batch. Real defect: last batch plus full `max_tokens` = 218k against Haiku's 200k window, on 2-3 of 84 skeletons. |
| 57 of 240 `applied` refs resolve to nothing | **Retracted as a number.** Independent resolver gives **4** under "no machine-checkable anchor", 140 under "no anchor pinning a specific change". No definition yields 57. Mechanism confirmed and strengthened. |
| 8 of 15 `check_*.py` gates untested | **Inflated; true figure 5 of 15.** |
| The rules would reject the canon | **Mostly refuted.** CYOA #53 and the JHM median book **pass** the production gate at 8-11, failing at 10-13 on one line (`PL-29` bans `time_cave`). Warlock's node count passes at 13-16/long. Rules are correctly narrow on stakes, wrongly narrow on topology and cadence. |
| Catalog census unresolved (61 / 84 / 147) | **Settled: 74 auto-pickable** across 18 offered cells, all populated (pools 3-5, median 4). 149 files = 84 graphs + 65 sidecars. The "4 empty cells" claim is struck. |
| Sibling convergence 96.3 is ~1.15x at scale (a correction favouring the programme) | **Retracted.** The N^0.788 fit had two confounded points and zero residual df. `AL-498`'s alarm stands; 96.3 is itself label-inclusive (67.2 body-only). |
| Threshold flywheel converts an over-approving admin into hidden findings | **Substantially refuted.** Suggestions are read-only, thresholds filter family surfaces only, nothing auto-applies. |
| Repair can rewire the graph | **Split.** `run_gate` does re-run on repair adoption, so arbitrary rewiring is refuted; skeleton fidelity genuinely never re-runs. |
| Guardian-primary approval as the economic fix | **Blocked by a settled decision.** ADR-005's 2026-06-30 amendment moved the approver *to* admin, owner-confirmed and re-ratified 2026-07-16, and `visibility=catalog` publishes cross-family. The binding constraint is ADR-008's Kids Category "pre-moderated pipeline" commitment, not COPPA/KWS. |

---

## 3. What the brief gets right, confirmed under challenge

- **F3's core claim survives every confound.** Tool-assisted authoring beats blind decisively. What
  does not survive is the per-model ranking on top of it.
- **"Not v4-pro for structure" survives n=3 scrutiny** (0/6, two failure modes). It is the one
  model-level claim in §4.2 that is statistically safe.
- **S-1's deterministic half reproduces exactly**: 27/15, zero disagreements across 42 shells.
- **S-1's falsifier cell was never edited**, only its Status. That corrects a first-round suspicion
  in the programme's favour.
- **`recognition-protocol-pilot/results.md` reports a failed instrument as failed** and refuses the
  tempting post-hoc repair.
- **`AL-479` already documents this review's own failure mode**, from a prior adversarial pass on an
  owner-requested review.
- **`AL-305` already proposes the gate-registry rule** this review reinvented.
- **Evidence-class labelling** (deterministic / model-judged / human-gated, with model-judged named
  as the weak class) is better practice than most organisations manage.

---

## 4. Revised recommendations

Only items that survived validation, ordered by (impact x certainty) / (effort x risk).

**Decisions, not code.**

1. **Rule on the hard-block override** (1.3). First query production for `summary.hard_block: true`
   on published versions. Then either close the path or make the override typed, traced,
   version-pinned, and subject to separation of duties.
2. **Put the D-7b recognition verdicts into the F5 decision** (1.1), void and re-close the three
   edited register rows per section F, and decide explicitly whether sharing a closed decision menu
   is the architecture you want. It may well be; it is simply not what F5 says.

**Cheap, safe, and now known to be correct.**

3. **Fix the job lifecycle** (1.5): commit `queued->running` in its own transaction, pass
   `rq_job_id`. The only live money leak, and a prerequisite for any timeout change.
4. **Cap the reading-level loop** (1.4). 38-59% of a book's bill for `in_band` 0.155.
5. **Land `UW-C225`** so the gate and the calibration measure the same thing, using the register's
   pre-established regression counts.
6. **Classify content-filter failures as terminal, not transient** (1.4), and fix the
   `dig_content=None` + `finish_reason='stop'` infinite-retry path.
7. **Run `run_guard_battery.py`** at all, after fixing the `--allow-title-rewrite` and
   `{PLACEHOLDER}` defects that would fail 28 of 31 books for non-reasons. Ship the fill-rate leg as
   `needs_review`.
8. **Split the walk floor by form** (1.2) and enforce it for prose CYO.
9. **Wire `imitable.py` and `blind_spots.py`**, the two genuine unwired cases.

**Do not do.**

- Do not enforce `--strict` as-is: it collapses selection 74 -> 20. **97% of strict findings are
  CG-1/2/3**, a family calibrated to an internal designer table while everything else is calibrated
  to JHM, and CG-2 demands 3-way decisions where JHM's maximum outdegree averages 2.58. Recalibrate
  CG first.
- Do not gate `consequence.py` (owner ruling `UW-C181`; returns `None` for 48 of 84 books).
- Do not add a novelty term to the pass criterion: TAU_CELL exists, nothing breaches it against the
  catalog, and it would penalise gate compliance.
- Do not build path-level evaluation before the instrument question is settled; doing so is the F6
  failure this review otherwise criticises.
- Do not reconstruct D-7b selections for solution transfer (the reconstructor sets the answer).

**The free calibration fix.** Run `check_skeleton.py` over the 40 JHM digraphs the repo already
cites and set a two-sided policy: admit >= X% of the anchor corpus, reject 100% of seeded defects.
That replaces circular calibration at zero cost.

**The settling experiment for model selection** costs **under $5 of credit**: 3 legs x 12 x 2
counterbalanced cells, an uncensorable primary endpoint, harness-instrumented loop. The cost is
engineering time, not provider spend.

---

## 5. What nobody looked at

Both rounds concentrated on generation and left the product unexamined. Never opened: **436 frontend
files**, the player and offline path, series continuity, personalization, the cover-art pipeline,
onboarding and request intake, and what a family experiences when generation fails. The review
declared "the reader is absent" from the framework while `reader-path-engagement-design.md` and
`check_prose_craft.py --max-moral-tags` both exist and were reported as gaps.

The blank-slate cohort's 191 requirements remain the most useful unexploited artifact, with one
caveat the red team established: they are one model sampled three times, so treat them as a
checklist, not as independent corroboration. Their strongest surviving contributions are
**precondition dominance** (every fact asserted as known must be established on every path reaching
that node, fully computable and unbuilt), **choice-label predictiveness**, a **peril floor** to make
over-moderation visible, and **seeded known-bad books** in the review queue, which a validator found
is largely already built (`moderation-qa-corpus.json`, seeder, scorecard, `mqa_` containment prefix)
and needs only blind production injection and path-shaped seeds.

One structural question neither round resolved: **the catalog's real economic function is amortising
structural review, not authoring.** Component composition only pays if `run_gate` becomes
compositional. A validator recommends two weeks classifying the ~15 blocking rules as local,
assembly-invariant, or global before committing either way.

## Related

- [Handoff](./cyo-brief-remediation-handoff-2026-08-22.md) for a team planning the remediation
- [Reconciliation](./cyo-brief-review-reconciliation-2026-08-22.md) against the parallel review and the live round
- [Remediation plan](./cyo-brief-gap-remediation-plan-2026-08-22.md), one plan per surviving item
- [Evidence](./evidence/brief-gap-analysis-2026-08-22/README.md), all 24 reviewer and validator reports
- [2026-08-22 research brief](./cyo-generation-research-brief-2026-08-22.md), the subject
- [2026-08-10 research brief](./cyo-generation-research-brief-2026-08-10.md)
- [Diversity test register](./diversity-test-register.md)
- [Architecture re-specification](./architecture-respecification-2026-08-10.md)
