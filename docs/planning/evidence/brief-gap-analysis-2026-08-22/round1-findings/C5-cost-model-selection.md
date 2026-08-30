# C5: Cost engineering and per-stage model selection

Component audit of brief `docs/planning/cyo-generation-research-brief-2026-08-22.md` sections F4, F7,
4.2, 4.5, against the code that implements them and the run records that evidence them.

Sources read: `generation/{usage,cost,metered,guarded,orchestrator,chunking,queue,provider,skeleton,
reading_level_loop,worker}.py`, `generation/providers/*`, `core/{pricing,config}.py`,
`moderation/{pipeline,stages,fidelity_review}.py`, `covers/*`, `story_requests/{authoring_plan,service}.py`,
`scripts/{compare_vendors,compare_skeleton_authors}.py`, `docs/planning/vendor-comparison/**`,
`docs/planning/evidence/skeleton-author-vendors/**` (via `.worktrees/brief-evidence/`),
`docs/planning/c302-fill-budget-options.md`, `docs/planning/skeleton-sourcing-test-plan-2026-08-21.md`,
`docs/planning/yield-results/`, the authoring lessons log and the unscheduled work register.

**Retraction.** An earlier draft of this audit reported that `evidence/skeleton-author-vendors/`,
`skeleton-sourcing-test-plan-2026-08-21.md`, register rows `S-0`..`S-5`, `AL-510`..`AL-514` and
`UW-C317`..`UW-C320` did not exist. That was an artifact of the branch I was given; all of them exist
and I have now read them. Nothing below rests on their absence, and question 4 is answered from the
real per-attempt records rather than from reconstruction.

---

## Price assumptions (every dollar figure below depends on these)

| Item | Rate used | Source |
| --- | --- | --- |
| `openrouter` / `anthropic/claude-haiku-4.5` | $1.00 / $5.00 per MTok | `core/pricing.py`, as_of 2026-08-14 |
| `openrouter` / `anthropic/claude-sonnet-4.6` | $3.00 / $15.00 | same |
| `openrouter` / `anthropic/claude-sonnet-5` | $2.00 / $10.00 | same |
| `openrouter` / `deepseek/deepseek-v4-pro` (`azure/us` pin) | $1.91 / $3.83 | `core/pricing.py`, as_of 2026-08-20 |
| `openrouter` / `deepseek/deepseek-v4-flash` | $0.14 / $0.28 | `core/pricing.py`, as_of 2026-08-14 |
| Opus-class tier (`claude-opus`, `claude-fable`) | **$15 / $75 assumed** | NOT in `core/pricing.py`; standard Opus-class list. Treated as a **floor** for `fable`, which CLAUDE.md places above Opus |
| Cover art, `gemini-3-pro-image` 1K portrait | **~$0.134/image assumed** | NOT in `core/pricing.py` and not metered anywhere; ~1,120 image output tokens at ~$120/MTok |
| Human review labour | **$25/hour assumed, fully loaded** | No project source; no measurement exists (see C5-1) |

Everything marked "measured" below is read from a committed run record. Everything else is labelled
estimate and shows its arithmetic.

---

## C5-1: There is no cost-per-book number, and the "cost-effective" claim is unevidenced

- **Severity**: critical
- **Category**: cost visibility
- **Locus**: `docs/planning/unscheduled-work-register.md` `UW-G19` (status `unscheduled`);
  `src/cyo_adventure/db/models.py:2693` (`cost_usd`); brief section 1 ("unit economics cap what any
  one book may cost to produce") and F7
- **Problem**: The programme's framing claim is that the pipeline produces books "at acceptable cost",
  and section 1 asserts a unit-economics cap. No such number exists anywhere in the repository. What
  exists is: a per-job `cost_usd` column on `generation_job` (added by #701), written once at the end
  of a job, exposed by **no API route, no admin surface, and no query in `scripts/`** (`grep -rl
  cost_usd src/ scripts/` returns only the writer, the model, and the vendor-comparison harness).
  There is no aggregation, no per-band figure, no cost-per-approved-book, no accounting for failed
  books, and no measurement of human review minutes. `UW-G19` states this in the register's own words
  ("every cost claim we could make today is an estimate presented as a measurement") and is still
  `unscheduled`. The brief's F7 ("engineer the cost") lists levers and never states the quantity
  those levers act on.

  **The best number I can construct.** Fill-stage cost is measured, from
  `docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/report.json` (DeepSeek V4 Pro,
  `azure/us` pin, cap 131,072, `max_repairs=3`, reading-level passes 2, `stage1_gate=skipped`):

  | Book | Band / nodes | Delivered leaf words | Output tok | **Measured cost** |
  | --- | --- | ---: | ---: | ---: |
  | 1 `the-last-cartage` | 16+ / 632 | 19,423 | 154,253 | **$1.0637** |
  | 2 `the-quarry-signal` | 13-16 / 267 | 9,997 | 75,278 | **$0.5383** |
  | 3 `the-tin-whistle-map` | 8-11 / 193 | 8,353 | 50,147 | **$0.3502** |
  | 4 `the-last-blue-cup` (rerun) | 3-5 | 598 | 3,366 | **$0.0474** |
  | 0 `the-last-cartage` | 16+ | 0 | - | **unmetered** ("no provider call was metered for this book"), 397.96 s |
  | 4 (first attempt) | 3-5 | 0 | 3,227 | **$0.0421** wasted |

  Run total $1.9943 for 3 delivered books = **$0.665 per delivered book, fill stage only**. Two of
  five books failed first pass (40%).

  > **Numerator and denominator note, 2026-08-30.** Re-read `report.json` on `origin/main`: it holds
  > **five** book records, three `passed` ($1.0637 + $0.5383 + $0.3502 = $1.9522) and two `error`
  > (one with `cost: null`, the unmetered 397.96 s book 0, and one at $0.0421). Its total is
  > therefore $1.9943, and **that total includes the wasted attempt but not the $0.0474 rerun**,
  > because the rerun is not in this report at all. Row 4 of the table above is from a separate run
  > record and is labelled a rerun; it should not be read as part of the same $1.9943.
  >
  > So $0.665 is *cost of this run per book this run delivered*, which is a defensible figure but is
  > not cost per unique delivered book. On the four distinct books actually delivered across both
  > runs, spending $1.9943 + $0.0474 = **$2.0417 over 4 books is $0.510 each**. Quote whichever
  > answers the question at hand and say which: $0.665 prices a run that fails 40% of its books,
  > $0.510 prices the delivered catalog. The 40% first-pass failure rate itself is unchanged, and so
  > is book 1's decomposition below, which uses only book 1's own metered cost.
  >
  > The `cost: null` book is the reason to check this at all: an empty-but-valid record contributes
  > nothing to the numerator and one to any naive denominator, which moves an average in whichever
  > direction the reader was not watching.

  Decomposing book 1: $1.0637 - (154,253 x $3.83/MTok = $0.5908) = $0.4729 of input at $1.91/MTok =
  **247,600 input tokens**, against a skeleton of ~99,400 tokens. The remaining ~148,000 input tokens
  and ~54,300 output tokens are the reading-level loop, i.e. **$0.492, 46% of that book's fill bill**
  (see C5-8).

  Moderation is **not in any run record**, because `compare_vendors.py` calls `fill_skeleton` only.
  Estimated for book 1 as delivered (632 nodes, 19,423 words ~= 25,900 prose tokens), from the call
  structure in `moderation/pipeline.py:1000-1020` and `moderation/stages.py`:
  safety `ceil(632/8)=79` calls (~45,650 in, ~25,280 out) + coherence 1 whole-book call (~31,900 in,
  1,024 out) + engagement 1 whole-book call (~31,900 in, 1,024 out) + stage-1 fidelity review 1 call
  carrying skeleton beats plus filled bodies (~60,000 in, 4,000 out) = **~169,450 in / ~31,330 out**.
  At the shipped review model `anthropic/claude-sonnet-4.6` ($3/$15): 0.16945x3 + 0.03133x15 =
  $0.508 + $0.470 = **$0.978**. At DeepSeek V4 Flash ($0.14/$0.28): **$0.033**.

  All-in reconstruction, per publishable book:

  | Line | 3-5 short | 8-11 medium | 16+ long |
  | --- | ---: | ---: | ---: |
  | Fill + reading-level (measured) | $0.047 | $0.350 | $1.064 |
  | Moderation @ shipped Sonnet 4.6 (est.) | $0.05 | $0.45 | $0.978 |
  | Cover art (est., unmetered) | $0.134 | $0.134 | $0.134 |
  | Skeleton amortization (est., see C5-12) | $0.10 | $0.30 | $0.50 |
  | Subtotal | $0.33 | $1.23 | $2.68 |
  | x1.25 for the 20-40% that never publish | **$0.41** | **$1.54** | **$3.35** |
  | Human review @ $25/h (5 / 12 / 20 min) | $2.08 | $5.00 | $8.33 |
  | **All-in** | **$2.49** | **$6.54** | **$11.68** |

  At a 40/40/20 band mix: **$1.45/book machine, $5.95/book all-in**. Human review is 59-71% of the
  total at every band.

  Two corrections that make this an underestimate, not an over-estimate. (a) `AL-490`: those three
  "passing" books delivered 38.9-52.9% of commissioned words. A book delivering its commissioned
  words roughly doubles the fill and moderation output terms, taking 16+ to ~$5.4 machine.
  (b) These are single-leg, gate-skipped harness runs; the production path adds the stage-1 gate,
  binding, and re-moderation after repair.

  **Against a subscription ceiling.** `core/config.py:931` sets `default_monthly_story_quota = 10`.
  A plausible kids-reading-app subscription is $7-15/month; at a 70% target gross margin that is a
  $2.10-$4.50/month COGS budget. At the realistic re-request rate implied by `Q-1` (a child exhausts
  a cell by roughly the fourth request), say 3 books/child/month, the all-in cost is
  **3 x $5.95 = $17.85/child/month against a $2.10-$4.50 budget: over by 4.0-8.5x**. At the full
  10-book quota it is $59.50/month, over by 13-28x. Machine-only, ignoring the mandatory human,
  3 x $1.45 = $4.35/month, which is still at or over the ceiling.
- **Why it matters for the goal**: "cost-effective" is half the programme's stated goal and it is the
  half with no instrument. Every architectural decision the brief defends on cost grounds (catalog
  reuse, model selection, gate-before-human) is being made against a quantity nobody has computed.
  On my reconstruction the programme is not cost-effective at its own default quota by a wide margin,
  and the binding term is the one the brief's F8 declares non-negotiable.
- **Recommendation**: Close `UW-G19` before the next architecture decision. Concretely: (1) surface
  `generation_job.cost_usd` in an admin endpoint and a weekly rollup keyed by band, status, and
  `cost_complete`; (2) add a `review_minutes` column written by the publishing approval action, which
  is a one-line timestamp diff and is the only way the dominant term ever becomes visible; (3) publish
  a single dated `cost-per-book.md` with the six lines above per band, marked estimate where it is an
  estimate; (4) state the unit-economics cap section 1 asserts as an actual number, then test the
  reconstruction against it.
- **How to check I'm right**: `grep -rl cost_usd src/ scripts/` (three writers, no readers).
  `python3 -c "import json;r=json.load(open('docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/report.json'));print(sum(b['cost'] or 0 for b in r['books']))"` returns 1.9943.
  `grep -n default_monthly_story_quota src/cyo_adventure/core/config.py` returns the 10. Search the
  repo for any file containing a cost-per-book figure: there is none.

---

## C5-2: No runtime spend cap exists; the only budget is a monthly request *count*

- **Severity**: critical
- **Category**: budget enforcement
- **Locus**: `src/cyo_adventure/story_requests/service.py:251` (`enforce_family_quota`),
  `core/config.py:931`, `api/generation.py:90` (`MAX_ACTIVE_JOBS_PER_FAMILY = 2`),
  `generation/orchestrator.py:1425-1520`
- **Problem**: Nothing in the request path is denominated in dollars. Tracing every bound that could
  stop a pathological book:
  - per-call `max_tokens`: `resolve_output_cap(model)`, min(131,072, per-model ceiling).
  - `max_repairs = 3` (`orchestrator.py:923`), shared between structural repair and stage-1 fidelity.
  - reading-level: `_DEFAULT_READING_LEVEL_PASSES = 2` passes, each `ceil(out_of_band/12)` calls
    (`reading_level_loop.py:80,672`). **No cap on the call count.**
  - moderation safety: `ceil(nodes / review_batch_size=8)` calls. **No cap on the call count.**
  - chunked fill: `plan_fill_batches` partitions until every batch fits. **No cap on batch count**,
    and each batch re-sends all previously written prose (`chunking.py:321`), so input grows
    quadratically in batch count.
  - RQ `job_timeout = 1800 s` (`core/config.py:404`). This is a wall-clock stop, not a spend stop.
  - `enforce_family_quota`: 10 **requests** per family per month, and `MAX_ACTIVE_JOBS_PER_FAMILY=2`.

  Not one of these is a budget. The quota is a count, so a family whose ten requests all land on 16+
  long books costs ~13x a family whose ten land on 3-5 shorts, and the platform charges both the same.
  There is no per-job ceiling, no per-family dollar ceiling, and no circuit breaker on aggregate spend.

  **Worst case for one request**, shipped models (fill `anthropic/claude-haiku-4.5` $1/$5, review
  `anthropic/claude-sonnet-4.6` $3/$15), a 632-node 16+ book at full commissioned delivery:
  fill + 3 repairs, 4 calls x (100k in + 64k out) = 400k in / 256k out = $0.40 + $1.28 = $1.68;
  reading-level 2 passes x 53 batches = 106 calls x (~9k in + ~9k out) = 954k in / 954k out =
  $0.95 + $4.77 = $5.72; moderation pass 1 = $1.88; repair + re-moderation = $2.39; cover $0.13.
  **Total ~$12.0 against a ~$2.2 median: 5.5x.** The only reason it is not 20x is that the job is
  killed by the 1,800 s wall clock first, which is a coincidence, not a control (see C5-14).
- **Why it matters for the goal**: A children's subscription product with no per-account spend ceiling
  has an unbounded worst case per paying customer. It also means the "cost-effective" claim cannot be
  enforced even if C5-1's number existed: there is nothing to enforce it with.
- **Recommendation**: Thread the `UsageLedger` already attached to every job into a budget check.
  `MeteredProvider.complete` is the single chokepoint every provider call passes through
  (`generation/metered.py`); adding `if estimate_run_cost(self._ledger.calls).amount_usd > budget:
  raise BudgetExceededError` there is a handful of lines and makes the cap structural in exactly the
  way the PII guard already is. Set the per-job budget from the band (a 3-5 book has no business
  spending 16+ money). Then convert `default_monthly_story_quota` from a count to a dollar budget, or
  keep the count and add a dollar budget beside it.
- **How to check I'm right**: `grep -rn "budget\|spend\|usd" src/cyo_adventure/generation/orchestrator.py`
  finds only token budgets. `grep -rn "cost" src/cyo_adventure/generation/metered.py` returns nothing.
  The only quota enforcement is `enforce_family_quota`, and it compares a count, not an amount
  (`service.py:294-296`: `quota = resolve_family_quota(family); if spent >= quota`).

---

## C5-3: The fill-rate floor that catches the measured waste mode is not in the production path

- **Severity**: critical
- **Category**: waste
- **Locus**: `scripts/check_fill_integrity.py` (script only);
  brief section 3.4 lists it as a pipeline "delivery measurement"; `AL-490`, `UW-C307`
- **Problem**: `AL-490` measured the single largest waste event in the programme's history: three
  books passed the deterministic gate while delivering **38.9%, 52.9% and 42.7%** of commissioned
  words, with 631 of 632, 245 of 267 and 191 of 193 nodes under the advisory floor. The countermeasure
  is `check_fill_integrity.py --min-fill-rate 0.6`, calibrated on those exact books. **It is a
  standalone script that nothing in `src/` imports.** `grep -rn "check_fill_integrity\|min_fill_rate\|
  fill_rate" src/cyo_adventure/` returns two comments and no call site. The brief's section 3.4
  presents it as part of "Story automated checks" alongside the gate; it is not.

  The same is true of `check_sibling_fills.py` (the 96.3-per-1000 four-gram finding, `AL-498`), which
  the brief does correctly mark as open work (`UW-C315`), and of `check_prose_craft.py`.

  In production this means the exact defect that produced $1.99 of spend for books at 39-53% delivery
  recurs, passes the gate, reaches a human, and is invisible to any counter. Worse, delivery is the
  denominator of every cost-per-book figure: at 40% delivery, a $1.06 book is really a $2.66 book
  measured per commissioned word, and nothing in the system knows that.
- **Why it matters for the goal**: F2 exists precisely because "a passing gate is not quality", and
  the delivery measurement is the countermeasure F2 names. Leaving it outside the pipeline means the
  brief's own headline lesson has not been operationalized, and cost-per-delivered-book cannot be
  computed even in principle from production data.
- **Recommendation**: Move the fill-rate computation into `validator/` or into
  `orchestrator.fill_skeleton`'s outcome (the skeleton is in hand at both sites), record it on the
  `generation_job` row beside `cost_usd`, and make it blocking at the calibrated 0.6. Then compute
  cost-per-commissioned-word rather than cost-per-job, which is the figure that actually prices a book.
- **How to check I'm right**: `grep -rn "check_fill_integrity\|fill_rate\|min_fill_rate"
  src/cyo_adventure/ --include=*.py` returns only comment references in `generation/skeleton.py:102,390`
  and `diversity/structure.py:3`. No router, worker, or validator calls it.

---

## C5-4: Billed calls are discarded from the meter, and a run record proves it

- **Severity**: high
- **Category**: metering
- **Locus**: `generation/providers/_base.py:262` (`return await attempt()` inside the retry loop);
  `providers/openrouter.py:349` (`if not content:` raises before any `TokenUsage` is built);
  `providers/anthropic.py:179-180` (`_extract_content` raises before `_extract_usage` runs);
  `providers/fallback.py:105-125`
- **Problem**: `run_with_retries` records the usage of the **successful attempt only**. Its docstring
  justifies this: "a transient failure is typically a 429 or a connection error, which is not billed".
  That is true for a 429 and false for the two failure modes this project has actually measured:
  - An HTTP **200 with empty content** is billed in full and is mapped to a transient `ProviderError`
    (`openrouter.py:349`; `anthropic.py:_extract_content`). The tokens are gone from the ledger.
    This is the `AL-328` / `moonshotai/kimi-k3` shape exactly: **$0.5319 billed for 32,000 output
    tokens of which 30,872 were reasoning and 1,128 prose, finishing on `length` and returning
    nothing usable** (vendor-comparison README, "The limiting case").
  - An `APIResponseValidationError` on a 2xx is billed and discarded the same way
    (`anthropic.py:_attempt`).
  - `FallbackProvider`'s docstring asserts "a leg that exhausted its transient retries returns no
    usage to attribute". Correct as a statement about the code; wrong as a statement about the bill.

  **Empirical proof in a committed run record.** `runs/deepseek-v4-pro-2026-08-20/report.json`
  book 0: `status: error`, `latency_s: 397.96`, `cost: null`,
  `cost_unavailable_reason: "no provider call was metered for this book"`,
  `error: "openrouter transient failure persisted after 3 attempts"`. `AL-492` establishes what those
  three attempts were: **`finish_reason: content_filter` with zero content, i.e. three billed 200s**,
  at ~133 s each. The ledger recorded nothing. The same book failed 7 of 7 times across two runs.

  A second, larger hole: the four Anthropic subagent legs in the S-1 experiment
  (`evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/records/*.record.json`) carry
  `input_tokens: null, output_tokens: null, reasoning_tokens: null, latency_s: 0.0`. **Not one token
  of the 42-shell tool-assisted run was metered, for any leg** (`summary.md` reports `output tokens`
  = 0 for all seven legs). Even in the blind run `e1-2026-08-21`, only 12 of 80 records carry token
  counts.

  On the brief's question "what happens where the provider does NOT report it": `usage.py` is careful
  and correct (`None` never collapses to `0`, `unknown_calls` is summed, `complete` is derived). The
  hole is one level up: a call that **fails** never reaches the ledger at all, so it does not even
  increment `unknown_calls`. `UsageTotals.complete` therefore reports `True` for a run that discarded
  three billed calls. That is worse than an incomplete flag: it is a confident wrong answer.
- **Why it matters for the goal**: The metering subsystem's stated purpose is that "a cost figure that
  is quietly wrong is worse than no cost figure at all". The discard path produces exactly that. And
  the discarded calls are systematically the expensive ones: reasoning burn, content filters, and cap
  truncation are precisely the modes that bill full and deliver nothing.
- **Recommendation**: Record usage on **every** attempt, successful or not. Concretely, build the
  `TokenUsage` before the content check in `openrouter._extract_completion` and
  `anthropic._attempt`, and give `run_with_retries` an optional ledger so failed attempts are appended
  with an `outcome` discriminator. Add a `failed_calls` field to `UsageTotals` beside `unknown_calls`,
  and make `complete` false when any call failed with an unread usage block. Then wire the harness's
  `_metered_fields` so `cost_unavailable_reason: "no provider call was metered"` becomes impossible.
- **How to check I'm right**: Read `providers/openrouter.py:335-360`: `dig_usage` is called *after*
  the `if not content: raise`. Read `providers/_base.py:255-270`: the loop returns only on success.
  Then `python3 -c "import json;print(json.load(open('docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/report.json'))['books'][0])"`.

---

## C5-5: Repriced at list, the recommended structure author is the most expensive option by 30-130x, and the recommendation does not survive

- **Severity**: high
- **Category**: comparison validity
- **Locus**: brief section 4.5 ("four Anthropic tiers plus the harness at zero marginal provider cost
  as subagents") and section 4.2's consequence line; `skeleton-sourcing-test-plan-2026-08-21.md`
  section 10; `evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/{tools-meta.json,shells/,summary.md}`
- **Problem**: The comparison that produces the recommendation "author structure with a tool-assisted
  Anthropic tier" is not a cost comparison. The test plan says so in its own words: the Anthropic legs
  were chosen as **"four Anthropic subagent legs at zero provider cost"**, run through the owner's
  Claude Code session rather than through the provider path, "tier-labeled, not backend-pinned". Their
  records carry no tokens and no latency. So the slate compares two legs whose tokens hit a bill
  against four legs whose tokens hit a flat-rate subscription, and reports the second group as free.

  **Reconstruction on real data.** `tools-meta.json` records actual checker invocations per attempt,
  and `shells/` holds the actual authored artifacts. Two independent methods:

  *Method A (artifact-sized).* Per invocation, output = the leg's own measured shell size (median
  3,395 tok in cell A, 5,747 in cell D); input = brief (6,000, assumed) + accumulated draft and
  feedback. Cost at the list rates in the table above.

  *Method B (measured-rate calibration).* Per invocation, use the per-attempt token rates actually
  recorded for a comparable leg in the blind run `smoke2-2026-08-21`: Anthropic tiers calibrated on
  `anthropic-sonnet-5` (7,178 in / 26,421 out per attempt, **81% of output was reasoning**), DeepSeek
  legs on their own measured rates (v4-pro 8,909/8,552 at 0% reasoning; v4-flash 6,311/18,649 at 70%).

  | Leg | Passes /6 | Checker runs | Method A total | Method B total | **A $/pass** | **B $/pass** |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | `deepseek-v4-flash` | 3 | 32 | $0.09 | $0.20 | **$0.031** | **$0.065** |
  | `claude-haiku-subagent` | 3 | 51 | $1.60 | $7.11 | **$0.533** | **$2.37** |
  | `claude-sonnet-subagent` | 4 | 42 | $3.54 | $11.70 | **$0.885** | **$2.93** |
  | `claude-fable-subagent` | 6 | 24 | $13.97 | $50.14 | **$2.33** | **$8.36** |
  | `claude-opus-subagent` | 6 | 27 | $17.55 | $56.41 | **$2.93** | **$9.40** |
  | `deepseek-v4-pro` | 0 | 46 | $2.87 | $2.29 | n/a | n/a |
  | `moonshot-kimi-k3-modal` | 5 | 37 | off-bill | off-bill | n/a | n/a |

  Method B's DeepSeek figure validates the model: $2.29 for 6 v4-pro shells = $0.38/shell, against the
  test plan's own pre-registered estimate of "$6-12 for 18 shells" ($0.33-0.67/shell). The methods
  disagree by ~3.5x on the Anthropic legs because Method B carries Sonnet-5's measured 81% reasoning
  burn; the true figure depends on whether the subagents ran with extended thinking on, which **nobody
  recorded**. Either way:

  1. **The cheapest passing structure author is DeepSeek V4 Flash by 17-129x per pass.** Cost per pass
     already prices reliability: Flash's 3/6 pass rate is in the denominator.
  2. **The recommended tier (Fable/Opus) is the most expensive option on the board**, $2.33-$9.40 per
     pass against Flash's $0.031-$0.065.
  3. **The four "free" legs are the dominant cost of the experiment.** At list they are $33-$126
     against the $1.30 attributed to DeepSeek, i.e. 96-99% of the true bill, in a programme the plan
     capped at "~$40 of provider credit". The brief's 4.5 sentence about premium Western legs being
     90% of the *previous* slate's bill is repeated as if the replacement slate fixed it. It did not;
     it moved the same spend off the ledger.
  4. **The stated $1.30 DeepSeek figure is itself low.** Pricing the DeepSeek token counts that the
     records *do* carry (e1 + e1r3 + both smokes) at the pinned rates gives **$2.376**, 1.8x the
     stated figure, and those records are themselves incomplete (12 of 80 in e1).

  **Cost per quality unit cannot be computed at all.** The S-1 grid's only outcome is binary
  strict-pass. F2 says explicitly that a passing gate is not quality, so the recommendation rests on
  the one measure the framework declares insufficient. The one continuous axis that *was* recorded
  cuts the other way: `summary.md`'s min catalog distance is `claude-opus 0.051`, `claude-fable 0.066`,
  `claude-sonnet 0.083`, `claude-haiku 0.138`, `deepseek-v4-flash 0.150`, `deepseek-v4-pro 0.172`
  against an anti-clone floor `TAU_CELL = 0.05`. The expensive Anthropic tiers author the shells
  *least* distinct from the existing catalog, with Opus 0.001 above the floor that would reject it.

  The fill-stage half of the recommendation ("fill with V4 Pro") does survive a level comparison: the
  vendor README's $/book-delivered table puts V4 Pro at $0.0398 against Sonnet 4.6 at $0.1860 and
  Sonnet 5 at $1.4194. But it survives on a table that prices the *call*, not the delivered book:
  `AL-490` then measured V4 Pro delivering 39-53% of commissioned words, so its real
  $/commissioned-word is 2-2.5x the table's figure and the gap to the Anthropic legs narrows.
- **Why it matters for the goal**: F4 is the brief's enabling recommendation and F7 is its cost
  discipline. Section 4.5 applies F7's discipline to two legs and exempts four, then section 4.2 makes
  a production recommendation for one of the exempt four. On a level basis the recommendation inverts.
  A billing boundary is not a cost finding.
- **Recommendation**: (1) Restate section 4.5 with the Anthropic legs priced at list, in a bracket
  ($33-$126) with the assumption named, and stop describing them as zero-cost; say "off-bill against a
  flat-rate subscription, not measured". (2) Instrument the subagent driver so tool-assisted legs
  record tokens; without that no future skeleton-sourcing decision can be costed either. (3) Re-run the
  cell-A/D grid with V4 Flash as the *primary* structure-author candidate and an Anthropic tier as the
  reference, since Flash passed 3/6 at 1/40th the level cost, and the decision hinges on whether the
  extra 3/6 reliability is worth 30-130x. (4) Add a continuous structural-quality endpoint so
  cost-per-quality-unit is computable at all.
- **How to check I'm right**: `python3 -c "import json;m=json.load(open('docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/tools-meta.json'));print(len(m))"` = 42; the per-leg
  checker-run totals are 24/51/27/42/32/46/37 as tabulated. `grep -n input_tokens
  docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/records/*.record.json`
  shows `null` on every record. `sed -n 505,520p docs/planning/skeleton-sourcing-test-plan-2026-08-21.md`
  carries the "at zero provider cost" sentence and the "tier-labeled, not backend-pinned" limitation.

---

## C5-6: Two shipped backends and the entire cover-art stage are unpriced or unmetered

- **Severity**: high
- **Category**: metering
- **Locus**: `core/pricing.py` `_PRICES` (keys cover only `openrouter` and `ollama`);
  `providers/anthropic.py:172` and `providers/modal.py:260` (both report their own provider name);
  `core/config.py:411` (`generation_provider` accepts `"anthropic"` and `"modal"`);
  `covers/provider.py:16`, `covers/service.py:155`
- **Problem**: Three distinct gaps.
  1. **`generation_provider="anthropic"` prices as $0.00.** The direct-Anthropic adapter reports
     `provider="anthropic"` and `PRICES` has no `("anthropic", *)` key, so `price_for` returns `None`,
     `estimate_cost` returns `Decimal(0)` with `complete=False`, and every job on that backend records
     `cost_usd = 0.000000`. This is not a hypothetical configuration: `MODEL_OUTPUT_CAPS` carries
     dedicated rows for the `anthropic`-spelling ids `claude-sonnet-4-6` and `claude-haiku-4-5`
     precisely because that backend is shipped, and `active_fill_model` reads `anthropic_model` for it.
     `("modal", *)` is missing for the same reason.
  2. **Cached tokens are requested but never accounted.** `openrouter._build_messages` sets
     `cache_control: {"type": "ephemeral"}` on the system block for every `anthropic/` model, which is
     the shipped fill default. Nothing reads `usage.prompt_tokens_details.cached_tokens`: `dig_usage`
     reads only `prompt_tokens`/`completion_tokens`, and `TokenUsage` has no cached field. Every input
     token is billed at 1.0x. Anthropic reads cost 0.1x and writes 1.25x, so the recorded cost
     **overstates** a warm-cache call by up to ~10x on the cached share. The vendor README measured 44%
     of `gpt-5.6-sol`'s and 30% of `glm-5.2`'s prompt served from cache and says so explicitly: "any
     price model built from published rates without a cache-hit term will over-recover". Magnitude:
     input is 44% of book 1's fill bill ($0.47 of $1.06); a 40% hit at 0.1x would cut that to $0.30,
     i.e. **~16% of the book's recorded cost is a cache-blind overstatement**.
  3. **Cover art is completely outside the accounting.** `covers/provider.py` calls the Google GenAI
     client directly with no ledger, no `TokenUsage`, no price row for `gemini-3-pro-image`, and no
     retry accounting. `grep -rn "ledger\|UsageLedger" src/cyo_adventure/covers/` returns nothing. At
     my assumed $0.134/image this is 3-40% of the machine cost of a book depending on band, and it is
     the single largest term at 3-5 (where the fill is $0.047).
- **Why it matters for the goal**: A cost figure that reports $0.00 for a configured backend, and that
  omits a whole per-book stage, cannot support any cost claim. Gap 1 is the same class of defect as
  `AL-333` (which found every cloud entry unpriced and every row writing `cost_complete = false`);
  that was closed for OpenRouter and left open for the other two backends.
- **Recommendation**: Add `("anthropic", *)` and `("modal", *)` rows to `_PRICES` and to
  `scripts/refresh_pricing.py`, or make `build_provider` refuse a backend with no priced model outside
  `local`. Add `cached_input_tokens` to `TokenUsage`, read it from
  `usage.prompt_tokens_details.cached_tokens` and from the Anthropic SDK's
  `cache_read_input_tokens`/`cache_creation_input_tokens`, and add the two multipliers to `ModelPrice`.
  Meter cover generation into the job ledger with a per-image price row.
- **How to check I'm right**: `python3 -c "import re;print(sorted(set(re.findall(r'\(\"(\w+)\", \"', open('src/cyo_adventure/core/pricing.py').read()))))"` prints `['ollama','openrouter']`, while
  `grep -n 'generation_provider: Literal' -A2 src/cyo_adventure/core/config.py` lists five backends.
  `grep -rn "cached\|cache_read" src/cyo_adventure/generation/` finds only the `cache_control` request
  in `openrouter.py:126`, never a read.

---

## C5-7: Per-stage model selection is half-built, and the shipped configuration contradicts the brief's own recommendation

- **Severity**: high
- **Category**: model selection
- **Locus**: `core/config.py:459,460,490,612,613,935`;
  `story_requests/authoring_plan.py:58-85,234-279`; `generation/worker.py:1011,1477,1632`
- **Problem**: The brief's F4 says "the authoring plan needs a model per stage" and calls it "the
  enabling change". Partially answering the audit question: some of it exists, none of it is in the
  authoring plan, and the shipped defaults are the opposite of the recommendation.

  Where each stage's model actually comes from today:

  | Stage | Source | Shipped default |
  | --- | --- | --- |
  | Skeleton authoring (`mechanism="skill"`) | `AuthoringPlanRequest.prep_model`, validated against a **hand-maintained** `SKILL_MECHANISM_MODELS` frozenset (`authoring_plan.py:64`) | admin choice |
  | Skeleton authoring (`mechanism="automated_provider"`) | `plan.provider` / `plan.model`, checked against a DB allowlist | admin choice |
  | Fill | `Settings.openrouter_model`, overridable per job via `_authoring_model_override` | `anthropic/claude-haiku-4.5` |
  | Fill fallback | `Settings.openrouter_fallback_model` | `anthropic/claude-sonnet-4.6` |
  | Stage-1 fidelity review | `authoring["review_stage1_model"]`, else falls back to `prep_model` | - |
  | Moderation review (stage 2) | `Settings.review_openrouter_model`, with `_review_stage2_override` | `anthropic/claude-sonnet-4.6` |
  | Reading-level repair | **none**: reuses the fill provider | fill model |
  | Cover | `Settings.cover_model` | `gemini-3-pro-image` |

  So: the fill and review stages *can* differ, but only through process-level `Settings` plus two
  ad-hoc overrides smuggled through the `authoring_metadata` JSON blob. The `AuthoringPlan` schema,
  which is the object the brief names, carries a model for **one** stage (skeleton authoring). There
  is no per-stage model in the plan, no per-band selection, and the reading-level loop, which is the
  single largest call-count consumer, has no model of its own at all.

  And the shipped defaults contradict 4.2's recommendation on both live stages: **fill is Haiku 4.5,
  not V4 Pro; review is Sonnet 4.6, not V4 Flash.** The review divergence alone is worth $0.945 per
  16+ book (C5-1's arithmetic: $0.978 at Sonnet against $0.033 at Flash), which is 35% of that book's
  entire machine cost, for a change the brief says is already owner practice.

  **Operational cost of running 3+ models per book**, which the brief does not price:
  - *Pinning*: `AL-499`/`UW-C316` establishes that `MODEL_OUTPUT_CAPS` is keyed per slug while the
    real ceiling is per endpoint (18 endpoints, 16,384 to 1,048,576, for one DeepSeek slug). Each
    additional model multiplies that exposure, and pinning must be re-probed per run.
  - *Version drift*: three tables must move together per model: `_PRICES`, `MODEL_OUTPUT_CAPS`, and
    the provider allowlist. `refresh_pricing.py` deliberately **excludes** the v4-pro row (because a
    refresh would overwrite the pinned endpoint price with the default route's, a ~25% understatement),
    so that one row is hand-maintained forever. `SKILL_MECHANISM_MODELS` is a fourth, also hand-kept,
    with the comment "no automated check ties the two together".
  - *Prompt tuning*: `strip_code_fences` exists because some models fence JSON; `llm_effort` is forced
    to `"off"` because reasoning on Claude burns the whole budget and returns `finish_reason=length`.
    Those are two per-model workarounds already, on two models.
  - *Evaluation matrix*: stages x models x bands x lengths. At 3 stages, 3 candidate models per stage
    and 18 production cells, a full re-validation is 486 cells; the S-1 grid managed 42 shells over
    two cells before the budget cap bound.
  - *Deprecation*: `openrouter_fallback_model` is the only automatic substitution and it moves cost up
    3x (C5-11). Nothing else has a documented substitution path; a retired model surfaces as a
    leg-fatal 404, and the `-preview` slug problem is already recorded in the vendor README.
- **Why it matters for the goal**: F4 is presented as implementable and nearly free. It is neither: it
  is one schema field plus four hand-maintained tables that must be kept consistent by memory, and the
  cheapest instance of it (review on V4 Flash) is not shipped despite already being owner practice.
- **Recommendation**: (1) Ship the review-model change first: set `review_openrouter_model` to
  `deepseek/deepseek-v4-flash`, add its price and cap rows, keep Sonnet as an escalation model for
  nodes Flash flags. This is the single largest available cost cut and the brief already says the
  quality is there. (2) Promote the per-stage models from `Settings` plus JSON-blob overrides into
  explicit `AuthoringPlan` fields (`fill_model`, `review_model`, `reading_level_model`) with allowlist
  validation, so the plan is the record of what ran. (3) Add a test that every model named in any of
  the four tables appears in all four.
- **How to check I'm right**: `grep -n "openrouter_model\|review_openrouter_model\|openrouter_fallback_model" src/cyo_adventure/core/config.py` gives the three defaults. `grep -n "model" src/cyo_adventure/story_requests/authoring_plan.py` shows only `prep_model` and the automated-provider pair. `grep -rn "reading_level" src/cyo_adventure/core/config.py` returns nothing.

---

## C5-8: The reading-level loop is the largest uncapped consumer and it discards its own output

- **Severity**: high
- **Category**: waste
- **Locus**: `generation/reading_level_loop.py:80` (`_BATCH_SIZE = 12`), `:658-684`;
  `generation/orchestrator.py:144` (`_DEFAULT_READING_LEVEL_PASSES = 2`); `AL-345`
- **Problem**: The loop makes `passes x ceil(out_of_band_nodes / 12)` provider calls with no aggregate
  call cap and no dollar cap. On a 632-node book with 84.5% of nodes out of band that is
  **2 x 53 = 106 calls**, more than every other stage combined.

  It is not theoretical. Decomposing the measured book 1 (C5-1): the fill accounts for ~99,400 input
  and ~99,900 output tokens; the record shows 247,600 input and 154,253 output. The residual
  (~148,000 in / ~54,300 out) is the reading-level loop, priced at $1.91/$3.83 = $0.284 + $0.208 =
  **$0.492, 46% of that book's fill-stage bill.** What it bought: `in_band = 0.155`. Nearly half the
  spend on the most expensive book delivered 15.5% band conformance.

  `AL-345` then records the failure mode that makes this worse: the post-splice gate re-check can
  block, and when it does the loop's **entire output is discarded**: 50 revised nodes thrown away on
  a paid run, the book shipping at grade 5.61 with 12% of nodes in band while still reporting
  `status=passed`. `AL-350` adds that the discard is recorded nowhere durable: one line of stdout.
  So the largest consumer in the pipeline can spend its full budget, have the result thrown away, and
  leave no trace on the job row.
- **Why it matters for the goal**: This is the clearest available instance of the brief's F7 claim
  going unexamined. F7 lists "repair loops in the harness with hard round caps" as a measured lever;
  the production reading-level loop has a round cap and no call cap, and the call count is what costs
  money. It is also the stage whose cost/benefit is worst by an order of magnitude.
- **Recommendation**: (1) Raise `_BATCH_SIZE` from 12 to ~40 (the batch output is 12 rewritten node
  bodies, ~1,200 tokens, against caps of 64,000+; the batch is 50x smaller than it needs to be): a
  3.3x call-count cut with no quality change. (2) Add an absolute call budget per book, derived from
  band. (3) Record `reading_level_calls`, `nodes_revised`, `discarded_for_gate`, and the loop's own
  token subtotal on the `generation_job` row, so `AL-345`'s discard is visible in data rather than in
  stdout. (4) Decide whether a loop that moves in-band from (unknown) to 0.155 at 46% of the bill
  should run at all at 16+.
- **How to check I'm right**: `sed -n 655,690p src/cyo_adventure/generation/reading_level_loop.py`
  shows the `for _pass_index in range(ctx.max_passes)` / `for start in range(0, len(out_of_band),
  _BATCH_SIZE)` nest with no call counter. The book-1 arithmetic: 154,253 x 3.83e-6 = 0.5908;
  1.06372982 - 0.5908 = 0.4729; 0.4729 / 1.91e-6 = 247,600 input tokens against a ~99,400-token skeleton.

---

## C5-9: Completion caps are hand-transcribed per slug, and there is no billed-but-empty detector

- **Severity**: medium
- **Category**: cap sizing
- **Locus**: `generation/skeleton.py:194` (`MAX_FILL_OUTPUT_TOKENS = 131_072`), `:248-268`
  (`MODEL_OUTPUT_CAPS`), `:296-340` (`resolve_output_cap`), `:350` (`_FEASIBILITY_MARGIN = 0.8`);
  `AL-328`, `AL-479`, `AL-499` / `UW-C316`
- **Problem**: Answering the audit question directly: sizing is **hand-set, per-slug, and partial**.
  `MODEL_OUTPUT_CAPS` is "transcribed from the OpenRouter models endpoint on 2026-08-16, not
  estimated", holds 10 rows, and clamps the global 131,072 down. It is not derived from anything, and
  it is not per-model reasoning overhead: it is the backend's declared output ceiling, which is a
  different quantity from what `AL-328` says the cap must be sized against ("size the production cap
  from the most budget-hungry supported model plus its reasoning overhead").

  What happens when a new model is added: the table is **permissive by default**: a missing row gets
  the 131,072 default. The comment that justified that permissiveness ("a length stop is leg-fatal, so
  an unknown small-output model fails fast") is retracted in the code itself by `AL-479`: the
  leg-fatal branch sits inside `if not content:`, so an over-ask that truncates **non-empty** is an
  ordinary completion that parses as nothing and then spends the entire repair budget. So a new model
  added to the allowlist without a cap row silently buys 1 fill + 3 repairs of garbage. Only a test
  (`test_every_configured_default_model_has_a_cap`) protects the *configured defaults*; a per-job
  `model_override` or an admin allowlist addition is unprotected.

  `AL-499`/`UW-C316` adds that the key is wrong in kind: the real ceiling is per **endpoint**, and one
  DeepSeek slug is served from 18 endpoints declaring 16,384 to 1,048,576 against a single table value
  of 393,216. A per-slug row is a floor pretending to be a ceiling.

  **There is no billed-but-empty detector.** `Completion.finish_reason` exists and is populated by the
  OpenAI-shaped adapters: but not by `providers/anthropic.py`, which never sets it. Nothing aggregates
  it: `UsageTotals` has no `length_stops` field, `generation_job` has no column for it, and the empty
  case raises before any usage is built (C5-4), so the one event you would count is the one event that
  is never recorded. The `AL-328` failure ("$0.5319 for 32,000 tokens of which 30,872 were reasoning,
  returned nothing") would today produce: no ledger entry, no cost, no counter, one `provider.transient_retry`
  log line.

  Also unrecorded: `reasoning_tokens` is captured per call in `TokenUsage` but **dropped by
  `UsageLedger.snapshot()`**: `UsageTotals` has no reasoning field. `AL-332`'s proposed change
  ("record `reasoning_tokens` per call so the share is observable in production") is half-done: it is
  recorded per call and discarded at the aggregate, which is the only thing that gets persisted.
- **Why it matters for the goal**: F7 names "completion caps sized to reasoning overhead" as a measured
  lever. The implemented mechanism sizes caps to declared output ceilings, not to reasoning overhead,
  keyed at the wrong granularity, with a permissive default and no detector for the failure it exists
  to prevent.
- **Recommendation**: (1) Add `reasoning_tokens`, `length_stops`, and `failed_calls` to `UsageTotals`
  and to the `generation_job` row; reasoning share is the single best cheap predictor of a model's
  real cost (`AL-332`: legs above 10% reasoning share were underestimated ~2x with no overlap).
  (2) Re-key `MODEL_OUTPUT_CAPS` on `(provider, model, endpoint)` or require a pin in config for any
  endpoint-spread slug, enforced by a test (`UW-C316`). (3) Make an unknown model's cap the *minimum*
  known cap rather than the default, i.e. fail closed. (4) Set `finish_reason` in
  `providers/anthropic.py` so the one discriminator that separates truncation from a dead endpoint is
  populated on every backend.
- **How to check I'm right**: `sed -n 240,270p src/cyo_adventure/generation/skeleton.py` is the
  hand-transcribed table with its own `#CRITICAL` note. `grep -n reasoning src/cyo_adventure/generation/usage.py`
  shows the field on `TokenUsage` and its absence from `UsageTotals`. `grep -n finish_reason
  src/cyo_adventure/generation/providers/anthropic.py` returns nothing.

---

## C5-10: On the shipped backend the output cap never resolves from the provider, so a per-job model override is invisible to it

- **Severity**: medium
- **Category**: cap sizing
- **Locus**: `generation/providers/openrouter.py:114` (only `name`, **no `model` property**);
  `generation/providers/ollama.py:164` (same); `generation/providers/fallback.py:73` (same);
  `generation/orchestrator.py:1414-1424`; `generation/provider.py:721-734`;
  `core/config.py:523` (`provider_fallback_enabled: bool = True`); `AL-432`, `UW-C271`
- **Problem**: `fill_skeleton` resolves the output cap by asking the provider for its model first,
  because "the PROVIDER is asked first ... it is the only object built with a per-job model override
  (`worker.py` passes `model_override=`), while reading `Settings` alone silently resolves the cap for
  the process default instead of for the job's model (`AL-432`)". That fix does not work on the
  shipped backend. **`OpenRouterProvider` declares no `model` property**: only `name`. Nor does
  `OllamaProvider`. Nor does `FallbackProvider`. The only adapter that declares one is
  `AnthropicProvider`, which is also the one backend with no price rows (C5-6).

  So on `generation_provider="openrouter"`: with or without the cascade, which defaults on ,
  `getattr(provider, "model", None)` returns `None` every time, and the cap falls through to
  `active_fill_model(settings)`, i.e. `Settings.openrouter_model`, the **process default**. `AL-432`'s
  stated defect is therefore still live on the path it was written for, and a passing test can hide it
  because a test provider that declares `model` exercises the branch that production never takes.

  Three consequences:
  - A per-job `model_override` (the only route by which an admin's model choice reaches the fill) has
    its cap resolved for the process default. Overriding to `deepseek/deepseek-v4-pro` (ceiling
    393,216) yields a cap of 64,000 (Haiku's), so `is_fill_feasible` returns False for skeletons that
    would have fitted and the chunked path engages needlessly: more calls, more re-sent prose
    (`chunking.py:321` resends all prior prose per batch), more money, for no reason.
  - Overriding *down* to a small-ceiling model is worse: the cap stays at the default's 64,000, the
    over-ask truncates non-empty, and `AL-479` establishes that spends the whole repair budget.
  - The cascade's fallback legs run under the primary's cap regardless. The third leg is Ollama
    (`qwen2.5:14b`), asked for a 64,000-token completion. The orchestrator registers this half as
    `UW-C271`; the `model_override` half above is not registered anywhere.
- **Why it matters for the goal**: The cap governs both what a call can cost and whether the chunked
  path (which multiplies input tokens) engages. C5-7's per-stage model selection cannot reach the
  cost-controlling decision while the cap is resolved from a process-level default.
- **Recommendation**: Add a `model` property to `OpenRouterProvider` and `OllamaProvider` (one line
  each, mirroring `AnthropicProvider:92`), give `FallbackProvider` one returning the primary leg's
  model, and clamp `max_tokens` per leg inside `FallbackProvider.complete` before delegating. Then add
  a test that constructs the provider through `build_provider` rather than through a stub, so the
  production branch is the one exercised.
- **How to check I'm right**: `grep -n "def model\|def name" src/cyo_adventure/generation/providers/*.py`
  shows `def model` on `anthropic.py` alone. `sed -n 1414,1424p
  src/cyo_adventure/generation/orchestrator.py` is the resolution, and its own `#ASSUME` names the
  cascade case while missing that the bare OpenRouter leg has the same gap.
  `grep -n provider_fallback_enabled src/cyo_adventure/core/config.py` shows the default True.

---

## C5-11: Silent failover moves the fill to a 3x more expensive model with no cost signal

- **Severity**: medium
- **Category**: waste
- **Locus**: `core/config.py:459-460`; `providers/fallback.py:118-133`
- **Problem**: The cascade's second leg is `anthropic/claude-sonnet-4.6` ($3/$15) behind a primary of
  `anthropic/claude-haiku-4.5` ($1/$5): a **3x input and 3x output** escalation. A failover emits one
  `fallback.leg_failover` warning and nothing else. There is no metric, no counter on the job row, and
  no threshold. `TokenUsage` does correctly attribute the leg that answered, so the *cost* is right;
  what is missing is any way to notice that a persistent primary outage has been quietly tripling the
  bill for a week. The per-run attempt cap (`_DEFAULT_MAX_TOTAL_ATTEMPTS`) bounds attempts, not spend,
  and `_dead` legs persist only for the life of one job, so every job re-pays the discovery cost.
- **Why it matters for the goal**: This is the "silent fallback to a costlier model" waste mode the
  audit asks about, and the answer is that nothing would notice. It compounds with C5-10: the failover
  leg also runs under the primary's cap.
- **Recommendation**: Record the leg that served each stage on the job row (the ledger already holds it
  per call), and alert on the ratio of fallback-served to primary-served calls. Consider ordering the
  cascade by cost rather than by quality, or making the fallback opt-in per band.
- **How to check I'm right**: `grep -n "openrouter_fallback_model\|provider_fallback_enabled"
  src/cyo_adventure/core/config.py`; the price rows in `core/pricing.py` give 1/5 against 3/15.
  `grep -n "leg_failover" src/cyo_adventure/generation/providers/fallback.py` is the only signal.

---

## C5-12: Scaling is linear in human review; catalog amortization is not a cost lever at any real scale

- **Severity**: medium
- **Category**: scaling
- **Locus**: ADR-005 (mandatory human approval); brief F8; `Q-1` (a child exhausts a cell by ~the
  fourth request at 3-4 skeletons/cell)
- **Problem**: Modelling from C5-1's per-book figures at 3 books/child/month and a 40/40/20 band mix
  ($1.45/book machine, 12 min average review):

  | Active children | Books/mo | Machine $/mo | Review hours/mo | Review $/mo @ $25/h | Total $/mo | Revenue @ $10/child |
  | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
  | 100 | 300 | $435 | 60 | $1,500 | **$1,935** | $1,000 |
  | 1,000 | 3,000 | $4,350 | 600 | $15,000 | **$19,350** | $10,000 |
  | 10,000 | 30,000 | $43,500 | 6,000 | $150,000 | **$193,500** | $100,000 |

  **The curve does not bend.** Every term is linear in books produced. There is no fixed cost large
  enough to amortize and no per-book term that falls with volume. Gross margin is negative at every
  scale and worsens in absolute dollars. The binding constraint is not tokens: at 1,000 children the
  programme needs 600 review-hours/month (3.5 FTE); at 10,000 it needs 6,000 (35 FTE).

  **What catalog amortization actually buys.** At 18 cells x 3-4 skeletons = 60-73 skeletons and
  10,000 children x 3 books/month, each skeleton is filled ~400 times per month. Skeleton authoring at
  C5-5's level cost ($0.2-$56 per shell depending on tier) amortizes to **$0.00004-$0.014 per book**.
  Catalog reuse is therefore **irrelevant to unit economics above roughly 100 children**. It is a
  *variety* lever (F5's real subject) and a *human-review* lever (F8: a fill over a reviewed shell asks
  less of the approver than a fill over an unreviewed one, which is exactly what `S-5` is testing). It
  should not be presented, as F1/F5's framing invites, as a cost lever.

  The one architectural change that most reduces cost per book is therefore **not** a model change.
  Ranked:
  1. **Reduce human review minutes** (sampled review of the spine plus a random path sample rather
     than every node). Saves 59-71% of all-in cost. Quality cost: it weakens ADR-005 from "a human
     approved this book" to "a human approved a sample of this book", which the ADR does not permit
     and which is a children's-safety decision, not an engineering one. This is the decision that
     determines whether the programme has viable unit economics.
  2. **Move moderation review to V4 Flash** (C5-7): saves $0.945 on a 16+ book, 35% of machine cost,
     at a quality cost the brief already argues is near zero (V4 Flash is current owner practice for
     first-pass review). Ship this first because it is free.
  3. **Cut the reading-level loop's call count** (C5-8): 3.3x fewer calls from a batch-size change,
     no quality cost at all.
- **Why it matters for the goal**: The programme's cost work is concentrated on the term that scales
  cheaply (tokens) and silent on the term that does not (the mandatory human). At 10,000 children the
  token bill is 22% of the total and the review payroll is 78%.
- **Recommendation**: Model the review-labour curve explicitly in the roadmap before committing to the
  Track 2 public launch, and put the sampled-review question in front of the owner as an ADR amendment
  with the arithmetic attached. Re-frame F5's catalog reuse as a variety-and-review-burden lever and
  drop the cost framing, which the arithmetic does not support.
- **How to check I'm right**: The arithmetic is above and rests only on C5-1's per-book figures and
  the $25/h assumption; substitute your own rate and the ratio is unchanged as long as review takes
  more than ~90 seconds per book at the medium band. `Q-1`'s exhaustion result is in the 2026-08-10
  brief section 4; ADR-005 is `docs/planning/adr/`.

---

## C5-13: The ledger has no stage attribution, so per-stage cost cannot be computed even in principle

- **Severity**: medium
- **Category**: metering
- **Locus**: `generation/usage.py:105-111` (`TokenUsage` fields), `:190-260` (`UsageLedger`);
  `generation/metered.py` (module docstring: "Nothing writes one today")
- **Problem**: The audit asks whether cost is attributable per book, per stage, per model. Per book:
  yes (one ledger per job, stamped onto `generation_job`). Per model: yes (`estimate_run_cost` costs
  each call at its own model's price, and the `cost.py` docstring is explicit about why). **Per stage:
  no.** `TokenUsage` carries `provider`, `model`, tokens, duration, reasoning: and no stage label.
  `UsageLedger` retains calls in order, and `metered.py` notes that this "leaves a per-call event log
  possible later without changing anything here. Nothing writes one today."

  So the fill, the repair loop, the stage-1 fidelity review, the reading-level loop, and every
  moderation stage all bill into one undifferentiated number. Every stage-level cost figure in this
  audit had to be reconstructed by subtracting a token estimate from a total (C5-1, C5-8), which is
  exactly the archaeology `core/pricing.py`'s own docstring says the project wants to stop doing. And
  it makes C5-7's per-stage model selection unevaluable: you cannot decide which stage to move to a
  cheaper model when you cannot see what each stage costs.
- **Why it matters for the goal**: F4's whole premise is that stages differ enough to warrant different
  models. Confirming or refuting that in production requires per-stage cost, which does not exist.
- **Recommendation**: Add a `stage: str` field to `TokenUsage`, set from a context variable or an
  explicit argument at each `complete()` site (the `stage_log` machinery already threads a stage name
  through `_RepairContext` and `ReadingLevelContext`). Persist a per-stage rollup on the job row, or
  write the per-call event log `metered.py` already anticipates. Roughly a day's work and it is the
  prerequisite for every other cost decision in this audit.
- **How to check I'm right**: `grep -n "stage" src/cyo_adventure/generation/usage.py` finds only a
  docstring reference to `_RepairContext.stage_log`. `UsageTotals.to_dict` emits five numbers and a
  boolean, with no breakdown.

---

## C5-14: The most expensive books exceed the RQ job timeout, so the highest spend has the highest abort rate

- **Severity**: medium
- **Category**: waste
- **Locus**: `core/config.py:404` (`generation_job_timeout_seconds: int = 1800`);
  `generation/queue.py:154`;
  `runs/deepseek-v4-pro-2026-08-20/report.json` book 1 `latency_s: 1874.34`
- **Problem**: The measured wall clock for the 16+ book that cost $1.064 is **1,874 s**, which is
  **74 s past the 1,800 s RQ `job_timeout`**. That measurement was taken through
  `scripts/compare_vendors.py`, which has no timeout; the same book routed through the production
  queue is killed. Books 2 and 3 came in at 687 s and 469 s, so the margin is not general: it binds
  specifically on the largest, most expensive books, i.e. the ones where an abort wastes the most money.

  RQ's SIGALRM does unwind Python, so `worker.py`'s interrupt guard runs and `_record_failure` stamps
  `cost_usd`: the spend is recorded, which is a genuine strength of the design. What is missing is
  that nothing notices the *pattern*: there is no counter for timeout-aborted jobs, no relationship
  between band and timeout, and `requeue_stranded_jobs` deliberately does not re-enqueue (correctly,
  since "the job may already have spent provider budget"), so a 16+ request simply fails and the
  family has burned one of ten monthly quota slots plus a dollar of provider spend for nothing.

  The related hole: a **SIGKILL**ed worker (OOM, power loss) does not run the guard, so the job sits
  `running` until `requeue_stranded_jobs` force-fails it with `error="interrupted: worker died"` and
  **no cost recorded at all**. That path writes `status`, `error`, and an event, and never touches
  `cost_usd`.
- **Why it matters for the goal**: The 16+ and 13-16 bands are the ones ADR-011's scale framework
  makes largest, the ones the catalog grew into (`the-last-cartage` at 99,906 tokens, 95.3% of the
  selection screen), and the ones that cost the most. They are also the ones the queue cannot finish.
- **Recommendation**: Set `job_timeout` from the skeleton's expected output tokens rather than a flat
  1,800 s, or raise the flat value to cover the measured p99 at 16+ (a 3,600 s floor covers the
  observed 1,874 s with headroom). Add a `timeout` outcome counter keyed by band. Have
  `requeue_stranded_jobs`' force-fail path write `cost_usd = NULL, cost_complete = false` explicitly
  rather than leaving both `NULL` by default, so an orphan is distinguishable from an unmeasured job.
- **How to check I'm right**: `grep -n generation_job_timeout_seconds src/cyo_adventure/core/config.py`
  gives 1800; `python3 -c "import json;print([b['latency_s'] for b in json.load(open('docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/report.json'))['books']])"` gives
  `[397.96, 1874.34, 686.93, 469.33, 48.19]`. `sed -n 250,265p src/cyo_adventure/generation/queue.py`
  shows the force-fail path writing no cost.

---

## C5-15: Two of the four spend guards F7 and 4.5 claim exist do not

- **Severity**: medium
- **Category**: waste
- **Locus**: brief 4.5 ("All three now have countermeasures in the harness (`--resume`, preflight,
  credits checks, sized caps)"); `scripts/compare_skeleton_authors.py`;
  `evidence/skeleton-author-vendors/README.md` lines 29-39
- **Problem**: Checking each claim against the harness:
  - `--resume`: **exists** (`compare_skeleton_authors.py:1036`), and the README documents its use to
    recover the 76 lost shells. Note it exists in `compare_skeleton_authors.py` only; `compare_vendors.py`
    has no `--resume` (it relies on `persist_book` writing as it goes).
  - preflight: **exists** (`compare_vendors.py:1787`, re-exported and called at
    `compare_skeleton_authors.py:861-867`), one three-token completion per pin.
  - sized caps: **exists** as a `--max-tokens` run condition recorded in `run.json`.
  - **credits check: does not exist.** The test plan's section 10 states the remedy: "every live
    invocation of `compare_skeleton_authors.py` is preceded by a credits check (`/api/v1/credits`) and
    the run report records the before/after balance, so a halt like the 2026-08-21 one is an announced
    stop, not 76 silent 402s". `grep -n "credits\|balance\|/key" scripts/compare_skeleton_authors.py`
    returns nothing. The guard against the exact failure that destroyed the registered S-1 run
    (**76 of 80 shells lost to HTTP 402 at $400.92 used of $400.00**) was specified and not built.

  Also worth stating: all four of these are **harness** guards. None is in the production request path,
  where the equivalent failure (an exhausted provider balance mid-day) surfaces as a leg-fatal 402 that
  marks the leg dead and fails over to the 3x more expensive fallback (C5-11), and then to Ollama.
- **Why it matters for the goal**: F7's fifth lever is "spend guards, because the one thing worse than
  an expensive run is a run that dies mid-grid on an exhausted balance", and the brief reports the
  matter closed. One of the three named countermeasures is unbuilt, and the failure it addresses has
  already cost this programme one registered run.
- **Recommendation**: Add the `/api/v1/credits` preflight to `compare_skeleton_authors.py` and
  `compare_vendors.py` beside the existing endpoint preflight, recording before/after balance in
  `run.json`: it is a single GET and it is already specified. In production, treat an HTTP 402 on
  the primary leg as a platform alert rather than a per-job failover, since the failover response to
  "out of money" is "spend money faster".
- **How to check I'm right**: `grep -n "credits\|balance" scripts/compare_skeleton_authors.py
  scripts/compare_vendors.py` returns nothing. `sed -n 543,546p
  docs/planning/skeleton-sourcing-test-plan-2026-08-21.md` is the specification.
  `sed -n 29,39p docs/planning/evidence/skeleton-author-vendors/README.md` records the $400.92/$400.00
  halt.

---

## C5-16: Enumerated production waste modes and whether anything would notice

- **Severity**: medium
- **Category**: waste
- **Locus**: cross-cutting; see per-row loci
- **Problem**: Direct answer to the audit's enumeration question. Brief 4.5 names three measured waste
  modes and says all three have countermeasures "in the harness": which is accurate and is also the
  finding: they are harness countermeasures, and the production path has fewer.

  | Waste mode | Production countermeasure | Would anything notice? |
  | --- | --- | --- |
  | Non-converging repair | `max_repairs=3` plus the `_signature` no-progress abort (`orchestrator.py:321,879`) | Yes, bounded and logged. Best-covered mode. `AL-513` measured the unbounded version: 14 of 15 blind grid points censored at the cap |
  | Truncated fill billed in full | Per-model cap clamp; `finish_reason=length` leg-fatal **only when content is empty** (`AL-479`) | **No.** A non-empty truncation is an ordinary completion that parses as nothing and spends the repair budget. No counter |
  | Wholesale gate rejection after full spend | none | **No.** `AL-345`: 50 revised nodes discarded, one stdout line, nothing on the job row (`AL-350`) |
  | Silent fallback to a costlier model | none | **No.** One log line; 3x cost (C5-11) |
  | Duplicated work on retry | `unique=True` RQ job ids; `requeue_stranded_jobs` does not re-enqueue running rows | Yes, this one is genuinely well handled |
  | Orphaned jobs (SIGKILL) | `requeue_stranded_jobs` force-fails after `timeout + 5 min` | Partly: the row is closed, but **no cost is recorded** (C5-14) |
  | Billed-but-unmetered calls | none | **No** (C5-4), and the run record proves it |
  | Hollow fill (39-53% delivery) | none in production | **No** (C5-3) |
  | Deterministic content-filter loop | none | **No.** `AL-492`/`UW-C309`: 7 of 7 failures on one (skeleton, brief) pair, 3 attempts x ~133 s each buying nothing, reported as a generic transient failure |
  | Cover-art spend | none | **No**, not metered at all (C5-6) |

  Four of ten modes are covered. The six that are not are, with one exception, the ones that cost
  money silently rather than loudly.
- **Why it matters for the goal**: F7's discipline is applied to the experiment harness and not to the
  product. The harness is where money is spent deliberately and watched; production is where it will
  be spent continuously and unwatched.
- **Recommendation**: The three cheapest closures, in order: (1) record failed-call usage (C5-4), which
  closes two rows at once; (2) put the fill-rate floor in the pipeline (C5-3); (3) add
  `length_stops`/`fallback_calls`/`reading_level_calls` counters to the job row, which closes three more.
- **How to check I'm right**: Each row's locus is checkable individually; the grep commands are given
  in C5-3, C5-4, C5-8, C5-11 and C5-14.

---

## Summary of the headline number

**There is no cost-per-book figure in this programme.** The best reconstruction available, showing all
arithmetic and assumptions above:

- **Fill stage, measured**: $0.047 (3-5) / $0.350 (8-11) / $0.538 (13-16) / $1.064 (16+), DeepSeek V4
  Pro, at 39-53% word delivery.
- **All-in per publishable book, reconstructed**: **$2.49 (3-5) / $6.54 (8-11) / $11.68 (16+)**;
  **$5.95 at a 40/40/20 band mix**, of which **$1.45 is machine and $4.50 is human review**.
- **Against a plausible ceiling**: at 3 books/child/month and a $10/month subscription with a 70%
  target gross margin, the programme is over budget by **4-8.5x**; at the shipped 10-book quota, by
  **13-28x**.

The claim that the framework is cost-effective is currently **assumed, not evidenced**.
