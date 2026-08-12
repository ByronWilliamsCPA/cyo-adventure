---
title: Cross-vendor fill comparison
description: Run configuration for the vendor-versus-task idiom floor measurement.
---

# Cross-vendor fill comparison

Inputs for `scripts/compare_vendors.py`. The question is whether the residual shared-idiom floor
is a property of *the task* (skeleton, band, prompt) or of *the vendor* (one model's house style).
Those imply opposite diversification strategies, and neither number exists today.

## Why these skeletons

`--skeleton` pairs index-wise with `--briefs`, so skeleton *i* is filled with brief *i* by every
vendor. Structure is therefore constant across the vendor axis (which isolates prose idiom) and
varies across the brief axis (which is what makes a within-vendor pair share nothing but the model
and the age band, the condition the 3.3 floor was measured under).

The four 5-8 skeletons below were chosen against four constraints:

1. **Same age band.** A cross-band pair would measure band difference, not vendor difference.
2. **Independently authored.** None has a `.lineage.json`, so no two are mutation siblings sharing
   a structural ancestor. In the 8-11 band four of nine are mutation-derived.
3. **Inside the single-call output cap.** `fill_skeleton` sends the whole skeleton and expects the
   whole filled document back under `_MAX_TOKENS_PROSE` (32,000). These four project to 21% to 36%
   of that. Every original skeleton in the 13-16 and 16+ bands projects *over* it, and most of
   10-13 does too; those are authored offline through the `cyo-author` skill rather than through
   this path.
4. **Comparable book length to the calibration.** At 2,594 to 4,326 fill words these sit close to
   the ~2,801-word books the 3.3 figure was computed over, so the rate is measured on similar mass.

| # | Skeleton (`skeletons/5-8/`) | Topology | Fill words | Brief premise |
| - | --- | --- | ---: | --- |
| 0 | `the-lantern-festival.json` | loop_and_grow | 2,915 | lantern that will not float |
| 1 | `the-night-market.json` | open_map | 4,326 | lost puppy among the stalls |
| 2 | `the-school-garden-mystery.json` | open_map | 2,594 | something eating the bean shoots |
| 3 | `the-snow-day-expedition.json` | time_cave | 2,747 | siblings mapping a snowed-in garden |

All four declare `age_band: 5-8`, `reading_level` target 2.5 with tolerance 1.5, tier 1, prose, and
`production_eligible: true`. The topologies differ deliberately: if a vendor effect showed up on
only one topology that is worth seeing.

## Why these vendors

Six legs across five labs, approved 2026-08-12. Four labs contribute one checkpoint each; Anthropic
contributes two, because Sonnet 5 is what the pipeline runs today and 4.6 is what it ran before, and
whether a version bump moves the floor is a separate and cheaper question than whether a vendor
does.

| Leg | Model | Pinned backend | $/MTok in / out | 4-book cost |
| --- | --- | --- | ---: | ---: |
| `anthropic-sonnet-4.6` | `anthropic/claude-sonnet-4.6` | `amazon-bedrock/global` | 3 / 15 | $0.61 |
| `anthropic-sonnet-5` | `anthropic/claude-sonnet-5` | `amazon-bedrock/global` | 2 / 10 | $0.41 |
| `openai-gpt-5.6-sol` | `openai/gpt-5.6-sol` | `azure` | 5 / 30 | $1.19 |
| `xai-grok-4.6` | `x-ai/grok-4.6` | `xai/zdr` | 2 / 6 | $0.28 |
| `moonshot-kimi-k3` | `moonshotai/kimi-k3` | `moonshotai/mxfp4` | 3 / 15 | $0.61 |
| `google-gemini-3.1-pro` | `google/gemini-3.1-pro-preview` | `google-vertex/global` | 2 / 12 | $0.47 |

Both Anthropic legs share one backend deliberately, so the version-bump control differs by checkpoint
and nothing else.

The two Anthropic legs declare `"family": "anthropic"`. Everything else leaves `family` unset and
falls back to its own label, so it is its own lineage.

Matching is on **tier, not price**. OpenAI's flagship costs 2.5x Anthropic's, and the cheaper
`gpt-5.6-terra` and `-luna` exist; a surprising result from a mid-tier model could not be told apart
from a house-style finding, so the slate compares flagships and accepts the uneven bill.

### Why pin a backend at all

`vendors.json` pins each slug to one provider tag. An OpenRouter slug is not a vendor: verified on
2026-08-12 against `GET /api/v1/models/{id}/endpoints`, `anthropic/claude-sonnet-4.6` alone has
seven endpoints across four provider names, so an unpinned run attributed to Anthropic can be
answered by Bedrock. The adapter sends `allow_fallbacks: false` alongside the pin, so a substitution
becomes a visible error rather than a silent one, and a pin that matches nothing fails on the first
call rather than quietly routing elsewhere.

Three details the endpoint listing makes clear and the slug alone does not:

- **A closed-weight model's backends all serve the same dated snapshot, at the same price**
  (`anthropic/claude-4.6-sonnet-20260217`, `anthropic/claude-sonnet-5-20260630`,
  `openai/gpt-5.6-sol-20260709`, `google/gemini-3.1-pro-preview-20260219`,
  `x-ai/grok-4.6-20260810`). For those the pin buys a single serving stack and reproducibility, not
  a different model, and every one of them reports quantization as `unknown`.
- **An open-weight model's backends do not.** `moonshotai/kimi-k3` has **fourteen** endpoints across
  twelve resellers at genuinely different quantizations: `morph/fp4`, `deepinfra/bf16`,
  `baseten/fp8`, `moonshotai/mxfp4`, and five more reporting `unknown`. The default route is Morph
  at fp4. This is the concrete case that turns "pin the provider" from a precaution into a
  requirement, and it is why the run pins the first-party Moonshot endpoint.
- **A provider name covers several service tiers.** `openai` alone is standard, `openai/flex` and
  `openai/priority` sit at half and double the price for identical weights; Google and xAI do the
  same. The pins target standard tiers, except xAI where `xai/zdr` (zero data retention) is offered
  at the *same* price as standard and is the better default for a children's product.

### Resolving is not reaching

Three of the six pins here are **not** the vendor's own endpoint, and that is not a preference. This
account's OpenRouter data policy excludes the first-party endpoints of Anthropic, OpenAI, and Google
AI Studio while permitting the same models served through Amazon Bedrock, Azure, and Google Vertex.
An unpinned call to `anthropic/claude-sonnet-5` therefore succeeds and silently lands on Bedrock,
which is the exact unattributability the pin exists to prevent.

Two traps follow, both of which cost a failed run to find:

- **`GET /models/{id}/endpoints` lists endpoints the account cannot use.** Every slug resolving is no
  evidence that any of them will answer. Reachability has to be probed with a real completion,
  which is what the pre-flight below does.
- **`provider.order` reports the wrong reason.** A pin at a blocked endpoint with
  `allow_fallbacks: false` returns `404 No endpoints found for <model>`, which reads as a bad slug.
  The same request with `provider.only` returns the actual cause: `No endpoints available matching
  your guardrail restrictions and data policy`. Diagnose with `only`, then pin with `order`.

Endpoint **tags** (`xai/zdr`, `moonshotai/mxfp4`, `amazon-bedrock/global`) are routable in both
fields, and are what the pins use: a tag fixes region, service tier, and quantization, where a
provider name alone fixes none of the three.

A `-preview` slug can be retired without notice, and Gemini is the one such slug here, so this has
to be re-verified per run rather than trusted from the last one. Every live run therefore begins
with a pre-flight: one three-token completion through each pin, all six attempted even after the
first failure (a data policy usually blocks several at once, and converging one pin per run would
take as many runs as there are bad pins). It prints a reachable/unreachable line per leg and exits
non-zero before generating anything if any leg failed, so a mispinned slate costs one cent instead
of a partial run. `--mock` skips it; there is nothing to reach.

## Running it

Dry run first. It proves the plumbing with no network and no cost, and its verdict line is
replaced with a disclaimer so the saturated mock numbers cannot be quoted as a result:

```bash
uv run python scripts/compare_vendors.py \
  --skeleton skeletons/5-8/the-lantern-festival.json \
  --skeleton skeletons/5-8/the-night-market.json \
  --skeleton skeletons/5-8/the-school-garden-mystery.json \
  --skeleton skeletons/5-8/the-snow-day-expedition.json \
  --briefs docs/planning/vendor-comparison/briefs-5-8.json \
  --vendors docs/planning/vendor-comparison/vendors.json \
  --mock --out out/vendor-comparison/dry-run
```

Pass `--vendors` to the dry run too, as above. With it, the slate is loaded and validated and each
leg is mirrored into a mock leg of the same lineage (its label prefixed `mock:` so no row can be
misread as a real measurement), so the rehearsal reproduces the paid run's leg count and family
layout. Without it the harness substitutes three generic legs, which exercises the analysis path but
would not catch a slate that split one lab across two families. Check the printed pair counts against
the table below before spending anything.

The paid run is the same command with `--vendors` and a throttle:

```bash
uv run python scripts/compare_vendors.py \
  --skeleton skeletons/5-8/the-lantern-festival.json \
  --skeleton skeletons/5-8/the-night-market.json \
  --skeleton skeletons/5-8/the-school-garden-mystery.json \
  --skeleton skeletons/5-8/the-snow-day-expedition.json \
  --briefs docs/planning/vendor-comparison/briefs-5-8.json \
  --vendors docs/planning/vendor-comparison/vendors.json \
  --throttle 3 --out out/vendor-comparison/run-1
```

## What it costs

24 paid fills (6 legs x 4 briefs) at 39,051 input and 33,023 output tokens per leg, priced at the
per-MTok rates fetched 2026-08-12 and listed in the vendor table above:

| | cost |
| --- | ---: |
| Anthropic, both legs | $1.02 |
| OpenAI | $1.19 |
| xAI | $0.28 |
| Moonshot | $0.61 |
| Google | $0.47 |
| **total, no retries** | **$3.57** |

A structural repair on a third of the books puts it near $4.76; two repairs on every book, which
would be a bad day, caps it near $10.71. Wall clock is dominated by 24 sequential long completions
plus the throttle, so budget roughly 40 to 80 minutes.

Per-book token cost is not reported by the harness. `GenerationProvider.complete` discards usage on
this branch; capture lands with #701 (`feat/generation-cost-instrumentation`), which changes that
return type across 52 files. Re-run after it merges to populate the column rather than building a
second counter that would conflict with it.

## What the pair counts will be

24 books over the 6 x 4 grid gives 276 pairs, bucketed on three axes: same leg or not, same lab or
not, same brief or not.

| | same brief | different brief |
| --- | --- | --- |
| **same leg** | not produced | 36 pairs (6 per leg): **within-vendor floor** |
| **same lab, other checkpoint** | 4 pairs: both confounds at once | 12 pairs: version-bump control |
| **different lab** | 56 pairs: premise convergence | 168 pairs: **cross-vendor floor** |

The headline is the right-hand column's top and bottom rows. Two confounds are kept out of it:

- **Premise convergence.** Comparing a cross-lab same-brief pair against a within-vendor
  different-brief pair would credit shared premise wording to vendor agreement, biasing the result
  toward "model choice does not matter".
- **The same lab twice.** Sonnet 4.6 and Sonnet 5 are two legs but one training lineage. Counting
  those 12 pairs as cross-vendor would drag the cross-vendor mean toward the within-vendor mean for
  a reason that has nothing to do with vendor choice, again biasing toward "task-driven". They get
  their own cell, which answers a genuinely useful question: does upgrading a checkpoint diversify
  anything?

Both off-headline cells are reported, just never averaged in.

## Reading the result

- **Cross-vendor materially above within-vendor** (the harness calls it at a ratio >= 1.15): the
  floor is vendor-driven. Rotating vendors is a cheap, large diversification lever and model
  selection belongs in the strategy alongside skeleton choice.
- **Comparable**: the floor is task-driven. Vendor rotation buys little; spend the effort on prompt
  and skeleton variety.
- **Cross-vendor materially below within-vendor** (ratio <= 0.87): inverted, and interesting.
  It would mean two vendors agree with each other more than one vendor agrees with itself, which
  points at a shared training-data idiom rather than a house style.

Then read the version-bump cell against those two. If it sits at the within-vendor level, a
checkpoint upgrade buys no diversification and rotation has to cross labs to be worth anything. If
it sits at the cross-vendor level, two checkpoints of one lab are as good as two labs, which is a
much cheaper rotation to operate.

Sample size caveat inherited from the calibration itself: 3.3 came from 3 pairs with a range of 1.9
to 5.0. This run's 36 and 168 pairs are far better, but the 12-pair version-bump cell is closer to
the calibration's own thinness, and a difference smaller than that spread is not a finding.
