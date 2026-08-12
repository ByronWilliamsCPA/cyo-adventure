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

`vendors.json` pins each slug to one backend. An OpenRouter slug is not a vendor: verified on
2026-08-12 against `GET /api/v1/models/{id}/endpoints`, `anthropic/claude-sonnet-4.6` alone is
served by four backends, so an unpinned run attributed to Anthropic can be answered by Bedrock at a
different quantization. The adapter sends `allow_fallbacks: false` alongside the pin, so a
substitution becomes a visible error rather than a silent one.

A `-preview` slug can be retired without notice. Re-verify the three slugs still resolve before
spending anything.

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
  --mock --out out/vendor-comparison/dry-run
```

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

12 paid fills (3 vendors x 4 briefs), priced at the per-MTok rates fetched 2026-08-12:

| | input | output | cost |
| --- | ---: | ---: | ---: |
| `anthropic/claude-sonnet-4.6` ($3 / $15) | 39,051 | 33,023 | $0.61 |
| `openai/gpt-5.4` ($2.5 / $15) | 39,051 | 33,023 | $0.59 |
| `google/gemini-3.1-pro-preview` ($2 / $12) | 39,051 | 33,023 | $0.47 |
| **total, no retries** | | | **$1.68** |

A structural repair on a third of the books puts it near $2.23; two repairs on every book, which
would be a bad day, caps it near $5.04. Wall clock is dominated by 12 sequential long completions
plus the throttle, so budget roughly 20 to 40 minutes.

Per-book token cost is not reported by the harness. `GenerationProvider.complete` discards usage on
this branch; capture lands with #701 (`feat/generation-cost-instrumentation`), which changes that
return type across 52 files. Re-run after it merges to populate the column rather than building a
second counter that would conflict with it.

## What the pair counts will be

12 books over the 3 x 4 grid, bucketed on two axes:

| | same brief | different brief |
| --- | --- | --- |
| **same vendor** | not produced | 18 pairs (6 per vendor): **within-vendor floor** |
| **cross vendor** | 12 pairs: premise convergence | 36 pairs: **cross-vendor floor** |

The headline is the right-hand column. Comparing a cross-vendor same-brief pair against a
within-vendor different-brief pair would credit shared premise wording to vendor agreement, and
that single confound would bias the result toward "model choice does not matter". The same-brief
cell is reported separately because it answers a real but different question.

## Reading the result

- **Cross-vendor materially above within-vendor** (the harness calls it at a ratio >= 1.15): the
  floor is vendor-driven. Rotating vendors is a cheap, large diversification lever and model
  selection belongs in the strategy alongside skeleton choice.
- **Comparable**: the floor is task-driven. Vendor rotation buys little; spend the effort on prompt
  and skeleton variety.
- **Cross-vendor materially below within-vendor** (ratio <= 0.87): inverted, and interesting.
  It would mean two vendors agree with each other more than one vendor agrees with itself, which
  points at a shared training-data idiom rather than a house style.

Sample size caveat inherited from the calibration itself: 3.3 came from 3 pairs with a range of 1.9
to 5.0. This run's 18 and 36 pairs are better, but a difference smaller than that spread is not a
finding.
