# Story Plan retrospective gate G1: the D5 re-run report

Date: 2026-11-21. Work package: WP-1.5 of `docs/planning/story-plan-implementation-plan.md`, re-run under owner
decision D5 ("take the single permitted revision and one re-run"). Gate: G1. Owner decision that consumes this report:
D5 ("Accept the G1 verdict").

This run measures. It changes no plan, assertion file, answer key, checker or book. (Written to the repo by the orchestrator from the scoring agent's report text, verbatim, because the
harness refused the agent's own write of this file; see `AL-807`.) Method, scoring definitions and
table formats are those of the first run's [report](../report.md), reused unchanged.

## Inputs and commits

| Input | Location | Commit |
| --- | --- | --- |
| Pass criterion (pre-registered, unchanged) | `docs/planning/story-plan-implementation-plan.md`, WP-1.5 | WP-1.5 section byte-identical to `87dc088` (checked by diff against the current file) |
| Answer key, 17 entries, `frozen: true` | `known-defects.json` (sha256 `6f5ded17bf66...`, re-checked) | `8dbeba7`, unchanged |
| Revised checker (the one D5 revision) | `src/cyo_adventure/storyplan/checks.py`, `scripts/check_story_plan.py` | `a671309`; no later commit touches either |
| Re-extraction prompt | `plans/EXTRACTION-PROMPT-v2.md` | `01521fa` |
| Re-run blind plans, assertion maps, manifest | `rerun/plans/y*.plan.json`, `rerun/assertions/y*.json`, `rerun/manifest.json` | `89984d9` |
| First-run blind plans (for separating effects) | `plans/x1`, `x2`, `x4`, `x5`, `x5b`, `x6` | `27066c5` |
| False-alarm books and plans (post WP-0.4, same as the first run) | `out/<slug>.filled.json`, `out/<slug>.plan.json` | lighthouse `3e29e04` / `b016455`; sky-ship `e9adcd1` / `600536d`; museum `a0b61e9` / `600536d`; signal `38f6a5a` / `b016455` |
| Raw outputs of this run | `rerun/runs/` | `1e90250` |

Runtime: Python 3.14.6 under `uv run`. Raw outputs:

- `rerun/runs/<id>.json`: the five re-run plans, `check_story_plan.py <book> <plan> --json --assertions <map>`.
- `rerun/runs/false-alarm/<slug>.json`: the four post-fix books, revised checker, no assertion maps.
- `rerun/runs/first-run-plans-revised-checker/<id>.json`: the first-run plans x1, x2, x4, x5, x5b and x6 with their
  first-run assertion maps, revised checker. x5b is included because the first run scored the October Blossom
  public-plant entries on both x5 and x5b.

### Staging and binding

Each re-run input was recreated from the manifest into `tmp_cleanup/rerun/<id>.book.json` (`git show <rev>:<path>`
for `git:` revisions, a copy of the worktree file otherwise). All five sha256 values equal the manifest. SP-0 reported
nothing on any run; `provenance.book_file` (`tmp_cleanup/blind/<id>.book.json`, the extractor's staging path) is
echoed but not compared. The checker did not crash on any input. Every blind run exited 1 (ERROR findings present);
on the false-alarm set, sky-ship exited 1 and the other three exited 0. Runs y1 and y2 were repeated and were
byte-identical.

| Re-run id | Book | Answer-key entries scored | First-run id | Minutes (manifest) |
| --- | --- | --- | --- | ---: |
| y1 | The October Blossom, `B-os-new-1` | KD-RB-O1-E05, KD-OS-PP-B-os-new-1-* | x5 (and x5b) | 70 |
| y2 | The Hollow Lighthouse, pre-fix revised (`15b14a1`) | KD-LH-B1 to KD-LH-S4 | x1 | 75 |
| y3 | The Orchard Signal, `B-os-new-2` | KD-OS-PP-B-os-new-2-* | x6 | 12 (the agent flagged this as likely too short) |
| y4 | The Hollow Lighthouse, original fill (`f3ba310`) | KD-LH-BS1 | x2 | 75 |
| y5 | The Lantern Keepers' List, `B-lkl-new-2` | KD-RB-L2-OVENS, KD-RB-L2-BEACON | x4 | 70 |

## Verdict

| Criterion (pre-registered, quoted in short) | Result | Verdict | Evidence |
| --- | --- | --- | --- |
| Exact class: the public plant (SP-4), 100 percent | 4 of 4 entries | PASS | y1: SP-4 at `n04d0` on `survey_signed_faulks`; y3: SP-4 at `n04d0` on `survey_signed_faulks` and `jonah_learned_author`. Both with `did_find_who_wrote=false`, route `n03d2 > c_n03d2_2 > n04d0`, the opening of the key's first witness |
| Exact class: the cross-payoff reference (SP-6), 100 percent | 1 of 1 | PASS | y5: SP-6 at `cq_payoff_did_start_beacon_steps` on `arthur` and `arthur_at_gate`, reached through `fn_up`, `did_start_beacon_steps=true` |
| Exact class: the two backstories (SP-3), 100 percent | 1 of 1 | PASS | y4: SP-3 ERROR "one reading meets both" `ferris_built_light` (`cm_light`) against `ferris_unaware_light_source` (`jr_light`); a second at `n_chamber` against `ferris_left_light_burning` |
| Assertion class: all three Run B leaks found | 3 of 3 | PASS | OVENS (y5, SP-2/SP-A `gave_biscuits_to_ovens`, `asked_ovens_before`), O1-E05 (y1, SP-2/SP-A `jonah_photo_of_notice`, `exercise_book_eleven_words`), BEACON (y5, SP-6 and SP-2/SP-A) |
| Assertion class: at least two of B1 to B3, with a reason for any miss | 2 of 3 (B2, B3); B1 missed | PASS | B1's reason below. B2 is found because the v2 extraction recorded the negation at `e_set_gears` (see the disclosure) |
| False alarms: on the four revised books after WP-0.4, no more than one ERROR per book a human judges wrong | 1 ERROR in all (sky-ship SP-8); lighthouse, museum and signal 0 | PASS whatever the judgement (no book has more than one ERROR, so none can exceed the budget) | The one ERROR's proposed judgement is "unclear"; the judgement is the owner's (D5) |
| **G1 overall** | | **PASS as scored** | Every row passes on a mechanical count. Acceptance of the verdict is the owner's under D5, to be read with the disclosure section |

## Per-entry scoring (all 17 answer-key entries)

"Found" means a finding at the entry's node (or a node in `other_nodes`) on the entry's fact, in a witness state
consistent with the entry's trigger. A finding at the right node on an unrelated fact is not counted.

| Entry | Gating? | Plan | Finding(s) matched: rule, node, fact, witness | Scored | Notes |
| --- | --- | --- | --- | --- | --- |
| KD-LH-B1 | yes (Lighthouse blocker) | y2 | None at `e_win_keeper_word` | missed | The plan has no fact for Ferris's earlier spoken warning. The ending requires `bog_second_gate`, which `cm_letter_map` (the map's "mind this") establishes on B1's route, so nothing is unguaranteed. The first run's near-miss (a duplicated "Ferris alive" fact) does not occur in y2, so this is a clean miss, not a judgement call |
| KD-LH-B2 | yes (Lighthouse blocker) | y2 | SP-3 ERROR at `e_set_gears`, choice `c_cm_light_relight_2`, `mira_has_key` (planted at `b_lens_reflect` and the other key sites) against `mira_has_no_key` (at `e_set_gears`), `has_key=true`, route identical to the key's witness | found | The plan records `e_set_gears` as establishing and asserting `mira_has_no_key`, which is what the v2 negation instruction asks for (manifest note) |
| KD-LH-B3 | yes (Lighthouse blocker) | y2 | Name half: SP-3 ERROR at `e_win_harbor`, choice `c_cm_smug_photo_2`, `mira_unaware_name` against `smuggler_named_varley` (at `jr_smug_names`), route identical to the key's first witness. Boat half: SP-2 and SP-A at `e_win_harbor` on `smuggler_grey_boat`, 14 of 14 states, route identical to the key's second witness | found (both halves) | |
| KD-LH-B3-follow | no (sibling) | y2 | SP-2 and SP-A at `cm_smug_follow` on `smuggler_grey_boat`, 14 of 14 states, route without `b_gallery_edge` or `cm_cottage` | found | |
| KD-LH-B3-honest | no (sibling) | y2 | SP-2 and SP-A at `e_neutral_honest` on `smuggler_grey_boat` | found | As in x1, the plan does not let `cm_smug_follow` establish the boat, so both nodes are flagged |
| KD-LH-S1 | no | y2 | None at `e_win_promise` | missed | The ending requires `ferris_on_moor`, which the letter supports; "where on the moor" is not a requirement in the plan. Entry is marked weak in the key |
| KD-LH-S2 | no | y2 | None | missed (expected) | Repeated reveal; no SP rule covers it |
| KD-LH-S3 | no | y2 | SP-2 and SP-A at `n_chamber` on `store_crates` ("The room that smells of tar is a store stacked with unmarked crates and barrels"), 14 of 14 states, route via `tn_cut` identical to the key's first witness; also SP-2 on the choice `c_n_chamber_2` ("Go back to the store that smells of tar") | found (mild judgement call) | The store half is the key's assertion. The plan's fact bundles the crates, which `n_chamber` does not mention, but the node presupposes the store has been entered ("behind her", "go back"), which is the entry's fact. A `great_lens` finding at the same node is the lamp half the key marks weak and is not counted |
| KD-LH-S4 | no | y2 | None at `e_set_a_drawer` | missed | The plan has no kitchen fact |
| KD-LH-BS1 | yes (exact, SP-3) | y4 | SP-3 ERROR at `cm_light` (via `c_n_chamber_3`), `ferris_built_light` against `ferris_unaware_light_source` (`jr_light`), on a route through `jr_light`, one reading meets both. Also SP-3 ERROR at `n_chamber` (via `c_tn_gate_open_1`), `ferris_unaware_light_source` against `ferris_left_light_burning` (`n_chamber`, `cm_letter_read`) | found | Claim set A (`jr_light`) against claim set B (`cm_light`, `n_chamber`, `cm_letter_read`). y4 has six further SP-3 ERRORs not in the key (a door both ajar and locked, the journal's position, crate declarations, the hidden stair's direction) |
| KD-RB-L2-OVENS | yes (Run B leak) | y5 | SP-2 and SP-A at `fn_ovens` on `gave_biscuits_to_ovens` and `asked_ovens_before`, 6 of 6 states, witness `did_start_sheepfold_turn=false`, route identical to the key's first witness (`bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_can > oil_school > oil_line > oil_count > fn_ovens`) | found | `asked_ovens_before` ("asked once today, politely with biscuits") also covers the key's "second time" extension; `quad_bike` is flagged too |
| KD-RB-O1-E05 | yes (Run B leak) | y1 | SP-2 and SP-A at `e05_0` on `jonah_photo_of_notice` (1 of 2 states, `did_go_down_read=false`) and `exercise_book_eleven_words` (2 of 2), on the key's witness route (`n03d0 > c_n03d0_2 > n04d2 > c_n04d2_0 > e05_0`) | found | Covers the photo and the copied words of the key's three-fact extension |
| KD-RB-L2-BEACON | yes (exact SP-6 and Run B leak) | y5 | SP-6 at `cq_payoff_did_start_beacon_steps` on `arthur` and `arthur_at_gate` (2 of 2 states), via `oil_taper > fn_up > c_fn_up_2_cq_did_start_beacon_steps`; SP-2 and SP-A on the same facts | found | |
| KD-OS-PP-B-os-new-1-n11d1 | yes (exact, SP-4) | y1 | SP-4 at `n04d0` on `survey_signed_faulks`, `did_find_who_wrote=false`, `did_go_down_read=true`, route `n03d2 > c_n03d2_2 > n04d0` (the opening of the key's first witness, which continues to the payoff site). Label half: SP-2 and SP-A at `n04d2`, choice `c_n04d2_2`, on `survey_signed_faulks`, `did_find_who_wrote=false` | found | The plan again declares the private half as the plant (`jonah_sought_author`); SP-4 now checks what the planting edge makes known (`cq_plant_did_find_who_wrote` establishes `survey_signed_faulks`) that a payoff passage requires (both payoff passages require it) |
| KD-OS-PP-B-os-new-1-n11d5 | yes (exact, SP-4) | y1 | The same SP-4 finding at `n04d0`, and the same label finding | found | SP-4 reports one finding per node and fact, so one finding at `n04d0` covers both payoff entries of this book, which share `n04d0`, the fact and the trigger. Related, as in the first run: SP-6 and SP-2 at `cq_payoff_did_find_who_wrote` on `faulks_pattern` (the key's "unearned" reader judgement) |
| KD-OS-PP-B-os-new-2-n11d1 | yes (exact, SP-4) | y3 | SP-4 at `n04d0` on `survey_signed_faulks` and on `jonah_learned_author`, same witness; label half SP-2 and SP-A at `n04d2`, choice `c_n04d2_2` | found (note) | Meets the definition (node in `other_nodes`, the name fact, the key's witness). Note: y3 records this payoff passage (`cq_payoff_did_find_who_wrote_site2`) as requiring only the private fact `faulks_name_in_ada_book`; SP-4 reaches the public name through the other payoff passage, which requires `survey_signed_faulks` and `jonah_learned_author` |
| KD-OS-PP-B-os-new-2-n11d5 | yes (exact, SP-4) | y3 | The same SP-4 findings at `n04d0` | found | Related: SP-3 ERROR at `e12_1` ("did not track down the name in time") against `jonah_learned_author` at `n04d0`, on a route through `n04d0` with `did_find_who_wrote=false`, a consequence of the same public plant |

Tally: exact classes 6 of 6 entries (public plant 4 of 4, cross-payoff 1 of 1, two backstories 1 of 1). Run B leaks 3
of 3. Lighthouse blockers 2 of 3. Non-gating: B3-follow, B3-honest and S3 found; S1, S2 (by design) and S4 missed.

### Reason for the Lighthouse B1 miss

B1 is an unestablished-fact defect whose fact is speech: Ferris's warning about the bog, delivered at `cm_cottage_wait`
and recalled at `e_win_keeper_word` ("Minded the bog, I see"). y2 records the bog itself (`bog_second_gate`) and has
both `cm_letter_map` and `cm_cottage_wait` establish it, so on B1's route (through the map) the ending's requirement
is guaranteed and nothing is flagged. The fact model can see the defect only if the extractor records "Ferris warned
Mira about the bog" as a fact distinct from "there is a bog", which neither blind extraction did.

## Comparison with the first run

### Per entry

The third column runs the revised checker on the first-run plans, which separates the effect of the checker revision
(column 2 to column 3) from the effect of the new extractions (column 3 to column 4).

| Entry | First run (x plan, first-run checker) | First-run plan, revised checker | Re-run (y plan, revised checker) | Difference comes from |
| --- | --- | --- | --- | --- |
| KD-LH-B1 | missed (judgement call) | missed (judgement call: the same `ferris_alive_on_moor` near-miss) | missed (clean) | extraction (y2 has no near-duplicate fact) |
| KD-LH-B2 | missed | missed | found | extraction (negation recorded at `e_set_gears`) |
| KD-LH-B3 | found | found | found | none |
| KD-LH-B3-follow | found | found | found | none |
| KD-LH-B3-honest | found | found | found | none |
| KD-LH-S1 | missed | missed | missed | none |
| KD-LH-S2 | missed (expected) | missed (expected) | missed (expected) | none |
| KD-LH-S3 | missed | missed | found | extraction (`store_crates` required at `n_chamber`) |
| KD-LH-S4 | missed | missed | missed | none |
| KD-LH-BS1 | found | found | found | none |
| KD-RB-L2-OVENS | found | found | found | none |
| KD-RB-O1-E05 | found (x5, x5b) | found | found | none |
| KD-RB-L2-BEACON | found | found | found | none |
| KD-OS-PP-B-os-new-1-n11d1 | missed (x5, x5b) | found (x5 on `faulks_wrote_survey`, x5b on `survey_signed_faulks`, both at `n04d0`) | found | checker revision (SP-4, `AL-817`) |
| KD-OS-PP-B-os-new-1-n11d5 | missed (x5, x5b) | found (as above) | found | checker revision |
| KD-OS-PP-B-os-new-2-n11d1 | missed (x6) | found (x6, `faulks_wrote_survey` at `n04d0`) | found | checker revision |
| KD-OS-PP-B-os-new-2-n11d5 | missed (x6) | found (as above) | found | checker revision |

Counterfactual: the revised checker on the first-run plans would score exact classes 6 of 6, Run B leaks 3 of 3, and
Lighthouse blockers 1 of 3 (2 of 3 only if B1's near-miss were counted). The pass therefore rests on both changes:
the checker revision supplies the public plant and the false-alarm reduction; the re-extraction supplies B2.

### ERROR counts per plan, by rule

First-run figures are from the first report's noise table. SP-1 is 0 on every row and is omitted; no other rule
reported an ERROR.

| Plan | Run | SP-2 | SP-3 | SP-4 | SP-6 | SP-8 | SP-9 | SP-A | Total | Nodes with an ERROR |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| x1 | first run | 10 | 1 | 0 | 1 | 0 | 7 | 20 | 39 | 19 of 162 |
| x1 | revised checker | 10 | 1 | 1 | 1 | 0 | 0 | 20 | 33 | 16 of 162 |
| y2 | re-run | 19 | 2 | 1 | 2 | 0 | 0 | 24 | 48 | 18 of 162 |
| x2 | first run | 24 | 2 | 0 | 0 | 0 | 0 | 25 | 51 | 24 of 149 |
| x2 | revised checker | 24 | 2 | 0 | 0 | 0 | 0 | 25 | 51 | 24 of 149 |
| y4 | re-run | 25 | 8 | 0 | 0 | 0 | 0 | 18 | 51 | 27 of 149 |
| x4 | first run | 105 | 1 | 0 | 7 | 13 | 0 | 100 | 226 | 63 of 132 |
| x4 | revised checker | 105 | 1 | 4 | 7 | 13 | 0 | 100 | 230 | 67 of 132 |
| y5 | re-run | 135 | 2 | 0 | 10 | 0 | 2 | 130 | 279 | 77 of 132 |
| x5 | first run | 444 | 1 | 0 | 11 | 13 | 0 | 424 | 893 | 160 of 179 |
| x5 | revised checker | 444 | 1 | 1 | 11 | 9 | 0 | 424 | 890 | 160 of 179 |
| x5b | first run | 461 | 3 | 0 | 12 | 0 | 0 | 441 | 917 | 163 of 179 |
| x5b | revised checker | 461 | 3 | 1 | 12 | 0 | 0 | 441 | 918 | 163 of 179 |
| y1 | re-run | 479 | 5 | 1 | 12 | 0 | 0 | 451 | 948 | 169 of 179 |
| x6 | first run | 437 | 5 | 0 | 8 | 13 | 0 | 415 | 878 | 159 of 179 |
| x6 | revised checker | 437 | 5 | 1 | 8 | 9 | 0 | 415 | 875 | 159 of 179 |
| y3 | re-run | 356 | 3 | 2 | 9 | 0 | 0 | 344 | 714 | 153 of 179 |

WARNINGs (not counted above): SP-3 x1 11, x2 2, x5 2, x5b 2, x6 2, y1 3, y2 1, y3 2, y4 1, y5 3; SP-8 x5 4, x6 4
(revised checker).

What changed, and why:

- **Checker revision.** SP-9 "wound" masking removed all 7 SP-9 ERRORs on x1. SP-8 moved 4 of x5's and x6's 13
  shared-cost decisions to WARNING (a shared real cost); 9 remain ERRORs because every option is costed "none". x4's
  13 SP-8 ERRORs are all "none" decisions and stay. SP-4 now fires on x1 (`cm_letter_read`, the lamp code), x5, x5b and
  x6 (the public plant at `n04d0`) and x4 (four nodes, `dot_mallow`; see the SP-4 section). No SP-2, SP-3, SP-6 or
  SP-A count changed on any first-run plan.
- **New extractions.** SP-8 is 0 on every re-run plan: the v2 convention ("gives up the other two routes") produced
  costs that differ per option. SP-3 rose on y4 (8 against 2) and y1 (5 against 1) and fell on y3 (3 against 5); the
  v2 instruction to record negations and states at the asserting passage plausibly adds contradicting pairs, but this
  run does not establish the cause. SP-2 and SP-A remain the bulk and still double-count (`AL-820`, untouched by the
  revision). y5 has two SP-9 ERRORs that no first-run plan had (see "Other observations").

## False alarms on the four revised books (post WP-0.4)

Revised checker, current books and plans, no `--assertions`. The books and plans are the same commits as in the first
run; only the checker changed. ERRORs fell from 11 to 1: the two SP-4 findings on endings are exempt (`AL-818`), three
of the four SP-8 findings are now WARNINGs (shared real cost, `AL-819`), and the five "wound" SP-9 findings are masked
(`AL-811`).

The judgement below is PROPOSED. Under D5 the judgement of "wrong" is the owner's. Whatever it is, no book can exceed
the one-wrong-ERROR budget, because no book has more than one ERROR.

| Book | Rule | Node | Checker's claim | What the book and route show | Proposed judgement |
| --- | --- | --- | --- | --- | --- |
| Sky-Ship Stowaway | SP-8 ERROR | `b_tell1` | offers `c_tell_crew`, `c_tell_captain`, `c_tell_reveal` and none costs anything ("none") in 6 states (`told_bosun=true`): no trade-off separates the options | The plan costs all three "none" (it predates the v2 convention). In the book all three lead to a winning outcome: `b_tell_crew` (the bosun vouches for her) to `e_win_crew`; `b_tell_captain` to a further choice between `e_win_captain` ("not safe or dry") and `e_neu_home`; `b_tell_reveal` (the crew see the calf) to `e_win_discovery`. With `told_bosun=false` the "tell the crew" option is the cold variant costed "may be laughed at" | unclear: the claim is accurate, and under the revised rule's stated purpose (no option gives anything up) it is arguably right; whether three costless good outcomes is a defect is a design call. Same judgement as the first run |

| Book | ERRORs, first run | ERRORs, re-run | Proposed wrong |
| --- | ---: | ---: | --- |
| Hollow Lighthouse | 6 (SP-4 1, SP-9 5) | 0 | 0 |
| Sky-Ship Stowaway | 1 (SP-8 1) | 1 (SP-8 1) | 0 (1 unclear) |
| Midnight Museum | 3 (SP-4 1, SP-8 2) | 0 | 0 |
| Signal in the Static | 1 (SP-8 1) | 0 | 0 |

### WARNINGs on the false-alarm set (not counted against the budget)

| Book | Rule | Node | Claim | Note |
| --- | --- | --- | --- | --- |
| Hollow Lighthouse | SP-3 | `a_desk_pick` | `has_key` (at the five key sites) and `mira_lacks_lamp_key` (at `cm_light_back`, `e_set_gears`) sit only on routes no single reading crosses | Consistent with the B2 fix: in the current book `c_cm_light_relight_2` (to `e_set_gears`) and `c_cm_light_relight_3` (to `cm_light_back`) are offered only with `has_key=false`. A variable-backed possession that differs by route is by design, so this is advisory at most |
| Midnight Museum | SP-8 | `n_start` | `c_start_gems`, `c_start_egypt`, `c_start_archive` share one cost ("leaves the other wings") in 2 states; symmetric opportunity cost | Was an ERROR in the first run (proposed wrong); now the advisory severity the revision intends |
| Midnight Museum | SP-8 | `n_cipher` | three roads share "leaves the other roads" in 8 states | As above |
| Signal in the Static | SP-8 | `m_numbers_1` | two choices share "one long job" in 4 states | As above; the text frames the trade-off ("her eyes will last for one long job tonight") |

## SP-4 false-positive analysis (`AL-825`)

`AL-825` predicted that the widened SP-4 can flag an incidental entity introduced in a planting scene. Every SP-4
finding on the re-run plans:

| Plan | Node | Fact | Thread (declared plant) | Classification | Evidence from the book |
| --- | --- | --- | --- | --- | --- |
| y1 | `n04d0` | `survey_signed_faulks` | `found_author` (`jonah_sought_author`) | answer-key match (KD-OS-PP-B-os-new-1-*) | `n04d0`: "The survey was signed D. Faulks and dated in August", reached unplanted via `n03d2 > c_n03d2_2` |
| y2 | `cm_letter_read` | `code_blinking_keeps_off` | `light_code` (`mira_knows_code`) | plausible real public plant (partial); not in the key | Ferris's letter: "set his own lamp blinking, which in his code means keep off". The unplanted reader can go on `cm_letter_map > cm_cottage`, where "Tell him the light says keep off" is offered only with `knows_code=true`, so a reader who has just read what the blinking means cannot say it. Partial: the letter gives only the "blinking" half; the payoff `cm_cottage_light` also says "Steady, he lands", and the flash payoffs need the three-short call, which the letter does not give. The same finding appears on x1 under the revised checker |
| y3 | `n04d0` | `survey_signed_faulks` | `t_found_author` (`faulks_name_in_ada_book`) | answer-key match (KD-OS-PP-B-os-new-2-*) | `n04d0`: "The survey was signed *D. Faulks* at the bottom of a cover sheet" |
| y3 | `n04d0` | `jonah_learned_author` | `t_found_author` | answer-key match (the same name, recorded as Jonah's knowledge) | Same sentence; the plan's fact is "Jonah has found out for himself that D. Faulks wrote the survey" |

None of the four is the incidental-entity class. That class did appear when the revised checker ran on the first-run
plan x4: four SP-4 ERRORs on `dot_mallow` ("Dot Mallow is the village postmistress who keeps the shop") at
`bs_brackets`, `bs_step`, `bs_carry` and `bs_dot`, Beacon-route nodes reached without the Sheepfold plant. The thread
plants the biscuits; the planting scene `sf_hub` introduces Dot ("the postmistress, Dot Mallow, out walking her
terrier"); `bs_dot` shows her shop ("Dot Mallow could find a use for anything in it"); a payoff passage
(`cq_payoff_did_start_sheepfold_turn_site2`) names her. That is exactly the `AL-825` pattern, and in a plan scored for
false alarms it would cost four wrong ERRORs.

It did not fire on y5, a plan for the same book, because of how y5 recorded the entity, not because of the checker:
in y5 the Beacon-route node `bs_dot` and the choices "Ask Dot Mallow what the shop has" require `dot_mallow` rather
than establish it, so the same text yields SP-2 and SP-A findings (six of each on `dot_mallow`, at those nodes and at
`oil_bench` and `pp_shop`) and no SP-4. The
class is therefore live in the revised checker and was avoided in this re-run by an extraction choice. It was not
exercised on the false-alarm set (no SP-4 finding there).

## Other observations (not pre-registered)

- **A new SP-9 homograph.** y5's two SP-9 ERRORs are the extractor's own plan strings matched against the `lethal`
  bundle: `oil_wick` "Old wicks die after twenty minutes" and `oil_relight` "relighting dead lanterns". This is the
  same class as "wound" (a homograph in a non-violent sense), which the revision masked for "wound" only. It does not
  touch the verdict (y5 is not in the false-alarm set), but a hand-written plan with these words would carry ERRORs a
  human would judge wrong.
- **One SP-4 finding per node and fact.** SP-4 reports the public plant once at `n04d0`, while the key has one entry
  per payoff site. Scoring both entries from one finding follows the key's shared trigger and `other_nodes`; a reader
  of the checker output alone would not see that two payoffs are affected.
- **SP-1 never fired.** The `AL-821` change (SP-1 no longer switches off SP-2 to SP-8) was not exercised on any plan
  in this run.
- **Extraction time.** 302 minutes for five plans (12 to 75), against 430 minutes for the corresponding first-run plans
  (x1 75, x2 80, x4 30, x5 150, x6 95). y3's 12 minutes is the agent's own estimate, flagged by it as likely too short.

## Disclosure

- **Who designed the revision.** The one revision (`a671309`) and the v2 extraction prompt (`01521fa`) were designed
  by an agent that had read the answer key and the first-run report. The plan's G1 revision note states that each
  change is justified by the rule's purpose in ADR-033 and names no book, node, fact or answer-key entry; that holds
  for the code, but the choice of which rules to change was made knowing which entries had been missed and why.
- **The public-plant result was known to be reachable before the re-run.** `AL-825` records that the revised SP-4,
  run on the first-run blind plans, reported the Orchard public plant on x5, x5b and x6. This report confirms it
  (`rerun/runs/first-run-plans-revised-checker/`). The public-plant row passes because of the checker change; the
  re-extractions again declared the private half of the thread as its `plant` (y1 `jonah_sought_author`, y3
  `faulks_name_in_ada_book`), so the extraction did not contribute to that row.
- **The negation instruction and B2.** The v2 instruction to record statements about the hero's possessions,
  knowledge or state, negatives included, at the passage that asserts them (`AL-822`) was written after the first run
  missed B2. Its example phrases were chosen to avoid answer-key wording (`AL-827`: the natural examples, a hero who has
  no key and a hero who does not know a name, match two blockers), and the prompt header records the check by search.
  The y2 extractor recorded `e_set_gears` as asserting `mira_has_no_key` "under the v2 negation instruction"
  (manifest). B2 is found because of that extraction choice: the revised checker on x1 still misses it. The
  re-extraction ran in a rebuilt blind worktree with fresh agents, none of which saw the first-run plans (manifest).
- **SP-9 length change.** The SP-9 length change made before the first run (`29c0ff8`) was ruled by the owner not to
  count as the revision (D5). The SP-9 "wound" masking is part of the revision (`AL-811`) and removes five of the
  first run's eleven false-alarm ERRORs.
- **The false-alarm row moved by checker change alone.** The four books and their plans are the same commits as the
  first run's inputs; all of the reduction from 11 ERRORs to 1 comes from SP-4 (`AL-818`), SP-8 (`AL-819`) and SP-9
  (`AL-811`).

## What the WP-1.5 "If it fails" clause says now

Quoted exactly from `docs/planning/story-plan-implementation-plan.md`, WP-1.5:

> **If it fails.** One revision of the schema or checks, time-boxed to size M, then one re-run on the same frozen
> corpus. If it fails again: stop. ADR-033 is withdrawn or narrowed; Phase 2 does not start; the fallback is the
> WP-0.4 second read as the standing continuity control for catalog books, plus the beat and label lint (`UW-C496`,
> `UW-C497`) on the shells in use. The report says so plainly.

This is the one re-run. The revision has been taken and there is no further one. Had this run failed, ADR-033 would be
withdrawn or narrowed and Phase 2 would not start. As scored it passes, so the clause is not triggered; the verdict
and its acceptance are the owner's under D5.

## Summary

Scored against the unchanged pre-registered criterion and the frozen answer key, the G1 re-run passes. All six
exact-class entries were found (the four public-plant entries, the cross-payoff reference and the two backstories),
all three Run B leaks were found, and two of the three Lighthouse blockers (B2 and B3) were found; B1 was missed
because neither extraction recorded Ferris's spoken warning as a fact separate from the bog the map shows. On the
four revised books the revised checker reports one ERROR in all (an SP-8 finding on the Sky-Ship's three costless
winning choices, proposed "unclear"), so no book can exceed the budget. The two halves of the pass have different
sources: the public plant and the false-alarm reduction come from the checker revision, which also produces them on
the first-run plans; B2 comes from the v2 extraction's negation instruction, which the first-run plan lacked. Both
were designed by an agent that had read the answer key, which the owner should weigh when deciding D5; the widened
SP-4's incidental-entity false positive (`AL-825`) and a new SP-9 homograph ("die", "dead") remain live but did not
affect any scored row.
