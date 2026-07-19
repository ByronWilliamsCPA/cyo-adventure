# Theme Contract: `the-cave-of-echoes` (parameterized)

This contract declares every slot used by
`out/pilot/the-cave-of-echoes.parameterized.json`. A **theme brief** supplies a
concrete value for each slot; the fill step then substitutes the value into the
`beats='...'` guidance and ending `title` labels before prose is generated. The
structure (node ids, choices, targets, ending kinds/valences, metadata) is fixed
and is **not** a slot: a theme changes *content*, never *shape*.

## Structure this contract preserves (invariant, non-negotiable)

- **Topology `time_cave`**: one entrance (`{THRESHOLD}` / `{ENTRANCE}`) opening
  onto **three parallel exploration routes** (A, B, C). Each route **forks into
  two sub-tracks**. Each sub-track has a single **commit-or-turn-back gate**:
  turning back yields a *lesser, safe* setback ending; committing leads *deeper*
  to a *greater* prize. Slots parameterize what fills each of these positions,
  never the positions themselves.
- **8-11 fail-state policy (safety gate)**: the six turn-back endings are
  `kind=setback, valence=negative`; the ten deep endings are
  `success`/`completion, valence=positive`. **There are no death endings, and no
  slot may introduce one.** Every gate is a *non-lethal* choice between a bigger
  reward and a safe retreat. See the per-slot constraints below: gates, deadlines
  and hazards must all be survivable and age-appropriate (content flags:
  violence none, scariness mild, peril moderate).
- **Word-count / role intent**: each node keeps its original `role=` and
  `words=`. Beats keep the same functional length and beat count; a theme value
  should be a short noun phrase, not a paragraph.

Slot count: **73** (7 global, 6 route-level, 60 per-track/per-ending).

---

## Global slots (7)

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{HERO}` | The child protagonist. | A single kid-relatable explorer (name or role). Age 8-11 appropriate; capable but not reckless. |
| `{COMPANION}` | The hero's companion who travels with them throughout. | Loyal, non-speaking or lightly-expressive sidekick (animal, robot, drone, younger sibling). Never a source of peril; reacts to mood (perks up, presses close). |
| `{THRESHOLD}` | The whole bounded, explorable place the story happens inside. | One entrance, three internal routes, self-contained. Must be **safe to explore for ages 8-11: no lethal hazards, no open drops to death, no toxic/unbreathable air**. Wonder over dread. |
| `{ENTRANCE}` | The single entry/exit point the hero returns to on a setback. | The mouth/airlock/trailhead of `{THRESHOLD}`; always reachable and safe to reach. |
| `{OPENING_MOMENT}` | The moment/condition that makes entry possible. | A recurring, non-lethal window (low tide, a scheduled power-down, morning cool). Must be repeatable so "come back next time" reads true. |
| `{DEADLINE}` | The non-lethal time pressure that closes the safe window. | A *survivable* deadline: the way out gets harder, not fatal. Being caught by it means a wet/dusty retreat, never harm. **No lethal countdown.** |
| `{DEADLINE_SIGN}` | The sensory sign the deadline is arriving, used at gates and retreats. | A visible, gradual cue (water pooling, lights dimming, sand shifting). Gives fair warning; escalates slowly enough to retreat safely. |

Route mapping: A = the first opening, B = the second, C = the third. The choice
labels at `n_start`, `la_fork`, `ra_fork`, `da_fork` are fixed structural text;
theme values must stay consistent with those labels' left/right/deeper framing.

## Route-level slots (6): each route's identity

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{ROUTE_A_LURE}` | The sensory signal drawing the hero down route A. | A distinct, benign "pull" (a hum, a light, a smell). Distinguishable from B and C. |
| `{ROUTE_A_CHAR}` | The physical character of route A's corridor. | A passable way (narrow but crossable). No dead-end hazards. |
| `{ROUTE_B_LURE}` | The sensory signal for route B. | Distinct from A and C. |
| `{ROUTE_B_CHAR}` | The character of route B's corridor. | Passable; may be wetter/colder but safe. |
| `{ROUTE_C_LURE}` | The sensory signal for route C. | Distinct from A and B; the "darkest/least obvious" pull. |
| `{ROUTE_C_CHAR}` | The character of route C's corridor. | Passable; the darkest route, but navigable with care. |

---

## Per-track and per-ending slots (60)

Each route forks into two sub-tracks. Every sub-track has this shared shape, so
its slots share a shape too:

- `_SIGN`: the cue at the fork that identifies this sub-track.
- `_LANDMARK` (or `_LANDMARK1/2`): notable feature(s) passed while descending.
- `_ZONE_HINT`: the first glimpse/promise of the reward zone.
- `_GATE`: the **commit-or-turn-back obstacle**. MUST be non-lethal and
  survivable to retreat from. This same phrase names the setback ending
  ("Turned Back at `{_GATE}`").
- `_ZONE`: the destination zone reached after committing.
- `_OFFER1` / `_OFFER2`: the two things the deep zone presents (for two-prize
  tracks).
- `_PRIZE*`: the greater reward(s) won. MUST be a discovery/keepsake/achievement,
  never harm to anyone. Names the positive ending.

### Route A, track 1 (`la_*` glow track: a reward zone offering TWO prizes)

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{A1_SIGN}` | Fork cue for A1 (something that catches the light). | Benign visual cue. |
| `{A1_LANDMARK}` | The glinting feature passed on the way down. | Wonder, not hazard. |
| `{A1_ZONE_HINT}` | First glow/promise of the zone through a far wall. | Inviting, safe. |
| `{A1_GATE}` | The narrow-gap commit obstacle (squeeze through vs turn back). | Non-lethal; a tight but passable gap. Retreat is always safe. |
| `{A1_ZONE}` | The reward zone (a light-filled chamber of wonder). | Safe, awe-inducing. |
| `{A1_OFFER1}` | The near, takeable reward in the zone. | A keepsake the hero can carry out; taking it harms nothing. |
| `{A1_OFFER2}` | The deeper pull toward the greater reward. | A safe onward passage. |
| `{A1_PRIZE1}` | Ending: the carried keepsake (success). | Positive; a real object brought home. Names ending `e_crystal`. |
| `{A1_PRIZE2_PATH}` | The transition passage toward the deeper prize. | Safe; sound-shaping motif. |
| `{A1_PRIZE2_ZONE}` | The deeper wonder-chamber. | Safe, marvelous. |
| `{A1_PRIZE2}` | Ending: the deep discovery (completion). | Positive; an experience/secret. Names ending `e_song`. |

### Route A, track 2 (`la_hum*`/`la_bell*`: a deep single-prize chain)

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{A2_SIGN}` | Fork cue for A2 (a warm, pulling sound). | Benign. |
| `{A2_LANDMARK}` | The resonant thing sensed far below. | Intriguing, not threatening. |
| `{A2_ZONE_HINT}` | The metallic/gleaming glimpse from the chamber below. | Safe promise. |
| `{A2_GATE}` | The descent aid left by a prior visitor (climb down vs climb back). | Non-lethal descent; retreat safe. |
| `{A2_FIND}` | The large old artifact discovered at the bottom. | A historical object; no danger. |
| `{A2_DETAIL1}` | The markings/inscription on the find plus nearby useful leftovers. | Readable clue + benign gear. |
| `{A2_DETAIL2}` | What those leftovers provide (light + a way to climb out). | Practical, safe. |
| `{A2_PRIZE}` | Ending: the recovered history (success). | Positive; a shareable discovery. Names ending `e_bell`. |

### Route B, track 1 (`ra_lake*`: an open expanse offering TWO prizes)

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{B1_SIGN}` | Fork cue for B1 (a growing open-space sound). | Benign. |
| `{B1_LANDMARK1}` | Underfoot change as the space opens. | Passable footing. |
| `{B1_LANDMARK2}` | The edge/shelf above the open expanse. | Safe vantage; no forced drop. |
| `{B1_GATE}` | The slippery narrowing shelf (descend vs back off). | Non-lethal; "before anyone slips" retreat is safe. |
| `{B1_ZONE}` | The vast open expanse below. | Safe to reach and stand beside. |
| `{B1_OFFER1}` | A vehicle/means to cross the expanse. | Usable, safe when prepared. |
| `{B1_OFFER2}` | A glowing shallow path along the edge. | Ankle-deep/safe. |
| `{B1_PRIZE1_PREP}` | The action that readies the crossing means. | Simple, safe prep. |
| `{B1_PRIZE1}` | Ending: crossing the expanse (success). | Positive achievement. Names `e_rowboat`. |
| `{B1_PRIZE2_PATH}` | The glowing trail across the shallows. | Safe, shallow. |
| `{B1_PRIZE2}` | Ending: the hidden spot under open sky (completion). | Positive; a secret place + keepsake. Names `e_islet`. |

### Route B, track 2 (`ra_pool*`: a tight bright chamber offering TWO prizes)

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{B2_SIGN}` | Fork cue for B2 (a distinct smell from a side-passage). | Benign. |
| `{B2_LANDMARK1}` | The tight passage's first pale light. | Passable crouch. |
| `{B2_LANDMARK2}` | The clear channel along the floor. | Shallow, safe. |
| `{B2_GATE}` | A curtain/threshold with the deadline filling behind (press on vs hurry back). | Non-lethal; retreat beats the deadline safely. |
| `{B2_ZONE}` | The bright hidden chamber full of small creatures. | Safe micro-world; creatures harmless. |
| `{B2_OFFER1}` | A rare, glowing creature to record. | Observed, not harmed. |
| `{B2_OFFER2}` | A track to a deeper darker basin. | Safe to follow. |
| `{B2_PRIZE1_ACT}` | The recording/observation action, leaving the creature in place. | Non-destructive. |
| `{B2_PRIZE1}` | Ending: the documented rare creature (success). | Positive; a record, not a captured animal. Names `e_starfish`. |
| `{B2_PRIZE2_FIND}` | The gleaming object half-buried in the basin. | Safe to lift; inert. |
| `{B2_PRIZE2}` | Ending: the recovered object (success). | Positive keepsake. Names `e_shell`. |

### Route C, track 1 (`da_bat*`: a living hazard to cross, single prize)

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{C1_SIGN}` | Fork cue for C1 (a small fluttering/skittering sound). | Benign but distinct. |
| `{C1_LANDMARK}` | The many resting living things overhead. | Harmless if undisturbed; the peril is only to *them being disturbed*, not to the hero. No attack, no injury. |
| `{C1_ZONE_HINT}` | The distant circle of daylight (a way up). | Safe promise. |
| `{C1_GATE}` | Crossing quietly beneath the resting colony (cross vs back away). | Non-lethal; worst case is a noisy retreat, never harm. |
| `{C1_CLIMB1}` | The rough natural stair upward. | Solid, climbable. |
| `{C1_CLIMB2}` | Evidence a prior explorer climbed here (a carving). | Reassuring, safe. |
| `{C1_CLIMB3}` | The final soft/mossy funnel to the surface. | Passable with a boost. |
| `{C1_PRIZE}` | Ending: the hidden surface exit + colony to report (completion). | Positive; a secret route + a discovery. Names `e_bats`. |

### Route C, track 2 (`da_cache*`: a hidden store offering TWO prizes)

| Slot | Meaning | Constraints |
| --- | --- | --- |
| `{C2_SIGN}` | Fork cue for C2 (creak of old material, glint of old metal). | Benign. |
| `{C2_LANDMARK1}` | The old barrier/door into the side-cave. | Openable by a kid; no trap. |
| `{C2_LANDMARK2}` | The hand-made walled-off hiding place behind it. | Safe to enter. |
| `{C2_GATE}` | Stepping in as the deadline wets the floor (quick look vs leave it). | Non-lethal; leaving is always safe. |
| `{C2_ZONE}` | The forgotten store/cache itself. | Historical, safe. |
| `{C2_INNER}` | The state of the interior (mostly-crumbled containers, two dry ones). | Dusty, harmless. |
| `{C2_OFFER1}` | The first recoverable object (a guiding instrument). | Inert, useful. |
| `{C2_OFFER2}` | The second, heavier recoverable object (a rattling hoard). | Inert, carriable. |
| `{C2_PRIZE1_ACT}` | Cleaning/using the first object to find the way out. | Safe, clever. |
| `{C2_PRIZE1}` | Ending: the working recovered instrument (success). | Positive keepsake + story. Names `e_compass`. |
| `{C2_PRIZE2}` | Ending: the recovered hoard studied by experts (success). | Positive; historical find, not stolen loot in a harmful sense. Names `e_coins`. |

---

## How a theme brief consumes this contract

A `theme_brief` provides one value per slot above. Validation before fill should
assert, per the constraints column:

1. No slot value implies death, lethal injury, or an unsurvivable hazard
   (preserves the 8-11 no-death fail-state policy).
2. Every `_GATE` value is a choice a child could safely retreat from.
3. Every `_PRIZE*` value is a benign discovery/keepsake/achievement.
4. `{THRESHOLD}`, `{OPENING_MOMENT}`, `{DEADLINE}` together describe a
   *repeatable, non-lethal* explore-and-return frame.

Because these constraints live in the contract and the ending kinds/valences are
fixed in the skeleton, the deterministic safety gate holds for **any** conforming
theme.
