<!-- markdownlint-disable MD038 -- witness routes are code spans wrapped across lines -->

# Residual check of the five fixed held-out books (2026-11-22)

Independent continuity check of every ERROR raised by the ten blind Story Plan extractions of the books fixed on
2026-11-22, in `clean-plans-fixed/plans/{e1..e5,f1..f5}.plan.json` (mapped in `clean-plans-fixed/manifest.json`), and
of the presuppositions and contradictions those extractions recorded in `requires`, `contradicts` and
`provenance.notes`. Read-only: no book, plan or assertion file was changed. (Written to the repo by the orchestrator from the checker agent's saved copy.) It mirrors
[residuals-2026-11-21.md](./residuals-2026-11-21.md) in method, severity scale and classes. Each book was verified
against the sha256 that both of its extractions bind; all ten match.

| Book | sha256 (prefix) | Plans |
| --- | --- | --- |
| `out/the-signal-in-the-static.filled.json` | `2636ac09b732` | e1, f3 |
| `out/the-midnight-museum.filled.json` | `af54082e1ac3` | e2, f5 |
| `out/the-mapmakers-island.filled.json` | `ce7e80a923c4` | e3, f4 |
| `out/the-cave-of-echoes.filled.json` | `a4a7c0903915` | e4, f1 |
| `out/the-sky-ship-stowaway.filled.json` | `3621f39c156a` | e5, f2 |

The fix records are `fixes-2026-11-22-<slug>.md` in this folder.

## Method

- The checker output of each plan (`scripts/check_story_plan.py <book> <plan> --json --assertions <file>`, run before
  this check) was read in full: 145 ERRORs (Signal 5 and 13, Museum 21 and 7, Mapmaker's 47 and 43, Cave 0 and 0,
  Sky-Ship 5 and 4). Every ERROR is assigned to one group below; the per-plan tally is at the end. WARNINGs were read
  too: all are cross-route SP-3 pairs, SP-8 or SP-D advisories, and none is a continuity defect.
- Each book's previous version (the 2026-11-21 sha256) was taken from git and diffed node by node. Only the nodes the
  fix records name changed, so a 2026-11-21 verdict on any other node still stands on unchanged text.
- For every suspect, a breadth-first search over `StoryEngine` configurations (`start`, `visible_choices`, `choose`,
  honouring conditions and effects) looked for a route that reaches the node with no earlier body passed through, and
  no label taken, that introduces the fact. The shortest such route is the witness. Route counts below come from an
  exhaustive memoised walk of the same engine and count distinct choice sequences from `n_open` to the node's first
  entry.
- All nine witnesses for real defects were replayed from `n_open` by script: every choice was visible in turn, each
  route lands on the named node, and every quotation was matched verbatim against the node body or one of its labels.
- Raised by: "both" means each pass recorded the suspect at that node; "e1" or "f4" (and so on) names the one pass
  that did. Severity follows the 2026-11-21 scale: **blocker** is a plain contradiction or a fact false on the route,
  **should-fix** an unshown presupposition or a label that contradicts its outcome, **minor** a small wording slip.

### Artifact kinds

- **Gated label** (lesson AL-858): the fact appears only in a choice label, or only in a choice's condition, that is
  hidden from the states lacking it, yet the per-node assertion map credits it to every state of the node.
- **Label option** (new variant of AL-858, Mapmaker's e3 only): an ungated label proposes an action ("Pocket the
  locket", "Take the working compass"). The plan records the fact as that choice's `establishes`, but the assertion
  map also lists it at the offering node, so SP-A reports it for the readers who have not yet chosen.
- **Scoped negation** (convention 1): a negation scoped to a character's knowledge or to "the world", or a lack that a
  later passage changes, recorded as contradicting the later fact.
- **Plan wording**: an SP-9 denylist hit on the plan's own strings, not on the book's prose.
- **Introduced in place** (reported as "not a defect"): the passage states the fact in words a first-time reader can
  learn it from, but the extractor recorded it at that node as a `requires` or assertion instead of an `establishes`.

## Witness shorthands

- `MM-key` = `c_open > c_desk_map > c_desk_map_go > c_start_gems > c_gems_case > c_gems_vitrine > c_vitrine_go >
  c_corridor_key` (lands on `n_key`), as in the 2026-11-21 report.
- `SG-rel` = `c_open > c_n_shelf_1 > c_n_shelf_battery_1 > c_n_start_2` (lands on `r_relay_1`).

## Verdicts at a glance

Real defects take new ids continuing the 2026-11-21 series. Groups of non-defects use local ids (S, M, P, K).

| ID | Book | Node(s) | Verdict | Class or kind | Raised by |
| --- | --- | --- | --- | --- | --- |
| SG-7 | Signal | `r_relay_beat` | real: minor | `unestablished_fact_on_route` | f3 |
| SG-8 | Signal | `r_relay_1` (and `r_relay_beat`) | real: minor | `unestablished_fact_on_route` | f3 |
| S1 | Signal | `r_no_freq` against `e_st_note` | artifact | scoped negation | both |
| S2-S5 | Signal | `n_b2`, `f_st_power`, `f_st_alder`, `f_help_1` | artifact | gated label | both |
| S6 | Signal | `n_b3` | artifact | gated label (condition only) | f3 |
| S8 | Signal | `m_numbers_1` | not a defect | SG-1 fix holds | f3 (e1 note) |
| S10 | Signal | `n_b2_choice` | not a defect | already adjudicated, SG-3 | f3 |
| S11 | Signal | `e_he_safe` | not a defect | introduced in place | f3 |
| S12 | Signal | `mm_count_tide` against `f_he_act` | not a defect | rounding | e1 note |
| S13 | Signal | `mm_count_extrap` against `mm_count_clock` | not a defect | sibling branches | f3 note |
| MM-5 | Museum | `e_win_mystery_solved` | real: minor | `unestablished_fact_on_route` | e2 |
| M1 | Museum | `v_letter`, `v_letter_ps`, label `c_letter_ps` | not a defect | already adjudicated, MM-2 | e2 |
| M3 | Museum | `e_win_hero_curator` | not a defect | supported by `n_vault` | e2 |
| M4 | Museum | plan strings (`wound`) | artifact | plan wording | both |
| M5-M10 | Museum | six nodes, listed in the Museum section | artifact | gated label | split |
| M11 | Museum | notes (curator, key, Pym, Row Q, letter split) | not a defect | MM-1, MM-3 or plan only | split |
| MI-12 | Mapmaker | `e_tw_log` | real: minor | `unestablished_fact_on_route` | both |
| MI-13 | Mapmaker | `cf_bench` | real: minor | `unestablished_fact_on_route` | e3 |
| MI-14 | Mapmaker | `tf_gap` | real: minor | `unestablished_fact_on_route` | e3 |
| MI-15 | Mapmaker | `tf_gully` label `c_tf_gully_1` | real: minor | `unestablished_fact_on_route` | e3 |
| MI-16 | Mapmaker | `L_cove` body and label `c_L_cove_1` | real: minor | `unestablished_fact_on_route` | f4 |
| MI-17 | Mapmaker | `mg_blind` | real: minor | `unestablished_fact_on_route` | f4 |
| P1 | Mapmaker | Alder's tools and mirror, 13 nodes | not a defect | already adjudicated, MI-3 | both |
| P2 | Mapmaker | `ship_turns` "lost mapmaker" | not a defect | already adjudicated, MI-4 | both |
| P3 | Mapmaker | the cove at four nodes | not a defect | already adjudicated, MI-6 | both |
| P4 | Mapmaker | `L_cove` against `camp_chart` | artifact | scoped negation | e3 |
| P8 | Mapmaker | `tf_cliffgap` | not a defect | introduced by every parent | e3 |
| P9 | Mapmaker | 12 label-option nodes | artifact | label option | e3 |
| P11 | Mapmaker | `e_ch_alder_name` | not a defect | `ch_sign` on every route | f4 |
| P12 | Mapmaker | `ch_seal_final` "signed" | not a defect | signing label on every route | f4 |
| P14 | Mapmaker | `e_tw_note` | not a defect | `tw_fuelstore` on every route | f4 |
| P15 | Mapmaker | notes ("oldest map", "the ridge camp", animals) | not a defect | cross-route or own text | e3 note |
| K1 | Sky-Ship | `e_set_nest` "the lookout" | not a defect | introduced in place | e5 |
| K2, K4 | Sky-Ship | `b_steer1`, `b_patch1` | artifact | gated label (condition only) | e5 |
| K3 | Sky-Ship | `b_steer_ok` | not a defect | introduced in place | e5 |
| K5 | Sky-Ship | `e_win_discovery` | not a defect | SS-1 fix holds | f2 |
| K6 | Sky-Ship | `p_save1` against `p_save_b` | artifact | scoped negation (state change) | f2 |
| K7 | Sky-Ship | `n_secret` | not a defect | introduced in place | f2 |

The Cave of Echoes raised no ERROR in either pass and no note that names a presupposition or contradiction.

## The Signal in the Static

**SG-7. `r_relay_beat`: "a station the county shut down".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "Nobody leaves a lamp burning in a station the county shut down."
- Witness: `SG-rel > c_r_relay_1_1 > c_r_re_path_1 > c_r_re_gap_1` (7 choices). All 10 routes into the node lack it.
- Why: the sibling of SG-6. The 2026-11-21 fix replaced "when the county did" at `r_re_hut`, but this sentence sits
  one or two screens later on the same relay route, which never says who ran or closed the station (`n_start` only
  says it "has stood dark for as long as she can remember"). The county is introduced as it goes and a reader infers
  an abandoned public site, so it stays minor, the same rating SG-6 had. Text unchanged since 2026-11-21; the earlier
  check missed it.
- Raised by: f3 only (SP-2 and SP-A `county_closed_relay`, plus a note).
- Fix: before "Nobody leaves a lamp burning in a station the county shut down."; after "Nobody leaves a lamp burning
  in a station that has stood dark for years."

**SG-8. `r_relay_1`: "the loop in her earbuds".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "The loop in her earbuds is so loud that she turns it down." (`r_relay_beat` repeats "the loop in her
  earbuds".)
- Witness: `SG-rel` (4 choices). Both routes into the node lack it.
- Why: on the relay route nothing has said that Wren carries a receiver; until now she has heard the loop only on the
  attic shortwave. The coordinates route introduces the device in words ("Wren clips her handheld radio to her belt",
  `r_coord_1`); the relay route takes it for granted. The possessive lets a reader infer a portable set, so minor.
  Text unchanged since 2026-11-21.
- Raised by: f3 only (SP-A `loop_on_handheld`).
- Fix: before "The loop in her earbuds is so loud that she turns it down."; after "The loop in the earbuds of her
  handheld radio is so loud that she turns it down."

**S1. `r_no_freq` "not one of them ever ... answered him" against `e_st_note`.** Artifact: scoped negation.

- Quotes: `r_no_freq` "As far as Wren can tell from forty years of cards, not one of them ever picked up a microphone
  and answered him." `e_st_note`: "Two dots, every midnight, for twenty years, and I took it for a fault in the set".
- Why: the negation is scoped to what the postcards show Wren, and Kell himself never recognised the two dots as an
  answer. Both facts are true together. Raised by both (e1 `nobody_answered`, f3 `no_listener_answered`, SP-3 each).

**S2 to S5. Gated labels.** Artifact: gated label. Each fact appears only in a label hidden from the states without it:
`n_b2` `c_n_b2_2` "Press his headset tight and listen under the voice." (`has_headset == True`); `f_st_power`
`c_f_st_power_1` "Splice in Grandpa's spare battery." (`has_battery == True`); `f_st_alder` `c_f_st_alder_3` "Tell him
the note in his door was hers." (`left_note == True`); `f_help_1` `c_f_help_1_3` "Ring Mrs. Okafor at the marina."
(`okafor_trust == True`). These are the four the 2026-11-21 report listed. Raised by both.

**S6. `n_b3` `note_left`.** Artifact: gated label (condition only). Neither the body nor a label mentions the note;
f3 credited the condition of `c_n_b3_2` (`left_note == True`), whose label is "Keep listening after the tape clicks
off." Raised by f3 only.

**S8. `m_numbers_1` "fetched down from a cedar trunk".** Not a defect. The SG-1 fix holds: the passage introduces the
trunk with "a cedar trunk in the attic". f3 recorded the fact as `requires` with its own definite wording ("taken from
the cedar trunk"); e1 left a note that does not apply to the fixed sentence. Raised by f3 (SP-2, SP-A) and an e1 note.

**S10. `n_b2_choice` "the count running down".** Not a defect: SG-3, text unchanged. Raised by f3 only.

**S11. `e_he_safe` "The HOLD switch, under the red guard".** Not a defect: introduced in place by the old man's own
line. e1 recorded `hold_switch` as established at this node. Raised by f3 only (SP-A).

**S12. Tide peak "eighteen minutes to midnight" against "Twenty to midnight is the top of a spring tide".** Not a
defect. `mm_count_tide` gives the peak to the minute; the very next node on that route (`mm_count_warn`) and the
officer in `f_he_act` round it to twenty to midnight, the hour the count ends. 420 of 2,520 routes into `f_he_act`
read both. e1 recorded it as one fact in a note, not as a contradiction. An optional harmonising edit would be "it
tops out at twenty to midnight".

**S13. `mm_count_extrap` "has not put a timer" against `mm_count_clock` "PLAY TAPE 2, THEN ERASE ALL".** Not a defect:
the two are sibling choices into `n_b3`, and no reading crosses both (an SP-3 warning). Raised in an f3 note.

**Signal totals:** 0 blocker, 0 should-fix, 2 minor.

## The Midnight Museum

**MM-5. `e_win_mystery_solved`: "the portrait of old Ellery".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "a new brass plate hung under the portrait of old Ellery".
- Witness: `MM-key > c_key_display > c_display_force > c_force_careful > c_careful_cipher > c_cipher_stars >
  c_stars_dome > c_dome_rotunda > c_rot_align > c_align_set > c_set_vault > c_vault_letter > c_letter_reveal >
  c_reveal_more > c_reveal_end` (22 choices). 2,700 of the 4,320 routes into the ending never see the portrait.
- Why: the portrait is shown only in `k_founder` and `k_founder_portrait` (the study route). The display-case and
  back-stair routes reach this ending without it, and the definite article presumes it. A founder's portrait in his
  own museum is easy to infer, so minor, the same pattern as CE-1. Text unchanged since 2026-11-21; neither earlier
  pass raised it.
- Raised by: e2 only (SP-2 and SP-A `founder_portrait`, plus a note).
- Fix: before "a new brass plate hung under the portrait of old Ellery"; after "a new brass plate hung under a
  portrait of old Ellery".

**M1. "The founder's glasses" (`v_letter`, `v_letter_ps`, label `c_letter_ps`).** Not a defect: MM-2. `k_stairs_base`
changed since then, but only by the MM-4 clause appended to its last sentence; the cupboard still holds "a rolled
chart, brittle at the edges, and a pair of round glasses with thick lenses", so MM-2's reasoning holds. The SP-A at
`v_letter` is also a gated label (`c_letter_ps`, `has_glasses == True`). Raised by e2 only (two SP-2, two SP-6, two
SP-A, and a note).

**M3. `e_win_hero_curator`: "Old Ellery had not sold the town's treasures".** Not a defect. No route into the ending
states the town's accusation (0 of 3,240 routes reach it after "sold", "thief" or "stole"), but `n_vault` is on every
route, and there Ellery says "I only hid it from men who meant to sell it by the pound". The ending's line reports
the letter the curator has just read aloud in the scene, and is true on the route. Raised by e2 only.

**M4. SP-9 on the plans' "wound".** Artifact: plan wording. e2 `brass_wren` ("sings and bows when wound"),
`ro_workshop` ("waits to be wound") and `e_win_owl_witness` ("the wound owl"); f5 `wren_sings` ("The wound wren") and
`e_win_secret_workshop` ("The wound wren"). The book uses "wound" only for winding: "Nadia wound the brass wren",
"Nadia wound the key three turns", and stairs that "wound down". Raised by both.

**M5 to M10. Gated labels.** Artifact: gated label, each confirmed against its label and condition:

| Group | Node | Label | Condition | Raised by |
| --- | --- | --- | --- | --- |
| M5 | `b_egypt_map` | `c_map_wedge` "Wedge the gallery door open, then duck under the rope." | `read_back` | both |
| M6 | `c_archive_dark` | `c_dark_chalk` "Chalk an arrow on every shelf end and go on in the dark." | chalk | both |
| M7 | `ro_records` | `c_records_note` "Unfold the crossword with NADIA printed on it." | `has_chalk` | both |
| M8 | `v_letter` | `c_letter_ps` "Read the row of ants through the founder's glasses." | `has_glasses` | both |
| M9 | `v_map` | `c_map_back` "Turn the whole map over." (condition only for the half sentence) | `read_back` | e2 |
| M10 | `v_grab` | `c_grab_swap` "Press the brass token into the hollow." | `has_token` | both |

M5, M6, M7, M8 and M10 were listed as false flags on 2026-11-21. M7's `crossword_nadia` fails in all 8 states only
because no plan establishes it before the gated label.

**M11. Museum notes.** Not defects. f5 on the curator (MM-1) and the brass key on the guard's desk (MM-3): text
unchanged. f5 on Pym: he is named by his badge (`e_set_alarm`) or his signed note (`ro_records_note`), and 0 routes
reach `ro_pym` without one of them. e2 on Row Q (an introduction) and `phone_has_signal`, and f5 on the split letter
facts: plan modelling only.

**Museum totals:** 0 blocker, 0 should-fix, 1 minor.

## The Mapmaker's Island

**MI-12. `e_tw_log`: Alder named as if known.** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "The logbook was Alder's, and Wren read the last entry twice to be sure."
- Witness: `c_open > c_n_start_4 > c_tw_enter_1 > c_tw_ground_1` (4 choices; the only route into the ending).
- Why: on this route the logbook (`tw_ground`) is the first trace of anyone, and no passage has named Alder. Every
  other first mention in the book introduces the name ("a name, Alder", "A mapmaker named Alder"); this one alone
  treats it as known. The ending then calls Alder "the lost mapmaker", so the reader can work out that Alder kept the
  log, and the possessive reads as an introduction of ownership. Minor, though it is the closest of these to
  should-fix, being a person rather than a place. Text unchanged since 2026-11-21.
- Raised by: both (e3 `alder_name`, f4 `alder_named`, SP-2 and SP-A each).
- Fix: before "The logbook was Alder's, and Wren read the last entry twice to be sure."; after "The logbook had been
  kept by a mapmaker named Alder, and Wren read the last entry twice to be sure."

**MI-13. `cf_bench`: "The grassy bench".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "The grassy bench was the ridge's broad shoulder, and up here the wind was a live thing."
- Witness: `c_open > c_n_start_2 > c_cf_enter_2 > c_cf_traverse_2 > c_cf_upper_1` (5 choices; 15 of 33 routes).
- Why: the parents `cf_ledge` and `cf_shelf` arrive "onto a broad grassy bench", but `cf_upper` (label "Climb the
  faint path on.") does not, and on the `cf_dellcarve` routes the only bench met is the carved one in the dell. The
  apposition defines the bench, so minor.
- Raised by: e3 only. Fix: before "The grassy bench was the ridge's broad shoulder"; after "A grassy bench formed the
  ridge's broad shoulder".

**MI-14. `tf_gap`: "The green gap".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "The green gap was the mouth of a valley, where a stream came tumbling down to meet the sea."
- Witness: `c_open > c_n_start_5 > c_tf_enter_2 > c_tf_channel_2` (4 choices; 5 of 6 routes).
- Why: only `tf_sketchrun` ("a green gap opened in the shoreline") introduces it. From `tf_channel` the label is "Cut
  inland up a firm rise."; from `tf_bottle` it is "Set out inland for the ridge camp." Self-defining, so minor.
- Raised by: e3 only. Fix: before "The green gap was the mouth of a valley"; after "A green gap in the shoreline was
  the mouth of a valley".

**MI-15. `tf_gully` label: "the cliff gap".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: label `c_tf_gully_1` "Hurry through the gully to the cliff gap."
- Witness: `c_open > c_n_start_5 > c_tf_enter_4 > c_tf_mussel_2` (4 choices; the only route into `tf_gully`).
- Why: `tf_mussel` and `tf_gully` point the gully "toward the cliffs" but never mention a gap; the label is its first
  mention on this route, with a definite article. `tf_cliffgap` then explains it ("a slot of dark wet sand"). Every
  other parent of `tf_cliffgap` introduces the gap, so the fix belongs in `tf_gully`, not in the label.
- Raised by: e3 only (SP-2 on the choice, SP-A at the node). Fix: before "The deep gully cut a shortcut straight
  toward the cliffs, its floor still just dry."; after "The deep gully cut a shortcut straight toward a gap in the
  cliffs, its floor still just dry."

**MI-16. `L_cove`: "the spring".** Real: minor. Class `unestablished_fact_on_route`.

- Quotes: "Map the cove and climb the rill toward the spring, follow the compass rose up toward the ridge, search the
  tide pools and sea cave, or rest a while in the calm." and label `c_L_cove_1` "Map the cove, then climb the rill
  toward the spring."
- Witness: `c_open > c_n_start_3 > c_cv_enter_2 > c_cv_glitter_2 > c_cv_deepglow_1` (5 choices; 22 of 34 routes).
- Why: the passage shows "A thread of fresh water trickled down one rock wall", the rill, but no spring has been
  named on the cave, tower or flats routes into it. The same slip as MI-7, which fixed two other "the spring" sites
  and left this one. The 2026-11-21 report noted that c4 flagged the `L_cove` label but gave it no verdict.
- Raised by: f4 only (SP-2 and SP-A `spring_above`). Fix: "toward the spring" becomes "toward its spring" in both the
  body sentence and the label.

**MI-17. `mg_blind`: "the seep".** Real: minor. Class `unestablished_fact_on_route`.

- Quote: "A plank walk ran off the back of the blind toward firmer ground and the seep that climbed inland."
- Witness: `c_open > c_n_start_1 > c_mg_enter_3 > c_mg_creek_3 > c_mg_heron_1` (5 choices; both routes into it).
- Why: `mg_heron` and `mg_blind` never mention a seep. WP-0.4 changed `mg_seep`, the next node, to "A seep" for this
  reason; this earlier sentence on the same route kept the definite article.
- Raised by: f4 only (SP-2 and SP-A `seep_inland`). Fix: before "and the seep that climbed inland"; after "and a seep
  that climbed inland".

**P1. Alder's tools and mirror.** Not a defect: MI-3, text unchanged (none of the 13 nodes changed). Re-verified on the
fixed book: 0 routes reach `L_summit`, `summit_signal`, `signal_aim`, `signal_flash`, `ship_turns` or `race_down`
without an earlier "mirror", and 0 reach `camp_summitpath`, `ch_sightings`, `ch_ink`, `ch_farshore` or
`summit_signal` without "spyglass", "pens" or "tools" (`L_camp` lays them out on every route, and `camp_summitpath`
says "with Alder's chart and tools carried safe"). e3's note repeats MI-3's question about the `c_L_camp_3` route,
which MI-3 answered. Raised by both (e3 `wren_carries_alder_tools`; f4 `camp_tools_held` and `mirror_held`).

**P2. `ship_turns` "a lost mapmaker's mirror".** Not a defect: MI-4, text unchanged. f4's fact text adds "a storm
took the boat and the ship came too late", which the passage does not say. Raised by both.

**P3. The cove at `summit_signal`, `ship_turns`, `race_down` and `meet_boat`.** Not a defect: MI-6, text unchanged.
`meet_boat` was not named then; it follows `race_down` ("toward the cove") on its only route. 0 routes reach any of
the four without an earlier "cove". Raised by both.

**P4. `L_cove` "a place no chart had ever shown to the world" against `camp_chart` "the reef and cove fixed with
care".** Artifact: scoped negation. The negation is scoped "to the world": Alder's chart lies unpublished at the
camp, and `L_cove` goes on "It felt like a secret kept for whoever was lucky enough to find it." Raised by e3 only
(SP-3 and a note).

**P8. `tf_cliffgap` "The cliff gap".** Not a defect: all four parents name it first (`tf_channel` "that cliff gap",
the `tf_gully` label, `tf_cargo`, `tf_deck`); 0 of 13 routes lack it. Raised by e3 only.

**P9. Label options.** Artifact: label option. In each case the fact is the action of one ungated label, and e3
records it as that choice's `establishes` and also lists it in the node's assertions:

| Node | Label (choice) | Fact |
| --- | --- | --- |
| `mg_turtle_note` | "Mark the turtle and press on inland." (`c_mg_turtle_note_1`) | `wren_marked_oyster_turtle` |
| `cf_box` | "Pocket the locket and hurry on." (`c_cf_box_2`) | `wren_keeps_locket` |
| `cv_pup` | "Mark the pup and climb toward the light." (`c_cv_pup_1`) | `wren_marked_cave_pup` |
| `tw_salvage` | "Take the alidade inland toward the ridge." (`c_tw_salvage_1`, `_2`) | `wren_has_tower_find` |
| `tw_tube` | "Follow the draft toward the ridge camp." (`c_tw_tube_1`) | `wren_has_tower_find` |
| `L_camp` | "Take Alder's chart and start for the summit." (`c_L_camp_3`) | `wren_carries_alder_chart` |
| `camp_chart` | "Take up the tools and ready to finish it." (`c_camp_chart_1`) | `wren_carries_alder_tools` |
| `camp_trunk` | "Gather the tools and ready to climb on." (`c_camp_trunk_1`) | `wren_carries_alder_tools` |
| `tw_seachest` | "Take the working compass and climb on." (`c_tw_seachest_1`) | `wren_took_compass` |
| `tf_seals` | "Mark the tangled pup to send help later." (`c_tf_seals_1`) | `wren_marked_net_pup` |
| `cove_seacave` | "Take Alder's pencil and climb the cove path." (`c_cove_seacave_1`) | `wren_took_alder_pencil` |
| `tw_cache` | "Take the tools and the letter and climb the stair." (`c_tw_cache_1`) | `wren_took_brass_tools` |

f4 followed its own stated rule ("Choice labels that take an object ... record the possession as choice
establishes") and kept them out of its assertions, which is why f4 raised none of these.

**P11. `e_ch_alder_name` "the promise kept".** Not a defect: `ch_sign` is on every route into the ending (41,728) and
says Alder left the banner empty "as if the naming were meant for whoever finished it". Raised by f4 only.

**P12. `ch_seal_final` "The masterwork was drawn and signed".** Not a defect: both parents of `ch_sign` offer only a
signing label, `c_ch_ink_1` "Sign the finished masterwork." or `c_ch_pencil_1` "Sign the detailed masterwork.", so
every one of the 41,728 routes has signed. f4 recorded `chart_signed` only at `e_ch_survey`. Raised by f4 only. Left
as found (agency, control rule): the label `c_ch_sign_3` "Ring the margins with the island's living things." leads to
a passage that offers that same choice again.

**P14. `e_tw_note` "the lost mapmaker's story".** Not a defect: `tw_fuelstore`, its only parent, shows Alder's note
("Gone to finish the ridge chart") and signature. Raised by f4 only.

**P15. e3 notes.** Not defects. "The oldest map of all" at `cv_ochre` and `e_star_map` sits on routes no reading
crosses (an SP-3 warning). The separate turtles and pups are a modelling choice. On the note that Alder and the ridge
camp are used as known: a scan of every passage naming Alder found 19 first mentions on some route, and 18 introduce
the name ("a name, Alder"); only MI-12 does not. "The ridge camp" at `tw_tube`, `tf_bottle` and `e_tw_log` is Alder's
own reference inside the message that introduces the camp, and the ridge itself is seen from `n_start` on every route.

**Mapmaker's Island totals:** 0 blocker, 0 should-fix, 6 minor.

## The Cave of Echoes

Both passes produced 0 ERRORs; the only findings are SP-3 warnings on routes no reading crosses (turn-back endings
against forward routes, coin box against compass). Neither pass's notes name a presupposition. The four fixed sites
read as the fix record says: "imagines how a museum will react", "picturing a museum polishing", "her rockpool club
back home", label `c_da_out` "Follow Biscuit out.". CE-3 is unchanged and still not a defect. f1's note that Biscuit
is never called a dog is not a defect (tail, paws and a bark make it plain).

**Cave of Echoes totals:** 0 blocker, 0 should-fix, 0 minor.

## The Sky-Ship Stowaway

**K1. `e_set_nest` "the lookout".** Not a defect: introduced in the scene ("bellowed a voice above. Two big hands
hauled her over the rail of the crow's nest, and the lookout wrapped her in his own thick coat"), and a ship's
lookout is a standing role, as the purser was in SS-4. Raised by e5 only (SP-2, SP-A).

**K2 and K4. `b_steer1`, `b_patch1`.** Artifact: gated label (condition only). `b_steer1` `c_steer_purr` "Hold Pip up
to the tube." (`fed_pip == True`) says nothing of sardines; at `b_patch1` both rigging labels read "Climb the rigging
to the tear." and differ only in `knows_ropes`, while the body only asks "Have you ever crossed live rope?". Pip rides
in Bree's coat on all 12 configurations into `b_steer1`. Raised by e5 only.

**K3. `b_steer_ok` the three-note hum.** Not a defect: introduced in place ("She kept it soft, three notes going down
like steps"), and the "familiar hoooom" follows `n_secret` ("Hoooom," he sang) on every route. The passage never says
"our song". Raised by e5 only.

**K5. `e_win_discovery` "Forty buckets of it, every day".** Not a defect: the SS-1 fix holds, and the line now states
the buckets. f2's fact text adds "for cargo, on the captain's orders" from `f_galley1`, which this passage does not
assert. Raised by f2 only (SP-2, SP-A).

**K6. `p_save1` strap pins the fin against `p_save_b` fin freed.** Artifact: scoped negation (a state that changes):
`p_save1` "one strap had twisted tight around his left fin, pinning it flat", then `p_save_b` "the strap slid free".
Raised by f2 only (SP-3).

**K7. `n_secret` "a storm they only half understood".** Not a defect: introduced in place. Raised by f2 only (SP-A).

The three fixed sites (SS-1, SS-2, SS-3) were re-read and none raised a finding in either pass.

**Sky-Ship totals:** 0 blocker, 0 should-fix, 0 minor.

## ERROR tally

| Plan | ERRORs | Real | Not defect | Adjudicated | Gated | Option | Scoped | Wording |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| e1 Signal | 5 | 0 | 0 | 0 | 4 | 0 | 1 | 0 |
| f3 Signal | 13 | 3 | 3 | 1 | 5 | 0 | 1 | 0 |
| e2 Museum | 21 | 2 | 2 | 6 | 8 | 0 | 0 | 3 |
| f5 Museum | 7 | 0 | 0 | 0 | 5 | 0 | 0 | 2 |
| e3 Mapmaker's | 47 | 8 | 2 | 24 | 0 | 12 | 1 | 0 |
| f4 Mapmaker's | 43 | 6 | 6 | 31 | 0 | 0 | 0 | 0 |
| e4 Cave | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| f1 Cave | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| e5 Sky-Ship | 5 | 0 | 3 | 0 | 2 | 0 | 0 | 0 |
| f2 Sky-Ship | 4 | 0 | 3 | 0 | 0 | 0 | 1 | 0 |
| **Total** | **145** | **19** | **19** | **62** | **24** | **12** | **4** | **5** |

Columns: real (minor), not a defect, already adjudicated, then the artifact kinds gated label, label option,
scoped negation and plan wording.

The 19 ERRORs on real defects are 9 distinct minor defects (an SP-2 and an SP-A usually name the same one). "Already
adjudicated" is SG-3, MM-2, MI-3, MI-4 and MI-6, all on unchanged text. 100 of the 145 ERRORs (69 percent) are
artifacts or already-adjudicated non-defects.

## Bottom line per book

| Book | Blocker | Should-fix | Minor | Verdict | Minors |
| --- | ---: | ---: | ---: | --- | --- |
| The Signal in the Static | 0 | 0 | 2 | clean | SG-7, SG-8 |
| The Midnight Museum | 0 | 0 | 1 | clean | MM-5 |
| The Mapmaker's Island | 0 | 0 | 6 | clean | MI-12 to MI-17 |
| The Cave of Echoes | 0 | 0 | 0 | clean | none |
| The Sky-Ship Stowaway | 0 | 0 | 0 | clean | none |

Every blocker and should-fix from 2026-11-21 is gone: SG-2, SG-4, SG-5, MI-2, MI-9, MI-10, MI-11, SS-3 and CE-4 raise
nothing in either pass, and no new blocker or should-fix appeared. What remains is definite-article and naming slips,
all nine on text unchanged since 2026-11-21. Three (SG-7, MI-16, MI-17) are siblings of sites that an
earlier fix corrected: the same presupposition on the same route, left behind.

If the minors are recorded rather than fixed, they belong in `known_residuals` for these books' plan items, in the
Vanishing Orchard manner. A reject or `unsure` citing SG-7, SG-8, MM-5 or MI-12 to MI-17 is then a true positive;
one citing any group above marked artifact, not a defect or already adjudicated is a false flag.

## Proposed minimal fixes

Mapmaker's is a control book: each fix below is a continuity wording change with no effect on choices, conditions,
effects or endings, and the `ch_seal_final` re-offer is left alone as agency.

| ID | Node | Before | After |
| --- | --- | --- | --- |
| SG-7 | `r_relay_beat` | "in a station the county shut down." | "in a station that has stood dark for years." |
| SG-8 | `r_relay_1` | "The loop in her earbuds" | "The loop in the earbuds of her handheld radio" |
| MM-5 | `e_win_mystery_solved` | "hung under the portrait of old Ellery" | "hung under a portrait of old Ellery" |
| MI-12 | `e_tw_log` | "The logbook was Alder's," | "The logbook had been kept by a mapmaker named Alder," |
| MI-13 | `cf_bench` | "The grassy bench was the ridge's" | "A grassy bench formed the ridge's" |
| MI-14 | `tf_gap` | "The green gap was the mouth" | "A green gap in the shoreline was the mouth" |
| MI-15 | `tf_gully` | "straight toward the cliffs, its floor" | "straight toward a gap in the cliffs, its floor" |
| MI-16 | `L_cove` body | "climb the rill toward the spring" | "climb the rill toward its spring" |
| MI-16 | `c_L_cove_1` label | "then climb the rill toward the spring." | "then climb the rill toward its spring." |
| MI-17 | `mg_blind` | "and the seep that climbed inland." | "and a seep that climbed inland." |

Each changes only words, so the shape hash is unchanged. A fix pass should re-run FK grade on `r_relay_1` and
`e_tw_log`, which grow by a few words, and then re-run the term scan described in the second lesson below.

## Lessons for the logs (proposed; not written by this read-only check)

1. **Category:** validator. **Lesson:** SP-A false ERRORs come from where a fact sits, not only from gated labels:
   ungated label options recorded as choice `establishes` (12 in e3), and gated choices whose condition, not their
   words, carries the fact (`n_b3`, `b_steer1`, `b_patch1`, `v_map`). The assertion file cannot say which, because it
   is keyed by node alone. **Proposed change:** extend AL-858 by letting the assertion file give each fact's source
   (body or choice id). SP-A then credits a choice's facts only to states where it is visible, skips facts the plan
   records as that choice's `establishes`, and rejects a choice-sourced fact whose label does not state it.
2. **Category:** authoring. **Lesson:** residual fixes are made per site, and sibling sites with the same
   presupposition on the same route survive: SG-6 fixed `r_re_hut` but not `r_relay_beat`; MI-7 fixed two "the
   spring" sites but not `L_cove`; WP-0.4 fixed `mg_seep` but not `mg_blind` one node earlier. **Proposed change:**
   before a residual fix is closed, scan every body and label for the fixed fact's key term and run a route-miss check
   (is the node reachable with no earlier introduction?) on each hit. Ship the scan as a script; a prototype is
   `rc/scan.py` in this check's scratchpad.
3. **Category:** validator. **Lesson:** 9 of 145 ERRORs were facts a passage introduces in its own words, which the
   extractor recorded there as `requires` or as an assertion without `establishes` because an earlier node on another
   route establishes them (`m_numbers_1`, `e_he_safe`, `e_set_nest`, `b_steer_ok`, `e_win_discovery`, `n_secret`). The
   checker cannot tell this from a presupposition, and its message does not show the sentence. **Proposed change:** add
   an extraction-prompt rule that a passage which states a fact so a first-time reader learns it establishes that fact,
   even if another node does too; and have SP-2 and SP-A quote the node's sentence that matches the fact, so a reviewer
   can judge in-place introduction at a glance.

The SP-9 hits in M4 ("the wound wren", "when wound", "to be wound") are further evidence for the open AL-831 rather
than a new lesson: the winding mask still misses a determiner before an automaton noun, and the passive "when wound"
and "to be wound".
