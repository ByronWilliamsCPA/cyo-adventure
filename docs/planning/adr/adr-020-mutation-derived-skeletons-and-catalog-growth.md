---
title: "ADR-020: Mutation-derived skeletons and catalog growth"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Ratify the WS-5 catalog-growth model before mutation-derived trees are
  promoted at scale: a promoted mutant is a first-class catalog skeleton with its
  own slug, contract, and selection weight and no inherited trust; provenance lives
  in a skeletons/<band>/<slug>.lineage.json sidecar with the catalog scanner's
  sidecar skip generalized; the gate is byte-identical plus promotion-only anti-clone
  and state floors that can only reject; human structure approval is the skeletons/
  PR review, distinct from ADR-005 story approval; a mutant inherits its parent's
  (band, length, style) cell; and mutants of parameterized parents ship contracts
  while mutants of contract-less parents land contract-less at parity."
tags:
  - planning
  - architecture
  - decisions
  - generation
  - validation
  - diversity
---

# ADR-020: Mutation-derived skeletons and catalog growth

> **Status**: Accepted (2026-07-20; drafted at WS-5 D8 with the composed-chain
> promotion bundle below as the evidence exhibit, ratified by the owner after WS-5
> merged. The decision set governs how mutation-derived trees are promoted at scale;
> the six decisions below are now binding on WS-6 (fresh-generation feed) and WS-8
> (catalog flywheel).)
> **Date**: 2026-07-20
> **Relates to**: [ADR-019](./adr-019-parameterized-skeletons-theme-contracts.md)
> (parameterization varies content on a fixed structure; ADR-020 governs changing
> the structure itself and growing the catalog from non-hand-authored sources, the
> question ADR-019 only gestured at), [ADR-011](./adr-011-story-scale-framework.md)
> (the constraint grammar is the frozen safety object; every operator perturbs only
> grammar clauses it declares and the gate re-proves every result),
> [ADR-005](./adr-005-mandatory-human-approval.md) (human story approval still gates
> every published story; ADR-020's human structure approval is a distinct, earlier
> step over the skeleton, not the story), [ADR-001](./adr-001-story-format-json-storybook.md)
> (the Storybook schema is unchanged; lineage lives outside the story document).
> Design spec: `docs/planning/ws5-structure-state-variation-design.md` (section 8
> is this ADR's decision source; sections 4-6 the operators, harness, and bundle).

## TL;DR

WS-5 grows the skeleton catalog by mutating already gate-verified trees with cheap,
deterministic operators (M1-M5), offline and catalog-time only. A mutant is not a
special object: once promoted it is an ordinary catalog skeleton with a new slug,
its own theme contract, and ordinary selection weight, and it earns catalog
membership exactly the way a hand-authored skeleton does, through the byte-identical
`validator/` gate plus a stricter WS-5 acceptance harness. Nothing is inherited from
the parent except the cell. Provenance (parent slug and content hash, the operator
chain with parameters and seeds, the acceptance digest) is recorded in a
`skeletons/<band>/<slug>.lineage.json` sidecar, and the catalog scanner's existing
`*.contract.json` skip is generalized so lineage is never mistaken for a selectable
skeleton. The gate is identical in both directions (no novelty exception): the WS-5
additions (an anti-clone structural distance floor, a state-signature floor, and
ending-coverage / clock re-proof for Tier-2) are promotion criteria that can only
reject, never admit. A human structure-approval step, the `skeletons/` PR review, is
named explicitly and kept distinct from ADR-005 story approval; there is no
auto-merge for skeleton promotion. A mutant inherits its parent's `(band, length,
style)` cell in v1, and mutants of parameterized parents ship contracts while mutants
of contract-less parents land contract-less at parity until the WS-2 Tier-2 wave.

## Context

### Where the catalog stands

`skeletons/` holds 59 gate-verified trees (56 production, 3 MVP seeds) across six
bands, 45 with WS-2 theme-contract sidecars (ADR-019). Every skeleton is re-gated at
load, so the mutation substrate is by construction a set of trees the gate has already
accepted. The cost of a new verified tree today is the cost of authoring 10 to 155
nodes of beats guidance plus structure plus review; that cost is why cells hold 5 to 12
skeletons and why WS-4's `CATALOG` saturation escalation currently terminates in a log
line with nothing to consume it. Meanwhile the catalog embodies sunk, human-reviewed
value. Mutation converts that sunk value into new trees at a fraction of authoring
cost, with the gate re-proving safety mechanically.

### What WS-5 D1-D7 built

The pure operator framework (`ops`, `subtree`, `identity`), the five operator families
(M1 sibling-subtree swap, M2 ending re-map within a valence class, M3 prune/graft
within the envelope, M4 vary decisions-per-path, M5 Tier-2 state variation), the
acceptance harness (`acceptance.py`) that re-runs the unchanged gate and adds the
Tier-2 single-walk coverage/clock re-proof and the contract-acceptance stage, and the
calibrated anti-clone floors (`floors.py`, `TAU_STRUCT`/`TAU_CELL`/`TAU_STATE` in a
committed baseline). D7 confirmed the expected shape: a single operator usually leaves
a mutant below `TAU_STRUCT` (M1 preserves every aggregate shape feature, M2 is
composition-only), so the highest-value mutants pair a structural op with an outcome
re-map or a second structural move, which motivates bounded operator chains (OQ-7).

### What ADR-019 does not cover, and WS-5 needs ratified

ADR-019 governs how content varies on a fixed structure. WS-5 changes the structure
itself and grows the catalog from non-hand-authored sources, which ADR-019 only
gestures at ("the catalog flywheel can promote new trees through the same
neutralize-and-contract machinery"). The decisions below have no ratified home; without
this ADR they live only in the WS-5 workstream design, which is exactly the
unrecorded-model failure ADR-011's context section warns against.

### The constraint the model must not violate

No mutant may reach a child, or even the catalog, except through the byte-identical
gate plus a reviewed human PR. The frozen safety object is the ADR-011 constraint
grammar, not the 59 graphs: WS-5 varies trees strictly inside the grammar, the gate
verifies every result, and a gate failure discards the mutant, never weakens the gate.
The WS-5 additions are strictly one-directional (reject-only).

## Decision

### 1. Mutants are first-class catalog citizens

A promoted mutant is a new skeleton: new slug, own contract, ordinary selection weight,
no runtime linkage to its parent. Trust is earned per tree through the identical gate
plus the stricter WS-5 acceptance; nothing is inherited. Selection, generation, and
publish see only promoted skeletons and cannot tell a mutant from a hand-authored tree.

### 2. Provenance is recorded, out of the story document

`StoryMetadata` is `extra="forbid"` and reader-facing, so lineage lives in a
`skeletons/<band>/<slug>.lineage.json` sidecar: parent slug and content hash, donor
slugs, the operator chain with parameters and seeds, the tool version, and the
acceptance digest. The catalog scanner's sidecar skip is generalized from
`*.contract.json` to a shared `is_sidecar` predicate (a suffix set) so lineage is never
treated as a selectable skeleton and a future sidecar type is a single edit. This
mirrors ADR-019 Decision 2's sidecar reasoning: lineage must version and review
atomically with the tree it explains (OQ-1).

### 3. The gate is identical, plus promotion-only additions

No novelty exception in either direction. Mutants pass the byte-identical gate that a
hand-authored skeleton and its contract face; the WS-5 additions (the anti-clone
structural distance floor `TAU_STRUCT`/`TAU_CELL`, the state-signature floor
`TAU_STATE`, and the Tier-2 ending-coverage and clock re-proof) are promotion criteria
that can only reject a candidate, never admit one the gate blocked. Composed (future)
and fresh-generated (WS-6) trees inherit the same bar.

### 4. Human structure approval is the skeletons/ PR review

Promotion is a reviewed `skeletons/` PR, performed by the owner or a delegated admin on
the promotion bundle's evidence (diagram, acceptance transcript, sample fill, lineage).
It is deliberately distinct from ADR-005 story approval (which continues to gate every
published story) and from ADR-019's no-new-theme-review posture (themes still need no
human step; structures always did need one, and this names it). No auto-merge for
skeleton promotion PRs (OQ-5). WS-8 automation, when built, prepares PRs; humans merge
them.

### 5. Cell inheritance

A mutant declares its parent's `(band, length, style)` cell verbatim in v1.
Cross-cell derivation (for example a prune/graft moving the node count across a length
envelope boundary) changes the clocks, floors, and teen-band style semantics at once
and is a future ADR-020 amendment with evidence, not an operator option (OQ-4).

### 6. Contract parity

Mutants of parameterized parents ship a mutated `.contract.json` (surviving slots kept,
pruned-only slots dropped, grafted slots imported under renamed `M<k>_<SLOT>` ids,
`default_binding` complete, `contract_version` reset to 1) that passes the WS-2
acceptance runner, including the band-mandatory denylist floor unioned in regardless of
contract content. Mutants of the contract-less Tier-2 parents land contract-less at
parity with their parent until the WS-2 Tier-2 migration wave, when they migrate in the
same wave as ordinary skeletons (OQ-2).

## Consequences

### Positive

- The WS-4 `cell_theme_saturated` signal gains a mechanism to consume: saturated cells
  can be grown from sunk, human-reviewed catalog value at a fraction of authoring cost.
- Every promotion carries a machine-readable, replayable provenance record, so any
  promoted mutant re-derives byte-for-byte and a bundle built from a since-changed
  parent hard-fails the `--verify-bundle` check before a PR is opened.
- Safety is unchanged: the gate is byte-identical, the floors are reject-only, and a
  promoted mutant still runs the full fill -> gate -> moderation -> ADR-005 chain for
  every story generated from it.
- The model generalizes: WS-6 fresh-generated and a future composed grammar tree
  inherit the same promotion bar and the same lineage sidecar.

### Negative / accepted costs

- Catalog bloat: many promoted mutants per cell flatten selection weights and grow the
  contract-maintenance surface. Governed by promoting on demand (the WS-4 saturation
  signal) rather than on supply.
- Reviewer load: each promotion is a human PR review. Distinct from and additive to
  ADR-005 story review; the bundle's diagram and sample-fill exist to make it cheap.
- Floor gaming: `structural_distance` is a feature-vector metric a chain could learn to
  move without moving perceived structure. Mitigated by the human seeing the diagram and
  revisitable when WS-0's judge-model phase can score tree-pair distinctness.
- A new sidecar file class (`*.lineage.json`) in `skeletons/`, accepted as the atomic-
  versioning cost already paid for contracts.

### Evidence exhibit: one end-to-end composed-chain promotion bundle

Produced at D8 with `scripts/mutate_skeleton.py` and verified; the raw bundle lives in
gitignored `out/mutations/` (promotion into `skeletons/` is a human PR), so the evidence
is captured here.

- **Parent:** `the-cave-of-echoes` (band 8-11, short, prose, Tier-1, 64 nodes, 16
  endings, `time_cave`), a parameterized parent with a 72-slot theme contract.
- **Chain (2 ops, OQ-7 bounded):** M3 graft (donor `the-robot-fair-sabotage`, subtree
  `n_lockup`, 36 nodes, onto host decision `la_crystal_take`, seed 0), then M2 ending
  re-map within a valence class (seed 3). A structural graft paired with an outcome
  re-map, the design's stated highest-value pairing.
- **Result:** a 100-node mutant. `structural_distance(parent, mutant) = 0.3362`, at or
  above `TAU_STRUCT = 0.332507` (clears the parent anti-clone clause); minimum distance
  to any in-cell sibling `= 0.1318`, at or above `TAU_CELL = 0.01` (clears the in-cell
  clone clause). `TAU_CELL` is the documented clamp floor: the current catalog has two
  near-identical in-cell siblings whose observed distance (0.000947) would otherwise
  drive the threshold toward a clone-admitting zero, so the calibrator clamps it up to
  the safe minimum (thresholds live in the committed
  `docs/planning/ws5_floor_baseline.json`, re-derivable by
  `scripts/calibrate_mutation_floors.py`). The graft imports the donor's referenced
  slots under renamed `M<k>_` ids into a fresh mutant contract that passes stage-4
  acceptance.
- **Re-guidance:** the chain emitted 9 re-guidance items (the graft-seam choice label,
  the graft-root entry beats, and the M2-affected ending titles, leaf beats, and
  advisory upstream approaches). With author-supplied resolutions for all 9, the mutant
  is fully resolved and would-be-promotable, then clears the anti-clone floor.
- **Acceptance:** every stage passed, in order: 0 preconditions, 1 gate (the unchanged
  full gate), 2 cell assertion, 3 structural anti-clone floor, 4 contract acceptance.
  The stage-5 sample fill (deterministic mock provider, default binding) passed its own
  gate cleanly, structurally unblocked.
- **Bundle:** the writer emitted the mutant shell, the mutated contract, the
  `lineage.json` sidecar (op chain `[M3 seed 0, M2 seed 3]`, donor
  `the-robot-fair-sabotage`, lineage version 1), the acceptance transcript, the
  re-guidance resolutions, the sample-fill evidence, and the structure diagram
  (`diagram.puml`; `.svg` when a SHA-verified PlantUML jar is available). `--verify-bundle`
  recomputed the parent content hash and matched the lineage record, confirming the
  bundle describes the live catalog parent.

## Alternatives considered

- **Lineage inside the story document.** Rejected: `StoryMetadata` is reader-facing and
  `extra="forbid"`; provenance is authoring metadata that must not travel to a child and
  must version atomically with the tree, which the sidecar gives (Decision 2).
- **Bundle/PR-only lineage with no new file class.** Rejected: lineage must survive the
  bundle's `out/` lifetime and be reviewable next to the promoted tree; the scanner
  change is one suffix check plus one test (OQ-1).
- **Advisory-first anti-clone floors.** Rejected: an advisory floor on a metric whose
  whole purpose is to keep the distinct-trees headline metric honest would let the count
  inflate silently. Floors are reject-only, so blocking-at-promotion carries no safety
  risk (OQ-3).
- **Single-operator mutants only.** Rejected: D7 showed single ops usually fall below
  `TAU_STRUCT`, and the highest-value mutants pair a structural op with an outcome
  re-map. Bounded chains (`<= 3` ops, recorded in the lineage `op_chain`) are the
  minimum that reaches genuinely distinct trees; acceptance runs on the final candidate
  regardless of chain length (OQ-7).
- **An in-app admin promotion surface instead of a PR.** Deferred to WS-8 if promotion
  volume ever warrants it; the catalog is already git-versioned and PR-reviewed, so PR
  review is the lowest-cost structure-approval step for WS-5 (OQ-5).
