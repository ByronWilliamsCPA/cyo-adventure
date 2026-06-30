---
title: "Skeleton Structure Diagrams and Catalog (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "skeletons/; src/cyo_adventure/generation/skeleton.py; src/cyo_adventure/storybook/models.py; docs/architecture/diagrams/; docs/architecture/README.md; .claude/skills/cyo-author/reference/skeleton-format.md"
purpose: "Design for a deterministic generator that renders each preset story skeleton (a structurally-valid Storybook shell) as a PlantUML state diagram, plus a catalog and data-dictionary doc, so the preset library is reviewable at a glance and diagrams cannot drift from the JSON."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/skeleton-diagrams` (worktree `.worktrees/feat-skeleton-diagrams`,
> based on `origin/main`) | Date: 2026-06-30 | Author: Byron Williams (with Claude)

## 1. Problem and goal

The preset story skeletons under `skeletons/` are structurally-valid Storybook
shells: directed graphs of nodes whose non-ending bodies carry a `<<FILL ...>>`
directive. Reviewing them today means reading JSON node-by-node and mentally
reconstructing the branching shape. As the library grows toward the full matrix
(six age bands x story lengths), this does not scale, and there is no single
surface that answers "what structures do we already have?"

**Goal.** Produce a visual, faithful diagram for every skeleton, plus one
reference document that catalogs the library and defines the controlled
vocabulary behind it. Diagrams must be exact (built from the JSON, not drawn by
hand or by an AI image model) and must not be able to silently drift from the
data.

**Non-goal.** Authoring the missing band x length skeletons; generating
illustrative or cover art (AI image generation is explicitly out of scope for
these structural diagrams, where a hallucinated edge would mislead a reviewer).

## 2. Background: what a skeleton is

A skeleton (see `src/cyo_adventure/generation/skeleton.py`) is loaded and
validated through the existing gate's blocking layers (structure, references,
reachability, termination, budget) at load time. Each skeleton has:

- `start_node` (entry).
- `nodes[]`, each with `id`, `body`, `is_ending`. Non-ending nodes carry a
  `<<FILL role=ROLE words=N beats='...'>>` directive and a list of `choices`
  (`id`, `label`, `target`). Ending nodes carry an `ending` object
  (`valence`, `kind`, `title`).
- `metadata`: `age_band`, `reading_level`, `tier`, `themes`,
  `estimated_minutes`, `ending_count`, `content_flags`, `topology`.

The graph is therefore directly renderable as a state machine: `[*]` to the
start node, choices as labeled transitions, ending nodes as terminal states.

### Current library (3 of 6 bands populated)

| Skeleton | Band | Length (est. min) | Tier | Topology | Nodes | Endings (valence) |
| --- | --- | --- | --- | --- | --- | --- |
| The Lost Mitten | 3-5 | 5 | 1 | loop_and_grow | 11 | 3 (3 positive) |
| The Clocktower Cipher | 10-13 | 18 | 1 | branch_and_bottleneck | 25 | 8 (3 positive, 1 neutral, 4 negative) |
| The Sunken Signal | 16+ | 30 | 2 | branch_and_bottleneck | 32 | 14 (1 positive, 1 neutral, 12 negative) |

## 3. Approach: deterministic generator, three layers

The work splits into a pure transform, a thin I/O shell, and an optional render
step. The split makes the core trivially testable and lets the deliverable
degrade gracefully: even if the PlantUML jar cannot be fetched, the committed
`.puml` source is still produced.

### 3.1 Pure transform

`skeleton_to_plantuml(data: dict[str, object]) -> str` in a new module
`src/cyo_adventure/generation/diagram.py`.

- Input is a decoded skeleton dict (already validated by `load_skeleton`).
- Output is deterministic PlantUML **state diagram** source. Deterministic means
  byte-stable for a given input: nodes and transitions are emitted in document
  order (start node first, then `nodes[]` order), so regeneration is diffable.
- Pure: no filesystem, no clock, no network. This is what makes strict-mode
  coverage and the drift-guard test cheap.

### 3.2 CLI shell

`scripts/render_skeleton_diagrams.py`:

1. Walk `skeletons/**/*.json`.
2. For each, call `load_skeleton()` (validates) then `skeleton_to_plantuml()`.
3. Write `docs/architecture/diagrams/skeletons/<band>/<slug>.puml`.
4. If a PlantUML jar is available, render `<slug>.svg` beside it.
5. Regenerate the catalog/data-dictionary doc (section 5) from the same in-memory
   skeleton data, so the catalog and the diagrams are always built from one pass.

Flags: `--check` (regenerate to a temp area and diff against committed files;
non-zero exit on drift, for the test/CI to call) and `--no-svg` (skip rendering).

### 3.3 Render step

The project standard is PlantUML `.puml` + `.svg` pairs rendered with
`java -jar plantuml.jar -tsvg`. `java` 21 is present, but the README's
`/tmp/plantuml.jar` is ephemeral and currently absent. The render step will:

- Look for the jar at a stable cached path (`~/.cache/cyo-adventure/plantuml-<ver>.jar`),
  falling back to an env var `PLANTUML_JAR` if set.
- If absent, download the pinned version (**1.2024.7**, matching the existing
  SVGs) and verify a known SHA-256 before use.
- Never fail the whole run if rendering is unavailable: emit `.puml`, warn that
  SVGs were skipped, exit 0 unless `--check` found drift.

```text
#CRITICAL: external resource: the render step downloads a jar over the network.
#VERIFY: pin the version, verify SHA-256 before executing the jar, and treat a
         download failure as a skipped-SVG warning, never an executed-unverified-binary.
```

## 4. The diagram: a PlantUML state diagram

For each skeleton:

- `[*] --> <start_node>`.
- Each non-ending node is a state. Its label shows `id`, `role`, and target
  `words` (parsed from the FILL directive). The `<<FILL` body text and `beats`
  prose are **not** rendered as node labels (only role/words), so author intent
  never leaks into the structural view.
- Each choice is a transition `<from> --> <target> : <label>` (label truncated
  with an ellipsis beyond ~40 chars to keep layout readable).
- Each ending node is a state styled by `valence` and shows `kind` + ending
  `title`, then `--> [*]`.
- Color encoding via `skinparam state` stereotypes:
  - Roles: `setup`, `rising`, `choice`, `climax` (distinct, calm hues).
  - Endings: `positive` = green, `neutral` = gray, `negative` = red.
- A `legend` / `note` block carries the metadata that names the structure:
  title, age band, tier, length (est. minutes), topology, node count, ending
  count, and the valence split.

PlantUML lays state diagrams out with Graphviz/dot, so reconvergence
(branch_and_bottleneck) and back-edges (loop_and_grow) render without manual
positioning. The 32-node, 14-ending Sunken Signal is the layout stress test and
will be visually checked before the approach is considered adequate; if its
layout is unreadable, the fallback documented in section 8 applies.

## 5. Catalog + data-dictionary doc

`docs/architecture/story-skeletons.md`, four parts:

1. **Basics.** What a skeleton is, how diagrams are generated, and the one
   command to regenerate them.
2. **Documented skeletons.** The catalog table (section 2.1 columns: Skeleton,
   Age band, Length, Tier, Topology, Nodes, Endings + valence split, Diagram
   link), organized by age band then length, each row linking its rendered SVG.
3. **Data dictionary.** One subsection per key variable, each with a definition
   and its preset options or constraint, sourced from `models.py`:

   | Variable | Type | Preset options / constraint |
   | --- | --- | --- |
   | `age_band` | closed enum | `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+` |
   | `tier` | int 1-2 | `1`, `2` (tier 1 forbids state variables) |
   | `topology` | closed enum | `time_cave`, `gauntlet`, `branch_and_bottleneck`, `loop_and_grow` |
   | `valence` | closed enum | `positive`, `neutral`, `negative` |
   | `ending.kind` | closed enum | `success`, `setback`, `death`, `capture`, `completion`, `discovery` |
   | content flags | level enum per category | categories `violence`, `scariness`, `peril`; levels `none` < `mild` < `moderate` < `intense` |
   | `estimated_minutes` | int >= 1 | open (length is continuous; per-band ranges governed by `validator/band_profile.py`) |
   | node `role` | FILL directive | `setup`, `rising`, `choice`, `climax`, plus ending subtypes |

4. **Coverage gaps.** Which band x length cells have a skeleton today and which
   are empty, so the library's coverage is visible at a glance.

The doc is linked from the diagram index in `docs/architecture/README.md`.

### Known drift to flag (not fix here)

`.claude/skills/cyo-author/reference/skeleton-format.md` documents ending types
as `{completion, good, neutral, failure, death}` under an `ending.type` field.
The enforced model uses `ending.kind` in
`{success, setback, death, capture, completion, discovery}` plus a separate
`valence`. The data dictionary sources from `models.py` (the enforced schema)
and notes the discrepancy; correcting the format reference is a follow-up logged
to `docs/template_feedback.md`, out of scope for this change.

## 6. Testing

Project gates apply (Ruff, BasedPyright strict, >= 80% coverage, RAD markers).

- **Transform unit tests** (pure, deterministic):
  - `[*] --> <start_node>` transition present and correct.
  - Every node in `nodes[]` emits exactly one state.
  - Every choice emits one labeled transition to its `target`.
  - Ending states carry valence-correct styling and the ending title/kind.
  - No `<<FILL`, `beats=`, or body prose appears anywhere in the output.
  - Legend metadata (band, length, tier, topology, counts, valence split) matches
    the input.
  - Determinism: same input renders byte-identical output across two calls.
- **Drift guard** (`tests/` test that shells out to `--check`): regenerate
  `.puml` (and the catalog's skeleton list) from each committed skeleton and
  assert it matches the committed files. A skeleton edited without regenerating
  its diagram fails CI. SVG bytes are not asserted (renderer-version sensitive);
  only `.puml` source and the catalog table are drift-checked.
- **Fixture coverage:** the three real skeletons plus a tiny synthetic skeleton
  (one start, one choice, one ending of each valence) to exercise styling
  branches without depending on the production presets.

## 7. Components and boundaries

| Unit | Responsibility | Depends on |
| --- | --- | --- |
| `generation/diagram.py::skeleton_to_plantuml` | dict -> PlantUML string (pure) | FILL-directive parsing helper; `storybook` enums for styling keys |
| `scripts/render_skeleton_diagrams.py` | walk, validate, write `.puml`, render `.svg`, rebuild catalog, `--check` | `load_skeleton`, `skeleton_to_plantuml`, optional jar |
| `docs/architecture/story-skeletons.md` | human catalog + data dictionary | generated section content |
| drift-guard test | fail on stale diagram/catalog | `scripts/...--check` |

The FILL-directive parser (`role`, `words` extraction) is a small shared helper;
if `generation/` already parses FILL elsewhere, reuse it rather than duplicating.

## 8. Risks and fallback

- **Layout quality on large graphs.** If PlantUML's dot-backed layout renders the
  32-node Sunken Signal as spaghetti, options in order of preference:
  (a) tune PlantUML layout hints (`hide empty description`, direction,
  grouping endings); (b) emit Graphviz `.dot` directly for finer rank control
  (`dot` is already installed) while keeping the same catalog. The transform's
  output format is an internal detail behind `skeleton_to_plantuml`, so this is a
  localized change. The user has accepted PlantUML as the primary; this is a
  contingency only.
- **Jar provenance.** Mitigated by version pin + SHA-256 verification (section 3.3).

## 9. Out of scope (YAGNI)

Authoring new skeletons; AI/Nano Banana illustrative art; MkDocs nav wiring beyond
linking the catalog; CI auto-render of SVGs (the script is provided; wiring it
into a workflow is a separate decision). The generator makes each of these a
small follow-up rather than a rewrite.
