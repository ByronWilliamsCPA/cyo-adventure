# WP-1.6 second read: The Clockwork Menagerie

Second-reader continuity pass over `out/the-clockwork-menagerie.filled.json` (WP-1.6 fresh corpus, band 8-11).
Book sha256 `f69e13d99a242a3478066522deb123f564cc556c1661ff14f824a8482274204e` (verified before reading): 167 nodes,
183 choices, 27 endings, 0 variables, start `n_open`. The reader did not write the book and wrote no Story Plan; the
plan checker and `storyplan/` were not read or run. (Written to the repo by the orchestrator from the reader's saved copy, because the harness refuses subagent
writes of evidence files; see `AL-807`.)

**Method.** Every route played with `StoryEngine` (`start`, `visible_choices`, `choose`) depth first from `n_open`:
8,852 complete routes, 167 reachable (node, state) configurations (the book has no variables, so configurations equal
nodes), 167/167 nodes and 27/27 endings reached, no dead ends, longest route 33 choices. Twelve merge nodes (`av_deep`,
`sv_deep`, `ds_deep`, `cg_deep`, `av_conv`, `sv_conv`, `ds_conv`, `cg_conv`, `n_key`, `n_spring`, `n_shop`, `n_hub`)
were each read against every inbound branch. Every body and label was then read against the routes that reach it.
Each quoted sentence was checked verbatim against the JSON by script, each witness was replayed with the engine, and
each "never shown" claim was checked by searching the bodies on the witness route before the cited node.

Severity: blocker (plain contradiction, or a fact false on the route), should-fix (unshown presupposition), minor
(small wording slip). With no variables, `state_contradiction` and `public_plant` had nothing to bite on; their zero
count is an empty class, not a pass.

**Route abbreviations** (all choice ids, from the start):

- `AVA` = `c_open > c_start_av > c_av_x0 > c_av_deep > c_av_a > c_av_a1 > c_av_a2 > c_av_a3 > c_av_a4 > c_av_a5`
- `AVB` = `c_open > c_start_av > c_av_x0 > c_av_deep > c_av_b > c_av_b1 > c_av_b2 > c_av_b3` (reaches `av_b4`)
- `SVA` = `c_open > c_start_sv > c_sv_x0 > c_sv_deep > c_sv_a > c_sv_a1 > c_sv_a2 > c_sv_a3 > c_sv_a4` (reaches
  `sv_a5`)
- `SVB` = `c_open > c_start_sv > c_sv_x0 > c_sv_deep > c_sv_b > c_sv_b1 > c_sv_b2 > c_sv_b3` (reaches `sv_b4`)
- `DSA` = `c_open > c_start_ds > c_ds_x0 > c_ds_deep > c_ds_a > c_ds_a1 > c_ds_a2 > c_ds_a3 > c_ds_a4` (reaches
  `ds_a5`)
- `DSB` = `c_open > c_start_ds > c_ds_x0 > c_ds_deep > c_ds_b > c_ds_b1 > c_ds_b2` (reaches `ds_b3`)
- `CGA` = `c_open > c_start_cg > c_cg_x0 > c_cg_deep > c_cg_a > c_cg_a1 > c_cg_a2 > c_cg_a3 > c_cg_a4` (reaches
  `cg_a5`)
- `CGB` = `c_open > c_start_cg > c_cg_x0 > c_cg_deep > c_cg_b > c_cg_b1 > c_cg_b2 > c_cg_b3` (reaches `cg_b4`)
- `K` = `AVB > c_av_b4 > c_av_conv > c_av_conv2 > c_av_conv3` (12 choices, reaches `n_key`)
- `KA` = `K > c_key_a > c_k_a1 > c_k_a2 > c_k_a3` (reaches `n_spring`)
- `SA` = `KA > c_spring_a > c_s_a1 > c_s_a2 > c_s_a3` (reaches `n_shop`)
- `T` = `c_key_a > c_k_a1 > c_k_a2 > c_k_a3 > c_spring_a > c_s_a1 > c_s_a2 > c_s_a3 > c_shop_a > c_p_a1 > c_p_a2 >
  c_p_a3` (`n_key` to `n_hub`)
- `H` = `K > T` = `SA > c_shop_a > c_p_a1 > c_p_a2 > c_p_a3` (24 choices, reaches `n_hub`)

## Blockers (11)

| ID | Node | Other nodes | Class | Shortest witness |
| --- | --- | --- | --- | --- |
| B1 | `av_x0` | `n_open` | `timeline` | `c_open > c_start_av` |
| B2 | `av_conv` | `av_a5` | `location_or_physical_state` | `AVA` |
| B3 | `ds_conv` | `ds_a5` | `location_or_physical_state` | `DSA > c_ds_a4 > c_ds_a5` |
| B4 | `cg_conv` | `cg_a5`, `cg_b4` | `location_or_physical_state` | `CGA > c_cg_a4 > c_cg_a5` |
| B5 | `av_conv3` | `av_b1` to `av_b4` | `unestablished_fact_on_route` | `AVB > c_av_b4 > c_av_conv > c_av_conv2` |
| B6 | `fh_fx1` | `n_spring`, `fh_fx_*`, `fh_dawn_o2` | `other` | `H > c_hub_fx` |
| B7 | `fh_sec1` | `n_hub` | `location_or_physical_state` | `H > c_hub_sec` |
| B8 | `fh_sec_c1` | `n_key`, `fh_sec_c2` | `location_or_physical_state` | `H > c_hub_sec > c_sec_c` |
| B9 | `e_neu_caretaker` | `fh_sec_j1` | `cross_payoff_reference` | `H > c_hub_dawn > c_dawn_w > c_dawn_w1a` |
| B10 | `fh_fx_fly` | `cg_a3` | `location_or_physical_state` | see detail |
| B11 | `e_win_most` | `fh_rw_b_ok` | `other` | `H > c_hub_rw > c_rw_b > c_rw_bok > c_rw_bok2` |

- **B1.** `av_x0`: "Hundreds of clockwork birds sat frozen on their perches, their beaks still open on songs that had
  stopped hours before." Two nodes earlier `n_open` says "hundreds of clockwork creatures wound down long ago". Long
  ago and hours before cannot both hold for the same stillness. (`n_shop`'s letter, Fettle recently taken poorly,
  sides with "hours"; `fh_fx_bird2` "a long, long sleep" sides with "long ago".)
- **B2.** `av_conv`: "Before she could even reach for the handle, Tock leapt from her shoulder" at "the tall inner
  door that opened onto the central rotunda". On the AVA route `av_a5` ends "The keeper walkway ended at a low service
  door." and she "wrapped her hand around the cold handle". Her hand is already on the handle, and the low service door
  has become a tall inner door. (Tock is also on the floor there; see M10.)
- **B3.** `ds_conv`: "Before she could grip the handle, Tock squeezed himself eagerly through the gap at the door's
  edge". The immediately preceding `ds_a5` ends "gripped the round handle of the porthole door, and made ready to step
  forward."
- **B4.** `cg_conv`: "Before she could reach the arch, Tock slipped away from her shoulder and squeezed through the
  narrow crack ahead of her". On the CGA route `cg_a5` has "The painted path ended at a mirrored door" and she "wrapped
  her fingers around the brass handle"; she is already at a door, not short of an arch. On the CGB route (`CGB >
  c_cg_b4`) the mirrored door she laid her hand on also turns into an arch, without the handle clash.
- **B5.** `av_conv3`: "The clue had promised a master key here, near the heart of everything, and this was surely the
  heart." On the AVB route the clues were a decoy feather and an owl's wing pointing at an archway; no clue mentions a
  master key, a rotunda, or waking anything (search of `av_x0` to `av_conv2` on that route finds no "master", "wake"
  or "promis"). The master-key card exists only on the sibling branch `av_a3`.
- **B6.** `fh_fx1`: "But with the master key and a little spare wind, she could wake just one animal, one single
  creature to greet the dawn." `n_spring`, on every route here, set the rule: "Nothing could be wound until it was
  mended. Even the master key in her hand was useless against a broken heart of steel." The mainspring is still broken,
  yet `fh_fx_lion` ("fitted the master key, then began to wind"), `fh_fx_whale`, `fh_fx_eleph` and `fh_dawn_o2` ("Nia
  fitted the master key with great care") wind animals with that key and they wake. Two incompatible rules for how the
  menagerie runs.
- **B7.** `fh_sec1`: "She looked about the warm little workshop for where it might lie." The previous node `n_hub`
  says "Every path had ended here, at the great spring-room, and now Nia stood ready." (all three `p_*3` nodes walk her
  back to the spring-room). No move back to the workshop is shown; `fh_sec_j1`, `fh_sec_m1` and `fh_sec_c1` then stay
  in the workshop.
- **B8.** `fh_sec_c1`: "On the master ring in her hand hung a whole set of tiny keys." She holds exactly what `n_key`
  gave her: "High on a brass hook beside the towering clock hung a single key." No ring and no small keys appear on
  any route; `fh_sec_c2` ("She held the ring of tiny keys up to the candlelight") builds on it.
- **B9.** `e_neu_caretaker`: "She told of the broken spring, the hidden workshop, the mouse, the journal, and the
  night among the sleeping animals." This ending is reachable only through `n_hub > fh_dawn1`; the journal
  (`fh_sec_j1`) and the second mouse (`fh_sec1`, `fh_sec_m1`) belong to the sibling `fh_sec1` branch. On this route she
  never saw a journal. ("The mouse" might be read as Tock; "the journal" cannot.)
- **B10.** `fh_fx_fly`: "On a little stand among the ferns lay the tiny seed-small winder made for the butterflies."
  On the CGA route `cg_a3` ends "Then she tucked the little winder safely into her pocket". The winder she pocketed is
  back on its stand. Witness: `CGA > c_cg_a4 > c_cg_a5 > c_cg_conv > c_cg_conv2 > c_cg_conv3 > T > c_hub_fx >
  c_fx_fly`.
- **B11.** `e_win_most`: "A few small ones, far off in distant halls, slept on, for the mend was not quite perfect."
  The reader chose "Stop and reseat it properly." and `fh_rw_b_ok` says she "fitted it once more, this time nice and
  true. It clicked home properly." and calls it "a job done right". The ending's imperfect mend contradicts the
  passage, and the label, that led to it.

## Should-fix (16)

| ID | Node | Other nodes | Class | Shortest witness |
| --- | --- | --- | --- | --- |
| S1 | `ds_b3` | | `unestablished_fact_on_route` | `DSB` |
| S2 | `av_b4` | | `unestablished_fact_on_route` | `AVB` |
| S3 | `sv_b4` | | `unestablished_fact_on_route` | `SVB` |
| S4 | `ds_b4` | | `unestablished_fact_on_route` | `DSB > c_ds_b3` |
| S5 | `sv_a5` | `ds_a5`, `cg_a5`, `av_conv`, `sv_conv`, `cg_conv` | `unestablished_fact_on_route` | `SVA` |
| S6 | `sv_conv` | `sv_a5`, `sv_b4` | `location_or_physical_state` | `SVA > c_sv_a5` |
| S7 | `sv_conv3` | `ds_conv3`, `cg_conv3` | `unestablished_fact_on_route` | `SVB > c_sv_b4 > c_sv_conv > c_sv_conv2` |
| S8 | `n_key` | | `unestablished_fact_on_route` | `K` |
| S9 | `sv_a1` | `sv_a2`, `sv_rec`, `sv_risk` | `repeated_reveal` | see detail |
| S10 | `s_c3` | | `unestablished_fact_on_route` | see detail |
| S11 | `n_shop` | | `unestablished_fact_on_route` | `SA` |
| S12 | `n_shop` | `s_a3`, `p_a3` | `location_or_physical_state` | `SA > c_shop_a > c_p_a1 > c_p_a2` |
| S13 | `n_hub` | `n_shop`, `fh_dawn_w2` | `unestablished_fact_on_route` | see detail |
| S14 | `fh_sec1` | `n_hub`, `n_shop` | `unestablished_fact_on_route` | `H > c_hub_sec` |
| S15 | `e_win_eleph` | `fh_fx_eleph` | `unestablished_fact_on_route` | see detail |
| S16 | `e_neu_mouse` | `n_hub`, `av_conv2` | `timeline` | `H > c_hub_sec > c_sec_m > c_sec_m1b` |

- **S1.** `ds_b3`: "She knew that mark by now. It meant the heart of the museum, the place with the great clock, the
  place she had been trying to reach all night." On the DSB route she has seen no clock mark, heard of no great clock
  and set no goal of reaching the heart (`n_open` to `ds_b2` mention none).
- **S2.** `av_b4`: "With every step the warm hum grew louder and closer, that deep steady thrum she now knew came from
  the center of the whole museum." No hum is mentioned anywhere before this on the AVB route, let alone its source.
- **S3.** `sv_b4`: "She pressed her hand flat to it, the way she had learned to, and felt the warmth and the deep
  steady hum of the museum's heart beating close behind." On SVB she has never laid a hand on a door, never heard the
  hum, and never heard of the museum's heart.
- **S4.** `ds_b4`: "With it came the deep steady hum she now knew so well." First mention of the hum on the DSB route.
- **S5.** "The great clock" is spoken of as known, though no route but AVA plants it (`av_a5` "the picture of a great
  clock"). `sv_a5`: "It was the great clock, she was sure, beating on at the center of everything." (SVA). Also
  `ds_a5` "Somewhere just beyond, close now, the great clock ticked its deep slow beat" (DSA); `cg_a5` "Behind it she
  felt the great clock beating, slow and deep" (CGA); `av_conv` "She could feel the great clock's hum right through the
  floor now." (`AVB > c_av_b4`); `sv_conv` "Nia could feel the great clock humming on the far side, closer now than
  ever." (`SVB > c_sv_b4`); `cg_conv` "She could feel the great clock humming now, closer than it had ever been"
  (`CGB > c_cg_b4`). Search for "clock" outside "clockwork" on each of these routes before the cited node finds nothing.
- **S6.** `sv_conv`: "Both routes across the savanna met at the same spot in the end, a tall arch in the inner wall
  that opened onto the central rotunda." On SVA, `sv_a5` has "The trail of oil-drips ended at a plain door set in the
  savanna wall" and she "took hold of the handle, and made ready to step forward."; on SVB, `sv_b4` "At last they
  brought her to a keeper door set in the far wall." The door she was about to open becomes an arch. Same pattern as
  B2 to B4 without the explicit handle clash.
- **S7.** `sv_conv3`: "The keys that could wake the sleeping menagerie must hang somewhere close to this great clock."
  Neither savanna route ever mentions keys that wake the animals, or a wish to wake them (SVB's keyring held oil-cans;
  SVA has no keys at all). Same on `ds_conv3` "The keys that could wake the whole sleeping menagerie must hang somewhere
  close beside this clock." (`DSB > c_ds_b3 > c_ds_b4 > c_ds_conv > c_ds_conv2`) and `cg_conv3` "The keys that could
  wake the whole menagerie must hang somewhere close by the clock." (`CGB > c_cg_b4 > c_cg_conv > c_cg_conv2`). The
  master-key goal is planted only on AVA (`av_a3`), DSA (`ds_a3`) and CGA (`cg_a3`).
- **S8.** `n_key`: "And here at last she found what she had come for." and "The caretaker's master key, she knew at
  once, the one key that could wind the whole menagerie." On `K` (and on both savanna routes, DSB and CGB) she did not
  come for a key and has no way to know what this one does.
- **S9.** `sv_a1`: "Then, without warning, one last breath of leftover wind stirred inside it." and `sv_a2`: "It was
  not truly awake, she saw, but it was not fully asleep either." with "She understood at once." On the recovery route
  she has already watched the elephant lurch awake (`sv_risk`) and then `sv_rec`: "Slowly, slowly, the beast lost the
  last of its wind and began to settle". The scare and the lesson play again as new, and "the last of its wind" is
  followed by more wind. Witness: `c_open > c_start_sv > c_sv_x0 > c_sv_risk > c_sv_rec > c_sv_rec1 > c_sv_rec2 >
  c_sv_a`. (Rated should-fix, not blocker, because `sv_deep` adds an elephant herd, so the second elephant could just
  be another one.)
- **S10.** `s_c3`: "There, right in front of her, was a small hidden door, plain and low, the very one Keeper Fettle
  must have used a thousand times." Fettle is named only in `k_b2`; on the `c_key_a` and `c_key_c` branches he has
  never been mentioned. Witness: `KA > c_spring_c > c_sc_ok > c_sc2`.
- **S11.** `n_shop`: "On the bench lay a letter in Keeper Fettle's own hand." On the `c_key_a` and `c_key_c` branches,
  via `s_a*` or `s_b*`, this is the first mention of Fettle, given as if the reader knows him.
- **S12.** `n_shop`: "There were oil-cans and clamps and, on a hook of its own, the special tool made just for changing
  a mainspring." On the `s_a*` route she is carrying that tool: `s_a3` "She tucked the heavy tool under her arm." and
  `s_a2` identifies it as the mainspring-changing clamp. `p_a3` then has her take "the special changing tool from its
  hook" again. One unique tool is in two places.
- **S13.** `n_hub`: "And clear in her head were Keeper Fettle's careful instructions, learned by heart." On the route
  through `s_c*` (crawlspace) and `p_b*` (cart) she never studies a card, the mending book or the manual; `n_shop` only
  reports that drawings were left, then asserts "Now Nia had the master key, a spare mainspring within reach, and the
  knowledge to use it." `fh_dawn_w2` ("just as Fettle's drawings had shown her") leans on the same unshown study.
  Witness: `KA > c_spring_c > c_sc_ok > c_sc2 > c_sc3 > c_shop_b > c_p_b1 > c_p_b2 > c_p_b3`.
- **S14.** `fh_sec1`: "Keeper Fettle's letter had hinted at a deeper secret, hidden somewhere in the museum." The
  letter's content is given in `n_shop` ("He had been taken poorly, it said, and could not come, and he had left
  careful drawings of how to mend the great spring for whoever might find them.") and, on one branch, `p_c1` (a
  shortcut lever). No route shows a hint of a secret; `n_hub`'s offer "follow Keeper Fettle's deepest secret" rests on
  the same missing plant.
- **S15.** `e_win_eleph`: "The elephant had lurched so scarily in the dark." and "She had taken the frightening thing
  and made it gentle." (also "no longer a runaway"). `fh_fx_eleph`: "She understood it. It had never meant any harm;
  it had only been half-wound and blind and clumsy." On any aviary, deep-sea or conservatory route, and on SVB, Nia
  never saw the elephant move; only `fh_fx1`'s one-line description ("never quite winds down") precedes this. The
  elephant was never a runaway on any route. Witness: `H > c_hub_fx > c_fx_eleph > c_fx_eleph1 > c_fx_eleph2`.
- **S16.** `e_neu_mouse`: "it kept her company through the last dark hours of the night." Dawn has already come: the
  rotunda had "the first grey light of dawn" (`av_conv2` and siblings), and the previous node `n_hub` says "Through the
  tall windows the sky was turning the soft grey of dawn."

## Minor (21)

| ID | Node | Other nodes | Class | Shortest witness |
| --- | --- | --- | --- | --- |
| M1 | `p_c1` | `n_shop` | `timeline` | `SA > c_shop_c` |
| M2 | `s_a1` (`c_s_a1`) | `s_a2` | `label_outcome_mismatch` | `KA > c_spring_a > c_s_a1` |
| M3 | `s_b1` (`c_s_b1`) | `s_b2` | `label_outcome_mismatch` | `KA > c_spring_b > c_s_b1` |
| M4 | `p_a1` (`c_p_a1`) | `p_a2` | `label_outcome_mismatch` | `SA > c_shop_a > c_p_a1` |
| M5 | `p_b1` (`c_p_b1`) | `p_b2` | `label_outcome_mismatch` | `SA > c_shop_b > c_p_b1` |
| M6 | `fh_sec1` (`c_sec_m`) | `fh_sec_m1` | `label_outcome_mismatch` | `H > c_hub_sec > c_sec_m > c_sec_m1b` |
| M7 | `n_spring` | `k_c3`, `k_b3` | `location_or_physical_state` | `K > c_key_c > c_kc_ok > c_kc2 > c_kc3` |
| M8 | `fh_rw1` | `e_set_spring`, `fh_dawn_s1` | `timeline` | `H > c_hub_rw` |
| M9 | `fh_sec_j1` | `n_start`, `n_shop` | `timeline` | `H > c_hub_sec > c_sec_j` |
| M10 | `av_conv` | `av_a4`, `av_a5`, `cg_conv` | `location_or_physical_state` | `AVA` |
| M11 | `e_set_av` | | `location_or_physical_state` | `c_open > c_start_av > c_av_x0 > c_av_risk > c_av_fail` |
| M12 | `e_set_ds` | | `location_or_physical_state` | `c_open > c_start_ds > c_ds_x0 > c_ds_risk > c_ds_fail` |
| M13 | `e_set_sv` | | `location_or_physical_state` | `c_open > c_start_sv > c_sv_x0 > c_sv_risk > c_sv_fail` |
| M14 | `e_set_key` | `k_c1` | `location_or_physical_state` | `K > c_key_c > c_kc_fail` |
| M15 | `fh_dawn_s1` | `n_hub` | `location_or_physical_state` | `H > c_hub_dawn > c_dawn_s` |
| M16 | `fh_fx_whale` | | `location_or_physical_state` | `H > c_hub_fx > c_fx_whale` |
| M17 | `e_win_mouse` | `fh_sec_m2` | `other` | `H > c_hub_sec > c_sec_m > c_sec_m1a > c_sec_m2` |
| M18 | `e_set_cabinet` | `n_shop` | `other` | `H > c_hub_sec > c_sec_c > c_sec_c1b` |
| M19 | `fh_sec_j2` | `k_b1`, `k_b2` | `two_backstories` | see detail |
| M20 | `fh_sec_j2` | `fh_sec_c3` | `two_backstories` | see detail |
| M21 | `e_set_shop` | `p_c1` | `unestablished_fact_on_route` | `SA > c_shop_c > c_pc_fail` |

- **M1.** `p_c1`: "Nia read Keeper Fettle's letter last". On this route the letter is the first of the three things
  she picks, and `n_shop` already had her read it ("Nia read it by candlelight."), so `c_shop_c` "Read keeper Fettle’s
  letter." repeats an action and the new lever note surfaces on a second reading.
- **M2.** Label `c_s_a1` "Follow the keeper sign." leads to `s_a2`, where Tock digs up a card ("Tock burrowed down
  under the loose tools"); the sign first appears in `s_a3`.
- **M3.** Label `c_s_b1` "Search for the door." leads to `s_b2`, where she reads the book ("Nia pulled down the heavy
  mending book"); no door is known until `s_b3`.
- **M4.** Label `c_p_a1` "Head back to the spring-room." leads to `p_a2`, still in the workshop: "Nia read the manual
  through twice".
- **M5.** Label `c_p_b1` "Wheel the cart back." is offered before any cart exists; `p_b2` then finds it: "Nia found the
  answer in a corner of the workshop. It was a little keeper cart".
- **M6.** Label `c_sec_m` "Follow the clockwork mouse." leads to `fh_sec_m1`, where "Nia hesitated." and may choose
  "Coax the mouse gently to you.", ending at `e_neu_mouse` without ever following it.
- **M7.** `n_spring`: "All three ways brought Nia out on a high ledge above the great spring-room." After label
  `c_kc3` "Climb down to the works." and `k_c3` "Nia found the way down and began to climb toward the silent works
  below." (also `k_b3` "Nia followed the walkway on, down toward the silent heart of the museum." on
  `K > c_key_b > c_k_b1 > c_k_b2 > c_k_b3`), she arrives high up again.
- **M8.** Dawn keeps arriving. After `av_conv2`'s "first grey light of dawn" and `n_hub`'s "sky was turning the soft
  grey of dawn", `fh_rw1` has "racing to finish before the dawn came" (label `c_rw_b` "Work bold and fast to beat the
  dawn."), `e_set_spring` "until the keepers came at dawn" (`KA > c_spring_c > c_sc_fail`), `fh_dawn_s1` "Nia leaned her
  head back and waited quietly for the dawn.", and `e_win_all` and `e_win_bird` "When the doors opened at dawn".
- **M9.** `n_start`: "Her candle stub was already burning low. Nia had to pick just one to explore before the little
  flame went out." The same stub lasts the whole night and past dawn: `n_shop` "Nia read it by candlelight.",
  `fh_sec_j1` "turned the leaves slowly by the light of her candle stub", `fh_sec_c2`.
- **M10.** `av_conv` "Tock leapt from her shoulder" on AVA, where `av_a4` has "He hopped down from her shoulder and
  darted off." and `av_a5` "Tock stood up on his back legs" at the door. Likewise `cg_conv` "Tock slipped away from her
  shoulder" after `cg_a5` "Tock stood up tall beside her" (CGA) or `cg_b4` "Tock ticked with excitement at her feet."
  (CGB).
- **M11.** `e_set_av` (other node `av_risk`): "Far below, Tock ran in worried circles, ticking hard." In `av_risk` "Tock
  clung tight to her collar" as she climbed; no parting is shown.
- **M12.** `e_set_ds`: "Down below, Tock squeaked and squeaked" while she hangs on the catwalk; and `e_set_cg`
  (`c_open > c_start_cg > c_cg_x0 > c_cg_risk > c_cg_fail`): "tap on the glass to Tock on the far side". Tock rode
  with her into both risks; how he got elsewhere is not shown.
- **M13.** `e_set_sv` (other node `sv_risk`): "Gently and blindly, it backed her into the far corner of the hall." She
  was on the horizon-wall walkway, "just a thin ledge between the painted sky and a long drop to the floor", with the
  elephant below.
- **M14.** `e_set_key`: "it latched shut fast behind her, penning her in the little dark stairwell with no way back
  up." The turnstile is "At the very bottom" of the stairs (`k_c1`); a latch below her does not block the stairs above.
- **M15.** `fh_dawn_s1`: "It spilled little by little across the sleeping animals all around them." She is on "the
  great spring-room floor", a machine room; the animals are out in the halls.
- **M16.** `fh_fx_whale`: "She picked the biggest of them all, a vast copper whale drifting high above" and, three
  sentences on, "There was a winding-place low on its side, just within reach if she stood on her toes."
- **M17.** `e_win_mouse`: "a dozen small helpers"; `fh_sec_m2` just said "Dozens of them lay curled up small and
  still."
- **M18.** `e_set_cabinet`: "to tell Keeper Fettle in the morning that she had been too impatient". His letter in
  `n_shop` says "He had been taken poorly, it said, and could not come"; other endings have him come home "at last" or
  hear "later".
- **M19.** `fh_sec_j2`: "Page by page, Nia read how Keeper Fettle had built the whole menagerie himself." On the
  portrait route she has seen earlier keepers: `k_b1` "Old caretakers looked down at her from their frames. They were
  men and women in oil-stained aprons, each holding some little clockwork creature with pride.", with Fettle as "The
  last portrait in the row". A line of predecessors with clockwork creatures sits badly with one man building them all.
  Witness: `K > c_key_b > c_k_b1 > c_k_b2 > c_k_b3 > c_spring_a > c_s_a1 > c_s_a2 > c_s_a3 > c_shop_a > c_p_a1 >
  c_p_a2 > c_p_a3 > c_hub_sec > c_sec_j > c_sec_j1`. Minor because the earlier keepers could be read as tending his
  work.
- **M20.** `fh_sec_j2`: "He made the brass larks first, when he was young." `fh_sec_c3`: "stood the very first
  clockwork animal Fettle ever made. It was a small brass rabbit". Not co-reachable (sibling branches under
  `fh_sec1`); no single reader meets both. Witnesses `H > c_hub_sec > c_sec_j > c_sec_j1` and `H > c_hub_sec >
  c_sec_c > c_sec_c1a > c_sec_c2`.
- **M21.** `e_set_shop`: "rattling off down a side track with the precious spare spring aboard." On this route the
  cart appears only as a possibility in `p_c1` ("That lever could send a loaded cart speeding straight back to the
  spring-room") and no loading is shown.

## Class tally

| Class | Blocker | Should-fix | Minor | Total |
| --- | ---: | ---: | ---: | ---: |
| `unestablished_fact_on_route` | 1 | 12 | 1 | 14 |
| `location_or_physical_state` | 6 | 2 | 8 | 16 |
| `timeline` | 1 | 1 | 3 | 5 |
| `label_outcome_mismatch` | 0 | 0 | 5 | 5 |
| `other` | 2 | 0 | 2 | 4 |
| `two_backstories` | 0 | 0 | 2 | 2 |
| `repeated_reveal` | 0 | 1 | 0 | 1 |
| `cross_payoff_reference` | 1 | 0 | 0 | 1 |
| `state_contradiction` | 0 | 0 | 0 | 0 |
| `public_plant` | 0 | 0 | 0 | 0 |
| **Total** | **11** | **16** | **21** | **48** |

Pattern note: most should-fix items share one cause. The four wing chains each have an `a` branch that plants the
master key, the rotunda and the hum, and a `b` branch (plus both savanna branches) that does not, while the shared
`*_conv`, `*_conv3` and `n_key` nodes speak as if the plant always happened. Fettle has the same shape one level down
(named only on `c_key_b`).

## Checked, not defects

- The four `*_rec2 > *_deep` loops: each deep node reads correctly on a second arrival after a recovery.
- `av_b2` and `sv_b2` key hopes (a decoy feather, a keyring): Nia is locked in, so wanting keys needs no plant.
- "Both ways through the aviary brought Nia ..." and its siblings at `*_conv`: narrator summary, not a claim the
  reader saw both ways.
- `n_key` itself on AVA, DSA and CGA: the master key is planted there (`av_a3`, `ds_a3`, `cg_a3`).
- `n_spring` on all three `k_*` branches: the master works, the broken mainspring and the three offers are consistent.
- `n_shop` on `s_b*`: the mending book's hidden-workshop drawing and the door match.
- `fh_rw_cl1` "In his notes he had drawn a small helper gear": read as part of the "careful drawings" the letter
  reports, not a new object.
- `fh_fx_bird`: the lark's keyhole is too small for the master key and a winder is found there; consistent.
- `e_win_bird` "smiled his tired kind smile" on routes without `k_b2`: plain description, not a callback.
- `n_open` premise (missed the last bus, then shut inside the museum): a thin causal link, accepted as the premise.
- `ds_conv2` "out of the cramped dark" on DSA (mapped corridors rather than the crawl passage): close enough.
- Endings `e_set_rw`, `e_set_dawn`, `e_neu_dawn`, `e_win_all_quiet`, `e_win_note`, `e_win_journal`,
  `e_win_cabinet`, `e_win_one`, `e_win_clever`, `e_win_lion`, `e_win_whale`, `e_win_fly`, `e_win_all`: reread in flow,
  nothing beyond M8 (dawn).
