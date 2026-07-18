# Three Theme Bindings for `the-cave-of-echoes` (parameterized)

The same parameterized skeleton (`out/pilot/the-cave-of-echoes.parameterized.json`,
identical structure to the production skeleton) filled three different ways. One
structure, three distinct stories. Each binding lists the concrete value of every
**global** slot, the three **route** identities, and a one-line sketch of each
route's two sub-tracks (the two prizes / one prize + the safe turn-back).

The `time_cave` shape is unchanged in all three: one entrance, three routes, each
route forking into two commit-or-turn-back sub-tracks, six safe setback endings
and ten positive prize endings. No death endings in any theme.

---

## A. Sea caves under the old lighthouse (the original theme)

**Global slots**

| Slot | Value |
| --- | --- |
| `{HERO}` | Maya |
| `{COMPANION}` | her dog Biscuit |
| `{THRESHOLD}` | the sea caves under the old lighthouse |
| `{ENTRANCE}` | the cave mouth |
| `{OPENING_MOMENT}` | low tide |
| `{DEADLINE}` | the tide turns |
| `{DEADLINE_SIGN}` | seawater rising around their feet |

**Routes**

- `{ROUTE_A_LURE}` a humming echo / `{ROUTE_B_LURE}` a dripping echo /
  `{ROUTE_C_LURE}` a whispering echo.
- **Route A (glow + resonance).** Track 1: squeeze through a wet crack into a
  crystal grotto, then either take a glowing crystal home (prize) or go deeper to
  a chamber that sings (prize); turn back at the flooding crack = safe setback.
  Track 2: climb an old rope ladder to a sunken ship's bell and recover the lost
  ship's name (prize); refuse the climb = safe setback.
- **Route B (water).** Track 1: descend a weed-slick shelf to an underground
  lake, then row across it (prize) or wade a glowing-shell shallows to a hidden
  islet (prize); back off the shelf = safe setback. Track 2: push through a weed
  curtain into a bright tide-pool, then record a rare starfish (prize) or lift a
  great spiral shell from a deep basin (prize); beat the tide back = safe setback.
- **Route C (dark).** Track 1: cross beneath a sleeping bat roost to a rock stair
  and out a hidden meadow skylight (prize); leave the bats be = safe setback.
  Track 2: open a smugglers' cache and carry out either a working brass compass
  (prize) or a box of old coins (prize); mark it on the map and leave = safe
  setback.

---

## B. Derelict orbital space station (low-power drift)

**Global slots**

| Slot | Value |
| --- | --- |
| `{HERO}` | Priya |
| `{COMPANION}` | her repair-drone Pip |
| `{THRESHOLD}` | the drifting derelict station Halcyon |
| `{ENTRANCE}` | the docking airlock |
| `{OPENING_MOMENT}` | the station's scheduled low-power drift |
| `{DEADLINE}` | the reactor spins back up and seals the bulkheads |
| `{DEADLINE_SIGN}` | warning lights waking up and doors easing shut |

**Routes**

- `{ROUTE_A_LURE}` a resonant power-hum / `{ROUTE_B_LURE}` a hiss of venting
  coolant / `{ROUTE_C_LURE}` a faint intermittent beacon-ping.
- **Route A (energy core).** Track 1: slip through a jammed pressure hatch into a
  crystal-lattice power core, then pocket a still-charged power cell (prize) or go
  deeper to a resonance vault that plays back stored voices (prize); turn back at
  the hatch as pressure drops = safe setback. Track 2: take a maintenance ladder
  down to a great signal-bell antenna and recover a lost ship's transponder ID
  (prize); refuse the descent = safe setback.
- **Route B (fluids bay).** Track 1: edge along a frost-slick catwalk to a vast
  zero-g coolant reservoir, then raft across it on a service pod (prize) or wade a
  glowing-microbe shallow to a hidden observation blister (prize); back off the
  catwalk = safe setback. Track 2: pass a curtain of drifting cabling into a bright
  hydroponics pool, then log a rare bioluminescent creature (prize) or lift a
  perfect data-crystal from a dark tank (prize); beat the bulkheads back = safe
  setback.
- **Route C (dark decks).** Track 1: cross beneath a dormant swarm of charging
  maintenance bots to a debris stair and out a hull viewport onto the sail
  (prize); leave the swarm undisturbed = safe setback. Track 2: force an old crew
  locker and carry out either a working handheld navigator (prize) or a case of
  archival memory chips (prize); tag it on the map and leave = safe setback.

---

## C. Fossil canyon dinosaur dig (dry-season badlands)

**Global slots**

| Slot | Value |
| --- | --- |
| `{HERO}` | Theo |
| `{COMPANION}` | his kestrel Comet |
| `{THRESHOLD}` | the slot canyons of the Redwall fossil beds |
| `{ENTRANCE}` | the canyon trailhead |
| `{OPENING_MOMENT}` | the dry-season morning, before the heat |
| `{DEADLINE}` | the afternoon flash-flood pulse comes down the wash |
| `{DEADLINE_SIGN}` | muddy runoff trickling and rising across the canyon floor |

**Routes**

- `{ROUTE_A_LURE}` a wind that hums through a fluted wall / `{ROUTE_B_LURE}` the
  drip of a seep spring / `{ROUTE_C_LURE}` the dry rattle of loose scree.
- **Route A (crystal seam).** Track 1: squeeze through a narrow slot into a geode
  chamber, then bring out a banded agate (prize) or press deeper to a whispering
  echo-hall of fluted stone (prize); turn back at the slot as runoff pools = safe
  setback. Track 2: down-climb a fixed rope to a giant fossil ribcage and record
  the name of a species lost for ages (prize); refuse the down-climb = safe
  setback.
- **Route B (spring pool).** Track 1: edge a mud-slick ledge to a still canyon
  plunge-pool, then paddle across on a driftwood raft (prize) or wade a
  mineral-glowing shallow to a hidden hanging garden (prize); back off the ledge =
  safe setback. Track 2: part a curtain of hanging roots into a bright spring
  grotto, then sketch a rare blind cave salamander (prize) or lift a perfect
  ammonite from a dark basin (prize); beat the flood back = safe setback.
- **Route C (shadowed undercut).** Track 1: cross beneath a colony of roosting
  cliff swallows to a rockfall stair and out a hidden rim notch onto the mesa
  (prize); leave the nests be = safe setback. Track 2: open an old prospector's
  supply niche and carry out either a still-true brass compass (prize) or a tin of
  antique survey tokens (prize); mark it on the map and leave = safe setback.

---

## What this proves

Every global, route, and per-track slot took a completely different concrete
value across sea-cave, space-station, and fossil-canyon themes, yet:

- the node graph, choice targets, and all 16 ending kinds/valences are byte-for-
  byte identical to the production skeleton;
- each theme keeps the `time_cave` three-route / two-sub-track / commit-or-turn-
  back shape;
- each theme's six turn-back endings stay safe setbacks and each theme's ten deep
  endings stay positive prizes, with no death path introduced.

One structure, three stories, one intact safety gate.
