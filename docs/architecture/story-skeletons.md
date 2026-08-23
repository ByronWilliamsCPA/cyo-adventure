---
title: "Story Skeleton Catalog"
schema_type: common
status: published
owner: core-maintainer
purpose: "Catalog of preset story skeletons (structure diagrams) and the data dictionary for skeleton metadata, generated from skeletons/."
tags:
  - architecture
  - reference
  - documentation
---

A **skeleton** is a structurally-valid Storybook shell: a directed graph of nodes
whose non-ending bodies carry a `<<FILL role=... words=... beats='...'>>` directive
to be replaced by prose. Each skeleton is validated by the gate's blocking layers
at load time, so a skeleton can never introduce a structural defect.

This page catalogs the preset skeletons and defines the controlled vocabulary
behind their metadata. The table below and the band-coverage matrix are generated
from `skeletons/` by `scripts/render_skeleton_diagrams.py`; regenerate after
changing any skeleton:

```bash
PYTHONPATH=. uv run python scripts/render_skeleton_diagrams.py
```

The structure diagrams are PlantUML state diagrams: `[*]` enters the start node,
choices are labeled transitions, and ending nodes are terminal states colored by
valence (green positive, gray neutral, red negative). Non-ending nodes are colored
by narrative role.

<!-- BEGIN GENERATED: skeleton-catalog -->

### Documented skeletons

| Skeleton | Band | Length (min) | Tier | Topology | Nodes | Endings (+/n/-) | Diagram |
| --- | --- | --- | --- | --- | --- | --- | --- |
| The Blackout Week | 10-13 | 7 | 1 | branch_and_bottleneck | 91 | 10/9/0 | [svg](diagrams/skeletons/10-13/the-blackout-week.svg) |
| The Cartographer's Apprentice | 10-13 | 9 | 1 | branch_and_bottleneck | 254 | 12/16/15 | [svg](diagrams/skeletons/10-13/the-cartographers-apprentice.svg) |
| The Cinderwick Exchange | 10-13 | 12 | 1 | sorting_hat | 99 | 8/5/7 | [svg](diagrams/skeletons/10-13/the-cinderwick-exchange.svg) |
| The Clocktower Cipher | 10-13 | 18 | 1 | branch_and_bottleneck | 26 | 3/1/4 | [svg](diagrams/skeletons/10-13/the-clocktower-cipher.svg) |
| The Envoy of Three Courts | 10-13 | 9 | 1 | sorting_hat | 159 | 18/6/6 | [svg](diagrams/skeletons/10-13/the-envoy-of-three-courts.svg) |
| The Flooded Quarter | 10-13 | 10 | 2 | open_map | 155 | 12/9/7 | [svg](diagrams/skeletons/10-13/the-flooded-quarter.svg) |
| The Glass Comet | 10-13 | 7 | 2 | branch_and_bottleneck | 105 | 4/11/5 | [svg](diagrams/skeletons/10-13/the-glass-comet.svg) |
| The Hollow Lighthouse | 10-13 | 13 | 1 | branch_and_bottleneck | 149 | 10/5/16 | [svg](diagrams/skeletons/10-13/the-hollow-lighthouse.svg) |
| The Mapmaker's Island | 10-13 | 22 | 1 | branch_and_bottleneck | 225 | 11/32/29 | [svg](diagrams/skeletons/10-13/the-mapmakers-island.svg) |
| The Midnight Frequency | 10-13 | 7 | 1 | open_map | 101 | 9/2/7 | [svg](diagrams/skeletons/10-13/the-midnight-frequency.svg) |
| The Midnight Museum | 10-13 | 9 | 1 | branch_and_bottleneck | 95 | 7/3/9 | [svg](diagrams/skeletons/10-13/the-midnight-museum.svg) |
| The Observatory Shift | 10-13 | 16 | 1 | sorting_hat | 145 | 9/11/7 | [svg](diagrams/skeletons/10-13/the-observatory-shift.svg) |
| The Orchard Signal | 10-13 | 7 | 1 | branch_and_bottleneck | 173 | 9/15/6 | [svg](diagrams/skeletons/10-13/the-orchard-signal.svg) |
| The Skyrail Heist | 10-13 | 11 | 1 | sorting_hat | 246 | 29/6/5 | [svg](diagrams/skeletons/10-13/the-skyrail-heist.svg) |
| The Winter of the Wolf Queen | 10-13 | 12 | 2 | open_map | 250 | 19/14/7 | [svg](diagrams/skeletons/10-13/the-winter-of-the-wolf-queen.svg) |
| The Conservatory Wars | 13-16 | 11 | 1 | sorting_hat | 160 | 20/4/2 | [svg](diagrams/skeletons/13-16/the-conservatory-wars.svg) |
| The Glasswright's Debt | 13-16 | 11 | 1 | branch_and_bottleneck | 130 | 7/10/6 | [svg](diagrams/skeletons/13-16/the-glasswright-debt.svg) |
| The Harrowstone Keep | 13-16 | 30 | 2 | branch_and_bottleneck | 551 | 4/3/145 | [svg](diagrams/skeletons/13-16/the-harrowstone-keep.svg) |
| The Hollow Crown Gambit | 13-16 | 11 | 1 | branch_and_bottleneck | 434 | 8/10/40 | [svg](diagrams/skeletons/13-16/the-hollow-crown-gambit.svg) |
| The Hollow Sea | 13-16 | 24 | 2 | open_map | 197 | 21/12/7 | [svg](diagrams/skeletons/13-16/the-hollow-sea.svg) |
| The Iron Spire Trial | 13-16 | 30 | 2 | gauntlet | 277 | 2/1/76 | [svg](diagrams/skeletons/13-16/the-iron-spire-trial.svg) |
| The Labyrinth of Glass | 13-16 | 35 | 1 | gauntlet | 383 | 2/1/113 | [svg](diagrams/skeletons/13-16/the-labyrinth-of-glass.svg) |
| The Migration Year | 13-16 | 14 | 1 | branch_and_bottleneck | 176 | 10/13/7 | [svg](diagrams/skeletons/13-16/the-migration-year.svg) |
| The Quarry Signal | 13-16 | 10 | 2 | branch_and_bottleneck | 267 | 9/8/19 | [svg](diagrams/skeletons/13-16/the-quarry-signal.svg) |
| The Saltmarsh Run | 13-16 | 8 | 1 | gauntlet | 322 | 6/9/27 | [svg](diagrams/skeletons/13-16/the-saltmarsh-run.svg) |
| The Serpent Vaults | 13-16 | 35 | 2 | gauntlet | 530 | 4/33/135 | [svg](diagrams/skeletons/13-16/the-serpent-vaults.svg) |
| The Signal in the Static | 13-16 | 11 | 1 | branch_and_bottleneck | 124 | 11/0/21 | [svg](diagrams/skeletons/13-16/the-signal-in-the-static.svg) |
| The Smuggler's Cut | 13-16 | 16 | 1 | branch_and_bottleneck | 277 | 2/1/77 | [svg](diagrams/skeletons/13-16/the-smugglers-cut.svg) |
| The Sunken Temple | 13-16 | 30 | 2 | branch_and_bottleneck | 551 | 4/3/145 | [svg](diagrams/skeletons/13-16/the-sunken-temple.svg) |
| The Sunspire Ascent | 13-16 | 15 | 1 | branch_and_bottleneck | 253 | 2/5/67 | [svg](diagrams/skeletons/13-16/the-sunspire-ascent.svg) |
| The Thornwood Trial | 13-16 | 24 | 1 | branch_and_bottleneck | 376 | 4/0/111 | [svg](diagrams/skeletons/13-16/the-thornwood-trial.svg) |
| The Undertow Season | 13-16 | 11 | 2 | open_map | 128 | 12/10/6 | [svg](diagrams/skeletons/13-16/the-undertow-season.svg) |
| The Vanishing Orchard | 13-16 | 18 | 1 | branch_and_bottleneck | 178 | 5/5/23 | [svg](diagrams/skeletons/13-16/the-vanishing-orchard.svg) |
| The Year of Four Banners | 13-16 | 26 | 1 | sorting_hat | 212 | 10/11/12 | [svg](diagrams/skeletons/13-16/the-year-of-four-banners.svg) |
| The Ashfall Expedition | 16+ | 30 | 1 | branch_and_bottleneck | 506 | 3/0/140 | [svg](diagrams/skeletons/16+/the-ashfall-expedition.svg) |
| The Blackwood Sanatorium | 16+ | 40 | 1 | open_map | 151 | 2/8/14 | [svg](diagrams/skeletons/16+/the-blackwood-sanatorium.svg) |
| The Cinder Bazaar | 16+ | 40 | 2 | branch_and_bottleneck | 453 | 3/18/120 | [svg](diagrams/skeletons/16+/the-cinder-bazaar.svg) |
| The Drowned Court | 16+ | 18 | 1 | branch_and_bottleneck | 315 | 5/2/98 | [svg](diagrams/skeletons/16+/the-drowned-court.svg) |
| The Last Cartage | 16+ | 16 | 1 | gauntlet | 632 | 6/15/67 | [svg](diagrams/skeletons/16+/the-last-cartage.svg) |
| The Last Train North | 16+ | 14 | 1 | branch_and_bottleneck | 144 | 5/9/11 | [svg](diagrams/skeletons/16+/the-last-train-north.svg) |
| The Long Thaw | 16+ | 18 | 1 | branch_and_bottleneck | 220 | 6/28/11 | [svg](diagrams/skeletons/16+/the-long-thaw.svg) |
| The Longwinter Station | 16+ | 34 | 2 | open_map | 248 | 22/9/13 | [svg](diagrams/skeletons/16+/the-longwinter-station.svg) |
| The Obsidian Relay | 16+ | 12 | 1 | branch_and_bottleneck | 393 | 5/11/46 | [svg](diagrams/skeletons/16+/the-obsidian-relay.svg) |
| The Pale Road | 16+ | 45 | 1 | gauntlet | 498 | 2/1/147 | [svg](diagrams/skeletons/16+/the-pale-road.svg) |
| The Quarantine Ledger | 16+ | 14 | 1 | branch_and_bottleneck | 141 | 6/23/9 | [svg](diagrams/skeletons/16+/the-quarantine-ledger.svg) |
| The Quiet Harbor Protocol | 16+ | 24 | 2 | branch_and_bottleneck | 153 | 3/11/14 | [svg](diagrams/skeletons/16+/the-quiet-harbor-protocol.svg) |
| The Red Meridian Run | 16+ | 30 | 1 | gauntlet | 306 | 2/1/87 | [svg](diagrams/skeletons/16+/the-red-meridian-run.svg) |
| The Salt Archive | 16+ | 24 | 1 | branch_and_bottleneck | 226 | 15/21/18 | [svg](diagrams/skeletons/16+/the-salt-archive.svg) |
| The Sunken Signal | 16+ | 30 | 2 | branch_and_bottleneck | 33 | 1/1/12 | [svg](diagrams/skeletons/16+/the-sunken-signal.svg) |
| The Tenfold Siege | 16+ | 55 | 2 | gauntlet | 677 | 2/3/204 | [svg](diagrams/skeletons/16+/the-tenfold-siege.svg) |
| The Third Shift | 16+ | 26 | 1 | sorting_hat | 151 | 6/11/11 | [svg](diagrams/skeletons/16+/the-third-shift.svg) |
| The Tricameral City | 16+ | 44 | 1 | sorting_hat | 240 | 8/17/17 | [svg](diagrams/skeletons/16+/the-tricameral-city.svg) |
| Baking Day with Grandma Vole | 3-5 | 6 | 1 | loop_and_grow | 30 | 6/0/0 | [svg](diagrams/skeletons/3-5/baking-day-with-grandma-vole.svg) |
| Puddle Jumping Day | 3-5 | 3 | 1 | time_cave | 19 | 4/0/0 | [svg](diagrams/skeletons/3-5/puddle-jumping-day.svg) |
| The Big Cardboard Box | 3-5 | 3 | 1 | time_cave | 44 | 6/12/0 | [svg](diagrams/skeletons/3-5/the-big-cardboard-box.svg) |
| The Big Red Balloon | 3-5 | 4 | 1 | time_cave | 32 | 5/1/0 | [svg](diagrams/skeletons/3-5/the-big-red-balloon.svg) |
| Clover and the Butterfly | 3-5 | 2 | 1 | time_cave | 20 | 4/3/0 | [svg](diagrams/skeletons/3-5/the-clover-and-the-butterfly.svg) |
| The Last Blue Cup | 3-5 | 2 | 1 | loop_and_grow | 17 | 3/3/0 | [svg](diagrams/skeletons/3-5/the-last-blue-cup.svg) |
| The Lost Mitten | 3-5 | 3 | 1 | loop_and_grow | 11 | 3/0/0 | [svg](diagrams/skeletons/3-5/the-lost-mitten.svg) |
| The Market Morning | 3-5 | 3 | 1 | time_cave | 21 | 6/0/0 | [svg](diagrams/skeletons/3-5/the-market-morning.svg) |
| The Sleepy Little Star | 3-5 | 3 | 1 | loop_and_grow | 17 | 3/0/0 | [svg](diagrams/skeletons/3-5/the-sleepy-little-star.svg) |
| The Teddy Bears' Picnic | 3-5 | 3 | 1 | loop_and_grow | 29 | 5/6/0 | [svg](diagrams/skeletons/3-5/the-teddy-bears-picnic.svg) |
| The Very Tall Slide | 3-5 | 5 | 1 | loop_and_grow | 35 | 3/3/0 | [svg](diagrams/skeletons/3-5/the-very-tall-slide.svg) |
| The Backyard Treasure Map | 5-8 | 7 | 1 | time_cave | 62 | 6/6/0 | [svg](diagrams/skeletons/5-8/the-backyard-treasure-map.svg) |
| The Bridge of Stones | 5-8 | 11 | 1 | open_map | 58 | 6/4/2 | [svg](diagrams/skeletons/5-8/the-bridge-of-stones.svg) |
| The Lantern Festival | 5-8 | 6 | 1 | loop_and_grow | 37 | 7/3/0 | [svg](diagrams/skeletons/5-8/the-lantern-festival.svg) |
| The Night Market | 5-8 | 9 | 1 | open_map | 60 | 9/4/0 | [svg](diagrams/skeletons/5-8/the-night-market.svg) |
| The Paper Plane Hall | 5-8 | 8 | 1 | loop_and_grow | 50 | 4/9/0 | [svg](diagrams/skeletons/5-8/the-paper-plane-hall.svg) |
| The School Garden Mystery | 5-8 | 8 | 1 | open_map | 35 | 4/3/0 | [svg](diagrams/skeletons/5-8/the-school-garden-mystery.svg) |
| The Seedling Thief | 5-8 | 5 | 1 | open_map | 31 | 6/4/0 | [svg](diagrams/skeletons/5-8/the-seedling-thief.svg) |
| The Snow Day Expedition | 5-8 | 7 | 1 | time_cave | 38 | 8/2/0 | [svg](diagrams/skeletons/5-8/the-snow-day-expedition.svg) |
| The Tide Pool Rescue | 5-8 | 10 | 1 | loop_and_grow | 55 | 10/2/0 | [svg](diagrams/skeletons/5-8/the-tide-pool-rescue.svg) |
| The Cave of Echoes | 8-11 | 8 | 1 | time_cave | 65 | 10/6/0 | [svg](diagrams/skeletons/8-11/the-cave-of-echoes.svg) |
| The Clockwork Menagerie | 8-11 | 18 | 1 | branch_and_bottleneck | 167 | 14/6/7 | [svg](diagrams/skeletons/8-11/the-clockwork-menagerie.svg) |
| The Guild of Junior Inventors | 8-11 | 12 | 1 | sorting_hat | 191 | 11/8/15 | [svg](diagrams/skeletons/8-11/the-guild-of-junior-inventors.svg) |
| The Half-Hour Call | 8-11 | 8 | 1 | branch_and_bottleneck | 61 | 7/7/0 | [svg](diagrams/skeletons/8-11/the-half-hour-call.svg) |
| The Hundred-Door Hotel | 8-11 | 12 | 1 | open_map | 176 | 6/24/1 | [svg](diagrams/skeletons/8-11/the-hundred-door-hotel.svg) |
| The Lantern Keepers' List | 8-11 | 10 | 1 | branch_and_bottleneck | 125 | 10/12/2 | [svg](diagrams/skeletons/8-11/the-lantern-keepers-list.svg) |
| The Locked Carousel | 8-11 | 8 | 1 | open_map | 71 | 6/7/0 | [svg](diagrams/skeletons/8-11/the-locked-carousel.svg) |
| The River of Small Boats | 8-11 | 10 | 1 | time_cave | 127 | 17/9/0 | [svg](diagrams/skeletons/8-11/the-river-of-small-boats.svg) |
| The Robot Fair Sabotage | 8-11 | 8 | 1 | branch_and_bottleneck | 74 | 5/5/4 | [svg](diagrams/skeletons/8-11/the-robot-fair-sabotage.svg) |
| The Sky-Ship Stowaway | 8-11 | 11 | 1 | branch_and_bottleneck | 112 | 8/8/4 | [svg](diagrams/skeletons/8-11/the-sky-ship-stowaway.svg) |
| The Storm Chasers Club | 8-11 | 10 | 1 | sorting_hat | 121 | 16/5/4 | [svg](diagrams/skeletons/8-11/the-storm-chasers-club.svg) |
| The Tin Whistle Map | 8-11 | 11 | 1 | branch_and_bottleneck | 193 | 15/14/6 | [svg](diagrams/skeletons/8-11/the-tin-whistle-map.svg) |

### Band coverage

| Age band | Skeletons |
| --- | --- |
| 3-5 | yes |
| 5-8 | yes |
| 8-11 | yes |
| 10-13 | yes |
| 13-16 | yes |
| 16+ | yes |

<!-- END GENERATED: skeleton-catalog -->

Most catalogued skeletons are production-eligible and together cover every
`(age_band, length, narrative_style)` cell the ADR-011 production matrix offers, each
declaring its `length`, `narrative_style` (where the band is style-aware), and
`metadata.production_eligible: true`. For the current shell, node, and per-cell counts
see [the catalog census](../planning/catalog-census.md), which is generated from the
catalog; the figures that used to be written out here were correct on the day they were
typed and then went stale in place (`UW-G24`). Three skeletons
(The Clocktower Cipher, The Sunken Signal, The Lost Mitten) declare
`production_eligible: false` and no `length` or `narrative_style`: they are ADR-011
section 1a MVP/Test-tier development seeds (a band-independent 8-45 node envelope,
budgeted with `mvp_node_budget` in `validator/band_profile.py`), not examples of a
production cell, and are excluded from the cell-aware selection described below. The
"Length (min)" column above is `estimated_minutes` (a read-time estimate), not the
ADR-011 `length` scale tier described below; per-cell production node budgets live in
`validator/band_profile.py` (`_PRODUCTION_CELLS`), not a single fixed per-band range.
The "Tier" column is the generation `tier` field (`1` forbids state variables, `2`
allows them), a separate concept from the MVP/Test tier.

## Skeleton selection

When an admin builds the authoring plan for an approved story request
(`story_requests/authoring_plan.py`), the skeleton for a `skeleton_fill` plan is chosen
by **cell-aware matching**, not by band alone (`generation/skeleton_match.py`). This
replaced an earlier band-only, style/length-blind `select_skeleton_for_band` helper as
part of the skeleton-matching rework (workstream WS-C, PR #175).

1. **Cell match.** `candidates_for_cell(band, length, style)` scans every
   production-eligible skeleton file under `skeletons/<band>/` and keeps only those
   whose metadata matches the request's `(age_band, length, narrative_style)` cell
   (`skeleton_matches_cell`). A skeleton that declares no `length` is a wildcard that
   matches any request length. `narrative_style` is checked only for the two
   style-aware bands, `13-16` and `16+`; every other band is implicitly `prose`. If no
   skeleton matches the cell, the authoring plan is rejected (422) rather than falling
   back to a different cell.
2. **Recency-weighted pick.** Among the in-cell candidates, `select_skeleton_for_cell`
   draws a weighted-random slug so a family does not keep seeing the same skeleton
   repeated. The weight is inverse-frequency, `1 / (1 + recent_count)`, where
   `recent_count` (from `recent_skeleton_usage`) is how many of the family's most
   recent 20 `storybook_version` rows used that slug, counted across every status and
   every storybook (skeleton diversity reflects authoring activity, not delivery). An
   unused skeleton gets weight `1.0`; a recently-used one is discounted but never
   reaches zero, so no candidate is ever fully excluded. A family-less (admin or
   catalog-origin) request has no recency history and gets a uniform pick.
3. **Admin override.** An admin may set `skeleton_slug` directly on the authoring plan
   (decision C-6); the override is unconstrained and may name a skeleton outside the
   request's own cell or band. `find_skeleton_metadata` resolves it by scanning every
   band directory, rejects any path-traversal attempt (`resolve_skeleton_path`), and
   the caller records the skeleton's *real* band rather than the request's band. An
   out-of-cell or non-production-eligible override is accepted but attaches a
   non-blocking warning to the authoring-plan result instead of failing.

Skeleton selection is a distinct concern from **provider selection**: which LLM
backend (Anthropic, OpenRouter, or Modal) fills the chosen skeleton's
`<<FILL>>` directives is governed separately by the admin-editable provider/model
allowlist (`generation/allowlist.py`, workstream WS-C PR #170) and
`generation/provider.py::build_provider`. Which skeleton is picked and which provider
fills it are independent decisions within the same authoring plan.

## Character envelope (`accepts_character`)

A skeleton may opt into the persistent reader character introduced by
[ADR-028](../planning/adr/adr-028-persistent-reader-characters.md) by declaring an `accepts_character`
field: a mapping from canonical variable name to the inclusive range the skeleton proves
itself safe across. A character is a seeded `VarState`, carried into the book by the existing
name-match seeding path; omitting the field means the book accepts no character at all.

**Zero catalog skeletons declare an envelope today.** `grep -rl accepts_character skeletons/`
returns nothing: every rule described below is implemented, tested, and unreached, so no reader
can currently be bound to a character through a catalog book. Two pilots were drafted during the
ADR-028 workstream and both were withdrawn on 2026-08-08 (see `UW-A46`, `AL-129`, `AL-131`). Read
this section as the contract a future participating skeleton must meet, not as a description of
anything in the catalog now.

The canonical vocabulary is four variables: `archetype` (0-6, declared by prose cells) and
`might`/`wits`/`nerve` (0-2 each, declared by gamebook cells). `archetype` and the stats never
appear in the same envelope: in a mechanics-driven gamebook the stat spread already is the
archetype, so `archetype` carries identity only in prose cells that have no stats to infer it
from. A participating prose skeleton keeps an in-story build node, gated behind a bypass node,
that sets `archetype` from its initial `0` ("not yet chosen") to 1-6 for a first-time reader,
while a returning reader arrives already carrying a value and is routed past it.

The `CH-1` through `CH-8` rules (`validator/character.py`) prove a declared envelope safe
before publication: vocabulary and range checks that need no state-space walk (`CH-1`, `CH-2`,
`CH-5`, `CH-6`, `CH-7`), three rules that re-walk Layer 2 once per envelope entry state to
prove no dead branch, no new per-state defect, and a satisfying ending remains reachable
(`CH-3a`, `CH-3b`, `CH-4`), and a build-node cost pre-flight (`CH-8`) that rejects a skeleton
too large to host the archetype build node's six-way branching before the walk cap would. Full
rule definitions live in [`docs/planning/validator-rules.md`](../planning/validator-rules.md);
authoring guidance for declaring an envelope, the archetype/stats split, and the build node
idiom lives in `.claude/skills/cyo-author/reference/skeleton-format.md`.

**Gate-time cost is mechanism-driven, not fixed.** Because `CH-3a`/`CH-3b`/`CH-4` re-walk the
story once per entry state, cost scales with how many states the envelope admits: 7 for an
`archetype`-only envelope, 3 x 3 x 3 = 27 for the canonical three-stat envelope. Measured on
`skeletons/16+/the-longwinter-station.json` (248 nodes, 51,241 base configurations), the gate
took 0.77s with no envelope and 49.58s with the canonical 27-state envelope, a roughly 64x
multiplier (`docs/planning/unscheduled-work-register.md` rows UW-A47 and UW-A48). This does not
change what `CH-5`'s 64-state cap admits; it changes how long an admissible skeleton takes to
gate.

The unit that makes this predictable is the **config-walk**: base configurations multiplied by the
envelope's entry states. The skeleton's own declared-initial walk is counted separately, not folded
into that multiplier, because it runs whether or not an envelope is declared. Cost runs at roughly
**3.5e-5 seconds per config-walk** on large graphs, measured across skeletons spanning three orders
of magnitude of walk count, and the anchor point is `the-longwinter-station`: 51,241 base
configurations x 27 envelope states = 1,383,507 config-walks at 48.8s of envelope-attributable
time, with the remaining 0.77s of the 49.58s whole-gate run being that baseline walk.

**No per-run gate budget exists.** An earlier revision of this section compared the anchor against a
"~12s gate budget"; no such budget was ever set, in the roadmap, in CI config, or in any ADR, so the
comparison has been removed rather than replaced with another number. The measured 49.58s whole-gate
run on this skeleton (`UW-A47`, `UW-A48`) is the reference point authors should size against, and
the authoring-facing arithmetic that follows from it, including the per-envelope table, is in
`.claude/skills/cyo-author/reference/skeleton-format.md`.

**The stat-gate wall (`L2-11`).** A skeleton declaring a `might`/`wits`/`nerve` envelope cannot gate
a choice condition directly on a stat threshold. `validator/layer2.py::_check_dead_branches` walks
only the skeleton's single declared-initial baseline configuration with no `accepts_character`
awareness, so a `might >= 2` branch is unconditionally unreachable in baseline whenever the declared
initial sits below the threshold, and `L2-11` blocks publication before any CH-* rule runs. `CH-3a`'s
union-quantified walk does not suppress it, because `L2-11` is raised on the baseline walk
independently. The archetype build-node idiom does not transfer, since a stat book deliberately has
no in-story mutating node. The authoring workaround (an auxiliary non-canonical `resolve` boolean,
reset by an unconditioned choice immediately before the gate and XOR-combined with the stat
threshold) is documented in `.claude/skills/cyo-author/reference/skeleton-format.md`, and it carries
a real cost rather than a cosmetic one: because a free player choice must be able to flip the
outcome, **the reader cannot perceive the stat deciding anything**, which is why a 13-16 pilot built
on the pattern was withdrawn in 2026-08. Making `_check_dead_branches` envelope-aware would remove
the need for the workaround; that is an open validator question tracked as `UW-C64`.

## Data dictionary

Sourced from `src/cyo_adventure/storybook/models.py` (the enforced schema), with one
exception: node `role` is a FILL-directive convention read by
`generation/diagram.py`, not a field the structural gate enforces. Where
`.claude/skills/cyo-author/reference/skeleton-format.md` disagrees, the model wins.

| Variable | Type | Preset options / constraint |
| --- | --- | --- |
| `age_band` | closed enum | `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+` |
| `tier` | int 1-2 | `1`, `2` (tier 1 forbids state variables) |
| `topology` | closed enum | `time_cave`, `gauntlet`, `branch_and_bottleneck`, `loop_and_grow`, `open_map`, `sorting_hat` |
| `length` | closed enum, optional | `short`, `medium`, `long`; the ADR-011 story-scale axis. Young bands (`3-5`, `5-8`) cap at `medium`. Omitted means the story is not scale-classified |
| `narrative_style` | closed enum, optional | `prose`, `gamebook`; meaningful only for `13-16`/`16+`; every other band is implicitly `prose` |
| `production_eligible` | bool | defaults to `true`; `false` marks a non-production MVP/Test-tier skeleton (ADR-011 section 1a) |
| `valence` | closed enum | `positive`, `neutral`, `negative` |
| `ending.kind` | closed enum | `success`, `setback`, `death`, `capture`, `completion`, `discovery` |
| content flags | level enum per category | categories `violence`, `scariness`, `peril`; levels `none` < `mild` < `moderate` < `intense` |
| `estimated_minutes` | int >= 1 | open (a read-time estimate; not the `length` scale tier above) |
| node `role` | FILL directive | `setup`, `rising`, `choice`, `climax`, plus ending subtypes |

### Definitions

- **age_band** -- the reading age the story targets; drives reading-level, content,
  and fail-state policy.
- **estimated_minutes** -- an integer read-time estimate (the "Length (min)" catalog
  column); distinct from the `length` scale-tier field below.
- **length** -- the ADR-011 story-scale tier (`short` / `medium` / `long`), one axis of
  the `(age_band, length, narrative_style)` production matrix whose per-cell node
  budgets live in `validator/band_profile.py` (`_PRODUCTION_CELLS`). Optional: a
  skeleton that declares no `length` is not scale-classified and keeps the band-level
  budget instead of a per-cell production node budget.
- **narrative_style** -- `prose` or `gamebook`; chunks the same word budget into
  fewer/longer or more/shorter nodes. Meaningful only for `13-16` and `16+`; every
  other band is implicitly `prose`.
- **production_eligible** -- defaults to `true`. `false` marks a non-production
  MVP/Test-tier skeleton (ADR-011 section 1a): a band-independent 8-45 node envelope
  for prototyping and pipeline/generator testing, excluded from child-facing
  production selection regardless of band. All three skeletons in this catalog are
  currently `production_eligible: false` development seeds, not examples of a
  production `(age_band, length, narrative_style)` cell.
- **tier** -- generation tier; tier 1 stories declare no state variables. Not to be
  confused with the MVP/Test tier above (a `production_eligible` concept).
- **topology** -- the branching shape of the graph (Ashwell vocabulary). Six ADR-011
  topologies: `time_cave`, `gauntlet`, `branch_and_bottleneck` (absorbs the retired
  Ashwell `quest` variant), `loop_and_grow`, `open_map`, and `sorting_hat`.
- **valence** -- how an ending feels (positive / neutral / negative), independent of
  what mechanically happened.
- **ending.kind** -- what mechanically happened at an ending (closed set).
- **content flags** -- per-category sensitivity levels, scored against the band ceiling.
- **role** -- a node's narrative function, declared in its FILL directive.
