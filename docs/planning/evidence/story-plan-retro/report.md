# Story Plan retrospective gate G1: WP-1.5 report

Date: 2026-11-21. Work package: WP-1.5 of `docs/planning/story-plan-implementation-plan.md`. Gate: G1. Owner
decision that consumes this report: D5 ("Accept the G1 verdict").

This run measures. It changes no plan, assertion file, answer key, checker or book. (Written to the repo by the
orchestrator from the run agent's report text, verbatim, because the harness refused the agent's own write of this
file; see `AL-807`.)

## Inputs and commits

| Input | Location | Commit |
| --- | --- | --- |
| Pass criterion (pre-registered) | `docs/planning/story-plan-implementation-plan.md`, WP-1.5 | WP-1.5 text last changed in `87dc088`, before the answer key and WP-1.4 |
| Answer key, 17 entries, `frozen: true` | `known-defects.json` (sha256 `6f5ded17bf66...`) | `8dbeba7` (before the extraction prompt `c8ad50e`) |
| Blind extraction prompt | `plans/EXTRACTION-PROMPT.md` | `c8ad50e` |
| Blind plans, assertion maps, manifest | `plans/x*.plan.json`, `assertions/x*.json`, `plans/manifest.json` | `27066c5` |
| Checker | `src/cyo_adventure/storyplan/checks.py`, `scripts/check_story_plan.py` | `29c0ff8`, `37a579a` (worktree HEAD `27066c5`) |
| False-alarm books and plans (post WP-0.4) | `out/<slug>.filled.json`, `out/<slug>.plan.json` | lighthouse `3e29e04` / `b016455`; sky-ship `e9adcd1` / `600536d`; museum `a0b61e9` / `600536d`; signal `38f6a5a` / `b016455` |

Runtime: Python 3.14.6 under `uv run`. Raw outputs committed beside this report:

- `runs/<id>.json`: the ten blind runs, `check_story_plan.py <book> <plan> --json --assertions <map>`.
- `runs/false-alarm/current/<slug>.json`: the four post-fix books, current checker.
- `runs/false-alarm/pre-29c0ff8/<slug>.json`: the same four, checker as of `29c0ff8^` (disclosure section).

### Staging and binding

Each blind input was recreated into `tmp_cleanup/wp15/<id>.book.json` (`git show <rev>:<path>` for `git:` revisions,
a copy of the run file otherwise). All ten sha256 values equal the manifest. SP-0 reported nothing on any run: it
checks `provenance.book_sha256` and the shape hash, both of which matched; `provenance.book_file`
(`tmp_cleanup/blind/<id>.book.json`, the extractor's staging path) is echoed in the output but not compared, so the
staging path difference is not a finding. The checker did not crash on any input; every run exited 1 (ERROR
findings present). Two runs (x1, x5) were repeated and were byte-identical.

## Verdict

| Criterion (pre-registered, quoted in short) | Result | Verdict | Evidence |
| --- | --- | --- | --- |
| Exact class: the public plant (SP-4), 100 percent | 0 of 4 entries | FAIL | SP-4 reported nothing on x5, x5b or x6. Each blind plan named "Jonah wrote the name down" as the thread's `plant` and recorded "the survey is signed D. Faulks" as a separate fact; `n04d0` establishes the second, so SP-4 had nothing to see |
| Exact class: the cross-payoff reference (SP-6), 100 percent | 1 of 1 | PASS | x4: SP-6 at `cq_payoff_did_start_beacon_steps` on `arthur_tremlett` and `arthur_at_gate`, witness route equal to the answer key's |
| Exact class: the two backstories (SP-3), 100 percent | 1 of 1 | PASS | x2: SP-3 ERROR "one reading meets both" `ferris_built_rig` (`cm_light`) and `ferris_light_unexplained` (`jr_light`, `jr_light_read`) |
| Assertion class: all three Run B leaks found | 3 of 3 | PASS | OVENS (x4, SP-A/SP-2 `biscuits_given`), O1-E05 (x5 and x5b, SP-A/SP-2 on the photo and the copied words), BEACON (x4, SP-A/SP-2 and SP-6) |
| Assertion class: at least two of B1 to B3, with a reason for any miss | 1 of 3 as scored (B3); B1 is a judgement call; B2 missed | NEEDS OWNER JUDGEMENT (scored FAIL) | Counting B1 would make it 2 of 3. Reasons below |
| False alarms: on the four revised books after WP-0.4, no more than one ERROR per book a human judges wrong | 11 ERRORs; proposed wrong: lighthouse 6, museum 3, signal 1, sky-ship 0 (1 unclear) | FAIL on proposed judgements (the judgement is the owner's, D5) | Lighthouse fails whatever SP-4 is judged: five SP-9 ERRORs are the word "wound" (clockwork) matched as graphic, already recorded as a false positive in `AL-811` and in the plan's own SP-9 note before this run |
| **G1 overall** | | **FAIL as scored** | The public-plant row fails on a mechanical count that involves no judgement |

## Per-entry scoring (all 17 answer-key entries)

"Found" means a finding at the entry's node (or a node in `other_nodes`) on the entry's fact, in a witness state
consistent with the entry's trigger. A finding at the right node on an unrelated fact is not counted.

| Entry | Gating? | Plan | Finding(s) matched: rule, node, fact, witness | Scored | Notes |
| --- | --- | --- | --- | --- | --- |
| KD-LH-B1 | yes (Lighthouse blocker) | x1 | Only SP-2 and SP-A at `e_win_keeper_word` on `ferris_alive_on_moor` ("Ferris is alive and living in the cottage on the moor"), 14 of 14 states, witness route exactly B1's (`cm_letter_read > c_cm_letter_read_1 > cm_letter_map > c_cm_letter_map_2`) | missed (judgement call) | Right node and right route, wrong fact. The defect is Ferris's earlier spoken warning about the bog; the plan has no fact for it. Its `bog_by_second_gate` is established by `cm_letter_map` (the map's "mind this"), so it is guaranteed on B1's route. The flagged fact is a near-duplicate of `ferris_alive` plus `ferris_cottage`, which this route does establish (the letter, the map); the finding is an artefact of that duplication that happens to land on B1. A reader sent to the node by it would probably find the line, which is why this is a judgement call |
| KD-LH-B2 | yes (Lighthouse blocker) | x1 | None at `e_set_gears`. At `cm_light_relight`, SP-A on `mira_has_key` in `has_key=false` states | missed | The SP-A finding is the opposite polarity: the extractor recorded `cm_light_relight` as asserting she has the key (from the conditional label), and the checker flags readers without it. B2 is the reverse: with `has_key=true`, `e_set_gears` says she has no key. The plan's `mira_lacks_key` (contradicting `mira_has_key`) is established only at `cm_light_back`, not at `e_set_gears`, so SP-3 had no contradicting pair on this route (it reports `mira_has_key` against `mira_lacks_key` only as a cross-route WARNING) |
| KD-LH-B3 | yes (Lighthouse blocker) | x1 | Name half: SP-3 ERROR at `e_win_harbor`, choice `c_cm_smug_photo_2`, `mira_knows_no_name` against `smuggler_is_varley` (at `jr_smug_names`), one reading meets both. Boat half: SP-2 and SP-A at `e_win_harbor` on `grey_boat_man`, 14 of 14 states, route via `cm_smug > cm_smug_photo` | found (both halves) | |
| KD-LH-B3-follow | no (sibling) | x1 | SP-2 and SP-A at `cm_smug_follow` on `grey_boat_man`, 14 of 14 states | found | |
| KD-LH-B3-honest | no (sibling) | x1 | SP-2 and SP-A at `e_neutral_honest` on `grey_boat_man` | found | The plan does not let `cm_smug_follow`'s assertion establish the boat, so both nodes are flagged, as the key predicted for such a plan |
| KD-LH-S1 | no | x1 | None at `e_win_promise` | missed | The ending establishes `ferris_alive_on_moor` itself; "where Ferris lives" (`ferris_cottage`, from the map) is not in its assertion list. Entry is marked weak in the key |
| KD-LH-S2 | no | x1 | None | missed (expected) | Repeated reveal; the key records that no SP rule covers it |
| KD-LH-S3 | no | x1 | At `n_chamber` only `great_lamp_dark` (SP-2, SP-A) | missed | The store half is the key's assertion; `n_chamber`'s assertion list omits the store, and the plan has no "Mira has been in the store" fact. The lamp-related finding is the half the key marks weak and is about a dark lamp, not "two lamps over her head" |
| KD-LH-S4 | no | x1 | None at `e_set_a_drawer` | missed | The plan has no kitchen fact |
| KD-LH-BS1 | yes (exact, SP-3) | x2 | SP-3 ERROR at `cm_light` (via `c_n_chamber_3`), `ferris_built_rig` against `ferris_light_unexplained` (`jr_light`, `jr_light_read`), one reading meets both | found | Matches claim set A (`jr_light`) against claim set B (`cm_light`). x2 also has an unrelated SP-3 ERROR (`inner_door_ajar` against `inner_door_locked`) not in the key |
| KD-RB-L2-OVENS | yes (Run B leak) | x4 | SP-A and SP-2 at `fn_ovens` on `biscuits_given`, witness `did_start_sheepfold_turn=false`, route identical to the key's first witness; also `ovens_said_yes_before` (3 of 6 states), the key's "second time" extension | found | `biscuits_given` fails in 6 of 6 states, planted ones included, because the plan establishes it only at a payoff site; the finding is broader than the defect but names it |
| KD-RB-O1-E05 | yes (Run B leak) | x5, x5b | x5: SP-A and SP-2 at `e05_0` on `jonah_photo_notice` (1 of 2 states, `did_go_down_read=false`) and `eleven_words_copied`. x5b: `jonah_photographed_notice`, `jonah_copied_eleven_words`, `eleven_words`. Both on the key's witness route (`n03d0 > c_n03d0_2 > n04d2 > c_n04d2_0`) | found (both plans) | Both plans also flag the three-fact extension the key added |
| KD-RB-L2-BEACON | yes (exact SP-6 and Run B leak) | x4 | SP-6 at `cq_payoff_did_start_beacon_steps` on `arthur_tremlett` and `arthur_at_gate` (2 of 2 states); SP-2 and SP-A on the same facts; route identical to the key's | found | |
| KD-OS-PP-B-os-new-1-n11d1 | yes (exact, SP-4) | x5, x5b | No SP-4 finding. Related: SP-2 (choice `c_n04d2_2`) and SP-A at `n04d2` on `faulks_wrote_survey` / `survey_signed_faulks`, `did_find_who_wrote=false` | missed | The related finding is the label half of the key's trigger ("Find out what Faulks actually looked at" shown unplanted), reported as an unestablished fact, not as a public plant. It does not cover `n04d0` showing the signature, which is the SP-4 defect |
| KD-OS-PP-B-os-new-1-n11d5 | yes (exact, SP-4) | x5, x5b | No SP-4 finding. Related: SP-6 and SP-2 at `cq_payoff_did_find_who_wrote` on `faulks_pattern`; the same `n04d2` label finding | missed | The SP-6 finding matches the key's reader judgement ("unearned: the surveyor's other work, the pattern of reports") but not the public-plant class the key scores |
| KD-OS-PP-B-os-new-2-n11d1 | yes (exact, SP-4) | x6 | No SP-4 finding. Related: the `n04d2` label finding on `faulks_wrote_survey` | missed | As above |
| KD-OS-PP-B-os-new-2-n11d5 | yes (exact, SP-4) | x6 | No SP-4 finding. Related: the `n04d2` label finding | missed | As above |

Tally: exact classes 2 of 6 entries (public plant 0 of 4, cross-payoff 1 of 1, two backstories 1 of 1). Run B leaks 3
of 3. Lighthouse blockers 1 of 3 (2 of 3 if B1 is counted). Non-gating: B3-follow and B3-honest found; S1 to S4
missed (S2 by design).

### Why the public plant was missed in all three plans

The thread `did_find_who_wrote` in the book plants two things at once: the name D. Faulks, and Jonah writing it down.
All three plans (x5, x5b, x6, written by two independent agents) put the act of writing it down in the thread's
`plant` and the name in an ordinary fact (`faulks_wrote_survey`, `survey_signed_faulks`). The act of writing is
exclusive to the planting route, so SP-4, which compares only the declared `plant` fact, is correctly silent. The
payoffs in the book recall the name, which is public. SP-4's power therefore rests on the extractor choosing the
public half as the plant, which nothing in the schema or the prompt forces.

### Reasons for the Lighthouse blocker misses

- **B2 (state contradiction).** The plan never says, at `e_set_gears`, that Mira lacks a key; `e_set_gears`
  establishes `lamp_needs_key` and `tower_key`, which do not contradict `mira_has_key`. With no contradicting fact on
  that node, SP-3 cannot fire, and SP-2 and SP-A ask only whether asserted facts are guaranteed, not whether they
  conflict with the state.
- **B1 (unestablished fact).** The prior warning is not a fact in the plan; the closest fact (`bog_by_second_gate`)
  is established on B1's route by the map. See the table row for the near-miss.

## False alarms on the four revised books (post WP-0.4)

Current checker, current books and plans (no `--assertions`, since these plans have no assertion maps). Counts match
the expected 6, 1, 3, 1.

The judgements below are PROPOSED. Under D5 the judgement of "wrong" is the owner's.

| Book | Rule | Node / field | Checker's claim | What the book and route show | Proposed judgement |
| --- | --- | --- | --- | --- | --- |
| Hollow Lighthouse | SP-4 | `e_win_keeper_found` | establishes `lamp_code`, the plant of `t_code`, on a route skipping every planting choice (`knows_code=false`) | An ending. Ferris tells Mira the code ("steady, he lands, and blinking, he keeps off") as part of the reveal. Nothing follows an ending, so no payoff can be reached with the public plant | wrong |
| Hollow Lighthouse | SP-9 | `facts.little_lamp_rig.text` | matches a band-mandatory denylist term (bundle `graphic`) | Term matched is "wound" in "a clockwork shutter, wound and filled tonight" | wrong |
| Hollow Lighthouse | SP-9 | `nodes.n_light.event` | same | "wound tonight" (clockwork) | wrong |
| Hollow Lighthouse | SP-9 | `nodes.e_set_c_stuck.event` | same | "wound clockwork in the rock" | wrong |
| Hollow Lighthouse | SP-9 | `nodes.e_win_signal.event` | same | "the spring freshly wound" | wrong |
| Hollow Lighthouse | SP-9 | `endings.e_set_c_stuck.gift` | same | "clockwork wound since sundown" | wrong |
| Sky-Ship Stowaway | SP-8 | `b_tell1` | offers `c_tell_crew`, `c_tell_captain`, `c_tell_reveal` at one cost ("none") in 6 states (`told_bosun=true`) | All three lead to a winning scene (`b_tell_crew` to `e_win_crew`; `b_tell_captain` to `e_win_captain` or `e_neu_home`; `b_tell_reveal` to `e_win_discovery`); none costs anything in text or plan. With `told_bosun=false` the cold option costs "may be laughed at" | unclear: the claim is accurate; whether a costless choice among good outcomes is a defect is a design call |
| Midnight Museum | SP-4 | `e_set_locked_gallery` | establishes `map_back_warning`, the plant of `t_back`, on an unplanted route | A setback ending whose gift is reading the map's back for the first time. The WP-0.4 reader recorded this exact finding as intended ("That ending is the reveal (its `gift`), so this is intended") | wrong |
| Midnight Museum | SP-8 | `n_start` | `c_start_gems`, `c_start_egypt`, `c_start_archive` at one cost ("leaves the other wings") | The opening three-wing hub; each wing costs the other two. No option is a right answer, which is the defect SP-8 names in ADR-033 ("forks with one right answer") | wrong |
| Midnight Museum | SP-8 | `n_cipher` | `c_cipher_stars`, `c_cipher_map`, `c_cipher_clock` at one cost ("leaves the other roads") | The note itself offers "one of my three roads"; each road leads to its own two-choice scene | wrong |
| Signal in the Static | SP-8 | `m_numbers_1` | two choices at one cost ("one long job") | The text frames the trade-off ("her eyes will last for one long job tonight"): cipher or timing, each with its own sub-branches | wrong |

Per book, proposed wrong ERRORs: lighthouse 6 (5 if the SP-4 is judged right), sky-ship 0 (1 unclear), museum 3 (1
if both SP-8 are judged right), signal 1. The budget is one per book, so the lighthouse exceeds it under any
judgement of its SP-4, and the museum exceeds it unless both SP-8 findings are judged right. Three patterns account
for all 11: the five "wound" homographs, SP-4 firing on an ending that is itself the reveal (2), and SP-8 on a
choice whose options share one cost (4; 3 of them symmetric opportunity costs).

## Disclosure: SP-9 changed after it was observed failing on these plans

SP-9's length rule was changed on 2026-11-21 in commit `29c0ff8` (per-field caps of 120, 240 and 600 characters
replacing a flat 120) after it was observed failing on the seven hand-written family-test plans and before this run.
The plans' own over-cap strings were then condensed in commit `b016455` (lighthouse and signal among the four books
here). Both commits precede the WP-1.4 extraction prompt (`c8ad50e`). `29c0ff8` touched only
`src/cyo_adventure/storyplan/checks.py` among checker code, so the "before" run below used a scratch copy of the
package with that one file replaced by `git show 29c0ff8^:src/cyo_adventure/storyplan/checks.py`; the live checker
was not changed.

ERROR counts on the false-alarm set:

| Book | Current checker, current plans | Pre-`29c0ff8` checker, current plans | Pre-`29c0ff8` checker, pre-`b016455` plans | Current checker, pre-`b016455` plans |
| --- | ---: | ---: | ---: | ---: |
| Hollow Lighthouse | 6 (SP-4 1, SP-9 5) | 24 (SP-4 1, SP-9 23: 18 length, 5 "wound") | 25 (SP-9 24: 19 length) | 7 (1 length) |
| Sky-Ship Stowaway | 1 (SP-8 1) | 8 (SP-8 1, SP-9 7 length) | 8 | 1 |
| Midnight Museum | 3 (SP-4 1, SP-8 2) | 19 (SP-4 1, SP-8 2, SP-9 16 length) | 19 | 3 |
| Signal in the Static | 1 (SP-8 1) | 17 (SP-8 1, SP-9 16 length) | 20 (SP-9 19 length) | 4 (3 length) |

Under the pre-change rule every one of the four books carries more than one ERROR (the length findings) that the
change was made to remove, so the false-alarm criterion would fail on all four books instead of on one or two.

On the blind plans the change removed only length findings: x1 5, x2 8, x3 15, x4 23, x5 10, x5b 21, x6 8, x7 6, x8
43, x9 38. No other rule's counts changed.

Whether the length change counts as the WP-1.5 "one revision of the schema or checks" is for the owner to decide
(D5). This report does not decide it. The five "wound" findings were also known before this run: the plan's own SP-9
note counts "five uses of 'wound' for clockwork", and `AL-811` (open) records the "wound" denylist as a false positive
on the hand-written plans and proposes recalibrating it "as part of WP-1.5"; no recalibration was made, so they count
here.

## Agreement: x5 against x5b (WP-1.4 measure)

Two extractions of one book (`B-os-new-1`, 179 nodes), by different agents (x5: 150 minutes, 166 facts; x5b: 80
minutes, 228 facts).

| Measure | x5 | x5b |
| --- | --- | --- |
| Answer-key entries detected | KD-RB-O1-E05 | KD-RB-O1-E05 |
| Public-plant entries (SP-4) | 0 of 2 | 0 of 2 |
| Same related findings | `n04d2` label (SP-2/SP-A); SP-6 `faulks_pattern` at `cq_payoff_did_find_who_wrote` | the same two |
| Nodes with at least one ERROR | 160 | 163 |
| ERROR count | 893 | 917 |

Nodes with at least one ERROR: intersection 157, union 166, Jaccard 0.946. That figure is mostly base rate: with 160
and 163 of 179 nodes flagged, independent flagging would give an expected Jaccard of about 0.82 (expected
intersection 145.7). Thirteen nodes are clean in both. Only in x5: `e18_1`, `n04c2`, `n10c6`. Only in x5b: `n00c0`,
`n05d2`, `n06c1`, `n06c2`, `n06c4`, `n12c0`.

| Rule | x5 ERRORs | x5b ERRORs | Nodes x5 / x5b / both |
| --- | ---: | ---: | --- |
| SP-2 | 444 | 461 | 160 / 163 / 157 |
| SP-3 | 1 | 3 | 1 / 2 / 1 |
| SP-6 | 11 | 12 | 8 / 9 / 8 |
| SP-8 | 13 | 0 | 13 / 0 / 0 |
| SP-A | 424 | 441 | 160 / 162 / 156 |

Qualitative note. On the structural rules the two agree closely where the plan structure is fixed by the book: SP-6
names the same payoff sites and, allowing for different fact ids, largely the same facts (Abara, the Faulks name, the
data request, the four visits, Halvor, Tobe); both find the same SP-3 contradiction at `e18_3` (Ada still writing
against the record having stopped), and x5b finds two more. They disagree completely on SP-8, and only because of
authoring style: x5 wrote cost "none" on 152 of 346 choices, x5b on 34. They agree on the miss that decides G1: both
chose the private half of the surveyor-name thread as its plant. SP-2 and SP-A agreement is high but uninformative
at this flag rate.

## Extraction time and blindness deviations (from the manifest)

| Id | Book | Model | Minutes | Deviation or caveat recorded |
| --- | --- | --- | ---: | --- |
| x1 | Hollow Lighthouse, pre-fix revised | opus | 75 | none |
| x2 | Hollow Lighthouse, original fill | opus | 80 | none |
| x3 | Lantern Keepers' List, `B-lkl-new-1` | opus | 50 | intent/cost table shared with x4 (same agent, same graph) |
| x4 | Lantern Keepers' List, `B-lkl-new-2` | opus | 30 | same agent as x3; cost table reused |
| x5 | October Blossom, `B-os-new-1` | opus | 150 | ran `ls` on output folders, which listed other agents' output file names (not opened) |
| x5b | October Blossom, second extraction | opus | 80 | separate agent |
| x6 | Orchard Signal, `B-os-new-2` | opus | 95 | same agent as x5; cost table reused with 19 costs rewritten; same `ls` deviation |
| x7 | Sky-Ship Stowaway, pre-fix revised | sonnet | 75 | routes traced by hand; most costs "none" |
| x8 | Signal in the Static, pre-fix revised | sonnet | 75 | no StoryEngine |
| x9 | Midnight Museum, pre-fix revised | sonnet | 95 | no StoryEngine; assertion map generated from the plan's `requires`/`establishes`, not a separate prose pass |

Total 805 minutes for ten plans (30 to 150 per book, median 77.5).

## Supplementary (not pre-registered)

### x7, x8, x9 against their WP-0.4 findings files

Pre-fix revised books, scored against the blockers and should-fix items in `findings-<slug>.md`. "Found" uses the
same rule as above. These books are not in the frozen key.

| Book (plan) | Blockers found | Should-fix found | Notes |
| --- | --- | --- | --- |
| Sky-Ship (x7) | 0 of 2 (F3, F8 missed) | 1 of 2 (F2: SP-A at `e_neu_kite` on `nimbus_fin_strapped`, `fin_free=false`) | SP-1 failed (`threads.ropes_learned.planting_choices` lists `c_rig_b`, which does not set `knows_ropes`; `c_rig_b_go` does), so SP-2 to SP-8 were skipped and only SP-A ran |
| Signal (x8) | 3 of 5 (B1 and B2: SP-2/SP-A `spring_tide_high_2342` at `f_he_act`, `e_he_safe`; B4: `wren_has_grandpa_logbook` at `m_numbers_1`, `m_num_cipher`). Missed B3 (timeline), B5 (age) | 1 of 9 (S9: SP-3 ERROR `marin_cannot_hear_loop` at `mm_list_daughter` against `marin_has_been_listening`) | Judgement calls not counted: S4 (`grandpa_tide_table` flagged at `mm_count_1` as unestablished; the defect is a second, inconsistent tide table) and S8 (the same contradiction as S9, at `n_b3_choice`, not named) |
| Museum (x9) | 0 of 1 (F2, the one-minute floor, missed) | 4 of 7 (F4 `garden_gate` at `e_neutral_evidence`, `v_share_secret`; F6 `guard_hums` at `n_rotunda`, `ro_pym`; F7 `arch_29` at `e_win_lost_wing`; F16 `reading_table_landing`/`reading_table_lamp` at `k_display_careful`). Missed F1 (cipher), F3 (times), F5 (slab) | Also hit minor F9 (`letter_addressed_finder` at `v_share`) and F11 (SP-3 `east_wing_thought_gone` against `east_wing_bricked_in`) |

Recall: blockers 3 of 8 (0 of 2, 3 of 5, 0 of 1); should-fix 6 of 18 (1 of 2, 1 of 9, 4 of 7). The misses cluster in
three kinds the fact model does not express: timelines (signal B3, museum F3), physical state or location (sky-ship
F3, museum F2 and F5), and one detail held two ways across routes with no `contradicts` marked (museum F1).

### x3, the negative control

`B-lkl-new-1` has no answer-key entries. It is not verified clean; it is simply not in the key. ERRORs by rule: SP-2
103, SP-A 97, SP-8 13, SP-6 5, SP-3 2 (220 in all; 61 of 132 nodes). Spot checks:

- SP-6 `wind_across` at `cq_payoff_did_start_beacon_steps`: "Wren remembered the wind test from earlier: how it came
  across, not up," on a route that never visits `bs_test`, where the result is shown (`bs_hub` only sets the lantern
  out). Looks like a real defect of the cross-payoff kind; unverified.
- SP-2 `shoulder` at `fn_taper` ("the dark part of the shoulder", the ridge's shoulder unintroduced on the Beacon
  route): real but trivial.
- SP-2 `ovens_quad` at `pp_quad`: the node's own text introduces the quad bike, so the plan should have it establish,
  not require, the fact. Extraction noise.
- SP-8 (13): every one is a decision whose choices all carry cost "none" (136 of 314 choices in the shared x3/x4
  table). Extraction noise.

## Noise characterisation

ERRORs per blind plan, by rule (current checker):

| Plan | SP-1 | SP-2 | SP-3 | SP-4 | SP-6 | SP-8 | SP-9 | SP-A | Total | Nodes with an ERROR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| x1 | 0 | 10 | 1 | 0 | 1 | 0 | 7 | 20 | 39 | 19 of 162 |
| x2 | 0 | 24 | 2 | 0 | 0 | 0 | 0 | 25 | 51 | 24 of 149 |
| x3 | 0 | 103 | 2 | 0 | 5 | 13 | 0 | 97 | 220 | 61 of 132 |
| x4 | 0 | 105 | 1 | 0 | 7 | 13 | 0 | 100 | 226 | 63 of 132 |
| x5 | 0 | 444 | 1 | 0 | 11 | 13 | 0 | 424 | 893 | 160 of 179 |
| x5b | 0 | 461 | 3 | 0 | 12 | 0 | 0 | 441 | 917 | 163 of 179 |
| x6 | 0 | 437 | 5 | 0 | 8 | 13 | 0 | 415 | 878 | 159 of 179 |
| x7 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 9 | 6 of 123 (SP-2 to SP-8 skipped) |
| x8 | 0 | 15 | 2 | 0 | 0 | 1 | 0 | 26 | 44 | 23 of 139 |
| x9 | 0 | 34 | 4 | 1 | 0 | 15 | 0 | 40 | 94 | 45 of 108 |

SP-3 WARNINGs (not counted above): x1 11, x2 2, x5 2, x5b 2, x6 2, x8 1.

- **SP-2 and SP-A dominate, and they double-count.** Assertion maps include each node's `requires` (x9's was
  generated from them), so nearly every SP-2 finding has an SP-A twin. Findings are deduplicated per `(rule, node,
  fact)`, so one fact missing on a route yields a finding at every later node that needs it: in x5, `tobe` alone
  accounts for 24 SP-2 findings and `faulks_wrote_survey` for 23.
- **On the Run B books much of the volume is extraction placement, some is real.** Spot checks in x5: `tobe` at
  `n11d1` is established in the plan only at `n05d5`, while the book uses Tobe at `n07d0` on the witness route
  without introduction, so the downstream findings are cascade; `abara` at `n07d4` ("Dr Abara was careful on the
  phone") and `six_shelves_1911` at `n03d2` ("Nine hands, six shelves" on a route that never saw the shelves) look
  like real presuppositions in these known-leaky fills.
- **SP-8 is driven by authoring style.** Plans that wrote cost "none" widely (x3, x4: 136 of 314 choices; x5 152,
  x6 156 of 346; x9 99 of 133) produce 13 to 15 SP-8 ERRORs; x5b (34 of 346) produces none on the same book.
- **SP-9 denylist: "wound" (clockwork).** All seven SP-9 ERRORs on x1, and all five on the post-fix lighthouse plan,
  are "wound" in the sense of winding clockwork ("The great lamp cannot be wound or lit", "Somebody wound the light's
  clockwork tonight").
- **SP-4 on endings.** The only SP-4 findings anywhere in this run (x9 blind, museum and lighthouse post-fix) are on
  endings that deliver the plant as the ending's reveal.
- **SP-1 gates everything.** One mislabelled planting choice in x7 turned off SP-2 to SP-8 for that plan.

## What the WP-1.5 "If it fails" clause says happens next

Quoted exactly from `docs/planning/story-plan-implementation-plan.md`, WP-1.5:

> **If it fails.** One revision of the schema or checks, time-boxed to size M, then one re-run on the same frozen
> corpus. If it fails again: stop. ADR-033 is withdrawn or narrowed; Phase 2 does not start; the fallback is the
> WP-0.4 second read as the standing continuity control for catalog books, plus the beat and label lint (`UW-C496`,
> `UW-C497`) on the shells in use. The report says so plainly.

## Summary

Scored against the pre-registered criterion, G1 fails. The cross-payoff reference, the two-backstory contradiction and
all three Run B leaks were found, and so was Lighthouse blocker B3. The public plant was found in none of four
entries: all three blind plans of the two Orchard books made the private half of the surveyor-name thread (Jonah
writing the name down) the thread's plant and the public half (the signed survey) an ordinary fact, so SP-4 had
nothing to compare. Lighthouse B2 was missed because no blind fact said Mira lacks the key at the ending, and B1 was
missed on a strict reading (the finding at its node and route names a different fact), which is a judgement call the
owner may reverse. On the four revised books, 11 ERRORs were reported; on proposed judgements the lighthouse (five
"wound" homographs and an SP-4 on an ending) and the museum (an SP-4 on an ending and two SP-8 findings on symmetric
choices) exceed the one-wrong-per-book budget. SP-9's length rule was changed before this run after failing on these
plans; with the old rule every revised book would have exceeded the budget, and whether that change counts as the one
permitted revision is the owner's decision under D5, as is the verdict itself.
