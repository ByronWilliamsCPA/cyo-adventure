# D4 proposal: the retained shell set

Status: proposal for owner decision D4 of `story-plan-implementation-plan.md`. Read-only analysis dated 2026-11-21.
Consumed by WP-2.2 (retained shapes and typed directive format). Nothing in the catalog was changed to produce it.

> **Decided 2026-11-21 (owner, in session).** Tier 1 as recommended (twelve shells, six short and medium cells);
> trees count as a retained shape; the consequence-tool freeze stays and state comes from plan threads; family-test
> shells may be converted, shell files only. Recorded as D4 in
> [story-plan-implementation-plan.md](./story-plan-implementation-plan.md).

## 1. What this recommends

1. The plan's wording cannot be met literally: the family bands have **10 offered cells**, so "two shapes per offered
   cell" needs **20** shells, and the plan caps the set at 12. The owner has to choose which constraint gives.
2. Recommended (Tier 1): **12 shells** that give two shapes in each of the **six short and medium cells** (8-11 short
   and medium, 10-13 short and medium, 13-16 medium prose and medium gamebook).
3. Optional (Tier 2): **+8 shells** for the four long cells, if the owner lifts the cap to 20.
4. Every cell has at least four production-eligible shells and at least three distinct shapes (section 7), so no cell
   loses eligibility in either tier; unconverted shells stay v1 and byte-identical, as WP-2.2 requires.
5. Honest limit: **no cell reaches two stateful, contract-clean shapes**; stateful shells carry native literals and
   contracted shells are stateless (sections 3 and 7).

## 2. Method and definitions

- **Offered cell.** `validator/band_profile.py::offered_cells()` (ADR-011) lists 18
  `(age_band, length, narrative_style)` cells; the family bands hold 10: 8-11 short, medium and long, 10-13 short,
  medium and long (all prose), and 13-16 medium and long in both prose and gamebook. Selection
  (`generation/skeleton_match.py`,
  `candidates_for_cell`) matches on band and length for every band below 13-16 and adds style at 13-16 and 16+. A
  shell lives in exactly one cell.
- **Strict agency.** `scripts/check_skeleton.py <shell> --strict-agency` was run on all 46 shells in the three bands
  (`tmp_cleanup/d4/checks.txt`). The rule fails only a production-eligible 8-11+ shell that has a merge node and
  **zero** declared variables and is not on `scripts/stateless_shell_grandfather.txt`. So "pass" has three kinds, kept
  apart below: **real** (declares variables), **exempt** (a pure tree with no merge node) and **grandfathered**
  (stateless with merges, passes only through the list). The rule counts variables above zero; ADR-011 section 12 asks
  for 2 (short) or
  3 (medium and long), at most 4, and that stricter reading is flagged where it matters.
- **Distinctness.** `diversity/structure.py::structural_distance` (0 identical, 1 maximal). The committed in-cell floor
  `tau_cell` is 0.05; every proposed pair is at least 0.33.
- **Native literals.** Counted by script (`tmp_cleanup/d4/lit.py`, `lit2.py`): named people and places in FILL beats,
  choice labels and variable descriptions that are not `{PLACEHOLDER}` tokens. It is a heuristic (it misses lower-case
  story nouns), so treat the node counts as a floor. Contracted shells carry hundreds of `{SLOT}` tokens instead.
- **Used for a book.** A filled edition exists at `out/<slug>.filled.json`, or the book is on the D3 family-test list.
  Whether the edition is published in the database was not checked (no database access in this analysis).
- **Lineage.** The ten family-band shells with a `.lineage.json` are all `origin: fresh`, `hand-authored:v1`, no parent
  and no mutation chain. The other 36 have no sidecar. No shell in the three bands is a mutant of another.

## 3. Tier 1: the retained set (12 shells, 6 cells)

B&B = branch_and_bottleneck. Columns: N = nodes, E = endings, V = declared variables, M = merge nodes (as
`check_skeleton.py` prints them).
SA = `--strict-agency` kind. Literals = nodes whose beats name a story-specific proper noun, of fill nodes.

| Cell | Shell (path under `skeletons/`) | Topology | N / E | V | M | SA | Literals | Used for a book |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8-11 short | `8-11/the-locked-carousel` | open_map | 71 / 13 | 0 | 12 | grandfathered | 2 of 71 | no |
| 8-11 short | `8-11/the-cave-of-echoes` | time_cave | 65 / 16 | 0 | 0 | exempt (tree) | 0 of 65 | yes, D3 control |
| 8-11 medium | `8-11/the-lantern-keepers-list` | B&B | 132 / 24 | 3 | 106 | real (pilot) | 107 of 132 | no |
| 8-11 medium | `8-11/the-storm-chasers-club` | sorting_hat | 121 / 25 | 0 | 0 | exempt (tree) | 0 of 121 | no |
| 10-13 short | `10-13/the-glass-comet` | B&B | 105 / 20 | 3 | 24 | real | 57 of 105 | no |
| 10-13 short | `10-13/the-cinderwick-exchange` | sorting_hat | 99 / 20 | 0 | 0 | exempt (tree) | 11 of 99 | no |
| 10-13 medium | `10-13/the-orchard-signal` | B&B | 179 / 30 | 3 | 129 | real (pilot) | 60 of 179 | no |
| 10-13 medium | `10-13/the-flooded-quarter` | open_map | 155 / 28 | 3 | 49 | real | 86 of 155 | no |
| 13-16 medium prose | `13-16/the-undertow-season` | open_map | 128 / 28 | 2 | 29 | real (see note) | 83 of 128 | no |
| 13-16 medium prose | `13-16/the-conservatory-wars` | sorting_hat | 160 / 26 | 0 | 0 | exempt (tree) | 10 of 160 | no |
| 13-16 medium gamebook | `13-16/the-quarry-signal` | B&B | 267 / 36 | 3 | 217 | real | 91 of 267 | no |
| 13-16 medium gamebook | `13-16/the-iron-spire-trial` | gauntlet | 277 / 79 | 3 | 13 | real | 13 of 277 | no |

Notes on the table:

- Cell labels for 8-11 and 10-13 are band and length only (style is prose and does not partition those bands).
- Only `the-orchard-signal` and `the-quarry-signal` also pass plain `--strict`; the other ten fail it on legacy
  advisories. WP-2.2 requires skeleton posture and `--strict-agency`, not `--strict`.
- Lineage: `the-locked-carousel` and `the-cinderwick-exchange` have `fresh`, hand-authored sidecars; the other ten have
  none. The two pilots (`lantern-keepers-list`, `orchard-signal`) were rewritten in place by the state-promotion tool
  (`f42e93b`).
- `the-undertow-season` declares 2 variables, below ADR-011's 3 for a medium cell; the check passes it (variables above
  zero), but WP-2.2's conversion should add one boolean plant and payoff or record the exception.

### Why each was chosen, and what conversion it needs

"v2" means rewriting every `<<FILL ...>>` directive to `<<FILL v=2 role=... words=... function=...>>` with the beats
removed. That work is the same for all twelve; each entry lists only the extra work.

- `the-locked-carousel` (cost low).
  - Why: Only open_map shape in 8-11 short; contract with 337 slot tokens; near-zero literals.
  - Extra work: Two literals ("Pennies", "Saturdays"); stateless with 12 merges, so strict agency passes only by the
    grandfather list.
- `the-cave-of-echoes` (cost low).
  - Why: Pure time_cave tree (no merges, so no state needed); 244 slot tokens; no literals.
  - Extra work: None beyond v2. It is the unrevised D3 control, so convert the shell only, never
    `out/the-cave-of-echoes.filled.json`.
- `the-lantern-keepers-list` (cost high).
  - Why: The only stateful 8-11 medium shell; 106 merges, 3 variables, 12 conditional choices.
  - Extra work: Heavy: "Beacon Steps" and "Sheepfold" run through 107 of 132 beats, and all 3 variable descriptions are
    native text. No contract, so slots must be defined.
- `the-storm-chasers-club` (cost low).
  - Why: sorting_hat tree gives a different shape from the bottleneck above (distance 0.54); contract, zero literals.
  - Extra work: None beyond v2; exempt from state.
- `the-glass-comet` (cost medium).
  - Why: Stateful (3 variables, 14 conditional choices, 30 effects) with only five distinct names.
  - Extra work: Remove "Vitrea", "Wren", "Halloran", "Hartwell" (57 beats); no contract.
- `the-cinderwick-exchange` (cost low).
  - Why: sorting_hat tree, distance 0.52 from the comet; contract; one literal word.
  - Extra work: Remove "Exchange" (11 beats); exempt from state.
- `the-orchard-signal` (cost medium).
  - Why: Pilot with 3 variables, 129 merges; passes plain `--strict` too.
  - Extra work: Remove "Ada", "Faulks", "Bramley", "Cassar", "October" (60 beats) and 2 native variable descriptions; no
    contract.
- `the-flooded-quarter` (cost medium).
  - Why: Second stateful 10-13 medium shape; open_map against the pilot's bottleneck (distance 0.33).
  - Extra work: Remove "Joss", "Brice", "Fen", "Salma" (86 beats); no contract.
- `the-undertow-season` (cost medium).
  - Why: The only stateful 13-16 medium prose shell.
  - Extra work: Remove "Cass", "Dane", "Graywater", "Pruitt" (83 beats); third variable (see note).
- `the-conservatory-wars` (cost low).
  - Why: sorting_hat tree, distance 0.56 from undertow; contract with 621 slots.
  - Extra work: Month names in 10 beats are calendar structure; decide whether they are literals. Exempt from state.
- `the-quarry-signal` (cost low).
  - Why: Stateful, 3 variables, 217 merges, passes `--strict`; the literal is one name.
  - Extra work: Remove "Dell" (94 beats); no contract.
- `the-iron-spire-trial` (cost low).
  - Why: gauntlet against the quarry's bottleneck (distance 0.52); stateful, 3 variables.
  - Extra work: Remove "Spire" and "Iron" (13 beats); no contract.

### Ranked alternates per cell

- **8-11 short**: 1. `the-robot-fair-sabotage`; 2. `the-half-hour-call`.
  - Robot fair has a contract, grandfathered, B&B (0.36 from the cave). Half-hour call is native-named ("Bea",
    "Adeyinka") and only 0.19 from robot fair.
- **8-11 medium**: 1. `the-river-of-small-boats`; 2. `the-sky-ship-stowaway`.
  - River is a contracted time_cave tree (0.39 from storm chasers). Sky ship is a D3 revised book with a filled edition,
    but is stateless with 20 merges.
- **10-13 short**: 1. `the-midnight-frequency`; 2. `the-midnight-museum`.
  - Frequency is open_map, contracted, grandfathered (0.36 from cinderwick). Museum is a D3 revised book, B&B, 0.30 from
    the comet.
- **10-13 medium**: 1. `the-hollow-lighthouse`; 2. `the-envoy-of-three-courts`.
  - Lighthouse has a filled edition and three known blockers (AL-790), stateless. Envoy is a contracted sorting_hat tree
    (0.55 from the orchard).
- **13-16 medium prose**: 1. `the-signal-in-the-static`; 2. `the-glasswright-debt`.
  - Signal is a D3 revised book, contracted, stateless, 6 merges (0.55 from undertow). Glasswright is native-named, 124
    merges, stateless.
- **13-16 medium gamebook**: 1. `the-smugglers-cut`; 2. `the-saltmarsh-run`.
  - Smugglers cut is contracted, B&B, stateless (0.43 from quarry); note `the-sunspire-ascent` is its near-twin at 0.08.
    Saltmarsh run is a native-named gauntlet, stateless.

Alternates that are stateless need a state pass added by hand if they are promoted, because the state-promotion tool is
frozen (section 6).

## 4. Tier 2: the four long cells (8 more shells, only if the cap is lifted to 20)

- **8-11 long**: `8-11/the-hundred-door-hotel` (open_map, 181 / 31, V=4, M=52, pilot), with
  `8-11/the-guild-of-junior-inventors` (sorting_hat tree, 191 / 34, contract) (distance 0.56).
  - Alternates: `the-clockwork-menagerie` (contracted, 12 merges, filled edition), `the-tin-whistle-map` (native, 171
    merges).
  - Hotel has a contract and light literals (18 of 181 beats): the cheapest pilot to convert.
- **10-13 long**: `10-13/the-cartographers-apprentice` (B&B, 262 / 43, V=4, M=198, pilot), with
  `10-13/the-winter-of-the-wolf-queen` (open_map, 250 / 40, V=3) (distance 0.38).
  - Alternates: `the-mapmakers-island` (D3 control, contracted, 225 / 72, stateless, 0.27 and 0.44),
    `the-skyrail-heist`.
  - Wolf queen has 165 of 250 beats naming "Maren", "Rill", "Bracken"; the pilot fails plain `--strict`.
- **13-16 long prose**: `13-16/the-migration-year` (B&B, 185 / 30, V=4, M=170, pilot), with `13-16/the-hollow-sea`
  (open_map, 197 / 40, V=3) (distance 0.40).
  - Alternates: `the-vanishing-orchard` (D3 control, contracted, stateless; 0.37 and 0.58), `the-year-of-four-banners`.
  - Migration year names "Mamgu" and "Bea" in 183 of 185 beats: the costliest literal removal in the catalog.
- **13-16 long gamebook**: `13-16/the-hollow-crown-gambit` (B&B, 443 / 58, V=4, M=200, pilot), with
  `13-16/the-serpent-vaults` (gauntlet, 530 / 172, V=3, contract-less, 0.50) (distance 0.50).
  - Alternates: `the-thornwood-trial` (contracted, stateless; 0.41 and 0.55), `the-labyrinth-of-glass`.
  - Choose one of `harrowstone-keep` and `sunken-temple`, never both: they are the same shape (distance 0.000, same
    series). Crown gambit has 129 of 443 beats naming "Crown", "Chamber", "Assize".

Long shells have 170 to 550 nodes each, so conversion and any later scene-by-scene fill cost the most there. That is why
Tier 1 stops at medium.

## 5. Candidate census (all 46 shells in the three bands)

`SA`: R real, E exempt tree, G grandfathered, X fails (ineligible). Eligible = `production_eligible` in metadata.
"Filled" marks a shell with `out/<slug>.filled.json`; "D3" marks the seven family-test books.

| Shell | Cell | N / E | V | M | SA | Filled or D3 |
| --- | --- | --- | --- | --- | --- | --- |
| `8-11/the-cave-of-echoes` | 8-11 short | 65 / 16 | 0 | 0 | E | filled, D3 control |
| `8-11/the-half-hour-call` | 8-11 short | 61 / 14 | 0 | 37 | G | no |
| `8-11/the-locked-carousel` | 8-11 short | 71 / 13 | 0 | 12 | G | no |
| `8-11/the-robot-fair-sabotage` | 8-11 short | 74 / 14 | 0 | 6 | G | no |
| `8-11/the-lantern-keepers-list` | 8-11 medium | 132 / 24 | 3 | 106 | R | no |
| `8-11/the-river-of-small-boats` | 8-11 medium | 127 / 26 | 0 | 0 | E | no |
| `8-11/the-sky-ship-stowaway` | 8-11 medium | 112 / 20 | 0 | 20 | G | filled, D3 revised |
| `8-11/the-storm-chasers-club` | 8-11 medium | 121 / 25 | 0 | 0 | E | no |
| `8-11/the-clockwork-menagerie` | 8-11 long | 167 / 27 | 0 | 12 | G | filled |
| `8-11/the-guild-of-junior-inventors` | 8-11 long | 191 / 34 | 0 | 0 | E | no |
| `8-11/the-hundred-door-hotel` | 8-11 long | 181 / 31 | 4 | 52 | R | no |
| `8-11/the-tin-whistle-map` | 8-11 long | 193 / 35 | 0 | 171 | G | no |
| `10-13/the-blackout-week` | 10-13 short | 91 / 19 | 0 | 70 | G | no |
| `10-13/the-cinderwick-exchange` | 10-13 short | 99 / 20 | 0 | 0 | E | no |
| `10-13/the-glass-comet` | 10-13 short | 105 / 20 | 3 | 24 | R | no |
| `10-13/the-midnight-frequency` | 10-13 short | 101 / 18 | 0 | 19 | G | no |
| `10-13/the-midnight-museum` | 10-13 short | 95 / 19 | 0 | 8 | G | filled, D3 revised |
| `10-13/the-envoy-of-three-courts` | 10-13 medium | 159 / 30 | 0 | 0 | E | no |
| `10-13/the-flooded-quarter` | 10-13 medium | 155 / 28 | 3 | 49 | R | no |
| `10-13/the-hollow-lighthouse` | 10-13 medium | 149 / 31 | 0 | 17 | G | filled, D3 revised |
| `10-13/the-observatory-shift` | 10-13 medium | 145 / 27 | 0 | 0 | E | no |
| `10-13/the-orchard-signal` | 10-13 medium | 179 / 30 | 3 | 129 | R | no |
| `10-13/the-cartographers-apprentice` | 10-13 long | 262 / 43 | 4 | 198 | R | no |
| `10-13/the-mapmakers-island` | 10-13 long | 225 / 72 | 0 | 33 | G | filled, D3 control |
| `10-13/the-skyrail-heist` | 10-13 long | 246 / 40 | 0 | 0 | E | no |
| `10-13/the-winter-of-the-wolf-queen` | 10-13 long | 250 / 40 | 3 | 46 | R | no |
| `10-13/the-clocktower-cipher` | none (no length, ineligible) | 26 / 8 | 0 | 3 | X | filled |
| `13-16/the-conservatory-wars` | 13-16 medium prose | 160 / 26 | 0 | 0 | E | no |
| `13-16/the-glasswright-debt` | 13-16 medium prose | 130 / 23 | 0 | 124 | G | no |
| `13-16/the-signal-in-the-static` | 13-16 medium prose | 124 / 32 | 0 | 6 | G | filled, D3 revised |
| `13-16/the-undertow-season` | 13-16 medium prose | 128 / 28 | 2 | 29 | R | no |
| `13-16/the-hollow-sea` | 13-16 long prose | 197 / 40 | 3 | 36 | R | no |
| `13-16/the-migration-year` | 13-16 long prose | 185 / 30 | 4 | 170 | R | no |
| `13-16/the-vanishing-orchard` | 13-16 long prose | 178 / 33 | 0 | 9 | G | filled, D3 control |
| `13-16/the-year-of-four-banners` | 13-16 long prose | 212 / 33 | 0 | 0 | E | no |
| `13-16/the-iron-spire-trial` | 13-16 medium gamebook | 277 / 79 | 3 | 13 | R | no |
| `13-16/the-quarry-signal` | 13-16 medium gamebook | 267 / 36 | 3 | 217 | R | no |
| `13-16/the-saltmarsh-run` | 13-16 medium gamebook | 322 / 42 | 0 | 152 | G | no |
| `13-16/the-smugglers-cut` | 13-16 medium gamebook | 277 / 80 | 0 | 10 | G | no |
| `13-16/the-sunspire-ascent` | 13-16 medium gamebook | 253 / 74 | 0 | 11 | G | filled |
| `13-16/the-harrowstone-keep` | 13-16 long gamebook | 551 / 152 | 4 | 66 | R | filled |
| `13-16/the-hollow-crown-gambit` | 13-16 long gamebook | 443 / 58 | 4 | 200 | R | no |
| `13-16/the-labyrinth-of-glass` | 13-16 long gamebook | 383 / 116 | 0 | 19 | G | no |
| `13-16/the-serpent-vaults` | 13-16 long gamebook | 530 / 172 | 3 | 29 | R | no |
| `13-16/the-sunken-temple` | 13-16 long gamebook | 551 / 152 | 4 | 66 | R | filled |
| `13-16/the-thornwood-trial` | 13-16 long gamebook | 376 / 115 | 0 | 19 | G | filled |

The six promoted pilots are `the-hundred-door-hotel`, `the-lantern-keepers-list`, `the-cartographers-apprentice`,
`the-orchard-signal`, `the-hollow-crown-gambit` and `the-migration-year`. None has a filled edition. Only the hotel
has a contract; the other five have none, and all six name story-specific people and places in their directives (the
review's A.5 item 6 finding, confirmed here).

## 6. Risks and consequences of choosing this set

1. **Stateless picks conflict with the freeze.** `the-locked-carousel` (and any alternate marked G) passes strict
   agency only because it is grandfathered. Making it stateful needs `scripts/add_consequence.py`, which WP-0.1 action 1
   forbids, or hand-authored state inside WP-2.2. D4 should say which. The tree picks (E) avoid the question.
2. **Converting changes a shell's hash, not its edition.** Edited-in-place shells (`the-cave-of-echoes`) must not
   touch the filled controls in `out/`, or the D3 revised-versus-control comparison is spoiled.
3. **Contracts.** The stateful picks have no `.contract.json`. WP-2.2's literal removal should be paired with a
   contract, or the shells stay unusable for reskinned requests (the very reason the pilots are frozen).
4. **Near-twins.** `harrowstone-keep` and `sunken-temple` (0.000), `smugglers-cut` and `sunspire-ascent` (0.078),
   `the-half-hour-call` and `robot-fair-sabotage` (0.19) and `the-envoy-of-three-courts` and `the-observatory-shift`
   (0.17) must never be retained as a pair.
5. **Tier 1 leaves long cells unconverted.** They stay v1 and eligible, so plan-first requests at long length would
   fall back to skeleton fill until Tier 2 is done.

## 7. Cells that cannot reach two shapes

Counting what the catalog has today. Every cell has at least two production-eligible shells with distinct shapes, so the
shortfalls are all about the preferred quality (stateful, contract-clean), not about shape count.

| Cell | Eligible shells | Stateful | Can reach two stateful shapes now? | What the second shape would be |
| --- | --- | --- | --- | --- |
| 8-11 short | 4 | 0 | No (zero) | Both picks stateless: a tree plus a grandfathered open_map. |
| 8-11 medium | 4 | 1 | No | Lantern (stateful) plus a tree. |
| 8-11 long | 4 | 1 | No | Hotel (stateful) plus a tree. |
| 10-13 short | 5 | 1 | No | Glass comet plus a tree. |
| 10-13 medium | 5 | 2 | Yes | Orchard signal and flooded quarter. |
| 10-13 long | 4 | 2 | Yes | Cartographers and wolf queen. |
| 13-16 medium prose | 4 | 1 | No | Undertow (2 variables, one short of ADR-011) plus a tree. |
| 13-16 long prose | 4 | 2 | Yes | Migration year and hollow sea. |
| 13-16 medium gamebook | 5 | 2 | Yes | Quarry signal and iron spire trial. |
| 13-16 long gamebook | 6 (5 shapes) | 4 (3 shapes) | Yes | Crown gambit and serpent vaults. |

Where "stateful" is satisfied, the stateful shells carry native literals and have no contract, so none of the ten cells
can reach two shapes that are both stateful **and** already free of native literals. The closest are the quarry signal
(one name) and the iron spire trial (two words), both in 13-16 medium gamebook.

## 8. Decisions needed from the owner

1. Tier 1 only (12 shells, six cells), or Tier 2 as well (20 shells, ten cells), or a cap between the two.
2. For the five cells with a tree as the second shape: accept a pure tree (no state, exempt) as a retained shape, or
   require two stateful shapes and accept that those cells will not reach the bar until a state pass is written.
3. Whether WP-2.2 may hand-author state, or lift the `add_consequence.py` freeze, for any stateless pick.
4. Whether the two D3 controls and four revised books may have their shells converted (shell only, editions untouched).
