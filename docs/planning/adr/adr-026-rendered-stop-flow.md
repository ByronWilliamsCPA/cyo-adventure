---
title: "ADR-026: Rendered-stop flow of linear passages"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Implement the owner's every-stop-ends-in-a-choice ruling (design review D1) at the
  presentation layer: the reader flows consecutive single-choice nodes into one rendered stop for
  bands 8-11 and up, and keeps discrete pages with a choice cadence at 3-5 and 5-8, leaving the
  story graph and ADR-011's researched constants unchanged."
tags:
  - planning
  - architecture
  - decisions
  - player
---

# ADR-026: Rendered-stop flow of linear passages

> **Status**: Accepted (2026-08-01), owner ratification recorded in
> [design-review-kid-appeal-2026-08-01.md](../design-review-kid-appeal-2026-08-01.md) section 8
> (question Q1), on the evidence in that document's research appendix.
> **Cross-sign**: both player engines, the conformance corpus, reader UI. The storybook schema, the
> validator's structural rules, and ADR-011's scale constants are explicitly unchanged.
> **Relates to**: ADR-011 (constants preserved), ADR-024 (go-back semantics extended to stops),
> ADR-025 (any schema-visible additions ride minor versions).

## TL;DR

A **node is not a screen**. The reader composes **rendered stops**: for bands 8-11, 10-13, 13-16,
and 16+, consecutive single-choice non-ending nodes flow into one scrollable passage that ends at
the next real choice or ending, so every stop a child makes ends in a choice. For 3-5 and 5-8 the
reader keeps discrete pages (picture-book pacing) and the choice cadence is governed by the
per-band choice grammar (pending ratification as an ADR-011 amendment). The graph keeps its linear
beats, preserving the researched genre shape, the words-per-node ceilings, and every published blob.

## Context

The owner ruled that every page a child stops on must offer a choice (design review D1). Measured:
69% of non-ending nodes are single-choice; 0 of 61 skeletons would satisfy the ruling structurally.
But ADR-011 research-locks decisions-per-path at ~4-8 and mandates linear passages as the substance
carrier, anchored on measurement of the printed genre. The conflict is presentational: print flows
linear passages as continuous prose; our node-equals-screen rendering turns each one into a
"Continue" tap. External research (design review, research appendix) supports resolving at the
render layer: the strongest adaptation precedent (inkle's ink "gather" architecture) keeps linear
graph structure under a surface where nearly every stop ends in a choice, and no source supports
force-branching every node. For pre-readers the same research warns against interaction density
(comprehension competes with interaction), so young bands keep discrete pages with a cadence
instead.

## Decision

1. **Rendered stop, defined.** At 8-11 and up: starting from the current node, the reader renders
   the node body and, while the current node is non-ending and has exactly one choice, follows it
   and appends the next body to the same scrollable passage. The stop ends where the next node
   offers 2+ choices or is an ending. The choice list rendered is that terminal node's. The
   "Continue" button ceases to exist at these bands.
2. **Traversal semantics are unchanged.** Flowing through a single-choice node applies its
   `on_enter` effects in order, appends it to `path`, and adds it to `visit_set`, exactly as if
   tapped. Server-side replay validation (`player/replay.py`) is unaffected; the recorded path
   remains node-level.
3. **Go-back operates on stops.** The ADR-024 back affordance rewinds to the previous rendered
   stop (the previous real choice), not the previous node; rewinding into the middle of a flowed
   run is never observable. This matches the button's purpose (undo a mis-tapped choice).
4. **Young bands keep pages.** At 3-5 and 5-8 the reader renders one node per page. Choice cadence,
   flavor mix, and any scaffold-interaction affordance are governed by the per-band choice grammar
   table (design review Q2), which lands as an ADR-011 amendment once ratified; this ADR only fixes
   the presentation split by band.
5. **Conformance-gated.** Stop composition is pure traversal logic and must be implemented
   identically in `player/engine.py` and `frontend/src/player/engine.ts` (or a shared
   stop-composition layer over them), with `schema/conformance/` cases covering: flow across
   effects, flow into endings, loop-back edges inside a run, condition-gated single choices (a
   single choice whose condition is false ends the stop as a dead-end guard; the validator already
   forbids unreachable continuations), and back-by-stop. No band ships flowed rendering before the
   corpus covers it.
6. **Band source of truth.** The band comes from the reading profile (`data-age-band` already
   stamps the kid shell); a guardian changing a profile's band changes presentation on next load,
   with no content change.

## Consequences

- D1 is satisfied for 8+ readers with zero content rewrites and no change to generation budgets,
  validator topology rules, or published blobs.
- The reader's progress display naturally becomes per-stop, which is the same direction `AL-029`
  (route-relative progress) needs; implement together.
- `AL-030` (synchronous whole-read replay on every page turn) gets worse if naively combined with
  multi-node stops; the stop-composition layer should memoize the flowed run rather than re-walk.
- Word count per rendered stop rises (a flowed run concatenates 1-3 node bodies on current chain
  statistics, 82% of runs being length 1-2); the per-band grammar's words-per-stop column becomes
  the operative reading-load guardrail, replacing per-node ceilings as the felt page size.
- The grandfathered catalog (decision D3/D11) reads acceptably under flow immediately, which is
  what makes grandfathering viable while compliant skeletons are authored cell by cell.
