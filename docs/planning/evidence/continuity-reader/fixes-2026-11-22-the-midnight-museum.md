# Residual continuity fix: The Midnight Museum (2026-11-22)

Fix for the one real residual recorded for `out/the-midnight-museum.filled.json` in
[residuals-2026-11-21.md](./residuals-2026-11-21.md) (section "The Midnight Museum"). Owner-approved 2026-11-22; the
edit pause is lifted for this revised family-test book. MM-1, MM-2 and MM-3 were judged not defects there and are
unchanged. The earlier WP-0.4 fixes in
[findings-the-midnight-museum.md](../story-plan-retro/findings-the-midnight-museum.md) were read first and none is
touched; this fix uses the same introducing clause as `k_founder_desk` and `k_founder_portrait` ("where a small
reading table stood by the window"), in the style of F16.

## Fix

| Id | Node | Before quote | After quote | How verified |
| --- | --- | --- | --- | --- |
| MM-4 | `k_stairs_base` | "at the top." | "at the top, where a small reading table stood by the window." | E, W |

How verified: E is the witness replayed with `StoryEngine`; W is the exhaustive route walk (both below). The quotes
are the end of the passage's last sentence, which reads in full: "She pushed the glasses up into her hair, tucked the
chart under her arm, and climbed to the landing at the top, where a small reading table stood by the window."

The witness from the residuals file, `MM-key > c_key_stairs > c_stairs_base > c_base_study`, replays as
`c_open > c_desk_map > c_desk_map_go > c_start_gems > c_gems_case > c_gems_vitrine > c_vitrine_go > c_corridor_key >
c_key_stairs > c_stairs_base > c_base_study` (11 choices) and lands on `k_study`. Before the fix no node on that route
introduced a reading table before the label `c_base_study` ("Carry the chart to the reading table.") and `k_study`
("The lamp on the reading table had a brass chain."). After the fix `k_stairs_base` introduces it, so the label, the
`k_study` passage and `e_win_hero_curator` ("at the reading table upstairs") are true on that route.

Every inbound edge to `k_study` now introduces the table in its source passage: `k_founder_desk`,
`k_founder_portrait`, `k_cabinet`, `k_stairs_up` and, after this fix, `k_stairs_base`. `k_display_careful`, which
skips `k_study`, introduces it too.

## Route walk

All 37,704 complete routes were played with `StoryEngine` (`start`, `visible_choices`, `choose`), recording whether
a passage introducing the reading table was visited before each node that leans on it.

| Node | Route visits | Without the table first, before | Without the table first, after |
| --- | ---: | ---: | ---: |
| `k_study` | 100 | 20 | 0 |
| `e_win_hero_curator` | 3,240 | 540 | 0 |

## Plan

`out/the-midnight-museum.plan.json` was brought into line:

- New fact `landing_reading_table`: "A small reading table stands by the window on the landing outside the founder's
  study."
- Established by `k_founder_desk`, `k_founder_portrait`, `k_cabinet`, `k_stairs_up`, `k_stairs_base` and
  `k_display_careful`, each of which states it; required by `k_study` and `e_win_hero_curator`.
- `k_stairs_base` event extended with "She climbs to the landing and its reading table."
- `provenance.book_sha256` set to the new hash; `provenance.notes` gains "residual fixes 2026-11-22: MM-4".

## Checks

| Check | Result |
| --- | --- |
| Shape hash | unchanged: `sha256:26d8c8e8827e22695be39d03b0e5045720f1e223479d28d9c061a84abd2f1660` |
| Book sha256 | `e466cce6...2917b0234` before, `af54082e...0fbe594f1` after |
| Structure (bodies and labels stripped, HEAD against fixed) | identical |
| `run_story_gate.py` | exit 0; findings 0, blocked False, safety_flagged False |
| `run_fill_gate(...).blocked` | False |
| `check_story_plan.py` | 0 errors, 2 warnings (SP-8 symmetric cost at `n_start` and `n_cipher`, both pre-existing) |
| `check_fill_integrity.py` | markers, words, fill-rate pass; structure FAIL, known and pre-existing |
| `check_prose_craft.py` | exit 0; only change is the narration word count (9,872 to 9,881) |
| Em-dash (U+2014) in book | 0 |
