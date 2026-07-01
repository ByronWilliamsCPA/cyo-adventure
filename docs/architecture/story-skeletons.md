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
| The Sunken Signal | 16+ | 30 | 2 | branch_and_bottleneck | 32 | 1/1/12 | [svg](diagrams/skeletons/16+/the-sunken-signal.svg) |
| The Lost Mitten | 3-5 | 5 | 1 | loop_and_grow | 11 | 3/0/0 | [svg](diagrams/skeletons/3-5/the-lost-mitten.svg) |

### Band coverage

| Age band | Skeletons |
| --- | --- |
| 3-5 | yes |
| 5-8 | none yet |
| 8-11 | none yet |
| 10-13 | yes |
| 13-16 | none yet |
| 16+ | yes |

<!-- END GENERATED: skeleton-catalog -->

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
| `topology` | closed enum | `time_cave`, `gauntlet`, `branch_and_bottleneck`, `loop_and_grow` |
| `valence` | closed enum | `positive`, `neutral`, `negative` |
| `ending.kind` | closed enum | `success`, `setback`, `death`, `capture`, `completion`, `discovery` |
| content flags | level enum per category | categories `violence`, `scariness`, `peril`; levels `none` < `mild` < `moderate` < `intense` |
| `estimated_minutes` | int >= 1 | open (length is continuous; per-band ranges in `validator/band_profile.py`) |
| node `role` | FILL directive | `setup`, `rising`, `choice`, `climax`, plus ending subtypes |

### Definitions

- **age_band** -- the reading age the story targets; drives reading-level, content,
  and fail-state policy.
- **length** -- `estimated_minutes`, an integer; not a fixed set. Per-band word and
  node ranges are governed by `validator/band_profile.py`.
- **tier** -- generation tier; tier 1 stories declare no state variables.
- **topology** -- the branching shape of the graph (Ashwell vocabulary).
- **valence** -- how an ending feels (positive / neutral / negative), independent of
  what mechanically happened.
- **ending.kind** -- what mechanically happened at an ending (closed set).
- **content flags** -- per-category sensitivity levels, scored against the band ceiling.
- **role** -- a node's narrative function, declared in its FILL directive.
