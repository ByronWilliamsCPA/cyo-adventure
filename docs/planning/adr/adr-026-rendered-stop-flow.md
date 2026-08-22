---
title: "ADR-026: Rendered-stop flow of linear passages"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Implement the owner's every-stop-ends-in-a-choice ruling (design review D1) at the
  presentation layer: the reader flows consecutive single-choice nodes into one rendered stop for
  bands 8-11 and up, and keeps discrete pages with a choice cadence at 3-5 and 5-8, touching
  neither the story graph nor ADR-011's constants. ADR-011 has since re-derived its
  decisions-per-path window per cell on its own amendment; see the note under Status."
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
> validator's structural rules, and ADR-011's scale constants are explicitly unchanged **by this
> ADR**.
> **Relates to**: ADR-011 (constants untouched here), ADR-024 (go-back semantics extended to stops),
> ADR-025 (any schema-visible additions ride minor versions).
>
> **Note (2026-08-22)**: "unchanged" above is a statement about this decision's blast radius, and it
> still holds: nothing here edited ADR-011. ADR-011's constants themselves are no longer what this
> document describes. Its section 6 was rewritten on 2026-08-22 (`UW-C327`, ADR-011 section 11):
> decisions per path is now a **derived per-cell window** rather than a research-locked flat
> "~4-8", which survives only as the JHM 2019 anchor for the `8-11`/`10-13` Short prose region. The
> two references below (Context, Alternative 1) quote the pre-amendment wording because they record
> what was true at the 2026-08-01 decision; read them as history, not as the current constant. The
> amendment does not disturb this ADR's decision: it derives the flowed-band floors **from** the
> section 10 grammar this ADR ratified, so the two are consistent by construction.

## TL;DR

A **node is not a screen**. The reader composes **rendered stops**: for bands 8-11, 10-13, 13-16,
and 16+, consecutive single-choice non-ending nodes flow into one scrollable passage that ends at
the next real choice or ending, so every stop a child makes ends in a choice. For 3-5 and 5-8 the
reader keeps discrete pages (picture-book pacing) and the choice cadence is governed by the
per-band choice grammar ([ADR-011](./adr-011-story-scale-framework.md) section 10, ratified as D15
alongside this ADR). The graph keeps its linear
beats, preserving the researched genre shape, the words-per-node ceilings, and every published blob.

## Context

The owner ruled that every page a child stops on must offer a choice (design review D1). Measured:
69% of non-ending nodes are single-choice; 0 of 61 skeletons would satisfy the ruling structurally.
But ADR-011, as it read at this decision, research-locked decisions-per-path at ~4-8 and mandates
linear passages as the substance carrier, anchored on measurement of the printed genre (that flat
constant was superseded on 2026-08-22; see the note under Status). The conflict is presentational: print flows
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
   table (design review Q2), ratified as D15 and landed in the same change as this ADR as
   [ADR-011](./adr-011-story-scale-framework.md) section 10; this ADR only fixes the presentation
   split by band. Note the split of authority: ADR-011 section 10 says how many choices a band's
   content should carry, this ADR says how a band renders them, and `validator/choice_grammar.py`
   enforces neither by default (its `enforce_grammar` flag is off; see the CG family in
   [validator-rules.md](../validator-rules.md)).
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

## Alternatives Considered

### Alternative 1: force-branch the content (make every node a real choice)

Satisfy D1 structurally rather than presentationally: rewrite skeletons and generation prompts so
no non-ending node has exactly one choice.

Rejected. 69% of non-ending nodes are single-choice and 0 of 61 skeletons would pass, so this is a
rewrite of the entire catalog, not a change to it. It also fought ADR-011's research lock directly:
at the time of this decision, decisions-per-path was anchored at a flat ~4-8 on measurement of the
printed genre, and linear passages are the substance carrier. The rejection does not depend on that
flat constant, which ADR-011 has since replaced with a derived per-cell window: the per-cell floors
are higher still, so force-branching every node fights them at least as hard. No source in the
research appendix supports force-branching every node, and
inkle's ink "gather" architecture, the strongest adaptation precedent, does the opposite: linear
graph structure under a choice-dense surface.

### Alternative 2: keep the "Continue" button and accept the tap

Change nothing; treat "Continue" as an acceptable page turn.

Rejected by D1 itself, which is a ruling about what a child experiences, and the measurement is why
it was ruled: at 69% single-choice nodes, a reader spends most of a book tapping a button that
offers no decision. That is the "interactive book that is mostly not interactive" the design review
set out to fix.

### Alternative 3: flow at every band, including 3-5 and 5-8

Apply one rendering rule everywhere rather than splitting by band.

Rejected on the research the same review cites for the opposite conclusion at young bands:
comprehension competes with interaction for pre-readers, so raising interaction density at 3-5
costs understanding. A picture-book page is also a deliberate unit at that age. The split is the
cost of this decision, not an oversight: two rendering modes must both stay corpus-proven, which
decision 5 makes explicit.

### Alternative 4: compose stops server-side and send the reader a flat page list

Have the backend do the flowing and hand the client pre-composed stops, avoiding a second
implementation.

Rejected because it breaks offline reading, which is a load-bearing product property (ADR-002): a
cached blob must be playable with no server, so the client needs the composition logic regardless.
Having built it client-side, the server copy exists for replay validation and is held identical by
`schema/conformance/stop_traces.json` rather than by hoping. That dual-engine tax is acknowledged
in decision 5 rather than avoided.

## Implementation notes (2026-08-01, first implementation)

The engine layer (`player/stops.py`, `frontend/src/player/stops.ts`,
`schema/conformance/stop_traces.json`) pinned four semantics worth recording:

1. The branch/dead-end decision counts the node's **raw** `choices`, not the visible subset: a
   2-choice node with one condition-hidden choice ends the stop (and may therefore render a single
   visible choice). This matches the decision text literally; revisit only if reader data shows it
   reads as a broken page.
2. The loop guard is **per-stop**: only a would-be revisit within the same composed run halts
   flow; cross-stop revisits (loop_and_grow topologies) are unaffected.
3. Loop detection halts at the current node **without** applying the looping transition, so the
   reader can still choose to take the loop; it just never auto-flows.
4. Go-back-by-stop lives frontend-only (`backOneStop` replays the existing `back()` per node in
   the stop), consistent with the engines' existing convention that back-navigation is not
   mirrored server-side; stop composition itself is corpus-proven identical on both sides.

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
