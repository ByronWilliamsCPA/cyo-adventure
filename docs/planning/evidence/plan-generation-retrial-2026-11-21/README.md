# Plan-generation retrial (2026-11-22)

The six WP-2.3 smoke requests re-run on the density-fixed plan path (`a9e14c2` to `07a8482`: SP-D warnings, one
density repair, the convention-1 section of `plan.md`). Same driver (`scripts/smoke_plan_generation.py`, now with
`--out` and `--reasoning-budget`), same model (`anthropic/claude-sonnet-5.5` via OpenRouter, reasoning effort `low`),
same requests, Stage 0 skipped and recorded. Owner-approved, 8 USD cap. First run: `../plan-generation-smoke-2026-11-21/`.

## Results

| Run | Request | Shape | Status | Plan calls | Facts (before, after) | Passages with no fact (before, after) | Distinct costs (before, after) | USD |
| --- | --- | --- | --- | ---: | --- | --- | --- | ---: |
| 1 | P01 | the-locked-carousel | checked | 1 | 6, 58 | 0 of 58, 0 of 58 | 78, 113 of 118 | 0.15 |
| 2 | P02 | the-cave-of-echoes | checked | 1 | 10, 44 | 0 of 49, 0 of 49 | 16, 30 of 64 | 0.13 |
| 3 | P03 | the-locked-carousel | checked | 3 | 10, 90 | 50 of 58, 0 of 58 | 67, 115 of 118 | 0.56 |
| 4 | P04 | the-locked-carousel | checked | 1 | 8, 71 | 0 of 58, 0 of 58 | 106, 104 of 118 | 0.14 |
| 5 | P05 | the-cave-of-echoes | checked | 1 | 10, 60 | 0 of 49, 0 of 49 | 23, 63 of 64 | 0.14 |
| 6 | G03 (medium) | the-lantern-keepers-list | **no plan** | 1 | 9, none | 106 of 108, none | 8, none | 0.35 |

Spend: about 1.58 USD (runs 1 to 6 at 1.50, plus about 0.08 for the second run-6 attempt below).

## What it shows

- **Density is fixed on the short shapes.** Facts per plan went from 6 to 10 to 44 to 90, no passage records nothing,
  and choice costs are now specific to their decision. No SP-D warning was raised on runs 1 to 5. Four of five passed
  on the first plan call.
- **The largest shape now overflows one call.** Run 6 stopped at `max_tokens` 32,000 with 11,071 reasoning tokens
  spent (`runs/6-truncated-effort-low.json`): a denser plan for a 132-node, 314-choice shape no longer fits one call
  once reasoning is included. This is the `AL-844` risk, now real.
- **A reasoning token budget did not hold.** Re-running run 6 with an explicit OpenRouter reasoning budget of 1,536
  tokens (`runs/6-reasoning-budget-1536.json`) ended with the provider reporting all 32,000 tokens spent on reasoning
  and no content. The budget form of the reasoning control is not honoured for this model on this route, so the
  explicit-reasoning work (`AL-847`) is verified only for the effort form.

## Next

Write large plans in scene chunks (`AL-844`), and treat the reasoning budget form as unverified until a call shows it
capping reasoning.
