---
title: "Story Runtime Semantics v1"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Define the canonical execution model shared by the player and the validator for Tier-2 story traversal."
tags:
  - planning
  - specifications
  - functional
component: Development-Tools
source: "tech-spec.md section 'Story Runtime Semantics v1'"
---

# Story Runtime Semantics v1

> **Status**: Accepted (cross-signed) | **Version**: 1.2 | **Updated**: 2026-07-26
> **Scope**: Tier-1 and Tier-2 stories
> **Binding on**: Player (TypeScript/XState) and Validator (Python/networkx)

---

## Purpose

Tier-2 stories behave like small programs. The player and the validator must share one
execution model or they will disagree on the one path nobody tested. This document defines
that shared model normatively. Every statement in a numbered rule below is binding; no
implementation may deviate without an ADR and a revision to this document.

---

## 1. Transition Order

**Normative rule**: on every choice selection, apply effects in this exact order:

1. Evaluate the choice `condition` against the current `var_state`.
2. If the condition is true (or absent) and the choice is selected, apply the choice `effects`
   to `var_state`.
3. Set `current_node` to the choice `target`.
4. Apply the target node's `on_enter` effects to `var_state`.

This order is canonical. Saves, tests, and the validator all assume it. No implementation may
reorder steps 2 and 4 or insert additional state-mutation points between them.

**Rationale**: choice effects happen "on the way out" of the current node; `on_enter` effects
happen "on the way in" to the target node. Swapping the order changes observable state for
subsequent conditions.

---

## 2. Effect Application and `once: true` Semantics

**Normative rule**: `on_enter` effects run on every visit to a node unless the effect carries
`once: true`.

An effect marked `once: true` applies exactly on the first entry to its node. Subsequent visits
to the same node skip that effect. The record of which nodes have been entered at least once is
kept in the **implicit visit set**, stored as part of `var_state` (see Section 5: Save Format).

**Example**: `once: true` is appropriate for "you find the lantern." Re-entering the lantern
room on a later pass should not set `has_lantern` again (it is already true), but an `inc`
marked `once` on a limited-supply node must also not apply twice.

**Implementation requirement**: both the Python and the TypeScript evaluators must implement
the visit set. An implementation that applies `once` effects on re-entry is incorrect.

---

## 3. Variable Bounds

**Normative rule**: `inc` and `dec` effects are bounded by the `min` and `max` declared on the
variable.

**Schema invalidity**: a story where any reachable transition can push a variable past its
declared `min` or `max` is schema-invalid and **fails validation**. The validator rejects it;
silent clamping is not a valid response to a bound violation detected statically.

**Runtime defensive fallback**: the runtime clamps `inc`/`dec` at `min`/`max` as a last-resort
defensive measure only. A clamp at runtime is treated as a bug in the story or the generator,
not as designed behavior. Authors and the generator must not rely on runtime clamping to satisfy
game logic.

**Verification**: the Layer-1 validator (rule L1-6) checks that no reachable transition exceeds
declared bounds. A story must not reach `published` state if this check fails.

---

## 4. Choice Visibility

**Normative rule**: a choice whose `condition` evaluates to false is **hidden** from the reader.
It is not shown in a disabled or greyed-out state.

**Rationale**: younger readers should not see locked options they cannot explain. Showing
"[locked: needs lantern]" violates the design principle that the UI presents only valid actions.

**Implementation requirement**: both the PWA player and the validator's configuration walk must
use identical condition evaluation. A choice invisible to the validator must be invisible to the
player; a choice visible to the validator must be visible to the player. Divergence here
constitutes a conformance failure (see ADR-006 and Section 10: Cross-Sign).

---

## 5. Save Format

**Normative rule**: a save is a point-in-time snapshot. It stores exactly:

| Field | Type | Description |
| --- | --- | --- |
| `current_node` | String | Node id at the moment of save |
| `var_state` | Object | Full variable name-to-value map at the moment of save |
| `path` | Array of String | Ordered list of node ids visited, from `start_node` to `current_node` |
| `visit_set` | Set of String | Set of node ids entered at least once (drives `once: true` logic) |
| `save_slots` | Object | Named save-slot map (slot name to snapshot; may be empty) |
| `version` | Integer | The Storybook `version` this save was taken against |
| `state_revision` | Integer | The server-side revision counter at save time |

v1 uses snapshots, not an event log. A snapshot carries no history of *how* variables reached
their values, so no intermediate state can be reconstructed by inverting effects. Replaying
`path` forward from a known origin is a different operation and is permitted: see Section 6.

> **Note (2026-07-26)**: `save_slots` is client-writable and server-persisted but is the only
> field of this table omitted from `validate_reading_state`
> (`src/cyo_adventure/api/reading.py`), which defeats the anti-forgery intent stated two lines
> above it in that file. It is inert while nothing restores from a slot. Tracked as a defect;
> ADR-024 Decision 6 explains why any future replay origin must not repeat the pattern.

**Constraint**: a save taken against `version` N cannot be used with `version` N+1 (see
Section 8: Version Pinning).

---

## 6. Backtracking by Forward Replay

> **Revised 2026-07-26 (v1.2) by [ADR-024](./adr/adr-024-bounded-backtracking-path-replay.md).** This section
> previously read "there is no 'back' button in v1", on the rationale that backtracking "requires undoing
> effects, which demands an event-log model rather than a snapshot model". A back button had meanwhile shipped
> (`frontend/src/reader/Reader.tsx`), so the document and the product disagreed. The rationale is what was
> wrong: the shipped mechanism never undoes anything, so the snapshot model of Section 5 is preserved and no
> event log is needed. The prohibition is replaced by the rules below.

**Normative rule**: a reader may return to an earlier point on their own recorded path, and any such state is
produced **only** by replaying `path` forward from a known origin with known initial variables. Reversing an
effect, decrementing a counter, or otherwise computing an inverse is prohibited. A state not reachable by
forward replay is not reachable at all.

**Why this preserves the snapshot model**: a save records `path` (Section 5), so every prefix of that path is
replayable from the origin. Re-deriving an earlier state needs no history of *how* variables changed, only the
ordered choices that changed them.

**Availability is fail-closed.** Backtracking is available exactly when there is at least one recorded choice
(`path.length > 1`) **and** the recorded path replays faithfully, reproducing the live state. Otherwise the
reader gets no backtracking rather than an incorrect one. This holds for a continuation read, whose origin
variables are not recoverable: see ADR-024 Decision 6, which keeps continuation backtracking disabled and
states what enabling it would require.

**What rewinds**: `current_node`, `var_state`, `path`, and `visit_set`, being the product of the choice
history. **What carries over unchanged**: `state_revision` (owned by the server's concurrency counter) and
`save_slots` (owned outside the choice history). `version` is unchanged and Section 8 pinning still applies.

**Server impact**: none. A replayed shorter state is indistinguishable from having made fewer choices and
satisfies the existing structural floor, so backtracking introduces no server contract. The cross-sign for this
section is player-only.

A bounded multi-hop retry affordance is permitted under ADR-024 Decision 5, as a control distinct from the
single-step in-story one.

---

## 7. Endings

**Normative rule**: an ending node is identified by its stable `ending.id`. The `ending.id`
must be stable across prose edits and schema-compatible revisions. The "endings found" tracker
records `ending.id`, not the node id or the ending title, so it survives prose changes that do
not change the ending identity.

**Structural requirement**: an ending node has `is_ending: true`, exactly zero `choices`, and
a non-empty `ending` block containing a unique `ending.id`, a two-axis `valence` and `kind`,
and a `title` (two-axis endings per [ADR-001](./adr/adr-001-story-format-json-storybook.md)).

---

## 8. Version Pinning for In-Progress Reads

**Normative rule**: a reader session is pinned to the Storybook `version` it started on.
Publishing a new version of a Storybook does not mutate or invalidate an active read session.

**Mechanism**: the `reading_state` row carries the `version` integer alongside `current_node`
and `var_state`. The API rejects a `PUT` if `version` in the request does not match the version
the session began on (returns 409). The client offers the reader the choice to start the new
version or continue the current one.

**Invariant**: a save is always played back against the same version it was taken against.

---

## 9. Choice ID Uniqueness

**Normative rule**: every `choice.id` must be unique within a story (across all nodes and all
versions of the story schema). Choice ids are stable identifiers used for audit, debugging,
and analytics.

**Enforcement**: the Layer-1 validator (rule L1-2) checks uniqueness. A story with duplicate
choice ids fails validation.

---

## 10. Cross-Sign

This document is **binding on both the player implementation and the validator implementation**.
Neither may implement a behaviour that contradicts a normative rule above without first revising
this document and obtaining owner sign-off.

Sections that affect both implementations and require explicit agreement between the player owner
and the validator owner before Phase 1 begins:

- Section 1: Transition Order
- Section 2: `once: true` semantics and the visit set
- Section 3: Bound rejection (schema-invalid, not silently clamped)
- Section 4: Hidden (not disabled) choices
- Section 5: Save format fields (particularly `visit_set`)

**RESOLVED: cross-sign satisfied.** The player and validator implementations shipped in Phase 1
(merged) and are held to this model by the shared conformance corpus; Phase 4a is feature-complete
as of 2026-07-03. The cross-sign gate that once blocked Phase-1 implementation is closed. Any
future change to a normative rule above still requires owner sign-off and a version bump to this
document.

---

## Related Documents

- [Tech Spec: Story Runtime Semantics v1](./tech-spec.md#story-runtime-semantics-v1)
- [Validator Rule Catalog](./validator-rules.md)
- [Condition Evaluator Specification](./condition-evaluator-spec.md)
- [ADR-006: In-house condition evaluator](./adr/adr-006-conditions-inhouse-evaluator.md)
