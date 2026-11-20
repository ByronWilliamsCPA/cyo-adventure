# Structural verification, 2026-11-20: evidence bundle

> **Provenance.** Every fill here was written by `deepseek/deepseek-v4-pro` (one Stage D call by
> `anthropic/claude-sonnet-4.6`, see the run log) on the production OpenRouter cascade and measured
> by this repository's deterministic instruments. Hand readings are one reader's (the agent that ran
> the round); no child and no second human has read any of it. The findings are in
> [`../../structural-verification-2026-11-20.md`](../../structural-verification-2026-11-20.md).

## What was run

| Run | Question | Skeleton | Arms | Fills |
| --- | --- | --- | --- | ---: |
| A | Do the 2026-11-20 prompt changes (commits after `1c42b3b`) yield better fills on the same skeleton? | `16+/the-last-train-north` | OLD x3, NEW x3, NEW forced-chunked x1 | 7 |
| A | same | `8-11/the-clockwork-menagerie` | OLD x3, NEW x3 | 6 |
| B | Does a fill of a state-promoted skeleton keep the state contract and write payoffs a child can connect to their plants? | `8-11/the-lantern-keepers-list`, `10-13/the-orchard-signal` | NEW x2 each | 4 |

The OLD arm ran from `.worktrees/prompt-baseline` (detached at `1c42b3b`, its own `uv sync`), the NEW arm
from `.worktrees/verify-runs`. Each `run.json` records the `cyo_adventure` path it imported and the
sha256 prefix of every fill template and `prompts.py`, so the arm is provable per fill. The bound skeleton
hash (`bound_skeleton_sha`) and brief hash are identical across arms for each skeleton.

## Harness (no new pipeline)

- `run_fill.py` calls the production `build_provider` (OpenRouter cascade: v4-pro pinned to `azure/us`
  by `core/pricing.py::ENDPOINT_PINS`, then `claude-sonnet-4.6`; no Modal leg configured) wrapped in
  `MeteredProvider`, and the production `orchestrator.fill_skeleton` with production defaults
  (`max_repairs=3`, two Stage D passes, `min_fill_rate=0.6`), as `generation/worker.py` does. Declared
  deviations: `stage1_gate="skipped"` (as in the 2026-08-21 round); the contract's `default_binding`
  rendered deterministically instead of the LLM binder (so both arms receive byte-identical bound
  skeletons); and, for `A-ltn-new-chunked` only, `--force-cap 24000` to force the chunked path.
  Every call is recorded (serving model, tokens, wall clock, finish reason).
- `evaluate.py` scores a fill with `run_fill_gate`, `check_fill_integrity.py`, `check_prose_craft.py
  --json`, `measure_consequence.py`, `validator.dialogue`, and an exact condition/effects comparison on
  both the raw first reply (before `normalize_filled_story`) and the delivered book. Run from the NEW
  worktree for every fill, so both arms are measured by the same instruments.
- `playthrough.py` plays every plant-to-payoff pair with `StoryEngine`, shortest route with and
  without the plant. `tabulate.py` prints the tables. `render_prompt.py` renders a fill prompt offline.
- Reachability: `scripts/compare_vendors.py::preflight` against `vendors-production-cascade.json`
  (both legs reachable) before the first paid call.
- Briefs (`briefs/`) are production-shaped `ConceptBrief` dumps of each skeleton's NATIVE theme, so
  no reskin confounds the comparison. Operator-authored; no real child identity.

## Files

| Path | What |
| --- | --- |
| `runs/<label>/filled.json` | The delivered book (after sentinel reinsertion), JSON-escaped (`ensure_ascii`), so the model's em-dashes are stored as JSON `\u2014` escapes; the data is unchanged. |
| `runs/<label>/run.json` | Arm, template hashes, every call (model, tokens, wall clock), stage log, estimated cost. |
| `runs/<label>/metrics.json` | Everything `evaluate.py` measured. |
| `reference/` | The same instruments on the committed `out/*.filled.json` books, for context only (a different authoring path). |
| `prompts/` | Rendered OLD and NEW system prompts for one skeleton, the user-prompt diffs (offline render and from the run itself; the run's prompt equals the offline render byte for byte), and the per-batch merge notes the chunked fill received. Whitespace-normalized by the repository's pre-commit hooks; the verbatim sha256 prefixes are in each `run.json`. |
| `merge-readings.md` | Three merge nodes per Run A fill, the same three per skeleton in every arm. |
| `playthroughs/` | Every plant and payoff of each Run B fill, both states. |

## Run log

All fills 2026-11-20 between 21:49 and 22:27 UTC, in three concurrent waves. "Est." is
`generation/cost.py::estimate_run_cost` at the `azure/us` price row (1.91 / 3.83 USD per MTok).

| Label | Arm | Served model(s) | Calls | Tokens in / out | Wall s | Est. USD | Outcome |
| --- | --- | --- | ---: | --- | ---: | ---: | --- |
| A-ltn-old-1 | old | v4-pro | 19 | 79,175 / 53,981 | 327 | 0.358 | needs_review (fill rate 0.511) |
| A-ltn-old-2 | old | v4-pro | 19 | 82,433 / 61,623 | 429 | 0.393 | passed |
| A-ltn-old-3 | old | v4-pro | 13 | 63,632 / 49,196 | 311 | 0.310 | passed |
| A-ltn-new-1 | new | v4-pro | 24 | 134,510 / 103,885 | 721 | 0.655 | passed after 1 repair (first reply duplicated node `g0a1_5`) |
| A-ltn-new-2 | new | v4-pro | 18 | 89,585 / 69,081 | 454 | 0.436 | passed |
| A-ltn-new-3 | new | v4-pro | 14 | 106,340 / 86,254 | 454 | 0.533 | passed after 1 repair (first reply broke a choice) |
| A-ltn-new-chunked | new | v4-pro | 20 | 246,324 / 76,406 | 465 | 0.763 | passed; 3 batches, batch 1 retried once (returned an extra node) |
| A-cm-old-1 | old | v4-pro | 20 | 145,853 / 128,862 | 668 | 0.772 | passed after 2 repairs (first reply renamed node `sv_a2` to `av_a2`) |
| A-cm-old-2 | old | v4-pro | 15 | 62,675 / 37,206 | 265 | 0.262 | needs_review (fill rate 0.583) |
| A-cm-old-3 | old | v4-pro + sonnet-4.6 | 14 | 58,434 / 32,048 | 191 | 0.237 | needs_review (fill rate 0.479); Stage D call 13 got a leg-fatal HTTP 400 from v4-pro and was served by sonnet-4.6 (106 output tokens) |
| A-cm-new-1 | new | v4-pro | 17 | 74,804 / 46,000 | 263 | 0.319 | passed |
| A-cm-new-2 | new | v4-pro | 13 | 67,211 / 46,497 | 323 | 0.306 | passed |
| A-cm-new-3 | new | v4-pro | 12 | 63,181 / 40,987 | 263 | 0.278 | passed |
| B-lkl-new-1 | new | v4-pro | 16 | 81,676 / 43,377 | 232 | 0.322 | passed |
| B-lkl-new-2 | new | v4-pro | 16 | 84,006 / 47,448 | 281 | 0.342 | passed |
| B-os-new-1 | new | v4-pro | 24 | 114,699 / 75,804 | 446 | 0.509 | passed |
| B-os-new-2 | new | v4-pro | 21 | 104,529 / 65,416 | 396 | 0.450 | passed |

**Spend.** Estimated 5.889 USD across the 17 fills. OpenRouter's own cumulative `usage` for the key
rose by **5.0525 USD** between the reachability probe and the last fill (that figure includes the
two-call probe and would include any other use of the key in the window). Pre-spend estimate from
`docs/planning/unit-cost-model.md` (0.0215 USD per 1k commissioned words, band range 0.0186 to 0.0285):
about 3.4 USD for the planned 9 fills; the round grew to 17 fills inside the 15 USD cap.

**Failures.** None. 17 of 17 fills delivered a book; no `content_filter` stop and no empty reply on
any call (the 2026-08 rounds saw 20 to 40 percent). One call fell over to the fallback leg (above).
No retry of a whole fill was needed.
