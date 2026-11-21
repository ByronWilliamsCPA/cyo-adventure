# WP-1.6 fresh-corpus confirmation: corpus selection

Committed before any read of these books, so the selection cannot follow the results
(`docs/planning/story-plan-implementation-plan.md`, WP-1.6; owner decision D5, condition 2).

## Rule

One catalog book per family band (8-11, 10-13, 13-16) that has not been read, planned or used anywhere in WP-0.3 to
WP-1.5 or the plan-review pilot. Where a band has more than one eligible book, the book is drawn by
`sha256(<commit hash>) mod <count>` over the sorted eligible slugs, using the commit that recorded the D5 acceptance
(`862ee6cb9321befe4b410d896672e74d4a38bff8`).

## Eligible books and the draw

| Band | Eligible (unused) | Draw | Selected |
| --- | --- | --- | --- |
| 8-11 | `the-clockwork-menagerie` | only one eligible | `the-clockwork-menagerie` |
| 10-13 | `the-clocktower-cipher` | only one eligible | `the-clocktower-cipher` |
| 13-16 | `the-harrowstone-keep`, `the-sunken-temple`, `the-sunspire-ascent`, `the-thornwood-trial` | index 3 of 4 | `the-thornwood-trial` |

Excluded as already used: `the-cave-of-echoes`, `the-sky-ship-stowaway`, `the-hollow-lighthouse`,
`the-midnight-museum`, `the-mapmakers-island`, `the-signal-in-the-static`, `the-vanishing-orchard`, and the Run B
fills.

## Books as read

| Slug | File | SHA-256 | Nodes | Variables |
| --- | --- | --- | ---: | ---: |
| `the-clockwork-menagerie` | `out/the-clockwork-menagerie.filled.json` | `f69e13d99a242a3478066522deb123f564cc556c1661ff14f824a8482274204e` | 167 | 0 |
| `the-clocktower-cipher` | `out/the-clocktower-cipher.filled.json` | `2d476787f5e61104d2e8f87765820496488f2780d3c08cd19cfcc7516b305bb5` | 26 | 0 |
| `the-thornwood-trial` | `out/the-thornwood-trial.filled.json` | `cd3f45ad0d3d8075e57fdd203612a66ce59d65f1b2613c5ba7419caaf165476d` | 376 | 0 |

Caveats recorded up front: the 10-13 book is small (26 nodes) because it is the only eligible one, and none of the
three declares variables, so the state-contradiction and public-plant classes may have no items to find. The report
will say so rather than score an empty class as a pass.

## Order of work

1. Second read of each book (WP-0.4 method), findings frozen and committed here first.
2. Blind plan extraction under `../story-plan-retro/plans/EXTRACTION-PROMPT-v2.md` by fresh agents that cannot see
   step 1.
3. The checker on step 2, scored against step 1 with the WP-1.5 "found" definition and the WP-1.6 criterion.
