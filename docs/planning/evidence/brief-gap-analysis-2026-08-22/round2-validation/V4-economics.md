# V4: Adversarial validation of the unit-economics cluster

> **Superseded, 2026-08-30.** #784 (`2b8bc8e1`) landed
> [unit-cost-model.md](../../../unit-cost-model.md), `scripts/unit_cost_model.py` and
> `src/cyo_adventure/core/pricing.py`: a per-book cost model built from billed prose-fill records
> rather than from model defaults. **That is now the source of truth for every dollar figure**, and
> `main`'s revenue anchor is a $1.99 or $4.99 subscription, not the "$5-8 catalog subscription with
> metered credit packs" this report reasons against. The catalog arithmetic here is also wrong on its
> own terms: "86 shells" was already incorrect when written, and the authoritative census is
> [catalog-census.md](../../../catalog-census.md) (#740) at 84 shells, 81 declaring
> production-eligible, 74 reachable in an offered cell. The +1 errors match a failure to exclude
> `.narrative.json` sidecars.

Target: synthesis section 1.4 of `docs/planning/cyo-brief-gap-analysis-2026-08-22.md`, and the
prior findings C5 (all), A3, A1, C4-3.

Everything below is re-derived from primary records. Where I use an estimate I say so and give a
bracket. I broke three of the eight claims, materially corrected three more, and strengthened two.

---

## 0. What I re-measured first (because everything else moves off it)

### 0.1 The word-count correction propagates further than the synthesis says

Measured directly over `skeletons/*/*.json` by summing `words=` in every `<<FILL ...>>` directive
(**84 shells**; corrected 2026-08-30, this read "86 shells, excluding `.contract.json` /
`.lineage.json`", which is one exclusion short: `.narrative.json` is itself a sidecar suffix, so the
two narrative sidecars on `main`, `skeletons/3-5/the-lost-mitten.narrative.json` and
`skeletons/10-13/the-clocktower-cipher.narrative.json`, were being counted as shells. The
authoritative population is the census at `docs/planning/catalog-census.md`: 84 shells, of which 81
declare `production_eligible` and 74 are reachable through an offered cell. Those last two are
different numbers and are not interchangeable; every count in this report is a **file count over all
84 shells**, not a production-exposure count):

| | |
|---|---|
| 677-node book | `16+/the-tenfold-siege.json`, **42,233** commissioned words |
| Catalog maximum words | `16+/the-last-cartage.json`, **49,953** words at **632** nodes |
| Per-band median commissioned words | 3-5: 868 · 5-8: 3,526 · 8-11: 12,351 · 10-13: 14,325 · 13-16: 21,343 · 16+: 33,150 |

The brief's "677-node, ~118,000-word graph" fuses one book's node count with a word figure **2.79x**
its actual commission. Confirmed.

**But the correction is smaller than the parent brief assumed for C5, and larger for A3.** C5's
headline is built on a *measured* run record whose token counts are facts, not on the brief's word
figure; the word error touches only C5's extrapolations. A3 hard-coded `W=118,000, N=677` at line
273 and derived its entire large-book branch from it, so A3's large-book number is directly wrong.

### 0.2 A second, larger measurement error nobody found: the books deliver 4-8 output tokens per word

From `docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/` (report.json + books/ +
rerun-book4/books.jsonl), all measured:

| Book | Band | Nodes | Commissioned | Delivered words | Fill rate | in_tok (derived) | out_tok | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `the-last-cartage` | 16+ | 632 | 49,953 | 19,423 | **38.9%** | 247,613 | 154,253 | $1.0637 |
| `the-quarry-signal` | 13-16 | 267 | 18,888 | 9,997 | **52.9%** | 130,896 | 75,278 | $0.5383 |
| `the-tin-whistle-map` | 8-11 | 193 | 19,574 | 8,353 | **42.7%** | 82,778 | 50,147 | $0.3502 |
| `the-last-blue-cup` (rerun) | 3-5 | 17 | 674 | 598 | **88.7%** | 18,051 | 3,366 | $0.0474 |

Input tokens are my derivation (`in = (cost - out*rate_out)/rate_in` at the pinned
$1.91/$3.83); the record carries only `output_tokens`. All four fill rates reproduce `AL-490`.

I then opened the delivered books and counted the prose: `leaf_words` is **total body words across
all nodes**, not ending words (I verified: 19,423 = sum of all `body` word counts for book 1).
Retained text in book 1 = 25,705 body tokens + 12,471 choice-label tokens = **38,176 tokens**.

**154,253 output tokens were billed to retain 38,176 tokens of text: 4.0x.** Per delivered word the
ratio is 7.94 (16+), 7.53 (13-16), 6.00 (8-11), 5.63 (3-5). This is a model-free, arithmetic-only
finding from a committed record and it is the single largest waste signal in the programme. Neither
C5 nor A3 computed it.

### 0.3 The shipped fill model is not the model that was measured

`core/config.py:459` ships `openrouter_model = "anthropic/claude-haiku-4.5"` ($1/$5);
`:612` ships `review_openrouter_model = "anthropic/claude-sonnet-4.6"` ($3/$15). The measured run
used DeepSeek V4 Pro ($1.91/$3.83), which is **not** the production fill model. Repricing the same
measured token profiles at the shipped model:

| Band | Measured (V4 Pro) | Shipped (Haiku 4.5) |
|---|---:|---:|
| 16+ | $1.064 | **$1.019** |
| 13-16 | $0.538 | **$0.507** |
| 8-11 | $0.350 | **$0.334** |
| 3-5 | $0.047 | **$0.035** |

Haiku is cheaper on input and dearer on output, and the two nearly cancel. C5 reported measured
V4 Pro figures as if they were production cost without flagging the substitution; the substitution
happens to be conservative by 4-26%, so nothing breaks, but the audit did not check.

---

## Claim 1: all-in is $2.49 / $6.54 / $11.68, $5.95 at 40/40/20, $1.45 machine + $4.50 human

**Verdict: not sustained as a point estimate. The machine half is roughly right (I get $1.20 vs
$1.45). The human half is not an estimate of anything, it contradicts C4-3, the finding it is
presented alongside. Severity: high.**

### What I did to break it

I re-derived every line of C5's six-row table from primaries and attacked each assumption for
load-bearingness.

| Assumption | Load-bearing? | Verdict |
|---|---|---|
| Fill cost (measured) | Yes | **Holds.** Reproduces to the cent; conservative vs shipped model. |
| Moderation "est." ($0.05/$0.45/$0.978) | **Yes, 37% of 16+ machine** | **Under-specified.** See below; I get $0.98-$1.64 for 16+, central $1.26. C5 landed on the *bottom* of the defensible range. |
| Cover art $0.134 "assumed" | At 3-5 only (53% of that band's machine cost) | **Holds as a family estimate.** `covers/provider.py:42` calls `gemini-3-pro-image` at 1K 2:3 portrait, one image per version, **no retry**. A3's $0.035 is the Flash-Image rate and is wrong for this model. Unverifiable in-repo: no price row exists (C5-6 confirmed). |
| Skeleton amortization $0.10/$0.30/$0.50 | Yes, ~15% of machine | **Refuted by C5's own C5-12**, which computes $0.00004-$0.014/book above ~100 children. Since claim 2 is a *scale* claim, the correct line is ~$0.01, not $0.10-$0.50. C5 is internally inconsistent here and it inflates its own machine figure. |
| x1.25 for books that never publish | Yes | **Too narrow, wrong direction unclear.** Recorded spend gives x1.022; *attempt* failure gives x1.75 (4 of 7 recorded attempts delivered). Two of the three failures were **unmetered** ("no provider call was metered", 397.96 s and 397.59 s of wall clock each), so real waste is unknown and non-zero. Defensible bracket x1.05-x1.75. |
| Human at $25/h | Yes, 76% of the headline | Rate is arbitrary but sensitivity-neutral. |
| Human at **5 / 12 / 20 minutes** | **Yes, this is the whole number** | **Refuted.** Not derived from anything. C4-3, in the same review round, measured the surface at hours. C5's minutes are ~5-12x below its sibling finding. |

### The moderation re-derivation (C5 marked this "est." and never showed the prompt sizes)

I measured the actual prompts: `_SAFETY_SYSTEM_BATCH` is 81 tokens, `_COHERENCE_SYSTEM` 95,
`_ENGAGEMENT_SYSTEM` 181 (`moderation/stages.py`). `review_batch_size = 8` (`config.py:657`),
so safety issues `ceil(N/8)` calls; coherence and engagement are one whole-book call each; stage-1
fidelity carries beats + bodies. Input is therefore dominated by the prose, not the prompts.

The one genuinely unknown quantity is **safety output tokens per node** (a structured verdict).
At 30 / 60 / 100 tokens per node, 16+ moderation at Sonnet 4.6 is **$0.976 / $1.260 / $1.639**.
C5's $0.978 is the 30-token corner. This is unmeasurable from any committed record because
`TokenUsage` has no stage field (C5-13, verified), which is exactly why C5-13's recommendation
matters more than C5-1's.

### Re-derived cost, with a range instead of a point

Machine, per publishable book (shipped models, skeleton at scale, cover $0.134):

| Band | Fill | Moderation (central) | Cover | Skeleton | **Machine** |
|---|---:|---:|---:|---:|---:|
| 3-5 | $0.035 | $0.074 | $0.134 | $0.01 | **$0.253** |
| 8-11 | $0.334 | $0.462 | $0.134 | $0.01 | **$0.939** |
| 16+ | $1.019 | $1.260 | $0.134 | $0.01 | **$2.423** |

40/40/20 mix, pre-waste **$0.962**; x1.25 waste → **$1.20**.

| | Low | Central | High |
|---|---:|---:|---:|
| **Machine / book (40/40/20)** | **$0.54** | **$1.20** | **$4.02** |
| basis | Flash review model, x1.05 waste | Sonnet review, x1.25 waste | Sonnet review at 100 tok/node, delivery at full commission (capped 2.6x), x1.75 waste |

C5's $1.45 sits inside this and is ~20% high, entirely because of the skeleton line it refutes
elsewhere. **The machine half of C5's claim survives.**

Human review, three internally-consistent scenarios rather than one assumption:

| Scenario | 3-5 | 8-11 | 16+ | 40/40/20 |
|---|---:|---:|---:|---:|
| **R-A** C5's assumed 5/12/20 min @ $25/h | $2.08 | $5.00 | $8.33 | **$4.50** |
| **R-B** the surface as built, corrected words, 200 wpm + 3 min overhead @ $25/h | $2.50 | $25.40 | $60.80 | **$23.32** |
| **R-C** A3's sampled review, 1.75 min flat @ $10.67/h | $0.31 | $0.31 | $0.31 | **$0.31** |

**All-in: $1.51 (R-C) / $5.70 (R-A) / $24.52 (R-B).**

### What prior review missed

1. **C5-1 and C4-3 cannot both be true.** C5 prices 12 minutes of review per book as COGS. C4-3
   says the surface demands hours and that "today they ask for something no one performs." Either
   the review is happening (then C5's $4.50 is 5x too low and the all-in is ~$24) or it is not
   (then the $4.50 is not being spent and the safety claim, not the cost claim, is what fails).
   The synthesis stacks both findings as mutually reinforcing when they are in tension. **This is
   the single most important defect in the cluster** and no reviewer flagged it.
2. C5's own C5-12 refutes C5-1's skeleton-amortization line.
3. Two of three failures were unmetered, so the waste multiplier is a lower bound, not an estimate.
4. The 4.0x output-to-retained-text ratio (0.2) is a bigger cost lever than anything C5 identified
   and is measured, not estimated.

---

## Claim 2: over by 4-8.5x at 3 books/month against $10 / 70% margin; 13-28x at the 10-book quota

**Verdict: the frame is wrong; the conclusion partly survives in a different and sharper form.
Severity: high (against the claim as written).**

### What I did to break it

I went looking for actual pricing intent, which C5 did not do. It exists, in two places.

**`docs/planning/adr/adr-008-public-app-store-launch.md` decision 3** and
**`docs/planning/PROJECT-PLAN.md:1168-1170`**:

| Tier | Contents | Price |
|---|---|---|
| Free | curated starter library, one profile, offline | $0 |
| Family subscription | full public catalog, multiple profiles, offline, read-aloud, progress | **~$5-8/month, decided pre-launch** |
| **Generation credits** | metered custom-story generation | **consumable packs; "price covers LLM cost with margin"** |

Plus: Apple Small Business Program, **15% commission** (P8-09); and P8-05, "generation API
decrements credits **on accepted jobs only** (failed gate = no charge)".

So:

- **Custom generation is not bundled into the subscription.** ADR-008's rationale says it in
  terms: "the metered credit add-on converts the pipeline's marginal cost into margin." C5's
  $10-subscription-must-cover-3-books frame is not the programme's model and no document proposes
  it. C5 invented the denominator. **Claim 2 as stated: refuted.**
- The real subscription is **$5-8**, not $10, and it buys *catalog* access whose marginal cost is
  ~$0 (amortized across all subscribers). Subscription economics are not the constraint.
  **Historical as of 2026-08-30**: the `$5-8` figure and everything derived from it in this section
  are pre-#784 analysis. `2b8bc8e1` replaced the revenue anchor with a **$1.99 or $4.99**
  subscription and made `docs/planning/unit-cost-model.md` the source of truth for cost figures, as
  the notice at the head of this report says. The refutation of C5's invented $10 denominator stands
  on its own, since it turns on C5 having no source for $10 at all, but the required-price table
  below is priced against the retired anchor and must be recomputed against the current one before
  it is used for any decision.
- C5 also ignored the **15% store take**, which is written down in the plan.

### Redone against the real model

Required consumable price per book, at Apple 15% and a 70% target gross margin:
`P = COGS / (0.30 x 0.85) = COGS / 0.255`.

| COGS basis | COGS | **Required price per generated book** |
|---|---:|---:|
| Machine only (guardian reviews, unpaid) | $1.20 | **$4.71** |
| All-in, R-C sampled staff review | $1.51 | **$5.92** |
| All-in, R-A (C5's assumed minutes) | $5.70 | **$22.35** |
| All-in, R-B (surface as built) | $24.52 | **$96.16** |

**The sharper falsification, and it is against the repo's own words.** ADR-008 decision 3 states:
*"generation cost on the Haiku-primary roster is **cents per story**."* That is the programme's
only written cost claim, it is priced at the shipped model, and it is **wrong by 5x at my floor
and 40x at my central estimate, before any human cost at all**. Machine-only is $0.54-$4.02 per
book. This is a better finding than the invented $10/70% comparison because it is a claim someone
actually made, in a ratified decision record, and it is checkable.

### The exposure that is real today

`core/config.py:931` `default_monthly_story_quota = 10`, enforced as a **count** by
`story_requests/service.py:294`. No entitlement or credit ledger exists in code (`grep -rni
"entitlement" src/` returns nothing; P8-03 is not started). So the shipped default grants every
family 10 free generations per month. At central machine cost that is **$12.02/month of COGS per
family against a ~$5-8 subscription**, underwater on machine cost alone, before the human, with
the failure waste on the house by design (P8-05). That is the defensible version of C5's "13-28x".

### What prior review missed

C5 never read ADR-008 or PROJECT-PLAN Phase 8. The entire monetization design, metered credits,
$5-8 not $10, 15% Apple take, failures free to the customer, was sitting in the planning tree.

---

## Claim 3: A3 independently derived $0.58/book with the human at 71%

**Verdict: the convergence is real but weak, and the synthesis overstates it. Severity: medium.**

### What I did to break it

I compared the two derivations line by line.

| | C5 | A3 |
|---|---|---|
| Fill cost basis | measured run record | first-principles token model |
| Human review time | 5/12/20 min (asserted) | **1.75 min flat, every band** (A3 line 644) |
| Human rate | $25/h | $10.67/productive hour offshore |
| Human cost/book | $4.50 | **$0.311** |
| All-in median book | $5.95 | **$0.575** |
| Large book | $11.68 | $3.88 (at W=118,000) |

They agree on **one ordinal statement**, the human is the largest single line, and disagree on
its magnitude by **14.5x**, and on all-in by **10x**. A3's $0.58 is a *ceiling* derived from
assumed subscription arithmetic (B-1 $12.99, B-7 30% COGS); C5's $5.95 is a *cost*. Comparing them
as "two reviewers reached this independently" compares a ceiling to a cost and calls the gap
agreement.

Worse: A3's own model **assumes away the problem it later names**. It charges $0.311 of review for
a 118,000-word book and $0.311 for a 674-word book, then argues at line 619-629 that "118,000 words
/ 250 wpm = 7.87 hours per book ... the review surface must be O(1) in book size". Its cost table
already assumes the O(1) surface exists. The impossibility result and the P&L are inconsistent
inside one document.

**How much weight the convergence deserves:** it is worth something, because two reviewers with
different information reached "the human dominates" without coordinating, and A3 could not have
been anchored on C5's numbers (it had no repo access and used a different price sheet, a different
wage, and a different book model). But both were reasoning from the same generic prior, *human
labour is expensive relative to 2026 token prices*, which is true of essentially any
LLM-plus-review pipeline and required no evidence from this programme. The convergence supports
the **direction** and supports **nothing about the magnitude**. Synthesis 1.4 presents the
tabulated dollars as jointly corroborated; they are not.

One thing A3 got right that C5 did not: A3 costed **cover art as a first-class line** and noticed
that at the small end it is 23% of unit cost. C5 buried it as an "assumed" row.

---

## Claim 4: no cost-per-book number anywhere; no runtime spend cap; `_MAX_COST_USD` is an overflow clamp

**Verdict: fully verified. Severity: critical. Strengthened.**

- `generation/cost.py:43` `_MAX_COST_USD = Decimal("999999.999999")`, used at `:119` as
  `if amount > _MAX_COST_USD: return _MAX_COST_USD, True`. The surrounding `#CRITICAL` comment
  states its purpose explicitly: the `Numeric(12,6)` column at `db/models.py:2693` raises
  `numeric field overflow` at COMMIT, which would double-fault the interrupt guard. It is a
  database-column guard. **Not a budget.**
- `grep -rn "cost_usd" src/ scripts/`: three writers (`worker.py:263`, the model, the vendor
  harness), **zero readers**. No API route, no admin surface, no aggregation, no rollup.
- `grep -rn "cost\|budget\|usd" src/cyo_adventure/generation/metered.py`: **no output at all.**
  The single chokepoint every provider call passes through knows nothing about money.
- `story_requests/service.py:294` compares a **count**, `resolve_family_quota(family)`, against
  `spent`. Nothing in the request path is denominated in dollars.
- No `review_minutes` / dwell / duration column exists anywhere. `reviewed_at` exists only on
  `story_request` (the guardian's upstream intake gate), never on storybook approval.

**Strengthening it:** ADR-008's own trade-off section lists the mitigation for "Public LLM
generation is a cost-abuse surface" as *"metered credits, per-family quotas, **global cost caps**,
rate limiting."* Three of those four do not exist. Claim 4 does not merely find a gap; it
refutes a stated control in a ratified ADR. That framing should replace the current one.

---

## Claim 5 (C5-5): repriced at list, the Anthropic S-1 legs cost $33-126 vs DeepSeek's $1.30

**Verdict: direction verified, magnitude overstated, and the asymmetry is misdescribed.
Severity: medium.**

### What I did to break it

I re-read every record in `.worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/runs/`.

1. **The "$1.30 DeepSeek" figure.** Summing every measured DeepSeek record across e1, e1r3, smoke
   and smoke2 at the pinned rates: v4-pro $0.808 + $0.991 + $0.148 + $0.249 = $2.195; v4-flash
   $0.057 + $0.096 + $0.031 = $0.184. **Total $2.38.** C5 said $2.376. **Independently confirmed.**
2. **The asymmetry is not what C5 says.** In `e1r3-tools-2026-08-21`, **every** leg has
   `input_tokens = output_tokens = latency_s = 0/null`: DeepSeek included (42 records, all seven
   legs). So in the run that produced the recommendation, *no* leg is measured; both sides are
   reconstructions. C5 describes it as measured-vs-unmeasured. It is unmeasured-vs-unmeasured.
3. **C5's bracket floor is too high.** There *is* one apples-to-apples measured Anthropic leg:
   `anthropic-sonnet-5` in e1, 16 attempts, 25,407 in / 143,616 out = **$1.487, i.e. $0.093 per
   attempt** at $2/$10. Against e1's `deepseek-v4-flash` at $0.0036/attempt that is **26x**,
   measured, on the same grid. Costing the four subagent legs at 6 attempts each on that measured
   per-attempt profile, scaled by tier list price, gives a **floor of ~$9.5** for the four legs
   (haiku $0.28, sonnet $0.84, opus $4.18, fable >=$4.18). C5's Method A ($36.7) is already an
   upper-ish estimate because it bills **every checker invocation** (24-51 per leg) as a fresh
   model turn with accumulated context, which nobody recorded either way.

**Corrected bracket: the four off-bill legs cost $9.5-$125 at list, against $2.38 measured for
DeepSeek, 80% to 98% of the true experiment bill, not 96-99%.** The recommendation still inverts
on a level basis; the inversion is 26x measured / ~190x at Opus-tier list, not "30-130x" as a
tight interval.

Pass rates verified from the records: fable 6/6, opus 6/6, sonnet 4/6, kimi 5/6, haiku 3/6,
flash 3/6, **v4-pro 0/6**.

### What prior review missed

That the "zero provider cost" framing and the missing tokens are the *same* defect applied to all
seven legs, and that one measured Anthropic leg already exists in the evidence tree and gives a
harder floor than either of C5's two reconstructions.

---

## Claim 6 (C5-8): the reading-level loop was 46% of a measured 16+ book's bill for `in_band` 0.155, uncapped

**Verdict: the structural finding is verified; the 46% is not derivable and is probably an
underestimate. Severity: high (the finding), medium (the arithmetic).**

Verified in code (`generation/reading_level_loop.py:658-684`): `for _pass_index in
range(ctx.max_passes)` over `for start in range(0, len(out_of_band), _BATCH_SIZE)` with
`_BATCH_SIZE = 12` (`:80`) and `_DEFAULT_READING_LEVEL_PASSES = 2` (`orchestrator.py:144`). No
call counter, no dollar bound. `in_band = 0.155` after the loop is in the record. The
`AL-345` discard path is real.

One correction C5 missed in its favour: there **is** a `no_progress_abort` break when a pass
accepts nothing, so the call count is bounded at `passes x ceil(N/12)` = 106, not unbounded.
It is uncapped by *budget*, not by *count*. C5-2 says "no cap on the call count," which is wrong
as written.

**The 46% cannot be derived the way C5 derived it.** C5 subtracted an assumed fill footprint
(~99,400 in / ~99,900 out) from the record. The ~99,900 output figure is the *skeleton's* token
size, not the fill's output; the fill's actual retained output is 38,176 tokens (measured, 0.2
above). Redoing it from the loop's own mechanics, 2 passes over ~534 out-of-band nodes at
25,705 body tokens total gives ~43,400 output and ~50,000 input tokens, i.e. **~$0.26, 25% of the
bill**. Redoing it as a residual against measured retained text leaves **$0.60+, 57%**. The honest
statement is *"somewhere between a quarter and three-fifths of the bill, and the pipeline cannot
tell you which, because `TokenUsage` has no stage field."* That makes C5-13, not C5-8, the finding
that has to be fixed first.

---

## Claim 7 (C4-3): review time measured at 3.0-8.3 hours/book vs ADR-005's "a few minutes"

**Verdict: the surface finding is verified; the hours are normative, not measured, and the range
needs restating. Severity: high (the finding), medium (the number).**

### What the review surface actually requires

Verified in code, not inferred. `frontend/src/admin/ReviewDetailPage.tsx:601` renders
`readThrough.reachable.map(...)`, every reachable node as a card, and `:624` appends every
unreachable node. `frontend/src/guardian/storyReadThrough.ts:175-208` is a stack-based DFS
pre-order, not a path enumeration. No pagination, no sampling, no elision, no risk order.
`api/approval.py:145` `approve_storybook` takes `storybook_id` and an optional visibility: no
version, no attestation, no acknowledgement. All confirmed.

### Re-measured with corrected word counts

The reviewer sees body prose **plus choice labels** (both render on the card).

| | Visible words | @250 wpm | @150 wpm |
|---|---:|---:|---:|
| Largest book **as actually delivered** (`the-last-cartage`, 19,423 + 9,243) | 28,666 | **1.9 h** | **3.2 h** |
| Largest book **at full commission** (49,953 + labels) | 73,725 | **4.9 h** | **8.2 h** |
| 8-11 as delivered | 11,628 | 47 min | 78 min |
| 8-11 at full commission | 27,248 | 1.8 h | 3.0 h |
| 3-5 as delivered | 598 | 2.4 min | 4.0 min |

So C4's "3.0-8.3 h" is **approximately right for a correctly-filled largest book** (4.9-8.2 h) and
**~1.7x too high for the books the pipeline actually produces today** (1.9-3.2 h). Its low end
should be 1.9 h. Against ADR-005's "a few minutes" (line 97, line 119) the gap is **23-38x as
delivered, 59-98x at full commission**, the same order as C4's 35-100x, so the finding stands.

### The attack that lands

**"3.0-8.3 hours assumes reading every word" is exactly right, and nothing requires it.** The page's
own comment describes the overview as "the skim entry point ... before deciding whether to read
every passage **or jump straight to the flagged ones**," and Approve requires no evidence of
either. So the hours figure is *what a conscientious reviewer would spend*, not *what is being
spent*. It is a normative upper bound on the control, not an operating cost.

**Consequence, and this is the cluster's central error:** C5 multiplied a review-time number by a
wage rate and put it in a COGS table. You cannot book as COGS labour that C4 says is not being
performed. Either:

- staff genuinely read the books → all-in is ~$24.52/book (R-B), 4x C5's headline, and the
  economics are far worse than the synthesis says; or
- staff skim the flagged set → the review labour line is small (R-C-like, ~$0.31-$2), the all-in is
  ~$1.5-$2, the economics **close comfortably**, and what fails is ADR-005's safety guarantee, not
  the P&L.

The programme is in the second state and describing itself as if it were in the first. **The
finding is a safety finding wearing a cost finding's clothes.** No reviewer said this.

---

## Claim 8: F4 and F7 optimise the ~24% of the bill that is not binding

**Verdict: sustained, and stronger than stated, with one qualification the synthesis omits.
Severity: n/a (validation).**

### The quantitative ceiling on the fill-stage fixes

Machine cost, 40/40/20 mix, central: **$1.20**. Every fill-stage lever, priced individually on
the measured token profiles:

| Lever | Saving / book (mix) | Basis |
|---|---:|---|
| Move moderation review Sonnet 4.6 -> V4 Flash | **$0.461** | measured token profile x price ratio (30x) |
| Timeout/retry fix (waste x1.25 -> x1.05) | **$0.192** | measured failure records |
| Reading-level: 2 passes -> 1 | **$0.033** | ~21,700 output tokens on 16+, x0.2 band weight |
| Prompt caching, 40% hit at 0.1x on fill input | **$0.032** | 247,613 in on 16+, x0.2 |
| `_BATCH_SIZE` 12 -> 40 (3.3x fewer calls) | **$0.006** | saves per-call instruction overhead only; output is the same nodes either way |
| **Total realistic** | **~$0.72** | |

Floor after all fixes: **$0.54/book machine** (my Low column, independently derived).

So the maximum the entire F4/F7 programme can deliver is **about $0.72 per book**, and **zeroing
machine cost entirely saves $1.20**:

| All-in scenario | Machine share | F4+F7 ceiling as % of bill |
|---|---:|---:|
| R-B (surface as built) $24.52 | 4.9% | **2.9%** |
| R-A (C5's minutes) $5.70 | 21.1% | **12.6%** |
| R-C (sampled review) $1.51 | 79.5% | **47.7%** |

**Claim 8 survives at 3-13% under any staff-review structure.** The synthesis's "~24%" is close to
my R-A figure of 21%.

### The qualification the synthesis omits

Under R-C, and under the guardian-primary structure both blank-slate reviewers recommend, the
human line goes to **zero paid dollars** and machine cost becomes ~80-100% of COGS. **F7 is not
non-binding in general; it is non-binding *conditional on paid staff review surviving*.** If the
recommendation the synthesis endorses is adopted, the recommendation the synthesis dismisses
becomes the whole problem. Section 1.4 should say "F4/F7 optimise 3-13% of the bill *today*, and
80%+ of it in the world section 1.4 recommends."

---

# Recommendation review

## R1. Produce a cost-per-book number

**Endorse, with a scope change.** A single dated `cost-per-book.md` is worth having, but the
binding number is **review minutes**, not tokens, and it is the one thing a document cannot
manufacture. Sequence it: (a) `review_minutes` on the approval action *first*, it is a
timestamp diff, and until it exists every cost document is a re-run of this argument;
(b) `stage` on `TokenUsage` second; (c) the document third, once two of its six lines are
measurements rather than estimates.

Also: the document must state the **commissioned-vs-delivered** basis. Every figure in this
cluster is per *delivered* book at 39-53% fill. A pipeline fixed to deliver its commission costs
~2.3x more. A cost document that does not say which basis it uses will be misread within a month.

## R2. Add a `stage` field to `TokenUsage`

**Endorse, highest priority of the four.** This is the finding that unblocks the others: C5-8's
"46%" and C5-1's moderation row are both unfalsifiable today, and both would be facts with this
field. `metered.py`'s docstring already anticipates the per-call event log; `_RepairContext` and
`ReadingLevelContext` already carry a `stage_log`. Set it from a context variable at the
`complete()` site.

Add one field the audit did not ask for: **`retained_output_tokens`** (or compute it at job end as
delivered text tokens / billed output tokens). The 4.0x ratio in 0.2 is the largest measured waste
in the programme and nothing today would surface it.

## R3. Enforce a runtime per-book spend ceiling

**Endorse the control; the proposed design as written is unsafe. Here is the failure behaviour it
needs.**

Is it safe? Yes, but only because of a property of this codebase that the recommendation does not
name: `worker.py::_record_failure` is **total**, its docstring states the whole cost path
(`usage`, `cost`, `core.pricing`) contains no `raise`, so a budget exception raised mid-run lands
in the existing pipeline-exception path and still stamps `cost_usd`, `input_tokens`,
`output_tokens`, `provider_call_count`. A ceiling that raises is therefore already
accounting-correct. That is the precondition; verify it holds before shipping.

What happens to a half-generated book, designed:

1. **Raise at the chokepoint, not at the stage.** `MeteredProvider.complete` is the single point
   every call passes through. Check *before* issuing: `if spent + worst_case(this call) > budget:
   raise BudgetExceededError`. Checking after the call means the ceiling is always breached by one
   call, and on a 16+ book one call is up to 131,072 output tokens.
2. **Never mid-fill-batch.** The ceiling must be evaluated at **stage boundaries** as a soft check
   and at the chokepoint as a hard backstop. Tripping mid-batch discards a batch's output that was
   already paid for, the exact `AL-345` pathology (paid output thrown away) reproduced as a
   feature.
3. **Degrade, don't abort, where the stage is optional.** Reading-level (Stage D) and repair are
   *improvement* stages; the book is structurally valid without them. Budget exhaustion there
   should **skip the remaining passes and record `budget_degraded=true` on the job row**, not fail
   the book. Budget exhaustion during *fill* or *moderation* must fail, because a partial fill is
   an incomplete book and unmoderated prose must never reach `in_review`.
4. **Terminal, not retryable.** `BudgetExceededError` must classify as **permanent**. Every
   provider adapter's transient path retries; a budget error routed there would burn the overage
   three more times. `requeue_stranded_jobs` already refuses to re-enqueue on the stated grounds
   that "the job may already have spent provider budget", same reasoning, make it explicit.
5. **Do not consume the family's quota slot.** Today a failed 16+ job burns one of ten monthly
   requests plus real spend, for nothing. Under P8-05's "failed gate = no charge" rule a
   budget-aborted job must refund the count too, or the control converts an operator cost problem
   into a customer-facing one.
6. **Retain the partial artifact** per ADR-007 (raw-output retention) and surface it to an
   operator, so a book that tripped at 90% can be finished by raising its budget rather than
   re-run from zero at full cost. Without this the ceiling *increases* total spend on the books it
   fires on.
7. **Set the budget from the band, and log the distribution before enforcing.** Ship it in
   shadow mode (`would_exceed=true` recorded, nothing raised) for one cycle. A ceiling calibrated
   on four books is a ceiling that fires on the 40% tail.

Suggested initial budgets from my central machine figures, at ~2.5x the observed median so the
control catches pathology rather than variance: 3-5 $0.30 · 5-8 $0.60 · 8-11 $1.20 · 10-13 $1.60 ·
13-16 $2.00 · 16+ $3.50.

**One thing the recommendation gets wrong by omission:** a spend ceiling does not solve the
problem this cluster identified. It bounds the tail of a term that is 5-21% of the bill. It should
be shipped because unbounded per-account spend is indefensible in a consumer product, not because
it improves unit economics. Do not let it be scored as the economics fix.

## R4. Guardian-primary approval with staff as risk-triggered second line

**This is the recommendation that matters and it is the one the reviewers were least equipped to
make. Verdict: not viable as stated; viable in a narrowed form. Three blockers, in order of
severity.**

### Blocker 1 (fatal as stated): it reverses an explicit, twice-ratified owner decision, for
reasons the reviewers never saw

`adr-005-mandatory-human-approval.md:18-42` is an **amendment dated 2026-06-30** that moved the
approver **from the child's parent to a global admin**, "confirmed by the project owner", and
**reconfirmed 2026-07-16** during the capability-register review. Its stated rationale:

> "The admin screens content **cross-family**: the approval router requires `principal.is_admin`
> ... `authorize_family` is intentionally not called on approval routes because the safety-review
> authority spans families." ... "Centralizing the screen in a trained safety operator raises the
> floor on review consistency versus a per-parent approval."

And the ratification note assigns the guardian a *different* control point: "the admin is the
safety gate on AI output (register item A6), and the guardian's control point is upstream, as the
**cost gate on generation spend** (ADR-015, register G7)."

A1 and A3 had no repo access and could not know this. The synthesis, which did, presents
guardian-primary approval as an open product question. It is a **decided** question, and the
decision went the other way, twice, on child-safety grounds. Reopening it is legitimate; presenting
it as unconsidered is not.

### Blocker 2 (structural, and it constrains any narrowed form): the approve action can publish
cross-family

`publishing/state_machine.py:56-66` defines `Visibility = {family, catalog}`; the docstring says
`catalog` "shares it with **every family's** guardian browse-and-assign surface."
`api/approval.py:157` reads that visibility off the approve request body.
`api/library.py:420,565` confirm a `catalog` book is readable cross-family.

So the approve action a guardian would be handed is the same action that publishes into other
families' libraries. **Guardian-primary approval is only coherent if the action is split**:
guardian approve -> `visibility=family` **only**, hard-enforced server-side; `visibility=catalog`
remains admin-only. That split does not exist today and is not in either reviewer's
recommendation. It also caps the saving: any book intended for the shared catalog still needs the
paid human, so the guardian route saves review labour only on single-family books.

Note also ADR-016's connected-families recommendation ring: a family-visibility book that gets
*recommended* to a cousin's family is a guardian-approved book reaching another family's child by
a different door. Check that path before shipping.

### Blocker 3 (compliance): COPPA is not the obstacle; the App Store is

I read ADR-018 and ADR-008 specifically for this.

- **COPPA / KWS (ADR-018 D1)** governs **verifiable parental consent for the collection and use of
  a child's personal information**. Content approval is not a COPPA-regulated act. A guardian
  approving their own child's book raises **no COPPA issue** and, if anything, is more consonant
  with the parental-control posture. ADR-018's D2 (child-directed, confirmed 2026-08-06) and D3
  (US-only, confirmed 2026-07-20) do not bear on it either. **The reviewers' implicit worry here is
  unfounded**, and note that the KWS legs are wired against the **Test** environment only
  (CLAUDE.md, 2026-08-09), so no VPC is live regardless.
- **The real compliance exposure is ADR-008 decision 5 and the trade-off note.** ADR-008 commits
  to a Kids Category listing and mitigates the AI-content rejection risk with *"detailed review
  notes on the **pre-moderated pipeline**"* and the assertion that *"Children never trigger
  generation and never see raw model output."* If the mandatory human becomes the child's own
  parent, the pipeline is no longer *operator*-pre-moderated; it is user-moderated with automated
  screening. That is a materially different App Review submission for a Kids Category app whose
  differentiator (ADR-008 Positive: "The safety pipeline becomes a marketable differentiator") is
  precisely the operator screen. This is a **rejection-risk and positioning** question, and it is
  the one that should be put to the owner, not a privacy question.

### What is actually viable

Not "guardian-primary." Rather, in ascending order of what it costs to give up:

1. **Fix the surface first, and re-measure before deciding.** C4-3's recommendation (paths not
   nodes, risk-ranked order) plausibly takes the 16+ book from 1.9-3.2 h to ~30-60 min without
   touching who approves. At $25/h that is **$48-80 falling to $12.50-25: a $23-67 saving on a
   16+ book, and roughly $17/book on the 40/40/20 mix** - 24x the entire F4+F7 ceiling of $0.72.
   **This dominates the guardian question and requires no ADR amendment.** It should be done
   first and the economics recomputed after.
2. **Guardian approval for `visibility=family` books only**, staff retained for `catalog`,
   with the split enforced server-side. Requires an ADR-005 amendment and an App Review position.
3. **Sampled staff review** (spine + random path sample). Weakens ADR-005 from "a human approved
   this book" to "a human approved a sample". C5-12 says correctly that this is a children's-safety
   decision, not an engineering one.

Whichever is chosen, the ADR-005 amendment must also fix the **"a few minutes"** claim at
lines 97 and 119, which is false above the 5-8 band by 23-98x and is the sentence that let this
cost never get modelled.

---

# What everyone missed

1. **C5-1 and C4-3 are in direct contradiction and the synthesis fuses them.** You cannot book
   12 minutes of review as COGS and simultaneously find that the surface demands hours nobody
   spends. The programme is not over budget by 4-8.5x on a review cost it is paying; it is
   **under-reviewing at a cost nobody has measured**. Restating 1.4 around that inverts what the
   finding is *about*: it is a safety finding, and the cost table is its symptom.

2. **4.0x of output tokens do not become text.** 154,253 billed output tokens produced 38,176
   tokens of retained prose on the largest measured book, and the ratio holds at 4.2-5.9x across
   all four books and both bands. This is measured, model-free, and larger than every lever in
   F7 combined. Nobody computed it, because nobody opened the delivered books and counted.

3. **The programme's own written cost claim is falsifiable and false.** ADR-008 decision 3:
   "generation cost on the Haiku-primary roster is cents per story." It is $0.54-$4.02 machine-only.
   That is a better target than an invented $10/70% frame, and it is in a ratified decision record
   that Phase 8 will be built against.

4. **The actual monetization design was in the repo and no cost reviewer read it.** Metered credit
   packs, not a bundled subscription; $5-8 not $10; 15% Apple take; "failed gate = no charge" so
   the 40% failure rate is entirely the operator's. Every one of those changes the arithmetic.

5. **The shipped 10-book quota is an uncapped free entitlement.** No credit ledger exists
   (P8-03 not started). `default_monthly_story_quota = 10` is enforced as a count. At central
   machine cost that is $12.02/family/month against a $5-8 subscription, underwater on machine
   cost alone, today, with no human in the picture. This is the concrete exposure and it is not in
   any finding.

6. **`near_cap` is broken and it is a cost signal.** `compare_vendors.py:297` computes
   `output_tokens >= max_tokens * 0.95` where `output_tokens` is the **ledger total across every
   call** and `max_tokens` is the **per-call cap**. On any multi-call book it reports headroom
   exhaustion that did not happen. Book 1's `near_cap: true` means only that the book emitted
   >124,518 tokens in total. Every conclusion drawn from that flag about cap sizing (C5-9, C5-10)
   is reading a broken instrument.

7. **The 40/40/20 band mix is unevidenced and the catalog contradicts it.** The catalog is
   3-5: **11**, 5-8: 9, 8-11: 12, 10-13: **15**, 13-16: 19, 16+: 18, **44% of shells are 13-16 or
   16+** (corrected 2026-08-30: this read `3-5: 12 ... 10-13: 16 ... 43%` and summed to 86, because
   the two `.narrative.json` sidecars, one in each of those two bands, were counted as shells; the
   corrected mix sums to the census's 84 and the share becomes `37/84 = 44%`),
   the two most expensive bands, in an app whose vision statement says "for kids". Either the
   catalog is mis-invested relative to demand, or the mix is far more expensive than 40/40/20.
   Nobody checked, and the mix is the multiplier on every headline number.

8. **Nobody costed the thing that would actually be sold.** Under the credit model the deliverable
   is a *price per generated book*: $4.71 (machine only) to $96 (surface as built). A parent will
   not pay $22 for one custom story. That number, not a margin ratio, is the decision.
