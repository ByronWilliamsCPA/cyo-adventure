# Variant divergence: v1 (shipped) vs v2 vs v3

Per-node comparison of the four graded fields (`establishes`, `choice_semantics`, `affect`, `function`) across all three narrative-obligation contracts over the unchanged `the-clocktower-cipher` skeleton graph. A cell lists which fields differ for that pair; the bar for a valid variant is >= 2 of 4 differing fields, for every node, on every pair.

| node | v1 vs v2 (n, fields) | v1 vs v3 (n, fields) | v2 vs v3 (n, fields) |
|---|---|---|---|
| `n_open` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_start` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_note` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_door` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_keeper` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_keyhunt` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_keeper_story` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_window` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_inside` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_stairs` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_study` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_pendulum` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_basement` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_clockface` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_setcorrect` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_setjam` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_backpanel` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_vault` | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function | 4/4: establishes, choice_semantics, affect, function |
| `n_end_library` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |
| `n_end_giveup` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |
| `n_end_timeout` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |
| `n_end_stuck` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |
| `n_end_secret` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |
| `n_end_hero` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |
| `n_end_keepsake` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |
| `n_end_caught` | 3/4: establishes, affect, function | 3/4: establishes, affect, function | 3/4: establishes, affect, function |

## Per-pair summary

- v1 vs v2: 26/26 nodes meet the 2-of-4 bar.
- v1 vs v3: 26/26 nodes meet the 2-of-4 bar.
- v2 vs v3: 26/26 nodes meet the 2-of-4 bar.

## Nodes under the bar

None. Every node meets the 2-of-4 bar on every pair (v1 vs v2, v1 vs v3, v2 vs v3). No merge node required forcing: the graph's three merge points (`n_inside`, 6-way; `n_clockface`, 4-way; `n_vault`, 3-way) were handled by giving each variant its own whole-graph fact vocabulary (test-of-character facts for v2; reconstruct-and-remember facts for v3), so the facts each merge node's contract `entry_state` requires differ in name and meaning across variants even though the graph position and physical action are fixed. NC-1 merge closure was verified deterministically (`scripts/check_narrative_contract.py`, exit 0 for both new contracts) rather than by hand, precisely because the merges are the part hand-checking is likely to get wrong.

## Note on the 18 `open`-tier nodes vs the 8 `locked_outcome` (ending) nodes

The 18 non-ending nodes hit 4/4 on every pair: they carry a `choice_semantics` block (they have outgoing choices), and that field diverges too, on top of `establishes`, `affect`, and `function`. The 8 ending nodes are graph leaves with no outgoing choices, so `choice_semantics` is structurally absent (empty on all three variants) and cannot contribute a difference; they still clear the bar at 3/4 via `establishes`, `affect`, and `function`. This is a structural property of the graph (endings have no choices), not a variant that fell short of the four-field ideal.
