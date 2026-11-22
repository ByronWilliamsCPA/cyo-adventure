# Residual continuity fixes: The Sky-Ship Stowaway (2026-11-22)

Owner-approved residual pass over `out/the-sky-ship-stowaway.filled.json`, fixing the items marked real in
[residuals-2026-11-21.md](residuals-2026-11-21.md) (section "The Sky-Ship Stowaway"): SS-1 and SS-2 (minor) and
SS-3 (should-fix). SS-4 (the purser) is not a defect and is unchanged. The WP-0.4 fixes recorded in
[findings-the-sky-ship-stowaway.md](../story-plan-retro/findings-the-sky-ship-stowaway.md) were read first and are
all intact (F2's "twisted strap of his harness" at `e_neu_kite` is untouched).

- Book sha256 before: `73a5c0d5d1976891b1f4e1f773344ac3698ac230e517d3c6b3144cb6da1f1441`.
- Book sha256 after: `3621f39c156ad9fa64360889dd24a63dbdbf0e6030e48b2d3fa5158c71a1a66f`.
- Shape hash, unchanged: `sha256:505dc8a647b7f9437b0fe1113aece4e9fa7c461eea0b0ff626a50fd042216e42`.

Sentence-level body edits in three nodes. No node, choice, label, condition, effect, variable or ending was changed;
the book is identical to its previous version once node bodies are removed.

## Fixes

Each row is one side of one fix; the SS-2 quotes run over two rows. Witnesses A to C are listed below.

| ID | Node | Side | Quote | Verified |
| --- | --- | --- | --- | --- |
| SS-1 | `e_win_discovery` | before | "So THIS is where my forty buckets go," he said | Witness A |
| SS-1 | `e_win_discovery` | after | "Forty buckets of it, every day," he said, | Witness A |
| SS-1 | `e_win_discovery` | (cont.) | "and so THIS is where they go," | Witness A |
| SS-2 | `b_free1` | before | "If he goes, he goes as he is, because I have not been able to get near that | Witness B |
| SS-2 | `b_free1` | (cont.) | harness since the first thunder," the captain added. | Witness B |
| SS-2 | `b_free1` | after | "He wears a leather harness around his middle," the captain added. | Witness B |
| SS-2 | `b_free1` | (cont.) | "If he goes, he goes in it. I have not been able to get near the buckles | Witness B |
| SS-2 | `b_free1` | (cont.) | since the first thunder." | Witness B |
| SS-3 | `f_rig_a` | before | Bree looked up, but she could not tell one seam from another. | Witness C |
| SS-3 | `f_rig_a` | after | Bree looked up, but from this far below, with nothing but her own eyes, | Witness C |
| SS-3 | `f_rig_a` | (cont.) | she could not tell one seam from another. | Witness C |

Why each edit is true on every route:

- **SS-1.** The sentence before is "The cook brought the mash himself", so "it" is the mash and the line states the
  forty buckets instead of recalling them. On the `f_galley1` routes it now echoes the cook's own "Forty buckets of
  fish mash every day".
- **SS-2.** The captain introduces the harness in her own line. On routes through `p_save1` ("A leather harness was
  buckled around his middle") it restates a known fact, and `b_free_ok` ("slipped the last buckle of the harness")
  and `e_neu_kite` still follow from it. The edit also lowers the node's FK grade from 5.45 to 4.39; a first draft
  of one long sentence raised it to 6.11 and drew an advisory RL-13, so it was split.
- **SS-3.** The vantage difference is now on the page: on the crow's-nest route Bree saw the stern seam through a
  spyglass, and here she is far below the riggers with her bare eyes. On routes that never reach the nest the clause
  presupposes nothing ("Far above, two riggers" is in the same passage). A remembered seam was not used because it
  would be false on the routes that skip `c_nest_a`.

## Witness replays

Each witness was replayed with `StoryEngine` from `n_open`; every choice was visible in turn and each route lands on
the node named. `SS-eng` is `c_open > c_start_eng > c_eng_deep > c_eng_a > c_eng_a_go > c_eng_a2_go >
c_eng_conv_go`.

- **A (SS-1).** `SS-eng > c_friend_cabin > c_cabin_a > c_cabin_a_go > c_cabin_mid_go > c_storm_deck > c_deck_a >
  c_deck_a_go > c_deck_mid_go > c_secret_people > c_people_b > c_people_b_go > c_people_mid_go > c_bridge_tell >
  c_tell_reveal > c_tell_reveal_win` (22 choices, all variables false). No earlier node on the route mentions
  buckets; the line now introduces them.
- **B (SS-2).** `SS-eng > c_friend_galley > c_galley_a > c_galley_a_go > c_galley_mid_go > c_storm_deck > c_deck_a
  > c_deck_a_go > c_deck_mid_go > c_secret_pip > c_pip_go > c_save_mid_go > c_bridge_free` (19 choices,
  `fed_pip=true`). No earlier node mentions a harness; the captain now introduces it.
- **C (SS-3).** `c_open > c_start_nest > c_nest_deep > c_nest_a > c_nest_a_go > c_nest_a2_go > c_nest_conv_go >
  c_friend_rig > c_rig_a` (9 choices). The spyglass and the tired seam appear at `c_nest_deep` and `c_nest_a`; the
  sentence at `f_rig_a` now says why Bree cannot pick the seam out from the catwalk.

## Plan changes

`out/the-sky-ship-stowaway.plan.json`, kept in its existing `indent=1` format:

- New facts `seams_alike_from_below`, `nimbus_harness` and `mash_for_nimbus`.
- `f_rig_a` establishes `seams_alike_from_below`; `b_free1` establishes `nimbus_harness`, which `b_free_ok` and
  `e_neu_kite` now require; `e_win_discovery` establishes `mash_for_nimbus`. Events updated for the three nodes.
- Costs written for `c_tell_crew`, `c_tell_captain` and `c_tell_reveal`. They had all been `none`, which the G1
  revision of SP-8 (AL-819) made an ERROR at `b_tell1` before this pass began; the new costs are read from the prose
  (the bosun vouching before the crew, the captain's fear of gossip, three ladders down mid-storm).
- `provenance.book_sha256` set to the new hash; a `provenance.notes` entry records the residual fixes.

## Acceptance

| Check | Result |
| --- | --- |
| `run_story_gate.py` | exit 0, `findings=1` (advisory RL-13 at `e_set_nest`, present before), `blocked=False` |
| `run_fill_gate(...).blocked` | `False` |
| `check_story_plan.py` | 0 errors, 0 warnings (before: 1 ERROR, SP-8 at `b_tell1`) |
| `check_fill_integrity.py` | markers, words (mean 100.8) and fill-rate (103.0%) ok; structure fails as before |
| `check_prose_craft.py --check` | exit 0, every line identical except the narration word count |
| Shape hash | unchanged |
| Witnesses A, B, C | replay and now read true |

The structure check compares against `skeletons/8-11/the-sky-ship-stowaway.json` and failed before this pass too,
as expected for a revised book.
