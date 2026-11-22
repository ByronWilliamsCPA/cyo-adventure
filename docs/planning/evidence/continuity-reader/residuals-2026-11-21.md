Summary (6 lines):
1. 28 suspects plus one related find checked against the current text; witnesses replayed, quotes matched verbatim.
2. Real: 1 blocker (Signal `m_num_countdown`), 8 should-fix and 11 minor; 9 suspects are not defects.
3. Midnight Museum, Sky-Ship and Cave of Echoes keep a usable clean label; each has known residuals to record.
4. Signal fails D12's clean premise: one blocker sits in both blind plans, as a requirement the route never met.
5. Mapmaker's Island carries four should-fix, one a same-route contradiction that both plans mark (checker ERROR).
6. Recommendation: relabel Signal and Mapmaker now, then fix and re-extract them; record residuals on the other three.

<!-- markdownlint-disable MD038 -- witness routes are code spans wrapped across lines -->

# Residual check of the five post-fix held-out books (2026-11-21)

Independent continuity check of the suspects raised by the ten blind Story Plan extractions in
`clean-plans/plans/{c1..c5,d1..d5}.plan.json` (mapped in `clean-plans/manifest.json`). Read-only: no book or plan was
changed. (Written to the repo by the orchestrator from the checker agent's saved copy.) Each book was verified against the sha256 that its two extractions bind:

| Book | sha256 (prefix) | Plans |
| --- | --- | --- |
| `out/the-sky-ship-stowaway.filled.json` | `73a5c0d5d197` | c5, d1 |
| `out/the-signal-in-the-static.filled.json` | `d701b7891ff2` | c3, d4 |
| `out/the-mapmakers-island.filled.json` | `2bb129096f67` | c4, d2 |
| `out/the-cave-of-echoes.filled.json` | `3a3606f4a0be` | c2, d5 |
| `out/the-midnight-museum.filled.json` | `e466cce64d9f` | c1, d3 |

## Method

- Routes were enumerated depth first with `StoryEngine` (`start`, `visible_choices`, `choose`), honouring conditions
  and effects: 41,460 routes for Sky-Ship, 311,654 for Mapmaker's Island. For each suspect, every route into the node
  was searched for an earlier passage that establishes the fact. The shortest route without one is the witness.
- All witnesses below (44 in total) were replayed from `n_open` by script and land on the named node. Every
  quotation was matched verbatim against the node body or one of its labels.
- What each blind pass raised was read from three places: its `requires`/`establishes`/`contradicts` entries and
  `provenance.notes`, and an `scripts/check_story_plan.py <book> <plan> --assertions <file>` run on each plan.
  "Both" means each pass recorded the presupposition or contradiction at that node independently.
- The WP-0.4 findings (`../story-plan-retro/findings-<slug>.md`) were read to see what had already been fixed, but
  each verdict below comes from the current text.
- Severity follows the WP-1.6 second reads. **Blocker** means a plain contradiction, or a fact that is false on the
  route. **Should-fix** means an unshown presupposition, or a label that contradicts its outcome. **Minor** means a
  small wording slip.

## Witness shorthands

Each shorthand expands to exact choice ids, joined by `>`.

- `SS-eng` = `c_open > c_start_eng > c_eng_deep > c_eng_a > c_eng_a_go > c_eng_a2_go > c_eng_conv_go` (lands on
  `n_friend`).
- `SG-H` = `c_open > c_n_shelf_1 > c_n_shelf_battery_1 > c_n_start_1 > c_r_coord_1_1 > c_r_coord_harbor_1 >
  c_r_coord_harbor_ask_1 > c_r_coord_beat_1 > c_r_coord_close_1` (the WP-0.4 `H`). `SG-N` = `c_n_b1_1 >
  c_n_b1_note_1 > c_n_b1_echo_1`. `SG-S` = `c_n_b1_2 > c_n_b1_slip_1 > c_n_b1_echo_1`.
- `SG-D3` = `c_n_b2_1 > c_n_b2_echo_1 > c_n_b2_choice_1 > c_mm_listener_1_1 > c_mm_list_family_1 >
  c_mm_list_daughter_1 > c_n_b3_1 > c_n_b3_echo_1 > c_n_b3_choice_3 > c_f_help_1_2` (from `n_b2` to
  `f_he_colleague`).
- `R-camp` and `R-summit` are as defined in the WP-0.4 Mapmaker file. `R-camp` = `c_open > c_n_start_4 >
  c_tw_enter_3 > c_tw_cellar_2 > c_tw_supplies_1 > c_cf_campapproach_1 > c_camp_ascent1_1 > c_camp_ascent2_1 >
  c_camp_ascent3a_1 > c_camp_ascent4_1`. `R-summit` = `R-camp > c_camp_ascent5_1 > c_L_camp_3 >
  c_camp_summitpath_1 > c_ridge_notch_1 > c_wind_gap_1` (enters `L_summit`; it took "Alder's chart" and skipped the
  table and the trunk).
- `MM-key` = `c_open > c_desk_map > c_desk_map_go > c_start_gems > c_gems_case > c_gems_vitrine > c_vitrine_go >
  c_corridor_key` (lands on `n_key`). `MM-rot` = `MM-key > c_key_founder > c_founder_desk > c_desk_study >
  c_study_cipher > c_cipher_stars > c_stars_dome > c_dome_rotunda` (lands on `n_rotunda`).

## Verdicts at a glance

| ID | Book | Node(s) | Verdict | Class | Raised by |
| --- | --- | --- | --- | --- | --- |
| SS-1 | Sky-Ship | `e_win_discovery` | real: minor | `unestablished_fact_on_route` | both |
| SS-2 | Sky-Ship | `b_free1` | real: minor | `unestablished_fact_on_route` | d1 |
| SS-3 | Sky-Ship | `c_nest_a`, `f_rig_a` | real: should-fix | `state_contradiction` | c5 |
| SS-4 | Sky-Ship | `e_set_hold`, `e_set_salon`, `e_set_galley`, `e_set_cabin` | not a defect | `other` | c5 |
| SG-1 | Signal | `m_numbers_1` | real: minor | `unestablished_fact_on_route` | both |
| SG-2 | Signal | `m_num_countdown` (with `n_b2`) | real: blocker | `unestablished_fact_on_route` | both |
| SG-3 | Signal | `n_b2_choice` | not a defect | `unestablished_fact_on_route` | d4 |
| SG-4 | Signal | `m_who_article`, `f_he_colleague`, `e_he_dead` | real: should-fix | `two_backstories` | both |
| SG-5 | Signal | `e_he_complete` | real: should-fix | `unestablished_fact_on_route` | c3 |
| SG-6 | Signal | `r_re_hut` | real: minor | `unestablished_fact_on_route` | c3 |
| MI-1 | Mapmaker | 14 nodes naming the Chart House | real: minor | `unestablished_fact_on_route` | both |
| MI-2 | Mapmaker | 8 nodes naming "the sketchbook" | real: should-fix | `unestablished_fact_on_route` | both |
| MI-3 | Mapmaker | `camp_summitpath`, `L_summit` and later | not a defect | `unestablished_fact_on_route` | both |
| MI-4 | Mapmaker | `ship_turns` | not a defect | `unestablished_fact_on_route` | both |
| MI-5 | Mapmaker | `camp_journal` | real: minor | `unestablished_fact_on_route` | both |
| MI-6 | Mapmaker | `ch_reef`, `race_down`, `summit_signal` | not a defect | `unestablished_fact_on_route` | split |
| MI-7 | Mapmaker | `cv_upflow`, `cv_glowworm` | real: minor | `unestablished_fact_on_route` | split |
| MI-8 | Mapmaker | `cv_deepglow` | real: minor | `unestablished_fact_on_route` | d2 |
| MI-9 | Mapmaker | `tw_brazier` label into `e_tw_nofuel` | real: should-fix | `label_outcome_mismatch` | neither |
| MI-10 | Mapmaker | `ch_pencil`, `e_ch_dusk` | real: should-fix | `state_contradiction` | both |
| MI-11 | Mapmaker | `ch_gather` (from `summit_signal`) | real: should-fix | `unestablished_fact_on_route` | neither |
| CE-1 | Cave | `da_skylight`, `da_coins2` | real: minor | `unestablished_fact_on_route` | c2 |
| CE-2 | Cave | `ra_starfish2` | real: minor | `unestablished_fact_on_route` | c2 |
| CE-3 | Cave | `la_bell4`, `da_compass2` | not a defect | `unestablished_fact_on_route` | c2 |
| CE-4 | Cave | label `c_da_out`, `da_compass`, `da_compass2` | real: should-fix | `label_outcome_mismatch` | c2 |
| MM-1 | Museum | `v_share`, endings, label `c_swap_end` | not a defect | `unestablished_fact_on_route` | c1 |
| MM-2 | Museum | `v_letter_ps`, label `c_letter_ps` | not a defect | `unestablished_fact_on_route` | d3 |
| MM-3 | Museum | `e_neutral_call_home` | not a defect | `location_or_physical_state` | d3 |
| MM-4 | Museum | `k_study`, `c_base_study`, `e_win_hero_curator` | real: minor | `unestablished_fact_on_route` | c1 |

"Split" means the two passes raised the suspect at different nodes of the group; the entry below says which.

## The Sky-Ship Stowaway

**SS-1. `e_win_discovery`: "my forty buckets".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "\"So THIS is where my forty buckets go,\" he said".
- Witness: `SS-eng > c_friend_cabin > c_cabin_a > c_cabin_a_go > c_cabin_mid_go > c_storm_deck > c_deck_a >
  c_deck_a_go > c_deck_mid_go > c_secret_people > c_people_b > c_people_b_go > c_people_mid_go > c_bridge_tell >
  c_tell_reveal > c_tell_reveal_win` (22 choices).
- Why: the buckets appear only at `f_galley1`, `s_hold_b` and the ending `e_set_galley`. On 3,840 of the 6,944
  routes into this ending the line is a callback to nothing. It still reads on its own (the cook makes the mash and
  has just learned where it goes), so it stays a small slip. "The cook" is a ship's role and is fine.
- Raised by: both (c5 `forty_buckets_mash`, d1 `mash_forty_buckets` plus a note).

**SS-2. `b_free1`: "that harness".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "I have not been able to get near that harness since the first thunder".
- Witness: `SS-eng > c_friend_galley > c_galley_a > c_galley_a_go > c_galley_mid_go > c_storm_deck > c_deck_a >
  c_deck_a_go > c_deck_mid_go > c_secret_pip > c_pip_go > c_save_mid_go > c_bridge_free` (19 choices).
- Why: the harness is shown only at `s_hold_b` and `p_save1`. On 4,256 of the 7,936 routes into `b_free1` nobody has
  mentioned it. The captain says it while standing in front of Nimbus, so "that" works as pointing within the scene,
  and both follow-ons (`b_free_ok`, and `e_neu_kite` after the WP-0.4 fix) show the harness. Minor.
- Raised by: d1 only (`nimbus_wears_harness` and a note).

**SS-3. Seam spotted, then no seam can be told apart.** Real: should-fix. Class `state_contradiction`.

- Quotes: `c_nest_a` "Near the stern, though, one seam looked different, puckered and dark, like a mend on an old
  sock." and "\"That one is tired,\" Bree whispered." Then `f_rig_a`: "Bree looked up, but she could not tell one seam
  from another." This follows a rigger's question: "Which seam, the old one, the one that always goes?"
- Witness: `c_open > c_start_nest > c_nest_deep > c_nest_a > c_nest_a_go > c_nest_a2_go > c_nest_conv_go >
  c_friend_rig > c_rig_a` (9 choices; 820 routes cross both nodes).
- Why: the riggers ask exactly the question Bree answered earlier on this route, and the text has her unable to
  answer it, with no word that she remembers the stern seam. The vantage points differ: a spyglass on the outer
  envelope from the crow's nest, against the bare eye on the gasbags from an inner catwalk. That keeps this short of
  a plain contradiction, but the reader gets no hint of the difference.
- Raised by: c5 only (`bree_cant_tell_seams` contradicts `bree_spotted_tired_seam`; a checker SP-3 ERROR).

**SS-4. The purser named without introduction.** Not a defect. Class `other` (vocabulary).

- Quotes: `e_set_hold` "The purser saw Bree ashore at the next port."; `e_set_salon` "He sat her down in the purser's
  office"; `e_set_galley` "Then he marched Bree to the purser's office, grumbling all the way."; `e_set_cabin` "she
  marched them to the purser, quite gently."
- Witness: `c_open > c_start_hold > c_hold_risk > c_hold_fail` (`e_set_hold`). For `e_set_salon`: `c_open >
  c_start_salon > c_salon_risk > c_salon_fail`.
- Why: a purser is a standing role on a passenger ship, in the same way as "the cook" or "the steward". Each sentence
  gives the role its function (an office, seeing stowaways ashore). Nothing on any route contradicts it. The word may
  stretch the 8-11 band, but that is a vocabulary question, not continuity.
- Raised by: c5 only (an SP-2 and SP-A ERROR at all four nodes). d1 recorded the purser as established in place.

**Sky-Ship totals:** 0 blocker, 1 should-fix, 2 minor.

## The Signal in the Static

**SG-1. `m_numbers_1`: "the cedar trunk".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "Her grandfather's logbook lies by her elbow, fetched down from the cedar trunk in the attic".
- Witness: `SG-H > SG-N > c_n_b1_choice_1` (13 choices).
- Why: the WP-0.4 fix (B4) added this clause to explain where the logbook came from. On routes that skipped
  `r_notes_1` and `r_no_trunk`, the definite "the cedar trunk" names a trunk the reader has never met. The clause
  introduces it well enough that the reader infers it. "A cedar trunk" would remove the slip.
- Raised by: both (c3 and d4 `cedar_trunk`; d4 also in a note).

**SG-2. `m_num_countdown`: the letter M known before it is found.** Real: blocker. Class
`unestablished_fact_on_route`.

- Quote: "threaded through every cycle is that one stubborn letter, M."
- Witness: `SG-H > SG-N > c_n_b1_choice_1 > c_m_numbers_1_2 > c_m_num_time_2 > c_m_num_pattern_1` (16 choices).
  Continue with `> c_m_num_countdown_1` to reach `n_b2`.
- Why: on the timing route, nothing before this passage mentions a letter. Only the cipher route (`m_num_cipher`)
  decodes an M, and Wren has no means here of learning one. One screen later, `n_b2` on the same route says the two
  tones are something "that she has heard all week and taken for the machine clearing its throat". Only then does
  she check them against the Morse chart and find M. So the text gives her the letter before the passage in which
  she discovers it: a fact false on the route. 4,824 of the 8,040 routes into the node are affected.
- Raised by: both (c3 `loop_letter_m`, d4 `letter_m_in_loop`, each an SP-2 ERROR, plus a d4 note).

**SG-3. `n_b2_choice`: "the count running down".** Not a defect.

- Quote: "what is the count running down to, now that it has stopped starting over from the top?"
- Witness: `SG-H > SG-N > c_n_b1_choice_2 > c_m_who_1_1 > c_m_who_film_1 > c_m_who_article_1 > c_n_b2_1 >
  c_n_b2_echo_1` (18 choices; this is a who-is-Kell route).
- Why: `n_open` is on every route and describes "a slow tone that counts downward and resets". The parent `n_b2_echo`
  shows that the tone starts lower each night and is "running out of room". All 56,640 routes into the node carry
  that setup.
- Raised by: d4 only (`count_going_down`, an SP-2 ERROR). c3 required other facts here, all of them met.

**SG-4. Kell "the only one" who refused, but Ruiz also stayed.** Real: should-fix. Class `two_backstories`.

- Quotes: `m_who_article` "He is the only one of nine staff who refused the transfer inland." Then `f_he_colleague`:
  "Eight names are bracketed together, with a note beside the bracket: TRANSFERRED INLAND." and, for Ruiz, "next to
  that her grandfather has printed three words: STAYED, WON'T TALK." Then `e_he_dead`: "\"You want Ruiz,\" he says,
  "because the rest of us took the money and went."
- Witness: `SG-H > SG-S > c_n_b1_choice_2 > c_m_who_1_1 > c_m_who_film_1 > c_m_who_article_1 > SG-D3` (26 choices,
  lands on `f_he_colleague`). Add `> c_f_he_colleague_2` for `e_he_dead`; 1,080 routes cross both nodes.
- Why: on one reading, the paper says Kell alone refused the transfer, out of nine staff. The address book then
  lists eight transferred men and Ruiz, who stayed and still has keys (`e_he_dead`), so with Kell that makes ten
  relay men. The two can be squared only by a reason the book never gives, such as Ruiz resigning rather than
  refusing, or the paper getting it wrong. Should-fix rather than blocker, because the article is an in-world source
  that could be mistaken.
- Raised by: both (c3 marked `kell_only_one_refused` contradicting `ruiz_stayed`, an SP-3 ERROR; d4 recorded both
  facts in a note without marking them).

**SG-5. `e_he_complete`: "the number circled in his address book".** Real: should-fix. Class
`unestablished_fact_on_route`.

- Quote: "dials the number circled in his address book".
- Witness: `SG-H > SG-S > c_n_b1_choice_1 > c_m_numbers_1_1 > c_m_num_cipher_1 > c_m_num_cracked_1 > SG-D3 >
  c_f_he_colleague_1 > c_f_he_join_1` (28 choices).
- Why: Kell's address book and its circled number are introduced only at `f_st_control`, `e_st_hesitate` and
  `e_he_okafor`, and the Ruiz route visits none of them. 2,016 of the 2,520 routes into this ending are affected.
  The only address book this route has shown is Grandpa's (`f_help_1`, `f_he_colleague`), so "his" reads at first as
  the wrong man's. This is the climax line, and it names the object that reaches Marin.
- Raised by: c3 only. d4 recorded `circled_number` as established at `e_he_complete`. d4's own SP-2 ERROR at
  `e_he_okafor` is not a defect, because that passage introduces "a number circled".

**SG-6. `r_re_hut`: "when the county did".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "The technician Alder, whoever he is, did not walk away when the county did."
- Witness: `c_open > c_n_shelf_1 > c_n_shelf_battery_1 > c_n_start_2 > c_r_relay_1_2 > c_r_re_lane_2` (6 choices; all
  3,788 routes into the node).
- Why: the relay route has shown a station that "has stood dark for as long as she can remember" and a chained gate,
  but has not said that the county ran it or closed it. A 13-16 reader infers an abandoned public site, and the
  sentence introduces the county as it goes. It is a small presupposition.
- Raised by: c3 only (`county_closed_relay`).

**Signal totals:** 1 blocker, 2 should-fix, 2 minor.

## The Mapmaker's Island

**MI-1. The Chart House, never introduced.** Real: minor. Class `unestablished_fact_on_route`.

- Quote (`tf_enter`): "Everyone at the Chart House knew the rule of such places."
- Witness: `c_open > c_n_start_5` (2 choices).
- Nodes (14): `mg_readmarks`, `cv_ochre`, `e_cv_paintings`, `tf_enter`, `cove_starrock`, `e_star_map`, `ch_double`,
  `e_ch_alder_name`, `e_ch_spare`, `signal_flash`, `mg_ruin`, `e_ch_clean`, `e_cv_fish`, `e_tf_bell`.
- Why: no route introduces it. Each use is self-explaining ("taught", "apprentice", "keepers"), and with `n_open`'s
  apprenticeship it reads as Wren's guild. It is world-building left implicit, the same on every route, rather than
  a route-dependent fact. The WP-0.4 reader edited `cv_ochre` and kept the name.
- Raised by: both (c4 note and SP-2, d2 SP-2).

**MI-2. "The sketchbook" against "one blank sheet of paper".** Real: should-fix. Class
`unestablished_fact_on_route`.

- Quotes: `n_open` "Wren climbed out with a satchel, a flask, and one blank sheet of paper." Then, for example,
  `e_tf_stranded` "The sketchbook rode high overhead in both hands" and `camp_ascent4` "checked the sketchbook was
  dry".
- Witness: `c_open > c_n_start_5 > c_tf_enter_1 > c_tf_sandbar_2` (4 choices, `e_tf_stranded`). For `e_mg_canoe`:
  `c_open > c_n_start_1 > c_mg_enter_4 > c_mg_lagoon_1 > c_mg_canoe_2`.
- Nodes (8): `camp_ascent4`, `e_tf_stranded`, `e_mg_canoe`, `e_cf_slip`, `e_tw_charts`, `e_mg_chick`, `e_cf_canopy`,
  `e_cv_raft`.
- Why: the opening lists Wren's kit, and the single sheet is the point of the test. A sketchbook is then treated as
  long-known kit, the thing Wren saves from the water. It does not contradict the opening outright, since it could
  be in the satchel, but it is an unshown presupposition in eight passages against an opening that inventories the
  kit and leaves it out.
- Raised by: both (c4 note and SP-2 `has_sketchbook`; d2 SP-2 `wren_has_sketchbook`).

**MI-3. Alder's tools after "Take Alder's chart".** Not a defect.

- Quotes: `L_camp` "Beside it lay a row of pens, a brass spyglass, and a small signal mirror"; `camp_summitpath`
  "with Alder's chart and tools carried safe"; `L_summit` "signal the far ship first with Alder's mirror".
- Witness: `R-camp > c_camp_ascent5_1 > c_L_camp_3` (12 choices; lands on `camp_summitpath`).
- Why: the WP-0.4 fix (finding 43) holds. `L_camp` is on every route into the summit and lays the tools out, and
  `camp_summitpath` says they are carried. "Mirror" and "spyglass" occur before `L_summit`, `summit_signal`,
  `signal_aim`, `ch_sightings`, `ch_farshore` and `ch_ink` on every route (0 misses in 302,528 routes into
  `L_summit`). The label names only the chart, but the passage it leads to adds the tools, so label and outcome agree.
- Raised by: both (c4 note and SP-2 `has_alder_tools`; d2 SP-2 at `camp_summitpath`, `summit_signal`, `L_summit`).

**MI-4. `ship_turns`: "a lost mapmaker's mirror".** Not a defect.

- Quote: "called by a blade of light off a lost mapmaker's mirror."
- Witness: `R-summit > c_L_summit_2 > c_summit_signal_1 > c_signal_aim_1 > c_signal_flash_1` (19 choices).
- Why: the WP-0.4 fix (finding 49) softened "dead" to "lost". `L_camp`, on every route, shows the camp "long empty",
  with the tools set out "as if for the next mapmaker". That supports "lost" in its sense of gone and not returned.
- Raised by: both (`alder_never_returned`, an SP-2 ERROR in c4 and d2).

**MI-5. `camp_journal`: the hidden cove and the spring as known.** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "Naming the hidden cove. Fixing the spring and the reef, and dreaming of the far wild shore."
- Witness: `R-camp > c_camp_ascent5_1 > c_L_camp_2 > c_camp_trunk_2` (13 choices; 24,120 routes have no cove before
  it, and 6,720 have no spring).
- Why: this is a summary of Alder's journal, so the definite articles are Alder's own references, and the reader
  learns from it that a hidden cove and a spring exist. Writing "a hidden cove" and "a spring" would fix it.
- Raised by: both for the cove (c4 and d2 `hidden_cove`); d2 only for the spring (`island_spring`).

**MI-6. The cove at `ch_reef`, `race_down` and `summit_signal`.** Not a defect.

- Quotes: `ch_reef` "Wren fixed the reef and the cove first"; `race_down` "down a hand-cut path toward the cove";
  `summit_signal` "might call the boat in early to the sheltered cove".
- Witnesses: `R-summit > c_L_summit_1 > c_summit_survey_2` (`ch_reef`); `R-summit > c_L_summit_2 > c_summit_signal_1 >
  c_signal_aim_1 > c_signal_flash_1 > c_ship_turns_1` (`race_down`).
- Why: `L_summit` ("every secret cove") is on every route into these nodes, `summit_survey` ("Sight the reef, the
  cove, the pale flats") is the parent of `ch_reef`, and `summit_signal` and `ship_turns` name the sheltered cove
  before `race_down`. 0 of 73,024 routes into `ch_reef` and 0 of 10,432 into `race_down` lack "cove".
- Raised by: split (`ch_reef` d2 only; `summit_signal` c4 only; `race_down` and `ship_turns` both).

**MI-7. `cv_upflow`, `cv_glowworm`: "the spring" in the caves.** Real: minor. Class `unestablished_fact_on_route`.

- Quotes: `cv_upflow` "The way to the spring ran upstream"; `cv_glowworm` "the trickle of the spring somewhere ahead".
- Witnesses: `c_open > c_n_start_3 > c_cv_enter_1 > c_cv_water_2` (`cv_upflow`); `c_open > c_n_start_3 >
  c_cv_enter_1 > c_cv_water_3 > c_cv_rift_2` (`cv_glowworm`, all 1,912 routes into it).
- Why: the parent `cv_water` speaks only of "wherever the water was born", and no spring has been named. `cv_upflow`
  then explains "the island's spring" itself. Small definite slips of the same kind the WP-0.4 pass fixed at
  `mg_seep` ("A seep").
- Raised by: split (`cv_glowworm` both; `cv_upflow` d2 only; c4 also flagged `cv_ochre` and the `L_cove` label).

**MI-8. `cv_deepglow`: "the glow" after the squeeze.** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "Wren pushed toward the glow, and it grew from a thread to a crack to a bright seam of daylight."
- Witness: `c_open > c_n_start_3 > c_cv_enter_1 > c_cv_water_3 > c_cv_rift_1 > c_cv_squeeze_1` (6 choices).
- Why: the other two parents set up a light ahead: `cv_glitter` "a further glow" and `cv_arch` "to the light". The
  squeeze route has only the glowworms behind her and "the wider cave" ahead. "A glow" fixes it.
- Raised by: d2 only (`deep_glow_seen`).

**MI-9. `tw_brazier` label "give up" against an ending that searched.** Real: should-fix. Class
`label_outcome_mismatch`.

- Quotes: label `c_tw_brazier_2` "Give up on the dead beacon and turn back." Then `e_tw_nofuel`: "Wren poked about the
  cold brazier and the rocks around it, hunting for the fuel store." and "the search had swallowed a good hour".
- Witness: `c_open > c_n_start_4 > c_tw_enter_2 > c_tw_stair_1 > c_tw_top_3 > c_tw_beacon_1 > c_tw_brazier_2` (7
  choices).
- Why: the reader picks the option that is not the search, and gets the search and its cost. The sibling label
  `c_tw_brazier_1` is the one that searches.
- Raised by: neither as a defect. Both recorded the outcome (c4 `no_fuel_store`, d2 `fuel_store_not_found`) and the
  label's intent "give up on the dead beacon"; c4 even gave its cost as "an hour lost", but neither marked it.

**MI-10. `ch_pencil` "nothing missing", then `e_ch_dusk` "half-drawn".** Real: should-fix. Class
`state_contradiction`.

- Quotes: `ch_pencil` "But nothing was missing, nothing forgotten". Then `e_ch_dusk`: "Wren ran for the beach at last
  with a wonderful, unfinished thing rolled tight, too detailed ever to call done." and "Wren climbed aboard with the
  loveliest half-drawn island in the world".
- Witness: `R-summit > c_L_summit_2 > c_summit_signal_2 > c_ch_gather_1 > c_ch_table_2 > c_ch_pencil_2` (20
  choices).
- Why: on one reading the chart is complete, and on the next screen it is half-drawn. "Unfinished" can be read as
  perfectionism, since she keeps adding, but "half-drawn" cannot. Should-fix rather than blocker, because the
  perfectionist reading carries most of the passage.
- Raised by: both (`chart_finished` against `chart_unfinished`, an SP-3 ERROR in c4 and in d2).

**MI-11. `ch_gather` "everything fixed" after only signalling.** Real: should-fix. Class
`unestablished_fact_on_route`.

- Quotes: `summit_signal` "It would cost the finishing of the chart, or most of it." Then `ch_gather`: "Everything
  seen, everything fixed, everything understood." and "every piece fitting against Alder's careful half like two
  halves of one puzzle".
- Witness: `R-summit > c_L_summit_2 > c_summit_signal_2` (17 choices).
- Why: on this route no summit survey happened (`summit_survey`, `ch_sightings`, `ch_reef` and `ch_farshore` are all
  skipped). The day's sketches cover one region plus the camp, and the passage before warned that signalling would
  cost the chart. "Everything fixed" and the blank half fitting are unshown. This route also feeds MI-10, so the
  "nothing missing" of `ch_pencil` is unearned on the shortest route as well.
- Raised by: neither as a defect. d2 recorded `island_fully_surveyed` as established at `ch_gather`.

**Mapmaker's Island totals:** 0 blocker, 4 should-fix, 4 minor.

## The Cave of Echoes

**CE-1. "The museum".** Real: minor. Class `unestablished_fact_on_route`.

- Quotes: `da_skylight` "She already imagines how the museum will react."; `da_coins2` "She is already picturing the
  museum polishing every coin".
- Witnesses: `c_open > c_down > c_da_fork > c_bat > c_da_creep > c_da_grey > c_batenter > c_da_stair > c_da_climb >
  c_da_push` (`da_skylight`); `c_open > c_down > c_da_fork > c_cache > c_da_door > c_da_peer > c_cacheenter >
  c_da_boxes > c_coins > c_da_carry` (`da_coins2`).
- Why: no museum exists in the book's world before these endings. The reader infers a local museum, but the
  definite article presumes they already know one.
- Raised by: c2 only (note and SP-2 `museum_known`). d5 recorded `local_museum` as established in place.

**CE-2. "The rockpool club back home".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "She knows the rockpool club back home will not believe her story."
- Witness: `c_open > c_right > c_ra_fork > c_pool > c_ra_crouch > c_ra_channel > c_enter > c_ra_kneel > c_star >
  c_ra_sketch` (10 choices).
- Why: an identity detail introduced in the last passage of a route with the definite article. It is
  self-explaining, and the WP-0.4 reader recorded it as soft and left it.
- Raised by: c2 only.

**CE-3. "The whole town".** Not a defect.

- Quotes: `la_bell4` "Maya can already picture the whole town gathering close."; `da_compass2` "She already knows the
  whole town will beg to hear this story".
- Witness: `c_open > c_left > c_la_fork > c_hum > c_la_ring > c_la_chime > c_bell > c_la_bell2 > c_la_bell3 >
  c_la_bell4` (10 choices).
- Why: "the whole town" is an idiom for the people of the place where Maya lives, which the same passage locates
  ("near her home"). It presupposes nothing a reader needs.
- Raised by: c2 only (`town_home`).

**CE-4. Label "Follow the compass out." against Biscuit leading.** Real: should-fix. Class `label_outcome_mismatch`.

- Quotes: label `c_da_out` "Follow the compass out." Then `da_compass`: "Biscuit trots ahead, sure of the way, while
  Maya follows him through the dark passage." and `da_compass2`: "Biscuit leads Maya straight out to the cave mouth."
- Witness: `c_open > c_down > c_da_fork > c_cache > c_da_door > c_da_peer > c_cacheenter > c_da_boxes > c_compass >
  c_da_out` (10 choices).
- Why: WP-0.4 fix 2 rewrote both bodies so that Biscuit, not the needle, finds the way out, because a compass cannot
  point to a cave mouth. The label was left behind and still asserts the claim that fix removed. Same class as the
  known Vanishing Orchard residual.
- Raised by: c2 only (a provenance note). d5 recorded `biscuit_leads_out` and the label's intent without marking them.

**Cave of Echoes totals:** 0 blocker, 1 should-fix, 2 minor.

## The Midnight Museum

**MM-1. "The curator", named without introduction.** Not a defect.

- Quotes: `v_share` "The curator unlocked the staff door at eight."; label `c_swap_end` "Carry the owl up to meet the
  curator."; `e_win_secret_workshop` "The curator was not going to believe a word".
- Witnesses: `MM-rot > c_rot_align > c_align_set > c_set_vault > c_vault_share` (`v_share`); `MM-rot > c_rot_align >
  c_align_set > c_set_vault > c_vault_grab > c_grab_swap` (`v_grab_swap`, label offered); `MM-rot > c_rot_panel >
  c_panel_secret > c_secret_workshop > c_workshop_end`.
- Why: a museum's curator is a role the setting supplies, like a ship's purser, and every use gives the role its
  function (keys, the staff door at eight). Nothing contradicts it. The gender (she) is consistent across all uses.
- Raised by: c1 only (`museum_has_curator`, SP-2 at eight nodes and at `c_swap_end`).

**MM-2. "The founder's glasses" on the back-stair route.** Not a defect.

- Quotes: `k_stairs_base` "Inside lay a rolled chart, brittle at the edges, and a pair of round glasses with thick
  lenses." and "\"Turn the inner ring three places, and good luck to you.\"". Then `v_letter_ps`: "Nadia pulled the
  founder's glasses down out of her hair". Label `c_letter_ps`: "Read the row of ants through the founder's glasses."
- Witness: `MM-key > c_key_stairs > c_stairs_base > c_base_study > c_study_cipher > c_cipher_stars > c_stars_dome >
  c_dome_rotunda > c_rot_align > c_align_set > c_set_vault > c_vault_letter > c_letter_ps` (20 choices).
- Why: `n_key` is on every route. There the founder says the key opens his back stair and "Behind each one I left a
  way to read that note". The cupboard at the foot of that stair holds his chart, with his instruction to the
  finder, and the glasses beside it. That they are his is as well established here as on the `k_founder_desk` route,
  which also never says it in words.
- Raised by: d3 only (note and SP-2 `glasses_are_founders`).

**MM-3. The brass key on the guard's desk.** Not a defect.

- Quote: `e_neutral_call_home` "and at the brass key on his desk".
- Witness: `MM-rot > c_rot_records > c_records_phone > c_phone_call` (18 choices).
- Why: every route into the node passes `n_key`, so Nadia carries the key. She sits at the guard's desk waiting to be
  collected, and setting the key down there is an unstated but ordinary action. Nothing places the key elsewhere.
  The WP-0.4 reader reached the same verdict.
- Raised by: d3 only (a note).

**MM-4 (added). "The reading table" on the back-stair route.** Real: minor. Class `unestablished_fact_on_route`.

- Quotes: label `c_base_study` "Carry the chart to the reading table."; `k_study` "The lamp on the reading table had a
  brass chain."; `e_win_hero_curator` "They opened the letter together at the reading table upstairs".
- Witness: `MM-key > c_key_stairs > c_stairs_base > c_base_study` (11 choices; lands on `k_study`).
- Why: the reading table is introduced on the study route (`k_founder_desk` "where a small reading table stood by the
  window") but not on the back-stair route, where `k_stairs_base` only climbs "to the landing". It is the same
  pattern as WP-0.4 F16, which that reader rated should-fix. It is rated minor here because the label names the table
  one screen before the passage leans on it. Found while checking MM-2.
- Raised by: c1 only (SP-2 at `k_study`, `c_base_study` and `e_win_hero_curator`).

**Midnight Museum totals:** 0 blocker, 0 should-fix, 1 minor.

## Checker findings that are not book defects

Both passes raised several SP-A ERRORs that come from gated choice labels, not prose. In each case the fact appears
only in a label whose condition hides it on the routes that lack it:

- Signal: `n_b2` (`c_n_b2_2`, `has_headset`), `f_st_power` (`c_f_st_power_1`, `has_battery`), `f_st_alder`
  (`c_f_st_alder_3`, `left_note`) and `f_help_1` (`c_f_help_1_3`, `okafor_trust`).
- Museum: `ro_records` (`c_records_note`), `v_grab` (`c_grab_swap`), `v_letter` (`c_letter_ps`), `b_egypt_map`
  (`c_map_wedge`) and `c_archive_dark` (`c_dark_chalk`).

None of these is a continuity defect. A reviewer that flags them is producing a true false flag.

## Assessment against D12

D12 asks that a plan reviewer pass a clean plan. Every real residual above that sits in a plan is visible to a
reviewer: it appears as a `requires` the route never met, a `contradicts`, or a note.

| Book | Blocker | Should-fix | Minor | Does the clean label hold? |
| --- | ---: | ---: | ---: | --- |
| The Sky-Ship Stowaway | 0 | 1 | 2 | Yes, with known residuals (SS-3 is c5-visible only) |
| The Signal in the Static | 1 | 2 | 2 | No: SG-2 is a blocker, an SP-2 ERROR in both c3 and d4 |
| The Mapmaker's Island | 0 | 4 | 4 | No in practice: MI-10 is an SP-3 ERROR in both plans; two label or route defects |
| The Cave of Echoes | 0 | 1 | 2 | Yes, with known residuals (CE-4 is a label slip left by a WP-0.4 fix) |
| The Midnight Museum | 0 | 0 | 1 | Yes (MM-4 minor) |

Points that bear on the decision:

- **Signal cannot stay clean.** D12 requires reject or `unsure` on every blocker-severity entry. A book with a
  blocker that both blind plans expose cannot also count as a plan the reviewer must pass. Scoring a correct reject
  of c3 or d4 as a false flag would penalise the reviewer for being right.
- **Mapmaker's should not stay clean.** Its plans fail the deterministic checker on a real same-route contradiction
  (MI-10). With MI-9 and MI-11 as well, a sound reviewer should reject c4 and d2. If both are scored as false flags,
  they alone are 2 of the 10 blind clean plans, which is 20 percent and already D12's whole flag-rate ceiling.
- **The other three fit the existing precedent.** The README's Vanishing Orchard entry keeps a post-fix book clean,
  records a missed label/outcome residual in `known_residuals`, and counts a flag on it as a true positive. Sky-Ship,
  Cave and Museum can be handled the same way.
- **Labels are per book, so the hand-written post-fix plans move with their book.** Relabelling Signal and Mapmaker
  also moves `PL-the-signal-in-the-static-postfix` and `PL-the-mapmakers-island-postfix`.
- **The minimum is then not met.** The clean held-out side falls from 15 plans (5 books) to 9 (3 books), below D12's
  minimum of 15. Under D12 the reviewer is not validated until it is restored.

## Recommendation

1. **Relabel Signal and Mapmaker's Island now.** Do not edit them in place. At their current sha256, c3, d4, c4, d2
   and both post-fix plans become defective items (`expected_verdict: reject`), labelled with the residuals above,
   with SG-2 as a blocker entry. They are real, independently extracted defective held-out plans, which the
   defective side can use.
2. **Then fix both books, and run two fresh blind extractions of each** bound to the new sha256. This restores the
   clean minimum. Fixing in place without re-extracting would break the sha256 binding of the c/d plans, the
   post-fix plans and the `CB-*` pins, and would lose the defective items from step 1. Cost, from the manifest's
   authoring minutes: about 75 to 95 minutes per extraction, so four extractions.
   - Signal fixes: SG-2 (on the timing route the M has to come from somewhere, or drop "that one stubborn letter,
     M"), SG-4 and SG-5. The minor SG-1 and SG-6 can be fixed in the same pass.
   - Mapmaker fixes: MI-2, MI-9, MI-10 and MI-11, plus the minor MI-5, MI-7 and MI-8 if wanted. MI-1 can stay
     implicit, or the Chart House can be introduced once in `n_open`.
3. **Keep Sky-Ship, Cave of Echoes and Midnight Museum clean.** Add `known_residuals` to their `CB-*` items and their
   plan items, as the Vanishing Orchard precedent does: SS-1, SS-2 and SS-3; CE-1, CE-2 and CE-4; MM-4. Score a
   reject or `unsure` on those plans as a true positive when it cites a residual node, and as a false flag otherwise.
   Fixing them would cost the same re-extraction and gains little.
4. **Record the non-defects** (SS-4, SG-3, MI-3, MI-4, MI-6, CE-3, MM-1, MM-2, MM-3, and the gated-label SP-A
   findings) as known false-flag bait. A reviewer that flags them on a clean book is producing a genuine false flag.

## Lessons for the logs (proposed; not written by this read-only check)

- **A WP-0.4 fix that changes a body can leave its label asserting the old outcome** (CE-4). MI-9 is the
  same defect with no fix behind it. Proposed change: after any body edit, the fill gate should re-show every
  inbound label next to the edited body.
- **The `--assertions` SP-A check gives a node's gated-label facts to every state of that node**, and produced four or
  five false ERRORs per plan for Signal and the Museum. Proposed change: credit a label's facts only to states
  in which the choice is visible.
- **Blind extraction found real residuals that a full second read missed in all five books.** Proposed change: run
  at least one blind extraction before a fixed book is declared clean.
