# Residual continuity fixes: the-mapmakers-island (control book, 2026-11-22)

- **Book:** `out/the-mapmakers-island.filled.json`, id `sk_mapmakers_island`, 225 nodes, 72 endings, band 10-13.
- **Before:** sha256 `2bb129096f67e9f45e1f9b19c2b2b63623c1fa492e1a5ca4c2d373ae65b1d4d1` (WP-0.4 fixed text, `16932c1`).
- **After:** sha256 `ce7e80a923c4090aa180a84a6dbfa141ef4468496b477cfe9058c4b364a3b853`.
- **Shape hash:** `sha256:009aa1d3bc0f5ef307b9056b46a0d7a1cb2b0310e26766f2dac9d761e2f7ee40`, unchanged.
- **Scope:** the items judged real in `residuals-2026-11-21.md` (section "The Mapmaker's Island"): MI-1, MI-2,
  MI-5, MI-7, MI-8, MI-9, MI-10, MI-11. MI-3, MI-4 and MI-6 were judged not defects and are left as written.
- **Control rule (D3):** continuity only. No node, choice, condition, effect, variable or ending valence or kind
  changed; no agency problem was touched. The WP-0.4 fixes in `../story-plan-retro/findings-the-mapmakers-island.md`
  were re-read and none is undone (findings 8, 9, 47 and 51 sit in or next to touched text and still hold).

## Fixes

Every quote is verbatim; the table quotes the changed fragment, and the full sentences follow it. Witnesses (W1 to
W10) are the routes in the residuals file. Each was replayed from `n_open` with `StoryEngine` (`start`,
`visible_choices`, `choose`); each landed on the named node, and the after text was found on the route, in a body
passed through or a label taken.

| ID | Node | Before | After | How verified |
| --- | --- | --- | --- | --- |
| MI-1 | `n_open` | "the apprenticeship goes" | "the apprenticeship at the Chart House goes" | W1; on every route |
| MI-2 | `n_open` | "a flask, and one blank sheet" | "a flask, a sketchbook for field notes, and" | W2a, W2b, W2c |
| MI-2 | `n_open` | "at first light, and Wren" | "at first light. Wren" | FK 7.3 to 5.5 |
| MI-5 | `camp_journal` | "Naming the hidden cove. Fixing the spring" | "Naming a hidden cove. Fixing a spring" | W3 |
| MI-7 | `cv_upflow` | "The way to the spring ran upstream" | "The way on ran upstream" | W4 |
| MI-7 | `cv_glowworm` | "the trickle of the spring" | "the trickle of a spring" | W5 |
| MI-8 | `cv_deepglow` | "Wren pushed toward the glow" | "Wren pushed toward a faint glow" | W6 (6 choices) |
| MI-9 | `e_tw_nofuel` | "Wren poked about the cold brazier" | "Wren let the fuel store go" | W7 |
| MI-9 | `e_tw_nofuel` | "the search had swallowed" | "the long trek out along the headland had swallowed" | W7 |
| MI-10 | `e_ch_dusk` | "One more cove, drawn in." | "One more cove, shaded finer." | W8 (20 choices) |
| MI-10 | `e_ch_dusk` | "a wonderful, unfinished thing" | "a wonderful thing rolled tight and still unsigned" | W8 |
| MI-10 | `e_ch_dusk` | "the loveliest half-drawn island" | "the loveliest never-finished island" | W8 |
| MI-11 | `ch_gather` | "and the island came whole." | "and whatever the sketches lacked lay in plain sight" | W9, W10 |
| MI-11 | `ch_gather` | "every piece fitting against" | "every piece could be set against" | W9, W10 |
| MI-11 | `ch_gather` | "everything fixed" | "everything within reach" | W9, W10 |
| MI-11 | `ch_gather` | "the mapmaker who finished it" | "the mapmaker who would finish it" | W9, W10 |

Full sentences, before and after:

- MI-1, MI-2 (`n_open`). Before: "The rowboat scraped onto the sand at first light, and Wren climbed out with a
  satchel, a flask, and one blank sheet of paper." and "Fill that paper with a true chart before the ship returns at
  dusk, or the apprenticeship goes to somebody else." After: "The rowboat scraped onto the sand at first light. Wren
  climbed out with a satchel, a flask, a sketchbook for field notes, and one blank sheet of paper." and "Fill that
  paper with a true chart before the ship returns at dusk, or the apprenticeship at the Chart House goes to somebody
  else." The split is there only to hold reading level: FK grade was 7.3 with the kit clause added, 5.5 after.
- MI-5 (`camp_journal`). Before: "Naming the hidden cove. Fixing the spring and the reef, and dreaming of the far wild
  shore." After: "Naming a hidden cove. Fixing a spring and the reef, and dreaming of the far wild shore."
- MI-7 (`cv_upflow`). Before: "The way to the spring ran upstream, against the cold current, and Wren climbed it
  steadily, boots braced on the streambed." After: "The way on ran upstream, against the cold current, and Wren
  climbed it steadily, boots braced on the streambed." The passage still introduces "the island's spring" itself.
- MI-7 (`cv_glowworm`). Before: "The ground sloped off gently toward a sound Wren had been half hearing all along, the
  trickle of the spring somewhere ahead." After: the same with "the trickle of a spring somewhere ahead." The later
  "toward the spring" and the label "Follow the easy way to the spring." now follow the introduction.
- MI-8 (`cv_deepglow`). Before: "Wren pushed toward the glow, and it grew from a thread to a crack to a bright seam of
  daylight." After: "Wren pushed toward a faint glow, and it grew from a thread to a crack to a bright seam of
  daylight." Still reads after `cv_glitter` ("a further glow") and `cv_arch` ("the light").
- MI-9 (`e_tw_nofuel`). Before: "Wren poked about the cold brazier and the rocks around it, hunting for the fuel
  store. There was nothing but rust and old ash and a great deal of wind." and "...and the search had swallowed a good
  hour for a plain dead end." After: "Wren let the fuel store go and gave the dead beacon one last look instead. There
  was nothing in the brazier but rust and old ash, and nothing around it but a great deal of wind." and "...and the
  long trek out along the headland had swallowed a good hour for a plain dead end." The hour now comes from the walk
  out (`tw_beacon`: "Wren went out to it against the wind").
- MI-10 (`e_ch_dusk`). Before: "One more cove, drawn in.", "Wren ran for the beach at last with a wonderful,
  unfinished thing rolled tight, too detailed ever to call done." and "Wren climbed aboard with the loveliest
  half-drawn island in the world, and the lesson that done beats perfect, every time." After: "One more cove, shaded
  finer.", "Wren ran for the beach at last with a wonderful thing rolled tight and still unsigned, too detailed ever to
  call done." and "Wren climbed aboard with the loveliest never-finished island in the world, and the lesson that done
  beats perfect, every time."
- MI-11 (`ch_gather`). Before: "The stones held them flat, and the island came whole. Coast and cave, ridge and reef,
  spring and shore, every piece fitting against Alder's careful half like two halves of one puzzle. It was all there.
  Everything seen, everything fixed, everything understood. The work of the mapmaker who came first and the mapmaker
  who finished it, side by side, making a single true thing." After: "The stones held them flat, and whatever the
  sketches lacked lay in plain sight below the summit, there to be read straight off the land. Coast and cave, ridge
  and reef, spring and shore, every piece could be set against Alder's careful half like two halves of one puzzle. It
  was all there. Everything seen, everything within reach, everything understood. The work of the mapmaker who came
  first and the mapmaker who would finish it, side by side, making a single true thing."

Witnesses (`R-camp` and `R-summit` as defined in the residuals file):

- W1 `c_open > c_n_start_5` (lands on `tf_enter`).
- W2a `c_open > c_n_start_5 > c_tf_enter_1 > c_tf_sandbar_2` (`e_tf_stranded`); W2b `c_open > c_n_start_1 >
  c_mg_enter_4 > c_mg_lagoon_1 > c_mg_canoe_2` (`e_mg_canoe`); W2c `R-camp` (through `camp_ascent4`).
- W3 `R-camp > c_camp_ascent5_1 > c_L_camp_2 > c_camp_trunk_2` (`camp_journal`).
- W4 `c_open > c_n_start_3 > c_cv_enter_1 > c_cv_water_2` (`cv_upflow`).
- W5 `c_open > c_n_start_3 > c_cv_enter_1 > c_cv_water_3 > c_cv_rift_2` (`cv_glowworm`).
- W6 `c_open > c_n_start_3 > c_cv_enter_1 > c_cv_water_3 > c_cv_rift_1 > c_cv_squeeze_1` (`cv_deepglow`).
- W7 `c_open > c_n_start_4 > c_tw_enter_2 > c_tw_stair_1 > c_tw_top_3 > c_tw_beacon_1 > c_tw_brazier_2`
  (`e_tw_nofuel`).
- W8 `R-summit > c_L_summit_2 > c_summit_signal_2 > c_ch_gather_1 > c_ch_table_2 > c_ch_pencil_2` (`e_ch_dusk`).
- W9 `R-summit > c_L_summit_2 > c_summit_signal_2` (`ch_gather`). `L_summit` ("saw, at last, the whole island") is on
  every route into `ch_gather`.
- W10 the three surveying parents of `ch_gather` (`ch_sightings`, `ch_reef`, `ch_farshore`), read against the new
  text: each still reads true.

**Why MI-2 was fixed in the opening.** The residual offered two fixes: name a sketchbook in `n_open`'s kit, or rewrite
the eight sketchbook passages. The opening fix was chosen because the eight passages are not the whole of it: at
least a dozen more passages fill "page after page" (`e_mg_village`, `e_cf_carve`, `e_cv_fish`, `e_cv_prints`), copy
charts "into the sketchbook", or gather "the whole day's sketches" (`ch_gather`, `ch_sightings`), and all of them
presuppose paper beyond the single sheet. One clause in the kit list makes every one true on every route. The test
stays intact: the sheet is still the one page the mate named, "Fill that paper" still binds to it (it is the last
item listed), and a field sketchbook is a working tool, not a second chance at the chart.

**Why MI-9 was fixed in the ending.** The label and the decision prose in `tw_brazier` both say "give up on the dead
beacon and turn back"; only the ending searched. Rewriting the ending's opening keeps the two options distinct (the
sibling `c_tw_brazier_1` is the search). The last two sentences, which the give-up detector reads, are unchanged.

**Why MI-10 and MI-11 were fixed this way.** `ch_pencil` leads both to signing and to `e_ch_dusk`, so "nothing was
missing" stays and the ending now reads as perfectionism (unsigned, never called done) rather than a half-drawn
chart. `ch_gather` has four parents; three surveyed, the signalling route did not. The passage now draws the missing
ground from the view below the summit, which every route into `ch_gather` has seen, so it is true on all four without
changing which endings exist. `summit_signal`'s "It would cost the finishing of the chart, or most of it" was left:
it states the cost of a full signal, and sharpening it would change how much the choice matters (agency, out of
scope).

## Plan updates (`out/the-mapmakers-island.plan.json`)

- New fact `wren_sketchbook`; `n_open` now establishes `wren_sketchbook` and `chart_house`.
- The eight sketchbook passages (`camp_ascent4`, `e_tf_stranded`, `e_mg_canoe`, `e_cf_slip`, `e_tw_charts`,
  `e_mg_chick`, `e_cf_canopy`, `e_cv_raft`) now require `wren_sketchbook`.
- `ch_gather` now requires `summit_view`.
- Reworded facts: `wren_alone`, `chart_house`, `alder_named_cove`, `no_fuel_found`, `chart_gathered`,
  `chart_unfinished_dusk`. Reworded events: `n_open`, `camp_journal`, `e_tw_nofuel`, `e_ch_dusk`, `ch_gather`; cost
  of `c_tw_brazier_2`.
- `provenance.book_sha256` set to the new hash; note "residual fixes 2026-11-22: MI-1, MI-2, MI-5, MI-7, MI-8, MI-9,
  MI-10, MI-11" added.

## Acceptance

- `uv run python scripts/run_story_gate.py out/the-mapmakers-island.filled.json`: exit 0, `findings=49
  blocked=False` (51 before). Two warnings cleared, none added: CG-4 at `e_tw_nofuel` (the ending's opening now
  shares words with its label; CG-4 29 to 28) and RL-13 at `e_ch_dusk` (RL-13 15 to 14).
- `run_fill_gate(book).blocked`: False.
- `uv run python scripts/check_story_plan.py out/the-mapmakers-island.filled.json`: 0 errors, 0 warnings (also 0
  and 0 before).
- `scripts/check_fill_integrity.py skeletons/10-13/the-mapmakers-island.json out/the-mapmakers-island.filled.json`:
  markers, words (mean 109.1 per node) and fill-rate (111.0%) pass. Structure fails, as before this pass and as the
  WP-0.4 record says: the skeleton declares `metadata.narrative_person: "third"` and the book does not.
- Agency headline from `scripts/check_prose_craft.py`, identical before and after (control rule):
  `agency: 33 merge nodes, 1 of them tell the reader the route did not matter; 0 variables, so no choice comes
  back; 7 of 113 decisions restate or announce their options; 4 of 29 setback endings have the hero give up, 2 come
  within 3 decisions.`
- Shape hash unchanged (above). `scripts/build_validation_set.py --check` still passes: the set pins this book at
  git revision `16932c1`, not the working tree.
