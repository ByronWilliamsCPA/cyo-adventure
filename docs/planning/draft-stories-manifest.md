<!--
SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
SPDX-License-Identifier: MIT
-->

# Draft stories manifest (authored, not yet in production)

These are complete, validator-passed filled Storybooks that have been authored
(a `skeletons/<band>/<slug>.json` shell filled with age-band-appropriate prose)
but have NOT been imported or published to production. They become "in
production" only after the import/publish flow: the `cyo-author` skill validates
and imports a filled story, then it passes the `publishing/` approve-and-publish
state machine plus guardian/admin approval before it is served to a child.

All files below are git-tracked in `ByronWilliamsCPA/cyo-adventure`; no access
beyond the repository is required. Generated 2026-07-20.

Not drafts (do not point here):

- `skeletons/<band>/<slug>.json`: the shells (structure + `<<FILL>>` directives,
  no prose) these were filled from.
- `out/ws2/<slug>/`: WS-2 theme-rebinding intermediates (`plan.json`,
  `new-theme.bound.json`, `binding.json`, `fingerprint-manifest.json`).
- Gitignored scratch: `out/mutations/` (WS-5 promotion bundles),
  `out/diversity/` (eval fills), `output/`.

## Stories (23 distinct, across all six bands)

| Title | Band | Length | Style | Tier | Nodes | Endings | Path |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Clover and the Butterfly | 3-5 | short | prose | T1 | 20 | 7 | `out/the-clover-and-the-butterfly.filled.json` |
| The Lost Mitten | 3-5 | n/a | n/a | T1 | 11 | 3 | `out/the-lost-mitten.filled.json` |
| The Teddy Bears' Picnic | 3-5 | medium | prose | T1 | 29 | 11 | `out/the-teddy-bears-picnic.filled.json` |
| The Backyard Treasure Map | 5-8 | medium | prose | T1 | 61 | 12 | `out/the-backyard-treasure-map.filled.json` |
| The Lantern Festival | 5-8 | short | prose | T1 | 36 | 10 | `out/the-lantern-festival.filled.json` |
| The Cave of Echoes | 8-11 | short | prose | T1 | 64 | 16 | `out/the-cave-of-echoes.filled.json` |
| The Clockwork Menagerie | 8-11 | long | prose | T1 | 166 | 27 | `out/the-clockwork-menagerie.filled.json` |
| The Sky-Ship Stowaway | 8-11 | medium | prose | T1 | 111 | 20 | `out/the-sky-ship-stowaway.filled.json` |
| The Clocktower Cipher | 10-13 | n/a | n/a | T1 | 25 | 8 | `out/the-clocktower-cipher.filled.json` |
| The Hollow Lighthouse | 10-13 | medium | prose | T1 | 148 | 31 | `out/the-hollow-lighthouse.filled.json` |
| The Mapmaker's Island | 10-13 | long | prose | T1 | 224 | 72 | `out/the-mapmakers-island.filled.json` |
| The Midnight Museum | 10-13 | short | prose | T1 | 94 | 19 | `out/the-midnight-museum.filled.json` |
| The Harrowstone Keep | 13-16 | long | gamebook | T2 | 550 | 152 | `out/the-harrowstone-keep.filled.json` |
| The Signal in the Static | 13-16 | medium | prose | T1 | 123 | 32 | `out/the-signal-in-the-static.filled.json` |
| The Sunken Temple | 13-16 | long | gamebook | T2 | 550 | 152 | `out/the-sunken-temple.filled.json` |
| The Sunspire Ascent | 13-16 | medium | gamebook | T1 | 252 | 74 | `out/the-sunspire-ascent.filled.json` |
| The Thornwood Trial | 13-16 | long | gamebook | T1 | 375 | 115 | `out/the-thornwood-trial.filled.json` |
| The Vanishing Orchard | 13-16 | long | prose | T1 | 177 | 33 | `out/the-vanishing-orchard.filled.json` |
| The Ashfall Expedition | 16+ | long | gamebook | T1 | 505 | 143 | `out/the-ashfall-expedition.filled.json` |
| The Drowned Court | 16+ | medium | gamebook | T1 | 314 | 105 | `out/the-drowned-court.filled.json` |
| The Last Train North | 16+ | medium | prose | T1 | 143 | 25 | `out/the-last-train-north.filled.json` |
| The Salt Archive | 16+ | long | prose | T1 | 225 | 54 | `out/the-salt-archive.filled.json` |
| The Sunken Signal | 16+ | n/a | n/a | T2 | 32 | 14 | `out/the-sunken-signal.filled.json` |

## Pilot re-theme variants

Same *Cave of Echoes* skeleton, filled for two alternate themes (WS-2 pilot).

| Title (theme) | Band | Path |
| --- | --- | --- |
| The Cave of Echoes (dino-dig) | 8-11 | `out/pilot/fills/the-cave-of-echoes.dino-dig.filled.json` |
| The Cave of Echoes (space-station) | 8-11 | `out/pilot/fills/the-cave-of-echoes.space-station.filled.json` |

## Notes

- Tier-2 (stateful, items/flags/counters) stories: The Harrowstone Keep, The
  Sunken Temple, The Sunken Signal.
- Three stories carry an older metadata shape (`schema_version: "1.0"`, no
  `metadata.topology`, stale `{id, type, title}` endings): The Lost Mitten,
  The Clocktower Cipher, The Sunken Signal. Empirically verified (by running
  `validator/gate.py::run_gate` against each) to need exactly three
  normalizations before the gate passes, all backfilled from the source
  skeleton rather than invented: bump `schema_version` to `"2.0"`; copy
  `metadata.topology` and `metadata.production_eligible` (`False` for all
  three) from the skeleton; replace each node's stale `ending` dict with the
  skeleton's `{id, valence, kind, title}` shape, matched by node id. See
  `generation/import_catalog.py::_normalize_legacy_fill` for the
  implementation and `tests/unit/test_import_catalog.py::
  TestRealLegacyFilesNormalizeCleanly` for the regression proving it against
  these three files.
- Node and ending counts are read directly from each filled document.
