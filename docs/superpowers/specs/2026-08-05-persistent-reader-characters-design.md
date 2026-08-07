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

> **Status**: Approved design | **Date**: 2026-08-05, revised 2026-08-06
> **Gate**: SQ-22 / OG5 ruled **GO** by the owner
> **Next ADR number**: ADR-028
> **Build progress**: step 0 of section 9.2 (ADR-025 implementation) shipped 2026-08-06 in PR
> [#636](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/636). Steps 1 onward are
> unstarted. Measurements and "ground truth" statements in section 2 were taken on 2026-08-05;
> where step 0 has since falsified one, the item says so inline rather than being silently
> rewritten, so the design's original reasoning stays auditable.

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
| D12 | Promote an 8-11 skeleton to Tier 2 for the prose pilot, rather than piloting prose at 10-13 | Owner choice, post-round-2 |

This spec incorporates **two** adversarial review passes (`senior-architecture-reviewer`; round 1
on the draft, verdict *material rework needed*; round 2 on this spec, verdict *needs revision*).
Every finding was independently verified against code before being folded in. **Section 10 records
what changed, what was falsified, and one round-1 disposition that round 2 proved wrong.**

---

## 2. Ground truth

Each claim below was verified by reading the code, not inferred. They drive the whole design.

1. **The carried-state runtime already exists in both engines.**
   `player/engine.py:58` `start_continuation(carried)`
   merges carried values into declared initials *before* the start node's `on_enter` runs.
   WS-G G3 carry rules: name-match against a declared variable, type-match or skip, int clamped
   to the receiving variable's declared bounds. `frontend/src/player/engine.ts` mirrors it;
   divergence is a conformance failure under `runtime-semantics.md` section 1.
2. **The walk already accepts a carried entry.** `walk_configurations(story, cap=100_000, carried=...)`
   in `validator/walk.py:95-133`.
3. **`validate_layer2` already accepts `carried=`.** The gate simply never passes it:
   `validator/gate.py:140` calls `validate_layer2(story)`
   with declared initials only. This makes the Layer-2 plumbing for envelope proofs cheap; the
   *semantics* change in section 5.2 is the real work.
4. **SR-9 is the proof template.** `validator/series.py`
   proves a receiving book safe when entered with each distinct satisfying exit state of the
   sending book: `_satisfying_exit_states`, an `_l2_error_signatures` baseline diff, and
   `_satisfying_ending_reachable`. Caps at `_MAX_ENTRY_STATES = 64` and warns when the cap bites.
5. **`_l2_error_signatures` keys on `rule_id|node_id` only** (series.py:325-339). It deliberately
   drops the message because the message embeds variable state. It also drops `choice_id`, so two
   distinct dead branches on the same node collapse to one signature.
6. **The frontend seed is one-shot.** `ReaderPage.tsx` applies a continuation only when no saved
   reading state exists. The saved `varState` is authoritative thereafter.
7. **Backtracking is already disabled for seeded reads, deliberately.**
   `frontend/src/player/engine.ts:297-300` returns `null`
   from the Go-back path when `live.path[0] !== story.start_node`, with a comment explaining that
   a non-start entry cannot be reproduced by replay. Open issue **#460** (RESTART discards carried
   state) is the same defect class.
8. **The seed is attacker-shapeable.** `frontend/src/player/series.ts` carries an `#ASSUME: security`
   marker: the seed arrives as router `location.state`, is shape-checked by `parseContinuation`, and
   every value is re-filtered by `startContinuation`.
9. **`PERSONALIZATION_FIELDS` is a closed frozenset** of 11 slot fields
   (`storybook/theme_contract.py:74-97`).
   `REAL_PERSON_PERSONALIZATION_FIELDS` forces any slot naming a real person to declare `role_safety`.
   Free text is already permitted for `pet_name` and, via guardian `display_name`, for
   `protagonist_first_name`. Route A (self-naming disallowed) operates only at the
   request/generation layer and is orthogonal (ADR-023 section 4).
10. **Personalization storage is one value per `(child_profile_id, slot_type)`**
    (`storybook/personalization_values.py`),
    in exactly one of three shapes, with a DB CHECK on `slot_type`.
11. ~~**ADR-025 is accepted but not implemented.**~~ **Superseded 2026-08-06 by PR
    [#636](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/636)**, which implemented it.
    As measured on 2026-08-05 this read: `_check_schema_version` requires exact equality with
    `SCHEMA_VERSION = "2.0"` and there is no `SCHEMA_MINOR`. Both are now false. `SCHEMA_MAJOR`
    and `SCHEMA_MINOR` exist, `SCHEMA_VERSION` is derived from them, and the check accepts any
    same-major minor at or below `SCHEMA_MINOR`. Still true and still load-bearing for this
    design: every model sets `extra="forbid"` and `schema/storybook.schema.json` sets
    `additionalProperties: false`, so `accepts_character` must be added as an enumerated field at
    a declared minor rather than slipped in as an unknown key. ADR-026 and ADR-027 were parked
    behind the same gate and are now unblocked.
12. **Rule namespaces in use**: `CG`, `L1`, `L2` (through `L2-14`), `PL`, `RL`, `SR`. `CH-*` is free.
13. **The gamebook narrative style exists only at 13-16 and 16+**
    (`validator/band_profile.py` `_PRODUCTION_CELLS`).
    Every 8-11 and 10-13 production cell is prose.

### 2.1 Catalog measurements (2026-08-05, `skeletons/`)

Measured, not estimated. These numbers replace the arithmetic in the draft, which was wrong.

| Measure | Value |
|---|---|
| Skeletons total | **61** |
| (`skeletons/*/*.json` file count, for reference) | 124 = 61 skeletons + 47 `.contract.json` + 16 `.lineage.json` sidecars |
| With non-empty `variables` (the backfill population) | 14 of 61 (23%) |
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

```text
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
  child_profile_id  uuid NOT NULL REFERENCES child_profile (id) ON DELETE CASCADE
                                                          -- ADR-022 Tier 1 family_scoped
  name              text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 32)
                                                          -- ADR-023 slot, section 6
  archetype         text NOT NULL CHECK (archetype IN (
                      'scout','guardian','trickster','scholar','healer','wildheart'))
  look              text NOT NULL CHECK (look IN (
                      'avatar_01', ..., 'avatar_12'))         -- closed illustrated set
  is_active         boolean NOT NULL DEFAULT false
  books_completed   integer NOT NULL DEFAULT 0 CHECK (books_completed >= 0)
  created_at, updated_at, retired_at

  CHECK (NOT (is_active AND retired_at IS NOT NULL))       -- see "Active and retired" below

CREATE UNIQUE INDEX ON character (child_profile_id) WHERE is_active;

character_attribute
  character_id  uuid NOT NULL REFERENCES character (id) ON DELETE CASCADE
  name          text NOT NULL CHECK (name IN ('archetype','might','wits','nerve'))
  value_int     integer NOT NULL
  PRIMARY KEY (character_id, name)

  -- The vocabulary contract of section 4.2, enforced in the database rather
  -- than only in application code. Per-name, because the ranges differ.
  CHECK (
       (name = 'archetype'               AND value_int BETWEEN 0 AND 6)
    OR (name IN ('might','wits','nerve') AND value_int BETWEEN 0 AND 2)
  )
```

A partial unique index rather than a `child_profile.active_character_id` FK: an FK on the profile
creates a circular reference and needs a composite FK to stop profile A pointing at profile B's
character. The partial index gets uniqueness and ownership for free.

`retired_at` is a soft delete. A saved reading state was seeded from a character; hard-deleting it
orphans the provenance of an in-progress book (section 7.3).

**Active and retired is not a legal state.** Without the table CHECK above, a row can be both
`is_active = true` and retired. Such a row still matches the partial unique index, so it silently
blocks activating any replacement character while presenting to the reader as deleted: the profile
has no usable character and no error explains why. The CHECK makes the state unrepresentable, which
means retirement and activation must move together: **retiring the active character and activating
its replacement is one transaction**, clearing `is_active` on the outgoing row before setting it on
the incoming one. Retiring with no replacement simply leaves the profile with no active character,
which is a legal state.

**`value_bool` is deliberately absent in v1.** Every name in the canonical vocabulary (section 4.2)
is an integer, so a nullable two-shape column plus `num_nonnulls(...) = 1` would buy nothing except
a way to store an attribute no rule can read. A single `NOT NULL` integer column lets the range
CHECK above be unconditional. This is the one place the shape does **not** mirror
`child_profile_personalization`'s multi-shape pattern; adding a second shape later is an ordinary
additive migration, and should be gated on a canonical name that actually needs it rather than
provisioned in advance.

Otherwise the shape deliberately mirrors `child_profile_personalization`'s (subject, key) plus
CHECK pattern rather than inventing a new one.

**Deletion and retention.** `child_profile_id` cascades: a character is meaningless without its
profile, and ADR-018 children's-privacy deletion must not leave an orphan row holding a child-chosen
name. `character_attribute` cascades from `character` for the same reason. Note what cascade does
*not* cover: a `character_name` value already materialized into a published Storybook blob or a
saved reading state is not reachable by FK. Section 6.1 owns that path.

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

The guarantee that *does* hold, stated precisely, rests on **four** rules and fails if any one of
them is weakened:

1. `CH-2` equality: the declared variable bounds **equal** the declared envelope, so the envelope
   the validator walked is exactly the range the clamp permits.
2. `CH-2` canonical containment: those bounds lie within the canonical range, so the clamp cannot
   be widened past the vocabulary by an authoring mistake.
3. `CH-1` set equality: no canonical variable is carried that the envelope did not vary, so there
   is no unproven dimension for a forged seed to move in.
4. `CH-6` namespace reservation: a book that does not opt in cannot declare a canonical name at
   all, so it can never receive a carry it was not proven for.

Given all four, G3's clamp to declared bounds is equivalent to a clamp to the proven envelope, and
a forged seed cannot reach a state outside it. Cheating changes difficulty; it can never reach an
unvalidated state.

To be recorded as a `#CRITICAL` marker naming all four rules, so that weakening any one of them in
future shows up as breaking a stated invariant rather than as a local rule change. Must be
revisited if rewards or cross-family visibility ever attach to a character.

> The draft claimed this guarantee came from an `accepts_character` clamp. No such clamp exists at
> runtime; `_clamp` uses declared variable bounds only. The guarantee is real but it is `CH-2`'s
> equality requirement that makes it so, which is why `CH-2` is containment-then-equality below.

### 3.4 Authorization and RLS

#### `character` cannot be Tier 1 as drawn

Section 3.1 annotates `child_profile_id` with "ADR-022 Tier 1 family_scoped", but the table as
drawn carries no `family_id` column, and ADR-022's Tier 1 policy shape is a flat
`family_id::text = current_setting('app.family_id', true)` predicate. ADR-022's own technical-debt
clause resolves the case explicitly: a table scoped by `child_profile_id` rather than a direct
`family_id` needs either a denormalized `family_id` (preferred, keeps the predicate flat) or a
join-based predicate (discouraged, per-row cost), and any table that cannot carry a flat
`family_id` is **demoted to Tier 2 pending a denormalization migration** rather than given a
subquery predicate.

So this is a choice the design has to make, not an annotation it can assert:

| Option | Consequence |
| --- | --- |
| **Denormalize `family_id` onto `character`** (preferred) | Tier 1 as claimed. Costs a column plus the invariant that it always matches `child_profile.family_id`, which needs an FK to `(family_id, id)` on `child_profile` or a trigger; a drifted denormalized key is an RLS bypass, not a stale cache. |
| Leave it Tier 2 | The annotation in 3.1 is wrong and must be corrected. Application-layer `authorize_family()` scoping becomes the only control for this table, which is precisely the single-missed-`WHERE` exposure ADR-022 exists to reduce. |

`character_attribute` is one further hop from `family_id` (via `character`), so it inherits the
same decision and, if `character` is denormalized, is the stronger candidate for Tier 2: it holds
no name, no free text, and is meaningless without the parent row.

`character_book_completion` (section 7.3) is reachable from `reading_state`, which ADR-022 already
lists as a Tier 1 candidate; it should follow whatever `reading_state` does rather than being
decided separately.

#### Authorization matrix

The API step in the build order needs this settled before it is written, because "guardian-set
toggle, default off" (section 6.1) and "a kid creates a character" are different principals acting
on the same row:

| Operation | Kid (device-granted session) | Guardian (own family) | Admin |
| --- | --- | --- | --- |
| Create character | Yes, for own profile | Yes, for a profile in own family | No (same posture as profile-create, which is 403 by design) |
| Read own characters | Yes | Yes | Via the review surface only |
| Rename (`character.name`) | Yes, subject to the `character_name` governance toggle and set-time validation (6.1) | Yes | No |
| Change `look` / `archetype` | Yes | Yes | No |
| Activate / retire | Yes | Yes | No |
| Delete | No (retire only) | Yes | No |
| Write attributes / `books_completed` | **No principal.** Server-side writeback only (7.3) | **No** | **No** |

The last row is the load-bearing one: attributes are earned, never set. Exposing any write path for
them, even to an admin, would make the monotone-up property a claim about the UI rather than an
invariant, and section 5.1's proofs depend on it holding absolutely.

### 3.5 What a character does not touch

Stated as invariants rather than left to inference, because each is a place a reader of this spec
could reasonably assume the opposite, and because two of them are what keep the feature cheap:

- **Generation.** No character input reaches the LLM pipeline. A book is authored once, from its
  skeleton and request brief, and is byte-identical for every character that opens it. The
  character affects only the entry `var_state` handed to an already-published, already-validated
  blob. This is the "preset books" half of the title and it is what makes the envelope proof
  possible at all: the artifact being proven never varies.
- **Cover art.** Covers are per-storybook, not per-character or per-reader. A character's `look` is
  an avatar rendered in library and reader chrome (section 6.1) and is never composited into cover
  art, which would multiply ADR-017 cover generation by the character population and put an
  unreviewed image in front of a child.
- **Moderation and approval.** Nothing about a character re-opens an approved book. The approval
  gate ran against the blob, and the character changes no blob content. The one child-authored
  string in the system, `character.name`, is governed at set time and render time by the ADR-023
  slot rules (section 6.1) rather than by re-running the story through moderation.
- **Other readers.** Ring 1 only, permanently (section 6.1). A character is never visible to
  another household, so it carries no social surface, no leaderboard, and no shared score. Section
  3.3's "accepted" verdict on seed forgery depends on this and must be revisited if it changes.

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

### 4.3 `archetype = 0` means "not yet chosen"

A participating prose book keeps an **in-story build node** that sets `archetype` to 1-6. From the
book's declared initials (`archetype: 0`) that node is reachable, so every archetype-gated flavour
branch is visible to the existing declared-initials Layer-2 walk. This is verified, not reasoned:
`_ever_visible_choice_ids` (`layer2.py:628-642`)
accumulates a **global** set across all configurations and `_check_dead_branches` (:657-685) tests
membership in it, so one visible configuration anywhere clears a choice permanently. Synthetic
fixtures of this shape pass the declared-initials walk with zero errors.

Without it, an exogenous immutable `archetype` makes every non-initial flavour branch unreachable
from declared initials and L2-11 errors the book out of publication before any CH-* rule runs.
`series.py:389-399` documents the mirror image for carried series variables, where the "gift it if
missing" idiom plays the same role.

It also reunifies D1 with the exploration doc's original in-story build selection: a first-time
reader builds in-story, a returning reader brings a character, same book and same graph.

#### 4.3.1 The build node must be bypassed, not gated

The build node's *own* choices must be gated on `archetype == 0`, so a reader arriving with 1-6
does not rebuild. If the book always routes **through** the build node, that reader lands on a page
where every choice is invisible: a zero-button page. This is a runtime break, not a validator
artifact (`player/engine.py:105-117`; `choose` raises
at :167-169), and it also raises `L2-9` (stateful dead end) and `L2-10`.

**Required shape**: a *gate node* precedes the build node and routes past it when `archetype != 0`.
The build node is entered only when there is a build to do. A shape where the build node is always
entered is non-conforming and must be rejected in authoring review.

#### 4.3.2 The build node makes `archetype` mutable, which costs 6x on the baseline walk

A declared-but-never-set variable is a constant and costs nothing (section 4.5). The build node
sets it, so `archetype` takes six distinct values along different paths and every downstream node
forks into six variable states. Measured by injecting the idiom into real catalog skeletons:

| Book | Baseline | With the idiom |
|---|---|---|
| `10-13/the-glass-comet` | 638 | 3,829 (**6.00x**) |
| `10-13/the-flooded-quarter` | 19,236 | **capped** |
| `10-13/the-winter-of-the-wolf-queen` | 28,512 | **capped** |

`L2-12` capping is an immediate ERROR (`layer2.py:129-131`),
so a book whose base closure exceeds roughly 100,000 / 6 = **16,600 configurations cannot host a
six-way build node at all**. `CH-8` (section 5.1) enforces this as a pre-flight check rather than
letting authors discover it as an opaque L2-12.

This cost applies only to prose books with a build node. Gamebook stats are seeded, not built
in-story, so they stay constant within a walk and cost nothing.

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

**Scope of this result, precisely.** It holds for a variable that is *seeded and never set in-book*,
which is every gamebook stat. It does **not** hold for a prose book's `archetype`, because the build
node sets it and a mutable variable does multiply the walk. Section 4.3.2 measures that case
separately, and `CH-8` gates it. The two measurements were originally taken in isolation and their
composition was not measured, which is exactly how the draft came to state a general claim that was
only true of half the design.

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
| `CH-1` | ERROR | **Set equality, both directions.** Every `accepts_character` name is in the canonical vocabulary and declared in `variables` with matching type, **and** every canonical-vocabulary name appearing in `variables` also appears in `accepts_character` |
| `CH-2` | ERROR | Each envelope range **equals** the declared variable's `min`/`max`, **and** that range satisfies `min <= max` and lies within the canonical range for that name (section 4.2) |
| `CH-3a` | ERROR | **Union-quantified.** A conditional choice that is invisible in *every* configuration across the baseline walk and all envelope walks combined is a dead branch |
| `CH-3b` | ERROR | **Per-state.** For every envelope state, entry raises no `L2-9`, `L2-10`, or `L2-14` error the book does not raise from its own declared initials |
| `CH-4` | ERROR | For every envelope state, a satisfying ending remains reachable |
| `CH-5` | ERROR | Envelope size exceeds `_MAX_ENTRY_STATES` |
| `CH-6` | ERROR | A book that does not declare `accepts_character` may not declare a variable whose name is in the canonical vocabulary |
| `CH-7` | ERROR | A book declaring `accepts_character` is not a non-first book of a `carries_state` series |
| `CH-8` | ERROR | A book with a build node whose base closure exceeds `cap / (build_node_arity)` configurations (section 4.3.2) |

#### The `CH-3` split is not a refinement, it is the correction of a fatal error

The draft specified a single per-state `CH-3`: "for every envelope state, no Layer-2 error the book
does not raise from its own declared initials". **That rule rejects every participating book**, and
it does so by construction rather than by accident.

Character-gated content means that in envelope state `archetype = 3`, the branches gated on
`archetype` values 1, 2, 4, 5, and 6 are *correctly* invisible. A per-state L2-11 check reads each
of those as a new dead branch. Measured on synthetic fixtures: 6 to 8 new errors per non-zero
envelope state, including the build node's own choices. Section 4.3 and the draft's `CH-3` directly
contradicted each other, and the contradiction is intrinsic to the feature: **per-state dead-branch
quantification is incompatible with character-gated content of any kind**, build node or not.

So the round-1 reviewer's union-quantification finding was right, and section 10's original
disposition ("accepted, with a cheaper fix") was wrong. The `archetype = 0` idiom solves a genuine
and separate problem, keeping the *existing* declared-initials gate green so participating books
stay publishable, and section 4.3 is confirmed correct about that. It does not remove the need to
re-quantify the new rule.

The split is by rule semantics, not convenience:

- **`L2-11` is a union property.** "This branch is unreachable for anybody" is the defect. Whether
  it is reachable in *this* state is not.
- **`L2-9`, `L2-10`, `L2-14` are per-state properties.** A dead end, an inescapable loop, or a
  decision offering only forbidden outcomes is a real defect for the reader who hits it, even if
  another envelope state avoids it. These stay per-state with a baseline diff.

`CH-3b`/`CH-4` are SR-9's baseline diff and reachability check with "satisfying exit states of book
N" swapped for "states in the declared envelope". `CH-3a` needs the union of `_ever_visible_choice_ids`
across all walks, so all walks must complete before it can report. All three read one `WalkResult`
per envelope state, so the cost is 27 walks, not 81.

**`CH-1` is set equality, not one-way membership.** Checking only that each `accepts_character`
name is declared in `variables` leaves the converse open, and the converse is the dangerous
direction. G3 carry is name-match against *declared variables*, so a book that declares `wits` in
`variables` but omits it from `accepts_character` still receives `wits` at runtime, from a
dimension no envelope walk ever varied. The book would be proven safe across an envelope that does
not describe the states it can actually enter, which is section 3.3's guarantee failing silently
rather than loudly. `CH-6` does not close this: it governs books that do **not** opt in, and this
is exactly the opted-in case. So for a book declaring `accepts_character`, the set of canonical
names in `variables` and the set in `accepts_character` must be identical. Non-canonical variables
are unaffected and may be declared freely; G3 never carries them.

**An empty envelope is legal and means "declares the field, accepts nothing".** `accepts_character:
{}` on a book with no canonical variables satisfies `CH-1` vacuously and produces exactly one
envelope walk, the baseline. It is distinct from omitting `accepts_character` entirely, which
leaves the book outside the feature and under `CH-6`. The distinction is worth keeping because it
lets a book opt in structurally (and be listed as character-compatible) before it declares any
stat. `CH-3a`, `CH-4`, and `CH-5` must each be defined on the one-walk case rather than assuming
`n >= 1` non-baseline states; a regression test covers the empty envelope specifically.

**`CH-2` is equality, not containment, *and* is bounded by the canonical range.** Two separate
requirements that are easy to conflate:

- *Envelope equals declared bounds.* If the envelope were merely contained in the declared bounds,
  the two could differ, and G3's clamp to *declared bounds* would silently admit reachable states
  the validator never proved. The clamp makes that failure invisible at runtime. Equality is what
  makes section 3.3's integrity guarantee true.
- *Declared bounds sit inside the canonical range.* Equality alone does not bound the pair. A book
  could declare `might: -1..3` or `archetype: 0..7`, satisfy `CH-2` because the envelope matches,
  and thereby prove itself safe across states the vocabulary does not define. The database CHECK in
  section 3.1 stops a *stored* character holding such a value, but the seed is untrusted client
  input (section 3.3) and G3 clamps to declared bounds, so a forged `might: 3` would survive into a
  book that declared `0..3`. Requiring `canonical_min <= min <= max <= canonical_max` is what makes
  the clamp equivalent to the vocabulary. A **narrower** per-book range stays legal and is expected:
  a gentle 8-11 book may accept `might: 0..1` and be proven across two states rather than three.

**`CH-5` is an ERROR, not a warning.** SR-9 warns because a series chain's entry-state count is
*emergent* from the sending book and the author cannot directly control it. An envelope is
*declared*, so exceeding the cap is an authoring mistake with an obvious fix. Reporting a book
clean over a truncated sample of a declared envelope would be a silent gate failure.

**`CH-6` closes the seeding hole.** Without it, "a book omitting `accepts_character` behaves exactly
as today" is false: G3 name-match seeds *any* book declaring a canonical name, opted in or not. The
catalog scan (section 2.1) shows zero current clashes, so this rule is free to impose now.

### 5.2 The gate must become envelope-aware

`run_gate` walks Layer 2 from declared initials only (ground truth 3). For a participating book,
`run_gate` must additionally run the CH-* rules, and `CH-3b`'s baseline diff must be computed against
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
if that node already has one from the baseline. `CH-3b` must use a signature that includes
`choice_id` where the finding carries one.

Fixing it in place also tightens SR-9. That is safe in principle and verified in practice:
`rule|node|choice` strictly refines `rule|node`, so the set of new findings can only grow, never
shrink, and no currently-reported finding can disappear. Only `L2-11` carries a `choice_id`, so the
blast radius is one rule. All 27 series tests pass under both signatures, and the `brass-lantern`
catalog chain is byte-identical under both with zero baseline L2-11 findings to unmask.

**Merge gate.** The four skipped Wyrmreach trilogy tests (`test_series.py:655-675`) depend on
`out/*.filled.json` fixtures that are absent from the tree, and Wyrmreach is the only real live
`carries_state` chain. `validate_series` runs on the approve path
(`publishing/service.py:409-416`), so a chain
turned newly red would block approval of an already-published series at runtime. **The `choice_id`
change lands only after those fixtures are restored and that chain is confirmed green under both
signatures.**

### 5.4 A rejected optimisation

A merged walk seeded from a synthetic fan-out entry works for `CH-3a` (dead-branch visibility is a union
property) but not for `CH-4`, which needs per-state attribution. Re-adding the entry state to the
config key costs back exactly the 27x saved. The honest per-state loop ships; the merged walk stays
available as a `CH-3a`-only lever if catalog validation time becomes a problem.

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
| Purge | `character.name` joins the ADR-023 purge paths | Must be confirmed against the concrete implementation, not asserted; ADR-023:569-570 describes the requirement, not the wiring. See "Storage contract" below, which is why this cannot be left as an assertion. |

With the toggle off, a character still works: rendering falls back to the existing
`protagonist_first_name` resolution. The character's mechanical and visual identity is unaffected.

#### Storage contract: `character_name` has no personalization row

This is the consequence of "source its value from the active character row", and it needs stating
because every other slot behaves the other way:

- Every other slot in `PERSONALIZATION_FIELDS` stores its value as a
  `child_profile_personalization` row keyed `(child_profile_id, slot_type)`.
- `character_name` stores **nothing** there. The values payload synthesizes it at resolve time from
  `character.name` of the active character. There is no row to find, update, or delete.

Three consequences follow, and each is work rather than a note:

1. **Any purge, export, or audit that enumerates `child_profile_personalization` rows will miss
   `character_name` silently.** It will not error; it will report a clean sweep having never seen
   the value. Under ADR-018 children's-privacy deletion that is the worst failure shape available:
   a deletion path that reports success while a child-typed name survives in `character.name`. The
   purge must therefore be extended to the `character` table explicitly, not assumed to be covered.
   The `ON DELETE CASCADE` in section 3.1 covers profile deletion; it does **not** cover a
   slot-level clear, where the profile stays and only the value must go.
2. **A slot-level clear needs defined semantics.** Clearing `character_name` cannot delete a row,
   so it means one of: turn the governance toggle off (value retained, not rendered), or blank
   `character.name` (which the `char_length(name) >= 1` CHECK forbids). The design takes the first:
   **clearing the slot turns the toggle off and rendering falls back to
   `protagonist_first_name`.** A guardian who wants the name *gone* rather than unrendered retires
   or deletes the character, which is a character operation, not a slot operation. The guardian UI
   must say which of the two it is doing.
3. **The set of slots a purge must visit is no longer derivable from `PERSONALIZATION_FIELDS`.**
   That constant is the vocabulary, not the storage map, and `character_name` is the first member
   whose storage lives outside the personalization table. Whatever enumerates purge targets needs
   to be its own explicit list with a test that every `PERSONALIZATION_FIELDS` member is accounted
   for by exactly one storage path, so the next externally-sourced slot fails loudly instead of
   inheriting this gap.

There is no `PURGEABLE_SLOT_TYPES` constant in the tree today (verified 2026-08-06), so item 3 is
creating that map, not extending one.

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

**The binding is server-derived, never client-supplied.** Ground truth 8 says the seed *values* are
attacker-shapeable and section 3.3 accepts that, because `CH-1`/`CH-2`/`CH-6` plus the clamp bound
what a forged value can reach. The character *identity* is a different matter and is not covered by
that argument: if `reading_state.character_id` were accepted from the request body, a kid could
bind a read to another profile's character and, through the writeback in 7.3, credit progression
onto a character they do not own. That crosses the profile boundary the whole envelope argument
assumes.

So on first open the server resolves the bound character itself, as
`SELECT id FROM character WHERE child_profile_id = <authenticated profile> AND is_active`, and
ignores any client-provided id. The client supplies *values* (which are re-filtered and clamped)
and never an identity. The one place an id crosses the wire is offline sync, where the reading
state carries the `character_id` the server itself assigned at first open; on sync the server
re-validates that the id still belongs to the same profile before accepting the completion, rather
than trusting the round trip.

### 7.3 Progression writeback

On reaching a **satisfying** ending, project the final `var_state` back onto the bound character,
filtered to canonical names, monotone-capped:

```text
new_value        = min(canonical_max, max(current_value, exit_value))
books_completed += 1
```

- Nothing is granted on death or setback, so failure costs the run.
- `max()` is monotone-up, so a character never degrades and the envelope stays permanently bounded,
  which is what keeps `CH-3a`/`CH-3b`/`CH-4` provable forever.

Locus, idempotency, and provenance, all of which the draft left undefined:

- **Locus**: server-side, in the reading-completion path, transactionally with the completion record.
  The client never writes character attributes.
- **Idempotency**: keyed on `(reading_state_id, character_id)`, **and the key must be a unique
  database constraint, not a lookup**. See "Idempotency is a constraint, not a check" below.
- **Provenance**: the reading state records the `character_id` it was seeded from. This is required
  by 7.1, 7.2, and by the soft-delete rationale in section 3.1, and it needs schema of its own; see
  "Reading-state columns" below.
- **Offline**: writeback happens on sync, through the same constraint, so an offline completion that
  syncs twice credits once.

#### Idempotency is a constraint, not a check

Reading `(reading_state_id, character_id)` and branching on "no prior completion found" is a
read-modify-write, and two concurrent syncs (the common case: a device reconnecting while the same
account has the book open elsewhere) can both observe no prior row and both increment. The key has
to be enforced by the database:

```sql
character_book_completion
  reading_state_id  uuid NOT NULL REFERENCES reading_state (id) ON DELETE CASCADE
  character_id      uuid NOT NULL REFERENCES character (id)     ON DELETE CASCADE
  completed_at      timestamptz NOT NULL DEFAULT now()
  PRIMARY KEY (reading_state_id, character_id)
```

The writeback is then, in one transaction: `INSERT ... ON CONFLICT DO NOTHING`, and increment
`books_completed` **only if that insert reported a row**. A duplicate sync inserts nothing and
increments nothing.

The attribute update has the same hazard in a quieter form. `new_value = min(canonical_max,
max(current_value, exit_value))` is idempotent as a *function* but not as a read-then-write: two
transactions reading `might = 0` and writing `1` and `2` respectively can interleave so the `2` is
lost. Compute it in the statement rather than in application code:

```sql
UPDATE character_attribute
   SET value_int = LEAST(:canonical_max, GREATEST(value_int, :exit_value))
 WHERE character_id = :character_id AND name = :name;
```

Row-level locking then makes the monotone-up property hold under concurrency, which matters because
section 5.1's proofs depend on it: a lost update is a character moving *down*, and a character that
can move down breaks the "envelope stays permanently bounded" argument that `CH-3a`/`CH-3b`/`CH-4`
rest on.

#### Reading-state columns

Sections 7.1, 7.2, and the provenance bullet above all require the reading state to persist what it
was seeded from and with. That is schema on an existing table, and it is missing from the build
order's migration step (section 9.2 step 4 creates only `character` and `character_attribute`):

| Column | Purpose |
| --- | --- |
| `character_id uuid NULL REFERENCES character (id) ON DELETE SET NULL` | The bound character (7.2 "Restart", 7.3 provenance). `NULL` for an unseeded read, and `SET NULL` rather than `CASCADE` because losing the character must not delete a child's in-progress book. This is also why `retired_at` is a soft delete: an ordinary retirement keeps the row, and the FK, intact. |
| `seed_var_state jsonb NULL` | The projected entry state actually applied, so seed-aware replay (7.1) can restart from it without re-projecting from a character that may since have changed. |

Both are additive and nullable, so the migration is safe on existing rows: every current reading
state is an unseeded read, which is exactly what `NULL` in both columns means.

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
- **`CH-3b` signature granularity** (section 5.3). A fixture where the baseline already has one dead
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
- **`CH-3a` must accept what `CH-3b` would reject.** A fixture with six archetype-gated branches,
  validated across the full envelope. Every non-zero state leaves five of them invisible, so a
  per-state dead-branch check reports five errors and the union check reports none. This is the
  single test that distinguishes a working rule from the one that rejects the entire feature; write
  it first, and confirm it fails against a per-state implementation.
- **The bypass-gate shape** (4.3.1). A returning reader with `archetype != 0` must reach a page with
  at least one visible choice. The always-entered shape must be rejected: assert the zero-button
  page raises, so the broken shape cannot be authored by accident.
- **`CH-8` against the real catalog.** `the-flooded-quarter` and `the-winter-of-the-wolf-queen` must
  be rejected by `CH-8` *before* they reach L2-12, and `the-glass-comet` must pass. Using real
  skeletons rather than fixtures is the point: the threshold is calibrated against the catalog.
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

**ADR-025 implementation was a hard blocker** (ground truth 11) and, as written on 2026-08-05, was
scheduled nowhere: no register row, no roadmap entry, no issue. The owner funded it as step 0 (D9).

**Status as of 2026-08-06: step 0 is done.** PR
[#636](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/636) implemented the accepted range,
so this prerequisite is discharged and ADR-026 and ADR-027 are unblocked along with it. Two
residues of that work are scheduled rather than closed: `UW-A45` (nothing ties the emitted
`schema_version` stamp to `SCHEMA_VERSION`; the owner ruled this ships as a validator rule
alongside the first `SCHEMA_MINOR` bump) and `UW-C26` / `AL-080` (the importer's duplicate
acceptance rule). Neither blocks the work below.

`accepts_character` remains in the easy class of additive field, a catalog-time validation contract
that no player reads. Note the interaction with `UW-A45`: under the ruled design, a book using
`accepts_character` must declare a `schema_version` at or above the minor that introduces the
field, so the field's minor bump and that validator rule land together.

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

```text
0   ADR-025 implementation                            [DONE 2026-08-06, PR #636]
1   ADR-028 + ADR-023 amendment + OG5 record          [decisions]
2   canonical vocabulary constants + accepts_character field
3   validator/character.py CH-1..CH-8 + tests
    (CH-3a union / CH-3b per-state, per 5.1; the signature fix is NOT here)
4   migration: character, character_attribute, character_book_completion,
    reading_state.character_id + .seed_var_state (7.3), ADR-022 Tier 1 RLS
5   API: character CRUD, activate, values-payload extension
    (authorization matrix in section 3.4; retire+activate is ONE transaction, 3.1)
6   both engines: seed persistence + seed-aware replay; closes #460
7   frontend: creator, picker, reader seed wiring
8a  promote 8-11/the-storm-chasers-club Tier 1 -> Tier 2 (see below)
8b  pilot skeletons: one 13-16 medium gamebook; the promoted 8-11 prose book
9   progression writeback (server-side, idempotent)
10  authoring docs + cyo-author idiom
--  restore Wyrmreach fixtures, then land the _l2_error_signatures choice_id fix (5.3)
```

**Step 3 must re-quantify before it writes.** `CH-3` as originally specified rejects every
participating book; the split in section 5.1 is a prerequisite of the module, not a later
refinement.

**Why step 8a exists (D12).** All nine 8-11 skeletons declare zero variables, consistent with Tier 1,
and `L1-6` forbids a Tier-1 book from declaring any
(`layer1.py:478-490`); tier is `metadata.tier`.
**No Tier-2 8-11 book exists**, so piloting prose at the band D3 names is real authoring work. It is
scheduled as its own step rather than absorbed into the pilot step, because a promotion that turns
out to be expensive should stall visibly rather than quietly enlarge step 8b.

Measured candidates (config count equals node count exactly, confirming zero variables):

| Skeleton | Nodes | Endings | Decisions | Length | Lineage variant |
|---|---|---|---|---|---|
| `the-storm-chasers-club` | 121 | 25 | 23 | medium | no |
| `the-river-of-small-boats` | 127 | 26 | 24 | medium | no |
| `the-clockwork-menagerie` | 166 | 27 | 29 | long | yes |
| `the-hundred-door-hotel` | 176 | 31 | 118 | long | no |

**Recommended: `the-storm-chasers-club`.** It has the most headroom inside the 8-11 medium prose
node envelope of (100, 160, 30), so a gate node, a build node, and six flavour branches fit without
approaching the ceiling. It carries no `.lineage.json`, so promoting it does not perturb mutation
lineage. `the-hundred-door-hotel` is rejected despite its size: 118 decisions across 176 nodes is a
hub topology that is expensive to retrofit archetype gating into.

`CH-8` is not a constraint at this band. Post-promotion with a six-way build node these books land
at roughly 6x their node count, so 384 to 1,146 configurations against a 16,600 threshold. The
`CH-8` risk is a 10-13 and 13-16 problem, not an 8-11 one.

For reference if the prose pilot ever moves bands: `10-13/the-glass-comet` (638 configs) is the only
existing Tier-2 prose book with enough headroom. `the-flooded-quarter` and
`the-winter-of-the-wolf-queen` both cap out under the build-node idiom (section 4.3.2).

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
| Participating prose books fail their own L2-11 gate before CH-* runs | **Accepted. This disposition was originally wrong and round 2 corrected it.** The draft claimed the `archetype = 0` idiom made union quantification unnecessary. It does not: the idiom fixes the *existing* declared-initials gate (4.3, verified), but the *new* rule still needs union quantification or it rejects every participating book. See `CH-3a`/`CH-3b` in 5.1 |
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

### Round 2 (narrowed scope, after the full run hit a usage limit)

Verdict on the two questions asked: Q1 **needs revision**, Q2 **sound with a merge gate**.

| Finding | Disposition |
|---|---|
| 4.3 is correct that the idiom keeps the *existing* declared-initials gate green; `_ever_visible_choice_ids` is a global accumulator, so one visible config clears a choice permanently | **Confirmed, and now stated as verified rather than argued** (4.3) |
| The draft's per-state `CH-3` rejects every participating book, because character-gated branches are correctly invisible in states that do not select them. 6-8 new errors per non-zero envelope state | **Accepted. Fatal, and fixed**: `CH-3` splits into union-quantified `CH-3a` (L2-11) and per-state `CH-3b` (L2-9/10/14). Section 10's original disposition of the round-1 finding is corrected above |
| A build node that is always entered gives a returning reader a zero-button page, a runtime break, plus L2-9 and L2-10 | **Accepted.** The required shape is a bypass gate, specified in 4.3.1. The draft described the broken shape |
| The build node makes `archetype` mutable, costing 6.00x on the *baseline* walk; two catalog books cap out | **Accepted.** 4.3.2 measures it, 4.5 is rescoped, and `CH-8` gates it. The draft validated 4.3 and 4.5 in isolation and never measured their composition |
| No Tier-2 8-11 book exists (`L1-6` forbids Tier-1 variables), so the 8-11 prose pilot is unscheduled work | **Accepted, escalated, and decided (D12)**: promote `8-11/the-storm-chasers-club` to Tier 2 as step 8a. Piloting prose at `the-glass-comet` was the alternative and was declined, because it would have tested the prose case at a band D3 did not name |
| The `choice_id` signature change can only add findings, but the Wyrmreach fixtures are missing and `validate_series` runs on the approve path | **Accepted.** Merge-gated and moved out of step 3 (5.3, 9.2) |

### Round 3 (PR review of #636, 2026-08-06)

The PR under review implemented step 0 (ADR-025) and carried this spec as a new file. The review's
findings against the spec itself are dispositioned here; the ADR-025 code findings are in that
ADR's implementation notes and in `AL-080`/`UW-C26`.

| Finding | Disposition |
|---|---|
| 13 markdown links pointed outside `docs/`, aborting `mkdocs build --strict` | **Accepted, and it was a live build break, not a lint nit.** Converted to plain code spans, matching the dominant `docs/planning/` convention. Absolute `blob/main` URLs were rejected as the fix: they would have traded a mkdocs failure for 13 new lychee targets that rot as lines move |
| Ground truth 11 ("ADR-025 accepted but not implemented") and §9.1 ("scheduled nowhere") were falsified by the same PR that carried this file | **Accepted.** Both annotated in place rather than rewritten, so the design's original reasoning stays auditable; §9.2 step 0 marked done |
| §2.1 "Skeletons total 124" counts sidecars | **Accepted.** 124 = 61 skeletons + 47 `.contract.json` + 16 `.lineage.json`. The real denominator is 61, which also moves the backfill population from an apparent 11% to 23% |
| `is_active = true` with a non-null `retired_at` is representable, matches the partial unique index, and silently blocks activating a replacement | **Accepted.** Table CHECK added (3.1); retire-plus-activate specified as one transaction |
| `character_attribute` accepts `value_bool` and any integer; `num_nonnulls` does not enforce the vocabulary contract | **Accepted.** `value_bool` dropped for v1 and the column made `NOT NULL`, with a per-name range CHECK (3.1). Recorded as a deliberate divergence from `child_profile_personalization`'s multi-shape pattern |
| `CH-1` checks envelope-to-`variables` only; a book can declare a canonical variable it does not accept, and G3 carries it | **Accepted.** `CH-1` becomes set equality in both directions (5.1). `CH-6` does not cover this: it governs non-participating books, and this is the participating case |
| `CH-2` equality does not bound the pair; `might: -1..3` would pass | **Accepted.** `CH-2` gains `min <= max` plus canonical-range containment, narrower per-book ranges still legal (5.1) |
| The integrity guarantee in 3.3 was attributed to `CH-2` alone | **Accepted.** Restated as resting on four rules (`CH-1`, `CH-2` equality, `CH-2` containment, `CH-6`), so weakening any one reads as breaking a stated invariant |
| The reading state must be bound to a character, but nothing said the binding is server-derived | **Accepted.** A client-supplied `character_id` would let a reader credit progression onto another profile's character; the server resolves it from the authenticated profile's active character (7.2) |
| `character_name` has no `child_profile_personalization` row, so any purge enumerating that table misses it silently | **Accepted, and it is the worst failure shape available** under ADR-018: a deletion that reports success while a child-typed name survives. Storage contract, slot-clear semantics, and the need for an explicit storage map written up in 6.1. No `PURGEABLE_SLOT_TYPES` constant exists today, so this is creating that map |
| Idempotency keyed on `(reading_state_id, character_id)` as a lookup, not a constraint | **Accepted.** Two concurrent syncs can both see no prior completion. Specified as a `character_book_completion` PK with insert-then-increment, plus the `max()` lost-update fixed by computing `GREATEST` in the statement (7.3) |
| 7.1/7.3 require reading-state persistence the migration step never creates | **Accepted.** `reading_state.character_id` and `.seed_var_state` specified and added to build order step 4 (7.3, 9.2) |
| `character` is annotated ADR-022 Tier 1 but carries no `family_id` | **Accepted.** ADR-022's own debt clause demotes such a table to Tier 2 pending denormalization rather than allowing a subquery predicate. Written up as an explicit choice with its consequences, not an annotation (3.4) |
| No authorization matrix for a row that both a kid and a guardian act on | **Accepted.** Matrix added (3.4). The load-bearing row is that no principal may write attributes or `books_completed`; they are earned, never set |
| Nothing stated whether characters reach generation, cover art, or moderation | **Accepted.** Written as invariants in 3.5. Two of them (byte-identical books, per-storybook covers) are what keep the feature cheap and the envelope proof possible |
| Changed markdown must stay within 120 characters | **Declined.** `.markdownlint.json` sets `MD013: false` and `line-length: false`; no gate enforces a line length on markdown in this repo, and the surrounding tables already exceed it. Raising it here would reformat unrelated content to satisfy a rule the project has switched off |
| Three fenced blocks lacked a language identifier (MD040) | **Accepted.** Labelled `text` |
