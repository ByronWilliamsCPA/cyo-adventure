<!-- markdownlint-disable MD038 -- witness routes are code spans wrapped across lines -->

# Residual continuity fixes: the-cave-of-echoes (control book, 2026-11-22)

Owner-approved pass over the real items in the Cave of Echoes section of
[residuals-2026-11-21.md](./residuals-2026-11-21.md). This is a control book in the family test (decision D3), so
only continuity defects are fixed and agency problems are left as they are. CE-3 ("the whole town") is not a defect
and is unchanged. The earlier WP-0.4 fixes in
[findings-the-cave-of-echoes.md](../story-plan-retro/findings-the-cave-of-echoes.md) were re-read first; none is
undone (`da_compass` and `da_compass2` keep Biscuit leading the way out, which is what CE-4's label now says).

- Book: `out/the-cave-of-echoes.filled.json`.
  - sha256 before: `3a3606f4a0bee7fa42c399b18847d62260b3efd074cf69328087c53f13928273`.
  - sha256 after: `a4a7c090391572dc58e3c31166f53fbe51a03aba18fa4a086a26b6f833fbc7fe`.
- Shape hash unchanged: `sha256:70c334341d9e40bc1b272bcb9254c354308a798799ecafe3c75e0564f017a628`.
- Edits are sentence-level: three body sentences and one choice label. No node, choice, target, condition, effect,
  variable or ending field changed. A load-and-dump round trip was byte-identical before editing.

## Fixes

| Id | Node | Before | After | How verified |
| --- | --- | --- | --- | --- |
| CE-1 | `da_skylight` | "imagines how the museum will react." | "imagines how a museum will react." | W1, `e_bats` |
| CE-1 | `da_coins2` | "picturing the museum polishing" | "picturing a museum polishing" | W2, `e_coins` |
| CE-2 | `ra_starfish2` | "She knows the rockpool club back home" | "She knows her rockpool club back home" | W3 |
| CE-4 | `c_da_out` label | "Follow the compass out." | "Follow Biscuit out." | W4, `e_compass` |

Full sentences after the fix: `da_skylight` "She already imagines how a museum will react."; `da_coins2` "She is already
picturing a museum polishing every coin and printing her name on a little card"; `ra_starfish2` "She knows her
rockpool club back home will not believe her story." The label sits on node `da_compass`. W1 to W4 are the witness
replays below; W3 lands on `e_starfish`.

Why each fix is the smallest true one:

- CE-1: the indefinite article introduces a museum instead of presuming the reader already knows one. "A museum"
  occurs only on these two endings, and no route reads both.
- CE-2: the possessive makes the sentence introduce the club as Maya's own, which is all the passage needs.
- CE-4: both bodies on the route already have Biscuit lead (`da_compass` "Biscuit trots ahead, sure of the way";
  `da_compass2` "Biscuit leads Maya straight out to the cave mouth"), so the label now promises what happens.

## Witness replays

Each witness was replayed from `n_open` with `StoryEngine` (`start`, `visible_choices`, `choose`). Every choice was
visible at its step, and each route lands on the named ending with the fixed sentence on the path.

Witness routes (choice ids from `n_open`, 10 choices each):

- W1: `c_open > c_down > c_da_fork > c_bat > c_da_creep > c_da_grey > c_batenter > c_da_stair > c_da_climb >
  c_da_push`. Lands on `da_skylight` (`e_bats`). The only "museum" on the path is "a museum".
- W2: `c_open > c_down > c_da_fork > c_cache > c_da_door > c_da_peer > c_cacheenter > c_da_boxes > c_coins >
  c_da_carry`. Lands on `da_coins2` (`e_coins`). The only "museum" on the path is "a museum".
- W3: `c_open > c_right > c_ra_fork > c_pool > c_ra_crouch > c_ra_channel > c_enter > c_ra_kneel > c_star >
  c_ra_sketch`. Lands on `ra_starfish2` (`e_starfish`). The club appears once, as "her rockpool club back home".
- W4: `c_open > c_down > c_da_fork > c_cache > c_da_door > c_da_peer > c_cacheenter > c_da_boxes > c_compass >
  c_da_out`. Lands on `da_compass2` (`e_compass`). The final label offered is "Follow Biscuit out."; no label or
  body on the path says the compass shows the way.

## Plan updates

`out/the-cave-of-echoes.plan.json` now binds the new book hash and carries the note
"residual fixes 2026-11-22: CE-1, CE-2, CE-4 (...)".

- Facts: `museum` and `rockpool_club` texts say how each is introduced; `home_elsewhere` quotes "her rockpool club
  back home"; `compass_out` now reads "Biscuit led Maya out ... with the compass in her hand".
- Fact `compass_points_way_out` is renamed `biscuit_knows_way_out` (same text), in `facts`, in `da_compass`
  `establishes` and in `da_compass2` `requires`. The old id asserted the claim WP-0.4 fix 2 removed. No other file
  references it.
- Node events for `ra_starfish2`, `da_skylight` and `da_coins2` match the new sentences. Their `requires` and
  `establishes` lists are unchanged: each still establishes the fact it introduces.
- Choices: `c_da_out` intent "follow Biscuit out"; `c_compass` intent "take the light brass compass" (it said the
  compass "can guide them", the same removed claim). Ending gift for `da_coins2` reads "for a museum".

## Acceptance

| Check | Before | After |
| --- | --- | --- |
| `run_story_gate.py` | exit 0, `findings=17 blocked=False` | exit 0, identical output |
| `run_fill_gate(...).blocked` | False | False |
| `check_story_plan.py` | 0 errors, 1 warning (SP-3) | 0 errors, 1 warning (SP-3) |
| `check_fill_integrity.py` | markers, words, fill-rate ok | markers, words, fill-rate ok |
| `check_fill_integrity.py` structure | FAIL (pre-existing) | FAIL (pre-existing) |
| Shape hash | `70c33434...` | `70c33434...` |
| `check_prose_craft.py` | exit 0 | exit 0, output byte-identical |

The one plan warning, both before and after, is the recorded soft cross-route item: SP-3 at `la_crystal_out` for
`home_elsewhere` (at `la_crystal_out`, `ra_starfish2`) against `home_near_cove` (at `la_bell4`), on routes no single
reading crosses.

The structure failure predates this pass: the filled metadata lacks `narrative_person` and other skeleton keys, as
the WP-0.4 findings record.

Agency headline, identical before and after (control rule):

```text
agency: no merge nodes (every route stays separate); 0 variables, so no choice comes back; 5 of 14 decisions
restate or announce their options; 0 of 0 setback endings have the hero give up, 0 come within 3 decisions.
```

## Left as found

- CE-3 ("the whole town" in `la_bell4` and `da_compass2`): not a defect, per the residual check.
- Plan residue outside this pass: the `da_cache_back` ending gift still says "marked on the map", though WP-0.4 fix 3
  removed the map from the book, and several older `provenance.notes` entries describe pre-fix text. Neither is
  read by any gate; both are plan wording only.
