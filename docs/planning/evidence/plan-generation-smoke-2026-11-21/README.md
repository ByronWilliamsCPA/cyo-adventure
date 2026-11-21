# WP-2.3 paid smoke: Story Plan generation (2026-11-21)

The first paid run of the plan path built in WP-2.3: request to pitches to a checked Story Plan on a retained shape,
through the production `generate_story_plan` with the production SP-0 to SP-9 checks and repair budget. Approved
by the owner on 2026-11-21: Sonnet 5.5 through OpenRouter, a hard spend stop at 8.00 USD, Stage 0 skipped. This is
the first measurement of plan-generation yield, tokens and latency (WP-2.3 acceptance).

**Result: 6 of 6 plans passed SP-1 to SP-9 within the repair budget, for 1.56 USD in total.** Three passed on the
first plan call. A passing plan is not yet a good plan, though: see
[What the plans look like](#what-the-plans-look-like).

## Setup

- **Driver.** [`scripts/smoke_plan_generation.py`](../../../../scripts/smoke_plan_generation.py). It builds each job
  as `generation/worker.py::_run_plan_generation` does: the brief from `story_requests/brief.py::brief_from_request`,
  the shape matched by `candidates_for_cell` and picked by `story_requests/authoring_plan.py::_pick_shape` (seeded by
  a UUID5 of the request id, so a re-run draws the same shape), then `load_bound_shape`, `plan_request_from_brief`
  and `generate_story_plan` with `max_repairs=2`.
- **Model.** `anthropic/claude-sonnet-5.5` on one OpenRouter leg (`build_openrouter_cost_reporting_leg`, unpinned:
  there is no endpoint pin for this model), not the production cascade. Pitch calls `max_tokens` 2,000; plan calls
  32,000 (the generator's own ceiling; Sonnet 5.5 has no lower row in `MODEL_OUTPUT_CAPS`). Per-attempt timeout 900
  seconds. The model recorded per call is the configured id; the provider does not surface the served model.
- **Reasoning.** Explicit `reasoning.effort` `low`, set through `Settings.llm_effort`, the only reasoning control
  the provider class has. The first attempt used the production default `llm_effort="off"`, which omits the
  parameter on the assumption that the model will then not think. It thought anyway: 11,490 reasoning tokens on one
  plan call (the answer still arrived, `finish_reason` `stop`). That probe is kept as
  [`config-probe-effort-off.json`](./config-probe-effort-off.json); its plan was not checked or kept. With `low`,
  reasoning ran 0 to 3,078 tokens per call and no call hit `max_tokens`.
- **Stage 0.** Skipped and recorded on every result: no `OPENAI_API_KEY` here. The screen is the production
  `classifier_screen(None)`, which with no key calls nothing. Each pitch was still floored by SP-9 and the PII guard.
- **Spend stop.** Before each call the driver adds a worst-case estimate for that call (prompt characters / 2 as
  input tokens plus the full `max_tokens` as output) to the spend so far, and refuses the call if the sum would
  cross the budget. Spend so far is the larger of the `MeteredProvider` ledgers priced at 2 / 10 USD per million
  tokens (read off OpenRouter's own breakdown in the plan-review pilot) and OpenRouter's reported per-call charge.
  The probe's 0.28 USD was carried into the main run's budget. The worst case for all six runs using every repair
  was 7.87 USD; nothing came near the stop.
- **Per-attempt findings.** `generate_story_plan` returns only the last plan and its report, so the driver replays
  each plan answer through the generator's own load and check steps (no calls). Every run's replay of the last
  attempt matched the generator's error count (`replay_consistent: true`).

### Requests

| Run | Request | Text | Length | Shape | How chosen |
| --- | --- | --- | --- | --- | --- |
| 1 | P01 | a story about my dog who gets lost in the woods | short | `the-locked-carousel` | cell pick |
| 2 | P02 | a dragon who is scared of fire | short | `the-cave-of-echoes` | cell pick |
| 3 | P03 | me and my sister solving a mystery in an old castle | short | `the-locked-carousel` | cell pick |
| 4 | P04 | a robot that learns to play music | short | `the-locked-carousel` | cell pick |
| 5 | P05 | a pirate looking for treasure under the sea | short | `the-cave-of-echoes` | cell pick |
| 6 | G03 | a missing school trophy mystery | medium | `the-lantern-keepers-list` | override |

The panel ([`panel.json`](../short-request-panel/panel.json)) has no per-request band: every request runs at both of
its bands, in panel order with 8-11 first, so the first five 8-11 jobs are P01 to P05. Run 6 adds a medium request
bound to the three-thread shape by an admin-style override, because both 8-11 short shapes are stateless and the
smoke would otherwise leave SP-4 to SP-6 unmeasured (`AL-843`). Its text is panel request G03, used at medium.

## Results

| Run | Status | Attempts | First ERRORs | Final ERRORs | In tokens | Out tokens (reasoning) | USD | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | checked | 1 | none | none | 7,226 | 10,236 (1,148) | 0.112 | 67 |
| 2 | checked | 3 | SP-3: 1 | none | 40,316 | 22,679 (2,461) | 0.300 | 119 |
| 3 | checked | 1 | none | none | 7,215 | 7,726 (0) | 0.087 | 47 |
| 4 | checked | 1 | none | none | 7,210 | 10,903 (1,507) | 0.119 | 75 |
| 5 | checked | 2 | SP-9: 3 | none | 22,945 | 13,351 (285) | 0.171 | 74 |
| 6 | checked | 2 | SP-9: 1 | none | 55,945 | 39,325 (3,078) | 0.496 | 197 |
| **Total** | 6 checked | 10 plan calls | | | 140,857 | 104,220 (8,479) | 1.284 | 577 |

Cost is OpenRouter's reported charge; the metered estimate at 2 / 10 USD per million was 1.324. "Attempts" counts
plan calls (the first plus repairs); each run also made one pitch call. No attempt in any run had a WARNING.
Request texts are in each `runs/<n>.json`; G03 is quoted in full there. "Nodes with no fact" (below) counts
passages that neither require nor establish a fact.

| Spend | Calls | USD (vendor) |
| --- | --- | --- |
| Configuration probe (`llm_effort="off"`, run 1 pitch and first plan call) | 2 | 0.276 |
| Smoke (six runs) | 16 | 1.284 |
| **Total** | 18 | **1.560** |

- **Yield.** 6 of 6 plans pass SP-1 to SP-9 within the repair budget (5 of 5 for the WP-2.3 acceptance requests).
  3 of 6 passed on the first plan call; 4 repairs in all, out of a budget of 12.
- **Pitches.** Every run's first pitch passed the floors and the PII guard; on-demand mode then stops screening, so
  pitches 2 and 3 are recorded as `not screened`. A pitch call costs about 0.006 USD and 5 seconds.
- **Plan calls.** Short shapes (65 and 71 nodes): 6,300 to 10,400 output tokens and 29 to 69 seconds per call. The
  largest 8-11 shape (132 nodes, 314 choices): 20,053 output tokens and 108 seconds for the first call, close to the
  21k estimate in `AL-844`. A repair carries the previous plan, so its input is about three times the first call's
  (43,545 tokens for run 6).
- **What the repairs fixed.**
  - Run 5 (SP-9, 3 findings) and run 6 (SP-9, 1): a band-mandatory denylist term in bundle `lethal` in a node event,
    a cost and an ending gift. One repair cleared each. The finding does not name the matched term.
  - Run 2 (SP-3, twice): "the book answers its question two ways": a failure fact (`f_rush`, Ember rushes and
    the wick stays damp, at six neutral turn-back endings) sat in a contradiction pair with the truth fact
    `f_small_safe`. The first repair returned the identical finding. The passing plan has no contradiction pair at
    all. SP-3's two-answer finding needs a marked pair that touches the truth, so the repair most likely removed the
    `contradicts` mark rather than changing the story. The driver did not keep the text of loaded attempts, so this
    is inferred, not shown.

### Thread rules (run 6)

SP-4 to SP-6 ran on all three threads of `the-lantern-keepers-list` (`did_start_beacon_steps`,
`did_start_sheepfold_turn`, `did_knock_doors_that`) at both attempts and **found nothing**. SP-1 excluded no thread.
The plan binds a muddy button, a torn note and a brass key to the three planting choices, establishes each plant only
on its planting choice, and gives each thread its two payoff sites with a `shows` line (for example "The torn note
points Wren to the right door"). The only ERROR at the first attempt was the SP-9 term above.

## What the plans look like

Read: the truth, cast and facts of runs 1, 2 and 6, one route through each walked against its shape, and the counts
below for all six.

- **They are stories, and they follow the request.** Run 1 is a lost dog (Biscuit) found resting in a hollow log by
  a creek, with an owl who hints at the creek. Run 2 is a young dragon who learns slow breathing and a dry wick make a
  small, safe flame. Run 6 is a trophy mystery whose culprit, the caretaker, cracked the cup by accident and was
  mending it in secret, with the blamed classmate cleared. Each truth answers its question, and each passes SP-2 and
  SP-3 against its graph.
- **Convention 3 (costs) is followed.** "None" appears only on single-option passages in all six plans (one
  exception, in run 1); at decisions the costs name what is given up ("Gives up the other two paths").
- **Convention 2 (dialogue) is followed where dialogue appears.** Run 2 records "Old Moth told Explorer that slow
  breaths keep a flame small and steady" as its own fact, separate from the breathing fact itself.
- **Convention 1 (state facts) is mostly not followed: the plans record very little.** The checks can only see what
  a plan records, and these plans record a thin ledger:

  | Run | Shape nodes | Facts | Contradiction pairs | Nodes with no fact | Distinct choice intents |
  | --- | --- | --- | --- | --- | --- |
  | 1 | 71 | 6 | 0 | 0 | 98 of 118 |
  | 2 | 65 | 10 | 0 | 0 | 49 of 64 |
  | 3 | 71 | 10 | 1 | 63 | 83 of 118 |
  | 4 | 71 | 8 | 0 | 0 | 106 of 118 |
  | 5 | 65 | 10 | 2 | 0 | 49 of 64 |
  | 6 | 132 | 9 | 1 | 128 | 18 of 314 |

  In run 1 every passage requires `f_lost`, but the clues the hero finds (a bent twig, fur, a chipmunk, bird tracks)
  are events only, never facts, although choice costs refer to them ("Gives up the fur"). Run 6 is the clearest case:
  128 of 132 passages neither require nor establish anything; 89 choices share the intent "Follow the muddy
  footprints" and 89 "Question a suspect", whatever passage they lead to (one leads to "Wren checks the corridor
  noticeboard"); and three cost strings cover 284 of 314 choices. Its events are distinct, but along a route they
  read as a list of places rather than a chain of discoveries, and the truth is established only at its two
  endings. It passes every SP rule because almost nothing in it can contradict anything.
- So **yield, as WP-2.3 defines it, overstates readiness.** The repair loop is cheap and reliable at clearing what
  the checks see; nothing measures what a plan leaves unrecorded. The largest shape is where the model economised
  most, consistent with `AL-844`'s concern about one call writing 132 nodes and 314 choices.

## What broke

1. **`llm_effort="off"` does not stop Sonnet 5.5 from reasoning.** The production default omits the `reasoning`
   parameter, and the OpenRouter adapter's own comment says that is how reasoning is kept off for structured output.
   Sonnet 5.5 spent 11,490 reasoning tokens on one plan call anyway. Fixed for this smoke by setting `low`
   explicitly; the production default is unchanged.
2. **Per-attempt evidence needs private helpers.** `PlanGenerationResult` keeps only the last plan and report. The
   per-attempt findings above come from replaying each answer through `_decode_object`, `_normalize`, `_assemble`
   and `check_plan`. The driver kept raw text only for answers that did not load, so the run 2 repair cannot be
   shown line by line.
3. Nothing else failed: no provider error, no timeout, no truncation, no unparseable answer, no load error, no PII
   hit.

## Files

- `runs/<n>.json`: one per request. The request and its panel reference, the shape id, hash, cell and how it was
  chosen, the brief, every call (kind, model, input, output and reasoning tokens, finish reason, estimated and vendor
  cost, latency, the worst case and spend checked before it), the pitches with their screen outcomes, the Stage 0
  skip, `story_plan_status`, attempts, the stage log, every SP finding by rule at each attempt, the final check
  report and the final plan.
- `config-probe-effort-off.json`: the two calls made with `llm_effort="off"` before the configuration was fixed.
- Re-run: `uv run python scripts/smoke_plan_generation.py --dry-run` prints shapes and worst cases without calling
  anything; drop `--dry-run` to spend.
