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
baseline, and **51,241 in every one of the 27 envelope states**, min equal to max.
The envelope multiplies the number of walks, not the size of each. **The 100,000 cap is untouched.**

Wall-clock is a separate question from the cap, and only one figure should be quoted for it: the
whole-gate one. On that same skeleton (`skeletons/16+/the-longwinter-station.json`, 248 nodes,
51,241 base configurations, the canonical 27-state `might`/`wits`/`nerve` envelope), `run_gate`
takes **0.77s with no envelope declared and 49.58s with it**, a roughly 64x multiplier. That is the
number a guardian-reachable route actually holds, and it is the measurement both
[UW-A47](../unscheduled-work-register.md) (bounded gate concurrency, shipped) and
[UW-A48](../unscheduled-work-register.md) (memoise the per-entry-state walk, open) rest on. Per
config-walk the constant is ~3.5e-5 s, stable across three books of very different sizes; the
authoring-facing arithmetic that follows from it is written out in
`.claude/skills/cyo-author/reference/skeleton-format.md`.

That result holds only for a variable seeded and never set in-book, which is every gamebook stat. It does
**not** hold for a prose book's `archetype`, because the build node sets it:

| Book | Baseline | With the build-node idiom |
|---|---|---|
| `10-13/the-glass-comet` | 638 | 3,829 (6.00x) |
| `10-13/the-flooded-quarter` | 19,236 | capped |
| `10-13/the-winter-of-the-wolf-queen` | 28,512 | capped |

A book whose base closure exceeds 100,000 // 6 = **16,666 configurations cannot host a six-way build
node at all** (the exact threshold `validator/character.py` enforces). `CH-8` enforces this as a pre-flight check rather than letting authors discover it as an
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

Fourteen conditions hold the guarantee up. It fails silently without any one of them. The first eight are
validator-side, proven once at gate time against a skeleton document. The persistent-characters runtime
(branch `feat/persistent-characters-runtime`) adds six more that hold at read time, once a character stops
being only a validated envelope and starts being an actual seed a real read binds to: the walk proves every
*declared* state safe, and rows 9-14 are what keep a real reader's actual entry state inside that proven set
rather than letting a runtime shortcut manufacture one the walk never saw.

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
| 9 | The binding is **server-derived**; no request model accepts `character_id` (`api/schemas.py`; resolved by `_bind_active_character` in `api/reading.py`) | If a client could name the character to bind, a request could seed a read with a character CH-* never proved belongs to that reader, walked envelope or not; the guarantee is about the reader who owns this read, not about some character somewhere that happens to validate. |
| 10 | The seed is **snapshotted at read start and never recomputed** (`api/reading.py`: `_bind_active_character` computes the seed once, into `reading_state.seed_var_state`, at row creation) | A seed recomputed from the character's live attributes on every read would let a state proven walked at bind time become an unwalked one later, if the character's attributes changed in between (for example, a concurrent completion in another book writing back new stats); the walk says nothing about a seed it never saw. |
| 11 | **Whenever replay runs**, it validates against the **stored** seed, because `validate_reading_state`'s `seed_var_state` parameter (`player/replay.py`) is **required**, with no default, so no call site can omit it. The guarantee is conditional, and the condition is load-bearing: replay runs only on a save that carries a `choice_path`, and the shipped web client never sends one (`frontend/src/offline/sync.ts::toPutPayload` builds the PUT body field by field and omits it), so on every save today's client makes, this row is closing a channel nothing currently walks through | An omittable parameter lets a call site silently fall back to an unseeded replay even for a seeded read, reopening the exact tampering channel the parameter exists to close: a client submitting a `choice_path` that replays cleanly from a forged declared-initial state instead of the real, server-held seed. The row stays at full strength despite being unexercised, because the API accepts `choice_path` from **any** client, not only the shipped one, and because the offline queue, a native client, or a future replay-based conflict resolution would each start sending one without touching this parameter. Read it as a guarantee about what happens if replay runs, never as evidence that the replay baseline is enforced on real traffic; it is not, and the accepted residual below is the direct consequence. |
| 12 | Writeback idempotency is the `character_book_completion` **primary key** (`db/models.py::CharacterBookCompletion`), enforced by `INSERT ... ON CONFLICT DO NOTHING`, not an application-level check | A "have we recorded this already?" read-then-write in application code is racy under concurrent offline-sync retries; double-crediting a satisfying-ending completion is a data-integrity failure the walked-state guarantee has no opinion on, but the reader-facing progression feature depends on exactly as much. |
| 13 | The attribute update is computed **in-statement** with `LEAST`/`GREATEST` (`characters/progression.py`: `SET value_int = LEAST(:canonical_max, GREATEST(value_int, :exit_value))`) | Computing the new value in Python (read, clamp, write) is a read-modify-write race across concurrent completions from different devices or books: one writer's update can be lost, and neither the monotonic floor nor the vocabulary ceiling is enforced against the value actually committed, silently producing an attribute CH-2's canonical range was never proved to admit. |
| 14 | `character.family_id` is backed by a **composite FK** (`fk_character_profile_family` on `(child_profile_id, family_id)`) to `child_profile (id, family_id)` (`db/models.py::Character`), which is what makes the Tier 1 `family_scoped` RLS policy (ADR-022) sound | `family_id` is denormalized onto the row so the policy can read it without a join. Without the composite FK tying it to the same profile's own `family_id`, an insert or update could set a character's `family_id` inconsistent with its owning profile's real family, and the RLS policy would then scope access by a value that is claimed rather than proven, defeating the isolation ADR-022 exists to give this table. |

#### Accepted residual: the bound seed can disagree with the seed the client opened from, and nothing reports it

Rows 9 to 14 are conditions, not a claim that the chain is currently airtight end to end. One gap is
known, measured, and accepted rather than fixed, and it belongs here beside the table rather than in
a follow-on footnote, because it is what row 11's conditional wording is pointing at.

The active character can change between the client's seed fetch and this branch's own
`_bind_active_character` call on the create path: a guardian or a second tab switches the active
character in that window. The row is then created carrying character B's seed while the `var_state`
the client sends was produced from character A's. **Nothing rejects it**, for exactly row 11's
reason: rejection would require a replay proof, replay needs a `choice_path`, and the shipped client
sends none. A first save that omits `choice_path` is checked only against the structural floor, so it
can persist a `var_state` the bound seed could never have produced.

The consequence is user-visible, not merely theoretical. On the read's next resume, `canGoBack` fails
closed against the mismatched seed, so **Go back silently disappears for the rest of that read**, and
RESTART reopens from the new character's numbers. A related residual covers a fresh read that cannot
reach the network or is served a service-worker-cached `characters` response with no `seed_var_state`
at all: it still opens from declared initials.

`api/reading.py` carries the full `#EDGE` marker, including its own judgement that calling this
"latent" undersells it, and that marker is the authority. Two things follow for anyone extending this
design. Anything that starts sending `choice_path` (a native client, the offline queue, replay-based
conflict resolution) converts this residual from a degraded Go-back button into a permanently wedged
read, because every later save then replays from the stored seed, disagrees, and 422s. And rows 10
and 11 should be read as protecting the seed **once bound**, never as proving the bound seed is the
one the reader's client actually started from.

CH-2 also requires the declared range to lie inside the canonical vocabulary range. That check is **not**
one of the fourteen, and recording why matters, because it reads like one. A book declaring `archetype: 0..3`
walks exactly `0..3`, and a reader carrying `5` is clamped to `3`, so the reader lands in a proven state
either way; narrowing is safe by the same mechanism row 1 already guarantees. Containment earns its place
on two other grounds. It restores CH-8's precondition, since CH-8 derives arity from
`len(ARCHETYPE_ROSTER)` rather than from the document, and a wider-than-canonical declaration would
silently under-measure the real configuration count. And it keeps the proven state space inside the
vocabulary, which the character writer path assumes when it projects a walked value back onto a
persistent character.

## Follow-on work

- **Written and passing its tests on an unmerged branch, with one accepted residual.** The character
  CRUD/API surface, the seed projection into `VarState`, the read-time binding and replay conditions
  (rows 9-11 above), the progression writeback (rows 12-13), the `character.family_id` composite FK
  (row 14), and the ADR-023 amendment's `character_name` personalization slot are all written on branch
  `feat/persistent-characters-runtime`; the character creator and picker UI, and the reader-surfaced
  bound character, are the frontend half of the same branch. Two qualifications are part of the status
  rather than caveats on it. The branch is **unmerged and unpushed**, so nothing here is on `main` and
  no citation above proves anything yet. And the chain ships with the **accepted residual** recorded
  under "Integrity posture" above: the bound seed can disagree with the seed the client opened from,
  and the mismatch degrades Go back for the rest of that read instead of being reported.
  [UW-A46](../unscheduled-work-register.md) does **not** cover any of this work and is not closed by
  this branch; see the next bullet for what that row actually tracks.
- **Still unbuilt, and what `UW-A46` tracks**: the pathfinder pilot skeleton itself, a real
  `accepts_character` book in a 13-16 gamebook cell plus the empirical A/B measurement against a matched
  non-carrying skeleton. A 13-16 stat-envelope pilot was drafted during this workstream and **withdrawn
  on 2026-08-08** rather than shipped: with `_check_dead_branches` envelope-blind, every stat gate had to
  be faked through the workaround in `AL-129`, which leaves the reader unable to perceive the choices the
  stats were supposed to drive. [UW-A46](../unscheduled-work-register.md) therefore stays open, and
  whether the pilot is worth authoring at all turns on the `L2-11` question that
  [UW-C64](../unscheduled-work-register.md) now carries.

  A second pilot was withdrawn the same day. `the-storm-chasers-club` (8-11, archetype envelope 0-6) was
  promoted to Tier 2 on this branch and the promotion was **withdrawn on 2026-08-08** after review, so the
  book reverts to the Tier 1 book it already was. Its envelope passed all eight CH-* rules while doing
  nothing a reader could perceive: the one archetype-gated choice sat behind an only-inbound edge whose
  effect set the very value the gate tested, making the condition unconditionally true for all seven entry
  states, and its six archetype-setting choices were ungated with no bypass, which this branch's own
  `skeleton-format.md` forbids. See `AL-131`. **The consequence for this ADR is that the runtime ships with
  zero participating catalog books.** Everything in the bullet above is enforced, tested, and unreached: no
  skeleton in the catalog declares `accepts_character`, so no reader can yet be bound to a character. That
  is deliberate, and it is the same posture PR [#636](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/636)
  shipped the static half under.
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
