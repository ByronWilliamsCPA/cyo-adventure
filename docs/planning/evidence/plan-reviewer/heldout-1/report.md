# Plan reviewer validation run heldout-1

Live run on the held_out half.

## Run

| Item | Value |
| --- | --- |
| Half | held_out |
| Reviewer model (configured) | `google/gemini-3.1-pro-preview` |
| Reviewer model (reported by the provider) | `google/gemini-3.1-pro-preview` |
| Writer model | `anthropic/claude-sonnet-5.5` |
| Prompt hash | `sha256:6a3be10872416bfa179cbbff7278b1c28b9b636af70ed38668a8a54014e4371e` |
| Runs per plan | 2 |
| Reasoning | effort `medium`, max_tokens 24000, temperature 0.2 |
| Plans | 46 run, 13 clean-labelled checked only, 0 unrun |
| Spend | 5.55 USD, cap 15 |
| Finish reasons | {'stop': 44} |
| Tokens in / out | 1078480 / 315853 |

## Verdict (G3b)

G3b: **FAIL**

| Condition | Met | Detail |
| --- | --- | --- |
| held-out half | yes | half is held_out |
| live reviewer | yes | a dry run never passes G3b |
| run complete | yes | every selected plan was run within the budget |
| defective plans >= 15 | yes | 17 real defective plans |
| clean baselines cover >= 5 books (D12 amended) | yes | 5 books, 10 baselines, unamended minimum 15 plans |
| defect recall >= 0.9 | NO | 15/17 = 0.88 (95% 0.66 to 0.97) |
| every blocker entry flagged | NO | 26 blocker entries |
| clean false-flag rate <= 0.2 | NO | 6/10 = 0.60 (95% 0.31 to 0.83) |
| run agreement >= 0.9 | NO | 18/22 = 0.82 (95% 0.61 to 0.93) |

Thresholds are the owner's D12 values, fixed before any prompt was written: recall at least 0.9 and every blocker entry; clean flag rate at most 0.2; run agreement at least 0.9; at least 15 defective plans; the clean minimum met by baselines of 5 books, reported per book. Synthetic recall is reported and is not a threshold.

Informational, not a threshold: located recall, family B: 7/8 = 0.88 (95% 0.53 to 0.98) (any-reject recall 7/8 = 0.88 (95% 0.53 to 0.98)).

## (a) Real defective plans

| Figure | Value |
| --- | --- |
| Recall overall (checker plus reviewer) | 15/17 = 0.88 (95% 0.66 to 0.97) |
| Of which checker-caught (no model call) | 13/17 = 0.76 (95% 0.53 to 0.90) |
| Reviewer-decisive recall (the reviewer's own) | 2/4 = 0.50 (95% 0.15 to 0.85) |
| Recall, worst severity blocker | 7/8 = 0.88 (95% 0.53 to 0.98) |
| Recall, worst severity should-fix | 8/9 = 0.89 (95% 0.56 to 0.98) |

Every blocker entry (a plan that carries it counts once per entry):

| Blocker entry | Plans carrying it | Flagged | All flagged |
| --- | --- | --- | --- |
| CC-B1 | 1 | 1 | yes |
| CC-B2 | 1 | 1 | yes |
| CC-B3 | 1 | 1 | yes |
| CC-B4 | 1 | 1 | yes |
| CC-B5 | 1 | 1 | yes |
| CC-B6 | 1 | 1 | yes |
| CM-B1 | 1 | 1 | yes |
| CM-B10 | 1 | 1 | yes |
| CM-B11 | 1 | 1 | yes |
| CM-B2 | 1 | 1 | yes |
| CM-B3 | 1 | 1 | yes |
| CM-B4 | 1 | 1 | yes |
| CM-B5 | 1 | 1 | yes |
| CM-B6 | 1 | 1 | yes |
| CM-B7 | 1 | 1 | yes |
| CM-B8 | 1 | 1 | yes |
| CM-B9 | 1 | 1 | yes |
| MM-F2 | 1 | 1 | yes |
| R1121-SG-2 | 3 | 2 | NO |
| SG-B1 | 1 | 1 | yes |
| SG-B2 | 1 | 1 | yes |
| SG-B3 | 1 | 1 | yes |
| SG-B4 | 1 | 1 | yes |
| SG-B5 | 1 | 1 | yes |
| SS-F3 | 1 | 1 | yes |
| SS-F8 | 1 | 1 | yes |

A plan's `defects` are every defect its book revision carries, an upper bound on what is visible in the plan.

## (b) Synthetic plans (never merged with the real set)

| Figure | Value |
| --- | --- |
| Family A, checker-visible (a floor, not reviewing skill) | 11/11 = 1.00 (95% 0.74 to 1.00) |
| Family B, checker-invisible | 7/8 = 0.88 (95% 0.53 to 0.98) |
| Family B class B1 | 1/2 = 0.50 (95% 0.09 to 0.91) |
| Family B class B2 | 2/2 = 1.00 (95% 0.34 to 1.00) |
| Family B class B3 | 2/2 = 1.00 (95% 0.34 to 1.00) |
| Family B class B4 | 2/2 = 1.00 (95% 0.34 to 1.00) |
| Family B, located (a finding names a seeded entry) | 7/8 = 0.88 (95% 0.53 to 0.98) |
| Family B class B1, located | 1/2 = 0.50 (95% 0.09 to 0.91) |
| Family B class B2, located | 2/2 = 1.00 (95% 0.34 to 1.00) |
| Family B class B3, located | 2/2 = 1.00 (95% 0.34 to 1.00) |
| Family B class B4, located | 2/2 = 1.00 (95% 0.34 to 1.00) |

Synthetic recall overstates real recall: each seed is one defect at a known place in an otherwise clean plan.

Located recall credits a seed only when a reviewer finding (either run) names an entry the seed edited; the any-reject figure credits any reject or unsure, so a reviewer that rejects everything scores 100 percent on it. Located recall is informational: D12 sets no threshold for it, and G3b is unchanged.

## (c) Clean baselines

| Figure | Value |
| --- | --- |
| Flag rate, raw (reject or unsure) | 6/10 = 0.60 (95% 0.31 to 0.83) |
| False-flag rate (flags not at a known residual) | 6/10 = 0.60 (95% 0.31 to 0.83) |
| Flags explained by a known residual (true positives) | 0 |
| False flags on baselines that needed repair | 5/8 = 0.62 (95% 0.31 to 0.86) |
| False flags on baselines that needed no repair | 1/2 = 0.50 (95% 0.09 to 0.91) |

Per book (the effective clean sample is the books, not the plans):

| Book | Baselines | Flagged | False flags |
| --- | --- | --- | --- |
| the-signal-in-the-static | 2 | 2 | 2 |
| the-midnight-museum | 2 | 1 | 1 |
| the-mapmakers-island | 2 | 2 | 2 |
| the-cave-of-echoes | 2 | 1 | 1 |
| the-sky-ship-stowaway | 2 | 0 | 0 |

A reviewer finding at a recorded known residual is a true positive, not a false flag (`AL-882`); a flag elsewhere on the book is still a false flag.

## (d) Run agreement

Identical verdicts across the runs of a plan: 18/22 = 0.82 (95% 0.61 to 0.93).

## (e) Cost model

Projected: 22 plans reach the reviewer (24 the checker already rejects), 44 calls, 1,829,726 input and 616,000 output tokens, about 11.05 USD at 2.0 in and 12.0 out per million tokens (2.1 characters per input token, 14000 output tokens per call).

## (f) Reject-everything diagnostic

| Figure | Value |
| --- | --- |
| Flagged, every plan the reviewer ran on (clean and defective) | 15/22 = 0.68 (95% 0.47 to 0.84) |
| Flagged, clean baselines | 6/10 = 0.60 (95% 0.31 to 0.83) |
| Flagged, seeds the reviewer ran on | 7/8 = 0.88 (95% 0.53 to 0.98) |

No warning: the reviewer did not flag more than 90% of both clean baselines and seeds.

## Plans

| Plan | Source | Book | Expected | Checker | Run verdicts | Final | Findings | Seed located |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PL-x7 | real | the-sky-ship-stowaway | reject | ERROR SP-1,SP-2,SP-6,SP-8 | none | reject | 0 | - |
| PL-x8 | real | the-signal-in-the-static | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-x9 | real | the-midnight-museum | reject | ERROR SP-2,SP-3,SP-8 | none | reject | 0 | - |
| PL-z2 | real | the-clockwork-menagerie | reject | ERROR SP-2,SP-3,SP-9 | none | reject | 0 | - |
| PL-z3 | real | the-clocktower-cipher | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-c2 | real | the-cave-of-echoes | reject | ERROR SP-2 | none | reject | 0 | - |
| PL-c3 | real | the-signal-in-the-static | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-c4 | real | the-mapmakers-island | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-c5 | real | the-sky-ship-stowaway | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-d1 | real | the-sky-ship-stowaway | reject | ERROR SP-2 | none | reject | 0 | - |
| PL-d2 | real | the-mapmakers-island | reject | ERROR SP-2,SP-3 | none | reject | 0 | - |
| PL-d4 | real | the-signal-in-the-static | reject | ERROR SP-2 | none | reject | 0 | - |
| PL-d5 | real | the-cave-of-echoes | reject | clean | reject, reject | reject | 1 | - |
| PL-the-sky-ship-stowaway-postfix | real | the-sky-ship-stowaway | reject | ERROR SP-8 | none | reject | 0 | - |
| PL-the-signal-in-the-static-postfix | real | the-signal-in-the-static | reject | clean | pass, pass | pass | 0 | - |
| PL-the-cave-of-echoes-postfix | real | the-cave-of-echoes | reject | clean | reject, reject | reject | 4 | - |
| PL-the-mapmakers-island-postfix | real | the-mapmakers-island | reject | clean | pass, pass | pass | 0 | - |
| SY-A-SP-1-1 | synthetic | the-cave-of-echoes | reject | ERROR SP-1 | none | reject | 0 | NO |
| SY-A-SP-9-1 | synthetic | the-cave-of-echoes | reject | ERROR SP-9 | none | reject | 0 | NO |
| SY-A-SP-2-1 | synthetic | the-mapmakers-island | reject | ERROR SP-2 | none | reject | 0 | NO |
| SY-A-SP-7-1 | synthetic | the-mapmakers-island | reject | ERROR SP-7 | none | reject | 0 | NO |
| SY-A-SP-8-1 | synthetic | the-mapmakers-island | reject | ERROR SP-8 | none | reject | 0 | NO |
| SY-A-SP-4-1 | synthetic | the-signal-in-the-static | reject | ERROR SP-4 | none | reject | 0 | NO |
| SY-A-SP-6-1 | synthetic | the-signal-in-the-static | reject | ERROR SP-6 | none | reject | 0 | NO |
| SY-A-SP-4-2 | synthetic | the-midnight-museum | reject | ERROR SP-4 | none | reject | 0 | NO |
| SY-A-SP-5-1 | synthetic | the-midnight-museum | reject | ERROR SP-5 | none | reject | 0 | NO |
| SY-A-SP-3-1 | synthetic | the-sky-ship-stowaway | reject | ERROR SP-3 | none | reject | 0 | NO |
| SY-A-SP-9-2 | synthetic | the-sky-ship-stowaway | reject | ERROR SP-9 | none | reject | 0 | NO |
| SY-B-B1-1 | synthetic | the-cave-of-echoes | reject | clean | reject, reject | reject | 2 | yes |
| SY-B-B3-1 | synthetic | the-cave-of-echoes | reject | clean | reject, reject | reject | 2 | yes |
| SY-B-B2-1 | synthetic | the-mapmakers-island | reject | clean | reject, reject | reject | 1 | yes |
| SY-B-B3-2 | synthetic | the-signal-in-the-static | reject | clean | reject, reject | reject | 2 | yes |
| SY-B-B4-1 | synthetic | the-signal-in-the-static | reject | clean | reject, reject | reject | 2 | yes |
| SY-B-B1-2 | synthetic | the-midnight-museum | reject | clean | pass, pass | pass | 0 | NO |
| SY-B-B4-2 | synthetic | the-midnight-museum | reject | clean | reject, reject | reject | 2 | yes |
| SY-B-B2-2 | synthetic | the-sky-ship-stowaway | reject | clean | reject, reject | reject | 1 | yes |
| CBL-PL-e1 | baseline | the-signal-in-the-static | pass | clean | pass, reject | unsure | 1 | - |
| CBL-PL-e2 | baseline | the-midnight-museum | pass | clean | pass, pass | pass | 0 | - |
| CBL-PL-e3 | baseline | the-mapmakers-island | pass | clean | pass, reject | unsure | 3 | - |
| CBL-PL-e4 | baseline | the-cave-of-echoes | pass | clean | reject, reject | reject | 2 | - |
| CBL-PL-e5 | baseline | the-sky-ship-stowaway | pass | clean | pass, pass | pass | 1 | - |
| CBL-PL-f1 | baseline | the-cave-of-echoes | pass | clean | pass, pass | pass | 0 | - |
| CBL-PL-f2 | baseline | the-sky-ship-stowaway | pass | clean | pass, pass | pass | 0 | - |
| CBL-PL-f3 | baseline | the-signal-in-the-static | pass | clean | reject, reject | reject | 2 | - |
| CBL-PL-f4 | baseline | the-mapmakers-island | pass | clean | pass, reject | unsure | 2 | - |
| CBL-PL-f5 | baseline | the-midnight-museum | pass | clean | reject, pass | unsure | 1 | - |

## Findings by plan (flagged plans; reasons are in results.json)

- PL-d5: c_retreat (label_outcome_mismatch, should-fix)
- PL-the-cave-of-echoes-postfix: c_retreat (label_outcome_mismatch, should-fix); lighthouse_ranger (state_contradiction, minor); ra_islet (state_contradiction, should-fix); ra_islet (ending_gift_mismatch, should-fix)
- SY-B-B1-1: c_lakeback (label_outcome_mismatch, should-fix); c_retreat (label_outcome_mismatch, should-fix)
- SY-B-B3-1: da_bat_back (ending_gift_mismatch, blocker); c_retreat (label_outcome_mismatch, should-fix)
- SY-B-B2-1: alder_sailed_home (truth_contradiction, blocker)
- SY-B-B3-2: e_count_wait (ending_gift_mismatch, blocker); e_count_wait (ending_gift_mismatch, should-fix)
- SY-B-B4-1: has_battery (payoff_shows_mismatch, should-fix); e_re_log (ending_gift_mismatch, should-fix)
- SY-B-B4-2: has_chalk (payoff_shows_mismatch, should-fix); c_map_follow (label_outcome_mismatch, should-fix)
- SY-B-B2-2: quill_sells_calf (truth_contradiction, blocker)
- CBL-PL-e1: e_re_log (ending_gift_mismatch, should-fix)
- CBL-PL-e3: summit_signal (state_contradiction, blocker); ch_sightings (state_contradiction, blocker); ch_ink (state_contradiction, blocker)
- CBL-PL-e4: c_retreat (label_outcome_mismatch, should-fix); c_poolback (label_outcome_mismatch, should-fix)
- CBL-PL-f3: e_st_alder_refuse (truth_contradiction, blocker); c_r_re_cellar2_2 (label_outcome_mismatch, should-fix)
- CBL-PL-f4: c_ch_sign_3 (label_outcome_mismatch, should-fix); c_summit_signal_2 (label_outcome_mismatch, should-fix)
- CBL-PL-f5: has_chalk (payoff_shows_mismatch, should-fix)

## Limits

- Synthetic recall overstates real recall, and family A is checker-visible by construction.
- The clean sample is five books; per-book results matter more than the pooled rate.
- The plan writer is Sonnet 5.5, so the reviewer must be a different model; independence is enforced on configured ids only.
- There is no measured recall on dull, generic or off-request plans: those classes stay advisory.
- One reader per book labelled the real set; a clean label is the latest verified state.
