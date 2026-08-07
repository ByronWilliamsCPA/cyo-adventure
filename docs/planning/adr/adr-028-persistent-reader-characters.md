---
title: "ADR-028: Persistent reader characters"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Authorize a persistent reader character carried across preset books as a seeded VarState,
  define the canonical variable vocabulary and the accepts_character envelope, establish the CH-* rule
  family that proves a book safe across exactly that envelope, and record the inspiration-only IP
  posture for archetype naming."
tags:
  - planning
  - architecture
  - decisions
  - storybook
  - validator
---

# ADR-028: Persistent reader characters

> **Status**: Accepted (2026-08-06), on owner direction recorded as decisions D1-D12 in
> [2026-08-05-persistent-reader-characters-design.md](../../superpowers/specs/2026-08-05-persistent-reader-characters-design.md)
> section 1.
> **Authority**: the design spec above, whose section 10 records what a two-round adversarial review
> changed and which of its findings measurement falsified.
> **Depends on**: [ADR-025](./adr-025-additive-storybook-schema-versioning.md). `accepts_character`
> cannot exist while the parser demands exact `"2.0"` and every model sets `extra="forbid"`.
> **Amends**: [ADR-023](./adr-023-story-personalization-slots.md), by the in-place amendment dated
> 2026-08-06 in that document, which adds the `character_name` slot.
> **Cross-sign**: both player engines and the conformance corpus, once seeding becomes a runtime path.

## TL;DR

A reader creates a character once and carries it through **preset** books. Books are never regenerated per
character. Each participating book declares an `accepts_character` envelope, and the validator proves the
book safe across exactly that envelope before it can be published.

A character is a `VarState`. It is seeded through the WS-G G3 carry path that already exists in both
engines, so the seed runtime is not new code.

## Context

The reader-facing want is a DnD-style character that persists across books. The naive readings of that want
are both unaffordable: regenerating a book per character multiplies generation cost by the character space,
and a free-text character sheet has no validation story at all.

Three facts constrain the design.

1. **G3 carry is name-match.** An undeclared canonical name is silently ignored rather than an error, so the
   vocabulary is a menu each book draws from, not a mandate every book satisfies. A 16+ long gamebook and an
   8-11 prose book can share a character while declaring disjoint variable sets.
2. **Tier-2 conditions are a JSONLogic subset with no string comparison.** Any character trait a condition
   reads must be an integer.
3. **Layer-2 proves properties from a book's declared initial state.** A character arriving from outside is
   an entry state the existing walk never considered.

## Decision

### 1. A character is a seeded `VarState`, not a new runtime concept

The projection that builds a seed maps the database character row to a variable state, which G3 carries into
the book by name match. No new player concept, no new condition operator, no per-character generation.

### 2. The canonical vocabulary v1 is four variables

| Name | Type | Range | Declared by | Meaning |
|---|---|---|---|---|
| `archetype` | int | 0-6 | prose cells | `0` means not yet chosen; `1`-`6` are the six archetypes in roster order (`scout`, `guardian`, `trickster`, `scholar`, `healer`, `wildheart`). Gates flavour and prose colour. Never a difficulty check. |
| `might` | int | 0-2 | gamebook cells | Trained force |
| `wits` | int | 0-2 | gamebook cells | Trained cleverness |
| `nerve` | int | 0-2 | gamebook cells | Trained composure |

Range 0-2 rather than 0-3 is a deliberate envelope-size choice: three stats at 0-3 is 64 states, at 0-2 it is
27. A four-band degrees-of-success ladder still fits (`>= 2` crit, `== 1` pass, `== 0` with a local resource
= scrape, `== 0` without = fail).

`archetype` and the stats never coexist in a gamebook, because in a mechanics book the stat spread **is** the
archetype. `archetype` carries identity only where there are no stats to infer it from.

**Type boundary.** `character.archetype` is a text enum in the database, because a text enum is readable in a
migration and survives a roster reorder. The Storybook variable is an int. The projection that maps text to
the int code above is the single place the roster order is load-bearing, and it is pinned by a test so a
future roster insertion cannot silently renumber live characters.

### 3. `archetype = 0` means "not yet chosen", and the build node must be bypassed rather than gated

An exogenous immutable `archetype` makes every archetype-gated flavour branch unreachable from a book's
declared initials, so `L2-11` errors the book out of publication before any new rule runs. A participating
book therefore declares `archetype: 0` and keeps an in-story **build node** that sets it to 1-6, which keeps
every branch visible to the existing declared-initials walk.

The build node's own choices are gated on `archetype == 0`. A book that always routes **through** the build
node lands a returning reader on a page where every choice is invisible, which is a runtime break rather
than a validator artifact. The conforming shape is a **gate node** that precedes the build node and routes
past it when `archetype != 0`.

### 4. `accepts_character` declares the envelope, and omitting it accepts no character

```json
"accepts_character": {
  "might": {"min": 0, "max": 2},
  "wits":  {"min": 0, "max": 2},
  "nerve": {"min": 0, "max": 2}
}
```

Envelope size is the product of the ranges: 27 states for the gamebook above, 7 for a prose book declaring
only `archetype`. A book omitting the field accepts no character, and `CH-6` enforces that by reserving the
canonical names, so a book that has not opted in cannot be seeded through an accidental name collision.

### 5. The CH-* rule family proves the envelope

New module `validator/character.py`, namespace `CH-*`. It sits in its own namespace rather than extending
`L2-*` because, like `SR-*`, it proves a **cross-artifact handoff** rather than a within-story property.

| Rule | Severity | Check |
|---|---|---|
| `CH-1` | ERROR | Every `accepts_character` name is canonical and declared in `variables` with matching type |
| `CH-2` | ERROR | Each envelope range **equals** the declared variable's `min`/`max` |
| `CH-3a` | ERROR | Union-quantified: a conditional choice invisible in every configuration across the baseline walk and all envelope walks combined is a dead branch |
| `CH-3b` | ERROR | Per-state: for every envelope state, entry raises no `L2-9`, `L2-10`, or `L2-14` error the book does not raise from its own declared initials |
| `CH-4` | ERROR | For every envelope state, a satisfying ending remains reachable |
| `CH-5` | ERROR | Envelope size exceeds `MAX_ENTRY_STATES` |
| `CH-6` | ERROR | A book not declaring `accepts_character` may not declare a canonical variable name |
| `CH-7` | ERROR | A book declaring `accepts_character` is not a non-first book of a `carries_state` series |
| `CH-8` | ERROR | A book with a build node whose base closure exceeds `cap / build_node_arity` configurations |

**The CH-3 split is a correction, not a refinement.** A single per-state CH-3 rejects every participating
book by construction: in envelope state `archetype = 3`, the branches gated on 1, 2, 4, 5, and 6 are
*correctly* invisible, and a per-state L2-11 check reads each as a new dead branch. Per-state dead-branch
quantification is incompatible with character-gated content of any kind. `L2-11` is a union property; `L2-9`,
`L2-10`, and `L2-14` are per-state properties and keep a baseline diff.

**CH-2 is equality, not containment.** If the envelope were merely contained in the declared bounds, G3's
clamp to *declared* bounds would silently admit reachable states the validator never proved, and the clamp
makes that failure invisible at runtime.

**CH-5 is an ERROR, not a warning.** SR-9 warns because a chain's entry-state count is emergent from the
sending book. An envelope is declared, so exceeding the cap has an obvious fix, and reporting a book clean
over a truncated sample of a declared envelope would be a silent gate failure.

### 6. Character and series are mutually exclusive in v1

`CH-7` forbids a book declaring `accepts_character` from being a non-first book of a `carries_state` series.
Two independent sources of carried state entering one book is a composition this design has not proved.

### 7. Archetype naming is inspiration-only (Option A)

The six archetype names are generic fantasy roles, not references to any published game system's classes,
statistics, or mechanics. No system's content is copied, adapted, or named. This is recorded the way ADR-023
recorded OD-5: as an explicit posture rather than an unstated assumption.

## Consequences

### Measured cost

An immutable character variable is a **constant within a walk**, and a constant adds no distinct
`ConfigKey`s. Measured on the worst book in the catalog, `the-longwinter-station`: 51,241 configurations at
baseline, and **51,241 in every one of the 27 envelope states**, min equal to max, 12.15s for all 27 walks.
The envelope multiplies the number of walks, not the size of each. **The 100,000 cap is untouched.**

That result holds only for a variable seeded and never set in-book, which is every gamebook stat. It does
**not** hold for a prose book's `archetype`, because the build node sets it:

| Book | Baseline | With the build-node idiom |
|---|---|---|
| `10-13/the-glass-comet` | 638 | 3,829 (6.00x) |
| `10-13/the-flooded-quarter` | 19,236 | capped |
| `10-13/the-winter-of-the-wolf-queen` | 28,512 | capped |

A book whose base closure exceeds roughly 100,000 / 6 = **16,600 configurations cannot host a six-way build
node at all**. `CH-8` enforces this as a pre-flight check rather than letting authors discover it as an
opaque `L2-12`.

### Technical debt accepted

`_l2_error_signatures` in `validator/series.py` keys on `rule_id|node_id`, so two distinct dead branches on
one node collapse to a single signature. `CH-3b` defines its own signature including `choice_id`. Fixing the
shared function in place would also tighten SR-9, which is safe in principle (`rule|node|choice` strictly
refines `rule|node`, so findings can only grow) but is **gated behind restoring the four skipped Wyrmreach
trilogy fixtures**, because `validate_series` runs on the approve path and a chain turned newly red would
block approval of an already-published series at runtime.

### Integrity posture

<!-- #CRITICAL: data integrity: a seeded entry state that the validator never proved can reach a child
     reader, because the runtime clamp to declared bounds hides the discrepancy rather than reporting it.
     #VERIFY: every row of the conditions table below is load-bearing on its own; each must stay pinned by
     a test that fails when that row alone is weakened. Do not relax a row because the surrounding rules
     look sufficient. They are not independent, and the failure mode is silent by construction. -->

The guarantee this ADR makes is that **every state a reader can arrive in has been walked**.

The mechanism is narrower than it looks, and stating it first is what makes the conditions legible.
`StoryEngine.start_continuation` clamps every carried value to the story's **declared variable bounds**
(`player/engine.py`; `frontend/src/player/engine.ts` mirrors it). `envelope_states` enumerates the
**envelope**. Those are two different objects, and CH-2's equality is the only thing forcing them to be
the same set. The clamp target and the walked set coincide by construction, not by coincidence.

Eight conditions hold the guarantee up. It fails silently without any one of them.

| # | Condition | Why it is load-bearing |
| --- | --- | --- |
| 1 | CH-2 requires **equality**, not containment, between the envelope span and the declared bounds | The clamp targets the declared bounds and the walk enumerates the envelope; equality is what makes those one set. |
| 2 | CH-2 rejects a declared variable with an **absent** `min` or `max` | The clamp is a no-op when a bound is `None`, so an opted-in unbounded variable admits any forged integer, unclamped and unwalked. |
| 3 | CH-6 enforces namespace reservation in **both** directions | Seeding is by name match, so a non-opted-in book declaring a canonical name is seeded with no proof; and an opted-in book may declare a canonical variable its envelope omits, which CH-1 and CH-2 never reach (CH-1 only walks envelope to variable). |
| 4 | CH-7 forbids a character in a non-first book of a `carries_state` series | The walk enumerates envelope states **or** series carried states, never their cross product, so two carry sources into one book is a state space nothing walks. |
| 5 | CH-5 stays a blocking **ERROR** | The walk is skipped whenever the envelope exceeds `MAX_ENTRY_STATES`, and that skip is independent of CH-5's severity. Downgrade CH-5 and the book is both unwalked and unblocked. |
| 6 | `"CH"` stays in `gate.py`'s blocked-prefix tuple | Without it every CH ERROR is reported but not blocking, which makes rows 1 to 5 advisory. This grew more load-bearing when the walk began skipping on **any** CH error rather than only CH-5: that skip is sound only because a CH error blocks. |
| 7 | CH-3b fails **closed** when the Layer 2 walk hits its cap | A capped walk returns only an L2-12 finding, which is not in the per-state rule set, so a capped state would otherwise read exactly like a clean one. |
| 8 | CH-3b's per-state signature includes the finding **message** | The message embeds the variable state; without it two dead ends on one node at two different states collapse into a single signature, and a genuinely new per-state defect is suppressed as an already-known baseline. |

CH-2 also requires the declared range to lie inside the canonical vocabulary range. That check is **not**
one of the eight, and recording why matters, because it reads like one. A book declaring `archetype: 0..3`
walks exactly `0..3`, and a reader carrying `5` is clamped to `3`, so the reader lands in a proven state
either way; narrowing is safe by the same mechanism row 1 already guarantees. Containment earns its place
on two other grounds. It restores CH-8's precondition, since CH-8 derives arity from
`len(ARCHETYPE_ROSTER)` rather than from the document, and a wider-than-canonical declaration would
silently under-measure the real configuration count. And it keeps the proven state space inside the
vocabulary, which the unbuilt character writer path assumes when it projects a walked value back onto a
persistent character.

## Follow-on work

- **The character CRUD/API surface, the seed projection, and the `character_name` personalization slot are
  unbuilt.** This ADR authorizes the vocabulary, the `accepts_character` envelope, and the CH-* validator
  proof; it does not build the database row, the seed projection into `VarState`, or the ADR-023 amendment's
  `character_name` slot, all of which are scheduled as later work in the same authoring plan that
  implements the CH-* rules. Given a register home: [UW-A46](../unscheduled-work-register.md), Phase 5.
- **The `_l2_error_signatures` tightening named above in "Technical debt accepted" is intentionally left
  without its own register row here.** It is gated behind restoring the four skipped Wyrmreach trilogy
  fixtures, a precondition not yet met, and this plan's own bookkeeping step (register homes for work
  discovered while landing the CH-* rules) runs after those rules ship, when the interaction is concretely
  known rather than anticipated.

## Related

- [ADR-023](./adr-023-story-personalization-slots.md), amended 2026-08-06 for the `character_name` slot
- [ADR-025](./adr-025-additive-storybook-schema-versioning.md), the hard prerequisite
- [pathfinder-structure-exploration.md](../pathfinder-structure-exploration.md), SQ-22 / OG5
- [capability-register.md](../capability-register.md), K3 and K18
