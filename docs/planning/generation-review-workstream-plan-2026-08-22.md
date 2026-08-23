---
title: "Generation Research Review: Workstream Plan"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Gives a phase home to the thirteen-agent review of the 2026-08-22 generation research brief: every confirmed finding traced to a step with acceptance criteria, stopping at four owner decisions."
tags:
  - planning
  - generation
  - measurement
component: Development-Tools
---

# Generation research review: workstream plan

Date: 2026-08-22, corrected 2026-08-23. Status: step 1 complete. Step 2 executed, with one fix
shipped (`41d30909`) and the rest carried by two open PRs,
[#742](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/742) (convergence reporting and the
series prose-reuse gate) and [#743](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/743) (the
remaining request-path gaps, plus dating the catalog counts). Step 3's INSTRUMENTS are built on
branch `feat/step3-safety-approval-measurement`: R-11's gate-entry event and
`publishing/gate_metrics.py`, and R-6's corpus extension to the `13-16` and `16+` bands. Both
measurements are registered as `S-6` and `S-7` in the
[diversity test register](./diversity-test-register.md) with their falsifiers fixed before either
ran. NEITHER MEASUREMENT HAS RUN: S-6 waits on the `submitted` migration reaching an environment and
accumulating enough rounds to pass its validity gate, and S-7's first measurement is the next scheduled
`safety-eval.yml` run after this merges (see the correction under Step 3). No result from either may be quoted until its artifact is committed. Steps 4
to 7 not started. This plan
gives a phase home to the 14 critical and high findings, the five condensed medium and low bundles,
and the seven-step sequence produced by the thirteen-agent review of the 2026-08-22 generation
research brief.

**Citation note.** The `R-*` IDs used throughout are the review's own numbering. That review's
artifact is not committed, so no `R-*` ID in this document resolves to anything in the tree; the
findings are traceable only through this plan's restatements of them. `R-12` is not carried here at
all, so this document covers 13 of the 14 findings it claims. Committing the artifact, and closing
the citation gap that let this through, is `UW-K21`.

**Owner question this plan answers:** the review concluded that the programme underneath the brief
is sound and that the brief itself is not yet trustworthy as a decision document. Which of its
recommendations are engineering we can schedule, and which are rulings only the owner can
make? This plan separates the two and refuses to plan past a ruling.

**What this plan does not do.** It does not make the four decisions in section 3. Each is written
with its measured inputs and its options, and then stops. Nothing downstream of an unmade decision
is planned in detail here, because planning it would require assuming an answer, and the review's
own headline failure was a consequence line hardening into policy before the evidence under it was
checked.

---

## 1. Where the evidence stands

The review's numbered findings are the input. Two of them were themselves wrong in the direction
that matters, which is why step 1 came first in the review's sequence and why it was executed
before this plan was written:

- **R-1 (fill-model claim inverts the evidence)** was confirmed and corrected. The brief called
  DeepSeek V4 Pro "the best prose model measured" and derived "fill with V4 Pro" from it. On the
  blind panel V4 Pro is fifth of eight at -0.13 z; what it holds is the lowest cost per
  delivered book at $0.0398. Section 4.2's line is now labelled a proposal rather than a recorded
  decision, and the fill assignment is re-opened as decision **D1** below.
- **R-7 (checkable numbers are wrong or stale)** was confirmed, and was larger than the review
  found. The review flagged the brief; the same figures had been hand-copied into roughly 40 other
  sites. "61 graphs and 11,458 nodes" was exactly correct at commit `154d44f` on 2026-08-12 and had
  decayed to 84 shells and 15,470 nodes by the time the brief quoted it. Every copy agreed with
  every other copy, so nothing flagged it.

Two of the review's own numbers did not survive verification and were dropped rather than published:
its "4 to 10 skeletons per covered cell" figure, and a `fill_completeness` claim that appears
nowhere under `src/`. Treat the review as high-quality input, not as an oracle.

**Step 1 is complete** (PRs #738 and #740). It covered R-1's restatement, R-7's numbers, the
wiring-status language in sections 3.2 and 3.4, the F2 safety-stub sentence, the section 4.2 scope
sentence, tagging consequence lines as proposals, and the "owner practice" non-evidence label. It
also produced `scripts/catalog_census.py`, so the census itself is generated rather than hand-copied.
That removes transcription drift at the source but not label drift, where a document quotes the
census by hand or pairs a figure with the wrong label: `AL-551` records that where each document
cites it from stays open under `UW-G24`, and `AL-557` records the label half specifically. Two
residuals are carried into step 1r below.

---

## 2. Steps, findings, and acceptance criteria

Ordering is the review's, cheapest first. The review explicitly demoted the two levers the brief
called cheapest (the recognition-instrument repair and the PL-18 message fix) on the grounds that
the recognition repair as scoped validates the wrong discrimination and re-imports the armature
confound. This plan keeps that demotion.

### Step 1r. Documentation residual (hours, unblocked)

| Finding | Work |
| --- | --- |
| R-7 residual | State plainly in the brief's evidence-class preamble that every rater to date is an LLM session and no child has read any book. The preamble names "blind LLM raters, the weak class" but never says the second half, which is the part a reader assumes rather than checks. |
| Medium: terminology | Disambiguate the three colliding S-namespaces (design-history levers `S0`-`S9`, sourcing arms `S0`/`S2`/`S3`, register rows `S-0`..`S-5`). Correct "guaranteed LRU" to "weighted toward least recently used" and the parameterize script's description (it applies a slotting plan, it does not emit the contract). |
| `UW-G24` "date it" bucket | The ADR-011/023/025/026 measurement passages, the dated review and handoff documents, and the `AL` rows. These record what a procedure returned on a date and must be dated, not rewritten. |
| R-3 residual | The brief still describes the fill-rate floor as unwired at `cyo-generation-research-brief-2026-08-10.md:70` and `:196-202`. `41d30909` wired it after PR #738 landed, so step 1's correction pass predates the fix and missed it. |
| `UW-G24` judgement calls | Four sites where prose quotes a catalog count while the code iterates the live catalog: `tests/unit/test_policy.py:1910`, `tests/unit/test_analyze_sibling_exposure.py:814`, `tests/unit/test_orchestrator.py:1024`, and `scripts/check_skeleton.py:92` ("40 of 61 skeletons", an advisory-incidence claim never re-measured against the 84-shell catalog). |

**Acceptance:** no site in the tree asserts a catalog figure as current state without either citing
the census or carrying its measurement date; each figure is paired with the label the census uses
for that quantity; the three S-namespaces are disambiguated in the brief's glossary; and the brief's
evidence-class preamble states that no child has read any book. `UW-G24`'s citation-sites bucket
closes. Its gate-outcome bucket stays open under D4, so `UW-G24` itself does not close here.

### Step 2. Wire the floors (days, unblocked)

The review's R-3 finding is that the delivery floors exist only where nobody ships from. The
reachability half is confirmed and is sharper than the brief admits: `check_fill_integrity.py` and
`check_sibling_fills.py` are reachable from `run_guard_battery.py`, a hand-run harness that no
workflow or hook references, and from one other non-request-path site
(`scripts/compare_vendors.py:1274` imports `pairwise_shared_grams`). CI does load the harness module
(`tests/unit/test_guard_gating.py:53-59` `exec_module`s it to assert its registrations) but never
runs the battery over a book.

**Correction, 2026-08-22.** The inference drawn from that, that the fill-rate floor is therefore
unenforced at request time, is false, and this plan asserted it before checking. Executing the step
produced an enforcement map instead: every blocking check in `check_fill_integrity.py` already has a
request-path enforcer.

| `check_fill_integrity.py` blocking check | Request-path enforcer |
| --- | --- |
| Leftover `<<FILL ...>>` directives | `fidelity_gate.run_stage1_gate` via `has_unfilled_directives` (`generation/skeleton.py:693-703`), which scans node bodies only. Choice labels are covered by validator rule **PL-27** `check_fill_residue` (`validator/policy.py:104`), and storybook and ending titles by `check_fill_integrity.py:454-455`'s whole-document marker scan. All 15,470 committed directives sit at `/nodes/[]/body`, so the narrower coverage is latent, not live. |
| Structure preserved against the skeleton | `fidelity_gate.run_stage1_gate` via `structure_violations` |
| Band per-node word maximum (`words_per_node_profile`) | Validator rule **PL-19** (`validator/policy.py::_check_words_per_node`) at `Severity.ERROR` |
| Story-level fill rate >= 0.6 | `orchestrator._with_fill_rate`, shipped by PR [#737](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/737) (`41d30909`), committed the same day this plan was written |

The last row is moot on today's catalog, but not by construction, and the first draft of this plan
overclaimed it. `word_count_violations` does admit a node only within `[0.6 * target, 1.4 * target]`
(`_WORD_COUNT_TOLERANCE = 0.4`, `generation/fidelity.py:159-161`, bounds inclusive). The arithmetic
step does not follow from that, because the per-node check and the story-level sum do not range over
the same nodes: `commissioned_words_by_node` matches loosely with
`re.findall(r"words\s*=\s*(\d+)")` (`generation/skeleton.py:577`), while the per-node check uses a
strict anchored grammar and skips any body it cannot parse (`generation/fidelity.py:148-149`). The
codebase records that divergence as deliberate (`generation/skeleton.py:561-572`). Demonstrated by
execution: a directive written `words = 100` with a space, or carrying trailing prose, or on a node
with a non-`str` id, passes every fidelity check and yields a story fill rate of 0.02.

All 15,470 committed bodies across the 84 shells parse under the strict grammar, so the floor cannot
fire today. That is a fact about the catalog, not about the code, and one newly authored or mutated
shell can break it silently. The genuinely load-bearing step is also not the arithmetic:
`orchestrator.py:1774` downgrades to `needs_review` on any Stage 1 violation before
`_with_fill_rate` evaluates its own floor at `orchestrator.py:1376`. Wiring the floor was a no-op on
this catalog; it was not a provable one.

What the step found is recorded as `AL-562` and is implemented on branch
`fix/stage1-persist-signal-coupling`, carried by open PR
[#742](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/742): the persist gate that lets a
clean-downgraded fill reach a human keyed on a report-dict key that
`worker._regate_after_transform` replaces wholesale, so a downgraded fill whose document the
reinsertion transform rewrote would have been dropped with no `Storybook`, no `StorybookVersion`,
and no moderation run. It is dormant only until ADR-023 D4 lands a contract that declares a
personalizable slot.

Two corrections to how that was first written here. The lesson is `AL-562`, not `AL-551`: rebasing
the branch onto `f6adbc67` renumbered its rows to `AL-562`..`AL-568`, and `AL-551` is the unrelated
hand-copied-count lesson from PR #738. The citation is a forward reference until #742 merges. And
the fix is not on `main`: on that branch the signal rides `GenerationOutcome.clean_downgrade`, a
typed field every rebuild carries forward, but on `main` `GenerationOutcome` has no such field and
the value is still a local variable read from the report dict at `worker.py:1473-1476`. The defect
is live until #742 merges.

The general lesson, which applies to the rest of this step: "the constant lives in a script" is
evidence about that script, not about the request path. Confirm the absence of an enforcer before
scheduling work to add one.

| Finding | Work |
| --- | --- |
| R-3 | ~~Move the fill-rate 0.6 floor into the generation worker or the validator gate.~~ **Done and moot, see the correction above.** ~~Wire the sibling-gram check for same-skeleton fills; that half stands, and it is the only fill-integrity measure with no request-path enforcer.~~ **Also superseded, 2026-08-23.** Open PR [#742](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/742) adds `_sibling_gram_findings` to `moderation/leaf_diversity.py` on the request path (`SIBLING_GRAM_ADVISORY_PER_1000 = 60.0`, `Verdict.ADVISORY`) plus validator rule `SR-10` in `validator/series.py` at `ERROR`, enforced through `publishing/service.py::approve`. The "only measure with no enforcer" claim was wrong twice over: `check_fill_integrity.py:454-455` already scanned the whole document. Remaining work here is the acceptance citation, not new code. |
| R-2 (partial) | Surface fill-rate, sibling-gram, and the safety summary on the approval screen, so the human gate sees what the automated gate measured. |
| Medium: path coherence | Build the two cheap proposed detectors: the outbound choice-grammar companion, and the duplicate-body plus POV checks. Give chunked fills a repair budget; today they have zero and differ contractually from one-shot fills. |
| Medium: fidelity judge | Stop defaulting the fidelity judge to the model that wrote the fill. It currently reviews itself. |
| Selection | Per-family reuse cap in selection. |
| `UW-C338` | Adopt the convention that any doc claim a check "enforces" or "gates" something names its invoker (workflow file, hook id, or call site under `src/`), so this class of claim is falsifiable next time. |

**Acceptance:** every floor the brief describes as a pipeline defense has a named invoker on the
request path, and a test that fails when the invoker is removed. Where the enforcer already exists
under a different name, the acceptance is the citation, not new code. The approval screen renders
fill-rate, sibling-gram and safety-summary values drawn from the same fields the automated gate
wrote. Each new detector fires on a known-positive fixture and stays silent on a known-negative one.
Chunked fills carry a non-zero repair budget stated in the same place one-shot fills state theirs.
The fidelity judge's model is asserted by test to differ from the fill model. `UW-C105`, `UW-C147`,
`UW-C315` and `UW-C338` close.

**Dependency note:** the fidelity-judge item touches which model reviews a fill, and is adjacent to
D1 but not gated by it. "Not the model that wrote it" is correct under any fill assignment.

### Step 3. Run the cheap blocked measurements (days, small spend, unblocked)

| Finding | Work |
| --- | --- |
| R-6 | Adversarial safety harness per band, including 13-16 and 16+, registered with `S`-row discipline. The review's finding is that safety measurement lags quality measurement by an order of magnitude; this is the cheapest way to close the gap. Note the F2 correction: the safety seam runs but its body is a Phase-2 no-op, so `safety_flagged` is structurally always `False`. The harness must not treat that field as a signal. |
| R-11 | Log approval duration and send-backs. The human gate is currently the least measured stage in the pipeline. |
| Directive delta | Re-run at production `TREE` settings rather than the pilot settings. |

**Correction (2026-08-23) to this step's "small spend" framing.** R-6 needs no spend
decision and no new run to be commissioned. `.github/workflows/safety-eval.yml` has
run the adversarial corpus against live classifiers every Sunday at 04:00 UTC since
at least 2026-07-26 on existing repo secrets, gating on the acceptance thresholds in
`tests/llm_eval/test_adversarial_safety_eval.py`. It picks up whatever the corpus
contains, so extending the corpus IS commissioning the measurement; the marginal
cost is a handful of extra calls inside a job that already runs. What those green
runs never covered is the point: with no items at `13-16` or `16+`, every one of
them measured four of the six bands, so "the safety eval is green" was never the
same claim as "the gate holds at every band".

A second constraint this step must respect, learned from the gate rather than the
doc: `classify_item` scores an `expected_min_verdict` of `block` as MISSED when the
pipeline merely FLAGS, and a class-A miss is a hard assertion. Setting an
expectation above the documented route-to-human threshold turns a safe outcome into
a red weekly run and a filed tracking issue, so a predicted bright-line block
belongs in the item's rationale and the archived results, never in its expectation.

**Acceptance:** each measurement is registered as an `S`-row with its falsifier declared before it
runs, and its artifact is committed. No result is reported that the register does not carry, and no
harness reads `safety_flagged` as a signal while `validator/safety.py::check_safety` remains a
Phase-2 stub.

### Step 4. Economics spine (days, gated by D3)

R-5: the economics half of the goal has no target, no unit-cost model, and no human-minutes term.
The human minutes will dominate cost at scale, and nothing currently accounts for them.

| Finding | Work |
| --- | --- |
| R-5 | Unit-cost model page per `UW-G19` and `E5`, with a stated per-book cap by band. **The cap derives from a revenue target that does not exist yet: see D3.** |
| R-5 | Shadow-price the subagent legs; meter covers; price the Anthropic and Modal providers. **ADR-003 caveat:** the ADR prefers OpenRouter independent of price, so a pricing result cannot by itself re-route a leg; treat this as input to D1, not as a routing decision. |
| Medium: 4.5 artifacts | The per-leg dollar figures have no committed artifact; they are owner billing prose, not deterministic accounting from run records. Either commit the accounting or relabel the figures. |
| Medium: "credits checks" | The brief names a guard that does not exist. Build the endpoint pinning, credits preflight, and daily spend counter, or remove the claim. |
| Medium: F7 levers | F7's lever list omits measured levers already in the vendor README: prompt caching (44% and 30% cache-served rates, with a warning the brief drops), reasoning-share as a selection rule, batch APIs for offline catalog work, and chunk-size economics. |

The reasoning-share lever is worth promoting: LLM cost on this programme tracks reasoning, not
output length. Measured spans were 1.36x on prose against 8.8x on cost; cost buys in-band compliance
weakly (Spearman +0.64) and buys diversity not at all (rho -0.11). That is the programme's cleanest
cost discriminator and it is currently absent from the brief.

**Acceptance:** a per-book cost ceiling by band exists, is derived from a stated revenue
assumption, includes a human-minutes term, and every leg price traces to a committed run record. The
4.5 per-leg figures are either backed by that accounting or relabelled as owner billing prose. The
credits guard the brief names either exists with a named call site or the claim is removed. F7's
lever list carries the four measured levers, including the cache-rate warning the brief drops.

### Step 5. Constant and provenance governance (days, partly gated by D2)

| Finding | Work |
| --- | --- |
| R-10 | Diversity-floor baseline with a recalibration rule keyed to fill-model changes. Unify the `TAU_CELL` loader. Prompt-version hash manifest. Run-record schema carrying git SHA, sampling parameters, and relative paths. |
| R-9 (partial) | Strict enforcement in the promotion prover, plus the deletion and label workflow holes. **Gated by D2.** |
| Medium: reproducibility | No sampling parameters or harness git SHA are recorded anywhere. Three merged evidence rigs are pre-registered against books never committed. Cell D results are published only in the brief while the register still says the cell is open. Several lesson-log IDs cited by the brief and by code point at the wrong lessons after a renumbering. |

**Acceptance:** a stranger can re-run any published result from the committed artifact alone: git
SHA, sampling parameters and relative paths are in every run record, and the books the three merged
evidence rigs pre-register against are committed. Every calibrated constant has one loader and a
recalibration trigger keyed to fill-model changes. Cell D's register row matches what the brief
publishes. No `AL` citation in the brief, in this plan, or in code resolves to the wrong row, and a
check enforces that rather than leaving it to review (`UW-K21`).

### Step 6. Harden F3 and F4 (about a week, priced, partly gated by D1)

| Finding | Work |
| --- | --- |
| R-8 | S-1's per-model rankings are statistically and methodologically unsupported. One costed, transcript-committed tool-assisted replication, including an Anthropic API leg, and re-run the DeepSeek cells on the same harness. **ADR-003 caveat:** exercising a direct Anthropic leg for measurement does not amend the ADR's OpenRouter preference; any routing consequence is D1's to rule on. |
| R-9 | The skeleton stage has no above-floor quality measure. Run the shell quality rubric blind over tool-passed versus catalog shells. |
| R-1 | The stateful-without-checker ablation. |
| S-5 | Repair its corpus and citations. |

**Acceptance:** every per-model claim in section 4.2 traces to a committed transcript from a single
harness, and the ranking survives a stated statistical test rather than a count of passes. The shell
quality rubric returns a scored comparison of tool-passed against catalog shells, the
stateful-without-checker ablation reports an effect with its confidence interval, and S-5's corpus
and citations resolve.

**Gating note:** only the R-8 replication is gated by D1, because the fill assignment determines
which cells are worth re-running. The R-9 rubric, the R-1 ablation and the S-5 repair are
D1-independent and can start now.

### Step 7. Instrument the defect that matters (longer, gated by D1 and by step 3)

R-2 is the review's most serious structural finding: the flagship defect has no working detector,
and production is unguarded at the decision level.

| Finding | Work |
| --- | --- |
| R-2 | A declared operation-and-stake schema field as the deterministic, decision-level measure. |
| R-13 | The premise-pool design, sized from a one-page demand model. The brief omits the decision framework that would make it a decision document. |
| R-4 | A same-band non-mystery control before any recognition re-validation. F5's perceptual half is contradicted by the programme's only rater data: on 2026-08-21 both raters called a cross-graph pair the same adventure, partly because the control was wrong. |
| R-4 | S-4 margins re-derived, including the first actual repeat pair rather than only adjacent pairs. |
| R-14 | Compose this framework with the accepted adjacent programmes and live loops it currently ignores. |

**Acceptance:** the defect the brief names as the one that matters has a detector that fires on a
known-positive fixture and does not fire on a known-negative one, and it runs at the decision level
in production. The premise pool is sized from a committed demand model. S-4's margins are re-derived
over at least one true repeat pair, against a same-band non-mystery control. R-14's composition
names each adjacent programme and live loop it reconciles with.

---

## 3. Decisions this plan stops at

Each decision below carries what has been measured for it. None is made here.

### D1. Which leg fills

**Blocks:** steps 6 and 7, and the unit-cost model in step 4.

The brief's "fill with V4 Pro" was derived from a superlative that describes cost, not quality. The
priced trade, from the 2026-08-10 brief, is explicit: `xai-grok-4.6` costs 4.9x more for 0.74 of
judged quality. In per-book terms that is $0.0398 against $0.1963 for +0.74 z and +0.14 in-band.

The complication is that this decision and step 6 are mutually entangled: R-8 says the per-model
rankings that would inform the decision are themselves unsupported. Two coherent orders exist.
Either rule provisionally now and let step 6's replication confirm or overturn it, or run step 6
first and rule on its output, accepting that the fill stage stays unassigned for about a week.

**Tracked by:** `UW-C339`, `AL-555`.

### D2. Is the strict bar the production bar

**Blocks:** the R-9 half of step 5.

This was re-measured on 2026-08-22 by running `check_skeleton.py` over all 84 shells with and
without `--strict`, and the measurement changes the question.

| | Result |
| --- | --- |
| Pass `--strict` | 20 of 84 shells |
| Would be retired | 54 of 74 reachable in an offered cell, **73%** (the register said 97%) |
| Fail *without* `--strict` | 3 of 84, all already `production_eligible: false` |

Two findings sharpen it. First, the gate promotion runs is not in question: nothing a request can
reach fails it today. Second, **the entire delta is the `CG-*` grammar family**, which `--strict`
promotes from advisory to blocking. Of the 54 reachable shells strict would reject, 21 fail on
`CG-*` alone and 33 on `CG-*` plus something structural, and **none fail on structural grounds
alone**. All 20 `--strict` passers sit inside the 74-shell reachable set, which is what fixes the
split at 21 + 33 = 54.

`CG-3`'s words-per-stop ceiling accounts for 1,785 of the findings by itself within that retired
set, and 1,965 across all 84 shells (re-measured 2026-08-23; an earlier figure of 1,557 here
reconciled under neither scoping). The full strict-blocking breakdown across 84 shells is CG-1 80,
CG-2 344, CG-3 1,965, PL-23 31, PL-24 30, PL-26 6, plus 11 walk-floor, 7 reconvergence and 1
endings-floor failures.

The ruling therefore narrows to whether `CG-3`'s words-per-stop ceiling is calibrated for the
catalog we ship, rather than to the strict bar as a whole. The structural floors that `--strict`
adds reject nothing independently.

**Tracked by:** `UW-C116`, `UW-C158`.

### D3. The economics target

**Blocks:** step 4 entirely.

A per-book cost cap by band cannot be derived without a revenue assumption. The review references a
20%-of-revenue target; that target is not recorded anywhere in the tree. This decision needs a
number from the owner, plus a position on whether human approval minutes are costed at a notional
rate or excluded with that exclusion stated.

**Tracked by:** `UW-G19`, `E5`.

### D4. Where documents cite the census, and whether `--check` gates

**Blocks:** whether step 1 stays fixed.

`scripts/catalog_census.py --check` reports staleness against the committed
`docs/planning/catalog-census.md`.

**Correction, 2026-08-23.** This plan first said `--check` is deliberately wired to neither
pre-commit nor CI, and that not wiring it accepts an advisory census. The CI half is false. A stale
census is already a build failure today, by a different route:
`tests/unit/test_catalog_census.py::test_generated_doc_is_current` asserts
`GENERATED_DOC.read_text(...) == render(census())`, the same comparison `main(["--check"])` performs
at `scripts/catalog_census.py:442`. It carries no marker, and `.github/workflows/ci.yml` selects
`-m "unit or not (integration or security or slow)"`, so it runs on every pull request. Verified by
appending `STALE` to the census doc: `1 failed, 15 passed`.

What is genuinely open is narrower: whether to add a pre-commit hook as well, trading commit speed
against catching the drift one step earlier than CI does. The census is not advisory.

A related gap has no owner yet: **gate outcomes decay exactly like counts and have no emitter at
all.** D2's own inputs are the evidence. "The strict bar passes 2 of 61" had drifted to 20 of 84,
and its cost from 97% to 73%, which is a 24-point error in the input to an open decision. The
census covers what the catalog *is*; nothing covers what a gate *would say about it*.

**Tracked by:** `UW-G24`.

---

## 4. What can start immediately

Steps 1r, 2 and 3 are unblocked and account for the majority of the review's confirmed findings,
including its most serious wiring finding (R-3) and the safety-measurement gap (R-6). Step 5 can
start on everything except its R-9 half.

Steps 4, 6 and 7 are blocked on D3, D1, and D1 respectively.

The review's own judgement is worth restating as the reason for this ordering: "the expensive risk
is letting section 4.2's consequence lines harden into production policy before the corrections
land." Two of those lines are now labelled proposals and one of them, the fill assignment, is D1.
