<!-- markdownlint-disable MD029 -- findings keep one running number so cross-references hold -->

# WP-0.4 second-reader findings: the-mapmakers-island (control book)

- **Book:** `out/the-mapmakers-island.filled.json`, id `sk_mapmakers_island`, 225 nodes, 72 endings, band 10-13.
- **Pre-fix revision:** `846d9fc` (sha256 `b2d5a0dc960979c4f08bbe0bc770a9d965c6ec9ed9ada47fa968b866b2973d91`), the file
  the WP-0.3 plan was written against.
- **Status:** CONTROL book (D3, 2026-11-21). Only continuity defects are fixed. Agency problems are recorded at the end
  and left open by design.
- **Reader:** WP-0.4 second reader (did not write the plan), 2026-11-21. (Written to the repo by the orchestrator from
  the reader's report, because the harness refused the reader's own write of this file.)

## Method

The book declares no variables, so every reachable configuration is `(node, {})`. A breadth-first walk with
`StoryEngine` (`start()`, `visible_choices()`, `choose()`) reached 225 configurations over 301 choice edges, which is
every node. I read every passage and label against what the reader can know on entry along every route. Known-on-entry
was computed exactly as a dataflow over the DAG: the guaranteed set at a node is the intersection, over all incoming
edges, of (guaranteed set at the parent, plus the parent's `establishes`, plus the choice's plant). I checked every
plan `requires` against that set and every `contradicts` against the union set, and read the prose for anything the
plan did not model. The plan's `provenance.continuity_notes` were the starting leads; each was re-verified, and the
read added several the notes missed (marked NEW).

Routes are choice ids from `n_open`. Two long routes recur:

- **R-camp** (reaches the camp having met no Alder clue and no camp clue):
  `c_open > c_n_start_4 > c_tw_enter_3 > c_tw_cellar_2 > c_tw_supplies_1 > c_cf_campapproach_1 > c_camp_ascent1_1 >
  c_camp_ascent2_1 > c_camp_ascent3a_1 > c_camp_ascent4_1` (enters `camp_ascent5`).
- **R-summit** = R-camp `> c_camp_ascent5_1 > c_L_camp_3 > c_camp_summitpath_1 > c_ridge_notch_1 > c_wind_gap_1`
  (enters `L_summit` having skipped the table and the trunk).

State is `{}` on every route. Every quote below is verbatim from the pre-fix file.

## Findings and fixes

Severity: **blocker** = false on every route, or a plain contradiction a single route can read; **should-fix** = a
fact asserted on a route that never established it; **minor** = a small unestablished definite reference or detail.

### Impossible on every route

1. **ch_pencil** (blocker). Route: R-summit `> c_L_summit_1 > c_summit_survey_1 > c_ch_sightings_1 > c_ch_gather_1 >
   c_ch_table_2`. Quote: "Every tide pool, every orchid on its rock face, the handprint cave and the star slab and the
   vanished village." The handprint cave (`cv_glitter`), star slab (`cove_rise`) and village (`mg_ruin`) lie on
   mutually exclusive first-act branches; no route has seen all three, and the orchids are only on `cf_hollow`. Fix:
   "Every tide pool, every stream, every cave mouth and headland and reef." `ch_table`'s "every tide pool and orchid
   and cave" became "every tide pool and stream and cave" for the same reason.
2. **summit_signal** (blocker). Route: R-summit `> c_L_summit_2`. Quote: "The seal pup in the warm cave, the turtle
   out on the reef." The pup is met only on `c_cv_enter_3`, the turtle only on `c_mg_enter_2`; the branches are
   exclusive, so no route met both, and a pup inside a cave cannot be seen from the summit. Fix: the line now says only
   what the summit can show: through the spyglass Wren picks out a small turtle on its back in a draining pool on the
   reef.
3. **meet_boat** (blocker). Route: R-summit `> c_L_summit_2 > c_summit_signal_1 > c_signal_aim_1 > c_signal_flash_1 >
   c_ship_turns_1 > c_race_down_1`. Quote: "From the heights above, the whole coast had lain open, and two stranded
   creatures with it." Same impossibility as finding 2. Fix: the turtle is the one seen from the summit; the pup is
   heard crying from a sea cave in the cliffs on the way down the cove path, true on every route into `meet_boat` (all
   come through `race_down`).
4. **e_rescue_pup** (should-fix). Route: finding 3's route `> c_meet_boat_1`. Quote: "Wren guided the two sailors to
   the warm cave, and together, three pairs of hands where one had failed, they lifted the seal pup up and out." "The
   warm cave" and "where one had failed" lean on `cv_warm`/`cv_pup`, which this route never visited (and no continuing
   route ever tried and failed: that try is the ending `e_cv_pup_fail`). Fix: "into the sea cave, following the crying
   ... where one alone could never have managed"; "It went through the sea tube on the rising tide" became "They
   carried it down to the rising tide".

### Plain contradictions

5. **e_rescue_turtle** (blocker). Route: finding 3's route `> c_meet_boat_2`, with the turtle met first on
   `c_n_start_1 > c_mg_enter_2`. Quote: "Wren led the sailors out across the flats to the reef, timing it against the
   tide." The flats are to the right of the landing beach; the oyster-rock turtle and the reef channel that feeds its
   pools are on the mangrove side. Fix: "out along the rocks to the reef".
6. **e_ch_clean** (blocker). Route: R-summit `> c_L_summit_1 > c_summit_survey_1 > c_ch_sightings_1 > c_ch_gather_1 >
   c_ch_table_2 > c_ch_pencil_1 > c_ch_sign_3 > c_ch_seal_final_2`. Quotes: "Wren handed over the clean inked
   masterwork exactly as drawn" and "the honest shape of the island fixed forever in black ink." On this route the chart
   was pencilled soft and grey. Fix: "the clean masterwork exactly as drawn" and "fixed true on the page".
7. **tf_cargo / cove_starrock** (blocker). Route: `c_open > c_n_start_5 > c_tf_enter_2 > c_tf_channel_3 > c_tf_wreck_1 >
   c_tf_hold_1 > c_tf_cargo_1 > c_tf_cliffgap_1 > c_L_cove_2 > c_cove_rise_1`. Quote (tf_cargo): "This was the very
   ship that had carried the island's first settlers, the families who came and built", while `cove_starrock` on the
   same route credits "the island's first people", long before any chart. Fix: the Marigold "had carried settlers out
   to the island long ago, the families who came to build"; `e_tf_bell`'s "brought the first families" became "brought
   settler families".
8. **camp_journal / ch_farshore** (blocker, NEW). Route: R-camp `> c_camp_ascent5_1 > c_L_camp_2 > c_camp_trunk_2 >
   c_camp_journal_1 > c_camp_ready_1 > c_camp_summitpath_1 > c_ridge_notch_1 > c_wind_gap_1 > c_L_summit_1 >
   c_summit_survey_3`. Quote (camp_journal): "Fixing the spring, the reef, the far wild shore." `camp_chart` says the far
   shore was left blank and `ch_farshore` calls it ground never mapped by anyone. Fix: "Fixing the spring and the reef,
   and dreaming of the far wild shore."
9. **camp_journal / ch_ink** (should-fix, NEW). Route: finding 8's route ending `c_L_summit_2 > c_summit_signal_2 >
   c_ch_gather_1 > c_ch_table_1`. Quote (ch_ink): "The cove and the reef named at last in a firm clear hand." The
   journal on this route says Alder named the hidden cove. Fix: "lettered in a firm clear hand".
10. **mg_readmarks, cf_notes, tf_bottle vs L_camp** (should-fix, NEW). Routes `c_open > c_n_start_1 > c_mg_enter_1 >
    c_mg_bridge_1 > c_mg_carve_2`; `c_open > c_n_start_2 > c_cf_enter_3 > c_cf_hollow_1 > c_cf_box_1`;
    `c_open > c_n_start_5 > c_tf_enter_3 > c_tf_strand_1`, each continuing to `L_camp`. Quotes: "A complete chart of
    the island had been left at a camp on the ridge"; "Alder had drawn a full chart of the island and hidden it safe at
    a camp on the ridge."; "The full chart of it waits at the ridge camp". `L_camp` finds half the island drawn, and
    Wren never remarks on it. Fix: "A chart of the island"; "Alder had begun a chart of the island and left it safe";
    "toward the camp and the map"; "The chart of it".
11. **summit_signal vs n_open** (minor). Route: R-summit `> c_L_summit_2`. Quote: "The ship was a far white speck
    standing off the reef, patient, waiting for dusk." `n_open` has the ship return at dusk (and `e_tf_bottle` watches
    for "the returning sail"). Fix: "a far white speck, back already and standing off the reef, waiting for dusk."
12. **tf_deck** (minor, NEW). Route: `c_open > c_n_start_5 > c_tf_enter_2 > c_tf_channel_3 > c_tf_wreck_2`. Quote: "From
    the high stern rail," Wren has climbed the deck, which slopes up to the bow, to the bow; label `c_tf_deck_1` also said
    "the high stern". Fix: "high bow rail" in body and label (the label asserted the wrong fact).

### Alder named on routes that never introduced the name (should-fix)

Alder is introduced only at `mg_readmarks`, `mg_overhang`, `cf_notes`, `e_tw_log`, `tw_tube` and `tf_bottle`. Each
node below names Alder (or recognises the hand) on the route shown, which met none of them. Fix pattern: make the
reference introduce itself by putting the name on the object Wren is looking at, or drop a comparison that needs it.

13. **mg_dam**. `c_open > c_n_start_1 > c_mg_enter_4 > c_mg_lagoon_3`. Quote: "It was one of Alder's marks, driven
    here long ago and still keeping its place, exactly where an old chart would have said it should be." (no old chart
    exists on this route either). Fix: the stake has "a faded number and a name, Alder, burned into its side"; "Some
    mapmaker called Alder had driven it here long ago". Covers `e_mg_stake`.
14. **mg_blind**. `c_open > c_n_start_1 > c_mg_enter_3 > c_mg_creek_3 > c_mg_heron_1`. Quote: "The blind was a
    surveyor's hide, and Alder had used it well." Fix: "a name cut into its doorpost, Alder, said whose it had been."
    Covers `e_mg_tidetable`.
15. **mg_ruin**. `c_open > c_n_start_1 > c_mg_enter_4 > c_mg_lagoon_1 > c_mg_canoe_1 > c_mg_paddle_1 > c_mg_lagfar_1`.
    Quote: "It was older than Alder, older than any chart," Fix: "It was older than any chart,".
16. **cf_fallpool**. `c_open > c_n_start_2 > c_cf_enter_4 > c_cf_falls_3`. Quote: "Alder's hand again, patient and
    exact." Fix: "A name was cut small in one corner, Alder: some surveyor's work, patient and exact." Covers
    `e_cf_gauge`.
17. **cf_dellcarve**. `c_open > c_n_start_2 > c_cf_enter_2 > c_cf_traverse_3 > c_cf_dell_2`. Quote: "And there, among
    them, small and neat, was Alder's mark." Fix: "was a name cut in full: Alder." and "Wren traced the name". Covers
    `e_cf_carve`.
18. **cf_treetop**. `c_open > c_n_start_2 > c_cf_enter_1 > c_cf_switch_1 > c_cf_ledge_1 > c_cf_bench_2 > c_cf_grove_1 >
    c_cf_canopy_1`. Quote: "This was Alder's treetop survey point." Fix: "a surveyor's treetop lookout", the sighting
    ring stamped "Alder".
19. **cf_shrine**. `c_open > c_n_start_2 > c_cf_enter_1 > c_cf_switch_1 > c_cf_ledge_1 > c_cf_bench_2 > c_cf_grove_2`.
    Quote: "This was older than Alder, older than any chart," Fix: "This was older than any chart,".
20. **cv_ochre**. `c_open > c_n_start_3 > c_cv_enter_2 > c_cv_glitter_1`. Quote: "older than the Chart House, older
    than Alder, older than everyone." Fix: "older than the Chart House, older than everyone."
21. **tw_tube**. `c_open > c_n_start_4 > c_tw_enter_3 > c_tw_cellar_1`. Quote: "badly water-stained, Alder's abandoned
    draft." Fix: "an abandoned draft signed with a single name, Alder." Covers `e_tw_draft`.
22. **tw_wallcharts**. `c_open > c_n_start_4 > c_tw_enter_4 > c_tw_quarters_1`. Quote: "and signed in the same corner."
    followed by "Alder's life". Fix: "signed in the same corner with the same name, Alder." Covers `e_tw_charts`.
23. **tw_seachest**. `c_open > c_n_start_4 > c_tw_enter_4 > c_tw_quarters_2`. Quote: "This was the family Alder had
    left ashore to come and map the world" Fix: the drawing carries "across the top in wobbly letters, For Alder."
    Covers `e_tw_drawing`.
24. **tw_cache**. `c_open > c_n_start_4 > c_tw_enter_1 > c_tw_ground_3 > c_tw_slab_1`. Quote: "addressed in a hand Wren
    now knew well, to whoever finishes my work." (one glimpse of the logbook hand at `tw_ground` is not "knew well";
    the label names Alder). Fix: "addressed in a small sure hand to whoever finishes my work, and signed with one name,
    Alder." Covers `e_tw_cache`.
25. **tw_viewdial**. `c_open > c_n_start_4 > c_tw_enter_2 > c_tw_stair_1 > c_tw_top_3 > c_tw_beacon_2`. Quote:
    "lettered in a small sure hand. Alder had spent" Fix: inserted "A name was cut at its foot: Alder." Covers
    `e_tw_dial`.
26. **tw_fuelstore**. `c_open > c_n_start_4 > c_tw_enter_2 > c_tw_stair_1 > c_tw_top_3 > c_tw_beacon_1 >
    c_tw_brazier_1`. Quote: "in a hand Wren was learning to know, a last line." Fix: "in a smaller, surer hand, a last
    line ... The signature beneath it read Alder." Covers `e_tw_note`, whose "the boat that came too late" (not on this
    route) became "the return that never came".
27. **cove_seacave**. `c_open > c_n_start_3 > c_cv_enter_2 > c_cv_glitter_2 > c_cv_deepglow_1 > c_L_cove_3 >
    c_cove_pools_1`. Quote: "were initials and a date. Wren traced them and knew the hand. Alder's." Fix: "were a name
    and a date. Wren traced the letters. Alder." Covers `e_cove_tin`.
28. **cove_rockpool**. Same route with `c_cove_pools_2`. Quote: "It was the very work Alder had begun and never
    finished, taken up now by another hand." Fix: "It was careful, valuable work, the foundation of any reliable
    chart."
29. **fresh_cairn**. `c_open > c_n_start_2 > c_cf_enter_2 > c_cf_traverse_1 > c_L_fresh_1 > c_fresh_climb_1 >
    c_fresh_meadow_2`. Quote: "It was one of Alder's boundary points, set here to fix the very middle of the island."
    Fix: the capstone carries "a survey mark, an arrow, and a name, Alder. It was a boundary point". Covers
    `e_fresh_cairn`.
30. **camp_ascent5 / L_camp** (merge). R-camp. Quote: "Alder's camp, exactly where every clue on the island had been
    quietly pointing all day. The driftwood arrows, the scratched names, the line of patient cairns, all of them had led
    here." No Alder, no clue, no driftwood (only `mg_carve`) and no scratched name (only `mg_overhang`) on this route;
    only the cairns are on every route. Fix: "A name was painted small on a board above the low doorway: Alder. This
    was Alder's camp, at the very end of the line of patient cairns."
31. **camp_chart** (NEW). R-camp `> c_camp_ascent5_1 > c_L_camp_1`. Quote: "in the small sure hand Wren now knew so
    well." Fix: "in the same small sure hand." (the hand of the chart just seen in `L_camp`).

### Merge passages that presuppose clues or a camp

32. **cf_bench** (should-fix). `c_open > c_n_start_2 > c_cf_enter_1 > c_cf_switch_1 > c_cf_ledge_1`. Quote: "A stony
    trail climbed on toward the high camp Wren kept hearing about, the place every clue pointed to." Fix: "toward the
    high ridge, where a speck of grey canvas showed against the rock: a camp."
33. **cove_ridge** (should-fix). `c_open > c_n_start_3 > c_cv_enter_2 > c_cv_glitter_2 > c_cv_deepglow_1 > c_L_cove_2 >
    c_cove_rise_2`. Quote: "Every clue on the island had been pointing to it all day." Fix: "A stony trail lifted away
    up the ridge toward a speck of grey canvas that could only be a camp."
34. **tw_toridge** (should-fix). `c_open > c_n_start_4 > c_tw_enter_1 > c_tw_ground_2 > c_tw_salvage_1`. Quote: "It was
    the place all the day's clues kept pointing toward." Fix: "a speck of grey canvas showed at last: a camp on the
    ridge."
35. **cf_campapproach** (should-fix, NEW). `c_open > c_n_start_4 > c_tw_enter_3 > c_tw_cellar_2 > c_tw_supplies_1`.
    Quote: "The last stretch toward the camp was a scramble over broken rock" No camp is known on this route. Fixed
    upstream in `tw_supplies`: "toward a speck of grey canvas high on the ridge that could only be a camp." Every other
    parent now establishes the camp.
36. **tw_salvage** (minor). `c_open > c_n_start_4 > c_tw_enter_1 > c_tw_ground_2`. Quote: "straight inland toward the
    ridge camp, or carry it up" and label "Take the alidade toward the ridge camp." Fix: "toward the ridge" in body and
    label (the label asserted an unestablished fact).
37. **tw_top** (minor). `c_open > c_n_start_4 > c_tw_enter_2 > c_tw_stair_1`. Quote: "away across the ridge, reached
    only by way of the camp." Fix: "with a speck of grey canvas, some kind of camp, tucked below it."
38. **cv_tohigh** (minor). `c_open > c_n_start_3 > c_cv_enter_3 > c_cv_warm_1 > c_cv_pup_1`. Quote: "not far above, the
    grey canvas of the ridge camp showed against the higher rock." Fix: "a speck of grey canvas showed against the
    higher rock: a camp on the ridge."
39. **L_fresh** (should-fix). `c_open > c_n_start_2 > c_cf_enter_2 > c_cf_traverse_1`. Quotes: "Whoever had drawn the
    first ochre map had marked this very place." (the ochre map is only on `cv_ochre`) and "A path climbed on toward
    the ridge and its camp." Fix: "Any true chart of the island would have to begin here." and "far up it, where the
    trees thinned, a speck of grey canvas showed: a camp."
40. **cf_upper** (minor). `c_open > c_n_start_2 > c_cf_enter_2 > c_cf_traverse_2`. Quote: "Up meant height and progress
    and the camp beyond." Fix: "Up meant height and progress." Also "winked up from the beach" became "winked up from
    below" (the gleam was seen partway up, at `cf_enter`).
41. **e_ascent_daunted** (minor, NEW). R-camp prefix `... > c_camp_ascent1_1 > c_camp_ascent2_3`. Quote: "a grey speck
    out of reach, its chart saved for a braver day." No chart at the camp is known on this route. Fix: "saved for a
    braver day."
42. **tw_cellar** (minor). `c_open > c_n_start_4 > c_tw_enter_3`. Quote: "It might hold the very map the whole island
    seemed to whisper about." Fix: "It might hold an old survey of the island itself."

### Tools found on one route and used at the summit

43. **L_summit / summit_signal / signal sequence** (blocker). R-summit. Quotes: "signal the far ship first with Alder's
    mirror" (L_summit) and "Wren remembered Alder's signal mirror warm in the satchel." (summit_signal). The mirror was
    only in the trunk; routes `c_L_camp_3` and `c_L_camp_1` never saw it. Fix: `L_camp` now lays "a row of pens, a brass
    spyglass, and a small signal mirror" beside the chart and says the camp is "long empty"; `camp_summitpath` opens
    "with Alder's chart and tools carried safe"; `camp_trunk` now holds "spare nibs in a tin, a bottle of ink, and a
    soft cloth for polishing the mirror and the spyglass lens" instead, so the two do not contradict.
44. **camp_ready** (should-fix). R-camp `> c_camp_ascent5_1 > c_L_camp_1 > c_camp_chart_1`. Quote: "The pens, the
    glass, the fixed and certain lines already drawn" Fixed by finding 43 (no text change here).
45. **ch_farshore / ch_ink** (should-fix). R-summit `> c_L_summit_1 > c_summit_survey_3`, and the `ch_ink` route of
    finding 9 without the trunk. Quotes: "Wren turned the brass glass on the far shore" and "Wren inked the chart with
    Alder's good pen". Fixed by finding 43.
46. **ch_sightings** (blocker). R-summit `> c_L_summit_1 > c_summit_survey_1`. Quote: "The salvaged brass rule swung
    true" The alidade is found only at `tw_salvage`. Fix: "Alder's brass spyglass swung true".
47. **ch_sign** (blocker). R-summit `> c_L_summit_2 > c_summit_signal_2 > c_ch_gather_1 > c_ch_table_1 > c_ch_ink_1`.
    Quote: "Whoever finishes the chart, Alder's journal had said, should name the island." The journal is read only on
    `c_camp_trunk_2`. Fix: "Alder had left the banner across the top of the half chart empty, as if the naming were
    meant for whoever finished it. Now that blank banner waited for a single word."
48. **e_ch_survey** (minor, NEW). Finding 47's route `> c_ch_sign_4`. Quote: "small and neat, the way Alder always
    had." Alder's signing habit is seen only at `tw_wallcharts`. Fix: "the way careful surveyors always had."
49. **ship_turns** (minor, NEW). R-summit `> c_L_summit_2 > c_summit_signal_1 > c_signal_aim_1 > c_signal_flash_1`.
    Quote: "off a dead mapmaker's mirror" Alder's death is only implied on the trunk and tower routes. Fix: "a lost
    mapmaker's mirror".
50. **race_down** (minor, NEW). Finding 49's route `> c_ship_turns_1`. Quote: "Past the camp, down the cut cove path,"
    No cove path is known on this route. Fix: "down a hand-cut path toward the cove,".

### Smaller unestablished references (minor)

51. **cv_deepglow**. `c_open > c_n_start_3 > c_cv_enter_2 > c_cv_glitter_2`. Quote: "It was the hidden cove, seen from
    below now," No cave route has seen the cove from above. Fix: "It was a hidden cove,".
52. **cv_enter**. `c_open > c_n_start_3`. Quote: "Someone had been here before, and recently." The only predecessors in
    the book are long gone. Fix: "Someone had been here before."
53. **mg_seep**. `c_open > c_n_start_1 > c_mg_enter_4 > c_mg_lagoon_2 > c_mg_lagtunnel_1`. Quote: "The seep of clear
    water climbed out of the marsh" No seep on the root-tunnel route. Fix: "A seep of clear water".
54. **cove_rise** (NEW). `c_open > c_n_start_1 > c_mg_enter_1 > c_mg_bridge_1 > c_mg_carve_2 > c_mg_readmarks_1 >
    c_mg_highground_2 > c_mg_seep_2 > c_mg_overhang_1`. Quote: "The hand-cut path climbed steeply" No such path is
    introduced on the overhang route. Fix: "A hand-cut path".
55. **tf_cliffgap**. `c_open > c_n_start_5 > c_tf_enter_2 > c_tf_channel_1`. Quote: "a secret cove that no chart had
    ever shown." Alder's chart (`camp_chart`) shows the cove. Fix: "a secret cove hidden from every passing ship."
    (`L_cove`'s "no chart had ever shown to the world" is true, since Alder's chart never left the camp; unchanged.)
56. **cf_shelf** (NEW). `c_open > c_n_start_2 > c_cf_enter_1 > c_cf_switch_2`. Quote: "onto the same grassy bench where
    the ridge path began" The bench was seen only on the sibling `cf_ledge`. Fix: "onto a broad grassy bench".

## Recorded and not fixed

**Agency problems (control rule: never fixed).** No variables, so no choice ever comes back; 33 merge nodes, one of
which (`camp_ascent4`) says the two ways came together; 7 of 113 decisions restate their options (`mg_oyster`,
`mg_gametrail`, `cf_traverse`, `tw_salvage`, `cf_fallpool`, `cv_lakebeach`, `cv_glowworm`); meta labels
`c_tw_seachest_2`, `c_tw_fuelstore_2`, `c_cove_seacave_2`; second-person labels `c_tf_seals_2`, `c_tf_hold_2`,
`c_cf_dellcarve_1`; four give-up setback endings; two setbacks within three decisions of the start. Marking the turtle
(`c_mg_turtle_note_1`), the cave pup (`c_cv_pup_1`) or the tangled pup (`c_tf_seals_1`) changes nothing later, and the
locket girl in `cf_box` is never returned to. After the fix `meet_boat` no longer names the cave pup or the oyster-rock
turtle as the ones Wren met (no route met both, so naming them was false); a reader who marked one may still take the
reef turtle or the sea-cave pup to be that animal. A real payoff would need a variable, which the control rule forbids.

**Soft time words (judged not contradictions).** `e_mg_turtle_seen`'s "slipping light" in the morning and similar loose
time words in endings read as the day passing, not a stated clock time; left as written.

**Prose slips that are not continuity (left for the owner).** `e_cove_tin` ends "and could not bring itself to mind"
(Wren never takes a pronoun), and `cf_shelf` has "It brought them out" for Wren. One word each, outside the controls
rule.

**Plausible but unstated.** `e_ch_alder_name` has the mate understand "the whole story" from the name Alder; the mate
may know the Chart House's lost mapmaker. Nothing contradicts it; left.

## Result after the fix

- Known-on-entry dataflow over the fixed book and the updated plan: 0 requirements not guaranteed on some route, 0
  contradictions (48 before). Engine walk: 225 configurations, every node, re-read.
- Open continuity findings: 0. Open agency findings: as recorded above, by design.
- `scripts/run_story_gate.py`: exit 0; `run_fill_gate(...).blocked` False; warnings by rule unchanged except RL-13,
  16 to 15.
- `scripts/check_fill_integrity.py skeletons/10-13/the-mapmakers-island.json out/the-mapmakers-island.filled.json`:
  markers, words and fill-rate pass. Structure fails, as before this pass: the skeleton declares
  `metadata.narrative_person: "third"` and the book does not; there is no other structural difference. Left as found.
- Agency headline from `check_prose_craft.py`, before and after (identical):
  `agency: 33 merge nodes, 1 of them tell the reader the route did not matter; 0 variables, so no choice comes back; 7 of 113 decisions restate or announce their options; 4 of 29 setback endings have the hero give up, 2 come within 3 decisions.`
