# Continuity findings: the-cave-of-echoes (control book, WP-0.4)

Read date: 2026-11-21. The book declares no variables, so every node has exactly one state; the 65 nodes form a tree
(no merge nodes) with 16 endings, and every route was read in full. Control rule: only plain contradictions and
unestablished facts are fixed. Agency problems are recorded and left open by design: five of 14 decisions restate or
announce their options (`ra_lake_app`, `ra_pool_app`, `da_fork`, `da_cache_app`, `da_cache_room`), there are no
variables and no merge nodes, and `ra_row` / `la_bell4` etc. are each reachable by exactly one route. Craft headline
before and after the fixes is identical: `agency: no merge nodes (every route stays separate); 0 variables, so no
choice comes back; 5 of 14 decisions restate or announce their options; 0 of 0 setback endings have the hero give up,
0 come within 3 decisions.`

## Fixed (pre-fix finding, fix applied)

| # | Sev | Node | Route | Quoted sentence | Why wrong | Fix |
|---|-----|------|-------|-----------------|-----------|-----|
| 1 | high | `ra_lake2` | c_right > c_right fork > c_lake > c_ra_pebbles | "The lapping sound, it turns out, is only Biscuit's paw." | `ra_fork` / `ra_lake_way` have the sound growing louder from ahead before Biscuit is near the water | The lapping is the black lake nudging the shelf; Biscuit just tests the cold edge |
| 2 | high | `da_compass` / `da_compass2` | c_down > c_cache > c_compass > c_da_out | "pointing her the quickest way back to the cave mouth" vs "still finding true north" | A needle cannot do both; the way out is not established to lie north | Biscuit knows the way out; the needle just swings true; `da_compass2` has Biscuit lead them out |
| 3 | high | `da_cache_back` | c_down > c_cache > c_cacheback | "marks the spot carefully on her map ... folds her map away" | No map exists on any route | Maya marks the spot in her memory (ending title left, it now reads as a mental map) |
| 4 | med | `da_roost` vs `da_skylight` | c_down > c_bat > c_batenter > ... > c_da_push | carved initials show "someone climbed this very chimney" vs "a whole secret way ... nobody else ever knew" | Same route contradicts itself | "a whole forgotten way ... bats nobody in years seems to have noticed" |
| 5 | med | `la_bell3`, `la_bell4` | c_left > c_hum > ... > c_la_bell4 | "lit against the dark"; "climb the good rope back up ... hand over hand" | Nothing lights the lantern (stub of candle, no flame); the way back up is the ladder that held, and a dog cannot go hand over hand | Lantern swings from her wrist; they climb the rope ladder with the rope over her shoulder; `la_bell3` says the rope is "too good to leave behind" instead of a climbing aid |
| 6 | med | `la_song`, `da_bat_back` | c_left > ... > la_song; c_down > c_bat > c_batback | "the old lighthouse keeper"; "the lighthouse ranger" | A person named as known; the aunt is the keeper and no ranger exists | "the lighthouse keepers of long ago"; "ask her aunt" |
| 7 | med | `ra_starfish` vs `ra_starfish2` | c_right > ... > c_star | "Maya snaps a photo" vs "will not believe her story ... until they see the sketch" | A camera appears from nowhere and the ending says no photo exists | Photo sentence replaced by looking over the pool one last time |
| 8 | low | `ra_islet` | c_right > ... > c_wade | "fills a small jar" | A jar from nowhere | "tucks a few pale shells into her pocket" |
| 9 | low | `la_bell3`, `ra_starfish` | notebook routes | "her notebook" | Never established before first use | `n_start` has Maya check her notebook is in her pocket |
| 10 | low | `la_crystal_take` | c_left > c_glitter > ... > c_take | "curves back the way she came, toward the old lighthouse stairs" | Back the way she came leads to the beach, not stairs; "old lighthouse stairs" is unintroduced | "curves upward, toward the lighthouse above the cove" |

## Left alone (soft or taste, recorded)

- Home: "everyone back home" (`la_crystal_out`), "rockpool club back home" (`ra_starfish2`) versus "near her home"
  (`la_bell4`). No single route carries both; each is consistent on its own route.
- The paper-like rustle in `la_tunnel` is never explained (unpaid setup, craft not continuity).
- `la_bell` / `la_bell4`: Biscuit on a rope ladder, taste.
- `ra_row`: "the first people in a lifetime" with an old rowboat present, hedged by "in a lifetime".
- `la_hum` "not wind at all" has the earlier wind simile only on the shared `la_tunnel` rustle; fine.
- Time of day: "evening" exits versus "daylight" exits sit on different routes.

## Pre-existing, not touched

`check_fill_integrity.py` reports `FAIL structure` against `skeletons/8-11/the-cave-of-echoes.json` both before and
after: the filled metadata lacks `narrative_person` and a few other skeleton keys. This predates the pass and is not
changed (the brief forbids structural edits).

## Result

Zero open plain contradictions after a second full read. Gate exits 0, `run_fill_gate(...).blocked` is False.
