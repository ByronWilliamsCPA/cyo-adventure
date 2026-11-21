# Plan-review pilot: Sonnet as Story Plan reviewer (2026-11-21)

An informal first look at ADR-033 Decision 3 as amended (D11): a different model from the plan writer reviews a
Story Plan before prose. This is **not** the WP-3.7 validation. It has no held-out split, no D12 thresholds, and the
prompt was written once and not tuned. Every book used here is now "seen" by reviewer-prompt design and must go in
the WP-3.7 tuning half, not the held-out half.

## Setup

- Reviewer: `anthropic/claude-sonnet-5.5` through OpenRouter (the project's existing `OPENROUTER_API_KEY`), temperature
  0.2, reasoning budget 12,000 tokens, two runs per plan. Plan writers were Opus agents, so writer and reviewer differ.
- Input per call: the plan JSON with `provenance.notes` removed (notes can carry continuity findings), plus the book's
  graph only (node, choice, target, condition, effects, ending valence and kind), no prose. Script: `run_pilot.py.txt` (kept as text: evidence, not project code; rename to `.py` to run);
  raw outputs: `runs/<case>.run<N>.json`.
- Cost: 2.93 USD for the 12 calls. A first attempt with `max_tokens` 8,000 spent every token on reasoning and returned
  no answer (2.19 USD, discarded).

| Case | Plan | Book | Known defects |
| --- | --- | --- | --- |
| `lh_prefix_blind` | WP-1.4 blind plan x1 | Hollow Lighthouse, pre-fix (`15b14a1`) | KD-LH-B1 to B3, S1 to S4 |
| `lkl2_blind` | blind plan x4 | Run B `B-lkl-new-2` | KD-RB-L2-OVENS, KD-RB-L2-BEACON |
| `lkl1_blind` | blind plan x3 | Run B `B-lkl-new-1` | none in the key |
| `os1_blind` | blind plan x5 | Run B `B-os-new-1` | KD-RB-O1-E05, two public-plant entries |
| `lh_postfix` | `out/the-hollow-lighthouse.plan.json` | post-fix book | none known |
| `orchard_postfix` | `out/the-vanishing-orchard.plan.json` | post-fix control book | none known (continuity) |

## Results

Verdicts: `reject` in 11 of 12 runs. The two runs agreed on every case except `lh_postfix` (`reject` 0.6 and `pass`
0.6).

Known defects, both runs unless stated:

| Entry | Reviewer | Deterministic checker (WP-1.5, same plan) |
| --- | --- | --- |
| KD-LH-B1 | should-fix at `e_win_keeper_word` on `ferris_alive_on_moor` (the same near-miss as the checker) | near-miss, judgement call |
| KD-LH-B2 | **found**: `c_cm_light_relight_2` is offered with `has_key` true and `e_set_gears` then says she needs a key (should-fix) | missed |
| KD-LH-B3 | found (`grey_boat_man`, blocker) | found |
| KD-LH-S3 | `n_chamber` on `great_lamp_dark` only (the weak half) | the same |
| KD-RB-L2-OVENS | found (`fn_ovens`, `biscuits_given`) | found |
| KD-RB-L2-BEACON | found (Arthur at the payoff, disjoint branches) | found |
| KD-RB-O1-E05 | found | found |
| Public plant (os1) | related only: the `faulks_pattern` payoff is unearned (both runs), not the public-plant class | missed (SP-4 silent) |

On the post-fix plans, which have no known continuity defects, the reviewer raised findings, and some are real. Verified
against the book: in the Vanishing Orchard, `c_b1a_dec_2` "Pull back from it." leads to `e_b1a`, where Rowan "held the
water a moment too long". The label and the outcome contradict each other, and the WP-0.4 second reader missed it.
Others (the orchard's `kept_everything` after a memory was given at `b2t_p1`, the lighthouse `e_set_stair` gift
against `truth`) are plausible and unverified. Craft findings (forks whose cost announces the setback, a b3 choice with
no lasting effect) are agency points the control book is known to carry.

## Weaknesses seen

- **Misread choice `requires`.** The schema checks a choice's `requires` against what is known on entry to the offering
  node plus that node's `establishes`. The reviewer treated it as known before the node, so it called several branches
  "unreachable" (`og_twins`, the Tobe and developer introductions, the cave pool, `cm_letter_map`). These are false
  blockers caused by the prompt, which did not state the rule.
- **Volume.** 12 to 25 findings per plan, mostly genuine route-level presuppositions the checker also reports. A model
  reviewer adds value on semantic contradictions (B2, the inverted orchard label), not on the route trace the checker
  already does exactly.
- **Reject rate on clean plans.** Under this prompt the reviewer would send nearly every plan to the owner, which
  would defeat review by exception until the prompt and D12 thresholds are set.

## What it suggests for WP-3.7

1. State the `requires` and `establishes` semantics in the prompt, and give the reviewer the deterministic checker's
   findings, so it spends its attention on what the checker cannot see: state contradictions, label and outcome
   mismatches, truth against gifts, agency.
2. Score separately for "checker-visible" and "checker-invisible" findings. The pilot's one clear win over the checker
   (B2) is in the second group.
3. Set `max_tokens` well above the reasoning budget for reasoning models on OpenRouter.
