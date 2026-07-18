---
schema_type: planning
title: "Finding: choice labels in the structure fingerprint vs the fill contract"
description: "A WS-0/WS-1 finding surfaced while trying to grow the diversity panel with a
  second same-tree pair: structure_fingerprint counts choice labels as structure, but the
  automated fill rewrites labels, so the anti-template guard's same-tree precondition only
  holds for theme-neutral-label skeletons. Records the facts, the implication for WS-1, and
  the open decision."
tags:
  - planning
  - diversity
  - generation
status: open
owner: core-maintainer
component: Strategy
source: "Surfaced 2026-07-18 by the panel-monoculture growth attempt (reusing PR #297's
  the-harrowstone-keep gauntlet skeleton); verified against diversity/structure.py,
  diversity/leaf.py, generation/templates/fill.md, scripts/check_fill_integrity.py, the
  validator gate, and the committed cave panel fills."
---

# Finding: choice labels in the structure fingerprint vs the fill contract

## The facts (all verified in code, 2026-07-18)

1. `diversity/structure.py::_strip_leaf_content` removes only story `title`, node `body`,
   and `ending.title`. **Choice `label` is retained**, so it is part of
   `structure_fingerprint`. Two stories that differ in any choice label hash differently.
2. `diversity/leaf.py::anti_template_verdict` (the ATG, the one hard-gated diversity check)
   requires the two fills to share a `structure_fingerprint`; it raises `ValidationError`
   otherwise. It measures leaf distance over node **bodies** only.
3. `generation/templates/fill.md` (the automated Stage B' fill) instructs the model to
   replace "every choice label ... by final choice text matching the semantic intent of
   that choice's original label," and to adapt names/setting/theme to the request. So the
   automated fill **rewrites labels**.
4. `scripts/check_fill_integrity.py` strips only node `body` and requires the rest
   (ids, choices, targets, endings, variables, metadata, **labels**) byte-identical to the
   skeleton. It is a **standalone script**: nothing under `src/` imports it, and the
   runtime validator gate (`validator/`) does not compare a fill's labels to its skeleton.
   So label immutability is a manual/CI convention, not a runtime-enforced invariant.
5. Empirically, the committed cave panel fills preserve labels exactly: sea-caves vs
   space-station is **63/63 choice labels byte-identical** ("Follow the humming echo to the
   left."). The cave-of-echoes skeleton's labels are **theme-neutral**, so a reskin leaves
   them unchanged and the two fills share a fingerprint. PR #297's the-harrowstone-keep
   bakes ~30 plot proper nouns into its labels, so any reskin necessarily changes them.

## Implication

- A same-tree ATG pair (the panel's monoculture-breaking artifact, and WS-1's leaf-diversity
  check on two fills of one skeleton) is only well-defined when the two fills share every
  choice label. That holds for **theme-neutral-label skeletons** (cave), and for
  label-preserving fill paths (the pilot parameterization). It does **not** robustly hold
  for arbitrary automated production fills of a theme-specific skeleton, where labels move
  with the theme and the ATG would raise instead of comparing.
- This is a latent gap for WS-1 as written (`query.select_atg_comparison_partner` pairs two
  same-skeleton production fills and expects the ATG to run on them).

## The open decision (owner's call)

1. **Labels stay structure (lower-risk, no shipped-metric change).** Keep the fingerprint
   as-is and treat "theme-neutral choice labels" as a skeleton-authoring requirement for any
   skeleton meant to carry same-tree theme diversity. Retire the panel monoculture by
   adding a theme-neutral non-cave skeleton (author or find one) filled under two themes.
   Harrowstone is theme-locked and is used only as a cross-tree entry.
2. **Labels become leaves (principled, bigger change).** Strip choice labels in
   `_strip_leaf_content` (and fold them into the ATG's leaf distance), matching the
   leaves-on-a-tree definition (a label is branch-describing prose the reader reads). Makes
   the ATG robust to label rewrites (fixes the WS-1 gap) and unlocks harrowstone-style
   skeletons for reskin. Requires re-baselining the panel and aligning
   `check_fill_integrity` to the same convention.
3. **Defer.** Add harrowstone as a cross-tree pair now for topology/band structural
   coverage; leave the same-tree monoculture and the WS-1 gap for a later, explicit
   decision.

Recommendation: decide 1 vs 2 deliberately (it defines what "same tree" means for the whole
diversity system); either way, option 3's cross-tree addition is a safe interim step. This
document is the durable record so the finding is not lost; the chosen path updates
`story-flexibility-plan.md` (WS-1) and `ws0-phase2-harness-design.md` (section 7 risk 1).
