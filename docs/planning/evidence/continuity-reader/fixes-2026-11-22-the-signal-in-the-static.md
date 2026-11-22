# Residual fixes: The Signal in the Static (2026-11-22)

Fixes for the real items in [residuals-2026-11-21.md](residuals-2026-11-21.md) (section "The Signal in the
Static"), owner-approved 2026-11-22. SG-3 was judged not a defect and is unchanged. The WP-0.4 fixes in
[findings-the-signal-in-the-static.md](../story-plan-retro/findings-the-signal-in-the-static.md) are kept.

- Book `out/the-signal-in-the-static.filled.json`: sha256 `d701b7891ff2...` before, `2636ac09b732...` after.
- Prose only, one sentence or clause per item. No node, choice, condition, effect, variable or ending changed;
  the shape hash stays `47dec22dff1f...`.
- Plan `out/the-signal-in-the-static.plan.json`: `alder_refused_transfer` text, events of `m_who_article`,
  `m_num_countdown`, `e_he_complete` and `r_re_hut`; `e_he_complete` now establishes `circled_number`;
  `provenance.book_sha256` rebound; a `provenance.notes` entry added.

| ID | Node | Before | After | Verified |
| --- | --- | --- | --- | --- |
| SG-1 | `m_numbers_1` | "from the cedar trunk in the attic" | "from a cedar trunk in the attic" | W1 |
| SG-2 | `m_num_countdown` | "threaded through every cycle is that one stubborn letter, M." | clause cut | W2, W2b |
| SG-4 | `m_who_article` | "only one of nine staff who refused the transfer inland." | see note A | W4, W4b |
| SG-5 | `e_he_complete` | "dials the number circled in his address book." | see note B | W5 |
| SG-6 | `r_re_hut` | "did not walk away when the county did." | "when the station went dark." | W6 |

Notes:

- A: "He is the only one of ten staff who refused to leave: eight took the transfer inland, and one resigned
  rather than go." This squares the article with the eight bracketed men and Ruiz (STAYED) in `f_he_colleague`.
- B: "dials a number that Kell has circled so many times in his address book that the paper shines." The sentence
  now introduces the number and names its owner, so "his" can no longer read as Grandpa's.
- SG-2: the sentence now reads "The intervals are closing on tonight like a hand closing." The letter is first
  given on this route at `n_b2` (the Morse chart).

Verification: each witness was replayed from `n_open` with `StoryEngine`. It lands on the node, the new text is
present, and the earlier nodes on the route were searched for the fact.

- W1: `SG-H > SG-N > c_n_b1_choice_1` (13 choices). No earlier node mentions a trunk.
- W2: `SG-H > SG-N > c_n_b1_choice_1 > c_m_numbers_1_2 > c_m_num_time_2 > c_m_num_pattern_1` (16). No earlier
  node, and not `m_num_countdown` itself, names M or a letter.
- W2b: W2 `> c_m_num_countdown_1` (17) lands on `n_b2`, which finds M.
- W4: `SG-H > SG-S > c_n_b1_choice_2 > c_m_who_1_1 > c_m_who_film_1 > c_m_who_article_1 > SG-D3` (26) lands on
  `f_he_colleague`. W4b adds `> c_f_he_colleague_2` (27) and lands on `e_he_dead`. Ten staff now matches eight,
  Ruiz and Kell.
- W5: `SG-H > SG-S > c_n_b1_choice_1 > c_m_numbers_1_1 > c_m_num_cipher_1 > c_m_num_cracked_1 > SG-D3 >
  c_f_he_colleague_1 > c_f_he_join_1` (28). No earlier node mentions a circled number.
- W6: `c_open > c_n_shelf_1 > c_n_shelf_battery_1 > c_n_start_2 > c_r_relay_1_2 > c_r_re_lane_2` (6). `n_start`
  ("has stood dark for as long as she can remember") is on every route into `r_re_hut`.

Gates after the fix:

- `run_story_gate.py` exits 0. `run_fill_gate` is not blocked, with the same 4 warnings as before.
- `check_story_plan.py`: 0 errors, 1 warning. The warning (SP-8 at `m_numbers_1`) was there before.
- `check_fill_integrity.py`: markers, words and fill-rate pass. Structure fails, as it does for every revised
  book.
- `check_prose_craft.py --check`: exits 0, with no new failures.
