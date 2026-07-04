---
title: "Story Skeleton Catalog"
schema_type: common
status: published
owner: core-maintainer
purpose: "Catalog of preset story skeletons (structure diagrams) and the data dictionary for skeleton metadata, generated from skeletons/."
tags:
  - architecture
  - reference
  - documentation
---

A **skeleton** is a structurally-valid Storybook shell: a directed graph of nodes
whose non-ending bodies carry a `<<FILL role=... words=... beats='...'>>` directive
to be replaced by prose. Each skeleton is validated by the gate's blocking layers
at load time, so a skeleton can never introduce a structural defect.

This page catalogs the preset skeletons and defines the controlled vocabulary
behind their metadata. The table below and the band-coverage matrix are generated
from `skeletons/` by `scripts/render_skeleton_diagrams.py`; regenerate after
changing any skeleton:

```bash
PYTHONPATH=. uv run python scripts/render_skeleton_diagrams.py
```

The structure diagrams are PlantUML state diagrams: `[*]` enters the start node,
choices are labeled transitions, and ending nodes are terminal states colored by
valence (green positive, gray neutral, red negative). Non-ending nodes are colored
by narrative role.

<!-- BEGIN GENERATED: skeleton-catalog -->

### Documented skeletons

| Skeleton | Band | Length (min) | Tier | Topology | Nodes | Endings (+/n/-) | Diagram |
| --- | --- | --- | --- | --- | --- | --- | --- |
| The Clocktower Cipher | 10-13 | 18 | 1 | branch_and_bottleneck | 25 | 3/1/4 | [svg](diagrams/skeletons/10-13/the-clocktower-cipher.svg) |
| The Hollow Lighthouse | 10-13 | 13 | 1 | branch_and_bottleneck | 148 | 10/5/16 | [svg](diagrams/skeletons/10-13/the-hollow-lighthouse.svg) |
| The Mapmaker's Island | 10-13 | 22 | 1 | branch_and_bottleneck | 224 | 11/32/29 | [svg](diagrams/skeletons/10-13/the-mapmakers-island.svg) |
| The Midnight Museum | 10-13 | 9 | 1 | branch_and_bottleneck | 94 | 7/3/9 | [svg](diagrams/skeletons/10-13/the-midnight-museum.svg) |
| The Signal in the Static | 13-16 | 11 | 1 | branch_and_bottleneck | 123 | 11/0/21 | [svg](diagrams/skeletons/13-16/the-signal-in-the-static.svg) |
| The Vanishing Orchard | 13-16 | 18 | 1 | branch_and_bottleneck | 177 | 5/5/23 | [svg](diagrams/skeletons/13-16/the-vanishing-orchard.svg) |
| The Last Train North | 16+ | 14 | 1 | branch_and_bottleneck | 143 | 5/9/11 | [svg](diagrams/skeletons/16+/the-last-train-north.svg) |
| The Salt Archive | 16+ | 24 | 1 | branch_and_bottleneck | 225 | 15/21/18 | [svg](diagrams/skeletons/16+/the-salt-archive.svg) |
| The Sunken Signal | 16+ | 30 | 2 | branch_and_bottleneck | 32 | 1/1/12 | [svg](diagrams/skeletons/16+/the-sunken-signal.svg) |
| Clover and the Butterfly | 3-5 | 3 | 1 | time_cave | 20 | 4/0/3 | [svg](diagrams/skeletons/3-5/the-clover-and-the-butterfly.svg) |
| The Lost Mitten | 3-5 | 5 | 1 | loop_and_grow | 11 | 3/0/0 | [svg](diagrams/skeletons/3-5/the-lost-mitten.svg) |
| The Teddy Bears' Picnic | 3-5 | 5 | 1 | loop_and_grow | 29 | 5/0/6 | [svg](diagrams/skeletons/3-5/the-teddy-bears-picnic.svg) |
| The Backyard Treasure Map | 5-8 | 7 | 1 | time_cave | 61 | 6/0/6 | [svg](diagrams/skeletons/5-8/the-backyard-treasure-map.svg) |
| The Lantern Festival | 5-8 | 6 | 1 | loop_and_grow | 36 | 7/0/3 | [svg](diagrams/skeletons/5-8/the-lantern-festival.svg) |
| The Cave of Echoes | 8-11 | 8 | 1 | time_cave | 64 | 10/0/6 | [svg](diagrams/skeletons/8-11/the-cave-of-echoes.svg) |
| The Clockwork Menagerie | 8-11 | 18 | 1 | branch_and_bottleneck | 166 | 14/3/10 | [svg](diagrams/skeletons/8-11/the-clockwork-menagerie.svg) |
| The Sky-Ship Stowaway | 8-11 | 11 | 1 | branch_and_bottleneck | 111 | 8/1/11 | [svg](diagrams/skeletons/8-11/the-sky-ship-stowaway.svg) |

### Band coverage

| Age band | Skeletons |
| --- | --- |
| 3-5 | yes |
| 5-8 | yes |
| 8-11 | yes |
| 10-13 | yes |
| 13-16 | yes |
| 16+ | yes |

<!-- END GENERATED: skeleton-catalog -->

Three of the six catalogued skeletons (The Clocktower Cipher, The Sunken Signal, The
Lost Mitten) declare `production_eligible: false` and no `length` or `narrative_style`:
they are ADR-011 section 1a MVP/Test-tier development seeds (a band-independent 8-45
node envelope, budgeted with `mvp_node_budget` in `validator/band_profile.py`), not
examples of a production `(age_band, length, narrative_style)` cell. The other three
(The Midnight Museum, The Lantern Festival, The Cave of Echoes) are the first
production-eligible seeds: each declares `length: short`, `narrative_style: prose`,
and `production_eligible: true` for one ADR-011 launch cell. The "Length (min)" column
above is `estimated_minutes` (a read-time estimate), not the ADR-011 `length` scale
tier described below; per-cell production node budgets live in
`validator/band_profile.py` (`_PRODUCTION_CELLS`), not a single fixed per-band range.
The "Tier" column is the generation `tier` field (`1` forbids state variables, `2`
allows them), a separate concept from the MVP/Test tier.

## Data dictionary

Sourced from `src/cyo_adventure/storybook/models.py` (the enforced schema), with one
exception: node `role` is a FILL-directive convention read by
`generation/diagram.py`, not a field the structural gate enforces. Where
`.claude/skills/cyo-author/reference/skeleton-format.md` disagrees, the model wins;
see template feedback for the doc-correction follow-up.

| Variable | Type | Preset options / constraint |
| --- | --- | --- |
| `age_band` | closed enum | `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+` |
| `tier` | int 1-2 | `1`, `2` (tier 1 forbids state variables) |
| `topology` | closed enum | `time_cave`, `gauntlet`, `branch_and_bottleneck`, `loop_and_grow`, `open_map`, `sorting_hat` |
| `length` | closed enum, optional | `short`, `medium`, `long`; the ADR-011 story-scale axis. Young bands (`3-5`, `5-8`) cap at `medium`. Omitted means the story is not scale-classified |
| `narrative_style` | closed enum, optional | `prose`, `gamebook`; meaningful only for `13-16`/`16+`; every other band is implicitly `prose` |
| `production_eligible` | bool | defaults to `true`; `false` marks a non-production MVP/Test-tier skeleton (ADR-011 section 1a) |
| `valence` | closed enum | `positive`, `neutral`, `negative` |
| `ending.kind` | closed enum | `success`, `setback`, `death`, `capture`, `completion`, `discovery` |
| content flags | level enum per category | categories `violence`, `scariness`, `peril`; levels `none` < `mild` < `moderate` < `intense` |
| `estimated_minutes` | int >= 1 | open (a read-time estimate; not the `length` scale tier above) |
| node `role` | FILL directive | `setup`, `rising`, `choice`, `climax`, plus ending subtypes |

### Definitions

- **age_band** -- the reading age the story targets; drives reading-level, content,
  and fail-state policy.
- **estimated_minutes** -- an integer read-time estimate (the "Length (min)" catalog
  column); distinct from the `length` scale-tier field below.
- **length** -- the ADR-011 story-scale tier (`short` / `medium` / `long`), one axis of
  the `(age_band, length, narrative_style)` production matrix whose per-cell node
  budgets live in `validator/band_profile.py` (`_PRODUCTION_CELLS`). Optional: a
  skeleton that declares no `length` is not scale-classified and keeps the band-level
  budget instead of a per-cell production node budget.
- **narrative_style** -- `prose` or `gamebook`; chunks the same word budget into
  fewer/longer or more/shorter nodes. Meaningful only for `13-16` and `16+`; every
  other band is implicitly `prose`.
- **production_eligible** -- defaults to `true`. `false` marks a non-production
  MVP/Test-tier skeleton (ADR-011 section 1a): a band-independent 8-45 node envelope
  for prototyping and pipeline/generator testing, excluded from child-facing
  production selection regardless of band. All three skeletons in this catalog are
  currently `production_eligible: false` development seeds, not examples of a
  production `(age_band, length, narrative_style)` cell.
- **tier** -- generation tier; tier 1 stories declare no state variables. Not to be
  confused with the MVP/Test tier above (a `production_eligible` concept).
- **topology** -- the branching shape of the graph (Ashwell vocabulary). Six ADR-011
  topologies: `time_cave`, `gauntlet`, `branch_and_bottleneck` (absorbs the retired
  Ashwell `quest` variant), `loop_and_grow`, `open_map`, and `sorting_hat`.
- **valence** -- how an ending feels (positive / neutral / negative), independent of
  what mechanically happened.
- **ending.kind** -- what mechanically happened at an ending (closed set).
- **content flags** -- per-category sensitivity levels, scored against the band ceiling.
- **role** -- a node's narrative function, declared in its FILL directive.
