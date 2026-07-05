---
title: "Skeleton Authoring Handoff (P1 preset library)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Kickoff context for authoring production-eligible skeletons against the merged ADR-011 story-scale enabler."
tags:
  - planning
  - authoring
  - skeleton-library
  - story-scale
---

## What this is

The **story-scale enabler is merged** (PR #70, squash `baf7347`, 2026-07-03). All
eight enabler slices are on `main`: length/style/topology enums, derived per-cell node
budgets, words-per-node walls, min-to-complete arc floors, breadth-scaled ending/decision
floors, series metadata + meta-validator, the 18-cell coverage grid, and the PL-21
off-matrix rejection rule. The framework spec is
[adr-011-story-scale-framework.md](adr/adr-011-story-scale-framework.md), also on `main`.

The **content half** of the two-branch plan authors production-eligible skeleton JSON
against that now-frozen contract. No enabler code work remains; the job is authoring plus
passing the gate.

## Starting point (read before doing anything)

Author on a branch cut from current `main` so you inherit the enabler code; the derived
gate needs `band_profile.offered_cells`, which is absent from any branch that predates
PR #70. The recommended path is a fresh branch:

```bash
git switch main && git pull
git switch -c feat/skeleton-library
```

### If you are resuming from the retired `feat/skeleton-library-expansion` branch

That branch predates the enabler and is several commits behind `main`; rebase it before
authoring so it picks up the enabler code:

```bash
cd <repo-root>/.worktrees/skeleton-library-expansion
git fetch origin main
git rebase origin/main
# Its two ADR-011 commits (438514d, 1537cb7) are already on `main` (PR #70 copied the
# file verbatim); expect them to go empty on rebase, run `git rebase --skip` for each.
env -u VIRTUAL_ENV uv run pytest -q   # confirm you inherited the enabler and a green suite
```

Its one unique doc commit, `7389c21` (`docs(planning): add skeleton library expansion
plan`, the full framework tables), never landed on `main`. ADR-011 carries self-contained
tables and supersedes it, so cherry-pick it only if you decide the plan doc still adds
value over the ADR.

## The contract you author against

Every scale-classified skeleton runs `validator.gate.run_gate(data)` and must return
`blocked=False`. "Scale-classified" means the metadata declares a `length` **and**
`production_eligible` is not `false`. The teeth that now apply (all inert on a length-less
seed, all active once you declare a cell):

| Rule | Enforces | Failure mode |
|---|---|---|
| PL-17 (breadth-scaled) | `min_endings` = ceil(nodes x 0.15 prose / 0.25 gamebook); `min_decisions` = ceil(nodes x 0.08) | too few endings/decisions for the node count |
| PL-19 (words/node) | per-node **max wall** on every story; story-**mean** advisory (WARNING) for scale stories | a `<<FILL words=N>>` above the cell max is an ERROR |
| PL-20 (min-to-complete) | shortest path in nodes from start to a satisfying ending meets the cell arc floor | a too-short fastest-finish is an ERROR |
| PL-21 (off-matrix) | `(band, length, style)` must be one of the 18 offered cells | an off-matrix cell is ERROR-rejected, no silent band fallback |

Node budgets, arc floors, and words/node come straight from ADR-011. Query them live
rather than transcribing:

```bash
env -u VIRTUAL_ENV uv run python -c "
from cyo_adventure.validator.band_profile import (
    production_cell_budget, min_complete_floor, words_per_node_profile)
print(production_cell_budget('8-11','short','prose'))   # (min, max, depth)
print(min_complete_floor('8-11','short','prose'))        # arc floor nodes
print(words_per_node_profile('8-11','prose'))            # (mean, lo, hi, per_node_max)
"
```

## The 18 offered cells and P1 targets

`offered_cells()` (band, length, style):

```
3-5:    short, medium               (prose only)
5-8:    short, medium               (prose only)
8-11:   short, medium, long         (prose only)
10-13:  short, medium, long         (prose only)
13-16:  medium, long (prose); medium, long (gamebook)
16+:    medium, long (prose); medium, long (gamebook)
```

`main` currently has **only three seeds, all `production_eligible: false`** (MVP/Test
tier): `3-5/the-lost-mitten`, `10-13/the-clocktower-cipher`, `16+/the-sunken-signal`.
**There are zero production-eligible skeletons.** P1 seeds the launch bands:

| Cell | Node budget (min,max,depth) | Arc floor | Words/node (mean,lo,hi,max) | Topology |
|---|---|---|---|---|
| `8-11 short prose` | (60, 100, 23) | 9 | (100, 70, 135, 220) | time_cave |
| `5-8 short prose` | (29, 50, 18) | 7 | (70, 50, 95, 155) | loop_and_grow |
| `13-16 medium gamebook` | (245, 370, 60) | 24 | (65, 45, 90, 145) | gauntlet |

> **Trap (PL-21):** `13-16 short gamebook` is **off-matrix** , its budget is `None`.
> Gamebook exists only at 13-16/16+, and only at `medium`/`long`. The plan memo's
> "13-16 gamebook gauntlet" as a light P1 target is wrong: the smallest legal 13-16
> gamebook is **medium = 245-370 nodes**, a large authoring lift. Decide whether to keep
> it in P1 or swap in another prose cell (e.g. `10-13 short prose`).

## Authoring workflow (one skeleton at a time)

1. **File path:** `skeletons/<band>/<slug>.json` (e.g. `skeletons/8-11/the-cave-of-echoes.json`).
2. **Node bodies are FILL-templated**, not prose. Each node body is a directive the
   generation stage later fills, and it declares its own word budget so the gate can size
   the story pre-fill:
   ```json
   "body": "<<FILL role=setup words=95 beats='...one-line beat sheet...'>>"
   ```
   The `words=N` you write is what PL-19 checks against the cell's per-node max, and what
   PL-20 sums along the shortest satisfying path. Keep each `N` <= the cell's per-node max.
3. **Metadata block** must declare the cell and mark it production-ready. Mirror an
   existing seed's shape (`skeletons/3-5/the-lost-mitten.json`) but set:
   ```json
   "length": "short",
   "narrative_style": "prose",
   "production_eligible": true,
   "topology": "time_cave"
   ```
   (Omitting `length`, or leaving `production_eligible: false`, keeps the story on the
   old band path and silently skips every PL-17/19/20/21 tooth , that is the MVP/Test
   escape hatch, not what you want for a launch skeleton.)
4. **Gate it** until `blocked=False`:
   ```bash
   env -u VIRTUAL_ENV uv run python -c "
   from cyo_adventure.generation.skeleton import load_skeleton
   from cyo_adventure.validator.gate import run_gate
   from pathlib import Path
   r = run_gate(load_skeleton(Path('skeletons/8-11/the-cave-of-echoes.json')))
   print('blocked:', r.blocked); print('rules:', r.report.rule_ids())
   "
   ```
   The loader-gate pair is the spec: if `run_gate` passes, the skeleton is valid.
5. **Render the diagram** so the graph is reviewable:
   `env -u VIRTUAL_ENV uv run python scripts/render_skeleton_diagrams.py`
6. **Add a corpus test assertion** (follow `tests/unit/test_corpus_layer2.py`) so the new
   seed is pinned `blocked=False` in CI.
7. **One signed commit per skeleton**, on a `feat/` branch, conventional message
   (`feat(skeletons): add 8-11 short prose time_cave seed`). Run
   `pre-commit run --all-files` first. Keep skeleton `.json` strict (no trailing commas)
   so `check-json` passes; regenerate schema only via
   `python -m cyo_adventure.storybook.schema_export`.

## Definition of done (per skeleton)

- `(band, length, style)` is one of the 18 offered cells; `production_eligible: true`.
- Node count within the cell's (min, max); no node's `words=N` exceeds the per-node max.
- Endings >= PL-17 breadth floor; decisions >= PL-17 decision floor.
- Shortest path to a satisfying ending >= the cell arc floor (PL-20).
- Topology matches what the classifier admits for the graph shape (time_cave/gauntlet/etc).
- `run_gate` returns `blocked=False`; a corpus test pins it; diagram regenerated.

## Open decisions to settle first

1. **Which 3 bands lead launch?** The plan's "natural core" is `5-8 / 8-11 / 10-13`
   (all prose, all with a cheap `short` cell). The older P1 list (`8-11 / 5-8 / 13-16`)
   pulls in the 245+ node gamebook. Recommend leading with the three prose `short` cells
   for fastest time-to-first-production-skeleton, and treating 13-16 gamebook as its own
   later effort.
2. **The orphaned plan doc** (`7389c21`): land via a `docs:` PR or drop in favor of
   ADR-011. Not a blocker for authoring.
3. **Deferred enabler refinements** (issues #77 off-matrix prompt guidance, #78
   brief.length->metadata.length propagation, #79 test hardening + cross-field metadata
   invariants) are the enabler author's calls and do not block authoring. Skeletons are
   hand-authored, so the #78 propagation gap (a generation-path concern) does not affect
   this branch.

## Pointers

- Framework spec: [adr/adr-011-story-scale-framework.md](adr/adr-011-story-scale-framework.md)
- Loader / gate: `src/cyo_adventure/generation/skeleton.py`, `src/cyo_adventure/validator/gate.py`
- Budgets / floors / cells: `src/cyo_adventure/validator/band_profile.py`
- Policy rules PL-15..PL-21: `src/cyo_adventure/validator/policy.py`
- Series meta-validator (later, for campaigns): `src/cyo_adventure/validator/series.py`
- Existing seeds to mimic: `skeletons/3-5/the-lost-mitten.json` (small), `skeletons/16+/the-sunken-signal.json` (large)
