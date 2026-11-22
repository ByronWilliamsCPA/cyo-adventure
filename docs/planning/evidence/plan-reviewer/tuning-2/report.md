# Plan reviewer validation run tuning-2

Live run on the tuning half.

## Run

| Item | Value |
| --- | --- |
| Half | tuning |
| Reviewer model (configured) | `google/gemini-3.1-pro-preview` |
| Reviewer model (reported by the provider) | `google/gemini-3.1-pro-preview` |
| Writer model | `anthropic/claude-sonnet-5.5` |
| Prompt hash | `sha256:6a3be10872416bfa179cbbff7278b1c28b9b636af70ed38668a8a54014e4371e` |
| Runs per plan | 2 |
| Reasoning | effort `medium`, max_tokens 24000, temperature 0.2 |
| Plans | 27 run, 2 clean-labelled checked only, 0 unrun |
| Spend | 1.39 USD, cap 5 |
| Finish reasons | {'stop': 12} |
| Tokens in / out | 321322 / 62634 |

## Verdict (G3b)

**G3b: FAIL** (the tuning half never passes G3b: it guides prompt work only)

| Condition | Met | Detail |
| --- | --- | --- |
| held-out half | NO | half is tuning |
| live reviewer | yes | a dry run never passes G3b |
| run complete | yes | every selected plan was run within the budget |
| defective plans >= 15 | NO | 12 real defective plans |
| clean baselines cover >= 5 books (D12 amended) | NO | 2 books, 2 baselines, unamended minimum 15 plans |
| defect recall >= 0.9 | yes | 12/12 = 1.00 (95% 0.76 to 1.00) |
| every blocker entry flagged | yes | 8 blocker entries |
| clean false-flag rate <= 0.2 | NO | 1/2 = 0.50 (95% 0.09 to 0.91) |
| run agreement >= 0.9 | yes | 6/6 = 1.00 (95% 0.61 to 1.00) |

Thresholds are the owner's D12 values, fixed before any prompt was written: recall at least 0.9 and every blocker entry; clean flag rate at most 0.2; run agreement at least 0.9; at least 15 defective plans; the clean minimum met by baselines of 5 books, reported per book. Synthetic recall is reported and is not a threshold.

Informational, not a threshold: located recall, family B: 3/4 = 0.75 (95% 0.30 to 0.95) (any-reject recall 4/4 = 1.00 (95% 0.51 to 1.00)).

**WARNING: the reviewer flagged more than 90% of both clean baselines (2/2 = 1.00 (95% 0.34 to 1.00)) and seeds (4/4 = 1.00 (95% 0.51 to 1.00)): it discriminates nothing, so its any-reject recall means nothing; read located recall.**

## (a) Real defective plans

| Figure | Value |
| --- | --- |
| Recall overall (checker plus reviewer) | 12/12 = 1.00 (95% 0.76 to 1.00) |
| Of which checker-caught (no model call) | 12/12 = 1.00 (95% 0.76 to 1.00) |
| Reviewer-decisive recall (the reviewer's own) | 0/0 (no plans) |
| Recall, worst severity blocker | 5/5 = 1.00 (95% 0.57 to 1.00) |
| Recall, worst severity leak | 5/5 = 1.00 (95% 0.57 to 1.00) |
| Recall, worst severity thin | 2/2 = 1.00 (95% 0.34 to 1.00) |

Every blocker entry (a plan that carries it counts once per entry):

| Blocker entry | Plans carrying it | Flagged | All flagged |
| --- | --- | --- | --- |
| KD-LH-B1 | 2 | 2 | yes |
| KD-LH-B2 | 2 | 2 | yes |
| KD-LH-B3 | 2 | 2 | yes |
| KD-LH-BS1 | 2 | 2 | yes |
| TT-B1 | 1 | 1 | yes |
| TT-B2 | 1 | 1 | yes |
| TT-B3 | 1 | 1 | yes |
| TT-B4 | 1 | 1 | yes |

A plan's `defects` are every defect its book revision carries, an upper bound on what is visible in the plan.

## (b) Synthetic plans (never merged with the real set)

| Figure | Value |
| --- | --- |
| Family A, checker-visible (a floor, not reviewing skill) | 9/9 = 1.00 (95% 0.70 to 1.00) |
| Family B, checker-invisible | 4/4 = 1.00 (95% 0.51 to 1.00) |
| Family B class B1 | 1/1 = 1.00 (95% 0.21 to 1.00) |
| Family B class B2 | 1/1 = 1.00 (95% 0.21 to 1.00) |
| Family B class B3 | 1/1 = 1.00 (95% 0.21 to 1.00) |
| Family B class B4 | 1/1 = 1.00 (95% 0.21 to 1.00) |
| Family B, located (a finding names a seeded entry) | 3/4 = 0.75 (95% 0.30 to 0.95) |
| Family B class B1, located | 0/1 = 0.00 (95% 0.00 to 0.79) |
| Family B class B2, located | 1/1 = 1.00 (95% 0.21 to 1.00) |
| Family B class B3, located | 1/1 = 1.00 (95% 0.21 to 1.00) |
| Family B class B4, located | 1/1 = 1.00 (95% 0.21 to 1.00) |

Synthetic recall overstates real recall: each seed is one defect at a known place in an otherwise clean plan.

Located recall credits a seed only when a reviewer finding (either run) names an entry the seed edited; the any-reject figure credits any reject or unsure, so a reviewer that rejects everything scores 100 percent on it. Located recall is informational: D12 sets no threshold for it, and G3b is unchanged.

## (c) Clean baselines

| Figure | Value |
| --- | --- |
| Flag rate, raw (reject or unsure) | 2/2 = 1.00 (95% 0.34 to 1.00) |
| False-flag rate (flags not at a known residual) | 1/2 = 0.50 (95% 0.09 to 0.91) |
| Flags explained by a known residual (true positives) | 1 |
| False flags on baselines that needed repair | 0/0 (no plans) |
| False flags on baselines that needed no repair | 1/2 = 0.50 (95% 0.09 to 0.91) |

Per book (the effective clean sample is the books, not the plans):

| Book | Baselines | Flagged | False flags |
| --- | --- | --- | --- |
| the-hollow-lighthouse | 1 | 1 | 0 |
| the-vanishing-orchard | 1 | 1 | 1 |

A reviewer finding at a recorded known residual is a true positive, not a false flag (`AL-882`); a flag elsewhere on the book is still a false flag.

## (d) Run agreement

Identical verdicts across the runs of a plan: 6/6 = 1.00 (95% 0.61 to 1.00).

## (e) Cost model

Projected: 6 plans reach the reviewer (21 the checker already rejects), 12 calls, 516,552 input and 168,000 output tokens, about 3.05 USD at 2.0 in and 12.0 out per million tokens (2.1 characters per input token, 14000 output tokens per call).

## (f) Reject-everything diagnostic

| Figure | Value |
| --- | --- |
| Flagged, every plan the reviewer ran on (clean and defective) | 6/6 = 1.00 (95% 0.61 to 1.00) |
| Flagged, clean baselines | 2/2 = 1.00 (95% 0.34 to 1.00) |
| Flagged, seeds the reviewer ran on | 4/4 = 1.00 (95% 0.51 to 1.00) |

**WARNING: the reviewer flagged more than 90% of both clean baselines (2/2 = 1.00 (95% 0.34 to 1.00)) and seeds (4/4 = 1.00 (95% 0.51 to 1.00)): it discriminates nothing, so its any-reject recall means nothing; read located recall.**

## Plans

| Plan | Source | Book | Expected | Checker | Run verdicts | Final | Findings | Seed located |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PL-x1 | real | the-hollow-lighthouse | reject | ERROR SP-2,SP-3,SP-4,SP-6 | none | reject | 0 | - |
| PL-x2 | real | the-hollow-lighthouse | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-x4 | real | the-lantern-keepers-list | reject | ERROR SP-2,SP-3,SP-4,SP-6,SP-8 | none | reject | 0 | - |
| PL-x5 | real | the-orchard-signal | reject | ERROR SP-2,SP-3,SP-4,SP-6,SP-8 | none | reject | 0 | - |
| PL-x5b | real | the-orchard-signal | reject | ERROR SP-2,SP-3,SP-4,SP-6 | none | reject | 0 | - |
| PL-x6 | real | the-orchard-signal | reject | ERROR SP-2,SP-3,SP-4,SP-6,SP-8 | none | reject | 0 | - |
| PL-y1 | real | the-orchard-signal | reject | ERROR SP-2,SP-3,SP-4,SP-6 | none | reject | 0 | - |
| PL-y2 | real | the-hollow-lighthouse | reject | ERROR SP-2,SP-3,SP-4,SP-6 | none | reject | 0 | - |
| PL-y3 | real | the-orchard-signal | reject | ERROR SP-2,SP-3,SP-4,SP-6 | none | reject | 0 | - |
| PL-y4 | real | the-hollow-lighthouse | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-y5 | real | the-lantern-keepers-list | reject | ERROR SP-2,SP-3,SP-6,SP-9 | none | reject | 0 | - |
| PL-z1 | real | the-thornwood-trial | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| SY-A-SP-4-3 | synthetic | the-hollow-lighthouse | reject | ERROR SP-4 | none | reject | 0 | NO |
| SY-A-SP-5-2 | synthetic | the-hollow-lighthouse | reject | ERROR SP-5 | none | reject | 0 | NO |
| SY-A-SP-9-3 | synthetic | the-hollow-lighthouse | reject | ERROR SP-9 | none | reject | 0 | NO |
| SY-A-SP-1-2 | synthetic | the-vanishing-orchard | reject | ERROR SP-1 | none | reject | 0 | NO |
| SY-A-SP-2-2 | synthetic | the-vanishing-orchard | reject | ERROR SP-2 | none | reject | 0 | NO |
| SY-A-SP-3-2 | synthetic | the-vanishing-orchard | reject | ERROR SP-3 | none | reject | 0 | NO |
| SY-A-SP-7-2 | synthetic | the-vanishing-orchard | reject | ERROR SP-7 | none | reject | 0 | NO |
| SY-A-SP-8-2 | synthetic | the-vanishing-orchard | reject | ERROR SP-8 | none | reject | 0 | NO |
| SY-A-SP-9-4 | synthetic | the-vanishing-orchard | reject | ERROR SP-9 | none | reject | 0 | NO |
| SY-B-B1-3 | synthetic | the-hollow-lighthouse | reject | clean | reject, reject | reject | 2 | NO |
| SY-B-B4-3 | synthetic | the-hollow-lighthouse | reject | clean | reject, reject | reject | 2 | yes |
| SY-B-B2-3 | synthetic | the-vanishing-orchard | reject | clean | reject, reject | reject | 4 | yes |
| SY-B-B3-3 | synthetic | the-vanishing-orchard | reject | clean | reject, reject | reject | 3 | yes |
| CBL-PL-the-hollow-lighthouse-postfix | baseline | the-hollow-lighthouse | pass | clean | reject, reject | reject | 1 | - |
| CBL-PL-the-vanishing-orchard-postfix | baseline | the-vanishing-orchard | pass | clean | reject, reject | reject | 4 | - |

## Findings by plan (flagged plans; reasons are in results.json)

- SY-B-B1-3: e_set_stair (ending_gift_mismatch, blocker); e_set_stair (ending_gift_mismatch, should-fix)
- SY-B-B4-3: t_key (payoff_shows_mismatch, should-fix); e_set_stair (ending_gift_mismatch, should-fix)
- SY-B-B2-3: grandmother_writes_postcards (truth_contradiction, blocker); c_b1a_dec_2 (label_outcome_mismatch, should-fix); c_fin_one_2_2 (label_outcome_mismatch, should-fix); c_b2t_m_2 (label_outcome_mismatch, should-fix)
- SY-B-B3-3: e_pho_a (ending_gift_mismatch, should-fix); c_b1a_dec_2 (label_outcome_mismatch, should-fix); c_b2t_m_2 (label_outcome_mismatch, should-fix)
- CBL-PL-the-hollow-lighthouse-postfix: e_set_stair (ending_gift_mismatch, blocker)
- CBL-PL-the-vanishing-orchard-postfix: c_b1a_dec_2 (label_outcome_mismatch, blocker); e_trade_photo (state_contradiction, blocker); c_b2t_m_2 (label_outcome_mismatch, should-fix); name_every_year (state_contradiction, blocker)

## Limits

- Synthetic recall overstates real recall, and family A is checker-visible by construction.
- The clean sample is five books; per-book results matter more than the pooled rate.
- The plan writer is Sonnet 5.5, so the reviewer must be a different model; independence is enforced on configured ids only.
- There is no measured recall on dull, generic or off-request plans: those classes stay advisory.
- One reader per book labelled the real set; a clean label is the latest verified state.
