# Wave 5 design briefs: 36 new skeletons (2 per production cell)

Supervisor-authored briefs for the skeleton-expansion wave of
`docs/planning/story-inventory-initial-run.md` (section 6.1). Each brief pins the
cell, topology, tier, a node-count target inside the cell envelope, and a theme
premise. Numeric contracts not listed here (words/node envelope, per-band content
ceilings, forbidden ending kinds, arc floor) come from `validator/band_profile.py`
and are restated in each designer prompt.

Diversity rule: within a cell, the two new skeletons must differ from each other and
from the existing skeleton in topology (wherever the band allowance offers more than
one) and in theme. Every existing 8-11+ production skeleton is
`branch_and_bottleneck`, so this wave deliberately exercises `open_map`,
`sorting_hat`, `time_cave`, and `gauntlet`.

Tier-2 rule: at 10-13 and up, exactly one of the two new skeletons per cell is
Tier 2 (declared variables, effects, conditions); the other stays Tier 1. Bands
below 10-13 are all Tier 1 in this wave.

Dagger-cell rule (per product direction): in each dagger cell (13-16 Long gamebook,
16+ Medium gamebook, 16+ Long gamebook), one skeleton targets the low end of the
envelope and one deliberately targets the upper half, to empirically test ADR-011's
~460-node hand-authoring ceiling. Ceiling-challenger design reports must record
chunks needed, repair cycles, findings density, and cost vs the low-end sibling.

| # | Cell (band/length/style) | Slug | Topology | Tier | Node target | min-complete | Endings | Theme premise |
| -: | --- | --- | --- | :-: | --- | :-: | --- | --- |
| 1 | 3-5 / short / prose | the-sleepy-little-star | loop_and_grow | 1 | 14-20 | 6 | 2-4 | A little star is scared to come out at night; gentle try-again loops (too shy, too wiggly) until the sky feels just right. |
| 2 | 3-5 / short / prose | puddle-jumping-day | time_cave | 1 | 16-22 | 6 | 3-4 | A rainy-day walk; each puddle or path is a tiny branching adventure with splashy, cozy endings. |
| 3 | 3-5 / medium / prose | the-big-red-balloon | time_cave | 1 | 28-40 | 7 | 4-6 | A balloon slips away at the park; follow it past the duck pond, the ice-cream cart, and the kite hill. |
| 4 | 3-5 / medium / prose | baking-day-with-grandma-vole | loop_and_grow | 1 | 30-42 | 7 | 4-6 | Pip Vole and Grandma Vole bake seed-honey buns in their burrow kitchen; each ingredient hunt can comically go wrong and loop back for another try. (Protagonist changed from a bear to avoid re-skinning the teddy-bears-picnic sibling.) |
| 5 | 5-8 / short / prose | the-school-garden-mystery | open_map | 1 | 34-46 | 7 | 6-9 | Something is nibbling the class lettuce; explore the garden's corners in any order to gather clues. |
| 6 | 5-8 / short / prose | the-snow-day-expedition | time_cave | 1 | 34-48 | 7 | 6-10 | A backyard becomes the Arctic on a snow day; every route is a different pretend expedition. |
| 7 | 5-8 / medium / prose | the-tide-pool-rescue | loop_and_grow | 1 | 55-75 | 9 | 10-14 | Help stranded tide-pool creatures before the tide comes back; comic retries when a plan flops. |
| 8 | 5-8 / medium / prose | the-night-market | open_map | 1 | 58-80 | 9 | 10-15 | A lantern-lit night market hub; visit stalls in any order to trade small kindnesses for what a lost friend needs. |
| 9 | 8-11 / short / prose | the-robot-fair-sabotage | branch_and_bottleneck | 1 | 65-90 | 9 | 12-16 | Someone tampered with the science-fair robots; routes through suspects bottleneck at the big demo. |
| 10 | 8-11 / short / prose | the-locked-carousel | open_map | 1 | 65-90 | 9 | 12-16 | An old funfair after hours; explore rides in any order to find why the carousel is sealed (moderate spooky, no death). |
| 11 | 8-11 / medium / prose | the-storm-chasers-club | sorting_hat | 1 | 110-150 | 12 | 18-26 | Join the club and get sorted into radio, mapping, or field-kit tracks; each track rides the same storm differently. |
| 12 | 8-11 / medium / prose | the-river-of-small-boats | time_cave | 1 | 110-150 | 12 | 18-26 | A toy-boat race down a real river; channels, locks, and islands as committed forks flowing downstream. (Topology changed from open_map per reviewer shelf guidance: hold the 8-11 band at two open_maps.) |
| 13 | 8-11 / long / prose | the-guild-of-junior-inventors | sorting_hat | 1 | 170-220 | 14 | 28-36 | Guild trials sort you into gears, gliders, or gadgets; three parallel workshop arcs to a shared showcase. |
| 14 | 8-11 / long / prose | the-hundred-door-hotel | open_map | 1 | 170-220 | 14 | 28-36 | A grand old hotel with numbered doors; explore floors in any order to reunite a family of ghosts (friendly, moderate spooky). |
| 15 | 10-13 / short / prose | the-midnight-frequency | open_map | 1 | 95-125 | 11 | 14-20 | A numbers-station scavenger hunt across town; tune, decode, and visit sites in any order before dawn. |
| 16 | 10-13 / short / prose | the-glass-comet | branch_and_bottleneck | 2 | 95-125 | 11 | 14-20 | One night at an observatory to photograph a comet; a small state machine (plates, clouds, time) gates the perfect shot. |
| 17 | 10-13 / medium / prose | the-envoy-of-three-courts | sorting_hat | 1 | 150-200 | 14 | 22-30 | A young envoy is assigned to one of three rival courts; each track sees the same brewing treaty crisis from a different side. |
| 18 | 10-13 / medium / prose | the-flooded-quarter | open_map | 2 | 150-200 | 14 | 22-30 | A river city's quarter floods overnight; water-level and supplies variables gate which streets are passable. |
| 19 | 10-13 / long / prose | the-skyrail-heist | sorting_hat | 1 | 240-300 | 17 | 32-42 | Recover a stolen archive from a moving skyrail; sorted into planner, climber, or talker crew tracks. |
| 20 | 10-13 / long / prose | the-winter-of-the-wolf-queen | open_map | 2 | 240-300 | 17 | 32-42 | A winter journey between mountain villages; warmth and provisions state decides which passes and shelters open. |
| 21 | 13-16 / medium / prose | the-undertow-season | open_map | 2 | 125-160 | 15 | 20-28 | A lifeguard summer in a town with a drowned secret; trust variables with locals open or close the truth. |
| 22 | 13-16 / medium / prose | the-conservatory-wars | sorting_hat | 1 | 125-160 | 15 | 20-28 | An elite music school sorts new students into three studios; rivalry, sabotage, and one shared final concert. |
| 23 | 13-16 / medium / gamebook | the-iron-spire-trial | gauntlet | 2 | 260-320 | 24 | many fails (~25-35% terminals) | A formal ascent trial up a fortified spire; one true path, many lethal missteps, restart-on-fail checkpoints. |
| 24 | 13-16 / medium / gamebook | the-smugglers-cut | branch_and_bottleneck | 1 | 260-330 | 24 | many fails | A night heist through a canal city; route choices bottleneck at the vault, with lethal fail branches. |
| 25 | 13-16 / long / prose | the-year-of-four-banners | sorting_hat | 1 | 190-240 | 20 | 30-40 | A succession year told from inside one of three factions; your banner decides which betrayals you witness. |
| 26 | 13-16 / long / prose | the-hollow-sea | open_map | 2 | 190-240 | 20 | 30-40 | Chart an inland sea that swallows sound; hull and supplies state gates islands, storms, and the sea's answer. |
| 27 | 13-16 / long / gamebook | the-labyrinth-of-glass | gauntlet | 1 | 380-420 (dagger: LOW end) | 32 | many fails | A mirror labyrinth beneath an opera house; disciplined single-spine gauntlet with restart-on-fail. |
| 28 | 13-16 / long / gamebook | the-serpent-vaults | gauntlet | 2 | 500-585 (dagger: CEILING CHALLENGER) | 32 | many fails | Descend a flooded vault network; state-gated locks and air supply. Deliberately above the ~460-node ceiling to test it. |
| 29 | 16+ / medium / prose | the-third-shift | sorting_hat | 1 | 150-190 | 18 | 24-32 | New hire at a facility that only exists at night; sorted into security, archives, or maintenance, each shift sees a different wrongness. |
| 30 | 16+ / medium / prose | the-quiet-harbor-protocol | branch_and_bottleneck | 2 | 150-190 | 18 | 24-32 | A retired signals officer spots a dead protocol reactivating; suspicion and evidence state decide who can be trusted at the rendezvous. |
| 31 | 16+ / medium / gamebook | the-red-meridian-run | gauntlet | 1 | 300-340 (dagger: LOW end) | 29 | many fails | A blockade run across a contested strait; one route, brutal checkpoints, lethal restarts. |
| 32 | 16+ / medium / gamebook | the-cinder-bazaar | branch_and_bottleneck | 2 | 420-475 (dagger: CEILING CHALLENGER) | 29 | many fails | Survive and trade through a burning market city; inventory state opens routes. Upper-envelope ceiling test. |
| 33 | 16+ / long / prose | the-tricameral-city | sorting_hat | 1 | 240-300 | 23 | 36-48 | A city ruled by three chambers; an auditor's year inside one chamber, with the other two as rivals and mirrors. |
| 34 | 16+ / long / prose | the-longwinter-station | open_map | 2 | 240-300 | 23 | 36-48 | Overwinter crew at a polar station finds a signal under the ice; heat, fuel, and crew-trust state gate the station map. |
| 35 | 16+ / long / gamebook | the-pale-road | gauntlet | 1 | 475-520 (dagger: LOW end) | 37 | many fails | A pilgrimage across a salt desert that unmakes the unprepared; canonical long gauntlet at the envelope floor. |
| 36 | 16+ / long / gamebook | the-tenfold-siege | gauntlet | 2 | 600-680 (dagger: CEILING CHALLENGER) | 37 | many fails | Hold a fortress through ten escalating assaults; supplies and morale state. Deliberately far above the ceiling to stress-test it. |

Ending-count targets follow the ADR-011 master table for the cell; gamebook cells
are "few wins + many fails" with ~25-35% of nodes as terminals. Every brief also
carries the constants: decisions per path ~4-8, choices per decision 2-3, ~2-3 setup
nodes before the first choice, and the band's fail-state policy.
