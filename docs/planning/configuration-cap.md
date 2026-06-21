---
title: "Configuration Cap Worked Example"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Provide a concrete variable-budget example showing why the 100,000-configuration cap is safe and practical for Tier-2 stories."
tags:
  - planning
  - specifications
  - architecture
component: Development-Tools
source: "tech-spec.md Layer-2 rule 12; PROJECT-PLAN.md item P0-12"
---

# Configuration Cap Worked Example

> **Status**: Draft | **Version**: 1.0 | **Updated**: 2026-06-20
> **Scope**: Tier-2 stories only (Layer 2 validation)
> **Related rule**: [L2-12 in the Validator Rule Catalog](./validator-rules.md)

---

## Purpose

The Layer-2 state-space validator walks every reachable configuration `(node_id, var_state)`
in a Tier-2 story. Rule L2-12 aborts the walk and fails validation if the reachable set
exceeds the cap (default 100,000). This document works a concrete example to show that the
cap is generous relative to realistic stories, gives authors a practical variable budget, and
explains why the reachable set is always much smaller than the theoretical maximum.

---

## 1. The Rule

**Rule L2-12**: if the reachable configuration set exceeds 100,000, the validator fails
immediately with:

```
L2-12 cap: reachable configuration set exceeded the ceiling of 100000 configurations
in story '{story_id}' (state space too large; reduce variable count or tighten bounds)
```

The cap is a configurable default. Changing it requires an owner decision and a revision to
this document. The current default of 100,000 is chosen to keep validation under 2 seconds
for a 200-node story (see tech-spec performance targets).

---

## 2. Theoretical Upper Bound (Per Node)

The theoretical maximum number of configurations at a single node is the product of all
distinct values each variable can take.

**Example variable set**:

| Variable | Type | Range | Distinct values |
|----------|------|-------|-----------------|
| `has_lantern` | bool | false, true | 2 |
| `has_key` | bool | false, true | 2 |
| `courage` | int | 0..5 (min=0, max=5) | 6 |

Theoretical configurations per node: `2 * 2 * 6 = 24`

Across approximately 50 nodes: `24 * 50 = 1,200` theoretical configurations.

This is far below the 100,000 ceiling.

---

## 3. Why Reachable << Theoretical

The validator walks only **reachable** configurations, not the full Cartesian product. Several
factors reduce the reachable set below the theoretical maximum:

1. **Initial state constraint**: the walk starts from a single initial configuration
   `(start_node, initial_var_state)`. Variables begin at their `initial` values, so many
   var-state combinations are never produced (you cannot start with `courage = 5` if `courage`
   initialises to `1` and can only increment by 1).

2. **Effect topology**: variables change only via `inc`, `dec`, and `set` effects on specific
   transitions. Not every variable combination is reachable from any other; the graph of
   var-state transitions is sparse.

3. **Condition pruning**: a choice with `{ ">=": [{"var": "courage"}, 3] }` is only visible
   when `courage >= 3`. Configurations where that choice would be the only option and `courage
   < 3` are dead ends caught by L2-9, not additional reachable configurations.

4. **`once: true` effects**: a node whose `on_enter` effect has `once: true` can only
   contribute its effect once per path. The visit set tracks this, but it also means that
   re-visiting a node does not produce a new var-state (the var is unchanged), so re-entry
   collapses into the same configuration as the previous visit.

In practice, realistic Tier-2 stories with the budget below have reachable sets well under
1,000 configurations for a 50-node story.

---

## 4. Variable Budget Table

The following table gives authors and the generator a practical Tier-2 variable budget. Each
row shows a variable set, its theoretical maximum configurations per node, and the estimated
reachable total across a 50-node story (reachable is roughly 5% to 20% of theoretical in
practice).

| Bool count | Int count (range) | Theoretical/node | Estimated reachable (50 nodes) | Under cap? |
|------------|-------------------|-----------------|-------------------------------|------------|
| 2 | 1 (0..5) | 24 | ~120 to 480 | Yes |
| 3 | 1 (0..5) | 48 | ~240 to 960 | Yes |
| 4 | 1 (0..5) | 96 | ~480 to 1,920 | Yes |
| 2 | 2 (0..5 each) | 144 | ~720 to 2,880 | Yes |
| 4 | 2 (0..5 each) | 576 | ~2,880 to 11,520 | Yes |
| 6 | 2 (0..5 each) | 2,304 | ~11,520 to 46,080 | Yes |
| 8 | 2 (0..5 each) | 9,216 | ~46,080 to 184,320 | Borderline |
| 4 | 1 (0..9) | 160 | ~800 to 3,200 | Yes |
| 4 | 2 (0..9 each) | 1,600 | ~8,000 to 32,000 | Yes |
| 6 | 2 (0..9 each) | 6,400 | ~32,000 to 128,000 | Risky |

**Recommended safe budget for a typical 30-to-60-node Tier-2 story**: up to 4 booleans and
1 to 2 integers with range 0..5. This yields a theoretical maximum well under 1,000
configurations per node and comfortably under 50,000 reachable configurations, leaving a
large margin before the cap.

**Generator constraint**: the drafting guide should cap variable declarations at 4 booleans
and 2 integers for generated stories unless the story design explicitly requires more, and
the Tier-2 schema should enforce a soft warning at this threshold via the validator.

---

## 5. The Exhaustive Example: 2 Booleans + One int(0..5) Across ~50 Nodes

This is the reference example from PROJECT-PLAN.md item P0-12.

**Variables**:
- `has_lantern: bool`, initial `false`
- `has_key: bool`, initial `false`
- `courage: int`, initial `1`, min `0`, max `5`

**Theoretical maximum configurations per node**: `2 * 2 * 6 = 24`

**Theoretical maximum across 50 nodes**: `24 * 50 = 1,200`

**Estimated reachable configurations**: because `courage` starts at `1` and can only increment
or decrement one step at a time, and because `has_lantern` and `has_key` only change via `set`
effects at specific nodes, the reachable set is a small fraction of the theoretical maximum.
A story with this variable set will typically produce 50 to 300 reachable configurations total,
not 1,200.

**Distance to cap**: 1,200 theoretical / 100,000 cap = 1.2% of the ceiling. A story would
need to be roughly 80x larger than this example before the theoretical maximum even reached
the cap; actual reachable counts stay far lower.

---

## 6. What Triggers the Cap

A story approaches the cap when:

- Many boolean variables are declared (each doubles the per-node theoretical space).
- Integer variables have wide ranges (min=0, max=99 contributes 100 distinct values).
- The story is large (many nodes multiply the per-node space).
- Effects are dense (many transitions change many variables, making more var-states reachable
  from each other).

The cap protects validator runtime, not story quality. A story that triggers L2-12 is usually
one that has accumulated unnecessary variables or used integers where booleans would serve.
The fix is to reduce variable count, tighten bounds, or redesign the state model.

---

## 7. Rule Summary

| Condition | Outcome |
|-----------|---------|
| Reachable configurations <= 100,000 | Layer-2 walk completes; other L2 rules checked. |
| Reachable configurations > 100,000 | L2-12 fires; story fails with "state space too large". |

**The cap is 100,000 reachable configurations, not theoretical configurations.** A story with
a large theoretical space but tight effect topology may pass; one with a small theoretical
space but dense effects that explore the full product may fail.

---

## Related Documents

- [Validator Rule Catalog: L2-12](./validator-rules.md)
- [Story Runtime Semantics v1](./runtime-semantics.md)
- [Tech Spec: Validation Gate Layer 2](./tech-spec.md#validation-gate-deterministic-no-llm)
- [PROJECT-PLAN.md item P0-12](./PROJECT-PLAN.md)
