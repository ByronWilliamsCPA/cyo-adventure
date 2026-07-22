<!--
SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
SPDX-License-Identifier: MIT
-->

# WS-8 anti-clone floor recalibration (proposed ADR-020 amendment)

> **Status: PROPOSAL, awaiting owner sign-off.** No floor value or acceptance
> clause changes until this is approved. This document is the evidence base and
> the proposed amendment text; on approval it becomes an amendment to
> `adr-020-mutation-derived-skeletons-and-catalog-growth.md` and drives a small,
> reviewed change to `mutation/floors.py`, the baseline JSON, and the calibration
> script.

## 1. Decision requested

The WS-8 catalog flywheel (D1-D4, delivered) cannot promote any automated
candidate, because every bounded mutation is rejected by the `TAU_STRUCT`
anti-clone floor. This proposes to fix the floor's *scope* (not to weaken it):
retire the mutant-to-parent distance clause that is mis-calibrated, and promote
the in-cell anti-duplication clause (`TAU_CELL`) to the real guarantee, applied
against every in-cell tree including the parent, at a calibrated value. The
owner decides the final `TAU_CELL` value from the tradeoff table in section 5.

## 2. The problem (measured)

Every WS-8 mutation candidate is discarded at acceptance clause 2 of design 4.6
(`structural_distance(parent, candidate) >= TAU_STRUCT`, `TAU_STRUCT = 0.332507`).

Measured `structural_distance(parent, best-mutant)` with the strongest available
generation (largest-donor-subtree graft, prune-and-graft replace):

| Parent (nodes) | Best mutant parent-distance |
| --- | --- |
| the-sleepy-little-star (17) | 0.117 |
| puddle-jumping-day (19) | 0.066 |
| the-clover-and-the-butterfly (20) | 0.029 |
| the-teddy-bears-picnic (29) | 0.086 |
| baking-day-with-grandma-vole (30) | 0.091 |
| the-big-red-balloon (32) | 0.082 |
| the-school-garden-mystery (35) | 0.084 |
| the-lantern-festival (36) | 0.038 |
| the-snow-day-expedition (38) | 0.050 |
| the-cave-of-echoes (64, high envelope headroom) | 0.316 |

Achieved mutant parent-distance: **min 0.029, median 0.082, max 0.117** across
the nine small trees; a rare high-headroom tree reaches **0.316**. **0 of 10
clear `TAU_STRUCT` (0.333).**

This is not a generation-quality gap that a better search closes. It is
structural: normalized graph-edit distance needs roughly a third of a tree to
change to reach 0.33, but the WS-5 operators are bounded by design (a graft may
not exceed the cell node-count maximum; a prune may not drop below the minimum
or strand nodes; a swap is envelope-neutral and near-isomorphic; chains are
capped at three ops). A bounded mutation of one tree therefore stays close to
its parent by construction, except when a tree has unusual envelope headroom to
absorb a large graft.

## 3. Root cause: a sibling-pair percentile applied to parent distance

`scripts/calibrate_mutation_floors.py` derives `TAU_STRUCT` as the **25th
percentile of same-cell hand-authored *pairwise* structural distances** (design
4.6 / OQ-3). From the committed baseline (`ws5_floor_baseline.json`,
`same_cell_structural`, n=67 pairs):

| statistic | value |
| --- | --- |
| min | 0.0009 |
| p05 | 0.2306 |
| **p25 (= TAU_STRUCT)** | **0.3325** |
| median | 0.3956 |
| max | 0.5766 |

That distribution answers "how different are two *independently authored*
trees in the same cell?" The acceptance gate then applies it to a different
question: "how different is a tree from a *bounded mutation of itself*?" The two
distributions are essentially disjoint: mutants live in **0.03-0.32**,
independent siblings in **0.23-0.58**. Using the sibling-pair p25 as the
parent-to-mutant floor rejects ~100% of mutants. The metric is sound; its
application to the parent-distance clause is the error.

`TAU_CELL`, the clause that actually protects against duplicates
(`min over in-cell siblings of structural_distance >= TAU_CELL`), was calibrated
to the observed same-cell **minimum** (0.0009 -- itself a near-duplicate pair the
catalog already contains) and clamped up to 0.01. At 0.01 it only rejects
byte-near-identical trees, so it is too weak to be the primary anti-duplication
guarantee on its own.

## 4. Proposed model: two correctly-scoped floors

The anti-clone design wants two guarantees. Re-scope them to what is actually
measurable for a mutation:

1. **Anti-no-op (keep, unchanged).** Design 4.6 clause 1 already requires
   `structure_fingerprint(candidate) != structure_fingerprint(parent)`: a mutant
   must change the structural fingerprint (topology / ending set), so a pure
   re-labeling or a no-op never counts as a new tree. This stays.

2. **Anti-duplication (the real guarantee): a strengthened `TAU_CELL`, applied
   against every in-cell tree INCLUDING the parent.** The parent is itself an
   in-cell tree, so "the mutant is not a near-duplicate of any existing in-cell
   tree" *subsumes* "the mutant is meaningfully different from its parent." This
   replaces the mis-scoped parent-distance clause with a single, correctly-scoped
   one, and it is the clause that genuinely prevents catalog clones (a mutant too
   close to ANY existing tree -- parent or sibling -- is rejected).

3. **Retire the mutant parent-distance `>= TAU_STRUCT` clause** (design 4.6
   clause 2) for the mutation origin. `TAU_STRUCT` is kept in the baseline as the
   documented hand-authored cross-tree diversity *target* (and remains available
   for any future comparison of independently-authored trees), but it no longer
   gates mutants. For WS-6 fresh trees (no parent) this clause was already
   vacuous (D5 / design 7.2), so retiring it unifies the two origins.

Tier-2 state variation (`TAU_STATE`, the M5-only path) is unchanged.

Net acceptance for a mutant becomes: passes the full deterministic gate; changes
the structural fingerprint; and is at least `TAU_CELL` from every in-cell tree
including its parent. No stage is removed; the parent-distance stage is
re-scoped into the in-cell stage at a calibrated threshold.

## 5. Calibration and the tradeoff (owner's call)

Proposal: re-derive `TAU_CELL` not as the raw same-cell minimum (which is a
degenerate near-duplicate) but as a deliberate anti-duplication floor, chosen
from the tradeoff below. Candidate values, their yield against the measured
mutant distribution, and their duplicate-rejection margin over the known 0.0009
near-duplicate pair:

| TAU_CELL | Rejects 0.0009 clone? | Margin | Mutant yield (small trees, median 0.082) | Reading |
| --- | --- | --- | --- | --- |
| 0.01 (today) | yes | 11x | ~all mutants pass vs parent | too weak; admits thin near-clones |
| **0.05 (recommended)** | yes | **53x** | roughly half+ (those >= 0.05) | a mutant is >= ~5% structurally changed |
| 0.08 | yes | 84x | ~half | modest variation floor |
| 0.10 | yes | 105x | fewer (high-headroom trees) | closer to "clearly distinct" |
| 0.2306 (sibling p05) | yes | 243x | ~none except cave | back to near-zero yield |

**Recommendation: `TAU_CELL = 0.05`**, applied against parent + siblings. It
rejects the known near-duplicate with a 53x margin, admits the mutants that
represent a genuine structural change (a grafted subtree, a re-mapped ending
set, a pruned branch), and excludes the thinnest edits. The owner may pick a
higher value for a stricter "clearly distinct" bar at the cost of yield; this is
a catalog-curation judgment, which is the right place for it (see section 6).

The exact value would be committed through the calibration script and the
baseline JSON, with the derivation note updated, so it stays reproducible and
drift-guarded exactly as today.

## 6. Why this is a quality bar, not a safety weakening

The anti-clone floor is a **catalog-curation** threshold, not a child-safety
gate. Lowering the parent-distance bar cannot expose a child to unsafe content,
because every promoted tree still passes, in order:

1. the full deterministic `run_gate` (topology, safety, reading level, band
   profile) -- unchanged;
2. moderation review -- unchanged;
3. **human structure approval** -- the D4 `skeleton-promotion` draft PR, which a
   human must review and merge (ADR-020 decision 4); a reviewer who judges a
   mutant too similar to its parent to be worth adding simply declines the PR;
4. **human story approval** (ADR-005) on every story later generated from the
   tree.

So the only thing the parent-distance bar controls is whether an *automated
candidate is offered to a human reviewer at all*. Setting it to a sibling-pair
percentile means no candidate is ever offered; setting it to a calibrated
in-cell anti-duplication value means genuine variations are offered and the
human makes the final distinctness call. This is a curation calibration,
appropriately owner-decided, consistent with WS-5 principle 4 ("discard, never
weaken"): we are not weakening a safety gate, we are correcting a mis-scoped
quality metric.

## 7. Implementation impact if approved (all behind sign-off)

- `mutation/floors.py`: `structural_floor_reason` drops the parent-distance
  clause; the in-cell clause compares against parent + siblings at the new
  `TAU_CELL`. (`M5`-only shape-unchanged mutants keep the `TAU_STATE` path.)
- `docs/planning/ws5_floor_baseline.json` + `scripts/calibrate_mutation_floors.py`:
  new `TAU_CELL` derivation + value; `TAU_STRUCT` retained as documentation.
- `mutation/acceptance.py`: the clause 2 wiring, if it references parent-distance
  directly.
- `adr-020-...md`: an amendment section recording this decision and its evidence.
- Tests: the anti-clone floor tests updated to the re-scoped clauses; a new
  fixture proving a near-duplicate (< new `TAU_CELL`) is still rejected and a
  genuine variation is admitted.
- WS-8 D2 strategy: no change required, but the flywheel now yields promotable
  candidates for the cells whose mutants clear the new in-cell floor; D7 metrics
  report the realized yield per cell.

## 8. Open questions for the owner

- **OQ-A (the value).** `TAU_CELL = 0.05` (recommended) or a stricter value?
  Section 5 is the tradeoff.
- **OQ-B (recalibration basis).** Derive `TAU_CELL` as a fixed owner-chosen
  value (transparent, judgment-based) or as a percentile of a freshly measured
  mutant-distance distribution (data-driven, but the distribution is generation-
  dependent)? Recommendation: fixed owner-chosen value, documented, because it
  is a curation bar and a data-derived value would drift with operator changes.
- **OQ-C (scope).** Apply the re-scoped floor to the mutation origin only (this
  proposal), leaving hand-authored catalog additions and any future WS-6 fresh
  trees under their own (parentless) acceptance, which is already how D5 frames
  it. Recommendation: yes, mutation-origin only.
