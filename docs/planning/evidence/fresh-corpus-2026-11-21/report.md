# WP-1.6 fresh-corpus confirmation: scoring report

Date: 2026-11-21. Work package: WP-1.6 of `docs/planning/story-plan-implementation-plan.md` (added under owner
decision D5, condition 2). This run measures. It changes no plan, assertion map, second read, checker or book. (Written to the repo by the orchestrator
from the scoring agent's saved copy, verbatim, because the harness refuses subagent writes of report files; see
`AL-807`.) Method,
the "found" definition and table formats are those of the G1 re-run
[report](../story-plan-retro/rerun/report.md), reused.

## Inputs and commits

| Input | Location | Commit |
| --- | --- | --- |
| Pass criterion (pre-registered) | `docs/planning/story-plan-implementation-plan.md`, WP-1.6 | Added in `862ee6c`; the WP-1.6 section is byte-identical at the scored HEAD (checked by diff) |
| Corpus selection, recorded before any read | `README.md` (this folder) | `471263d` |
| Frozen second reads (the reference truth) | `second-read-the-thornwood-trial.md`, `second-read-the-clockwork-menagerie.md`, `second-read-the-clocktower-cipher.md` | `a99c8df` (Clocktower), `5d5c72c` (the other two) |
| Blind plans, assertion maps, manifest | `plans/z*.plan.json`, `assertions/z*.json`, `manifest.json` | `8f0e3c7` |
| Extraction prompt | `../story-plan-retro/plans/EXTRACTION-PROMPT-v2.md` | `01521fa` |
| Checker (unchanged since the G1 revision) | `src/cyo_adventure/storyplan/checks.py`, `scripts/check_story_plan.py` | `a671309`; no later commit touches either |
| Raw outputs of this run | `runs/z1.json`, `runs/z2.json`, `runs/z3.json` | `33fcdd7` |

Command, per book: `uv run python scripts/check_story_plan.py out/<slug>.filled.json plans/<id>.plan.json --json
--assertions assertions/<id>.json` (paths under this folder abbreviated). Runtime: Python 3.14.6 under `uv run`.

| Id | Book | Band | Nodes | Variables | Book sha256 (equals the README) | Exit | Repeat run |
| --- | --- | --- | ---: | ---: | --- | ---: | --- |
| z1 | The Thornwood Trial | 13-16 | 376 | 0 | `cd3f45ad0d3d...` | 1 | byte-identical |
| z2 | The Clockwork Menagerie | 8-11 | 167 | 0 | `f69e13d99a24...` | 1 | byte-identical |
| z3 | The Clocktower Cipher | 10-13 | 26 | 0 | `2d476787f5e6...` | 1 | byte-identical |

All three sha256 values were recomputed before the run and equal the README. SP-0 reported nothing; the checker did
not crash. Every run exited 1 (ERROR findings present).

## Verdict

| Criterion row (pre-registered, quoted in short) | Result | Verdict | Evidence |
| --- | --- | --- | --- |
| 1. "at least half found across the three books" (covered-class blockers and should-fix) | 23 of 31 (74 percent); 21 of 31 (68 percent) if both judgement calls are scored as misses. Per book: z1 2 of 4, z2 12 of 14, z3 9 of 13 (7 of 13 strict) | PASS | Per-item tables below. Blockers 7 of 8, should-fix 16 of 23 |
| 2. "every exact-class item found" | 1 of 1 (z2 B9, cross-payoff reference) | PASS as counted, on a near-empty class | Found by SP-2 and SP-A at `e_neu_caretaker`, not by SP-6 (no threads exist). Public plant: no item in any book. Two backstories: no blocker or should-fix item (two minor items in z2, both missed, not scored). An empty class is not a pass |
| 3. "no more than one ERROR per book that the owner judges wrong" | z1: 0 ERRORs outside the second read. z3: 0. z2: 73 of 138 ERRORs outside the second read, of which at least 20 are proposed wrong (10 SP-9 homographs, 10 plan-extraction artefacts), in at least four root groups | NEEDS OWNER JUDGEMENT; proposed FAIL on z2 | False-alarm table below. Under every grouping considered, z2 exceeds the budget unless plan-extraction artefacts are not counted as wrong and the SP-9 findings are counted as one |
| **WP-1.6 overall** | | **NEEDS OWNER JUDGEMENT; proposed FAIL** | Rows 1 and 2 pass; row 3 fails on z2 under the proposed judgement. The judgement of "wrong" is the owner's |

## Per-item scoring

"Found" means a checker finding (any SP rule, or SP-A) at the second-read item's node, or one of its other nodes, on
a fact that expresses that item's defect, in a witness state and route consistent with the item's witness. A finding
at the right node on an unrelated fact is not counted. With no variables, every state is "(no variables)", so
consistency is judged by route. Judgement calls are marked.

The scoring set is every blocker and should-fix item in a class the fact model covers (`unestablished_fact_on_route`,
`state_contradiction`, `two_backstories`, `public_plant`, `cross_payoff_reference`). Exact classes are the last three.

### z1, The Thornwood Trial (scoring set 4)

| Item | Severity, class | Finding(s) matched: rule, node, fact, route | Scored | Notes |
| --- | --- | --- | --- | --- |
| B4 | blocker, unestablished | None at `e_ridge2_49` or any of its ten sibling false-mark endings | missed | The plan records `e_ridge2_49` as establishing `false_marks_exist` and the chain as establishing `wren_off_marks`, with no fact "Wren followed a mark" and no `contradicts` pair, so nothing can fire |
| S1 | should-fix, unestablished | SP-2 and SP-A at `e_maze_5_0` on `warden_present_maze`, route `@maze > S(maze,5) > c_b_maze_5_s0` (the item's witness). Also 8 more of the 18 instances: `e_maze3_7`, `e_maze4_8`, `e_ridge_hub1`, `e_ridge_1_0`, `e_ridge5_55`, `e_gate_hub0`, `e_gate4_64`, `e_gate5_65` | found | The grove, warren and council instances are not flagged because the plan lets those hubs establish a present warden |
| S2 | should-fix, unestablished | None on the test-never-staged fact. SP-3 at `h_council` (`council_second_test` against `warren_mercy_test`) is at the item's node but is the numbering defect S4 | missed | No plan fact says a test was staged or passed, so `h_ridge`, `f_name` and `e_win_warden` require nothing missing. An absent event is visible to the fact model only if a later node requires "the test happened" |
| S3 | should-fix, unestablished | SP-2 and SP-A at `e_win_wild` on `wren_showed_beasts_mercy`, route `@dusk > c_f_dusk_1 > c_f_name_2`; SP-2 on the choice `c_f_name_2` at `f_name` (other node) | found | |

### z2, The Clockwork Menagerie (scoring set 14)

| Item | Severity, class | Finding(s) matched: rule, node, fact, route | Scored | Notes |
| --- | --- | --- | --- | --- |
| B5 | blocker, unestablished | SP-2 and SP-A at `av_conv3` on `master_key_card`, `nia_seeks_key`, `key_can_wake_menagerie`, route `AVB > c_av_b4 > c_av_conv > c_av_conv2` | found | |
| B9 | blocker, cross-payoff (exact) | SP-2 and SP-A at `e_neu_caretaker` on `nia_read_journal` and `second_mouse`, route `H > c_hub_dawn > c_dawn_w > c_dawn_w1a` (the item's witness) | found | Found as an unestablished fact; SP-6 cannot fire because the book has no threads |
| S1 | should-fix, unestablished | SP-2 and SP-A at `ds_b3` on `clock_mark_means_heart`, `nia_seeking_heart`, `great_clock`, route `DSB` | found | |
| S2 | should-fix, unestablished | SP-2 and SP-A at `av_b4` on `museum_hum`, route `AVB` | found | |
| S3 | should-fix, unestablished | SP-2 and SP-A at `sv_b4` on `nia_feels_doors_habit` ("as she has learned to"), route `SVB` | found | The hum half is not flagged: the plan lets `sv_b4` establish `museum_hum` |
| S4 | should-fix, unestablished | SP-2 and SP-A at `ds_b4` on `museum_hum`, route `DSB > c_ds_b3` | found | |
| S5 | should-fix, unestablished | SP-2 and SP-A on `great_clock` at `sv_a5` (route `SVA`, the item's witness) and at the other nodes `ds_a5`, `cg_a5`, `av_conv` (`AVB`), `sv_conv` (`SVB`), `cg_conv` (`CGB`); also `museum_hum` at `av_conv` | found | All six nodes the item names |
| S7 | should-fix, unestablished | SP-2 and SP-A at `sv_conv3`, `ds_conv3`, `cg_conv3` on `nia_seeks_key` and `key_can_wake_menagerie`, on the `SVB`, `DSB`, `CGB` routes | found | |
| S8 | should-fix, unestablished | None at `n_key` | missed | The plan lets `n_key` establish `key_can_wake_menagerie` and records no "came for it" fact. The same facts are flagged one node earlier at `av_conv3` (B5), which is a different node and is not counted |
| S10 | should-fix, unestablished | SP-2 and SP-A at `s_c3` on `fettle_named`, route `KA > c_spring_c > c_sc_ok > c_sc2` | found | |
| S11 | should-fix, unestablished | SP-2 and SP-A at `n_shop` on `fettle_named`, route `SA` (via `c_key_a`, `s_a*`); SP-2 on the choice `c_shop_c` | found | |
| S13 | should-fix, unestablished | None on the instructions fact. `n_hub` is flagged on `nia_loves_a_creature`, `fettle_has_secret`, `fettle_named`, all unrelated to "instructions learned by heart" | missed | The plan lets `n_shop` establish `nia_knows_mend` on every route, so the crawlspace-and-cart route is not separated |
| S14 | should-fix, unestablished | SP-2 and SP-A at `fh_sec1` on `letter_hinted_secret`, route `H > c_hub_sec`; at `n_hub` (other node) on `fettle_has_secret`, and on the choice `c_hub_sec` | found | |
| S15 | should-fix, unestablished | SP-2 and SP-A at `e_win_eleph` on `elephant_lurched_at_nia`, route `H > c_hub_fx > c_fx_eleph > c_fx_eleph1 > c_fx_eleph2` | found | |

### z3, The Clocktower Cipher (scoring set 13)

`P` abbreviates `c_open > c_examine > c_note_inside`, as in the second read.

| Item | Severity, class | Finding(s) matched: rule, node, fact, route | Scored | Notes |
| --- | --- | --- | --- | --- |
| B1 | blocker, unestablished | SP-2 and SP-A at `n_clockface` on `cipher_wheel`, route `P > c_inside_stairs > c_stairs_face` (the item's witness) | found | |
| B2 | blocker, unestablished | SP-2 at `n_setjam` on the choice `c_jam_oil`, fact `has_oil_can`; SP-A at `n_setjam` on `has_oil_can`; route `P > c_inside_stairs > c_stairs_face > c_face_jam` | found | |
| B3 | blocker, state contradiction | SP-3 ERROR at `n_end_stuck`, choice `c_jam_stuck`, "one reading meets both" `has_oil_can` (at `c_pendulum_oil`) and `no_oil_can` (at `n_end_stuck`), route `P > c_inside_pendulum > c_pendulum_oil > c_face_jam > c_jam_stuck` (the item's witness) | found | |
| B4 | blocker, unestablished | SP-2 and SP-A on `eda_name` at `n_stairs` (route `P > c_inside_stairs`), and at the other nodes `n_backpanel` and `n_end_caught` | found | |
| B5 | blocker, unestablished | SP-2 and SP-A at `n_stairs` on `keeper_gave_token`, route `P > c_inside_stairs` | found (judgement call) | The plan's fact is the keeper giving a token, not describing one. On the item's witness (routes A to E) the keeper is never met, so the missing fact is the cause; on route F the keeper gives the token without describing it and no finding fires there |
| S1 | should-fix, unestablished | SP-2 and SP-A on `eda_name` at `n_study` (route `P > c_inside_study`, the item's witness) and at the other nodes `n_basement`, `n_setcorrect`, `n_vault`, `n_end_library`, `n_end_timeout`, `n_end_secret`, `n_end_hero`; on `clockmaker_built` at `n_inside` | found | |
| S2 | should-fix, unestablished | None on the goal fact. `n_inside` is flagged on `landing_inside` (M2) and `clockmaker_built` (S1) | missed | The plan lets `n_inside` establish `cipher_set_at_clockface`, the very presupposition |
| S3 | should-fix, unestablished | SP-2 and SP-A on `tower_has_vault` at `n_backpanel` (route `P > c_inside_stairs > c_stairs_face > c_face_panel`) and at `n_end_library` (route `P > c_inside_study > c_study_logs`), both the item's witnesses | found | |
| S4 | should-fix, unestablished | SP-2 and SP-A at `n_setjam` on `oil_can_on_ledge`, route `P > c_inside_stairs > c_stairs_face > c_face_jam` (the item's witness) | found | |
| S5 | should-fix, unestablished | None at `n_keeper_story` | missed | The plan records no key fact as required there |
| S6 | should-fix, unestablished | SP-2 and SP-A at `n_vault` on `tower_has_vault` ("a vault in the tower, opened from behind the clockface"), route `P > c_inside_stairs > c_stairs_face > c_face_jam > c_jam_oil` | found (judgement call) | Expresses the "nothing shows a panel opening" half, not the "solved is false" half. The checker's route enters by the stairs; the item's witness enters by the pendulum; both reach `n_vault` through `c_jam_oil` without a correct setting, which is the item's cause |
| S7 | should-fix, unestablished | None at `n_end_keepsake` | missed | The plan records no "letter opened" fact; `n_end_keepsake` requires only `sealed_letter` and `automaton` |
| S8 | should-fix, unestablished | None on the lock-up bell. `n_end_timeout` is flagged on `eda_name` (S1) | missed | The plan lets `n_end_timeout` establish `spin_jammed`, whose text includes the bell |

### Tally

| Book | Blockers found | Should-fix found | Scoring set found | Strict (judgement calls as misses) |
| --- | --- | --- | --- | --- |
| z1 Thornwood | 0 of 1 | 2 of 3 | 2 of 4 (50 percent) | 2 of 4 |
| z2 Menagerie | 2 of 2 | 10 of 12 | 12 of 14 (86 percent) | 12 of 14 |
| z3 Clocktower | 5 of 5 | 4 of 8 | 9 of 13 (69 percent) | 7 of 13 |
| **All** | **7 of 8** | **16 of 23** | **23 of 31 (74 percent)** | **21 of 31 (68 percent)** |

By class: `unestablished_fact_on_route` 21 of 29, `state_contradiction` 1 of 1 (z3 B3), `cross_payoff_reference` 1 of
1 (z2 B9), `two_backstories` 0 items, `public_plant` 0 items.

Every one of the eight misses traces to an extraction choice, not to checker logic: the plan lets the presupposing
node establish the presupposed fact (z2 S8, S13; z3 S2, S8), records no fact for the presupposition (z3 S5, S7; z1
S2), or records the contradicting statement without a `contradicts` pair (z1 B4).

### Exact classes: what is empty

The three books declare no variables and no choice conditions, so no plan has threads. Consequences:

- **Public plant: empty in all three books.** There is no gated payoff, so there is nothing to plant publicly, and
  SP-4 cannot fire. No second-read item of this class exists.
- **Two backstories: empty among the scored severities.** z2 has two minor items (M19, M20, Fettle's building of the
  menagerie against the portrait row and against the brass rabbit); neither was caught (no SP-3 on those facts) and
  neither is scored. z1 and z3 have none.
- **Cross-payoff reference: one item** (z2 B9). It was found, but by SP-2 and SP-A as an unestablished fact; SP-6, the
  rule written for this class, cannot fire without threads.
- **State contradiction (covered, not exact): one scored item** (z3 B3), found by SP-3, plus one minor (z3 M9), missed.

Row 2 therefore passes on one item. That is a weak test of the exact classes, and an empty class is not a pass.

## False alarms: ERRORs outside the second read

Every ERROR on the three plans was mapped to a second-read item (any severity, any class) by node, other nodes and
fact. z1: all 23 ERRORs map (S1 18, S3 4, and the SP-3 at `h_council`, which is S4). z3: all 42 map (B1 to B5, S1,
S3, S4, S6, and the minor items M2 and M6). z2: 65 of 138 map; 73 do not. Those 73 are grouped below by root fact
(the fact whose absence or contradiction produces them), because SP-2 and SP-A report the same pair twice and a fact
missing at its first mention cascades to every later node that needs it (`AL-820`). For each group the book was read
at the cited node and route.

The judgements are PROPOSED. Under the criterion the judgement of "wrong" is the owner's.

| Group (root fact) | ERRORs (rules) | Nodes | Checker's claim | What the book and route show | Proposed judgement |
| --- | ---: | --- | --- | --- | --- |
| SP-9 "wound" homograph | 7 (SP-9) | facts `elephant_lurched_at_nia`, `nia_waited_behind_baobab`, `elephant_made_whole`; nodes `sv_risk`, `av_a1`, `sv_a2`, `fh_fx_eleph2` | plan strings match the `graphic` bundle | "half-wound elephant", "wound down", "Wound full", "Wound true": the clockwork sense. The `AL-811` mask applies only when the same string holds a winding cue ("clock", "key", "spring" and so on) or "wound up/tight"; these strings have none | wrong: checker false alarm (the `AL-828` homograph class) |
| SP-9 "dead end" homograph | 3 (SP-9) | fact `nia_shut_in_gallery`; node `e_set_cg`; choice `c_cg_fail` cost | plan strings match the `lethal` bundle | "a gallery dead end", "a glass dead end": a blind corridor | wrong: checker false alarm (`AL-828`; the G1 re-run report flagged "die" and "dead" as live) |
| `nia_seeks_key` at `av_b2`, `sv_b2` | 4 (SP-2 2, SP-A 2) | `av_b2`, `sv_b2`, on the `AVB` and `SVB` routes | the node requires "Nia is searching for a key that could wake the museum" | A key-shaped decoy feather and a keyring on a shelf: Nia, locked in, hopes for keys. Nothing about waking. The second read lists both nodes under "Checked, not defects" | wrong: plan-extraction artefact (the fact is over-specified for these nodes) |
| `spare_spring_heavy` at `p_c1`, `p_c2` | 4 (SP-2 2, SP-A 2) | route `SA > c_shop_c` | the node requires "the spare mainspring is far heavier than it looks" | `p_c1` "the great heavy spring she must move" and `p_c2` "the heavy spare spring" describe the spring in the narration; nothing presupposes an earlier scene. The plan establishes the fact only at `p_b1` | wrong: plan-extraction artefact (should establish at `p_c1`) |
| `butterfly_winder` at `fh_fx_fly` | 2 (SP-2, SP-A) | route `H > c_hub_fx > c_fx_fly` via the aviary | the node requires the winder planted at `cg_a2` | "On a little stand among the ferns lay the tiny seed-small winder made for the butterflies": the node introduces the winder itself. (On the conservatory route the real defect is B10, found by SP-3) | wrong: plan-extraction artefact |
| `fettle_named` downstream of `n_shop` | 44 (SP-2 22, SP-A 22) | `p_c1`, `n_hub`, `fh_rw1`, `fh_rw_c2`, `fh_rw_cl1`, `fh_sec1`, `fh_sec_j1` to `j3`, `fh_sec_m2`, `fh_sec_c1`, `fh_sec_c3`, `fh_dawn_w2`, and nine endings, all on routes through `c_key_a` | each node requires "the caretaker is Keeper Fettle ..." | The real defect is the first mention (S10 at `s_c3`, S11 at `n_shop`), found and scored. After `n_shop` ("a letter in Keeper Fettle's own hand") the reader has the name; the later nodes are not separate defects (the second read checked `e_win_bird` explicitly). The plan records `n_shop` as requiring, not establishing, the name | cascade of a real, scored root: proposed not wrong if the owner counts by root; wrong at each node under a literal per-ERROR count |
| `great_clock` at `ds_conv` | 2 (SP-2, SP-A) | route `DSB > c_ds_b3 > c_ds_b4` | the node requires the great clock | On `DSB` the clock was first presupposed at `ds_b3` (S1, found); `ds_conv`'s mention follows it. The second read lists `av_conv`, `sv_conv` and `cg_conv` under S5 but rightly not `ds_conv` | cascade of a real, scored root: as above |
| `nia_spotted_trick` at `fh_rw1` | 3 (SP-2 2 incl. choice `c_rw_cl`, SP-A 1) | route `H > c_hub_rw` | the node requires "Nia has spotted a clever trick in Fettle's notes" | "the clever little trick she had spotted in Fettle's notes": no node on any route shows her finding a trick (on `H` she reads the manual twice, `p_a2`). The plan establishes the fact nowhere. Same shape as S13. The second reader accepted the helper gear at `fh_rw_cl1` as part of the drawings the letter reports, and may have read this line the same way | not wrong (arguable): real defect the second reader missed, should-fix level, unestablished fact |
| `nia_loves_a_creature` at `n_hub` | 3 (SP-2 2 incl. choice `c_hub_fx`, SP-A 1) | route `H` | the node requires "Nia has come to love one particular creature" | "mend just one beloved creature she had come to love": no route singles out a creature before this; `fh_fx1` then offers five. The plan establishes the fact nowhere, so the extractor read it as a presupposition | unclear: a mild real presupposition, or generic phrasing a reader accepts |
| SP-3 `clock_hands_stopped` against `great_clock_ticking` | 1 (SP-3) | `ds_conv3`, route `DSA > c_ds_a5 > c_ds_conv > c_ds_conv2` | one reading meets both | `ds_a5` "the great clock ticked its deep slow beat, and she could feel each tick"; three nodes later `ds_conv3` "its hands stopped and still". (`cg_a5` "beating" against `cg_conv3` "frozen still" is the same pattern; the checker reports one finding) | not wrong: real defect the second reader missed (mild; a reader could take the beat as the works rather than the hands) |

### Count against the budget

The criterion's unit is the ERROR, per book, budget one.

| Book | ERRORs | Outside the second read | Proposed wrong, per ERROR | Proposed wrong, per root group | Within budget? |
| --- | ---: | ---: | --- | --- | --- |
| z1 Thornwood | 23 | 0 | 0 | 0 | yes |
| z2 Menagerie | 138 | 73 | 20 (SP-9 10, artefacts 10); 66 with the two cascades; up to 69 if "unclear" is judged wrong | 5 (two SP-9, three artefact groups); 4 if the SP-9 findings are one group; 7 with the cascades | no, under every count in this row |
| z3 Clocktower | 42 | 0 | 0 | 0 | yes |

The only reading under which z2 stays within budget is to count by root group, to treat plan-extraction artefacts as
not wrong, and to count the SP-9 findings as one root. Plan-extraction artefacts are the blind extractor's choices,
not the checker's, but WP-1.6 measures "the revised checks and the plan-writing conventions" together, so this report
proposes counting them.

## Uncovered and minor classes

Reported, not scored. Items in classes the fact model does not cover (`timeline`, `location_or_physical_state`,
`label_outcome_mismatch`, `repeated_reveal`, `other`), and minor items in covered classes.

| Book | Uncovered-class items (all severities) | Caught anyway | How |
| --- | ---: | --- | --- |
| z1 | 21 (B1 to B3, S4 to S11, M1 to M10) | S4 (other: test numbering skips the warren) | SP-3 at `h_council`, `council_second_test` against `warren_mercy_test`, route `@council`; the extractor declared the pair as contradicting |
| z2 | 31 (B1 to B4, B6 to B8, B10, B11, S6, S9, S12, S16, and 18 minor) | B8 (ring of tiny keys against a single key); B10 (winder pocketed, then on its stand); M1 (letter read "last" when it is first) | B8: SP-3 at `fh_sec_c1`, `master_ring_tiny_keys` against `single_key_on_hook` (at `n_key`), plus SP-2. B10: SP-3 at `fh_fx_fly`, `winder_in_pocket` (at `cg_a3`) against `winder_on_stand`, on the conservatory route. M1: SP-2 and SP-A at `p_c1` on `examined_before_letter` |
| z3 | 13 (B6, M1 to M3, M5 to M8, M10 to M14) | M2 ("the landing" with no landing); M6 ("Decode the final message" against a plain letter) | M2: SP-2 and SP-A at `n_inside` on `landing_inside`, route `P`. M6: SP-3 at `n_end_hero`, `letter_encoded` (at `n_vault`) against `letter_plain` |

Six of 65 uncovered-class items were caught, each through a fact or `contradicts` pair the extractor chose to record
(two object contradictions, z2 B8 and B10; one numbering clash, z1 S4; one sequence slip, z2 M1; one missing
referent, z3 M2; one label, z3 M6). The uncovered timeline-heavy defects that dominate z1 (B1 to B3, S11: dusk in
the morning areas) were not touched.

Minor items in covered classes, also not scored: z2 M19 and M20 (`two_backstories`) and M21 (`unestablished`), z3 M4
(`unestablished`) and M9 (`state_contradiction`). None was caught.

## Noise

ERROR counts per plan, by rule. SP-1, SP-4, SP-6 and SP-8 reported no ERROR on any plan; with no variables and no
threads, SP-4 and SP-6 have nothing to test and SP-8 sees only symmetric costs.

| Plan | SP-2 | SP-3 | SP-9 | SP-A | Total ERRORs | Nodes with an ERROR | ERRORs mapped to a second-read item | Authoring minutes |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| z1 Thornwood | 11 | 1 | 0 | 11 | 23 | 12 of 376 | 23 | 75 |
| z2 Menagerie | 65 | 3 | 10 | 60 | 138 | 50 of 167 | 65 | 55 |
| z3 Clocktower | 20 | 2 | 0 | 20 | 42 | 15 of 26 | 42 | 40 |

WARNINGs (not counted): SP-3 z1 10, z2 2, z3 5 (all "routes no single reading crosses": the four approaches in z1,
the alternative endings everywhere); SP-8 z1 1, z2 2 (symmetric opportunity costs at `n_start` and `fh_fx1`).

Observations:

- SP-A repeats almost every SP-2 finding (equal counts in z1 and z3; 60 against 65 in z2, where the difference is four
  choice-level SP-2 findings and one pair SP-A does not repeat), so roughly half of each total is the `AL-820` double
  count.
- The one cascade that matters is `fettle_named` in z2: 44 ERRORs (32 percent of the plan's total) from one
  requires-not-establishes choice at `n_shop`. One root defect, scored once as S10 and S11.
- z3 is the cleanest signal: 42 ERRORs at 15 of 26 nodes, every one tied to a second-read item. z1 is quiet (23) and
  equally clean, but it caught only half its small scoring set.

## Context and consequences

This test exists because G1 passed on its one re-run after a revision designed by an agent that had read the answer
key. WP-1.6, as pre-registered: "G1 passed on its one re-run after a revision designed by an agent that had read the
answer key. This package measures the revised checks and the plan-writing conventions on books nobody has used to
design them."

Quoted exactly from `docs/planning/story-plan-implementation-plan.md`, WP-1.6:

> **If it passes.** The WP-0.4 second read may be retired as the standing control for catalog books (owner decision).
> **If it fails.** The second read stays; the report says which classes failed. Phase 2 is not blocked either way.

Under the proposed judgement the test fails on row 3 alone. No covered class failed on recall: unestablished facts 21
of 29, the one state contradiction and the one cross-payoff reference found. What failed is precision on z2: ten
SP-9 homograph ERRORs in the blind extractor's own plan strings (the `AL-828` class, open since the G1 re-run), and
ten ERRORs from three over-specified or misplaced plan facts. Two exact classes could not be tested at all, because
no book in this corpus declares variables. If the owner accepts the proposed judgement, the second read stays as the
standing control. If the owner judges otherwise (by root, artefacts not counted, SP-9 as one root), the test passes on
a mechanical count, but the exact-class row would still rest on a single item found by a general rule rather than
the rule written for it. Phase 2 is not blocked either way.

Disclosure: the scorer read the frozen second reads in order to score; it did not see them before the plans were
committed (`8f0e3c7`), and it changed no input. The v2 extraction prompt was designed by the agent that had read the
G1 answer key, but none of these three books was used in G1 or in designing the prompt (README).

## Summary

On three catalog books that no one had used to design the checks, the revised Story Plan checker, run on blind plans,
found 23 of the 31 blocker and should-fix continuity defects in its covered classes (74 percent; 68 percent with the
two judgement calls scored as misses): 2 of 4 in The Thornwood Trial, 12 of 14 in The Clockwork Menagerie and 9 of 13
in The Clocktower Cipher. That clears the half-found bar easily, and every miss traces to how a plan recorded a fact,
not to the checker's logic. The exact-class row passes only on one item, a cross-payoff reference caught as an
unestablished fact, because none of the books declares variables: the public-plant class is empty and the two
backstories appear only as minor items, so these classes were not really tested. Precision is where it fails. The
Thornwood and Clocktower plans raised no ERROR outside the second read, but the Menagerie plan raised 73, of which
this report proposes at least 20 as wrong: ten SP-9 matches on "wound" and "dead end" in the clockwork and corridor
senses, and ten from plan facts recorded at the wrong node or over-specified. That is over the budget of one per book
under every count this report proposes (it stays within budget only if artefacts are excused and the SP-9 findings
are counted as one), so the proposed overall verdict is FAIL, which under WP-1.6 means the
second read stays as the standing control; Phase 2 is not blocked. The judgement of which ERRORs are wrong is the
owner's.
