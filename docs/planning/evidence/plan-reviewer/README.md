# Plan reviewer: validation harness and evidence (WP-3.7)

The plan reviewer is a model, different from the one that wrote a Story Plan, that reads the plan and answers `pass`,
`reject` or `unsure` with reasons that name plan entries (owner decision D11). It may not be used until it has been
validated against the project's labelled ground truth at thresholds the owner fixed before any prompt was written
(D12). This directory holds the evidence for that validation. Nothing in it is a validation yet: the prompt and the
harness are built, and no paid run has been made.

Read first: `docs/planning/story-plan-implementation-plan.md` (WP-3.7, WP-2.4, rows D11 and D12),
`../continuity-reader/README.md` (the validation-set format and the split) and
`../plan-review-pilot-2026-11-21/README.md` (the informal first look this design answers).

## What was built

| Piece | Where |
| --- | --- |
| Verdict model, defensive parser, independence rule, two-run combination, checker authority, seeded sample, suspension rule, validated-pairing refusal, the prompt's renderers | `src/cyo_adventure/storyplan/review.py` (pure) |
| Figures with intervals, the D12 thresholds, the G3b verdict, the held-out rule, the cost model | `src/cyo_adventure/storyplan/review_figures.py` (pure) |
| The provider call: two runs, effort reasoning, bounded concurrency, hard spend cap, per-call cost | `src/cyo_adventure/moderation/plan_reviewer.py` |
| The prompt, with a calibration section for tuning | `src/cyo_adventure/generation/templates/plan_review.md`, built by `build_plan_review_prompt` in `generation/prompts.py` |
| Settings (`story_plan_reviewer_*`, `story_plan_writer_model`) | `src/cyo_adventure/core/config.py` |
| One plan, one verdict | `scripts/review_story_plan.py` |
| The validation harness | `scripts/validate_plan_reviewer.py` |

The reviewer is **not wired** into `generation/worker.py` or `story_requests/authoring_plan.py`; that is WP-2.4.
`moderation.plan_reviewer.settings_refusal(settings)` is the function the worker will call before every plan: it returns a
reason code (`disabled`, `suspended`, `not_independent`, `unvalidated`, `pairing_mismatch` and so on) for anything but a
usable reviewer, and the worker routes the job to the owner on any of them.

### How a plan is reviewed

1. The deterministic checks (SP-0 to SP-9) run. If they report an ERROR the plan is rejected as `checker_caught` and no
   model is called. A reviewer `pass` over a checker ERROR is never possible.
2. Otherwise the reviewer is called twice, at low temperature, with the effort form of OpenRouter's reasoning control
   (the token-budget form is not honored there, AL-856) and a `max_tokens` of 24,000 so that reasoning cannot starve the
   answer (AL-823, AL-847). A `length` finish is `unsure` and is never retried.
3. It receives: the plan JSON without `provenance.notes` (and without `approver` and `checks`); the book graph only
   (node, choice, target, condition, effects, ending valence and kind, with **no prose**); the request text inside an
   untrusted fence; and the checker's findings. The system prompt states the rules the pilot's reviewer got wrong
   (a choice's `requires` is checked against what is known on entry plus the offering node's `establishes`) and says
   its job is what the checker cannot see: a label or intent that contradicts its outcome, a fact that contradicts
   `truth`, an ending gift that contradicts its valence, kind or the truth, a payoff `shows` that does not match its
   plant. It is told not to re-trace routes.
4. Two answers are combined: identical verdicts keep the verdict, any disagreement is `unsure`, the findings are unioned.
   Bad JSON, an unknown verdict, a provider error or a spend stop are `unsure` with a machine reason code, never a pass.
5. Findings carry one plan entry id, a class, a severity and a short reason. A long quotation in a reason is removed on
   the way in; nothing this code generates quotes story text.

Only five classes carry authority: `label_outcome_mismatch`, `truth_contradiction`, `ending_gift_mismatch`,
`payoff_shows_mismatch` and `state_contradiction`. `agency_or_cost`, `request_fidelity`, `band_suitability`,
`dull_or_generic` and `other` are advisory, because there is no measured recall for them (D12, scope of authority).

## Inputs

All read from committed files with every sha256 verified; a mismatch stops the run.

| Input | File | Used for |
| --- | --- | --- |
| Real defective plans | `../continuity-reader/validation-set.json`, `kind: plan`, strong label, `expected_verdict: reject` | Figure (a): recall |
| Real clean-labelled plans | the same, `expected_verdict: pass` | Checked by the checker only (no model call); the clean sample is the baselines |
| Synthetic plans | `synthetic/validation-set.synthetic.json` (family A checker-visible, family B checker-invisible) | Figure (b), reported apart |
| Clean sample | `clean-baselines/manifest.json`, schema `clean-baselines/v1`: the checker-repaired baselines of five books | Figure (c): flag rate |

`unknown` smoke plans and weak-labelled plans are skipped and counted. The harness stops with a clear message when the
baselines manifest is absent. Plan items that name a git revision are read with `git show`, so a shallow clone cannot run
the harness.

## Figures

Never merged. Every proportion is reported as counts with a Wilson 95 percent interval, because the samples are small
and clustered by book.

| Figure | What it is |
| --- | --- |
| (a) Real defective recall | Overall (checker plus reviewer), split into **checker-caught** plans (an SP ERROR, no model call) and **reviewer-decisive** plans (the checks were clean); recall on the decisive subset is the reviewer's own. Also by worst severity carried, and per blocker entry |
| (b) Synthetic recall | Family A (a floor: checker-visible by construction) and family B apart, B further by class (B1 to B4). Family B is reported twice: **any-reject recall** (any reject or `unsure` counts) and **located recall** (see below) |
| (c) Clean flag rate | On the baselines: raw, and with a finding at a recorded known residual counted as the true positive it is (`AL-882`); per book; with and without the baselines that needed repair |
| (d) Run agreement | Identical verdicts across the two runs of a plan, over plans the reviewer ran on |
| (e) Thresholds and G3b | Every D12 threshold and the minimum size, and one pass or fail line |
| (f) Reject-everything diagnostic | The share of every plan the reviewer ran on that was flagged (clean and defective), the share of clean baselines and of seeds flagged, and a warning line (see below) |

### Located recall (family B, informational)

The any-reject recall is too lenient on its own: a reviewer that rejects every plan scores 100 percent on it. The
first live tuning pass (`tuning-1`) rejected every plan, both clean baselines included. **Located recall** credits a
family B seed only when the reviewer's findings (the union of both runs) name at least one entry the seed edited, and
only on a plan the reviewer flagged.

- **Seeded entry ids** come from the item's `edited_paths` (JSON pointers): `/choices/<id>/...` is a choice id,
  `/nodes/<id>/...` a node id, `/facts/<id>` a fact id, `/endings/<id>/...` an ending id, `/threads/<id>/...` a thread
  id; a seed's pointers are united, so an edit that adds a fact counts the fact (`/facts/<id>`) and the node that
  establishes it. A node pointer that walks into a fact list by a non-numeric segment
  (`/nodes/<id>/establishes/<fact>`) counts that fact too; no committed item uses that shape. Any other pointer names
  no entry. The code is `pointer_entry_ids` and `seeded_entry_ids` in `review_figures.py`.
- It is reported for family B overall and per class (B1 to B4), with Wilson intervals, beside the any-reject figure and
  labelled as such. A family B plan with no derivable seeded entry is counted apart (`family_B_located_unscorable`) and
  left out of the located denominators rather than scored as a miss.
- It is **informational**. The D12 thresholds are pre-registered and G3b's rules are unchanged: located recall is not a
  threshold, and the verdict section prints it as an informational line only.
- Family A is checker-caught by construction and has no located figure.
- **Real defective plans have no located figure, on purpose.** A real plan item's `defects` records only each defect's
  id, class and severity. The node ids sit in the matching reader items (`node`, `other_nodes`, `choice_ids`), and they
  do resolve, but the result would not be reliable: the defects are every defect the *book revision* carries (an upper
  bound on what a plan can show, see below), most are prose-level, and the target sets are large (for example 39
  distinct nodes for the two Lighthouse plans carrying 20 defects, 83 for the 48 of the Clockwork plan), so almost any
  finding would land in one. The four reviewer-decisive held-out plans are the only place it would matter, and a located
  figure there would credit coincidence. Recording a per-plan list of the defects visible in the plan (not the book) is
  what would make it possible; until then real recall stays any-reject, and the checker-caught split is the honest
  reading of it.

### Reject-everything diagnostic

Printed in the report (section (f)) and in `results.json` under `figures.reject_everything_diagnostic`: the flagged
share of all plans the reviewer ran on (checker-caught plans never reach it), of clean baselines, and of the seeds it
ran on (family B in practice). The report carries a **warning line**, and repeats it in the verdict section, when more
than 90 percent of the clean baselines **and** more than 90 percent of the seeds were flagged: a reviewer that does that
discriminates nothing, and read together with located recall it shows whether any seed was actually found. It is a
diagnostic, not a gate.

### What `results.json` records for re-scoring

Every plan record carries `blockers`, `residual_entries`, `seeded_entry_ids`, `reviewer_findings_at_entry` (every
seeded id with the class and severity of each finding that names it; an empty list means that entry was not named) and
`located`, next to the full `review` (verdict, run verdicts and every finding). Located recall can therefore be
recomputed from `results.json` alone.

### Re-scoring an existing run

```bash
uv run python scripts/validate_plan_reviewer.py --rescore docs/planning/evidence/plan-reviewer/tuning-1
```

`--rescore <run-dir>` reads `<run-dir>/results.json`, rebuilds the scored plans from the recorded reviews, recomputes
every figure and G3b with the same rules, and writes `report.rescored.md` and `results.rescored.json` beside the
original. It makes no model call, never writes the original `results.json`, `report.md` or `raw/`, and refuses when
either output already exists. A results file written before these fields existed (such as `tuning-1`) is back-filled
by item id from the committed validation sets (the three JSON set files only; no plan, book or git revision is
loaded). `results.rescored.json` records the original and the recomputed G3b verdict side by side.

### The tuning-1 re-score

`tuning-1` was re-scored with this tool; the files are `tuning-1/report.rescored.md` and
`tuning-1/results.rescored.json`. Family B located recall is 3 of 4 (any-reject recall 4 of 4), and the
reject-everything warning fires (clean baselines 2 of 2 flagged, seeds 4 of 4 flagged, all 6 reviewer-run plans
flagged). The seeded entry of `SY-B-B1-3` (`c_a_hearth_1`) was never named; the other three seeds were located. The
G3b verdict is unchanged (tuning never passes it). With four seeds and two baselines this is a tuning signal, not a
measurement.

A flag on a clean baseline is "explained" when it has findings, at least one cites a known residual's node or choice, and
no blocker or should-fix finding cites anything else. A flag with no findings (a disagreement, a parse failure) is a
false flag.

## Pre-registered thresholds

Quoted from D12 (decided 2026-11-21, before any prompt was written), judged on the held-out half only.

| Item | Decided value |
| --- | --- |
| Defect recall | reject or `unsure` on at least 90 percent of labelled defective plans, and on every blocker-severity entry |
| Flag rate on clean plans | reject or `unsure` on at most 20 percent |
| Run agreement | identical verdicts on at least 90 percent of plans across two runs |
| Minimum validation size | at least 15 defective and 15 clean held-out plans; amended 2026-11-21 (`AL-853`): the clean minimum is met by baselines of five books, reported per book |
| Sample rate | 1 in 10 in steady state (`story_plan_reviewer_sample_rate` 0.1); 100 percent through the pilot (1.0) |
| Suspension | the owner overturns any blocker-class pass, or more than 1 in 5 of the last 10 sampled passes (at least 5 sampled) |
| Scope of authority | per defect class: only classes with measured recall; others advisory |

G3b passes only when every condition holds on a **live, complete, held-out** run: recall at least 0.90 over the real
defective plans, every blocker entry flagged (every plan carrying it), clean false-flag rate at most 0.20, run agreement
at least 0.90, at least 15 defective plans and clean baselines of at least five books. Synthetic recall is reported and is
not a threshold, because D12 names none.

"Every blocker entry" is read strictly: an entry passes only when every plan that carries it was flagged. A plan's
`defects` are every defect its book revision carries, an upper bound on what a plan reader can see.

## The tuning rule (pre-registered)

`--half tuning` is for prompt work. `--half held_out` requires `--confirm-held-out`, records the prompt hash, and the
harness refuses a held-out run in these cases (the record is `held-out-runs.json`, written before the first call so a
crashed run still counts):

- the same writer, reviewer and prompt hash has already been run on the held-out half;
- the pairing has already used one held-out run that passed G3b (a changed prompt voids the validation and needs a new
  owner decision, not a second look);
- the pairing has already used its first run and its one prompt revision (D12: one revision after a failed first run,
  then stop). An unfinished first run counts as failed.

A change of writer model, reviewer model or prompt voids the validation: `validated-pairing.json` is written only by a
live, complete, held-out run that passes G3b, and `reviewer_refusal` refuses any pairing that does not match the
setting `story_plan_reviewer_validated_pairing` exactly. Dry runs touch neither record.

## Commands

```bash
# Plumbing check, no network, no key: a stub provider answers pass, so the figures mean nothing.
uv run python scripts/validate_plan_reviewer.py --half tuning --dry-run
uv run python scripts/validate_plan_reviewer.py --half held_out --dry-run

# A tuning pass (live). The budget is a hard cap checked before every call.
uv run python scripts/validate_plan_reviewer.py --half tuning --live --budget 8 \
    --reviewer-model google/gemini-3.1-pro-preview

# The held-out pass: one look per pairing and prompt hash.
uv run python scripts/validate_plan_reviewer.py --half held_out --live --budget 25 \
    --reviewer-model google/gemini-3.1-pro-preview --confirm-held-out

# One plan against its book.
uv run python scripts/review_story_plan.py --plan out/<slug>.plan.json --book out/<slug>.filled.json --dry-run
```

`--rescore <run-dir>` takes no `--half`, `--live` or `--dry-run` (see above).

`--only <id,id>` runs a partial set (a partial run never passes G3b), `--price-in` and `--price-out` set the reviewer's
price when `core/pricing.py` has no row (otherwise 3 and 15 USD per million tokens are assumed), and `--temperature`,
`--effort` and `--max-tokens` override the settings for one run. Output is `<run-id>/results.json`, `report.md` and `raw/`
(every call's answer, ASCII-escaped). On a G3b pass the harness prints
`STORY_PLAN_REVIEWER_VALIDATED_PAIRING=<writer>|<reviewer>|<prompt hash>`, the value to set.

## Cost model

Measured from the pilot (2026-11-21): 74,842 plan characters made a 41,430-token prompt, about 2.0 to 2.1 characters per
token, and twelve calls averaged about 14,000 completion tokens, mostly reasoning. The harness builds the real prompts, so
its projection is exact on input size and assumed on output. At 3 USD per million input and 15 per million output tokens:

| Scope | Plans reaching the reviewer | Calls (2 runs) | Input tokens | Output tokens | USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tuning half, checker-clean plans only (the real run) | 6 | 12 | 0.51 million | 0.17 million | 4.04 |
| Held-out half, checker-clean plans only (the real run) | 22 | 44 | 1.80 million | 0.62 million | 14.63 |
| Tuning half, every plan sent regardless of the checker | 27 | 54 | 3.25 million | 0.76 million | 21.09 |
| Held-out half, every plan sent regardless of the checker | 46 | 92 | 3.96 million | 1.29 million | 31.19 |
| Both halves, every plan sent | 73 | 146 | 7.21 million | 2.04 million | 52.28 |

The harness sends only plans the checker passes (checker authority), so the real cost of one tuning pass is about 4 USD
and of the held-out pass about 15 USD. The WP-3.7 estimate of 5 to 10 USD assumed far fewer or cheaper calls: the plans
are 20 to 30 thousand tokens each and reasoning dominates the output. A reviewer at the pilot's Sonnet 5.5 price
(2 and 10 USD) would cost about two thirds of these figures.

## What the dry run on the real files already shows

These come from the checker, not from any model, and hold whatever the reviewer does.

- Of the 17 real defective held-out plans, 13 are rejected by SP-0 to SP-9 with no model call; only 4 are reviewer-decisive.
  Of the 12 real defective tuning plans, all 12 are checker-caught. The system's headline recall is therefore the
  checker's, and the reviewer's own recall is measured on 4 plans in the held-out half and none in the tuning half.
- The tuning half has only 6 plans the reviewer can be tuned on: 4 family B seeds and 2 clean baselines. That is thin for
  prompt work; the held-out half has 22 (8 family B seeds, 10 baselines and 4 real defective plans).
- 13 clean-labelled real plans in the held-out half are not sent to the reviewer: the baselines replace them as the clean
  sample, and the checker status of those plans is recorded in `results.json` (`checker_only_clean_plans`).

## Limits

- Synthetic recall overstates real recall: each seed is one defect at a known place in an otherwise clean plan. Family A
  is checker-visible by construction and is a floor, not evidence of reviewing skill.
- The clean sample is five books, two baselines each. Per-book results matter more than the pooled rate, and the
  baselines are checker-repaired plans, not plans as a writer produced them (see `clean-baselines/README.md`).
- The plan writer is Sonnet 5.5, so the reviewer must be a different model. The independence rule is enforced on
  configured model ids only (same id, or same vendor and model family, where a family is the name without its version
  tokens): it cannot see a router that substitutes one model for another, and the harness records the model ids the
  provider reports on every call.
- There is no measured recall on dull, generic or off-request plans, nor on agency or cost problems, so those classes
  stay advisory and never justify a reject on their own.
- One reader per book labelled the real set; a clean label is the latest verified state, not a proof of no defect.
- The reviewer's price is assumed when `core/pricing.py` has no row, so the spend figures can be off by that ratio;
  `--price-in` and `--price-out` correct it, and the vendor's own per-call charge wins when the provider reports one.

## Outcome of the first validation (2026-11-22)

| Run | Half | Prompt | Spend | Result |
| --- | --- | --- | --- | --- |
| [`tuning-1`](./tuning-1/report.md) | tuning | first | 1.68 USD | Both clean baselines rejected; 3 of 9 findings true |
| [`tuning-2`](./tuning-2/report.md) | tuning | calibrated | 1.39 USD | Fewer findings; both clean baselines still rejected |
| [`heldout-1`](./heldout-1/report.md) | held out | calibrated | 5.55 USD | **G3b FAIL** |

Reviewer `google/gemini-3.1-pro-preview`, writer `anthropic/claude-sonnet-5.5`. Held-out figures against the
pre-registered D12 values: defect recall 15/17 = 0.88 (needs 0.90; 13 of 17 checker-caught, the reviewer's own recall
2 of 4); one blocker entry not flagged; clean false-flag rate 6/10 = 0.60 (needs 0.20; per book 2/2 Signal, 2/2
Mapmaker's, 1/2 Museum, 1/2 Cave, 0/2 Sky-Ship); run agreement 18/22 = 0.82 (needs 0.90); family A 11/11; family B
located 7/8. No validated pairing was written. The reviewer stays disabled and the owner reads every plan until an owner
decision changes that (see the WP-3.7 outcome in `story-plan-implementation-plan.md`).
