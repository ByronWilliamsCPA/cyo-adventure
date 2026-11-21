<!-- markdownlint-disable MD038 -- witness routes are code spans wrapped across lines -->

# WP-1.6 second read: The Thornwood Trial

Second-reader continuity pass over `out/the-thornwood-trial.filled.json` (fresh-corpus confirmation, band 13-16). Book
sha256 `cd3f45ad0d3d8075e57fdd203612a66ce59d65f1b2613c5ba7419caaf165476d` (verified before reading): 376 nodes, 396
choices, 115 endings (4 positive), no variables. The reader did not write the book, did not read or run the Story Plan
checker or `src/cyo_adventure/storyplan/`, and wrote no plan. (Written to the repo by the orchestrator from the reader's saved copy, because the harness refuses subagent
writes of evidence files; see `AL-807`.)

## Method

**Routes and configurations.** Every reachable configuration was enumerated with `StoryEngine` (`start`,
`visible_choices`, `choose`). With no variables, a configuration is just a node: 376 of 376 reachable, no dead ends,
no orphans. The graph is a DAG with 1,046,836 complete routes (longest 78 choices), too many to replay one by one.
Per-node inbound routes were counted by topological DP instead (up to 62,500 routes into `f_dusk`, `f_name` and each
winning ending). Only 19 nodes have more than one parent: `h_maze` (4 approaches), the five later hubs, `f_dusk`, and
`b_*_3` / `b_*_4` in each area (rejoins from the warden runs). Because nothing carries state, every route into a node
arrives with the same facts as any other route through the same parents. So the read checked each node against each
distinct inbound path shape: spine, each warden run, and each approach.

**Structure.** The book has an opening (`n_open`, `n_start`, four approaches `ap_1`-`ap_4`), then six areas in a fixed
order (Bramble Maze, Sunken Grove, Beast-Warren, Elder-Tree Council, Far Ridge, Far Gate), then the finale (`f_dusk`,
`f_name`, `f_wild`, seven endings). Each area has a hub `h_*`, five spine nodes `b_*_1`-`5`, three warden runs
`rc_*_k_1`-`3` that rejoin the spine or the next hub, eleven excursion chains `x_*` of two or three nodes, and
eighteen setback endings. Spine, run and chain bodies come from per-area templates; the setback endings come from six
template families of 18 nodes each.

**Reading.** All 376 bodies and 396 choice labels were read in full (about 25,400 words), area by area, in route order
from the hub. Each was checked against its inbound path, the hub text before it, and the book-wide clock (dawn at the
eaves, dusk at the ridge and gate). Every ending was then classified by template family against its entry label and
the chain text in front of it. Every finding below was replayed with `StoryEngine` from `n_open` along the witness
route given, and every quotation was checked verbatim against the node body by script. Read time: about 11 minutes of
wall clock by the container clock (18:30 to 18:41 UTC, 2026-11-21), all nodes read in full.

**Witness notation.** Routes are choice ids from `n_open`, joined by `>`. The shorthands below expand to exact choice
ids and were expanded and replayed by script.

- `@maze` = `c_open > c_n_start_1 > c_ap_1_1` (lands on `h_maze`).
- `@grove`, `@warren`, `@council`, `@ridge`, `@gate`, `@dusk` = the previous shorthand plus that area's first warden
  run, `c_h_<a>_f > c_b_<a>_1_rc0 > c_rc_<a>_0_1_1 > c_rc_<a>_0_2_1 > c_rc_<a>_0_3_1`. Each lands on the next hub;
  `@dusk` lands on `f_dusk`. These are the shortest routes to each hub.
- `S(a,k)` = `c_h_<a>_f > c_b_<a>_1_f > ... > c_b_<a>_<k-1>_f` (walk the spine of area `a` to `b_<a>_<k>`).
- `+n` = take the only choice n more times (excursion and run chains have one choice per node).

Severity: blocker (plain contradiction or a fact false on the route), should-fix (unshown presupposition or
label/outcome contradiction), minor (small wording slip). Instance lists name every node that carries the defect.

## Blockers

| ID | Class | Node | Nodes | Defect |
| --- | --- | --- | ---: | --- |
| B1 | `timeline` | `b_maze_2` | 4 | Light "failing fast" in the first area of a dawn-to-dusk day |
| B2 | `timeline` | `rc_maze_1_2` | 10 | Runs make the light "give out completely", then day returns |
| B3 | `timeline` | `x_mazeh_1_2` | 13 | Dusk and failing light inside the Bramble Maze, minutes after dawn |
| B4 | `unestablished_fact_on_route` | `e_ridge2_49` | 11 | False-mark endings after chains that left the marks |

**B1. Light "failing fast" in the first area of a dawn-to-dusk day.** `timeline`. Node `b_maze_2`: "Further into
Bramble Maze, the light is failing fast and the thorn closes in underfoot."

- Witness: `@maze > S(maze,2)`.
- Why: The day runs dawn to dusk (`n_open` "one single day, dawn to dusk"; `ap_4` "before the day has properly
  begun"). The reader is minutes into the first of six areas, and the same route crosses three more areas before
  `h_ridge` "climbs toward the last of the light". The spine template repeats the line in every area, so it is false
  in the four daytime areas.
- Supporting: the same spine nodes `b_maze_4`/`b_maze_5` (and grove, warren, council) speak of "the dark" ahead.
- Instances (4): `b_maze_2` (`@maze > S(maze,2)`); `b_grove_2` (`@grove > S(grove,2)`); `b_warren_2` (`@warren >
  S(warren,2)`); `b_council_2` (`@council > S(council,2)`).

**B2. Runs make the light "give out completely", then day returns.** `timeline`. Node `rc_maze_1_2`: "Further along
the excursion, the light gives out completely and the warden signs all but vanish beneath the thorn."

- Witness: `@maze > S(maze,2) > c_b_maze_2_rc1 > +3` (lands on `b_maze_3`).
- Why: Two clicks later the same route reaches `b_maze_3` "which quietly costs the daylight you cannot spare", and
  then three more areas of day before dusk at `h_ridge`. The run itself set out to "recover the daylight you keep
  steadily losing". Full dark mid-morning is false, and day returning after it is a plain contradiction on one
  route. The ridge and gate copies are also wrong: after `rc_ridge_1_2` the route reaches `h_gate` "The Far Gate
  stands black against the last red band of dusk". The first-run copies (`rc_*_0_2`) put the reader "You push onward
  through the gathering dark" and then hand them to the next hub in daylight. The shortest winning route takes all
  six of these runs.
- Instances (10): `rc_maze_1_2` (`@maze > S(maze,2) > c_b_maze_2_rc1 > +1`); `rc_grove_1_2` (`@grove > S(grove,2) >
  c_b_grove_2_rc1 > +1`); `rc_warren_1_2` (`@warren > S(warren,2) > c_b_warren_2_rc1 > +1`); `rc_council_1_2`
  (`@council > S(council,2) > c_b_council_2_rc1 > +1`); `rc_ridge_1_2` (`@ridge > S(ridge,2) > c_b_ridge_2_rc1 >
  +1`); `rc_gate_1_2` (`@gate > S(gate,2) > c_b_gate_2_rc1 > +1`); `rc_maze_0_2` (`@maze > c_h_maze_f >
  c_b_maze_1_rc0 > +1`); `rc_grove_0_2` (`@grove > c_h_grove_f > c_b_grove_1_rc0 > +1`); `rc_warren_0_2` (`@warren >
  c_h_warren_f > c_b_warren_1_rc0 > +1`); `rc_council_0_2` (`@council > c_h_council_f > c_b_council_1_rc0 > +1`).

**B3. Dusk and failing light inside the Bramble Maze, minutes after dawn.** `timeline`. Node `x_mazeh_1_2`: "the
failing light turns every choice into a blind guess".

- Witness: `@maze > c_h_maze_c0 > +1`.
- Why: Three clicks after `ap_1` sends the reader in with "settle your nerve for the long day ahead", the maze is
  losing its light. Every Bramble Maze excursion chain has a copy ("the deepening dusk drains away what little you
  could still make out", "would burn the last of the daylight"). Two maze endings put dusk at the moment of failure:
  `e_maze4_9` "behind you the warden marks have already been swallowed by the dusk", `e_maze_2_0` "Now the dusk is
  down".
- Instances (13): `x_maze1_2_2` (`@maze > c_h_maze_f > c_b_maze_1_x0 > +1`); `x_maze1_3_1` (`@maze > c_h_maze_f >
  c_b_maze_1_x1`); `x_maze2_4_2` (`@maze > S(maze,2) > c_b_maze_2_x0 > +1`); `x_maze2_5_2` (`@maze > S(maze,2) >
  c_b_maze_2_x1 > +1`); `x_maze3_6_1` (`@maze > S(maze,3) > c_b_maze_3_x0`); `x_maze3_7_2` (`@maze > S(maze,3) >
  c_b_maze_3_x1 > +1`); `x_maze4_8_2` (`@maze > S(maze,4) > c_b_maze_4_x0 > +1`); `x_maze4_9_1` (`@maze > S(maze,4)
  > c_b_maze_4_x1`); `x_maze5_10_2` (`@maze > S(maze,5) > c_b_maze_5_x0 > +1`); `x_maze5_11_2` (`@maze > S(maze,5) >
  c_b_maze_5_x1 > +1`); `x_mazeh_1_2` (`@maze > c_h_maze_c0 > +1`); `e_maze4_9` (`@maze > S(maze,4) > c_b_maze_4_x1
  > +3`); `e_maze_2_0` (`@maze > S(maze,2) > c_b_maze_2_s0`).

**B4. False-mark endings after chains that left the marks.** `unestablished_fact_on_route`. Node `e_ridge2_49`: "You
followed the mark in good faith, never guessing it was a false one".

- Witness: `@ridge > S(ridge,2) > c_b_ridge_2_x1 > +3`.
- Why: On this route `x_ridge2_49_1` says "You have drifted clean off the warden signs without ever meaning to" and
  `x_ridge2_49_3` says "No warden mark survives to follow home." The ending then says the hero followed a mark the
  whole way. All eleven false-mark endings that close an excursion chain do the same: each chain opens by leaving
  the marks ("You leave the true line", "A single step off the marks", "drifted clean off the warden signs") and
  loses them, and then the ending blames a false sign the hero "trusted so completely" or followed "the whole way
  along". The ending pool is assigned without regard to the chain: each of the six ending families (false mark,
  warden test, haste, exhaustion, fall, dead end) has exactly 18 members spread evenly across every entry label.
- Instances (11): `e_maze1_2` (`@maze > c_h_maze_f > c_b_maze_1_x0 > +3`); `e_grove5_22` (`@grove > S(grove,5) >
  c_b_grove_5_x1 > +2`); `e_warren4_31` (`@warren > S(warren,4) > c_b_warren_4_x1 > +3`); `e_warren5_32` (`@warren >
  S(warren,5) > c_b_warren_5_x0 > +3`); `e_council3_40` (`@council > S(council,3) > c_b_council_3_x1 > +2`);
  `e_council4_41` (`@council > S(council,4) > c_b_council_4_x0 > +2`); `e_ridge2_49` (`@ridge > S(ridge,2) >
  c_b_ridge_2_x1 > +3`); `e_ridge3_50` (`@ridge > S(ridge,3) > c_b_ridge_3_x0 > +3`); `e_gate1_58` (`@gate >
  c_h_gate_f > c_b_gate_1_x1 > +2`); `e_gate2_59` (`@gate > S(gate,2) > c_b_gate_2_x0 > +2`); `e_gateh_56` (`@gate >
  c_h_gate_c0 > +2`).

## Should-fix

| ID | Class | Node | Nodes | Defect |
| --- | --- | --- | ---: | --- |
| S1 | `unestablished_fact_on_route` | `e_maze_5_0` | 18 | Warden-test endings with no warden or exchange on the route |
| S2 | `unestablished_fact_on_route` | `h_council` | 6 | Hub tests are announced, never staged, then treated as passed |
| S3 | `unestablished_fact_on_route` | `e_win_wild` | 2 | Wardens praise sparing warren beasts that no route meets |
| S4 | `other` | `h_council` | 4 | Warden-test numbering skips the Beast-Warren test |
| S5 | `location_or_physical_state` | `h_maze` | 5 | "Very heart" of the maze reached by pressing on to its mouth |
| S6 | `location_or_physical_state` | `f_dusk` | 5 | At the Far Gate, then a whole area, then emerging before it |
| S7 | `timeline` | `f_wild` | 3 | Same arrival: on time for f_name, "a latecomer" for f_wild |
| S8 | `label_outcome_mismatch` | `x_maze5_10_1` | 12 | "Follow the sound instead." leads to no sound |
| S9 | `label_outcome_mismatch` | `x_maze1_2_1` | 18 | Deliberate choices told as "without ever meaning to" |
| S10 | `label_outcome_mismatch` | `e_council_5_0` | 5 | Labels that leave the marks end in a followed false mark |
| S11 | `timeline` | `x_grove1_13_2` | 43 | Dusk in the midday areas; night in the morning maze |

**S1. Warden-test endings with no warden or exchange on the route.** `unestablished_fact_on_route`. Node `e_maze_5_0`:
"The test breaks on nothing large at all, only a beat spoken too soon or a reach made with the wrong hand"; "The
warden nods once, not unkindly, and points you out of Bramble Maze toward the road home."

- Witness: `@maze > S(maze,5) > c_b_maze_5_s0`.
- Why: No warden is in the Bramble Maze; the book places "the first warden of the whole Trial" in the next area. The
  route never stages any spoken test: the label was "Cut straight across the marks." The other 17 warden-test
  endings ("You do nearly everything right ... a hasty answer", "It is a small thing that finally fails you ... a
  rushed word", "Here the warden asks very little of you") end spine stretches or solitary excursion chains. A chain
  like that says the hero is alone in the dark with "No warden mark survives". A hub choice like that walked away
  from the test ("Take the wider, gentler way", "Try the narrow shortcut around the test"). The three maze instances
  are the worst, because the maze has no warden at all.
- Instances (18): `e_council1_35` (`@council > c_h_council_f > c_b_council_1_x0 > +3`); `e_council_2_0` (`@council >
  S(council,2) > c_b_council_2_s0`); `e_gate4_64` (`@gate > S(gate,4) > c_b_gate_4_x1 > +3`); `e_gate5_65` (`@gate >
  S(gate,5) > c_b_gate_5_x0 > +3`); `e_gate_hub0` (`@gate > c_h_gate_s0`); `e_grove2_16` (`@grove > S(grove,2) >
  c_b_grove_2_x1 > +3`); `e_grove3_17` (`@grove > S(grove,3) > c_b_grove_3_x0 > +3`); `e_grove_4_0` (`@grove >
  S(grove,4) > c_b_grove_4_s0`); `e_maze3_7` (`@maze > S(maze,3) > c_b_maze_3_x1 > +2`); `e_maze4_8` (`@maze >
  S(maze,4) > c_b_maze_4_x0 > +2`); `e_maze_5_0` (`@maze > S(maze,5) > c_b_maze_5_s0`); `e_ridge5_55` (`@ridge >
  S(ridge,5) > c_b_ridge_5_x1 > +2`); `e_ridge_1_0` (`@ridge > c_h_ridge_f > c_b_ridge_1_s0`); `e_ridge_hub1`
  (`@ridge > c_h_ridge_s1`); `e_warren1_25` (`@warren > c_h_warren_f > c_b_warren_1_x1 > +2`); `e_warren2_26`
  (`@warren > S(warren,2) > c_b_warren_2_x0 > +2`); `e_warren_3_0` (`@warren > S(warren,3) > c_b_warren_3_s0`);
  `e_warrenh_23` (`@warren > c_h_warren_c0 > +2`).

**S2. Hub tests are announced, never staged, then treated as passed.** `unestablished_fact_on_route`. Node
`h_council`: "they will not let you pass until the second warden test, a test of your judgement, is done".

- Witness: `@council > c_h_council_f > c_b_council_1_rc0 > +3` (lands on `h_ridge`).
- Why: The reader takes the true mark "directly to their feet" and then walks on through generic trail nodes or a
  warden run. No question, judgement or verdict is ever shown, yet `h_ridge` moves on to "the third warden test". It
  is the same at `h_grove` ("the first warden of the whole Trial waits with a test for you"), `h_warren` (the
  lynx-warden watching "whether you will fight, flee, or show it mercy") and `h_ridge`. `f_name` then asks for
  "every test you faced", and `e_win_warden` says "the whole test passed". None of the four tests happens on any
  route.
- Instances (6): `h_grove` (`@grove`); `h_warren` (`@warren`); `h_council` (`@council`); `h_ridge` (`@ridge`);
  `f_name` (`@dusk > c_f_dusk_1`); `e_win_warden` (`@dusk > c_f_dusk_1 > c_f_name_1`).

**S3. Wardens praise sparing warren beasts that no route meets.** `unestablished_fact_on_route`. Node `e_win_wild`:
"To spare the warren beasts when you might so easily have struck at them".

- Witness: `@dusk > c_f_dusk_1 > c_f_name_2`.
- Why: No route offers a chance to strike or spare anything. The only beast shown is the lynx-warden pacing its
  ledge at `h_warren`, and every warren node after it is about paths, dens and marks. The `f_name` label "Answer
  that it was mercy shown to the beasts." also leans on this unshown event. All 62,500 routes into `f_name` can take
  this answer.
- Instances (2): `e_win_wild` (`@dusk > c_f_dusk_1 > c_f_name_2`); `f_name` (`@dusk > c_f_dusk_1`).

**S4. Warden-test numbering skips the Beast-Warren test.** `other`. Node `h_council`: "the second warden test".

- Witness: `@council`.
- Why: On this route the reader has met "the first warden of the whole Trial waits with a test for you" and then the
  lynx-warden at `h_warren` "watching closely to see whether you will fight, flee, or show it mercy". That makes the
  council the third test, not the second, and `h_ridge` "the third warden test" the fourth. The maze hub also frames
  itself as a test ("far too kind to be the real test", label "Try the narrow shortcut around the test").
- Instances (4): `h_grove` (`@grove`); `h_warren` (`@warren`); `h_council` (`@council`); `h_ridge` (`@ridge`).

**S5. "Very heart" of the maze reached by pressing on to its mouth.** `location_or_physical_state`. Node `h_maze`:
"You stand at the very heart of the Bramble Maze".

- Witness: `@maze`.
- Why: All four approaches deliver the reader to the maze mouth ("bringing you at last to the maze mouth"; label
  "Press on to the maze mouth."). The next node, `b_maze_1`, then says "You work steadily deeper", and `b_maze_5`
  says "nearing the far end". The hero is at the entrance, not the heart.
- Instances (5): `h_maze` (`@maze`); `ap_1` (`c_open > c_n_start_1`); `ap_2` (`c_open > c_n_start_2`); `ap_3`
  (`c_open > c_n_start_3`); `ap_4` (`c_open > c_n_start_4`).

**S6. At the Far Gate, then a whole area, then emerging before it.** `location_or_physical_state`. Node `f_dusk`: "You
spill out of the trees before the Far Gate".

- Witness: `@dusk`.
- Why: At `h_gate` the gate is already in front of the hero: "The Far Gate stands black against the last red band of
  dusk" and "The truest mark leads straight to the gate itself". Five spine stretches follow ("Further into Far
  Gate", "Deep within Far Gate", "nearing the far end of Far Gate now"), or a warden run. Then the hero comes out of
  the trees in front of the gate. The gate is both reached and still ahead.
- Instances (5): `h_gate` (`@gate`); `b_gate_1` (`@gate > c_h_gate_f`); `b_gate_5` (`@gate > S(gate,5)`);
  `rc_gate_0_3` (`@gate > c_h_gate_f > c_b_gate_1_rc0 > +2`); `f_dusk` (`@dusk`).

**S7. Same arrival: on time for f_name, "a latecomer" for f_wild.** `timeline`. Node `f_wild`: "The wardens will not
draw the great bar for a latecomer, since that gate is for those who arrive with the light still in the sky."

- Witness: `@dusk > c_f_dusk_2`.
- Why: Both `f_name` and `f_wild` hang off `f_dusk`, so the history is identical. `f_dusk` has the bar still drawn
  and the wardens "waiting to judge how you ran the whole of the Trial". On the `f_name` branch they name the hero
  and "The heavy bar lifts at last". Whether the hero arrived in time depends on which answer they pick afterwards.
- Instances (3): `f_wild` (`@dusk > c_f_dusk_2`); `f_dusk` (`@dusk`); `e_win_warden` (`@dusk > c_f_dusk_1 >
  c_f_name_1`).

**S8. "Follow the sound instead." leads to no sound.** `label_outcome_mismatch`. Node `x_maze5_10_1`: "You leave the
true line for the easy-looking way, which for a dozen strides seems kinder underfoot."

- Witness: `@maze > S(maze,5) > c_b_maze_5_x0`.
- Why: The label at `b_maze_5` is "Follow the sound instead." (after "a sound pulls at you from the dark"). The
  outcome says the hero took the easy-looking way, and no sound is ever heard. Six of the twelve "Follow the sound"
  chains open this way and six open with "It felt like a clever shortcut a moment ago". Only `x_gate5_65_1` mentions
  any sound ("the sounding horns"), and it still opens on the easy-looking way.
- Instances (12): `x_council4_42_1` (`@council > S(council,4) > c_b_council_4_x1`); `x_council5_43_1` (`@council >
  S(council,5) > c_b_council_5_x0`); `x_gate4_64_1` (`@gate > S(gate,4) > c_b_gate_4_x1`); `x_gate5_65_1` (`@gate >
  S(gate,5) > c_b_gate_5_x0`); `x_grove4_20_1` (`@grove > S(grove,4) > c_b_grove_4_x1`); `x_grove5_21_1` (`@grove >
  S(grove,5) > c_b_grove_5_x0`); `x_maze4_9_1` (`@maze > S(maze,4) > c_b_maze_4_x1`); `x_maze5_10_1` (`@maze >
  S(maze,5) > c_b_maze_5_x0`); `x_ridge4_53_1` (`@ridge > S(ridge,4) > c_b_ridge_4_x1`); `x_ridge5_54_1` (`@ridge >
  S(ridge,5) > c_b_ridge_5_x0`); `x_warren4_31_1` (`@warren > S(warren,4) > c_b_warren_4_x1`); `x_warren5_32_1`
  (`@warren > S(warren,5) > c_b_warren_5_x0`).

**S9. Deliberate choices told as "without ever meaning to".** `label_outcome_mismatch`. Node `x_maze1_2_1`: "You have
drifted clean off the warden signs without ever meaning to."

- Witness: `@maze > c_h_maze_f > c_b_maze_1_x0`.
- Why: The reader chose "Double back and start over." The other instances follow "Cut straight across the marks." or
  "Chance the quicker line." All three are deliberate moves, and the first is a return toward known ground, yet the
  outcome describes a wide, soft side-branch the hero wandered onto by accident.
- Instances (18): `x_council1_35_1` (`@council > c_h_council_f > c_b_council_1_x0`); `x_council2_38_1` (`@council >
  S(council,2) > c_b_council_2_x1`); `x_council4_41_1` (`@council > S(council,4) > c_b_council_4_x0`);
  `x_gate1_57_1` (`@gate > c_h_gate_f > c_b_gate_1_x0`); `x_gate2_60_1` (`@gate > S(gate,2) > c_b_gate_2_x1`);
  `x_gate4_63_1` (`@gate > S(gate,4) > c_b_gate_4_x0`); `x_grove1_13_1` (`@grove > c_h_grove_f > c_b_grove_1_x0`);
  `x_grove2_16_1` (`@grove > S(grove,2) > c_b_grove_2_x1`); `x_grove4_19_1` (`@grove > S(grove,4) >
  c_b_grove_4_x0`); `x_maze1_2_1` (`@maze > c_h_maze_f > c_b_maze_1_x0`); `x_maze2_5_1` (`@maze > S(maze,2) >
  c_b_maze_2_x1`); `x_maze4_8_1` (`@maze > S(maze,4) > c_b_maze_4_x0`); `x_ridge1_46_1` (`@ridge > c_h_ridge_f >
  c_b_ridge_1_x0`); `x_ridge2_49_1` (`@ridge > S(ridge,2) > c_b_ridge_2_x1`); `x_ridge4_52_1` (`@ridge > S(ridge,4)
  > c_b_ridge_4_x0`); `x_warren1_24_1` (`@warren > c_h_warren_f > c_b_warren_1_x0`); `x_warren2_27_1` (`@warren >
  S(warren,2) > c_b_warren_2_x1`); `x_warren4_30_1` (`@warren > S(warren,4) > c_b_warren_4_x0`).

**S10. Labels that leave the marks end in a followed false mark.** `label_outcome_mismatch`. Node `e_council_5_0`:
"Too late you understand that the mark was wrong the whole way along".

- Witness: `@council > S(council,5) > c_b_council_5_s0`.
- Why: The label was "Cut straight across the marks.", which means ignoring them, not following one. The others:
  "Turn aside toward the strange light." (`e_grove_1_0`, `e_grove_hub1`), "Take the wider, gentler way." at
  `h_warren` (the hub says that way "in truth leads nowhere", against "The truest mark", so `e_warren_hub0` "You
  followed the mark in good faith" is false), and "Trust the easy looking path." (`e_ridge_4_0`, where `b_ridge_4`
  calls that path "smoother than the true way and therefore rightly suspect" and says "Only one of these choices
  keeps you on the marks").
- Instances (5): `e_grove_1_0` (`@grove > c_h_grove_f > c_b_grove_1_s0`); `e_grove_hub1` (`@grove > c_h_grove_s1`);
  `e_warren_hub0` (`@warren > c_h_warren_s0`); `e_council_5_0` (`@council > S(council,5) > c_b_council_5_s0`);
  `e_ridge_4_0` (`@ridge > S(ridge,4) > c_b_ridge_4_s0`).

**S11. Dusk in the midday areas; night in the morning maze.** `timeline`. Node `x_grove1_13_2`: "the deepening dusk
drains away what little you could still make out".

- Witness: `@grove > c_h_grove_f > c_b_grove_1_x0 > +1`.
- Why: The grove, warren and council lie between a dawn start and a ridge that "climbs toward the last of the
  light". Every excursion chain in those areas has dusk, failing light or "the last of the daylight". Maze endings
  also bring on night within one to three clicks of a morning hub: "The last of the day drains from the sky
  overhead" (one click past `b_maze_1`), "wait for the searchers who will come at first light", "a long wait for
  dawn". These only fit if the hero spent the whole day stuck, which the text never says, so they are should-fix
  rather than blocker.
- Instances (43): `x_council1_35_2` (`@council > c_h_council_f > c_b_council_1_x0 > +1`); `x_council1_36_1`
  (`@council > c_h_council_f > c_b_council_1_x1`); `x_council2_37_2` (`@council > S(council,2) > c_b_council_2_x0 >
  +1`); `x_council2_38_2` (`@council > S(council,2) > c_b_council_2_x1 > +1`); `x_council3_39_1` (`@council >
  S(council,3) > c_b_council_3_x0`); `x_council3_40_2` (`@council > S(council,3) > c_b_council_3_x1 > +1`);
  `x_council4_41_2` (`@council > S(council,4) > c_b_council_4_x0 > +1`); `x_council4_42_1` (`@council > S(council,4)
  > c_b_council_4_x1`); `x_council5_43_2` (`@council > S(council,5) > c_b_council_5_x0 > +1`); `x_council5_44_2`
  (`@council > S(council,5) > c_b_council_5_x1 > +1`); `x_councilh_34_2` (`@council > c_h_council_c0 > +1`);
  `x_grove1_13_2` (`@grove > c_h_grove_f > c_b_grove_1_x0 > +1`); `x_grove1_14_1` (`@grove > c_h_grove_f >
  c_b_grove_1_x1`); `x_grove2_15_2` (`@grove > S(grove,2) > c_b_grove_2_x0 > +1`); `x_grove2_16_2` (`@grove >
  S(grove,2) > c_b_grove_2_x1 > +1`); `x_grove3_17_1` (`@grove > S(grove,3) > c_b_grove_3_x0`); `x_grove3_18_2`
  (`@grove > S(grove,3) > c_b_grove_3_x1 > +1`); `x_grove4_19_2` (`@grove > S(grove,4) > c_b_grove_4_x0 > +1`);
  `x_grove4_20_1` (`@grove > S(grove,4) > c_b_grove_4_x1`); `x_grove5_21_2` (`@grove > S(grove,5) > c_b_grove_5_x0 >
  +1`); `x_grove5_22_2` (`@grove > S(grove,5) > c_b_grove_5_x1 > +1`); `x_groveh_12_2` (`@grove > c_h_grove_c0 >
  +1`); `x_warren1_24_2` (`@warren > c_h_warren_f > c_b_warren_1_x0 > +1`); `x_warren1_25_1` (`@warren >
  c_h_warren_f > c_b_warren_1_x1`); `x_warren2_26_2` (`@warren > S(warren,2) > c_b_warren_2_x0 > +1`);
  `x_warren2_27_2` (`@warren > S(warren,2) > c_b_warren_2_x1 > +1`); `x_warren3_28_1` (`@warren > S(warren,3) >
  c_b_warren_3_x0`); `x_warren3_29_2` (`@warren > S(warren,3) > c_b_warren_3_x1 > +1`); `x_warren4_30_2` (`@warren >
  S(warren,4) > c_b_warren_4_x0 > +1`); `x_warren4_31_1` (`@warren > S(warren,4) > c_b_warren_4_x1`);
  `x_warren5_32_2` (`@warren > S(warren,5) > c_b_warren_5_x0 > +1`); `x_warren5_33_2` (`@warren > S(warren,5) >
  c_b_warren_5_x1 > +1`); `x_warrenh_23_2` (`@warren > c_h_warren_c0 > +1`); `e_maze_1_0` (`@maze > c_h_maze_f >
  c_b_maze_1_s0`); `e_maze_hub1` (`@maze > c_h_maze_s1`); `e_mazeh_1` (`@maze > c_h_maze_c0 > +2`); `e_maze_3_0`
  (`@maze > S(maze,3) > c_b_maze_3_s0`); `e_maze1_3` (`@maze > c_h_maze_f > c_b_maze_1_x1 > +2`); `e_maze2_4`
  (`@maze > S(maze,2) > c_b_maze_2_x0 > +2`); `e_maze5_11` (`@maze > S(maze,5) > c_b_maze_5_x1 > +2`); `e_maze_4_0`
  (`@maze > S(maze,4) > c_b_maze_4_s0`); `e_maze3_6` (`@maze > S(maze,3) > c_b_maze_3_x0 > +3`); `e_maze2_5` (`@maze
  > S(maze,2) > c_b_maze_2_x1 > +3`).

## Minor

| ID | Class | Node | Nodes | Defect |
| --- | --- | --- | ---: | --- |
| M1 | `label_outcome_mismatch` | `e_council5_44` | 5 | Haste endings after a careful walk or a non-hasty choice |
| M2 | `label_outcome_mismatch` | `e_maze_1_0` | 12 | "Turn aside toward the strange light." never reaches a light |
| M3 | `label_outcome_mismatch` | `e_maze_3_0` | 5 | "Double back and start over." endings narrate something else |
| M4 | `location_or_physical_state` | `rc_ridge_2_3` | 2 | Marks "cut into the bark" on the bare rock of the Far Ridge |
| M5 | `location_or_physical_state` | `e_warren_3_0` | 4 | The Beast-Warren lynx-warden given a hand, arm and face |
| M6 | `location_or_physical_state` | `e_maze1_3` | 7 | "Gate still uncrossed behind you" with the gate ahead |
| M7 | `location_or_physical_state` | `b_grove_3` | 5 | Spine fatigue resets every area |
| M8 | `timeline` | `e_gate_late` | 2 | The last horn dies away twice |
| M9 | `label_outcome_mismatch` | `f_wild` | 1 | Hero begs for the wild ways; the warden "offers" them as new |
| M10 | `label_outcome_mismatch` | `x_mazeh_1_1` | 12 | Shortcut and easy-path labels open on the other template |

**M1. Haste endings after a careful walk or a non-hasty choice.** `label_outcome_mismatch`. Node `e_council5_44`:
"Trying desperately to win back lost time, you crash onward without reading the ground".

- Witness: `@council > S(council,5) > c_b_council_5_x1 > +2`.
- Why: The node before it, `x_council5_44_2`, ends "one careful step and then the next", and the label was "Take the
  wider, gentler way." `e_gate4_63` is the same case. The haste endings also follow "Turn aside toward the strange
  light." (`e_council_1_0`, `e_council_hub1`) and "Take the wider, gentler way." at `h_ridge` (`e_ridge_hub0`).
- Instances (5): `e_council5_44` (`@council > S(council,5) > c_b_council_5_x1 > +2`); `e_gate4_63` (`@gate >
  S(gate,4) > c_b_gate_4_x0 > +2`); `e_council_1_0` (`@council > c_h_council_f > c_b_council_1_s0`);
  `e_council_hub1` (`@council > c_h_council_s1`); `e_ridge_hub0` (`@ridge > c_h_ridge_s0`).

**M2. "Turn aside toward the strange light." never reaches a light.** `label_outcome_mismatch`. Node `e_maze_1_0`:
"Your foot finds nothing where you were certain of solid ground".

- Witness: `@maze > c_h_maze_f > c_b_maze_1_s0`.
- Why: None of the twelve "strange light" outcomes mentions the light, what it was, or reaching it. Some overlap
  with S1, S10, S11 and M1.
- Instances (12): `e_council_1_0` (`@council > c_h_council_f > c_b_council_1_s0`); `e_council_hub1` (`@council >
  c_h_council_s1`); `e_gate_1_0` (`@gate > c_h_gate_f > c_b_gate_1_s0`); `e_gate_hub1` (`@gate > c_h_gate_s1`);
  `e_grove_1_0` (`@grove > c_h_grove_f > c_b_grove_1_s0`); `e_grove_hub1` (`@grove > c_h_grove_s1`); `e_maze_1_0`
  (`@maze > c_h_maze_f > c_b_maze_1_s0`); `e_maze_hub1` (`@maze > c_h_maze_s1`); `e_ridge_1_0` (`@ridge >
  c_h_ridge_f > c_b_ridge_1_s0`); `e_ridge_hub1` (`@ridge > c_h_ridge_s1`); `e_warren_1_0` (`@warren > c_h_warren_f
  > c_b_warren_1_s0`); `e_warren_hub1` (`@warren > c_h_warren_s1`).

**M3. "Double back and start over." endings narrate something else.** `label_outcome_mismatch`. Node `e_maze_3_0`:
"There comes a point where pressing forward is only stubborn pride".

- Witness: `@maze > S(maze,3) > c_b_maze_3_s0`.
- Why: Doubling back is not pressing forward. The other copies are: `e_gate_3_0` choosing to believe a false mark,
  `e_grove_3_0` "you throw yourself at a rough stretch", `e_warren_3_0` a warden test, and `e_ridge_3_0` "One
  careless stride".
- Instances (5): `e_gate_3_0` (`@gate > S(gate,3) > c_b_gate_3_s0`); `e_grove_3_0` (`@grove > S(grove,3) >
  c_b_grove_3_s0`); `e_warren_3_0` (`@warren > S(warren,3) > c_b_warren_3_s0`); `e_ridge_3_0` (`@ridge > S(ridge,3)
  > c_b_ridge_3_s0`); `e_maze_3_0` (`@maze > S(maze,3) > c_b_maze_3_s0`).

**M4. Marks "cut into the bark" on the bare rock of the Far Ridge.** `location_or_physical_state`. Node
`rc_ridge_2_3`: "cut clean and deep into the bark".

- Witness: `@ridge > S(ridge,3) > c_b_ridge_3_rc2 > +2`.
- Why: The ridge is "a wind-scoured spine of rock high above the whole darkening forest", and its marks are cairns
  and scratched stone ("scoured every warden mark clean off the bare stone"). `e_ridge3_50` repeats the bark ("a lie
  in the bark").
- Instances (2): `rc_ridge_2_3` (`@ridge > S(ridge,3) > c_b_ridge_3_rc2 > +2`); `e_ridge3_50` (`@ridge > S(ridge,3)
  > c_b_ridge_3_x0 > +3`).

**M5. The Beast-Warren lynx-warden given a hand, arm and face.** `location_or_physical_state`. Node `e_warren_3_0`:
"The warden's hand lifts toward the way out".

- Witness: `@warren > S(warren,3) > c_b_warren_3_s0`.
- Why: The only warden in the Beast-Warren is "the great lynx-warden".
- Instances (4): `e_warren_3_0` (`@warren > S(warren,3) > c_b_warren_3_s0`); `e_warrenh_23` (`@warren >
  c_h_warren_c0 > +2`); `e_warren1_25` (`@warren > c_h_warren_f > c_b_warren_1_x1 > +2`); `e_warren2_26` (`@warren >
  S(warren,2) > c_b_warren_2_x0 > +2`).

**M6. "Gate still uncrossed behind you" with the gate ahead.** `location_or_physical_state`. Node `e_maze1_3`: "the
gate still uncrossed behind you".

- Witness: `@maze > c_h_maze_f > c_b_maze_1_x1 > +2`.
- Why: The Far Gate is the goal at the far side of the wood, so it is ahead of the hero. In the Far Gate area
  `e_gate_1_0` also says "This season's crossing is finished before it ever reached the gate" after `h_gate` stood
  the hero in front of it.
- Instances (7): `e_council4_42` (`@council > S(council,4) > c_b_council_4_x1 > +3`); `e_gate3_61` (`@gate >
  S(gate,3) > c_b_gate_3_x0 > +3`); `e_grove_2_0` (`@grove > S(grove,2) > c_b_grove_2_s0`); `e_maze1_3` (`@maze >
  c_h_maze_f > c_b_maze_1_x1 > +2`); `e_ridge4_52` (`@ridge > S(ridge,4) > c_b_ridge_4_x0 > +2`); `e_warren_1_0`
  (`@warren > c_h_warren_f > c_b_warren_1_s0`); `e_gate_1_0` (`@gate > c_h_gate_f > c_b_gate_1_s0`).

**M7. Spine fatigue resets every area.** `location_or_physical_state`. Node `b_grove_3`: "your legs are beginning to
tire beneath you".

- Witness: `@grove > S(grove,3)`.
- Why: The previous area ended with "But you are badly spent". Every area repeats the same tiring arc and the same
  "light is failing fast" (B1), so a spine reader is "badly spent" at the end of each area and only "beginning to
  tire" again in the next.
- Instances (5): `b_grove_3` (`@grove > S(grove,3)`); `b_warren_3` (`@warren > S(warren,3)`); `b_council_3`
  (`@council > S(council,3)`); `b_ridge_3` (`@ridge > S(ridge,3)`); `b_gate_3` (`@gate > S(gate,3)`).

**M8. The last horn dies away twice.** `timeline`. Node `e_gate_late`: "simply let the last horn die away around you".

- Witness: `@dusk > c_f_dusk_4`.
- Why: `f_dusk` already had the hero arrive "just as the last horn dies away", and its label "Sink down, spent, and
  let the horns pass." assumes horns still sounding.
- Instances (2): `e_gate_late` (`@dusk > c_f_dusk_4`); `f_dusk` (`@dusk`).

**M9. Hero begs for the wild ways; the warden "offers" them as new.** `label_outcome_mismatch`. Node `f_wild`: "But
one warden studies you a long moment and quietly offers another road."

- Witness: `@dusk > c_f_dusk_2`.
- Why: The label was "Beg to pass by the wild ways instead.", so the hero asked for the wild ways, yet the warden
  introduces them as an idea of their own, and `f_wild` then asks the hero to choose them again.
- Instances (1): `f_wild` (`@dusk > c_f_dusk_2`).

**M10. Shortcut and easy-path labels open on the other template.** `label_outcome_mismatch`. Node `x_mazeh_1_1`: "You
leave the true line for the easy-looking way".

- Witness: `@maze > c_h_maze_c0`.
- Why: The label was "Try the narrow shortcut around the test." (all six hubs). Conversely, six "Trust the easy
  looking path." chains open with "It felt like a clever shortcut a moment ago".
- Instances (12): `x_councilh_34_1` (`@council > c_h_council_c0`); `x_gateh_56_1` (`@gate > c_h_gate_c0`);
  `x_groveh_12_1` (`@grove > c_h_grove_c0`); `x_mazeh_1_1` (`@maze > c_h_maze_c0`); `x_ridgeh_45_1` (`@ridge >
  c_h_ridge_c0`); `x_warrenh_23_1` (`@warren > c_h_warren_c0`); `x_council1_36_1` (`@council > c_h_council_f >
  c_b_council_1_x1`); `x_gate1_58_1` (`@gate > c_h_gate_f > c_b_gate_1_x1`); `x_grove1_14_1` (`@grove > c_h_grove_f
  > c_b_grove_1_x1`); `x_maze1_3_1` (`@maze > c_h_maze_f > c_b_maze_1_x1`); `x_ridge1_47_1` (`@ridge > c_h_ridge_f >
  c_b_ridge_1_x1`); `x_warren1_25_1` (`@warren > c_h_warren_f > c_b_warren_1_x1`).

## Class tally

| Class | Findings | IDs |
| --- | ---: | --- |
| `unestablished_fact_on_route` | 4 | B4, S1, S2, S3 |
| `state_contradiction` | 0 | - |
| `two_backstories` | 0 | - |
| `public_plant` | 0 | - |
| `cross_payoff_reference` | 0 | - |
| `label_outcome_mismatch` | 8 | S8, S9, S10, M1, M2, M3, M9, M10 |
| `repeated_reveal` | 0 | - |
| `timeline` | 6 | B1, B2, B3, S7, S11, M8 |
| `location_or_physical_state` | 6 | S5, S6, M4, M5, M6, M7 |
| `other` | 1 | S4 |
| **Total** | 25 | 4 blocker, 11 should-fix, 10 minor |

`state_contradiction` and `public_plant` have nothing to find because the book declares no variables; their zero is a
structural empty class, not a pass. No `two_backstories`, `cross_payoff_reference` or `repeated_reveal` defect was
found after a targeted search.

## Checked, not defects

- The four approaches (`ap_1`-`ap_4`) each deliver to the maze mouth in consistent terms; `h_maze` "four thorn paths
  knot together" matches them (only "very heart" is wrong, S5).
- Merge nodes `b_*_3` and `b_*_4` read cleanly from both the spine and the warden-run rejoin (apart from the light,
  B2). Each later hub reads cleanly from both `b_*_5` and `rc_*_0_3`.
- The finale cast is consistent: three wardens at `f_dusk`, the "head warden" (she) in `f_name`, `e_win_warden` and
  `e_win_honest`, "the eldest" in `e_win_wild`. They are distinct from the three hooded council wardens.
- `e_win_alt` ("At dawn you come out on the far side") fits the night walk in `f_wild`. `e_gate_slip` and
  `e_gate_next` fit `f_dusk`.
- Gate and ridge setback endings that speak of dusk, horns ending and searchers at first light fit the clock there.
- A warren excursion under a "packed roof" ending in a caved-in den with sky overhead (`e_warren3_29`,
  `e_warren4_30`) is physically possible, so it is not listed.
- No name, object or person appears from nowhere other than the wardens of S1 and the beasts of S3. "Wren" is used
  consistently (`n_open`, ending titles).
- Out of continuity scope, noted only: template glitches "over stone and stone" (`rc_ridge_0_2`) and "over cut stone
  and stone" (`rc_gate_0_2`), and the heavy verbatim repetition of spine and run text across all six areas.
