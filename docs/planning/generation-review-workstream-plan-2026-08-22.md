# Generation research review: workstream plan

Date: 2026-08-22. Status: drafted, no step started beyond step 1. This plan gives a phase home to
the 14 critical and high findings, the five condensed medium and low bundles, and the seven-step
sequence produced by the thirteen-agent review of the 2026-08-22 generation research brief. Step 1
is already complete and is recorded here for traceability, not as work.

**Owner question this plan answers:** the review concluded that the programme underneath the brief
is sound and that the brief itself is not yet trustworthy as a decision document. Which of its
recommendations are engineering we can simply schedule, and which are rulings only the owner can
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
  blind panel V4 Pro is fifth of eight at -0.13 z; what it actually holds is the lowest cost per
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
also produced `scripts/catalog_census.py`, so the count class of R-7 defect cannot recur by
transcription. One residual is carried into step 1r below.

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
| `UW-G24` judgement calls | Four sites where prose quotes a catalog count while the code iterates the live catalog: `tests/unit/test_policy.py:1910`, `tests/unit/test_analyze_sibling_exposure.py:814`, `tests/unit/test_orchestrator.py:985`, and `scripts/check_skeleton.py:92` ("40 of 61 skeletons", an advisory-incidence claim never re-measured against the 84-shell catalog). |

**Acceptance:** no site in the tree asserts a catalog figure as current state without either citing
the census or carrying its measurement date. `UW-G24` closes.

### Step 2. Wire the floors (days, unblocked)

The review's R-3 finding is that the delivery floors exist only where nobody ships from. The
reachability half is confirmed and is sharper than the brief admits: `check_fill_integrity.py` and
`check_sibling_fills.py` are reachable only from `run_guard_battery.py`, a hand-run harness that no
workflow or hook references.

**Correction, 2026-08-22.** The inference drawn from that, that the fill-rate floor is therefore
unenforced at request time, is false, and this plan asserted it before checking. Executing the step
produced an enforcement map instead: every blocking check in `check_fill_integrity.py` already has a
request-path enforcer.

| `check_fill_integrity.py` blocking check | Request-path enforcer |
| --- | --- |
| Leftover `<<FILL ...>>` directives | `fidelity_gate.run_stage1_gate` via `has_unfilled_directives` |
| Structure preserved against the skeleton | `fidelity_gate.run_stage1_gate` via `structure_violations` |
| Band per-node word maximum (`words_per_node_profile`) | Validator rule **PL-19** (`validator/policy.py::_check_words_per_node`) at `Severity.ERROR` |
| Story-level fill rate >= 0.6 | `orchestrator._with_fill_rate`, shipped by PR [#737](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/737) (`41d30909`) one day before this plan was written |

The last row is doubly moot: `word_count_violations` admits a node only within
`[0.6 * target, 1.4 * target]`, so `sum(delivered) >= 0.6 * sum(target)` holds by construction and a
story-level 0.6 floor cannot fire on the request path at all. Wiring it was a provable no-op.

What the step actually found is recorded as `AL-551` and fixed on branch
`fix/stage1-persist-signal-coupling`: the persist gate that lets a clean-downgraded fill reach a
human keyed on a report-dict key that `worker._regate_after_transform` replaces wholesale, so a
downgraded fill whose document the reinsertion transform rewrote would have been dropped with no
`Storybook`, no `StorybookVersion`, and no moderation run. It is dormant only until ADR-023 D4
lands a contract that declares a personalizable slot. The signal now rides
`GenerationOutcome.clean_downgrade`, a typed field every rebuild carries forward.

The general lesson, which applies to the rest of this step: "the constant lives in a script" is
evidence about that script, not about the request path. Confirm the absence of an enforcer before
scheduling work to add one.

| Finding | Work |
| --- | --- |
| R-3 | ~~Move the fill-rate 0.6 floor into the generation worker or the validator gate.~~ **Done and moot, see the correction above.** Wire the sibling-gram check for same-skeleton fills; that half stands, and it is the only fill-integrity measure with no request-path enforcer. |
| R-2 (partial) | Surface fill-rate, sibling-gram, and the safety summary on the approval screen, so the human gate sees what the automated gate measured. |
| Medium: path coherence | Build the two cheap proposed detectors: the outbound choice-grammar companion, and the duplicate-body plus POV checks. Give chunked fills a repair budget; today they have zero and differ contractually from one-shot fills. |
| Medium: fidelity judge | Stop defaulting the fidelity judge to the model that wrote the fill. It currently reviews itself. |
| Selection | Per-family reuse cap in selection. |
| `UW-C338` | Adopt the convention that any doc claim a check "enforces" or "gates" something names its invoker (workflow file, hook id, or call site under `src/`), so this class of claim is falsifiable next time. |

**Acceptance:** every floor the brief describes as a pipeline defense has a named invoker on the
request path, and a test that fails when the invoker is removed. Where the enforcer already exists
under a different name, the acceptance is the citation, not new code. `UW-C105`, `UW-C147`,
`UW-C315` and `UW-C338` close.

**Dependency note:** the fidelity-judge item touches which model reviews a fill, and is adjacent to
D1 but not gated by it. "Not the model that wrote it" is correct under any fill assignment.

### Step 3. Run the cheap blocked measurements (days, small spend, unblocked)

| Finding | Work |
| --- | --- |
| R-6 | Adversarial safety harness per band, including 13-16 and 16+, registered with `S`-row discipline. The review's finding is that safety measurement lags quality measurement by an order of magnitude; this is the cheapest way to close the gap. Note the F2 correction: the safety seam runs but its body is a Phase-2 no-op, so `safety_flagged` is structurally always `False`. The harness must not treat that field as a signal. |
| R-11 | Log approval duration and send-backs. The human gate is currently the least measured stage in the pipeline. |
| Directive delta | Re-run at production `TREE` settings rather than the pilot settings. |

**Acceptance:** each measurement is registered as an `S`-row with its falsifier declared before it
runs, and its artifact is committed. No result is reported that the register does not carry.

### Step 4. Economics spine (days, gated by D3)

R-5: the economics half of the goal has no target, no unit-cost model, and no human-minutes term.
The human minutes will dominate cost at scale, and nothing currently accounts for them.

| Finding | Work |
| --- | --- |
| R-5 | Unit-cost model page per `UW-G19` and `E5`, with a stated per-book cap by band. **The cap derives from a revenue target that does not exist yet: see D3.** |
| R-5 | Shadow-price the subagent legs; meter covers; price the Anthropic and Modal providers. |
| Medium: 4.5 artifacts | The per-leg dollar figures have no committed artifact; they are owner billing prose, not deterministic accounting from run records. Either commit the accounting or relabel the figures. |
| Medium: "credits checks" | The brief names a guard that does not exist. Build the endpoint pinning, credits preflight, and daily spend counter, or remove the claim. |
| Medium: F7 levers | F7's lever list omits measured levers already in the vendor README: prompt caching (44% and 30% cache-served rates, with a warning the brief drops), reasoning-share as a selection rule, batch APIs for offline catalog work, and chunk-size economics. |

The reasoning-share lever is worth promoting: LLM cost on this programme tracks reasoning, not
output length. Measured spans were 1.36x on prose and 8.8x on cost, and cost buys diversity at
rho -0.11. That is their cleanest cost discriminator and it is currently absent from the brief.

**Acceptance:** a per-book cost ceiling by band exists, is derived from a stated revenue
assumption, includes a human-minutes term, and every leg price traces to a committed run record.

### Step 5. Constant and provenance governance (days, partly gated by D2)

| Finding | Work |
| --- | --- |
| R-10 | Diversity-floor baseline with a recalibration rule keyed to fill-model changes. Unify the `TAU_CELL` loader. Prompt-version hash manifest. Run-record schema carrying git SHA, sampling parameters, and relative paths. |
| R-9 (partial) | Strict enforcement in the promotion prover, plus the deletion and label workflow holes. **Gated by D2.** |
| Medium: reproducibility | No sampling parameters or harness git SHA are recorded anywhere. Three merged evidence rigs are pre-registered against books never committed. Cell D results are published only in the brief while the register still says the cell is open. Several lesson-log IDs cited by the brief and by code point at the wrong lessons after a renumbering. |

**Acceptance:** a stranger can re-run any published result from the committed artifact alone. Every
calibrated constant has one loader and a recalibration trigger. No `AL` citation in the brief or in
code resolves to the wrong row.

### Step 6. Harden F3 and F4 (about a week, priced, gated by D1)

| Finding | Work |
| --- | --- |
| R-8 | S-1's per-model rankings are statistically and methodologically unsupported. One costed, transcript-committed tool-assisted replication, including an Anthropic API leg, and re-run the DeepSeek cells on the same harness. |
| R-9 | The skeleton stage has no above-floor quality measure. Run the shell quality rubric blind over tool-passed versus catalog shells. |
| R-1 | The stateful-without-checker ablation. |
| S-5 | Repair its corpus and citations. |

**Acceptance:** every per-model claim in section 4.2 traces to a committed transcript from a single
harness, and the ranking survives a stated statistical test rather than a count of passes.

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
in production.

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
| Would be retired | 55 of 74 production-eligible, **74%** (the register said 97%) |
| Fail *without* `--strict` | 3 of 84, all already `production_eligible: false` |

Two findings sharpen it. First, the gate promotion actually runs is not in question: nothing a
request can reach fails it today. Second, **the entire delta is the `CG-*` grammar family**, which
`--strict` promotes from advisory to blocking. Of the 55 eligible shells strict would reject, 21
fail on `CG-*` alone and 34 on `CG-*` plus something structural, and **none fail on structural
grounds alone**. `CG-3`'s words-per-stop ceiling is 1,557 of the findings by itself.

So the ruling is not "is the strict bar right". It is whether `CG-3`'s words-per-stop ceiling is
calibrated for the catalog we ship. The structural floors that `--strict` adds reject nothing
independently.

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
`docs/planning/catalog-census.md`. It is deliberately not wired to pre-commit or CI. Wiring it
makes a stale doc a build failure, which is the only mechanism that has ever stopped this class of
drift on this project; not wiring it keeps commits fast and accepts that the census is advisory.

A related gap has no owner yet: **gate outcomes decay exactly like counts and have no emitter at
all.** D2's own inputs are the evidence. "The strict bar passes 2 of 61" had drifted to 20 of 84,
and its cost from 97% to 74%, which is a 23-point error in the input to an open decision. The
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
