---
title: "ADR-024: Bounded backtracking by forward path replay"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Resolve the contradiction between runtime-semantics.md section 6 ('there is no back button in v1')
  and the back button that ships in Reader.tsx. Ratify forward path replay as the backtracking mechanism,
  which preserves the v1 snapshot model instead of requiring the event log section 6 deferred the feature for,
  and authorize a bounded multi-hop retry affordance at the ending screen."
tags:
  - planning
  - architecture
  - decisions
  - player
---

# ADR-024: Bounded backtracking by forward path replay

> **Status**: Accepted (2026-07-26), on owner direction to implement
> [story-diversity-implementation-plan.md](../story-diversity-implementation-plan.md) slice S0.
> **Supersedes**: [runtime-semantics.md](../runtime-semantics.md) section 6 ("No Backtracking in v1"),
> whose own text requires "a revision to this document and an ADR" for any Phase-1 back-button
> implementation. This is that ADR; the section-6 revision lands with it.
> **Cross-sign**: player only. The validator and server need no change; see Decision 2.

## TL;DR

Backtracking is permitted, and is implemented **only** by replaying the recorded path forward from a known
origin, never by reversing effects. That is why it does not need the event-log model section 6 deferred it
for: a snapshot plus its recorded path is already sufficient to re-derive any earlier point on that path.
Availability is fail-closed. A bounded multi-hop retry affordance is authorized at the ending screen. Enabling
backtracking for **continuation reads** is explicitly *not* authorized here, because it requires durable state
that does not exist yet.

## Context

`runtime-semantics.md` section 6 states, normatively, "the reader moves forward only. There is no 'back' button
in v1", with the rationale that "a back button requires undoing effects, which demands an event-log model rather
than a snapshot model."

A back button ships. `frontend/src/reader/Reader.tsx:210` renders it, commenting "Kids mis-tap constantly; Go
back undoes just the last choice by replaying." So the document and the product disagree, and the document says
what to do about that.

**The rationale, not just the rule, is what turned out to be wrong.** Section 6 assumed backtracking means
undoing effects. The shipped implementation never undoes anything: `back()`
(`frontend/src/player/engine.ts:325`) calls `replayRecordedPath`, which starts a fresh `start(story)` and
re-applies the recorded choices, then returns the state one step short of the live one. Effects are applied
forward, exactly once, in the same order as the original read. No inverse operation exists anywhere in the
mechanism, so no event log is required. The snapshot model of section 5 is preserved intact.

This ADR ratifies that mechanism, tightens the rules around it, and authorizes one extension.

## Decision

### 1. Backtracking is by forward replay only

**Normative rule**: any state a reader returns to is produced by replaying the recorded `path` forward from a
known origin with known initial variables. Reversing an effect, decrementing a counter, or otherwise computing
an inverse is prohibited. If a state cannot be reached by forward replay, the reader does not go there.

This is what keeps the mechanism compatible with section 5's snapshot format. A save records `path`, so any
prefix of that path is replayable; nothing about undoing is needed.

### 2. The server and validator are unaffected

**Normative rule**: backtracking is a client-side concern and introduces no server contract.

A state produced by Go back is indistinguishable from having made fewer choices, so the existing save path
accepts it by construction: `api/reading.py::put_reading_state` uses revision-based optimistic concurrency and
requires nothing about `path` growing between saves, and `player/replay.py::_check_structure` requires only known
node ids, `current_node === path[path.length - 1]`, and a complete in-bounds `var_state`, all of which a shorter
replayed state satisfies. This is why the cross-sign is player-only.

### 3. Availability is fail-closed, and defined on replayability

**Normative rule**: Go back is available exactly when both hold:

1. `path.length > 1` (there is at least one recorded choice to undo), and
2. the recorded path replays faithfully from the origin, reproducing the live state.

When replay cannot reproduce the live state, the reader gets **no** Go back rather than a wrong one. The
enumerated fail-closed cases, all of which return `null` today:

| Case | Why it fails closed |
| --- | --- |
| `path.length <= 1` | Nothing to undo |
| `path[0] !== start_node` (continuation read) | The origin's initial variables are not recoverable; see Decision 6 |
| Dangling `start_node` | `start()` throws; a corrupt story must not crash the reader |
| Dangling choice target | `choose()` throws; the branch is treated as dead |
| Replay budget exhausted | `MAX_REPLAY_STEPS` (5000) bounds the search over paths where several choices share a target |

**`canGoBack` must be defined as `back(...) !== null`**, never as an independent predicate. Two predicates that
can disagree would render a button that does nothing, which is worse than no button.

### 4. What rewinds and what carries over

**Normative rule**: Go back rewinds exactly what choices produced, and nothing else.

| Field | Behaviour | Why |
| --- | --- | --- |
| `current_node`, `var_state`, `path`, `visit_set` | Rewound to the replayed prior state | These are the product of the choice history |
| `state_revision` | Carried over unchanged | Owned by the server's concurrency counter, not by the choice history |
| `save_slots` | Carried over unchanged | Owned outside the choice history; a rewind is not a slot operation |
| `version` | Unchanged | Section 8 version pinning still applies |

### 5. A bounded multi-hop retry affordance is authorized

**Normative rule**: a second, separately labelled affordance may walk back **up to three hops** to the nearest
ancestor at which the reader had a genuine choice, subject to Decision 3's availability rule. Constraints:

- It is a **distinct control from the in-story Go back**, which remains single-step and unchanged. The in-story
  control exists for mis-taps; repurposing it to move a young reader three passages upstream would erase prose
  they were enjoying, and at the 3-5 and 5-8 bands there is no fatal corridor to rescue because `_PROFILES`
  forbids `death` and `capture` at both.
- It is offered at the **ending screen only**.
- Availability stays Decision 3's rule. It must **not** be gated on "an untaken choice exists within 3 hops",
  which would hide the control at a climax the reader has already partly explored, so a button the child just
  learned would vanish exactly when they expected it.
- The walk stops at the **first branching ancestor** regardless of whether its other options were taken, so the
  destination is always "the last place you got to pick" rather than a distance that varies per press.
- Three is a **starting bound, to be re-evaluated as stories are developed** (owner decision, 2026-07-25). It is
  not derived from a measurement; it is chosen because all 73 measured shallow foreclosing terminals lie within
  three hops of a node offering a real alternative.

### 6. Continuation-read backtracking is NOT authorized by this ADR

**Normative rule**: a continuation read gets no backtracking until a separate decision provides a durable,
server-validated replay origin.

This is called out because the gap looks like a small bug and is not. `startContinuation`
(`engine.ts:123`) seeds `var_state` from a carried map, but the resulting `ReadingState` does not retain that
map, and nothing persists it:

- `ReadingState` has no column for a carried or initial variable state (`db/models.py:725`).
- `Completion` stores only `(child_profile_id, storybook_id, version, ending_id, found_at)`, so the predecessor
  book's exit state cannot be re-derived either.
- The seed reaches the client only transiently, through router `location.state`, which `series.ts` documents as
  untrusted and attacker-shapeable via history manipulation.

So enabling it requires new durable state, which means a schema change, an API change, and an OpenAPI
regeneration. **And that new state would be a replay origin, which makes it a state-restoration input**: exactly
the class of defect that `save_slots` already represents, being client-writable, server-persisted, and omitted
from `validate_reading_state`. A naive implementation would create a second instance of that defect, where a
forged origin lets a reader replay into a state they never earned, in the state-carrying series books where
there is most to gain by doing so.

Any future decision to enable it must therefore land the origin as **server-validated** data, not merely
persisted data.

## Consequences

- Section 6 of `runtime-semantics.md` is rewritten from a prohibition into the rules above, and the document
  version moves to 1.2.
- The multi-hop affordance is unblocked and needs no further ADR.
- Continuation backtracking stays disabled, and is now disabled *on the record* with its cost stated, rather
  than by an undocumented fail-closed branch.
- "Read again" on a continuation read remains wrong for a separate reason not fixed here: `machine.ts:108`
  resets to `start_node` with declared initials, fabricating carried variables the reader never earned. That is
  a reset bug, not a backtracking one, and is tracked as its own defect.

## Validation

- `engine.test.ts` must keep its "fails closed for a continuation state" case; Decision 6 makes it normative
  rather than incidental.
- A test at an ending reached through a **single-choice corridor**, since 58 of the 73 measured shallow
  foreclosing terminals are reached that way and a one-hop rewind re-presents the same fatal choice.
- A test that `canGoBack` and `back` never disagree.
- A test that `save_slots` and `state_revision` survive a rewind unchanged.

## Related

- [runtime-semantics.md](../runtime-semantics.md) sections 5, 6, 8
- [ADR-001](./adr-001-story-format-json-storybook.md) (two-axis endings)
- [ADR-011](./adr-011-story-scale-framework.md) section 8 (series continuity)
- [story-diversity-plan-v2.md](../story-diversity-plan-v2.md) items A12, A13a, A13b, A18, B2, B4
