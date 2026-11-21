# Second-reader continuity findings: the-vanishing-orchard (WP-0.4, control book)

- Book: `out/the-vanishing-orchard.filled.json` (pre-fix sha256 `75fa2655...` per the WP-0.3 plan; pre-fix text at
  commit `846d9fc`). Plan: `out/the-vanishing-orchard.plan.json`.
- Reader: a second agent that did not write the plan, 2026-11-21. (Written to the repo by the orchestrator from the
  reader's report, because the harness refused the reader's own write of this file.)
- Method: every reachable configuration played with `StoryEngine` (`start`, `visible_choices`, `choose`). The book
  declares no variables, so every node has exactly one state (`{}`): 178 configurations of 178 nodes, reached over
  2,576 complete routes. Each route was walked against the plan's known-on-entry sets (union of `establishes` of the
  nodes visited before), and every passage and label was read for plain contradictions the plan missed.
- Control rule (D3): only continuity defects are fixed. Agency problems are listed at the end and left open by design.
- State for every finding below: `{}` (no variables). Routes are written as choice ids.

## Backstory decision

1. **Grandmother.** Chosen: she went into the spring forty years ago, before Rowan was born; Rowan never met her and
   knows her face only from photographs. Supported by kee_a_p3, kee_conv, rec_conv, b2k_p1, b2kt_p1, b2kt_p3,
   cel_t_p3, n_b5_2 and both grandmother endings (e_all_grandmother, e_all_rest), which cannot be made true any other
   way. The opposing reading (teen Rowan knew her) rested on four phrases (pho_conv, cel_t_p3, pho_t_p1, b2t_p1/e_b2tb).
2. **Childhood.** Chosen: born in Alderwick, carried away as a small child, raised elsewhere. Supported by n_open (on
   every route: "the orchard town where she was born"), b3v_p2, fin_one_1, fin_one_2, e_b3wn and every "grew up
   elsewhere" line (rec_a_p3, rec_t_p3, b1at_p3, n_b2). Only kee_t_p1 ("never planted here") and b1at_p1 opposed it.
3. **Cadence.** Chosen: the orchard lease renews the bargain once every fortieth year (the frost of a renewal year
   sets it for another forty), and under it the tree was given one willing name, a keeper, a year. This keeps every
   "fortieth year" and "another forty years" line (rec_b_p2, rec_b_p4, rec_conv, cel_t_p4, n_b4, e_one_hesitate) and
   the cord with "coil upon coil" of keeper knots (kee_b_p1 to kee_b_p4), which a forty-year keeper would contradict.
4. **Time of day.** Chosen: a morning arrival, afternoon investigation, dusk at the square, the frost night at the
   spring, dawn after it. One change at n_open fixes six afternoon passages.

## Findings (pre-fix) and fixes

Severity: **B** blocker (plain contradiction a child can meet on one route), **S** should-fix (fact asserted that the
route never established), **M** minor.

| # | Sev | Node | Route (example) | Quoted sentence (pre-fix) | Why wrong | Fix applied |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | B | pho_conv, cel_t_p3 | c_n_start_3 > c_pho_entry_2 > ... > c_pho_bdec_1; c_n_start_4 > ... > c_cel_conv_1 > c_cel_t_p1_1 > c_cel_t_p2_1 | "decades younger than Rowan had ever known her" | The grandmother went into the spring forty years ago; teenage Rowan cannot have known her | "younger than in any photograph Rowan had ever seen of her" (both nodes) |
| 2 | B | pho_t_p1 | any pho route into pho_conv | "the same careful looping script Rowan half remembered from birthday cards long ago" | Same contradiction | The message is "signed with her grandmother's name, in a careful looping script" |
| 3 | B | b2t_p1 | c_n_b2_1 | "the taste of her grandmother's kitchen on a Sunday" | Same contradiction | "the taste of Sunday mornings in the kitchen at home" |
| 4 | B | e_b2tb | c_n_b2_1 > c_b2t_p1_1 > ... > c_b2t_m_2 | "her whole memory of her grandmother, all of it at once, the Sunday kitchens and the birthday cards and the warm looping voice"; "She had traded the very person she was trying to honour" | Grandmother contradiction, and the Sunday memory was already traded at b2t_p1 on this route (b2t_m: a traded memory is gone for good) | She gives "every memory she had of her family ... the birthdays and the bedtime voices"; "She had traded away the very people who had made her"; dropped "whose kitchen had smelled of apples" |
| 5 | B | kee_t_p1 | c_n_start_2 > ... > c_kee_conv_1 | "You were never planted here." | n_open (every route) says she was born there; b3v_p2, fin_one_2, e_b3wn give her early years there | "You were carried off before you could take root here." |
| 6 | B | b1at_p1 | c_n_b1_1 > ... > c_b1a_dec_1 | "her childhood banked in streets the orchard had never owned"; "because she had put down no roots here" | Same | "carried away as a small child ... nearly all her childhood"; "taken away before she could put down roots here" |
| 7 | M | b1at_p3, b2tt_p2 | b1a and b2t routes | "No one born in the town"; "Anyone born in Alderwick" | Rowan was born in the town | "raised" |
| 8 | M | fin_one_1 | c_n_b4_3 | "the neighbour girl she had grown up beside" | She left as a small child | "played beside as a small child" |
| 9 | S | b1bt_p1, n_b2 (and every "outsideness" line) | c_n_start_3 or c_n_start_4 > ... > c_n_b1_2 > ... > c_b1b_dec_1 | "her untaken memory", "her outsideness" | pho and cel routes never said she grew up away | n_open now states it on every route: "where she was born, and which her family had left when she was very small" |
| 10 | B | kee_b_p1 | c_n_start_2 > c_kee_entry_2 | "On a nail beside Odile hung a length of knotted cord"; "The nail it hung from had been rubbed smooth" | kee_entry, one node earlier, has the cord "looped at her belt" | Rowan asks "about the knotted cord at Odile's belt"; "Its coils had been rubbed pale by generations of hands. Odile unhooked it and laid it in Rowan's lap" |
| 11 | S | kee_conv | c_kee_entry_1 > ... > c_kee_adec_1 | "Odile drew the cord back through Rowan's hands" | On the kee_a route Rowan never held the cord | "Odile ran the knotted cord through Rowan's hands" |
| 12 | B | kee_t_p3 vs n_b3 | kee route > ... > n_b3 | "Her legs would no longer carry her down the steep hill" | n_b3 has Odile come down to the spring on Teo's arm | "Her legs could manage the steep hill only slowly now ... she would hold Rowan back when speed was everything" |
| 13 | B | kee_a_p3 vs rec_b_p4 vs n_b1 | kee_a route through n_b1; rec_b route through n_b1 | "each keeper had fed the tree one willing name a year"; "Once in every fortieth year ... the town promised that the orchard should keep a little in exchange for a fruitful season"; "letting the root keep a little of them each season" | Three cadences, two of them on one route | kee_a_p3: "the tree had been given one willing name a year. One keeper, chosen or offered"; rec_b_p4: "the town renewed its promise that the orchard should keep a little in exchange for each fruitful season"; n_b1: "year by year" |
| 14 | B | n_open vs afternoon passages | c_open > c_n_start_4 > c_cel_entry_1 > c_cel_a_p1_1 | n_open "rattled away into the dusk" then cel_a_p1 "the mild autumn afternoon" (also rec_t_p4, pho_clue, e_cel_a, e_cel_b) with no night between | Impossible on every route | n_open: "The morning bus ... rattled away down the valley road" |
| 15 | S | e_b2ta | c_n_b1_3 > ... > c_b1ct_p3_1 > c_n_b2_1 > ... > c_b2t_d1_2 | "climbed back up the frozen stair into the mild afternoon" | On the b1c route it is already dusk (b1c_p1, e_b1c) | "out into the cold orchard air" |
| 16 | M | n_b5, fin_trade_2 | c_n_b4_1 > ... > c_n_b5_1; c_n_b4_4 > ... > c_fin_trade_2_1 | "its window golden in the dusk"; "lit golden against the dusk" | The next passages step into morning on the frost night | "in the first grey light"; "against the dark" |
| 17 | S | kee_t_p4 | kee route | "The first frost was only days away now" | The frost silvers the grass that same night (n_b3, n_b4) | "close now, perhaps no more than a night away" |
| 18 | B | n_b1 (all four entries) | c_n_start_1 > ... > c_rec_clue_1; c_n_start_3 > ... > c_pho_clue_1; c_n_start_4 > ... > c_cel_clue_1 | "And in her palm, hard and dark as a peppercorn, rested a withered seed, the token every keeper carries." | Only the keeper route gives her a seed; b1b_dec, n_b2 and later nodes rely on it on every route | Seed found in each route's own single-choice clue node: rec_clue (slips from the cellar-photo envelope), pho_clue (drops from behind her grandmother's photograph), cel_clue (lies beside the carved words); n_b1 drops the gloss "the token every keeper carries" (n_b2 explains it) |
| 19 | S | pho_a_p3, pho_b_p1, pho_b_p4, pho_t_p3, e_pho_a, e_pho_b, cel_b_p2, cel_t_p1, n_b1 and later | c_n_start_3; c_n_start_4 | "The Quiet had reached even into the memory of the machine" (and others) | The name is given only by Odile on the keeper route | n_start (every route) adds: "In her head she had already begun to call it the Quiet"; kee_a_p1: "Odile called it the Quiet, the same word Rowan had been using in her own head" |
| 20 | S | cel_a_p3, cel_a_p4, cel_t_p1 | c_n_start_4 > c_cel_entry_1 ... | "Odile's warning came back to her"; "the black spring Odile had described"; "understood what Odile had meant" | Rowan never meets Odile on a cel route | Odile references removed: "she saw that the cold below was not weather at all but something rising from whatever lay beneath"; "it made her think of black water far below"; "understood. The Quiet could not take her." |
| 21 | S | cel_b_p1, cel_b_p2, cel_b_p3, cel_b_p4 | c_n_start_4 > c_cel_entry_2 | "dropped it through the gap in the barklocked door"; "through the open door"; "Rowan opened the door fully" | The gap is chiselled only on cel_a; the living bar is never removed on cel_b | cel_b_p1 establishes a natural split in the bark "a little wider than her two hands"; cel_b_p2 "through the gap"; cel_b_p4 "levered the split bar out of its frame at last, the bark tearing like wet cloth" |
| 22 | M | cel_entry, cel_clue | cel routes | "every thread she had followed in Alderwick ended here" | On that route she followed one | "every thread that had tugged at her in Alderwick" (n_start's four threads) |
| 23 | S | e_cel_a, e_cel_b | c_cel_adec_2; c_cel_bdec_2 | "The register stayed blank"; "why the register had mattered" | The blank register is seen only on rec routes | "The deed hall's records went on losing their names"; "why the deed hall had mattered" |
| 24 | S | rec_clue | c_rec_entry_1 > ... > c_rec_t_p4_1 | "this time the door did not bar itself behind her" | The door is barred only in the ending e_rec_a, never on a route that reaches rec_clue | "The clerk let her out through the front door himself and wished her luck." |
| 25 | S | rec_conv, rec_clue | c_rec_entry_1 > ... > c_rec_adec_1 | "the name written on the latest clause"; "the fortieth-year clause" | The lease clause is found only on rec_b | rec_conv: "the name on the most recent renewal of the old orchard lease, inked forty years ago"; rec_clue: "the lease renewed forty years ago" |
| 26 | S | kee_a_p1, kee_b_p2 | c_n_start_2 > c_kee_entry_1; > c_kee_entry_2 | "That was why the register ran blank"; "the way the neighbours were gone from the clerk" | Register and clerk are records-branch only | "why the neighbours could not place the names on the memorial ... and why whole years seemed to have gone missing"; "the way the names on the memorial were gone from the town" |
| 27 | S | pho_t_p1 to pho_t_p4, pho_clue | c_n_start_3 > c_pho_entry_1 > ... > c_pho_adec_1 | "Rowan turned to the album's final page"; "carried the album back"; "the steady orchard album"; "a keeper's face waited in the album" | The album is found only on pho_b | pho_conv now notes the orchard photographs never flicker (true on both routes); the message is on the back of the grandmother's photograph; "steady orchard photographs/pictures"; pho_clue "a keeper's face had been swallowed from a christening portrait" |
| 28 | S | b1a_p3 | c_n_start_1/3/4 > ... > c_n_b1_1 > c_b1a_p1_1 > c_b1a_p2_1 | "exactly what the empty knot was waiting for" | The empty knot is shown only at kee_conv | "exactly what such a keeping cost" |
| 29 | S | b1bt_p2 | c_n_start_1/3/4 > ... > c_n_b1_2 > ... > c_b1bt_p1_1 | "The founders had fed the tree by taking grief from the living." | The grief bargain is told only on kee_a, b1a or b3w | "taking memory from the living" (n_b1 tells that on every route) |
| 30 | S | b2k_p1 (and the knot image through b2k_d1, b2k_m, e_b2ka, e_b2kb, b2kt_p2) | c_n_start_4 > ... > c_n_b2_2 | "The line of keepers had broken forty years ago ... a single knot in the long rope of guardians tied and never filled" | A recap of keeper-route facts; cel, pho and rec routes never saw the cord | Made a revelation: "the spring showed it to her. In the turning water she saw her grandmother walk down to this same spring forty years ago, the last of a long line of keepers ... like a knot tied in a cord and never filled"; b2k_d1 "knot in the line" |
| 31 | S | e_b2ka | c_n_start_1/3/4 > ... > c_b2k_d1_2 | "even Odile, the last keeper on Mabb Hill, had thinned to a name that only Rowan still remembered" | On those routes Rowan has never met Odile (n_b3 comes later) | "even the old keeper on Mabb Hill had begun to thin out of the town's memory" |
| 32 | M | b1ct_p3 > n_b3 | c_n_b1_3 > ... > c_b1ct_p3_1 > ... > n_b3 | "Rowan rose from the doorway with Teo beside her"; then n_b3 "Her cousin had come too" down the stair | Teo is already with her | "sent Teo running up Mabb Hill for the old keeper" (so he arrives with Odile at n_b3) |
| 33 | S | b3u_p1, b3u_p2 | rec, pho or cel route > c_n_b3_1 | "Teo's stubborn kind of love"; "Old Mr Hallet was among them, and the frightened clerk" | Teo's stubborn love is told only on kee or b1c; Hallet only on b1c; the clerk only on rec | "a stubborn kind of love"; "The young clerk from the deed hall was among them, and an old man with rheumy eyes" |
| 34 | B | n_b4 | c_n_b3_3 > ... > c_b3wt_p3_1 | "Behind her stood the gathered town, or else a single beloved face was held steady in her mind." | On the b3w route neither is true | "Odile and Teo were with her." (true on every route after n_b3) |
| 35 | B | fin_all_1, fin_all_2 | c_n_b3_2 or c_n_b3_3 > ... > c_n_b4_1 | "rushing from the gathered town"; "leading the frightened crowd"; "the whole town pulling as one" | The town gathers only on b3u | "rushing from the town toward the water"; "calling the names of the lost"; "With the three of them pulling as one and the town's remembering pouring in behind them" |
| 36 | B | fin_share_1 (and fin_share_2, e_share_lost) | c_n_b3_2 or c_n_b3_3 > ... > c_n_b4_2 | "Rowan asked the gathered town for something stranger than sacrifice." | No crowd on b3v or b3w | "Townsfolk filled the stair behind her now, more arriving all the time, drawn down by a pull none of them could name, and Rowan asked them ..." |
| 37 | S | n_b5 label, n_b5_2 | c_n_b4_2 > c_fin_share_1_1 > c_fin_share_2_1 | label "Notice the one gap the flood did not reach."; "the great rising flood of remembering had passed her by"; "the one soul the flood had not lifted" | The flood happens only on fin_all | Label "Notice the one gap the remembering did not reach."; "the great rising tide of returning years"; "the one soul the returning years had not lifted" |
| 38 | M | n_b5_2 | any route to n_b5_2 | "the memory the root had held the longest and the deepest" | Two hundred years of keepers were held longer | "held the deepest" |
| 39 | M | e_all_grandmother | ... > c_n_b5_2_1 | "the old keeper came up out of the black water" | cel_t_p3 shows her young in the water | "the lost keeper" |
| 40 | M | e_one_hesitate, e_one_saved | c_fin_one_1_2; c_fin_one_2_1 | "a face in a fading photograph"; "Neighbours who had passed her fading photograph a hundred times" | No photograph of the girl exists on any route | "a face that no one but Rowan would mourn"; "passed her family's door" |
| 41 | M | e_trade_photo | c_n_b4_4 > ... > c_fin_trade_2_3 | "she held one thing back, a single photograph of the orchard gate" | The photograph appears from nowhere on kee and cel routes | Introduced in place: "the one photograph she had brought with her from home, a picture of the orchard gate taken the year she was born" |
| 42 | M | kee_conv | kee_a route | "you will need it before the frost" | The frost deadline is not yet told on kee_a | "before the first frost" |

### Read but not fixed (not plain contradictions)

- "Last keeper" names both Odile (the last living orchard-keeper) and the grandmother (the last keeper to pay); the
  book distinguishes them by "to pay the price". Left.
- The bargain's motive is grief relief (kee_a_p2, b1a_p2, b3w_p2) and a fruitful harvest (rec_b_p4, n_b1); the book
  presents both and never denies either. Left; the plan's `truth` records both.
- n_b5's gap-toothed girl who "won every game of conkers" is a callback only b3v readers catch; it stands alone for the
  rest. Left.
- Unpaid setups (the margin word "enough", the blossom and lock of hair, the mill-fire children, the clerk's daughter)
  are never returned to. Not a contradiction. Left.
- "the frozen stair" on routes where frost on the stair was not shown earlier: description, not presupposition. Left.

## Agency problems recorded, never fixed (control)

From `scripts/check_prose_craft.py` and the read: 3 of 9 merge nodes open by saying the route did not matter (n_b1,
n_b2, n_b4); 23 of 38 decisions recap their options; label sameness top-3 share 54.7 percent ("Go on.", "Follow it down
toward the root.", "Carry what you found to the cider house."); one moral tag (e_trade_greed); n_b4 offers all four
finales on every route regardless of the act-three choice; no variables, so no early choice changes a later option;
many setbacks within three decisions of n_start.

## Post-fix re-read

All 178 configurations replayed on the fixed book over all 2,576 routes. Every plan node's `requires` is in its
known-on-entry set on every route, no two contradicting facts are known together on any route, and the passage-level
read found no remaining plain contradiction. **Open continuity findings: 0.** Agency findings above stay open by design.
After the pass: `run_story_gate.py` exit 0 (81 findings, was 82; RL-13 17 to 16), `run_fill_gate(...).blocked` False;
`check_fill_integrity.py` markers, words and fill-rate pass, structure fails as before the pass (skeleton
`metadata.narrative_person` drift, left as found).
