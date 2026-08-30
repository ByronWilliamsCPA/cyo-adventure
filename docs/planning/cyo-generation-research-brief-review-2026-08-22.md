# Multi-agent review of the 2026-08-22 generation research brief

Date: 2026-08-22. Subject:
[cyo-generation-research-brief-2026-08-22.md](./cyo-generation-research-brief-2026-08-22.md), reviewed as the
current account of the framework for producing high quality CYO books at acceptable cost.

Method: thirteen independent review agents in three groups. Four fresh-eyes agents received only the product
goal (no access to the brief, companions, or code) and specified the ideal evaluation methodology, cost
discipline, editorial standard, and generation architecture from first principles; their output was diffed
against the programme to expose blind spots. Four structural reviewers read the whole brief and audited it for
scientific rigor, claim-by-claim accuracy, strategic coherence, and testing and reproducibility engineering.
Five component reviewers went deep on the skeleton stage, the fill stage, diversity and instruments, cost, and
safety plus the human gate. All repo-grounded agents verified claims against the research branch
`claude/model-selection-skeleton-dev-78yp7u` (checked out read-only), including the raw run records under
`docs/planning/evidence/`, the register, the test plan, and the production code. Where this review quotes a
number, at least one agent recomputed it from committed artifacts; where two agents disagreed, the recomputed
value from raw records was used. Companion citations refer to the research-branch versions as read on
2026-08-22; the copies on `main` carry later corrections this review predates.

Severity scale: Critical undermines a load-bearing conclusion or the business goal; High is a material gap or
weakness; Medium and Low are real but smaller. Findings carry stable IDs R-1 and up.

> **Landed 2026-08-30, and dated.** This document is the 2026-08-22 record of what thirteen agents found on
> that date, against the research branch `claude/model-selection-skeleton-dev-78yp7u` at `01b7119`. It is kept
> as evidence, not maintained as current state: `main`'s registers cite `R-1` through `R-14` by name, and this
> is the source those names point at. Current disposition for every finding lives in
> [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md), which
> traces each one to a step with acceptance criteria. **Several findings have been overtaken by work that
> landed after 2026-08-22**; a dated note appears under each affected finding, and this list is deliberately
> not enumerated here, because an exhaustive count in a banner goes stale the next time something lands. The
> current disposition of every `R-*` is carried by
> [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md) and
> [diversity-test-register.md](./diversity-test-register.md), and those are authoritative over anything here.
> Absence of a note is weak evidence: it means nothing was found to have moved when the notes were last swept
> (2026-08-30, covering R-1 through R-14), not that nothing has. R-9's promotion-CI half was re-verified
> against `main` on 2026-08-30 and still stands. Where this document and the
> brief it reviews disagree, the brief on `main` is the corrected text: it absorbed R-1, R-7 and others through
> [#738](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/738) and later PRs, and no copy of it is
> carried alongside this review.

## 1. Verdict

The programme underneath the brief is unusually good: pre-registered experiments with falsifiers that actually
fire, negative results published as headlines, deterministic artifacts a stranger can re-run, and honest
self-correction. The brief itself, as a decision document, is not yet trustworthy: its two headline model
claims are contradicted or unsupported by the programme's own artifacts, its central framework principles rest
on evidence it overstates, the floors it presents as pipeline defenses are mostly offline scripts, the defect
it names as the one that matters most currently has no working detector anywhere, safety measurement lags
quality measurement by an order of magnitude, and the economics half of the goal has no target, no unit-cost
model, and no accounting for the human minutes that will dominate cost at scale. Most of the fixes are cheap;
several are documentation-only. The expensive risk is letting section 4.2's "consequence for the product"
lines harden into production policy before the corrections below land.

## 2. Critical findings

### R-1. The fill-model claim inverts the programme's own evidence (4.1, F4)

Found independently by four reviewers. The brief: "DeepSeek V4 Pro emerged as the best judged prose at roughly
a fifth the cost of the premium Western legs", and F4 builds on it. The only blind cross-lab panel on record
(2026-08-10 brief, section 29) scores V4 Pro at judged quality -0.13, fifth of eight, behind sonnet-5 (+0.69),
grok-4.6 (+0.61), gpt-5.6-sol (+0.38), and sonnet-4.6 (+0.14); section 31 states the actual trade (4.9x
cheaper, gives up 0.74 z of judged quality) and calls grok-4.6 "close to dominant". No later panel reversing
this exists anywhere on the research branch. What V4 Pro actually won is cost per delivered book ($0.0398
versus $0.186 to $1.42). Additional defects in the same section: the selection was produced by the
model-judged class that F6 says may confirm but never produce rankings; the judged design cannot rank eight
legs anyway (four books per leg, one band, no inter-judge agreement statistic, one leg's top score resting on
a single delivered book); and "six legs across five labs" describes the aborted slate, not the measured one
(eight legs, six labs). Fix: restate 4.1 and F4 as the priced trade they are, carry the three-axis table
(quality, diversity, cost) forward, and re-open the fill-model choice as the policy question the test plan
actually posed.

> **Note added 2026-08-30. Fix landed; conclusion discharged.** All three parts of the fix are done on `main`.
> The brief no longer makes the claim: `cyo-generation-research-brief-2026-08-22.md:283` now reads "DeepSeek
> V4 Pro did not emerge as the best-judged prose. It is the cheapest leg per delivered book", and `:106` says
> "It is not the best-judged prose model", both absorbed through
> [#738](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/738). The fill-model choice was re-opened as a
> policy question and ruled: `D1` in the workstream plan, ruled provisionally 2026-08-23, keeps
> `deepseek/deepseek-v4-pro` on the fill lane on cost and optionality grounds and states in as many words that
> the ruling "deliberately does not rest on" the disputed ranking, with the measurement preceding it kept
> rather than replaced. That is the shape this finding asked for: the conclusion was not that V4 Pro is the
> wrong leg, it was that the stated reason for choosing it was false. The reason is now different and the
> measurement it rests on is visible.

### R-2. The flagship defect has no working detector, and production is unguarded at the decision level (1, 4.4, F5)

The brief names decision regurgitation as the quality defect that matters most. Today nothing can detect it:
DecisionSignature v1 and v2 invert against raters, the recognition protocol failed its pre-registered control,
and solution transfer's surviving tier measures puzzle-device portability, a proper subset that is blind to
the brief's own worked example. What protects production meanwhile: a differentiation directive whose effect
was never measured and which, at production settings, renders its weakest level for exactly the load-bearing
case (cross-family same-skeleton siblings always get the "write it straight" TREE paragraph, because
escalation is per-family and theme-gated); `check_sibling_fills.py`, imported nowhere in `src/`; an advisory,
fail-open leaf-diversity flag defined only for same-fingerprint pairs; and weighted-random skeleton selection
that guarantees a full decision-sequence repeat at cell exhaustion (register row Q-1). The measured exposure:
a same-skeleton sibling pair shares 96.3 4-grams per 1000, 24x budget, and passed the deterministic gate. Fix:
wire the sibling-gram check into the worker for same-skeleton fills, run the blocked directive-delta
measurement at production settings (not only the committed best-case spec), add a per-family reuse cap, and
fund a decision-level instrument (the architecture re-specification's declared operation and stake schema
field is the cheapest credible path).

> **Note added 2026-08-30. One premise superseded.** "A differentiation directive whose effect was never
> measured" was true on 2026-08-22 and is no longer. The blocked measurement this finding asks for has since
> run, landing in `41d30909` ([#737](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/737)) as section
> 7.2 of [live-structural-round-2026-08-21.md](./live-structural-round-2026-08-21.md), titled "The directive is
> not the lever". It refutes the directive rather than rescuing it: 96.3 shared four-grams per 1000 raw against
> 110.7 best-case directed, about 15% worse, with hand-authored same-skeleton twins at 202.0 and a budget of
> 4.0. The finding's conclusion is unaffected; only the "never measured" clause is stale, and that
> recommendation is discharged. The sibling-gram recommendation also moved: a shared `diversity/grams.py`
> definition now backs an advisory request-path check in `moderation/leaf_diversity.py`, with validator rule
> `SR-10` enforced through `publishing/service.py::approve` (`37a08a60`,
> [#742](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/742)). `check_sibling_fills.py` itself is still
> offline. The per-family reuse cap and the decision-level instrument remain open.

### R-3. The delivery floors exist only where nobody ships from (3.4, F2)

F2 claims every gate is paired with a delivery measurement so a hollow pass is visible. The fill-rate floor
(0.6, calibrated so the under-delivering books fail) is a standalone script invoked by no production module,
workflow, or hook; the register row itself says gate carriage is still open. The request path enforces only a
per-node tolerance of 0.4 whose comment says it is "a generous starting tolerance, not calibrated", and the
persisted per-book metric counts filled nodes, not words, so it reads 1.0 on a book that delivered 38.9% of
its commissioned words. A book delivering 61% on every node passes every automated defense, forever, at full
price. The 0.6 value itself is calibrated to one incident with a margin of 0.035 and has no reader-facing
rationale. Fix: wire the floor into the worker or gate, fix the node-counting metric, and re-derive the floor
from band reading-time commitments (PL-23 already computes derived minutes).

> **Note added 2026-08-30. Largely superseded.** The reachability claim was true on 2026-08-22 and is now
> false. The story-level fill-rate floor runs on the request path at
> `generation/orchestrator.py::_with_fill_rate`, which calls `generation/skeleton.py::story_fill_rate` on every
> fill and forces `needs_review` below the floor rather than blocking (owner ruling 9.3). That wiring landed in
> `41d30909` ([#737](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/737)); the remaining request-path
> gaps closed in `9ea50b40` ([#743](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/743)). The
> workstream plan's step 2 carries the resulting enforcement map plus two corrections to this finding: the
> stale enforcement claims it cites sit in the 2026-08-22 brief, not the 2026-08-10 one, and by 2026-08-23
> both delivery measurements had a request-path counterpart, so the finding was wider than stated and is now
> closed on both halves. What still stands is the derivation half: 0.6 remains calibrated to one incident,
> and re-deriving it from band reading-time commitments is not addressed by any of that work.

### R-4. F5's perceptual half is contradicted by the programme's only rater data on it (F5, 4.3, 4.4)

The S-0 known-answer test used the D-7/D-7b pairs, exactly F5's configuration (shared structure, independently
authored decisional strata), as ground-truth distinct books. All four raters called the pair the same
adventure at scene 2 with the scale's worst distinctness score ("one book in costumes"). The brief reports
this only as an instrument failure; it is also adverse perceptual evidence against the architecture F5
licenses. The supporting deterministic evidence is one pair on a 26-node graph (catalog median about 150),
with a 473-word non-wordless residue and the deletion arm deferred, and convergence is known to triple with
graph size (D-2). Section 2's claim that no principle is aspiration is false for F5 (its end-to-end test, S-2,
is open and blocked) and partly for F8 (S-5 open). S-2's own falsifier is meanwhile preordained to fire on any
shared-armature pair given the S-0 data, so the confirmation step and the favored architecture are on a
collision course. Fix: carry the adverse reading into F5, mark it provisionally supported and decided by
S-2/S-4, and add decision-level variation mechanisms before the rater step re-runs.

### R-5. The economics half of the goal has no target, no model, and no human-minutes term (1, 4.5, F7, F8)

Section 1 says unit economics cap what a book may cost; no cap or per-book cost model exists anywhere in the
citation chain. The only business target on record (LLM plus hosting under 20% of subscription revenue,
implying roughly $1.00 to $1.60 per family per month at the stated tier) is never cited by the brief and is
arithmetically threatened by its own measurements: a 16+ fill cost $1.06 while delivering 39 to 53% of
commissioned words, and a floor-compliant 16+ fill projects to several dollars before repairs, review, covers,
or the human. The tool-assisted authoring regime recommended by 4.2 recorded zero token usage (all subagent
records carry null usage), so "zero marginal provider cost" is a billing artifact of the owner's subscription
and the recommended architecture has no measured dollar cost at all. Human time appears in no ledger: no
review-minutes-per-book measurement exists, no reviewer capacity plan exists anywhere, and at plausible
internal rates the human approval of a large book exceeds its entire LLM bill. The fresh-eyes cost review and
the repo audit converge: reviewer minutes, not tokens, are the scarce resource at scale, and the brief's cost
section prices neither them nor skeleton authoring nor covers (unmetered in code). Fix: build the unit-cost
model page the unscheduled-work register already specifies (UW-G19, test plan E5), derive and state the
per-book cap by band, shadow-price subagent legs, and instrument review minutes in the approval UI.

> **Note added 2026-08-30. Partly overtaken; the conclusion survives.** The "no target" half moved on
> 2026-08-23, when the owner **partially ruled `D3`**: the revenue anchor is a subscription at $1.99 or $4.99
> (which of the two is open), cost allocation is a credit system scaling with book length and age band, and
> **human approval minutes are costed at a notional rate rather than excluded**, which is the specific
> omission this finding was about. The workstream plan also records that the 20%-of-revenue target this
> finding referenced "remains unrecorded anywhere in the tree, and is not adopted", so that figure should not
> be quoted from here as project policy. What has not moved: Step 4, the unit-cost model page, is listed "not
> started", `UW-G19` still carries open wall-clock, retry and repair columns, and `S-6`'s reviewer-minutes
> measurement has not run (see R-11). **No per-book cost cap exists**, which was the finding, so the
> conclusion stands; what changed is that the cap now has a parameterised structure to be computed against
> instead of nothing at all.

### R-6. Safety measurement rigor lags quality rigor by an order of magnitude (F2, 3.4, 3.5, S-5)

The quality side has calibrated floors and pre-registered rows; the safety side has a 13-item adversarial
corpus with three executable passages in its most serious class and zero items for the 13-16 and 16+ bands,
exactly one live run (overall catch rate 0.667, prompt-injection class caught at 0.0, still unfixed and
unscheduled), and no register row. F2 credits the deterministic gate with "safety classification" that is an
empty Phase-2 stub in code (always returns no findings); real safety classification is an external classifier
plus an LLM reviewer, the brief's own weak class. The first-pass review model is asserted by "owner practice"
while the cited formalization plan explicitly disclaims the moderation pipeline, config still defaults to a
different vendor, and no artifact ties the named model to any catch rate. S-5, the one registered safety
experiment, is a shell-integrity floor mislabeled as a safety floor: it cites the wrong lesson IDs and omits
the tag-dishonesty defect class the programme itself documented (strict-clean shells whose valence tags
misdescribe their scenes), which is the one way a bespoke generator ships a cruel ending economy through the
current gates. Fix: run the already-built adversarial harness per band including 13-16 and 16+ and register it
with S-row discipline; repair S-5's corpus and citations before it runs; restate F2's safety sentence to match
the code.

> **Note added 2026-08-30. Fix landed; this finding's stated fix is discharged, and the measurement it asked
> for found something worse than it predicted.** Three of the factual claims above are now false on `main`.
> `docs/planning/safety/adversarial-corpus.json` is **v1.1, 25 items**, with **6 items at `13-16` and 6 at
> `16+`** (verified by parsing the file on `main`), so "zero items for the 13-16 and 16+ bands" no longer
> holds. It **has a register row**: `S-7` in [diversity-test-register.md](./diversity-test-register.md) (row
> at `:1317`, section introduced at `:1298`), pre-registered two-sided so a gate that flags everything cannot
> score 100%. And it is neither unrun nor unscheduled: `.github/workflows/safety-eval.yml` runs the corpus
> against live classifiers weekly, and two `workflow_dispatch` runs on 2026-08-24 have artifacts committed
> under `docs/planning/safety/`.
>
> **What those runs found is the part worth carrying forward, and it is not good news.** The operative run is
> the majority-of-3-draws one (`adversarial-results-2026-08-24-majority-k.json`, run 32721963326), scored
> under an owner amendment to `S-7` clause (b). It inverts both halves of the earlier single-draw run: the
> `A7-control-onband-grief-13-16` over-block did not reproduce on any draw and is **withdrawn** as sampling
> noise, while **`A9-actionable-harm-16plus` was missed on 3 of 3 draws** (`is_fail_safe: false` on every
> draw, three distinct archived `reason` strings, Wilson 95% on the adverse rate [0.44, 1.0]). Class A is
> therefore **6 of 7 (0.857)**, not the 7 of 7 the single-draw run reported. The retired single-draw scoring
> was producing a false GREEN on the catch side as well as a false RED on the control side, and only the loud
> one had been noticed. Remediation is an owner ruling on the band safety rubric, open at **`UW-C361`**
> (`AL-601`), which explicitly must not be closed by relaxing `A9`'s `expected_min_verdict` or by narrowing
> `_HARD_CATCH_CLASSES`. Class E is measured but not gated and its acceptance bar is unreconciled across three
> documents (`UW-C360`), so no class-E rate is quotable. **So: "safety measurement lags quality measurement"
> is discharged as a process claim; the underlying worry it was a proxy for is now a measured, tracked
> defect** rather than an unprobed band.

## 3. High findings

### R-7. Checkable numbers in the brief are wrong or stale

Independently recomputed by three reviewers from raw records: F3's "passed 14 of 21 at ages 5-8" is 12 of 21
(the brief's own 4.2 table sums to 12; the register propagated an arithmetic slip); "swept the harder 10-13
cell" is false (haiku 1/3, v4-pro 0/3, v4-flash 1 pass and 1 fail on record); the blind arm's "21 attempts"
was cell A only (blind cell D was descoped). Section 1's catalog is stale: the committed catalog is 84 graphs
and 15,470 nodes, not 61 and 11,458, and the "~118,000-word graph" is unsupported by any computable basis (the
677-node skeleton commissions 42,233 words; the largest commission anywhere is 49,953). Q-1's "3-4 skeletons
per cell" is also stale (production-eligible shells now run 4 to 10 per covered cell). A one-line script at
publication time would have caught all of these; adopt the rule that any count in the brief regenerates from
records.

> **Note added 2026-08-30. Fix landed, and this finding got one of its own numbers wrong.** The rule it asks
> for is implemented rather than adopted on paper: `scripts/catalog_census.py` generates
> [catalog-census.md](./catalog-census.md), which is now the single source for catalog counts, and it carries
> exactly the figures argued for above (84 shells, 15,470 nodes, the 677-node/42,233-word and
> 632-node/49,953-word superlatives). Counts cite the census; they are not hand-counted or globbed.
>
> **The correction runs the other way too.** This finding's own replacement figure, "production-eligible
> shells now run 4 to 10 per covered cell", did not survive verification and was dropped by the workstream
> plan. The census reports **3 to 5 per covered cell, median 4**. A finding about stale numbers shipping a
> stale number of its own is the same defect at one remove, which is the argument for regenerating rather than
> recomputing by hand. Whether `--check` gates the census in CI is still open as `D4`.

### R-8. S-1's per-model rankings are statistically and methodologically unsupported

The pre-registered primary endpoint was degenerate in both conditions (permutation p = 1.0 twice), the run
summary itself labels every other field "exploratory and decision-inert per register row S-1", and the plan's
multiplicity rule says exploratory endpoints cannot trigger decision rules; 4.2's consequence line triggers
three. Recomputed inference: only two contrasts separate (tool versus blind, 12/21 versus 2/21, p = 0.0025;
v4-pro 0/6 versus fable/opus 6/6, p = 0.0022); every other tier comparison at n = 3 per cell has p between
0.18 and 1.0, so "frontier Anthropic tiers converge fastest and most reliably" is unsupported against kimi at
5/6. The tool condition also ran on three different harnesses (in-session subagents with repo access versus a
manual text-JSON loop for API legs), with no committed harness, no transcripts, no snapshots, no sampling
parameters, and hand-maintained result metadata missing six cell-D entries; format and transport losses were
scored as authoring failures. The sole grader is a checker calibrated on the Claude-authored catalog, and the
passing Anthropic shells sit nearest that catalog (one pass 0.0007 above the anti-clone floor; 8 of 26 below
the hand-authored 5th percentile of in-cell distance), so the experiment partly measures resemblance to the
incumbent author. The regime-level conclusion stands; restate the tier ranking as a screen, run one costed,
transcript-committed replication before the authoring-model choice hardens, and consider one cheap ablation
(stateful session, checker withheld) before F3 is treated as mechanism rather than observation.

### R-9. The skeleton stage has no above-floor quality measure, and its bar is weaker than described

The programme's own open lessons say strict-clean does not mean approvable (three strict-clean drafts were
each rejected on human review; choice fairness and consequence are invisible to every current metric; a
measured 77% position bias has no gate). Yet S-1's only endpoint is strict pass/fail, so the structure author
was selected on gate passes the programme itself calls hollow, the exact F2 mistake one section earlier. The
authoring bar is also weaker than 3.2 claims: the anti-clone floor is not in `check_skeleton --strict` at all
(it lives in a separate audit, and CI promotion explicitly skips it for hand-authored originals); the
promotion prover invokes the checker without `--strict`, so the walk floor, reconvergence cap, ending floors,
and grammar escalations are unenforceable after merge; deletion-only skeleton PRs skip re-proving entirely;
and the no-auto-merge guard is label-gated with nothing applying the label. The drafting-brief generator
omits PL-25 and the PL-18 shape semantics, so S-1 legs were scored against unstated constraints (the plan's
own control says such failures indict the brief, not the arm). Fix: build and run the shell quality rubric
blind over the tool-passed shells versus catalog shells, add the missing rules to the generated brief with a
completeness test, enforce strict at promotion, and close the workflow holes.

> **Note added 2026-08-30. Re-verified and still true.** The promotion-CI half was checked against `main`:
> `scripts/check_promotion_bundle.py` builds its checker argv as the shell path plus, at most, `--allow-mvp`,
> then calls `check_skeleton_main(argv)`, so `--strict` is never passed. The only callers that hand `--strict`
> to `check_skeleton.py` are `scripts/compare_skeleton_authors.py` and `scripts/modal_kimi_leg.py`, both
> research rigs, plus `scripts/generate_drafting_brief.py`, which emits the flag only inside advice text for a
> human author to run. Two later independent reviews reached the same conclusion. The workstream plan gates
> this half of step 5 on owner decision D2.

### R-10. Model drift, provenance, and calibrated-constant governance are unhandled in production

All evidence was collected on pinned backends; production OpenRouter calls are unpinned (no provider-order
config exists) across a slug with 18 endpoints spanning 16k to 1M output ceilings and mixed quantization,
which reopens the truncation-burn failure the programme already paid for, and the fallback wrapper can change
the authoring model mid-book with nothing flagging it (per-stage selection, F4, has no runtime enforcement).
The served backend is never recorded, so drift cannot be attributed after the fact; there is no re-benchmark
cadence or canary for fill quality; the prompt version is one hand-bumped string covering fourteen templates
with two recorded drift precedents; and the calibrated constants the architecture leans on (gram budget 4.0,
idiom floor 3.3, fill floor 0.6) live in no committed baseline with a check. The idiom floor was measured on
three pairs, one model, one band, and never on the recommended fill model, so the V4 Pro migration invalidates
its measured basis the day it lands. Fix: config-level endpoint pinning with endpoint-aware caps, served-
backend capture in usage rows, a small scheduled canary with a drift alarm, a hash-manifest binding for the
prompt version, and a diversity-floor baseline file with a recalibration rule keyed to fill-model changes.

### R-11. The human gate is the least measured stage and the review surface ignores the research instruments

F8 makes the human the last line and S-5 judges architectures on what they ask that human to review, yet
nothing measures reviewer time, send-back rates, or rubber-stamping; no reviewer capacity or throughput
assumption exists in any planning document; and the approval surface presents a full linear read (a multi-hour
scroll for the largest books, which an internal row already says cannot deliver approval at 746 nodes) with
none of the programme's instruments (fill rate, sibling similarity, safety findings summary) surfaced to the
approver. All four fresh-eyes reviews independently identified reviewer minutes as the dominant unit cost and
the binding scale constraint under a mandatory-approval policy; the repo audit confirms the programme has
never priced it. Fix: log approval duration and send-back reasons from existing events, pipe the delivery and
sibling measurements onto the review surface, define the review-mode policy per band and size (full read
versus structured coverage), and add reviewer capacity to the framework before S-5 decides sourcing on
review-burden grounds.

> **Note added 2026-08-30. The first half of the fix landed; the conclusion survives, because the instrument
> has not run.** "Nothing measures reviewer time, send-back rates" is no longer true of the codebase:
> `src/cyo_adventure/publishing/gate_metrics.py` exists on `main`, added with `EventType.SUBMITTED` and
> migration `20260823120000` on 2026-08-23. It pairs each `submitted` event with the `released`/`sent_back`
> that follows it into review ROUNDS and reports median and p90 round duration, send-back rate over decided
> rounds, and mean rounds-to-release. It is registered as **`S-6`** in
> [diversity-test-register.md](./diversity-test-register.md) (row at `:1316`), pre-registered with a blocking
> validity gate (at least 10 decided rounds and at least one round at `round_index >= 2`) and a refutable
> expectation (median round duration under 24h, send-back rate under 0.20).
>
> **It has produced no figure.** `S-6`'s status is "registered, not yet run": neither staging nor production
> has carried the `submitted` migration long enough for the validity gate to pass, so no duration or rate may
> be quoted from it anywhere. **The finding's conclusion is therefore intact.** Nothing is yet known about
> reviewer minutes, no reviewer-capacity plan exists, and R-5's human-minutes term still has no measurement
> under it. The distinction matters for anyone citing this finding: the fix "log approval duration and
> send-back reasons from existing events" is built, and the other three fix items (surfacing fill rate,
> sibling similarity and the safety summary on the review surface; a per-band review-mode policy; reviewer
> capacity in the framework) are open work in the workstream plan.

### R-12. "Refuted" is overstated, and two capital facts are mis-summarized (4.3)

Most of the refuted list (S3, S5, S6, S7, S9, and the M-4 null) rests on recognition-style instruments later
shown broken or saturated, with the failure direction biased toward refutation; the genuinely refuted items
are the deterministic ones (S8's structural distances, the gram counts, the leak measurements). Downgrade the
rest to "not detected". Q-1 is quoted for its exhaustion half while the register's actual headline (depth is
the wrong capital; narrative contracts cover 2 of 61 skeletons and gate the only mechanism ever measured to
clear the anti-clone floor; **2 of the 61 then catalogued**, a figure now superseded, see the note below) is
dropped, and no demand model exists anywhere (requests per child per month
against skeletons or strata per cell per year; recomputation shows no-repeat depth at weekly cadence is about
14x current, roughly 1,600 review-hours per year at the register's own amortization price). Premise curation
is declared a control and remains unspecified beyond 16 frozen experiment premises: no size target, no per-cell
coverage rule, no per-child repulsion. 4.3 also asserts the mutation pilot's perceptual claim that 4.4 rules
unconfirmed two paragraphs later.

> **Note added 2026-08-30. One citable number superseded; the rest of the finding has not moved.** The "2 of
> 61 skeletons" figure above was correct when Q-2 was measured on 2026-08-11 and is stale now, in exactly the
> way R-7 is about: 61 was the catalog size on that date, and the census reports **84 shells**. The current
> value is **2 of 84** ([diversity-test-register.md](./diversity-test-register.md) `:1191`); the numerator did
> not change, the denominator did, so contract coverage got relatively worse rather than better. The register
> now dates the figure at its Q-2 row (`:1101`) so the comparison cannot be made silently again. **Everything
> else in R-12 is untouched**: the over-generous "refuted" labels on S3, S5, S6, S7, S9 and the M-4 null, the
> missing demand model, and the unspecified premise-curation control are addressed by no workstream step.
> R-12 is in fact the one finding the workstream plan does not carry at all, which it states itself, so this
> finding has no scheduled home; closing that citation gap is `UW-K21`.

### R-13. The brief omits the decision framework that would make it a decision document (5, 4.2)

The pre-registered decision rules R1 through R7, their blocking graph (S-2 blocked on S-0 and S-1; S-4 on S-0;
S-5 accounting on S-1 through S-4), the programme budget cap, and the scope carve-outs (gamebook cells, the
3-5 band, and series books stay on the catalog path regardless of outcome) never reach the brief, and 4.2's
"consequence for the product" lines read as decisions although the test plan explicitly defers the wiring
("deliberately out of scope until the decision framework has an answer") and no ADR records them. Results
measured on two short-form cells are stated without the plan's own scope exclusions, while section 1
headlines the excluded tail. The "two cheapest quality levers" claim is asserted without comparison against
the one-command directive-delta measurement the register calls commercially load-bearing. Fix: reproduce the
rules table and blocking graph in section 5, tag every consequence line as proposal or decision with an owner,
and add the scope sentence to 4.2.

### R-14. Accepted adjacent programmes and live loops are never composed with this framework

Personalization slots (ADR-023, in implementation) and persistent reader characters (ADR-028, production
modules) operate on the same prose layer this framework measures, yet neither appears in the brief, register,
or test plan: persistent per-child casts push a child's books toward sameness exactly where S-4 measures
distinctness (arms do not state whether casts are held constant), and sentinel or recurring-character prose
loads the shared-gram counts. The post-publication loop (kid flags, rescreen, remoderate, thresholds) exists
in code but is invisible to the research programme: no flag-to-calibration feedback, no rescreen trigger on
threshold writes, no SLA. Provider risk is unassessed at the policy level: no ToS or output-licensing analysis
for DeepSeek or Moonshot outputs in a commercial children's product, no deprecation watch, and the recommended
assignment concentrates fill and first-pass review in one vendor against ADR-010's own independence rationale.

## 4. Medium and low findings (condensed)

- Path-level coherence is unmeasured: the continuity and consequence validators are self-declared non-gates,
  chunked fills have zero repair budget and contractually differ from one-shot fills, and a gate-passing book
  asserts state a reachable path never established. The two cheap proposed detectors (outbound choice-grammar
  companion, duplicate-body and POV checks) are unbuilt. The fidelity judge defaults to the model that wrote
  the fill, reviewing itself.
- The reading-level gate is a Flesch-Kincaid variant, advisory-only, with a validated syllable counter but no
  known-answer fixtures of band-leveled children's texts, one recorded Goodharting incident, and an in-band
  metric confounded with fill rate (a hollow book conforms by accident); the vendor comparison's in-band axis
  inherits this.
- Reproducibility holes: no sampling parameters or harness git SHA recorded anywhere; three merged evidence
  rigs pre-registered against books that were never committed; cell D results published only in the brief
  while the register still says the cell is open; several lesson-log IDs cited by the brief and code point at
  the wrong lessons after a renumbering (the drift lesson and the provenance lessons live at different IDs).
- 4.5's per-leg dollar figures have no committed artifact (owner billing prose, not "deterministic accounting
  from run records"), "credits checks" names a guard that does not exist, and the premium-slate comparison is
  not the same grid. F7's lever list omits measured levers: prompt caching (44% and 30% cache-served rates are
  already in the vendor README, with a warning the brief drops), reasoning-share as a selection rule (their
  cleanest cost discriminator), batch APIs for offline catalog work, and chunk-size economics.
- Terminology: three colliding S-namespaces (design-history levers S0-S9, sourcing arms S0/S2/S3, register
  rows S-0..S-5) and undefined terms at first use invite exactly the misreading a decision document exists to
  prevent. Selection is "weighted toward least recently used", not guaranteed LRU; the parameterize script
  applies a slotting plan rather than emitting the contract.

## 5. Fresh-eyes blind-spot analysis

The four goal-only agents were asked to specify the ideal programme without seeing this one. Where their
must-haves match what the repo-grounded reviewers found missing everywhere (brief and companions), the gap is
programme-wide rather than a summarization choice. The recurring themes, roughly ordered by leverage:

1. The human review system as a measured instrument: review-mode policy per band and size, seeded-defect
   catch rate for reviewers, inter-rater agreement, time floors against rubber-stamping, per-node rejection
   feeding repair, and reviewer capacity math. The programme measures everything except its last line of
   defense.
2. Unit-economics discipline: fully loaded cost per published book by band and size class, funnel and yield
   accounting with a scrap multiplier, dispersion targets (predictability is a tail metric), a waste ledger,
   per-book circuit breakers in the production path, and shadow pricing for subsidized capacity.
3. An escape-rate north star: severity-weighted post-approval defects per published books, with every escape
   root-caused to the gate that should have caught it and converted into a seeded regression case. The flags
   and rescreen machinery exists in code; the feedback loop into gates and priorities does not.
4. Instrument governance: a metric registry with owners and expiry dates, seeded-defect (mutation) testing of
   every gate including the human one, shadow mode before a gate arms, gameability audits, judge drift
   canaries that freeze judge-gated decisions, and periodic gate ROI ablation.
5. Kid ground truth: no child or human has rated any book; all perceptual numbers are same-family LLM raters.
   A standing family panel, fear calibration to the sensitive quartile, comprehension probes, and an
   adult-or-model versus kid correlation audit are the missing calibration layer, with proxies retired when
   their correlation is weak.
6. Choice and agency quality measures: label-outcome calibration, fake-choice and dominated-choice rates, an
   incentive-matrix audit (antisocial choices must not systematically win at young bands), a foreshadowing
   gate for failure endings, second-read novelty, position-bias monitoring (a 77% bias is already measured and
   ungated), and junction-pair coverage with gates binding on the worst reachable path, not the average.
7. Model lifecycle management: champion-challenger shadow runs, recipe versioning (model snapshot, prompt
   hash, params, thresholds as one promotable unit), one-change-at-a-time attribution, a deprecation calendar,
   and recalibration triggers on any scorer or generator change.
8. A per-book evidence bundle: every published book carries its full lineage (model snapshots, prompt hashes,
   gate versions, thresholds in effect, approver identity bound to the artifact hash) so any incident is
   answerable from the record alone. The job ledger is a strong start; stage attribution, covers, and two
   provider families are missing from it.
9. Cost-shaped generation choices: bounded per-node context for the long tail (linear versus quadratic cost),
   caching-aware prompt layout, batch-tier scheduling for all offline work, cover art generated after
   approval, and early-abort prediction to move scrap left.
10. Alternatives analysis for structure: the brief frames structure as constraint satisfaction (F1) yet never
    evaluates procedural or grammar-based graph sampling as the skeleton factory, with the LLM confined to
    prose and beats. Given R-8's harness caveats and R-9's missing quality measure, correctness-by-construction
    plus checker-validated sampling is the natural challenger to tool-assisted LLM authoring, and nothing in
    the record rules it in or out.

## 6. What the brief and programme do well

- Falsifier-first culture that actually bites: pre-registered margins, declared deviations, instrument
  failures reported as headlines (D-3's inversion, S-0 recorded as FAILED by its own rule), and retractions
  with re-derivations (the fp4 headline, the 62% attribution).
- The deterministic layer is real science: committed artifacts and re-runnable scoring; reviewers
  independently reproduced the S-1 pass table, the blind counts, the 4.5 premium-leg dollar totals, and the
  sibling-gram figures from raw records.
- The gates-are-floors insight (F2) and the lesson-to-tooling loop are genuinely operating: the fill-rate hole
  was found, measured, and answered with a calibrated floor within days, and the evidence-class taxonomy keeps
  most claims honest about their support.
- The accounting and metering code is engineered for honest failure (unreported-versus-zero token semantics,
  lower-bound flags, billed-leg attribution, reconciliation within 2% of provider billing).

## 7. Recommended sequence

Cheapest first, and compared against the brief's own claim that the recognition-instrument repair and the
PL-18 message fix are the two cheapest quality levers. This review demotes both: the PL-18 fix is real but is
a convergence-cost lever, and the recognition repair as scoped validates the wrong discrimination (cross-band
cues) while re-importing the armature confound. Higher-leverage items at comparable or lower cost:

1. Documentation pass on the brief itself (hours): correct R-1's restatement, R-7's numbers, the wiring-status
   language (3.2, 3.4), the safety-stub sentence (F2), rater provenance ("all raters are LLM sessions; no
   child has read any book"), the 4.2 scope sentence, and tag consequence lines as proposals. Add "owner
   practice" as an explicit non-evidence label.
2. Wire the floors (days): fill-rate 0.6 into the worker or gate; sibling-gram check for same-skeleton fills;
   surface both plus safety summaries on the approval screen; per-family reuse cap in selection.
3. Run the cheap, blocked measurements (days, small spend): the directive-delta at production TREE settings;
   the adversarial safety harness per band including 13-16 and 16+, registered with S-row discipline; approval
   duration and send-back logging.
4. Economics spine (days): the unit-cost model page per UW-G19 and E5 with a stated per-book cap by band
   derived from the 20%-of-revenue target; shadow-price the subagent legs; meter covers; price the anthropic
   and modal providers; endpoint pinning plus a credits preflight and a daily spend counter.
5. Constant and provenance governance (days): diversity-floor baseline with a recalibration rule keyed to
   fill-model changes; TAU_CELL loader unification; strict enforcement in the promotion prover plus the
   deletion and label workflow holes; prompt-version hash manifest; run-record schema (git SHA, sampling
   params, relative paths).
6. Before F3/F4 harden (a week, priced): one costed, transcript-committed tool-assisted replication including
   an Anthropic API leg and re-run DeepSeek cells on the same harness; the shell quality rubric run blind over
   tool-passed versus catalog shells; the stateful-without-checker ablation; repair S-5's corpus and citations.
7. Instrument the defect that matters (longer): the declared operation and stake schema field as the
   deterministic decision-level measure; the premise-pool design sized from a one-page demand model; a
   same-band non-mystery control before recognition re-validation; S-4 margins re-derived (include the first
   actual repeat pair, not only adjacent pairs).

## 8. Review provenance and limits

Thirteen agents ran on 2026-08-22: fresh-eyes evaluation methodology, cost, editorial QA, and architecture
(no access to the brief); rigor, claim verification, framework coherence, and testing/reproducibility (whole
brief plus companions plus code); and skeleton, fill, diversity and instruments, cost, and safety/human-gate
deep dives. All nine repo-grounded agents were interrupted once by an account usage limit and resumed with
context intact; all thirteen completed. Numbers quoted here were recomputed from committed artifacts on the
research branch by at least one agent, and the load-bearing ones (R-1's panel scores, R-7's recounts, R-8's
tests) by two to four agents independently with agreeing values. Limits: agents did not run any paid model
calls, so claims about unrun measurements are about their absence, not their outcome; branch-only artifacts
were read at commit `01b7119` of `claude/model-selection-skeleton-dev-78yp7u`; and where a later artifact
exists outside that branch this review cannot see it. Two companion files were copied onto the review branch
to support the review, the brief itself and
[skeleton-sourcing-test-plan-2026-08-21.md](./skeleton-sourcing-test-plan-2026-08-21.md), which the brief links
and the strict docs build requires. Neither copy is carried here: `main` already holds both at those paths and
both have since taken corrections this review predates, so the links above resolve to the current text rather
than to the 2026-08-22 snapshots the agents read. The thirteen full agent reports behind this synthesis are
preserved in `evidence/brief-review-2026-08-22/` (excluded from the docs build, like the other evidence
directories).
