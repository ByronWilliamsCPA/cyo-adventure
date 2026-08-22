# Sourcing-programme shared materials (S-0)

Fixed 2026-08-21, before any S-row arm has generated anything, per the
[skeleton sourcing test plan](../../skeleton-sourcing-test-plan-2026-08-21.md) section 5 E0 and
register row `S-0`. Everything in this file is frozen: an experiment that wants different premises
or briefs registers the change in the S-row before running, or it is not the registered experiment.

## E1 cells

Three cheap-band cells plus one hard-band cell, all prose (gamebook and 3-5 are out of the plan's
scope), all in `offered_cells()`:

| Cell id | Band | Length | Style |
| --- | --- | --- | --- |
| A | 5-8 | short | prose |
| B | 8-11 | short | prose |
| C | 8-11 | medium | prose |
| D | 10-13 | short | prose |

Usage note (2026-08-22): the executed S-1 runs used cells A and D at 3 replicates each (plan
section 10 descope). Cells B and C, and every cell's replicate-4 premise, stay frozen here unused;
a later experiment that wants them registers that use in its S-row first.

Briefs come from `scripts/generate_drafting_brief.py <band> <length> prose` at run time, never
hand-copied (AL-149).

## Curated premise list

Sixteen premises, four per cell, one per replicate. Design rules, applied at authoring time:

- No premise uses a light, lamp, signal, beacon, or transmission motif (the Q-3c convergence mode).
- No premise family (animal care, craft, community event, journey, mystery object, performance,
  trade, survey) repeats within a cell.
- Premises name a protagonist, a goal, and a setting; they do not name story structure, endings, or
  choice content, which belong to the arm under test.

| ID | Cell | Premise |
| --- | --- | --- |
| PA-1 | A | Miri looks after the school's three hens for the holiday week, and one morning the smallest hen is missing. |
| PA-2 | A | Tomas and his grandmother build a kite for the spring festival, but the wind keeps changing and every new design needs testing. |
| PA-3 | A | On the first snowy day, Priya must find her little brother's boot, lost somewhere along the sled run, before their walk home. |
| PA-4 | A | The class garden's giant pumpkin has a mysterious nibbler, and Sam wants to find out who it is without scaring any animal away. |
| PB-1 | B | The town's old carousel breaks a week before the fete, and Nell, the mechanic's apprentice, thinks she can fix it if she can find the missing part. |
| PB-2 | B | While shelving returns, library volunteer Theo finds a fifty-year-old letter tucked in an atlas, addressed to someone who still lives in town. |
| PB-3 | B | A spring tide strands a rockpool full of creatures far up the beach, and Jonah's tide-watching club has one afternoon to move them safely. |
| PB-4 | B | The school orchestra's tuba goes missing on tour day, and Ada traces the mix-up across the town's three delivery vans. |
| PC-1 | C | The neighbourhood street market loses its permit spot, and Rosa organizes the stallholders to find and win a new one before Saturday. |
| PC-2 | C | An old footpath to the river has been fenced off, and twins Leo and June set out to prove the right of way still exists by walking its forgotten course. |
| PC-3 | C | A storm blows a racing pigeon with a numbered leg-ring into Amir's yard, and he sets out to return it to an owner three villages away. |
| PC-4 | C | Great-aunt Bee's famous chutney recipe is half missing, and the family kitchen becomes a test lab to reconstruct it before the county show. |
| PD-1 | D | A junk-shop chess set turns out to have one piece too many, carved differently from the rest, and Wren traces where the extra piece began. |
| PD-2 | D | Two nights before opening, the school play's lead quits, and stage manager Cass must re-plan the show around who is left. |
| PD-3 | D | At the harvest swap-market, Idris discovers the tokens everyone trades with have two subtly different mintings, and prices are quietly drifting apart. |
| PD-4 | D | The river-gauge readings Dara's science club submits stop matching the town's official numbers, and finding out why means walking the whole river. |

## Allocation rule (counterbalanced, fixed)

For E1: replicate `r` of cell `c` uses premise `P<c>-<r>` for **every** leg, so legs are compared on
identical premises and the premise axis cancels within a replicate. No leg ever invents or edits a
premise; a leg that drifts from its premise is reported as drift, not re-run. For E2: the 4-6
decisional strata draw premises `PD-1`..`PD-4` first, then `PC-1`, `PC-2` if six are needed (E2's
stratum is a 10-13-scale artifact; the two C premises are flagged as off-band and used only if the
count requires them). For E3: premises come from the request briefs below, not from this list.

## E3 request briefs

Six briefs, fixed here before any arm runs, shared verbatim across arms. Shape mirrors the
`story_requests` intake (band, length, interests, requested elements, tone note). Briefs 5 and 6
carry elements the catalog demonstrably cannot serve: `grep -rli` over `skeletons/` for
"submarine" and "circus" returns zero files as of this commit (verified 2026-08-21; re-verify when
running E3, since the catalog grows).

| ID | Cell | Brief |
| --- | --- | --- |
| BR-1 | 5-8 short | For a 6-year-old who loves swimming and maps. Requested: a story about following a hand-drawn map to find a hidden pond, with a friendly animal met along the way. Tone: gentle, no peril beyond getting briefly muddy. |
| BR-2 | 8-11 medium | For a 9-year-old who bakes with their dad and cares intensely about fairness. Requested: a baking-contest story where something unfair happens and gets put right without a villain being humiliated. |
| BR-3 | 10-13 short | For a 12-year-old into ciphers and night trains. Requested: a mystery aboard a sleeper train involving a coded note, solvable by the reader from clues shown on the page. |
| BR-4 | 8-11 medium | For a 10-year-old who just moved towns and misses their old friends. Requested: a story about finding belonging in a new place, where keeping the old friendship also matters. Tone: warm; homesickness may be named but the ending is hopeful. |
| BR-5 | 10-13 short | For a 13-year-old obsessed with deep-sea exploration. Requested: a submarine expedition story with sonar, pressure limits, and a discovery that is wondrous rather than monstrous. **Catalog-unservable element: submarine.** |
| BR-6 | 5-8 short | For a 7-year-old who loves acrobats. Requested: a traveling-circus story with a tightrope act and a first-time performance. **Catalog-unservable element: circus.** |

## Judged-instrument counterbalancing (consumed by S-0's recognition runs and S-2/S-4)

For every rated pair (X, Y): rater 1 reads X as Book One and Y as Book Two; rater 2 reads Y as Book
One and X as Book Two. Raters are independent sessions, see no arm labels, and their model tier is
recorded per verdict, per the frozen protocol's rules.
