---
schema_type: common
title: "Persistent Reader Characters: Declared Envelopes over Preset Books"
status: draft
owner: core-maintainer
purpose: "Let a reader create a character once and carry it through preset books, with each book declaring the character range it accepts and the validator proving the book safe across exactly that range."
tags:
  - planning
  - project
---

> **Status**: Approved design, pre-implementation | **Date**: 2026-08-05
> **Gate**: SQ-22 / OG5 ruled **GO** by the owner
> **Next ADR number**: ADR-028

A reader creates a character once, keeps it, and carries it through preset books. Books are
never regenerated per character. Each book declares the character range it accepts, and the
validator proves the book safe across exactly that range before it can be published.

---

## 1. Provenance

The open item is **SQ-22 / owner gate OG5** ("Pathfinder Phase 0 go/no-go"), recorded in
[story-structure-improvement-plan.md:200,251](../../planning/story-structure-improvement-plan.md)
and [story-structure-implementation-briefs.md:651-656](../../planning/story-structure-implementation-briefs.md).
The decision package is [pathfinder-structure-exploration.md](../../planning/pathfinder-structure-exploration.md),
whose section 8 defines a four-phase gated path exiting Phase 0 on a recorded ADR.

The owner ruled GO and widened scope beyond what the exploration doc proposed.

| # | Decision | Basis |
|---|---|---|
| D1 | Blend in-story build selection with an app-level persistent character; books stay preset | Owner: "reader could create a character and reuse them through stories. We don't create new stories for each character." |
| D2 | Declared envelope per book | Owner choice among four models |
| D3 | Bands 8-11, 10-13, 13-16, 16+ | Owner choice |
| D4 | Prose cells: identity carries, mechanics don't | Owner choice |
| D5 | Name via ADR-023 render-time substitution; everything else from a closed roster | Owner choice |
| D6 | All three subsystems (identity, mechanics, progression) in one body of work | Owner choice |
| D7 | Several characters per profile, one active at a time | Owner choice |
| D8 | Two adversarial review passes: on the draft and on this spec | Owner choice |
| D9 | Fund ADR-025 implementation as step 0 | Owner choice, post-review |
| D10 | Reader lifecycle (backtracking, restart, issue #460) is in scope | Owner choice, post-review |
| D11 | Keep three stats; do not shrink the envelope | Owner choice, post-review |

This spec incorporates the round-1 adversarial review (`senior-architecture-reviewer`, Fable 5,
verdict *material rework needed*). Every blocker and major it raised was independently verified
against code before being folded in; section 9 records what changed and what was falsified.

---

## 2. Ground truth

Each claim below was verified by reading the code, not inferred. They drive the whole design.

1. **The carried-state runtime already exists in both engines.**
   [`player/engine.py:58`](../../../src/cyo_adventure/player/engine.py) `start_continuation(carried)`
   merges carried values into declared initials *before* the start node's `on_enter` runs.
   WS-G G3 carry rules: name-match against a declared variable, type-match or skip, int clamped
   to the receiving variable's declared bounds. `frontend/src/player/engine.ts` mirrors it;
   divergence is a conformance failure under `runtime-semantics.md` section 1.
2. **The walk already accepts a carried entry.** `walk_configurations(story, cap=100_000, carried=...)`
   in [`validator/walk.py:95-133`](../../../src/cyo_adventure/validator/walk.py).
3. **`validate_layer2` already accepts `carried=`.** The gate simply never passes it:
   [`validator/gate.py:140`](../../../src/cyo_adventure/validator/gate.py) calls `validate_layer2(story)`
   with declared initials only. This makes the Layer-2 plumbing for envelope proofs cheap; the
   *semantics* change in section 5.2 is the real work.
4. **SR-9 is the proof template.** [`validator/series.py`](../../../src/cyo_adventure/validator/series.py)
   proves a receiving book safe when entered with each distinct satisfying exit state of the
   sending book: `_satisfying_exit_states`, an `_l2_error_signatures` baseline diff, and
   `_satisfying_ending_reachable`. Caps at `_MAX_ENTRY_STATES = 64` and warns when the cap bites.
5. **`_l2_error_signatures` keys on `rule_id|node_id` only** (series.py:325-339). It deliberately
   drops the message because the message embeds variable state. It also drops `choice_id`, so two
   distinct dead branches on the same node collapse to one signature.
6. **The frontend seed is one-shot.** `ReaderPage.tsx` applies a continuation only when no saved
   reading state exists. The saved `varState` is authoritative thereafter.
7. **Backtracking is already disabled for seeded reads, deliberately.**
   [`frontend/src/player/engine.ts:297-300`](../../../frontend/src/player/engine.ts) returns `null`
   from the Go-back path when `live.path[0] !== story.start_node`, with a comment explaining that
   a non-start entry cannot be reproduced by replay. Open issue **#460** (RESTART discards carried
   state) is the same defect class.
8. **The seed is attacker-shapeable.** `frontend/src/player/series.ts` carries an `#ASSUME: security`
   marker: the seed arrives as router `location.state`, is shape-checked by `parseContinuation`, and
   every value is re-filtered by `startContinuation`.
9. **`PERSONALIZATION_FIELDS` is a closed frozenset** of 11 slot fields
   ([`storybook/theme_contract.py:74-97`](../../../src/cyo_adventure/storybook/theme_contract.py)).
   `REAL_PERSON_PERSONALIZATION_FIELDS` forces any slot naming a real person to declare `role_safety`.
   Free text is already permitted for `pet_name` and, via guardian `display_name`, for
   `protagonist_first_name`. Route A (self-naming disallowed) operates only at the
   request/generation layer and is orthogonal (ADR-023 section 4).
10. **Personalization storage is one value per `(child_profile_id, slot_type)`**
    ([`storybook/personalization_values.py`](../../../src/cyo_adventure/storybook/personalization_values.py)),
    in exactly one of three shapes, with a DB CHECK on `slot_type`.
11. **ADR-025 is accepted but not implemented.** `_check_schema_version` requires exact equality
    with `SCHEMA_VERSION = "2.0"`, there is no `SCHEMA_MINOR`, every model sets `extra="forbid"`,
    and `schema/storybook.schema.json` sets `additionalProperties: false`. ADR-026 and ADR-027 are
    parked behind the same gate.
12. **Rule namespaces in use**: `CG`, `L1`, `L2` (through `L2-14`), `PL`, `RL`, `SR`. `CH-*` is free.
13. **The gamebook narrative style exists only at 13-16 and 16+**
    ([`validator/band_profile.py`](../../../src/cyo_adventure/validator/band_profile.py) `_PRODUCTION_CELLS`).
    Every 8-11 and 10-13 production cell is prose.

### 2.1 Catalog measurements (2026-08-05, `skeletons/`)

Measured, not estimated. These numbers replace the arithmetic in the draft, which was wrong.

| Measure | Value |
|---|---|
| Skeletons total | 124 |
| With non-empty `variables` (the backfill population) | 14 |
| Using `once: true` | 5, at 5-6 once-nodes each |
| Canonical names (`might`/`wits`/`nerve`/`archetype`) already in use | **0** |
| Largest config closure | `16+/the-longwinter-station.json`, **51,241** configs (51% of cap), 337ms |
| Second largest | `10-13/the-winter-of-the-wolf-queen.json`, 28,512 |
| Full 14-book walk | 1.18s |

The zero-clash result is load-bearing: reserving the canonical vocabulary is free today and
becomes impossible once any book adopts one of those names for a different meaning.

---

## 3. Architecture: a character is a `VarState`

Opening a book projects the active character into a `{name: value}` map and hands it to the
existing seed path. Books never learn characters exist; G3 name-match does the coupling. A book
declaring `might` picks it up; a book that does not, ignores it.

```
kid taps a book
  -> client reads the active character
  -> projects to VarState  {might: 2, wits: 1, nerve: 0}
  -> startContinuation(story, entryNode=null, characterVarState)
       -> G3: name-match, type-match, clamp to declared bounds
       -> merged into declared initials BEFORE start-node on_enter
  -> saved reading state owns var_state; the seed is never re-applied
```

### 3.1 Entity model

```sql
character
  id                uuid PK
  child_profile_id  uuid NOT NULL REFERENCES child_profile   -- ADR-022 Tier 1 family_scoped
  name              text NOT NULL       -- free text; ADR-023 slot, section 6
  archetype         text NOT NULL CHECK (archetype IN (
                      'scout','guardian','trickster','scholar','healer','wildheart'))
  look              text NOT NULL CHECK (look IN (
                      'avatar_01', ..., 'avatar_12'))         -- closed illustrated set
  is_active         boolean NOT NULL DEFAULT false
  books_completed   integer NOT NULL DEFAULT 0
  created_at, updated_at, retired_at

CREATE UNIQUE INDEX ON character (child_profile_id) WHERE is_active;

character_attribute
  character_id  uuid NOT NULL REFERENCES character ON DELETE CASCADE
  name          text NOT NULL CHECK (name IN (<canonical vocabulary>))
  value_int     integer NULL
  value_bool    boolean NULL
  PRIMARY KEY (character_id, name)
  CHECK (num_nonnulls(value_int, value_bool) = 1)
```

A partial unique index rather than a `child_profile.active_character_id` FK: an FK on the profile
creates a circular reference and needs a composite FK to stop profile A pointing at profile B's
character. The partial index gets uniqueness and ownership for free.

`retired_at` is a soft delete. A saved reading state was seeded from a character; hard-deleting it
orphans the provenance of an in-progress book (section 7.3).

The shape deliberately mirrors `child_profile_personalization`'s (subject, key) plus multi-shape
plus CHECK pattern rather than inventing a new one.

### 3.2 Character and series are mutually exclusive in v1

A book can be both book N+1 of a `carries_state` series and opened with a character. Both compete
for the same one-shot seed slot, and the composition produces cross-product entry states that
neither SR-9 nor the new CH-* rules walk.

**Rule: a book that declares `accepts_character` may not be a non-first book of a `carries_state`
series, and vice versa.** Enforced as `CH-7` (ERROR). Book 1 of a series may accept a character
normally, because it has no carried series state.

This is a v1 scope boundary, not a permanent one. Lifting it requires a combined proof over the
cross-product and should be its own gated decision with its own measurement.

### 3.3 Integrity posture

The seed is untrusted client input (ground truth 8). A child can forge a within-bounds character
sheet via history manipulation. **Accepted**: single-player, own book, no shared score, no unlock
economy.

The guarantee that *does* hold, stated precisely: `CH-2` (section 5.1) requires the declared
variable bounds to **equal** the declared envelope, and G3 clamps every carried int to those
declared bounds. Therefore a forged seed cannot reach a state outside the envelope the book was
proven safe across. Cheating changes difficulty; it can never reach an unvalidated state.

To be recorded as a `#CRITICAL` marker. Must be revisited if rewards or cross-family visibility
ever attach to a character.

> The draft claimed this guarantee came from an `accepts_character` clamp. No such clamp exists at
> runtime; `_clamp` uses declared variable bounds only. The guarantee is real but it is `CH-2`'s
> equality requirement that makes it so, which is why `CH-2` is containment-then-equality below.

---

## 4. Vocabulary and envelope

### 4.1 The vocabulary is a menu, not a mandate

G3 carry is name-match, so an undeclared canonical name is silently ignored rather than an error.
Each book declares only the subset it uses, sized to its own cell. A 16+ long gamebook and an 8-11
prose book can share a character while declaring disjoint variable sets.

### 4.2 Canonical vocabulary v1

| Name | Type | Range | Declared by | Meaning |
|---|---|---|---|---|
| `archetype` | int | 0-6 | prose cells | `0` means **not yet chosen** (section 4.3); `1`-`6` are the six archetypes in roster order (`scout`, `guardian`, `trickster`, `scholar`, `healer`, `wildheart`). Gates flavour choices and prose colour. Never a difficulty check. |
| `might` | int | 0-2 | gamebook cells | Trained force |
| `wits` | int | 0-2 | gamebook cells | Trained cleverness |
| `nerve` | int | 0-2 | gamebook cells | Trained composure |

**Range 0-2, not 0-3.** Three stats at 0-3 gives a 64-state envelope; at 0-2 it is 27. A four-band
degrees-of-success ladder still fits: `>= 2` crit, `== 1` pass, `== 0` with a local resource =
scrape, `== 0` without = fail.

**`archetype` and the stats never coexist in a gamebook.** They do not need to: in a mechanics book
**the stat spread is the archetype** (a Scout is `wits 2 / nerve 1 / might 0`). `archetype` carries
identity only where there are no stats to infer it from, that is, prose cells.

Name and look cost nothing here: `name` is an ADR-023 render-time slot and `look` is a UI column.
Neither is ever a Storybook variable.

**Type boundary.** `character.archetype` is a text enum in the database, because a text enum is
readable in a migration and survives a roster reorder. The Storybook variable is an int, because
Tier-2 conditions are a JSONLogic subset with no string comparison. The projection that builds the
seed `VarState` maps text to the int code above, and that mapping is the single place the roster
order is load-bearing. It must be covered by a test that pins each name to its code, so a future
roster insertion cannot silently renumber live characters.

### 4.3 `archetype = 0` means "not yet chosen", and this is what keeps books publishable

A participating prose book keeps an **in-story build node** gated on `archetype == 0`. From the
book's declared initials (`archetype: 0`) that node is reachable and sets 1-5, so every
archetype-gated flavour branch is visible to the existing Layer-2 walk. A reader arriving with a
character already holding 1-5 simply skips the node.

This is not a convenience. Without it, an exogenous immutable `archetype` makes every non-initial
flavour branch unreachable from declared initials, and **L2-11 (dead branches) errors the book out
before any CH-* rule runs** ([`validator/layer2.py:657-685`](../../../src/cyo_adventure/validator/layer2.py)).
The book would fail its own existing gate. `series.py:389-399` documents the mirror-image of this
exact failure for carried series variables, where the series "gift it if missing" idiom is what
avoids it; an identity variable has no such idiom available, so the build node supplies one.

Consequence: it also reunifies D1 with the exploration doc's original in-story build selection. A
first-time reader builds in-story; a returning reader brings a character. Same book, same graph.

### 4.4 `accepts_character`

```json
"accepts_character": {
  "might": {"min": 0, "max": 2},
  "wits":  {"min": 0, "max": 2},
  "nerve": {"min": 0, "max": 2}
}
```

Envelope size is the product of the ranges. For the gamebook example above, **27 states**; for a
prose book declaring only `archetype` at 0-6, **7 states**. Both are under the existing
`_MAX_ENTRY_STATES = 64`, and `CH-5` errors if a future declaration is not.

A book omitting `accepts_character` accepts no character. This is enforced, not assumed: `CH-6`
(section 5.1) reserves the canonical names so that a book which has not opted in cannot be seeded
by G3 name-match through an accidental name collision.

### 4.5 Envelope cost: measured, and it does not touch the cap

The draft predicted the envelope would multiply per-walk configuration counts. It does not. An
immutable character variable is a constant within a walk, and a constant adds no distinct
`ConfigKey`s. Measured on the worst book in the catalog:

| Measure | Value |
|---|---|
| `the-longwinter-station` baseline | 51,241 configs, `capped=False` |
| Same book, each of 27 envelope states | **51,241 configs every time**, min = max |
| Wall-clock for all 27 walks | **12.15s** |

The envelope multiplies the *number of walks*, not the size of each. **The 100,000 cap stays
unchanged.** The cost is catalog-time wall-clock: roughly 27x the single-book walk, worst case
about 12s per participating book. Catalog validation is not on the request path, so this is
acceptable; it is recorded as a CI budget item in section 8.

**Separate risk, unrelated to characters**: `the-longwinter-station` already sits at 51% of the cap
with no character involved. Books that add character-gated branches have less headroom than the cap
number suggests. `L2-12` already reports capping; section 8 adds a pilot check that a participating
book stays under 25% of cap, per the exploration doc's Phase 1 exit criterion.

---

## 5. Validation

New module `validator/character.py`, namespace `CH-*` (free per ground truth 12). It belongs in its
own namespace rather than extending `L2-*` because, like `SR-*`, it proves a **cross-artifact
handoff**, not a within-story property.

### 5.1 Rules

| Rule | Severity | Check |
|---|---|---|
| `CH-1` | ERROR | Every `accepts_character` name is in the canonical vocabulary AND declared in `variables` with matching type |
| `CH-2` | ERROR | Each envelope range **equals** the declared variable's `min`/`max` |
| `CH-3` | ERROR | For every envelope state, entry raises no Layer-2 error the book does not raise from its own declared initials |
| `CH-4` | ERROR | For every envelope state, a satisfying ending remains reachable |
| `CH-5` | ERROR | Envelope size exceeds `_MAX_ENTRY_STATES` |
| `CH-6` | ERROR | A book that does not declare `accepts_character` may not declare a variable whose name is in the canonical vocabulary |
| `CH-7` | ERROR | A book declaring `accepts_character` is not a non-first book of a `carries_state` series |

`CH-3`/`CH-4` are SR-9's baseline-diff and reachability check with "satisfying exit states of book
N" swapped for "states in the declared envelope". Both read a single `WalkResult` per envelope
state, so the cost is 27 walks, not 54.

**`CH-2` is equality, not containment.** If the envelope were merely contained in the declared
bounds, the two could differ, and G3's clamp to *declared bounds* would silently admit reachable
states the validator never proved. The clamp makes that failure invisible at runtime. Equality is
what makes section 3.3's integrity guarantee true.

**`CH-5` is an ERROR, not a warning.** SR-9 warns because a series chain's entry-state count is
*emergent* from the sending book and the author cannot directly control it. An envelope is
*declared*, so exceeding the cap is an authoring mistake with an obvious fix. Reporting a book
clean over a truncated sample of a declared envelope would be a silent gate failure.

**`CH-6` closes the seeding hole.** Without it, "a book omitting `accepts_character` behaves exactly
as today" is false: G3 name-match seeds *any* book declaring a canonical name, opted in or not. The
catalog scan (section 2.1) shows zero current clashes, so this rule is free to impose now.

### 5.2 The gate must become envelope-aware

`run_gate` walks Layer 2 from declared initials only (ground truth 3). For a participating book,
`run_gate` must additionally run the CH-* rules, and `CH-3`'s baseline diff must be computed against
that same declared-initials run so the two agree on what the baseline is.

The `archetype = 0` idiom (section 4.3) is what keeps the *existing* L2-11 pass green for prose
books, so the gate change is additive: new rules, no change to L2-11's quantification. Gamebook
stats are read in conditions but the book's own declared initials are `0/0/0`, which is inside the
envelope, so the same reasoning holds. If a future book needs a branch reachable *only* at a
non-zero stat, that branch is dead under its own gate and the author must supply an in-book
acquisition path exactly as the series "gift it if missing" idiom does.

### 5.3 Signature granularity

`_l2_error_signatures` keys on `rule_id|node_id` (ground truth 5). Two distinct dead branches on one
node collapse to a single signature, so a *new* dead branch introduced by a seeded entry is masked
if that node already has one from the baseline. `CH-3` must use a signature that includes
`choice_id` where the finding carries one. This is a genuine defect in the shared helper; fixing it
in place also tightens SR-9, which is desirable and must be covered by a regression test that would
have failed before the change.

### 5.4 A rejected optimisation

A merged walk seeded from a synthetic fan-out entry works for `CH-3` (error reachability is a union
property) but not for `CH-4`, which needs per-state attribution. Re-adding the entry state to the
config key costs back exactly the 27x saved. The honest per-state loop ships; the merged walk stays
available as a `CH-3`-only lever if catalog validation time becomes a problem.

---

## 6. Identity: a source change, not a shape change

Personalization is keyed `(child_profile_id, slot_type)`, one value per child forever (ground truth
10), which does not fit a per-character mutable name.

**Resolution: add the slot type, but source its value from the active character row.**
`character.name` is a column; the per-profile values payload gains a `character_name` field resolved
from whichever character is active. No PK change, no DB CHECK migration on `slot_type`, no change to
three-shape validation. The resolver learns one new source.

### 6.1 ADR-023 amendment

| Property | Value | Why |
|---|---|---|
| Slot | `character_name` | New entry in `PERSONALIZATION_FIELDS` |
| Shape | Free text | Same category as `pet_name`, the existing free-text precedent |
| Ring ceiling | Ring 1 only, permanently | Profile-scoped; never renders on another household's device |
| `REAL_PERSON_PERSONALIZATION_FIELDS` | Included | A kid can type their own name. Treating it as fictional would skip the `role_safety` audit; including it forces `role_safety: "protagonist"`, which is also true. |
| Governance | Guardian-set toggle, **default off** | ADR-023's governance model is guardian-controlled and opt-in. A kid-authored value inverts that, so the guardian holds an explicit per-profile enable, sees the current value, and can clear it. |
| Validation | `validator/slots.py` structural plus band-mandatory denylist, at set time **and** at render time | ADR-023's explicit requirement for promoting a stored value into rendered content |
| Purge | `character.name` joins the ADR-023 purge paths | Must be confirmed against the concrete implementation, not asserted; ADR-023:569-570 describes the requirement, not the wiring |

With the toggle off, a character still works: rendering falls back to the existing
`protagonist_first_name` resolution. The character's mechanical and visual identity is unaffected.

`look` is deliberately **not** a slot: it is an avatar in library and reader chrome, never
substituted into prose, so it is an enum column with no compliance surface. Prose rendering of
appearance would be a separate amendment.

Route A is untouched: it operates at the request/generation layer (ground truth 9).

---

## 7. Reader lifecycle and progression

### 7.1 Backtracking and restart are in scope (D10)

Today a seeded read silently loses "Go back a page" and the ADR-026 stop rewind, because replay
starts at `start_node` and a seeded read did not (ground truth 7). Open issue **#460** is the same
defect: RESTART discards carried state.

Both are fixed here rather than shipped as a regression. The fix is to make replay seed-aware: the
recorded path is replayed from the **seeded entry state** rather than from bare declared initials,
so `path[0] === story.start_node` stops being the precondition for Go-back. This requires the seed
to be persisted with the reading state rather than being purely transient, which is also what
section 7.3 needs for provenance. Both engines change, and the conformance corpus covers it.

### 7.2 Seed lifecycle

| Event | Behaviour |
|---|---|
| First open of a book, no saved state | Active character is projected and seeded |
| Subsequent opens | Saved `varState` is authoritative; seed is not re-applied |
| Restart (#460) | Re-seeds from the character bound to that reading state, not from the currently active character |
| Active character changed mid-book | No effect on the in-progress read; the bound character owns it |
| Offline first open | The character is available locally, so the seed applies offline; the bound character id syncs with the reading state |
| Book completed, reopened | Treated as a fresh read and re-seeded from the then-active character |

### 7.3 Progression writeback

On reaching a **satisfying** ending, project the final `var_state` back onto the bound character,
filtered to canonical names, monotone-capped:

```
new_value        = min(canonical_max, max(current_value, exit_value))
books_completed += 1
```

- Nothing is granted on death or setback, so failure costs the run.
- `max()` is monotone-up, so a character never degrades and the envelope stays permanently bounded,
  which is what keeps `CH-3`/`CH-4` provable forever.

Locus, idempotency, and provenance, all of which the draft left undefined:

- **Locus**: server-side, in the reading-completion path, transactionally with the completion record.
  The client never writes character attributes.
- **Idempotency**: keyed on `(reading_state_id, character_id)`. A replayed or re-synced completion
  must not increment `books_completed` twice. The attribute `max()` is naturally idempotent; the
  counter is not, and the counter is the one that needs the key.
- **Provenance**: the reading state records the `character_id` it was seeded from. This is required
  by 7.1, 7.2, and by the soft-delete rationale in section 3.1.
- **Offline**: writeback happens on sync, through the same idempotency key, so an offline completion
  that syncs twice credits once.

### 7.4 Balance risk (recorded with a measurement, not solved)

At three stats capped at 2, a character reaches 2/2/2 fairly quickly and every threshold check
becomes a critical success. Two levers, neither free:

- **Per-book clamping** is already in the design: a late-catalog book declares
  `"might": {"min": 0, "max": 1}`, and because `CH-2` forces the declared variable bounds to match,
  G3's clamp re-creates difficulty.
- **Retirement** is the intended answer, supported by D7.

Per the exploration doc's "measure, do not vibe" criterion, this is an open item with a
measurement (replay rate and K18 ratings on pilot books, split by character maturity), not a guessed
tuning.

---

## 8. Testing

The cases that carry real risk, as distinct from coverage:

- **`CH-2` equality.** An envelope narrower *or* wider than the declared bounds must error. The
  narrower case is the one the runtime hides, and a happy-path-only test proves nothing.
- **`CH-6` namespace reservation.** A book declaring `might` without `accepts_character` must error.
  Without this test the rule can silently become a no-op.
- **`CH-3` signature granularity** (section 5.3). A fixture where the baseline already has one dead
  branch on a node and the seeded entry adds a second on the same node. This test must fail against
  the current `rule_id|node_id` signature.
- **The `archetype = 0` idiom under the existing gate.** A participating prose book must pass
  `run_gate` with L2-11 green *before* any CH-* rule runs. This is the property that makes
  participating books publishable at all.
- **Seed-aware replay conformance in both engines** (section 7.1). Belongs in the conformance corpus
  under `runtime-semantics.md` section 1, not a one-sided unit test.
- **Writeback idempotency.** A completion delivered twice, and an offline completion synced twice,
  must credit `books_completed` once.
- **Archetype code pinning** (section 4.2). A test that pins each roster name to its int code, so a
  roster insertion cannot silently renumber every existing character's archetype.
- **Pilot gate evidence.** Exploration doc Phase 1 exit criterion is a config count under 25% of cap.
  The largest book in the catalog today is at 51%, so this is a real constraint on which skeletons
  can participate; the walk report is the artifact.
- **RLS.** `character` and `character_attribute` are ADR-022 Tier 1 `family_scoped`. Reads happen
  after the principal is built, avoiding the pre-principal chicken-and-egg that bit `device_grant`.
- **CI budget.** Catalog validation gains roughly 12s per participating book. Record the measured
  delta; if it exceeds the CI budget, the section 5.4 lever is the response.

---

## 9. Prerequisites and build order

### 9.1 Prerequisites

**ADR-025 implementation is a hard blocker** (ground truth 11) and is scheduled nowhere: no register
row, no roadmap entry, no issue. The owner has funded it as step 0 (D9). It is not wasted scope:
ADR-026 and ADR-027 are parked behind the same gate. `accepts_character` is in the easy class of
additive field, a catalog-time validation contract that no player reads.

Then:

1. ADR-028 covering all three subsystems, the Option A inspiration-only IP posture (recorded the way
   ADR-023 recorded OD-5), and the section 3.3 integrity posture as a `#CRITICAL` marker
2. ADR-023 amendment per section 6.1
3. SQ-22 / OG5 decision recorded in `pathfinder-structure-exploration.md`; row flipped in
   `story-structure-improvement-plan.md`
4. Capability register citation (K3 state-and-consequence, K18 engagement)
5. Register row plus phase token for the pilot
6. Authoring lessons log appended at the end of any authoring run (mandatory project rule)

### 9.2 Build order

```
0   ADR-025 implementation                            [prereq; unblocks 026/027 too]
1   ADR-028 + ADR-023 amendment + OG5 record          [decisions]
2   canonical vocabulary constants + accepts_character field
3   validator/character.py CH-1..CH-7 + signature fix + tests
4   migration: character, character_attribute, ADR-022 Tier 1 RLS
5   API: character CRUD, activate, values-payload extension
6   both engines: seed persistence + seed-aware replay; closes #460
7   frontend: creator, picker, reader seed wiring
8   pilot skeletons: one 13-16 medium gamebook, one 8-11 prose with the archetype-0 build node
9   progression writeback (server-side, idempotent)
10  authoring docs + cyo-author idiom
```

Steps 2-3 are validator-only and land before any data model exists, so the proof machinery is
testable against hand-written fixtures before a character can be created.

Step 6 is larger than the draft implied. "No new runtime code" was true only for the seed path; the
lifecycle work in section 7.1 is real engine and frontend change in both languages.

---

## 10. What the adversarial review changed

Round-1 verdict was *material rework needed*. All 13 ground-truth claims verified. Recorded here so
round 2 can check the reconciliation rather than re-derive it.

| Finding | Disposition |
|---|---|
| No `accepts_character` clamp exists at runtime; the draft's integrity guarantee was false | **Accepted.** `CH-2` becomes equality (5.1); guarantee restated in 3.3 |
| "A book omitting `accepts_character` behaves as today" is false; G3 seeds any canonical name | **Accepted.** New `CH-6`; catalog scan confirms zero current clashes |
| Participating prose books fail their own L2-11 gate before CH-* runs | **Accepted, with a cheaper fix than proposed.** The reviewer proposed making the gate union-quantified. The `archetype = 0` build-node idiom (4.3) keeps L2-11 green with no change to its quantification |
| Character x series composition is unproven | **Accepted.** Made mutually exclusive in v1 via `CH-7` (3.2) |
| The §3.3 budget arithmetic omits the once-set `ConfigKey` component, a 2^k multiplier | **Falsified by measurement, in both directions.** The catalog has 5-6 once-nodes per affected book, not the 3 assumed, so the reviewer understated k. But the envelope multiplies walk *count*, not per-walk configs: measured 51,241 configs in every one of 27 envelope states. The cap is untouched; the cost is 12.15s wall-clock (4.5) |
| Seed lifecycle collapses after first read; #460 is an unlisted prerequisite | **Accepted.** Section 7.2 defines every path; #460 is in scope (D10) |
| Every seeded read silently loses "Go back" | **Accepted.** Fixed rather than shipped as a regression (7.1) |
| Writeback has no locus, idempotency, provenance, or offline rule | **Accepted.** Section 7.3 |
| `character_name` inverts ADR-023's guardian-set, default-off governance | **Accepted.** Guardian toggle, default off, with fallback (6.1) |
| `_l2_error_signatures` drops `choice_id` and can mask same-node deltas | **Accepted.** Section 5.3, with a regression test that fails before the fix |
| `CH-5` should be ERROR, not WARNING | **Accepted**, with the reasoning made explicit in 5.1: declared, not emergent |
| Backfill population is 14 skeletons, not 2 | **Accepted.** Confirmed by scan (2.1) |
| Is funding ADR-025 the intended price? | Owner: yes (D9) |
| Is losing "Go back" acceptable for a pilot? | Owner: no, fix it (D10) |
| Shrink the envelope to fit the cap? | Moot: measurement shows the cap is not threatened (D11) |
