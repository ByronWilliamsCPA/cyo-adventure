# WP-1.6 second read: The Clocktower Cipher

Second-reader continuity pass over `out/the-clocktower-cipher.filled.json` (band 10-13), sha256
`2d476787f5e61104d2e8f87765820496488f2780d3c08cd19cfcc7516b305bb5` (verified before the read). 26 nodes,
35 choices, 8 endings, no variables. The reader did not write the book, did not write or read a Story Plan, and did
not read or run the plan checker. This file is the reference truth for the WP-1.6 blind test. (Written to the repo
by the orchestrator from the reader's report, verbatim, because the harness refuses subagent writes of evidence files;
see `AL-807`.)

**Method (WP-0.4).** Every route played depth first from `n_open` with `StoryEngine` (`start`, `visible_choices`,
`choose`): **300 complete routes**, **26 reachable (node, state) configurations** (one per node, because the book
declares no variables), 26/26 nodes and 8/8 endings reached, no dead ends. Every body and every choice label was
then read against every route that reaches it. The book has three merge nodes where route history diverges:
`n_inside` (six entry routes), `n_clockface` (four) and `n_vault` (three). Because there are no variables, the
objects and knowledge a route hands the hero (decoded note, brass key, keeper's story and the name Eda, keeper's
token, cipher wheel, oil can) are untracked, and no choice is gated on them; each finding below was replayed with
the engine and the route checked for the absence of the node that would have established the fact (scripts in
`tmp_cleanup/fc-clocktower/`).

Entry routes into `n_inside`, and what each shows:

| Route | Choices from start | Shows |
| --- | --- | --- |
| A | `c_open > c_examine > c_note_key > c_keyhunt_in` | note decoded by hand (key, grate), brass key |
| B | `c_open > c_examine > c_note_inside` | note decoded by hand; grate never shown |
| C | `c_open > c_door > c_door_force` | side door forced |
| D | `c_open > c_door > c_door_window` | window climb, high wooden landing |
| E | `c_open > c_keeper > c_keeper_enter` | keeper met, offers to unlock |
| F | `c_open > c_keeper > c_keeper_story > c_story_in` | keeper's story: Eda, "Set the clock right", token |

Only `n_study` gives the cipher wheel and only `n_pendulum` (via `c_pendulum_oil`) gives the oil can.

Severity: blocker (plain contradiction, or a fact false on the route), should-fix (unshown presupposition), minor.
In the witness routes, `P` abbreviates `c_open > c_examine > c_note_inside` (route B, the shortest entry; routes C
and E tie at three choices and show the same defects unless stated).

## Blockers

| ID | Node | Other nodes | Class | Routes affected |
| --- | --- | --- | --- | ---: |
| B1 | `n_clockface` | `n_setcorrect`, `n_backpanel` | `unestablished_fact_on_route` | 216 of 288 via `n_clockface` |
| B2 | `n_setjam` | `c_jam_oil`, `n_vault` | `unestablished_fact_on_route` | 54 |
| B3 | `n_end_stuck` | `c_jam_stuck` | `state_contradiction` | 6 |
| B4 | `n_stairs` | `n_backpanel`, `n_end_caught` | `unestablished_fact_on_route` | 150 |
| B5 | `n_stairs` | `n_keeper_story` | `unestablished_fact_on_route` | 72 |
| B6 | `n_end_library` | `n_open`, `n_end_hero` | `location_or_physical_state` | 6 |

**B1. The hero "had the cipher wheel" on routes that never found it.** `n_clockface`: "She had the cipher wheel and
could work out the exact setting, slow and sure." Also `n_setcorrect` "Mara worked the cipher wheel one last time"
and `n_backpanel` "She set to work with the cipher wheel." Witness: `P > c_inside_stairs > c_stairs_face`. The wheel
exists only in `n_study`; the stairs, pendulum and basement routes never visit it. On routes C to F Mara never
decoded any of the note by hand either, so the "hour and minute Eda had hidden in the note" at `n_setcorrect` has
no source at all on those routes.

**B2. The oil can is used on routes that never took it.** `c_jam_oil` "Free the jammed gears with the oil can." is
always visible and leads to `n_vault`, while `n_setjam` on the same page says: "Without it, the mechanism was simply
stuck, wedged tight by their own impatience, and there would be no opening it tonight." Witness:
`P > c_inside_stairs > c_stairs_face > c_face_jam > c_jam_oil`. The can is only picked up at `n_pendulum`; the
stairs, study and basement routes reach `n_setjam` without it and still open the vault with it.

**B3. "Without the oil can" when the route took the oil can.** `n_end_stuck`: "They worked at the jammed gears with
everything they had, but without the oil can there was nothing to ease the locked teeth, and the mechanism would
not give." The choice that leads here, `c_jam_stuck`, reads "Give up; the gears will not move." Witness:
`P > c_inside_pendulum > c_pendulum_oil > c_face_jam > c_jam_stuck`. On this route the friends crossed the ledge at
`n_pendulum` specifically to grab the oil can.

**B4. Mara says the name "Eda" on routes where nobody told her.** `n_stairs`: "\"Eda left these all over,\" Mara
guessed, pocketing it." Also `n_backpanel` "\"Eda and her layers,\" Mara said" and `n_end_caught` "\"Eda thought of
everything,\" Mara groaned". Witness: `P > c_inside_stairs`. The name is given only by the keeper at
`n_keeper_story` (route F). On routes A to E the character speaks a name she cannot know.

**B5. A token "exactly like the one the keeper had described".** `n_stairs`: "He knelt and pried it up, and
underneath, wedged in the gap, sat a small brass gear-token, exactly like the one the keeper had described."
Witness: `P > c_inside_stairs`. The keeper describes no token on any route. On routes A to D he is never met; on E
he mentions nothing of the kind; on F (`c_open > c_keeper > c_keeper_story > c_story_in > c_inside_stairs`) he hands
Mara a token with only "You'll know when you need this", which is giving, not describing. Mara's "Eda left these
all over" then treats a first find as a known pattern on routes A to E.

**B6. The frozen, silent clock tolls the hour.** `n_end_library`: "When the great bell finally tolled the hour, deep
and sudden, they jumped." Witness: `P > c_inside_study > c_study_logs`. `n_open` establishes "The old clocktower had
not chimed in years. Its great brass hands were frozen at twelve," and `n_end_hero` "chimed true for the first time
in years". On this route nobody touches the clock; the same ending says "They had not set the clock."

## Should-fix

| ID | Node | Other nodes | Class | Routes affected |
| --- | --- | --- | --- | ---: |
| S1 | `n_study` | `n_inside`, `n_basement`, `n_setcorrect`, `n_vault`, endings | `unestablished_fact_on_route` | 240 |
| S2 | `n_inside` | `n_study` | `unestablished_fact_on_route` | 250 |
| S3 | `n_backpanel` | `n_end_library` | `unestablished_fact_on_route` | 102 |
| S4 | `n_setjam` | `n_end_stuck` | `unestablished_fact_on_route` | 72 |
| S5 | `n_keeper_story` | none | `unestablished_fact_on_route` | 50 |
| S6 | `n_vault` | `n_setjam`, `c_jam_oil` | `unestablished_fact_on_route` | 72 |
| S7 | `n_end_keepsake` | `n_vault`, `c_vault_keep` | `unestablished_fact_on_route` | 72 |
| S8 | `n_end_timeout` | `n_open` | `unestablished_fact_on_route` | 24 |

**S1. Eda, and a woman clockmaker distinct from the clockkeeper, presupposed in narration.** `n_study`: "She turned
the discs and felt the cipher's logic fall open in her mind; now she could decode anything Eda had left." Witness:
`P > c_inside_study`. Same presupposition in `n_inside` "the clockmaker's study" (and label `c_inside_study`),
`n_basement` "Eda's genius", `n_setcorrect` "the way Eda wanted", `n_vault` "Eda's design", `n_end_library`,
`n_end_timeout` "they would do it Eda's way: slowly", `n_end_secret` and `n_end_hero`. Only route F says who Eda is,
that she built the tower, and that her test rewards patience; elsewhere the reader has met only "the old
clockkeeper", so "the clockmaker" reads as him and "Eda's way: slowly" leans on an account the route never gave.

**S2. The goal "set the cipher" at the clockface stated before anyone learns it.** `n_inside`: "A spiral stair climbed
toward the great clockface overhead, where they would have to set the cipher." Also Theo at `n_study`: "\"We came to
set the clock,\" he reminded them." Witness: `P`. The note's decoded lines (`n_note`) are about a key and a grate;
the only source for setting the clock is the keeper's "Set the clock right, and it opens" on route F.

**S3. "The vault" expected before any vault is mentioned.** `n_backpanel`: "Together they worked the panel free,
revealing not the vault they expected but a second, smaller puzzle". Also "which would surely open the main vault",
and `n_end_library` "They had not found the vault." Witnesses: `P > c_inside_stairs > c_stairs_face > c_face_panel`;
`P > c_inside_study > c_study_logs`. The vault is first named at `n_setcorrect`, a sibling these routes never visit;
on route F the keeper even says "She didn't trust a vault or a safe."

**S4. "The oil can from the pendulum ledge" on routes that never saw it.** `n_setjam`: "If they had the oil can from
the pendulum ledge, they might free the jammed gears before any harm was done." Witness:
`P > c_inside_stairs > c_stairs_face > c_face_jam`. `n_inside` describes the pit and the ledge but no can; the can is
shown only at `n_pendulum`. `n_end_stuck` "without the oil can" carries the same definite reference.

**S5. "The key" on the one route that has no key.** `n_keeper_story`: "The cipher, the key, the warnings, all of it
was Eda speaking, choosing her finders." Witness: `c_open > c_keeper > c_keeper_story` (the only route to this node).
No key has been found and the note has not been decoded on this route.

**S6. The vault opens, and the tower counts as solved, after a forced wrong setting.** `n_vault`: "They had solved
the tower; now they had to decide what kind of finders they were." Witness:
`P > c_inside_pendulum > c_pendulum_oil > c_face_jam > c_jam_oil`. At `n_setjam` Theo forced the hands "to a guess"
and jammed them; oiling the gears frees them but never sets the right time, and nothing shows a panel opening or the
friends entering, yet `n_vault` opens with them inside. "Solved" is false on this route.

**S7. A sealed letter folded "back" and a secret kept unread.** `n_end_keepsake`: "Then Mara folded the letter back
along its old creases and set it down." Witness:
`P > c_inside_stairs > c_stairs_face > c_face_correct > c_correct_vault > c_vault_keep`. `n_vault` shows "A folded
letter, sealed with wax." Only `n_end_hero` breaks the seal; on this route nobody opens or reads it, yet it is
folded back, and the friends keep "the clockmaker's secret" (label `c_vault_keep`) and call it "a real mystery,
solved" without having learned what the letter says.

**S8. "The lock-up bell" that nobody established.** `n_end_timeout`: "\"That's the lock-up bell,\" Mara realized."
Witness: `P > c_inside_stairs > c_stairs_face > c_face_random`. No lock-up bell appears on any route, and the bell
is "jolted awake by the mechanism" of a tower that "had not chimed in years", so it cannot also be a familiar
lock-up signal.

## Minor

| ID | Node | Other nodes | Class | Witness |
| --- | --- | --- | --- | --- |
| M1 | `n_clockface` | `n_inside`, `n_keeper_story` | `repeated_reveal` | `P > c_inside_stairs > c_stairs_face` |
| M2 | `n_inside` | `n_window` | `location_or_physical_state` | `P` |
| M3 | `n_inside` | `c_note_inside`, `n_keeper_story` | `other` | `P`; route F |
| M4 | `n_window` | `n_open`, `n_note` | `unestablished_fact_on_route` | `c_open > c_door > c_door_window` |
| M5 | `c_keeper_enter` | `n_inside` | `label_outcome_mismatch` | `c_open > c_keeper > c_keeper_enter` |
| M6 | `c_vault_share` | `n_end_hero` | `label_outcome_mismatch` | `P > ... > c_correct_vault > c_vault_share` |
| M7 | `c_vault_grab` | `n_end_caught` | `label_outcome_mismatch` | `P > ... > c_correct_vault > c_vault_grab` |
| M8 | `c_panel_secret` | `n_backpanel` | `other` | `P > c_inside_stairs > c_stairs_face > c_face_panel` |
| M9 | `n_setjam` | `n_pendulum` | `state_contradiction` | `P > c_inside_pendulum > c_pendulum_oil > c_face_jam` |
| M10 | `n_end_giveup` | `n_pendulum` | `location_or_physical_state` | `P > c_inside_pendulum > c_pendulum_giveup` |
| M11 | `n_end_giveup` | `n_start`, `n_inside` | `timeline` | `P > c_inside_pendulum > c_pendulum_giveup` |
| M12 | `n_clockface` | `n_pendulum` | `location_or_physical_state` | `P > c_inside_pendulum > c_pendulum_oil` |
| M13 | `n_end_library` | `n_inside` | `location_or_physical_state` | `P > c_inside_study > c_study_logs` |
| M14 | `n_keeper_story` | `n_stairs` | `other` | route F `> c_inside_stairs >` any ending |

In M6 and M7, `...` stands for `c_inside_stairs > c_stairs_face > c_face_correct`.

- **M1.** `n_clockface`: "\"You set the time named in the cipher,\" Mara realized, \"and something happens.\"" A
  realization of what `n_inside` already narrated on every route ("where they would have to set the cipher"), and on
  route F of what the keeper said outright ("Set the clock right, and it opens").
- **M2.** `n_inside`: "At the foot of the landing the tower opened into a tall, shadowed hall, the spine of the whole
  machine." Only route D shows a landing (`n_window`); routes A, B, C, E and F arrive through a ground-level door or
  grate, so "the landing" has no referent.
- **M3.** How they get in is never shown on two routes. Route B's label `c_note_inside` "Try the loose grate the note
  mentions." goes straight to `n_inside`; no grate is found or crossed. On route F the front door is "locked tight"
  (`n_open`) and the keeper only "pointed them toward the door" (`n_keeper_story`); the unlocking he offered at
  `n_keeper` is never done on this route.
- **M4.** `n_window`: "Lin followed more slowly, testing each grip, while Mara waited below with the note." On route D
  the note is still pinned to the door (`n_open`); taking it down is shown only at `n_note`.
- **M5.** `c_keeper_enter` "Go inside with the keeper." `n_inside` has no keeper in it and never says he left; he
  had already said he "would not climb those stairs himself".
- **M6.** `c_vault_share` "Decode the final message and bring it to the town." `n_end_hero`: "It was a message to the
  town, written in plain words at last". Nothing is decoded.
- **M7.** `c_vault_grab` "Stuff the treasure in your bag and run." No bag exists on any route, only Theo lifts the
  dish, nobody runs, and the label switches to second person in a third-person book.
- **M8.** `c_panel_secret` "Slip into the clockmaker's hidden workshop." The page offers only "the faint scratched
  sequence into whatever lay beyond it" and says it "led somewhere Eda had not advertised at all"; the label names a
  destination the characters cannot know until `n_end_secret` reveals it.
- **M9.** `n_setjam`: "If they had the oil can from the pendulum ledge, they might free the jammed gears before any
  harm was done." On the pendulum route they hold it; the conditional reads as if they might not.
- **M10.** `n_end_giveup`: "They backed carefully away from the pit and returned to the safer stairs." and "They
  climbed back down and out into the cool evening". On routes other than D they were never on the stairs, and the pit
  is on the ground-floor hall, so there is nothing to climb back down from.
- **M11.** `n_end_giveup`: "as the light faded they realized they had run out of time to solve the rest". Minutes
  after entering, on an afternoon that "stretched ahead of them, gold and quiet" (`n_start`), with no time shown
  passing and the spiral stair still open to them.
- **M12.** Arriving at `n_clockface` ("At last they stood behind the great clockface") straight from the ledge in
  the ground-floor pendulum pit. The ledge runs "into the dark"; the clockface is "overhead" and reached elsewhere
  only by the spiral stair or the basement ladder. No climb is shown.
- **M13.** `n_end_library`: "the clockkeeper's voice floated up the stairwell, calling them down". The study is "a low
  door ... to one side" of the ground-floor hall (`n_inside`); there is no stairwell between them and the keeper.
- **M14.** Two tokens with no payoff. `n_keeper_story` "You'll know when you need this." and `n_stairs` "Little keys
  for little locks." No passage on any route uses a token.

## Class tally

| Class | Count | IDs |
| --- | ---: | --- |
| `unestablished_fact_on_route` | 13 | B1, B2, B4, B5, S1, S2, S3, S4, S5, S6, S7, S8, M4 |
| `state_contradiction` | 2 | B3, M9 |
| `two_backstories` | 0 | none |
| `public_plant` | 0 | none (no variables) |
| `cross_payoff_reference` | 0 | none |
| `label_outcome_mismatch` | 3 | M5, M6, M7 |
| `repeated_reveal` | 1 | M1 |
| `timeline` | 1 | M11 |
| `location_or_physical_state` | 5 | B6, M2, M10, M12, M13 |
| `other` | 3 | M3, M8, M14 |
| **Total** | **28** | 6 blockers, 8 should-fix, 14 minor |

The book declares no variables, so `state_contradiction` here means a passage says the hero lacks an object the
route gave them (B3, M9); claims of holding an object the route never gave are filed as
`unestablished_fact_on_route` (B1, B2).

## Checked, not defects

- The keeper arriving in endings on routes that never met him (`n_end_library`, `n_end_stuck`, `n_end_timeout`,
  `n_end_caught`): `n_start` places him nearby, `n_keeper` shows he expects note-finders, and the caught and timeout
  bells explain his coming.
- A vault despite the keeper's "She didn't trust a vault or a safe": the vault sits behind the puzzle, consistent with
  "She trusted a puzzle."
- `n_study` "That's how you read the code" on routes A and B, where Mara decoded part of the note by hand: she got
  only two lines ("The second line was harder"), so the wheel extends rather than repeats the reveal.
- The wobbly tread near the top of the spiral stair (`n_stairs`) on route D: the window landing is not stated to be on
  the same stair.
- Brass key and front door on route A (`n_keyhunt`, `c_keyhunt_in`); side door and window on routes C and D;
  consistent with `n_open` and `n_door`.
- Character traits (Mara puzzles, Theo climbing and impatience, Lin caution) and Theo's apology in `n_setjam` and
  `n_end_stuck`, stable on every route.
- Afternoon to evening progression on every route except as noted in M11.
- `n_end_hero` charter and spring backstory against the keeper's "something the town had nearly lost"; "The clock,
  repaired now" against the frozen clock of `n_open`.
- Lin's lit oil lantern (`n_basement`) on basement, jam, stuck routes while `n_end_stuck` says "nothing to ease the
  locked teeth": a gap a sharp reader may notice, but no passage asserts the lantern oil could serve; not counted.
- `n_end_keepsake` "whenever the clock chimed" on the panel route, where the clock was never set: years later, a
  repair by others is plausible; not counted.
- `c_window_in` "Drop down into the tower." after the friends are already inside: matches "down, into the heart of it".
- "the warnings" (plural) in `n_keeper_story` against a single KEEP OUT sign, and a town seen through "frosted glass"
  at `n_clockface`: loose wording, not counted.

Out of scope and not counted: three ending titles are unfilled placeholders (`{END_LIBRARY_TITLE}`,
`{END_SECRET_TITLE}`, `{END_HERO_TITLE}`).
