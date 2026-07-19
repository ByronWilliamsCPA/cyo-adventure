# Skeleton design report: The Cinderwick Exchange

- **Slug / file**: `skeletons/10-13/the-cinderwick-exchange.json`
- **Id / title**: `sk_cinderwick_exchange` / "The Cinderwick Exchange"
- **Cell**: age_band `10-13`, length `short`, narrative_style `prose`
- **Topology**: `sorting_hat`, **tier**: 1 (stateless, no variables)
- **Node count**: 99 (cell envelope 90-140; sits in-band with siblings
  the-midnight-museum=94, the-midnight-frequency=101, the-glass-comet=105)
- **Endings**: 20; **decision nodes**: 13

## Premise

On the Turning, the one night a year the old Cinderwick Exchange (a brick
message-and-clock house above the mills of Marrow Hollow) wakes, twelve-year-old
Wren Ashby is chosen as the town's single new keykeeper. At midnight the Exchange
must send the true-time signal that keeps every clock, mill wheel, and school bell
in the valley honest for the year, and this Turning something has gone wrong in
every one of its four halls at once. Nightmaster Odell Vane cannot mind them all,
so Wren must choose ONE hall to keep through the night.

## How the sort works

A three-node intro (`n_start` -> `n_arrival` -> `n_sort`) delivers the setup and
the single sorting choice. `n_sort` offers four mutually exclusive halls; the
reader's one choice drops them into a self-contained track that never touches the
other three. This is a PURE TREE: every node has in-degree <= 1, there is zero
reconvergence and zero shared downstream nodes between tracks, so PL-18 classifies
the graph as `{time_cave, sorting_hat}` and the declared `sorting_hat` is
admissible. Sorting is purely by the early choice (tier 1, no state).

## Track breakdown (each an identical 24-node pure-tree sub-adventure)

Each track: `root -> intro -> survey -> hub(3-way) ->` an A branch (7 nodes, an
inner 2-way choice, 2 endings), a B branch (5 nodes, 1 ending), and a C branch
(8 nodes, an inner 2-way choice, 2 endings). 3 decisions and 5 endings per track.

1. **The Clockloft** (gears/time; tender Junia the clocksmith). Trouble: the
   master pendulum drags and midnight will fall late. Fix the escapement pallet,
   free a jammed count-wheel, or rebalance the pendulum bob.
2. **The Whispering Gallery** (sound/messages; tender Doran the echo-reader).
   Trouble: a false echo loops in the sound-dome, hiding the true message. Trace
   the false horn, sift the true words by ear, or climb to the master horn. The
   `t2_cd_end` outcome ("The Coaxing Dark") is a non-lethal `capture` (safety-
   flagged): the reader who trusts the coaxing false voice is lured onto the ruined
   gantry, stranded and turned around in the dark, and must be guided back to
   safety by Doran, having lost the message.
3. **The Cistern** (water/pressure; tender Marlow). Trouble: a leaking main will
   drop the pressure that drives the Exchange. Dive and clamp the seam, pump the
   header tank, or shut the great stop-valve.
4. **The Cartway** (pneumatic tubes; tender Effie the runner). Trouble: the
   midnight capsule carrying the true-time token has jammed in the brass veins.
   Crawl the duct, reroute the air pressure, or send a chaser capsule.

## Ending kinds / valences (20 total)

- success x4 (positive), completion x4 (positive)
- discovery x5 (neutral)
- setback x4 (negative), capture x3 (negative)

No `death` endings: `t2_cd_end` was originally tagged `death` but was re-tagged to
non-lethal `capture` to keep this gap-filler consistent with the cell's
established no-death tone (all eleven other 10-13 production skeletons cap their
worst outcome at `setback`/`capture`, and the skeleton-format band table reserves
explicit lethality for 13-16+). The eerie "lured into the dark" tone is kept; the
fatal implication is dropped (the reader is stranded and must retreat, not killed).

Every `ab_end` (the shallowest leaf, depth 11) is non-satisfying by design;
all `success`/`completion` endings sit at depth >= 12, so the PL-20 arc floor
(11) has margin. Kind variety exercises the 10-13 fail-state policy
(logical failure and entrapment) without lethal outcomes.

## Validation

Structural checks (via `scripts/check_skeleton.py`, full gate blocking layers):
pure tree confirmed (0 reconverging nodes, DAG), shortest satisfying path = 12
nodes (floor 11), longest path = 12 hops (max_depth 28), PL-17 floors met
(20 endings >= 15, 13 decisions >= 8), node count 99 within 90-140, tier-1 with
no variables, no em-dash. `check_skeleton.py` final output:

```
stats: nodes=99 endings=20 fill_nodes=99 cell=(10-13, short, prose) topology=sorting_hat tier=1
ok: skeleton passes gate and brief checks
```

Exit code 0, no errors, no warnings.
