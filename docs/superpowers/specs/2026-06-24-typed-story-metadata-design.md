---
title: "Typed Story Metadata and the Programmatic Review Boundary (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md; src/cyo_adventure/storybook/models.py; src/cyo_adventure/validator/"
purpose: "Design for typing story metadata (two-axis endings, content flags, topology, per-node safety scope) so age-safety and shape checks become deterministic gate invariants, plus the config-driven six-band policy table, the PL-15..PL-18 policy gate, and the AI reviewer roster for the irreducible judgments."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/typed-story-metadata` (worktree `.worktrees/typed-story-metadata`,
> based on `feat/modal-generation-tiers`) | Date: 2026-06-24 | Author: Byron Williams (with Claude)
> Builds on the skeleton-library design
> (`docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md`).

## 1. Problem and goal

Review of generated stories splits into two kinds of work: checks a computer can
make deterministically (graph integrity, schema, counts) and judgments that need a
reader's understanding (does this prose suit a six-year-old, is it coherent, is it
safe). The skeleton-library pivot already moves *structure* into the
programmatic column by construction. This design pushes the boundary further: it
**types the metadata that today is free-form**, so several age-safety and shape
checks that would otherwise need an AI reviewer become deterministic gate
invariants, and it **defines the AI reviewer layer** for the judgments that remain
genuinely irreducible.

Two concrete observations motivate the work:

1. `Ending.type` is a free-form string (`src/cyo_adventure/storybook/models.py`,
   `Ending`). The three demo skeletons use five values: `good`, `completion`,
   `neutral`, `failure`, `death`. Nothing keys off them, so the age-gated
   no-death rule cannot be enforced.
2. `ContentFlags` (violence / scariness / peril at none / mild / moderate) already
   exists on `StoryMetadata`, but **no rule compares those flags against the age
   band**. The data is declared and then ignored.

The goal is to formalize these (and a small number of new fields) into typed,
gate-checkable invariants, complete the per-band policy table for all six bands,
add the policy gate layer, and specify the lightweight AI reviewer roster that
consumes the remaining-judgment metadata.

## 2. Scope

In scope: the Storybook schema change (v2.0), the config-driven band profile, the
new policy gate layer, migration of the three demo skeletons, and the **design** of
the AI reviewer architecture. The reviewer agents are designed here but built in a
later implementation phase, because they cannot precede the metadata they consume.

Out of scope: changing generation prompts or providers; the series-manifest feature
(it only *benefits* from `EndingKind.COMPLETION` being typed, it is not built here);
frontend changes.

## 3. Decisions locked during brainstorming (2026-06-24)

| Decision | Choice |
|---|---|
| Ending outcome model | **Two typed axes**: `valence` + `kind` (not a single enum, not a boolean flag) |
| Schema evolution | **Breaking**: repurpose `Ending.type`; bump `SCHEMA_VERSION` to `2.0`; rewrite the 3 skeletons |
| Topology and counts | **Declare-and-verify** topology on the skeleton; **derive** ending/decision floors from the graph |
| Spec scope | **Everything**: schema + gate + the review-agent roster and per-band checklists |

## 4. Data model (Storybook schema 2.0)

All additions live in `src/cyo_adventure/storybook/models.py` and are exported
through `schema_export.build_schema()`.

### 4.1 New enumerations

```python
class Valence(StrEnum):          # how the ending feels (drives age-fit review)
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"

class EndingKind(StrEnum):       # what mechanically happened (closed set)
    SUCCESS = "success"          # goal achieved
    SETBACK = "setback"          # failed but survived   (was free-form "failure")
    DEATH = "death"              # character dies         (young-band forbidden)
    CAPTURE = "capture"          # captured / trapped     (young-band forbidden)
    COMPLETION = "completion"    # series-advancing close
    DISCOVERY = "discovery"      # open / ambiguous       (was free-form "neutral")

class Topology(StrEnum):         # Ashwell vocabulary; authored and verified
    TIME_CAVE = "time_cave"
    GAUNTLET = "gauntlet"
    BRANCH_AND_BOTTLENECK = "branch_and_bottleneck"
    LOOP_AND_GROW = "loop_and_grow"

class SafetyScope(StrEnum):      # per-node hint that scopes the safety checklist
    PERIL = "peril"
    SCARY_IMAGERY = "scary_imagery"
    CONFLICT = "conflict"
    SAD_MOMENT = "sad_moment"
```

### 4.2 Model changes

- **`Ending`** (breaking): remove `type: str`; add `valence: Valence` and
  `kind: EndingKind`. Keep `id` and `title`. An ending is now self-describing on
  both axes.
- **`ContentFlagLevel`**: add `INTENSE = "intense"` above `MODERATE`, so the 16+
  band has policy headroom above the level appropriate for younger bands. Order
  becomes `none < mild < moderate < intense`.
- **`StoryMetadata`**: add `topology: Topology` (authored, required in v2.0).
  `content_flags` and `ending_count` stay as they are.
- **`Node`**: add `safety_scope: list[SafetyScope] = Field(default_factory=list)`.
  Empty by default. The safety reviewer reads it to select the correct per-band
  checklist for sensitive passages; an empty list means no scoped sensitivity.

### 4.3 Floors are not stored on the story

Minimum ending count and minimum decision-node count are **band requirements**, not
per-story authored values. They live in the band profile (section 5) and are
checked against the graph (PL-17). This is the "derive floors" half of the locked
decision: nothing new is authored per story for floors, only verified.

## 5. Band profile (config-driven, all six bands)

New module `src/cyo_adventure/validator/band_profile.py`. It **absorbs the existing
`_BUDGETS` table** in `layer1.py` (which currently covers only `8-11`, `10-13`,
`13-16`, three of the six bands) into one per-band source of truth. `layer1.py`'s
`band_budget()` becomes a thin accessor over this profile so the L1-7 budget check
and the new PL checks read the same data and cannot drift.

```python
@dataclass(frozen=True, slots=True)
class BandProfile:
    min_nodes: int
    max_nodes: int
    max_depth: int
    content_ceiling: Mapping[str, ContentFlagLevel]   # per flag: violence/scariness/peril
    forbidden_ending_kinds: frozenset[EndingKind]
    min_endings: int
    min_decisions: int
    reconvergence_ceiling: int | None = None          # open calibration item; None = unset
```

Profiles are defined for all six bands (`3-5`, `5-8`, `8-11`, `10-13`, `13-16`,
`16+`). Indicative young-band policy: `3-5` and `5-8` set
`forbidden_ending_kinds = {DEATH, CAPTURE}` and `content_ceiling` at `none`/`mild`;
older bands relax both. Exact numbers are filled in during implementation and are
the natural place to tune later, but the only band measured by research is `9-12`;
`3-5` and `16+` remain product-defined.

`reconvergence_ceiling` stays `None` by default (the one deferred calibration item);
PL checks skip it when unset.

## 6. Gate enforcement (new policy layer)

New module `src/cyo_adventure/validator/policy.py`, rule family **PL-15..PL-18**.
It runs inside `run_gate` (`validator/gate.py`) **after Layer 1 passes and the
Storybook parses**, because it needs the typed model and the graph, and **before
Layer 2**. All four rules are ERROR-severity and blocking.

| Rule | Check | Mechanism |
|---|---|---|
| **PL-15** ending-kind policy | no ending whose `kind` is in the band's `forbidden_ending_kinds` | set membership over endings (the no-death / no-capture rule) |
| **PL-16** content ceiling | each `metadata.content_flags` value ≤ the band's `content_ceiling` for that flag | ordered-enum comparison |
| **PL-17** floors | distinct endings ≥ `min_endings`; decision nodes (non-ending nodes with ≥ 2 choices) ≥ `min_decisions` | counted from the graph |
| **PL-18** topology verify | declared `metadata.topology` matches the class inferred from graph metrics | networkx classifier (see 6.1) |

`GateResult.blocked` is extended: it is `True` when any ERROR finding's `rule_id`
starts with `L1`, `L2`, **or `PL`**. RL-13 (advisory) and SAFE-14 (routed to human
review) keep their current non-blocking semantics.

### 6.1 Topology classification

A small classifier derives a `Topology` from the choice graph using interpretable
metrics: branching factor distribution, presence and count of reconvergence
(bottleneck) nodes, and cycle presence (loop-and-grow). PL-18 compares the declared
topology to the inferred one and errors on mismatch. The classifier is deterministic
and unit-tested against the demo skeletons. Where a graph is genuinely ambiguous
between two classes, the classifier returns the set of admissible classes and PL-18
passes if the declared topology is among them; this avoids false rejections on
borderline shapes.

## 7. Review-agent architecture (AI layer)

The metadata above shrinks the AI reviewer's job to the judgments that are
genuinely irreducible. The architecture has three stages.

### 7.1 Deterministic pre-filters (no model)

Run first; cheapest, and they gate entry to the paid stages:

- full `run_gate` re-run on the filled story (defense in depth; structure should be
  guaranteed if fill cannot edit structure)
- `has_unfilled_directives()` confirms no `<<FILL>>` slot remains
- per-node word count within the band budget
- Flesch-Kincaid reading level (existing RL-13)
- profanity / blocklist scan and PII scan (existing `generation/pii.py`)
- topology hash: the filled graph must equal the source skeleton graph

### 7.2 Provider moderation

A single stateless moderation API call (the SAFE-14 seam in `validator/safety.py`).
Catches gross policy violations cheaply; it is a model call, not a reasoning agent.

### 7.3 Reviewer roster

Each reviewer is checklist-driven, returns structured output
`{pass: bool, rule_id: str, reason: str}`, and is given a **per-band checklist** as
its contract. Scopes are deliberately narrow so a cheap model is viable.

| Reviewer | Scope | Default tier | Consumes |
|---|---|---|---|
| edge-coherence | per edge: source body + choice label + target body | cheap | graph |
| fill-fidelity | filled body vs skeleton `FILL role` / `beats` | cheap | skeleton + filled pair |
| choice-quality | per node: choices meaningful and distinct | cheap | graph |
| age-fit | per node / story vs band | cheap then mid | band profile |
| continuity | whole story: names, setting, threads | mid | filled story |
| safety | per node, scoped by `safety_scope` | adversarial majority vote, default-block | band policy + `safety_scope` |

Model tiers mirror the generation tiers: a cheap default model (Gemma / Haiku /
gpt-oss) for the high-volume node- and edge-local checks; only flagged items
escalate to Opus. Safety is the one place to spend more: N cheap reviewers prompted
to refute (default to block on uncertainty), block if any flags.

The fill-fidelity reviewer needs both the original skeleton (for the `FILL role` and
`beats`) and the filled story, because the directive is replaced by prose at fill
time. The orchestrator therefore passes the `(skeleton, filled_story)` pair, not the
filled story alone.

## 8. Migration (schema 1.0 to 2.0, breaking)

1. Bump `SCHEMA_VERSION` to `"2.0"` and update the version guard in `Storybook`.
2. Update `schema_export.build_schema()` and the exported
   `schema/storybook.schema.json`.
3. Update `validator/layer1.py` ending handling and any raw-dict reads that assumed
   `ending.type`.
4. Rewrite the three demo skeleton endings:
   - `good` -> `valence=positive, kind=success`
   - `completion` -> `valence=positive, kind=completion`
   - `neutral` -> `valence=neutral, kind=discovery`
   - `failure` -> `valence=negative, kind=setback`
   - `death` -> `valence=negative, kind=death`
   Add `metadata.topology` to each skeleton (3-5 lost-mitten: time_cave or
   branch-and-bottleneck per its graph; 10-13 clocktower: branch_and_bottleneck;
   16+ sunken-signal: branch_and_bottleneck) and `safety_scope` on any peril nodes.
5. Complete `band_profile.py` for all six bands.
6. DB-persisted `StorybookVersion` rows: the project is pre-launch and is expected to
   hold no v1.0 stories. The plan includes a **check step** (query for any persisted
   stories) rather than a data migration; if any exist, they are re-generated or
   hand-migrated before merge. This is recorded as a `#CRITICAL: data integrity`
   assumption to verify, not assumed silently.

## 9. Implementation phasing

The spec covers everything; the build is ordered because each phase depends on the
prior one:

1. **Schema 2.0**: enums, `Ending`, `Topology`, `SafetyScope`, `ContentFlagLevel`
   extension, `StoryMetadata.topology`, `Node.safety_scope`; `schema_export`;
   migrate the 3 skeletons; tests.
2. **Band profile**: `band_profile.py` for all six bands; refactor
   `layer1.band_budget()` to read it; tests.
3. **Policy gate**: `policy.py` (PL-15..PL-18) + topology classifier;
   wire into `run_gate`; extend `GateResult.blocked`; tests.
4. **Review-agent layer**: deterministic pre-filters, reviewer interfaces, per-band
   checklists, model-tier routing, SAFE-14 fill. The agents are the largest phase
   and may be split again at planning time.

## 10. Testing and quality

- Unit tests per new enum/model invariant, per band profile, per PL rule (pass and
  fail cases), and for the topology classifier against the three skeletons.
- Each PL rule has an explicit young-band fail case (e.g. a 3-5 story with a `death`
  ending must be blocked by PL-15).
- The three migrated skeletons must pass `load_skeleton` and the full gate.
- Coverage stays at or above the project's 80% line / 70% branch minimum; the
  validator package is critical-path and targets 90%.
- RAD markers required on the gate and migration paths (data integrity at the
  Pydantic boundary; the persisted-story check in section 8).
- `ruff`, `basedpyright` strict, `bandit`, `pip-audit`, and pre-commit all green
  before each phase commits.

## 11. Acceptance criteria

- `Ending` carries `valence` + `kind`; no free-form `type` remains in code or
  skeletons.
- `band_profile.py` defines all six bands and is the single source for budgets and
  policy; `_BUDGETS` is gone.
- `run_gate` blocks on PL-15..PL-18; a 3-5 story containing a `death` or `capture`
  ending is rejected with a PL-15 finding.
- Declared topology is verified against the graph (PL-18) for all three skeletons.
- The review-agent architecture (roster, scopes, tiers, per-band checklist contract,
  SAFE-14 seam) is specified well enough to be turned into its own implementation
  plan.
- Full suite green; schema version is `2.0`.
